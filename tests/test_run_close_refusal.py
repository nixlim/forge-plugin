from __future__ import annotations

import contextlib
import io
import json
import shutil
import unittest
from pathlib import Path
from unittest import mock

from tests._revision9_coord_constants import key
from tests._revision9_coord_support import Revision9BuilderBatchSupport

import codex_orch_tools
from codex_orchestrator import batch, builders, close_law, journal


class RunCloseRefusalTests(Revision9BuilderBatchSupport, unittest.TestCase):
    FIXED_TIME = "2026-09-30T12:00:00Z"
    CORRELATION_ISSUE = (
        "task 'task-01' has inconsistent bound candidate across gate and "
        "landing records"
    )
    GATE_ISSUES = (
        "run closed as passed without a passing 'gate-1' verification after "
        "the last mutating execution",
        "run closed as passed without a passing 'gate-2' verification after "
        "the last mutating execution",
        "run closed as passed without a passing 'gate-3: review-final verdict' "
        "verification after the last mutating execution",
    )

    @staticmethod
    def _binding(
        chain_id: str,
        seed: str,
        *,
        reviewed: bool = False,
    ) -> dict[str, object]:
        review = (
            {
                "verdict": "PASS",
                "iteration": 1,
                "reviewer_role": "review-final",
                "package_digest": key("run-close-review-package"),
            }
            if reviewed
            else None
        )
        preimage = {
            "schema": journal.BINDING_SCHEMA,
            "source_record": {
                "chain_id": chain_id,
                "event_digest": key(f"{seed}-event"),
            },
            "candidate": {
                "kind": "staged-diff-sha256",
                "value": key("run-close-candidate"),
            },
            "review": review,
        }
        return {
            **preimage,
            "binding_id": journal._sha256(
                journal._canonical_json_bytes(preimage)
            ),
        }

    def _add_bound_verification(
        self,
        repo: Path,
        run_id: str,
        chain_id: str,
        criterion: str,
        seed: str,
    ) -> None:
        binding = self._binding(
            chain_id,
            seed,
            reviewed=criterion == journal.GATE_3_CRITERION,
        )
        with mock.patch.object(builders, "resolve_binding", return_value=binding):
            builders.verification_add(
                repo,
                run_id,
                idempotency_key=key(f"{run_id}-{seed}"),
                task="task-01",
                criterion=criterion,
                method="unittest",
                check="python3 -m unittest synthetic",
                result="passed",
                observation="synthetic bound gate passed",
                evidence=[],
                binding_chain=chain_id,
                binding_id=str(binding["binding_id"]),
            )

    def _add_bound_landing(
        self, repo: Path, run_id: str, chain_id: str
    ) -> None:
        binding = self._binding(chain_id, "landing")
        with mock.patch.object(builders, "resolve_binding", return_value=binding):
            builders.decision_add(
                repo,
                run_id,
                idempotency_key=key(f"{run_id}-landing"),
                task="task-01",
                resolution="The synthetic candidate landed",
                finding=None,
                outcome="chain-landing",
                risk=None,
                basis=[],
                binding_chain=chain_id,
                binding_id=str(binding["binding_id"]),
            )

    def _capfix_run(self, name: str) -> tuple[Path, str, Path]:
        repo, head = self._new_repo(name)
        run_id = f"run-20260930-{name}"
        with self.api_environment():
            opening = self.open_run(repo, run_id).records[0]
            self.start_task(repo, run_id)
            run_dir = self.run_dir(repo, run_id)
            for relative in ("prompt.md", "events.jsonl", "handoff.md"):
                (run_dir / relative).write_text(
                    "synthetic evidence\n", encoding="utf-8"
                )
            route = opening["route"]
            assert isinstance(route, dict)
            implementer = route["implementer"]
            assert isinstance(implementer, dict)
            builders.execution_start(
                repo,
                run_id,
                idempotency_key=key(f"{run_id}-execution"),
                agent="codex-impl-01",
                task="task-01",
                provider=str(implementer["provider"]),
                role="implementer",
                mode="headless",
                model=str(implementer["model"]),
                effort=str(implementer["effort"]),
                worktree=str(repo.resolve()),
                head=head,
                prompt="prompt.md",
                handoff="handoff.md",
                event_source="exec",
                events="events.jsonl",
                sandbox="workspace-write",
                route_source=str(implementer["route_source"]),
                route_sha256=str(implementer["route_sha256"]),
            )
            builders.execution_result(
                repo,
                run_id,
                idempotency_key=key(f"{run_id}-result"),
                execution="execution-01",
                agent="codex-impl-01",
                task="task-01",
                status="complete",
                summary="Synthetic implementation completed",
                files_changed=["src/example.py"],
                caveats=[],
                handoff="handoff.md",
            )
            builders.decision_add(
                repo,
                run_id,
                idempotency_key=key(f"{run_id}-unbound-landing-evidence"),
                task="task-01",
                resolution="Record unbound landing evidence only",
                finding=None,
                outcome=None,
                risk=None,
                basis=["synthetic landing evidence"],
                binding_chain=None,
                binding_id=None,
            )
            builders.task_finish(
                repo,
                run_id,
                idempotency_key=key(f"{run_id}-finish"),
                task="task-01",
                status="complete",
            )
        return repo, run_id, run_dir

    def _four_qas_b_run(self, name: str) -> tuple[Path, str, Path]:
        repo, _head = self._new_repo(name)
        run_id = f"run-20260930-{name}"
        chain_id = "c-2026-09-30T120000Z-a401"
        with self.api_environment():
            self.open_run(repo, run_id)
            self.start_task(repo, run_id)
            self._add_bound_verification(
                repo, run_id, chain_id, "gate-2: stack validation", "gate-2"
            )
            self._add_bound_verification(
                repo, run_id, chain_id, journal.GATE_3_CRITERION, "gate-3"
            )
            self._add_bound_landing(repo, run_id, chain_id)
            with mock.patch.object(
                builders, "_terminal_chain_guard", return_value=None
            ):
                builders.task_finish(
                    repo,
                    run_id,
                    idempotency_key=key(f"{run_id}-finish"),
                    task="task-01",
                    status="complete",
                )
        return repo, run_id, self.run_dir(repo, run_id)

    def _passed_close_refusal(
        self, repo: Path, run_id: str, label: str
    ) -> str:
        with self.api_environment(), self.assertRaises(
            journal.CoordinationRefusal
        ) as raised:
            builders.run_close(
                repo,
                run_id,
                idempotency_key=key(f"{run_id}-{label}"),
                judgment="passed",
                summary="This passed close must be refused",
                risks=[],
                follow_ups=[],
            )
        return str(raised.exception)

    def _typed_blocked_close(
        self, repo: Path, run_id: str, close_key: str
    ) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        argv = [
            "run-close",
            "--repo",
            str(repo.resolve()),
            "--run-id",
            run_id,
            "--idempotency-key",
            close_key,
            "--judgment",
            "blocked",
            "--summary",
            "Close the synthetic run as blocked",
        ]
        with (
            self.api_environment(),
            mock.patch.object(journal, "_utc_now", return_value=self.FIXED_TIME),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = codex_orch_tools._typed_main(argv)
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_one_issue_is_named_without_suffix_and_refusal_is_read_only(
        self,
    ) -> None:
        repo, run_id, run_dir = self._four_qas_b_run("one-issue")
        journal_path = run_dir / "journal.jsonl"
        receipts_path = run_dir / journal.BATCH_RECEIPTS_NAME
        journal_before = journal_path.read_bytes()
        receipts_before = receipts_path.read_bytes()
        intent_path = run_dir / journal.BATCH_INTENT_NAME
        expected = (
            builders.RUN_CLOSE_VALIDATION_REFUSAL
            + ": "
            + self.CORRELATION_ISSUE
        )

        self.assertEqual(
            self._passed_close_refusal(repo, run_id, "enabled-close"), expected
        )
        self.assertEqual(journal_path.read_bytes(), journal_before)
        self.assertEqual(receipts_path.read_bytes(), receipts_before)
        self.assertFalse(intent_path.exists())
        self.assertEqual(journal._scan_run(run_dir).disposition, "open")

        disabled = close_law.RUN_CLOSE_LEGIBILITY_CONTROLS - {"first-issue"}
        with mock.patch.object(
            close_law, "RUN_CLOSE_LEGIBILITY_CONTROLS", disabled
        ):
            with self.assertRaises(AssertionError):
                self.assertEqual(
                    self._passed_close_refusal(
                        repo, run_id, "disabled-positive-assertion"
                    ),
                    expected,
                )
            self.assertEqual(
                self._passed_close_refusal(repo, run_id, "disabled-close"),
                builders.RUN_CLOSE_VALIDATION_REFUSAL,
            )

    def test_three_issues_name_first_and_report_two_more(self) -> None:
        repo, run_id, _run_dir = self._capfix_run("three-issues")
        expected = (
            builders.RUN_CLOSE_VALIDATION_REFUSAL
            + ": "
            + self.GATE_ISSUES[0]
            + " (+2 more; run journal close-preflight)"
        )

        self.assertEqual(
            self._passed_close_refusal(repo, run_id, "passed-close"), expected
        )

    def test_blocked_close_notices_preserve_stdout_and_skip_repeats(self) -> None:
        repo, run_id, _run_dir = self._capfix_run("blocked-notices")
        state_root = repo / ".codex-orchestrator"
        backup = Path(self.temporary.name) / "blocked-notices-backup"
        shutil.copytree(state_root, backup)
        registry_path = repo / ".forge/tmp/run-registry.json"
        registry_before = registry_path.read_bytes()
        close_key = key(f"{run_id}-blocked-close")
        expected_notices = [
            f"forge: notice — passed close would be refused: {issue}"
            for issue in self.GATE_ISSUES
        ]

        exit_code, enabled_stdout, enabled_stderr = self._typed_blocked_close(
            repo, run_id, close_key
        )
        self.assertEqual(exit_code, 0, enabled_stderr)
        self.assertEqual(enabled_stderr.splitlines(), expected_notices)
        repeated_code, _repeated_stdout, repeated_stderr = (
            self._typed_blocked_close(repo, run_id, close_key)
        )
        self.assertEqual(repeated_code, 0, repeated_stderr)
        self.assertEqual(repeated_stderr, "")

        shutil.rmtree(state_root)
        shutil.copytree(backup, state_root)
        registry_path.write_bytes(registry_before)
        disabled = close_law.RUN_CLOSE_LEGIBILITY_CONTROLS - {
            "blocked-close-projection"
        }
        with mock.patch.object(
            close_law, "RUN_CLOSE_LEGIBILITY_CONTROLS", disabled
        ):
            disabled_code, disabled_stdout, disabled_stderr = (
                self._typed_blocked_close(repo, run_id, close_key)
            )
        with self.assertRaises(AssertionError):
            self.assertEqual(disabled_stderr.splitlines(), expected_notices)
        self.assertEqual(disabled_code, 0, disabled_stderr)
        self.assertEqual(disabled_stdout, enabled_stdout)
        self.assertEqual(disabled_stderr, "")

    def test_blocked_close_notice_output_is_capped_at_fifty(self) -> None:
        issues = tuple(f"synthetic issue {index}" for index in range(52))
        outcome = batch.BatchOutcome(receipt={}, records=(), repeated=False)
        stdout = io.StringIO()
        stderr = io.StringIO()
        argv = [
            "run-close",
            "--repo",
            str(self.repo.resolve()),
            "--run-id",
            "run-20260930-notice-cap",
            "--idempotency-key",
            key("notice-cap"),
            "--judgment",
            "blocked",
            "--summary",
            "Exercise the notice cap",
        ]
        with (
            self.api_environment(),
            mock.patch.object(builders, "run_close", return_value=outcome),
            mock.patch.object(
                close_law, "blocked_close_passed_issues", return_value=issues
            ),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = codex_orch_tools._typed_main(argv)

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["repeated"], False)
        lines = stderr.getvalue().splitlines()
        self.assertEqual(len(lines), 51)
        self.assertTrue(lines[49].endswith("synthetic issue 49"))
        self.assertEqual(
            lines[50],
            "forge: notice — passed close would be refused: "
            "(+2 more; run journal close-preflight)",
        )


if __name__ == "__main__":
    unittest.main()
