"""Behavioral tests for the durable-commitment audit."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "scripts" / "forge" / "audit-commitments.py"
FIXTURE = ROOT / "tests" / "replay" / "archive-audit"
EXPECTED = (
    b"## Residual Risks\n\n"
    b"- A residual compatibility risk remains.\n\n"
    b"## Follow-ups\n\n"
    b"- Monitor the first archived run.\n"
)


class AuditCommitmentsTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.repo = self.base / "repo"
        self.repo.mkdir()
        (self.repo / "docs").mkdir()
        (self.repo / "docs" / "repo-basis.md").write_text(
            "# Repository basis\n", encoding="utf-8"
        )
        self.run_dir = self.base / "run"
        shutil.copytree(FIXTURE, self.run_dir)
        fixture = (self.run_dir / "journal.jsonl").read_text(encoding="utf-8")
        (self.run_dir / "journal.jsonl").write_text(
            fixture.replace("__REPO__", str(self.repo)), encoding="utf-8"
        )

    def records(self) -> list[dict[str, object]]:
        return [
            json.loads(line)
            for line in (self.run_dir / "journal.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]

    def write_records(self, records: list[dict[str, object]]) -> None:
        value = "".join(
            json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n"
            for record in records
        )
        (self.run_dir / "journal.jsonl").write_text(value, encoding="utf-8")

    def invoke(
        self, script: Path = AUDIT, *, cwd: Path | None = None
    ) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [sys.executable, str(script), "--run-dir", str(self.run_dir)],
            cwd=cwd or self.base,
            check=False,
            capture_output=True,
        )

    def assert_failure(
        self, result: subprocess.CompletedProcess[bytes], code: int, diagnostic: bytes
    ) -> None:
        self.assertEqual(code, result.returncode)
        self.assertEqual(b"", result.stdout)
        self.assertEqual(diagnostic, result.stderr)

    def mutate(self, transform) -> list[dict[str, object]]:
        records = self.records()
        transform(records)
        self.write_records(records)
        return records

    def git(self, *arguments: str, cwd: Path | None = None) -> None:
        subprocess.run(
            ["git", *arguments],
            cwd=cwd or self.repo,
            check=True,
            capture_output=True,
        )

    def make_branch_artifact(self, branch: str, relative: str) -> None:
        self.git("init")
        self.git("config", "user.name", "Audit Fixture")
        self.git("config", "user.email", "audit@example.invalid")
        self.git("add", ".")
        self.git("commit", "-m", "fixture root")
        self.git("switch", "-c", branch)
        artifact = self.repo / relative
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text("branch artifact\n", encoding="utf-8")
        self.git("add", relative)
        self.git("commit", "-m", "branch artifact")
        self.git("switch", "-")

    def make_forge_source_repo(self, conformance_source: str) -> None:
        """Turn the ordinary fixture repository into a tracked forge source."""

        for relative in (
            "tests/test_repo_conformance.py",
            ".claude-plugin/plugin.json",
            "docs/specs/forge-plugin-spec.md",
        ):
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                conformance_source if relative.startswith("tests/") else "fixture\n",
                encoding="utf-8",
            )
        self.git("init")
        self.git("config", "user.name", "Audit Fixture")
        self.git("config", "user.email", "audit@example.invalid")
        self.git("add", ".")
        self.git("commit", "-m", "forge source fixture")

    @staticmethod
    def conformance_program(*, stdout: str, stderr: str = "", code: int = 0) -> str:
        return (
            "import sys\n"
            "from pathlib import Path\n"
            "assert sys.argv[1] == '--run-dir'\n"
            "assert Path(sys.argv[2], 'journal.jsonl').is_file()\n"
            f"sys.stdout.write({stdout!r})\n"
            f"sys.stderr.write({stderr!r})\n"
            f"raise SystemExit({code})\n"
        )

    @staticmethod
    def correction(
        supplier: str, *lines: str
    ) -> dict[str, object]:
        return {
            "type": "decision",
            "id": supplier,
            "finding": "Correct a citation.",
            "outcome": "operator_decision",
            "resolution": "citation-correction:\n" + "\n".join(lines),
            "basis": [],
            "risk": "low",
        }

    def test_success_is_cwd_independent_and_byte_exact(self) -> None:
        result = self.invoke(cwd=Path("/"))
        self.assertEqual(0, result.returncode)
        self.assertEqual(EXPECTED, result.stdout)
        self.assertEqual(b"", result.stderr)

    def test_forge_source_historical_routing_findings_are_prepended(self) -> None:
        findings = (
            "## Historical Routing Findings\n\n"
            "- journal line 5: agent 'review-01' recorded model/effort "
            "('gpt-5.6-terra', 'high'); expected model/effort "
            "('gpt-5.6-terra', 'medium') from abc1234:agents/reviewer.toml\n"
        )
        self.make_forge_source_repo(self.conformance_program(stdout=findings))

        result = self.invoke()

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(findings.encode() + b"\n" + EXPECTED, result.stdout)
        self.assertEqual(b"", result.stderr)

    def test_forge_source_current_conformance_failure_refuses_without_stdout(
        self,
    ) -> None:
        report = "## Historical Routing Findings\n\nNone recorded\n"
        self.make_forge_source_repo(
            self.conformance_program(
                stdout=report,
                stderr=(
                    "forge repo conformance: system/codex/agents/review-cheap.toml "
                    "does not match FR-030\n"
                ),
                code=1,
            )
        )

        result = self.invoke()

        self.assertEqual(1, result.returncode)
        self.assertEqual(b"", result.stdout)
        self.assertIn(b"repository conformance failed", result.stderr)
        self.assertIn(b"does not match FR-030", result.stderr)
        self.assertIn(b"Historical Routing Findings", result.stderr)

    def test_forge_source_malformed_conformance_output_refuses(self) -> None:
        self.make_forge_source_repo(
            self.conformance_program(stdout="historical finding without heading\n")
        )

        result = self.invoke()

        self.assertEqual(2, result.returncode)
        self.assertEqual(b"", result.stdout)
        self.assertIn(b"repository conformance output is invalid", result.stderr)

    def test_nested_repo_path_inside_forge_source_is_not_misclassified(self) -> None:
        self.make_forge_source_repo(
            self.conformance_program(
                stdout="## Historical Routing Findings\n\nNone recorded\n",
                stderr="forge repo conformance: should not run\n",
                code=1,
            )
        )
        nested_repo = self.repo / "ordinary-nested-repo"
        (nested_repo / "docs").mkdir(parents=True)
        (nested_repo / "docs/repo-basis.md").write_text(
            "# Nested repository basis\n", encoding="utf-8"
        )
        self.mutate(
            lambda records: records[0].__setitem__("repo", str(nested_repo))
        )

        result = self.invoke()

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(EXPECTED, result.stdout)
        self.assertEqual(b"", result.stderr)

    def test_repo_conformance_control_is_killed_when_disabled(self) -> None:
        findings = (
            "## Historical Routing Findings\n\n"
            "- journal line 16: agent 'review-02' recorded model/effort "
            "('gpt-5.6-terra', 'high'); expected model/effort "
            "('gpt-5.6-terra', 'medium') from def5678:agents/reviewer.toml\n"
        )
        self.make_forge_source_repo(self.conformance_program(stdout=findings))
        intact = self.invoke()
        self.assertEqual(0, intact.returncode, intact.stderr)
        self.assertIn(findings.encode(), intact.stdout)

        mutant = self.disabled_control_copy(
            AUDIT.read_text(encoding="utf-8"),
            "repo-conformance",
            '    conformance_prefix = ""  # CONTROL DISABLED\n',
        )
        disabled = self.invoke(mutant)
        self.assertEqual(0, disabled.returncode, disabled.stderr)
        with self.assertRaises(AssertionError):
            self.assertIn(findings.encode(), disabled.stdout)

        failing_source = self.conformance_program(
            stdout="## Historical Routing Findings\n\nNone recorded\n",
            stderr="forge repo conformance: current route drift\n",
            code=1,
        )
        (self.repo / "tests/test_repo_conformance.py").write_text(
            failing_source, encoding="utf-8"
        )
        self.git("add", "tests/test_repo_conformance.py")
        self.git("commit", "-m", "current route drift fixture")
        intact_failure = self.invoke()
        self.assertNotEqual(0, intact_failure.returncode)
        disabled_escape = self.invoke(mutant)
        self.assertEqual(0, disabled_escape.returncode, disabled_escape.stderr)
        self.assertEqual(EXPECTED, disabled_escape.stdout)

    def test_absent_commitment_arrays_render_none_recorded(self) -> None:
        def remove_arrays(records: list[dict[str, object]]) -> None:
            close = records[-1]
            close.pop("risks")
            close.pop("follow_ups")

        self.mutate(remove_arrays)
        result = self.invoke()
        self.assertEqual(0, result.returncode)
        self.assertEqual(
            b"## Residual Risks\n\nNone recorded\n\n"
            b"## Follow-ups\n\nNone recorded\n",
            result.stdout,
        )
        self.assertEqual(b"", result.stderr)

    def test_unknown_structured_task_reference_is_exact(self) -> None:
        def change(records: list[dict[str, object]]) -> None:
            records[3]["task"] = "task-99"

        self.mutate(change)
        self.assert_failure(
            self.invoke(),
            3,
            b"forge: commitment audit failed \xe2\x80\x94 unknown task reference: "
            b"task-99 (decision decision-01 task field)\n",
        )

    def test_recorded_branch_name_in_decision_prose_is_not_a_task_reference(self) -> None:
        def change(records: list[dict[str, object]]) -> None:
            records.insert(
                -1,
                {
                    "type": "execution",
                    "agent": "reviewer-branch-prose",
                    "execution": "execution-branch-prose",
                    "task": "task-07",
                    "role": "review",
                    "branch": "forge/task-03-invariants",
                },
            )
            records[3]["resolution"] = (
                "Artifact exists on recorded branch forge/task-03-invariants."
            )

        self.mutate(change)
        result = self.invoke()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(EXPECTED, result.stdout)

    def test_recorded_branch_prefix_does_not_hide_a_longer_unknown_task(self) -> None:
        def change(records: list[dict[str, object]]) -> None:
            records.insert(
                -1,
                {
                    "type": "execution",
                    "agent": "reviewer-branch-prefix",
                    "execution": "execution-branch-prefix",
                    "task": "task-07",
                    "role": "review",
                    "branch": "forge/task-03-invariants",
                },
            )
            records[3]["resolution"] = (
                "Unknown work remains on forge/task-03-invariants-other."
            )

        self.mutate(change)
        self.assert_failure(
            self.invoke(),
            3,
            b"forge: commitment audit failed \xe2\x80\x94 unknown task reference: "
            b"task-03-invariants-other (decision decision-01 resolution)\n",
        )

    def test_unknown_resolution_task_references_with_punctuation_are_exact(self) -> None:
        def change(records: list[dict[str, object]]) -> None:
            records[3]["resolution"] = (
                "Create task-07/task-08, task-09; and task-10."
            )

        self.mutate(change)
        self.assert_failure(
            self.invoke(),
            3,
            b"forge: commitment audit failed \xe2\x80\x94 unknown task reference: "
            b"task-09 (decision decision-01 resolution)\n",
        )

    def test_latest_non_terminal_task_is_exact(self) -> None:
        def change(records: list[dict[str, object]]) -> None:
            records[5]["status"] = "active"

        self.mutate(change)
        self.assert_failure(
            self.invoke(),
            4,
            b"forge: commitment audit failed \xe2\x80\x94 task is non-terminal at close: "
            b"task-07 (latest status: active)\n",
        )

    def test_missing_decision_basis_path_is_exact(self) -> None:
        def change(records: list[dict[str, object]]) -> None:
            records[3]["basis"] = ["findings/missing.md (binding review)"]

        self.mutate(change)
        self.assert_failure(
            self.invoke(),
            5,
            b"forge: commitment audit failed \xe2\x80\x94 cited path does not exist "
            b"within run or repository: findings/missing.md "
            b"(decision decision-01 basis[0])\n",
        )

    def legacy_declaration(self) -> dict[str, object]:
        return {
            "type": "decision",
            "id": "journal-dialect-compat",
            "resolution": "legacy-dialect-compat: pre-D13 journal",
        }

    def test_pre_declaration_absolute_citations_are_legacy_findings(self) -> None:
        # The palimpsest authoring-system archive shape: a declared legacy
        # journal cites absolute paths from before the declaration — one
        # resolving inside the run directory, one existing but outside every
        # audit root. Neither can be repaired by a citation-correction append
        # (the run is closed), so the audit must degrade them to a visible
        # Legacy Citations section instead of refusing the archive.
        (self.run_dir / "plan.md").write_text("# plan\n", encoding="utf-8")
        outside = self.base / "elsewhere"
        outside.mkdir()
        (outside / "SKILL.md").write_text("# skill\n", encoding="utf-8")

        def change(records: list[dict[str, object]]) -> None:
            records[3]["basis"] = [
                str(self.run_dir / "plan.md"),
                str(outside / "SKILL.md"),
            ]
            records.insert(-1, self.legacy_declaration())

        self.mutate(change)
        result = self.invoke()
        self.assertEqual(0, result.returncode, result.stderr)
        stdout = result.stdout.decode("utf-8")
        self.assertIn("## Legacy Citations\n", stdout)
        self.assertIn(
            f"- {self.run_dir / 'plan.md'} (decision decision-01 basis[0])", stdout
        )
        self.assertIn(
            f"- {outside / 'SKILL.md'} (decision decision-01 basis[1])", stdout
        )

    def test_post_declaration_absolute_citation_still_fails(self) -> None:
        # Cutover: a record at or after the declaration gets no citation
        # tolerance even when the cited absolute path exists.
        (self.run_dir / "plan.md").write_text("# plan\n", encoding="utf-8")

        def change(records: list[dict[str, object]]) -> None:
            records.insert(3, self.legacy_declaration())
            records[4]["basis"] = [str(self.run_dir / "plan.md")]

        self.mutate(change)
        self.assert_failure(
            self.invoke(),
            5,
            "forge: commitment audit failed — cited path does not exist "
            f"within run or repository: {self.run_dir / 'plan.md'} "
            "(decision decision-01 basis[0])\n".encode("utf-8"),
        )

    def test_undeclared_absolute_citation_still_fails(self) -> None:
        # Strict parity: without a declaration an absolute citation refuses
        # the archive exactly as before.
        (self.run_dir / "plan.md").write_text("# plan\n", encoding="utf-8")

        def change(records: list[dict[str, object]]) -> None:
            records[3]["basis"] = [str(self.run_dir / "plan.md")]

        self.mutate(change)
        self.assert_failure(
            self.invoke(),
            5,
            "forge: commitment audit failed — cited path does not exist "
            f"within run or repository: {self.run_dir / 'plan.md'} "
            "(decision decision-01 basis[0])\n".encode("utf-8"),
        )

    def test_corrected_missing_pre_declaration_citation_stays_hard(self) -> None:
        # A citation-correction is a modern repair: even under a dialect
        # declaration, a corrected citation whose corrected path is still
        # missing must keep the exact refusal. This is the killing test for
        # the tolerance's `correction is None` clause — with that clause
        # disabled, this journal would archive while rendering the failed
        # repair in both Citation Corrections and Legacy Citations.
        plan = self.run_dir / "plan.md"
        plan.write_text("# plan\n", encoding="utf-8")

        def change(records: list[dict[str, object]]) -> None:
            records[3]["basis"] = [str(plan)]
            records.insert(
                -1,
                self.correction(
                    "fix-01", "decision-01 basis[0]: findings/still-missing.md"
                ),
            )
            records.insert(-1, self.legacy_declaration())

        self.mutate(change)
        expected = (
            "forge: commitment audit failed — cited path does not exist "
            "within run or repository: findings/still-missing.md "
            f"(corrected from {plan} for decision decision-01 basis[0] "
            "by decision fix-01)\n"
        ).encode("utf-8")
        self.assert_failure(self.invoke(), 5, expected)

    def test_backticked_path_shaped_observation_is_audited(self) -> None:
        def change(records: list[dict[str, object]]) -> None:
            records[4]["observation"] = "FAIL; see `evidence/missing.txt`."

        self.mutate(change)
        self.assert_failure(
            self.invoke(),
            5,
            b"forge: commitment audit failed \xe2\x80\x94 cited path does not exist "
            b"within run or repository: evidence/missing.txt "
            b"(verification verification-01 observation)\n",
        )

    def test_markdown_link_path_shaped_observation_is_audited(self) -> None:
        def change(records: list[dict[str, object]]) -> None:
            records[4]["observation"] = (
                "FAIL; see [missing evidence](evidence/missing.txt)."
            )

        self.mutate(change)
        self.assert_failure(
            self.invoke(),
            5,
            b"forge: commitment audit failed \xe2\x80\x94 cited path does not exist "
            b"within run or repository: evidence/missing.txt "
            b"(verification verification-01 observation)\n",
        )

    def test_arbitrary_extensions_dotfiles_and_extensionless_basis_paths_are_audited(self) -> None:
        def change(records: list[dict[str, object]]) -> None:
            records[3]["basis"] = ["binding-review.pdf", ".forge-manifest"]

        self.mutate(change)
        result = self.invoke()
        self.assertEqual(5, result.returncode)
        self.assertIn(b"binding-review.pdf", result.stderr)

    def test_bare_observation_prose_is_not_treated_as_a_path(self) -> None:
        observations = (
            "+405/-63",
            "+419/-63",
            "check-02/check-06",
            "check-02/06/08/10/12",
            "forge/task-02-spec",
            "tests/test_test_quality.py:92-106",
            "evidence/missing.txt",
        )
        for observation in observations:
            with self.subTest(observation=observation):
                with tempfile.TemporaryDirectory() as temporary:
                    original = self.run_dir
                    self.run_dir = Path(temporary) / "run"
                    shutil.copytree(original, self.run_dir)
                    try:
                        records = self.records()
                        records[4]["observation"] = observation
                        self.write_records(records)
                        result = self.invoke()
                        self.assertEqual(0, result.returncode, result.stderr)
                    finally:
                        self.run_dir = original

    def test_delimited_observation_requires_separator_and_known_suffix(self) -> None:
        def change(records: list[dict[str, object]]) -> None:
            records[4]["observation"] = (
                "Compared `check-02/check-06`, `check-02/06/08/10/12`, "
                "`forge/task-02-spec`, `plans/final`, `missing.txt`, and "
                "`evidence/missing.blorb`."
            )

        self.mutate(change)
        result = self.invoke()
        self.assertEqual(0, result.returncode, result.stderr)

    def test_delimited_trailing_slash_observation_is_audited(self) -> None:
        def change(records: list[dict[str, object]]) -> None:
            records[4]["observation"] = "Expected output in `missing-evidence/`."

        self.mutate(change)
        self.assert_failure(
            self.invoke(),
            5,
            b"forge: commitment audit failed \xe2\x80\x94 cited path does not exist "
            b"within run or repository: missing-evidence/ "
            b"(verification verification-01 observation)\n",
        )

    def test_line_suffix_forms_are_stripped_from_citations(self) -> None:
        def change(records: list[dict[str, object]]) -> None:
            records[3]["basis"] = [
                "docs/repo-basis.md:92",
                "docs/repo-basis.md:92-106",
                "docs/repo-basis.md:92:106",
            ]
            records[4]["observation"] = (
                "Checked `evidence/result.txt:92`, `evidence/result.txt:92-106`, "
                "and `evidence/result.txt:92:106`."
            )

        self.mutate(change)
        result = self.invoke()
        self.assertEqual(0, result.returncode, result.stderr)

    def test_line_range_is_stripped_in_missing_path_diagnostic(self) -> None:
        def change(records: list[dict[str, object]]) -> None:
            records[4]["observation"] = "Checked `evidence/missing.py:92-106`."

        self.mutate(change)
        self.assert_failure(
            self.invoke(),
            5,
            b"forge: commitment audit failed \xe2\x80\x94 cited path does not exist "
            b"within run or repository: evidence/missing.py "
            b"(verification verification-01 observation)\n",
        )

    def test_angle_bracket_and_extensionless_basis_paths_are_audited(self) -> None:
        def change(records: list[dict[str, object]]) -> None:
            records[3]["basis"] = ["[ADR](<plan choice.yaml>)", "Makefile"]

        self.mutate(change)
        result = self.invoke()
        self.assertEqual(5, result.returncode)
        self.assertIn(b"plan choice.yaml", result.stderr)

    def test_structured_task_reference_remains_case_exact(self) -> None:
        def change(records: list[dict[str, object]]) -> None:
            records[3]["task"] = "TASK-07"

        self.mutate(change)
        self.assert_failure(
            self.invoke(),
            3,
            b"forge: commitment audit failed \xe2\x80\x94 unknown task reference: "
            b"TASK-07 (decision decision-01 task field)\n",
        )

    def test_prefixed_unknown_resolution_task_reference_is_exact(self) -> None:
        def change(records: list[dict[str, object]]) -> None:
            records[3]["resolution"] = "Defer sprint-task-99."

        self.mutate(change)
        self.assert_failure(
            self.invoke(),
            3,
            b"forge: commitment audit failed \xe2\x80\x94 unknown task reference: "
            b"sprint-task-99 (decision decision-01 resolution)\n",
        )

    def test_resolution_task_identity_is_case_folded(self) -> None:
        def change(records: list[dict[str, object]]) -> None:
            records[3]["resolution"] = "Complete task-07, then Task-07."

        self.mutate(change)
        result = self.invoke()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(EXPECTED, result.stdout)
        self.assertEqual(b"", result.stderr)

    def test_backticked_command_is_not_a_path(self) -> None:
        def change(records: list[dict[str, object]]) -> None:
            records[3]["basis"] = [
                "`git diff --check`",
                "`check-01`",
                "plans/independent-plan.md",
            ]

        self.mutate(change)
        result = self.invoke()
        self.assertEqual(0, result.returncode, result.stderr)

    def test_backticked_observation_command_is_not_a_path(self) -> None:
        observations = (
            "Ran `python3 scripts/forge/missing.py` successfully.",
            "Result: `see scripts/forge/missing.py`.",
            "Result: `assert path == scripts/forge/missing.py`.",
            "Result: `status check-02/check-06 saved to evidence/missing.txt`.",
        )
        for observation in observations:
            with self.subTest(observation=observation):
                with tempfile.TemporaryDirectory() as temporary:
                    original = self.run_dir
                    self.run_dir = Path(temporary) / "run"
                    shutil.copytree(original, self.run_dir)
                    try:
                        records = self.records()
                        records[4]["observation"] = observation
                        self.write_records(records)
                        result = self.invoke()
                        self.assertEqual(0, result.returncode, result.stderr)
                    finally:
                        self.run_dir = original

    def test_unwrapped_space_basis_path_is_audited(self) -> None:
        def change(records: list[dict[str, object]]) -> None:
            records[3]["basis"] = ["plan choice.yaml"]

        self.mutate(change)
        self.assert_failure(
            self.invoke(),
            5,
            b"forge: commitment audit failed \xe2\x80\x94 cited path does not exist "
            b"within run or repository: plan choice.yaml "
            b"(decision decision-01 basis[0])\n",
        )

    def test_traversal_citation_cannot_escape_roots(self) -> None:
        (self.base / "outside.md").write_text("outside\n", encoding="utf-8")

        def change(records: list[dict[str, object]]) -> None:
            records[3]["basis"] = ["../outside.md"]

        self.mutate(change)
        self.assert_failure(
            self.invoke(),
            5,
            b"forge: commitment audit failed \xe2\x80\x94 cited path does not exist "
            b"within run or repository: ../outside.md "
            b"(decision decision-01 basis[0])\n",
        )

    def test_citation_resolves_on_recorded_execution_branch(self) -> None:
        self.make_branch_artifact("fixture/task-branch", "branch-only/result.txt")

        def change(records: list[dict[str, object]]) -> None:
            records[3]["basis"] = ["branch-only/result.txt"]
            records.insert(
                -1,
                {
                    "type": "execution",
                    "agent": "implementer-01",
                    "execution": "execution-01",
                    "task": "task-07",
                    "role": "review",
                    "branch": "fixture/task-branch",
                },
            )

        self.mutate(change)
        result = self.invoke()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(EXPECTED, result.stdout)

    def test_unrecorded_and_missing_branches_do_not_resolve_or_leak_git_errors(self) -> None:
        self.make_branch_artifact("fixture/unrecorded", "branch-only/result.txt")

        def change(records: list[dict[str, object]]) -> None:
            records[3]["basis"] = ["branch-only/result.txt"]
            records.insert(
                -1,
                {
                    "type": "execution",
                    "agent": "reviewer-01",
                    "execution": "execution-01",
                    "task": "task-07",
                    "role": "review",
                    "branch": "fixture/deleted-or-missing",
                },
            )

        self.mutate(change)
        self.assert_failure(
            self.invoke(),
            5,
            b"forge: commitment audit failed \xe2\x80\x94 cited path does not exist "
            b"within run or repository: branch-only/result.txt "
            b"(decision decision-01 basis[0])\n",
        )

    def test_missing_recorded_branch_is_skipped_before_valid_recorded_branch(
        self,
    ) -> None:
        cited = "branch-only/after-missing.txt"
        self.make_branch_artifact("fixture/valid-after-missing", cited)

        def change(records: list[dict[str, object]]) -> None:
            records[3]["basis"] = [cited]
            insert_at = len(records) - 1
            records[insert_at:insert_at] = [
                {
                    "type": "execution",
                    "agent": "reviewer-missing",
                    "execution": "execution-missing",
                    "task": "task-07",
                    "role": "review",
                    "branch": "fixture/deleted-branch",
                },
                {
                    "type": "execution",
                    "agent": "reviewer-valid",
                    "execution": "execution-valid",
                    "task": "task-07",
                    "role": "review",
                    "branch": "fixture/valid-after-missing",
                },
            ]

        self.mutate(change)
        result = self.invoke()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(b"", result.stderr)

    def test_revision_expressions_are_not_treated_as_recorded_branches(self) -> None:
        cited = "docs/repo-basis.md"
        self.make_branch_artifact(
            "fixture/revision-source", "branch-only/revision-source.txt"
        )
        for revision in ("HEAD", "@{0}", "@{-1}"):
            with self.subTest(revision=revision):
                self.setUp_fixture_again()
                (self.repo / cited).unlink(missing_ok=True)

                def change(
                    records: list[dict[str, object]], branch: str = revision
                ) -> None:
                    records[3]["basis"] = [cited]
                    records.insert(
                        -1,
                        {
                            "type": "execution",
                            "agent": "reviewer-revision",
                            "execution": "execution-revision",
                            "task": "task-07",
                            "role": "review",
                            "branch": branch,
                        },
                    )

                self.mutate(change)
                result = self.invoke()
                self.assertEqual(5, result.returncode)
                self.assertIn(cited.encode(), result.stderr)

    def test_branch_resolution_keeps_absolute_and_traversal_paths_confined(self) -> None:
        self.make_branch_artifact("fixture/task-branch", "outside.md")
        for cited in ("../outside.md", str(self.repo / "outside.md")):
            with self.subTest(cited=cited):
                self.setUp_fixture_again()

                def change(
                    records: list[dict[str, object]], cited_path: str = cited
                ) -> None:
                    records[3]["basis"] = [cited_path]
                    records.insert(
                        -1,
                        {
                            "type": "execution",
                            "agent": "reviewer-01",
                            "execution": "execution-01",
                            "task": "task-07",
                            "role": "review",
                            "branch": "fixture/task-branch",
                        },
                    )

                self.mutate(change)
                result = self.invoke()
                self.assertEqual(5, result.returncode)
                self.assertIn(cited.encode(), result.stderr)

    def test_latest_correction_is_applied_and_reported_with_supplier(self) -> None:
        def change(records: list[dict[str, object]]) -> None:
            records[3]["basis"] = ["missing/original.md"]
            records.insert(
                -1,
                self.correction(
                    "decision-z-first",
                    "decision-01 basis[0]: still/missing.md",
                ),
            )
            records.insert(
                -1,
                self.correction(
                    "decision-a-latest",
                    "decision-01 basis[0]: docs/repo-basis.md",
                ),
            )

        self.mutate(change)
        result = self.invoke()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(b"## Citation Corrections\n", result.stdout)
        self.assertIn(
            b"decision decision-a-latest applied to decision decision-01 basis[0]: "
            b"missing/original.md -> docs/repo-basis.md",
            result.stdout,
        )
        self.assertNotIn(b"decision-z-first applied", result.stdout)

    def test_latest_correction_to_missing_path_remains_fatal(self) -> None:
        def change(records: list[dict[str, object]]) -> None:
            records[3]["basis"] = ["missing/original.md"]
            records.insert(
                -1,
                self.correction(
                    "decision-z-first",
                    "decision-01 basis[0]: docs/repo-basis.md",
                ),
            )
            records.insert(
                -1,
                self.correction(
                    "decision-a-latest",
                    "decision-01 basis[0]: still/missing.md",
                ),
            )

        self.mutate(change)
        result = self.invoke()
        self.assertEqual(5, result.returncode)
        self.assertIn(
            b"still/missing.md (corrected from missing/original.md",
            result.stderr,
        )
        self.assertIn(b"by decision decision-a-latest", result.stderr)

    def test_correction_can_resolve_on_recorded_execution_branch(self) -> None:
        self.make_branch_artifact(
            "fixture/correction-branch", "branch-only/corrected.txt"
        )

        def change(records: list[dict[str, object]]) -> None:
            records[3]["basis"] = ["missing/original.md"]
            records.insert(
                -1,
                {
                    "type": "execution",
                    "agent": "reviewer-correction",
                    "execution": "execution-01",
                    "task": "task-07",
                    "role": "review",
                    "branch": "fixture/correction-branch",
                },
            )
            records.insert(
                -1,
                self.correction(
                    "decision-correction",
                    "decision-01 basis[0]: branch-only/corrected.txt",
                ),
            )

        self.mutate(change)
        result = self.invoke()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(b"missing/original.md -> branch-only/corrected.txt", result.stdout)

    def test_verification_correction_redirects_before_existence_check(self) -> None:
        def change(records: list[dict[str, object]]) -> None:
            records.insert(
                -1,
                self.correction(
                    "decision-correction",
                    "verification-01 observation: evidence/result.txt -> evidence/missing.txt",
                ),
            )

        self.mutate(change)
        self.assert_failure(
            self.invoke(),
            5,
            b"forge: commitment audit failed \xe2\x80\x94 cited path does not exist "
            b"within run or repository: evidence/missing.txt "
            b"(corrected from evidence/result.txt for verification verification-01 "
            b"observation by decision decision-correction)\n",
        )

    def test_corrected_path_remains_confined(self) -> None:
        outside = self.base / "outside.md"
        outside.write_text("outside\n", encoding="utf-8")
        for corrected in ("../outside.md", str(outside)):
            with self.subTest(corrected=corrected):
                self.setUp_fixture_again()

                def change(
                    records: list[dict[str, object]], corrected_path: str = corrected
                ) -> None:
                    records.insert(
                        -1,
                        self.correction(
                            "decision-correction",
                            f"decision-01 basis[0]: {corrected_path}",
                        ),
                    )

                self.mutate(change)
                result = self.invoke()
                self.assertEqual(5, result.returncode)
                self.assertIn(
                    f"{corrected} (corrected from".encode(), result.stderr
                )

    def test_correction_block_stops_at_prose_after_applying_directives(self) -> None:
        def change(records: list[dict[str, object]]) -> None:
            records[3]["basis"] = ["missing/original.md"]
            records.insert(
                -1,
                self.correction(
                    "decision-correction",
                    "decision-01 basis[0]: docs/repo-basis.md",
                    "Each corrected target was verified before writing.",
                    "decision-01 basis[0]: still/missing.md",
                ),
            )

        self.mutate(change)
        result = self.invoke()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(
            b"decision decision-correction applied to decision decision-01 basis[0]: "
            b"missing/original.md -> docs/repo-basis.md",
            result.stdout,
        )
        self.assertNotIn(b"still/missing.md", result.stdout)
        self.assertEqual(b"", result.stderr)

    def test_correction_block_starting_with_prose_applies_no_directives(self) -> None:
        def change(records: list[dict[str, object]]) -> None:
            records[3]["basis"] = ["missing/original.md"]
            records.insert(
                -1,
                self.correction(
                    "decision-correction",
                    "This entry contains explanatory prose only.",
                    "decision-01 basis[0]: docs/repo-basis.md",
                ),
            )

        self.mutate(change)
        self.assert_failure(
            self.invoke(),
            5,
            b"forge: commitment audit failed \xe2\x80\x94 cited path does not exist "
            b"within run or repository: missing/original.md "
            b"(decision decision-01 basis[0])\n",
        )

    def test_mistyped_correction_directive_is_prose_and_leaves_citation_loud(self) -> None:
        def change(records: list[dict[str, object]]) -> None:
            records[3]["basis"] = ["missing/original.md"]
            records.insert(
                -1,
                self.correction(
                    "decision-correction",
                    "decision-01 basis[0] docs/repo-basis.md",
                ),
            )

        self.mutate(change)
        self.assert_failure(
            self.invoke(),
            5,
            b"forge: commitment audit failed \xe2\x80\x94 cited path does not exist "
            b"within run or repository: missing/original.md "
            b"(decision decision-01 basis[0])\n",
        )

    def test_unknown_correction_target_has_distinct_exit_code_and_exact_diagnostic(self) -> None:
        def change(records: list[dict[str, object]]) -> None:
            records.insert(
                -1,
                self.correction(
                    "decision-correction",
                    "decision-01 basis[99]: docs/repo-basis.md",
                ),
            )

        self.mutate(change)
        self.assert_failure(
            self.invoke(),
            6,
            b"forge: commitment audit failed \xe2\x80\x94 citation correction target "
            b"does not exist: decision decision-01 basis[99] "
            b"(supplied by decision decision-correction)\n",
        )

    def test_unknown_verification_correction_token_is_exit_six(self) -> None:
        def change(records: list[dict[str, object]]) -> None:
            records.insert(
                -1,
                self.correction(
                    "decision-correction",
                    "verification-01 observation: evidence/other.txt -> evidence/result.txt",
                ),
            )

        self.mutate(change)
        result = self.invoke()
        self.assertEqual(6, result.returncode)
        self.assertIn(
            b"verification verification-01 observation token evidence/other.txt",
            result.stderr,
        )

    def test_unknown_correction_ids_are_exit_six(self) -> None:
        cases = (
            (
                "decision-missing basis[0]: docs/repo-basis.md",
                b"decision decision-missing basis[0]",
            ),
            (
                "verification-missing observation: evidence/result.txt -> "
                "docs/repo-basis.md",
                b"verification verification-missing observation token evidence/result.txt",
            ),
        )
        for correction_line, expected in cases:
            with self.subTest(correction_line=correction_line):
                self.setUp_fixture_again()

                def change(
                    records: list[dict[str, object]], line: str = correction_line
                ) -> None:
                    records.insert(-1, self.correction("decision-correction", line))

                self.mutate(change)
                result = self.invoke()
                self.assertEqual(6, result.returncode)
                self.assertIn(expected, result.stderr)

    def test_new_controls_are_killed_when_disabled_in_temp_copies(self) -> None:
        source = AUDIT.read_text(encoding="utf-8")

        with self.subTest(control="branch-aware"):
            self.make_branch_artifact(
                "fixture/mutation-branch", "branch-only/mutation.txt"
            )

            def branch_fixture(records: list[dict[str, object]]) -> None:
                records[3]["basis"] = ["branch-only/mutation.txt"]
                records.insert(
                    -1,
                    {
                        "type": "execution",
                        "agent": "reviewer-mutation",
                        "execution": "execution-01",
                        "task": "task-07",
                        "role": "review",
                        "branch": "fixture/mutation-branch",
                    },
                )

            self.mutate(branch_fixture)
            intact = self.invoke()
            self.assertEqual(0, intact.returncode, intact.stderr)
            mutant = self.disabled_control_copy(
                source, "branch-aware", "    return False\n"
            )
            disabled = self.invoke(mutant)
            self.assertEqual(5, disabled.returncode)
            self.assertIn(b"branch-only/mutation.txt", disabled.stderr)

        with self.subTest(control="citation-correction"):
            self.setUp_fixture_again()

            def correction_fixture(records: list[dict[str, object]]) -> None:
                records[3]["basis"] = ["missing/original.md"]
                records.insert(
                    -1,
                    self.correction(
                        "decision-mutation-correction",
                        "decision-01 basis[0]: docs/repo-basis.md",
                    ),
                )

            self.mutate(correction_fixture)
            intact = self.invoke()
            self.assertEqual(0, intact.returncode, intact.stderr)
            mutant = self.disabled_control_copy(source, "citation-correction", "    pass\n")
            disabled = self.invoke(mutant)
            self.assertEqual(5, disabled.returncode)
            self.assertIn(b"missing/original.md", disabled.stderr)

    def test_invalid_repository_root_is_exact(self) -> None:
        def change(records: list[dict[str, object]]) -> None:
            records[0]["repo"] = str(self.base / "absent-repository")

        self.mutate(change)
        self.assert_failure(
            self.invoke(),
            2,
            b"forge: commitment audit failed \xe2\x80\x94 run_started repo must name "
            b"an existing absolute directory\n",
        )

    def test_malformed_present_commitment_array_is_exact(self) -> None:
        def change(records: list[dict[str, object]]) -> None:
            records[-1]["risks"] = "not an array"

        self.mutate(change)
        self.assert_failure(
            self.invoke(),
            2,
            b"forge: commitment audit failed \xe2\x80\x94 run_closed risks must be "
            b"an array of non-empty strings\n",
        )

    def test_each_control_is_killed_when_disabled_in_a_temp_copy(self) -> None:
        mutations = (
            (
                "unknown-task",
                lambda records: records[3].__setitem__("task", "task-99"),
                b"unknown task reference",
            ),
            (
                "terminal-task",
                lambda records: records[5].__setitem__("status", "active"),
                b"task is non-terminal",
            ),
            (
                "cited-path",
                lambda records: records[3].__setitem__(
                    "basis", ["findings/never-written.md"]
                ),
                b"cited path does not exist",
            ),
        )
        source = AUDIT.read_text(encoding="utf-8")
        for marker, mutate, expected in mutations:
            with self.subTest(control=marker):
                # First prove the intact control observes the broken fixture.
                self.mutate(mutate)
                intact = self.invoke()
                self.assertNotEqual(0, intact.returncode)
                self.assertIn(expected, intact.stderr)

                # Disable only that stable enforcement block in a temp copy.
                begin = f"    # CONTROL {marker} BEGIN\n"
                end = f"    # CONTROL {marker} END\n"
                before, rest = source.split(begin, 1)
                _, after = rest.split(end, 1)
                mutant = AUDIT.parent / f".audit-{marker}-disabled.py"
                self.addCleanup(mutant.unlink, missing_ok=True)
                mutant.write_text(
                    before + begin + "    pass\n" + end + after,
                    encoding="utf-8",
                )
                disabled = self.invoke(mutant)
                self.assertEqual(0, disabled.returncode, disabled.stderr)
                self.assertEqual(EXPECTED, disabled.stdout)
                self.assertEqual(b"", disabled.stderr)

                # Restore the pristine fixture for the next subtest.
                self.setUp_fixture_again()

    def disabled_control_copy(self, source: str, marker: str, replacement: str) -> Path:
        begin = f"    # CONTROL {marker} BEGIN\n"
        end = f"    # CONTROL {marker} END\n"
        before, rest = source.split(begin, 1)
        _, after = rest.split(end, 1)
        mutant = AUDIT.parent / f".audit-{marker}-disabled.py"
        self.addCleanup(mutant.unlink, missing_ok=True)
        mutant.write_text(
            before + begin + replacement + end + after,
            encoding="utf-8",
        )
        return mutant

    def setUp_fixture_again(self) -> None:
        shutil.rmtree(self.run_dir)
        shutil.copytree(FIXTURE, self.run_dir)
        fixture = (self.run_dir / "journal.jsonl").read_text(encoding="utf-8")
        (self.run_dir / "journal.jsonl").write_text(
            fixture.replace("__REPO__", str(self.repo)), encoding="utf-8"
        )


if __name__ == "__main__":
    unittest.main()
