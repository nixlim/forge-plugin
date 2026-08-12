from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.codex_orchestrator.journal import validate_run

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "codex_orch_tools.py"
REPLAY_FIXTURES = ROOT / "tests" / "replay"

MISSING_GATE_ISSUES = {
    "gate-1": (
        "run closed as passed without a passing 'gate-1' verification after the last "
        "mutating execution"
    ),
    "gate-2": (
        "run closed as passed without a passing 'gate-2' verification after the last "
        "mutating execution"
    ),
    "gate-3": (
        "run closed as passed without a passing 'gate-3: review-final verdict' verification "
        "after the last mutating execution"
    ),
}


def write_journal(run_dir: Path, records: list[dict[str, object]]) -> None:
    (run_dir / "journal.jsonl").write_text(
        "".join(json.dumps(record, separators=(",", ":")) + "\n" for record in records),
        encoding="utf-8",
    )


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        text=True,
        capture_output=True,
        cwd=ROOT,
    )


def gate_verification(
    record_id: str, criterion: str, result: str = "passed"
) -> dict[str, object]:
    return {
        "type": "verification",
        "id": record_id,
        "task": "task-01",
        "criterion": criterion,
        "method": "command",
        "check": f"fixture check for {criterion}",
        "result": result,
        "observation": f"fixture result: {result}",
    }


def passing_gates() -> list[dict[str, object]]:
    return [
        gate_verification("check-gate-1", "gate-1: project tests"),
        gate_verification("check-gate-2", "gate-2: lint and types"),
        gate_verification("check-gate-3", "gate-3: review-final verdict"),
    ]


class GatesValidationTests(unittest.TestCase):
    def make_run(
        self,
        root: Path,
        *,
        role: str = "implementation",
        before_result: list[dict[str, object]] | None = None,
        after_result: list[dict[str, object]] | None = None,
        judgment: str = "passed",
    ) -> tuple[Path, list[dict[str, object]]]:
        run_dir = root / "run"
        run_dir.mkdir()
        (run_dir / "handoff.md").write_text("## Status\n\ncomplete\n", encoding="utf-8")
        records: list[dict[str, object]] = [
            {"type": "run_started"},
            {"type": "task", "id": "task-01", "status": "complete"},
            {
                "type": "execution",
                "task": "task-01",
                "agent": "codex-fixture-01",
                "execution": "execution-01",
                "role": role,
                "handoff": "handoff.md",
            },
            *(before_result or []),
            {
                "type": "execution_result",
                "task": "task-01",
                "agent": "codex-fixture-01",
                "execution": "execution-01",
                "status": "complete",
                "handoff": "handoff.md",
            },
            *(after_result or []),
            {"type": "run_closed", "judgment": judgment},
        ]
        write_journal(run_dir, records)
        return run_dir, records

    def test_all_three_passing_gates_after_the_last_mutation_are_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, _ = self.make_run(Path(tmp), after_result=passing_gates())
            payload = validate_run(run_dir, gates=True)

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["issues"], [])
        self.assertEqual(payload["profile"], "gates")

    def test_each_missing_gate_produces_its_own_exact_issue(self) -> None:
        for missing_gate, expected_issue in MISSING_GATE_ISSUES.items():
            with self.subTest(missing_gate=missing_gate), tempfile.TemporaryDirectory() as tmp:
                retained_gates = [
                    record
                    for record in passing_gates()
                    if not str(record["criterion"]).startswith(f"{missing_gate}:")
                ]
                run_dir, _ = self.make_run(Path(tmp), after_result=retained_gates)
                payload = validate_run(run_dir, gates=True)

            self.assertFalse(payload["ok"])
            self.assertEqual(payload["issues"], [expected_issue])

    def test_each_missing_gate_is_reported_exactly_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, _ = self.make_run(Path(tmp))
            payload = validate_run(run_dir, gates=True)

        self.assertFalse(payload["ok"])
        self.assertEqual(len(payload["issues"]), 3)
        for issue in MISSING_GATE_ISSUES.values():
            self.assertEqual(payload["issues"].count(issue), 1)

    def test_gate_before_the_last_mutating_execution_result_does_not_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, records = self.make_run(Path(tmp))
            close = records.pop()
            records.extend(
                [
                    gate_verification("check-gate-1-early", "gate-1: project tests"),
                    {
                        "type": "execution",
                        "task": "task-01",
                        "agent": "codex-fixture-02",
                        "execution": "execution-01",
                        "role": "implementation",
                        "handoff": "handoff.md",
                    },
                    {
                        "type": "execution_result",
                        "task": "task-01",
                        "agent": "codex-fixture-02",
                        "execution": "execution-01",
                        "status": "complete",
                        "handoff": "handoff.md",
                    },
                    gate_verification("check-gate-2", "gate-2: lint and types"),
                    gate_verification("check-gate-3", "gate-3: review-final verdict"),
                    close,
                ]
            )
            write_journal(run_dir, records)
            payload = validate_run(run_dir, gates=True)

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["issues"], [MISSING_GATE_ISSUES["gate-1"]])

    def test_unterminated_mutating_execution_makes_gate_boundary_unsatisfiable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, records = self.make_run(Path(tmp))
            close = records.pop()
            records.extend(
                [
                    {
                        "type": "execution",
                        "task": "task-01",
                        "agent": "codex-fixture-02",
                        "execution": "execution-01",
                        "role": "implementation",
                        "handoff": "handoff.md",
                    },
                    *passing_gates(),
                    close,
                ]
            )
            write_journal(run_dir, records)
            payload = validate_run(run_dir, gates=True)

        self.assertFalse(payload["ok"])
        self.assertEqual(
            payload["issues"],
            [
                "execution codex-fixture-02/execution-01 has no terminal execution_result",
                *MISSING_GATE_ISSUES.values(),
            ],
        )

    def test_run_with_no_executions_is_exempt_from_required_gate_presence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            write_journal(
                run_dir,
                [
                    {"type": "run_started"},
                    {"type": "task", "id": "task-01", "status": "complete"},
                    {"type": "run_closed", "judgment": "passed"},
                ],
            )
            payload = validate_run(run_dir, gates=True)

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["issues"], [])

    def test_review_only_run_is_exempt_from_required_gate_presence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, _ = self.make_run(Path(tmp), role="review")
            payload = validate_run(run_dir, gates=True)

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["issues"], [])

    def test_gate_3_presence_requires_the_exact_review_final_criterion(self) -> None:
        non_final_gate_3 = gate_verification(
            "check-gate-3-other", "gate-3: review of an earlier candidate"
        )
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, _ = self.make_run(
                Path(tmp),
                after_result=[*passing_gates()[:2], non_final_gate_3],
            )
            payload = validate_run(run_dir, gates=True)

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["issues"], [MISSING_GATE_ISSUES["gate-3"]])

    def test_later_identical_passing_recheck_clears_failed_gate(self) -> None:
        failed = gate_verification("check-gate-1-failed", "gate-1: blast radius", "failed")
        recheck = gate_verification("check-gate-1-recheck", "gate-1: blast radius")
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, _ = self.make_run(
                Path(tmp), role="review", after_result=[failed, recheck]
            )
            payload = validate_run(run_dir, gates=True)

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["issues"], [])
        self.assertEqual(
            payload["non_passing_verifications"],
            [
                {
                    "id": "check-gate-1-failed",
                    "task": "task-01",
                    "criterion": "gate-1: blast radius",
                    "result": "failed",
                    "check": "fixture check for gate-1: blast radius",
                    "observation": "fixture result: failed",
                }
            ],
        )

    def test_passing_same_prefix_with_different_criterion_does_not_clear_failure(self) -> None:
        failed = gate_verification("check-gate-1-failed", "gate-1: blast radius", "failed")
        prefix_only = gate_verification("check-gate-1-other", "gate-1: project tests")
        expected = (
            "failed gate verification 'check-gate-1-failed' has no subsequent passing recheck"
        )
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, _ = self.make_run(
                Path(tmp), role="review", after_result=[failed, prefix_only]
            )
            payload = validate_run(run_dir, gates=True)

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["issues"], [expected])

    def test_identical_pass_before_failure_does_not_count_as_a_recheck(self) -> None:
        earlier_pass = gate_verification("check-gate-1-pass", "gate-1: project tests")
        failed = gate_verification("check-gate-1-failed", "gate-1: project tests", "failed")
        expected = (
            "failed gate verification 'check-gate-1-failed' has no subsequent passing recheck"
        )
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, _ = self.make_run(
                Path(tmp), role="review", after_result=[earlier_pass, failed]
            )
            payload = validate_run(run_dir, gates=True)

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["issues"], [expected])

    def test_unknown_gate_criteria_are_exact_issues(self) -> None:
        unknown_gate_4 = gate_verification("check-gate-4", "gate-4: security scan")
        unknown_gate_1m = gate_verification("check-gate-1m", "gate-1m: mutation")
        missing_space = gate_verification("check-gate-1-typo", "gate-1:project tests")
        known_gate_3_prefix = gate_verification("check-gate-3-other", "gate-3: candidate note")
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, _ = self.make_run(
                Path(tmp),
                role="review",
                after_result=[
                    unknown_gate_4,
                    unknown_gate_1m,
                    missing_space,
                    known_gate_3_prefix,
                ],
            )
            payload = validate_run(run_dir, gates=True)

        self.assertFalse(payload["ok"])
        self.assertEqual(len(payload["issues"]), 3)
        self.assertCountEqual(
            payload["issues"],
            [
                "unknown gate criterion: gate-4: security scan",
                "unknown gate criterion: gate-1m: mutation",
                "unknown gate criterion: gate-1:project tests",
            ],
        )

    def test_mutation_verification_is_visible_but_cannot_satisfy_a_gate(self) -> None:
        mutation = gate_verification("mutation-python", "mutation: python", "failed")
        mutation["check"] = 'mutmut run --paths-to-mutate "$@"'
        mutation["observation"] = (
            "tool=mutmut; scope=python; outcome=completed; exit_code=1; "
            'timeout=600s; scoped_files=["src/new.py"]'
        )
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, _ = self.make_run(Path(tmp), after_result=[mutation])
            plain_payload = validate_run(run_dir)
            gates_payload = validate_run(run_dir, gates=True)

        expected_visible = {
            "id": "mutation-python",
            "task": "task-01",
            "criterion": "mutation: python",
            "result": "failed",
            "check": 'mutmut run --paths-to-mutate "$@"',
            "observation": mutation["observation"],
        }
        self.assertTrue(plain_payload["ok"])
        self.assertEqual(plain_payload["issues"], [])
        self.assertEqual(plain_payload["non_passing_verifications"], [expected_visible])
        self.assertFalse(gates_payload["ok"])
        self.assertEqual(gates_payload["issues"], list(MISSING_GATE_ISSUES.values()))
        self.assertEqual(gates_payload["non_passing_verifications"], [expected_visible])

    def test_profile_is_opt_in_and_plain_payload_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, _ = self.make_run(Path(tmp))
            plain_payload = validate_run(run_dir)
            gates_payload = validate_run(run_dir, gates=True)

        self.assertEqual(
            plain_payload,
            {
                "ok": True,
                "issues": [],
                "warnings": [],
                "non_passing_verifications": [],
            },
        )
        self.assertNotIn("profile", plain_payload)
        self.assertEqual(set(gates_payload), {*plain_payload, "profile"})
        self.assertEqual(gates_payload["profile"], "gates")
        self.assertFalse(gates_payload["ok"])

    def test_negative_replay_fixtures_exit_one_with_exact_issues(self) -> None:
        fixtures = {
            "gates-missing-gate-3": MISSING_GATE_ISSUES["gate-3"],
            "gates-failed-no-recheck": (
                "failed gate verification 'gate-1-failed' has no subsequent passing recheck"
            ),
        }
        for fixture_name, expected_issue in fixtures.items():
            with self.subTest(fixture=fixture_name):
                fixture = REPLAY_FIXTURES / fixture_name
                plain_result = run_cli("validate", str(fixture))
                gates_result = run_cli("validate", str(fixture), "--gates")

                self.assertEqual(plain_result.returncode, 0, plain_result.stderr)
                self.assertEqual(set(json.loads(plain_result.stdout)), {
                    "ok",
                    "issues",
                    "warnings",
                    "non_passing_verifications",
                })
                self.assertEqual(gates_result.returncode, 1, gates_result.stderr)
                gates_payload = json.loads(gates_result.stdout)
                self.assertEqual(gates_payload["profile"], "gates")
                self.assertEqual(gates_payload["issues"], [expected_issue])


if __name__ == "__main__":
    unittest.main()
