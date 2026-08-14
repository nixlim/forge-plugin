from __future__ import annotations

import json
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/forge/journal-patterns.py"
GATE3_PRODUCERS = (
    ROOT / "docs/orchestration-contract.md",
    ROOT / "skills/commit/SKILL.md",
    ROOT / "skills/worktree-merge/SKILL.md",
)


def canonical(value: dict) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode()


def run(*args: str, cwd: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        list(args), cwd=cwd, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )


class JournalPatternsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        run("git", "init", "-q", cwd=self.root)
        run("git", "config", "user.email", "forge@example.invalid", cwd=self.root)
        run("git", "config", "user.name", "Forge Test", cwd=self.root)
        (self.root / "system/codex/agents").mkdir(parents=True)
        (self.root / "agents").mkdir()
        (self.root / "system/codex/agents/implementer.toml").write_text(
            'model = "gpt-recorded"\nmodel_reasoning_effort = "high"\n'
        )
        (self.root / "system/codex/agents/review-cheap.toml").write_text(
            'model = "review-recorded"\nmodel_reasoning_effort = "medium"\n'
        )
        (self.root / "agents/review-final.md").write_text(
            "---\nmodel: claude-recorded\neffort: high\n---\n"
        )
        run("git", "add", ".", cwd=self.root)
        run("git", "commit", "-qm", "recorded routes", cwd=self.root)
        self.recorded_head = run("git", "rev-parse", "HEAD", cwd=self.root).stdout.decode().strip()
        (self.root / "system/codex/agents/implementer.toml").write_text(
            'model = "gpt-current"\nmodel_reasoning_effort = "low"\n'
        )
        run("git", "add", ".", cwd=self.root)
        run("git", "commit", "-qm", "current routes", cwd=self.root)
        self.current_head = run("git", "rev-parse", "HEAD", cwd=self.root).stdout.decode().strip()
        self.inputs = self.root / "inputs"
        self.inputs.mkdir()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_journal(self, name: str, records: list[dict]) -> Path:
        path = self.inputs / name
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
        return path

    def invoke(self, *journals: Path, script: Path = SCRIPT) -> subprocess.CompletedProcess[bytes]:
        return run(
            sys.executable, str(script), "--repo", str(self.root),
            "--revision", self.current_head, *(str(path) for path in journals),
            cwd=self.root,
        )

    def assert_shape(self, value: dict) -> None:
        self.assertEqual(
            {"available", "decision_outcomes", "diagnostics", "failure", "findings", "routing", "tasks"},
            set(value),
        )
        self.assertIsInstance(value["available"], bool)
        self.assertIsInstance(value["failure"], str)
        self.assertEqual({"by_reviewer_role", "by_severity"}, set(value["findings"]))
        for item in value["diagnostics"]:
            self.assertEqual({"count", "diagnostic"}, set(item))
            self.assertIsInstance(item["count"], int)
            self.assertNotIsInstance(item["count"], bool)
            self.assertGreater(item["count"], 0)
        for item in value["routing"]:
            self.assertEqual(
                {"agent", "committed_effort", "committed_model", "execution", "recorded_effort", "recorded_model", "run_id", "status"},
                set(item),
            )
            self.assertIn(item["status"], {"matched", "mismatched", "unavailable"})
        for item in value["tasks"]:
            self.assertEqual(
                {"block_to_pass_latency_ms", "iterations", "results", "run_id", "task"},
                set(item),
            )
            self.assertIsInstance(item["iterations"], int)
            self.assertGreaterEqual(item["iterations"], 0)

    def rich_records(self) -> list[dict]:
        return [
            {"type": "run_started", "run_id": "run-rich"},
            {"type": "decision", "outcome": "accepted", "diagnostic": " exact  diagnostic "},
            {"type": "decision", "outcome": "rejected"},
            {"type": "execution", "run_id": "run-rich", "task": "task-main", "execution": "execution-02", "agent": "impl", "provider": "codex", "role": "implementation", "head": self.recorded_head, "model": "wrong", "effort": "high"},
            {"type": "execution", "run_id": "run-rich", "task": "task-main", "execution": "execution-01", "agent": "impl", "provider": "codex", "role": "implementation", "head": self.recorded_head, "model": "gpt-recorded", "effort": "high"},
            {"type": "execution", "run_id": "run-rich", "task": "task-main", "execution": "execution-03", "agent": "review-final-like", "role": "review", "head": self.recorded_head, "model": "claude-recorded", "effort": "high"},
            {"type": "execution", "run_id": "run-rich", "task": "task-main", "execution": "review-01", "agent": "review-cheap", "provider": "codex", "role": "review", "head": self.recorded_head, "model": "review-recorded", "effort": "medium"},
            {"type": "execution", "run_id": "run-rich", "task": "task-main", "execution": "review-02", "agent": "review-cheap", "provider": "codex", "role": "review", "head": self.recorded_head, "model": "review-recorded", "effort": "medium"},
            {"type": "verification", "task": "task-main", "criterion": "gate-1", "result": "failed", "observation": "tool=mutation-testing policy; outcome=unavailable; diagnostic=forge: exact failure", "recorded_at": "2026-01-01T00:00:00Z"},
            {"type": "verification", "task": "task-main", "criterion": "gate-3: review-final verdict", "result": "failed", "observation": "BLOCK; 2 CRITICAL/MAJOR findings; severities CRITICAL=1,MAJOR=1,MINOR=1; reviewer review-cheap; iteration 2 of 8.", "recorded_at": "2026-01-01T00:00:01Z"},
            {"type": "verification", "task": "task-main", "criterion": "gate-3: review-final verdict", "result": "passed", "observation": "PASS", "recorded_at": "2026-01-01T00:00:42.125Z"},
        ]

    def rich_expected(self) -> dict:
        return {
            "available": True,
            "decision_outcomes": {"accepted": 1, "rejected": 1},
            "diagnostics": [
                {"count": 1, "diagnostic": " exact  diagnostic "},
                {"count": 1, "diagnostic": "BLOCK; 2 CRITICAL/MAJOR findings; severities CRITICAL=1,MAJOR=1,MINOR=1; reviewer review-cheap; iteration 2 of 8."},
                {"count": 1, "diagnostic": "forge: exact failure"},
            ],
            "failure": "",
            "findings": {
                "by_reviewer_role": {"review-cheap": 3},
                "by_severity": {"CRITICAL": 1, "MAJOR": 1, "MINOR": 1},
            },
            "routing": [
                {"agent": "impl", "committed_effort": "high", "committed_model": "gpt-recorded", "execution": "execution-01", "recorded_effort": "high", "recorded_model": "gpt-recorded", "run_id": "run-rich", "status": "matched"},
                {"agent": "impl", "committed_effort": "high", "committed_model": "gpt-recorded", "execution": "execution-02", "recorded_effort": "high", "recorded_model": "wrong", "run_id": "run-rich", "status": "mismatched"},
                {"agent": "review-final-like", "committed_effort": "", "committed_model": "", "execution": "execution-03", "recorded_effort": "high", "recorded_model": "claude-recorded", "run_id": "run-rich", "status": "unavailable"},
                {"agent": "review-cheap", "committed_effort": "medium", "committed_model": "review-recorded", "execution": "review-01", "recorded_effort": "medium", "recorded_model": "review-recorded", "run_id": "run-rich", "status": "matched"},
                {"agent": "review-cheap", "committed_effort": "medium", "committed_model": "review-recorded", "execution": "review-02", "recorded_effort": "medium", "recorded_model": "review-recorded", "run_id": "run-rich", "status": "matched"},
            ],
            "tasks": [{"block_to_pass_latency_ms": 41125, "iterations": 3, "results": ["failed", "failed", "passed"], "run_id": "run-rich", "task": "task-main"}],
        }

    def test_empty_corpus_is_available_canonical(self) -> None:
        result = self.invoke()
        expected = {"available": True, "decision_outcomes": {}, "diagnostics": [], "failure": "", "findings": {"by_reviewer_role": {}, "by_severity": {}}, "routing": [], "tasks": []}
        self.assertEqual(0, result.returncode)
        self.assertEqual(canonical(expected), result.stdout)
        self.assert_shape(json.loads(result.stdout))

    def test_exact_metrics_types_canonical_bytes_and_argument_invariance(self) -> None:
        rich = self.write_journal("z-rich.jsonl", self.rich_records())
        other = self.write_journal("a-other.jsonl", [
            {"type": "run_started", "run_id": "run-other"},
            {"type": "verification", "task": "task-z", "result": "skipped", "observation": "not run"},
        ])
        forward = self.invoke(rich, other)
        reverse = self.invoke(other, rich)
        expected = self.rich_expected()
        expected["tasks"] = [
            {"block_to_pass_latency_ms": None, "iterations": 0, "results": ["skipped"], "run_id": "run-other", "task": "task-z"},
            *expected["tasks"],
        ]
        self.assertEqual(0, forward.returncode)
        self.assertEqual(canonical(expected), forward.stdout)
        self.assertEqual(forward.stdout, reverse.stdout)
        self.assert_shape(json.loads(forward.stdout))

    def test_recorded_head_routing_does_not_use_current_head(self) -> None:
        path = self.write_journal("route.jsonl", self.rich_records()[:8])
        result = self.invoke(path)
        self.assertEqual(0, result.returncode)
        rows = json.loads(result.stdout)["routing"]
        self.assertEqual(["matched", "mismatched", "unavailable", "matched", "matched"], [row["status"] for row in rows])
        self.assertTrue(all(row["committed_model"] != "gpt-current" for row in rows))

    def test_legacy_run_started_id_and_stable_malformed_failure(self) -> None:
        legacy = self.write_journal("legacy.jsonl", [
            {"type": "run_started", "id": "run-legacy"},
            {"type": "verification", "task": "task", "result": "passed"},
        ])
        result = self.invoke(legacy)
        self.assertEqual(0, result.returncode)
        self.assertEqual("run-legacy", json.loads(result.stdout)["tasks"][0]["run_id"])
        malformed = self.inputs / "bad.jsonl"
        malformed.write_text('{"type":"run_started","run_id":"bad"}\n{bad\n')
        first = self.invoke(malformed)
        second = self.invoke(malformed)
        expected = {"available": False, "decision_outcomes": {}, "diagnostics": [], "failure": "journal-json", "findings": {"by_reviewer_role": {}, "by_severity": {}}, "routing": [], "tasks": []}
        self.assertEqual(2, first.returncode)
        self.assertEqual(canonical(expected), first.stdout)
        self.assertEqual(first.stdout, second.stdout)

    def load_namespace(self, source: str) -> dict:
        namespace = {"__name__": "journal_patterns_mutant", "__file__": str(SCRIPT)}
        exec(compile(source, str(SCRIPT), "exec"), namespace)
        return namespace

    def latency(self, records: list[dict]) -> int | None:
        return self.load_namespace(SCRIPT.read_text())["latency_ms"](records)

    def test_gate3_block_to_next_gate3_pass_latency(self) -> None:
        records = [
            {"criterion": "suite", "result": "failed", "recorded_at": "2026-01-01T00:00:00Z"},
            {"criterion": "suite", "result": "passed", "recorded_at": "2026-01-01T00:00:10Z"},
            {"criterion": "gate-3: review-final verdict", "result": "failed", "recorded_at": "2026-01-01T00:00:20Z"},
            {"criterion": "gate-3: review-final verdict", "result": "passed", "recorded_at": "2026-01-01T00:00:40.125Z"},
        ]
        self.assertEqual(20125, self.latency(records))

    def test_non_gate3_failures_emit_no_block_latency(self) -> None:
        records = [
            {"criterion": "suite", "result": "failed", "recorded_at": "2026-01-01T00:00:00Z"},
            {"criterion": "first-pass review", "result": "passed", "recorded_at": "2026-01-01T00:00:10Z"},
        ]
        self.assertIsNone(self.latency(records))

    def test_gate3_block_without_later_gate3_pass_emits_no_latency(self) -> None:
        records = [
            {"criterion": "gate-3: review-final verdict", "result": "failed", "recorded_at": "2026-01-01T00:00:01Z"},
            {"criterion": "suite", "result": "passed", "recorded_at": "2026-01-01T00:00:10Z"},
        ]
        self.assertIsNone(self.latency(records))

    def test_each_metric_control_mutation_is_detected(self) -> None:
        journal = self.write_journal("rich.jsonl", self.rich_records())
        source = SCRIPT.read_text()
        expected = self.rich_expected()
        mutations = [
            ("outcome_counts[outcome] += 1", "outcome_counts[outcome] += 0"),
            ("diagnostic_counts[diagnostic] += 1", "diagnostic_counts[diagnostic] += 0"),
            ('results = [record["result"] for record in records]', "results = []"),
            ("review_execution_counts[(run_id, task)]", "0"),
            ('"block_to_pass_latency_ms": latency_ms(records),', '"block_to_pass_latency_ms": None,'),
            (
                '        if record.get("criterion") != "gate-3: review-final verdict":\n            continue',
                "",
            ),
            ("committed_model == recorded_model", "False and committed_model == recorded_model"),
        ]
        for needle, replacement in mutations:
            with self.subTest(needle=needle):
                self.assertEqual(1, source.count(needle))
                mutant_source = source.replace(needle, replacement, 1)
                actual = self.load_namespace(mutant_source)["extract"](
                    [journal], self.root, self.current_head
                )
                self.assertNotEqual(canonical(expected), canonical(actual))
        canonical_anchor = 'separators=(",", ":")'
        self.assertEqual(1, source.count(canonical_anchor))
        mutant = self.load_namespace(
            source.replace(canonical_anchor, 'separators=(", ", ": ")', 1)
        )
        self.assertNotEqual(canonical(expected), mutant["canonical_bytes"](expected))

    def test_standard_journal_grammar_controls_are_discriminating(self) -> None:
        journal = self.write_journal("rich.jsonl", self.rich_records())
        source = SCRIPT.read_text()
        expected = self.rich_expected()
        mutations = [
            ("embedded_diagnostic = observation_diagnostic(record)", "embedded_diagnostic = None"),
            ("or gate3_findings is not None", "or False"),
            ("severity_counts[severity] += count", "severity_counts[severity] += 0"),
            ("reviewer_counts[gate3_reviewer] += sum(gate3_counts.values())", "reviewer_counts[gate3_reviewer] += 0"),
        ]
        for needle, replacement in mutations:
            with self.subTest(needle=needle):
                self.assertEqual(1, source.count(needle))
                actual = self.load_namespace(source.replace(needle, replacement, 1))["extract"](
                    [journal], self.root, self.current_head
                )
                self.assertNotEqual(canonical(expected), canonical(actual))

    def test_legacy_gate3_does_not_invent_a_reviewer_role(self) -> None:
        journal = self.write_journal(
            "legacy-gate3.jsonl",
            [
                {"type": "run_started", "run_id": "run-legacy-gate3"},
                {
                    "type": "verification",
                    "task": "task-main",
                    "criterion": "gate-3: review-final verdict",
                    "result": "failed",
                    "observation": (
                        "BLOCK; 1 CRITICAL/MAJOR findings; iteration 1 of 8."
                    ),
                },
            ],
        )
        source = SCRIPT.read_text(encoding="utf-8")

        def reviewer_counts(namespace: dict[str, object]) -> dict[str, int]:
            return namespace["extract"](
                [journal], self.root, self.current_head
            )["findings"]["by_reviewer_role"]

        expected: dict[str, int] = {}
        self.assertEqual(expected, reviewer_counts(self.load_namespace(source)))

        needle = "return counts, None"
        self.assertEqual(1, source.count(needle))
        mutant = self.load_namespace(
            source.replace(needle, 'return counts, "review-final"', 1)
        )
        self.assertNotEqual(expected, reviewer_counts(mutant))

    def test_gate3_producers_share_the_lossless_observation_grammar(self) -> None:
        grammar = (
            "`<PASS|BLOCK>; <critical-plus-major-count> CRITICAL/MAJOR findings; "
            "severities CRITICAL=<count>,MAJOR=<count>,MINOR=<count>; reviewer "
            "<review-cheap|review-final>; iteration <number> of 8.`"
        )

        def assert_contract(text: str) -> None:
            self.assertIn(grammar, " ".join(text.split()))

        for path in GATE3_PRODUCERS:
            with self.subTest(path=path):
                source = path.read_text(encoding="utf-8")
                normalized = " ".join(source.split())
                assert_contract(normalized)
                with self.assertRaises(AssertionError):
                    assert_contract(
                        normalized.replace(grammar, "DISABLED GATE3 GRAMMAR", 1)
                    )

    def test_input_sort_mutant_is_detected(self) -> None:
        first = self.write_journal("z.jsonl", [
            {"type": "run_started", "run_id": "same"},
            {"type": "verification", "task": "task", "result": "failed"},
        ])
        second = self.write_journal("a.jsonl", [
            {"type": "run_started", "run_id": "same"},
            {"type": "verification", "task": "task", "result": "passed"},
        ])
        source = SCRIPT.read_text()
        sort_anchor = textwrap.dedent('''\
            journals = sorted(
                    (Path(path) for path in paths), key=lambda path: str(path).encode("utf-8")
                )''').strip()
        self.assertIn(sort_anchor, source)
        mutant_source = source.replace(
            sort_anchor, "journals = list(Path(path) for path in paths)", 1
        )
        namespace = self.load_namespace(mutant_source)
        forward = namespace["extract"]([first, second], self.root, self.current_head)
        reverse = namespace["extract"]([second, first], self.root, self.current_head)
        self.assertNotEqual(canonical(forward), canonical(reverse))

if __name__ == "__main__":
    unittest.main()
