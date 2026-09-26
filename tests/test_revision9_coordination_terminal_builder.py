from __future__ import annotations

import copy
import json
import os
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from tests._revision9_coord_constants import key
from tests._revision9_coord_support import Revision9BuilderBatchSupport

from codex_orchestrator import builders, journal


class Revision9TerminalBuilderTests(Revision9BuilderBatchSupport, unittest.TestCase):

    def _append_orchestrator_provenance(self, repo: Path, run_id: str) -> None:
        builders.decision_add(
            repo, run_id, idempotency_key=key(f"{run_id}-orchestrator-provenance"),
            task="task-01", resolution="orchestrator-owned: terminal-control fixture", finding=None,
            outcome=None, risk=None, basis=["terminal-control test setup"], binding_chain=None, binding_id=None)

    def _append_test_landing(
        self, repo: Path, run_id: str, chain_id: str
    ) -> dict[str, object]:
        return self._append_test_decision(repo, run_id, chain_id, "chain-landing")

    def _append_test_decision(
        self, repo: Path, run_id: str, chain_id: str, outcome: str, *, seed: str = ""
    ) -> dict[str, object]:
        preimage = {
            "schema": journal.BINDING_SCHEMA,
            "source_record": {
                "chain_id": chain_id,
                "event_digest": key(
                    ("terminal-event" if outcome == "chain-landing" else f"terminal-event-{outcome}")
                    + seed
                ),
            },
            "candidate": {
                "kind": "staged-diff-sha256",
                "value": key("terminal-candidate"),
            },
            "review": None,
        }
        binding = {
            **preimage,
            "binding_id": journal._sha256(journal._canonical_json_bytes(preimage)),
        }
        with mock.patch.object(builders, "resolve_binding", return_value=binding):
            appended = builders.decision_add(
                repo,
                run_id,
                idempotency_key=key(f"{run_id}-{chain_id}-terminal-{outcome}{seed}"),
                task="task-01",
                resolution=(
                    "The bound candidate landed"
                    if outcome == "chain-landing"
                    else "The bound chain was aborted"
                ),
                finding=None,
                outcome=outcome,
                risk=None,
                basis=[],
                binding_chain=chain_id,
                binding_id=str(binding["binding_id"]),
            )
        self.assertFalse(appended.repeated)
        self.assertEqual(len(appended.records), 1)
        recorded_binding = appended.records[0].get("binding")
        self.assertEqual(recorded_binding, binding)
        assert isinstance(recorded_binding, dict)
        return recorded_binding

    def test_terminal_builder_guards_pending_outbox_and_missing_landing(self) -> None:
        with self.api_environment():
            repo, run_id, run_binding = self._terminal_control_repo("terminal-pending")
            self._write_bound_chain_state(
                repo,
                run_id,
                run_binding=run_binding,
                outbox={"pending": True},
            )
            with self.assertRaisesRegex(
                journal.CoordinationRefusal, builders.JOURNAL_OUTBOX_PENDING
            ):
                builders.task_finish(
                    repo,
                    run_id,
                    idempotency_key=key("terminal-pending"),
                    task="task-01",
                    status="complete",
                )
            self.assertFalse(
                (self.run_dir(repo, run_id) / journal.BATCH_INTENT_NAME).exists()
            )

            repo, run_id, run_binding = self._terminal_control_repo("terminal-landing")
            self._write_bound_chain_state(
                repo, run_id, run_binding=run_binding, outbox=None
            )
            with self.assertRaisesRegex(
                journal.CoordinationRefusal, builders.TERMINAL_CHAIN_INVALID
            ):
                builders.task_finish(
                    repo,
                    run_id,
                    idempotency_key=key("terminal-landing"),
                    task="task-01",
                    status="complete",
                )

    def _abort_bound_chain_fixture(
        self, repo: Path, chain_id: str, state_path: Path, *, outbox: object = None
    ) -> None:
        """Append an authenticated chain_aborted event to a fixture chain."""
        events_path = state_path.parent / f"{chain_id}.events.jsonl"
        events = [
            json.loads(line)
            for line in events_path.read_text(encoding="utf-8").splitlines()
            if line
        ]
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state = copy.deepcopy(state)
        state["last_event_at"] = "2026-08-28T12:05:00Z"
        state["state"] = "aborted"
        state["commit_result"] = {
            "aborted_at": state["last_event_at"],
            "reason": "candidate superseded",
        }
        state["journal_outbox"] = outbox
        unsigned = {
            "sequence": len(events) + 1,
            "prev_digest": events[-1]["digest"],
            "payload": {
                "at": state["last_event_at"],
                "details": {"reason": "candidate superseded"},
                "event": "chain_aborted",
                "state": copy.deepcopy(state),
            },
        }
        event = {
            **unsigned,
            "digest": journal._sha256(journal._canonical_json_bytes(unsigned)),
        }
        events.append(event)
        events_path.write_bytes(
            b"".join(journal._canonical_json_bytes(item) + b"\n" for item in events)
        )
        state_path.write_bytes(journal._canonical_json_bytes(state) + b"\n")

    def test_terminal_builder_accepts_authenticated_abort_disposition(self) -> None:
        """Bead forge-plugin-437: an explicit abort is a terminal disposition."""
        with self.api_environment():
            repo, run_id, run_binding = self._terminal_control_repo("abort-accepted")
            chain_id, state_path = self._write_bound_chain_state(
                repo, run_id, run_binding=run_binding, outbox=None)
            self._abort_bound_chain_fixture(repo, chain_id, state_path)
            self._append_orchestrator_provenance(repo, run_id)
            with mock.patch.object(
                builders,
                "TERMINAL_CHAIN_CONTROLS",
                builders.TERMINAL_CHAIN_CONTROLS - {"abort-disposition"},
            ), self.assertRaisesRegex(
                journal.CoordinationRefusal, builders.TERMINAL_CHAIN_INVALID
            ):
                builders.task_finish(
                    repo, run_id, idempotency_key=key("abort-disabled"),
                    task="task-01", status="complete",
                )
            outcome = builders.task_finish(
                repo, run_id, idempotency_key=key("abort-accepted"),
                task="task-01", status="complete",
            )
            self.assertEqual(outcome.records[0]["status"], "complete")

            # A landing decision citing the aborted chain contradicts its state.
            repo, run_id, run_binding = self._terminal_control_repo("abort-landing")
            chain_id, state_path = self._write_bound_chain_state(
                repo, run_id, run_binding=run_binding, outbox=None
            )
            self._abort_bound_chain_fixture(repo, chain_id, state_path)
            self._append_test_landing(repo, run_id, chain_id)
            with self.assertRaisesRegex(
                journal.CoordinationRefusal, builders.TERMINAL_CHAIN_INVALID
            ):
                builders.task_finish(
                    repo, run_id, idempotency_key=key("abort-landing"),
                    task="task-01", status="complete",
                )

            # An aborted chain whose outbox is still pending is not terminal.
            repo, run_id, run_binding = self._terminal_control_repo("abort-outbox")
            chain_id, state_path = self._write_bound_chain_state(
                repo, run_id, run_binding=run_binding, outbox={"pending": True}
            )
            self._abort_bound_chain_fixture(
                repo, chain_id, state_path, outbox={"pending": True}
            )
            # A consequential chain_aborted appended over an unreceipted outbox
            # is a replay violation, so replay refuses it before the outbox or
            # abort-disposition controls are reached.
            with self.assertRaisesRegex(
                journal.CoordinationRefusal, builders.TERMINAL_CHAIN_INVALID
            ):
                builders.task_finish(
                    repo, run_id, idempotency_key=key("abort-outbox"),
                    task="task-01", status="complete",
                )

            # A landing decision citing the aborted chain is contradictory even
            # when the journal also holds the abort decision.
            repo, run_id, run_binding = self._terminal_control_repo("abort-both")
            chain_id, state_path = self._write_bound_chain_state(
                repo, run_id, run_binding=run_binding, outbox=None
            )
            self._abort_bound_chain_fixture(repo, chain_id, state_path)
            self._append_test_decision(repo, run_id, chain_id, "chain-abort")
            self._append_test_landing(repo, run_id, chain_id)
            with self.assertRaisesRegex(
                journal.CoordinationRefusal, builders.TERMINAL_CHAIN_INVALID
            ):
                builders.task_finish(
                    repo, run_id, idempotency_key=key("abort-both"),
                    task="task-01", status="complete",
                )

            # Two abort decisions for one aborted chain are refused: exactly
            # one carried decision is the only accepted shape.
            repo, run_id, run_binding = self._terminal_control_repo("abort-twice")
            chain_id, state_path = self._write_bound_chain_state(
                repo, run_id, run_binding=run_binding, outbox=None
            )
            self._abort_bound_chain_fixture(repo, chain_id, state_path)
            self._append_test_decision(repo, run_id, chain_id, "chain-abort")
            self._append_test_decision(
                repo, run_id, chain_id, "chain-abort", seed="second"
            )
            with self.assertRaisesRegex(
                journal.CoordinationRefusal, builders.TERMINAL_CHAIN_INVALID
            ):
                builders.task_finish(
                    repo, run_id, idempotency_key=key("abort-twice"),
                    task="task-01", status="complete",
                )

            # An abort decision citing a chain that is not a terminal abort is
            # contradictory too.
            repo, run_id, run_binding = self._terminal_control_repo("abort-live")
            chain_id, state_path = self._write_bound_chain_state(
                repo, run_id, run_binding=run_binding, outbox=None
            )
            self._append_test_decision(repo, run_id, chain_id, "chain-abort")
            with self.assertRaisesRegex(
                journal.CoordinationRefusal, builders.TERMINAL_CHAIN_INVALID
            ):
                builders.task_finish(
                    repo, run_id, idempotency_key=key("abort-live"),
                    task="task-01", status="complete",
                )

    def test_terminal_abort_disposition_fails_closed_on_shape(self) -> None:
        base = {"state": "aborted", "journal_outbox": None}
        self.assertFalse(builders._terminal_abort_disposition(dict(base)))
        self.assertFalse(builders._terminal_abort_disposition({**base, "kind": "other"}))
        self.assertFalse(
            builders._terminal_abort_disposition({**base, "kind": "commit", "commit_result": {}})
        )
        self.assertFalse(
            builders._terminal_abort_disposition(
                {**base, "kind": "commit", "commit_result": {"aborted_at": "2026-08-28T12:05:00Z", "commit_sha": "1" * 40}}
            )
        )
        self.assertTrue(
            builders._terminal_abort_disposition(
                {**base, "kind": "commit", "commit_result": {"aborted_at": "2026-08-28T12:05:00Z", "reason": ""}}
            )
        )
        self.assertTrue(builders._terminal_abort_disposition({**base, "kind": "merge"}))
        self.assertFalse(
            builders._terminal_abort_disposition({**base, "kind": "merge", "journal_outbox": {"pending": True}})
        )

    def _self_event_fixture(self) -> tuple[dict, dict, dict]:
        """A minimal aborted commit state and its abort_disposition_recorded event."""
        sha = key("self-event-candidate")
        prior = {
            "schema": "forge-chain/1",
            "chain_id": "c-2026-09-05T000000Z-abcd",
            "kind": "commit",
            "state": "aborted",
            "created_at": "2026-09-05T00:00:00Z",
            "last_event_at": "2026-09-05T00:01:00Z",
            "inactive_after": "2026-09-06T00:01:00Z",
            "candidate": {"sha256": sha, "computed_at": "2026-09-05T00:00:30Z"},
            "commit_result": {"aborted_at": "2026-09-05T00:01:00Z", "reason": "legacy"},
            "run_binding": {
                "run_id": "run-20260905-self-event",
                "task_id": "task-01",
                "repository": "/repo",
                "policy_digest": key("policy"),
            },
            "journal_outbox": None,
        }
        current = copy.deepcopy(prior)
        current["last_event_at"] = "2026-09-05T00:02:00Z"
        current["inactive_after"] = "2026-09-06T00:02:00Z"
        event = {
            "sequence": 9,
            "prev_digest": key("prev"),
            "payload": {
                "at": "2026-09-05T00:02:00Z",
                "details": {"reason": "legacy"},
                "event": "abort_disposition_recorded",
                "state": copy.deepcopy(current),
            },
        }
        return prior, current, event

    def test_abort_disposition_self_event_admission_controls_are_load_bearing(self) -> None:
        """Bead forge-plugin-rtj: the self-event replays only from aborted, unchanged."""
        prior, current, event = self._self_event_fixture()
        self.assertTrue(builders._commit_transition_valid(event, prior, current))
        # Enum control: an unknown event name is refused.
        with mock.patch.object(
            builders, "_COMMIT_EVENT_NAMES",
            builders._COMMIT_EVENT_NAMES - {"abort_disposition_recorded"},
        ):
            self.assertFalse(builders._commit_transition_valid(event, prior, current))
        # Transition control: the self-event is admitted only from aborted.
        live_prior = {**copy.deepcopy(prior), "state": "authorized"}
        live_current = {**copy.deepcopy(current), "state": "authorized"}
        live_event = copy.deepcopy(event); live_event["payload"]["state"] = copy.deepcopy(live_current)
        self.assertFalse(builders._commit_transition_valid(live_event, live_prior, live_current))
        with mock.patch.dict(
            builders._COMMIT_STATE_TRANSITIONS, {"authorized": frozenset({"authorized"})}
        ):
            # Even with the table loosened, the event-specific branch refuses a
            # non-aborted prior: both controls are load-bearing.
            self.assertFalse(builders._commit_transition_valid(live_event, live_prior, live_current))
        # Top-level control: the self-event may change no state field.
        rewritten = copy.deepcopy(current)
        rewritten["commit_result"] = {"aborted_at": "2026-09-05T00:02:00Z", "reason": "rewritten"}
        rewritten_event = copy.deepcopy(event); rewritten_event["payload"]["state"] = copy.deepcopy(rewritten)
        self.assertFalse(builders._commit_transition_valid(rewritten_event, prior, rewritten))
        with mock.patch.dict(
            builders._COMMIT_EVENT_TOP_LEVEL_CHANGES,
            {"abort_disposition_recorded": frozenset({"commit_result"})},
        ):
            self.assertTrue(builders._commit_transition_valid(rewritten_event, prior, rewritten))

    def test_abort_disposition_self_event_source_fact_requires_aborted_unchanged_prior(self) -> None:
        prior, current, event = self._self_event_fixture()
        binding = {
            "candidate": {"kind": "staged-diff-sha256", "value": current["candidate"]["sha256"]},
            "review": None,
        }
        record = {"type": "decision", "outcome": "chain-abort"}
        self.assertTrue(
            builders._binding_matches_source_fact(binding, record, event, prior, current, family="commit")
        )
        # Prior must already be aborted for the self-event branch.
        live_prior = {**copy.deepcopy(prior), "state": "authorized"}
        self.assertFalse(
            builders._binding_matches_source_fact(binding, record, event, live_prior, current, family="commit")
        )
        # commit_result must be unchanged across the self-event.
        changed_prior = copy.deepcopy(prior)
        changed_prior["commit_result"] = {"aborted_at": "2026-09-05T00:00:59Z", "reason": "other"}
        self.assertFalse(
            builders._binding_matches_source_fact(binding, record, event, changed_prior, current, family="commit")
        )
        # A landed commit never carries an abort decision.
        landed = copy.deepcopy(current); landed["commit_result"] = {**current["commit_result"], "commit_sha": "1" * 40}
        landed_prior = copy.deepcopy(prior); landed_prior["commit_result"] = copy.deepcopy(landed["commit_result"])
        self.assertFalse(
            builders._binding_matches_source_fact(binding, record, event, landed_prior, landed, family="commit")
        )
        # The original chain_aborted branch still requires a transition into aborted.
        aborted_event = copy.deepcopy(event); aborted_event["payload"]["event"] = "chain_aborted"
        self.assertFalse(
            builders._binding_matches_source_fact(binding, record, aborted_event, prior, current, family="commit")
        )
        # Any other event name is refused for a chain-abort binding.
        other = copy.deepcopy(event); other["payload"]["event"] = "head_moved"
        self.assertFalse(
            builders._binding_matches_source_fact(binding, record, other, prior, current, family="commit")
        )

    def test_terminal_builder_accepts_only_explicit_absent_chain_tombstone(self) -> None:
        with self.api_environment():
            repo, run_id, run_binding = self._terminal_control_repo(
                "terminal-tombstone"
            )
            chain_id, state_path = self._write_bound_chain_state(
                repo, run_id, run_binding=run_binding, outbox=None
            )
            self._append_test_landing(repo, run_id, chain_id)
            events_path = state_path.with_name(f"{chain_id}.events.jsonl")
            state_path.unlink()
            events_path.unlink()

            with self.assertRaisesRegex(
                journal.CoordinationRefusal, builders.TERMINAL_CHAIN_INVALID
            ):
                builders.task_finish(
                    repo,
                    run_id,
                    idempotency_key=key("terminal-tombstone-absent"),
                    task="task-01",
                    status="complete",
                )

            tombstones = state_path.parent / "tombstones"
            tombstones.mkdir(mode=0o700)
            tombstone = {
                "schema": "forge-chain-tombstone/1",
                "chain_id": chain_id,
                "event": "frozen-abort",
                "reason": "operator quarantined exact chain artifacts",
                "recorded_at": "2026-08-31T12:00:00Z",
                "operator": {"host": "fixture", "pid": os.getpid(), "uid": os.geteuid()},
                "artifacts": {
                    "state": {"status": "absent"},
                    "events": {"status": "absent"},
                },
            }
            (tombstones / f"{chain_id}.json").write_bytes(
                journal._canonical_json_bytes(tombstone) + b"\n"
            )

            state_path.write_bytes(b"{}\n")
            with self.assertRaisesRegex(
                journal.CoordinationRefusal, builders.TERMINAL_CHAIN_INVALID
            ):
                builders.task_finish(
                    repo,
                    run_id,
                    idempotency_key=key("terminal-tombstone-partial"),
                    task="task-01",
                    status="complete",
                )
            state_path.unlink()

            with mock.patch.object(
                builders,
                "TERMINAL_CHAIN_CONTROLS",
                builders.TERMINAL_CHAIN_CONTROLS - {"tombstone"},
            ), self.assertRaisesRegex(
                journal.CoordinationRefusal, builders.TERMINAL_CHAIN_INVALID
            ):
                builders.task_finish(
                    repo,
                    run_id,
                    idempotency_key=key("terminal-tombstone-disabled"),
                    task="task-01",
                    status="complete",
                )

            outcome = builders.task_finish(
                repo,
                run_id,
                idempotency_key=key("terminal-tombstone-enabled"),
                task="task-01",
                status="complete",
            )
            self.assertEqual(outcome.records[0]["status"], "complete")

    def test_terminal_builder_accepts_exact_captured_tombstone_then_quarantine(self) -> None:
        with self.api_environment():
            repo, run_id, run_binding = self._terminal_control_repo(
                "terminal-captured-tombstone"
            )
            chain_id, state_path = self._write_bound_chain_state(
                repo, run_id, run_binding=run_binding, outbox=None
            )
            self._append_test_landing(repo, run_id, chain_id)
            events_path = state_path.with_name(f"{chain_id}.events.jsonl")
            events_path.write_bytes(b"{malformed-event}\n")

            def captured(path: Path) -> dict[str, object]:
                raw = path.read_bytes()
                return {
                    "status": "captured",
                    "sha256": journal._sha256(raw),
                    "bytes": len(raw),
                }

            tombstones = state_path.parent / "tombstones"
            tombstones.mkdir(mode=0o700)
            tombstone = {
                "schema": "forge-chain-tombstone/1",
                "chain_id": chain_id,
                "event": "frozen-abort",
                "reason": "operator sealed the exact frozen chain artifacts",
                "recorded_at": "2026-08-31T12:00:00Z",
                "operator": {
                    "host": "fixture",
                    "pid": os.getpid(),
                    "uid": os.geteuid(),
                },
                "artifacts": {
                    "state": captured(state_path),
                    "events": captured(events_path),
                },
            }
            (tombstones / f"{chain_id}.json").write_bytes(
                journal._canonical_json_bytes(tombstone) + b"\n"
            )

            state_bytes = state_path.read_bytes()
            state_path.write_bytes(state_bytes + b" ")
            with self.assertRaisesRegex(
                journal.CoordinationRefusal, builders.TERMINAL_CHAIN_INVALID
            ):
                builders.task_finish(
                    repo,
                    run_id,
                    idempotency_key=key("terminal-captured-changed"),
                    task="task-01",
                    status="complete",
                )
            state_path.write_bytes(state_bytes)

            with mock.patch.object(
                builders,
                "TERMINAL_CHAIN_CONTROLS",
                builders.TERMINAL_CHAIN_CONTROLS - {"tombstone"},
            ), self.assertRaisesRegex(
                journal.CoordinationRefusal, builders.TERMINAL_CHAIN_INVALID
            ):
                builders.task_finish(
                    repo,
                    run_id,
                    idempotency_key=key("terminal-captured-disabled"),
                    task="task-01",
                    status="complete",
                )

            finished = builders.task_finish(
                repo,
                run_id,
                idempotency_key=key("terminal-captured-enabled"),
                task="task-01",
                status="complete",
            )
            self.assertEqual(finished.records[0]["status"], "complete")

            state_path.unlink()
            events_path.unlink()
            closed = builders.run_close(
                repo,
                run_id,
                idempotency_key=key("terminal-captured-quarantined"),
                judgment="blocked",
                summary="Frozen chain was explicitly sealed and quarantined",
                risks=[],
                follow_ups=[],
            )
            self.assertEqual(closed.records[0]["type"], "run_closed")

    def test_each_terminal_chain_control_is_load_bearing(self) -> None:
        with self.api_environment():
            repo, run_id, run_binding = self._terminal_control_repo("control-enumeration")
            self._write_bound_chain_state(
                repo, run_id, run_binding=run_binding, outbox={"pending": True})
            self._append_orchestrator_provenance(repo, run_id)
            with mock.patch.object(
                builders,
                "TERMINAL_CHAIN_CONTROLS",
                builders.TERMINAL_CHAIN_CONTROLS - {"enumeration"},
            ):
                outcome = builders.task_finish(
                    repo, run_id, idempotency_key=key("no-enumeration"),
                    task="task-01", status="complete")
            self.assertEqual(outcome.records[0]["status"], "complete")

            repo, run_id, _run_binding = self._terminal_control_repo("control-lock")
            chain_id, _ = self._write_bound_chain_state(
                repo, run_id, run_binding=None, outbox=None)
            self._append_orchestrator_provenance(repo, run_id)
            lock = repo / ".forge/chains" / f".{chain_id}.events.lock"
            target = Path(self.temporary.name) / "hostile-chain-lock"
            target.write_text("foreign\n", encoding="utf-8")
            os.symlink(target, lock)
            with self.assertRaisesRegex(
                journal.CoordinationRefusal, builders.TERMINAL_CHAIN_INVALID
            ):
                builders.task_finish(
                    repo, run_id, idempotency_key=key("with-lock"),
                    task="task-01", status="complete",
                )
            with mock.patch.object(
                builders,
                "TERMINAL_CHAIN_CONTROLS",
                builders.TERMINAL_CHAIN_CONTROLS - {"lock"},
            ):
                outcome = builders.task_finish(
                    repo, run_id, idempotency_key=key("without-lock"),
                    task="task-01", status="complete")
            self.assertEqual(outcome.records[0]["status"], "complete")

            repo, run_id, _run_binding = self._terminal_control_repo("control-binding")
            self._write_bound_chain_state(
                repo, run_id, run_binding={"malformed": True}, outbox=None)
            self._append_orchestrator_provenance(repo, run_id)
            with mock.patch.object(
                builders,
                "TERMINAL_CHAIN_CONTROLS",
                builders.TERMINAL_CHAIN_CONTROLS - {"binding"},
            ):
                outcome = builders.task_finish(
                    repo, run_id, idempotency_key=key("without-binding"),
                    task="task-01", status="complete")
            self.assertEqual(outcome.records[0]["status"], "complete")

            repo, run_id, run_binding = self._terminal_control_repo("control-landing")
            self._write_bound_chain_state(
                repo, run_id, run_binding=run_binding, outbox=None)
            self._append_orchestrator_provenance(repo, run_id)
            with mock.patch.object(
                builders,
                "TERMINAL_CHAIN_CONTROLS",
                builders.TERMINAL_CHAIN_CONTROLS - {"landing"},
            ):
                outcome = builders.task_finish(
                    repo, run_id, idempotency_key=key("without-landing"),
                    task="task-01", status="complete")
            self.assertEqual(outcome.records[0]["status"], "complete")

            repo, run_id, run_binding = self._terminal_control_repo("control-outbox")
            chain_id, state_path = self._write_bound_chain_state(
                repo, run_id, run_binding=run_binding, outbox={"pending": True}
            )
            binding = self._append_test_landing(repo, run_id, chain_id)
            replayed_state = json.loads(state_path.read_text(encoding="utf-8"))

            def resolve_outbox_fixture(*_args, replay_only=False, **_kwargs):
                return replayed_state if replay_only else binding

            with mock.patch.object(
                builders,
                "TERMINAL_CHAIN_CONTROLS",
                builders.TERMINAL_CHAIN_CONTROLS - {"outbox"},
            ), mock.patch.object(
                builders,
                "_resolve_binding_from_descriptor",
                side_effect=resolve_outbox_fixture,
            ):
                outcome = builders.task_finish(
                    repo, run_id, idempotency_key=key("without-outbox"),
                    task="task-01", status="complete")
            self.assertEqual(outcome.records[0]["status"], "complete")

            repo, run_id, run_binding = self._terminal_control_repo("control-replay")
            chain_id, _ = self._write_bound_chain_state(
                repo, run_id, run_binding=run_binding, outbox=None
            )
            self._append_test_landing(repo, run_id, chain_id)
            with mock.patch.object(
                builders,
                "TERMINAL_CHAIN_CONTROLS",
                builders.TERMINAL_CHAIN_CONTROLS - {"replay"},
            ):
                outcome = builders.task_finish(
                    repo, run_id, idempotency_key=key("without-replay"),
                    task="task-01", status="complete",
                )
            self.assertEqual(outcome.records[0]["status"], "complete")

    def test_terminal_guard_refuses_chain_root_swap_after_enumeration(self) -> None:
        with self.api_environment():
            repo, run_id, _run_binding = self._terminal_control_repo(
                "terminal-root-swap"
            )
            self._write_bound_chain_state(
                repo, run_id, run_binding=None, outbox=None
            )
            chains = repo / ".forge/chains"
            displaced = repo / ".forge/chains-displaced"
            swapped = False
            original_chain_lock = builders._optional_chain_lock

            @contextmanager
            def swap_before_chain_lock(
                _root: Path, _chain_id: str, **_descriptor_binding: object
            ):
                nonlocal swapped
                if not swapped:
                    chains.rename(displaced)
                    chains.mkdir()
                    for source in displaced.iterdir():
                        if source.name.endswith(".json"):
                            (chains / source.name).write_bytes(source.read_bytes())
                    swapped = True
                with original_chain_lock(
                    _root, _chain_id, **_descriptor_binding
                ):
                    yield

            journal_before = (
                self.run_dir(repo, run_id) / "journal.jsonl"
            ).read_bytes()
            with mock.patch.object(
                builders, "_optional_chain_lock", side_effect=swap_before_chain_lock
            ), self.assertRaisesRegex(
                journal.CoordinationRefusal, builders.TERMINAL_CHAIN_INVALID
            ):
                builders.task_finish(
                    repo,
                    run_id,
                    idempotency_key=key("terminal-root-swap"),
                    task="task-01",
                    status="complete",
                )
            self.assertEqual(
                (self.run_dir(repo, run_id) / "journal.jsonl").read_bytes(),
                journal_before,
            )
