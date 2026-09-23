from __future__ import annotations
import json
import os
import socket
import subprocess
import sys
import time
import unittest
from unittest import mock

from tests._revision8_constants import RECORDED_AT, ROOT, TOOLS
from tests._revision8_support import Revision8Support

sys.path.insert(0, str(ROOT / "scripts"))
from codex_orchestrator import journal  # noqa: E402




class Revision8CoordinationTests(Revision8Support, unittest.TestCase):
    """Revision-8 append, orphan, identity, and successor-DAG contracts."""

    def test_postsyscall_baseexception_restores_registry_and_owner_begin_paths(
        self,
    ) -> None:
        class InjectedInterruption(BaseException):
            pass

        self.runs_root.mkdir(parents=True)
        self.prime_registry_lock()
        absent_before = self.coordination_snapshot()
        real_link = journal.os.link
        absent_linked = False

        def interrupt_absent_registry_link(
            source: object,
            destination: object,
            *,
            src_dir_fd: int | None = None,
            dst_dir_fd: int | None = None,
            follow_symlinks: bool = True,
        ) -> None:
            nonlocal absent_linked
            real_link(
                source,
                destination,
                src_dir_fd=src_dir_fd,
                dst_dir_fd=dst_dir_fd,
                follow_symlinks=follow_symlinks,
            )
            if (
                not absent_linked
                and os.fspath(source).endswith(".candidate")
                and os.fspath(destination) == "run-registry.json"
            ):
                absent_linked = True
                raise InjectedInterruption()

        with self.api_environment(), mock.patch.object(
            journal.os,
            "link",
            side_effect=interrupt_absent_registry_link,
        ):
            with self.assertRaises(journal.CoordinationRefusal) as absent_caught:
                journal.open_run(
                    self.repo,
                    "run-interrupted-absent",
                    ["src/interrupted/absent/**"],
                    self.opening_record("run-interrupted-absent"),
                )

        self.assertTrue(absent_linked)
        self.assertEqual(str(absent_caught.exception), journal.REGISTRY_UPDATE_FAILED)
        self.assertEqual(self.coordination_snapshot(), absent_before)
        self.assertFalse(self.registry_path.exists())

        primed = self.open_run("run-interrupted-prime", "src/interrupted/**")
        self.assertEqual(primed.returncode, 0, primed.stderr)
        self.prime_batch_lock("run-interrupted-prime")
        before_existing = self.coordination_snapshot()
        real_exchange = journal._exchange_names_at
        registry_exchanged = False

        def interrupt_registry_exchange(
            directory_descriptor: int,
            first_name: str,
            second_name: str,
        ) -> None:
            nonlocal registry_exchanged
            real_exchange(directory_descriptor, first_name, second_name)
            if (
                not registry_exchanged
                and first_name.startswith(".run-registry.json.")
                and first_name.endswith(".candidate")
                and second_name == "run-registry.json"
            ):
                registry_exchanged = True
                raise InjectedInterruption()

        with self.api_environment(), mock.patch.object(
            journal,
            "_exchange_names_at",
            side_effect=interrupt_registry_exchange,
        ):
            with self.assertRaises(journal.CoordinationRefusal) as existing_caught:
                journal.readmit_run(
                    self.repo,
                    "run-interrupted-prime",
                    ["src/interrupted/readmitted/**"],
                    replace=True,
                )

        self.assertTrue(registry_exchanged)
        self.assertEqual(
            str(existing_caught.exception), journal.REGISTRY_UPDATE_FAILED
        )
        self.assertEqual(self.coordination_snapshot(), before_existing)

        owner_path = self.run_dir("run-interrupted-prime") / "owner"
        stale_owner = (
            f"pid: {self.proven_dead_pid()}\n"
            f"host: {socket.gethostname()}\n"
            f"started_at: {RECORDED_AT}\n"
        ).encode("utf-8")
        owner_path.write_bytes(stale_owner)
        stale_before = self.coordination_snapshot()
        owner_exchanged = False

        def interrupt_owner_exchange(
            directory_descriptor: int,
            first_name: str,
            second_name: str,
        ) -> None:
            nonlocal owner_exchanged
            real_exchange(directory_descriptor, first_name, second_name)
            if (
                not owner_exchanged
                and first_name.startswith(".owner.")
                and first_name.endswith(".candidate")
                and second_name == "owner"
            ):
                owner_exchanged = True
                raise InjectedInterruption()

        with self.api_environment(), mock.patch.object(
            journal,
            "_exchange_names_at",
            side_effect=interrupt_owner_exchange,
        ):
            with self.assertRaises(InjectedInterruption):
                journal.append_run_record(
                    self.repo,
                    "run-interrupted-prime",
                    self.decision_record(id="interrupted-stale-owner"),
                )

        self.assertTrue(owner_exchanged)
        interrupted_after = dict(stale_before)
        interrupted_after[
            ".codex-orchestrator/runs/run-interrupted-prime/"
            + journal.BATCH_LOCK_NAME
        ] = ("file", b"")
        self.assertEqual(self.coordination_snapshot(), interrupted_after)

        legacy_id = "run-interrupted-missing-owner"
        legacy_dir = self.run_dir(legacy_id)
        legacy_dir.mkdir()
        legacy_journal = self.journal_path(legacy_id)
        legacy_journal.write_text(
            json.dumps(
                {"type": "run_started", "run_id": legacy_id, "goal": "legacy"}
            )
            + "\n",
            encoding="utf-8",
        )
        missing_before = self.coordination_snapshot()
        owner_linked = False

        def interrupt_missing_owner_link(
            source: object,
            destination: object,
            *,
            src_dir_fd: int | None = None,
            dst_dir_fd: int | None = None,
            follow_symlinks: bool = True,
        ) -> None:
            nonlocal owner_linked
            real_link(
                source,
                destination,
                src_dir_fd=src_dir_fd,
                dst_dir_fd=dst_dir_fd,
                follow_symlinks=follow_symlinks,
            )
            if (
                not owner_linked
                and os.fspath(source).startswith(".owner.")
                and os.fspath(source).endswith(".candidate")
                and os.fspath(destination) == "owner"
            ):
                owner_linked = True
                raise InjectedInterruption()

        with self.api_environment(), mock.patch.object(
            journal.os,
            "link",
            side_effect=interrupt_missing_owner_link,
        ):
            with self.assertRaises(InjectedInterruption):
                journal.append_run_record(
                    self.repo,
                    legacy_id,
                    self.decision_record(id="interrupted-missing-owner"),
                )

        self.assertTrue(owner_linked)
        missing_after = dict(missing_before)
        missing_after[
            f".codex-orchestrator/runs/{legacy_id}/"
            + journal.BATCH_LOCK_NAME
        ] = ("file", b"")
        self.assertEqual(self.coordination_snapshot(), missing_after)
        self.assertFalse((legacy_dir / "owner").exists())

    def test_postsyscall_baseexception_during_rollback_retains_coherent_candidate(
        self,
    ) -> None:
        class InjectedInterruption(BaseException):
            pass

        self.runs_root.mkdir(parents=True)
        self.prime_registry_lock()
        real_move = journal._move_name_noreplace_at
        absent_moved = False

        def interrupt_absent_registry_rollback(
            directory_descriptor: int,
            source_name: str,
            destination_name: str,
        ) -> None:
            nonlocal absent_moved
            real_move(directory_descriptor, source_name, destination_name)
            if (
                not absent_moved
                and source_name == "run-registry.json"
                and destination_name.endswith(".rollback")
            ):
                absent_moved = True
                raise InjectedInterruption()

        with self.api_environment(), mock.patch.object(
            journal,
            "_validate_post_registry_publication",
            side_effect=journal.CoordinationRefusal(journal.REGISTRY_UNAVAILABLE),
        ), mock.patch.object(
            journal,
            "_move_name_noreplace_at",
            side_effect=interrupt_absent_registry_rollback,
        ):
            with self.assertRaises(journal.RegistryRestorationRefusal) as absent_caught:
                journal.open_run(
                    self.repo,
                    "run-rollback-interrupted-a",
                    ["src/rollback/a/**"],
                    self.opening_record("run-rollback-interrupted-a"),
                )

        self.assertTrue(absent_moved)
        self.assertEqual(str(absent_caught.exception), journal.JOURNAL_ROLLBACK_FAILED)
        registry = json.loads(self.registry_path.read_bytes())
        self.assertEqual(
            {entry["run_id"] for entry in registry["open_runs"]},
            {"run-rollback-interrupted-a"},
        )
        self.assertTrue(self.journal_path("run-rollback-interrupted-a").is_file())

        before_existing_registry = self.registry_path.read_bytes()
        real_exchange = journal._exchange_names_at
        existing_restored = False

        def interrupt_existing_registry_rollback(
            directory_descriptor: int,
            first_name: str,
            second_name: str,
        ) -> None:
            nonlocal existing_restored
            real_exchange(directory_descriptor, first_name, second_name)
            if (
                not existing_restored
                and first_name.startswith(".run-registry.json.")
                and first_name.endswith(".previous")
                and second_name == "run-registry.json"
            ):
                existing_restored = True
                raise InjectedInterruption()

        with self.api_environment(), mock.patch.object(
            journal,
            "_validate_post_registry_publication",
            side_effect=journal.CoordinationRefusal(journal.REGISTRY_UNAVAILABLE),
        ), mock.patch.object(
            journal,
            "_exchange_names_at",
            side_effect=interrupt_existing_registry_rollback,
        ):
            with self.assertRaises(journal.RegistryRestorationRefusal) as existing_caught:
                journal.open_run(
                    self.repo,
                    "run-rollback-interrupted-b",
                    ["src/rollback/b/**"],
                    self.opening_record("run-rollback-interrupted-b"),
                )

        self.assertTrue(existing_restored)
        self.assertEqual(
            str(existing_caught.exception), journal.JOURNAL_ROLLBACK_FAILED
        )
        registry = json.loads(self.registry_path.read_bytes())
        self.assertEqual(
            {entry["run_id"] for entry in registry["open_runs"]},
            {"run-rollback-interrupted-a", "run-rollback-interrupted-b"},
        )
        self.assertTrue(self.journal_path("run-rollback-interrupted-b").is_file())
        self.assertTrue(
            any(
                path.read_bytes() == before_existing_registry
                for path in self.registry_path.parent.glob(
                    ".run-registry.json.*.previous"
                )
            )
        )

        owner_path = self.run_dir("run-rollback-interrupted-a") / "owner"
        owner_path.write_bytes(
            (
                f"pid: {self.proven_dead_pid()}\n"
                f"host: {socket.gethostname()}\n"
                f"started_at: {RECORDED_AT}\n"
            ).encode("utf-8")
        )
        journal_before = self.journal_path("run-rollback-interrupted-a").read_bytes()
        registry_before = self.registry_path.read_bytes()
        owner_restored = False

        def interrupt_owner_rollback(
            directory_descriptor: int,
            first_name: str,
            second_name: str,
        ) -> None:
            nonlocal owner_restored
            real_exchange(directory_descriptor, first_name, second_name)
            if (
                not owner_restored
                and first_name.startswith(".owner.")
                and first_name.endswith(".previous")
                and second_name == "owner"
            ):
                owner_restored = True
                raise InjectedInterruption()

        append_failure = journal.CoordinationRefusal(journal.REGISTRY_UNAVAILABLE)
        with self.api_environment(), mock.patch.object(
            journal,
            "_append_with_locked_stream",
            side_effect=append_failure,
        ), mock.patch.object(
            journal,
            "_exchange_names_at",
            side_effect=interrupt_owner_rollback,
        ):
            with self.assertRaises(journal.OwnerRestorationRefusal) as owner_caught:
                journal.append_run_record(
                    self.repo,
                    "run-rollback-interrupted-a",
                    self.decision_record(id="interrupted-owner-rollback"),
                )

        self.assertTrue(owner_restored)
        self.assertEqual(str(owner_caught.exception), journal.JOURNAL_ROLLBACK_FAILED)
        self.assertTrue(
            owner_path.read_bytes().startswith(
                f"pid: {os.getpid()}\n".encode("utf-8")
            )
        )
        self.assertEqual(
            self.journal_path("run-rollback-interrupted-a").read_bytes(),
            journal_before,
        )
        self.assertEqual(self.registry_path.read_bytes(), registry_before)

        legacy_id = "run-rollback-interrupted-missing"
        legacy_dir = self.run_dir(legacy_id)
        legacy_dir.mkdir()
        legacy_journal = self.journal_path(legacy_id)
        legacy_journal.write_text(
            json.dumps(
                {"type": "run_started", "run_id": legacy_id, "goal": "legacy"}
            )
            + "\n",
            encoding="utf-8",
        )
        legacy_before = legacy_journal.read_bytes()
        missing_moved = False

        def interrupt_missing_owner_rollback(
            directory_descriptor: int,
            source_name: str,
            destination_name: str,
        ) -> None:
            nonlocal missing_moved
            real_move(directory_descriptor, source_name, destination_name)
            if (
                not missing_moved
                and source_name == "owner"
                and destination_name.startswith(".owner.")
                and destination_name.endswith(".rollback")
            ):
                missing_moved = True
                raise InjectedInterruption()

        with self.api_environment(), mock.patch.object(
            journal,
            "_append_with_locked_stream",
            side_effect=append_failure,
        ), mock.patch.object(
            journal,
            "_move_name_noreplace_at",
            side_effect=interrupt_missing_owner_rollback,
        ):
            with self.assertRaises(journal.OwnerRestorationRefusal) as missing_caught:
                journal.append_run_record(
                    self.repo,
                    legacy_id,
                    self.decision_record(id="interrupted-missing-rollback"),
                )

        self.assertTrue(missing_moved)
        self.assertEqual(str(missing_caught.exception), journal.JOURNAL_ROLLBACK_FAILED)
        self.assertTrue(
            (legacy_dir / "owner").read_bytes().startswith(
                f"pid: {os.getpid()}\n".encode("utf-8")
            )
        )
        self.assertEqual(legacy_journal.read_bytes(), legacy_before)
        self.assertEqual(self.registry_path.read_bytes(), registry_before)

    def test_postrestoration_read_and_lock_failures_keep_registry_journal_coherent(
        self,
    ) -> None:
        self.runs_root.mkdir(parents=True)
        self.prime_registry_lock()
        real_move = journal._move_name_noreplace_at
        real_read = journal._read_registry_snapshot
        real_unlink = journal._unlink_if_observed
        absent_restored = False
        absent_failed = False
        cleanup_before_absent_proof: list[str] = []

        def observe_absent_restore(
            directory_descriptor: int,
            source_name: str,
            destination_name: str,
        ) -> None:
            nonlocal absent_restored
            real_move(directory_descriptor, source_name, destination_name)
            if (
                source_name == "run-registry.json"
                and destination_name.endswith(".rollback")
            ):
                absent_restored = True

        def fail_absent_read(*args: object, **kwargs: object):
            nonlocal absent_failed
            if absent_restored and not absent_failed:
                retained = list(
                    self.registry_path.parent.glob(
                        ".run-registry.json.*.rollback"
                    )
                )
                self.assertEqual(len(retained), 1)
                absent_failed = True
                raise OSError("injected restored-registry read failure")
            return real_read(*args, **kwargs)

        def observe_absent_cleanup(
            directory_descriptor: int,
            name: str,
            observation: journal.FileObservation,
        ) -> None:
            if absent_restored and not absent_failed and name.endswith(".rollback"):
                cleanup_before_absent_proof.append(name)
            real_unlink(directory_descriptor, name, observation)

        with self.api_environment(), mock.patch.object(
            journal,
            "_validate_post_registry_publication",
            side_effect=journal.CoordinationRefusal(journal.REGISTRY_UNAVAILABLE),
        ), mock.patch.object(
            journal,
            "_move_name_noreplace_at",
            side_effect=observe_absent_restore,
        ), mock.patch.object(
            journal,
            "_read_registry_snapshot",
            side_effect=fail_absent_read,
        ), mock.patch.object(
            journal,
            "_unlink_if_observed",
            side_effect=observe_absent_cleanup,
        ):
            with self.assertRaises(journal.RegistryRestorationRefusal) as absent_caught:
                journal.open_run(
                    self.repo,
                    "run-proof-absent",
                    ["src/proof/absent/**"],
                    self.opening_record("run-proof-absent"),
                )

        self.assertTrue(absent_restored)
        self.assertTrue(absent_failed)
        self.assertEqual(cleanup_before_absent_proof, [])
        self.assertEqual(str(absent_caught.exception), journal.JOURNAL_ROLLBACK_FAILED)
        registry = json.loads(self.registry_path.read_bytes())
        self.assertEqual(
            {entry["run_id"] for entry in registry["open_runs"]},
            {"run-proof-absent"},
        )
        self.assertTrue(self.journal_path("run-proof-absent").is_file())

        real_exchange = journal._exchange_names_at
        real_validate_lock = journal._validate_registry_lock
        existing_restored = False
        existing_failed = False
        cleanup_before_existing_proof: list[str] = []
        prior_registry = self.registry_path.read_bytes()

        def observe_existing_restore(
            directory_descriptor: int,
            first_name: str,
            second_name: str,
        ) -> None:
            nonlocal existing_restored
            real_exchange(directory_descriptor, first_name, second_name)
            if (
                first_name.startswith(".run-registry.json.")
                and first_name.endswith(".previous")
                and second_name == "run-registry.json"
            ):
                existing_restored = True

        def fail_existing_lock(*args: object, **kwargs: object) -> None:
            nonlocal existing_failed
            if existing_restored and not existing_failed:
                retained = list(
                    self.registry_path.parent.glob(
                        ".run-registry.json.*.previous"
                    )
                )
                self.assertTrue(
                    any(path.read_bytes() != prior_registry for path in retained)
                )
                existing_failed = True
                raise journal.CoordinationRefusal(journal.REGISTRY_LOCK_UNAVAILABLE)
            real_validate_lock(*args, **kwargs)  # type: ignore[arg-type]

        def observe_existing_cleanup(
            directory_descriptor: int,
            name: str,
            observation: journal.FileObservation,
        ) -> None:
            if (
                existing_restored
                and not existing_failed
                and name.endswith(".previous")
            ):
                cleanup_before_existing_proof.append(name)
            real_unlink(directory_descriptor, name, observation)

        with self.api_environment(), mock.patch.object(
            journal,
            "_validate_post_registry_publication",
            side_effect=journal.CoordinationRefusal(journal.REGISTRY_UNAVAILABLE),
        ), mock.patch.object(
            journal,
            "_exchange_names_at",
            side_effect=observe_existing_restore,
        ), mock.patch.object(
            journal,
            "_validate_registry_lock",
            side_effect=fail_existing_lock,
        ), mock.patch.object(
            journal,
            "_unlink_if_observed",
            side_effect=observe_existing_cleanup,
        ):
            with self.assertRaises(journal.RegistryRestorationRefusal) as existing_caught:
                journal.open_run(
                    self.repo,
                    "run-proof-existing",
                    ["src/proof/existing/**"],
                    self.opening_record("run-proof-existing"),
                )

        self.assertTrue(existing_restored)
        self.assertTrue(existing_failed)
        self.assertEqual(cleanup_before_existing_proof, [])
        self.assertEqual(
            str(existing_caught.exception), journal.JOURNAL_ROLLBACK_FAILED
        )
        registry = json.loads(self.registry_path.read_bytes())
        self.assertEqual(
            {entry["run_id"] for entry in registry["open_runs"]},
            {"run-proof-absent", "run-proof-existing"},
        )
        self.assertTrue(self.journal_path("run-proof-existing").is_file())
        self.assertTrue(
            any(
                path.read_bytes() == prior_registry
                for path in self.registry_path.parent.glob(
                    ".run-registry.json.*.previous"
                )
            )
        )

    def test_successor_transfer_control_is_load_bearing(self) -> None:
        self.assertEqual(self.open_run("run-transfer-A", "src/transfer/**").returncode, 0)
        self.assertEqual(self.retire("run-transfer-A").returncode, 0)
        before = self.coordination_snapshot()

        enabled = journal.SUCCESSOR_DAG_CONTROLS
        with self.api_environment(), mock.patch.object(
            journal, "SUCCESSOR_DAG_CONTROLS", enabled - {"transfer"}
        ):
            with self.assertRaises(journal.CoordinationRefusal) as caught:
                journal.open_run(
                    self.repo,
                    "run-transfer-B",
                    ["src/transfer/branch/**"],
                    self.opening_record("run-transfer-B"),
                    successor_of="run-transfer-A",
                )
        self.assertEqual(
            str(caught.exception),
            "forge: successor run refused — predecessor run-transfer-A is not a "
            "scope-reserving retired run",
        )
        self.assertEqual(self.coordination_snapshot(), before)
        self.assertFalse(self.run_dir("run-transfer-B").exists())

    def test_successor_chain_transfers_ancestry_releases_and_readmits(self) -> None:
        self.assertEqual(self.open_run("run-A", "src/ancestor/**").returncode, 0)
        self.assertEqual(self.retire("run-A").returncode, 0)

        opened_b = self.open_run(
            "run-B", "src/ancestor/b/**", successor_of="run-A"
        )
        self.assertEqual(opened_b.returncode, 0, opened_b.stderr)
        second_child = self.open_run(
            "run-A-second", "src/ancestor/second/**", successor_of="run-A"
        )
        self.assertEqual(second_child.returncode, 1)
        self.assertEqual(
            second_child.stderr,
            "forge: successor run refused — predecessor run-A is not a "
            "scope-reserving retired run\n",
        )
        self.assertFalse(self.run_dir("run-A-second").exists())
        self.assertEqual(self.retire("run-B").returncode, 0)

        self.assertEqual(self.open_run("run-U", "src/unrelated/**").returncode, 0)
        self.assertEqual(self.retire("run-U").returncode, 0)

        opened_c = self.open_run(
            "run-C", "src/ancestor/b/c/**", successor_of="run-B"
        )
        self.assertEqual(opened_c.returncode, 0, opened_c.stderr)
        carried = self.open_run("run-carried-probe", "src/ancestor/carried.py")
        self.assertEqual(carried.returncode, 1)
        self.assertEqual(
            carried.stderr,
            "forge: new run refused — scope overlap between run-carried-probe and "
            "open run run-C\n",
        )

        readmitted = self.readmit(
            "run-C", "src/ancestor/readmitted/**", replace=True
        )
        self.assertEqual(readmitted.returncode, 0, readmitted.stderr)
        unrelated = self.readmit(
            "run-C", "src/unrelated/file.py", replace=True
        )
        self.assertEqual(unrelated.returncode, 1)
        self.assertEqual(
            unrelated.stderr,
            "forge: new run refused — scope overlap between run-C and "
            "scope-reserving retired run run-U\n",
        )

        closed = self.command(
            "run-close",
            "--repo",
            str(self.repo),
            "--run-id",
            "run-C",
            "--idempotency-key",
            "2" * 64,
            "--judgment",
            "passed",
            "--summary",
            "Successor ancestry was transferred and released",
        )
        self.assertEqual(closed.returncode, 0, closed.stderr)
        readmitted_after_release = self.open_run(
            "run-after-release", "src/ancestor/new.py"
        )
        self.assertEqual(
            readmitted_after_release.returncode, 0, readmitted_after_release.stderr
        )
        unrelated_still_reserved = self.open_run(
            "run-unrelated-probe", "src/unrelated/new.py"
        )
        self.assertEqual(unrelated_still_reserved.returncode, 1)
        self.assertEqual(
            unrelated_still_reserved.stderr,
            "forge: new run refused — scope overlap between run-unrelated-probe and "
            "scope-reserving retired run run-U\n",
        )

    def test_successor_readmission_may_leave_ancestor_scope_but_keeps_it_reserved(self) -> None:
        self.assertEqual(
            self.open_run("run-readmit-A", "src/ancestor/**").returncode, 0
        )
        self.assertEqual(self.retire("run-readmit-A").returncode, 0)
        successor = self.open_run(
            "run-readmit-B",
            "src/ancestor/initial/**",
            successor_of="run-readmit-A",
        )
        self.assertEqual(successor.returncode, 0, successor.stderr)

        readmitted = self.readmit(
            "run-readmit-B", "src/disjoint/**", replace=True
        )

        self.assertEqual(readmitted.returncode, 0, readmitted.stderr)
        registry = json.loads(self.registry_path.read_text(encoding="utf-8"))
        self.assertEqual(
            registry["open_runs"],
            [{"run_id": "run-readmit-B", "scope": ["src/disjoint/**"]}],
        )
        ancestor_probe = self.open_run(
            "run-readmit-ancestor-probe", "src/ancestor/file.py"
        )
        self.assertEqual(ancestor_probe.returncode, 1)
        self.assertEqual(
            ancestor_probe.stderr,
            "forge: new run refused — scope overlap between "
            "run-readmit-ancestor-probe and open run run-readmit-B\n",
        )
        own_probe = self.open_run(
            "run-readmit-own-probe", "src/disjoint/file.py"
        )
        self.assertEqual(own_probe.returncode, 1)
        self.assertEqual(
            own_probe.stderr,
            "forge: new run refused — scope overlap between run-readmit-own-probe "
            "and open run run-readmit-B\n",
        )

    def test_successor_refusal_literals_for_retired_overlap_and_disjoint_scope(self) -> None:
        self.assertEqual(self.open_run("run-retired-base", "src/base/**").returncode, 0)
        self.assertEqual(self.retire("run-retired-base").returncode, 0)

        ordinary = self.open_run("run-ordinary", "src/base/file.py")
        self.assertEqual(ordinary.returncode, 1)
        self.assertEqual(
            ordinary.stderr,
            "forge: new run refused — scope overlap between run-ordinary and "
            "scope-reserving retired run run-retired-base\n",
        )
        disjoint = self.open_run(
            "run-disjoint", "other/**", successor_of="run-retired-base"
        )
        self.assertEqual(disjoint.returncode, 1)
        self.assertEqual(
            disjoint.stderr,
            "forge: successor run refused — scope of run-disjoint does not overlap "
            "scope-reserving retired run run-retired-base\n",
        )

    def test_persisted_dangling_successor_edge_is_generic_and_nonmutating(self) -> None:
        self.plant_run_state(
            "run-dangling",
            ("src/dangling/**",),
            successor_of="run-missing-predecessor",
        )
        self.write_registry({"run-dangling": ("src/dangling/**",)})
        self.prime_registry_lock()
        before = self.coordination_snapshot()

        refused = self.open_run("run-after-dangling", "other/**")

        self.assertEqual(refused.returncode, 1)
        self.assertEqual(refused.stdout, "")
        self.assertEqual(refused.stderr, journal.REGISTRY_UNAVAILABLE + "\n")
        self.assertEqual(self.coordination_snapshot(), before)
        self.assertFalse(self.run_dir("run-after-dangling").exists())

    def test_persisted_successor_cycle_is_generic_and_nonmutating(self) -> None:
        self.plant_run_state(
            "run-cycle-A",
            ("src/cycle/**",),
            successor_of="run-cycle-B",
            retired=True,
        )
        self.plant_run_state(
            "run-cycle-B",
            ("src/cycle/branch/**",),
            successor_of="run-cycle-A",
            retired=True,
        )
        self.write_registry({})
        self.prime_registry_lock()
        before = self.coordination_snapshot()

        refused = self.open_run("run-after-cycle", "other/**")

        self.assertEqual(refused.returncode, 1)
        self.assertEqual(refused.stdout, "")
        self.assertEqual(refused.stderr, journal.REGISTRY_UNAVAILABLE + "\n")
        self.assertEqual(self.coordination_snapshot(), before)
        self.assertFalse(self.run_dir("run-after-cycle").exists())

    def test_persisted_disjoint_successor_edge_is_generic_and_nonmutating(self) -> None:
        self.plant_run_state("run-edge-A", ("src/a/**",), retired=True)
        self.plant_run_state(
            "run-edge-B",
            ("src/b/**",),
            successor_of="run-edge-A",
        )
        self.write_registry({"run-edge-B": ("src/b/**",)})
        self.prime_registry_lock()
        before = self.coordination_snapshot()

        refused = self.open_run("run-after-disjoint-edge", "other/**")

        self.assertEqual(refused.returncode, 1)
        self.assertEqual(refused.stdout, "")
        self.assertEqual(refused.stderr, journal.REGISTRY_UNAVAILABLE + "\n")
        self.assertEqual(self.coordination_snapshot(), before)
        self.assertFalse(self.run_dir("run-after-disjoint-edge").exists())

    def test_legacy_successor_close_without_valid_judgment_cannot_release_scope(self) -> None:
        self.plant_run_state("run-legacy-release-A", ("src/legacy/**",), retired=True)
        successor_dir = self.run_dir("run-legacy-release-B")
        successor_dir.mkdir()
        opening = self.opening_record(
            "run-legacy-release-B",
            scope=["src/legacy/branch/**"],
            successor_of="run-legacy-release-A",
        )
        opening["id"] = opening.pop("run_id")
        owner = (
            f"pid: {os.getpid()}\n"
            f"host: {socket.gethostname()}\n"
            f"started_at: {RECORDED_AT}\n"
        )
        (successor_dir / "owner").write_text(owner, encoding="utf-8")
        self.write_registry({})
        self.prime_registry_lock()

        for judgment in (None, "unsafe-release"):
            closure: dict[str, object] = {
                "type": "run_closed",
                "recorded_at": RECORDED_AT,
                "summary": "historical closure must not release ancestry",
            }
            if judgment is not None:
                closure["judgment"] = judgment
            self.journal_path("run-legacy-release-B").write_text(
                "".join(
                    json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
                    for record in (opening, closure)
                ),
                encoding="utf-8",
            )
            before = self.coordination_snapshot()

            with self.subTest(judgment=judgment):
                refused = self.open_run(
                    "run-legacy-release-probe", "src/legacy/probe.py"
                )
                self.assertEqual(refused.returncode, 1)
                self.assertEqual(refused.stdout, "")
                self.assertEqual(
                    refused.stderr, journal.REGISTRY_UNAVAILABLE + "\n"
                )
                self.assertEqual(self.coordination_snapshot(), before)
                self.assertFalse(
                    self.run_dir("run-legacy-release-probe").exists()
                )

    def test_mixed_open_and_retired_conflicts_are_byte_sorted(self) -> None:
        self.assertEqual(
            self.open_run("run-z-open", "src/open/**").returncode, 0
        )
        self.assertEqual(
            self.open_run("run-a-retired", "src/retired/**").returncode, 0
        )
        self.assertEqual(self.retire("run-a-retired").returncode, 0)
        before = self.coordination_snapshot()

        refused = self.open_run("run-mixed", "src/**")

        self.assertEqual(refused.returncode, 1)
        self.assertEqual(
            refused.stderr,
            "forge: new run refused — scope overlap between run-mixed and "
            "scope-reserving retired run run-a-retired\n"
            "forge: new run refused — scope overlap between run-mixed and open run "
            "run-z-open\n",
        )
        self.assertEqual(self.coordination_snapshot(), before)
        self.assertFalse(self.run_dir("run-mixed").exists())

    def test_concurrent_successor_and_ordinary_admission_serialize_atomically(self) -> None:
        self.assertEqual(self.open_run("run-race-A", "src/race/**").returncode, 0)
        self.assertEqual(self.retire("run-race-A").returncode, 0)
        successor_record = self.write_record(
            self.opening_record("run-race-successor"), "race-successor"
        )
        ordinary_record = self.write_record(
            self.opening_record("run-race-ordinary"), "race-ordinary"
        )
        ready_successor = self.root / "successor.ready"
        ready_ordinary = self.root / "ordinary.ready"
        gate = self.root / "admission.gate"
        barrier_program = (
            "import os,sys,time\n"
            "from pathlib import Path\n"
            "ready=Path(sys.argv[1]); gate=Path(sys.argv[2])\n"
            "ready.touch()\n"
            "deadline=time.monotonic()+10\n"
            "while not gate.exists():\n"
            "    if time.monotonic()>deadline: raise SystemExit(97)\n"
            "    time.sleep(0.005)\n"
            "os.execv(sys.executable,[sys.executable,*sys.argv[3:]])\n"
        )
        common = ["--repo", str(self.repo)]
        successor_arguments = [
            "run-open",
            *common,
            "--run-id",
            "run-race-successor",
            "--scope",
            "src/race/successor/**",
            "--record-json",
            str(successor_record),
            "--successor-of",
            "run-race-A",
        ]
        ordinary_arguments = [
            "run-open",
            *common,
            "--run-id",
            "run-race-ordinary",
            "--scope",
            "src/race/ordinary/**",
            "--record-json",
            str(ordinary_record),
        ]
        processes = (
            subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    barrier_program,
                    str(ready_successor),
                    str(gate),
                    str(TOOLS),
                    *successor_arguments,
                ],
                cwd=self.repo,
                env=self.env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            ),
            subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    barrier_program,
                    str(ready_ordinary),
                    str(gate),
                    str(TOOLS),
                    *ordinary_arguments,
                ],
                cwd=self.repo,
                env=self.env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            ),
        )
        deadline = time.monotonic() + 10
        while not (ready_successor.exists() and ready_ordinary.exists()):
            if any(process.poll() is not None for process in processes):
                break
            if time.monotonic() >= deadline:
                break
            time.sleep(0.005)
        both_ready = ready_successor.exists() and ready_ordinary.exists()
        gate.touch()
        results: list[tuple[int, str, str]] = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=20)
            results.append((process.returncode, stdout, stderr))

        self.assertTrue(both_ready, results)
        successor_result, ordinary_result = results
        self.assertEqual(successor_result[0], 0, successor_result)
        self.assertEqual(ordinary_result[0], 1, ordinary_result)
        self.assertEqual(ordinary_result[1], "")
        self.assertIn(
            ordinary_result[2],
            {
                "forge: new run refused — scope overlap between run-race-ordinary "
                "and scope-reserving retired run run-race-A\n",
                "forge: new run refused — scope overlap between run-race-ordinary "
                "and open run run-race-successor\n",
            },
        )
        registry = json.loads(self.registry_path.read_text(encoding="utf-8"))
        self.assertEqual(
            registry["open_runs"],
            [
                {
                    "run_id": "run-race-successor",
                    "scope": ["src/race/successor/**"],
                }
            ],
        )
        self.assertFalse(self.run_dir("run-race-ordinary").exists())

    def test_only_a_retired_successor_may_close_and_release_ancestry(self) -> None:
        self.assertEqual(self.open_run("run-leaf", "src/leaf/**").returncode, 0)
        self.assertEqual(self.retire("run-leaf").returncode, 0)
        before = self.coordination_snapshot()

        refused_root = self.close("run-leaf", judgment="blocked")

        self.assertEqual(refused_root.returncode, 1)
        self.assertEqual(
            refused_root.stderr,
            "forge: run close refused — run run-leaf is retired\n",
        )
        self.assertEqual(self.coordination_snapshot(), before)

        successor = self.open_run(
            "run-leaf-successor",
            "src/leaf/successor/**",
            successor_of="run-leaf",
        )
        self.assertEqual(successor.returncode, 0, successor.stderr)
        self.assertEqual(self.retire("run-leaf-successor").returncode, 0)
        closed = self.close("run-leaf-successor", judgment="blocked")
        self.assertEqual(closed.returncode, 0, closed.stderr)
        reused = self.open_run("run-after-leaf", "src/leaf/reused.py")
        self.assertEqual(reused.returncode, 0, reused.stderr)

    def test_close_rollback_preserves_effective_ancestral_reservation(self) -> None:
        self.assertEqual(self.open_run("run-rollback-A", "src/rollback/**").returncode, 0)
        self.assertEqual(self.retire("run-rollback-A").returncode, 0)
        self.assertEqual(
            self.open_run(
                "run-rollback-B",
                "src/rollback/branch/**",
                successor_of="run-rollback-A",
            ).returncode,
            0,
        )
        self.prime_batch_lock("run-rollback-B")
        before = self.coordination_snapshot()

        with self.api_environment(), mock.patch.object(
            journal, "_write_registry", side_effect=OSError("injected update failure")
        ):
            with self.assertRaises(journal.CoordinationRefusal) as caught:
                journal.close_run(
                    self.repo, "run-rollback-B", self.closure_record("passed")
                )
        self.assertEqual(
            str(caught.exception),
            "forge: run coordination refused — run registry update failed",
        )
        self.assertEqual(self.coordination_snapshot(), before)

        probe = self.open_run("run-rollback-probe", "src/rollback/probe.py")
        self.assertEqual(probe.returncode, 1)
        self.assertEqual(
            probe.stderr,
            "forge: new run refused — scope overlap between run-rollback-probe and "
            "open run run-rollback-B\n",
        )

    def test_release_control_disabled_keeps_retired_ancestry_reserved(self) -> None:
        self.assertEqual(self.open_run("run-release-A", "src/release/**").returncode, 0)
        self.assertEqual(self.retire("run-release-A").returncode, 0)
        self.assertEqual(
            self.open_run(
                "run-release-B",
                "src/release/branch/**",
                successor_of="run-release-A",
            ).returncode,
            0,
        )

        enabled = journal.SUCCESSOR_DAG_CONTROLS
        with self.api_environment(), mock.patch.object(
            journal, "SUCCESSOR_DAG_CONTROLS", enabled - {"release"}
        ):
            journal.close_run(
                self.repo, "run-release-B", self.closure_record("passed")
            )
            with self.assertRaises(journal.CoordinationRefusal) as caught:
                journal.open_run(
                    self.repo,
                    "run-release-probe",
                    ["src/release/probe.py"],
                    self.opening_record("run-release-probe"),
                )
        self.assertEqual(
            str(caught.exception),
            "forge: new run refused — scope overlap between run-release-probe and "
            "scope-reserving retired run run-release-B",
        )
        self.assertFalse(self.run_dir("run-release-probe").exists())

    def test_historical_fork_releases_shared_ancestor_only_after_both_branches_close(self) -> None:
        self.assertEqual(self.open_run("run-fork-A", "src/shared/**").returncode, 0)
        self.assertEqual(self.retire("run-fork-A").returncode, 0)
        self.assertEqual(
            self.open_run(
                "run-fork-B", "src/shared/b/**", successor_of="run-fork-A"
            ).returncode,
            0,
        )

        fork_c = self.run_dir("run-fork-C")
        fork_c.mkdir()
        opening_c = self.opening_record("run-fork-C")
        opening_c["scope"] = ["src/shared/c/**"]
        opening_c["successor_of"] = "run-fork-A"
        (fork_c / "journal.jsonl").write_text(
            json.dumps(opening_c, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        (fork_c / "owner").write_text(
            f"pid: {os.getpid()}\nhost: {socket.gethostname()}\n"
            f"started_at: {RECORDED_AT}\n",
            encoding="utf-8",
        )
        self.write_registry(
            {
                "run-fork-B": ("src/shared/b/**",),
                "run-fork-C": ("src/shared/c/**",),
            }
        )

        closed_b = self.close("run-fork-B")
        self.assertEqual(closed_b.returncode, 0, closed_b.stderr)
        still_reserved = self.open_run("run-fork-probe", "src/shared/probe.py")
        self.assertEqual(still_reserved.returncode, 1)
        self.assertEqual(
            still_reserved.stderr,
            "forge: new run refused — scope overlap between run-fork-probe and "
            "open run run-fork-C\n",
        )

        closed_c = self.close("run-fork-C")
        self.assertEqual(closed_c.returncode, 0, closed_c.stderr)
        released = self.open_run("run-fork-probe", "src/shared/probe.py")
        self.assertEqual(released.returncode, 0, released.stderr)


if __name__ == "__main__":
    unittest.main()
