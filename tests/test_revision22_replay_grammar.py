"""Kept native replay grammar tests moved from the retired CLI surfaces module."""
import copy
import hashlib
import unittest

from tests._cli_loader import load_cli

CLI = load_cli("forge_revision22_replay_grammar")


def key(value):
    return hashlib.sha256(value.encode()).hexdigest()


class MergeDeltaReplayTests(unittest.TestCase):
    def test_merge_reducer_uses_explicit_delta_and_refuses_payload_state(self) -> None:
        recorded_at = "2026-08-28T12:00:00Z"
        delta: dict[str, object] = {
            "schema": "forge-merge-chain/1",
            "chain_id": "c-2026-08-28T120000Z-cafe",
            "kind": "merge",
            "state": "classifying",
            "created_at": recorded_at,
            "owner": {},
            "run": None,
            "repository": "/fixture/revision9/repository",
            "worktree": {},
            "branch": "refs/heads/fixture",
            "target": {},
            "policy_source": {},
            "candidate": None,
            "tier": None,
            "steps": {},
            "review": {},
            "approval": {},
            "authorization": {},
            "integration": {},
            "cleanup": {},
            "run_binding": None,
        }
        event: dict[str, object] = {
            "schema": "forge-merge-event/1",
            "chain_id": delta["chain_id"],
            "sequence": 1,
            "at": recorded_at,
            "event": "chain_started",
            "generation_digest": None,
            "previous_digest": "0" * 64,
            "payload": {"delta": delta},
            "digest": "1" * 64,
        }

        reduced = CLI.reduce_merge_event(None, copy.deepcopy(event))
        self.assertEqual(reduced["state"], "classifying")
        self.assertEqual(reduced["last_event_at"], recorded_at)
        self.assertEqual(reduced["journal_outbox"], None)
        self.assertNotIn("state", event["payload"])

        malicious = copy.deepcopy(event)
        malicious["payload"]["state"] = {
            "state": "closed",
            "journal_outbox": None,
            "invented": True,
        }
        with self.assertRaisesRegex(
            ValueError, "merge transition lacks an explicit state delta"
        ):
            CLI.reduce_merge_event(None, malicious)

        epoch_digest = key("derived-epoch-event")
        epoch_event = {
            "schema": "forge-merge-event/1",
            "chain_id": delta["chain_id"],
            "sequence": 2,
            "at": "2026-08-28T12:01:00Z",
            "event": "epoch_intent",
            "generation_digest": key("derived-epoch-generation"),
            "previous_digest": event["digest"],
            "payload": {
                "delta": {
                    "state": "rebasing",
                    "integration": {
                        "epoch": {
                            "operation_nonce": "e" * 32,
                            "generation_digest": key(
                                "derived-epoch-generation"
                            ),
                            "intent_digest": None,
                            "started_at": "2026-08-28T12:01:00Z",
                        }
                    },
                }
            },
            "digest": epoch_digest,
        }
        epoch_state = CLI.reduce_merge_event(reduced, epoch_event)
        self.assertEqual(
            epoch_state["integration"]["epoch"]["intent_digest"],
            epoch_digest,
        )
        recursive_epoch = copy.deepcopy(epoch_event)
        recursive_epoch["payload"]["delta"]["integration"]["epoch"][
            "intent_digest"
        ] = epoch_digest
        with self.assertRaisesRegex(
            ValueError, "merge transition lacks an explicit state delta"
        ):
            CLI.reduce_merge_event(reduced, recursive_epoch)
