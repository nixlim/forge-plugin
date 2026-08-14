"""Behavioral and mutation-discriminating tests for advisory learning writes."""

from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
WRITER = ROOT / "scripts" / "forge" / "learn-proposals.py"
RUN_ID = "run-learning-01"
AGENT = "review-cheap-01"
EXECUTION = "execution-01"
PROMPT = (
    b"ROLE\r\n\nExact prompt bytes: \xcf\x80  \n"
    b"## Expected\nThis heading belongs to the prompt.\n"
    b"````\n## Provenance\nno-final-newline"
)
PRIOR_GOTCHAS = b"# Learned failure shapes\r\nprior \xcf\x80"
INPUT_HEAD_SENTINEL = "INPUT_HEAD_FROM_REPO"
ARCHIVE_PATH = f".forge/history/runs/{RUN_ID}.md"
FORBIDDEN_CONTROLS = {
    "promoted tasks": ".forge/evals/tasks/promoted.md",
    "result baseline": ".forge/evals/tasks/promoted.result",
    "rules": "rules/injected.md",
    "constitution": "rules/review-constitution.md",
    "project policy": "forge-project.md",
    "manifest": ".forge-manifest",
    "routing config": "system/codex/config.toml",
    "routing agent": "system/codex/agents/implementer.toml",
    "hooks": "system/codex/hooks.json",
    "gates": "scripts/forge/validate-gates.py",
    "execpolicy": ".codex/rules/forge.rules",
    "agents": "agents/review-final.md",
    "other control": "skills/commit/SKILL.md",
}
TRAVERSAL_ATTACKS = {
    "promoted tasks": "../tasks/promoted",
    "result baseline": "../tasks/promoted.result",
    "rules": "../../../rules/injected",
    "constitution": "../../../rules/review-constitution",
    "project policy": "../../../forge-project",
    "manifest": "../../../.forge-manifest",
    "routing config": "../../../system/codex/config.toml",
    "routing agent": "../../../system/codex/agents/implementer.toml",
    "hooks": "../../../system/codex/hooks.json",
    "gates": "../../../scripts/forge/validate-gates.py",
    "execpolicy": "../../../.codex/rules/forge.rules",
    "agents": "../../../agents/review-final",
    "other control": "../../../skills/commit/SKILL",
}


class LearnProposalsTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="forge-learn-proposals-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.counter = 0
        self.latest_input_head = ""

    def make_repo(self, name: str | None = None) -> Path:
        if name is None:
            self.counter += 1
            name = f"repo-{self.counter}"
        repo = self.base / name
        repo.mkdir()
        subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.email", "tests@example.invalid"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.name", "Forge Tests"], check=True
        )
        run_dir = repo / ".codex-orchestrator" / "runs" / RUN_ID
        prompt = run_dir / "agents" / AGENT / EXECUTION / "prompt.md"
        prompt.parent.mkdir(parents=True)
        prompt.write_bytes(PROMPT)
        records = [
            {"type": "run_started", "run_id": RUN_ID},
            {
                "type": "execution",
                "agent": AGENT,
                "execution": EXECUTION,
                "prompt": prompt.relative_to(run_dir).as_posix(),
                "role": "review",
                "task": "task-main",
            },
            {
                "type": "decision",
                "id": "decision-01",
                "task": "task-main",
                "finding": "The boundary defect escaped review.",
                "outcome": "claude_decision",
            },
            {
                "type": "verification",
                "id": "verification-01",
                "task": "task-main",
                "result": "failed",
                "observation": "The boundary defect was reproduced.",
            },
            {"type": "run_closed", "judgment": "passed"},
        ]
        (run_dir / "journal.jsonl").write_text(
            "".join(json.dumps(item, sort_keys=True) + "\n" for item in records),
            encoding="utf-8",
        )
        (repo / ".forge/evals/candidates").mkdir(parents=True)
        history = repo / ".forge/history"
        history.mkdir(parents=True)
        (history / "gotchas.md").write_bytes(PRIOR_GOTCHAS)
        archive = history / "runs" / f"{RUN_ID}.md"
        archive.parent.mkdir()
        provenance = {
            "decisions": [{"id": "decision-01", "task": "task-main"}],
            "executions": [
                {
                    "agent": AGENT,
                    "execution": EXECUTION,
                    "prompt": prompt.relative_to(run_dir).as_posix(),
                    "prompt_sha256": hashlib.sha256(PROMPT).hexdigest(),
                    "role": "review",
                    "task": "task-main",
                }
            ],
            "failed_or_inconclusive_verifications": [
                {
                    "criterion": None,
                    "id": "verification-01",
                    "observation": "The boundary defect was reproduced.",
                    "result": "failed",
                    "task": "task-main",
                }
            ],
        }
        archive.write_text(
            "\n".join(
                [
                    f"# Forge Run Archive: {RUN_ID}",
                    "",
                    "## Learning provenance",
                    "",
                    "<!-- BEGIN FORGE LEARNING PROVENANCE v1 -->",
                    "```json",
                    json.dumps(provenance, ensure_ascii=False, sort_keys=True, indent=2),
                    "```",
                    "<!-- END FORGE LEARNING PROVENANCE v1 -->",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        subprocess.run(
            ["git", "-C", str(repo), "add", ARCHIVE_PATH, ".forge/history/gotchas.md"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "commit", "--quiet", "-m", "fixture archive"],
            check=True,
        )
        self.latest_input_head = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        return repo

    def commit_archive_provenance(
        self,
        repo: Path,
        mutate: Callable[[dict[str, Any]], None],
        *,
        canonical: bool = True,
    ) -> None:
        archive = repo / ARCHIVE_PATH
        text = archive.read_text(encoding="utf-8")
        begin = "<!-- BEGIN FORGE LEARNING PROVENANCE v1 -->\n```json\n"
        end = "\n```\n<!-- END FORGE LEARNING PROVENANCE v1 -->"
        encoded = text.split(begin, 1)[1].split(end, 1)[0]
        provenance = json.loads(encoded)
        mutate(provenance)
        replacement = json.dumps(
            provenance,
            ensure_ascii=False,
            sort_keys=True,
            indent=2 if canonical else None,
            separators=None if canonical else (",", ":"),
        )
        archive.write_text(
            text.split(begin, 1)[0]
            + begin
            + replacement
            + end
            + text.split(end, 1)[1],
            encoding="utf-8",
        )
        subprocess.run(
            ["git", "-C", str(repo), "add", ARCHIVE_PATH], check=True
        )
        subprocess.run(
            ["git", "-C", str(repo), "commit", "--quiet", "-m", "mutate archive authority"],
            check=True,
        )
        self.latest_input_head = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def candidate(self, **changes: object) -> dict[str, object]:
        value: dict[str, object] = {
            "id": "journal-review-missed-boundary",
            "category": "review",
            "agent": AGENT,
            "expected_verdict": "BLOCK",
            "run_id": RUN_ID,
            "execution": EXECUTION,
            "scenario": "A boundary defect escaped the first review.",
            "expected": f"`{AGENT}` MUST return **BLOCK** and name the boundary defect.",
        }
        value.update(changes)
        return value

    def gotcha(self, **changes: object) -> dict[str, object]:
        value: dict[str, object] = {
            "run_id": RUN_ID,
            "agent": AGENT,
            "execution": EXECUTION,
            "entries": [
                {"type": "decision", "id": "decision-01"},
                {"type": "verification", "id": "verification-01"},
            ],
            "line": "Check empty and final-page boundaries before accepting pagination changes.",
        }
        value.update(changes)
        return value

    def payload(
        self,
        *,
        candidates: list[dict[str, object]] | None = None,
        gotchas: list[dict[str, object]] | None = None,
        **changes: object,
    ) -> dict[str, object]:
        value: dict[str, object] = {
            "schema_version": 1,
            "input_head": INPUT_HEAD_SENTINEL,
            "candidates": [self.candidate()] if candidates is None else candidates,
            "gotchas": [self.gotcha()] if gotchas is None else gotchas,
        }
        value.update(changes)
        return value

    def invoke(
        self,
        repo: Path,
        payload: dict[str, object],
        *,
        writer: Path = WRITER,
    ) -> subprocess.CompletedProcess[bytes]:
        self.counter += 1
        proposal = self.base / f"proposal-{self.counter}.json"
        payload = json.loads(json.dumps(payload))
        if payload.get("input_head") == INPUT_HEAD_SENTINEL:
            payload["input_head"] = self.latest_input_head
        proposal.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )
        return subprocess.run(
            [sys.executable, str(writer), "--repo", str(repo), "--proposal", str(proposal)],
            check=False,
            capture_output=True,
        )

    def snapshot(self, repo: Path) -> dict[str, tuple[str, bytes]]:
        result: dict[str, tuple[str, bytes]] = {}
        for path in sorted(repo.rglob("*")):
            relative = path.relative_to(repo).as_posix()
            if path.is_symlink():
                result[relative] = ("link", os.readlink(path).encode("utf-8"))
            elif path.is_file():
                result[relative] = ("file", path.read_bytes())
        return result

    def expected_candidate(self) -> bytes:
        return (
            b"---\n"
            b"id: journal-review-missed-boundary\n"
            b"category: review\n"
            b"agent: review-cheap-01\n"
            b"expected_verdict: BLOCK\n"
            b"---\n\n"
            b"## Scenario\n\n"
            b"A boundary defect escaped the first review.\n\n"
            b"## Input\n\n"
            b"`````\n"
            + PROMPT
            + b"\n`````\n\n## Expected\n\n"
            b"`review-cheap-01` MUST return **BLOCK** and name the boundary defect.\n\n"
            b"## Provenance\n\n"
            b"- run-id: `run-learning-01`\n"
            b"- agent: `review-cheap-01`\n"
            b"- execution-id: `execution-01`\n"
            + f"- archive: `{self.latest_input_head}:{ARCHIVE_PATH}`\n".encode("ascii")
        )

    def test_allowed_outputs_preserve_exact_prompt_form_and_prior_gotcha_bytes(self) -> None:
        repo = self.make_repo()
        result = self.invoke(repo, self.payload())
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        self.assertEqual(
            result.stdout,
            b".forge/evals/candidates/journal-review-missed-boundary.md\n"
            b".forge/history/gotchas.md\n",
        )
        self.assertEqual(result.stderr, b"")

        candidate = repo / ".forge/evals/candidates/journal-review-missed-boundary.md"
        self.assertEqual(candidate.read_bytes(), self.expected_candidate())
        input_section = candidate.read_bytes().split(b"## Input\n\n", 1)[1]
        fence, fenced_tail = input_section.split(b"\n", 1)
        input_bytes, after_fence = fenced_tail.split(b"\n" + fence + b"\n", 1)
        self.assertEqual(fence, b"`````")
        self.assertEqual(input_bytes, PROMPT)
        self.assertTrue(after_fence.startswith(b"\n## Expected\n"))
        self.assertFalse((repo / ".forge/evals/tasks").exists())
        self.assertEqual(list(repo.rglob("*.result")), [])

        gotcha_line = (
            b"- Check empty and final-page boundaries before accepting pagination changes. "
            b"[journal: run-id=run-learning-01; agent=review-cheap-01; "
            b"execution-id=execution-01; entries=decision:decision-01,"
            b"verification:verification-01] "
            + f"[archive: {self.latest_input_head}:{ARCHIVE_PATH}]\n".encode("ascii")
        )
        after = (repo / ".forge/history/gotchas.md").read_bytes()
        self.assertTrue(after.startswith(PRIOR_GOTCHAS))
        self.assertEqual(after, PRIOR_GOTCHAS + b"\n" + gotcha_line)
        self.assertEqual(after.count(gotcha_line), 1)

    def test_candidate_collision_refuses_before_any_append_or_overwrite(self) -> None:
        repo = self.make_repo()
        candidate = repo / ".forge/evals/candidates/journal-review-missed-boundary.md"
        candidate.write_bytes(b"EXISTING CANDIDATE\n")
        before = self.snapshot(repo)
        result = self.invoke(
            repo,
            self.payload(
                candidates=[
                    self.candidate(id="would-be-written-first"),
                    self.candidate(),
                ]
            ),
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"candidate-collision", result.stderr)
        self.assertEqual(self.snapshot(repo), before)

    def test_gotcha_only_append_adds_one_line_and_candidate_only_is_new(self) -> None:
        gotcha_repo = self.make_repo()
        shutil.rmtree(gotcha_repo / ".forge/evals")
        result = self.invoke(gotcha_repo, self.payload(candidates=[]))
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        self.assertEqual(result.stdout, b".forge/history/gotchas.md\n")
        appended = (gotcha_repo / ".forge/history/gotchas.md").read_bytes()
        self.assertTrue(appended.startswith(PRIOR_GOTCHAS))
        self.assertEqual(appended[len(PRIOR_GOTCHAS) :].count(b"\n"), 2)
        self.assertFalse((gotcha_repo / ".forge/evals").exists())

        candidate_repo = self.make_repo()
        shutil.rmtree(candidate_repo / ".forge/history")
        result = self.invoke(candidate_repo, self.payload(gotchas=[]))
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        self.assertEqual(
            result.stdout,
            b".forge/evals/candidates/journal-review-missed-boundary.md\n",
        )
        self.assertFalse((candidate_repo / ".forge/history").exists())

    def test_forbidden_control_path_traversal_matrix_is_unwritable(self) -> None:
        repo = self.make_repo()
        for relative in FORBIDDEN_CONTROLS.values():
            path = repo / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"CONTROL:{relative}\n".encode("utf-8"))
        before = self.snapshot(repo)
        attacks = dict(TRAVERSAL_ATTACKS)
        attacks.update(
            {
                "absolute": (Path(os.sep) / "rules/review-constitution").as_posix(),
                "windows separator": "..\\..\\rules\\review-constitution",
                "result suffix": "promoted.result",
                "newline": "candidate\n../../../rules/injected",
                "nul": "candidate\x00../../../rules/injected",
                "unicode slash": "candidate\u2215..\u2215rules",
            }
        )
        for surface, attack in attacks.items():
            with self.subTest(surface=surface):
                result = self.invoke(
                    repo,
                    self.payload(candidates=[self.candidate(id=attack)]),
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn(b"invalid-candidate-id", result.stderr)
                self.assertEqual(self.snapshot(repo), before)

        for surface, destination in FORBIDDEN_CONTROLS.items():
            with self.subTest(surface=surface, vector="configurable destination"):
                candidate = dict(self.candidate(), output_path=destination)
                result = self.invoke(repo, self.payload(candidates=[candidate]))
                self.assertEqual(result.returncode, 2)
                self.assertEqual(self.snapshot(repo), before)

    def test_source_traversal_and_unearned_provenance_are_refused_without_writes(self) -> None:
        cases = [
            ("run traversal", self.payload(candidates=[self.candidate(run_id="../run")])),
            (
                "absolute run",
                self.payload(
                    candidates=[
                        self.candidate(run_id=str(Path(os.sep) / "tmp" / "run"))
                    ]
                ),
            ),
            ("agent mismatch", self.payload(candidates=[self.candidate(agent="other-agent")])),
            (
                "execution mismatch",
                self.payload(candidates=[self.candidate(execution="execution-02")]),
            ),
            (
                "gotcha newline",
                self.payload(candidates=[], gotchas=[self.gotcha(line="shape\nINJECTED")]),
            ),
        ]
        for name, payload in cases:
            with self.subTest(case=name):
                repo = self.make_repo()
                before = self.snapshot(repo)
                result = self.invoke(repo, payload)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(self.snapshot(repo), before)

        for prompt_path in (
            "../../../../forge-project.md",
            str(Path(os.sep) / "tmp" / "prompt.md"),
        ):
            with self.subTest(prompt=prompt_path):
                repo = self.make_repo()
                journal = repo / ".codex-orchestrator/runs" / RUN_ID / "journal.jsonl"
                records = [json.loads(line) for line in journal.read_text().splitlines()]
                records[1]["prompt"] = prompt_path
                journal.write_text(
                    "".join(json.dumps(item) + "\n" for item in records), encoding="utf-8"
                )
                before = self.snapshot(repo)
                result = self.invoke(repo, self.payload())
                self.assertEqual(result.returncode, 2)
                self.assertIn(b"invalid-prompt-path", result.stderr)
                self.assertEqual(self.snapshot(repo), before)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support required")
    def test_symlink_outputs_and_prompt_escape_are_refused(self) -> None:
        repo = self.make_repo()
        candidate_dir = repo / ".forge/evals/candidates"
        candidate_dir.rmdir()
        os.symlink("../tasks", candidate_dir)
        before = self.snapshot(repo)
        result = self.invoke(repo, self.payload())
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"unsafe-output-path", result.stderr)
        self.assertEqual(self.snapshot(repo), before)

        repo = self.make_repo()
        gotchas = repo / ".forge/history/gotchas.md"
        gotchas.unlink()
        policy = repo / "forge-project.md"
        policy.write_bytes(b"CONTROL POLICY\n")
        os.symlink(os.path.relpath(policy, gotchas.parent), gotchas)
        before = self.snapshot(repo)
        result = self.invoke(repo, self.payload(candidates=[]))
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"unsafe-output-path", result.stderr)
        self.assertEqual(self.snapshot(repo), before)

        repo = self.make_repo()
        run_dir = repo / ".codex-orchestrator/runs" / RUN_ID
        prompt = run_dir / "agents" / AGENT / EXECUTION / "prompt.md"
        prompt.unlink()
        outside = repo / "forge-project.md"
        outside.write_bytes(b"SECRET CONTROL INPUT\n")
        os.symlink(os.path.relpath(outside, prompt.parent), prompt)
        before = self.snapshot(repo)
        result = self.invoke(repo, self.payload())
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"invalid-prompt-path", result.stderr)
        self.assertEqual(self.snapshot(repo), before)

        repo = self.make_repo()
        run_dir = repo / ".codex-orchestrator/runs" / RUN_ID
        prompt = run_dir / "agents" / AGENT / EXECUTION / "prompt.md"
        in_run_target = prompt.with_name("recorded-prompt.md")
        prompt.rename(in_run_target)
        os.symlink(in_run_target.name, prompt)
        before = self.snapshot(repo)
        result = self.invoke(repo, self.payload())
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"invalid-prompt-path", result.stderr)
        self.assertEqual(self.snapshot(repo), before)

    @unittest.skipUnless(hasattr(os, "link"), "hard-link support required")
    def test_hardlinked_recorded_prompt_is_refused_and_kills_disabled_guard(self) -> None:
        repo = self.make_repo()
        prompt = repo / ".codex-orchestrator/runs" / RUN_ID / "agents" / AGENT / EXECUTION / "prompt.md"
        outside = repo / "forge-project.md"
        outside.write_bytes(PROMPT)
        prompt.unlink()
        os.link(outside, prompt)
        before = self.snapshot(repo)

        result = self.invoke(repo, self.payload())

        self.assertEqual(result.returncode, 2)
        self.assertIn(b"invalid-prompt-path", result.stderr)
        self.assertEqual(self.snapshot(repo), before)

        mutant = self.mutated_writer(
            [
                (
                    "        metadata = resolved.lstat()\n"
                    "    except (OSError, RuntimeError, ValueError) as exc:\n"
                    '        raise ProposalRefusal("invalid-prompt-path") from exc\n'
                    "    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:",
                    "        metadata = resolved.lstat()\n"
                    "    except (OSError, RuntimeError, ValueError) as exc:\n"
                    '        raise ProposalRefusal("invalid-prompt-path") from exc\n'
                    "    if not stat.S_ISREG(metadata.st_mode):",
                ),
                (
                    "            if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:\n"
                    '                refuse("invalid-prompt-path")',
                    "            if not stat.S_ISREG(opened.st_mode):\n"
                    '                refuse("invalid-prompt-path")',
                ),
            ],
            "prompt-hard-link-guard-disabled.py",
        )
        mutated = self.invoke(repo, self.payload(), writer=mutant)
        self.assertEqual(mutated.returncode, 0, mutated.stderr.decode(errors="replace"))
        with self.assertRaises(AssertionError):
            self.assertEqual(self.snapshot(repo), before)

    @unittest.skipUnless(hasattr(os, "link"), "hard-link support required")
    def test_hardlinked_gotchas_cannot_mutate_any_control(self) -> None:
        for surface, destination in FORBIDDEN_CONTROLS.items():
            with self.subTest(surface=surface):
                repo = self.make_repo()
                control = repo / destination
                control.parent.mkdir(parents=True, exist_ok=True)
                control.write_bytes(f"CONTROL:{destination}".encode("utf-8"))
                gotchas = repo / ".forge/history/gotchas.md"
                gotchas.unlink()
                os.link(control, gotchas)
                before = self.snapshot(repo)

                result = self.invoke(repo, self.payload(candidates=[]))

                self.assertEqual(result.returncode, 2)
                self.assertIn(b"unsafe-output-path", result.stderr)
                self.assertEqual(self.snapshot(repo), before)

        repo = self.make_repo()
        control = repo / "forge-project.md"
        original = PRIOR_GOTCHAS + b"\nMUTATION ORACLE CONTROL"
        control.write_bytes(original)
        gotchas = repo / ".forge/history/gotchas.md"
        gotchas.unlink()
        os.link(control, gotchas)
        mutant = self.mutated_writer(
            [
                (
                    "    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:\n"
                    '        refuse("unsafe-output-path")',
                    "    if not stat.S_ISREG(metadata.st_mode):\n"
                    '        refuse("unsafe-output-path")',
                ),
                (
                    "            if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:\n"
                    '                refuse("unsafe-output-path")',
                    "            if not stat.S_ISREG(opened.st_mode):\n"
                    '                refuse("unsafe-output-path")',
                ),
                (
                    "        or opened.st_nlink != 1",
                    "        or False",
                ),
            ],
            "hard-link-guard-disabled.py",
        )

        result = self.invoke(repo, self.payload(candidates=[]), writer=mutant)

        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        with self.assertRaises(AssertionError):
            self.assertEqual(control.read_bytes(), original)

    def test_gotcha_entries_require_unique_same_task_journal_evidence(self) -> None:
        invalid_payloads = [
            self.payload(candidates=[], gotchas=[self.gotcha(entries=[])]),
            self.payload(
                candidates=[],
                gotchas=[
                    self.gotcha(
                        entries=[
                            {"type": "decision", "id": "decision-01"},
                            {"type": "decision", "id": "decision-01"},
                        ]
                    )
                ],
            ),
            self.payload(
                candidates=[],
                gotchas=[
                    self.gotcha(
                        entries=[{"type": "decision", "id": "missing-decision"}]
                    )
                ],
            ),
        ]
        for index, payload in enumerate(invalid_payloads):
            with self.subTest(case="proposal entry", index=index):
                repo = self.make_repo()
                before = self.snapshot(repo)
                result = self.invoke(repo, payload)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(self.snapshot(repo), before)

        for case in ("wrong task", "duplicate journal entry", "missing execution task"):
            with self.subTest(case=case):
                repo = self.make_repo()
                journal = repo / ".codex-orchestrator/runs" / RUN_ID / "journal.jsonl"
                records = [json.loads(line) for line in journal.read_text().splitlines()]
                if case == "wrong task":
                    records[2]["task"] = "task-other"
                elif case == "duplicate journal entry":
                    records.append(dict(records[2]))
                else:
                    records[1].pop("task")
                journal.write_text(
                    "".join(json.dumps(item) + "\n" for item in records),
                    encoding="utf-8",
                )
                before = self.snapshot(repo)
                result = self.invoke(repo, self.payload(candidates=[]))
                self.assertEqual(result.returncode, 2)
                self.assertEqual(self.snapshot(repo), before)

        repo = self.make_repo()
        journal = repo / ".codex-orchestrator/runs" / RUN_ID / "journal.jsonl"
        records = [json.loads(line) for line in journal.read_text().splitlines()]
        records[2]["task"] = "task-other"
        journal.write_text(
            "".join(json.dumps(item) + "\n" for item in records), encoding="utf-8"
        )
        before = self.snapshot(repo)
        mutant = self.mutated_writer(
            [
                (
                    '        entries = validate_gotcha_entries(records, record, gotcha["entries"])',
                    '        entries = tuple((item["type"], item["id"]) for item in gotcha["entries"])',
                )
            ],
            "gotcha-entry-validation-disabled.py",
        )
        result = self.invoke(repo, self.payload(candidates=[]), writer=mutant)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        with self.assertRaises(AssertionError):
            self.assertEqual(self.snapshot(repo), before)

    def test_closed_failure_provenance_controls_are_semantic_and_discriminating(self) -> None:
        def read_records(repo: Path) -> tuple[Path, list[dict[str, Any]]]:
            journal = repo / ".codex-orchestrator/runs" / RUN_ID / "journal.jsonl"
            return journal, [json.loads(line) for line in journal.read_text().splitlines()]

        def write_records(journal: Path, records: list[dict[str, Any]]) -> None:
            journal.write_text(
                "".join(json.dumps(item, sort_keys=True) + "\n" for item in records),
                encoding="utf-8",
            )

        repo = self.make_repo()
        journal, records = read_records(repo)
        write_records(journal, records[:-1])
        before = self.snapshot(repo)
        result = self.invoke(repo, self.payload(gotchas=[]))
        self.assertEqual(2, result.returncode)
        self.assertIn(b"run-not-closed", result.stderr)
        self.assertEqual(before, self.snapshot(repo))
        mutant = self.mutated_writer(
            [("    require_closed_run(records)", "    pass")],
            "closed-run-check-disabled.py",
        )
        mutated = self.invoke(repo, self.payload(gotchas=[]), writer=mutant)
        self.assertEqual(0, mutated.returncode, mutated.stderr.decode(errors="replace"))
        with self.assertRaises(AssertionError):
            self.assertEqual(before, self.snapshot(repo))

        repo = self.make_repo()
        journal, records = read_records(repo)
        records[3]["result"] = "passed"
        write_records(journal, records)
        self.commit_archive_provenance(
            repo,
            lambda provenance: provenance[
                "failed_or_inconclusive_verifications"
            ].clear(),
        )
        before = self.snapshot(repo)
        result = self.invoke(repo, self.payload(gotchas=[]))
        self.assertEqual(2, result.returncode)
        self.assertIn(b"archive-failure-unavailable", result.stderr)
        self.assertEqual(before, self.snapshot(repo))
        failure_guard = (
            '    if not failures:\n'
            '        refuse("archive-failure-unavailable")'
        )
        mutant = self.mutated_writer(
            [
                (
                    failure_guard,
                    '    if False:\n        refuse("archive-failure-unavailable")',
                )
            ],
            "failure-evidence-check-disabled.py",
        )
        mutated = self.invoke(repo, self.payload(gotchas=[]), writer=mutant)
        self.assertEqual(0, mutated.returncode, mutated.stderr.decode(errors="replace"))
        with self.assertRaises(AssertionError):
            self.assertEqual(before, self.snapshot(repo))

        repo = self.make_repo()
        before = self.snapshot(repo)
        decision_only = self.gotcha(
            entries=[{"type": "decision", "id": "decision-01"}]
        )
        result = self.invoke(
            repo,
            self.payload(candidates=[], gotchas=[decision_only]),
        )
        self.assertEqual(2, result.returncode)
        self.assertIn(b"unearned-gotcha", result.stderr)
        self.assertEqual(before, self.snapshot(repo))
        guard = (
            '        if not any(entry_type == "verification" for entry_type, _identity in entries):\n'
            '            refuse("unearned-gotcha")'
        )
        mutant = self.mutated_writer(
            [(guard, '        if False:\n            refuse("unearned-gotcha")')],
            "earned-citation-check-disabled.py",
        )
        mutated = self.invoke(
            repo,
            self.payload(candidates=[], gotchas=[decision_only]),
            writer=mutant,
        )
        self.assertEqual(0, mutated.returncode, mutated.stderr.decode(errors="replace"))
        with self.assertRaises(AssertionError):
            self.assertEqual(before, self.snapshot(repo))

    def test_exact_schema_and_newline_injection_fail_closed(self) -> None:
        invalid = [
            {
                key: value
                for key, value in self.payload().items()
                if key != "input_head"
            },
            self.payload(input_head=True),
            self.payload(input_head="0" * 39),
            self.payload(input_head="0" * 40),
            self.payload(schema_version=True),
            self.payload(schema_version=1.0),
            self.payload(output_path="rules/review-constitution.md"),
            self.payload(candidates=[], gotchas=[]),
            self.payload(
                candidates=[dict(self.candidate(), output=".forge/evals/tasks/x.md")]
            ),
            self.payload(
                candidates=[dict(self.candidate(), path="rules/review-constitution.md")]
            ),
            self.payload(
                candidates=[dict(self.candidate(), baseline="tasks/x.result")]
            ),
            self.payload(candidates=[self.candidate(expected_verdict="ALLOW")]),
            self.payload(candidates=[self.candidate(expected_verdict="FLAG")]),
            self.payload(candidates=[self.candidate(), self.candidate()]),
            self.payload(candidates=[], gotchas=[self.gotcha(), self.gotcha()]),
            self.payload(
                candidates=[],
                gotchas=[self.gotcha(line="shape\u2028INJECTED")],
            ),
            self.payload(
                candidates=[],
                gotchas=[self.gotcha(entries=[{"type": "task", "id": "task-main"}])],
            ),
            self.payload(
                candidates=[],
                gotchas=[
                    self.gotcha(
                        entries=[
                            {
                                "type": "decision",
                                "id": "decision-01",
                                "output": "rules/injected.md",
                            }
                        ]
                    )
                ],
            ),
        ]
        for index, payload in enumerate(invalid):
            with self.subTest(index=index):
                repo = self.make_repo()
                before = self.snapshot(repo)
                result = self.invoke(repo, payload)
                self.assertEqual(result.returncode, 2)
            self.assertEqual(self.snapshot(repo), before)

        repo = self.make_repo()
        proposal = self.base / "duplicate-member-proposal.json"
        proposal.write_bytes(
            b'{"schema_version":1,"schema_version":1,"candidates":[],"gotchas":[]}'
        )
        before = self.snapshot(repo)
        result = subprocess.run(
            [
                sys.executable,
                str(WRITER),
                "--repo",
                str(repo),
                "--proposal",
                str(proposal),
            ],
            check=False,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"invalid-proposal", result.stderr)
        self.assertEqual(self.snapshot(repo), before)

    def test_flag_requires_recorded_monitoring_role_and_kills_disabled_guard(self) -> None:
        repo = self.make_repo()
        payload = self.payload(
            candidates=[self.candidate(expected_verdict="FLAG")], gotchas=[]
        )
        before = self.snapshot(repo)

        result = self.invoke(repo, payload)

        self.assertEqual(result.returncode, 2)
        self.assertIn(b"invalid-verdict", result.stderr)
        self.assertEqual(self.snapshot(repo), before)

        guard = (
            '        if candidate["expected_verdict"] == "FLAG" and '
            'record.get("role") != "monitoring":\n'
            '            refuse("invalid-verdict")'
        )
        mutant = self.mutated_writer(
            [(guard, '        if False:\n            refuse("invalid-verdict")')],
            "flag-role-guard-disabled.py",
        )
        mutated = self.invoke(repo, payload, writer=mutant)
        self.assertEqual(mutated.returncode, 0, mutated.stderr.decode(errors="replace"))
        with self.assertRaises(AssertionError):
            self.assertEqual(self.snapshot(repo), before)

        tampered_repo = self.make_repo()
        journal = (
            tampered_repo
            / ".codex-orchestrator"
            / "runs"
            / RUN_ID
            / "journal.jsonl"
        )
        records = [json.loads(line) for line in journal.read_text().splitlines()]
        records[1]["role"] = "monitoring"
        journal.write_text(
            "".join(json.dumps(item, sort_keys=True) + "\n" for item in records),
            encoding="utf-8",
        )
        tampered_before = self.snapshot(tampered_repo)
        tampered = self.invoke(tampered_repo, payload)
        self.assertEqual(tampered.returncode, 2)
        self.assertIn(b"archive-journal-mismatch", tampered.stderr)
        self.assertEqual(self.snapshot(tampered_repo), tampered_before)
        role_binding_mutant = self.mutated_writer(
            [(" or execution.get(\"role\") != role", "")],
            "archive-role-binding-disabled.py",
        )
        bypassed = self.invoke(tampered_repo, payload, writer=role_binding_mutant)
        self.assertEqual(bypassed.returncode, 0, bypassed.stderr.decode(errors="replace"))
        with self.assertRaises(AssertionError):
            self.assertEqual(self.snapshot(tampered_repo), tampered_before)

        monitoring_repo = self.make_repo()
        journal = (
            monitoring_repo
            / ".codex-orchestrator"
            / "runs"
            / RUN_ID
            / "journal.jsonl"
        )
        records = [json.loads(line) for line in journal.read_text().splitlines()]
        records[1]["role"] = "monitoring"
        journal.write_text(
            "".join(json.dumps(item, sort_keys=True) + "\n" for item in records),
            encoding="utf-8",
        )
        self.commit_archive_provenance(
            monitoring_repo,
            lambda provenance: provenance["executions"][0].update(role="monitoring"),
        )
        restored = self.invoke(monitoring_repo, payload)
        self.assertEqual(restored.returncode, 0, restored.stderr.decode(errors="replace"))

    def test_only_fixed_git_read_process_and_no_configurable_output_capability(self) -> None:
        tree = ast.parse(WRITER.read_text(encoding="utf-8"))
        imported: set[str] = set()
        forbidden_calls: list[str] = []
        subprocess_calls: list[ast.Call] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", 1)[0])
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in {"system", "popen"} or node.func.attr.startswith(
                    ("exec", "spawn")
                ):
                    forbidden_calls.append(node.func.attr)
                if (
                    isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "subprocess"
                    and node.func.attr == "run"
                ):
                    subprocess_calls.append(node)
        self.assertIn("subprocess", imported)
        self.assertEqual(forbidden_calls, [])
        self.assertEqual(len(subprocess_calls), 1)
        self.assertEqual(
            ast.unparse(subprocess_calls[0].args[0]),
            "['git', '-C', os.fspath(repo), *arguments]",
        )

        repo = self.make_repo()
        proposal = self.base / "cli-capability-proposal.json"
        payload = self.payload(input_head=self.latest_input_head)
        proposal.write_text(json.dumps(payload), encoding="utf-8")
        before = self.snapshot(repo)
        result = subprocess.run(
            [
                sys.executable,
                str(WRITER),
                "--repo",
                str(repo),
                "--proposal",
                str(proposal),
                "--output",
                str(repo / "rules/forbidden.md"),
            ],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.snapshot(repo), before)

    def test_committed_head_candidate_and_gotcha_prefix_controls_are_discriminating(self) -> None:
        repo = self.make_repo()
        stale_head = self.latest_input_head
        marker = repo / "head-advanced.txt"
        marker.write_text("later committed authority\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", marker.name], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "commit", "--quiet", "-m", "advance head"],
            check=True,
        )
        before = self.snapshot(repo)
        stale_payload = self.payload(input_head=stale_head, gotchas=[])
        result = self.invoke(repo, stale_payload)
        self.assertEqual(2, result.returncode)
        self.assertIn(b"input-head-stale", result.stderr)
        self.assertEqual(before, self.snapshot(repo))
        head_guard = (
            '    if current != input_head.encode("ascii") + b"\\n":\n'
            '        refuse("input-head-stale")'
        )
        mutant = self.mutated_writer(
            [(head_guard, '    if False:\n        refuse("input-head-stale")')],
            "current-head-check-disabled.py",
        )
        bypassed = self.invoke(repo, stale_payload, writer=mutant)
        self.assertEqual(0, bypassed.returncode, bypassed.stderr.decode(errors="replace"))
        with self.assertRaises(AssertionError):
            self.assertEqual(before, self.snapshot(repo))

        repo = self.make_repo()
        candidate = repo / ".forge/evals/candidates/journal-review-missed-boundary.md"
        candidate.write_bytes(b"COMMITTED CANDIDATE\n")
        subprocess.run(
            ["git", "-C", str(repo), "add", candidate.relative_to(repo).as_posix()],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "commit", "--quiet", "-m", "track candidate"],
            check=True,
        )
        self.latest_input_head = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        candidate.unlink()
        before = self.snapshot(repo)
        result = self.invoke(repo, self.payload(gotchas=[]))
        self.assertEqual(2, result.returncode)
        self.assertIn(b"candidate-collision", result.stderr)
        self.assertEqual(before, self.snapshot(repo))
        committed_candidate_guard = (
            '        if committed_entry(repo, input_head, candidate_path) is not None:\n'
            '            refuse("candidate-collision")'
        )
        mutant = self.mutated_writer(
            [
                (
                    committed_candidate_guard,
                    '        if False:\n            refuse("candidate-collision")',
                )
            ],
            "committed-candidate-check-disabled.py",
        )
        bypassed = self.invoke(repo, self.payload(gotchas=[]), writer=mutant)
        self.assertEqual(0, bypassed.returncode, bypassed.stderr.decode(errors="replace"))
        with self.assertRaises(AssertionError):
            self.assertEqual(before, self.snapshot(repo))

        repo = self.make_repo()
        gotchas = repo / ".forge/history/gotchas.md"
        gotchas.write_bytes(b"TRUNCATED COMMITTED PREFIX")
        before = self.snapshot(repo)
        result = self.invoke(repo, self.payload(candidates=[]))
        self.assertEqual(2, result.returncode)
        self.assertIn(b"gotcha-prefix-mismatch", result.stderr)
        self.assertEqual(before, self.snapshot(repo))
        prefix_guard = (
            '    if committed is not None and not current.startswith(committed):\n'
            '        refuse("gotcha-prefix-mismatch")'
        )
        mutant = self.mutated_writer(
            [
                (prefix_guard, '    if False:\n        refuse("gotcha-prefix-mismatch")'),
                (
                    "        if committed is not None and not prior.startswith(committed):\n"
                    '            refuse("gotcha-prefix-mismatch")',
                    '        if False:\n            refuse("gotcha-prefix-mismatch")',
                ),
            ],
            "committed-gotcha-prefix-disabled.py",
        )
        bypassed = self.invoke(repo, self.payload(candidates=[]), writer=mutant)
        self.assertEqual(0, bypassed.returncode, bypassed.stderr.decode(errors="replace"))
        with self.assertRaises(AssertionError):
            self.assertEqual(before, self.snapshot(repo))

    def mutated_writer(self, replacements: list[tuple[str, str]], name: str) -> Path:
        source = WRITER.read_text(encoding="utf-8")
        for before, after in replacements:
            self.assertEqual(source.count(before), 1, before)
            source = source.replace(before, after, 1)
        target = self.base / name
        target.write_text(source, encoding="utf-8")
        return target

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support required")
    def test_ancestor_swap_after_validation_is_refused_by_opened_identity(self) -> None:
        repo = self.make_repo()
        outside = self.base / "outside-history"
        outside.mkdir()
        outside_gotchas = outside / "gotchas.md"
        outside_gotchas.write_bytes(PRIOR_GOTCHAS)
        before = self.snapshot(repo)
        outside_before = outside_gotchas.read_bytes()

        open_call = "            descriptor = os.open(path, open_flags, 0o666)"
        raced_open = (
            '            if path.name == "gotchas.md":\n'
            '                parked = path.parent.with_name("history.race-parked")\n'
            "                path.parent.rename(parked)\n"
            f"                os.symlink({os.fspath(outside)!r}, path.parent)\n"
            "                try:\n"
            "                    descriptor = os.open(path, open_flags, 0o666)\n"
            "                finally:\n"
            "                    path.parent.unlink()\n"
            "                    parked.rename(path.parent)\n"
            "            else:\n"
            "                descriptor = os.open(path, open_flags, 0o666)"
        )
        race_writer = self.mutated_writer(
            [(open_call, raced_open)], "ancestor-swap.py"
        )

        result = self.invoke(repo, self.payload(candidates=[]), writer=race_writer)

        self.assertEqual(result.returncode, 2)
        self.assertIn(b"unsafe-output-path", result.stderr)
        self.assertEqual(self.snapshot(repo), before)
        self.assertEqual(outside_gotchas.read_bytes(), outside_before)

        identity_guard = (
            "        or opened.st_nlink != 1\n"
            "        or (opened.st_dev, opened.st_ino) "
            "!= (intended.st_dev, intended.st_ino)"
        )
        identity_disabled = self.mutated_writer(
            [
                (open_call, raced_open),
                (
                    identity_guard,
                    "        or opened.st_nlink != 1\n        or False",
                ),
            ],
            "ancestor-swap-identity-disabled.py",
        )
        bypassed = self.invoke(
            repo, self.payload(candidates=[]), writer=identity_disabled
        )
        self.assertEqual(
            bypassed.returncode, 0, bypassed.stderr.decode(errors="replace")
        )
        self.assertEqual(self.snapshot(repo), before)
        self.assertNotEqual(outside_gotchas.read_bytes(), outside_before)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support required")
    def test_new_file_ancestor_swap_cannot_create_outside(self) -> None:
        repo = self.make_repo()
        candidate_dir = repo / ".forge/evals/candidates"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        outside = self.base / "outside-candidates"
        outside.mkdir()
        candidate_name = "journal-review-missed-boundary.md"
        outside_candidate = outside / candidate_name
        before = self.snapshot(repo)

        parent_validation = (
            "        validate_opened_directory(repo, path.parent, parent_descriptor)"
        )
        raced_parent = (
            parent_validation
            + "\n        raced_parent = False\n"
            + f'        if must_be_new and path.name == "{candidate_name}":\n'
            + '            parked_parent = path.parent.with_name("candidates.race-parked")\n'
            + "            path.parent.rename(parked_parent)\n"
            + f"            os.symlink({os.fspath(outside)!r}, path.parent)\n"
            + "            raced_parent = True"
        )
        output_validation = "        validate_opened_output(repo, path, descriptor)"
        raced_validation = (
            "        try:\n"
            "            validate_opened_output(repo, path, descriptor)\n"
            "        finally:\n"
            "            if raced_parent:\n"
            "                path.parent.unlink()\n"
            "                parked_parent.rename(path.parent)"
        )
        race_writer = self.mutated_writer(
            [
                (parent_validation, raced_parent),
                (output_validation, raced_validation),
            ],
            "new-file-ancestor-swap.py",
        )

        result = self.invoke(repo, self.payload(gotchas=[]), writer=race_writer)

        self.assertEqual(2, result.returncode)
        self.assertIn(b"unsafe-output-path", result.stderr)
        self.assertEqual(before, self.snapshot(repo))
        self.assertFalse(outside_candidate.exists())

        relative_open = (
            "            descriptor = os.open(\n"
            "                path.name,\n"
            "                open_flags,\n"
            "                0o666,\n"
            "                dir_fd=parent_descriptor,\n"
            "            )"
        )
        unsafe_open = "            descriptor = os.open(path, open_flags, 0o666)"
        unsafe_writer = self.mutated_writer(
            [
                (parent_validation, raced_parent),
                (output_validation, raced_validation),
                (relative_open, unsafe_open),
            ],
            "new-file-dirfd-disabled.py",
        )
        bypassed = self.invoke(repo, self.payload(gotchas=[]), writer=unsafe_writer)
        self.assertEqual(2, bypassed.returncode)
        self.assertIn(b"unsafe-output-path", bypassed.stderr)
        self.assertEqual(before, self.snapshot(repo))
        self.assertTrue(outside_candidate.is_file())

    def assert_transaction_intact(self, repo: Path) -> None:
        self.assertEqual(list((repo / ".forge/evals/candidates").glob("*.md")), [])
        gotchas = repo / ".forge/history/gotchas.md"
        self.assertTrue(gotchas.is_file())
        self.assertEqual(gotchas.read_bytes(), PRIOR_GOTCHAS)

    def assert_only_gotcha_lock_artifact(self, repo: Path) -> None:
        forge = repo / ".forge"
        if not forge.exists():
            return
        self.assertEqual(
            {
                path.relative_to(forge).as_posix()
                for path in forge.rglob("*")
            },
            {"tmp", "tmp/learn-gotchas.lock"},
        )
        self.assertTrue((forge / "tmp").is_dir())
        self.assertTrue((forge / "tmp/learn-gotchas.lock").is_file())

    def test_late_append_failure_rolls_back_every_candidate_and_partial_gotcha(self) -> None:
        payload = self.payload(
            candidates=[
                self.candidate(id="rollback-candidate-one"),
                self.candidate(id="rollback-candidate-two"),
            ]
        )
        injected_failure = (
            "            output.write(payload)",
            "            output.write(payload[:7])\n"
            "            output.flush()\n"
            '            raise OSError("simulated later write failure")',
        )

        repo = self.make_repo()
        failure_writer = self.mutated_writer([injected_failure], "late-write-failure.py")
        result = self.invoke(repo, payload, writer=failure_writer)
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"write-failed", result.stderr)
        self.assert_transaction_intact(repo)

        repo = self.make_repo()
        interrupt_writer = self.mutated_writer(
            [
                (
                    "            output.write(payload)",
                    "            output.write(payload[:7])\n"
                    "            output.flush()\n"
                    '            raise KeyboardInterrupt("simulated interrupt")',
                )
            ],
            "late-write-interrupt.py",
        )
        result = self.invoke(repo, payload, writer=interrupt_writer)
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"execution-failed", result.stderr)
        self.assert_transaction_intact(repo)

        repo = self.make_repo()
        subprocess.run(
            ["git", "-C", str(repo), "rm", "--quiet", ".forge/history/gotchas.md"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "commit", "--quiet", "-m", "remove prior gotchas"],
            check=True,
        )
        self.latest_input_head = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        shutil.rmtree(repo / ".forge")
        result = self.invoke(repo, payload, writer=failure_writer)
        self.assertEqual(result.returncode, 2)
        self.assert_only_gotcha_lock_artifact(repo)

        repo = self.make_repo()
        candidate_rollback_disabled = self.mutated_writer(
            [
                injected_failure,
                (
                    "        for target in reversed(created_candidates):",
                    "        for target in ():",
                ),
            ],
            "candidate-rollback-disabled.py",
        )
        result = self.invoke(repo, payload, writer=candidate_rollback_disabled)
        self.assertEqual(result.returncode, 2)
        with self.assertRaises(AssertionError):
            self.assert_transaction_intact(repo)

        repo = self.make_repo()
        subprocess.run(
            ["git", "-C", str(repo), "rm", "--quiet", ".forge/history/gotchas.md"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "commit", "--quiet", "-m", "remove prior gotchas"],
            check=True,
        )
        self.latest_input_head = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        shutil.rmtree(repo / ".forge")
        directory_rollback_disabled = self.mutated_writer(
            [
                injected_failure,
                (
                    "        for directory in reversed(created_directories):",
                    "        for directory in ():",
                ),
            ],
            "directory-rollback-disabled.py",
        )
        result = self.invoke(repo, payload, writer=directory_rollback_disabled)
        self.assertEqual(result.returncode, 2)
        with self.assertRaises(AssertionError):
            self.assert_only_gotcha_lock_artifact(repo)

        repo = self.make_repo()
        gotcha_rollback_disabled = self.mutated_writer(
            [
                injected_failure,
                (
                    "                    os.ftruncate(descriptor, prior_size)",
                    "                    os.ftruncate("
                    "descriptor, os.fstat(descriptor).st_size)",
                ),
            ],
            "gotcha-rollback-disabled.py",
        )
        result = self.invoke(repo, payload, writer=gotcha_rollback_disabled)
        self.assertEqual(result.returncode, 2)
        with self.assertRaises(AssertionError):
            self.assert_transaction_intact(repo)

    def test_oracles_reject_disabled_path_prompt_append_and_collision_controls(self) -> None:
        unsafe_path_refusal = (
            "forge: learning proposal refused — unsafe-output-path\n".encode("utf-8")
        )
        invalid_candidate_refusal = (
            "forge: learning proposal refused — invalid-candidate-id\n".encode("utf-8")
        )
        open_time_replacements = [
            (
                "        validate_opened_directory(repo, path.parent, parent_descriptor)",
                "        os.fstat(parent_descriptor)",
            ),
            (
                "            descriptor = os.open(\n"
                "                path.name,\n"
                "                open_flags,\n"
                "                0o666,\n"
                "                dir_fd=parent_descriptor,\n"
                "            )",
                "            descriptor = os.open(path, open_flags, 0o666)",
            ),
            (
                "        validate_opened_output(repo, path, descriptor)",
                "        os.fstat(descriptor)",
            ),
        ]

        # Every forbidden-surface oracle kills a mutant with both confinement
        # layers disabled: configurable pathnames plus an unconfined open.
        source = WRITER.read_text(encoding="utf-8")
        segment_guard = (
            '    if text in {".", ".."} or SAFE_SEGMENT.fullmatch(text) is None:\n'
            "        refuse(code)"
        )
        self.assertEqual(source.count(segment_guard), 1)
        source = source.replace(segment_guard, "    if False:\n        refuse(code)", 1)
        result_guard = (
            '        if candidate_id.endswith(".result"):\n'
            '            refuse("invalid-candidate-id")'
        )
        self.assertEqual(source.count(result_guard), 1)
        source = source.replace(result_guard, "        if False:\n            refuse(\"invalid-candidate-id\")", 1)
        fixed_target = 'target = candidate_dir / f"{candidate.candidate_id}.md"'
        self.assertEqual(source.count(fixed_target), 2)
        source = source.replace(fixed_target, "target = repo / candidate.candidate_id")
        for before, after in open_time_replacements:
            self.assertEqual(source.count(before), 1, before)
            source = source.replace(before, after, 1)
        direct_output_mutant = self.base / "direct-output-mutant.py"
        direct_output_mutant.write_text(source, encoding="utf-8")

        for surface, destination in FORBIDDEN_CONTROLS.items():
            with self.subTest(surface=surface, mutant="configurable output"):
                repo = self.make_repo()
                forbidden = repo / destination
                forbidden.parent.mkdir(parents=True, exist_ok=True)
                result = self.invoke(
                    repo,
                    self.payload(
                        candidates=[self.candidate(id=destination)], gotchas=[]
                    ),
                    writer=direct_output_mutant,
                )
                self.assertEqual(
                    result.returncode, 0, result.stderr.decode(errors="replace")
                )
                self.assertEqual(result.stdout, f"{destination}\n".encode("utf-8"))
                self.assertEqual(result.stderr, b"")
                self.assertTrue(forbidden.is_file())

        # Pathname and open-time confinement are independent and load-bearing.
        # Either remaining layer refuses; only their combined removal permits escape.
        pathname_disabled = self.mutated_writer(
            [
                (
                    segment_guard,
                    "    if False:\n        refuse(code)",
                )
            ],
            "pathname-confinement-disabled.py",
        )
        open_time_disabled = self.mutated_writer(
            open_time_replacements,
            "open-time-confinement-disabled.py",
        )
        both_disabled = self.mutated_writer(
            [
                (
                    segment_guard,
                    "    if False:\n        refuse(code)",
                ),
                *open_time_replacements,
            ],
            "both-confinement-layers-disabled.py",
        )
        traversal_id = "../../../rules/MUTANT_CONTROL"
        traversal_stdout = (
            b".forge/evals/candidates/../../../rules/MUTANT_CONTROL.md\n"
        )
        cases = (
            (
                "pathname disabled",
                pathname_disabled,
                2,
                b"",
                unsafe_path_refusal,
                False,
            ),
            (
                "open-time disabled",
                open_time_disabled,
                2,
                b"",
                invalid_candidate_refusal,
                False,
            ),
            (
                "both disabled",
                both_disabled,
                0,
                traversal_stdout,
                b"",
                True,
            ),
        )
        for layer, mutant, exit_code, stdout, stderr, written in cases:
            with self.subTest(control="path containment", layer=layer):
                repo = self.make_repo()
                (repo / "rules").mkdir()
                target = repo / "rules/MUTANT_CONTROL.md"
                result = self.invoke(
                    repo,
                    self.payload(
                        candidates=[self.candidate(id=traversal_id)],
                        gotchas=[],
                    ),
                    writer=mutant,
                )
                self.assertEqual(result.returncode, exit_code)
                self.assertEqual(result.stdout, stdout)
                self.assertEqual(result.stderr, stderr)
                self.assertEqual(target.is_file(), written)

        # Exact prompt sourcing: replacing the recorded bytes trips the byte oracle.
        repo = self.make_repo()
        mutant = self.mutated_writer(
            [
                (
                    '            with os.fdopen(descriptor, "rb", closefd=False) as handle:\n'
                    '                return handle.read()',
                    '            with os.fdopen(descriptor, "rb", closefd=False) as handle:\n'
                    '                return b"DISABLED_PROMPT"',
                ),
                (
                    '    if (\n'
                    '        execution.get("prompt") != prompt\n'
                    '        or hashlib.sha256(hydrated_prompt).hexdigest() != digest\n'
                    '    ):',
                    '    if execution.get("prompt") != prompt:',
                ),
            ],
            "prompt-mutant.py",
        )
        result = self.invoke(repo, self.payload(gotchas=[]), writer=mutant)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        candidate = repo / ".forge/evals/candidates/journal-review-missed-boundary.md"
        with self.assertRaises(AssertionError):
            self.assertEqual(candidate.read_bytes(), self.expected_candidate())

        # Append-only gotchas: changing append to truncate destroys the prefix oracle.
        repo = self.make_repo()
        mutant = self.mutated_writer(
            [
                (
                    "            output.seek(0, os.SEEK_END)",
                    "            output.seek(0)\n            output.truncate()",
                )
            ],
            "append-mutant.py",
        )
        result = self.invoke(repo, self.payload(candidates=[]), writer=mutant)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        with self.assertRaises(AssertionError):
            self.assertTrue((repo / ".forge/history/gotchas.md").read_bytes().startswith(PRIOR_GOTCHAS))

        # New-only candidates: disabling both collision checks makes overwrite observable.
        repo = self.make_repo()
        target = repo / ".forge/evals/candidates/journal-review-missed-boundary.md"
        original = b"ORIGINAL CANDIDATE\n"
        target.write_bytes(original)
        mutant = self.mutated_writer(
            [
                (
                    "            if lexical_exists(target):\n                refuse(\"candidate-collision\")",
                    "            if False:\n                refuse(\"candidate-collision\")",
                ),
                (
                    "                        target,\n"
                    "                        os.O_WRONLY,\n"
                    "                        must_be_new=True,",
                    "                        target,\n"
                    "                        os.O_WRONLY | os.O_TRUNC,\n"
                    "                        must_be_new=False,",
                ),
            ],
            "collision-mutant.py",
        )
        result = self.invoke(repo, self.payload(gotchas=[]), writer=mutant)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        with self.assertRaises(AssertionError):
            self.assertEqual(target.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
