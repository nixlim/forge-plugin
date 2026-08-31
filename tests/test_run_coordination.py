from __future__ import annotations

import json
import os
import re
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
    RECORDED_AT = "2026-08-26T12:00:00Z"

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="forge-run-registry-")
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name) / "repo"
        subprocess.run(["git", "init", "--quiet", str(self.repo)], check=True)
        self.env = os.environ.copy()
        self.env["FORGE_SESSION_PID"] = str(os.getpid())

    def strict_record(self, value: dict[str, object]) -> dict[str, object]:
        kind = value.get("type")
        defaults: dict[str, dict[str, object]] = {
            "run_started": {
                "recorded_at": self.RECORDED_AT,
                "goal": "Exercise run coordination",
                "repo": str(self.repo.resolve()),
                "repo_head": "0" * 40,
                "repo_status": [],
                "plugin_ref": "forge-test",
            },
            "task": {
                "recorded_at": self.RECORDED_AT,
                "id": "task-01",
                "status": "active",
                "goal": "Exercise the bounded task",
                "acceptance": ["The focused behavior holds"],
                "files": ["src/example.py"],
            },
            "execution": {
                "recorded_at": self.RECORDED_AT,
                "agent": "codex-impl-01",
                "task": "task-01",
                "provider": "openai",
                "role": "implementation",
                "mode": "headless",
                "model": "gpt-test",
                "effort": "high",
                "execution": "execution-01",
                "worktree": str(self.repo.resolve()),
                "head": "0" * 40,
                "prompt": "prompt.md",
                "handoff": "handoff.md",
                "event_source": "exec",
                "events": "events.jsonl",
            },
            "execution_result": {
                "recorded_at": self.RECORDED_AT,
                "agent": "codex-impl-01",
                "task": "task-01",
                "summary": "Execution completed",
                "execution": "execution-01",
                "status": "complete",
                "files_changed": [],
                "caveats": [],
                "handoff": "handoff.md",
            },
            "verification": {
                "recorded_at": self.RECORDED_AT,
                "id": "check-01",
                "task": "task-01",
                "criterion": "Focused behavior",
                "method": "unittest",
                "check": "python3 -m unittest",
                "observation": "Focused behavior observed",
                "result": "passed",
            },
            "decision": {
                "recorded_at": self.RECORDED_AT,
                "id": "decision-01",
                "resolution": "Use the coordinated path",
            },
            "run_closed": {
                "recorded_at": self.RECORDED_AT,
                "judgment": "passed",
                "summary": "Run completed",
                "validation": {
                    "ok": True,
                    "issues": [],
                    "warnings": [],
                    "non_passing_verifications": [],
                    "profile": "gates",
                },
                "risks": [],
                "follow_ups": [],
            },
        }
        completed = dict(defaults.get(str(kind), {}))
        completed.update(value)
        return completed

    def record(self, name: str, value: dict[str, object]) -> Path:
        target = Path(self.temporary.name) / name
        target.write_text(json.dumps(self.strict_record(value)), encoding="utf-8")
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

    def coordination_bytes(self, run_id: str) -> tuple[bytes, bytes, bytes]:
        run_dir = self.journal_path(run_id).parent
        return (
            self.journal_path(run_id).read_bytes(),
            (run_dir / "owner").read_bytes(),
            self.registry_bytes(),
        )

    def activate_writer_contract(self, run_id: str) -> None:
        journal_path = self.journal_path(run_id)
        opening = json.loads(journal_path.read_text(encoding="utf-8"))
        opening["writer_contract"] = journal.WRITER_CONTRACT
        journal_path.write_bytes(journal._journal_payload(opening))

    def outside_citation(self, run_id: str, name: str) -> str:
        outside = Path(self.temporary.name) / "outside" / name
        outside.parent.mkdir(parents=True, exist_ok=True)
        outside.write_text("outside\n", encoding="utf-8")
        return Path(
            os.path.relpath(outside, self.journal_path(run_id).parent)
        ).as_posix()

    def test_open_is_atomic_and_registry_is_canonical(self) -> None:
        """FR-191/FR-192 and DM-010/DM-011: atomically open a registered owned run."""
        result = self.open("run-b", "src/a/**", "src/b/**")

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
            b'{"open_runs":[{"run_id":"run-b","scope":["src/a/**","src/b/**"]}],"schema_version":1}\n',
        )
        first = json.loads(self.journal_path("run-b").read_text().splitlines()[0])
        self.assertEqual(first["scope"], ["src/a/**", "src/b/**"])

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

    def plant_legacy_journal(self, run_id: str, *, closed: bool) -> Path:
        """Write a pre-D13 journal: identity keyed `id` (not `run_id`), no scope.

        The real repository carries two such journals from the pre-coordination
        orchestrator; one ends with a post-close citation-correction decision,
        which the old FR-120 correction rule explicitly allowed.
        """
        run_dir = self.repo / ".codex-orchestrator/runs" / run_id
        run_dir.mkdir(parents=True)
        records: list[dict[str, object]] = [
            {"type": "run_started", "id": run_id, "goal": "legacy"},
            {"type": "verification", "id": "verify-01", "task": "task-01", "result": "passed"},
        ]
        if closed:
            records.append({"type": "run_closed", "id": run_id, "judgment": "passed"})
            # Mirror the real run-20260811 tail: the old FR-120 correction rule
            # appended a re-verification AND a citation-correction decision.
            records.append(
                {"type": "verification", "id": "verify-90", "task": "task-01", "result": "passed"}
            )
            records.append(
                {
                    "type": "decision",
                    "id": "decision-90",
                    "resolution": "citation-correction: verify-01 observation: a -> b",
                }
            )
        journal_file = run_dir / "journal.jsonl"
        journal_file.write_text(
            "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
        )
        return journal_file

    def test_closed_legacy_journal_does_not_poison_admission(self) -> None:
        """FR-014: journals that carry run_closed are excluded from admission, so a
        closed pre-D13 journal (legacy `id` key, trailing correction decision) must
        not make the registry unavailable for every future run."""
        legacy = self.plant_legacy_journal("run-legacy-closed", closed=True)
        before = legacy.read_bytes()

        result = self.open("run-a", "src/a/**")

        self.assertEqual(result.returncode, 0, result.stderr)
        registry = json.loads(self.registry_bytes())
        self.assertEqual(
            [item["run_id"] for item in registry["open_runs"]], ["run-a"]
        )
        self.assertEqual(legacy.read_bytes(), before)

    def test_post_close_tolerance_is_denied_to_d13_journals(self) -> None:
        """The trailing-record tolerance is for pre-D13 journals only: a run_id-keyed
        journal with any record after run_closed is corrupt and must refuse."""
        run_dir = self.repo / ".codex-orchestrator/runs/run-d13-trailing"
        run_dir.mkdir(parents=True)
        records = [
            {"type": "run_started", "run_id": "run-d13-trailing", "scope": ["src/x/**"]},
            {"type": "run_closed", "run_id": "run-d13-trailing", "judgment": "passed"},
            {"type": "decision", "id": "decision-01", "resolution": "late append"},
        ]
        (run_dir / "journal.jsonl").write_text(
            "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
        )

        refused = self.open("run-a", "src/a/**")

        self.assertEqual(refused.returncode, 1)
        self.assertEqual(refused.stderr, journal.REGISTRY_UNAVAILABLE + "\n")

    def test_post_close_tolerance_rejects_untolerated_record_types(self) -> None:
        """Legacy tolerance covers only the correction shapes the old FR-120 rule
        produced (verification, decision); anything else after run_closed refuses."""
        legacy = self.plant_legacy_journal("run-legacy-tail", closed=True)
        records = legacy.read_text(encoding="utf-8").splitlines()
        records.append(json.dumps({"type": "task", "id": "task-99"}))
        legacy.write_text("\n".join(records) + "\n", encoding="utf-8")

        refused = self.open("run-a", "src/a/**")

        self.assertEqual(refused.returncode, 1)
        self.assertEqual(refused.stderr, journal.REGISTRY_UNAVAILABLE + "\n")

    @unittest.skipUnless(
        (ROOT / ".codex-orchestrator/runs/run-20260811-verification-expansion").is_dir(),
        "real legacy run journals not present in this checkout",
    )
    def test_real_legacy_journals_admit_a_new_run(self) -> None:
        """End-to-end against the real pre-D13 journals: copy them into the fixture
        repo and prove run-open admits a new run. This is the exact defect that
        blocked the first real run-open (COR-05: the decisions-only tolerance was
        written against an assumed tail; the real tail is run_closed ->
        verification -> decision)."""
        source = ROOT / ".codex-orchestrator/runs"
        target = self.repo / ".codex-orchestrator/runs"
        target.mkdir(parents=True)
        for run_dir in source.iterdir():
            # A LIVE open run (owner sidecar present — e.g. the run coordinating
            # this very change) is out of scope here: copying it without the live
            # registry correctly fails closed as an unregistered open-run scope
            # (FR-014). This test targets the closed pre-D13 journals only.
            if (run_dir / "owner").is_file():
                continue
            if (run_dir / "journal.jsonl").is_file():
                (target / run_dir.name).mkdir()
                shutil.copy2(
                    run_dir / "journal.jsonl", target / run_dir.name / "journal.jsonl"
                )

        result = self.open("run-a", "src/a/**")

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_legacy_identity_must_match_directory(self) -> None:
        """The identity leg of the closed-journal tolerance: a legacy journal whose
        `id` disagrees with its directory name is corrupt state and must refuse —
        the tolerance never waives identity."""
        legacy = self.plant_legacy_journal("run-legacy-mismatch", closed=True)
        records = legacy.read_text(encoding="utf-8").splitlines()
        first = json.loads(records[0])
        first["id"] = "run-some-other-name"
        records[0] = json.dumps(first)
        legacy.write_text("\n".join(records) + "\n", encoding="utf-8")

        refused = self.open("run-a", "src/a/**")

        self.assertEqual(refused.returncode, 1)
        self.assertEqual(refused.stderr, journal.REGISTRY_UNAVAILABLE + "\n")

    def test_empty_run_id_key_is_not_rescued_by_legacy_id(self) -> None:
        """A journal that HAS a run_id key (even empty) is a D13 journal: the legacy
        `id` fallback must not rescue it, and the empty identity must refuse."""
        run_dir = self.repo / ".codex-orchestrator/runs/run-empty-runid"
        run_dir.mkdir(parents=True)
        records = [
            {"type": "run_started", "run_id": "", "id": "run-empty-runid"},
            {"type": "run_closed", "run_id": "", "judgment": "passed"},
        ]
        (run_dir / "journal.jsonl").write_text(
            "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
        )

        refused = self.open("run-a", "src/a/**")

        self.assertEqual(refused.returncode, 1)
        self.assertEqual(refused.stderr, journal.REGISTRY_UNAVAILABLE + "\n")

    def plant_pre_coordination_run(self, run_id: str) -> Path:
        # A run opened before D13 coordination existed: run_id-keyed start
        # record with no scope key, no owner sidecar, no run_closed, and no
        # registry entry (the registry itself postdates the run).
        run_dir = self.repo / ".codex-orchestrator/runs" / run_id
        run_dir.mkdir(parents=True)
        records = [
            {"type": "run_started", "run_id": run_id, "goal": "legacy open"},
            {"type": "task", "id": "task-01", "status": "done"},
        ]
        (run_dir / "journal.jsonl").write_text(
            "".join(json.dumps(record) + "\n" for record in records)
        )
        return run_dir

    def test_pre_coordination_open_run_blocks_admission_by_overlap_not_poison(self) -> None:
        # FR-014: unknown open-run scope is repository-wide. That must surface
        # as an overlap refusal naming the run — not as registry poisoning
        # that hides which run is in the way.
        self.plant_pre_coordination_run("authoring-system")
        result = self.open("run-a", "src/a/**")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(
            result.stderr,
            "forge: new run refused — scope overlap between run-a and open run authoring-system\n",
        )

    def test_pre_coordination_open_run_is_adoptable_then_closable(self) -> None:
        # The fix palimpsest-bjb needs end-to-end: append a record to the
        # legacy open run (adopting ownership), close it, then admit new work.
        run_dir = self.plant_pre_coordination_run("authoring-system")
        append_record = self.record(
            "declaration",
            {
                "type": "decision",
                "id": "journal-dialect-compat",
                "resolution": "legacy-dialect-compat: pre-D13 journal",
            },
        )
        appended = self.command(
            "journal-append",
            "--repo",
            str(self.repo),
            "--run-id",
            "authoring-system",
            "--record-json",
            append_record,
        )
        self.assertEqual(appended.returncode, 0, appended.stderr)
        owner = (run_dir / "owner").read_text()
        self.assertIn(f"pid: {os.getpid()}\n", owner)
        # The repository-wide sentinel scope is in-memory admission state
        # only: no registry bytes exist until a real scope is admitted.
        self.assertFalse((self.repo / ".forge/tmp/run-registry.json").exists())
        closed = self.command(
            "run-close",
            "--repo",
            str(self.repo),
            "--run-id",
            "authoring-system",
            "--record-json",
            self.record(
                "closure",
                {"type": "run_closed", "run_id": "authoring-system", "judgment": "passed"},
            ),
        )
        self.assertEqual(closed.returncode, 0, closed.stderr)
        self.assertNotIn(b'"**"', self.registry_bytes())
        admitted = self.open("run-a", "src/a/**")
        self.assertEqual(admitted.returncode, 0, admitted.stderr)

    def test_scopeless_open_run_with_owner_keeps_ownership_rules(self) -> None:
        # Adoption itself writes an owner sidecar next to a scope-less
        # run_started, so that pairing is legitimate history, not corruption.
        # The sidecar changes nothing about admission (still repository-wide,
        # blocking by overlap), and the normal ownership rules keep governing
        # appends: an owner this session cannot verify is foreign.
        run_dir = self.plant_pre_coordination_run("authoring-system")
        (run_dir / "owner").write_text(
            f"pid: 1\nhost: {socket.gethostname()}\nstarted_at: 2026-08-09T10:00:00Z\n"
        )

        result = self.open("run-a", "src/a/**")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(
            result.stderr,
            "forge: new run refused — scope overlap between run-a and open run authoring-system\n",
        )

        declaration = self.record(
            "declaration",
            {
                "type": "decision",
                "id": "journal-dialect-compat",
                "resolution": "legacy-dialect-compat: pre-D13 journal",
            },
        )
        appended = self.command(
            "journal-append",
            "--repo",
            str(self.repo),
            "--run-id",
            "authoring-system",
            "--record-json",
            str(declaration),
        )
        self.assertEqual(appended.returncode, 1, appended.stderr)
        self.assertIn("has live owner 1@", appended.stderr)

    def test_closing_one_pre_coordination_run_never_persists_the_sentinel(self) -> None:
        # Pre-D13 had no mutual exclusion, so two open pre-coordination runs
        # are legitimate history. Closing one writes the registry while the
        # survivor's sentinel scope is still in the admission map; the write
        # filter is the only thing keeping "**" out of the persisted bytes,
        # and a poisoned registry would refuse every later command.
        self.plant_pre_coordination_run("authoring-system")
        self.plant_pre_coordination_run("scenario-support")
        declaration = self.record(
            "declaration",
            {
                "type": "decision",
                "id": "journal-dialect-compat",
                "resolution": "legacy-dialect-compat: pre-D13 journal",
            },
        )
        appended = self.command(
            "journal-append",
            "--repo",
            str(self.repo),
            "--run-id",
            "authoring-system",
            "--record-json",
            str(declaration),
        )
        self.assertEqual(appended.returncode, 0, appended.stderr)
        closed = self.command(
            "run-close",
            "--repo",
            str(self.repo),
            "--run-id",
            "authoring-system",
            "--record-json",
            str(
                self.record(
                    "closure",
                    {
                        "type": "run_closed",
                        "run_id": "authoring-system",
                        "judgment": "passed",
                    },
                )
            ),
        )
        self.assertEqual(closed.returncode, 0, closed.stderr)
        self.assertNotIn(b'"**"', self.registry_bytes())
        # The registry stays loadable and the survivor still guards admission.
        refused = self.open("run-a", "src/a/**")
        self.assertEqual(refused.returncode, 1, refused.stderr)
        self.assertEqual(
            refused.stderr,
            "forge: new run refused — scope overlap between run-a and open run scenario-support\n",
        )

    def test_d13_open_run_missing_from_registry_refuses_all_admission(self) -> None:
        # The registry is the admission authority for D13 runs: an open D13
        # journal it cannot vouch for fails every command closed, and the
        # pre-coordination tolerance must never admit it from journal scope.
        opened = self.open("run-a", "src/a/**")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        rogue = self.repo / ".codex-orchestrator/runs/run-rogue"
        rogue.mkdir(parents=True)
        (rogue / "journal.jsonl").write_text(
            json.dumps(
                {"type": "run_started", "run_id": "run-rogue", "scope": ["src/b/**"]}
            )
            + "\n",
            encoding="utf-8",
        )
        (rogue / "owner").write_text(
            f"pid: {os.getpid()}\nhost: {socket.gethostname()}\n"
            "started_at: 2026-08-16T10:00:00Z\n"
        )

        refused = self.open("run-c", "src/c/**")

        self.assertEqual(refused.returncode, 1, refused.stderr)
        self.assertEqual(refused.stderr, journal.REGISTRY_UNAVAILABLE + "\n")

    def test_pre_coordination_run_cannot_be_retired_into_a_poison_state(self) -> None:
        # A retired scope-less run is unrepresentable (not closed, no scope),
        # so retiring one would poison every future scan with no tooling
        # recovery. The state machine is adopt -> close; retire must refuse
        # with a diagnostic naming that path, and the refusal must leave the
        # coordination layer fully operable.
        self.plant_pre_coordination_run("authoring-system")

        retired = self.command(
            "run-retire", "--repo", str(self.repo), "--run-id", "authoring-system"
        )
        self.assertEqual(retired.returncode, 1, retired.stderr)
        self.assertEqual(
            retired.stderr,
            "forge: run retire refused — pre-coordination run authoring-system"
            " has no admitted scope to reuse; adopt and close it instead\n",
        )

        # Disable-detection: were the refusal removed, retirement would succeed
        # and this append would fail REGISTRY_UNAVAILABLE on the poisoned scan.
        appended = self.command(
            "journal-append",
            "--repo",
            str(self.repo),
            "--run-id",
            "authoring-system",
            "--record-json",
            str(
                self.record(
                    "declaration",
                    {
                        "type": "decision",
                        "id": "journal-dialect-compat",
                        "resolution": "legacy-dialect-compat: pre-D13 journal",
                    },
                )
            ),
        )
        self.assertEqual(appended.returncode, 0, appended.stderr)

    def test_present_but_invalid_scope_key_is_not_pre_coordination(self) -> None:
        # The classification requires the scope KEY to be absent: a D13
        # journal whose scope is present but invalid is corruption and keeps
        # the hard refusal — it must not be downgraded to adoptability.
        run_dir = self.repo / ".codex-orchestrator/runs/run-null-scope"
        run_dir.mkdir(parents=True)
        (run_dir / "journal.jsonl").write_text(
            json.dumps(
                {"type": "run_started", "run_id": "run-null-scope", "scope": None}
            )
            + "\n",
            encoding="utf-8",
        )

        refused = self.open("run-a", "src/a/**")

        self.assertEqual(refused.returncode, 1, refused.stderr)
        self.assertEqual(refused.stderr, journal.REGISTRY_UNAVAILABLE + "\n")

    def test_open_legacy_journal_still_fails_closed(self) -> None:
        """FR-014: an open journal with no scope is repository-wide — every new
        admission is refused by overlap naming the run, never fail-open."""
        self.plant_legacy_journal("run-legacy-open", closed=False)

        refused = self.open("run-a", "src/a/**")

        self.assertEqual(refused.returncode, 1)
        self.assertEqual(
            refused.stderr,
            "forge: new run refused — scope overlap between run-a and open run run-legacy-open\n",
        )
        self.assertFalse(self.journal_path("run-a").exists())

    def test_glob_pairs_fail_conservatively_and_dot_run_is_refused(self) -> None:
        """FR-014/FR-192 and DM-011: fail closed for ambiguous globs and run state."""
        self.assertTrue(journal.pathspecs_overlap("[ab]x", "a[xy]"))
        self.assertTrue(journal.pathspecs_overlap("src/[ab].py", "src/a[xy].py"))
        self.assertTrue(journal.pathspecs_overlap("x[ab]", "x[bc]"))

        refused = self.open(".hidden", "src/a/**")
        self.assertEqual(refused.returncode, 1)
        self.assertEqual(refused.stderr, "forge: new run refused — invalid run id\n")

    def test_stray_regular_file_in_runs_root_is_not_run_state(self) -> None:
        """A non-dot regular file in runs/ cannot be a run and must not poison admission.

        Session tooling (the claude-mem hook) drops a CLAUDE.md stub into every
        directory it touches, including .codex-orchestrator/runs/. A regular
        file holds no journal and no scope, and atomic-open crash temps are
        dot-prefixed (covered by the fail-closed test below), so refusing the
        whole registry over a stub breaks every run-open intermittently.
        """
        runs_root = self.repo / ".codex-orchestrator/runs"
        runs_root.mkdir(parents=True)
        stub = runs_root / "CLAUDE.md"
        stub.write_text("<claude-mem-context>\n\n</claude-mem-context>\n", encoding="utf-8")

        opened = self.open("run-a", "src/a/**")

        self.assertEqual(opened.returncode, 0, opened.stderr)
        self.assertIn(b'"run_id":"run-a"', self.registry_bytes())
        self.assertTrue(stub.is_file(), "stub must be left untouched")

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
            '                if not _safe_run_entry_name(name) or name.startswith("."):\n'
            "                    raise CoordinationRefusal(REGISTRY_UNAVAILABLE)\n",
            '                if not _safe_run_entry_name(name):\n'
            "                    raise CoordinationRefusal(REGISTRY_UNAVAILABLE)\n"
            '                if name.startswith("."):\n'
            "                    continue  # control disabled by mutant\n",
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
            original_owner = owner.read_bytes()
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
            owner.write_bytes(original_owner)

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
        self.assertEqual(
            crashed.stderr, "forge: run coordination refused — internal error\n"
        )
        self.assertNotIn("OverflowError", crashed.stderr)

    def test_out_of_root_citation_fields_refuse_without_coordination_writes(self) -> None:
        """FR-017: every audit citation surface refuses with its exact field label."""
        run_id = "run-citations"
        self.assertEqual(self.open(run_id, "src/**").returncode, 0)
        run_dir = self.journal_path(run_id).parent
        (run_dir / "inside.txt").write_text("inside\n", encoding="utf-8")
        outside = self.outside_citation(run_id, "all-fields.txt")
        owner = run_dir / "owner"
        owner.write_text(
            f"pid: 2147483647\nhost: {socket.gethostname()}\n"
            "started_at: 2026-08-13T00:00:00Z\n",
            encoding="utf-8",
        )
        before = self.coordination_bytes(run_id)
        cases: tuple[tuple[str, dict[str, object]], ...] = (
            ("execution.prompt", {"type": "execution", "prompt": outside}),
            ("execution.events", {"type": "execution", "events": outside}),
            ("execution.handoff", {"type": "execution", "handoff": outside}),
            (
                "execution_result.handoff",
                {"type": "execution_result", "handoff": outside},
            ),
            (
                "verification.evidence[1]",
                {
                    "type": "verification",
                    "evidence": ["inside.txt", outside],
                },
            ),
            (
                "decision.basis[1]",
                {
                    "type": "decision",
                    "basis": ["decision-previous", f"reviewed `{outside}`"],
                },
            ),
            (
                f"verification.observation token {outside}",
                {
                    "type": "verification",
                    "observation": f"reviewed `{outside}`",
                },
            ),
        )

        for index, (field, record) in enumerate(cases):
            with self.subTest(field=field):
                refused = self.command(
                    "journal-append",
                    "--repo",
                    str(self.repo),
                    "--run-id",
                    run_id,
                    "--record-json",
                    str(self.record(f"outside-{index}.json", record)),
                )
                self.assertEqual(refused.returncode, 1)
                self.assertEqual(
                    refused.stderr,
                    "forge: journal append refused — record cites path outside run or "
                    f"repository: {field}: {outside}\n",
                )
                self.assertEqual(self.coordination_bytes(run_id), before)

    def test_citation_roots_accept_relative_paths_and_refuse_escapes(self) -> None:
        """FR-017: use the audit's ordered, root-specific containment predicate."""
        run_id = "run-roots"
        self.assertEqual(self.open(run_id, "src/**").returncode, 0)
        run_dir = self.journal_path(run_id).parent
        run_file = run_dir / "run-proof.txt"
        run_file.write_text("run\n", encoding="utf-8")
        repo_file = self.repo / "repo-proof.jsonl"
        repo_file.write_text("repo\n", encoding="utf-8")
        accepted = self.command(
            "journal-append",
            "--repo",
            str(self.repo),
            "--run-id",
            run_id,
            "--record-json",
            str(
                self.record(
                    "relative-roots.json",
                    {
                        "type": "execution",
                        "prompt": run_file.name,
                        "events": repo_file.name,
                    },
                )
            ),
        )
        self.assertEqual(accepted.returncode, 0, accepted.stderr)

        sibling = run_dir.parent / "outside-run.txt"
        sibling.write_text("sibling\n", encoding="utf-8")
        repo_target = self.repo / "shared-citations"
        repo_target.mkdir()
        (repo_target / "proof.txt").write_text("repo target\n", encoding="utf-8")
        (run_dir / "repo-link").symlink_to(repo_target, target_is_directory=True)
        external_target = Path(self.temporary.name) / "external-citations"
        external_target.mkdir()
        (external_target / "proof.txt").write_text("external target\n", encoding="utf-8")
        (run_dir / "external-link").symlink_to(external_target, target_is_directory=True)
        cases = (
            (str(run_file.resolve()), "execution.prompt"),
            ("../outside-run.txt", "execution.prompt"),
            ("repo-link/proof.txt", "execution.prompt"),
            ("external-link/proof.txt", "execution.prompt"),
        )
        for index, (citation, field) in enumerate(cases):
            with self.subTest(citation=citation):
                before = self.coordination_bytes(run_id)
                refused = self.command(
                    "journal-append",
                    "--repo",
                    str(self.repo),
                    "--run-id",
                    run_id,
                    "--record-json",
                    str(
                        self.record(
                            f"root-escape-{index}.json",
                            {"type": "execution", "prompt": citation},
                        )
                    ),
                )
                self.assertEqual(refused.returncode, 1)
                self.assertEqual(
                    refused.stderr,
                    "forge: journal append refused — record cites path outside run or "
                    f"repository: {field}: {citation}\n",
                )
                self.assertEqual(self.coordination_bytes(run_id), before)

    def test_anchored_symlink_escape_cannot_fall_through_to_repository(self) -> None:
        """FR-017: the shared ordered root selection anchors at the run spelling."""

        run_id = "run-anchored-citation"
        self.assertEqual(self.open(run_id, "src/**").returncode, 0)
        run_dir = self.journal_path(run_id).parent
        outside = Path(self.temporary.name) / "anchored-outside"
        outside.mkdir()
        (outside / "proof.txt").write_text("outside\n", encoding="utf-8")
        (run_dir / "anchored").symlink_to(outside, target_is_directory=True)
        safe = self.repo / "anchored"
        safe.mkdir()
        (safe / "proof.txt").write_text("repository\n", encoding="utf-8")
        citation = "anchored/proof.txt"
        self.assertFalse(
            journal._citation_is_contained(self.repo, run_dir, citation)
        )
        before = self.coordination_bytes(run_id)

        refused = self.command(
            "journal-append",
            "--repo",
            str(self.repo),
            "--run-id",
            run_id,
            "--record-json",
            str(
                self.record(
                    "anchored-citation.json",
                    {
                        "type": "decision",
                        "id": "decision-anchored",
                        "basis": [citation],
                    },
                )
            ),
        )

        self.assertEqual(refused.returncode, 1)
        self.assertEqual(
            refused.stderr,
            "forge: journal append refused — record cites path outside run or "
            f"repository: decision.basis[0]: {citation}\n",
        )
        self.assertEqual(self.coordination_bytes(run_id), before)

    def test_non_path_basis_and_observation_are_accepted(self) -> None:
        """FR-017: record IDs and prose are not promoted to path citations."""
        run_id = "run-prose"
        self.assertEqual(self.open(run_id, "src/**").returncode, 0)
        records: tuple[dict[str, object], ...] = (
            {
                "type": "decision",
                "id": "decision-prose",
                "basis": ["decision-previous", "independent reviewer consensus"],
            },
            {
                "type": "verification",
                "id": "verification-prose",
                "observation": "PASS; decision-previous corroborates task-02",
            },
        )
        before = self.journal_path(run_id).read_bytes()
        for index, record in enumerate(records):
            appended = self.command(
                "journal-append",
                "--repo",
                str(self.repo),
                "--run-id",
                run_id,
                "--record-json",
                str(self.record(f"prose-{index}.json", record)),
            )
            self.assertEqual(appended.returncode, 0, appended.stderr)
        self.assertTrue(self.journal_path(run_id).read_bytes().startswith(before))
        self.assertEqual(len(self.journal_path(run_id).read_text().splitlines()), 3)

    def test_lifecycle_citation_refusals_precede_every_coordination_write(self) -> None:
        """FR-017: run-open and run-close reject citations before lifecycle checks."""
        self.assertEqual(self.open("run-existing", "src/existing/**").returncode, 0)
        existing_before = self.coordination_bytes("run-existing")
        outside_open = self.outside_citation("run-new", "open.txt")
        opening = self.record(
            "bad-opening.json", {"type": "execution", "prompt": outside_open}
        )
        refused_open = self.command(
            "run-open",
            "--repo",
            str(self.repo),
            "--run-id",
            "run-new",
            "--scope",
            "src/new/**",
            "--record-json",
            str(opening),
        )
        self.assertEqual(refused_open.returncode, 1)
        self.assertEqual(
            refused_open.stderr,
            "forge: journal append refused — record cites path outside run or "
            f"repository: execution.prompt: {outside_open}\n",
        )
        self.assertFalse(self.journal_path("run-new").parent.exists())
        self.assertEqual(self.coordination_bytes("run-existing"), existing_before)

        run_id = "run-closing"
        self.assertEqual(self.open(run_id, "src/closing/**").returncode, 0)
        run_dir = self.journal_path(run_id).parent
        (run_dir / "owner").write_text(
            f"pid: 2147483647\nhost: {socket.gethostname()}\n"
            "started_at: 2026-08-13T00:00:00Z\n",
            encoding="utf-8",
        )
        close_before = self.coordination_bytes(run_id)
        outside_close = self.outside_citation(run_id, "close.txt")
        closing = self.record(
            "bad-closing.json",
            {"type": "execution_result", "handoff": outside_close},
        )
        refused_close = self.command(
            "run-close",
            "--repo",
            str(self.repo),
            "--run-id",
            run_id,
            "--record-json",
            str(closing),
        )
        self.assertEqual(refused_close.returncode, 1)
        self.assertEqual(
            refused_close.stderr,
            "forge: journal append refused — record cites path outside run or "
            f"repository: execution_result.handoff: {outside_close}\n",
        )
        self.assertEqual(self.coordination_bytes(run_id), close_before)

    def test_citation_root_enforcement_frozenset_is_load_bearing(self) -> None:
        """FR-017: disabling the append-time leg in memory permits the bad append."""
        run_id = "run-citation-mutant"
        self.assertEqual(self.open(run_id, "src/**").returncode, 0)
        run_dir = self.journal_path(run_id).parent
        outside = self.outside_citation(run_id, "mutant.txt")
        record = self.strict_record(
            {
                "type": "decision",
                "id": "decision-mutant",
                "basis": [f"reviewed `{outside}`"],
            }
        )
        with self.assertRaisesRegex(
            journal.CoordinationRefusal, "record cites path outside run or repository"
        ):
            journal._validate_append_citations(self.repo, run_dir, record)

        before = self.journal_path(run_id).read_bytes()
        enabled = journal.CITATION_ROOT_ENFORCEMENT_LEGS
        with mock.patch.dict(os.environ, {"FORGE_SESSION_PID": str(os.getpid())}):
            with mock.patch.object(
                journal,
                "CITATION_ROOT_ENFORCEMENT_LEGS",
                enabled - {"append-time"},
            ):
                journal.append_run_record(self.repo, run_id, record)
        self.assertNotEqual(self.journal_path(run_id).read_bytes(), before)

    def test_append_owned_record_enforces_citation_roots_before_owner_takeover(self) -> None:
        """FR-017: the mutation-runner append path cannot bypass the root guard."""
        run_id = "run-owned-append"
        self.assertEqual(self.open(run_id, "src/**").returncode, 0)
        run_dir = self.journal_path(run_id).parent
        owner = run_dir / "owner"
        owner.write_text(
            f"pid: 2147483647\nhost: {socket.gethostname()}\n"
            "started_at: 2026-08-13T00:00:00Z\n",
            encoding="utf-8",
        )
        outside = self.outside_citation(run_id, "owned-append.txt")
        record = {
            "type": "verification",
            "id": "verification-owned-append",
            "evidence": [outside],
        }
        before = self.coordination_bytes(run_id)

        with mock.patch.dict(os.environ, {"FORGE_SESSION_PID": str(os.getpid())}):
            with self.assertRaisesRegex(
                journal.CoordinationRefusal,
                re.escape(
                    "forge: journal append refused — record cites path outside run or "
                    f"repository: verification.evidence[0]: {outside}"
                ),
            ):
                journal.append_owned_record(self.journal_path(run_id), record)

        self.assertEqual(self.coordination_bytes(run_id), before)

    def test_append_owned_record_uses_the_recorded_linked_worktree_root(self) -> None:
        """FR-017: common-root lookup cannot hide a linked-worktree symlink escape."""
        subprocess.run(
            [
                "git",
                "-C",
                str(self.repo),
                "-c",
                "user.name=Forge Tests",
                "-c",
                "user.email=forge-tests@example.invalid",
                "commit",
                "--allow-empty",
                "--quiet",
                "-m",
                "base",
            ],
            check=True,
        )
        linked = Path(self.temporary.name) / "linked-worktree"
        subprocess.run(
            ["git", "-C", str(self.repo), "worktree", "add", "--detach", str(linked)],
            check=True,
            capture_output=True,
        )
        run_id = "run-linked-owned-append"
        opening = self.record(
            "linked-opening.json",
            {"type": "run_started", "run_id": run_id, "repo": str(linked)},
        )
        opened = self.command(
            "run-open",
            "--repo",
            str(linked),
            "--run-id",
            run_id,
            "--scope",
            "src/**",
            "--record-json",
            str(opening),
        )
        self.assertEqual(opened.returncode, 0, opened.stderr)

        external = Path(self.temporary.name) / "linked-external"
        external.mkdir()
        (external / "proof.txt").write_text("outside\n", encoding="utf-8")
        (linked / "escape").symlink_to(external, target_is_directory=True)
        citation = "escape/proof.txt"
        record = {
            "type": "verification",
            "id": "verification-linked-owned-append",
            "evidence": [citation],
        }
        before = self.coordination_bytes(run_id)

        with mock.patch.dict(os.environ, {"FORGE_SESSION_PID": str(os.getpid())}):
            with self.assertRaisesRegex(
                journal.CoordinationRefusal,
                re.escape(
                    "forge: journal append refused — record cites path outside run or "
                    f"repository: verification.evidence[0]: {citation}"
                ),
            ):
                journal.append_owned_record(self.journal_path(run_id), record)

        self.assertEqual(self.coordination_bytes(run_id), before)

    def test_public_append_cannot_substitute_a_linked_worktree_root(self) -> None:
        """FR-017: a caller worktree cannot replace the run's recorded worktree."""
        subprocess.run(
            [
                "git",
                "-C",
                str(self.repo),
                "-c",
                "user.name=Forge Tests",
                "-c",
                "user.email=forge-tests@example.invalid",
                "commit",
                "--allow-empty",
                "--quiet",
                "-m",
                "base",
            ],
            check=True,
        )
        worktree_a = Path(self.temporary.name) / "linked-a"
        worktree_b = Path(self.temporary.name) / "linked-b"
        for worktree in (worktree_a, worktree_b):
            subprocess.run(
                ["git", "-C", str(self.repo), "worktree", "add", "--detach", str(worktree)],
                check=True,
                capture_output=True,
            )
        run_id = "run-linked-public-append"
        opening = self.record(
            "public-linked-opening.json",
            {"type": "run_started", "run_id": run_id, "repo": str(worktree_a)},
        )
        opened = self.command(
            "run-open",
            "--repo",
            str(worktree_a),
            "--run-id",
            run_id,
            "--scope",
            "src/**",
            "--record-json",
            str(opening),
        )
        self.assertEqual(opened.returncode, 0, opened.stderr)

        external = Path(self.temporary.name) / "public-linked-external"
        external.mkdir()
        (external / "proof.txt").write_text("outside\n", encoding="utf-8")
        (worktree_a / "escape").symlink_to(external, target_is_directory=True)
        (worktree_b / "escape").mkdir()
        (worktree_b / "escape/proof.txt").write_text("inside B\n", encoding="utf-8")
        run_dir = self.journal_path(run_id).parent
        (run_dir / "owner").write_text(
            f"pid: 2147483647\nhost: {socket.gethostname()}\n"
            "started_at: 2026-08-13T00:00:00Z\n",
            encoding="utf-8",
        )
        citation = "escape/proof.txt"
        record = self.record(
            "public-linked-append.json",
            {
                "type": "verification",
                "id": "verification-linked-public-append",
                "evidence": [citation],
            },
        )
        before = self.coordination_bytes(run_id)

        refused = self.command(
            "journal-append",
            "--repo",
            str(worktree_b),
            "--run-id",
            run_id,
            "--record-json",
            str(record),
        )

        self.assertEqual(refused.returncode, 1)
        self.assertEqual(
            refused.stderr,
            "forge: journal append refused — record cites path outside run or "
            f"repository: verification.evidence[0]: {citation}\n",
        )
        self.assertEqual(self.coordination_bytes(run_id), before)

    def test_modern_run_without_recorded_repo_has_no_common_root_fallback(self) -> None:
        """FR-017: a scoped run missing repo may not inherit common-root citations."""
        run_id = "run-modern-missing-repo"
        self.assertEqual(self.open(run_id, "src/**").returncode, 0)
        journal_path = self.journal_path(run_id)
        opening = json.loads(journal_path.read_text(encoding="utf-8"))
        self.assertIn("scope", opening)
        opening.pop("repo", None)
        journal_path.write_text(json.dumps(opening) + "\n", encoding="utf-8")

        run_dir = journal_path.parent
        external = Path(self.temporary.name) / "missing-repo-external"
        external.mkdir()
        (external / "proof.txt").write_text("outside\n", encoding="utf-8")
        (run_dir / "escape").symlink_to(external, target_is_directory=True)
        (self.repo / "escape").mkdir()
        (self.repo / "escape/proof.txt").write_text("common root\n", encoding="utf-8")
        (run_dir / "owner").write_text(
            f"pid: 2147483647\nhost: {socket.gethostname()}\n"
            "started_at: 2026-08-13T00:00:00Z\n",
            encoding="utf-8",
        )
        citation = "escape/proof.txt"
        record = {
            "type": "verification",
            "id": "verification-modern-missing-repo",
            "evidence": [citation],
        }
        before = self.coordination_bytes(run_id)

        with mock.patch.dict(os.environ, {"FORGE_SESSION_PID": str(os.getpid())}):
            with self.assertRaisesRegex(
                journal.CoordinationRefusal,
                re.escape(
                    "forge: journal append refused — recorded repository unavailable "
                    "for run run-modern-missing-repo"
                ),
            ):
                journal.append_owned_record(journal_path, record)

        self.assertEqual(self.coordination_bytes(run_id), before)

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
        self.assertIn('"src/a/**"', refused.stderr)
        self.assertEqual(self.journal_path("run-A").read_bytes(), before)
        self.assertIn(b'"scope":["src/a/**"]', self.registry_bytes())

        replaced_but_unsafe = self.command(
            "run-readmit", "--repo", str(self.repo), "--run-id", "run-A",
            "--scope", "src/a/other.py", "--replace",
        )
        self.assertEqual(replaced_but_unsafe.returncode, 1)
        self.assertIn('"src/a/x.py"', replaced_but_unsafe.stderr)
        self.assertEqual(self.journal_path("run-A").read_bytes(), before)

        replaced = self.command(
            "run-readmit", "--repo", str(self.repo), "--run-id", "run-A",
            "--scope", "src/a/x.py", "--replace",
        )
        self.assertEqual(replaced.returncode, 0, replaced.stderr)
        self.assertIn(b'"scope":["src/a/x.py"]', self.registry_bytes())

    def test_readmission_requires_complete_current_set_without_replace(self) -> None:
        self.assertEqual(
            self.open("run-A", "docs/**", "src/**").returncode, 0
        )
        before = self.journal_path("run-A").read_bytes()

        refused = self.command(
            "run-readmit", "--repo", str(self.repo), "--run-id", "run-A",
            "--scope", "src/**",
        )

        self.assertEqual(refused.returncode, 1)
        self.assertIn('"docs/**"', refused.stderr)
        self.assertEqual(self.journal_path("run-A").read_bytes(), before)

    def test_activated_readmission_requires_typed_builder_record(self) -> None:
        self.assertEqual(self.open("run-legacy", "legacy/**").returncode, 0)
        self.assertEqual(self.open("run-activated", "src/**").returncode, 0)
        self.activate_writer_contract("run-activated")

        with mock.patch.dict(os.environ, {"FORGE_SESSION_PID": str(os.getpid())}):
            for label, run_id, transaction_scope, authority in (
                ("activated-direct-raw", "run-activated", ["src/**"], None),
                (
                    "activated-authority-without-record",
                    "run-activated",
                    ["src/**"],
                    journal._SCOPE_CHANGE_BUILDER_AUTHORITY,
                ),
                (
                    "legacy-authority-without-record",
                    "run-legacy",
                    ["legacy/**"],
                    journal._SCOPE_CHANGE_BUILDER_AUTHORITY,
                ),
            ):
                with self.subTest(label=label):
                    before = self.coordination_bytes(run_id)
                    with self.assertRaises(journal.CoordinationRefusal) as caught:
                        journal.readmit_run(
                            self.repo,
                            run_id,
                            transaction_scope,
                            _builder_authority=authority,
                            _record=None,
                        )
                    self.assertEqual(
                        str(caught.exception),
                        "forge: journal append refused — activated writer requires "
                        "typed builder",
                    )
                    self.assertEqual(self.coordination_bytes(run_id), before)

    def test_readmission_authority_binds_run_and_scope_across_contracts(self) -> None:
        self.assertEqual(self.open("run-legacy", "legacy/**").returncode, 0)
        self.assertEqual(self.open("run-activated", "src/**").returncode, 0)
        self.activate_writer_contract("run-activated")
        contract_cases = (
            (
                "legacy",
                "run-legacy",
                ["legacy/**", "tests/**"],
                ["docs/**", "legacy/**"],
            ),
            (
                "activated",
                "run-activated",
                ["src/**", "tests/**"],
                ["docs/**", "src/**"],
            ),
        )

        with mock.patch.dict(os.environ, {"FORGE_SESSION_PID": str(os.getpid())}):
            for contract, run_id, transaction_scope, mismatched_scope in contract_cases:
                record_cases = (
                    (
                        "run_id",
                        self.strict_record(
                            {
                                "type": "decision",
                                "id": f"forge-scope-readmission-{'a' * 32}",
                                "resolution": journal.READMISSION_RESOLUTION,
                                "run_id": "run-other",
                                "scope": transaction_scope,
                            }
                        ),
                    ),
                    (
                        "scope",
                        self.strict_record(
                            {
                                "type": "decision",
                                "id": f"forge-scope-readmission-{'b' * 32}",
                                "resolution": journal.READMISSION_RESOLUTION,
                                "run_id": run_id,
                                "scope": mismatched_scope,
                            }
                        ),
                    ),
                )
                for field, record in record_cases:
                    with self.subTest(contract=contract, field=field):
                        before = self.coordination_bytes(run_id)
                        with self.assertRaises(journal.CoordinationRefusal) as caught:
                            journal.readmit_run(
                                self.repo,
                                run_id,
                                transaction_scope,
                                _builder_authority=(
                                    journal._SCOPE_CHANGE_BUILDER_AUTHORITY
                                ),
                                _record=record,
                            )
                        self.assertEqual(
                            str(caught.exception), journal.INVALID_JOURNAL_RECORD
                        )
                        self.assertEqual(self.coordination_bytes(run_id), before)

    def test_legacy_task_append_scope_refusal_names_offending_pathspec(self) -> None:
        self.assertEqual(self.open("run-A", "src/**").returncode, 0)
        task = self.record(
            "outside-task.json",
            {
                "type": "task",
                "id": "task-1",
                "status": "active",
                "files": ["docs/guide.md"],
            },
        )

        refused = self.command(
            "journal-append", "--repo", str(self.repo), "--run-id", "run-A",
            "--record-json", str(task),
        )

        self.assertEqual(refused.returncode, 1)
        self.assertIn('"docs/guide.md"', refused.stderr)

    def test_named_scope_refusal_escapes_control_characters_on_one_line(self) -> None:
        self.assertEqual(self.open("run-A", "src/**").returncode, 0)
        task = self.record(
            "escaped-outside-task.json",
            {
                "type": "task",
                "id": "task-1",
                "status": "active",
                "files": ["docs/line\nbreak.md"],
            },
        )

        refused = self.command(
            "journal-append", "--repo", str(self.repo), "--run-id", "run-A",
            "--record-json", str(task),
        )

        self.assertEqual(refused.returncode, 1)
        self.assertEqual(refused.stderr.count("\n"), 1)
        self.assertIn('"docs/line\\nbreak.md"', refused.stderr)

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
            with self.assertRaisesRegex(
                journal.CoordinationRefusal,
                re.escape("forge: journal append refused — run run-A is retired"),
            ):
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
                self.strict_record({"type": "run_started", "run_id": "run-A"}),
            )
            before = self.journal_path("run-A").read_bytes()
            registry_before = self.registry_bytes()

            def fail_registry_publication(
                state_root: Path,
                locked: journal.RegistryLock,
                prior: journal.RegistrySnapshot,
                payload: bytes,
            ) -> journal.RegistryPublication:
                raise OSError("mutant disabled registry publication")

            with mock.patch.object(
                journal,
                "_begin_registry_publication",
                side_effect=fail_registry_publication,
            ) as begin_publication:
                with self.assertRaises(journal.CoordinationRefusal) as caught:
                    journal.readmit_run(self.repo, "run-A", ["src/a/**", "src/shared/**"])

            self.assertEqual(str(caught.exception), journal.REGISTRY_UPDATE_FAILED)
            begin_publication.assert_called_once()
            self.assertEqual(self.journal_path("run-A").read_bytes(), before)
            self.assertEqual(self.registry_bytes(), registry_before)

    def test_admission_sensor_kills_disabled_overlap_control_copy(self) -> None:
        """FR-014/FR-192 and DM-011: prove overlap sensing kills a disabled control."""
        self.assertEqual(self.open("run-A", "src/shared/**").returncode, 0)
        self.assertEqual(self.open("run-B", "src/shared/file.py").returncode, 1)

        mutant, environment = self.mutant_tools(
            "admission-overlap-mutant",
            "        if other_id in excluded or not scopes_overlap(scope, reservation.scope):\n",
            "        if True:  # overlap control disabled by mutant\n",
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
