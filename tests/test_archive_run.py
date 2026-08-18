"""Behavior tests for the durable intent archive transaction."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from tests.test_e2e_smoke import assemble_codex_prompt
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARCHIVER = ROOT / "scripts" / "forge" / "archive-run.py"
LOCKED_LEARN_WRITER = ROOT / "scripts" / "forge" / "learn-proposals-locked.py"
CONTAMINATION = "forge: archive refused — close tree contains unrelated changes\n"
FRESH_ARCHIVE_REVIEWER = r'''from __future__ import annotations

import json
import os
import sys
from pathlib import Path

if len(sys.argv) != 4:
    raise SystemExit("expected exactly three evidence paths")
if os.environ.get("FORGE_REVIEW_PROFILE") != "review-periodic":
    raise SystemExit("expected review-periodic profile")
if os.environ.get("FORGE_REVIEW_ACCESS") != "read-only":
    raise SystemExit("expected read-only access")
patterns_path, archives_path, gotchas_path = map(Path, sys.argv[1:])
patterns = json.loads(patterns_path.read_text(encoding="utf-8"))
if set(patterns) != {
    "available", "decision_outcomes", "diagnostics", "failure", "findings", "routing", "tasks"
} or patterns["available"] is not True or patterns["failure"] != "":
    raise SystemExit("journal patterns unavailable")
if set(patterns["findings"]) != {"by_reviewer_role", "by_severity"}:
    raise SystemExit("invalid journal patterns")
archives = json.loads(archives_path.read_text(encoding="utf-8"))
gotchas = json.loads(gotchas_path.read_text(encoding="utf-8"))
if len(archives) != 1 or set(archives[0]) != {"content", "head", "path"}:
    raise SystemExit("invalid committed archive input")
archive = archives[0]
if set(gotchas) != {"content", "head", "path", "present"}:
    raise SystemExit("invalid committed gotchas input")
if gotchas["head"] != archive["head"] or gotchas["path"] != ".forge/history/gotchas.md":
    raise SystemExit("committed input identity mismatch")
if gotchas["present"] is not True or not isinstance(gotchas["content"], str) or not gotchas["content"]:
    raise SystemExit("invalid committed gotchas availability")
begin = "<!-- BEGIN FORGE LEARNING PROVENANCE v1 -->\n```json\n"
end = "\n```\n<!-- END FORGE LEARNING PROVENANCE v1 -->"
if archive["content"].count(begin) != 1 or archive["content"].count(end) != 1:
    raise SystemExit("archive provenance unavailable")
encoded = archive["content"].split(begin, 1)[1].split(end, 1)[0]
provenance = json.loads(encoded)
execution = provenance["executions"][0]
task = execution["task"]
decision = next(item for item in provenance["decisions"] if item["task"] == task)
verification = next(
    item
    for item in provenance["failed_or_inconclusive_verifications"]
    if item["task"] == task and item["result"] in {"failed", "inconclusive"}
)
run_id = Path(archive["path"]).stem
proposal = {
    "candidates": [{
        "agent": execution["agent"],
        "category": "review",
        "execution": execution["execution"],
        "expected": "The review control blocks the archived boundary failure.",
        "expected_verdict": "BLOCK",
        "id": "archive-review-boundary",
        "run_id": run_id,
        "scenario": "Archived boundary failure",
    }],
    "gotchas": [{
        "agent": execution["agent"],
        "entries": [
            {"id": decision["id"], "type": "decision"},
            {"id": verification["id"], "type": "verification"},
        ],
        "execution": execution["execution"],
        "line": "Archived boundary failure needed an earlier review control",
        "run_id": run_id,
    }],
    "input_head": archive["head"],
    "schema_version": 1,
}
sys.stdout.write(json.dumps(proposal, sort_keys=True, separators=(",", ":")) + "\n")
'''


class ArchiveRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="forge-archive-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "--quiet")
        self.git("symbolic-ref", "HEAD", "refs/heads/main")
        self.git("config", "user.name", "Archive Fixture")
        self.git("config", "user.email", "archive@example.invalid")
        (self.repo / ".gitignore").write_text(".forge/tmp/\n", encoding="utf-8")
        (self.repo / "tracked.txt").write_text("initial\n", encoding="utf-8")
        self.git("add", ".gitignore", "tracked.txt")
        self.git("commit", "--quiet", "-m", "fixture")
        self.starting_head = self.git("rev-parse", "HEAD").stdout.strip()

        self.run_id = "archive-fixture-01"
        self.run_dir = self.root / self.run_id
        self.run_dir.mkdir()
        (self.run_dir / "claude-plan.md").write_bytes(
            b"# Claude plan\r\n\r\nPreserve CRLF and trailing spaces.  \r\n"
        )
        (self.run_dir / "codex-contract.txt").write_bytes(
            b"CODEX CONTRACT\nbyte-for-byte body without final newline"
        )
        (self.run_dir / "plan choice.yaml").write_bytes(
            b"decision: preserve-percent-encoded-reference\n"
        )
        (self.run_dir / "Makefile").write_bytes(b"archive:\n\t@true\n")
        self.records = self.valid_records()
        self.write_journal()
        self.post_close = self.root / "post-close.json"
        self.post_payload = {
            "issues": [],
            "non_passing_verifications": [],
            "ok": True,
            "profile": "gates",
            "warnings": [],
        }
        self.post_close.write_text(
            json.dumps(self.post_payload, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        self.archive_relative = Path(".forge/history/runs") / f"{self.run_id}.md"
        self.archive_path = self.repo / self.archive_relative

    def git(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", *arguments],
            cwd=self.repo,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            self.fail(f"git {' '.join(arguments)} failed: {result.stderr}")
        return result

    def valid_records(self) -> list[dict[str, object]]:
        gate_observation = "PASS; 0 CRITICAL/MAJOR findings; iteration 2 of 8."
        pre_close = {
            "issues": [],
            "non_passing_verifications": [],
            "ok": True,
            "profile": "gates",
            "warnings": [],
        }
        return [
            {
                "type": "run_started",
                "run_id": self.run_id,
                "goal": "Ship the durable intent archive.",
                "repo": str(self.repo.resolve()),
                "repo_head": self.starting_head,
            },
            {
                "type": "task",
                "id": "task-07",
                "status": "active",
                "goal": "Archive the closed run.",
                "acceptance": ["Archive is deterministic.", "Archive is committed history."],
            },
            {
                "type": "decision",
                "id": "decision-07",
                "task": "task-07",
                "finding": "Both independent plans agree.",
                "outcome": "accepted",
                "resolution": "Implement task-07 with a fail-closed transaction.",
                "basis": [
                    "claude-plan.md#fr-124",
                    "Independent proposal: `codex-contract.txt`",
                    "[ADR](plan%20choice.yaml \"binding choice\")",
                ],
            },
            {
                "type": "verification",
                "id": "verification-gate-1",
                "task": "task-07",
                "criterion": "gate-1: project tests",
                "check": "python3 -m unittest discover -s tests",
                "result": "passed",
                "observation": gate_observation,
            },
            {
                "type": "verification",
                "id": "verification-gate-2",
                "task": "task-07",
                "criterion": "gate-2: lint and types",
                "check": "python3 -m py_compile scripts/forge/archive-run.py",
                "result": "passed",
                "observation": gate_observation,
            },
            {
                "type": "verification",
                "id": "verification-gate-3",
                "task": "task-07",
                "criterion": "gate-3: review-final verdict",
                "check": f"review-final over git diff {self.starting_head}..{self.starting_head}",
                "result": "passed",
                "observation": gate_observation,
            },
            # Deliberately terse: the renderer must carry the contract from the
            # earlier task entry while taking this as the latest outcome.
            {
                "type": "task",
                "id": "task-07",
                "status": "complete",
                "outcome": "Implemented and independently reviewed.",
            },
            {
                "type": "run_closed",
                "judgment": "passed",
                "validation": pre_close,
                "risks": ["A later schema migration remains out of scope."],
                "follow_ups": ["Implement D12 separately."],
            },
        ]

    def write_journal(self) -> None:
        (self.run_dir / "journal.jsonl").write_text(
            "".join(
                json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
                for record in self.records
            ),
            encoding="utf-8",
        )

    def refresh_validation_payloads(self) -> None:
        # Preserve the independently passing pre-close snapshot while deriving
        # the current post-close result from the now-mutated journal.
        self.records[-1]["validation"] = {
            "issues": [],
            "non_passing_verifications": [],
            "ok": True,
            "profile": "gates",
            "warnings": [],
        }
        self.write_journal()
        result = subprocess.run(
            [
                sys.executable,
                os.fspath(ROOT / "scripts" / "codex_orch_tools.py"),
                "validate",
                os.fspath(self.run_dir),
                "--gates",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)
        self.post_payload = payload
        self.post_close.write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )

    def set_passing_post_close(self) -> None:
        self.post_payload = {
            "issues": [],
            "non_passing_verifications": [],
            "ok": True,
            "profile": "gates",
            "warnings": [],
        }
        self.records[-1]["validation"] = dict(self.post_payload)
        self.write_journal()
        result = subprocess.run(
            [
                sys.executable,
                os.fspath(ROOT / "scripts" / "codex_orch_tools.py"),
                "validate",
                os.fspath(self.run_dir),
                "--gates",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.post_payload = json.loads(result.stdout)
        self.records[-1]["validation"] = {
            "issues": [],
            "non_passing_verifications": [],
            "ok": True,
            "profile": "gates",
            "warnings": [],
        }
        self.write_journal()
        self.post_close.write_text(
            json.dumps(self.post_payload, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )

    def add_learning_evidence(self) -> bytes:
        prompt = b"Review the archived boundary failure exactly.\nDo not guess.\n"
        execution_dir = self.run_dir / "agents" / "review-cheap-archive" / "execution-01"
        execution_dir.mkdir(parents=True)
        (execution_dir / "prompt.md").write_bytes(prompt)
        (execution_dir / "handoff.md").write_text(
            "The boundary failure was reproduced.\n", encoding="utf-8"
        )
        execution = {
            "type": "execution",
            "agent": "review-cheap-archive",
            "execution": "execution-01",
            "task": "task-07",
            "role": "review",
            "prompt": "agents/review-cheap-archive/execution-01/prompt.md",
            "handoff": "agents/review-cheap-archive/execution-01/handoff.md",
        }
        execution_result = {
            "type": "execution_result",
            "agent": "review-cheap-archive",
            "execution": "execution-01",
            "task": "task-07",
            "status": "complete",
            "handoff": "agents/review-cheap-archive/execution-01/handoff.md",
        }
        decision_index = next(
            index
            for index, record in enumerate(self.records)
            if record.get("type") == "decision"
        )
        self.records[decision_index:decision_index] = [execution, execution_result]
        first_gate = next(
            index
            for index, record in enumerate(self.records)
            if record.get("id") == "verification-gate-1"
        )
        self.records.insert(
            first_gate,
            {
                "type": "verification",
                "id": "verification-learning-01",
                "task": "task-07",
                "criterion": "acceptance: archive boundary failure",
                "check": "reproduce archived boundary failure",
                "result": "failed",
                "observation": "The boundary failure escaped the earlier review control.",
            },
        )
        self.write_journal()
        return prompt

    def synchronize_validation_payloads(self) -> None:
        command = [
            sys.executable,
            os.fspath(ROOT / "scripts" / "codex_orch_tools.py"),
            "validate",
            os.fspath(self.run_dir),
            "--gates",
        ]
        first = subprocess.run(command, check=False, capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        payload = json.loads(first.stdout)
        self.records[-1]["validation"] = payload
        self.write_journal()
        second = subprocess.run(command, check=False, capture_output=True, text=True)
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.post_payload = json.loads(second.stdout)
        self.assertEqual(self.post_payload, payload)
        self.post_close.write_text(
            json.dumps(self.post_payload, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )

    def learning_provenance_from_input(
        self, archive_input: list[dict[str, str]]
    ) -> dict[str, object]:
        self.assertEqual(len(archive_input), 1)
        element = archive_input[0]
        self.assertEqual(set(element), {"content", "head", "path"})
        self.assertEqual(element["path"], self.archive_relative.as_posix())
        begin = "<!-- BEGIN FORGE LEARNING PROVENANCE v1 -->\n```json\n"
        end = "\n```\n<!-- END FORGE LEARNING PROVENANCE v1 -->"
        self.assertEqual(element["content"].count(begin), 1)
        self.assertEqual(element["content"].count(end), 1)
        encoded = element["content"].split(begin, 1)[1].split(end, 1)[0]
        provenance = json.loads(encoded)
        self.assertEqual(
            set(provenance),
            {"decisions", "executions", "failed_or_inconclusive_verifications"},
        )
        return provenance

    def invoke(
        self,
        *,
        archiver: Path = ARCHIVER,
        closing_head: str | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [
                sys.executable,
                os.fspath(archiver),
                "--run-dir",
                os.fspath(self.run_dir),
                "--closing-head",
                closing_head or self.git("rev-parse", "HEAD").stdout.strip(),
                "--post-close-validation",
                os.fspath(self.post_close),
            ],
            cwd=self.repo,
            check=False,
            capture_output=True,
        )

    def mutant_archiver(self, name: str, needle: str, replacement: str) -> Path:
        """Create an isolated script tree with exactly one disabled control."""

        mutant_root = self.root / name
        shutil.copytree(ROOT / "scripts", mutant_root / "scripts")
        mutant = mutant_root / "scripts" / "forge" / "archive-run.py"
        source = mutant.read_text(encoding="utf-8")
        self.assertEqual(source.count(needle), 1, needle)
        mutant.write_text(source.replace(needle, replacement), encoding="utf-8")
        return mutant

    def install_repo_conformance_authority(self) -> str:
        """Make the fixture a minimal forge-plugin source repository."""

        sources = (
            Path(".claude-plugin/plugin.json"),
            Path("agents/review-final.md"),
            Path("docs/specs/forge-plugin-spec.md"),
            Path("system/codex/agents/implementer.toml"),
            Path("system/codex/agents/review-cheap.toml"),
            Path("tests/test_repo_conformance.py"),
        )
        for relative in sources:
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / relative).read_bytes())
        # The conformance walk is fail closed when the governed script root is
        # unavailable. This fixture has no governed executables of its own.
        (self.repo / "scripts/forge").mkdir(parents=True)
        self.git("add", *(relative.as_posix() for relative in sources))
        self.git("commit", "--quiet", "-m", "install routing authority")
        return self.git("rev-parse", "HEAD").stdout.strip()

    def assert_archive_absent_and_unstaged(self) -> None:
        self.assertFalse(self.archive_path.exists())
        self.assertEqual(self.git("diff", "--cached", "--name-only").stdout, "")

    def test_renders_deterministic_complete_archive_and_stages_only_it(self) -> None:
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(result.stdout, os.fsencode(self.archive_relative.as_posix() + "\n"))
        self.assertEqual(result.stderr, b"")
        self.assertEqual(
            self.git("diff", "--cached", "--name-only").stdout,
            self.archive_relative.as_posix() + "\n",
        )
        self.assertEqual(self.git("diff", "--name-only").stdout, "")
        self.assertEqual(
            self.git("ls-files", "--others", "--exclude-standard").stdout,
            "",
        )

        archive = self.archive_path.read_bytes()
        text = archive.decode("utf-8")
        self.assertIn("Ship the durable intent archive.", text)
        self.assertIn("Archive is deterministic.", text)
        self.assertIn("Final status: complete", text)
        self.assertIn("Final outcome: Implemented and independently reviewed.", text)
        self.assertIn("decision-07", text)
        self.assertIn("gate-3: review-final verdict", text)
        self.assertIn(
            f"{self.starting_head}..{self.starting_head}",
            text,
        )
        self.assertIn("| passed | PASS | 2 |", text)
        self.assertIn("## Residual Risks\n\n- A later schema migration", text)
        self.assertIn("## Follow-ups\n\n- Implement D12 separately.", text)
        self.assertIn(f"Starting HEAD: {self.starting_head}", text)
        self.assertIn(f"Closing HEAD: {self.starting_head}", text)
        self.assertEqual(text.count("Closing HEAD:"), 1)
        self.assertNotIn("Archive commit", text)

        first = b"<!-- BEGIN VERBATIM DOCUMENT: claude-plan.md#fr-124 -->\n"
        last = b"<!-- END VERBATIM DOCUMENT: claude-plan.md#fr-124 -->"
        self.assertEqual(archive.split(first, 1)[1].split(last, 1)[0], (self.run_dir / "claude-plan.md").read_bytes())
        first = b"<!-- BEGIN VERBATIM DOCUMENT: Independent proposal: `codex-contract.txt` -->\n"
        last = b"<!-- END VERBATIM DOCUMENT: Independent proposal: `codex-contract.txt` -->"
        self.assertEqual(archive.split(first, 1)[1].split(last, 1)[0], (self.run_dir / "codex-contract.txt").read_bytes())
        first = b'<!-- BEGIN VERBATIM DOCUMENT: [ADR](plan%20choice.yaml "binding choice") -->\n'
        last = b'<!-- END VERBATIM DOCUMENT: [ADR](plan%20choice.yaml "binding choice") -->'
        self.assertEqual(archive.split(first, 1)[1].split(last, 1)[0], (self.run_dir / "plan choice.yaml").read_bytes())

    def test_committed_learning_provenance_reaches_real_locked_writer(self) -> None:
        prior_gotchas = b"# Forge Gotchas\n\n- Prior committed observation.\n"
        (self.repo / "forge-project.md").write_text(
            "# Project\n\n"
            "<!-- FORGE:REGION agent-project-context BEGIN -->\n"
            "Durable archive context for later agents.\n"
            "<!-- FORGE:REGION agent-project-context END -->\n",
            encoding="utf-8",
        )
        gotchas_path = self.repo / ".forge/history/gotchas.md"
        gotchas_path.parent.mkdir(parents=True)
        gotchas_path.write_bytes(prior_gotchas)
        self.git("add", "forge-project.md", ".forge/history/gotchas.md")
        self.git("commit", "--quiet", "-m", "add project context")
        prompt = self.add_learning_evidence()
        self.synchronize_validation_payloads()

        reviewer = self.root / "fresh-review-periodic.py"
        reviewer.write_text(FRESH_ARCHIVE_REVIEWER, encoding="utf-8")

        def review(
            archive_input: list[dict[str, str]], *, expect_success: bool
        ) -> subprocess.CompletedProcess[bytes]:
            patterns_path = self.root / "input-1-journal-patterns.json"
            archives_path = self.root / "input-2-committed-archives.json"
            gotchas_path = self.root / "input-3-committed-gotchas.json"
            for path in (patterns_path, archives_path, gotchas_path):
                if path.exists():
                    path.chmod(0o644)
            patterns_path.write_text(
                json.dumps(
                    {
                        "available": True,
                        "decision_outcomes": {},
                        "diagnostics": [],
                        "failure": "",
                        "findings": {"by_reviewer_role": {}, "by_severity": {}},
                        "routing": [],
                        "tasks": [],
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n",
                encoding="utf-8",
            )
            archives_path.write_text(
                json.dumps(archive_input, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            gotchas_path.write_text(
                json.dumps(
                    {
                        "content": self.git(
                            "show",
                            f'{archive_input[0]["head"]}:.forge/history/gotchas.md',
                        ).stdout,
                        "head": archive_input[0]["head"],
                        "path": ".forge/history/gotchas.md",
                        "present": True,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n",
                encoding="utf-8",
            )
            for path in (patterns_path, archives_path, gotchas_path):
                path.chmod(0o444)
            before = self.git("status", "--porcelain=v1", "--untracked-files=all").stdout
            result = subprocess.run(
                [
                    sys.executable,
                    os.fspath(reviewer),
                    os.fspath(patterns_path),
                    os.fspath(archives_path),
                    os.fspath(gotchas_path),
                ],
                cwd=self.root,
                check=False,
                capture_output=True,
                env={
                    **os.environ,
                    "FORGE_REVIEW_ACCESS": "read-only",
                    "FORGE_REVIEW_PROFILE": "review-periodic",
                },
            )
            after = self.git("status", "--porcelain=v1", "--untracked-files=all").stdout
            self.assertEqual(after, before, "read-only reviewer mutated the repository")
            if expect_success:
                self.assertEqual(result.returncode, 0, result.stderr.decode())
            else:
                self.assertNotEqual(result.returncode, 0)
            return result

        mutant = self.mutant_archiver(
            "learning-provenance-disabled",
            "*canonical_json(learning_provenance(records, run_dir)),",
            '*canonical_json({"decisions": [], "executions": [], "failed_or_inconclusive_verifications": []}),',
        )
        disabled = self.invoke(archiver=mutant)
        self.assertEqual(disabled.returncode, 0, disabled.stderr.decode())
        disabled_input = [
            {
                "content": self.archive_path.read_text(encoding="utf-8"),
                "head": self.git("rev-parse", "HEAD").stdout.strip(),
                "path": self.archive_relative.as_posix(),
            }
        ]
        review(disabled_input, expect_success=False)

        self.git("reset", "--quiet")
        self.archive_path.unlink()
        restored = self.invoke()
        self.assertEqual(restored.returncode, 0, restored.stderr.decode())
        self.git("commit", "--quiet", "-m", "archive learning provenance")
        input_head = self.git("rev-parse", "HEAD").stdout.strip()
        committed_content = self.git(
            "show", f"{input_head}:{self.archive_relative.as_posix()}"
        ).stdout
        archive_input = [
            {
                "content": committed_content,
                "head": input_head,
                "path": self.archive_relative.as_posix(),
            }
        ]
        provenance = self.learning_provenance_from_input(archive_input)
        self.assertEqual(
            provenance["executions"],
            [
                {
                    "agent": "review-cheap-archive",
                    "execution": "execution-01",
                    "prompt": "agents/review-cheap-archive/execution-01/prompt.md",
                    "prompt_sha256": hashlib.sha256(prompt).hexdigest(),
                    "role": "review",
                    "task": "task-07",
                }
            ],
        )
        self.assertEqual(
            provenance["failed_or_inconclusive_verifications"],
            [
                {
                    "criterion": "acceptance: archive boundary failure",
                    "id": "verification-learning-01",
                    "observation": "The boundary failure escaped the earlier review control.",
                    "result": "failed",
                    "task": "task-07",
                }
            ],
        )
        reviewed = review(archive_input, expect_success=True)
        proposal = json.loads(reviewed.stdout)
        self.assertEqual(proposal["input_head"], input_head)
        self.assertEqual(proposal["candidates"][0]["agent"], "review-cheap-archive")
        self.assertEqual(proposal["candidates"][0]["execution"], "execution-01")
        self.assertEqual(proposal["candidates"][0]["run_id"], self.run_dir.name)
        self.assertEqual(
            proposal["gotchas"][0]["entries"],
            [
                {"id": "decision-07", "type": "decision"},
                {"id": "verification-learning-01", "type": "verification"},
            ],
        )

        citation = f"[archive: {input_head}:{self.archive_relative.as_posix()}]"
        candidate_archive = (
            f"- archive: `{input_head}:{self.archive_relative.as_posix()}`"
        )
        proposal_path = self.root / "review-output.json"
        proposal_path.write_bytes(reviewed.stdout)
        installed_run = (
            self.repo / ".codex-orchestrator" / "runs" / self.run_dir.name
        )
        installed_run.parent.mkdir(parents=True)
        shutil.copytree(self.run_dir, installed_run)
        before_writer_status = set(
            self.git("status", "--porcelain=v1", "--untracked-files=all").stdout.splitlines()
        )

        written = subprocess.run(
            [
                sys.executable,
                os.fspath(LOCKED_LEARN_WRITER),
                "--repo",
                os.fspath(self.repo),
                "--proposal",
                os.fspath(proposal_path),
            ],
            check=False,
            capture_output=True,
        )
        self.assertEqual(written.returncode, 0, written.stderr.decode())
        candidate = self.repo / ".forge/evals/candidates/archive-review-boundary.md"
        candidate_bytes = candidate.read_bytes()
        self.assertIn(prompt, candidate_bytes)
        self.assertIn(candidate_archive.encode(), candidate_bytes)
        gotchas_bytes = gotchas_path.read_bytes()
        self.assertTrue(gotchas_bytes.startswith(prior_gotchas))
        gotchas = gotchas_bytes.decode("utf-8")
        self.assertIn(citation, gotchas)
        self.assertIn("decision:decision-07", gotchas)
        self.assertIn("verification:verification-learning-01", gotchas)
        after_writer_status = set(
            self.git("status", "--porcelain=v1", "--untracked-files=all").stdout.splitlines()
        )
        self.assertTrue(before_writer_status <= after_writer_status)
        self.assertEqual(
            after_writer_status - before_writer_status,
            {
                " M .forge/history/gotchas.md",
                "?? .forge/evals/candidates/archive-review-boundary.md",
            },
        )

        self.git("add", ".forge/history/gotchas.md")
        self.git("commit", "--quiet", "-m", "commit learned gotcha")
        next_input = self.git("show", "HEAD:.forge/history/gotchas.md").stdout
        self.assertIn(citation, next_input)
        self.assertIn("verification:verification-learning-01", next_input)
        assignment = "## Assignment\n\nReview the next archived boundary."
        later_prompt = assemble_codex_prompt(
            execution_worktree=self.repo,
            template_name="review-cheap.md",
            task_assignment=assignment,
        )
        template = (ROOT / "system/codex/prompts/review-cheap.md").read_bytes()
        context_at = later_prompt.index(b"Durable archive context for later agents.")
        gotcha_at = later_prompt.index(citation.encode("utf-8"))
        assignment_at = later_prompt.index(assignment.encode("utf-8"))
        self.assertTrue(later_prompt.startswith(template))
        self.assertLess(context_at, gotcha_at)
        self.assertLess(gotcha_at, assignment_at)
        self.assertEqual(
            self.git(
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
                "--",
                ".forge/evals/candidates",
            ).stdout,
            "?? .forge/evals/candidates/archive-review-boundary.md\n",
        )

    def test_hardlinked_recorded_prompt_is_not_citable_and_kills_disabled_filter(self) -> None:
        prompt = self.add_learning_evidence()
        self.synchronize_validation_payloads()

        def provenance(text: str) -> dict[str, object]:
            return self.learning_provenance_from_input(
                [
                    {
                        "content": text,
                        "head": self.git("rev-parse", "HEAD").stdout.strip(),
                        "path": self.archive_relative.as_posix(),
                    }
                ]
            )

        def without_learning_provenance(text: str) -> str:
            begin = "<!-- BEGIN FORGE LEARNING PROVENANCE v1 -->"
            end = "<!-- END FORGE LEARNING PROVENANCE v1 -->"
            start = text.index(begin)
            finish = text.index(end, start) + len(end)
            return text[:start] + text[finish:]

        baseline = self.invoke()
        self.assertEqual(baseline.returncode, 0, baseline.stderr.decode())
        baseline_text = self.archive_path.read_text(encoding="utf-8")
        baseline_provenance = provenance(baseline_text)
        self.assertEqual(len(baseline_provenance["executions"]), 1)
        self.git("reset", "--quiet")
        self.archive_path.unlink()

        recorded = (
            self.run_dir
            / "agents"
            / "review-cheap-archive"
            / "execution-01"
            / "prompt.md"
        )
        outside = self.root / "outside-prompt.md"
        outside.write_bytes(prompt)
        recorded.unlink()
        os.link(outside, recorded)

        def archive_oracle(result: subprocess.CompletedProcess[bytes]) -> tuple[str, dict[str, object]]:
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(result.stdout, os.fsencode(self.archive_relative.as_posix() + "\n"))
            self.assertEqual(result.stderr, b"")
            self.assertEqual(
                self.git("diff", "--cached", "--name-only").stdout,
                self.archive_relative.as_posix() + "\n",
            )
            text = self.archive_path.read_text(encoding="utf-8")
            authority = provenance(text)
            self.assertEqual(authority["executions"], [])
            self.assertEqual(authority["decisions"], baseline_provenance["decisions"])
            self.assertEqual(
                authority["failed_or_inconclusive_verifications"],
                baseline_provenance["failed_or_inconclusive_verifications"],
            )
            self.assertEqual(
                without_learning_provenance(text),
                without_learning_provenance(baseline_text),
            )
            return text, authority

        controlled = self.invoke()
        controlled_text, _ = archive_oracle(controlled)

        self.git("reset", "--quiet")
        self.archive_path.unlink()

        needle = (
            "    except ArchiveRefusal:\n"
            "        # Learning provenance is advisory. A missing or unsafe recorded prompt\n"
            "        # removes this execution's citation authority; it must not invalidate an\n"
            "        # otherwise canonical close/archive transaction.\n"
            "        return None\n"
        )
        replacement = (
            "    except ArchiveRefusal:\n"
            "        prompt = str(record[\"prompt\"])\n"
            "        digest = hashlib.sha256((run_dir / prompt).read_bytes()).hexdigest()\n"
        )
        mutant = self.mutant_archiver(
            "recorded-prompt-omit-disabled", needle, replacement
        )
        disabled = self.invoke(archiver=mutant)

        self.assertEqual(disabled.returncode, 0, disabled.stderr.decode())
        with self.assertRaises(AssertionError):
            archive_oracle(disabled)
        disabled_text = self.archive_path.read_text(encoding="utf-8")
        disabled_provenance = provenance(disabled_text)
        self.assertEqual(len(disabled_provenance["executions"]), 1)
        self.assertEqual(
            disabled_provenance["executions"][0]["prompt_sha256"],
            hashlib.sha256(prompt).hexdigest(),
        )
        self.assertEqual(
            without_learning_provenance(disabled_text),
            without_learning_provenance(controlled_text),
        )

    def test_copies_every_document_when_one_basis_names_multiple_files(self) -> None:
        decision = next(record for record in self.records if record.get("type") == "decision")
        decision["basis"] = ["claude-plan.md and codex-contract.txt"]
        self.write_journal()

        result = self.invoke()

        self.assertEqual(result.returncode, 0, result.stderr.decode())
        archive = self.archive_path.read_bytes()
        label = b"claude-plan.md and codex-contract.txt"
        self.assertEqual(archive.count(b"<!-- BEGIN VERBATIM DOCUMENT:"), 2)
        self.assertEqual(archive.count(b"<!-- BEGIN VERBATIM DOCUMENT: " + label + b" -->"), 2)
        self.assertIn((self.run_dir / "claude-plan.md").read_bytes(), archive)
        self.assertIn((self.run_dir / "codex-contract.txt").read_bytes(), archive)

    def test_copies_angle_bracket_and_extensionless_basis_documents(self) -> None:
        decision = next(record for record in self.records if record.get("type") == "decision")
        decision["basis"] = ["[ADR](<plan choice.yaml>)", "Makefile"]
        self.write_journal()

        result = self.invoke()

        self.assertEqual(result.returncode, 0, result.stderr.decode())
        archive = self.archive_path.read_bytes()
        self.assertIn((self.run_dir / "plan choice.yaml").read_bytes(), archive)
        self.assertIn((self.run_dir / "Makefile").read_bytes(), archive)

    def test_citation_corrections_section_reaches_written_archive(self) -> None:
        decision = next(record for record in self.records if record.get("type") == "decision")
        decision["basis"] = ["missing/original.md"]
        self.records.insert(
            -1,
            {
                "type": "decision",
                "id": "decision-citation-correction",
                "finding": "Correct a citation.",
                "outcome": "operator_decision",
                "resolution": "citation-correction:\ndecision-07 basis[0]: claude-plan.md",
                "basis": [],
                "risk": "low",
            },
        )
        self.write_journal()

        result = self.invoke()

        self.assertEqual(result.returncode, 0, result.stderr.decode())
        text = self.archive_path.read_text(encoding="utf-8")
        self.assertIn("## Citation Corrections\n", text)
        self.assertIn(
            "decision decision-citation-correction applied to decision decision-07 basis[0]: "
            "missing/original.md -> claude-plan.md",
            text,
        )
        provenance = self.learning_provenance_from_input(
            [
                {
                    "content": text,
                    "head": self.git("rev-parse", "HEAD").stdout.strip(),
                    "path": self.archive_relative.as_posix(),
                }
            ]
        )
        self.assertEqual(
            provenance["decisions"], [{"id": "decision-07", "task": "task-07"}]
        )

        self.git("reset", "--quiet")
        self.archive_path.unlink()
        mutant = self.mutant_archiver(
            "citation-corrections-disabled",
            'lines.extend(["", audit_fragment.rstrip("\\n"), "", "## Provenance", ""])',
            'lines.extend(["", "## Residual Risks\\n\\n- none", "", "## Provenance", ""])',
        )

        disabled = self.invoke(archiver=mutant)

        self.assertEqual(disabled.returncode, 0, disabled.stderr.decode())
        disabled_text = self.archive_path.read_text(encoding="utf-8")
        # Re-run the positive archive-layer sensor against the disabled control:
        # these are the exact predicates above, negated only so this outer mutant
        # test can prove that both original assertions would fail.
        positive_assertions = (
            "## Citation Corrections\n" in disabled_text,
            (
                "decision decision-citation-correction applied to decision "
                "decision-07 basis[0]: missing/original.md -> claude-plan.md"
                in disabled_text
            ),
        )
        self.assertEqual(positive_assertions, (False, False))

    def test_historical_routing_findings_reach_written_archive(self) -> None:
        authority_head = self.install_repo_conformance_authority()
        handoff = "routing-review-handoff.md"
        (self.run_dir / handoff).write_text("Historical route reviewed.\n", encoding="utf-8")
        executions = [
            {
                "type": "execution",
                "agent": "codex-review-historical",
                "execution": "execution-01",
                "task": "task-07",
                "provider": "codex",
                "role": "review",
                "head": authority_head,
                "model": "gpt-5.6-terra",
                "effort": "medium",
                "handoff": handoff,
                "event_source": "exec",
            },
            {
                "type": "execution_result",
                "agent": "codex-review-historical",
                "execution": "execution-01",
                "task": "task-07",
                "status": "complete",
                "handoff": handoff,
            },
            {
                "type": "execution",
                "agent": "claude-review-historical",
                "execution": "execution-01",
                "task": "task-07",
                "provider": "claude",
                "role": "review",
                "head": authority_head,
                "model": "fable",
                "effort": "medium",
                "handoff": handoff,
                "event_source": "claude",
            },
            {
                "type": "execution_result",
                "agent": "claude-review-historical",
                "execution": "execution-01",
                "task": "task-07",
                "status": "complete",
                "handoff": handoff,
            },
        ]
        self.records[-2:-2] = executions
        self.write_journal()
        journal_lines = {
            record["agent"]: line_number
            for line_number, record in enumerate(self.records, 1)
            if record.get("type") == "execution"
        }
        expected = (
            (
                f"journal line {journal_lines['codex-review-historical']}: agent "
                "'codex-review-historical' recorded model/effort "
                "('gpt-5.6-terra', 'medium'); expected model/effort "
                f"('gpt-5.6-sol', 'high') from {authority_head}:"
                "system/codex/agents/review-cheap.toml"
            ),
            (
                f"journal line {journal_lines['claude-review-historical']}: agent "
                "'claude-review-historical' recorded model/effort "
                "('fable', 'medium'); expected model/effort ('fable', 'high') "
                f"from {authority_head}:agents/review-final.md"
            ),
        )

        result = self.invoke()

        self.assertEqual(result.returncode, 0, result.stderr.decode())
        archive = self.archive_path.read_text(encoding="utf-8")
        self.assertEqual(archive.count("## Historical Routing Findings\n"), 1)
        for finding in expected:
            self.assertIn(f"- {finding}\n", archive)
        provenance = self.learning_provenance_from_input(
            [
                {
                    "content": archive,
                    "head": self.git("rev-parse", "HEAD").stdout.strip(),
                    "path": self.archive_relative.as_posix(),
                }
            ]
        )
        self.assertEqual(provenance["executions"], [])

        self.git("reset", "--quiet")
        self.archive_path.unlink()
        mutant = self.mutant_archiver(
            "historical-routing-findings-disabled",
            "    audit_fragment = run_audit(run_dir, dispense_targets, dispense_reason)\n",
            (
                "    audit_fragment = run_audit(run_dir, dispense_targets, dispense_reason)\n"
                "    if audit_fragment.startswith(\"## Historical Routing Findings\\n\"):\n"
                "        audit_fragment = (\"## Residual Risks\" + "
                "audit_fragment.split(\"## Residual Risks\", 1)[1])\n"
            ),
        )

        disabled = self.invoke(archiver=mutant)

        self.assertEqual(disabled.returncode, 0, disabled.stderr.decode())
        disabled_archive = self.archive_path.read_text(encoding="utf-8")
        # These are the positive archive predicates above evaluated after the
        # routing-finding inclusion control has been disabled in isolation.
        self.assertEqual(
            (
                "## Historical Routing Findings\n" in disabled_archive,
                *(f"- {finding}\n" in disabled_archive for finding in expected),
            ),
            (False, False, False),
        )

    def test_output_is_byte_deterministic_across_equivalent_repositories(self) -> None:
        first = self.invoke()
        self.assertEqual(first.returncode, 0, first.stderr.decode())
        first_bytes = self.archive_path.read_bytes()
        # The already-created path is append-only. A fresh equivalent repository
        # must produce the same bytes without relying on timestamps or agent memory.
        self.git("reset", "--quiet", "HEAD", "--", self.archive_relative.as_posix())
        self.archive_path.unlink()
        second = self.invoke()
        self.assertEqual(second.returncode, 0, second.stderr.decode())
        self.assertEqual(self.archive_path.read_bytes(), first_bytes)

    def test_refuses_tracked_untracked_and_staged_contamination_byte_exact(self) -> None:
        variants = ("tracked", "untracked", "staged")
        for variant in variants:
            with self.subTest(variant=variant):
                if variant == "tracked":
                    (self.repo / "tracked.txt").write_text("changed\n", encoding="utf-8")
                else:
                    (self.repo / "unrelated.txt").write_text("unrelated\n", encoding="utf-8")
                    if variant == "staged":
                        self.git("add", "unrelated.txt")
                result = self.invoke()
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, b"")
                self.assertEqual(result.stderr, CONTAMINATION.encode())
                self.assertFalse(self.archive_path.exists())
                if variant == "tracked":
                    self.git("restore", "tracked.txt")
                elif variant == "untracked":
                    (self.repo / "unrelated.txt").unlink()
                else:
                    self.git("reset", "--quiet", "HEAD", "--", "unrelated.txt")
                    (self.repo / "unrelated.txt").unlink()

    def test_refuses_overwrite_without_changing_existing_archive(self) -> None:
        first = self.invoke()
        self.assertEqual(first.returncode, 0, first.stderr.decode())
        before = self.archive_path.read_bytes()
        second = self.invoke()
        self.assertEqual(second.returncode, 1)
        self.assertEqual(second.stdout, b"")
        self.assertEqual(
            second.stderr,
            (
                "forge: archive refused — archive already exists: "
                f"{self.archive_relative.as_posix()}\n"
            ).encode(),
        )
        self.assertEqual(self.archive_path.read_bytes(), before)

    def test_audit_failure_is_propagated_before_archive_bytes(self) -> None:
        decision = next(record for record in self.records if record["type"] == "decision")
        decision["task"] = "task-99"
        self.write_journal()
        # Audit runs before fresh gated validation, so this distinct audit
        # violation must be the reported failure.
        result = self.invoke()
        self.assertEqual(result.returncode, 3)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(
            result.stderr,
            b"forge: commitment audit failed \xe2\x80\x94 unknown task reference: task-99 (decision decision-07 task field)\n",
        )
        self.assert_archive_absent_and_unstaged()

    def test_wrong_closing_head_and_nonpassing_validation_fail_closed(self) -> None:
        wrong = self.invoke(closing_head="0" * 40)
        self.assertEqual(wrong.returncode, 1)
        self.assertEqual(
            wrong.stderr,
            b"forge: archive refused \xe2\x80\x94 closing HEAD does not match repository HEAD\n",
        )
        self.assert_archive_absent_and_unstaged()

    def test_stale_post_close_and_invalid_pre_close_fail_closed(self) -> None:
        self.records[-1]["validation"] = {"ok": True, "profile": "baseline", "issues": []}
        self.write_journal()
        invalid_pre = self.invoke()
        self.assertEqual(invalid_pre.returncode, 1)
        self.assertEqual(
            invalid_pre.stderr,
            b"forge: archive refused \xe2\x80\x94 pre-close gated validation did not pass\n",
        )
        self.assert_archive_absent_and_unstaged()

        self.records[-1]["validation"] = dict(self.post_payload)
        self.records[3]["result"] = "failed"
        self.write_journal()
        stale = self.invoke()
        self.assertEqual(stale.returncode, 1)
        self.assertEqual(
            stale.stderr,
            b"forge: archive refused \xe2\x80\x94 pre-close gated validation is stale or does not match journal\n",
        )
        self.assert_archive_absent_and_unstaged()

    def test_well_formed_but_stale_pre_close_payload_fails_closed(self) -> None:
        self.records[-1]["validation"] = {
            "issues": [],
            "non_passing_verifications": [],
            "ok": True,
            "profile": "gates",
            "warnings": ["fabricated stale warning"],
        }
        self.write_journal()

        result = self.invoke()

        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            result.stderr,
            b"forge: archive refused \xe2\x80\x94 pre-close gated validation is stale or does not match journal\n",
        )
        self.assert_archive_absent_and_unstaged()

    def test_pre_close_freshness_control_is_killed(self) -> None:
        self.records[-1]["validation"] = {
            "issues": [],
            "non_passing_verifications": [],
            "ok": True,
            "profile": "gates",
            "warnings": ["fabricated stale warning"],
        }
        self.write_journal()
        intact = self.invoke()
        self.assertEqual(intact.returncode, 1)
        self.assert_archive_absent_and_unstaged()

        mutant = self.mutant_archiver(
            "mutant-pre-close-freshness",
            "    if not is_passing_gated_payload(fresh_pre_close) or embedded_pre_close != fresh_pre_close:\n        raise ArchiveRefusal(\n            \"forge: archive refused — pre-close gated validation is stale or does not match journal\"\n        )\n",
            "    pass  # CONTROL DISABLED: pre-close freshness binding\n",
        )
        result = self.invoke(archiver=mutant)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertIn(
            '"fabricated stale warning"',
            self.archive_path.read_text(encoding="utf-8"),
        )

    def test_unexpected_post_write_exception_rolls_back_archive_and_index(self) -> None:
        mutant_root = self.root / "unexpected-failure-plugin"
        shutil.copytree(ROOT / "scripts", mutant_root / "scripts")
        mutant = mutant_root / "scripts" / "forge" / "archive-run.py"
        source = mutant.read_text(encoding="utf-8")
        needle = '        staged_blob = git_stdout(repo, "show", f":{relative}")\n'
        replacement = '        raise OSError("injected unexpected failure")\n' + needle
        self.assertEqual(source.count(needle), 1)
        mutant.write_text(source.replace(needle, replacement), encoding="utf-8")

        result = self.invoke(archiver=mutant)

        self.assertNotEqual(result.returncode, 0)
        self.assert_archive_absent_and_unstaged()

    def test_unexpected_exception_during_initial_write_rolls_back_archive(self) -> None:
        mutant_root = self.root / "initial-write-failure-plugin"
        shutil.copytree(ROOT / "scripts", mutant_root / "scripts")
        mutant = mutant_root / "scripts" / "forge" / "archive-run.py"
        source = mutant.read_text(encoding="utf-8")
        needle = "        created = True\n        with handle:\n"
        replacement = (
            "        created = True\n"
            "        raise KeyboardInterrupt('injected initial-write failure')\n"
            "        with handle:\n"
        )
        self.assertEqual(source.count(needle), 1)
        mutant.write_text(source.replace(needle, replacement), encoding="utf-8")

        result = self.invoke(archiver=mutant)

        self.assertNotEqual(result.returncode, 0)
        self.assert_archive_absent_and_unstaged()

    def test_cleanup_still_unlinks_when_git_unstage_raises(self) -> None:
        mutant_root = self.root / "cleanup-git-exception-plugin"
        shutil.copytree(ROOT / "scripts", mutant_root / "scripts")
        mutant = mutant_root / "scripts" / "forge" / "archive-run.py"
        source = mutant.read_text(encoding="utf-8")
        race = '        staged_blob = git_stdout(repo, "show", f":{relative}")\n'
        self.assertEqual(source.count(race), 1)
        source = source.replace(
            race,
            '        raise OSError("injected post-stage failure")\n' + race,
        )
        unstage = (
            '        removed = run_git(\n'
            '            repo, "rm", "--cached", "--force", "--ignore-unmatch", "--", relative\n'
            '        )\n'
        )
        self.assertEqual(source.count(unstage), 1)
        source = source.replace(
            unstage,
            '        raise OSError("injected git launch failure")\n',
        )
        mutant.write_text(source, encoding="utf-8")

        result = self.invoke(archiver=mutant)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            result.stderr,
            b"forge: archive refused \xe2\x80\x94 transaction rollback failed\n",
        )
        self.assertFalse(self.archive_path.exists())

    def test_rejects_fabricated_starting_head(self) -> None:
        self.records[0]["repo_head"] = "0" * 40
        self.write_journal()
        result = self.invoke()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            result.stderr,
            b"forge: archive refused \xe2\x80\x94 starting HEAD is not a repository commit\n",
        )
        self.assert_archive_absent_and_unstaged()

    def test_rejects_staged_byte_normalization_and_rolls_back(self) -> None:
        (self.repo / ".gitattributes").write_text(
            ".forge/history/runs/*.md text eol=crlf\n", encoding="utf-8"
        )
        self.git("add", ".gitattributes")
        self.git("commit", "--quiet", "-m", "normalize history")
        # Keep command-derived provenance consistent with the implementation
        # commit immediately preceding archive generation.
        head = self.git("rev-parse", "HEAD").stdout.strip()
        self.records[0]["repo_head"] = head
        self.write_journal()
        result = self.invoke(closing_head=head)
        self.assertEqual(result.returncode, 1)
        self.assertIn(
            result.stderr,
            {
                b"forge: archive refused \xe2\x80\x94 could not stage archive\n",
                b"forge: archive refused \xe2\x80\x94 staged archive bytes differ from rendered archive\n",
            },
        )
        self.assert_archive_absent_and_unstaged()

    def test_staged_byte_identity_control_is_killed(self) -> None:
        (self.repo / ".gitattributes").write_text(
            ".forge/history/runs/*.md text eol=crlf\n", encoding="utf-8"
        )
        self.git("add", ".gitattributes")
        self.git("commit", "--quiet", "-m", "normalize staged archives")
        head = self.git("rev-parse", "HEAD").stdout.strip()
        self.records[0]["repo_head"] = head
        self.write_journal()

        intact = self.invoke(closing_head=head)
        self.assertEqual(intact.returncode, 1)
        self.assert_archive_absent_and_unstaged()

        mutant = self.mutant_archiver(
            "mutant-staged-bytes",
            '        if staged_blob != rendered_bytes:\n            raise ArchiveRefusal(\n                "forge: archive refused — staged archive bytes differ from rendered archive"\n            )\n',
            "        pass  # CONTROL DISABLED: staged byte identity\n",
        )
        # Git may reject the add rather than normalize it on some versions. In
        # this isolated mutant, replace the add with hash-object/update-index so
        # only the staged-byte identity control determines acceptance.
        source = mutant.read_text(encoding="utf-8")
        needle = '        add = run_git(repo, "add", "--", relative)\n        if add.returncode != 0:\n            raise ArchiveRefusal("forge: archive refused — could not stage archive")\n'
        replacement = (
            '        normalized = archive_path.read_bytes().replace(b"\\n", b"\\r\\n")\n'
            '        blob_proc = subprocess.run(["git", "hash-object", "-w", "--stdin"], cwd=repo, input=normalized, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)\n'
            '        blob = blob_proc.stdout.decode("ascii").strip()\n'
            '        add = run_git(repo, "update-index", "--add", "--cacheinfo", "100644", blob, relative)\n'
            '        if add.returncode != 0:\n            raise ArchiveRefusal("forge: archive refused — could not stage archive")\n'
        )
        self.assertEqual(source.count(needle), 1)
        mutant.write_text(source.replace(needle, replacement), encoding="utf-8")
        escaped = self.invoke(archiver=mutant, closing_head=head)
        self.assertEqual(escaped.returncode, 1)
        # With the byte check disabled, the normalized staged blob survives
        # until the independent final postproof rejects the worktree mismatch.
        # The intact byte check rejects earlier with its dedicated diagnostic.
        self.assertEqual(escaped.stderr, CONTAMINATION.encode())

    def test_starting_commit_binding_mutant_is_killed(self) -> None:
        self.records[0]["repo_head"] = "0" * 40
        self.write_journal()
        mutant = self.mutant_archiver(
            "mutant-starting-head",
            '    start_commit = run_git(repo, "cat-file", "-e", f"{starting_head}^{{commit}}")\n    if start_commit.returncode != 0:\n        raise ArchiveRefusal("forge: archive refused — starting HEAD is not a repository commit")\n',
            "    pass  # CONTROL DISABLED: starting-HEAD commit binding\n",
        )
        result = self.invoke(archiver=mutant)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertIn("Starting HEAD: " + "0" * 40, self.archive_path.read_text(encoding="utf-8"))

    def test_refuses_foreign_run_repository(self) -> None:
        started = self.records[0]
        started["repo"] = os.fspath(self.root / "foreign-repository")
        (self.root / "foreign-repository").mkdir()
        self.write_journal()
        result = self.invoke()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(
            result.stderr,
            b"forge: archive refused \xe2\x80\x94 run repository does not match current repository\n",
        )
        self.assert_archive_absent_and_unstaged()

    def test_post_write_contamination_rolls_back_archive_and_index(self) -> None:
        """A race after the clean proof is detected and the archive is removed."""
        mutant_root = self.root / "race-plugin"
        shutil.copytree(ROOT / "scripts", mutant_root / "scripts")
        mutant = mutant_root / "scripts" / "forge" / "archive-run.py"
        source = mutant.read_text(encoding="utf-8")
        needle = "    try:\n        if nul_paths(git_stdout(repo, \"diff\", \"--name-only\", \"-z\")):\n"
        replacement = (
            "    try:\n"
            "        (repo / 'raced-unrelated.txt').write_text('race\\n', encoding='utf-8')\n"
            "        if nul_paths(git_stdout(repo, \"diff\", \"--name-only\", \"-z\")):\n"
        )
        self.assertEqual(source.count(needle), 1)
        mutant.write_text(source.replace(needle, replacement), encoding="utf-8")
        result = self.invoke(archiver=mutant)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr, CONTAMINATION.encode())
        self.assert_archive_absent_and_unstaged()
        self.assertTrue((self.repo / "raced-unrelated.txt").is_file())

    def test_rollback_verification_control_is_killed(self) -> None:
        mutant = self.mutant_archiver(
            "mutant-rollback",
            '    if failed:\n        raise ArchiveRefusal("forge: archive refused — transaction rollback failed")\n',
            "    pass  # CONTROL DISABLED: rollback verification\n",
        )
        source = mutant.read_text(encoding="utf-8")
        rm_call = (
            '        removed = run_git(\n'
            '            repo, "rm", "--cached", "--force", "--ignore-unmatch", "--", relative\n'
            '        )\n'
            '        failed = removed.returncode != 0\n'
        )
        self.assertEqual(source.count(rm_call), 1)
        source = source.replace(
            rm_call,
            '        failed = True  # forced git rollback failure\n',
        )
        unlink = "        archive_path.unlink(missing_ok=True)\n"
        self.assertEqual(source.count(unlink), 1)
        source = source.replace(unlink, "        pass  # forced rollback residue\n")
        race = "    try:\n        if nul_paths(git_stdout(repo, \"diff\", \"--name-only\", \"-z\")):\n"
        self.assertEqual(source.count(race), 1)
        source = source.replace(
            race,
            "    try:\n        (repo / 'rollback-race.txt').write_text('race\\n', encoding='utf-8')\n        if nul_paths(git_stdout(repo, \"diff\", \"--name-only\", \"-z\")):\n",
        )
        mutant.write_text(source, encoding="utf-8")
        result = self.invoke(archiver=mutant)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, CONTAMINATION.encode())
        # The disabled verification lets failed rollback leave archive residue;
        # the intact control would replace this with rollback-failed refusal.
        self.assertTrue(self.archive_path.exists())

    def test_audit_invocation_control_is_killed_by_unknown_task_fixture(self) -> None:
        """A temp-copy mutant proves the audit call is behaviorally observed."""
        decision = next(record for record in self.records if record["type"] == "decision")
        decision["task"] = "task-99"
        self.write_journal()
        self.set_passing_post_close()
        # This mutant isolates the archive audit invocation. Disable the two
        # independent gated-validation checks that correctly reject the same
        # malformed journal, then observe that removing the audit permits it.

        mutant_root = self.root / "mutant-plugin"
        shutil.copytree(ROOT / "scripts", mutant_root / "scripts")
        mutant = mutant_root / "scripts" / "forge" / "archive-run.py"
        source = mutant.read_text(encoding="utf-8")
        needle = "    audit_fragment = run_audit(run_dir, dispense_targets, dispense_reason)\n"
        self.assertEqual(source.count(needle), 1)
        mutant.write_text(
            source.replace(
                needle,
                '    audit_fragment = "## Residual Risks\\n\\nNone recorded\\n\\n## Follow-ups\\n\\nNone recorded\\n"\n',
            ),
            encoding="utf-8",
        )
        source = mutant.read_text(encoding="utf-8")
        pre = "    if not is_passing_gated_payload(embedded_pre_close):\n        raise ArchiveRefusal(\"forge: archive refused — pre-close gated validation did not pass\")\n"
        supplied = "    if not is_passing_gated_payload(post_close):\n        raise ArchiveRefusal(\"forge: archive refused — post-close gated validation did not pass\")\n"
        fresh_pre = "    if not is_passing_gated_payload(fresh_pre_close) or embedded_pre_close != fresh_pre_close:\n        raise ArchiveRefusal(\n            \"forge: archive refused — pre-close gated validation is stale or does not match journal\"\n        )\n"
        fresh = "    if not is_passing_gated_payload(fresh_validation) or post_close != fresh_validation:\n        raise ArchiveRefusal(\n            \"forge: archive refused — post-close gated validation is stale or does not match journal\"\n        )\n"
        self.assertEqual(source.count(pre), 1)
        self.assertEqual(source.count(supplied), 1)
        self.assertEqual(source.count(fresh_pre), 1)
        self.assertEqual(source.count(fresh), 1)
        mutant.write_text(
            source.replace(pre, "    pass  # isolated audit mutant: pre-close check disabled\n")
            .replace(supplied, "    pass  # isolated audit mutant: supplied check disabled\n")
            .replace(fresh_pre, "    pass  # isolated audit mutant: pre-close freshness disabled\n")
            .replace(fresh, "    pass  # isolated audit mutant: fresh check disabled\n"),
            encoding="utf-8",
        )
        result = self.invoke(archiver=mutant)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertTrue(self.archive_path.is_file())

    def test_clean_preflight_mutant_is_killed(self) -> None:
        mutant = self.mutant_archiver(
            "mutant-clean-preflight",
            "    prove_clean(repo)\n",
            "    pass  # CONTROL DISABLED: clean preflight\n",
        )
        (self.repo / "unrelated.txt").write_text("unrelated\n", encoding="utf-8")
        # Isolate the preflight: disable the later transaction proofs too. The
        # mutant then escapes, proving the intact early control is observable.
        source = mutant.read_text(encoding="utf-8")
        for needle, replacement in (
            (
                '        if nul_paths(git_stdout(repo, "diff", "--name-only", "-z")):\n',
                '        if False:  # isolated preflight mutant: tracked proof disabled\n',
            ),
            (
                '        if nul_paths(git_stdout(repo, "diff", "--cached", "--name-only", "-z")):\n',
                '        if False:  # isolated preflight mutant: staged proof disabled\n',
            ),
            (
                '        if nul_paths(git_stdout(repo, "ls-files", "--others", "--exclude-standard", "-z")) != [\n            os.fsencode(relative)\n        ]:\n',
                '        if False:  # isolated preflight mutant: untracked proof disabled\n',
            ),
            (
                '        if staged != [os.fsencode(relative)] or unstaged or untracked:\n',
                '        if False:  # isolated preflight mutant: postproof disabled\n',
            ),
        ):
            self.assertEqual(source.count(needle), 1, needle)
            source = source.replace(needle, replacement)
        mutant.write_text(source, encoding="utf-8")
        result = self.invoke(archiver=mutant)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertTrue(self.archive_path.is_file())
        self.assertTrue((self.repo / "unrelated.txt").is_file())

    def test_archive_only_postproof_mutant_is_killed(self) -> None:
        mutant = self.mutant_archiver(
            "mutant-postproof",
            "        if staged != [os.fsencode(relative)] or unstaged or untracked:\n",
            "        if False:  # CONTROL DISABLED: archive-only postproof\n",
        )
        # Inject contamination immediately after staging, so it is observable
        # only by the final archive-only proof.
        source = mutant.read_text(encoding="utf-8")
        needle = (
            "        staged = nul_paths(git_stdout(repo, \"diff\", \"--cached\", \"--name-only\", \"-z\"))\n"
            "        unstaged = nul_paths(git_stdout(repo, \"diff\", \"--name-only\", \"-z\"))\n"
        )
        replacement = (
            "        (repo / 'late-unrelated.txt').write_text('late\\n', encoding='utf-8')\n"
            + needle
        )
        self.assertEqual(source.count(needle), 1)
        mutant.write_text(source.replace(needle, replacement), encoding="utf-8")
        result = self.invoke(archiver=mutant)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        # A correct test must reject the disabled control's contaminated success.
        self.assertIn("late-unrelated.txt", self.git("ls-files", "--others", "--exclude-standard").stdout)
        self.assertTrue(self.archive_path.is_file())

    def test_overwrite_guard_mutant_is_killed(self) -> None:
        # Commit a sentinel so the repository is clean: append-only history is
        # allowed to exist in HEAD, but must never be replaced. First prove the
        # real control refuses it without changing a byte.
        self.archive_path.parent.mkdir(parents=True)
        sentinel = b"immutable-existing-archive\n"
        self.archive_path.write_bytes(sentinel)
        self.git("add", self.archive_relative.as_posix())
        self.git("commit", "--quiet", "-m", "committed archive sentinel")
        baseline = self.invoke()
        self.assertEqual(baseline.returncode, 1)
        self.assertEqual(
            baseline.stderr,
            (
                "forge: archive refused — archive already exists: "
                f"{self.archive_relative.as_posix()}\n"
            ).encode(),
        )
        self.assertEqual(self.archive_path.read_bytes(), sentinel)

        # Disable the full append-only defense in an isolated copy: the early
        # existence guard, exclusive creation, and the transaction's new-file
        # proof. The mutant then overwrites the committed history path.
        mutant = self.mutant_archiver(
            "mutant-overwrite",
            "    if archive_path.exists() or archive_path.is_symlink():\n        raise ArchiveRefusal(f\"forge: archive refused — archive already exists: {relative}\")\n",
            "    pass  # CONTROL DISABLED: append-only preflight\n",
        )
        source = mutant.read_text(encoding="utf-8")
        needle = '            handle = archive_path.open("x", encoding="utf-8", newline="")\n'
        replacement = '            handle = archive_path.open("w", encoding="utf-8", newline="")\n'
        self.assertEqual(source.count(needle), 1)
        source = source.replace(needle, replacement)
        needle = '        if nul_paths(git_stdout(repo, "diff", "--name-only", "-z")):\n'
        replacement = '        if False:  # CONTROL DISABLED: archive must be a new path\n'
        self.assertEqual(source.count(needle), 1)
        source = source.replace(needle, replacement)
        needle = (
            '        if nul_paths(git_stdout(repo, "ls-files", "--others", '
            '"--exclude-standard", "-z")) != [\n'
            '            os.fsencode(relative)\n'
            '        ]:\n'
        )
        replacement = '        if False:  # CONTROL DISABLED: archive must start untracked\n'
        self.assertEqual(source.count(needle), 1)
        mutant.write_text(source.replace(needle, replacement), encoding="utf-8")
        result = self.invoke(archiver=mutant)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertNotEqual(self.archive_path.read_bytes(), sentinel)

    def test_closing_head_binding_mutant_is_killed(self) -> None:
        mutant = self.mutant_archiver(
            "mutant-closing-head",
            "    if closing_head != recorded_head:\n        raise ArchiveRefusal(\"forge: archive refused — closing HEAD does not match repository HEAD\")\n",
            "    pass  # CONTROL DISABLED: closing-HEAD binding\n",
        )
        result = self.invoke(archiver=mutant, closing_head="0" * 40)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertIn("Closing HEAD: " + "0" * 40, self.archive_path.read_text(encoding="utf-8"))

    def test_post_close_pass_binding_mutant_is_killed(self) -> None:
        mutant = self.mutant_archiver(
            "mutant-post-close",
            "    if not is_passing_gated_payload(post_close):\n        raise ArchiveRefusal(\"forge: archive refused — post-close gated validation did not pass\")\n",
            "    pass  # CONTROL DISABLED: passing post-close validation\n",
        )
        self.post_payload["ok"] = False
        self.post_payload["issues"] = ["gate failed"]
        self.post_close.write_text(json.dumps(self.post_payload), encoding="utf-8")
        source = mutant.read_text(encoding="utf-8")
        freshness = "    if not is_passing_gated_payload(fresh_validation) or post_close != fresh_validation:\n        raise ArchiveRefusal(\n            \"forge: archive refused — post-close gated validation is stale or does not match journal\"\n        )\n"
        self.assertEqual(source.count(freshness), 1)
        mutant.write_text(
            source.replace(
                freshness,
                "    pass  # CONTROL DISABLED: post-close freshness binding\n",
            ),
            encoding="utf-8",
        )
        result = self.invoke(archiver=mutant)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertIn('"ok": false', self.archive_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
