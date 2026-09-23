from __future__ import annotations

import json
import os
import socket
import unittest
from unittest import mock

from tests._revision8_constants import RECORDED_AT
from tests._revision8_support import Revision8Support

from codex_orchestrator import journal


class Revision8InterruptionsTests(Revision8Support, unittest.TestCase):

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
