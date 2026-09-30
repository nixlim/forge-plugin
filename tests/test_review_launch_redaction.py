"""Boundary-safe and shape-aware credential redaction tests."""

from __future__ import annotations

import inspect
import json
import os
import textwrap
import unittest
from types import FunctionType
from unittest import mock

from tests._cli_loader import package_module
from tests.test_review_launch_streams import WrapperHarness, WrapperLaunchOptions

LAUNCH = package_module("engine._review_launch")
WRAPPER = package_module("engine._review_wrapper")
COLLECT = package_module("engine._verbs_review_collect")


def mutated_function(
    function: FunctionType, anchor: str, replacement: str
) -> FunctionType:
    """Compile one exact in-memory mutation with the function's globals."""

    source = textwrap.dedent(inspect.getsource(function))
    if source.count(anchor) != 1:
        raise AssertionError(f"mutation anchor drifted for {function.__name__}")
    namespace = dict(function.__globals__)
    exec(
        compile(
            source.replace(anchor, replacement, 1),
            function.__code__.co_filename,
            "exec",
        ),
        namespace,
    )
    mutant = namespace[function.__name__]
    if not isinstance(mutant, FunctionType):
        raise AssertionError(f"mutation did not define {function.__name__}")
    return mutant


class ReviewLaunchRedactionTests(WrapperHarness):
    def patterns(self, values: dict[str, str]) -> list[tuple[bytes, bytes]]:
        with mock.patch.dict(os.environ, values, clear=True):
            return WRAPPER._redaction_patterns(sorted(values))

    def test_credential_raw_and_json_forms_are_redacted_at_every_split(self) -> None:
        values = {
            "HOME": "/home/agents",
            "ANTHROPIC_API_KEY": 'quote"line\nslash\\snow-雪',
            "USER": "agents",
        }

        def assert_credential_redaction() -> None:
            patterns = self.patterns(values)
            self.assertNotIn(b"agents", {pattern for pattern, _marker in patterns})
            for name in ("HOME", "ANTHROPIC_API_KEY"):
                replacement = f"<redacted:{name}>".encode()
                actual_patterns = {
                    pattern for pattern, marker in patterns if marker == replacement
                }
                value = values[name]
                expected_patterns = {
                    value.encode(),
                    json.dumps(value, ensure_ascii=True)[1:-1].encode(),
                    json.dumps(value, ensure_ascii=False)[1:-1].encode(),
                }
                self.assertTrue(expected_patterns <= actual_patterns)
                for pattern in expected_patterns:
                    for offset in range(len(pattern) + 1):
                        with self.subTest(name=name, pattern=pattern, offset=offset):
                            redactor = WRAPPER._StreamRedactor(patterns)
                            output = redactor.feed(b"left:" + pattern[:offset])
                            output += redactor.feed(
                                pattern[offset:] + b":right", final=True
                            )
                            self.assertEqual(
                                output, b"left:" + replacement + b":right"
                            )
            self.assertEqual(
                WRAPPER._StreamRedactor(patterns).carry_limit,
                max(len(pattern) for pattern, _marker in patterns) - 1,
            )

        assert_credential_redaction()
        exempt = WRAPPER.REDACTION_EXEMPT_NAMES | {"ANTHROPIC_API_KEY"}
        with (
            mock.patch.object(WRAPPER, "REDACTION_EXEMPT_NAMES", exempt),
            self.assertRaises(AssertionError),
        ):
            assert_credential_redaction()

    def test_exempt_value_equal_to_credential_value_is_still_redacted(self) -> None:
        patterns = self.patterns(
            {"USER": "shared-secret", "ANTHROPIC_API_KEY": "shared-secret"}
        )
        output = WRAPPER._StreamRedactor(patterns).feed(b"shared-secret", final=True)
        self.assertEqual(output, b"<redacted:ANTHROPIC_API_KEY>")

    def test_exact_four_noncredential_values_survive_and_are_load_bearing(self) -> None:
        values = {
            "USER": "fixture-user",
            "LANG": "en_US.UTF-8",
            "LC_ALL": "en_GB.UTF-8",
            "TERM": "xterm-fixture",
        }
        payload = "|".join(values.values()).encode()
        expected = frozenset(values)
        self.assertEqual(WRAPPER.REDACTION_EXEMPT_NAMES, expected)

        def assert_survives() -> None:
            patterns = self.patterns(values)
            output = WRAPPER._StreamRedactor(patterns).feed(payload, final=True)
            self.assertEqual(output, payload)

        assert_survives()
        for name in values:
            with self.subTest(name=name):
                with (
                    mock.patch.object(
                        WRAPPER,
                        "REDACTION_EXEMPT_NAMES",
                        expected - {name},
                    ),
                    self.assertRaises(AssertionError),
                ):
                    assert_survives()

    def test_longest_first_prevents_prefix_leakage(self) -> None:
        values = {"LONG": "shared-prefix-secret", "SHORT": "shared-prefix"}
        patterns = self.patterns(values)
        raw = b"shared-prefix-secret shared-prefix"
        output = WRAPPER._StreamRedactor(patterns).feed(raw, final=True)
        self.assertEqual(output, b"<redacted:LONG> <redacted:SHORT>")
        self.assertNotIn(b"shared-prefix", output)

    def test_user_value_preserves_agents_path_but_extractor_key_fails_closed(self) -> None:
        event = {
            "type": "system",
            "subtype": "init",
            "model": "fixture-model",
            "agents": ["fixture"],
            "path": "agents/review-final.md",
        }
        serialized = json.dumps(event).encode()

        def assert_survives() -> None:
            patterns = self.patterns({"USER": "agents"})
            persisted, error = WRAPPER._EventCapture(patterns).line_bytes(
                serialized, terminated=True
            )
            self.assertIsNone(error)
            self.assertIn(b'"agents":["fixture"]', persisted)
            self.assertIn(b'"path":"agents/review-final.md"', persisted)

        assert_survives()
        without_user = WRAPPER.REDACTION_EXEMPT_NAMES - {"USER"}
        with (
            mock.patch.object(WRAPPER, "REDACTION_EXEMPT_NAMES", without_user),
            self.assertRaises(AssertionError),
        ):
            assert_survives()

        type_patterns = [(b"type", b"<redacted:CANARY>")]
        capture = WRAPPER._EventCapture(type_patterns)
        _persisted, error = capture.line_bytes(serialized, terminated=True)
        self.assertEqual(error, "redaction damaged type")

    def test_secret_inside_init_model_is_structural_damage_in_process(self) -> None:
        secret = "admitted-model-secret"
        patterns = self.patterns({"CANARY": secret})
        raw = json.dumps({
            "type": "system", "subtype": "init", "model": f"prefix-{secret}",
        }).encode()

        def assert_damage() -> None:
            persisted, error = WRAPPER._EventCapture(patterns).line_bytes(
                raw, terminated=True
            )
            self.assertEqual(error, "redaction damaged model")
            self.assertIn(b"<redacted:CANARY>", persisted)
            self.assertNotIn(secret.encode(), persisted)

        assert_damage()
        with (
            mock.patch.object(
                WRAPPER._EventCapture, "_structural_damage", return_value=None
            ),
            self.assertRaises(AssertionError),
        ):
            assert_damage()

    def test_validated_claude_init_value_matches_are_redacted_without_damage(self) -> None:
        expectation = ("default", ("Read", "Grep"))
        event = {
            "type": "system",
            "subtype": "init",
            "permissionMode": "default",
            "tools": ["Grep", "Read"],
        }
        raw = json.dumps(event).encode()
        patterns = self.patterns({"AWS_PROFILE": "default", "AWS_REGION": "Read"})

        def assert_validated_values_pass() -> None:
            persisted, error = WRAPPER._EventCapture(
                patterns, expectation
            ).line_bytes(raw, terminated=True)
            self.assertIsNone(error)
            decoded = json.loads(persisted)
            self.assertEqual(decoded["permissionMode"], "<redacted:AWS_PROFILE>")
            self.assertEqual(decoded["tools"], ["Grep", "<redacted:AWS_REGION>"])

        assert_validated_values_pass()

        _persisted, error = WRAPPER._EventCapture(patterns).line_bytes(
            raw, terminated=True
        )
        self.assertEqual(error, "redaction damaged init.permissionMode")

        nonconforming = {**event, "permissionMode": "acceptEdits"}
        _persisted, error = WRAPPER._EventCapture(
            patterns, expectation
        ).line_bytes(json.dumps(nonconforming).encode(), terminated=True)
        self.assertEqual(error, "claude init mismatch")

        redact_json = WRAPPER._redact_json

        def old_damage_rule(
            value: object,
            selected_patterns: list[tuple[bytes, bytes]],
            scope: str = "top",
            *,
            validated_init: bool = False,
        ) -> tuple[object, str | None]:
            del validated_init
            return redact_json(
                value,
                selected_patterns,
                scope,
                validated_init=False,
            )

        with (
            mock.patch.object(WRAPPER, "_redact_json", side_effect=old_damage_rule),
            self.assertRaises(AssertionError),
        ):
            assert_validated_values_pass()

        def assert_key_damage(key: str) -> None:
            patterns = [(key.encode(), b"<redacted:KEY>")]
            _persisted, error = WRAPPER._EventCapture(
                patterns, expectation
            ).line_bytes(raw, terminated=True)
            self.assertEqual(error, f"redaction damaged init.{key}")

        for key in ("permissionMode", "tools"):
            with self.subTest(field=key, shape="key"):
                assert_key_damage(key)
        with (
            mock.patch.object(WRAPPER, "_protected_json_field", return_value=None),
            self.assertRaises(AssertionError),
        ):
            assert_key_damage("tools")

    def test_validated_claude_init_exemption_is_limited_to_first_event(self) -> None:
        expectation = ("default", ("Read", "Grep"))
        event = {
            "type": "system",
            "subtype": "init",
            "permissionMode": "default",
            "tools": ["Grep", "Read"],
        }
        raw = json.dumps(event).encode()

        def assert_later_init_damage(values: dict[str, str], field: str) -> None:
            capture = WRAPPER._EventCapture(self.patterns(values), expectation)
            first, first_error = capture.line_bytes(raw, terminated=True)
            self.assertIsNone(first_error)
            self.assertIn(b"<redacted:", first)
            second, second_error = capture.line_bytes(raw, terminated=True)
            self.assertEqual(second_error, f"redaction damaged {field}")
            self.assertIn(b"<redacted:", second)

        anchor = (
            "    validated_init = (\n"
            "        self.line == 1\n"
            "        and self.claude_init is not None\n"
            "        and init_error is None\n"
            "    )\n"
        )
        mutant = mutated_function(
            WRAPPER._EventCapture.line_bytes,
            anchor,
            "    validated_init = (\n"
            "        self.claude_init is not None\n"
            "        and init_error is None\n"
            "    )\n",
        )
        cases = (
            ({"AWS_PROFILE": "default"}, "init.permissionMode"),
            ({"AWS_REGION": "Read"}, "init.tools"),
        )
        for values, field in cases:
            with self.subTest(field=field):
                assert_later_init_damage(values, field)
                with (
                    mock.patch.object(WRAPPER._EventCapture, "line_bytes", mutant),
                    self.assertRaises(AssertionError),
                ):
                    assert_later_init_damage(values, field)

    def test_validated_claude_init_value_matches_pass_through_wrapper(self) -> None:
        source = """
import json, sys
sys.stdin.read()
print(json.dumps({'type':'result','is_error':False,
                  'result':'VERDICT: PASS'}), flush=True)
"""
        process, attempt = self.launch(
            "validated-init-value-redaction",
            source,
            environment={"AWS_PROFILE": "default", "AWS_REGION": "Read"},
        )
        completion = self.completion(process, attempt)
        events = [
            json.loads(line)
            for line in (attempt / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        self.assertIsNone(completion["error"])
        self.assertEqual(events[0]["permissionMode"], "<redacted:AWS_PROFILE>")
        self.assertEqual(
            events[0]["tools"], ["<redacted:AWS_REGION>", "Grep"]
        )

    def test_secret_inside_init_model_is_structural_damage_in_wrapper_source(self) -> None:
        secret = "admitted-model-secret"
        provider = """
import json, os, sys
sys.stdin.read()
print(json.dumps({'type':'system','subtype':'init',
                  'model':'prefix-' + os.environ['CANARY']}), flush=True)
"""

        def assert_damage(name: str, source: str | None = None) -> None:
            process, attempt = self.launch(
                name,
                provider,
                environment={"CANARY": secret},
                options=WrapperLaunchOptions(wrapper_source=source),
            )
            completion = self.completion(process, attempt)
            events = (attempt / "events.jsonl").read_bytes()
            self.assertEqual(completion["error"], "redaction damaged model")
            self.assertIn(b"<redacted:CANARY>", events)
            self.assertNotIn(secret.encode(), events)

        assert_damage("damaged-model-source")
        source = WRAPPER.wrapper_source()
        anchor = "        damaged = damaged or self._structural_damage(redacted)\n"
        self.assertEqual(source.count(anchor), 1)
        disabled = source.replace(anchor, "        damaged = damaged\n", 1)
        with self.assertRaises(AssertionError):
            assert_damage("damaged-model-source-disabled", disabled)

    def test_user_value_does_not_create_a_non_extractor_key_collision(self) -> None:
        patterns = self.patterns({"USER": "agents"})
        event = {
            "type": "system",
            "subtype": "init",
            "model": "fixture-model",
            "agents": ["redacted-key"],
            "<redacted:USER>": ["existing-key"],
        }
        serialized = json.dumps(event).encode()
        persisted, error = WRAPPER._EventCapture(patterns).line_bytes(
            serialized, terminated=True
        )
        self.assertIsNone(error)
        decoded = json.loads(persisted)
        self.assertEqual(decoded["agents"], ["redacted-key"])
        self.assertEqual(decoded["<redacted:USER>"], ["existing-key"])

    def test_non_extractor_key_collision_does_not_fail_closed(self) -> None:
        patterns = self.patterns({"HOME": "agents"})
        event = {
            "type": "system",
            "subtype": "init",
            "model": "fixture-model",
            "agents": ["redacted-key"],
            "<redacted:HOME>": ["existing-key"],
        }

        def assert_collision_survives() -> None:
            persisted, error = WRAPPER._EventCapture(patterns).line_bytes(
                json.dumps(event).encode(), terminated=True
            )
            self.assertIsNone(error)
            self.assertEqual(
                json.loads(persisted)["<redacted:HOME>"], ["existing-key"]
            )

        assert_collision_survives()
        redact_json = WRAPPER._redact_json

        def fail_any_key_collision(
            value: object,
            selected_patterns: list[tuple[bytes, bytes]],
            scope: str = "top",
            *,
            validated_init: bool = False,
        ) -> tuple[object, str | None]:
            transformed, damage = redact_json(
                value,
                selected_patterns,
                scope,
                validated_init=validated_init,
            )
            collided = (
                isinstance(value, dict)
                and isinstance(transformed, dict)
                and len(transformed) < len(value)
            )
            return transformed, damage or ("non-extractor" if collided else None)

        with (
            mock.patch.object(
                WRAPPER, "_redact_json", side_effect=fail_any_key_collision
            ),
            self.assertRaises(AssertionError),
        ):
            assert_collision_survives()

    def test_json_escaped_value_inside_result_remains_extractable(self) -> None:
        secret = 'line\nquote"slash\\snow'
        patterns = self.patterns({"CANARY": secret})
        event = {"type": "result", "is_error": False, "result": f"before {secret} after"}
        serialized = json.dumps(event, ensure_ascii=True).encode()
        redacted = WRAPPER._StreamRedactor(patterns).feed(serialized, final=True)
        capture = WRAPPER._EventCapture(patterns)
        _persisted, error = capture.line_bytes(redacted, terminated=True)
        verdict, verdict_error, _model = WRAPPER._capture_verdict(
            -1, "claude", capture, patterns
        )
        self.assertIsNone(error)
        self.assertIsNone(verdict_error)
        self.assertEqual(verdict, b"before <redacted:CANARY> after")

    def test_zero_through_three_byte_allowlisted_values_are_withheld(self) -> None:
        environment = {
            "HOME": "",
            "PATH": "p",
            "LANG": "cc",
            "LC_ALL": "ddd",
            "USER": "four",
            "TMPDIR": "five5",
            "TERM": "sixsix",
            "CODEX_HOME": "codex-home",
        }
        admitted, names, omitted = LAUNCH.allowed_environment("codex", environment)
        self.assertEqual(omitted, ("HOME", "LANG", "LC_ALL", "PATH"))
        self.assertEqual(names, tuple(sorted(admitted)))
        self.assertNotIn("HOME", admitted)
        self.assertEqual(admitted["USER"], "four")

    def test_codex_streams_and_staged_verdict_never_persist_passed_values(self) -> None:
        environment = {
            "LONG": "shared-prefix-secret",
            "SHORT": "shared-prefix",
            "LINE": "line\nsecret",
            "QUOTE": 'quote"slash\\snow-雪',
        }
        source = """
import json, os, pathlib, sys
prompt = sys.stdin.read()
def digest(name):
    prefix = name + ': '
    return next(line[len(prefix):] for line in prompt.splitlines()
                if line.startswith(prefix))
values = [os.environ[name] for name in sorted(os.environ)]
verdict = ('VERDICT: PASS\\n' + 'candidate: ' + digest('candidate') + '\\n' +
           'package: ' + digest('package') + '\\n' + '|'.join(values))
target = pathlib.Path(sys.argv[1])
temporary = target.with_name(target.name + '.provider-tmp')
temporary.write_text(verdict, encoding='utf-8')
os.replace(temporary, target)
print(json.dumps({'type':'turn.completed','payload':values}, ensure_ascii=True), flush=True)
print('|'.join(values), file=sys.stderr, flush=True)
"""
        attempt_path = self.root / "codex-redaction" / "verdict.staging"
        process, attempt = self.launch(
            "codex-redaction",
            source,
            settings=("codex", 5.0),
            arguments=(str(attempt_path),),
            environment=environment,
        )
        completion = self.completion(process, attempt)
        self.assertIsNone(completion["error"])
        durable = b"\n".join(
            (
                (attempt / "events.jsonl").read_bytes(),
                (attempt / "stderr.log").read_bytes(),
                (attempt / "verdict.txt").read_bytes(),
            )
        )
        for name, value in environment.items():
            with self.subTest(name=name):
                self.assertNotIn(value.encode(), durable)
                self.assertIn(f"<redacted:{name}>".encode(), durable)
        self.assertFalse((attempt / "verdict.staging").exists())

    def test_wrapper_passes_only_its_exact_environment(self) -> None:
        environment = {"ALLOWED": "allowed-value"}
        source = """
import json, os, sys
sys.stdin.read()
print(json.dumps({'type':'result','is_error':False,
                  'result':'VERDICT: PASS','names':sorted(os.environ)}), flush=True)
"""
        with mock.patch.dict(os.environ, {"FORBIDDEN_CANARY": "must-not-pass"}):
            process, attempt = self.launch(
                "environment-boundary", source, environment=environment
            )
            completion = self.completion(process, attempt)
        self.assertIsNone(completion["error"])
        events = (attempt / "events.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("FORBIDDEN_CANARY", events)
        self.assertIn("ALLOWED", events)

    def test_value_inside_citation_yields_an_invalid_redacted_verdict(self) -> None:
        environment = {"CANARY": "1111"}
        staging = self.root / "citation" / "verdict.staging"
        source = """
import json, pathlib, sys
sys.stdin.read()
target = pathlib.Path(sys.argv[1])
target.write_text('VERDICT: PASS\\ncandidate: ' + '1' * 64 +
                  '\\npackage: ' + '2' * 64 + '\\n', encoding='utf-8')
print(json.dumps({'type':'turn.completed'}), flush=True)
"""
        process, attempt = self.launch(
            "citation",
            source,
            settings=("codex", 5.0),
            arguments=(str(staging),),
            environment=environment,
        )
        completion = self.completion(process, attempt)
        self.assertIsNone(completion["error"])
        verdict = (attempt / "verdict.txt").read_bytes()
        self.assertIn(b"<redacted:CANARY>", verdict)
        with self.assertRaisesRegex(ValueError, "cite the current candidate"):
            COLLECT._parse_verdict(verdict, "1" * 64, "2" * 64)

    def test_stream_redaction_control_is_load_bearing_in_memory(self) -> None:
        patterns = [(b"credential-value", b"<redacted:CANARY>")]

        def assert_redacted() -> None:
            output = WRAPPER._StreamRedactor(patterns).feed(
                b"credential-value", final=True
            )
            self.assertNotIn(b"credential-value", output)

        assert_redacted()
        with mock.patch.object(WRAPPER._StreamRedactor, "_replace", lambda _self, value: value):
            with self.assertRaises(AssertionError):
                assert_redacted()


if __name__ == "__main__":
    unittest.main()
