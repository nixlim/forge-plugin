"""Focused dormant merge lifecycle and carried-regression tests."""

from __future__ import annotations

import copy
import contextlib
import datetime as dt
import hashlib
import io
import json
import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from unittest import mock

from tests import test_cli_merge_adapters as ADAPTERS


CLI = ADAPTERS.CLI
RUNTIME = ADAPTERS.RUNTIME


class MergeCarriedRegressionTests(ADAPTERS.MergeAdapterFixture):
    def test_unrelated_detached_worktree_does_not_invalidate_inventory(self) -> None:
        detached = self.temp_root / "detached"
        self.git("worktree", "add", "--quiet", "--detach", str(detached), self.base)

        admission = CLI.MergeEngine(self.context()).start(str(self.worktree))

        self.assertEqual(admission.worktree, self.worktree)
        inventory = CLI._registered_worktrees(CLI.Repository(self.repo))
        detached_rows = [row for row in inventory if row["worktree"] == str(detached)]
        self.assertEqual(len(detached_rows), 1)
        self.assertEqual(detached_rows[0]["detached"], "")

    def test_oversized_review_request_retry_is_the_same_structured_refusal(self) -> None:
        _admission, _generation, store, engine, _outcome, _calls = self.verify_chain()
        oversized = b"x" * (CLI.OUTPUT_CAP_BYTES + 1)

        with mock.patch.object(
            engine, "_review_package", return_value=(oversized, [], {})
        ):
            refusals = []
            for _attempt in range(2):
                with self.assertRaises(CLI.Refusal) as caught:
                    engine.review_request()
                refusals.append(caught.exception)

        self.assertEqual(
            [refusal.reason_code for refusal in refusals],
            [CLI.V2ReasonCode.EVIDENCE_INCOMPLETE] * 2,
        )
        self.assertEqual(
            [refusal.message for refusal in refusals],
            [
                "forge: review refused — reviewer cannot inspect the complete authoritative package"
            ]
            * 2,
        )
        self.assertEqual(store.load(self.chain_id)["review"], {})

    def test_git_status_failure_is_a_structured_v2_refusal(self) -> None:
        original = CLI.Repository.git
        for launch_error in (False, True):
            def fail_status(repository, args, **kwargs):
                if list(args) == ["status", "--porcelain=v1", "--untracked-files=all"]:
                    if launch_error:
                        raise OSError("fixture status launch race")
                    return subprocess.CompletedProcess(
                        ["git", *args], 1, b"", b"fixture status race"
                    )
                return original(repository, args, **kwargs)

            with self.subTest(launch_error=launch_error), mock.patch.object(
                CLI.Repository, "git", new=fail_status
            ), self.assertRaises(CLI.Refusal) as caught:
                CLI.MergeEngine(self.context()).start(str(self.worktree))

            self.assertEqual(
                caught.exception.reason_code,
                CLI.V2ReasonCode.WORKTREE_INVALID,
            )
            self.assertEqual(caught.exception.schema, "forge-cli/2")
            self.assertEqual(
                caught.exception.message,
                "forge: merge start refused — source worktree status is unavailable",
            )

    def test_generation_diff_failures_are_structured_v2_refusals(self) -> None:
        engine = CLI.MergeEngine(self.context())
        admission = engine.start(str(self.worktree))
        original = CLI.Repository.git

        for selected, message in (
            (
                lambda args: args and args[0] == "diff" and "--name-only" not in args,
                "forge: merge start refused — fixed candidate diff is unavailable",
            ),
            (
                lambda args: "--name-only" in args,
                "forge: merge start refused — candidate path set is unavailable",
            ),
        ):
            def fail_selected(repository, args, **kwargs):
                if selected(list(args)):
                    raise OSError("fixture diff race")
                return original(repository, args, **kwargs)

            with self.subTest(message=message), mock.patch.object(
                CLI.Repository, "git", new=fail_selected
            ):
                with self.assertRaises(CLI.Refusal) as caught:
                    engine.bind_candidate(admission, self.base)
            self.assertEqual(
                caught.exception.reason_code,
                CLI.V2ReasonCode.EVIDENCE_INCOMPLETE,
            )
            self.assertEqual(caught.exception.schema, "forge-cli/2")
            self.assertEqual(caught.exception.message, message)

    def test_actual_head_movement_retains_candidate_stale_reason(self) -> None:
        engine = CLI.MergeEngine(self.context())
        admission = engine.start(str(self.worktree))
        (self.worktree / "src" / "app.py").write_text(
            "VALUE = 99\n", encoding="utf-8"
        )
        self.git_at(self.worktree, "add", "src/app.py")
        self.git_at(self.worktree, "commit", "--quiet", "-m", "move head")

        with self.assertRaises(CLI.Refusal) as caught:
            engine.bind_candidate(admission, self.base)
        self.assertEqual(
            caught.exception.reason_code,
            CLI.V2ReasonCode.CANDIDATE_STALE,
        )
        self.assertEqual(
            caught.exception.message,
            "forge: merge start refused — candidate HEAD changed after admission",
        )

    def test_review_diff_failure_is_a_structured_v2_refusal(self) -> None:
        _admission, _generation, store, engine, _outcome, _calls = self.verify_chain()
        original = CLI.Repository.git
        candidate_diff_calls = 0

        def fail_package_diff(repository, args, **kwargs):
            nonlocal candidate_diff_calls
            if args and args[0] == "diff" and "--name-only" not in args:
                candidate_diff_calls += 1
                if candidate_diff_calls == 2:
                    raise OSError("fixture review diff race")
            return original(repository, args, **kwargs)

        before = store.events_path(self.chain_id).read_bytes()
        with mock.patch.object(CLI.Repository, "git", new=fail_package_diff):
            with self.assertRaises(CLI.Refusal) as caught:
                engine.review_request()

        self.assertEqual(caught.exception.reason_code, CLI.V2ReasonCode.EVIDENCE_INCOMPLETE)
        self.assertEqual(caught.exception.schema, "forge-cli/2")
        self.assertEqual(
            caught.exception.message,
            "forge: review request refused — authoritative candidate diff is unavailable",
        )
        self.assertEqual(store.events_path(self.chain_id).read_bytes(), before)


class MergeLifecycleStartTests(ADAPTERS.MergeAdapterFixture):
    def start_lifecycle(self, *, bound: bool = False):
        if bound:
            self.open_run()
        engine = CLI.MergeEngine(
            self.context(run_id=self.run_id if bound else None)
        )
        outcome = engine.start_chain(
            str(self.worktree),
            task=self.task_id if bound else None,
            remote_tip=self.base,
        )
        store = engine.store
        state = store.load(str(outcome.chain_id))
        return engine, store, state, outcome

    def crash_after_scope_sidecar_publication(self, *, bound: bool = True):
        """Leave a composite bootstrap in the post-sidecar crash window."""

        if bound:
            self.open_run()
        starter = CLI.MergeEngine(
            self.context(run_id=self.run_id if bound else None)
        )
        publish = CLI._publish_merge_scope_binding

        def publish_then_crash(*args, **kwargs):
            published = publish(*args, **kwargs)
            os.kill(os.getpid(), signal.SIGKILL)
            return published

        child = os.fork()
        if child == 0:
            try:
                with mock.patch.object(
                    CLI,
                    "_publish_merge_scope_binding",
                    side_effect=publish_then_crash,
                ):
                    starter.start_chain(
                        str(self.worktree),
                        task=self.task_id if bound else None,
                        remote_tip=self.base,
                    )
            except BaseException:
                os._exit(125)
            os._exit(0)
        _waited, status = os.waitpid(child, 0)
        self.assertTrue(os.WIFSIGNALED(status), status)
        self.assertEqual(os.WTERMSIG(status), signal.SIGKILL)
        chain_ids = starter.store.list_ids(family="merge")
        self.assertEqual(len(chain_ids), 1)
        self.chain_id = chain_ids[0]
        state = starter.store.load(self.chain_id)
        self.assertEqual(state["state"], "classifying")
        self.assertEqual(state["integration"]["intent"]["operation"], "fetch")
        return starter, state

    def crash_before_scope_sidecar_publication(self, *, bound: bool):
        """Leave the authentic pre-sidecar composite crash window."""

        if bound:
            self.open_run()
        starter = CLI.MergeEngine(
            self.context(run_id=self.run_id if bound else None)
        )

        def crash_before_publish(*_args, **_kwargs):
            os.kill(os.getpid(), signal.SIGKILL)

        child = os.fork()
        if child == 0:
            try:
                with mock.patch.object(
                    CLI,
                    "_publish_merge_scope_binding",
                    side_effect=crash_before_publish,
                ):
                    starter.start_chain(
                        str(self.worktree),
                        task=self.task_id if bound else None,
                        remote_tip=self.base,
                    )
            except BaseException:
                os._exit(125)
            os._exit(0)
        _waited, status = os.waitpid(child, 0)
        self.assertTrue(os.WIFSIGNALED(status), status)
        self.assertEqual(os.WTERMSIG(status), signal.SIGKILL)
        chain_ids = starter.store.list_ids(family="merge")
        self.assertEqual(len(chain_ids), 1)
        self.chain_id = chain_ids[0]
        state = starter.store.load(self.chain_id)
        self.assertEqual(state["state"], "classifying")
        self.assertEqual(state["integration"]["intent"]["operation"], "fetch")
        self.assertFalse(
            list(
                starter.store.artifact_dir(self.chain_id).glob(
                    "scope-fetch-*.json"
                )
            )
        )
        return starter, state

    def crash_after_bootstrap_result_before_fence_release(
        self, *, succeeded: bool
    ):
        """Leave a persisted fetch result behind its original live name."""

        starter = CLI.MergeEngine(self.context())
        acquire = CLI.acquire_common_lock

        def kill_after_result(stage: str) -> None:
            if stage == "fence-result-persisted":
                os.kill(os.getpid(), signal.SIGKILL)

        def acquire_with_boundary(*args, **kwargs):
            kwargs["boundary"] = kill_after_result
            return acquire(*args, **kwargs)

        child = os.fork()
        if child == 0:
            try:
                with mock.patch.object(
                    CLI,
                    "acquire_common_lock",
                    side_effect=acquire_with_boundary,
                ):
                    starter.start_chain(
                        str(self.worktree),
                        remote_tip=(self.base if succeeded else "f" * 40),
                    )
            except BaseException:
                os._exit(125)
            os._exit(0)
        _waited, status = os.waitpid(child, 0)
        self.assertTrue(os.WIFSIGNALED(status), status)
        self.assertEqual(os.WTERMSIG(status), signal.SIGKILL)
        chain_ids = starter.store.list_ids(family="merge")
        self.assertEqual(len(chain_ids), 1)
        self.chain_id = chain_ids[0]
        state = starter.store.load(self.chain_id)
        events = [
            json.loads(line)
            for line in starter.store.events_path(self.chain_id)
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        self.assertEqual(events[-1]["event"], "fetch_result")
        self.assertEqual(
            state["integration"]["intent"]["result"],
            "success" if succeeded else "failed",
        )
        return starter, state, events[-1]

    def remove_crashed_common_owner(self, common_dir: Path) -> None:
        """Leave the authenticated crash fence while simulating owner-release loss."""

        lock_directory = common_dir / CLI.COMMON_LOCK_DIRECTORY_NAME
        inner = lock_directory / CLI.COMMON_LOCK_OWNER_NAME
        outer = common_dir / CLI.COMMON_LOCK_INTENT_NAME
        self.assertTrue(inner.is_file())
        self.assertTrue(outer.is_file())
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        common_descriptor = os.open(common_dir, flags)
        lock_descriptor = os.open(lock_directory, flags)
        try:
            inner.unlink()
            os.fsync(lock_descriptor)
            os.close(lock_descriptor)
            lock_descriptor = -1
            lock_directory.rmdir()
            os.fsync(common_descriptor)
            outer.unlink()
            os.fsync(common_descriptor)
        finally:
            if lock_descriptor >= 0:
                os.close(lock_descriptor)
            os.close(common_descriptor)
        self.assertEqual(CLI.inspect_common_lock(common_dir).topology, "free")

    def classify_crashed_bootstrap_fence(
        self,
        starter,
        state,
        reservation,
        fence,
    ) -> None:
        self.assertTrue(reservation.matches_chain(self.chain_id))
        intent_digest = CLI._merge_event_digest(
            starter.store, self.chain_id, "fetch_intent"
        )
        self.assertIsNotNone(intent_digest)
        CLI._classify_merge_scope_binding(
            starter.store,
            state,
            fetch_intent_digest=intent_digest,
            scope_request=state["integration"]["intent"].get("scope_request"),
            fence=fence,
        )

    @staticmethod
    def reseal_mapping(value) -> None:
        body = {key: item for key, item in value.items() if key != "digest"}
        value["digest"] = CLI.sha256_bytes(CLI.canonical_bytes(body))

    def assert_redigested_fetch_result_mutants_refuse(
        self,
        *,
        bound: bool,
        mutants,
    ) -> None:
        _engine, store, _state, outcome = self.start_lifecycle(bound=bound)
        chain_id = str(outcome.chain_id)
        events_path = store.events_path(chain_id)
        original_bytes = events_path.read_bytes()
        original_events = [
            json.loads(line) for line in original_bytes.splitlines()
        ]
        fetch_index = next(
            index
            for index in range(len(original_events) - 1, -1, -1)
            if original_events[index]["event"] == "fetch_result"
        )
        original_binding = original_events[fetch_index]["payload"][
            "scope_fetch_binding"
        ]
        sidecar = store.common_root / original_binding["publication"][
            "canonical_path"
        ]
        sidecar_bytes = sidecar.read_bytes()

        for label, mutate in mutants:
            with self.subTest(label=label):
                events = copy.deepcopy(original_events)
                fetch_result = events[fetch_index]
                binding = fetch_result["payload"]["scope_fetch_binding"]
                proof = fetch_result["payload"]["scope_proof"]
                mutate(binding, proof)
                self.reseal_mapping(binding)
                if proof is not None:
                    proof["scope_fetch_binding_digest"] = binding["digest"]
                    self.reseal_mapping(proof)
                self.reseal_mapping(fetch_result)
                mutant_bytes = b"".join(
                    CLI.canonical_bytes(event) + b"\n" for event in events
                )
                with self.assertRaisesRegex(
                    CLI.FrozenError,
                    rf"merge event {fetch_result['sequence']} transition is invalid",
                ):
                    CLI._replay_merge_event_bytes(chain_id, mutant_bytes)
                self.assertEqual(events_path.read_bytes(), original_bytes)
                self.assertEqual(sidecar.read_bytes(), sidecar_bytes)

    def start_and_capture_composite_metadata(self, *, bound: bool):
        if bound:
            self.open_run()
        engine = CLI.MergeEngine(
            self.context(run_id=self.run_id if bound else None)
        )
        publish = CLI._publish_merge_scope_binding
        captured = []

        def capture(*args, **kwargs):
            result = kwargs["result"]
            captured.append(copy.deepcopy(result.metadata))
            return publish(*args, **kwargs)

        with mock.patch.object(
            CLI, "_publish_merge_scope_binding", side_effect=capture
        ):
            outcome = engine.start_chain(
                str(self.worktree),
                task=self.task_id if bound else None,
            )
        self.assertEqual(len(captured), 1)
        state = engine.store.load(str(outcome.chain_id))
        events = [
            json.loads(line)
            for line in engine.store.events_path(str(outcome.chain_id))
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        event = next(
            item for item in reversed(events) if item["event"] == "fetch_result"
        )
        return engine, state, outcome, event, captured[0]

    def assert_fresh_composite_metadata(self, *, bound: bool) -> None:
        engine, state, outcome, event, metadata = (
            self.start_and_capture_composite_metadata(bound=bound)
        )
        binding = event["payload"]["scope_fetch_binding"]
        self.assertEqual(
            set(metadata),
            {
                "schema",
                "constituent_order",
                "environment_digest",
                "resolved_tip",
                "fetch",
                "scope",
                "scope_changed_paths",
                "full_patch",
            },
        )
        self.assertEqual(metadata["schema"], "forge-bootstrap-composite-result/1")
        self.assertEqual(metadata["resolved_tip"], self.base)
        self.assertEqual(
            metadata["environment_digest"],
            CLI._git_environment_digest(CLI._merge_scope_environment()),
        )
        self.assertEqual(
            metadata["constituent_order"],
            ["fetch", "name-status", "full-patch"]
            if bound
            else ["fetch", "full-patch"],
        )
        self.assertEqual(
            metadata["fetch"]["argv"],
            [
                "git",
                "--no-pager",
                "-C",
                str(self.worktree),
                "fetch",
                "--no-tags",
                "--quiet",
                "origin",
                "refs/heads/fixture-main",
            ],
        )
        if bound:
            self.assertEqual(
                metadata["scope"]["argv"],
                CLI._merge_scope_argv(
                    self.worktree, self.base, self.candidate_head
                ),
            )
            self.assertEqual(metadata["scope_changed_paths"], ["src/app.py"])
            self.assertEqual(
                metadata["scope"]["output_digest"],
                binding["child_result"]["output_digest"],
            )
        else:
            self.assertIsNone(metadata["scope"])
            self.assertIsNone(metadata["scope_changed_paths"])
            self.assertEqual(
                binding["child_result"]["output_digest"], CLI.sha256_bytes(b"")
            )
        self.assertEqual(
            metadata["full_patch"]["argv"],
            CLI._merge_full_patch_argv(
                self.worktree, self.base, self.candidate_head
            ),
        )
        self.assertEqual(
            metadata["full_patch"]["output_digest"],
            binding["full_patch_output_digest"],
        )
        record_keys = {
            "argv",
            "exit",
            "output_digest",
            "stderr_digest",
            "launch_failed",
            "output_limit_exceeded",
        }
        for name in metadata["constituent_order"]:
            key = "scope" if name == "name-status" else name.replace("-", "_")
            record = metadata[key]
            self.assertEqual(set(record), record_keys)
            self.assertEqual(record["exit"], 0)
            self.assertFalse(record["launch_failed"])
            self.assertFalse(record["output_limit_exceeded"])
            self.assertNotIn("output", record)
        event_bytes = engine.store.events_path(str(outcome.chain_id)).read_bytes()
        sidecar = engine.store.common_root / binding["publication"][
            "canonical_path"
        ]
        self.assertNotIn(b"constituent_order", event_bytes)
        self.assertNotIn(b"constituent_order", sidecar.read_bytes())
        self.assertEqual(state["candidate"]["diff_sha256"], binding["full_patch_output_digest"])

    def stream_exact_patch(self) -> tuple[int, str]:
        """Independently stream the pinned full-patch range for assertions."""

        process = subprocess.Popen(
            CLI._merge_full_patch_argv(
                self.worktree, self.base, self.candidate_head
            ),
            cwd=self.worktree,
            env=CLI._merge_scope_environment(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertIsNotNone(process.stdout)
        digest = hashlib.sha256()
        length = 0
        while True:
            chunk = process.stdout.read(16 * 1024)
            if not chunk:
                break
            length += len(chunk)
            digest.update(chunk)
        stderr = process.stderr.read() if process.stderr is not None else b""
        returncode = process.wait()
        process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()
        self.assertEqual(returncode, 0, stderr.decode("utf-8", "replace"))
        return length, digest.hexdigest()

    def tune_exact_patch_size(self, target: int) -> tuple[bytes, str]:
        """Amend the fixture candidate until its pinned patch is exactly target bytes."""

        marker = b"REV12-EXACT-PATCH-STREAM-MUST-NOT-BE-RETAINED"
        payload_size = target - 512
        self.assertGreaterEqual(payload_size, len(marker))
        for _attempt in range(4):
            payload = (marker + b"-") + b"x" * (
                payload_size - len(marker) - 1
            )
            (self.worktree / "src" / "app.py").write_bytes(payload)
            self.git_at(self.worktree, "add", "src/app.py")
            self.git_at(
                self.worktree, "commit", "--quiet", "--amend", "--no-edit"
            )
            self.candidate_head = self.git_at(self.worktree, "rev-parse", "HEAD")
            observed, digest = self.stream_exact_patch()
            if observed == target:
                return marker, digest
            payload_size += target - observed
            self.assertGreaterEqual(payload_size, len(marker))
        self.fail(f"could not tune full-patch output to exactly {target} bytes")

    def assert_patch_boundary_bootstrap(self, *, bound: bool, target: int) -> None:
        marker, patch_digest = self.tune_exact_patch_size(target)
        observed, observed_digest = self.stream_exact_patch()
        self.assertEqual(observed, target)
        self.assertEqual(observed_digest, patch_digest)

        _engine, store, state, outcome = self.start_lifecycle(bound=bound)
        event_bytes = store.events_path(str(outcome.chain_id)).read_bytes()
        events = [json.loads(line) for line in event_bytes.splitlines()]
        fetch_result = next(
            event for event in reversed(events) if event["event"] == "fetch_result"
        )
        binding = fetch_result["payload"]["scope_fetch_binding"]
        canonical = store.common_root / binding["publication"]["canonical_path"]
        sidecar_bytes = canonical.read_bytes()

        self.assertTrue(outcome.ok)
        self.assertEqual(state["state"], "verifying")
        self.assertEqual(binding["full_patch_output_digest"], patch_digest)
        self.assertEqual(state["candidate"]["diff_sha256"], patch_digest)
        self.assertFalse(binding["child_result"]["output_limit_exceeded"])
        if bound:
            self.assertIsNotNone(fetch_result["payload"]["scope_proof"])
        else:
            self.assertIsNone(fetch_result["payload"]["scope_proof"])
        self.assertNotIn(marker, event_bytes)
        self.assertNotIn(marker, sidecar_bytes)
        self.assertFalse(
            any("patch" in key for key in binding["child_result"])
        )
        self.assertNotIn("output", binding["child_result"])

    def low_level_full_patch_failure(
        self, failure: str
    ) -> CLI.FencedProcessResult:
        """Exercise one bounded full-patch failure in the composite child."""

        cap = 32
        fetch_argv = [CLI.sys.executable, "-c", "pass", "fixture-fetch"]
        scope_argv = [
            CLI.sys.executable,
            "-c",
            "import os;os.write(1,b'M\\0src/app.py\\0')",
            "fixture-name-status",
        ]
        if failure == "nonzero":
            patch_script = (
                "import os;"
                "os.write(2,b'fixture patch failure\\n');"
                "raise SystemExit(23)"
            )
        elif failure == "stderr-cap":
            patch_script = "import os;os.write(2,b'e'*33)"
        else:
            self.assertEqual(failure, "launch")
            patch_script = "import os;os.write(1,b'patch')"
        patch_argv = [
            CLI.sys.executable,
            "-c",
            patch_script,
            "fixture-full-patch",
        ]
        request = {
            "schema": "forge-bootstrap-composite-request/1",
            "worktree": str(self.worktree),
            "git_dir": str(self.worktree / ".git"),
            "candidate_head": self.candidate_head,
            "remote_tip": self.base,
            "run_bound": False,
            "fetch_argv": fetch_argv,
            "cap": cap,
        }
        encoded = CLI.base64.urlsafe_b64encode(
            CLI.canonical_bytes(request)
        ).decode("ascii")
        written: list[bytes] = []
        original_popen = subprocess.Popen

        def launch(argv, *args, **kwargs):
            if failure == "launch" and list(argv) == patch_argv:
                raise OSError("fixture full-patch launch failure")
            return original_popen(argv, *args, **kwargs)

        def capture_write(descriptor: int, payload: bytes) -> int:
            self.assertEqual(descriptor, 1)
            written.append(bytes(payload))
            return len(payload)

        with mock.patch.object(
            CLI, "_merge_scope_argv", return_value=scope_argv
        ), mock.patch.object(
            CLI, "_merge_full_patch_argv", return_value=patch_argv
        ), mock.patch.object(
            CLI.subprocess, "Popen", side_effect=launch
        ), mock.patch.object(
            CLI.os, "write", side_effect=capture_write
        ):
            self.assertEqual(CLI._merge_bootstrap_child_main(encoded), 0)
            self.assertEqual(len(written), 1)
            protocol_bytes = written[0]
            raw = CLI.FencedProcessResult(
                argv=["fixture-composite"],
                returncode=0,
                duration_seconds=0.01,
                output=protocol_bytes,
                output_digest=CLI.sha256_bytes(protocol_bytes),
                timed_out=False,
                output_limit=False,
                launch_failed=False,
                group_survived=False,
                authorized=True,
                fence_digest="a" * 64,
                fence_inode=1,
            )
            decoded = CLI._decode_merge_bootstrap_result(
                raw,
                run_bound=False,
                fetch_argv=fetch_argv,
                worktree=self.worktree,
                candidate_head=self.candidate_head,
                environment_digest=CLI._git_environment_digest(os.environ),
            )

        self.assertIsInstance(decoded.metadata, dict)
        metadata = decoded.metadata
        self.assertEqual(metadata["constituent_order"], ["fetch", "full-patch"])
        self.assertEqual(metadata["fetch"]["exit"], 0)
        self.assertIsNone(metadata["scope"])
        self.assertIsNone(metadata["scope_changed_paths"])
        patch = metadata["full_patch"]
        self.assertEqual(patch["argv"], patch_argv)
        self.assertNotEqual(decoded.returncode, 0)
        self.assertEqual(decoded.output, b"")
        if failure == "launch":
            self.assertIsNone(patch["exit"])
            self.assertTrue(patch["launch_failed"])
            self.assertFalse(patch["output_limit_exceeded"])
            self.assertTrue(decoded.launch_failed)
        elif failure == "nonzero":
            self.assertEqual(patch["exit"], 23)
            self.assertEqual(
                patch["stderr_digest"],
                CLI.sha256_bytes(b"fixture patch failure\n"),
            )
            self.assertFalse(patch["launch_failed"])
            self.assertFalse(patch["output_limit_exceeded"])
            self.assertFalse(decoded.launch_failed)
        else:
            self.assertEqual(
                patch["stderr_digest"], CLI.sha256_bytes(b"e" * (cap + 1))
            )
            self.assertFalse(patch["launch_failed"])
            self.assertTrue(patch["output_limit_exceeded"])
            self.assertTrue(decoded.output_limit)
        return decoded

    def assert_unbound_composite_failure_is_pre_sidecar(
        self, result: CLI.FencedProcessResult
    ) -> None:
        """Persist a decoded composite failure without launching another child."""

        injected: list[CLI.FencedProcessResult] = []

        def fail_fenced_command(_lock, **kwargs):
            current = CLI.dataclasses.replace(
                result,
                argv=list(kwargs["argv"]),
                authorized=True,
                fence_digest="b" * 64,
                fence_inode=2,
            )
            injected.append(current)
            kwargs["persist_result"](current)
            return current

        engine = CLI.MergeEngine(self.context())
        with mock.patch.object(
            CLI, "run_fenced_command", side_effect=fail_fenced_command
        ), self.assertRaises(CLI.Refusal) as caught:
            engine.start_chain(str(self.worktree), remote_tip=self.base)

        self.assertEqual(len(injected), 1)
        self.assertEqual(
            caught.exception.reason_code, CLI.V2ReasonCode.FETCH_FAILED
        )
        self.assertEqual(
            caught.exception.message,
            "forge: merge start refused — fixed target fetch failed",
        )
        state = caught.exception.chain
        self.assertEqual(state["state"], "classifying")
        self.assertIsNone(state["candidate"])
        self.assertEqual(state["integration"]["condition"], "fetch-failed")
        self.assertEqual(
            state["integration"]["intent"]["operation"], "fetch-result"
        )
        self.assertEqual(state["integration"]["intent"]["result"], "failed")
        chain_id = str(state["chain_id"])
        events = [
            json.loads(line)
            for line in engine.store.events_path(chain_id)
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        self.assertEqual(events[-1]["event"], "fetch_result")
        self.assertIsNone(events[-1]["payload"]["scope_fetch_binding"])
        self.assertIsNone(events[-1]["payload"]["scope_proof"])
        self.assertFalse(
            list(engine.store.artifact_dir(chain_id).glob("scope-fetch-*.json"))
        )

    def test_start_publishes_ownership_and_generation_before_success(self) -> None:
        _engine, store, state, outcome = self.start_lifecycle()

        self.assertTrue(outcome.ok)
        self.assertEqual(outcome.schema, "forge-cli/2")
        self.assertEqual(state["state"], "verifying")
        self.assertEqual(state["candidate"]["generation"], 1)
        self.assertEqual(state["candidate"]["candidate_head"], self.candidate_head)
        self.assertEqual(state["candidate"]["remote_tip"], self.base)
        self.assertEqual(state["worktree"]["claim"]["status"], "owned")
        claim = Path(state["worktree"]["claim"]["path"])
        self.assertTrue(claim.is_file())
        events = [
            json.loads(line)
            for line in store.events_path(str(outcome.chain_id))
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        self.assertEqual(
            [event["event"] for event in events],
            [
                "chain_started",
                "ownership_intent",
                "ownership_claimed",
                "fetch_intent",
                "fetch_result",
                "generation_refreshed",
            ],
        )
        fetched = events[-2]
        classified = events[-1]
        self.assertEqual(fetched["payload"]["delta"]["state"], "classifying")
        self.assertNotIn("tier", fetched["payload"]["delta"])
        self.assertEqual(
            fetched["payload"]["delta"]["candidate"], state["candidate"]
        )
        self.assertEqual(
            fetched["generation_digest"], state["candidate"]["generation_digest"]
        )
        pending = CLI._replay_merge_event_bytes(
            str(outcome.chain_id),
            b"".join(CLI.canonical_bytes(event) + b"\n" for event in events[:-1]),
        ).state
        self.assertEqual(pending["state"], "classifying")
        self.assertIsNone(pending["tier"])
        self.assertEqual(pending["candidate"], state["candidate"])
        self.assertEqual(
            classified["generation_digest"], fetched["generation_digest"]
        )
        self.assertNotIn("candidate", classified["payload"]["delta"])
        self.assertEqual(classified["payload"]["delta"]["tier"], state["tier"])

    def test_start_refuses_a_second_live_owner_with_exact_literal(self) -> None:
        _engine, _store, state, _outcome = self.start_lifecycle()

        with self.assertRaises(CLI.Refusal) as caught:
            CLI.MergeEngine(self.context()).start_chain(
                str(self.worktree), remote_tip=self.base
            )

        self.assertEqual(
            caught.exception.reason_code,
            CLI.V2ReasonCode.LIVE_MERGE_CHAIN_EXISTS,
        )
        self.assertEqual(
            caught.exception.message,
            "forge: merge start refused — selected worktree already has a live merge owner",
        )
        self.assertEqual(caught.exception.chain["chain_id"], state["chain_id"])

    def test_released_owner_is_the_authenticated_predecessor_of_reuse(self) -> None:
        _first_engine, first_store, first, _outcome = self.start_lifecycle()
        CLI.MergeEngine(
            self.context(chain_id=first["chain_id"])
        ).abort("first complete")
        first_events = [
            json.loads(line)
            for line in first_store.events_path(first["chain_id"])
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        release_digest = next(
            event["digest"]
            for event in reversed(first_events)
            if event["event"] == "ownership_released"
        )

        second = CLI.MergeEngine(self.context()).start_chain(
            str(self.worktree), remote_tip=self.base
        )
        second_events = [
            json.loads(line)
            for line in first_store.events_path(str(second.chain_id))
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        intent = next(
            event for event in second_events if event["event"] == "ownership_intent"
        )
        self.assertEqual(intent["payload"]["predecessor_chain_id"], first["chain_id"])
        self.assertEqual(
            intent["payload"]["predecessor_release_digest"], release_digest
        )

    def test_predecessor_selection_rejects_an_authenticated_fork(self) -> None:
        admission = CLI.MergeEngine(self.context()).start(str(self.worktree))
        store = CLI.MergeChainStore(self.repo)
        _digest, _name, claim_path = CLI._merge_claim_identity(
            store, admission.worktree_identity
        )

        def replay(chain_id, released_digest):
            state = {
                "chain_id": chain_id,
                "state": "aborted",
                "worktree": {
                    **copy.deepcopy(admission.worktree_identity),
                    "claim": {
                        "status": "released",
                        "path": str(claim_path),
                        "inode": 17,
                        "digest": "b" * 64,
                    },
                },
            }
            return mock.Mock(
                state=state,
                events=(
                    {
                        "event": "ownership_intent",
                        "payload": {
                            "predecessor_chain_id": None,
                            "predecessor_release_digest": None,
                        },
                    },
                    {"event": "ownership_claimed", "payload": {}},
                    {
                        "event": "ownership_released",
                        "digest": released_digest,
                        "payload": {"release_mode": "acquired"},
                    },
                ),
            )

        fake_store = mock.Mock()
        fake_store.list_ids.return_value = [
            "c-2026-08-30T150000Z-a001",
            "c-2026-08-30T150001Z-a002",
        ]
        fake_store.event_lock.side_effect = lambda _chain_id: contextlib.nullcontext()
        first_replay = replay(fake_store.list_ids.return_value[0], "c" * 64)
        second_replay = replay(fake_store.list_ids.return_value[1], "d" * 64)
        fake_store._read_replay_locked.side_effect = (
            first_replay,
            first_replay,
            second_replay,
            second_replay,
        )

        with self.assertRaisesRegex(CLI.FrozenError, "ownership lineage is forked"):
            CLI._merge_released_predecessor(
                fake_store, claim_path, admission.worktree_identity
            )

    def test_predecessor_selection_never_skips_a_corrupt_merge_replay(self) -> None:
        admission = CLI.MergeEngine(self.context()).start(str(self.worktree))
        store = CLI.MergeChainStore(self.repo)
        _digest, _name, claim_path = CLI._merge_claim_identity(
            store, admission.worktree_identity
        )
        fake_store = mock.Mock()
        corrupt_id = "c-2026-08-30T150000Z-a001"
        fake_store.list_ids.return_value = [corrupt_id]
        fake_store.event_lock.return_value = contextlib.nullcontext()
        fake_store._read_replay_locked.side_effect = CLI.FrozenError(
            "fixture authenticated replay failure",
            chain_id=corrupt_id,
            schema="forge-cli/2",
        )
        initial = CLI.MergeEngine(self.context())._initial_merge_state(
            corrupt_id,
            admission,
            claim_path,
            at="2026-08-30T15:00:00Z",
        )
        unsigned = {
            "schema": "forge-merge-event/1",
            "chain_id": corrupt_id,
            "sequence": 1,
            "at": "2026-08-30T15:00:00Z",
            "event": "chain_started",
            "generation_digest": None,
            "previous_digest": CLI.ZERO_DIGEST,
            "payload": {"delta": initial},
        }
        opening = {**unsigned, "digest": CLI.sha256_bytes(CLI.canonical_bytes(unsigned))}
        fake_store.events_path.return_value = Path(f"{corrupt_id}.events.jsonl")
        fake_store._read_root_bytes.return_value = CLI.canonical_bytes(opening) + b"\n"

        with self.assertRaisesRegex(CLI.FrozenError, "authenticated replay failure"):
            CLI._merge_released_predecessor(
                fake_store, claim_path, admission.worktree_identity
            )

    def test_publication_failure_is_addressable_and_absent_claim_can_abort(self) -> None:
        starter = CLI.MergeEngine(self.context())
        with mock.patch.object(
            CLI, "_publish_merge_claim", side_effect=OSError("fixture link failure")
        ), self.assertRaises(CLI.Refusal) as caught:
            starter.start_chain(str(self.worktree), remote_tip=self.base)

        failed = caught.exception.chain
        self.assertEqual(failed["worktree"]["claim"]["status"], "unpublished")
        self.assertFalse(Path(failed["worktree"]["claim"]["path"]).exists())
        engine = CLI.MergeEngine(self.context(chain_id=failed["chain_id"]))
        inspected = engine.status()
        self.assertEqual(
            inspected.next_required_step,
            f"forge merge abort --chain-id {failed['chain_id']}",
        )
        with self.assertRaises(CLI.Refusal) as refresh:
            engine.refresh(remote_tip=self.base)
        self.assertEqual(
            refresh.exception.message,
            "forge: merge refresh refused — ownership publication requires recovery",
        )
        aborted = engine.abort("publication failed")
        self.assertTrue(aborted.ok)
        self.assertEqual(starter.store.load(failed["chain_id"])["state"], "aborted")

    def test_publish_before_claim_event_routes_to_recovery(self) -> None:
        original = CLI._publish_merge_claim

        def publish_then_interrupt(*args, **kwargs):
            published = original(*args, **kwargs)
            raise FileExistsError(published.path)

        starter = CLI.MergeEngine(self.context())
        with mock.patch.object(
            CLI, "_publish_merge_claim", side_effect=publish_then_interrupt
        ), self.assertRaises(CLI.Refusal) as caught:
            starter.start_chain(str(self.worktree), remote_tip=self.base)

        failed = caught.exception.chain
        self.assertEqual(
            caught.exception.reason_code,
            CLI.V2ReasonCode.STATE_PRECONDITION,
        )
        self.assertEqual(
            caught.exception.message,
            "forge: merge start refused — ownership publication requires recovery",
        )
        self.assertEqual(failed["worktree"]["claim"]["status"], "unpublished")
        self.assertTrue(Path(failed["worktree"]["claim"]["path"]).exists())
        inspected = CLI.MergeEngine(
            self.context(chain_id=failed["chain_id"])
        ).status()
        self.assertEqual(
            inspected.next_required_step,
            f"forge merge recover --chain-id {failed['chain_id']}",
        )

    def test_malformed_publication_collision_freezes_instead_of_claiming_live(self) -> None:
        def collide(_store, _name, path, _record):
            os.symlink("missing-collision-target", path)
            raise FileExistsError(path)

        starter = CLI.MergeEngine(self.context())
        with mock.patch.object(
            CLI, "_publish_merge_claim", side_effect=collide
        ), self.assertRaises(CLI.FrozenError) as caught:
            starter.start_chain(str(self.worktree), remote_tip=self.base)
        self.assertRegex(
            str(caught.exception),
            "publication collision is malformed|collision vanished before authentication",
        )

    def test_never_published_abort_rejects_a_dangling_claim_symlink(self) -> None:
        starter = CLI.MergeEngine(self.context())
        with mock.patch.object(
            CLI, "_publish_merge_claim", side_effect=OSError("fixture link failure")
        ), self.assertRaises(CLI.Refusal) as failed_start:
            starter.start_chain(str(self.worktree), remote_tip=self.base)
        failed = failed_start.exception.chain
        claim_path = Path(failed["worktree"]["claim"]["path"])
        os.symlink("missing-claim-target", claim_path)
        self.assertTrue(os.path.lexists(claim_path))
        self.assertFalse(claim_path.exists())

        engine = CLI.MergeEngine(self.context(chain_id=failed["chain_id"]))
        self.assertEqual(
            engine.status().next_required_step,
            f"forge merge recover --chain-id {failed['chain_id']}",
        )
        before = starter.store.events_path(failed["chain_id"]).read_bytes()
        with self.assertRaisesRegex(
            CLI.FrozenError, "unpublished merge ownership path unexpectedly exists"
        ):
            engine.abort("unsafe collision")
        self.assertEqual(
            starter.store.events_path(failed["chain_id"]).read_bytes(), before
        )

    def test_failed_bootstrap_tip_is_durable_and_refresh_retry_is_structured(self) -> None:
        engine = CLI.MergeEngine(self.context())

        def fail_composite(raw: CLI.FencedProcessResult, **_kwargs: object):
            return CLI.dataclasses.replace(
                raw,
                returncode=1,
                output=b"",
                output_digest=hashlib.sha256(b"").hexdigest(),
                metadata=None,
            )

        with mock.patch.object(
            CLI,
            "_decode_merge_bootstrap_result",
            side_effect=fail_composite,
        ), self.assertRaises(CLI.Refusal) as first:
            engine.start_chain(str(self.worktree))
        self.assertEqual(first.exception.reason_code, CLI.V2ReasonCode.FETCH_FAILED)
        chain_id = first.exception.chain["chain_id"]
        failed = engine.store.load(chain_id)
        self.assertEqual(failed["state"], "classifying")
        self.assertIsNone(failed["candidate"])
        self.assertEqual(failed["integration"]["condition"], "fetch-failed")
        failed_events = [
            json.loads(line)
            for line in engine.store.events_path(chain_id)
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        self.assertIsNone(
            failed_events[-1]["payload"]["scope_fetch_binding"]
        )
        self.assertIsNone(failed_events[-1]["payload"]["scope_proof"])
        self.assertFalse(
            list(engine.store.artifact_dir(chain_id).glob("scope-fetch-*.json"))
        )

        retry = CLI.MergeEngine(self.context(chain_id=chain_id))
        outcome = retry.refresh(remote_tip=self.base)
        current = retry.store.load(chain_id)
        self.assertTrue(outcome.ok)
        self.assertEqual(current["state"], "verifying")
        self.assertEqual(current["candidate"]["generation"], 1)
        events = [
            json.loads(line)
            for line in retry.store.events_path(chain_id)
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        self.assertEqual(
            [event["event"] for event in events[-3:]],
            ["fetch_intent", "fetch_result", "generation_refreshed"],
        )
        first_fetch_result = next(
            event for event in events if event["event"] == "fetch_result"
        )
        self.assertIsNone(first_fetch_result["payload"]["scope_fetch_binding"])
        self.assertIsNone(first_fetch_result["payload"]["scope_proof"])
        retry_fetch_result = events[-2]
        self.assertEqual(
            retry_fetch_result["payload"]["delta"]["integration"]["intent"][
                "attempt"
            ],
            2,
        )
        self.assertIsNone(current["integration"]["intent"])

    def test_run_bound_start_persists_the_immutable_binding(self) -> None:
        _engine, _store, state, _outcome = self.start_lifecycle(bound=True)

        self.assertEqual(
            state["run_binding"],
            {
                "run_id": self.run_id,
                "task_id": self.task_id,
                "repository": str(self.repo.resolve()),
                "policy_digest": state["policy_source"]["digest"],
            },
        )
        self.assertEqual(state["run"], self.run_id)

    def test_run_bound_start_publishes_exact_scope_sidecar_and_proof(self) -> None:
        with mock.patch.object(
            CLI, "run_fenced_command", wraps=CLI.run_fenced_command
        ) as fenced:
            _engine, store, state, outcome = self.start_lifecycle(bound=True)
        self.assertEqual(fenced.call_count, 1)
        events = [
            json.loads(line)
            for line in store.events_path(str(outcome.chain_id))
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        fetch_event = next(
            event for event in reversed(events) if event["event"] == "fetch_result"
        )
        fetch_result = fetch_event["payload"]
        binding = fetch_result["scope_fetch_binding"]
        proof = fetch_result["scope_proof"]

        self.assertEqual(
            set(binding),
            {
                "schema",
                "chain_id",
                "fetch_intent_digest",
                "scope_request_digest",
                "candidate_head",
                "remote_tip",
                "command_template_digest",
                "command_digest",
                "full_patch_command_digest",
                "full_patch_output_digest",
                "environment_digest",
                "publication",
                "retained_inflight",
                "child_result",
                "recorded_at",
                "digest",
            },
        )
        self.assertEqual(binding["schema"], "forge-run-scope-fetch-binding/2")
        self.assertEqual(len(binding), 16)
        self.assertNotIn(None, binding.values())
        self.assertEqual(
            set(proof),
            {
                "schema",
                "run_id",
                "task_id",
                "generation_digest",
                "remote_tip",
                "candidate_head",
                "command_template_digest",
                "command_digest",
                "environment_digest",
                "scope_fetch_binding_digest",
                "output_digest",
                "task_files",
                "admitted_scope",
                "changed_paths",
                "out_of_scope_paths",
                "result",
                "digest",
            },
        )
        binding_body = {
            key: value for key, value in binding.items() if key != "digest"
        }
        proof_body = {key: value for key, value in proof.items() if key != "digest"}
        self.assertEqual(len(binding_body), 15)
        self.assertEqual(
            binding["digest"], CLI.sha256_bytes(CLI.canonical_bytes(binding_body))
        )
        self.assertEqual(
            proof["digest"], CLI.sha256_bytes(CLI.canonical_bytes(proof_body))
        )
        self.assertEqual(proof["scope_fetch_binding_digest"], binding["digest"])
        self.assertEqual(binding["child_result"]["resolved_tip"], self.base)
        self.assertEqual(
            binding["child_result"]["output_digest"], proof["output_digest"]
        )
        self.assertEqual(
            binding["full_patch_command_digest"],
            CLI.sha256_bytes(
                CLI.canonical_bytes(
                    CLI._merge_full_patch_argv(
                        self.worktree, self.base, self.candidate_head
                    )
                )
            ),
        )
        _patch_length, patch_digest = self.stream_exact_patch()
        self.assertEqual(binding["full_patch_output_digest"], patch_digest)
        self.assertEqual(
            binding["full_patch_output_digest"], state["candidate"]["diff_sha256"]
        )
        self.assertEqual(
            fetch_event["generation_digest"],
            state["candidate"]["generation_digest"],
        )
        self.assertEqual(
            fetch_event["payload"]["delta"]["candidate"], state["candidate"]
        )
        canonical = store.common_root / binding["publication"]["canonical_path"]
        temporary = store.common_root / binding["publication"]["temporary_path"]
        self.assertEqual(json.loads(canonical.read_bytes()), binding)
        self.assertFalse(temporary.exists())
        self.assertEqual(canonical.stat().st_nlink, 1)

        def reseal(candidate):
            body = {
                key: value for key, value in candidate.items() if key != "digest"
            }
            candidate["digest"] = CLI.sha256_bytes(CLI.canonical_bytes(body))
            return candidate

        malformed = []
        negative_device = copy.deepcopy(binding)
        negative_device["retained_inflight"]["device"] = -1
        malformed.append(reseal(negative_device))
        wrong_fence_path = copy.deepcopy(binding)
        wrong_fence_path["retained_inflight"]["path"] = "/tmp/not-agent-rebase.inflight"
        malformed.append(reseal(wrong_fence_path))
        malformed_child_digest = copy.deepcopy(binding)
        malformed_child_digest["child_result"]["output_digest"] = "not-a-digest"
        malformed.append(reseal(malformed_child_digest))
        boolean_exit = copy.deepcopy(binding)
        boolean_exit["child_result"]["exit"] = False
        malformed.append(reseal(boolean_exit))
        numeric_oid = copy.deepcopy(binding)
        numeric_oid["candidate_head"] = int("1" * 40, 16)
        malformed.append(reseal(numeric_oid))
        numeric_digest = copy.deepcopy(binding)
        numeric_digest["fetch_intent_digest"] = int("1" * 64, 16)
        malformed.append(reseal(numeric_digest))
        extra_retained_field = copy.deepcopy(binding)
        extra_retained_field["retained_inflight"]["unexpected"] = True
        malformed.append(reseal(extra_retained_field))
        missing_full_patch_digest = copy.deepcopy(binding)
        missing_full_patch_digest["full_patch_output_digest"] = None
        malformed.append(reseal(missing_full_patch_digest))
        for candidate in malformed:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                CLI._validate_merge_scope_fetch_binding(candidate)

    def test_unbound_start_publishes_exact_null_member_sidecar(self) -> None:
        with mock.patch.object(
            CLI,
            "_merge_scope_argv",
            side_effect=AssertionError(
                "unbound composite bootstrap must not launch name-status"
            ),
        ), mock.patch.object(
            CLI, "run_fenced_command", wraps=CLI.run_fenced_command
        ) as fenced:
            _engine, store, state, outcome = self.start_lifecycle()
        self.assertEqual(fenced.call_count, 1)
        events = [
            json.loads(line)
            for line in store.events_path(str(outcome.chain_id))
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        fetch_result = next(
            event for event in reversed(events) if event["event"] == "fetch_result"
        )
        binding = fetch_result["payload"]["scope_fetch_binding"]

        self.assertIsNone(fetch_result["payload"]["scope_proof"])
        self.assertEqual(
            set(binding),
            {
                "schema",
                "chain_id",
                "fetch_intent_digest",
                "scope_request_digest",
                "candidate_head",
                "remote_tip",
                "command_template_digest",
                "command_digest",
                "full_patch_command_digest",
                "full_patch_output_digest",
                "environment_digest",
                "publication",
                "retained_inflight",
                "child_result",
                "recorded_at",
                "digest",
            },
        )
        self.assertEqual(binding["schema"], "forge-run-scope-fetch-binding/2")
        self.assertEqual(len(binding), 16)
        body = {key: value for key, value in binding.items() if key != "digest"}
        self.assertEqual(len(body), 15)
        self.assertEqual(
            {key for key, value in binding.items() if value is None},
            {
                "scope_request_digest",
                "command_template_digest",
                "command_digest",
            },
        )
        self.assertTrue(
            all(
                value is not None
                for key, value in binding.items()
                if key
                not in {
                    "scope_request_digest",
                    "command_template_digest",
                    "command_digest",
                }
            )
        )
        self.assertEqual(
            binding["digest"], CLI.sha256_bytes(CLI.canonical_bytes(body))
        )
        self.assertEqual(binding["child_result"]["resolved_tip"], self.base)
        self.assertEqual(
            binding["child_result"]["output_digest"], CLI.sha256_bytes(b"")
        )
        self.assertNotEqual(
            binding["child_result"]["output_digest"],
            binding["full_patch_output_digest"],
        )
        self.assertEqual(
            binding["full_patch_command_digest"],
            CLI.sha256_bytes(
                CLI.canonical_bytes(
                    CLI._merge_full_patch_argv(
                        self.worktree, self.base, self.candidate_head
                    )
                )
            ),
        )
        _patch_length, patch_digest = self.stream_exact_patch()
        self.assertEqual(binding["full_patch_output_digest"], patch_digest)
        self.assertEqual(
            binding["full_patch_output_digest"], state["candidate"]["diff_sha256"]
        )
        self.assertEqual(
            fetch_result["generation_digest"],
            state["candidate"]["generation_digest"],
        )
        self.assertEqual(
            fetch_result["payload"]["delta"]["candidate"], state["candidate"]
        )
        canonical = store.common_root / binding["publication"]["canonical_path"]
        temporary = store.common_root / binding["publication"]["temporary_path"]
        self.assertEqual(json.loads(canonical.read_bytes()), binding)
        self.assertFalse(temporary.exists())

        nonnull_scope_digest = copy.deepcopy(binding)
        nonnull_scope_digest["command_digest"] = CLI.ZERO_DIGEST
        nonnull_body = {
            key: value
            for key, value in nonnull_scope_digest.items()
            if key != "digest"
        }
        nonnull_scope_digest["digest"] = CLI.sha256_bytes(
            CLI.canonical_bytes(nonnull_body)
        )
        with self.assertRaises(ValueError):
            CLI._validate_merge_scope_fetch_binding(nonnull_scope_digest)

        missing_required_digest = copy.deepcopy(binding)
        missing_required_digest["full_patch_output_digest"] = None
        missing_body = {
            key: value
            for key, value in missing_required_digest.items()
            if key != "digest"
        }
        missing_required_digest["digest"] = CLI.sha256_bytes(
            CLI.canonical_bytes(missing_body)
        )
        with self.assertRaises(ValueError):
            CLI._validate_merge_scope_fetch_binding(missing_required_digest)

    def test_bound_fresh_child_reports_exact_composite_metadata(self) -> None:
        self.assert_fresh_composite_metadata(bound=True)

    def test_unbound_fresh_child_reports_exact_composite_metadata(self) -> None:
        self.assert_fresh_composite_metadata(bound=False)

    def test_bound_fetch_result_replay_recomputes_every_scope_relationship(self) -> None:
        def wrong_proof_output(_binding, proof):
            proof["output_digest"] = CLI.ZERO_DIGEST

        def invented_containment(_binding, proof):
            proof["changed_paths"] = sorted(
                {*proof["changed_paths"], "outside/replay.py"},
                key=lambda item: item.encode("utf-8"),
            )
            proof["out_of_scope_paths"] = []
            proof["result"] = "contained"

        def invented_excess(_binding, proof):
            proof["out_of_scope_paths"] = ["src/app.py"]
            proof["result"] = "exceeded"

        def wrong_command(binding, proof):
            binding["command_digest"] = CLI.ZERO_DIGEST
            proof["command_digest"] = CLI.ZERO_DIGEST

        def wrong_full_patch_command(binding, _proof):
            binding["full_patch_command_digest"] = CLI.ZERO_DIGEST

        def wrong_environment(binding, proof):
            binding["environment_digest"] = CLI.ZERO_DIGEST
            proof["environment_digest"] = CLI.ZERO_DIGEST

        def wrong_publication(binding, _proof):
            nonce = binding["retained_inflight"]["nonce"]
            canonical = (
                f".forge/chains/{binding['chain_id']}/scope-fetch-"
                f"{binding['fetch_intent_digest']}-{CLI.ZERO_DIGEST}.json"
            )
            binding["publication"]["canonical_path"] = canonical
            binding["publication"]["temporary_path"] = (
                f"{canonical}.tmp-{nonce}"
            )

        def wrong_full_patch_output(binding, _proof):
            binding["full_patch_output_digest"] = CLI.ZERO_DIGEST

        self.assert_redigested_fetch_result_mutants_refuse(
            bound=True,
            mutants=(
                ("proof-child-output-digest", wrong_proof_output),
                ("containment-recomputation", invented_containment),
                ("excess-recomputation", invented_excess),
                ("name-status-command", wrong_command),
                ("full-patch-command", wrong_full_patch_command),
                ("environment", wrong_environment),
                ("publication", wrong_publication),
                ("full-patch-output", wrong_full_patch_output),
            ),
        )

    def test_unbound_fetch_result_replay_recomputes_non_scope_relationships(self) -> None:
        def wrong_full_patch_command(binding, proof):
            self.assertIsNone(proof)
            binding["full_patch_command_digest"] = CLI.ZERO_DIGEST

        def wrong_environment(binding, proof):
            self.assertIsNone(proof)
            binding["environment_digest"] = CLI.ZERO_DIGEST

        def wrong_publication(binding, proof):
            self.assertIsNone(proof)
            nonce = binding["retained_inflight"]["nonce"]
            canonical = (
                f".forge/chains/{binding['chain_id']}/scope-fetch-"
                f"{binding['fetch_intent_digest']}-{CLI.ZERO_DIGEST}.json"
            )
            binding["publication"]["canonical_path"] = canonical
            binding["publication"]["temporary_path"] = (
                f"{canonical}.tmp-{nonce}"
            )

        def wrong_retained_path(binding, proof):
            self.assertIsNone(proof)
            binding["retained_inflight"]["path"] = (
                "/tmp/agent-rebase.inflight"
            )

        def wrong_full_patch_output(binding, proof):
            self.assertIsNone(proof)
            binding["full_patch_output_digest"] = CLI.ZERO_DIGEST

        self.assert_redigested_fetch_result_mutants_refuse(
            bound=False,
            mutants=(
                ("full-patch-command", wrong_full_patch_command),
                ("environment", wrong_environment),
                ("publication", wrong_publication),
                ("retained-fence-path", wrong_retained_path),
                ("full-patch-output", wrong_full_patch_output),
            ),
        )

    def test_bound_full_patch_below_output_cap_streams_successfully(self) -> None:
        self.assert_patch_boundary_bootstrap(
            bound=True, target=CLI.OUTPUT_CAP_BYTES - 1
        )

    def test_bound_full_patch_at_exact_output_cap_streams_successfully(self) -> None:
        self.assert_patch_boundary_bootstrap(
            bound=True, target=CLI.OUTPUT_CAP_BYTES
        )

    def test_bound_full_patch_above_output_cap_streams_successfully(self) -> None:
        self.assert_patch_boundary_bootstrap(
            bound=True, target=CLI.OUTPUT_CAP_BYTES + 1
        )

    def test_unbound_full_patch_below_output_cap_streams_successfully(self) -> None:
        self.assert_patch_boundary_bootstrap(
            bound=False, target=CLI.OUTPUT_CAP_BYTES - 1
        )

    def test_unbound_full_patch_at_exact_output_cap_streams_successfully(self) -> None:
        self.assert_patch_boundary_bootstrap(
            bound=False, target=CLI.OUTPUT_CAP_BYTES
        )

    def test_unbound_full_patch_above_output_cap_streams_successfully(self) -> None:
        self.assert_patch_boundary_bootstrap(
            bound=False, target=CLI.OUTPUT_CAP_BYTES + 1
        )

    def test_unbound_full_patch_launch_failure_is_pre_sidecar_fetch_failure(
        self,
    ) -> None:
        result = self.low_level_full_patch_failure("launch")
        self.assert_unbound_composite_failure_is_pre_sidecar(result)

    def test_unbound_full_patch_nonzero_is_pre_sidecar_fetch_failure(self) -> None:
        result = self.low_level_full_patch_failure("nonzero")
        self.assert_unbound_composite_failure_is_pre_sidecar(result)

    def test_unbound_full_patch_stderr_cap_is_pre_sidecar_fetch_failure(
        self,
    ) -> None:
        result = self.low_level_full_patch_failure("stderr-cap")
        self.assert_unbound_composite_failure_is_pre_sidecar(result)

    def test_composite_timeout_and_survivor_discard_partial_protocol(self) -> None:
        partial = b'{"schema":"forge-bootstrap-composite-result/1"'
        for label, returncode, timed_out, group_survived in (
            ("timeout", None, True, False),
            ("surviving-process", 0, False, True),
        ):
            with self.subTest(label=label):
                raw = CLI.FencedProcessResult(
                    argv=["fixture-composite"],
                    returncode=returncode,
                    duration_seconds=1200.0 if timed_out else 0.01,
                    output=partial,
                    output_digest=CLI.sha256_bytes(partial),
                    timed_out=timed_out,
                    output_limit=False,
                    launch_failed=False,
                    group_survived=group_survived,
                    authorized=True,
                    fence_digest="c" * 64,
                    fence_inode=3,
                )

                decoded = CLI._decode_merge_bootstrap_result(
                    raw, run_bound=False
                )

                self.assertEqual(decoded.output, b"")
                self.assertEqual(
                    decoded.output_digest, CLI.sha256_bytes(b"")
                )
                self.assertIsNone(decoded.metadata)
                self.assertEqual(decoded.timed_out, timed_out)
                self.assertEqual(decoded.group_survived, group_survived)
                if timed_out:
                    self.assert_unbound_composite_failure_is_pre_sidecar(
                        decoded
                    )

    def test_composite_crash_while_collecting_each_constituent_emits_no_result(
        self,
    ) -> None:
        class ConstituentCrash(BaseException):
            pass

        class CrashOnWait:
            def __init__(self, process, label: str):
                self._process = process
                self._label = label
                self.stdout = process.stdout
                self.stderr = process.stderr

            @property
            def returncode(self):
                return self._process.returncode

            def wait(self, *args, **kwargs):
                self._process.wait(*args, **kwargs)
                raise ConstituentCrash(
                    f"fixture crash during {self._label} execution"
                )

            def terminate(self):
                return self._process.terminate()

            def kill(self):
                return self._process.kill()

        fetch_argv = [CLI.sys.executable, "-c", "pass", "fixture-fetch"]
        scope_argv = [
            CLI.sys.executable,
            "-c",
            "import os;os.write(1,b'M\\0src/app.py\\0')",
            "fixture-name-status",
        ]
        patch_argv = [
            CLI.sys.executable,
            "-c",
            "import os;os.write(1,b'patch')",
            "fixture-full-patch",
        ]
        request = {
            "schema": "forge-bootstrap-composite-request/1",
            "worktree": str(self.worktree),
            "git_dir": str(self.worktree / ".git"),
            "candidate_head": self.candidate_head,
            "remote_tip": self.base,
            "run_bound": True,
            "fetch_argv": fetch_argv,
            "cap": 64,
        }
        encoded = CLI.base64.urlsafe_b64encode(
            CLI.canonical_bytes(request)
        ).decode("ascii")
        labels = {
            tuple(fetch_argv): "fetch",
            tuple(scope_argv): "name-status",
            tuple(patch_argv): "full-patch",
        }
        original_popen = subprocess.Popen

        for crash_label, expected_calls in (
            ("fetch", ["fetch"]),
            ("name-status", ["fetch", "name-status"]),
            ("full-patch", ["fetch", "name-status", "full-patch"]),
        ):
            with self.subTest(crash_label=crash_label):
                calls: list[str] = []
                written: list[bytes] = []

                def launch(argv, *args, **kwargs):
                    label = labels[tuple(str(value) for value in argv)]
                    calls.append(label)
                    process = original_popen(argv, *args, **kwargs)
                    return (
                        CrashOnWait(process, label)
                        if label == crash_label
                        else process
                    )

                def capture_write(_descriptor: int, payload: bytes) -> int:
                    written.append(bytes(payload))
                    return len(payload)

                with mock.patch.object(
                    CLI, "_merge_scope_argv", return_value=scope_argv
                ), mock.patch.object(
                    CLI, "_merge_full_patch_argv", return_value=patch_argv
                ), mock.patch.object(
                    CLI.subprocess, "Popen", side_effect=launch
                ), mock.patch.object(
                    CLI.os, "write", side_effect=capture_write
                ), self.assertRaisesRegex(
                    ConstituentCrash,
                    f"fixture crash during {crash_label} execution",
                ):
                    CLI._merge_bootstrap_child_main(encoded)

                self.assertEqual(calls, expected_calls)
                self.assertEqual(written, [])

    def test_composite_and_parent_share_hostile_name_status_parser(self) -> None:
        valid_cases = (
            (b"", ()),
            (
                (
                    b'R0\0src/old"quote.py\0src/new"quote.py\0'
                    b"C01\0src/copy source.py\0src/copy target.py\0"
                    b"R100\0z-last.py\0a-first.py\0"
                    b"M\0src/repeated.py\0M\0src/repeated.py\0"
                ),
                (
                    "a-first.py",
                    'src/copy source.py',
                    "src/copy target.py",
                    'src/new"quote.py',
                    'src/old"quote.py',
                    "src/repeated.py",
                    "z-last.py",
                ),
            ),
        )
        invalid_cases = (
            b"M\0src/unterminated.py",
            b"R101\0old.py\0new.py\0",
            b"C999\0old.py\0new.py\0",
            b"R\0old.py\0new.py\0",
            b"M\0",
            b"M\0/absolute.py\0",
            b"M\0./relative.py\0",
            b"M\0src//repeated.py\0",
            b"M\0src/./dot.py\0",
            b"M\0../escape.py\0",
            b"M\0 leading.py\0",
            b"M\0trailing.py \0",
            b"M\0!exclude.py\0",
            b"M\0^exclude.py\0",
            b"M\0-option.py\0",
            b"M\0:magic.py\0",
            b"M\0*.py\0",
            b"M\0[ab].py\0",
            b"M\0question?.py\0",
            b"M\0.forge/private.json\0",
            b"M\0.codex-orchestrator/private.json\0",
            b"M\0.worktrees/private.py\0",
            b"M\0src\\quoted.py\0",
            b"M\0src/invalid-utf8-\xff.py\0",
            b"M\0src/nul\0tail.py\0",
        )

        fetch_argv = [CLI.sys.executable, "-c", "pass", "fixture-fetch"]
        patch_argv = [CLI.sys.executable, "-c", "pass", "fixture-full-patch"]

        def composite_paths(scope_output: bytes) -> tuple[str, ...] | None:
            scope_argv = [
                CLI.sys.executable,
                "-c",
                f"import os;os.write(1,{scope_output!r})",
                "fixture-name-status",
            ]
            request = {
                "schema": "forge-bootstrap-composite-request/1",
                "worktree": str(self.worktree),
                "git_dir": str(self.worktree / ".git"),
                "candidate_head": self.candidate_head,
                "remote_tip": self.base,
                "run_bound": True,
                "fetch_argv": fetch_argv,
                "cap": CLI.OUTPUT_CAP_BYTES,
            }
            encoded = CLI.base64.urlsafe_b64encode(
                CLI.canonical_bytes(request)
            ).decode("ascii")
            written: list[bytes] = []

            def capture_write(descriptor: int, payload: bytes) -> int:
                self.assertEqual(descriptor, 1)
                written.append(bytes(payload))
                return len(payload)

            with mock.patch.object(
                CLI, "_merge_scope_argv", return_value=scope_argv
            ), mock.patch.object(
                CLI, "_merge_full_patch_argv", return_value=patch_argv
            ), mock.patch.object(
                CLI.os, "write", side_effect=capture_write
            ):
                self.assertEqual(CLI._merge_bootstrap_child_main(encoded), 0)
            self.assertEqual(len(written), 1)
            protocol = json.loads(written[0])
            self.assertEqual(protocol["constituent_order"][:2], ["fetch", "name-status"])
            if protocol["scope"]["exit"] != 0:
                self.assertIsNone(protocol["scope_changed_paths"])
                self.assertIsNone(protocol["full_patch"])
                return None
            self.assertEqual(protocol["scope"]["exit"], 0)
            self.assertEqual(protocol["constituent_order"][-1], "full-patch")
            return tuple(protocol["scope_changed_paths"])

        for raw, expected in valid_cases:
            with self.subTest(kind="valid", raw=raw):
                self.assertEqual(CLI._parse_merge_scope_output(raw), expected)
                self.assertEqual(composite_paths(raw), expected)
        for raw in invalid_cases:
            with self.subTest(kind="invalid", raw=raw):
                with self.assertRaises(ValueError):
                    CLI._parse_merge_scope_output(raw)
                self.assertIsNone(composite_paths(raw))

    def test_bound_name_status_output_remains_capped(self) -> None:
        marker = b"REV12-NAME-STATUS-CAP-PATCH-MUST-NOT-BE-RETAINED"
        bulk = self.worktree / "src" / "bulk"
        bulk.mkdir()
        suffix = "n" * 96
        for index in range(700):
            (bulk / f"{index:04d}-{suffix}.txt").write_bytes(marker)
        self.git_at(self.worktree, "add", "src/bulk")
        self.git_at(
            self.worktree, "commit", "--quiet", "-m", "oversized name status"
        )
        self.candidate_head = self.git_at(self.worktree, "rev-parse", "HEAD")
        scope_result = subprocess.run(
            CLI._merge_scope_argv(
                self.worktree, self.base, self.candidate_head
            ),
            cwd=self.worktree,
            env=CLI._merge_scope_environment(),
            capture_output=True,
            check=False,
        )
        self.assertEqual(scope_result.returncode, 0, scope_result.stderr)
        self.assertGreater(len(scope_result.stdout), CLI.OUTPUT_CAP_BYTES)

        self.open_run()
        engine = CLI.MergeEngine(self.context(run_id=self.run_id))
        decode = CLI._decode_merge_bootstrap_result
        decoded = []

        def capture_decode(*args, **kwargs):
            result = decode(*args, **kwargs)
            decoded.append(copy.deepcopy(result.metadata))
            return result

        with mock.patch.object(
            CLI, "_decode_merge_bootstrap_result", side_effect=capture_decode
        ), self.assertRaises(CLI.Refusal) as caught:
            engine.start_chain(
                str(self.worktree), task=self.task_id, remote_tip=self.base
            )

        self.assertEqual(len(decoded), 1)
        metadata = decoded[0]
        self.assertEqual(metadata["constituent_order"], ["fetch", "name-status"])
        self.assertEqual(
            metadata["scope"]["argv"],
            CLI._merge_scope_argv(
                self.worktree, self.base, self.candidate_head
            ),
        )
        self.assertTrue(metadata["scope"]["output_limit_exceeded"])
        self.assertIsNone(metadata["scope_changed_paths"])
        self.assertIsNone(metadata["full_patch"])
        self.assertEqual(
            metadata["environment_digest"],
            CLI._git_environment_digest(CLI._merge_scope_environment()),
        )
        self.assertEqual(
            caught.exception.reason_code,
            CLI.V2ReasonCode.RUN_TASK_BINDING_INVALID,
        )
        self.assertEqual(caught.exception.chain["state"], "aborted")
        chain_id = str(caught.exception.chain["chain_id"])
        event_bytes = engine.store.events_path(chain_id).read_bytes()
        events = [json.loads(line) for line in event_bytes.splitlines()]
        fetch_result = next(
            event for event in events if event["event"] == "fetch_result"
        )
        self.assertIsNone(fetch_result["payload"]["scope_fetch_binding"])
        self.assertIsNone(fetch_result["payload"]["scope_proof"])
        self.assertIsNone(caught.exception.chain["candidate"])
        self.assertFalse(
            list(engine.store.artifact_dir(chain_id).glob("scope-fetch-*.json"))
        )
        self.assertNotIn(marker, event_bytes)

    def test_unbound_fetch_failure_reports_only_the_launched_prefix(self) -> None:
        unavailable_tip = "f" * 40
        expected_fetch_argv = [
            "git",
            "--no-pager",
            "-C",
            str(self.worktree),
            "cat-file",
            "-e",
            f"{unavailable_tip}^{{commit}}",
        ]
        engine = CLI.MergeEngine(self.context())
        decode = CLI._decode_merge_bootstrap_result
        decoded = []

        def capture_decode(*args, **kwargs):
            result = decode(*args, **kwargs)
            decoded.append(copy.deepcopy(result.metadata))
            return result

        with mock.patch.object(
            CLI, "_decode_merge_bootstrap_result", side_effect=capture_decode
        ), self.assertRaises(CLI.Refusal) as caught:
            engine.start_chain(
                str(self.worktree), remote_tip=unavailable_tip
            )

        self.assertEqual(
            caught.exception.reason_code, CLI.V2ReasonCode.FETCH_FAILED
        )
        self.assertEqual(len(decoded), 1)
        metadata = decoded[0]
        self.assertEqual(metadata["constituent_order"], ["fetch"])
        self.assertEqual(metadata["fetch"]["argv"], expected_fetch_argv)
        self.assertNotEqual(metadata["fetch"]["exit"], 0)
        self.assertFalse(metadata["fetch"]["launch_failed"])
        self.assertFalse(metadata["fetch"]["output_limit_exceeded"])
        self.assertIsNone(metadata["resolved_tip"])
        self.assertIsNone(metadata["scope"])
        self.assertIsNone(metadata["scope_changed_paths"])
        self.assertIsNone(metadata["full_patch"])
        self.assertEqual(
            metadata["environment_digest"],
            CLI._git_environment_digest(CLI._merge_scope_environment()),
        )
        state = caught.exception.chain
        self.assertEqual(state["state"], "classifying")
        self.assertIsNone(state["candidate"])
        chain_id = str(state["chain_id"])
        event_bytes = engine.store.events_path(chain_id).read_bytes()
        events = [json.loads(line) for line in event_bytes.splitlines()]
        fetch_result = events[-1]
        self.assertEqual(fetch_result["event"], "fetch_result")
        self.assertIsNone(fetch_result["payload"]["scope_fetch_binding"])
        self.assertIsNone(fetch_result["payload"]["scope_proof"])
        self.assertNotIn(b"constituent_order", event_bytes)
        self.assertFalse(
            list(engine.store.artifact_dir(chain_id).glob("scope-fetch-*.json"))
        )

    def test_unbound_oversized_full_patch_streams_to_digest_only(self) -> None:
        marker = b"REV12-FULL-PATCH-MUST-NOT-BE-RETAINED"
        for index in range(6):
            path = self.worktree / "payload" / f"segment-{index}.txt"
            path.parent.mkdir(exist_ok=True)
            unit = marker + f"-{index:02d}-".encode("ascii")
            path.write_bytes(
                (unit * ((32 * 1024 // len(unit)) + 1))[: 32 * 1024]
            )
            self.git_at(self.worktree, "add", str(path.relative_to(self.worktree)))
            self.git_at(
                self.worktree,
                "commit",
                "--quiet",
                "-m",
                f"oversized patch segment {index}",
            )
        self.candidate_head = self.git_at(self.worktree, "rev-parse", "HEAD")
        patch_length, patch_digest = self.stream_exact_patch()
        self.assertGreater(patch_length, CLI.OUTPUT_CAP_BYTES)

        _engine, store, state, outcome = self.start_lifecycle()
        event_bytes = store.events_path(str(outcome.chain_id)).read_bytes()
        events = [json.loads(line) for line in event_bytes.splitlines()]
        fetch_result = next(
            event for event in reversed(events) if event["event"] == "fetch_result"
        )
        binding = fetch_result["payload"]["scope_fetch_binding"]

        self.assertTrue(outcome.ok)
        self.assertEqual(state["state"], "verifying")
        self.assertEqual(binding["full_patch_output_digest"], patch_digest)
        self.assertEqual(state["candidate"]["diff_sha256"], patch_digest)
        self.assertFalse(binding["child_result"]["output_limit_exceeded"])
        self.assertEqual(
            binding["child_result"]["output_digest"], CLI.sha256_bytes(b"")
        )
        canonical = store.common_root / binding["publication"]["canonical_path"]
        sidecar_bytes = canonical.read_bytes()
        self.assertNotIn(marker, event_bytes)
        self.assertNotIn(marker, sidecar_bytes)
        self.assertFalse(
            any("patch" in key for key in binding["child_result"])
        )
        self.assertNotIn("output", binding["child_result"])

    def test_composite_bootstrap_streaming_control_is_load_bearing(self) -> None:
        engine = CLI.MergeEngine(self.context())
        with mock.patch.object(
            CLI,
            "MERGE_INTEGRATION_CONTROLS",
            CLI.MERGE_INTEGRATION_CONTROLS - {"composite-bootstrap-streaming"},
        ), self.assertRaisesRegex(
            CLI.FrozenError,
            "merge integration control is unavailable: composite-bootstrap-streaming",
        ):
            engine.start_chain(str(self.worktree), remote_tip=self.base)
        chain_ids = engine.store.list_ids(family="merge")
        if chain_ids:
            state = engine.store.load(chain_ids[0])
            self.assertIsNone(state["candidate"])
            self.assertFalse(
                list(engine.store.artifact_dir(chain_ids[0]).glob("scope-fetch-*.json"))
            )

    def test_scope_sidecar_classifier_admits_exactly_four_crash_states(self) -> None:
        starter, state = self.crash_after_scope_sidecar_publication()
        intent_digest = CLI._merge_event_digest(
            starter.store, self.chain_id, "fetch_intent"
        )
        self.assertIsNotNone(intent_digest)
        fence = CLI._discover_merge_scope_fence_from_sidecar(
            starter.store,
            state,
            fetch_intent_digest=intent_digest,
        )
        self.assertIsNotNone(fence)
        request = state["integration"]["intent"]["scope_request"]
        names = CLI._merge_scope_binding_names(
            self.chain_id, intent_digest, fence
        )
        canonical = starter.store.artifact_dir(self.chain_id) / names[0]
        temporary = starter.store.artifact_dir(self.chain_id) / names[1]

        def topology() -> str:
            return CLI._classify_merge_scope_binding(
                starter.store,
                state,
                fetch_intent_digest=intent_digest,
                scope_request=request,
                fence=fence,
            ).topology

        self.assertEqual(topology(), "canonical-one-link")
        wrong_parent = json.loads(canonical.read_bytes())
        wrong_parent["retained_inflight"]["path"] = "/tmp/agent-rebase.inflight"
        wrong_parent_body = {
            key: value for key, value in wrong_parent.items() if key != "digest"
        }
        wrong_parent["digest"] = CLI.sha256_bytes(
            CLI.canonical_bytes(wrong_parent_body)
        )
        validator = CLI._merge_scope_binding_validator(
            state,
            fetch_intent_digest=intent_digest,
            scope_request=request,
            fence=fence,
        )
        with self.assertRaises(ValueError):
            validator(wrong_parent)
        os.link(canonical, temporary)
        self.assertEqual(topology(), "same-inode-two-link")
        race_link = canonical.with_name(f"{canonical.name}.race-link")
        original_unlink = CLI._unlink_merge_scope_temporary_at

        def add_link_before_unlink(*args, **kwargs):
            os.link(canonical, race_link)
            return original_unlink(*args, **kwargs)

        with mock.patch.object(
            CLI,
            "_unlink_merge_scope_temporary_at",
            side_effect=add_link_before_unlink,
        ), self.assertRaises(CLI.FrozenError):
            CLI._resume_merge_scope_binding(
                starter.store,
                state,
                fetch_intent_digest=intent_digest,
                scope_request=request,
                fence=fence,
            )
        self.assertTrue(temporary.exists())
        self.assertTrue(race_link.exists())
        race_link.unlink()
        third = canonical.with_name(f"{canonical.name}.extra-link")
        os.link(canonical, third)
        with self.assertRaises((CLI.FrozenError, OSError)):
            topology()
        third.unlink()
        resumed = CLI._resume_merge_scope_binding(
            starter.store,
            state,
            fetch_intent_digest=intent_digest,
            scope_request=request,
            fence=fence,
        )
        self.assertIsNotNone(resumed)
        self.assertEqual(topology(), "canonical-one-link")
        self.assertFalse(temporary.exists())
        os.link(canonical, temporary)
        canonical.unlink()
        self.assertEqual(topology(), "temporary-one-link")
        resumed = CLI._resume_merge_scope_binding(
            starter.store,
            state,
            fetch_intent_digest=intent_digest,
            scope_request=request,
            fence=fence,
        )
        self.assertIsNotNone(resumed)
        self.assertEqual(topology(), "canonical-one-link")
        canonical.unlink()
        self.assertEqual(topology(), "absent")
        conflicting = starter.store.artifact_dir(self.chain_id) / (
            f"scope-fetch-{intent_digest}-conflicting-name.json"
        )
        conflicting.write_bytes(b"{}\n")
        with self.assertRaises(CLI.FrozenError):
            CLI._discover_merge_scope_fence_from_sidecar(
                starter.store,
                state,
                fetch_intent_digest=intent_digest,
            )

    def test_bound_sidecar_recovery_aborts_without_rerunning_a_constituent(self) -> None:
        starter, _interrupted = self.crash_after_scope_sidecar_publication()
        engine = CLI.MergeEngine(self.context(chain_id=self.chain_id))
        before = starter.store.events_path(self.chain_id).read_bytes()
        with mock.patch.object(
            CLI,
            "MERGE_INTEGRATION_CONTROLS",
            CLI.MERGE_INTEGRATION_CONTROLS - {"scope-sidecar-recovery"},
        ), self.assertRaisesRegex(
            CLI.FrozenError,
            "merge integration control is unavailable: scope-sidecar-recovery",
        ):
            engine.recover()
        self.assertEqual(starter.store.events_path(self.chain_id).read_bytes(), before)

        with mock.patch.object(
            CLI,
            "run_fenced_command",
            side_effect=AssertionError(
                "bound sidecar recovery must not rerun the composite child"
            ),
        ), mock.patch.object(
            CLI,
            "_derive_merge_scope",
            side_effect=AssertionError(
                "bound sidecar recovery must not rerun name-status"
            ),
        ), self.assertRaises(CLI.Refusal) as caught:
            engine.recover()
        current = starter.store.load(self.chain_id)
        self.assertEqual(
            caught.exception.reason_code,
            CLI.V2ReasonCode.RUN_TASK_BINDING_INVALID,
        )
        self.assertEqual(current["state"], "aborted")
        self.assertIsNone(current["candidate"])
        events = [
            json.loads(line)
            for line in starter.store.events_path(self.chain_id)
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        names = [event["event"] for event in events]
        self.assertEqual(names.count("fetch_intent"), 1)
        self.assertEqual(names.count("fetch_result"), 1)
        fetch_result = next(
            event for event in events if event["event"] == "fetch_result"
        )
        self.assertEqual(
            fetch_result["payload"]["scope_fetch_binding"]["schema"],
            "forge-run-scope-fetch-binding/2",
        )
        self.assertIsNone(fetch_result["payload"]["scope_proof"])

    def test_surviving_fence_requires_reservation_held_classification_before_clear(self) -> None:
        starter, interrupted = self.crash_after_scope_sidecar_publication(
            bound=False
        )
        common_dir = Path(interrupted["worktree"]["common_dir"])
        fence_path = common_dir / CLI.COMMON_LOCK_INFLIGHT_NAME
        reservation_path = common_dir / CLI.COMMON_LOCK_RECOVERY_NAME
        original_inode = fence_path.stat().st_ino

        with self.assertRaises(CLI.CommonLockUnavailable):
            CLI.acquire_common_lock(
                common_dir,
                owner_kind="merge",
                chain_id=self.chain_id,
                operation="recover",
                timeout=1,
                no_transaction_record=True,
            )
        self.assertEqual(fence_path.stat().st_ino, original_inode)
        self.assertFalse(reservation_path.exists())

        observed: list[str] = []

        def classify(reservation, fence):
            self.assertTrue(reservation.matches_chain(self.chain_id))
            self.assertTrue(reservation_path.exists())
            self.assertEqual(fence_path.stat().st_ino, original_inode)
            self.assertEqual(fence.inode, original_inode)
            observed.append("classified")

        with mock.patch.object(
            CLI,
            "COMMON_LOCK_CONTROLS",
            CLI.COMMON_LOCK_CONTROLS
            - {"reservation-held-lifecycle-classification"},
        ), self.assertRaisesRegex(
            CLI.FrozenError,
            "common-lock control is unavailable: reservation-held-lifecycle-classification",
        ):
            CLI.acquire_common_lock(
                common_dir,
                owner_kind="merge",
                chain_id=self.chain_id,
                operation="recover",
                timeout=1,
                no_transaction_record=True,
                recovery_classifier=classify,
            )
        self.assertFalse(observed)
        self.assertEqual(fence_path.stat().st_ino, original_inode)
        self.assertFalse(reservation_path.exists())

        boundaries: list[str] = []
        recovered = CLI.acquire_common_lock(
            common_dir,
            owner_kind="merge",
            chain_id=self.chain_id,
            operation="recover",
            timeout=1,
            no_transaction_record=True,
            recovery_classifier=classify,
            boundary=boundaries.append,
        )
        try:
            self.assertEqual(observed, ["classified"])
            self.assertFalse(fence_path.exists())
            self.assertFalse(reservation_path.exists())
            self.assertLess(
                boundaries.index("recovery-fence-lifecycle-classified"),
                boundaries.index("recovery-fence-cleared"),
            )
        finally:
            recovered.release()

    def test_event_lock_deadline_refuses_cross_process_holder(self) -> None:
        store = CLI.MergeEngine(self.context()).store
        ready_read, ready_write = os.pipe()
        release_read, release_write = os.pipe()
        child = os.fork()
        if child == 0:
            try:
                os.close(ready_read)
                os.close(release_write)
                with store.event_lock(self.chain_id):
                    os.write(ready_write, b"1")
                    os.read(release_read, 1)
            except BaseException:
                os._exit(125)
            os._exit(0)

        os.close(ready_write)
        os.close(release_read)
        try:
            self.assertEqual(os.read(ready_read, 1), b"1")
            started = time.monotonic()
            with self.assertRaisesRegex(
                TimeoutError,
                "cross-process descriptor lock acquisition exhausted the shared deadline",
            ):
                with store.event_lock(
                    self.chain_id,
                    deadline=time.monotonic() + 0.05,
                ):
                    self.fail("contended event lock crossed its shared deadline")
            self.assertLess(time.monotonic() - started, 1.0)
        finally:
            os.close(ready_read)
            try:
                os.write(release_write, b"1")
            except OSError:
                pass
            os.close(release_write)
            _waited, status = os.waitpid(child, 0)
        self.assertTrue(os.WIFEXITED(status), status)
        self.assertEqual(os.WEXITSTATUS(status), 0)

    def assert_nonrecover_refresh_cannot_clear_surviving_fence(
        self, *, use_flock: bool
    ) -> None:
        starter, interrupted = self.crash_after_scope_sidecar_publication(
            bound=False
        )
        common_dir = Path(interrupted["worktree"]["common_dir"])
        fence_path = common_dir / CLI.COMMON_LOCK_INFLIGHT_NAME
        reservation_path = common_dir / CLI.COMMON_LOCK_RECOVERY_NAME
        outer_path = common_dir / CLI.COMMON_LOCK_INTENT_NAME
        inner_path = (
            common_dir
            / CLI.COMMON_LOCK_DIRECTORY_NAME
            / CLI.COMMON_LOCK_OWNER_NAME
        )
        before_events = starter.store.events_path(self.chain_id).read_bytes()
        state_path = starter.store.state_path(self.chain_id)
        before_state = state_path.read_bytes()
        sidecars = list(
            starter.store.artifact_dir(self.chain_id).glob("scope-fetch-*.json")
        )
        self.assertEqual(len(sidecars), 1)
        before_sidecar = sidecars[0].read_bytes()
        before_sidecar_inode = sidecars[0].stat().st_ino
        before_fence = fence_path.read_bytes()
        before_fence_inode = fence_path.stat().st_ino
        before_outer = outer_path.read_bytes()
        before_outer_inode = outer_path.stat().st_ino
        before_inner = inner_path.read_bytes()
        before_inner_inode = inner_path.stat().st_ino
        acquire = CLI.acquire_common_lock

        def short_acquire(*args, **kwargs):
            kwargs["timeout"] = 0.05
            kwargs["use_flock"] = use_flock
            return acquire(*args, **kwargs)

        engine = CLI.MergeEngine(self.context(chain_id=self.chain_id))
        with mock.patch.object(
            CLI, "acquire_common_lock", side_effect=short_acquire
        ), self.assertRaises(CLI.CommonLockUnavailable) as caught:
            engine.refresh(remote_tip=self.base)

        self.assertEqual(
            caught.exception.reason_code,
            CLI.V2ReasonCode.REBASE_LOCK_UNAVAILABLE,
        )
        self.assertEqual(
            starter.store.events_path(self.chain_id).read_bytes(), before_events
        )
        self.assertEqual(state_path.read_bytes(), before_state)
        self.assertEqual(sidecars[0].read_bytes(), before_sidecar)
        self.assertEqual(sidecars[0].stat().st_ino, before_sidecar_inode)
        self.assertEqual(fence_path.read_bytes(), before_fence)
        self.assertEqual(fence_path.stat().st_ino, before_fence_inode)
        self.assertEqual(outer_path.read_bytes(), before_outer)
        self.assertEqual(outer_path.stat().st_ino, before_outer_inode)
        self.assertEqual(inner_path.read_bytes(), before_inner)
        self.assertEqual(inner_path.stat().st_ino, before_inner_inode)
        self.assertFalse(reservation_path.exists())
        self.assertFalse(list(common_dir.glob(".agent-rebase.recover.*.tmp")))
        self.assertEqual(CLI.inspect_common_lock(common_dir).topology, "complete")

    def test_nonrecover_refresh_refuses_surviving_fence_with_flock(self) -> None:
        self.assert_nonrecover_refresh_cannot_clear_surviving_fence(
            use_flock=True
        )

    def test_nonrecover_refresh_refuses_surviving_fence_portable_only(self) -> None:
        self.assert_nonrecover_refresh_cannot_clear_surviving_fence(
            use_flock=False
        )

    def assert_outer_owner_absent_nonrecover_refresh_refuses(
        self, *, use_flock: bool
    ) -> None:
        starter, interrupted = self.crash_after_scope_sidecar_publication(
            bound=False
        )
        common_dir = Path(interrupted["worktree"]["common_dir"])
        fence_path = common_dir / CLI.COMMON_LOCK_INFLIGHT_NAME
        reservation_path = common_dir / CLI.COMMON_LOCK_RECOVERY_NAME
        state_path = starter.store.state_path(self.chain_id)
        events_path = starter.store.events_path(self.chain_id)
        sidecars = list(
            starter.store.artifact_dir(self.chain_id).glob("scope-fetch-*.json")
        )
        self.assertEqual(len(sidecars), 1)
        self.remove_crashed_common_owner(common_dir)
        before_state = state_path.read_bytes()
        before_events = events_path.read_bytes()
        before_sidecar = sidecars[0].read_bytes()
        before_sidecar_inode = sidecars[0].stat().st_ino
        before_fence = fence_path.read_bytes()
        before_fence_inode = fence_path.stat().st_ino
        acquire = CLI.acquire_common_lock
        acquisitions = []

        def short_acquire(*args, **kwargs):
            self.assertEqual(kwargs["operation"], "refresh")
            self.assertIsNone(kwargs.get("recovery_classifier"))
            acquisitions.append(kwargs["operation"])
            kwargs["timeout"] = 0.05
            kwargs["use_flock"] = use_flock
            kwargs["pid_probe"] = lambda _pid: "dead"
            kwargs["group_probe"] = lambda _pgid: "dead"
            return acquire(*args, **kwargs)

        engine = CLI.MergeEngine(self.context(chain_id=self.chain_id))
        with mock.patch.object(
            CLI, "acquire_common_lock", side_effect=short_acquire
        ), mock.patch.object(
            CLI,
            "_classify_merge_scope_binding",
            side_effect=AssertionError(
                "ordinary acquisition must not classify a surviving fence"
            ),
        ), self.assertRaises(CLI.CommonLockUnavailable) as caught:
            engine.refresh(remote_tip=self.base)

        self.assertEqual(acquisitions, ["refresh"])
        self.assertEqual(
            caught.exception.reason_code,
            CLI.V2ReasonCode.REBASE_LOCK_UNAVAILABLE,
        )
        self.assertEqual(state_path.read_bytes(), before_state)
        self.assertEqual(events_path.read_bytes(), before_events)
        self.assertEqual(sidecars[0].read_bytes(), before_sidecar)
        self.assertEqual(sidecars[0].stat().st_ino, before_sidecar_inode)
        self.assertEqual(fence_path.read_bytes(), before_fence)
        self.assertEqual(fence_path.stat().st_ino, before_fence_inode)
        self.assertFalse(reservation_path.exists())
        self.assertFalse(list(common_dir.glob(".agent-rebase.recover.*.tmp")))
        self.assertEqual(CLI.inspect_common_lock(common_dir).topology, "free")

    def test_outer_owner_absent_nonrecover_refresh_refuses_with_flock(self) -> None:
        self.assert_outer_owner_absent_nonrecover_refresh_refuses(
            use_flock=True
        )

    def test_outer_owner_absent_nonrecover_refresh_refuses_portable_only(
        self,
    ) -> None:
        self.assert_outer_owner_absent_nonrecover_refresh_refuses(
            use_flock=False
        )

    def assert_outer_owner_absent_fence_recovery(self, *, use_flock: bool) -> None:
        self.assertTrue(
            use_flock,
            "outer-owner-absent recovery requires demonstrably held flock",
        )
        starter, interrupted = self.crash_after_scope_sidecar_publication(
            bound=False
        )
        common_dir = Path(interrupted["worktree"]["common_dir"])
        fence_path = common_dir / CLI.COMMON_LOCK_INFLIGHT_NAME
        reservation_path = common_dir / CLI.COMMON_LOCK_RECOVERY_NAME
        before_fence_inode = fence_path.stat().st_ino
        self.remove_crashed_common_owner(common_dir)
        classified: list[int] = []
        boundaries: list[str] = []

        def classify(reservation, fence):
            self.assertTrue(reservation_path.is_file())
            self.assertEqual(fence_path.stat().st_ino, before_fence_inode)
            self.classify_crashed_bootstrap_fence(
                starter, interrupted, reservation, fence
            )
            classified.append(fence.inode)

        recovered = CLI.acquire_common_lock(
            common_dir,
            owner_kind="merge",
            chain_id=self.chain_id,
            operation="recover",
            timeout=1,
            use_flock=use_flock,
            pid_probe=lambda _pid: "dead",
            group_probe=lambda _pgid: "dead",
            no_transaction_record=True,
            recovery_classifier=classify,
            boundary=boundaries.append,
        )
        try:
            self.assertEqual(classified, [before_fence_inode])
            self.assertFalse(fence_path.exists())
            self.assertFalse(reservation_path.exists())
            self.assertLess(
                boundaries.index("flock-record-fsynced"),
                boundaries.index("recovery-reservation-published"),
            )
            self.assertLess(
                boundaries.index("recovery-reservation-published"),
                boundaries.index("recovery-fence-lifecycle-classified"),
            )
            self.assertLess(
                boundaries.index("recovery-fence-lifecycle-classified"),
                boundaries.index("recovery-fence-cleared"),
            )
        finally:
            recovered.release()
        self.assertEqual(CLI.inspect_common_lock(common_dir).topology, "free")

    def test_outer_owner_absent_fence_recovery_with_flock(self) -> None:
        self.assert_outer_owner_absent_fence_recovery(use_flock=True)

    def test_outer_owner_absent_fence_recovery_with_portable_owner_only(self) -> None:
        starter, interrupted = self.crash_after_scope_sidecar_publication(
            bound=False
        )
        common_dir = Path(interrupted["worktree"]["common_dir"])
        fence_path = common_dir / CLI.COMMON_LOCK_INFLIGHT_NAME
        reservation_path = common_dir / CLI.COMMON_LOCK_RECOVERY_NAME
        state_path = starter.store.state_path(self.chain_id)
        events_path = starter.store.events_path(self.chain_id)
        sidecars = list(
            starter.store.artifact_dir(self.chain_id).glob("scope-fetch-*.json")
        )
        self.assertEqual(len(sidecars), 1)
        self.remove_crashed_common_owner(common_dir)
        before_state = state_path.read_bytes()
        before_events = events_path.read_bytes()
        before_sidecar = sidecars[0].read_bytes()
        before_sidecar_inode = sidecars[0].stat().st_ino
        before_fence = fence_path.read_bytes()
        before_fence_inode = fence_path.stat().st_ino
        classified = []

        def forbidden_classification(_reservation, _fence):
            classified.append(True)
            raise AssertionError(
                "portable-only owner must not classify an orphaned fence"
            )

        with self.assertRaises(CLI.CommonLockUnavailable):
            CLI.acquire_common_lock(
                common_dir,
                owner_kind="merge",
                chain_id=self.chain_id,
                operation="recover",
                timeout=0.05,
                use_flock=False,
                pid_probe=lambda _pid: "dead",
                group_probe=lambda _pgid: "dead",
                no_transaction_record=True,
                recovery_classifier=forbidden_classification,
            )

        self.assertFalse(classified)
        self.assertEqual(state_path.read_bytes(), before_state)
        self.assertEqual(events_path.read_bytes(), before_events)
        self.assertEqual(sidecars[0].read_bytes(), before_sidecar)
        self.assertEqual(sidecars[0].stat().st_ino, before_sidecar_inode)
        self.assertEqual(fence_path.read_bytes(), before_fence)
        self.assertEqual(fence_path.stat().st_ino, before_fence_inode)
        self.assertFalse(reservation_path.exists())
        self.assertFalse(list(common_dir.glob(".agent-rebase.recover.*.tmp")))
        self.assertEqual(CLI.inspect_common_lock(common_dir).topology, "free")

    def test_outer_owner_absent_classifier_failure_cleans_only_reservation(self) -> None:
        starter, interrupted = self.crash_after_scope_sidecar_publication(
            bound=False
        )
        common_dir = Path(interrupted["worktree"]["common_dir"])
        fence_path = common_dir / CLI.COMMON_LOCK_INFLIGHT_NAME
        reservation_path = common_dir / CLI.COMMON_LOCK_RECOVERY_NAME
        state_path = starter.store.state_path(self.chain_id)
        events_path = starter.store.events_path(self.chain_id)
        sidecars = list(
            starter.store.artifact_dir(self.chain_id).glob("scope-fetch-*.json")
        )
        self.assertEqual(len(sidecars), 1)
        before_fence = fence_path.read_bytes()
        before_fence_inode = fence_path.stat().st_ino
        self.remove_crashed_common_owner(common_dir)
        before_state = state_path.read_bytes()
        before_events = events_path.read_bytes()
        before_sidecar = sidecars[0].read_bytes()
        before_sidecar_inode = sidecars[0].stat().st_ino
        observed: list[str] = []

        def refuse_classification(reservation, fence):
            self.assertTrue(reservation_path.is_file())
            self.assertTrue(reservation.matches_chain(self.chain_id))
            self.assertEqual(fence.inode, before_fence_inode)
            observed.append("classification-refused")
            raise OSError("fixture lifecycle classification refusal")

        with self.assertRaises(CLI.CommonLockUnavailable):
            CLI.acquire_common_lock(
                common_dir,
                owner_kind="merge",
                chain_id=self.chain_id,
                operation="recover",
                timeout=0.1,
                use_flock=True,
                pid_probe=lambda _pid: "dead",
                group_probe=lambda _pgid: "dead",
                no_transaction_record=True,
                recovery_classifier=refuse_classification,
            )

        self.assertTrue(observed)
        self.assertEqual(set(observed), {"classification-refused"})
        self.assertEqual(state_path.read_bytes(), before_state)
        self.assertEqual(events_path.read_bytes(), before_events)
        self.assertEqual(sidecars[0].read_bytes(), before_sidecar)
        self.assertEqual(sidecars[0].stat().st_ino, before_sidecar_inode)
        self.assertEqual(fence_path.read_bytes(), before_fence)
        self.assertEqual(fence_path.stat().st_ino, before_fence_inode)
        self.assertFalse(reservation_path.exists())
        self.assertFalse(list(common_dir.glob(".agent-rebase.recover.*.tmp")))
        self.assertEqual(CLI.inspect_common_lock(common_dir).topology, "free")

    def assert_post_result_original_fence_recovers(
        self, *, succeeded: bool
    ) -> None:
        starter, state, fetch_result = (
            self.crash_after_bootstrap_result_before_fence_release(
                succeeded=succeeded
            )
        )
        common_dir = Path(state["worktree"]["common_dir"])
        fence_path = common_dir / CLI.COMMON_LOCK_INFLIGHT_NAME
        reservation_path = common_dir / CLI.COMMON_LOCK_RECOVERY_NAME
        state_path = starter.store.state_path(self.chain_id)
        events_path = starter.store.events_path(self.chain_id)
        before_state = state_path.read_bytes()
        before_events = events_path.read_bytes()
        before_fence_inode = fence_path.stat().st_ino
        binding = fetch_result["payload"]["scope_fetch_binding"]
        sidecars = list(
            starter.store.artifact_dir(self.chain_id).glob("scope-fetch-*.json")
        )
        if succeeded:
            self.assertEqual(state["state"], "classifying")
            self.assertIsNone(state["tier"])
            self.assertIsInstance(state["candidate"], dict)
            self.assertIsInstance(binding, dict)
            self.assertEqual(len(sidecars), 1)
            self.assertEqual(
                binding["retained_inflight"]["inode"], before_fence_inode
            )
            before_sidecar = sidecars[0].read_bytes()
            before_sidecar_inode = sidecars[0].stat().st_ino
        else:
            self.assertEqual(state["state"], "classifying")
            self.assertEqual(
                state["integration"]["condition"], "fetch-failed"
            )
            self.assertIsNone(binding)
            self.assertIsNone(fetch_result["payload"]["scope_proof"])
            self.assertFalse(sidecars)
            before_sidecar = None
            before_sidecar_inode = None

        boundaries: list[str] = []
        acquire = CLI.acquire_common_lock

        def capture_recovery(*args, **kwargs):
            kwargs["boundary"] = boundaries.append
            kwargs["timeout"] = 1
            kwargs["use_flock"] = True
            kwargs["pid_probe"] = lambda _pid: "dead"
            kwargs["group_probe"] = lambda _pgid: "dead"
            return acquire(*args, **kwargs)

        engine = CLI.MergeEngine(self.context(chain_id=self.chain_id))
        with mock.patch.object(
            CLI, "acquire_common_lock", side_effect=capture_recovery
        ), mock.patch.object(
            CLI,
            "run_fenced_command",
            side_effect=AssertionError(
                "post-result fence recovery must not rerun a constituent"
            ),
        ):
            with engine._recording_common_lock(
                common_dir,
                chain_id=self.chain_id,
                operation="recover",
            ) as recovered:
                recovered.assert_held()
                self.assertFalse(fence_path.exists())
                self.assertFalse(reservation_path.exists())

        self.assertLess(
            boundaries.index("recovery-reservation-published"),
            boundaries.index("recovery-fence-lifecycle-classified"),
        )
        self.assertLess(
            boundaries.index("recovery-fence-lifecycle-classified"),
            boundaries.index("recovery-fence-cleared"),
        )
        after_state = json.loads(state_path.read_bytes())
        before_state_value = json.loads(before_state)
        for timestamp in ("last_event_at", "inactive_after"):
            after_state.pop(timestamp)
            before_state_value.pop(timestamp)
        self.assertEqual(after_state, before_state_value)
        before_event_lines = before_events.splitlines()
        after_event_lines = events_path.read_bytes().splitlines()
        self.assertEqual(after_event_lines[:-1], before_event_lines)
        recovery_event = json.loads(after_event_lines[-1])
        self.assertEqual(recovery_event["event"], "condition_recorded")
        self.assertEqual(recovery_event["payload"]["delta"], {})
        recovery_proof = recovery_event["payload"]["recovery_proof"]
        self.assertEqual(
            recovery_proof["schema"],
            "forge-merge-fence-recovery-proof/1",
        )
        self.assertEqual(
            recovery_proof["lifecycle"]["classification"],
            "fetch-result-persisted",
        )
        self.assertEqual(
            recovery_proof["digest"],
            CLI.sha256_bytes(
                CLI.canonical_bytes(
                    {
                        name: value
                        for name, value in recovery_proof.items()
                        if name != "digest"
                    }
                )
            ),
        )
        if succeeded:
            self.assertEqual(sidecars[0].read_bytes(), before_sidecar)
            self.assertEqual(sidecars[0].stat().st_ino, before_sidecar_inode)
        self.assertFalse(fence_path.exists())
        self.assertFalse(reservation_path.exists())
        self.assertFalse(list(common_dir.glob(".agent-rebase.recover.*.tmp")))
        self.assertEqual(CLI.inspect_common_lock(common_dir).topology, "free")

    def test_success_result_and_sidecar_precede_original_fence_recovery(
        self,
    ) -> None:
        self.assert_post_result_original_fence_recovers(succeeded=True)

    def test_failed_result_and_absent_sidecar_precede_original_fence_recovery(
        self,
    ) -> None:
        self.assert_post_result_original_fence_recovers(succeeded=False)

    def test_unbound_sidecar_recovery_binds_generation_without_rerun(self) -> None:
        starter, _interrupted = self.crash_after_scope_sidecar_publication(
            bound=False
        )
        engine = CLI.MergeEngine(self.context(chain_id=self.chain_id))
        with mock.patch.object(
            CLI,
            "run_fenced_command",
            side_effect=AssertionError(
                "unbound sidecar recovery must not rerun the composite child"
            ),
        ), mock.patch.object(
            CLI,
            "_derive_merge_scope",
            side_effect=AssertionError(
                "unbound sidecar recovery must not launch name-status"
            ),
        ):
            recovered = engine.recover()
        current = starter.store.load(self.chain_id)
        self.assertTrue(recovered.ok)
        self.assertEqual(current["state"], "verifying")
        self.assertEqual(current["candidate"]["remote_tip"], self.base)
        events = [
            json.loads(line)
            for line in starter.store.events_path(self.chain_id)
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        names = [event["event"] for event in events]
        self.assertEqual(names.count("fetch_intent"), 1)
        self.assertEqual(names.count("fetch_result"), 1)
        fetch_result = next(
            event for event in events if event["event"] == "fetch_result"
        )
        binding = fetch_result["payload"]["scope_fetch_binding"]
        self.assertEqual(binding["schema"], "forge-run-scope-fetch-binding/2")
        self.assertIsNone(fetch_result["payload"]["scope_proof"])
        self.assertEqual(
            current["candidate"]["diff_sha256"],
            binding["full_patch_output_digest"],
        )

    def test_unbound_divergent_sidecar_recovery_freezes_without_rerun(self) -> None:
        starter, _interrupted = self.crash_after_scope_sidecar_publication(
            bound=False
        )
        sidecars = list(
            starter.store.artifact_dir(self.chain_id).glob("scope-fetch-*.json")
        )
        self.assertEqual(len(sidecars), 1)
        sidecar = sidecars[0]
        binding = json.loads(sidecar.read_bytes())
        binding["remote_tip"] = "f" * 40
        body = {key: value for key, value in binding.items() if key != "digest"}
        binding["digest"] = CLI.sha256_bytes(CLI.canonical_bytes(body))
        divergent = CLI.canonical_bytes(binding) + b"\n"
        sidecar.write_bytes(divergent)
        before_events = starter.store.events_path(self.chain_id).read_bytes()

        engine = CLI.MergeEngine(self.context(chain_id=self.chain_id))
        with mock.patch.object(
            CLI,
            "run_fenced_command",
            side_effect=AssertionError(
                "divergent sidecar recovery must not rerun the composite child"
            ),
        ), self.assertRaises(CLI.FrozenError):
            engine.recover()

        self.assertEqual(
            starter.store.events_path(self.chain_id).read_bytes(), before_events
        )
        self.assertEqual(sidecar.read_bytes(), divergent)

    def test_bare_recover_both_absent_aborts_without_fetch_or_scope(self) -> None:
        starter, _interrupted = self.crash_before_scope_sidecar_publication(
            bound=True
        )
        engine = CLI.MergeEngine(self.context(chain_id=self.chain_id))
        with mock.patch.object(
            CLI,
            "run_fenced_command",
            side_effect=AssertionError("both-absent recovery must not refetch"),
        ), mock.patch.object(
            CLI,
            "_derive_merge_scope",
            side_effect=AssertionError("both-absent recovery must not derive scope"),
        ), self.assertRaises(CLI.Refusal) as caught:
            engine.recover()
        current = starter.store.load(self.chain_id)
        self.assertEqual(
            caught.exception.reason_code,
            CLI.V2ReasonCode.RUN_TASK_BINDING_INVALID,
        )
        self.assertEqual(current["state"], "aborted")
        fetch_results = [
            event
            for event in (
                json.loads(line)
                for line in starter.store.events_path(self.chain_id)
                .read_text(encoding="utf-8")
                .splitlines()
            )
            if event["event"] == "fetch_result"
        ]
        self.assertEqual(len(fetch_results), 1)
        self.assertIsNone(fetch_results[0]["payload"]["scope_fetch_binding"])
        self.assertIsNone(fetch_results[0]["payload"]["scope_proof"])

    def test_unbound_pre_sidecar_crash_recovers_as_fetch_failure(self) -> None:
        starter, interrupted = self.crash_before_scope_sidecar_publication(
            bound=False
        )
        common_dir = Path(interrupted["worktree"]["common_dir"])
        fence_path = common_dir / CLI.COMMON_LOCK_INFLIGHT_NAME
        original_fence_inode = fence_path.stat().st_ino
        engine = CLI.MergeEngine(self.context(chain_id=self.chain_id))
        with mock.patch.object(
            CLI,
            "run_fenced_command",
            side_effect=AssertionError(
                "unbound pre-sidecar recovery must not rerun the composite child"
            ),
        ), mock.patch.object(
            CLI,
            "_derive_merge_scope",
            side_effect=AssertionError(
                "unbound pre-sidecar recovery must not launch name-status"
            ),
        ):
            recovered = engine.recover()

        current = starter.store.load(self.chain_id)
        self.assertTrue(recovered.ok)
        self.assertEqual(current["state"], "classifying")
        self.assertIsNone(current["candidate"])
        self.assertEqual(current["integration"]["condition"], "fetch-failed")
        self.assertEqual(
            current["integration"]["intent"]["result"], "failed"
        )
        events = [
            json.loads(line)
            for line in starter.store.events_path(self.chain_id)
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        self.assertEqual(
            [event["event"] for event in events].count("fetch_intent"), 1
        )
        fetch_results = [
            event for event in events if event["event"] == "fetch_result"
        ]
        self.assertEqual(len(fetch_results), 1)
        self.assertIsNone(fetch_results[0]["payload"]["scope_fetch_binding"])
        self.assertIsNone(fetch_results[0]["payload"]["scope_proof"])
        self.assertFalse(fence_path.exists(), original_fence_inode)
        self.assertFalse(
            list(
                starter.store.artifact_dir(self.chain_id).glob(
                    "scope-fetch-*.json"
                )
            )
        )
        self.assertFalse(
            (common_dir / CLI.COMMON_LOCK_RECOVERY_NAME).exists()
        )
        self.assertFalse(list(common_dir.glob(".agent-rebase.recover.*.tmp")))
        self.assertEqual(CLI.inspect_common_lock(common_dir).topology, "free")

    def test_second_bare_recover_preserves_unbound_pre_sidecar_fetch_failure(
        self,
    ) -> None:
        starter, _interrupted = self.crash_before_scope_sidecar_publication(
            bound=False
        )
        engine = CLI.MergeEngine(self.context(chain_id=self.chain_id))

        with mock.patch.object(
            CLI,
            "run_fenced_command",
            side_effect=AssertionError(
                "recovery of a pre-sidecar failure must not rerun the composite"
            ),
        ), mock.patch.object(
            CLI,
            "_derive_merge_scope",
            side_effect=AssertionError(
                "unbound pre-sidecar recovery must not derive scope"
            ),
        ):
            first = engine.recover()
            before_state = starter.store.state_path(self.chain_id).read_bytes()
            before_events = starter.store.events_path(self.chain_id).read_bytes()

            with self.assertRaises(CLI.Refusal) as caught:
                engine.recover()

        self.assertTrue(first.ok)
        self.assertEqual(
            caught.exception.reason_code, CLI.V2ReasonCode.FETCH_FAILED
        )
        self.assertEqual(
            caught.exception.message,
            "forge: merge recover refused — fixed target fetch failed",
        )
        self.assertEqual(
            starter.store.state_path(self.chain_id).read_bytes(), before_state
        )
        self.assertEqual(
            starter.store.events_path(self.chain_id).read_bytes(), before_events
        )
        current = starter.store.load(self.chain_id)
        self.assertEqual(current["state"], "classifying")
        self.assertIsNone(current["candidate"])
        self.assertEqual(current["integration"]["condition"], "fetch-failed")
        intent = current["integration"]["intent"]
        self.assertEqual(
            set(intent),
            {
                "operation",
                "operation_nonce",
                "attempt",
                "result",
                "resolved_tip",
            },
        )
        self.assertEqual(intent["operation"], "fetch-result")
        self.assertRegex(intent["operation_nonce"], r"^[0-9a-f]{32}$")
        self.assertEqual(intent["attempt"], 1)
        self.assertEqual(intent["result"], "failed")
        self.assertIsNone(intent["resolved_tip"])

    def test_bound_common_lock_is_always_nested_under_the_journal_lock(self) -> None:
        self.open_run()
        starter = CLI.MergeEngine(self.context(run_id=self.run_id))

        def exercise(engine, invoke):
            journal_depth = 0
            common_entries = []
            original_outer = engine.store._journal_outer
            original_common = CLI.acquire_common_lock

            @contextlib.contextmanager
            def tracked_outer(binding):
                nonlocal journal_depth
                with original_outer(binding):
                    journal_depth += 1
                    try:
                        yield
                    finally:
                        journal_depth -= 1

            @contextlib.contextmanager
            def tracked_common(*args, **kwargs):
                common_entries.append(journal_depth)
                with original_common(*args, **kwargs) as lock:
                    yield lock

            with mock.patch.object(
                engine.store, "_journal_outer", new=tracked_outer
            ), mock.patch.object(
                CLI, "acquire_common_lock", new=tracked_common
            ):
                result = invoke()
            self.assertTrue(common_entries)
            self.assertTrue(all(depth > 0 for depth in common_entries))
            return result

        started = exercise(
            starter,
            lambda: starter.start_chain(
                str(self.worktree), task=self.task_id, remote_tip=self.base
            ),
        )
        engine = CLI.MergeEngine(self.context(chain_id=str(started.chain_id)))
        exercise(engine, lambda: engine.refresh(remote_tip=self.base))
        exercise(engine, lambda: engine.abort("lock order checked"))

    def test_post_fetch_run_scope_refusal_releases_ownership_and_aborts(self) -> None:
        self.open_run()
        outside = self.worktree / "outside" / "task.py"
        outside.parent.mkdir()
        outside.write_text("OUTSIDE = True\n", encoding="utf-8")
        self.git_at(self.worktree, "add", "outside/task.py")
        self.git_at(
            self.worktree,
            "commit",
            "--quiet",
            "-m",
            "add out-of-scope path",
        )

        engine = CLI.MergeEngine(self.context(run_id=self.run_id))
        with self.assertRaises(CLI.Refusal) as caught:
            engine.start_chain(
                str(self.worktree),
                task=self.task_id,
                remote_tip=self.base,
            )

        self.assertEqual(
            caught.exception.reason_code,
            CLI.V2ReasonCode.RUN_SCOPE_EXCEEDED,
        )
        self.assertEqual(
            caught.exception.message,
            "forge: merge start refused — changed paths exceed bound task scope",
        )
        self.assertEqual(caught.exception.chain["state"], "aborted")
        self.assertEqual(
            caught.exception.chain["worktree"]["claim"]["status"], "released"
        )
        self.assertFalse(
            Path(caught.exception.chain["worktree"]["claim"]["path"]).exists()
        )

    def test_scope_excess_release_requires_literal_zero_status_bytes(self) -> None:
        self.open_run()
        outside = self.worktree / "outside" / "status-byte.py"
        outside.parent.mkdir()
        outside.write_text("OUTSIDE = True\n", encoding="utf-8")
        self.git_at(self.worktree, "add", "outside/status-byte.py")
        self.git_at(
            self.worktree, "commit", "--quiet", "-m", "scope status-byte case"
        )
        engine = CLI.MergeEngine(self.context(run_id=self.run_id))
        original_status = CLI._merge_worktree_status

        def inject_one_status_byte(*args, **kwargs):
            result = original_status(*args, **kwargs)
            chain_ids = engine.store.list_ids(family="merge")
            if len(chain_ids) != 1:
                return result
            current = engine.store.load(chain_ids[0])
            return (
                b"\n"
                if current.get("state") == "classifying"
                and current.get("candidate") is not None
                else result
            )

        with mock.patch.object(
            CLI, "_merge_worktree_status", side_effect=inject_one_status_byte
        ), self.assertRaisesRegex(
            CLI.FrozenError, "run-scope abort worktree status is not exact clean"
        ):
            engine.start_chain(
                str(self.worktree), task=self.task_id, remote_tip=self.base
            )
        chain_ids = engine.store.list_ids(family="merge")
        self.assertEqual(len(chain_ids), 1)
        state = engine.store.load(chain_ids[0])
        self.assertEqual(state["state"], "classifying")
        self.assertEqual(state["worktree"]["claim"]["status"], "owned")
        names = [
            json.loads(line)["event"]
            for line in engine.store.events_path(chain_ids[0])
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        self.assertNotIn("ownership_release_intent", names)

    def test_scope_release_clean_status_control_is_load_bearing(self) -> None:
        self.open_run()
        outside = self.worktree / "outside" / "control.py"
        outside.parent.mkdir()
        outside.write_text("OUTSIDE = True\n", encoding="utf-8")
        self.git_at(self.worktree, "add", "outside/control.py")
        self.git_at(self.worktree, "commit", "--quiet", "-m", "scope control case")
        engine = CLI.MergeEngine(self.context(run_id=self.run_id))

        with mock.patch.object(
            CLI,
            "MERGE_INTEGRATION_CONTROLS",
            CLI.MERGE_INTEGRATION_CONTROLS - {"scope-release-clean-status"},
        ), self.assertRaisesRegex(
            CLI.FrozenError,
            "merge integration control is unavailable: scope-release-clean-status",
        ):
            engine.start_chain(
                str(self.worktree), task=self.task_id, remote_tip=self.base
            )
        chain_ids = engine.store.list_ids(family="merge")
        self.assertEqual(len(chain_ids), 1)
        state = engine.store.load(chain_ids[0])
        self.assertEqual(state["state"], "classifying")
        self.assertEqual(state["worktree"]["claim"]["status"], "owned")


class MergeLifecycleRefreshTests(ADAPTERS.MergeAdapterFixture):
    def test_run_bound_refresh_scope_excess_refuses_and_releases_like_start(self) -> None:
        self.open_run()
        starter = CLI.MergeEngine(self.context(run_id=self.run_id))
        started = starter.start_chain(
            str(self.worktree), task=self.task_id, remote_tip=self.base
        )
        outside = self.worktree / "outside" / "refresh.py"
        outside.parent.mkdir()
        outside.write_text("OUTSIDE = True\n", encoding="utf-8")
        self.git_at(self.worktree, "add", "outside/refresh.py")
        self.git_at(
            self.worktree,
            "commit",
            "--quiet",
            "-m",
            "refresh outside task scope",
        )

        engine = CLI.MergeEngine(self.context(chain_id=str(started.chain_id)))
        with self.assertRaises(CLI.Refusal) as caught:
            engine.refresh(remote_tip=self.base)

        self.assertEqual(
            caught.exception.reason_code, CLI.V2ReasonCode.RUN_SCOPE_EXCEEDED
        )
        self.assertEqual(
            caught.exception.message,
            "forge: merge refresh refused — changed paths exceed bound task scope",
        )
        terminal = caught.exception.chain
        self.assertEqual(terminal["state"], "aborted")
        self.assertEqual(terminal["worktree"]["claim"]["status"], "released")
        self.assertFalse(Path(terminal["worktree"]["claim"]["path"]).exists())
        events = [
            json.loads(line)
            for line in engine.store.events_path(str(started.chain_id))
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        self.assertEqual(
            [event["event"] for event in events[-5:]],
            [
                "fetch_intent",
                "fetch_result",
                "ownership_release_intent",
                "ownership_released",
                "aborted",
            ],
        )
        self.assertEqual(events[-4]["payload"]["scope_proof"]["result"], "exceeded")

    def test_refresh_restarts_the_same_generation_and_invalidates_gate_evidence(self) -> None:
        _admission, generation, store, engine, _outcome, _calls = self.verify_chain()

        outcome = engine.refresh(remote_tip=self.base)
        state = store.load(self.chain_id)

        self.assertTrue(outcome.ok)
        self.assertEqual(state["state"], "verifying")
        self.assertEqual(state["candidate"], generation.candidate)
        self.assertEqual(state["steps"], {})
        self.assertEqual(state["review"], {})
        self.assertEqual(state["approval"], {})
        self.assertEqual(state["authorization"], {})
        self.assertEqual(
            json.loads(
                store.events_path(self.chain_id)
                .read_text(encoding="utf-8")
                .splitlines()[-1]
            )["event"],
            "generation_refreshed",
        )

    def test_refresh_after_block_increments_generation_and_retains_iteration(self) -> None:
        _admission, _generation, store, engine, _outcome, _calls = self.verify_chain()
        engine.review_request()
        request = store.load(self.chain_id)["review"]["request"]
        verdict = self.write_verdict(
            "lifecycle-block.txt", "BLOCK", request, ("MAJOR", "repair")
        )
        engine.review_attach(str(verdict))
        (self.worktree / "src" / "app.py").write_text(
            "VALUE = 3\n", encoding="utf-8"
        )
        self.git_at(self.worktree, "add", "src/app.py")
        self.git_at(self.worktree, "commit", "--quiet", "-m", "repair review")

        outcome = engine.refresh(remote_tip=self.base)
        state = store.load(self.chain_id)

        self.assertTrue(outcome.ok)
        self.assertEqual(state["state"], "verifying")
        self.assertEqual(state["candidate"]["generation"], 2)
        self.assertEqual(
            state["candidate"]["candidate_head"],
            self.git_at(self.worktree, "rev-parse", "HEAD"),
        )
        self.assertEqual(state["review"], {"iteration": 1})
        self.assertEqual(state["steps"], {})
        self.assertEqual(state["approval"], {})
        self.assertEqual(state["authorization"], {})

    def test_refresh_iteration_cap_and_pending_cosign_are_exact_refusals(self) -> None:
        _admission, _generation, store, engine, _outcome, _calls = self.verify_chain()
        base = store.load(self.chain_id)
        cases = (
            (
                {"iteration": 8},
                CLI.V2ReasonCode.ITERATION_CAP,
                "forge: merge refresh refused — review iteration cap of 8 is final",
            ),
            (
                {"iteration": 1, "operator_cosign_required": True},
                CLI.V2ReasonCode.STATE_PRECONDITION,
                "forge: merge refresh refused — above-MINOR disposition awaits operator co-sign",
            ),
        )
        for review, reason, message in cases:
            state = copy.deepcopy(base)
            state["review"] = review
            with self.subTest(message=message), mock.patch.object(
                engine, "_load", return_value=state
            ), mock.patch.object(engine, "_halt"), self.assertRaises(
                CLI.Refusal
            ) as caught:
                engine.refresh(remote_tip=self.base)
            self.assertEqual(caught.exception.reason_code, reason)
            self.assertEqual(caught.exception.message, message)

    def test_refresh_refuses_every_deferred_scalar_state(self) -> None:
        _admission, _generation, store, engine, _outcome, _calls = self.verify_chain()
        base = store.load(self.chain_id)
        for scalar in (
            "rebasing",
            "rebase_conflict",
            "reverifying",
            "reverification_failed",
            "pushing",
            "pushed",
            "cleanup_pending",
            "closed",
            "aborted",
        ):
            state = copy.deepcopy(base)
            state["state"] = scalar
            with self.subTest(state=scalar), mock.patch.object(
                engine, "_load", return_value=state
            ), mock.patch.object(
                engine, "_preflight_lifecycle", return_value=state
            ), mock.patch.object(engine, "_halt"), self.assertRaises(
                CLI.Refusal
            ) as caught:
                engine.refresh(remote_tip=self.base)
            self.assertEqual(
                caught.exception.reason_code, CLI.V2ReasonCode.STATE_PRECONDITION
            )
            self.assertEqual(
                caught.exception.message,
                "forge: merge refresh refused — merge transition is not admitted",
            )

    def test_refresh_scalar_row_precedes_iteration_cap(self) -> None:
        _admission, _generation, store, engine, _outcome, _calls = self.verify_chain()
        state = store.load(self.chain_id)
        state["state"] = "closed"
        state["review"] = {"iteration": 8}
        with mock.patch.object(engine, "_load", return_value=state), mock.patch.object(
            engine, "_preflight_lifecycle", return_value=state
        ), mock.patch.object(engine, "_halt"), self.assertRaises(
            CLI.Refusal
        ) as caught:
            engine.refresh(remote_tip=self.base)
        self.assertEqual(
            caught.exception.reason_code,
            CLI.V2ReasonCode.STATE_PRECONDITION,
        )
        self.assertEqual(
            caught.exception.message,
            "forge: merge refresh refused — merge transition is not admitted",
        )

    def test_post_start_missing_worktree_persists_foreign_git_state(self) -> None:
        starter = CLI.MergeEngine(self.context())
        outcome = starter.start_chain(str(self.worktree), remote_tip=self.base)
        engine = CLI.MergeEngine(self.context(chain_id=str(outcome.chain_id)))
        moved = self.temp_root / "candidate-moved"
        self.worktree.rename(moved)
        try:
            with self.assertRaises(CLI.Refusal) as caught:
                engine.refresh(remote_tip=self.base)
            state = engine.store.load(str(outcome.chain_id))
        finally:
            moved.rename(self.worktree)

        self.assertEqual(
            caught.exception.reason_code, CLI.V2ReasonCode.STATE_PRECONDITION
        )
        self.assertEqual(
            caught.exception.message,
            "forge: merge refresh refused — recorded worktree is missing",
        )
        self.assertEqual(state["state"], "verifying")
        self.assertEqual(state["integration"]["condition"], "foreign-git-state")
        self.assertEqual(
            json.loads(
                engine.store.events_path(str(outcome.chain_id))
                .read_text(encoding="utf-8")
                .splitlines()[-1]
            )["event"],
            "condition_recorded",
        )


class MergeLifecycleApprovalTests(ADAPTERS.MergeAdapterFixture):
    def test_nonmovement_counter_reset_control_is_load_bearing(self) -> None:
        integration = {"remote_movement_count": 7}
        CLI._reset_merge_nonmovement_counter(integration)
        self.assertEqual(integration["remote_movement_count"], 0)

        retained = {"remote_movement_count": 7}
        with mock.patch.object(
            CLI,
            "MERGE_INTEGRATION_CONTROLS",
            CLI.MERGE_INTEGRATION_CONTROLS - {"nonmovement-counter-reset"},
        ), self.assertRaisesRegex(
            CLI.FrozenError,
            "merge integration control is unavailable: nonmovement-counter-reset",
        ):
            CLI._reset_merge_nonmovement_counter(retained)
        self.assertEqual(retained["remote_movement_count"], 7)

    def awaiting_control_chain(self):
        control = self.worktree / "scripts" / "control.py"
        control.parent.mkdir(exist_ok=True)
        control.write_text("ENABLED = True\n", encoding="utf-8")
        self.git_at(self.worktree, "add", "scripts/control.py")
        self.git_at(
            self.worktree, "commit", "--quiet", "-m", "control candidate"
        )
        _admission, _generation, store, engine, _outcome, _calls = self.verify_chain()
        engine.review_request()
        request = store.load(self.chain_id)["review"]["request"]
        verdict = self.write_verdict("control-pass.txt", "PASS", request)
        engine.review_attach(str(verdict))
        state = store.load(self.chain_id)
        self.assertEqual(state["state"], "awaiting_approval")
        self.assertTrue(state["tier"]["control"])
        return store, engine, state

    def test_gate_four_approval_binds_exact_candidate_and_generation(self) -> None:
        store, engine, awaiting = self.awaiting_control_chain()

        outcome = engine.approve(awaiting["candidate"]["candidate_head"])
        state = store.load(self.chain_id)

        self.assertTrue(outcome.ok)
        self.assertEqual(state["state"], "authorized")
        self.assertEqual(
            state["approval"],
            {
                "purpose": "gate-4",
                "chain_id": self.chain_id,
                "candidate": awaiting["candidate"]["candidate_head"],
                "generation_digest": awaiting["candidate"]["generation_digest"],
                "recorded_at": state["approval"]["recorded_at"],
                "directed_by": "operator",
            },
        )

    def test_finding_disposition_cosign_is_distinct_and_same_state(self) -> None:
        _admission, _generation, store, engine, _outcome, _calls = self.verify_chain()
        engine.review_request()
        request = store.load(self.chain_id)["review"]["request"]
        verdict = self.write_verdict(
            "finding-block.txt", "BLOCK", request, ("MAJOR", "repair")
        )
        engine.review_attach(str(verdict))
        with self.assertRaises(CLI.Refusal) as parked:
            engine.review_disposition(1, "MAJOR", "accepted risk")
        self.assertEqual(parked.exception.reason_code, CLI.V2ReasonCode.APPROVAL_REQUIRED)
        before = store.load(self.chain_id)

        outcome = engine.approve(before["candidate"]["candidate_head"])
        state = store.load(self.chain_id)

        self.assertTrue(outcome.ok)
        self.assertEqual(state["state"], "revising")
        self.assertFalse(state["review"]["operator_cosign_required"])
        self.assertEqual(state["approval"]["purpose"], "finding-disposition")
        self.assertEqual(state["approval"]["finding"], 1)
        self.assertEqual(state["approval"]["resolution"], "accepted risk")

    def test_remote_churn_acknowledgement_clears_only_that_condition(self) -> None:
        store, engine, awaiting = self.awaiting_control_chain()
        integration = copy.deepcopy(awaiting["integration"])
        integration.update(
            {
                "condition": "remote-churn",
                "primary_condition": "none",
                "remote_movement_count": 8,
            }
        )
        parked = store.transition(
            awaiting,
            "condition_recorded",
            {"delta": {"integration": integration}},
            generation_digest=awaiting["candidate"]["generation_digest"],
            at=CLI.iso_z(),
        )

        engine.approve(parked["candidate"]["candidate_head"])
        state = store.load(self.chain_id)

        self.assertEqual(state["state"], "authorized")
        self.assertEqual(state["approval"]["purpose"], "remote-churn")
        self.assertEqual(state["integration"]["condition"], "none")
        self.assertEqual(state["integration"]["remote_movement_count"], 0)
        self.assertTrue(engine._current_merge_authority(state))

    def test_approval_stale_candidate_and_wrong_state_refusals_are_exact(self) -> None:
        store, engine, awaiting = self.awaiting_control_chain()
        with self.assertRaises(CLI.Refusal) as stale:
            engine.approve("f" * 40)
        self.assertEqual(stale.exception.reason_code, CLI.V2ReasonCode.CANDIDATE_STALE)
        self.assertEqual(
            stale.exception.message,
            "forge: merge approve refused — candidate HEAD does not match the current generation",
        )
        self.assertEqual(store.load(self.chain_id), awaiting)

        for scalar in (
            "classifying",
            "verifying",
            "reviewing",
            "revising",
            "authorized",
            "rebasing",
            "rebase_conflict",
            "reverifying",
            "reverification_failed",
            "pushing",
            "pushed",
            "cleanup_pending",
            "closed",
            "aborted",
        ):
            state = copy.deepcopy(awaiting)
            state["state"] = scalar
            state["review"].pop("operator_cosign_required", None)
            with self.subTest(state=scalar), mock.patch.object(
                engine, "_load", return_value=state
            ), mock.patch.object(
                engine, "_preflight_lifecycle", return_value=state
            ), mock.patch.object(engine, "_halt"), self.assertRaises(
                CLI.Refusal
            ) as caught:
                engine.approve(awaiting["candidate"]["candidate_head"])
            self.assertEqual(
                caught.exception.reason_code, CLI.V2ReasonCode.STATE_PRECONDITION
            )
            self.assertEqual(
                caught.exception.message,
                "forge: merge approve refused — merge transition is not admitted",
            )

    def test_disposition_cosign_at_iteration_cap_is_refused_without_write(self) -> None:
        _admission, _generation, store, engine, _outcome, _calls = self.verify_chain()
        state = store.load(self.chain_id)
        state["state"] = "revising"
        state["review"] = {
            "iteration": 8,
            "operator_cosign_required": True,
        }
        with mock.patch.object(engine, "_load", return_value=state), mock.patch.object(
            engine, "_preflight_lifecycle", return_value=state
        ), mock.patch.object(engine, "_halt"), self.assertRaises(
            CLI.Refusal
        ) as caught:
            engine.approve(state["candidate"]["candidate_head"])
        self.assertEqual(caught.exception.reason_code, CLI.V2ReasonCode.ITERATION_CAP)
        self.assertEqual(
            caught.exception.message,
            "forge: merge approve refused — review iteration cap of 8 is final",
        )


class MergeLifecycleAbortTests(ADAPTERS.MergeAdapterFixture):
    def start_owned_chain(self):
        starter = CLI.MergeEngine(self.context())
        outcome = starter.start_chain(str(self.worktree), remote_tip=self.base)
        engine = CLI.MergeEngine(self.context(chain_id=str(outcome.chain_id)))
        return engine.store, engine, engine.store.load(str(outcome.chain_id))

    def test_abort_before_attempt_releases_claim_then_records_terminal(self) -> None:
        store, engine, started = self.start_owned_chain()
        claim_path = Path(started["worktree"]["claim"]["path"])
        self.assertTrue(claim_path.exists())

        outcome = engine.abort("operator cancelled")
        state = store.load(started["chain_id"])

        self.assertTrue(outcome.ok)
        self.assertEqual(state["state"], "aborted")
        self.assertEqual(state["worktree"]["claim"]["status"], "released")
        self.assertFalse(claim_path.exists())
        events = [
            json.loads(line)["event"]
            for line in store.events_path(started["chain_id"])
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        self.assertEqual(
            events[-3:],
            ["ownership_release_intent", "ownership_released", "aborted"],
        )
        inspected = engine.status()
        self.assertTrue(inspected.ok)
        self.assertEqual(inspected.state, "aborted")
        self.assertEqual(inspected.next_required_step, "none — merge chain aborted")

    def test_abort_priority_rows_precede_inactivity_missing_and_scalar_state(self) -> None:
        _store, engine, base = self.start_owned_chain()
        past = "2000-01-01T00:00:00Z"
        missing = str(self.temp_root / "now-missing")
        priority = (
            (
                "releasing",
                "current",
                "pushed",
                past,
                "forge: merge abort refused — ownership release completion is pending",
            ),
            (
                "owned",
                "current",
                "pushed",
                past,
                "forge: merge abort refused — current intended HEAD is already contained",
            ),
            (
                "owned",
                "older",
                "pushed",
                "2999-01-01T00:00:00Z",
                "forge: merge abort refused — an older attempted HEAD is contained",
            ),
        )
        for claim_status, containment, scalar, inactive_after, message in priority:
            state = copy.deepcopy(base)
            state["worktree"]["claim"]["status"] = claim_status
            state["worktree"]["path"] = missing
            state["inactive_after"] = inactive_after
            state["state"] = scalar
            with self.subTest(message=message), mock.patch.object(
                engine, "_load", return_value=state
            ), mock.patch.object(
                CLI, "_merge_containment", return_value=(containment, ())
            ), self.assertRaises(CLI.Refusal) as caught:
                engine.abort()
            self.assertEqual(
                caught.exception.reason_code, CLI.V2ReasonCode.STATE_PRECONDITION
            )
            self.assertEqual(caught.exception.message, message)

    def test_abort_inactivity_precedes_missing_worktree_and_missing_precedes_scalar(self) -> None:
        _store, engine, base = self.start_owned_chain()
        missing = str(self.temp_root / "now-missing")
        inactive = copy.deepcopy(base)
        inactive["worktree"]["path"] = missing
        inactive["inactive_after"] = "2000-01-01T00:00:00Z"
        inactive["state"] = "pushed"
        with mock.patch.object(engine, "_load", return_value=inactive), mock.patch.object(
            CLI, "_merge_containment", return_value=("none", ())
        ), self.assertRaises(CLI.Refusal) as caught:
            engine.abort()
        self.assertEqual(
            caught.exception.message,
            "forge: merge abort refused — inactive chain cannot prove missing-worktree safety",
        )

        active = copy.deepcopy(inactive)
        active["inactive_after"] = "2999-01-01T00:00:00Z"
        with mock.patch.object(engine, "_load", return_value=active), mock.patch.object(
            CLI, "_merge_containment", return_value=("none", ())
        ), mock.patch.object(
            engine, "_preflight_lifecycle", side_effect=CLI._merge_refusal(
                CLI.V2ReasonCode.STATE_PRECONDITION,
                "forge: merge abort refused — recorded worktree is missing",
            )
        ), self.assertRaises(CLI.Refusal) as caught:
            engine.abort()
        self.assertEqual(
            caught.exception.message,
            "forge: merge abort refused — recorded worktree is missing",
        )

    def test_abort_deferred_and_terminal_scalar_refusals_are_exact(self) -> None:
        _store, engine, base = self.start_owned_chain()
        cases = (
            (
                "pushed",
                "forge: merge abort refused — durable pushed truth requires cleanup",
            ),
            (
                "cleanup_pending",
                "forge: merge abort refused — durable pushed truth requires cleanup",
            ),
            (
                "rebasing",
                "forge: merge abort refused — active rebase restoration is required",
            ),
            (
                "rebase_conflict",
                "forge: merge abort refused — active rebase restoration is required",
            ),
            (
                "closed",
                "forge: merge abort refused — merge transition is not admitted",
            ),
            (
                "aborted",
                "forge: merge abort refused — merge transition is not admitted",
            ),
        )
        for scalar, message in cases:
            state = copy.deepcopy(base)
            state["state"] = scalar
            with self.subTest(state=scalar), mock.patch.object(
                engine, "_load", return_value=state
            ), mock.patch.object(
                CLI, "_merge_containment", return_value=("none", ())
            ), mock.patch.object(
                CLI, "_merge_process_unresolved", return_value=False
            ), self.assertRaises(CLI.Refusal) as caught:
                engine.abort()
            self.assertEqual(
                caught.exception.reason_code, CLI.V2ReasonCode.STATE_PRECONDITION
            )
            self.assertEqual(caught.exception.message, message)

    def test_abort_requires_all_false_containment_and_no_unresolved_process(self) -> None:
        _store, engine, base = self.start_owned_chain()
        attempted = copy.deepcopy(base)
        attempted["integration"]["push"] = {"attempted_heads": [self.candidate_head]}
        with mock.patch.object(engine, "_load", return_value=attempted), mock.patch.object(
            CLI, "_merge_containment", return_value=("unresolved", ())
        ), self.assertRaises(CLI.Refusal) as caught:
            engine.abort()
        self.assertEqual(
            caught.exception.message,
            "forge: merge abort refused — attempted heads lack authoritative all-false containment",
        )

        with mock.patch.object(engine, "_load", return_value=base), mock.patch.object(
            CLI, "_merge_containment", return_value=("none", ())
        ), mock.patch.object(
            CLI, "_merge_process_unresolved", return_value=True
        ), self.assertRaises(CLI.Refusal) as caught:
            engine.abort()
        self.assertEqual(
            caught.exception.message,
            "forge: merge abort refused — a live or unresolved process remains",
        )

    def test_synthetic_all_false_snapshot_cannot_bypass_locked_replay(self) -> None:
        _store, engine, base = self.start_owned_chain()
        attempted = copy.deepcopy(base)
        attempted["integration"]["push"] = {"attempted_heads": [self.candidate_head]}
        with mock.patch.object(engine, "_load", return_value=attempted), mock.patch.object(
            CLI, "_merge_containment", return_value=("all-false", (False,))
        ), mock.patch.object(
            CLI, "_merge_process_unresolved", return_value=False
        ), mock.patch.object(
            engine, "_release_to_aborted_locked"
        ) as release, self.assertRaises(CLI.Refusal) as caught:
            engine.abort("not landed")
        self.assertEqual(
            caught.exception.message,
            "forge: merge abort refused — merge state changed before release",
        )
        release.assert_not_called()

    def test_abort_rechecks_process_after_lock_acquisition(self) -> None:
        _store, engine, base = self.start_owned_chain()
        with mock.patch.object(
            engine, "_load", return_value=base
        ), mock.patch.object(
            CLI, "_merge_containment", return_value=("none", ())
        ), mock.patch.object(
            CLI, "_merge_process_unresolved", side_effect=[False, True]
        ), mock.patch.object(
            engine, "_halt"
        ), mock.patch.object(
            CLI, "acquire_common_lock", return_value=contextlib.nullcontext()
        ), mock.patch.object(
            engine, "_release_to_aborted"
        ) as release, self.assertRaises(CLI.Refusal) as caught:
            engine.abort("not landed")
        self.assertEqual(
            caught.exception.message,
            "forge: merge abort refused — a live or unresolved process remains",
        )
        release.assert_not_called()


class MergeLifecycleVerifyTests(ADAPTERS.MergeAdapterFixture):
    def test_verify_is_resumable_and_reviewing_completion_is_idempotent(self) -> None:
        _admission, _generation, store, engine, _outcome, _calls = self.verify_chain()
        before = store.events_path(self.chain_id).read_bytes()

        outcome = engine.verify()

        self.assertTrue(outcome.ok)
        self.assertEqual(
            outcome.message, "merge mechanical verification already complete; no-op"
        )
        self.assertEqual(store.events_path(self.chain_id).read_bytes(), before)

    def test_gate_run_enforces_the_next_exact_gate(self) -> None:
        admission, generation = self.admission_and_generation()
        _store, _state = self.create_chain(admission, generation)
        engine = CLI.MergeEngine(self.context(chain_id=self.chain_id))

        with self.assertRaises(CLI.Refusal) as caught:
            engine.gate_run("assertion-sensor")

        self.assertEqual(caught.exception.reason_code, CLI.V2ReasonCode.STATE_PRECONDITION)
        self.assertEqual(
            caught.exception.message,
            "forge: merge gate run assertion-sensor refused — merge transition is not admitted",
        )
        self.assertEqual(caught.exception.expected, "next incomplete gate gate-1")

    def test_verify_and_gate_refuse_every_nonmechanical_scalar_state(self) -> None:
        _admission, _generation, store, engine, _outcome, _calls = self.verify_chain()
        base = store.load(self.chain_id)
        for scalar in (
            "classifying",
            "revising",
            "awaiting_approval",
            "authorized",
            "rebasing",
            "rebase_conflict",
            "reverifying",
            "reverification_failed",
            "pushing",
            "pushed",
            "cleanup_pending",
            "closed",
            "aborted",
        ):
            state = copy.deepcopy(base)
            state["state"] = scalar
            for verb, call, message in (
                (
                    "verify",
                    engine.verify,
                    "forge: merge verify refused — merge transition is not admitted",
                ),
                (
                    "gate",
                    lambda: engine.gate_run("gate-1"),
                    "forge: merge gate run gate-1 refused — merge transition is not admitted",
                ),
            ):
                with self.subTest(state=scalar, verb=verb), mock.patch.object(
                    engine, "_load", return_value=state
                ), mock.patch.object(
                    engine, "_preflight_lifecycle", return_value=state
                ), mock.patch.object(engine, "_halt"), self.assertRaises(
                    CLI.Refusal
                ) as caught:
                    call()
                self.assertEqual(
                    caught.exception.reason_code,
                    CLI.V2ReasonCode.STATE_PRECONDITION,
                )
                self.assertEqual(caught.exception.message, message)


class MergeLifecycleReviewEdgeTests(ADAPTERS.MergeAdapterFixture):
    def blocked_chain(self):
        _admission, _generation, store, engine, _outcome, _calls = self.verify_chain()
        engine.review_request()
        request = store.load(self.chain_id)["review"]["request"]
        verdict = self.write_verdict(
            "edge-block.txt", "BLOCK", request, ("MAJOR", "repair")
        )
        engine.review_attach(str(verdict))
        return store, engine, store.load(self.chain_id)

    def test_review_request_and_disposition_cap_refusals_are_structured(self) -> None:
        _admission, _generation, store, engine, _outcome, _calls = self.verify_chain()
        base = store.load(self.chain_id)
        capped = copy.deepcopy(base)
        capped["review"] = {"iteration": 8}
        with mock.patch.object(engine, "_load", return_value=capped), mock.patch.object(
            engine, "_preflight_lifecycle", return_value=capped
        ), mock.patch.object(engine, "_halt"), self.assertRaises(
            CLI.Refusal
        ) as request:
            engine.review_request()
        self.assertEqual(request.exception.reason_code, CLI.V2ReasonCode.ITERATION_CAP)
        self.assertEqual(
            request.exception.message,
            "review iteration cap of 8 reached; no further merge review is admitted",
        )

        capped["state"] = "revising"
        capped["review"] = {
            "iteration": 8,
            "verdict": {"findings": [{"severity": "MAJOR"}]},
        }
        with mock.patch.object(engine, "_load", return_value=capped), mock.patch.object(
            engine, "_preflight_lifecycle", return_value=capped
        ), mock.patch.object(engine, "_halt"), self.assertRaises(
            CLI.Refusal
        ) as disposition:
            engine.review_disposition(1, "MAJOR", "accept")
        self.assertEqual(
            disposition.exception.reason_code, CLI.V2ReasonCode.ITERATION_CAP
        )
        self.assertEqual(
            disposition.exception.message,
            "forge: review disposition refused — review iteration cap of 8 is final",
        )

    def test_concurrent_above_minor_dispositions_admit_exactly_one(self) -> None:
        store, _engine, base = self.blocked_chain()
        before_events = store.events_path(self.chain_id).read_bytes()
        engines = [
            CLI.MergeEngine(self.context(chain_id=self.chain_id)) for _index in range(2)
        ]
        rendezvous = threading.Barrier(2)
        synchronized_thread = threading.local()
        synchronization_lock = threading.Lock()
        arrivals: list[int] = []
        crossings: list[int] = []
        worker_threads: list[int | None] = [None, None]
        original_acquire = CLI.acquire_chain_lease
        results: list[BaseException | None] = [None, None]

        def synchronized_acquire(*args, **kwargs):
            if not getattr(synchronized_thread, "arrived", False):
                synchronized_thread.arrived = True
                identity = threading.get_ident()
                with synchronization_lock:
                    arrivals.append(identity)
                rendezvous.wait(timeout=1)
                with synchronization_lock:
                    crossings.append(identity)
            return original_acquire(*args, **kwargs)

        def submit(index: int) -> None:
            worker_threads[index] = threading.get_ident()
            try:
                engines[index].review_disposition(
                    1, "MAJOR", f"concurrent resolution {index}"
                )
            except BaseException as exc:
                results[index] = exc
            else:
                results[index] = AssertionError(
                    "above-MINOR disposition unexpectedly returned success"
                )

        threads = [
            threading.Thread(target=submit, args=(index,), daemon=True)
            for index in range(2)
        ]
        with mock.patch.object(
            CLI, "acquire_chain_lease", new=synchronized_acquire
        ), mock.patch.object(engines[0], "_halt"), mock.patch.object(
            engines[1], "_halt"
        ):
            for thread in threads:
                thread.start()
            deadline = time.monotonic() + 1
            for thread in threads:
                thread.join(max(0.0, deadline - time.monotonic()))

        self.assertFalse(
            any(thread.is_alive() for thread in threads),
            "concurrent disposition workers did not finish",
        )
        self.assertEqual(len(set(arrivals)), 2)
        self.assertEqual(set(arrivals), set(worker_threads))
        self.assertEqual(set(crossings), set(worker_threads))
        with self.assertRaises(FileNotFoundError):
            (store.root / f"{self.chain_id}.lock").lstat()
        self.assertTrue(all(isinstance(result, CLI.Refusal) for result in results))
        refusals = [result for result in results if isinstance(result, CLI.Refusal)]
        winners = [
            (index, result)
            for index, result in enumerate(results)
            if isinstance(result, CLI.Refusal)
            and result.reason_code == CLI.V2ReasonCode.APPROVAL_REQUIRED
        ]
        losers = [
            result
            for result in refusals
            if result.reason_code == CLI.V2ReasonCode.STATE_PRECONDITION
        ]
        self.assertEqual(len(winners), 1)
        self.assertEqual(len(losers), 1)
        self.assertEqual(
            winners[0][1].message,
            "above-MINOR disposition is parked pending operator co-sign",
        )
        self.assertEqual(
            losers[0].message,
            "forge: review disposition refused — above-MINOR disposition already awaits operator co-sign",
        )

        current = store.load(self.chain_id)
        self.assertEqual(current, winners[0][1].chain)
        self.assertTrue(current["review"]["operator_cosign_required"])
        self.assertEqual(len(current["review"]["dispositions"]), 1)
        self.assertEqual(
            current["review"]["dispositions"][0]["resolution"],
            f"concurrent resolution {winners[0][0]}",
        )
        self.assertEqual(
            current["review"]["dispositions"][0]["candidate"],
            base["candidate"]["candidate_head"],
        )
        after_events = store.events_path(self.chain_id).read_bytes()
        self.assertEqual(after_events[: len(before_events)], before_events)
        appended_events = after_events[len(before_events) :].splitlines()
        self.assertEqual(len(appended_events), 1)
        self.assertEqual(
            json.loads(appended_events[0])["event"], "review_disposition"
        )

    def test_disposition_severity_and_resolution_refusals_are_exact(self) -> None:
        _store, engine, state = self.blocked_chain()
        with self.assertRaises(CLI.Refusal) as severity:
            engine.review_disposition(1, "CRITICAL", "accept")
        self.assertEqual(
            severity.exception.message,
            "forge: review disposition refused — severity does not match the finding",
        )
        with self.assertRaises(CLI.Refusal) as resolution:
            engine.review_disposition(1, "MAJOR", "   ")
        self.assertEqual(
            resolution.exception.message,
            "forge: review disposition refused — resolution must be nonempty",
        )
        self.assertEqual(engine.store.load(self.chain_id), state)

    def test_review_verbs_obey_priority_preflight_before_scalar_rows(self) -> None:
        _admission, _generation, store, engine, _outcome, _calls = self.verify_chain()
        state = store.load(self.chain_id)
        state["state"] = "closed"
        refusal = CLI._merge_refusal(
            CLI.V2ReasonCode.STATE_PRECONDITION,
            "forge: review request refused — merge chain is inactive",
        )
        for name, invoke in (
            ("request", engine.review_request),
            ("collect", engine.review_collect),
            ("attach", lambda: engine.review_attach("verdict.txt")),
            (
                "disposition",
                lambda: engine.review_disposition(1, "MAJOR", "accept"),
            ),
        ):
            with self.subTest(verb=name), mock.patch.object(
                engine, "_load", return_value=state
            ), mock.patch.object(
                engine, "_preflight_lifecycle", side_effect=refusal
            ), self.assertRaises(CLI.Refusal) as caught:
                invoke()
            self.assertEqual(
                caught.exception.message,
                "forge: review request refused — merge chain is inactive",
            )


class MergeLifecycleStatusTests(ADAPTERS.MergeAdapterFixture):
    def test_status_maps_all_fifteen_states_including_terminals(self) -> None:
        admission, generation = self.admission_and_generation()
        store, state = self.create_chain(admission, generation)
        engine = CLI.MergeEngine(self.context(chain_id=self.chain_id))
        expected_prefixes = {
            "classifying": "forge merge refresh",
            "verifying": "forge merge verify",
            "reviewing": "forge review request",
            "revising": "forge merge refresh",
            "awaiting_approval": "forge merge approve",
            "authorized": "forge merge finalize",
            "rebasing": "forge merge recover",
            "rebase_conflict": "forge merge recover",
            "reverifying": "forge merge verify",
            "reverification_failed": "forge merge recover",
            "pushing": "forge merge recover",
            "pushed": "forge merge cleanup",
            "cleanup_pending": "forge merge cleanup",
            "closed": "none — merge chain closed",
            "aborted": "none — merge chain aborted",
        }
        self.assertEqual(len(expected_prefixes), 15)
        for scalar, prefix in expected_prefixes.items():
            projected = copy.deepcopy(state)
            projected["state"] = scalar
            with self.subTest(state=scalar), mock.patch.object(
                engine, "_load", return_value=projected
            ):
                outcome = engine.status()
            self.assertTrue(outcome.ok)
            self.assertEqual(outcome.state, scalar)
            self.assertTrue(outcome.next_required_step.startswith(prefix))

    def test_pending_release_status_routes_to_recovery(self) -> None:
        admission, generation = self.admission_and_generation()
        _store, state = self.create_chain(admission, generation)
        state["worktree"]["claim"]["status"] = "releasing"
        engine = CLI.MergeEngine(self.context(chain_id=self.chain_id))
        with mock.patch.object(engine, "_load", return_value=state):
            outcome = engine.status()
        self.assertEqual(
            outcome.next_required_step,
            f"forge merge recover --chain-id {self.chain_id}",
        )

    def test_explicit_frozen_chain_is_addressable_and_does_not_poison_process_state(self) -> None:
        admission, generation = self.admission_and_generation()
        store, _state = self.create_chain(admission, generation)
        projection = store.state_path(self.chain_id).read_bytes()
        store.state_path(self.chain_id).write_bytes(b"{}\n")

        with self.assertRaises(CLI.FrozenError) as caught:
            CLI.MergeEngine(self.context(chain_id=self.chain_id)).status()
        self.assertEqual(caught.exception.schema, "forge-cli/2")
        store.state_path(self.chain_id).write_bytes(projection)
        healthy = CLI.MergeEngine(self.context(chain_id=self.chain_id)).status()
        self.assertTrue(healthy.ok)
        self.assertEqual(healthy.state, "verifying")

    def test_merge_shared_status_requires_explicit_chain_id(self) -> None:
        with self.assertRaises(CLI.Refusal) as caught:
            CLI.MergeEngine(self.context()).status()
        self.assertEqual(caught.exception.reason_code, CLI.ReasonCode.STATE_PRECONDITION)
        self.assertEqual(caught.exception.schema, "forge-cli/2")
        self.assertEqual(
            caught.exception.message,
            "forge: merge shared verb refused — explicit --chain-id is required",
        )


class MergeLifecycleDormancyTests(ADAPTERS.MergeAdapterFixture):
    def test_lifecycle_adds_only_the_run_scope_reason_enum_member(self) -> None:
        self.assertEqual(len(CLI.V2ReasonCode), 54)
        self.assertIn("run-scope-exceeded", {item.value for item in CLI.V2ReasonCode})

    def test_activation_flag_false_hides_merge_and_true_exposes_exact_slice(self) -> None:
        self.assertIs(CLI.MERGE_LIFECYCLE_ACTIVE, False)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(CLI.Refusal):
            CLI.build_parser().parse_args(
                ["merge", "start", "--worktree", str(self.worktree)]
            )

        cases = (
            (["merge", "start", "--worktree", str(self.worktree)], "start"),
            (["merge", "refresh"], "refresh"),
            (["merge", "verify"], "verify"),
            (["merge", "gate", "run", "gate-1"], "gate"),
            (["merge", "approve", "--candidate", self.candidate_head], "approve"),
            (["merge", "finalize"], "finalize"),
            (["merge", "recover"], "recover"),
            (["merge", "cleanup"], "cleanup"),
            (["merge", "abort", "--reason", "stop"], "abort"),
        )
        with mock.patch.object(RUNTIME, "MERGE_LIFECYCLE_ACTIVE", True):
            for argv, command in cases:
                with self.subTest(argv=argv):
                    parsed = CLI.build_parser().parse_args(argv)
                self.assertEqual(parsed.command, "merge")
                self.assertEqual(parsed.merge_command, command)
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(
                CLI.Refusal
            ):
                CLI.build_parser().parse_args(["merge", "skip", "gate-1"])

    def test_default_dormancy_has_no_user_reachable_chain_mutation(self) -> None:
        before = tuple(CLI.MergeChainStore(self.repo).list_ids(family="merge"))
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = CLI.main(
                [
                    "--repo",
                    str(self.repo),
                    "merge",
                    "start",
                    "--worktree",
                    str(self.worktree),
                ]
            )
        after = tuple(CLI.MergeChainStore(self.repo).list_ids(family="merge"))
        self.assertEqual(result, 1)
        self.assertEqual(after, before)
        self.assertIn("invalid CLI invocation", stdout.getvalue())

    def test_activation_does_not_change_commit_family_grammar(self) -> None:
        argv = ["commit", "start", "--paths", "src/app.py", "--declare-tier", "hard"]
        with mock.patch.object(RUNTIME, "MERGE_LIFECYCLE_ACTIVE", False):
            dormant = vars(CLI.build_parser().parse_args(argv))
        with mock.patch.object(RUNTIME, "MERGE_LIFECYCLE_ACTIVE", True):
            active = vars(CLI.build_parser().parse_args(argv))
        self.assertEqual(active, dormant)

    def test_active_merge_start_run_task_pairing_is_checked_before_discovery(self) -> None:
        with mock.patch.object(RUNTIME, "MERGE_LIFECYCLE_ACTIVE", True):
            options, remaining = CLI._extract_global_options(
                [
                    "--run-id",
                    self.run_id,
                    "merge",
                    "start",
                    "--worktree",
                    str(self.worktree),
                ]
            )
            args = CLI.build_parser().parse_args(remaining)
            with self.assertRaises(CLI.Refusal) as caught:
                CLI._validate_revision9_cross_options(options, args)
        self.assertEqual(
            caught.exception.reason_code,
            CLI.V2ReasonCode.RUN_TASK_BINDING_REQUIRED,
        )
        self.assertEqual(
            caught.exception.message,
            "forge: merge start refused — --run-id and --task must be supplied together",
        )

    def test_active_main_admits_paired_start_but_rejects_later_run_id(self) -> None:
        captured = []

        def dispatch(engine, args):
            captured.append((engine.ctx.options.run_id, args.command, args.merge_command))
            return CLI.Outcome(
                ok=True,
                reason_code=CLI.V2ReasonCode.OK,
                message="captured",
                next_required_step="none",
                schema="forge-cli/2",
            )

        with mock.patch.object(RUNTIME, "MERGE_LIFECYCLE_ACTIVE", True), mock.patch.object(
            CLI, "dispatch", side_effect=dispatch
        ), contextlib.redirect_stdout(io.StringIO()):
            result = CLI.main(
                [
                    "--repo",
                    str(self.repo),
                    "--run-id",
                    self.run_id,
                    "merge",
                    "start",
                    "--worktree",
                    str(self.worktree),
                    "--task",
                    self.task_id,
                ]
            )
        self.assertEqual(result, 0)
        self.assertEqual(captured, [(self.run_id, "merge", "start")])

        output = io.StringIO()
        with mock.patch.object(RUNTIME, "MERGE_LIFECYCLE_ACTIVE", True), mock.patch.object(
            CLI, "dispatch", side_effect=AssertionError("dispatch must not run")
        ), contextlib.redirect_stdout(output):
            result = CLI.main(
                [
                    "--repo",
                    str(self.repo),
                    "--run-id",
                    self.run_id,
                    "merge",
                    "refresh",
                ]
            )
        self.assertEqual(result, 1)
        self.assertIn(
            "forge: CLI run/task binding refused — later chain verbs inherit state and take no --run-id",
            output.getvalue(),
        )

    def test_dispatch_routes_each_compiled_merge_verb_to_its_engine_method(self) -> None:
        calls = []

        class FakeMerge:
            def _outcome(self, name, *values):
                calls.append((name, *values))
                return CLI.Outcome(
                    ok=True,
                    reason_code=CLI.V2ReasonCode.OK,
                    message=name,
                    next_required_step="none",
                    schema="forge-cli/2",
                )

            def start_chain(self, worktree, declared_tier, *, task):
                return self._outcome("start", worktree, declared_tier, task)

            def refresh(self):
                return self._outcome("refresh")

            def verify(self):
                return self._outcome("verify")

            def gate_run(self, gate_id):
                return self._outcome("gate", gate_id)

            def approve(self, candidate):
                return self._outcome("approve", candidate)

            def finalize(self):
                return self._outcome("finalize")

            def recover(self, *, continue_rebase, paths, abort_rebase):
                return self._outcome(
                    "recover", continue_rebase, paths, abort_rebase
                )

            def cleanup_chain(self):
                return self._outcome("cleanup")

            def abort(self, reason):
                return self._outcome("abort", reason)

        repository = CLI.Repository(self.repo)
        root_engine = CLI.Engine(
            CLI.CommandContext(
                repository,
                CLI.ChainStore(repository.common_root()),
                CLI.CLIOptions(revision9_face=True),
            )
        )
        vectors = (
            (
                [
                    "merge",
                    "start",
                    "--worktree",
                    str(self.worktree),
                    "--declare-tier",
                    "hard",
                    "--task",
                    self.task_id,
                ],
                ("start", str(self.worktree), "hard", self.task_id),
            ),
            (["merge", "refresh"], ("refresh",)),
            (["merge", "verify"], ("verify",)),
            (["merge", "gate", "run", "gate-1"], ("gate", "gate-1")),
            (
                ["merge", "approve", "--candidate", self.candidate_head],
                ("approve", self.candidate_head),
            ),
            (["merge", "finalize"], ("finalize",)),
            (["merge", "recover"], ("recover", False, None, False)),
            (
                [
                    "merge",
                    "recover",
                    "--continue",
                    "--paths",
                    "src/app.py",
                    "src/[literal]*.py",
                ],
                (
                    "recover",
                    True,
                    ["src/app.py", "src/[literal]*.py"],
                    False,
                ),
            ),
            (
                ["merge", "recover", "--abort-rebase"],
                ("recover", False, None, True),
            ),
            (["merge", "cleanup"], ("cleanup",)),
            (["merge", "abort", "--reason", "stop"], ("abort", "stop")),
        )
        with mock.patch.object(RUNTIME, "MERGE_LIFECYCLE_ACTIVE", True), mock.patch.object(
            CLI, "_merge_command_engine", return_value=FakeMerge()
        ):
            for argv, expected in vectors:
                parsed = CLI.build_parser().parse_args(argv)
                outcome = CLI.dispatch(root_engine, parsed)
                self.assertTrue(outcome.ok)
                self.assertEqual(calls[-1], expected)

    def test_each_lifecycle_control_is_load_bearing(self) -> None:
        engine = CLI.MergeEngine(self.context(chain_id=self.chain_id))
        calls = {
            "dormant-parser-gate": lambda: CLI.build_parser(),
            "atomic-worktree-ownership": lambda: CLI.MergeEngine(
                self.context()
            ).start_chain(str(self.worktree), remote_tip=self.base),
            "admission-priority": lambda: engine._preflight_lifecycle(
                {"chain_id": self.chain_id}, "merge verify"
            ),
            "candidate-bound-approval": lambda: engine.approve("a" * 40),
        }
        for control, call in calls.items():
            activation = (
                mock.patch.object(RUNTIME, "MERGE_LIFECYCLE_ACTIVE", True)
                if control == "dormant-parser-gate"
                else contextlib.nullcontext()
            )
            with self.subTest(control=control), activation, mock.patch.object(
                CLI,
                "MERGE_LIFECYCLE_CONTROLS",
                CLI.MERGE_LIFECYCLE_CONTROLS - {control},
            ), self.assertRaisesRegex(
                CLI.FrozenError,
                f"merge lifecycle control is unavailable: {control}",
            ):
                call()


if __name__ == "__main__":
    import unittest

    unittest.main()
