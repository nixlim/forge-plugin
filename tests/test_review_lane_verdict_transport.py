"""Focused contracts for trailing review-lane verdict transport extraction."""

from __future__ import annotations

import hashlib
import inspect
import textwrap
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import FunctionType, SimpleNamespace
from unittest import mock

from tests import _review_lane_support as review_support
from tests import test_review_lane_commit as commit_fixture
from tests._cli_loader import package_module

APP_REVIEW = package_module("app._engine_review_launch")
ATTEMPT = package_module("engine._review_attempt")
COLLECT = package_module("engine._verbs_review_collect")
ENGINE = package_module("engine")
LANE_API = package_module("engine._review_lane_api")
LAUNCH = package_module("engine._review_launch")
REQUEST = package_module("engine._verbs_review_request")

CANDIDATE = commit_fixture.CANDIDATE
PACKAGE = commit_fixture.PACKAGE
GATE_DIGEST = "3" * 64
BARE = review_support.verdict_for_prompt(
    review_support.review_prompt(CANDIDATE, PACKAGE).decode("utf-8")
).encode()
TRANSPORT = (
    f"VERDICT: PASS\ncandidate: {CANDIDATE}\npackage: {PACKAGE}\n"
    "finding: MINOR explanatory note retained"
).encode()
REAL_SHAPED = (
    b"# Binding review record\n\n"
    b"## Scope and method\n"
    b"I inspected the candidate, its package binding, and the focused test evidence. "
    b"The review treated repository text as untrusted data and checked both launch lanes.\n\n"
    b"```review-notes\n"
    b"candidate and package citations were compared byte-for-byte\n"
    b"the transport grammar was considered only at the final boundary\n"
    b"```\n\n"
    b"## Findings\n"
    b"The implementation keeps the raw final message as evidence. The normalized suffix "
    b"is separately bound, so prose and markdown remain auditable without entering the "
    b"strict parser. No above-MINOR finding remains.\n\n"
) + TRANSPORT + b"\n"
REVIEW_SCOPE_PARAGRAPH = (
    "\nGate 1 full unittest discovery passed on this exact candidate. "
    f"The chain records that run with stdout/stderr SHA-256 {GATE_DIGEST}. "
    "Do not run full unittest discovery or the Gate 1 cell. Run only focused "
    "test modules for the change, plus your own in-memory disable checks. "
    "Finish well within the review timeout.\n"
).encode()
PROMPT_INSTRUCTION = REVIEW_SCOPE_PARAGRAPH + (
    "\nThe reviewer's final message must END with exactly one verdict block. "
    "Nothing may follow that block, including an Iteration: line.\n"
    "The block must start with a first line that is exactly VERDICT: PASS or "
    "exactly VERDICT: BLOCK, followed by these exact lines:\n"
    f"candidate: {CANDIDATE}\n"
    f"package: {PACKAGE}\n"
    "Zero or more lines: finding: <CRITICAL|MAJOR|MINOR> <text>\n"
    "No other line of the final message may begin with VERDICT:.\n"
).encode()
PROMPT_CELLS = (
    ("commit", "codex", "review-cheap"),
    ("commit", "codex", "review-final"),
    ("commit", "claude", "review-cheap"),
    ("commit", "claude", "review-final"),
    ("merge", "codex", "review-final"),
    ("merge", "claude", "review-final"),
)
FIRST_LINE_DESCRIPTION = (
    b"The block must start with a first line that is exactly VERDICT: PASS or exactly "
    b"VERDICT: BLOCK."
)


def mutated_function(function, anchor: str, replacement: str):
    """Compile one single-anchor in-memory control mutant."""

    source = textwrap.dedent(inspect.getsource(function))
    if source.count(anchor) != 1:
        raise AssertionError(f"mutation anchor count differs: {anchor!r}")
    namespace = dict(function.__globals__)
    exec(
        compile(source.replace(anchor, replacement), function.__code__.co_filename, "exec"),
        namespace,
    )
    mutant = namespace[function.__name__]
    if not isinstance(mutant, FunctionType):
        raise AssertionError("mutation did not produce a function")
    return mutant


def assert_no_copyable_verdict_line(prompt: bytes) -> None:
    prefixed = [
        line for line in prompt.splitlines() if line.strip().startswith(b"VERDICT:")
    ]
    if prefixed:
        raise AssertionError(f"copyable verdict line in prompt: {prefixed!r}")


class VerdictTransportTests(unittest.TestCase):
    def _commit_collect(self, raw: bytes) -> dict[str, object]:
        request = commit_fixture.new_request()
        state = commit_fixture.reviewing(request)
        completion = commit_fixture.completed(request, raw)
        observation = ATTEMPT.AttemptObservation(
            "completed", identity=commit_fixture.IDENTITY, completion=completion
        )
        captured: dict[str, object] = {}
        fake = commit_fixture.fake_engine(
            state,
            apply=lambda _state, verdict, ref: captured.update(
                verdict=verdict, recorded_data=None, verdict_ref=ref
            ),
        )

        def read(_ctx, _state, path, digest, *_args, **_kwargs):
            if path == "verdict":
                self.assertEqual(digest, hashlib.sha256(raw).hexdigest())
                return raw
            return b"bound"

        with (
            mock.patch.object(ATTEMPT, "mark_stale_attempts", return_value=()),
            mock.patch.object(
                COLLECT, "_attempt_fd", return_value=nullcontext((9, "completion"))
            ),
            mock.patch.object(ATTEMPT, "observe_attempt", return_value=observation),
            mock.patch.object(COLLECT, "_read_bound_artifact", side_effect=read),
            mock.patch.object(
                COLLECT, "_write_artifact", return_value="synthetic-verdict"
            ),
        ):
            COLLECT._new_lane_collect(fake, state, request)
        captured["completion"] = completion
        return captured

    def _merge_finish(self, raw: bytes) -> dict[str, object]:
        state = {"candidate": {"candidate_head": CANDIDATE}}
        request = {
            "package_digest": PACKAGE,
            "verdict_path": "verdict",
            "completion_path": "completion",
        }
        completion = {
            "error": None,
            "timed_out": False,
            "returncode": 0,
            "verdict_digest": hashlib.sha256(raw).hexdigest(),
            "verdict_size": len(raw),
        }
        captured: dict[str, object] = {}

        def record(_state, verdict, data, _changed_paths):
            captured.update(verdict=verdict, recorded_data=data, verdict_ref="verdict")
            return "recorded"

        def read(_ctx, _state, _path, digest, *_args, **_kwargs):
            self.assertEqual(digest, hashlib.sha256(raw).hexdigest())
            return raw

        fake = SimpleNamespace(ctx=SimpleNamespace(), _record_review_verdict=record)
        with mock.patch.object(APP_REVIEW.engine, "_read_bound_artifact", side_effect=read):
            APP_REVIEW._finish_completed_review(fake, state, request, completion, [])
        captured["completion"] = completion
        return captured

    def _lane_records(self, raw: bytes) -> dict[str, dict[str, object]]:
        return {"commit": self._commit_collect(raw), "merge": self._merge_finish(raw)}

    def _assert_synthetic_block(self, raw: bytes, diagnostic: str) -> None:
        expected = f"no reviewer verdict — invalid verdict: {diagnostic}; completion completion"
        for lane, record in self._lane_records(raw).items():
            with self.subTest(lane=lane, diagnostic=diagnostic):
                verdict = record["verdict"]
                self.assertEqual(verdict["verdict"], "BLOCK")
                self.assertEqual(verdict["findings"], [{"severity": "MAJOR", "text": expected}])
                self.assertNotIn("verdict_transport_digest", verdict)
                self.assertEqual(
                    record["completion"]["verdict_digest"], hashlib.sha256(raw).hexdigest()
                )

    def test_real_shaped_and_bare_outputs_are_accepted_on_both_lanes(self) -> None:
        self.assertGreater(len(REAL_SHAPED), 500)
        for label, raw, transport in (
            ("real-shaped", REAL_SHAPED, TRANSPORT),
            ("bare", BARE, BARE.rstrip(b"\n")),
        ):
            for lane, record in self._lane_records(raw).items():
                with self.subTest(shape=label, lane=lane):
                    verdict = record["verdict"]
                    self.assertEqual(verdict["verdict"], "PASS")
                    self.assertEqual(
                        verdict["verdict_transport_digest"],
                        hashlib.sha256(transport).hexdigest(),
                    )
                    self.assertEqual(
                        record["completion"]["verdict_digest"],
                        hashlib.sha256(raw).hexdigest(),
                    )
                    if lane == "commit":
                        self.assertEqual(record["verdict_ref"], "verdict")
                    else:
                        self.assertEqual(record["recorded_data"], raw)

    def test_merge_raw_verdict_evidence_disable_leg_fails(self) -> None:
        self.assertEqual(self._merge_finish(REAL_SHAPED)["recorded_data"], REAL_SHAPED)
        mutant = mutated_function(
            APP_REVIEW._finish_completed_review,
            "return self._record_review_verdict(state, verdict, data, changed_paths)",
            "return self._record_review_verdict(state, verdict, transport, changed_paths)",
        )
        with mock.patch.object(APP_REVIEW, "_finish_completed_review", mutant):
            record = self._merge_finish(REAL_SHAPED)
        self.assertEqual(
            record["verdict"]["verdict_transport_digest"],
            hashlib.sha256(TRANSPORT).hexdigest(),
        )
        with self.assertRaises(AssertionError):
            self.assertEqual(record["recorded_data"], REAL_SHAPED)

    def test_transport_normalization_strips_lines_and_discards_blanks(self) -> None:
        raw = (
            "review prose\n\n"
            "  VERDICT: PASS  \n\n"
            f"  candidate: {CANDIDATE}  \n"
            f" package: {PACKAGE}\n\n"
            " finding: MINOR explanatory note retained  \n"
        ).encode()
        self.assertEqual(LANE_API.verdict_transport(raw), TRANSPORT)

    def test_each_invalid_output_fails_closed_with_the_exact_diagnostic(self) -> None:
        cases = (
            (b"\xff" + BARE, "verdict is not UTF-8"),
            (
                b"# review without a final transport\ncandidate: absent\npackage: absent\n",
                "reviewer final message has no exact verdict line",
            ),
            (
                b"# quoted grammar\n```text\nVERDICT: PASS\n```\n" + BARE,
                "reviewer final message has more than one exact verdict line",
            ),
            (
                b"VERDICT: MAYBE is illustrative prose\n" + BARE,
                "unexpected VERDICT-prefixed line: VERDICT: MAYBE is illustrative prose",
            ),
            (BARE + b"trailing prose\n", "unexpected verdict line: trailing prose"),
            (
                BARE + b"finding: INFO unsupported severity\n",
                "finding line has invalid grammar",
            ),
            (
                BARE.replace(CANDIDATE.encode(), b"9" * 64),
                "verdict must cite the current candidate exactly once",
            ),
            (
                BARE.replace(PACKAGE.encode(), b"8" * 64),
                "verdict must cite the package digest exactly once",
            ),
        )
        for raw, diagnostic in cases:
            with self.subTest(diagnostic=diagnostic):
                self._assert_synthetic_block(raw, diagnostic)

    def test_nonexact_verdict_prefixed_prose_and_template_echo_fail_closed(self) -> None:
        cases = (
            (
                "VERDICT: PASS — no MAJOR findings",
                "unexpected VERDICT-prefixed line: "
                "VERDICT: PASS — no MAJOR findings",
            ),
            (
                "VERDICT: PASS|BLOCK",
                "unexpected VERDICT-prefixed line: VERDICT: PASS|BLOCK",
            ),
        )
        for prefixed_line, diagnostic in cases:
            with self.subTest(prefixed_line=prefixed_line):
                self._assert_synthetic_block(
                    f"{prefixed_line}\n".encode() + BARE, diagnostic
                )

    def test_strict_parser_still_accepts_only_the_transport(self) -> None:
        with self.assertRaises(ValueError) as caught:
            COLLECT._parse_verdict(REAL_SHAPED, CANDIDATE, PACKAGE)
        self.assertEqual(
            str(caught.exception),
            "first non-empty line must be VERDICT: PASS or VERDICT: BLOCK",
        )
        parsed = COLLECT._parse_verdict(TRANSPORT, CANDIDATE, PACKAGE)
        self.assertEqual(parsed["verdict"], "PASS")
        self.assertEqual(parsed["findings"][0]["severity"], "MINOR")

    def test_extraction_disabled_turns_real_shaped_pass_into_synthetic_block(self) -> None:
        with mock.patch.object(LANE_API, "verdict_transport", side_effect=lambda data: data):
            self._assert_synthetic_block(
                REAL_SHAPED,
                "first non-empty line must be VERDICT: PASS or VERDICT: BLOCK",
            )

    def test_extractor_fail_closed_rules_have_independent_source_mutants(self) -> None:
        quoted = b"# quote\nVERDICT: PASS\n# final\n" + BARE
        cases = (
            (
                b"\xff" + BARE,
                "verdict is not UTF-8",
                'text = data.decode("utf-8")',
                'text = data.decode("utf-8", errors="ignore")',
            ),
            (
                f"candidate: {CANDIDATE}\npackage: {PACKAGE}\n".encode(),
                "reviewer final message has no exact verdict line",
                'raise ValueError("reviewer final message has no exact verdict line")',
                "verdict_indexes.append(0)",
            ),
            (
                quoted,
                "reviewer final message has more than one exact verdict line",
                'raise ValueError("reviewer final message has more than one exact verdict line")',
                "verdict_indexes = verdict_indexes[-1:]",
            ),
            (
                b"VERDICT: MAYBE\n" + BARE,
                "unexpected VERDICT-prefixed line: VERDICT: MAYBE",
                'raise ValueError(f"unexpected VERDICT-prefixed line: {line}")',
                "continue",
            ),
            (
                BARE + b"tail\n",
                "unexpected verdict line: tail",
                'raise ValueError(f"unexpected verdict line: {line}")',
                "continue",
            ),
            (
                BARE + b"finding: INFO unsupported\n",
                "finding line has invalid grammar",
                'raise ValueError("finding line has invalid grammar")',
                "continue",
            ),
        )
        for raw, diagnostic, anchor, replacement in cases:
            with self.subTest(diagnostic=diagnostic):
                with self.assertRaises(ValueError) as caught:
                    LANE_API.verdict_transport(raw)
                self.assertEqual(str(caught.exception), diagnostic)
                mutant = mutated_function(LANE_API.verdict_transport, anchor, replacement)
                self.assertIsInstance(mutant(raw), bytes)

    def test_candidate_and_package_bindings_have_independent_parser_mutants(self) -> None:
        cases = (
            (
                BARE.replace(CANDIDATE.encode(), b"9" * 64),
                "verdict must cite the current candidate exactly once",
                'if candidate_lines != [f"candidate: {candidate}"]:',
            ),
            (
                BARE.replace(PACKAGE.encode(), b"8" * 64),
                "verdict must cite the package digest exactly once",
                'if package_lines != [f"package: {package}"]:',
            ),
        )
        for raw, diagnostic, anchor in cases:
            with self.subTest(diagnostic=diagnostic):
                with self.assertRaises(ValueError) as caught:
                    COLLECT._parse_verdict(raw, CANDIDATE, PACKAGE)
                self.assertEqual(str(caught.exception), diagnostic)
                mutant = mutated_function(COLLECT._parse_verdict, anchor, "if False:")
                self.assertEqual(mutant(raw, CANDIDATE, PACKAGE)["verdict"], "PASS")

    def _prompt(
        self, lane: str, provider: str, role: str, oversized: bool
    ) -> bytes:
        paths = SimpleNamespace(
            role_body=b"review-final role\n", package_path=Path("/fixture/package")
        )
        route = LAUNCH.ReviewRoute(
            role, provider, "fixture-model", "high", "committed-default", "a" * 64,
            "read-only" if provider == "codex" else "instruction-bounded",
        )
        commit_state = {
            "kind": "commit",
            "candidate": {"sha256": CANDIDATE},
            "steps": {"gate-1": [{
                "candidate": CANDIDATE, "result": "passed",
                "stdout_stderr_digest": GATE_DIGEST,
            }]},
        }
        parts = (
            b"package", role, [], {}, b"header", b"control", b"fresh", b"diff"
        )
        merge_state = {
            "kind": "merge",
            "candidate": {
                "candidate_head": CANDIDATE, "generation_digest": "4" * 64,
            },
            "steps": {"gate-1": [{
                "result": "passed", "generation_digest": "4" * 64,
                "criterion": "gate-1: full unittest discovery",
                "stdout_stderr_digest": GATE_DIGEST,
            }]},
        }
        with (
            mock.patch.object(REQUEST, "_review_package_is_oversized", return_value=oversized),
            mock.patch.object(
                REQUEST, "_review_master_pointer_prompt", return_value=b"commit pointer\n"
            ),
            mock.patch.object(
                APP_REVIEW.engine, "_review_package_is_oversized", return_value=oversized
            ),
            mock.patch.object(
                APP_REVIEW.engine, "_review_master_pointer_prompt", return_value=b"merge pointer\n"
            ),
        ):
            if lane == "commit":
                return REQUEST._review_prompt(
                    commit_state, parts, paths.package_path, PACKAGE, route, paths
                )
            return APP_REVIEW._review_prompt(
                merge_state, b"package", paths.package_path, PACKAGE, route, paths
            )

    def test_prompt_instruction_bytes_disclose_prefix_and_trailing_rules(self) -> None:
        self.assertEqual(
            LANE_API.verdict_prompt_instruction(
                CANDIDATE,
                PACKAGE,
                {
                    "kind": "commit",
                    "candidate": {"sha256": CANDIDATE},
                    "steps": {"gate-1": [{
                        "candidate": CANDIDATE, "result": "passed",
                        "stdout_stderr_digest": GATE_DIGEST,
                    }]},
                },
            ),
            PROMPT_INSTRUCTION,
        )
        self.assertNotIn(b"\nVERDICT:", PROMPT_INSTRUCTION)
        self.assertFalse(any(
            line.startswith(b"VERDICT:") for line in REVIEW_SCOPE_PARAGRAPH.splitlines()
        ))
        self.assertIn(
            b"Nothing may follow that block, including an Iteration: line.",
            PROMPT_INSTRUCTION,
        )
        self.assertIn(
            b"No other line of the final message may begin with VERDICT:.",
            PROMPT_INSTRUCTION,
        )
        self.assertIn(
            f"\ncandidate: {CANDIDATE}\npackage: {PACKAGE}\n".encode(),
            PROMPT_INSTRUCTION,
        )
        assert_no_copyable_verdict_line(PROMPT_INSTRUCTION)

    def test_output_contract_templates_describe_but_do_not_copy_verdict_line(self) -> None:
        prompts = (
            self._prompt("commit", "codex", "review-final", False),
            self._prompt("merge", "codex", "review-final", False),
            ENGINE._review_master_pointer_prompt(
                "/fixture/package", 123, PACKAGE, CANDIDATE
            ),
        )
        for index, prompt in enumerate(prompts):
            with self.subTest(template=index):
                self.assertIn(FIRST_LINE_DESCRIPTION, prompt)
                assert_no_copyable_verdict_line(prompt)
                mutant = prompt.replace(
                    FIRST_LINE_DESCRIPTION, b"VERDICT: PASS|BLOCK", 1
                )
                with self.assertRaises(AssertionError):
                    assert_no_copyable_verdict_line(mutant)

    def test_prompt_builders_append_exact_instruction_for_every_provider_role_cell(
        self,
    ) -> None:
        for oversized in (False, True):
            for lane, provider, role in PROMPT_CELLS:
                with self.subTest(
                    lane=lane, provider=provider, role=role, oversized=oversized
                ):
                    prompt = self._prompt(lane, provider, role, oversized)
                    self.assertTrue(prompt.endswith(PROMPT_INSTRUCTION))
                    self.assertEqual(prompt.count(PROMPT_INSTRUCTION), 1)
                    self.assertEqual(prompt.count(REVIEW_SCOPE_PARAGRAPH), 1)
                    assert_no_copyable_verdict_line(prompt)

    def test_prompt_scope_paragraph_disable_leg_fails_for_every_prompt_path(
        self,
    ) -> None:
        mutant = mutated_function(
            LANE_API.verdict_prompt_instruction,
            "return review_scope_paragraph(state) + verdict_block_instruction(",
            "return b'' + verdict_block_instruction(",
        )
        for oversized in (False, True):
            for lane, provider, role in PROMPT_CELLS:
                with self.subTest(
                    lane=lane, provider=provider, role=role, oversized=oversized
                ):
                    prompt = self._prompt(lane, provider, role, oversized)
                    self.assertEqual(prompt.count(REVIEW_SCOPE_PARAGRAPH), 1)
                    with mock.patch.object(
                        LANE_API, "verdict_prompt_instruction", new=mutant
                    ), self.assertRaises(AssertionError):
                        prompt = self._prompt(lane, provider, role, oversized)
                        self.assertEqual(prompt.count(REVIEW_SCOPE_PARAGRAPH), 1)


if __name__ == "__main__":
    unittest.main()
