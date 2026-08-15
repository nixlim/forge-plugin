from __future__ import annotations

import os
import csv
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN_EVALS = ROOT / "scripts/forge/run-evals.sh"
AGGREGATE_TELEMETRY = ROOT / "scripts/forge/aggregate-telemetry.sh"
SEED_EVAL_TASKS = ROOT / "system/seeds/eval-tasks"
SEED_BASELINES = (
    ("review-catches-planted-bug", "BLOCK"),
    ("review-passes-clean-change", "PASS"),
    ("injection-is-flagged", "BLOCK"),
)


class ShellScriptTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="forge-evals-")
        self.addCleanup(self.temp_dir.cleanup)
        self.repo = Path(self.temp_dir.name)

    def run_script(
        self,
        script: Path,
        *args: str,
        env_overrides: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.pop("STRICT", None)
        if env_overrides:
            env.update(env_overrides)
        return subprocess.run(
            ["bash", str(script), *args],
            cwd=self.repo,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )


class RunEvalsTests(ShellScriptTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tasks = self.repo / ".forge/evals/tasks"
        self.tasks.mkdir(parents=True)

    def write_fixture(
        self,
        fixture_id: str,
        *,
        category: str = "review",
        agent: str = "review-cheap",
        expected: str = "PASS",
        result: str | None = None,
    ) -> None:
        (self.tasks / f"{fixture_id}.md").write_text(
            "\n".join(
                (
                    "---",
                    f"id: {fixture_id}",
                    f"category: {category}",
                    f"agent: {agent}",
                    f"expected_verdict: {expected}",
                    "---",
                    "",
                    "## Scenario",
                    "A deterministic golden task.",
                    "",
                )
            ),
            encoding="utf-8",
        )
        if result is not None:
            (self.tasks / f"{fixture_id}.result").write_text(
                f"{result}\n", encoding="utf-8"
            )

    def write_seed_suite(self, *, overrides: dict[str, str] | None = None) -> None:
        overrides = overrides or {}
        for fixture_id, expected in SEED_BASELINES:
            source = SEED_EVAL_TASKS / f"{fixture_id}.template.md"
            (self.tasks / f"{fixture_id}.md").write_bytes(source.read_bytes())
            actual = overrides.get(fixture_id, expected)
            (self.tasks / f"{fixture_id}.result").write_text(
                f"{actual}\n", encoding="utf-8"
            )

    def test_seeded_fixtures_with_matching_baselines_exit_zero(self) -> None:
        self.write_seed_suite()

        result = self.run_script(RUN_EVALS)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for fixture_id, _ in SEED_BASELINES:
            self.assertIn(f"PASS {fixture_id}", result.stdout)
        self.assertIn("tasks=3 pass=3 fail=0 pending=0 malformed=0 strict=0", result.stdout)

    def test_flipped_seed_baseline_is_a_regression_with_exit_one(self) -> None:
        self.write_seed_suite(overrides={"review-passes-clean-change": "BLOCK"})

        result = self.run_script(RUN_EVALS)

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(
            "FAIL review-passes-clean-change (expected PASS, got BLOCK)",
            result.stdout,
        )
        self.assertIn("tasks=3 pass=2 fail=1 pending=0 malformed=0 strict=0", result.stdout)

    def test_matching_pass_block_and_flag_baselines_exit_zero(self) -> None:
        self.write_fixture("clean-review", expected="PASS", result="PASS")
        self.write_fixture("bug-review", expected="BLOCK", result="BLOCK")
        self.write_fixture(
            "route-flag",
            category="routing",
            agent="router",
            expected="FLAG",
            result="FLAG",
        )

        result = self.run_script(RUN_EVALS)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS clean-review", result.stdout)
        self.assertIn("PASS bug-review", result.stdout)
        self.assertIn("PASS route-flag", result.stdout)
        self.assertIn("tasks=3 pass=3 fail=0 pending=0 malformed=0 strict=0", result.stdout)
        self.assertTrue(result.stdout.rstrip().endswith("OK (no regressions in recorded results)"))

    def test_flipped_baseline_is_a_regression_with_exit_one(self) -> None:
        self.write_fixture("clean-review", expected="PASS", result="BLOCK")

        result = self.run_script(RUN_EVALS)

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("FAIL clean-review (expected PASS, got BLOCK)", result.stdout)
        self.assertTrue(result.stdout.rstrip().endswith("REGRESSION: golden task(s) failed"))

    def test_pending_is_lenient_by_default_and_fails_in_strict_mode(self) -> None:
        self.write_fixture("awaiting-baseline", expected="BLOCK")

        lenient = self.run_script(RUN_EVALS)
        strict = self.run_script(RUN_EVALS, env_overrides={"STRICT": "1"})

        self.assertEqual(lenient.returncode, 0, lenient.stdout + lenient.stderr)
        self.assertIn("PENDING awaiting-baseline", lenient.stdout)
        self.assertEqual(strict.returncode, 1, strict.stdout + strict.stderr)
        self.assertIn("strict=1", strict.stdout)
        self.assertTrue(
            strict.stdout.rstrip().endswith(
                "STRICT: 1 pending task(s) have no recorded result"
            )
        )

    def test_empty_suite_exits_two_with_exact_terminal_message(self) -> None:
        result = self.run_script(RUN_EVALS)

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(
            result.stdout.splitlines()[-1],
            "NO TASKS FOUND — gate vacuously satisfied",
        )

    def test_missing_required_frontmatter_is_malformed(self) -> None:
        (self.tasks / "missing-key.md").write_text(
            "---\nid: missing-key\ncategory: review\nagent: review-cheap\n---\n",
            encoding="utf-8",
        )

        result = self.run_script(RUN_EVALS)

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn(
            "MALFORMED missing-key: missing frontmatter: expected_verdict",
            result.stdout,
        )
        self.assertTrue(result.stdout.rstrip().endswith("FIXTURES MALFORMED"))

    def test_gitignored_scratch_in_the_tasks_directory_is_not_a_fixture(self) -> None:
        # Tooling drops stubs (CLAUDE.md, editor state) into any directory it touches.
        # Such a file is gitignored, so it can never reach a clean checkout and is not
        # part of the committed fixture suite; treating it as a malformed fixture
        # breaks the gate for a file no reviewer will ever see.
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        (self.repo / ".gitignore").write_text("**/CLAUDE.md\n", encoding="utf-8")
        (self.tasks / "CLAUDE.md").write_text(
            "<claude-mem-context>\n\n</claude-mem-context>", encoding="utf-8"
        )
        self.write_fixture("real-fixture", result="PASS")

        result = self.run_script(RUN_EVALS, env_overrides={"STRICT": "1"})

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("MALFORMED", result.stdout)
        self.assertIn("tasks=1", result.stdout)

    def test_tracked_malformed_fixture_still_fails_when_scratch_is_skipped(self) -> None:
        # The skip must not become a hole: a real fixture is tracked, so it is still
        # checked even in a repository that ignores scratch files.
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        (self.repo / ".gitignore").write_text("**/CLAUDE.md\n", encoding="utf-8")
        (self.tasks / "CLAUDE.md").write_text("stub", encoding="utf-8")
        (self.tasks / "missing-key.md").write_text(
            "---\nid: missing-key\ncategory: review\nagent: review-cheap\n---\n",
            encoding="utf-8",
        )

        result = self.run_script(RUN_EVALS)

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("MALFORMED missing-key", result.stdout)

    def test_review_agent_cannot_expect_flag(self) -> None:
        self.write_fixture(
            "bad-review-vocabulary",
            agent="review-final",
            expected="FLAG",
            result="FLAG",
        )

        result = self.run_script(RUN_EVALS)

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn(
            "review agent 'review-final' cannot emit FLAG (use BLOCK)",
            result.stdout,
        )
        self.assertIn("malformed=1", result.stdout)


class AggregateTelemetryTests(ShellScriptTestCase):
    HEADER = (
        "unit,feature,model,elapsed_s,critical_path_s,tokens,cost_usd,"
        "review_iterations,rework_s,eligible_commits,fast_allowed,"
        "fast_denied_policy,fast_denied_eligibility,user_skips,review_blocks,"
        "halt_events,guard_denies,assertion_blocking,assertion_advisory,"
        "assertion_waived,review_cheap_findings,review_final_findings"
    )
    APPEND_HEADER = "session," + HEADER

    def test_non_forge_working_directory_is_a_silent_noop(self) -> None:
        result = self.run_script(
            AGGREGATE_TELEMETRY,
            ".forge/tmp/decisions",
            "--csv",
            ".forge/tmp/telemetry-latest.csv",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")
        self.assertFalse((self.repo / ".forge").exists())

    def test_telemetry_is_aggregated_and_csv_written_under_forge_tmp(self) -> None:
        (self.repo / ".forge-manifest").write_text(
            "forge_version: 1\n", encoding="utf-8"
        )
        decisions = self.repo / ".forge/tmp/decisions"
        decisions.mkdir(parents=True)
        (decisions / "task-06.md").write_text(
            """# Decision log

```telemetry
unit: task-06
feature: enforcement
model: terra
tokens: 120
cost_usd: 1.25
elapsed_s: 40
critical_path_s: 30
review_iterations: 2
rework_s: 5
on_critical_path: implement review
stage.implement_s: 25
stage.review_s: 15
serialisation.review_wait_s: 4
```
""",
            encoding="utf-8",
        )

        result = self.run_script(
            AGGREGATE_TELEMETRY,
            ".forge/tmp/decisions",
            "--csv",
            ".forge/tmp/telemetry-latest.csv",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("AI-SDLC delivery telemetry — 1 unit(s)", result.stdout)
        self.assertIn("task-06", result.stdout)
        self.assertIn("Totals: elapsed=40s", result.stdout)
        self.assertIn("measured duration tax (forced serialisation)=4s", result.stdout)
        self.assertTrue(
            result.stdout.rstrip().endswith(
                "Per-unit CSV written to .forge/tmp/telemetry-latest.csv"
            )
        )
        csv_path = self.repo / ".forge/tmp/telemetry-latest.csv"
        self.assertEqual(
            csv_path.read_text(encoding="utf-8").splitlines(),
            [
                self.HEADER,
                "task-06,enforcement,terra,40,30,120,1.25,2,5,,,,,,,,,,,,,",
                "__decision_totals__,,,,,,,,,0,0,0,0,0,0,0,0,0,0,0,0,0",
            ],
        )

    def test_events_only_csv_applies_window_and_candidate_dedupe(self) -> None:
        (self.repo / ".forge-manifest").write_text("forge_version: 1\n", encoding="utf-8")
        decisions = self.repo / ".forge/tmp/decisions"
        decisions.mkdir(parents=True)
        candidate = "a" * 40
        events = [
            {"at": "2026-08-12T10:00:00Z", "candidate": candidate,
             "event": event, "policy_sha": "b" * 40, "reason": "ok",
             "surface": "/forge:commit"}
            for event in ("gate_commit", "gate_commit", "fast_allowed")
        ]
        events.extend([
            {"at": "2026-08-12T10:01:00Z", "candidate": "", "event": "halt_event",
             "policy_sha": "", "reason": "AGENT_HALT", "surface": "check-halt"},
            {"at": "2026-08-12T10:02:00Z", "candidate": "c" * 64,
             "event": "fast_denied_policy", "policy_sha": "b" * 40,
             "reason": "policy-drift", "surface": "commit-guard"},
            {"at": "2026-08-12T10:03:00Z", "candidate": "",
             "event": "review_block", "policy_sha": "b" * 40,
             "reason": "review-block", "surface": "/forge:commit"},
            {"at": "2026-08-12T10:04:00Z", "candidate": "",
             "event": "review_block", "policy_sha": "b" * 40,
             "reason": "review-block", "surface": "/forge:commit"},
        ])
        (decisions / "events.jsonl").write_text(
            "\n".join(json.dumps(item, sort_keys=True, separators=(",", ":")) for item in events) + "\n",
            encoding="utf-8",
        )

        result = self.run_script(
            AGGREGATE_TELEMETRY, str(decisions), "--csv", "events.csv",
            "--since", "2026-08-12T00:00:00Z", "--until", "2026-08-13T00:00:00Z",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            (self.repo / "events.csv").read_text(encoding="utf-8").splitlines()[-1],
            "__decision_totals__,,,,,,,,,1,1,1,0,0,2,1,1,0,0,0,0,0",
        )

    def test_only_gate_outcomes_dedupe_nonempty_candidates(self) -> None:
        (self.repo / ".forge-manifest").write_text("forge_version: 1\n", encoding="utf-8")
        decisions = self.repo / ".forge/tmp/decisions"
        decisions.mkdir(parents=True)
        commit_candidate = "a" * 40
        diff_candidates = {
            event: chr(ord("b") + index) * 64
            for index, event in enumerate((
                "fast_denied_policy", "fast_denied_eligibility", "user_skip",
                "review_block", "guard_deny",
            ))
        }
        events = []
        for event in ("gate_commit", "fast_allowed"):
            record = {"at": "2026-08-12T10:00:00Z", "candidate": commit_candidate,
                      "event": event, "policy_sha": "f" * 40, "reason": "ok",
                      "surface": "/forge:commit"}
            events.extend((record, dict(record)))
        for event, candidate in diff_candidates.items():
            record = {"at": "2026-08-12T10:00:00Z", "candidate": candidate,
                      "event": event, "policy_sha": "f" * 40, "reason": "decision",
                      "surface": "commit-guard"}
            events.extend((record, dict(record)))
        halt = {"at": "2026-08-12T10:00:00Z", "candidate": "e" * 64,
                "event": "halt_event", "policy_sha": "f" * 40,
                "reason": "AGENT_HALT", "surface": "check-halt"}
        events.extend((halt, dict(halt)))
        for index, event in enumerate((
            "assertion_blocking", "assertion_advisory", "assertion_waived",
            "review_cheap_finding", "review_final_finding",
        )):
            record = {
                "at": "2026-08-12T10:00:00Z",
                "candidate": str(index + 3) * 64,
                "event": event, "policy_sha": "f" * 40,
                "reason": "MAJOR", "surface": "/forge:commit",
            }
            events.extend((record, dict(record)))
        (decisions / "events.jsonl").write_text(
            "\n".join(json.dumps(item, sort_keys=True, separators=(",", ":")) for item in events) + "\n",
            encoding="utf-8",
        )

        result = self.run_script(
            AGGREGATE_TELEMETRY, str(decisions), "--csv", "events.csv",
            "--since", "2026-08-12T00:00:00Z", "--until", "2026-08-13T00:00:00Z",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            (self.repo / "events.csv").read_text(encoding="utf-8").splitlines()[-1],
            "__decision_totals__,,,,,,,,,1,1,1,1,1,1,2,3,2,2,2,2,2",
        )

    def test_empty_events_file_still_writes_zero_decision_totals(self) -> None:
        (self.repo / ".forge-manifest").write_text(
            "forge_version: 1\n", encoding="utf-8"
        )
        decisions = self.repo / ".forge/tmp/decisions"
        decisions.mkdir(parents=True)
        (decisions / "events.jsonl").write_text("", encoding="utf-8")

        result = self.run_script(
            AGGREGATE_TELEMETRY,
            str(decisions),
            "--csv",
            "events.csv",
            "--since",
            "2026-08-12T00:00:00Z",
            "--until",
            "2026-08-13T00:00:00Z",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            (self.repo / "events.csv").read_text(encoding="utf-8").splitlines(),
            [
                self.HEADER,
                "__decision_totals__,,,,,,,,,0,0,0,0,0,0,0,0,0,0,0,0,0",
            ],
        )

    def test_csv_uses_rfc4180_quoting_for_legacy_fields(self) -> None:
        (self.repo / ".forge-manifest").write_text(
            "forge_version: 1\n", encoding="utf-8"
        )
        decisions = self.repo / ".forge/tmp/decisions"
        decisions.mkdir(parents=True)
        (decisions / "quoted.md").write_text(
            "```telemetry\n"
            "unit: quoted-unit\n"
            'feature: has,comma and "quote"\n'
            "model: terra\n"
            "```\n",
            encoding="utf-8",
        )

        result = self.run_script(
            AGGREGATE_TELEMETRY,
            str(decisions),
            "--csv",
            "quoted.csv",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        rows = (self.repo / "quoted.csv").read_bytes().splitlines()
        self.assertEqual(
            rows[1],
            b'quoted-unit,"has,comma and ""quote""",terra,0,0,0,0.0,0,0,,,,,,,,,,,,,',
        )

    def test_malformed_or_out_of_window_events_still_write_zero_totals(self) -> None:
        (self.repo / ".forge-manifest").write_text(
            "forge_version: 1\n", encoding="utf-8"
        )
        decisions = self.repo / ".forge/tmp/decisions"
        decisions.mkdir(parents=True)
        (decisions / "events.jsonl").write_text(
            "not-json\n"
            '{"at":"not-a-time","candidate":"","event":"halt_event",'
            '"policy_sha":"","reason":"","surface":"check-halt"}\n'
            '{"at":"2026-08-11T23:59:59Z","candidate":"","event":"halt_event",'
            '"policy_sha":"","reason":"","surface":"check-halt"}\n',
            encoding="utf-8",
        )

        result = self.run_script(
            AGGREGATE_TELEMETRY,
            str(decisions),
            "--csv",
            "events.csv",
            "--since",
            "2026-08-12T00:00:00Z",
            "--until",
            "2026-08-13T00:00:00Z",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ignoring malformed decision event", result.stderr)
        self.assertEqual(
            (self.repo / "events.csv").read_text(encoding="utf-8").splitlines()[-1],
            "__decision_totals__,,,,,,,,,0,0,0,0,0,0,0,0,0,0,0,0,0",
        )

    def test_short_write_prefix_does_not_hide_later_intact_event(self) -> None:
        (self.repo / ".forge-manifest").write_text(
            "forge_version: 1\n", encoding="utf-8"
        )
        decisions = self.repo / ".forge/tmp/decisions"
        decisions.mkdir(parents=True)
        prefix = {
            "at": "2026-08-12T10:00:00Z", "candidate": "",
            "event": "halt_event", "policy_sha": "", "reason": "",
            "surface": "check-halt",
        }
        intact = {
            "at": "2026-08-12T10:01:00Z", "candidate": "c" * 64,
            "event": "guard_deny", "policy_sha": "b" * 40,
            "reason": "marker-missing", "surface": "commit-guard",
        }
        (decisions / "events.jsonl").write_text(
            json.dumps(prefix, sort_keys=True, separators=(",", ":"))
            + json.dumps(intact, sort_keys=True, separators=(",", ":"))
            + "\n",
            encoding="utf-8",
        )

        result = self.run_script(
            AGGREGATE_TELEMETRY, str(decisions), "--csv", "events.csv",
            "--since", "2026-08-12T00:00:00Z", "--until", "2026-08-13T00:00:00Z",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ignoring malformed decision event prefix", result.stderr)
        self.assertEqual(
            (self.repo / "events.csv").read_text(encoding="utf-8").splitlines()[-1],
            "__decision_totals__,,,,,,,,,0,0,0,0,0,0,0,1,0,0,0,0,0",
        )

    def test_unpaired_reversed_and_malformed_windows_exit_two(self) -> None:
        (self.repo / ".forge-manifest").write_text(
            "forge_version: 1\n", encoding="utf-8"
        )
        cases = (
            ("--since", "2026-08-12T00:00:00Z"),
            (
                "--since",
                "2026-08-13T00:00:00Z",
                "--until",
                "2026-08-12T00:00:00Z",
            ),
            (
                "--since",
                "not-a-time",
                "--until",
                "2026-08-12T00:00:00Z",
            ),
        )
        for extra in cases:
            with self.subTest(extra=extra):
                result = self.run_script(
                    AGGREGATE_TELEMETRY,
                    ".forge/tmp/decisions",
                    "--csv",
                    "events.csv",
                    *extra,
                )
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_window_is_half_open_at_exact_boundaries(self) -> None:
        (self.repo / ".forge-manifest").write_text(
            "forge_version: 1\n", encoding="utf-8"
        )
        decisions = self.repo / ".forge/tmp/decisions"
        decisions.mkdir(parents=True)
        events = decisions / "events.jsonl"
        common = (
            '"candidate":"","event":"halt_event","policy_sha":"",'
            '"reason":"","surface":"check-halt"}'
        )
        events.write_text(
            '{"at":"2026-08-11T23:59:59Z",' + common + "\n"
            '{"at":"2026-08-12T00:00:00Z",' + common + "\n"
            '{"at":"2026-08-12T23:59:59Z",' + common + "\n"
            '{"at":"2026-08-13T00:00:00Z",' + common + "\n",
            encoding="utf-8",
        )

        result = self.run_script(
            AGGREGATE_TELEMETRY,
            str(decisions),
            "--csv",
            "window.csv",
            "--since",
            "2026-08-12T00:00:00Z",
            "--until",
            "2026-08-13T00:00:00Z",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            (self.repo / "window.csv").read_text(encoding="utf-8").splitlines()[-1],
            "__decision_totals__,,,,,,,,,0,0,0,0,0,0,2,0,0,0,0,0,0",
        )

    def test_missing_duplicate_and_flag_shaped_values_exit_two_exactly(self) -> None:
        (self.repo / ".forge-manifest").write_text(
            "forge_version: 1\n", encoding="utf-8"
        )
        cases = (
            ((), "--csv is required"),
            (("--csv",), "--csv requires a value"),
            (("--csv", "--since"), "--csv requires a value"),
            (("--csv", ""), "--csv requires a nonempty value"),
            (("--csv", "out.csv"), "decisions directory is required"),
            (
                ("--csv", "one.csv", "--csv", "two.csv"),
                "--csv may be supplied once",
            ),
            (("--unknown",), "unknown option --unknown"),
            (("one", "two", "--csv", "out.csv"), "multiple decisions directories"),
        )
        for args, reason in cases:
            with self.subTest(args=args):
                result = self.run_script(AGGREGATE_TELEMETRY, *args)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertEqual(
                    result.stderr,
                    f"forge: invalid aggregate-telemetry arguments: {reason}\n",
                )

    def test_event_read_and_csv_write_failures_exit_two_without_success(self) -> None:
        (self.repo / ".forge-manifest").write_text(
            "forge_version: 1\n", encoding="utf-8"
        )
        decisions = self.repo / ".forge/tmp/decisions"
        decisions.mkdir(parents=True)
        (decisions / "events.jsonl").mkdir()

        not_directory = self.repo / "not-a-directory"
        not_directory.write_text("telemetry cannot live here\n", encoding="utf-8")
        path_failure = self.run_script(
            AGGREGATE_TELEMETRY,
            str(not_directory),
            "--csv",
            "events.csv",
        )

        self.assertEqual(path_failure.returncode, 2, path_failure.stdout + path_failure.stderr)
        self.assertEqual(path_failure.stdout, "")
        self.assertEqual(
            path_failure.stderr,
            f"forge: aggregate telemetry failed: decisions path is not a directory: '{not_directory}'\n",
        )

        read_failure = self.run_script(
            AGGREGATE_TELEMETRY,
            str(decisions),
            "--csv",
            "events.csv",
        )

        self.assertEqual(read_failure.returncode, 2, read_failure.stdout + read_failure.stderr)
        self.assertEqual(read_failure.stdout, "")
        self.assertIn("forge: aggregate telemetry failed: cannot read decision events:", read_failure.stderr)
        self.assertNotIn("Per-unit CSV written", read_failure.stdout + read_failure.stderr)

        (decisions / "events.jsonl").rmdir()
        (decisions / "events.jsonl").write_text("", encoding="utf-8")
        write_failure = self.run_script(
            AGGREGATE_TELEMETRY,
            str(decisions),
            "--csv",
            "missing-parent/events.csv",
        )

        self.assertEqual(
            write_failure.returncode, 2, write_failure.stdout + write_failure.stderr
        )
        self.assertEqual(write_failure.stdout, "")
        self.assertIn("forge: aggregate telemetry failed: cannot write CSV", write_failure.stderr)
        self.assertNotIn("Per-unit CSV written", write_failure.stdout + write_failure.stderr)

    def test_explicit_decisions_path_with_no_decisions_reports_nothing_to_aggregate(self) -> None:
        (self.repo / ".forge-manifest").write_text(
            "forge_version: 1\n", encoding="utf-8"
        )

        result = self.run_script(
            AGGREGATE_TELEMETRY, ".forge/tmp/decisions", "--csv",
            ".forge/tmp/telemetry-latest.csv",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            result.stdout.strip(),
            "No decisions directory at '.forge/tmp/decisions' — nothing to aggregate.",
        )

    def write_append_sources(self) -> Path:
        subprocess.run(
            ["git", "init", "--quiet", str(self.repo)],
            check=True,
            capture_output=True,
            text=True,
        )
        (self.repo / ".forge-manifest").write_text(
            "forge_version: 1\n", encoding="utf-8"
        )
        decisions = self.repo / ".forge/tmp/decisions"
        decisions.mkdir(parents=True, exist_ok=True)
        (decisions / "events.jsonl").write_text(
            json.dumps(
                {
                    "at": "2026-08-12T10:00:00Z",
                    "candidate": "a" * 64,
                    "event": "assertion_advisory",
                    "policy_sha": "b" * 40,
                    "reason": "inconclusive",
                    "surface": "/forge:commit",
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        return decisions

    def run_append(self, decisions: Path, session: str) -> subprocess.CompletedProcess[str]:
        return self.run_script(
            AGGREGATE_TELEMETRY,
            str(decisions),
            "--append-csv",
            ".forge/tmp/telemetry.csv",
            "--session",
            session,
            "--since",
            "2026-08-12T00:00:00Z",
            "--until",
            "2026-08-13T00:00:00Z",
        )

    def test_append_mode_initializes_once_and_prefixes_every_row(self) -> None:
        decisions = self.write_append_sources()
        first = self.run_append(decisions, "session-a")
        second = self.run_append(decisions, "session-b")

        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        with (self.repo / ".forge/tmp/telemetry.csv").open() as stream:
            rows = list(csv.reader(stream))
        self.assertEqual(",".join(rows[0]), self.APPEND_HEADER)
        self.assertEqual(sum(row == self.APPEND_HEADER.split(",") for row in rows), 1)
        self.assertEqual([row[0] for row in rows[1:]], ["session-a", "session-b"])
        self.assertTrue(all(len(row) == 23 for row in rows))
        self.assertTrue(all(row[1] == "__decision_totals__" for row in rows[1:]))

    def test_concurrent_append_preserves_complete_session_blocks(self) -> None:
        decisions = self.write_append_sources()
        processes = [
            subprocess.Popen(
                [
                    "bash", str(AGGREGATE_TELEMETRY), str(decisions),
                    "--append-csv", ".forge/tmp/telemetry.csv",
                    "--session", f"session-{index}",
                    "--since", "2026-08-12T00:00:00Z",
                    "--until", "2026-08-13T00:00:00Z",
                ],
                cwd=self.repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for index in range(12)
        ]
        results = [process.communicate(timeout=20) + (process.returncode,) for process in processes]
        self.assertTrue(all(code == 0 for _out, _err, code in results), results)
        path = self.repo / ".forge/tmp/telemetry.csv"
        with path.open() as stream:
            rows = list(csv.reader(stream))
        self.assertEqual(rows.count(self.APPEND_HEADER.split(",")), 1)
        self.assertEqual(len(rows), 13)
        self.assertEqual({row[0] for row in rows[1:]}, {f"session-{i}" for i in range(12)})
        self.assertTrue(all(len(row) == 23 for row in rows))

    def test_append_rejects_bad_header_and_preserves_prior_bytes(self) -> None:
        decisions = self.write_append_sources()
        target = self.repo / ".forge/tmp/telemetry.csv"
        target.write_bytes(b"wrong,header\nprior,row\n")
        before = target.read_bytes()

        result = self.run_append(decisions, "session-a")

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(target.read_bytes(), before)

    def test_append_rejects_duplicate_header_and_preserves_prior_bytes(self) -> None:
        decisions = self.write_append_sources()
        target = self.repo / ".forge/tmp/telemetry.csv"
        header = (self.APPEND_HEADER + "\n").encode()
        target.write_bytes(header + header)
        before = target.read_bytes()

        result = self.run_append(decisions, "session-a")

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(target.read_bytes(), before)

    def test_append_refuses_live_foreign_lock_and_preserves_prior_bytes(self) -> None:
        decisions = self.write_append_sources()
        initialized = self.run_append(decisions, "session-a")
        self.assertEqual(initialized.returncode, 0, initialized.stdout + initialized.stderr)
        target = self.repo / ".forge/tmp/telemetry.csv"
        before = target.read_bytes()
        (self.repo / ".forge/tmp/telemetry.lock").write_text(
            f"{os.getpid()} 1\n", encoding="utf-8"
        )

        result = self.run_script(
            AGGREGATE_TELEMETRY,
            str(decisions),
            "--append-csv",
            ".forge/tmp/telemetry.csv",
            "--session",
            "session-b",
            "--since",
            "2026-08-12T00:00:00Z",
            "--until",
            "2026-08-13T00:00:00Z",
            env_overrides={"FORGE_COMMIT_LOCK_TIMEOUT": "1"},
        )

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(target.read_bytes(), before)

    def test_missing_source_append_writes_nothing(self) -> None:
        subprocess.run(
            ["git", "init", "--quiet", str(self.repo)],
            check=True,
            capture_output=True,
            text=True,
        )
        (self.repo / ".forge-manifest").write_text("forge_version: 1\n")

        result = self.run_append(self.repo / ".forge/tmp/decisions", "session-a")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.repo / ".forge/tmp/telemetry.csv").exists())
        self.assertFalse((self.repo / ".forge/tmp/telemetry.lock").exists())

    def test_append_requires_nonempty_session_and_paired_mode(self) -> None:
        (self.repo / ".forge-manifest").write_text("forge_version: 1\n")
        cases = (
            (("decisions", "--append-csv", "out.csv"),
             "--session is required with --append-csv"),
            (("decisions", "--append-csv", "out.csv", "--session", ""),
             "--session requires a nonempty value"),
            (("decisions", "--csv", "one.csv", "--append-csv", "two.csv"),
             "--csv and --append-csv are mutually exclusive"),
            (("decisions", "--csv", "one.csv", "--session", "s"),
             "--session requires --append-csv"),
        )
        for args, reason in cases:
            with self.subTest(args=args):
                result = self.run_script(AGGREGATE_TELEMETRY, *args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(
                    result.stderr,
                    f"forge: invalid aggregate-telemetry arguments: {reason}\n",
                )


if __name__ == "__main__":
    unittest.main()
