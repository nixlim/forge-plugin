from __future__ import annotations

import json
import subprocess
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from tests._revision9_coord_constants import ROOT, key
from tests._revision9_coord_support import Revision9BuilderBatchSupport

from codex_orchestrator import batch, builders, journal


class Revision9ScopeChangeTests(Revision9BuilderBatchSupport, unittest.TestCase):

    def test_activated_scope_readmission_uses_typed_builder(self) -> None:
        run_id = "run-20260831-activated-readmit"
        with self.api_environment():
            self.open_run(self.repo, run_id)
            with self.assertRaisesRegex(
                journal.CoordinationRefusal,
                "activated writer requires typed builder",
            ):
                journal.readmit_run(self.repo, run_id, ["src/**"])

            readmission = builders.scope_change(
                self.repo,
                run_id,
                idempotency_key=key("activated-readmit-api"),
                scope=["src/**", "tests/**"],
            )
            self.assertIsInstance(readmission, batch.BatchOutcome)
            self.assertFalse(readmission.repeated)
            repeated = builders.scope_change(
                self.repo,
                run_id,
                idempotency_key=key("activated-readmit-api"),
                scope=["src/**", "tests/**"],
            )
            self.assertIsInstance(repeated, batch.BatchOutcome)
            self.assertTrue(repeated.repeated)
            with self.assertRaisesRegex(
                journal.CoordinationRefusal,
                "idempotency key already names different content",
            ):
                builders.scope_change(
                    self.repo,
                    run_id,
                    idempotency_key=key("activated-readmit-api"),
                    scope=["docs/**", "src/**", "tests/**"],
                )
            state = journal._scan_run(self.run_dir(self.repo, run_id))
            self.assertEqual(state.scope, ("src/**", "tests/**"))
            self.assertEqual(
                state.records[-1]["resolution"], journal.READMISSION_RESOLUTION
            )

            public = self.command(
                "run-readmit",
                "--repo",
                str(self.repo),
                "--run-id",
                run_id,
                "--idempotency-key",
                key("activated-readmit-cli"),
                "--scope",
                "docs/**",
                "--scope",
                "src/**",
                "--scope",
                "tests/**",
            )
            self.assertEqual(public.returncode, 0, public.stderr)
            state = journal._scan_run(self.run_dir(self.repo, run_id))
            self.assertEqual(state.scope, ("docs/**", "src/**", "tests/**"))

            before = (self.run_dir(self.repo, run_id) / "journal.jsonl").read_bytes()
            with mock.patch.object(
                builders,
                "BUILDER_VALIDATION_CONTROLS",
                builders.BUILDER_VALIDATION_CONTROLS - {"scope-change"},
            ), self.assertRaisesRegex(
                journal.CoordinationRefusal, "scope-change control is unavailable"
            ):
                builders.scope_change(
                    self.repo,
                    run_id,
                    idempotency_key=key("activated-readmit-disabled"),
                    scope=["docs/**", "src/**", "tests/**", "tools/**"],
                )
            self.assertEqual(
                (self.run_dir(self.repo, run_id) / "journal.jsonl").read_bytes(),
                before,
            )

    def test_readmit_sequence_keeps_receipts_contiguous_and_appends_resume(self) -> None:
        run_id = "run-20260831-readmit-receipts"
        with self.api_environment():
            self.open_run(self.repo, run_id)
            builders.task_start(
                self.repo,
                run_id,
                idempotency_key=key("readmit-sequence-task-1"),
                task="task-01",
                goal="Establish the initial admitted task",
                acceptance=["The task is receipted"],
                files=["src/example.py"],
            )
            readmitted = self.command(
                "run-readmit",
                "--repo",
                str(self.repo),
                "--run-id",
                run_id,
                "--idempotency-key",
                key("readmit-sequence-scope"),
                "--scope",
                "src/**",
                "--scope",
                "tests/**",
            )
            self.assertEqual(readmitted.returncode, 0, readmitted.stderr)
            self.assertEqual(
                json.loads(readmitted.stdout)["records"][0]["resolution"],
                journal.READMISSION_RESOLUTION,
            )
            builders.task_start(
                self.repo,
                run_id,
                idempotency_key=key("readmit-sequence-task-2"),
                task="task-02",
                goal="Use the widened scope",
                acceptance=["The second task is receipted"],
                files=["tests/test_example.py"],
            )

            run_dir = self.run_dir(self.repo, run_id)
            records, issues = journal.read_journal(
                run_dir / "journal.jsonl"
            )
            self.assertEqual(issues, [])
            self.assertEqual(
                [record["type"] for record in records],
                ["run_started", "task", "decision", "task"],
            )
            builders.task_start(
                self.repo,
                run_id,
                idempotency_key=key("readmit-sequence-task-3"),
                task="task-03",
                goal="Prove appends continue",
                acceptance=["A later append succeeds"],
                files=["tests/test_later.py"],
            )

        receipts = [
            json.loads(line)
            for line in (
                run_dir / journal.BATCH_RECEIPTS_NAME
            ).read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(len(receipts), 5)
        self.assertTrue(
            all(
                current["base_size"] == previous["journal_size"]
                for previous, current in zip(receipts, receipts[1:])
            )
        )
        self.assertFalse((run_dir / journal.BATCH_INTENT_NAME).exists())

    def test_scope_change_recovers_intent_and_receipted_registry_publication(self) -> None:
        for crash_point in ("intent", "registry"):
            with self.subTest(crash_point=crash_point):
                repo, _ = self._new_repo(f"repo-readmit-{crash_point}")
                run_id = f"run-20260831-readmit-{crash_point}"
                transaction_key = key(f"readmit-{crash_point}")
                with self.api_environment():
                    self.open_run(repo, run_id)
                    if crash_point == "intent":
                        with mock.patch.object(
                            batch,
                            "_recover_locked",
                            side_effect=RuntimeError("crash after intent"),
                        ), self.assertRaisesRegex(
                            RuntimeError, "crash after intent"
                        ):
                            builders.scope_change(
                                repo,
                                run_id,
                                idempotency_key=transaction_key,
                                scope=["src/**", "tests/**"],
                            )
                        run_dir = self.run_dir(repo, run_id)
                        self.assertTrue(
                            (run_dir / journal.BATCH_INTENT_NAME).is_file()
                        )
                        original_registry_lock = journal._registry_lock
                        registry_epochs = 0

                        @contextmanager
                        def counted_registry_lock(state_root: Path):
                            nonlocal registry_epochs
                            registry_epochs += 1
                            with original_registry_lock(state_root) as locked:
                                yield locked

                        with mock.patch.object(
                            journal,
                            "_registry_lock",
                            side_effect=counted_registry_lock,
                        ):
                            recovered = batch.recover_batch(repo, run_id)
                        self.assertEqual(registry_epochs, 1)
                    else:
                        with mock.patch.object(
                            journal,
                            "_write_registry",
                            side_effect=journal.CoordinationRefusal(
                                journal.REGISTRY_UPDATE_FAILED
                            ),
                        ), self.assertRaisesRegex(
                            journal.CoordinationRefusal,
                            journal.REGISTRY_UPDATE_FAILED,
                        ):
                            builders.scope_change(
                                repo,
                                run_id,
                                idempotency_key=transaction_key,
                                scope=["src/**", "tests/**"],
                            )
                        run_dir = self.run_dir(repo, run_id)
                        self.assertFalse(
                            (run_dir / journal.BATCH_INTENT_NAME).exists()
                        )
                        recovered = builders.scope_change(
                            repo,
                            run_id,
                            idempotency_key=transaction_key,
                            scope=["src/**", "tests/**"],
                        )
                    self.assertTrue(recovered.repeated)
                    self.assertFalse(
                        (run_dir / journal.BATCH_INTENT_NAME).exists()
                    )
                    state = journal._scan_run(run_dir)
                    self.assertEqual(state.scope, ("src/**", "tests/**"))
                    receipts = [
                        json.loads(line)
                        for line in (
                            run_dir / journal.BATCH_RECEIPTS_NAME
                        ).read_text(encoding="utf-8").splitlines()
                    ]
                    self.assertEqual(len(receipts), 2)

    def test_scope_change_recovery_refuses_unproved_replace_and_disabled_control(self) -> None:
        for scenario in ("unproved-replace", "disabled-control"):
            with self.subTest(scenario=scenario):
                repo, _ = self._new_repo(f"repo-readmit-{scenario}")
                run_id = f"run-20260831-readmit-{scenario}"
                transaction_key = key(f"readmit-{scenario}")
                with self.api_environment():
                    builders.run_open(
                        repo,
                        run_id,
                        idempotency_key=key(f"{scenario}-open"),
                        goal="Exercise guarded readmission recovery",
                        scope=["src/**", "tests/**"],
                        plugin_ref="forge-test-revision-9",
                    )
                    with mock.patch.object(
                        batch,
                        "_recover_locked",
                        side_effect=RuntimeError("crash after intent"),
                    ), self.assertRaisesRegex(RuntimeError, "crash after intent"):
                        builders.scope_change(
                            repo,
                            run_id,
                            idempotency_key=transaction_key,
                            scope=(
                                ["src/**"]
                                if scenario == "unproved-replace"
                                else ["src/**", "tests/**", "tools/**"]
                            ),
                            replace=scenario == "unproved-replace",
                        )
                    run_dir = self.run_dir(repo, run_id)
                    if scenario == "unproved-replace":
                        current = journal._session_owner()
                        (run_dir / "owner").write_bytes(
                            journal._owner_bytes(
                                journal.Owner(
                                    pid=99999999,
                                    host=current.host,
                                    started_at="2026-08-31T00:00:00Z",
                                )
                            )
                        )
                    before = {
                        path.name: path.read_bytes()
                        for path in run_dir.iterdir()
                        if path.is_file()
                    }
                    controls = (
                        batch.SCOPE_CHANGE_TRANSACTION_CONTROLS
                        if scenario == "unproved-replace"
                        else frozenset()
                    )
                    expected = (
                        "proposed scope omits current pathspecs"
                        if scenario == "unproved-replace"
                        else journal.BATCH_DIVERGED
                    )
                    with mock.patch.object(
                        batch,
                        "SCOPE_CHANGE_TRANSACTION_CONTROLS",
                        controls,
                    ), self.assertRaisesRegex(
                        journal.CoordinationRefusal, expected
                    ):
                        batch.recover_batch(repo, run_id)
                    after = {
                        path.name: path.read_bytes()
                        for path in run_dir.iterdir()
                        if path.is_file()
                    }
                    self.assertEqual(after, before)

                    recovered = builders.scope_change(
                        repo,
                        run_id,
                        idempotency_key=transaction_key,
                        scope=(
                            ["src/**"]
                            if scenario == "unproved-replace"
                            else ["src/**", "tests/**", "tools/**"]
                        ),
                        replace=scenario == "unproved-replace",
                    )
                    self.assertTrue(recovered.repeated)
                    self.assertFalse(
                        (run_dir / journal.BATCH_INTENT_NAME).exists()
                    )

    def test_activated_scope_change_rechecks_superset_containment_and_conflicts(self) -> None:
        run_id = "run-20260831-readmit-predicates"
        other_id = "run-20260831-readmit-conflict"
        with self.api_environment():
            builders.run_open(
                self.repo,
                run_id,
                idempotency_key=key("readmit-predicates-open"),
                goal="Exercise every locked readmission predicate",
                scope=["src/**", "tests/**"],
                plugin_ref="forge-test-revision-9",
            )
            builders.task_start(
                self.repo,
                run_id,
                idempotency_key=key("readmit-predicates-task"),
                task="task-01",
                goal="Pin a contained task",
                acceptance=["Readmission retains this file"],
                files=["src/example.py"],
            )
            builders.run_open(
                self.repo,
                other_id,
                idempotency_key=key("readmit-conflict-open"),
                goal="Reserve a conflicting scope",
                scope=["docs/**"],
                plugin_ref="forge-test-revision-9",
            )
            run_dir = self.run_dir(self.repo, run_id)

            cases = (
                (
                    "omitted-current",
                    ["src/**"],
                    False,
                    '"tests/**"',
                ),
                (
                    "task-containment",
                    ["tests/**"],
                    True,
                    '"src/example.py"',
                ),
                (
                    "other-run-conflict",
                    ["docs/**", "src/**", "tests/**"],
                    False,
                    other_id,
                ),
            )
            for label, scope, replace, expected in cases:
                with self.subTest(label=label):
                    before = {
                        path.name: path.read_bytes()
                        for path in run_dir.iterdir()
                        if path.is_file()
                    }
                    with self.assertRaises(
                        journal.CoordinationRefusal
                    ) as caught:
                        builders.scope_change(
                            self.repo,
                            run_id,
                            idempotency_key=key(f"readmit-{label}"),
                            scope=scope,
                            replace=replace,
                        )
                    self.assertIn(expected, str(caught.exception))
                    after = {
                        path.name: path.read_bytes()
                        for path in run_dir.iterdir()
                        if path.is_file()
                    }
                    self.assertEqual(after, before)

    def test_concurrent_admission_and_scope_change_remain_disjoint(self) -> None:
        target = "run-20260831-readmit-race-target"
        contender = "run-20260831-readmit-race-contender"
        with self.api_environment():
            self.open_run(self.repo, target)
            current = journal._session_owner()
            (self.run_dir(self.repo, target) / "owner").write_bytes(
                journal._owner_bytes(
                    journal.Owner(
                        pid=99999999,
                        host=current.host,
                        started_at="2026-08-31T00:00:00Z",
                    )
                )
            )

        barrier_dir = Path(self.temporary.name) / "readmit-race-barrier"
        barrier_dir.mkdir()
        program = r'''
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from codex_orchestrator import builders, journal

mode, repository, barrier = sys.argv[2:]
repository = Path(repository)
barrier = Path(barrier)
os.environ["FORGE_SESSION_PID"] = str(os.getpid())
original = journal._registry_lock
first = True

@contextmanager
def synchronized_registry_lock(state_root):
    global first
    if first:
        first = False
        (barrier / mode).write_text("ready\n", encoding="utf-8")
        deadline = time.monotonic() + 10.0
        while len(tuple(barrier.iterdir())) < 2:
            if time.monotonic() >= deadline:
                raise RuntimeError("barrier timeout")
            time.sleep(0.01)
    with original(state_root) as locked:
        yield locked

journal._registry_lock = synchronized_registry_lock
try:
    if mode == "readmit":
        builders.scope_change(
            repository,
            "run-20260831-readmit-race-target",
            idempotency_key="1" * 64,
            scope=["src/**", "tests/**"],
        )
    else:
        builders.run_open(
            repository,
            "run-20260831-readmit-race-contender",
            idempotency_key="2" * 64,
            goal="Race the locked scope change",
            scope=["tests/**"],
            plugin_ref="forge-test-revision-9",
        )
except journal.CoordinationRefusal as exc:
    print(str(exc))
    raise SystemExit(1)
print("committed")
'''
        processes = [
            subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    program,
                    str(ROOT / "scripts"),
                    mode,
                    str(self.repo),
                    str(barrier_dir),
                ],
                cwd=self.repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            for mode in ("readmit", "admit")
        ]
        results: list[tuple[int, str, str]] = []
        try:
            for process in processes:
                stdout, stderr = process.communicate(timeout=20)
                results.append((process.returncode, stdout, stderr))
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)

        self.assertEqual(
            sorted(result[0] for result in results), [0, 1], results
        )
        refusal = next(result[1] for result in results if result[0] == 1)
        self.assertIn("scope overlap", refusal)
        registry = json.loads(
            (self.repo / ".forge/tmp/run-registry.json").read_text(
                encoding="utf-8"
            )
        )
        scopes = {
            entry["run_id"]: tuple(entry["scope"])
            for entry in registry["open_runs"]
        }
        if contender in scopes:
            self.assertEqual(scopes[target], ("src/**",))
            self.assertEqual(scopes[contender], ("tests/**",))
        else:
            self.assertEqual(scopes[target], ("src/**", "tests/**"))
        with batch.batch_lock(
            self.run_dir(self.repo, target), create=False
        ) as locked:
            batch._load_receipts(locked)
