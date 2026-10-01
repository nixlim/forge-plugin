from __future__ import annotations

import copy
import fcntl
import hashlib
import io
import json
import os
import stat
import subprocess
import sys
import time
import unittest
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from unittest import mock

from tests._revision9_coord_constants import key
from tests._revision9_coord_support import Revision9BuilderBatchSupport

from codex_orchestrator import batch, builders, close_law, close_preflight, journal


class ClosePreflightTests(Revision9BuilderBatchSupport, unittest.TestCase):
    def _repository(self, name: str) -> tuple[Path, str]:
        return self._new_repo(f"close-preflight-{name}")

    def _terminal_run(
        self,
        name: str,
        *,
        provenance: bool = True,
    ) -> tuple[Path, str, Path]:
        repo, _head = self._repository(name)
        run_id = f"run-20260930-preflight-{name}"
        self.open_run(repo, run_id)
        self.start_task(repo, run_id)
        if provenance:
            builders.decision_add(
                repo,
                run_id,
                idempotency_key=key(f"{name}-provenance"),
                task="task-01",
                resolution="orchestrator-owned: close preflight fixture",
                finding=None,
                outcome=None,
                risk=None,
                basis=["synthetic close-preflight fixture"],
                binding_chain=None,
                binding_id=None,
            )
        finish_context = (
            mock.patch.object(
                journal.route_provenance,
                "enforce_task_finish",
                return_value=None,
            )
            if not provenance
            else mock.patch.object(
                builders, "_terminal_chain_guard", wraps=builders._terminal_chain_guard
            )
        )
        with finish_context:
            builders.task_finish(
                repo,
                run_id,
                idempotency_key=key(f"{name}-finish"),
                task="task-01",
                status="complete",
            )
        return repo, run_id, self.run_dir(repo, run_id)

    @staticmethod
    def _binding(
        chain_id: str, seed: str, *, reviewed: bool = False
    ) -> dict[str, object]:
        review = (
            {
                "verdict": "PASS",
                "iteration": 1,
                "reviewer_role": "review-final",
                "package_digest": key(f"{seed}-review-package"),
            }
            if reviewed
            else None
        )
        preimage = {
            "schema": journal.BINDING_SCHEMA,
            "source_record": {
                "chain_id": chain_id,
                "event_digest": key(f"{seed}-event"),
            },
            "candidate": {
                "kind": "staged-diff-sha256",
                "value": key("close-preflight-candidate"),
            },
            "review": review,
        }
        return {
            **preimage,
            "binding_id": journal._sha256(journal._canonical_json_bytes(preimage)),
        }

    def _bound_verification(
        self,
        repo: Path,
        run_id: str,
        chain_id: str,
        criterion: str,
        seed: str,
    ) -> None:
        binding = self._binding(
            chain_id,
            seed,
            reviewed=criterion == journal.GATE_3_CRITERION,
        )
        with mock.patch.object(builders, "resolve_binding", return_value=binding):
            builders.verification_add(
                repo,
                run_id,
                idempotency_key=key(f"{run_id}-{seed}"),
                task="task-01",
                criterion=criterion,
                method="unittest",
                check="python3 -m unittest synthetic",
                result="passed",
                observation="synthetic bound gate passed",
                evidence=[],
                binding_chain=chain_id,
                binding_id=str(binding["binding_id"]),
            )

    def _bound_landing(
        self, repo: Path, run_id: str, chain_id: str, seed: str
    ) -> None:
        binding = self._binding(chain_id, seed)
        with mock.patch.object(builders, "resolve_binding", return_value=binding):
            builders.decision_add(
                repo,
                run_id,
                idempotency_key=key(f"{run_id}-{seed}"),
                task="task-01",
                resolution="The synthetic candidate landed",
                finding=None,
                outcome="chain-landing",
                risk=None,
                basis=[],
                binding_chain=chain_id,
                binding_id=str(binding["binding_id"]),
            )

    def _missing_gate_three_run(
        self, name: str
    ) -> tuple[Path, str, Path]:
        from tests import test_run_bound_gate_one as gate_fixture

        fixture = gate_fixture.RunBoundGateOneTests(
            "test_verify_executes_and_drains_bound_gate_one"
        )
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        repo = fixture.repo
        run_id = f"run-20260930-preflight-{name}"
        chain_id = fixture._start_bound_docs_chain(run_id)
        run_dir = self.run_dir(repo, run_id)
        for relative in ("prompt.md", "events.jsonl", "handoff.md"):
            (run_dir / relative).write_text("fixture evidence\n", encoding="utf-8")
        route = fixture._run_records(run_id)[0]["route"]["implementer"]
        with fixture.cli_process_context():
            builders.execution_start(
                repo,
                run_id,
                idempotency_key=key(f"{name}-execution"),
                agent="codex-impl-01",
                task="task-01",
                provider=route["provider"],
                role="implementer",
                mode="headless",
                model=route["model"],
                effort=route["effort"],
                worktree=str(repo.resolve()),
                head=fixture.git("rev-parse", "HEAD"),
                prompt="prompt.md",
                handoff="handoff.md",
                event_source="exec",
                events="events.jsonl",
                sandbox="workspace-write",
                route_source=route["route_source"],
                route_sha256=route["route_sha256"],
            )
            builders.execution_result(
                repo,
                run_id,
                idempotency_key=key(f"{name}-result"),
                execution="execution-01",
                agent="codex-impl-01",
                task="task-01",
                status="complete",
                summary="Synthetic implementation completed",
                files_changed=["docs/guide.md"],
                caveats=[],
                handoff="handoff.md",
            )
        exit_code, verified = fixture.invoke_cli(
            "--chain-id", chain_id, "verify"
        )
        self.assertEqual(exit_code, 0, verified)
        self.assertEqual(verified["state"], "authorized")
        exit_code, finalized = fixture.invoke_cli(
            "--chain-id",
            chain_id,
            "commit",
            "finalize",
            "--message",
            "Land missing Gate-3 fixture",
        )
        self.assertEqual(exit_code, 0, finalized)
        self.assertEqual(finalized["state"], "closed")
        with fixture.cli_process_context():
            builders.decision_add(
                repo,
                run_id,
                idempotency_key=key(f"{name}-provenance"),
                task="task-01",
                resolution="orchestrator-owned: close preflight fixture",
                finding=None,
                outcome=None,
                risk=None,
                basis=["synthetic close-preflight fixture"],
                binding_chain=None,
                binding_id=None,
            )
            builders.task_finish(
                repo,
                run_id,
                idempotency_key=key(f"{name}-finish"),
                task="task-01",
                status="complete",
            )
        return repo, run_id, run_dir

    def _nonterminal_chain_run(
        self, name: str, *, pending: bool = False
    ) -> tuple[Path, str, Path, str]:
        repo, run_id, run_dir = self._terminal_run(name)
        run_binding = {
            "run_id": run_id,
            "task_id": "task-01",
            "repository": str(repo.resolve()),
            "policy_digest": key(f"{name}-policy"),
        }
        chain_id = f"c-2026-09-30T12{len(name):02d}00Z-b101"
        self._write_bound_chain_state(
            repo,
            run_id,
            run_binding=run_binding,
            outbox={"fixture": True} if pending else None,
            chain_id=chain_id,
        )
        return repo, run_id, run_dir, chain_id

    def _parity_fixture(
        self, mode: str, name: str
    ) -> tuple[Path, str, Path]:
        if mode == "closable":
            return self._terminal_run(name)
        if mode == "missing-gate-3":
            return self._missing_gate_three_run(name)
        if mode == "missing-provenance":
            return self._terminal_run(name, provenance=False)
        repo, run_id, run_dir, _chain_id = self._nonterminal_chain_run(
            name, pending=mode == "pending-outbox"
        )
        return repo, run_id, run_dir

    @staticmethod
    def _close(
        repo: Path, run_id: str
    ) -> tuple[bool, str | None]:
        try:
            builders.run_close(
                repo,
                run_id,
                idempotency_key=key(f"{run_id}-close"),
                judgment="passed",
                summary="Synthetic run is ready to close",
                risks=[],
                follow_ups=[],
            )
        except journal.CoordinationRefusal as exc:
            return False, str(exc)
        return True, None

    def test_preflight_has_passed_close_parity_for_each_refusal_source(self) -> None:
        modes = (
            "closable",
            "missing-gate-3",
            "missing-provenance",
            "nonterminal-chain",
            "pending-outbox",
        )
        with self.api_environment():
            for ordinal, mode in enumerate(modes, 1):
                with self.subTest(mode=mode):
                    report_repo, report_run, _report_dir = self._parity_fixture(
                        mode, f"parity-report-{ordinal}"
                    )
                    close_repo, close_run, close_dir = self._parity_fixture(
                        mode, f"parity-close-{ordinal}"
                    )
                    payload = close_preflight.preflight(
                        report_repo, report_run
                    )
                    expected_source = close_law.project_close(
                        close_dir,
                        journal.read_journal(close_dir / "journal.jsonl")[0],
                        "passed",
                    )["issues"]
                    accepted, refusal = self._close(close_repo, close_run)

                    self.assertEqual(payload["would_close_passed"], accepted)
                    if mode == "closable":
                        self.assertEqual(payload["issues"], [])
                    elif mode == "missing-gate-3":
                        self.assertEqual(payload["issues"], expected_source)
                    else:
                        self.assertIsInstance(refusal, str)
                        self.assertEqual(payload["issues"], str(refusal).splitlines())

    def test_builder_and_preflight_share_one_projection_implementation(self) -> None:
        with self.api_environment():
            repo, run_id, _run_dir = self._terminal_run("shared-projection")
            original = close_law.project_close
            with mock.patch.object(
                close_law, "project_close", wraps=original
            ) as projection:
                payload = close_preflight.preflight(repo, run_id)
                accepted, refusal = self._close(repo, run_id)

        self.assertTrue(payload["would_close_passed"])
        self.assertTrue(accepted, refusal)
        self.assertEqual(projection.call_count, 2)
        report_call, builder_call = projection.call_args_list
        self.assertEqual(report_call.args[1], builder_call.args[1])
        self.assertEqual(report_call.args[2], builder_call.args[2], "passed")

    @staticmethod
    def _snapshot(root: Path) -> dict[str, tuple[int, int, int, str | None]]:
        snapshot: dict[str, tuple[int, int, int, str | None]] = {}
        for path in (root, *sorted(root.rglob("*"), key=lambda item: os.fsencode(item))):
            observed = path.lstat()
            digest = (
                hashlib.sha256(path.read_bytes()).hexdigest()
                if stat.S_ISREG(observed.st_mode)
                else None
            )
            snapshot[str(path.relative_to(root))] = (
                observed.st_ino,
                observed.st_size,
                observed.st_mtime_ns,
                digest,
            )
        return snapshot

    def _assert_chain_preflight_is_read_only(
        self,
        name: str,
        *,
        observed: dict[str, Path] | None = None,
    ) -> tuple[Path, str]:
        repo, run_id, run_dir, chain_id = self._nonterminal_chain_run(name)
        chains_root = builders.chain_storage_root(repo)
        lock_path = chains_root / f".{chain_id}.events.lock"
        if observed is not None:
            observed["lock_path"] = lock_path
        self.assertFalse(lock_path.exists())
        run_before = self._snapshot(run_dir)
        chains_before = self._snapshot(chains_root)

        payload = close_preflight.preflight(repo, run_id)

        self.assertFalse(payload["would_close_passed"])
        self.assertEqual(self._snapshot(run_dir), run_before)
        self.assertEqual(self._snapshot(chains_root), chains_before)
        self.assertFalse(lock_path.exists())
        self.assertFalse((run_dir / journal.BATCH_INTENT_NAME).exists())
        return lock_path, chain_id

    def test_chain_replay_is_read_only_and_control_disable_restores_lock_creation(
        self,
    ) -> None:
        with self.api_environment():
            self._assert_chain_preflight_is_read_only("chain-read-only")
            disabled = close_law.CLOSE_LAW_CONTROLS - {"read-only-chain-lock"}
            observed: dict[str, Path] = {}
            with mock.patch.object(
                close_law, "CLOSE_LAW_CONTROLS", disabled
            ), self.assertRaises(AssertionError):
                self._assert_chain_preflight_is_read_only(
                    "chain-lock-disabled", observed=observed
                )
            self.assertTrue(observed["lock_path"].exists())

    @staticmethod
    def _outbox_records(repo: Path, chain_id: str) -> tuple[str, tuple[dict, ...]]:
        events_path = builders.chain_storage_root(repo) / f"{chain_id}.events.jsonl"
        events = [json.loads(line) for line in events_path.read_bytes().splitlines()]
        carrier = next(
            event["payload"]["details"]
            for event in events
            if isinstance(event.get("payload"), dict)
            and isinstance(event["payload"].get("details"), dict)
            and "journal_batch" in event["payload"]["details"]
        )
        journal_batch = carrier["journal_batch"]
        return str(carrier["source_event_digest"]), tuple(
            copy.deepcopy(journal_batch["records"])
        )

    @staticmethod
    def _acknowledge(
        repo: Path,
        chain_id: str,
        state_path: Path,
        receipt: dict[str, object],
    ) -> None:
        events_path = builders.chain_storage_root(repo) / f"{chain_id}.events.jsonl"
        events = [json.loads(line) for line in events_path.read_bytes().splitlines()]
        state = json.loads(state_path.read_bytes())
        pending = state["journal_outbox"]
        state = copy.deepcopy(state)
        state["last_event_at"] = "2026-09-30T12:04:00Z"
        state["journal_outbox"] = None
        unsigned = {
            "sequence": len(events) + 1,
            "prev_digest": events[-1]["digest"],
            "payload": {
                "at": state["last_event_at"],
                "details": batch.journal_receipted_details(pending, receipt),
                "event": "journal_receipted",
                "state": copy.deepcopy(state),
            },
        }
        events.append(
            {
                **unsigned,
                "digest": journal._sha256(journal._canonical_json_bytes(unsigned)),
            }
        )
        events_path.write_bytes(
            b"".join(journal._canonical_json_bytes(event) + b"\n" for event in events)
        )
        state_path.write_bytes(journal._canonical_json_bytes(state) + b"\n")

    def _receipted_chain_run(
        self, name: str
    ) -> tuple[Path, str, Path, str]:
        repo, _head = self._repository(name)
        run_id = f"run-20260930-preflight-{name}"
        self._open_legacy_run(repo, run_id, scope=["src/**"])
        run_dir = self.run_dir(repo, run_id)
        journal_path = run_dir / "journal.jsonl"
        journal.append_owned_record(
            journal_path,
            {
                "type": "task",
                "id": "task-01",
                "status": "active",
                "goal": "Exercise receipt replay",
                "acceptance": ["The shared lock is reused"],
                "files": ["src/example.py"],
                "run_id": run_id,
                "recorded_at": "2026-09-30T12:01:00Z",
            },
        )
        journal_prefix = journal_path.read_bytes()
        with batch.batch_lock(run_dir, create=True) as locked:
            batch._ensure_receipt_ledger(locked)
        chain_id = "c-2026-09-30T120200Z-c101"
        run_binding = {
            "run_id": run_id,
            "task_id": "task-01",
            "repository": str(repo.resolve()),
            "policy_digest": key(f"{name}-policy"),
        }
        _chain_id, state_path = self._write_bound_chain_state(
            repo,
            run_id,
            run_binding=run_binding,
            outbox={"fixture": True},
            chain_id=chain_id,
        )
        source_digest, records = self._outbox_records(repo, chain_id)
        batch_bytes = b"".join(journal._journal_line(record) for record in records)
        inputs = {
            "chain_id": chain_id,
            "source_event_digest": source_digest,
            "batch_digest": journal._sha256(batch_bytes),
            "record_count": len(records),
        }
        _request, request_digest = batch.normalized_request(
            repo.resolve(), run_id, "chain outbox-drain", inputs
        )
        journal_bytes = journal_prefix + batch_bytes
        journal_path.write_bytes(journal_bytes)
        receipt = {
            "schema": journal.BATCH_RECEIPT_SCHEMA,
            "idempotency_key": source_digest,
            "request_sha256": request_digest,
            "base_size": len(journal_prefix),
            "batch_sha256": journal._sha256(batch_bytes),
            "record_count": len(records),
            "journal_size": len(journal_bytes),
            "journal_sha256": journal._sha256(journal_bytes),
            "recorded_at": "2026-09-30T12:03:00Z",
        }
        (run_dir / journal.BATCH_RECEIPTS_NAME).write_bytes(
            journal._canonical_json_bytes(receipt) + b"\n"
        )
        self._acknowledge(repo, chain_id, state_path, receipt)
        return repo, run_id, run_dir, chain_id

    @contextmanager
    def _nonlocking_batch_spy(self, entered: list[Path]):
        @contextmanager
        def nonlocking(run_dir: Path, *, create: bool):
            self.assertFalse(create)
            entered.append(run_dir)
            run_descriptor, _run_observation = journal._open_bound_directory(run_dir)
            lock_descriptor = os.open(
                journal.BATCH_LOCK_NAME,
                batch._safe_open_flags(os.O_RDONLY),
                dir_fd=run_descriptor,
            )
            try:
                yield batch.BatchLock(
                    run_dir,
                    run_descriptor,
                    lock_descriptor,
                    journal._file_observation(os.fstat(lock_descriptor)),
                )
            finally:
                os.close(lock_descriptor)
                os.close(run_descriptor)

        with mock.patch.object(batch, "batch_lock", side_effect=nonlocking):
            yield

    @contextmanager
    def _process_lock(self, path: Path, mode: int):
        code = (
            "import fcntl,os,sys; "
            "fd=os.open(sys.argv[1],os.O_RDONLY); "
            f"fcntl.flock(fd,{mode}); "
            "print('locked',flush=True); sys.stdin.buffer.read(); os.close(fd)"
        )
        process = subprocess.Popen(
            [sys.executable, "-c", code, str(path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert process.stdout is not None
        self.assertEqual(process.stdout.readline().strip(), "locked")
        try:
            yield
        finally:
            assert process.stdin is not None
            process.stdin.close()
            return_code = process.wait(timeout=5)
            assert process.stderr is not None
            error = process.stderr.read()
            process.stdout.close()
            process.stderr.close()
            self.assertEqual(return_code, 0, error)

    def _assert_receipt_preflight_reuses_shared_lock(self, name: str) -> list[Path]:
        repo, run_id, run_dir, _chain_id = self._receipted_chain_run(name)
        entered: list[Path] = []
        with self._nonlocking_batch_spy(entered), self._process_lock(
            run_dir / journal.BATCH_LOCK_NAME, fcntl.LOCK_SH
        ):
            payload = close_preflight.preflight(repo, run_id)
        self.assertFalse(payload["would_close_passed"])
        self.assertEqual(entered, [])
        return entered

    def test_receipt_replay_reuses_shared_hold_and_control_disable_reenters_lock(
        self,
    ) -> None:
        with self.api_environment():
            self._assert_receipt_preflight_reuses_shared_lock("receipt-read-only")
            disabled = close_law.CLOSE_LAW_CONTROLS - {"read-only-receipt-check"}
            with mock.patch.object(
                close_law, "CLOSE_LAW_CONTROLS", disabled
            ), self.assertRaises(AssertionError):
                self._assert_receipt_preflight_reuses_shared_lock(
                    "receipt-check-disabled"
                )

    def test_existing_chain_lock_has_bounded_shared_wait(self) -> None:
        with self.api_environment():
            repo, run_id, _run_dir, chain_id = self._nonterminal_chain_run(
                "chain-lock-busy"
            )
            lock_path = builders.chain_storage_root(repo) / f".{chain_id}.events.lock"
            lock_path.write_bytes(b"")
            descriptor = os.open(lock_path, os.O_RDONLY)
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            started = time.monotonic()
            try:
                with mock.patch.object(close_law, "CHAIN_LOCK_WAIT_SECONDS", 0.3):
                    payload = close_preflight.preflight(repo, run_id)
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
                os.close(descriptor)

        self.assertLess(time.monotonic() - started, 2.0)
        self.assertEqual(
            payload["issues"],
            [f"forge: close preflight — chain lock busy: {chain_id}"],
        )
        self.assertFalse(payload["would_close_passed"])

    def _projection_run(self, name: str) -> tuple[Path, str, str]:
        repo, _head = self._repository(name)
        run_id = f"run-20260930-preflight-{name}"
        self.open_run(repo, run_id)
        self.start_task(repo, run_id)
        chain_id = "c-2026-09-30T120300Z-d101"
        for index, criterion in enumerate(
            ("gate-1: gate-1", "gate-2: stack", journal.GATE_3_CRITERION), 1
        ):
            self._bound_verification(
                repo, run_id, chain_id, criterion, f"projection-gate-{index}"
            )
        builders.decision_add(
            repo,
            run_id,
            idempotency_key=key(f"{name}-provenance"),
            task="task-01",
            resolution="orchestrator-owned: projected chain fixture",
            finding=None,
            outcome=None,
            risk=None,
            basis=["projection fixture"],
            binding_chain=None,
            binding_id=None,
        )
        chains_root = builders.chain_storage_root(repo)
        chains_root.mkdir(parents=True, exist_ok=True)
        (chains_root / f"{chain_id}.json").write_text(
            json.dumps(
                {
                    "chain_id": chain_id,
                    "tier": {"control": False},
                    "review": {"operator_cosign_required": False},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return repo, run_id, chain_id

    def test_named_chain_projects_landing_and_task_completion(self) -> None:
        expected = (
            "task 'task-01' has inconsistent bound candidate across gate and "
            "landing records"
        )
        with self.api_environment(), mock.patch.object(
            builders, "_terminal_chain_guard", return_value=None
        ):
            repo, run_id, chain_id = self._projection_run("projected-chain")
            without = close_preflight.preflight(repo, run_id)
            projected = close_preflight.preflight(repo, run_id, chain=chain_id)

        self.assertEqual(
            without["issues"],
            [
                "task task-01 is not terminal; latest status is 'active'",
                expected,
            ],
        )
        self.assertFalse(without["would_close_passed"])
        self.assertEqual(projected["issues"], [])
        self.assertTrue(projected["would_close_passed"])
        self.assertEqual(projected["projected_chain"], chain_id)

    def test_projected_chain_records_continue_snapshot_line_numbers(self) -> None:
        chain_id = "c-2026-09-30T120350Z-d102"
        binding = self._binding(chain_id, "projected-lines")
        records = [
            {"type": "run_started", "_line": 1},
            {
                "type": "verification",
                "id": "check-01",
                "task": "task-01",
                "criterion": "gate-1: gate-1",
                "result": "passed",
                "binding": binding,
                "_line": 4,
            },
        ]

        projected = close_law.projected_chain_records(
            records,
            chain_id,
            {
                "tier": {"control": True},
                "review": {"operator_cosign_required": False},
            },
        )

        self.assertEqual([record["_line"] for record in projected], [1, 4, 5, 6, 7])
        self.assertEqual(
            [record.get("outcome") for record in projected[2:4]],
            ["chain-landing", "chain-approval"],
        )
        self.assertEqual(projected[4]["status"], "complete")
        self.assertEqual(records[-1]["_line"], 4)

    def test_output_is_compact_valid_json_bounded_to_64_kib(self) -> None:
        issues = [f"issue-{index}:" + ("x" * 2048) for index in range(100)]
        with self.api_environment():
            repo, run_id, _run_dir = self._terminal_run("output-cap")
            output = io.StringIO()
            with mock.patch.object(
                close_preflight, "_projected_issues", return_value=issues
            ), redirect_stdout(output):
                exit_code = close_preflight.main(repo, run_id)

        rendered = output.getvalue()
        payload = json.loads(rendered)
        self.assertEqual(exit_code, 1)
        self.assertLessEqual(len(rendered.encode("utf-8")), 65_536)
        self.assertEqual(rendered.count("\n"), 1)
        self.assertGreater(payload["issues_omitted"], 0)
        self.assertFalse(payload["would_close_passed"])

    def test_cli_exit_codes_key_and_duplicate_chain_contract(self) -> None:
        with self.api_environment():
            repo, run_id, _run_dir = self._terminal_run("cli")
        base = [
            "journal",
            "close-preflight",
            "--repo",
            str(repo.resolve()),
            "--run-id",
            run_id,
        ]
        accepted = self.command(*base)
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        payload = json.loads(accepted.stdout)
        self.assertEqual(payload["schema"], "forge-close-preflight/1")
        self.assertEqual(
            set(payload),
            {
                "issues",
                "journal_lines",
                "projected_chain",
                "run_id",
                "schema",
                "would_close_passed",
            },
        )
        self.assertTrue(payload["would_close_passed"])

        refused_key = self.command(
            *base,
            "--idempotency-key",
            key("preflight-must-not-take-a-key"),
        )
        self.assertEqual(refused_key.returncode, 1)
        self.assertEqual(refused_key.stdout, "")
        self.assertEqual(refused_key.stderr.strip(), journal.BATCH_KEY_REFUSAL)

        chain_id = "c-2026-09-30T120400Z-e101"
        duplicate = self.command(
            *base, "--chain", chain_id, "--chain", chain_id
        )
        self.assertEqual(duplicate.returncode, 1)
        self.assertEqual(duplicate.stdout, "")
        self.assertEqual(
            duplicate.stderr.strip(),
            "forge: CLI option refused — duplicate --chain",
        )

    def test_closed_invalid_and_unbound_chain_diagnostics_are_exact(self) -> None:
        with self.api_environment():
            closed_repo, closed_run, _closed_dir = self._terminal_run("closed")
            accepted, refusal = self._close(closed_repo, closed_run)
            self.assertTrue(accepted, refusal)
            closed = close_preflight.preflight(closed_repo, closed_run)

            repo, run_id, _run_dir = self._terminal_run("diagnostics")
            invalid_value = "not-a-chain-sensitive-marker"
            invalid = close_preflight.preflight(
                repo, run_id, chain=invalid_value
            )
            chain_id = "c-2026-09-30T120500Z-f101"
            missing = close_preflight.preflight(repo, run_id, chain=chain_id)

        self.assertEqual(
            closed["issues"], ["forge: close preflight — run is not open"]
        )
        self.assertEqual(
            invalid["issues"], ["forge: close preflight — invalid chain id"]
        )
        self.assertIsNone(invalid["projected_chain"])
        self.assertNotIn(invalid_value, json.dumps(invalid, sort_keys=True))
        self.assertEqual(
            missing["issues"],
            [
                "forge: close preflight — projected chain has no bound gate "
                f"records: {chain_id}"
            ],
        )


if __name__ == "__main__":
    unittest.main()
