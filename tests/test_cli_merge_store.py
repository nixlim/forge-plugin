"""Focused event-family and dormant DM-014 storage tests for Forge CLI."""

from __future__ import annotations

import contextlib
import copy
import datetime as dt
import hashlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest import mock



ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = ROOT / "scripts" / "forge" / "cli.py"


from tests._cli_loader import load_script, package_module, patch_chain_core  # shared loader


CLI = load_script("forge_cli_merge_store_tests", CLI_PATH)
CORE = package_module("chain_core")  # cli split phase 2b: canonical chain-core module
RUNTIME = package_module("runtime")  # cli split phase 2a: canonical patch seam for runtime controls
CLI_FIXTURE_SUPPORT = load_script(
    "forge_cli_merge_store_fixture_support",
    ROOT / "tests" / "test_cli_chain.py",
)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class MergeStoreFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.git_dir = self.root / ".git"
        self.git_dir.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def initial_merge(
        self,
        chain_id: str = "c-2026-08-30T120000Z-a001",
    ) -> tuple[dict[str, object], dict[str, object]]:
        at = "2026-01-01T12:00:00Z"
        worktree_identity = {
            "path": str(self.root),
            "git_dir": str(self.git_dir),
            "common_dir": str(self.git_dir),
        }
        worktree_digest = digest(CLI.canonical_bytes(worktree_identity))
        claim_path = str(
            self.git_dir.parent
            / ".forge"
            / "chains"
            / "owners"
            / f"{worktree_digest}.claim"
        )
        owner = {
            "pid": os.getpid(),
            "host": "merge-store-test",
            "session": "merge-store-session",
            "started_at": at,
        }
        claim_record = {
            "chain_id": chain_id,
            "host": owner["host"],
            "pid": owner["pid"],
            "session": owner["session"],
            "started_at": owner["started_at"],
            "worktree_digest": worktree_digest,
        }
        claim_digest = digest(CLI.canonical_bytes(claim_record))
        initial = {
            "schema": "forge-merge-chain/1",
            "chain_id": chain_id,
            "kind": "merge",
            "state": "classifying",
            "created_at": at,
            "owner": owner,
            "run": None,
            "repository": str(self.root),
            "worktree": {
                **worktree_identity,
                "claim": {
                    "status": "unpublished",
                    "path": claim_path,
                    "inode": None,
                    "digest": None,
                },
            },
            "branch": "refs/heads/main",
            "target": {
                "remote": "origin",
                "destination_ref": "refs/heads/main",
                "manifest_commit": "1" * 40,
            },
            "policy_source": {"commit": "1" * 40, "digest": "2" * 64},
            "candidate": None,
            "tier": None,
            "steps": {},
            "review": {},
            "approval": {},
            "authorization": {},
            "integration": {
                "condition": "none",
                "primary_condition": "none",
                "epoch": None,
                "remote_movement_count": 0,
                "intent": None,
                "observed": None,
                "pre_rebase": None,
                "conflict": None,
                "push": None,
            },
            "cleanup": {"condition": "none"},
        }
        metadata = {
            "at": at,
            "worktree_identity": worktree_identity,
            "worktree_digest": worktree_digest,
            "claim_path": claim_path,
            "claim_digest": claim_digest,
        }
        return initial, metadata

    def create_merge(
        self,
        chain_id: str = "c-2026-08-30T120000Z-a001",
        *,
        boundary=None,
    ) -> tuple[object, dict[str, object], dict[str, object]]:
        initial, metadata = self.initial_merge(chain_id)
        store = CLI.MergeChainStore(self.root, boundary=boundary)
        state = store.create(
            initial,
            at=str(metadata["at"]),
            session="merge-store-session",
        )
        return store, state, metadata

    def create_commit(
        self,
        chain_id: str = "c-2026-08-30T110000Z-c001",
        *,
        event: str = "chain_started",
    ) -> tuple[object, dict[str, object], dict[str, object]]:
        fixed = dt.datetime(2026, 1, 1, 11, 0, tzinfo=dt.timezone.utc)
        policy = CLI.Policy(
            sha="3" * 40,
            raw=b"fixture policy\n",
            digest="4" * 64,
            regions={},
            gate1="true",
            stack_commands=[],
            invariants=[],
            changelog=None,
            reviewer_eval_triggers=(),
            reviewer_eval_region_digest=None,
            reviewer_eval_trigger_error=None,
        )
        repository = CLI.Repository(self.root)
        with mock.patch.object(RUNTIME, "utc_now", return_value=fixed):
            state = CLI._new_state(
                chain_id,
                repository,
                "5" * 40,
                policy,
                ["docs/example.md"],
                "standard",
            )
            details = {"paths": list(state["paths"])}
            store = CLI.ChainStore(self.root)
            store.create(state, event, details)
        return store, state, {
            "fixed": fixed,
            "details": details,
            "event": event,
        }

    def ownership_intent(
        self,
        store: object,
        state: dict[str, object],
        metadata: dict[str, object],
        *,
        at: str = "2026-01-01T12:00:01Z",
    ) -> dict[str, object]:
        return store.transition(
            state,
            "ownership_intent",
            {
                "worktree_digest": metadata["worktree_digest"],
                "claim_path": metadata["claim_path"],
                "intended_claim_digest": metadata["claim_digest"],
                "predecessor_chain_id": None,
                "predecessor_release_digest": None,
            },
            generation_digest=None,
            at=at,
            session="merge-store-session",
        )


class MergeStoreFamilyAndReplayTests(MergeStoreFixture):
    def test_operator_tombstone_refuses_captured_merge_with_unreadable_events(self) -> None:
        _merge_store, merge_state, _metadata = self.create_merge(
            "c-2026-08-30T120000Z-a000"
        )
        chain_id = str(merge_state["chain_id"])
        store = CLI.ChainStore(self.root)
        store.events_path(chain_id).write_bytes(b"{malformed-event}\n")
        engine = CLI.Engine(
            CLI.CommandContext(
                CLI.Repository(self.root),
                store,
                CLI.CLIOptions(chain_id=chain_id, revision9_face=True),
            )
        )

        with self.assertRaises(CLI.Refusal) as caught:
            engine.operator_tombstone(
                "a captured merge chain must not inherit commit family"
            )

        self.assertEqual(
            caught.exception.reason_code.value, "state-precondition"
        )
        self.assertFalse(
            (self.root / ".forge/chains/tombstones" / f"{chain_id}.json").exists()
        )

    def test_commit_bytes_are_identical_and_merge_grammar_stays_separate(self) -> None:
        commit_store, commit_state, fixture = self.create_commit()
        chain_id = str(commit_state["chain_id"])
        payload = {
            "at": CLI.iso_z(fixture["fixed"]),
            "details": fixture["details"],
            "event": fixture["event"],
            "state": copy.deepcopy(commit_state),
        }
        unsigned = {
            "sequence": 1,
            "prev_digest": CLI.ZERO_DIGEST,
            "payload": payload,
        }
        expected_event = {
            **unsigned,
            "digest": digest(CLI.canonical_bytes(unsigned)),
        }
        self.assertEqual(
            commit_store.events_path(chain_id).read_bytes(),
            CLI.canonical_bytes(expected_event) + b"\n",
        )
        self.assertEqual(
            commit_store.state_path(chain_id).read_bytes(),
            CLI.canonical_bytes(commit_state) + b"\n",
        )

        _merge_store, merge_state, _metadata = self.create_merge(
            "c-2026-08-30T120000Z-a002"
        )
        self.assertEqual(
            CLI.MERGE_STATE_KEYS,
            {
                "schema",
                "chain_id",
                "kind",
                "state",
                "created_at",
                "last_event_at",
                "inactive_after",
                "owner",
                "run",
                "repository",
                "worktree",
                "branch",
                "target",
                "policy_source",
                "candidate",
                "tier",
                "steps",
                "review",
                "approval",
                "authorization",
                "integration",
                "cleanup",
            },
        )
        self.assertEqual(
            CLI.MERGE_EVENT_NAMES,
            {
                "chain_started",
                "ownership_intent",
                "ownership_claimed",
                "ownership_release_intent",
                "ownership_released",
                "gate_recorded",
                "review_requested",
                "review_attached",
                "review_disposition",
                "approval_recorded",
                "generation_refreshed",
                "generation_carried_forward",
                "epoch_intent",
                "fetch_intent",
                "fetch_result",
                "rebase_intent",
                "rebase_conflict",
                "rebase_result",
                "reverification_result",
                "push_intent",
                "push_observed",
                "cleanup_intent",
                "cleanup_result",
                "condition_recorded",
                "lock_release_result",
                "aborted",
                "closed",
                "journal_receipted",
            },
        )
        self.assertEqual(
            CLI.MERGE_EVENT_KEYS,
            {
                "schema",
                "chain_id",
                "sequence",
                "at",
                "event",
                "generation_digest",
                "previous_digest",
                "payload",
                "digest",
            },
        )
        self.assertEqual(
            CLI.EVENT_KEYS,
            {"sequence", "prev_digest", "payload", "digest"},
        )
        self.assertEqual(
            CLI.STATE_KEYS,
            {
                "schema",
                "chain_id",
                "kind",
                "state",
                "created_at",
                "last_event_at",
                "inactive_after",
                "repo_head",
                "policy_source",
                "paths",
                "staging",
                "candidate",
                "tier",
                "steps",
                "review",
                "approval",
                "authorization",
                "commit_result",
            },
        )
        self.assertIs(CLI.validate_merge_state(merge_state), merge_state)
        with self.assertRaises(CLI.FrozenError):
            CLI.validate_state(copy.deepcopy(merge_state))
        with self.assertRaises(CLI.FrozenError):
            CLI.ChainStore(self.root).load(str(merge_state["chain_id"]))

    def test_commit_stale_cas_reports_current_archive_tail(self) -> None:
        store, state, _fixture = self.create_commit(
            "c-2026-08-30T110000Z-c002"
        )
        chain_id = str(state["chain_id"])
        stale = store.load(chain_id)
        current = store.load(chain_id)
        CLI._transition_state(stale, "verifying")
        CLI._transition_state(stale, "reviewing")
        CLI._transition_state(current, "verifying")

        archive_run_id = "run-20260830-stale-cas"
        archive_path = f".forge/history/runs/{archive_run_id}.md"
        current["paths"] = [archive_path]
        current["staging"]["archive"] = {
            "run_id": archive_run_id,
            "path": archive_path,
            "closing_head": "6" * 40,
            "legacy_recovered_head": None,
            "legacy_approval": None,
            "post_close_validation": str(self.root / "archive-validation"),
            "dispense_targets": [],
            "dispense_reason": None,
            "rendered_sha256": "7" * 64,
        }
        advanced_at = dt.datetime(
            2026, 1, 1, 11, 0, 1, tzinfo=dt.timezone.utc
        )
        with mock.patch.object(RUNTIME, "utc_now", return_value=advanced_at):
            store.persist(current, "fixture_tail_advanced", {"fixture": "current"})

        expected_tail = copy.deepcopy(current)
        events_before_refusal = store.events_path(chain_id).read_bytes()
        with self.assertRaises(CLI.Refusal) as refused:
            store.persist(stale, "fixture_stale_result", {"fixture": "stale"})

        self.assertEqual(refused.exception.reason_code.value, "state-precondition")
        self.assertEqual(refused.exception.chain, expected_tail)
        outcome = refused.exception.outcome()
        self.assertEqual(outcome.state, "verifying")
        self.assertEqual(outcome.schema, "forge-cli/2")
        self.assertEqual(store.events_path(chain_id).read_bytes(), events_before_refusal)


    def test_commit_persist_transition_bytes_remain_identical(self) -> None:
        store, state, fixture = self.create_commit(
            "c-2026-08-30T110000Z-c003"
        )
        chain_id = str(state["chain_id"])
        initial_state = copy.deepcopy(state)
        initial_payload = {
            "at": CLI.iso_z(fixture["fixed"]),
            "details": fixture["details"],
            "event": fixture["event"],
            "state": initial_state,
        }
        initial_unsigned = {
            "sequence": 1,
            "prev_digest": CLI.ZERO_DIGEST,
            "payload": initial_payload,
        }
        initial_event = {
            **initial_unsigned,
            "digest": digest(CLI.canonical_bytes(initial_unsigned)),
        }

        CLI._transition_state(state, "verifying")
        transition_at = fixture["fixed"] + dt.timedelta(seconds=1)
        transition_details = {"fixture": "persist-byte-identity"}
        expected_state = copy.deepcopy(state)
        expected_state["last_event_at"] = CLI.iso_z(transition_at)
        expected_state["inactive_after"] = CLI.iso_z(
            transition_at + dt.timedelta(seconds=CLI.INACTIVE_SECONDS)
        )
        with mock.patch.object(RUNTIME, "utc_now", return_value=transition_at):
            store.persist(state, "fixture_verifying", transition_details)

        transition_payload = {
            "at": CLI.iso_z(transition_at),
            "details": transition_details,
            "event": "fixture_verifying",
            "state": expected_state,
        }
        transition_unsigned = {
            "sequence": 2,
            "prev_digest": initial_event["digest"],
            "payload": transition_payload,
        }
        transition_event = {
            **transition_unsigned,
            "digest": digest(CLI.canonical_bytes(transition_unsigned)),
        }
        self.assertEqual(state, expected_state)
        self.assertEqual(
            store.events_path(chain_id).read_bytes(),
            CLI.canonical_bytes(initial_event)
            + b"\n"
            + CLI.canonical_bytes(transition_event)
            + b"\n",
        )
        self.assertEqual(
            store.state_path(chain_id).read_bytes(),
            CLI.canonical_bytes(expected_state) + b"\n",
        )

    def test_family_is_event_first_and_one_frozen_chain_does_not_wedge_others(self) -> None:
        commit_store, commit_state, _fixture = self.create_commit(
            event="fixture_authorized"
        )
        merge_store, merge_state, _metadata = self.create_merge(
            "c-2026-08-30T120000Z-a003"
        )
        merge_id = str(merge_state["chain_id"])
        bad_id = "c-2026-08-30T120000Z-a004"
        merge_store.state_path(merge_id).write_bytes(
            CLI.canonical_bytes(
                {"schema": "forge-chain/1", "kind": "commit", "state": "closed"}
            )
            + b"\n"
        )
        merge_store.events_path(bad_id).write_bytes(b"{not-json}\n")

        self.assertEqual(commit_store.chain_family(merge_id), "merge")
        warning = io.StringIO()
        with contextlib.redirect_stderr(warning):
            commit_ids = commit_store.list_ids(family="commit")
        self.assertEqual(commit_ids, [str(commit_state["chain_id"])])
        self.assertEqual(
            warning.getvalue(),
            "forge: warning — skipped unreadable chain "
            f"{bad_id} while enumerating commit chains\n",
        )
        self.assertEqual(commit_store.list_ids(family="merge"), [merge_id])
        with self.assertRaises(CLI.FrozenError):
            commit_store.chain_family(bad_id)
        with self.assertRaises(CLI.FrozenError) as raised:
            merge_store.load(merge_id)
        self.assertEqual(raised.exception.schema, "forge-cli/2")

        options = CLI.CLIOptions()
        engine = CLI.Engine(
            CLI.CommandContext(CLI.Repository(self.root), commit_store, options)
        )
        selected = engine._chains_for_worktree()
        self.assertEqual(
            [state["chain_id"] for state in selected],
            [commit_state["chain_id"]],
        )

        options.chain_id = merge_id
        with self.assertRaisesRegex(
            CLI.FrozenError, "commit selection refused a merge-family chain"
        ):
            engine.abort("commit abort must not seal merge state")
        self.assertFalse(
            (self.root / ".forge/chains/tombstones" / f"{merge_id}.json").exists()
        )

        routed = CLI._route_shared_chain_engine(engine)
        self.assertIsInstance(routed, CLI.MergeEngine)
        with self.assertRaises(CLI.FrozenError) as routed_failure:
            routed.status()
        self.assertEqual(routed_failure.exception.schema, "forge-cli/2")

    def test_missing_and_stale_projection_repair_before_resolver_and_cas(self) -> None:
        store, first, metadata = self.create_merge(
            "c-2026-08-30T120000Z-a005"
        )
        first_projection = CLI.canonical_bytes(first) + b"\n"
        current = self.ownership_intent(store, first, metadata)
        state_path = store.state_path(str(current["chain_id"]))
        final_projection = CLI.canonical_bytes(current) + b"\n"

        state_path.write_bytes(first_projection)
        repaired = store.load(str(current["chain_id"]), session="repair-session")
        self.assertEqual(repaired, current)
        self.assertEqual(state_path.read_bytes(), final_projection)

        state_path.unlink()
        repaired = store.load(str(current["chain_id"]), session="repair-session")
        self.assertEqual(repaired, current)
        self.assertEqual(state_path.read_bytes(), final_projection)

        with self.assertRaises(CLI.Refusal) as stale:
            self.ownership_intent(
                store,
                first,
                metadata,
                at="2026-01-01T12:00:02Z",
            )
        self.assertEqual(stale.exception.reason_code.value, "state-precondition")
        self.assertEqual(stale.exception.chain, current)
        self.assertEqual(state_path.read_bytes(), final_projection)

    def test_status_and_all_shared_review_verbs_route_to_dormant_merge_family(self) -> None:
        store, state, metadata = self.create_merge(
            "c-2026-08-30T120000Z-a006"
        )
        state = self.ownership_intent(store, state, metadata)
        chain_id = str(state["chain_id"])
        options = CLI.CLIOptions(chain_id=chain_id)
        engine = CLI.Engine(
            CLI.CommandContext(CLI.Repository(self.root), CLI.ChainStore(self.root), options)
        )

        status = CLI.dispatch(engine, CLI.build_parser().parse_args(["status"]))
        self.assertTrue(status.ok)
        self.assertEqual(status.schema, "forge-cli/2")
        before = store.events_path(chain_id).read_bytes()
        review_argv = (
            ("review", "request"),
            ("review", "collect"),
            ("review", "cancel"),
            ("review", "attach", "--verdict-file", "verdict.txt"),
            (
                "review",
                "disposition",
                "--finding",
                "1",
                "--severity",
                "MAJOR",
                "--resolution",
                "resolved",
            ),
        )
        for argv in review_argv:
            with self.subTest(argv=argv), self.assertRaises(CLI.Refusal) as refused:
                CLI.dispatch(engine, CLI.build_parser().parse_args(list(argv)))
            envelope = refused.exception.outcome().envelope()
            self.assertEqual(envelope["schema"], "forge-cli/2")
            self.assertEqual(envelope["reason_code"], "state-precondition")
        self.assertEqual(store.events_path(chain_id).read_bytes(), before)
        with self.assertRaises(CLI.Refusal):
            CLI.build_parser().parse_args(["merge", "start"])

    def test_each_new_store_control_fails_closed_when_disabled_in_memory(self) -> None:
        self.assertEqual(
            CLI.MERGE_STORE_CONTROLS,
            CLI._REQUIRED_MERGE_STORE_CONTROLS,
        )
        for control in sorted(CLI._REQUIRED_MERGE_STORE_CONTROLS):
            with self.subTest(control=control), patch_chain_core("MERGE_STORE_CONTROLS",
                CLI._REQUIRED_MERGE_STORE_CONTROLS - {control},
            ), self.assertRaises(CLI.FrozenError):
                CLI._require_merge_store_control(control)

    def test_registered_builder_transition_grammar_is_load_bearing(self) -> None:
        store, state, metadata = self.create_merge(
            "c-2026-08-30T120000Z-a007"
        )
        state = self.ownership_intent(store, state, metadata)
        builders = package_module("chain_core._replay_grammar")
        projection = store.state_path(str(state["chain_id"])).read_bytes()
        with mock.patch.object(
            builders, "_validate_merge_transition", return_value=False
        ), self.assertRaises(CLI.FrozenError):
            store.load(str(state["chain_id"]), session="builder-mutant")
        self.assertEqual(
            store.state_path(str(state["chain_id"])).read_bytes(), projection
        )



if __name__ == "__main__":
    unittest.main()
