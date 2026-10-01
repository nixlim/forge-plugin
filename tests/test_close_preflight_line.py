"""Focused contracts for the S8 journal-only close-preflight line."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests import test_close_preflight as preflight_fixture
from tests import test_review_lane_commit as review_fixture
from tests import test_revision9_cli_surfaces as cli_fixture
from tests._cli_loader import package_module
from tests._revision9_coord_constants import key

from codex_orchestrator import close_law, close_preflight, journal

ATTEMPT = package_module("engine._review_attempt")
COLLECT = package_module("engine._verbs_review_collect")
DECISION = package_module("engine._verbs_decision")
STATUS = package_module("engine._verbs_status")

CHAIN_ID = "c-2026-09-30T120000Z-abcd"
RUN_ID = "run-20260930-close-line"
NO_ISSUE = "no issue found; terminal chain guard not run"


def bound_state(request: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "chain_id": CHAIN_ID,
        "state": "reviewing",
        "inactive_after": "2999-01-01T00:00:00Z",
        "repo_head": "a" * 40,
        "candidate": {
            "schema": "forge-commit-candidate/2",
            "sha256": review_fixture.CANDIDATE,
            "authorization_id": review_fixture.CANDIDATE,
        },
        "tier": {"effective": "standard", "control": False},
        "review": {
            "request": request,
            "iteration": 3,
            "verdict": None,
            "operator_cosign_required": False,
        },
        "approval": {},
        "authorization": {},
        "run_binding": {
            "run_id": RUN_ID,
            "task_id": "task-01",
            "repository": "/fixture/repo",
            "policy_digest": "b" * 64,
        },
    }


def journal_only_line(chain_id: str | None) -> str:
    projection = f", projecting {chain_id}" if chain_id is not None else ""
    return f"close preflight (journal-only{projection}): {NO_ISSUE}"


def summary_double(
    _run_dir: Path,
    projecting_chain: str | None,
    _chain_state: dict[str, object],
) -> str:
    return journal_only_line(projecting_chain)


class JournalOnlySummaryTests(unittest.TestCase):
    @staticmethod
    def _summary(
        issues: list[str], *, chain_id: str | None = None
    ) -> str:
        records = [{"type": "run_started", "_line": 1}]
        state = bound_state()
        with (
            mock.patch.object(journal, "read_journal", return_value=(records, [])),
            mock.patch.object(
                close_law, "project_close", return_value={"issues": issues}
            ),
            mock.patch.object(
                close_law, "projected_chain_records", return_value=records
            ),
            mock.patch.object(
                close_preflight, "_bound_chain_record", return_value=True
            ),
            mock.patch.object(
                journal.route_provenance, "enforce_run_close", return_value=None
            ),
        ):
            return close_preflight.summary_line(
                Path("/fixture/run"), chain_id, state
            )

    def test_summary_line_has_all_pinned_forms(self) -> None:
        self.assertEqual(
            self._summary([]),
            f"close preflight (journal-only): {NO_ISSUE}",
        )
        self.assertEqual(
            self._summary(["first issue", "second issue"], chain_id=CHAIN_ID),
            "close preflight (journal-only, projecting "
            f"{CHAIN_ID}): 2 issue(s), first: first issue",
        )

    def test_summary_first_issue_escapes_controls_and_caps_length(self) -> None:
        issue = "before\nmid\r\x1b\x85\u2028\u2029" + ("x" * 70_000)

        def assert_safe() -> None:
            line = self._summary([issue])
            rendered = line.partition("first: ")[2]
            for character in ("\n", "\r", "\x1b", "\x85", "\u2028", "\u2029"):
                self.assertNotIn(character, rendered)
            for escaped in (r"\n", r"\r", r"\x1b", r"\x85", r"\u2028", r"\u2029"):
                self.assertIn(escaped, rendered)
            self.assertEqual(
                len(rendered.encode("utf-8")),
                close_preflight._SUMMARY_ISSUE_LIMIT_BYTES,
            )
            self.assertTrue(rendered.endswith("..."))

        assert_safe()
        with mock.patch.object(
            close_preflight, "_summary_issue", side_effect=lambda value: value
        ), self.assertRaises(AssertionError):
            assert_safe()

    def test_summary_line_maps_runtime_and_os_errors_to_unavailable(self) -> None:
        for raised in (RuntimeError("fixture failure"), OSError("fixture read")):
            with self.subTest(error=type(raised).__name__), mock.patch.object(
                journal, "read_journal", side_effect=raised
            ):
                line = close_preflight.summary_line(
                    Path("/fixture/run"), CHAIN_ID, bound_state()
                )
            self.assertEqual(
                line,
                "close preflight (journal-only, projecting "
                f"{CHAIN_ID}): unavailable",
            )
            self.assertNotIn(journal.BATCH_DIVERGED, line)

    def test_closed_summary_uses_the_full_preflight_issue(self) -> None:
        records = [
            {"type": "run_started", "_line": 1},
            {"type": "run_closed", "_line": 2},
        ]
        with (
            mock.patch.object(journal, "read_journal", return_value=(records, [])),
            mock.patch.object(close_law, "project_close") as project,
            mock.patch.object(journal.route_provenance, "enforce_run_close") as route,
        ):
            line = close_preflight.summary_line(
                Path("/fixture/run"), None, bound_state()
            )

        self.assertEqual(
            line,
            "close preflight (journal-only): 1 issue(s), first: "
            "forge: close preflight — run is not open",
        )
        project.assert_not_called()
        route.assert_not_called()


class EngineSurfaceTests(unittest.TestCase):
    @staticmethod
    def _status(state: dict[str, object]):
        store = SimpleNamespace(
            common_root=Path("/fixture/repo"),
            tombstone=lambda _chain: None,
        )
        repository = SimpleNamespace(
            root=Path("/fixture/repo"),
            head=lambda: state["repo_head"],
            candidate_hash=lambda: state["candidate"].get("sha256"),
        )
        fake = SimpleNamespace(
            ctx=SimpleNamespace(
                options=SimpleNamespace(chain_id=state["chain_id"]),
                store=store,
                repo=repository,
            ),
            select=lambda **_kwargs: state,
            next_step=lambda _state: "forge review request",
        )
        return STATUS.status(fake)

    @staticmethod
    def _verify(state: dict[str, object]):
        state["state"] = "verifying"
        store = SimpleNamespace(
            common_root=Path("/fixture/repo"),
            persist=lambda *_args, **_kwargs: None,
        )
        fake = SimpleNamespace(
            ctx=SimpleNamespace(
                options=SimpleNamespace(verbose=False),
                store=store,
                repo=SimpleNamespace(root=Path("/fixture/repo")),
            ),
            select=lambda **_kwargs: state,
            _preflight=lambda *_args: None,
            _wrong_state=lambda *_args: None,
            gate_run=lambda *_args: None,
            next_step=lambda _state: "forge review request",
        )
        def transition(target: dict[str, object], name: str) -> None:
            target["state"] = name

        with (
            mock.patch.object(
                DECISION.runtime, "_fast_mechanical_skips", return_value=[]
            ),
            mock.patch.object(
                DECISION.chain_core, "_policy_for_state", return_value=object()
            ),
            mock.patch.object(DECISION, "_next_incomplete", return_value=None),
            mock.patch.object(DECISION, "_transition_state", side_effect=transition),
        ):
            return DECISION.verify(fake)

    @staticmethod
    def _review_fake(state: dict[str, object]):
        def apply(
            target: dict[str, object], _verdict: dict[str, object], ref: str
        ):
            return COLLECT._success(
                target,
                "review PASS recorded",
                "forge commit finalize",
                evidence_refs=[ref],
            )

        fake = review_fixture.fake_engine(state, apply=apply)
        fake.ctx.repo = SimpleNamespace(root=Path("/fixture/repo"))
        return fake

    def test_run_bound_status_and_verify_append_the_line(self) -> None:
        with mock.patch.object(
            close_preflight, "summary_line", side_effect=summary_double
        ) as summary:
            status = self._status(bound_state())
            verified = self._verify(bound_state())

        self.assertEqual(
            status.message,
            f"chain {CHAIN_ID} is reviewing; {journal_only_line(None)}",
        )
        self.assertEqual(
            verified.message,
            "all required mechanical verification steps are complete; "
            f"{journal_only_line(CHAIN_ID)}",
        )
        self.assertEqual(status.exit_code, 0)
        self.assertEqual(verified.exit_code, 0)
        self.assertEqual(
            [call.args[1] for call in summary.call_args_list], [None, CHAIN_ID]
        )

    def test_unbound_status_and_verify_messages_are_byte_identical(self) -> None:
        status_state = bound_state()
        verify_state = bound_state()
        status_state["run_binding"] = None
        verify_state["run_binding"] = None
        with mock.patch.object(close_preflight, "summary_line") as summary:
            status = self._status(status_state)
            verified = self._verify(verify_state)

        self.assertEqual(status.message, f"chain {CHAIN_ID} is reviewing")
        self.assertEqual(
            verified.message,
            "all required mechanical verification steps are complete",
        )
        summary.assert_not_called()

    def test_internal_summary_errors_leave_success_and_report_unavailable(self) -> None:
        for raised in (RuntimeError("fixture failure"), OSError("fixture read")):
            state = bound_state()
            records = [{"type": "run_started", "_line": 1}]
            with (
                self.subTest(error=type(raised).__name__),
                mock.patch.object(
                    journal, "read_journal", return_value=(records, [])
                ),
                mock.patch.object(close_law, "project_close", side_effect=raised),
            ):
                outcome = self._status(state)
            self.assertEqual(outcome.exit_code, 0)
            self.assertTrue(outcome.message.endswith("): unavailable"))
            self.assertNotIn(journal.BATCH_DIVERGED, outcome.message)

    def test_closed_status_uses_run_not_open_and_other_status_return_is_unchanged(
        self,
    ) -> None:
        closed = bound_state()
        closed["state"] = "closed"
        records = [
            {"type": "run_started", "_line": 1},
            {"type": "run_closed", "_line": 2},
        ]
        with mock.patch.object(
            journal, "read_journal", return_value=(records, [])
        ):
            outcome = self._status(closed)
        self.assertEqual(
            outcome.message,
            f"chain {CHAIN_ID} is closed; close preflight (journal-only): "
            "1 issue(s), first: forge: close preflight — run is not open",
        )
        self.assertEqual(outcome.exit_code, 0)

        inactive = bound_state()
        inactive["inactive_after"] = "2000-01-01T00:00:00Z"
        with mock.patch.object(close_preflight, "summary_line") as summary:
            outcome = self._status(inactive)
        self.assertEqual(
            outcome.message,
            "chain is inactive after 24 hours without an event; only status or "
            "abort is admitted",
        )
        summary.assert_not_called()

    @staticmethod
    def _pass_verdict() -> bytes:
        return (
            f"VERDICT: PASS\ncandidate: {review_fixture.CANDIDATE}\n"
            f"package: {review_fixture.PACKAGE}\n"
        ).encode()

    def _legacy_collect_pass(self, *, bound: bool = True):
        verdict = self._pass_verdict()
        request = {
            "reviewer": "review-cheap",
            "pid": 91,
            "package": "package",
            "package_digest": review_fixture.PACKAGE,
            "prompt_path": "prompt",
            "prompt_digest": "3" * 64,
            "completion_path": "completion",
            "verdict_path": "verdict",
            "argv_digest": "4" * 64,
            "events_path": "events",
        }
        completion = {
            "argv_digest": "4" * 64,
            "completed_at": review_fixture.FUTURE,
            "error": None,
            "prompt_digest": "3" * 64,
            "returncode": 0,
            "reviewer_pid": 92,
            "schema": "forge-review-process/1",
            "started_at": review_fixture.FUTURE,
            "verdict_digest": hashlib.sha256(verdict).hexdigest(),
            "verdict_size": len(verdict),
            "wrapper_pid": 91,
        }
        artifacts = {
            "package": b"package",
            "prompt": b"prompt",
            "completion": json.dumps(completion).encode(),
            "verdict": verdict,
        }
        with (
            mock.patch.object(COLLECT, "_pid_is_running", return_value=False),
            mock.patch.object(
                COLLECT,
                "_read_bound_artifact",
                side_effect=lambda _ctx, _state, path, *_args, **_kwargs: artifacts[
                    path
                ],
            ),
        ):
            state = bound_state(request)
            if not bound:
                state["run_binding"] = None
            return COLLECT.review_collect(self._review_fake(state))

    def _new_lane_collect_pass(self, *, bound: bool = True):
        verdict = self._pass_verdict()
        lane_request = review_fixture.new_request()
        completion = review_fixture.completed(lane_request, verdict)
        observation = ATTEMPT.AttemptObservation(
            "completed", identity=review_fixture.IDENTITY, completion=completion
        )
        with (
            mock.patch.object(ATTEMPT, "mark_stale_attempts", return_value=()),
            mock.patch.object(
                COLLECT, "_attempt_fd", return_value=nullcontext((9, "completion"))
            ),
            mock.patch.object(ATTEMPT, "observe_attempt", return_value=observation),
            mock.patch.object(
                COLLECT,
                "_read_bound_artifact",
                side_effect=lambda _ctx, _state, path, *_args, **_kwargs: (
                    verdict if path == "verdict" else b"bound"
                ),
            ),
        ):
            state = bound_state(lane_request)
            if not bound:
                state["run_binding"] = None
            return COLLECT.review_collect(self._review_fake(state))

    def test_legacy_collect_and_new_lane_pass_append_the_line(self) -> None:
        with (
            mock.patch.object(
                close_preflight, "summary_line", side_effect=summary_double
            ),
            mock.patch.object(
                COLLECT,
                "_review_collect_close_preflight_line",
                wraps=COLLECT._review_collect_close_preflight_line,
            ) as decorate,
        ):
            legacy = self._legacy_collect_pass()
            new_lane = self._new_lane_collect_pass()

        expected = f"review PASS recorded; {journal_only_line(CHAIN_ID)}"
        self.assertEqual(legacy.message, expected)
        self.assertEqual(new_lane.message, expected)
        self.assertEqual(decorate.call_count, 2)

    def test_unbound_review_collect_pass_messages_are_byte_identical(self) -> None:
        with mock.patch.object(close_preflight, "summary_line") as summary:
            legacy = self._legacy_collect_pass(bound=False)
            new_lane = self._new_lane_collect_pass(bound=False)

        self.assertEqual(legacy.message, "review PASS recorded")
        self.assertEqual(new_lane.message, "review PASS recorded")
        summary.assert_not_called()

    def test_synthetic_block_and_legacy_attach_are_byte_identical(self) -> None:
        request = review_fixture.new_request()
        block_state = bound_state(request)
        block_fake = review_fixture.fake_engine(
            block_state,
            apply=lambda state, _verdict, ref: COLLECT._success(
                state,
                "review BLOCK recorded at iteration 4",
                "forge commit restage",
                evidence_refs=[ref],
            ),
        )
        block_fake.ctx.repo = SimpleNamespace(root=Path("/fixture/repo"))
        with (
            mock.patch.object(
                COLLECT,
                "_review_collect_close_preflight_line",
                wraps=COLLECT._review_collect_close_preflight_line,
            ) as decorate,
            mock.patch.object(
                COLLECT, "_write_artifact", return_value="synthetic-verdict"
            ),
        ):
            blocked = COLLECT._synthetic_block(
                block_fake, block_state, request, "provider exit 9"
            )
        self.assertEqual(blocked.message, "review BLOCK recorded at iteration 4")
        decorate.assert_not_called()

        decorated_block = COLLECT._success(
            block_state,
            "review BLOCK recorded at iteration 4",
            "forge commit restage",
            evidence_refs=["fixture-verdict"],
        )
        with mock.patch.object(close_preflight, "summary_line") as summary:
            unchanged_block = COLLECT._review_collect_close_preflight_line(
                block_fake, block_state, decorated_block
            )
        self.assertIs(unchanged_block, decorated_block)
        summary.assert_not_called()

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            attach_request = {
                "reviewer": "review-final",
                "invocation": "legacy command",
                "package": (
                    f".forge/chains/{CHAIN_ID}/review/iteration-04/"
                    "attempt-old/package.txt"
                ),
                "package_digest": review_fixture.PACKAGE,
            }
            attach_state = bound_state(attach_request)
            store = review_fixture._Store(root)
            attach_fake = review_fixture.fake_engine(
                attach_state,
                store,
                lambda state, _value, ref: COLLECT._success(
                    state,
                    "review PASS recorded",
                    "forge commit finalize",
                    evidence_refs=[ref],
                ),
            )
            attach_fake.ctx.repo = SimpleNamespace(root=root)
            verdict_path = root / "verdict.txt"
            verdict_path.write_text(
                f"VERDICT: PASS\ncandidate: {review_fixture.CANDIDATE}\n"
                f"package: {review_fixture.PACKAGE}\n",
                encoding="utf-8",
            )
            with (
                mock.patch.object(close_preflight, "summary_line") as summary,
                mock.patch.object(
                    COLLECT, "_read_bound_artifact", return_value=b"package"
                ),
                mock.patch.object(
                    COLLECT, "_write_artifact", return_value="legacy-verdict"
                ),
            ):
                attached = COLLECT.review_attach(attach_fake, str(verdict_path))
        self.assertEqual(attached.message, "review PASS recorded")
        summary.assert_not_called()

    def _surface_messages(self) -> dict[str, str]:
        return {
            "status": self._status(bound_state()).message,
            "verify": self._verify(bound_state()).message,
            "legacy": self._legacy_collect_pass().message,
            "new-lane": self._new_lane_collect_pass().message,
        }

    def _assert_surface_lines(self, messages: dict[str, str]) -> None:
        self.assertIn("; close preflight (journal-only): ", messages["status"])
        for name in ("verify", "legacy", "new-lane"):
            self.assertIn(
                f"; close preflight (journal-only, projecting {CHAIN_ID}): ",
                messages[name],
            )

    def test_close_preflight_line_disable_restores_all_four_messages(self) -> None:
        records = [{"type": "run_started", "_line": 1}]

        with (
            mock.patch.object(journal, "read_journal", return_value=(records, [])),
            mock.patch.object(
                close_law, "project_close", return_value={"issues": []}
            ),
            mock.patch.object(
                journal.route_provenance, "enforce_run_close", return_value=None
            ),
            mock.patch.object(
                close_preflight, "_bound_chain_record", return_value=True
            ),
            mock.patch.object(
                close_law, "projected_chain_records", return_value=records
            ),
        ):
            self._assert_surface_lines(self._surface_messages())
            disabled = close_preflight.CLOSE_PREFLIGHT_CONTROLS - {
                "close-preflight-line"
            }
            with mock.patch.object(
                close_preflight, "CLOSE_PREFLIGHT_CONTROLS", disabled
            ), self.assertRaises(AssertionError):
                self._assert_surface_lines(self._surface_messages())
            with mock.patch.object(
                close_preflight, "CLOSE_PREFLIGHT_CONTROLS", disabled
            ):
                restored = self._surface_messages()
        self.assertEqual(
            restored,
            {
                "status": f"chain {CHAIN_ID} is reviewing",
                "verify": "all required mechanical verification steps are complete",
                "legacy": "review PASS recorded",
                "new-lane": "review PASS recorded",
            },
        )


class RealFixtureSummaryTests(unittest.TestCase):
    @staticmethod
    def _fixture() -> preflight_fixture.ClosePreflightTests:
        fixture = preflight_fixture.ClosePreflightTests(
            "test_named_chain_projects_landing_and_task_completion"
        )
        fixture.setUp()
        return fixture

    def _managed_fixture(self) -> preflight_fixture.ClosePreflightTests:
        fixture = self._fixture()
        self.addCleanup(fixture.doCleanups)
        return fixture

    @staticmethod
    def _active_run(
        fixture: preflight_fixture.ClosePreflightTests, name: str
    ) -> tuple[Path, str, Path]:
        repo, _head = fixture._repository(name)
        run_id = f"run-20260930-line-{name}"
        fixture.open_run(repo, run_id)
        fixture.start_task(repo, run_id)
        return repo, run_id, fixture.run_dir(repo, run_id)

    def test_real_journals_pin_every_complete_line_form(self) -> None:
        fixture = self._managed_fixture()
        with fixture.api_environment():
            _repo, _run_id, closable_dir = fixture._terminal_run("line-closable")
            _repo, _run_id, active_dir = self._active_run(fixture, "line-active")
            closed_repo, closed_run, closed_dir = fixture._terminal_run("line-closed")
            accepted, refusal = fixture._close(closed_repo, closed_run)
            self.assertTrue(accepted, refusal)
            projected_repo, projected_run, projected_chain = fixture._projection_run(
                "line-projected"
            )
            projected_dir = fixture.run_dir(projected_repo, projected_run)
            projected_state = json.loads(
                (
                    projected_repo
                    / ".forge"
                    / "chains"
                    / f"{projected_chain}.json"
                ).read_text(encoding="utf-8")
            )
            _repo, _run_id, unbound_dir = fixture._terminal_run("line-unbound")

        self.assertEqual(
            close_preflight.summary_line(closable_dir, None, None),
            "close preflight (journal-only): " + NO_ISSUE,
        )
        self.assertEqual(
            close_preflight.summary_line(active_dir, None, None),
            "close preflight (journal-only): 1 issue(s), first: task task-01 "
            "is not terminal; latest status is 'active'",
        )
        self.assertEqual(
            close_preflight.summary_line(closed_dir, None, None),
            "close preflight (journal-only): 1 issue(s), first: "
            "forge: close preflight — run is not open",
        )
        self.assertEqual(
            close_preflight.summary_line(
                projected_dir, projected_chain, projected_state
            ),
            journal_only_line(projected_chain),
        )
        self.assertEqual(
            close_preflight.summary_line(unbound_dir, CHAIN_ID, {}),
            f"close preflight (journal-only, projecting {CHAIN_ID}): unavailable",
        )

    def test_unavailable_and_false_no_issue_mutations_fail_exact_lines(self) -> None:
        fixture = self._managed_fixture()
        with fixture.api_environment():
            _repo, _run_id, closable_dir = fixture._terminal_run("mutation-available")
            _repo, _run_id, active_dir = self._active_run(fixture, "mutation-issue")

        def assert_closable() -> None:
            self.assertEqual(
                close_preflight.summary_line(closable_dir, None, None),
                "close preflight (journal-only): " + NO_ISSUE,
            )

        def assert_active_issue() -> None:
            self.assertEqual(
                close_preflight.summary_line(active_dir, None, None),
                "close preflight (journal-only): 1 issue(s), first: task task-01 "
                "is not terminal; latest status is 'active'",
            )

        assert_closable()
        with mock.patch.object(
            close_preflight,
            "_summary_records",
            side_effect=OSError("fixture unavailable mutation"),
        ), self.assertRaises(AssertionError):
            assert_closable()
        assert_active_issue()
        with mock.patch.object(
            close_law, "project_close", return_value={"issues": []}
        ), self.assertRaises(AssertionError):
            assert_active_issue()

    def test_fr247_leg_and_in_memory_approval_are_load_bearing(self) -> None:
        fixture = self._managed_fixture()
        with fixture.api_environment():
            _repo, _run_id, provenance_dir = fixture._terminal_run(
                "line-provenance", provenance=False
            )
            projected_repo, projected_run, projected_chain = fixture._projection_run(
                "line-approval"
            )
        expected_provenance = (
            "close preflight (journal-only): 1 issue(s), first: forge: run-close "
            "refused — task task-01 recorded complete without completion provenance "
            "(FR-247)"
        )

        def assert_provenance() -> None:
            self.assertEqual(
                close_preflight.summary_line(provenance_dir, None, None),
                expected_provenance,
            )

        assert_provenance()
        with mock.patch.object(
            journal.route_provenance, "enforce_run_close", return_value=None
        ), self.assertRaises(AssertionError):
            assert_provenance()

        projected_dir = fixture.run_dir(projected_repo, projected_run)
        state_path = (
            projected_repo / ".forge" / "chains" / f"{projected_chain}.json"
        )
        chain_state = json.loads(state_path.read_text(encoding="utf-8"))
        chain_state["tier"]["control"] = True
        original = close_law.projected_chain_records

        def assert_approval_projection(projector) -> None:
            captured: list[dict[str, object]] = []

            def project(records, chain_id, state):
                self.assertEqual(state, chain_state)
                result = projector(records, chain_id, state)
                captured.extend(result)
                return result

            with mock.patch.object(
                close_law, "projected_chain_records", side_effect=project
            ):
                self.assertEqual(
                    close_preflight.summary_line(
                        projected_dir, projected_chain, chain_state
                    ),
                    journal_only_line(projected_chain),
                )
            self.assertTrue(
                any(
                    record.get("type") == "decision"
                    and record.get("outcome") == "chain-approval"
                    for record in captured
                )
            )

        assert_approval_projection(original)

        def ignore_state(records, chain_id, _state):
            return original(records, chain_id, {})

        with self.assertRaises(AssertionError):
            assert_approval_projection(ignore_state)


class RealCliLineTests(unittest.TestCase):
    def _fixture(self) -> cli_fixture.Revision9BoundCLIIntegrationTests:
        fixture = cli_fixture.Revision9BoundCLIIntegrationTests(
            "test_bound_multicell_stack_journals_one_completed_batch"
        )
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        return fixture

    def _start_bound(
        self,
        fixture: cli_fixture.Revision9BoundCLIIntegrationTests,
        run_id: str,
        path: str,
        content: str,
    ) -> str:
        scope = ("docs/**",) if path.startswith("docs/") else ("src/**",)
        if path.startswith("scripts/"):
            scope = ("scripts/**",)
        fixture.open_run_and_task(run_id, scope=scope, files=(path,))
        fixture.change(path, content)
        exit_code, started = fixture.invoke_cli(
            "--run-id",
            run_id,
            "commit",
            "start",
            "--paths",
            path,
            "--task",
            "task-01",
        )
        self.assertEqual(exit_code, 0, started)
        return str(started["chain_id"])

    def _finish_task(
        self,
        fixture: cli_fixture.Revision9BoundCLIIntegrationTests,
        run_id: str,
    ) -> None:
        _batch, cli_builders, _journal = cli_fixture.CLI._coordination_modules()
        with fixture.cli_process_context():
            cli_builders.decision_add(
                fixture.repo,
                run_id,
                idempotency_key=key(f"{run_id}-provenance"),
                task="task-01",
                resolution="orchestrator-owned: close-preflight line fixture",
                finding=None,
                outcome=None,
                risk=None,
                basis=["real CLI line fixture"],
                binding_chain=None,
                binding_id=None,
            )
            cli_builders.task_finish(
                fixture.repo,
                run_id,
                idempotency_key=key(f"{run_id}-finish"),
                task="task-01",
                status="complete",
            )

    def _close_run(
        self,
        fixture: cli_fixture.Revision9BoundCLIIntegrationTests,
        run_id: str,
    ) -> None:
        _batch, cli_builders, _journal = cli_fixture.CLI._coordination_modules()
        with fixture.cli_process_context():
            cli_builders.run_close(
                fixture.repo,
                run_id,
                idempotency_key=key(f"{run_id}-close"),
                judgment="passed",
                summary="Close-preflight line fixture passed",
                risks=[],
                follow_ups=[],
            )

    def test_real_cli_status_and_verify_pin_issue_and_closable_suffixes(self) -> None:
        active = self._fixture()
        active_chain = self._start_bound(
            active,
            "run-20260930-line-cli-active",
            "src/app.py",
            "VALUE = 2\n",
        )
        exit_code, status = active.invoke_cli(
            "--chain-id", active_chain, "status"
        )
        self.assertEqual(exit_code, 0, status)
        self.assertEqual(
            status["message"],
            f"chain {active_chain} is verifying; close preflight (journal-only): "
            "1 issue(s), first: task task-01 is not terminal; latest status is "
            "'active'",
        )

        projected = self._fixture()
        projected_chain = self._start_bound(
            projected,
            "run-20260930-line-cli-projected",
            "docs/guide.md",
            "# Close-preflight line fixture\n",
        )
        exit_code, verified = projected.invoke_cli(
            "--chain-id", projected_chain, "verify"
        )
        self.assertEqual(exit_code, 0, verified)
        self.assertEqual(
            verified["message"],
            "all required mechanical verification steps are complete; "
            "close preflight (journal-only, projecting "
            f"{projected_chain}): 1 issue(s), first: task 'task-01' has "
            "inconsistent bound candidate across gate and landing records",
        )

        closable = self._fixture()
        open_run = "run-20260930-line-cli-closable"
        closable_chain = self._start_bound(
            closable,
            open_run,
            "scripts/tool.py",
            "CONTROL = 2\n",
        )
        exit_code, verified = closable.invoke_cli(
            "--chain-id", closable_chain, "verify"
        )
        self.assertEqual(exit_code, 0, verified)
        exit_code, requested = closable.invoke_cli(
            "--chain-id", closable_chain, "review", "request"
        )
        self.assertEqual(exit_code, 0, requested)
        request = closable.state(closable_chain)["review"]["request"]
        closable.wait_for_review_completion(request)
        exit_code, collected = closable.invoke_cli(
            "--chain-id", closable_chain, "review", "collect"
        )
        self.assertEqual(exit_code, 0, collected)
        candidate = str(closable.state(closable_chain)["candidate"]["sha256"])
        exit_code, approved = closable.invoke_cli(
            "--chain-id",
            closable_chain,
            "commit",
            "approve",
            "--candidate",
            candidate,
        )
        self.assertEqual(exit_code, 0, approved)
        exit_code, finalized = closable.invoke_cli(
            "--chain-id",
            closable_chain,
            "commit",
            "finalize",
            "--message",
            "Land the closable journal-line fixture",
        )
        self.assertEqual(exit_code, 0, finalized)
        self._finish_task(closable, open_run)
        preview = close_preflight.preflight(closable.repo, open_run)
        self.assertTrue(preview["would_close_passed"], preview)
        self.assertEqual(preview["issues"], [], preview)
        exit_code, closed_status = closable.invoke_cli(
            "--chain-id", closable_chain, "status"
        )
        self.assertEqual(exit_code, 0, closed_status)
        self.assertEqual(
            closed_status["message"],
            f"chain {closable_chain} is closed; close preflight (journal-only): "
            + NO_ISSUE,
        )

        self._close_run(closable, open_run)
        exit_code, run_closed_status = closable.invoke_cli(
            "--chain-id", closable_chain, "status"
        )
        self.assertEqual(exit_code, 0, run_closed_status)
        self.assertEqual(
            run_closed_status["message"],
            f"chain {closable_chain} is closed; close preflight (journal-only): "
            "1 issue(s), first: forge: close preflight — run is not open",
        )

    def test_real_cli_control_collect_uses_in_memory_approval_state(self) -> None:
        original = close_law.projected_chain_records

        def assert_collect(projector) -> None:
            fixture = self._fixture()
            run_id = f"run-20260930-line-cli-approval-{len(self._cleanups)}"
            chain_id = self._start_bound(
                fixture,
                run_id,
                "scripts/tool.py",
                "CONTROL = 2\n",
            )
            exit_code, verified = fixture.invoke_cli(
                "--chain-id", chain_id, "verify"
            )
            self.assertEqual(exit_code, 0, verified)
            self.assertTrue(fixture.state(chain_id)["tier"]["control"])
            exit_code, requested = fixture.invoke_cli(
                "--chain-id", chain_id, "review", "request"
            )
            self.assertEqual(exit_code, 0, requested)
            request = fixture.state(chain_id)["review"]["request"]
            fixture.wait_for_review_completion(request)
            captured: list[dict[str, object]] = []

            def project(records, projected_chain, state):
                result = projector(records, projected_chain, state)
                captured.extend(result)
                return result

            with mock.patch.object(
                close_law, "projected_chain_records", side_effect=project
            ):
                exit_code, collected = fixture.invoke_cli(
                    "--chain-id", chain_id, "review", "collect"
                )
            self.assertEqual(exit_code, 0, collected)
            self.assertEqual(collected["state"], "awaiting_approval")
            self.assertEqual(
                collected["message"],
                f"review PASS recorded; {journal_only_line(chain_id)}",
            )
            self.assertTrue(
                any(
                    record.get("type") == "decision"
                    and record.get("outcome") == "chain-approval"
                    for record in captured
                )
            )

        assert_collect(original)

        def ignore_state(records, chain_id, _state):
            return original(records, chain_id, {})

        with self.assertRaises(AssertionError):
            assert_collect(ignore_state)

    def test_real_cli_projecting_surface_without_bound_verification_is_unavailable(
        self,
    ) -> None:
        fixture = self._fixture()
        chain_id = self._start_bound(
            fixture,
            "run-20260930-line-cli-no-bound-verification",
            "src/app.py",
            "VALUE = 2\n",
        )
        for gate_id in (
            "gate-1",
            "stack:python",
            "assertion-sensor",
            "invariant:1",
            "secret-scan",
        ):
            exit_code, skipped = fixture.invoke_cli(
                "--chain-id",
                chain_id,
                "commit",
                "skip",
                gate_id,
                "--reason",
                "construct a no-verification projection fixture",
            )
            self.assertEqual(exit_code, 0, skipped)
        exit_code, verified = fixture.invoke_cli(
            "--chain-id", chain_id, "verify"
        )

        self.assertEqual(exit_code, 0, verified)
        self.assertEqual(
            verified["message"],
            "all required mechanical verification steps are complete; close "
            "preflight (journal-only, projecting "
            f"{chain_id}): unavailable",
        )


if __name__ == "__main__":
    unittest.main()
