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
                "unit,feature,model,elapsed_s,critical_path_s,tokens,cost_usd,review_iterations,rework_s",
                "task-06,enforcement,terra,40,30,120,1.25,2,5",
            ],
        )

    def test_forge_repo_without_decisions_uses_re_rooted_default(self) -> None:
        (self.repo / ".forge-manifest").write_text(
            "forge_version: 1\n", encoding="utf-8"
        )

        result = self.run_script(AGGREGATE_TELEMETRY)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            result.stdout.strip(),
            "No decisions directory at '.forge/tmp/decisions' — nothing to aggregate.",
        )


if __name__ == "__main__":
    unittest.main()
