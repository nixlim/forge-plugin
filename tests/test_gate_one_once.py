"""Gate 1 once per candidate (Revision 17): evidence predicates and committed policy pins.

Covers the chain_core predicates that decide when Gate 1 is complete and when a candidate
is docs-class, each with the control disabled in memory, plus the committed policy surfaces
this revision changed: the mypy stack cell and its tracked baseline, and the fast-tier row.
"""

from __future__ import annotations

import copy
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests._cli_loader import load_script, package_module

ROOT = Path(__file__).resolve().parents[1]
CHAIN_CORE = package_module("chain_core")
GATE_EVIDENCE = package_module("chain_core._gate_evidence")
POLICY_BYTES = (ROOT / "forge-project.md").read_bytes()
RISK_TIER = ROOT / "scripts/forge/risk_tier.py"
TYPE_BASELINE = ".refactor/type-baseline.json"
TYPE_BASELINE_TRIGGER_ROW = (
    "| `.refactor/type-baseline.json` | binding review and explicit operator approval "
    "(type-check ratchet strength authority) |"
)

CANDIDATE = "a" * 64
OTHER = "b" * 64


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    ).stdout.strip()


def classifier_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(
            None,
            (str(ROOT / "scripts/forge"), environment.get("PYTHONPATH", "")),
        )
    )
    return environment


def classify_type_baseline(
    policy_bytes: bytes,
) -> tuple[subprocess.CompletedProcess[str], dict[str, object] | None]:
    with tempfile.TemporaryDirectory() as directory:
        repo = Path(directory)
        git(repo, "init", "-q")
        git(repo, "config", "user.name", "Forge Test")
        git(repo, "config", "user.email", "forge@example.test")
        (repo / "forge-project.md").write_bytes(policy_bytes)
        baseline = repo / TYPE_BASELINE
        baseline.parent.mkdir(parents=True)
        baseline.write_text('{"revision": 1}\n', encoding="utf-8")
        git(repo, "add", "forge-project.md", TYPE_BASELINE)
        git(repo, "commit", "-qm", "policy")
        policy_sha = git(repo, "rev-parse", "HEAD")
        baseline.write_text('{"revision": 2}\n', encoding="utf-8")
        git(repo, "add", TYPE_BASELINE)
        result = subprocess.run(
            [
                sys.executable,
                str(RISK_TIER),
                "--repo",
                str(repo),
                "--policy-sha",
                policy_sha,
                "--staged",
            ],
            cwd=repo,
            env=classifier_environment(),
            capture_output=True,
            text=True,
            timeout=30,
        )
    payload = json.loads(result.stdout) if result.stdout else None
    return result, payload


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

    def test_type_baseline_is_control_class_and_has_an_approval_trigger(self) -> None:
        risk_tier = load_script("risk_tier_type_baseline_pin", RISK_TIER)
        text = POLICY_BYTES.decode("utf-8")
        policy = risk_tier.parse_policy(text, "0" * 40)
        control_patterns = [
            patterns for category, patterns in policy.category_rows if category == "control"
        ]
        self.assertEqual(len(control_patterns), 1)
        self.assertIn(TYPE_BASELINE, control_patterns[0])
        trigger_lines = risk_tier.regions(text)["project-triggers"].splitlines()
        self.assertEqual(trigger_lines.count(TYPE_BASELINE_TRIGGER_ROW), 1)

    def test_type_baseline_control_pattern_sets_the_hard_tier(self) -> None:
        result, payload = classify_type_baseline(POLICY_BYTES)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["derived_tier"], "hard")
        paths = payload["paths"]
        self.assertIsInstance(paths, list)
        self.assertEqual(len(paths), 1)
        path = paths[0]
        self.assertIs(path["control_floor"], True)
        self.assertIn("control", path["categories"])

        marker = b", `.refactor/type-baseline.json`"
        self.assertEqual(POLICY_BYTES.count(marker), 1)
        mutant_policy = POLICY_BYTES.replace(marker, b"", 1)
        mutant_result, mutant = classify_type_baseline(mutant_policy)
        self.assertEqual(mutant_result.returncode, 0, mutant_result.stderr)
        self.assertIsNotNone(mutant)
        assert mutant is not None
        self.assertEqual(mutant["derived_tier"], "standard")
        mutant_paths = mutant["paths"]
        self.assertIsInstance(mutant_paths, list)
        self.assertEqual(len(mutant_paths), 1)
        mutant_path = mutant_paths[0]
        self.assertIs(mutant_path["control_floor"], False)
        self.assertEqual(mutant_path["categories"], ["config"])

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
