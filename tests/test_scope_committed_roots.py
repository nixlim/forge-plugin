from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

from tests import test_cli_chain as cli_support
from tests._cli_loader import load_cli, package_module, patch_engine
from tests._revision8_support import Revision8Support

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from codex_orchestrator import journal  # noqa: E402

CANDIDATE = package_module("candidate")
CLI = load_cli("forge_scope_committed_roots_tests")
RUNTIME = package_module("runtime")

ADMITTED = (
    ".forge/evals/tasks/fr230-phase3-4-v2.manifest.json",
    ".forge/evals/**",
    ".forge/evals/candidates/x.md",
    ".forge/history/runs/x/archive.md",
)
REFUSED = (
    ".forge",
    ".forge/evals",
    ".forge/history",
    ".forge/*",
    ".forge/eval*/x",
    ".forge/tmp/run-registry.json",
    ".forge/chains/x.json",
    ".forge/local/routes.toml",
    ".forge/other/x",
    ".codex-orchestrator/runs/x/journal.jsonl",
    ".worktrees/x/y",
)


class ScopeCommittedRootPredicateTests(unittest.TestCase):
    def test_admission_matrix_matches_journal_and_candidate_contracts(self) -> None:
        for value in ADMITTED:
            with self.subTest(value=value):
                self.assertTrue(journal._valid_scope_item(value))
                self.assertEqual(journal.canonical_scope([value]), (value,))
                self.assertTrue(CANDIDATE.valid_scope_path(value))

        for value in REFUSED:
            with self.subTest(value=value):
                self.assertFalse(journal._valid_scope_item(value))
                with self.assertRaises(journal.CoordinationRefusal):
                    journal.canonical_scope([value])
                self.assertFalse(CANDIDATE.valid_scope_path(value))

    def test_committed_subtree_controls_are_load_bearing(self) -> None:
        with mock.patch.object(journal, "_scope_root_admitted", return_value=False):
            for value in ADMITTED:
                with self.subTest(module="journal", value=value):
                    self.assertFalse(journal._valid_scope_item(value))
                    with self.assertRaises(journal.CoordinationRefusal):
                        journal.canonical_scope([value])

        with mock.patch.object(CANDIDATE, "_scope_root_admitted", return_value=False):
            for value in ADMITTED:
                with self.subTest(module="candidate", value=value):
                    self.assertFalse(CANDIDATE.valid_scope_path(value))


class ScopeCommittedRootTypedCliTests(Revision8Support, unittest.TestCase):
    RUN_ID = "run-committed-forge-scope"

    def _typed_open(self, run_id: str, *scope: str):
        arguments = [
            "run-open",
            "--repo",
            str(self.repo),
            "--run-id",
            run_id,
            "--idempotency-key",
            "1" * 64,
            "--goal",
            "Exercise committed Forge scope",
            "--plugin-ref",
            "forge-scope-committed-roots-test",
        ]
        for value in scope:
            arguments.extend(("--scope", value))
        return self.command(*arguments)

    def _registry_scope(self, run_id: str) -> list[str]:
        registry = json.loads(self.registry_path.read_bytes())
        return next(
            item["scope"]
            for item in registry["open_runs"]
            if item["run_id"] == run_id
        )

    def test_typed_open_and_readmit_persist_committed_forge_scope(self) -> None:
        initial = [
            ".forge/evals/tasks/x.json",
            "scripts/x.py",
        ]
        opened = self._typed_open(self.RUN_ID, *initial)

        self.assertEqual(opened.returncode, 0, opened.stderr)
        self.assertEqual(self._registry_scope(self.RUN_ID), initial)

        widened = [
            ".forge/evals/tasks/x.json",
            ".forge/history/runs/x.md",
            "scripts/x.py",
        ]
        readmitted = self.readmit(self.RUN_ID, *widened)

        self.assertEqual(readmitted.returncode, 0, readmitted.stderr)
        self.assertEqual(self._registry_scope(self.RUN_ID), widened)

    def test_escape_refusals_remain_byte_identical(self) -> None:
        invalid_open = self._typed_open("run-invalid-committed-scope", "../escape")
        self.assertEqual(invalid_open.returncode, 1)
        self.assertEqual(
            invalid_open.stderr,
            "forge: new run refused — invalid scope\n",
        )

        self.assertEqual(self._typed_open(self.RUN_ID, "scripts/**").returncode, 0)
        invalid_readmit = self.readmit(self.RUN_ID, "../escape")
        self.assertEqual(invalid_readmit.returncode, 1)
        self.assertEqual(
            invalid_readmit.stderr,
            "forge: run readmit refused — invalid scope\n",
        )


class ScopeCommittedRootBoundCandidateTests(cli_support.ForgeCLIFixture):
    RUN_ID = "run-bound-committed-forge-scope"
    TARGET = ".forge/evals/tasks/bound_subject.py"

    def setUp(self) -> None:
        super().setUp()
        target = self.repo / self.TARGET
        target.parent.mkdir(parents=True)
        target.write_text("VALUE = 1\n", encoding="utf-8")
        self.git("add", "--all")
        self.git("commit", "--quiet", "-m", "committed Forge subject")

    @contextlib.contextmanager
    def _cli_process_context(self):
        environment = self.environment(FORGE_SESSION_PID=str(os.getpid()))
        with (
            mock.patch.dict(os.environ, environment, clear=True),
            mock.patch.object(RUNTIME, "SCRIPT_DIR", self.helpers),
            mock.patch.object(RUNTIME, "PLUGIN_ROOT", ROOT),
            patch_engine("CODEX_EXECUTABLE", str(self.helpers / "fake-codex")),
        ):
            yield

    def _invoke_cli(self, *argv: str) -> tuple[int, dict[str, object]]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            self._cli_process_context(),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = CLI.main(["--json", "--repo", str(self.repo), *argv])
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(stdout.getvalue().count("\n"), 1)
        envelope = json.loads(stdout.getvalue())
        self.assertEqual(set(envelope), cli_support.ENVELOPE_KEYS)
        return exit_code, envelope

    def _prepare_bound_change(self) -> None:
        _batch, builders, _journal = CLI._coordination_modules()
        with self._cli_process_context():
            builders.run_open(
                self.repo,
                self.RUN_ID,
                idempotency_key="2" * 64,
                goal="Exercise a run-bound committed Forge subject",
                scope=[self.TARGET],
                plugin_ref="forge-scope-committed-roots-test",
            )
            builders.task_start(
                self.repo,
                self.RUN_ID,
                idempotency_key="3" * 64,
                task="task-01",
                goal="Change the committed Forge subject",
                acceptance=["The run-bound candidate starts"],
                files=[self.TARGET],
            )
        (self.repo / self.TARGET).write_text("VALUE = 2\n", encoding="utf-8")

    def _start_bound_chain(self) -> tuple[int, dict[str, object]]:
        return self._invoke_cli(
            "--run-id",
            self.RUN_ID,
            "commit",
            "start",
            "--paths",
            self.TARGET,
            "--task",
            "task-01",
        )

    def test_run_bound_commit_start_admits_committed_forge_subject(self) -> None:
        self._prepare_bound_change()

        exit_code, envelope = self._start_bound_chain()

        self.assertEqual(exit_code, 0, envelope)
        state = self.state(str(envelope["chain_id"]))
        self.assertEqual(state["paths"], [self.TARGET])
        self.assertEqual(
            state["run_binding"],
            {
                "policy_digest": state["policy_source"]["digest"],
                "repository": str(self.repo),
                "run_id": self.RUN_ID,
                "task_id": "task-01",
            },
        )

    def test_run_bound_commit_start_refuses_when_carveout_is_disabled(self) -> None:
        self._prepare_bound_change()

        with mock.patch.object(CANDIDATE, "_COMMITTED_FORGE_SUBTREES", ()):
            exit_code, envelope = self._start_bound_chain()

        self.assertEqual(exit_code, 1, envelope)
        self.assertEqual(envelope["reason_code"], "run-task-binding-invalid")
        self.assertEqual(
            envelope["message"],
            "forge: commit start refused — run/task binding is invalid",
        )


if __name__ == "__main__":
    unittest.main()
