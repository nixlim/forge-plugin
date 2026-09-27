"""Public API and typed-launch compatibility contracts for the review lane."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import stat
import subprocess
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests._cli_loader import package_module
from tests._review_lane_support import ReviewLaneSupport

ATTEMPT = package_module("engine._review_attempt")
ENGINE = package_module("engine")
LANE_API = package_module("engine._review_lane_api")
LAUNCH = package_module("engine._review_launch")
WRAPPER = package_module("engine._review_wrapper")
WRAPPER_IO = package_module("engine._review_wrapper_io")
ROOT = Path(__file__).resolve().parents[1]
ATTEMPT_ID = "attempt-0123456789abcdef"


def flat_binding() -> dict[str, object]:
    return {
        "attempt": ATTEMPT_ID,
        "provider": "codex",
        "route_source": "committed-default",
        "route_sha256": "1" * 64,
        "sandbox": "read-only",
        "launcher_argv_digest": "2" * 64,
        "prompt_digest": "3" * 64,
        "environment_names": [],
        "omitted_short": [],
    }


class ReviewLanePublicApiTests(unittest.TestCase):
    def test_api_has_no_request_verb_or_app_launch_imports(self) -> None:
        source = Path(LANE_API.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported.update(
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        )
        forbidden = {
            "forge_cli.engine._verbs_review_request",
            "forge_cli.engine._verbs_review_collect",
            "forge_cli.engine._verbs_review_cancel",
            "forge_cli.app._engine_review_launch",
        }
        self.assertTrue(forbidden.isdisjoint(imported))

    def test_attempt_id_generator_is_shared_by_both_launch_owners(self) -> None:
        with mock.patch.object(LANE_API.secrets, "token_hex", return_value="a" * 16):
            self.assertEqual(LANE_API.new_attempt_id(), "attempt-" + "a" * 16)
        for relative, call in (
            (
                "scripts/forge/forge_cli/engine/_verbs_review_request.py",
                "_review_lane_api.new_attempt_id()",
            ),
            (
                "scripts/forge/forge_cli/app/_engine_review_launch.py",
                "engine.new_attempt_id()",
            ),
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn(call, source)

    def test_attempt_directory_opener_is_public_and_delegated(self) -> None:
        with self.subTest("real directory"):
            with self.assertRaises(FileNotFoundError):
                LANE_API.open_attempt_directory(Path("/missing/forge-attempt"))
        with mock.patch.object(
            LANE_API, "open_attempt_directory", return_value=71
        ) as opener:
            paths = SimpleNamespace(attempt_dir=Path("/fixture/attempt"))
            self.assertEqual(LAUNCH._open_attempt(paths), 71)
        opener.assert_called_once_with(paths.attempt_dir)

    def test_wrapper_launcher_binds_canonical_config_and_source(self) -> None:
        context = SimpleNamespace(command_digest=lambda argv: "digest:" + argv[3])
        config = {"z": 2, "a": [1]}
        with mock.patch.object(LANE_API, "wrapper_source", return_value="wrapper"):
            config_json, argv, digest = LANE_API.wrapper_launcher(context, 17, config)
        self.assertEqual(config_json, '{"a":[1],"z":2}')
        self.assertEqual(
            argv, (sys.executable, "-I", "-c", "wrapper", "17", config_json)
        )
        self.assertEqual(digest, "digest:wrapper")

    def test_spawn_wrapper_owns_the_detached_process_contract(self) -> None:
        process = SimpleNamespace()
        with (
            mock.patch.object(LANE_API.subprocess, "Popen", return_value=process) as popen,
            mock.patch.object(LANE_API, "reap_detached") as reap,
        ):
            returned = LANE_API.spawn_wrapper(
                ("python", "wrapper"),
                cwd=Path("/fixture/worktree"),
                environment={"PATH": "/trusted"},
                attempt_fd=23,
            )
        self.assertIs(returned, process)
        self.assertEqual(popen.call_args.args[0], ["python", "wrapper"])
        self.assertEqual(popen.call_args.kwargs["cwd"], "/fixture/worktree")
        self.assertEqual(popen.call_args.kwargs["env"], {"PATH": "/trusted"})
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        self.assertTrue(popen.call_args.kwargs["close_fds"])
        self.assertEqual(popen.call_args.kwargs["pass_fds"], (23,))
        reap.assert_called_once_with(process)

    def test_flat_binding_drives_terminal_completion_and_abandonment(self) -> None:
        binding = flat_binding()
        record = ATTEMPT.make_terminal_completion(binding, "wrapper-lost")
        self.assertEqual(record["route_source"], "committed-default")
        self.assertEqual(record["route_sha256"], "1" * 64)
        with self.subTest("abandonment"):
            import tempfile

            with tempfile.TemporaryDirectory() as temporary:
                directory = os.open(temporary, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    won, abandoned = ATTEMPT.claim_abandoned(directory, binding)
                finally:
                    os.close(directory)
            self.assertTrue(won)
            self.assertEqual(abandoned["error"], "abandoned")

        def nested_only(request: object, field: str) -> object:
            assert isinstance(request, dict)
            route = request.get("route")
            if field in {"provider", "route_source", "route_sha256"}:
                return route.get(field) if isinstance(route, dict) else None
            return request.get(field)

        with (
            mock.patch.object(ATTEMPT, "_request_value", side_effect=nested_only),
            self.assertRaises(ATTEMPT.AttemptRecordError),
        ):
            ATTEMPT.make_terminal_completion(binding, "wrapper-lost")

    def test_publish_or_read_terminal_returns_the_race_winner(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            directory = os.open(temporary, os.O_RDONLY | os.O_DIRECTORY)
            try:
                won, published = LANE_API.publish_or_read_terminal(
                    directory, flat_binding(), "launch-failed: spawn error"
                )
                raced, existing = LANE_API.publish_or_read_terminal(
                    directory, flat_binding(), "launch-failed: spawn error"
                )
            finally:
                os.close(directory)
        self.assertTrue(won)
        self.assertFalse(raced)
        self.assertEqual(existing, published)

    def test_probe_refusal_accepts_a_typed_launch_verb(self) -> None:
        with (
            mock.patch.object(LAUNCH.subprocess, "Popen", side_effect=OSError(2, "missing")),
            self.assertRaises(ENGINE.Refusal) as caught,
        ):
            LAUNCH.probe_provider_version(
                "codex", "/missing/codex", {}, Path("/tmp"), verb="launch start"
            )
        self.assertEqual(
            caught.exception.message,
            "forge: launch start refused — codex executable is unavailable: /missing/codex",
        )
        self.assertEqual(
            caught.exception.remediation,
            "repair the reviewer route and retry forge launch start",
        )

    def assert_completion_vocabulary_exposed(self) -> None:
        self.assertIs(
            LANE_API.__dict__.get("COMPLETION_KEYS"), ATTEMPT.COMPLETION_KEYS
        )
        self.assertIs(
            LANE_API.__dict__.get("COMPLETION_ERRORS"), ATTEMPT.COMPLETION_ERRORS
        )
        self.assertIs(
            LANE_API.__dict__.get("COMPLETION_SCHEMA"), WRAPPER_IO.COMPLETION_SCHEMA
        )

    def test_completion_vocabulary_is_exposed_by_lane_api(self) -> None:
        self.assert_completion_vocabulary_exposed()
        self.assertEqual(
            LANE_API.COMPLETION_KEYS,
            {
                "argv_digest",
                "attempt",
                "completed_at",
                "environment_names",
                "error",
                "events_bytes",
                "observed_model",
                "omitted_short",
                "pgid",
                "prompt_digest",
                "provider",
                "returncode",
                "reviewer_pid",
                "route_sha256",
                "route_source",
                "sandbox",
                "schema",
                "started_at",
                "timed_out",
                "verdict_digest",
                "verdict_size",
                "wrapper_pid",
            },
        )

    def test_completion_vocabulary_exposure_is_load_bearing(self) -> None:
        for name in ("COMPLETION_KEYS", "COMPLETION_ERRORS", "COMPLETION_SCHEMA"):
            with self.subTest(name=name), mock.patch.dict(LANE_API.__dict__):
                del LANE_API.__dict__[name]
                with self.assertRaises(AssertionError):
                    self.assert_completion_vocabulary_exposed()

    def assert_refresh_recheck_fields_exposed(self) -> None:
        self.assertEqual(
            LANE_API.__dict__.get("REFRESH_RECHECK_FIELDS"),
            frozenset({"reviewer_pid", "reviewer_birth", "started_at"}),
        )

    def test_refresh_recheck_fields_are_exposed_by_lane_api(self) -> None:
        self.assert_refresh_recheck_fields_exposed()

    def test_refresh_recheck_fields_exposure_is_load_bearing(self) -> None:
        with mock.patch.dict(LANE_API.__dict__):
            del LANE_API.__dict__["REFRESH_RECHECK_FIELDS"]
            with self.assertRaises(AssertionError):
                self.assert_refresh_recheck_fields_exposed()

    def test_shared_sets_and_completion_schema_have_one_owner(self) -> None:
        self.assertEqual(
            LANE_API.NO_SIGNAL_OUTCOMES,
            {"identity-unproven", "wrapper-identity-unproven", "recorded-identity-unproven"},
        )
        self.assertIn("wrapper-dead / child-alive", LANE_API.CANCEL_REQUIRED_OUTCOMES)
        engine_sources = (ROOT / "scripts/forge/forge_cli/engine").glob("*.py")
        count = sum(
            path.read_text(encoding="utf-8").count(
                'COMPLETION_SCHEMA = "forge-review-process/2"'
            )
            for path in engine_sources
        )
        self.assertEqual(count, 1)


class WrapperOptionTests(ReviewLaneSupport, unittest.TestCase):
    def _directory(self) -> int:
        descriptor = os.open(self.attempt_dir, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, descriptor)
        return descriptor

    def _touch(self, name: str, data: bytes = b"", mode: int = 0o600) -> Path:
        path = self.attempt_dir / name
        path.write_bytes(data)
        path.chmod(mode)
        return path

    def _assert_open_rejected(self, name: str, opener: object) -> None:
        with self.assertRaises(OSError):
            WRAPPER_IO._open_events(self._directory(), name, True, opener)

    @staticmethod
    def _unsafe_opener(directory: int, name: str, flags: int) -> int:
        return os.open(name, flags, dir_fd=directory)

    def test_existing_empty_owner_only_events_file_is_accepted(self) -> None:
        self._touch("typed-events.jsonl")
        observed: list[int] = []

        def opener(directory: int, name: str, flags: int) -> int:
            observed.append(flags)
            return WRAPPER.open_owner_regular(directory, name, flags)

        descriptor = WRAPPER_IO._open_events(
            self._directory(), "typed-events.jsonl", True, opener
        )
        try:
            os.write(descriptor, b"event\n")
        finally:
            os.close(descriptor)
        self.assertEqual(observed, [os.O_WRONLY | os.O_APPEND])
        self.assertEqual((self.attempt_dir / "typed-events.jsonl").read_bytes(), b"event\n")

    def test_nonempty_events_control_is_load_bearing(self) -> None:
        self._touch("events.jsonl", b"occupied")

        def assert_rejected() -> None:
            self._assert_open_rejected("events.jsonl", WRAPPER.open_owner_regular)

        assert_rejected()
        with (
            mock.patch.object(WRAPPER_IO, "_events_file_empty", return_value=True),
            self.assertRaises(AssertionError),
        ):
            assert_rejected()

    def test_symlink_events_control_is_load_bearing(self) -> None:
        self._touch("target.jsonl")
        (self.attempt_dir / "events.jsonl").symlink_to("target.jsonl")

        def assert_rejected(opener: object) -> None:
            self._assert_open_rejected("events.jsonl", opener)

        assert_rejected(WRAPPER.open_owner_regular)
        with self.assertRaises(AssertionError):
            assert_rejected(self._unsafe_opener)

    def test_mode_events_control_is_load_bearing(self) -> None:
        self._touch("events.jsonl", mode=0o644)

        def assert_rejected(opener: object) -> None:
            self._assert_open_rejected("events.jsonl", opener)

        assert_rejected(WRAPPER.open_owner_regular)
        with self.assertRaises(AssertionError):
            assert_rejected(self._unsafe_opener)

    def test_owner_events_control_is_load_bearing(self) -> None:
        self._touch("events.jsonl")
        foreign = SimpleNamespace(
            st_mode=stat.S_IFREG | 0o600,
            st_uid=os.geteuid() + 1,
            st_size=0,
        )

        def assert_rejected() -> None:
            with mock.patch.object(WRAPPER.os, "fstat", return_value=foreign):
                self._assert_open_rejected("events.jsonl", WRAPPER.open_owner_regular)

        assert_rejected()
        with (
            mock.patch.object(WRAPPER.os, "fstat", return_value=foreign),
            mock.patch.object(WRAPPER.os, "geteuid", return_value=foreign.st_uid),
            self.assertRaises(AssertionError),
        ):
            self._assert_open_rejected("events.jsonl", WRAPPER.open_owner_regular)

    def test_leaf_name_control_is_load_bearing(self) -> None:
        leaves = dict(WRAPPER_IO._DEFAULT_LEAVES, events="../events")

        def assert_rejected() -> None:
            with self.assertRaises(ValueError):
                WRAPPER_IO._wrapper_options({"leaves": leaves})

        assert_rejected()
        with (
            mock.patch.object(WRAPPER_IO, "_valid_attempt_leaf", return_value=True),
            self.assertRaises(AssertionError),
        ):
            assert_rejected()

    def test_duplicate_leaf_control_is_load_bearing(self) -> None:
        leaves = dict(WRAPPER_IO._DEFAULT_LEAVES, events="prompt.txt")

        def assert_rejected() -> None:
            with self.assertRaises(ValueError):
                WRAPPER_IO._wrapper_options({"leaves": leaves})

        assert_rejected()
        with (
            mock.patch.object(WRAPPER_IO, "_distinct_attempt_leaves", return_value=True),
            self.assertRaises(AssertionError),
        ):
            assert_rejected()

    def test_reserved_leaf_control_is_load_bearing(self) -> None:
        leaves = dict(WRAPPER_IO._DEFAULT_LEAVES, capture="identity.json")

        def assert_rejected() -> None:
            with self.assertRaises(ValueError):
                WRAPPER_IO._wrapper_options({"leaves": leaves})

        assert_rejected()
        with (
            mock.patch.object(
                WRAPPER_IO, "_leaves_avoid_control_artifacts", return_value=True
            ),
            self.assertRaises(AssertionError),
        ):
            assert_rejected()

    def test_known_keys_and_boolean_controls_are_load_bearing(self) -> None:
        extra = dict(WRAPPER_IO._DEFAULT_LEAVES, unknown="extra")

        def assert_unknown() -> None:
            with self.assertRaises(ValueError):
                WRAPPER_IO._wrapper_options({"leaves": extra})

        assert_unknown()
        with (
            mock.patch.object(WRAPPER_IO, "_known_leaf_keys", return_value=True),
            self.assertRaises(AssertionError),
        ):
            assert_unknown()

        def assert_non_boolean() -> None:
            with self.assertRaises(ValueError):
                WRAPPER_IO._wrapper_options({"events_existing": 1})

        assert_non_boolean()
        with (
            mock.patch.object(WRAPPER_IO, "_events_existing", return_value=True),
            self.assertRaises(AssertionError),
        ):
            assert_non_boolean()


@unittest.skipUnless(sys.platform.startswith("linux"), "wrapper integration needs /proc")
class WrapperExistingEventsIntegrationTests(ReviewLaneSupport, unittest.TestCase):
    def test_custom_leaves_accept_precreated_events_without_changing_defaults(self) -> None:
        provider = self.install_provider("codex")
        prompt = b"candidate: " + b"1" * 64 + b"\npackage: " + b"2" * 64 + b"\n"
        leaves = {
            "prompt": "typed.prompt",
            "events": "typed.events",
            "stderr": "typed.stderr",
            "capture": "typed.verdict",
            "staging": "typed.staging",
        }
        self._write_owner_file(leaves["prompt"], prompt)
        self._write_owner_file(leaves["events"], b"")
        staging = self.attempt_dir / leaves["staging"]
        argv = [str(provider), "exec", "--json", "--output-last-message", str(staging), "-"]
        config = {
            "attempt": ATTEMPT_ID,
            "provider": "codex",
            "route_source": "committed-default",
            "route_sha256": "a" * 64,
            "sandbox": "read-only",
            "argv": argv,
            "argv_digest": WRAPPER._canonical_digest(argv),
            "prompt_digest": hashlib.sha256(prompt).hexdigest(),
            "timeout": 5,
            "grace": 1,
            "environment_names": [],
            "omitted_short": [],
            "leaves": leaves,
            "events_existing": True,
        }
        process = self._start(config)
        completion = self._completion(process)
        self.assertEqual(process.returncode, 0)
        self.assertIsNone(completion["error"])
        self.assertGreater((self.attempt_dir / leaves["events"]).stat().st_size, 0)
        self.assertTrue((self.attempt_dir / leaves["capture"]).is_file())
        for default in ("prompt.txt", "events.jsonl", "stderr.log", "verdict.txt"):
            self.assertFalse((self.attempt_dir / default).exists())

    def test_real_wrapper_rejects_capture_collision_without_corrupting_identity(self) -> None:
        leaves = dict(WRAPPER_IO._DEFAULT_LEAVES, capture="identity.json")
        config = {
            "attempt": ATTEMPT_ID,
            "provider": "codex",
            "route_source": "committed-default",
            "route_sha256": "a" * 64,
            "sandbox": "read-only",
            "argv": [],
            "argv_digest": WRAPPER._canonical_digest([]),
            "prompt_digest": "b" * 64,
            "timeout": 5,
            "grace": 1,
            "environment_names": [],
            "omitted_short": [],
            "leaves": leaves,
        }
        process = self._start(config)
        completion = self._completion(process)
        self.assertEqual(process.returncode, 1)
        self.assertEqual(completion["error"], "wrapper failure")
        identity = json.loads((self.attempt_dir / "identity.json").read_text())
        self.assertEqual(identity["schema"], "forge-review-identity/1")

    def _start(self, config: dict[str, object]) -> subprocess.Popen[bytes]:
        directory = os.open(self.attempt_dir, os.O_RDONLY | os.O_DIRECTORY)
        try:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    WRAPPER.wrapper_source(),
                    str(directory),
                    json.dumps(config, sort_keys=True, separators=(",", ":")),
                ],
                env={},
                pass_fds=(directory,),
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        finally:
            os.close(directory)
        self.addCleanup(self._stop, process)
        return process

    def _completion(self, process: subprocess.Popen[bytes]) -> dict[str, object]:
        completion_path = self.attempt_dir / "completion.json"
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not completion_path.exists():
            time.sleep(0.02)
        self.assertTrue(completion_path.exists())
        process.wait(timeout=10)
        return json.loads(completion_path.read_text(encoding="utf-8"))

    def _write_owner_file(self, name: str, data: bytes) -> None:
        path = self.attempt_dir / name
        path.write_bytes(data)
        path.chmod(0o600)

    @staticmethod
    def _stop(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=2)


if __name__ == "__main__":
    unittest.main()
