from __future__ import annotations

import copy
import json
import os
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "scripts/codex_orch_tools.py"

sys.path.insert(0, str(ROOT / "scripts"))
from codex_orchestrator import journal  # noqa: E402


RECORDED_AT = "2026-08-26T12:00:00Z"


class Revision8CoordinationTests(unittest.TestCase):
    """Revision-8 append, orphan, identity, and successor-DAG contracts."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="forge-revision8-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        subprocess.run(["git", "init", "--quiet", str(self.repo)], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(self.repo),
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
        self.head = subprocess.run(
            ["git", "-C", str(self.repo), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        self.env = os.environ.copy()
        self.env["FORGE_SESSION_PID"] = str(os.getpid())
        self._record_number = 0

    @property
    def runs_root(self) -> Path:
        return self.repo / ".codex-orchestrator/runs"

    @property
    def registry_path(self) -> Path:
        return self.repo / ".forge/tmp/run-registry.json"

    def run_dir(self, run_id: str) -> Path:
        return self.runs_root / run_id

    def journal_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "journal.jsonl"

    def write_record(self, value: object, stem: str = "record") -> Path:
        self._record_number += 1
        target = self.root / f"{stem}-{self._record_number:03d}.json"
        target.write_text(json.dumps(value), encoding="utf-8")
        return target

    def command(
        self,
        *arguments: str,
        environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(TOOLS), *arguments],
            cwd=self.repo,
            env=self.env if environment is None else environment,
            check=False,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=20,
        )

    @contextmanager
    def api_environment(self):
        with mock.patch.dict(os.environ, self.env, clear=True):
            yield

    def opening_record(self, run_id: str, **updates: object) -> dict[str, object]:
        record: dict[str, object] = {
            "type": "run_started",
            "recorded_at": RECORDED_AT,
            "run_id": run_id,
            "goal": f"Coordinate {run_id}",
            "repo": str(self.repo.resolve()),
            "repo_head": self.head,
            "repo_status": [],
            "plugin_ref": "forge-test-revision-8",
        }
        record.update(updates)
        return record

    def task_record(self, **updates: object) -> dict[str, object]:
        record: dict[str, object] = {
            "type": "task",
            "recorded_at": RECORDED_AT,
            "id": "task-01",
            "status": "active",
            "goal": "Implement the bounded task",
            "acceptance": ["The focused check passes"],
            "files": ["src/feature.py"],
        }
        record.update(updates)
        return record

    def execution_record(self, **updates: object) -> dict[str, object]:
        record: dict[str, object] = {
            "type": "execution",
            "recorded_at": RECORDED_AT,
            "agent": "codex-impl-01",
            "task": "task-01",
            "provider": "openai",
            "role": "implementation",
            "mode": "headless",
            "model": "gpt-test",
            "effort": "high",
            "execution": "execution-01",
            "worktree": str(self.repo.resolve()),
            "head": self.head,
            "prompt": "prompt.md",
            "handoff": "handoff.md",
            "event_source": "exec",
            "events": "events.jsonl",
        }
        record.update(updates)
        return record

    def execution_result_record(self, **updates: object) -> dict[str, object]:
        record: dict[str, object] = {
            "type": "execution_result",
            "recorded_at": RECORDED_AT,
            "agent": "codex-impl-01",
            "task": "task-01",
            "summary": "Implementation complete",
            "execution": "execution-01",
            "status": "complete",
            "files_changed": ["src/feature.py"],
            "caveats": [],
            "handoff": "handoff.md",
        }
        record.update(updates)
        return record

    def verification_record(self, **updates: object) -> dict[str, object]:
        record: dict[str, object] = {
            "type": "verification",
            "recorded_at": RECORDED_AT,
            "id": "check-01",
            "task": "task-01",
            "criterion": "focused revision-8 behavior",
            "method": "unittest",
            "check": "python3 -m unittest",
            "observation": "all focused assertions passed",
            "result": "passed",
            "evidence": [],
        }
        record.update(updates)
        return record

    def decision_record(self, **updates: object) -> dict[str, object]:
        record: dict[str, object] = {
            "type": "decision",
            "recorded_at": RECORDED_AT,
            "id": "decision-01",
            "resolution": "Use the tested coordination path",
            "basis": [],
        }
        record.update(updates)
        return record

    def closure_record(
        self, judgment: str = "passed", **updates: object
    ) -> dict[str, object]:
        record: dict[str, object] = {
            "type": "run_closed",
            "recorded_at": RECORDED_AT,
            "judgment": judgment,
            "summary": f"Run closed as {judgment}",
            "validation": {
                "ok": judgment == "passed",
                "issues": [],
                "warnings": [],
                "non_passing_verifications": [],
                "profile": "gates",
            },
            "risks": [],
            "follow_ups": [],
        }
        record.update(updates)
        return record

    def create_citation_files(self, run_id: str) -> None:
        run_dir = self.run_dir(run_id)
        (run_dir / "prompt.md").write_text("Implement.\n", encoding="utf-8")
        (run_dir / "events.jsonl").write_text(
            '{"type":"turn.completed"}\n', encoding="utf-8"
        )
        (run_dir / "handoff.md").write_text("Complete.\n", encoding="utf-8")

    def open_run(
        self,
        run_id: str,
        *scope: str,
        successor_of: str | None = None,
        record: object | None = None,
        environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        opening = self.opening_record(run_id) if record is None else record
        arguments = [
            "run-open",
            "--repo",
            str(self.repo),
            "--run-id",
            run_id,
        ]
        for item in scope or ("src/**",):
            arguments.extend(("--scope", item))
        arguments.extend(("--record-json", str(self.write_record(opening, "open"))))
        if successor_of is not None:
            arguments.extend(("--successor-of", successor_of))
        return self.command(*arguments, environment=environment)

    def append_record(
        self,
        run_id: str,
        record: object,
        *,
        environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return self.command(
            "journal-append",
            "--repo",
            str(self.repo),
            "--run-id",
            run_id,
            "--record-json",
            str(self.write_record(record, "append")),
            environment=environment,
        )

    def readmit(
        self,
        run_id: str,
        *scope: str,
        environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        arguments = [
            "run-readmit",
            "--repo",
            str(self.repo),
            "--run-id",
            run_id,
        ]
        for item in scope:
            arguments.extend(("--scope", item))
        return self.command(*arguments, environment=environment)

    def retire(
        self, run_id: str, *, environment: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        return self.command(
            "run-retire",
            "--repo",
            str(self.repo),
            "--run-id",
            run_id,
            environment=environment,
        )

    def close(
        self,
        run_id: str,
        *,
        judgment: str = "passed",
        record: object | None = None,
        environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        closing = self.closure_record(judgment) if record is None else record
        return self.command(
            "run-close",
            "--repo",
            str(self.repo),
            "--run-id",
            run_id,
            "--record-json",
            str(self.write_record(closing, "close")),
            environment=environment,
        )

    def coordination_snapshot(self) -> dict[str, tuple[str, object]]:
        snapshot: dict[str, tuple[str, object]] = {}
        for root in (self.repo / ".codex-orchestrator", self.repo / ".forge"):
            if not root.exists() and not root.is_symlink():
                continue
            for path in [root, *sorted(root.rglob("*"))]:
                relative = path.relative_to(self.repo).as_posix()
                details = path.lstat()
                if stat.S_ISLNK(details.st_mode):
                    snapshot[relative] = ("symlink", os.readlink(path))
                elif stat.S_ISREG(details.st_mode):
                    snapshot[relative] = ("file", path.read_bytes())
                elif stat.S_ISDIR(details.st_mode):
                    snapshot[relative] = ("directory", details.st_mode & 0o7777)
                else:
                    snapshot[relative] = ("other", details.st_mode)
        return snapshot

    def write_registry(self, entries: dict[str, tuple[str, ...]]) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "open_runs": [
                {"run_id": run_id, "scope": list(entries[run_id])}
                for run_id in sorted(entries, key=lambda value: value.encode("utf-8"))
            ],
            "schema_version": 1,
        }
        self.registry_path.write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )

    def prime_registry_lock(self) -> None:
        lock = self.repo / ".forge/tmp/run-registry.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.touch()

    def assert_absent_registry_node_collision(self, kind: str) -> None:
        self.runs_root.mkdir(parents=True)
        self.prime_registry_lock()
        candidate_id = f"run-absent-registry-{kind}"
        foreign_payload = f"foreign {kind} registry node\n".encode("utf-8")
        foreign_identity: list[tuple[int, int, int, int, int]] = []
        foreign_target: list[str] = []
        unreadable_handles: list[object] = []
        triggered = False
        real_link = journal.os.link

        def install_foreign_then_link(
            source: object,
            destination: object,
            *,
            src_dir_fd: int | None = None,
            dst_dir_fd: int | None = None,
            follow_symlinks: bool = True,
        ) -> None:
            nonlocal triggered
            if (
                not triggered
                and os.fspath(destination) == "run-registry.json"
                and os.fspath(source).endswith(".candidate")
            ):
                triggered = True
                if kind == "directory":
                    self.registry_path.mkdir()
                    (self.registry_path / "foreign-state").write_bytes(
                        foreign_payload
                    )
                elif kind in {"symlink", "broken-symlink"}:
                    target = self.root / f"{kind}-registry-target"
                    if kind == "symlink":
                        target.write_bytes(foreign_payload)
                    os.symlink(target, self.registry_path)
                    foreign_target.append(os.readlink(self.registry_path))
                elif kind == "unreadable-file":
                    handle = self.registry_path.open("w+b")
                    handle.write(foreign_payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                    os.chmod(self.registry_path, 0)
                    unreadable_handles.append(handle)
                    self.addCleanup(handle.close)
                else:
                    self.fail(f"unknown registry-node fixture {kind}")
                observed = self.registry_path.lstat()
                foreign_identity.append(
                    (
                        observed.st_dev,
                        observed.st_ino,
                        observed.st_mode,
                        observed.st_size,
                        observed.st_mtime_ns,
                    )
                )
            real_link(
                source,
                destination,
                src_dir_fd=src_dir_fd,
                dst_dir_fd=dst_dir_fd,
                follow_symlinks=follow_symlinks,
            )

        with self.api_environment(), mock.patch.object(
            journal.os,
            "link",
            side_effect=install_foreign_then_link,
        ):
            with self.assertRaises(journal.CoordinationRefusal) as caught:
                journal.open_run(
                    self.repo,
                    candidate_id,
                    [f"src/absent/{kind}/**"],
                    self.opening_record(candidate_id),
                )

        observed = self.registry_path.lstat()
        self.assertTrue(triggered)
        self.assertEqual(str(caught.exception), journal.REGISTRY_UPDATE_FAILED)
        self.assertEqual(
            (
                observed.st_dev,
                observed.st_ino,
                observed.st_mode,
                observed.st_size,
                observed.st_mtime_ns,
            ),
            foreign_identity[0],
        )
        if kind == "directory":
            self.assertTrue(stat.S_ISDIR(observed.st_mode))
            self.assertEqual(
                (self.registry_path / "foreign-state").read_bytes(),
                foreign_payload,
            )
        elif kind == "symlink":
            self.assertTrue(stat.S_ISLNK(observed.st_mode))
            self.assertEqual(os.readlink(self.registry_path), foreign_target[0])
            self.assertEqual(Path(foreign_target[0]).read_bytes(), foreign_payload)
        elif kind == "broken-symlink":
            self.assertTrue(stat.S_ISLNK(observed.st_mode))
            self.assertEqual(os.readlink(self.registry_path), foreign_target[0])
            self.assertFalse(Path(foreign_target[0]).exists())
        else:
            self.assertTrue(stat.S_ISREG(observed.st_mode))
            self.assertEqual(stat.S_IMODE(observed.st_mode), 0)
            handle = unreadable_handles[0]
            handle.seek(0)  # type: ignore[attr-defined]
            self.assertEqual(handle.read(), foreign_payload)  # type: ignore[attr-defined]
        self.assertFalse(self.run_dir(candidate_id).exists())
        self.assertEqual(list(self.runs_root.iterdir()), [])
        self.assertEqual(
            list(self.registry_path.parent.glob(".run-registry.json.*")), []
        )

    def valid_candidate(
        self, kind: str, *, run_id: str = "run-boundary"
    ) -> dict[str, object]:
        factories = {
            "run_started": lambda: self.opening_record(
                run_id, scope=["src/**"]
            ),
            "task": self.task_record,
            "execution": self.execution_record,
            "execution_result": self.execution_result_record,
            "verification": self.verification_record,
            "decision": self.decision_record,
            "run_closed": self.closure_record,
        }
        return copy.deepcopy(factories[kind]())

    def assert_invalid_candidate(
        self,
        candidate: object,
        detail: str | None,
        *,
        run_id: str = "run-boundary",
        prior_records: tuple[dict[str, object], ...] = (),
    ) -> None:
        with self.assertRaises(journal.CoordinationRefusal) as caught:
            journal._validate_proposed_record(
                candidate,
                run_id=run_id,
                repo_root=self.repo.resolve(),
                scope=("src/**",),
                prior_records=prior_records,
            )
        expected = journal.INVALID_JOURNAL_RECORD
        if detail is not None:
            expected += f": {detail}"
        self.assertEqual(str(caught.exception), expected)

    def assert_valid_candidate(
        self,
        candidate: object,
        *,
        run_id: str = "run-boundary",
        prior_records: tuple[dict[str, object], ...] = (),
    ) -> None:
        validated = journal._validate_proposed_record(
            candidate,
            run_id=run_id,
            repo_root=self.repo.resolve(),
            scope=("src/**",),
            prior_records=prior_records,
        )
        self.assertIs(validated, candidate)

    def plant_run_state(
        self,
        run_id: str,
        scope: tuple[str, ...],
        *,
        successor_of: str | None = None,
        retired: bool = False,
    ) -> None:
        run_dir = self.run_dir(run_id)
        run_dir.mkdir(parents=True)
        opening = self.opening_record(run_id, scope=list(scope))
        if successor_of is not None:
            opening["successor_of"] = successor_of
        records = [opening]
        if retired:
            records.append(
                {
                    "type": "decision",
                    "recorded_at": RECORDED_AT,
                    "id": "forge-run-retired",
                    "resolution": journal.RETIREMENT_RESOLUTION,
                }
            )
        self.journal_path(run_id).write_text(
            "".join(
                json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
                for record in records
            ),
            encoding="utf-8",
        )
        (run_dir / "owner").write_text(
            f"pid: {os.getpid()}\n"
            f"host: {socket.gethostname()}\n"
            f"started_at: {RECORDED_AT}\n",
            encoding="utf-8",
        )

    def proven_dead_pid(self) -> str:
        process = subprocess.Popen(
            [sys.executable, "-c", "pass"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        process.wait(timeout=10)
        self.assertIsNotNone(process.pid)
        try:
            os.kill(process.pid, 0)
        except ProcessLookupError:
            return str(process.pid)
        self.fail(f"short-lived fixture PID {process.pid} is unexpectedly still live")

    def test_all_seven_strict_minimum_record_types_append(self) -> None:
        opened = self.open_run("run-seven", "src/**")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        self.create_citation_files("run-seven")

        records = (
            self.task_record(),
            self.execution_record(),
            self.execution_result_record(),
            self.verification_record(),
            self.decision_record(future_extension={"schema": 2}),
        )
        for record in records:
            with self.subTest(record_type=record["type"]):
                appended = self.append_record("run-seven", record)
                self.assertEqual(appended.returncode, 0, appended.stderr)
        closed = self.close("run-seven")
        self.assertEqual(closed.returncode, 0, closed.stderr)

        landed = [
            json.loads(line)
            for line in self.journal_path("run-seven").read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(
            [record["type"] for record in landed],
            [
                "run_started",
                "task",
                "execution",
                "execution_result",
                "verification",
                "decision",
                "run_closed",
            ],
        )
        self.assertEqual(landed[-2]["future_extension"], {"schema": 2})

    def test_per_type_first_required_field_diagnostics_are_exact(self) -> None:
        opened = self.open_run("run-matrix", "src/**")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        self.create_citation_files("run-matrix")
        before = self.coordination_snapshot()

        cases: tuple[
            tuple[str, dict[str, object], str, str], ...
        ] = (
            (
                "run_started",
                self.opening_record("run-missing-start-id"),
                "run_id",
                "run_started.run_id is required",
            ),
            ("task", self.task_record(), "id", "task.id is required"),
            (
                "execution",
                self.execution_record(),
                "agent",
                "execution.agent is required",
            ),
            (
                "execution_result",
                self.execution_result_record(),
                "agent",
                "execution_result.agent is required",
            ),
            (
                "verification",
                self.verification_record(),
                "id",
                "verification.id is required",
            ),
            ("decision", self.decision_record(), "id", "decision.id is required"),
            (
                "run_closed",
                self.closure_record(),
                "judgment",
                "run_closed.judgment is required",
            ),
        )
        for kind, candidate, missing, detail in cases:
            with self.subTest(record_type=kind):
                candidate.pop(missing)
                if kind == "run_started":
                    refused = self.open_run(
                        "run-missing-start-id", "other/**", record=candidate
                    )
                    self.assertFalse(self.run_dir("run-missing-start-id").exists())
                elif kind == "run_closed":
                    refused = self.close("run-matrix", record=candidate)
                else:
                    refused = self.append_record("run-matrix", candidate)
                self.assertEqual(refused.returncode, 1)
                self.assertEqual(
                    refused.stderr,
                    f"forge: journal append refused — invalid journal record: {detail}\n",
                )
                self.assertEqual(self.coordination_snapshot(), before)

    def test_fr019_common_and_required_string_boundaries(self) -> None:
        kinds = (
            "run_started",
            "task",
            "execution",
            "execution_result",
            "verification",
            "decision",
            "run_closed",
        )
        for kind in kinds:
            with self.subTest(kind=kind, field="recorded_at", mutation="missing"):
                candidate = self.valid_candidate(kind)
                candidate.pop("recorded_at")
                self.assert_invalid_candidate(
                    candidate, f"{kind}.recorded_at is required"
                )
            for bad_value in (None, "", "2026-08-26T12:00:00+00:00"):
                with self.subTest(
                    kind=kind, field="recorded_at", bad_value=bad_value
                ):
                    candidate = self.valid_candidate(kind)
                    candidate["recorded_at"] = bad_value
                    self.assert_invalid_candidate(
                        candidate,
                        f"{kind}.recorded_at must be a valid UTC RFC-3339 "
                        "timestamp ending in Z",
                    )
            if kind != "run_started":
                for bad_value in (None, "", "invalid/run-id"):
                    with self.subTest(
                        kind=kind, field="run_id", bad_value=bad_value
                    ):
                        candidate = self.valid_candidate(kind)
                        candidate["run_id"] = bad_value
                        self.assert_invalid_candidate(
                            candidate, f"{kind}.run_id must be a valid run ID"
                        )
                candidate = self.valid_candidate(kind)
                candidate["run_id"] = "run-somewhere-else"
                self.assert_invalid_candidate(
                    candidate, f"{kind}.run_id must match target run"
                )

        ordinary = "must be nonempty"
        fields: dict[str, tuple[tuple[str, str, str], ...]] = {
            "run_started": (
                ("run_id", "must be a valid run ID", "must be a valid run ID"),
                ("goal", "must be a string", ordinary),
                ("repo", "must be a string", "must be an absolute path"),
                ("repo_head", "must be a string", "must be a full Git object ID"),
                ("plugin_ref", "must be a string", ordinary),
            ),
            "task": (
                ("id", "must be a string", ordinary),
                (
                    "status",
                    "must be a string",
                    "must be one of active, complete, blocked, failed",
                ),
                ("goal", "must be a string", ordinary),
            ),
            "execution": tuple(
                (field, "must be a string", ordinary)
                for field in (
                    "agent",
                    "task",
                    "provider",
                    "role",
                    "mode",
                    "model",
                    "effort",
                )
            )
            + (
                ("execution", "must be a string", "must match execution-NN"),
                ("worktree", "must be a string", "must be an absolute path"),
                ("head", "must be a string", "must be a full Git object ID"),
                ("prompt", "must be a string", ordinary),
                ("handoff", "must be a string", ordinary),
                ("event_source", "must be a string", ordinary),
            ),
            "execution_result": (
                ("agent", "must be a string", ordinary),
                ("task", "must be a string", ordinary),
                ("summary", "must be a string", ordinary),
                ("execution", "must be a string", "must match execution-NN"),
                (
                    "status",
                    "must be a string",
                    "must be one of complete, blocked, failed",
                ),
                ("handoff", "must be a string", ordinary),
            ),
            "verification": tuple(
                (field, "must be a string", ordinary)
                for field in (
                    "id",
                    "task",
                    "criterion",
                    "method",
                    "check",
                    "observation",
                )
            )
            + (
                (
                    "result",
                    "must be a string",
                    "must be one of passed, failed, inconclusive, skipped",
                ),
            ),
            "decision": (
                ("id", "must be a string", ordinary),
                ("resolution", "must be a string", ordinary),
            ),
            "run_closed": (
                (
                    "judgment",
                    "must be a string",
                    "must be one of passed, blocked",
                ),
                ("summary", "must be a string", ordinary),
            ),
        }
        for kind, definitions in fields.items():
            for field, wrong_type, empty in definitions:
                with self.subTest(kind=kind, field=field, mutation="missing"):
                    candidate = self.valid_candidate(kind)
                    candidate.pop(field)
                    self.assert_invalid_candidate(
                        candidate, f"{kind}.{field} is required"
                    )
                with self.subTest(kind=kind, field=field, mutation="wrong-type"):
                    candidate = self.valid_candidate(kind)
                    candidate[field] = None
                    self.assert_invalid_candidate(
                        candidate, f"{kind}.{field} {wrong_type}"
                    )
                with self.subTest(kind=kind, field=field, mutation="empty"):
                    candidate = self.valid_candidate(kind)
                    candidate[field] = ""
                    self.assert_invalid_candidate(candidate, f"{kind}.{field} {empty}")

    def test_fr019_format_enum_repository_and_scope_boundaries(self) -> None:
        format_cases: tuple[tuple[str, str, object, str], ...] = (
            (
                "run_started",
                "run_id",
                "invalid/run-id",
                "must be a valid run ID",
            ),
            (
                "run_started",
                "run_id",
                "run-different",
                "must match target run",
            ),
            (
                "run_started",
                "repo",
                "relative/repo",
                "must be an absolute path",
            ),
            (
                "run_started",
                "repo",
                str(self.root.resolve()),
                "must match target repository",
            ),
            (
                "run_started",
                "repo_head",
                "f" * 39,
                "must be a full Git object ID",
            ),
            (
                "execution",
                "execution",
                "execution-1",
                "must match execution-NN",
            ),
            (
                "execution_result",
                "execution",
                "execution-001",
                "must match execution-NN",
            ),
            (
                "execution",
                "worktree",
                "relative/worktree",
                "must be an absolute path",
            ),
            (
                "execution",
                "head",
                "A" * 40,
                "must be a full Git object ID",
            ),
        )
        for kind, field, bad_value, requirement in format_cases:
            with self.subTest(kind=kind, field=field, bad_value=bad_value):
                candidate = self.valid_candidate(kind)
                candidate[field] = bad_value
                self.assert_invalid_candidate(
                    candidate, f"{kind}.{field} {requirement}"
                )

        enum_cases = {
            "task": ("status", ("active", "complete", "blocked", "failed")),
            "execution_result": (
                "status",
                ("complete", "blocked", "failed"),
            ),
            "verification": (
                "result",
                ("passed", "failed", "inconclusive", "skipped"),
            ),
            "run_closed": ("judgment", ("passed", "blocked")),
        }
        for kind, (field, allowed) in enum_cases.items():
            for value in allowed:
                with self.subTest(kind=kind, field=field, allowed=value):
                    candidate = self.valid_candidate(kind)
                    candidate[field] = value
                    if kind == "execution_result" and value != "complete":
                        candidate.pop("handoff")
                    self.assert_valid_candidate(candidate)
            candidate = self.valid_candidate(kind)
            candidate[field] = "not-an-enum-member"
            self.assert_invalid_candidate(
                candidate,
                f"{kind}.{field} must be one of {', '.join(allowed)}",
            )

        scope_cases: tuple[tuple[object, str], ...] = (
            (None, "run_started.scope must be an array"),
            ([], "run_started.scope must be nonempty"),
            (
                ["src/ok/**", ""],
                "run_started.scope[1] must be a nonempty string",
            ),
            (
                ["src/z/**", "src/a/**"],
                "run_started.scope must be a canonical nonempty admitted scope",
            ),
            (
                ["../escape"],
                "run_started.scope must be a canonical nonempty admitted scope",
            ),
        )
        candidate = self.valid_candidate("run_started")
        candidate.pop("scope")
        self.assert_invalid_candidate(candidate, "run_started.scope is required")
        for value, detail in scope_cases:
            with self.subTest(field="scope", value=value):
                candidate = self.valid_candidate("run_started")
                candidate["scope"] = value
                self.assert_invalid_candidate(candidate, detail)

        for value, requirement in (
            (["../escape"], "must be a positive repository-relative Git pathspec"),
            (["elsewhere/**"], "must be contained by admitted scope"),
        ):
            candidate = self.valid_candidate("task")
            candidate["files"] = value
            self.assert_invalid_candidate(
                candidate, f"task.files[0] {requirement}"
            )

    def test_fr019_all_arrays_and_nested_validation_boundaries(self) -> None:
        arrays: tuple[tuple[str, str, bool, bool, list[str]], ...] = (
            ("run_started", "repo_status", True, False, [" M file", ""]),
            ("task", "acceptance", True, True, ["criterion", ""]),
            ("task", "files", True, True, ["src/valid.py", ""]),
            (
                "execution_result",
                "files_changed",
                True,
                False,
                ["src/valid.py", ""],
            ),
            ("execution_result", "caveats", True, False, ["none", ""]),
            ("verification", "evidence", False, False, ["proof.txt", ""]),
            ("decision", "basis", False, False, ["decision-00", ""]),
            ("run_closed", "risks", True, False, ["risk", ""]),
            ("run_closed", "follow_ups", True, False, ["follow-up", ""]),
        )
        for kind, field, required, nonempty, bad_members in arrays:
            with self.subTest(kind=kind, field=field, mutation="missing"):
                candidate = self.valid_candidate(kind)
                candidate.pop(field, None)
                if required:
                    self.assert_invalid_candidate(
                        candidate, f"{kind}.{field} is required"
                    )
                else:
                    self.assert_valid_candidate(candidate)
            with self.subTest(kind=kind, field=field, mutation="wrong-type"):
                candidate = self.valid_candidate(kind)
                candidate[field] = None
                self.assert_invalid_candidate(
                    candidate, f"{kind}.{field} must be an array"
                )
            with self.subTest(kind=kind, field=field, mutation="empty"):
                candidate = self.valid_candidate(kind)
                candidate[field] = []
                if nonempty:
                    self.assert_invalid_candidate(
                        candidate, f"{kind}.{field} must be nonempty"
                    )
                else:
                    self.assert_valid_candidate(candidate)
            with self.subTest(kind=kind, field=field, mutation="member-index"):
                candidate = self.valid_candidate(kind)
                candidate[field] = bad_members
                self.assert_invalid_candidate(
                    candidate,
                    f"{kind}.{field}[1] must be a nonempty string",
                )

        validation_fields = (
            "issues",
            "warnings",
            "non_passing_verifications",
        )
        candidate = self.valid_candidate("run_closed")
        candidate.pop("validation")
        self.assert_invalid_candidate(candidate, "run_closed.validation is required")
        candidate = self.valid_candidate("run_closed")
        candidate["validation"] = []
        self.assert_invalid_candidate(
            candidate, "run_closed.validation must be an object"
        )
        for field in validation_fields:
            with self.subTest(validation_field=field, mutation="missing"):
                candidate = self.valid_candidate("run_closed")
                validation = candidate["validation"]
                assert isinstance(validation, dict)
                validation.pop(field)
                self.assert_invalid_candidate(
                    candidate, f"run_closed.validation.{field} is required"
                )
            with self.subTest(validation_field=field, mutation="wrong-type"):
                candidate = self.valid_candidate("run_closed")
                validation = candidate["validation"]
                assert isinstance(validation, dict)
                validation[field] = None
                self.assert_invalid_candidate(
                    candidate, f"run_closed.validation.{field} must be an array"
                )
        for field in ("issues", "warnings"):
            candidate = self.valid_candidate("run_closed")
            validation = candidate["validation"]
            assert isinstance(validation, dict)
            validation[field] = ["first", ""]
            self.assert_invalid_candidate(
                candidate,
                f"run_closed.validation.{field}[1] must be a nonempty string",
            )

        candidate = self.valid_candidate("run_closed")
        validation = candidate["validation"]
        assert isinstance(validation, dict)
        validation.pop("ok")
        self.assert_invalid_candidate(candidate, "run_closed.validation.ok is required")
        for bad_value in (None, 0, 1, "true"):
            candidate = self.valid_candidate("run_closed")
            validation = candidate["validation"]
            assert isinstance(validation, dict)
            validation["ok"] = bad_value
            self.assert_invalid_candidate(
                candidate, "run_closed.validation.ok must be Boolean"
            )
        candidate = self.valid_candidate("run_closed")
        validation = candidate["validation"]
        assert isinstance(validation, dict)
        validation.pop("profile")
        self.assert_invalid_candidate(
            candidate, "run_closed.validation.profile is required"
        )
        for bad_value in (None, "", "default"):
            candidate = self.valid_candidate("run_closed")
            validation = candidate["validation"]
            assert isinstance(validation, dict)
            validation["profile"] = bad_value
            self.assert_invalid_candidate(
                candidate, "run_closed.validation.profile must be exactly gates"
            )

    def test_fr019_inheritance_events_handoff_optionals_and_extensions(self) -> None:
        prior = self.task_record(id="task-inherit")
        terminal = {
            "type": "task",
            "recorded_at": RECORDED_AT,
            "id": "task-inherit",
            "status": "complete",
        }
        self.assert_valid_candidate(terminal, prior_records=(prior,))

        for status in ("active", "complete"):
            with self.subTest(inheritance="missing-prior", status=status):
                candidate = dict(terminal, status=status)
                self.assert_invalid_candidate(candidate, "task.goal is required")
        candidate = dict(terminal, id="task-other")
        self.assert_invalid_candidate(
            candidate, "task.goal is required", prior_records=(prior,)
        )
        older = self.task_record(id="task-inherit")
        newest_sparse = {
            "type": "task",
            "recorded_at": RECORDED_AT,
            "id": "task-inherit",
            "status": "complete",
        }
        self.assert_invalid_candidate(
            terminal,
            "task.goal is required",
            prior_records=(older, newest_sparse),
        )
        for field, bad_value, requirement in (
            ("goal", None, "must be a string"),
            ("goal", "", "must be nonempty"),
            ("acceptance", None, "must be an array"),
            ("acceptance", [], "must be nonempty"),
            ("files", None, "must be an array"),
            ("files", [], "must be nonempty"),
        ):
            candidate = dict(terminal)
            candidate[field] = bad_value
            self.assert_invalid_candidate(
                candidate,
                f"task.{field} {requirement}",
                prior_records=(prior,),
            )

        execution = self.valid_candidate("execution")
        execution.pop("events")
        self.assert_invalid_candidate(execution, "execution.events is required")
        execution = self.valid_candidate("execution")
        execution["events"] = ""
        self.assert_invalid_candidate(execution, "execution.events must be nonempty")
        execution = self.valid_candidate("execution")
        execution["events"] = None
        self.assert_invalid_candidate(execution, "execution.events must be a string")
        for events in (None, ""):
            execution = self.valid_candidate("execution")
            execution["event_source"] = "manual"
            if events is None:
                execution.pop("events")
            else:
                execution["events"] = events
            self.assert_valid_candidate(execution)

        for status in ("blocked", "failed"):
            result = self.valid_candidate("execution_result")
            result["status"] = status
            result.pop("handoff")
            self.assert_valid_candidate(result)
            result["handoff"] = ""
            self.assert_valid_candidate(result)
        result = self.valid_candidate("execution_result")
        result.pop("handoff")
        self.assert_invalid_candidate(result, "execution_result.handoff is required")
        result = self.valid_candidate("execution_result")
        result["handoff"] = None
        self.assert_invalid_candidate(
            result, "execution_result.handoff must be a string"
        )
        result = self.valid_candidate("execution_result")
        result["handoff"] = ""
        self.assert_invalid_candidate(
            result, "execution_result.handoff must be nonempty"
        )

        for field in ("task", "finding", "outcome", "risk"):
            decision = self.valid_candidate("decision")
            decision[field] = None
            self.assert_invalid_candidate(
                decision, f"decision.{field} must be a string"
            )
            decision[field] = ""
            self.assert_valid_candidate(decision)
        opening = self.valid_candidate("run_started")
        opening["successor_of"] = None
        self.assert_invalid_candidate(
            opening, "run_started.successor_of must be a valid run ID"
        )
        opening["successor_of"] = "run-predecessor"
        self.assert_valid_candidate(opening)

        for kind in (
            "run_started",
            "task",
            "execution",
            "execution_result",
            "verification",
            "decision",
            "run_closed",
        ):
            with self.subTest(kind=kind, extension="unknown"):
                candidate = self.valid_candidate(kind)
                candidate["future_extension"] = {"schema": 2}
                if kind == "run_closed":
                    validation = candidate["validation"]
                    assert isinstance(validation, dict)
                    validation["future_nested"] = True
                self.assert_valid_candidate(candidate)

    def test_first_failure_examples_and_envelope_literal_are_exact(self) -> None:
        opened = self.open_run("run-first", "src/**")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        self.create_citation_files("run-first")
        before = self.coordination_snapshot()

        candidates: tuple[tuple[object, str], ...] = (
            (
                self.task_record(goal=None, acceptance=[], files=[]),
                "forge: journal append refused — invalid journal record: "
                "task.goal must be a string\n",
            ),
            (
                self.execution_record(execution="secret-invalid-execution", worktree=""),
                "forge: journal append refused — invalid journal record: "
                "execution.execution must match execution-NN\n",
            ),
            (
                self.verification_record(result="secret-invalid-result"),
                "forge: journal append refused — invalid journal record: "
                "verification.result must be one of passed, failed, inconclusive, skipped\n",
            ),
            (
                {"recorded_at": RECORDED_AT},
                "forge: journal append refused — invalid journal record\n",
            ),
            ([], "forge: journal append refused — invalid journal record\n"),
        )
        for index, (candidate, expected) in enumerate(candidates):
            with self.subTest(case=index):
                refused = self.append_record("run-first", candidate)
                self.assertEqual(refused.returncode, 1)
                self.assertEqual(refused.stderr, expected)
                self.assertNotIn("secret-invalid", refused.stderr)
                self.assertEqual(self.coordination_snapshot(), before)

    def test_array_members_fail_at_the_first_ascending_index(self) -> None:
        opened = self.open_run("run-array-order", "src/**")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        candidate = self.task_record(
            acceptance=["first valid criterion", "", "secret-later-value"],
            files=["not-in-scope/**"],
        )
        before = self.coordination_snapshot()

        refused = self.append_record("run-array-order", candidate)

        self.assertEqual(refused.returncode, 1)
        self.assertEqual(
            refused.stderr,
            "forge: journal append refused — invalid journal record: "
            "task.acceptance[1] must be a nonempty string\n",
        )
        self.assertNotIn("secret-later-value", refused.stderr)
        self.assertNotIn("not-in-scope", refused.stderr)
        self.assertEqual(self.coordination_snapshot(), before)

    def test_reserved_lifecycle_decisions_require_commands_and_preserve_bytes(self) -> None:
        opened = self.open_run("run-lifecycle-append", "src/**")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        before = self.coordination_snapshot()
        candidates = (
            {
                "type": "decision",
                "recorded_at": RECORDED_AT,
                "id": "forge-run-retired",
                "resolution": journal.RETIREMENT_RESOLUTION,
            },
            {
                "type": "decision",
                "recorded_at": RECORDED_AT,
                "id": "forge-scope-readmission-0123456789abcdef0123456789abcdef",
                "resolution": journal.READMISSION_RESOLUTION,
                "scope": ["src/**"],
            },
        )

        for candidate in candidates:
            with self.subTest(decision_id=candidate["id"]):
                refused = self.append_record("run-lifecycle-append", candidate)
                self.assertEqual(refused.returncode, 1)
                self.assertEqual(refused.stdout, "")
                self.assertEqual(
                    refused.stderr,
                    "forge: journal append refused — lifecycle command required\n",
                )
                self.assertEqual(self.coordination_snapshot(), before)

    def test_sparse_history_reads_unchanged_but_same_new_shape_refuses(self) -> None:
        opened = self.open_run("run-legacy-sparse", "src/**")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        sparse = {
            "type": "task",
            "recorded_at": RECORDED_AT,
            "id": "legacy-task",
            "status": "complete",
        }
        journal_path = self.journal_path("run-legacy-sparse")
        with journal_path.open("ab") as stream:
            stream.write((json.dumps(sparse) + "\n").encode("utf-8"))
        before = self.coordination_snapshot()

        with mock.patch.object(
            journal,
            "_validate_proposed_record",
            side_effect=AssertionError("historical reader invoked append validator"),
        ):
            scanned = journal._scan_run(self.run_dir("run-legacy-sparse"))
            records, _issues = journal.read_journal(journal_path)
            payload = journal.validate_run(self.run_dir("run-legacy-sparse"))

        self.assertEqual(scanned.run_id, "run-legacy-sparse")
        parsed_sparse = dict(records[-1])
        self.assertEqual(parsed_sparse.pop("_line"), 2)
        self.assertEqual(parsed_sparse, sparse)
        self.assertIsInstance(payload, dict)
        self.assertEqual(self.coordination_snapshot(), before)

        refused = self.append_record("run-legacy-sparse", sparse)
        self.assertEqual(refused.returncode, 1)
        self.assertEqual(
            refused.stderr,
            "forge: journal append refused — invalid journal record: "
            "task.goal is required\n",
        )
        self.assertEqual(self.coordination_snapshot(), before)

    def test_invalid_candidate_precedes_stale_owner_takeover_and_changes_no_bytes(self) -> None:
        opened = self.open_run("run-stale", "src/**")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        owner = self.run_dir("run-stale") / "owner"
        dead_pid = self.proven_dead_pid()
        owner.write_text(
            f"pid: {dead_pid}\n"
            f"host: {socket.gethostname()}\n"
            f"started_at: {RECORDED_AT}\n",
            encoding="utf-8",
        )
        before = self.coordination_snapshot()

        invalid = self.decision_record()
        invalid.pop("resolution")
        refused = self.append_record("run-stale", invalid)

        self.assertEqual(refused.returncode, 1)
        self.assertEqual(
            refused.stderr,
            "forge: journal append refused — invalid journal record: "
            "decision.resolution is required\n",
        )
        self.assertEqual(self.coordination_snapshot(), before)
        self.assertTrue(
            owner.read_text(encoding="utf-8").startswith(
                f"pid: {dead_pid}\n"
            )
        )

    def test_unserializable_candidate_precedes_stale_takeover_and_changes_no_bytes(self) -> None:
        opened = self.open_run("run-stale-serialization", "src/**")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        owner = self.run_dir("run-stale-serialization") / "owner"
        dead_pid = self.proven_dead_pid()
        owner.write_text(
            f"pid: {dead_pid}\n"
            f"host: {socket.gethostname()}\n"
            f"started_at: {RECORDED_AT}\n",
            encoding="utf-8",
        )
        candidate = self.decision_record(future_extension=object())
        before = self.coordination_snapshot()

        with self.api_environment():
            with self.assertRaises(journal.CoordinationRefusal) as caught:
                journal.append_run_record(
                    self.repo, "run-stale-serialization", candidate
                )

        self.assertEqual(str(caught.exception), journal.INVALID_JOURNAL_RECORD)
        self.assertEqual(self.coordination_snapshot(), before)
        self.assertTrue(
            owner.read_text(encoding="utf-8").startswith(f"pid: {dead_pid}\n")
        )

    def test_foreign_owner_classification_precedes_candidate_schema(self) -> None:
        opened = self.open_run("run-foreign", "src/**")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        owner = self.run_dir("run-foreign") / "owner"
        foreign_host = f"foreign-{socket.gethostname()}"
        owner.write_text(
            f"pid: 42\nhost: {foreign_host}\nstarted_at: {RECORDED_AT}\n",
            encoding="utf-8",
        )
        before = self.coordination_snapshot()

        refused = self.append_record("run-foreign", self.decision_record(resolution=None))

        self.assertEqual(refused.returncode, 1)
        self.assertEqual(
            refused.stderr,
            "forge: journal append refused — run run-foreign has live owner "
            f"42@{foreign_host}\n",
        )
        self.assertEqual(self.coordination_snapshot(), before)

    def test_engine_lifecycle_owner_classification_precedes_schema(self) -> None:
        opened = self.open_run("run-engine-owner-order", "src/engine/**")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        owner_path = self.run_dir("run-engine-owner-order") / "owner"
        original_owner = owner_path.read_bytes()
        operations = (
            (
                "readmit",
                lambda: journal.readmit_run(
                    self.repo,
                    "run-engine-owner-order",
                    ["src/engine/readmitted/**"],
                ),
            ),
            (
                "retire",
                lambda: journal.retire_run(self.repo, "run-engine-owner-order"),
            ),
        )

        for operation, invoke in operations:
            owner_path.write_bytes(b"malformed owner\n")
            before = self.coordination_snapshot()
            validator = mock.Mock(
                side_effect=AssertionError(
                    f"{operation} schema validation ran before owner classification"
                )
            )
            try:
                with self.subTest(operation=operation), self.api_environment(), mock.patch.object(
                    journal, "_validate_proposed_record", validator
                ):
                    with self.assertRaises(journal.CoordinationRefusal) as caught:
                        invoke()
                    self.assertEqual(
                        str(caught.exception),
                        "forge: journal append refused — owner record missing or "
                        "malformed for run run-engine-owner-order",
                    )
                    validator.assert_not_called()
                    self.assertEqual(self.coordination_snapshot(), before)
            finally:
                owner_path.write_bytes(original_owner)

    def test_engine_lifecycle_envelope_is_built_before_session_identity(self) -> None:
        opened = self.open_run("run-engine-envelope-order", "src/engine/**")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        missing_pid = dict(self.env)
        missing_pid.pop("FORGE_SESSION_PID", None)
        operations = (
            (
                "readmit",
                lambda: journal.readmit_run(
                    self.repo,
                    "run-engine-envelope-order",
                    ["src/engine/readmitted/**"],
                ),
                journal.READMISSION_RESOLUTION,
            ),
            (
                "retire",
                lambda: journal.retire_run(self.repo, "run-engine-envelope-order"),
                journal.RETIREMENT_RESOLUTION,
            ),
        )

        for operation, invoke, expected_resolution in operations:
            seen: list[object] = []

            def refuse_generated_envelope(record: object) -> dict[str, object]:
                seen.append(copy.deepcopy(record))
                raise journal.CoordinationRefusal(journal.INVALID_JOURNAL_RECORD)

            before = self.coordination_snapshot()
            with self.subTest(operation=operation), mock.patch.dict(
                os.environ, missing_pid, clear=True
            ), mock.patch.object(
                journal,
                "_validate_record_envelope",
                side_effect=refuse_generated_envelope,
            ):
                with self.assertRaises(journal.CoordinationRefusal) as caught:
                    invoke()
            self.assertEqual(str(caught.exception), journal.INVALID_JOURNAL_RECORD)
            self.assertEqual(len(seen), 1)
            self.assertIsInstance(seen[0], dict)
            self.assertEqual(seen[0]["type"], "decision")  # type: ignore[index]
            self.assertEqual(
                seen[0]["resolution"],  # type: ignore[index]
                expected_resolution,
            )
            self.assertEqual(self.coordination_snapshot(), before)

    def test_citation_controls_precede_current_session_identity_refusals(self) -> None:
        opened = self.open_run("run-citation-session", "src/**")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        outside = str((self.root / "outside-citation.txt").resolve())
        candidates = (
            (
                self.execution_record(prompt=outside),
                "forge: journal append refused — record cites path outside run or "
                f"repository: execution.prompt: {outside}",
            ),
            (
                self.decision_record(
                    id="correction-invalid",
                    resolution="citation-correction:\nnot a directive",
                ),
                "forge: journal append refused — invalid citation correction",
            ),
        )
        missing = dict(self.env)
        missing.pop("FORGE_SESSION_PID", None)
        malformed = dict(self.env, FORGE_SESSION_PID="not-a-pid")
        dead = dict(self.env, FORGE_SESSION_PID=self.proven_dead_pid())
        unverifiable = dict(self.env, FORGE_SESSION_PID=str(sys.maxsize + 1))

        for identity, environment in (
            ("missing", missing),
            ("malformed", malformed),
            ("dead", dead),
            ("os-unverifiable", unverifiable),
        ):
            for candidate, expected in candidates:
                with self.subTest(identity=identity, candidate=candidate["type"]):
                    before = self.coordination_snapshot()
                    with mock.patch.dict(os.environ, environment, clear=True):
                        with self.assertRaises(journal.CoordinationRefusal) as caught:
                            journal.append_run_record(
                                self.repo, "run-citation-session", candidate
                            )
                    self.assertEqual(str(caught.exception), expected)
                    self.assertEqual(self.coordination_snapshot(), before)

    def test_current_session_identity_literals_are_exact_and_nonmutating(self) -> None:
        opened = self.open_run("run-session-exact", "src/**")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        missing = dict(self.env)
        missing.pop("FORGE_SESSION_PID", None)
        cases = (
            (
                "missing",
                missing,
                "forge: FORGE_SESSION_PID must be exported as a positive base-10 integer",
            ),
            (
                "malformed-present",
                dict(self.env, FORGE_SESSION_PID="12x"),
                "forge: FORGE_SESSION_PID must be exported as a positive base-10 integer",
            ),
            (
                "dead",
                dict(self.env, FORGE_SESSION_PID=self.proven_dead_pid()),
                "forge: FORGE_SESSION_PID does not name a live same-host session owner",
            ),
            (
                "os-unverifiable",
                dict(self.env, FORGE_SESSION_PID=str(sys.maxsize + 1)),
                "forge: FORGE_SESSION_PID does not name a live same-host session owner",
            ),
        )
        candidate = self.decision_record(id="session-identity-probe")
        for label, environment, expected in cases:
            with self.subTest(identity=label):
                before = self.coordination_snapshot()
                with mock.patch.dict(os.environ, environment, clear=True):
                    with self.assertRaises(journal.CoordinationRefusal) as caught:
                        journal.append_run_record(
                            self.repo, "run-session-exact", candidate
                        )
                self.assertEqual(str(caught.exception), expected)
                self.assertEqual(self.coordination_snapshot(), before)

    def test_citation_controls_precede_recorded_owner_classification(self) -> None:
        opened = self.open_run("run-citation-owner", "src/**")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        owner_path = self.run_dir("run-citation-owner") / "owner"
        original_owner = owner_path.read_bytes()
        outside = str((self.root / "outside-owner-citation.txt").resolve())
        candidates = (
            (
                self.verification_record(evidence=[outside]),
                "forge: journal append refused — record cites path outside run or "
                f"repository: verification.evidence[0]: {outside}",
            ),
            (
                self.decision_record(
                    id="correction-owner-invalid",
                    resolution="citation-correction:\nnot a directive",
                ),
                "forge: journal append refused — invalid citation correction",
            ),
            (
                self.decision_record(
                    id="correction-owner-absent",
                    resolution=(
                        "citation-correction:\n"
                        "decision-absent basis[0]: corrected/path.md"
                    ),
                ),
                "forge: journal append refused — citation correction target does not exist",
            ),
        )
        foreign_host = f"foreign-{socket.gethostname()}"
        owner_cases = (
            (
                "foreign",
                (
                    f"pid: 42\nhost: {foreign_host}\n"
                    f"started_at: {RECORDED_AT}\n"
                ).encode("utf-8"),
                "forge: journal append refused — run run-citation-owner has live owner "
                f"42@{foreign_host}",
            ),
            (
                "malformed",
                b"malformed owner\n",
                "forge: journal append refused — owner record missing or malformed for "
                "run run-citation-owner",
            ),
        )
        for owner_kind, owner_bytes, owner_refusal in owner_cases:
            owner_path.write_bytes(owner_bytes)
            try:
                for candidate, expected in candidates:
                    with self.subTest(owner=owner_kind, candidate=candidate["id"]):
                        before = self.coordination_snapshot()
                        with self.api_environment():
                            with self.assertRaises(
                                journal.CoordinationRefusal
                            ) as caught:
                                journal.append_run_record(
                                    self.repo, "run-citation-owner", candidate
                                )
                        self.assertEqual(str(caught.exception), expected)
                        self.assertEqual(self.coordination_snapshot(), before)

                before = self.coordination_snapshot()
                with self.api_environment():
                    with self.assertRaises(journal.CoordinationRefusal) as caught:
                        journal.append_run_record(
                            self.repo,
                            "run-citation-owner",
                            self.decision_record(id="owner-reachability-probe"),
                        )
                self.assertEqual(str(caught.exception), owner_refusal)
                self.assertEqual(self.coordination_snapshot(), before)
            finally:
                owner_path.write_bytes(original_owner)

    def test_new_write_validator_control_is_load_bearing(self) -> None:
        opened = self.open_run("run-validator-control", "src/**")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        malformed = {
            "type": "decision",
            "recorded_at": RECORDED_AT,
            "id": "malformed-without-resolution",
        }
        before = self.journal_path("run-validator-control").read_bytes()

        with self.api_environment(), mock.patch.object(
            journal, "NEW_WRITE_VALIDATION_CONTROLS", frozenset()
        ):
            journal.append_run_record(self.repo, "run-validator-control", malformed)

        after = self.journal_path("run-validator-control").read_bytes()
        self.assertNotEqual(after, before)
        self.assertEqual(json.loads(after.splitlines()[-1]), malformed)

    def test_dead_or_unverifiable_session_pid_refuses_every_coordination_entry(self) -> None:
        opened = self.open_run("run-live", "src/**")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        dead_env = dict(self.env)
        dead_env["FORGE_SESSION_PID"] = self.proven_dead_pid()
        before = self.coordination_snapshot()
        expected = (
            "forge: FORGE_SESSION_PID does not name a live same-host session owner\n"
        )
        cases = (
            self.open_run(
                "run-dead", "dead/**", environment=dead_env
            ),
            self.append_record(
                "run-live", self.decision_record(id="dead-append"), environment=dead_env
            ),
            self.readmit("run-live", "src/**", environment=dead_env),
            self.retire("run-live", environment=dead_env),
            self.close("run-live", environment=dead_env),
        )
        for result in cases:
            with self.subTest(arguments=result.args[2] if len(result.args) > 2 else result.args):
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stderr, expected)
                self.assertEqual(result.stdout, "")
                self.assertEqual(self.coordination_snapshot(), before)
        self.assertFalse(self.run_dir("run-dead").exists())

    def test_invalid_session_pid_literal_is_retained(self) -> None:
        bad_env = dict(self.env)
        bad_env.pop("FORGE_SESSION_PID", None)
        result = self.open_run("run-no-session", "src/**", environment=bad_env)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            result.stderr,
            "forge: FORGE_SESSION_PID must be exported as a positive base-10 integer\n",
        )
        self.assertFalse((self.repo / ".codex-orchestrator").exists())
        self.assertFalse((self.repo / ".forge").exists())

    def test_live_session_identity_is_stable_across_fresh_cli_shells(self) -> None:
        opened = self.open_run("run-fresh-shells", "src/fresh/**")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        owner_path = self.run_dir("run-fresh-shells") / "owner"
        owner_before = owner_path.read_bytes()
        self.assertTrue(owner_before.startswith(f"pid: {os.getpid()}\n".encode()))

        appended = self.append_record(
            "run-fresh-shells", self.decision_record(id="fresh-shell-append")
        )
        self.assertEqual(appended.returncode, 0, appended.stderr)
        readmitted = self.readmit("run-fresh-shells", "src/fresh/new/**")
        self.assertEqual(readmitted.returncode, 0, readmitted.stderr)
        closed = self.close("run-fresh-shells")
        self.assertEqual(closed.returncode, 0, closed.stderr)

        self.assertEqual(owner_path.read_bytes(), owner_before)

    def test_operation_specific_invalid_id_and_missing_run_literals(self) -> None:
        bad_id = "untrusted/id"
        invalid_cases = (
            (
                self.open_run(bad_id, "src/**", record=self.opening_record("safe-id")),
                "new run",
            ),
            (self.append_record(bad_id, self.decision_record()), "journal append"),
            (self.readmit(bad_id, "src/**"), "run readmit"),
            (self.close(bad_id), "run close"),
            (self.retire(bad_id), "run retire"),
        )
        for result, operation in invalid_cases:
            with self.subTest(operation=operation):
                self.assertEqual(result.returncode, 1)
                self.assertEqual(
                    result.stderr, f"forge: {operation} refused — invalid run id\n"
                )
                self.assertNotIn(bad_id, result.stderr)

        missing_cases = (
            (self.append_record("run-absent", self.decision_record()), "journal append"),
            (self.readmit("run-absent", "src/**"), "run readmit"),
            (self.close("run-absent"), "run close"),
            (self.retire("run-absent"), "run retire"),
        )
        for result, operation in missing_cases:
            with self.subTest(operation=operation):
                self.assertEqual(result.returncode, 1)
                self.assertEqual(
                    result.stderr,
                    f"forge: {operation} refused — run run-absent does not exist\n",
                )

    def test_operation_specific_repository_unavailable_literals(self) -> None:
        missing_repo = self.root / "missing-repository"
        opening = self.write_record(self.opening_record("run-repo-missing"), "missing-repo")
        decision = self.write_record(self.decision_record(), "missing-repo")
        closing = self.write_record(self.closure_record(), "missing-repo")
        cases = (
            (
                self.command(
                    "run-open",
                    "--repo",
                    str(missing_repo),
                    "--run-id",
                    "run-repo-missing",
                    "--scope",
                    "src/**",
                    "--record-json",
                    str(opening),
                ),
                "new run",
            ),
            (
                self.command(
                    "journal-append",
                    "--repo",
                    str(missing_repo),
                    "--run-id",
                    "run-repo-missing",
                    "--record-json",
                    str(decision),
                ),
                "journal append",
            ),
            (
                self.command(
                    "run-readmit",
                    "--repo",
                    str(missing_repo),
                    "--run-id",
                    "run-repo-missing",
                    "--scope",
                    "src/**",
                ),
                "run readmit",
            ),
            (
                self.command(
                    "run-close",
                    "--repo",
                    str(missing_repo),
                    "--run-id",
                    "run-repo-missing",
                    "--record-json",
                    str(closing),
                ),
                "run close",
            ),
            (
                self.command(
                    "run-retire",
                    "--repo",
                    str(missing_repo),
                    "--run-id",
                    "run-repo-missing",
                ),
                "run retire",
            ),
        )
        for result, operation in cases:
            with self.subTest(operation=operation):
                self.assertEqual(result.returncode, 1)
                self.assertEqual(
                    result.stderr,
                    f"forge: {operation} refused — repository unavailable\n",
                )
                self.assertNotIn(str(missing_repo), result.stderr)

    def test_scope_existing_closed_retired_and_recorded_repo_causes_are_distinct(self) -> None:
        invalid_open = self.open_run("run-invalid-scope", "../escape")
        self.assertEqual(invalid_open.returncode, 1)
        self.assertEqual(invalid_open.stderr, "forge: new run refused — invalid scope\n")

        self.assertEqual(self.open_run("run-open", "src/open/**").returncode, 0)
        invalid_readmit = self.readmit("run-open", "../escape")
        self.assertEqual(invalid_readmit.returncode, 1)
        self.assertEqual(
            invalid_readmit.stderr, "forge: run readmit refused — invalid scope\n"
        )
        duplicate = self.open_run("run-open", "src/other/**")
        self.assertEqual(duplicate.returncode, 1)
        self.assertEqual(
            duplicate.stderr, "forge: new run refused — run run-open already exists\n"
        )

        self.assertEqual(self.open_run("run-closed", "src/closed/**").returncode, 0)
        self.assertEqual(self.close("run-closed").returncode, 0)
        closed = self.append_record("run-closed", self.decision_record(id="after-close"))
        self.assertEqual(closed.returncode, 1)
        self.assertEqual(
            closed.stderr,
            "forge: journal append refused — run run-closed is closed\n",
        )

        self.assertEqual(self.open_run("run-retired", "src/retired/**").returncode, 0)
        self.assertEqual(self.retire("run-retired").returncode, 0)
        retired = self.append_record(
            "run-retired", self.decision_record(id="after-retirement")
        )
        self.assertEqual(retired.returncode, 1)
        self.assertEqual(
            retired.stderr,
            "forge: journal append refused — run run-retired is retired\n",
        )

        self.assertEqual(self.open_run("run-recorded-repo", "src/repo/**").returncode, 0)
        records = self.journal_path("run-recorded-repo").read_text(encoding="utf-8").splitlines()
        opening = json.loads(records[0])
        opening["repo"] = str(self.root / "missing-recorded-repository")
        records[0] = json.dumps(opening, sort_keys=True, separators=(",", ":"))
        self.journal_path("run-recorded-repo").write_text(
            "\n".join(records) + "\n", encoding="utf-8"
        )
        recorded_repo = self.append_record(
            "run-recorded-repo", self.decision_record(id="repo-unavailable")
        )
        self.assertEqual(recorded_repo.returncode, 1)
        self.assertEqual(
            recorded_repo.stderr,
            "forge: journal append refused — recorded repository unavailable for run "
            "run-recorded-repo\n",
        )

    def test_lock_registry_update_and_rollback_failure_literals_are_exact(self) -> None:
        with self.api_environment(), mock.patch.object(
            journal.fcntl, "flock", side_effect=OSError("secret lock failure")
        ):
            with self.assertRaises(journal.CoordinationRefusal) as caught:
                journal.open_run(
                    self.repo,
                    "run-lock-failure",
                    ["src/lock/**"],
                    self.opening_record("run-lock-failure"),
                )
        self.assertEqual(
            str(caught.exception),
            "forge: run coordination refused — run registry lock unavailable",
        )
        self.assertNotIn("secret", str(caught.exception))

        self.assertEqual(self.open_run("run-update", "src/update/**").returncode, 0)
        before = self.coordination_snapshot()
        with self.api_environment(), mock.patch.object(
            journal, "_write_registry", side_effect=OSError("secret update failure")
        ):
            with self.assertRaises(journal.CoordinationRefusal) as caught:
                journal.readmit_run(self.repo, "run-update", ["src/update/new/**"])
        self.assertEqual(
            str(caught.exception),
            "forge: run coordination refused — run registry update failed",
        )
        self.assertEqual(self.coordination_snapshot(), before)

        with self.api_environment(), mock.patch.object(
            journal, "_write_registry", side_effect=OSError("secret update failure")
        ), mock.patch.object(
            journal.os, "ftruncate", side_effect=OSError("secret rollback failure")
        ):
            with self.assertRaises(journal.CoordinationRefusal) as caught:
                journal.readmit_run(self.repo, "run-update", ["src/update/again/**"])
        self.assertEqual(
            str(caught.exception),
            "forge: run coordination refused — journal rollback failed after run registry "
            "update failure",
        )
        self.assertNotIn("secret", str(caught.exception))

    def test_post_scan_journal_target_swaps_are_generic_and_never_followed(self) -> None:
        opened = self.open_run("run-journal-race", "src/**")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        journal_path = self.journal_path("run-journal-race")
        owner_path = self.run_dir("run-journal-race") / "owner"
        original_journal = journal_path.read_bytes()
        original_owner = owner_path.read_bytes()
        original_registry = self.registry_path.read_bytes()
        real_repository_root = journal._recorded_repository_root

        for case in ("deleted", "replaced", "symlink"):
            saved = self.root / f"journal-race-{case}.original"
            external = self.root / f"journal-race-{case}.target"
            decoy = f"{case} decoy must remain byte-identical\n".encode("utf-8")
            triggered = False

            def mutate_after_scan(
                run_dir: Path,
                state_root: Path,
                *,
                records: tuple[dict[str, object], ...] | None = None,
            ) -> Path:
                nonlocal triggered
                repository = real_repository_root(
                    run_dir, state_root, records=records
                )
                if not triggered:
                    triggered = True
                    os.replace(journal_path, saved)
                    if case == "replaced":
                        journal_path.write_bytes(decoy)
                    elif case == "symlink":
                        external.write_bytes(decoy)
                        journal_path.symlink_to(external)
                return repository

            try:
                with self.subTest(case=case), self.api_environment(), mock.patch.object(
                    journal,
                    "_recorded_repository_root",
                    side_effect=mutate_after_scan,
                ):
                    with self.assertRaises(journal.CoordinationRefusal) as caught:
                        journal.append_run_record(
                            self.repo,
                            "run-journal-race",
                            self.decision_record(id=f"journal-race-{case}"),
                        )
                    self.assertTrue(triggered)
                    self.assertEqual(str(caught.exception), journal.REGISTRY_UNAVAILABLE)
                    self.assertEqual(saved.read_bytes(), original_journal)
                    self.assertEqual(owner_path.read_bytes(), original_owner)
                    self.assertEqual(self.registry_path.read_bytes(), original_registry)
                    if case == "deleted":
                        self.assertFalse(journal_path.exists())
                        self.assertFalse(journal_path.is_symlink())
                    elif case == "replaced":
                        self.assertEqual(journal_path.read_bytes(), decoy)
                    else:
                        self.assertTrue(journal_path.is_symlink())
                        self.assertEqual(external.read_bytes(), decoy)
            finally:
                if journal_path.is_symlink() or journal_path.exists():
                    journal_path.unlink()
                if saved.exists():
                    os.replace(saved, journal_path)
                if external.exists():
                    external.unlink()

    def test_ordinary_append_registry_drift_after_fsync_rolls_back_append(self) -> None:
        opened = self.open_run("run-append-registry-drift", "src/drift/**")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        journal_path = self.journal_path("run-append-registry-drift")
        owner_path = self.run_dir("run-append-registry-drift") / "owner"
        journal_before = journal_path.read_bytes()
        owner_before = owner_path.read_bytes()
        drifted_registry = journal._registry_payload(
            {"run-append-registry-drift": ("src/drift/rebound/**",)}
        )
        candidate = self.decision_record(id="append-after-fsync-drift")
        real_append = journal._append_with_locked_stream
        appended_before_drift: list[bytes] = []

        def append_then_drift(*args: object, **kwargs: object) -> int:
            offset = real_append(*args, **kwargs)  # type: ignore[arg-type]
            appended = journal_path.read_bytes()
            self.assertGreater(len(appended), len(journal_before))
            self.assertEqual(json.loads(appended.splitlines()[-1]), candidate)
            appended_before_drift.append(appended)
            self.registry_path.write_bytes(drifted_registry)
            return offset

        with self.api_environment(), mock.patch.object(
            journal,
            "_append_with_locked_stream",
            side_effect=append_then_drift,
        ):
            with self.assertRaises(journal.CoordinationRefusal) as caught:
                journal.append_run_record(
                    self.repo, "run-append-registry-drift", candidate
                )

        self.assertEqual(str(caught.exception), journal.REGISTRY_UNAVAILABLE)
        self.assertEqual(len(appended_before_drift), 1)
        self.assertEqual(journal_path.read_bytes(), journal_before)
        self.assertEqual(owner_path.read_bytes(), owner_before)
        self.assertEqual(self.registry_path.read_bytes(), drifted_registry)

    def test_malformed_registry_remains_generic(self) -> None:
        self.registry_path.parent.mkdir(parents=True)
        self.registry_path.write_text("{}\n", encoding="utf-8")
        malformed = self.open_run("run-malformed-registry", "src/**")
        self.assertEqual(malformed.returncode, 1)
        self.assertEqual(malformed.stderr, journal.REGISTRY_UNAVAILABLE + "\n")

    def test_registry_stat_to_open_identity_swaps_are_generic_and_nonmutating(self) -> None:
        opened = self.open_run("run-registry-race-prime", "prime/**")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        original_registry = self.registry_path.read_bytes()
        prime_journal = self.journal_path("run-registry-race-prime").read_bytes()
        prime_owner = (self.run_dir("run-registry-race-prime") / "owner").read_bytes()
        real_open = journal.os.open

        for case in ("replacement", "symlink"):
            saved = self.root / f"registry-race-{case}.original"
            external = self.root / f"registry-race-{case}.target"
            triggered = False

            def swap_before_open(
                path: object,
                flags: int,
                mode: int = 0o777,
                *,
                dir_fd: int | None = None,
            ) -> int:
                nonlocal triggered
                if (
                    not triggered
                    and dir_fd is not None
                    and os.fspath(path) == self.registry_path.name
                ):
                    triggered = True
                    os.replace(self.registry_path, saved)
                    if case == "replacement":
                        self.registry_path.write_bytes(original_registry)
                    else:
                        external.write_bytes(original_registry)
                        self.registry_path.symlink_to(external)
                if dir_fd is None:
                    return real_open(path, flags, mode)  # type: ignore[arg-type]
                return real_open(  # type: ignore[arg-type]
                    path, flags, mode, dir_fd=dir_fd
                )

            candidate_id = f"run-registry-race-{case}"
            try:
                with self.subTest(case=case), self.api_environment(), mock.patch.object(
                    journal.os, "open", side_effect=swap_before_open
                ):
                    with self.assertRaises(journal.CoordinationRefusal) as caught:
                        journal.open_run(
                            self.repo,
                            candidate_id,
                            [f"src/{case}/**"],
                            self.opening_record(candidate_id),
                        )
                    self.assertTrue(triggered)
                    self.assertEqual(str(caught.exception), journal.REGISTRY_UNAVAILABLE)
                    self.assertFalse(self.run_dir(candidate_id).exists())
                    self.assertEqual(saved.read_bytes(), original_registry)
                    self.assertEqual(
                        self.journal_path("run-registry-race-prime").read_bytes(),
                        prime_journal,
                    )
                    self.assertEqual(
                        (self.run_dir("run-registry-race-prime") / "owner").read_bytes(),
                        prime_owner,
                    )
                    if case == "replacement":
                        self.assertEqual(
                            self.registry_path.read_bytes(), original_registry
                        )
                    else:
                        self.assertTrue(self.registry_path.is_symlink())
                        self.assertEqual(external.read_bytes(), original_registry)
            finally:
                if self.registry_path.is_symlink() or self.registry_path.exists():
                    self.registry_path.unlink()
                if saved.exists():
                    os.replace(saved, self.registry_path)
                if external.exists():
                    external.unlink()

    def test_registry_parent_and_lock_epoch_swaps_refuse_without_redirecting(self) -> None:
        opened = self.open_run("run-registry-epoch", "src/epoch/**")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        tmp_directory = self.repo / ".forge/tmp"
        lock_path = tmp_directory / "run-registry.lock"
        original_registry = self.registry_path.read_bytes()
        original_journal = self.journal_path("run-registry-epoch").read_bytes()
        original_owner = (self.run_dir("run-registry-epoch") / "owner").read_bytes()
        real_validate = journal._validate_registry_publication

        for case in ("parent", "lock"):
            displaced = self.root / f"registry-epoch-{case}-original"
            foreign_registry = b"foreign registry target must remain untouched\n"
            foreign_lock = b"foreign lock target must remain untouched\n"
            triggered = False

            def swap_after_validation(*args: object, **kwargs: object) -> None:
                nonlocal triggered
                real_validate(*args, **kwargs)  # type: ignore[arg-type]
                if triggered:
                    return
                triggered = True
                if case == "parent":
                    os.replace(tmp_directory, displaced)
                    tmp_directory.mkdir()
                    self.registry_path.write_bytes(foreign_registry)
                    lock_path.write_bytes(foreign_lock)
                else:
                    os.replace(lock_path, displaced)
                    lock_path.write_bytes(foreign_lock)

            before = self.coordination_snapshot()
            try:
                with self.subTest(case=case), self.api_environment(), mock.patch.object(
                    journal,
                    "_validate_registry_publication",
                    side_effect=swap_after_validation,
                ):
                    with self.assertRaises(journal.CoordinationRefusal) as caught:
                        journal.readmit_run(
                            self.repo,
                            "run-registry-epoch",
                            [f"src/epoch/{case}/**"],
                        )
                self.assertTrue(triggered)
                self.assertEqual(
                    str(caught.exception), journal.REGISTRY_LOCK_UNAVAILABLE
                )
                self.assertEqual(
                    self.journal_path("run-registry-epoch").read_bytes(),
                    original_journal,
                )
                self.assertEqual(
                    (self.run_dir("run-registry-epoch") / "owner").read_bytes(),
                    original_owner,
                )
                if case == "parent":
                    self.assertEqual(
                        (displaced / "run-registry.json").read_bytes(),
                        original_registry,
                    )
                    self.assertEqual(self.registry_path.read_bytes(), foreign_registry)
                    self.assertEqual(lock_path.read_bytes(), foreign_lock)
                else:
                    self.assertEqual(self.registry_path.read_bytes(), original_registry)
                    self.assertEqual(lock_path.read_bytes(), foreign_lock)
            finally:
                if case == "parent" and displaced.exists():
                    self.registry_path.unlink()
                    lock_path.unlink()
                    tmp_directory.rmdir()
                    os.replace(displaced, tmp_directory)
                elif case == "lock" and displaced.exists():
                    lock_path.unlink()
                    os.replace(displaced, lock_path)
            self.assertEqual(self.coordination_snapshot(), before)

    def test_postpublication_fault_restores_every_lifecycle_transaction(self) -> None:
        for run_id, scope in (
            ("run-postpublish-readmit", "src/postpublish/readmit/**"),
            ("run-postpublish-close", "src/postpublish/close/**"),
            ("run-postpublish-retire", "src/postpublish/retire/**"),
        ):
            opened = self.open_run(run_id, scope)
            self.assertEqual(opened.returncode, 0, opened.stderr)

        operations = (
            (
                "open",
                "run-postpublish-open",
                lambda: journal.open_run(
                    self.repo,
                    "run-postpublish-open",
                    ["src/postpublish/open/**"],
                    self.opening_record("run-postpublish-open"),
                ),
            ),
            (
                "readmit",
                "run-postpublish-readmit",
                lambda: journal.readmit_run(
                    self.repo,
                    "run-postpublish-readmit",
                    ["src/postpublish/readmit/new/**"],
                ),
            ),
            (
                "close",
                "run-postpublish-close",
                lambda: journal.close_run(
                    self.repo,
                    "run-postpublish-close",
                    self.closure_record(),
                ),
            ),
            (
                "retire",
                "run-postpublish-retire",
                lambda: journal.retire_run(
                    self.repo, "run-postpublish-retire"
                ),
            ),
        )

        for operation, run_id, invoke in operations:
            registry_before = self.registry_path.read_bytes()
            before = self.coordination_snapshot()
            published: list[bytes] = []

            def refuse_after_publication(*_args: object, **_kwargs: object) -> None:
                candidate = self.registry_path.read_bytes()
                self.assertNotEqual(candidate, registry_before)
                published.append(candidate)
                raise journal.CoordinationRefusal(journal.REGISTRY_UNAVAILABLE)

            with self.subTest(operation=operation), self.api_environment(), mock.patch.object(
                journal,
                "_validate_post_registry_publication",
                side_effect=refuse_after_publication,
            ):
                with self.assertRaises(journal.CoordinationRefusal) as caught:
                    invoke()
            self.assertEqual(str(caught.exception), journal.REGISTRY_UNAVAILABLE)
            self.assertEqual(len(published), 1)
            self.assertEqual(self.registry_path.read_bytes(), registry_before)
            self.assertEqual(self.coordination_snapshot(), before)
            if operation == "open":
                self.assertFalse(self.run_dir(run_id).exists())

    def test_initially_absent_registry_is_removed_after_postpublication_fault(self) -> None:
        self.runs_root.mkdir(parents=True)
        self.prime_registry_lock()
        candidate_id = "run-absent-registry-rollback"
        before = self.coordination_snapshot()
        published: list[bytes] = []

        def refuse_after_publication(*_args: object, **_kwargs: object) -> None:
            candidate = self.registry_path.read_bytes()
            registry = json.loads(candidate)
            self.assertEqual(
                [entry["run_id"] for entry in registry["open_runs"]],
                [candidate_id],
            )
            published.append(candidate)
            raise journal.CoordinationRefusal(journal.REGISTRY_UNAVAILABLE)

        with self.api_environment(), mock.patch.object(
            journal,
            "_validate_post_registry_publication",
            side_effect=refuse_after_publication,
        ):
            with self.assertRaises(journal.CoordinationRefusal) as caught:
                journal.open_run(
                    self.repo,
                    candidate_id,
                    ["src/absent-registry/**"],
                    self.opening_record(candidate_id),
                )

        self.assertEqual(str(caught.exception), journal.REGISTRY_UNAVAILABLE)
        self.assertEqual(len(published), 1)
        self.assertFalse(self.registry_path.exists())
        self.assertFalse(self.run_dir(candidate_id).exists())
        self.assertEqual(self.coordination_snapshot(), before)

    def test_registry_restoration_failure_retains_published_run_and_journal(self) -> None:
        primed = self.open_run("run-restoration-prime", "src/restoration/prime/**")
        self.assertEqual(primed.returncode, 0, primed.stderr)
        candidate_id = "run-restoration-candidate"

        with self.api_environment(), mock.patch.object(
            journal,
            "_validate_post_registry_publication",
            side_effect=journal.CoordinationRefusal(journal.REGISTRY_UNAVAILABLE),
        ), mock.patch.object(
            journal,
            "_rollback_registry_publication",
            side_effect=journal.RegistryRestorationRefusal(
                journal.JOURNAL_ROLLBACK_FAILED
            ),
        ):
            with self.assertRaises(journal.CoordinationRefusal) as caught:
                journal.open_run(
                    self.repo,
                    candidate_id,
                    ["src/restoration/candidate/**"],
                    self.opening_record(candidate_id),
                )

        self.assertEqual(str(caught.exception), journal.JOURNAL_ROLLBACK_FAILED)
        registry = json.loads(self.registry_path.read_bytes())
        self.assertIn(
            candidate_id,
            {entry["run_id"] for entry in registry["open_runs"]},
        )
        self.assertTrue((self.run_dir(candidate_id) / "owner").is_file())
        opening = json.loads(self.journal_path(candidate_id).read_bytes())
        self.assertEqual(opening["type"], "run_started")
        self.assertEqual(opening["run_id"], candidate_id)

        journal_before = self.journal_path("run-restoration-prime").read_bytes()
        readmitted_scope = ["src/restoration/prime/readmitted/**"]
        with self.api_environment(), mock.patch.object(
            journal,
            "_validate_post_registry_publication",
            side_effect=journal.CoordinationRefusal(journal.REGISTRY_UNAVAILABLE),
        ), mock.patch.object(
            journal,
            "_rollback_registry_publication",
            side_effect=journal.RegistryRestorationRefusal(
                journal.JOURNAL_ROLLBACK_FAILED
            ),
        ):
            with self.assertRaises(journal.CoordinationRefusal) as caught:
                journal.readmit_run(
                    self.repo, "run-restoration-prime", readmitted_scope
                )

        self.assertEqual(str(caught.exception), journal.JOURNAL_ROLLBACK_FAILED)
        journal_after = self.journal_path("run-restoration-prime").read_bytes()
        self.assertNotEqual(journal_after, journal_before)
        readmission = json.loads(journal_after.splitlines()[-1])
        self.assertEqual(readmission["resolution"], journal.READMISSION_RESOLUTION)
        self.assertEqual(readmission["scope"], readmitted_scope)
        registry = json.loads(self.registry_path.read_bytes())
        scopes = {
            entry["run_id"]: entry["scope"] for entry in registry["open_runs"]
        }
        self.assertEqual(scopes["run-restoration-prime"], readmitted_scope)

    def test_existing_registry_publication_keeps_canonical_name_present(self) -> None:
        primed = self.open_run("run-canonical-registry", "src/canonical/**")
        self.assertEqual(primed.returncode, 0, primed.stderr)
        real_link = journal.os.link
        real_exchange = journal._exchange_names_at
        real_unlink = journal.os.unlink
        backup_links: list[tuple[int, int]] = []
        exchanges: list[tuple[str, str, int, int]] = []
        canonical_unlinks: list[str] = []

        def observe_link(
            source: object,
            destination: object,
            *,
            src_dir_fd: int | None = None,
            dst_dir_fd: int | None = None,
            follow_symlinks: bool = True,
        ) -> None:
            is_backup = (
                os.fspath(source) == "run-registry.json"
                and src_dir_fd is not None
                and dst_dir_fd is not None
            )
            before_inode = None
            if is_backup:
                before_inode = os.stat(
                    "run-registry.json",
                    dir_fd=src_dir_fd,
                    follow_symlinks=False,
                ).st_ino
            real_link(
                source,
                destination,
                src_dir_fd=src_dir_fd,
                dst_dir_fd=dst_dir_fd,
                follow_symlinks=follow_symlinks,
            )
            if is_backup:
                canonical_inode = os.stat(
                    "run-registry.json",
                    dir_fd=src_dir_fd,
                    follow_symlinks=False,
                ).st_ino
                backup_inode = os.stat(
                    destination,
                    dir_fd=dst_dir_fd,
                    follow_symlinks=False,
                ).st_ino
                self.assertEqual(before_inode, canonical_inode)
                self.assertEqual(canonical_inode, backup_inode)
                backup_links.append((canonical_inode, backup_inode))

        def observe_exchange(
            directory_descriptor: int,
            first_name: str,
            second_name: str,
        ) -> None:
            involves_canonical = "run-registry.json" in {
                first_name,
                second_name,
            }
            before_inode = None
            if involves_canonical:
                before_inode = os.stat(
                    "run-registry.json",
                    dir_fd=directory_descriptor,
                    follow_symlinks=False,
                ).st_ino
            real_exchange(directory_descriptor, first_name, second_name)
            if involves_canonical:
                after_inode = os.stat(
                    "run-registry.json",
                    dir_fd=directory_descriptor,
                    follow_symlinks=False,
                ).st_ino
                self.assertNotEqual(before_inode, after_inode)
                exchanges.append(
                    (
                        first_name,
                        second_name,
                        before_inode,  # type: ignore[arg-type]
                        after_inode,
                    )
                )

        def observe_unlink(
            path: object, *, dir_fd: int | None = None
        ) -> None:
            if os.fspath(path) == "run-registry.json":
                canonical_unlinks.append(os.fspath(path))
            real_unlink(path, dir_fd=dir_fd)

        with self.api_environment(), mock.patch.object(
            journal.os, "link", side_effect=observe_link
        ), mock.patch.object(
            journal, "_exchange_names_at", side_effect=observe_exchange
        ), mock.patch.object(
            journal.os, "unlink", side_effect=observe_unlink
        ):
            journal.readmit_run(
                self.repo,
                "run-canonical-registry",
                ["src/canonical/readmitted/**"],
            )

        self.assertEqual(len(backup_links), 1)
        self.assertEqual(len(exchanges), 1)
        self.assertTrue(exchanges[0][0].endswith(".candidate"))
        self.assertEqual(exchanges[0][1], "run-registry.json")
        self.assertEqual(canonical_unlinks, [])
        self.assertTrue(self.registry_path.is_file())

    def test_stale_owner_append_failure_restores_owner_and_journal(self) -> None:
        opened = self.open_run("run-stale-owner-append", "src/stale/append/**")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        run_dir = self.run_dir("run-stale-owner-append")
        owner_path = run_dir / "owner"
        journal_path = run_dir / "journal.jsonl"
        stale_owner = (
            f"pid: {self.proven_dead_pid()}\n"
            f"host: {socket.gethostname()}\n"
            f"started_at: {RECORDED_AT}\n"
        ).encode("utf-8")
        owner_path.write_bytes(stale_owner)
        owner_before = owner_path.lstat()
        journal_before = journal_path.read_bytes()
        registry_before = self.registry_path.read_bytes()
        drifted_registry = journal._registry_payload(
            {"run-stale-owner-append": ("src/stale/rebound/**",)}
        )
        candidate = self.decision_record(id="stale-owner-append-failure")
        real_append = journal._append_with_locked_stream
        takeover_seen: list[bytes] = []

        def append_then_drift(*args: object, **kwargs: object) -> int:
            offset = real_append(*args, **kwargs)  # type: ignore[arg-type]
            installed_owner = owner_path.read_bytes()
            self.assertNotEqual(installed_owner, stale_owner)
            self.assertTrue(
                installed_owner.startswith(f"pid: {os.getpid()}\n".encode("utf-8"))
            )
            takeover_seen.append(installed_owner)
            self.registry_path.write_bytes(drifted_registry)
            return offset

        with self.api_environment(), mock.patch.object(
            journal,
            "_append_with_locked_stream",
            side_effect=append_then_drift,
        ):
            with self.assertRaises(journal.CoordinationRefusal) as caught:
                journal.append_run_record(
                    self.repo, "run-stale-owner-append", candidate
                )

        owner_after = owner_path.lstat()
        self.assertEqual(str(caught.exception), journal.REGISTRY_UNAVAILABLE)
        self.assertEqual(len(takeover_seen), 1)
        self.assertEqual(owner_path.read_bytes(), stale_owner)
        self.assertEqual(
            (owner_after.st_dev, owner_after.st_ino, owner_after.st_mode),
            (owner_before.st_dev, owner_before.st_ino, owner_before.st_mode),
        )
        self.assertEqual(journal_path.read_bytes(), journal_before)
        self.assertEqual(self.registry_path.read_bytes(), drifted_registry)
        self.assertNotEqual(self.registry_path.read_bytes(), registry_before)
        self.assertEqual(list(run_dir.glob(".owner.*")), [])

    def test_stale_owner_lifecycle_failure_restores_all_transaction_bytes(self) -> None:
        run_id = "run-stale-owner-lifecycle"
        opened = self.open_run(run_id, "src/stale/lifecycle/**")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        run_dir = self.run_dir(run_id)
        owner_path = run_dir / "owner"
        journal_path = run_dir / "journal.jsonl"
        stale_owner = (
            f"pid: {self.proven_dead_pid()}\n"
            f"host: {socket.gethostname()}\n"
            f"started_at: {RECORDED_AT}\n"
        ).encode("utf-8")
        owner_path.write_bytes(stale_owner)
        real_post = journal._validate_post_registry_publication
        operations = (
            (
                "readmit",
                lambda: journal.readmit_run(
                    self.repo,
                    run_id,
                    ["src/stale/lifecycle/readmitted/**"],
                ),
            ),
            (
                "close",
                lambda: journal.close_run(
                    self.repo, run_id, self.closure_record()
                ),
            ),
            ("retire", lambda: journal.retire_run(self.repo, run_id)),
        )

        for operation, invoke in operations:
            before = self.coordination_snapshot()
            owner_before = owner_path.lstat()
            journal_before = journal_path.read_bytes()
            registry_before = self.registry_path.read_bytes()
            registry_stat_before = self.registry_path.lstat()
            reached: list[bytes] = []

            def validate_then_refuse(*args: object, **kwargs: object) -> None:
                real_post(*args, **kwargs)  # type: ignore[arg-type]
                current_owner = owner_path.read_bytes()
                self.assertNotEqual(current_owner, stale_owner)
                self.assertNotEqual(self.registry_path.read_bytes(), registry_before)
                reached.append(current_owner)
                raise journal.CoordinationRefusal(journal.REGISTRY_UNAVAILABLE)

            with self.subTest(operation=operation), self.api_environment(), mock.patch.object(
                journal,
                "_validate_post_registry_publication",
                side_effect=validate_then_refuse,
            ):
                with self.assertRaises(journal.CoordinationRefusal) as caught:
                    invoke()

            owner_after = owner_path.lstat()
            registry_stat_after = self.registry_path.lstat()
            self.assertEqual(str(caught.exception), journal.REGISTRY_UNAVAILABLE)
            self.assertEqual(len(reached), 1)
            self.assertEqual(owner_path.read_bytes(), stale_owner)
            self.assertEqual(
                (owner_after.st_dev, owner_after.st_ino, owner_after.st_mode),
                (owner_before.st_dev, owner_before.st_ino, owner_before.st_mode),
            )
            self.assertEqual(journal_path.read_bytes(), journal_before)
            self.assertEqual(self.registry_path.read_bytes(), registry_before)
            self.assertEqual(
                (
                    registry_stat_after.st_dev,
                    registry_stat_after.st_ino,
                    registry_stat_after.st_mode,
                ),
                (
                    registry_stat_before.st_dev,
                    registry_stat_before.st_ino,
                    registry_stat_before.st_mode,
                ),
            )
            self.assertEqual(self.coordination_snapshot(), before)
            self.assertEqual(list(run_dir.glob(".owner.*")), [])

    def test_owner_restoration_identity_conflict_preserves_foreign_owner(self) -> None:
        run_id = "run-owner-restoration-conflict"
        opened = self.open_run(run_id, "src/owner/conflict/**")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        run_dir = self.run_dir(run_id)
        owner_path = run_dir / "owner"
        journal_path = run_dir / "journal.jsonl"
        stale_owner = (
            f"pid: {self.proven_dead_pid()}\n"
            f"host: {socket.gethostname()}\n"
            f"started_at: {RECORDED_AT}\n"
        ).encode("utf-8")
        owner_path.write_bytes(stale_owner)
        journal_before = journal_path.read_bytes()
        drifted_registry = journal._registry_payload(
            {run_id: ("src/owner/conflict/rebound/**",)}
        )
        foreign_owner = (
            b"pid: 42\n"
            b"host: foreign-owner.invalid\n"
            b"started_at: 2026-08-26T12:00:00Z\n"
        )
        displaced_candidate = self.root / "owner-restoration-candidate"
        real_append = journal._append_with_locked_stream
        real_rollback_owner = journal._rollback_owner_takeover
        foreign_observation: list[tuple[int, int, int]] = []

        def append_then_drift(*args: object, **kwargs: object) -> int:
            offset = real_append(*args, **kwargs)  # type: ignore[arg-type]
            self.registry_path.write_bytes(drifted_registry)
            return offset

        def replace_owner_then_rollback(
            locked: journal.LockedJournal,
            takeover: journal.OwnerTakeover,
        ) -> None:
            self.assertIsNotNone(takeover.candidate_observation)
            os.replace(owner_path, displaced_candidate)
            owner_path.write_bytes(foreign_owner)
            observed = owner_path.lstat()
            foreign_observation.append(
                (observed.st_dev, observed.st_ino, observed.st_mode)
            )
            real_rollback_owner(locked, takeover)

        with self.api_environment(), mock.patch.object(
            journal,
            "_append_with_locked_stream",
            side_effect=append_then_drift,
        ), mock.patch.object(
            journal,
            "_rollback_owner_takeover",
            side_effect=replace_owner_then_rollback,
        ):
            with self.assertRaises(journal.CoordinationRefusal) as caught:
                journal.append_run_record(
                    self.repo,
                    run_id,
                    self.decision_record(id="owner-restoration-conflict"),
                )

        observed = owner_path.lstat()
        self.assertIsInstance(caught.exception, journal.OwnerRestorationRefusal)
        self.assertEqual(str(caught.exception), journal.JOURNAL_ROLLBACK_FAILED)
        self.assertEqual(journal_path.read_bytes(), journal_before)
        self.assertEqual(self.registry_path.read_bytes(), drifted_registry)
        self.assertEqual(owner_path.read_bytes(), foreign_owner)
        self.assertEqual(
            (observed.st_dev, observed.st_ino, observed.st_mode),
            foreign_observation[0],
        )
        self.assertTrue(
            displaced_candidate.read_bytes().startswith(
                f"pid: {os.getpid()}\n".encode("utf-8")
            )
        )
        prior_backups = list(run_dir.glob(".owner.*.previous"))
        self.assertEqual(len(prior_backups), 1)
        self.assertEqual(prior_backups[0].read_bytes(), stale_owner)

    def test_registry_exchange_race_restores_foreign_canonical_without_publish(self) -> None:
        primed = self.open_run("run-exchange-prime", "src/exchange/prime/**")
        self.assertEqual(primed.returncode, 0, primed.stderr)
        candidate_id = "run-exchange-race"
        prior_registry = self.registry_path.read_bytes()
        prior_stat = self.registry_path.lstat()
        prime_journal = self.journal_path("run-exchange-prime").read_bytes()
        displaced_prior = self.root / "registry-exchange-prior"
        foreign_registry = journal._registry_payload({})
        foreign_observation: list[tuple[int, int, int]] = []
        real_exchange = journal._exchange_names_at
        triggered = False

        def install_foreign_then_exchange(
            directory_descriptor: int,
            first_name: str,
            second_name: str,
        ) -> None:
            nonlocal triggered
            if (
                not triggered
                and first_name.endswith(".candidate")
                and second_name == "run-registry.json"
            ):
                triggered = True
                os.replace(self.registry_path, displaced_prior)
                self.registry_path.write_bytes(foreign_registry)
                observed = self.registry_path.lstat()
                foreign_observation.append(
                    (observed.st_dev, observed.st_ino, observed.st_mode)
                )
            real_exchange(directory_descriptor, first_name, second_name)

        with self.api_environment(), mock.patch.object(
            journal,
            "_exchange_names_at",
            side_effect=install_foreign_then_exchange,
        ):
            with self.assertRaises(journal.CoordinationRefusal) as caught:
                journal.open_run(
                    self.repo,
                    candidate_id,
                    ["src/exchange/candidate/**"],
                    self.opening_record(candidate_id),
                )

        foreign_stat = self.registry_path.lstat()
        displaced_stat = displaced_prior.lstat()
        self.assertTrue(triggered)
        self.assertEqual(str(caught.exception), journal.REGISTRY_UNAVAILABLE)
        self.assertEqual(self.registry_path.read_bytes(), foreign_registry)
        self.assertEqual(
            (foreign_stat.st_dev, foreign_stat.st_ino, foreign_stat.st_mode),
            foreign_observation[0],
        )
        self.assertEqual(displaced_prior.read_bytes(), prior_registry)
        self.assertEqual(
            (displaced_stat.st_dev, displaced_stat.st_ino, displaced_stat.st_mode),
            (prior_stat.st_dev, prior_stat.st_ino, prior_stat.st_mode),
        )
        self.assertEqual(
            self.journal_path("run-exchange-prime").read_bytes(), prime_journal
        )
        self.assertFalse(self.run_dir(candidate_id).exists())
        self.assertEqual(
            list(self.registry_path.parent.glob(".run-registry.json.*")), []
        )

    def test_absent_registry_link_race_never_clobbers_foreign_canonical(self) -> None:
        self.runs_root.mkdir(parents=True)
        self.prime_registry_lock()
        candidate_id = "run-absent-registry-race"
        foreign_registry = journal._registry_payload({})
        foreign_observation: list[tuple[int, int, int]] = []
        real_link = journal.os.link
        triggered = False

        def install_foreign_then_link(
            source: object,
            destination: object,
            *,
            src_dir_fd: int | None = None,
            dst_dir_fd: int | None = None,
            follow_symlinks: bool = True,
        ) -> None:
            nonlocal triggered
            if (
                not triggered
                and os.fspath(destination) == "run-registry.json"
                and os.fspath(source).endswith(".candidate")
            ):
                triggered = True
                self.registry_path.write_bytes(foreign_registry)
                observed = self.registry_path.lstat()
                foreign_observation.append(
                    (observed.st_dev, observed.st_ino, observed.st_mode)
                )
            real_link(
                source,
                destination,
                src_dir_fd=src_dir_fd,
                dst_dir_fd=dst_dir_fd,
                follow_symlinks=follow_symlinks,
            )

        with self.api_environment(), mock.patch.object(
            journal.os,
            "link",
            side_effect=install_foreign_then_link,
        ):
            with self.assertRaises(journal.CoordinationRefusal) as caught:
                journal.open_run(
                    self.repo,
                    candidate_id,
                    ["src/absent/race/**"],
                    self.opening_record(candidate_id),
                )

        foreign_stat = self.registry_path.lstat()
        self.assertTrue(triggered)
        self.assertEqual(str(caught.exception), journal.REGISTRY_UPDATE_FAILED)
        self.assertEqual(self.registry_path.read_bytes(), foreign_registry)
        self.assertEqual(
            (foreign_stat.st_dev, foreign_stat.st_ino, foreign_stat.st_mode),
            foreign_observation[0],
        )
        self.assertFalse(self.run_dir(candidate_id).exists())
        self.assertEqual(list(self.runs_root.iterdir()), [])
        self.assertEqual(
            list(self.registry_path.parent.glob(".run-registry.json.*")), []
        )

    def test_absent_registry_directory_collision_preserves_foreign_node(self) -> None:
        self.assert_absent_registry_node_collision("directory")

    def test_absent_registry_symlink_collision_preserves_foreign_node(self) -> None:
        self.assert_absent_registry_node_collision("symlink")

    def test_absent_registry_broken_symlink_collision_preserves_foreign_node(
        self,
    ) -> None:
        self.assert_absent_registry_node_collision("broken-symlink")

    def test_absent_registry_unreadable_file_collision_preserves_foreign_node(
        self,
    ) -> None:
        self.assert_absent_registry_node_collision("unreadable-file")

    def test_exact_staged_registry_prelink_is_recognized_as_published(self) -> None:
        self.runs_root.mkdir(parents=True)
        self.prime_registry_lock()
        run_id = "run-exact-prelink-success"
        real_link_exact = journal._link_exact_at
        raw_link = journal.os.link
        outcomes: list[journal.NamespaceMutationOutcome] = []

        def prelink_exact_candidate(
            directory_descriptor: int,
            source_name: str,
            destination_name: str,
            expected: journal.ExactFile,
        ) -> journal.NamespaceMutationOutcome:
            if destination_name == "run-registry.json" and not outcomes:
                raw_link(
                    source_name,
                    destination_name,
                    src_dir_fd=directory_descriptor,
                    dst_dir_fd=directory_descriptor,
                    follow_symlinks=False,
                )
                source = os.stat(
                    source_name,
                    dir_fd=directory_descriptor,
                    follow_symlinks=False,
                )
                destination = os.stat(
                    destination_name,
                    dir_fd=directory_descriptor,
                    follow_symlinks=False,
                )
                self.assertEqual(
                    (source.st_dev, source.st_ino),
                    (destination.st_dev, destination.st_ino),
                )
            outcome = real_link_exact(
                directory_descriptor,
                source_name,
                destination_name,
                expected,
            )
            outcomes.append(outcome)
            return outcome

        with self.api_environment(), mock.patch.object(
            journal,
            "_link_exact_at",
            side_effect=prelink_exact_candidate,
        ):
            opened = journal.open_run(
                self.repo,
                run_id,
                ["src/exact/prelink/**"],
                self.opening_record(run_id),
            )

        self.assertEqual(opened, self.run_dir(run_id))
        self.assertEqual([outcome.phase for outcome in outcomes], ["post"])
        registry = json.loads(self.registry_path.read_bytes())
        self.assertEqual(
            {entry["run_id"] for entry in registry["open_runs"]},
            {run_id},
        )
        self.assertTrue((self.run_dir(run_id) / "owner").is_file())
        opening = json.loads(self.journal_path(run_id).read_bytes())
        self.assertEqual(opening["run_id"], run_id)
        self.assertEqual(opening["scope"], ["src/exact/prelink/**"])
        self.assertEqual(
            list(self.registry_path.parent.glob(".run-registry.json.*")), []
        )

    def test_exact_staged_registry_prelink_rolls_back_after_validation_failure(
        self,
    ) -> None:
        self.runs_root.mkdir(parents=True)
        self.prime_registry_lock()
        run_id = "run-exact-prelink-rollback"
        before = self.coordination_snapshot()
        real_link_exact = journal._link_exact_at
        raw_link = journal.os.link
        outcomes: list[journal.NamespaceMutationOutcome] = []

        def prelink_exact_candidate(
            directory_descriptor: int,
            source_name: str,
            destination_name: str,
            expected: journal.ExactFile,
        ) -> journal.NamespaceMutationOutcome:
            if destination_name == "run-registry.json" and not outcomes:
                raw_link(
                    source_name,
                    destination_name,
                    src_dir_fd=directory_descriptor,
                    dst_dir_fd=directory_descriptor,
                    follow_symlinks=False,
                )
            outcome = real_link_exact(
                directory_descriptor,
                source_name,
                destination_name,
                expected,
            )
            outcomes.append(outcome)
            return outcome

        with self.api_environment(), mock.patch.object(
            journal,
            "_link_exact_at",
            side_effect=prelink_exact_candidate,
        ), mock.patch.object(
            journal,
            "_validate_post_registry_publication",
            side_effect=journal.CoordinationRefusal(journal.REGISTRY_UNAVAILABLE),
        ):
            with self.assertRaises(journal.CoordinationRefusal) as caught:
                journal.open_run(
                    self.repo,
                    run_id,
                    ["src/exact/prelink/rollback/**"],
                    self.opening_record(run_id),
                )

        self.assertEqual(str(caught.exception), journal.REGISTRY_UNAVAILABLE)
        self.assertEqual([outcome.phase for outcome in outcomes], ["post"])
        self.assertEqual(self.coordination_snapshot(), before)
        self.assertFalse(self.registry_path.exists())
        self.assertFalse(self.run_dir(run_id).exists())
        self.assertEqual(list(self.runs_root.iterdir()), [])
        self.assertEqual(
            list(self.registry_path.parent.glob(".run-registry.json.*")), []
        )

    def test_exact_staged_owner_prelink_is_recognized_as_adopted(self) -> None:
        run_id = "run-exact-owner-prelink"
        run_dir = self.run_dir(run_id)
        run_dir.mkdir(parents=True)
        self.prime_registry_lock()
        opening = {"type": "run_started", "run_id": run_id, "goal": "legacy"}
        self.journal_path(run_id).write_text(
            json.dumps(opening, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        candidate = self.decision_record(id="exact-owner-prelink")
        real_link_exact = journal._link_exact_at
        raw_link = journal.os.link
        outcomes: list[journal.NamespaceMutationOutcome] = []

        def prelink_exact_owner(
            directory_descriptor: int,
            source_name: str,
            destination_name: str,
            expected: journal.ExactFile,
        ) -> journal.NamespaceMutationOutcome:
            if destination_name == "owner" and not outcomes:
                raw_link(
                    source_name,
                    destination_name,
                    src_dir_fd=directory_descriptor,
                    dst_dir_fd=directory_descriptor,
                    follow_symlinks=False,
                )
            outcome = real_link_exact(
                directory_descriptor,
                source_name,
                destination_name,
                expected,
            )
            outcomes.append(outcome)
            return outcome

        with self.api_environment(), mock.patch.object(
            journal,
            "_link_exact_at",
            side_effect=prelink_exact_owner,
        ):
            journal.append_run_record(self.repo, run_id, candidate)

        self.assertEqual([outcome.phase for outcome in outcomes], ["post"])
        owner = (run_dir / "owner").read_bytes()
        self.assertTrue(owner.startswith(f"pid: {os.getpid()}\n".encode("utf-8")))
        self.assertIn(
            f"host: {socket.gethostname()}\n".encode("utf-8"),
            owner,
        )
        records = [
            json.loads(line)
            for line in self.journal_path(run_id).read_bytes().splitlines()
        ]
        self.assertEqual(records, [opening, candidate])
        self.assertEqual(list(run_dir.glob(".owner.*")), [])
        self.assertFalse(self.registry_path.exists())

    def test_postexchange_foreign_canonicals_are_preserved_for_registry_and_owner(
        self,
    ) -> None:
        run_id = "run-postexchange-owner"
        opened = self.open_run(run_id, "src/postexchange/owner/**")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        run_dir = self.run_dir(run_id)
        owner_path = run_dir / "owner"
        journal_path = self.journal_path(run_id)
        stale_owner = (
            f"pid: {self.proven_dead_pid()}\n"
            f"host: {socket.gethostname()}\n"
            f"started_at: {RECORDED_AT}\n"
        ).encode("utf-8")
        foreign_owner = (
            b"pid: 41\n"
            b"host: postexchange-owner.invalid\n"
            b"started_at: 2026-08-26T12:00:00Z\n"
        )
        owner_path.write_bytes(stale_owner)
        journal_before = journal_path.read_bytes()
        registry_before = self.registry_path.read_bytes()
        displaced_owner_candidate = self.root / "postexchange-owner-candidate"
        foreign_owner_identity: list[tuple[int, int, int]] = []
        real_exchange = journal._exchange_names_at
        owner_raced = False

        def race_owner_after_exchange(
            directory_descriptor: int,
            first_name: str,
            second_name: str,
        ) -> None:
            nonlocal owner_raced
            real_exchange(directory_descriptor, first_name, second_name)
            if (
                not owner_raced
                and first_name.startswith(".owner.")
                and first_name.endswith(".candidate")
                and second_name == "owner"
            ):
                owner_raced = True
                os.replace(owner_path, displaced_owner_candidate)
                owner_path.write_bytes(foreign_owner)
                observed = owner_path.lstat()
                foreign_owner_identity.append(
                    (observed.st_dev, observed.st_ino, observed.st_mode)
                )

        with self.api_environment(), mock.patch.object(
            journal,
            "_exchange_names_at",
            side_effect=race_owner_after_exchange,
        ), mock.patch.object(journal, "_append_with_locked_stream") as append_mock:
            with self.assertRaises(journal.OwnerRestorationRefusal) as owner_caught:
                journal.append_run_record(
                    self.repo,
                    run_id,
                    self.decision_record(id="postexchange-owner-race"),
                )

        owner_after = owner_path.lstat()
        self.assertTrue(owner_raced)
        self.assertEqual(str(owner_caught.exception), journal.JOURNAL_ROLLBACK_FAILED)
        self.assertEqual(owner_path.read_bytes(), foreign_owner)
        self.assertEqual(
            (owner_after.st_dev, owner_after.st_ino, owner_after.st_mode),
            foreign_owner_identity[0],
        )
        self.assertTrue(
            displaced_owner_candidate.read_bytes().startswith(
                f"pid: {os.getpid()}\n".encode("utf-8")
            )
        )
        self.assertEqual(journal_path.read_bytes(), journal_before)
        self.assertEqual(self.registry_path.read_bytes(), registry_before)
        append_mock.assert_not_called()
        self.assertTrue(
            any(
                path.read_bytes() == stale_owner
                for path in run_dir.glob(".owner.*")
            )
        )

        candidate_id = "run-postexchange-registry"
        prior_registry = self.registry_path.read_bytes()
        foreign_registry = journal._registry_payload({})
        displaced_registry_candidate = self.root / "postexchange-registry-candidate"
        foreign_registry_identity: list[tuple[int, int, int]] = []
        registry_raced = False

        def race_registry_after_exchange(
            directory_descriptor: int,
            first_name: str,
            second_name: str,
        ) -> None:
            nonlocal registry_raced
            real_exchange(directory_descriptor, first_name, second_name)
            if (
                not registry_raced
                and first_name.startswith(".run-registry.json.")
                and first_name.endswith(".candidate")
                and second_name == "run-registry.json"
            ):
                registry_raced = True
                os.replace(self.registry_path, displaced_registry_candidate)
                self.registry_path.write_bytes(foreign_registry)
                observed = self.registry_path.lstat()
                foreign_registry_identity.append(
                    (observed.st_dev, observed.st_ino, observed.st_mode)
                )

        with self.api_environment(), mock.patch.object(
            journal,
            "_exchange_names_at",
            side_effect=race_registry_after_exchange,
        ), mock.patch.object(journal, "_cleanup_claimed_run") as cleanup_mock:
            with self.assertRaises(journal.RegistryRestorationRefusal) as registry_caught:
                journal.open_run(
                    self.repo,
                    candidate_id,
                    ["src/postexchange/registry/**"],
                    self.opening_record(candidate_id),
                )

        registry_after = self.registry_path.lstat()
        self.assertTrue(registry_raced)
        self.assertEqual(
            str(registry_caught.exception), journal.JOURNAL_ROLLBACK_FAILED
        )
        self.assertEqual(self.registry_path.read_bytes(), foreign_registry)
        self.assertEqual(
            (registry_after.st_dev, registry_after.st_ino, registry_after.st_mode),
            foreign_registry_identity[0],
        )
        published = json.loads(displaced_registry_candidate.read_bytes())
        self.assertIn(
            candidate_id,
            {entry["run_id"] for entry in published["open_runs"]},
        )
        self.assertTrue(self.journal_path(candidate_id).is_file())
        cleanup_mock.assert_not_called()
        self.assertTrue(
            any(
                path.read_bytes() == prior_registry
                for path in self.registry_path.parent.glob(
                    ".run-registry.json.*"
                )
            )
        )

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
        self.assertEqual(self.coordination_snapshot(), stale_before)

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
        self.assertEqual(self.coordination_snapshot(), missing_before)
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

    def test_registry_restoration_cleanup_occurs_only_after_final_proof(self) -> None:
        primed = self.open_run("run-cleanup-proof", "src/cleanup/prime/**")
        self.assertEqual(primed.returncode, 0, primed.stderr)
        before = self.coordination_snapshot()
        real_validate = journal._validate_restored_registry_publication
        real_unlink = journal._unlink_if_observed
        proof_started = False
        proof_complete = False
        cleaned: list[str] = []

        def validate_then_mark(
            *args: object,
            **kwargs: object,
        ) -> None:
            nonlocal proof_started, proof_complete
            proof_started = True
            retained = list(
                self.registry_path.parent.glob(
                    ".run-registry.json.*.previous"
                )
            )
            self.assertEqual(len(retained), 1)
            real_validate(*args, **kwargs)  # type: ignore[arg-type]
            proof_complete = True

        def require_proof_before_cleanup(
            directory_descriptor: int,
            name: str,
            observation: journal.FileObservation,
        ) -> None:
            if name.endswith(".previous"):
                self.assertTrue(proof_complete)
                cleaned.append(name)
            real_unlink(directory_descriptor, name, observation)

        with self.api_environment(), mock.patch.object(
            journal,
            "_validate_post_registry_publication",
            side_effect=journal.CoordinationRefusal(journal.REGISTRY_UNAVAILABLE),
        ), mock.patch.object(
            journal,
            "_validate_restored_registry_publication",
            side_effect=validate_then_mark,
        ), mock.patch.object(
            journal,
            "_unlink_if_observed",
            side_effect=require_proof_before_cleanup,
        ):
            with self.assertRaises(journal.CoordinationRefusal) as caught:
                journal.open_run(
                    self.repo,
                    "run-cleanup-candidate",
                    ["src/cleanup/candidate/**"],
                    self.opening_record("run-cleanup-candidate"),
                )

        self.assertEqual(str(caught.exception), journal.REGISTRY_UNAVAILABLE)
        self.assertTrue(proof_started)
        self.assertTrue(proof_complete)
        self.assertEqual(len(cleaned), 1)
        self.assertEqual(self.coordination_snapshot(), before)
        self.assertFalse(self.run_dir("run-cleanup-candidate").exists())
        self.assertEqual(
            list(self.registry_path.parent.glob(".run-registry.json.*")), []
        )

    def test_registered_missing_journal_remains_generic(self) -> None:
        orphan = self.run_dir("run-registered-orphan")
        orphan.mkdir(parents=True)
        self.write_registry({"run-registered-orphan": ("src/orphan/**",)})
        (self.repo / ".forge/tmp/run-registry.lock").touch()
        before = self.coordination_snapshot()

        refused = self.open_run("run-other", "src/other/**")

        self.assertEqual(refused.returncode, 1)
        self.assertEqual(refused.stderr, journal.REGISTRY_UNAVAILABLE + "\n")
        self.assertEqual(self.coordination_snapshot(), before)

    def test_empty_placeholder_is_silent_for_all_unrelated_coordination(self) -> None:
        placeholder = self.run_dir("orphan-placeholder")
        placeholder.mkdir(parents=True)
        observed = placeholder.lstat()
        identity = (
            observed.st_dev,
            observed.st_ino,
            observed.st_mode,
            observed.st_size,
            observed.st_mtime_ns,
        )

        opened = self.open_run("run-placeholder-a", "src/a/**")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        appended = self.append_record(
            "run-placeholder-a", self.decision_record(id="placeholder-append")
        )
        self.assertEqual(appended.returncode, 0, appended.stderr)
        readmitted = self.readmit("run-placeholder-a", "src/a/new/**")
        self.assertEqual(readmitted.returncode, 0, readmitted.stderr)

        self.assertEqual(self.open_run("run-placeholder-b", "src/b/**").returncode, 0)
        closed = self.close("run-placeholder-b")
        self.assertEqual(closed.returncode, 0, closed.stderr)
        self.assertEqual(self.open_run("run-placeholder-c", "src/c/**").returncode, 0)
        retired = self.retire("run-placeholder-c")
        self.assertEqual(retired.returncode, 0, retired.stderr)

        after = placeholder.lstat()
        self.assertEqual(
            (after.st_dev, after.st_ino, after.st_mode, after.st_size, after.st_mtime_ns),
            identity,
        )
        self.assertEqual(list(placeholder.iterdir()), [])
        registry = json.loads(self.registry_path.read_text(encoding="utf-8"))
        self.assertNotIn(
            "orphan-placeholder", [item["run_id"] for item in registry["open_runs"]]
        )

        same_id = self.open_run("orphan-placeholder", "src/orphan/**")
        self.assertEqual(same_id.returncode, 1)
        self.assertEqual(
            same_id.stderr,
            "forge: new run refused — run orphan-placeholder directory exists without "
            "journal.jsonl\n",
        )
        self.assertEqual(list(placeholder.iterdir()), [])

    def test_empty_placeholder_targeted_validate_and_monitor_remain_unchanged(self) -> None:
        placeholder = self.run_dir("orphan-targeted")
        placeholder.mkdir(parents=True)
        journal_path = placeholder / "journal.jsonl"

        validated = self.command("validate", str(placeholder))
        expected_validation = {
            "issues": [
                f"missing journal: {journal_path.resolve()}",
                "journal must contain exactly one run_started entry; found 0",
            ],
            "non_passing_verifications": [],
            "ok": False,
            "warnings": [],
        }
        self.assertEqual(validated.returncode, 1)
        self.assertEqual(validated.stderr, "")
        self.assertEqual(
            validated.stdout,
            json.dumps(expected_validation, sort_keys=True) + "\n",
        )

        monitored = self.command(
            "monitor",
            "--repo",
            str(self.repo),
            "--run-id",
            "orphan-targeted",
            "--once",
        )
        expected_monitor = {
            "message": f"could not read run journal: missing journal: {journal_path}",
            "path": str(journal_path),
            "type": "monitor_error",
        }
        self.assertEqual(monitored.returncode, 1)
        self.assertEqual(monitored.stderr, "")
        self.assertEqual(
            monitored.stdout,
            json.dumps(expected_monitor, sort_keys=True, separators=(",", ":"))
            + "\n",
        )
        self.assertEqual(list(placeholder.iterdir()), [])

    def test_same_id_state_created_after_final_classification_is_never_overwritten(self) -> None:
        primed = self.open_run("run-final-window-prime", "prime/**")
        self.assertEqual(primed.returncode, 0, primed.stderr)
        original_registry = self.registry_path.read_bytes()
        prime_journal = self.journal_path("run-final-window-prime").read_bytes()
        prime_owner = (self.run_dir("run-final-window-prime") / "owner").read_bytes()
        real_mkdir = journal.os.mkdir

        for case in ("empty", "nonempty", "symlink"):
            candidate_id = f"run-final-window-{case}"
            target = self.run_dir(candidate_id)
            external = self.root / f"final-window-{case}-target"
            child_bytes = b"externally created state\n"
            triggered = False

            def create_same_id_state(
                path: object,
                mode: int = 0o777,
                *,
                dir_fd: int | None = None,
            ) -> None:
                nonlocal triggered
                same_id_install = (
                    dir_fd is not None and os.fspath(path) == candidate_id
                )
                if same_id_install and not triggered:
                    triggered = True
                    if case == "symlink":
                        external.mkdir()
                        (external / "sentinel").write_bytes(child_bytes)
                        target.symlink_to(external, target_is_directory=True)
                    else:
                        real_mkdir(path, mode, dir_fd=dir_fd)  # type: ignore[arg-type]
                        if case == "nonempty":
                            (target / "sentinel").write_bytes(child_bytes)
                if dir_fd is None:
                    real_mkdir(path, mode)  # type: ignore[arg-type]
                else:
                    real_mkdir(path, mode, dir_fd=dir_fd)  # type: ignore[arg-type]

            if case == "empty":
                expected = (
                    f"forge: new run refused — run {candidate_id} directory exists "
                    "without journal.jsonl"
                )
            elif case == "nonempty":
                expected = (
                    "forge: new run refused — run directory "
                    f".codex-orchestrator/runs/{candidate_id} lacks journal.jsonl"
                )
            else:
                expected = journal.REGISTRY_UNAVAILABLE
            try:
                with self.subTest(case=case), self.api_environment(), mock.patch.object(
                    journal.os, "mkdir", side_effect=create_same_id_state
                ):
                    with self.assertRaises(journal.CoordinationRefusal) as caught:
                        journal.open_run(
                            self.repo,
                            candidate_id,
                            [f"src/{case}/**"],
                            self.opening_record(candidate_id),
                        )
                    self.assertTrue(triggered)
                    self.assertEqual(str(caught.exception), expected)
                    self.assertEqual(self.registry_path.read_bytes(), original_registry)
                    self.assertEqual(
                        self.journal_path("run-final-window-prime").read_bytes(),
                        prime_journal,
                    )
                    self.assertEqual(
                        (self.run_dir("run-final-window-prime") / "owner").read_bytes(),
                        prime_owner,
                    )
                    if case == "empty":
                        self.assertTrue(target.is_dir())
                        self.assertEqual(list(target.iterdir()), [])
                    elif case == "nonempty":
                        self.assertEqual((target / "sentinel").read_bytes(), child_bytes)
                        self.assertEqual(
                            {child.name for child in target.iterdir()}, {"sentinel"}
                        )
                    else:
                        self.assertTrue(target.is_symlink())
                        self.assertEqual((external / "sentinel").read_bytes(), child_bytes)
                        self.assertEqual(
                            {child.name for child in external.iterdir()}, {"sentinel"}
                        )
            finally:
                if target.is_symlink():
                    target.unlink()
                elif target.exists():
                    for child in target.iterdir():
                        child.unlink()
                    target.rmdir()
                if external.exists():
                    for child in external.iterdir():
                        child.unlink()
                    external.rmdir()

    def test_nonempty_ownerless_orphan_names_validated_repo_relative_path(self) -> None:
        self.assertEqual(self.open_run("run-existing", "src/existing/**").returncode, 0)
        orphan = self.run_dir("orphan-run")
        (orphan / "some-subdir").mkdir(parents=True)
        before = self.coordination_snapshot()

        refused = self.open_run("run-candidate", "src/candidate/**")

        self.assertEqual(refused.returncode, 1)
        self.assertEqual(
            refused.stderr,
            "forge: new run refused — run directory "
            ".codex-orchestrator/runs/orphan-run lacks journal.jsonl\n",
        )
        self.assertEqual(self.coordination_snapshot(), before)
        self.assertTrue((orphan / "some-subdir").is_dir())
        self.assertFalse(self.run_dir("run-candidate").exists())

    def test_non_dot_regular_file_in_runs_root_is_silently_ignored(self) -> None:
        self.runs_root.mkdir(parents=True)
        stray = self.runs_root / "CLAUDE.md"
        original = b"hook-deposited documentation stub\n"
        stray.write_bytes(original)

        opened = self.open_run("run-with-stray", "src/**")

        self.assertEqual(opened.returncode, 0, opened.stderr)
        self.assertEqual(stray.read_bytes(), original)

    def test_ambiguous_orphan_kinds_remain_generic_and_nonmutating(self) -> None:
        primed = self.open_run("run-orphan-prime", "prime/**")
        self.assertEqual(primed.returncode, 0, primed.stderr)
        owner_bytes = (self.run_dir("run-orphan-prime") / "owner").read_bytes()

        cases = (
            "owner-bearing",
            "symlink",
            "broken-symlink",
            "dot-prefixed",
            "zero-byte-journal",
            "malformed-journal",
            "non-file-journal",
            "unreadable-journal",
        )
        for index, case in enumerate(cases):
            name = ".orphan-crash" if case == "dot-prefixed" else f"orphan-{case}"
            fixture = self.runs_root / name
            external: Path | None = None
            unreadable_bytes: bytes | None = None
            try:
                if case == "symlink":
                    external = self.root / "live-orphan-link-target"
                    external.mkdir()
                    fixture.symlink_to(external, target_is_directory=True)
                elif case == "broken-symlink":
                    fixture.symlink_to(
                        self.root / "absent-orphan-link-target",
                        target_is_directory=True,
                    )
                else:
                    fixture.mkdir()
                    if case == "owner-bearing":
                        (fixture / "owner").write_bytes(owner_bytes)
                    elif case == "zero-byte-journal":
                        (fixture / "journal.jsonl").touch()
                    elif case == "malformed-journal":
                        (fixture / "journal.jsonl").write_bytes(b"not-json\n")
                    elif case == "non-file-journal":
                        (fixture / "journal.jsonl").mkdir()
                    elif case == "unreadable-journal":
                        unreadable_bytes = b'{"not":"trusted-history"}\n'
                        journal_file = fixture / "journal.jsonl"
                        journal_file.write_bytes(unreadable_bytes)
                        journal_file.chmod(0)

                if case == "unreadable-journal":
                    registry_before = self.registry_path.read_bytes()
                    journal_file = fixture / "journal.jsonl"
                    observed_before = journal_file.lstat()
                else:
                    before = self.coordination_snapshot()

                candidate_id = f"run-orphan-probe-{index}"
                refused = self.open_run(candidate_id, f"candidate/{index}/**")

                with self.subTest(case=case):
                    self.assertEqual(refused.returncode, 1)
                    self.assertEqual(refused.stdout, "")
                    self.assertEqual(
                        refused.stderr, journal.REGISTRY_UNAVAILABLE + "\n"
                    )
                    self.assertFalse(self.run_dir(candidate_id).exists())
                    if case == "unreadable-journal":
                        observed_after = journal_file.lstat()
                        self.assertEqual(
                            (
                                observed_after.st_dev,
                                observed_after.st_ino,
                                observed_after.st_mode,
                                observed_after.st_size,
                            ),
                            (
                                observed_before.st_dev,
                                observed_before.st_ino,
                                observed_before.st_mode,
                                observed_before.st_size,
                            ),
                        )
                        self.assertEqual(
                            self.registry_path.read_bytes(), registry_before
                        )
                    else:
                        self.assertEqual(self.coordination_snapshot(), before)
            finally:
                if case == "unreadable-journal" and fixture.exists():
                    journal_file = fixture / "journal.jsonl"
                    if journal_file.exists():
                        journal_file.chmod(0o600)
                        if unreadable_bytes is not None:
                            self.assertEqual(journal_file.read_bytes(), unreadable_bytes)
                        journal_file.unlink()
                elif fixture.is_symlink():
                    fixture.unlink()
                elif fixture.exists():
                    for child in list(fixture.iterdir()):
                        if child.is_dir() and not child.is_symlink():
                            child.rmdir()
                        else:
                            child.unlink()
                if fixture.exists() and not fixture.is_symlink():
                    fixture.rmdir()
                if external is not None and external.exists():
                    external.rmdir()

    def test_orphan_classifier_control_is_load_bearing(self) -> None:
        placeholder = self.run_dir("orphan-control")
        placeholder.mkdir(parents=True)
        primed = self.open_run("run-classifier-prime", "prime/**")
        self.assertEqual(primed.returncode, 0, primed.stderr)
        before = self.coordination_snapshot()

        with self.api_environment(), mock.patch.object(
            journal, "ORPHAN_CLASSIFICATION_CONTROLS", frozenset()
        ):
            with self.assertRaises(journal.CoordinationRefusal) as caught:
                journal.open_run(
                    self.repo,
                    "run-classifier-disabled",
                    ["src/**"],
                    self.opening_record("run-classifier-disabled"),
                )
        self.assertEqual(str(caught.exception), journal.REGISTRY_UNAVAILABLE)
        self.assertEqual(self.coordination_snapshot(), before)
        self.assertEqual(list(placeholder.iterdir()), [])

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

        readmitted = self.readmit("run-C", "src/ancestor/readmitted/**")
        self.assertEqual(readmitted.returncode, 0, readmitted.stderr)
        unrelated = self.readmit("run-C", "src/unrelated/file.py")
        self.assertEqual(unrelated.returncode, 1)
        self.assertEqual(
            unrelated.stderr,
            "forge: new run refused — scope overlap between run-C and "
            "scope-reserving retired run run-U\n",
        )

        closed = self.close("run-C", judgment="passed")
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

        readmitted = self.readmit("run-readmit-B", "src/disjoint/**")

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

    def test_runs_root_inode_swap_after_phase_two_is_generic_even_when_empty(self) -> None:
        self.runs_root.mkdir(parents=True)
        self.prime_registry_lock()
        real_open_child = journal._open_bound_child_directory

        for case in ("empty", "populated"):
            if case == "populated":
                primed = self.open_run("run-runs-root-prime", "prime/**")
                self.assertEqual(primed.returncode, 0, primed.stderr)
            candidate_id = f"run-runs-root-{case}"
            displaced = self.root / f"runs-root-{case}-original"
            replacement = self.root / f"runs-root-{case}-replacement"
            registry_before = (
                self.registry_path.read_bytes() if self.registry_path.exists() else None
            )
            before = self.coordination_snapshot()
            triggered = False

            def bind_then_swap(
                parent_descriptor: int,
                name: str,
                before_stat: os.stat_result,
            ) -> tuple[int, journal.FileObservation]:
                nonlocal triggered
                descriptor, observation = real_open_child(
                    parent_descriptor, name, before_stat
                )
                if name == "runs" and not triggered:
                    triggered = True
                    os.replace(self.runs_root, displaced)
                    self.runs_root.mkdir()
                return descriptor, observation

            try:
                with self.subTest(case=case), self.api_environment(), mock.patch.object(
                    journal,
                    "_open_bound_child_directory",
                    side_effect=bind_then_swap,
                ):
                    with self.assertRaises(journal.CoordinationRefusal) as caught:
                        journal.open_run(
                            self.repo,
                            candidate_id,
                            [f"src/runs-root/{case}/**"],
                            self.opening_record(candidate_id),
                        )
                self.assertTrue(triggered)
                self.assertEqual(str(caught.exception), journal.REGISTRY_UNAVAILABLE)
                self.assertEqual(list(self.runs_root.iterdir()), [])
                self.assertFalse((self.runs_root / candidate_id).exists())
                self.assertFalse((displaced / candidate_id).exists())
                if case == "empty":
                    self.assertEqual(list(displaced.iterdir()), [])
                    self.assertFalse(self.registry_path.exists())
                else:
                    self.assertTrue(
                        (displaced / "run-runs-root-prime/journal.jsonl").is_file()
                    )
                    self.assertEqual(self.registry_path.read_bytes(), registry_before)
            finally:
                if self.runs_root.exists():
                    os.replace(self.runs_root, replacement)
                if displaced.exists():
                    os.replace(displaced, self.runs_root)
            self.assertEqual(self.coordination_snapshot(), before)

    def test_claimed_candidate_child_is_preserved_but_never_published(self) -> None:
        primed = self.open_run("run-candidate-child-prime", "prime/**")
        self.assertEqual(primed.returncode, 0, primed.stderr)
        candidate_id = "run-candidate-child"
        candidate = self.run_dir(candidate_id)
        injected = candidate / "some-subdir"
        sentinel = injected / "foreign-state"
        foreign_bytes = b"foreign candidate state must survive rollback\n"
        registry_before = self.registry_path.read_bytes()
        real_validate = journal._validate_new_run_claim
        triggered = False

        def inject_then_validate(
            state_root: Path, claim: journal.NewRunClaim
        ) -> None:
            nonlocal triggered
            if not triggered:
                triggered = True
                injected.mkdir()
                sentinel.write_bytes(foreign_bytes)
            real_validate(state_root, claim)

        with self.api_environment(), mock.patch.object(
            journal,
            "_validate_new_run_claim",
            side_effect=inject_then_validate,
        ):
            with self.assertRaises(journal.CoordinationRefusal) as caught:
                journal.open_run(
                    self.repo,
                    candidate_id,
                    ["src/candidate/**"],
                    self.opening_record(candidate_id),
                )

        self.assertTrue(triggered)
        self.assertEqual(str(caught.exception), journal.REGISTRY_UNAVAILABLE)
        self.assertEqual(self.registry_path.read_bytes(), registry_before)
        registry = json.loads(registry_before)
        self.assertNotIn(
            candidate_id,
            {entry["run_id"] for entry in registry["open_runs"]},
        )
        self.assertEqual(sentinel.read_bytes(), foreign_bytes)
        self.assertEqual({child.name for child in candidate.iterdir()}, {"some-subdir"})
        self.assertFalse((candidate / "owner").exists())
        self.assertFalse((candidate / "journal.jsonl").exists())

    def test_cleanup_identity_replacements_preserve_foreign_state_and_fail(self) -> None:
        primed = self.open_run("run-cleanup-race-prime", "prime/**")
        self.assertEqual(primed.returncode, 0, primed.stderr)
        registry_before = self.registry_path.read_bytes()
        real_cleanup = journal._cleanup_claimed_run
        foreign_bytes = b"foreign rollback-race state must never be deleted\n"

        for case in ("file", "directory"):
            candidate_id = f"run-cleanup-race-{case}"
            candidate = self.run_dir(candidate_id)
            displaced_file = self.root / f"cleanup-race-{case}-journal.original"
            displaced_directory = self.root / f"cleanup-race-{case}-run.original"
            canonical_leftover = self.root / f"cleanup-race-{case}-canonical"
            triggered = False

            def replace_before_cleanup(
                parent_descriptor: int,
                name: str,
                directory_descriptor: int,
                directory_observation: journal.FileObservation,
                created: dict[
                    str, tuple[journal.FileObservation, bytes]
                ],
            ) -> bool:
                nonlocal triggered
                self.assertEqual(name, candidate_id)
                if not triggered:
                    triggered = True
                    if case == "file":
                        os.replace(candidate / "journal.jsonl", displaced_file)
                        (candidate / "journal.jsonl").write_bytes(foreign_bytes)
                    else:
                        os.replace(candidate, displaced_directory)
                        candidate.mkdir()
                        (candidate / "foreign-state").write_bytes(foreign_bytes)
                return real_cleanup(
                    parent_descriptor,
                    name,
                    directory_descriptor,
                    directory_observation,
                    created,
                )

            try:
                with self.subTest(case=case), self.api_environment(), mock.patch.object(
                    journal,
                    "_write_registry",
                    side_effect=journal.CoordinationRefusal(
                        journal.REGISTRY_UPDATE_FAILED
                    ),
                ), mock.patch.object(
                    journal,
                    "_cleanup_claimed_run",
                    side_effect=replace_before_cleanup,
                ):
                    with self.assertRaises(journal.CoordinationRefusal) as caught:
                        journal.open_run(
                            self.repo,
                            candidate_id,
                            [f"src/cleanup/{case}/**"],
                            self.opening_record(candidate_id),
                        )
                self.assertTrue(triggered)
                self.assertEqual(str(caught.exception), journal.JOURNAL_ROLLBACK_FAILED)
                self.assertEqual(self.registry_path.read_bytes(), registry_before)
                registry = json.loads(registry_before)
                self.assertNotIn(
                    candidate_id,
                    {entry["run_id"] for entry in registry["open_runs"]},
                )
                if case == "file":
                    self.assertEqual(
                        (candidate / "journal.jsonl").read_bytes(), foreign_bytes
                    )
                    self.assertIn(
                        f'"run_id":"{candidate_id}"'.encode("utf-8"),
                        displaced_file.read_bytes(),
                    )
                    self.assertTrue((candidate / "owner").is_file())
                else:
                    self.assertEqual(
                        (candidate / "foreign-state").read_bytes(), foreign_bytes
                    )
                    self.assertTrue(
                        (displaced_directory / "journal.jsonl").is_file()
                    )
                    self.assertTrue((displaced_directory / "owner").is_file())
            finally:
                if candidate.exists():
                    os.replace(candidate, canonical_leftover)

    def test_placeholder_mutation_at_publication_refuses_and_rolls_back_candidate(self) -> None:
        self.assertEqual(self.open_run("run-publication-prime", "prime/**").returncode, 0)
        placeholder = self.run_dir("orphan-publication-race")
        placeholder.mkdir()
        registry_before = self.registry_path.read_bytes()
        prime_before = self.journal_path("run-publication-prime").read_bytes()
        publication_reached = threading.Event()
        placeholder_mutated = threading.Event()
        thread_errors: list[BaseException] = []
        real_revalidate = journal._revalidate_placeholders

        def mutate_placeholder() -> None:
            try:
                if not publication_reached.wait(timeout=10):
                    raise AssertionError("publication fence was not reached")
                (placeholder / "raced-child").write_text(
                    "external mutation\n", encoding="utf-8"
                )
            except BaseException as exc:
                thread_errors.append(exc)
            finally:
                placeholder_mutated.set()

        def barrier_revalidate(observations: object) -> None:
            publication_reached.set()
            if not placeholder_mutated.wait(timeout=10):
                raise AssertionError("placeholder mutator did not resume publication")
            real_revalidate(observations)  # type: ignore[arg-type]

        mutator = threading.Thread(target=mutate_placeholder, daemon=True)
        mutator.start()
        with self.api_environment(), mock.patch.object(
            journal, "_revalidate_placeholders", side_effect=barrier_revalidate
        ):
            with self.assertRaises(journal.CoordinationRefusal) as caught:
                journal.open_run(
                    self.repo,
                    "run-publication-candidate",
                    ["src/publication/**"],
                    self.opening_record("run-publication-candidate"),
                )
        mutator.join(timeout=10)

        self.assertFalse(mutator.is_alive())
        self.assertEqual(thread_errors, [])
        self.assertEqual(str(caught.exception), journal.REGISTRY_UNAVAILABLE)
        self.assertEqual(self.registry_path.read_bytes(), registry_before)
        self.assertEqual(
            self.journal_path("run-publication-prime").read_bytes(), prime_before
        )
        self.assertFalse(self.run_dir("run-publication-candidate").exists())
        self.assertEqual(
            (placeholder / "raced-child").read_text(encoding="utf-8"),
            "external mutation\n",
        )

    def test_placeholder_inode_and_type_replacement_at_publication_are_generic(self) -> None:
        self.assertEqual(
            self.open_run("run-placeholder-swap-prime", "prime/**").returncode, 0
        )
        registry_before = self.registry_path.read_bytes()
        prime_before = self.journal_path("run-placeholder-swap-prime").read_bytes()
        real_revalidate = journal._revalidate_placeholders

        for case in ("inode", "regular", "symlink"):
            placeholder = self.run_dir(f"orphan-publication-{case}")
            placeholder.mkdir()
            original_stat = placeholder.lstat()
            saved = self.root / f"orphan-publication-{case}-original"
            external = self.root / f"orphan-publication-{case}-external"
            sentinel = b"replacement must remain untouched\n"
            triggered = False

            def replace_observed_placeholder(observations: object) -> None:
                nonlocal triggered
                if not triggered:
                    triggered = True
                    os.replace(placeholder, saved)
                    if case == "inode":
                        placeholder.mkdir()
                    elif case == "regular":
                        placeholder.write_bytes(sentinel)
                    else:
                        external.mkdir()
                        (external / "sentinel").write_bytes(sentinel)
                        placeholder.symlink_to(external, target_is_directory=True)
                real_revalidate(observations)  # type: ignore[arg-type]

            candidate_id = f"run-placeholder-publication-{case}"
            try:
                with self.subTest(case=case), self.api_environment(), mock.patch.object(
                    journal,
                    "_revalidate_placeholders",
                    side_effect=replace_observed_placeholder,
                ):
                    with self.assertRaises(journal.CoordinationRefusal) as caught:
                        journal.open_run(
                            self.repo,
                            candidate_id,
                            [f"src/{case}/**"],
                            self.opening_record(candidate_id),
                        )
                    self.assertTrue(triggered)
                    self.assertEqual(str(caught.exception), journal.REGISTRY_UNAVAILABLE)
                    self.assertEqual(self.registry_path.read_bytes(), registry_before)
                    self.assertEqual(
                        self.journal_path("run-placeholder-swap-prime").read_bytes(),
                        prime_before,
                    )
                    self.assertFalse(self.run_dir(candidate_id).exists())
                    saved_stat = saved.lstat()
                    self.assertEqual(
                        (saved_stat.st_dev, saved_stat.st_ino, saved_stat.st_mode),
                        (
                            original_stat.st_dev,
                            original_stat.st_ino,
                            original_stat.st_mode,
                        ),
                    )
                    self.assertEqual(list(saved.iterdir()), [])
                    if case == "inode":
                        self.assertTrue(placeholder.is_dir())
                        self.assertNotEqual(placeholder.lstat().st_ino, original_stat.st_ino)
                    elif case == "regular":
                        self.assertEqual(placeholder.read_bytes(), sentinel)
                    else:
                        self.assertTrue(placeholder.is_symlink())
                        self.assertEqual((external / "sentinel").read_bytes(), sentinel)
            finally:
                if placeholder.is_symlink() or placeholder.is_file():
                    placeholder.unlink()
                elif placeholder.exists():
                    placeholder.rmdir()
                if saved.exists():
                    saved.rmdir()
                if external.exists():
                    for child in external.iterdir():
                        child.unlink()
                    external.rmdir()

    def test_run_directory_identity_swap_at_publication_rolls_back_original(self) -> None:
        opened = self.open_run("run-directory-publication", "src/original/**")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        run_dir = self.run_dir("run-directory-publication")
        displaced = self.root / "run-directory-publication-original"
        journal_before = self.journal_path("run-directory-publication").read_bytes()
        owner_before = (run_dir / "owner").read_bytes()
        registry_before = self.registry_path.read_bytes()
        real_revalidate = journal._revalidate_placeholders
        triggered = False

        def swap_run_directory(observations: object) -> None:
            nonlocal triggered
            if not triggered:
                triggered = True
                os.replace(run_dir, displaced)
                run_dir.mkdir()
            real_revalidate(observations)  # type: ignore[arg-type]

        with self.api_environment(), mock.patch.object(
            journal, "_revalidate_placeholders", side_effect=swap_run_directory
        ):
            with self.assertRaises(journal.CoordinationRefusal) as caught:
                journal.readmit_run(
                    self.repo,
                    "run-directory-publication",
                    ["src/readmitted/**"],
                )

        self.assertTrue(triggered)
        self.assertEqual(str(caught.exception), journal.REGISTRY_UNAVAILABLE)
        self.assertEqual(self.registry_path.read_bytes(), registry_before)
        self.assertEqual((displaced / "journal.jsonl").read_bytes(), journal_before)
        self.assertEqual((displaced / "owner").read_bytes(), owner_before)
        self.assertEqual(list(run_dir.iterdir()), [])

    def test_journal_identity_swap_at_publication_rolls_back_bound_original(self) -> None:
        opened = self.open_run("run-journal-publication", "src/original/**")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        journal_path = self.journal_path("run-journal-publication")
        displaced = self.root / "run-journal-publication-original.jsonl"
        original = journal_path.read_bytes()
        registry_before = self.registry_path.read_bytes()
        owner_before = (self.run_dir("run-journal-publication") / "owner").read_bytes()
        decoy = b"publication decoy must not be appended or truncated\n"
        real_revalidate = journal._revalidate_placeholders
        triggered = False

        def swap_journal(observations: object) -> None:
            nonlocal triggered
            if not triggered:
                triggered = True
                os.replace(journal_path, displaced)
                journal_path.write_bytes(decoy)
            real_revalidate(observations)  # type: ignore[arg-type]

        with self.api_environment(), mock.patch.object(
            journal, "_revalidate_placeholders", side_effect=swap_journal
        ):
            with self.assertRaises(journal.CoordinationRefusal) as caught:
                journal.readmit_run(
                    self.repo,
                    "run-journal-publication",
                    ["src/readmitted/**"],
                )

        self.assertTrue(triggered)
        self.assertEqual(str(caught.exception), journal.REGISTRY_UNAVAILABLE)
        self.assertEqual(self.registry_path.read_bytes(), registry_before)
        self.assertEqual(displaced.read_bytes(), original)
        self.assertEqual(journal_path.read_bytes(), decoy)
        self.assertEqual(
            (self.run_dir("run-journal-publication") / "owner").read_bytes(),
            owner_before,
        )

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
