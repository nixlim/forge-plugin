from __future__ import annotations

import base64
import copy
import io
import json
import os
import subprocess
import sys
import tempfile
from contextlib import contextmanager, redirect_stderr
from pathlib import Path
from unittest import mock

from tests._revision9_coord_constants import TOOLS, key

from codex_orchestrator import batch, builders, journal


class Revision9BuilderBatchSupport:
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="forge-revision9-builder-")
        self.addCleanup(self.temporary.cleanup)
        self.env = os.environ.copy()
        self.env["FORGE_SESSION_PID"] = str(os.getpid())
        self.repo, self.head = self._new_repo("repo")

    def _new_repo(self, name: str) -> tuple[Path, str]:
        repo = Path(self.temporary.name) / name
        subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "-c",
                "user.name=Forge Tests",
                "-c",
                "user.email=forge-tests@example.invalid",
                "-c",
                "commit.gpgsign=false",
                "commit",
                "--allow-empty",
                "--quiet",
                "-m",
                "base",
            ],
            check=True,
        )
        head = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        return repo, head

    @contextmanager
    def api_environment(self):
        with mock.patch.dict(os.environ, self.env, clear=True):
            yield

    def run_dir(self, repo: Path, run_id: str) -> Path:
        return repo / ".codex-orchestrator/runs" / run_id

    def open_run(self, repo: Path, run_id: str, label: str = "open") -> batch.BatchOutcome:
        return builders.run_open(
            repo,
            run_id,
            idempotency_key=key(f"{run_id}-{label}"),
            goal="Exercise Revision 9",
            scope=["src/**"],
            plugin_ref="forge-test-revision-9",
        )

    def start_task(self, repo: Path, run_id: str, label: str = "task") -> batch.BatchOutcome:
        return builders.task_start(
            repo,
            run_id,
            idempotency_key=key(f"{run_id}-{label}"),
            task="task-01",
            goal="Implement the typed transaction",
            acceptance=["The focused behavior passes"],
            files=["src/example.py"],
        )

    def _leave_complete_intent(
        self, repo: Path, run_id: str
    ) -> tuple[Path, dict[str, object]]:
        self.open_run(repo, run_id)
        def crash_after_journal(
            locked: batch.BatchLock,
            intent: dict[str, object],
            _observation: journal.FileObservation,
            **_kwargs: object,
        ) -> batch.BatchOutcome:
            batch_bytes = base64.urlsafe_b64decode(
                str(intent["batch_bytes"])
                + "=" * (-len(str(intent["batch_bytes"])) % 4)
            )
            descriptor = os.open(
                "journal.jsonl",
                os.O_WRONLY | os.O_APPEND,
                dir_fd=locked.run_descriptor,
            )
            try:
                os.write(descriptor, batch_bytes)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            raise RuntimeError("crash")

        with mock.patch.object(batch, "_recover_locked", side_effect=crash_after_journal):
            with self.assertRaisesRegex(RuntimeError, "crash"):
                self.start_task(repo, run_id)
        run_dir = self.run_dir(repo, run_id)
        intent = json.loads(
            (run_dir / journal.BATCH_INTENT_NAME).read_text(encoding="utf-8")
        )
        self.assertEqual(intent["schema"], journal.BATCH_INTENT_SCHEMA)
        self.assertEqual(set(intent), batch._intent_keys())
        self.assertNotIn("=", intent["batch_bytes"])
        self.assertNotIn("=", intent["receipt_bytes"])
        return run_dir, intent

    def _write_landed_intent_for_last_receipt(
        self, run_dir: Path, ledger_lines: list[bytes]
    ) -> dict[str, object]:
        following_line = ledger_lines[-1]
        following = json.loads(following_line)
        ledger_prefix = b"".join(ledger_lines[:-1])
        journal_bytes = (run_dir / "journal.jsonl").read_bytes()
        batch_bytes = journal_bytes[
            int(following["base_size"]) : int(following["journal_size"])
        ]
        intent = {
            "schema": journal.BATCH_INTENT_SCHEMA,
            "idempotency_key": following["idempotency_key"],
            "request_sha256": following["request_sha256"],
            "base_size": following["base_size"],
            "base_sha256": journal._sha256(
                journal_bytes[: int(following["base_size"])]
            ),
            "record_count": following["record_count"],
            "batch_bytes": batch._encode_base64url(batch_bytes),
            "batch_sha256": following["batch_sha256"],
            "receipt_base_size": len(ledger_prefix),
            "receipt_base_sha256": journal._sha256(ledger_prefix),
            "receipt_bytes": batch._encode_base64url(following_line),
        }
        (run_dir / journal.BATCH_INTENT_NAME).write_bytes(
            journal._canonical_json_bytes(intent) + b"\n"
        )
        return intent

    def _write_bound_chain_state(
        self,
        repo: Path,
        run_id: str,
        *,
        run_binding: object,
        outbox: object = None,
        activation_marker: dict[str, object] | None = None,
        chain_id: str = "c-2026-08-28T120000Z-abcd",
    ) -> tuple[str, Path]:
        chains = builders.chain_storage_root(repo)
        chains.mkdir(parents=True, exist_ok=True)
        state_path = chains / f"{chain_id}.json"

        # Terminal controls authenticate a bound chain by replaying its event
        # stream before trusting either the materialized outbox or landing
        # state.  Keep malformed/unbound fixtures minimal for the controls
        # that intentionally stop before replay; valid bindings receive a
        # small, semantically valid commit history.
        if not (
            isinstance(run_binding, dict)
            and set(run_binding)
            == {"run_id", "task_id", "repository", "policy_digest"}
        ):
            state_path.write_bytes(
                journal._canonical_json_bytes(
                    {
                        "schema": "fixture-chain/1",
                        "chain_id": chain_id,
                        "run_binding": run_binding,
                        "journal_outbox": outbox,
                    }
                )
                + b"\n"
            )
            return chain_id, state_path

        paths = ["src/example.py"]
        candidate = key("terminal-candidate")
        inactive_after = "2026-08-29T12:00:00Z"
        state: dict[str, object] = {
            "schema": "forge-chain/1",
            "chain_id": chain_id,
            "kind": "commit",
            "state": "classifying",
            "created_at": "2026-08-28T12:00:00Z",
            "last_event_at": "2026-08-28T12:00:00Z",
            "inactive_after": inactive_after,
            "repo_head": "1" * 40,
            "policy_source": {
                "path": "forge-project.md",
                "sha": "1" * 40,
                "digest": run_binding["policy_digest"],
            },
            "paths": paths,
            "staging": {
                "worktree_root": str(repo.resolve()),
                "session_identity": "fixture",
                "staged_paths": [],
                "staged_at": None,
                "classification_runs": 0,
                "anomalies": [],
            },
            "candidate": {"sha256": None, "computed_at": None},
            "tier": {
                "declared": None,
                "derived": None,
                "effective": None,
                "control": False,
                "categories": [],
                "classification": None,
            },
            "steps": {},
            "review": {
                "iteration": 0,
                "request": None,
                "verdict": None,
                "dispositions": [],
                "operator_cosign_required": False,
                "residual_risk": None,
            },
            "approval": {},
            "authorization": {},
            "commit_result": {},
            "run_binding": copy.deepcopy(run_binding),
            "journal_outbox": None,
        }
        events: list[dict[str, object]] = []
        previous = "0" * 64

        def append_event(
            event_name: str,
            at: str,
            details: dict[str, object],
            snapshot: dict[str, object],
        ) -> None:
            nonlocal previous
            unsigned = {
                "sequence": len(events) + 1,
                "prev_digest": previous,
                "payload": {
                    "at": at,
                    "details": details,
                    "event": event_name,
                    "state": copy.deepcopy(snapshot),
                },
            }
            event = {
                **unsigned,
                "digest": journal._sha256(journal._canonical_json_bytes(unsigned)),
            }
            events.append(event)
            previous = str(event["digest"])

        append_event("chain_started", state["last_event_at"], {"paths": paths}, state)

        state = copy.deepcopy(state)
        state["last_event_at"] = "2026-08-28T12:01:00Z"
        assert isinstance(state["staging"], dict)
        state["staging"]["staged_paths"] = paths
        state["staging"]["staged_at"] = state["last_event_at"]
        state["candidate"] = {
            "sha256": candidate,
            "computed_at": state["last_event_at"],
        }
        append_event(
            "candidate_staged",
            str(state["last_event_at"]),
            {"candidate": candidate, "paths": paths},
            state,
        )

        state = copy.deepcopy(state)
        state["last_event_at"] = "2026-08-28T12:02:00Z"
        state["state"] = "verifying"
        assert isinstance(state["staging"], dict)
        state["staging"]["classification_runs"] = 1
        state["tier"] = {
            "declared": None,
            "derived": "fast",
            "effective": "fast",
            "control": False,
            "categories": [],
            "classification": {"fixture": True},
        }
        state["steps"] = {
            "classification": [
                {"candidate": candidate, "result": "passed"}
            ]
        }
        append_event(
            "classified",
            str(state["last_event_at"]),
            {"effective_tier": "fast", "control": False},
            state,
        )

        if outbox is not None:
            state = copy.deepcopy(state)
            state["last_event_at"] = "2026-08-28T12:03:00Z"
            assert isinstance(state["steps"], dict)
            state["steps"]["gate-1"] = [
                {"candidate": candidate, "result": "passed"}
            ]
            unsigned = {
                "sequence": len(events) + 1,
                "prev_digest": previous,
                "payload": {
                    "at": state["last_event_at"],
                    "details": {
                        "step_id": "gate-1",
                        "result": "passed",
                        "run": 1,
                    },
                    "event": "step_recorded",
                    "state": state,
                },
            }
            source_digest = journal._sha256(
                journal._canonical_json_bytes(unsigned)
            )
            binding_preimage = {
                "schema": journal.BINDING_SCHEMA,
                "source_record": {
                    "chain_id": chain_id,
                    "event_digest": source_digest,
                },
                "candidate": {
                    "kind": "staged-diff-sha256",
                    "value": candidate,
                },
                "review": None,
            }
            binding = {
                **binding_preimage,
                "binding_id": journal._sha256(
                    journal._canonical_json_bytes(binding_preimage)
                ),
            }
            record = {
                "type": "verification",
                "recorded_at": state["last_event_at"],
                "run_id": run_id,
                "id": "check-fixture",
                "task": run_binding["task_id"],
                "criterion": "gate-1: terminal fixture",
                "method": "fixture",
                "check": "fixture",
                "result": "passed",
                "observation": "fixture",
                "evidence": [],
                "binding": binding,
            }
            records = (
                [copy.deepcopy(activation_marker), record]
                if activation_marker is not None
                else [record]
            )
            batch_bytes = b"".join(
                journal._journal_line(item) for item in records
            )
            journal_batch = {
                "idempotency_key": source_digest,
                "batch_digest": journal._sha256(batch_bytes),
                "record_count": len(records),
                "records": records,
            }
            assert isinstance(unsigned["payload"], dict)
            details = unsigned["payload"]["details"]
            assert isinstance(details, dict)
            details["source_event_digest"] = source_digest
            details["journal_batch"] = journal_batch
            state["journal_outbox"] = {
                "idempotency_key": source_digest,
                "batch_digest": journal_batch["batch_digest"],
                "record_count": len(records),
                "source_event_digest": source_digest,
            }
            final_event = {
                **unsigned,
                "digest": journal._sha256(journal._canonical_json_bytes(unsigned)),
            }
            events.append(final_event)

        (chains / f"{chain_id}.events.jsonl").write_bytes(
            b"".join(
                journal._canonical_json_bytes(event) + b"\n" for event in events
            )
        )
        state_path.write_bytes(
            journal._canonical_json_bytes(state) + b"\n"
        )
        return chain_id, state_path

    def _chain_drain_authorizer(
        self,
        repo: Path,
        run_id: str,
        chain_id: str,
        source_event_digest: str,
        records: tuple[dict[str, object], ...],
        *,
        mismatch: str | None = None,
    ) -> tuple[object, object, list[dict[str, object]]]:
        capability = object()
        calls: list[dict[str, object]] = []
        task_id = next(
            str(record["task"])
            for record in records
            if isinstance(record.get("task"), str)
        )
        batch_bytes = b"".join(
            journal._journal_line(record) for record in records
        )
        inputs = {
            "chain_id": chain_id,
            "source_event_digest": source_event_digest,
            "batch_digest": journal._sha256(batch_bytes),
            "record_count": len(records),
        }
        _, request_sha256 = batch.normalized_request(
            repo.resolve(), run_id, "chain outbox-drain", inputs
        )

        def exact(path: Path) -> journal.ExactFile:
            observed = os.lstat(path)
            return journal.ExactFile(
                path.read_bytes(), journal._file_observation(observed)
            )

        def authorize(**kwargs: object) -> object:
            calls.append(dict(kwargs))
            if kwargs.get("capability") is not capability:
                raise journal.CoordinationRefusal(
                    journal.INVALID_JOURNAL_RECORD
                )
            self.assertEqual(kwargs.get("repository"), repo.resolve())
            self.assertEqual(kwargs.get("run_id"), run_id)
            self.assertEqual(kwargs.get("task_id"), task_id)
            self.assertEqual(kwargs.get("chain_id"), chain_id)
            self.assertEqual(
                kwargs.get("source_event_digest"), source_event_digest
            )
            self.assertEqual(kwargs.get("supplied_records"), records)
            run_dir = self.run_dir(repo, run_id)
            values: dict[str, object] = {
                "repository": str(repo.resolve()),
                "run_id": run_id,
                "task_id": task_id,
                "chain_id": chain_id,
                "source_event_digest": source_event_digest,
                "request_sha256": request_sha256,
                "batch_bytes": batch_bytes,
                "record_count": len(records),
                "journal_exact": exact(run_dir / "journal.jsonl"),
                "receipts_exact": exact(
                    run_dir / journal.BATCH_RECEIPTS_NAME
                ),
            }
            if mismatch == "repository":
                values["repository"] = str(repo.resolve()) + "-foreign"
            elif mismatch in {
                "run_id",
                "task_id",
                "chain_id",
                "source_event_digest",
                "request_sha256",
            }:
                values[mismatch] = key(f"mismatch-{mismatch}")
            elif mismatch == "batch_bytes":
                changed = copy.deepcopy(records[0])
                changed["recorded_at"] = "2026-08-28T12:59:59Z"
                values["batch_bytes"] = journal._journal_line(changed)
            elif mismatch == "record_count":
                values["record_count"] = len(records) + 1
            elif mismatch == "journal_exact":
                current = values["journal_exact"]
                assert isinstance(current, journal.ExactFile)
                values["journal_exact"] = journal.ExactFile(
                    current.payload + b" ", current.observation
                )
            elif mismatch == "receipts_exact":
                current = values["receipts_exact"]
                assert isinstance(current, journal.ExactFile)
                values["receipts_exact"] = journal.ExactFile(
                    current.payload + b" ", current.observation
                )
            return batch._ChainBatchAuthorization(**values)

        return capability, authorize, calls

    def _terminal_control_repo(self, name: str) -> tuple[Path, str, dict[str, object]]:
        repo, _ = self._new_repo(name)
        run_id = f"run-20260828-{name}"
        self.open_run(repo, run_id)
        self.start_task(repo, run_id)
        run_binding = {
            "run_id": run_id,
            "task_id": "task-01",
            "repository": str(repo.resolve()),
            "policy_digest": key("policy"),
        }
        return repo, run_id, run_binding

    def _open_legacy_run(
        self,
        repo: Path,
        run_id: str,
        *,
        successor_of: str | None = None,
        scope: list[str] | None = None,
    ) -> None:
        record: dict[str, object] = {
            "type": "run_started",
            "recorded_at": "2026-08-28T12:00:00Z",
            "run_id": run_id,
            "goal": "Legacy successor recovery fixture",
            "repo": str(repo.resolve()),
            "repo_head": subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip(),
            "repo_status": [],
            "plugin_ref": "forge-test-revision-9",
        }
        if successor_of is not None:
            record["successor_of"] = successor_of
        captured = io.StringIO()
        with redirect_stderr(captured):
            journal.open_run(
                repo,
                run_id,
                ["src/**"] if scope is None else scope,
                record,
                successor_of=successor_of,
            )
        self.assertEqual(captured.getvalue(), "")

    @staticmethod
    def _activation_markers(
        records: list[dict[str, object]] | tuple[dict[str, object], ...],
    ) -> list[dict[str, object]]:
        return [
            record
            for record in records
            if journal._writer_activation_marker(record)
        ]

    @staticmethod
    def _run_file_bytes(run_dir: Path) -> dict[str, bytes]:
        return {
            path.name: path.read_bytes()
            for path in run_dir.iterdir()
            if path.is_file()
        }

    def _invoke_raw_lifecycle(
        self, repo: Path, run_id: str, operation: str
    ) -> None:
        if operation == "readmit":
            journal.readmit_run(repo, run_id, ["src/**"])
            return
        if operation == "retire":
            journal.retire_run(repo, run_id)
            return
        self.assertEqual(operation, "close")
        run_dir = self.run_dir(repo, run_id)
        journal.close_run(
            repo,
            run_id,
            {
                "type": "run_closed",
                "recorded_at": "2026-09-10T03:20:01Z",
                "run_id": run_id,
                "judgment": "blocked",
                "summary": "Pending activation retains first-use authority",
                "validation": journal.validate_run(run_dir, gates=True),
                "risks": [],
                "follow_ups": [],
            },
        )

    def _seed_gh17_wedge(
        self,
        repo: Path,
        run_id: str,
        *,
        explicit_gap_run_id: str | None = None,
    ) -> tuple[Path, dict[str, object]]:
        self._open_legacy_run(repo, run_id)
        run_dir = self.run_dir(repo, run_id)
        journal_path = run_dir / "journal.jsonl"
        legacy_prefix = journal_path.read_bytes()
        with batch.batch_lock(run_dir, create=True):
            pass

        task = {
            "type": "task",
            "id": "task-01",
            "status": "active",
            "goal": "Reproduce the historical GH17 recovery wedge",
            "acceptance": ["Recovery does not reapply durable records"],
            "files": ["src/example.py"],
            "run_id": run_id,
            "recorded_at": "2026-09-10T02:00:00Z",
        }
        task_bytes = journal._journal_line(task)
        task_key = key(f"{run_id}-legacy-task")
        task_inputs = {
            "task": "task-01",
            "goal": task["goal"],
            "acceptance": task["acceptance"],
            "file": task["files"],
        }
        _task_request, task_request_sha256 = batch.normalized_request(
            repo.resolve(), run_id, "journal task-start", task_inputs
        )
        task_journal = legacy_prefix + task_bytes
        task_receipt = {
            "schema": journal.BATCH_RECEIPT_SCHEMA,
            "idempotency_key": task_key,
            "request_sha256": task_request_sha256,
            "base_size": len(legacy_prefix),
            "batch_sha256": journal._sha256(task_bytes),
            "record_count": 1,
            "journal_size": len(task_journal),
            "journal_sha256": journal._sha256(task_journal),
            "recorded_at": "2026-09-10T02:00:00Z",
        }
        task_receipt_line = (
            journal._canonical_json_bytes(task_receipt) + b"\n"
        )

        def raw_verification(
            check_id: str,
            observation: str,
            recorded_at: str,
            *,
            legacy: bool = False,
        ) -> dict[str, object]:
            record = {
                "type": "verification",
                "id": check_id,
                "task": "task-01",
                "criterion": "mutation",
                "method": "bash",
                "check": "true",
                "result": "passed",
                "observation": observation,
                "evidence": [],
                "run_id": run_id,
                "recorded_at": recorded_at,
            }
            if legacy:
                del record["run_id"]
            return record

        raw_first = raw_verification(
            "check-01",
            "raw mutation one",
            "2026-09-10T02:00:01Z",
            legacy=True,
        )
        if explicit_gap_run_id is not None:
            raw_first["run_id"] = explicit_gap_run_id
        raw_second = raw_verification(
            "check-02",
            "raw mutation two",
            "2026-09-10T02:00:02Z",
            legacy=True,
        )
        gap_bytes = journal._journal_line(raw_first) + journal._journal_line(
            raw_second
        )
        padding = 786 - len(gap_bytes)
        self.assertGreaterEqual(padding, 0)
        raw_second["observation"] = str(raw_second["observation"]) + (
            "x" * padding
        )
        gap_bytes = journal._journal_line(raw_first) + journal._journal_line(
            raw_second
        )
        self.assertEqual(len(gap_bytes), 786)

        typed_verification = raw_verification(
            "check-03",
            "fully applied typed verification",
            "2026-09-10T02:00:03Z",
        )
        typed_bytes = journal._journal_line(typed_verification)
        gap_base = len(task_journal)
        gap_end = gap_base + len(gap_bytes)
        historical_journal = task_journal + gap_bytes + typed_bytes
        journal_path.write_bytes(historical_journal)

        spent_key = key(f"{run_id}-typed-verification")
        spent_inputs = {
            "task": "task-01",
            "criterion": typed_verification["criterion"],
            "method": typed_verification["method"],
            "check": typed_verification["check"],
            "result": typed_verification["result"],
            "observation": typed_verification["observation"],
            "evidence": [],
            "binding_chain": None,
            "binding_id": None,
        }
        _spent_request, spent_request_sha256 = batch.normalized_request(
            repo.resolve(), run_id, "journal verification-add", spent_inputs
        )
        spent_receipt = {
            "schema": journal.BATCH_RECEIPT_SCHEMA,
            "idempotency_key": spent_key,
            "request_sha256": spent_request_sha256,
            "base_size": gap_end,
            "batch_sha256": journal._sha256(typed_bytes),
            "record_count": 1,
            "journal_size": len(historical_journal),
            "journal_sha256": journal._sha256(historical_journal),
            "recorded_at": typed_verification["recorded_at"],
        }
        spent_receipt_line = (
            journal._canonical_json_bytes(spent_receipt) + b"\n"
        )
        ledger_lines = [task_receipt_line, spent_receipt_line]
        (run_dir / journal.BATCH_RECEIPTS_NAME).write_bytes(
            b"".join(ledger_lines)
        )
        intent = self._write_landed_intent_for_last_receipt(
            run_dir, ledger_lines
        )
        return run_dir, {
            "legacy_prefix": legacy_prefix,
            "task": task,
            "task_receipt": task_receipt,
            "gap_records": (raw_first, raw_second),
            "gap_bytes": gap_bytes,
            "gap_base": gap_base,
            "gap_end": gap_end,
            "typed_verification": typed_verification,
            "spent_receipt": spent_receipt,
            "intent": intent,
            "historical_journal": historical_journal,
        }

    def _assert_gh17_recovered(
        self,
        run_dir: Path,
        context: dict[str, object],
    ) -> tuple[dict[str, object], list[dict[str, object]]]:
        journal_path = run_dir / "journal.jsonl"
        records, issues = journal.read_journal(journal_path)
        self.assertEqual(issues, [])
        markers = self._activation_markers(records)
        self.assertEqual(len(markers), 1)
        marker = {
            name: value
            for name, value in markers[0].items()
            if name != "_line"
        }
        historical_journal = context["historical_journal"]
        self.assertIsInstance(historical_journal, bytes)
        self.assertEqual(
            journal_path.read_bytes(),
            historical_journal + journal._journal_line(marker),
        )
        self.assertEqual(marker["receipt_origin_size"], len(context["legacy_prefix"]))
        self.assertEqual(
            marker["receipt_origin_sha256"],
            journal._sha256(context["legacy_prefix"]),
        )
        for check_id in ("check-01", "check-02", "check-03"):
            self.assertEqual(
                sum(
                    record.get("type") == "verification"
                    and record.get("id") == check_id
                    for record in records
                ),
                1,
            )

        receipts = [
            json.loads(line)
            for line in (
                run_dir / journal.BATCH_RECEIPTS_NAME
            ).read_bytes().splitlines()
        ]
        repairs = [
            receipt
            for receipt in receipts
            if receipt.get("repaired") is True
        ]
        self.assertEqual(len(repairs), 1)
        self.assertEqual(repairs[0]["base_size"], context["gap_base"])
        self.assertEqual(repairs[0]["journal_size"], context["gap_end"])
        self.assertEqual(repairs[0]["record_count"], 2)
        self.assertEqual(
            repairs[0]["batch_sha256"],
            journal._sha256(context["gap_bytes"]),
        )
        spent_receipt = context["spent_receipt"]
        self.assertIsInstance(spent_receipt, dict)
        self.assertEqual(
            sum(
                receipt["idempotency_key"]
                == spent_receipt["idempotency_key"]
                for receipt in receipts
            ),
            1,
        )
        marker_base = len(historical_journal)
        activation_receipts = [
            receipt
            for receipt in receipts
            if receipt.get("repaired") is not True
            and receipt["base_size"] == marker_base
            and receipt["batch_sha256"]
            == journal._sha256(journal._journal_line(marker))
        ]
        self.assertEqual(len(activation_receipts), 1)
        self.assertEqual(activation_receipts[0]["record_count"], 1)
        self.assertFalse((run_dir / journal.BATCH_INTENT_NAME).exists())
        return marker, receipts

    def command(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(TOOLS), *arguments],
            cwd=self.repo,
            env=self.env,
            check=False,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
        )
