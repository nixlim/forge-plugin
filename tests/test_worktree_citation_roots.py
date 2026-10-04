"""Worktree coverage for the shared FR-017 citation-root predicate."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests._cli_loader import load_script

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "forge"))

import commitment_paths  # noqa: E402
from codex_orchestrator import close_law, journal  # noqa: E402

AUDIT = load_script(
    "worktree_citation_audit",
    ROOT / "scripts" / "forge" / "audit-commitments.py",
)
ARCHIVE = load_script(
    "worktree_citation_archive",
    ROOT / "scripts" / "forge" / "archive-run.py",
)


class WorktreeCitationRootTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="forge-worktree-roots-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.repository = self.base / "repo"
        self.repository.mkdir()
        self._git("init", "--quiet")
        self._git("config", "user.name", "Citation Fixture")
        self._git("config", "user.email", "citation@example.invalid")
        (self.repository / "tracked.txt").write_text("initial\n", encoding="utf-8")
        self._git("add", "tracked.txt")
        self._git("commit", "--quiet", "-m", "initial")
        self.head = self._git_output("rev-parse", "HEAD")
        self.worktree = self.repository / ".worktrees/linked"
        self._git(
            "worktree",
            "add",
            "--quiet",
            "-b",
            "citation-fixture",
            str(self.worktree),
            self.head,
        )
        self.relative = (
            ".forge/chains/c-2026-10-04T120000Z-abcd/evidence/shared.md"
        )
        artifact = self.repository / self.relative
        artifact.parent.mkdir(parents=True)
        artifact.write_text("# Common-root evidence\n\nshared body\n", encoding="utf-8")
        self.run_dir = (
            self.repository
            / ".codex-orchestrator/runs/run-worktree-citations"
        )
        self.run_dir.mkdir(parents=True)
        self.write_records(self._fixture_records())

    def _git(self, *arguments: str, cwd: Path | None = None) -> None:
        subprocess.run(
            ["git", *arguments],
            cwd=cwd or self.repository,
            check=True,
            capture_output=True,
        )

    def _git_output(self, *arguments: str, cwd: Path | None = None) -> str:
        return subprocess.run(
            ["git", *arguments],
            cwd=cwd or self.repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def _fixture_records(self) -> list[dict[str, object]]:
        validation = {
            "ok": True,
            "issues": [],
            "warnings": [],
            "non_passing_verifications": [],
            "profile": "gates",
        }
        return [
            {
                "type": "run_started",
                "run_id": self.run_dir.name,
                "goal": "Archive a run opened from a linked worktree.",
                "repo": str(self.worktree),
                "repo_head": self.head,
            },
            {
                "type": "task",
                "id": "task-01",
                "goal": "Exercise every citation surface.",
                "acceptance": ["All citation readers agree."],
                "files": ["scripts/forge/commitment_paths.py"],
                "status": "active",
            },
            {
                "type": "verification",
                "id": "check-01",
                "task": "task-01",
                "criterion": "common-root evidence",
                "method": "shared predicate",
                "check": "worktree citation roots",
                "result": "passed",
                "observation": f"reviewed `{self.relative}`",
                "evidence": [self.relative],
            },
            {
                "type": "execution",
                "execution": "execution-01",
                "task": "task-01",
                "prompt": self.relative,
                "events": self.relative,
                "handoff": self.relative,
            },
            {
                "type": "execution_result",
                "execution": "execution-01",
                "task": "task-01",
                "handoff": self.relative,
            },
            {
                "type": "decision",
                "id": "decision-01",
                "task": "task-01",
                "finding": "The common-root artifact is authoritative.",
                "outcome": "consensus",
                "resolution": "Use the shared ordered roots.",
                "basis": [self.relative],
                "risk": "low",
            },
            {
                "type": "task",
                "id": "task-01",
                "status": "complete",
                "outcome": "Citation readers agreed.",
            },
            {
                "type": "run_closed",
                "judgment": "passed",
                "summary": "Worktree citation run passed.",
                "validation": validation,
                "risks": [],
                "follow_ups": [],
            },
        ]

    def _focused_citation_records(
        self, citation: str, *, closed: bool = False
    ) -> list[dict[str, object]]:
        """Return a closeable journal whose only citation is one evidence path."""

        excluded = {"execution", "execution_result", "decision"}
        if not closed:
            excluded.add("run_closed")
        records = [
            record
            for record in self._fixture_records()
            if record.get("type") not in excluded
        ]
        verification = next(
            record for record in records if record.get("type") == "verification"
        )
        verification["evidence"] = [citation]
        verification["observation"] = "reviewed evidence"
        return records

    def records(self) -> list[dict[str, object]]:
        return [
            json.loads(line)
            for line in (self.run_dir / "journal.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]

    def write_records(
        self,
        records: list[dict[str, object]],
        *,
        run_dir: Path | None = None,
    ) -> None:
        ((run_dir or self.run_dir) / "journal.jsonl").write_text(
            "".join(
                json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
                for record in records
            ),
            encoding="utf-8",
        )

    def citation_records(self) -> list[dict[str, object]]:
        return [
            record
            for record in self.records()
            if record.get("type")
            in {"verification", "execution", "execution_result", "decision"}
        ]

    def _render(self) -> str:
        records, issues = journal.read_journal(self.run_dir / "journal.jsonl")
        self.assertEqual([], issues)
        closed = next(record for record in records if record.get("type") == "run_closed")
        fragment = AUDIT.audit(self.run_dir)
        return ARCHIVE.render_archive(
            repo=self.worktree.resolve(),
            run_dir=self.run_dir,
            records=records,
            closing_head=self.head,
            post_close=closed["validation"],
            audit_fragment=fragment,
        )

    def test_linked_worktree_append_audit_and_archive_use_layout_root(self) -> None:
        for record in self.citation_records():
            with self.subTest(record=record["type"]):
                journal._validate_append_citations(
                    self.worktree.resolve(),
                    self.run_dir,
                    record,
                )

        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/forge/audit-commitments.py"),
             "--run-dir", str(self.run_dir)],
            cwd=self.worktree,
            check=False,
            capture_output=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(b"", result.stderr)
        self.assertIn(b"## Residual Risks", result.stdout)

        rendered = self._render()
        self.assertIn("## Verbatim basis documents", rendered)
        self.assertIn(f"### {self.relative}", rendered)
        self.assertIn("# Common-root evidence\n\nshared body\n", rendered)

    def test_layout_only_citation_uses_one_predicate_for_all_readers(self) -> None:
        layout_file = self.repository / self.relative
        self.assertTrue(layout_file.is_file())
        self.assertFalse((self.worktree / self.relative).exists())
        records = self._focused_citation_records(self.relative)
        verification = next(
            record for record in records if record.get("type") == "verification"
        )

        journal._validate_append_citations(
            self.worktree.resolve(), self.run_dir, verification
        )
        self.write_records(records)
        with mock.patch.object(
            journal,
            "resolve_citation_path",
            wraps=commitment_paths.resolve_citation_path,
        ) as resolver:
            validation = journal.validate_run(self.run_dir)
        self.assertTrue(validation["ok"], validation["issues"])
        matching_calls = [
            call
            for call in resolver.call_args_list
            if len(call.args) > 1 and call.args[1] == self.relative
        ]
        self.assertTrue(matching_calls, resolver.call_args_list)
        self.assertTrue(
            any(
                call.kwargs.get("roots")
                == (
                    self.run_dir.resolve(),
                    self.worktree.resolve(),
                    self.repository.resolve(),
                )
                for call in matching_calls
            ),
            matching_calls,
        )

        projection = close_law.project_close(self.run_dir, records, "passed")
        self.assertTrue(projection["ok"], projection["issues"])
        self.write_records(
            self._focused_citation_records(self.relative, closed=True)
        )
        self.assertIn("## Residual Risks", AUDIT.audit(self.run_dir))

    def test_pre_close_recompute_keeps_the_real_run_citation_root(self) -> None:
        citation = "run-local/evidence.log"
        evidence = self.run_dir / citation
        evidence.parent.mkdir(parents=True)
        evidence.write_text("run-local evidence\n", encoding="utf-8")
        self.assertFalse((self.worktree / citation).exists())
        self.assertFalse((self.repository / citation).exists())
        records = self._focused_citation_records(citation, closed=True)
        self.write_records(records)
        for line, record in enumerate(records, start=1):
            record["_line"] = line

        fresh = ARCHIVE.recompute_pre_close_validation(self.run_dir, records)
        self.assertIsNotNone(fresh)
        assert fresh is not None
        self.assertTrue(fresh["ok"], fresh)

        original_validate = ARCHIVE.validate_run
        propagated: list[object] = []

        def without_citation_run_dir(run_dir, **kwargs):
            propagated.append(kwargs.pop("citation_run_dir", None))
            return original_validate(run_dir, **kwargs)

        with mock.patch.object(
            ARCHIVE,
            "validate_run",
            side_effect=without_citation_run_dir,
        ):
            degraded = ARCHIVE.recompute_pre_close_validation(
                self.run_dir, records
            )
        self.assertEqual([self.run_dir], propagated)
        self.assertIsNotNone(degraded)
        assert degraded is not None
        self.assertFalse(degraded["ok"], degraded)
        self.assertTrue(
            any(
                "referenced evidence[0] file does not exist" in issue
                for issue in degraded["issues"]
            ),
            degraded["issues"],
        )

    def test_validation_roots_and_controls_match_revision_twenty(self) -> None:
        records = self._focused_citation_records(self.relative)
        expected = (
            self.run_dir.resolve(),
            self.worktree.resolve(),
            self.repository.resolve(),
        )
        self.assertEqual(
            frozenset({"audit", "basis-documents", "append-time"}),
            commitment_paths.CITATION_LAYOUT_ROOT_LEGS,
        )
        self.assertEqual(expected, journal._validation_roots(self.run_dir, records))

        with mock.patch.object(journal, "VALIDATION_REPOSITORY_LEG", False):
            self.assertEqual(
                (self.run_dir,),
                journal._validation_roots(self.run_dir, records),
            )
            self.write_records(records)
            disabled = journal.validate_run(self.run_dir)
        self.assertFalse(disabled["ok"])
        self.assertTrue(
            any(
                "referenced evidence[0] file does not exist" in issue
                for issue in disabled["issues"]
            ),
            disabled["issues"],
        )

    def test_recorded_escape_blocks_layout_fallthrough_for_all_readers(self) -> None:
        outside = self.base / "outside-recorded-root.md"
        outside.write_text("outside\n", encoding="utf-8")
        recorded_file = self.worktree / self.relative
        recorded_file.parent.mkdir(parents=True)
        recorded_file.symlink_to(outside)
        self.assertTrue((self.repository / self.relative).is_file())
        self.assertTrue(recorded_file.is_symlink())
        records = self._focused_citation_records(self.relative)
        verification = next(
            record for record in records if record.get("type") == "verification"
        )

        with self.assertRaisesRegex(
            journal.CoordinationRefusal,
            "record cites path outside run or repository",
        ):
            journal._validate_append_citations(
                self.worktree.resolve(), self.run_dir, verification
            )
        self.write_records(records)
        validation = journal.validate_run(self.run_dir)
        self.assertFalse(validation["ok"])
        expected = f"referenced evidence[0] file does not exist: {self.relative}"
        self.assertTrue(
            any(expected in issue for issue in validation["issues"]),
            validation["issues"],
        )
        projection = close_law.project_close(self.run_dir, records, "passed")
        self.assertFalse(projection["ok"])
        self.assertTrue(
            any(expected in issue for issue in projection["issues"]),
            projection["issues"],
        )

        self.write_records(
            self._focused_citation_records(self.relative, closed=True)
        )
        with self.assertRaises(AUDIT.Failure) as caught:
            AUDIT.audit(self.run_dir)
        self.assertEqual(5, caught.exception.exit_code)
        self.assertIn(self.relative, caught.exception.diagnostic)

    def test_fr016_missing_probe_keeps_run_and_layout_roots_only(self) -> None:
        citation = "legacy-recorded-only/evidence.log"
        recorded_file = self.worktree / citation
        recorded_file.parent.mkdir(parents=True)
        recorded_file.write_text("recorded-root evidence\n", encoding="utf-8")
        self.assertFalse((self.run_dir / citation).exists())
        self.assertFalse((self.repository / citation).exists())
        records = self._focused_citation_records(citation)
        records.insert(
            3,
            {
                "type": "decision",
                "id": "journal-dialect-compat",
                "resolution": "legacy-dialect-compat: approved fixture",
            },
        )
        self.write_records(records)

        result = journal.validate_run(self.run_dir)
        self.assertTrue(result["ok"], result["issues"])
        self.assertTrue(
            any(
                f"tolerated missing evidence[0] file: {citation}" in warning
                for warning in result["warnings"]
            ),
            result["warnings"],
        )
        with mock.patch.object(
            journal,
            "LEGACY_COMPATIBILITY_LEGS",
            journal.LEGACY_COMPATIBILITY_LEGS - {"missing-evidence-file"},
        ):
            disabled = journal.validate_run(self.run_dir)
        self.assertFalse(disabled["ok"])
        self.assertTrue(
            any(citation in issue for issue in disabled["issues"]),
            disabled["issues"],
        )

    def test_validation_uses_recorded_worktree_before_layout_root(self) -> None:
        citation = "only-in-recorded-worktree.log"
        (self.worktree / citation).write_text("worktree only\n", encoding="utf-8")
        self.assertFalse((self.repository / citation).exists())
        run_dir = self.run_dir.parent / "run-worktree-validation"
        run_dir.mkdir()
        records = [
            {
                "type": "run_started",
                "run_id": run_dir.name,
                "repo": str(self.worktree),
                "repo_head": self.head,
            },
            {"type": "task", "id": "task-01", "status": "complete"},
            {
                "type": "verification",
                "id": "check-01",
                "task": "task-01",
                "criterion": "recorded worktree citation",
                "method": "validate",
                "check": "validate_run",
                "result": "passed",
                "observation": "recorded worktree evidence exists",
                "evidence": [citation],
            },
            {"type": "run_closed", "judgment": "passed", "summary": "done"},
        ]
        self.write_records(records, run_dir=run_dir)

        result = journal.validate_run(run_dir)
        self.assertTrue(result["ok"], result["issues"])
        self.assertTrue(journal.declared_file_exists(run_dir, citation))
        with mock.patch.object(journal, "VALIDATION_REPOSITORY_LEG", False):
            disabled = journal.validate_run(run_dir)
        self.assertFalse(disabled["ok"])
        self.assertTrue(
            any("referenced evidence[0] file does not exist" in issue
                for issue in disabled["issues"]),
            disabled["issues"],
        )

    def test_out_of_layout_validation_keeps_the_recorded_root(self) -> None:
        citation = "out-of-layout-recorded.log"
        (self.worktree / citation).write_text("recorded only\n", encoding="utf-8")
        recorded_subdirectory = self.worktree / "nested"
        recorded_subdirectory.mkdir()
        run_dir = self.base / "foreign-runs" / "run-recorded-root"
        run_dir.mkdir(parents=True)
        records = [
            {"type": "run_started", "repo": str(recorded_subdirectory)},
            {"type": "task", "id": "task-01", "status": "complete"},
            {
                "type": "verification",
                "id": "check-01",
                "task": "task-01",
                "criterion": "out-of-layout recorded root",
                "result": "passed",
                "evidence": [citation],
            },
            {"type": "run_closed", "judgment": "passed", "summary": "done"},
        ]
        self.write_records(records, run_dir=run_dir)

        self.assertIsNone(journal._layout_repository_root(run_dir))
        self.assertEqual(
            (run_dir, self.worktree.resolve()),
            journal._validation_roots(run_dir, records),
        )
        result = journal.validate_run(run_dir)
        self.assertTrue(result["ok"], result["issues"])
        with mock.patch.object(journal, "VALIDATION_REPOSITORY_LEG", False):
            self.assertFalse(journal.validate_run(run_dir)["ok"])

        # An arbitrary non-Git directory cannot become the recorded root.
        broad_root = self.base / "broad-directory"
        broad_root.mkdir()
        outside = broad_root / "broad-root-only.log"
        outside.write_text("outside\n", encoding="utf-8")
        citation = outside.relative_to(broad_root).as_posix()
        run_dir = self.base / "foreign-runs" / "run-broad-root"
        run_dir.mkdir(parents=True)
        records = [
            {"type": "run_started", "repo": str(broad_root)},
            {"type": "task", "id": "task-01", "status": "complete"},
            {
                "type": "verification",
                "id": "check-01",
                "task": "task-01",
                "criterion": "broad recorded root stays bounded",
                "result": "passed",
                "evidence": [citation],
            },
            {"type": "run_closed", "judgment": "passed", "summary": "done"},
        ]
        self.write_records(records, run_dir=run_dir)

        self.assertTrue((broad_root / citation).is_file())
        self.assertEqual((run_dir,), journal._validation_roots(run_dir, records))
        result = journal.validate_run(run_dir)
        self.assertFalse(result["ok"])
        self.assertTrue(
            any("referenced evidence[0] file does not exist" in issue
                for issue in result["issues"]),
            result["issues"],
        )

    def test_legacy_non_missing_errors_are_not_tolerated(self) -> None:
        citation = "afile/sub.log"
        (self.repository / "afile").write_text("regular file\n", encoding="utf-8")
        records = self._focused_citation_records(citation)
        records.insert(
            3,
            {
                "type": "decision",
                "id": "journal-dialect-compat",
                "resolution": "legacy-dialect-compat: approved fixture",
            },
        )
        self.write_records(records)

        result = journal.validate_run(self.run_dir)
        expected = f"referenced evidence[0] file does not exist: {citation}"
        self.assertFalse(result["ok"])
        self.assertTrue(any(expected in issue for issue in result["issues"]))
        self.assertFalse(
            any("tolerated missing evidence" in warning
                for warning in result["warnings"]),
            result["warnings"],
        )

        with mock.patch.object(journal, "VALIDATION_REPOSITORY_LEG", False):
            weakened = journal.validate_run(self.run_dir)
        self.assertTrue(weakened["ok"], weakened["issues"])
        self.assertTrue(
            any("tolerated missing evidence[0] file" in warning
                for warning in weakened["warnings"]),
            weakened["warnings"],
        )

        # Other OSErrors stay hard under the same compatibility leg.
        citation = "permission-denied-evidence.log"
        records = [
            {"type": "run_started", "repo": str(self.worktree)},
            {"type": "task", "id": "task-01", "status": "complete"},
            {
                "type": "verification",
                "id": "check-01",
                "task": "task-01",
                "criterion": "unreadable evidence stays hard",
                "result": "passed",
                "evidence": [citation],
            },
            {
                "type": "decision",
                "id": "journal-dialect-compat",
                "resolution": "legacy-dialect-compat: approved fixture",
            },
            {"type": "run_closed", "judgment": "passed", "summary": "done"},
        ]
        self.write_records(records)
        real_lstat = os.lstat

        def permission_denied(path: os.PathLike[str] | str, *args, **kwargs):
            if Path(path).name == citation:
                raise PermissionError("fixture denial")
            return real_lstat(path, *args, **kwargs)

        with mock.patch.object(journal.os, "lstat", side_effect=permission_denied):
            result = journal.validate_run(self.run_dir)
        self.assertFalse(result["ok"])
        self.assertFalse(
            any("tolerated missing evidence" in warning
                for warning in result["warnings"]),
            result["warnings"],
        )

    def test_legacy_missing_escape_spellings_stay_hard(self) -> None:
        outside = self.base / "outside-evidence"
        outside.mkdir()
        (self.run_dir / "esc").symlink_to(outside, target_is_directory=True)
        for citation in ("../missing.log", "esc/missing.log"):
            with self.subTest(citation=citation):
                records = [
                    {"type": "run_started", "repo": str(self.worktree)},
                    {"type": "task", "id": "task-01", "status": "complete"},
                    {
                        "type": "verification",
                        "id": "check-01",
                        "task": "task-01",
                        "criterion": "anchored escape stays hard",
                        "result": "passed",
                        "evidence": [citation],
                    },
                    {
                        "type": "decision",
                        "id": "journal-dialect-compat",
                        "resolution": "legacy-dialect-compat: approved fixture",
                    },
                    {"type": "run_closed", "judgment": "passed", "summary": "done"},
                ]
                self.write_records(records)

                selected = commitment_paths.resolve_contained_path(
                    citation,
                    journal._validation_roots(self.run_dir, records),
                )
                if citation.startswith("esc/"):
                    self.assertIsNotNone(selected)
                    assert selected is not None
                    self.assertTrue(selected.anchored)
                    self.assertFalse(selected.contained)
                else:
                    self.assertIsNone(selected)
                result = journal.validate_run(self.run_dir)
                self.assertFalse(result["ok"])
                self.assertTrue(
                    any(citation in issue for issue in result["issues"]),
                    result["issues"],
                )
                self.assertFalse(
                    any("tolerated missing evidence" in warning
                        for warning in result["warnings"]),
                    result["warnings"],
                )

    def test_append_audit_and_archive_import_one_predicate(self) -> None:
        self.assertIs(commitment_paths.resolve_citation_path, AUDIT.resolve_citation_path)
        self.assertIs(commitment_paths.resolve_citation_path, ARCHIVE.resolve_citation_path)
        self.assertIs(commitment_paths.resolve_citation_path, journal.resolve_citation_path)

    def test_audit_and_basis_document_legs_are_load_bearing(self) -> None:
        enabled = commitment_paths.CITATION_LAYOUT_ROOT_LEGS
        self.assertIn("## Residual Risks", AUDIT.audit(self.run_dir))
        decisions = [
            record for record in self.records() if record.get("type") == "decision"
        ]
        documents = ARCHIVE.basis_documents(
            self.worktree.resolve(),
            self.run_dir,
            decisions,
        )
        self.assertEqual([self.relative], [document.label for document in documents])

        with mock.patch.object(
            commitment_paths,
            "CITATION_LAYOUT_ROOT_LEGS",
            enabled - {"audit"},
        ):
            with self.assertRaises(AUDIT.Failure) as caught:
                AUDIT.audit(self.run_dir)
        self.assertEqual(5, caught.exception.exit_code)
        self.assertEqual(
            "cited path does not exist within run or repository: "
            f"{self.relative} (verification check-01 evidence[0])",
            caught.exception.diagnostic,
        )

        with mock.patch.object(
            commitment_paths,
            "CITATION_LAYOUT_ROOT_LEGS",
            enabled - {"basis-documents"},
        ):
            self.assertEqual(
                [],
                ARCHIVE.basis_documents(
                    self.worktree.resolve(),
                    self.run_dir,
                    decisions,
                ),
            )

    def test_named_audit_control_block_is_load_bearing(self) -> None:
        source = (ROOT / "scripts/forge/audit-commitments.py").read_text(
            encoding="utf-8"
        )
        begin = "    # CONTROL layout-root BEGIN\n"
        end = "    # CONTROL layout-root END\n"
        before, rest = source.split(begin, 1)
        _, after = rest.split(end, 1)
        source = (
            before
            + begin
            + '    citation_leg = "disabled-audit"\n'
            + end
            + after
        )
        derived = "PLUGIN_ROOT = Path(__file__).resolve().parents[2]\n"
        pinned = (
            f"PLUGIN_ROOT = Path({str(ROOT)!r})\n"
            f"sys.path.insert(0, {str(ROOT / 'scripts/forge')!r})\n"
        )
        mutant = self.base / "audit-layout-root-disabled.py"
        mutant.write_text(source.replace(derived, pinned, 1), encoding="utf-8")

        result = subprocess.run(
            [sys.executable, str(mutant), "--run-dir", str(self.run_dir)],
            cwd=self.worktree,
            check=False,
            capture_output=True,
        )
        self.assertEqual(5, result.returncode)
        self.assertEqual(b"", result.stdout)
        self.assertIn(self.relative.encode(), result.stderr)

    def test_layout_escape_refuses_append_and_audit(self) -> None:
        escape = ".forge/chains/c-2026-10-04T120000Z-abcd/evidence/escape.md"
        outside = self.base / "outside.md"
        outside.write_text("outside\n", encoding="utf-8")
        (self.repository / escape).symlink_to(outside)
        record = {"type": "verification", "id": "escape", "evidence": [escape]}

        with self.assertRaisesRegex(
            journal.CoordinationRefusal,
            "record cites path outside run or repository",
        ):
            journal._validate_append_citations(
                self.worktree.resolve(), self.run_dir, record
            )
        enabled = commitment_paths.CITATION_LAYOUT_ROOT_LEGS
        with mock.patch.object(
            commitment_paths,
            "CITATION_LAYOUT_ROOT_LEGS",
            enabled - {"append-time"},
        ):
            journal._validate_append_citations(
                self.worktree.resolve(), self.run_dir, record
            )

        records = self.records()
        verification = next(
            item for item in records if item.get("type") == "verification"
        )
        verification["evidence"] = [escape]
        self.write_records(records)
        with self.assertRaises(AUDIT.Failure) as caught:
            AUDIT.audit(self.run_dir)
        self.assertEqual(5, caught.exception.exit_code)
        self.assertIn(escape, caught.exception.diagnostic)

    def test_traversal_and_absolute_citations_still_refuse(self) -> None:
        traversal = "../outside.md"
        (self.run_dir.parent / "outside.md").write_text(
            "outside\n", encoding="utf-8"
        )
        cases = (traversal, str(self.repository / self.relative))
        for value in cases:
            with self.subTest(value=value):
                record = {
                    "type": "verification",
                    "id": "escape",
                    "evidence": [value],
                }
                with self.assertRaisesRegex(
                    journal.CoordinationRefusal,
                    "record cites path outside run or repository",
                ):
                    journal._validate_append_citations(
                        self.worktree.resolve(), self.run_dir, record
                    )

                records = self.records()
                verification = next(
                    item for item in records if item.get("type") == "verification"
                )
                verification["evidence"] = [value]
                self.write_records(records)
                with self.assertRaises(AUDIT.Failure) as caught:
                    AUDIT.audit(self.run_dir)
                self.assertEqual(5, caught.exception.exit_code)
                self.write_records(self._fixture_records())

    def test_main_checkout_recorded_leg_still_works_without_layout_leg(self) -> None:
        records = self.records()
        records[0]["repo"] = str(self.repository)
        self.write_records(records)
        enabled = commitment_paths.CITATION_LAYOUT_ROOT_LEGS
        with mock.patch.object(
            commitment_paths,
            "CITATION_LAYOUT_ROOT_LEGS",
            enabled - {"audit"},
        ):
            output = AUDIT.audit(self.run_dir)
        self.assertIn("## Residual Risks", output)


class WorktreeLegacyRecoveryRootTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="forge-recovery-root-")
        self.addCleanup(self.temporary.cleanup)
        self.repository = Path(self.temporary.name) / "repo"
        self.repository.mkdir()
        self.run_git("init", "--quiet")
        self.run_git("config", "user.name", "Recovery Fixture")
        self.run_git("config", "user.email", "recovery@example.invalid")
        (self.repository / "tracked.txt").write_text("initial\n", encoding="utf-8")
        self.run_git("add", "tracked.txt")
        self.run_git("commit", "--quiet", "-m", "initial")
        self.head = self.output_git("rev-parse", "HEAD")
        self.worktree = self.repository / ".worktrees/recovery"
        self.run_git(
            "worktree",
            "add",
            "--quiet",
            "-b",
            "recovery-fixture",
            str(self.worktree),
            self.head,
        )

    def run_git(self, *arguments: str) -> None:
        subprocess.run(
            ["git", *arguments],
            cwd=self.repository,
            check=True,
            capture_output=True,
        )

    def output_git(self, *arguments: str) -> str:
        return subprocess.run(
            ["git", *arguments],
            cwd=self.repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    @staticmethod
    def write_journal(run_dir: Path, records: list[dict[str, object]]) -> None:
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "journal.jsonl").write_text(
            "".join(
                json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
                for record in records
            ),
            encoding="utf-8",
        )

    def test_recovery_containment_uses_resolved_target_parent(self) -> None:
        target_name = "legacy-target"
        recovery_name = "recovery-run"
        resolution = (
            f"legacy-archive-recovery: {target_name} recovered closing HEAD "
            f"{self.head}; operator recovered the closed implementation state"
        )
        with mock.patch.dict(
            os.environ,
            {"FORGE_SESSION_PID": str(os.getpid())},
        ):
            ARCHIVE.journal_builders.run_open(
                self.worktree.resolve(),
                recovery_name,
                idempotency_key=hashlib.sha256(b"open recovery").hexdigest(),
                goal="Approve one recovery",
                scope=["recovery/**"],
                plugin_ref="forge-test-worktree-roots",
            )
            decision = ARCHIVE.journal_builders.decision_add(
                self.worktree.resolve(),
                recovery_name,
                idempotency_key=hashlib.sha256(b"approve recovery").hexdigest(),
                resolution=resolution,
                task=None,
                finding=None,
                outcome="operator_approval",
                risk=None,
                basis=(),
                binding_chain=None,
                binding_id=None,
            )
            runs = self.repository / ".codex-orchestrator/runs"
            target = runs / target_name
            self.write_journal(
                target,
                [
                    {
                        "type": "run_started",
                        "run_id": target_name,
                        "repo": str(self.worktree),
                        "repo_head": self.head,
                        "goal": "Preserve a historical run.",
                        "scope": ["legacy/**"],
                    },
                    {"type": "run_closed", "judgment": "passed"},
                ],
            )
            linked_runs = Path(self.temporary.name) / "linked-runs"
            linked_runs.symlink_to(runs, target_is_directory=True)
            linked_target = linked_runs / target_name
            decision_id = decision.records[0]["id"]
            mode = ARCHIVE.legacy_closing_mode(
                repo=self.worktree.resolve(),
                target_run_dir=linked_target,
                recovered_head=self.head,
                approval=f"{recovery_name}:{decision_id}",
                prove_approval=True,
            )
        self.assertEqual(
            ARCHIVE.ClosingMode(self.head, f"{recovery_name}:{decision_id}"),
            mode,
        )
        escaped_recovery = Path(self.temporary.name) / "escaped-recovery"
        shutil.move(runs / recovery_name, escaped_recovery)
        (runs / recovery_name).symlink_to(
            escaped_recovery,
            target_is_directory=True,
        )
        with mock.patch.dict(
            os.environ,
            {"FORGE_SESSION_PID": str(os.getpid())},
        ):
            current_owner = ARCHIVE.journal_engine._session_owner()
            owner_before = ARCHIVE.journal_engine._read_owner_observation(
                escaped_recovery / "owner"
            )
            self.assertIsNotNone(owner_before)
            assert owner_before is not None
            self.assertEqual(current_owner.pid, owner_before[1].pid)
            self.assertEqual(current_owner.host, owner_before[1].host)
            with self.assertRaises(ARCHIVE.ArchiveRefusal):
                ARCHIVE.legacy_closing_mode(
                    repo=self.worktree.resolve(),
                    target_run_dir=linked_target,
                    recovered_head=self.head,
                    approval=f"{recovery_name}:{decision_id}",
                    prove_approval=True,
                )


if __name__ == "__main__":
    unittest.main()
