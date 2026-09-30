from __future__ import annotations

import copy
import hashlib
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from codex_orchestrator import journal, landed_evidence  # noqa: E402

CRITERION = "gate-1: project tests"
RECHECK_ISSUE = (
    "failed gate verification 'check-failed' has no subsequent passing recheck"
)


def digest(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


class LandedRecheckSourceTests(unittest.TestCase):
    chain_a = "c-2026-09-30T110000Z-b001"
    chain_b = "c-2026-09-30T110100Z-b002"
    candidate_a = {
        "kind": "staged-diff-sha256",
        "value": digest("candidate-a"),
    }
    candidate_b = {
        "kind": "staged-diff-sha256",
        "value": digest("candidate-b"),
    }

    def binding(
        self,
        seed: str,
        *,
        chain: str,
        candidate: dict[str, object],
    ) -> dict[str, object]:
        preimage: dict[str, object] = {
            "schema": journal.BINDING_SCHEMA,
            "source_record": {
                "chain_id": chain,
                "event_digest": digest(f"event-{seed}"),
            },
            "candidate": copy.deepcopy(candidate),
            "review": None,
        }
        return {
            **preimage,
            "binding_id": journal._sha256(journal._canonical_json_bytes(preimage)),
        }

    def verification(
        self,
        seed: str,
        result: str,
        *,
        chain: str | None = None,
        candidate: dict[str, object] | None = None,
        task: str = "task-01",
    ) -> dict[str, object]:
        record: dict[str, object] = {
            "type": "verification",
            "id": f"check-{seed}",
            "task": task,
            "criterion": CRITERION,
            "result": result,
        }
        if chain is not None and candidate is not None:
            record["binding"] = self.binding(
                seed,
                chain=chain,
                candidate=candidate,
            )
        return record

    def decision(
        self,
        seed: str,
        outcome: str,
        *,
        chain: str,
        candidate: dict[str, object],
        task: str = "task-01",
    ) -> dict[str, object]:
        return {
            "type": "decision",
            "id": f"decision-{seed}",
            "task": task,
            "outcome": outcome,
            "binding": self.binding(seed, chain=chain, candidate=candidate),
        }

    @staticmethod
    def relined(records: list[dict[str, object]]) -> list[dict[str, object]]:
        for line, record in enumerate(records, 1):
            record["_line"] = line
        return records

    @staticmethod
    def activated_start() -> dict[str, object]:
        return {
            "type": "run_started",
            "writer_contract": journal.WRITER_CONTRACT,
        }

    @staticmethod
    def profile_issues(records: list[dict[str, object]]) -> list[str]:
        issues: list[str] = []
        journal.check_gate_profile(copy.deepcopy(records), issues, [], None)
        return issues

    def failed_and_passed(
        self,
        *,
        failed_chain: str | None = None,
        failed_candidate: dict[str, object] | None = None,
        passed_chain: str | None = None,
        passed_candidate: dict[str, object] | None = None,
        task: str = "task-01",
    ) -> tuple[dict[str, object], dict[str, object]]:
        return (
            self.verification(
                "failed",
                "failed",
                chain=failed_chain,
                candidate=failed_candidate,
                task=task,
            ),
            self.verification(
                "passed",
                "passed",
                chain=passed_chain,
                candidate=passed_candidate,
                task=task,
            ),
        )

    def test_aborted_chain_recheck_does_not_clear_failure_and_disable_restores_rule(
        self,
    ) -> None:
        failed, passed = self.failed_and_passed(
            failed_chain=self.chain_a,
            failed_candidate=self.candidate_a,
            passed_chain=self.chain_a,
            passed_candidate=self.candidate_a,
        )
        records = self.relined(
            [
                self.activated_start(),
                failed,
                passed,
                self.decision(
                    "abort",
                    "chain-abort",
                    chain=self.chain_a,
                    candidate=self.candidate_a,
                ),
            ]
        )

        def assert_control_applies() -> None:
            self.assertEqual(self.profile_issues(records), [RECHECK_ISSUE])

        assert_control_applies()
        with mock.patch.object(
            landed_evidence,
            "LANDED_EVIDENCE_CONTROLS",
            landed_evidence.LANDED_EVIDENCE_CONTROLS
            - {"landed-recheck-source"},
        ):
            with self.assertRaises(AssertionError):
                assert_control_applies()
            self.assertEqual(self.profile_issues(records), [])

    def test_landed_different_chain_recheck_clears_failure(self) -> None:
        failed, passed = self.failed_and_passed(
            failed_chain=self.chain_a,
            failed_candidate=self.candidate_a,
            passed_chain=self.chain_b,
            passed_candidate=self.candidate_b,
        )
        records = self.relined(
            [
                self.activated_start(),
                failed,
                passed,
                self.decision(
                    "landing",
                    "chain-landing",
                    chain=self.chain_b,
                    candidate=self.candidate_b,
                ),
            ]
        )
        self.assertEqual(self.profile_issues(records), [])

    def test_same_unlanded_candidate_recheck_clears_failure(self) -> None:
        failed, passed = self.failed_and_passed(
            failed_chain=self.chain_a,
            failed_candidate=self.candidate_a,
            passed_chain=self.chain_a,
            passed_candidate=self.candidate_a,
        )
        records = self.relined([self.activated_start(), failed, passed])
        self.assertTrue(landed_evidence.recheck_source(records)([failed, passed], 0))
        self.assertEqual(self.profile_issues(records), [])

    def test_wy8n_landed_same_chain_recheck_is_unchanged(self) -> None:
        failed, passed = self.failed_and_passed(
            failed_chain=self.chain_a,
            failed_candidate=self.candidate_a,
            passed_chain=self.chain_a,
            passed_candidate=self.candidate_a,
        )
        records = self.relined(
            [
                self.activated_start(),
                failed,
                passed,
                self.decision(
                    "landing",
                    "chain-landing",
                    chain=self.chain_a,
                    candidate=self.candidate_a,
                ),
            ]
        )
        self.assertEqual(self.profile_issues(records), [])
        with mock.patch.object(
            landed_evidence,
            "LANDED_EVIDENCE_CONTROLS",
            landed_evidence.LANDED_EVIDENCE_CONTROLS
            - {"landed-recheck-source"},
        ):
            self.assertEqual(self.profile_issues(records), [])

    def test_superseded_candidate_recheck_does_not_clear_failure(self) -> None:
        failed, passed = self.failed_and_passed(
            failed_chain=self.chain_a,
            failed_candidate=self.candidate_a,
            passed_chain=self.chain_a,
            passed_candidate=self.candidate_a,
        )
        records = self.relined(
            [
                self.activated_start(),
                failed,
                passed,
                self.decision(
                    "replacement",
                    "chain-approval",
                    chain=self.chain_a,
                    candidate=self.candidate_b,
                ),
            ]
        )
        self.assertEqual(self.profile_issues(records), [RECHECK_ISSUE])

    def test_unbound_failure_requires_a_landed_recheck(self) -> None:
        failed, passed = self.failed_and_passed(
            passed_chain=self.chain_b,
            passed_candidate=self.candidate_b,
        )
        unlanded = self.relined([self.activated_start(), failed, passed])
        self.assertEqual(self.profile_issues(unlanded), [RECHECK_ISSUE])
        landed = self.relined(
            [
                self.activated_start(),
                failed,
                passed,
                self.decision(
                    "landing",
                    "chain-landing",
                    chain=self.chain_b,
                    candidate=self.candidate_b,
                ),
            ]
        )
        self.assertEqual(self.profile_issues(landed), [])

    def test_abort_retirement_remains_task_scoped(self) -> None:
        failed, passed = self.failed_and_passed(
            failed_chain=self.chain_a,
            failed_candidate=self.candidate_a,
            passed_chain=self.chain_a,
            passed_candidate=self.candidate_a,
            task="task-B",
        )
        records = self.relined(
            [
                self.activated_start(),
                failed,
                passed,
                self.decision(
                    "task-a-abort",
                    "chain-abort",
                    chain=self.chain_a,
                    candidate=self.candidate_a,
                    task="task-A",
                ),
            ]
        )
        self.assertEqual(self.profile_issues(records), [])

    def test_legacy_any_later_identical_pass_rule_is_unchanged(self) -> None:
        failed, passed = self.failed_and_passed()
        records = self.relined([{"type": "run_started"}, failed, passed])
        self.assertEqual(self.profile_issues(records), [])
        with mock.patch.object(
            landed_evidence,
            "LANDED_EVIDENCE_CONTROLS",
            landed_evidence.LANDED_EVIDENCE_CONTROLS
            - {"landed-recheck-source"},
        ):
            self.assertEqual(self.profile_issues(records), [])


if __name__ == "__main__":
    unittest.main()
