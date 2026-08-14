from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tests.test_drift_check import DriftFixture


ROOT = Path(__file__).resolve().parents[1]
DRIFT = ROOT / "scripts/forge/drift-check.sh"
EXTRACTOR = ROOT / "scripts/forge/journal-patterns.py"


class D14JournalConfinementTests(unittest.TestCase):
    def assert_confined(self, summary: dict) -> None:
        self.assertEqual({"state": "ok"}, summary["status"])
        self.assertTrue(summary["journal_patterns"]["available"])
        self.assertEqual({}, summary["journal_patterns"]["decision_outcomes"])
        self.assertEqual("journal-patterns", summary["checks"][-1]["check"])
        self.assertEqual("passed", summary["checks"][-1]["outcome"])

    def test_outside_journal_symlink_is_refused_and_guard_is_discriminating(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            fixture = DriftFixture(Path(temp))
            outside = fixture.root / "outside-journals"
            outside.mkdir()
            (outside / "journal.jsonl").write_text(
                '{"type":"run_started","run_id":"outside"}\n'
                '{"type":"decision","outcome":"must-not-be-read"}\n',
                encoding="utf-8",
            )
            (fixture.repo / ".git/info/exclude").write_text(
                ".codex-orchestrator/\n", encoding="utf-8"
            )
            runs = fixture.repo / ".codex-orchestrator" / "runs"
            runs.mkdir(parents=True)
            (runs / "evil").symlink_to(outside, target_is_directory=True)

            result = fixture.invoke()
            summary = json.loads(result.stdout)
            self.assertEqual(0, result.returncode)
            self.assert_confined(summary)

            source = DRIFT.read_text(encoding="utf-8")
            symlink_guard = (
                "if path.is_file() and not path.is_symlink() "
                "and not path.parent.is_symlink()"
            )
            self.assertEqual(1, source.count(symlink_guard))
            mutant = fixture.root / "drift-no-journal-confinement.sh"
            mutant.write_text(
                source.replace(symlink_guard, "if path.is_file()", 1),
                encoding="utf-8",
            )
            mutant.chmod(0o755)
            env = os.environ.copy()
            env.update(
                {
                    "CLAUDE_PLUGIN_ROOT": str(fixture.plugin),
                    "FORGE_DRIFT_NOW": "2026-01-02T03:04:05Z",
                    "FORGE_DRIFT_LOCK_TIMEOUT": "1",
                    "FORGE_DRIFT_PRUNE_DAYS": "30",
                }
            )
            mutated_result = subprocess.run(
                ["bash", str(mutant), "--repo", str(fixture.repo)],
                cwd=fixture.repo,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            mutated_summary = json.loads(mutated_result.stdout)
            self.assertEqual(2, mutated_result.returncode)
            self.assertFalse(mutated_summary["journal_patterns"]["available"])
            self.assertEqual(
                "journal-path", mutated_summary["journal_patterns"]["failure"]
            )
            with self.assertRaises(AssertionError):
                self.assert_confined(mutated_summary)

    def test_extractor_rejects_an_earlier_symlink_ancestor_and_mutant_reads_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            fixture = DriftFixture(Path(temp))
            outside_root = fixture.root / "outside-orchestrator"
            outside_run = outside_root / "runs" / "outside-run"
            outside_run.mkdir(parents=True)
            (outside_run / "journal.jsonl").write_text(
                '{"type":"run_started","run_id":"outside-run"}\n'
                '{"type":"decision","outcome":"must-not-be-read"}\n',
                encoding="utf-8",
            )
            (fixture.repo / ".codex-orchestrator").symlink_to(
                outside_root, target_is_directory=True
            )
            lexical_journal = (
                fixture.repo
                / ".codex-orchestrator"
                / "runs"
                / "outside-run"
                / "journal.jsonl"
            )

            controlled = subprocess.run(
                [
                    sys.executable,
                    str(EXTRACTOR),
                    "--repo",
                    str(fixture.repo),
                    "--revision",
                    "HEAD",
                    str(lexical_journal),
                ],
                cwd=fixture.repo,
                check=False,
                capture_output=True,
            )
            self.assertEqual(2, controlled.returncode)
            controlled_summary = json.loads(controlled.stdout)
            self.assertFalse(controlled_summary["available"])
            self.assertEqual("journal-path", controlled_summary["failure"])
            self.assertEqual({}, controlled_summary["decision_outcomes"])

            source = EXTRACTOR.read_text(encoding="utf-8")
            guard = "safe_path = confined_regular_file(path, repo)"
            self.assertEqual(1, source.count(guard))
            mutant = fixture.root / "journal-patterns-no-confinement.py"
            mutant.write_text(
                source.replace(guard, "safe_path = path", 1), encoding="utf-8"
            )
            mutated = subprocess.run(
                [
                    sys.executable,
                    str(mutant),
                    "--repo",
                    str(fixture.repo),
                    "--revision",
                    "HEAD",
                    str(lexical_journal),
                ],
                cwd=fixture.repo,
                check=False,
                capture_output=True,
            )
            self.assertEqual(0, mutated.returncode, mutated.stderr.decode())
            mutated_summary = json.loads(mutated.stdout)
            self.assertEqual(
                {"must-not-be-read": 1}, mutated_summary["decision_outcomes"]
            )
            with self.assertRaises(AssertionError):
                self.assertEqual({}, mutated_summary["decision_outcomes"])


if __name__ == "__main__":
    unittest.main()
