from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_SKILL = ROOT / "skills/report/SKILL.md"
REPORT_TEMPLATE = """# Report

## Summary

## Changes

## Orchestration Graph

## Consensus

## Final Results"""


class ReportSkillTests(unittest.TestCase):
    def test_report_structure_and_evidence_sources(self) -> None:
        skill = REPORT_SKILL.read_text(encoding="utf-8")
        self.assertIn(REPORT_TEMPLATE, skill)
        normalized = " ".join(skill.split())
        controls = (
            "### Gate Result",
            "### Risks / Follow-ups",
            "Mermaid `flowchart TD`",
            "`.forge/chains/`",
            "Git for delivered changes",
            "observed checks and chain records for gates and approvals",
            "A journal reference alone cannot establish a gate result.",
            "Reconcile numeric totals",
        )
        for control in controls:
            with self.subTest(control=control):
                self.assertIn(control, normalized)
                with self.assertRaises(AssertionError):
                    self.assertIn(control, normalized.replace(control, "DISABLED_CONTROL", 1))

    def test_report_uses_structural_validation_without_archive_precondition(self) -> None:
        skill = REPORT_SKILL.read_text(encoding="utf-8")
        self.assertIn('codex_orch_tools.py" validate', skill)
        self.assertIn("A `run_closed` record describes the reported outcome", skill)
        self.assertNotIn("validate --gates", skill)
        self.assertNotIn(".forge/history/runs/", skill)
        self.assertNotIn("run_closed.judgment", skill)
        self.assertIn("Report validation issues honestly.", skill)

    def test_report_does_not_promote_claims_to_results(self) -> None:
        skill = " ".join(REPORT_SKILL.read_text(encoding="utf-8").split())
        for control in (
            "Treat a handoff as a claim",
            "Surface missing or conflicting facts",
            "never infer a passing check, verdict, or terminal execution status",
            "Do not attribute initially dirty paths",
        ):
            with self.subTest(control=control):
                self.assertIn(control, skill)


if __name__ == "__main__":
    unittest.main()
