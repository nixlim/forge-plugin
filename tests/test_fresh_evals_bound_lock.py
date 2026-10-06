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
from tests._fresh_eval_support import (
    FRESH,
    FreshEvalRepo,
    ScriptedLauncher,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


CLI = load_cli("forge_fresh_evals_bound_lock_tests")
ENGINE = package_module("engine")
RUNTIME = package_module("runtime")






class FreshEvalChainTests(cli_support.ForgeCLIFixture):
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

    def _start_chain(self) -> str:
        (self.repo / self.TARGET).write_text("VALUE = 2\n", encoding="utf-8")
        exit_code, envelope = self._invoke_cli(
            "commit",
            "start",
            "--paths",
            self.TARGET,
        )
        self.assertEqual(exit_code, 0, envelope)
        return str(envelope["chain_id"])

    def test_chain_verify_collects_fresh_reviewer_evidence(self) -> None:
        chain_id = self._start_chain()
        launcher = ScriptedLauncher(self.fresh_repository.expected_verdicts)

        with mock.patch.object(
            FRESH, "NativeReviewerLauncher", return_value=launcher
        ), mock.patch.object(RUNTIME, "_coordination_modules",
                             side_effect=AssertionError("journal consulted")):
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
