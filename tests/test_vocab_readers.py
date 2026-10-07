"""Journal readers keep legacy and future records as data."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.codex_orchestrator.journal import read_journal, validate_run


class VocabularyReaderTests(unittest.TestCase):
    def test_unknown_kind_and_legacy_type_survive_read(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            records = [
                {"kind": "future_execution", "run_id": "run", "payload": {"x": 1}},
                {"type": "verification", "judgment": "blocked"},
                {"type": "legacy_unrecognized", "scope": ["elsewhere"]},
            ]
            path = run_dir / "journal.jsonl"
            path.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            read, issues = read_journal(path)
            validation = validate_run(run_dir)
        self.assertEqual(read, records)
        self.assertEqual(issues, [])
        self.assertEqual(validation, {"ok": True, "issues": []})

    def test_partial_final_line_is_tolerated_only_on_live_read(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "journal.jsonl"
            path.write_text(
                '{"kind":"decision","run_id":"run","text":"first"}\n'
                '{"kind":"decision","run_id":"run"',
                encoding="utf-8",
            )
            records, live_issues = read_journal(path, allow_partial_final_line=True)
            _, closed_issues = read_journal(path)
        self.assertEqual(len(records), 1)
        self.assertEqual(live_issues, [])
        self.assertEqual(
            closed_issues,
            ["forge: journal validate failed: malformed JSON object at line 2"],
        )
