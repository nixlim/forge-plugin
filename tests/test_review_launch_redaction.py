"""Boundary-safe and shape-aware credential redaction tests."""

from __future__ import annotations

import json
import os
import unittest
from unittest import mock

from tests._cli_loader import package_module
from tests.test_review_launch_streams import WrapperHarness

LAUNCH = package_module("engine._review_launch")
WRAPPER = package_module("engine._review_wrapper")
COLLECT = package_module("engine._verbs_review_collect")


class ReviewLaunchRedactionTests(WrapperHarness):
    def patterns(self, values: dict[str, str]) -> list[tuple[bytes, bytes]]:
        with mock.patch.dict(os.environ, values, clear=True):
            return WRAPPER._redaction_patterns(sorted(values))

    def test_raw_and_every_json_escaped_split_offset_are_redacted(self) -> None:
        values = {"CANARY": 'quote"line\nslash\\snow-雪'}
        patterns = self.patterns(values)
        replacement = b"<redacted:CANARY>"
        expected_patterns = {pattern for pattern, marker in patterns if marker == replacement}
        self.assertGreaterEqual(len(expected_patterns), 2)
        redactor = WRAPPER._StreamRedactor(patterns)
        self.assertEqual(
            redactor.carry_limit,
            max(len(pattern) for pattern in expected_patterns) - 1,
        )
        for pattern in expected_patterns:
            for offset in range(len(pattern) + 1):
                with self.subTest(pattern=pattern, offset=offset):
                    redactor = WRAPPER._StreamRedactor(patterns)
                    output = redactor.feed(b"left:" + pattern[:offset])
                    output += redactor.feed(pattern[offset:] + b":right", final=True)
                    self.assertEqual(output, b"left:" + replacement + b":right")

    def test_longest_first_prevents_prefix_leakage(self) -> None:
        values = {"LONG": "shared-prefix-secret", "SHORT": "shared-prefix"}
        patterns = self.patterns(values)
        raw = b"shared-prefix-secret shared-prefix"
        output = WRAPPER._StreamRedactor(patterns).feed(raw, final=True)
        self.assertEqual(output, b"<redacted:LONG> <redacted:SHORT>")
        self.assertNotIn(b"shared-prefix", output)

    def test_recorded_agents_key_passes_but_extractor_key_fails_closed(self) -> None:
        agents_patterns = [(b"agents", b"<redacted:USER>")]
        capture = WRAPPER._EventCapture(agents_patterns)
        event = {
            "type": "system",
            "subtype": "init",
            "model": "fixture-model",
            "agents": ["fixture"],
        }
        serialized = json.dumps(event).encode()
        redacted = WRAPPER._StreamRedactor(agents_patterns).feed(serialized, final=True)
        persisted, error = capture.line_bytes(redacted, terminated=True)
        self.assertIsNone(error)
        self.assertIn(b'"<redacted:USER>":["fixture"]', persisted)

        type_patterns = [(b"type", b"<redacted:CANARY>")]
        capture = WRAPPER._EventCapture(type_patterns)
        redacted = WRAPPER._StreamRedactor(type_patterns).feed(serialized, final=True)
        _persisted, error = capture.line_bytes(redacted, terminated=True)
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
                wrapper_source=source,
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

    def test_non_extractor_key_collision_does_not_fail_closed(self) -> None:
        patterns = [(b"agents", b"<redacted:USER>")]
        event = {
            "type": "system",
            "subtype": "init",
            "model": "fixture-model",
            "agents": ["redacted-key"],
            "<redacted:USER>": ["existing-key"],
        }
        serialized = json.dumps(event).encode()
        redacted = WRAPPER._StreamRedactor(patterns).feed(serialized, final=True)
        persisted, error = WRAPPER._EventCapture(patterns).line_bytes(
            redacted, terminated=True
        )
        self.assertIsNone(error)
        self.assertEqual(json.loads(persisted)["<redacted:USER>"], ["existing-key"])

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
