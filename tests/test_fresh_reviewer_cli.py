from __future__ import annotations

import contextlib
import copy
import dataclasses
import io
import json
import os
from pathlib import Path
import threading
import unittest
from unittest import mock


from tests import _review_lane_support as review_support
from tests._cli_loader import load_cli, package_module, patch_engine
from tests._fresh_eval_support import (
    CANDIDATE,
    FRESH,
    FreshEvalRepo,
    ScriptedLauncher,
    canonical_document,
    policy_with_trigger_region,
    sha256,
    trigger_table,
)


CLI = load_cli("forge_fresh_reviewer_cli_tests")
CORE = package_module("chain_core")
ENGINE = package_module("engine")
RUNTIME = package_module("runtime")

ROOT = Path(__file__).resolve().parents[1]
CHAIN_ID = "c-2026-09-08T120000Z-0002"
BASELINE_TRANSCRIPT = b"forge: recorded-baseline integrity fixture PASS\n"
EXPECTED_CONTROLS = frozenset(
    {
        "authenticated-trigger-source",
        "exact-staged-path-match",
        "candidate-checkout-tree",
        "oracle-withholding",
        "fixture-inventory",
        "fresh-request-binding",
        "route-binding",
        "process-completion",
        "bounded-process",
        "verdict-grammar",
        "expected-verdict-comparison",
        "artifact-digest",
        "final-index-reobservation",
        "current-candidate-step",
    }
)


class FreshReviewerCLIFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = FreshEvalRepo(fenced_oracle=True)
        self.addCleanup(self.repository.cleanup)
        self.repository.stage_append("rules/review-constitution.md")
        self.snapshot = self.repository.snapshot()

        self.repo = CLI.Repository(self.repository.root)
        policy_sha, policy_raw = self.repo.policy()
        self.policy = CLI.parse_policy(policy_sha, policy_raw)
        self.store = CLI.ChainStore(self.repo.common_root())
        self.context = CLI.CommandContext(
            repo=self.repo,
            store=self.store,
            options=CLI.CLIOptions(
                chain_id=CHAIN_ID,
                repo=str(self.repository.root),
                original_argv=("gate", "run", "fresh-reviewer-evals"),
            ),
            policy=self.policy,
        )

        self.state = CLI._new_state(
            CHAIN_ID,
            self.repo,
            self.repo.head(),
            self.policy,
            self.snapshot.paths,
            "hard",
        )
        self.state["paths"] = list(self.snapshot.paths)
        self.state["staging"].update(
            {
                "staged_paths": list(self.snapshot.paths),
                "staged_at": CLI.iso_z(),
            }
        )
        self.state["candidate"] = self.snapshot.state_record()
        self.state["tier"].update(
            {
                "derived": "hard",
                "effective": "hard",
                "control": True,
                "categories": [],
                "classification": {"fixture": True},
            }
        )
        passed = {
            "candidate": self.snapshot.authorization_id,
            "result": "passed",
        }
        self.state["steps"] = {"classification": [dict(passed)]}
        for step_id in CORE._required_steps(self.context, self.state):
            if step_id == CORE.FRESH_REVIEWER_EVALS_GATE:
                continue
            if step_id == "gate-1":
                gate_passed = {
                    **passed,
                    "env_fingerprint": "fresh-cli-fixture",
                    "stdout_stderr_digest": sha256(b"fresh-cli gate-1 fixture\n"),
                }
                self.state["steps"][step_id] = [dict(gate_passed), dict(gate_passed)]
            else:
                self.state["steps"][step_id] = [dict(passed)]
        CLI._transition_state(self.state, "verifying")
        self.store.create(
            self.state,
            "fixture_fresh_cli_created",
            {"fixture": True},
        )

        candidate_relative = (
            "candidate/"
            f"{self.snapshot.authorization_id}-"
            f"{self.snapshot.review_diff_sha256}.patch"
        )
        ENGINE._write_artifact(
            self.context,
            self.state,
            candidate_relative,
            self.snapshot.review_diff,
            exclusive=True,
        )
        baseline_ref = ENGINE._write_artifact(
            self.context,
            self.state,
            "evidence/strict-evals-fixture.log",
            BASELINE_TRANSCRIPT,
            exclusive=True,
        )
        baseline = self.state["steps"]["strict-evals"][-1]
        baseline.update(
            {
                "transcript": baseline_ref,
                "stdout_stderr_digest": sha256(BASELINE_TRANSCRIPT),
            }
        )
        self.store.persist(
            self.state,
            "fixture_fresh_cli_artifacts",
            {"fixture": True},
        )

    def invoke(self, *arguments: str) -> tuple[int, dict[str, object]]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        argv = [
            "--json",
            "--repo",
            str(self.repository.root),
            "--chain-id",
            CHAIN_ID,
            *arguments,
        ]
        with mock.patch.dict(
            os.environ, {"CLAUDE_PLUGIN_ROOT": str(ROOT)}, clear=False
        ), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = CLI.main(argv)
        self.assertEqual(stderr.getvalue(), "")
        rendered = stdout.getvalue()
        self.assertTrue(rendered.endswith("\n"), rendered)
        self.assertEqual(rendered.count("\n"), 1, rendered)
        return exit_code, json.loads(rendered)

    def load(self) -> dict[str, object]:
        return self.store.load(CHAIN_ID)

    @contextlib.contextmanager
    def no_halt(self):
        with patch_engine("_run_halt", return_value=None):
            yield

    def run_fresh(
        self, launcher: ScriptedLauncher
    ) -> tuple[int, dict[str, object]]:
        with self.no_halt(), mock.patch.object(
            FRESH, "NativeReviewerLauncher", return_value=launcher
        ):
            return self.invoke("gate", "run", "fresh-reviewer-evals")

    def pass_fresh(self) -> tuple[ScriptedLauncher, dict[str, object]]:
        launcher = ScriptedLauncher(self.repository.expected_verdicts)
        code, envelope = self.run_fresh(launcher)
        self.assertEqual(code, 0, envelope)
        self.assertEqual(envelope["message"], "forge: fresh reviewer eval PASS")
        return launcher, self.load()

    def manifest_bytes(self, state: dict[str, object] | None = None) -> bytes:
        selected = state or self.load()
        step = selected["steps"]["fresh-reviewer-evals"][-1]
        return (self.store.common_root / step["manifest"]).read_bytes()

    def persist(self, state: dict[str, object], event: str) -> None:
        self.store.persist(state, event, {"fixture": True})


class FreshReviewerCLIGateTests(FreshReviewerCLIFixture):
    def test_request_and_complete_plan_are_durable_before_native_launcher_factory(self) -> None:
        launcher = ScriptedLauncher(self.repository.expected_verdicts)
        observed: list[dict[str, object]] = []

        def native_factory():
            observed.append(copy.deepcopy(self.load()))
            return launcher

        with self.no_halt(), mock.patch.object(
            FRESH, "NativeReviewerLauncher", side_effect=native_factory
        ):
            code, envelope = self.invoke(
                "gate", "run", "fresh-reviewer-evals"
            )

        self.assertEqual(code, 0, envelope)
        self.assertEqual(envelope["message"], "forge: fresh reviewer eval PASS")
        self.assertEqual(len(observed), 1)
        before_launch = observed[0]
        requests = before_launch["steps"]["fresh-reviewer-evals-requests"]
        self.assertEqual(len(requests), 1)
        request = requests[0]
        self.assertEqual(request["candidate"], self.snapshot.state_record())
        self.assertEqual(
            FRESH.candidate_binding(request["candidate"]),
            FRESH.candidate_binding(self.snapshot.state_record()),
        )
        self.assertEqual(request["paths"], list(self.snapshot.paths))
        expected_suite, expected_packages = FRESH.prepare_request_plan(
            self.repository.context,
            self.snapshot.state_record(),
            request["request_id"],
        )
        self.assertEqual(request["suite"], expected_suite)
        self.assertEqual(request["fixture_packages"], expected_packages)
        inventory_ids = [item["id"] for item in request["suite"]["inventory"]]
        self.assertEqual(inventory_ids, sorted(inventory_ids, key=str.encode))
        self.assertEqual(len(request["suite"]["inventory"]), 11)
        self.assertEqual(len(request["fixture_packages"]), 9)
        self.assertEqual(
            [item["fixture_id"] for item in request["fixture_packages"]],
            sorted(
                (item["fixture_id"] for item in request["fixture_packages"]),
                key=str.encode,
            ),
        )
        self.assertNotIn("fresh-reviewer-evals", before_launch["steps"])
        self.assertEqual(len(launcher.started), 9)

        durable = self.load()
        step = durable["steps"]["fresh-reviewer-evals"][-1]
        self.assertEqual(step["candidate"], self.snapshot.authorization_id)
        self.assertEqual(step["request_id"], request["request_id"])
        self.assertEqual(step["outcome"], "PASS")
        self.assertEqual(step["result"], "passed")
        raw = self.manifest_bytes(durable)
        self.assertEqual(step["manifest_sha256"], sha256(raw))
        self.assertEqual(step["manifest_byte_count"], len(raw))

    def test_gate_order_requires_recorded_baseline_before_request_or_launch(self) -> None:
        state = self.load()
        state["steps"].pop("strict-evals")
        self.persist(state, "fixture_removed_strict_evals")
        launcher = ScriptedLauncher(self.repository.expected_verdicts)

        code, envelope = self.run_fresh(launcher)

        self.assertEqual(code, 1, envelope)
        self.assertEqual(
            envelope["message"],
            "fresh reviewer evaluation must run at its ordered Gate-2 position",
        )
        self.assertEqual(envelope["expected"], "strict-evals")
        self.assertEqual(envelope["observed"], "fresh-reviewer-evals")
        self.assertEqual(launcher.started, [])
        durable = self.load()
        self.assertNotIn("fresh-reviewer-evals-requests", durable["steps"])
        self.assertNotIn("fresh-reviewer-evals", durable["steps"])

    def test_control_candidate_cannot_skip_recorded_baseline(self) -> None:
        with self.no_halt():
            code, envelope = self.invoke(
                "commit",
                "skip",
                "strict-evals",
                "--reason",
                "attempted synthetic baseline",
            )

        self.assertEqual(code, 1, envelope)
        self.assertEqual(envelope["reason_code"], "skip-not-permitted")
        self.assertEqual(envelope["message"], "skip does not cover strict-evals")
        self.assertNotIn(
            "strict-evals", self.load()["steps"].get("user_skips", {})
        )

    def test_operator_skip_requires_nonempty_reason(self) -> None:
        with self.no_halt():
            code, envelope = self.invoke(
                "commit",
                "skip",
                "fresh-reviewer-evals",
                "--reason",
                "",
            )

        self.assertEqual(code, 1, envelope)
        self.assertEqual(envelope["reason_code"], "skip-not-permitted")
        self.assertEqual(envelope["message"], "skip reason must be nonempty")
        self.assertNotIn(
            "fresh-reviewer-evals",
            self.load()["steps"].get("user_skips", {}),
        )

    def test_operator_skip_records_reason_and_satisfies_verify(self) -> None:
        reason = "bootstrap the reviewer-facing trigger region"
        with self.no_halt():
            code, skipped = self.invoke(
                "commit",
                "skip",
                "fresh-reviewer-evals",
                "--reason",
                reason,
            )

        self.assertEqual(code, 0, skipped)
        self.assertEqual(skipped["reason_code"], "ok")
        self.assertEqual(
            skipped["message"],
            "operator skip recorded for fresh-reviewer-evals",
        )
        durable = self.load()
        record = durable["steps"]["user_skips"]["fresh-reviewer-evals"]
        self.assertEqual(record["directed_by"], "operator")
        self.assertEqual(record["reason"], reason)
        self.assertRegex(record["argv_digest"], r"\A[0-9a-f]{64}\Z")
        event = self.store._events(CHAIN_ID)[-1]
        self.assertEqual(event["payload"]["event"], "operator_skip")
        self.assertEqual(
            event["payload"]["details"],
            {
                "directed_by": "operator",
                "gate_id": "fresh-reviewer-evals",
                "reason": reason,
            },
        )

        with self.no_halt():
            code, verified = self.invoke("verify")

        self.assertEqual(code, 0, verified)
        self.assertEqual(
            verified["message"],
            "all required mechanical verification steps are complete",
        )
        durable = self.load()
        self.assertEqual(durable["state"], "reviewing")
        self.assertNotIn("fresh-reviewer-evals-requests", durable["steps"])
        self.assertNotIn("fresh-reviewer-evals", durable["steps"])
        self.assertEqual(
            durable["steps"]["user_skips"]["fresh-reviewer-evals"]["reason"],
            reason,
        )

    def test_recorded_baseline_reads_exact_candidate_not_mutable_worktree(self) -> None:
        state = self.load()
        state["steps"].pop("strict-evals")
        self.persist(state, "fixture_removed_strict_evals")
        mutable_result = (
            self.repository.root
            / ".forge/evals/tasks/review-passes-clean-change.result"
        )
        self.assertEqual(mutable_result.read_text(encoding="utf-8").strip(), "PASS")
        mutable_result.write_text("BLOCK\n", encoding="utf-8")
        materialized_paths: list[Path] = []
        original_materialize = FRESH.materialize_candidate

        @contextlib.contextmanager
        def observe_materialization(*args, **kwargs):
            with original_materialize(*args, **kwargs) as materialized:
                materialized_paths.append(materialized.path)
                yield materialized

        with self.no_halt(), mock.patch.object(
            FRESH, "materialize_candidate", observe_materialization
        ):
            code, envelope = self.invoke("gate", "run", "strict-evals")

        self.assertEqual(code, 0, envelope)
        self.assertEqual(envelope["message"], "gate strict-evals passed")
        self.assertEqual(len(materialized_paths), 1)
        self.assertNotEqual(materialized_paths[0], self.repository.root)
        self.assertFalse(materialized_paths[0].exists())
        durable = self.load()
        baseline = durable["steps"]["strict-evals"][-1]
        self.assertEqual(baseline["result"], "passed")
        transcript = (self.store.common_root / baseline["transcript"]).read_text(
            encoding="utf-8"
        )
        self.assertIn("PASS review-passes-clean-change", transcript)
        self.assertNotIn(
            "FAIL review-passes-clean-change (expected PASS, got BLOCK)",
            transcript,
        )

    def test_exact_exit_one_block_forbids_retry_but_allows_operator_skip(self) -> None:
        target = "review-passes-clean-change"
        launcher = ScriptedLauncher(
            self.repository.expected_verdicts,
            verdicts={target: "BLOCK"},
        )
        expected = (
            "forge: fresh reviewer eval regression: review-passes-clean-change "
            "(expected PASS, got BLOCK)"
        )

        code, envelope = self.run_fresh(launcher)

        self.assertEqual(code, 1, envelope)
        self.assertEqual(envelope["message"], expected)
        self.assertEqual(envelope["reason_code"], "evidence-incomplete")
        state = self.load()
        self.assertEqual(state["state"], "revising")
        self.assertEqual(state["review"]["iteration"], 1)
        self.assertEqual(len(state["steps"]["fresh-reviewer-evals-requests"]), 1)
        self.assertEqual(len(state["steps"]["fresh-reviewer-evals"]), 1)
        self.assertEqual(state["steps"]["fresh-reviewer-evals"][-1]["outcome"], "BLOCK")
        launches = list(launcher.started)

        code, retry = self.run_fresh(launcher)
        self.assertEqual(code, 1, retry)
        self.assertEqual(retry["reason_code"], "state-precondition")
        self.assertEqual(launcher.started, launches)
        self.assertEqual(
            len(self.load()["steps"]["fresh-reviewer-evals-requests"]), 1
        )

        with self.no_halt():
            code, skipped = self.invoke(
                "commit",
                "skip",
                "fresh-reviewer-evals",
                "--reason",
                "operator-directed bootstrap transition",
            )
        self.assertEqual(code, 0, skipped)
        self.assertEqual(skipped["state"], "classifying")
        self.assertEqual(
            skipped["next_required_step"],
            f"forge classify --chain-id {CHAIN_ID}",
        )
        skipped_state = self.load()
        self.assertEqual(
            skipped_state["steps"]["user_skips"]["fresh-reviewer-evals"][
                "reason"
            ],
            "operator-directed bootstrap transition",
        )
        self.assertEqual(
            skipped_state["steps"]["fresh-reviewer-evals"][-1]["outcome"],
            "BLOCK",
        )
        self.assertEqual(
            len(skipped_state["steps"]["fresh-reviewer-evals-requests"]), 1
        )

    def test_exact_exit_two_invalid_consumes_then_retries_at_next_iteration(self) -> None:
        target = "review-passes-clean-change"
        invalid = ScriptedLauncher(
            self.repository.expected_verdicts,
            malformed={target: b"VERDICT: MAYBE\n"},
        )

        code, envelope = self.run_fresh(invalid)

        self.assertEqual(code, 2, envelope)
        self.assertEqual(
            envelope["message"],
            "forge: fresh reviewer eval evidence invalid: reviewer result "
            "is incomplete or malformed",
        )
        state = self.load()
        self.assertEqual(state["state"], "verifying")
        self.assertEqual(state["review"]["iteration"], 1)
        first_request = state["steps"]["fresh-reviewer-evals-requests"][-1]
        first_step = state["steps"]["fresh-reviewer-evals"][-1]
        self.assertEqual(first_request["iteration"], 1)
        self.assertEqual(first_step["iteration"], 1)
        self.assertEqual(first_step["outcome"], "INVALID")

        passing = ScriptedLauncher(self.repository.expected_verdicts)
        code, retried = self.run_fresh(passing)

        self.assertEqual(code, 0, retried)
        state = self.load()
        self.assertEqual(len(state["steps"]["fresh-reviewer-evals-requests"]), 2)
        self.assertEqual(len(state["steps"]["fresh-reviewer-evals"]), 2)
        self.assertNotEqual(
            state["steps"]["fresh-reviewer-evals-requests"][0]["request_id"],
            state["steps"]["fresh-reviewer-evals-requests"][1]["request_id"],
        )
        self.assertEqual(state["steps"]["fresh-reviewer-evals"][-1]["iteration"], 2)
        self.assertEqual(state["steps"]["fresh-reviewer-evals"][-1]["outcome"], "PASS")
        self.assertEqual(state["review"]["iteration"], 1)
        self.assertEqual(len(passing.started), 9)

    def test_prelaunch_halt_leaves_durable_request_then_terminalizes_without_relaunch(self) -> None:
        launcher = ScriptedLauncher(self.repository.expected_verdicts)
        halt_calls = 0

        def halt(_context, state=None, **_kwargs):
            nonlocal halt_calls
            halt_calls += 1
            if halt_calls == 1:
                return None
            raise CLI.Refusal(
                CLI.ReasonCode.HALT_ENGAGED,
                "operator halt check refused state mutation",
                expected="check-halt.sh exit 0",
                observed="forge: halted by test sentinel",
                remediation="operator must inspect and clear the applicable AGENT_HALT sentinel",
                chain=state,
            )

        with patch_engine("_run_halt", side_effect=halt), mock.patch.object(
            FRESH, "NativeReviewerLauncher", return_value=launcher
        ):
            code, envelope = self.invoke(
                "gate", "run", "fresh-reviewer-evals"
            )

        self.assertEqual(code, 1, envelope)
        self.assertEqual(envelope["reason_code"], "halt-engaged")
        self.assertEqual(
            envelope["message"], "operator halt check refused state mutation"
        )
        self.assertEqual(launcher.started, [])
        interrupted = self.load()
        self.assertEqual(
            len(interrupted["steps"]["fresh-reviewer-evals-requests"]), 1
        )
        self.assertNotIn("fresh-reviewer-evals", interrupted["steps"])
        request_id = interrupted["steps"]["fresh-reviewer-evals-requests"][-1][
            "request_id"
        ]

        with self.no_halt(), mock.patch.object(
            FRESH, "NativeReviewerLauncher", return_value=launcher
        ):
            code, terminalized = self.invoke(
                "gate", "run", "fresh-reviewer-evals"
            )

        self.assertEqual(code, 2, terminalized)
        self.assertEqual(
            terminalized["message"],
            "forge: fresh reviewer eval evidence invalid: prior durable request "
            "has no terminal step; launch outcome is unverifiable",
        )
        self.assertEqual(launcher.started, [])
        state = self.load()
        self.assertEqual(state["review"]["iteration"], 1)
        self.assertEqual(len(state["steps"]["fresh-reviewer-evals-requests"]), 1)
        self.assertEqual(len(state["steps"]["fresh-reviewer-evals"]), 1)
        self.assertEqual(state["steps"]["fresh-reviewer-evals"][-1]["request_id"], request_id)
        self.assertEqual(state["steps"]["fresh-reviewer-evals"][-1]["outcome"], "INVALID")

        passing = ScriptedLauncher(self.repository.expected_verdicts)
        code, retried = self.run_fresh(passing)
        self.assertEqual(code, 0, retried)
        state = self.load()
        self.assertEqual(len(state["steps"]["fresh-reviewer-evals-requests"]), 2)
        self.assertEqual(state["steps"]["fresh-reviewer-evals"][-1]["iteration"], 2)
        self.assertEqual(state["steps"]["fresh-reviewer-evals"][-1]["outcome"], "PASS")
        self.assertEqual(len(passing.started), 9)

    def test_eighth_invalid_records_residual_risk_and_forbids_ninth_request(self) -> None:
        state = self.load()
        state["review"]["iteration"] = 7
        self.persist(state, "fixture_at_seventh_fresh_generation")
        target = "review-passes-clean-change"
        invalid = ScriptedLauncher(
            self.repository.expected_verdicts,
            malformed={target: b"VERDICT: MAYBE\n"},
        )

        code, envelope = self.run_fresh(invalid)

        self.assertEqual(code, 2, envelope)
        state = self.load()
        self.assertEqual(state["review"]["iteration"], 8)
        self.assertEqual(
            state["review"]["residual_risk"]["reason"],
            "fresh reviewer evaluation iteration cap reached",
        )
        request_count = len(state["steps"]["fresh-reviewer-evals-requests"])
        launches = list(invalid.started)

        code, capped = self.run_fresh(invalid)
        self.assertEqual(code, 1, capped)
        self.assertEqual(capped["reason_code"], "iteration-cap")
        self.assertEqual(
            capped["message"],
            "review iteration cap of 8 reached; no further state advancement is admitted",
        )
        self.assertEqual(invalid.started, launches)
        self.assertEqual(
            len(self.load()["steps"]["fresh-reviewer-evals-requests"]),
            request_count,
        )

    def test_eighth_block_rerun_reports_cap_and_never_launches_ninth(self) -> None:
        state = self.load()
        state["review"]["iteration"] = 7
        self.persist(state, "fixture_at_seventh_block_generation")
        target = "review-passes-clean-change"
        blocking = ScriptedLauncher(
            self.repository.expected_verdicts,
            verdicts={target: "BLOCK"},
        )

        code, envelope = self.run_fresh(blocking)
        self.assertEqual(code, 1, envelope)
        state = self.load()
        self.assertEqual(state["review"]["iteration"], 8)
        request_count = len(state["steps"]["fresh-reviewer-evals-requests"])
        launches = list(blocking.started)

        code, capped = self.run_fresh(blocking)
        self.assertEqual(code, 1, capped)
        self.assertEqual(capped["reason_code"], "iteration-cap")
        self.assertEqual(capped["observed"], "8")
        self.assertIn("commit abort --reason iteration-cap", capped["remediation"])
        self.assertEqual(blocking.started, launches)
        self.assertEqual(
            len(self.load()["steps"]["fresh-reviewer-evals-requests"]),
            request_count,
        )

    def test_final_index_reobservation_rejects_change_after_last_result(self) -> None:
        delegate = ScriptedLauncher(self.repository.expected_verdicts)
        mutation_lock = threading.Lock()
        mutated = False

        class IndexMutatingLauncher:
            def launch(inner_self, request):
                nonlocal mutated
                result = delegate.launch(request)
                with mutation_lock:
                    if len(delegate.completed) == 9 and not mutated:
                        self.repository.stage_append(
                            "rules/review-constitution.md",
                            b"\nchanged after final reviewer result\n",
                        )
                        mutated = True
                return result

        with self.no_halt(), mock.patch.object(
            FRESH,
            "NativeReviewerLauncher",
            return_value=IndexMutatingLauncher(),
        ):
            code, envelope = self.invoke(
                "gate", "run", "fresh-reviewer-evals"
            )

        self.assertTrue(mutated)
        self.assertEqual(len(delegate.started), 9)
        self.assertEqual(code, 2, envelope)
        self.assertEqual(
            envelope["message"],
            "forge: fresh reviewer eval evidence invalid: live index changed "
            "before fresh step recording",
        )

    def test_launcher_cannot_lie_about_output_cap_or_digest(self) -> None:
        target = "review-passes-clean-change"

        for label in ("overflow", "digest"):
            with self.subTest(label=label):
                delegate = ScriptedLauncher(self.repository.expected_verdicts)

                class LyingLauncher:
                    def launch(inner_self, request):
                        result = delegate.launch(request)
                        if request.fixture_id != target:
                            return result
                        if label == "overflow":
                            output = b"x" * (FRESH.EVENTS_CAP_BYTES + 1)
                            return dataclasses.replace(
                                result,
                                output=output,
                                output_digest=sha256(output),
                                output_overflow=False,
                            )
                        return dataclasses.replace(
                            result, output_digest="0" * 64
                        )

                with self.no_halt(), mock.patch.object(
                    FRESH,
                    "NativeReviewerLauncher",
                    return_value=LyingLauncher(),
                ):
                    code, envelope = self.invoke(
                        "gate", "run", "fresh-reviewer-evals"
                    )
                self.assertEqual(code, 2, envelope)
                self.assertEqual(
                    envelope["message"],
                    "forge: fresh reviewer eval evidence invalid: reviewer "
                    "result is incomplete or malformed",
                )
                manifest = json.loads(self.manifest_bytes())
                result = next(
                    item for item in manifest["results"]
                    if item["fixture_id"] == target
                )
                self.assertIsNone(result["actual_verdict"])
                if label == "overflow":
                    self.assertTrue(result["output_overflow"])
                    self.assertEqual(
                        result["events_byte_count"], FRESH.EVENTS_CAP_BYTES
                    )
                else:
                    self.assertFalse(result["output_overflow"])
                    completion = json.loads(
                        (self.store.common_root / result["completion_path"])
                        .read_bytes()
                    )
                    self.assertEqual(
                        completion["error"],
                        "reviewer output digest is malformed",
                    )




class FreshReviewerCLIProvenanceTests(FreshReviewerCLIFixture):
    def _replace_manifest(
        self,
        state: dict[str, object],
        value: dict[str, object],
        event: str,
    ) -> None:
        step = state["steps"]["fresh-reviewer-evals"][-1]
        raw = canonical_document(value)
        (self.store.common_root / step["manifest"]).write_bytes(raw)
        step["manifest_sha256"] = sha256(raw)
        step["manifest_byte_count"] = len(raw)
        self.persist(state, event)

    def test_current_step_and_foreign_tree_base_chain_request_evidence_fail_closed(self) -> None:
        launcher, original_state = self.pass_fresh()
        self.assertEqual(len(launcher.started), 9)
        original_manifest = json.loads(self.manifest_bytes(original_state))
        original_raw = canonical_document(original_manifest)
        original_step = copy.deepcopy(
            original_state["steps"]["fresh-reviewer-evals"][-1]
        )

        cases = []

        foreign_tree = copy.deepcopy(original_manifest)
        object_format = original_manifest["candidate"]["object_format"]
        oid_length = 40 if object_format == "sha1" else 64
        foreign_tree_oid = "0" * oid_length
        foreign_tree["candidate"]["tree_oid"] = foreign_tree_oid
        foreign_tree["candidate"]["authorization_id"] = CANDIDATE.authorization_id(
            object_format, foreign_tree_oid
        )
        cases.append(
            (
                "foreign-tree",
                foreign_tree,
                "forge: fresh reviewer eval evidence invalid: fresh reviewer "
                "manifest candidate binding is stale or foreign",
            )
        )

        foreign_base = copy.deepcopy(original_manifest)
        foreign_base["candidate"]["base_commit_oid"] = "1" * oid_length
        cases.append(
            (
                "foreign-base",
                foreign_base,
                "forge: fresh reviewer eval evidence invalid: fresh reviewer "
                "manifest candidate binding is stale or foreign",
            )
        )

        foreign_chain = copy.deepcopy(original_manifest)
        foreign_chain["chain_id"] = "foreign-fresh-chain"
        cases.append(
            (
                "foreign-chain",
                foreign_chain,
                "forge: fresh reviewer eval evidence invalid: fresh reviewer "
                "manifest chain/request binding is stale or foreign",
            )
        )

        stale_request = copy.deepcopy(original_manifest)
        stale_request["request_id"] = "f" * 32
        cases.append(
            (
                "stale-request",
                stale_request,
                "forge: fresh reviewer eval evidence invalid: fresh reviewer "
                "manifest chain/request binding is stale or foreign",
            )
        )

        for label, manifest, diagnostic in cases:
            with self.subTest(label=label):
                state = self.load()
                self._replace_manifest(
                    state, manifest, f"fixture_tampered_{label.replace('-', '_')}"
                )
                unused = ScriptedLauncher(self.repository.expected_verdicts)
                code, envelope = self.run_fresh(unused)
                self.assertEqual(code, 2, envelope)
                self.assertEqual(envelope["message"], diagnostic)
                self.assertEqual(unused.started, [])

                restored = self.load()
                path = self.store.common_root / original_step["manifest"]
                path.write_bytes(original_raw)
                restored["steps"]["fresh-reviewer-evals"][-1] = copy.deepcopy(
                    original_step
                )
                self.persist(restored, f"fixture_restored_{label.replace('-', '_')}")

        state = self.load()
        state["steps"]["fresh-reviewer-evals"][-1]["candidate"] = "e" * 64
        self.persist(state, "fixture_foreign_current_step")
        unused = ScriptedLauncher(self.repository.expected_verdicts)
        code, envelope = self.run_fresh(unused)
        self.assertEqual(code, 2, envelope)
        self.assertEqual(
            envelope["message"],
            "forge: fresh reviewer eval evidence invalid: prior durable request "
            "has no terminal step; launch outcome is unverifiable",
        )
        self.assertEqual(unused.started, [])

    def test_manifest_byte_count_is_required_and_reobserved(self) -> None:
        _launcher, state = self.pass_fresh()
        original = copy.deepcopy(state["steps"]["fresh-reviewer-evals"][-1])
        raw = self.manifest_bytes(state)
        self.assertEqual(original["manifest_byte_count"], len(raw))

        for label, mutate, diagnostic in (
            (
                "missing",
                lambda record: record.pop("manifest_byte_count"),
                "forge: fresh reviewer eval evidence invalid: current-candidate "
                "fresh reviewer PASS record is missing or malformed",
            ),
            (
                "wrong",
                lambda record: record.__setitem__(
                    "manifest_byte_count", len(raw) + 1
                ),
                "forge: fresh reviewer eval evidence invalid: fresh reviewer "
                "manifest byte count is missing or changed",
            ),
        ):
            with self.subTest(label=label):
                state = self.load()
                mutate(state["steps"]["fresh-reviewer-evals"][-1])
                self.persist(state, f"fixture_manifest_count_{label}")
                unused = ScriptedLauncher(self.repository.expected_verdicts)
                code, envelope = self.run_fresh(unused)
                self.assertEqual(code, 2, envelope)
                self.assertEqual(envelope["message"], diagnostic)
                self.assertEqual(unused.started, [])
                restored = self.load()
                restored["steps"]["fresh-reviewer-evals"][-1] = copy.deepcopy(
                    original
                )
                self.persist(restored, f"fixture_manifest_count_{label}_restored")

    def test_review_request_reports_tampered_fresh_evidence_as_exit_two(self) -> None:
        _launcher, _state = self.pass_fresh()
        with self.no_halt():
            code, verified = self.invoke("verify")
        self.assertEqual(code, 0, verified)
        state = self.load()
        step = state["steps"]["fresh-reviewer-evals"][-1]
        (self.store.common_root / step["manifest"]).write_bytes(b"{}\n")

        with self.no_halt():
            code, envelope = self.invoke("review", "request")

        self.assertEqual(code, 2, envelope)
        self.assertEqual(envelope["reason_code"], "evidence-incomplete")
        self.assertTrue(
            envelope["message"].startswith(
                "forge: fresh reviewer eval evidence invalid: "
            ),
            envelope,
        )

    def test_review_request_reports_missing_fresh_manifest_as_exit_two(self) -> None:
        self.pass_fresh()
        with self.no_halt():
            code, verified = self.invoke("verify")
        self.assertEqual(code, 0, verified)
        state = self.load()
        state["steps"]["fresh-reviewer-evals"][-1].pop("manifest")
        self.persist(state, "fixture_removed_fresh_manifest_binding")

        with self.no_halt():
            code, envelope = self.invoke("review", "request")

        diagnostic = (
            "forge: fresh reviewer eval evidence invalid: current-candidate "
            "fresh reviewer PASS record is missing or malformed"
        )
        self.assertEqual(code, 2, envelope)
        self.assertEqual(envelope["reason_code"], "evidence-incomplete")
        self.assertEqual(envelope["message"], diagnostic)
        self.assertEqual(envelope["observed"], diagnostic)

    def test_review_final_package_contains_complete_fresh_material(self) -> None:
        _launcher, passed = self.pass_fresh()
        fresh_manifest = self.manifest_bytes(passed)
        manifest = json.loads(fresh_manifest)
        logs = self.store.common_root / "fake-review-provider/logs"
        provider = review_support.install_fake_provider(logs.parent / "bin", "claude", log_dir=logs)

        with self.no_halt(), patch_engine("CLAUDE_EXECUTABLE", str(provider)):
            code, verified = self.invoke("verify")
            self.assertEqual(code, 0, verified)
            self.assertEqual(self.load()["state"], "reviewing")
            code, requested = self.invoke("review", "request")

        self.assertEqual(code, 0, requested)
        state = self.load()
        review_request = state["review"]["request"]
        self.assertEqual(review_request["reviewer"], "review-final")
        fresh_step = state["steps"]["fresh-reviewer-evals"][-1]
        self.assertEqual(review_request["iteration"], fresh_step["iteration"])
        completion = self.store.common_root / review_request["completion_path"]
        review_support.wait_for_completion(completion)
        launch_argv = json.loads((logs / "claude.argv.json").read_text())
        self.assertEqual(launch_argv[0], "-p")
        package = (self.store.common_root / review_request["package"]).read_bytes()
        self.assertIn(b"--- BEGIN UNTRUSTED FRESH REVIEWER EVALUATION EVIDENCE ---", package)
        self.assertIn(b"--- END UNTRUSTED FRESH REVIEWER EVALUATION EVIDENCE ---", package)
        self.assertIn(BASELINE_TRANSCRIPT, package)
        self.assertIn(fresh_manifest, package)
        self.assertIn(b'"schema":"forge-review-fresh-eval-evidence/1"', package)
        self.assertIn(b'"excluded_fixtures"', package)
        self.assertIn(b'"fr223-bang-bypass-v1"', package)
        self.assertIn(b'"fr223-bang-channel-temptation-v1"', package)
        self.assertIn(b'"verdict_summary"', package)
        for result in manifest["results"]:
            verdict = (self.store.common_root / result["verdict_path"]).read_bytes()
            self.assertIn(verdict, package)
            marker = f"--- fresh verdict {result['fixture_id']} ".encode()
            self.assertIn(marker, package)
        self.assertLess(
            package.index(b"--- END UNTRUSTED FRESH REVIEWER EVALUATION EVIDENCE ---"),
            package.index(b"--- BEGIN UNTRUSTED CANDIDATE DIFF ---"),
        )


class FreshReviewerCLIDisableMatrixTests(FreshReviewerCLIFixture):
    def _authorize_fixture(self) -> None:
        state = self.load()
        candidate = state["candidate"]["sha256"]
        state["review"]["verdict"] = {
            "verdict": "PASS",
            "candidate": candidate,
            "findings": [],
        }
        state["approval"] = {
            "candidate": candidate,
            "approved_at": CLI.iso_z(),
            "qualification": {"fixture": True},
        }
        state["steps"]["approval-qualification"] = [
            {"candidate": candidate, "result": "passed"}
        ]
        CLI._transition_state(state, "reviewing")
        CLI._transition_state(state, "awaiting_approval")
        CLI._issue_authorization(state, self.context)
        self.persist(state, "fixture_authorized_for_finalize_matrix")

    def test_every_fresh_control_is_fail_closed_through_cli_finalize(self) -> None:
        self.assertEqual(FRESH.REQUIRED_CONTROLS, EXPECTED_CONTROLS)
        self.assertEqual(FRESH.FRESH_EVAL_CONTROLS, EXPECTED_CONTROLS)
        self.pass_fresh()
        self._authorize_fixture()
        original_fresh_check = ENGINE.FINALIZE_CHECKS["fresh-reviewer-evals"]

        for control in sorted(EXPECTED_CONTROLS):
            with self.subTest(control=control):
                def disable_only_during_fresh_check(context, *, selected=control):
                    with mock.patch.object(
                        FRESH,
                        "FRESH_EVAL_CONTROLS",
                        FRESH.REQUIRED_CONTROLS - {selected},
                    ):
                        return original_fresh_check(context)

                with mock.patch.dict(
                    ENGINE.FINALIZE_CHECKS,
                    {
                        "halt": lambda _context: True,
                        "lock": lambda _context: True,
                        "fresh-reviewer-evals": disable_only_during_fresh_check,
                    },
                ):
                    code, envelope = self.invoke(
                        "commit", "finalize", "--message", "must not commit"
                    )
                diagnostic = (
                    "forge: fresh reviewer eval evidence invalid: required control "
                    f"unavailable: {control}"
                )
                self.assertEqual(code, 2, envelope)
                self.assertEqual(envelope["reason_code"], "evidence-incomplete")
                self.assertEqual(envelope["message"], diagnostic)
                self.assertEqual(envelope["observed"], diagnostic)
                self.assertEqual(self.load()["state"], "authorized")
                self.assertEqual(self.repo.head(), self.state["repo_head"])

    def test_finalize_reports_tampered_fresh_evidence_as_exit_two(self) -> None:
        self.pass_fresh()
        self._authorize_fixture()
        state = self.load()
        step = state["steps"]["fresh-reviewer-evals"][-1]
        (self.store.common_root / step["manifest"]).write_bytes(b"{}\n")

        with mock.patch.dict(
            ENGINE.FINALIZE_CHECKS,
            {"halt": lambda _context: True, "lock": lambda _context: True},
        ):
            code, envelope = self.invoke(
                "commit", "finalize", "--message", "must not commit"
            )

        self.assertEqual(code, 2, envelope)
        self.assertEqual(envelope["reason_code"], "evidence-incomplete")
        self.assertTrue(
            envelope["message"].startswith(
                "forge: fresh reviewer eval evidence invalid: "
            ),
            envelope,
        )
        self.assertEqual(self.load()["state"], "authorized")
        self.assertEqual(self.repo.head(), self.state["repo_head"])

    def test_finalize_reports_missing_fresh_manifest_as_exit_two(self) -> None:
        self.pass_fresh()
        self._authorize_fixture()
        state = self.load()
        state["steps"]["fresh-reviewer-evals"][-1].pop("manifest")
        self.persist(state, "fixture_removed_finalize_fresh_manifest_binding")

        with mock.patch.dict(
            ENGINE.FINALIZE_CHECKS,
            {"halt": lambda _context: True, "lock": lambda _context: True},
        ):
            code, envelope = self.invoke(
                "commit", "finalize", "--message", "must not commit"
            )

        diagnostic = (
            "forge: fresh reviewer eval evidence invalid: current-candidate "
            "fresh reviewer PASS record is missing or malformed"
        )
        self.assertEqual(code, 2, envelope)
        self.assertEqual(envelope["reason_code"], "evidence-incomplete")
        self.assertEqual(envelope["message"], diagnostic)
        self.assertEqual(envelope["observed"], diagnostic)
        self.assertEqual(self.load()["state"], "authorized")
        self.assertEqual(self.repo.head(), self.state["repo_head"])

    def test_unknown_active_control_is_exit_two_before_request(self) -> None:
        launcher = ScriptedLauncher(self.repository.expected_verdicts)
        with self.no_halt(), mock.patch.object(
            FRESH,
            "FRESH_EVAL_CONTROLS",
            FRESH.REQUIRED_CONTROLS | {"surprise"},
        ), mock.patch.object(
            FRESH, "NativeReviewerLauncher", return_value=launcher
        ):
            code, envelope = self.invoke(
                "gate", "run", "fresh-reviewer-evals"
            )
        self.assertEqual(code, 2, envelope)
        self.assertEqual(
            envelope["message"],
            "forge: fresh reviewer eval evidence invalid: unknown active control: surprise",
        )
        self.assertEqual(launcher.started, [])
        self.assertNotIn(
            "fresh-reviewer-evals-requests", self.load()["steps"]
        )


class FreshEvalSupportTests(unittest.TestCase):
    def test_policy_helper_replaces_existing_trigger_region_once(self) -> None:
        raw = b"fixture policy\n"
        first = policy_with_trigger_region(raw)
        replacement = trigger_table().replace("rules/**", "rules/**/*.md")
        second = policy_with_trigger_region(first, replacement)

        self.assertEqual(
            second.count(
                b"<!-- FORGE:REGION reviewer-facing-eval-triggers BEGIN -->"
            ),
            1,
        )
        self.assertEqual(
            second.count(
                b"<!-- FORGE:REGION reviewer-facing-eval-triggers END -->"
            ),
            1,
        )
        self.assertIn(b"| constitution | rules/**/*.md |", second)
        self.assertNotIn(b"| constitution | rules/** |", second)


if __name__ == "__main__":
    unittest.main()
