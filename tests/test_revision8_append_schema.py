from __future__ import annotations

import json
import unittest
from unittest import mock

from tests._revision8_constants import RECORDED_AT
from tests._revision8_support import Revision8Support

from codex_orchestrator import journal


class Revision8AppendSchemaTests(Revision8Support, unittest.TestCase):

    def test_all_seven_strict_minimum_record_types_append(self) -> None:
        opened = self.open_run("run-seven", "src/**")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        self.create_citation_files("run-seven")

        records = (
            self.task_record(),
            self.execution_record(),
            self.execution_result_record(),
            self.verification_record(),
            self.decision_record(future_extension={"schema": 2}),
        )
        for record in records:
            with self.subTest(record_type=record["type"]):
                appended = self.append_record("run-seven", record)
                self.assertEqual(appended.returncode, 0, appended.stderr)
        closed = self.close("run-seven")
        self.assertEqual(closed.returncode, 0, closed.stderr)

        landed = [
            json.loads(line)
            for line in self.journal_path("run-seven").read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(
            [record["type"] for record in landed],
            [
                "run_started",
                "task",
                "execution",
                "execution_result",
                "verification",
                "decision",
                "run_closed",
            ],
        )
        self.assertEqual(landed[-2]["future_extension"], {"schema": 2})

    def test_per_type_first_required_field_diagnostics_are_exact(self) -> None:
        opened = self.open_run("run-matrix", "src/**")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        self.create_citation_files("run-matrix")
        before = self.coordination_snapshot()

        cases: tuple[
            tuple[str, dict[str, object], str, str], ...
        ] = (
            (
                "run_started",
                self.opening_record("run-missing-start-id"),
                "run_id",
                "run_started.run_id is required",
            ),
            ("task", self.task_record(), "id", "task.id is required"),
            (
                "execution",
                self.execution_record(),
                "agent",
                "execution.agent is required",
            ),
            (
                "execution_result",
                self.execution_result_record(),
                "agent",
                "execution_result.agent is required",
            ),
            (
                "verification",
                self.verification_record(),
                "id",
                "verification.id is required",
            ),
            ("decision", self.decision_record(), "id", "decision.id is required"),
            (
                "run_closed",
                self.closure_record(),
                "judgment",
                "run_closed.judgment is required",
            ),
        )
        for kind, candidate, missing, detail in cases:
            with self.subTest(record_type=kind):
                candidate.pop(missing)
                if kind == "run_started":
                    refused = self.open_run(
                        "run-missing-start-id", "other/**", record=candidate
                    )
                    self.assertFalse(self.run_dir("run-missing-start-id").exists())
                elif kind == "run_closed":
                    refused = self.close("run-matrix", record=candidate)
                else:
                    refused = self.append_record("run-matrix", candidate)
                self.assertEqual(refused.returncode, 1)
                self.assertEqual(
                    refused.stderr,
                    f"forge: journal append refused — invalid journal record: {detail}\n",
                )
                self.assertEqual(self.coordination_snapshot(), before)

    def test_fr019_common_and_required_string_boundaries(self) -> None:
        kinds = (
            "run_started",
            "task",
            "execution",
            "execution_result",
            "verification",
            "decision",
            "run_closed",
        )
        for kind in kinds:
            with self.subTest(kind=kind, field="recorded_at", mutation="missing"):
                candidate = self.valid_candidate(kind)
                candidate.pop("recorded_at")
                self.assert_invalid_candidate(
                    candidate, f"{kind}.recorded_at is required"
                )
            for bad_value in (None, "", "2026-08-26T12:00:00+00:00"):
                with self.subTest(
                    kind=kind, field="recorded_at", bad_value=bad_value
                ):
                    candidate = self.valid_candidate(kind)
                    candidate["recorded_at"] = bad_value
                    self.assert_invalid_candidate(
                        candidate,
                        f"{kind}.recorded_at must be a valid UTC RFC-3339 "
                        "timestamp ending in Z",
                    )
            if kind != "run_started":
                for bad_value in (None, "", "invalid/run-id"):
                    with self.subTest(
                        kind=kind, field="run_id", bad_value=bad_value
                    ):
                        candidate = self.valid_candidate(kind)
                        candidate["run_id"] = bad_value
                        self.assert_invalid_candidate(
                            candidate, f"{kind}.run_id must be a valid run ID"
                        )
                candidate = self.valid_candidate(kind)
                candidate["run_id"] = "run-somewhere-else"
                self.assert_invalid_candidate(
                    candidate, f"{kind}.run_id must match target run"
                )

        ordinary = "must be nonempty"
        fields: dict[str, tuple[tuple[str, str, str], ...]] = {
            "run_started": (
                ("run_id", "must be a valid run ID", "must be a valid run ID"),
                ("goal", "must be a string", ordinary),
                ("repo", "must be a string", "must be an absolute path"),
                ("repo_head", "must be a string", "must be a full Git object ID"),
                ("plugin_ref", "must be a string", ordinary),
            ),
            "task": (
                ("id", "must be a string", ordinary),
                (
                    "status",
                    "must be a string",
                    "must be one of active, complete, blocked, failed",
                ),
                ("goal", "must be a string", ordinary),
            ),
            "execution": tuple(
                (field, "must be a string", ordinary)
                for field in (
                    "agent",
                    "task",
                    "provider",
                    "role",
                    "mode",
                    "model",
                    "effort",
                )
            )
            + (
                ("execution", "must be a string", "must match execution-NN"),
                ("worktree", "must be a string", "must be an absolute path"),
                ("head", "must be a string", "must be a full Git object ID"),
                ("prompt", "must be a string", ordinary),
                ("handoff", "must be a string", ordinary),
                ("event_source", "must be a string", ordinary),
            ),
            "execution_result": (
                ("agent", "must be a string", ordinary),
                ("task", "must be a string", ordinary),
                ("summary", "must be a string", ordinary),
                ("execution", "must be a string", "must match execution-NN"),
                (
                    "status",
                    "must be a string",
                    "must be one of complete, blocked, failed",
                ),
                ("handoff", "must be a string", ordinary),
            ),
            "verification": tuple(
                (field, "must be a string", ordinary)
                for field in (
                    "id",
                    "task",
                    "criterion",
                    "method",
                    "check",
                    "observation",
                )
            )
            + (
                (
                    "result",
                    "must be a string",
                    "must be one of passed, failed, inconclusive, skipped",
                ),
            ),
            "decision": (
                ("id", "must be a string", ordinary),
                ("resolution", "must be a string", ordinary),
            ),
            "run_closed": (
                (
                    "judgment",
                    "must be a string",
                    "must be one of passed, blocked",
                ),
                ("summary", "must be a string", ordinary),
            ),
        }
        for kind, definitions in fields.items():
            for field, wrong_type, empty in definitions:
                with self.subTest(kind=kind, field=field, mutation="missing"):
                    candidate = self.valid_candidate(kind)
                    candidate.pop(field)
                    self.assert_invalid_candidate(
                        candidate, f"{kind}.{field} is required"
                    )
                with self.subTest(kind=kind, field=field, mutation="wrong-type"):
                    candidate = self.valid_candidate(kind)
                    candidate[field] = None
                    self.assert_invalid_candidate(
                        candidate, f"{kind}.{field} {wrong_type}"
                    )
                with self.subTest(kind=kind, field=field, mutation="empty"):
                    candidate = self.valid_candidate(kind)
                    candidate[field] = ""
                    self.assert_invalid_candidate(candidate, f"{kind}.{field} {empty}")

    def test_fr019_format_enum_repository_and_scope_boundaries(self) -> None:
        format_cases: tuple[tuple[str, str, object, str], ...] = (
            (
                "run_started",
                "run_id",
                "invalid/run-id",
                "must be a valid run ID",
            ),
            (
                "run_started",
                "run_id",
                "run-different",
                "must match target run",
            ),
            (
                "run_started",
                "repo",
                "relative/repo",
                "must be an absolute path",
            ),
            (
                "run_started",
                "repo",
                str(self.root.resolve()),
                "must match target repository",
            ),
            (
                "run_started",
                "repo_head",
                "f" * 39,
                "must be a full Git object ID",
            ),
            (
                "execution",
                "execution",
                "execution-1",
                "must match execution-NN",
            ),
            (
                "execution_result",
                "execution",
                "execution-001",
                "must match execution-NN",
            ),
            (
                "execution",
                "worktree",
                "relative/worktree",
                "must be an absolute path",
            ),
            (
                "execution",
                "head",
                "A" * 40,
                "must be a full Git object ID",
            ),
        )
        for kind, field, bad_value, requirement in format_cases:
            with self.subTest(kind=kind, field=field, bad_value=bad_value):
                candidate = self.valid_candidate(kind)
                candidate[field] = bad_value
                self.assert_invalid_candidate(
                    candidate, f"{kind}.{field} {requirement}"
                )

        enum_cases = {
            "task": ("status", ("active", "complete", "blocked", "failed")),
            "execution_result": (
                "status",
                ("complete", "blocked", "failed"),
            ),
            "verification": (
                "result",
                ("passed", "failed", "inconclusive", "skipped"),
            ),
            "run_closed": ("judgment", ("passed", "blocked")),
        }
        for kind, (field, allowed) in enum_cases.items():
            for value in allowed:
                with self.subTest(kind=kind, field=field, allowed=value):
                    candidate = self.valid_candidate(kind)
                    candidate[field] = value
                    if kind == "execution_result" and value != "complete":
                        candidate.pop("handoff")
                    self.assert_valid_candidate(candidate)
            candidate = self.valid_candidate(kind)
            candidate[field] = "not-an-enum-member"
            self.assert_invalid_candidate(
                candidate,
                f"{kind}.{field} must be one of {', '.join(allowed)}",
            )

        scope_cases: tuple[tuple[object, str], ...] = (
            (None, "run_started.scope must be an array"),
            ([], "run_started.scope must be nonempty"),
            (
                ["src/ok/**", ""],
                "run_started.scope[1] must be a nonempty string",
            ),
            (
                ["src/z/**", "src/a/**"],
                "run_started.scope must be a canonical nonempty admitted scope",
            ),
            (
                ["../escape"],
                "run_started.scope must be a canonical nonempty admitted scope",
            ),
        )
        candidate = self.valid_candidate("run_started")
        candidate.pop("scope")
        self.assert_invalid_candidate(candidate, "run_started.scope is required")
        for value, detail in scope_cases:
            with self.subTest(field="scope", value=value):
                candidate = self.valid_candidate("run_started")
                candidate["scope"] = value
                self.assert_invalid_candidate(candidate, detail)

        for value, requirement in (
            (["../escape"], "must be a positive repository-relative Git pathspec"),
            (["elsewhere/**"], "must be contained by admitted scope"),
        ):
            candidate = self.valid_candidate("task")
            candidate["files"] = value
            self.assert_invalid_candidate(
                candidate, f"task.files[0] {requirement}"
            )

    def test_fr019_all_arrays_and_nested_validation_boundaries(self) -> None:
        arrays: tuple[tuple[str, str, bool, bool, list[str]], ...] = (
            ("run_started", "repo_status", True, False, [" M file", ""]),
            ("task", "acceptance", True, True, ["criterion", ""]),
            ("task", "files", True, True, ["src/valid.py", ""]),
            (
                "execution_result",
                "files_changed",
                True,
                False,
                ["src/valid.py", ""],
            ),
            ("execution_result", "caveats", True, False, ["none", ""]),
            ("verification", "evidence", False, False, ["proof.txt", ""]),
            ("decision", "basis", False, False, ["decision-00", ""]),
            ("run_closed", "risks", True, False, ["risk", ""]),
            ("run_closed", "follow_ups", True, False, ["follow-up", ""]),
        )
        for kind, field, required, nonempty, bad_members in arrays:
            with self.subTest(kind=kind, field=field, mutation="missing"):
                candidate = self.valid_candidate(kind)
                candidate.pop(field, None)
                if required:
                    self.assert_invalid_candidate(
                        candidate, f"{kind}.{field} is required"
                    )
                else:
                    self.assert_valid_candidate(candidate)
            with self.subTest(kind=kind, field=field, mutation="wrong-type"):
                candidate = self.valid_candidate(kind)
                candidate[field] = None
                self.assert_invalid_candidate(
                    candidate, f"{kind}.{field} must be an array"
                )
            with self.subTest(kind=kind, field=field, mutation="empty"):
                candidate = self.valid_candidate(kind)
                candidate[field] = []
                if nonempty:
                    self.assert_invalid_candidate(
                        candidate, f"{kind}.{field} must be nonempty"
                    )
                else:
                    self.assert_valid_candidate(candidate)
            with self.subTest(kind=kind, field=field, mutation="member-index"):
                candidate = self.valid_candidate(kind)
                candidate[field] = bad_members
                self.assert_invalid_candidate(
                    candidate,
                    f"{kind}.{field}[1] must be a nonempty string",
                )

        validation_fields = (
            "issues",
            "warnings",
            "non_passing_verifications",
        )
        candidate = self.valid_candidate("run_closed")
        candidate.pop("validation")
        self.assert_invalid_candidate(candidate, "run_closed.validation is required")
        candidate = self.valid_candidate("run_closed")
        candidate["validation"] = []
        self.assert_invalid_candidate(
            candidate, "run_closed.validation must be an object"
        )
        for field in validation_fields:
            with self.subTest(validation_field=field, mutation="missing"):
                candidate = self.valid_candidate("run_closed")
                validation = candidate["validation"]
                assert isinstance(validation, dict)
                validation.pop(field)
                self.assert_invalid_candidate(
                    candidate, f"run_closed.validation.{field} is required"
                )
            with self.subTest(validation_field=field, mutation="wrong-type"):
                candidate = self.valid_candidate("run_closed")
                validation = candidate["validation"]
                assert isinstance(validation, dict)
                validation[field] = None
                self.assert_invalid_candidate(
                    candidate, f"run_closed.validation.{field} must be an array"
                )
        for field in ("issues", "warnings"):
            candidate = self.valid_candidate("run_closed")
            validation = candidate["validation"]
            assert isinstance(validation, dict)
            validation[field] = ["first", ""]
            self.assert_invalid_candidate(
                candidate,
                f"run_closed.validation.{field}[1] must be a nonempty string",
            )

        candidate = self.valid_candidate("run_closed")
        validation = candidate["validation"]
        assert isinstance(validation, dict)
        validation.pop("ok")
        self.assert_invalid_candidate(candidate, "run_closed.validation.ok is required")
        for bad_value in (None, 0, 1, "true"):
            candidate = self.valid_candidate("run_closed")
            validation = candidate["validation"]
            assert isinstance(validation, dict)
            validation["ok"] = bad_value
            self.assert_invalid_candidate(
                candidate, "run_closed.validation.ok must be Boolean"
            )
        candidate = self.valid_candidate("run_closed")
        validation = candidate["validation"]
        assert isinstance(validation, dict)
        validation.pop("profile")
        self.assert_invalid_candidate(
            candidate, "run_closed.validation.profile is required"
        )
        for bad_value in (None, "", "default"):
            candidate = self.valid_candidate("run_closed")
            validation = candidate["validation"]
            assert isinstance(validation, dict)
            validation["profile"] = bad_value
            self.assert_invalid_candidate(
                candidate, "run_closed.validation.profile must be exactly gates"
            )

    def test_fr019_inheritance_events_handoff_optionals_and_extensions(self) -> None:
        prior = self.task_record(id="task-inherit")
        terminal = {
            "type": "task",
            "recorded_at": RECORDED_AT,
            "id": "task-inherit",
            "status": "complete",
        }
        self.assert_valid_candidate(terminal, prior_records=(prior,))

        for status in ("active", "complete"):
            with self.subTest(inheritance="missing-prior", status=status):
                candidate = dict(terminal, status=status)
                self.assert_invalid_candidate(candidate, "task.goal is required")
        candidate = dict(terminal, id="task-other")
        self.assert_invalid_candidate(
            candidate, "task.goal is required", prior_records=(prior,)
        )
        older = self.task_record(id="task-inherit")
        newest_sparse = {
            "type": "task",
            "recorded_at": RECORDED_AT,
            "id": "task-inherit",
            "status": "complete",
        }
        self.assert_invalid_candidate(
            terminal,
            "task.goal is required",
            prior_records=(older, newest_sparse),
        )
        for field, bad_value, requirement in (
            ("goal", None, "must be a string"),
            ("goal", "", "must be nonempty"),
            ("acceptance", None, "must be an array"),
            ("acceptance", [], "must be nonempty"),
            ("files", None, "must be an array"),
            ("files", [], "must be nonempty"),
        ):
            candidate = dict(terminal)
            candidate[field] = bad_value
            self.assert_invalid_candidate(
                candidate,
                f"task.{field} {requirement}",
                prior_records=(prior,),
            )

        execution = self.valid_candidate("execution")
        execution.pop("events")
        self.assert_invalid_candidate(execution, "execution.events is required")
        execution = self.valid_candidate("execution")
        execution["events"] = ""
        self.assert_invalid_candidate(execution, "execution.events must be nonempty")
        execution = self.valid_candidate("execution")
        execution["events"] = None
        self.assert_invalid_candidate(execution, "execution.events must be a string")
        for events in (None, ""):
            execution = self.valid_candidate("execution")
            execution["event_source"] = "claude"
            if events is None:
                execution.pop("events")
            else:
                execution["events"] = events
            self.assert_valid_candidate(execution)

        for status in ("blocked", "failed"):
            result = self.valid_candidate("execution_result")
            result["status"] = status
            result.pop("handoff")
            self.assert_valid_candidate(result)
            result["handoff"] = ""
            self.assert_valid_candidate(result)
        result = self.valid_candidate("execution_result")
        result.pop("handoff")
        self.assert_invalid_candidate(result, "execution_result.handoff is required")
        result = self.valid_candidate("execution_result")
        result["handoff"] = None
        self.assert_invalid_candidate(
            result, "execution_result.handoff must be a string"
        )
        result = self.valid_candidate("execution_result")
        result["handoff"] = ""
        self.assert_invalid_candidate(
            result, "execution_result.handoff must be nonempty"
        )

        for field in ("task", "finding", "outcome", "risk"):
            decision = self.valid_candidate("decision")
            decision[field] = None
            self.assert_invalid_candidate(
                decision, f"decision.{field} must be a string"
            )
            decision[field] = ""
            self.assert_valid_candidate(decision)
        opening = self.valid_candidate("run_started")
        opening["successor_of"] = None
        self.assert_invalid_candidate(
            opening, "run_started.successor_of must be a valid run ID"
        )
        opening["successor_of"] = "run-predecessor"
        self.assert_valid_candidate(opening)

        for kind in (
            "run_started",
            "task",
            "execution",
            "execution_result",
            "verification",
            "decision",
            "run_closed",
        ):
            with self.subTest(kind=kind, extension="unknown"):
                candidate = self.valid_candidate(kind)
                candidate["future_extension"] = {"schema": 2}
                if kind == "run_closed":
                    validation = candidate["validation"]
                    assert isinstance(validation, dict)
                    validation["future_nested"] = True
                self.assert_valid_candidate(candidate)

    def test_first_failure_examples_and_envelope_literal_are_exact(self) -> None:
        opened = self.open_run("run-first", "src/**")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        self.create_citation_files("run-first")
        before = self.coordination_snapshot()

        candidates: tuple[tuple[object, str], ...] = (
            (
                self.task_record(goal=None, acceptance=[], files=[]),
                "forge: journal append refused — invalid journal record: "
                "task.goal must be a string\n",
            ),
            (
                self.execution_record(execution="secret-invalid-execution", worktree=""),
                "forge: journal append refused — invalid journal record: "
                "execution.execution must match execution-NN\n",
            ),
            (
                self.verification_record(result="secret-invalid-result"),
                "forge: journal append refused — invalid journal record: "
                "verification.result must be one of passed, failed, inconclusive, skipped\n",
            ),
            (
                {"recorded_at": RECORDED_AT},
                "forge: journal append refused — invalid journal record\n",
            ),
            ([], "forge: journal append refused — invalid journal record\n"),
        )
        for index, (candidate, expected) in enumerate(candidates):
            with self.subTest(case=index):
                refused = self.append_record("run-first", candidate)
                self.assertEqual(refused.returncode, 1)
                self.assertEqual(refused.stderr, expected)
                self.assertNotIn("secret-invalid", refused.stderr)
                self.assertEqual(self.coordination_snapshot(), before)

    def test_array_members_fail_at_the_first_ascending_index(self) -> None:
        opened = self.open_run("run-array-order", "src/**")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        candidate = self.task_record(
            acceptance=["first valid criterion", "", "secret-later-value"],
            files=["not-in-scope/**"],
        )
        before = self.coordination_snapshot()

        refused = self.append_record("run-array-order", candidate)

        self.assertEqual(refused.returncode, 1)
        self.assertEqual(
            refused.stderr,
            "forge: journal append refused — invalid journal record: "
            "task.acceptance[1] must be a nonempty string\n",
        )
        self.assertNotIn("secret-later-value", refused.stderr)
        self.assertNotIn("not-in-scope", refused.stderr)
        self.assertEqual(self.coordination_snapshot(), before)

    def test_reserved_lifecycle_decisions_require_commands_and_preserve_bytes(self) -> None:
        opened = self.open_run("run-lifecycle-append", "src/**")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        before = self.coordination_snapshot()
        candidates = (
            {
                "type": "decision",
                "recorded_at": RECORDED_AT,
                "id": "forge-run-retired",
                "resolution": journal.RETIREMENT_RESOLUTION,
            },
            {
                "type": "decision",
                "recorded_at": RECORDED_AT,
                "id": "forge-scope-readmission-0123456789abcdef0123456789abcdef",
                "resolution": journal.READMISSION_RESOLUTION,
                "scope": ["src/**"],
            },
        )

        for candidate in candidates:
            with self.subTest(decision_id=candidate["id"]):
                refused = self.append_record("run-lifecycle-append", candidate)
                self.assertEqual(refused.returncode, 1)
                self.assertEqual(refused.stdout, "")
                self.assertEqual(
                    refused.stderr,
                    "forge: journal append refused — lifecycle command required\n",
                )
                self.assertEqual(self.coordination_snapshot(), before)

    def test_sparse_history_reads_unchanged_but_same_new_shape_refuses(self) -> None:
        opened = self.open_run("run-legacy-sparse", "src/**")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        sparse = {
            "type": "task",
            "recorded_at": RECORDED_AT,
            "id": "legacy-task",
            "status": "complete",
        }
        journal_path = self.journal_path("run-legacy-sparse")
        with journal_path.open("ab") as stream:
            stream.write((json.dumps(sparse) + "\n").encode("utf-8"))
        before = self.coordination_snapshot()

        with mock.patch.object(
            journal,
            "_validate_proposed_record",
            side_effect=AssertionError("historical reader invoked append validator"),
        ):
            scanned = journal._scan_run(self.run_dir("run-legacy-sparse"))
            records, _issues = journal.read_journal(journal_path)
            payload = journal.validate_run(self.run_dir("run-legacy-sparse"))

        self.assertEqual(scanned.run_id, "run-legacy-sparse")
        parsed_sparse = dict(records[-1])
        self.assertEqual(parsed_sparse.pop("_line"), 2)
        self.assertEqual(parsed_sparse, sparse)
        self.assertIsInstance(payload, dict)
        self.assertEqual(self.coordination_snapshot(), before)

        refused = self.append_record("run-legacy-sparse", sparse)
        self.assertEqual(refused.returncode, 1)
        self.assertEqual(
            refused.stderr,
            "forge: journal append refused — invalid journal record: "
            "task.goal is required\n",
        )
        self.assertEqual(self.coordination_snapshot(), before)
