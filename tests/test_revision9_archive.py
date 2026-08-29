"""Focused Revision-9 archive fidelity and disable-control tests."""

from __future__ import annotations

import base64
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
ARCHIVER = ROOT / "scripts" / "forge" / "archive-run.py"
PHASE0_HEAD = "f64164b4f8695b745c7a4d85d09cc295aa6d3846"
PHASE0_APPROVAL = "run-20260827-archive-fidelity:decision-03"
HARDENING_HEAD = "76d4f7a4d638b98812fc570ba033d7a19b1c7d61"
HARDENING_ARCHIVE_SHA = "bf8aaff5c3bbc4d285c28c968b3a72b5ef704a8d588645347c43ba96b225d57b"


def load_archiver() -> object:
    name = "_forge_revision9_archive_tests"
    cached = sys.modules.get(name)
    if cached is not None:
        return cached
    specification = importlib.util.spec_from_file_location(name, ARCHIVER)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


archive = load_archiver()


def load_cli_fixture_support() -> object:
    name = "_forge_revision9_archive_cli_fixture_support"
    cached = sys.modules.get(name)
    if cached is not None:
        return cached
    path = ROOT / "tests" / "test_cli_chain.py"
    specification = importlib.util.spec_from_file_location(name, path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


CLI_FIXTURE_SUPPORT = load_cli_fixture_support()


def canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


class Revision9ArchiveBlocksTests(unittest.TestCase):
    def test_discrepancy_enum_and_dispositions_are_closed(self) -> None:
        self.assertEqual(
            archive.DISCREPANCY_CODES,
            (
                "ambiguous_legacy_candidate",
                "ignored_nonreview_verdict",
                "legacy_decision_shape",
                "missing_chain_artifact",
                "result_verdict_conflict",
                "snapshot_changed",
                "structured_chain_mismatch",
                "unbound_approval",
            ),
        )
        self.assertEqual(
            archive.AUTHORITATIVE_DISCREPANCIES,
            {
                "structured_chain_mismatch",
                "result_verdict_conflict",
                "unbound_approval",
                "missing_chain_artifact",
                "snapshot_changed",
            },
        )
        self.assertEqual(
            archive.LEGACY_DISPLAY_DISCREPANCIES,
            {
                "ambiguous_legacy_candidate",
                "ignored_nonreview_verdict",
                "legacy_decision_shape",
            },
        )
        for code in archive.AUTHORITATIVE_DISCREPANCIES:
            with self.subTest(code=code), self.assertRaisesRegex(
                archive.ArchiveRefusal,
                rf"^forge: archive refused — authoritative chain discrepancy: {code}$",
            ):
                archive.authoritative_discrepancy(code)

    def test_activated_mixed_structured_and_legacy_decision_is_reported(self) -> None:
        records = [
            {
                "_line": 7,
                "type": "decision",
                "id": "decision-01",
                "resolution": "Structured resolution",
                "decision": "Legacy decision prose",
            }
        ]

        discrepancies = archive.legacy_discrepancies(records, activated=True)

        self.assertEqual(
            [item.code for item in discrepancies], ["legacy_decision_shape"]
        )
        self.assertEqual(discrepancies[0].record_line, 7)

    def test_state_fence_preserves_missing_lf_and_uses_hostile_safe_width(self) -> None:
        raw = b'{"hostile":"`````","value":1}'
        digest = hashlib.sha256(raw).hexdigest()
        rendered = archive.render_chain_state_block(raw)
        self.assertEqual(
            rendered,
            f"<!-- FORGE:CHAIN-STATE v1 bytes={len(raw)} sha256={digest} fence=6 -->\n"
            "``````json\n"
            f"{raw.decode()}\n"
            "``````\n"
            "<!-- /FORGE:CHAIN-STATE -->\n",
        )
        opening, body = rendered.split("\n", 1)
        size = int(re.search(r"bytes=(\d+)", opening).group(1))
        encoded = body.split("\n", 1)[1].encode("utf-8")
        self.assertEqual(encoded[:size], raw)

    def test_event_embedding_zero_boundary_and_unembedded_fallback(self) -> None:
        empty = archive.render_chain_event_block(b"")
        self.assertEqual(
            empty,
            "<!-- FORGE:CHAIN-EVIDENCE v1 encoding=base64url bytes=0 "
            f"sha256={hashlib.sha256(b'').hexdigest()} -->\n\n"
            "<!-- /FORGE:CHAIN-EVIDENCE -->\n",
        )

        boundary = bytes(range(256)) * (archive.EVENT_EMBED_LIMIT // 256)
        rendered = archive.render_chain_event_block(boundary)
        lines = rendered.splitlines()
        self.assertIn("encoding=base64url", lines[0])
        self.assertNotIn("=", lines[1])
        padding = "=" * (-len(lines[1]) % 4)
        self.assertEqual(base64.urlsafe_b64decode(lines[1] + padding), boundary)

        oversized = boundary + b"x"
        fallback = archive.render_chain_event_block(oversized)
        self.assertEqual(
            fallback,
            "<!-- FORGE:CHAIN-EVIDENCE v1 encoding=UNEMBEDDED "
            f"bytes={len(oversized)} sha256={hashlib.sha256(oversized).hexdigest()} -->\n"
            "<!-- /FORGE:CHAIN-EVIDENCE -->\n",
        )

    def test_archive_utf8_cap_and_disable_control_are_load_bearing(self) -> None:
        with mock.patch.object(archive, "ARCHIVE_SIZE_LIMIT", 4):
            self.assertEqual(archive.enforce_archive_size("éé"), "éé".encode())
            with self.assertRaisesRegex(
                archive.ArchiveRefusal,
                "^forge: archive refused — rendered archive exceeds 16 MiB$",
            ):
                archive.enforce_archive_size("ééa")

        disabled = archive.RENDERER_CONTROLS - {"archive-size"}
        with mock.patch.object(archive, "RENDERER_CONTROLS", disabled):
            with self.assertRaisesRegex(
                archive.ArchiveRefusal,
                "^forge: archive refused — rendered archive exceeds 16 MiB$",
            ):
                archive.enforce_archive_size("")

    def test_legacy_table_prose_is_html_escaped_and_control_is_load_bearing(self) -> None:
        hostile = "<!-- FORGE:CHAIN-STATE --> <script>& |\nsecond"
        rendered = archive.table_cell(hostile)
        self.assertEqual(
            rendered,
            "&lt;!-- FORGE:CHAIN-STATE --&gt; &lt;script&gt;&amp; \\|<br>second",
        )
        self.assertNotIn("<!-- FORGE:CHAIN-STATE", rendered)
        self.assertNotIn("<script>", rendered)

        disabled = archive.RENDERER_CONTROLS - {"html-escape"}
        with mock.patch.object(archive, "RENDERER_CONTROLS", disabled):
            with self.assertRaisesRegex(
                archive.ArchiveRefusal,
                "^forge: archive refused — renderer escaping control unavailable$",
            ):
                archive.table_cell("legacy prose")

    def test_merge_reducer_is_delta_only_and_disabled_replay_fails_closed(self) -> None:
        at = "2026-08-28T12:00:00Z"
        chain_id = "c-2026-08-28T120000Z-abcd"
        event = {
            "event": "chain_started",
            "at": at,
            "payload": {
                "delta": {
                    "schema": "forge-merge-chain/1",
                    "chain_id": chain_id,
                    "kind": "merge",
                    "state": "classifying",
                }
            },
        }
        state = archive._merge_transition_reducer(None, event)
        self.assertEqual(state["last_event_at"], at)
        self.assertEqual(state["inactive_after"], "2026-08-29T12:00:00Z")
        self.assertIsNone(state["journal_outbox"])

        hostile = json.loads(json.dumps(event))
        hostile["payload"]["state"] = {"invented": "authority"}
        with self.assertRaisesRegex(ValueError, "explicit state delta"):
            archive._merge_transition_reducer(None, hostile)

        disabled = archive.RENDERER_CONTROLS - {"merge-reducer"}
        modern = {"run_binding": None, "journal_outbox": None}
        with mock.patch.object(archive, "RENDERER_CONTROLS", disabled), mock.patch.object(
            archive.journal_builders, "_resolve_binding_from_descriptor"
        ) as replay:
            with self.assertRaisesRegex(
                archive.ArchiveRefusal, "structured_chain_mismatch$"
            ):
                archive.replay_chain_state(
                    ROOT, -1, chain_id, modern, (), "merge"
                )
            replay.assert_not_called()

    def test_binding_only_control_and_authoritative_conflicts_fail_closed(self) -> None:
        disabled = archive.RENDERER_CONTROLS - {"binding-only"}
        with mock.patch.object(archive, "RENDERER_CONTROLS", disabled):
            with self.assertRaisesRegex(
                archive.ArchiveRefusal, "structured_chain_mismatch$"
            ):
                archive.required_binding_records([], True)

        unbound_approval = {
            "type": "decision",
            "id": "decision-01",
            "task": "task-01",
            "outcome": "chain-approval",
        }
        with self.assertRaisesRegex(archive.ArchiveRefusal, "unbound_approval$"):
            archive.required_binding_records([unbound_approval], True)

        conflict = {
            "type": "verification",
            "id": "check-01",
            "task": "task-01",
            "criterion": "gate-3: review-final verdict",
            "result": "failed",
            "binding": {"review": {"verdict": "PASS"}},
        }
        with self.assertRaisesRegex(
            archive.ArchiveRefusal, "result_verdict_conflict$"
        ):
            archive.required_binding_records([conflict], True)

        optional_chain = "c-2026-08-28T120000Z-abcd"
        optional_binding = {
            "type": "verification",
            "id": "check-02",
            "criterion": "diagnostic: retained chain fact",
            "result": "passed",
            "binding": {
                "source_record": {
                    "chain_id": optional_chain,
                    "event_digest": "1" * 64,
                }
            },
        }
        with mock.patch.object(
            archive.journal_engine, "_binding_shape_valid", return_value=True
        ):
            self.assertEqual(
                archive.binding_chain_ids([optional_binding], True),
                {optional_chain},
            )

    def test_legacy_review_prose_is_display_only_and_ambiguous_hashes_unbound(self) -> None:
        nonreview = {
            "type": "verification",
            "id": "check-09",
            "_line": 26,
            "criterion": "gate-2: STRICT evals",
            "check": "STRICT=1 run-evals.sh",
            "observation": "a review-cheap BLOCK named a planted defect",
        }
        discrepancies: list[object] = []
        self.assertEqual(
            archive.legacy_review_values(nonreview, discrepancies),
            (archive.NONE, archive.NONE, archive.NONE),
        )
        self.assertEqual([item.code for item in discrepancies], ["ignored_nonreview_verdict"])

        first = "1" * 64
        second = "2" * 64
        review = {
            "type": "verification",
            "id": "check-10",
            "_line": 29,
            "criterion": "gate-3: review-final verdict",
            "check": f"review-final over staged diff {first}; stale prose {second}",
            "result": "passed",
            "observation": (
                "PASS; 0 CRITICAL/MAJOR findings; severities "
                "CRITICAL=0,MAJOR=0,MINOR=1; reviewer review-final; "
                "iteration 2 of 8."
            ),
        }
        discrepancies = []
        self.assertEqual(
            archive.legacy_review_values(review, discrepancies),
            (archive.UNBOUND, "PASS", "2"),
        )
        self.assertEqual(
            [item.code for item in discrepancies], ["ambiguous_legacy_candidate"]
        )

        hostile = dict(review)
        hostile["check"] = f"documentation checksum {first}"
        hostile["observation"] = "quoted prose says PASS at iteration 7 of 8"
        discrepancies = []
        self.assertEqual(
            archive.legacy_review_values(hostile, discrepancies),
            (archive.UNBOUND, archive.UNBOUND, archive.UNBOUND),
        )
        self.assertEqual(
            [item.code for item in discrepancies], ["ambiguous_legacy_candidate"]
        )


class Revision9ChainSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="forge-r9-chain-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "--quiet"], cwd=self.repo, check=True)
        subprocess.run(
            ["git", "config", "user.name", "Revision Nine"], cwd=self.repo, check=True
        )
        subprocess.run(
            ["git", "config", "user.email", "r9@example.invalid"],
            cwd=self.repo,
            check=True,
        )
        (self.repo / "tracked").write_text("initial\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "--quiet", "-m", "initial"], cwd=self.repo, check=True)
        self.run_dir = self.root / "run-legacy"
        self.run_dir.mkdir()

    def write_legacy_chain(self, root: Path, chain_id: str, note: str) -> tuple[bytes, bytes]:
        root.mkdir(parents=True, exist_ok=True)
        state = {
            "schema": "forge-chain/1",
            "chain_id": chain_id,
            "kind": "commit",
            "state": "closed",
            "note": note,
        }
        state_raw = json.dumps(state, sort_keys=True).encode("utf-8")  # no final LF
        unsigned = {
            "sequence": 1,
            "prev_digest": "0" * 64,
            "payload": {
                "at": "2026-08-28T00:00:00Z",
                "details": {},
                "event": "chain_started",
                "state": state,
            },
        }
        event = {**unsigned, "digest": hashlib.sha256(canonical(unsigned)).hexdigest()}
        events_raw = canonical(event) + b"\n"
        (root / f"{chain_id}.json").write_bytes(state_raw)
        (root / f"{chain_id}.events.jsonl").write_bytes(events_raw)
        return state_raw, events_raw

    def write_captured_ingest(
        self,
        family: str,
        *,
        suffix: str,
        detail_size: int = 0,
    ) -> tuple[
        str,
        list[dict[str, object]],
        tuple[str, str, str],
        dict[str, object],
        dict[str, object],
    ]:
        chain_id = f"c-2026-08-28T01{suffix}00Z-{suffix.zfill(4)}"
        at = "2026-08-28T01:00:00Z"
        if family == "commit":
            state: dict[str, object] = {
                "schema": "forge-chain/1",
                "chain_id": chain_id,
                "kind": "commit",
                "state": "closed",
                "run_binding": None,
                "journal_outbox": None,
                "candidate": {"sha256": "a" * 64},
            }
            unsigned: dict[str, object] = {
                "sequence": 1,
                "prev_digest": "0" * 64,
                "payload": {
                    "at": at,
                    "details": {"fixture": "x" * detail_size},
                    "event": "commit_produced",
                    "state": state,
                },
            }
        else:
            unsigned = {
                "schema": "forge-merge-event/1",
                "chain_id": chain_id,
                "sequence": 1,
                "at": at,
                "event": "chain_started",
                "generation_digest": "b" * 64,
                "previous_digest": "0" * 64,
                "payload": {
                    "delta": {
                        "schema": "forge-merge-chain/1",
                        "chain_id": chain_id,
                        "kind": "merge",
                        "state": "closed",
                        "run": None,
                        "run_binding": None,
                        "candidate": {"generation_digest": "b" * 64},
                    }
                },
            }
            state = archive._merge_transition_reducer(None, unsigned)
        event = {
            **unsigned,
            "digest": hashlib.sha256(canonical(unsigned)).hexdigest(),
        }
        events_raw = canonical(event) + b"\n"
        state_raw = canonical(state)
        outcome_map: dict[str, object] = {
            "schema": "forge-chain-ingest-outcome-map/1",
            "chain_id": chain_id,
            "task": f"task-{suffix}",
            "task_status": "complete",
            "event_digests": [event["digest"]],
        }
        outcome_raw = canonical(outcome_map)
        citations: list[str] = []
        for name, raw in (
            ("state.json", state_raw),
            ("events.jsonl", events_raw),
            ("outcome-map.json", outcome_raw),
        ):
            digest = hashlib.sha256(raw).hexdigest()
            relative = (
                Path("captured")
                / "sha256"
                / digest
                / name
            )
            path = self.run_dir / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            citations.append(relative.as_posix())
        binding = {
            "schema": "forge-gate-binding/1",
            "source_record": {
                "chain_id": chain_id,
                "event_digest": event["digest"],
            },
            "candidate": {
                "kind": (
                    "staged-diff-sha256" if family == "commit" else "git-range"
                ),
                "value": (
                    "a" * 64
                    if family == "commit"
                    else {"base": "c" * 40, "head": "d" * 40}
                ),
            },
            "review": None,
        }
        binding["binding_id"] = hashlib.sha256(canonical(binding)).hexdigest()
        landing: dict[str, object] = {
            "_line": 11,
            "type": "decision",
            "id": "decision-01",
            "task": outcome_map["task"],
            "resolution": "captured fixture landing",
            "outcome": "chain-landing",
            "basis": citations,
            "binding": binding,
        }
        terminal: dict[str, object] = {
            "_line": 12,
            "type": "task",
            "id": outcome_map["task"],
            "status": "complete",
        }
        return (
            chain_id,
            [landing, terminal],
            (citations[0], citations[1], citations[2]),
            state,
            event,
        )

    def test_pre_activation_capture_replays_exact_bytes_and_detects_change(self) -> None:
        chain_id = "c-2026-08-28T000000Z-abcd"
        state_raw, events_raw = self.write_legacy_chain(
            self.run_dir / "chains", chain_id, "hostile ````` state"
        )
        package = archive.capture_chain_package(
            self.repo, self.run_dir, {chain_id}, activated=False
        )
        self.assertEqual(len(package.chains), 1)
        self.assertEqual(package.chains[0].state_file.raw, state_raw)
        self.assertEqual(package.chains[0].events_file.raw, events_raw)
        self.assertIn("fence=6", archive.render_chain_state_block(state_raw))

        (self.run_dir / "chains" / f"{chain_id}.json").write_bytes(state_raw + b" ")
        with self.assertRaisesRegex(archive.ArchiveRefusal, "snapshot_changed$"):
            archive.recheck_chain_package(package)

    def test_activated_capture_uses_repo_authority_and_only_cited_chain(self) -> None:
        cited = "c-2026-08-28T000001Z-abcd"
        unrelated = "c-2026-08-28T000002Z-abcd"
        repo_state, _ = self.write_legacy_chain(
            self.repo / ".forge" / "chains", cited, "repo authority"
        )
        self.write_legacy_chain(
            self.repo / ".forge" / "chains", unrelated, "must not embed"
        )
        self.write_legacy_chain(self.run_dir / "chains", cited, "stale run-local copy")

        package = archive.capture_chain_package(
            self.repo, self.run_dir, {cited}, activated=True
        )
        self.assertEqual([item.chain_id for item in package.chains], [cited])
        self.assertEqual(package.chains[0].state_file.raw, repo_state)

    def test_retrospective_commit_and_merge_replay_captured_packages(self) -> None:
        for family, suffix in (("commit", "01"), ("merge", "02")):
            with self.subTest(family=family):
                chain_id, records, citations, state, event = self.write_captured_ingest(
                    family, suffix=suffix
                )
                eligible = (
                    archive.EligibleIngestRecord(
                        str(event["digest"]), "decision", outcome="chain-landing"
                    ),
                )
                with mock.patch.object(
                    archive.journal_engine, "_binding_shape_valid", return_value=True
                ), mock.patch.object(
                    archive.journal_builders, "_state_shape_valid", return_value=True
                ), mock.patch.object(
                    archive.journal_builders,
                    "_commit_transition_valid",
                    return_value=True,
                ), mock.patch.object(
                    archive.journal_builders,
                    "_merge_transition_valid",
                    return_value=True,
                ), mock.patch.object(
                    archive,
                    "derive_captured_ingest_eligible_records",
                    return_value=eligible,
                ):
                    package = archive.capture_archive_chain_package(
                        self.repo,
                        self.run_dir,
                        records,
                        {chain_id},
                        activated=True,
                    )
                self.assertIsNone(package.root)
                self.assertEqual([item.chain_id for item in package.chains], [chain_id])
                self.assertEqual(package.chains[0].state, state)
                self.assertEqual(package.chains[0].events[0], event)
                self.assertEqual(package.captured[0].citations, citations)

                with mock.patch.object(
                    archive.journal_engine, "_binding_shape_valid", return_value=True
                ), mock.patch.object(
                    archive.journal_builders,
                    "_binding_matches_source_fact",
                    return_value=True,
                ) as source_fact, mock.patch.object(
                    archive.journal_builders,
                    "_binding_is_current",
                    return_value=True,
                ) as current_fact:
                    resolved = archive.resolve_archive_bindings(
                        self.repo,
                        self.run_dir,
                        records,
                        package,
                        True,
                    )
                self.assertEqual(resolved[11], records[0]["binding"])
                source_fact.assert_called_once()
                current_fact.assert_called_once()

                documents = archive.basis_documents(
                    self.repo, self.run_dir, [records[0]]
                )
                verbatim = archive.verbatim_basis_documents(package, documents)
                self.assertEqual([item.label for item in verbatim], [citations[2]])
                self.assertEqual(
                    set(archive.captured_chain_evidence_paths(package)),
                    {self.run_dir / citations[0], self.run_dir / citations[1]},
                )
                sections = "\n".join(
                    archive.render_chain_sections(package, records, resolved, [])
                )
                self.assertIn("<!-- FORGE:CHAIN-STATE v1", sections)
                self.assertIn("<!-- FORGE:CHAIN-EVIDENCE v1", sections)

    def test_captured_ingest_controls_and_path_grammar_fail_closed(self) -> None:
        chain_id, records, citations, _state, _event = self.write_captured_ingest(
            "commit", suffix="03"
        )
        with mock.patch.object(
            archive.journal_engine, "_binding_shape_valid", return_value=True
        ):
            disabled = archive.RENDERER_CONTROLS - {
                "captured-ingest-classification"
            }
            with mock.patch.object(archive, "RENDERER_CONTROLS", disabled):
                with self.assertRaisesRegex(
                    archive.ArchiveRefusal, "structured_chain_mismatch$"
                ):
                    archive.classify_captured_ingest_citations(
                        self.run_dir, records, {chain_id}
                    )

            for mutation in ("reordered", "repository-relative"):
                hostile = json.loads(json.dumps(records))
                if mutation == "reordered":
                    hostile[0]["basis"][0], hostile[0]["basis"][1] = (
                        hostile[0]["basis"][1],
                        hostile[0]["basis"][0],
                    )
                else:
                    hostile[0]["basis"][0] = (
                        f".codex-orchestrator/runs/{self.run_dir.name}/"
                        f"{hostile[0]['basis'][0]}"
                    )
                with self.subTest(mutation=mutation), self.assertRaisesRegex(
                    archive.ArchiveRefusal, "structured_chain_mismatch$"
                ):
                    archive.classify_captured_ingest_citations(
                        self.run_dir, hostile, {chain_id}
                    )

        wrong_digest = list(citations)
        state_bytes = (self.run_dir / citations[0]).read_bytes()
        wrong_digest[0] = str(
            Path(citations[0]).parents[1] / ("0" * 64) / "state.json"
        )
        wrong_path = self.run_dir / wrong_digest[0]
        wrong_path.parent.mkdir(parents=True, exist_ok=True)
        wrong_path.write_bytes(state_bytes)
        with self.assertRaisesRegex(
            archive.ArchiveRefusal, "structured_chain_mismatch$"
        ):
            archive.capture_captured_ingest_packages(
                self.repo, self.run_dir, {chain_id: tuple(wrong_digest)}
            )

    def test_captured_replay_binding_and_snapshot_controls_are_load_bearing(self) -> None:
        chain_id, records, _citations, _state, event = self.write_captured_ingest(
            "merge", suffix="04"
        )
        eligible = (
            archive.EligibleIngestRecord(
                str(event["digest"]), "decision", outcome="chain-landing"
            ),
        )
        with mock.patch.object(
            archive.journal_engine, "_binding_shape_valid", return_value=True
        ), mock.patch.object(
            archive.journal_builders, "_state_shape_valid", return_value=True
        ), mock.patch.object(
            archive.journal_builders, "_merge_transition_valid", return_value=True
        ), mock.patch.object(
            archive,
            "derive_captured_ingest_eligible_records",
            return_value=eligible,
        ):
            package = archive.capture_archive_chain_package(
                self.repo,
                self.run_dir,
                records,
                {chain_id},
                activated=True,
            )
        captured = package.captured[0]

        disabled = archive.RENDERER_CONTROLS - {"captured-ingest-eligibility"}
        with mock.patch.object(archive, "RENDERER_CONTROLS", disabled):
            with self.assertRaisesRegex(
                archive.ArchiveRefusal, "structured_chain_mismatch$"
            ):
                archive.derive_captured_ingest_eligible_records(
                    self.repo,
                    captured.chain.state,
                    captured.replay_entries,
                    "merge",
                    "task-04",
                )

        disabled = archive.RENDERER_CONTROLS - {"captured-ingest-replay"}
        with mock.patch.object(archive, "RENDERER_CONTROLS", disabled):
            with self.assertRaisesRegex(
                archive.ArchiveRefusal, "structured_chain_mismatch$"
            ):
                archive.replay_captured_unbound_chain(
                    chain_id,
                    captured.chain.state,
                    captured.chain.events,
                    "merge",
                )

        disabled = archive.RENDERER_CONTROLS - {"captured-ingest-binding"}
        with mock.patch.object(
            archive, "RENDERER_CONTROLS", disabled
        ), mock.patch.object(
            archive.journal_engine, "_binding_shape_valid", return_value=True
        ):
            with self.assertRaisesRegex(
                archive.ArchiveRefusal, "structured_chain_mismatch$"
            ):
                archive.resolve_archive_bindings(
                    self.repo, self.run_dir, records, package, True
                )

        stale = json.loads(json.dumps(records))
        stale[0]["binding"]["source_record"]["event_digest"] = "f" * 64
        with mock.patch.object(
            archive.journal_engine, "_binding_shape_valid", return_value=True
        ), self.assertRaisesRegex(
            archive.ArchiveRefusal, "structured_chain_mismatch$"
        ):
            archive.resolve_archive_bindings(
                self.repo, self.run_dir, stale, package, True
            )

        state_path = package.captured[0].documents[0].path
        state_path.write_bytes(state_path.read_bytes() + b" ")
        with self.assertRaisesRegex(archive.ArchiveRefusal, "snapshot_changed$"):
            archive.recheck_captured_ingest_packages(package)

    def test_captured_merge_payload_state_is_never_authority(self) -> None:
        chain_id, records, _citations, _state, event = self.write_captured_ingest(
            "merge", suffix="05"
        )
        eligible = (
            archive.EligibleIngestRecord(
                str(event["digest"]), "decision", outcome="chain-landing"
            ),
        )
        with mock.patch.object(
            archive.journal_engine, "_binding_shape_valid", return_value=True
        ), mock.patch.object(
            archive.journal_builders, "_state_shape_valid", return_value=True
        ), mock.patch.object(
            archive.journal_builders, "_merge_transition_valid", return_value=True
        ), mock.patch.object(
            archive,
            "derive_captured_ingest_eligible_records",
            return_value=eligible,
        ):
            package = archive.capture_archive_chain_package(
                self.repo,
                self.run_dir,
                records,
                {chain_id},
                activated=True,
            )
        captured = package.captured[0]
        hostile = json.loads(json.dumps(captured.chain.events[0]))
        hostile["payload"]["state"] = captured.chain.state
        with mock.patch.object(
            archive.journal_builders, "_state_shape_valid", return_value=True
        ), self.assertRaisesRegex(
            archive.ArchiveRefusal, "structured_chain_mismatch$"
        ):
            archive.replay_captured_unbound_chain(
                chain_id,
                captured.chain.state,
                (hostile,),
                "merge",
            )

    def test_oversized_captured_events_are_not_duplicated_as_basis(self) -> None:
        chain_id, records, citations, _state, event = self.write_captured_ingest(
            "commit", suffix="06", detail_size=archive.EVENT_EMBED_LIMIT
        )
        eligible = (
            archive.EligibleIngestRecord(
                str(event["digest"]), "decision", outcome="chain-landing"
            ),
        )
        with mock.patch.object(
            archive.journal_engine, "_binding_shape_valid", return_value=True
        ), mock.patch.object(
            archive.journal_builders, "_state_shape_valid", return_value=True
        ), mock.patch.object(
            archive.journal_builders, "_commit_transition_valid", return_value=True
        ), mock.patch.object(
            archive,
            "derive_captured_ingest_eligible_records",
            return_value=eligible,
        ):
            package = archive.capture_archive_chain_package(
                self.repo,
                self.run_dir,
                records,
                {chain_id},
                activated=True,
            )
        events_raw = package.chains[0].events_file.raw
        self.assertGreater(len(events_raw), archive.EVENT_EMBED_LIMIT)
        self.assertIn("encoding=UNEMBEDDED", archive.render_chain_event_block(events_raw))
        documents = archive.basis_documents(self.repo, self.run_dir, [records[0]])
        self.assertEqual(
            [item.label for item in archive.verbatim_basis_documents(package, documents)],
            [citations[2]],
        )

    def test_carried_record_requires_exact_canonical_key_set_and_values(self) -> None:
        binding = {
            "schema": "forge-journal-binding/1",
            "binding_id": "b-" + "1" * 64,
            "source_record": {
                "chain_id": "c-2026-08-28T000010Z-abcd",
                "event_digest": "2" * 64,
            },
        }
        record = {
            "_line": 7,
            "type": "verification",
            "id": "check-01",
            "criterion": "gate-1: tests",
            "result": "passed",
            "binding": binding,
        }
        carried = {name: value for name, value in record.items() if name != "_line"}
        identity = archive.FileIdentity(1, 2, 0, os.geteuid(), 1, 0, 0)

        def snapshot(candidate: dict[str, object]) -> object:
            event = {
                "payload": {"details": {"journal_batch": {"records": [candidate]}}}
            }
            return archive.ChainSnapshot(
                "c-2026-08-28T000010Z-abcd",
                archive.ExactFile("state", b"", identity),
                archive.ExactFile("events", b"", identity),
                {},
                (event,),
                "commit",
                "2" * 64,
                None,
                None,
            )

        archive.require_exact_carried_record(
            snapshot(carried), binding["binding_id"], record
        )
        with self.assertRaisesRegex(
            archive.ArchiveRefusal, "structured_chain_mismatch$"
        ):
            archive.require_exact_carried_record(
                snapshot({**carried, "unexpected": None}),
                binding["binding_id"],
                record,
            )

        disabled = archive.RENDERER_CONTROLS - {"carried-record-equality"}
        with mock.patch.object(archive, "RENDERER_CONTROLS", disabled):
            with self.assertRaisesRegex(
                archive.ArchiveRefusal, "structured_chain_mismatch$"
            ):
                archive.require_exact_carried_record(
                    snapshot(carried), binding["binding_id"], record
                )

    def test_archive_creation_is_no_follow_and_rollback_preserves_replacement(self) -> None:
        relative = ".forge/history/runs/run-race.md"
        archive_path = self.repo / relative
        exact = archive.create_archive_file(
            self.repo, archive_path, relative, "created\n"
        )
        archive_path.unlink()
        archive_path.write_text("concurrent replacement\n", encoding="utf-8")
        with self.assertRaisesRegex(
            archive.ArchiveRefusal,
            "^forge: archive refused — transaction rollback failed$",
        ):
            archive.unlink_archive_candidate(self.repo, relative, exact)
        self.assertEqual(
            archive_path.read_text(encoding="utf-8"), "concurrent replacement\n"
        )

    def test_quarantine_rollback_preserves_replacement_appearing_after_rename(self) -> None:
        relative = ".forge/history/runs/run-post-rename-race.md"
        archive_path = self.repo / relative
        exact = archive.create_archive_file(
            self.repo, archive_path, relative, "created\n"
        )
        real_rename = archive.os.rename

        def rename_then_replace(*arguments: object, **keywords: object) -> None:
            real_rename(*arguments, **keywords)
            archive_path.write_text("post-rename replacement\n", encoding="utf-8")

        with mock.patch.object(
            archive.os, "rename", side_effect=rename_then_replace
        ), self.assertRaisesRegex(
            archive.ArchiveRefusal,
            "^forge: archive refused — transaction rollback failed$",
        ):
            archive.unlink_archive_candidate(self.repo, relative, exact)
        self.assertEqual(
            archive_path.read_text(encoding="utf-8"),
            "post-rename replacement\n",
        )
        self.assertEqual(
            list(archive_path.parent.glob(f".{archive_path.name}.rollback-*")),
            [],
        )

    def test_archive_creation_refuses_symlinked_owner_parent(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        os.symlink(outside, self.repo / ".forge")
        relative = ".forge/history/runs/run-symlink.md"
        with self.assertRaisesRegex(
            archive.ArchiveRefusal,
            "^forge: archive refused — unsafe archive parent$",
        ):
            archive.create_archive_file(
                self.repo, self.repo / relative, relative, "candidate\n"
            )
        self.assertFalse((outside / "history" / "runs" / "run-symlink.md").exists())

    def test_matching_untracked_candidate_is_staged_and_equality_control_is_live(self) -> None:
        relative = ".forge/history/runs/run-pre-rendered.md"
        candidate = self.repo / relative
        candidate.parent.mkdir(parents=True)
        candidate.write_bytes(b"exact candidate\n")
        snapshot = archive.untracked_archive_snapshot(
            self.repo, candidate, relative
        )
        self.assertIsNotNone(snapshot)
        archive.prove_clean_with_untracked_archive(self.repo, relative)

        disabled = archive.RENDERER_CONTROLS - {"candidate-rerender"}
        with mock.patch.object(archive, "RENDERER_CONTROLS", disabled):
            with self.assertRaisesRegex(
                archive.ArchiveRefusal, "differs from deterministic rerender"
            ):
                archive.write_and_stage(
                    self.repo,
                    relative,
                    "exact candidate\n",
                    preexisting=snapshot,
                )
        self.assertEqual(
            subprocess.run(
                ["git", "diff", "--cached", "--name-only"],
                cwd=self.repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout,
            "",
        )

        archive.write_and_stage(
            self.repo,
            relative,
            "exact candidate\n",
            preexisting=snapshot,
        )
        self.assertEqual(candidate.read_bytes(), b"exact candidate\n")
        self.assertEqual(
            subprocess.run(
                ["git", "diff", "--cached", "--name-only"],
                cwd=self.repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout,
            relative + "\n",
        )

    def test_basis_document_snapshot_is_exact_and_disable_detected(self) -> None:
        basis = self.run_dir / "plan.md"
        basis.write_bytes(b"plan bytes without final LF")
        decisions = [{"type": "decision", "basis": ["plan.md"]}]
        documents = archive.basis_documents(self.repo, self.run_dir, decisions)
        self.assertEqual(documents[0].exact.raw, b"plan bytes without final LF")

        basis.write_bytes(b"changed")
        with self.assertRaisesRegex(
            archive.ArchiveRefusal, "basis document changed during rendering"
        ):
            archive.recheck_basis_documents(documents)

        disabled = archive.RENDERER_CONTROLS - {"basis-snapshot"}
        with mock.patch.object(archive, "RENDERER_CONTROLS", disabled):
            with self.assertRaisesRegex(archive.ArchiveRefusal, "unsafe basis document"):
                archive.basis_documents(self.repo, self.run_dir, decisions)

    def test_missing_artifact_and_disabled_snapshot_replay_controls_fail_closed(self) -> None:
        chain_id = "c-2026-08-28T000003Z-abcd"
        with self.assertRaisesRegex(archive.ArchiveRefusal, "missing_chain_artifact$"):
            archive.capture_chain_package(
                self.repo, self.run_dir, {chain_id}, activated=True
            )

        self.write_legacy_chain(self.run_dir / "chains", chain_id, "state")
        disabled = archive.RENDERER_CONTROLS - {"chain-snapshot"}
        with mock.patch.object(archive, "RENDERER_CONTROLS", disabled):
            with self.assertRaisesRegex(
                archive.ArchiveRefusal, "missing_chain_artifact$"
            ):
                archive.capture_chain_package(
                    self.repo, self.run_dir, {chain_id}, activated=False
                )

        event_raw = (self.run_dir / "chains" / f"{chain_id}.events.jsonl").read_bytes()
        disabled = archive.RENDERER_CONTROLS - {"chain-replay"}
        with mock.patch.object(archive, "RENDERER_CONTROLS", disabled):
            with self.assertRaisesRegex(
                archive.ArchiveRefusal, "structured_chain_mismatch$"
            ):
                archive.decode_event_log(chain_id, event_raw)


class Revision9RealIngestArchiveTests(CLI_FIXTURE_SUPPORT.ForgeCLIFixture):
    @contextlib.contextmanager
    def cli_context(self, cli: object):
        environment = self.environment(FORGE_SESSION_PID=str(os.getpid()))
        with mock.patch.dict(os.environ, environment, clear=True), mock.patch.object(
            cli, "SCRIPT_DIR", self.helpers
        ), mock.patch.object(cli, "PLUGIN_ROOT", ROOT), mock.patch.object(
            cli, "CODEX_EXECUTABLE", str(self.helpers / "fake-codex")
        ):
            yield

    def invoke_cli(self, cli: object, *argv: str) -> dict[str, object]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with self.cli_context(cli), contextlib.redirect_stdout(
            stdout
        ), contextlib.redirect_stderr(stderr):
            exit_code = cli.main(["--json", "--repo", str(self.repo), *argv])
        self.assertEqual(exit_code, 0, stderr.getvalue() or stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")
        return json.loads(stdout.getvalue())

    def test_real_cli_ingest_archive_replay_rejects_joint_truncation(self) -> None:
        cli = archive._load_cli_ingest_authority()
        archive._CLI_INGEST_AUTHORITY = cli
        self.change("docs/guide.md", "# Real retrospective archive fixture\n")
        started = self.invoke_cli(
            cli, "commit", "start", "--paths", "docs/guide.md"
        )
        chain_id = str(started["chain_id"])
        verified = self.invoke_cli(cli, "--chain-id", chain_id, "verify")
        self.assertEqual(verified["state"], "authorized")
        finalized = self.invoke_cli(
            cli,
            "--chain-id",
            chain_id,
            "commit",
            "finalize",
            "--message",
            "Create real retrospective archive fixture",
        )
        self.assertEqual(finalized["state"], "closed")

        state_raw = self.state_path(chain_id).read_bytes()
        events_raw = self.events_path(chain_id).read_bytes()
        state = json.loads(state_raw)
        events, family, _first, _last = archive.decode_event_log(
            chain_id, events_raw
        )
        replay_entries = archive.replay_captured_unbound_chain(
            chain_id, state, events, family
        )
        eligible = archive.derive_captured_ingest_eligible_records(
            self.repo, state, replay_entries, family, "task-01"
        )
        selected: list[str] = []
        for item in eligible:
            if item.event_digest not in selected:
                selected.append(item.event_digest)
        self.assertGreater(len(selected), 1)

        run_id = "run-20260828-real-archive-ingest"
        cli.register_coordination_seams()
        _batch, builders, _journal = cli._coordination_modules()
        with self.cli_context(cli):
            builders.run_open(
                self.repo,
                run_id,
                idempotency_key=hashlib.sha256(b"archive-real-open").hexdigest(),
                goal="Archive one real retrospective ingest",
                scope=["docs/**"],
                plugin_ref="forge-revision9-archive-tests",
            )
            builders.task_start(
                self.repo,
                run_id,
                idempotency_key=hashlib.sha256(b"archive-real-task").hexdigest(),
                task="task-01",
                goal="Bind the real unbound commit chain",
                acceptance=["Captured replay and bindings resolve"],
                files=["docs/guide.md"],
            )
        external = self.repo / "external"
        external.mkdir()
        outcome_map = {
            "schema": "forge-chain-ingest-outcome-map/1",
            "chain_id": chain_id,
            "task": "task-01",
            "task_status": "complete",
            "event_digests": selected,
        }
        sources = {
            "state-file": ("external/state.json", state_raw),
            "events-file": ("external/events.jsonl", events_raw),
            "outcome-map": ("external/outcome-map.json", canonical(outcome_map) + b"\n"),
        }
        for _field, (relative, raw) in sources.items():
            (self.repo / relative).write_bytes(raw)
        closing_head = self.git("rev-parse", "HEAD")
        self.invoke_cli(
            cli,
            "--run-id",
            run_id,
            "journal",
            "ingest-chain",
            "--task",
            "task-01",
            "--state-file",
            sources["state-file"][0],
            "--events-file",
            sources["events-file"][0],
            "--outcome-map",
            sources["outcome-map"][0],
            "--closing-head",
            closing_head,
            "--task-status",
            "complete",
            "--idempotency-key",
            hashlib.sha256(b"archive-real-ingest").hexdigest(),
        )

        run_dir = self.repo / ".codex-orchestrator" / "runs" / run_id
        records, _journal_raw = archive.stable_journal_snapshot(run_dir)
        package = archive.capture_archive_chain_package(
            self.repo, run_dir, records, {chain_id}, activated=True
        )
        resolved = archive.resolve_archive_bindings(
            self.repo, run_dir, records, package, True
        )
        self.assertEqual(len(resolved), len(eligible))
        self.assertEqual(package.captured[0].eligible_records, eligible)

        # A mutually consistent captured package, outcome map, and journal
        # still cannot erase an invariant required by the committed policy.
        # Keep every later native state replay-valid while removing it.
        omitted_step = "invariant:1"
        self.assertIn(omitted_step, state["steps"])
        omitted_digest = next(
            str(event["digest"])
            for event in events
            if event["payload"]["event"] == "step_recorded"
            and event["payload"]["details"].get("step_id") == omitted_step
            and str(event["digest"]) in selected
        )

        def without_gate(value: dict[str, object]) -> dict[str, object]:
            result = copy.deepcopy(value)
            result["steps"].pop(omitted_step, None)
            return result

        digest_map: dict[str, str] = {}
        omitted_events: list[dict[str, object]] = []
        previous_digest = "0" * 64
        for source_event in events:
            old_digest = str(source_event["digest"])
            payload = copy.deepcopy(source_event["payload"])
            if (
                payload["event"] == "step_recorded"
                and payload["details"].get("step_id") == omitted_step
            ):
                continue
            payload["state"] = without_gate(payload["state"])
            unsigned = {
                "sequence": len(omitted_events) + 1,
                "prev_digest": previous_digest,
                "payload": payload,
            }
            rewritten = {
                **unsigned,
                "digest": hashlib.sha256(canonical(unsigned)).hexdigest(),
            }
            digest_map[old_digest] = str(rewritten["digest"])
            previous_digest = str(rewritten["digest"])
            omitted_events.append(rewritten)
        omitted_state = without_gate(state)
        omitted_events_raw = b"".join(
            canonical(event) + b"\n" for event in omitted_events
        )
        replayed_events, omitted_family, _first, _last = archive.decode_event_log(
            chain_id, omitted_events_raw
        )
        omitted_replay = archive.replay_captured_unbound_chain(
            chain_id, omitted_state, replayed_events, omitted_family
        )
        with self.assertRaisesRegex(
            archive.ArchiveRefusal, "structured_chain_mismatch$"
        ):
            archive.derive_captured_ingest_eligible_records(
                self.repo,
                omitted_state,
                omitted_replay,
                omitted_family,
                "task-01",
            )

        omitted_map = copy.deepcopy(outcome_map)
        omitted_map["event_digests"] = [
            digest_map[digest]
            for digest in selected
            if digest != omitted_digest
        ]
        omitted_documents = (
            ("state.json", canonical(omitted_state) + b"\n"),
            ("events.jsonl", omitted_events_raw),
            ("outcome-map.json", canonical(omitted_map) + b"\n"),
        )
        omitted_citations: list[str] = []
        for name, raw in omitted_documents:
            digest = hashlib.sha256(raw).hexdigest()
            relative = (
                Path(".codex-orchestrator")
                / "runs"
                / run_id
                / "captured"
                / "sha256"
                / digest
                / name
            )
            destination = self.repo / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
            omitted_citations.append(relative.as_posix())
        omitted_records = copy.deepcopy(records)
        omitted_records = [
            record
            for record in omitted_records
            if not (
                isinstance(record.get("binding"), dict)
                and record["binding"].get("source_record", {}).get("event_digest")
                == omitted_digest
            )
        ]
        for record in omitted_records:
            binding = record.get("binding")
            source = binding.get("source_record") if isinstance(binding, dict) else None
            old_digest = source.get("event_digest") if isinstance(source, dict) else None
            if isinstance(old_digest, str) and old_digest in digest_map:
                source["event_digest"] = digest_map[old_digest]
                preimage = {
                    key: copy.deepcopy(value)
                    for key, value in binding.items()
                    if key != "binding_id"
                }
                binding["binding_id"] = hashlib.sha256(canonical(preimage)).hexdigest()
            if record.get("outcome") == "chain-landing":
                record["basis"] = omitted_citations
        with self.assertRaisesRegex(
            archive.ArchiveRefusal, "structured_chain_mismatch$"
        ):
            archive.capture_archive_chain_package(
                self.repo,
                run_dir,
                omitted_records,
                {chain_id},
                activated=True,
            )

        omitted = eligible[0].event_digest
        truncated_records = copy.deepcopy(records)
        truncated_records = [
            record
            for record in truncated_records
            if not (
                isinstance(record.get("binding"), dict)
                and record["binding"].get("source_record", {}).get("event_digest")
                == omitted
            )
        ]
        truncated_map = copy.deepcopy(outcome_map)
        truncated_map["event_digests"] = [
            digest for digest in selected if digest != omitted
        ]
        truncated_raw = canonical(truncated_map) + b"\n"
        truncated_digest = hashlib.sha256(truncated_raw).hexdigest()
        truncated_relative = (
            Path(".codex-orchestrator")
            / "runs"
            / run_id
            / "captured"
            / "sha256"
            / truncated_digest
            / "outcome-map.json"
        )
        truncated_path = self.repo / truncated_relative
        truncated_path.parent.mkdir(parents=True)
        truncated_path.write_bytes(truncated_raw)
        landing = next(
            record
            for record in truncated_records
            if record.get("outcome") == "chain-landing"
        )
        landing["basis"][2] = truncated_relative.as_posix()
        with self.assertRaisesRegex(
            archive.ArchiveRefusal, "structured_chain_mismatch$"
        ):
            archive.capture_archive_chain_package(
                self.repo,
                run_dir,
                truncated_records,
                {chain_id},
                activated=True,
            )


class Revision9LegacyClosingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="forge-r9-legacy-")
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name) / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "--quiet"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.name", "Recovery"], cwd=self.repo, check=True)
        subprocess.run(
            ["git", "config", "user.email", "recovery@example.invalid"],
            cwd=self.repo,
            check=True,
        )
        (self.repo / "tracked").write_text("initial\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "--quiet", "-m", "initial"], cwd=self.repo, check=True)
        self.head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        runs = self.repo / ".codex-orchestrator" / "runs"
        self.target = runs / "legacy-target"
        self.recovery = runs / "recovery-run"
        self.resolution = (
            f"legacy-archive-recovery: legacy-target recovered closing HEAD {self.head}; "
            "operator recovered the closed implementation state"
        )
        self.environment = mock.patch.dict(
            os.environ, {"FORGE_SESSION_PID": str(os.getpid())}
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        archive.journal_builders.run_open(
            self.repo,
            "recovery-run",
            idempotency_key=hashlib.sha256(b"open recovery run").hexdigest(),
            goal="Approve one legacy archive recovery",
            scope=["recovery/**"],
            plugin_ref="forge-test-revision-9",
        )
        decision = archive.journal_builders.decision_add(
            self.repo,
            "recovery-run",
            idempotency_key=hashlib.sha256(b"approve legacy recovery").hexdigest(),
            resolution=self.resolution,
            task=None,
            finding=None,
            outcome="operator_approval",
            risk=None,
            basis=(),
            binding_chain=None,
            binding_id=None,
        )
        self.decision_id = decision.records[0]["id"]
        self.approval = f"recovery-run:{self.decision_id}"
        self.target.mkdir()
        self.write_journal(
            self.target,
            [
                {
                    "type": "run_started",
                    "run_id": "legacy-target",
                    "repo": str(self.repo),
                    "repo_head": self.head,
                    "goal": "Preserve a historical closed run",
                    "scope": ["legacy/**"],
                },
                {"type": "run_closed", "judgment": "passed"},
            ],
        )

    @staticmethod
    def write_journal(run_dir: Path, records: list[dict[str, object]]) -> None:
        (run_dir / "journal.jsonl").write_bytes(
            b"".join(canonical(record) + b"\n" for record in records)
        )

    def test_exact_approval_grammar_resolves_and_mismatch_has_one_literal(self) -> None:
        mode = archive.legacy_closing_mode(
            repo=self.repo,
            target_run_dir=self.target,
            recovered_head=self.head,
            approval=self.approval,
            prove_approval=True,
        )
        self.assertEqual(mode, archive.ClosingMode(self.head, self.approval))

        records, _ = archive.stable_journal_snapshot(self.recovery)
        records = [
            {name: value for name, value in record.items() if name != "_line"}
            for record in records
        ]
        approval_record = next(
            record for record in records if record.get("id") == self.decision_id
        )
        approval_record["resolution"] = self.resolution + "\nsecond line"
        self.write_journal(self.recovery, records)
        with self.assertRaisesRegex(
            archive.ArchiveRefusal,
            "^forge: archive refused — legacy recovery approval missing or mismatched$",
        ):
            archive.legacy_closing_mode(
                repo=self.repo,
                target_run_dir=self.target,
                recovered_head=self.head,
                approval=self.approval,
                prove_approval=True,
            )

    def test_legacy_approval_disable_control_is_detected(self) -> None:
        disabled = archive.RENDERER_CONTROLS - {"legacy-approval"}
        with mock.patch.object(archive, "RENDERER_CONTROLS", disabled):
            with self.assertRaisesRegex(
                archive.ArchiveRefusal,
                "legacy recovery approval missing or mismatched$",
            ):
                archive.legacy_closing_mode(
                    repo=self.repo,
                    target_run_dir=self.target,
                    recovered_head=self.head,
                    approval=self.approval,
                    prove_approval=True,
                )

    def test_recovery_approval_requires_current_open_activated_owner(self) -> None:
        (self.recovery / "owner").unlink()
        with self.assertRaisesRegex(
            archive.ArchiveRefusal,
            "^forge: archive refused — legacy recovery approval missing or mismatched$",
        ):
            archive.legacy_closing_mode(
                repo=self.repo,
                target_run_dir=self.target,
                recovered_head=self.head,
                approval=self.approval,
                prove_approval=True,
            )


class Revision9Phase0GoldenTests(unittest.TestCase):
    def test_real_hardening_journal_is_unbound_without_changing_committed_history(self) -> None:
        run_id = "run-20260826-coordination-hardening"
        run_dir = ROOT / ".codex-orchestrator" / "runs" / run_id
        archive_relative = f".forge/history/runs/{run_id}.md"
        source_before = (run_dir / "journal.jsonl").read_bytes()
        committed_before = subprocess.run(
            ["git", "show", f"HEAD:{archive_relative}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout
        self.assertEqual(
            hashlib.sha256(committed_before).hexdigest(), HARDENING_ARCHIVE_SHA
        )

        real_run_git = archive.run_git

        def absent_for_pure_rerender(repo: Path, *arguments: str) -> object:
            if arguments == (
                "ls-tree",
                "-z",
                "--name-only",
                "HEAD",
                "--",
                archive_relative,
            ):
                return subprocess.CompletedProcess(
                    ["git", *arguments], 0, b"", b""
                )
            return real_run_git(repo, *arguments)

        # The checked-in archive is immutable.  For renderer regression only,
        # isolate the high-level absent-from-HEAD predicate; no destination is
        # created or replaced and every journal/chain proof still executes.
        with mock.patch.object(
            archive, "run_git", side_effect=absent_for_pure_rerender
        ):
            rendered = archive.render_archive_candidate(
                repo=ROOT,
                run_dir=run_dir,
                closing_head=HARDENING_HEAD,
                legacy_recovered_head=None,
                legacy_approval=None,
                post_close_validation=run_dir / "post-close-validation.json",
            )
        self.assertEqual(
            hashlib.sha256(rendered).hexdigest(),
            "be53b308502d7a0359216142be41b59c3694032a0790a7c1c0cb221b9ef5d7e8",
        )
        text = rendered.decode("utf-8")
        self.assertEqual(text.count(f"Closing HEAD: {HARDENING_HEAD}"), 1)
        self.assertNotIn("Legacy recovered closing HEAD:", text)
        first_review = next(
            line
            for line in text.splitlines()
            if line.startswith("| gate-3: review-final verdict")
        )
        self.assertIn("| UNBOUND | passed | PASS | 2 | UNBOUND | UNBOUND |", first_review)
        self.assertIn("`ambiguous_legacy_candidate`", text)
        for line in text.splitlines():
            if line.startswith(("| gate-1: ", "| gate-2: ")):
                self.assertIn(
                    "| passed | None recorded | None recorded | UNBOUND | UNBOUND |",
                    line,
                )

        self.assertEqual((run_dir / "journal.jsonl").read_bytes(), source_before)
        committed_after = subprocess.run(
            ["git", "show", f"HEAD:{archive_relative}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout
        self.assertEqual(committed_after, committed_before)
        self.assertEqual(
            hashlib.sha256(committed_after).hexdigest(), HARDENING_ARCHIVE_SHA
        )

    def test_real_phase0_preview_is_deterministic_and_never_misattributes_verdicts(self) -> None:
        run_dir = ROOT / ".codex-orchestrator" / "runs" / "run-20260821-phase0-evals"
        rendered = archive.preview_legacy_archive_candidate(
            repo=ROOT,
            run_dir=run_dir,
            legacy_recovered_head=PHASE0_HEAD,
            proposed_legacy_approval=PHASE0_APPROVAL,
            post_close_validation=run_dir / "post-close-validation.json",
        )
        self.assertEqual(
            hashlib.sha256(rendered).hexdigest(),
            "44cbad0018b7fb81482073cbdc0864ee19b0e59bac608b86af07c61b361d735f",
        )
        text = rendered.decode("utf-8")
        self.assertIn("### decision-05", text)
        self.assertIn("Decision (legacy field):", text)
        self.assertIn("Physical journal line: 40", text)
        raw_line = (run_dir / "journal.jsonl").read_bytes().splitlines(keepends=True)[39]
        self.assertIn(f"Raw-line SHA-256: {hashlib.sha256(raw_line).hexdigest()}", text)
        self.assertIn(
            f"Legacy recovered closing HEAD: {PHASE0_HEAD}", text
        )
        self.assertIn(f"Legacy recovery approval: {PHASE0_APPROVAL}", text)
        self.assertEqual(
            text.count(f"Legacy recovered closing HEAD: {PHASE0_HEAD}"), 1
        )
        self.assertEqual(
            text.count(f"Legacy recovery approval: {PHASE0_APPROVAL}"), 1
        )
        self.assertNotIn(f"Closing HEAD: {PHASE0_HEAD}", text)
        self.assertIn("`legacy_decision_shape`", text)
        self.assertIn("`ignored_nonreview_verdict`", text)
        self.assertIn(
            "| gate-2: STRICT evals with recorded baselines | "
            "STRICT=1 bash scripts/forge/run-evals.sh (exit read directly) | "
            "None recorded | passed | None recorded | None recorded | UNBOUND | UNBOUND |",
            text,
        )

    def test_authoritative_renderer_does_not_accept_a_proposed_approval(self) -> None:
        run_dir = ROOT / ".codex-orchestrator" / "runs" / "run-20260821-phase0-evals"
        with self.assertRaisesRegex(
            archive.ArchiveRefusal,
            "^forge: archive refused — legacy recovery approval missing or mismatched$",
        ):
            archive.render_archive_candidate(
                repo=ROOT,
                run_dir=run_dir,
                closing_head=None,
                legacy_recovered_head=PHASE0_HEAD,
                legacy_approval=PHASE0_APPROVAL,
                post_close_validation=run_dir / "post-close-validation.json",
            )


if __name__ == "__main__":
    unittest.main()
