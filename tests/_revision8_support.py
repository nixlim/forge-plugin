from __future__ import annotations

import copy
import json
import os
import socket
import stat
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from tests._revision8_constants import RECORDED_AT, TOOLS

from codex_orchestrator import batch, journal


class Revision8Support:

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
        self._readmit_number = 0

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
            "provider": "codex",
            "role": "implementer",
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
        replace: bool = False,
        environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        self._readmit_number += 1
        arguments = [
            "run-readmit",
            "--repo",
            str(self.repo),
            "--run-id",
            run_id,
            "--idempotency-key",
            f"{self._readmit_number:064x}",
        ]
        for item in scope:
            arguments.extend(("--scope", item))
        if replace:
            arguments.append("--replace")
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

    def prime_batch_lock(self, run_id: str) -> None:
        """Give a legacy run the stable lock retained by its first raw mutation."""

        with batch.batch_lock(self.run_dir(run_id), create=True):
            pass

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
