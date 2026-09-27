"""Provider, route, environment, and argv contracts for the review lane."""

from __future__ import annotations

import hashlib
import importlib
import json
import stat
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from tests._review_lane_support import ENGINE, ReviewLaneSupport
from tests.test_review_launch_streams import WrapperHarness

LAUNCH = importlib.import_module("forge_cli.engine._review_launch")
WRAPPER = importlib.import_module("forge_cli.engine._review_wrapper")
WRAPPER_IO = importlib.import_module("forge_cli.engine._review_wrapper_io")
ROUTE_CONFIG = LAUNCH.route_config


class ReviewLaunchProviderTests(ReviewLaneSupport, unittest.TestCase):
    @staticmethod
    def resolved_route() -> object:
        return ROUTE_CONFIG.ResolvedRoute(
            role="review-final",
            provider="claude",
            model="fable",
            effort="high",
            route_source="committed-default",
            route_sha256="a" * 64,
        )

    def test_committed_timeouts_and_probe_bounds_are_pinned(self) -> None:
        self.assertEqual(
            LAUNCH.PROFILE_TIMEOUT_SECONDS,
            {"review": 1200, "implementer": 3600, "plan": 1200},
        )
        self.assertEqual(LAUNCH.IDENTITY_DEADLINE_SECONDS, 60)
        self.assertEqual(LAUNCH.VERSION_PROBE_TIMEOUT_SECONDS, 10)
        self.assertEqual(LAUNCH.VERSION_PROBE_LIMIT_BYTES, 4096)
        self.assertEqual(LAUNCH.TERMINATE_GRACE_SECONDS, 5)

    def test_allowed_environment_filters_names_and_short_values(self) -> None:
        source = self.environment(
            LANG="C",
            LC_ALL="en_GB.UTF-8",
            GOOGLE_APPLICATION_CREDENTIALS="google-credential",
        )

        codex, codex_names, codex_short = LAUNCH.allowed_environment("codex", source)
        claude, claude_names, claude_short = LAUNCH.allowed_environment("claude", source)

        self.assertEqual(tuple(sorted(codex)), codex_names)
        self.assertEqual(tuple(sorted(claude)), claude_names)
        self.assertEqual(codex_short, ("LANG",))
        self.assertEqual(
            claude_short,
            ("CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "LANG"),
        )
        self.assertIn("CODEX_HOME", codex)
        self.assertNotIn("CODEX_HOME", claude)
        self.assertIn("ANTHROPIC_API_KEY", claude)
        self.assertIn("AWS_REGION", claude)
        self.assertIn("GOOGLE_APPLICATION_CREDENTIALS", claude)
        self.assertNotIn("FORGE_TEST_FORBIDDEN", codex)
        self.assertNotIn("FORGE_TEST_FORBIDDEN", claude)
        self.assertNotIn("LANG", codex)
        self.assertNotIn("LANG", claude)

    def test_environment_allowlist_control_is_load_bearing(self) -> None:
        source = self.environment(FORGE_TEST_FORBIDDEN="four-or-more")

        def assert_boundary() -> None:
            environment, names, _omitted = LAUNCH.allowed_environment("codex", source)
            self.assertNotIn("FORGE_TEST_FORBIDDEN", environment)
            self.assertEqual(names, tuple(sorted(environment)))

        assert_boundary()
        with (
            mock.patch.object(
                LAUNCH._PROBE_SUPPORT,
                "_allowed_environment",
                side_effect=lambda _provider, _environ=None: dict(source),
            ),
            self.assertRaises(AssertionError),
        ):
            assert_boundary()

    def test_route_resolution_returns_dm018_fields_and_profile_sandbox(self) -> None:
        resolved = ROUTE_CONFIG.ResolvedRoute(
            role="review-final",
            provider="codex",
            model="gpt-5.6-sol",
            effort="high",
            route_source="committed-default",
            route_sha256="a" * 64,
        )
        context = SimpleNamespace(repo=SimpleNamespace(root=self.worktree))
        with mock.patch.object(LAUNCH.route_config, "resolve", return_value=resolved) as call:
            route = LAUNCH.resolve_review_route(context, "review-final", "base-oid")

        call.assert_called_once_with(self.worktree, "review-final", "base-oid")
        self.assertEqual(route.role, "review-final")
        self.assertEqual(route.sandbox, "read-only")
        self.assertEqual(
            route.route_fields(),
            {
                "provider": "codex",
                "model": "gpt-5.6-sol",
                "effort": "high",
                "route_source": "committed-default",
                "route_sha256": "a" * 64,
            },
        )

    def test_route_refusal_diagnostic_is_preserved_verbatim(self) -> None:
        diagnostic = "forge: committed route refused — malformed fixture"
        context = SimpleNamespace(repo=SimpleNamespace(root=self.worktree))
        with (
            mock.patch.object(
                LAUNCH.route_config,
                "resolve",
                side_effect=ROUTE_CONFIG.RouteRefusal(diagnostic),
            ),
            self.assertRaises(ENGINE.Refusal) as caught,
        ):
            LAUNCH.resolve_review_route(context, "review-cheap", "base-oid")
        self.assertEqual(caught.exception.reason_code, ENGINE.ReasonCode.EVIDENCE_INCOMPLETE)
        self.assertEqual(caught.exception.message, diagnostic)

    def test_run_snapshot_missing_role_refusal_is_load_bearing(self) -> None:
        context = SimpleNamespace(repo=SimpleNamespace(root=self.worktree))

        def assert_refused() -> None:
            with self.assertRaises(ENGINE.Refusal) as caught:
                LAUNCH.resolve_review_route(context, "review-final", "base-oid")
            self.assertEqual(
                caught.exception.message,
                "forge: review request refused — role review-final has no frozen route "
                "in the run snapshot",
            )

        with (
            mock.patch.object(LAUNCH.route_config, "resolve", return_value=self.resolved_route()),
            mock.patch.object(LAUNCH, "_run_snapshot", return_value={}),
        ):
            assert_refused()
            with (
                mock.patch.object(LAUNCH, "_check_snapshot", return_value=None),
                self.assertRaises(AssertionError),
            ):
                assert_refused()

    def test_run_snapshot_refuses_each_divergent_dm018_field(self) -> None:
        context = SimpleNamespace(repo=SimpleNamespace(root=self.worktree))
        route = self.resolved_route()
        expected = {
            "provider": "claude",
            "model": "fable",
            "effort": "high",
            "route_source": "committed-default",
            "route_sha256": "a" * 64,
        }
        with mock.patch.object(LAUNCH.route_config, "resolve", return_value=route):
            for field in expected:
                snapshot_route = dict(expected)
                snapshot_route[field] = "divergent"
                with (
                    self.subTest(field=field),
                    mock.patch.object(
                        LAUNCH,
                        "_run_snapshot",
                        return_value={"review-final": snapshot_route},
                    ),
                    self.assertRaises(ENGINE.Refusal) as caught,
                ):
                    LAUNCH.resolve_review_route(context, "review-final", "base-oid")
                self.assertEqual(
                    caught.exception.message,
                    "forge: review request refused — route diverges from run snapshot "
                    f"for review-final: {field}",
                )

    def test_exact_codex_argv_for_both_review_roles(self) -> None:
        paths = self.paths()
        executable = str(self.bin_dir / "codex")
        expected = [
            executable,
            "exec",
            "--json",
            "--output-last-message",
            str(paths.staging_path),
            "-s",
            "read-only",
            "-c",
            "approval_policy=never",
            "-c",
            "model=gpt-5.6-sol",
            "-c",
            "model_reasoning_effort=high",
            "-C",
            str(self.worktree),
            "-",
        ]
        with mock.patch.object(LAUNCH, "CODEX_EXECUTABLE", executable):
            for role in ("review-cheap", "review-final"):
                with self.subTest(role=role):
                    self.assertEqual(
                        LAUNCH.reviewer_argv(
                            "codex", role, "gpt-5.6-sol", "high", paths
                        ),
                        expected,
                    )

    def test_exact_claude_argv_for_both_review_roles(self) -> None:
        paths = self.paths()
        executable = str(self.bin_dir / "claude")
        common = [
            executable,
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
        ]
        cases = {
            "review-cheap": (
                self.plugin_root / "system/claude/prompts/review-cheap.md",
                "Read,Grep,Glob,LS,Bash",
            ),
            "review-final": (paths.role_body_path, "Read,Bash,Glob,Grep,LS"),
        }
        with mock.patch.object(LAUNCH, "CLAUDE_EXECUTABLE", executable):
            for role, (body, tools) in cases.items():
                with self.subTest(role=role):
                    self.assertEqual(
                        LAUNCH.reviewer_argv("claude", role, "fable", "high", paths),
                        common
                        + [
                            str(body),
                            "--tools",
                            tools,
                            "--permission-prompts",
                            "none",
                        ],
                    )

    def test_review_final_body_is_derived_owner_only_and_digest_bound(self) -> None:
        source = self.plugin_root / "agents/review-final.md"
        source.parent.mkdir(parents=True)
        source.write_text(
            "---\nname: review-final\ndescription: fixture\n---\n"
            "# Final reviewer\n"
            "Read ${CLAUDE_PLUGIN_ROOT}/docs/policy.md.\n",
            encoding="utf-8",
        )

        path, body, digest = LAUNCH.materialize_review_final_body(
            self.plugin_root, self.attempt_dir
        )

        expected = (
            "# Final reviewer\n"
            f"Read {self.plugin_root}/docs/policy.md.\n"
        ).encode()
        self.assertEqual(body, expected)
        self.assertEqual(path.read_bytes(), expected)
        self.assertEqual(digest, hashlib.sha256(expected).hexdigest())
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(path.parent, self.attempt_dir)

    def test_claude_success_uses_is_error_not_subtype(self) -> None:
        capture = WRAPPER._EventCapture([])
        event = {
            "type": "result",
            "subtype": "error",
            "is_error": False,
            "result": "bound verdict",
        }
        _persisted, line_error = capture.line_bytes(
            json.dumps(event).encode(), terminated=True)

        verdict, error, _model = WRAPPER._capture_verdict(-1, "claude", capture, [])

        self.assertIsNone(line_error)
        self.assertEqual(verdict, b"bound verdict")
        self.assertIsNone(error)

    def test_claude_auth_and_not_logged_in_literals_are_pinned(self) -> None:
        capture = WRAPPER._EventCapture([])
        event = {
            "type": "result",
            "subtype": "success",
            "is_error": True,
            "result": "Not logged in - run /login",
        }
        capture.line_bytes(json.dumps(event).encode(), terminated=True)

        verdict, error, _model = WRAPPER._capture_verdict(-1, "claude", capture, [])

        self.assertEqual(verdict, b"")
        self.assertEqual(error, "not-logged-in")

        def finalize_error(disable: bool) -> str | None:
            state = {
                "config": {"provider": "claude"}, "error": None, "capture": capture,
                "stderr_raw": b"", "returncode": 9, "directory": -1,
                "patterns": [], "child": None,
                "capture_verdict": WRAPPER._capture_verdict,
            }
            captured = WRAPPER_IO._claude_capture(state, capture)
            with (
                mock.patch.object(
                    WRAPPER_IO, "_claude_capture", return_value=None if disable else captured
                ),
                mock.patch.object(WRAPPER_IO, "_publish_result", return_value=True) as publish,
            ):
                WRAPPER_IO._finalize(state)
            return publish.call_args.args[1]

        self.assertEqual(finalize_error(False), "not-logged-in")
        self.assertEqual(finalize_error(True), "provider exit 9")
        self.assertEqual(
            LAUNCH.CODEX_NOT_LOGGED_IN,
            "forge: codex launch refused — codex CLI is not logged in; "
            "run codex login manually and retry",
        )
        self.assertEqual(
            LAUNCH.CLAUDE_NOT_LOGGED_IN,
            "forge: claude launch refused — claude CLI is not logged in; "
            "run interactive /login manually and retry",
        )
    def test_claude_observed_model_uses_stream_evidence(self) -> None:
        capture = WRAPPER._EventCapture([])
        events = (
            {"type": "system", "subtype": "init", "model": "init-model"},
            {"type": "assistant", "message": {"model": "message-model"}},
            {
                "type": "result",
                "is_error": False,
                "result": "bound verdict",
                "modelUsage": {"usage-model": {"inputTokens": 1}},
            },
        )
        for event in events:
            _persisted, error = capture.line_bytes(
                json.dumps(event).encode(), terminated=True
            )
            self.assertIsNone(error)

        _verdict, error, observed = WRAPPER._capture_verdict(
            -1, "claude", capture, [])

        self.assertIsNone(error)
        self.assertEqual(observed, "usage-model")

    def test_provider_version_probe_accepts_both_exact_floors(self) -> None:
        cases = (
            ("codex", "codex-cli 0.155.0", "0.155.0"),
            ("claude", "2.1.278 (Claude Code)", "2.1.278"),
        )
        for provider, output, expected in cases:
            with self.subTest(provider=provider):
                environment, _names, _short = LAUNCH.allowed_environment(
                    provider, self.environment())
                executable = self.install_provider(provider, version=output)
                observed = LAUNCH.probe_provider_version(
                    provider, str(executable), environment, self.worktree
                )
                self.assertEqual(observed, expected)
                argv = json.loads(
                    (self.logs / f"{provider}.version-argv.json").read_text()
                )
                self.assertEqual(argv, ["--version"])
                child_environment = json.loads(
                    (self.logs / f"{provider}.version-environment.json").read_text()
                )
                self.assertNotIn("FORGE_TEST_FORBIDDEN", child_environment)

    def test_provider_version_probe_refuses_below_floor(self) -> None:
        environment, _names, _short = LAUNCH.allowed_environment("codex", self.environment())
        cases = (
            (
                "codex",
                "codex-cli 0.154.9",
                "forge: review request refused — codex version 0.154.9 "
                "is below required 0.155.0",
            ),
            (
                "claude",
                "2.1.277 (Claude Code)",
                "forge: review request refused — claude version 2.1.277 "
                "is below required 2.1.278",
            ),
        )
        for provider, output, diagnostic in cases:
            with self.subTest(provider=provider):
                executable = self.install_provider(provider, version=output)
                with self.assertRaises(ENGINE.Refusal) as caught:
                    LAUNCH.probe_provider_version(
                        provider, str(executable), environment, self.worktree
                    )
                self.assertEqual(caught.exception.message, diagnostic)

    def test_provider_version_probe_refuses_failed_and_unparseable_output(self) -> None:
        environment, _names, _short = LAUNCH.allowed_environment("codex", self.environment())
        cases = (
            (
                "version-nonzero",
                "forge: review request refused — codex version probe failed with exit 9",
            ),
            (
                "version-unparseable",
                "forge: review request refused — codex version output is unparseable",
            ),
            (
                "version-oversize",
                "forge: review request refused — codex version probe output exceeded 4096 bytes",
            ),
            (
                "version-oversize-stderr",
                "forge: review request refused — codex version probe output exceeded 4096 bytes",
            ),
        )
        for mode, diagnostic in cases:
            with self.subTest(mode=mode):
                executable = self.install_provider("codex", mode=mode)
                with self.assertRaises(ENGINE.Refusal) as caught:
                    LAUNCH.probe_provider_version(
                        "codex", str(executable), environment, self.worktree
                    )
                self.assertEqual(caught.exception.message, diagnostic)

    def test_provider_version_probe_is_bounded_and_uses_a_new_session(self) -> None:
        executable = self.install_provider("codex", mode="version-hang")
        environment, _names, _short = LAUNCH.allowed_environment("codex", self.environment())
        real_popen = LAUNCH.subprocess.Popen
        observed: list[bool] = []

        def record_popen(*args: object, **kwargs: object) -> object:
            observed.append(bool(kwargs.get("start_new_session")))
            return real_popen(*args, **kwargs)  # type: ignore[arg-type]

        started = time.monotonic()
        with (
            mock.patch.object(LAUNCH, "VERSION_PROBE_TIMEOUT_SECONDS", 0.05),
            mock.patch.object(LAUNCH, "TERMINATE_GRACE_SECONDS", 0.05),
            mock.patch.object(LAUNCH.subprocess, "Popen", side_effect=record_popen),
            self.assertRaises(ENGINE.Refusal) as caught,
        ):
            LAUNCH.probe_provider_version(
                "codex", str(executable), environment, self.worktree
            )
        self.assertLess(time.monotonic() - started, 2.0)
        self.assertEqual(observed, [True])
        self.assertIn("codex version probe timed out", caught.exception.message)

    def test_missing_provider_executable_refuses_before_launch(self) -> None:
        environment, _names, _short = LAUNCH.allowed_environment("codex", self.environment())
        missing = self.bin_dir / "missing-codex"
        with self.assertRaises(ENGINE.Refusal) as caught:
            LAUNCH.probe_provider_version(
                "codex", str(missing), environment, self.worktree
            )
        self.assertTrue(
            caught.exception.message.startswith(
                "forge: review request refused — codex executable is unavailable:"
            )
        )


class ProviderAuthWrapperTests(WrapperHarness):
    def test_claude_nonzero_auth_result_is_not_logged_in(self) -> None:
        cases = (
            ("auth", True, "Not logged in - run /login", "not-logged-in"),
            ("success", False, "VERDICT: PASS", "provider exit 9"),
        )
        for label, is_error, result, expected in cases:
            event = json.dumps({"type": "result", "is_error": is_error, "result": result})
            source = f"import sys;sys.stdin.read();print({event!r});raise SystemExit(9)"
            process, attempt = self.launch(f"claude-{label}-nonzero", source)
            completion = self.completion(process, attempt)
            self.assertEqual((completion["error"], completion["returncode"]), (expected, 9))

    def test_codex_bounded_401_event_and_stderr_are_not_logged_in(self) -> None:
        event = json.dumps({"type": "error", "message": "HTTP 401: authentication required"})
        cases = {
            "event": f"import sys;sys.stdin.read();print({event!r});raise SystemExit(9)",
            "stderr": "import sys;sys.stdin.read();print('HTTP 401: authentication required',"
            "file=sys.stderr);raise SystemExit(9)",
        }
        for label, source in cases.items():
            with self.subTest(label=label):
                process, attempt = self.launch(label, source, settings=("codex", 5))
                completion = self.completion(process, attempt)
                self.assertEqual(completion["error"], "not-logged-in")
        self.assertFalse(WRAPPER_IO._codex_auth_event(event.replace("401", "1401").encode()))
        self.assertFalse(WRAPPER_IO._status_401(b"HTTP 4010 authentication required"))
        with mock.patch.object(WRAPPER_IO, "_status_401", return_value=False):
            with self.assertRaises(AssertionError):
                self.assertTrue(WRAPPER_IO._codex_auth_event(event.encode()))


class ReviewLaunchBoundaryTests(ReviewLaneSupport, unittest.TestCase):
    def test_post_spawn_reaper_failure_cannot_reclassify_launch(self) -> None:
        process = SimpleNamespace(wait=mock.Mock())
        with mock.patch.object(
            WRAPPER.threading.Thread,
            "start",
            side_effect=RuntimeError("fixture thread exhaustion"),
        ):
            WRAPPER.reap_detached(process)
        process.wait.assert_not_called()

    def test_argv_controls_are_load_bearing(self) -> None:
        paths = self.paths()

        def assert_controls() -> None:
            argv = LAUNCH.reviewer_argv(
                "codex", "review-final", "gpt-5.6-sol", "high", paths
            )
            self.assertIn("--json", argv)
            self.assertIn("approval_policy=never", argv)
            self.assertIn("read-only", argv)

        assert_controls()
        real = LAUNCH.reviewer_argv
        with (
            mock.patch.object(
                LAUNCH,
                "reviewer_argv",
                side_effect=lambda *args, **kwargs: [
                    item
                    for item in real(*args, **kwargs)
                    if item not in {"--json", "approval_policy=never", "read-only"}
                ],
            ),
            self.assertRaises(AssertionError),
        ):
            assert_controls()


if __name__ == "__main__":
    unittest.main()
