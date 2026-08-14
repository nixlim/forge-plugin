from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "scripts/codex_orch_tools.py"

import sys

sys.path.insert(0, str(ROOT / "scripts"))
from codex_orchestrator import journal  # noqa: E402


class RunCoordinationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="forge-run-registry-")
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name) / "repo"
        subprocess.run(["git", "init", "--quiet", str(self.repo)], check=True)
        self.env = os.environ.copy()
        self.env["FORGE_SESSION_PID"] = str(os.getpid())

    def record(self, name: str, value: dict[str, object]) -> Path:
        target = Path(self.temporary.name) / name
        target.write_text(json.dumps(value), encoding="utf-8")
        return target

    def command(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return self.command_with(TOOLS, self.env, *arguments)

    def command_with(
        self, tools: Path, environment: dict[str, str], *arguments: str
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(tools), *arguments],
            cwd=self.repo,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

    def mutant_tools(self, name: str, needle: str, replacement: str) -> tuple[Path, dict[str, str]]:
        mutant_root = Path(self.temporary.name) / name
        shutil.copytree(ROOT / "scripts/codex_orchestrator", mutant_root / "codex_orchestrator")
        (mutant_root / "forge").mkdir()
        shutil.copy2(
            ROOT / "scripts/forge/commitment_paths.py",
            mutant_root / "forge/commitment_paths.py",
        )
        shutil.copy2(TOOLS, mutant_root / "codex_orch_tools.py")
        source_path = mutant_root / "codex_orchestrator/journal.py"
        source = source_path.read_text(encoding="utf-8")
        self.assertEqual(source.count(needle), 1)
        source_path.write_text(source.replace(needle, replacement), encoding="utf-8")
        environment = dict(self.env)
        environment["PYTHONPATH"] = str(mutant_root)
        return mutant_root / "codex_orch_tools.py", environment

    def open(self, run_id: str, *scope: str) -> subprocess.CompletedProcess[str]:
        opening = self.record(
            f"{run_id}-open.json", {"type": "run_started", "run_id": run_id}
        )
        arguments = ["run-open", "--repo", str(self.repo), "--run-id", run_id]
        for item in scope:
            arguments.extend(("--scope", item))
        arguments.extend(("--record-json", str(opening)))
        return self.command(*arguments)

    def registry_bytes(self) -> bytes:
        return (self.repo / ".forge/tmp/run-registry.json").read_bytes()

    def journal_path(self, run_id: str) -> Path:
        return self.repo / ".codex-orchestrator/runs" / run_id / "journal.jsonl"

    def test_open_is_atomic_and_registry_is_canonical(self) -> None:
        """FR-191/FR-192 and DM-010/DM-011: atomically open a registered owned run."""
        result = self.open("run-b", "src/b/**", "src/b/**")

        self.assertEqual(result.returncode, 0, result.stderr)
        run_dir = self.journal_path("run-b").parent
        owner = (run_dir / "owner").read_bytes()
        lines = owner.decode("utf-8").splitlines()
        self.assertEqual(lines[0], f"pid: {os.getpid()}")
        self.assertEqual(lines[1], f"host: {socket.gethostname()}")
        self.assertRegex(lines[2], r"^started_at: .+Z$")
        self.assertEqual(len(lines), 3)
        self.assertTrue(owner.endswith(b"\n"))
        self.assertEqual(
            self.registry_bytes(),
            b'{"open_runs":[{"run_id":"run-b","scope":["src/b/**"]}],"schema_version":1}\n',
        )
        first = json.loads(self.journal_path("run-b").read_text().splitlines()[0])
        self.assertEqual(first["scope"], ["src/b/**"])

    def test_disjoint_admission_and_exact_overlap_refusal(self) -> None:
        """FR-014/FR-192 and DM-011: admit disjoint scopes and refuse exact overlap."""
        self.assertEqual(self.open("run-A", "src/a/**").returncode, 0)
        before = self.journal_path("run-A").read_bytes()
        self.assertEqual(self.open("run-B", "src/b/**").returncode, 0)

        refused = self.open("run-C", "src/a/shared.py")

        self.assertEqual(refused.returncode, 1)
        self.assertEqual(
            refused.stderr,
            "forge: new run refused — scope overlap between run-C and open run run-A\n",
        )
        self.assertEqual(self.journal_path("run-A").read_bytes(), before)
        self.assertFalse(self.journal_path("run-C").exists())

    def test_glob_pairs_fail_conservatively_and_dot_run_is_refused(self) -> None:
        """FR-014/FR-192 and DM-011: fail closed for ambiguous globs and run state."""
        self.assertTrue(journal.pathspecs_overlap("[ab]x", "a[xy]"))
        self.assertTrue(journal.pathspecs_overlap("src/[ab].py", "src/a[xy].py"))
        self.assertTrue(journal.pathspecs_overlap("x[ab]", "x[bc]"))

        refused = self.open(".hidden", "src/a/**")
        self.assertEqual(refused.returncode, 1)
        self.assertEqual(refused.stderr, journal.REGISTRY_UNAVAILABLE + "\n")

    def test_crashed_dot_opening_fails_closed_and_disabled_control_is_detected(self) -> None:
        """FR-014/FR-192 and DM-011: detect removal of crashed-state protection."""
        self.assertEqual(self.open("run-A", "src/a/**").returncode, 0)
        registry_before = self.registry_bytes()
        journal_before = self.journal_path("run-A").read_bytes()
        crashed = self.repo / ".codex-orchestrator/runs/.run-B.open.crashed"
        crashed.mkdir()
        (crashed / "owner").write_text(
            f"pid: {os.getpid()}\nhost: {socket.gethostname()}\n"
            "started_at: 2026-08-13T00:00:00Z\n",
            encoding="utf-8",
        )
        (crashed / "journal.jsonl").write_text(
            '{"run_id":"run-B","scope":["src/b/**"],"type":"run_started"}\n',
            encoding="utf-8",
        )

        refused = self.open("run-B", "src/b/**")

        self.assertEqual(refused.returncode, 1)
        self.assertEqual(refused.stderr, journal.REGISTRY_UNAVAILABLE + "\n")
        self.assertEqual(self.registry_bytes(), registry_before)
        self.assertEqual(self.journal_path("run-A").read_bytes(), journal_before)
        self.assertFalse(self.journal_path("run-B").exists())

        mutant, environment = self.mutant_tools(
            "dot-opening-mutant",
            '    if any(entry.name.startswith(".") for entry in entries):\n'
            "        raise CoordinationRefusal(REGISTRY_UNAVAILABLE)\n",
            "    entries = [entry for entry in entries "
            "if not entry.name.startswith('.') ]  # control disabled by mutant\n",
        )
        opening = self.record(
            "run-mutant-open.json", {"type": "run_started", "run_id": "run-mutant"}
        )
        bypassed = self.command_with(
            mutant,
            environment,
            "run-open", "--repo", str(self.repo), "--run-id", "run-mutant",
            "--scope", "src/mutant/**", "--record-json", str(opening),
        )
        self.assertEqual(bypassed.returncode, 0, bypassed.stderr)

    def test_foreign_owner_refuses_every_append_without_byte_change(self) -> None:
        """FR-191 and DM-010: refuse a foreign owner without changing journal bytes."""
        self.assertEqual(self.open("run-A", "src/a/**").returncode, 0)
        owner = self.journal_path("run-A").parent / "owner"
        owner.write_text(
            "pid: 42\nhost: remote-host\nstarted_at: 2026-08-13T00:00:00Z\n",
            encoding="utf-8",
        )
        before = self.journal_path("run-A").read_bytes()
        record = self.record(
            "verification.json", {"type": "verification", "id": "verification-1"}
        )

        refused = self.command(
            "journal-append",
            "--repo",
            str(self.repo),
            "--run-id",
            "run-A",
            "--record-json",
            str(record),
        )

        self.assertEqual(refused.returncode, 1)
        self.assertEqual(
            refused.stderr,
            "forge: journal append refused — run run-A has live owner 42@remote-host\n",
        )
        self.assertEqual(self.journal_path("run-A").read_bytes(), before)

    def test_missing_and_malformed_owner_refuse_without_append(self) -> None:
        """FR-191 and DM-010: refuse missing or malformed owners without appending."""
        for malformed in (None, b"pid: nope\n"):
            run_id = "missing" if malformed is None else "malformed"
            self.assertEqual(self.open(run_id, f"src/{run_id}/**").returncode, 0)
            owner = self.journal_path(run_id).parent / "owner"
            if malformed is None:
                owner.unlink()
            else:
                owner.write_bytes(malformed)
            before = self.journal_path(run_id).read_bytes()
            record = self.record(
                f"{run_id}.json", {"type": "verification", "id": f"verify-{run_id}"}
            )
            refused = self.command(
                "journal-append", "--repo", str(self.repo), "--run-id", run_id,
                "--record-json", str(record),
            )
            self.assertEqual(
                refused.stderr,
                f"forge: journal append refused — owner record missing or malformed for run {run_id}\n",
            )
            self.assertEqual(self.journal_path(run_id).read_bytes(), before)

    def test_same_host_dead_pid_is_taken_over(self) -> None:
        """FR-191 and DM-010: allow takeover only for a proven-dead same-host owner."""
        self.assertEqual(self.open("run-A", "src/a/**").returncode, 0)
        owner = self.journal_path("run-A").parent / "owner"
        owner.write_text(
            f"pid: 2147483647\nhost: {socket.gethostname()}\nstarted_at: 2026-08-13T00:00:00Z\n",
            encoding="utf-8",
        )
        record = self.record("takeover.json", {"type": "verification", "id": "takeover"})

        result = self.command(
            "journal-append", "--repo", str(self.repo), "--run-id", "run-A",
            "--record-json", str(record),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(owner.read_text().startswith(f"pid: {os.getpid()}\n"))
        self.assertEqual(len(self.journal_path("run-A").read_text().splitlines()), 2)

    def test_os_unrepresentable_pid_is_foreign_and_overflow_mutant_is_detected(self) -> None:
        """FR-191 and DM-010: treat an OS-unrepresentable PID as foreign ownership."""
        self.assertEqual(self.open("run-A", "src/a/**").returncode, 0)
        owner = self.journal_path("run-A").parent / "owner"
        huge_pid = "9" * 1000
        owner.write_text(
            f"pid: {huge_pid}\nhost: {socket.gethostname()}\n"
            "started_at: 2026-08-13T00:00:00Z\n",
            encoding="utf-8",
        )
        owner_before = owner.read_bytes()
        journal_before = self.journal_path("run-A").read_bytes()
        record = self.record("overflow.json", {"type": "verification", "id": "overflow"})

        refused = self.command(
            "journal-append", "--repo", str(self.repo), "--run-id", "run-A",
            "--record-json", str(record),
        )

        self.assertEqual(refused.returncode, 1)
        self.assertEqual(
            refused.stderr,
            f"forge: journal append refused — run run-A has live owner "
            f"{huge_pid}@{socket.gethostname()}\n",
        )
        self.assertEqual(owner.read_bytes(), owner_before)
        self.assertEqual(self.journal_path("run-A").read_bytes(), journal_before)

        mutant, environment = self.mutant_tools(
            "pid-overflow-mutant",
            "    except OverflowError:\n"
            "        # A syntactically valid but OS-unrepresentable PID cannot be proven\n"
            "        # dead, so DM-010 classifies it as unverifiable foreign ownership.\n"
            "        return None\n",
            "",
        )
        crashed = self.command_with(
            mutant,
            environment,
            "journal-append", "--repo", str(self.repo), "--run-id", "run-A",
            "--record-json", str(record),
        )
        self.assertNotEqual(crashed.returncode, 0)
        self.assertIn("OverflowError", crashed.stderr)

    def test_citation_corrections_require_strict_grammar_and_preserve_history(self) -> None:
        """FR-191: enforce citation-correction grammar while preserving history."""
        self.assertEqual(self.open("run-A", "src/a/**").returncode, 0)
        entries = (
            {
                "type": "decision",
                "id": "decision-source",
                "basis": ["old/decision.txt"],
                "resolution": "keep evidence",
            },
            {
                "type": "verification",
                "id": "verification-source",
                "observation": "checked `old/verification.txt`",
                "result": "passed",
            },
            {
                "type": "decision",
                "id": "correction-one",
                "resolution": (
                    "citation-correction:\n"
                    "decision-source basis[0]: first/decision.txt\n"
                    "verification-source observation: old/verification.txt -> first/verification.txt"
                ),
            },
            {
                "type": "decision",
                "id": "correction-two",
                "resolution": (
                    "citation-correction:\n"
                    "decision-source basis[0]: latest/decision.txt"
                ),
            },
        )
        for index, entry in enumerate(entries):
            record = self.record(f"citation-{index}.json", entry)
            appended = self.command(
                "journal-append", "--repo", str(self.repo), "--run-id", "run-A",
                "--record-json", str(record),
            )
            self.assertEqual(appended.returncode, 0, appended.stderr)

        records = [
            json.loads(line)
            for line in self.journal_path("run-A").read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(records[1]["basis"], ["old/decision.txt"])
        self.assertEqual(records[2]["observation"], "checked `old/verification.txt`")
        self.assertEqual(records[3]["resolution"], entries[2]["resolution"])
        self.assertEqual(records[4]["resolution"], entries[3]["resolution"])

        nonexistent = self.record(
            "citation-nonexistent.json",
            {
                "type": "decision",
                "id": "correction-nonexistent",
                "resolution": (
                    "citation-correction:\n"
                    "verification-source observation: checked `old/verification.txt` -> ignored.txt"
                ),
            },
        )
        refused_target = self.command(
            "journal-append", "--repo", str(self.repo), "--run-id", "run-A",
            "--record-json", str(nonexistent),
        )
        self.assertEqual(refused_target.returncode, 1)
        self.assertEqual(
            refused_target.stderr,
            "forge: journal append refused — citation correction target does not exist\n",
        )

        malformed = self.record(
            "citation-malformed.json",
            {
                "type": "decision",
                "id": "correction-malformed",
                # FR-191/FR-173: a directive followed by prose is accepted (the
                # block ends at the first non-directive line). What is refused is
                # a correction that supplies no directive at all.
                "resolution": (
                    "citation-correction:\n"
                    "explanatory prose is not a directive"
                ),
            },
        )
        before = self.journal_path("run-A").read_bytes()
        refused = self.command(
            "journal-append", "--repo", str(self.repo), "--run-id", "run-A",
            "--record-json", str(malformed),
        )
        self.assertEqual(refused.returncode, 1)
        self.assertEqual(
            refused.stderr,
            "forge: journal append refused — invalid citation correction\n",
        )
        self.assertEqual(self.journal_path("run-A").read_bytes(), before)

        with mock.patch.dict(os.environ, {"FORGE_SESSION_PID": str(os.getpid())}):
            original = journal._citation_correction_lines

            def permissive(record: dict[str, object]) -> tuple[str, ...] | None:
                try:
                    return original(record)
                except journal.CoordinationRefusal:
                    return ("decision-source basis[0]: ignored/decision.txt",)

            with mock.patch.object(
                journal, "_citation_correction_lines", side_effect=permissive
            ):
                journal.append_run_record(
                    self.repo, "run-A", json.loads(malformed.read_text(encoding="utf-8"))
                )
        self.assertNotEqual(self.journal_path("run-A").read_bytes(), before)
        validation = journal.validate_run(self.journal_path("run-A").parent)
        self.assertFalse(validation["ok"])
        self.assertTrue(
            any("invalid citation correction" in issue for issue in validation["issues"])
        )

    def test_task_containment_and_readmission_cannot_shrink_existing_tasks(self) -> None:
        """FR-014/FR-192: keep task files in scope and forbid shrinking readmission."""
        self.assertEqual(self.open("run-A", "src/a/**").returncode, 0)
        task = self.record(
            "task.json",
            {"type": "task", "id": "task-1", "status": "active", "files": ["src/a/x.py"]},
        )
        self.assertEqual(
            self.command(
                "journal-append", "--repo", str(self.repo), "--run-id", "run-A",
                "--record-json", str(task),
            ).returncode,
            0,
        )
        before = self.journal_path("run-A").read_bytes()

        refused = self.command(
            "run-readmit", "--repo", str(self.repo), "--run-id", "run-A",
            "--scope", "src/a/other.py",
        )

        self.assertEqual(refused.returncode, 1)
        self.assertIn("task files exceed admitted scope", refused.stderr)
        self.assertEqual(self.journal_path("run-A").read_bytes(), before)
        self.assertIn(b'"scope":["src/a/**"]', self.registry_bytes())

    def test_append_path_cannot_bypass_retirement(self) -> None:
        """FR-014/FR-192 and DM-011: prevent append paths from bypassing retirement."""
        self.assertEqual(self.open("run-A", "src/a/**").returncode, 0)
        journal_path = self.journal_path("run-A")
        before_retire = journal_path.read_bytes()
        self.assertEqual(
            self.command("run-retire", "--repo", str(self.repo), "--run-id", "run-A").returncode,
            0,
        )
        retired = journal_path.read_bytes()
        self.assertNotEqual(retired, before_retire)

        with mock.patch.dict(os.environ, {"FORGE_SESSION_PID": str(os.getpid())}):
            with self.assertRaisesRegex(journal.CoordinationRefusal, "run registry unavailable"):
                journal.append_owned_record(
                    journal_path, {"type": "verification", "id": "too-late"}
                )
        self.assertEqual(journal_path.read_bytes(), retired)

    def test_registry_write_failure_rolls_back_readmission_journal(self) -> None:
        """FR-192 and DM-011: roll back journal scope when registry replacement fails."""
        with mock.patch.dict(os.environ, {"FORGE_SESSION_PID": str(os.getpid())}):
            journal.open_run(
                self.repo,
                "run-A",
                ["src/a/**"],
                {"type": "run_started", "run_id": "run-A"},
            )
            before = self.journal_path("run-A").read_bytes()
            real_replace = journal._atomic_replace

            def fail_registry(path: Path, payload: bytes) -> None:
                if path.name == "run-registry.json":
                    raise OSError("mutant disabled registry replace")
                real_replace(path, payload)

            with mock.patch.object(journal, "_atomic_replace", side_effect=fail_registry):
                with self.assertRaises(journal.CoordinationRefusal):
                    journal.readmit_run(self.repo, "run-A", ["src/a/**", "src/shared/**"])

            self.assertEqual(self.journal_path("run-A").read_bytes(), before)

    def test_admission_sensor_kills_disabled_overlap_control_copy(self) -> None:
        """FR-014/FR-192 and DM-011: prove overlap sensing kills a disabled control."""
        self.assertEqual(self.open("run-A", "src/shared/**").returncode, 0)
        self.assertEqual(self.open("run-B", "src/shared/file.py").returncode, 1)

        mutant, environment = self.mutant_tools(
            "admission-overlap-mutant",
            "            if scopes_overlap(scope, other_scope)\n",
            "            if False  # overlap control disabled by mutant\n",
        )
        opening = self.record(
            "run-B-mutant-open.json", {"type": "run_started", "run_id": "run-B-mutant"}
        )
        bypassed = self.command_with(
            mutant,
            environment,
            "run-open", "--repo", str(self.repo), "--run-id", "run-B-mutant",
            "--scope", "src/shared/file.py", "--record-json", str(opening),
        )
        self.assertEqual(bypassed.returncode, 0, bypassed.stderr)
        registry = json.loads(self.registry_bytes())
        self.assertEqual(
            {item["run_id"] for item in registry["open_runs"]},
            {"run-A", "run-B-mutant"},
        )


if __name__ == "__main__":
    unittest.main()
