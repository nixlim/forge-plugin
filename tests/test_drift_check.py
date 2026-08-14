from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
DRIFT_CHECK = ROOT / "scripts/forge/drift-check.sh"
DRIFT_STALENESS = ROOT / "scripts/forge/drift-staleness.sh"
MUTATION_HELPER = ROOT / "scripts/forge/run-scoped-mutation.py"
EMIT_EVENT = ROOT / "scripts/forge/emit-decision-event.py"
NOW = "2026-08-11T12:00:00Z"
CONFIG_WARNING = (
    "forge: malformed drift-config — using defaults "
    "(cadence: 14d, retention: forever, event-retention: 400d)"
)
STALE_WARNING = "forge: drift report stale — run /forge:drift"


def region(name: str, body: str) -> str:
    return (
        f"<!-- FORGE:REGION {name} BEGIN -->\n"
        f"{body.rstrip()}\n"
        f"<!-- FORGE:REGION {name} END -->"
    )


def policy_text(
    *,
    file_categories: str | None = None,
    stack_validations: str | None = None,
    gate_one: str | None = None,
    mutation: str | None = None,
    invariants: str = "",
    drift_config: str | None = None,
) -> str:
    bodies = {
        "project-overview": "Fixture project.",
        "file-categories": file_categories
        or "| Category | File patterns |\n|---|---|\n| `fixture` | `*` |",
        "stack-validations": stack_validations
        or "Fixture validation:\n\n```bash\ntrue\n```",
        "gate1-test-command": gate_one or "```bash\ntrue\n```",
        "changelog-policy": "Fixture changelog policy.",
        "review-prompt-project-focus": "Fixture review focus.",
        "project-triggers": "Fixture triggers.",
        "completeness-project-items": "Fixture completeness items.",
        "agent-project-context": "Fixture context.",
        "mutation-testing": mutation
        or "No mutation tool available for fixture — assertion-quality fallback only.",
        "invariants": invariants,
        "risk-tiers": "Fixture risk tiers.",
        "drift-config": drift_config
        or "cadence: 14d\nretention: forever\nevent-retention: 400d",
        "trigger-paths": "Fixture trigger paths.",
    }
    return "\n\n".join(region(name, body) for name, body in bodies.items()) + "\n"


class DriftFixture:
    def __init__(self, root: Path, **policy_kwargs: str) -> None:
        self.root = root
        self.repo = root / "repo"
        self.plugin = root / "plugin"
        self.eval_log = root / "eval.log"
        self.repo.mkdir(parents=True)
        (self.plugin / "scripts/forge").mkdir(parents=True)
        shutil.copy2(MUTATION_HELPER, self.plugin / "scripts/forge/run-scoped-mutation.py")
        shutil.copy2(EMIT_EVENT, self.plugin / "scripts/forge/emit-decision-event.py")
        self._script(
            "run-evals.sh",
            """#!/bin/sh
[ "${STRICT:-}" = 1 ] || exit 91
printf 'STRICT=%s\\n' "${STRICT:-}" >> "${FORGE_EVAL_LOG}"
exit "${FORGE_TEST_EVAL_EXIT:-0}"
""",
        )
        self._script(
            "acquire-commit-lock.sh",
            """#!/bin/sh
status="${FORGE_TEST_ACQUIRE_EXIT:-0}"
[ "$status" = 0 ] || exit "$status"
[ "$#" -eq 1 ] || exit 64
lock_file="$PWD/$1"
mkdir -p "$(dirname "$lock_file")" || exit 1
(set -C; : > "$lock_file") 2>/dev/null || exit 1
""",
        )
        self._script(
            "release-commit-lock.sh",
            """#!/bin/sh
status="${FORGE_TEST_RELEASE_EXIT:-0}"
[ "$status" = 0 ] || exit "$status"
[ "$#" -eq 1 ] || exit 64
lock_file="$PWD/$1"
[ -f "$lock_file" ] || exit 1
[ -z "${FORGE_TEST_RELEASE_READY:-}" ] || : > "$FORGE_TEST_RELEASE_READY" || exit 1
rm -f -- "$lock_file"
""",
        )
        self.git("init", "-q")
        self.git("config", "user.name", "Drift Fixture")
        self.git("config", "user.email", "drift@example.invalid")
        self.write(".gitignore", ".forge/tmp/\n")
        self.write(".forge-manifest", "fixture\n")
        self.write("docs/spec.md", "committed fixture\n")
        policy = policy_text(**policy_kwargs)
        self.write("forge-project.md", policy)
        self.write(
            "AGENTS.md",
            "<!-- FORGE:BEGIN -->\n" + policy.rstrip("\n") + "\n<!-- FORGE:END -->\n",
        )
        self.write("CLAUDE.md", "@forge-project.md\n")
        self.commit("fixture policy")

    def _script(self, name: str, content: str) -> None:
        path = self.plugin / "scripts/forge" / name
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)

    def write(self, relative: str, content: str) -> Path:
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=self.repo,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        return result.stdout.strip()

    def commit(self, message: str) -> str:
        self.git("add", "--all")
        self.git("commit", "-qm", message)
        return self.git("rev-parse", "HEAD")

    def invoke(self, *, now: str = NOW, extra_env: dict[str, str] | None = None):
        env = {
            **os.environ,
            "CLAUDE_PLUGIN_ROOT": str(self.plugin),
            "FORGE_DRIFT_NOW": now,
            "FORGE_EVAL_LOG": str(self.eval_log),
        }
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            ["bash", str(DRIFT_CHECK)],
            cwd=self.repo,
            env=env,
            capture_output=True,
            check=False,
        )

    def staleness(self, *, now: str = NOW):
        return subprocess.run(
            ["bash", str(DRIFT_STALENESS)],
            cwd=self.repo,
            env={**os.environ, "FORGE_DRIFT_NOW": now},
            capture_output=True,
            check=False,
        )

    def event(self, at: str, event: str, candidate: str = "") -> dict[str, str]:
        return {
            "at": at,
            "candidate": candidate,
            "event": event,
            "policy_sha": self.git("rev-parse", "HEAD"),
            "reason": "",
            "surface": "forge:commit",
        }

    def write_events(self, events: list[dict[str, str]], *, malformed: bool = False) -> Path:
        path = self.repo / ".forge/tmp/decisions/events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps(item, sort_keys=True, separators=(",", ":")) for item in events]
        if malformed:
            lines.append("{malformed")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path


class DriftCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.temp = Path(self.temporary.name)

    def fixture(self, **kwargs: str) -> DriftFixture:
        return DriftFixture(self.temp, **kwargs)

    def assert_canonical(self, fixture: DriftFixture, result, now: str = NOW) -> dict:
        self.assertTrue(result.stdout.endswith(b"\n"), result.stdout)
        self.assertEqual(result.stdout.count(b"\n"), 1, result.stdout)
        parsed = json.loads(result.stdout)
        self.assertEqual(
            result.stdout,
            (json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode(),
        )
        target = fixture.repo / ".forge/tmp/drift" / f"{now[:10]}.json"
        self.assertEqual(target.read_bytes(), result.stdout)
        self.assertEqual(
            set(parsed),
            {"checks", "findings", "generated_at", "policy_sha", "schema_version", "status", "telemetry"},
        )
        self.assertEqual(parsed["schema_version"], 1)
        for item in parsed["checks"]:
            self.assertEqual(set(item), {"check", "duration_ms", "outcome", "summary"})
            self.assertIs(type(item["duration_ms"]), int)
            self.assertGreaterEqual(item["duration_ms"], 0)
        return parsed

    def assert_empty_telemetry(self, value: dict) -> None:
        self.assertEqual(
            value,
            {
                "available": False,
                "eligible_commits": 0,
                "event_prune": {"entries_removed": 0, "failure": "", "new_oldest_at": ""},
                "fast_allowed": 0,
                "fast_denied_eligibility": 0,
                "fast_denied_policy": 0,
                "guard_denies": 0,
                "halt_events": 0,
                "review_blocks": 0,
                "user_skips": 0,
                "window_end": "",
                "window_start": "",
            },
        )

    def normalized_summary(self, value: dict) -> dict:
        """Normalize only values that a black-box run cannot make literal."""
        normalized = json.loads(json.dumps(value))
        normalized["policy_sha"] = "<policy-sha>"
        for item in normalized["checks"]:
            item["duration_ms"] = 0
        return normalized

    def test_exit_zero_literal_shape_canonical_output_and_strict_inventory(self) -> None:
        for block_present in (False, True):
            with self.subTest(block_present=block_present):
                fixture = DriftFixture(self.temp / f"exit-zero-{block_present}")
                block = fixture.repo / ".forge/tmp/drift-block"
                marker = b"operator-owned critical drift block\n"
                if block_present:
                    block.parent.mkdir(parents=True, exist_ok=True)
                    block.write_bytes(marker)
                result = fixture.invoke()
                self.assertEqual(result.returncode, 0, result.stderr.decode())
                summary = self.assert_canonical(fixture, result)
                self.assertEqual(result.stderr, b"")
                self.assertEqual(fixture.eval_log.read_text(), "STRICT=1\n")
                self.assertEqual(summary["generated_at"], NOW)
                self.assertEqual(summary["policy_sha"], fixture.git("rev-parse", "HEAD"))
                self.assertEqual(summary["findings"], [])
                self.assertEqual(summary["status"], {"state": "ok"})
                self.assertEqual(
                    [
                        (item["check"], item["outcome"], item["summary"])
                        for item in summary["checks"]
                    ],
                    [
                        ("worktree-clean", "passed", "clean"),
                        ("evals-strict", "passed", "STRICT evals passed"),
                        ("gate-1", "passed", "Gate 1 passed on clean tree"),
                        ("gate-2", "passed", "1 validations passed"),
                        ("invariant-sweep", "passed", "0 invariants passed"),
                        ("mutation-full", "passed", "no mutation commands configured"),
                        ("file-category-coverage", "passed", "all tracked files categorized"),
                        ("region-staleness", "passed", "policy regions current"),
                        ("telemetry", "passed", "telemetry aggregated"),
                    ],
                )
                self.assertEqual(
                    summary["telemetry"],
                    {
                        "available": True,
                        "eligible_commits": 0,
                        "event_prune": {
                            "entries_removed": 0,
                            "failure": "",
                            "new_oldest_at": "",
                        },
                        "fast_allowed": 0,
                        "fast_denied_eligibility": 0,
                        "fast_denied_policy": 0,
                        "guard_denies": 0,
                        "halt_events": 0,
                        "review_blocks": 0,
                        "user_skips": 0,
                        "window_end": NOW,
                        "window_start": "2026-07-01T00:00:00Z",
                    },
                )
                if block_present:
                    self.assertEqual(block.read_bytes(), marker)
                else:
                    self.assertFalse(block.exists())

    def test_multiline_html_comment_in_drift_config_is_ignored(self) -> None:
        fixture = self.fixture(
            drift_config=(
                "<!-- forge-init: confirm these defaults with exactly one valid cadence,\n"
                "retention, and event-retention line. -->\n\n"
                "cadence: 14d\nretention: forever\nevent-retention: 400d"
            )
        )
        result = fixture.invoke()
        self.assertEqual(result.returncode, 1, result.stderr.decode())
        self.assertEqual(result.stderr, b"")
        summary = self.assert_canonical(fixture, result)
        self.assertEqual(summary["status"], {"state": "findings"})
        self.assertIn("unfilled-sentinel", summary["findings"][0]["evidence"])

    def test_dirty_precondition_literal_shape_has_sorted_unique_paths_and_skips_all_work(self) -> None:
        fixture = self.fixture()
        fixture.write("docs/spec.md", "modified\n")
        fixture.write("scratch.txt", "untracked\n")
        result = fixture.invoke()
        self.assertEqual(result.returncode, 2)
        summary = self.assert_canonical(fixture, result)
        self.assertFalse(fixture.eval_log.exists(), "STRICT evals ran despite dirty precondition")
        self.assertEqual(summary["findings"], [])
        self.assertEqual(
            [{key: value for key, value in summary["checks"][0].items() if key != "duration_ms"}],
            [{"check": "worktree-clean", "outcome": "failed", "summary": "dirty worktree"}],
        )
        self.assertEqual(
            summary["status"],
            {"dirty_paths": ["docs/spec.md", "scratch.txt"], "failure": "dirty-worktree", "state": "failed"},
        )
        self.assert_empty_telemetry(summary["telemetry"])
        self.assertEqual(
            self.normalized_summary(summary),
            {
                "checks": [{
                    "check": "worktree-clean",
                    "duration_ms": 0,
                    "outcome": "failed",
                    "summary": "dirty worktree",
                }],
                "findings": [],
                "generated_at": NOW,
                "policy_sha": "<policy-sha>",
                "schema_version": 1,
                "status": {
                    "dirty_paths": ["docs/spec.md", "scratch.txt"],
                    "failure": "dirty-worktree",
                    "state": "failed",
                },
                "telemetry": summary["telemetry"],
            },
        )

    def test_deleted_tracked_manifest_is_dirty_precondition_and_skips_evals(self) -> None:
        fixture = self.fixture()
        (fixture.repo / ".forge-manifest").unlink()
        result = fixture.invoke()
        self.assertEqual(result.returncode, 2)
        summary = self.assert_canonical(fixture, result)
        self.assertFalse(fixture.eval_log.exists(), "STRICT evals ran after manifest deletion")
        self.assertEqual(
            self.normalized_summary(summary),
            {
                "checks": [{
                    "check": "worktree-clean",
                    "duration_ms": 0,
                    "outcome": "failed",
                    "summary": "dirty worktree",
                }],
                "findings": [],
                "generated_at": NOW,
                "policy_sha": "<policy-sha>",
                "schema_version": 1,
                "status": {
                    "dirty_paths": [".forge-manifest"],
                    "failure": "dirty-worktree",
                    "state": "failed",
                },
                "telemetry": summary["telemetry"],
            },
        )
        self.assert_empty_telemetry(summary["telemetry"])

    def test_dirty_unborn_repository_reports_dirty_before_head_resolution(self) -> None:
        fixture = DriftFixture(self.temp)
        repo = fixture.root / "unborn"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        (repo / "untracked.txt").write_text("dirty\n", encoding="utf-8")

        result = subprocess.run(
            [str(DRIFT_CHECK)],
            cwd=repo,
            env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(fixture.plugin), "FORGE_DRIFT_NOW": NOW},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        summary = json.loads(result.stdout)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(summary["policy_sha"], "")
        self.assertEqual(summary["status"], {
            "dirty_paths": ["untracked.txt"],
            "failure": "dirty-worktree",
            "state": "failed",
        })
        self.assertEqual([item["check"] for item in summary["checks"]], ["worktree-clean"])

    def test_missing_region_is_reported_by_region_staleness_inventory(self) -> None:
        fixture = self.fixture()
        policy = (fixture.repo / "forge-project.md").read_text(encoding="utf-8")
        begin = "<!-- FORGE:REGION project-overview BEGIN -->"
        end = "<!-- FORGE:REGION project-overview END -->"
        before, remainder = policy.split(begin, 1)
        _body, after = remainder.split(end, 1)
        policy = (before + after).lstrip("\n")
        fixture.write("forge-project.md", policy)
        fixture.write("AGENTS.md", "<!-- FORGE:BEGIN -->\n" + policy.rstrip("\n") + "\n<!-- FORGE:END -->\n")
        fixture.commit("remove region")
        result = fixture.invoke()
        self.assertEqual(result.returncode, 1, result.stderr.decode())
        summary = self.assert_canonical(fixture, result)
        finding = next(item for item in summary["findings"] if item["code"] == "stale-policy-region")
        self.assertIn("region-inventory", finding["evidence"])

    def test_mutation_survivor_exit_one_matches_literal_finding_shape(self) -> None:
        for block_present in (False, True):
            with self.subTest(block_present=block_present):
                fixture = DriftFixture(
                    self.temp / f"exit-one-{block_present}",
                    mutation=(
                        "| category | command | changed-files form | timeout |\n"
                        "|---|---|---|---|\n"
                        "| python | printf 'surviving mutant\\n'; exit 1 | $@ | 5 |"
                    ),
                )
                block = fixture.repo / ".forge/tmp/drift-block"
                marker = b"operator-owned critical drift block\n"
                if block_present:
                    block.parent.mkdir(parents=True, exist_ok=True)
                    block.write_bytes(marker)
                result = fixture.invoke()
                self.assertEqual(result.returncode, 1, result.stderr.decode())
                summary = self.assert_canonical(fixture, result)
                mutation_check = next(
                    item for item in summary["checks"] if item["check"] == "mutation-full"
                )
                self.assertEqual(mutation_check["outcome"], "finding")
                self.assertEqual(
                    mutation_check["summary"],
                    "full-suite mutation left a surviving mutant",
                )
                self.assertEqual(
                    summary["findings"],
                    [{
                        "check": "mutation-full",
                        "code": "mutation-survivor",
                        "evidence": ["category=python"],
                        "severity": "MAJOR",
                        "summary": "full-suite mutation left a surviving mutant",
                    }],
                )
                self.assertEqual(summary["status"], {"state": "findings"})
                self.assertTrue(summary["telemetry"]["available"])
                if block_present:
                    self.assertEqual(block.read_bytes(), marker)
                else:
                    self.assertFalse(block.exists())

    def test_invariant_execution_exit_two_matches_non_dirty_literal_shape(self) -> None:
        fixture = self.fixture(
            invariants=(
                "| invariant | check command | enforcement point |\n"
                "|---|---|---|\n"
                "| fixture invariant | exit 1 | hook |"
            )
        )
        result = fixture.invoke()
        self.assertEqual(result.returncode, 2)
        summary = self.assert_canonical(fixture, result)
        self.assertEqual(summary["findings"], [])
        self.assertEqual([item["check"] for item in summary["checks"]], [
            "worktree-clean", "evals-strict", "gate-1", "gate-2", "invariant-sweep"
        ])
        failed = summary["checks"][-1]
        self.assertEqual(
            {key: value for key, value in failed.items() if key != "duration_ms"},
            {"check": "invariant-sweep", "outcome": "failed", "summary": "runner failed"},
        )
        self.assertEqual(summary["status"], {"failure": "invariant-execution", "state": "failed"})
        self.assert_empty_telemetry(summary["telemetry"])
        expected_checks = [
            ("worktree-clean", "passed", "clean"),
            ("evals-strict", "passed", "STRICT evals passed"),
            ("gate-1", "passed", "Gate 1 passed on clean tree"),
            ("gate-2", "passed", "1 validations passed"),
            ("invariant-sweep", "failed", "runner failed"),
        ]
        self.assertEqual(
            self.normalized_summary(summary),
            {
                "checks": [
                    {"check": name, "duration_ms": 0, "outcome": outcome, "summary": text}
                    for name, outcome, text in expected_checks
                ],
                "findings": [],
                "generated_at": NOW,
                "policy_sha": "<policy-sha>",
                "schema_version": 1,
                "status": {"failure": "invariant-execution", "state": "failed"},
                "telemetry": summary["telemetry"],
            },
        )

    def test_direct_event_aggregation_dedupes_window_and_prunes_by_retention(self) -> None:
        fixture = self.fixture(
            drift_config="cadence: 14d\nretention: forever\nevent-retention: 366d"
        )
        sha40 = "a" * 40
        sha64a = "b" * 64
        sha64b = "c" * 64
        sha64c = "d" * 64
        events = [
            fixture.event("2024-01-01T00:00:00Z", "halt_event"),
            fixture.event("2025-08-12T00:00:00Z", "halt_event"),
            fixture.event("2026-07-01T00:00:00Z", "gate_commit", sha40),
            fixture.event("2026-07-02T00:00:00Z", "gate_commit", sha40),
            fixture.event("2026-07-03T00:00:00Z", "fast_allowed", sha40),
            fixture.event("2026-07-04T00:00:00Z", "fast_allowed", sha40),
            fixture.event("2026-07-05T00:00:00Z", "fast_denied_policy", sha64a),
            fixture.event("2026-07-06T00:00:00Z", "fast_denied_policy", sha64a),
            fixture.event("2026-07-07T00:00:00Z", "fast_denied_eligibility"),
            fixture.event("2026-07-08T00:00:00Z", "fast_denied_eligibility"),
            fixture.event("2026-07-09T00:00:00Z", "user_skip", sha64b),
            fixture.event("2026-07-10T00:00:00Z", "review_block", sha64c),
            fixture.event("2026-07-11T00:00:00Z", "guard_deny", sha64b),
            fixture.event("2026-07-12T00:00:00Z", "halt_event"),
            fixture.event("2026-07-13T00:00:00Z", "halt_event"),
        ]
        event_path = fixture.write_events(events, malformed=True)
        result = fixture.invoke()
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        summary = self.assert_canonical(fixture, result)
        self.assertNotIn(b"telemetry.csv", result.stdout)
        self.assertEqual(
            summary["telemetry"],
            {
                "available": True,
                "eligible_commits": 1,
                "event_prune": {"entries_removed": 2, "failure": "", "new_oldest_at": "2025-08-12T00:00:00Z"},
                "fast_allowed": 1,
                "fast_denied_eligibility": 2,
                "fast_denied_policy": 1,
                "guard_denies": 4,
                "halt_events": 2,
                "review_blocks": 1,
                "user_skips": 1,
                "window_end": NOW,
                "window_start": "2026-07-01T00:00:00Z",
            },
        )
        retained = [json.loads(line) for line in event_path.read_text().splitlines()]
        self.assertEqual(retained[0]["at"], "2025-08-12T00:00:00Z")
        self.assertTrue(any(item["at"] == "2026-07-01T00:00:00Z" for item in retained))

    def test_prune_clamp_retains_every_event_at_or_after_window_start(self) -> None:
        fixture = self.fixture()
        event_path = fixture.write_events([
            fixture.event("2026-06-30T23:59:59Z", "halt_event"),
            fixture.event("2026-07-01T00:00:00Z", "halt_event"),
            fixture.event("2026-07-01T01:00:00Z", "halt_event"),
        ])
        result = fixture.invoke(extra_env={"FORGE_DRIFT_RETENTION_DAYS_UNSAFE": "1"})
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        summary = self.assert_canonical(fixture, result)
        self.assertEqual(
            summary["telemetry"]["event_prune"],
            {
                "entries_removed": 1,
                "failure": "",
                "new_oldest_at": "2026-07-01T00:00:00Z",
            },
        )
        retained = [json.loads(line) for line in event_path.read_text().splitlines()]
        self.assertEqual(
            [item["at"] for item in retained],
            ["2026-07-01T00:00:00Z", "2026-07-01T01:00:00Z"],
        )

    def test_short_write_prefix_does_not_hide_later_intact_event(self) -> None:
        fixture = self.fixture()
        short_write = fixture.event("2026-07-01T00:00:00Z", "halt_event")
        intact = fixture.event("2026-07-02T00:00:00Z", "guard_deny", "b" * 64)
        event_path = fixture.repo / ".forge/tmp/decisions/events.jsonl"
        event_path.parent.mkdir(parents=True, exist_ok=True)
        short_payload = json.dumps(
            short_write, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        intact_payload = (
            json.dumps(intact, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        # Model an os.write() that wrote the complete JSON object but omitted
        # its final newline, followed by a later successful intact append.
        event_path.write_bytes(short_payload + intact_payload)

        result = fixture.invoke()

        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertIn(
            "forge: malformed decision event prefix ignored",
            result.stderr.decode(),
        )
        summary = self.assert_canonical(fixture, result)
        self.assertEqual(summary["telemetry"]["halt_events"], 0)
        self.assertEqual(summary["telemetry"]["guard_denies"], 1)
        self.assertEqual(
            summary["telemetry"]["event_prune"],
            {
                "entries_removed": 1,
                "failure": "",
                "new_oldest_at": "2026-07-02T00:00:00Z",
            },
        )
        self.assertEqual(event_path.read_bytes(), intact_payload)
        self.assertEqual(
            [json.loads(line) for line in event_path.read_text().splitlines()],
            [intact],
        )

    def test_event_at_window_end_is_excluded_from_telemetry(self) -> None:
        fixture = self.fixture()
        event_path = fixture.write_events([
            fixture.event("2026-08-11T11:59:59Z", "gate_commit", "a" * 40),
            fixture.event(NOW, "gate_commit", "b" * 40),
        ])
        result = fixture.invoke()
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        summary = self.assert_canonical(fixture, result)
        self.assertEqual(summary["telemetry"]["eligible_commits"], 1)
        self.assertEqual(summary["telemetry"]["window_end"], NOW)
        self.assertEqual(len(event_path.read_text().splitlines()), 2)

    def test_poisoned_stop_hook_csv_cannot_change_drift_telemetry(self) -> None:
        fixture = self.fixture()
        fixture.write_events([
            fixture.event("2026-07-02T00:00:00Z", "gate_commit", "a" * 40),
            fixture.event("2026-07-03T00:00:00Z", "review_block", "b" * 64),
        ])
        baseline = fixture.invoke()
        self.assertEqual(baseline.returncode, 0, baseline.stderr.decode())
        self.assert_canonical(fixture, baseline)
        _prefix, separator, baseline_fragment = baseline.stdout.rpartition(b',"telemetry":')
        self.assertEqual(separator, b',"telemetry":')
        self.assertTrue(baseline_fragment.endswith(b"}\n"))
        baseline_bytes = baseline_fragment[:-2]

        fixture.write(
            ".forge/tmp/telemetry.csv",
            (
                "unit,feature,model,elapsed_s,critical_path_s,tokens,cost_usd,"
                "review_iterations,rework_s,eligible_commits,fast_allowed,"
                "fast_denied_policy,fast_denied_eligibility,user_skips,review_blocks,"
                "halt_events,guard_denies\n"
                "__decision_totals__,,,,,,,,,99,98,97,96,95,94,93,92\n"
            ),
        )
        poisoned = fixture.invoke()
        self.assertEqual(poisoned.returncode, 0, poisoned.stderr.decode())
        self.assert_canonical(fixture, poisoned)
        _prefix, separator, poisoned_fragment = poisoned.stdout.rpartition(b',"telemetry":')
        self.assertEqual(separator, b',"telemetry":')
        self.assertTrue(poisoned_fragment.endswith(b"}\n"))
        poisoned_bytes = poisoned_fragment[:-2]
        self.assertEqual(poisoned_bytes, baseline_bytes)

    def test_prune_lock_failure_is_nonfatal_and_preserves_aggregation_exit(self) -> None:
        fixture = self.fixture()
        event_path = fixture.write_events([
            fixture.event("2026-07-02T00:00:00Z", "gate_commit", "a" * 40)
        ])
        original = event_path.read_bytes()
        result = fixture.invoke(extra_env={"FORGE_TEST_ACQUIRE_EXIT": "1"})
        self.assertEqual(result.returncode, 0)
        summary = self.assert_canonical(fixture, result)
        self.assertEqual(summary["status"], {"state": "ok"})
        self.assertTrue(summary["telemetry"]["available"])
        self.assertEqual(summary["telemetry"]["eligible_commits"], 1)
        self.assertEqual(
            summary["telemetry"]["event_prune"],
            {"entries_removed": 0, "failure": "event-prune-lock", "new_oldest_at": ""},
        )
        self.assertEqual(event_path.read_bytes(), original)

    def test_prune_waits_for_registered_emitter_and_retains_its_append(self) -> None:
        fixture = self.fixture()
        old = fixture.event("2024-01-01T00:00:00Z", "halt_event")
        retained = fixture.event("2026-07-02T00:00:00Z", "gate_commit", "a" * 40)
        event_path = fixture.write_events([old, retained])
        ready = fixture.root / "emitter-registered"
        release = fixture.root / "release-emitter"
        prune_released = fixture.root / "prune-lock-released"
        emitted_candidate = "b" * 64
        emitter = subprocess.Popen(
            [
                "python3",
                str(fixture.plugin / "scripts/forge/emit-decision-event.py"),
                "--at",
                "2026-08-10T00:00:00Z",
                "--candidate",
                emitted_candidate,
                "--event",
                "guard_deny",
                "--policy-sha",
                fixture.git("rev-parse", "HEAD"),
                "--reason",
                "concurrent-prune",
                "--surface",
                "forge:commit",
            ],
            cwd=fixture.repo,
            env={
                **os.environ,
                "FORGE_TEST_EVENT_REGISTERED_READY": str(ready),
                "FORGE_TEST_EVENT_REGISTERED_RELEASE": str(release),
            },
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.addCleanup(lambda: emitter.poll() is None and emitter.kill())

        deadline = time.monotonic() + 5
        while not ready.exists() and emitter.poll() is None and time.monotonic() < deadline:
            time.sleep(0.005)
        if not ready.exists():
            _stdout, stderr = emitter.communicate(timeout=1)
            self.fail(stderr.decode() or "emitter did not reach registration barrier")

        drift = subprocess.Popen(
            ["bash", str(DRIFT_CHECK)],
            cwd=fixture.repo,
            env={
                **os.environ,
                "CLAUDE_PLUGIN_ROOT": str(fixture.plugin),
                "FORGE_DRIFT_NOW": NOW,
                "FORGE_EVAL_LOG": str(fixture.eval_log),
                "FORGE_DRIFT_RETENTION_DAYS_UNSAFE": "1",
                "FORGE_TEST_RELEASE_READY": str(prune_released),
            },
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.addCleanup(lambda: drift.poll() is None and drift.kill())
        lock_path = fixture.repo / ".forge/tmp/events.lock"
        deadline = time.monotonic() + 5
        while not lock_path.exists() and drift.poll() is None and time.monotonic() < deadline:
            time.sleep(0.005)
        if not lock_path.exists():
            _stdout, stderr = drift.communicate(timeout=1)
            self.fail(stderr.decode() or "drift check did not acquire the events lock")
        time.sleep(0.1)
        self.assertIsNone(drift.poll(), "pruner did not wait for registered event writer")
        self.assertTrue(lock_path.exists(), "pruner released its lock before writer drained")
        self.assertFalse(prune_released.exists(), "pruner reached release before writer drained")

        release.touch()
        emitter_stdout, emitter_stderr = emitter.communicate(timeout=5)
        drift_stdout, drift_stderr = drift.communicate(timeout=5)
        self.assertEqual(emitter.returncode, 0, emitter_stderr.decode())
        self.assertEqual(emitter_stdout, b"")
        self.assertEqual(drift.returncode, 0, drift_stderr.decode())
        self.assertTrue(prune_released.exists())
        summary = json.loads(drift_stdout)
        self.assertEqual(
            summary["telemetry"]["event_prune"],
            {
                "entries_removed": 1,
                "failure": "",
                "new_oldest_at": "2026-07-02T00:00:00Z",
            },
        )
        records = [json.loads(line) for line in event_path.read_text().splitlines()]
        self.assertNotIn(old, records)
        self.assertEqual(
            [record["candidate"] for record in records],
            [retained["candidate"], emitted_candidate],
        )
        self.assertEqual(records.count(retained), 1)
        self.assertEqual(
            [record for record in records if record["candidate"] == emitted_candidate],
            [
                {
                    "at": "2026-08-10T00:00:00Z",
                    "candidate": emitted_candidate,
                    "event": "guard_deny",
                    "policy_sha": fixture.git("rev-parse", "HEAD"),
                    "reason": "concurrent-prune",
                    "surface": "forge:commit",
                }
            ],
        )

    def test_uncertain_event_writer_preserves_events_and_is_nonfatal(self) -> None:
        fixture = self.fixture()
        old = fixture.event("2024-01-01T00:00:00Z", "halt_event")
        retained = fixture.event("2026-07-02T00:00:00Z", "gate_commit", "a" * 40)
        event_path = fixture.write_events([old, retained])
        original = event_path.read_bytes()
        uncertain = fixture.repo / ".forge/tmp/event-writers/not-a-writer-token"
        uncertain.parent.mkdir(parents=True)
        uncertain.touch()

        result = fixture.invoke(extra_env={"FORGE_DRIFT_RETENTION_DAYS_UNSAFE": "1"})

        self.assertEqual(result.returncode, 0, result.stderr.decode())
        summary = self.assert_canonical(fixture, result)
        self.assertEqual(summary["status"], {"state": "ok"})
        self.assertEqual(
            summary["telemetry"]["event_prune"],
            {
                "entries_removed": 0,
                "failure": "event-prune-writer-drain",
                "new_oldest_at": "",
            },
        )
        self.assertEqual(event_path.read_bytes(), original)
        self.assertFalse((fixture.repo / ".forge/tmp/events.lock").exists())

    def test_measurement_event_is_retained_and_occurrence_counted(self) -> None:
        fixture = self.fixture()
        measurement = fixture.event(
            "2026-07-02T00:00:00Z", "assertion_advisory", "c" * 64
        )
        fixture.write_events([measurement, measurement])

        result = fixture.invoke()

        self.assertEqual(result.returncode, 0, result.stderr.decode())
        summary = self.assert_canonical(fixture, result)
        self.assertEqual(summary["status"], {"state": "ok"})
        self.assertEqual(
            summary["telemetry"]["event_prune"],
            {
                "entries_removed": 0,
                "failure": "",
                "new_oldest_at": "2026-07-02T00:00:00Z",
            },
        )
        records = [
            json.loads(line)
            for line in (
                fixture.repo / ".forge/tmp/decisions/events.jsonl"
            ).read_text().splitlines()
        ]
        self.assertEqual(records, [measurement, measurement])

    def test_invalid_prune_override_is_nonfatal_and_preserves_full_telemetry(self) -> None:
        for label, invalid_override in (("empty", ""), ("text", "abc")):
            with self.subTest(invalid_override=invalid_override):
                fixture = DriftFixture(self.temp / label)
                event_path = fixture.write_events([
                    fixture.event("2024-01-01T00:00:00Z", "halt_event"),
                    fixture.event("2026-07-02T00:00:00Z", "gate_commit", "a" * 40)
                ])
                original = event_path.read_bytes()

                result = fixture.invoke(
                    extra_env={"FORGE_DRIFT_RETENTION_DAYS_UNSAFE": invalid_override}
                )

                self.assertEqual(result.returncode, 0, result.stderr.decode())
                summary = self.assert_canonical(fixture, result)
                self.assertEqual(summary["status"], {"state": "ok"})
                self.assertEqual(
                    summary["telemetry"],
                    {
                        "available": True,
                        "eligible_commits": 1,
                        "event_prune": {
                            "entries_removed": 0,
                            "failure": "event-prune-config",
                            "new_oldest_at": "",
                        },
                        "fast_allowed": 0,
                        "fast_denied_eligibility": 0,
                        "fast_denied_policy": 0,
                        "guard_denies": 0,
                        "halt_events": 0,
                        "review_blocks": 0,
                        "user_skips": 0,
                        "window_end": NOW,
                        "window_start": "2026-07-01T00:00:00Z",
                    },
                )
                self.assertEqual(event_path.read_bytes(), original)

    def test_malformed_config_warns_and_uses_all_defaults_while_365_is_invalid(self) -> None:
        fixture = self.fixture(
            drift_config="cadence: 1d\nretention: 1d\nevent-retention: 365d"
        )
        fixture.write_events([fixture.event("2025-07-20T00:00:00Z", "halt_event")])
        result = fixture.invoke()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr.decode(), CONFIG_WARNING + "\n")
        summary = self.assert_canonical(fixture, result)
        self.assertEqual(
            summary["telemetry"]["event_prune"],
            {"entries_removed": 0, "failure": "", "new_oldest_at": "2025-07-20T00:00:00Z"},
        )

    def test_366_day_event_retention_is_valid_and_same_day_summary_overwrites(self) -> None:
        fixture = self.fixture(
            drift_config="cadence: 14d\nretention: forever\nevent-retention: 366d"
        )
        fixture.write_events([fixture.event("2025-07-20T00:00:00Z", "halt_event")])
        first = fixture.invoke(now="2026-08-11T12:00:00Z")
        self.assertEqual(first.returncode, 0)
        self.assertEqual(first.stderr, b"")
        first_summary = self.assert_canonical(fixture, first, "2026-08-11T12:00:00Z")
        self.assertEqual(first_summary["telemetry"]["event_prune"]["entries_removed"], 1)
        second = fixture.invoke(now="2026-08-11T13:00:00Z")
        self.assertEqual(second.returncode, 0)
        self.assertNotEqual(first.stdout, second.stdout)
        self.assertEqual(
            (fixture.repo / ".forge/tmp/drift/2026-08-11.json").read_bytes(),
            second.stdout,
        )

    def test_fractional_utc_event_is_counted_and_pruned_by_time_not_as_malformed(self) -> None:
        fixture = self.fixture(
            drift_config="cadence: 14d\nretention: forever\nevent-retention: 366d"
        )
        old_fractional = "2025-07-20T00:00:00.900000Z"
        current_fractional = "2026-07-02T03:04:05.123456Z"
        event_path = fixture.write_events([
            fixture.event(old_fractional, "halt_event"),
            fixture.event(current_fractional, "gate_commit", "a" * 40),
        ])
        result = fixture.invoke()
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(result.stderr, b"")
        summary = self.assert_canonical(fixture, result)
        self.assertEqual(summary["telemetry"]["eligible_commits"], 1)
        self.assertEqual(
            summary["telemetry"]["event_prune"],
            {
                "entries_removed": 1,
                "failure": "",
                "new_oldest_at": current_fractional,
            },
        )
        retained = [json.loads(line) for line in event_path.read_text().splitlines()]
        self.assertEqual([item["at"] for item in retained], [current_fractional])

    def test_arbitrarily_huge_valid_event_retention_emits_schema_without_traceback(self) -> None:
        fixture = self.fixture(
            drift_config=(
                "cadence: 14d\nretention: forever\nevent-retention: "
                + ("9" * 5000)
                + "d"
            )
        )
        event_path = fixture.write_events([
            fixture.event("2026-07-02T00:00:00Z", "gate_commit", "a" * 40)
        ])
        original = event_path.read_bytes()
        result = fixture.invoke()
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(result.stderr, b"")
        self.assertNotIn(b"Traceback", result.stdout + result.stderr)
        summary = self.assert_canonical(fixture, result)
        self.assertEqual(summary["status"], {"state": "ok"})
        self.assertEqual(summary["telemetry"]["eligible_commits"], 1)
        self.assertEqual(event_path.read_bytes(), original)

    def test_missing_or_unlaunchable_eval_helper_is_exit_two_schema(self) -> None:
        for case in ("missing", "unlaunchable"):
            with self.subTest(case=case):
                fixture = DriftFixture(self.temp / case)
                helper = fixture.plugin / "scripts/forge/run-evals.sh"
                if case == "missing":
                    helper.unlink()
                else:
                    helper.chmod(0o644)
                result = fixture.invoke()
                self.assertEqual(result.returncode, 2)
                self.assertNotIn(b"Traceback", result.stdout + result.stderr)
                summary = self.assert_canonical(fixture, result)
                self.assertEqual(
                    [(item["check"], item["outcome"], item["summary"]) for item in summary["checks"]],
                    [
                        ("worktree-clean", "passed", "clean"),
                        ("evals-strict", "failed", "STRICT evals failed to execute"),
                    ],
                )
                self.assertEqual(
                    summary["status"],
                    {"failure": "eval-execution", "state": "failed"},
                )
                self.assertEqual(summary["findings"], [])
                self.assert_empty_telemetry(summary["telemetry"])

    def test_unexpected_runner_exception_is_exit_two_schema(self) -> None:
        fixture = self.fixture()
        helper = fixture.plugin / "scripts/forge/run-scoped-mutation.py"
        text = helper.read_text(encoding="utf-8")
        signature = "def run_command(command: str, paths: list[str], timeout: int, repo: Path) -> RunOutcome:\n"
        self.assertIn(signature, text)
        helper.write_text(
            text.replace(
                signature,
                signature + "    raise RuntimeError('disabled runner control')\n",
                1,
            ),
            encoding="utf-8",
        )
        result = fixture.invoke()
        self.assertEqual(result.returncode, 2, result.stderr.decode())
        self.assertNotIn(b"Traceback", result.stdout + result.stderr)
        summary = self.assert_canonical(fixture, result)
        self.assertEqual(summary["status"], {"failure": "gate-1-execution", "state": "failed"})
        self.assertEqual(summary["findings"], [])

    def test_unexpected_top_level_exception_emits_canonical_failure_schema(self) -> None:
        fixture = self.fixture()
        helper = fixture.plugin / "scripts/forge/run-scoped-mutation.py"
        text = helper.read_text(encoding="utf-8")
        signature = "def parse_file_categories(policy: str) -> dict[str, tuple[str, ...]]:\n"
        self.assertIn(signature, text)
        helper.write_text(
            text.replace(
                signature,
                signature + "    raise KeyboardInterrupt('disabled top-level boundary control')\n",
                1,
            ),
            encoding="utf-8",
        )
        result = fixture.invoke()
        self.assertEqual(result.returncode, 2, result.stderr.decode())
        self.assertNotIn(b"Traceback", result.stdout + result.stderr)
        summary = self.assert_canonical(fixture, result)
        self.assertEqual(summary["status"], {"failure": "drift-execution", "state": "failed"})
        self.assertEqual(summary["findings"], [])
        self.assertEqual(
            [(item["check"], item["outcome"], item["summary"]) for item in summary["checks"]],
            [("worktree-clean", "failed", "drift execution failed")],
        )
        self.assert_empty_telemetry(summary["telemetry"])

    def test_missing_or_unmarked_rendered_files_are_region_staleness_findings(self) -> None:
        for case in ("missing", "unmarked"):
            with self.subTest(case=case):
                fixture = DriftFixture(self.temp / case)
                agents = fixture.repo / "AGENTS.md"
                claude = fixture.repo / "CLAUDE.md"
                if case == "missing":
                    agents.unlink()
                    claude.unlink()
                else:
                    agents.write_text("policy without FORGE splice markers\n", encoding="utf-8")
                    claude.write_text("no forge project import\n", encoding="utf-8")
                fixture.commit(f"{case} rendered policy files")
                result = fixture.invoke()
                self.assertEqual(result.returncode, 1, result.stderr.decode())
                summary = self.assert_canonical(fixture, result)
                self.assertEqual(
                    summary["findings"],
                    [{
                        "check": "region-staleness",
                        "code": "stale-policy-region",
                        "evidence": ["rendered=AGENTS.md", "rendered=CLAUDE.md"],
                        "severity": "MAJOR",
                        "summary": "committed policy regions are stale",
                    }],
                )
                region_check = next(
                    item for item in summary["checks"] if item["check"] == "region-staleness"
                )
                self.assertEqual(region_check["outcome"], "finding")

    def test_nested_package_json_needs_exact_npm_category_despite_npm_prose(self) -> None:
        fixture = self.fixture(
            file_categories=(
                "| Category | File patterns |\n"
                "|---|---|\n"
                "| `fixture` | `*` |"
            ),
            stack_validations=(
                "npm is named here, but this is not a file-category row.\n\n"
                "```bash\n# npm\ntrue\n```"
            ),
        )
        fixture.write("service/package.json", '{"name":"service"}\n')
        fixture.commit("add nested node service")
        result = fixture.invoke()
        self.assertEqual(result.returncode, 1, result.stderr.decode())
        summary = self.assert_canonical(fixture, result)
        self.assertEqual(
            summary["findings"],
            [{
                "check": "region-staleness",
                "code": "stale-policy-region",
                "evidence": ["stack=node"],
                "severity": "MAJOR",
                "summary": "committed policy regions are stale",
            }],
        )
        coverage = next(
            item for item in summary["checks"] if item["check"] == "file-category-coverage"
        )
        self.assertEqual(coverage["outcome"], "passed")

    def test_deleted_then_restored_command_path_is_not_stale(self) -> None:
        fixture = self.fixture(
            gate_one="```bash\ntest -f scripts/check.sh\n```"
        )
        target = fixture.write("scripts/check.sh", "#!/bin/sh\nexit 0\n")
        fixture.commit("add command path")
        target.unlink()
        fixture.commit("delete command path")
        fixture.write("scripts/check.sh", "#!/bin/sh\nexit 0\n")
        fixture.commit("restore command path")
        result = fixture.invoke()
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        summary = self.assert_canonical(fixture, result)
        self.assertEqual(summary["findings"], [])
        region_check = next(
            item for item in summary["checks"] if item["check"] == "region-staleness"
        )
        self.assertEqual(
            (region_check["outcome"], region_check["summary"]),
            ("passed", "policy regions current"),
        )


class DriftStalenessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.temp = Path(self.temporary.name)

    def test_inert_outside_initialized_repository(self) -> None:
        result = subprocess.run(
            ["bash", str(DRIFT_STALENESS)],
            cwd=self.temp,
            env={**os.environ, "FORGE_DRIFT_NOW": NOW},
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr, b"")
        self.assertEqual(list(self.temp.iterdir()), [])

    def test_inert_in_git_repository_without_manifest(self) -> None:
        for args in (
            ("init", "-q"),
            ("config", "user.name", "Drift Fixture"),
            ("config", "user.email", "drift@example.invalid"),
            ("config", "commit.gpgsign", "false"),
        ):
            result = subprocess.run(
                ["git", *args],
                cwd=self.temp,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr.decode())
        (self.temp / "tracked.txt").write_text("committed\n", encoding="utf-8")
        for args in (("add", "tracked.txt"), ("commit", "-qm", "initial")):
            result = subprocess.run(
                ["git", *args],
                cwd=self.temp,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr.decode())
        nested = self.temp / "nested"
        nested.mkdir()
        result = subprocess.run(
            ["bash", str(DRIFT_STALENESS)],
            cwd=nested,
            env={**os.environ, "FORGE_DRIFT_NOW": NOW},
            capture_output=True,
            check=False,
        )
        self.assertFalse((self.temp / ".forge-manifest").exists())
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr, b"")

    def test_staleness_reads_committed_policy_not_worktree_edit(self) -> None:
        fixture = DriftFixture(
            self.temp,
            drift_config="cadence: 1d\nretention: forever\nevent-retention: 400d",
        )
        fixture.write(".forge/history/drift/2026-08-09T120000Z.md", "# Drift\n")
        fixture.commit("stale drift report")
        fixture.write(
            "forge-project.md",
            policy_text(
                drift_config=(
                    "cadence: 999d\nretention: forever\nevent-retention: 400d"
                )
            ),
        )
        self.assertEqual(fixture.git("status", "--short"), "M forge-project.md")
        result = fixture.staleness()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr.decode(), STALE_WARNING + "\n")

    def test_warns_without_report_and_is_silent_for_fresh_committed_report(self) -> None:
        fixture = DriftFixture(self.temp)
        stale = fixture.staleness()
        self.assertEqual(stale.returncode, 0)
        self.assertEqual(stale.stdout, b"")
        self.assertEqual(stale.stderr.decode(), STALE_WARNING + "\n")
        fixture.write(".forge/history/drift/2026-08-10T120000Z.md", "# Drift\n")
        fixture.commit("fresh drift report")
        fresh = fixture.staleness()
        self.assertEqual(fresh.returncode, 0)
        self.assertEqual(fresh.stdout, b"")
        self.assertEqual(fresh.stderr, b"")

    def test_malformed_config_emits_exact_default_warning_and_stale_nudge(self) -> None:
        fixture = DriftFixture(
            self.temp,
            drift_config="cadence: 1d\nretention: forever\nevent-retention: 365d",
        )
        result = fixture.staleness()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(
            result.stderr.decode(),
            CONFIG_WARNING + "\n" + STALE_WARNING + "\n",
        )

    def test_nested_timestamped_report_does_not_satisfy_direct_history_layout(self) -> None:
        fixture = DriftFixture(self.temp)
        fixture.write(".forge/history/drift/archive/2026-08-12T115900Z.md", "nested\n")
        fixture.commit("nested report")
        result = fixture.staleness()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr.decode(), STALE_WARNING + "\n")

    def test_staleness_ignores_multiline_drift_config_comment(self) -> None:
        fixture = DriftFixture(
            self.temp,
            drift_config=(
                "<!-- forge-init: confirm these defaults with exactly one valid cadence,\n"
                "retention, and event-retention line. -->\n\n"
                "cadence: 14d\nretention: forever\nevent-retention: 400d"
            ),
        )
        result = fixture.staleness()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr.decode(), STALE_WARNING + "\n")

    def test_report_suffix_requires_collision_number_at_least_two(self) -> None:
        invalid = DriftFixture(self.temp / "invalid")
        invalid.write(".forge/history/drift/2026-08-11T115900Z-01.md", "invalid suffix\n")
        invalid.commit("invalid suffix")
        invalid_result = invalid.staleness()
        self.assertEqual(invalid_result.returncode, 0)
        self.assertEqual(invalid_result.stderr.decode(), STALE_WARNING + "\n")

        valid = DriftFixture(self.temp / "valid")
        valid.write(".forge/history/drift/2026-08-11T115900Z-100.md", "valid suffix\n")
        valid.commit("valid suffix")
        valid_result = valid.staleness()
        self.assertEqual(valid_result.returncode, 0)
        self.assertEqual(valid_result.stderr, b"")


if __name__ == "__main__":
    unittest.main()
