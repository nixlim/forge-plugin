"""Archive acceptance tests for source-authenticated historical bindings."""

from __future__ import annotations

import ast
import contextlib
import json
import os
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest import mock

from tests import test_revision9_cli_surfaces as rev9
from tests._cli_loader import load_script
from tests.archive_historical_binding_clauses import (
    HistoricalBindingClauseTests as HistoricalBindingClauseTests,
)

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = load_script(
    "_forge_archive_historical_bindings",
    ROOT / "scripts" / "forge" / "archive-run.py",
)
ARCHIVE_REFUSAL = (
    "forge: archive refused — authoritative chain discrepancy: structured_chain_mismatch"
)
BUILDER_REFUSAL = (
    "forge: journal append refused — invalid journal record: binding chain replay failed"
)


@dataclass(frozen=True)
class ArchiveProof:
    """One replay-authenticated live-chain package and its resolution."""

    records: list[dict[str, Any]]
    package: Any
    bindings: Any


def _imports_binding_history(node: ast.AST) -> bool:
    if isinstance(node, ast.Import):
        return any(alias.name.endswith(".binding_history") for alias in node.names)
    if not isinstance(node, ast.ImportFrom):
        return False
    return bool(
        (node.module or "").endswith(".binding_history")
        or any(alias.name == "binding_history" for alias in node.names)
    )


def _enables_historical_replay(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    function = node.func
    targets_resolver = (
        isinstance(function, ast.Name) and function.id == "_resolve_binding_from_descriptor"
    ) or (
        isinstance(function, ast.Attribute) and function.attr == "_resolve_binding_from_descriptor"
    )
    return targets_resolver and any(
        keyword.arg in {None, "historical"} for keyword in node.keywords
    )


class ArchiveHistoricalBindingsTests(rev9.CLI_FIXTURE_SUPPORT.ForgeCLIFixture):
    """Exercise historical acceptance without inheriting another test class."""

    open_run_and_task = rev9.Revision9BoundCLIIntegrationTests.open_run_and_task
    start_bound_chain = rev9.Revision9BoundCLIIntegrationTests.start_bound_chain
    start_bound_fast_chain = rev9.Revision9BoundCLIIntegrationTests.start_bound_fast_chain
    _record_orchestrator_provenance = (
        rev9.Revision9BoundCLIIntegrationTests._record_orchestrator_provenance
    )

    def setUp(self) -> None:
        super().setUp()
        self.cli_environment_overrides: dict[str, str] = {}

    def revision9_environment(self) -> dict[str, str]:
        environment = self.environment(FORGE_SESSION_PID=str(os.getpid()))
        environment.update(self.cli_environment_overrides)
        return environment

    @contextlib.contextmanager
    def cli_process_context(self) -> Iterator[None]:
        with (
            mock.patch.dict(os.environ, self.revision9_environment(), clear=True),
            mock.patch.object(rev9.RUNTIME, "SCRIPT_DIR", self.helpers),
            mock.patch.object(rev9.RUNTIME, "PLUGIN_ROOT", ROOT),
            rev9.patch_engine("CODEX_EXECUTABLE", str(self.helpers / "fake-codex")),
            rev9.patch_engine("CLAUDE_EXECUTABLE", str(self.helpers / "fake-claude")),
        ):
            yield

    invoke_cli = rev9.Revision9BoundCLIIntegrationTests.invoke_cli
    invoke_cli_at = rev9.Revision9BoundCLIIntegrationTests.invoke_cli_at

    def _run_dir(self, run_id: str) -> Path:
        return self.repo / ".codex-orchestrator" / "runs" / run_id

    def _start_fast_unverified(self, run_id: str) -> str:
        self.open_run_and_task(
            run_id,
            scope=("docs/**",),
            files=("docs/guide.md",),
        )
        self.change("docs/guide.md", f"# {run_id}\n")
        exit_code, started = self.invoke_cli(
            "--run-id",
            run_id,
            "commit",
            "start",
            "--paths",
            "docs/guide.md",
            "--task",
            "task-01",
        )
        self.assertEqual(exit_code, 0, started)
        return str(started["chain_id"])

    def _start_hard_unverified(self, run_id: str) -> str:
        self.open_run_and_task(
            run_id,
            scope=("scripts/**",),
            files=("scripts/tool.py",),
        )
        self.change("scripts/tool.py", "CONTROL = 2\n")
        exit_code, started = self.invoke_cli(
            "--run-id",
            run_id,
            "commit",
            "start",
            "--paths",
            "scripts/tool.py",
            "--task",
            "task-01",
        )
        self.assertEqual(exit_code, 0, started)
        chain_id = str(started["chain_id"])
        self.assertEqual(self.state(chain_id)["tier"]["effective"], "hard")
        return chain_id

    def _restage(self, chain_id: str, relative: str, content: str) -> tuple[str, str]:
        old_candidate = str(self.state(chain_id)["candidate"]["authorization_id"])
        self.change(relative, content)
        exit_code, restaged = self.invoke_cli(
            "--chain-id",
            chain_id,
            "commit",
            "restage",
            "--paths",
            relative,
        )
        self.assertEqual(exit_code, 0, restaged)
        self.assertEqual(restaged["state"], "verifying")
        new_candidate = str(self.state(chain_id)["candidate"]["authorization_id"])
        self.assertNotEqual(old_candidate, new_candidate)
        return old_candidate, new_candidate

    def _verify(self, chain_id: str, *, expected: int = 0) -> dict[str, object]:
        exit_code, result = self.invoke_cli("--chain-id", chain_id, "verify")
        self.assertEqual(exit_code, expected, result)
        return result

    def _review(self, chain_id: str) -> None:
        exit_code, requested = self.invoke_cli("--chain-id", chain_id, "review", "request")
        self.assertEqual(exit_code, 0, requested)
        request = self.state(chain_id)["review"]["request"]
        self.assertIsInstance(request, dict)
        self.wait_for_review_completion(request)
        exit_code, collected = self.invoke_cli("--chain-id", chain_id, "review", "collect")
        self.assertEqual(exit_code, 0, collected)
        if collected["state"] == "awaiting_approval":
            candidate = str(self.state(chain_id)["candidate"]["authorization_id"])
            exit_code, approved = self.invoke_cli(
                "--chain-id",
                chain_id,
                "commit",
                "approve",
                "--candidate",
                candidate,
            )
            self.assertEqual(exit_code, 0, approved)
            self.assertEqual(approved["state"], "authorized")
        else:
            self.assertEqual(collected["state"], "authorized")

    def _land(self, chain_id: str, message: str) -> str:
        exit_code, landed = self.invoke_cli(
            "--chain-id",
            chain_id,
            "commit",
            "finalize",
            "--message",
            message,
        )
        self.assertEqual(exit_code, 0, landed)
        self.assertEqual(landed["state"], "closed")
        return self.git("rev-parse", "HEAD")

    def _read_records(self, run_id: str) -> tuple[list[dict[str, Any]], bytes]:
        return ARCHIVE.stable_journal_snapshot(self._run_dir(run_id))

    def _resolve(self, run_id: str) -> ArchiveProof:
        records, raw = self._read_records(run_id)
        activated = ARCHIVE.journal_engine.writer_contract_active(records)
        activated_ids, _origin = ARCHIVE.activated_record_partition(records, raw, activated)
        required_ids = ARCHIVE.binding_chain_ids(
            records,
            activated,
            activated_record_ids=activated_ids,
        )
        selected = (
            [record for record in records if id(record) in activated_ids] if activated else records
        )
        package = ARCHIVE.capture_archive_chain_package(
            self.repo,
            self._run_dir(run_id),
            selected,
            required_ids,
            activated=activated,
        )
        bindings = ARCHIVE.resolve_archive_bindings(
            self.repo,
            self._run_dir(run_id),
            records,
            package,
            activated,
            activated_record_ids=activated_ids,
        )
        return ArchiveProof(records, package, bindings)

    @staticmethod
    def _line_map(proof: ArchiveProof) -> dict[int, dict[str, Any]]:
        return {int(record["_line"]): record for record in proof.records}

    def _historical_rows(
        self, proof: ArchiveProof, reason: str
    ) -> list[tuple[int, dict[str, Any], dict[str, object]]]:
        line_map = self._line_map(proof)
        self.assertIsInstance(proof.bindings, ARCHIVE.binding_history.ResolvedBindings)
        return [
            (line, line_map[line], proof.bindings[line])
            for line, value in proof.bindings.classifications.items()
            if value == reason
        ]

    def _current_lines(self, proof: ArchiveProof) -> set[int]:
        self.assertIsInstance(proof.bindings, ARCHIVE.binding_history.ResolvedBindings)
        return {
            line
            for line, value in proof.bindings.classifications.items()
            if value == ARCHIVE.binding_history.CURRENT
        }

    def _finish_and_close(self, run_id: str) -> Path:
        _batch, builders, journal = rev9.CLI._coordination_modules()
        self._record_orchestrator_provenance(run_id, "historical archive fixture")
        with self.cli_process_context():
            builders.task_finish(
                self.repo,
                run_id,
                idempotency_key=rev9.key(f"{run_id}-finish"),
                task="task-01",
                status="complete",
            )
            builders.run_close(
                self.repo,
                run_id,
                idempotency_key=rev9.key(f"{run_id}-close"),
                judgment="passed",
                summary="Historical bindings remain authenticated",
                risks=[],
                follow_ups=[],
            )
            validation = journal.validate_run(self._run_dir(run_id), gates=True)
        self.assertTrue(validation["ok"], validation)
        post_close = self._run_dir(run_id) / "post-close-validation.json"
        post_close.write_text(
            json.dumps(
                validation,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        return post_close

    def _render_twice(self, run_id: str, closing_head: str, post_close: Path) -> bytes:
        options = {
            "repo": self.repo,
            "run_dir": self._run_dir(run_id),
            "closing_head": closing_head,
            "legacy_recovered_head": None,
            "legacy_approval": None,
            "post_close_validation": post_close,
        }
        with self.cli_process_context():
            first = ARCHIVE.render_archive_candidate(**options)
            second = ARCHIVE.render_archive_candidate(**options)
        self.assertEqual(first, second)
        self.assertLess(len(first), ARCHIVE.ARCHIVE_SIZE_LIMIT)
        return first

    def _assert_control_refuses(
        self,
        run_id: str,
        module: ModuleType,
        attribute: str,
        control: str,
    ) -> None:
        controls = getattr(module, attribute)
        with mock.patch.object(module, attribute, controls - {control}):
            with self.assertRaisesRegex(ARCHIVE.ArchiveRefusal, f"^{re.escape(ARCHIVE_REFUSAL)}$"):
                self._resolve(run_id)

    def _assert_terminal_decision_must_be_current(self, run_id: str, outcome: str) -> None:
        records, _raw = self._read_records(run_id)
        terminal = next(record for record in records if record.get("outcome") == outcome)
        binding_id = str(terminal["binding"]["binding_id"])
        original = ARCHIVE.journal_builders._resolve_binding_from_descriptor
        journal = ARCHIVE.journal_engine

        def make_noncurrent(*args: object, **kwargs: object) -> dict[str, object]:
            result = original(*args, **kwargs)
            if str(args[3]) != binding_id:
                return result
            if not kwargs.get("historical"):
                raise journal.CoordinationRefusal(BUILDER_REFUSAL)
            self.assertEqual(set(result), {"binding", "currency"})
            return {"binding": result["binding"], "currency": "rerun"}

        with (
            mock.patch.object(
                ARCHIVE.journal_builders,
                "_resolve_binding_from_descriptor",
                side_effect=make_noncurrent,
            ),
            self.assertRaisesRegex(ARCHIVE.ArchiveRefusal, f"^{re.escape(ARCHIVE_REFUSAL)}$"),
        ):
            self._resolve(run_id)

    def _assert_currency_disagreement_refuses(self, run_id: str, line: int, currency: str) -> None:
        original = ARCHIVE.binding_history._classify

        def classify_with_disagreement(
            context: Any,
            records: list[dict[str, Any]],
            currencies: Mapping[int, str],
        ) -> dict[int, str]:
            changed = dict(currencies)
            changed[line] = currency
            return original(context, records, changed)

        with (
            mock.patch.object(
                ARCHIVE.binding_history,
                "_classify",
                side_effect=classify_with_disagreement,
            ),
            self.assertRaisesRegex(ARCHIVE.ArchiveRefusal, f"^{re.escape(ARCHIVE_REFUSAL)}$"),
        ):
            self._resolve(run_id)

    def _assert_append_stays_current_only(self, run_id: str, record: dict[str, Any]) -> None:
        _batch, builders, journal = rev9.CLI._coordination_modules()
        binding = record["binding"]
        chain_id = str(binding["source_record"]["chain_id"])
        journal_path = self._run_dir(run_id) / "journal.jsonl"
        before = journal_path.read_bytes()
        with (
            self.cli_process_context(),
            mock.patch.object(builders, "_require_new_chain_binding", return_value=None),
            self.assertRaisesRegex(journal.CoordinationRefusal, f"^{re.escape(BUILDER_REFUSAL)}$"),
        ):
            builders.verification_add(
                self.repo,
                run_id,
                idempotency_key=rev9.key(f"{run_id}-stale-append"),
                task=str(record["task"]),
                criterion=str(record["criterion"]),
                method=str(record["method"]),
                check=str(record["check"]),
                result=str(record["result"]),
                observation=str(record["observation"]),
                evidence=list(record["evidence"]),
                binding_chain=chain_id,
                binding_id=str(binding["binding_id"]),
            )
        self.assertEqual(journal_path.read_bytes(), before)

    def test_restaged_landed_history_renders_and_controls_are_load_bearing(
        self,
    ) -> None:
        run_id = "run-20261003-historical-restaged-landed"
        chain_id = self._start_hard_unverified(run_id)
        exit_code, gate = self.invoke_cli("--chain-id", chain_id, "gate", "run", "gate-1")
        self.assertEqual(exit_code, 0, gate)
        old_candidate, new_candidate = self._restage(chain_id, "scripts/tool.py", "CONTROL = 3\n")
        self.assertEqual(self._verify(chain_id)["state"], "reviewing")
        self._review(chain_id)
        closing_head = self._land(chain_id, "Land restaged historical fixture")

        proof = self._resolve(run_id)
        rows = self._historical_rows(proof, "superseded candidate")
        self.assertTrue(rows)
        self.assertTrue(
            all(
                binding["candidate"]["value"]["authorization_id"] == old_candidate
                for _line, _record, binding in rows
            )
        )
        self.assertTrue(
            any(
                binding["candidate"]["value"]["authorization_id"] == new_candidate
                for line, binding in proof.bindings.items()
                if line in self._current_lines(proof)
            )
        )
        line, record, binding = rows[0]
        self._assert_append_stays_current_only(run_id, record)
        post_close = self._finish_and_close(run_id)
        rendered = self._render_twice(run_id, closing_head, post_close).decode()
        status = (
            "BOUND — source-authenticated history; NOT LANDING EVIDENCE "
            f"(superseded candidate; {binding['binding_id']})"
        )
        self.assertIn(status, rendered)
        self.assertIn(f"- line {line}: {status}", rendered)
        gate_row = next(row for row in rendered.splitlines() if status in row)
        self.assertIn(f"| {old_candidate} |", gate_row)
        self.assertNotIn("`structured_chain_mismatch`", rendered)
        self.assertNotIsInstance(proof.bindings, dict)
        with self.assertRaisesRegex(ARCHIVE.ArchiveRefusal, f"^{re.escape(ARCHIVE_REFUSAL)}$"):
            ARCHIVE.binding_history.status_for(
                dict(proof.bindings),
                line,
                binding["binding_id"],
                ARCHIVE.authoritative_discrepancy,
            )

        self._assert_control_refuses(
            run_id,
            ARCHIVE.journal_builders,
            "BUILDER_VALIDATION_CONTROLS",
            "historical-binding-replay",
        )
        self._assert_control_refuses(run_id, ARCHIVE, "RENDERER_CONTROLS", "historical-binding")
        self._assert_terminal_decision_must_be_current(run_id, "chain-landing")

        superseded = {str(item[2]["binding_id"]) for item in rows}
        with (
            mock.patch.object(
                ARCHIVE.binding_history.journal,
                "_superseded_binding_ids",
                return_value=set(),
            ),
            self.assertRaisesRegex(ARCHIVE.ArchiveRefusal, f"^{re.escape(ARCHIVE_REFUSAL)}$"),
        ):
            self._resolve(run_id)
        current_line, current_gate = next(
            (line_number, binding)
            for line_number, binding in proof.bindings.items()
            if line_number in self._current_lines(proof)
            and self._line_map(proof)[line_number].get("type") == "verification"
        )
        self.assertEqual(
            ARCHIVE.binding_history.status_for(
                proof.bindings,
                current_line,
                current_gate["binding_id"],
                ARCHIVE.authoritative_discrepancy,
            ),
            f"BOUND ({current_gate['binding_id']})",
        )
        self.assertEqual(
            ARCHIVE.binding_history.journal_mapping(
                proof.bindings,
                current_line,
                current_gate["binding_id"],
                ARCHIVE.authoritative_discrepancy,
            ),
            f"- line {current_line}: {current_gate['binding_id']}",
        )
        with (
            mock.patch.object(
                ARCHIVE.binding_history.journal,
                "_superseded_binding_ids",
                return_value=superseded | {str(current_gate["binding_id"])},
            ),
            self.assertRaisesRegex(ARCHIVE.ArchiveRefusal, f"^{re.escape(ARCHIVE_REFUSAL)}$"),
        ):
            self._resolve(run_id)

        self._assert_currency_disagreement_refuses(run_id, line, "rerun")

    def test_restage_then_rerun_then_land_observes_source_event_order(self) -> None:
        run_id = "run-20261004-historical-restage-rerun-land"
        chain_id = self._start_hard_unverified(run_id)
        exit_code, gate = self.invoke_cli("--chain-id", chain_id, "gate", "run", "gate-1")
        self.assertEqual(exit_code, 0, gate)
        old_candidate, new_candidate = self._restage(chain_id, "scripts/tool.py", "CONTROL = 3\n")
        for _index in range(2):
            exit_code, gate = self.invoke_cli("--chain-id", chain_id, "gate", "run", "gate-1")
            self.assertEqual(exit_code, 0, gate)
        self.assertEqual(self._verify(chain_id)["state"], "reviewing")
        self._review(chain_id)
        self._land(chain_id, "Land restaged rerun historical fixture")

        proof = self._resolve(run_id)
        self.assertEqual(
            set(proof.bindings.classifications.values()),
            {
                ARCHIVE.binding_history.CURRENT,
                ARCHIVE.binding_history.RERUN,
                ARCHIVE.binding_history.SUPERSEDED,
            },
        )
        superseded = self._historical_rows(proof, ARCHIVE.binding_history.SUPERSEDED)
        reruns = self._historical_rows(proof, ARCHIVE.binding_history.RERUN)
        self.assertTrue(superseded)
        self.assertTrue(reruns)
        self.assertTrue(
            all(
                row[2]["candidate"]["value"]["authorization_id"] == old_candidate
                for row in superseded
            )
        )
        self.assertTrue(
            all(row[2]["candidate"]["value"]["authorization_id"] == new_candidate for row in reruns)
        )

    def test_restaged_abort_marks_current_record_and_requires_abort_control(
        self,
    ) -> None:
        run_id = "run-20261003-historical-restaged-abort"
        chain_id = self.start_bound_fast_chain(run_id)
        self._restage(chain_id, "docs/guide.md", "# Restaged aborted candidate\n")
        exit_code, aborted = self.invoke_cli(
            "--chain-id",
            chain_id,
            "commit",
            "abort",
            "--reason",
            "exercise carried abort history",
        )
        self.assertEqual(exit_code, 0, aborted)
        self.assertEqual(aborted["state"], "aborted")
        proof = self._resolve(run_id)
        superseded = self._historical_rows(proof, "superseded candidate")
        aborted_rows = self._historical_rows(proof, "aborted chain")
        self.assertTrue(superseded)
        self.assertTrue(aborted_rows)
        abort_line, abort_record, abort_binding = next(
            row for row in aborted_rows if row[1].get("outcome") == "chain-abort"
        )
        self.assertNotIn(abort_line, {line for line, _record, _binding in superseded})
        post_close = self._finish_and_close(run_id)
        closing_head = self.git("rev-parse", "HEAD")
        rendered = self._render_twice(run_id, closing_head, post_close).decode()
        status = (
            "BOUND — source-authenticated history; NOT LANDING EVIDENCE "
            f"(aborted chain; {abort_binding['binding_id']})"
        )
        self.assertIn(f"Binding status: {status}", rendered)
        self.assertIn(f"- line {abort_line}: {status}", rendered)
        self.assertEqual(abort_record["outcome"], "chain-abort")
        self._assert_control_refuses(run_id, ARCHIVE, "RENDERER_CONTROLS", "historical-abort")
        self._assert_terminal_decision_must_be_current(run_id, "chain-abort")
        self._assert_currency_disagreement_refuses(run_id, abort_line, "superseded")
        with (
            mock.patch.object(
                ARCHIVE.binding_history.landed_evidence,
                "retirement_predicate",
                return_value=lambda _record: False,
            ),
            self.assertRaisesRegex(ARCHIVE.ArchiveRefusal, f"^{re.escape(ARCHIVE_REFUSAL)}$"),
        ):
            self._resolve(run_id)

    def test_aborted_chain_precedes_an_earlier_rerun(self) -> None:
        run_id = "run-20261004-historical-abort-rerun"
        chain_id = self.start_bound_chain(run_id)
        for _index in range(2):
            exit_code, gate = self.invoke_cli("--chain-id", chain_id, "gate", "run", "gate-1")
            self.assertEqual(exit_code, 0, gate)
        exit_code, aborted = self.invoke_cli(
            "--chain-id",
            chain_id,
            "commit",
            "abort",
            "--reason",
            "pin aborted-before-rerun precedence",
        )
        self.assertEqual(exit_code, 0, aborted)
        self.assertEqual(aborted["state"], "aborted")

        proof = self._resolve(run_id)
        self.assertFalse(ARCHIVE.binding_history.journal._superseded_binding_ids(proof.records))
        self.assertEqual(
            set(proof.bindings.classifications.values()),
            {ARCHIVE.binding_history.ABORTED},
        )
        gate_rows = [
            record for record in proof.records if record.get("criterion", "").startswith("gate-1: ")
        ]
        self.assertGreaterEqual(len(gate_rows), 2)

    def test_failed_then_passed_is_a_cleared_recheck(self) -> None:
        run_id = "run-20261003-historical-recheck"
        chain_id = self.start_bound_chain(run_id)
        self.cli_environment_overrides["FORGE_TEST_FAIL_ONCE"] = "gate-1"
        self.assertEqual(self._verify(chain_id, expected=1)["state"], "verifying")
        self.assertEqual(self._verify(chain_id)["state"], "reviewing")
        self._review(chain_id)
        self._land(chain_id, "Land passing recheck fixture")

        proof = self._resolve(run_id)
        rows = self._historical_rows(proof, "failed gate cleared by passing recheck")
        self.assertTrue(rows)
        self.assertTrue(all(record["result"] == "failed" for _, record, _ in rows))
        line, failed_record, binding = rows[0]
        self.assertEqual(
            ARCHIVE.binding_history.status_for(
                proof.bindings,
                line,
                binding["binding_id"],
                ARCHIVE.authoritative_discrepancy,
            ),
            "BOUND — source-authenticated history; NOT LANDING EVIDENCE "
            f"(failed gate cleared by passing recheck; {binding['binding_id']})",
        )
        current_passes = [
            record
            for line, record in self._line_map(proof).items()
            if line in self._current_lines(proof)
            and record.get("type") == "verification"
            and record.get("result") == "passed"
        ]
        self.assertTrue(current_passes)
        verifications = [record for record in proof.records if record.get("type") == "verification"]
        recheck = ARCHIVE.binding_history.landed_evidence.recheck_source(proof.records)
        self.assertFalse(
            ARCHIVE.binding_history._cleared_by_current_recheck(
                failed_record, verifications, recheck, set()
            )
        )
        self.assertTrue(
            ARCHIVE.binding_history._cleared_by_current_recheck(
                failed_record,
                verifications,
                recheck,
                self._current_lines(proof),
            )
        )
        self._assert_control_refuses(run_id, ARCHIVE, "RENDERER_CONTROLS", "historical-recheck")
        self._assert_currency_disagreement_refuses(run_id, line, "superseded")
        self._assert_currency_disagreement_refuses(run_id, line, "current")
        with (
            mock.patch.object(
                ARCHIVE.binding_history,
                "_cleared_by_current_recheck",
                return_value=False,
            ),
            self.assertRaisesRegex(ARCHIVE.ArchiveRefusal, f"^{re.escape(ARCHIVE_REFUSAL)}$"),
        ):
            self._resolve(run_id)

    def test_passed_then_passed_is_an_earlier_rerun(self) -> None:
        run_id = "run-20261003-historical-rerun"
        chain_id = self.start_bound_chain(run_id)
        self.assertEqual(self._verify(chain_id)["state"], "reviewing")
        self._review(chain_id)
        original_candidate = self.state(chain_id)["candidate"]["authorization_id"]
        self.move_head_same_tree()
        moved = self._verify(chain_id, expected=1)
        self.assertEqual(moved["reason_code"], "head-moved")
        exit_code, rebased = self.invoke_cli("--chain-id", chain_id, "commit", "rebase")
        self.assertEqual(exit_code, 0, rebased)
        self.assertEqual(
            self.state(chain_id)["candidate"]["authorization_id"],
            original_candidate,
        )
        self.assertEqual(self._verify(chain_id)["state"], "authorized")
        self._land(chain_id, "Land same-candidate rerun fixture")

        proof = self._resolve(run_id)
        rows = self._historical_rows(proof, "earlier run of the same step")
        self.assertTrue(rows)
        self.assertTrue(all(record["result"] == "passed" for _, record, _ in rows))
        line, earlier_record, binding = rows[0]
        self.assertEqual(
            ARCHIVE.binding_history.status_for(
                proof.bindings,
                line,
                binding["binding_id"],
                ARCHIVE.authoritative_discrepancy,
            ),
            "BOUND — source-authenticated history; NOT LANDING EVIDENCE "
            f"(earlier run of the same step; {binding['binding_id']})",
        )
        self.assertTrue(
            all(
                binding["candidate"]["value"]["authorization_id"] == original_candidate
                for _line, _record, binding in rows
            )
        )
        self._assert_control_refuses(run_id, ARCHIVE, "RENDERER_CONTROLS", "historical-rerun")
        verifications = [record for record in proof.records if record.get("type") == "verification"]
        newest = ARCHIVE.binding_history._newest_steps(verifications)
        reason_options = {
            "superseded": set(),
            "aborted": False,
            "cleared": False,
            "newest_steps": newest,
        }
        self.assertIsNone(
            ARCHIVE.binding_history._reason_for(
                earlier_record, current_lines=set(), **reason_options
            )
        )
        self.assertEqual(
            ARCHIVE.binding_history._reason_for(
                earlier_record,
                current_lines=self._current_lines(proof),
                **reason_options,
            ),
            ARCHIVE.binding_history.RERUN,
        )
        self._assert_currency_disagreement_refuses(run_id, line, "superseded")
        self._assert_currency_disagreement_refuses(run_id, line, "current")
        with (
            mock.patch.object(ARCHIVE.binding_history, "_newest_steps", return_value={}),
            self.assertRaisesRegex(ARCHIVE.ArchiveRefusal, f"^{re.escape(ARCHIVE_REFUSAL)}$"),
        ):
            self._resolve(run_id)

    def test_nonterminal_and_uncarried_abort_remain_refused(self) -> None:
        run_id = "run-20261003-historical-nonterminal"
        chain_id = self.start_bound_fast_chain(run_id)
        self._restage(chain_id, "docs/guide.md", "# Nonterminal candidate\n")
        self.assertEqual(self._verify(chain_id)["state"], "authorized")

        def assert_refused() -> None:
            with self.assertRaisesRegex(ARCHIVE.ArchiveRefusal, f"^{re.escape(ARCHIVE_REFUSAL)}$"):
                self._resolve(run_id)

        assert_refused()
        with (
            mock.patch.object(
                ARCHIVE.binding_history,
                "_terminal_anchors",
                return_value={chain_id: "chain-landing"},
            ),
            self.assertRaises(AssertionError),
        ):
            assert_refused()

    def test_abort_without_carried_decision_remains_refused(self) -> None:
        run_id = "run-20261003-historical-uncarried-abort"
        chain_id = self.start_bound_fast_chain(run_id)
        self._restage(chain_id, "docs/guide.md", "# Uncarried abort candidate\n")
        self.assertEqual(self._verify(chain_id)["state"], "authorized")
        with mock.patch.object(rev9.RUNTIME, "_build_chain_journal_records", return_value=()):
            exit_code, aborted = self.invoke_cli(
                "--chain-id",
                chain_id,
                "commit",
                "abort",
                "--reason",
                "legacy abort without a carried decision",
            )
        self.assertEqual(exit_code, 0, aborted)
        self.assertEqual(aborted["state"], "aborted")

        def assert_refused() -> None:
            with self.assertRaisesRegex(ARCHIVE.ArchiveRefusal, f"^{re.escape(ARCHIVE_REFUSAL)}$"):
                self._resolve(run_id)

        assert_refused()
        with (
            mock.patch.object(
                ARCHIVE.binding_history,
                "_terminal_anchors",
                return_value={chain_id: "chain-landing"},
            ),
            self.assertRaises(AssertionError),
        ):
            assert_refused()

    def test_non_gate_and_non_chain_decision_history_remain_refused(self) -> None:
        controls = ARCHIVE.RENDERER_CONTROLS
        variants = (
            {"type": "verification", "criterion": "manual: not a gate"},
            {"type": "decision", "outcome": "operator_approval"},
        )
        for fields in variants:
            with self.subTest(fields=fields):
                record = {
                    "_line": 1,
                    "binding": {
                        "binding_id": "historical-binding",
                        "source_record": {"chain_id": "chain"},
                    },
                    **fields,
                }
                context = ARCHIVE.binding_history.ResolutionContext(
                    Path("."),
                    "run-20261003-record-restriction",
                    -1,
                    {"chain": SimpleNamespace(state={})},
                    [record],
                    controls,
                    None,
                    lambda *_args: None,
                    ARCHIVE.authoritative_discrepancy,
                )

                patches = (
                    mock.patch.object(
                        ARCHIVE.binding_history,
                        "_terminal_anchors",
                        return_value={"chain": "chain-landing"},
                    ),
                    mock.patch.object(
                        ARCHIVE.binding_history.journal,
                        "_superseded_binding_ids",
                        return_value={"historical-binding"},
                    ),
                    mock.patch.object(
                        ARCHIVE.binding_history.landed_evidence,
                        "retirement_predicate",
                        return_value=lambda _record: False,
                    ),
                )
                with patches[0], patches[1], patches[2]:
                    with self.assertRaisesRegex(
                        ARCHIVE.ArchiveRefusal,
                        f"^{re.escape(ARCHIVE_REFUSAL)}$",
                    ):
                        ARCHIVE.binding_history._classify(context, [record], {1: "superseded"})
                    with mock.patch.object(
                        ARCHIVE.binding_history,
                        "_historical_record_allowed",
                        return_value=True,
                    ):
                        self.assertEqual(
                            ARCHIVE.binding_history._classify(context, [record], {1: "superseded"}),
                            {1: ARCHIVE.binding_history.SUPERSEDED},
                        )

    def test_historical_mode_is_archive_private_by_ast(self) -> None:
        import_variants = (
            "from codex_orchestrator import binding_history",
            "import codex_orchestrator.binding_history",
            "from codex_orchestrator.binding_history import resolve_live_bindings",
        )
        for source in import_variants:
            self.assertTrue(any(map(_imports_binding_history, ast.walk(ast.parse(source)))))
        enable_variants = (
            "builders._resolve_binding_from_descriptor(historical=True)",
            "builders._resolve_binding_from_descriptor(historical=False)",
            "builders._resolve_binding_from_descriptor(historical=enabled)",
            "builders._resolve_binding_from_descriptor(**options)",
        )
        for source in enable_variants:
            self.assertTrue(any(map(_enables_historical_replay, ast.walk(ast.parse(source)))))
        scripts = ROOT / "scripts"
        importers: set[Path] = set()
        historical_enablers: set[Path] = set()
        for path in scripts.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if _imports_binding_history(node):
                    importers.add(path.relative_to(ROOT))
                if _enables_historical_replay(node):
                    historical_enablers.add(path.relative_to(ROOT))
        self.assertEqual(importers, {Path("scripts/forge/archive-run.py")})
        self.assertEqual(
            historical_enablers,
            {Path("scripts/codex_orchestrator/binding_history.py")},
        )
        planted_variants = {
            Path("scripts/forge/planted_historical_keyword.py"): (
                "builders._resolve_binding_from_descriptor(historical=enabled)"
            ),
            Path("scripts/forge/planted_historical_expansion.py"): (
                "builders._resolve_binding_from_descriptor(**options)"
            ),
        }
        for path, source in planted_variants.items():
            tree = ast.parse(source, filename=str(path))
            if any(map(_enables_historical_replay, ast.walk(tree))):
                historical_enablers.add(path)
        self.assertEqual(
            historical_enablers,
            {
                Path("scripts/codex_orchestrator/binding_history.py"),
                *planted_variants,
            },
        )


if __name__ == "__main__":
    import unittest

    unittest.main()
