"""Engine coverage for index flags that hide working-tree drift."""

from __future__ import annotations

import sys
from unittest import mock

import tests.test_cli_chain as chain_tests
import tests.test_cli_chain_finalize as finalize_tests

FLAG_SUFFIX = "index flag: git diff cannot compare it; clear the flag, then restage)"


def flagged(path: str, name: str) -> str:
    return f"{path} ({name} {FLAG_SUFFIX}"


class FlagDriftChainTests(chain_tests.ForgeCLIFixture):
    def start_test_candidate(self) -> tuple[str, str]:
        path = "tests/test_flag.py"
        (self.repo / "tests").mkdir()
        self.change(path, "def test_flag():\n    pass\n")
        chain_id = str(self.start(path)["chain_id"])
        return path, chain_id

    def test_sensor_refuses_assume_unchanged_before_launch(self) -> None:
        path, chain_id = self.start_test_candidate()
        self.git("update-index", "--assume-unchanged", path)
        self.change(path, "def test_flag():\n    assert True\n")
        label = flagged(path, "assume-unchanged")

        _result, refusal = self.cli("verify", "--chain-id", chain_id, expected=1)

        self.assert_refusal_contract(refusal, "drift-tree-index")
        self.assertEqual(
            refusal["message"],
            "working tree differs from staged candidate before assertion sensor: "
            + label,
        )
        self.assertEqual(refusal["observed"], label)
        self.assertNotIn("assertion-sensor", self.gate_lines())

    def test_sensor_refuses_deleted_skip_worktree_before_launch(self) -> None:
        path, chain_id = self.start_test_candidate()
        self.git("update-index", "--skip-worktree", path)
        (self.repo / path).unlink()
        label = flagged(path, "skip-worktree")

        _result, refusal = self.cli("verify", "--chain-id", chain_id, expected=1)

        self.assert_refusal_contract(refusal, "drift-tree-index")
        self.assertEqual(
            refusal["message"],
            "working tree differs from staged candidate before assertion sensor: "
            + label,
        )
        self.assertEqual(refusal["observed"], label)
        self.assertNotIn("assertion-sensor", self.gate_lines())
        evidence_dir = self.repo / ".forge" / "chains" / chain_id / "evidence"
        transcripts = "\n".join(
            path.read_text(encoding="utf-8", errors="replace")
            for path in evidence_dir.glob("*.log")
        )
        self.assertNotIn("forge: deleted test path skipped:", transcripts)

    def test_review_request_refuses_assume_unchanged_drift(self) -> None:
        path = "src/app.py"
        self.change(path, "VALUE = 2\n")
        chain_id = str(self.start(path)["chain_id"])
        self.cli("verify", "--chain-id", chain_id, expected=0)
        self.git("update-index", "--assume-unchanged", path)
        self.change(path, "VALUE = 3\n")
        label = flagged(path, "assume-unchanged")

        _result, refusal = self.cli(
            "review", "request", "--chain-id", chain_id, expected=1
        )

        self.assert_refusal_contract(refusal, "drift-tree-index")
        self.assertEqual(
            refusal["message"],
            "working tree differs from staged review candidate: " + label,
        )
        self.assertEqual(refusal["observed"], label)
        state = self.state(chain_id)
        self.assertEqual(state["state"], "reviewing")
        self.assertIsNone(state["review"]["request"])


class FlagDriftFinalizeTests(finalize_tests.FinalizeFixture):
    def hide_tracked_candidate(self) -> str:
        self.git("update-index", "--assume-unchanged", "tracked.txt")
        (self.root / "tracked.txt").write_text(
            "candidate one\nhidden working tree\n", encoding="utf-8"
        )
        return flagged("tracked.txt", "assume-unchanged")

    def test_finalize_refuses_assume_unchanged_drift(self) -> None:
        label = self.hide_tracked_candidate()

        refusal = self.assert_refusal(
            finalize_tests.CLI.ReasonCode.DRIFT_TREE_INDEX,
            "working tree differs from staged candidate at finalize: " + label,
        )

        self.assertEqual(refusal.observed, label)

    def test_parser_disable_reopens_finalize_bypass(self) -> None:
        self.hide_tracked_candidate()
        repository_module = sys.modules[finalize_tests.CLI.Repository.__module__]

        with mock.patch.object(
            repository_module, "_flagged_index_labels", return_value=[]
        ):
            self.assertEqual(self.repo.tree_index_drift(["tracked.txt"]), [])
            with self.patched_helpers():
                outcome = self.engine.finalize("fixture commit")

        self.assertTrue(outcome.ok)
        self.assertEqual(outcome.state, "closed")

    def test_operator_index_drift_skip_allows_flagged_finalize(self) -> None:
        self.hide_tracked_candidate()
        self.state["steps"]["user_skips"] = {
            "index-drift": {
                "directed_by": "operator",
                "reason": "commit the staged snapshot",
                "argv_digest": "a" * 64,
                "journaled_at": finalize_tests.CLI.iso_z(),
            }
        }
        self.persist()

        with self.patched_helpers():
            outcome = self.engine.finalize("fixture commit")

        self.assertTrue(outcome.ok)
        self.assertEqual(outcome.state, "closed")
        self.assertEqual(self.git("show", "HEAD:tracked.txt").stdout, "candidate one\n")
        self.assertEqual(
            (self.root / "tracked.txt").read_text(encoding="utf-8"),
            "candidate one\nhidden working tree\n",
        )
