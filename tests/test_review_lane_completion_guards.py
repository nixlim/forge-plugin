"""Focused regression tests for review cancellation and completion guards."""

from __future__ import annotations

import inspect
import json
import os
import tempfile
import textwrap
import unittest
from pathlib import Path
from types import FunctionType, SimpleNamespace
from unittest import mock

from tests._cli_loader import package_module, patch_engine
from tests.test_review_launch_streams import WrapperHarness

APP_REQUEST = package_module("app._engine_review_request")
ATTEMPT = package_module("engine._review_attempt")
CANCEL = package_module("engine._verbs_review_cancel")
ENGINE = package_module("engine")
LANE_API = package_module("engine._review_lane_api")
WRAPPER = package_module("engine._review_wrapper")

CURRENT_ATTEMPT = "attempt-0123456789abcdef"
FOREIGN_ATTEMPT = "attempt-fedcba9876543210"
KILL_UNCONFIRMED = "forge: review cancel refused — kill-unconfirmed: [88]"


def request(attempt: str = CURRENT_ATTEMPT) -> dict[str, object]:
    return {
        "attempt": attempt,
        "provider": "codex",
        "sandbox": "read-only",
        "route": {
            "provider": "codex",
            "route_source": "committed-default",
            "route_sha256": "1" * 64,
        },
        "argv_digest": "2" * 64,
        "prompt_digest": "3" * 64,
        "environment_names": [],
        "omitted_short": [],
    }


def mutated_function(
    function: FunctionType, anchor: str, replacement: str
) -> FunctionType:
    """Compile one exact source mutation with the production function's globals."""

    source = textwrap.dedent(inspect.getsource(function))
    if source.count(anchor) != 1:
        raise AssertionError(f"mutation anchor drifted for {function.__name__}")
    namespace = dict(function.__globals__)
    exec(compile(source.replace(anchor, replacement, 1), function.__code__.co_filename, "exec"),
         namespace)
    mutated = namespace[function.__name__]
    if not isinstance(mutated, FunctionType):
        raise AssertionError(f"mutation did not define {function.__name__}")
    return mutated


def rebound_function(function: FunctionType, **bindings: object) -> FunctionType:
    """Clone ``function`` while replacing selected global bindings."""

    namespace = dict(function.__globals__)
    namespace.update(bindings)
    rebound = FunctionType(
        function.__code__, namespace, function.__name__, function.__defaults__,
        function.__closure__,
    )
    rebound.__kwdefaults__ = function.__kwdefaults__
    return rebound


def mutated_wrapper_source(anchor: str, replacement: str) -> str:
    source = WRAPPER.wrapper_source()
    if source.count(anchor) != 1:
        raise AssertionError("wrapper mutation anchor drifted")
    return source.replace(anchor, replacement, 1)


class KillUnconfirmedLiteralTests(unittest.TestCase):
    def legacy_formatter(self) -> FunctionType:
        return mutated_function(
            LANE_API.cancel_kill_unconfirmed_message,
            'return f"forge: review cancel refused — kill-unconfirmed: {list(members)}"',
            'return f"review cancel kill-unconfirmed; remaining PIDs {list(members)}"',
        )

    def assert_commit_literal(self) -> None:
        state = {"chain_id": "c-2026-09-27T010203Z-abcd"}
        alive = ATTEMPT.GroupProof("reviewer-alive", 77, (88,))
        remaining = ATTEMPT.GroupProof("kill-unconfirmed", 77, (88,))
        with (
            mock.patch.object(ATTEMPT, "prove_group_ownership", return_value=alive),
            mock.patch.object(ATTEMPT, "terminate_owned_group", return_value=remaining),
            self.assertRaises(ENGINE.Refusal) as caught,
        ):
            CANCEL._cancel_group(state, {"pgid": 77})
        self.assertEqual(caught.exception.message, KILL_UNCONFIRMED)

    def test_commit_cancel_pins_exact_kill_unconfirmed_refusal(self) -> None:
        self.assert_commit_literal()
        with (
            mock.patch.object(
                LANE_API, "cancel_kill_unconfirmed_message", self.legacy_formatter()
            ),
            self.assertRaises(AssertionError),
        ):
            self.assert_commit_literal()

    def assert_merge_literal(self) -> None:
        state = {"chain_id": "m-2026-09-27T010203Z-abcd"}
        alive = ATTEMPT.GroupProof("reviewer-alive", 77, (88,))
        remaining = ATTEMPT.GroupProof("kill-unconfirmed", 77, (88,))
        owner = SimpleNamespace(_refuse_wrapper_identity_unproven=lambda *_args: None)
        with (
            patch_engine("terminate_owned_group", return_value=remaining),
            self.assertRaises(ENGINE.Refusal) as caught,
        ):
            APP_REQUEST._cancel_group_outcome(owner, state, {"pgid": 77}, alive)
        self.assertEqual(caught.exception.message, KILL_UNCONFIRMED)

    def test_merge_cancel_pins_exact_kill_unconfirmed_refusal(self) -> None:
        self.assert_merge_literal()
        with (
            mock.patch.object(
                LANE_API, "cancel_kill_unconfirmed_message", self.legacy_formatter()
            ),
            self.assertRaises(AssertionError),
        ):
            self.assert_merge_literal()


class CancelImmutableIdentityTests(unittest.TestCase):
    def assert_recheck(self, publisher: FunctionType = CANCEL._publish_completion) -> None:
        identity = {
            "schema": WRAPPER.IDENTITY_SCHEMA,
            "attempt": CURRENT_ATTEMPT,
            "wrapper_pid": 77,
            "pgid": 77,
            "wrapper_birth": {
                "kind": "linux-proc", "boot_id": "boot", "starttime": 1,
            },
            "reviewer_pid": None,
            "reviewer_birth": None,
            "started_at": "2026-09-27T12:00:00Z",
        }
        stored = dict(identity)
        state = {"chain_id": "c-2026-09-27T010203Z-abcd"}

        def rewrite_after_proof(_identity: object) -> ATTEMPT.GroupProof:
            stored["wrapper_birth"] = {
                "kind": "linux-proc", "boot_id": "boot", "starttime": 2,
            }
            return ATTEMPT.GroupProof("group-empty", 77)

        publish = mock.Mock(return_value=True)
        with (
            patch_engine("read_identity", side_effect=lambda *_args: dict(stored)),
            patch_engine("read_completion", return_value=None),
            patch_engine("prove_group_ownership", side_effect=rewrite_after_proof),
            patch_engine("publish_terminal_completion", publish),
            self.assertRaises(ENGINE.Refusal) as caught,
        ):
            opened = CANCEL._read_open_attempt(state, request(), 9)
            outcome, _proof = CANCEL._cancel_group(state, opened)
            publisher(SimpleNamespace(), state, request(), opened, 9, outcome)
        self.assertEqual(
            caught.exception.message,
            "review attempt record is invalid: identity.json changed group identity "
            "before completion publication",
        )
        publish.assert_not_called()

    def test_cancel_rechecks_immutable_identity_before_publication(self) -> None:
        self.assert_recheck()
        anchor = (
            "        if any(\n"
            "            current.get(field) != identity.get(field)\n"
            "            for field in _review_lane_api.IMMUTABLE_IDENTITY_FIELDS\n"
            "        ):\n"
        )
        disabled = mutated_function(
            CANCEL._publish_completion,
            anchor,
            anchor.replace("if any(", "if False and any("),
        )
        with self.assertRaises(AssertionError):
            self.assert_recheck(disabled)


class VerdictCapTests(WrapperHarness):
    RAW_CAP = (
        "    if limit is not None and len(data) > limit:\n"
        '        raise ValueError("verdict cap")'
    )
    CODEX_REDACTED_CAP = (
        "        if len(verdict) > VERDICT_LIMIT_BYTES:\n"
        '            raise ValueError("verdict cap")'
    )
    CLAUDE_CAP = (
        "    if len(verdict) > VERDICT_LIMIT_BYTES:\n"
        '        return b"", "verdict cap", observed'
    )

    def assert_cap(
        self,
        name: str,
        provider: str,
        provider_source: str,
        *,
        wrapper_source: str | None = None,
        environment: dict[str, str] | None = None,
    ) -> None:
        staging = self.root / name / "verdict.staging"
        arguments = (str(staging),) if provider == "codex" else ()
        patcher = (
            mock.patch.object(WRAPPER, "wrapper_source", return_value=wrapper_source)
            if wrapper_source is not None
            else mock.patch.object(WRAPPER, "wrapper_source", wraps=WRAPPER.wrapper_source)
        )
        with patcher:
            process, attempt = self.launch(
                name,
                provider_source,
                settings=(provider, 5.0),
                arguments=arguments,
                environment=environment,
            )
        completion = self.completion(process, attempt)
        self.assertEqual(completion["error"], "verdict cap")
        self.assertEqual(completion["verdict_size"], 0)

    def test_claude_oversized_result_is_capped(self) -> None:
        provider = """
import json, sys
sys.stdin.read()
print(json.dumps({'type': 'result', 'is_error': False,
                  'result': 'v' * 65537}), flush=True)
"""
        self.assert_cap("claude-cap", "claude", provider)
        mutant = mutated_wrapper_source(
            self.CLAUDE_CAP,
            "    if False:\n"
            '        return b"", "verdict cap", observed',
        )
        with self.assertRaises(AssertionError):
            self.assert_cap(
                "claude-cap-disabled", "claude", provider, wrapper_source=mutant
            )

    def test_codex_raw_staging_is_capped_before_redaction(self) -> None:
        provider = """
import json, os, pathlib, sys
sys.stdin.read()
pathlib.Path(sys.argv[1]).write_bytes(os.environ['CANARY'].encode() * 66)
print(json.dumps({'type': 'turn.completed'}), flush=True)
"""
        environment = {"CANARY": "x" * 1000}
        self.assert_cap("codex-raw-cap", "codex", provider, environment=environment)
        mutant = mutated_wrapper_source(
            self.RAW_CAP,
            "    if False:\n"
            '        raise ValueError("verdict cap")',
        )
        with self.assertRaises(AssertionError):
            self.assert_cap(
                "codex-raw-cap-disabled",
                "codex",
                provider,
                wrapper_source=mutant,
                environment=environment,
            )

    def test_codex_post_redaction_verdict_is_capped(self) -> None:
        provider = """
import json, os, pathlib, sys
sys.stdin.read()
pathlib.Path(sys.argv[1]).write_bytes(os.environ['CANARY'].encode() * 4000)
print(json.dumps({'type': 'turn.completed'}), flush=True)
"""
        environment = {"CANARY": "four"}
        self.assert_cap(
            "codex-redacted-cap", "codex", provider, environment=environment
        )
        mutant = mutated_wrapper_source(
            self.CODEX_REDACTED_CAP,
            "        if False:\n"
            '            raise ValueError("verdict cap")',
        )
        with self.assertRaises(AssertionError):
            self.assert_cap(
                "codex-redacted-cap-disabled",
                "codex",
                provider,
                wrapper_source=mutant,
                environment=environment,
            )


class AttemptFieldBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="forge-review-binding-")
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name)
        self.descriptor = os.open(
            self.path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        )
        self.addCleanup(os.close, self.descriptor)
        completion = ATTEMPT.make_terminal_completion(
            request(FOREIGN_ATTEMPT),
            "launch-failed: spawn error",
            completed_at="2026-09-27T12:00:00Z",
        )
        path = self.path / "completion.json"
        path.write_text(
            json.dumps(completion, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        path.chmod(0o600)

    def test_read_completion_rejects_foreign_attempt_in_current_directory(self) -> None:
        def assert_refused() -> None:
            with self.assertRaisesRegex(
                ATTEMPT.AttemptRecordError, "attempt binding differs"
            ):
                ATTEMPT.read_completion(self.descriptor, CURRENT_ATTEMPT)

        assert_refused()
        mutant = mutated_function(
            ATTEMPT._validate_completion,
            "    _require(expected_attempt is None or attempt == expected_attempt, "
            '"attempt binding differs")\n',
            "",
        )
        with (
            mock.patch.object(ATTEMPT, "_validate_completion", mutant),
            self.assertRaises(AssertionError),
        ):
            assert_refused()

    def test_claude_init_mismatch_is_a_load_bearing_completion_term(self) -> None:
        completion = ATTEMPT.make_terminal_completion(
            request(),
            "claude init mismatch",
            completed_at="2026-09-27T12:00:00Z",
        )

        def assert_admitted() -> None:
            ATTEMPT._validate_completion_values(completion)

        assert_admitted()
        without_term = ATTEMPT._COMPLETION_ERRORS - {"claude init mismatch"}
        with (
            mock.patch.object(ATTEMPT, "_COMPLETION_ERRORS", without_term),
            self.assertRaisesRegex(ATTEMPT.AttemptRecordError, "invalid error"),
        ):
            assert_admitted()

    def test_binding_rejects_foreign_attempt_even_after_unbound_read(self) -> None:
        completion = ATTEMPT.read_completion(self.descriptor)
        self.assertIsNotNone(completion)
        assert completion is not None

        def assert_refused() -> None:
            with self.assertRaisesRegex(
                ATTEMPT.AttemptRecordError,
                "completion.json attempt differs from the request",
            ):
                ATTEMPT.validate_completion_binding(completion, request(), None)

        assert_refused()
        mutant = mutated_function(
            ATTEMPT.validate_completion_binding,
            '    for field in ("provider", "route_source", "route_sha256", '
            '"sandbox", "attempt"):\n',
            '    for field in ("provider", "route_source", "route_sha256", '
            '"sandbox"):\n',
        )
        with (
            mock.patch.object(ATTEMPT, "validate_completion_binding", mutant),
            self.assertRaises(AssertionError),
        ):
            assert_refused()

    def test_read_completion_rejects_unexplained_null_returncode(self) -> None:
        completion = ATTEMPT.make_terminal_completion(
            request(), "launch-failed: spawn error", completed_at="2026-09-27T12:00:00Z"
        )
        completion["error"] = None
        path = self.path / "completion.json"
        path.write_text(json.dumps(completion, sort_keys=True), encoding="utf-8")
        path.chmod(0o600)

        def assert_refused() -> None:
            with self.assertRaisesRegex(ATTEMPT.AttemptRecordError, "^null returncode$"):
                ATTEMPT.read_completion(self.descriptor, CURRENT_ATTEMPT)

        assert_refused()
        anchor = (
            '    _require(returncode is not None or value.get("timed_out") '
            'or error is not None,\n             "null returncode")\n'
        )
        mutant_values = mutated_function(
            ATTEMPT._validate_completion_values, anchor, ""
        )
        mutant_validate = rebound_function(
            ATTEMPT._validate_completion,
            _validate_completion_values=mutant_values,
        )
        mutant_read = rebound_function(
            ATTEMPT.read_completion, _validate_completion=mutant_validate
        )
        with (
            patch_engine("read_completion", mutant_read),
            self.assertRaises(AssertionError),
        ):
            assert_refused()

    def test_read_identity_rejects_nonleader_process_group(self) -> None:
        identity = {
            "schema": WRAPPER.IDENTITY_SCHEMA,
            "attempt": CURRENT_ATTEMPT,
            "wrapper_pid": 77,
            "pgid": 78,
            "wrapper_birth": {
                "kind": "linux-proc", "boot_id": "boot", "starttime": 1,
            },
            "reviewer_pid": None,
            "reviewer_birth": None,
            "started_at": "2026-09-27T12:00:00Z",
        }
        path = self.path / "identity.json"
        path.write_text(json.dumps(identity, sort_keys=True), encoding="utf-8")
        path.chmod(0o600)

        def assert_refused() -> None:
            with self.assertRaisesRegex(
                ATTEMPT.AttemptRecordError,
                "^identity.json does not identify its group leader$",
            ):
                ATTEMPT.read_identity(self.descriptor, CURRENT_ATTEMPT)

        assert_refused()
        anchor = (
            "        wrapper_pid == pgid and "
            "(wrapper_birth is None or _valid_birth(wrapper_birth)),\n"
        )
        mutant_live = mutated_function(
            ATTEMPT._validate_live_identity,
            anchor,
            "        wrapper_birth is None or _valid_birth(wrapper_birth),\n",
        )
        mutant_validate = rebound_function(
            ATTEMPT._validate_identity, _validate_live_identity=mutant_live
        )
        mutant_read = rebound_function(
            ATTEMPT.read_identity, _validate_identity=mutant_validate
        )
        with (
            patch_engine("read_identity", mutant_read),
            self.assertRaises(AssertionError),
        ):
            assert_refused()


if __name__ == "__main__":
    unittest.main()
