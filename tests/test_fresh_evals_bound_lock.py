from __future__ import annotations

import contextlib
import contextvars
import hashlib
import io
import json
import os
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import cast
from unittest import mock

from tests import test_cli_chain as cli_support
from tests._cli_loader import load_cli, package_module, patch_engine
from tests._fresh_eval_support import (
    FRESH,
    FreshEvalRepo,
    MemoryArtifacts,
    ScriptedLauncher,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from codex_orchestrator import batch  # noqa: E402

CLI = load_cli("forge_fresh_evals_bound_lock_tests")
ENGINE = package_module("engine")
RUNTIME = package_module("runtime")


class _BareContext:
    def run(self, function, *args, **kwargs):
        return function(*args, **kwargs)


class FreshEvalBoundLockTests(unittest.TestCase):
    LOCK_KEY = "forge-test-fresh-evals-bound-lock"

    def setUp(self) -> None:
        active = batch._active_locks()
        self.assertNotIn(self.LOCK_KEY, active)
        active[self.LOCK_KEY] = cast(batch.BatchLock, object())
        self.addCleanup(active.pop, self.LOCK_KEY, None)

    def _collect(self, request_id: str):
        with FreshEvalRepo() as repository, MemoryArtifacts() as artifacts:
            repository.stage_append("rules/review-constitution.md")
            snapshot = repository.snapshot()
            evaluation = repository.evaluation(
                snapshot,
                request_id=request_id,
                request_is_persisted=lambda: self.LOCK_KEY in batch._active_locks(),
            )
            expected = [item["fixture_id"] for item in evaluation.fixture_packages]
            launcher = ScriptedLauncher(repository.expected_verdicts)
            outcome = FRESH.collect(evaluation, artifacts, launcher=launcher)
        return outcome, launcher, expected

    def test_active_lock_registry_propagates_only_through_copied_context(self) -> None:
        def lock_is_registered() -> bool:
            return self.LOCK_KEY in batch._active_locks()

        with ThreadPoolExecutor(max_workers=1) as pool:
            propagated = pool.submit(
                contextvars.copy_context().run, lock_is_registered
            ).result()
            bare = pool.submit(lock_is_registered).result()

        self.assertTrue(propagated)
        self.assertFalse(bare)

    def test_collect_worker_probe_sees_calling_context_lock_registry(self) -> None:
        outcome, launcher, expected = self._collect("a" * 32)

        self.assertEqual(outcome.exit_code, 0, outcome.diagnostic)
        self.assertCountEqual(launcher.started, expected)

    def test_collect_refuses_when_worker_context_propagation_is_disabled(self) -> None:
        with mock.patch.object(
            FRESH.contextvars,
            "copy_context",
            side_effect=_BareContext,
        ):
            outcome, launcher, _expected = self._collect("b" * 32)

        self.assertEqual(outcome.exit_code, 2)
        self.assertEqual(
            outcome.diagnostic,
            "forge: fresh reviewer eval evidence invalid: "
            "fresh request was not durable before reviewer launch",
        )
        self.assertEqual(launcher.started, [])


class FreshEvalBoundChainTests(cli_support.ForgeCLIFixture):
    TARGET = "scripts/forge/forge_cli/engine/bound_eval_target.py"
    RUN_ID = "run-20260924-fresh-evals-bound-lock"

    def setUp(self) -> None:
        super().setUp()
        self.fresh_repository = FreshEvalRepo()
        self.addCleanup(self.fresh_repository.cleanup)
        self._install_fresh_evaluation_inputs()
        target = self.repo / self.TARGET
        target.parent.mkdir(parents=True)
        target.write_text("VALUE = 1\n", encoding="utf-8")
        self.git("add", "--all")
        self.git("commit", "--quiet", "-m", "fresh evaluation controls")

    @staticmethod
    def _key(label: str) -> str:
        return hashlib.sha256(label.encode("utf-8")).hexdigest()

    def _install_fresh_evaluation_inputs(self) -> None:
        source_root = self.fresh_repository.root
        relatives = (
            ".codex/agents/review-cheap.toml",
            ".codex/config.toml",
            ".forge/history/gotchas.md",
            "rules/review-constitution.md",
            "system/codex/agents/review-cheap.toml",
            "system/codex/config.toml",
            "system/codex/prompts/review-cheap.md",
        )
        for relative in relatives:
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((source_root / relative).read_bytes())
        task_source = source_root / ".forge/evals/tasks"
        task_target = self.repo / ".forge/evals/tasks"
        task_target.mkdir(parents=True)
        for source in task_source.iterdir():
            if source.is_file():
                (task_target / source.name).write_bytes(source.read_bytes())

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

    def _start_bound_chain(self) -> str:
        _batch, builders, _journal = CLI._coordination_modules()
        with self._cli_process_context():
            builders.run_open(
                self.repo,
                self.RUN_ID,
                idempotency_key=self._key("run-open"),
                goal="Exercise a run-bound fresh reviewer evaluation",
                scope=["scripts/forge/forge_cli/engine/**"],
                plugin_ref="forge-fresh-evals-bound-lock-test",
            )
            builders.task_start(
                self.repo,
                self.RUN_ID,
                idempotency_key=self._key("task-start"),
                task="task-01",
                goal="Verify the bound worker durability probe",
                acceptance=["The fresh reviewer evaluation passes"],
                files=[self.TARGET],
            )
        (self.repo / self.TARGET).write_text("VALUE = 2\n", encoding="utf-8")
        exit_code, envelope = self._invoke_cli(
            "--run-id",
            self.RUN_ID,
            "commit",
            "start",
            "--paths",
            self.TARGET,
            "--task",
            "task-01",
        )
        self.assertEqual(exit_code, 0, envelope)
        return str(envelope["chain_id"])

    def test_run_bound_verify_collects_fresh_reviewer_evidence(self) -> None:
        chain_id = self._start_bound_chain()
        launcher = ScriptedLauncher(self.fresh_repository.expected_verdicts)

        with mock.patch.object(
            FRESH, "NativeReviewerLauncher", return_value=launcher
        ):
            exit_code, envelope = self._invoke_cli(
                "--chain-id", chain_id, "verify"
            )

        self.assertEqual(exit_code, 0, envelope)
        state = self.state(chain_id)
        request = state["steps"]["fresh-reviewer-evals-requests"][-1]
        result = state["steps"]["fresh-reviewer-evals"][-1]
        self.assertEqual(result["result"], "passed")
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["outcome"], "PASS")
        self.assertCountEqual(
            launcher.started,
            [item["fixture_id"] for item in request["fixture_packages"]],
        )
        self.assertTrue((self.repo / result["manifest"]).is_file())


if __name__ == "__main__":
    unittest.main()
