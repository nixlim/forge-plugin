"""Revision-19 resolution of a run's recorded repository."""

from __future__ import annotations

import contextlib
import copy
import dataclasses
import errno
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from tests._git_env import init_quiet_repository  # noqa: E402
from tests._revision9_coord_constants import key  # noqa: E402
from tests._revision9_coord_support import (  # noqa: E402
    Revision9BuilderBatchSupport,
)

import codex_orch_tools  # noqa: E402
from codex_orchestrator import (  # noqa: E402
    batch,
    builders,
    journal,
    recorded_repository,
)

AUDIT = ROOT / "scripts/forge/audit-commitments.py"
AUDIT_FIXTURE = ROOT / "tests/replay/archive-audit"
HISTORICAL_ROUTING_HEADING = "## Historical Routing Findings\n"
AUDIT_REPOSITORY_REFUSAL = (
    "forge: commitment audit failed — run_started repo must name an existing "
    "absolute directory\n"
)


def recorded_repository_refusal(run_id: str) -> str:
    return (
        "forge: journal append refused — recorded repository unavailable for run "
        f"{run_id}"
    )


class RecordedRepositoryWorkflowTests(
    Revision9BuilderBatchSupport, unittest.TestCase
):
    def _add_worktree(self, repository: Path, name: str) -> Path:
        worktree = repository / ".worktrees" / name
        worktree.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(repository),
                "worktree",
                "add",
                "--quiet",
                "--detach",
                str(worktree),
                "HEAD",
            ],
            check=True,
            capture_output=True,
        )
        return worktree.resolve()

    def _remove_worktree(self, repository: Path, worktree: Path) -> None:
        subprocess.run(
            [
                "git",
                "-C",
                str(repository),
                "worktree",
                "remove",
                "--force",
                str(worktree),
            ],
            check=True,
            capture_output=True,
        )
        self.assertFalse(worktree.exists())

    def _commit_empty(self, repository: Path) -> None:
        subprocess.run(
            [
                "git",
                "-C",
                str(repository),
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
            capture_output=True,
        )

    def _separate_git_checkout(self, label: str) -> Path:
        checkout = Path(self.temporary.name) / f"{label}-checkout"
        git_directory = Path(self.temporary.name) / f"{label}-metadata/repo.git"
        git_directory.parent.mkdir()
        subprocess.run(
            [
                "git",
                "init",
                "--quiet",
                f"--separate-git-dir={git_directory}",
                str(checkout),
            ],
            check=True,
            capture_output=True,
        )
        self._commit_empty(checkout)
        self.assertTrue((checkout / ".git").is_file())
        return checkout.resolve()

    def _submodule_checkout(self) -> Path:
        superproject, _head = self._new_repo("submodule-superproject")
        source, _head = self._new_repo("submodule-source")
        subprocess.run(
            [
                "git",
                "-c",
                "protocol.file.allow=always",
                "-C",
                str(superproject),
                "submodule",
                "add",
                "--quiet",
                str(source),
                "child",
            ],
            check=True,
            capture_output=True,
        )
        checkout = superproject / "child"
        self.assertTrue((checkout / ".git").is_file())
        return checkout.resolve()

    def _typed(self, *arguments: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            self.api_environment(),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = codex_orch_tools._typed_main(list(arguments))
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def _raw(self, *arguments: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            self.api_environment(),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = codex_orch_tools.main(list(arguments))
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def _open_task_in_worktree(
        self, repository: Path, worktree: Path, run_id: str
    ) -> None:
        with self.api_environment():
            self.open_run(worktree, run_id)
            self.start_task(worktree, run_id)
            builders.decision_add(
                worktree,
                run_id,
                idempotency_key=key(f"{run_id}-completion-provenance"),
                task="task-01",
                resolution="orchestrator-owned: recorded-repository fixture",
                finding=None,
                outcome=None,
                risk=None,
                basis=["synthetic recorded-repository fixture"],
                binding_chain=None,
                binding_id=None,
            )
        self.assertTrue(
            (repository / ".codex-orchestrator/runs" / run_id).is_dir()
        )

    def _typed_finish(
        self, repository: Path, run_id: str, label: str
    ) -> tuple[int, str, str]:
        return self._typed(
            "journal",
            "task-finish",
            "--repo",
            str(repository.resolve()),
            "--run-id",
            run_id,
            "--idempotency-key",
            key(f"{run_id}-{label}"),
            "--task",
            "task-01",
            "--status",
            "complete",
        )

    def _typed_close(
        self, repository: Path, run_id: str, label: str
    ) -> tuple[int, str, str]:
        return self._typed(
            "run-close",
            "--repo",
            str(repository.resolve()),
            "--run-id",
            run_id,
            "--idempotency-key",
            key(f"{run_id}-{label}"),
            "--judgment",
            "blocked",
            "--summary",
            "The recorded worktree was removed after reintegration",
        )

    def _assert_subdirectory_lifecycle(
        self,
        repository: Path,
        nested: Path,
        caller: Path,
        label: str,
    ) -> None:
        run_id = f"run-20261003-subdirectory-{label}"
        open_code, open_stdout, open_stderr = self._typed(
            "run-open",
            "--repo",
            str(nested.resolve()),
            "--run-id",
            run_id,
            "--idempotency-key",
            key(f"{run_id}-open"),
            "--goal",
            "Exercise an admitted repository subdirectory",
            "--scope",
            "src/**",
            "--plugin-ref",
            "forge-test-recorded-repository",
        )
        self.assertEqual(open_code, 0, open_stderr)
        self.assertEqual(json.loads(open_stdout)["records"][0]["repo"], str(nested))

        task_code, _task_stdout, task_stderr = self._typed(
            "journal",
            "task-start",
            "--repo",
            str(caller.resolve()),
            "--run-id",
            run_id,
            "--idempotency-key",
            key(f"{run_id}-task"),
            "--task",
            "task-01",
            "--goal",
            "Exercise the recorded repository resolver",
            "--acceptance",
            "The lifecycle remains writable",
            "--file",
            "src/example.py",
        )
        self.assertEqual(task_code, 0, task_stderr)
        append_code, _append_stdout, append_stderr = self._typed(
            "journal",
            "decision-add",
            "--repo",
            str(caller.resolve()),
            "--run-id",
            run_id,
            "--idempotency-key",
            key(f"{run_id}-decision"),
            "--task",
            "task-01",
            "--resolution",
            "orchestrator-owned: subdirectory lifecycle fixture",
            "--basis",
            "synthetic recorded-repository fixture",
        )
        self.assertEqual(append_code, 0, append_stderr)

        probe_id = f"{run_id}-released"
        probe_arguments = (
            "run-open",
            "--repo",
            str(caller.resolve()),
            "--run-id",
            probe_id,
            "--idempotency-key",
            key(f"{probe_id}-open"),
            "--goal",
            "Prove the closed run released its scope",
            "--scope",
            "src/**",
            "--plugin-ref",
            "forge-test-recorded-repository",
        )
        blocked_code, blocked_stdout, blocked_stderr = self._typed(*probe_arguments)
        self.assertEqual(blocked_code, 1)
        self.assertEqual(blocked_stdout, "")
        self.assertEqual(
            blocked_stderr,
            f"forge: new run refused — scope overlap between {probe_id} and "
            f"open run {run_id}\n",
        )
        finish_code, _finish_stdout, finish_stderr = self._typed_finish(
            caller, run_id, f"{label}-finish"
        )
        self.assertEqual(finish_code, 0, finish_stderr)
        close_code, _close_stdout, close_stderr = self._typed_close(
            caller, run_id, f"{label}-close"
        )
        self.assertEqual(close_code, 0, close_stderr)
        self.assertEqual(
            journal._scan_run(self.run_dir(repository, run_id)).disposition,
            "closed",
        )

        probe_code, _probe_stdout, probe_stderr = self._typed(*probe_arguments)
        self.assertEqual(probe_code, 0, probe_stderr)

        retire_id = f"{run_id}-retire"
        with self.api_environment():
            self._open_legacy_run(
                nested,
                retire_id,
                scope=[f"retire-{label}/**"],
            )
        retire_code, retire_stdout, retire_stderr = self._raw(
            "run-retire",
            "--repo",
            str(caller.resolve()),
            "--run-id",
            retire_id,
        )
        self.assertEqual(retire_code, 0, retire_stderr)
        self.assertEqual(retire_stdout, "")
        self.assertEqual(retire_stderr, "")
        self.assertEqual(
            journal._scan_run(self.run_dir(repository, retire_id)).disposition,
            "retired",
        )

    def _invoke_mismatch(
        self, site: str, repository: Path, run_id: str
    ) -> object:
        if site == "owner":
            return batch._adopt_owner_before_intent(
                repository,
                journal._resolve_state_root(repository),
                run_id,
                close=False,
            )
        if site in {"legacy-scope", "scope"}:
            return builders.scope_change(
                repository,
                run_id,
                idempotency_key=key(f"{run_id}-scope"),
                scope=["src/**", "tests/**"],
            )
        return builders.task_start(
            repository,
            run_id,
            idempotency_key=key(f"{run_id}-task"),
            task="task-01",
            goal="Exercise a live repository mismatch",
            acceptance=["The exact diagnostic is emitted"],
            files=["src/example.py"],
        )

    def _assert_mismatch_literal(
        self, site: str, repository: Path, run_id: str
    ) -> None:
        with self.assertRaises(journal.CoordinationRefusal) as caught:
            self._invoke_mismatch(site, repository, run_id)
        diagnostic = str(caught.exception)
        self.assertEqual(diagnostic, recorded_repository_refusal(run_id))
        self.assertNotIn("run registry unavailable", diagnostic)

    def _assert_recorded_value_refused(
        self, run_dir: Path, state_root: Path, value: str
    ) -> None:
        with self.assertRaises(journal.CoordinationRefusal) as caught:
            journal._recorded_repository_root(
                run_dir,
                state_root,
                state_root,
                records=({"type": "run_started", "repo": value},),
            )
        self.assertEqual(
            str(caught.exception),
            recorded_repository_refusal(run_dir.name),
        )

    def _assert_external_git_layout(self, repository: Path, label: str) -> None:
        nested = repository / "admitted-subdirectory"
        nested.mkdir()
        state_root = journal._resolve_state_root(repository)
        self.assertNotEqual(state_root, repository)
        original_common = recorded_repository._git_common_directory
        common_queries: list[Path] = []

        def checkout_common(candidate: Path) -> Path:
            resolved = candidate.resolve()
            self.assertNotEqual(resolved, state_root)
            common_queries.append(resolved)
            return original_common(candidate)

        with mock.patch.object(
            recorded_repository,
            "_git_common_directory",
            side_effect=checkout_common,
        ), self.api_environment():
            for recorded, caller, kind in (
                (repository, nested, "toplevel"),
                (nested, repository, "subdirectory"),
            ):
                run_id = f"run-20261003-{label}-{kind}"
                builders.run_open(
                    recorded,
                    run_id,
                    idempotency_key=key(f"{run_id}-open"),
                    goal="Exercise nonstandard Git metadata",
                    scope=[f"{kind}/**"],
                    plugin_ref="forge-test-recorded-repository",
                )
                run_dir = state_root / ".codex-orchestrator/runs" / run_id
                self.assertTrue(run_dir.is_dir())
                self.assertFalse(
                    (repository / ".codex-orchestrator/runs" / run_id).exists()
                )
                common_queries.clear()
                resolved = recorded_repository.resolve(
                    str(recorded),
                    caller_repository=caller,
                    state_root=state_root,
                    run_dir=run_dir,
                )
                self.assertEqual(resolved, (repository, None))
                self.assertIn(caller.resolve(), common_queries)
                self.assertEqual(
                    journal._recorded_repository_root(
                        run_dir, state_root, caller
                    ),
                    repository,
                )
                before = (run_dir / "journal.jsonl").read_bytes()
                builders.task_start(
                    caller,
                    run_id,
                    idempotency_key=key(f"{run_id}-task"),
                    task="task-01",
                    goal="Append from the other repository path form",
                    acceptance=["The append resolves the recorded checkout"],
                    files=[f"{kind}/example.py"],
                )
                self.assertGreater(
                    len((run_dir / "journal.jsonl").read_bytes()), len(before)
                )

    def test_dead_worktree_allows_typed_task_finish_and_run_close(self) -> None:
        run_id = "run-20261003-recorded-repository"
        worktree = self._add_worktree(self.repo, "gone")
        self._open_task_in_worktree(self.repo, worktree, run_id)
        self._remove_worktree(self.repo, worktree)

        finish_code, finish_stdout, finish_stderr = self._typed_finish(
            self.repo, run_id, "finish"
        )
        self.assertEqual(finish_code, 0, finish_stderr)
        self.assertEqual(
            json.loads(finish_stdout)["records"][0]["status"], "complete"
        )

        close_code, close_stdout, close_stderr = self._typed_close(
            self.repo, run_id, "close"
        )
        self.assertEqual(close_code, 0, close_stderr)
        self.assertEqual(
            json.loads(close_stdout)["records"][0]["type"], "run_closed"
        )
        self.assertEqual(
            journal._scan_run(self.run_dir(self.repo, run_id)).disposition,
            "closed",
        )

        disabled_run = "run-20261003-recorded-repository-disabled"
        disabled_worktree = self._add_worktree(self.repo, "gone-disabled")
        self._open_task_in_worktree(
            self.repo, disabled_worktree, disabled_run
        )
        self._remove_worktree(self.repo, disabled_worktree)
        disabled_legs = recorded_repository.RECORDED_REPOSITORY_LEGS - {
            "absent-worktree"
        }
        with mock.patch.object(
            recorded_repository,
            "RECORDED_REPOSITORY_LEGS",
            disabled_legs,
        ):
            disabled_code, disabled_stdout, disabled_stderr = (
                self._typed_finish(self.repo, disabled_run, "finish")
            )
        with self.assertRaises(AssertionError):
            self.assertEqual(disabled_code, 0, disabled_stderr)
        self.assertEqual(disabled_stdout, "")
        self.assertEqual(
            disabled_stderr,
            recorded_repository_refusal(disabled_run) + "\n",
        )

    def test_invalid_absent_values_and_lstat_eacces_refuse_exactly(self) -> None:
        run_id = "run-20261003-recorded-repository-invalid"
        run_dir = self.run_dir(self.repo, run_id)
        run_dir.mkdir(parents=True)
        cases = (
            ("outside", str(self.repo.resolve() / "missing-x"), run_dir),
            (
                "worktrees-boundary",
                str(self.repo.resolve() / ".worktrees"),
                run_dir,
            ),
            (
                "non-normalized",
                os.fspath(
                    self.repo.resolve() / ".worktrees" / ".." / "missing-x"
                ),
                run_dir,
            ),
            ("relative", ".worktrees/gone", run_dir),
            (
                "wrong-run-layout",
                str(self.repo.resolve() / ".worktrees" / "gone"),
                self.repo / ".codex-orchestrator" / "other" / run_id,
            ),
        )
        for label, value, candidate_run_dir in cases:
            with self.subTest(case=label):
                self._assert_recorded_value_refused(
                    candidate_run_dir, self.repo.resolve(), value
                )

        denied = self.repo.resolve() / ".worktrees" / "denied"
        denied_error = OSError(errno.EACCES, "synthetic lstat denial")
        with mock.patch.object(
            recorded_repository.os, "lstat", side_effect=denied_error
        ), self.assertRaises(journal.CoordinationRefusal) as caught:
            journal._recorded_repository_root(
                run_dir,
                self.repo.resolve(),
                records=(
                    {"type": "run_started", "repo": str(denied)},
                ),
            )
        self.assertEqual(
            str(caught.exception), recorded_repository_refusal(run_id)
        )

    def test_present_repository_resolves_toplevel_and_requires_shared_common_dir(
        self,
    ) -> None:
        run_id = "run-20261003-recorded-repository-present"
        run_dir = self.run_dir(self.repo, run_id)
        run_dir.mkdir(parents=True)

        nested = self.repo.resolve() / "ordinary-subdirectory"
        nested.mkdir()
        resolved, absent_relative = recorded_repository.resolve(
            str(nested), state_root=self.repo.resolve(), run_dir=run_dir
        )
        self.assertEqual(resolved, self.repo.resolve())
        self.assertIsNone(absent_relative)

        symlink = self.repo.resolve() / "subdirectory-link"
        symlink.symlink_to(nested, target_is_directory=True)
        linked, linked_absent = recorded_repository.resolve(
            str(symlink), state_root=self.repo.resolve(), run_dir=run_dir
        )
        self.assertEqual(linked, self.repo.resolve())
        self.assertIsNone(linked_absent)

        worktree = self._add_worktree(self.repo, "present-worktree")
        worktree_nested = worktree / "ordinary-subdirectory"
        worktree_nested.mkdir()
        worktree_root, worktree_absent = recorded_repository.resolve(
            str(worktree_nested),
            state_root=self.repo.resolve(),
            run_dir=run_dir,
        )
        self.assertEqual(worktree_root, worktree)
        self.assertIsNone(worktree_absent)
        original_git_directory = recorded_repository._git_directory

        def disabled_toplevel(
            repository: Path, *arguments: str
        ) -> Path:
            if repository == nested and arguments == ("--show-toplevel",):
                return nested
            return original_git_directory(repository, *arguments)

        with mock.patch.object(
            recorded_repository, "_git_directory", side_effect=disabled_toplevel
        ), self.assertRaises(AssertionError):
            disabled_root, _disabled_absent = recorded_repository.resolve(
                str(nested), state_root=self.repo.resolve(), run_dir=run_dir
            )
            self.assertEqual(disabled_root, self.repo.resolve())

        foreign, _head = self._new_repo("foreign-recorded-repository")
        self._assert_recorded_value_refused(
            run_dir, self.repo.resolve(), str(foreign.resolve())
        )
        caller_common = recorded_repository._git_common_directory(
            self.repo.resolve()
        )
        with mock.patch.object(
            recorded_repository,
            "_git_common_directory",
            return_value=caller_common,
        ), self.assertRaises(AssertionError):
            self._assert_recorded_value_refused(
                run_dir, self.repo.resolve(), str(foreign.resolve())
            )

    def test_subdirectory_open_remains_writable_from_toplevel_and_subdirectory(
        self,
    ) -> None:
        for caller_kind in ("toplevel", "subdirectory"):
            with self.subTest(caller=caller_kind):
                repository, _head = self._new_repo(f"subdirectory-{caller_kind}")
                nested = repository.resolve() / "admitted-subdirectory"
                nested.mkdir()
                caller = repository if caller_kind == "toplevel" else nested
                self._assert_subdirectory_lifecycle(
                    repository.resolve(), nested, caller, caller_kind
                )

        original_present = recorded_repository._present_repository

        def disabled_present(
            recorded: str, caller_repository: Path, state_root: Path
        ) -> Path:
            supplied = Path(recorded).expanduser().resolve(strict=True)
            top_level = original_present(recorded, caller_repository, state_root)
            if supplied != top_level:
                raise recorded_repository.ResolutionError
            return top_level

        disabled_repo, _head = self._new_repo("subdirectory-disabled-resolver")
        disabled_nested = disabled_repo.resolve() / "admitted-subdirectory"
        disabled_nested.mkdir()
        with mock.patch.object(
            recorded_repository,
            "_present_repository",
            side_effect=disabled_present,
        ), self.assertRaises(AssertionError):
            self._assert_subdirectory_lifecycle(
                disabled_repo.resolve(),
                disabled_nested,
                disabled_repo.resolve(),
                "disabled-resolver",
            )

        disabled_repo, _head = self._new_repo("subdirectory-disabled-caller")
        disabled_nested = disabled_repo.resolve() / "admitted-subdirectory"
        disabled_nested.mkdir()
        with mock.patch.object(
            journal,
            "_recorded_repository_matches",
            side_effect=lambda recorded, caller, _state: recorded == caller,
        ), self.assertRaises(AssertionError):
            self._assert_subdirectory_lifecycle(
                disabled_repo.resolve(),
                disabled_nested,
                disabled_nested,
                "disabled-caller",
            )

    def test_separate_git_dir_and_submodule_use_caller_checkout(self) -> None:
        fixtures = (
            (self._separate_git_checkout("separate"), "separate"),
            (self._submodule_checkout(), "submodule"),
        )
        for repository, label in fixtures:
            with self.subTest(layout=label):
                self._assert_external_git_layout(repository, label)

    def test_deleted_separate_git_checkout_outside_worktrees_refuses(self) -> None:
        repository = self._separate_git_checkout("deleted-separate")
        state_root = journal._resolve_state_root(repository)
        run_id = "run-20261003-deleted-separate"
        run_dir = state_root / ".codex-orchestrator/runs" / run_id
        run_dir.mkdir(parents=True)
        recorded = str(repository)
        self.assertFalse(repository.is_relative_to(state_root / ".worktrees"))
        shutil.rmtree(repository)

        with self.assertRaises(recorded_repository.ResolutionError):
            recorded_repository.resolve(
                recorded,
                caller_repository=repository,
                state_root=state_root,
                run_dir=run_dir,
            )
        with self.assertRaises(journal.CoordinationRefusal) as caught:
            journal._recorded_repository_root(
                run_dir,
                state_root,
                repository,
                records=({"type": "run_started", "repo": recorded},),
            )
        self.assertEqual(
            str(caught.exception), recorded_repository_refusal(run_id)
        )

    def test_enotdir_is_an_absent_worktree_value(self) -> None:
        run_id = "run-20261003-recorded-repository-enotdir"
        run_dir = self.run_dir(self.repo, run_id)
        run_dir.mkdir(parents=True)
        blocker = self.repo / ".worktrees" / "not-a-directory"
        blocker.parent.mkdir(parents=True)
        blocker.write_text("not a directory\n", encoding="utf-8")
        recorded = blocker / "gone"

        root, absent_relative = recorded_repository.resolve(
            str(recorded), state_root=self.repo.resolve(), run_dir=run_dir
        )

        self.assertEqual(root, self.repo.resolve())
        self.assertIsNotNone(absent_relative)
        self.assertEqual(
            os.fspath(absent_relative), ".worktrees/not-a-directory/gone"
        )

    def test_all_live_repository_mismatches_use_recorded_repo_literal(self) -> None:
        for site in ("owner", "legacy-scope", "scope", "existing"):
            with self.subTest(site=site):
                repository, _head = self._new_repo(f"mismatch-{site}")
                worktree = self._add_worktree(repository, "live")
                run_id = f"run-20261003-mismatch-{site}"
                with self.api_environment():
                    if site == "legacy-scope":
                        self._open_legacy_run(worktree, run_id)
                    else:
                        self.open_run(worktree, run_id)

                    self._assert_mismatch_literal(site, repository, run_id)

    def test_live_main_repository_refuses_linked_worktree_callers(self) -> None:
        for site in ("owner", "legacy-scope", "scope", "existing"):
            with self.subTest(site=site):
                repository, _head = self._new_repo(f"reverse-mismatch-{site}")
                worktree = self._add_worktree(repository, "live")
                run_id = f"run-20261003-reverse-mismatch-{site}"
                with self.api_environment():
                    if site == "legacy-scope":
                        self._open_legacy_run(repository, run_id)
                    else:
                        self.open_run(repository, run_id)

                    self._assert_mismatch_literal(site, worktree, run_id)

    def test_state_root_widening_fails_reverse_mismatch_sensor(self) -> None:
        def widened_match(
            recorded: Path, caller: Path, state_root: Path
        ) -> bool:
            caller_root = recorded_repository._present_repository(
                str(caller), caller, state_root
            )
            return recorded in {caller_root, state_root}

        repository, _head = self._new_repo("widened-existing")
        worktree = self._add_worktree(repository, "live")
        run_id = "run-20261003-widened-existing"
        with self.api_environment():
            self.open_run(repository, run_id)
            with mock.patch.object(
                journal,
                "_recorded_repository_matches",
                side_effect=widened_match,
            ), self.assertRaises(AssertionError):
                self._assert_mismatch_literal("existing", worktree, run_id)

    def test_old_mismatch_literal_fails_the_positive_sensor(self) -> None:
        repository, _head = self._new_repo("mismatch-disabled")
        worktree = self._add_worktree(repository, "live")
        run_id = "run-20261003-mismatch-disabled"
        with self.api_environment():
            self.open_run(worktree, run_id)

            with mock.patch.object(
                journal,
                "_recorded_repository_unavailable",
                return_value=journal.REGISTRY_UNAVAILABLE,
            ), self.assertRaises(AssertionError):
                self._assert_mismatch_literal(
                    "existing", repository, run_id
                )

    def test_pending_intent_keeps_strict_recorded_repository_string(self) -> None:
        repository, _head = self._new_repo("pending-intent")
        worktree = self._add_worktree(repository, "gone")
        run_id = "run-20261003-pending-recorded-repository"
        with self.api_environment():
            self.open_run(worktree, run_id)
            original_write_intent = batch._write_intent

            def crash_after_intent(*arguments: object, **keywords: object) -> object:
                original_write_intent(*arguments, **keywords)
                raise RuntimeError("synthetic crash after intent")

            with mock.patch.object(
                batch, "_write_intent", side_effect=crash_after_intent
            ), self.assertRaisesRegex(
                RuntimeError, "synthetic crash after intent"
            ):
                builders.scope_change(
                    worktree,
                    run_id,
                    idempotency_key=key(f"{run_id}-readmit"),
                    scope=["src/**", "tests/**"],
                )
        run_dir = self.run_dir(repository, run_id)
        self.assertTrue((run_dir / journal.BATCH_INTENT_NAME).is_file())
        before = {
            path.name: path.read_bytes()
            for path in run_dir.iterdir()
            if path.is_file()
        }
        self._remove_worktree(repository, worktree)

        def assert_diverged() -> None:
            with self.api_environment(), self.assertRaises(
                journal.CoordinationRefusal
            ) as caught:
                batch.recover_batch(repository, run_id)
            self.assertEqual(str(caught.exception), journal.BATCH_DIVERGED)

        assert_diverged()
        self.assertEqual(
            {
                path.name: path.read_bytes()
                for path in run_dir.iterdir()
                if path.is_file()
            },
            before,
        )
        self.assertTrue((run_dir / journal.BATCH_INTENT_NAME).is_file())

        original_context = batch._scope_change_recovery_context

        def disabled_string_check(
            *arguments: object, **keywords: object
        ) -> tuple[object, ...]:
            context = original_context(*arguments, **keywords)
            view, state, scope, published, base = context
            records = copy.deepcopy(state.records)
            records[0]["repo"] = str(repository.resolve())
            return (
                view,
                dataclasses.replace(state, records=records),
                scope,
                published,
                base,
            )

        with mock.patch.object(
            batch,
            "_scope_change_recovery_context",
            side_effect=disabled_string_check,
        ), self.assertRaises(AssertionError):
            assert_diverged()


class RecordedRepositoryAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix="forge-recorded-repository-audit-"
        )
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name) / "repo"
        self.repo.mkdir()
        self._git("init", "--quiet")
        self._git("symbolic-ref", "HEAD", "refs/heads/main")
        self._git("config", "user.name", "Recorded Repository Fixture")
        self._git("config", "user.email", "recorded-repo@example.invalid")
        (self.repo / ".gitignore").write_text(
            ".codex-orchestrator/\n.forge/tmp/\n.worktrees/\n",
            encoding="utf-8",
        )
        (self.repo / "docs").mkdir()
        (self.repo / "docs/repo-basis.md").write_text(
            "# Repository basis\n", encoding="utf-8"
        )
        self._git("add", ".gitignore", "docs/repo-basis.md")
        self._git("commit", "--quiet", "-m", "fixture")
        self._install_repo_conformance_authority()

        self.run_id = "archive-audit"
        self.run_dir = (
            self.repo / ".codex-orchestrator" / "runs" / self.run_id
        )
        shutil.copytree(AUDIT_FIXTURE, self.run_dir)
        dead_worktree = self.repo.resolve() / ".worktrees" / "gone"
        journal_path = self.run_dir / "journal.jsonl"
        journal_path.write_text(
            journal_path.read_text(encoding="utf-8").replace(
                "__REPO__", str(dead_worktree)
            ),
            encoding="utf-8",
        )

    def _git(self, *arguments: str) -> str:
        result = subprocess.run(
            ["git", *arguments],
            cwd=self.repo,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def _install_repo_conformance_authority(self) -> None:
        sources = (
            Path(".claude-plugin/plugin.json"),
            Path("agents/review-final.md"),
            Path("docs/specs/forge-plugin-spec.md"),
            Path("system/codex/agents/implementer.toml"),
            Path("system/codex/agents/plan.toml"),
            Path("system/codex/agents/review-cheap.toml"),
            Path("scripts/forge/route_config.py"),
            Path("scripts/forge/route_config_git.py"),
            Path("scripts/forge/route_config_probe.py"),
            Path("scripts/forge/route_evidence.py"),
            Path("scripts/forge/route_provenance.py"),
            Path("scripts/forge/route_vocab.py"),
            Path("tests/test_repo_conformance.py"),
        )
        for relative in sources:
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)
        (self.repo / "scripts/forge").mkdir(parents=True, exist_ok=True)
        self._git("add", *(relative.as_posix() for relative in sources))
        self._git("commit", "--quiet", "-m", "install routing authority")

    def _load_audit_module(self) -> types.ModuleType:
        name = f"audit_commitments_recorded_repository_{id(self)}"
        spec = importlib.util.spec_from_file_location(name, AUDIT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        self.addCleanup(sys.modules.pop, name, None)
        spec.loader.exec_module(module)
        return module

    def _record_repository(self, value: Path) -> None:
        journal_path = self.run_dir / "journal.jsonl"
        records = [
            json.loads(line)
            for line in journal_path.read_text(encoding="utf-8").splitlines()
        ]
        records[0]["repo"] = str(value)
        journal_path.write_text(
            "".join(
                json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
                for record in records
            ),
            encoding="utf-8",
        )

    def _invoke_audit(self, module: types.ModuleType) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = module.main(["--run-dir", str(self.run_dir)])
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def _assert_fixed_layout_refusal(self, module: types.ModuleType) -> None:
        legacy_resolver = module._legacy_recorded_repository
        with mock.patch.object(
            module,
            "_legacy_recorded_repository",
            wraps=legacy_resolver,
        ) as legacy:
            self.assertEqual(
                self._invoke_audit(module),
                (2, "", AUDIT_REPOSITORY_REFUSAL),
            )
        legacy.assert_not_called()

    @staticmethod
    def _independent_forge_source_root(
        start: dict[str, object], *_arguments: object
    ) -> Path | None:
        value = start.get("repo")
        if not isinstance(value, str):
            return None
        try:
            return Path(value).expanduser().resolve(strict=True)
        except (OSError, RuntimeError, ValueError):
            return None

    def test_dead_worktree_audit_still_runs_repository_conformance(self) -> None:
        module = self._load_audit_module()

        rendered = module.audit(self.run_dir)

        self.assertIn(HISTORICAL_ROUTING_HEADING, rendered)
        with mock.patch.object(
            module,
            "forge_source_root",
            side_effect=self._independent_forge_source_root,
        ):
            disabled = module.audit(self.run_dir)
        with self.assertRaises(AssertionError):
            self.assertIn(HISTORICAL_ROUTING_HEADING, disabled)
        self.assertNotIn(HISTORICAL_ROUTING_HEADING, disabled)

    def test_fixed_layout_absent_outside_worktrees_refuses_without_fallback(
        self,
    ) -> None:
        self._record_repository(self.repo.resolve() / "absent-repository")
        module = self._load_audit_module()

        self._assert_fixed_layout_refusal(module)

        original_fail = module.fail

        def disabled_mapping(exit_code: int, diagnostic: str) -> None:
            if (
                exit_code == 2
                and diagnostic
                == "run_started repo must name an existing absolute directory"
            ):
                raise module.recorded_repository_engine.ResolutionError
            original_fail(exit_code, diagnostic)

        with mock.patch.object(
            module, "fail", side_effect=disabled_mapping
        ), self.assertRaises(AssertionError):
            self._assert_fixed_layout_refusal(module)

    def test_fixed_layout_foreign_repository_refuses_without_fallback(
        self,
    ) -> None:
        foreign = Path(self.temporary.name) / "foreign"
        init_quiet_repository(foreign, "--quiet").check_returncode()
        (foreign / "docs").mkdir()
        (foreign / "docs/repo-basis.md").write_text(
            "# Foreign repository basis\n", encoding="utf-8"
        )
        self._record_repository(foreign.resolve())
        module = self._load_audit_module()

        self._assert_fixed_layout_refusal(module)

        with mock.patch.object(
            module.journal_engine,
            "_layout_repository_root",
            return_value=None,
        ), self.assertRaises(AssertionError):
            self._assert_fixed_layout_refusal(module)


if __name__ == "__main__":
    unittest.main()
