from __future__ import annotations

import csv
import datetime as dt
import fcntl
import hashlib
import itertools
import json
import multiprocessing
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import traceback
import unittest


ROOT = Path(__file__).resolve().parents[1]
FORGE_SCRIPTS = ROOT / "scripts" / "forge"
COMMIT_GUARD = FORGE_SCRIPTS / "commit-guard.sh"
ACQUIRE_LOCK = FORGE_SCRIPTS / "acquire-commit-lock.sh"
RELEASE_LOCK = FORGE_SCRIPTS / "release-commit-lock.sh"
EMIT_EVENT = FORGE_SCRIPTS / "emit-decision-event.py"
AGGREGATE = FORGE_SCRIPTS / "aggregate-telemetry.sh"
ORCH_TOOLS = ROOT / "scripts" / "codex_orch_tools.py"
WINDOW_START = "2000-01-01T00:00:00Z"
WINDOW_END = "2100-01-01T00:00:00Z"
HARNESS_DEADLINE_SECONDS = 75


def _run(
    arguments: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    input_bytes: bytes | None = None,
    timeout: float = 30,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        arguments,
        cwd=cwd,
        env=env,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
    )


def _checked(
    arguments: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    input_bytes: bytes | None = None,
    timeout: float = 30,
) -> subprocess.CompletedProcess[bytes]:
    completed = _run(
        arguments, cwd=cwd, env=env, input_bytes=input_bytes, timeout=timeout
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"command failed ({completed.returncode}): {arguments!r}\n"
            f"stdout={completed.stdout.decode('utf-8', 'replace')}\n"
            f"stderr={completed.stderr.decode('utf-8', 'replace')}"
        )
    return completed


def _git(cwd: Path, *arguments: str, input_bytes: bytes | None = None) -> bytes:
    return _checked(
        ["git", *arguments], cwd=cwd, input_bytes=input_bytes
    ).stdout


def _utc_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def _orch(
    config: dict[str, object],
    env: dict[str, str],
    *arguments: str,
) -> subprocess.CompletedProcess[bytes]:
    return _run(
        ["python3", str(config.get("orch_tools", ORCH_TOOLS)), *arguments],
        cwd=Path(str(config["worktree"])),
        env=env,
    )


def _require_ok(completed: subprocess.CompletedProcess[bytes], label: str) -> None:
    if completed.returncode != 0:
        raise AssertionError(
            f"{label} failed ({completed.returncode}): "
            f"{completed.stdout.decode('utf-8', 'replace')}"
            f"{completed.stderr.decode('utf-8', 'replace')}"
        )


def _journal_open(config: dict[str, object], env: dict[str, str]) -> None:
    record = Path(str(config["record_dir"])) / f"{config['run_id']}-open.json"
    _write_json(record, {"run_id": config["run_id"], "type": "run_started"})
    completed = _orch(
        config,
        env,
        "run-open",
        "--repo",
        str(config["worktree"]),
        "--run-id",
        str(config["run_id"]),
        "--scope",
        str(config["scope"]),
        "--record-json",
        str(record),
    )
    _require_ok(completed, "run-open")


def _journal_append(
    config: dict[str, object],
    env: dict[str, str],
    *,
    suffix: str,
    criterion: str,
) -> None:
    record = Path(str(config["record_dir"])) / f"{config['run_id']}-{suffix}.json"
    _write_json(
        record,
        {
            "criterion": criterion,
            "id": f"{config['run_id']}-{suffix}",
            "result": "passed",
            "run_id": config["run_id"],
            "type": "verification",
        },
    )
    completed = _orch(
        config,
        env,
        "journal-append",
        "--repo",
        str(config["worktree"]),
        "--run-id",
        str(config["run_id"]),
        "--record-json",
        str(record),
    )
    _require_ok(completed, "journal-append")


def _journal_close(config: dict[str, object], env: dict[str, str]) -> None:
    record = Path(str(config["record_dir"])) / f"{config['run_id']}-close.json"
    _write_json(record, {"run_id": config["run_id"], "type": "run_closed"})
    completed = _orch(
        config,
        env,
        "run-close",
        "--repo",
        str(config["worktree"]),
        "--run-id",
        str(config["run_id"]),
        "--record-json",
        str(record),
    )
    _require_ok(completed, "run-close")


def _guard(worktree: Path, env: dict[str, str], guard: Path = COMMIT_GUARD) -> subprocess.CompletedProcess[bytes]:
    payload = json.dumps(
        {"tool_input": {"command": "git commit -m d13"}, "tool_name": "Bash"}
    ).encode("utf-8")
    return _run(["bash", str(guard)], cwd=worktree, env=env, input_bytes=payload)


def _write_marker(main_root: Path, candidate: str) -> Path:
    marker = main_root / ".forge/tmp/authorized" / candidate
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(f"{candidate}\n{_utc_now()}\n", encoding="utf-8")
    return marker


def _write_telemetry_unit(main_root: Path, worker_id: str) -> None:
    decisions = main_root / ".forge/tmp/decisions"
    decisions.mkdir(parents=True, exist_ok=True)
    (decisions / f"{worker_id}.md").write_text(
        "```telemetry\n"
        f"unit: unit-{worker_id}\n"
        "feature: d13-concurrency\n"
        "model: fixture\n"
        "elapsed_s: 1\n"
        "critical_path_s: 1\n"
        "tokens: 1\n"
        "cost_usd: 0\n"
        "review_iterations: 1\n"
        "rework_s: 0\n"
        "```\n",
        encoding="utf-8",
    )


def _emit_event(
    config: dict[str, object], env: dict[str, str], candidate: str, event: str
) -> subprocess.CompletedProcess[bytes]:
    reason = "inconclusive" if event == "assertion_advisory" else "MINOR"
    emitter = Path(str(config.get("event_emitter", EMIT_EVENT)))
    completed = _run(
        [
            "python3",
            str(emitter),
            "--at",
            _utc_now(),
            "--candidate",
            candidate,
            "--event",
            event,
            "--policy-sha",
            str(config["base"]),
            "--reason",
            reason,
            "--surface",
            "fixture",
        ],
        cwd=Path(str(config["worktree"])),
        env=env,
    )
    _require_ok(completed, "emit-decision-event")
    return completed


def _emit_event_process(
    repo: str,
    emitter: str,
    policy_sha: str,
    candidate: str,
    barrier: object,
    result_path: str,
    open_barrier_dir: str | None,
    open_barrier_count: int | None,
) -> None:
    result: dict[str, object] = {"candidate": candidate, "pid": os.getpid()}
    env = os.environ.copy()
    env["FORGE_SESSION_PID"] = str(os.getpid())
    env.pop("FORGE_TEST_EVENT_OPEN_BARRIER_DIR", None)
    env.pop("FORGE_TEST_EVENT_OPEN_BARRIER_COUNT", None)
    if open_barrier_dir is not None and open_barrier_count is not None:
        env["FORGE_TEST_EVENT_OPEN_BARRIER_DIR"] = open_barrier_dir
        env["FORGE_TEST_EVENT_OPEN_BARRIER_COUNT"] = str(open_barrier_count)
    try:
        barrier.wait(timeout=15)
        completed = _run(
            [
                "python3",
                emitter,
                "--at",
                _utc_now(),
                "--candidate",
                candidate,
                "--event",
                "assertion_advisory",
                "--policy-sha",
                policy_sha,
                "--reason",
                "inconclusive",
                "--surface",
                "fixture",
            ],
            cwd=Path(repo),
            env=env,
            timeout=12,
        )
        result.update(
            {
                "returncode": completed.returncode,
                "stderr": completed.stderr.decode("utf-8", "replace"),
                "stdout": completed.stdout.decode("utf-8", "replace"),
            }
        )
    except BaseException:
        result["traceback"] = traceback.format_exc()
        try:
            barrier.abort()
        except BaseException:
            pass
    finally:
        _write_json(Path(result_path), result)


def _join_processes(
    processes: list[multiprocessing.Process],
    *,
    deadline_seconds: float = HARNESS_DEADLINE_SECONDS,
) -> list[multiprocessing.Process]:
    deadline = time.monotonic() + deadline_seconds
    for process in processes:
        process.join(max(0.1, deadline - time.monotonic()))
    alive = [process for process in processes if process.is_alive()]
    for process in alive:
        process.terminate()
        process.join(5)
    return alive


def _aggregate(config: dict[str, object], env: dict[str, str]) -> None:
    main_root = Path(str(config["main_root"]))
    completed = _run(
        [
            "bash",
            str(AGGREGATE),
            str(main_root / ".forge/tmp/decisions"),
            "--append-csv",
            ".forge/tmp/telemetry.csv",
            "--session",
            f"session-{config['worker_id']}",
            "--since",
            WINDOW_START,
            "--until",
            WINDOW_END,
        ],
        cwd=Path(str(config["worktree"])),
        env=env,
        timeout=40,
    )
    _require_ok(completed, "aggregate-telemetry")


def _overlap_probe(config: dict[str, object], env: dict[str, str]) -> dict[str, object]:
    record = Path(str(config["record_dir"])) / "run-overlap-open.json"
    _write_json(record, {"run_id": "run-overlap", "type": "run_started"})
    completed = _orch(
        config,
        env,
        "run-open",
        "--repo",
        str(config["worktree"]),
        "--run-id",
        "run-overlap",
        "--scope",
        str(config["scope"]),
        "--record-json",
        str(record),
    )
    return {
        "returncode": completed.returncode,
        "stderr": completed.stderr.decode("utf-8", "replace"),
        "stdout": completed.stdout.decode("utf-8", "replace"),
    }


def _foreign_owner_probe(
    config: dict[str, object],
    env: dict[str, str],
    target_run_id: str,
) -> dict[str, object]:
    worker_id = str(config["worker_id"])
    record = Path(str(config["record_dir"])) / f"{worker_id}-foreign-owner.json"
    _write_json(
        record,
        {
            "criterion": "ownership: foreign writer must not append",
            "id": f"foreign-{worker_id}",
            "result": "passed",
            "run_id": target_run_id,
            "type": "verification",
        },
    )
    journal = (
        Path(str(config["main_root"]))
        / ".codex-orchestrator/runs"
        / target_run_id
        / "journal.jsonl"
    )
    completed = _orch(
        config,
        env,
        "journal-append",
        "--repo",
        str(config["worktree"]),
        "--run-id",
        target_run_id,
        "--record-json",
        str(record),
    )
    records = [
        json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()
    ]
    return {
        "foreign_record_present": any(
            record.get("id") == f"foreign-{worker_id}" for record in records
        ),
        "returncode": completed.returncode,
        "stderr": completed.stderr.decode("utf-8", "replace"),
        "stdout": completed.stdout.decode("utf-8", "replace"),
    }


def _concurrent_marker_phase(
    config: dict[str, object],
    env: dict[str, str],
    barrier: object,
    result: dict[str, object],
    candidate: str | None,
) -> None:
    """Make each commit guard face only the other live candidate marker."""

    main_root = Path(str(config["main_root"]))
    marker_dir = main_root / ".forge/tmp/authorized"
    own_marker = marker_dir / candidate if candidate is not None else None
    guard_path = Path(str(config.get("guard_path", COMMIT_GUARD)))
    cross_denials_enabled = bool(config.get("cross_denials_enabled", True))

    # Both authorizers publish before anybody observes or removes a marker.
    barrier.wait(timeout=30)
    result["markers_at_barrier"] = sorted(
        path.name for path in marker_dir.glob("*") if path.is_file()
    )
    barrier.wait(timeout=30)

    for active_worker in ("commit-a", "commit-b"):
        active = config["worker_id"] == active_worker
        if active:
            assert own_marker is not None
            own_marker.unlink()
        barrier.wait(timeout=30)
        if active:
            denied = (
                _guard(Path(str(config["worktree"])), env, guard_path)
                if cross_denials_enabled
                else subprocess.CompletedProcess([], 0, b"", b"")
            )
            result["cross_admission_probe"] = {
                "marker_names": sorted(
                    path.name for path in marker_dir.glob("*") if path.is_file()
                ),
                "returncode": denied.returncode,
                "stderr": denied.stderr.decode("utf-8", "replace"),
                "stdout": denied.stdout.decode("utf-8", "replace"),
            }
        barrier.wait(timeout=30)
        if active:
            assert candidate is not None
            _write_marker(main_root, candidate)
        barrier.wait(timeout=30)

    if candidate is not None:
        guarded = _guard(Path(str(config["worktree"])), env, guard_path)
        if guarded.returncode != 0 or guarded.stdout or guarded.stderr:
            raise AssertionError(
                "commit guard refused own candidate: "
                + guarded.stdout.decode("utf-8", "replace")
                + guarded.stderr.decode("utf-8", "replace")
            )
    barrier.wait(timeout=30)
    if config["worker_id"] == "commit-a":
        # The denial probes are test instrumentation, not session telemetry.
        # Both have completed at the barrier, so their two advisory rows can
        # be removed before the four real chains emit their own events.
        (main_root / ".forge/tmp/decisions/events.jsonl").unlink(missing_ok=True)
    barrier.wait(timeout=30)


def _commit_chain(
    config: dict[str, object],
    env: dict[str, str],
    barrier: object,
    result: dict[str, object],
) -> str:
    worktree = Path(str(config["worktree"]))
    main_root = Path(str(config["main_root"]))
    relative_path = str(config["scope"])
    _checked(["git", "add", "--", relative_path], cwd=worktree, env=env)
    staged = _git(worktree, "diff", "--cached")
    candidate = hashlib.sha256(staged).hexdigest()
    if candidate != config["candidate"]:
        raise AssertionError("commit candidate changed before authorization")
    marker = _write_marker(main_root, candidate)
    _concurrent_marker_phase(config, env, barrier, result, candidate)
    acquired = _run(
        ["bash", str(ACQUIRE_LOCK)], cwd=worktree, env=env, timeout=20
    )
    _require_ok(acquired, "commit-lock acquire")
    result["commit_lock_stderr"] = acquired.stderr.decode("utf-8", "replace")
    try:
        under_lock = hashlib.sha256(_git(worktree, "diff", "--cached")).hexdigest()
        if under_lock != candidate:
            raise AssertionError("staged bytes changed under commit lock")
        time.sleep(0.35)
        _checked(
            ["git", "commit", "--quiet", "--no-gpg-sign", "-m", str(config["worker_id"])],
            cwd=worktree,
            env=env,
        )
    finally:
        released = _run(["bash", str(RELEASE_LOCK)], cwd=worktree, env=env)
        _require_ok(released, "commit-lock release")
        marker.unlink(missing_ok=True)
    _journal_append(
        config, env, suffix="commit", criterion="gate-commit: committed candidate"
    )
    result["head"] = _git(worktree, "rev-parse", "HEAD").decode().strip()
    return candidate


def _merge_chain(
    config: dict[str, object],
    env: dict[str, str],
    barrier: object,
    merge_barrier: object,
    result: dict[str, object],
) -> str:
    worktree = Path(str(config["worktree"]))
    base = str(config["base"])
    head = str(config["candidate_head"])
    _checked(["git", "diff", "--check", f"{base}...{head}"], cwd=worktree, env=env)
    _checked(["git", "merge-base", "--is-ancestor", base, head], cwd=worktree, env=env)
    merge_diff = _git(worktree, "diff", "--binary", f"{base}...{head}")
    candidate = hashlib.sha256(merge_diff).hexdigest()
    _journal_append(config, env, suffix="gate-1", criterion="gate-1: harmless diff check")
    _journal_append(config, env, suffix="gate-2", criterion="gate-2: harmless ancestry check")
    _concurrent_marker_phase(config, env, barrier, result, None)

    common = Path(
        _git(worktree, "rev-parse", "--path-format=absolute", "--git-common-dir")
        .decode()
        .strip()
    )
    lock_path = common / "agent-rebase.lock"
    lock_path.touch(exist_ok=True)
    merge_barrier.wait(timeout=30)
    rebase_lock_enabled = bool(config.get("rebase_lock_enabled", True))
    with lock_path.open("a+b") as lock_stream:
        started = time.monotonic()
        if rebase_lock_enabled:
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX)
        result["rebase_lock_wait_s"] = time.monotonic() - started
        try:
            if _git(worktree, "rev-parse", "HEAD").decode().strip() != head:
                raise AssertionError("merge candidate HEAD changed after gates")
            integration_ref = str(config["integration_ref"])
            old = _git(worktree, "rev-parse", integration_ref).decode().strip()
            result["destination_before"] = old
            if not rebase_lock_enabled:
                # Make the disabled-control race deterministic: both real merge
                # chains bind the same destination before either update-ref.
                merge_barrier.wait(timeout=30)
            time.sleep(0.35)
            _checked(
                ["git", "-c", "commit.gpgSign=false", "rebase", old],
                cwd=worktree,
                env=env,
            )
            integrated = _git(worktree, "rev-parse", "HEAD").decode().strip()
            _checked(
                ["git", "merge-base", "--is-ancestor", old, integrated],
                cwd=worktree,
                env=env,
            )
            _checked(
                ["git", "update-ref", integration_ref, integrated, old],
                cwd=worktree,
                env=env,
            )
            result["head"] = integrated
        finally:
            if rebase_lock_enabled:
                fcntl.flock(lock_stream.fileno(), fcntl.LOCK_UN)
    _journal_append(
        config, env, suffix="merge", criterion="gate-3: fast-forward integration"
    )
    return candidate


def _complete_worker(
    config: dict[str, object],
    barrier: object,
    owner_barrier: object,
    merge_barrier: object,
) -> None:
    result: dict[str, object] = {
        "kind": config["kind"],
        "pid": os.getpid(),
        "run_id": config["run_id"],
        "worker_id": config["worker_id"],
    }
    env = os.environ.copy()
    env["FORGE_SESSION_PID"] = str(os.getpid())
    env["GIT_EDITOR"] = "true"
    env["GIT_SEQUENCE_EDITOR"] = "true"
    env["PYTHONPATH"] = str(ROOT / "scripts")
    try:
        stall_before_barrier_s = float(config.get("stall_before_barrier_s", 0))
        if stall_before_barrier_s:
            time.sleep(stall_before_barrier_s)
        barrier.wait(timeout=30)
        _journal_open(config, env)
        barrier.wait(timeout=30)
        if config["worker_id"] == "commit-a":
            owner_barrier.wait(timeout=30)
            _journal_append(
                config,
                env,
                suffix="owner-race",
                criterion="ownership: rightful writer remains admitted",
            )
        elif config["worker_id"] == "merge-a":
            owner_barrier.wait(timeout=30)
            result["foreign_owner_probe"] = _foreign_owner_probe(
                config, env, "run-commit-a"
            )
        barrier.wait(timeout=30)
        if config.get("overlap_probe"):
            result["overlap"] = _overlap_probe(config, env)
        if config["kind"] == "commit":
            candidate = _commit_chain(config, env, barrier, result)
            event = "assertion_advisory"
        else:
            candidate = _merge_chain(config, env, barrier, merge_barrier, result)
            event = "review_final_finding"
        result["candidate"] = candidate
        _write_telemetry_unit(Path(str(config["main_root"])), str(config["worker_id"]))
        emitted = _emit_event(config, env, candidate, event)
        result["event_stderr"] = emitted.stderr.decode("utf-8", "replace")
        barrier.wait(timeout=40)
        _aggregate(config, env)
        _journal_close(config, env)
        result["ok"] = True
    except BaseException:
        result["ok"] = False
        result["traceback"] = traceback.format_exc()
        try:
            barrier.abort()
        except BaseException:
            pass
    finally:
        _write_json(Path(str(config["result_path"])), result)


def _hold_commit_lock(repo: str, ready: object, release: object, result_path: str) -> None:
    env = os.environ.copy()
    env["FORGE_SESSION_PID"] = str(os.getpid())
    result: dict[str, object] = {"pid": os.getpid()}
    try:
        acquired = _run(["bash", str(ACQUIRE_LOCK)], cwd=Path(repo), env=env)
        _require_ok(acquired, "holder acquire")
        result["acquired"] = True
        ready.set()
        if not release.wait(20):
            raise AssertionError("holder release event timed out")
        released = _run(["bash", str(RELEASE_LOCK)], cwd=Path(repo), env=env)
        _require_ok(released, "holder release")
        result["released"] = True
    except BaseException:
        result["traceback"] = traceback.format_exc()
        ready.set()
    finally:
        _write_json(Path(result_path), result)


class D13ConcurrentRepositoryHarnessTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="forge-d13-concurrency-")
        self.addCleanup(self.temporary.cleanup)
        self.scratch = Path(self.temporary.name)
        self.repo = self.scratch / "main"
        self.worktrees = self.scratch / "worktrees"
        self.records = self.scratch / "records"
        self.results = self.scratch / "results"
        self.worktrees.mkdir()
        self.records.mkdir()
        self.results.mkdir()
        _checked(["git", "init", "--quiet", str(self.repo)], cwd=self.scratch)
        _git(self.repo, "config", "user.name", "Forge D13 Tests")
        _git(self.repo, "config", "user.email", "forge-d13@example.invalid")
        _git(self.repo, "symbolic-ref", "HEAD", "refs/heads/main")
        (self.repo / ".forge-manifest").write_text(
            "forge_version: 3\nplugin_ref: forge-plugin\n", encoding="utf-8"
        )
        (self.repo / "base.txt").write_text("base\n", encoding="utf-8")
        _git(self.repo, "add", ".forge-manifest", "base.txt")
        _git(self.repo, "commit", "--quiet", "--no-gpg-sign", "-m", "base")
        self.base = _git(self.repo, "rev-parse", "HEAD").decode().strip()

    def _add_worktree(self, name: str, branch: str) -> Path:
        target = self.worktrees / name
        _git(self.repo, "worktree", "add", "--quiet", "-b", branch, str(target), self.base)
        _git(target, "config", "user.name", "Forge D13 Tests")
        _git(target, "config", "user.email", "forge-d13@example.invalid")
        return target

    def _prepare_configs(self) -> list[dict[str, object]]:
        configs: list[dict[str, object]] = []
        integration_ref = "refs/heads/d13-integration"
        _git(self.repo, "update-ref", integration_ref, self.base)
        for suffix in ("a", "b"):
            worker_id = f"commit-{suffix}"
            worktree = self._add_worktree(worker_id, f"d13-{worker_id}")
            relative = f"commit/{suffix}.txt"
            path = worktree / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"{worker_id}\n", encoding="utf-8")
            _git(worktree, "add", "--", relative)
            candidate = hashlib.sha256(_git(worktree, "diff", "--cached")).hexdigest()
            configs.append(
                {
                    "base": self.base,
                    "candidate": candidate,
                    "kind": "commit",
                    "main_root": str(self.repo),
                    "overlap_probe": suffix == "a",
                    "record_dir": str(self.records),
                    "result_path": str(self.results / f"{worker_id}.json"),
                    "run_id": f"run-{worker_id}",
                    "scope": relative,
                    "worker_id": worker_id,
                    "worktree": str(worktree),
                }
            )

        for suffix in ("a", "b"):
            worker_id = f"merge-{suffix}"
            worktree = self._add_worktree(worker_id, f"d13-candidate-{suffix}")
            relative = f"merge/{suffix}.txt"
            path = worktree / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"{worker_id}\n", encoding="utf-8")
            _git(worktree, "add", "--", relative)
            _git(worktree, "commit", "--quiet", "--no-gpg-sign", "-m", worker_id)
            head = _git(worktree, "rev-parse", "HEAD").decode().strip()
            configs.append(
                {
                    "base": self.base,
                    "candidate_head": head,
                    "integration_ref": integration_ref,
                    "kind": "merge",
                    "main_root": str(self.repo),
                    "record_dir": str(self.records),
                    "result_path": str(self.results / f"{worker_id}.json"),
                    "run_id": f"run-{worker_id}",
                    "scope": relative,
                    "worker_id": worker_id,
                    "worktree": str(worktree),
                }
            )
        return configs

    def _launch_complete_workers(
        self, configs: list[dict[str, object]]
    ) -> list[multiprocessing.Process]:
        context = multiprocessing.get_context("fork")
        barrier = context.Barrier(4)
        owner_barrier = context.Barrier(2)
        merge_barrier = context.Barrier(2)
        processes = [
            context.Process(
                target=_complete_worker,
                args=(config, barrier, owner_barrier, merge_barrier),
            )
            for config in configs
        ]
        for process in processes:
            process.start()
        self.addCleanup(self._terminate_processes, processes)
        return processes

    def _terminate_processes(
        self, processes: list[multiprocessing.Process]
    ) -> None:
        for process in processes:
            if process.is_alive():
                process.terminate()
        for process in processes:
            process.join(5)

    def _assert_processes_completed(
        self,
        processes: list[multiprocessing.Process],
        alive: list[multiprocessing.Process],
        *,
        label: str,
    ) -> None:
        self.assertEqual(alive, [], f"{label} deadlocked")
        self.assertTrue(
            all(process.exitcode == 0 for process in processes),
            f"{label} child process failed",
        )

    def _load_worker_results(
        self, configs: list[dict[str, object]]
    ) -> list[dict[str, object]]:
        return [
            json.loads(Path(str(config["result_path"])).read_text(encoding="utf-8"))
            for config in configs
        ]

    def _assert_complete_worker_outcomes(
        self,
        configs: list[dict[str, object]],
        processes: list[multiprocessing.Process],
        alive: list[multiprocessing.Process],
    ) -> list[dict[str, object]]:
        self._assert_processes_completed(
            processes, alive, label="four-worker harness"
        )
        results = self._load_worker_results(configs)
        failures = [result for result in results if not result.get("ok")]
        self.assertEqual(failures, [], "four-worker harness worker failures")
        return results

    def _assert_concurrent_event_batch(
        self,
        *,
        count: int,
        emitter: Path,
        label: str,
        synchronize_after_open: bool = False,
    ) -> None:
        events = self.repo / ".forge/tmp/decisions/events.jsonl"
        events.unlink(missing_ok=True)
        open_barrier_dir = self.results / f"event-open-barrier-{label}"
        if open_barrier_dir.exists():
            shutil.rmtree(open_barrier_dir)
        candidates = {
            hashlib.sha256(f"{label}-{index}".encode()).hexdigest()
            for index in range(count)
        }
        context = multiprocessing.get_context("fork")
        barrier = context.Barrier(count)
        result_paths = [
            self.results / f"event-{label}-{index}.json" for index in range(count)
        ]
        processes = [
            context.Process(
                target=_emit_event_process,
                args=(
                    str(self.repo),
                    str(emitter),
                    self.base,
                    candidate,
                    barrier,
                    str(result_path),
                    str(open_barrier_dir) if synchronize_after_open else None,
                    count if synchronize_after_open else None,
                ),
            )
            for candidate, result_path in zip(sorted(candidates), result_paths)
        ]
        for process in processes:
            process.start()
        self.addCleanup(self._terminate_processes, processes)
        alive = _join_processes(processes, deadline_seconds=20)
        self._assert_processes_completed(
            processes, alive, label=f"{count}-event emitter harness"
        )
        emitter_results = [
            json.loads(path.read_text(encoding="utf-8")) for path in result_paths
        ]
        self.assertTrue(
            all("traceback" not in result for result in emitter_results),
            f"{label}: event emitter process raised",
        )
        self.assertEqual(
            [result.get("returncode") for result in emitter_results],
            [0] * count,
            f"{label}: event emitter primary outcome changed",
        )
        records = [
            json.loads(line)
            for line in events.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(len(records), count, f"{label}: event records lost")
        self.assertEqual(
            {record["candidate"] for record in records},
            candidates,
            f"{label}: event candidates changed",
        )

    def _assert_in_phase_marker_cross_denial(
        self, configs: list[dict[str, object]], results: list[dict[str, object]]
    ) -> None:
        expected_candidates = {
            str(config["candidate"])
            for config in configs
            if config["kind"] == "commit"
        }
        probes = [
            result["cross_admission_probe"]
            for result in results
            if result["kind"] == "commit"
        ]
        self.assertEqual(len(probes), 2)
        for probe in probes:
            self.assertEqual(probe["returncode"], 0)
            self.assertEqual(len(probe["marker_names"]), 1)
            self.assertIn(probe["marker_names"][0], expected_candidates)
            self.assertIn(
                "forge: commit not authorized — run /forge:commit (marker missing)",
                probe["stdout"],
            )

    def _assert_competing_owner_refused(
        self,
        results: list[dict[str, object]],
        *,
        expected_pid: int | None = None,
    ) -> None:
        probe = next(
            result["foreign_owner_probe"]
            for result in results
            if "foreign_owner_probe" in result
        )
        if expected_pid is None:
            expected_pid = int(next(
                result for result in results if result["worker_id"] == "commit-a"
            )["pid"])
        self.assertEqual(probe["returncode"], 1)
        self.assertFalse(probe["foreign_record_present"])
        self.assertIn(
            f"forge: journal append refused — run run-commit-a has live owner "
            f"{expected_pid}@{socket.gethostname()}",
            probe["stderr"],
        )

    def _assert_shared_destination_chain(
        self, configs: list[dict[str, object]], results: list[dict[str, object]]
    ) -> None:
        merge_results = [result for result in results if result["kind"] == "merge"]
        first = next(
            result for result in merge_results if result["destination_before"] == self.base
        )
        second_candidates = [
            result for result in merge_results if result["destination_before"] != self.base
        ]
        self.assertEqual(len(second_candidates), 1)
        second = second_candidates[0]
        self.assertEqual(second["destination_before"], first["head"])
        final_destination = _git(
            self.repo, "rev-parse", "refs/heads/d13-integration"
        ).decode().strip()
        self.assertEqual(final_destination, second["head"])
        for result in merge_results:
            self.assertEqual(
                _git(self.repo, "merge-base", "--is-ancestor", str(result["head"]), final_destination),
                b"",
            )
        self.assertEqual(
            {config["integration_ref"] for config in configs if config["kind"] == "merge"},
            {"refs/heads/d13-integration"},
        )

    def _assert_journal_identity(self, run_id: str) -> None:
        records = [
            json.loads(line)
            for line in (
                self.repo / ".codex-orchestrator/runs" / run_id / "journal.jsonl"
            ).read_text(encoding="utf-8").splitlines()
        ]
        self.assertTrue(all(record.get("run_id") == run_id for record in records))

    def test_two_commit_chains_and_two_merges_are_simultaneous_and_lossless(self) -> None:
        """FR-190..FR-194 and DM-006/DM-010/DM-011: run the complete concurrency harness."""
        configs = self._prepare_configs()
        processes = self._launch_complete_workers(configs)
        alive = _join_processes(processes)
        results = self._assert_complete_worker_outcomes(configs, processes, alive)
        expected_candidates = {
            str(config["candidate"])
            for config in configs
            if config["kind"] == "commit"
        }
        for result in results:
            self.assertEqual(set(result["markers_at_barrier"]), expected_candidates)
        self._assert_in_phase_marker_cross_denial(configs, results)
        self._assert_competing_owner_refused(results)
        self._assert_shared_destination_chain(configs, results)

        overlap = next(result["overlap"] for result in results if "overlap" in result)
        self.assertEqual(overlap["returncode"], 1)
        self.assertIn("run-overlap", overlap["stderr"])
        self.assertIn("run-commit-a", overlap["stderr"])
        self.assertFalse(
            (self.repo / ".codex-orchestrator/runs/run-overlap").exists()
        )
        self.assertTrue(
            any("another session is committing" in result.get("commit_lock_stderr", "") for result in results)
        )
        merge_waits = [
            float(result["rebase_lock_wait_s"])
            for result in results
            if result["kind"] == "merge"
        ]
        self.assertGreater(max(merge_waits), 0.20)

        for config, result in zip(configs, results):
            run_id = str(config["run_id"])
            run_dir = self.repo / ".codex-orchestrator/runs" / run_id
            owner_lines = (run_dir / "owner").read_text(encoding="utf-8").splitlines()
            self.assertEqual(owner_lines[0], f"pid: {result['pid']}")
            self.assertEqual(owner_lines[1], f"host: {socket.gethostname()}")
            self.assertRegex(owner_lines[2], r"^started_at: .+Z$")
            records = [
                json.loads(line)
                for line in (run_dir / "journal.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertGreaterEqual(len(records), 3)
            self.assertEqual(records[0]["type"], "run_started")
            self.assertEqual(records[-1]["type"], "run_closed")
            self._assert_journal_identity(run_id)
            if config["kind"] == "commit":
                self.assertEqual(
                    _git(Path(str(config["worktree"])), "show", "--format=", "--name-only", "HEAD")
                    .decode()
                    .strip(),
                    str(config["scope"]),
                )
            else:
                self.assertTrue(result["head"])

        authorized = self.repo / ".forge/tmp/authorized"
        self.assertEqual(list(authorized.glob("*")), [])
        event_records = [
            json.loads(line)
            for line in (self.repo / ".forge/tmp/decisions/events.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        self.assertEqual(len(event_records), 4)
        self.assertEqual(
            {record["candidate"] for record in event_records},
            {str(result["candidate"]) for result in results},
        )

        with (self.repo / ".forge/tmp/telemetry.csv").open(
            encoding="utf-8", newline=""
        ) as stream:
            rows = list(csv.reader(stream, strict=True))
        header = rows[0]
        self.assertEqual(len(header), 23)
        self.assertEqual(sum(row == header for row in rows), 1)
        self.assertTrue(all(len(row) == 23 for row in rows))
        blocks = [(session, list(group)) for session, group in itertools.groupby(rows[1:], lambda row: row[0])]
        self.assertEqual(len(blocks), 4)
        self.assertEqual(
            {session for session, _ in blocks},
            {f"session-{config['worker_id']}" for config in configs},
        )
        expected_units = {f"unit-{config['worker_id']}" for config in configs}
        for _session, block in blocks:
            self.assertEqual(len(block), 5)
            self.assertEqual({row[1] for row in block[:-1]}, expected_units)
            self.assertEqual(block[-1][1], "__decision_totals__")
            self.assertEqual(block[-1][header.index("assertion_advisory")], "2")
            self.assertEqual(block[-1][header.index("review_final_findings")], "2")

    def test_decision_event_appends_are_lossless_at_four_and_eight_sessions(self) -> None:
        """FR-157: preserve all event appends across four and eight concurrent sessions."""
        for count in (4, 8):
            with self.subTest(count=count):
                self._assert_concurrent_event_batch(
                    count=count,
                    emitter=EMIT_EVENT,
                    label=f"intact-{count}",
                )

    def test_lossless_event_sensor_kills_non_appending_emitter_copy(self) -> None:
        """FR-157: prove the losslessness sensor rejects a non-appending emitter."""
        mutant_root = self.scratch / "event-mutant"
        shutil.copytree(FORGE_SCRIPTS, mutant_root / "scripts" / "forge")
        mutant = mutant_root / "scripts" / "forge" / "emit-decision-event.py"
        source = mutant.read_text(encoding="utf-8")
        append_open = (
            '                    descriptor = os.open(\n'
            '                        decisions / "events.jsonl",\n'
            "                        os.O_WRONLY | os.O_APPEND | os.O_CREAT,\n"
            "                        0o600,\n"
            "                    )\n"
        )
        non_appending_open = append_open.replace(" | os.O_APPEND", "")
        self.assertEqual(source.count(append_open), 1)
        mutant.write_text(
            source.replace(append_open, non_appending_open), encoding="utf-8"
        )

        with self.assertRaisesRegex(AssertionError, "event records lost"):
            self._assert_concurrent_event_batch(
                count=4,
                emitter=mutant,
                label="no-o-append-mutant",
                synchronize_after_open=True,
            )

        records = [
            json.loads(line)
            for line in (
                self.repo / ".forge/tmp/decisions/events.jsonl"
            ).read_text(encoding="utf-8").splitlines()
        ]
        self.assertLess(len(records), 4)

        self._assert_concurrent_event_batch(
            count=4,
            emitter=EMIT_EVENT,
            label="restored-o-append",
            synchronize_after_open=True,
        )

    def test_deadlock_deadline_sensor_terminates_stuck_real_workers(self) -> None:
        """FR-194: prove the harness detects and terminates deadlocked workers."""
        configs = self._prepare_configs()
        configs[0]["stall_before_barrier_s"] = 5
        processes = self._launch_complete_workers(configs)
        started = time.monotonic()
        alive = _join_processes(processes, deadline_seconds=0.5)
        elapsed = time.monotonic() - started

        self.assertTrue(alive, "stuck-worker control did not reach the deadline")
        with self.assertRaisesRegex(AssertionError, "deadlocked"):
            self._assert_complete_worker_outcomes(configs, processes, alive)
        self.assertTrue(all(not process.is_alive() for process in processes))
        self.assertLess(elapsed, 3, "short deadlock deadline was not enforced")

    def test_live_commit_lock_contention_fails_closed_and_mutant_is_detected(self) -> None:
        """FR-055/FR-194: prove lock contention fails closed and is mutation-sensitive."""
        context = multiprocessing.get_context("fork")
        ready = context.Event()
        release = context.Event()
        result_path = self.results / "lock-holder.json"
        holder = context.Process(
            target=_hold_commit_lock,
            args=(str(self.repo), ready, release, str(result_path)),
        )
        holder.start()
        self.assertTrue(ready.wait(15), "lock holder did not initialize")
        env = os.environ.copy()
        env["FORGE_SESSION_PID"] = str(os.getpid())
        env["FORGE_COMMIT_LOCK_TIMEOUT"] = "1"
        refused = _run(["bash", str(ACQUIRE_LOCK)], cwd=self.repo, env=env, timeout=10)
        self.assertEqual(refused.returncode, 1)
        self.assertIn("failed to acquire commit lock", refused.stderr.decode())
        lock_path = self.repo / ".forge/tmp/commit-lock"
        original_owner = lock_path.read_bytes()

        mutant = self.scratch / "lock-mutant" / "acquire-commit-lock.sh"
        mutant.parent.mkdir()
        shutil.copy2(ACQUIRE_LOCK, mutant)
        source = mutant.read_text(encoding="utf-8")
        needle = 'if (set -o noclobber; create_lock "$lock_file") 2>/dev/null; then\n        return 0'
        replacement = "if true; then\n        return 0"
        self.assertEqual(source.count(needle), 1)
        mutant.write_text(source.replace(needle, replacement), encoding="utf-8")
        bypassed = _run(["bash", str(mutant)], cwd=self.repo, env=env, timeout=10)
        self.assertEqual(bypassed.returncode, 0, bypassed.stderr.decode())
        self.assertEqual(lock_path.read_bytes(), original_owner)

        release.set()
        holder.join(15)
        if holder.is_alive():
            holder.terminate()
            holder.join(5)
        self.assertEqual(holder.exitcode, 0)
        holder_result = json.loads(result_path.read_text(encoding="utf-8"))
        self.assertNotIn("traceback", holder_result)
        self.assertTrue(holder_result["released"])

    def test_cross_admission_sensor_kills_disabled_guard_copy(self) -> None:
        """FR-190/FR-194 and DM-006: prove marker cross-admission is detected."""
        configs = self._prepare_configs()
        commits = [config for config in configs if config["kind"] == "commit"]
        marker = _write_marker(self.repo, str(commits[0]["candidate"]))
        self.addCleanup(marker.unlink, missing_ok=True)
        env = os.environ.copy()
        env["FORGE_SESSION_PID"] = str(os.getpid())
        intact = _guard(Path(str(commits[1]["worktree"])), env)
        self.assertIn("(marker missing)", intact.stdout.decode("utf-8", "replace"))

        mutant_root = self.scratch / "guard-mutant"
        shutil.copytree(FORGE_SCRIPTS, mutant_root / "scripts" / "forge")
        mutant = mutant_root / "scripts" / "forge" / "commit-guard.sh"
        source = mutant.read_text(encoding="utf-8")
        needle = '''marker_state = (
            marker_failure(context, classifier, candidate)
            if candidate
            else "marker hash mismatch"
        )'''
        self.assertEqual(source.count(needle), 1)
        mutant.write_text(source.replace(needle, "marker_state = None"), encoding="utf-8")
        bypassed = _guard(Path(str(commits[1]["worktree"])), env, mutant)
        self.assertEqual(bypassed.returncode, 0, bypassed.stderr.decode())
        self.assertEqual(bypassed.stdout, b"")

    def test_competing_owner_sensor_kills_disabled_ownership_copy(self) -> None:
        """FR-191/FR-194 and DM-010: prove competing journal ownership is detected."""
        config = self._prepare_configs()[0]
        config["run_id"] = "run-owner-mutant"
        env = os.environ.copy()
        env["FORGE_SESSION_PID"] = str(os.getpid())
        _journal_open(config, env)

        foreign = dict(config)
        foreign["worker_id"] = "foreign-mutant"
        foreign_env = dict(env)
        foreign_env["FORGE_SESSION_PID"] = str(os.getpid() + 100000)
        intact = _foreign_owner_probe(foreign, foreign_env, "run-owner-mutant")
        self.assertEqual(intact["returncode"], 1)
        self.assertFalse(intact["foreign_record_present"])

        mutant_root = self.scratch / "owner-mutant"
        shutil.copytree(ROOT / "scripts" / "codex_orchestrator", mutant_root / "codex_orchestrator")
        (mutant_root / "forge").mkdir()
        shutil.copy2(
            ROOT / "scripts/forge/commitment_paths.py",
            mutant_root / "forge/commitment_paths.py",
        )
        shutil.copy2(ORCH_TOOLS, mutant_root / "codex_orch_tools.py")
        mutant_journal = mutant_root / "codex_orchestrator" / "journal.py"
        source = mutant_journal.read_text(encoding="utf-8")
        needle = "    _ensure_owner(run_dir, run_id, current)\n"
        self.assertEqual(source.count(needle), 1)
        mutant_journal.write_text(source.replace(needle, "    # ownership disabled by mutant\n"), encoding="utf-8")
        foreign["orch_tools"] = str(mutant_root / "codex_orch_tools.py")
        mutant_env = dict(foreign_env)
        mutant_env["PYTHONPATH"] = str(mutant_root)
        bypassed = _foreign_owner_probe(foreign, mutant_env, "run-owner-mutant")
        sensor_result = dict(bypassed)
        sensor_result["stderr"] = sensor_result["stderr"].replace(
            "run-owner-mutant", "run-commit-a"
        )
        with self.assertRaises(AssertionError):
            self._assert_competing_owner_refused(
                [{"foreign_owner_probe": sensor_result}], expected_pid=os.getpid()
            )

    def test_shared_destination_sensor_kills_split_destination_mutant(self) -> None:
        """FR-062/FR-194: prove concurrent merges share one guarded destination."""
        configs = self._prepare_configs()
        for config in configs:
            if config["kind"] == "merge":
                config["rebase_lock_enabled"] = False

        processes = self._launch_complete_workers(configs)
        alive = _join_processes(processes)
        with self.assertRaisesRegex(AssertionError, "worker failures"):
            self._assert_complete_worker_outcomes(configs, processes, alive)

        results = self._load_worker_results(configs)
        merge_results = [result for result in results if result["kind"] == "merge"]
        self.assertEqual(
            [result.get("destination_before") for result in merge_results],
            [self.base, self.base],
        )
        self.assertTrue(
            any(
                "update-ref" in str(result.get("traceback", ""))
                for result in merge_results
            ),
            "disabled real rebase lock did not lose the guarded destination update",
        )

    def test_journal_identity_sensor_kills_disabled_identity_copy(self) -> None:
        """FR-191/FR-194: prove cross-run journal identities are rejected and detected."""
        config = self._prepare_configs()[0]
        config["run_id"] = "run-identity-mutant"
        env = os.environ.copy()
        env["FORGE_SESSION_PID"] = str(os.getpid())
        _journal_open(config, env)
        record = Path(str(config["record_dir"])) / "wrong-identity.json"
        _write_json(
            record,
            {
                "criterion": "identity sensor",
                "id": "wrong-identity",
                "result": "passed",
                "run_id": "another-run",
                "type": "verification",
            },
        )
        arguments = (
            "journal-append", "--repo", str(config["worktree"]), "--run-id",
            str(config["run_id"]), "--record-json", str(record),
        )
        intact = _orch(config, env, *arguments)
        self.assertEqual(intact.returncode, 1)
        self.assertIn("run identity mismatch", intact.stderr.decode())
        self._assert_journal_identity(str(config["run_id"]))

        mutant_root = self.scratch / "identity-mutant"
        shutil.copytree(ROOT / "scripts/codex_orchestrator", mutant_root / "codex_orchestrator")
        (mutant_root / "forge").mkdir()
        shutil.copy2(
            ROOT / "scripts/forge/commitment_paths.py",
            mutant_root / "forge/commitment_paths.py",
        )
        shutil.copy2(ORCH_TOOLS, mutant_root / "codex_orch_tools.py")
        mutant_journal = mutant_root / "codex_orchestrator/journal.py"
        source = mutant_journal.read_text(encoding="utf-8")
        needle = (
            '    if "run_id" in record and record.get("run_id") != run_id:\n'
            '        raise CoordinationRefusal("forge: journal append refused — run identity mismatch")\n'
        )
        self.assertEqual(source.count(needle), 1)
        mutant_journal.write_text(
            source.replace(needle, "    # run identity control disabled by mutant\n"),
            encoding="utf-8",
        )
        mutant_config = dict(config)
        mutant_config["orch_tools"] = str(mutant_root / "codex_orch_tools.py")
        mutant_env = dict(env)
        mutant_env["PYTHONPATH"] = str(mutant_root)
        bypassed = _orch(mutant_config, mutant_env, *arguments)
        self.assertEqual(bypassed.returncode, 0, bypassed.stderr.decode())
        with self.assertRaises(AssertionError):
            self._assert_journal_identity(str(config["run_id"]))


if __name__ == "__main__":
    unittest.main()
