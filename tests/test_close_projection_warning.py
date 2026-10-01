"""Passed-close projection warnings for typed journal appends."""

from __future__ import annotations

import contextlib
import io
import json
import os
import shlex
import shutil
import unittest
from pathlib import Path
from unittest import mock

from tests import test_result_before_gate as RESULT_BEFORE_GATE
from tests._revision9_coord_constants import key
from tests._revision9_coord_support import Revision9BuilderBatchSupport

import codex_orch_tools
from codex_orchestrator import builders, close_law, journal, result_gate

WARNING_PREFIX = (
    "forge: journal warning — this append makes a passed close impossible "
    "as recorded: "
)
MISSING_GATE_ISSUES = (
    "execution codex-impl-01/execution-01 has no terminal execution_result",
    "run closed as passed without a passing 'gate-1' verification after "
    "the last mutating execution",
    "run closed as passed without a passing 'gate-2' verification after "
    "the last mutating execution",
    "run closed as passed without a passing 'gate-3: review-final verdict' "
    "verification after the last mutating execution",
)
BOUND_GATE_CASES = (
    ("commit restage", ("commit", "restage", "--paths", "src/app.py")),
    ("commit rebase", ("commit", "rebase")),
    ("verify", ("verify",)),
    ("gate run", ("gate", "run", "gate-1")),
    ("review request", ("review", "request")),
)


class CloseProjectionWarningTests(
    Revision9BuilderBatchSupport, unittest.TestCase
):
    """Exercise the codex_orch_tools warning channel after durable appends."""

    FIXED_TIME = "2026-09-30T12:00:00Z"
    CHAIN_ID = "c-2026-09-30T115900Z-a701"

    def setUp(self) -> None:
        super().setUp()
        self.env.pop("CLAUDE_CODE_SESSION_ID", None)

    @staticmethod
    def _binding(seed: str, *, reviewed: bool = False) -> dict[str, object]:
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
                "chain_id": CloseProjectionWarningTests.CHAIN_ID,
                "event_digest": key(f"{seed}-event"),
            },
            "candidate": {
                "kind": "staged-diff-sha256",
                "value": key("close-projection-warning-candidate"),
            },
            "review": review,
        }
        return {
            **preimage,
            "binding_id": journal._sha256(
                journal._canonical_json_bytes(preimage)
            ),
        }

    def _open_task(self, name: str) -> tuple[str, dict[str, object]]:
        run_id = f"run-20260930-warning-{name}"
        with self.api_environment():
            opening = self.open_run(self.repo, run_id).records[0]
            self.start_task(self.repo, run_id)
        run_dir = self.run_dir(self.repo, run_id)
        for relative in ("prompt.md", "events.jsonl", "handoff.md"):
            (run_dir / relative).write_text(
                "synthetic warning evidence\n", encoding="utf-8"
            )
        return run_id, dict(opening)

    def _add_gate(self, run_id: str, criterion: str, seed: str) -> str:
        binding = self._binding(
            seed, reviewed=criterion == journal.GATE_3_CRITERION
        )
        with self.api_environment(), mock.patch.object(
            builders, "resolve_binding", return_value=binding
        ):
            builders.verification_add(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-{seed}"),
                task="task-01",
                criterion=criterion,
                method="unittest",
                check="python3 -m unittest synthetic",
                result="passed",
                observation="synthetic bound gate passed",
                evidence=[],
                binding_chain=self.CHAIN_ID,
                binding_id=str(binding["binding_id"]),
            )
        return str(binding["binding_id"])

    def _add_clean_landing(self, run_id: str) -> str:
        first_binding = self._add_gate(
            run_id, "gate-1: project tests", "gate-1"
        )
        self._add_gate(run_id, "gate-2: stack checks", "gate-2")
        self._add_gate(run_id, journal.GATE_3_CRITERION, "gate-3")
        binding = self._binding("landing")
        with self.api_environment(), mock.patch.object(
            builders, "resolve_binding", return_value=binding
        ):
            builders.decision_add(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-landing"),
                task="task-01",
                resolution="The synthetic candidate landed",
                finding=None,
                outcome="chain-landing",
                risk=None,
                basis=[],
                binding_chain=self.CHAIN_ID,
                binding_id=str(binding["binding_id"]),
            )
        return first_binding

    @staticmethod
    def _implementer(opening: dict[str, object]) -> dict[str, object]:
        route = opening["route"]
        assert isinstance(route, dict)
        implementer = route["implementer"]
        assert isinstance(implementer, dict)
        return implementer

    def _execution_start_argv(
        self,
        run_id: str,
        opening: dict[str, object],
        *,
        idempotency_key: str,
    ) -> list[str]:
        implementer = self._implementer(opening)
        sandbox = journal.route_evidence.route_config.profile_sandbox(
            str(implementer["provider"]), "implementer"
        )
        return [
            "journal",
            "execution-start",
            "--repo",
            str(self.repo.resolve()),
            "--run-id",
            run_id,
            "--idempotency-key",
            idempotency_key,
            "--agent",
            "codex-impl-01",
            "--task",
            "task-01",
            "--provider",
            str(implementer["provider"]),
            "--role",
            "implementer",
            "--mode",
            "headless",
            "--sandbox",
            sandbox,
            "--route-source",
            str(implementer["route_source"]),
            "--route-sha256",
            str(implementer["route_sha256"]),
            "--model",
            str(implementer["model"]),
            "--effort",
            str(implementer["effort"]),
            "--worktree",
            str(self.repo.resolve()),
            "--head",
            self.head,
            "--prompt",
            "prompt.md",
            "--handoff",
            "handoff.md",
            "--event-source",
            "exec",
            "--events",
            "events.jsonl",
        ]

    def _execution_result_argv(
        self, run_id: str, *, idempotency_key: str
    ) -> list[str]:
        return [
            "journal",
            "execution-result",
            "--repo",
            str(self.repo.resolve()),
            "--run-id",
            run_id,
            "--idempotency-key",
            idempotency_key,
            "--execution",
            "execution-01",
            "--agent",
            "codex-impl-01",
            "--task",
            "task-01",
            "--status",
            "complete",
            "--summary",
            "Synthetic implementation completed",
            "--file-changed",
            "src/example.py",
            "--handoff",
            "handoff.md",
        ]

    def _task_finish_argv(
        self, run_id: str, *, idempotency_key: str
    ) -> list[str]:
        return [
            "journal",
            "task-finish",
            "--repo",
            str(self.repo.resolve()),
            "--run-id",
            run_id,
            "--idempotency-key",
            idempotency_key,
            "--task",
            "task-01",
            "--status",
            "complete",
        ]

    def _invoke(self, argv: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            self.api_environment(),
            mock.patch.object(journal, "_utc_now", return_value=self.FIXED_TIME),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = codex_orch_tools._typed_main(argv)
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def _seed_execution(
        self, run_id: str, opening: dict[str, object]
    ) -> None:
        implementer = self._implementer(opening)
        with self.api_environment():
            outcome = builders.execution_start(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-seed-execution"),
                agent="codex-impl-01",
                task="task-01",
                provider=str(implementer["provider"]),
                role="implementer",
                mode="headless",
                model=str(implementer["model"]),
                effort=str(implementer["effort"]),
                worktree=str(self.repo.resolve()),
                head=self.head,
                prompt="prompt.md",
                handoff="handoff.md",
                event_source="exec",
                events="events.jsonl",
                sandbox=journal.route_evidence.route_config.profile_sandbox(
                    str(implementer["provider"]), "implementer"
                ),
                route_source=str(implementer["route_source"]),
                route_sha256=str(implementer["route_sha256"]),
            )
        self.assertEqual(outcome.records[0]["execution"], "execution-01")

    def _snapshot_run_state(self, label: str) -> tuple[Path, bytes | None]:
        state_root = self.repo / ".codex-orchestrator"
        backup = Path(self.temporary.name) / f"{label}-state-backup"
        shutil.copytree(state_root, backup)
        registry = self.repo / ".forge/tmp/run-registry.json"
        registry_bytes = registry.read_bytes() if registry.is_file() else None
        return backup, registry_bytes

    def _restore_run_state(
        self, backup: Path, registry_bytes: bytes | None
    ) -> None:
        state_root = self.repo / ".codex-orchestrator"
        shutil.rmtree(state_root)
        shutil.copytree(backup, state_root)
        registry = self.repo / ".forge/tmp/run-registry.json"
        if registry_bytes is None:
            if registry.exists():
                registry.unlink()
        else:
            registry.parent.mkdir(parents=True, exist_ok=True)
            registry.write_bytes(registry_bytes)

    def test_execution_start_warns_and_control_is_load_bearing(self) -> None:
        run_id, opening = self._open_task("execution-start")
        self._add_clean_landing(run_id)
        argv = self._execution_start_argv(
            run_id,
            opening,
            idempotency_key=key(f"{run_id}-execution-start"),
        )
        backup, registry = self._snapshot_run_state("execution-start")
        expected = [WARNING_PREFIX + issue for issue in MISSING_GATE_ISSUES]

        original_project = close_law.project_close
        held_during_projection: list[bool] = []

        def project_with_lock_check(*args: object, **kwargs: object) -> object:
            run_dir = self.run_dir(self.repo, run_id)
            held_during_projection.append(
                os.path.abspath(os.fspath(run_dir))
                in journal._held_batch_locks()
            )
            return original_project(*args, **kwargs)

        with mock.patch.object(
            close_law, "project_close", side_effect=project_with_lock_check
        ):
            exit_code, enabled_stdout, enabled_stderr = self._invoke(argv)
        self.assertEqual(exit_code, 0, enabled_stderr)
        self.assertEqual(held_during_projection, [True, True])

        def assert_positive(stderr: str) -> None:
            self.assertEqual(stderr.splitlines(), expected)

        assert_positive(enabled_stderr)
        self.assertEqual(json.loads(enabled_stdout)["repeated"], False)

        self._restore_run_state(backup, registry)
        disabled = result_gate.RESULT_GATE_CONTROLS - {
            "close-projection-warning"
        }
        with mock.patch.object(
            result_gate, "RESULT_GATE_CONTROLS", disabled
        ):
            disabled_code, disabled_stdout, disabled_stderr = self._invoke(argv)
        with self.assertRaises(AssertionError):
            assert_positive(disabled_stderr)
        self.assertEqual(disabled_code, 0, disabled_stderr)
        self.assertEqual(disabled_stdout, enabled_stdout)
        self.assertEqual(disabled_stderr, "")

    def test_execution_result_after_landing_warns_once(self) -> None:
        run_id, opening = self._open_task("execution-result")
        first_binding = self._add_clean_landing(run_id)
        self._seed_execution(run_id, opening)
        argv = self._execution_result_argv(
            run_id,
            idempotency_key=key(f"{run_id}-execution-result"),
        )

        exit_code, stdout, stderr = self._invoke(argv)
        self.assertEqual(exit_code, 0, stderr)
        self.assertEqual(json.loads(stdout)["repeated"], False)
        self.assertEqual(
            stderr.splitlines(),
            [
                WARNING_PREFIX
                + f"binding {first_binding!r} precedes the last mutating "
                "execution for task 'task-01'"
            ],
        )

        repeated_code, repeated_stdout, repeated_stderr = self._invoke(argv)
        self.assertEqual(repeated_code, 0, repeated_stderr)
        self.assertEqual(json.loads(repeated_stdout)["repeated"], True)
        self.assertEqual(repeated_stderr, "")

    def test_task_finish_without_a_new_close_issue_is_quiet(self) -> None:
        run_id, _opening = self._open_task("task-finish")
        self._add_clean_landing(run_id)
        argv = self._task_finish_argv(
            run_id,
            idempotency_key=key(f"{run_id}-task-finish"),
        )

        with (
            mock.patch.object(
                builders, "_terminal_chain_guard", return_value=None
            ),
            mock.patch.object(
                result_gate,
                "append_warnings",
                wraps=result_gate.append_warnings,
            ) as warning_spy,
        ):
            exit_code, stdout, stderr = self._invoke(argv)

        self.assertEqual(exit_code, 0, stderr)
        warning_spy.assert_called_once()
        payload = json.loads(stdout)
        self.assertEqual(payload["records"][0]["status"], "complete")
        self.assertEqual(stderr, "")

    def test_internal_projection_error_preserves_exit_and_stdout(self) -> None:
        run_id, opening = self._open_task("internal-error")
        argv = self._execution_start_argv(
            run_id,
            opening,
            idempotency_key=key(f"{run_id}-execution-start"),
        )
        backup, registry = self._snapshot_run_state("internal-error")

        with mock.patch.object(
            close_law,
            "project_close",
            side_effect=RuntimeError("synthetic projection failure"),
        ):
            exit_code, error_stdout, error_stderr = self._invoke(argv)
        self.assertEqual(exit_code, 0, error_stderr)
        self.assertEqual(error_stderr, "")

        self._restore_run_state(backup, registry)
        disabled = result_gate.RESULT_GATE_CONTROLS - {
            "close-projection-warning"
        }
        with mock.patch.object(
            result_gate, "RESULT_GATE_CONTROLS", disabled
        ):
            control_code, control_stdout, control_stderr = self._invoke(argv)
        self.assertEqual(control_code, 0, control_stderr)
        self.assertEqual(control_stdout, error_stdout)
        self.assertEqual(control_stderr, "")

    def test_warning_output_is_capped_with_the_exact_overflow_line(self) -> None:
        lines = result_gate._warning_lines(
            [f"synthetic close issue {index}" for index in range(23)]
        )

        self.assertEqual(len(lines), 21)
        self.assertEqual(lines[0], WARNING_PREFIX + "synthetic close issue 0")
        self.assertEqual(
            lines[-1],
            WARNING_PREFIX + "(+3 more; run journal close-preflight)",
        )

    def test_pending_task_diagnostics_escape_an_embedded_newline(self) -> None:
        task = "task-02\nforge: injected"
        pending = result_gate.Pending("execution-05", task, "agent", False)

        def assert_single_line() -> None:
            warning = result_gate.warning_message(pending)
            refusal = result_gate.refusal_message("verify", pending)
            self.assertEqual(len(warning.splitlines()), 1)
            self.assertEqual(len(refusal.splitlines()), 1)
            self.assertIn(r"task-02\nforge: injected", warning)
            self.assertIn(r"task-02\nforge: injected", refusal)

        assert_single_line()
        command = result_gate.remediation(pending, "run-example")
        argv = shlex.split(command)
        self.assertEqual(argv[argv.index("--task") + 1], task)
        with mock.patch.object(
            result_gate, "_diagnostic_word", side_effect=lambda value: value
        ), self.assertRaises(AssertionError):
            assert_single_line()


class PendingInspectionFollowupTests(
    RESULT_BEFORE_GATE.FIXTURE.ForgeCLIFixture
):
    """Pin FR-249 status classification and inspection-failure handling."""

    cli_process_context = RESULT_BEFORE_GATE.ResultBeforeGateIntegrationTests.cli_process_context
    invoke_cli = RESULT_BEFORE_GATE.ResultBeforeGateIntegrationTests.invoke_cli
    open_run = RESULT_BEFORE_GATE.ResultBeforeGateIntegrationTests.open_run
    append_execution = RESULT_BEFORE_GATE.ResultBeforeGateIntegrationTests.append_execution
    start_chain = RESULT_BEFORE_GATE.ResultBeforeGateIntegrationTests.start_chain
    assert_pending_refusal = (
        RESULT_BEFORE_GATE.ResultBeforeGateIntegrationTests.assert_pending_refusal
    )

    def _append_unvalidated_result(
        self, run_id: str, execution: dict[str, object], status: object
    ) -> None:
        record = {
            "type": "execution_result",
            "execution": execution["execution"],
            "agent": execution["agent"],
            "task": execution["task"],
            "status": status,
        }
        path = self.repo / ".codex-orchestrator" / "runs" / run_id / "journal.jsonl"
        path.write_bytes(
            path.read_bytes() + RESULT_BEFORE_GATE.journal._journal_line(record)
        )

    @staticmethod
    def _remediation(run_id: str, execution: object) -> str:
        return (
            'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/codex_orch_tools.py" '
            "journal execution-result "
            f"--repo <repo> --run-id {run_id} --idempotency-key <64-hex> "
            f"--execution {execution} --agent <agent> --task task-01 "
            "--status <complete|blocked|failed> --summary <text>"
        )

    def _assert_inspection_refusal(
        self,
        *argv: str,
        verb: str,
        chain_id: str | None = None,
        exception_classes: tuple[str, ...] = (),
    ) -> None:
        if chain_id is not None:
            state_before = self.state_path(chain_id).read_bytes()
            events_before = self.events_path(chain_id).read_bytes()
        exit_code, envelope, stderr = self.invoke_cli(*argv)
        message = (
            f"forge: {verb} refused — pending execution_result inspection is unavailable"
        )
        self.assertEqual((exit_code, stderr), (1, ""))
        self.assertEqual(envelope["reason_code"], "run-task-binding-invalid")
        self.assertEqual(envelope["message"], message)
        self.assertEqual(envelope["expected"], "readable committed policy and run journal")
        self.assertEqual(
            envelope["remediation"],
            "inspect the run journal and committed policy, then retry",
        )
        observed = message
        if exception_classes:
            observed += "; causes " + " <- ".join(exception_classes)
        self.assertEqual(envelope["observed"], observed)
        rendered = json.dumps(envelope)
        for detail in ("inspection detail", "nested detail", "not a string"):
            self.assertNotIn(detail, rendered)
        if not exception_classes:
            for class_name in ("KeyError", "LookupError", "RuntimeError", "OSError"):
                self.assertNotIn(class_name, rendered)
        if chain_id is not None:
            self.assertEqual(self.state_path(chain_id).read_bytes(), state_before)
            self.assertEqual(self.events_path(chain_id).read_bytes(), events_before)

    def test_nonterminal_status_shapes_match_close_law_and_control(self) -> None:
        absent = object()
        cases = (
            ("missing", absent),
            ("null", None),
            ("integer", 7),
            ("list", ["complete"]),
            ("nonterminal-string", "running"),
        )

        def assert_pending(status: object) -> None:
            results = []
            for number, task in ((1, "task-01"), (2, "task-02")):
                record: dict[str, object] = {
                    "type": "execution_result",
                    "execution": f"execution-{number:02d}",
                    "agent": "codex-impl-01",
                    "task": task,
                }
                if status is not absent:
                    record["status"] = status
                results.append(record)
            records = RESULT_BEFORE_GATE.activated_records(
                RESULT_BEFORE_GATE.task_record("task-01", "src/app.py"),
                RESULT_BEFORE_GATE.task_record("task-02", "docs/guide.md"),
                RESULT_BEFORE_GATE.execution_record(1, "task-01"),
                RESULT_BEFORE_GATE.execution_record(2, "task-02"),
                *results,
            )
            blocking, advisory = result_gate.pending_mutations(
                records,
                chain_task="task-01",
                chain_paths=("src/app.py",),
                exempt_paths=(),
            )
            self.assertEqual(
                (
                    [item.execution for item in blocking],
                    [item.execution for item in advisory],
                ),
                (["execution-01"], ["execution-02"]),
            )

        for label, status in cases:
            with self.subTest(label=label):
                assert_pending(status)
        with mock.patch.object(
            result_gate, "_result_is_terminal", return_value=True
        ), self.assertRaises(AssertionError):
            assert_pending(["complete"])

    def test_commit_start_treats_malformed_result_as_pending(self) -> None:
        start_run = "run-20260930-result-start-malformed"
        start_opening = self.open_run(start_run)
        start_execution = self.append_execution(start_run, start_opening)
        self._append_unvalidated_result(start_run, start_execution, ["complete"])
        self.change("src/app.py", "VALUE = 2\n")

        def assert_start_pending() -> None:
            exit_code, envelope, stderr = self.invoke_cli(
                "--run-id", start_run, "commit", "start", "--paths", "src/app.py",
                "--task", "task-01",
            )
            self.assertEqual((exit_code, stderr), (1, ""))
            self.assert_pending_refusal(
                envelope,
                verb="commit start",
                run_id=start_run,
                execution=str(start_execution["execution"]),
                remediation=self._remediation(
                    start_run, start_execution["execution"]
                ),
            )

        assert_start_pending()
        with mock.patch.object(
            result_gate,
            "_result_is_terminal",
            side_effect=ValueError("disabled non-terminal classification"),
        ), self.assertRaises(AssertionError):
            assert_start_pending()

    def test_bound_verbs_treat_malformed_result_as_pending(self) -> None:
        bound_run = "run-20260930-result-bound-malformed"
        bound_opening = self.open_run(bound_run)
        chain_id = self.start_chain(bound_run)
        bound_execution = self.append_execution(bound_run, bound_opening)
        self._append_unvalidated_result(bound_run, bound_execution, ["complete"])

        def assert_bound_pending(verb: str, argv: tuple[str, ...]) -> None:
            state_before = self.state_path(chain_id).read_bytes()
            events_before = self.events_path(chain_id).read_bytes()
            exit_code, envelope, stderr = self.invoke_cli(
                "--chain-id", chain_id, *argv
            )
            self.assertEqual((exit_code, stderr), (1, ""))
            self.assert_pending_refusal(
                envelope,
                verb=verb,
                run_id=bound_run,
                execution=str(bound_execution["execution"]),
                remediation=self._remediation(
                    bound_run, bound_execution["execution"]
                ),
            )
            self.assertEqual(self.state_path(chain_id).read_bytes(), state_before)
            self.assertEqual(self.events_path(chain_id).read_bytes(), events_before)

        for verb, argv in BOUND_GATE_CASES:
            with self.subTest(verb=verb):
                assert_bound_pending(verb, argv)
                with mock.patch.object(
                    result_gate,
                    "_result_is_terminal",
                    side_effect=ValueError("disabled non-terminal classification"),
                ), self.assertRaises(AssertionError):
                    assert_bound_pending(verb, argv)

    def test_commit_start_inspection_failures_use_bound_reason(self) -> None:
        start_run = "run-20260930-result-start-inspection-error"
        start_opening = self.open_run(start_run)
        self.append_execution(start_run, start_opening)
        self.change("src/app.py", "VALUE = 2\n")
        for patcher in (
            mock.patch.object(
                RESULT_BEFORE_GATE.journal,
                "_scan_run",
                side_effect=OSError("inspection detail"),
            ),
            mock.patch.object(
                result_gate,
                "pending_mutations",
                side_effect=KeyError("inspection detail"),
            ),
        ):
            with patcher:
                self._assert_inspection_refusal(
                    "--run-id", start_run, "commit", "start", "--paths", "src/app.py",
                    "--task", "task-01", verb="commit start",
                )

    def test_bound_inspection_failures_are_safe_and_verbose_only(self) -> None:
        bound_run = "run-20260930-result-bound-inspection-error"
        self.open_run(bound_run)
        chain_id = self.start_chain(bound_run)

        def fail_policy(*_args, **_kwargs):
            try:
                raise LookupError("nested detail")
            except LookupError as exc:
                raise KeyError("inspection detail") from exc

        def policy_failure():
            return mock.patch.object(
                RESULT_BEFORE_GATE.COMMAND_LOCK.chain_core,
                "_policy_for_state",
                side_effect=fail_policy,
            )

        def disabled_mapping(*_args, **_kwargs):
            return RuntimeError("disabled inspection mapping")

        original_refusal = (
            RESULT_BEFORE_GATE.COMMAND_LOCK._pending_result_inspection_refusal
        )

        def always_verbose(verb, state, exc, **_kwargs):
            return original_refusal(verb, state, exc, verbose=True)

        for verb, argv in BOUND_GATE_CASES:
            with self.subTest(verb=verb), policy_failure():
                self._assert_inspection_refusal(
                    "--chain-id", chain_id, *argv, verb=verb, chain_id=chain_id
                )
            with self.subTest(verb=verb, mode="verbose"), policy_failure():
                self._assert_inspection_refusal(
                    "--verbose", "--chain-id", chain_id, *argv,
                    verb=verb, chain_id=chain_id,
                    exception_classes=("KeyError", "LookupError"),
                )
            with (
                self.subTest(verb=verb, control="exception-mapping"),
                policy_failure(),
                mock.patch.object(
                    RESULT_BEFORE_GATE.COMMAND_LOCK,
                    "_pending_result_inspection_refusal",
                    side_effect=disabled_mapping,
                ),
                self.assertRaises(AssertionError),
            ):
                self._assert_inspection_refusal(
                    "--chain-id", chain_id, *argv, verb=verb, chain_id=chain_id
                )

        with (
            policy_failure(),
            mock.patch.object(
                RESULT_BEFORE_GATE.COMMAND_LOCK,
                "_pending_result_inspection_refusal",
                side_effect=always_verbose,
            ),
            self.assertRaises(AssertionError),
        ):
            self._assert_inspection_refusal(
                "--chain-id", chain_id, "verify", verb="verify", chain_id=chain_id
            )


if __name__ == "__main__":
    unittest.main()
