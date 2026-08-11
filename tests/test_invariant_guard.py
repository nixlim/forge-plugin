from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts" / "forge" / "invariant-guard.sh"


def policy_with_rows(*rows: str) -> str:
    rendered_rows = "\n".join(rows)
    return f"""# Forge Project

<!-- FORGE:REGION invariants BEGIN -->
| invariant | check command | enforcement point |
| --- | --- | --- |
{rendered_rows}
<!-- FORGE:REGION invariants END -->
"""


class InvariantGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary_directory.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Forge Tests")
        self.git("config", "user.email", "forge-tests@example.invalid")
        (self.repo / ".forge-manifest").write_text("init_completed: true\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def git(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *arguments],
            cwd=self.repo,
            check=True,
            capture_output=True,
            text=True,
        )

    def commit_policy(self, *rows: str) -> None:
        (self.repo / "forge-project.md").write_text(policy_with_rows(*rows), encoding="utf-8")
        self.git("add", ".forge-manifest", "forge-project.md")
        self.git("commit", "-q", "-m", "test policy")

    def assert_advisory(
        self,
        result: subprocess.CompletedProcess[str],
        *advisories: str,
    ) -> None:
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            json.loads(result.stdout),
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": "".join(
                        f"{advisory}\n" for advisory in advisories
                    ),
                }
            },
        )

    def invoke(
        self,
        *,
        cwd: Path | None = None,
        timeout: float = 6.0,
        environment: dict[str, str] | None = None,
        launcher: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ([launcher, str(GUARD)] if launcher else [str(GUARD)]),
            cwd=cwd or self.repo,
            input=json.dumps(
                {
                    "hook_event_name": "PostToolUse",
                    "tool_name": "Edit",
                    "tool_input": {"file_path": "example.txt"},
                }
            ),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=environment,
        )

    def test_non_forge_working_directory_is_silent_and_inert(self) -> None:
        with tempfile.TemporaryDirectory() as unrelated:
            result = self.invoke(cwd=Path(unrelated))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def test_missing_committed_policy_is_a_json_advisory(self) -> None:
        result = self.invoke()

        self.assert_advisory(
            result,
            "forge: invariant advisory — policy "
            "(committed forge-project.md unavailable)",
        )
        self.assertEqual(result.stderr, "")

    def test_only_hook_enforcement_rows_execute(self) -> None:
        self.commit_policy(
            "| commit check | printf commit > commit-ran | commit |",
            "| merge check | printf merge > merge-ran | merge |",
            "| hook check | printf hook > hook-ran | hook |",
        )

        result = self.invoke()

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")
        self.assertFalse((self.repo / "commit-ran").exists())
        self.assertFalse((self.repo / "merge-ran").exists())
        self.assertEqual((self.repo / "hook-ran").read_text(encoding="utf-8"), "hook")

    def test_policy_is_read_from_committed_head_not_working_tree(self) -> None:
        self.commit_policy("| source is committed | printf committed > policy-source | hook |")
        (self.repo / "forge-project.md").write_text(
            policy_with_rows("| source is mutable | printf working > policy-source | hook |"),
            encoding="utf-8",
        )

        result = self.invoke()

        self.assertEqual(result.returncode, 0)
        self.assertEqual((self.repo / "policy-source").read_text(encoding="utf-8"), "committed")

    def test_command_cell_is_one_bash_c_argument_with_literal_forge_argv_zero(self) -> None:
        self.commit_policy(
            "| $(touch invariant-name-executed) | "
            'test "$0" = forge && test "$#" -eq 0 && '
            'printf \'%s,%s\\n\' "$0" "$#" > argv-result | hook |'
        )

        result = self.invoke()

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual((self.repo / "argv-result").read_text(encoding="utf-8"), "forge,0\n")
        self.assertFalse((self.repo / "invariant-name-executed").exists())

    def test_process_argv_contains_the_complete_logical_cell_without_wrapping(self) -> None:
        command = 'test "$0" = forge && test "$#" -eq 0 && : "two words"'
        self.commit_policy(f"| exact argv | {command} | hook |")
        fake_bin = self.repo / "fake-bin"
        fake_bin.mkdir()
        argument_log = self.repo / "bash-arguments"
        real_bash = "/bin/bash"
        wrapper = fake_bin / "bash"
        wrapper.write_text(
            "#!/bin/sh\n"
            "{\n"
            "  printf '%s\\n' \"$#\"\n"
            "  printf '<%s>\\n' \"$@\"\n"
            '} > "$FORGE_ARG_LOG"\n'
            'exec "$FORGE_REAL_BASH" "$@"\n',
            encoding="utf-8",
        )
        wrapper.chmod(0o755)
        environment = dict(os.environ)
        environment.update(
            {
                "PATH": f"{fake_bin}{os.pathsep}{environment['PATH']}",
                "FORGE_ARG_LOG": str(argument_log),
                "FORGE_REAL_BASH": real_bash,
            }
        )

        result = self.invoke(environment=environment, launcher=real_bash)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            argument_log.read_text(encoding="utf-8"),
            f"3\n<-c>\n<{command}>\n<forge>\n",
        )

    def test_markdown_escaped_pipe_is_part_of_the_logical_command_cell(self) -> None:
        self.commit_policy(r"| logical pipe | printf forge \| tr a-z A-Z > pipe-result | hook |")

        result = self.invoke()

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual((self.repo / "pipe-result").read_text(encoding="utf-8"), "FORGE")

    def test_failure_is_advisory_and_never_a_deny_decision(self) -> None:
        self.commit_policy("| reversible schema | exit 7 | hook |")

        result = self.invoke()

        self.assert_advisory(
            result,
            "forge: invariant advisory — reversible schema (exit 7)",
        )
        self.assertNotIn("permissionDecision", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_multiple_failures_share_one_additional_context_response(self) -> None:
        self.commit_policy(
            "| first hook | exit 3 | hook |",
            "| second hook | exit 4 | hook |",
        )

        result = self.invoke()

        self.assert_advisory(
            result,
            "forge: invariant advisory — first hook (exit 3)",
            "forge: invariant advisory — second hook (exit 4)",
        )
        self.assertEqual(result.stdout.count("hookSpecificOutput"), 1)
        self.assertEqual(result.stderr, "")

    def test_malformed_committed_table_executes_nothing_and_is_advisory(self) -> None:
        self.commit_policy("| missing point | touch must-not-run | |")

        result = self.invoke()

        self.assert_advisory(
            result,
            "forge: invariant advisory — policy (executable policy row malformed)",
        )
        self.assertFalse((self.repo / "must-not-run").exists())

    def test_each_check_has_a_two_second_budget_and_process_group_is_killed(self) -> None:
        self.commit_policy("| bounded hook | sleep 30 & wait | hook |")

        started = time.monotonic()
        result = self.invoke()
        elapsed = time.monotonic() - started

        self.assertLess(elapsed, 2.5)
        self.assert_advisory(
            result,
            "forge: invariant advisory — bounded hook (timed out)",
        )

    def test_successful_shell_cannot_leave_a_detached_descendant(self) -> None:
        self.commit_policy(
            "| no detached survivors | "
            "printf '%s' \"$$\" > detached-pgid; "
            "sleep 30 >/dev/null 2>&1 & | hook |"
        )

        result = self.invoke()

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        process_group = int((self.repo / "detached-pgid").read_text(encoding="utf-8"))
        with self.assertRaises(ProcessLookupError):
            os.killpg(process_group, 0)

    def test_output_limit_breach_is_capped_and_advisory(self) -> None:
        self.commit_policy(
            "| bounded output | python3 -c 'import sys; sys.stdout.write(\"x\" * 70000)' | hook |"
        )

        result = self.invoke()

        self.assert_advisory(
            result,
            "forge: invariant advisory — bounded output (output limit exceeded)",
        )
        self.assertLess(len(result.stdout.encode("utf-8")), 65_536)
        self.assertEqual(result.stderr, "")

    def test_advisory_metadata_cannot_amplify_output_beyond_the_cap(self) -> None:
        huge_name = "n" * 70_000
        self.commit_policy(f"| {huge_name} | exit 9 | hook |")

        result = self.invoke()

        self.assertLessEqual(len(result.stdout.encode("utf-8")), 65_536)
        response = json.loads(result.stdout)
        self.assertEqual(
            response["hookSpecificOutput"]["hookEventName"],
            "PostToolUse",
        )
        additional_context = response["hookSpecificOutput"]["additionalContext"]
        self.assertTrue(additional_context.startswith("forge: invariant advisory — n"))
        self.assertTrue(additional_context.endswith(" (exit 9)\n"))
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
