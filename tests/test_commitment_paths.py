"""Coextensiveness tests for the shared FR-017 path inventory."""

from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]

import sys

sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "forge"))

import commitment_paths  # noqa: E402
from codex_orchestrator import batch, journal  # noqa: E402


class CommitmentPathInventoryTests(unittest.TestCase):
    maxDiff = None

    def test_exact_immutable_fourteen_surface_table(self) -> None:
        expected = (
            ("execution.prompt", "record", ("run", "repository"), ("append", "audit"), "execution", "prompt", "direct", None, True, False, False, None, "record-citation", False, False, None),
            ("execution.events", "record", ("run", "repository"), ("append", "audit"), "execution", "events", "direct", None, True, False, False, None, "record-citation", False, False, None),
            ("execution.handoff", "record", ("run", "repository"), ("append", "audit"), "execution", "handoff", "direct", None, False, False, False, None, "record-citation", False, False, None),
            ("execution_result.handoff", "record", ("run", "repository"), ("append", "audit"), "execution_result", "handoff", "direct", None, False, False, False, None, "record-citation", False, False, None),
            ("verification.evidence", "record", ("run", "repository"), ("append", "audit"), "verification", "evidence", "array", None, True, False, False, None, "record-citation", False, False, None),
            ("decision.basis", "record", ("run", "repository"), ("append", "audit"), "decision", "basis", "token-array", "basis", True, True, True, None, "record-citation", False, False, None),
            ("verification.observation", "record", ("run", "repository"), ("append", "audit"), "verification", "observation", "tokens", "observation", True, True, True, None, "record-citation", False, False, None),
            ("ingest.state_file", "ingest-input", ("repository",), ("capture", "audit"), None, None, "direct", None, False, False, False, None, "capture-surrogate", False, False, None),
            ("ingest.events_file", "ingest-input", ("repository",), ("capture", "audit"), None, None, "direct", None, False, False, False, None, "capture-surrogate", False, False, None),
            ("ingest.outcome_map", "ingest-input", ("repository",), ("capture", "audit"), None, None, "direct", None, False, False, False, None, "capture-surrogate", False, False, None),
            ("ingest.captured_package", "ingest-capture", ("run",), ("capture", "audit"), None, None, "direct", None, False, False, False, "captured-digest", "structured-landing", True, True, None),
            ("batch.intent", "batch", ("run",), ("append", "audit"), None, None, "direct", None, False, False, False, "run", "optional-derived", True, True, ".journal-batch.intent"),
            ("batch.receipt", "batch", ("run",), ("append", "audit"), None, None, "direct", None, False, False, False, "run", "activated-required", True, True, ".journal-batch-receipts.jsonl"),
            ("archive.candidate", "archive", ("repository",), ("render", "audit"), None, None, "direct", None, False, False, False, "archive-history", "optional-derived", True, True, ".forge/history/runs/{run_id}.md"),
        )
        actual = tuple(
            (
                surface.label,
                surface.owner,
                surface.roots,
                surface.enforcement,
                surface.record_type,
                surface.field,
                surface.extraction,
                surface.context,
                surface.legacy_missing,
                surface.correctable,
                surface.dispensable,
                surface.direct_child_parent,
                surface.audit_policy,
                surface.owner_controlled,
                surface.single_link,
                surface.derived_path,
            )
            for surface in commitment_paths.COMMITMENT_PATH_SURFACES
        )

        self.assertEqual(expected, actual)
        self.assertEqual(
            commitment_paths.COMMITMENT_PATH_SURFACES,
            commitment_paths.commitment_surfaces(),
        )
        self.assertTrue(
            all(
                surface.no_follow and surface.file_type == "regular-file"
                for surface in commitment_paths.COMMITMENT_PATH_SURFACES
            )
        )
        with self.assertRaises(FrozenInstanceError):
            commitment_paths.COMMITMENT_PATH_SURFACES[0].label = "disabled"  # type: ignore[misc]

        expected_projections = {
            "append": (
                "execution.prompt",
                "execution.events",
                "execution.handoff",
                "execution_result.handoff",
                "verification.evidence",
                "decision.basis",
                "verification.observation",
                "batch.intent",
                "batch.receipt",
            ),
            "capture": (
                "ingest.state_file",
                "ingest.events_file",
                "ingest.outcome_map",
                "ingest.captured_package",
            ),
            "render": ("archive.candidate",),
            "audit": tuple(row[0] for row in expected),
        }
        self.assertEqual(
            expected_projections,
            {
                enforcement: tuple(
                    surface.label
                    for surface in commitment_paths.commitment_surfaces(
                        enforcement=enforcement
                    )
                )
                for enforcement in ("append", "capture", "render", "audit")
            },
        )

    def test_run_captured_path_grammar_is_exact_and_run_relative(self) -> None:
        digest = "a" * 64
        for name in commitment_paths.CAPTURED_PACKAGE_NAMES:
            with self.subTest(name=name):
                value = f"captured/sha256/{digest}/{name}"
                parsed = commitment_paths.parse_run_captured_path(
                    value,
                    run_id="run-20260829-capture",
                )
                self.assertIsNotNone(parsed)
                assert parsed is not None
                self.assertEqual(value, parsed.relative)
                self.assertEqual(digest, parsed.digest)
                self.assertEqual(name, parsed.name)

        invalid = (
            f".codex-orchestrator/runs/run-20260829-capture/captured/sha256/{digest}/state.json",
            f"/captured/sha256/{digest}/state.json",
            f"../captured/sha256/{digest}/state.json",
            f"captured/sha256/{digest.upper()}/state.json",
            f"captured/sha256/{digest}/nested/state.json",
            f"captured/sha256/{digest}/other.json",
        )
        for value in invalid:
            with self.subTest(value=value):
                self.assertIsNone(
                    commitment_paths.parse_run_captured_path(
                        value,
                        run_id="run-20260829-capture",
                    )
                )
        self.assertIsNone(
            commitment_paths.parse_run_captured_path(
                f"captured/sha256/{digest}/state.json",
                run_id="../wrong-run",
            )
        )

    def test_generic_policy_enforces_table_direct_child_and_no_follow(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository = base / "repo"
            run_dir = repository / ".codex-orchestrator/runs/run-policy"
            digest_dir = run_dir / "captured/sha256" / ("a" * 64)
            archive_parent = repository / ".forge/history/runs"
            digest_dir.mkdir(parents=True)
            archive_parent.mkdir(parents=True)

            state_file = repository / "chains/state.json"
            state_file.parent.mkdir()
            state_file.write_text("{}\n", encoding="utf-8")
            ingest = commitment_paths.commitment_surface("ingest.state_file")
            self.assertIsNotNone(
                commitment_paths.validate_surface_path(
                    ingest,
                    "chains/state.json",
                    repository=repository,
                    run_dir=run_dir,
                    require_file=True,
                )
            )
            (repository / "chains/state-link.json").symlink_to(state_file)
            self.assertIsNone(
                commitment_paths.validate_surface_path(
                    ingest,
                    "chains/state-link.json",
                    repository=repository,
                    run_dir=run_dir,
                    require_file=True,
                )
            )

            captured_file = digest_dir / "state.json"
            captured_file.write_text("{}\n", encoding="utf-8")
            captured = commitment_paths.commitment_surface(
                "ingest.captured_package"
            )
            captured_value = captured_file.relative_to(run_dir).as_posix()
            self.assertIsNotNone(
                commitment_paths.validate_surface_path(
                    captured,
                    captured_value,
                    repository=repository,
                    run_dir=run_dir,
                    direct_parent=digest_dir,
                    require_file=True,
                )
            )
            self.assertIsNone(
                commitment_paths.validate_surface_path(
                    captured,
                    "captured/sha256/nested/state.json",
                    repository=repository,
                    run_dir=run_dir,
                    direct_parent=digest_dir,
                )
            )
            hardlinked = digest_dir / "events.jsonl"
            os.link(captured_file, hardlinked)
            self.assertIsNone(
                commitment_paths.validate_surface_path(
                    captured,
                    hardlinked.relative_to(run_dir).as_posix(),
                    repository=repository,
                    run_dir=run_dir,
                    direct_parent=digest_dir,
                    require_file=True,
                )
            )

            intent = commitment_paths.commitment_surface("batch.intent")
            self.assertIsNotNone(
                commitment_paths.validate_surface_path(
                    intent,
                    ".journal-batch.intent",
                    repository=repository,
                    run_dir=run_dir,
                    direct_parent=run_dir,
                )
            )
            self.assertIsNone(
                commitment_paths.validate_surface_path(
                    intent,
                    "nested/.journal-batch.intent",
                    repository=repository,
                    run_dir=run_dir,
                    direct_parent=run_dir,
                )
            )

            archive = commitment_paths.commitment_surface("archive.candidate")
            self.assertIsNotNone(
                commitment_paths.validate_surface_path(
                    archive,
                    ".forge/history/runs/run-policy.md",
                    repository=repository,
                    run_dir=run_dir,
                    direct_parent=archive_parent,
                )
            )

    def test_record_expansion_is_coextensive_for_journal_and_audit(self) -> None:
        records = (
            {
                "type": "execution",
                "execution": "execution-01",
                "prompt": "prompt.md",
                "events": "events.jsonl",
                "handoff": "handoff.md",
            },
            {
                "type": "execution_result",
                "execution": "execution-01",
                "handoff": "handoff.md",
            },
            {
                "type": "verification",
                "id": "verification-evidence",
                "evidence": ["evidence/one.txt", "evidence/two.txt"],
            },
            {
                "type": "decision",
                "id": "decision-01",
                "basis": ["reviewed `plans/final.md`"],
            },
            {
                "type": "verification",
                "id": "verification-observation",
                "observation": "checked `evidence/observation.txt`",
            },
        )
        expanded = tuple(
            citation
            for record in records
            for citation in commitment_paths.iter_record_citations(record)
        )
        self.assertEqual(
            (
                "execution.prompt",
                "execution.events",
                "execution.handoff",
                "execution_result.handoff",
                "verification.evidence[0]",
                "verification.evidence[1]",
                "decision.basis[0]",
                "verification.observation token evidence/observation.txt",
            ),
            tuple(citation.label for citation in expanded),
        )
        record_inventory = tuple(
            surface.label
            for surface in commitment_paths.COMMITMENT_PATH_SURFACES
            if surface.owner == "record"
        )
        self.assertEqual(
            record_inventory,
            tuple(dict.fromkeys(citation.surface.label for citation in expanded)),
        )
        self.assertEqual(
            tuple(
                (citation.label, citation.value)
                for record in records
                for citation in commitment_paths.iter_record_citations(record)
            ),
            tuple(
                citation
                for record in records
                for citation in journal._record_citations(record)
            ),
        )

        spec = importlib.util.spec_from_file_location(
            "audit_commitments_inventory_test",
            ROOT / "scripts" / "forge" / "audit-commitments.py",
        )
        assert spec is not None and spec.loader is not None
        audit = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = audit
        self.addCleanup(sys.modules.pop, spec.name, None)
        spec.loader.exec_module(audit)
        audited = audit.citations(records)
        self.assertEqual(
            tuple(citation.surface.label for citation in expanded),
            tuple(citation.surface.label for citation in audited),
        )
        self.assertEqual(
            {"decision.basis", "verification.observation"},
            {
                citation.surface.label
                for citation in audited
                if citation.target is not None
            },
        )

        disabled = tuple(
            replace(
                surface,
                enforcement=tuple(
                    point for point in surface.enforcement if point != "audit"
                ),
            )
            if surface.label == "decision.basis"
            else surface
            for surface in commitment_paths.COMMITMENT_PATH_SURFACES
        )
        with mock.patch.object(
            commitment_paths,
            "COMMITMENT_PATH_SURFACES",
            disabled,
        ):
            self.assertNotIn(
                "decision.basis",
                {citation.surface.label for citation in audit.citations(records)},
            )
            self.assertIn(
                "decision.basis",
                {
                    citation.surface.label
                    for record in records
                    for citation in commitment_paths.iter_record_citations(
                        record,
                        enforcement="append",
                    )
                },
            )

    def test_final_built_record_escape_precedes_schema_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository = base / "repo"
            run_dir = repository / ".codex-orchestrator/runs/run-final"
            run_dir.mkdir(parents=True)
            outside = base / "outside/evidence.txt"
            outside.parent.mkdir()
            outside.write_text("outside\n", encoding="utf-8")
            citation = Path(os.path.relpath(outside, run_dir)).as_posix()
            record = {
                "type": "verification",
                "recorded_at": "2026-08-28T12:00:00Z",
                "id": "verification-final-authorized",
                "task": "task-01",
                "criterion": "Authorized ingest result",
                "method": "journal ingest-chain",
                "check": "captured package replay",
                "observation": "authorized final record",
                "result": "passed",
                "evidence": [citation],
            }
            state = journal.RunState(
                "run-final",
                run_dir,
                "open",
                ("src/**",),
                ("src/**",),
            )

            with mock.patch.object(
                journal,
                "_validate_proposed_record",
                side_effect=AssertionError("schema validation ran first"),
            ):
                with self.assertRaisesRegex(
                    journal.CoordinationRefusal,
                    "record cites path outside run or repository: "
                    "verification.evidence\\[0\\]",
                ):
                    batch._prevalidate_records(
                        repository,
                        state,
                        (record,),
                        close=False,
                    )

    def test_typed_binding_replay_refuses_historical_and_projected_duplicates(
        self,
    ) -> None:
        source = {
            "chain_id": "c-2026-08-28T120000Z-abcd",
            "event_digest": "1" * 64,
        }
        candidate = {"kind": "staged-diff-sha256", "value": "2" * 64}
        preimage = {
            "schema": journal.BINDING_SCHEMA,
            "source_record": source,
            "candidate": candidate,
            "review": None,
        }
        binding = dict(preimage)
        binding["binding_id"] = journal._sha256(
            journal._canonical_json_bytes(preimage)
        )

        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "repo"
            run_dir = repository / ".codex-orchestrator/runs/run-replay"
            run_dir.mkdir(parents=True)

            def decision(identifier: str) -> dict[str, object]:
                return {
                    "type": "decision",
                    "recorded_at": "2026-08-28T12:00:00Z",
                    "id": identifier,
                    "resolution": "Retain the replayed chain result",
                    "binding": binding,
                }

            cases = (
                (
                    (
                        {
                            "type": "verification",
                            "id": "verification-existing",
                            "binding": binding,
                        },
                    ),
                    (decision("decision-new"),),
                ),
                (
                    (),
                    (decision("decision-one"), decision("decision-two")),
                ),
            )
            for existing, proposed in cases:
                with self.subTest(existing=bool(existing)):
                    state = journal.RunState(
                        "run-replay",
                        run_dir,
                        "open",
                        ("src/**",),
                        ("src/**",),
                        records=existing,
                    )
                    before = tuple(run_dir.iterdir())
                    with self.assertRaises(
                        journal.CoordinationRefusal
                    ) as raised:
                        batch._prevalidate_records(
                            repository,
                            state,
                            proposed,
                            close=False,
                        )
                    self.assertEqual(
                        journal.DUPLICATE_CHAIN_BINDING,
                        str(raised.exception),
                    )
                    self.assertEqual(before, tuple(run_dir.iterdir()))


if __name__ == "__main__":
    unittest.main()
