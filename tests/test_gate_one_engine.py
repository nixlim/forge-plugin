"""Gate 1 once per candidate through the real engine (Revision 17).

CLI-level scenarios reuse the subprocess fixture from ``tests.test_cli_chain``; the in-process
switch test reuses the finalize fixture so the docs-class predicate can be disabled in memory
against a persisted chain. Both fixtures are imported as modules so their own suites are not
collected twice.
"""

from __future__ import annotations

import tests.test_cli_chain as chain_tests
import tests.test_cli_chain_finalize as finalize_tests


class GateOneChainTests(chain_tests.ForgeCLIFixture):
    def test_gate_one_runs_once_per_candidate_and_reruns_once_after_a_failure(self) -> None:
        self.change("src/app.py", "VALUE = 2\n")
        chain_id = str(self.start("src/app.py")["chain_id"])
        _result, failed = self.cli(
            "verify",
            "--chain-id",
            chain_id,
            expected=1,
            FORGE_TEST_FAIL_ONCE="gate-1",
        )
        self.assertEqual(failed["reason_code"], "evidence-incomplete")
        failed_state = self.state(chain_id)
        self.assertEqual(len(failed_state["steps"]["gate-1"]), 1)
        self.assertEqual(failed_state["steps"]["gate-1"][0]["result"], "failed")

        _result, verified = self.cli(
            "verify",
            "--chain-id",
            chain_id,
            expected=0,
            FORGE_TEST_FAIL_ONCE="gate-1",
        )
        self.assertEqual(verified["state"], "reviewing")
        state = self.state(chain_id)
        runs = state["steps"]["gate-1"]
        # One failed execution and exactly one passing recheck: the gate is
        # satisfied by the newest current run, never by a counted pair.
        self.assertEqual([record["result"] for record in runs], ["failed", "passed"])
        self.assertEqual(self.gate_lines().count("gate-1"), 2)
        self.assertTrue(all("pair_voided" not in record for record in runs))
        self.assertNotIn(
            "gate_1_pair_voided",
            [event["payload"]["event"] for event in self.events(chain_id)],
        )
        # A satisfied gate is not re-run by a later verify.
        self.cli("verify", "--chain-id", chain_id, expected=0)
        self.assertEqual(self.gate_lines().count("gate-1"), 2)

    def test_docs_class_candidate_records_gate_one_skip_without_launching_the_cell(self) -> None:
        self.change("docs/guide.md", "# Docs only\n")
        chain_id = str(self.start("docs/guide.md")["chain_id"])
        _result, verified = self.cli("verify", "--chain-id", chain_id, expected=0)
        state = self.state(chain_id)
        self.assertEqual(state["tier"]["effective"], "fast")
        self.assertFalse(state["tier"]["control"])
        runs = state["steps"]["gate-1"]
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["result"], "skipped")
        self.assertEqual(runs[0]["reason"], "docs-class candidate")
        self.assertTrue(runs[0]["skipped"])
        self.assertEqual(runs[0]["candidate"], state["candidate"]["sha256"])
        self.assertEqual(runs[0]["command_argv"], [])
        self.assertNotIn("gate-1", self.gate_lines())
        transcript = (self.repo / runs[0]["transcript"]).read_text(encoding="utf-8")
        self.assertIn("gate-1 skipped", transcript)
        self.assertIn("docs-class candidate", transcript)
        self.assertIn("path: docs/guide.md", transcript)
        skip_events = [
            event["payload"]["details"]
            for event in self.events(chain_id)
            if event["payload"]["event"] == "step_recorded"
            and event["payload"]["details"].get("step_id") == "gate-1"
        ]
        self.assertEqual(skip_events, [{"step_id": "gate-1", "result": "skipped", "run": 1}])
        self.assertEqual(verified["state"], "authorized")

    def test_mixed_candidate_with_a_docs_path_still_runs_gate_one(self) -> None:
        self.change("docs/guide.md", "# Docs and code\n")
        self.change("src/app.py", "VALUE = 3\n")
        _result, started = self.cli(
            "commit", "start", "--paths", "docs/guide.md", "src/app.py", expected=0
        )
        chain_id = str(started["chain_id"])
        self.cli("verify", "--chain-id", chain_id, expected=0)
        state = self.state(chain_id)
        runs = state["steps"]["gate-1"]
        self.assertEqual([record["result"] for record in runs], ["passed"])
        self.assertEqual(self.gate_lines().count("gate-1"), 1)

    def test_direct_gate_one_run_on_a_docs_class_candidate_records_the_skip(self) -> None:
        self.change("docs/guide.md", "# Docs only\n")
        chain_id = str(self.start("docs/guide.md")["chain_id"])
        _result, outcome = self.cli("gate", "run", "gate-1", "--chain-id", chain_id, expected=0)
        self.assertIn("docs-class candidate", outcome["message"])
        self.assertNotIn("gate-1", self.gate_lines())
        state = self.state(chain_id)
        self.assertEqual(state["steps"]["gate-1"][-1]["result"], "skipped")
        # The skip satisfies the gate: a second direct run records nothing new
        # because verify already treats the gate as complete.
        self.cli("verify", "--chain-id", chain_id, expected=0)
        self.assertEqual(len(self.state(chain_id)["steps"]["gate-1"]), 1)


class GateOneEngineSwitchTests(finalize_tests.FinalizeFixture):
    def docs_class_evidence(self) -> list[dict[str, object]]:
        return [
            {
                "path": path,
                "status": "M",
                "categories": ["docs"],
                "matched_rows": [{"tier": "fast", "pattern": "docs/**"}],
                "formatting_only": False,
                "formatting_decision": "line-shape",
                "dependency_decision": [],
                "unknown_manifest_floor": False,
                "control_floor": False,
                "trigger_matches": [],
                "path_tier": "fast",
            }
            for path in self.state["paths"]
        ]

    def test_docs_class_predicate_is_the_switch_between_gate_one_skip_and_run(self) -> None:
        # Same persisted chain, same verb: with the classifier's per-path evidence
        # proving every path docs-class the engine records a skip and launches no
        # cell; with the predicate disabled in memory the very same call launches
        # the committed gate-1 cell. The predicate, not the verb, is load-bearing.
        self.state["state"] = "verifying"
        self.state["steps"].pop("gate-1")
        self.state["tier"].update(
            {"categories": ["docs"], "classification": {"paths": self.docs_class_evidence()}}
        )
        self.persist()
        with self.patched_helpers() as calls:
            outcome = self.engine.gate_run("gate-1")
        self.assertTrue(outcome.ok)
        self.assertIn("docs-class candidate", outcome.message)
        self.assertNotIn("-c", calls)  # no `bash -c <cell>` launch
        skipped = self.store.load(finalize_tests.CHAIN_ID)
        self.assertEqual(
            [(r["result"], r["reason"]) for r in skipped["steps"]["gate-1"]],
            [("skipped", "docs-class candidate")],
        )
        self.assertEqual(skipped["steps"]["gate-1"][0]["candidate"], self.candidate)
        self.assertTrue(finalize_tests.CLI._gate_one_complete(skipped))

        skipped["steps"].pop("gate-1")
        self.store.persist(skipped, "fixture_adjusted", {"fixture": True})
        with finalize_tests.patch_chain_core("_docs_class_candidate", return_value=False):
            with self.patched_helpers() as calls:
                outcome = self.engine.gate_run("gate-1")
        self.assertTrue(outcome.ok)
        self.assertIn("-c", calls)
        ran = self.store.load(finalize_tests.CHAIN_ID)
        self.assertEqual([r["result"] for r in ran["steps"]["gate-1"]], ["passed"])
        self.assertEqual(ran["steps"]["gate-1"][0]["command_argv"][:2], ["bash", "-c"])
