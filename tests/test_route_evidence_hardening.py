from __future__ import annotations

import errno
import inspect
import os
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FORGE_SCRIPTS = SCRIPTS / "forge"
for search_path in (SCRIPTS, FORGE_SCRIPTS):
    if str(search_path) not in sys.path:
        sys.path.insert(0, str(search_path))

from codex_orchestrator import journal  # noqa: E402

route_evidence = journal.route_evidence
route_vocab = route_evidence.route_vocab

SESSION_ID = "route-evidence-hardening"
MODEL_LINE = b'{"type":"assistant","message":{"model":"opus"}}\n'
EXPECTED_ROLE_REFUSAL = (
    "forge: journal append refused — invalid journal record: execution role "
    "'implementer' is not canonical; use one of implementer, review-cheap, "
    "review-final, plan, monitoring"
)
REFUSAL_BLOCK = (
    "    if role is None:\n"
    "        _refuse(\n"
    '            f"execution role {raw_role!r} is not canonical; use one of "\n'
    '            + ", ".join(route_vocab.ROLE_IDS),\n'
    "            refusal,\n"
    "        )\n"
)


class RouteEvidenceHardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.scratch = Path(self.temporary.name)
        self.home = self.scratch / "home"
        self.home.mkdir()
        self.repo = self.scratch / "nonexistent-repo"
        self.transcript = (
            self.home
            / ".claude"
            / "projects"
            / route_evidence._project_slug(self.repo)
            / f"{SESSION_ID}.jsonl"
        )
        self.transcript.parent.mkdir(parents=True)
        self.environment = mock.patch.dict(
            os.environ,
            {"HOME": str(self.home), "CLAUDE_CODE_SESSION_ID": SESSION_ID},
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def _release_fifo(self) -> None:
        deadline = time.monotonic() + 5
        while True:
            try:
                descriptor = os.open(
                    self.transcript, os.O_WRONLY | os.O_NONBLOCK
                )
            except OSError as exc:
                if exc.errno == errno.ENXIO and time.monotonic() < deadline:
                    time.sleep(0.01)
                    continue
                raise
            os.close(descriptor)
            return

    def _bounded_orchestrator_model(
        self, timeout: float, *, expect_blocked: bool = False
    ) -> dict[str, object]:
        outcome: dict[str, object] = {}

        def invoke() -> None:
            try:
                outcome["result"] = route_evidence.orchestrator_model(self.repo)
            except BaseException as exc:
                outcome["error"] = exc

        worker = threading.Thread(target=invoke, daemon=True)
        worker.start()
        worker.join(timeout)
        blocked = worker.is_alive()
        try:
            if expect_blocked:
                self.assertTrue(blocked, "disabled nonblocking control did not block")
            elif blocked:
                self.fail("orchestrator_model blocked while opening a FIFO")
        finally:
            if blocked:
                self._release_fifo()
                worker.join(5)
        self.assertFalse(worker.is_alive(), "FIFO reader survived its bounded release")
        error = outcome.get("error")
        if isinstance(error, BaseException):
            raise error
        result = outcome.get("result")
        self.assertIsInstance(result, dict)
        assert isinstance(result, dict)
        return result

    @staticmethod
    def _compiled_route_evidence(source: str, *, optimize: int) -> types.ModuleType:
        module = types.ModuleType("_route_evidence_hardening_compiled")
        module.__file__ = str(ROOT / "scripts/forge/route_evidence.py")
        code = compile(source, module.__file__, "exec", optimize=optimize)
        exec(code, module.__dict__)
        return module

    def _execution_candidate(self, **updates: object) -> dict[str, object]:
        candidate: dict[str, object] = {
            "type": "execution",
            "recorded_at": "2026-09-27T12:00:00Z",
            "agent": "codex-impl-01",
            "task": "task-01",
            "provider": "codex",
            "role": "implementer",
            "mode": "headless",
            "model": "gpt-test",
            "effort": "high",
            "execution": "execution-01",
            "worktree": str(self.scratch.resolve()),
            "head": "a" * 40,
            "prompt": "prompt.md",
            "handoff": "handoff.md",
            "event_source": "exec",
            "events": "events.jsonl",
        }
        candidate.update(updates)
        return candidate

    def _validate_candidate(
        self, candidate: dict[str, object], *, historical: object | None = None
    ) -> dict[str, object]:
        return journal._validate_proposed_record(
            candidate,
            run_id="run-boundary",
            repo_root=self.scratch.resolve(),
            scope=("src/**",),
            _historical_replay=historical,
        )

    def test_fifo_transcript_degrades_without_blocking(self) -> None:
        os.mkfifo(self.transcript)
        descriptors_before = len(os.listdir("/dev/fd"))
        self.assertEqual(
            self._bounded_orchestrator_model(5),
            {"observed": None, "reason": "unreadable"},
        )
        self.assertEqual(len(os.listdir("/dev/fd")), descriptors_before)

        disabled_flags = route_evidence.TRANSCRIPT_OPEN_FLAGS & ~os.O_NONBLOCK
        with mock.patch.object(
            route_evidence, "TRANSCRIPT_OPEN_FLAGS", disabled_flags
        ):
            self.assertEqual(
                self._bounded_orchestrator_model(1, expect_blocked=True),
                {"observed": None, "reason": "unreadable"},
            )

    def test_non_regular_transcript_is_rejected_before_reading(self) -> None:
        os.mkfifo(self.transcript)
        with self.subTest(path_type="fifo"):
            with mock.patch.object(
                route_evidence.os, "fdopen", wraps=os.fdopen
            ) as fdopen:
                self.assertEqual(
                    self._bounded_orchestrator_model(5),
                    {"observed": None, "reason": "unreadable"},
                )
                self.assertEqual(fdopen.call_count, 0)
        self.transcript.unlink()

        with self.subTest(path_type="directory"):
            self.transcript.mkdir()
            with mock.patch.object(
                route_evidence.os, "fdopen", wraps=os.fdopen
            ) as fdopen:
                self.assertEqual(
                    route_evidence.orchestrator_model(self.repo),
                    {"observed": None, "reason": "unreadable"},
                )
                self.assertEqual(fdopen.call_count, 0)
            self.transcript.rmdir()

        os.mkfifo(self.transcript)
        fake_stat = SimpleNamespace(S_ISREG=lambda _mode: True)
        with (
            mock.patch.object(route_evidence, "stat", fake_stat),
            mock.patch.object(route_evidence.os, "fdopen", wraps=os.fdopen) as fdopen,
        ):
            self.assertEqual(
                self._bounded_orchestrator_model(5),
                {"observed": None, "reason": "unreadable"},
            )
            self.assertGreaterEqual(fdopen.call_count, 1)

    def test_symlinked_transcript_is_not_followed(self) -> None:
        target = self.scratch / "regular-transcript.jsonl"
        target.write_bytes(MODEL_LINE)
        self.transcript.symlink_to(target)
        self.assertEqual(
            route_evidence.orchestrator_model(self.repo),
            {"observed": None, "reason": "unreadable"},
        )

        self.transcript.unlink()
        self.transcript.symlink_to(self.scratch / "missing-transcript.jsonl")
        self.assertEqual(
            route_evidence.orchestrator_model(self.repo),
            {"observed": None, "reason": "unreadable"},
        )

        self.transcript.unlink()
        self.transcript.symlink_to(target)
        disabled_flags = route_evidence.TRANSCRIPT_OPEN_FLAGS & ~os.O_NOFOLLOW
        with mock.patch.object(
            route_evidence, "TRANSCRIPT_OPEN_FLAGS", disabled_flags
        ):
            self.assertEqual(
                route_evidence.orchestrator_model(self.repo),
                {"observed": "opus"},
            )

    def test_regular_and_absent_transcripts_unchanged(self) -> None:
        self.assertEqual(
            route_evidence.orchestrator_model(self.repo),
            {"observed": None, "reason": "transcript-absent"},
        )
        self.transcript.write_bytes(MODEL_LINE)
        self.assertEqual(
            route_evidence.orchestrator_model(self.repo),
            {"observed": "opus"},
        )
        self.transcript.write_bytes(
            b"x" * (route_evidence.TRANSCRIPT_TAIL_BYTES + 10)
            + b"\n"
            + MODEL_LINE
        )
        self.assertEqual(
            route_evidence.orchestrator_model(self.repo),
            {"observed": "opus"},
        )

    def test_execution_validation_has_no_historical_mode(self) -> None:
        self.assertEqual(
            list(inspect.signature(route_evidence.validate_execution).parameters),
            ["record", "prior_records", "refusal"],
        )
        candidate = self._execution_candidate()
        with mock.patch.object(
            route_evidence,
            "validate_execution",
            wraps=route_evidence.validate_execution,
        ) as validate:
            self.assertEqual(self._validate_candidate(candidate), candidate)
            validate.assert_called_once_with(
                candidate, (), refusal=journal.CoordinationRefusal
            )

        historical = self._execution_candidate(sandbox="danger-full-access")
        with mock.patch.object(
            route_evidence,
            "validate_execution",
            wraps=route_evidence.validate_execution,
        ) as validate:
            self.assertEqual(
                self._validate_candidate(
                    historical, historical=journal._HISTORICAL_REPLAY
                ),
                historical,
            )
            self.assertEqual(validate.call_count, 0)

        expected = (
            "forge: journal append refused — invalid journal record: execution "
            "route fields must be given together (sandbox, route_source, route_sha256)"
        )
        with mock.patch.object(
            route_evidence,
            "validate_execution",
            wraps=route_evidence.validate_execution,
        ) as validate:
            with self.assertRaises(journal.CoordinationRefusal) as caught:
                self._validate_candidate(historical, historical=object())
            self.assertEqual(str(caught.exception), expected)
            validate.assert_called_once_with(
                historical, (), refusal=journal.CoordinationRefusal
            )

    def test_unresolvable_role_refuses_even_with_asserts_stripped(self) -> None:
        record = {
            "role": "implementer",
            "provider": "codex",
            "mode": "headless",
            "event_source": "exec",
            "sandbox": "workspace-write",
            "route_source": "local",
            "route_sha256": "a" * 64,
        }
        prior = ({"type": "run_started", "route": {"implementer": {}}},)
        path = ROOT / "scripts/forge/route_evidence.py"
        source = path.read_text(encoding="utf-8")

        with mock.patch.object(route_vocab, "canonical_role", return_value=None):
            with self.assertRaises(journal.CoordinationRefusal) as caught:
                route_evidence.validate_execution(
                    record, prior, refusal=journal.CoordinationRefusal
                )
            self.assertEqual(str(caught.exception), EXPECTED_ROLE_REFUSAL)
            self.assertNotIsInstance(caught.exception, AssertionError)

            optimized = self._compiled_route_evidence(source, optimize=1)
            with self.assertRaises(journal.CoordinationRefusal) as caught:
                optimized.validate_execution(
                    record, prior, refusal=journal.CoordinationRefusal
                )
            self.assertEqual(str(caught.exception), EXPECTED_ROLE_REFUSAL)

            self.assertEqual(source.count(REFUSAL_BLOCK), 1)
            mutant_source = source.replace(
                REFUSAL_BLOCK, "    assert role is not None\n"
            )
            mutant = self._compiled_route_evidence(mutant_source, optimize=1)
            with self.assertRaises(journal.CoordinationRefusal) as caught:
                mutant.validate_execution(
                    record, prior, refusal=journal.CoordinationRefusal
                )
            self.assertNotEqual(str(caught.exception), EXPECTED_ROLE_REFUSAL)
            self.assertIn("role None has no frozen route", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
