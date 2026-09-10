from __future__ import annotations

import contextlib
import copy
import dataclasses
import io
import json
import os
from pathlib import Path
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

from tests._cli_loader import load_cli, package_module
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
                self.state["steps"][step_id] = [
                    {**passed, "env_fingerprint": "fresh-cli-fixture"},
                    {**passed, "env_fingerprint": "fresh-cli-fixture"},
                ]
            else:
                self.state["steps"][step_id] = [dict(passed)]
        CLI._transition_state(self.state, "verifying")
        self.store.create(
            self.state,
            "fresh_cli_fixture_created",
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
            "fresh_cli_fixture_artifacts",
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
        with mock.patch.object(ENGINE, "_run_halt", return_value=None):
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

        with mock.patch.object(ENGINE, "_run_halt", side_effect=halt), mock.patch.object(
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

    def test_fresh_step_projects_exact_recorded_gate_claim_to_journal(self) -> None:
        _launcher, state = self.pass_fresh()
        state["run_binding"] = {
            "run_id": "run-fresh-journal",
            "task_id": "task-02",
        }
        fake_run = SimpleNamespace(
            records=[{"type": "task", "id": "task-02", "status": "active"}]
        )
        batch, builders, _journal = RUNTIME._coordination_modules()
        fake_journal = SimpleNamespace(
            _resolve_repository=lambda repository, _operation: (
                repository,
                repository,
            ),
            _scan_run=lambda _run_dir: fake_run,
            _writer_contract_active=lambda _records: True,
        )

        with mock.patch.object(
            RUNTIME,
            "_coordination_modules",
            return_value=(batch, builders, fake_journal),
        ):
            records = ENGINE._build_chain_journal_records(
                self.repository.root,
                state,
                "step_recorded",
                {
                    "step_id": "fresh-reviewer-evals",
                    "run": 1,
                    "result": "passed",
                },
                "a" * 64,
            )

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["criterion"], "gate-2: fresh reviewer evaluation")
        self.assertEqual(
            record["method"],
            "Forge CLI commit chain — Candidate-bound fresh reviewer evaluation",
        )
        step = state["steps"]["fresh-reviewer-evals"][0]
        self.assertEqual(record["evidence"], [step["transcript"], step["manifest"]])

    def test_fresh_skip_projects_and_binds_exact_operator_reason(self) -> None:
        _batch, builders, _journal = RUNTIME._coordination_modules()
        prior = self.load()
        prior["run_binding"] = {
            "run_id": "run-fresh-skip-journal",
            "task_id": "task-02",
        }
        current = copy.deepcopy(prior)
        reason = "bootstrap trigger-region adoption"
        fact = {
            "directed_by": "operator",
            "reason": reason,
            "argv_digest": "a" * 64,
            "journaled_at": CLI.iso_z(),
        }
        current["steps"].setdefault("user_skips", {})[
            "fresh-reviewer-evals"
        ] = fact
        details = {
            "gate_id": "fresh-reviewer-evals",
            "directed_by": "operator",
            "reason": reason,
        }
        event = {
            "payload": {
                "at": current["last_event_at"],
                "details": details,
                "event": "operator_skip",
                "state": current,
            }
        }
        fake_run = SimpleNamespace(
            records=[{"type": "task", "id": "task-02", "status": "active"}]
        )
        fake_journal = SimpleNamespace(
            _resolve_repository=lambda repository, _operation: (
                repository,
                repository,
            ),
            _scan_run=lambda _run_dir: fake_run,
            _writer_contract_active=lambda _records: True,
        )

        with mock.patch.object(
            RUNTIME,
            "_coordination_modules",
            return_value=(_batch, builders, fake_journal),
        ):
            records = ENGINE._build_chain_journal_records(
                self.repository.root,
                current,
                "operator_skip",
                details,
                "b" * 64,
            )

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["type"], "decision")
        self.assertEqual(record["outcome"], "chain-skip")
        self.assertEqual(record["basis"], [])
        self.assertEqual(
            record["resolution"],
            "Forge commit chain skip recorded: fresh-reviewer-evals; "
            f"operator reason: {reason}",
        )
        self.assertTrue(
            builders._binding_matches_source_fact(
                record["binding"],
                record,
                event,
                prior,
                current,
                family="commit",
            )
        )
        for replacement in (
            "Forge commit chain skip recorded: fresh-reviewer-evals",
            "Forge commit chain skip recorded: fresh-reviewer-evals; "
            "operator reason: different reason",
        ):
            with self.subTest(replacement=replacement):
                mutated = copy.deepcopy(record)
                mutated["resolution"] = replacement
                self.assertFalse(
                    builders._binding_matches_source_fact(
                        mutated["binding"],
                        mutated,
                        event,
                        prior,
                        current,
                        family="commit",
                    )
                )
        misplaced = copy.deepcopy(record)
        misplaced["resolution"] = (
            "Forge commit chain skip recorded: fresh-reviewer-evals"
        )
        misplaced["basis"] = [reason]
        self.assertFalse(
            builders._binding_matches_source_fact(
                misplaced["binding"],
                misplaced,
                event,
                prior,
                current,
                family="commit",
            )
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

        with self.no_halt():
            code, verified = self.invoke("verify")
            self.assertEqual(code, 0, verified)
            self.assertEqual(self.load()["state"], "reviewing")
            code, requested = self.invoke("review", "request")

        self.assertEqual(code, 0, requested)
        state = self.load()
        review_request = state["review"]["request"]
        self.assertEqual(review_request["reviewer"], "review-final")
        self.assertEqual(
            review_request["iteration"],
            state["steps"]["fresh-reviewer-evals"][-1]["iteration"],
        )
        package = (self.store.common_root / review_request["package"]).read_bytes()
        self.assertIn(
            b"--- BEGIN UNTRUSTED FRESH REVIEWER EVALUATION EVIDENCE ---",
            package,
        )
        self.assertIn(
            b"--- END UNTRUSTED FRESH REVIEWER EVALUATION EVIDENCE ---",
            package,
        )
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
            self.assertIn(
                f"--- fresh verdict {result['fixture_id']} ".encode("utf-8"),
                package,
            )
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


class FreshReviewerBuilderReplayTests(FreshReviewerCLIFixture):
    def _fresh_request_transition(self):
        self.pass_fresh()
        _batch, builders, _journal = RUNTIME._coordination_modules()
        events = self.store._events(CHAIN_ID)
        request_index = next(
            index
            for index, event in enumerate(events)
            if event["payload"]["event"] == "fresh_reviewer_evals_requested"
        )
        return (
            builders,
            copy.deepcopy(events[request_index]),
            copy.deepcopy(events[request_index - 1]["payload"]["state"]),
        )

    def _fresh_terminal_transition(self):
        self.pass_fresh()
        _batch, builders, _journal = RUNTIME._coordination_modules()
        events = self.store._events(CHAIN_ID)
        terminal_index = next(
            index
            for index, event in enumerate(events)
            if event["payload"]["event"] == "step_recorded"
            and event["payload"]["details"].get("step_id")
            == "fresh-reviewer-evals"
        )
        return (
            builders,
            copy.deepcopy(events[terminal_index]),
            copy.deepcopy(events[terminal_index - 1]["payload"]["state"]),
        )

    def test_replay_rejects_request_before_baseline_and_non_v2_candidate(self) -> None:
        builders, original, prior = self._fresh_request_transition()
        self.assertTrue(
            builders._commit_transition_valid(
                original, prior, original["payload"]["state"]
            )
        )

        for missing in ("strict-evals", "secret-scan"):
            with self.subTest(missing=missing):
                out_of_order = copy.deepcopy(original)
                out_of_order_prior = copy.deepcopy(prior)
                out_of_order_current = out_of_order["payload"]["state"]
                out_of_order_prior["steps"].pop(missing)
                out_of_order_current["steps"].pop(missing)
                self.assertFalse(
                    builders._commit_transition_valid(
                        out_of_order, out_of_order_prior, out_of_order_current
                    )
                )

        malformed = copy.deepcopy(original)
        malformed_prior = copy.deepcopy(prior)
        malformed_current = malformed["payload"]["state"]
        malformed_prior["candidate"].pop("computed_at")
        malformed_current["candidate"].pop("computed_at")
        request = malformed_current["steps"]["fresh-reviewer-evals-requests"][-1]
        request["candidate"].pop("computed_at")
        malformed["payload"]["details"]["request"] = copy.deepcopy(request)
        self.assertFalse(
            builders._commit_transition_valid(
                malformed, malformed_prior, malformed_current
            )
        )

    def test_replay_rejects_terminal_before_required_gate_position(self) -> None:
        builders, original, prior = self._fresh_terminal_transition()
        self.assertTrue(
            builders._commit_transition_valid(
                original, prior, original["payload"]["state"]
            )
        )
        for missing in ("strict-evals", "secret-scan"):
            with self.subTest(missing=missing):
                out_of_order = copy.deepcopy(original)
                out_of_order_prior = copy.deepcopy(prior)
                out_of_order_current = out_of_order["payload"]["state"]
                out_of_order_prior["steps"].pop(missing)
                out_of_order_current["steps"].pop(missing)
                self.assertFalse(
                    builders._commit_transition_valid(
                        out_of_order, out_of_order_prior, out_of_order_current
                    )
                )

    def test_replay_accepts_fresh_skip_and_rejects_control_baseline_skip(self) -> None:
        _batch, builders, _journal = RUNTIME._coordination_modules()
        for gate_id in ("fresh-reviewer-evals", "strict-evals"):
            with self.subTest(gate_id=gate_id):
                prior = self.load()
                current = copy.deepcopy(prior)
                fact = {
                    "directed_by": "operator",
                    "reason": "explicit operator direction",
                    "argv_digest": "a" * 64,
                    "journaled_at": CLI.iso_z(),
                }
                current["steps"].setdefault("user_skips", {})[gate_id] = fact
                event = {
                    "payload": {
                        "at": current["last_event_at"],
                        "details": {
                            "gate_id": gate_id,
                            "directed_by": "operator",
                            "reason": fact["reason"],
                        },
                        "event": "operator_skip",
                        "state": current,
                    }
                }
                delta = builders._commit_skip_delta(event, prior, current)
                valid = builders._commit_transition_valid(event, prior, current)
                if gate_id == "fresh-reviewer-evals":
                    self.assertEqual(delta, (gate_id, fact))
                    self.assertTrue(valid)
                else:
                    self.assertIsNone(delta)
                    self.assertFalse(valid)

    def test_replay_rejects_forged_or_malformed_fresh_skip(self) -> None:
        _batch, builders, _journal = RUNTIME._coordination_modules()
        prior = self.load()
        fact = {
            "directed_by": "operator",
            "reason": "explicit operator direction",
            "argv_digest": "a" * 64,
            "journaled_at": CLI.iso_z(),
        }
        current = copy.deepcopy(prior)
        current["steps"].setdefault("user_skips", {})[
            "fresh-reviewer-evals"
        ] = copy.deepcopy(fact)
        event = {
            "payload": {
                "at": current["last_event_at"],
                "details": {
                    "gate_id": "fresh-reviewer-evals",
                    "directed_by": "operator",
                    "reason": fact["reason"],
                },
                "event": "operator_skip",
                "state": current,
            }
        }

        cases = (
            "model-author",
            "empty-reason",
            "bad-argv-digest",
            "bad-journal-time",
            "unknown-gate",
            "unconfigured-invariant",
            "extra-fact-key",
            "state-reviewing",
            "state-authorized",
            "state-classifying",
            "review-tamper",
            "approval-tamper",
            "authorization-tamper",
        )
        for case in cases:
            with self.subTest(case=case):
                malformed_event = copy.deepcopy(event)
                malformed_current = malformed_event["payload"]["state"]
                malformed_fact = malformed_current["steps"]["user_skips"][
                    "fresh-reviewer-evals"
                ]
                malformed_details = malformed_event["payload"]["details"]
                if case == "model-author":
                    malformed_fact["directed_by"] = "model"
                    malformed_details["directed_by"] = "model"
                elif case == "empty-reason":
                    malformed_fact["reason"] = ""
                    malformed_details["reason"] = ""
                elif case == "bad-argv-digest":
                    malformed_fact["argv_digest"] = "not-a-digest"
                elif case == "bad-journal-time":
                    malformed_fact["journaled_at"] = "not-a-time"
                elif case == "unknown-gate":
                    malformed_current["steps"]["user_skips"] = {
                        "unknown-gate": malformed_fact
                    }
                    malformed_details["gate_id"] = "unknown-gate"
                elif case == "unconfigured-invariant":
                    malformed_current["steps"]["user_skips"] = {
                        "invariant:999": malformed_fact
                    }
                    malformed_details["gate_id"] = "invariant:999"
                elif case == "extra-fact-key":
                    malformed_fact["extra"] = True
                elif case.startswith("state-"):
                    malformed_current["state"] = case.removeprefix("state-")
                elif case == "review-tamper":
                    malformed_current["review"]["residual_risk"] = {
                        "reason": "forged"
                    }
                elif case == "approval-tamper":
                    malformed_current["approval"] = {
                        "candidate": self.snapshot.authorization_id
                    }
                else:
                    malformed_current["authorization"] = {
                        "candidate": self.snapshot.authorization_id
                    }
                self.assertIsNone(
                    builders._commit_skip_delta(
                        malformed_event, prior, malformed_current
                    )
                )
                self.assertFalse(
                    builders._commit_transition_valid(
                        malformed_event, prior, malformed_current
                    )
                )

    def test_replay_rejects_fresh_skip_for_authenticated_zero_match(self) -> None:
        _batch, builders, _journal = RUNTIME._coordination_modules()
        with FreshEvalRepo(fenced_oracle=True) as repository:
            repository.stage_append("src/unrelated.py")
            snapshot = repository.snapshot()
            trigger = FRESH.derive_trigger(
                repository.context,
                repository.policy,
                snapshot.state_record(),
                snapshot.paths,
            )
            self.assertFalse(FRESH.trigger_required(trigger))

            repo = CLI.Repository(repository.root)
            policy_sha, policy_raw = repo.policy()
            policy = CLI.parse_policy(policy_sha, policy_raw)
            prior = CLI._new_state(
                "c-2026-09-08T120000Z-0099",
                repo,
                repo.head(),
                policy,
                snapshot.paths,
                "hard",
            )
            prior["paths"] = list(snapshot.paths)
            prior["staging"].update(
                {
                    "staged_paths": list(snapshot.paths),
                    "staged_at": CLI.iso_z(),
                }
            )
            prior["candidate"] = snapshot.state_record()
            prior["tier"].update(
                {
                    "derived": "hard",
                    "effective": "hard",
                    "control": True,
                    "categories": [],
                    "classification": {"fixture": True},
                }
            )
            CLI._transition_state(prior, "verifying")
            fact = {
                "directed_by": "operator",
                "reason": "not actually configured",
                "argv_digest": "a" * 64,
                "journaled_at": CLI.iso_z(),
            }
            current = copy.deepcopy(prior)
            current["steps"]["user_skips"] = {
                "fresh-reviewer-evals": fact
            }
            event = {
                "payload": {
                    "at": current["last_event_at"],
                    "details": {
                        "gate_id": "fresh-reviewer-evals",
                        "directed_by": "operator",
                        "reason": fact["reason"],
                    },
                    "event": "operator_skip",
                    "state": current,
                }
            }

            self.assertIsNone(
                builders._commit_skip_delta(event, prior, current)
            )
            self.assertFalse(
                builders._commit_transition_valid(event, prior, current)
            )

            block_prior = copy.deepcopy(prior)
            CLI._transition_state(block_prior, "revising")
            block_prior["steps"]["fresh-reviewer-evals"] = [
                {
                    "candidate": snapshot.authorization_id,
                    "result": "failed",
                    "outcome": "BLOCK",
                }
            ]
            block_current = copy.deepcopy(block_prior)
            CLI._transition_state(block_current, "classifying")
            block_current["steps"]["user_skips"] = {
                "fresh-reviewer-evals": fact
            }
            block_event = copy.deepcopy(event)
            block_event["payload"]["state"] = block_current
            block_event["payload"]["at"] = block_current["last_event_at"]

            self.assertIsNone(
                builders._commit_skip_delta(
                    block_event, block_prior, block_current
                )
            )
            self.assertFalse(
                builders._commit_transition_valid(
                    block_event, block_prior, block_current
                )
            )

    def test_replay_allows_flag_only_for_subject_specific_baseline_fixture(self) -> None:
        self.pass_fresh()
        _batch, builders, _journal = RUNTIME._coordination_modules()
        events = self.store._events(CHAIN_ID)
        request_index = next(
            index
            for index, event in enumerate(events)
            if event["payload"]["event"] == "fresh_reviewer_evals_requested"
        )
        self.assertGreater(request_index, 0)
        original = events[request_index]
        prior = events[request_index - 1]["payload"]["state"]
        current = original["payload"]["state"]
        self.assertTrue(builders._commit_transition_valid(original, prior, current))

        def with_flag(disposition: str) -> tuple[dict[str, object], dict[str, object]]:
            event = copy.deepcopy(original)
            state = event["payload"]["state"]
            request = state["steps"]["fresh-reviewer-evals-requests"][-1]
            target = next(
                item
                for item in request["suite"]["inventory"]
                if item["disposition"] == disposition
            )
            target["expected_verdict"] = "FLAG"
            event["payload"]["details"]["request"] = copy.deepcopy(request)
            return event, state

        baseline_event, baseline_state = with_flag(
            "subject-specific-baseline-only"
        )
        self.assertTrue(
            builders._commit_transition_valid(
                baseline_event, prior, baseline_state
            )
        )

        fresh_event, fresh_state = with_flag("fresh-review")
        self.assertFalse(
            builders._commit_transition_valid(fresh_event, prior, fresh_state)
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
