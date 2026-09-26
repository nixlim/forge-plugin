from __future__ import annotations

import hashlib
import unittest
from unittest import mock

from tests._revision9_coord_constants import key
from tests._revision9_coord_support import Revision9BuilderBatchSupport

from codex_orchestrator import builders, journal

route_provenance = journal.route_provenance


class TaskCompletionProvenanceTests(
    Revision9BuilderBatchSupport, unittest.TestCase
):
    def setUp(self) -> None:
        super().setUp()
        self.env.pop("CLAUDE_CODE_SESSION_ID", None)
        self.execution_number = 0

    @staticmethod
    def _scope(run_id: str) -> str:
        return f"scopes/{run_id}/**"

    def _open(self, run_id: str, *, legacy: bool = False) -> dict[str, object]:
        with self.api_environment():
            if legacy:
                self._open_legacy_run(
                    self.repo, run_id, scope=[self._scope(run_id)]
                )
                records, issues = journal.read_journal(
                    self.run_dir(self.repo, run_id) / "journal.jsonl"
                )
                self.assertEqual(issues, [])
                return records[0]
            return builders.run_open(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-open"),
                goal="Exercise FR-247",
                scope=[self._scope(run_id)],
                plugin_ref="forge-test-completion-provenance",
            ).records[0]

    def _start_task(self, run_id: str, task: str = "task-01") -> None:
        with self.api_environment():
            builders.task_start(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-{task}-start"),
                task=task,
                goal="Prove completion provenance",
                acceptance=["The provenance is explicit"],
                files=[f"scopes/{run_id}/{task}.py"],
            )
        run_dir = self.run_dir(self.repo, run_id)
        for relative in ("prompt.md", "events.jsonl", "handoff.md", "ownership.txt"):
            (run_dir / relative).write_text("evidence\n", encoding="utf-8")

    def _setup(self, run_id: str, *, legacy: bool = False) -> dict[str, object]:
        opening = self._open(run_id, legacy=legacy)
        self._start_task(run_id)
        return opening

    def _execution(self, run_id: str, opening: dict[str, object], task: str = "task-01") -> str:
        self.execution_number += 1
        route = opening.get("route")
        entry = route.get("implementer") if isinstance(route, dict) else None
        if not isinstance(entry, dict):
            entry = {
                "provider": "codex",
                "model": "legacy-model",
                "effort": "high",
            }
        optional = (
            {
                "sandbox": journal.route_evidence.route_config.profile_sandbox(
                    str(entry["provider"]), "implementer"
                ),
                "route_source": entry["route_source"],
                "route_sha256": entry["route_sha256"],
            }
            if "route_source" in entry
            else {}
        )
        with self.api_environment():
            outcome = builders.execution_start(
                self.repo,
                run_id,
                idempotency_key=key(
                    f"{run_id}-{task}-execution-{self.execution_number}"
                ),
                agent="codex-impl-01",
                task=task,
                provider=str(entry["provider"]),
                role="implementer",
                mode="headless",
                model=str(entry["model"]),
                effort=str(entry["effort"]),
                worktree=str(self.repo.resolve()),
                head=self.head,
                prompt="prompt.md",
                handoff="handoff.md",
                event_source="exec",
                events="events.jsonl",
                **optional,
            )
        return str(outcome.records[0]["execution"])

    def _result(
        self,
        run_id: str,
        execution: str,
        *,
        task: str = "task-01",
        status: str,
    ) -> None:
        with self.api_environment():
            builders.execution_result(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-{task}-result-{status}-{execution}"),
                execution=execution,
                agent="codex-impl-01",
                task=task,
                status=status,
                summary=f"Execution ended {status}",
                files_changed=[],
                caveats=[],
                handoff="handoff.md" if status == "complete" else None,
            )

    def _finish(self, run_id: str, task: str = "task-01"):
        with self.api_environment():
            return builders.task_finish(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-{task}-finish"),
                task=task,
                status="complete",
            )

    def _assert_finish_refused(self, run_id: str, task: str = "task-01") -> None:
        with self.assertRaises(journal.CoordinationRefusal) as caught:
            self._finish(run_id, task)
        self.assertEqual(
            f"forge: task-finish refused — task {task} has no completion provenance "
            "(FR-247: implementer execution with a complete result, bound "
            "chain-landing decision, or an 'orchestrator-owned: <reason>' decision "
            "with basis)",
            str(caught.exception),
        )

    def _decision(
        self,
        run_id: str,
        *,
        task: str | None,
        resolution: str,
        basis: list[str],
    ) -> None:
        with self.api_environment():
            builders.decision_add(
                self.repo,
                run_id,
                idempotency_key=key(
                    f"{run_id}-decision-{task}-{resolution}-{basis!r}"
                ),
                task=task,
                resolution=resolution,
                finding=None,
                outcome=None,
                risk=None,
                basis=basis,
                binding_chain=None,
                binding_id=None,
            )

    def test_no_execution_or_decision_refuses(self) -> None:
        run_id = "run-20260925-provenance-none"
        self._setup(run_id)
        self._assert_finish_refused(run_id)
        disabled = "run-20260925-provenance-none-disabled"
        self._setup(disabled)
        with mock.patch.object(
            route_provenance, "enforce_task_finish", return_value=None
        ):
            with self.assertRaises(AssertionError):
                self._assert_finish_refused(disabled)

    def test_unterminated_and_failed_implementer_refuse(self) -> None:
        for index, status in enumerate((None, "failed", "blocked"), 1):
            with self.subTest(status=status):
                run_id = f"run-20260925-provenance-incomplete-{index}"
                opening = self._setup(run_id)
                execution = self._execution(run_id, opening)
                if status is not None:
                    self._result(run_id, execution, status=status)
                self._assert_finish_refused(run_id)

    def test_complete_implementer_result_admits_and_control_is_load_bearing(self) -> None:
        run_id = "run-20260925-provenance-complete"
        opening = self._setup(run_id)
        execution = self._execution(run_id, opening)
        self._result(run_id, execution, status="complete")
        self.assertEqual(self._finish(run_id).records[0]["status"], "complete")

        disabled = "run-20260925-provenance-complete-disabled"
        opening = self._setup(disabled)
        execution = self._execution(disabled, opening)
        self._result(disabled, execution, status="complete")
        with mock.patch.object(
            route_provenance, "completion_provenance", return_value=None
        ):
            self._assert_finish_refused(disabled)

    def test_different_task_execution_does_not_admit(self) -> None:
        run_id = "run-20260925-provenance-other-task"
        opening = self._setup(run_id)
        self._start_task(run_id, "task-02")
        execution = self._execution(run_id, opening, "task-02")
        self._result(run_id, execution, task="task-02", status="complete")
        self._assert_finish_refused(run_id)

    def test_bound_chain_landing_decision_admits(self) -> None:
        run_id = "run-20260925-provenance-landing"
        self._setup(run_id)
        chain_id = "c-2026-09-25T120000Z-abcd"
        preimage = {
            "schema": journal.BINDING_SCHEMA,
            "source_record": {
                "chain_id": chain_id,
                "event_digest": key("landing-event"),
            },
            "candidate": {
                "kind": "staged-diff-sha256",
                "value": key("landing-candidate"),
            },
            "review": None,
        }
        binding = {
            **preimage,
            "binding_id": hashlib.sha256(
                journal._canonical_json_bytes(preimage)
            ).hexdigest(),
        }
        with self.api_environment(), mock.patch.object(
            builders, "resolve_binding", return_value=binding
        ):
            builders.decision_add(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-landing"),
                task="task-01",
                resolution="The bound candidate landed",
                finding=None,
                outcome="chain-landing",
                risk=None,
                basis=[],
                binding_chain=chain_id,
                binding_id=str(binding["binding_id"]),
            )
        with mock.patch.object(builders, "_terminal_chain_guard", return_value=None):
            self.assertEqual(self._finish(run_id).records[0]["status"], "complete")

        invalid_preimage = {**preimage, "candidate": {}}
        invalid = {
            "type": "decision",
            "task": "task-01",
            "outcome": "chain-landing",
            "binding": {
                **invalid_preimage,
                "binding_id": hashlib.sha256(
                    journal._canonical_json_bytes(invalid_preimage)
                ).hexdigest(),
            },
        }
        self.assertIsNone(
            route_provenance.completion_provenance([invalid], "task-01")
        )

    def test_bound_landing_binding_shape_matches_journal_validator(self) -> None:
        staged = {"kind": "staged-diff-sha256", "value": key("equivalence-candidate")}
        tree_oid = "b" * 40
        tree_authorization = hashlib.sha256(
            b"forge-commit-candidate/2\0sha1\0"
            + tree_oid.encode("ascii")
            + b"\n"
        ).hexdigest()

        def tree_candidate(
            authorization_id: str, **extra: object
        ) -> dict[str, object]:
            return {
                "kind": "git-tree-candidate-v2",
                "value": {
                    "authorization_id": authorization_id,
                    "object_format": "sha1",
                    "tree_oid": tree_oid,
                    **extra,
                },
            }

        def make_binding(
            candidate: dict[str, object], **source_updates: object
        ) -> dict[str, object]:
            review = source_updates.pop("review", None)
            source: dict[str, object] = {
                "chain_id": "c-2026-09-25T120000Z-abcd",
                "event_digest": key("equivalence-event"),
            }
            source.update(source_updates)
            preimage = {
                "schema": journal.BINDING_SCHEMA,
                "source_record": source,
                "candidate": candidate,
                "review": review,
            }
            return {
                **preimage,
                "binding_id": hashlib.sha256(
                    journal._canonical_json_bytes(preimage)
                ).hexdigest(),
            }

        valid = make_binding(staged)
        range_value = {"base": "a" * 40, "head": "b" * 40}
        tree_extra = tree_candidate(tree_authorization, extra="forbidden")
        range_extra = {"kind": "git-range", "value": {**range_value, "extra": "forbidden"}}
        review = {
            "verdict": "PASS",
            "iteration": 1,
            "reviewer_role": "review-final",
            "package_digest": key("equivalence-review"),
        }
        fixtures = (
            ("valid-tree", make_binding(tree_candidate(tree_authorization)), True),
            ("binding-key-set", {**valid, "generation_id": "forbidden"}, False),
            ("source-key-set", make_binding(staged, generation_id="forbidden"), False),
            ("candidate-key-set", make_binding({**staged, "extra": "forbidden"}), False),
            ("tree-value-key-set", make_binding(tree_extra), False),
            ("range-value-key-set", make_binding(range_extra), False),
            (
                "chain-id-grammar",
                make_binding(staged, chain_id="c-2026-09-25T120000Z-ABCD"),
                False,
            ),
            ("object-id-grammar", make_binding({"kind": "git-commit", "value": "a" * 39}), False),
            ("tree-authorization-derivation", make_binding(tree_candidate("f" * 64)), False),
            ("review-must-be-null", make_binding(staged, review=review), False),
        )
        for name, binding, expected in fixtures:
            with self.subTest(case=name):
                record = {
                    "type": "decision",
                    "task": "task-01",
                    "outcome": "chain-landing",
                    "binding": binding,
                }
                journal_verdict = journal._binding_chain_and_candidate(record) is not None
                route_verdict = route_provenance._bound_landing(record, "task-01")
                self.assertEqual((route_verdict, journal_verdict), (expected, expected), name)

    def test_orchestrator_owned_decision_admits(self) -> None:
        run_id = "run-20260925-provenance-owned"
        self._setup(run_id)
        self._decision(
            run_id,
            task="task-01",
            resolution="orchestrator-owned: documentation-only task",
            basis=["ownership.txt"],
        )
        self.assertEqual(self._finish(run_id).records[0]["status"], "complete")

    def test_orchestrator_owned_grammar_requires_task_reason_and_basis(self) -> None:
        cases = (
            (None, "orchestrator-owned: valid reason", ["ownership.txt"]),
            ("task-01", "orchestrator-owned: ", ["ownership.txt"]),
            ("task-01", "orchestrator-owned: valid reason", []),
        )
        for index, (task, resolution, basis) in enumerate(cases, 1):
            with self.subTest(missing=index):
                run_id = f"run-20260925-provenance-owned-invalid-{index}"
                self._setup(run_id)
                self._decision(
                    run_id, task=task, resolution=resolution, basis=basis
                )
                self._assert_finish_refused(run_id)

    def test_run_close_lists_every_offending_task_bytewise(self) -> None:
        run_id = "run-20260925-provenance-close"
        self._open(run_id)
        for task in ("task-z", "task-a"):
            self._start_task(run_id, task)
        with mock.patch.object(
            route_provenance, "enforce_task_finish", return_value=None
        ):
            for task in ("task-z", "task-a"):
                self._finish(run_id, task)
        validation = {
            "ok": True,
            "issues": [],
            "warnings": [],
            "non_passing_verifications": [],
        }
        with (
            self.api_environment(),
            mock.patch.object(journal, "validate_run", return_value=validation),
            mock.patch.object(journal, "check_gate_profile", return_value=None),
            self.assertRaises(journal.CoordinationRefusal) as caught,
        ):
            builders.run_close(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-close"),
                judgment="passed",
                summary="All work is complete",
                risks=[],
                follow_ups=[],
            )
        self.assertEqual(
            "forge: run-close refused — task task-a recorded complete without "
            "completion provenance (FR-247)\n"
            "forge: run-close refused — task task-z recorded complete without "
            "completion provenance (FR-247)",
            str(caught.exception),
        )
        with (
            self.api_environment(),
            mock.patch.object(journal, "validate_run", return_value=validation),
            mock.patch.object(journal, "check_gate_profile", return_value=None),
            mock.patch.object(route_provenance, "enforce_run_close", return_value=None),
            self.assertRaises(AssertionError),
        ):
            with self.assertRaises(journal.CoordinationRefusal):
                builders.run_close(
                    self.repo,
                    run_id,
                    idempotency_key=key(f"{run_id}-close-disabled"),
                    judgment="passed",
                    summary="The disabled control must not pass its assertion",
                    risks=[],
                    follow_ups=[],
                )

    def test_run_close_checks_empty_files_records_outside_typed_writes(self) -> None:
        """Typed writes refuse empty files; this function-level branch defends raw records."""
        task = "task-empty-files"
        records = [
            {"type": "run_started", "route": {}},
            {
                "type": "task",
                "id": task,
                "status": "complete",
                "files": [],
            },
        ]
        expected = (
            f"forge: run-close refused — task {task} recorded complete without "
            "completion provenance (FR-247)"
        )

        def assert_refused() -> None:
            with self.assertRaises(journal.CoordinationRefusal) as caught:
                route_provenance.enforce_run_close(
                    records,
                    "passed",
                    refusal=journal.CoordinationRefusal,
                )
            self.assertEqual(expected, str(caught.exception))

        assert_refused()
        with mock.patch.object(
            route_provenance, "enforce_run_close", return_value=None
        ):
            with self.assertRaises(AssertionError):
                assert_refused()

        records.append(
            {
                "type": "decision",
                "task": task,
                "resolution": "orchestrator-owned: imported raw task record",
                "basis": ["raw journal provenance"],
            }
        )
        self.assertIsNone(
            route_provenance.enforce_run_close(
                records,
                "passed",
                refusal=journal.CoordinationRefusal,
            )
        )

    def test_pre_j_run_is_never_checked(self) -> None:
        run_id = "run-20260925-provenance-legacy"
        self._setup(run_id, legacy=True)
        self.assertEqual(self._finish(run_id).records[0]["status"], "complete")
        validation = {
            "ok": True,
            "issues": [],
            "warnings": [],
            "non_passing_verifications": [],
        }
        with (
            self.api_environment(),
            mock.patch.object(journal, "validate_run", return_value=validation),
            mock.patch.object(journal, "check_gate_profile", return_value=None),
        ):
            closed = builders.run_close(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-close"),
                judgment="passed",
                summary="Legacy compatibility remains open",
                risks=[],
                follow_ups=[],
            )
        self.assertEqual(closed.records[0]["judgment"], "passed")


if __name__ == "__main__":
    unittest.main()
