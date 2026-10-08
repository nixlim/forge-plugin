"""Load native pre-Revision-22 writer histories without migration or regeneration."""

import builtins
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests._cli_loader import load_cli, package_module

CLI = load_cli("forge_revision22_head_fixtures")
FIXTURES = Path(__file__).parent / "fixtures/revision22-head"


@contextlib.contextmanager
def no_journal_access():
    """Sense both late journal imports and any attempted journal file open."""
    prefixes = ("codex_orchestrator", "scripts.codex_orchestrator")
    removed = {name: sys.modules.pop(name) for name in tuple(sys.modules)
               if name.startswith(prefixes)}
    opened: list[str] = []
    original_builtin = builtins.open
    original_io = io.open
    original_os = os.open

    def guarded_open(file, *args, **kwargs):
        if str(file).endswith("journal.jsonl"):
            opened.append(str(file))
        return original_builtin(file, *args, **kwargs)

    def guarded_io(file, *args, **kwargs):
        if str(file).endswith("journal.jsonl"):
            opened.append(str(file))
        return original_io(file, *args, **kwargs)

    def guarded_os(file, *args, **kwargs):
        if str(file).endswith("journal.jsonl"):
            opened.append(str(file))
        return original_os(file, *args, **kwargs)

    try:
        with (mock.patch("builtins.open", side_effect=guarded_open),
              mock.patch("io.open", side_effect=guarded_io),
              mock.patch("os.open", side_effect=guarded_os)):
            try:
                yield
            finally:
                imported = {name for name in sys.modules if name.startswith(prefixes)}
                assert not imported, f"journal package imported: {imported}"
                assert not opened, f"journal path opened: {opened}"
    finally:
        for name in tuple(sys.modules):
            if name.startswith(prefixes):
                sys.modules.pop(name)
        sys.modules.update(removed)


class HeadWriterCompatibilityTests(unittest.TestCase):
    def test_journal_access_sensor_is_load_bearing(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(AssertionError, "journal path opened"):
                with no_journal_access():
                    (Path(directory) / "journal.jsonl").write_text("", encoding="utf-8")

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "fixtures"
        shutil.copytree(FIXTURES, self.root)

    def assert_head_fixture(self, family, bound):
        root = self.root / ("bound" if bound else "unbound")
        store_type, chain_id = {
            "merge": (CLI.MergeChainStore, "c-2026-08-30T120000Z-a001"),
            "commit": (CLI.ChainStore, "c-2026-08-30T110000Z-c002"),
        }[family]
        store = store_type(root)
        paths = (store.state_path(chain_id), store.events_path(chain_id))
        before = [path.read_bytes() for path in paths]
        with no_journal_access():
            loaded = store.load(chain_id)
        self.assertEqual(loaded, json.loads(before[0]))
        self.assertEqual(isinstance(loaded["run_binding"], dict), bound)
        self.assertIsNone(loaded["journal_outbox"])
        self.assertEqual([path.read_bytes() for path in paths], before)

    def test_head_merge_bytes_load_in_place(self):
        for bound in (False, True):
            with self.subTest(bound=bound):
                self.assert_head_fixture("merge", bound)

    def test_head_commit_bytes_load_in_place(self):
        for bound in (False, True):
            with self.subTest(bound=bound):
                self.assert_head_fixture("commit", bound)

    def test_legacy_null_outbox_projection_is_load_bearing(self):
        replay = package_module("chain_core._merge_replay")
        original = replay.reduce_merge_event

        def omit_legacy_outbox(previous, event):
            state = original(previous, event)
            state.pop("journal_outbox", None)
            return state

        self.assert_head_fixture("merge", True)
        with mock.patch.object(replay, "reduce_merge_event", side_effect=omit_legacy_outbox):
            with self.assertRaisesRegex(CLI.FrozenError, "contradicts authenticated event replay"):
                self.assert_head_fixture("merge", True)

    def assert_lifecycle_fixture(self, family):
        root = self.root / "lifecycle"
        chain_id = {
            "commit": "c-2026-09-02T182547Z-7ee3",
            "merge": "c-2026-10-06T140613Z-6a38",
        }[family]
        store = (CLI.ChainStore if family == "commit" else CLI.MergeChainStore)(root)
        paths = (store.state_path(chain_id), store.events_path(chain_id))
        before = [path.read_bytes() for path in paths]
        with no_journal_access():
            self.assertEqual(store.load(chain_id), json.loads(before[0]))
        self.assertEqual([path.read_bytes() for path in paths], before)
        return [json.loads(line) for line in before[1].splitlines()]

    def test_bound_commit_receipts_and_abort_disposition_load_in_place(self):
        events = self.assert_lifecycle_fixture("commit")
        self.assertIn("abort_disposition_recorded", [e["payload"]["event"] for e in events])
        self.assertTrue(any(
            current["payload"]["event"] == "journal_receipted"
            and prior["payload"]["state"]["journal_outbox"] is not None
            and current["payload"]["state"]["journal_outbox"] is None
            for prior, current in zip(events, events[1:], strict=False)
        ))
        for carrier in ("journal_batch", "source_event_digest"):
            self.assertTrue(any(carrier in e["payload"]["details"] for e in events), carrier)

    def test_merge_populated_scope_proof_loads_in_place(self):
        events = self.assert_lifecycle_fixture("merge")
        self.assertTrue(any(isinstance(e["payload"].get("scope_proof"), dict) for e in events))

    def test_refusing_outbox_clearing_receipt_is_detected(self):
        replay = package_module("chain_core._commit_replay")
        original = replay._legacy_fact_valid

        def refuse_outbox_change(prior, current):
            return original(prior, current) and (
                prior.get("journal_outbox") == current.get("journal_outbox")
            )

        self.test_bound_commit_receipts_and_abort_disposition_load_in_place()
        with mock.patch.object(replay, "_legacy_fact_valid", side_effect=refuse_outbox_change):
            with self.assertRaises(CLI.FrozenError):
                self.test_bound_commit_receipts_and_abort_disposition_load_in_place()

    def load_merge_fixture(self, name):
        store = CLI.MergeChainStore(self.root / name)
        path = next((self.root / name / '.forge/chains').glob('*.events.jsonl'))
        chain_id = path.name.removesuffix('.events.jsonl')
        paths = (store.state_path(chain_id), path)
        before = [p.read_bytes() for p in paths]
        with no_journal_access():
            self.assertEqual(store.load(chain_id), json.loads(before[0]))
        self.assertEqual([p.read_bytes() for p in paths], before)
        return store, chain_id, [json.loads(line) for line in before[1].splitlines()]

    def test_head_merge_carrier_and_receipt_load_in_place(self):
        _store, chain_id, events = self.load_merge_fixture('merge-receipt')
        replay = package_module('chain_core._merge_replay')._replay_merge_event_bytes(
            chain_id, b''.join(CLI.canonical_bytes(e) + b'\n' for e in events)
        )
        receipts = [(prior, current) for event, prior, current in replay.entries
                    if event['event'] == 'journal_receipted']
        self.assertTrue(receipts)
        for prior, current in receipts:
            self.assertIsInstance(prior['journal_outbox'], dict)
            self.assertIsNone(current['journal_outbox'])
        self.assertTrue(any('journal_batch' in e['payload'] for e in events))

    def test_head_scope_exceeded_abort_loads_in_place(self):
        store, chain_id, events = self.load_merge_fixture('merge-scope-abort')
        self.assertEqual(store.load(chain_id)['state'], 'aborted')
        self.assertTrue(any(e['payload'].get('scope_proof', {}).get('result') == 'exceeded'
                            for e in events if isinstance(e['payload'].get('scope_proof'), dict)))

    def test_head_scope_abort_rejects_tampered_preconditions_digest(self):
        from tests.test_revision22_merge_replay import rewrite_events

        store, chain_id, events = self.load_merge_fixture('merge-scope-abort')
        release = next(e for e in events if e['event'] == 'ownership_release_intent')
        release['payload']['terminal_preconditions_digest'] = '0' * 64
        rewrite_events(store, chain_id, events)
        with self.assertRaisesRegex(CLI.FrozenError, 'transition is invalid'):
            store.load(chain_id)
