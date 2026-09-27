"""Commit-lane contracts for generalized detached review processes."""

from __future__ import annotations

import hashlib
import json
import tempfile
import types
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests._cli_loader import package_module

ENGINE = package_module("engine")
COLLECT = package_module("engine._verbs_review_collect")
REQUEST = package_module("engine._verbs_review_request")
ATTEMPT = package_module("engine._review_attempt")
LAUNCH = package_module("engine._review_launch")
FIXTURE = (
    Path(__file__).parent
    / "fixtures/review_lane/vendored_verbs_review_collect_c35af17.json"
)
CANDIDATE = "1" * 64
PACKAGE = "2" * 64
ATTEMPT_ID = "attempt-" + "a" * 16
FUTURE = "2999-01-01T00:00:00Z"
IDENTITY = {
    "schema": "forge-review-identity/1", "attempt": ATTEMPT_ID,
    "wrapper_pid": 91, "pgid": 91, "reviewer_pid": 92,
    "wrapper_birth": None, "reviewer_birth": None,
    "started_at": "2026-09-27T01:02:04Z",
}


def reviewing(request: dict[str, object] | None) -> dict[str, object]:
    return {
        "chain_id": "c-2026-09-27T010203Z-abcd",
        "state": "reviewing",
        "candidate": {
            "schema": "forge-commit-candidate/2",
            "sha256": CANDIDATE,
            "authorization_id": CANDIDATE,
        },
        "review": {"request": request, "iteration": 3},
        "inactive_after": FUTURE,
    }


def new_request(**updates: object) -> dict[str, object]:
    request: dict[str, object] = {
        "lane": "forge-review-lane/1",
        "attempt": ATTEMPT_ID,
        "candidate": CANDIDATE,
        "package": "package",
        "package_digest": PACKAGE,
        "prompt_path": "prompt",
        "prompt_digest": "3" * 64,
        "events_path": "events",
        "stderr_path": "stderr",
        "identity_path": "identity",
        "completion_path": "completion",
        "verdict_path": "verdict",
        "argv_digest": "4" * 64,
        "environment_names": [],
        "omitted_short": [],
        "provider": "codex",
        "sandbox": "read-only",
        "route": {
            "provider": "codex",
            "model": "gpt-5.6-sol",
            "effort": "high",
            "route_source": "committed-default",
            "route_sha256": "5" * 64,
        },
        "reviewer": "review-cheap",
        "requested_at": "2026-09-27T01:02:03Z",
        "iteration": 4,
    }
    request.update(updates)
    return request


def completed(request: dict[str, object], verdict: bytes, error: str | None = None):
    overrides: dict[str, object] = {}
    if error is None:
        overrides = {
            "error": None,
            "returncode": 0,
            "verdict_digest": hashlib.sha256(verdict).hexdigest(),
            "verdict_size": len(verdict),
        }
        error = "cancelled"
    return ATTEMPT.make_terminal_completion(
        request, error, identity=IDENTITY, overrides=overrides
    )


def fake_engine(state: dict[str, object], store=None, apply=None):
    store = store or _Store()
    return SimpleNamespace(
        ctx=SimpleNamespace(store=store),
        select=lambda **_kwargs: state,
        _preflight=mock.Mock(),
        _wrong_state=lambda *_args: None,
        _parse_verdict=COLLECT._parse_verdict,
        _apply_verdict=apply or (lambda *_args: "applied"),
        next_step=lambda _state: "next",
    )


def request_engine(state: dict[str, object], store=None):
    store = store or _Store()
    repo = SimpleNamespace(
        root=Path("/fixture/repo"), tree_index_drift=lambda _paths: []
    )
    return SimpleNamespace(
        ctx=SimpleNamespace(store=store, repo=repo),
        select=lambda **_kwargs: state,
        _preflight=mock.Mock(),
        _wrong_state=lambda *_args: None,
        _review_package=lambda *_args: (
            b"package", "review-cheap", ["review-coding"], {},
            b"header", b"control", b"fresh", b"diff",
        ),
        next_step=lambda _state: "next",
    )


class _Store:
    def __init__(self, common_root: Path | None = None) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []
        self.common_root = common_root or Path("/tmp/forge-review-lane-test")

    def persist(
        self, _state: dict[str, object], event: str, details: dict[str, object]
    ) -> None:
        self.events.append((event, details))

    def artifact_dir(self, chain_id: str) -> Path:
        return self.common_root / ".forge/chains" / chain_id


class CommitReviewShapeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = object.__new__(ENGINE.Engine)

    def test_next_step_is_selected_by_persisted_request_shape(self) -> None:
        cases = (
            (None, "forge review request"),
            ({"cleared": {"outcome": "cancelled"}}, "forge review request"),
            ({"lane": "forge-review-lane/1"}, "forge review collect"),
            ({"reviewer": "review-cheap", "pid": 42}, "forge review collect"),
            (
                {"reviewer": "review-final", "invocation": "legacy"},
                "forge review attach --verdict-file <path>",
            ),
            ({"lane": "future-review-lane/9"}, "forge review collect"),
        )
        for request, expected in cases:
            with self.subTest(request=request):
                self.assertEqual(
                    self.engine.next_step(reviewing(request)),
                    f"{expected} --chain-id c-2026-09-27T010203Z-abcd",
                )

    def test_attach_is_retired_when_any_launch_shape_field_is_present(self) -> None:
        for field, value in (
            ("lane", "forge-review-lane/1"), ("provider", "codex"),
            ("pid", 7), ("attempt", "attempt-a"),
        ):
            request = {"reviewer": "review-final", "invocation": "legacy", field: value}
            fake = SimpleNamespace(
                select=lambda request=request, **_kwargs: reviewing(request),
                _preflight=lambda *_args, **_kwargs: None,
                _wrong_state=lambda *_args: None,
            )
            with self.subTest(field=field), self.assertRaises(ENGINE.Refusal) as caught:
                COLLECT.review_attach(fake, "unused")
            self.assertEqual(
                caught.exception.message,
                "review attach is retired for launched requests; use review collect",
            )
            self.assertIn("review collect", caught.exception.remediation)

    def test_attach_unknown_lane_takes_newer_shape_precedence(self) -> None:
        for extra in ({}, {"provider": "codex"}):
            request = {
                "lane": "forge-review-lane/2", "reviewer": "review-final",
                "invocation": "legacy", **extra,
            }
            fake = SimpleNamespace(
                select=lambda request=request, **_kwargs: reviewing(request),
                _preflight=lambda *_args: None,
                _wrong_state=lambda *_args: None,
            )
            with self.subTest(extra=extra), self.assertRaises(ENGINE.Refusal) as caught:
                COLLECT.review_attach(fake, "unused")
            self.assertEqual(caught.exception.message, COLLECT.NEWER_REQUEST_LITERAL)

    def test_unknown_request_lane_uses_the_pinned_newer_shape_literal(self) -> None:
        request = {"lane": "forge-review-lane/2", "reviewer": "review-final"}
        state = reviewing(request)
        with self.assertRaises(ENGINE.Refusal) as caught:
            REQUEST._recover_outstanding(SimpleNamespace(), state, request)
        self.assertEqual(caught.exception.message, REQUEST.NEWER_REQUEST_LITERAL)

    def test_clearing_rewrites_owner_record_without_spending_iteration(self) -> None:
        request = {
            "candidate": CANDIDATE,
            "package_digest": PACKAGE,
            "reviewer": "review-final",
            "iteration": 4,
        }
        state = reviewing(request)
        store = _Store()
        fake = SimpleNamespace(ctx=SimpleNamespace(store=store))
        REQUEST._clear_request(fake, state, request, "wrapper-lost")
        self.assertEqual(state["review"]["iteration"], 3)
        self.assertEqual(
            state["review"]["request"]["cleared"]["outcome"], "wrapper-lost"
        )
        self.assertEqual(
            store.events,
            [("review_requested", {
                "candidate": CANDIDATE, "package_digest": PACKAGE,
                "reviewer": "review-final", "iteration": 4,
            })],
        )

class CommitReviewPathTests(unittest.TestCase):
    def test_codex_review_final_stdin_is_body_then_package_then_contract(self) -> None:
        paths = SimpleNamespace(
            role_body=b"PINNED-BODY\n", package_path=Path("/fixture/package")
        )
        route = LAUNCH.ReviewRoute(
            "review-final", "codex", "gpt-5.6-sol", "high",
            "committed-default", "a" * 64, "read-only",
        )
        package = b"EXACT-PACKAGE-BYTES\n"
        parts = (package, "review-final", [], {}, b"h", b"c", b"f", b"d")
        state = {"candidate": {"sha256": CANDIDATE}}
        with mock.patch.object(REQUEST, "_review_package_is_oversized", return_value=False):
            prompt = REQUEST._review_prompt(
                state, parts, paths.package_path, PACKAGE, route, paths
            )
        prefix = paths.role_body + b"\n" + package
        self.assertTrue(prompt.startswith(prefix))
        self.assertEqual(
            prompt.index(b"--- BEGIN CONTROLLING OUTPUT CONTRACT ---"), len(prefix) + 1
        )

    def test_request_persists_owner_before_launch(self) -> None:
        state = reviewing(None)
        state.update(paths=["src/app.py"], tier={"effective": "standard"})
        state["candidate"].update(base_commit_oid="6" * 40)
        order: list[str] = []
        store = _Store()
        original_persist = store.persist
        store.persist = lambda *args: (order.append("persist"), original_persist(*args))[1]
        fake = request_engine(state, store)
        route = LAUNCH.ReviewRoute(
            "review-cheap", "codex", "gpt-5.6-sol", "high",
            "committed-default", "5" * 64, "read-only",
        )

        def prepare_paths(_ctx, _chain, relative, *_args, **_kwargs):
            return SimpleNamespace(attempt=relative.rsplit("/", 1)[-1])

        def prepare_launch(_ctx, _state, paths, _route, _prompt):
            fields = new_request(attempt=paths.attempt)
            return SimpleNamespace(request_fields=lambda: fields)

        with (
            mock.patch.object(
                REQUEST._review_lane_api,
                "new_attempt_id",
                return_value=ATTEMPT_ID,
            ) as mint,
            mock.patch.object(REQUEST, "_mechanical_complete", return_value=True),
            mock.patch.object(
                REQUEST._review_launch, "resolve_review_route", return_value=route
            ) as resolve,
            mock.patch.object(
                REQUEST._review_launch, "prepare_review_paths", side_effect=prepare_paths
            ),
            mock.patch.object(
                REQUEST._review_launch, "prepare_review_launch", side_effect=prepare_launch
            ),
            mock.patch.object(REQUEST, "_write_artifact", return_value="package"),
            mock.patch.object(REQUEST, "_review_prompt", return_value=b"prompt"),
            mock.patch.object(REQUEST, "_review_package_is_oversized", return_value=False),
            mock.patch.object(
                REQUEST._review_launch,
                "launch_review_wrapper",
                side_effect=lambda _launch: (
                    order.append("launch") or SimpleNamespace(pid=321)
                ),
            ),
        ):
            outcome = REQUEST.review_request(fake)
        self.assertTrue(outcome.ok)
        self.assertEqual(order, ["persist", "launch"])
        self.assertEqual(store.events[0][0], "review_requested")
        self.assertEqual(state["review"]["request"]["lane"], "forge-review-lane/1")
        self.assertEqual(state["review"]["request"]["attempt"], ATTEMPT_ID)
        mint.assert_called_once_with()
        self.assertEqual(resolve.call_args.args[2], "6" * 40)

    def test_route_snapshot_divergence_refuses_before_owner_event(self) -> None:
        state = reviewing(None)
        state.update(paths=[], tier={"effective": "standard"})
        state["candidate"].update(base_commit_oid="6" * 40)
        store = _Store()
        fake = request_engine(state, store)
        literal = (
            "forge: review request refused — route diverges from run snapshot "
            "for review-cheap: model"
        )
        refusal = ENGINE.Refusal(
            ENGINE.ReasonCode.STATE_PRECONDITION, literal,
            remediation="forge commit abort", chain=state,
        )
        with (
            mock.patch.object(REQUEST, "_mechanical_complete", return_value=True),
            mock.patch.object(
                REQUEST._review_launch, "resolve_review_route", side_effect=refusal
            ),
            mock.patch.object(
                REQUEST._review_launch, "prepare_review_paths"
            ) as prepare,
            self.assertRaises(ENGINE.Refusal) as caught,
        ):
            REQUEST.review_request(fake)
        self.assertEqual(caught.exception.message, literal)
        self.assertEqual(store.events, [])
        prepare.assert_not_called()

    def test_current_collector_accepts_legacy_v1_request(self) -> None:
        verdict = (
            f"VERDICT: PASS\ncandidate: {CANDIDATE}\npackage: {PACKAGE}\n"
        ).encode()
        request = {
            "reviewer": "review-cheap", "pid": 91, "package": "package",
            "package_digest": PACKAGE, "prompt_path": "prompt",
            "prompt_digest": "3" * 64, "completion_path": "completion",
            "verdict_path": "verdict", "argv_digest": "4" * 64,
            "events_path": "events",
        }
        completion = {
            "argv_digest": "4" * 64, "completed_at": FUTURE, "error": None,
            "prompt_digest": "3" * 64, "returncode": 0, "reviewer_pid": 92,
            "schema": "forge-review-process/1", "started_at": FUTURE,
            "verdict_digest": hashlib.sha256(verdict).hexdigest(),
            "verdict_size": len(verdict), "wrapper_pid": 91,
        }
        state = reviewing(request)
        seen: dict[str, object] = {}
        fake = fake_engine(
            state, apply=lambda _state, value, ref: seen.update(value=value, ref=ref)
        )
        artifacts = {
            "package": b"package", "prompt": b"prompt",
            "completion": json.dumps(completion).encode(), "verdict": verdict,
        }
        with (
            mock.patch.object(COLLECT, "_pid_is_running", return_value=False),
            mock.patch.object(
                COLLECT, "_read_bound_artifact",
                side_effect=lambda _ctx, _state, path, *_args, **_kwargs: artifacts[path],
            ),
        ):
            COLLECT.review_collect(fake)
        self.assertEqual(seen["value"]["verdict"], "PASS")
        self.assertEqual(seen["ref"], "verdict")

    def test_new_lane_success_and_terminal_collect(self) -> None:
        verdict = (
            f"VERDICT: PASS\ncandidate: {CANDIDATE}\npackage: {PACKAGE}\n"
        ).encode()
        for terminal in (False, True):
            with self.subTest(terminal=terminal):
                request = new_request()
                state = reviewing(request)
                store = _Store()
                seen: dict[str, object] = {}
                fake = fake_engine(
                    state, store,
                    lambda _state, value, ref, seen=seen: seen.update(value=value, ref=ref),
                )
                completion = completed(
                    request, verdict, "wrapper-lost" if terminal else None
                )
                observation = ATTEMPT.AttemptObservation(
                    "completed", identity=IDENTITY, completion=completion
                )
                with (
                    mock.patch.object(ATTEMPT, "mark_stale_attempts", return_value=()),
                    mock.patch.object(
                        COLLECT, "_attempt_fd", return_value=nullcontext((9, "completion"))
                    ),
                    mock.patch.object(
                        COLLECT._review_attempt, "observe_attempt",
                        return_value=observation,
                    ),
                    mock.patch.object(
                        COLLECT, "_read_bound_artifact",
                        side_effect=lambda _ctx, _state, path, *_args, **_kwargs:
                        verdict if path == "verdict" else b"bound",
                    ),
                ):
                    outcome = COLLECT.review_collect(fake)
                if terminal:
                    self.assertTrue(outcome.ok)
                    self.assertEqual(
                        state["review"]["request"]["cleared"]["outcome"],
                        "wrapper-lost",
                    )
                    self.assertEqual(state["review"]["iteration"], 3)
                else:
                    self.assertEqual(seen["value"]["verdict"], "PASS")

    def test_completion_binding_mismatch_fails_closed(self) -> None:
        request = new_request()
        completion = completed(request, b"unused", "wrapper-lost")
        completion["provider"] = "claude"
        observation = ATTEMPT.AttemptObservation(
            "completed", identity=IDENTITY, completion=completion
        )
        fake = fake_engine(reviewing(request))
        with (
            mock.patch.object(ATTEMPT, "mark_stale_attempts", return_value=()),
            mock.patch.object(
                COLLECT, "_attempt_fd", return_value=nullcontext((9, "completion"))
            ),
            mock.patch.object(
                COLLECT._review_attempt, "observe_attempt", return_value=observation
            ),
            mock.patch.object(COLLECT, "_read_bound_artifact", return_value=b"bound"),
            self.assertRaises(ENGINE.Refusal) as caught,
        ):
            COLLECT.review_collect(fake)
        self.assertEqual(
            caught.exception.message,
            "review completion record does not bind to the current attempt",
        )
        self.assertIn("commit abort", caught.exception.remediation)

    def test_malformed_completion_record_becomes_a_forge_refusal(self) -> None:
        request = new_request()
        fake = fake_engine(reviewing(request))
        malformed = ATTEMPT.AttemptRecordError("completion.json is not valid JSON")
        with (
            mock.patch.object(ATTEMPT, "mark_stale_attempts", return_value=()),
            mock.patch.object(
                COLLECT, "_attempt_fd", return_value=nullcontext((9, "completion"))
            ),
            mock.patch.object(
                COLLECT._review_attempt, "observe_attempt", side_effect=malformed
            ),
            mock.patch.object(COLLECT, "_read_bound_artifact", return_value=b"bound"),
            self.assertRaises(ENGINE.Refusal) as caught,
        ):
            COLLECT.review_collect(fake)
        self.assertEqual(caught.exception.reason_code, ENGINE.ReasonCode.EVIDENCE_INCOMPLETE)
        self.assertEqual(caught.exception.message, "review attempt record is invalid")
        self.assertEqual(caught.exception.observed, "completion.json is not valid JSON")
        self.assertIn("commit abort", caught.exception.remediation)

    def test_legacy_review_final_attach_remains_admitted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = {
                "reviewer": "review-final", "invocation": "legacy command",
                "package": ".forge/chains/c-2026-09-27T010203Z-abcd/"
                "review/iteration-04/attempt-old/package.txt",
                "package_digest": PACKAGE,
            }
            state, seen = reviewing(request), {}
            store = _Store(root)
            fake = fake_engine(
                state, store,
                lambda _state, value, ref: seen.update(value=value, ref=ref),
            )
            verdict = root / "verdict.txt"
            verdict.write_text(
                f"VERDICT: PASS\ncandidate: {CANDIDATE}\npackage: {PACKAGE}\n",
                encoding="utf-8",
            )
            with (
                mock.patch.object(COLLECT, "_read_bound_artifact", return_value=b"package"),
                mock.patch.object(COLLECT, "_write_artifact", return_value="legacy-verdict"),
            ):
                COLLECT.review_attach(fake, str(verdict))
            self.assertEqual(seen["value"]["verdict"], "PASS")
            self.assertEqual(seen["ref"], "legacy-verdict")

class CommitReviewCompatibilityTests(unittest.TestCase):
    def test_vendored_collector_is_byte_exact_c35af17_source(self) -> None:
        source = json.loads(FIXTURE.read_text(encoding="utf-8"))["source"]
        self.assertEqual(
            hashlib.sha256(source.encode()).hexdigest(),
            "d73cc8852a3b613ff788bd01539b09e3b461e883a88fd97915cd357e0d8296b3",
        )
        compile(source, str(FIXTURE), "exec")

    def test_pre_e_collector_refuses_a_v2_completion(self) -> None:
        source = json.loads(FIXTURE.read_text(encoding="utf-8"))["source"]
        legacy_subject = types.ModuleType("vendored_review_collect_c35af17")
        exec(compile(source, str(FIXTURE), "exec"), legacy_subject.__dict__)
        request = {
            "reviewer": "review-cheap", "pid": 991991,
            "package": "package", "package_digest": PACKAGE,
            "prompt_path": "prompt", "prompt_digest": "3" * 64,
            "completion_path": "completion", "verdict_path": "verdict",
            "argv_digest": "4" * 64, "events_path": "events",
        }
        completion = json.dumps({"schema": "forge-review-process/2"}).encode()
        fake = SimpleNamespace(
            ctx=SimpleNamespace(), select=lambda **_kwargs: reviewing(request),
            _preflight=lambda *_args: None, _wrong_state=lambda *_args: None,
        )

        def read(_ctx, _state, path, *_args, **_kwargs):
            return completion if path == "completion" else b""

        with (
            mock.patch.object(legacy_subject, "_read_bound_artifact", side_effect=read),
            mock.patch.object(legacy_subject, "_pid_is_running", return_value=False),
            self.assertRaises(ENGINE.Refusal) as caught,
        ):
            legacy_subject.review_collect(fake)
        self.assertEqual(
            caught.exception.message,
            "review-cheap completion record does not bind to the launched reviewer",
        )


if __name__ == "__main__":
    unittest.main()
