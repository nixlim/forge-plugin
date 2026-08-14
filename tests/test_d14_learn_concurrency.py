"""End-to-end concurrency evidence for advisory learning proposal writes."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts/forge/learn-proposals-locked.py"
WRITER = ROOT / "scripts/forge/learn-proposals.py"
RUN_ID = "run-concurrency"
AGENT = "review-cheap-01"
EXECUTION = "execution-01"
ROLE = "reviewer"
ARCHIVE_PATH = f".forge/history/runs/{RUN_ID}.md"
PRIOR_GOTCHAS = b"# Learned failure shapes\r\nexisting bytes"
PROMPT = b"ROLE\r\n\nExact concurrent prompt bytes: \xcf\x80\n"
LOCK_ANCHOR = "fcntl.flock(handle.fileno(), fcntl.LOCK_EX)"
START_GATE_ANCHOR = "def locked_run(repo: Path, argv: list[str]) -> None:\n    with proposal_lock(repo):"
APPEND_SNAPSHOT_ANCHOR = "        prior_size = len(prior)\n"


@dataclass(frozen=True)
class Invocation:
    candidate_id: str
    line: str
    proposal: Path
    input_head: str


@dataclass(frozen=True)
class Result:
    returncode: int
    stdout: bytes
    stderr: bytes


class LearnConcurrencyTests(unittest.TestCase):
    maxDiff = None

    def git(self, repo: Path, *arguments: str) -> str:
        result = subprocess.run(
            ["git", "-C", os.fspath(repo), *arguments],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        return result.stdout

    def make_repo(self, base: Path) -> tuple[Path, str]:
        repo = base / "repo"
        run_dir = repo / ".codex-orchestrator/runs" / RUN_ID
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
                "role": ROLE,
                "task": "task-main",
            },
            {"type": "decision", "id": "decision-01", "task": "task-main"},
            {
                "type": "verification",
                "id": "verification-01",
                "task": "task-main",
                "result": "failed",
                "observation": "The cited failure earned both advisory proposals.",
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
        archive = repo / ARCHIVE_PATH
        archive.parent.mkdir(parents=True)
        authority = {
            "decisions": [{"id": "decision-01", "task": "task-main"}],
            "executions": [
                {
                    "agent": AGENT,
                    "execution": EXECUTION,
                    "prompt": prompt.relative_to(run_dir).as_posix(),
                    "prompt_sha256": hashlib.sha256(PROMPT).hexdigest(),
                    "role": ROLE,
                    "task": "task-main",
                }
            ],
            "failed_or_inconclusive_verifications": [
                {
                    "criterion": None,
                    "id": "verification-01",
                    "observation": "The cited failure earned both advisory proposals.",
                    "result": "failed",
                    "task": "task-main",
                }
            ],
        }
        archive.write_text(
            "# Run archive\n\n"
            "<!-- BEGIN FORGE LEARNING PROVENANCE v1 -->\n"
            "```json\n"
            + json.dumps(authority, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n```\n"
            "<!-- END FORGE LEARNING PROVENANCE v1 -->\n",
            encoding="utf-8",
        )
        self.git(repo, "init", "--quiet")
        self.git(repo, "config", "user.email", "forge-concurrency@example.invalid")
        self.git(repo, "config", "user.name", "Forge concurrency test")
        self.git(repo, "add", ARCHIVE_PATH, ".forge/history/gotchas.md")
        self.git(repo, "commit", "--quiet", "-m", "commit learning inputs")
        input_head = self.git(repo, "rev-parse", "HEAD").strip()
        self.assertRegex(input_head, r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
        self.assertEqual(
            PRIOR_GOTCHAS,
            subprocess.run(
                [
                    "git",
                    "-C",
                    os.fspath(repo),
                    "cat-file",
                    "blob",
                    f"{input_head}:.forge/history/gotchas.md",
                ],
                check=True,
                capture_output=True,
            ).stdout,
        )
        return repo, input_head

    def make_invocation(
        self, base: Path, input_head: str, candidate_id: str, line: str
    ) -> Invocation:
        payload = {
            "schema_version": 1,
            "input_head": input_head,
            "candidates": [
                {
                    "id": candidate_id,
                    "category": "review",
                    "agent": AGENT,
                    "expected_verdict": "BLOCK",
                    "run_id": RUN_ID,
                    "execution": EXECUTION,
                    "scenario": f"{line} escaped the first review.",
                    "expected": "The reviewer MUST return BLOCK.",
                }
            ],
            "gotchas": [
                {
                    "run_id": RUN_ID,
                    "agent": AGENT,
                    "execution": EXECUTION,
                    "entries": [
                        {"type": "decision", "id": "decision-01"},
                        {"type": "verification", "id": "verification-01"},
                    ],
                    "line": line,
                }
            ],
        }
        proposal = base / f"{candidate_id}.json"
        proposal.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )
        return Invocation(candidate_id, line, proposal, input_head)

    def instrumented_sources(self) -> tuple[str, str]:
        wrapper = WRAPPER.read_text(encoding="utf-8")
        writer = WRITER.read_text(encoding="utf-8")
        self.assertEqual(1, wrapper.count(LOCK_ANCHOR))
        self.assertEqual(1, wrapper.count(START_GATE_ANCHOR))
        self.assertEqual(1, writer.count(APPEND_SNAPSHOT_ANCHOR))
        wrapper = wrapper.replace(
            START_GATE_ANCHOR,
            "def locked_run(repo: Path, argv: list[str]) -> None:\n"
            "    if os.environ.get('FORGE_D14_START_GATE') == '1':\n"
            "        print('READY', flush=True)\n"
            "        if sys.stdin.buffer.read(1) != b'G':\n"
            "            raise LockFailure\n"
            "    with proposal_lock(repo):",
            1,
        )
        writer = writer.replace(
            APPEND_SNAPSHOT_ANCHOR,
            APPEND_SNAPSHOT_ANCHOR
            + "        race_role = os.environ.get('FORGE_D14_RACE_ROLE')\n"
            + "        if race_role in {'winner', 'rollbacker'}:\n"
            + "            print(f'RACE-{race_role}', flush=True)\n"
            + "            if sys.stdin.buffer.read(1) != b'R':\n"
            + "                raise OSError('race coordination failed')\n"
            + "            if race_role == 'rollbacker':\n"
            + "                raise OSError('injected late append failure')\n",
            1,
        )
        return wrapper, writer

    def write_tools(
        self, base: Path, wrapper_source: str, writer_source: str
    ) -> Path:
        tools = base / "tools"
        tools.mkdir()
        wrapper = tools / WRAPPER.name
        writer = tools / WRITER.name
        wrapper.write_text(wrapper_source, encoding="utf-8")
        writer.write_text(writer_source, encoding="utf-8")
        return wrapper

    def launch(
        self,
        wrapper: Path,
        repo: Path,
        invocation: Invocation,
        *,
        role: str | None = None,
    ) -> subprocess.Popen[bytes]:
        environment = os.environ.copy()
        environment["FORGE_D14_START_GATE"] = "1"
        if role is not None:
            environment["FORGE_D14_RACE_ROLE"] = role
        return subprocess.Popen(
            [
                sys.executable,
                str(wrapper),
                "--repo",
                str(repo),
                "--proposal",
                str(invocation.proposal),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
        )

    def read_protocol_line(
        self, process: subprocess.Popen[bytes], expected: bytes
    ) -> None:
        assert process.stdout is not None
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            self.assertTrue(
                selector.select(timeout=5),
                f"proposal process did not emit {expected!r}",
            )
        self.assertEqual(expected + b"\n", process.stdout.readline())

    def release(self, process: subprocess.Popen[bytes], byte: bytes) -> None:
        assert process.stdin is not None
        process.stdin.write(byte)
        process.stdin.flush()

    def finish(self, process: subprocess.Popen[bytes]) -> Result:
        stdout, stderr = process.communicate(timeout=10)
        return Result(process.returncode, stdout, stderr)

    def stop(self, processes: list[subprocess.Popen[bytes]]) -> None:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.communicate()

    def gotcha_line(self, line: str, input_head: str) -> bytes:
        return (
            f"- {line} [journal: run-id={RUN_ID}; agent={AGENT}; "
            f"execution-id={EXECUTION}; entries=decision:decision-01,"
            "verification:verification-01] "
            f"[archive: {input_head}:{ARCHIVE_PATH}]\n"
        ).encode("utf-8")

    def assert_complete(
        self,
        repo: Path,
        invocations: tuple[Invocation, Invocation],
        results: tuple[Result, Result],
    ) -> None:
        for invocation, result in zip(invocations, results):
            self.assertEqual(0, result.returncode, result.stderr.decode(errors="replace"))
            self.assertEqual(b"", result.stderr)
            self.assertEqual(
                {
                    f".forge/evals/candidates/{invocation.candidate_id}.md",
                    ".forge/history/gotchas.md",
                },
                set(result.stdout.decode("utf-8").splitlines()),
            )
            candidate = (
                repo / ".forge/evals/candidates" / f"{invocation.candidate_id}.md"
            )
            content = candidate.read_bytes()
            self.assertIn(PROMPT, content)
            self.assertIn(invocation.candidate_id.encode("utf-8"), content)
            self.assertIn(
                f"- archive: `{invocation.input_head}:{ARCHIVE_PATH}`".encode(),
                content,
            )

        gotchas = (repo / ".forge/history/gotchas.md").read_bytes()
        lines = tuple(
            self.gotcha_line(invocation.line, invocation.input_head)
            for invocation in invocations
        )
        self.assertIn(
            gotchas,
            {
                PRIOR_GOTCHAS + b"\n" + lines[0] + lines[1],
                PRIOR_GOTCHAS + b"\n" + lines[1] + lines[0],
            },
        )
        self.assertFalse((repo / ".forge/evals/tasks").exists())
        self.assertEqual([], list(repo.rglob("*.result")))

    def test_real_writers_preserve_both_outputs_and_disabled_lock_fails_oracle(
        self,
    ) -> None:
        wrapper_source, writer_source = self.instrumented_sources()

        with tempfile.TemporaryDirectory(prefix="forge-learn-locked-") as raw:
            base = Path(raw)
            repo, input_head = self.make_repo(base)
            invocations = (
                self.make_invocation(
                    base, input_head, "candidate-alpha", "Preserve alpha evidence."
                ),
                self.make_invocation(
                    base, input_head, "candidate-beta", "Preserve beta evidence."
                ),
            )
            wrapper = self.write_tools(base, wrapper_source, writer_source)
            processes = [
                self.launch(wrapper, repo, invocations[0]),
                self.launch(wrapper, repo, invocations[1]),
            ]
            try:
                for process in processes:
                    self.read_protocol_line(process, b"READY")
                for process in processes:
                    self.release(process, b"G")
                results = (self.finish(processes[0]), self.finish(processes[1]))
            finally:
                self.stop(processes)
            self.assert_complete(repo, invocations, results)

        mutant_wrapper = wrapper_source.replace(
            LOCK_ANCHOR, "pass  # mutation: disabled proposal lock", 1
        )
        with tempfile.TemporaryDirectory(prefix="forge-learn-unlocked-") as raw:
            base = Path(raw)
            repo, input_head = self.make_repo(base)
            invocations = (
                self.make_invocation(
                    base, input_head, "candidate-winner", "Preserve winner evidence."
                ),
                self.make_invocation(
                    base,
                    input_head,
                    "candidate-rollbacker",
                    "Preserve rollback evidence.",
                ),
            )
            wrapper = self.write_tools(base, mutant_wrapper, writer_source)
            processes = [
                self.launch(wrapper, repo, invocations[0], role="winner"),
                self.launch(wrapper, repo, invocations[1], role="rollbacker"),
            ]
            try:
                for process in processes:
                    self.read_protocol_line(process, b"READY")
                for process in processes:
                    self.release(process, b"G")
                self.read_protocol_line(processes[0], b"RACE-winner")
                self.read_protocol_line(processes[1], b"RACE-rollbacker")
                self.release(processes[0], b"R")
                winner_result = self.finish(processes[0])
                self.release(processes[1], b"R")
                rollback_result = self.finish(processes[1])
            finally:
                self.stop(processes)

            self.assertEqual(0, winner_result.returncode, winner_result.stderr.decode())
            self.assertEqual(2, rollback_result.returncode)
            self.assertEqual(PRIOR_GOTCHAS, (repo / ".forge/history/gotchas.md").read_bytes())
            self.assertFalse(
                (repo / ".forge/evals/candidates/candidate-rollbacker.md").exists()
            )
            with self.assertRaises(AssertionError):
                self.assert_complete(
                    repo,
                    invocations,
                    (winner_result, rollback_result),
                )


if __name__ == "__main__":
    unittest.main()
