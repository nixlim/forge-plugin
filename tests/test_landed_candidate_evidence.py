from __future__ import annotations

import copy
import hashlib
import inspect
import sys
import textwrap
import unittest
from collections.abc import Callable
from pathlib import Path
from types import FunctionType
from unittest import mock

from tests import test_revision9_coordination as coordination

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from codex_orchestrator import journal, landed_evidence  # noqa: E402

MISSING_GATE_ISSUES = [
    "run closed as passed without a passing 'gate-1' verification after the "
    "last mutating execution",
    "run closed as passed without a passing 'gate-2' verification after the "
    "last mutating execution",
    "run closed as passed without a passing 'gate-3: review-final verdict' "
    "verification after the last mutating execution",
]


def digest(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


def mutated_function(
    function: FunctionType,
    anchor: str,
    replacement: str,
) -> FunctionType:
    """Compile one exact in-memory mutant with production globals."""

    source = textwrap.dedent(inspect.getsource(function))
    if source.count(anchor) != 1:
        raise AssertionError(f"mutation anchor drifted for {function.__name__}")
    namespace = dict(function.__globals__)
    exec(
        compile(
            source.replace(anchor, replacement, 1),
            function.__code__.co_filename,
            "exec",
        ),
        namespace,
    )
    mutant = namespace[function.__name__]
    if not isinstance(mutant, FunctionType):
        raise AssertionError(f"mutation did not define {function.__name__}")
    return mutant


class LandedCandidateEvidenceTests(unittest.TestCase):
    landed_chain = "c-2026-09-30T100000Z-a001"
    aborted_chain = "c-2026-09-30T100100Z-a002"
    landed_candidate = {
        "kind": "staged-diff-sha256",
        "value": digest("landed-candidate"),
    }
    aborted_candidate = {
        "kind": "staged-diff-sha256",
        "value": digest("aborted-candidate"),
    }

    def binding(
        self,
        seed: str,
        *,
        chain: str,
        candidate: dict[str, object],
        review: dict[str, object] | None = None,
    ) -> dict[str, object]:
        preimage: dict[str, object] = {
            "schema": journal.BINDING_SCHEMA,
            "source_record": {
                "chain_id": chain,
                "event_digest": digest(f"event-{seed}"),
            },
            "candidate": copy.deepcopy(candidate),
            "review": copy.deepcopy(review),
        }
        return {
            **preimage,
            "binding_id": journal._sha256(journal._canonical_json_bytes(preimage)),
        }

    def gate(
        self,
        seed: str,
        criterion: str,
        *,
        chain: str,
        candidate: dict[str, object],
    ) -> dict[str, object]:
        review = None
        if criterion == journal.GATE_3_CRITERION:
            review = {
                "verdict": "PASS",
                "iteration": 1,
                "reviewer_role": "review-final",
                "package_digest": digest(f"package-{seed}"),
            }
        return {
            "type": "verification",
            "id": f"check-{seed}",
            "task": "task-01",
            "criterion": criterion,
            "result": "passed",
            "binding": self.binding(
                seed,
                chain=chain,
                candidate=candidate,
                review=review,
            ),
        }

    def gate_set(
        self,
        seed: str,
        *,
        chain: str,
        candidate: dict[str, object],
    ) -> list[dict[str, object]]:
        return [
            self.gate(
                f"{seed}-1",
                "gate-1: project tests",
                chain=chain,
                candidate=candidate,
            ),
            self.gate(
                f"{seed}-2",
                "gate-2: stack checks",
                chain=chain,
                candidate=candidate,
            ),
            self.gate(
                f"{seed}-3",
                journal.GATE_3_CRITERION,
                chain=chain,
                candidate=candidate,
            ),
        ]

    def decision(
        self,
        seed: str,
        outcome: str,
        *,
        chain: str,
        candidate: dict[str, object],
    ) -> dict[str, object]:
        return {
            "type": "decision",
            "id": f"decision-{seed}",
            "task": "task-01",
            "outcome": outcome,
            "binding": self.binding(seed, chain=chain, candidate=candidate),
        }

    @staticmethod
    def relined(records: list[dict[str, object]]) -> list[dict[str, object]]:
        for line, record in enumerate(records, 1):
            record["_line"] = line
        return records

    @staticmethod
    def boundary_execution() -> list[dict[str, object]]:
        return [
            {
                "type": "execution",
                "agent": "codex-impl-boundary",
                "execution": "execution-01",
                "task": "task-boundary",
                "role": "implementer",
            },
            {
                "type": "execution_result",
                "agent": "codex-impl-boundary",
                "execution": "execution-01",
                "task": "task-boundary",
                "status": "complete",
            },
        ]

    @staticmethod
    def activated_start() -> dict[str, object]:
        return {
            "type": "run_started",
            "writer_contract": journal.WRITER_CONTRACT,
        }

    def profile_issues(self, records: list[dict[str, object]]) -> list[str]:
        issues: list[str] = []
        journal.check_gate_profile(copy.deepcopy(records), issues, [], None)
        return issues

    def route_f_records(self) -> list[dict[str, object]]:
        return self.relined(
            [
                self.activated_start(),
                {"type": "task", "id": "task-01", "status": "active"},
                *self.boundary_execution(),
                *self.gate_set(
                    "aborted",
                    chain=self.aborted_chain,
                    candidate=self.aborted_candidate,
                ),
                self.decision(
                    "abort",
                    "chain-abort",
                    chain=self.aborted_chain,
                    candidate=self.aborted_candidate,
                ),
                {"type": "task", "id": "task-01", "status": "complete"},
                {"type": "run_closed", "judgment": "passed"},
            ]
        )

    def route_j_records(self) -> list[dict[str, object]]:
        landed = self.gate_set(
            "landed",
            chain=self.landed_chain,
            candidate=self.landed_candidate,
        )
        return self.relined(
            [
                self.activated_start(),
                {"type": "task", "id": "task-01", "status": "active"},
                landed[0],
                *self.boundary_execution(),
                *landed[1:],
                self.decision(
                    "landing",
                    "chain-landing",
                    chain=self.landed_chain,
                    candidate=self.landed_candidate,
                ),
                *self.gate_set(
                    "aborted-j",
                    chain=self.aborted_chain,
                    candidate=self.aborted_candidate,
                ),
                self.decision(
                    "abort-j",
                    "chain-abort",
                    chain=self.aborted_chain,
                    candidate=self.aborted_candidate,
                ),
                {"type": "task", "id": "task-01", "status": "complete"},
                {"type": "run_closed", "judgment": "passed"},
            ]
        )

    def test_only_landed_candidate_gates_cross_the_run_boundary(self) -> None:
        self.assertEqual(self.profile_issues(self.route_j_records()), MISSING_GATE_ISSUES[:1])

    def test_aborted_chain_without_a_landing_cannot_supply_any_gate(self) -> None:
        records = self.route_f_records()

        def assert_filter_applies() -> None:
            self.assertEqual(self.profile_issues(records), MISSING_GATE_ISSUES)

        assert_filter_applies()
        with mock.patch.object(
            landed_evidence,
            "LANDED_EVIDENCE_CONTROLS",
            landed_evidence.LANDED_EVIDENCE_CONTROLS
            - {"landed-candidate-evidence"},
        ):
            with self.assertRaises(AssertionError):
                assert_filter_applies()
            self.assertEqual(self.profile_issues(records), [])

    def test_unbound_capfix_shape_is_unchanged(self) -> None:
        records = self.relined(
            [
                self.activated_start(),
                {"type": "task", "id": "task-01", "status": "active"},
                *self.boundary_execution(),
                {
                    "type": "decision",
                    "id": "decision-unbound",
                    "task": "task-01",
                    "outcome": "chain-landing",
                },
                {"type": "task", "id": "task-01", "status": "complete"},
                {"type": "run_closed", "judgment": "passed"},
            ]
        )
        self.assertEqual(self.profile_issues(records), MISSING_GATE_ISSUES)
        with mock.patch.object(
            landed_evidence, "LANDED_EVIDENCE_CONTROLS", frozenset()
        ):
            self.assertEqual(self.profile_issues(records), MISSING_GATE_ISSUES)

    def test_superseded_candidate_gates_do_not_count(self) -> None:
        replacement = {
            "kind": "staged-diff-sha256",
            "value": digest("replacement-candidate"),
        }
        gates = self.gate_set(
            "superseded",
            chain=self.landed_chain,
            candidate=self.landed_candidate,
        )
        records = self.relined(
            [
                self.activated_start(),
                *gates,
                self.decision(
                    "old-landing",
                    "chain-landing",
                    chain=self.landed_chain,
                    candidate=self.landed_candidate,
                ),
                self.decision(
                    "replacement",
                    "chain-approval",
                    chain=self.landed_chain,
                    candidate=replacement,
                ),
            ]
        )
        self.assertEqual(
            landed_evidence.missing_gate_issues(records, gates, 1, False),
            MISSING_GATE_ISSUES,
        )
        with mock.patch.object(
            landed_evidence, "LANDED_EVIDENCE_CONTROLS", frozenset()
        ):
            self.assertEqual(
                landed_evidence.missing_gate_issues(records, gates, 1, False),
                [],
            )

    def test_non_activated_run_keeps_the_any_record_rule(self) -> None:
        gates = [
            {
                **gate,
                "binding": None,
            }
            for gate in self.gate_set(
                "legacy",
                chain=self.landed_chain,
                candidate=self.landed_candidate,
            )
        ]
        records = self.relined(
            [
                {"type": "run_started"},
                *self.boundary_execution(),
                *gates,
                {"type": "run_closed", "judgment": "passed"},
            ]
        )
        self.assertEqual(self.profile_issues(records), [])

    def test_zero_mutations_and_4qasb_correlation_shape_are_unchanged(self) -> None:
        gates = self.gate_set(
            "4qasb",
            chain=self.landed_chain,
            candidate=self.landed_candidate,
        )[1:]
        records = self.relined(
            [
                self.activated_start(),
                {"type": "task", "id": "task-01", "status": "active"},
                *gates,
                self.decision(
                    "4qasb-landing",
                    "chain-landing",
                    chain=self.landed_chain,
                    candidate=self.landed_candidate,
                ),
                {"type": "task", "id": "task-01", "status": "complete"},
                {"type": "run_closed", "judgment": "passed"},
            ]
        )
        expected = [
            "task 'task-01' has inconsistent bound candidate across gate and "
            "landing records"
        ]
        self.assertEqual(self.profile_issues(records), expected)
        with mock.patch.object(
            landed_evidence, "LANDED_EVIDENCE_CONTROLS", frozenset()
        ):
            self.assertEqual(self.profile_issues(records), expected)

    def test_retirement_predicate_matches_the_correlation_retirement(self) -> None:
        fixture = coordination.Revision9BindingTests(
            "test_fr021_abort_decision_retires_its_chain_and_orders_terminal_task"
        )
        correlation_records = fixture.correlation_records()
        correlation_records[4:4] = fixture._superseded_set("parity")
        fixture._relined(correlation_records)
        for records in (
            self.route_f_records(),
            self.route_j_records(),
            correlation_records,
        ):
            with self.subTest(records=len(records)):
                candidate = landed_evidence.retirement_predicate(records)
                base = self._correlation_retirement_predicate(records)
                self.assertEqual(
                    [candidate(record) for record in records],
                    [base(record) for record in records],
                )

    @staticmethod
    def _correlation_retirement_predicate(
        records: list[dict[str, object]],
    ) -> Callable[[dict[str, object]], bool]:
        superseded = journal._superseded_binding_ids(records)
        aborted_chains_by_task: dict[str, set[str]] = {}
        for record in records:
            task = record.get("task")
            if (
                record.get("type") == "decision"
                and record.get("outcome") == "chain-abort"
                and isinstance(task, str)
                and (bound := journal._binding_chain_and_candidate(record)) is not None
            ):
                aborted_chains_by_task.setdefault(task, set()).add(bound[0])

        def retired(record: dict[str, object]) -> bool:
            task = record.get("task")
            bound = journal._binding_chain_and_candidate(record)
            return bound is not None and (
                bound[2] in superseded
                or (
                    isinstance(task, str)
                    and bound[0] in aborted_chains_by_task.get(task, set())
                )
            )

        return retired

    @classmethod
    def _global_id_retirement_predicate(
        cls,
        records: list[dict[str, object]],
    ) -> Callable[[dict[str, object]], bool]:
        base = cls._correlation_retirement_predicate(records)
        retired_ids = {
            bound[2]
            for record in records
            if record.get("type") in {"verification", "decision"}
            and (bound := journal._binding_chain_and_candidate(record)) is not None
            and base(record)
        }

        def retired(record: dict[str, object]) -> bool:
            bound = journal._binding_chain_and_candidate(record)
            return bound is not None and bound[2] in retired_ids

        return retired

    @staticmethod
    def _correlation_issues(records: list[dict[str, object]]) -> list[str]:
        issues: list[str] = []
        journal._check_binding_correlation(copy.deepcopy(records), issues)
        return issues

    def _base_36bc5dc_correlation_issues(
        self,
        records: list[dict[str, object]],
    ) -> list[str]:
        with mock.patch.object(
            landed_evidence,
            "retirement_predicate",
            side_effect=self._correlation_retirement_predicate,
        ):
            return self._correlation_issues(records)

    def _global_id_correlation_issues(
        self,
        records: list[dict[str, object]],
    ) -> list[str]:
        with mock.patch.object(
            landed_evidence,
            "retirement_predicate",
            side_effect=self._global_id_retirement_predicate,
        ):
            return self._correlation_issues(records)

    def _cross_task_abort_records(
        self,
        criterion: str,
    ) -> tuple[list[dict[str, object]], dict[str, object]]:
        shared = self.binding(
            "cross-task-abort",
            chain=self.aborted_chain,
            candidate=self.aborted_candidate,
        )
        verification = {
            "type": "verification",
            "id": "check-task-b-shared",
            "task": "task-B",
            "criterion": criterion,
            "result": "passed",
            "binding": copy.deepcopy(shared),
        }
        records = self.relined(
            [
                self.activated_start(),
                {"type": "task", "id": "task-A", "status": "active"},
                {"type": "task", "id": "task-B", "status": "active"},
                {
                    "type": "decision",
                    "id": "decision-task-a-abort",
                    "task": "task-A",
                    "outcome": "chain-abort",
                    "binding": copy.deepcopy(shared),
                },
                verification,
                {
                    "type": "execution",
                    "agent": "codex-impl-task-b",
                    "execution": "execution-01",
                    "task": "task-B",
                    "role": "implementation",
                },
                {
                    "type": "execution_result",
                    "agent": "codex-impl-task-b",
                    "execution": "execution-01",
                    "task": "task-B",
                    "status": "complete",
                },
                {"type": "run_closed", "judgment": "passed"},
            ]
        )
        return records, verification

    def test_cross_task_shared_abort_matches_base_correlation(self) -> None:
        cases = (
            ("focused: cross-task parity", []),
            (
                "gate-1: project tests",
                [
                    "task 'task-B' has inconsistent bound candidate across gate "
                    "and landing records"
                ],
            ),
        )
        for criterion, mutant_issues in cases:
            with self.subTest(criterion=criterion):
                records, verification = self._cross_task_abort_records(criterion)
                binding_id = verification["binding"]["binding_id"]
                expected = [
                    f"binding {binding_id!r} precedes the last mutating execution "
                    "for task 'task-B'"
                ]
                base_issues = self._base_36bc5dc_correlation_issues(records)
                self.assertEqual(base_issues, expected)
                self.assertEqual(self._correlation_issues(records), base_issues)
                self.assertEqual(
                    self._global_id_correlation_issues(records),
                    mutant_issues,
                )
                self.assertNotEqual(mutant_issues, base_issues)

    def test_cross_task_shared_abort_does_not_retire_other_tasks_gate(self) -> None:
        records, verification = self._cross_task_abort_records(
            "gate-1: project tests"
        )
        records.insert(
            -1,
            {
                "type": "decision",
                "id": "decision-task-b-landing",
                "task": "task-B",
                "outcome": "chain-landing",
                "binding": copy.deepcopy(verification["binding"]),
            },
        )
        self.relined(records)
        expected = MISSING_GATE_ISSUES[1:]
        self.assertEqual(
            landed_evidence.missing_gate_issues(records, [verification], 0, False),
            expected,
        )
        with mock.patch.object(
            landed_evidence,
            "retirement_predicate",
            side_effect=self._global_id_retirement_predicate,
        ):
            self.assertEqual(
                landed_evidence.missing_gate_issues(
                    records, [verification], 0, False
                ),
                MISSING_GATE_ISSUES,
            )

    def test_cross_task_shared_superseded_id_remains_globally_retired(self) -> None:
        shared = self.binding(
            "cross-task-superseded",
            chain=self.landed_chain,
            candidate=self.landed_candidate,
        )
        replacement = {
            "kind": "staged-diff-sha256",
            "value": digest("cross-task-replacement"),
        }
        task_b_record = {
            "type": "verification",
            "id": "check-task-b-superseded-id",
            "task": "task-B",
            "criterion": "focused: superseded parity",
            "result": "passed",
            "binding": copy.deepcopy(shared),
        }
        records = self.relined(
            [
                self.activated_start(),
                {
                    "type": "verification",
                    "id": "check-task-a-old",
                    "task": "task-A",
                    "criterion": "focused: old candidate",
                    "result": "passed",
                    "binding": copy.deepcopy(shared),
                },
                task_b_record,
                {
                    "type": "verification",
                    "id": "check-task-a-new",
                    "task": "task-A",
                    "criterion": "focused: new candidate",
                    "result": "passed",
                    "binding": self.binding(
                        "cross-task-replacement",
                        chain=self.landed_chain,
                        candidate=replacement,
                    ),
                },
                {
                    "type": "execution",
                    "agent": "codex-impl-task-b",
                    "execution": "execution-02",
                    "task": "task-B",
                    "role": "implementation",
                },
                {
                    "type": "execution_result",
                    "agent": "codex-impl-task-b",
                    "execution": "execution-02",
                    "task": "task-B",
                    "status": "complete",
                },
                {"type": "run_closed", "judgment": "passed"},
            ]
        )
        shared_id = shared["binding_id"]
        self.assertEqual(journal._superseded_binding_ids(records), {shared_id})
        base = self._correlation_retirement_predicate(records)
        candidate = landed_evidence.retirement_predicate(records)
        self.assertTrue(base(task_b_record))
        self.assertTrue(candidate(task_b_record))
        self.assertEqual(self._base_36bc5dc_correlation_issues(records), [])
        self.assertEqual(self._correlation_issues(records), [])


class LandedCandidateSubclauseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = LandedCandidateEvidenceTests()

    def test_approval_only_chain_gates_require_a_chain_landing(self) -> None:
        fixture = self.fixture
        gates = fixture.gate_set(
            "approval-only",
            chain=fixture.landed_chain,
            candidate=fixture.landed_candidate,
        )
        records = fixture.relined(
            [
                fixture.activated_start(),
                *fixture.boundary_execution(),
                *gates,
                fixture.decision(
                    "approval-only",
                    "chain-approval",
                    chain=fixture.landed_chain,
                    candidate=fixture.landed_candidate,
                ),
            ]
        )
        last_line = int(records[2]["_line"])

        def assert_gates_are_missing() -> None:
            self.assertEqual(
                landed_evidence.missing_gate_issues(
                    records, gates, last_line, False
                ),
                MISSING_GATE_ISSUES,
            )

        assert_gates_are_missing()
        mutants = (
            (
                "M1-prime",
                "_counting_predicate",
                mutated_function(
                    landed_evidence._counting_predicate,
                    "            and (bound[0], bound[1]) in landed\n",
                    "",
                ),
            ),
            (
                "M7",
                "landed_keys",
                mutated_function(
                    landed_evidence.landed_keys,
                    '        and record.get("outcome") == "chain-landing"\n',
                    "        and record.get(\"outcome\") in "
                    '{"chain-landing", "chain-approval", "chain-abort"}\n',
                ),
            ),
        )
        for name, attribute, mutant in mutants:
            with self.subTest(mutant=name), mock.patch.object(
                landed_evidence, attribute, mutant
            ):
                with self.assertRaises(AssertionError):
                    assert_gates_are_missing()
                self.assertEqual(
                    landed_evidence.missing_gate_issues(
                        records, gates, last_line, False
                    ),
                    [],
                )

    def test_cross_task_different_candidate_gate_requires_the_landed_pair(
        self,
    ) -> None:
        fixture = self.fixture
        gate = fixture.gate(
            "cross-task-candidate",
            "gate-1: project tests",
            chain=fixture.landed_chain,
            candidate=fixture.aborted_candidate,
        )
        gate["task"] = "task-B"
        landing = fixture.decision(
            "cross-task-landing",
            "chain-landing",
            chain=fixture.landed_chain,
            candidate=fixture.landed_candidate,
        )
        landing["task"] = "task-A"
        records = fixture.relined(
            [
                fixture.activated_start(),
                *fixture.boundary_execution(),
                gate,
                landing,
            ]
        )
        last_line = int(records[2]["_line"])

        def assert_gate_is_missing() -> None:
            self.assertEqual(
                landed_evidence.missing_gate_issues(
                    records, [gate], last_line, False
                ),
                MISSING_GATE_ISSUES,
            )

        assert_gate_is_missing()
        mutant = mutated_function(
            landed_evidence._counting_predicate,
            "            and (bound[0], bound[1]) in landed\n",
            "            and any(bound[0] == chain for chain, _candidate in landed)\n",
        )
        with mock.patch.object(landed_evidence, "_counting_predicate", mutant):
            with self.assertRaises(AssertionError):
                assert_gate_is_missing()
            self.assertEqual(
                landed_evidence.missing_gate_issues(
                    records, [gate], last_line, False
                ),
                MISSING_GATE_ISSUES[1:],
            )

    def test_tombstone_basis_abort_retires_landed_gate_records(self) -> None:
        fixture = self.fixture
        gates = fixture.gate_set(
            "tombstone",
            chain=fixture.aborted_chain,
            candidate=fixture.aborted_candidate,
        )
        for gate in gates:
            gate["task"] = "task-B"
        landing = fixture.decision(
            "tombstone-landing",
            "chain-landing",
            chain=fixture.aborted_chain,
            candidate=fixture.aborted_candidate,
        )
        landing["task"] = "task-A"
        abort = fixture.decision(
            "tombstone-abort",
            "chain-abort",
            chain=fixture.aborted_chain,
            candidate=fixture.aborted_candidate,
        )
        abort["task"] = "task-B"
        abort["basis"] = [
            journal.TOMBSTONE_DISPOSITION_BASIS.format(
                chain_id=fixture.aborted_chain
            )
        ]
        records = fixture.relined(
            [
                fixture.activated_start(),
                *fixture.boundary_execution(),
                landing,
                *gates,
                abort,
            ]
        )
        last_line = int(records[2]["_line"])

        def assert_gates_are_retired() -> None:
            self.assertEqual(
                landed_evidence.missing_gate_issues(
                    records, gates, last_line, False
                ),
                MISSING_GATE_ISSUES,
            )

        self.assertTrue(journal._is_tombstone_disposition(abort))
        assert_gates_are_retired()
        anchor = (
            '        and record.get("outcome") == "chain-abort"\n'
            '        and isinstance((task := record.get("task")), str)\n'
        )
        replacement = (
            '        and record.get("outcome") == "chain-abort"\n'
            "        and not journal._is_tombstone_disposition(record)\n"
            '        and isinstance((task := record.get("task")), str)\n'
        )
        mutant = mutated_function(
            landed_evidence.retirement_predicate,
            anchor,
            replacement,
        )
        with mock.patch.object(landed_evidence, "retirement_predicate", mutant):
            with self.assertRaises(AssertionError):
                assert_gates_are_retired()
            self.assertEqual(
                landed_evidence.missing_gate_issues(
                    records, gates, last_line, False
                ),
                [],
            )


if __name__ == "__main__":
    unittest.main()
