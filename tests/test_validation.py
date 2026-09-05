from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.codex_orchestrator import journal
from scripts.codex_orchestrator.journal import validate_run

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "codex_orch_tools.py"
# forge: modified from upstream — pin declared pre-cutover journal compatibility
PALIMPSEST_RUN = (
    ROOT.parent
    / "palimpsest"
    / ".codex-orchestrator"
    / "runs"
    / "authoring-system"
)
PALIMPSEST_REVIEWED_PREFIX_LINES = 826


def write_journal(run_dir: Path, records: list[dict[str, object]]) -> None:
    (run_dir / "journal.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
    )


class ValidationTests(unittest.TestCase):
    def make_run(self, root: Path) -> tuple[Path, list[dict[str, object]]]:
        run_dir = root / "run"
        execution_dir = run_dir / "codex-impl-01" / "execution-01"
        evidence_dir = run_dir / "evidence"
        execution_dir.mkdir(parents=True)
        evidence_dir.mkdir()
        (execution_dir / "prompt.md").write_text("Implement the task.\n", encoding="utf-8")
        (execution_dir / "events.jsonl").write_text(
            '{"type":"turn.completed"}\n', encoding="utf-8"
        )
        (execution_dir / "handoff.md").write_text("## Status\n\ncomplete\n", encoding="utf-8")
        (evidence_dir / "tests.txt").write_text("1 passed\n", encoding="utf-8")
        records: list[dict[str, object]] = [
            {"type": "run_started"},
            {"type": "task", "id": "task-01", "status": "complete"},
            {
                "type": "execution",
                "task": "task-01",
                "agent": "codex-impl-01",
                "execution": "execution-01",
                "prompt": "codex-impl-01/execution-01/prompt.md",
                "events": "codex-impl-01/execution-01/events.jsonl",
                "handoff": "codex-impl-01/execution-01/handoff.md",
            },
            {
                "type": "execution_result",
                "task": "task-01",
                "agent": "codex-impl-01",
                "execution": "execution-01",
                "status": "complete",
            },
            {
                "type": "verification",
                "id": "check-01",
                "task": "task-01",
                "result": "passed",
                "evidence": ["evidence/tests.txt"],
            },
        ]
        write_journal(run_dir, records)
        return run_dir, records

    # forge: modified from upstream — construct and disable each compatibility leg in isolation
    def legacy_declaration(
        self, justification: str = "operator-approved migration"
    ) -> dict[str, object]:
        return {
            "type": "decision",
            "id": "journal-dialect-compat",
            "resolution": f"legacy-dialect-compat: {justification}",
        }

    def make_legacy_run(
        self, root: Path, *, declaration: dict[str, object] | None = None
    ) -> tuple[Path, list[dict[str, object]]]:
        run_dir, _ = self.make_run(root)
        records: list[dict[str, object]] = [
            {"type": "run_started"},
            {"type": "task", "id": "task-01", "status": "complete"},
            {"type": "task", "id": "task-02", "status": "complete"},
            {"type": "observation", "detail": "legacy narrative"},
            {
                "type": "execution",
                "task": "task-01",
                "agent": "legacy-missing",
                "execution": "execution-01",
                "prompt": "(inline)",
                "events": "",
            },
            {
                "type": "execution",
                "task": "task-01",
                "agent": "codex-impl-01",
                "execution": "execution-01",
                "prompt": "codex-impl-01/execution-01/prompt.md",
                "events": "codex-impl-01/execution-01/events.jsonl",
                "handoff": "codex-impl-01/execution-01/handoff.md",
            },
            {
                "type": "execution_result",
                "task": "task-02",
                "agent": "codex-impl-01",
                "execution": "execution-01",
                "status": "handoff-ready",
            },
            {
                "type": "verification",
                "id": "legacy-failed-cleared",
                "criterion": "gate-1: exact legacy recheck",
                "result": "failed",
            },
            {
                "type": "verification",
                "id": "legacy-pass",
                "criterion": "gate-1: exact legacy recheck",
                "result": "pass",
                "evidence": "evidence/tests.txt",
            },
            {
                "type": "verification",
                "id": "legacy-failed-unrechecked",
                "criterion": "gate-2: unrechecked legacy failure",
                "result": "failed",
            },
            {"type": "verification", "id": "legacy-duplicate", "result": "passed"},
            {"type": "verification", "id": "legacy-duplicate", "result": "passed"},
        ]
        if declaration is not None:
            records.append(declaration)
        write_journal(run_dir, records)
        return run_dir, records

    def run_validation_cli(self, run_dir: Path) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "validate", "--gates", str(run_dir)],
            check=False,
            text=True,
            capture_output=True,
            cwd=ROOT,
        )
        return result, json.loads(result.stdout)

    def assert_legacy_leg_is_load_bearing(self, leg: str, expected_issue: str) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, _ = self.make_legacy_run(
                Path(tmp), declaration=self.legacy_declaration()
            )
            compatible = validate_run(run_dir, gates=True)
            enabled = journal.LEGACY_COMPATIBILITY_LEGS
            with mock.patch.object(
                journal, "LEGACY_COMPATIBILITY_LEGS", enabled - {leg}
            ):
                payload = validate_run(run_dir, gates=True)

        self.assertTrue(compatible["ok"], (leg, compatible["issues"]))
        self.assertFalse(payload["ok"])
        self.assertTrue(
            any(expected_issue in issue for issue in payload["issues"]),
            (leg, payload["issues"]),
        )

    def test_sparse_open_run_is_ready_to_close_and_cli_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, _ = self.make_run(Path(tmp))
            payload = validate_run(run_dir)
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "validate", str(run_dir)],
                check=False,
                text=True,
                capture_output=True,
                cwd=ROOT,
            )

        self.assertTrue(payload["ok"], payload["issues"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["ok"])

    def test_unreadable_records_and_unknown_types_are_issues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            missing = validate_run(run_dir)
            (run_dir / "journal.jsonl").write_text(
                '[]\nnot json\n{"type":"mystery"}\n', encoding="utf-8"
            )
            malformed = validate_run(run_dir)

        self.assertFalse(missing["ok"])
        self.assertTrue(any("missing journal" in issue for issue in missing["issues"]))
        self.assertFalse(malformed["ok"])
        self.assertTrue(any("must be an object" in issue for issue in malformed["issues"]))
        self.assertTrue(any("invalid JSON" in issue for issue in malformed["issues"]))
        self.assertTrue(any("unknown journal entry" in issue for issue in malformed["issues"]))

    def test_invalid_utf8_and_unresolvable_paths_are_reported_not_raised(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir, records = self.make_run(root)
            (run_dir / "journal.jsonl").write_bytes(b"\xff\xfe")
            unreadable = validate_run(run_dir)

            loop = root / "loop"
            loop.symlink_to(loop)
            records[2]["prompt"] = str(loop)
            write_journal(run_dir, records)
            unresolvable = validate_run(run_dir)

        self.assertFalse(unreadable["ok"])
        self.assertTrue(any("could not read journal" in issue for issue in unreadable["issues"]))
        self.assertFalse(unresolvable["ok"])
        self.assertTrue(any("prompt file" in issue for issue in unresolvable["issues"]))

    def test_nul_paths_are_reported_not_raised(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, records = self.make_run(Path(tmp))
            records[2]["events"] = "bad\0path"
            write_journal(run_dir, records)
            declared_path = validate_run(run_dir)
            run_path = validate_run(Path("bad\0path"))

        self.assertFalse(declared_path["ok"])
        self.assertTrue(any("events file" in issue for issue in declared_path["issues"]))
        self.assertFalse(run_path["ok"])
        self.assertTrue(any("invalid run directory" in issue for issue in run_path["issues"]))

    def test_start_and_close_markers_have_only_lifecycle_requirements(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, records = self.make_run(Path(tmp))
            close = {"type": "run_closed", "judgment": "passed"}

            write_journal(run_dir, [*records, close])
            self.assertTrue(validate_run(run_dir)["ok"])

            cases = {
                "missing start": records[1:],
                "start not first": [records[1], records[0], *records[2:]],
                "duplicate start": [records[0], records[0], *records[1:]],
                "duplicate close": [*records, close, close],
                "close not final": [*records, close, {"type": "decision"}],
                "invalid judgment": [*records, {"type": "run_closed", "judgment": "maybe"}],
            }
            for name, case_records in cases.items():
                with self.subTest(name=name):
                    write_journal(run_dir, case_records)
                    self.assertFalse(validate_run(run_dir)["ok"])

    def test_latest_task_status_must_be_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, records = self.make_run(Path(tmp))
            earlier_active = {"type": "task", "id": "task-01", "status": "active"}
            write_journal(run_dir, [records[0], earlier_active, *records[1:]])
            self.assertTrue(validate_run(run_dir)["ok"])

            for status in ("active", "pending", "unknown"):
                with self.subTest(status=status):
                    write_journal(
                        run_dir,
                        [*records, {"type": "task", "id": "task-01", "status": status}],
                    )
                    payload = validate_run(run_dir)
                    self.assertFalse(payload["ok"])
                    self.assertTrue(any("not terminal" in issue for issue in payload["issues"]))

    def test_execution_and_result_pairing_detects_omissions_and_mismatches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, records = self.make_run(Path(tmp))
            cases: dict[str, tuple[list[dict[str, object]], str]] = {}

            missing_result = copy.deepcopy(records)
            del missing_result[3]
            cases["missing result"] = missing_result, "no terminal execution_result"

            orphan_result = copy.deepcopy(records)
            del orphan_result[2]
            cases["orphan result"] = orphan_result, "unknown execution"

            duplicate_execution = copy.deepcopy(records)
            duplicate_execution.insert(3, copy.deepcopy(duplicate_execution[2]))
            cases["duplicate execution"] = duplicate_execution, "duplicate execution"

            duplicate_result = copy.deepcopy(records)
            duplicate_result.insert(4, copy.deepcopy(duplicate_result[3]))
            cases["duplicate result"] = duplicate_result, "duplicate execution_result"

            mismatched_task = copy.deepcopy(records)
            mismatched_task[3]["task"] = "task-02"
            cases["task mismatch"] = mismatched_task, "does not match"

            result_first = copy.deepcopy(records)
            result_first[2], result_first[3] = result_first[3], result_first[2]
            cases["result first"] = result_first, "must be recorded before"

            for name, (case_records, expected) in cases.items():
                with self.subTest(name=name):
                    write_journal(run_dir, case_records)
                    payload = validate_run(run_dir)
                    self.assertFalse(payload["ok"])
                    self.assertTrue(
                        any(expected in issue for issue in payload["issues"]), payload["issues"]
                    )

    def test_declared_files_and_handoff_severity_are_checked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir, records = self.make_run(root)
            execution_dir = run_dir / "codex-impl-01" / "execution-01"

            (execution_dir / "prompt.md").unlink()
            missing_prompt = validate_run(run_dir)
            self.assertFalse(missing_prompt["ok"])
            self.assertTrue(any("prompt file" in issue for issue in missing_prompt["issues"]))
            (execution_dir / "prompt.md").write_text("restored\n", encoding="utf-8")

            (run_dir / "evidence" / "tests.txt").unlink()
            missing_evidence = validate_run(run_dir)
            self.assertFalse(missing_evidence["ok"])
            self.assertTrue(
                any("evidence[0]" in issue for issue in missing_evidence["issues"])
            )
            (run_dir / "evidence" / "tests.txt").write_text("restored\n", encoding="utf-8")

            external_events = root / "external-events.jsonl"
            external_events.write_text('{"type":"turn.completed"}\n', encoding="utf-8")
            records[2]["events"] = str(external_events)
            write_journal(run_dir, records)
            self.assertTrue(validate_run(run_dir)["ok"])

            (execution_dir / "handoff.md").write_text("", encoding="utf-8")
            complete = validate_run(run_dir)
            self.assertFalse(complete["ok"])
            self.assertTrue(any("handoff is missing or empty" in x for x in complete["issues"]))

            records[3]["status"] = "failed"
            write_journal(run_dir, records)
            failed = validate_run(run_dir)
            self.assertTrue(failed["ok"], failed["issues"])
            self.assertTrue(any("handoff is missing or empty" in x for x in failed["warnings"]))

    def test_nonpassing_verifications_remain_visible_without_failing_structure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, records = self.make_run(Path(tmp))
            records[4]["result"] = "failed"
            records[4]["criterion"] = "focused tests"
            records.extend(
                [
                    {"type": "verification", "id": "check-02", "result": "inconclusive"},
                    {"type": "verification", "id": "check-03", "result": "skipped"},
                    {
                        "type": "verification",
                        "id": "check-04",
                        "criterion": "focused tests",
                        "result": "passed",
                    },
                ]
            )
            write_journal(run_dir, records)
            payload = validate_run(run_dir)

        self.assertTrue(payload["ok"], payload["issues"])
        self.assertEqual(
            [item["id"] for item in payload["non_passing_verifications"]],
            ["check-01", "check-02", "check-03"],
        )
        self.assertEqual(
            payload["non_passing_verifications"][0]["criterion"], "focused tests"
        )

    def test_core_status_values_are_still_checked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, records = self.make_run(Path(tmp))

            records[3].pop("status")
            write_journal(run_dir, records)
            missing_execution_status = validate_run(run_dir)

            records[3]["status"] = "complete"
            records[4].pop("result")
            write_journal(run_dir, records)
            missing_verification_result = validate_run(run_dir)

        self.assertFalse(missing_execution_status["ok"])
        self.assertTrue(
            any("status is not terminal" in issue for issue in missing_execution_status["issues"])
        )
        self.assertFalse(missing_verification_result["ok"])
        self.assertTrue(
            any(
                "verification result is not recognized" in issue
                for issue in missing_verification_result["issues"]
            )
        )

    def test_malformed_statuses_and_task_references_are_reported_not_raised(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, records = self.make_run(Path(tmp))
            records[1]["status"] = ["complete"]
            for record in records[2:5]:
                record["task"] = ["task-01"]
            records[3]["status"] = ["complete"]
            records[4]["result"] = ["passed"]
            records.append({"type": "run_closed", "judgment": ["passed"]})
            write_journal(run_dir, records)

            payload = validate_run(run_dir)

        self.assertFalse(payload["ok"])
        expected_fragments = (
            "run_closed judgment must be passed or blocked",
            "execution_result status is not terminal",
            "verification result is not recognized",
            "task task-01 is not terminal",
            "task reference must be a string",
        )
        for fragment in expected_fragments:
            self.assertTrue(
                any(fragment in issue for issue in payload["issues"]),
                (fragment, payload["issues"]),
            )
    def test_task_references_must_name_recorded_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, records = self.make_run(Path(tmp))
            records[2]["task"] = "task-missing"
            records[3]["task"] = "task-missing"
            records[4]["task"] = "task-missing"
            records.append(
                {"type": "decision", "id": "decision-01", "task": "task-missing"}
            )
            write_journal(run_dir, records)
            payload = validate_run(run_dir)

        self.assertFalse(payload["ok"])
        for kind in ("execution", "execution_result", "verification", "decision"):
            self.assertTrue(
                any(
                    f"{kind} references unknown task task-missing" in issue
                    for issue in payload["issues"]
                ),
                (kind, payload["issues"]),
            )

    def test_verification_and_decision_ids_must_be_unique(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, records = self.make_run(Path(tmp))
            records.extend(
                [
                    {"type": "verification", "id": "check-01", "result": "passed"},
                    {"type": "decision", "id": "decision-01"},
                    {"type": "decision", "id": "decision-01"},
                ]
            )
            write_journal(run_dir, records)
            payload = validate_run(run_dir)

        self.assertFalse(payload["ok"])
        self.assertTrue(any("duplicate verification id check-01" in x for x in payload["issues"]))
        self.assertTrue(any("duplicate decision id decision-01" in x for x in payload["issues"]))

    def test_evidence_errors_identify_the_list_item(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, records = self.make_run(Path(tmp))
            records[4]["evidence"] = ["evidence/missing.txt", 42]
            write_journal(run_dir, records)
            payload = validate_run(run_dir)

        self.assertFalse(payload["ok"])
        self.assertTrue(any("evidence[0]" in issue for issue in payload["issues"]))
        self.assertTrue(any("evidence[1]" in issue for issue in payload["issues"]))

    # forge: modified from upstream — enforce all ten warned compatibility contracts
    def test_legacy_compatibility_normalizes_all_ten_legs_and_preserves_strict_parity(
        self,
    ) -> None:
        expected_strict_issues = [
            "line 4: unknown journal entry type: 'observation'",
            "line 5: referenced prompt file does not exist: (inline)",
            "line 5: events must name a file",
            "line 7: execution_result status is not terminal: handoff-ready",
            "line 9: verification result is not recognized: pass",
            "line 9: evidence must be a list of file paths",
            "line 12: duplicate verification id legacy-duplicate",
            "execution legacy-missing/execution-01 has no terminal execution_result",
            "line 7: execution_result task 'task-02' does not match execution task 'task-01'",
            "failed gate verification 'legacy-failed-cleared' has no subsequent passing recheck",
            "failed gate verification 'legacy-failed-unrechecked' has no subsequent passing recheck",
        ]
        warning_fragments = (
            "legacy compatibility declaration active",
            "observation entry",
            "verification result 'pass'",
            "string evidence",
            "execution_result status 'handoff-ready'",
            "execution_result task 'task-02'",
            "missing prompt file",
            "duplicate verification id legacy-duplicate",
            "no terminal execution_result",
            "empty events reference",
            "failed gate verification 'legacy-failed-unrechecked'",
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            strict_run, _ = self.make_legacy_run(root / "strict")
            strict_payload = validate_run(strict_run, gates=True)
            compat_run, _ = self.make_legacy_run(
                root / "compat", declaration=self.legacy_declaration()
            )
            gated_payload = validate_run(compat_run, gates=True)
            plain_payload = validate_run(compat_run)

        self.assertEqual(strict_payload["issues"], expected_strict_issues)
        self.assertEqual(strict_payload["warnings"], [])
        self.assertFalse(strict_payload["ok"])
        self.assertEqual(strict_payload["profile"], "gates")
        self.assertEqual(
            [item["id"] for item in strict_payload["non_passing_verifications"]],
            ["legacy-failed-cleared", "legacy-failed-unrechecked"],
        )
        self.assertTrue(gated_payload["ok"], gated_payload["issues"])
        self.assertEqual(gated_payload["issues"], [])
        self.assertEqual(len(gated_payload["warnings"]), len(warning_fragments))
        self.assertEqual(
            gated_payload["warnings"][0],
            "line 13: legacy compatibility declaration active: "
            "operator-approved migration",
        )
        self.assertTrue(all(warning.startswith("line ") for warning in gated_payload["warnings"]))
        for fragment in warning_fragments:
            self.assertTrue(
                any(fragment in warning for warning in gated_payload["warnings"]),
                (fragment, gated_payload["warnings"]),
            )
        self.assertEqual(
            [item["id"] for item in gated_payload["non_passing_verifications"]],
            ["legacy-failed-cleared", "legacy-failed-unrechecked"],
        )
        self.assertTrue(plain_payload["ok"], plain_payload["issues"])
        self.assertNotIn("profile", plain_payload)
        self.assertEqual(len(plain_payload["warnings"]), len(warning_fragments) - 1)

    def test_legacy_compatibility_supports_historical_pass_shapes_and_status_mappings(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pass_run, pass_records = self.make_run(root / "pass-shape")
            pass_records[4].pop("result")
            pass_records[4]["status"] = "pass"
            pass_records.append(self.legacy_declaration())
            write_journal(pass_run, pass_records)
            status_pass_payload = validate_run(pass_run)

            pass_records[4]["result"] = "malformed"
            write_journal(pass_run, pass_records)
            malformed_result_payload = validate_run(pass_run)

            mapping_run, mapping_records = self.make_run(root / "status-mappings")
            mapping_records = copy.deepcopy(mapping_records)
            for index, status in enumerate(("handoff-ready", "pass", "block"), start=1):
                agent = f"legacy-status-{index}"
                execution = {
                    **copy.deepcopy(mapping_records[2]),
                    "agent": agent,
                    "execution": f"execution-{index:02d}",
                }
                result = {
                    "type": "execution_result",
                    "task": "task-01",
                    "agent": agent,
                    "execution": f"execution-{index:02d}",
                    "status": status,
                }
                mapping_records.extend((execution, result))
            mapping_records.append(self.legacy_declaration())
            write_journal(mapping_run, mapping_records)
            mapping_payload = validate_run(mapping_run)

        self.assertTrue(status_pass_payload["ok"], status_pass_payload["issues"])
        self.assertTrue(
            any("status 'pass' with no result" in warning for warning in status_pass_payload["warnings"])
        )
        self.assertFalse(malformed_result_payload["ok"])
        self.assertTrue(
            any("verification result is not recognized" in issue for issue in malformed_result_payload["issues"])
        )
        self.assertTrue(mapping_payload["ok"], mapping_payload["issues"])
        for source, target in (
            ("handoff-ready", "complete"),
            ("pass", "complete"),
            ("block", "blocked"),
        ):
            self.assertTrue(
                any(
                    f"status '{source}'" in warning and f"status '{target}'" in warning
                    for warning in mapping_payload["warnings"]
                ),
                (source, target, mapping_payload["warnings"]),
            )

    def test_legacy_compatibility_cutover_keeps_every_leg_strict(self) -> None:
        valid_paths = {
            "prompt": "codex-impl-01/execution-01/prompt.md",
            "events": "codex-impl-01/execution-01/events.jsonl",
            "handoff": "codex-impl-01/execution-01/handoff.md",
        }

        def execution(agent: str, **overrides: object) -> dict[str, object]:
            record: dict[str, object] = {
                "type": "execution",
                "task": "task-01",
                "agent": agent,
                "execution": "execution-01",
                **valid_paths,
            }
            record.update(overrides)
            return record

        def result(agent: str, **overrides: object) -> dict[str, object]:
            record: dict[str, object] = {
                "type": "execution_result",
                "task": "task-01",
                "agent": agent,
                "execution": "execution-01",
                "status": "complete",
            }
            record.update(overrides)
            return record

        cases: dict[
            str,
            tuple[list[dict[str, object]], list[dict[str, object]], str, str],
        ] = {
            "observation": (
                [],
                [{"type": "observation"}],
                "unknown journal entry type",
                "observation entry",
            ),
            "verification pass": (
                [],
                [{"type": "verification", "id": "cutover-pass", "result": "pass"}],
                "verification result is not recognized",
                "verification result 'pass'",
            ),
            "string evidence": (
                [],
                [
                    {
                        "type": "verification",
                        "id": "cutover-evidence",
                        "result": "passed",
                        "evidence": "evidence/tests.txt",
                    }
                ],
                "evidence must be a list",
                "string evidence",
            ),
            "execution status": (
                [execution("cutover-status")],
                [result("cutover-status", status="pass")],
                "status is not terminal",
                "execution_result status 'pass'",
            ),
            "task mismatch": (
                [
                    {"type": "task", "id": "task-02", "status": "complete"},
                    execution("cutover-mismatch"),
                ],
                [result("cutover-mismatch", task="task-02")],
                "does not match execution task",
                "execution_result task 'task-02'",
            ),
            "missing execution file": (
                [],
                [
                    execution("cutover-file", prompt="(inline)"),
                    result("cutover-file"),
                ],
                "referenced prompt file does not exist",
                "missing prompt file",
            ),
            "missing events file": (
                [],
                [
                    execution("cutover-events-file", events="missing-events.jsonl"),
                    result("cutover-events-file"),
                ],
                "referenced events file does not exist",
                "missing events file",
            ),
            "duplicate verification": (
                [],
                [{"type": "verification", "id": "check-01", "result": "passed"}],
                "duplicate verification id check-01",
                "duplicate verification id check-01",
            ),
            "missing execution result": (
                [],
                [execution("cutover-missing-result")],
                "no terminal execution_result",
                "no terminal execution_result",
            ),
            "empty events": (
                [],
                [
                    execution("cutover-events", events=""),
                    result("cutover-events", status="failed"),
                ],
                "events must name a file",
                "empty events reference",
            ),
            "failed gate recheck": (
                [],
                [
                    {
                        "type": "verification",
                        "id": "cutover-failed-gate",
                        "criterion": "gate-1: post-declaration failure",
                        "result": "failed",
                    }
                ],
                "failed gate verification 'cutover-failed-gate'",
                "failed gate verification 'cutover-failed-gate'",
            ),
        }

        for name, (
            pre_declaration,
            post_declaration,
            expected_issue,
            forbidden_warning,
        ) in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                run_dir, records = self.make_run(Path(tmp))
                write_journal(
                    run_dir,
                    [
                        *records,
                        *copy.deepcopy(pre_declaration),
                        self.legacy_declaration(),
                        *copy.deepcopy(post_declaration),
                    ],
                )
                payload = validate_run(run_dir, gates=True)

                self.assertFalse(payload["ok"])
                self.assertTrue(
                    any(expected_issue in issue for issue in payload["issues"]),
                    (name, payload["issues"]),
                )
                self.assertEqual(
                    sum(
                        "legacy compatibility declaration active" in warning
                        for warning in payload["warnings"]
                    ),
                    1,
                )
                self.assertEqual(len(payload["warnings"]), 1)
                self.assertFalse(
                    any(forbidden_warning in warning for warning in payload["warnings"]),
                    (name, payload["warnings"]),
                )

    def gate_passing_verifications(self) -> list[dict[str, object]]:
        return [
            {
                "type": "verification",
                "id": "gate1-pass",
                "criterion": "gate-1: full suite",
                "result": "passed",
            },
            {
                "type": "verification",
                "id": "gate2-pass",
                "criterion": "gate-2: stack validations",
                "result": "passed",
            },
            {
                "type": "verification",
                "id": "gate3-pass",
                "criterion": journal.GATE_3_CRITERION,
                "result": "passed",
            },
        ]

    def assert_all_gates_vetoed(self, payload: dict[str, object]) -> None:
        self.assertFalse(payload["ok"])
        for gate_name in ("gate-1", "gate-2", journal.GATE_3_CRITERION):
            self.assertIn(
                "run closed as passed without a passing "
                f"'{gate_name}' verification after the last mutating execution",
                payload["issues"],
            )

    def test_legacy_unterminated_mutations_do_not_veto_gates_after_declaration(
        self,
    ) -> None:
        # The palimpsest authoring-system close shape: pre-declaration mutating
        # executions either never received a terminal execution_result or were
        # terminated by a legacy status, while the passing gate verifications
        # sit after the last real terminal result. The missing-execution-result
        # and execution-result-status legs already tolerate both records in the
        # baseline checks, so the gate profile's unterminated-mutation veto and
        # its last-result line must honor the same tolerance.
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, _ = self.make_run(Path(tmp))
            handoff = run_dir / "codex-impl-44" / "execution-01" / "handoff.md"
            handoff.parent.mkdir(parents=True)
            handoff.write_text("delivered\n", encoding="utf-8")
            write_journal(
                run_dir,
                [
                    {"type": "run_started"},
                    {"type": "task", "id": "task-01", "status": "complete"},
                    {
                        "type": "execution",
                        "task": "task-01",
                        "agent": "codex-impl-09",
                        "execution": "execution-01",
                        "prompt": "(inline)",
                        "events": "",
                    },
                    {
                        "type": "execution",
                        "task": "task-01",
                        "agent": "codex-impl-44",
                        "execution": "execution-01",
                        "prompt": "(inline)",
                        "events": "",
                    },
                    {
                        "type": "execution_result",
                        "task": "task-01",
                        "agent": "codex-impl-44",
                        "execution": "execution-01",
                        "status": "handoff-ready",
                        "handoff": "codex-impl-44/execution-01/handoff.md",
                    },
                    *self.gate_passing_verifications(),
                    self.legacy_declaration(),
                    {"type": "run_closed", "judgment": "passed"},
                ],
            )
            result, payload = self.run_validation_cli(run_dir)
            self.assertEqual(result.returncode, 0, payload["issues"])
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["issues"], [])

    def test_legacy_status_mapped_result_still_anchors_gate_ordering(self) -> None:
        # A pre-declaration execution_result with a legacy terminal status must
        # count as the last mutating result for gate ordering: gates recorded
        # BEFORE it cannot satisfy the close requirement, or the tolerance
        # would quietly weaken the gates-after-mutation rule.
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, _ = self.make_run(Path(tmp))
            write_journal(
                run_dir,
                [
                    {"type": "run_started"},
                    {"type": "task", "id": "task-01", "status": "complete"},
                    {
                        "type": "execution",
                        "task": "task-01",
                        "agent": "codex-impl-44",
                        "execution": "execution-01",
                        "prompt": "(inline)",
                        "events": "",
                    },
                    *self.gate_passing_verifications(),
                    {
                        "type": "execution_result",
                        "task": "task-01",
                        "agent": "codex-impl-44",
                        "execution": "execution-01",
                        "status": "handoff-ready",
                    },
                    self.legacy_declaration(),
                    {"type": "run_closed", "judgment": "passed"},
                ],
            )
            _, payload = self.run_validation_cli(run_dir)
            self.assert_all_gates_vetoed(payload)

    def test_tolerated_duplicate_result_after_valid_gates_keeps_first_authority(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, baseline = self.make_run(Path(tmp))
            first_result = copy.deepcopy(baseline[3])
            duplicate_result = copy.deepcopy(first_result)
            write_journal(
                run_dir,
                [
                    *copy.deepcopy(baseline[:3]),
                    first_result,
                    *self.gate_passing_verifications(),
                    duplicate_result,
                    self.legacy_declaration(),
                    {"type": "run_closed", "judgment": "passed"},
                ],
            )

            compatible = validate_run(run_dir, gates=True)
            with mock.patch.object(
                journal,
                "LEGACY_COMPATIBILITY_LEGS",
                journal.LEGACY_COMPATIBILITY_LEGS
                - {"duplicate-execution-result"},
            ):
                strict = validate_run(run_dir, gates=True)

        self.assertTrue(compatible["ok"], compatible)
        self.assertEqual(compatible["issues"], [])
        self.assertTrue(
            any(
                "first occurrence at line 4 remains authoritative" in warning
                for warning in compatible["warnings"]
            ),
            compatible["warnings"],
        )
        self.assertFalse(strict["ok"])
        self.assertEqual(
            strict["issues"],
            [
                "line 8: duplicate execution_result for "
                "codex-impl-01/execution-01"
            ],
        )

    def test_post_declaration_unterminated_mutation_still_vetoes_gates(self) -> None:
        # Cutover: an unterminated mutating execution recorded at or after the
        # declaration gets no tolerance, so it keeps vetoing every gate.
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, _ = self.make_run(Path(tmp))
            write_journal(
                run_dir,
                [
                    {"type": "run_started"},
                    {"type": "task", "id": "task-01", "status": "complete"},
                    self.legacy_declaration(),
                    {
                        "type": "execution",
                        "task": "task-01",
                        "agent": "codex-impl-50",
                        "execution": "execution-01",
                        "prompt": "(inline)",
                        "events": "",
                    },
                    *self.gate_passing_verifications(),
                    {"type": "run_closed", "judgment": "passed"},
                ],
            )
            _, payload = self.run_validation_cli(run_dir)
            self.assert_all_gates_vetoed(payload)

    def test_legacy_compatibility_keeps_structural_floors_hard(self) -> None:
        close = {"type": "run_closed", "judgment": "passed"}
        cases = {
            "multiple close": ([close, close], "at most one run_closed"),
            "close not last": (
                [close, {"type": "decision", "id": "after-close"}],
                "run_closed must be the final journal entry",
            ),
            "malformed citation correction": (
                [
                    {
                        "type": "decision",
                        "id": "bad-citation",
                        "resolution": "citation-correction: malformed",
                    }
                ],
                "invalid citation correction",
            ),
            "bad judgment": (
                [{"type": "run_closed", "judgment": "maybe"}],
                "run_closed judgment must be passed or blocked",
            ),
        }

        for name, (trailing, expected_issue) in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                run_dir, records = self.make_run(Path(tmp))
                write_journal(run_dir, [*records, self.legacy_declaration(), *trailing])
                payload = validate_run(run_dir)

                self.assertFalse(payload["ok"])
                self.assertTrue(
                    any(expected_issue in issue for issue in payload["issues"]),
                    (name, payload["issues"]),
                )
                self.assertEqual(
                    sum(
                        "legacy compatibility declaration active" in warning
                        for warning in payload["warnings"]
                    ),
                    1,
                )

    def test_legacy_compatibility_requires_the_exact_declaration_grammar(self) -> None:
        candidates = {
            "wrong id": {
                "type": "decision",
                "id": "journal-dialect-compat-wrong",
                "resolution": "legacy-dialect-compat: approved",
            },
            "wrong resolution prefix": {
                "type": "decision",
                "id": "journal-dialect-compat",
                "resolution": "legacy-compat: approved",
            },
            "empty justification": self.legacy_declaration(""),
            "whitespace justification": self.legacy_declaration("   "),
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            strict_run, _ = self.make_legacy_run(root / "strict")
            strict_payload = validate_run(strict_run, gates=True)
            for name, candidate in candidates.items():
                with self.subTest(name=name):
                    run_dir, _ = self.make_legacy_run(
                        root / name.replace(" ", "-"), declaration=candidate
                    )
                    payload = validate_run(run_dir, gates=True)
                    self.assertEqual(payload["issues"], strict_payload["issues"])
                    self.assertFalse(
                        any("legacy compatibility" in warning for warning in payload["warnings"])
                    )

    def test_legacy_compatibility_does_not_admit_unlisted_shapes(self) -> None:
        cases = {
            "empty string evidence": (4, "evidence", "", "evidence must be a list"),
            "wrong events type": (2, "events", 42, "events must name a file"),
            "empty prompt": (2, "prompt", "", "prompt must name a file"),
            "unknown execution status": (3, "status", "ready", "status is not terminal"),
        }
        for name, (record_index, field, value, expected_issue) in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                run_dir, records = self.make_run(Path(tmp))
                records[record_index][field] = value
                records.append(self.legacy_declaration())
                write_journal(run_dir, records)
                payload = validate_run(run_dir)
                self.assertFalse(payload["ok"])
                self.assertTrue(
                    any(expected_issue in issue for issue in payload["issues"]),
                    (name, payload["issues"]),
                )
                self.assertEqual(
                    sum(
                        "legacy compatibility declaration active" in warning
                        for warning in payload["warnings"]
                    ),
                    1,
                )
                self.assertEqual(len(payload["warnings"]), 1)

        with tempfile.TemporaryDirectory() as tmp:
            run_dir, records = self.make_run(Path(tmp))
            records[4]["evidence"] = "evidence/missing.txt"
            records.append(self.legacy_declaration())
            write_journal(run_dir, records)
            missing_evidence = validate_run(run_dir)
        # Revision 9 (FR-016 leg e): a pre-declaration record naming a missing
        # evidence file is tolerated as a warning under an active declaration,
        # including the normalized singleton-string form.
        self.assertTrue(missing_evidence["ok"], missing_evidence["issues"])
        self.assertEqual(
            sum(
                "legacy compatibility declaration active" in warning
                for warning in missing_evidence["warnings"]
            ),
            1,
        )
        self.assertEqual(
            sum(
                "tolerated missing evidence[0] file: evidence/missing.txt" in warning
                for warning in missing_evidence["warnings"]
            ),
            1,
        )
        self.assertFalse(
            any(
                "referenced evidence[0] file does not exist" in issue
                for issue in missing_evidence["issues"]
            )
        )

    def test_legacy_task_mismatch_never_conceals_an_unknown_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, records = self.make_run(Path(tmp))
            records[3]["task"] = "task-missing"
            records.append(self.legacy_declaration())
            write_journal(run_dir, records)
            payload = validate_run(run_dir)

        self.assertFalse(payload["ok"])
        self.assertTrue(
            any(
                "execution_result references unknown task task-missing" in issue
                for issue in payload["issues"]
            )
        )
        self.assertTrue(
            any("does not match execution task" in issue for issue in payload["issues"])
        )
        self.assertFalse(
            any(
                "interpreted execution_result task" in warning
                for warning in payload["warnings"]
            )
        )

    def test_legacy_declaration_does_not_weaken_raw_lifecycle_or_task_terminality(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lifecycle_run, lifecycle_records = self.make_run(root / "lifecycle")
            write_journal(
                lifecycle_run,
                [
                    {"type": "observation", "detail": "before start"},
                    *lifecycle_records,
                    self.legacy_declaration(),
                ],
            )
            lifecycle_payload = validate_run(lifecycle_run)

            task_run, task_records = self.make_run(root / "task")
            task_records[1]["status"] = "active"
            task_records.append(self.legacy_declaration())
            write_journal(task_run, task_records)
            task_payload = validate_run(task_run)

        self.assertFalse(lifecycle_payload["ok"])
        self.assertIn(
            "run_started must be the first journal entry", lifecycle_payload["issues"]
        )
        self.assertTrue(
            any(
                "observation entry" in warning
                for warning in lifecycle_payload["warnings"]
            )
        )
        self.assertFalse(task_payload["ok"])
        self.assertIn(
            "task task-01 is not terminal; latest status is 'active'",
            task_payload["issues"],
        )

    def test_legacy_observation_leg_is_load_bearing(self) -> None:
        self.assert_legacy_leg_is_load_bearing("observation", "unknown journal entry type")

    def test_legacy_verification_pass_leg_is_load_bearing(self) -> None:
        self.assert_legacy_leg_is_load_bearing(
            "verification-pass", "verification result is not recognized"
        )

    def test_legacy_string_evidence_leg_is_load_bearing(self) -> None:
        self.assert_legacy_leg_is_load_bearing("string-evidence", "evidence must be a list")

    def test_legacy_execution_result_status_leg_is_load_bearing(self) -> None:
        self.assert_legacy_leg_is_load_bearing(
            "execution-result-status", "status is not terminal"
        )

    def test_legacy_execution_task_mismatch_leg_is_load_bearing(self) -> None:
        self.assert_legacy_leg_is_load_bearing(
            "execution-task-mismatch", "does not match execution task"
        )

    def test_legacy_missing_execution_file_leg_is_load_bearing(self) -> None:
        self.assert_legacy_leg_is_load_bearing(
            "missing-execution-file", "referenced prompt file does not exist"
        )

    def test_legacy_missing_execution_file_leg_also_covers_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, records = self.make_run(Path(tmp))
            records[2]["events"] = "missing-events.jsonl"
            records.append(self.legacy_declaration())
            write_journal(run_dir, records)
            compatible = validate_run(run_dir)
            enabled = journal.LEGACY_COMPATIBILITY_LEGS
            with mock.patch.object(
                journal,
                "LEGACY_COMPATIBILITY_LEGS",
                enabled - {"missing-execution-file"},
            ):
                disabled = validate_run(run_dir)

        self.assertTrue(compatible["ok"], compatible["issues"])
        self.assertTrue(
            any("missing events file" in warning for warning in compatible["warnings"])
        )
        self.assertFalse(disabled["ok"])
        self.assertTrue(
            any(
                "referenced events file does not exist" in issue
                for issue in disabled["issues"]
            )
        )

    def test_legacy_missing_execution_file_leg_keeps_existing_non_files_hard(
        self,
    ) -> None:
        for field in ("prompt", "events"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                run_dir, records = self.make_run(Path(tmp))
                existing_directory = run_dir / f"existing-{field}-directory"
                existing_directory.mkdir()
                records[2][field] = existing_directory.name
                records.append(self.legacy_declaration())
                write_journal(run_dir, records)
                payload = validate_run(run_dir)

                self.assertFalse(payload["ok"])
                self.assertTrue(
                    any(
                        f"referenced {field} file does not exist" in issue
                        for issue in payload["issues"]
                    )
                )
                self.assertFalse(
                    any(
                        f"missing {field} file" in warning
                        for warning in payload["warnings"]
                    )
                )

    def test_legacy_duplicate_verification_id_leg_is_load_bearing(self) -> None:
        self.assert_legacy_leg_is_load_bearing(
            "duplicate-verification-id", "duplicate verification id"
        )

    def test_legacy_missing_execution_result_leg_is_load_bearing(self) -> None:
        self.assert_legacy_leg_is_load_bearing(
            "missing-execution-result", "no terminal execution_result"
        )

    def test_legacy_empty_events_leg_is_load_bearing(self) -> None:
        self.assert_legacy_leg_is_load_bearing("empty-events", "events must name a file")

    def test_legacy_failed_gate_recheck_leg_is_load_bearing(self) -> None:
        self.assert_legacy_leg_is_load_bearing(
            "failed-gate-recheck", "failed gate verification 'legacy-failed-unrechecked'"
        )

    @unittest.skipUnless(
        (PALIMPSEST_RUN / "journal.jsonl").is_file(),
        "real palimpsest authoring-system journal is unavailable",
    )
    def test_real_palimpsest_reviewed_prefix_accounts_for_all_legacy_issues(self) -> None:
        expected_issue_counts = {
            "observation": 59,
            "verification-pass": 20,
            "string-evidence": 17,
            "execution-result-status": 10,
            "execution-task-mismatch": 31,
            "missing-execution-file": 8,
            "duplicate-verification-id": 3,
            "missing-execution-result": 5,
            "empty-events": 2,
            "failed-gate-recheck": 9,
        }
        expected_warning_counts = {
            **expected_issue_counts,
            "failed-gate-recheck": 7,
        }
        issue_fragments = {
            "observation": ("unknown journal entry type: 'observation'",),
            "verification-pass": ("verification result is not recognized",),
            "string-evidence": ("evidence must be a list",),
            "execution-result-status": ("status is not terminal",),
            "execution-task-mismatch": ("does not match execution task",),
            "missing-execution-file": (
                "referenced prompt file does not exist",
                "referenced events file does not exist",
            ),
            "duplicate-verification-id": ("duplicate verification id",),
            "missing-execution-result": ("has no terminal execution_result",),
            "empty-events": ("events must name a file",),
            "failed-gate-recheck": ("failed gate verification",),
        }
        warning_fragments = {
            "observation": ("observation entry",),
            "verification-pass": ("verification result",),
            "string-evidence": ("string evidence",),
            "execution-result-status": ("execution_result status",),
            "execution-task-mismatch": ("execution_result task",),
            "missing-execution-file": ("missing prompt file", "missing events file"),
            "duplicate-verification-id": ("duplicate verification id",),
            "missing-execution-result": ("no terminal execution_result",),
            "empty-events": ("empty events reference",),
            "failed-gate-recheck": ("failed gate verification",),
        }

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = (
                Path(tmp)
                / "repo"
                / ".codex-orchestrator"
                / "runs"
                / "authoring-system"
            )
            run_dir.mkdir(parents=True)
            for source in PALIMPSEST_RUN.iterdir():
                if source.name == "journal.jsonl":
                    continue
                (run_dir / source.name).symlink_to(
                    source, target_is_directory=source.is_dir()
                )
            copied_journal = run_dir / "journal.jsonl"
            shutil.copy2(PALIMPSEST_RUN / "journal.jsonl", copied_journal)
            reviewed_lines = copied_journal.read_bytes().splitlines(keepends=True)
            self.assertGreaterEqual(len(reviewed_lines), PALIMPSEST_REVIEWED_PREFIX_LINES)
            reviewed_tail = json.loads(
                reviewed_lines[PALIMPSEST_REVIEWED_PREFIX_LINES - 1]
            )
            self.assertEqual(reviewed_tail.get("type"), "decision")
            self.assertEqual(reviewed_tail.get("id"), "decision-41")
            copied_journal.write_bytes(
                b"".join(reviewed_lines[:PALIMPSEST_REVIEWED_PREFIX_LINES])
            )

            strict_result, strict_payload = self.run_validation_cli(run_dir)
            with copied_journal.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(self.legacy_declaration()) + "\n")
            compat_result, compat_payload = self.run_validation_cli(run_dir)

        self.assertEqual(strict_result.returncode, 1, strict_result.stderr)
        self.assertFalse(strict_payload["ok"])
        self.assertEqual(len(strict_payload["issues"]), 164)
        actual_issue_counts = {
            leg: sum(
                any(fragment in issue for fragment in fragments)
                for issue in strict_payload["issues"]
            )
            for leg, fragments in issue_fragments.items()
        }
        self.assertEqual(actual_issue_counts, expected_issue_counts)
        self.assertEqual(sum(actual_issue_counts.values()), len(strict_payload["issues"]))
        self.assertEqual(
            strict_payload["warnings"],
            [
                "execution claude-review-final-04/execution-17 handoff is missing or empty"
            ],
        )

        self.assertEqual(compat_result.returncode, 0, compat_result.stderr)
        self.assertTrue(compat_payload["ok"], compat_payload["issues"])
        self.assertEqual(compat_payload["issues"], [])
        self.assertEqual(compat_payload["profile"], "gates")
        actual_warning_counts = {
            leg: sum(
                any(fragment in warning for fragment in fragments)
                for warning in compat_payload["warnings"]
            )
            for leg, fragments in warning_fragments.items()
        }
        self.assertEqual(actual_warning_counts, expected_warning_counts)
        self.assertEqual(
            len(compat_payload["warnings"]),
            len(strict_payload["warnings"]) + 1 + sum(expected_warning_counts.values()),
        )
        for warning in strict_payload["warnings"]:
            self.assertIn(warning, compat_payload["warnings"])
        self.assertEqual(
            compat_payload["non_passing_verifications"],
            strict_payload["non_passing_verifications"],
        )
        self.assertEqual(
            sum(
                "legacy compatibility declaration active" in warning
                for warning in compat_payload["warnings"]
            ),
            1,
        )

    def test_sparse_decisions_and_optional_metadata_are_not_schema_checked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, records = self.make_run(Path(tmp))
            records.extend(
                [
                    {
                        "type": "decision",
                        "basis": ["missing-id", "missing-file"],
                        "extra": {"future": True},
                    },
                    {"type": "run_closed", "judgment": "blocked"},
                ]
            )
            write_journal(run_dir, records)
            payload = validate_run(run_dir)

        self.assertTrue(payload["ok"], payload["issues"])


class ClosedLegacyCompatTests(unittest.TestCase):
    """FR-018(a): operator-directed closed-run keying of the FR-016 posture."""

    # Borrow the fixture builders without inheriting (and re-running) the base suite.
    make_run = ValidationTests.make_run
    make_legacy_run = ValidationTests.make_legacy_run

    RUN_CLOSED = {
        "type": "run_closed",
        "judgment": "blocked",
        "summary": "legacy close",
        "risks": [],
        "follow_ups": [],
    }

    def make_closed_legacy_run(self, root: Path) -> Path:
        run_dir, records = self.make_legacy_run(root)
        write_journal(run_dir, [*records, dict(self.RUN_CLOSED)])
        return run_dir

    def test_flag_validates_closed_legacy_journal_with_activation_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self.make_closed_legacy_run(Path(tmp))
            strict = validate_run(run_dir, gates=True)
            flagged = validate_run(
                run_dir, gates=True, closed_legacy_compat="operator-directed archive"
            )
        self.assertFalse(strict["ok"])
        self.assertTrue(flagged["ok"], flagged["issues"])
        self.assertIn(
            "legacy compatibility closed-run flag active: operator-directed archive",
            " ".join(flagged["warnings"]),
        )

    def test_without_flag_validation_is_byte_identical_to_strict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self.make_closed_legacy_run(Path(tmp))
            strict = json.dumps(validate_run(run_dir, gates=True), sort_keys=True)
            default = json.dumps(
                validate_run(run_dir, gates=True, closed_legacy_compat=None),
                sort_keys=True,
            )
        self.assertEqual(strict, default)

    def test_flag_refuses_open_journal_with_exact_literal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, _ = self.make_legacy_run(Path(tmp))
            with self.assertRaises(journal.CoordinationRefusal) as caught:
                validate_run(run_dir, gates=True, closed_legacy_compat="x")
        self.assertEqual(
            "forge: closed-legacy-compat refused — journal has no run_closed entry",
            str(caught.exception),
        )

    def test_flag_justification_grammar_is_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self.make_closed_legacy_run(Path(tmp))
            for bad in ("", "   ", "two\nlines", "carriage\rreturn"):
                with self.assertRaises(journal.CoordinationRefusal):
                    validate_run(run_dir, gates=True, closed_legacy_compat=bad)

    def test_run_closed_stays_fully_strict_under_the_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, records = self.make_legacy_run(Path(tmp))
            bad_close = dict(self.RUN_CLOSED)
            bad_close["judgment"] = "wrapped-up"
            write_journal(run_dir, [*records, bad_close])
            flagged = validate_run(
                run_dir, gates=True, closed_legacy_compat="operator-directed"
            )
        self.assertFalse(flagged["ok"])
        self.assertTrue(
            any("judgment" in issue for issue in flagged["issues"]),
            flagged["issues"],
        )

    def test_disabled_leg_makes_the_flag_grant_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self.make_closed_legacy_run(Path(tmp))
            enabled = validate_run(
                run_dir, gates=True, closed_legacy_compat="operator-directed"
            )
            with mock.patch.object(
                journal, "CLOSED_RUN_DISPENSATION_LEGS", frozenset()
            ):
                disabled = validate_run(
                    run_dir, gates=True, closed_legacy_compat="operator-directed"
                )
        self.assertTrue(enabled["ok"], enabled["issues"])
        self.assertFalse(disabled["ok"])

    def test_cli_flag_round_trip_and_refusal_exit_codes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self.make_closed_legacy_run(Path(tmp))
            accepted = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "validate",
                    "--gates",
                    "--closed-legacy-compat",
                    "operator-directed archive",
                    str(run_dir),
                ],
                check=False,
                text=True,
                capture_output=True,
                cwd=ROOT,
            )
            payload = json.loads(accepted.stdout)
            open_run_dir, _ = self.make_legacy_run(Path(tmp) / "open")
            refused = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "validate",
                    "--gates",
                    "--closed-legacy-compat",
                    "x",
                    str(open_run_dir),
                ],
                check=False,
                text=True,
                capture_output=True,
                cwd=ROOT,
            )
        self.assertEqual(0, accepted.returncode, accepted.stderr)
        self.assertTrue(payload["ok"], payload["issues"])
        self.assertEqual(2, refused.returncode)
        self.assertEqual(
            "forge: closed-legacy-compat refused — journal has no run_closed entry",
            refused.stderr.strip(),
        )


class CitationRootTests(unittest.TestCase):
    """Revision 13 (FR-011 amendment, bead forge-plugin-7t0): ordered citation roots."""

    def layout(self, root: Path) -> tuple[Path, Path]:
        repo = root / "repo"
        run_dir = repo / ".codex-orchestrator" / "runs" / "run-20260904-roots"
        run_dir.mkdir(parents=True)
        return repo, run_dir

    def gate_records(self, evidence: str) -> list[dict[str, object]]:
        return [
            {"type": "run_started"},
            {"type": "task", "id": "task-01", "status": "complete"},
            {
                "type": "verification",
                "id": "check-01",
                "task": "task-01",
                "criterion": "gate-1: unit tests",
                "method": "unittest",
                "check": "python3 -m unittest",
                "result": "passed",
                "observation": "OK",
                "evidence": [evidence],
            },
            {"type": "run_closed", "judgment": "passed", "summary": "done"},
        ]

    def test_repository_root_resolves_drained_chain_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo, run_dir = self.layout(Path(tmp))
            evidence = repo / ".forge/chains/c-2026-09-04T000000Z-abcd/evidence"
            evidence.mkdir(parents=True)
            (evidence / "gate-1-01.log").write_text("OK\n", encoding="utf-8")
            citation = ".forge/chains/c-2026-09-04T000000Z-abcd/evidence/gate-1-01.log"
            write_journal(run_dir, self.gate_records(citation))
            result = validate_run(run_dir)
            self.assertTrue(result["ok"], result["issues"])
            self.assertTrue(journal.declared_file_exists(run_dir, citation))
            # A copy under the run directory still wins (run root first).
            mirrored = run_dir / citation
            mirrored.parent.mkdir(parents=True)
            mirrored.write_text("OK\n", encoding="utf-8")
            self.assertEqual(journal._resolve_declared_path(run_dir, citation), mirrored.resolve())
            # Disabling the repository root in memory restores the refusal.
            mirrored.unlink()
            with mock.patch.object(journal, "VALIDATION_REPOSITORY_LEG", False):
                disabled = validate_run(run_dir)
            self.assertFalse(disabled["ok"])
            self.assertTrue(
                any("referenced evidence[0] file does not exist" in issue for issue in disabled["issues"]),
                disabled["issues"],
            )

    def test_escapes_absent_paths_and_foreign_layouts_still_refuse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo, run_dir = self.layout(Path(tmp))
            outside = Path(tmp) / "outside.log"
            outside.write_text("OK\n", encoding="utf-8")
            link_dir = repo / "evidence"
            link_dir.mkdir()
            (link_dir / "escape.log").symlink_to(outside)
            write_journal(run_dir, self.gate_records("evidence/escape.log"))
            escaped = validate_run(run_dir)
            self.assertFalse(escaped["ok"])
            self.assertTrue(
                any("referenced evidence[0] file does not exist" in issue for issue in escaped["issues"]),
                escaped["issues"],
            )
            write_journal(run_dir, self.gate_records("evidence/absent.log"))
            absent = validate_run(run_dir)
            self.assertFalse(absent["ok"])
            self.assertTrue(
                any("referenced evidence[0] file does not exist" in issue for issue in absent["issues"]),
                absent["issues"],
            )
            write_journal(run_dir, self.gate_records(str(outside)))
            absolute = validate_run(run_dir)
            self.assertTrue(absolute["ok"], absolute["issues"])  # upstream run-only reading of absolute paths is unchanged
            # A run directory outside the fixed layout never gains a repository
            # root, even when the cited file exists two levels up where the
            # layout-derived root would have been.
            foreign = Path(tmp) / "elsewhere" / "runs" / "run-20260904-foreign"
            foreign.mkdir(parents=True)
            would_be_root = Path(tmp) / "elsewhere"
            (would_be_root / ".forge/chains/x/evidence").mkdir(parents=True)
            (would_be_root / ".forge/chains/x/evidence/gate-1-01.log").write_text("OK\n", encoding="utf-8")
            write_journal(foreign, self.gate_records(".forge/chains/x/evidence/gate-1-01.log"))
            self.assertIsNone(journal._layout_repository_root(foreign))
            foreign_result = validate_run(foreign)
            self.assertFalse(foreign_result["ok"])
            self.assertTrue(
                any("referenced evidence[0] file does not exist" in issue for issue in foreign_result["issues"]),
                foreign_result["issues"],
            )

    def test_legacy_missing_evidence_leg_consults_both_roots(self) -> None:
        """FR-016 tolerates a missing evidence file only when both roots miss it."""
        declaration = {
            "type": "decision",
            "id": "journal-dialect-compat",
            "resolution": "legacy-dialect-compat: operator-approved migration",
        }
        with tempfile.TemporaryDirectory() as tmp:
            repo, run_dir = self.layout(Path(tmp))
            outside = Path(tmp) / "outside.log"
            outside.write_text("OK\n", encoding="utf-8")
            (repo / "evidence").mkdir()
            (repo / "evidence" / "escape.log").symlink_to(outside)
            (repo / "evidence" / "dir.log").mkdir()

            def legacy_records(citation: str) -> list[dict[str, object]]:
                records = self.gate_records(citation)
                # The declaration must follow the pre-declaration record it covers.
                return records[:-1] + [declaration, records[-1]]

            for citation in ("evidence/escape.log", "evidence/dir.log"):
                with self.subTest(citation=citation):
                    write_journal(run_dir, legacy_records(citation))
                    present_but_invalid = validate_run(run_dir)
                    self.assertFalse(present_but_invalid["ok"], present_but_invalid)
                    self.assertTrue(
                        any("referenced evidence[0] file does not exist" in issue
                            for issue in present_but_invalid["issues"]),
                        present_but_invalid["issues"],
                    )
                    self.assertFalse(
                        any("tolerated missing evidence" in warning
                            for warning in present_but_invalid["warnings"])
                    )
                    # With the repository root disabled the old run-only leg
                    # tolerates the same citation: the branch is load-bearing.
                    with mock.patch.object(journal, "VALIDATION_REPOSITORY_LEG", False):
                        tolerated = validate_run(run_dir)
                    self.assertTrue(tolerated["ok"], tolerated["issues"])
                    self.assertTrue(
                        any("tolerated missing evidence[0] file" in warning
                            for warning in tolerated["warnings"]),
                        tolerated["warnings"],
                    )
            write_journal(run_dir, legacy_records("evidence/absent.log"))
            absent = validate_run(run_dir)
            self.assertTrue(absent["ok"], absent["issues"])
            self.assertTrue(
                any("tolerated missing evidence[0] file" in warning for warning in absent["warnings"]),
                absent["warnings"],
            )

    def test_symlinked_run_directory_derives_the_physical_repository(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_b, physical_run = self.layout(Path(tmp))
            repo_a = Path(tmp) / "repo-a"
            (repo_a / ".codex-orchestrator" / "runs").mkdir(parents=True)
            linked_run = repo_a / ".codex-orchestrator" / "runs" / physical_run.name
            linked_run.symlink_to(physical_run, target_is_directory=True)
            evidence = repo_b / ".forge/chains/c-2026-09-04T000000Z-abcd/evidence"
            evidence.mkdir(parents=True)
            (evidence / "gate-1-01.log").write_text("OK\n", encoding="utf-8")
            citation = ".forge/chains/c-2026-09-04T000000Z-abcd/evidence/gate-1-01.log"
            write_journal(physical_run, self.gate_records(citation))
            self.assertEqual(journal._layout_repository_root(linked_run), repo_b.resolve())
            self.assertTrue(validate_run(linked_run)["ok"])
            # The same file under repo-a (the link's spelling) is not the root.
            (repo_a / ".forge/chains/c-2026-09-04T000000Z-abcd/evidence").mkdir(parents=True)
            (evidence / "gate-1-01.log").unlink()
            (repo_a / citation).write_text("OK\n", encoding="utf-8")
            self.assertFalse(validate_run(linked_run)["ok"])

    def test_mirror_validation_needs_the_explicit_repository_root(self) -> None:
        """A journal validated outside the layout resolves only with the override."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, run_dir = self.layout(Path(tmp))
            evidence = repo / ".forge/chains/c-2026-09-04T000000Z-abcd/evidence"
            evidence.mkdir(parents=True)
            (evidence / "gate-1-01.log").write_text("OK\n", encoding="utf-8")
            citation = ".forge/chains/c-2026-09-04T000000Z-abcd/evidence/gate-1-01.log"
            records = self.gate_records(citation)
            write_journal(run_dir, records)
            mirror = Path(tmp) / "mirror" / run_dir.name
            mirror.mkdir(parents=True)
            write_journal(mirror, records)
            self.assertFalse(validate_run(mirror)["ok"])
            self.assertTrue(validate_run(mirror, repository=repo)["ok"])
            with mock.patch.object(journal, "VALIDATION_REPOSITORY_LEG", False):
                self.assertFalse(validate_run(mirror, repository=repo)["ok"])
            # The override never leaks past the call.
            self.assertIsNone(journal._VALIDATION_REPOSITORY.get())
            # The archive's pre-close recompute passes the real run's root.
            archive = sys.modules.get("_forge_validation_archive_probe")
            if archive is None:
                specification = importlib.util.spec_from_file_location(
                    "_forge_validation_archive_probe",
                    ROOT / "scripts" / "forge" / "archive-run.py",
                )
                assert specification is not None and specification.loader is not None
                archive = importlib.util.module_from_spec(specification)
                sys.modules["_forge_validation_archive_probe"] = archive
                specification.loader.exec_module(archive)
            closed = records[:-1] + [
                {"type": "run_closed", "judgment": "passed", "summary": "done",
                 "validation": {"ok": True, "issues": [], "warnings": [],
                                "non_passing_verifications": [], "profile": "gates"}}
            ]
            write_journal(run_dir, closed)
            for line, record in enumerate(closed, start=1):
                record["_line"] = line
            fresh = archive.recompute_pre_close_validation(run_dir, closed)
            self.assertTrue(fresh["ok"], fresh)
            # The archive binds its own journal module instance; disable the
            # control there to prove the recompute depends on it.
            with mock.patch.object(archive.journal_engine, "VALIDATION_REPOSITORY_LEG", False):
                degraded = archive.recompute_pre_close_validation(run_dir, closed)
            self.assertFalse(degraded["ok"], degraded)


if __name__ == "__main__":
    unittest.main()
