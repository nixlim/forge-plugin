"""Focused preflight and owner-publication tests for typed launch start."""

from __future__ import annotations

import concurrent.futures
import copy
import dataclasses
import errno
import json
import os
import shutil
import stat
import subprocess
import threading
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from tests._cli_loader import patch_engine
from tests._launch_support import (
    ENGINE,
    LAUNCH_LANE,
    STRIPPED_PATH,
    VERBS_LAUNCH,
    LaunchLaneSupport,
)

from codex_orchestrator import builders, journal


class _LaunchVerbSupport(LaunchLaneSupport):
    def _assert_clean_refusal(
        self,
        engine: object,
        invoke: object,
        code: object,
        message: str,
    ) -> ENGINE.Refusal:
        before = self.records()
        with self.assertRaises(ENGINE.Refusal) as caught:
            invoke()
        self.assertIs(caught.exception.reason_code, code)
        self.assertEqual(caught.exception.message, message)
        self.assertEqual(self.records(), before)
        self._assert_no_attempt()
        return caught.exception


class LaunchVerbPreflightTests(_LaunchVerbSupport, unittest.TestCase):
    def test_halt_is_v2_and_precedes_every_launch_write(self) -> None:
        engine = self.ready_engine()
        (self.repo / "AGENT_HALT").write_text("operator pause\n", encoding="utf-8")
        self._assert_clean_refusal(
            engine,
            lambda: self.seed_launch(engine=engine),
            ENGINE.V2ReasonCode.HALT_ENGAGED,
            "operator halt check refused state mutation",
        )

    def test_unregistered_and_main_implementer_worktrees_refuse_cleanly(self) -> None:
        engine = self.ready_engine()
        foreign, _head = self._new_repo("foreign")
        cases = (
            (
                foreign,
                "forge: launch refused — worktree is not a registered worktree "
                f"of this repository: {foreign}",
            ),
            (
                self.repo,
                "forge: launch refused — implementer worktree must be a dedicated "
                f"linked worktree: {self.repo}",
            ),
        )
        for worktree, message in cases:
            with self.subTest(worktree=worktree):
                self._assert_clean_refusal(
                    engine,
                    lambda worktree=worktree: self.seed_launch(
                        engine=engine, worktree=worktree
                    ),
                    ENGINE.V2ReasonCode.WORKTREE_INVALID,
                    message,
                )

    def test_worktree_registration_control_is_load_bearing(self) -> None:
        engine = self.ready_engine()
        foreign, _head = self._new_repo("foreign-disable")
        expected = (
            "forge: launch refused — worktree is not a registered worktree of "
            f"this repository: {foreign}"
        )

        def assertion() -> None:
            with self.assertRaises(ENGINE.Refusal) as caught:
                self.seed_launch(engine=engine, worktree=foreign)
            self.assertEqual(caught.exception.message, expected)

        assertion()
        with mock.patch.object(
            VERBS_LAUNCH,
            "_validate_worktree",
            return_value=(self.linked_worktree, self.head),
        ):
            with self.assertRaises(AssertionError):
                assertion()

    def test_initialization_and_active_task_checks_leave_no_attempt(self) -> None:
        engine = self.ready_engine()
        before = self.records()
        with self.assertRaises(ENGINE.Refusal) as inactive:
            VERBS_LAUNCH.launch(
                engine,
                role="implementer",
                task="task-99",
                worktree=str(self.linked_worktree),
                brief=str(self.brief),
            )
        self.assertEqual(
            inactive.exception.message,
            "forge: journal builder refused — task task-99 is not active",
        )
        self.assertEqual(self.records(), before)
        self._assert_no_attempt()

        manifest = self.linked_worktree / ".forge-manifest"
        manifest.write_text("init_completed: false\n", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(self.linked_worktree), "add", ".forge-manifest"],
            check=True,
        )
        subprocess.run(
            [
                "git", "-C", str(self.linked_worktree), "-c",
                "user.name=Forge Tests", "-c",
                "user.email=forge-tests@example.invalid", "commit", "--quiet",
                "-m", "incomplete manifest",
            ],
            check=True,
        )
        self._assert_clean_refusal(
            engine,
            lambda: self.seed_launch(engine=engine),
            ENGINE.V2ReasonCode.STATE_PRECONDITION,
            "forge: forge initialization incomplete — run /forge:init",
        )

    def test_route_refusal_is_verbatim_and_write_free(self) -> None:
        engine = self.ready_engine()
        routes = self.repo / ".forge/local/routes.toml"
        routes.parent.mkdir(parents=True, exist_ok=True)
        routes.write_text("# no schema\n", encoding="utf-8")
        routes.chmod(0o600)
        exclude = self.repo / ".git/info/exclude"
        exclude.write_text("/.forge/local/\n", encoding="utf-8")
        self._assert_clean_refusal(
            engine,
            lambda: self.seed_launch(engine=engine),
            ENGINE.V2ReasonCode.STATE_PRECONDITION,
            "forge: routes file refused — missing schema",
        )

    def test_every_snapshot_divergence_is_named_before_writes(self) -> None:
        engine = self.ready_engine()
        route = VERBS_LAUNCH.route_config.resolve(
            self.linked_worktree, "implementer", self.head
        )
        cases = {
            "provider": "claude",
            "model": "different-model",
            "effort": "low",
            "route_source": "local",
            "route_sha256": "0" * 64,
        }
        for field, value in cases.items():
            with self.subTest(field=field), mock.patch.object(
                VERBS_LAUNCH.route_config,
                "resolve",
                return_value=dataclasses.replace(route, **{field: value}),
            ):
                self._assert_clean_refusal(
                    engine,
                    lambda: self.seed_launch(engine=engine),
                    ENGINE.V2ReasonCode.INGEST_PROOF_INVALID,
                    "forge: execution refused — route diverges from run snapshot "
                    f"for implementer: {field}",
                )
        with mock.patch.object(
            VERBS_LAUNCH, "_resolve_route", return_value=(route, "read-only")
        ):
            self._assert_clean_refusal(
                engine,
                lambda: self.seed_launch(engine=engine),
                ENGINE.V2ReasonCode.INGEST_PROOF_INVALID,
                "forge: execution refused — route diverges from run snapshot "
                "for implementer: sandbox",
            )

    def test_missing_frozen_route_refuses_before_writes(self) -> None:
        engine = self.ready_engine()
        run = LAUNCH_LANE.run_state(engine.ctx, self.run_id)
        state = run.state
        records = list(state.records)
        opening = copy.deepcopy(records[0])
        opening["route"].pop("implementer")
        records[0] = opening
        synthetic = dataclasses.replace(state, records=tuple(records))
        with mock.patch.object(
            LAUNCH_LANE,
            "run_state",
            return_value=dataclasses.replace(run, state=synthetic),
        ):
            self._assert_clean_refusal(
                engine,
                lambda: self.seed_launch(engine=engine),
                ENGINE.V2ReasonCode.INGEST_PROOF_INVALID,
                "forge: execution refused — role implementer has no frozen route "
                "in the run snapshot",
            )

    def test_snapshot_comparison_control_is_load_bearing(self) -> None:
        engine = self.ready_engine()
        route = VERBS_LAUNCH.route_config.resolve(
            self.linked_worktree, "implementer", self.head
        )

        def assertion() -> None:
            with self.assertRaises(ENGINE.Refusal) as caught:
                self.seed_launch(engine=engine)
            self.assertIn("route diverges", caught.exception.message)

        with mock.patch.object(
            VERBS_LAUNCH.route_config,
            "resolve",
            return_value=dataclasses.replace(route, model="different-model"),
        ):
            assertion()
            with mock.patch.object(
                VERBS_LAUNCH.route_evidence, "validate_execution", return_value=None
            ):
                with self.assertRaises(AssertionError):
                    assertion()

    def test_missing_cli_and_floor_refusals_use_explicit_executables(self) -> None:
        engine = self.ready_engine()
        missing = self.scratch / "definitely-missing-codex"
        with patch_engine("CODEX_EXECUTABLE", str(missing)):
            self._assert_clean_refusal(
                engine,
                lambda: self.seed_launch(engine=engine),
                ENGINE.V2ReasonCode.EVIDENCE_INCOMPLETE,
                "forge: codex launch refused — codex CLI could not be started",
            )

        self.install_provider("codex", version="codex-cli 0.154.9")
        self._assert_clean_refusal(
            engine,
            lambda: self.seed_launch(engine=engine),
            ENGINE.V2ReasonCode.EVIDENCE_INCOMPLETE,
            "forge: launch refused — codex version 0.154.9 is below required 0.155.0",
        )

    def test_missing_cli_check_is_load_bearing(self) -> None:
        engine = self.ready_engine()
        missing = self.scratch / "missing-control-codex"

        def assertion() -> None:
            with self.assertRaises(ENGINE.Refusal) as caught:
                self.seed_launch(engine=engine)
            self.assertEqual(
                caught.exception.message,
                "forge: codex launch refused — codex CLI could not be started",
            )

        with patch_engine("CODEX_EXECUTABLE", str(missing)):
            assertion()
            with mock.patch.object(VERBS_LAUNCH.shutil, "which", return_value=str(missing)):
                with self.assertRaises(AssertionError):
                    assertion()


class LaunchVerbOwnerTests(_LaunchVerbSupport, unittest.TestCase):
    def test_launch_fake_can_emit_either_duplicate_permission_precedence(self) -> None:
        for mode, expected in (
            ("permission-mode-first", "acceptEdits"),
            ("permission-mode-last", "default"),
        ):
            with self.subTest(mode=mode):
                executable = self.install_mode_provider("claude", mode)
                process = subprocess.run(
                    [
                        str(executable),
                        "--permission-mode", "",
                        "--permission-mode", "-p",
                        "--permission-mode", "acceptEdits",
                        "--permission-mode", "default",
                        "--tools", "Read,Grep",
                        "--permission-mode",
                    ],
                    input=b"",
                    capture_output=True,
                    env=self.environment(),
                    check=True,
                )
                init = json.loads(process.stdout.splitlines()[0])
                self.assertEqual(init["permissionMode"], expected)
                self.assertEqual(init["tools"], ["Read", "Grep"])

    def test_claude_plan_redacts_handoff_and_validated_init_value_matches(self) -> None:
        home = "/home/agents/launch-fixture"
        planted = "anthropic-launch-secret"
        self.install_provider("claude", mode="redaction-handoff")
        self.configure_route("plan", "claude")
        with mock.patch.dict(
            os.environ,
            {
                "USER": "agents",
                "HOME": home,
                "ANTHROPIC_API_KEY": planted,
                "AWS_PROFILE": "default",
                "AWS_REGION": "Read",
            },
        ):
            self.launch_direct(
                role="plan", engine=self.ready_engine(), worktree=self.repo
            )
        record = self.execution_records()[0]
        completion_path = self.attempt_dir(record) / "completion.json"
        deadline = time.monotonic() + 10
        while not completion_path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(completion_path.exists())
        completion = json.loads(completion_path.read_text(encoding="utf-8"))
        handoff = (self.attempt_dir(record) / "handoff.md").read_text(encoding="utf-8")
        events = [
            json.loads(line)
            for line in (self.attempt_dir(record) / "events.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        self.assertIsNone(completion["error"])
        self.assertEqual(events[0]["permissionMode"], "<redacted:AWS_PROFILE>")
        self.assertIn("<redacted:AWS_REGION>", events[0]["tools"])
        self.assertIn("agents/review-final.md", handoff)
        self.assertIn("user=agents", handoff)
        self.assertIn("home=<redacted:HOME>", handoff)
        self.assertIn("planted=<redacted:ANTHROPIC_API_KEY>", handoff)
        self.assertNotIn(home, handoff)
        self.assertNotIn(planted, handoff)

    def test_owner_files_precede_record_and_record_binds_marker(self) -> None:
        engine = self.ready_engine()
        original = builders.execution_start
        observed: list[bool] = []

        def inspect_then_append(*args: object, **kwargs: object) -> object:
            marker = self.run_dir(self.repo, self.run_id) / str(kwargs["launch_marker"])
            directory = marker.parent
            observed.append(
                marker.is_file()
                and (directory / "prompt.md").is_file()
                and (directory / "events.jsonl").read_bytes() == b""
                and not (directory / "identity.json").exists()
            )
            return original(*args, **kwargs)

        with mock.patch.object(builders, "execution_start", side_effect=inspect_then_append):
            self.seed_launch(engine=engine)
        self.assertEqual(observed, [True])
        record = self.execution_records()[0]
        marker = self.marker(record)
        self.assertEqual(record["mode"], "detached")
        self.assertEqual(record["event_source"], "exec")
        self.assertEqual(
            record["launch_marker"],
            f"{record['agent']}/{record['execution']}/launch.json",
        )
        for field in ("sandbox", "route_source", "route_sha256"):
            self.assertEqual(record[field], marker[field])

    def test_marker_config_pid_and_minted_attempt_are_exact(self) -> None:
        engine = self.ready_engine()
        fixed_attempt = "attempt-0123456789abcdef"
        agent_dir = self.run_dir(self.repo, self.run_id) / "codex-implementer-01"
        real_launcher = VERBS_LAUNCH._review_lane_api.wrapper_launcher

        def tagged_launcher(*args: object, **kwargs: object) -> tuple[object, ...]:
            config_json, launcher_argv, _digest = real_launcher(*args, **kwargs)
            return config_json, launcher_argv, "f" * 64

        with (
            patch_engine(
                "new_attempt_id", new=lambda: (
                    self.assertTrue(agent_dir.is_dir()), fixed_attempt)[1]),
            patch_engine("wrapper_launcher", side_effect=tagged_launcher),
            patch_engine("spawn_wrapper", return_value=SimpleNamespace(pid=424_242)) as spawn,
        ):
            outcome = self.launch_direct(engine=engine)
        record = self.execution_records()[0]
        directory = self.attempt_dir(record)
        marker = self.marker(record)
        launcher_argv = tuple(spawn.call_args.args[0])
        config = json.loads(launcher_argv[-1])
        self.assertEqual(set(marker), LAUNCH_LANE.MARKER_KEYS)
        self.assertEqual(marker["attempt"], fixed_attempt)
        self.assertRegex(marker["attempt"], r"^attempt-[0-9a-f]{16}$")
        self.assertEqual(marker["launcher_argv_digest"], "f" * 64)
        self.assertEqual(
            config["leaves"],
            {
                "prompt": "prompt.md", "events": "events.jsonl",
                "stderr": "stderr.log", "capture": "handoff.md",
                "staging": "handoff.staging",
            },
        )
        self.assertIs(config["events_existing"], True)
        self.assertIsNone(config["role_body_digest"])
        self.assertEqual(
            config["timeout"],
            VERBS_LAUNCH._review_launch.PROFILE_TIMEOUT_SECONDS["implementer"],
        )
        self.assertEqual(config["grace"], VERBS_LAUNCH._review_launch.TERMINATE_GRACE_SECONDS)
        self.assertEqual(config["environment_names"], marker["environment_names"])
        self.assertEqual(config["omitted_short"], marker["omitted_short"])
        pid_lines = (directory / "pid").read_text(encoding="ascii").splitlines()
        self.assertEqual(pid_lines[:2], ["424242", "424242"])
        VERBS_LAUNCH.chain_core.parse_time(pid_lines[2])
        self.assertEqual(outcome.reason_code, ENGINE.V2ReasonCode.OK)
        self.assertEqual(
            tuple(outcome.evidence_refs),
            (f"{record['agent']}/{record['execution']}/prompt.md", str(record["launch_marker"])),
        )
        self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
        for name in ("prompt.md", "events.jsonl", "launch.json"):
            self.assertEqual(stat.S_IMODE((directory / name).stat().st_mode), 0o600)

    def test_claude_plan_record_and_timeout_use_the_plan_profile(self) -> None:
        self.configure_route("plan", "claude")
        engine = self.ready_engine()
        with patch_engine(
            "spawn_wrapper", return_value=SimpleNamespace(pid=424_242)
        ) as spawn:
            self.launch_direct(role="plan", engine=engine, worktree=self.repo)
        record = self.execution_records()[0]
        config = json.loads(tuple(spawn.call_args.args[0])[-1])
        self.assertEqual(record["event_source"], "claude")
        self.assertEqual(record["sandbox"], "read-only")
        self.assertEqual(
            config["timeout"], VERBS_LAUNCH._review_launch.PROFILE_TIMEOUT_SECONDS["plan"]
        )

    def test_stripped_path_is_hermetic_with_explicit_provider(self) -> None:
        self.assertEqual(os.environ["PATH"], STRIPPED_PATH)
        self.assertIsNone(shutil.which("codex", path=STRIPPED_PATH))
        self.assertIsNone(shutil.which("claude", path=STRIPPED_PATH))
        outcome = self.seed_launch(engine=self.ready_engine())
        self.assertTrue(outcome.ok)

    def test_inflight_guard_and_its_disable_leg(self) -> None:
        engine = self.ready_engine()
        self.seed_launch(engine=engine)
        before = self.records()
        expected = (
            "forge: launch refused — execution execution-01 is still in flight in "
            f"{self.linked_worktree}; run launch collect or launch cancel"
        )

        def assertion() -> None:
            with self.assertRaises(ENGINE.Refusal) as caught:
                self.seed_launch(engine=engine)
            self.assertEqual(caught.exception.message, expected)

        assertion()
        self.assertEqual(self.records(), before)
        with mock.patch.object(VERBS_LAUNCH, "_require_no_inflight", return_value=None):
            with self.assertRaises(AssertionError):
                assertion()
        self.assertEqual(len(self.execution_records()), 2)

    def test_concurrent_launches_create_exactly_one_owner_record(self) -> None:
        engine = self.ready_engine()
        barrier = threading.Barrier(2)

        def invoke() -> object:
            barrier.wait(timeout=5)
            try:
                return self.launch_direct(engine=engine)
            except ENGINE.Refusal as exc:
                return exc

        with patch_engine("spawn_wrapper", return_value=SimpleNamespace(pid=424_242)):
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _index: invoke(), range(2)))
        self.assertEqual(len(self.execution_records()), 1)
        self.assertEqual(sum(isinstance(item, ENGINE.Refusal) for item in results), 1)
        refusal = next(item for item in results if isinstance(item, ENGINE.Refusal))
        self.assertIn("is still in flight", refusal.message)

    def test_pre_record_failure_removes_only_invocation_files(self) -> None:
        engine = self.ready_engine()
        agent = self.run_dir(self.repo, self.run_id) / "codex-implementer-01"
        agent.mkdir(mode=0o700)
        sentinel = agent / "keep.txt"
        sentinel.write_text("keep\n", encoding="utf-8")
        with (
            mock.patch.object(
                builders,
                "execution_start",
                side_effect=journal.CoordinationRefusal("synthetic builder refusal"),
            ),
            self.assertRaises(ENGINE.Refusal),
        ):
            self.seed_launch(engine=engine)
        self.assertEqual(list(agent.iterdir()), [sentinel])
        self.assertFalse(self.execution_records())

    def test_popen_failure_publishes_completion_and_clears_record(self) -> None:
        engine = self.ready_engine()
        (self.linked_worktree / "src/example.py").write_text(
            "VALUE = 2\n", encoding="utf-8"
        )
        (self.linked_worktree / "notes.txt").write_text("new\n", encoding="utf-8")
        error = OSError(errno.EACCES, "fixture denied")
        with (
            patch_engine("spawn_wrapper", side_effect=error),
            self.assertRaises(ENGINE.Refusal) as caught,
        ):
            self.launch_direct(role="plan", engine=engine)
        self.assertIs(caught.exception.reason_code, ENGINE.V2ReasonCode.EVIDENCE_INCOMPLETE)
        self.assertEqual(
            caught.exception.message,
            "forge: launch failed for execution-01: launch-failed: errno 13",
        )
        execution = self.execution_records()[0]
        results = [record for record in self.records() if record.get("type") == "execution_result"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "failed")
        self.assertIn("error launch-failed: errno 13", results[0]["summary"])
        self.assertEqual(results[0]["files_changed"], ["notes.txt", "src/example.py"])
        self.assertIn("plan execution changed files", results[0]["caveats"])
        completion = json.loads(
            (self.attempt_dir(execution) / "completion.json").read_text(encoding="utf-8")
        )
        self.assertEqual(completion["error"], "launch-failed: errno 13")
        marker = self.marker(execution)
        self.assertEqual(marker["collected_status"], "failed")
        self.assertIsNotNone(marker["collected_at"])
        self.assertFalse((self.attempt_dir(execution) / "pid").exists())

    def test_generic_spawn_failure_closes_descriptor_and_clears_record(self) -> None:
        engine = self.ready_engine()
        descriptors: list[int] = []

        def fail(*_args: object, **kwargs: object) -> object:
            descriptors.append(int(kwargs["attempt_fd"]))
            raise ValueError("synthetic spawn failure")

        with patch_engine("spawn_wrapper", side_effect=fail), self.assertRaises(ENGINE.Refusal):
            self.launch_direct(engine=engine)
        with self.assertRaises(OSError):
            os.fstat(descriptors[0])
        self.assertEqual(self.records()[-1]["status"], "failed")

    def test_popen_failure_race_winner_uses_normal_collect_mapping(self) -> None:
        engine = self.ready_engine()
        publish = VERBS_LAUNCH._review_lane_api.publish_or_read_terminal

        def lose_race(attempt_fd: int, binding: object, *_args: object) -> tuple[bool, object]:
            won, completion = publish(
                attempt_fd, binding, "launch-failed: spawn error", None
            )
            self.assertTrue(won)
            return False, completion

        with (
            patch_engine("publish_or_read_terminal", side_effect=lose_race),
            patch_engine("spawn_wrapper", side_effect=OSError(errno.EACCES, "denied")),
            mock.patch.object(
                engine, "launch_collect", return_value=SimpleNamespace(state="winner")
            ) as collect,
        ):
            outcome = self.launch_direct(engine=engine)
        self.assertEqual(outcome.state, "winner")
        collect.assert_called_once_with("execution-01")


if __name__ == "__main__":
    unittest.main()
