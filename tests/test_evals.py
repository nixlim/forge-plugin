from __future__ import annotations

import os
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
                "unit,feature,model,elapsed_s,critical_path_s,tokens,cost_usd,review_iterations,rework_s,eligible_commits,fast_allowed,fast_denied_policy,fast_denied_eligibility,user_skips,review_blocks,halt_events,guard_denies",
                "task-06,enforcement,terra,40,30,120,1.25,2,5,,,,,,,,",
                "__decision_totals__,,,,,,,,,0,0,0,0,0,0,0,0",
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
        import json
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
            "__decision_totals__,,,,,,,,,1,1,1,0,0,2,1,1",
        )

    def test_every_event_counter_dedupes_nonempty_candidates(self) -> None:
        (self.repo / ".forge-manifest").write_text("forge_version: 1\n", encoding="utf-8")
        decisions = self.repo / ".forge/tmp/decisions"
        decisions.mkdir(parents=True)
        import json
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
            "__decision_totals__,,,,,,,,,1,1,1,1,1,1,2,3",
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
                "unit,feature,model,elapsed_s,critical_path_s,tokens,cost_usd,review_iterations,rework_s,eligible_commits,fast_allowed,fast_denied_policy,fast_denied_eligibility,user_skips,review_blocks,halt_events,guard_denies",
                "__decision_totals__,,,,,,,,,0,0,0,0,0,0,0,0",
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
            b'quoted-unit,"has,comma and ""quote""",terra,0,0,0,0.0,0,0,,,,,,,,',
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
            "__decision_totals__,,,,,,,,,0,0,0,0,0,0,0,0",
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
            "__decision_totals__,,,,,,,,,0,0,0,0,0,0,2,0",
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


if __name__ == "__main__":
    unittest.main()
