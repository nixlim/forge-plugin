"""Commit-lane cancellation and terminal serialization contracts."""

from __future__ import annotations

import unittest
from contextlib import contextmanager, nullcontext
from types import SimpleNamespace
from unittest import mock

from tests._cli_loader import package_module

ENGINE = package_module("engine")
ATTEMPT = package_module("engine._review_attempt")
CANCEL = package_module("engine._verbs_review_cancel")
COLLECT = package_module("engine._verbs_review_collect")
LANE_API = package_module("engine._review_lane_api")
PARSER = package_module("engine._parser")
REQUEST = package_module("engine._verbs_review_request")
STATE = package_module("engine._state")
ATTEMPT_ID = "attempt-" + "a" * 16
FUTURE = "2999-01-01T00:00:00Z"


def reviewing(request: dict[str, object]) -> dict[str, object]:
    return {
        "chain_id": "c-2026-09-27T010203Z-abcd",
        "state": "reviewing", "candidate": {"sha256": "1" * 64},
        "review": {"request": request, "iteration": 3}, "inactive_after": FUTURE,
    }


def new_request() -> dict[str, object]:
    return {
        "lane": "forge-review-lane/1",
        "attempt": ATTEMPT_ID,
        "candidate": "1" * 64,
        "package": "package",
        "package_digest": "2" * 64,
        "prompt_path": "prompt",
        "prompt_digest": "3" * 64,
        "events_path": "events",
        "stderr_path": "stderr",
        "identity_path": "identity",
        "completion_path": "completion",
        "verdict_path": "verdict",
        "argv_digest": "4" * 64,
        "environment_names": [], "omitted_short": [],
        "provider": "codex", "sandbox": "read-only",
        "route": {
            "provider": "codex",
            "route_source": "committed-default",
            "route_sha256": "5" * 64,
        },
        "reviewer": "review-cheap", "requested_at": "2026-09-27T01:02:03Z",
        "iteration": 4,
    }


def live_identity(reviewer_pid: int | None = None) -> dict[str, object]:
    reviewer_birth = None if reviewer_pid is None else {
        "kind": "linux-proc", "boot_id": "boot", "starttime": 2,
    }
    return {
        "schema": "forge-review-identity/1", "attempt": ATTEMPT_ID,
        "wrapper_pid": 77, "pgid": 77,
        "wrapper_birth": {"kind": "linux-proc", "boot_id": "boot", "starttime": 1},
        "reviewer_pid": reviewer_pid, "reviewer_birth": reviewer_birth,
        "started_at": FUTURE,
    }


class _Store:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def persist(self, _state, event, details) -> None:
        self.events.append((event, details))


def fake_engine(state: dict[str, object], store: _Store):
    return SimpleNamespace(
        ctx=SimpleNamespace(store=store), select=lambda **_kwargs: state,
        _preflight=mock.Mock(), _wrong_state=lambda *_args: None,
        next_step=lambda _state: "next",
    )


def attempt_fd(module):
    return mock.patch.object(
        module, "_attempt_fd", return_value=nullcontext((9, "completion")))


class CommitReviewCancelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.enterContext(
            mock.patch.object(
                ATTEMPT, "attempt_publication_lock", return_value=nullcontext(True)
            )
        )

    def test_parser_engine_and_terminal_touch_register_review_cancel(self) -> None:
        parsed = PARSER.build_parser().parse_args(["review", "cancel"])
        self.assertEqual((parsed.command, parsed.review_command), ("review", "cancel"))
        self.assertTrue(callable(ENGINE.Engine.review_cancel))
        self.assertIn("review cancel", STATE.TERMINAL_TOUCH_VERBS)

    def test_cancel_reviewing_and_completion_only_admissions(self) -> None:
        cases = (
            ("reviewing", FUTURE, 3, False),
            ("revising", "2000-01-01T00:00:00Z", 3, True),
            ("revising", FUTURE, 8, True),
            ("aborted", FUTURE, 3, True),
        )
        identity = live_identity()
        for state_name, inactive, iteration, completion_only in cases:
            with self.subTest(state=state_name, inactive=inactive, iteration=iteration):
                request, store = new_request(), _Store()
                state = reviewing(request)
                state.update(state=state_name, inactive_after=inactive)
                state["review"]["iteration"] = iteration
                fake = fake_engine(state, store)
                published: list[dict[str, object]] = []
                proof = ATTEMPT.GroupProof("group-empty", 77, (88,))
                with (
                    attempt_fd(CANCEL),
                    mock.patch.object(ATTEMPT, "read_identity", return_value=identity),
                    mock.patch.object(ATTEMPT, "read_completion", return_value=None),
                    mock.patch.object(ATTEMPT, "prove_group_ownership", return_value=proof),
                    mock.patch.object(ATTEMPT, "terminate_owned_group") as kill,
                    mock.patch.object(
                        ATTEMPT, "publish_terminal_completion",
                        side_effect=lambda _fd, record, sink=published:
                        sink.append(record) is None,
                    ),
                ):
                    outcome = CANCEL.review_cancel(fake)
                kill.assert_not_called()
                fake._preflight.assert_called_once_with(
                    state, "review cancel", allow_head_moved=True, check_candidate=False
                )
                self.assertEqual(published[0]["error"], "wrapper-lost")
                self.assertEqual(bool(store.events), not completion_only)
                self.assertEqual("cleared" in state["review"]["request"], not completion_only)
                self.assertIn("wrapper-lost", outcome.message)

    def test_cancel_refuses_an_active_nonreviewing_chain(self) -> None:
        request, store = new_request(), _Store()
        state = reviewing(request)
        fake = fake_engine(state, store)
        attempt = mock.patch.object(CANCEL, "_attempt_fd")

        def refusal() -> ENGINE.Refusal:
            with self.assertRaises(ENGINE.Refusal) as caught:
                CANCEL.review_cancel(fake)
            return caught.exception

        with attempt as opened:
            state["state"] = "revising"
            self.assertIn(
                "reviewing, inactive, iteration-capped, or terminal", refusal().message
            )
            request["lane"], state["state"] = "forge-review-lane/2", "aborted"
            self.assertEqual(refusal().message, CANCEL.NEWER_REQUEST_LITERAL)
            self.assertIn("commit abort", refusal().remediation)
            admitted = CANCEL.SUPPORTED_CANCEL_LANES | {"forge-review-lane/2"}
            with mock.patch.object(CANCEL, "SUPPORTED_CANCEL_LANES", admitted):
                self.assertNotEqual(refusal().message, CANCEL.NEWER_REQUEST_LITERAL)
        self.assertEqual((opened.called, store.events), (False, []))

    def test_cancel_finishes_an_existing_abandonment_claim(self) -> None:
        request, store = new_request(), _Store()
        state = reviewing(request)
        fake = fake_engine(state, store)
        identity = live_identity()
        identity.update(wrapper_pid=None, pgid=None, wrapper_birth=None)
        completion = ATTEMPT.make_terminal_completion(request, "abandoned")
        with (
            attempt_fd(CANCEL),
            mock.patch.object(ATTEMPT, "read_identity", return_value=identity),
            mock.patch.object(ATTEMPT, "read_completion", return_value=None),
            mock.patch.object(
                ATTEMPT, "claim_abandoned", return_value=(True, completion)
            ) as claim,
            mock.patch.object(ATTEMPT, "prove_group_ownership") as prove,
            mock.patch.object(ATTEMPT, "publish_terminal_completion") as publish,
        ):
            outcome = CANCEL.review_cancel(fake)
        claim.assert_called_once_with(9, request)
        prove.assert_not_called()
        publish.assert_not_called()
        self.assertIn("review attempt abandoned", outcome.message)
        self.assertEqual(state["review"]["request"]["cleared"]["outcome"], "abandoned")

    def test_cancel_refuses_identity_unproven_without_writes(self) -> None:
        request, store = new_request(), _Store()
        state, identity = reviewing(request), live_identity(88)
        proof = ATTEMPT.GroupProof("identity-unproven", 77, (88,))

        def assert_refusal() -> None:
            publish = mock.Mock()
            with (
                attempt_fd(CANCEL),
                mock.patch.object(ATTEMPT, "read_identity", return_value=identity),
                mock.patch.object(ATTEMPT, "read_completion", return_value=None),
                mock.patch.object(ATTEMPT, "prove_group_ownership", return_value=proof),
                mock.patch.object(ATTEMPT, "terminate_owned_group") as kill,
                mock.patch.object(ATTEMPT, "publish_terminal_completion", publish),
                self.assertRaises(ENGINE.Refusal) as caught,
            ):
                CANCEL.review_cancel(fake_engine(state, store))
            kill.assert_not_called()
            publish.assert_not_called()
            self.assertEqual(caught.exception.message, "forge: review cancel refused — "
                             "identity-unproven; member PIDs [88]; recorded PGID 77; "
                             "nothing was signalled")
            self.assertEqual((state, store.events), (reviewing(new_request()), []))

        assert_refusal()
        def legacy(*_args):
            return "cancelled", proof
        with mock.patch.object(CANCEL, "_cancel_group", side_effect=legacy), \
                self.assertRaises(AssertionError):
            assert_refusal()

    def test_cancel_refreshes_identity_before_completion_publication(self) -> None:
        initial, refreshed = live_identity(), live_identity(88)
        empty = ATTEMPT.GroupProof("group-empty", 77)
        alive = ATTEMPT.GroupProof("reviewer-alive", 77, (88,))
        cancelled = ATTEMPT.GroupProof("cancelled", 77)
        patch = mock.patch.object
        held = False

        @contextmanager
        def locked(_fd):
            nonlocal held
            held = True
            try:
                yield True
            finally:
                held = False

        def guarded(values):
            values = iter(values)

            def call(*_args):
                self.assertTrue(held)
                return next(values)

            return call

        def execute(lock):
            req, store = new_request(), _Store()
            state = reviewing(req)
            with (
                attempt_fd(CANCEL),
                patch(ATTEMPT, "attempt_publication_lock", side_effect=lock),
                patch(ATTEMPT, "read_identity", side_effect=guarded((initial, refreshed))),
                patch(ATTEMPT, "read_completion", side_effect=guarded((None,))),
                patch(ATTEMPT, "prove_group_ownership", side_effect=guarded((empty, alive))),
                patch(ATTEMPT, "terminate_owned_group", side_effect=guarded((cancelled,))) as kill,
                patch(
                    ATTEMPT, "publish_terminal_completion", side_effect=guarded((True,))
                ) as write,
            ):
                result = CANCEL.review_cancel(fake_engine(state, store))
            return result, state, write, kill

        outcome, state, write, kill = execute(locked)
        self.assertFalse(held)
        self.assertIn("attempt cancelled", outcome.message)
        self.assertEqual(write.call_args.args[1]["error"], "cancelled")
        kill.assert_called_once_with(refreshed, CANCEL._review_launch.TERMINATE_GRACE_SECONDS)
        self.assertEqual(state["review"]["request"]["cleared"]["outcome"], "cancelled")
        with self.assertRaises(AssertionError):
            execute(lambda _fd: nullcontext(True))

    def test_cancel_reclassifies_the_post_proof_result(self) -> None:
        identity = live_identity()
        request, store, publish = new_request(), _Store(), mock.Mock(return_value=True)
        with (
            attempt_fd(CANCEL),
            mock.patch.object(ATTEMPT, "read_identity", return_value=identity),
            mock.patch.object(ATTEMPT, "read_completion", return_value=None),
            mock.patch.object(ATTEMPT, "prove_group_ownership", return_value=
                              ATTEMPT.GroupProof("wrapper-alive", 77, (77,))),
            mock.patch.object(ATTEMPT, "terminate_owned_group", return_value=
                              ATTEMPT.GroupProof("identity-mismatch", 77)),
            mock.patch.object(ATTEMPT, "publish_terminal_completion", publish),
        ):
            CANCEL.review_cancel(fake_engine(reviewing(request), store))
        self.assertEqual(publish.call_args.args[1]["error"], "wrapper-lost")

        proof = ATTEMPT.GroupProof("identity-unproven", 77, (88,))
        with mock.patch.object(ATTEMPT, "prove_group_ownership", return_value=
                               ATTEMPT.GroupProof("wrapper-alive", 77, (77,))), \
                mock.patch.object(ATTEMPT, "terminate_owned_group", return_value=proof), \
                self.assertRaises(ENGINE.Refusal) as caught:
            CANCEL._cancel_group(reviewing(new_request()), identity)
        self.assertEqual(caught.exception.message, "forge: review cancel refused — "
                         "identity-unproven; member PIDs [88]; recorded PGID 77; "
                         "nothing was signalled")


class CommitReviewRecoveryAuditTests(unittest.TestCase):
    def test_request_recovery_sends_malformed_completion_to_commit_abort(self) -> None:
        request = new_request()
        state = reviewing(request)
        malformed = ATTEMPT.AttemptRecordError("completion.json is not valid JSON")
        with (
            attempt_fd(REQUEST),
            mock.patch.object(ATTEMPT, "observe_attempt", side_effect=malformed),
            self.assertRaises(ENGINE.Refusal) as caught,
        ):
            REQUEST._recover_outstanding(SimpleNamespace(), state, request)
        self.assertIn("commit abort", caught.exception.remediation)
        self.assertNotIn("cleared", state["review"]["request"])

    def test_request_recovery_sends_misbound_completion_to_commit_abort(self) -> None:
        request = new_request()
        state = reviewing(request)
        identity = live_identity()
        completion = ATTEMPT.make_terminal_completion(
            request, "wrapper-lost", identity=identity
        )
        completion["provider"] = "claude"
        observed = ATTEMPT.AttemptObservation(
            "completed", identity=identity, completion=completion
        )
        with (
            attempt_fd(REQUEST),
            mock.patch.object(ATTEMPT, "observe_attempt", return_value=observed),
            self.assertRaises(ENGINE.Refusal) as caught,
        ):
            REQUEST._recover_outstanding(SimpleNamespace(), state, request)
        self.assertIn("commit abort", caught.exception.remediation)
        self.assertNotIn("cleared", state["review"]["request"])

    def test_request_recovery_clears_published_nonverdict_terminals(self) -> None:
        complete = ATTEMPT.make_terminal_completion
        observation = ATTEMPT.AttemptObservation
        patch = mock.patch.object
        recover_request = REQUEST._recover_outstanding

        def recover(error: str) -> tuple[bool, dict[str, object]]:
            request, store = new_request(), _Store()
            state, identity = reviewing(request), live_identity()
            if error == "abandoned":
                identity.update(wrapper_pid=None, pgid=None, wrapper_birth=None)
            completion = complete(request, error, identity=identity)
            observed = observation("completed", identity=identity, completion=completion)
            with (
                patch(REQUEST, "_attempt_fd", return_value=nullcontext((9, "completion"))),
                patch(ATTEMPT, "observe_attempt", return_value=observed),
            ):
                result = recover_request(fake_engine(state, store), state, request)
            return result, state

        for error in ("abandoned", "wrapper-lost"):
            result, state = recover(error)
            self.assertTrue(result)
            self.assertEqual(state["review"]["request"]["cleared"]["outcome"], error)
        with mock.patch.object(REQUEST, "RECOVERABLE_COMPLETION_ERRORS", frozenset()):
            for error in ("abandoned", "wrapper-lost"):
                result, state = recover(error)
                self.assertFalse(result)
                self.assertNotIn("cleared", state["review"]["request"])

    def test_collect_pending_refusal_preserves_stale_evidence(self) -> None:
        request, store = new_request(), _Store()
        fake = fake_engine(reviewing(request), store)
        observed = ATTEMPT.AttemptObservation("running", reason="wrapper alive")
        with (
            mock.patch.object(
                ATTEMPT, "mark_stale_attempts", return_value=("stale.json",)
            ),
            attempt_fd(COLLECT),
            mock.patch.object(ATTEMPT, "observe_attempt", return_value=observed),
            mock.patch.object(COLLECT, "_read_bound_artifact", return_value=b"bound"),
            self.assertRaises(ENGINE.Refusal) as caught,
        ):
            COLLECT.review_collect(fake)
        self.assertIn("stale.json", caught.exception.evidence_refs)

    def test_collect_unproven_recorded_identity_requires_cancel(self) -> None:
        request, store = new_request(), _Store()
        fake = fake_engine(reviewing(request), store)
        observed = ATTEMPT.AttemptObservation(
            "recorded-identity-unproven", members=(88,), reason="birth identity unreadable"
        )

        def refusal() -> ENGINE.Refusal:
            with (
                mock.patch.object(ATTEMPT, "mark_stale_attempts", return_value=()),
                attempt_fd(COLLECT),
                mock.patch.object(ATTEMPT, "observe_attempt", return_value=observed),
                mock.patch.object(COLLECT, "_read_bound_artifact", return_value=b"bound"),
                self.assertRaises(ENGINE.Refusal) as caught,
            ):
                COLLECT.review_collect(fake)
            return caught.exception

        self.assertIn("review cancel", refusal().remediation)
        disabled = LANE_API.CANCEL_REQUIRED_OUTCOMES - {"recorded-identity-unproven"}
        with mock.patch.object(LANE_API, "CANCEL_REQUIRED_OUTCOMES", disabled):
            self.assertIn("review collect", refusal().remediation)

    def test_collect_auth_refusal_preserves_stale_evidence(self) -> None:
        request, store = new_request(), _Store()
        state = reviewing(request)
        fake = fake_engine(state, store)
        identity = live_identity(88)
        completion = ATTEMPT.make_terminal_completion(
            request, "not-logged-in", identity=identity
        )
        observed = ATTEMPT.AttemptObservation(
            "completed", identity=identity, completion=completion
        )
        with (
            mock.patch.object(
                ATTEMPT, "mark_stale_attempts", return_value=("stale.json",)
            ),
            attempt_fd(COLLECT),
            mock.patch.object(ATTEMPT, "observe_attempt", return_value=observed),
            mock.patch.object(COLLECT, "_read_bound_artifact", return_value=b"bound"),
            self.assertRaises(ENGINE.Refusal) as caught,
        ):
            COLLECT.review_collect(fake)
        self.assertIn("stale.json", caught.exception.evidence_refs)
        self.assertEqual(state["review"]["request"]["cleared"]["outcome"], "not-logged-in")

    def test_collect_timeout_uses_the_exact_timeout_error(self) -> None:
        request, store = new_request(), _Store()
        state = reviewing(request)
        fake = fake_engine(state, store)
        identity = live_identity(88)
        completion = ATTEMPT.make_terminal_completion(
            request, "wrapper-lost", identity=identity,
            overrides={"error": None, "timed_out": True},
        )
        observed = ATTEMPT.AttemptObservation(
            "completed", identity=identity, completion=completion
        )
        sentinel = object()
        with (
            mock.patch.object(ATTEMPT, "mark_stale_attempts", return_value=()),
            attempt_fd(COLLECT),
            mock.patch.object(ATTEMPT, "observe_attempt", return_value=observed),
            mock.patch.object(COLLECT, "_read_bound_artifact", return_value=b"bound"),
            mock.patch.object(
                COLLECT, "_synthetic_block", return_value=sentinel
            ) as synthetic,
        ):
            outcome = COLLECT.review_collect(fake)
        self.assertIs(outcome, sentinel)
        self.assertEqual(synthetic.call_args.args[-1], "timeout")

    def test_synthetic_block_retry_reuses_identical_artifact(self) -> None:
        request, store = new_request(), _Store()
        state, sentinel = reviewing(request), object()
        fake = fake_engine(state, store)
        fake._apply_verdict = mock.Mock(return_value=sentinel)
        with (
            mock.patch.object(
                COLLECT, "_write_artifact", side_effect=FileExistsError
            ) as write,
            mock.patch.object(COLLECT, "_read_bound_artifact", return_value=b"") as read,
        ):
            outcome = COLLECT._synthetic_block(fake, state, request, "timeout")
        self.assertIs(outcome, sentinel)
        content = write.call_args.args[3]
        self.assertEqual(read.call_args.args[3], COLLECT.sha256_bytes(content))
        self.assertEqual(read.call_args.args[2], fake._apply_verdict.call_args.args[2])

    def test_claude_init_mismatch_has_the_exact_synthetic_block_finding(self) -> None:
        request, store = new_request(), _Store()
        state, sentinel = reviewing(request), object()
        fake = fake_engine(state, store)
        fake._apply_verdict = mock.Mock(return_value=sentinel)
        with mock.patch.object(
            COLLECT, "_write_artifact", return_value="synthetic-verdict"
        ) as write:
            outcome = COLLECT._synthetic_block(
                fake, state, request, "claude init mismatch"
            )
        expected = (
            "no reviewer verdict — claude init mismatch; completion "
            f"{request['completion_path']}"
        )
        self.assertIs(outcome, sentinel)
        verdict = fake._apply_verdict.call_args.args[1]
        self.assertEqual(
            verdict["findings"], [{"severity": "MAJOR", "text": expected}]
        )
        self.assertIn(
            f"finding: MAJOR {expected}\n".encode(), write.call_args.args[3]
        )


if __name__ == "__main__":
    unittest.main()
