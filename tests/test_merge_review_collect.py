"""Focused merge-lane launch, collect, cancel, and compatibility tests."""

from __future__ import annotations

import json
import time
import unittest
from contextlib import contextmanager, nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests import _review_lane_support as review_support
from tests import test_cli_merge_adapters as adapters
from tests._cli_loader import package_module, patch_chain_core, patch_engine

APP_REVIEW = package_module("app._engine_review_launch")
APP_REQUEST = package_module("app._engine_review_request")
CORE = package_module("chain_core")
ENGINE, LANE_API = package_module("engine"), package_module("engine._review_lane_api")


class MergeReviewCollectTests(adapters.MergeAdapterFixture):
    """Exercise Option A through the real merge store and detached wrapper."""

    def setUp(self) -> None:
        super().setUp()
        self.bin_dir = self.temp_root / "review-bin"

    @contextmanager
    def provider(self, mode: str = "pass"):
        executable = review_support.install_fake_provider(
            self.bin_dir, "claude", mode=mode,
            log_dir=self.temp_root / f"review-logs-{mode}",
            executable_name=f"claude-{mode}",
        )
        with patch_engine("CLAUDE_EXECUTABLE", str(executable)):
            yield executable

    def launch(self, engine, store, mode: str = "pass"):
        with self.provider(mode):
            outcome = engine.review_request()
        state = store.load(self.chain_id)
        request = state["review"]["request"]
        completion = store.common_root / request["completion_path"]
        return outcome, state, request, completion

    @staticmethod
    def wait_for(path: Path) -> None:
        review_support.wait_for_completion(path, timeout=10.0)

    @staticmethod
    def wait_for_identity(path: Path) -> None:
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if path.exists():
                return
            time.sleep(0.02)
        raise AssertionError("review identity was not published within 10 s")

    def test_launch_and_collect_pass_through_review_attached(self) -> None:
        _admission, _generation, store, engine, _outcome, _calls = self.verify_chain()
        outcome, requested, request, completion = self.launch(engine, store)
        self.assertIn("launched detached", outcome.message)
        self.assertEqual(outcome.next_required_step,
                         f"forge review collect --chain-id {self.chain_id}")
        self.assertEqual(request["lane"], "forge-review-lane/1")
        self.assertEqual(request["provider"], "claude")
        self.assertEqual(set(request["route"]), {
            "provider", "model", "effort", "route_source", "route_sha256",
        })
        package = self.repo / request["package"]
        self.assertIn(request["attempt"], request["package"])
        package_bytes = package.read_bytes()
        self.assertIn(b"route: claude/fable/high/plugin-default/", package_bytes)
        self.assertIn(b"sandbox: instruction-bounded", package_bytes)
        self.assertIn(b"role-body-digest: ", package_bytes)
        self.assertEqual(requested["review"]["iteration"], 1)

        self.wait_for(completion)
        collected = engine.review_collect()
        current = store.load(self.chain_id)
        self.assertEqual(collected.message, "merge review PASS recorded")
        self.assertIn(current["state"], {"authorized", "awaiting_approval"})
        self.assertEqual(current["review"]["verdict"]["reviewer_role"], "review-final")
        event_lines = store.events_path(self.chain_id).read_text().splitlines()
        events = [json.loads(line)["event"] for line in event_lines]
        self.assertEqual(events[-2:], ["review_requested", "review_attached"])

    def test_nonzero_completion_is_a_synthetic_block(self) -> None:
        _admission, _generation, store, engine, _outcome, _calls = self.verify_chain()
        _outcome, _state, request, completion = self.launch(engine, store, "nonzero")
        self.wait_for(completion)
        with mock.patch.object(
            engine.store, "transition", side_effect=RuntimeError("fixture transition crash")
        ), self.assertRaisesRegex(RuntimeError, "fixture transition crash"):
            engine.review_collect()
        outcome = engine.review_collect()
        current = store.load(self.chain_id)
        self.assertEqual(outcome.message, "merge review BLOCK recorded")
        self.assertEqual(current["state"], "revising")
        finding = current["review"]["verdict"]["findings"][0]
        self.assertEqual(finding["severity"], "MAJOR")
        self.assertIn("no reviewer verdict", finding["text"])
        self.assertIn(str(request["completion_path"]), finding["text"])

    def test_cancel_spends_iteration_and_next_request_supersedes(self) -> None:
        _admission, _generation, store, engine, _outcome, _calls = self.verify_chain()
        _outcome, _state, first, completion = self.launch(engine, store, "hang")
        identity = store.common_root / first["identity_path"]
        self.wait_for_identity(identity)
        cancelled = engine.review_cancel()
        record = json.loads(completion.read_text())
        self.assertEqual(record["error"], "cancelled")
        self.assertIn("iteration spent", cancelled.message)
        after_cancel = store.load(self.chain_id)
        self.assertEqual(after_cancel["review"]["iteration"], 1)
        self.assertEqual(after_cancel["review"]["request"], first)

        _outcome, second_state, second, second_completion = self.launch(engine, store, "hang")
        self.assertEqual(second_state["review"]["iteration"], 2)
        self.assertNotEqual(first["attempt"], second["attempt"])
        self.wait_for_identity(store.common_root / second["identity_path"])
        with self.assertRaises(adapters.CLI.Refusal) as caught:
            engine.review_collect()
        stale = completion.parent / "stale.json"
        self.assertTrue(stale.is_file())
        stale_ref = stale.relative_to(store.common_root).as_posix()
        self.assertIn(stale_ref, caught.exception.evidence_refs)
        engine.review_cancel()

    def test_attach_is_retired_for_every_new_lane_request(self) -> None:
        _admission, _generation, store, engine, _outcome, _calls = self.verify_chain()
        _outcome, _state, _request, completion = self.launch(engine, store)
        verdict = self.temp_root / "external-verdict.txt"
        verdict.write_text("VERDICT: PASS\n", encoding="utf-8")
        with self.assertRaises(adapters.CLI.Refusal) as caught:
            engine.review_attach(str(verdict))
        self.assertIn("launched requests complete through review collect", caught.exception.message)
        self.assertIn("review collect", caught.exception.remediation)
        self.wait_for(completion)
        engine.review_collect()

    def test_unknown_lane_precedes_legacy_attach_and_empty_shape_fields(self) -> None:
        request = {"lane": "forge-review-lane/99", "reviewer": "review-final",
                   "invocation": "legacy-looking"}
        state = {"chain_id": self.chain_id, "review": {"request": request}}
        with self.assertRaises(adapters.CLI.Refusal) as caught:
            APP_REQUEST._legacy_attach_request(SimpleNamespace(), state)
        self.assertEqual(caught.exception.message, ENGINE.NEWER_SHAPE_LITERAL)

        empty_new_shape = {"reviewer": "review-final", "provider": ""}
        with self.assertRaises(adapters.CLI.Refusal) as caught:
            APP_REVIEW._recover_retryable(SimpleNamespace(), state, empty_new_shape)
        self.assertEqual(caught.exception.message, ENGINE.NEWER_SHAPE_LITERAL)

        fake = SimpleNamespace(_load=lambda: state, _halt=mock.Mock())
        def assert_cancel_shape():
            with self.assertRaises(adapters.CLI.Refusal) as cancelled:
                APP_REVIEW.review_cancel(fake)
            self.assertEqual(cancelled.exception.message, ENGINE.NEWER_SHAPE_LITERAL)
            self.assertIn("merge abort", cancelled.exception.remediation)
        assert_cancel_shape()
        with mock.patch.object(APP_REVIEW, "_LANE", request["lane"]), \
                self.assertRaises(AssertionError):
            assert_cancel_shape()

    def test_route_resolution_uses_remote_tip(self) -> None:
        _admission, _generation, store, engine, _outcome, _calls = self.verify_chain()
        before = store.load(self.chain_id)
        remote_tip = str(before["candidate"]["remote_tip"])
        original = ENGINE.resolve_review_route
        with self.provider(), patch_engine("resolve_review_route", wraps=original) as resolve:
            engine.review_request()
        self.assertEqual(resolve.call_args.args[2], remote_tip)
        request = store.load(self.chain_id)["review"]["request"]
        self.wait_for(store.common_root / request["completion_path"])
        engine.review_collect()

    def test_completion_binding_mismatch_and_malformed_record_fail_closed(self) -> None:
        _admission, _generation, store, engine, _outcome, _calls = self.verify_chain()
        _outcome, _state, request, completion = self.launch(engine, store)
        self.wait_for(completion)
        original = completion.read_bytes()
        record = json.loads(original)
        record["provider"] = "codex"
        completion.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
        with self.assertRaises(adapters.CLI.Refusal) as caught:
            engine.review_collect()
        self.assertIn("does not bind", caught.exception.message)
        self.assertIn("merge abort", caught.exception.remediation)

        completion.write_text("{malformed", encoding="utf-8")
        with self.assertRaises(adapters.CLI.Refusal) as caught:
            engine.review_collect()
        self.assertEqual(caught.exception.message, "forge: review attempt record is invalid")
        completion.write_bytes(original)
        engine.review_collect()

    def test_authentication_failure_spends_iteration_and_allows_retry(self) -> None:
        _admission, _generation, store, engine, _outcome, _calls = self.verify_chain()
        _outcome, _state, stale_request, stale_completion = self.launch(engine, store, "hang")
        self.wait_for_identity(store.common_root / stale_request["identity_path"])
        engine.review_cancel()
        _outcome, _state, request, completion = self.launch(engine, store, "auth")
        self.wait_for(completion)
        with self.assertRaises(adapters.CLI.Refusal) as caught:
            engine.review_collect()
        expected = ("forge: claude launch refused — claude CLI is not logged in; "
                    "run interactive /login manually and retry")
        self.assertEqual(caught.exception.message, expected)
        stale = stale_completion.parent / "stale.json"
        stale_ref = stale.relative_to(store.common_root).as_posix()
        self.assertIn(stale_ref, caught.exception.evidence_refs)
        _outcome, retried, second, second_completion = self.launch(engine, store)
        self.assertEqual(retried["review"]["iteration"], 3)
        self.assertNotEqual(second["attempt"], request["attempt"])
        self.wait_for(second_completion)
        engine.review_collect()

    def test_cancel_admits_inactive_cap_and_terminal_completion_only_states(self) -> None:
        identity = {
            "schema": "forge-review-identity/1",
            "attempt": "attempt-0123456789abcdef",
            "wrapper_pid": 77,
            "pgid": 77,
            "wrapper_birth": {"kind": "linux-proc", "boot_id": "boot", "starttime": 1},
            "reviewer_pid": None,
            "reviewer_birth": None,
            "started_at": "2026-09-27T00:00:00Z",
        }
        request = {"lane": "forge-review-lane/1", "attempt": identity["attempt"],
                   "completion_path": "completion.json"}
        cases = (
            ("reviewing", 1, "2999-01-01T00:00:00Z"),
            ("revising", 8, "2999-01-01T00:00:00Z"),
            ("authorized", 1, "2000-01-01T00:00:00Z"),
            ("aborted", 1, "2999-01-01T00:00:00Z"),
            ("closed", 1, "2999-01-01T00:00:00Z"),
        )
        for state_name, iteration, inactive_after in cases:
            state = {"chain_id": self.chain_id, "state": state_name,
                     "inactive_after": inactive_after,
                     "review": {"iteration": iteration, "request": request}}
            fake = SimpleNamespace(
                _load=lambda state=state: state,
                _halt=mock.Mock(),
                _read_cancel_records=lambda *_args: (identity, None),
                _refuse_wrapper_identity_unproven=lambda *_args: None,
                _cancel_group_outcome=lambda _state, _identity, proof: ("wrapper-lost", proof),
                _publish_cancel_completion=mock.Mock(return_value="wrapper-lost"),
                _review_retry_outcome=mock.Mock(return_value="completion-only"),
            )
            fake._review_cancel_admitted = lambda current, owner=fake: \
                APP_REQUEST._review_cancel_admitted(owner, current)
            with (
                self.subTest(state=state_name),
                mock.patch.object(APP_REVIEW, "_attempt_descriptor",
                                  return_value=nullcontext((9, "completion.json"))),
                patch_engine("read_identity", return_value=identity),
                patch_engine("read_completion", return_value=None),
                patch_engine("attempt_publication_lock", return_value=nullcontext()),
                patch_engine("prove_group_ownership",
                             return_value=ENGINE.GroupProof("group-empty", 77)),
            ):
                self.assertEqual(APP_REVIEW.review_cancel(fake), "completion-only")
            fake._halt.assert_called_once_with(state)

    def test_cancel_refuses_unadmitted_active_state_and_malformed_record(self) -> None:
        request = {"lane": "forge-review-lane/1", "attempt": "attempt-0123456789abcdef"}
        state = {"chain_id": self.chain_id, "state": "authorized",
                 "inactive_after": "2999-01-01T00:00:00Z",
                 "review": {"iteration": 1, "request": request}}
        fake = SimpleNamespace(
            _load=lambda: state,
            _halt=mock.Mock(),
            _review_cancel_admitted=lambda current: APP_REQUEST._review_cancel_admitted(
                fake, current
            ),
            _wrong_state=lambda current, expected, verb: (_ for _ in ()).throw(
                CORE._merge_refusal(
                    adapters.CLI.V2ReasonCode.STATE_PRECONDITION,
                    f"forge: {verb} refused — merge transition is not admitted",
                    expected=expected,
                    observed=str(current["state"]),
                    chain=current,
                )
            ),
        )
        with self.assertRaises(adapters.CLI.Refusal) as caught:
            APP_REVIEW.review_cancel(fake)
        self.assertIn("merge transition is not admitted", caught.exception.message)

        state["state"] = "reviewing"
        fake._review_cancel_admitted = lambda current: None
        fake._read_cancel_records = lambda current, directory, selected: \
            APP_REQUEST._read_cancel_records(current, directory, selected)
        with (
            mock.patch.object(APP_REVIEW, "_attempt_descriptor",
                              return_value=nullcontext((9, "completion.json"))),
            patch_engine("attempt_publication_lock", return_value=nullcontext()),
            patch_engine("read_identity",
                         side_effect=ENGINE.AttemptRecordError("malformed identity")),
            self.assertRaises(adapters.CLI.Refusal) as caught,
        ):
            APP_REVIEW.review_cancel(fake)
        self.assertIn("review attempt record is invalid", caught.exception.message)
        self.assertIn("merge abort", caught.exception.remediation)

    def test_pre_and_post_event_launch_failures_are_retryable(self) -> None:
        _admission, _generation, store, engine, _outcome, _calls = self.verify_chain()

        with self.provider(), patch_engine(
            "prepare_review_launch", side_effect=RuntimeError("pre-event fixture")
        ), self.assertRaisesRegex(RuntimeError, "pre-event fixture"):
            engine.review_request()
        self.assertNotIn("request", store.load(self.chain_id).get("review", {}))

        def fail_launch(launch):
            ENGINE.close_review_launch(launch)
            raise OSError(2, "/home/agents/private-review-path")

        with self.provider(), patch_engine(
            "launch_review_wrapper", side_effect=fail_launch
        ), self.assertRaises(adapters.CLI.Refusal) as caught:
            engine.review_request()
        self.assertTrue(caught.exception.message.endswith("reviewer launch failed: errno 2"))
        failed = store.load(self.chain_id)
        first = failed["review"]["request"]
        completion_path = store.common_root / first["completion_path"]
        completion = json.loads(completion_path.read_text())
        self.assertEqual(completion["error"], "launch-failed: errno 2")
        self.assertNotIn("/home/agents", json.dumps((failed, caught.exception.observed)))

        _outcome, retried, second, completion_path = self.launch(engine, store)
        self.assertEqual(retried["review"]["iteration"], 2)
        self.assertNotEqual(first["attempt"], second["attempt"])
        self.wait_for(completion_path)
        engine.review_collect()

    def test_iteration_cap_and_superseding_transition_are_fail_closed(self) -> None:
        state = {
            "chain_id": self.chain_id,
            "state": "reviewing",
            "review": {"iteration": 8, "request": {"iteration": 8}},
        }
        APP_REVIEW._collect_iteration_admitted(state)
        state["review"]["verdict"] = {"verdict": "BLOCK"}
        with self.assertRaises(adapters.CLI.Refusal) as caught:
            APP_REVIEW._collect_iteration_admitted(state)
        self.assertEqual(caught.exception.reason_code, adapters.CLI.V2ReasonCode.ITERATION_CAP)

    def test_eighth_launch_failure_spends_final_iteration_and_leaves_abort_only(self) -> None:
        _admission, _generation, store, engine, _outcome, _calls = self.verify_chain()
        attempts: list[str] = []

        def fail_launch(launch):
            ENGINE.close_review_launch(launch)
            raise RuntimeError("fixture spawn")

        with self.provider(), patch_engine(
            "launch_review_wrapper", side_effect=fail_launch
        ):
            for iteration in range(1, 9):
                with self.assertRaises(adapters.CLI.Refusal) as caught:
                    engine.review_request()
                state = store.load(self.chain_id)
                request = state["review"]["request"]
                attempts.append(request["attempt"])
                self.assertEqual(state["review"]["iteration"], iteration)
                expected = (
                    f"forge review request --chain-id {self.chain_id}"
                    if iteration < 8
                    else f"forge merge abort --chain-id {self.chain_id} "
                    "--reason iteration-cap"
                )
                self.assertEqual(caught.exception.remediation, expected)
            before_events = store.events_path(self.chain_id).read_bytes()
            before_state = store.state_path(self.chain_id).read_bytes()
            with self.assertRaises(adapters.CLI.Refusal) as capped:
                engine.review_request()

        self.assertEqual(capped.exception.reason_code, adapters.CLI.V2ReasonCode.ITERATION_CAP)
        self.assertEqual(len(set(attempts)), 8)
        self.assertEqual(store.events_path(self.chain_id).read_bytes(), before_events)
        self.assertEqual(store.state_path(self.chain_id).read_bytes(), before_state)

    def test_collect_and_cancel_require_mandatory_review_control(self) -> None:
        _admission, _generation, _store, engine, _outcome, _calls = self.verify_chain()
        controls = CORE.MERGE_ADAPTER_CONTROLS - {"mandatory-review-final"}
        for verb in (engine.review_collect, engine.review_cancel):
            with self.subTest(verb=verb.__name__), patch_chain_core(
                "MERGE_ADAPTER_CONTROLS", controls
            ), self.assertRaisesRegex(
                adapters.CLI.FrozenError,
                "merge adapter control is unavailable: mandatory-review-final",
            ):
                verb()

    def test_cancel_runs_halt_even_past_normal_lifecycle_preflight(self) -> None:
        _admission, _generation, store, engine, _outcome, _calls = self.verify_chain()
        _outcome, _state, _request, completion = self.launch(engine, store, "hang")
        halt = self.repo / "AGENT_HALT_merge"
        halt.write_text("pause\n", encoding="utf-8")
        with self.assertRaises(adapters.CLI.Refusal) as caught:
            engine.review_cancel()
        self.assertEqual(caught.exception.reason_code, adapters.CLI.V2ReasonCode.HALT_ENGAGED)
        halt.unlink()
        engine.review_cancel()
        self.assertTrue(completion.exists())


class MergeReviewUnitTests(unittest.TestCase):
    def test_eighth_auth_failure_preserves_literal_but_leaves_abort_only(self) -> None:
        request = {"provider": "claude", "completion_path": "completion.json"}
        state = {"chain_id": "m-fixture", "state": "reviewing",
                 "review": {"iteration": 8, "request": request}}
        with self.assertRaises(adapters.CLI.Refusal) as capped:
            APP_REQUEST._review_retry_outcome(SimpleNamespace(), state, request, "not-logged-in")
        self.assertEqual(capped.exception.message, ENGINE.CLAUDE_NOT_LOGGED_IN)
        self.assertEqual(capped.exception.remediation,
                         "forge merge abort --chain-id m-fixture --reason iteration-cap")

        state["review"]["iteration"] = 7
        with self.assertRaises(adapters.CLI.Refusal) as retryable:
            APP_REQUEST._review_retry_outcome(SimpleNamespace(), state, request, "not-logged-in")
        self.assertEqual(retryable.exception.message, ENGINE.CLAUDE_NOT_LOGGED_IN)
        self.assertEqual(retryable.exception.remediation,
                         ENGINE.CLAUDE_NOT_LOGGED_IN.rsplit("; ", 1)[-1])

    def test_cancel_reproves_refreshed_live_reviewer_before_publish(self) -> None:
        initial, refreshed = ({"wrapper_pid": 7, "reviewer_pid": None},
                              {"wrapper_pid": 7, "reviewer_pid": 8})
        request = {"lane": "forge-review-lane/1", "attempt": "attempt-fixture"}
        state = {"chain_id": "m-fixture", "state": "reviewing",
                 "review": {"iteration": 1, "request": request}}
        empty, stopped = (ENGINE.GroupProof("group-empty", 7),
                          ENGINE.GroupProof("cancelled", 7))
        live = ENGINE.GroupProof("reviewer-alive", 7, (8,))

        def exercise(latest, fenced=True):
            held = [False]
            lock = mock.MagicMock()
            if fenced:
                lock.return_value.__enter__.side_effect = lambda: held.__setitem__(0, True)
                lock.return_value.__exit__.side_effect = lambda *_: held.__setitem__(0, False)
            else:
                lock.return_value = nullcontext()
            read = mock.Mock(side_effect=[(initial, None), (latest, None)])
            publish = mock.Mock(side_effect=lambda *_args: _args[-1] if held[0]
                                else self.fail("publication lock not held"))
            fake = SimpleNamespace(
                _load=lambda: state, _halt=mock.Mock(),
                _review_cancel_admitted=lambda _state: None, _read_cancel_records=read,
                _refuse_wrapper_identity_unproven=lambda *_args: None,
                _publish_cancel_completion=publish,
                _review_retry_outcome=lambda _state, _request, outcome, _note="": outcome,
            )
            fake._cancel_group_outcome = lambda current, identity, proof: \
                APP_REQUEST._cancel_group_outcome(fake, current, identity, proof)
            with mock.patch.object(APP_REVIEW, "_attempt_descriptor",
                                   return_value=nullcontext((9, "completion.json"))), \
                    patch_engine("attempt_publication_lock", lock), \
                    patch_engine("prove_group_ownership", side_effect=[empty, live]) as prove, \
                    patch_engine("terminate_owned_group", return_value=stopped) as terminate:
                result = APP_REVIEW.review_cancel(fake)
            lock.assert_called_once_with(9)
            return result, prove, terminate, publish

        result, prove, terminate, publish = exercise(refreshed)
        self.assertEqual(result, "cancelled")
        self.assertEqual(prove.call_count, 2)
        terminate.assert_called_once_with(refreshed, ENGINE.TERMINATE_GRACE_SECONDS)
        self.assertEqual(publish.call_args.args[4], "cancelled")
        with self.assertRaises(AssertionError):
            exercise(refreshed, False)

        mutated = {**refreshed, "wrapper_pid": 9}
        def immutable_refusal():
            with self.assertRaises(adapters.CLI.Refusal) as caught:
                exercise(mutated)
            return caught.exception
        self.assertIn("immutable identity changed", immutable_refusal().message)
        with mock.patch.object(APP_REVIEW, "_immutable_identity_matches", return_value=True), \
                self.assertRaises(AssertionError):
            immutable_refusal()

    def test_request_and_collect_check_halt_before_lifecycle_preflight(self) -> None:
        state = {"chain_id": "m-fixture", "state": "reviewing"}
        order: list[str] = []

        def preflight(current, verb):
            order.append(f"preflight:{verb}")
            raise CORE._merge_refusal(
                adapters.CLI.V2ReasonCode.STATE_PRECONDITION,
                "fixture lifecycle refusal",
                chain=current,
            )

        fake = SimpleNamespace(_load=lambda: state,
                               _halt=lambda _state: order.append("halt"),
                               _preflight_lifecycle=preflight)
        for verb in (APP_REVIEW.review_request, APP_REVIEW.review_collect):
            order.clear()
            with self.subTest(verb=verb.__name__), self.assertRaises(adapters.CLI.Refusal):
                verb(fake)
            self.assertEqual(order, ["halt", f"preflight:review {verb.__name__[7:]}"])

    def test_cancel_reclassifies_the_post_proof_result(self) -> None:
        request = {"lane": "forge-review-lane/1", "attempt": "attempt-fixture"}
        state = {"chain_id": "m", "review": {"iteration": 1, "request": request}}
        before = json.loads(json.dumps(state))
        identity = {"attempt": request["attempt"], "pgid": 77, "wrapper_pid": 77}
        proof = ENGINE.GroupProof("identity-unproven", 77, (88,))

        def assert_refusal(mapper=None):
            publish, retry = mock.Mock(), mock.Mock()
            fake = SimpleNamespace(
                _load=lambda: state, _halt=lambda *_: None,
                _review_cancel_admitted=lambda *_: None,
                _read_cancel_records=lambda *_: (identity, None),
                _publish_cancel_completion=publish, _review_retry_outcome=retry,
            )
            fake._refuse_wrapper_identity_unproven = lambda current, selected: \
                APP_REQUEST._refuse_wrapper_identity_unproven(fake, current, selected)
            fake._cancel_group_outcome = mapper or (lambda current, owned, selected: \
                APP_REQUEST._cancel_group_outcome(fake, current, owned, selected))
            with mock.patch.object(APP_REVIEW, "_attempt_descriptor",
                                   return_value=nullcontext((9, "completion.json"))), \
                    patch_engine("attempt_publication_lock", return_value=nullcontext()), \
                    patch_engine("prove_group_ownership", return_value=proof), \
                    patch_engine("terminate_owned_group") as signal, \
                    self.assertRaises(adapters.CLI.Refusal) as caught:
                APP_REVIEW.review_cancel(fake)
            self.assertEqual(caught.exception.message, "forge: review cancel refused — "
                             "identity-unproven; member PIDs [88]; recorded PGID 77; "
                             "nothing was signalled")
            signal.assert_not_called()
            self.assertEqual((publish.call_count, retry.call_count), (0, 0))
            self.assertEqual(state, before)

        assert_refusal()
        with self.assertRaises(AssertionError):
            assert_refusal(lambda _state, _identity, selected: ("cancelled", selected))

        observed = ENGINE.AttemptObservation("recorded-identity-unproven", members=(88,))
        pending_args = (state, {"events_path": "events.jsonl"}, observed, ())
        self.assertIn("review cancel", APP_REVIEW._collect_pending(*pending_args).remediation)
        disabled = LANE_API.CANCEL_REQUIRED_OUTCOMES - {observed.outcome}
        with mock.patch.object(LANE_API, "CANCEL_REQUIRED_OUTCOMES", disabled):
            self.assertIn("review collect", APP_REVIEW._collect_pending(*pending_args).remediation)


class MergeRouteTests(adapters.MergeAdapterFixture):
    """Shared final-route refusal on merge chains."""

    def test_merge_review_final_refuses_equal_implementer_route(self) -> None:
        _admission, _generation, store, engine, _outcome, _calls = self.verify_chain()
        launch = package_module("engine._review_launch")
        original = launch.route_config.resolve

        def same_model(root, role, head):
            return original(root, "review-final" if role == "implementer" else role, head)

        before = store.events_path(self.chain_id).read_bytes()
        with mock.patch.object(launch.route_config, "resolve", side_effect=same_model):
            with self.assertRaises(APP_REVIEW.Refusal) as caught:
                engine.review_request()
            self.assertEqual(
                str(caught.exception),
                "forge: review request refused — review-final route equals the implementer route",
            )
            self.assertEqual(caught.exception.reason_code.value, "state-precondition")
            self.assertEqual(caught.exception.schema, "forge-cli/2")
            self.assertEqual(store.events_path(self.chain_id).read_bytes(), before)
            self.assertIsNone(store.load(self.chain_id)["review"].get("request"))
            with patch_engine("require_distinct_final_route", return_value=None):
                executable = review_support.install_fake_provider(
                    self.temp_root / "route-review-bin", "claude", mode="pass",
                    log_dir=self.temp_root / "route-review-log",
                )
                with patch_engine("CLAUDE_EXECUTABLE", str(executable)):
                    engine.review_request()
        self.assertIsNotNone(store.load(self.chain_id)["review"]["request"])


if __name__ == "__main__":
    unittest.main()
