from __future__ import annotations

import json
import os
import signal
import time
from unittest import mock

from tests.test_route_config_support import ROOT, route_config_probe


class RouteProbeMixin:
    def test_probe_bounds_are_fixed(self) -> None:
        self.assertEqual(route_config_probe.PROBE_TIMEOUT_SECONDS, 120)
        self.assertEqual(route_config_probe.TERMINATE_GRACE_SECONDS, 5)
        self.assertEqual(route_config_probe.STDOUT_LIMIT_BYTES, 16 * 1024 * 1024)
        self.assertEqual(route_config_probe.STDERR_LIMIT_BYTES, 1024 * 1024)

    def test_codex_probe_uses_exact_argv_scratch_and_allowlisted_environment(self) -> None:
        args_log = self.scratch / "codex.args"
        cwd_log = self.scratch / "codex.cwd"
        env_log = self.scratch / "codex.env"
        self.fake_executable(
            "codex",
            f"""printf '%s\\n' "$@" > {self.shell_path(args_log)}
pwd > {self.shell_path(cwd_log)}
printf '%s\\n' "${{FORGE_SESSION_PID-unset}}" "${{CLAUDE_PID-unset}}" \
  "${{CODEX_HOME-unset}}" "${{CODEX_UNSAFE-unset}}" > {self.shell_path(env_log)}
printf 'probe ok\\n' > "$4"
printf '{{"type":"turn.completed"}}\\n'
""",
        )
        spec = route_config_probe.ProbeSpec(
            "codex", "gpt-5.6-sol", "high", ("review-cheap",)
        )
        outcome = route_config_probe.probe_routes(
            self.repo,
            ROOT,
            [spec],
            environ=self.probe_environment(),
        )[0]
        self.assertTrue(outcome.ok, outcome)
        report = outcome.report
        self.assertIsNone(report["observed_model"])
        self.assertEqual(report["permission_denials"], [])
        cwd = cwd_log.read_text(encoding="utf-8").strip()
        self.assertTrue(cwd.startswith(str(self.repo / ".forge/tmp/route-probe/probe-")))
        self.assertEqual(
            args_log.read_text(encoding="utf-8").splitlines(),
            [
                "exec",
                "--json",
                "--output-last-message",
                f"{cwd}/last-message.txt",
                "-s",
                "read-only",
                "-c",
                "approval_policy=never",
                "-c",
                "model=gpt-5.6-sol",
                "-c",
                "model_reasoning_effort=high",
                "-C",
                cwd,
                "-",
            ],
        )
        expected_names = {
            "HOME",
            "PATH",
            "LANG",
            "LC_ALL",
            "USER",
            "TMPDIR",
            "TERM",
            "CODEX_HOME",
        }
        self.assertEqual(set(report["environment_names"]), expected_names)
        self.assertEqual(
            env_log.read_text().splitlines(),
            ["unset", "unset", str(self.scratch / "codex-home"), "unset"],
        )
        self.assertEqual(list((self.repo / ".forge/tmp/route-probe").iterdir()), [])

    def test_claude_probe_uses_plan_profile_and_records_stream_evidence(self) -> None:
        args_log = self.scratch / "claude.args"
        cwd_log = self.scratch / "claude.cwd"
        env_log = self.scratch / "claude.env"
        self.fake_executable(
            "claude",
            f"""printf '%s\\n' "$@" > {self.shell_path(args_log)}
pwd > {self.shell_path(cwd_log)}
printf '%s\\n' "${{FORGE_SESSION_PID-unset}}" "${{CLAUDE_PID-unset}}" \
  "${{CLAUDE_CODE_SESSION_ID-unset}}" "${{ANTHROPIC_MODEL-unset}}" \
  > {self.shell_path(env_log)}
printf '%s\\n' '{{"type":"system","subtype":"init","model":"init-model"}}'
printf '%s\\n' '{{"type":"assistant","message":{{"model":"assistant-model"}}}}'
printf '%s\\n' '{{"type":"result","is_error":false,"subtype":"success",\
"result":"ok","permission_denials":["Bash touch DENY_ME.txt"]}}'
""",
        )
        spec = route_config_probe.ProbeSpec("claude", "fable", "high", ("plan",))
        outcome = route_config_probe.probe_routes(
            self.repo,
            ROOT,
            [spec],
            environ=self.probe_environment(),
        )[0]
        self.assertTrue(outcome.ok, outcome)
        self.assertEqual(outcome.report["observed_model"], "assistant-model")
        self.assertEqual(
            outcome.report["permission_denials"],
            ["Bash touch DENY_ME.txt"],
        )
        cwd = cwd_log.read_text().strip()
        self.assertEqual(
            args_log.read_text().splitlines(),
            [
                "-p",
                "--safe-mode",
                "--strict-mcp-config",
                "--output-format",
                "stream-json",
                "--verbose",
                "--model",
                "fable",
                "--effort",
                "high",
                "--system-prompt-file",
                str(ROOT / "system/claude/prompts/plan.md"),
                "--tools",
                "Read,Grep,Glob,LS",
                "--permission-prompts",
                "none",
            ],
        )
        self.assertTrue(cwd.startswith(str(self.repo / ".forge/tmp/route-probe/probe-")))
        self.assertEqual(env_log.read_text().splitlines(), ["unset"] * 4)
        expected_names = {
            "HOME", "PATH", "LANG", "LC_ALL", "USER", "TMPDIR", "TERM",
            "ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY",
            "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLOUD_ML_REGION",
            "AWS_REGION", "GOOGLE_APPLICATION_CREDENTIALS",
        }
        self.assertEqual(set(outcome.report["environment_names"]), expected_names)

    def test_codex_stdout_and_stderr_401_are_detected_early(self) -> None:
        scripts = (
            "printf '%s\\n' '{\"type\":\"error\",\"message\":\"401 Unauthorized\"}'; sleep 10\n",
            "printf '%s\\n' '401 Unauthorized' >&2; sleep 10\n",
        )
        spec = route_config_probe.ProbeSpec("codex", "gpt-5.6-sol", "high", ("plan",))
        for index, body in enumerate(scripts):
            with self.subTest(stream=index):
                self.fake_executable("codex", body)
                started = time.monotonic()
                outcome = route_config_probe.probe_routes(
                    self.repo,
                    ROOT,
                    [spec],
                    environ=self.probe_environment(),
                )[0]
                self.assertLess(time.monotonic() - started, 2.0)
                self.assertEqual(
                    outcome.diagnostic,
                    "forge: codex launch refused — codex CLI is not logged in; "
                    "run codex login manually and retry",
                )

    def test_claude_not_logged_in_ignores_misleading_success_subtype(self) -> None:
        self.fake_executable(
            "claude",
            "printf '%s\\n' '{\"type\":\"result\",\"is_error\":true,"
            "\"subtype\":\"success\",\"result\":\"Not logged in · Please run /login\"}'; "
            "sleep 10\n",
        )
        spec = route_config_probe.ProbeSpec("claude", "fable", "high", ("plan",))
        started = time.monotonic()
        outcome = route_config_probe.probe_routes(
            self.repo,
            ROOT,
            [spec],
            environ=self.probe_environment(),
        )[0]
        self.assertLess(time.monotonic() - started, 2.0)
        self.assertEqual(
            outcome.diagnostic,
            "forge: claude launch refused — claude CLI is not logged in; "
            "run interactive /login manually and retry",
        )

    def test_timeout_escalates_to_sigkill_for_term_ignoring_process_group(self) -> None:
        child_started = self.scratch / "child.started"
        survivor = self.scratch / "child.survived"
        self.fake_executable(
            "codex",
            f"""trap '' TERM
sh -c 'trap "" TERM; printf started > {self.shell_path(child_started)}; \
sleep 0.4; printf survived > {self.shell_path(survivor)}; while :; do sleep 1; done' &
while [ ! -f {self.shell_path(child_started)} ]; do :; done
while :; do :; done
""",
        )
        spec = route_config_probe.ProbeSpec("codex", "gpt-5.6-sol", "high", ("plan",))
        with (
            mock.patch.object(route_config_probe, "PROBE_TIMEOUT_SECONDS", 0.2),
            mock.patch.object(route_config_probe, "TERMINATE_GRACE_SECONDS", 0.05),
        ):
            outcome = route_config_probe.probe_routes(
                self.repo,
                ROOT,
                [spec],
                environ=self.probe_environment(),
            )[0]
        time.sleep(0.45)
        self.assertTrue(child_started.exists())
        self.assertFalse(survivor.exists())
        self.assertTrue(outcome.report["timed_out"])
        self.assertEqual(outcome.report["returncode"], -signal.SIGKILL)
        self.assertEqual(
            outcome.diagnostic,
            "forge: codex launch refused — route probe timed out",
        )

    def test_output_caps_kill_group_and_keep_captured_bytes_bounded(self) -> None:
        child_started = self.scratch / "cap-child.started"
        survivor = self.scratch / "cap-child.survived"
        self.fake_executable(
            "codex",
            f"""trap '' TERM
sh -c 'trap "" TERM; printf started > {self.shell_path(child_started)}; \
sleep 0.4; printf survived > {self.shell_path(survivor)}; while :; do sleep 1; done' &
while [ ! -f {self.shell_path(child_started)} ]; do :; done
printf '%4096s' x
while :; do :; done
""",
        )
        observed = []
        real_outcome = route_config_probe._codex_outcome

        def capture_launch(*args: object, **kwargs: object) -> object:
            observed.append(args[1])
            return real_outcome(*args, **kwargs)  # type: ignore[arg-type]

        spec = route_config_probe.ProbeSpec("codex", "gpt-5.6-sol", "high", ("plan",))
        with (
            mock.patch.object(route_config_probe, "STDOUT_LIMIT_BYTES", 1024),
            mock.patch.object(route_config_probe, "TERMINATE_GRACE_SECONDS", 0.05),
            mock.patch.object(route_config_probe, "_codex_outcome", side_effect=capture_launch),
        ):
            outcome = route_config_probe.probe_routes(
                self.repo, ROOT, [spec], environ=self.probe_environment()
            )[0]
        time.sleep(0.45)
        self.assertTrue(child_started.exists())
        self.assertFalse(survivor.exists())
        self.assertEqual(len(observed[0].stdout), 1024)
        self.assertEqual(outcome.report["output_limit"], "stdout")
        self.assertEqual(outcome.report["returncode"], -signal.SIGKILL)
        self.assertEqual(
            outcome.diagnostic,
            "forge: codex launch refused — route probe stdout exceeded limit",
        )

    def test_probe_refuses_live_scratch_ancestor_symlink(self) -> None:
        outside = self.scratch / "outside-probe"
        outside.mkdir()
        forge = self.repo / ".forge"
        forge.mkdir()
        (forge / "tmp").symlink_to(outside, target_is_directory=True)
        spec = route_config_probe.ProbeSpec("codex", "gpt-5.6-sol", "high", ("plan",))
        outcome = route_config_probe.probe_routes(
            self.repo, ROOT, [spec], environ=self.probe_environment()
        )[0]
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual(
            outcome.diagnostic,
            "forge: route probe refused — unsafe scratch directory",
        )

    def test_stderr_cap_is_enforced_independently(self) -> None:
        self.fake_executable(
            "codex",
            "trap '' TERM\nprintf '%2048s' x >&2\nwhile :; do :; done\n",
        )
        spec = route_config_probe.ProbeSpec("codex", "gpt-5.6-sol", "high", ("plan",))
        with (
            mock.patch.object(route_config_probe, "STDERR_LIMIT_BYTES", 512),
            mock.patch.object(route_config_probe, "TERMINATE_GRACE_SECONDS", 0.05),
        ):
            outcome = route_config_probe.probe_routes(
                self.repo, ROOT, [spec], environ=self.probe_environment()
            )[0]
        self.assertEqual(outcome.report["output_limit"], "stderr")
        self.assertEqual(outcome.report["returncode"], -signal.SIGKILL)
        self.assertEqual(
            outcome.diagnostic,
            "forge: codex launch refused — route probe stderr exceeded limit",
        )

    def test_duplicate_pairs_launch_once_and_merge_roles_in_encounter_order(self) -> None:
        counter = self.scratch / "launches"
        self.fake_executable(
            "codex",
            f"printf x >> {self.shell_path(counter)}\nprintf ok > \"$4\"\n",
        )
        specs = [
            route_config_probe.ProbeSpec("codex", "gpt-5.6-sol", "high", ("review-cheap",)),
            route_config_probe.ProbeSpec("codex", "gpt-5.6-sol", "high", ("plan",)),
        ]
        outcomes = route_config_probe.probe_routes(
            self.repo,
            ROOT,
            specs,
            environ=self.probe_environment(),
        )
        self.assertEqual(counter.read_bytes(), b"x")
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0].report["roles"], ["review-cheap", "plan"])

    def test_probe_cli_reports_one_json_line_per_distinct_default_pair(self) -> None:
        self.fake_executable("codex", "printf ok > \"$4\"\n")
        self.fake_executable(
            "claude",
            "printf '%s\\n' '{\"type\":\"result\",\"is_error\":false,\"result\":\"ok\"}'\n",
        )
        with mock.patch.dict(os.environ, self.probe_environment(), clear=True):
            status, stdout, stderr = self.invoke("probe", "--repo", str(self.repo))
        reports = [json.loads(line) for line in stdout.splitlines()]
        self.assertEqual((status, stderr), (0, ""))
        self.assertEqual(len(reports), 3)
        matching = (
            report
            for report in reports
            if report["effort"] == "high" and report["provider"] == "codex"
        )
        self.assertEqual(next(matching)["roles"], ["review-cheap", "plan"])

    def test_probe_cli_emits_failed_report_diagnostic_and_exit_one(self) -> None:
        self.fake_executable(
            "codex",
            "printf '%s\\n' '{\"type\":\"error\",\"message\":\"401 Unauthorized\"}'; "
            "sleep 10\n",
        )
        with mock.patch.dict(os.environ, self.probe_environment(), clear=True):
            status, stdout, stderr = self.invoke(
                "probe", "--repo", str(self.repo), "--role", "plan"
            )
        reports = stdout.splitlines()
        self.assertEqual(status, 1)
        self.assertEqual(len(reports), 1)
        self.assertFalse(json.loads(reports[0])["ok"])
        self.assertEqual(
            stderr,
            "forge: codex launch refused — codex CLI is not logged in; "
            "run codex login manually and retry\n",
        )

    def test_environment_allowlist_disable_control_is_load_bearing(self) -> None:
        source = self.probe_environment()

        def assert_control() -> None:
            child = route_config_probe._allowed_environment("claude", source)
            self.assertNotIn("FORGE_SESSION_PID", child)
            self.assertNotIn("CLAUDE_PID", child)
            self.assertNotIn("ANTHROPIC_MODEL", child)
            self.assertNotIn("CODEX_UNSAFE", child)

        assert_control()
        with mock.patch.object(
            route_config_probe,
            "_allowed_environment",
            side_effect=lambda _provider, _source=None: dict(source),
        ):
            with self.assertRaises(AssertionError):
                assert_control()
