"""Integration tests for legacy and canonical route-vocabulary readers."""

from __future__ import annotations

import json
import runpy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts/forge"))

import route_vocab  # noqa: E402

from tests.test_repo_conformance import check_run, recorded_authority  # noqa: E402

from codex_orchestrator import journal, monitor  # noqa: E402

PATTERNS = ROOT / "scripts/forge/journal-patterns.py"
RUN_ID = "run-vocabulary"
TASK_ID = "task-vocabulary"


class VocabularyReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="forge-vocabulary-")
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name) / "repo"
        self.repo.mkdir()
        self.git("init", "--quiet")
        self.git("config", "user.email", "vocabulary@example.invalid")
        self.git("config", "user.name", "Vocabulary Tests")
        (self.repo / "system/codex/agents").mkdir(parents=True)
        (self.repo / "agents").mkdir()
        (self.repo / "system/codex/agents/implementer.toml").write_text(
            'model = "gpt-implementer"\nmodel_reasoning_effort = "high"\n'
            'sandbox_mode = "workspace-write"\n',
            encoding="utf-8",
        )
        (self.repo / "system/codex/agents/review-cheap.toml").write_text(
            'model = "gpt-review"\nmodel_reasoning_effort = "medium"\nsandbox_mode = "read-only"\n',
            encoding="utf-8",
        )
        (self.repo / "agents/review-final.md").write_text(
            "---\nmodel: fable\neffort: high\n---\n",
            encoding="utf-8",
        )
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", "route authorities")
        self.head = self.git("rev-parse", "HEAD").stdout.strip()
        self.run_dir = self.repo / ".codex-orchestrator/runs" / RUN_ID
        self.run_dir.mkdir(parents=True)
        self.records = self.execution_records()
        self.journal_path = self.run_dir / "journal.jsonl"
        self.write_journal(self.records)

    def git(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *arguments],
            cwd=self.repo,
            check=True,
            capture_output=True,
            text=True,
        )

    def execution_records(self) -> list[dict[str, object]]:
        spellings = (
            (
                "legacy-implementation",
                "codex",
                "implementation",
                "exec",
                "headless",
                "gpt-implementer",
                "high",
            ),
            (
                "legacy-reviewer-codex",
                "codex",
                "reviewer",
                "codex",
                "detached",
                "gpt-review",
                "medium",
            ),
            ("legacy-review-codex", "codex", "review", "exec", "read-only", "gpt-review", "medium"),
            (
                "legacy-review-codex-cli",
                "codex-cli",
                "review",
                "codex",
                "read-only",
                "gpt-review",
                "medium",
            ),
            ("legacy-review-claude", "claude", "review", "claude", "subagent", "fable", "high"),
            (
                "legacy-implementer",
                "codex",
                "implementer",
                "captured/events.jsonl",
                "workspace-write",
                "gpt-implementer",
                "high",
            ),
            (
                "legacy-implement",
                "codex",
                "implement",
                "exec",
                "headless",
                "gpt-implementer",
                "high",
            ),
            (
                "legacy-reviewer-claude",
                "claude",
                "reviewer",
                "agent-tool",
                "subagent",
                "fable",
                "high",
            ),
            ("legacy-plan", "codex", "plan", "codex", "read-only", "gpt-plan", "low"),
            (
                "canonical-implementer",
                "codex",
                "implementer",
                "exec",
                "workspace-write",
                "gpt-implementer",
                "high",
            ),
            (
                "canonical-review-cheap",
                "codex",
                "review-cheap",
                "exec",
                "read-only",
                "gpt-review",
                "medium",
            ),
            (
                "canonical-review-final",
                "claude",
                "review-final",
                "claude",
                "subagent",
                "fable",
                "high",
            ),
            (
                "canonical-plan",
                "codex",
                "plan",
                "canonical-plan/events.jsonl",
                "detached",
                "gpt-plan",
                "low",
            ),
            (
                "canonical-monitoring",
                "codex",
                "monitoring",
                "exec",
                "detached",
                "gpt-monitoring",
                "low",
            ),
            (
                "cross-provider-claude-implementation",
                "claude",
                "implementation",
                "claude",
                "subagent",
                "gpt-implementer",
                "high",
            ),
            (
                "cross-provider-codex-review-final",
                "codex",
                "review-final",
                "exec",
                "read-only",
                "gpt-review",
                "medium",
            ),
        )
        records: list[dict[str, object]] = [{"type": "run_started", "run_id": RUN_ID}]
        for index, values in enumerate(spellings, 1):
            agent, provider, role, source, mode, model, effort = values
            records.append(
                {
                    "type": "execution",
                    "run_id": RUN_ID,
                    "task": TASK_ID,
                    "agent": agent,
                    "execution": f"execution-{index:02d}",
                    "provider": provider,
                    "role": role,
                    "head": self.head,
                    "model": model,
                    "effort": effort,
                    "mode": mode,
                    "event_source": source,
                    "events": f"{agent}/execution-{index:02d}/events.jsonl",
                }
            )
        records.append(
            {
                "type": "verification",
                "task": TASK_ID,
                "criterion": "vocabulary fixture",
                "result": "passed",
            }
        )
        return records

    def write_journal(self, records: list[dict[str, object]], path: Path | None = None) -> None:
        target = path or self.journal_path
        target.write_text(
            "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
            encoding="utf-8",
        )

    def patterns(self) -> dict[str, object]:
        result = subprocess.run(
            [
                sys.executable,
                str(PATTERNS),
                "--repo",
                str(self.repo),
                "--revision",
                self.head,
                str(self.journal_path),
            ],
            cwd=self.repo,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        return json.loads(result.stdout)

    def test_pattern_and_conformance_readers_accept_both_vocabularies(self) -> None:
        extracted = self.patterns()
        routing = {row["agent"]: row for row in extracted["routing"]}
        unavailable = {agent for agent, row in routing.items() if row["status"] == "unavailable"}
        self.assertEqual(
            {
                "legacy-plan",
                "canonical-plan",
                "canonical-monitoring",
                "cross-provider-claude-implementation",
                "cross-provider-codex-review-final",
            },
            unavailable,
        )
        for agent in (
            "legacy-reviewer-codex",
            "legacy-review-codex",
            "legacy-review-codex-cli",
            "legacy-review-claude",
            "legacy-reviewer-claude",
            "canonical-review-cheap",
            "canonical-review-final",
        ):
            with self.subTest(agent=agent):
                self.assertEqual("matched", routing[agent]["status"])
        self.assertEqual(8, extracted["tasks"][0]["iterations"])
        authoritative_pairs = {
            ("codex", "implementer"),
            ("codex", "review-cheap"),
            ("claude", "review-final"),
        }
        expected_findings = []
        for line, record in enumerate(self.records, 1):
            provider = route_vocab.canonical_provider(record.get("provider"))
            role = route_vocab.canonical_role(record.get("role"), provider or "")
            if (
                provider in route_vocab.PROVIDER_IDS
                and role in route_vocab.ROLE_IDS
                and (provider, role) not in authoritative_pairs
            ):
                expected_findings.append(
                    f"journal line {line}: agent {record['agent']!r} "
                    f"raw role {record['role']!r}: no committed route authority "
                    f"for ({provider}, {role}) at {self.head}"
                )
        errors, findings = check_run(self.repo, self.run_dir)
        self.assertEqual([], errors)
        self.assertEqual(expected_findings, findings)

        codex_cli_line = next(
            line
            for line, record in enumerate(self.records, 1)
            if record.get("provider") == "codex-cli"
        )
        with mock.patch.object(
            route_vocab, "canonical_provider", side_effect=lambda raw: raw
        ):
            mutant_errors, mutant_findings = check_run(self.repo, self.run_dir)
        self.assertEqual(
            [f"journal line {codex_cli_line}: unknown Codex-cli execution role 'review'"],
            mutant_errors,
        )
        self.assertEqual(expected_findings, mutant_findings)

    def test_roles_without_authority_are_soft_and_unknown_role_is_hard(self) -> None:
        extracted = self.patterns()
        routing = {row["agent"]: row for row in extracted["routing"]}
        committed_route = runpy.run_path(str(PATTERNS))["committed_route"]
        negative_rows = [
            (line, record)
            for line, record in enumerate(self.records, 1)
            if str(record.get("agent", "")).startswith("cross-provider-")
        ]
        for line, record in negative_rows:
            provider = route_vocab.canonical_provider(record["provider"])
            role = route_vocab.canonical_role(record["role"], provider or "")
            with self.subTest(provider=provider, role=record["role"]):
                self.assertEqual("unavailable", routing[record["agent"]]["status"])
                self.assertIsNone(committed_route(self.repo, record))
                _authority, _path, error, finding = recorded_authority(
                    self.repo, self.head, record, line
                )
                self.assertIsNone(error)
                self.assertEqual(
                    f"journal line {line}: agent {record['agent']!r} "
                    f"raw role {record['role']!r}: no committed route authority "
                    f"for ({provider}, {role}) at {self.head}",
                    finding,
                )

        missing_pairs = (
            ("claude", "implementer"),
            ("claude", "review-cheap"),
            ("claude", "plan"),
            ("codex", "review-final"),
            ("codex", "plan"),
            ("codex", "monitoring"),
            ("claude", "monitoring"),
        )
        for offset, (provider, role) in enumerate(missing_pairs, 1):
            line = 900 + offset
            record = {
                "agent": f"unrouted-{provider}-{role}",
                "provider": provider,
                "role": role,
                "head": self.head,
            }
            with self.subTest(provider=provider, role=role):
                self.assertIsNone(committed_route(self.repo, record))
                _authority, _path, error, finding = recorded_authority(
                    self.repo, self.head, record, line
                )
                self.assertIsNone(error)
                self.assertEqual(
                    f"journal line {line}: agent {record['agent']!r} raw role {role!r}: "
                    f"no committed route authority for ({provider}, {role}) at {self.head}",
                    finding,
                )

        unknown = {
            "agent": "unknown-role",
            "provider": "codex",
            "role": "navigator",
            "head": self.head,
        }
        self.assertIsNone(committed_route(self.repo, unknown))
        _authority, _path, error, finding = recorded_authority(
            self.repo, self.head, unknown, 999
        )
        self.assertEqual(
            "journal line 999: unknown Codex execution role 'navigator'", error
        )
        self.assertIsNone(finding)

    def test_monitor_accepts_legacy_sources_but_still_rejects_unknowns(self) -> None:
        targets, errors = monitor.inflight_targets(self.run_dir)
        self.assertEqual([], errors)
        target_agents = {target.agent for target in targets}
        expected = {
            record["agent"]
            for record in self.records
            if record.get("type") == "execution"
            and record.get("event_source") not in {"claude", "agent-tool"}
        }
        self.assertEqual(expected, target_agents)

        unknown = self.repo / ".codex-orchestrator/runs/run-unknown"
        unknown.mkdir()
        record = next(dict(item) for item in self.records if item.get("type") == "execution")
        record["event_source"] = "ide"
        self.write_journal([record], unknown / "journal.jsonl")
        targets, errors = monitor.inflight_targets(unknown)
        self.assertEqual([], targets)
        self.assertEqual(1, len(errors))
        self.assertIn("unsupported event source", errors[0]["message"])

    def gate_profile_issues(self, raw_role: str) -> list[str]:
        records = [
            {
                "type": "execution",
                "agent": "agent-01",
                "execution": "execution-01",
                "task": TASK_ID,
                "role": raw_role,
                "_line": 1,
            },
            {
                "type": "execution_result",
                "agent": "agent-01",
                "execution": "execution-01",
                "task": TASK_ID,
                "status": "complete",
                "_line": 2,
            },
            {"type": "run_closed", "judgment": "passed", "_line": 3},
        ]
        issues: list[str] = []
        journal.check_gate_profile(records, issues, [], None)
        return issues

    def binding_correlation_issues(self, raw_role: str) -> list[str]:
        preimage: dict[str, object] = {
            "schema": journal.BINDING_SCHEMA,
            "source_record": {
                "chain_id": "c-2026-09-23T120000Z-abcd",
                "event_digest": "1" * 64,
            },
            "candidate": {"kind": "staged-diff-sha256", "value": "2" * 64},
            "review": None,
        }
        binding = {
            **preimage,
            "binding_id": journal._sha256(journal._canonical_json_bytes(preimage)),
        }
        records = [
            {
                "type": "run_started",
                "writer_contract": journal.WRITER_CONTRACT,
                "_line": 1,
            },
            {
                "type": "execution",
                "agent": "reviewer-01",
                "execution": "execution-01",
                "task": TASK_ID,
                "role": raw_role,
                "_line": 2,
            },
            {
                "type": "verification",
                "id": "check-01",
                "task": TASK_ID,
                "criterion": "vocabulary fixture",
                "result": "passed",
                "binding": binding,
                "_line": 3,
            },
            {
                "type": "execution_result",
                "agent": "reviewer-01",
                "execution": "execution-01",
                "task": TASK_ID,
                "status": "complete",
                "_line": 4,
            },
            {"type": "run_closed", "judgment": "passed", "_line": 5},
        ]
        issues: list[str] = []
        journal._check_binding_correlation(records, issues)
        return issues

    def test_journal_uses_raw_non_mutating_roles_at_both_call_sites(self) -> None:
        for role in ("review", "reviewer", "review-cheap", "review-final", "plan", "monitoring"):
            with self.subTest(role=role):
                self.assertEqual([], self.gate_profile_issues(role))
                self.assertEqual([], self.binding_correlation_issues(role))
        self.assertEqual(3, len(self.gate_profile_issues("implementer")))

        with mock.patch.object(
            journal.route_vocab,
            "is_non_mutating",
            side_effect=lambda role: role == "review",
        ):
            self.assertEqual(3, len(self.gate_profile_issues("reviewer")))
            issues = self.binding_correlation_issues("reviewer")
            self.assertEqual(1, len(issues))
            self.assertTrue(
                issues[0].startswith("binding '")
                and issues[0].endswith(
                    f"precedes the last mutating execution for task {TASK_ID!r}"
                ),
                issues,
            )
        source = (ROOT / "scripts/codex_orchestrator/journal.py").read_text(encoding="utf-8")
        self.assertEqual(2, source.count("route_vocab.is_non_mutating("))


if __name__ == "__main__":
    unittest.main()
