"""Focused FR-235/FR-236 portable common-lock and fence tests."""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from types import ModuleType
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = ROOT / "scripts" / "forge" / "cli.py"
CHAIN_ID = "c-2026-08-29T120000Z-abcd"


from tests._cli_loader import load_script  # cli split phase 0: one shared loader


CLI = load_script("forge_cli_common_lock_tests", CLI_PATH)


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.value += seconds


def git(*args: str, cwd: Path) -> bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout


def init_repo(root: Path) -> None:
    git("init", "-q", cwd=root)
    git("config", "user.name", "Forge Lock Test", cwd=root)
    git("config", "user.email", "forge-lock@example.invalid", cwd=root)
    (root / "tracked.txt").write_text("initial\n", encoding="utf-8")
    git("add", "tracked.txt", cwd=root)
    git("commit", "-qm", "initial", cwd=root)


def fork_owner_crash(common: Path, stage: str) -> int:
    pid = os.fork()
    if pid == 0:
        def boundary(observed: str) -> None:
            if observed == stage:
                os._exit(73)

        try:
            CLI.acquire_common_lock(
                common,
                owner_kind="phase5",
                chain_id=None,
                operation="phase5-scan",
                use_flock=False,
                timeout=2,
                boundary=boundary,
            )
        except BaseException:
            os._exit(74)
        os._exit(75)
    observed, status_value = os.waitpid(pid, 0)
    if observed != pid or os.waitstatus_to_exitcode(status_value) != 73:
        raise AssertionError(f"crash child did not reach {stage}")
    return pid


def fork_fence_crash(common: Path, stage: str, marker: Path, result_file: Path) -> int:
    pid = os.fork()
    if pid == 0:
        def boundary(observed: str) -> None:
            if observed == stage:
                os._exit(83)

        try:
            lock = CLI.acquire_common_lock(
                common,
                owner_kind="merge",
                chain_id=CHAIN_ID,
                operation="finalize",
                use_flock=False,
                timeout=2,
                no_transaction_record=True,
                boundary=boundary,
            )

            def persist(result: object) -> None:
                evidence = result.evidence()
                result_file.write_bytes(CLI.canonical_bytes(evidence))

            CLI.run_fenced_command(
                lock,
                operation="fetch",
                intent_digest=hashlib.sha256(b"durable-intent").hexdigest(),
                intent_validator=lambda: True,
                argv=[
                    sys.executable,
                    "-c",
                    (
                        "from pathlib import Path; "
                        f"Path({str(marker)!r}).write_text('ran', encoding='utf-8')"
                    ),
                ],
                cwd=common,
                persist_result=persist,
                timeout=2,
            )
        except BaseException:
            os._exit(84)
        os._exit(85)
    observed, status_value = os.waitpid(pid, 0)
    if observed != pid or os.waitstatus_to_exitcode(status_value) != 83:
        raise AssertionError(f"fence crash child did not reach {stage}")
    return pid


class PortableCommonLockTests(unittest.TestCase):
    def test_merge_and_push_require_recorder_or_explicit_no_transaction_opt_out(self) -> None:
        owners = (
            ("merge", CHAIN_ID, "finalize"),
            ("push", None, "push"),
        )
        for owner_kind, chain_id, operation in owners:
            with self.subTest(owner_kind=owner_kind), tempfile.TemporaryDirectory() as temporary:
                common = Path(temporary)
                with self.assertRaisesRegex(ValueError, "recorder"):
                    CLI.acquire_common_lock(
                        common,
                        owner_kind=owner_kind,
                        chain_id=chain_id,
                        operation=operation,
                        use_flock=False,
                        timeout=2,
                    )
                self.assertEqual(CLI.inspect_common_lock(common).topology, "free")

                lock = CLI.acquire_common_lock(
                    common,
                    owner_kind=owner_kind,
                    chain_id=chain_id,
                    operation=operation,
                    use_flock=False,
                    timeout=2,
                    no_transaction_record=True,
                )
                lock.release()

    def test_owner_record_publication_and_release_boundaries_are_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            common = Path(temporary)
            stages: list[tuple[str, str]] = []

            def boundary(stage: str) -> None:
                if stage.startswith("owner-") or stage.startswith("release-") or stage.startswith("flock-"):
                    stages.append((stage, CLI.inspect_common_lock(common).topology))

            lock = CLI.acquire_common_lock(
                common,
                owner_kind="merge",
                chain_id=CHAIN_ID,
                operation="finalize",
                timeout=2,
                no_transaction_record=True,
                boundary=boundary,
            )
            inspection = CLI.inspect_common_lock(common)
            self.assertEqual(inspection.topology, "complete")
            self.assertIsNotNone(inspection.outer)
            self.assertIsNotNone(inspection.inner)
            outer = inspection.outer
            inner = inspection.inner
            assert outer is not None and inner is not None
            self.assertEqual(set(outer.record), CLI._COMMON_LOCK_OWNER_KEYS)
            self.assertEqual(outer.record["schema"], "forge-rebase-lock/1")
            self.assertEqual(outer.record["owner_kind"], "merge")
            self.assertEqual(outer.record["chain_id"], CHAIN_ID)
            self.assertEqual(outer.record["operation"], "finalize")
            self.assertEqual(outer.inode, inner.inode)
            self.assertEqual(outer.digest, inner.digest)
            self.assertEqual(outer.mode, 0o600)
            self.assertEqual(
                (common / CLI.COMMON_LOCK_INTENT_NAME).read_bytes(),
                CLI.canonical_bytes(outer.record),
            )
            self.assertEqual(
                (common / CLI.COMMON_LOCK_FLOCK_NAME).read_bytes(),
                CLI.canonical_bytes(outer.record),
            )
            self.assertEqual(
                (common / CLI.COMMON_LOCK_DIRECTORY_NAME).stat().st_mode & 0o777,
                0o700,
            )
            lock.release()
            self.assertEqual(CLI.inspect_common_lock(common).topology, "free")

            observed_names = [name for name, _topology in stages]
            self.assertEqual(
                observed_names[:8],
                [
                    "owner-temp-fsynced",
                    "owner-intent-published",
                    "owner-temp-unlinked",
                    "owner-lockdir-created",
                    "owner-inner-linked",
                    "owner-portable-fsynced",
                    "flock-acquired",
                    "flock-record-fsynced",
                ],
            )
            release_names = [name for name in observed_names if name.startswith("release-")]
            self.assertEqual(
                release_names,
                [
                    "release-flock",
                    "release-inner-unlinked",
                    "release-inner-fsynced",
                    "release-lockdir-removed",
                    "release-parent-fsynced",
                    "release-intent-unlinked",
                    "release-final-fsynced",
                ],
            )
            topology_by_stage = dict(stages)
            self.assertEqual(topology_by_stage["release-inner-unlinked"], "outer-empty-directory")
            self.assertEqual(topology_by_stage["release-lockdir-removed"], "outer-only")
            self.assertEqual(topology_by_stage["release-parent-fsynced"], "outer-only")
            self.assertEqual(topology_by_stage["release-intent-unlinked"], "free")

    def test_every_release_failure_preserves_identity_and_admits_only_release_recovery(self) -> None:
        stages = (
            "release-flock",
            "release-inner-unlinked",
            "release-inner-fsynced",
            "release-lockdir-removed",
            "release-parent-fsynced",
            "release-intent-unlinked",
            "release-final-fsynced",
        )
        for failed_stage in stages:
            with self.subTest(stage=failed_stage), tempfile.TemporaryDirectory() as temporary:
                common = Path(temporary)
                lock = CLI.acquire_common_lock(
                    common,
                    owner_kind="phase5",
                    chain_id=None,
                    operation="phase5-scan",
                    use_flock=True,
                    timeout=2,
                )

                def fail(stage: str) -> None:
                    if stage == failed_stage:
                        raise OSError(f"injected {stage} failure")

                lock._boundary = fail
                with self.assertRaises(CLI.CommonLockReleaseFailure) as raised:
                    lock.release()
                self.assertEqual(raised.exception.reason_code.value, "lock-release-failed")
                self.assertTrue(lock._release_pending)
                with self.assertRaises(OSError):
                    lock.assert_held()
                lock._boundary = None
                lock.retry_release()
                self.assertTrue(lock.released)
                self.assertEqual(CLI.inspect_common_lock(common).topology, "free")

        with tempfile.TemporaryDirectory() as temporary:
            common = Path(temporary)
            lock = CLI.acquire_common_lock(
                common,
                owner_kind="phase5",
                chain_id=None,
                operation="phase5-scan",
                use_flock=True,
                timeout=2,
            )
            real_flock = lock._flock_impl

            def fail_unlock(descriptor: int, operation: int) -> None:
                if operation == CLI.fcntl.LOCK_UN:
                    raise OSError("injected kernel unlock failure")
                real_flock(descriptor, operation)

            lock._flock_impl = fail_unlock
            with self.assertRaises(CLI.CommonLockReleaseFailure):
                lock.release()
            self.assertEqual(CLI.inspect_common_lock(common).topology, "complete")
            lock._flock_impl = real_flock
            lock.retry_release()

    def test_every_canonical_acquisition_crash_boundary_is_observable_and_recoverable(self) -> None:
        expected = {
            "owner-temp-fsynced": "free",
            "owner-intent-published": "outer-only",
            "owner-temp-unlinked": "outer-only",
            "owner-lockdir-created": "outer-empty-directory",
            "owner-inner-linked": "complete",
            "owner-portable-fsynced": "complete",
        }
        for stage, topology in expected.items():
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as temporary:
                common = Path(temporary)
                fork_owner_crash(common, stage)
                self.assertEqual(CLI.inspect_common_lock(common).topology, topology)
                if topology != "free":
                    proofs: list[dict[str, object]] = []
                    recovered = CLI.acquire_common_lock(
                        common,
                        owner_kind="phase5",
                        chain_id=None,
                        operation="phase5-scan",
                        use_flock=False,
                        timeout=2,
                        recovery_recorder=proofs.append,
                    )
                    self.assertTrue(proofs)
                    reservation_proof = proofs[0]
                    self.assertEqual(
                        set(reservation_proof), CLI._COMMON_LOCK_RECOVERY_KEYS
                    )
                    recovered.release()
                    self.assertEqual(CLI.inspect_common_lock(common).topology, "free")

    def test_only_three_published_topologies_are_recovered(self) -> None:
        stages = (
            "owner-intent-published",
            "owner-lockdir-created",
            "owner-portable-fsynced",
        )
        for stage in stages:
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as temporary:
                common = Path(temporary)
                fork_owner_crash(common, stage)
                lock = CLI.acquire_common_lock(
                    common,
                    owner_kind="phase5",
                    chain_id=None,
                    operation="phase5-scan",
                    use_flock=False,
                    timeout=2,
                )
                lock.release()

        with tempfile.TemporaryDirectory() as temporary:
            common = Path(temporary)
            (common / CLI.COMMON_LOCK_DIRECTORY_NAME).mkdir(mode=0o700)
            clock = FakeClock()
            with self.assertRaises(CLI.CommonLockUnavailable):
                CLI.acquire_common_lock(
                    common,
                    owner_kind="phase5",
                    chain_id=None,
                    operation="phase5-scan",
                    use_flock=False,
                    timeout=300,
                    clock=clock,
                    sleeper=clock.sleep,
                )
            self.assertEqual(clock.value, 300.0)
            self.assertTrue((common / CLI.COMMON_LOCK_DIRECTORY_NAME).is_dir())

    def test_recovery_reservation_is_exact_and_a_crashed_claimant_is_never_reclaimed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            common = Path(temporary)
            fork_owner_crash(common, "owner-portable-fsynced")
            child = os.fork()
            if child == 0:
                def boundary(stage: str) -> None:
                    if stage == "recovery-reservation-published":
                        os._exit(91)

                try:
                    CLI.acquire_common_lock(
                        common,
                        owner_kind="phase5",
                        chain_id=None,
                        operation="phase5-scan",
                        use_flock=False,
                        timeout=2,
                        boundary=boundary,
                    )
                except BaseException:
                    os._exit(92)
                os._exit(93)
            _pid, status_value = os.waitpid(child, 0)
            self.assertEqual(os.waitstatus_to_exitcode(status_value), 91)
            reservation_path = common / CLI.COMMON_LOCK_RECOVERY_NAME
            before = reservation_path.read_bytes()
            parsed = json.loads(before)
            self.assertEqual(set(parsed), CLI._COMMON_LOCK_RECOVERY_KEYS)
            self.assertEqual(parsed["schema"], "forge-rebase-recovery/1")
            self.assertEqual(parsed["recovery_kind"], "fallback-owner")
            before_inode = reservation_path.stat().st_ino
            clock = FakeClock()
            with self.assertRaises(CLI.CommonLockUnavailable) as raised:
                CLI.acquire_common_lock(
                    common,
                    owner_kind="phase5",
                    chain_id=None,
                    operation="phase5-scan",
                    use_flock=False,
                    timeout=300,
                    clock=clock,
                    sleeper=clock.sleep,
                    pid_probe=lambda _pid: "dead",
                )
            self.assertEqual(clock.value, 300.0)
            self.assertEqual(raised.exception.reason_code.value, "rebase-lock-unavailable")
            self.assertEqual(reservation_path.read_bytes(), before)
            self.assertEqual(reservation_path.stat().st_ino, before_inode)

    def test_successful_recovery_exercises_every_reservation_and_release_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            common = Path(temporary)
            fork_owner_crash(common, "owner-lockdir-created")
            stages: list[str] = []
            lock = CLI.acquire_common_lock(
                common,
                owner_kind="phase5",
                chain_id=None,
                operation="phase5-scan",
                use_flock=False,
                timeout=2,
                boundary=stages.append,
            )
            for expected in (
                "recovery-temp-fsynced",
                "recovery-reservation-published",
                "recovery-temp-unlinked",
                "recovery-release-inner-completed",
                "recovery-release-inner-unlinked",
                "recovery-release-inner-fsynced",
                "recovery-release-lockdir-removed",
                "recovery-release-parent-fsynced",
                "recovery-release-intent-unlinked",
                "recovery-release-final-fsynced",
                "recovery-stale-owner-released",
                "recovery-reservation-cleared",
            ):
                self.assertIn(expected, stages)
            self.assertLess(
                stages.index("recovery-stale-owner-released"),
                stages.index("recovery-reservation-cleared"),
            )
            lock.release()

    def test_cross_backend_contenders_share_the_portable_namespace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            common = Path(temporary)
            linux = CLI.acquire_common_lock(
                common,
                owner_kind="phase5",
                chain_id=None,
                operation="phase5-scan",
                use_flock=True,
                timeout=2,
            )
            results: list[str] = []

            def contend() -> None:
                try:
                    CLI.acquire_common_lock(
                        common,
                        owner_kind="phase5",
                        chain_id=None,
                        operation="phase5-scan",
                        use_flock=False,
                        timeout=0.15,
                    )
                except CLI.CommonLockUnavailable:
                    results.append("blocked")

            thread = threading.Thread(target=contend)
            thread.start()
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(results, ["blocked"])
            linux.release()
            portable_only = CLI.acquire_common_lock(
                common,
                owner_kind="phase5",
                chain_id=None,
                operation="phase5-scan",
                use_flock=False,
                timeout=2,
            )
            portable_only.release()

    def test_one_injected_300_second_budget_covers_portable_and_flock_waits(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            common = Path(temporary)
            holder = CLI.acquire_common_lock(
                common,
                owner_kind="phase5",
                chain_id=None,
                operation="phase5-scan",
                use_flock=False,
                timeout=2,
            )
            clock = FakeClock()
            with self.assertRaises(CLI.CommonLockUnavailable):
                CLI.acquire_common_lock(
                    common,
                    owner_kind="phase5",
                    chain_id=None,
                    operation="phase5-scan",
                    use_flock=False,
                    timeout=300,
                    clock=clock,
                    sleeper=clock.sleep,
                )
            self.assertEqual(clock.value, 300.0)
            self.assertAlmostEqual(sum(clock.sleeps), 300.0)
            holder.release()

        with tempfile.TemporaryDirectory() as temporary:
            common = Path(temporary)
            clock = FakeClock()

            def busy(_descriptor: int, _operation: int) -> None:
                raise BlockingIOError(11, "busy")

            with self.assertRaises(CLI.CommonLockUnavailable):
                CLI.acquire_common_lock(
                    common,
                    owner_kind="phase5",
                    chain_id=None,
                    operation="phase5-scan",
                    use_flock=True,
                    timeout=300,
                    clock=clock,
                    sleeper=clock.sleep,
                    flock_impl=busy,
                )
            self.assertEqual(clock.value, 300.0)
            self.assertEqual(CLI.inspect_common_lock(common).topology, "free")

        with tempfile.TemporaryDirectory() as temporary:
            common = Path(temporary)
            fork_owner_crash(common, "owner-portable-fsynced")
            clock = FakeClock()

            def proof_exhausts_budget(_pid: int) -> str:
                clock.value = 300.0
                return "dead"

            before = (common / CLI.COMMON_LOCK_INTENT_NAME).read_bytes()
            with self.assertRaises(CLI.CommonLockUnavailable):
                CLI.acquire_common_lock(
                    common,
                    owner_kind="phase5",
                    chain_id=None,
                    operation="phase5-scan",
                    use_flock=False,
                    timeout=300,
                    clock=clock,
                    sleeper=clock.sleep,
                    pid_probe=proof_exhausts_budget,
                )
            self.assertEqual(
                (common / CLI.COMMON_LOCK_INTENT_NAME).read_bytes(), before
            )
            self.assertFalse((common / CLI.COMMON_LOCK_RECOVERY_NAME).exists())


class ChainLeaseTests(unittest.TestCase):
    def test_single_attempt_lease_contention_never_sleeps_or_resets_budget(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            chains = Path(temporary)
            holder = CLI.acquire_chain_lease(
                chains,
                chain_id=CHAIN_ID,
                session="holder-session",
                timeout=2,
            )
            clock = FakeClock()
            sleeper = mock.Mock(
                side_effect=AssertionError("single-attempt lease acquisition slept")
            )
            try:
                with self.assertRaises(CLI.ChainLeaseUnavailable):
                    CLI.acquire_chain_lease(
                        chains,
                        chain_id=CHAIN_ID,
                        session="contender-session",
                        timeout=300,
                        clock=clock,
                        sleeper=sleeper,
                        single_attempt=True,
                    )
            finally:
                holder.release()
            sleeper.assert_not_called()
            self.assertEqual(clock.value, 0.0)

    def test_lease_revalidates_inode_and_digest_before_every_write_and_release(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            chains = Path(temporary)
            lease = CLI.acquire_chain_lease(
                chains,
                chain_id=CHAIN_ID,
                session="stable-session",
                timeout=2,
            )
            path = lease.path
            original = path.read_bytes()
            original_inode = path.stat().st_ino
            replacement = chains / "replacement"
            replacement.write_bytes(original)
            replacement.chmod(0o600)
            path.unlink()
            replacement.rename(path)
            self.assertNotEqual(path.stat().st_ino, original_inode)
            with self.assertRaises(OSError):
                lease.before_event_append()
            with self.assertRaises(OSError):
                lease.before_state_replace()
            with self.assertRaises(OSError):
                lease.release()
            self.assertEqual(path.read_bytes(), original)
            path.unlink()
            os.close(lease._directory)
            lease._directory = -1

    def test_stale_lease_reclaim_requires_matching_common_exclusion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            common = root / "git-common"
            chains = root / "chains"
            common.mkdir()
            chains.mkdir()
            child = os.fork()
            if child == 0:
                CLI.acquire_chain_lease(
                    chains,
                    chain_id=CHAIN_ID,
                    session="dead-session",
                    timeout=2,
                )
                os._exit(0)
            os.waitpid(child, 0)
            clock = FakeClock()
            with self.assertRaises(CLI.ChainLeaseUnavailable):
                CLI.acquire_chain_lease(
                    chains,
                    chain_id=CHAIN_ID,
                    session="new-session",
                    timeout=1,
                    clock=clock,
                    sleeper=clock.sleep,
                    pid_probe=lambda _pid: "dead",
                )
            lock = CLI.acquire_common_lock(
                common,
                owner_kind="merge",
                chain_id=CHAIN_ID,
                operation="recover",
                use_flock=False,
                timeout=2,
                no_transaction_record=True,
            )
            lease = CLI.acquire_chain_lease(
                chains,
                chain_id=CHAIN_ID,
                session="new-session",
                timeout=2,
                exclusion=lock,
                pid_probe=lambda _pid: "dead",
            )
            lease.before_event_append()
            lease.before_state_replace()
            lease.release()
            lock.release()


class FencedProcessTests(unittest.TestCase):
    def test_revision10_gate_intent_preimage_is_exact_and_load_bearing(self) -> None:
        digest = lambda label: hashlib.sha256(label.encode()).hexdigest()
        values = {
            "chain_id": CHAIN_ID,
            "epoch_intent_digest": digest("epoch"),
            "seal_event_digest": digest("seal"),
            "generation_digest": digest("generation"),
            "policy_digest": digest("policy"),
            "suite_digest": digest("suite"),
            "cursor": 0,
            "kind": "gate",
            "gate_id": "gate-1",
            "authorizing_event_digest": digest("seal"),
        }
        preimage = {
            "schema": "forge-merge-gate-intent/1",
            "chain_id": CHAIN_ID,
            "epoch_intent_digest": values["epoch_intent_digest"],
            "seal_event_digest": values["seal_event_digest"],
            "generation_digest": values["generation_digest"],
            "policy_digest": values["policy_digest"],
            "suite_digest": values["suite_digest"],
            "cursor": 0,
            "kind": "gate",
            "id": "gate-1",
            "authorizing_event_digest": values["authorizing_event_digest"],
        }
        self.assertEqual(
            CLI.merge_gate_intent_digest(**values),
            hashlib.sha256(CLI.canonical_bytes(preimage)).hexdigest(),
        )
        with mock.patch.object(
            CLI,
            "COMMON_LOCK_CONTROLS",
            CLI.COMMON_LOCK_CONTROLS - {"fence-intent-revalidation"},
        ), self.assertRaises(CLI.FrozenError):
            CLI.merge_gate_intent_digest(**values)

    def test_later_gate_first_publication_survives_elapsed_acquisition_deadline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            common = Path(temporary)
            lock = CLI.acquire_common_lock(
                common,
                owner_kind="merge",
                chain_id=CHAIN_ID,
                operation="finalize",
                use_flock=False,
                timeout=300,
                no_transaction_record=True,
            )
            saved: list[object] = []
            try:
                first = CLI.run_fenced_command(
                    lock,
                    operation="gate",
                    intent_digest=hashlib.sha256(b"gate-1").hexdigest(),
                    intent_validator=lambda: True,
                    argv=[sys.executable, "-c", "print('gate-1')"],
                    cwd=common,
                    persist_result=saved.append,
                    timeout=2,
                )
                self.assertEqual(first.returncode, 0)
                self.assertFalse(
                    (common / CLI.COMMON_LOCK_INFLIGHT_NAME).exists()
                )

                # Model Gate 1 consuming 400 seconds in the same validly held
                # epoch.  The free fence namespace still admits Gate 2's first
                # publication attempt even though acquisition's deadline ended.
                lock.deadline = lock._clock() - 100.0
                ack_deadlines: list[float] = []
                real_spawn = CLI._spawn_blocked_fence_child
                real_publish = CLI._publish_fence
                publication_attempts = 0

                def capture_ack_deadline(*args: object, **kwargs: object) -> object:
                    ack_deadlines.append(float(kwargs["deadline"]))
                    return real_spawn(*args, **kwargs)

                def collide_once(*args: object, **kwargs: object) -> object:
                    nonlocal publication_attempts
                    publication_attempts += 1
                    if publication_attempts == 1:
                        raise FileExistsError
                    return real_publish(*args, **kwargs)

                with mock.patch.object(
                    CLI,
                    "_spawn_blocked_fence_child",
                    side_effect=capture_ack_deadline,
                ), mock.patch.object(
                    CLI,
                    "_publish_fence",
                    side_effect=collide_once,
                ):
                    second = CLI.run_fenced_command(
                        lock,
                        operation="gate",
                        intent_digest=hashlib.sha256(b"gate-2").hexdigest(),
                        intent_validator=lambda: True,
                        argv=[sys.executable, "-c", "print('gate-2')"],
                        cwd=common,
                        persist_result=saved.append,
                        timeout=2,
                    )
                self.assertEqual(second.returncode, 0)
                self.assertEqual(len(saved), 2)
                self.assertEqual(len(ack_deadlines), 2)
                self.assertEqual(publication_attempts, 2)
                self.assertTrue(
                    all(deadline > lock.deadline for deadline in ack_deadlines)
                )
                self.assertFalse(
                    (common / CLI.COMMON_LOCK_INFLIGHT_NAME).exists()
                )
            finally:
                lock.release()

    def test_fence_publication_and_ack_retries_exhaust_one_fresh_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            common = Path(temporary)
            lock = CLI.acquire_common_lock(
                common,
                owner_kind="merge",
                chain_id=CHAIN_ID,
                operation="finalize",
                use_flock=False,
                timeout=2,
                no_transaction_record=True,
            )
            original_clock = lock._clock
            original_sleeper = lock._sleeper
            try:
                for failure in ("ack", "publication-exists", "publication-oserror"):
                    with self.subTest(failure=failure):
                        retry_clock = FakeClock()
                        lock._clock = retry_clock
                        lock._sleeper = retry_clock.sleep
                        fake_child = CLI._BlockedFenceChild(
                            pid=201,
                            pgid=201,
                            start_descriptor=202,
                            output_descriptor=203,
                            exec_error_descriptor=204,
                        )
                        def spawn_attempt(*_args: object, **_kwargs: object) -> object:
                            if failure == "ack":
                                raise OSError("ack failed")
                            return fake_child

                        publication_error = (
                            FileExistsError()
                            if failure == "publication-exists"
                            else OSError("transient publication failure")
                        )

                        with mock.patch.object(
                            CLI, "COMMON_LOCK_TIMEOUT_SECONDS", 0.1
                        ), mock.patch.object(
                            CLI,
                            "_spawn_blocked_fence_child",
                            side_effect=spawn_attempt,
                        ) as spawn, mock.patch.object(
                            CLI,
                            "_publish_fence",
                            side_effect=publication_error,
                        ) as publish, mock.patch.object(
                            CLI, "_stop_unstarted_child", return_value=True
                        ):
                            with self.assertRaises(CLI.CommonLockUnavailable):
                                CLI.run_fenced_command(
                                    lock,
                                    operation="gate",
                                    intent_digest=hashlib.sha256(
                                        failure.encode()
                                    ).hexdigest(),
                                    intent_validator=lambda: True,
                                    argv=["never-started"],
                                    cwd=common,
                                    persist_result=lambda _result: None,
                                    timeout=2,
                                )
                        self.assertEqual(retry_clock.value, 0.1)
                        self.assertEqual(spawn.call_count, 2)
                        self.assertEqual(
                            publish.call_count,
                            0 if failure == "ack" else 2,
                        )
            finally:
                lock._clock = original_clock
                lock._sleeper = original_sleeper
                lock.release()

    def test_slow_first_ack_failure_does_not_reset_publication_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            common = Path(temporary)
            lock = CLI.acquire_common_lock(
                common,
                owner_kind="merge",
                chain_id=CHAIN_ID,
                operation="finalize",
                use_flock=False,
                timeout=2,
                no_transaction_record=True,
            )
            original_clock = lock._clock
            original_sleeper = lock._sleeper
            retry_clock = FakeClock()
            lock._clock = retry_clock
            lock._sleeper = retry_clock.sleep

            def slow_failure(*_args: object, **kwargs: object) -> object:
                self.assertEqual(kwargs["deadline"], 0.1)
                retry_clock.sleep(0.09)
                raise OSError("slow acknowledgement failure")

            try:
                with mock.patch.object(
                    CLI, "COMMON_LOCK_TIMEOUT_SECONDS", 0.1
                ), mock.patch.object(
                    CLI,
                    "_spawn_blocked_fence_child",
                    side_effect=slow_failure,
                ) as spawn:
                    with self.assertRaises(CLI.CommonLockUnavailable):
                        CLI.run_fenced_command(
                            lock,
                            operation="gate",
                            intent_digest=hashlib.sha256(b"slow-ack").hexdigest(),
                            intent_validator=lambda: True,
                            argv=["never-started"],
                            cwd=common,
                            persist_result=lambda _result: None,
                            timeout=2,
                        )
                self.assertEqual(spawn.call_count, 1)
                self.assertEqual(retry_clock.value, 0.1)
            finally:
                lock._clock = original_clock
                lock._sleeper = original_sleeper
                lock.release()

    def test_unreaped_blocked_child_is_never_retried(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            common = Path(temporary)
            lock = CLI.acquire_common_lock(
                common,
                owner_kind="merge",
                chain_id=CHAIN_ID,
                operation="finalize",
                use_flock=False,
                timeout=2,
                no_transaction_record=True,
            )
            retry_clock = FakeClock()
            original_clock = lock._clock
            original_sleeper = lock._sleeper
            lock._clock = retry_clock
            lock._sleeper = retry_clock.sleep
            try:
                with mock.patch.object(
                    CLI,
                    "_spawn_blocked_fence_child",
                    side_effect=ChildProcessError("unreaped blocked child"),
                ) as spawn:
                    with self.assertRaisesRegex(
                        CLI.CommonLockUnavailable, "common rebase lock unavailable"
                    ):
                        CLI.run_fenced_command(
                            lock,
                            operation="gate",
                            intent_digest=hashlib.sha256(b"unreaped").hexdigest(),
                            intent_validator=lambda: True,
                            argv=["never-started"],
                            cwd=common,
                            persist_result=lambda _result: None,
                            timeout=2,
                        )
                self.assertEqual(spawn.call_count, 1)
                self.assertEqual(retry_clock.value, 0.0)
            finally:
                lock._clock = original_clock
                lock._sleeper = original_sleeper
                lock.release()

    def test_unexpected_failure_refuses_when_blocked_child_cannot_reap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            common = Path(temporary)
            lock = CLI.acquire_common_lock(
                common,
                owner_kind="merge",
                chain_id=CHAIN_ID,
                operation="finalize",
                use_flock=False,
                timeout=2,
                no_transaction_record=True,
            )
            child = CLI._BlockedFenceChild(
                pid=221,
                pgid=221,
                start_descriptor=222,
                output_descriptor=223,
                exec_error_descriptor=224,
            )
            try:
                with mock.patch.object(
                    CLI, "_spawn_blocked_fence_child", return_value=child
                ), mock.patch.object(
                    CLI, "_publish_fence", side_effect=RuntimeError("unexpected")
                ), mock.patch.object(
                    CLI, "_stop_unstarted_child", return_value=False
                ) as stop:
                    with self.assertRaises(CLI.CommonLockUnavailable):
                        CLI.run_fenced_command(
                            lock,
                            operation="gate",
                            intent_digest=hashlib.sha256(
                                b"unreaped-cleanup"
                            ).hexdigest(),
                            intent_validator=lambda: True,
                            argv=["never-started"],
                            cwd=common,
                            persist_result=lambda _result: None,
                            timeout=2,
                        )
                stop.assert_called_once_with(
                    child,
                    clock=lock._clock,
                    sleeper=lock._sleeper,
                )
            finally:
                lock.release()

    def test_blocked_child_pipe_setup_and_failed_ack_cleanup_are_bounded(self) -> None:
        closed: list[int] = []
        with mock.patch.object(
            CLI,
            "_pipe_cloexec",
            side_effect=[(201, 202), (203, 204), OSError("descriptor pressure")],
        ), mock.patch.object(CLI.os, "close", side_effect=closed.append):
            with self.assertRaisesRegex(OSError, "descriptor pressure"):
                CLI._spawn_blocked_fence_child(
                    ["never-started"],
                    cwd=Path.cwd(),
                    env=None,
                    deadline=1.0,
                    clock=lambda: 0.0,
                    sleeper=lambda _delay: None,
                )
        self.assertEqual(closed, [201, 202, 203, 204])

        closed.clear()
        pipe_pairs = [(211, 212), (213, 214), (215, 216), (217, 218)]
        clock = FakeClock()
        with mock.patch.object(
            CLI, "_pipe_cloexec", side_effect=pipe_pairs
        ), mock.patch.object(CLI.os, "fork", return_value=219), mock.patch.object(
            CLI.os, "close", side_effect=closed.append
        ), mock.patch.object(
            CLI, "_read_child_ack", side_effect=OSError("ack failed")
        ), mock.patch.object(
            CLI, "_wait_for_child_exit", side_effect=[False, False]
        ), mock.patch.object(CLI.os, "kill") as kill_child:
            with self.assertRaisesRegex(ChildProcessError, "could not be reaped"):
                CLI._spawn_blocked_fence_child(
                    ["never-started"],
                    cwd=Path.cwd(),
                    env=None,
                    deadline=1.0,
                    clock=clock,
                    sleeper=clock.sleep,
                )
        kill_child.assert_called_once_with(219, CLI.signal.SIGKILL)
        self.assertEqual(
            closed,
            [211, 214, 216, 218, 212, 213, 215, 217],
        )

    def test_parent_pipe_close_failures_reap_before_returning_error(self) -> None:
        for failed_descriptor in (231, 233):
            with self.subTest(failed_descriptor=failed_descriptor):
                pipe_pairs = [(231, 232), (233, 234), (235, 236), (237, 238)]
                close_attempts: list[int] = []
                failed_once = False

                def fail_selected_close(descriptor: int) -> None:
                    nonlocal failed_once
                    close_attempts.append(descriptor)
                    if descriptor == failed_descriptor and not failed_once:
                        failed_once = True
                        raise OSError("injected parent close failure")

                with mock.patch.object(
                    CLI, "_pipe_cloexec", side_effect=pipe_pairs
                ), mock.patch.object(
                    CLI.os, "fork", return_value=239
                ), mock.patch.object(
                    CLI.os, "close", side_effect=fail_selected_close
                ), mock.patch.object(
                    CLI, "_read_child_ack", return_value=(239, 239)
                ) as read_ack, mock.patch.object(
                    CLI.os, "getpgid", return_value=239
                ), mock.patch.object(
                    CLI, "_wait_for_child_exit", return_value=True
                ) as wait_for_exit:
                    with self.assertRaisesRegex(
                        OSError, "injected parent close failure"
                    ):
                        CLI._spawn_blocked_fence_child(
                            ["never-started"],
                            cwd=Path.cwd(),
                            env=None,
                            deadline=1.0,
                            clock=lambda: 0.0,
                            sleeper=lambda _delay: None,
                        )

                self.assertTrue(failed_once)
                wait_for_exit.assert_called_once()
                self.assertEqual(set(close_attempts), set(range(231, 239)))
                if failed_descriptor == 231:
                    read_ack.assert_not_called()
                else:
                    read_ack.assert_called_once()

    def test_private_record_write_failure_removes_only_its_created_inode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            common = Path(temporary)
            canonical, descriptor = CLI._open_owned_directory(common)
            try:
                with mock.patch.object(
                    CLI, "_write_all", side_effect=OSError("write failed")
                ):
                    with self.assertRaisesRegex(OSError, "write failed"):
                        CLI._create_private_record_at(
                            descriptor,
                            canonical,
                            "cleanup-probe",
                            {"schema": "cleanup-probe/1"},
                            boundary=None,
                            stage="unused",
                        )
                self.assertEqual(list(common.iterdir()), [])
            finally:
                os.close(descriptor)

    def test_private_record_close_failure_removes_temp_before_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            common = Path(temporary)
            canonical, descriptor = CLI._open_owned_directory(common)
            real_close = CLI.os.close
            failed_close = False

            def fail_first_close(opened: int) -> None:
                nonlocal failed_close
                if not failed_close:
                    failed_close = True
                    raise OSError("close failed")
                real_close(opened)

            try:
                with mock.patch.object(
                    CLI.os, "close", side_effect=fail_first_close
                ):
                    with self.assertRaisesRegex(OSError, "close failed"):
                        CLI._create_private_record_at(
                            descriptor,
                            canonical,
                            "close-cleanup-probe",
                            {"schema": "close-cleanup-probe/1"},
                            boundary=None,
                            stage="unused",
                        )
                self.assertTrue(failed_close)
                self.assertEqual(list(common.iterdir()), [])
            finally:
                os.close(descriptor)

    def test_fence_publication_mismatch_preserves_foreign_canonical_inode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            common = Path(temporary)
            lock = CLI.acquire_common_lock(
                common,
                owner_kind="merge",
                chain_id=CHAIN_ID,
                operation="finalize",
                use_flock=False,
                timeout=2,
                no_transaction_record=True,
            )
            own_record = CLI._validate_fence_record(
                {
                    "schema": "forge-rebase-inflight/1",
                    "owner_kind": "merge",
                    "chain_id": CHAIN_ID,
                    "operation": "gate",
                    "host": lock.owner.record["host"],
                    "pid": os.getpid(),
                    "pgid": os.getpgrp(),
                    "started_at": CLI.iso_z(),
                    "intent_digest": hashlib.sha256(b"own").hexdigest(),
                    "nonce": "a" * 32,
                }
            )
            foreign_record = {
                **own_record,
                "intent_digest": hashlib.sha256(b"foreign").hexdigest(),
                "nonce": "b" * 32,
            }
            foreign_bytes = CLI.canonical_bytes(foreign_record)
            real_read = CLI._read_owned_record_at
            replaced = False

            def replace_before_first_canonical_read(
                parent: int,
                name: str,
                absolute_path: Path,
                validator: object,
            ) -> object:
                nonlocal replaced
                if name == CLI.COMMON_LOCK_INFLIGHT_NAME and not replaced:
                    replaced = True
                    os.unlink(name, dir_fd=parent)
                    foreign_descriptor = os.open(
                        name,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                        0o600,
                        dir_fd=parent,
                    )
                    try:
                        CLI._write_all(foreign_descriptor, foreign_bytes)
                        os.fsync(foreign_descriptor)
                    finally:
                        os.close(foreign_descriptor)
                    os.fsync(parent)
                return real_read(parent, name, absolute_path, validator)

            fence_path = common / CLI.COMMON_LOCK_INFLIGHT_NAME
            try:
                with mock.patch.object(
                    CLI,
                    "_read_owned_record_at",
                    side_effect=replace_before_first_canonical_read,
                ):
                    with self.assertRaises(CLI._PublicationCleanupFailure):
                        CLI._publish_fence(lock, own_record)
                self.assertTrue(replaced)
                self.assertEqual(fence_path.read_bytes(), foreign_bytes)
                self.assertEqual(
                    [path.name for path in common.glob(".agent-rebase.inflight.*.tmp")],
                    [],
                )
            finally:
                if fence_path.exists():
                    fence_path.unlink()
                lock.release()

    def test_early_fence_fsync_failure_cleans_attempt_before_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            common = Path(temporary)
            lock = CLI.acquire_common_lock(
                common,
                owner_kind="merge",
                chain_id=CHAIN_ID,
                operation="finalize",
                use_flock=False,
                timeout=2,
                no_transaction_record=True,
            )
            real_fsync = CLI.os.fsync
            failed_common_fsync = False
            saved: list[CLI.FencedProcessResult] = []

            def fail_first_common_fsync(descriptor: int) -> None:
                nonlocal failed_common_fsync
                if descriptor == lock._common and not failed_common_fsync:
                    failed_common_fsync = True
                    raise OSError("transient directory fsync failure")
                real_fsync(descriptor)

            try:
                with mock.patch.object(
                    CLI.os, "fsync", side_effect=fail_first_common_fsync
                ):
                    result = CLI.run_fenced_command(
                        lock,
                        operation="gate",
                        intent_digest=hashlib.sha256(b"fsync-retry").hexdigest(),
                        intent_validator=lambda: True,
                        argv=[sys.executable, "-c", "print('retried')"],
                        cwd=common,
                        persist_result=saved.append,
                        timeout=2,
                    )
                self.assertTrue(failed_common_fsync)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(saved, [result])
                self.assertFalse(
                    (common / CLI.COMMON_LOCK_INFLIGHT_NAME).exists()
                )
                self.assertEqual(
                    [path.name for path in common.glob(".agent-rebase.inflight.*.tmp")],
                    [],
                )
            finally:
                lock.release()

    def test_failed_publication_child_cleanup_is_bounded(self) -> None:
        child = CLI._BlockedFenceChild(
            pid=201,
            pgid=201,
            start_descriptor=202,
            output_descriptor=203,
            exec_error_descriptor=204,
        )
        clock = FakeClock()
        closed: list[int] = []
        with mock.patch.object(
            CLI, "_waitpid_nohang", return_value=(False, None)
        ), mock.patch.object(CLI.os, "killpg") as kill_group, mock.patch.object(
            CLI.os, "close", side_effect=closed.append
        ):
            stopped = CLI._stop_unstarted_child(
                child,
                clock=clock,
                sleeper=clock.sleep,
            )

        self.assertFalse(stopped)
        self.assertAlmostEqual(
            clock.value,
            CLI.FENCED_CHILD_STOP_GRACE_SECONDS + CLI.FENCED_CHILD_REAP_SECONDS,
        )
        kill_group.assert_called_once_with(child.pgid, CLI.signal.SIGKILL)
        self.assertEqual(
            closed,
            [
                child.start_descriptor,
                child.output_descriptor,
                child.exec_error_descriptor,
            ],
        )

    def test_post_termination_drain_has_hard_byte_and_time_bounds(self) -> None:
        class AlwaysReadySelector:
            def __init__(self) -> None:
                self.closed = False

            def register(self, _descriptor: int, _events: int) -> None:
                pass

            def select(self, _timeout: float) -> list[tuple[object, int]]:
                return [(object(), CLI.selectors.EVENT_READ)]

            def close(self) -> None:
                self.closed = True

        class NoDrainRelay:
            def write(self, _value: str) -> int:
                raise AssertionError("post-termination output was relayed")

            def flush(self) -> None:
                raise AssertionError("post-termination output was flushed")

        for mode in ("bytes", "time", "classification", "verbose"):
            with self.subTest(mode=mode):
                output_descriptor = 101
                error_descriptor = 102
                child = CLI._BlockedFenceChild(
                    pid=103,
                    pgid=103,
                    start_descriptor=-1,
                    output_descriptor=output_descriptor,
                    exec_error_descriptor=error_descriptor,
                )
                clock = FakeClock()
                clock.value = 1.0
                selector = AlwaysReadySelector()
                output_reads = 0
                closed: list[int] = []

                def continuous_read(descriptor: int, size: int) -> bytes:
                    nonlocal output_reads
                    if descriptor == error_descriptor:
                        return b""
                    self.assertEqual(descriptor, output_descriptor)
                    output_reads += 1
                    if output_reads > 10:
                        raise AssertionError("post-termination drain was unbounded")
                    if mode in {"time", "verbose"}:
                        clock.value += 1.0
                        return b"x"
                    return b"x" * size

                normal_exit = mode in {"classification", "verbose"}
                stderr_patch = (
                    mock.patch.object(CLI.sys, "stderr", NoDrainRelay())
                    if mode == "verbose"
                    else contextlib.nullcontext()
                )
                with stderr_patch, mock.patch.object(
                    CLI.selectors, "DefaultSelector", return_value=selector
                ), mock.patch.object(
                    CLI.os, "set_blocking"
                ), mock.patch.object(
                    CLI.os, "read", side_effect=continuous_read
                ), mock.patch.object(
                    CLI.os, "close", side_effect=closed.append
                ), mock.patch.object(
                    CLI,
                    "_waitpid_nohang",
                    return_value=(True, 0) if normal_exit else (False, None),
                ), mock.patch.object(
                    CLI,
                    "_terminate_fenced_group",
                    return_value=(None, True),
                ):
                    result = CLI._collect_fenced_child(
                        child,
                        argv=["continuous-writer"],
                        started=0.0,
                        timeout=10.0 if normal_exit else 0.5,
                        cap=(
                            CLI.OUTPUT_CAP_BYTES
                            if mode == "classification"
                            else 16
                        ),
                        clock=clock,
                        sleeper=clock.sleep,
                        group_probe=(
                            (lambda _pgid: "dead")
                            if normal_exit
                            else (lambda _pgid: "live")
                        ),
                        signal_group=lambda _pgid, _signal: None,
                        verbose=mode == "verbose",
                    )

                self.assertEqual(result[3], not normal_exit)
                self.assertEqual(result[6], not normal_exit)
                self.assertEqual(
                    result[4], mode in {"bytes", "classification"}
                )
                self.assertLessEqual(
                    output_reads,
                    9 if mode in {"bytes", "classification"} else 2,
                )
                self.assertTrue(selector.closed)
                self.assertEqual(closed, [output_descriptor, error_descriptor])

    def test_merge_fence_death_proof_requires_reservation_classification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            common = Path(temporary)
            boundaries: list[str] = []
            lock = CLI.acquire_common_lock(
                common,
                owner_kind="merge",
                chain_id=CHAIN_ID,
                operation="recover",
                use_flock=True,
                timeout=2,
                group_probe=lambda _pgid: "dead",
                no_transaction_record=True,
                boundary=boundaries.append,
            )
            fence = CLI._publish_fence(
                lock,
                CLI._validate_fence_record(
                    {
                        "schema": "forge-rebase-inflight/1",
                        "owner_kind": "merge",
                        "chain_id": CHAIN_ID,
                        "operation": "gate",
                        "host": lock.owner.record["host"],
                        "pid": os.getpid(),
                        "pgid": os.getpgrp(),
                        "started_at": CLI.iso_z(),
                        "intent_digest": hashlib.sha256(
                            b"mandatory-death-proof"
                        ).hexdigest(),
                        "nonce": "a" * 32,
                    }
                ),
            )
            fence_path = common / CLI.COMMON_LOCK_INFLIGHT_NAME
            fence_bytes = fence_path.read_bytes()
            reservation_path = common / CLI.COMMON_LOCK_RECOVERY_NAME
            classified: list[dict[str, object]] = []

            def classify(
                reservation: CLI.RecoveryReservation,
                observed_fence: CLI.PublishedLockRecord | None,
            ) -> None:
                self.assertTrue(reservation_path.is_file())
                reservation.assert_current("fixture lifecycle classification")
                self.assertTrue(reservation.matches_chain(CHAIN_ID))
                self.assertEqual(fence_path.read_bytes(), fence_bytes)
                self.assertEqual(fence_path.stat().st_ino, fence.inode)
                self.assertIsNotNone(observed_fence)
                assert observed_fence is not None
                self.assertEqual(observed_fence.inode, fence.inode)
                self.assertEqual(observed_fence.digest, fence.digest)
                record = reservation.record
                self.assertEqual(
                    record["recovery_kind"], "flock-held-dead-fence"
                )
                self.assertEqual(record["inflight_inode"], fence.inode)
                self.assertEqual(record["inflight_digest"], fence.digest)
                self.assertIsNotNone(record["group_dead_at"])
                classified.append(record)

            try:
                with self.assertRaisesRegex(
                    OSError,
                    "reservation-held lifecycle classification is required",
                ):
                    lock.recover_owned_fence(fence)
                self.assertTrue(fence_path.exists())
                self.assertEqual(fence_path.stat().st_ino, fence.inode)
                self.assertFalse(reservation_path.exists())
                self.assertIn("recovery-reservation-published", boundaries)
                self.assertNotIn(
                    "recovery-fence-lifecycle-classified", boundaries
                )
                self.assertNotIn("recovery-fence-cleared", boundaries)

                boundaries.clear()
                lock.recover_owned_fence(
                    fence, lifecycle_classifier=classify
                )
                self.assertEqual(len(classified), 1)
                self.assertFalse(fence_path.exists())
                self.assertFalse(reservation_path.exists())
                self.assertLess(
                    boundaries.index("recovery-reservation-published"),
                    boundaries.index("recovery-fence-lifecycle-classified"),
                )
                self.assertLess(
                    boundaries.index("recovery-fence-lifecycle-classified"),
                    boundaries.index("recovery-fence-cleared"),
                )
            finally:
                if fence_path.exists():
                    lock.recover_owned_fence(
                        fence, lifecycle_classifier=classify
                    )
                lock.release()

    def test_phase5_refuses_surviving_fence_without_inspection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            common = Path(temporary)
            marker = common / "marker"
            result_file = common / "result.json"
            fork_fence_crash(
                common,
                "fence-before-authorization",
                marker,
                result_file,
            )
            intent_path = common / CLI.COMMON_LOCK_INTENT_NAME
            fence_path = common / CLI.COMMON_LOCK_INFLIGHT_NAME
            intent_bytes = intent_path.read_bytes()
            fence_bytes = fence_path.read_bytes()
            intent_inode = intent_path.stat().st_ino
            fence_inode = fence_path.stat().st_ino
            clock = FakeClock()
            pid_probe = mock.Mock(
                side_effect=AssertionError(
                    "ordinary acquisition must not probe the owner PID"
                )
            )
            group_probe = mock.Mock(
                side_effect=AssertionError(
                    "ordinary acquisition must not probe the fence PGID"
                )
            )

            with mock.patch.object(
                CLI,
                "_inspect_common_lock_fd",
                side_effect=AssertionError(
                    "ordinary acquisition must not inspect a fenced owner"
                ),
            ), mock.patch.object(
                CLI,
                "_read_fence_for_recovery",
                side_effect=AssertionError(
                    "ordinary acquisition must not read the fence"
                ),
            ), self.assertRaisesRegex(
                CLI.CommonLockUnavailable,
                "^forge: common rebase lock unavailable$",
            ) as raised:
                CLI.acquire_common_lock(
                    common,
                    owner_kind="phase5",
                    chain_id=None,
                    operation="phase5-scan",
                    use_flock=False,
                    timeout=300,
                    clock=clock,
                    sleeper=clock.sleep,
                    pid_probe=pid_probe,
                    group_probe=group_probe,
                )

            self.assertEqual(
                raised.exception.reason_code.value,
                "rebase-lock-unavailable",
            )
            self.assertEqual(
                json.loads(raised.exception.observed),
                {
                    "common_dir": str(common),
                    "detail": "surviving in-flight fence requires explicit recovery",
                },
            )
            self.assertEqual(clock.value, 300.0)
            self.assertAlmostEqual(sum(clock.sleeps), 300.0)
            pid_probe.assert_not_called()
            group_probe.assert_not_called()
            self.assertEqual(intent_path.read_bytes(), intent_bytes)
            self.assertEqual(fence_path.read_bytes(), fence_bytes)
            self.assertEqual(intent_path.stat().st_ino, intent_inode)
            self.assertEqual(fence_path.stat().st_ino, fence_inode)
            self.assertFalse((common / CLI.COMMON_LOCK_RECOVERY_NAME).exists())

    def test_all_four_authorization_and_result_crash_windows_are_observable(self) -> None:
        cases = {
            "fence-before-authorization": (False, False),
            "fence-after-authorization": (True, False),
            "fence-before-result": (True, False),
            "fence-result-persisted": (True, True),
        }
        for stage, (ran, result_persisted) in cases.items():
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as temporary:
                common = Path(temporary)
                marker = common / "marker"
                result_file = common / "result.json"
                fork_fence_crash(common, stage, marker, result_file)
                deadline = time.monotonic() + 2
                while ran and not marker.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertEqual(marker.exists(), ran)
                self.assertEqual(result_file.exists(), result_persisted)
                fence_path = common / CLI.COMMON_LOCK_INFLIGHT_NAME
                self.assertTrue(fence_path.exists())
                fence_bytes = fence_path.read_bytes()
                fence_record = json.loads(fence_bytes)
                fence_digest = hashlib.sha256(fence_bytes).hexdigest()
                fence_inode = fence_path.stat().st_ino
                intent_path = common / CLI.COMMON_LOCK_INTENT_NAME
                intent_bytes = intent_path.read_bytes()
                intent_inode = intent_path.stat().st_ino
                intent_digest = hashlib.sha256(intent_bytes).hexdigest()
                reservation_path = common / CLI.COMMON_LOCK_RECOVERY_NAME

                with self.assertRaises(CLI.CommonLockUnavailable) as refused:
                    CLI.acquire_common_lock(
                        common,
                        owner_kind="merge",
                        chain_id=CHAIN_ID,
                        operation="recover",
                        use_flock=False,
                        timeout=2,
                        pid_probe=lambda _pid: "dead",
                        group_probe=lambda _pgid: "dead",
                        no_transaction_record=True,
                    )
                self.assertIn(
                    "reservation-held lifecycle classification is required",
                    json.loads(refused.exception.observed)["detail"],
                )
                self.assertEqual(intent_path.read_bytes(), intent_bytes)
                self.assertEqual(intent_path.stat().st_ino, intent_inode)
                self.assertEqual(fence_path.read_bytes(), fence_bytes)
                self.assertEqual(fence_path.stat().st_ino, fence_inode)
                self.assertFalse(reservation_path.exists())

                classified: list[dict[str, object]] = []

                def classify(
                    reservation: CLI.RecoveryReservation,
                    observed_fence: CLI.PublishedLockRecord | None,
                ) -> None:
                    self.assertTrue(reservation_path.is_file())
                    reservation.assert_current(
                        "fixture lifecycle classification"
                    )
                    self.assertTrue(reservation.matches_chain(CHAIN_ID))
                    self.assertEqual(fence_path.read_bytes(), fence_bytes)
                    self.assertEqual(fence_path.stat().st_ino, fence_inode)
                    self.assertIsNotNone(observed_fence)
                    assert observed_fence is not None
                    self.assertEqual(observed_fence.inode, fence_inode)
                    self.assertEqual(observed_fence.digest, fence_digest)
                    self.assertEqual(observed_fence.record, fence_record)
                    record = reservation.record
                    self.assertEqual(
                        record["recovery_kind"], "fallback-owner-and-fence"
                    )
                    self.assertEqual(record["stale_owner_inode"], intent_inode)
                    self.assertEqual(record["stale_owner_digest"], intent_digest)
                    self.assertEqual(record["inflight_inode"], fence_inode)
                    self.assertEqual(record["inflight_digest"], fence_digest)
                    self.assertEqual(
                        record["group_dead_at"], record["owner_dead_at"]
                    )
                    classified.append(record)

                boundaries: list[str] = []
                recovered = CLI.acquire_common_lock(
                    common,
                    owner_kind="merge",
                    chain_id=CHAIN_ID,
                    operation="recover",
                    use_flock=False,
                    timeout=2,
                    pid_probe=lambda _pid: "dead",
                    group_probe=lambda _pgid: "dead",
                    no_transaction_record=True,
                    recovery_classifier=classify,
                    boundary=boundaries.append,
                )
                try:
                    self.assertEqual(len(classified), 1)
                    self.assertFalse(fence_path.exists())
                    self.assertFalse(reservation_path.exists())
                    self.assertLess(
                        boundaries.index("recovery-reservation-published"),
                        boundaries.index(
                            "recovery-fence-lifecycle-classified"
                        ),
                    )
                    self.assertLess(
                        boundaries.index(
                            "recovery-fence-lifecycle-classified"
                        ),
                        boundaries.index("recovery-fence-cleared"),
                    )
                finally:
                    recovered.release()

    def test_timeout_and_output_cap_both_use_term_quarter_second_then_kill(self) -> None:
        commands = (
            (
                "timeout",
                "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                "time.sleep(30)",
                65536,
            ),
            (
                "cap",
                "import os,signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                "os.write(1, b'x' * 70000); time.sleep(30)",
                1024,
            ),
        )
        for label, program, cap in commands:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                common = Path(temporary)
                lock = CLI.acquire_common_lock(
                    common,
                    owner_kind="merge",
                    chain_id=CHAIN_ID,
                    operation="finalize",
                    use_flock=False,
                    timeout=2,
                    no_transaction_record=True,
                )
                sent: list[tuple[int, float]] = []

                def send(pgid: int, chosen_signal: int) -> None:
                    sent.append((chosen_signal, time.monotonic()))
                    os.killpg(pgid, chosen_signal)

                saved: list[object] = []
                result = CLI.run_fenced_command(
                    lock,
                    operation="gate",
                    intent_digest=hashlib.sha256(label.encode()).hexdigest(),
                    intent_validator=lambda: True,
                    argv=[sys.executable, "-c", program],
                    cwd=common,
                    persist_result=saved.append,
                    timeout=0.08 if label == "timeout" else 5,
                    cap=cap,
                    signal_group=send,
                )
                self.assertEqual([item[0] for item in sent], [signal.SIGTERM, signal.SIGKILL])
                self.assertGreaterEqual(sent[1][1] - sent[0][1], 0.23)
                self.assertEqual(len(saved), 1)
                self.assertFalse(result.group_survived)
                if label == "timeout":
                    self.assertTrue(result.timed_out)
                else:
                    self.assertTrue(result.output_limit)
                    self.assertEqual(len(result.output), cap)
                self.assertFalse((common / CLI.COMMON_LOCK_INFLIGHT_NAME).exists())
                lock.release()

    def test_final_group_probe_is_persisted_before_survivor_refusal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            common = Path(temporary)
            lock = CLI.acquire_common_lock(
                common,
                owner_kind="merge",
                chain_id=CHAIN_ID,
                operation="finalize",
                use_flock=False,
                timeout=2,
                no_transaction_record=True,
            )
            persisted: list[CLI.FencedProcessResult] = []
            probe = mock.Mock(side_effect=["dead", "dead", "live"])
            with self.assertRaises(CLI.FencedChildSurvived) as caught:
                CLI.run_fenced_command(
                    lock,
                    operation="gate",
                    intent_digest=hashlib.sha256(b"final-probe").hexdigest(),
                    intent_validator=lambda: True,
                    argv=[sys.executable, "-c", "pass"],
                    cwd=common,
                    persist_result=persisted.append,
                    timeout=1,
                    group_probe=probe,
                )
            self.assertEqual(probe.call_count, 3)
            self.assertEqual(len(persisted), 1)
            self.assertTrue(persisted[0].group_survived)
            self.assertEqual(caught.exception.result, persisted[0])
            self.assertIsNotNone(lock._unresolved_fence)
            self.assertTrue((common / CLI.COMMON_LOCK_INFLIGHT_NAME).exists())
            assert lock._unresolved_fence is not None
            lock.recover_owned_fence(
                lock._unresolved_fence,
                lifecycle_classifier=lambda _reservation, _fence: None,
            )
            lock.release()

    def test_post_persist_group_probe_retains_durable_result_before_refusal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            common = Path(temporary)
            lock = CLI.acquire_common_lock(
                common,
                owner_kind="merge",
                chain_id=CHAIN_ID,
                operation="finalize",
                use_flock=False,
                timeout=2,
                no_transaction_record=True,
            )
            persisted: list[CLI.FencedProcessResult] = []
            observed_statuses: list[str] = []

            def probe_status(_pgid: int) -> str:
                status = "live" if persisted else "dead"
                observed_statuses.append(status)
                return status

            probe = mock.Mock(side_effect=probe_status)
            with self.assertRaises(CLI.FencedChildSurvived) as caught:
                CLI.run_fenced_command(
                    lock,
                    operation="gate",
                    intent_digest=hashlib.sha256(b"post-persist-probe").hexdigest(),
                    intent_validator=lambda: True,
                    argv=[sys.executable, "-c", "pass"],
                    cwd=common,
                    persist_result=persisted.append,
                    timeout=1,
                    group_probe=probe,
                )
            self.assertGreaterEqual(probe.call_count, 2)
            self.assertTrue(all(status == "dead" for status in observed_statuses[:-1]))
            self.assertEqual(observed_statuses[-1], "live")
            self.assertEqual(len(persisted), 1)
            self.assertFalse(persisted[0].group_survived)
            self.assertTrue(caught.exception.result.group_survived)
            persisted_evidence = persisted[0].evidence()
            refusal_evidence = dict(persisted_evidence)
            refusal_evidence["group_survived"] = True
            self.assertEqual(caught.exception.result.evidence(), refusal_evidence)
            self.assertEqual(caught.exception.result.output, persisted[0].output)
            self.assertEqual(caught.exception.result.metadata, persisted[0].metadata)
            self.assertIsNot(caught.exception.result, persisted[0])
            self.assertIsNotNone(lock._unresolved_fence)
            self.assertTrue((common / CLI.COMMON_LOCK_INFLIGHT_NAME).exists())
            assert lock._unresolved_fence is not None
            lock.recover_owned_fence(
                lock._unresolved_fence,
                lifecycle_classifier=lambda _reservation, _fence: None,
            )
            lock.release()

    def test_unprovable_survivor_fences_every_later_owner_after_parent_exit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            common = Path(temporary)
            child = os.fork()
            if child == 0:
                try:
                    lock = CLI.acquire_common_lock(
                        common,
                        owner_kind="merge",
                        chain_id=CHAIN_ID,
                        operation="finalize",
                        use_flock=False,
                        timeout=2,
                        no_transaction_record=True,
                    )
                    CLI.run_fenced_command(
                        lock,
                        operation="fetch",
                        intent_digest=hashlib.sha256(b"survivor").hexdigest(),
                        intent_validator=lambda: True,
                        argv=[sys.executable, "-c", "import time; time.sleep(30)"],
                        cwd=common,
                        persist_result=lambda _result: None,
                        timeout=0.05,
                        group_probe=lambda _pgid: "live",
                    )
                except CLI.FencedChildSurvived:
                    os._exit(101)
                except BaseException:
                    os._exit(102)
                os._exit(103)
            _pid, status_value = os.waitpid(child, 0)
            self.assertEqual(os.waitstatus_to_exitcode(status_value), 101)
            self.assertTrue((common / CLI.COMMON_LOCK_INFLIGHT_NAME).exists())
            fence_bytes = (
                common / CLI.COMMON_LOCK_INFLIGHT_NAME
            ).read_bytes()
            fence_record = json.loads(fence_bytes)
            fence_digest = hashlib.sha256(fence_bytes).hexdigest()
            fence_inode = (
                common / CLI.COMMON_LOCK_INFLIGHT_NAME
            ).stat().st_ino
            intent_path = common / CLI.COMMON_LOCK_INTENT_NAME
            intent_bytes = intent_path.read_bytes()
            intent_inode = intent_path.stat().st_ino
            intent_digest = hashlib.sha256(intent_bytes).hexdigest()
            reservation_path = common / CLI.COMMON_LOCK_RECOVERY_NAME
            contenders = (
                ("merge", "c-2026-08-29T120001Z-bbbb", "recover"),
                ("push", None, "push"),
            )
            for owner_kind, chain_id, operation in contenders:
                clock = FakeClock()
                with self.subTest(owner_kind=owner_kind), self.assertRaises(
                    CLI.CommonLockUnavailable
                ):
                    CLI.acquire_common_lock(
                        common,
                        owner_kind=owner_kind,
                        chain_id=chain_id,
                        operation=operation,
                        use_flock=False,
                        timeout=300,
                        clock=clock,
                        sleeper=clock.sleep,
                        pid_probe=lambda _pid: "dead",
                        group_probe=lambda _pgid: "live",
                        no_transaction_record=True,
                    )
                self.assertEqual(clock.value, 300.0)

            with self.assertRaises(CLI.CommonLockUnavailable) as refused:
                CLI.acquire_common_lock(
                    common,
                    owner_kind="merge",
                    chain_id=CHAIN_ID,
                    operation="recover",
                    use_flock=False,
                    timeout=2,
                    pid_probe=lambda _pid: "dead",
                    group_probe=lambda _pgid: "dead",
                    no_transaction_record=True,
                )
            self.assertIn(
                "reservation-held lifecycle classification is required",
                json.loads(refused.exception.observed)["detail"],
            )
            self.assertEqual(intent_path.read_bytes(), intent_bytes)
            self.assertEqual(intent_path.stat().st_ino, intent_inode)
            self.assertEqual(
                (common / CLI.COMMON_LOCK_INFLIGHT_NAME).read_bytes(),
                fence_bytes,
            )
            self.assertEqual(
                (common / CLI.COMMON_LOCK_INFLIGHT_NAME).stat().st_ino,
                fence_inode,
            )
            self.assertFalse(reservation_path.exists())

            classified: list[dict[str, object]] = []

            def classify(
                reservation: CLI.RecoveryReservation,
                observed_fence: CLI.PublishedLockRecord | None,
            ) -> None:
                self.assertTrue(reservation_path.is_file())
                reservation.assert_current("fixture lifecycle classification")
                self.assertTrue(reservation.matches_chain(CHAIN_ID))
                self.assertEqual(
                    (common / CLI.COMMON_LOCK_INFLIGHT_NAME).read_bytes(),
                    fence_bytes,
                )
                self.assertEqual(
                    (common / CLI.COMMON_LOCK_INFLIGHT_NAME).stat().st_ino,
                    fence_inode,
                )
                self.assertIsNotNone(observed_fence)
                assert observed_fence is not None
                self.assertEqual(observed_fence.inode, fence_inode)
                self.assertEqual(observed_fence.digest, fence_digest)
                self.assertEqual(observed_fence.record, fence_record)
                record = reservation.record
                self.assertEqual(
                    record["recovery_kind"], "fallback-owner-and-fence"
                )
                self.assertEqual(record["stale_owner_inode"], intent_inode)
                self.assertEqual(record["stale_owner_digest"], intent_digest)
                self.assertEqual(record["inflight_inode"], fence_inode)
                self.assertEqual(record["inflight_digest"], fence_digest)
                self.assertEqual(
                    record["group_dead_at"], record["owner_dead_at"]
                )
                classified.append(record)

            boundaries: list[str] = []
            recovered = CLI.acquire_common_lock(
                common,
                owner_kind="merge",
                chain_id=CHAIN_ID,
                operation="recover",
                use_flock=False,
                timeout=2,
                pid_probe=lambda _pid: "dead",
                group_probe=lambda _pgid: "dead",
                no_transaction_record=True,
                recovery_classifier=classify,
                boundary=boundaries.append,
            )
            try:
                self.assertEqual(len(classified), 1)
                self.assertFalse(
                    (common / CLI.COMMON_LOCK_INFLIGHT_NAME).exists()
                )
                self.assertFalse(reservation_path.exists())
                self.assertLess(
                    boundaries.index("recovery-reservation-published"),
                    boundaries.index("recovery-fence-lifecycle-classified"),
                )
                self.assertLess(
                    boundaries.index("recovery-fence-lifecycle-classified"),
                    boundaries.index("recovery-fence-cleared"),
                )
            finally:
                recovered.release()


class WrapperAndDormancyTests(unittest.TestCase):
    def test_wrapper_holds_one_process_and_emits_one_final_v2_envelope(self) -> None:
        owners = (
            ("phase5", None, "phase5-scan"),
            ("merge", CHAIN_ID, "finalize"),
            ("push", None, "push"),
        )
        for owner_kind, chain_id, operation in owners:
            with self.subTest(owner_kind=owner_kind), tempfile.TemporaryDirectory() as temporary:
                repository = Path(temporary)
                init_repo(repository)
                common = Path(
                    os.fsdecode(
                        git(
                            "rev-parse",
                            "--path-format=absolute",
                            "--git-common-dir",
                            cwd=repository,
                        ).strip()
                    )
                )
                ready_read, ready_write = os.pipe()
                environment = os.environ.copy()
                environment.pop("FORGE_SESSION_PID", None)
                arguments = [
                    sys.executable,
                    str(CLI_PATH),
                    "--json",
                    "--repo",
                    str(repository),
                ]
                if chain_id is not None:
                    arguments.extend(["--chain-id", chain_id])
                arguments.extend(
                    [
                    "common-lock",
                    "hold",
                    "--owner-kind",
                    owner_kind,
                    "--operation",
                    operation,
                    "--ready-fd",
                    str(ready_write),
                    ]
                )
                process = subprocess.Popen(
                    arguments,
                    cwd=repository,
                    env=environment,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    pass_fds=(ready_write,),
                )
                os.close(ready_write)
                with os.fdopen(ready_read, "rb", closefd=True) as ready_stream:
                    ready = json.loads(ready_stream.readline())
                self.assertEqual(
                    set(ready), {"schema", "owner_digest", "nonce", "pid"}
                )
                self.assertEqual(ready["schema"], "forge-common-lock-ready/1")
                self.assertEqual(CLI.inspect_common_lock(common).topology, "complete")
                stdout, stderr = process.communicate(b"release\n", timeout=5)
                self.assertEqual(
                    process.returncode,
                    0,
                    stderr.decode("utf-8", "replace"),
                )
                self.assertEqual(stderr, b"")
                self.assertEqual(stdout.count(b"\n"), 1)
                envelope = json.loads(stdout)
                self.assertEqual(envelope["schema"], "forge-cli/2")
                self.assertEqual(envelope["reason_code"], "ok")
                self.assertEqual(
                    envelope["message"], "forge: common rebase lock released"
                )
                self.assertEqual(CLI.inspect_common_lock(common).topology, "free")

    def test_existing_status_does_not_reach_any_new_lock_control(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            init_repo(repository)
            stdout = io.StringIO()
            stderr = io.StringIO()
            with mock.patch.object(
                CLI,
                "acquire_common_lock",
                side_effect=AssertionError("dormant lock was reached"),
            ), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exit_code = CLI.main(
                    ["--json", "--repo", str(repository), "status"]
                )
            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr.getvalue(), "")
            envelope = json.loads(stdout.getvalue())
            self.assertEqual(envelope["schema"], "forge-cli/1")
            self.assertEqual(envelope["message"], "no commit chain exists for this worktree")

            stdout = io.StringIO()
            with mock.patch.object(
                CLI,
                "acquire_common_lock",
                side_effect=AssertionError("dormant lock was reached"),
            ), contextlib.redirect_stdout(stdout):
                exit_code = CLI.main(
                    [
                        "--json",
                        "--repo",
                        str(repository),
                        "commit",
                        "finalize",
                        "--message",
                        "common-lock",
                    ]
                )
            self.assertEqual(exit_code, 1)
            self.assertEqual(json.loads(stdout.getvalue())["schema"], "forge-cli/1")

    def test_each_new_control_is_independently_fail_closed_in_memory(self) -> None:
        for control in sorted(CLI._REQUIRED_COMMON_LOCK_CONTROLS):
            with self.subTest(control=control), mock.patch.object(
                CLI,
                "COMMON_LOCK_CONTROLS",
                CLI._REQUIRED_COMMON_LOCK_CONTROLS - {control},
            ), self.assertRaises(CLI.FrozenError):
                CLI._require_common_lock_control(control)


if __name__ == "__main__":
    unittest.main()
