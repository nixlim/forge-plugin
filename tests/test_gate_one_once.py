"""Gate 1 once per candidate (Revision 17): evidence predicates and committed policy pins.

Covers the chain_core predicates that decide when Gate 1 is complete and when a candidate
is docs-class, each with the control disabled in memory, plus the committed policy surfaces
this revision changed: the mypy stack cell and its tracked baseline, and the fast-tier row.
"""

from __future__ import annotations

import copy
import json
import re
import unittest
from pathlib import Path
from unittest import mock

from tests._cli_loader import load_script, package_module

ROOT = Path(__file__).resolve().parents[1]
CHAIN_CORE = package_module("chain_core")
GATE_EVIDENCE = package_module("chain_core._gate_evidence")
POLICY_BYTES = (ROOT / "forge-project.md").read_bytes()

CANDIDATE = "a" * 64
OTHER = "b" * 64


def docs_evidence(path: str = "docs/guide.md", **overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "path": path,
        "status": "M",
        "categories": ["docs"],
        "matched_rows": [{"tier": "fast", "pattern": "docs/**"}],
        "formatting_only": False,
        "formatting_decision": "line-shape",
        "dependency_decision": [],
        "unknown_manifest_floor": False,
        "control_floor": False,
        "trigger_matches": [],
        "path_tier": "fast",
    }
    record.update(overrides)
    return record


def state_with(
    paths: list[str],
    evidence: list[dict[str, object]],
    *,
    control: bool = False,
    gate_one=None,
    classification_candidate: str = CANDIDATE,
) -> dict[str, object]:
    steps: dict[str, object] = {
        "classification": [{"candidate": classification_candidate, "result": "passed"}],
    }
    if gate_one is not None:
        steps["gate-1"] = gate_one
    return {
        "paths": list(paths),
        "candidate": {"sha256": CANDIDATE},
        "tier": {
            "control": control,
            "categories": ["docs"],
            "derived": "fast",
            "effective": "fast",
            "declared": None,
            "classification": {"paths": evidence},
        },
        "steps": steps,
    }


class GateOneCompleteTests(unittest.TestCase):
    def test_one_current_passed_run_completes_the_gate(self) -> None:
        passed = {"candidate": CANDIDATE, "result": "passed"}
        state = state_with(["docs/guide.md"], [docs_evidence()], gate_one=[passed])
        self.assertTrue(CHAIN_CORE._gate_one_complete(state))

    def test_no_run_or_only_foreign_runs_leave_the_gate_incomplete(self) -> None:
        for runs in (None, [], [{"candidate": OTHER, "result": "passed"}], "malformed"):
            with self.subTest(runs=runs):
                state = state_with(["docs/guide.md"], [docs_evidence()], gate_one=runs)
                self.assertFalse(CHAIN_CORE._gate_one_complete(state))

    def test_newest_current_run_decides_not_an_older_pass(self) -> None:
        runs = [
            {"candidate": CANDIDATE, "result": "passed"},
            {"candidate": CANDIDATE, "result": "failed"},
        ]
        state = state_with(["docs/guide.md"], [docs_evidence()], gate_one=runs)
        self.assertFalse(CHAIN_CORE._gate_one_complete(state))
        runs.append({"candidate": CANDIDATE, "result": "passed"})
        self.assertTrue(CHAIN_CORE._gate_one_complete(state))

    def test_docs_class_skip_record_completes_only_with_the_fixed_reason(self) -> None:
        skip = {
            "candidate": CANDIDATE,
            "result": "skipped",
            "reason": CHAIN_CORE.DOCS_CLASS_SKIP_REASON,
        }
        state = state_with(["docs/guide.md"], [docs_evidence()], gate_one=[skip])
        self.assertTrue(CHAIN_CORE._gate_one_complete(state))
        for mutant in (
            {**skip, "reason": "operator accepts test omission"},
            {**skip, "reason": None},
            {**skip, "candidate": OTHER},
            {**skip, "result": "passed-ish"},
        ):
            with self.subTest(mutant=mutant):
                state = state_with(["docs/guide.md"], [docs_evidence()], gate_one=[mutant])
                self.assertFalse(CHAIN_CORE._gate_one_complete(state))

    def test_operator_skip_still_completes_the_gate(self) -> None:
        state = state_with(["src/app.py"], [docs_evidence("src/app.py", categories=["python"])])
        state["steps"]["user_skips"] = {"gate-1": {"directed_by": "operator", "reason": "x"}}
        self.assertTrue(CHAIN_CORE._gate_one_complete(state))

    def test_required_steps_list_gate_one_exactly_once(self) -> None:
        policy = package_module("policy").parse_policy("worktree", POLICY_BYTES)
        context = mock.Mock(policy=policy)
        state = state_with(["docs/guide.md"], [docs_evidence()])
        steps = CHAIN_CORE._required_steps(context, state)
        self.assertEqual(steps.count("gate-1"), 1)
        self.assertEqual(steps[0], "changelog")
        self.assertEqual(steps[1], "gate-1")


class DocsClassCandidateTests(unittest.TestCase):
    def test_all_docs_paths_with_current_classification_qualify(self) -> None:
        state = state_with(
            ["CHANGELOG.md", "docs/guide.md"],
            [docs_evidence("CHANGELOG.md", matched_rows=[]), docs_evidence()],
        )
        self.assertTrue(CHAIN_CORE._docs_class_candidate(state))

    def test_each_disqualifier_refuses(self) -> None:
        base = state_with(
            ["docs/guide.md", "docs/other.md"],
            [docs_evidence(), docs_evidence("docs/other.md")],
        )
        self.assertTrue(CHAIN_CORE._docs_class_candidate(base))
        mutants: dict[str, dict[str, object]] = {}

        def mutant(name: str):
            state = copy.deepcopy(base)
            mutants[name] = state
            return state

        def evidence(name: str) -> list[dict[str, object]]:
            return mutant(name)["tier"]["classification"]["paths"]

        mutant("control tier")["tier"]["control"] = True
        evidence("control floor on one path")[1]["control_floor"] = True
        evidence("second category")[0]["categories"] = ["docs", "control"]
        evidence("no category")[0]["categories"] = []
        evidence("trigger match")[1]["trigger_matches"] = ["docs/specs/**"]
        evidence("path missing from evidence").pop()
        evidence("extra evidence path").append(docs_evidence("docs/third.md"))
        mutant("empty evidence")["tier"]["classification"]["paths"] = []
        mutant("evidence not a list")["tier"]["classification"]["paths"] = {"x": True}
        mutant("classification missing")["tier"].pop("classification")
        stale = {"candidate": OTHER, "result": "passed"}
        mutant("stale classification")["steps"]["classification"] = [stale]
        failed = {"candidate": CANDIDATE, "result": "failed"}
        mutant("failed classification")["steps"]["classification"] = [failed]
        for name, state in mutants.items():
            with self.subTest(disqualifier=name):
                self.assertFalse(CHAIN_CORE._docs_class_candidate(state))

    def test_predicate_is_the_load_bearing_switch_for_the_skip_record(self) -> None:
        # With the predicate disabled in memory the skip writer refuses; it never
        # records a docs-class skip on its own judgment.
        state = state_with(["docs/guide.md"], [docs_evidence()])
        state["chain_id"] = "c-fixture"
        engine_checks = package_module("engine._gate_checks")
        with mock.patch.object(CHAIN_CORE, "_docs_class_candidate", return_value=False):
            with self.assertRaises(package_module("envelope").Refusal) as caught:
                engine_checks._record_docs_class_gate_one_skip(mock.Mock(), state)
        self.assertIn("not docs-class", caught.exception.message)
        self.assertNotIn("gate-1", state["steps"])


class CommittedPolicyPinsTests(unittest.TestCase):
    def test_stack_validations_carry_the_conformance_and_type_baseline_cells(self) -> None:
        policy = package_module("policy").parse_policy("worktree", POLICY_BYTES)
        self.assertEqual(len(policy.stack_commands), 3)
        self.assertIn("python3 -m unittest tests.test_repo_conformance", policy.stack_commands[0])
        cell = policy.stack_commands[1]
        self.assertTrue(cell.startswith('python3 - "$@" <<\'PY\''))
        self.assertIn('".refactor/type-baseline.json"', cell)
        self.assertIn('MYPYPATH="scripts:scripts/forge"', cell)
        self.assertIn('"scripts/forge/forge_cli"', cell)
        self.assertIn('if not any(path.endswith(".py") for path in sys.argv[1:]):', cell)
        # Keys normalize embedded line references; counts ratchet per key.
        self.assertIn('re.sub(r"\\bline \\d+\\b", "line N"', cell)
        self.assertIn("excess = current - allowed", cell)
        self.assertIn("raise SystemExit(1 if excess else 0)", cell)

    def test_docs_contract_cell_lists_every_module_that_reads_repository_prose(self) -> None:
        policy = package_module("policy").parse_policy("worktree", POLICY_BYTES)
        cell = policy.stack_commands[2]
        self.assertIn("docs contracts: no docs-class path in the candidate", cell)
        listed = set(re.findall(r'"(tests\.test_\w+)"', cell))
        self.assertTrue(listed)
        prose = re.compile(
            r'ROOT / "(?:README\.md|OPERATIONS\.md|UPSTREAM|LICENSE'
            r'|docs/orchestration-contract\.md)"|"docs/orchestration-contract\.md"'
        )
        readers = {
            f"tests.{path.stem}"
            for path in sorted((ROOT / "tests").glob("test_*.py"))
            if prose.search(path.read_text(encoding="utf-8"))
        }
        self.assertTrue(readers)
        self.assertLessEqual(readers, listed, sorted(readers - listed))
        for module in sorted(listed):
            self.assertTrue((ROOT / "tests" / f"{module.split('.')[1]}.py").is_file(), module)

    def test_type_baseline_is_tracked_and_keyed_by_code_and_message(self) -> None:
        baseline = json.loads((ROOT / ".refactor/type-baseline.json").read_text(encoding="utf-8"))
        self.assertEqual(baseline["pkg"], "scripts/forge/forge_cli")
        self.assertEqual(baseline["tool"], "mypy")
        self.assertRegex(baseline["ref"], r"^[0-9a-f]{40}$")
        self.assertIsInstance(baseline["errors"], dict)
        self.assertEqual(baseline["total"], sum(baseline["errors"].values()))
        self.assertTrue(all("::" in key for key in baseline["errors"]))

    def test_changelog_is_in_the_fast_tier_row(self) -> None:
        risk_tier = load_script("risk_tier_gate_once", ROOT / "scripts/forge/risk_tier.py")
        policy = risk_tier.parse_policy(POLICY_BYTES.decode("utf-8"), "0" * 40)
        fast_patterns = [patterns for tier, patterns in policy.tier_rows if tier == "fast"]
        self.assertEqual(len(fast_patterns), 1)
        self.assertIn("CHANGELOG.md", fast_patterns[0])
        self.assertIn("docs/**", fast_patterns[0])

    def test_gate_evidence_predicates_live_in_their_own_module(self) -> None:
        names = (
            "_user_skip",
            "_gate_one_complete",
            "_docs_class_candidate",
            "_latest_current_pass",
            "_gate_satisfied",
        )
        for name in names:
            with self.subTest(name=name):
                self.assertIs(getattr(CHAIN_CORE, name), getattr(GATE_EVIDENCE, name))
        self.assertFalse(hasattr(package_module("engine"), "_void_mismatched_gate_one_pair"))


if __name__ == "__main__":
    unittest.main()
