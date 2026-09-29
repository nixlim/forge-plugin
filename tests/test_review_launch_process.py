"""Real-process coverage for review attempt identity and process-group recovery."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests import test_review_lane_commit as commit_lane
from tests._cli_loader import package_module
from tests._review_lane_support import ReviewLaneSupport

ATTEMPT = package_module("engine._review_attempt")
ATTEMPT_PROC = package_module("engine._review_attempt_proc")
ENGINE = package_module("engine")
LAUNCH = package_module("engine._review_launch")
LANE_API = package_module("engine._review_lane_api")
WRAPPER = package_module("engine._review_wrapper")
REQUEST = package_module("engine._verbs_review_request")
ATTEMPT_ID = "attempt-0123456789abcdef"


class ReviewLaunchIsolationTests(ReviewLaneSupport, unittest.TestCase):
    def test_prepared_launcher_binds_isolation_source_limits_and_exact_env(self) -> None:
        paths = self.paths()
        route = LAUNCH.ReviewRoute(
            "review-cheap", "codex", "gpt-5.6-sol", "high",
            "committed-default", "a" * 64, "read-only",
        )
        environment = {"PATH": "/usr/bin:/bin", "USER": "forge-user"}

        def digest(argv) -> str:
            return hashlib.sha256(json.dumps(list(argv)).encode()).hexdigest()

        context = SimpleNamespace(command_digest=digest)
        with (
            mock.patch.object(
                LAUNCH, "allowed_environment",
                return_value=(environment, tuple(sorted(environment)), ()),
            ),
            mock.patch.object(LAUNCH, "probe_provider_version", return_value="0.155.0"),
            mock.patch.object(LAUNCH, "reviewer_argv", return_value=["/provider"]),
        ):
            launch = LAUNCH.prepare_review_launch(
                context, None, paths, route, b"fixture prompt"
            )
        self.assertEqual(launch.launcher_argv[1:3], ("-I", "-c"))
        self.assertEqual(launch.launcher_argv[3], WRAPPER.wrapper_source())
        self.assertLess(len(launch.launcher_argv[3].encode()), 131_072)
        config = json.loads(launch.config_json)
        self.assertEqual((config["timeout"], config["grace"]), (2400, 5))
        self.assertEqual(config["role_body_digest"], paths.role_body_digest)
        self.assertNotIn("leaves", config)
        self.assertNotIn("events_existing", config)
        self.assertEqual(launch.launcher_argv_digest, digest(launch.launcher_argv))
        changed = list(launch.launcher_argv)
        changed[3] += "\n"
        self.assertNotEqual(digest(changed), launch.launcher_argv_digest)
        with mock.patch.object(LANE_API.subprocess, "Popen", return_value=object()) as popen:
            LAUNCH.launch_review_wrapper(launch)
        self.assertEqual(popen.call_args.kwargs["env"], environment)
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        self.assertEqual(popen.call_args.kwargs["pass_fds"], (launch.attempt_fd,))

    def test_commit_spawn_value_error_publishes_and_clears_launch_failure(self) -> None:
        state = commit_lane.reviewing(None)
        state.update(paths=[], tier={"effective": "standard"})
        state["candidate"].update(base_commit_oid="6" * 40)
        store = commit_lane._Store()
        fake = commit_lane.request_engine(state, store)
        route = LAUNCH.ReviewRoute(
            "review-cheap", "codex", "gpt-5.6-sol", "high",
            "committed-default", "5" * 64, "read-only",
        )
        launch = SimpleNamespace(request_fields=lambda: commit_lane.new_request())
        canary = "/home/agents/private-review-path"
        published: list[dict[str, object]] = []
        with (
            mock.patch.object(REQUEST, "_mechanical_complete", return_value=True),
            mock.patch.object(LAUNCH, "resolve_review_route", return_value=route),
            mock.patch.object(
                LAUNCH, "prepare_review_paths",
                return_value=SimpleNamespace(attempt=commit_lane.ATTEMPT_ID),
            ),
            mock.patch.object(LAUNCH, "prepare_review_launch", return_value=launch),
            mock.patch.object(LAUNCH, "launch_review_wrapper", side_effect=OSError(2, canary)),
            mock.patch.object(REQUEST, "_write_artifact", return_value="package"),
            mock.patch.object(REQUEST, "_review_prompt", return_value=b"prompt"),
            mock.patch.object(REQUEST, "_review_package_is_oversized", return_value=False),
            mock.patch.object(
                REQUEST, "_attempt_fd", return_value=nullcontext((9, "completion"))
            ),
            mock.patch.object(
                ATTEMPT, "publish_terminal_completion",
                side_effect=lambda _fd, record: published.append(record) is None,
            ),
            self.assertRaises(ENGINE.Refusal) as caught,
        ):
            REQUEST.review_request(fake)
        self.assertEqual(caught.exception.message, "review launch failed: errno 2")
        self.assertEqual(published[0]["error"], "launch-failed: errno 2")
        self.assertEqual(state["review"]["request"]["cleared"]["outcome"], "launch-failed: errno 2")
        recorded = (published, state, caught.exception.message, caught.exception.observed)
        self.assertNotIn(canary, json.dumps(recorded))

    def test_commit_launch_preparation_refuses_before_owner_event(self) -> None:
        state = commit_lane.reviewing(None)
        state.update(paths=[], tier={"effective": "standard"})
        state["candidate"].update(base_commit_oid="6" * 40)
        store = commit_lane._Store()
        fake = commit_lane.request_engine(state, store)
        route = LAUNCH.ReviewRoute(
            "review-cheap", "codex", "gpt-5.6-sol", "high",
            "committed-default", "5" * 64, "read-only",
        )
        refusal = ENGINE.Refusal(
            ENGINE.ReasonCode.EVIDENCE_INCOMPLETE,
            "forge: review request refused — codex version probe failed with exit 9",
        )
        with (
            mock.patch.object(REQUEST, "_mechanical_complete", return_value=True),
            mock.patch.object(LAUNCH, "resolve_review_route", return_value=route),
            mock.patch.object(
                LAUNCH, "prepare_review_paths",
                return_value=SimpleNamespace(attempt=commit_lane.ATTEMPT_ID),
            ),
            mock.patch.object(LAUNCH, "prepare_review_launch", side_effect=refusal),
            mock.patch.object(REQUEST, "_write_artifact", return_value="package"),
            mock.patch.object(REQUEST, "_review_prompt", return_value=b"prompt"),
            self.assertRaises(ENGINE.Refusal),
        ):
            REQUEST.review_request(fake)
        self.assertEqual(store.events, [])


def wait_path(path: Path, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.01)
    raise AssertionError(f"timed out waiting for {path}")


def wait_gone(pid: int, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if ATTEMPT_PROC.process_snapshot(pid).get("status") in {"gone", "zombie"}:
            return
        time.sleep(0.02)
    raise AssertionError(f"PID {pid} survived process-group termination")


def request() -> dict[str, object]:
    return {
        "attempt": ATTEMPT_ID,
        "provider": "claude",
        "sandbox": "instruction-bounded",
        "route": {
            "provider": "claude",
            "model": "test-model",
            "effort": "high",
            "route_source": "committed-default",
            "route_sha256": "1" * 64,
        },
        "argv_digest": "2" * 64,
        "prompt_digest": "3" * 64,
        "environment_names": [],
        "omitted_short": [],
    }


@unittest.skipUnless(sys.platform.startswith("linux"), "real /proc process-group tests need Linux")
class ReviewProcessGroupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="forge-review-process-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.processes: list[subprocess.Popen[bytes]] = []
        self.groups: set[int] = set()
        self.addCleanup(self.cleanup_processes)

    def cleanup_processes(self) -> None:
        for pgid in self.groups:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        for process in self.processes:
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)

    def spawn_group(self, source: str, *arguments: str) -> subprocess.Popen[bytes]:
        process = subprocess.Popen(
            [sys.executable, "-I", "-c", source, *arguments],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        self.processes.append(process)
        self.groups.add(process.pid)
        return process

    def identity_for(self, wrapper_pid: int, reviewer_pid: int) -> dict[str, object]:
        wrapper_birth = WRAPPER.birth_identity(wrapper_pid)
        reviewer_birth = WRAPPER.birth_identity(reviewer_pid)
        self.assertIsNotNone(wrapper_birth)
        self.assertIsNotNone(reviewer_birth)
        return {
            "schema": WRAPPER.IDENTITY_SCHEMA,
            "attempt": ATTEMPT_ID,
            "wrapper_pid": wrapper_pid,
            "pgid": wrapper_pid,
            "wrapper_birth": wrapper_birth,
            "reviewer_pid": reviewer_pid,
            "reviewer_birth": reviewer_birth,
            "started_at": "2026-09-27T12:00:00Z",
        }

    def prepare_wrapper(
        self, name: str, provider_argv: list[str], timeout: float = 5.0
    ) -> tuple[Path, int, dict[str, object]]:
        provider_argv = [*provider_argv, "--tools", "Read"]
        attempt_dir = self.root / name
        attempt_dir.mkdir(mode=0o700)
        prompt = b"candidate: " + b"1" * 64 + b"\npackage: " + b"2" * 64 + b"\n"
        prompt_path = attempt_dir / "prompt.txt"
        prompt_path.write_bytes(prompt)
        prompt_path.chmod(0o600)
        descriptor = os.open(attempt_dir, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        self.addCleanup(os.close, descriptor)
        config = {
            "attempt": ATTEMPT_ID,
            "argv": provider_argv,
            "argv_digest": WRAPPER._canonical_digest(provider_argv),
            "prompt_digest": hashlib.sha256(prompt).hexdigest(),
            "provider": "claude",
            "route_source": "committed-default",
            "route_sha256": "1" * 64,
            "sandbox": "instruction-bounded",
            "timeout": timeout,
            "grace": 0.2,
            "environment_names": [],
            "omitted_short": [],
        }
        return attempt_dir, descriptor, config

    def launch_wrapper(
        self, descriptor: int, config: dict[str, object], *, cwd: Path | None = None
    ) -> subprocess.Popen[bytes]:
        process = subprocess.Popen(
            [
                sys.executable,
                "-I",
                "-c",
                WRAPPER.wrapper_source(),
                str(descriptor),
                json.dumps(config, sort_keys=True, separators=(",", ":")),
            ],
            pass_fds=(descriptor,),
            start_new_session=True,
            cwd=cwd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.processes.append(process)
        self.groups.add(process.pid)
        return process

    def test_term_reaches_descriptor_dropping_grandchild(self) -> None:
        marker = self.root / "grandchild.pid"
        source = """
import os, pathlib, subprocess, sys, time
child = subprocess.Popen(
    [sys.executable, '-I', '-c', 'import time; time.sleep(300)'], close_fds=True
)
p=sys.argv[1];q=p+'~';pathlib.Path(q).write_text(str(child.pid),encoding='ascii');os.replace(q,p)
time.sleep(300)
"""
        leader = self.spawn_group(source, str(marker))
        wait_path(marker)
        child_pid = int(marker.read_text(encoding="ascii"))
        owner = self.identity_for(leader.pid, child_pid)

        result = ATTEMPT.terminate_owned_group(owner, 0.2, 3.0)

        self.assertEqual(result.outcome, "cancelled")
        leader.wait(timeout=5)
        wait_gone(child_pid)
        self.groups.discard(leader.pid)

    def test_dead_leader_live_reviewer_is_still_owned_and_cancelled(self) -> None:
        marker = self.root / "reviewer.pid"
        release = self.root / "release"
        source = """
import os, pathlib, subprocess, sys, time
child = subprocess.Popen([sys.executable, '-I', '-c', 'import time; time.sleep(300)'])
p=sys.argv[1];q=p+'~';pathlib.Path(q).write_text(str(child.pid),encoding='ascii');os.replace(q,p)
while not pathlib.Path(sys.argv[2]).exists():
    time.sleep(0.01)
"""
        leader = self.spawn_group(source, str(marker), str(release))
        wait_path(marker)
        child_pid = int(marker.read_text(encoding="ascii"))
        owner = self.identity_for(leader.pid, child_pid)
        release.write_text("exit", encoding="ascii")
        leader.wait(timeout=5)

        proof = ATTEMPT.prove_group_ownership(owner)
        result = ATTEMPT.terminate_owned_group(owner, 0.2, 3.0)

        self.assertEqual((proof.outcome, result.outcome), ("reviewer-alive", "cancelled"))
        wait_gone(child_pid)
        self.groups.discard(leader.pid)

    def test_both_recorded_processes_gone_is_wrapper_lost(self) -> None:
        marker = self.root / "short-child.pid"
        release = self.root / "short-release"
        source = """
import os, pathlib, subprocess, sys, time
child = subprocess.Popen([sys.executable, '-I', '-c', 'import time; time.sleep(0.2)'])
p=sys.argv[1];q=p+'~';pathlib.Path(q).write_text(str(child.pid),encoding='ascii');os.replace(q,p)
while not pathlib.Path(sys.argv[2]).exists():
    time.sleep(0.01)
"""
        leader = self.spawn_group(source, str(marker), str(release))
        wait_path(marker)
        child_pid = int(marker.read_text(encoding="ascii"))
        owner = self.identity_for(leader.pid, child_pid)
        release.write_text("exit", encoding="ascii")
        leader.wait(timeout=5)
        wait_gone(child_pid)

        proof = ATTEMPT.prove_group_ownership(owner)

        self.assertEqual(proof.outcome, "group-empty")
        self.groups.discard(leader.pid)

    def test_real_pre_identity_death_becomes_abandoned(self) -> None:
        attempt_dir = self.root / "attempt"
        attempt_dir.mkdir(mode=0o700)
        descriptor = os.open(attempt_dir, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        self.addCleanup(os.close, descriptor)
        would_be_parent = self.spawn_group("import time; time.sleep(300)")
        os.killpg(would_be_parent.pid, signal.SIGKILL)
        would_be_parent.wait(timeout=5)
        self.groups.discard(would_be_parent.pid)
        deadline = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)

        observed = ATTEMPT.observe_attempt(
            descriptor, ATTEMPT_ID, deadline, dt.datetime.now(dt.timezone.utc)
        )
        won, completion = ATTEMPT.claim_abandoned(descriptor, request())

        self.assertEqual((observed.outcome, won), ("abandonable", True))
        self.assertEqual(completion["error"], "abandoned")

    def test_wrapper_publishes_identity_before_reviewer_first_instruction(self) -> None:
        attempt_dir = self.root / "wrapper-attempt"
        marker = self.root / "provider-saw-identity"
        provider_source = """
import json, pathlib, sys
attempt = pathlib.Path(sys.argv[1])
if not (attempt / 'identity.json').is_file():
    raise SystemExit(23)
pathlib.Path(sys.argv[2]).write_text('identity-first', encoding='ascii')
sys.stdin.read()
print(json.dumps({'type':'system','subtype':'init','model':'test-model',
                  'permissionMode':'default','tools':['Read']}), flush=True)
print(json.dumps({'type':'result','is_error':False,'result':'VERDICT: PASS'}), flush=True)
"""
        provider_argv = [
            sys.executable,
            "-I",
            "-c",
            provider_source,
            str(attempt_dir),
            str(marker),
        ]
        _attempt_dir, descriptor, config = self.prepare_wrapper(
            "wrapper-attempt", provider_argv
        )
        wrapper = self.launch_wrapper(descriptor, config)

        wrapper.wait(timeout=10)
        self.groups.discard(wrapper.pid)

        self.assertEqual(wrapper.returncode, 0)
        self.assertEqual(marker.read_text(encoding="ascii"), "identity-first")
        identity_record = ATTEMPT.read_identity(descriptor, ATTEMPT_ID)
        self.assertEqual((identity_record["wrapper_pid"], identity_record["pgid"]),
                         (wrapper.pid, wrapper.pid))

    def test_wrapper_losing_identity_claim_starts_no_reviewer(self) -> None:
        marker = self.root / "lost-claim-reviewer-started"
        provider_argv = [
            sys.executable,
            "-I",
            "-c",
            "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('started')",
            str(marker),
        ]
        _attempt, descriptor, config = self.prepare_wrapper("lost-claim", provider_argv)
        claim = {
            "schema": WRAPPER.IDENTITY_SCHEMA,
            "attempt": ATTEMPT_ID,
            "wrapper_pid": None,
            "pgid": None,
            "wrapper_birth": None,
            "reviewer_pid": None,
            "reviewer_birth": None,
            "started_at": "2026-09-27T12:00:00Z",
        }
        self.assertTrue(WRAPPER.exclusive_publish(descriptor, "identity.json", claim))

        wrapper = self.launch_wrapper(descriptor, config)
        wrapper.wait(timeout=5)
        self.groups.discard(wrapper.pid)

        self.assertEqual((wrapper.returncode, marker.exists()), (0, False))
        self.assertEqual(ATTEMPT.read_identity(descriptor, ATTEMPT_ID), claim)
        self.assertIsNone(ATTEMPT.read_completion(descriptor, ATTEMPT_ID))

    def test_isolated_wrapper_ignores_repo_root_json_shadow(self) -> None:
        shadow = self.root / "shadow"
        shadow.mkdir()
        marker = self.root / "shadow-imported"
        (shadow / "json.py").write_text(
            f"open({str(marker)!r}, 'w').write('shadowed')\n", encoding="utf-8"
        )
        subprocess.run([sys.executable, "-c", "import json"], cwd=shadow, check=True)
        self.assertTrue(marker.exists(), "disable leg must import the planted module")
        marker.unlink()
        source = """
import sys
sys.stdin.read()
print('{"type":"system","subtype":"init","model":"test-model",'
      '"permissionMode":"default","tools":["Read"]}', flush=True)
print('{"type":"result","is_error":false,"result":"VERDICT: PASS"}', flush=True)
"""
        provider_argv = [sys.executable, "-I", "-c", source]
        _attempt, descriptor, config = self.prepare_wrapper("isolated", provider_argv)

        wrapper = self.launch_wrapper(descriptor, config, cwd=shadow)
        wrapper.wait(timeout=10)
        self.groups.discard(wrapper.pid)

        self.assertFalse(marker.exists())
        self.assertIsNotNone(ATTEMPT.read_completion(descriptor, ATTEMPT_ID))

    def test_timeout_leaves_no_normal_or_descriptor_dropping_grandchild(self) -> None:
        source = """
import os, pathlib, subprocess, sys, time
drop = sys.argv[2] == 'drop'
child = subprocess.Popen(
    [sys.executable, '-I', '-c', 'import time; time.sleep(300)'], close_fds=drop
)
p=sys.argv[1];q=p+'~';pathlib.Path(q).write_text(str(child.pid),encoding='ascii');os.replace(q,p)
time.sleep(300)
"""
        for mode in ("normal", "drop"):
            with self.subTest(mode=mode):
                marker = self.root / f"timeout-{mode}.pid"
                argv = [sys.executable, "-I", "-c", source, str(marker), mode]
                _attempt, descriptor, config = self.prepare_wrapper(
                    f"timeout-{mode}", argv, timeout=0.2
                )
                wrapper = self.launch_wrapper(descriptor, config)
                wait_path(marker)
                wrapper.wait(timeout=10)
                self.groups.discard(wrapper.pid)
                identity_record = ATTEMPT.read_identity(descriptor, ATTEMPT_ID)
                completion = ATTEMPT.read_completion(descriptor, ATTEMPT_ID)
                self.assertEqual((completion["timed_out"], completion["error"]), (True, None))
                wait_gone(int(identity_record["reviewer_pid"]))
                wait_gone(int(marker.read_text(encoding="ascii")))

    def test_wrapper_killed_after_spawn_then_cancel_empties_group(self) -> None:
        marker = self.root / "cancel-grandchild.pid"
        source = """
import os, pathlib, subprocess, sys, time
child = subprocess.Popen([sys.executable, '-I', '-c', 'import time; time.sleep(300)'])
p=sys.argv[1];q=p+'~';pathlib.Path(q).write_text(str(child.pid),encoding='ascii');os.replace(q,p)
time.sleep(300)
"""
        argv = [sys.executable, "-I", "-c", source, str(marker)]
        _attempt, descriptor, config = self.prepare_wrapper("cancel", argv, timeout=30.0)
        wrapper = self.launch_wrapper(descriptor, config)
        wait_path(marker)
        identity_record = ATTEMPT.read_identity(descriptor, ATTEMPT_ID)
        self.assertIsNotNone(identity_record["reviewer_pid"])
        os.kill(wrapper.pid, signal.SIGKILL)
        wrapper.wait(timeout=5)

        proof = ATTEMPT.prove_group_ownership(identity_record)
        result = ATTEMPT.terminate_owned_group(identity_record, 0.2, 3.0)
        completion = ATTEMPT.make_terminal_completion(
            request(), "cancelled", identity=identity_record
        )
        self.assertTrue(ATTEMPT.publish_terminal_completion(descriptor, completion))

        self.assertEqual(proof.outcome, "reviewer-alive")
        self.assertEqual(result.outcome, "cancelled")
        wait_gone(int(identity_record["reviewer_pid"]))
        wait_gone(int(marker.read_text(encoding="ascii")))
        self.groups.discard(wrapper.pid)

    def test_only_unrecorded_grandchild_survives_without_group_kill(self) -> None:
        reviewer_marker = self.root / "recorded-reviewer.pid"
        extra_marker = self.root / "unrecorded-grandchild.pid"
        source = """
import os, pathlib, subprocess, sys, time
reviewer = subprocess.Popen([sys.executable, '-I', '-c', 'import time; time.sleep(300)'])
extra = subprocess.Popen([sys.executable, '-I', '-c', 'import time; time.sleep(300)'])
p=sys.argv[1];q=p+'~';pathlib.Path(q).write_text(str(reviewer.pid),encoding='ascii');os.replace(q,p)
p=sys.argv[2];q=p+'~';pathlib.Path(q).write_text(str(extra.pid),encoding='ascii');os.replace(q,p)
time.sleep(300)
"""
        leader = self.spawn_group(source, str(reviewer_marker), str(extra_marker))
        wait_path(reviewer_marker)
        wait_path(extra_marker)
        reviewer_pid = int(reviewer_marker.read_text(encoding="ascii"))
        extra_pid = int(extra_marker.read_text(encoding="ascii"))
        owner = self.identity_for(leader.pid, reviewer_pid)
        os.kill(leader.pid, signal.SIGKILL)
        leader.wait(timeout=5)
        os.kill(reviewer_pid, signal.SIGKILL)
        wait_gone(reviewer_pid)

        proof = ATTEMPT.prove_group_ownership(owner)
        result = ATTEMPT.terminate_owned_group(owner, 0.1, 0.1)

        self.assertEqual((proof.outcome, result.outcome), ("identity-unproven",) * 2)
        self.assertIn(extra_pid, proof.members)
        self.assertEqual(ATTEMPT_PROC.process_snapshot(extra_pid)["status"], "alive")


if __name__ == "__main__":
    unittest.main()
