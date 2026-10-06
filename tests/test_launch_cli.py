"""CLI parsing, validation, dispatch, and hermetic typed-launch integration."""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import unittest
from unittest import mock

from tests._cli_loader import load_cli, patch_engine
from tests._launch_support import (
    LaunchLaneSupport,
    wait_path,
)

CLI = load_cli("forge_launch_cli_tests")

MUTATING_LAUNCH_WARNINGS = (
    "forge: journal warning — this append makes a passed close impossible as "
    "recorded: execution codex-implementer-01/execution-01 has no terminal "
    "execution_result\n"
    "forge: journal warning — this append makes a passed close impossible as "
    "recorded: run closed as passed without a passing 'gate-1' verification "
    "after the last mutating execution\n"
    "forge: journal warning — this append makes a passed close impossible as "
    "recorded: run closed as passed without a passing 'gate-2' verification "
    "after the last mutating execution\n"
    "forge: journal warning — this append makes a passed close impossible as "
    "recorded: run closed as passed without a passing 'gate-3: review-final "
    "verdict' verification after the last mutating execution\n"
)
PLAN_LAUNCH_WARNING = (
    "forge: journal warning — this append makes a passed close impossible as "
    "recorded: execution claude-plan-01/execution-02 has no terminal "
    "execution_result\n"
)


class LaunchCLIParsingTests(LaunchLaneSupport, unittest.TestCase):
    def _dispatch(self, argv: list[str]) -> tuple[object, mock.Mock]:
        _options, remaining = CLI._extract_global_options(argv)
        parsed = CLI.build_parser().parse_args(remaining)
        engine = mock.Mock()
        sentinel = object()
        engine.launch.return_value = sentinel
        engine.launch_collect.return_value = sentinel
        engine.launch_cancel.return_value = sentinel
        self.assertIs(CLI.dispatch(engine, parsed), sentinel)
        return parsed, engine

    def _refusal(
        self, argv: list[str], *, schema: str = "forge-cli/2"
    ) -> dict[str, object]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(CLI.Repository, "discover") as discover,
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            discover.side_effect = AssertionError("repository discovery was reached")
            status = CLI.main(["--json", *argv])
        discover.assert_not_called()
        self.assertEqual(status, 1)
        self.assertEqual(stderr.getvalue(), "")
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["schema"], schema)
        return payload

    def _start(self) -> list[str]:
        return [
            "launch",
            "--role",
            "implementer",
            "--task",
            self.task_id,
            "--worktree",
            str(self.linked_worktree),
            "--brief",
            str(self.brief),
        ]

    def _globals(self) -> list[str]:
        return ["--repo", str(self.repo), "--run-id", self.run_id]

    def test_parse_and_dispatch_all_three_forms(self) -> None:
        parsed, engine = self._dispatch([*self._globals(), *self._start()])
        self.assertIsNone(parsed.launch_command)
        engine.launch.assert_called_once_with(
            role="implementer",
            task=self.task_id,
            worktree=str(self.linked_worktree),
            brief=str(self.brief),
        )

        parsed, engine = self._dispatch(
            [*self._globals(), "launch", "collect", "--execution", "execution-01"]
        )
        self.assertEqual(parsed.launch_command, "collect")
        engine.launch_collect.assert_called_once_with("execution-01")

        parsed, engine = self._dispatch(
            [*self._globals(), "launch", "cancel", "--execution", "execution-02"]
        )
        self.assertEqual(parsed.launch_command, "cancel")
        engine.launch_cancel.assert_called_once_with("execution-02")

    def test_launch_cross_option_literals_and_reason_codes(self) -> None:
        cases = (
            (
                self._start(),
                "state-precondition",
                "forge: launch refused — explicit --repo and --run-id are required",
            ),
            (
                [
                    *self._globals(),
                    "--chain-id",
                    "c-2026-08-28T120000Z-cafe",
                    *self._start(),
                ],
                "state-precondition",
                "forge: launch refused — --chain-id is not admitted",
            ),
            (
                [*self._globals(), "--chain-id", "malformed", *self._start()],
                "state-precondition",
                "forge: launch refused — --chain-id is not admitted",
            ),
            (
                [*self._globals(), "launch", "--role", "implementer"],
                "state-precondition",
                "forge: launch refused — --role, --task, --worktree and --brief "
                "are required, and --execution is not admitted",
            ),
            (
                [*self._globals(), *self._start(), "--execution", "execution-01"],
                "state-precondition",
                "forge: launch refused — --role, --task, --worktree and --brief "
                "are required, and --execution is not admitted",
            ),
            (
                [*self._globals(), "launch", "collect"],
                "state-precondition",
                "forge: launch collect refused — exactly --execution execution-NN "
                "is required",
            ),
            (
                [
                    *self._globals(),
                    "launch",
                    "cancel",
                    "--execution",
                    "execution-1",
                ],
                "state-precondition",
                "forge: launch cancel refused — exactly --execution execution-NN "
                "is required",
            ),
        )
        for argv, reason, message in cases:
            with self.subTest(message=message):
                payload = self._refusal(argv)
                self.assertEqual(payload["reason_code"], reason)
                self.assertEqual(payload["message"], message)

    def test_collect_and_cancel_reject_every_start_option(self) -> None:
        options = (
            ("--role", "implementer"),
            ("--task", self.task_id),
            ("--worktree", str(self.linked_worktree)),
            ("--brief", str(self.brief)),
        )
        for command in ("collect", "cancel"):
            for option in options:
                with self.subTest(command=command, option=option[0]):
                    payload = self._refusal(
                        [
                            *self._globals(),
                            "launch",
                            command,
                            "--execution",
                            "execution-01",
                            *option,
                        ]
                    )
                    self.assertEqual(payload["reason_code"], "state-precondition")
                    self.assertEqual(
                        payload["message"],
                        f"forge: launch {command} refused — exactly --execution "
                        "execution-NN is required",
                    )

    def test_help_names_launch_run_and_task_options(self) -> None:
        help_text = CLI.build_parser().format_help()
        self.assertIn("--run-id RUN_ID    name the launch journal", help_text)
        self.assertIn("--task TASK_ID is a launch option naming the task.", help_text)
        self.assertNotIn("journal ingest-chain", help_text)
        launch = CLI.build_parser().parse_args(self._start())
        self.assertEqual((launch.role, launch.task), ("implementer", self.task_id))

    def test_malformed_launch_grammar_uses_revision9_envelope(self) -> None:
        payload = self._refusal(["launch", "bogus"])
        self.assertEqual(payload["schema"], "forge-cli/2")

    def test_launch_as_legacy_extra_token_does_not_select_revision9(self) -> None:
        payload = self._refusal(["status", "launch"], schema="forge-cli/1")
        self.assertEqual(payload["reason_code"], "state-precondition")

    def test_run_id_remains_refused_for_an_unrelated_later_verb(self) -> None:
        payload = self._refusal(["--run-id", self.run_id, "status"])
        self.assertEqual(payload["reason_code"], "state-precondition")
        self.assertEqual(
            payload["message"],
            "forge: status refused — --run-id and --task are not admitted",
        )


class LaunchCLIIntegrationTests(LaunchLaneSupport, unittest.TestCase):
    def _invoke(
        self, argv: list[str], *, expected_stderr: str
    ) -> tuple[int, dict[str, object]]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = CLI.main(["--json", *argv])
        self.assertEqual(stderr.getvalue(), expected_stderr)
        return status, json.loads(stdout.getvalue())

    def _launch_and_collect(
        self, role: str, *, expected_launch_stderr: str
    ) -> None:
        common = ["--repo", str(self.repo), "--run-id", self.run_id]
        status, launched = self._invoke(
            [
                *common,
                "launch",
                "--role",
                role,
                "--task",
                self.task_id,
                "--worktree",
                str(self.linked_worktree),
                "--brief",
                str(self.brief),
            ],
            expected_stderr=expected_launch_stderr,
        )
        self.assertEqual(status, 0, launched)
        record = self.execution_records()[-1]
        self.assertIn(str(record["execution"]), launched["message"])
        wait_path(self.attempt_dir(record) / "completion.json")
        status, collected = self._invoke(
            [
                *common,
                "launch",
                "collect",
                "--execution",
                str(record["execution"]),
            ],
            expected_stderr="",
        )
        self.assertEqual(status, 0, collected)
        self.assertEqual(collected["state"], "complete")

    def test_codex_and_claude_are_hermetic_and_explicit(self) -> None:
        self.assertIsNone(shutil.which("codex", path=os.environ["PATH"]))
        self.assertIsNone(shutil.which("claude", path=os.environ["PATH"]))
        codex = self.install_provider("codex", executable_name="typed-codex-fixture")
        claude = self.install_provider("claude", executable_name="typed-claude-fixture")
        self.configure_route("implementer", "codex")
        self.configure_route("plan", "claude")
        self.open_run_and_task()
        with (
            patch_engine("CODEX_EXECUTABLE", str(codex)),
            patch_engine("CLAUDE_EXECUTABLE", str(claude)),
        ):
            self._launch_and_collect(
                "implementer",
                expected_launch_stderr=MUTATING_LAUNCH_WARNINGS,
            )
            self._launch_and_collect(
                "plan", expected_launch_stderr=PLAN_LAUNCH_WARNING
            )
        results = [row for row in self.records() if row.get("type") == "execution_result"]
        self.assertEqual([row["status"] for row in results], ["complete", "complete"])
        self.assertTrue((self.logs / "codex.argv.json").is_file())
        self.assertTrue((self.logs / "claude.argv.json").is_file())


if __name__ == "__main__":
    unittest.main()
