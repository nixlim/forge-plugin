"""Hermetic support for candidate-bound fresh reviewer evaluation tests."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile
import threading
from typing import Mapping

from tests._cli_loader import package_module


CANDIDATE = package_module("candidate")
FRESH = package_module("fresh_evals")
POLICY = package_module("policy")

ROOT = Path(__file__).resolve().parents[1]
TASK_ROOT = ROOT / ".forge" / "evals" / "tasks"

TRIGGER_ROWS = POLICY._parse_reviewer_eval_triggers(
    POLICY.REVIEWER_EVAL_TRIGGER_TABLE
)


def trigger_table(rows: tuple[tuple[str, tuple[str, ...]], ...] = TRIGGER_ROWS) -> str:
    rendered = ["| control | path patterns |", "|---|---|"]
    rendered.extend(
        f"| {control} | {', '.join(patterns)} |" for control, patterns in rows
    )
    return "\n".join(rendered) + "\n"


TRIGGER_TABLE = POLICY.REVIEWER_EVAL_TRIGGER_TABLE
ORACLE_TOKEN = "FRESH_ORACLE_MUST_BE_WITHHELD_7d6d98"
FENCED_SUBJECT_TOKEN = "FENCED_EXPECTED_IS_SUBJECT_39bbd1"
PROJECTION_ORACLE_PATHS = (
    (
        ".forge/evals/tasks/**",
        ".forge/evals/tasks/review-passes-clean-change.md",
    ),
    (".forge/evals/candidates/**", ".forge/evals/candidates/oracle.md"),
    (".forge/history/**", ".forge/history/projection-oracle.md"),
    ("docs/**", "docs/projection-oracle.md"),
    ("skills/init/SKILL.md", "skills/init/SKILL.md"),
    (
        "system/seeds/eval-tasks/**",
        "system/seeds/eval-tasks/projection-oracle.template.md",
    ),
    ("tests/**", "tests/projection-oracle.txt"),
)


def policy_with_trigger_region(raw: bytes, body: str = TRIGGER_TABLE) -> bytes:
    region = (
        "<!-- FORGE:REGION reviewer-facing-eval-triggers BEGIN -->\n"
        + body
        + "<!-- FORGE:REGION reviewer-facing-eval-triggers END -->\n"
    ).encode("utf-8")
    begin = b"<!-- FORGE:REGION reviewer-facing-eval-triggers BEGIN -->\n"
    end = b"<!-- FORGE:REGION reviewer-facing-eval-triggers END -->\n"
    begin_count = raw.count(begin)
    end_count = raw.count(end)
    if begin_count or end_count:
        if begin_count != 1 or end_count != 1:
            raise AssertionError("reviewer-facing eval trigger region is malformed")
        before, remainder = raw.split(begin, 1)
        _old_body, after = remainder.split(end, 1)
        return before + region + after
    return raw.rstrip(b"\n") + b"\n\n" + region


def canonical_document(value: object) -> bytes:
    return (
        __import__("json")
        .dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        .encode("utf-8")
        + b"\n"
    )


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class FreshEvalRepo:
    """A small Git repository whose base contains the real reviewer corpus."""

    def __init__(self, *, fenced_oracle: bool = False) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="forge-fresh-test-repo-")
        self.root = Path(self.temporary.name)
        self.git("init", "-q")
        self.git("config", "user.email", "forge@example.invalid")
        self.git("config", "user.name", "Forge Fresh Eval Test")

        policy_raw = policy_with_trigger_region((ROOT / "forge-project.md").read_bytes())
        self.write("forge-project.md", policy_raw)
        for relative in (
            ".codex/agents/review-cheap.toml",
            ".codex/config.toml",
            ".forge/history/gotchas.md",
            "rules/review-constitution.md",
            "system/codex/agents/review-cheap.toml",
            "system/codex/config.toml",
            "system/codex/prompts/review-cheap.md",
        ):
            self.write(relative, (ROOT / relative).read_bytes())

        for source in sorted(TASK_ROOT.glob("*.md")):
            raw = source.read_bytes()
            if fenced_oracle and source.name == "review-passes-clean-change.md":
                replacement = (
                    "```markdown\n"
                    "## Expected\n"
                    f"{FENCED_SUBJECT_TOKEN}\n"
                    "```\n\n"
                    "## Expected\n\n"
                    f"{ORACLE_TOKEN}\n"
                ).encode("utf-8")
                if raw.count(b"## Expected\n") != 1:
                    raise AssertionError("oracle fixture shape changed")
                raw = raw.replace(b"## Expected\n", replacement, 1)
            self.write(f".forge/evals/tasks/{source.name}", raw)
            result_source = source.with_suffix(".result")
            if result_source.is_file():
                self.write(
                    f".forge/evals/tasks/{result_source.name}",
                    result_source.read_bytes(),
                )

        if fenced_oracle:
            for pathspec, relative in PROJECTION_ORACLE_PATHS[1:]:
                self.write(relative, f"{ORACLE_TOKEN} {pathspec}\n")

        # A rename test needs a base-side triggering path that is not itself a
        # reviewer input or control used during collection.
        self.write("rules/rename-source.md", b"base-side trigger\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "base evaluator controls")
        self.base_oid = self.git("rev-parse", "HEAD").stdout.decode().strip()
        self.context = CANDIDATE.discover_context(self.root)
        self.policy = POLICY.parse_policy(self.base_oid, policy_raw)
        self.expected_verdicts = self._expected_verdicts()

    def cleanup(self) -> None:
        self.temporary.cleanup()

    def __enter__(self) -> "FreshEvalRepo":
        return self

    def __exit__(self, *_args: object) -> None:
        self.cleanup()

    def git(self, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            ["git", *arguments],
            cwd=self.root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=check,
        )

    def write(self, relative: str, raw: bytes | str) -> None:
        target = self.root / PurePosixPath(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw.encode("utf-8") if isinstance(raw, str) else raw)

    def stage_append(self, relative: str, suffix: bytes = b"\nchanged\n") -> None:
        target = self.root / PurePosixPath(relative)
        if target.exists():
            target.write_bytes(target.read_bytes() + suffix)
        else:
            self.write(relative, suffix.lstrip(b"\n"))
        self.git("add", "--", relative)

    def stage_many(self, paths: tuple[str, ...]) -> None:
        for index, path in enumerate(paths):
            suffix = f"\n# staged trigger {index}\n".encode("utf-8")
            self.stage_append(path, suffix)

    def remove(self, relative: str) -> None:
        self.git("rm", "-q", "--", relative)

    def snapshot(self):
        return CANDIDATE.snapshot(
            self.context, computed_at="2020-01-01T00:00:00Z"
        )

    def evaluation(
        self,
        snapshot=None,
        *,
        request_id: str = "1" * 32,
        chain_id: str = "fresh-eval-test-chain",
        artifact_prefix: str | None = None,
        request_is_persisted=lambda: True,
        halt_checker=lambda: None,
    ):
        selected = snapshot or self.snapshot()
        suite, fixture_packages = FRESH.prepare_request_plan(
            self.context,
            selected.state_record(),
            request_id,
        )
        return FRESH.EvaluationRequest(
            chain_id=chain_id,
            request_id=request_id,
            requested_at="2020-01-01T00:00:00Z",
            iteration=1,
            candidate=selected.state_record(),
            paths=selected.paths,
            policy=self.policy,
            source_context=self.context,
            artifact_prefix=artifact_prefix or f"fresh/{request_id}",
            suite=suite,
            fixture_packages=tuple(fixture_packages),
            request_is_persisted=request_is_persisted,
            halt_checker=halt_checker,
            final_index_observation=lambda: CANDIDATE.observe_index(self.context),
        )

    def _expected_verdicts(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for path in sorted((self.root / ".forge/evals/tasks").glob("*.md")):
            frontmatter, _offset = FRESH._frontmatter(path.read_bytes(), path.as_posix())
            result[frontmatter["id"]] = frontmatter["expected_verdict"]
        return result


class MemoryArtifacts:
    """Filesystem-backed chain-artifact seam with digest and no-follow reads."""

    def __init__(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="forge-fresh-artifacts-")
        self.root = Path(self.temporary.name)
        self._lock = threading.Lock()

    def cleanup(self) -> None:
        self.temporary.cleanup()

    def __enter__(self) -> "MemoryArtifacts":
        return self

    def __exit__(self, *_args: object) -> None:
        self.cleanup()

    def _path(self, reference: str) -> Path:
        relative = PurePosixPath(reference)
        if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            raise ValueError("unsafe artifact reference")
        return self.root / relative

    def write(self, relative: str, data: bytes, *, exclusive: bool) -> str:
        target = self._path(relative)
        with self._lock:
            target.parent.mkdir(parents=True, exist_ok=True)
            flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW
            flags |= os.O_EXCL if exclusive else os.O_TRUNC
            descriptor = os.open(target, flags, 0o600)
            try:
                os.write(descriptor, data)
            finally:
                os.close(descriptor)
        return relative

    def read(self, reference: str, expected_digest: str | None, *, max_bytes: int) -> bytes:
        target = self._path(reference)
        descriptor = os.open(target, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError("artifact is not regular")
            raw = os.read(descriptor, max_bytes + 1)
        finally:
            os.close(descriptor)
        if len(raw) > max_bytes:
            raise ValueError("artifact cap exceeded")
        if expected_digest is not None and sha256(raw) != expected_digest:
            raise ValueError("artifact digest changed")
        return raw

    def absolute(self, reference: str) -> Path:
        return self._path(reference)


class ScriptedLauncher:
    """No-model launcher that emits a bound verdict through the real argv path."""

    def __init__(
        self,
        expected: Mapping[str, str],
        *,
        verdicts: Mapping[str, str] | None = None,
        malformed: Mapping[str, bytes] | None = None,
        missing: frozenset[str] = frozenset(),
        timed_out: frozenset[str] = frozenset(),
        overflow: frozenset[str] = frozenset(),
        returncodes: Mapping[str, int] | None = None,
        first_wave_barrier: int | None = None,
    ) -> None:
        self.expected = dict(expected)
        self.verdicts = dict(verdicts or {})
        self.malformed = dict(malformed or {})
        self.missing = missing
        self.timed_out = timed_out
        self.overflow = overflow
        self.returncodes = dict(returncodes or {})
        self.requests: dict[str, object] = {}
        self.prompts: dict[str, bytes] = {}
        self.started: list[str] = []
        self.completed: list[str] = []
        self.active = 0
        self.max_active = 0
        self.last_started_after_first_wave = False
        self._lock = threading.Lock()
        self._barrier_size = first_wave_barrier
        self._barrier = (
            threading.Barrier(first_wave_barrier)
            if first_wave_barrier is not None
            else None
        )

    @staticmethod
    def _binding(prompt: bytes, key: bytes) -> str:
        match = re.search(rb"(?m)^" + re.escape(key) + rb": ([0-9a-f]+)$", prompt)
        if match is None:
            raise AssertionError(f"prompt omitted {key.decode()} binding")
        return match.group(1).decode("ascii")

    def launch(self, request):
        fixture_id = request.fixture_id
        with self._lock:
            sequence = len(self.started) + 1
            if self._barrier_size is not None and sequence > self._barrier_size:
                self.last_started_after_first_wave = len(self.completed) == self._barrier_size
            self.started.append(fixture_id)
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.requests[fixture_id] = request
            self.prompts[fixture_id] = request.prompt
        try:
            if self._barrier is not None and sequence <= int(self._barrier_size or 0):
                self._barrier.wait(timeout=10)
            authorization = self._binding(request.prompt, b"authorization_id")
            request_id = self._binding(request.prompt, b"request_id")
            package = self._binding(request.prompt, b"fixture_package")
            verdict = self.verdicts.get(fixture_id, self.expected[fixture_id])
            raw = self.malformed.get(
                fixture_id,
                (
                    f"VERDICT: {verdict}\n"
                    f"authorization_id: {authorization}\n"
                    f"request_id: {request_id}\n"
                    f"fixture_package: {package}\n"
                ).encode("utf-8"),
            )
            if fixture_id not in self.missing:
                verdict_index = request.argv.index("--output-last-message") + 1
                Path(request.argv[verdict_index]).write_bytes(raw)
            events = f'{{"fixture":"{fixture_id}","type":"result"}}\n'.encode("utf-8")
            started_at = FRESH._utc_now()
            completed_at = FRESH._utc_now()
            return FRESH.LaunchResult(
                argv=request.argv,
                returncode=self.returncodes.get(fixture_id, 0),
                output=events,
                output_digest=sha256(events),
                timed_out=fixture_id in self.timed_out,
                output_overflow=fixture_id in self.overflow,
                started_at=started_at,
                completed_at=completed_at,
                reviewer_pid=10_000 + sequence,
                process_group_id=10_000 + sequence,
            )
        finally:
            with self._lock:
                self.active -= 1
                self.completed.append(fixture_id)
