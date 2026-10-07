"""Structural journal validation and writer refusal tests."""

from __future__ import annotations

import fcntl
import inspect
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from scripts.codex_orchestrator import journal

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/codex_orch_tools.py"
LEGACY = ROOT / "tests/replay/long-run-001"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )


class ValidationTests(unittest.TestCase):
    def test_rewritten_cli_has_no_stale_lint_ignore_and_mutation_baseline_is_tight(self) -> None:
        from scripts.check_file_length import code_lines

        config = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertNotIn('"scripts/codex_orch_tools.py" =', config)
        baseline = json.loads((ROOT / ".refactor-baseline.json").read_text(encoding="utf-8"))
        self.assertEqual(
            baseline["tests/test_mutation_runner.py"],
            code_lines(str(ROOT / "tests/test_mutation_runner.py")),
        )

    def test_current_unknown_and_legacy_records_are_opaque(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            records = [
                {"kind": "future_kind", "run_id": "example", "anything": [1, 2]},
                {"type": "verification", "result": "passed"},
                {"type": "run_closed", "judgment": "blocked"},
            ]
            path = run_dir / "journal.jsonl"
            path.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            read, issues = journal.read_journal(path)
            validation = journal.validate_run(run_dir)
        self.assertEqual(read, records)
        self.assertEqual(issues, [])
        self.assertEqual(validation, {"ok": True, "issues": []})

    def test_malformed_lines_have_exact_diagnostic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            (run_dir / "journal.jsonl").write_text(
                '{"kind":"unknown","run_id":"run"}\n'
                'not json\n'
                '[]\n'
                '{"kind":"missing-id"}\n'
                '{"kind":"decision","run_id":"run","value":NaN}\n',
                encoding="utf-8",
            )
            result = run_cli("validate", str(run_dir))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            json.loads(result.stdout),
            {
                "ok": False,
                "issues": [
                    f"forge: journal validate failed: malformed JSON object at line {line}"
                    for line in (2, 3, 4, 5)
                ],
            },
        )

    def test_carriage_return_inside_one_json_line_is_not_a_line_break(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "journal.jsonl"
            path.write_bytes(
                b'{"kind":"decision",\r"run_id":"run","text":"first\\rpart"}\n'
                b'{"kind":"decision","run_id":"run","text":"second"}\n'
            )
            records, issues = journal.read_journal(path)
            self.assertEqual([record["text"] for record in records], ["first\rpart", "second"])
            self.assertEqual(issues, [])
            self.assertEqual(journal.validate_run(Path(temporary)), {"ok": True, "issues": []})
            source = inspect.getsource(journal._decode)
            self.assertIn('raw.split(b"\\n")', source)
            namespace = vars(journal).copy()
            exec(source.replace('raw.split(b"\\n")', 'raw.splitlines(keepends=True)'), namespace)
            mutant_records, mutant_issues = namespace["_decode"](path.read_bytes())
            self.assertNotEqual((mutant_records, mutant_issues), (records, issues))

    def test_legacy_replay_fixture_validates_without_migration(self) -> None:
        self.assertEqual(journal.validate_run(LEGACY), {"ok": True, "issues": []})
        result = run_cli("validate", str(LEGACY))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"ok": True, "issues": []})

    def test_invalid_run_id_refuses_before_any_path_and_never_echoes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            for invalid in ("", ".hidden", "../escape", "a/b", "a\\b", "a\x00b", "a\nb"):
                with self.subTest(invalid=repr(invalid)):
                    with self.assertRaises(journal.CoordinationRefusal) as caught:
                        journal.append_run_record(
                            repo, invalid, {"kind": "decision", "run_id": invalid}
                        )
                    self.assertEqual(
                        str(caught.exception),
                        "forge: journal append refused — invalid run id",
                    )
                    self.assertNotIn(invalid, str(caught.exception)) if invalid else None
                    self.assertFalse((repo / ".codex-orchestrator").exists())

    def test_cli_invalid_id_is_refused_before_creating_a_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = run_cli(
                "run-open", "--repo", temporary, "--run-id", "../private",
                "--intent", "work", "--actor", "operator",
            )
            self.assertEqual(result.returncode, 1)
            self.assertEqual(
                result.stderr, "forge: run-open refused — invalid run id\n"
            )
            self.assertNotIn("../private", result.stderr)
            self.assertFalse((Path(temporary) / ".codex-orchestrator").exists())

    def test_missing_envelope_refuses_without_creating_a_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            for record in ([], {}, {"kind": "task"}, {"run_id": "run"}):
                with self.subTest(record=record):
                    with self.assertRaises(journal.CoordinationRefusal) as caught:
                        journal.append_run_record(repo, "run", record)
                    self.assertEqual(str(caught.exception), journal.INVALID_ENVELOPE)
                    self.assertFalse((repo / ".codex-orchestrator").exists())

    def test_io_refusal_is_exact_and_never_exposes_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            blocker = repo / ".codex-orchestrator"
            blocker.write_text("not a directory", encoding="utf-8")
            with self.assertRaises(journal.CoordinationRefusal) as caught:
                journal.append_run_record(
                    repo, "run", {"kind": "decision", "run_id": "run"}
                )
            self.assertEqual(str(caught.exception), journal.APPEND_IO_ERROR)
            self.assertNotIn(str(repo), str(caught.exception))

    def test_journal_lock_failure_is_an_io_refusal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            with mock.patch.object(journal.fcntl, "flock", side_effect=OSError):
                with self.assertRaises(journal.CoordinationRefusal) as caught:
                    journal.append_run_record(
                        repo, "run", {"kind": "decision", "run_id": "run"}
                    )
            self.assertEqual(str(caught.exception), journal.APPEND_IO_ERROR)
            path = repo / ".codex-orchestrator/runs/run/journal.jsonl"
            self.assertEqual(path.read_bytes(), b"")

    def test_invalid_id_guard_is_load_bearing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            for invalid in (".hidden", "../escape", "a/b", "a\\b", "a\nb"):
                with self.subTest(invalid=repr(invalid)):
                    result = run_cli(
                        "run-open", "--repo", str(repo), "--run-id", invalid,
                        "--intent", "work", "--actor", "operator",
                    )
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(result.stderr,
                                     "forge: run-open refused — invalid run id\n")
                    self.assertNotIn(invalid, result.stderr)
                    self.assertFalse((repo / ".codex-orchestrator").exists())

    def test_symlinked_journal_refuses_without_touching_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            run_dir = journal.run_directory(repo, "run")
            run_dir.mkdir(parents=True)
            target = repo / "target"
            target.write_bytes(b"untouched\n")
            (run_dir / "journal.jsonl").symlink_to(target)
            with self.assertRaises(journal.CoordinationRefusal) as caught:
                journal.append_run_record(repo, "run", {"kind": "decision", "run_id": "run"})
            self.assertEqual(str(caught.exception), journal.APPEND_IO_ERROR)
            self.assertEqual(target.read_bytes(), b"untouched\n")

    def test_symlinked_run_directory_refuses_without_touching_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            runs = repo / ".codex-orchestrator/runs"
            runs.mkdir(parents=True)
            target = repo / "outside"
            target.mkdir()
            (runs / "run").symlink_to(target, target_is_directory=True)
            with self.assertRaises(journal.CoordinationRefusal) as caught:
                journal.append_run_record(repo, "run", {"kind": "decision", "run_id": "run"})
            self.assertEqual(str(caught.exception), journal.APPEND_IO_ERROR)
            self.assertEqual(list(target.iterdir()), [])

    def test_torn_line_is_separated_before_next_append(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            run_dir = journal.run_directory(repo, "run")
            run_dir.mkdir(parents=True)
            path = run_dir / "journal.jsonl"
            path.write_bytes(b'{"kind":"decision"')
            journal.append_run_record(repo, "run", {"kind": "decision", "run_id": "run"})
            self.assertEqual(path.read_bytes().splitlines()[0], b'{"kind":"decision"')
            self.assertEqual(json.loads(path.read_bytes().splitlines()[1])["run_id"], "run")

    def test_locked_append_refuses_a_replaced_journal_inode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            descriptor = journal.open_append_lock(repo, "run")
            path = journal.run_directory(repo, "run") / "journal.jsonl"
            old = path.with_name("old-journal.jsonl")
            try:
                path.rename(old)
                path.write_bytes(b"")
                with self.assertRaises(journal.CoordinationRefusal) as caught:
                    journal.append_locked_record(
                        descriptor, path, {"kind": "decision", "run_id": "run"}
                    )
                self.assertEqual(str(caught.exception), journal.APPEND_IO_ERROR)
                self.assertEqual((old.read_bytes(), path.read_bytes()), (b"", b""))
            finally:
                os.close(descriptor)

    def test_validate_treats_recursion_error_as_malformed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            (run_dir / "journal.jsonl").write_text("{}\n", encoding="utf-8")
            with mock.patch.object(journal.json, "loads", side_effect=RecursionError):
                self.assertEqual(journal.validate_run(run_dir), {
                    "ok": False,
                    "issues": ["forge: journal validate failed: malformed JSON object at line 1"],
                })

    def test_unreadable_journal_is_structural_issue(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self.assertEqual(journal.validate_run(Path(temporary)), {
                "ok": False, "issues": ["journal.jsonl: I/O error"],
            })

    def test_nonexistent_run_open_repo_refuses_without_creating_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "missing"
            result = run_cli("run-open", "--repo", str(repo), "--run-id", "run",
                             "--intent", "work", "--actor", "operator")
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stderr,
                             "forge: journal append failed: I/O error\n")
            self.assertFalse(repo.exists())

    def _assert_append_waits(self, repo: Path, path: Path) -> None:
        holder = os.open(path, os.O_WRONLY)
        real_flock = fcntl.flock
        held = threading.Event()
        contended = threading.Event()
        release = threading.Event()
        failures: list[BaseException] = []

        def sensed_flock(descriptor: int, mode: int) -> None:
            contended.set()
            real_flock(descriptor, mode)

        def hold_lock() -> None:
            try:
                real_flock(holder, fcntl.LOCK_EX)
                held.set()
                if not release.wait(5):
                    raise AssertionError("release event was not set")
            except BaseException as exc:
                failures.append(exc)
            finally:
                os.close(holder)

        def check_then_release() -> None:
            try:
                if not contended.wait(5):
                    raise AssertionError("writer did not try the held lock")
                if len(path.read_bytes().splitlines()) != 1:
                    raise AssertionError("writer appended before lock release")
            except BaseException as exc:
                failures.append(exc)
            finally:
                release.set()

        holder_thread = threading.Thread(target=hold_lock)
        holder_thread.start()
        try:
            self.assertTrue(held.wait(5), "holder did not take the lock")
            checker = threading.Thread(target=check_then_release)
            checker.start()
            with mock.patch.object(journal.fcntl, "flock", side_effect=sensed_flock):
                journal.append_run_record(
                    repo, "run", {"kind": "decision", "run_id": "run", "text": "second"}
                )
            checker.join(5)
            self.assertFalse(checker.is_alive())
        finally:
            release.set()
            holder_thread.join(5)
        self.assertFalse(holder_thread.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(len(path.read_bytes().splitlines()), 2)

    def _assert_flock_is_load_bearing(self, repo: Path, path: Path) -> None:
        real_flock = fcntl.flock
        holder = os.open(path, os.O_WRONLY)
        real_flock(holder, fcntl.LOCK_EX)
        try:
            with mock.patch.object(journal.fcntl, "flock", return_value=None):
                journal.append_run_record(
                    repo, "run", {"kind": "decision", "run_id": "run", "text": "mutant"}
                )
            with self.assertRaises(AssertionError):
                self.assertEqual(len(path.read_bytes().splitlines()), 2)
        finally:
            os.close(holder)

    def test_append_waits_for_the_journal_lock_and_lock_call_is_load_bearing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            path = journal.append_run_record(
                repo, "run", {"kind": "decision", "run_id": "run", "text": "first"}
            )
            self._assert_append_waits(repo, path)
            self._assert_flock_is_load_bearing(repo, path)

    def test_retired_validate_flags_exit_two(self) -> None:
        for flag in ("--gates", "--closed-legacy-compat=x"):
            with self.subTest(flag=flag):
                result = run_cli("validate", str(LEGACY), flag)
                self.assertEqual(result.returncode, 2)
                self.assertIn("usage:", result.stderr)
