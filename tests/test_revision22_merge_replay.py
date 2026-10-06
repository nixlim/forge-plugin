"""Historical merge proof fields are inert, while event digests remain binding."""

from __future__ import annotations

import copy
import datetime as dt
import json

from tests import test_cli_merge_adapters as adapters
from tests._cli_loader import load_cli, package_module

CLI = load_cli("forge_revision22_merge_replay")


def rewrite_events(store, chain_id, events):
    replacements = {}
    for event in events:
        old = event["digest"]
        event["previous_digest"] = replacements.get(
            event["previous_digest"], event["previous_digest"]
        )
        event["digest"] = CLI.sha256_bytes(
            CLI.canonical_bytes({key: value for key, value in event.items() if key != "digest"})
        )
        replacements[old] = event["digest"]
    store.events_path(chain_id).write_bytes(
        b"".join(CLI.canonical_bytes(event) + b"\n" for event in events)
    )


class LegacyMergeReplayTests(adapters.MergeAdapterFixture):
    def test_new_merge_writer_refuses_legacy_members_and_event_carriers(self):
        engine = CLI.MergeEngine(self.context())
        outcome = engine.start_chain(str(self.worktree), remote_tip=self.base)
        chain_id = str(outcome.chain_id)
        store = engine.store
        events = [
            json.loads(line) for line in store.events_path(chain_id).read_bytes().splitlines()
        ]
        initial = copy.deepcopy(events[0]["payload"]["delta"])
        initial["chain_id"] = "c-2026-10-06T120000Z-dead"
        self.assertIsNone(initial["run"])
        self.assertFalse({"run_binding", "journal_outbox"} & set(initial))
        for key, value in (("run_binding", None), ("journal_outbox", None), ("run", "legacy")):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "retired state members"):
                store.create({**initial, key: value})
        self.assertFalse(store.events_path(initial["chain_id"]).exists())
        with self.assertRaisesRegex(ValueError, "^public merge transition event is invalid$"):
            store.transition(store.load(chain_id), "journal_receipted", {}, generation_digest=None)

    def bootstrap_result(self):
        engine = CLI.MergeEngine(self.context())
        outcome = engine.start_chain(str(self.worktree), remote_tip=self.base)
        store = engine.store
        chain_id = str(outcome.chain_id)
        events = [
            json.loads(line) for line in store.events_path(chain_id).read_bytes().splitlines()
        ]
        return store, chain_id, events

    def rewind_before(self, store, chain_id, events, index):
        raw = b"".join(CLI.canonical_bytes(event) + b"\n" for event in events[:index])
        replay = package_module("chain_core._merge_replay")._replay_merge_event_bytes(chain_id, raw)
        store.events_path(chain_id).write_bytes(raw)
        store.state_path(chain_id).write_bytes(CLI.canonical_bytes(replay.state) + b"\n")
        return store.load(chain_id)

    def test_merge_writer_refuses_carriers_on_valid_aborted_event(self):
        engine = CLI.MergeEngine(self.context())
        outcome = engine.start_chain(str(self.worktree), remote_tip=self.base)
        chain_id = str(outcome.chain_id)
        engine = CLI.MergeEngine(self.context(chain_id=chain_id))
        engine.abort("carrier regression")
        store = engine.store
        events = [
            json.loads(line) for line in store.events_path(chain_id).read_bytes().splitlines()
        ]
        event = events[-1]
        self.assertEqual(event["event"], "aborted")
        for key in ("journal_batch", "source_event_digest"):
            state = self.rewind_before(store, chain_id, events, len(events) - 1)
            before = store.events_path(chain_id).read_bytes()
            with self.subTest(key=key):
                with self.assertRaisesRegex(
                    ValueError, "^retired merge event carrier is not admitted$"
                ):
                    store.transition(state, "aborted", {**event["payload"], key: None},
                                     generation_digest=event["generation_digest"], at=event["at"])
                self.assertEqual(store.events_path(chain_id).read_bytes(), before)

    def assert_unbound_fetch_refused(self, shape):
        store, chain_id, events = self.bootstrap_result()
        index = next(i for i, e in enumerate(events) if e["event"] == "fetch_result")
        event = copy.deepcopy(events[index])
        payload = event["payload"]
        if shape == "missing":
            del payload["scope_proof"]
        elif shape == "proof":
            payload["scope_proof"] = {"result": "exceeded"}
        else:
            binding = payload["scope_fetch_binding"]
            for key in ("scope_request_digest", "command_template_digest", "command_digest"):
                binding[key] = "a" * 64
            binding["digest"] = CLI.sha256_bytes(CLI.canonical_bytes(
                {k: v for k, v in binding.items() if k != "digest"}
            ))
        final_bytes = store.state_path(chain_id).read_bytes()
        prior = self.rewind_before(store, chain_id, events, index)
        self.assertIsNone(prior["integration"]["intent"].get("scope_request"))
        with self.subTest(surface="writer"), self.assertRaisesRegex(
            CLI.FrozenError, "^proposed merge transition is not admitted by DM-014$"
        ):
            store.transition(prior, "fetch_result", payload,
                             generation_digest=event["generation_digest"], at=event["at"])
        events[index] = event
        rewrite_events(store, chain_id, events)
        store.state_path(chain_id).write_bytes(final_bytes)
        with self.subTest(surface="reader"), self.assertRaisesRegex(CLI.FrozenError, "transition"):
            store.load(chain_id)

    def test_unbound_fetch_requires_scope_proof_member(self):
        self.assert_unbound_fetch_refused("missing")

    def test_unbound_fetch_requires_null_proof(self):
        self.assert_unbound_fetch_refused("proof")

    def test_unbound_fetch_requires_null_scope_binding_members(self):
        self.assert_unbound_fetch_refused("binding")

    def assert_event_refused(self, store, chain_id, events, index):
        event = events[index]
        prior = self.rewind_before(store, chain_id, events, index)
        paths = (store.state_path(chain_id), store.events_path(chain_id))
        before = [path.read_bytes() for path in paths]
        with self.subTest(surface="writer"):
            with self.assertRaisesRegex(
                CLI.FrozenError, "^proposed merge transition is not admitted by DM-014$"
            ):
                store.transition(prior, event["event"], event["payload"],
                                 generation_digest=event["generation_digest"], at=event["at"])
            self.assertEqual([path.read_bytes() for path in paths], before)
        rewrite_events(store, chain_id, events[:index + 1])
        current = CLI.reduce_merge_event(prior, event)
        store.state_path(chain_id).write_bytes(CLI.canonical_bytes(current) + b"\n")
        before = [path.read_bytes() for path in paths]
        with self.subTest(surface="reader"):
            with self.assertRaisesRegex(
                CLI.FrozenError, f"^merge event {index + 1} transition is invalid$"
            ):
                store.load(chain_id)
            self.assertEqual([path.read_bytes() for path in paths], before)

    def assert_bootstrap_fetch_refused(self, mutation):
        store, chain_id, events = self.bootstrap_result()
        index = next(i for i, event in enumerate(events) if event["event"] == "fetch_result")
        event = events[index]
        if mutation == "null-generation":
            event["generation_digest"] = None
        elif mutation == "wrong-generation":
            event["generation_digest"] = "0" * 64
        elif mutation == "regressed-at":
            event["at"] = CLI.iso_z(
                CLI.parse_time(events[index - 1]["at"]) - dt.timedelta(seconds=1)
            )
        else:
            intent = event["payload"]["delta"]["integration"]["intent"]
            intent["operation_nonce"] = (
                "0" * 32 if intent["operation_nonce"] != "0" * 32 else "1" * 32
            )
        self.assert_event_refused(store, chain_id, events, index)

    def test_bootstrap_fetch_refuses_null_generation(self):
        self.assert_bootstrap_fetch_refused("null-generation")

    def test_bootstrap_fetch_refuses_wrong_generation(self):
        self.assert_bootstrap_fetch_refused("wrong-generation")

    def test_bootstrap_fetch_refuses_regressed_timestamp(self):
        self.assert_bootstrap_fetch_refused("regressed-at")

    def test_bootstrap_fetch_refuses_mismatched_operation_nonce(self):
        self.assert_bootstrap_fetch_refused("nonce")

    def test_new_merge_fetch_intent_refuses_scope_request_member(self):
        store, chain_id, events = self.bootstrap_result()
        index = next(i for i, event in enumerate(events) if event["event"] == "fetch_intent")
        for value in (None, {}, {"task_id": "legacy"}):
            with self.subTest(value=value):
                changed = copy.deepcopy(events)
                changed[index]["payload"]["scope_request"] = value
                self.assert_event_refused(store, chain_id, changed, index)

    def test_new_merge_reader_refuses_lone_source_event_digest(self):
        store, chain_id, events = self.bootstrap_result()
        self.assertEqual(events[-1]["event"], "generation_refreshed")
        self.assertNotIn("run_binding", store.load(chain_id))
        events[-1]["payload"]["source_event_digest"] = "a" * 64
        rewrite_events(store, chain_id, events)
        paths = (store.state_path(chain_id), store.events_path(chain_id))
        before = [path.read_bytes() for path in paths]
        with self.assertRaisesRegex(
            CLI.FrozenError, f"^merge event {len(events)} transition is invalid$"
        ):
            store.load(chain_id)
        self.assertEqual([path.read_bytes() for path in paths], before)

    def test_merge_state_requires_both_legacy_keys_or_neither(self):
        store, chain_id, _events = self.bootstrap_result()
        state = store.load(chain_id)
        for key in ("run_binding", "journal_outbox"):
            with self.subTest(key=key), self.assertRaisesRegex(
                CLI.FrozenError, "materialized merge state has an invalid top-level key set"
            ):
                CLI.validate_merge_state({**state, key: None}, chain_id)
        self.assertEqual(CLI.validate_merge_state(state, chain_id), state)
        legacy = {**state, "run_binding": None, "journal_outbox": None}
        self.assertEqual(CLI.validate_merge_state(legacy, chain_id), legacy)
