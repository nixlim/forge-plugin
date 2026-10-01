"""Run-bound docs-class candidates execute Gate 1 instead of recording a skip."""

from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import unittest
from pathlib import Path
from unittest import mock

import tests.test_cli_chain as chain_tests
from tests._cli_loader import load_script, package_module, patch_engine
from tests._revision9_coord_constants import key

from codex_orchestrator import journal

ROOT = Path(__file__).resolve().parents[1]
CLI = load_script(
    "forge_run_bound_gate_one_tests",
    ROOT / "scripts/forge/cli.py",
)
ENVELOPE = package_module("envelope")
GATE_CHECKS = package_module("engine._gate_checks")
RUNTIME = package_module("runtime")

ENVELOPE_KEYS = {
    "chain_id",
    "evidence_refs",
    "expected",
    "message",
    "next_required_step",
    "observed",
    "ok",
    "reason_code",
    "remediation",
    "schema",
    "state",
}

CONTROL = "run-bound-gate-one"
REFUSAL = "gate-1 docs-class skip refused: a run-bound chain runs Gate 1"


def _binding(
    seed: str, *, review: dict[str, object] | None = None
) -> dict[str, object]:
    preimage: dict[str, object] = {
        "schema": journal.BINDING_SCHEMA,
        "source_record": {
            "chain_id": "c-2026-09-30T120000Z-abcd",
            "event_digest": key(f"event-{seed}"),
        },
        "candidate": {
            "kind": "staged-diff-sha256",
            "value": key("docs-candidate"),
        },
        "review": review,
    }
    return {
        **preimage,
        "binding_id": journal._sha256(journal._canonical_json_bytes(preimage)),
    }


def _close_records(*, gate_one: bool) -> list[dict[str, object]]:
    review = {
        "verdict": "PASS",
        "iteration": 1,
        "reviewer_role": "review-final",
        "package_digest": key("review-package"),
    }
    records: list[dict[str, object]] = [
        {
            "type": "run_started",
            "writer_contract": journal.WRITER_CONTRACT,
        },
        {"type": "task", "id": "task-01", "status": "active"},
    ]
    if gate_one:
        records.append(
            {
                "type": "verification",
                "id": "check-01",
                "task": "task-01",
                "criterion": "gate-1: gate-1",
                "result": "passed",
                "binding": _binding("gate-1"),
            }
        )
    records.extend(
        (
            {
                "type": "verification",
                "id": "check-02",
                "task": "task-01",
                "criterion": "gate-2: stack checks",
                "result": "passed",
                "binding": _binding("gate-2"),
            },
            {
                "type": "verification",
                "id": "check-03",
                "task": "task-01",
                "criterion": journal.GATE_3_CRITERION,
                "result": "passed",
                "binding": _binding("gate-3", review=review),
            },
            {
                "type": "decision",
                "id": "decision-01",
                "task": "task-01",
                "outcome": "chain-landing",
                "binding": _binding("landing"),
            },
            {"type": "task", "id": "task-01", "status": "complete"},
            {"type": "run_closed", "judgment": "passed"},
        )
    )
    for line, record in enumerate(records, start=1):
        record["_line"] = line
    return records


class RunBoundGateOneTests(chain_tests.ForgeCLIFixture):
    def revision9_environment(self) -> dict[str, str]:
        return self.environment(FORGE_SESSION_PID=str(os.getpid()))

    @contextlib.contextmanager
    def cli_process_context(self):
        with mock.patch.dict(
            os.environ, self.revision9_environment(), clear=True
        ), mock.patch.object(
            RUNTIME, "SCRIPT_DIR", self.helpers
        ), mock.patch.object(
            RUNTIME, "PLUGIN_ROOT", ROOT
        ), patch_engine(
            "CODEX_EXECUTABLE", str(self.helpers / "fake-codex")
        ), patch_engine(
            "CLAUDE_EXECUTABLE", str(self.helpers / "fake-claude")
        ):
            yield

    def invoke_cli(self, *argv: str) -> tuple[int, dict[str, object]]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with self.cli_process_context(), contextlib.redirect_stdout(
            stdout
        ), contextlib.redirect_stderr(stderr):
            exit_code = CLI.main(["--json", "--repo", str(self.repo), *argv])
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(stdout.getvalue().count("\n"), 1)
        envelope = json.loads(stdout.getvalue())
        self.assertEqual(set(envelope), ENVELOPE_KEYS)
        return exit_code, envelope

    def open_run_and_task(
        self,
        run_id: str,
        *,
        scope: tuple[str, ...],
        files: tuple[str, ...],
    ) -> None:
        _batch, builders, _journal = CLI._coordination_modules()
        with self.cli_process_context():
            builders.run_open(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-open"),
                goal="Exercise run-bound Gate 1",
                scope=list(scope),
                plugin_ref="forge-run-bound-gate-one-tests",
            )
            builders.task_start(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-task"),
                task="task-01",
                goal="Run Gate 1 on a bound docs candidate",
                acceptance=["The ordinary Gate 1 verification is bound"],
                files=list(files),
            )

    def _start_bound_docs_chain(self, run_id: str) -> str:
        self.open_run_and_task(
            run_id,
            scope=("docs/**",),
            files=("docs/guide.md",),
        )
        self.change("docs/guide.md", "# Run-bound docs candidate\n")
        exit_code, started = self.invoke_cli(
            "--run-id",
            run_id,
            "commit",
            "start",
            "--paths",
            "docs/guide.md",
            "--task",
            "task-01",
        )
        self.assertEqual(exit_code, 0, started)
        return str(started["chain_id"])

    def _run_records(self, run_id: str) -> list[dict[str, object]]:
        path = (
            self.repo
            / ".codex-orchestrator"
            / "runs"
            / run_id
            / "journal.jsonl"
        )
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def _assert_bound_gate_one_ran(self, run_id: str, chain_id: str) -> None:
        state = self.state(chain_id)
        self.assertEqual(
            [record["result"] for record in state["steps"]["gate-1"]],
            ["passed"],
        )
        self.assertNotIn("skipped", state["steps"]["gate-1"][0])
        self.assertEqual(self.gate_lines().count("gate-1"), 1)
        self.assertIsNone(state["journal_outbox"])
        drained = [
            record
            for record in self._run_records(run_id)
            if record.get("type") == "verification"
            and record.get("criterion") == "gate-1: gate-1"
        ]
        self.assertEqual(len(drained), 1)
        self.assertEqual(drained[0]["result"], "passed")
        self.assertEqual(
            drained[0]["binding"]["source_record"]["chain_id"],
            chain_id,
        )

    def test_direct_gate_run_executes_and_drains_bound_gate_one(self) -> None:
        run_id = "run-20260930-bound-docs-direct"
        chain_id = self._start_bound_docs_chain(run_id)

        exit_code, outcome = self.invoke_cli(
            "--chain-id", chain_id, "gate", "run", "gate-1"
        )

        self.assertEqual(exit_code, 0, outcome)
        self.assertIn("gate gate-1 passed", outcome["message"])
        self._assert_bound_gate_one_ran(run_id, chain_id)

    def test_verify_executes_and_drains_bound_gate_one(self) -> None:
        run_id = "run-20260930-bound-docs-verify"
        chain_id = self._start_bound_docs_chain(run_id)

        exit_code, outcome = self.invoke_cli("--chain-id", chain_id, "verify")

        self.assertEqual(exit_code, 0, outcome)
        self._assert_bound_gate_one_ran(run_id, chain_id)

    def test_bound_skip_writer_refuses_without_mutating_state(self) -> None:
        run_id = "run-20260930-bound-docs-refusal"
        chain_id = self._start_bound_docs_chain(run_id)
        state = self.state(chain_id)
        before = copy.deepcopy(state)
        persisted_before = self.state_path(chain_id).read_bytes()

        with self.assertRaises(ENVELOPE.Refusal) as caught:
            GATE_CHECKS._record_docs_class_gate_one_skip(mock.Mock(), state)

        self.assertEqual(caught.exception.reason_code, ENVELOPE.ReasonCode.STATE_PRECONDITION)
        self.assertEqual(caught.exception.message, REFUSAL)
        self.assertEqual(caught.exception.expected, "a chain with no run binding")
        self.assertEqual(
            caught.exception.remediation,
            f"forge gate run gate-1 --chain-id {chain_id}",
        )
        self.assertEqual(state, before)
        self.assertEqual(self.state_path(chain_id).read_bytes(), persisted_before)

    def test_bound_history_skip_is_not_engine_complete(self) -> None:
        candidate = key("bound-history-candidate")
        state = {
            "candidate": {"sha256": candidate},
            "run_binding": {"binding_id": key("bound-history-binding")},
            "steps": {
                "gate-1": [
                    {"candidate": candidate, "result": "passed"},
                    {
                        "candidate": candidate,
                        "result": "skipped",
                        "reason": GATE_CHECKS.chain_core.DOCS_CLASS_SKIP_REASON,
                    },
                    {"candidate": key("foreign-candidate"), "result": "failed"},
                ]
            },
        }
        context = mock.Mock()

        with mock.patch.object(
            GATE_CHECKS.chain_core, "_required_steps", return_value=["gate-1"]
        ):
            self.assertTrue(GATE_CHECKS.chain_core._gate_one_complete(state))
            self.assertFalse(GATE_CHECKS._gate_one_complete(state))
            self.assertFalse(GATE_CHECKS._mechanical_complete(context, state))
            self.assertEqual(GATE_CHECKS._next_incomplete(context, state), "gate-1")

            with mock.patch.object(
                GATE_CHECKS,
                "RUN_BOUND_GATE_ONE_CONTROLS",
                GATE_CHECKS.RUN_BOUND_GATE_ONE_CONTROLS - {CONTROL},
            ):
                self.assertTrue(GATE_CHECKS._gate_one_complete(state))
                self.assertTrue(GATE_CHECKS._mechanical_complete(context, state))
                self.assertIsNone(GATE_CHECKS._next_incomplete(context, state))

    def test_disabling_control_restores_the_bound_docs_skip(self) -> None:
        run_id = "run-20260930-bound-docs-disabled"
        chain_id = self._start_bound_docs_chain(run_id)
        direct_state = self.state(chain_id)

        with mock.patch.object(
            GATE_CHECKS,
            "RUN_BOUND_GATE_ONE_CONTROLS",
            GATE_CHECKS.RUN_BOUND_GATE_ONE_CONTROLS - {CONTROL},
        ):
            direct_context = mock.Mock()
            direct_record = {
                "candidate": direct_state["candidate"]["sha256"],
                "result": "skipped",
                "reason": "docs-class candidate",
                "skipped": True,
            }
            with mock.patch.object(
                GATE_CHECKS,
                "_write_artifact",
                return_value=".forge/chains/c-fixture/evidence/gate-1-01.log",
            ), mock.patch.object(
                GATE_CHECKS,
                "_evidence_record",
                return_value=direct_record,
            ):
                self.assertIs(
                    GATE_CHECKS._record_docs_class_gate_one_skip(
                        direct_context, direct_state
                    ),
                    direct_record,
                )
            direct_context.store.persist.assert_called_once()
            self.assertEqual(
                [
                    (record["result"], record["reason"])
                    for record in direct_state["steps"]["gate-1"]
                ],
                [("skipped", "docs-class candidate")],
            )
            exit_code, outcome = self.invoke_cli(
                "--chain-id", chain_id, "gate", "run", "gate-1"
            )

        self.assertEqual(exit_code, 0, outcome)
        state = self.state(chain_id)
        self.assertEqual(
            [
                (record["result"], record["reason"])
                for record in state["steps"]["gate-1"]
            ],
            [("skipped", "docs-class candidate")],
        )
        self.assertEqual(self.gate_lines(), [])
        self.assertFalse(
            any(
                record.get("criterion") == "gate-1: gate-1"
                for record in self._run_records(run_id)
            )
        )
        with self.assertRaises(AssertionError):
            self._assert_bound_gate_one_ran(run_id, chain_id)


class UnboundGateOneTests(chain_tests.ForgeCLIFixture):
    def test_unbound_docs_candidate_keeps_the_revision17_skip(self) -> None:
        self.change("docs/guide.md", "# Unbound docs candidate\n")
        chain_id = str(self.start("docs/guide.md")["chain_id"])

        _result, outcome = self.cli(
            "gate", "run", "gate-1", "--chain-id", chain_id, expected=0
        )

        self.assertIn("docs-class candidate", outcome["message"])
        self.assertEqual(
            [
                (record["result"], record["reason"])
                for record in self.state(chain_id)["steps"]["gate-1"]
            ],
            [("skipped", "docs-class candidate")],
        )
        self.assertEqual(self.gate_lines(), [])


class RunBoundCloseLawTests(unittest.TestCase):
    def test_bound_gate_one_record_repairs_the_landing_correlation(self) -> None:
        without_gate_one = _close_records(gate_one=False)
        issues: list[str] = []
        journal.check_gate_profile(without_gate_one, issues, [], None)
        self.assertEqual(
            issues,
            [
                "task 'task-01' has inconsistent bound candidate across gate "
                "and landing records"
            ],
        )

        with_gate_one = _close_records(gate_one=True)
        issues = []
        journal.check_gate_profile(with_gate_one, issues, [], None)
        self.assertEqual(issues, [])


if __name__ == "__main__":
    unittest.main()
