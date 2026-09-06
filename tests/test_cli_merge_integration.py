"""Hermetic real-remote coverage for the dormant bounded merge epoch."""

from __future__ import annotations

import base64
import copy
import json
import os
import signal
import subprocess
import threading
import time
import unittest
from collections import OrderedDict
from pathlib import Path
from unittest import mock

from tests import test_cli_merge_adapters as ADAPTERS


CLI = ADAPTERS.CLI
RUNTIME = ADAPTERS.RUNTIME


class _LogicalClock:
    """Advance lock and lease retry deadlines without wall-clock sleeps."""

    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        bounded = max(0.0, seconds)
        self.value += bounded
        time.sleep(min(bounded, 0.001))


class MergeIntegrationEpochTests(ADAPTERS.MergeAdapterFixture):
    _LOCK_TIMEOUT_SECONDS = 1.0
    _PROCESS_TIMEOUT_SECONDS = 5.0
    _REPLAY_CACHE_ENTRIES = 8
    # Hang guard only: bounds a child that never reaches its injected crash.
    # The guarded callbacks run real Git work, so keep generous headroom for
    # saturated CI hosts; the 10 ms poll keeps the success path fast.
    _SIGKILL_DEADLINE_SECONDS = 10.0
    _THREAD_JOIN_SECONDS = 10.0
    _SIGKILL_POLL_SECONDS = 0.01

    def setUp(self) -> None:
        super().setUp()
        clock = _LogicalClock()
        original_common_lock = CLI.acquire_common_lock
        original_chain_lease = CLI.acquire_chain_lease
        original_replay = CLI._replay_merge_event_bytes
        original_transition_valid = CLI._merge_transition_valid
        original_prepare_event = CLI.MergeChainStore._prepare_event
        _batch, builders, _journal = CLI._coordination_modules()
        baseline_controls = (
            frozenset(CLI.MERGE_STORE_CONTROLS),
            frozenset(CLI._REQUIRED_MERGE_STORE_CONTROLS),
            frozenset(CLI.MERGE_INTEGRATION_CONTROLS),
            frozenset(CLI._REQUIRED_MERGE_INTEGRATION_CONTROLS),
        )
        baseline_functions = (
            id(CLI.reduce_merge_event),
            id(CLI._merge_state_shape_valid),
            id(builders._merge_transition_valid),
            id(builders._state_shape_valid),
            id(builders._event_batch_records),
            id(builders._binding_matches_source_fact),
        )
        replay_cache = OrderedDict()
        replay_cache_observations = {"hits": 0}
        captured_context = {}
        preparing_event = 0
        self._original_common_lock = original_common_lock
        self._original_merge_replay = original_replay
        self._replay_cache_observations = replay_cache_observations

        def controls_and_validators_pristine():
            return bool(
                baseline_controls
                == (
                    frozenset(CLI.MERGE_STORE_CONTROLS),
                    frozenset(CLI._REQUIRED_MERGE_STORE_CONTROLS),
                    frozenset(CLI.MERGE_INTEGRATION_CONTROLS),
                    frozenset(CLI._REQUIRED_MERGE_INTEGRATION_CONTROLS),
                )
                and baseline_functions
                == (
                    id(CLI.reduce_merge_event),
                    id(CLI._merge_state_shape_valid),
                    id(builders._merge_transition_valid),
                    id(builders._state_shape_valid),
                    id(builders._event_batch_records),
                    id(builders._binding_matches_source_fact),
                )
                and CLI._merge_transition_valid is capture_transition_context
            )

        def replay_cache_eligible(replay):
            return bool(
                replay.state.get("run_binding") is None
                and replay.state.get("journal_outbox") is None
                and not any(entry[3] for entry in replay.entries)
                and not any(
                    event.get("event") == "journal_receipted"
                    for event in replay.events
                )
            )

        def remember_replay(key, replay):
            replay_cache[key] = replay
            replay_cache.move_to_end(key)
            while len(replay_cache) > self._REPLAY_CACHE_ENTRIES:
                replay_cache.popitem(last=False)

        def capture_transition_context(
            replay_builders,
            event,
            prior,
            current,
            *,
            context,
            history=(),
        ):
            result = original_transition_valid(
                replay_builders,
                event,
                prior,
                current,
                context=context,
                history=history,
            )
            if (
                result
                and preparing_event
                and context is not None
                and controls_and_validators_pristine()
            ):
                captured_context[event.get("digest")] = copy.deepcopy(
                    dict(context)
                )
            return result

        def cached_unbound_replay(
            chain_id, raw_events, *, verify_receipts=True
        ):
            if not controls_and_validators_pristine():
                return original_replay(
                    chain_id,
                    raw_events,
                    verify_receipts=verify_receipts,
                )
            key = (chain_id, raw_events)
            cached = replay_cache.get(key)
            if cached is not None:
                replay_cache_observations["hits"] += 1
                replay_cache.move_to_end(key)
                return cached
            replay = original_replay(
                chain_id,
                raw_events,
                verify_receipts=verify_receipts,
            )
            if replay_cache_eligible(replay):
                remember_replay(key, replay)
            return replay

        def cache_prepared_unbound_event(store, replay, **kwargs):
            nonlocal preparing_event
            captured_context.clear()
            preparing_event += 1
            try:
                result = original_prepare_event(store, replay, **kwargs)
            finally:
                preparing_event -= 1
            event, current, records, pending_outbox = result
            context = captured_context.pop(event.get("digest"), None)
            if not (
                controls_and_validators_pristine()
                and context is not None
                and not records
                and pending_outbox is None
                and current.get("run_binding") is None
                and current.get("journal_outbox") is None
                and (replay is None or replay_cache_eligible(replay))
            ):
                return result
            event_copy = copy.deepcopy(event)
            current_copy = CLI.validate_merge_state(
                copy.deepcopy(current), str(event["chain_id"])
            )
            raw_events = (
                replay.raw_events if replay is not None else b""
            ) + CLI.canonical_bytes(event) + b"\n"
            prepared = CLI.MergeReplayResult(
                state=current_copy,
                events=(replay.events if replay is not None else ())
                + (event_copy,),
                entries=(replay.entries if replay is not None else ())
                + (
                    (
                        event_copy,
                        (
                            copy.deepcopy(replay.state)
                            if replay is not None
                            else None
                        ),
                        copy.deepcopy(current),
                        (),
                        None,
                    ),
                ),
                prefix_state_bytes=(
                    replay.prefix_state_bytes if replay is not None else ()
                )
                + (CLI.canonical_bytes(current) + b"\n",),
                context=copy.deepcopy(context),
                raw_events=raw_events,
                tail_sequence=int(event["sequence"]),
                tail_digest=str(event["digest"]),
            )
            remember_replay((str(event["chain_id"]), raw_events), prepared)
            return result

        def bounded_common_lock(*args, **kwargs):
            kwargs["timeout"] = min(
                float(kwargs.get("timeout", CLI.COMMON_LOCK_TIMEOUT_SECONDS)),
                self._LOCK_TIMEOUT_SECONDS,
            )
            kwargs.setdefault("clock", clock)
            kwargs.setdefault("sleeper", clock.sleep)
            return original_common_lock(*args, **kwargs)

        def bounded_chain_lease(*args, **kwargs):
            kwargs["timeout"] = min(
                float(kwargs.get("timeout", CLI.COMMON_LOCK_TIMEOUT_SECONDS)),
                self._LOCK_TIMEOUT_SECONDS,
            )
            kwargs.setdefault("clock", clock)
            kwargs.setdefault("sleeper", clock.sleep)
            return original_chain_lease(*args, **kwargs)

        patches = (
            mock.patch.object(
                RUNTIME, "COMMAND_TIMEOUT_SECONDS", self._PROCESS_TIMEOUT_SECONDS
            ),
            mock.patch.object(
                CLI,
                "_merge_transition_valid",
                new=capture_transition_context,
            ),
            mock.patch.object(
                CLI,
                "_replay_merge_event_bytes",
                new=cached_unbound_replay,
            ),
            mock.patch.object(
                CLI.MergeChainStore,
                "_prepare_event",
                new=cache_prepared_unbound_event,
            ),
            mock.patch.object(
                CLI, "acquire_common_lock", new=bounded_common_lock
            ),
            mock.patch.object(
                CLI, "acquire_chain_lease", new=bounded_chain_lease
            ),
        )
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def assert_sigkill_crash(self, callback) -> None:
        child = os.fork()
        if child == 0:
            try:
                callback()
            except BaseException:
                os._exit(125)
            os._exit(0)
        deadline = time.monotonic() + self._SIGKILL_DEADLINE_SECONDS
        while True:
            waited, status = os.waitpid(child, os.WNOHANG)
            if waited == child:
                break
            if time.monotonic() >= deadline:
                try:
                    os.kill(child, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                os.waitpid(child, 0)
                self.fail(
                    "SIGKILL crash callback did not reach its injected crash "
                    f"within {self._SIGKILL_DEADLINE_SECONDS:.1f}s"
                )
            time.sleep(self._SIGKILL_POLL_SECONDS)
        self.assertTrue(os.WIFSIGNALED(status), status)
        self.assertEqual(os.WTERMSIG(status), signal.SIGKILL)

    def authorize(
        self, *, remote_tip: str | None = None
    ) -> tuple[object, object, dict[str, object]]:
        starter = CLI.MergeEngine(self.context())
        started = starter.start_chain(
            str(self.worktree), remote_tip=remote_tip or self.base
        )
        engine = CLI.MergeEngine(self.context(chain_id=str(started.chain_id)))
        with mock.patch.object(
            RUNTIME, "run_bounded", side_effect=self.passing_process
        ):
            verified = engine.verify()
        self.assertTrue(verified.ok)
        engine.review_request()
        state = engine.store.load(str(started.chain_id))
        verdict = self.write_verdict(
            f"{started.chain_id}-pass.txt",
            "PASS",
            state["review"]["request"],
        )
        attached = engine.review_attach(str(verdict))
        self.assertEqual(attached.state, "authorized")
        return engine, engine.store, engine.store.load(str(started.chain_id))

    @staticmethod
    def events(store: object, chain_id: str) -> list[dict[str, object]]:
        return [
            json.loads(line)
            for line in store.events_path(chain_id)
            .read_text(encoding="utf-8")
            .splitlines()
        ]

    def clone_remote_writer(self, name: str) -> Path:
        checkout = self.temp_root / name
        result = subprocess.run(
            ["git", "clone", "--quiet", str(self.origin), str(checkout)],
            env=self.environment(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for argv in (
            ["checkout", "--quiet", "fixture-main"],
            ["config", "user.name", "Remote Fixture"],
            ["config", "user.email", "remote@example.test"],
        ):
            completed = subprocess.run(
                ["git", "-C", str(checkout), *argv],
                env=self.environment(),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(
                completed.returncode, 0, completed.stdout + completed.stderr
            )
        return checkout

    def push_remote_change(
        self, checkout: Path, relative: str, contents: str
    ) -> str:
        path = checkout / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
        for argv in (
            ["add", relative],
            ["commit", "--quiet", "-m", f"remote change to {relative}"],
            ["push", "--quiet", "origin", "fixture-main"],
        ):
            completed = subprocess.run(
                ["git", "-C", str(checkout), *argv],
                env=self.environment(),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(
                completed.returncode, 0, completed.stdout + completed.stderr
            )
        return subprocess.check_output(
            ["git", "-C", str(checkout), "rev-parse", "HEAD"],
            env=self.environment(),
            text=True,
        ).strip()

    def prepare_carried_ancestor(
        self,
    ) -> tuple[object, object, dict[str, object], dict[str, object], str]:
        """Park a remote-only successor already contained by the candidate."""

        self.git_at(
            self.worktree,
            "push",
            "--quiet",
            "origin",
            f"{self.candidate_head}:refs/heads/fixture-main",
        )
        initial_remote = self.candidate_head
        self.git_at(
            self.worktree,
            "commit",
            "--quiet",
            "--allow-empty",
            "-m",
            "empty remote-only ancestor",
        )
        remote_only_tip = self.git_at(self.worktree, "rev-parse", "HEAD")
        added = self.worktree / "src" / "after-empty.py"
        added.write_text("AFTER = True\n", encoding="utf-8")
        self.git_at(self.worktree, "add", "src/after-empty.py")
        self.git_at(
            self.worktree,
            "commit",
            "--quiet",
            "-m",
            "candidate after empty ancestor",
        )
        engine, store, authorized = self.authorize(remote_tip=initial_remote)
        original = CLI.run_fenced_command
        moved = False

        def move_during_observation(lock, **kwargs):
            nonlocal moved
            if kwargs.get("operation") == "remote-observation" and not moved:
                self.git_at(
                    self.worktree,
                    "push",
                    "--quiet",
                    "origin",
                    f"{remote_only_tip}:refs/heads/fixture-main",
                )
                moved = True
            return original(lock, **kwargs)

        with mock.patch.object(
            CLI, "run_fenced_command", side_effect=move_during_observation
        ):
            parked = engine.finalize()
        self.assertTrue(parked.ok)
        carried = store.load(str(authorized["chain_id"]))
        self.assertEqual(carried["candidate"]["generation"], 2)
        self.assertEqual(carried["candidate"]["remote_tip"], remote_only_tip)
        return engine, store, authorized, carried, remote_only_tip

    def stage_carried_successor_candidate_observation(
        self, engine: object, store: object, chain_id: str
    ) -> None:
        """Complete the authenticated observation before a 1s crash window."""

        class AncestryEntryBoundary(RuntimeError):
            pass

        with mock.patch.object(
            engine,
            "_run_carried_successor_ancestry",
            side_effect=AncestryEntryBoundary(
                "park after the durable candidate observation"
            ),
        ), self.assertRaisesRegex(
            AncestryEntryBoundary, "durable candidate observation"
        ):
            engine.recover()

        prepared = store.load(chain_id)
        self.assertEqual(
            prepared["integration"]["intent"]["schema"],
            CLI._EPOCH_FETCH_OBSERVATION_SCHEMA,
        )
        replay = CLI._replay_merge_event_bytes(
            chain_id, store.events_path(chain_id).read_bytes()
        )
        candidate_context = replay.context.get("candidate_observation")
        raw_context = replay.context.get("epoch_fetch_observation")
        self.assertIsInstance(candidate_context, dict)
        self.assertIsInstance(raw_context, dict)
        evidence = candidate_context["evidence"]
        self.assertTrue(
            CLI._merge_candidate_observation_evidence_valid(prepared, evidence)
        )
        self.assertEqual(
            candidate_context["source_intent"], raw_context["evidence"]
        )
        self.assertEqual(
            candidate_context["evidence_digest"], evidence["evidence_digest"]
        )
        self.assertEqual(
            candidate_context["restore_event_digest"], replay.tail_digest
        )

    def prepare_older_only_attempts(
        self, *, defer_post_observation: bool
    ) -> tuple[object, object, dict[str, object], str, str, str]:
        """Run two real rejected pushes and publish only the older head."""

        engine, store, first_authorized = self.authorize()
        chain_id = str(first_authorized["chain_id"])
        older_head = str(first_authorized["candidate"]["candidate_head"])
        self.git_at(
            self.worktree,
            "push",
            "--quiet",
            "origin",
            f"{older_head}:refs/heads/older-attempt",
        )
        writer = self.clone_remote_writer("older-only-writer")
        original = CLI.run_fenced_command
        first_push = True

        def advance_before_first_push(lock, **kwargs):
            nonlocal first_push
            if kwargs.get("operation") == "push" and first_push:
                first_push = False
                self.push_remote_change(
                    writer, "remote-only.txt", "divergent remote base\n"
                )
            return original(lock, **kwargs)

        with mock.patch.object(
            CLI, "run_fenced_command", side_effect=advance_before_first_push
        ):
            moved = engine.finalize()
        moved_state = store.load(chain_id)
        self.assertTrue(moved.ok)
        self.assertEqual(moved_state["state"], "authorized")
        self.assertEqual(moved_state["integration"]["condition"], "non-fast-forward")
        self.assertEqual(
            moved_state["integration"]["push"]["attempted_heads"], [older_head]
        )

        def complete_gate_without_process(lock, **kwargs):
            if kwargs.get("operation") != "gate":
                return original(lock, **kwargs)
            output = b"fixture epoch gate pass\n"
            result = CLI.FencedProcessResult(
                argv=list(kwargs["argv"]),
                returncode=0,
                duration_seconds=0.01,
                output=output,
                output_digest=CLI.sha256_bytes(output),
                timed_out=False,
                output_limit=False,
                launch_failed=False,
                group_survived=False,
                authorized=True,
                fence_digest=CLI.sha256_bytes(CLI.canonical_bytes(kwargs["argv"])),
                fence_inode=1,
            )
            kwargs["persist_result"](result)
            return result

        original_candidate_observation = engine._run_candidate_observation_locked
        candidate_observations: dict[tuple[object, ...], dict[str, object]] = {}

        def reuse_unchanged_candidate_observation(
            state, lock, lease, *, verb, remote_tip, expected_head, classify
        ):
            key = (verb, remote_tip, expected_head, classify)
            retained = candidate_observations.get(key)
            if (
                retained is not None
                and retained.get("source_intent")
                == state.get("integration", {}).get("intent")
                and CLI._merge_candidate_observation_evidence_valid(state, retained)
            ):
                return state, copy.deepcopy(retained)
            current, evidence = original_candidate_observation(
                state,
                lock,
                lease,
                verb=verb,
                remote_tip=remote_tip,
                expected_head=expected_head,
                classify=classify,
            )
            candidate_observations[key] = copy.deepcopy(evidence)
            return current, evidence

        with mock.patch.object(
            CLI, "run_fenced_command", side_effect=complete_gate_without_process
        ), mock.patch.object(
            engine,
            "_run_candidate_observation_locked",
            side_effect=reuse_unchanged_candidate_observation,
        ):
            integrated = engine.finalize()
        reviewing = store.load(chain_id)
        self.assertTrue(integrated.ok)
        self.assertEqual(reviewing["state"], "reviewing")
        engine.review_request()
        requested = store.load(chain_id)
        verdict = self.write_verdict(
            f"{chain_id}-generation-two-pass.txt",
            "PASS",
            requested["review"]["request"],
        )
        engine.review_attach(str(verdict))
        second_authorized = store.load(chain_id)
        newer_head = str(second_authorized["candidate"]["candidate_head"])
        self.assertNotEqual(newer_head, older_head)
        self.assertEqual(second_authorized["state"], "authorized")

        self.git_at(writer, "fetch", "--quiet", "origin", "older-attempt")
        self.git_at(
            writer,
            "merge",
            "--quiet",
            "--no-ff",
            "--no-edit",
            "FETCH_HEAD",
        )
        containing_tip = self.git_at(writer, "rev-parse", "HEAD")
        second_push = True

        def advance_before_second_push(lock, **kwargs):
            nonlocal second_push
            if kwargs.get("operation") == "push" and second_push:
                second_push = False
                self.git_at(
                    writer,
                    "push",
                    "--quiet",
                    "origin",
                    f"{containing_tip}:refs/heads/fixture-main",
                )
            return original(lock, **kwargs)

        class DeferredPostObservation(RuntimeError):
            pass

        original_observation = engine._run_remote_observation

        def optionally_defer_observation(*args, **kwargs):
            if defer_post_observation and kwargs.get("phase") == "post-push":
                raise DeferredPostObservation("defer post-push observation")
            return original_observation(*args, **kwargs)

        patches = (
            mock.patch.object(
                CLI, "run_fenced_command", side_effect=advance_before_second_push
            ),
            mock.patch.object(
                engine,
                "_run_remote_observation",
                side_effect=optionally_defer_observation,
            ),
            mock.patch.object(
                engine,
                "_run_candidate_observation_locked",
                side_effect=reuse_unchanged_candidate_observation,
            ),
        )
        with patches[0], patches[1], patches[2]:
            if defer_post_observation:
                with self.assertRaisesRegex(
                    DeferredPostObservation, "defer post-push observation"
                ):
                    engine.finalize()
            else:
                completed = engine.finalize()
                self.assertTrue(completed.ok)

        current = store.load(chain_id)
        self.assertEqual(
            current["integration"]["push"]["attempted_heads"],
            [older_head, newer_head],
        )
        self.assertEqual(
            current["integration"]["push"]["result"]["classification"],
            "non-fast-forward",
        )
        self.assertEqual(
            self.git_at(self.origin, "rev-parse", "refs/heads/fixture-main"),
            containing_tip,
        )
        return (
            engine,
            store,
            first_authorized,
            older_head,
            newer_head,
            containing_tip,
        )

    @staticmethod
    def replay_prefix(events: list[dict[str, object]], stop: int) -> bytes:
        return b"".join(
            CLI.canonical_bytes(event) + b"\n" for event in events[: stop + 1]
        )

    @staticmethod
    def reseal_event(event: dict[str, object]) -> None:
        event.pop("digest", None)
        event["digest"] = CLI.sha256_bytes(CLI.canonical_bytes(event))

    @classmethod
    def reseal_suffix(
        cls, events: list[dict[str, object]], start: int
    ) -> bytes:
        previous = events[start - 1]["digest"] if start else None
        for event in events[start:]:
            event["previous_digest"] = previous
            cls.reseal_event(event)
            previous = event["digest"]
        return b"".join(CLI.canonical_bytes(event) + b"\n" for event in events)

    def assert_loud_explicit_recovery_refusal(
        self,
        engine: object,
        store: object,
        chain_id: str,
        scalar_state: str,
        *,
        bare_route: str,
        loaded_state: dict[str, object] | None = None,
        ownership_predicate: str = "not-applicable",
    ) -> None:
        persisted = store.load(chain_id) if loaded_state is None else None
        selected = copy.deepcopy(
            persisted if loaded_state is None else loaded_state
        )
        self.assertEqual(selected["state"], scalar_state)
        if loaded_state is None:
            assert persisted is not None
            self.assertEqual(persisted["state"], scalar_state)
        before_state = store.state_path(chain_id).read_bytes()
        before_events = store.events_path(chain_id).read_bytes()
        expected_diagnostic = (
            "forge: merge recover refused — explicit conflict recovery requires "
            f"the exact owned rebase_conflict state (actual state: {scalar_state})"
        )
        modes = (
            (
                "--continue",
                {"continue_rebase": True, "paths": ["src/app.py"]},
            ),
            ("--abort-rebase", {"abort_rebase": True}),
        )
        for flag, arguments in modes:
            with self.subTest(
                flag=flag,
                scalar_state=scalar_state,
                ownership_predicate=ownership_predicate,
            ), mock.patch.object(
                engine,
                "_read_only_recovery_flag_state",
                side_effect=lambda: copy.deepcopy(selected),
            ), mock.patch.object(
                engine,
                "_load",
                side_effect=lambda: copy.deepcopy(selected),
            ), mock.patch.object(
                engine,
                "_halt",
                side_effect=AssertionError(
                    f"explicit {flag} reached bare recovery routing"
                ),
            ) as recovery_routing, mock.patch.object(
                engine,
                bare_route,
                side_effect=AssertionError(
                    f"explicit {flag} reached bare recovery route {bare_route}"
                ),
            ) as routed, self.assertRaises(CLI.Refusal) as caught:
                engine.recover(**arguments)
            self.assertEqual(
                caught.exception.reason_code,
                CLI.V2ReasonCode.STATE_PRECONDITION,
            )
            self.assertEqual(caught.exception.observed, scalar_state)
            self.assertEqual(caught.exception.message, expected_diagnostic)
            diagnostic = caught.exception.outcome()
            self.assertEqual(diagnostic.exit_code, 1)
            self.assertEqual(diagnostic.state, scalar_state)
            self.assertEqual(diagnostic.observed, scalar_state)
            self.assertEqual(diagnostic.message, expected_diagnostic)
            recovery_routing.assert_not_called()
            routed.assert_not_called()
            self.assertEqual(
                store.state_path(chain_id).read_bytes(), before_state
            )
            self.assertEqual(
                store.events_path(chain_id).read_bytes(), before_events
            )

    def assert_conflict_observation_failure(self, failure: str) -> None:
        engine, store, authorized = self.authorize()
        writer = self.clone_remote_writer(f"observation-{failure}-writer")
        remote_tip = self.push_remote_change(
            writer, "src/app.py", "VALUE = 9000\n"
        )
        original = CLI.run_fenced_command
        injected = False

        def fail_first_conflict_read(lock, **kwargs):
            nonlocal injected
            argv = list(kwargs.get("argv", ()))
            if (
                not injected
                and kwargs.get("operation") == "continue"
                and argv
                == [
                    "git",
                    "diff",
                    "--name-only",
                    "--diff-filter=U",
                    "-z",
                    "--",
                ]
            ):
                injected = True
                output = f"simulated {failure}\n".encode("ascii")
                result = CLI.FencedProcessResult(
                    argv=argv,
                    returncode=None if failure in {"timeout", "launch"} else 1,
                    duration_seconds=1200.0 if failure == "timeout" else 0.01,
                    output=output,
                    output_digest=CLI.sha256_bytes(output),
                    timed_out=failure == "timeout",
                    output_limit=failure == "cap",
                    launch_failed=failure == "launch",
                    group_survived=failure == "survivor",
                    authorized=True,
                    fence_digest="d" * 64,
                    fence_inode=1,
                )
                kwargs["persist_result"](result)
                return result
            return original(lock, **kwargs)

        with mock.patch.object(
            CLI, "run_fenced_command", side_effect=fail_first_conflict_read
        ), self.assertRaises(CLI.Refusal) as caught:
            engine.finalize()
        current = store.load(str(authorized["chain_id"]))
        self.assertTrue(injected)
        self.assertEqual(caught.exception.reason_code, CLI.V2ReasonCode.REBASE_FAILED)
        self.assertNotEqual(current["state"], "rebase_conflict")
        self.assertEqual(current["integration"]["condition"], "foreign-git-state")
        self.assertIsNone(current["integration"]["conflict"])
        self.assertEqual(
            self.git_at(self.origin, "rev-parse", "refs/heads/fixture-main"),
            remote_tip,
        )

    def test_conflict_observation_timeout_is_fail_closed(self) -> None:
        self.assert_conflict_observation_failure("timeout")

    def test_conflict_observation_cap_breach_is_fail_closed(self) -> None:
        self.assert_conflict_observation_failure("cap")

    def test_conflict_observation_launch_failure_is_fail_closed(self) -> None:
        self.assert_conflict_observation_failure("launch")

    def test_conflict_observation_survivor_is_fail_closed(self) -> None:
        self.assert_conflict_observation_failure("survivor")

    def test_full_epoch_push_and_nonforce_cleanup(self) -> None:
        engine, store, authorized = self.authorize()

        finalized = engine.finalize()
        pushed = store.load(str(authorized["chain_id"]))
        self.assertTrue(finalized.ok)
        self.assertEqual(pushed["state"], "pushed")
        self.assertEqual(
            self.git_at(self.origin, "rev-parse", "refs/heads/fixture-main"),
            pushed["candidate"]["candidate_head"],
        )
        names = [
            event["event"]
            for event in self.events(store, str(authorized["chain_id"]))
        ]
        self.assertEqual(names.count("epoch_intent"), 1)
        self.assertEqual(names.count("fetch_intent"), 2)
        self.assertEqual(names.count("push_intent"), 1)
        self.assertEqual(names.count("push_observed"), 2)

        cleaned = engine.cleanup_chain()
        closed = store.load(str(authorized["chain_id"]))
        self.assertTrue(cleaned.ok)
        self.assertEqual(closed["state"], "closed")
        self.assertFalse(self.worktree.exists())
        self.assertFalse(Path(closed["worktree"]["claim"]["path"]).exists())
        self.assertNotEqual(
            CLI.Repository(self.repo)
            .git(["show-ref", "--verify", "refs/heads/feature"], check=False)
            .returncode,
            0,
        )

    def test_initial_destination_absence_is_fetch_failed_without_creation(
        self,
    ) -> None:
        destination = "refs/heads/fixture-main"
        self.git_at(self.origin, "update-ref", "-d", destination)
        original = CLI.run_fenced_command
        operations: list[str] = []

        def record_bootstrap_fetch(lock, **kwargs):
            operations.append(str(kwargs.get("operation")))
            return original(lock, **kwargs)

        remote_before = subprocess.run(
            ["git", "show-ref", "--verify", destination],
            cwd=self.origin,
            env=self.environment(),
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(remote_before.returncode, 0)

        starter = CLI.MergeEngine(self.context())
        with mock.patch.object(
            CLI, "run_fenced_command", side_effect=record_bootstrap_fetch
        ), self.assertRaises(CLI.Refusal) as caught:
            starter.start_chain(str(self.worktree))

        self.assertEqual(caught.exception.reason_code, CLI.V2ReasonCode.FETCH_FAILED)
        failed = caught.exception.chain
        chain_id = str(failed["chain_id"])
        events = self.events(starter.store, chain_id)
        self.assertEqual(operations, ["fetch"])
        self.assertEqual(failed["state"], "classifying")
        self.assertEqual(failed["integration"]["condition"], "fetch-failed")
        self.assertEqual(failed["integration"]["primary_condition"], "none")
        self.assertEqual(
            failed["integration"]["intent"],
            {
                "operation": "fetch-result",
                "operation_nonce": events[3]["payload"]["operation_nonce"],
                "attempt": 1,
                "result": "failed",
                "resolved_tip": None,
            },
        )
        self.assertIsNone(failed["integration"]["observed"])
        self.assertIsNone(failed["integration"]["push"])
        self.assertIsNone(failed["candidate"])
        self.assertIsNone(failed["tier"])
        self.assertIsNone(failed["run"])
        self.assertIsNone(failed["run_binding"])
        self.assertEqual(
            [event["event"] for event in events],
            [
                "chain_started",
                "ownership_intent",
                "ownership_claimed",
                "fetch_intent",
                "fetch_result",
            ],
        )
        self.assertEqual([event["sequence"] for event in events], [1, 2, 3, 4, 5])
        self.assertTrue(all(event["generation_digest"] is None for event in events))
        self.assertIsNone(events[3]["payload"]["scope_request"])
        self.assertIsNone(events[4]["payload"]["scope_fetch_binding"])
        self.assertIsNone(events[4]["payload"]["scope_proof"])
        remote_after = subprocess.run(
            ["git", "show-ref", "--verify", destination],
            cwd=self.origin,
            env=self.environment(),
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(remote_after.returncode, 0)

    def test_final_prepush_absence_parks_remote_moved_without_push(self) -> None:
        engine, store, authorized = self.authorize()
        destination = str(authorized["target"]["destination_ref"])
        original = CLI.run_fenced_command
        operations: list[str] = []
        deleted = False

        def delete_before_final_observation(lock, **kwargs):
            nonlocal deleted
            operation = str(kwargs.get("operation"))
            operations.append(operation)
            if operation == "remote-observation" and not deleted:
                self.assertIn("fetch", operations[:-1])
                self.assertNotIn("push", operations[:-1])
                self.git_at(self.origin, "update-ref", "-d", destination)
                deleted = True
            return original(lock, **kwargs)

        with mock.patch.object(
            CLI,
            "run_fenced_command",
            side_effect=delete_before_final_observation,
        ):
            parked = engine.finalize()

        chain_id = str(authorized["chain_id"])
        current = store.load(chain_id)
        events = self.events(store, chain_id)
        self.assertTrue(parked.ok)
        self.assertTrue(deleted)
        self.assertEqual(
            [
                operation
                for operation in operations
                if operation in {"fetch", "remote-observation", "push"}
            ],
            ["fetch", "remote-observation"],
        )
        self.assertEqual(current["state"], "authorized")
        self.assertEqual(current["integration"]["condition"], "remote-moved")
        self.assertEqual(current["integration"]["remote_movement_count"], 1)
        observed = current["integration"]["observed"]
        self.assertIsNotNone(observed)
        self.assertFalse(observed["exists"])
        self.assertIsNone(observed["oid"])
        self.assertFalse(observed["contains_intended_head"])
        self.assertEqual(observed["attempted_head_containment"], [])
        self.assertIsNone(current["integration"]["push"])
        self.assertEqual(current["candidate"], authorized["candidate"])
        self.assertEqual(events[-1]["event"], "push_observed")
        self.assertEqual(
            events[-1]["payload"]["delta"]["integration"]["observed"],
            observed,
        )
        self.assertNotIn("push_intent", [event["event"] for event in events])
        absent = subprocess.run(
            ["git", "show-ref", "--verify", destination],
            cwd=self.origin,
            env=self.environment(),
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(absent.returncode, 0)

    def test_deletion_after_final_read_is_recreated_by_ordinary_push(self) -> None:
        engine, store, authorized = self.authorize()
        destination = str(authorized["target"]["destination_ref"])
        original = CLI.run_fenced_command
        operations: list[tuple[str, list[str]]] = []
        final_read_complete = False
        deleted_before_push = False

        def delete_after_final_read(lock, **kwargs):
            nonlocal final_read_complete, deleted_before_push
            operation = str(kwargs.get("operation"))
            if operation == "push":
                self.assertTrue(final_read_complete)
                self.assertFalse(deleted_before_push)
                self.git_at(self.origin, "update-ref", "-d", destination)
                absent = subprocess.run(
                    ["git", "show-ref", "--verify", destination],
                    cwd=self.origin,
                    env=self.environment(),
                    capture_output=True,
                    check=False,
                )
                self.assertNotEqual(absent.returncode, 0)
                deleted_before_push = True
            result = original(lock, **kwargs)
            operations.append((operation, list(kwargs.get("argv", ()))))
            if operation == "remote-observation" and not final_read_complete:
                final_read_complete = True
            return result

        chain_id = str(authorized["chain_id"])
        events_before = self.events(store, chain_id)
        with mock.patch.object(
            CLI, "run_fenced_command", side_effect=delete_after_final_read
        ):
            finalized = engine.finalize()

        pushed = store.load(chain_id)
        new_events = self.events(store, chain_id)[len(events_before) :]
        lifecycle_events = [
            event
            for event in new_events
            if event["event"]
            in {"fetch_intent", "fetch_result", "push_intent", "push_observed"}
        ]
        intended_head = str(pushed["candidate"]["candidate_head"])
        filtered_operations = [
            item
            for item in operations
            if item[0] in {"fetch", "remote-observation", "push"}
        ]
        self.assertTrue(finalized.ok)
        self.assertTrue(deleted_before_push)
        self.assertEqual(
            [name for name, _argv in filtered_operations],
            ["fetch", "remote-observation", "push", "remote-observation"],
        )
        self.assertEqual(
            filtered_operations[2][1],
            [
                "git",
                "--no-pager",
                "-C",
                str(self.worktree),
                "push",
                "--porcelain",
                "origin",
                f"{intended_head}:{destination}",
            ],
        )
        self.assertFalse(
            any(argument.startswith("--force") for argument in filtered_operations[2][1])
        )
        self.assertEqual(
            [event["event"] for event in lifecycle_events],
            [
                "fetch_intent",
                "fetch_result",
                "push_observed",
                "push_intent",
                "push_observed",
            ],
        )
        observations = [
            event["payload"]["delta"]["integration"]
            for event in lifecycle_events
            if event["event"] == "push_observed"
        ]
        self.assertEqual(
            [observation["intent"]["phase"] for observation in observations],
            ["final-prepush", "post-push"],
        )
        self.assertEqual(
            observations[0]["observed"]["attempted_head_containment"], []
        )
        self.assertEqual(
            observations[1]["observed"]["attempted_head_containment"],
            [{"head": intended_head, "contained": True}],
        )
        self.assertEqual(pushed["state"], "pushed")
        self.assertEqual(
            pushed["integration"]["push"]["result"]["classification"],
            "success",
        )
        self.assertEqual(
            pushed["integration"]["observed"]["contains_intended_head"], True
        )
        self.assertEqual(
            pushed["integration"]["observed"]["attempted_head_containment"],
            [{"head": intended_head, "contained": True}],
        )
        self.assertEqual(
            self.git_at(self.origin, "rev-parse", destination),
            intended_head,
        )

    def test_post_intent_absence_preserves_real_non_fast_forward_result(
        self,
    ) -> None:
        engine, store, authorized = self.authorize()
        writer = self.clone_remote_writer("post-intent-absence-writer")
        destination = str(authorized["target"]["destination_ref"])
        original = CLI.run_fenced_command
        operations: list[str] = []
        deleted_after_rejection = False

        def reject_then_delete(lock, **kwargs):
            nonlocal deleted_after_rejection
            operation = str(kwargs.get("operation"))
            if operation == "push":
                self.push_remote_change(
                    writer,
                    "post-intent-race.txt",
                    "advance before candidate push\n",
                )
                result = original(lock, **kwargs)
                self.assertEqual(
                    CLI.MergeEngine._push_classification(result, destination),
                    "non-fast-forward",
                )
                self.git_at(self.origin, "update-ref", "-d", destination)
                deleted_after_rejection = True
            else:
                result = original(lock, **kwargs)
            operations.append(operation)
            return result

        with mock.patch.object(
            CLI, "run_fenced_command", side_effect=reject_then_delete
        ):
            parked = engine.finalize()

        current = store.load(str(authorized["chain_id"]))
        self.assertTrue(parked.ok)
        self.assertTrue(deleted_after_rejection)
        self.assertEqual(
            [name for name in operations if name in {"remote-observation", "push"}],
            ["remote-observation", "push", "remote-observation"],
        )
        self.assertEqual(current["state"], "authorized")
        self.assertEqual(current["integration"]["condition"], "non-fast-forward")
        self.assertEqual(current["integration"]["remote_movement_count"], 1)
        self.assertEqual(current["integration"]["observed"]["exists"], False)
        self.assertEqual(
            current["integration"]["push"]["result"]["classification"],
            "non-fast-forward",
        )
        self.assertEqual(
            current["integration"]["push"]["attempted_heads"],
            [authorized["candidate"]["candidate_head"]],
        )

    def test_recovery_resumes_the_single_fetch_intent(self) -> None:
        engine, store, authorized = self.authorize()
        original = CLI.run_fenced_command

        def kill_after_intent(lock, **kwargs):
            if kwargs.get("operation") == "fetch":
                os.kill(os.getpid(), signal.SIGKILL)
            return original(lock, **kwargs)

        def crash() -> None:
            with mock.patch.object(
                CLI, "run_fenced_command", side_effect=kill_after_intent
            ):
                engine.finalize()

        self.assert_sigkill_crash(crash)

        interrupted = store.load(str(authorized["chain_id"]))
        self.assertEqual(interrupted["state"], "rebasing")
        self.assertEqual(interrupted["integration"]["intent"]["operation"], "fetch")
        recovered = engine.recover()
        self.assertTrue(recovered.ok)
        self.assertEqual(store.load(str(authorized["chain_id"]))["state"], "pushed")
        names = [
            event["event"]
            for event in self.events(store, str(authorized["chain_id"]))
        ]
        self.assertEqual(names.count("epoch_intent"), 1)
        self.assertEqual(names.count("fetch_intent"), 2)
        self.assertEqual(names.count("push_intent"), 1)

    def test_recovery_completes_a_pending_ownership_release(self) -> None:
        engine, store, authorized = self.authorize()
        original = store.transition_locked
        crashed = False

        def crash_after_release_intent(snapshot, event_name, *args, **kwargs):
            nonlocal crashed
            current = original(snapshot, event_name, *args, **kwargs)
            if event_name == "ownership_release_intent" and not crashed:
                crashed = True
                raise RuntimeError("simulated crash after ownership release intent")
            return current

        with mock.patch.object(
            store, "transition_locked", side_effect=crash_after_release_intent
        ), self.assertRaisesRegex(RuntimeError, "ownership release intent"):
            engine.abort("fixture pending release")

        pending = store.load(str(authorized["chain_id"]))
        self.assertEqual(pending["worktree"]["claim"]["status"], "releasing")
        self.assertTrue(Path(pending["worktree"]["claim"]["path"]).exists())
        recovered = engine.recover()
        terminal = store.load(str(authorized["chain_id"]))
        self.assertTrue(recovered.ok)
        self.assertEqual(terminal["state"], "aborted")
        self.assertEqual(terminal["worktree"]["claim"]["status"], "released")
        self.assertFalse(Path(terminal["worktree"]["claim"]["path"]).exists())

    def test_no_attempt_abort_reason_and_preconditions_are_replay_bound(self) -> None:
        engine, store, authorized = self.authorize()
        chain_id = str(authorized["chain_id"])
        original = store.transition_locked
        stopped = False
        operator_reason = "operator prose must not enter the durable cutoff"

        def stop_after_release_intent(snapshot, event_name, *args, **kwargs):
            nonlocal stopped
            current = original(snapshot, event_name, *args, **kwargs)
            if event_name == "ownership_release_intent" and not stopped:
                stopped = True
                raise RuntimeError("stop after no-attempt release intent")
            return current

        with mock.patch.object(
            store,
            "transition_locked",
            side_effect=stop_after_release_intent,
        ), self.assertRaisesRegex(
            RuntimeError, "stop after no-attempt release intent"
        ):
            engine.abort(operator_reason)

        events = self.events(store, chain_id)
        release_index = next(
            index
            for index, event in enumerate(events)
            if event["event"] == "ownership_release_intent"
        )
        release = events[release_index]
        prior = self._original_merge_replay(
            chain_id,
            self.replay_prefix(events, release_index - 1),
        ).state
        expected_preconditions = {
            "schema": "forge-merge-abort-preconditions/1",
            "chain_id": chain_id,
            "source_state": prior["state"],
            "candidate": copy.deepcopy(prior["candidate"]),
            "integration": copy.deepcopy(prior["integration"]),
            "claim": copy.deepcopy(prior["worktree"]["claim"]),
            "reason": None,
        }
        expected_digest = CLI.sha256_bytes(
            CLI.canonical_bytes(expected_preconditions)
        )
        self.assertEqual(release_index, len(events) - 1)
        self.assertEqual(release["payload"]["target_terminal"], "aborted")
        self.assertEqual(
            release["payload"]["terminal_preconditions_digest"],
            expected_digest,
        )
        self.assertNotIn(
            operator_reason.encode("utf-8"), store.events_path(chain_id).read_bytes()
        )

        tampered = copy.deepcopy(events)
        selected = tampered[release_index]["payload"][
            "terminal_preconditions_digest"
        ]
        tampered[release_index]["payload"]["terminal_preconditions_digest"] = (
            ("0" if selected[0] != "0" else "1") + selected[1:]
        )
        tampered_raw = self.reseal_suffix(tampered, release_index)
        with mock.patch.object(
            store, "_read_root_bytes", return_value=tampered_raw
        ), self.assertRaisesRegex(
            CLI.FrozenError,
            rf"merge event {release['sequence']} transition is invalid",
        ):
            store._read_replay_locked(chain_id)

    def test_scope_abort_release_cutoffs_recover_without_rerunning_children(
        self,
    ) -> None:
        self.open_run()
        outside = self.worktree / "outside" / "scope-cutoff.py"
        outside.parent.mkdir()
        outside.write_text("OUTSIDE = True\n", encoding="utf-8")
        self.git_at(self.worktree, "add", "outside/scope-cutoff.py")
        self.git_at(
            self.worktree, "commit", "--quiet", "-m", "scope cutoff fixture"
        )
        remote_before = self.git_at(
            self.origin, "rev-parse", "refs/heads/fixture-main"
        )
        branch_before = self.git("rev-parse", "refs/heads/feature")

        def park_scope_release(cutoff: str):
            starter = CLI.MergeEngine(self.context(run_id=self.run_id))
            ids_before = set(starter.store.list_ids(family="merge"))
            original_transition = starter.store.transition
            stopped = False

            def stop_after_cutoff(snapshot, event_name, *args, **kwargs):
                nonlocal stopped
                current = original_transition(
                    snapshot, event_name, *args, **kwargs
                )
                if event_name == cutoff and not stopped:
                    stopped = True
                    raise RuntimeError(f"scope cutoff after {cutoff}")
                return current

            with mock.patch.object(
                starter.store,
                "transition",
                side_effect=stop_after_cutoff,
            ), self.assertRaisesRegex(
                RuntimeError, rf"scope cutoff after {cutoff}"
            ):
                starter.start_chain(
                    str(self.worktree),
                    task=self.task_id,
                    remote_tip=self.base,
                )
            created = set(starter.store.list_ids(family="merge")) - ids_before
            self.assertEqual(len(created), 1)
            chain_id = created.pop()
            engine = CLI.MergeEngine(self.context(chain_id=chain_id))
            pending = engine.store.load(chain_id)
            events = self.events(engine.store, chain_id)
            self.assertEqual(events[-1]["event"], cutoff)
            return engine, pending, events

        def assert_scope_preimage(engine, events):
            chain_id = str(events[0]["chain_id"])
            replay = self._original_merge_replay(
                chain_id, engine.store.events_path(chain_id).read_bytes()
            )
            release_entry = next(
                entry
                for entry in replay.entries
                if entry[0]["event"] == "ownership_release_intent"
            )
            release, prior = release_entry[:2]
            release_index = next(
                index
                for index, event in enumerate(replay.events)
                if event["digest"] == release["digest"]
            )
            history = list(replay.events[:release_index])
            scope_event = next(
                event
                for event in history
                if event["event"] == "fetch_result"
                and event["payload"]["scope_proof"]["result"] == "exceeded"
            )
            proof = scope_event["payload"]["scope_proof"]
            candidate = prior["candidate"]
            worktree = prior["worktree"]
            preconditions = {
                "schema": "forge-run-scope-abort-preconditions/1",
                "target_terminal": "aborted",
                "terminal_disposition": "ordinary",
                "release_mode": "acquired",
                "source_state": "classifying",
                "scope_proof_digest": proof["digest"],
                "fetch_result_event_digest": scope_event["digest"],
                "generation_digest": candidate["generation_digest"],
                "worktree_identity": {
                    name: worktree[name]
                    for name in ("path", "git_dir", "common_dir")
                },
                "branch": prior["branch"],
                "candidate_head": candidate["candidate_head"],
                "current_head": candidate["candidate_head"],
                "status_output_digest": CLI.sha256_bytes(b""),
                "push_intent_event_digests": [],
                "git_mutation_intent_event_digests": [],
                "unresolved_fence_digests": [],
            }
            self.assertEqual(history[-1]["digest"], scope_event["digest"])
            self.assertEqual(
                release["payload"]["terminal_preconditions_digest"],
                CLI.sha256_bytes(CLI.canonical_bytes(preconditions)),
            )
            self.assertTrue(
                CLI._merge_release_preconditions_valid(release, prior, history)
            )
            return release, prior, history, scope_event

        mutation_carriers = (
            {"event": "rebase_intent", "payload": {}},
            {"event": "push_intent", "payload": {}},
            {"event": "cleanup_intent", "payload": {}},
            {
                "event": "condition_recorded",
                "payload": {
                    "delta": {
                        "integration": {
                            "intent": {
                                "schema": "forge-remote-observation-progress/1",
                                "stage": "containment-intent",
                            }
                        }
                    }
                },
            },
            {
                "event": "condition_recorded",
                "payload": {
                    "delta": {
                        "integration": {
                            "intent": {
                                "schema": "forge-epoch-ancestry-intent/1",
                                "phase": "intent",
                            }
                        }
                    }
                },
            },
        )
        for ordinal, cutoff in enumerate(
            ("ownership_release_intent", "ownership_released")
        ):
            with self.subTest(cutoff=cutoff):
                engine, pending, before = park_scope_release(cutoff)
                chain_id = str(pending["chain_id"])
                release, prior, history, scope_event = assert_scope_preimage(
                    engine, before
                )
                release_payload = copy.deepcopy(release["payload"])
                scope_payload = copy.deepcopy(scope_event["payload"])
                claim_path = Path(str(pending["worktree"]["claim"]["path"]))
                self.assertTrue(claim_path.exists())
                self.assertEqual(
                    pending["worktree"]["claim"]["status"],
                    "releasing" if ordinal == 0 else "released",
                )

                if ordinal == 0:
                    for carrier in mutation_carriers:
                        retained = [*history[:-1], carrier, history[-1]]
                        self.assertFalse(
                            CLI._merge_release_preconditions_valid(
                                release, prior, retained
                            )
                        )
                    tampered = copy.deepcopy(before)
                    release_index = next(
                        index
                        for index, event in enumerate(tampered)
                        if event["digest"] == release["digest"]
                    )
                    digest = tampered[release_index]["payload"][
                        "terminal_preconditions_digest"
                    ]
                    tampered[release_index]["payload"][
                        "terminal_preconditions_digest"
                    ] = ("0" if digest[0] != "0" else "1") + digest[1:]
                    raw = self.reseal_suffix(tampered, release_index)
                    with mock.patch.object(
                        engine.store, "_read_root_bytes", return_value=raw
                    ), self.assertRaisesRegex(
                        CLI.FrozenError,
                        rf"merge event {release['sequence']} transition is invalid",
                    ):
                        engine.store._read_replay_locked(chain_id)

                original_remove = CLI._remove_merge_claim
                bounded_calls: list[list[str]] = []
                tombstone_failures = 0

                def record_bounded(argv, **kwargs):
                    bounded_calls.append(list(argv))
                    return original_bounded(argv, **kwargs)

                def retain_second_tombstone(
                    selected_store, selected_state, *, unlink=True
                ):
                    nonlocal tombstone_failures
                    if ordinal == 1 and unlink:
                        tombstone_failures += 1
                        raise OSError("retain released scope tombstone")
                    return original_remove(
                        selected_store, selected_state, unlink=unlink
                    )

                original_bounded = CLI.run_bounded
                with mock.patch.object(
                    CLI,
                    "run_fenced_command",
                    side_effect=AssertionError(
                        "scope release recovery reran a fenced Git child"
                    ),
                ) as fenced, mock.patch.object(
                    CLI,
                    "acquire_common_lock",
                    side_effect=AssertionError(
                        "scope release recovery acquired the common lock"
                    ),
                ) as common, mock.patch.object(
                    RUNTIME, "run_bounded", side_effect=record_bounded
                ), mock.patch.object(
                    CLI,
                    "_remove_merge_claim",
                    side_effect=retain_second_tombstone,
                ), mock.patch.object(
                    engine,
                    "_recover_classifying_bootstrap_locked",
                    side_effect=AssertionError(
                        "scope release recovery resumed bootstrap"
                    ),
                ) as bootstrap:
                    recovered = engine.recover()
                fenced.assert_not_called()
                common.assert_not_called()
                bootstrap.assert_not_called()

                terminal = engine.store.load(chain_id)
                after = self.events(engine.store, chain_id)
                expected_suffix = (
                    ["ownership_released", "aborted"]
                    if ordinal == 0
                    else ["aborted"]
                )
                self.assertTrue(recovered.ok)
                self.assertEqual(terminal["state"], "aborted")
                self.assertEqual(
                    [event["event"] for event in after[len(before) :]],
                    expected_suffix,
                )
                self.assertEqual(
                    next(
                        event["payload"]
                        for event in after
                        if event["event"] == "ownership_release_intent"
                    ),
                    release_payload,
                )
                self.assertEqual(
                    next(
                        event["payload"]
                        for event in after
                        if event["digest"] == scope_event["digest"]
                    ),
                    scope_payload,
                )
                self.assertEqual(
                    [Path(argv[1]).name for argv in bounded_calls],
                    ["check-halt.sh"],
                )
                self.assertEqual(tombstone_failures, ordinal)
                self.assertEqual(claim_path.exists(), ordinal == 1)
                self.assertEqual(
                    self.git_at(
                        self.origin, "rev-parse", "refs/heads/fixture-main"
                    ),
                    remote_before,
                )
                self.assertEqual(
                    self.git("rev-parse", "refs/heads/feature"), branch_before
                )

    def test_pending_release_stale_lease_routes_through_recovery_lock(self) -> None:
        engine, store, authorized = self.authorize()

        def park_release(selected_engine, selected_store, reason):
            original = selected_store.transition_locked
            stopped = False

            def stop_after_intent(snapshot, event_name, *args, **kwargs):
                nonlocal stopped
                current = original(snapshot, event_name, *args, **kwargs)
                if event_name == "ownership_release_intent" and not stopped:
                    stopped = True
                    raise RuntimeError("park release intent")
                return current

            with mock.patch.object(
                selected_store,
                "transition_locked",
                side_effect=stop_after_intent,
            ), self.assertRaisesRegex(RuntimeError, "park release intent"):
                selected_engine.abort(reason)
            pending = selected_store.load(str(selected_engine.ctx.options.chain_id))
            self.assertEqual(pending["worktree"]["claim"]["status"], "releasing")
            return pending

        first_id = str(authorized["chain_id"])
        park_release(engine, store, "free lease fast path")
        with mock.patch.object(
            CLI,
            "acquire_common_lock",
            side_effect=AssertionError("free pending release acquired common lock"),
        ) as free_common:
            free_recovery = engine.recover()
        free_common.assert_not_called()
        self.assertTrue(free_recovery.ok)
        self.assertEqual(store.load(first_id)["state"], "aborted")

        starter = CLI.MergeEngine(self.context())
        started = starter.start_chain(str(self.worktree), remote_tip=self.base)
        chain_id = str(started.chain_id)
        second = CLI.MergeEngine(self.context(chain_id=chain_id))
        pending = park_release(second, second.store, "stale lease recovery")
        lease_path = second.store.root / f"{chain_id}.lock"

        def reap_bounded(pid: int) -> int:
            deadline = time.monotonic() + self._SIGKILL_DEADLINE_SECONDS
            while time.monotonic() < deadline:
                waited, status = os.waitpid(pid, os.WNOHANG)
                if waited == pid:
                    return status
                time.sleep(self._SIGKILL_POLL_SECONDS)
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            _waited, status = os.waitpid(pid, 0)
            self.fail("stale-lease child exceeded its one-second reap deadline")
            return status

        child = os.fork()
        if child == 0:
            try:
                stranded = CLI.acquire_chain_lease(
                    second.store.root,
                    chain_id=chain_id,
                    session="crashed-release-holder",
                    timeout=0.5,
                )
                if stranded.path != lease_path:
                    os._exit(124)
            except BaseException:
                os._exit(125)
            os._exit(0)
        child_status = reap_bounded(child)
        self.assertTrue(os.WIFEXITED(child_status), child_status)
        self.assertEqual(os.WEXITSTATUS(child_status), 0)
        stale_record = json.loads(lease_path.read_text(encoding="utf-8"))
        self.assertEqual(stale_record["pid"], child)
        self.assertEqual(pending["worktree"]["claim"]["status"], "releasing")

        original_common = self._original_common_lock
        bounded_chain = CLI.acquire_chain_lease
        start_barrier = threading.Barrier(2)
        common_calls: list[tuple[str, str]] = []
        lease_exclusions: list[object] = []
        optimistic_attempts: list[object] = []
        boundaries: list[str] = []
        arrivals: list[int] = []

        def record_common(*args, **kwargs):
            arrivals.append(threading.get_ident())
            try:
                start_barrier.wait(timeout=0.5)
            except threading.BrokenBarrierError as exc:
                raise AssertionError(
                    "same-chain recovery contenders missed the barrier"
                ) from exc
            common_calls.append(
                (str(kwargs.get("operation")), str(kwargs.get("chain_id")))
            )
            kwargs.update(
                timeout=0.5,
                use_flock=False,
                clock=time.monotonic,
                sleeper=lambda seconds: time.sleep(min(seconds, 0.002)),
            )
            return original_common(*args, **kwargs)

        def record_chain(*args, **kwargs):
            exclusion = kwargs.get("exclusion")
            lease_exclusions.append(exclusion)
            if exclusion is None:
                optimistic_attempts.append(kwargs.get("single_attempt"))
                raise AssertionError(
                    "published stale lease incorrectly took the chain-only path"
                )
            kwargs.setdefault("boundary", boundaries.append)
            return bounded_chain(*args, **kwargs)

        before = self.events(second.store, chain_id)
        contenders = [
            CLI.MergeEngine(self.context(chain_id=chain_id)) for _index in range(2)
        ]
        results: list[object | None] = [None, None]

        def recover(index: int) -> None:
            try:
                results[index] = contenders[index].recover()
            except BaseException as exc:
                results[index] = exc

        threads = [
            threading.Thread(
                target=recover,
                args=(index,),
                name=f"stale-release-recover-{index}",
                daemon=True,
            )
            for index in range(2)
        ]
        with mock.patch.object(
            CLI, "acquire_common_lock", side_effect=record_common
        ), mock.patch.object(
            CLI, "acquire_chain_lease", side_effect=record_chain
        ):
            for thread in threads:
                thread.start()
            deadline = time.monotonic() + 1.0
            for thread in threads:
                thread.join(max(0.0, deadline - time.monotonic()))

        terminal = second.store.load(chain_id)
        after = self.events(second.store, chain_id)
        self.assertFalse(
            [thread.name for thread in threads if thread.is_alive()],
            results,
        )
        successes = [result for result in results if isinstance(result, CLI.Outcome)]
        idempotent = [result for result in results if isinstance(result, CLI.Refusal)]
        self.assertEqual(len(successes), 1, results)
        self.assertTrue(successes[0].ok)
        self.assertEqual(len(idempotent), 1, results)
        self.assertEqual(
            idempotent[0].reason_code, CLI.V2ReasonCode.STATE_PRECONDITION
        )
        self.assertEqual(idempotent[0].chain["state"], "aborted")
        self.assertEqual(terminal["state"], "aborted")
        self.assertEqual(terminal["worktree"]["claim"]["status"], "released")
        self.assertEqual(len(set(arrivals)), 2)
        self.assertEqual(optimistic_attempts, [])
        self.assertEqual(common_calls, [("recover", chain_id)] * 2)
        self.assertEqual(len(lease_exclusions), 2)
        self.assertTrue(
            all(
                isinstance(item, CLI.CommonRebaseLock)
                for item in lease_exclusions
            )
        )
        self.assertEqual(boundaries.count("chain-lease-stale-reclaimed"), 1)
        self.assertEqual(
            [event["event"] for event in after[len(before) :]],
            ["ownership_released", "aborted"],
        )
        self.assertEqual(
            sum(event["event"] == "ownership_released" for event in after),
            sum(event["event"] == "ownership_released" for event in before) + 1,
        )
        self.assertEqual(
            sum(event["event"] == "aborted" for event in after),
            sum(event["event"] == "aborted" for event in before) + 1,
        )
        self.assertFalse(lease_path.exists())
        self.assertEqual(
            CLI.inspect_common_lock(
                Path(str(terminal["worktree"]["common_dir"]))
            ).topology,
            "free",
        )

    def test_recovery_appends_only_terminal_after_ownership_released_cutoff(
        self,
    ) -> None:
        engine, store, authorized = self.authorize()
        original = store.transition_locked
        crashed = False

        def crash_after_release_result(snapshot, event_name, *args, **kwargs):
            nonlocal crashed
            current = original(snapshot, event_name, *args, **kwargs)
            if event_name == "ownership_released" and not crashed:
                crashed = True
                raise RuntimeError("simulated crash after ownership release result")
            return current

        with mock.patch.object(
            store, "transition_locked", side_effect=crash_after_release_result
        ), self.assertRaisesRegex(RuntimeError, "ownership release result"):
            engine.abort("fixture released cutoff")

        chain_id = str(authorized["chain_id"])
        released = store.load(chain_id)
        before = self.events(store, chain_id)
        remote_before = self.git_at(
            self.origin, "rev-parse", "refs/heads/fixture-main"
        )
        self.assertEqual(released["state"], "authorized")
        self.assertEqual(released["worktree"]["claim"]["status"], "released")
        self.assertEqual(before[-1]["event"], "ownership_released")

        recovered = engine.recover()
        terminal = store.load(chain_id)
        after = self.events(store, chain_id)
        self.assertTrue(recovered.ok)
        self.assertEqual(terminal["state"], "aborted")
        self.assertEqual(
            [event["event"] for event in after[len(before) :]], ["aborted"]
        )
        self.assertEqual(
            self.git_at(self.origin, "rev-parse", "refs/heads/fixture-main"),
            remote_before,
        )

    def test_terminal_abort_survives_tombstone_collection_failure(self) -> None:
        engine, store, authorized = self.authorize()
        original_remove = CLI._remove_merge_claim

        def fail_only_tombstone_collection(selected_store, state, *, unlink=True):
            if unlink:
                raise OSError("simulated tombstone collection failure")
            return original_remove(selected_store, state, unlink=False)

        with mock.patch.object(
            CLI, "_remove_merge_claim", side_effect=fail_only_tombstone_collection
        ):
            aborted = engine.abort("fixture retained tombstone")

        chain_id = str(authorized["chain_id"])
        terminal = store.load(chain_id)
        claim_path = Path(str(terminal["worktree"]["claim"]["path"]))
        release_digest = next(
            event["digest"]
            for event in reversed(self.events(store, chain_id))
            if event["event"] == "ownership_released"
        )
        self.assertTrue(aborted.ok)
        self.assertEqual(terminal["state"], "aborted")
        self.assertEqual(terminal["worktree"]["claim"]["status"], "released")
        self.assertTrue(claim_path.exists())

        successor = CLI.MergeEngine(self.context()).start_chain(
            str(self.worktree), remote_tip=self.base
        )
        self.assertNotEqual(str(successor.chain_id), chain_id)
        self.assertTrue(successor.ok)
        self.assertEqual(successor.state, "verifying")
        self.assertTrue(claim_path.exists())
        claim_record = json.loads(claim_path.read_text(encoding="utf-8"))
        self.assertEqual(claim_record["chain_id"], str(successor.chain_id))
        successor_intent = next(
            event
            for event in self.events(store, str(successor.chain_id))
            if event["event"] == "ownership_intent"
        )
        self.assertEqual(
            successor_intent["payload"]["predecessor_chain_id"], chain_id
        )
        self.assertEqual(
            successor_intent["payload"]["predecessor_release_digest"],
            release_digest,
        )

    def test_recovery_uses_the_sealed_cursor_after_rebase(self) -> None:
        engine, store, authorized = self.authorize()
        writer = self.clone_remote_writer("gate-crash-writer")
        self.push_remote_change(writer, "remote.txt", "remote generation\n")
        original = CLI.run_fenced_command

        class GateStartBoundary(RuntimeError):
            pass

        def park_before_first_gate(lock, **kwargs):
            if kwargs.get("operation") == "gate":
                raise GateStartBoundary("park before the first sealed gate")
            return original(lock, **kwargs)

        with mock.patch.object(
            CLI, "run_fenced_command", side_effect=park_before_first_gate
        ), self.assertRaisesRegex(GateStartBoundary, "first sealed gate"):
            engine.finalize()
        prepared = store.load(str(authorized["chain_id"]))
        self.assertEqual(prepared["state"], "reverifying")
        self.assertEqual(prepared["integration"]["epoch"]["gate_plan"]["cursor"], 0)

        def kill_before_gate_record(lock, **kwargs):
            if kwargs.get("operation") == "gate":
                os.kill(os.getpid(), signal.SIGKILL)
            return original(lock, **kwargs)

        def crash() -> None:
            with mock.patch.object(
                CLI, "run_fenced_command", side_effect=kill_before_gate_record
            ):
                engine.recover()

        self.assert_sigkill_crash(crash)

        interrupted = store.load(str(authorized["chain_id"]))
        plan = interrupted["integration"]["epoch"]["gate_plan"]
        self.assertEqual(interrupted["state"], "reverifying")
        self.assertEqual(plan["status"], "sealed")
        self.assertEqual(plan["cursor"], 0)
        recovered = engine.recover()
        self.assertTrue(recovered.ok)
        reviewing = store.load(str(authorized["chain_id"]))
        self.assertEqual(reviewing["state"], "reviewing")
        positions = []
        for event in self.events(store, str(authorized["chain_id"])):
            if event["event"] != "gate_recorded":
                continue
            for values in event["payload"]["delta"]["steps"].values():
                if isinstance(values, list) and values:
                    position = values[-1].get("gate_plan_position")
                    if position is not None:
                        positions.append(position["cursor"])
                elif isinstance(values, dict):
                    position = values.get("gate_plan_position")
                    if position is not None:
                        positions.append(position["cursor"])
        self.assertTrue(positions)
        self.assertEqual(min(positions), 0)

    def test_gate_tuple_mutation_parks_before_the_next_fenced_child(self) -> None:
        engine, store, authorized = self.authorize()
        writer = self.clone_remote_writer("gate-mutation-writer")
        remote_tip = self.push_remote_change(
            writer, "remote.txt", "force integrated gate reruns\n"
        )
        original = CLI.run_fenced_command
        gate_calls = 0

        def mutate_after_first_gate(lock, **kwargs):
            nonlocal gate_calls
            result = original(lock, **kwargs)
            if kwargs.get("operation") == "gate":
                gate_calls += 1
                if gate_calls == 1:
                    changed = self.worktree / "src" / "gate-mutated.py"
                    changed.write_text("MUTATED = True\n", encoding="utf-8")
                    self.git_at(self.worktree, "add", "src/gate-mutated.py")
                    self.git_at(
                        self.worktree,
                        "commit",
                        "--quiet",
                        "-m",
                        "mutate tuple after gate child",
                    )
            return result

        with mock.patch.object(
            CLI, "run_fenced_command", side_effect=mutate_after_first_gate
        ), self.assertRaises(CLI.Refusal) as caught:
            engine.finalize()

        parked = store.load(str(authorized["chain_id"]))
        self.assertEqual(caught.exception.reason_code, CLI.V2ReasonCode.CANDIDATE_STALE)
        self.assertEqual(gate_calls, 1)
        self.assertEqual(parked["state"], "verifying")
        self.assertEqual(parked["candidate"]["generation"], 3)
        self.assertEqual(
            parked["candidate"]["candidate_head"],
            self.git_at(self.worktree, "rev-parse", "HEAD"),
        )
        self.assertIsNone(parked["integration"]["epoch"])
        self.assertEqual(parked["steps"], {})
        self.assertEqual(
            self.git_at(self.origin, "rev-parse", "refs/heads/fixture-main"),
            remote_tip,
        )

    def test_push_outcome_unknown_is_resolved_only_by_recovery_observation(self) -> None:
        engine, store, authorized = self.authorize()
        original = CLI.run_fenced_command
        observations = 0

        class PostObservationBoundary(RuntimeError):
            pass

        def park_before_post_observation(lock, **kwargs):
            nonlocal observations
            if kwargs.get("operation") == "remote-observation":
                observations += 1
                if observations == 2:
                    raise PostObservationBoundary(
                        "park after push result before post observation"
                    )
            return original(lock, **kwargs)

        with mock.patch.object(
            CLI,
            "run_fenced_command",
            side_effect=park_before_post_observation,
        ), self.assertRaisesRegex(
            PostObservationBoundary, "before post observation"
        ):
            engine.finalize()
        prepared = store.load(str(authorized["chain_id"]))
        self.assertEqual(prepared["state"], "pushing")
        self.assertEqual(
            prepared["integration"]["push"]["result"]["classification"],
            "success",
        )

        def kill_before_post_observation(lock, **kwargs):
            if kwargs.get("operation") == "remote-observation":
                os.kill(os.getpid(), signal.SIGKILL)
            return original(lock, **kwargs)

        def crash() -> None:
            with mock.patch.object(
                CLI,
                "run_fenced_command",
                side_effect=kill_before_post_observation,
            ):
                engine.recover()

        self.assert_sigkill_crash(crash)

        pushing = store.load(str(authorized["chain_id"]))
        self.assertEqual(pushing["state"], "pushing")
        self.assertEqual(
            pushing["integration"]["push"]["result"]["classification"],
            "success",
        )
        recovered = engine.recover()
        self.assertTrue(recovered.ok)
        self.assertEqual(store.load(str(authorized["chain_id"]))["state"], "pushed")
        names = [
            event["event"]
            for event in self.events(store, str(authorized["chain_id"]))
        ]
        self.assertEqual(names.count("push_intent"), 1)

    def test_transient_known_push_failure_retries_after_fresh_old_tip(self) -> None:
        engine, store, authorized = self.authorize()
        original = CLI.run_fenced_command
        failed_once = False
        push_calls = 0

        def fail_first_push(lock, **kwargs):
            nonlocal failed_once, push_calls
            if kwargs.get("operation") == "push":
                push_calls += 1
            if kwargs.get("operation") == "push" and not failed_once:
                failed_once = True
                output = b"fatal: transient transport failure\n"
                result = CLI.FencedProcessResult(
                    argv=list(kwargs["argv"]),
                    returncode=1,
                    duration_seconds=0.01,
                    output=output,
                    output_digest=CLI.sha256_bytes(output),
                    timed_out=False,
                    output_limit=False,
                    launch_failed=False,
                    group_survived=False,
                    authorized=True,
                    fence_digest="a" * 64,
                    fence_inode=1,
                )
                kwargs["persist_result"](result)
                return result
            return original(lock, **kwargs)

        with mock.patch.object(CLI, "run_fenced_command", side_effect=fail_first_push):
            with self.assertRaises(CLI.Refusal) as first:
                engine.finalize()
            self.assertEqual(first.exception.reason_code, CLI.V2ReasonCode.PUSH_FAILED)
            self.assertEqual(first.exception.message, "forge: merge push failed")
            failed = store.load(str(authorized["chain_id"]))
            self.assertEqual(failed["state"], "pushing")
            self.assertEqual(failed["integration"]["condition"], "push-failed")
            before_retry = store.events_path(str(authorized["chain_id"])).read_bytes()
            with mock.patch.object(
                CLI,
                "MERGE_INTEGRATION_CONTROLS",
                CLI.MERGE_INTEGRATION_CONTROLS - {"push-retry"},
            ), self.assertRaisesRegex(
                CLI.FrozenError,
                "merge integration control is unavailable: push-retry",
            ):
                engine.recover()
            self.assertEqual(
                store.events_path(str(authorized["chain_id"])).read_bytes(),
                before_retry,
            )
            recovered = engine.recover()

        pushed = store.load(str(authorized["chain_id"]))
        self.assertTrue(recovered.ok)
        self.assertEqual(pushed["state"], "pushed")
        events = self.events(store, str(authorized["chain_id"]))
        names = [event["event"] for event in events]
        self.assertEqual(push_calls, 2)
        self.assertEqual(names.count("push_intent"), 2)
        self.assertEqual(names.count("push_observed"), 4)
        push_positions = [
            index for index, name in enumerate(names) if name == "push_intent"
        ]
        between = [
            events[index]["digest"]
            for index in range(push_positions[0] + 1, push_positions[1])
            if names[index] == "push_observed"
        ]
        self.assertEqual(len(between), 2)
        self.assertNotEqual(between[0], between[1])
        between_events = [
            events[index]
            for index in range(push_positions[0] + 1, push_positions[1])
            if names[index] == "push_observed"
        ]
        observed_fences = []
        for event in between_events:
            observation = event["payload"]["delta"]["integration"]["observed"]
            self.assertEqual(observation["exists"], True)
            self.assertEqual(observation["oid"], self.base)
            self.assertEqual(observation["contains_intended_head"], False)
            self.assertTrue(
                all(
                    member["contained"] is False
                    for member in observation["attempted_head_containment"]
                )
            )
            observed_fences.append(observation["inflight_digest"])
        self.assertEqual(len(set(observed_fences)), 2)
        self.assertTrue(
            any(
                event["event"] == "condition_recorded"
                and isinstance(
                    event["payload"].get("delta", {}).get("integration", {}).get(
                        "push"
                    ),
                    dict,
                )
                and event["payload"]["delta"]["integration"]["push"][
                    "result"
                ]["classification"]
                == "known-failure"
                for event in events
            )
        )
        self.assertEqual(
            pushed["integration"]["push"]["attempted_heads"],
            [authorized["candidate"]["candidate_head"]] * 2,
        )
        self.assertEqual(pushed["integration"]["remote_movement_count"], 0)
        self.assertEqual(
            self.git_at(self.origin, "rev-parse", "refs/heads/fixture-main"),
            pushed["candidate"]["candidate_head"],
        )

    def test_inactive_attempted_chain_freshly_observes_all_false_then_aborts(
        self,
    ) -> None:
        engine, store, authorized = self.authorize()
        original = CLI.run_fenced_command
        failed_pushes = 0

        def fail_push_without_remote_effect(lock, **kwargs):
            nonlocal failed_pushes
            if kwargs.get("operation") != "push":
                return original(lock, **kwargs)
            failed_pushes += 1
            output = b"fatal: fixture transport failure before update\n"
            result = CLI.FencedProcessResult(
                argv=list(kwargs["argv"]),
                returncode=1,
                duration_seconds=0.01,
                output=output,
                output_digest=CLI.sha256_bytes(output),
                timed_out=False,
                output_limit=False,
                launch_failed=False,
                group_survived=False,
                authorized=True,
                fence_digest="b" * 64,
                fence_inode=1,
            )
            kwargs["persist_result"](result)
            return result

        with mock.patch.object(
            CLI, "run_fenced_command", side_effect=fail_push_without_remote_effect
        ), self.assertRaises(CLI.Refusal) as failed:
            engine.finalize()
        self.assertEqual(failed.exception.reason_code, CLI.V2ReasonCode.PUSH_FAILED)
        pushing = store.load(str(authorized["chain_id"]))
        self.assertEqual(pushing["state"], "pushing")
        self.assertEqual(CLI._merge_containment(pushing), ("all-false", (False,)))
        before_names = [
            event["event"]
            for event in self.events(store, str(authorized["chain_id"]))
        ]
        recovery_operations: list[str] = []
        abort_operations: list[str] = []

        def record_recovery_observation(lock, **kwargs):
            recovery_operations.append(str(kwargs.get("operation")))
            return original(lock, **kwargs)

        future = CLI.parse_time("2999-01-01T00:00:00Z")
        with mock.patch.object(
            RUNTIME, "utc_now", return_value=future
        ), mock.patch.object(
            CLI, "run_fenced_command", side_effect=record_recovery_observation
        ):
            observed = engine.recover()
        observed_state = store.load(str(authorized["chain_id"]))
        self.assertTrue(observed.ok)
        self.assertEqual(observed.state, "pushing")
        self.assertEqual(
            observed.next_required_step,
            f"forge merge abort --chain-id {authorized['chain_id']}",
        )
        self.assertEqual(
            CLI._merge_containment(observed_state), ("all-false", (False,))
        )
        self.assertEqual(recovery_operations.count("remote-observation"), 1)
        self.assertEqual(recovery_operations.count("containment"), 1)
        self.assertNotIn("push", recovery_operations)
        observed_state_bytes = store.state_path(
            str(authorized["chain_id"])
        ).read_bytes()
        observed_event_bytes = store.events_path(
            str(authorized["chain_id"])
        ).read_bytes()
        observed_events = self.events(store, str(authorized["chain_id"]))
        target_observation = next(
            event
            for event in reversed(observed_events)
            if event["event"] == "push_observed"
        )
        target_sequence = int(target_observation["sequence"])
        validated_transition = CLI._merge_transition_valid
        target_reached = False

        def disable_observation_control_only_at_target(
            replay_builders,
            event,
            prior,
            current,
            *,
            context,
            history=(),
        ):
            nonlocal target_reached
            if event.get("sequence") != target_sequence:
                return validated_transition(
                    replay_builders,
                    event,
                    prior,
                    current,
                    context=context,
                    history=history,
                )
            target_reached = True
            with mock.patch.object(
                CLI,
                "MERGE_INTEGRATION_CONTROLS",
                CLI.MERGE_INTEGRATION_CONTROLS
                - {"observation-first-recovery"},
            ), self.assertRaisesRegex(
                CLI.FrozenError,
                "merge integration control is unavailable: "
                "observation-first-recovery",
            ):
                validated_transition(
                    replay_builders,
                    event,
                    prior,
                    current,
                    context=context,
                    history=history,
                )
            return False

        with mock.patch.object(
            CLI,
            "_merge_transition_valid",
            new=disable_observation_control_only_at_target,
        ), self.assertRaisesRegex(
            CLI.FrozenError,
            rf"merge event {target_sequence} transition is invalid",
        ):
            store.load(str(authorized["chain_id"]))
        self.assertTrue(target_reached)
        self.assertEqual(
            store.state_path(str(authorized["chain_id"])).read_bytes(),
            observed_state_bytes,
        )
        self.assertEqual(
            store.events_path(str(authorized["chain_id"])).read_bytes(),
            observed_event_bytes,
        )

        def record_abort_observation(lock, **kwargs):
            abort_operations.append(str(kwargs.get("operation")))
            return original(lock, **kwargs)

        with mock.patch.object(
            RUNTIME, "utc_now", return_value=future
        ), mock.patch.object(
            CLI, "run_fenced_command", side_effect=record_abort_observation
        ):
            outcome = engine.abort("authoritatively not landed")

        aborted = store.load(str(authorized["chain_id"]))
        after_events = self.events(store, str(authorized["chain_id"]))
        after_names = [event["event"] for event in after_events]
        self.assertTrue(outcome.ok)
        self.assertEqual(outcome.state, "aborted")
        self.assertEqual(outcome.next_required_step, "none — merge chain aborted")
        self.assertEqual(aborted["state"], "aborted")
        self.assertEqual(aborted["worktree"]["claim"]["status"], "released")
        self.assertEqual(failed_pushes, 1)
        self.assertEqual(abort_operations.count("remote-observation"), 1)
        self.assertEqual(abort_operations.count("containment"), 1)
        self.assertNotIn("push", abort_operations)
        self.assertEqual(
            after_names.count("push_observed"),
            before_names.count("push_observed") + 2,
        )
        self.assertEqual(
            after_names[-3:],
            ["ownership_release_intent", "ownership_released", "aborted"],
        )
        self.assertEqual(
            self.git_at(self.origin, "rev-parse", "refs/heads/fixture-main"),
            self.base,
        )

    def test_active_older_only_landing_parks_then_starts_a_fresh_epoch(self) -> None:
        engine, store, authorized, older_head, newer_head, containing_tip = (
            self.prepare_older_only_attempts(defer_post_observation=False)
        )
        chain_id = str(authorized["chain_id"])
        parked = store.load(chain_id)
        self.assertEqual(parked["state"], "authorized")
        self.assertEqual(parked["integration"]["condition"], "remote-moved")
        self.assertEqual(parked["integration"]["push"]["landed_head"], older_head)
        self.assertEqual(CLI._merge_containment(parked), ("older", (True, False)))

        events_before = self.events(store, chain_id)
        epoch_count = sum(event["event"] == "epoch_intent" for event in events_before)
        original = CLI.run_fenced_command
        original_candidate_observation = engine._run_candidate_observation_locked
        candidate_observations: dict[
            tuple[str, str, bool, str | None], dict[str, object]
        ] = {}
        durable_sources: set[str] = set()

        def reuse_bound_candidate_observation(
            state,
            lock,
            lease,
            *,
            verb,
            remote_tip,
            expected_head,
            classify,
            declared_tier=None,
        ):
            source_intent = state.get("integration", {}).get("intent")
            source_digest = CLI.sha256_bytes(CLI.canonical_bytes(source_intent))
            key = (remote_tip, expected_head, classify, declared_tier)
            retained = candidate_observations.get(key)
            requires_fetch_binding = bool(
                isinstance(source_intent, dict)
                and source_intent.get("schema")
                == "forge-epoch-fetch-observation/1"
                and source_digest not in durable_sources
            )
            if retained is None or requires_fetch_binding:
                current, evidence = original_candidate_observation(
                    state,
                    lock,
                    lease,
                    verb=verb,
                    remote_tip=remote_tip,
                    expected_head=expected_head,
                    classify=classify,
                    declared_tier=declared_tier,
                )
                candidate_observations[key] = copy.deepcopy(evidence)
                durable_sources.add(source_digest)
                return current, evidence
            specs = CLI._merge_candidate_observation_step_specs(
                state,
                remote_tip=remote_tip,
                expected_head=expected_head,
                classify=classify,
                declared_tier=declared_tier,
            )
            binding = CLI._merge_candidate_observation_binding(
                state,
                source_intent,
                verb=verb,
                remote_tip=remote_tip,
                expected_head=expected_head,
                classify=classify,
                declared_tier=declared_tier,
            )
            retained_steps = retained.get("steps")
            self.assertIsNotNone(specs)
            self.assertIsNotNone(binding)
            self.assertIsInstance(retained_steps, list)
            self.assertEqual(len(retained_steps), len(specs or ()))
            rebound_steps = []
            for prior, (step, cwd, argv) in zip(retained_steps, specs or ()):
                record = copy.deepcopy(prior)
                record.update(
                    {
                        "generation_digest": state["candidate"][
                            "generation_digest"
                        ],
                        "source_intent": copy.deepcopy(source_intent),
                        "verb": verb,
                        "observation_binding": binding,
                        "step": step,
                        "cwd": str(cwd),
                        "argv": list(argv),
                    }
                )
                rebound_steps.append(record)
            rebound = CLI._merge_candidate_observation_evidence(
                state, rebound_steps
            )
            self.assertIsNotNone(rebound)
            self.assertTrue(
                CLI._merge_candidate_observation_evidence_valid(state, rebound)
            )
            return state, rebound

        gate_calls = 0

        def complete_gate_without_process(lock, **kwargs):
            nonlocal gate_calls
            if kwargs.get("operation") != "gate":
                return original(lock, **kwargs)
            gate_calls += 1
            lock.assert_held()
            self.assertTrue(kwargs["intent_validator"]())
            output = b"fixture fresh epoch gate pass\n"
            result = CLI.FencedProcessResult(
                argv=list(kwargs["argv"]),
                returncode=0,
                duration_seconds=0.0,
                output=output,
                output_digest=CLI.sha256_bytes(output),
                timed_out=False,
                output_limit=False,
                launch_failed=False,
                group_survived=False,
                authorized=True,
                fence_digest=CLI.sha256_bytes(
                    CLI.canonical_bytes(
                        {"argv": kwargs["argv"], "gate_call": gate_calls}
                    )
                ),
                fence_inode=gate_calls,
            )
            kwargs["persist_result"](result)
            return result

        with mock.patch.object(
            CLI,
            "run_fenced_command",
            side_effect=complete_gate_without_process,
        ), mock.patch.object(
            engine,
            "_run_candidate_observation_locked",
            side_effect=reuse_bound_candidate_observation,
        ):
            recovered = engine.recover()
        fresh = store.load(chain_id)
        events_after_recovery = self.events(store, chain_id)
        fresh_head = str(fresh["candidate"]["candidate_head"])
        self.assertTrue(recovered.ok)
        self.assertEqual(fresh["state"], "reviewing")
        self.assertGreater(gate_calls, 0)
        self.assertNotIn(fresh_head, {older_head, newer_head})
        self.assertEqual(
            sum(
                event["event"] == "epoch_intent"
                for event in events_after_recovery
            ),
            epoch_count + 1,
        )
        self.assertEqual(fresh["candidate"]["generation"], 3)
        self.assertIsNone(fresh["integration"]["epoch"])
        self.assertEqual(
            fresh["integration"]["push"]["attempted_heads"],
            [older_head, newer_head],
        )

        engine.review_request()
        requested = store.load(chain_id)
        verdict = self.write_verdict(
            f"{chain_id}-fresh-epoch-pass.txt",
            "PASS",
            requested["review"]["request"],
        )
        attached = engine.review_attach(str(verdict))
        reviewed = store.load(chain_id)
        self.assertEqual(attached.state, "authorized")
        self.assertEqual(reviewed["candidate"]["candidate_head"], fresh_head)
        events_before_push = self.events(store, chain_id)
        push_intents_before = sum(
            event["event"] == "push_intent" for event in events_before_push
        )

        class FreshEpochPushBoundary(RuntimeError):
            pass

        push_boundaries = 0
        push_argv: list[str] | None = None

        def stop_after_durable_push_intent(lock, **kwargs):
            nonlocal push_boundaries, push_argv
            if kwargs.get("operation") == "push":
                push_boundaries += 1
                push_argv = list(kwargs["argv"])
                raise FreshEpochPushBoundary("fresh H3 reached push boundary")
            return complete_gate_without_process(lock, **kwargs)

        with mock.patch.object(
            CLI,
            "run_fenced_command",
            side_effect=stop_after_durable_push_intent,
        ), mock.patch.object(
            engine,
            "_run_candidate_observation_locked",
            side_effect=reuse_bound_candidate_observation,
        ), self.assertRaisesRegex(
            FreshEpochPushBoundary, "fresh H3 reached push boundary"
        ):
            engine.finalize()

        admitted = store.load(chain_id)
        events_after = self.events(store, chain_id)
        push_intents = [
            event for event in events_after if event["event"] == "push_intent"
        ]
        attempted_heads = admitted["integration"]["push"]["attempted_heads"]
        self.assertEqual(push_boundaries, 1)
        self.assertIsNotNone(push_argv)
        self.assertEqual(
            push_argv,
            [
                "git",
                "--no-pager",
                "-C",
                str(self.worktree),
                "push",
                "--porcelain",
                "origin",
                f"{fresh_head}:{admitted['target']['destination_ref']}",
            ],
        )
        self.assertEqual(admitted["state"], "pushing")
        self.assertIsNone(admitted["integration"]["push"]["result"])
        self.assertEqual(attempted_heads, [older_head, newer_head, fresh_head])
        self.assertEqual(attempted_heads.count(older_head), 1)
        self.assertEqual(attempted_heads.count(newer_head), 1)
        self.assertEqual(attempted_heads.count(fresh_head), 1)
        self.assertEqual(len(push_intents), push_intents_before + 1)
        self.assertEqual(
            [
                event["payload"]["delta"]["integration"]["push"][
                    "intended_head"
                ]
                for event in push_intents
            ],
            [older_head, newer_head, fresh_head],
        )
        self.assertEqual(events_after[-1]["event"], "push_intent")
        self.assertEqual(
            sum(event["event"] == "epoch_intent" for event in events_after),
            epoch_count + 2,
        )
        self.assertEqual(
            self.git_at(self.origin, "rev-parse", "refs/heads/fixture-main"),
            containing_tip,
        )

    def test_inactive_authorized_attempt_observes_without_starting_an_epoch(
        self,
    ) -> None:
        engine, store, authorized, older_head, newer_head, containing_tip = (
            self.prepare_older_only_attempts(defer_post_observation=False)
        )
        chain_id = str(authorized["chain_id"])
        parked = store.load(chain_id)
        before = self.events(store, chain_id)
        prior_observation = next(
            event["digest"]
            for event in reversed(before)
            if event["event"] == "push_observed"
        )
        original = CLI.run_fenced_command
        operations: list[str] = []

        def record_observation_children(lock, **kwargs):
            operations.append(str(kwargs.get("operation")))
            return original(lock, **kwargs)

        self.assertEqual(parked["state"], "authorized")
        self.assertEqual(parked["integration"]["condition"], "remote-moved")
        self.assertEqual(CLI._merge_containment(parked), ("older", (True, False)))
        future = CLI.parse_time("2999-01-01T00:00:00Z")
        with mock.patch.object(
            RUNTIME, "utc_now", return_value=future
        ), mock.patch.object(
            CLI, "run_fenced_command", side_effect=record_observation_children
        ), mock.patch.object(
            engine,
            "_begin_epoch",
            side_effect=AssertionError("inactive authorized recovery began an epoch"),
        ) as begin_epoch, mock.patch.object(
            engine,
            "_run_epoch_fetch",
            side_effect=AssertionError("inactive authorized recovery fetched an epoch"),
        ) as fetch_epoch:
            recovered = engine.recover()
        begin_epoch.assert_not_called()
        fetch_epoch.assert_not_called()

        terminal = store.load(chain_id)
        after = self.events(store, chain_id)
        fresh_observation = next(
            event["digest"]
            for event in reversed(after)
            if event["event"] == "push_observed"
        )
        self.assertTrue(recovered.ok)
        self.assertEqual(recovered.state, "aborted")
        self.assertEqual(
            recovered.next_required_step,
            f"forge merge start --worktree {self.worktree}",
        )
        self.assertEqual(terminal["state"], "aborted")
        self.assertEqual(terminal["worktree"]["claim"]["status"], "released")
        self.assertNotEqual(fresh_observation, prior_observation)
        self.assertEqual(
            sum(event["event"] == "push_observed" for event in after),
            sum(event["event"] == "push_observed" for event in before) + 1,
        )
        self.assertEqual(
            sum(event["event"] == "epoch_intent" for event in after),
            sum(event["event"] == "epoch_intent" for event in before),
        )
        self.assertEqual(operations, ["remote-observation", "containment", "containment"])
        self.assertEqual(terminal["integration"]["push"]["landed_head"], older_head)
        self.assertEqual(terminal["integration"]["push"]["intended_head"], newer_head)
        self.assertEqual(CLI._merge_containment(terminal), ("older", (True, False)))
        self.assertEqual(
            self.git_at(self.origin, "rev-parse", "refs/heads/fixture-main"),
            containing_tip,
        )

    def test_inactive_authorized_unavailable_observation_parks_without_retry(
        self,
    ) -> None:
        engine, store, authorized, _older_head, _newer_head, _containing_tip = (
            self.prepare_older_only_attempts(defer_post_observation=False)
        )
        chain_id = str(authorized["chain_id"])
        parked = store.load(chain_id)
        before = self.events(store, chain_id)
        self.assertEqual(parked["state"], "authorized")
        self.assertEqual(parked["integration"]["condition"], "remote-moved")
        operations: list[str] = []

        def persist_unavailable_observation(lock, **kwargs):
            operation = str(kwargs.get("operation"))
            operations.append(operation)
            self.assertEqual(operation, "remote-observation")
            output = b"fixture remote observation unavailable\n"
            result = CLI.FencedProcessResult(
                argv=list(kwargs["argv"]),
                returncode=None,
                duration_seconds=0.01,
                output=output,
                output_digest=CLI.sha256_bytes(output),
                timed_out=False,
                output_limit=False,
                launch_failed=True,
                group_survived=False,
                authorized=True,
                fence_digest="d" * 64,
                fence_inode=1,
            )
            kwargs["persist_result"](result)
            return result

        future = CLI.parse_time("2999-01-01T00:00:00Z")
        with mock.patch.object(
            RUNTIME, "utc_now", return_value=future
        ), mock.patch.object(
            CLI,
            "run_fenced_command",
            side_effect=persist_unavailable_observation,
        ), mock.patch.object(
            engine,
            "_begin_epoch",
            side_effect=AssertionError("inactive unavailable recovery began an epoch"),
        ) as begin_epoch, mock.patch.object(
            engine,
            "_run_epoch_push",
            side_effect=AssertionError("inactive unavailable recovery retried a push"),
        ) as retry_push, self.assertRaises(CLI.Refusal) as caught:
            engine.recover()

        begin_epoch.assert_not_called()
        retry_push.assert_not_called()
        self.assertEqual(caught.exception.reason_code, CLI.V2ReasonCode.PUSH_OUTCOME_UNKNOWN)
        observed = store.load(chain_id)
        after = self.events(store, chain_id)
        self.assertEqual(observed["state"], "pushing")
        self.assertEqual(
            observed["integration"]["condition"], "push-outcome-unknown"
        )
        self.assertEqual(observed["integration"]["primary_condition"], "none")
        self.assertEqual(observed["integration"]["remote_movement_count"], 0)
        self.assertEqual(observed["integration"]["observed"]["exists"], None)
        self.assertEqual(
            observed["integration"]["observed"]["contains_intended_head"], None
        )
        self.assertTrue(
            all(
                member["contained"] is None
                for member in observed["integration"]["observed"][
                    "attempted_head_containment"
                ]
            )
        )
        self.assertEqual(operations, ["remote-observation"])
        self.assertEqual(
            sum(event["event"] == "push_intent" for event in after),
            sum(event["event"] == "push_intent" for event in before),
        )
        self.assertEqual(
            sum(event["event"] == "epoch_intent" for event in after),
            sum(event["event"] == "epoch_intent" for event in before),
        )
        self.assertEqual(
            sum(event["event"] == "push_observed" for event in after),
            sum(event["event"] == "push_observed" for event in before) + 1,
        )

    def test_inactive_current_attempt_wins_without_retry_or_new_epoch(self) -> None:
        engine, store, authorized, _older_head, newer_head, _containing_tip = (
            self.prepare_older_only_attempts(defer_post_observation=False)
        )
        chain_id = str(authorized["chain_id"])
        parked = store.load(chain_id)
        before = self.events(store, chain_id)
        before_names = [event["event"] for event in before]
        self.assertEqual(parked["state"], "authorized")
        self.assertEqual(parked["integration"]["condition"], "remote-moved")
        self.assertEqual(CLI._merge_containment(parked)[0], "older")

        self.git_at(
            self.worktree,
            "push",
            "--quiet",
            "origin",
            f"{newer_head}:refs/heads/current-attempt",
        )
        self.git_at(
            self.origin,
            "update-ref",
            "refs/heads/fixture-main",
            newer_head,
        )
        operations: list[str] = []
        original = CLI.run_fenced_command

        def record_observation(lock, **kwargs):
            operations.append(str(kwargs.get("operation")))
            return original(lock, **kwargs)

        future = CLI.parse_time("2999-01-01T00:00:00Z")
        with mock.patch.object(
            RUNTIME, "utc_now", return_value=future
        ), mock.patch.object(
            CLI, "run_fenced_command", side_effect=record_observation
        ), mock.patch.object(
            engine,
            "_begin_epoch",
            side_effect=AssertionError("inactive current recovery began an epoch"),
        ) as begin_epoch, mock.patch.object(
            engine,
            "_run_epoch_fetch",
            side_effect=AssertionError("inactive current recovery fetched an epoch"),
        ) as fetch_epoch:
            recovered = engine.recover()
        begin_epoch.assert_not_called()
        fetch_epoch.assert_not_called()

        pushed = store.load(chain_id)
        after = self.events(store, chain_id)
        after_names = [event["event"] for event in after]
        self.assertTrue(recovered.ok)
        self.assertEqual(recovered.state, "pushed")
        self.assertEqual(
            recovered.next_required_step,
            f"forge merge cleanup --chain-id {chain_id}",
        )
        self.assertEqual(pushed["state"], "pushed")
        self.assertEqual(pushed["integration"]["condition"], "none")
        self.assertEqual(pushed["integration"]["primary_condition"], "none")
        self.assertEqual(pushed["integration"]["remote_movement_count"], 0)
        self.assertEqual(
            pushed["integration"]["push"]["landed_head"], newer_head
        )
        self.assertEqual(CLI._merge_containment(pushed)[0], "current")
        self.assertEqual(
            after_names.count("push_observed"),
            before_names.count("push_observed") + 1,
        )
        self.assertEqual(
            after_names.count("epoch_intent"), before_names.count("epoch_intent")
        )
        self.assertEqual(
            after_names.count("push_intent"), before_names.count("push_intent")
        )
        self.assertEqual(operations.count("remote-observation"), 1)
        self.assertEqual(operations.count("containment"), 2)
        self.assertNotIn("push", operations)
        self.assertEqual(
            self.git_at(self.origin, "rev-parse", "refs/heads/fixture-main"),
            newer_head,
        )

    def test_inactive_containment_intent_requires_inactive_observation_admission(
        self,
    ) -> None:
        engine, store, authorized, _older_head, _newer_head, _containing_tip = (
            self.prepare_older_only_attempts(defer_post_observation=False)
        )
        chain_id = str(authorized["chain_id"])
        events = self.events(store, chain_id)
        fetch_index = next(
            index
            for index in range(len(events) - 1, -1, -1)
            if events[index]["event"] == "condition_recorded"
            and events[index]
            .get("payload", {})
            .get("delta", {})
            .get("integration", {})
            .get("intent", {})
            .get("schema")
            == "forge-remote-observation-progress/1"
            and events[index]["payload"]["delta"]["integration"]["intent"].get(
                "phase"
            )
            == "post-push"
            and events[index]["payload"]["delta"]["integration"]["intent"].get(
                "stage"
            )
            == "fetch-result"
        )
        prefix_raw = self.replay_prefix(events, fetch_index)
        prefix = self._original_merge_replay(chain_id, prefix_raw).state
        progress = copy.deepcopy(prefix["integration"]["intent"])
        self.assertEqual(progress["stage"], "fetch-result")
        self.assertEqual(progress["fetch_result"]["exists"], True)
        self.assertTrue(progress["heads"])
        head = str(progress["heads"][0])
        tip = str(progress["fetch_result"]["oid"])
        future = CLI.parse_time("2999-01-01T00:00:00Z")
        containment_intent = {
            **progress,
            "stage": "containment-intent",
            "cursor": 0,
            "head": head,
            "argv": CLI._remote_containment_argv(prefix, head, tip),
            "recorded_at": CLI.iso_z(future),
        }
        forged_integration = copy.deepcopy(prefix["integration"])
        forged_integration["intent"] = containment_intent
        forged = {
            "schema": "forge-merge-event/1",
            "chain_id": chain_id,
            "sequence": int(events[fetch_index]["sequence"]) + 1,
            "at": CLI.iso_z(future),
            "event": "condition_recorded",
            "generation_digest": prefix["candidate"]["generation_digest"],
            "previous_digest": events[fetch_index]["digest"],
            "payload": {"delta": {"integration": forged_integration}},
        }
        self.reseal_event(forged)
        hostile_raw = prefix_raw + CLI.canonical_bytes(forged) + b"\n"
        before_state = store.state_path(chain_id).read_bytes()
        before_events = store.events_path(chain_id).read_bytes()
        original_read = store._read_root_bytes

        def hostile_event_prefix(name: str) -> bytes:
            if name == store.events_path(chain_id).name:
                return hostile_raw
            return original_read(name)

        with mock.patch.object(
            store, "_read_root_bytes", side_effect=hostile_event_prefix
        ), mock.patch.object(
            RUNTIME,
            "run_bounded",
            side_effect=AssertionError("inactive containment prefix launched a child"),
        ) as bounded, mock.patch.object(
            CLI,
            "run_fenced_command",
            side_effect=AssertionError("inactive containment prefix launched a fence"),
        ) as fenced, mock.patch.object(
            engine,
            "_run_remote_observation",
            side_effect=AssertionError("inactive containment prefix observed remote"),
        ) as observation, self.assertRaisesRegex(
            CLI.FrozenError,
            rf"merge event {forged['sequence']} transition is invalid",
        ):
            engine.recover()
        bounded.assert_not_called()
        fenced.assert_not_called()
        observation.assert_not_called()
        self.assertEqual(store.state_path(chain_id).read_bytes(), before_state)
        self.assertEqual(store.events_path(chain_id).read_bytes(), before_events)

    def test_inactive_push_observed_requires_fresh_completed_progress(self) -> None:
        engine, store, authorized, _older_head, newer_head, _containing_tip = (
            self.prepare_older_only_attempts(defer_post_observation=False)
        )
        chain_id = str(authorized["chain_id"])
        parked = store.load(chain_id)
        self.assertEqual(parked["state"], "authorized")
        self.assertEqual(CLI._merge_containment(parked)[0], "older")
        events = self.events(store, chain_id)
        future = CLI.parse_time("2999-01-01T00:00:00Z")
        forged_integration = copy.deepcopy(parked["integration"])
        forged_integration["condition"] = "none"
        forged_integration["primary_condition"] = "none"
        forged_integration["remote_movement_count"] = 0
        forged_integration["push"]["landed_head"] = newer_head
        prior_observed = parked["integration"]["observed"]
        forged_integration["observed"] = {
            "exists": True,
            "oid": newer_head,
            "contains_intended_head": True,
            "attempted_head_containment": [
                {"head": head, "contained": True}
                for head in forged_integration["push"]["attempted_heads"]
            ],
            "observed_at": CLI.iso_z(future),
            "inflight_digest": prior_observed["inflight_digest"],
            "output_digest": prior_observed["output_digest"],
        }
        forged = {
            "schema": "forge-merge-event/1",
            "chain_id": chain_id,
            "sequence": len(events) + 1,
            "at": CLI.iso_z(future),
            "event": "push_observed",
            "generation_digest": parked["candidate"]["generation_digest"],
            "previous_digest": events[-1]["digest"],
            "payload": {
                "delta": {
                    "state": "pushed",
                    "integration": forged_integration,
                }
            },
        }
        self.reseal_event(forged)
        hostile_raw = b"".join(
            CLI.canonical_bytes(event) + b"\n" for event in [*events, forged]
        )
        before_state = store.state_path(chain_id).read_bytes()
        before_events = store.events_path(chain_id).read_bytes()
        original_read = store._read_root_bytes

        def hostile_event_prefix(name: str) -> bytes:
            if name == store.events_path(chain_id).name:
                return hostile_raw
            return original_read(name)

        with mock.patch.object(
            store, "_read_root_bytes", side_effect=hostile_event_prefix
        ), mock.patch.object(
            RUNTIME,
            "run_bounded",
            side_effect=AssertionError("forged inactive observation launched a child"),
        ) as bounded, mock.patch.object(
            CLI,
            "run_fenced_command",
            side_effect=AssertionError("forged inactive observation launched a fence"),
        ) as fenced, mock.patch.object(
            engine,
            "_run_remote_observation",
            side_effect=AssertionError("forged inactive observation read remote"),
        ) as observation, self.assertRaisesRegex(
            CLI.FrozenError,
            rf"merge event {forged['sequence']} transition is invalid",
        ):
            engine.recover()
        bounded.assert_not_called()
        fenced.assert_not_called()
        observation.assert_not_called()
        self.assertEqual(store.state_path(chain_id).read_bytes(), before_state)
        self.assertEqual(store.events_path(chain_id).read_bytes(), before_events)

    def test_inactive_unavailable_push_observed_requires_completed_progress(
        self,
    ) -> None:
        engine, store, authorized, _older_head, _newer_head, _containing_tip = (
            self.prepare_older_only_attempts(defer_post_observation=True)
        )
        chain_id = str(authorized["chain_id"])
        parked = store.load(chain_id)
        events = self.events(store, chain_id)
        self.assertEqual(parked["state"], "pushing")
        self.assertTrue(
            CLI._merge_inactive_post_attempt_recovery_ready(parked, events)
        )
        push_intent_digest = next(
            event["digest"]
            for event in reversed(events)
            if event["event"] == "push_intent"
        )
        future = CLI.parse_time("2999-01-01T00:00:00Z")
        observation_integration = copy.deepcopy(parked["integration"])
        observation_integration["intent"] = CLI._remote_observation_intent(
            parked,
            phase="post-push",
            push_intent_digest=str(push_intent_digest),
        )
        observation_intent = {
            "schema": "forge-merge-event/1",
            "chain_id": chain_id,
            "sequence": int(events[-1]["sequence"]) + 1,
            "at": CLI.iso_z(future),
            "event": "condition_recorded",
            "generation_digest": parked["candidate"]["generation_digest"],
            "previous_digest": events[-1]["digest"],
            "payload": {"delta": {"integration": observation_integration}},
        }
        self.reseal_event(observation_intent)
        intent_prefix = b"".join(
            CLI.canonical_bytes(event) + b"\n"
            for event in [*events, observation_intent]
        )
        intent_state = self._original_merge_replay(chain_id, intent_prefix).state
        self.assertEqual(intent_state["state"], "pushing")
        self.assertEqual(
            intent_state["integration"]["intent"], observation_integration["intent"]
        )

        forged_integration = copy.deepcopy(intent_state["integration"])
        forged_integration["condition"] = "push-outcome-unknown"
        forged_integration["primary_condition"] = "none"
        forged_integration["remote_movement_count"] = 0
        forged_integration["push"]["landed_head"] = None
        forged_integration["observed"] = {
            "exists": None,
            "oid": None,
            "contains_intended_head": None,
            "attempted_head_containment": [
                {"head": head, "contained": None}
                for head in forged_integration["push"]["attempted_heads"]
            ],
            "observed_at": CLI.iso_z(future),
            "inflight_digest": "e" * 64,
            "output_digest": "f" * 64,
        }
        forged = {
            "schema": "forge-merge-event/1",
            "chain_id": chain_id,
            "sequence": int(observation_intent["sequence"]) + 1,
            "at": CLI.iso_z(future),
            "event": "push_observed",
            "generation_digest": parked["candidate"]["generation_digest"],
            "previous_digest": observation_intent["digest"],
            "payload": {"delta": {"integration": forged_integration}},
        }
        self.reseal_event(forged)
        hostile_raw = intent_prefix + CLI.canonical_bytes(forged) + b"\n"
        before_state = store.state_path(chain_id).read_bytes()
        before_events = store.events_path(chain_id).read_bytes()
        original_read = store._read_root_bytes

        def hostile_event_prefix(name: str) -> bytes:
            if name == store.events_path(chain_id).name:
                return hostile_raw
            return original_read(name)

        with mock.patch.object(
            store, "_read_root_bytes", side_effect=hostile_event_prefix
        ), mock.patch.object(
            RUNTIME,
            "run_bounded",
            side_effect=AssertionError("forged unavailable observation launched a child"),
        ) as bounded, mock.patch.object(
            CLI,
            "run_fenced_command",
            side_effect=AssertionError("forged unavailable observation launched a fence"),
        ) as fenced, mock.patch.object(
            engine,
            "_run_remote_observation",
            side_effect=AssertionError("forged unavailable observation read remote"),
        ) as observation, self.assertRaisesRegex(
            CLI.FrozenError,
            rf"merge event {forged['sequence']} transition is invalid",
        ):
            engine.recover()
        bounded.assert_not_called()
        fenced.assert_not_called()
        observation.assert_not_called()
        self.assertEqual(store.state_path(chain_id).read_bytes(), before_state)
        self.assertEqual(store.events_path(chain_id).read_bytes(), before_events)

    def test_epoch_child_launchers_refuse_once_authority_is_inactive(self) -> None:
        """The shared guard is load-bearing at the child launch boundary.

        Disabling ``_require_active_merge_epoch`` in memory must make this
        test fail: each launcher would then consume budget and reach the
        fenced child instead of refusing with the pinned diagnostic.
        """

        engine, store, authorized, _older_head, _newer_head, _containing_tip = (
            self.prepare_older_only_attempts(defer_post_observation=False)
        )
        chain_id = str(authorized["chain_id"])
        state = store.load(chain_id)
        before_state = store.state_path(chain_id).read_bytes()
        before_events = store.events_path(chain_id).read_bytes()
        future = CLI.parse_time("2999-01-01T00:00:00Z")

        class RefusingBudget(CLI._MergeEpochBudget):
            def consume(self, member: str) -> None:
                raise AssertionError(f"inactive epoch consumed the {member} budget")

        lock = mock.Mock(name="common-lock")
        lease = mock.Mock(name="chain-lease")
        launchers = {
            "fetch": lambda: engine._run_epoch_fetch(
                copy.deepcopy(state), lock, lease, RefusingBudget()
            ),
            "rebase": lambda: engine._run_epoch_rebase(
                copy.deepcopy(state), "0" * 40, lock, lease, RefusingBudget()
            ),
        }
        for child, launch in launchers.items():
            with self.subTest(child=child), mock.patch.object(
                RUNTIME, "utc_now", return_value=future
            ), mock.patch.object(
                CLI,
                "run_fenced_command",
                side_effect=AssertionError(f"inactive epoch launched the {child} child"),
            ) as fenced, self.assertRaises(CLI.Refusal) as caught:
                launch()
            self.assertEqual(
                caught.exception.reason_code, CLI.V2ReasonCode.STATE_PRECONDITION
            )
            self.assertEqual(
                caught.exception.message,
                "forge: merge epoch refused — inactive authority cannot start "
                "another child",
            )
            fenced.assert_not_called()
            lock.assert_not_called()
            lease.assert_not_called()
        self.assertEqual(store.state_path(chain_id).read_bytes(), before_state)
        self.assertEqual(store.events_path(chain_id).read_bytes(), before_events)

    def test_inactive_unstarted_epoch_refuses_without_observation_or_write(
        self,
    ) -> None:
        engine, store, authorized, _older_head, _newer_head, containing_tip = (
            self.prepare_older_only_attempts(defer_post_observation=False)
        )
        chain_id = str(authorized["chain_id"])

        class EpochFetchBoundary(RuntimeError):
            pass

        with mock.patch.object(
            engine,
            "_run_epoch_fetch",
            side_effect=EpochFetchBoundary("stop before the epoch fetch child"),
        ), self.assertRaisesRegex(EpochFetchBoundary, "before the epoch fetch child"):
            engine.recover()

        parked = store.load(chain_id)
        before_state = store.state_path(chain_id).read_bytes()
        before_events = store.events_path(chain_id).read_bytes()
        before_remote = self.git_at(
            self.origin, "rev-parse", "refs/heads/fixture-main"
        )
        self.assertEqual(parked["state"], "rebasing")
        self.assertTrue(parked["integration"]["push"]["attempted_heads"])
        self.assertEqual(self.events(store, chain_id)[-1]["event"], "epoch_intent")

        future = CLI.parse_time("2999-01-01T00:00:00Z")
        with mock.patch.object(
            RUNTIME, "utc_now", return_value=future
        ), mock.patch.object(
            engine,
            "_prepare_git_no_lazy_fetch_qualification",
            side_effect=AssertionError("inactive pre-push recovery qualified Git"),
        ) as qualification, mock.patch.object(
            CLI,
            "run_fenced_command",
            side_effect=AssertionError("inactive pre-push recovery launched a child"),
        ) as fenced, mock.patch.object(
            engine,
            "_run_remote_observation",
            side_effect=AssertionError("inactive pre-push recovery observed the remote"),
        ) as remote_observation, self.assertRaises(CLI.Refusal) as caught:
            engine.recover()

        self.assertEqual(caught.exception.reason_code, CLI.V2ReasonCode.STATE_PRECONDITION)
        self.assertEqual(
            caught.exception.message,
            "forge: merge recover refused — inactive epoch has no started child",
        )
        qualification.assert_not_called()
        fenced.assert_not_called()
        remote_observation.assert_not_called()
        self.assertEqual(store.state_path(chain_id).read_bytes(), before_state)
        self.assertEqual(store.events_path(chain_id).read_bytes(), before_events)
        self.assertEqual(
            self.git_at(self.origin, "rev-parse", "refs/heads/fixture-main"),
            before_remote,
        )
        self.assertEqual(before_remote, containing_tip)

        history = self.events(store, chain_id)
        self.assertFalse(
            CLI._merge_inactive_post_attempt_recovery_ready(parked, history)
        )
        prior_push_digest = next(
            event["digest"]
            for event in reversed(history)
            if event["event"] == "push_intent"
        )
        poisoned_integration = copy.deepcopy(parked["integration"])
        poisoned_integration["intent"] = CLI._remote_observation_intent(
            parked,
            phase="post-push",
            push_intent_digest=str(prior_push_digest),
        )
        forged = {
            "schema": "forge-merge-event/1",
            "chain_id": chain_id,
            "sequence": len(history) + 1,
            "at": CLI.iso_z(future),
            "event": "condition_recorded",
            "generation_digest": parked["candidate"]["generation_digest"],
            "previous_digest": history[-1]["digest"],
            "payload": {"delta": {"integration": poisoned_integration}},
        }
        self.reseal_event(forged)
        hostile_raw = b"".join(
            CLI.canonical_bytes(event) + b"\n" for event in [*history, forged]
        )
        original_read = store._read_root_bytes

        def hostile_event_prefix(name: str) -> bytes:
            if name == store.events_path(chain_id).name:
                return hostile_raw
            return original_read(name)

        with mock.patch.object(
            store, "_read_root_bytes", side_effect=hostile_event_prefix
        ), mock.patch.object(
            RUNTIME,
            "run_bounded",
            side_effect=AssertionError("hostile inactive prefix launched a child"),
        ) as bounded, mock.patch.object(
            CLI,
            "run_fenced_command",
            side_effect=AssertionError("hostile inactive prefix launched a fence"),
        ) as fenced, self.assertRaisesRegex(
            CLI.FrozenError,
            rf"merge event {forged['sequence']} transition is invalid",
        ):
            engine.recover()
        bounded.assert_not_called()
        fenced.assert_not_called()
        self.assertEqual(store.state_path(chain_id).read_bytes(), before_state)
        self.assertEqual(store.events_path(chain_id).read_bytes(), before_events)

    def test_inactive_unstarted_epoch_crossing_deadline_under_stale_owner_refuses(
        self,
    ) -> None:
        engine, store, authorized, _older_head, _newer_head, _containing_tip = (
            self.prepare_older_only_attempts(defer_post_observation=False)
        )
        chain_id = str(authorized["chain_id"])

        class EpochFetchBoundary(RuntimeError):
            pass

        with mock.patch.object(
            engine,
            "_run_epoch_fetch",
            side_effect=EpochFetchBoundary("stop before the epoch fetch child"),
        ), self.assertRaisesRegex(EpochFetchBoundary, "before the epoch fetch child"):
            engine.recover()

        parked = store.load(chain_id)
        self.assertEqual(parked["state"], "rebasing")
        self.assertEqual(self.events(store, chain_id)[-1]["event"], "epoch_intent")
        common_dir = Path(str(parked["worktree"]["common_dir"]))
        owner_path = common_dir / CLI.COMMON_LOCK_INTENT_NAME
        inner_owner_path = (
            common_dir
            / CLI.COMMON_LOCK_DIRECTORY_NAME
            / CLI.COMMON_LOCK_OWNER_NAME
        )
        reservation_path = common_dir / CLI.COMMON_LOCK_RECOVERY_NAME
        fence_path = common_dir / CLI.COMMON_LOCK_INFLIGHT_NAME
        chain_lease_path = store.root / f"{chain_id}.lock"

        child = os.fork()
        if child == 0:
            try:
                self._original_common_lock(
                    common_dir,
                    owner_kind="merge",
                    chain_id=chain_id,
                    operation="finalize",
                    use_flock=False,
                    timeout=0.5,
                    no_transaction_record=True,
                )
            except BaseException:
                os._exit(125)
            os._exit(0)

        def reap_child_nohang(pid: int) -> int:
            deadline = time.monotonic() + 1.0
            while time.monotonic() < deadline:
                waited, status = os.waitpid(pid, os.WNOHANG)
                if waited == pid:
                    return status
                time.sleep(0.01)
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            kill_deadline = time.monotonic() + 1.0
            while time.monotonic() < kill_deadline:
                waited, status = os.waitpid(pid, os.WNOHANG)
                if waited == pid:
                    self.fail("stale-owner child exceeded its one-second reap deadline")
                    return status
                time.sleep(0.01)
            self.fail("stale-owner child could not be reaped after SIGKILL")
            raise AssertionError("unreachable")

        child_status = reap_child_nohang(child)
        self.assertTrue(os.WIFEXITED(child_status), child_status)
        self.assertEqual(os.WEXITSTATUS(child_status), 0)
        owner_bytes = owner_path.read_bytes()
        owner_inode = owner_path.stat().st_ino
        owner_record = json.loads(owner_bytes)
        self.assertEqual(set(owner_record), CLI._COMMON_LOCK_OWNER_KEYS)
        self.assertEqual(owner_record["host"], CLI.socket.gethostname())
        self.assertEqual(owner_record["pid"], child)
        self.assertEqual(owner_record["owner_kind"], "merge")
        self.assertEqual(owner_record["chain_id"], chain_id)
        self.assertEqual(inner_owner_path.read_bytes(), owner_bytes)
        self.assertEqual(inner_owner_path.stat().st_ino, owner_inode)
        self.assertFalse(fence_path.exists())
        self.assertFalse(reservation_path.exists())
        self.assertFalse(chain_lease_path.exists())

        before_state = store.state_path(chain_id).read_bytes()
        before_events = store.events_path(chain_id).read_bytes()
        inactive_deadline = CLI.parse_time(str(parked["inactive_after"]))
        active_now = inactive_deadline - CLI.dt.timedelta(seconds=1)
        inactive_now = inactive_deadline + CLI.dt.timedelta(seconds=1)
        crossed_deadline = False
        recovery_clock = _LogicalClock()
        boundaries: list[str] = []
        real_acquire = self._original_common_lock

        def selected_now():
            return inactive_now if crossed_deadline else active_now

        def cross_deadline(stage: str) -> None:
            nonlocal crossed_deadline
            boundaries.append(stage)
            if stage == "recovery-reservation-published":
                recovery_clock.value = max(recovery_clock.value, 0.5)
                crossed_deadline = True

        def acquire_across_inactivity_boundary(*args, **kwargs):
            kwargs.update(
                {
                    "timeout": min(float(kwargs.get("timeout", 1.0)), 1.0),
                    "use_flock": False,
                    "clock": recovery_clock,
                    "sleeper": recovery_clock.sleep,
                    "now": selected_now,
                    "pid_probe": lambda _pid: "dead",
                    "boundary": cross_deadline,
                }
            )
            return real_acquire(*args, **kwargs)

        def bounded_before_deadline(argv, **kwargs):
            if crossed_deadline:
                raise AssertionError("deadline crossing launched a bounded child")
            return self.passing_process(argv, **kwargs)

        with mock.patch.object(
            RUNTIME, "utc_now", side_effect=selected_now
        ), mock.patch.object(
            CLI,
            "acquire_common_lock",
            side_effect=acquire_across_inactivity_boundary,
        ), mock.patch.object(
            RUNTIME,
            "run_bounded",
            side_effect=bounded_before_deadline,
        ) as bounded, mock.patch.object(
            CLI,
            "run_fenced_command",
            side_effect=AssertionError("deadline crossing launched a fenced child"),
        ) as fenced, mock.patch.object(
            engine,
            "_run_remote_observation",
            side_effect=AssertionError("deadline crossing observed the remote"),
        ) as observation, self.assertRaises(CLI.Refusal) as caught:
            engine.recover()

        self.assertEqual(caught.exception.reason_code, CLI.V2ReasonCode.STATE_PRECONDITION)
        self.assertEqual(
            caught.exception.message,
            "forge: merge recover refused — inactive epoch has no started child",
        )
        self.assertIn("recovery-reservation-published", boundaries)
        bounded.assert_called_once()
        fenced.assert_not_called()
        observation.assert_not_called()
        self.assertEqual(store.state_path(chain_id).read_bytes(), before_state)
        self.assertEqual(store.events_path(chain_id).read_bytes(), before_events)
        self.assertEqual(owner_path.read_bytes(), owner_bytes)
        self.assertEqual(owner_path.stat().st_ino, owner_inode)
        self.assertEqual(inner_owner_path.read_bytes(), owner_bytes)
        self.assertEqual(inner_owner_path.stat().st_ino, owner_inode)
        self.assertFalse(reservation_path.exists())
        self.assertFalse(chain_lease_path.exists())
        self.assertFalse(fence_path.exists())

    def test_inactive_older_only_landing_releases_tagged_terminal(self) -> None:
        engine, store, authorized, older_head, newer_head, containing_tip = (
            self.prepare_older_only_attempts(defer_post_observation=True)
        )
        chain_id = str(authorized["chain_id"])
        current_head = self.git_at(self.worktree, "rev-parse", "HEAD")
        original = CLI.run_fenced_command
        operations: list[str] = []

        def record_historical_observation(lock, **kwargs):
            operations.append(str(kwargs.get("operation")))
            return original(lock, **kwargs)

        future = CLI.parse_time("2999-01-01T00:00:00Z")
        with mock.patch.object(
            RUNTIME, "utc_now", return_value=future
        ), mock.patch.object(
            CLI, "run_fenced_command", side_effect=record_historical_observation
        ):
            recovered = engine.recover()

        terminal = store.load(chain_id)
        events = self.events(store, chain_id)
        self.assertTrue(recovered.ok)
        self.assertEqual(recovered.state, "aborted")
        self.assertEqual(
            recovered.next_required_step,
            f"forge merge start --worktree {self.worktree}",
        )
        self.assertEqual(terminal["state"], "aborted")
        self.assertEqual(terminal["worktree"]["claim"]["status"], "released")
        self.assertEqual(terminal["integration"]["push"]["landed_head"], older_head)
        self.assertEqual(terminal["integration"]["push"]["intended_head"], newer_head)
        self.assertEqual(CLI._merge_containment(terminal), ("older", (True, False)))
        self.assertEqual(self.git_at(self.worktree, "rev-parse", "HEAD"), current_head)
        self.assertTrue(self.worktree.exists())
        self.assertEqual(operations.count("remote-observation"), 1)
        self.assertEqual(operations.count("containment"), 2)
        self.assertFalse(
            {"push", "worktree-remove", "branch-delete"} & set(operations)
        )
        self.assertEqual(
            [event["event"] for event in events[-3:]],
            ["ownership_release_intent", "ownership_released", "aborted"],
        )
        self.assertEqual(
            events[-3]["payload"]["terminal_disposition"],
            "historical-landed-superseded",
        )
        self.assertEqual(
            events[-1]["payload"],
            {
                "terminal_disposition": "historical-landed-superseded",
                "landed_head": older_head,
                "superseded_head": newer_head,
                "observation_digest": terminal["integration"]["observed"][
                    "output_digest"
                ],
            },
        )
        self.assertEqual(
            self.git_at(self.origin, "rev-parse", "refs/heads/fixture-main"),
            containing_tip,
        )

    def test_historical_release_cutoffs_freeze_terminal_observation_across_remote_moves(
        self,
    ) -> None:
        engine, store, authorized, older_head, newer_head, containing_tip = (
            self.prepare_older_only_attempts(defer_post_observation=True)
        )
        chain_id = str(authorized["chain_id"])
        events_before = self.events(store, chain_id)
        current_head = self.git_at(self.worktree, "rev-parse", "HEAD")
        original_transition = store.transition_locked
        original_fenced = CLI.run_fenced_command
        operations: list[str] = []

        def record_only_initial_historical_observation(lock, **kwargs):
            operations.append(str(kwargs.get("operation")))
            return original_fenced(lock, **kwargs)

        class HistoricalReleaseCutoff(RuntimeError):
            pass

        def stop_after(selected_event: str):
            fired = False

            def delegated(snapshot, event_name, *args, **kwargs):
                nonlocal fired
                current = original_transition(
                    snapshot, event_name, *args, **kwargs
                )
                if event_name == selected_event and not fired:
                    fired = True
                    raise HistoricalReleaseCutoff(
                        f"historical cutoff after {selected_event}"
                    )
                return current

            return delegated

        future = CLI.parse_time("2999-01-01T00:00:00Z")
        with mock.patch.object(
            RUNTIME, "utc_now", return_value=future
        ), mock.patch.object(
            CLI,
            "run_fenced_command",
            side_effect=record_only_initial_historical_observation,
        ), mock.patch.object(
            store,
            "transition_locked",
            side_effect=stop_after("ownership_release_intent"),
        ), self.assertRaisesRegex(
            HistoricalReleaseCutoff,
            "historical cutoff after ownership_release_intent",
        ):
            engine.abort("historical older-only landing")

        pending = store.load(chain_id)
        pending_events = self.events(store, chain_id)
        release_intent = pending_events[-1]
        cutoff_integration = copy.deepcopy(pending["integration"])
        cutoff_observation = copy.deepcopy(cutoff_integration["observed"])
        release_intent_digest = str(release_intent["digest"])
        terminal_preconditions_digest = str(
            release_intent["payload"]["terminal_preconditions_digest"]
        )
        self.assertEqual(pending["state"], "pushing")
        self.assertEqual(pending["worktree"]["claim"]["status"], "releasing")
        self.assertEqual(release_intent["event"], "ownership_release_intent")
        self.assertEqual(
            release_intent["payload"]["terminal_disposition"],
            "historical-landed-superseded",
        )
        self.assertEqual(release_intent["payload"]["target_terminal"], "aborted")
        self.assertEqual(release_intent["payload"]["source_state"], "pushing")
        self.assertEqual(release_intent["payload"]["release_mode"], "acquired")
        self.assertRegex(terminal_preconditions_digest, r"^[0-9a-f]{64}$")
        self.assertEqual(cutoff_observation["oid"], containing_tip)
        self.assertFalse(cutoff_observation["contains_intended_head"])
        self.assertEqual(
            cutoff_observation["attempted_head_containment"],
            [
                {"head": older_head, "contained": True},
                {"head": newer_head, "contained": False},
            ],
        )
        self.assertEqual(CLI._merge_containment(pending), ("older", (True, False)))

        tampered_events = copy.deepcopy(pending_events)
        tampered_release_intent = tampered_events[-1]
        replacement_prefix = (
            "0" if terminal_preconditions_digest[0] != "0" else "1"
        )
        tampered_release_intent["payload"]["terminal_preconditions_digest"] = (
            replacement_prefix + terminal_preconditions_digest[1:]
        )
        self.reseal_event(tampered_release_intent)
        tampered_raw = b"".join(
            CLI.canonical_bytes(event) + b"\n" for event in tampered_events
        )
        with mock.patch.object(
            store, "_read_root_bytes", return_value=tampered_raw
        ), self.assertRaisesRegex(
            CLI.FrozenError,
            rf"merge event {release_intent['sequence']} transition is invalid",
        ):
            store._read_replay_locked(chain_id)

        writer = self.clone_remote_writer("historical-cutoff-writer")
        first_later_tip = self.push_remote_change(
            writer, "historical-after-intent.txt", "after release intent\n"
        )
        with mock.patch.object(
            RUNTIME, "utc_now", return_value=future
        ), mock.patch.object(
            CLI,
            "run_fenced_command",
            side_effect=record_only_initial_historical_observation,
        ), mock.patch.object(
            store,
            "transition_locked",
            side_effect=stop_after("ownership_released"),
        ), mock.patch.object(
            CLI,
            "acquire_common_lock",
            side_effect=AssertionError(
                "releasing recovery acquired the common lock"
            ),
        ) as releasing_common_lock, self.assertRaisesRegex(
            HistoricalReleaseCutoff,
            "historical cutoff after ownership_released",
        ):
            engine.recover()
        releasing_common_lock.assert_not_called()

        released = store.load(chain_id)
        released_events = self.events(store, chain_id)
        release_result = released_events[-1]
        self.assertEqual(released["state"], "pushing")
        self.assertEqual(released["worktree"]["claim"]["status"], "released")
        self.assertEqual(released["integration"], cutoff_integration)
        self.assertEqual(release_result["event"], "ownership_released")
        self.assertEqual(release_result["previous_digest"], release_intent_digest)
        self.assertEqual(
            release_result["payload"]["release_intent_digest"],
            release_intent_digest,
        )
        self.assertEqual(
            release_result["payload"]["terminal_disposition"],
            "historical-landed-superseded",
        )
        self.assertEqual(
            self.git_at(self.origin, "rev-parse", "refs/heads/fixture-main"),
            first_later_tip,
        )

        second_later_tip = self.push_remote_change(
            writer, "historical-after-release.txt", "after ownership released\n"
        )
        original_remove = CLI._remove_merge_claim
        tombstone_collection_attempts = 0

        def fail_terminal_tombstone_collection(
            selected_store, state, *, unlink=True
        ):
            nonlocal tombstone_collection_attempts
            if state.get("state") == "aborted" and unlink:
                tombstone_collection_attempts += 1
                raise OSError("simulated historical tombstone collection cutoff")
            return original_remove(selected_store, state, unlink=unlink)

        with mock.patch.object(
            RUNTIME, "utc_now", return_value=future
        ), mock.patch.object(
            CLI,
            "run_fenced_command",
            side_effect=record_only_initial_historical_observation,
        ), mock.patch.object(
            CLI,
            "_remove_merge_claim",
            side_effect=fail_terminal_tombstone_collection,
        ), mock.patch.object(
            CLI,
            "acquire_common_lock",
            side_effect=AssertionError(
                "released recovery acquired the common lock"
            ),
        ) as released_common_lock:
            recovered = engine.recover()
        released_common_lock.assert_not_called()

        terminal = store.load(chain_id)
        terminal_events = self.events(store, chain_id)
        terminal_event = terminal_events[-1]
        self.assertTrue(recovered.ok)
        self.assertEqual(recovered.state, "aborted")
        self.assertEqual(
            recovered.next_required_step,
            f"forge merge start --worktree {self.worktree}",
        )
        self.assertEqual(terminal["state"], "aborted")
        self.assertEqual(terminal["worktree"]["claim"]["status"], "released")
        self.assertEqual(tombstone_collection_attempts, 1)
        self.assertTrue(Path(terminal["worktree"]["claim"]["path"]).exists())
        self.assertEqual(terminal["integration"], cutoff_integration)
        self.assertEqual(terminal_event["event"], "aborted")
        self.assertEqual(terminal_event["previous_digest"], release_result["digest"])
        self.assertEqual(
            terminal_event["payload"],
            {
                "terminal_disposition": "historical-landed-superseded",
                "landed_head": older_head,
                "superseded_head": newer_head,
                "observation_digest": cutoff_observation["output_digest"],
            },
        )
        terminal_suffix = terminal_events[len(events_before) :]
        tagged = [
            event
            for event in terminal_suffix
            if event["event"]
            in {"ownership_release_intent", "ownership_released", "aborted"}
        ]
        self.assertEqual(
            [event["event"] for event in tagged],
            ["ownership_release_intent", "ownership_released", "aborted"],
        )
        self.assertEqual(
            [event["generation_digest"] for event in tagged],
            [terminal["candidate"]["generation_digest"]] * 3,
        )
        self.assertEqual(
            tagged[0]["payload"]["terminal_preconditions_digest"],
            terminal_preconditions_digest,
        )
        self.assertEqual(operations, ["remote-observation", "containment", "containment"])
        self.assertEqual(self.git_at(self.worktree, "rev-parse", "HEAD"), current_head)
        self.assertTrue(self.worktree.exists())
        self.assertEqual(
            self.git_at(self.origin, "rev-parse", "refs/heads/fixture-main"),
            second_later_tip,
        )

        final_remote_tip = self.push_remote_change(
            writer, "historical-after-terminal.txt", "after terminal fsync\n"
        )
        terminal_after_move = store.load(chain_id)
        self.assertEqual(terminal_after_move["integration"], cutoff_integration)
        self.assertEqual(
            terminal_after_move["integration"]["observed"], cutoff_observation
        )
        self.assertEqual(
            self.events(store, chain_id)[-1]["digest"], terminal_event["digest"]
        )
        self.assertEqual(
            self.git_at(self.origin, "rev-parse", "refs/heads/fixture-main"),
            final_remote_tip,
        )

    def test_recovery_retries_when_no_authorized_push_result_survived(self) -> None:
        engine, store, authorized = self.authorize()
        original = CLI.run_fenced_command

        class PushStartBoundary(RuntimeError):
            pass

        def park_before_push(lock, **kwargs):
            if kwargs.get("operation") == "push":
                raise PushStartBoundary("park after the durable push intent")
            return original(lock, **kwargs)

        with mock.patch.object(
            CLI, "run_fenced_command", side_effect=park_before_push
        ), self.assertRaisesRegex(PushStartBoundary, "durable push intent"):
            engine.finalize()
        prepared = store.load(str(authorized["chain_id"]))
        self.assertEqual(prepared["state"], "pushing")
        self.assertIsNone(prepared["integration"]["push"]["result"])
        observed = engine.recover()
        awaiting_retry = store.load(str(authorized["chain_id"]))
        self.assertTrue(observed.ok)
        self.assertEqual(awaiting_retry["state"], "pushing")
        self.assertIsNone(awaiting_retry["integration"]["push"]["result"])

        chain_id = str(authorized["chain_id"])
        push_intent_digest = next(
            event["digest"]
            for event in reversed(self.events(store, chain_id))
            if event["event"] == "push_intent"
        )
        push_argv = [
            "git",
            "--no-pager",
            "-C",
            str(self.worktree),
            "push",
            "--porcelain",
            "origin",
            (
                f"{awaiting_retry['candidate']['candidate_head']}:"
                f"{awaiting_retry['target']['destination_ref']}"
            ),
        ]
        push_environment = os.environ.copy()
        push_environment.pop("FORGE_SESSION_PID", None)
        push_environment.update(
            {
                "LC_ALL": "C",
                "LANG": "C",
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_NO_LAZY_FETCH": "1",
            }
        )

        reject = self.origin / "hooks" / "pre-receive"
        reject.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        reject.chmod(0o755)

        def crash() -> None:
            lock = self._original_common_lock(
                Path(str(awaiting_retry["worktree"]["common_dir"])),
                owner_kind="merge",
                chain_id=chain_id,
                operation="recover",
                timeout=0.5,
                use_flock=False,
                no_transaction_record=True,
            )
            with lock:
                original(
                    lock,
                    operation="push",
                    intent_digest=push_intent_digest,
                    intent_validator=lambda: True,
                    argv=push_argv,
                    cwd=self.worktree,
                    persist_result=lambda _result: os.kill(
                        os.getpid(), signal.SIGKILL
                    ),
                    env=push_environment,
                    timeout=self._PROCESS_TIMEOUT_SECONDS,
                    cap=CLI.OUTPUT_CAP_BYTES,
                )

        self.assert_sigkill_crash(crash)
        reject.unlink()
        interrupted = store.load(str(authorized["chain_id"]))
        self.assertEqual(interrupted["state"], "pushing")
        self.assertIsNone(interrupted["integration"]["push"]["result"])
        self.assertEqual(
            self.git_at(self.origin, "rev-parse", "refs/heads/fixture-main"),
            self.base,
        )

        self.assertEqual(
            sum(
                event["event"] == "push_intent"
                for event in self.events(store, str(authorized["chain_id"]))
            ),
            1,
        )

        recovered = engine.recover()
        pushed = store.load(str(authorized["chain_id"]))
        self.assertTrue(recovered.ok)
        self.assertEqual(pushed["state"], "pushed")
        self.assertEqual(
            pushed["integration"]["push"]["attempted_heads"],
            [authorized["candidate"]["candidate_head"]] * 2,
        )
        self.assertEqual(
            sum(
                event["event"] == "push_intent"
                for event in self.events(store, str(authorized["chain_id"]))
            ),
            2,
        )
        events = self.events(store, str(authorized["chain_id"]))
        names = [event["event"] for event in events]
        positions = [index for index, name in enumerate(names) if name == "push_intent"]
        observations = [
            events[index]
            for index in range(positions[0] + 1, positions[1])
            if names[index] == "push_observed"
        ]
        self.assertEqual(len(observations), 2)
        fences = []
        for event in observations:
            observation = event["payload"]["delta"]["integration"]["observed"]
            self.assertEqual(observation["exists"], True)
            self.assertEqual(observation["oid"], self.base)
            self.assertEqual(observation["contains_intended_head"], False)
            self.assertTrue(
                all(
                    member["contained"] is False
                    for member in observation["attempted_head_containment"]
                )
            )
            fences.append(observation["inflight_digest"])
        self.assertEqual(len(set(fences)), 2)
        self.assertEqual(pushed["integration"]["remote_movement_count"], 0)

    def test_invalid_candidate_history_mode_parks_before_push_intent(self) -> None:
        self.git(
            "commit",
            "--quiet",
            "--allow-empty",
            "-m",
            "remote-only empty movement",
        )
        movement_tip = self.git("rev-parse", "HEAD")
        self.git_at(self.worktree, "rebase", movement_tip)
        manifest = (self.worktree / ".forge-manifest").read_text(encoding="utf-8")
        manifest = manifest.replace(
            "init_completed: true\n",
            "init_completed: true\nhistory_mutation_mode: invented-v9\n",
        )
        (self.worktree / ".forge-manifest").write_text(manifest, encoding="utf-8")
        self.git_at(self.worktree, "add", ".forge-manifest")
        self.git_at(
            self.worktree,
            "commit",
            "--quiet",
            "-m",
            "candidate with invalid history mode",
        )

        starter = CLI.MergeEngine(self.context())
        started = starter.start_chain(str(self.worktree), remote_tip=self.base)
        engine = CLI.MergeEngine(self.context(chain_id=str(started.chain_id)))
        with mock.patch.object(RUNTIME, "run_bounded", side_effect=self.passing_process):
            engine.verify()
        engine.review_request()
        state = engine.store.load(str(started.chain_id))
        verdict = self.write_verdict(
            "invalid-mode-pass.txt", "PASS", state["review"]["request"]
        )
        engine.review_attach(str(verdict))
        awaiting = engine.store.load(str(started.chain_id))
        self.assertIn(awaiting["state"], {"authorized", "awaiting_approval"})
        if awaiting["state"] == "awaiting_approval":
            engine.approve(awaiting["candidate"]["candidate_head"])
        original_fenced = CLI.run_fenced_command
        moved = False

        def move_during_first_observation(lock, **kwargs):
            nonlocal moved
            if kwargs.get("operation") == "remote-observation" and not moved:
                self.git(
                    "push",
                    "--quiet",
                    "origin",
                    f"{movement_tip}:refs/heads/fixture-main",
                )
                moved = True
            return original_fenced(lock, **kwargs)

        with mock.patch.object(
            CLI, "run_fenced_command", side_effect=move_during_first_observation
        ):
            deferred = engine.finalize()
        moved_state = engine.store.load(str(started.chain_id))
        self.assertTrue(deferred.ok)
        self.assertTrue(moved)
        self.assertEqual(moved_state["state"], "authorized")
        self.assertEqual(moved_state["integration"]["remote_movement_count"], 1)
        before_push = sum(
            event["event"] == "push_intent"
            for event in self.events(engine.store, str(started.chain_id))
        )

        original_bounded = CLI.run_bounded
        mode_reads = []
        push_children = []

        def record_mode_read(argv, **kwargs):
            if "cat-file" in argv:
                mode_reads.append(list(argv))
            return original_bounded(argv, **kwargs)

        def record_push_child(lock, **kwargs):
            if kwargs.get("operation") == "push":
                push_children.append(list(kwargs.get("argv", ())))
            return original_fenced(lock, **kwargs)

        with mock.patch.object(
            RUNTIME, "run_bounded", side_effect=record_mode_read
        ), mock.patch.object(
            CLI, "run_fenced_command", side_effect=record_push_child
        ), self.assertRaises(CLI.Refusal) as caught:
            engine.finalize()
        parked = engine.store.load(str(started.chain_id))
        after_push = sum(
            event["event"] == "push_intent"
            for event in self.events(engine.store, str(started.chain_id))
        )
        self.assertEqual(caught.exception.reason_code, CLI.V2ReasonCode.STATE_PRECONDITION)
        self.assertEqual(
            caught.exception.message,
            "forge: history mutation mode invalid — repair committed .forge-manifest through Forge CLI",
        )
        self.assertEqual(parked["state"], "revising")
        self.assertEqual(parked["integration"]["condition"], "none")
        self.assertIsNone(parked["integration"]["epoch"])
        self.assertEqual(parked["integration"]["remote_movement_count"], 0)
        self.assertEqual(parked["approval"], {})
        self.assertEqual(parked["authorization"], {})
        self.assertEqual(after_push, before_push)
        self.assertEqual(push_children, [])
        self.assertIn(
            "repair committed .forge-manifest through Forge CLI",
            caught.exception.remediation,
        )
        invalid_results = [
            event
            for event in self.events(engine.store, str(started.chain_id))
            if event["event"] == "reverification_result"
            and event["payload"].get("delta", {}).get("integration", {}).get(
                "intent", {}
            ).get("operation")
            == "history-mutation-mode"
        ]
        self.assertEqual(len(invalid_results), 1)
        self.assertEqual(
            invalid_results[0]["payload"]["delta"]["integration"]["intent"][
                "result"
            ],
            "invalid",
        )
        self.assertEqual(
            mode_reads,
            [
                [
                    "git",
                    "cat-file",
                    "blob",
                    f"{parked['candidate']['candidate_head']}:.forge-manifest",
                ]
            ],
        )
        self.assertEqual(
            self.git_at(self.origin, "rev-parse", "refs/heads/fixture-main"),
            movement_tip,
        )

    def test_no_lazy_fetch_unsupported_refuses_before_final_lock(self) -> None:
        engine, store, authorized = self.authorize()
        chain_id = str(authorized["chain_id"])
        before = store.events_path(chain_id).read_bytes()
        original_bounded = CLI.run_bounded
        probe_argv = ["git", "--no-lazy-fetch", "--version"]
        probes = []

        def unsupported(argv, **kwargs):
            if list(argv) != probe_argv:
                return original_bounded(argv, **kwargs)
            probes.append((list(argv), dict(kwargs)))
            output = b"unknown option: --no-lazy-fetch\n"
            return CLI.ProcessResult(
                argv=list(argv),
                returncode=129,
                duration_seconds=0.01,
                output=output,
                output_digest=CLI.sha256_bytes(output),
            )

        with mock.patch.object(
            RUNTIME, "run_bounded", side_effect=unsupported
        ), mock.patch.object(
            CLI, "acquire_common_lock", wraps=CLI.acquire_common_lock
        ) as acquire, self.assertRaises(CLI.Refusal) as caught:
            engine.finalize()
        self.assertEqual(
            caught.exception.reason_code,
            CLI.V2ReasonCode.REBASE_LOCK_UNAVAILABLE,
        )
        self.assertEqual(
            caught.exception.message,
            "forge: merge finalize refused — final intended HEAD mode is unavailable",
        )
        self.assertEqual([entry[0] for entry in probes], [probe_argv])
        self.assertEqual(probes[0][1]["cwd"], self.worktree)
        self.assertEqual(probes[0][1]["env"]["LC_ALL"], "C")
        self.assertEqual(probes[0][1]["env"]["GIT_NO_LAZY_FETCH"], "1")
        acquire.assert_not_called()
        self.assertEqual(store.events_path(chain_id).read_bytes(), before)
        self.assertEqual(
            self.git_at(self.origin, "rev-parse", "refs/heads/fixture-main"),
            self.base,
        )

    def test_no_lazy_fetch_identity_drift_refuses_before_recovery_lock(self) -> None:
        engine, store, authorized = self.authorize()
        chain_id = str(authorized["chain_id"])

        class StopBeforeFinalMode(Exception):
            pass

        with mock.patch.object(
            engine,
            "_final_history_mutation_mode",
            side_effect=StopBeforeFinalMode,
        ), self.assertRaises(StopBeforeFinalMode):
            engine.finalize()
        interrupted = store.load(chain_id)
        self.assertEqual(interrupted["state"], "rebasing")
        plan = interrupted["integration"]["epoch"]["gate_plan"]
        self.assertEqual(plan["status"], "sealed")
        self.assertEqual(plan["cursor"], len(plan["suite"]))
        before = store.events_path(chain_id).read_bytes()

        stable_identity = (
            "/qualified/bin/git",
            "/qualified/bin/git",
            7,
            11,
            0o755,
            1024,
            13,
            17,
        )
        identity_calls = 0
        raw_argv = []
        original_bounded = CLI.run_bounded

        def drifting_identity(_cwd, _environment):
            nonlocal identity_calls
            identity_calls += 1
            if identity_calls == 3:
                return (
                    *stable_identity[:3],
                    stable_identity[3] + 1,
                    *stable_identity[4:],
                )
            return stable_identity

        def bounded(argv, **kwargs):
            raw_argv.append(list(argv))
            if list(argv) == ["git", "--no-lazy-fetch", "--version"]:
                output = b"git version 2.47.3\n"
                return CLI.ProcessResult(
                    argv=list(argv),
                    returncode=0,
                    duration_seconds=0.01,
                    output=output,
                    output_digest=CLI.sha256_bytes(output),
                )
            return original_bounded(argv, **kwargs)

        with mock.patch.object(
            CLI,
            "_git_executable_qualification",
            side_effect=drifting_identity,
        ), mock.patch.object(
            RUNTIME, "run_bounded", side_effect=bounded
        ), mock.patch.object(
            CLI, "acquire_common_lock", wraps=CLI.acquire_common_lock
        ) as acquire, self.assertRaises(CLI.Refusal) as caught:
            engine.recover()
        self.assertEqual(identity_calls, 3)
        self.assertEqual(
            caught.exception.reason_code,
            CLI.V2ReasonCode.REBASE_LOCK_UNAVAILABLE,
        )
        self.assertEqual(
            caught.exception.observed,
            "qualified Git executable or environment changed",
        )
        self.assertEqual(
            raw_argv,
            [
                ["bash", str(self.helpers / "check-halt.sh"), "merge"],
                ["git", "--no-lazy-fetch", "--version"],
            ],
        )
        acquire.assert_not_called()
        self.assertEqual(store.events_path(chain_id).read_bytes(), before)
        self.assertFalse(
            any(
                event["event"] == "push_intent"
                for event in self.events(store, chain_id)
            )
        )
        self.assertEqual(
            self.git_at(self.origin, "rev-parse", "refs/heads/fixture-main"),
            self.base,
        )

    def test_invalid_final_mode_control_is_load_bearing_at_push_boundary(self) -> None:
        engine, store, authorized = self.authorize()
        before = store.events_path(str(authorized["chain_id"])).read_bytes()
        with mock.patch.object(
            CLI,
            "MERGE_INTEGRATION_CONTROLS",
            CLI.MERGE_INTEGRATION_CONTROLS - {"final-intended-head-mode"},
        ), mock.patch.object(
            CLI, "_qualify_git_no_lazy_fetch"
        ) as probe, self.assertRaisesRegex(
            CLI.FrozenError,
            "merge integration control is unavailable: final-intended-head-mode",
        ):
            engine.finalize()
        probe.assert_not_called()
        self.assertEqual(
            store.events_path(str(authorized["chain_id"])).read_bytes(), before
        )

    def test_rebase_conflict_abort_proves_restoration(self) -> None:
        engine, store, authorized = self.authorize()
        writer = self.clone_remote_writer("conflict-writer")
        self.push_remote_change(writer, "src/app.py", "VALUE = 9000\n")
        original = CLI.run_fenced_command
        actions = []

        def record_reflog_action(lock, **kwargs):
            argv = list(kwargs.get("argv", ()))
            if kwargs.get("operation") == "abort" or (
                kwargs.get("operation") == "rebase" and "rebase" in argv
            ):
                actions.append(kwargs["env"].get("GIT_REFLOG_ACTION"))
            return original(lock, **kwargs)

        with mock.patch.object(
            CLI, "run_fenced_command", side_effect=record_reflog_action
        ):
            with self.assertRaises(CLI.Refusal) as caught:
                engine.finalize()
        self.assertEqual(caught.exception.reason_code, CLI.V2ReasonCode.REBASE_CONFLICT)
        conflicted = store.load(str(authorized["chain_id"]))
        self.assertEqual(conflicted["state"], "rebase_conflict")
        pre_head = conflicted["integration"]["pre_rebase"]["head"]
        expected_action = (
            f"forge-merge-rebase:{authorized['chain_id']}:"
            f"{authorized['candidate']['generation_digest']}:"
            f"{conflicted['integration']['epoch']['operation_nonce']}"
        )
        self.assertEqual(actions, [expected_action])

        with mock.patch.object(
            CLI, "run_fenced_command", side_effect=record_reflog_action
        ):
            recovered = engine.recover(abort_rebase=True)
        restored = store.load(str(authorized["chain_id"]))
        self.assertTrue(recovered.ok)
        self.assertEqual(restored["state"], "revising")
        self.assertEqual(restored["integration"]["condition"], "rebase-failed")
        self.assertEqual(self.git_at(self.worktree, "rev-parse", "HEAD"), pre_head)
        self.assertEqual(actions, [expected_action, expected_action])

    def test_explicit_recover_flags_refuse_from_nonconflict_scalar_states(
        self,
    ) -> None:
        engine, store, authorized = self.authorize()
        chain_id = str(authorized["chain_id"])
        legal_scalar_states = (
            "classifying",
            "verifying",
            "reviewing",
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
        )
        _batch, builders, _journal = CLI._coordination_modules()
        self.assertEqual(
            frozenset(legal_scalar_states),
            builders._MERGE_STATES,
        )
        bare_routes = {
            "classifying": "_recover_classifying_bootstrap_locked",
            "rebasing": "_finish_recovered_epoch_locked",
            "reverifying": "_finish_recovered_epoch_locked",
            "reverification_failed": "_run_candidate_observation_locked",
            "pushing": "_run_remote_observation",
        }
        refused_states = tuple(
            state for state in legal_scalar_states if state != "rebase_conflict"
        )
        self.assertEqual(
            set(refused_states),
            set(legal_scalar_states) - {"rebase_conflict"},
        )
        covered_states = {"authorized"}
        self.assert_loud_explicit_recovery_refusal(
            engine,
            store,
            chain_id,
            "authorized",
            bare_route="_wrong_state",
        )

        class StopBeforeFinalMode(Exception):
            pass

        with mock.patch.object(
            engine,
            "_final_history_mutation_mode",
            side_effect=StopBeforeFinalMode,
        ), self.assertRaises(StopBeforeFinalMode):
            engine.finalize()
        interrupted = store.load(chain_id)
        self.assertEqual(interrupted["state"], "rebasing")
        plan = interrupted["integration"]["epoch"]["gate_plan"]
        self.assertEqual(plan["status"], "sealed")
        self.assertEqual(plan["cursor"], len(plan["suite"]))
        self.assert_loud_explicit_recovery_refusal(
            engine,
            store,
            chain_id,
            "rebasing",
            bare_route="_finish_recovered_epoch_locked",
        )
        covered_states.add("rebasing")

        for scalar_state in refused_states:
            if scalar_state in covered_states:
                continue
            selected = copy.deepcopy(interrupted)
            selected["state"] = scalar_state
            self.assert_loud_explicit_recovery_refusal(
                engine,
                store,
                chain_id,
                scalar_state,
                bare_route=bare_routes.get(scalar_state, "_wrong_state"),
                loaded_state=selected,
            )
            covered_states.add(scalar_state)
        self.assertEqual(covered_states, set(refused_states))

    def test_explicit_recover_flags_refuse_from_unowned_conflict_tuple(
        self,
    ) -> None:
        engine, store, authorized = self.authorize()
        writer = self.clone_remote_writer("loud-recover-flags-writer")
        self.push_remote_change(writer, "src/app.py", "VALUE = 9000\n")
        with self.assertRaises(CLI.Refusal) as conflict:
            engine.finalize()
        self.assertEqual(
            conflict.exception.reason_code,
            CLI.V2ReasonCode.REBASE_CONFLICT,
        )

        chain_id = str(authorized["chain_id"])
        conflicted = store.load(chain_id)
        self.assertEqual(conflicted["state"], "rebase_conflict")
        git_dir = Path(str(conflicted["worktree"]["git_dir"]))
        live = [
            path
            for path in (git_dir / "rebase-merge", git_dir / "rebase-apply")
            if path.is_dir()
        ]
        self.assertEqual(len(live), 1)
        rebase_dir = live[0]
        head_name = rebase_dir / "head-name"
        original_head_name = head_name.read_bytes()
        parked_rebase_dir = git_dir / f"{rebase_dir.name}.forge-unowned"
        self.assertFalse(parked_rebase_dir.exists())
        # The exact-owned row is the sole admitted tuple; the existing positive
        # continue and abort tests exercise both explicit modes from that row.
        self.assertTrue(CLI._merge_owned_rebase_metadata(conflicted))

        ownership_predicates = (
            ("owned", "none", None, True),
            ("unowned", "park-rebase-directory", None, False),
            (
                "foreign",
                "replace-head-name",
                b"refs/heads/foreign-owner\n",
                False,
            ),
            ("malformed", "replace-head-name", b"x" * 4097, False),
        )
        _batch, builders, _journal = CLI._coordination_modules()
        legal_scalar_states = tuple(sorted(builders._MERGE_STATES))
        bare_routes = {
            "classifying": "_recover_classifying_bootstrap_locked",
            "rebasing": "_finish_recovered_epoch_locked",
            "rebase_conflict": "_recover_conflict_locked",
            "reverifying": "_finish_recovered_epoch_locked",
            "reverification_failed": "_run_candidate_observation_locked",
            "pushing": "_run_remote_observation",
        }
        refused_tuples = set()
        for (
            predicate,
            mutation,
            replacement,
            expected_owned,
        ) in ownership_predicates:
            try:
                if mutation == "park-rebase-directory":
                    rebase_dir.rename(parked_rebase_dir)
                elif mutation == "replace-head-name":
                    self.assertIsNotNone(replacement)
                    head_name.write_bytes(replacement)
                self.assertEqual(
                    CLI._merge_owned_rebase_metadata(conflicted),
                    expected_owned,
                )
                for scalar_state in legal_scalar_states:
                    selected = copy.deepcopy(conflicted)
                    selected["state"] = scalar_state
                    self.assertEqual(
                        CLI._merge_owned_rebase_metadata(selected),
                        expected_owned,
                    )
                    if scalar_state == "rebase_conflict" and expected_owned:
                        continue
                    self.assert_loud_explicit_recovery_refusal(
                        engine,
                        store,
                        chain_id,
                        scalar_state,
                        bare_route=bare_routes.get(scalar_state, "_wrong_state"),
                        loaded_state=selected,
                        ownership_predicate=predicate,
                    )
                    refused_tuples.add((scalar_state, predicate))
            finally:
                if parked_rebase_dir.exists():
                    parked_rebase_dir.rename(rebase_dir)
                head_name.write_bytes(original_head_name)
            self.assertTrue(CLI._merge_owned_rebase_metadata(conflicted))
        expected_tuples = {
            (scalar_state, predicate)
            for (
                predicate,
                _mutation,
                _replacement,
                expected_owned,
            ) in ownership_predicates
            for scalar_state in legal_scalar_states
            if not (scalar_state == "rebase_conflict" and expected_owned)
        }
        self.assertEqual(refused_tuples, expected_tuples)

    def test_loud_recover_flags_control_is_load_bearing_before_routing(
        self,
    ) -> None:
        engine, store, authorized = self.authorize()
        chain_id = str(authorized["chain_id"])
        control = "loud-recover-flags"
        self.assertIn(control, CLI._REQUIRED_MERGE_INTEGRATION_CONTROLS)
        before_state = store.state_path(chain_id).read_bytes()
        before_events = store.events_path(chain_id).read_bytes()
        modes = (
            (
                "--continue",
                {"continue_rebase": True, "paths": ["src/app.py"]},
            ),
            ("--abort-rebase", {"abort_rebase": True}),
        )
        for flag, arguments in modes:
            with self.subTest(flag=flag), mock.patch.object(
                CLI,
                "_REQUIRED_MERGE_INTEGRATION_CONTROLS",
                CLI._REQUIRED_MERGE_INTEGRATION_CONTROLS - {control},
            ), mock.patch.object(
                CLI,
                "MERGE_INTEGRATION_CONTROLS",
                CLI.MERGE_INTEGRATION_CONTROLS - {control},
            ), mock.patch.object(
                engine,
                "_wrong_state",
                side_effect=AssertionError(
                    f"explicit {flag} was routed as bare recovery"
                ),
            ) as routed, self.assertRaisesRegex(
                CLI.FrozenError,
                "merge integration control is unavailable: loud-recover-flags",
            ):
                engine.recover(**arguments)
            routed.assert_not_called()
            self.assertEqual(
                store.state_path(chain_id).read_bytes(), before_state
            )
            self.assertEqual(
                store.events_path(chain_id).read_bytes(), before_events
            )

    def test_recovery_rejects_foreign_clean_head_as_integrated_rebase(self) -> None:
        """FR-236: clean status plus HEAD movement is not integration proof."""

        engine, store, authorized = self.authorize()
        writer = self.clone_remote_writer("forged-integrated-writer")
        self.push_remote_change(writer, "remote.txt", "force a rebase\n")
        original = CLI.run_fenced_command

        def kill_before_rebase_child(lock, **kwargs):
            if kwargs.get("operation") == "rebase":
                os.kill(os.getpid(), signal.SIGKILL)
            return original(lock, **kwargs)

        def crash() -> None:
            with mock.patch.object(
                CLI, "run_fenced_command", side_effect=kill_before_rebase_child
            ):
                engine.finalize()

        self.assert_sigkill_crash(crash)
        interrupted = store.load(str(authorized["chain_id"]))
        self.assertEqual(interrupted["state"], "rebasing")
        self.assertEqual(interrupted["integration"]["intent"]["operation"], "rebase")

        foreign = self.worktree / "src" / "foreign.py"
        foreign.write_text("FOREIGN = True\n", encoding="utf-8")
        self.git_at(self.worktree, "add", "src/foreign.py")
        self.git_at(
            self.worktree, "commit", "--quiet", "-m", "foreign head movement"
        )
        foreign_head = self.git_at(self.worktree, "rev-parse", "HEAD")
        before_results = sum(
            event["event"] == "rebase_result"
            for event in self.events(store, str(authorized["chain_id"]))
        )
        before_events = store.events_path(str(authorized["chain_id"])).read_bytes()
        with mock.patch.object(
            CLI,
            "MERGE_INTEGRATION_CONTROLS",
            CLI.MERGE_INTEGRATION_CONTROLS - {"observation-first-recovery"},
        ), self.assertRaisesRegex(
            CLI.FrozenError,
            "merge integration control is unavailable: observation-first-recovery",
        ):
            engine.recover()
        self.assertEqual(
            store.events_path(str(authorized["chain_id"])).read_bytes(),
            before_events,
        )

        outcome = engine.recover()
        recovered = store.load(str(authorized["chain_id"]))
        after_results = sum(
            event["event"] == "rebase_result"
            for event in self.events(store, str(authorized["chain_id"]))
        )
        self.assertEqual(recovered["integration"]["condition"], "foreign-git-state")
        self.assertTrue(outcome.ok)
        self.assertNotEqual(recovered["candidate"]["candidate_head"], foreign_head)
        self.assertEqual(after_results, before_results)

    def test_recovery_without_started_rebase_authorizes_a_retry(self) -> None:
        """FR-232 row 913 is distinct from a durable failed rebase result."""

        engine, store, authorized = self.authorize()
        writer = self.clone_remote_writer("pre-rebase-retry-writer")
        self.push_remote_change(writer, "remote.txt", "force a retryable rebase\n")
        original = CLI.run_fenced_command

        def kill_before_rebase_child(lock, **kwargs):
            if kwargs.get("operation") == "rebase":
                os.kill(os.getpid(), signal.SIGKILL)
            return original(lock, **kwargs)

        def crash() -> None:
            with mock.patch.object(
                CLI, "run_fenced_command", side_effect=kill_before_rebase_child
            ):
                engine.finalize()

        self.assert_sigkill_crash(crash)
        pre_rebase = store.load(str(authorized["chain_id"]))["integration"][
            "pre_rebase"
        ]["head"]
        self.assertEqual(self.git_at(self.worktree, "rev-parse", "HEAD"), pre_rebase)

        recovered = engine.recover()
        retryable = store.load(str(authorized["chain_id"]))
        self.assertTrue(recovered.ok)
        self.assertEqual(retryable["state"], "authorized")
        self.assertEqual(retryable["integration"]["condition"], "none")
        self.assertIsNone(retryable["integration"]["epoch"])

    def test_integrated_observation_timeout_cannot_materialize_a_generation(self) -> None:
        engine, store, authorized = self.authorize()
        writer = self.clone_remote_writer("integrated-observation-timeout-writer")
        self.push_remote_change(writer, "remote.txt", "requires integration proof\n")
        original = CLI.run_fenced_command
        injected = False
        symbolic_ref_observations = 0

        def timeout_branch_observation(lock, **kwargs):
            nonlocal injected, symbolic_ref_observations
            argv = list(kwargs.get("argv", ()))
            if (
                kwargs.get("operation") == "containment"
                and "symbolic-ref" in argv
            ):
                symbolic_ref_observations += 1
            if (
                not injected
                and symbolic_ref_observations == 2
            ):
                injected = True
                output = b"simulated integrated observation timeout\n"
                result = CLI.FencedProcessResult(
                    argv=argv,
                    returncode=None,
                    duration_seconds=1200.0,
                    output=output,
                    output_digest=CLI.sha256_bytes(output),
                    timed_out=True,
                    output_limit=False,
                    launch_failed=False,
                    group_survived=False,
                    authorized=True,
                    fence_digest="e" * 64,
                    fence_inode=1,
                )
                kwargs["persist_result"](result)
                return result
            return original(lock, **kwargs)

        with mock.patch.object(
            CLI, "run_fenced_command", side_effect=timeout_branch_observation
        ), self.assertRaises(CLI.Refusal) as caught:
            engine.finalize()
        current = store.load(str(authorized["chain_id"]))
        self.assertTrue(injected)
        self.assertEqual(symbolic_ref_observations, 2)
        self.assertEqual(
            caught.exception.reason_code, CLI.V2ReasonCode.STATE_PRECONDITION
        )
        self.assertEqual(current["state"], "rebasing")
        self.assertEqual(current["integration"]["condition"], "foreign-git-state")
        self.assertEqual(
            current["candidate"]["candidate_head"],
            authorized["candidate"]["candidate_head"],
        )
        self.assertNotEqual(
            self.git_at(self.worktree, "rev-parse", "HEAD"),
            current["candidate"]["candidate_head"],
        )

    def test_continue_refuses_paths_outside_recorded_conflict_set(self) -> None:
        """The binding-review contamination probe is a permanent regression."""

        engine, store, authorized = self.authorize()
        writer = self.clone_remote_writer("continue-contamination-writer")
        self.push_remote_change(writer, "src/app.py", "VALUE = 9000\n")
        with self.assertRaises(CLI.Refusal) as conflict:
            engine.finalize()
        self.assertEqual(conflict.exception.reason_code, CLI.V2ReasonCode.REBASE_CONFLICT)
        conflicted = store.load(str(authorized["chain_id"]))
        self.assertEqual(
            conflicted["integration"]["conflict"]["authorized_paths"],
            ["src/app.py"],
        )

        (self.worktree / "src" / "app.py").write_text(
            "VALUE = 9001\n", encoding="utf-8"
        )
        contaminant = self.worktree / "src" / "contaminant.py"
        contaminant.write_text("CONTAMINATED = True\n", encoding="utf-8")
        before_events = store.events_path(str(authorized["chain_id"])).read_bytes()

        with self.assertRaises(CLI.Refusal) as caught:
            engine.recover(
                continue_rebase=True,
                paths=["src/app.py", "src/contaminant.py"],
            )
        self.assertEqual(caught.exception.reason_code, CLI.V2ReasonCode.STATE_PRECONDITION)
        self.assertEqual(
            store.events_path(str(authorized["chain_id"])).read_bytes(), before_events
        )
        self.assertFalse(
            CLI.Repository(self.worktree).git(
                ["ls-files", "--error-unmatch", "src/contaminant.py"], check=False
            ).returncode
            == 0
        )

    def test_continue_refuses_nonconflict_index_and_status_contamination(self) -> None:
        engine, store, authorized = self.authorize()
        writer = self.clone_remote_writer("continue-baseline-writer")
        remote_tip = self.push_remote_change(writer, "src/app.py", "VALUE = 9000\n")
        with self.assertRaises(CLI.Refusal):
            engine.finalize()

        (self.worktree / "src" / "app.py").write_text(
            "VALUE = 9001\n", encoding="utf-8"
        )
        staged = self.worktree / "src" / "staged-contaminant.py"
        staged.write_text("CONTAMINATED = True\n", encoding="utf-8")
        self.git_at(self.worktree, "add", "src/staged-contaminant.py")
        before_head = self.git_at(self.worktree, "rev-parse", "HEAD")

        with self.assertRaises(CLI.Refusal) as caught:
            engine.recover(continue_rebase=True, paths=["src/app.py"])
        current = store.load(str(authorized["chain_id"]))
        self.assertEqual(caught.exception.reason_code, CLI.V2ReasonCode.STATE_PRECONDITION)
        self.assertEqual(current["state"], "rebase_conflict")
        self.assertEqual(current["integration"]["condition"], "foreign-git-state")
        self.assertEqual(self.git_at(self.worktree, "rev-parse", "HEAD"), before_head)
        self.assertEqual(
            self.git_at(self.origin, "rev-parse", "refs/heads/fixture-main"),
            remote_tip,
        )

    def test_continue_refuses_changed_rebase_metadata_before_staging(self) -> None:
        engine, store, authorized = self.authorize()
        writer = self.clone_remote_writer("continue-metadata-writer")
        remote_tip = self.push_remote_change(
            writer, "src/app.py", "VALUE = 9000\n"
        )
        with self.assertRaises(CLI.Refusal):
            engine.finalize()
        conflicted = store.load(str(authorized["chain_id"]))
        git_dir = Path(str(conflicted["worktree"]["git_dir"]))
        live = [
            path
            for path in (git_dir / "rebase-merge", git_dir / "rebase-apply")
            if path.is_dir()
        ]
        self.assertEqual(len(live), 1)
        (live[0] / "head-name").write_text(
            "refs/heads/foreign-owner\n", encoding="utf-8"
        )
        (self.worktree / "src" / "app.py").write_text(
            "VALUE = 9001\n", encoding="utf-8"
        )
        original = CLI.run_fenced_command
        mutation_argv = []

        def record_mutation_children(lock, **kwargs):
            argv = list(kwargs.get("argv", ()))
            if "add" in argv or argv == ["git", "rebase", "--continue"]:
                mutation_argv.append(argv)
            return original(lock, **kwargs)

        with mock.patch.object(
            CLI, "run_fenced_command", side_effect=record_mutation_children
        ), self.assertRaises(CLI.Refusal) as caught:
            engine.recover(continue_rebase=True, paths=["src/app.py"])
        current = store.load(str(authorized["chain_id"]))
        self.assertEqual(caught.exception.reason_code, CLI.V2ReasonCode.STATE_PRECONDITION)
        self.assertEqual(current, conflicted)
        self.assertEqual(mutation_argv, [])
        self.assertEqual(
            self.git_at(self.origin, "rev-parse", "refs/heads/fixture-main"),
            remote_tip,
        )

    def test_continue_rechecks_baselines_after_literal_staging(self) -> None:
        engine, store, authorized = self.authorize()
        writer = self.clone_remote_writer("continue-post-stage-writer")
        self.push_remote_change(writer, "src/app.py", "VALUE = 9000\n")
        with self.assertRaises(CLI.Refusal):
            engine.finalize()
        (self.worktree / "src" / "app.py").write_text(
            "VALUE = 9001\n", encoding="utf-8"
        )
        original = CLI.run_fenced_command
        contaminated = False

        def contaminate_after_stage(lock, **kwargs):
            nonlocal contaminated
            result = original(lock, **kwargs)
            if (
                kwargs.get("operation") == "continue"
                and "add" in kwargs["argv"]
                and not contaminated
            ):
                contaminated = True
                path = self.worktree / "src" / "post-stage-contaminant.py"
                path.write_text("CONTAMINATED = True\n", encoding="utf-8")
                self.git_at(self.worktree, "add", "src/post-stage-contaminant.py")
            return result

        with mock.patch.object(
            CLI, "run_fenced_command", side_effect=contaminate_after_stage
        ), self.assertRaises(CLI.Refusal) as caught:
            engine.recover(continue_rebase=True, paths=["src/app.py"])
        current = store.load(str(authorized["chain_id"]))
        self.assertTrue(contaminated)
        self.assertEqual(caught.exception.reason_code, CLI.V2ReasonCode.STATE_PRECONDITION)
        self.assertEqual(current["state"], "rebase_conflict")
        self.assertEqual(current["integration"]["condition"], "foreign-git-state")
        self.assertNotIn(
            "src/post-stage-contaminant.py",
            self.git_at(self.worktree, "show", "--format=", "--name-only", "HEAD"),
        )

    def test_bare_recover_resumes_after_literal_staging_without_restaging(self) -> None:
        engine, store, authorized = self.authorize()
        writer = self.clone_remote_writer("continue-stage-crash-writer")
        self.push_remote_change(writer, "src/app.py", "VALUE = 9000\n")
        with self.assertRaises(CLI.Refusal):
            engine.finalize()
        (self.worktree / "src" / "app.py").write_text(
            "VALUE = 9001\n", encoding="utf-8"
        )
        original = CLI.run_fenced_command

        def kill_after_stage(lock, **kwargs):
            result = original(lock, **kwargs)
            if kwargs.get("operation") == "continue" and "add" in kwargs["argv"]:
                os.kill(os.getpid(), signal.SIGKILL)
            return result

        def crash() -> None:
            with mock.patch.object(
                CLI, "run_fenced_command", side_effect=kill_after_stage
            ):
                engine.recover(continue_rebase=True, paths=["src/app.py"])

        self.assert_sigkill_crash(crash)
        interrupted = store.load(str(authorized["chain_id"]))
        self.assertEqual(interrupted["state"], "rebase_conflict")
        self.assertEqual(interrupted["integration"]["intent"]["phase"], "stage-result")
        calls = []

        def record_resume(lock, **kwargs):
            argv = list(kwargs.get("argv", ()))
            if argv == ["git", "rebase", "--continue"] or "add" in argv:
                calls.append(argv)
            return original(lock, **kwargs)

        with mock.patch.object(CLI, "run_fenced_command", side_effect=record_resume):
            recovered = engine.recover()
        self.assertTrue(recovered.ok)
        self.assertEqual(calls, [["git", "rebase", "--continue"]])
        self.assertEqual(
            store.load(str(authorized["chain_id"]))["state"], "reviewing"
        )

    def test_abnormal_continue_result_retains_fail_closed_conflict_evidence(self) -> None:
        engine, store, authorized = self.authorize()
        writer = self.clone_remote_writer("continue-timeout-writer")
        self.push_remote_change(writer, "src/app.py", "VALUE = 9000\n")
        with self.assertRaises(CLI.Refusal):
            engine.finalize()
        (self.worktree / "src" / "app.py").write_text(
            "VALUE = 9001\n", encoding="utf-8"
        )
        original = CLI.run_fenced_command

        def timeout_continue(lock, **kwargs):
            if kwargs.get("operation") == "continue" and kwargs["argv"] == [
                "git",
                "rebase",
                "--continue",
            ]:
                output = b"simulated continuation timeout\n"
                result = CLI.FencedProcessResult(
                    argv=list(kwargs["argv"]),
                    returncode=None,
                    duration_seconds=1200.0,
                    output=output,
                    output_digest=CLI.sha256_bytes(output),
                    timed_out=True,
                    output_limit=False,
                    launch_failed=False,
                    group_survived=False,
                    authorized=True,
                    fence_digest="c" * 64,
                    fence_inode=1,
                )
                kwargs["persist_result"](result)
                return result
            return original(lock, **kwargs)

        with mock.patch.object(
            CLI, "run_fenced_command", side_effect=timeout_continue
        ), self.assertRaises(CLI.Refusal) as caught:
            engine.recover(continue_rebase=True, paths=["src/app.py"])
        current = store.load(str(authorized["chain_id"]))
        self.assertEqual(caught.exception.reason_code, CLI.V2ReasonCode.REBASE_FAILED)
        self.assertEqual(current["state"], "rebase_conflict")
        self.assertEqual(current["integration"]["condition"], "foreign-git-state")
        self.assertIsNotNone(current["integration"]["epoch"])
        self.assertIsNotNone(current["integration"]["conflict"])
        git_dir = Path(str(current["worktree"]["git_dir"]))
        self.assertTrue(
            (git_dir / "rebase-merge").exists()
            or (git_dir / "rebase-apply").exists()
        )

    def test_continue_uses_literal_direct_argv_and_preserves_baselines(self) -> None:
        engine, store, authorized = self.authorize()
        writer = self.clone_remote_writer("literal-continue-writer")
        self.push_remote_change(writer, "src/app.py", "VALUE = 9000\n")
        with self.assertRaises(CLI.Refusal):
            engine.finalize()
        conflicted = store.load(str(authorized["chain_id"]))
        conflict = conflicted["integration"]["conflict"]
        for name in ("index_baseline_digest", "status_baseline_digest"):
            self.assertRegex(conflict[name], r"^[0-9a-f]{64}$")

        (self.worktree / "src" / "app.py").write_text(
            "VALUE = 9001\n", encoding="utf-8"
        )
        original = CLI.run_fenced_command
        calls = []
        observation_calls = []
        observation_argv = {
            (
                "git",
                "diff",
                "--name-only",
                "--diff-filter=U",
                "-z",
                "--",
            ),
            ("git", "ls-files", "--stage", "-z", "--"),
            (
                "git",
                "status",
                "--porcelain=v1",
                "-z",
                "--untracked-files=all",
            ),
        }

        def record_calls(lock, **kwargs):
            argv = list(kwargs.get("argv", ()))
            if argv == ["git", "rebase", "--continue"] or "add" in argv:
                calls.append((argv, dict(kwargs["env"])))
            if tuple(argv) in observation_argv:
                observation_calls.append((kwargs.get("operation"), tuple(argv)))
            return original(lock, **kwargs)

        with mock.patch.object(CLI, "run_fenced_command", side_effect=record_calls):
            outcome = engine.recover(continue_rebase=True, paths=["src/app.py"])
        self.assertTrue(outcome.ok)
        self.assertEqual(len(calls), 2)
        self.assertEqual(
            calls[0][0],
            [
                "git",
                "--literal-pathspecs",
                "add",
                "--",
                "src/app.py",
            ],
        )
        self.assertEqual(
            calls[1][0],
            [
                "git",
                "rebase",
                "--continue",
            ],
        )
        self.assertEqual(calls[1][1]["GIT_EDITOR"], "true")
        self.assertEqual(
            calls[0][1]["GIT_REFLOG_ACTION"], calls[1][1]["GIT_REFLOG_ACTION"]
        )
        self.assertNotIn("sh", [argv[0] for argv, _env in calls])
        self.assertEqual(
            {argv for _operation, argv in observation_calls}, observation_argv
        )
        self.assertTrue(observation_calls)
        self.assertEqual(
            {operation for operation, _argv in observation_calls}, {"continue"}
        )

    def test_conflict_continue_control_is_load_bearing_at_conflict_boundary(self) -> None:
        engine, store, authorized = self.authorize()
        writer = self.clone_remote_writer("continue-control-writer")
        remote_tip = self.push_remote_change(
            writer, "src/app.py", "VALUE = 9000\n"
        )
        with self.assertRaises(CLI.Refusal):
            engine.finalize()
        (self.worktree / "src" / "app.py").write_text(
            "VALUE = 9001\n", encoding="utf-8"
        )
        chain_id = str(authorized["chain_id"])
        before_events = store.events_path(chain_id).read_bytes()
        before_index = (Path(str(store.load(chain_id)["worktree"]["git_dir"])) / "index").read_bytes()
        with mock.patch.object(
            CLI,
            "MERGE_INTEGRATION_CONTROLS",
            CLI.MERGE_INTEGRATION_CONTROLS - {"conflict-continue-contract"},
        ), self.assertRaisesRegex(
            CLI.FrozenError,
            "merge integration control is unavailable: conflict-continue-contract",
        ):
            engine.recover(continue_rebase=True, paths=["src/app.py"])
        self.assertEqual(store.events_path(chain_id).read_bytes(), before_events)
        self.assertEqual(
            (Path(str(store.load(chain_id)["worktree"]["git_dir"])) / "index").read_bytes(),
            before_index,
        )
        self.assertEqual(
            self.git_at(self.origin, "rev-parse", "refs/heads/fixture-main"),
            remote_tip,
        )

    def test_continue_path_grammar_rejects_magic_duplicates_and_nul(self) -> None:
        bad_sets = (
            ["src/app.py", "src/app.py"],
            ["src/app.py\0evil"],
            ["/src/app.py"],
            ["../src/app.py"],
            [":(glob)src/*.py"],
            [":/src/app.py"],
        )
        for paths in bad_sets:
            with self.subTest(paths=paths), self.assertRaises(ValueError):
                CLI._normalize_merge_conflict_paths(paths)
        self.assertEqual(
            CLI._normalize_merge_conflict_paths(
                ["src/*.py", "src/\\app.py", "src/question?.py"]
            ),
            ("src/*.py", "src/\\app.py", "src/question?.py"),
        )

    def test_continue_stages_a_literal_conflict_filename_with_glob_bytes(self) -> None:
        relative = "src/question?.py"
        candidate_path = self.worktree / relative
        candidate_path.write_text("VALUE = 'candidate'\n", encoding="utf-8")
        self.git_at(self.worktree, "add", "--", relative)
        self.git_at(
            self.worktree,
            "commit",
            "--quiet",
            "-m",
            "candidate literal conflict path",
        )
        engine, store, authorized = self.authorize()
        writer = self.clone_remote_writer("literal-glob-path-writer")
        self.push_remote_change(writer, relative, "VALUE = 'remote'\n")
        with self.assertRaises(CLI.Refusal) as conflict:
            engine.finalize()
        self.assertEqual(conflict.exception.reason_code, CLI.V2ReasonCode.REBASE_CONFLICT)
        conflicted = store.load(str(authorized["chain_id"]))
        self.assertEqual(
            conflicted["integration"]["conflict"]["authorized_paths"],
            [relative],
        )
        candidate_path.write_text("VALUE = 'resolved'\n", encoding="utf-8")
        calls = []
        original = CLI.run_fenced_command

        def record_literal_add(lock, **kwargs):
            argv = list(kwargs.get("argv", ()))
            if "add" in argv:
                calls.append(argv)
            return original(lock, **kwargs)

        with mock.patch.object(CLI, "run_fenced_command", side_effect=record_literal_add):
            recovered = engine.recover(continue_rebase=True, paths=[relative])
        self.assertTrue(recovered.ok)
        self.assertEqual(
            calls,
            [["git", "--literal-pathspecs", "add", "--", relative]],
        )
        self.assertEqual(
            store.load(str(authorized["chain_id"]))["state"], "reviewing"
        )

    def test_timed_out_rebase_with_metadata_is_not_classified_as_conflict(self) -> None:
        engine, store, authorized = self.authorize()
        writer = self.clone_remote_writer("timed-out-rebase-writer")
        self.push_remote_change(writer, "src/app.py", "VALUE = 9000\n")
        original = CLI.run_fenced_command

        def timed_out_after_git_started(lock, **kwargs):
            if kwargs.get("operation") != "rebase":
                return original(lock, **kwargs)
            child = subprocess.run(
                kwargs["argv"],
                cwd=kwargs["cwd"],
                env=kwargs["env"],
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(child.returncode, 0)
            output = child.stdout + child.stderr
            result = CLI.FencedProcessResult(
                argv=list(kwargs["argv"]),
                returncode=child.returncode,
                duration_seconds=0.01,
                output=output,
                output_digest=CLI.sha256_bytes(output),
                timed_out=True,
                output_limit=False,
                launch_failed=False,
                group_survived=False,
                authorized=True,
                fence_digest="b" * 64,
                fence_inode=1,
            )
            kwargs["persist_result"](result)
            return result

        with mock.patch.object(
            CLI, "run_fenced_command", side_effect=timed_out_after_git_started
        ), self.assertRaises(CLI.Refusal) as caught:
            engine.finalize()
        current = store.load(str(authorized["chain_id"]))
        self.assertEqual(caught.exception.reason_code, CLI.V2ReasonCode.REBASE_FAILED)
        self.assertNotEqual(current["state"], "rebase_conflict")
        self.assertEqual(current["integration"]["condition"], "foreign-git-state")
        self.assertEqual(current["integration"]["remote_movement_count"], 0)

    def test_push_rejection_requires_one_exact_target_porcelain_row(self) -> None:
        def result(output: bytes) -> object:
            return CLI.FencedProcessResult(
                argv=["git", "push"],
                returncode=1,
                duration_seconds=0.1,
                output=output,
                output_digest=CLI.sha256_bytes(output),
                timed_out=False,
                output_limit=False,
                launch_failed=False,
                group_survived=False,
                authorized=True,
                fence_digest="1" * 64,
                fence_inode=1,
            )

        destination = "refs/heads/fixture-main"
        exact = (
            b"!\trefs/heads/feature:refs/heads/fixture-main\t"
            b"[rejected] (fetch first)\n"
        )
        self.assertEqual(
            CLI.MergeEngine._push_classification(result(exact), destination),
            "non-fast-forward",
        )
        for malformed in (
            b"error: [rejected] (fetch first)\n",
            exact + exact,
            b"!\trefs/heads/feature:refs/heads/other\t"
            b"[rejected] (non-fast-forward)\n",
            b"!\trefs/heads/feature:refs/heads/fixture-main\t"
            b"[rejected] (remote rejected)\n",
        ):
            with self.subTest(output=malformed):
                self.assertEqual(
                    CLI.MergeEngine._push_classification(
                        result(malformed), destination
                    ),
                    "known-failure",
                )

    def test_remote_only_successor_is_carried_then_pushed_in_a_new_epoch(self) -> None:
        engine, store, authorized, carried, remote_only_tip = (
            self.prepare_carried_ancestor()
        )
        original = CLI.run_fenced_command
        self.assertEqual(carried["state"], "authorized")
        self.assertEqual(
            self.events(store, str(authorized["chain_id"]))[-1]["event"],
            "generation_carried_forward",
        )

        before_retry = store.events_path(str(authorized["chain_id"])).read_bytes()
        with mock.patch.object(
            CLI,
            "MERGE_INTEGRATION_CONTROLS",
            CLI.MERGE_INTEGRATION_CONTROLS
            - {"successor-ancestry-observation"},
        ), self.assertRaisesRegex(
            CLI.FrozenError,
            "merge integration control is unavailable: successor-ancestry-observation",
        ):
            engine.finalize()
        self.assertEqual(
            store.events_path(str(authorized["chain_id"])).read_bytes(), before_retry
        )

        second_epoch_children = []

        def record_second_epoch(lock, **kwargs):
            second_epoch_children.append(
                (kwargs.get("operation"), list(kwargs.get("argv", ())))
            )
            return original(lock, **kwargs)

        with mock.patch.object(
            CLI, "run_fenced_command", side_effect=record_second_epoch
        ):
            finalized = engine.finalize()
        pushed = store.load(str(authorized["chain_id"]))
        self.assertTrue(finalized.ok)
        self.assertEqual(pushed["state"], "pushed")
        events = self.events(store, str(authorized["chain_id"]))
        fetch_result = next(
            event for event in reversed(events) if event["event"] == "fetch_result"
        )
        ancestry_events = [
            event
            for event in events
            if isinstance(
                event.get("payload", {})
                .get("delta", {})
                .get("integration", {})
                .get("intent"),
                dict,
            )
            and event["payload"]["delta"]["integration"]["intent"].get(
                "schema"
            )
            == "forge-epoch-ancestry-intent/1"
        ]
        self.assertEqual(len(ancestry_events), 2)
        ancestry_intent, ancestry_result = ancestry_events
        intent_record = ancestry_intent["payload"]["delta"]["integration"][
            "intent"
        ]
        raw_events = [
            event
            for event in events
            if event.get("digest")
            == intent_record["fetch_observation_event_digest"]
            and isinstance(
                event.get("payload", {})
                .get("delta", {})
                .get("integration", {})
                .get("intent"),
                dict,
            )
            and event["payload"]["delta"]["integration"]["intent"].get(
                "schema"
            )
            == CLI._EPOCH_FETCH_OBSERVATION_SCHEMA
        ]
        self.assertEqual(len(raw_events), 1)
        raw_event = raw_events[0]
        raw_record = raw_event["payload"]["delta"]["integration"]["intent"]
        result_record = ancestry_result["payload"]["delta"]["integration"][
            "intent"
        ]
        self.assertEqual(
            raw_record["fetch_intent_event_digest"], raw_event["previous_digest"]
        )
        self.assertEqual(
            intent_record["fetch_observation_event_digest"], raw_event["digest"]
        )
        self.assertEqual(
            result_record["intent_event_digest"], ancestry_intent["digest"]
        )
        self.assertEqual(fetch_result["previous_digest"], ancestry_result["digest"])
        plan = pushed["integration"]["epoch"]["gate_plan"]
        self.assertEqual(plan["seal_event_digest"], fetch_result["digest"])
        self.assertNotIn(
            plan["seal_event_digest"],
            {
                event["digest"]
                for event in events
                if event["event"] == "condition_recorded"
            },
        )
        self.assertIn(
            (
                "containment",
                CLI._remote_containment_argv(
                    carried,
                    remote_only_tip,
                    carried["candidate"]["candidate_head"],
                ),
            ),
            second_epoch_children,
        )
        self.assertFalse(
            any(operation == "rebase" for operation, _argv in second_epoch_children)
        )
        self.assertEqual(
            self.git_at(self.origin, "rev-parse", "refs/heads/fixture-main"),
            pushed["candidate"]["candidate_head"],
        )

    def test_carried_successor_recover_resumes_after_raw_fetch_without_refetch(
        self,
    ) -> None:
        engine, store, authorized, _carried, _remote_tip = (
            self.prepare_carried_ancestor()
        )

        def crash() -> None:
            with mock.patch.object(
                CLI.MergeEngine,
                "_complete_epoch_fetch_locked",
                side_effect=lambda *_args, **_kwargs: os.kill(
                    os.getpid(), signal.SIGKILL
                ),
            ):
                engine.finalize()

        self.assert_sigkill_crash(crash)
        chain_id = str(authorized["chain_id"])
        interrupted = store.load(chain_id)
        self.assertEqual(
            interrupted["integration"]["intent"]["schema"],
            CLI._EPOCH_FETCH_OBSERVATION_SCHEMA,
        )

        def authenticated_raw_fetch_digests() -> list[str]:
            digests = []
            for event in self.events(store, chain_id):
                intent = (
                    event.get("payload", {})
                    .get("delta", {})
                    .get("integration", {})
                    .get("intent")
                )
                if (
                    event.get("event") == "condition_recorded"
                    and isinstance(intent, dict)
                    and intent.get("schema")
                    == CLI._EPOCH_FETCH_OBSERVATION_SCHEMA
                    and intent.get("generation_digest")
                    == interrupted["candidate"]["generation_digest"]
                    and event.get("previous_digest")
                    == intent.get("fetch_intent_event_digest")
                ):
                    digests.append(str(event["digest"]))
            return digests

        before_raw_digests = authenticated_raw_fetch_digests()
        self.assertEqual(len(before_raw_digests), 1)
        original = CLI.run_fenced_command
        calls = []

        def record(lock, **kwargs):
            calls.append((kwargs.get("operation"), list(kwargs.get("argv", ()))))
            return original(lock, **kwargs)

        with mock.patch.object(CLI, "run_fenced_command", side_effect=record):
            recovered = engine.recover()
        self.assertTrue(recovered.ok)
        self.assertFalse(any(operation == "fetch" for operation, _argv in calls))
        self.assertEqual(store.load(chain_id)["state"], "pushed")
        self.assertEqual(authenticated_raw_fetch_digests(), before_raw_digests)

    def test_carried_successor_recover_resumes_exact_ancestry_intent(self) -> None:
        engine, store, authorized, carried, remote_tip = (
            self.prepare_carried_ancestor()
        )

        class RawFetchBoundary(RuntimeError):
            pass

        with mock.patch.object(
            CLI.MergeEngine,
            "_complete_epoch_fetch_locked",
            side_effect=RawFetchBoundary("park after the durable raw fetch"),
        ), self.assertRaisesRegex(RawFetchBoundary, "durable raw fetch"):
            engine.finalize()
        chain_id = str(authorized["chain_id"])
        self.stage_carried_successor_candidate_observation(
            engine, store, chain_id
        )
        ancestry_argv = CLI._remote_containment_argv(
            carried,
            remote_tip,
            carried["candidate"]["candidate_head"],
        )
        original = CLI.run_fenced_command

        def kill_before_ancestry(lock, **kwargs):
            if list(kwargs.get("argv", ())) == ancestry_argv:
                os.kill(os.getpid(), signal.SIGKILL)
            return original(lock, **kwargs)

        def crash() -> None:
            with mock.patch.object(
                CLI, "run_fenced_command", side_effect=kill_before_ancestry
            ):
                engine.recover()

        self.assert_sigkill_crash(crash)
        interrupted = store.load(chain_id)
        intent = interrupted["integration"]["intent"]
        self.assertEqual(intent["schema"], "forge-epoch-ancestry-intent/1")
        self.assertEqual(intent["phase"], "intent")

        before = store.events_path(chain_id).read_bytes()
        with mock.patch.object(
            CLI,
            "_REQUIRED_MERGE_INTEGRATION_CONTROLS",
            CLI._REQUIRED_MERGE_INTEGRATION_CONTROLS
            - {"successor-ancestry-observation"},
        ), mock.patch.object(
            CLI,
            "MERGE_INTEGRATION_CONTROLS",
            CLI.MERGE_INTEGRATION_CONTROLS
            - {"successor-ancestry-observation"},
        ), self.assertRaisesRegex(
            CLI.FrozenError,
            "merge integration control is unavailable: successor-ancestry-observation",
        ):
            engine.recover()
        self.assertEqual(store.events_path(chain_id).read_bytes(), before)

        calls = []

        def record(lock, **kwargs):
            calls.append((kwargs.get("operation"), list(kwargs.get("argv", ()))))
            return original(lock, **kwargs)

        with mock.patch.object(CLI, "run_fenced_command", side_effect=record):
            recovered = engine.recover()
        self.assertTrue(recovered.ok)
        self.assertFalse(any(operation == "fetch" for operation, _argv in calls))
        self.assertEqual(
            sum(argv == ancestry_argv for _operation, argv in calls),
            1,
        )
        ancestry_intents = [
            event
            for event in self.events(store, chain_id)
            if event["event"] == "condition_recorded"
            and isinstance(
                event.get("payload", {})
                .get("delta", {})
                .get("integration", {})
                .get("intent"),
                dict,
            )
            and event["payload"]["delta"]["integration"]["intent"].get("schema")
            == "forge-epoch-ancestry-intent/1"
            and event["payload"]["delta"]["integration"]["intent"].get(
                "phase"
            )
            == "intent"
        ]
        self.assertEqual(len(ancestry_intents), 1)

    def test_carried_successor_recover_consumes_durable_ancestry_result(self) -> None:
        engine, store, authorized, carried, remote_tip = (
            self.prepare_carried_ancestor()
        )

        class RawFetchBoundary(RuntimeError):
            pass

        with mock.patch.object(
            CLI.MergeEngine,
            "_complete_epoch_fetch_locked",
            side_effect=RawFetchBoundary("park after the durable raw fetch"),
        ), self.assertRaisesRegex(RawFetchBoundary, "durable raw fetch"):
            engine.finalize()
        chain_id = str(authorized["chain_id"])
        self.stage_carried_successor_candidate_observation(
            engine, store, chain_id
        )
        ancestry_argv = CLI._remote_containment_argv(
            carried,
            remote_tip,
            carried["candidate"]["candidate_head"],
        )
        original_ancestry = CLI.MergeEngine._run_carried_successor_ancestry

        def kill_after_result(self, *args, **kwargs):
            result = original_ancestry(self, *args, **kwargs)
            os.kill(os.getpid(), signal.SIGKILL)
            return result

        def crash() -> None:
            with mock.patch.object(
                CLI.MergeEngine,
                "_run_carried_successor_ancestry",
                autospec=True,
                side_effect=kill_after_result,
            ):
                engine.recover()

        self.assert_sigkill_crash(crash)
        interrupted = store.load(chain_id)
        intent = interrupted["integration"]["intent"]
        self.assertEqual(intent["schema"], "forge-epoch-ancestry-intent/1")
        self.assertEqual(intent["phase"], "result")
        original = CLI.run_fenced_command
        calls = []

        def record(lock, **kwargs):
            calls.append((kwargs.get("operation"), list(kwargs.get("argv", ()))))
            return original(lock, **kwargs)

        with mock.patch.object(CLI, "run_fenced_command", side_effect=record):
            recovered = engine.recover()
        self.assertTrue(recovered.ok)
        self.assertFalse(any(operation == "fetch" for operation, _argv in calls))
        self.assertNotIn(ancestry_argv, [argv for _operation, argv in calls])
        completed = store.load(chain_id)
        events = self.events(store, chain_id)
        self.assertEqual(
            sum(
                1
                for event in events
                if isinstance(
                    event.get("payload", {})
                    .get("delta", {})
                    .get("integration", {})
                    .get("intent"),
                    dict,
                )
                and event["payload"]["delta"]["integration"]["intent"].get(
                    "schema"
                )
                == "forge-epoch-ancestry-intent/1"
                and event["payload"]["delta"]["integration"]["intent"].get(
                    "phase"
                )
                == "result"
            ),
            1,
        )
        fetch_result = next(
            event for event in reversed(events) if event["event"] == "fetch_result"
        )
        self.assertEqual(
            completed["integration"]["epoch"]["gate_plan"][
                "seal_event_digest"
            ],
            fetch_result["digest"],
        )

    def test_carried_successor_replay_rejects_each_upstream_digest_mutant(
        self,
    ) -> None:
        engine, store, authorized, _carried, _remote_tip = (
            self.prepare_carried_ancestor()
        )
        engine.finalize()
        chain_id = str(authorized["chain_id"])
        events = self.events(store, chain_id)

        def recorded_intent(event):
            return event.get("payload", {}).get("delta", {}).get(
                "integration", {}
            ).get("intent")

        raw_index = next(
            index
            for index, event in reversed(tuple(enumerate(events)))
            if isinstance(recorded_intent(event), dict)
            and recorded_intent(event).get("schema")
            == CLI._EPOCH_FETCH_OBSERVATION_SCHEMA
        )
        ancestry_intent_index = next(
            index
            for index, event in enumerate(events)
            if isinstance(recorded_intent(event), dict)
            and recorded_intent(event).get("schema")
            == "forge-epoch-ancestry-intent/1"
            and recorded_intent(event).get("phase") == "intent"
        )
        ancestry_result_index = next(
            index
            for index, event in enumerate(events)
            if isinstance(recorded_intent(event), dict)
            and recorded_intent(event).get("schema")
            == "forge-epoch-ancestry-intent/1"
            and recorded_intent(event).get("phase") == "result"
        )
        mutations = (
            (raw_index, "fetch_intent_event_digest"),
            (ancestry_intent_index, "candidate_observation_digest"),
            (ancestry_result_index, "intent_event_digest"),
        )
        for index, field in mutations:
            with self.subTest(field=field):
                mutated = copy.deepcopy(events)
                recorded_intent(mutated[index])[field] = "f" * 64
                self.reseal_event(mutated[index])
                with self.assertRaises(CLI.FrozenError):
                    CLI._replay_merge_event_bytes(
                        chain_id, self.replay_prefix(mutated, index)
                    )

    def test_divergent_present_tip_materializes_remote_only_successor(self) -> None:
        engine, store, authorized = self.authorize()
        writer = self.clone_remote_writer("divergent-carry-writer")
        original = CLI.run_fenced_command
        moved = False
        remote_tip = None
        operations: list[str] = []

        def move_during_final_observation(lock, **kwargs):
            nonlocal moved, remote_tip
            operation = str(kwargs.get("operation"))
            operations.append(operation)
            if kwargs.get("operation") == "remote-observation" and not moved:
                self.assertIn("fetch", operations[:-1])
                self.assertNotIn("push", operations[:-1])
                remote_tip = self.push_remote_change(
                    writer, "remote-only.txt", "ordinary present-tip movement\n"
                )
                moved = True
            return original(lock, **kwargs)

        before_steps = json.loads(json.dumps(authorized["steps"]))
        with mock.patch.object(
            CLI, "run_fenced_command", side_effect=move_during_final_observation
        ):
            parked = engine.finalize()
        carried = store.load(str(authorized["chain_id"]))
        self.assertTrue(parked.ok)
        self.assertIsNotNone(remote_tip)
        self.assertIn("fetch", operations)
        self.assertIn("remote-observation", operations)
        self.assertLess(
            operations.index("fetch"), operations.index("remote-observation")
        )
        self.assertNotIn("push", operations)
        self.assertNotEqual(remote_tip, authorized["candidate"]["remote_tip"])
        self.assertNotEqual(
            CLI.Repository(self.worktree)
            .git(
                [
                    "merge-base",
                    "--is-ancestor",
                    str(remote_tip),
                    authorized["candidate"]["candidate_head"],
                ],
                check=False,
            )
            .returncode,
            0,
        )
        self.assertEqual(carried["candidate"]["generation"], 2)
        self.assertEqual(carried["candidate"]["remote_tip"], remote_tip)
        self.assertEqual(carried["state"], "authorized")
        self.assertEqual(carried["integration"]["condition"], "remote-moved")
        self.assertEqual(carried["integration"]["remote_movement_count"], 1)
        self.assertEqual(carried["steps"], before_steps)
        event = self.events(store, str(authorized["chain_id"]))[-1]
        self.assertEqual(event["event"], "generation_carried_forward")
        self.assertEqual(
            event["payload"]["prior_generation_digest"],
            authorized["candidate"]["generation_digest"],
        )
        self.assertEqual(
            event["payload"]["successor_generation_digest"],
            carried["candidate"]["generation_digest"],
        )

        second_epoch_children = []

        def record_second_epoch(lock, **kwargs):
            second_epoch_children.append(
                (kwargs.get("operation"), list(kwargs.get("argv", ())))
            )
            return original(lock, **kwargs)

        with mock.patch.object(
            CLI, "run_fenced_command", side_effect=record_second_epoch
        ):
            integrated = engine.finalize()
        reviewing = store.load(str(authorized["chain_id"]))
        self.assertTrue(integrated.ok)
        self.assertIn(
            (
                "containment",
                CLI._remote_containment_argv(
                    carried,
                    str(remote_tip),
                    carried["candidate"]["candidate_head"],
                ),
            ),
            second_epoch_children,
        )
        self.assertTrue(
            any(operation == "rebase" for operation, _argv in second_epoch_children)
        )
        self.assertEqual(reviewing["state"], "reviewing")
        self.assertEqual(reviewing["candidate"]["generation"], 3)
        self.assertEqual(
            CLI.Repository(self.worktree)
            .git(
                [
                    "merge-base",
                    "--is-ancestor",
                    str(remote_tip),
                    reviewing["candidate"]["candidate_head"],
                ],
                check=False,
            )
            .returncode,
            0,
        )
        self.assertEqual(reviewing["approval"], {})
        self.assertEqual(reviewing["authorization"], {})
        self.assertEqual(reviewing["integration"]["remote_movement_count"], 0)
        chain_id = str(authorized["chain_id"])
        events = self.events(store, chain_id)
        rebase_result = next(
            event for event in reversed(events) if event["event"] == "rebase_result"
        )
        replay = CLI._replay_merge_event_bytes(
            chain_id, store.events_path(chain_id).read_bytes()
        )
        rebase_projection = next(
            current
            for event, _prior, current, _records, _source in replay.entries
            if event["digest"] == rebase_result["digest"]
        )
        self.assertEqual(
            rebase_projection["integration"]["epoch"]["gate_plan"][
                "seal_event_digest"
            ],
            rebase_result["digest"],
        )
        carried_fetch_projection = next(
            current
            for event, _prior, current, _records, _source in reversed(
                replay.entries
            )
            if event["event"] == "fetch_result"
            and current.get("candidate", {}).get("generation") == 2
        )
        self.assertEqual(
            carried_fetch_projection["integration"]["epoch"]["gate_plan"][
                "status"
            ],
            "unsealed",
        )

    def test_eighth_real_remote_defeat_requires_exact_churn_acknowledgement(
        self,
    ) -> None:
        destination = "refs/heads/fixture-main"
        self.git_at(
            self.worktree,
            "push",
            "--quiet",
            "origin",
            f"{self.candidate_head}:{destination}",
        )
        initial_remote = self.candidate_head
        remote_tips: list[str] = []
        for _index in range(8):
            _prior, moved = self.move_head_same_tree(self.worktree)
            remote_tips.append(moved)
        final_path = self.worktree / "src" / "after-churn.py"
        final_path.write_text("AFTER_CHURN = True\n", encoding="utf-8")
        self.git_at(self.worktree, "add", "src/after-churn.py")
        self.git_at(
            self.worktree,
            "commit",
            "--quiet",
            "-m",
            "candidate after remote churn ancestors",
        )
        self.candidate_head = self.git_at(self.worktree, "rev-parse", "HEAD")
        self.git_at(
            self.worktree,
            "push",
            "--quiet",
            "origin",
            f"{self.candidate_head}:refs/heads/churn-fixture-objects",
        )
        engine, store, authorized = self.authorize(remote_tip=initial_remote)
        chain_id = str(authorized["chain_id"])
        original = CLI.run_fenced_command
        operations: list[str] = []
        gate_calls = 0
        synthetic_children = 0
        candidate_outputs: dict[str, bytes] = {}
        candidate_commands: dict[tuple[str, ...], tuple[str, str]] = {}
        for observed_tip in (initial_remote, *remote_tips):
            for classify in (False, True):
                specs = CLI._merge_candidate_observation_step_specs(
                    authorized,
                    remote_tip=observed_tip,
                    expected_head=self.candidate_head,
                    classify=classify,
                    declared_tier=None,
                )
                self.assertIsNotNone(specs)
                for step, _cwd, argv in specs or ():
                    candidate_commands[tuple(argv)] = (step, observed_tip)

        def synthetic_result(lock, kwargs, output: bytes, ordinal: int):
            lock.assert_held()
            self.assertTrue(kwargs["intent_validator"]())
            result = CLI.FencedProcessResult(
                argv=list(kwargs["argv"]),
                returncode=0,
                duration_seconds=0.0,
                output=output,
                output_digest=CLI.sha256_bytes(output),
                timed_out=False,
                output_limit=False,
                launch_failed=False,
                group_survived=False,
                authorized=True,
                fence_digest=CLI.sha256_bytes(
                    CLI.canonical_bytes(
                        {
                            "operation": kwargs["operation"],
                            "argv": kwargs["argv"],
                            "ordinal": ordinal,
                        }
                    )
                ),
                fence_inode=ordinal,
            )
            kwargs["persist_result"](result)
            return result

        def candidate_or_gate(lock, **kwargs):
            nonlocal gate_calls, synthetic_children
            operation = str(kwargs.get("operation"))
            if operation == "gate":
                gate_calls += 1
                return synthetic_result(
                    lock, kwargs, b"fixture churn gate pass\n", gate_calls
                )
            candidate = candidate_commands.get(tuple(kwargs.get("argv", ())))
            if operation != "containment" or candidate is None:
                return original(lock, **kwargs)
            step, observed_tip = candidate
            if step == "tip":
                output = f"{observed_tip}\n".encode("ascii")
            elif step in candidate_outputs:
                output = candidate_outputs[step]
            else:
                result = original(lock, **kwargs)
                self.assertEqual(result.returncode, 0)
                self.assertTrue(result.authorized)
                candidate_outputs[step] = result.output
                return result
            synthetic_children += 1
            return synthetic_result(
                lock,
                kwargs,
                output,
                10_000 + synthetic_children,
            )

        original_candidate_observation = engine._run_candidate_observation_locked
        seed_observations: dict[
            tuple[bool, str | None], dict[str, object]
        ] = {}
        durable_source_digests: set[str] = set()
        synthesized_observations = 0

        def reuse_candidate_child_results(
            state,
            lock,
            lease,
            *,
            verb,
            remote_tip,
            expected_head,
            classify,
            declared_tier=None,
        ):
            nonlocal synthesized_observations
            seed_key = (classify, declared_tier)
            source_intent = state.get("integration", {}).get("intent")
            source_digest = CLI.sha256_bytes(CLI.canonical_bytes(source_intent))
            requires_fetch_binding = bool(
                isinstance(source_intent, dict)
                and source_intent.get("schema")
                == "forge-epoch-fetch-observation/1"
                and source_digest not in durable_source_digests
            )
            if seed_key not in seed_observations or requires_fetch_binding:
                current, evidence = original_candidate_observation(
                    state,
                    lock,
                    lease,
                    verb=verb,
                    remote_tip=remote_tip,
                    expected_head=expected_head,
                    classify=classify,
                    declared_tier=declared_tier,
                )
                seed_observations[seed_key] = copy.deepcopy(evidence)
                durable_source_digests.add(source_digest)
                return current, evidence
            specs = CLI._merge_candidate_observation_step_specs(
                state,
                remote_tip=remote_tip,
                expected_head=expected_head,
                classify=classify,
                declared_tier=declared_tier,
            )
            binding = CLI._merge_candidate_observation_binding(
                state,
                source_intent,
                verb=verb,
                remote_tip=remote_tip,
                expected_head=expected_head,
                classify=classify,
                declared_tier=declared_tier,
            )
            retained_steps = seed_observations[seed_key].get("steps")
            self.assertIsNotNone(specs)
            self.assertIsNotNone(binding)
            self.assertIsInstance(retained_steps, list)
            self.assertEqual(len(retained_steps), len(specs or ()))
            rebound_steps = []
            for prior, (step, cwd, argv) in zip(retained_steps, specs or ()):
                record = copy.deepcopy(prior)
                record.update(
                    {
                        "generation_digest": state["candidate"][
                            "generation_digest"
                        ],
                        "source_intent": copy.deepcopy(source_intent),
                        "verb": verb,
                        "remote_tip": remote_tip,
                        "expected_head": expected_head,
                        "classify": classify,
                        "declared_tier": declared_tier,
                        "observation_binding": binding,
                        "step": step,
                        "cwd": str(cwd),
                        "argv": list(argv),
                    }
                )
                if step == "tip":
                    output = f"{remote_tip}\n".encode("ascii")
                    child = copy.deepcopy(record["child_result"])
                    child.update(
                        {
                            "output_b64": base64.b64encode(output).decode("ascii"),
                            "output_digest": CLI.sha256_bytes(output),
                            "stored_output_digest": CLI.sha256_bytes(output),
                        }
                    )
                    record["child_result"] = child
                rebound_steps.append(record)
            rebound = CLI._merge_candidate_observation_evidence(
                state, rebound_steps
            )
            self.assertIsNotNone(rebound)
            self.assertTrue(
                CLI._merge_candidate_observation_evidence_valid(state, rebound)
            )
            synthesized_observations += 1
            return state, rebound

        for index, remote_tip in enumerate(remote_tips, start=1):
            advanced = False

            def advance_before_observation(lock, **kwargs):
                nonlocal advanced
                operation = str(kwargs.get("operation"))
                operations.append(operation)
                if operation == "remote-observation" and not advanced:
                    self.assertNotIn("push", operations)
                    self.git_at(
                        self.origin, "update-ref", destination, remote_tip
                    )
                    advanced = True
                return candidate_or_gate(lock, **kwargs)

            with mock.patch.object(
                CLI,
                "run_fenced_command",
                side_effect=advance_before_observation,
            ), mock.patch.object(
                engine,
                "_run_candidate_observation_locked",
                side_effect=reuse_candidate_child_results,
            ):
                if index < 8:
                    outcome = engine.finalize()
                    self.assertTrue(outcome.ok)
                else:
                    with self.assertRaises(CLI.Refusal) as caught:
                        engine.finalize()
                    self.assertEqual(
                        caught.exception.reason_code,
                        CLI.V2ReasonCode.REMOTE_CHURN,
                    )
                    self.assertEqual(
                        caught.exception.message,
                        "forge: merge finalize refused — remote churn exhausted the bounded retry counter",
                    )

            current = store.load(chain_id)
            self.assertTrue(advanced)
            self.assertEqual(current["candidate"]["generation"], index + 1)
            self.assertEqual(
                current["candidate"]["candidate_head"], self.candidate_head
            )
            self.assertEqual(current["candidate"]["remote_tip"], remote_tip)
            self.assertEqual(
                current["integration"]["remote_movement_count"], index
            )
            self.assertEqual(
                current["integration"]["condition"],
                "remote-churn" if index == 8 else "remote-moved",
            )
            self.assertEqual(
                current["state"],
                "awaiting_approval" if index == 8 else "authorized",
            )
            self.assertEqual(
                sum(
                    event["event"] == "generation_carried_forward"
                    for event in self.events(store, chain_id)
                ),
                index,
            )
            self.assertNotIn("push", operations)
            self.assertFalse(
                any(
                    event["event"] == "push_intent"
                    for event in self.events(store, chain_id)
                )
            )

        churned = store.load(chain_id)
        self.assertGreater(synthetic_children, 0)
        self.assertGreater(synthesized_observations, 0)
        self.assertEqual(operations.count("remote-observation"), 8)
        self.assertEqual(
            self.git_at(self.origin, "rev-parse", destination), remote_tips[-1]
        )
        self.assertNotEqual(remote_tips[-1], self.candidate_head)
        before_refusal = store.events_path(chain_id).read_bytes()
        with self.assertRaises(CLI.Refusal) as stale:
            engine.approve(initial_remote)
        self.assertEqual(stale.exception.reason_code, CLI.V2ReasonCode.CANDIDATE_STALE)
        self.assertEqual(store.events_path(chain_id).read_bytes(), before_refusal)

        acknowledged = engine.approve(str(churned["candidate"]["candidate_head"]))
        rearmed = store.load(chain_id)
        self.assertTrue(acknowledged.ok)
        self.assertEqual(rearmed["state"], "authorized")
        self.assertEqual(rearmed["integration"]["condition"], "none")
        self.assertEqual(rearmed["integration"]["primary_condition"], "none")
        self.assertEqual(rearmed["integration"]["remote_movement_count"], 0)
        self.assertEqual(rearmed["approval"]["purpose"], "remote-churn")
        events_after_ack = self.events(store, chain_id)
        self.assertEqual(events_after_ack[-1]["event"], "approval_recorded")
        approval_event = events_after_ack[-1]["payload"]["delta"]["approval"]
        self.assertEqual(
            approval_event["purpose"],
            "remote-churn",
        )
        self.assertEqual(
            approval_event["generation_digest"],
            rearmed["candidate"]["generation_digest"],
        )

        class RearmedPushBoundary(RuntimeError):
            pass

        epoch_count = sum(
            event["event"] == "epoch_intent" for event in events_after_ack
        )
        push_intent_count = sum(
            event["event"] == "push_intent" for event in events_after_ack
        )
        push_boundaries = 0

        def stop_rearmed_epoch_at_push(lock, **kwargs):
            nonlocal push_boundaries
            operation = str(kwargs.get("operation"))
            operations.append(operation)
            if operation == "push":
                push_boundaries += 1
                raise RearmedPushBoundary("re-armed epoch reached push")
            return candidate_or_gate(lock, **kwargs)

        with mock.patch.object(
            CLI,
            "run_fenced_command",
            side_effect=stop_rearmed_epoch_at_push,
        ), mock.patch.object(
            engine,
            "_run_candidate_observation_locked",
            side_effect=reuse_candidate_child_results,
        ), self.assertRaisesRegex(RearmedPushBoundary, "re-armed epoch reached push"):
            engine.finalize()

        rearmed_attempt = store.load(chain_id)
        final_events = self.events(store, chain_id)
        self.assertEqual(push_boundaries, 1)
        self.assertEqual(rearmed_attempt["state"], "pushing")
        self.assertIsNone(rearmed_attempt["integration"]["push"]["result"])
        self.assertEqual(
            rearmed_attempt["integration"]["push"]["attempted_heads"],
            [self.candidate_head],
        )
        self.assertEqual(
            sum(event["event"] == "epoch_intent" for event in final_events),
            epoch_count + 1,
        )
        self.assertEqual(
            sum(event["event"] == "push_intent" for event in final_events),
            push_intent_count + 1,
        )
        self.assertEqual(final_events[-1]["event"], "push_intent")
        self.assertEqual(
            self.git_at(self.origin, "rev-parse", destination), remote_tips[-1]
        )

    def test_unbound_replay_cache_matches_original_authenticated_boundary(
        self,
    ) -> None:
        started = CLI.MergeEngine(self.context()).start_chain(
            str(self.worktree), remote_tip=self.base
        )
        chain_id = str(started.chain_id)
        raw_events = self.context().store.events_path(chain_id).read_bytes()
        hits_before = self._replay_cache_observations["hits"]
        cached = CLI._replay_merge_event_bytes(chain_id, raw_events)
        self.assertEqual(
            self._replay_cache_observations["hits"], hits_before + 1
        )
        original = self._original_merge_replay(chain_id, raw_events)
        self.assertEqual(cached.state, original.state)
        self.assertEqual(cached.events, original.events)
        self.assertEqual(cached.entries, original.entries)
        self.assertEqual(cached.prefix_state_bytes, original.prefix_state_bytes)
        self.assertEqual(cached.context, original.context)
        self.assertEqual(cached.tail_sequence, original.tail_sequence)
        self.assertEqual(cached.tail_digest, original.tail_digest)
        self.assertEqual(cached.raw_events, original.raw_events)
        self.assertEqual(cached.raw_events, raw_events)

    def test_two_chain_ids_contend_on_the_same_common_lock(self) -> None:
        first_engine, first_store, first_authorized = self.authorize()
        first_chain_id = str(first_authorized["chain_id"])
        second_worktree = (self.temp_root / "candidate-two").resolve()
        self.git("branch", "feature-two", self.base)
        self.git("worktree", "add", "--quiet", str(second_worktree), "feature-two")
        second_path = second_worktree / "src" / "second.py"
        second_path.write_text("SECOND = True\n", encoding="utf-8")
        self.git_at(second_worktree, "add", "src/second.py")
        self.git_at(
            second_worktree,
            "commit",
            "--quiet",
            "-m",
            "second candidate",
        )
        second_started = CLI.MergeEngine(self.context()).start_chain(
            str(second_worktree), remote_tip=self.base
        )
        second_chain_id = str(second_started.chain_id)
        second_engine = CLI.MergeEngine(self.context(chain_id=second_chain_id))
        with mock.patch.object(
            RUNTIME, "run_bounded", side_effect=self.passing_process
        ):
            second_verified = second_engine.verify()
        self.assertTrue(second_verified.ok)
        second_engine.review_request()
        second_requested = second_engine.store.load(second_chain_id)
        second_verdict = self.write_verdict(
            f"{second_chain_id}-pass.txt",
            "PASS",
            second_requested["review"]["request"],
        )
        second_attached = second_engine.review_attach(str(second_verdict))
        self.assertEqual(second_attached.state, "authorized")

        common = CLI.Repository(self.repo).git_common_dir()
        remote_before = self.git_at(
            self.origin, "rev-parse", "refs/heads/fixture-main"
        )
        first_acquired = threading.Event()
        second_waiting = threading.Event()
        order: list[str] = []
        order_lock = threading.Lock()
        first_result: list[object | None] = [None]
        original_acquire = CLI.acquire_common_lock
        second_clock = _LogicalClock()

        class FirstFinalizeBoundary(RuntimeError):
            pass

        def record_order(value: str) -> None:
            with order_lock:
                order.append(value)

        def second_poll(seconds: float) -> None:
            if not second_waiting.is_set():
                record_order("second-waiting")
                second_waiting.set()
            bounded = min(max(0.0, seconds), 0.001)
            second_clock.value += bounded
            time.sleep(bounded)

        def synchronized_acquire(*args, **kwargs):
            chain_id = str(kwargs.get("chain_id"))
            if chain_id == second_chain_id:
                kwargs["clock"] = second_clock
                kwargs["sleeper"] = second_poll
            acquired = original_acquire(*args, **kwargs)
            if chain_id == first_chain_id:
                record_order("first-acquired")
                first_acquired.set()
                if not second_waiting.wait(1):
                    acquired.release()
                    raise AssertionError("second merge never observed contention")
            elif chain_id == second_chain_id:
                record_order("second-acquired")
            return acquired

        def first_contender() -> None:
            try:
                first_result[0] = first_engine.finalize()
            except BaseException as exc:
                first_result[0] = exc
            finally:
                first_acquired.set()

        first_thread = threading.Thread(
            target=first_contender, name="merge-finalize-first", daemon=True
        )
        with mock.patch.object(
            CLI, "acquire_common_lock", new=synchronized_acquire
        ), mock.patch.object(
            first_engine,
            "_run_candidate_observation_locked",
            side_effect=FirstFinalizeBoundary(
                "first merge released after proving engine-level contention"
            ),
        ):
            first_thread.start()
            self.assertTrue(
                first_acquired.wait(self._THREAD_JOIN_SECONDS),
                "first merge never acquired the common lock",
            )
            second_result = second_engine.finalize()
            first_thread.join(self._THREAD_JOIN_SECONDS)

        self.assertFalse(first_thread.is_alive(), "first merge did not finish")
        self.assertIsInstance(first_result[0], FirstFinalizeBoundary)
        self.assertTrue(second_result.ok)
        self.assertTrue(second_waiting.is_set())
        self.assertEqual(
            order,
            [
                "first-acquired",
                "second-waiting",
                "second-acquired",
            ],
        )
        self.assertEqual(CLI.inspect_common_lock(common).topology, "free")
        first_terminal = first_store.load(first_chain_id)
        second_terminal = second_engine.store.load(second_chain_id)
        self.assertEqual(first_terminal, first_authorized)
        self.assertEqual(second_terminal["state"], "pushed")
        self.assertEqual(second_terminal["candidate"]["generation"], 1)
        self.assertEqual(second_terminal["integration"]["condition"], "none")
        self.assertEqual(
            second_terminal["candidate"]["candidate_head"],
            second_requested["candidate"]["candidate_head"],
        )
        self.assertEqual(
            self.git_at(self.origin, "rev-parse", "refs/heads/fixture-main"),
            second_terminal["candidate"]["candidate_head"],
        )
        self.assertNotEqual(
            self.git_at(self.origin, "rev-parse", "refs/heads/fixture-main"),
            remote_before,
        )
        first_names = [
            event["event"] for event in self.events(first_store, first_chain_id)
        ]
        second_names = [
            event["event"]
            for event in self.events(second_engine.store, second_chain_id)
        ]
        self.assertEqual(first_names.count("push_intent"), 0)
        self.assertEqual(second_names.count("generation_carried_forward"), 0)
        self.assertEqual(second_names.count("rebase_intent"), 0)
        self.assertEqual(second_names.count("push_intent"), 1)

    def test_merge_contention_exhausts_one_injected_300_second_budget(self) -> None:
        engine, store, authorized = self.authorize()
        second_worktree = (self.temp_root / "budget-holder").resolve()
        self.git("branch", "budget-holder", self.base)
        self.git(
            "worktree", "add", "--quiet", str(second_worktree), "budget-holder"
        )
        holder_chain = CLI.MergeEngine(self.context()).start_chain(
            str(second_worktree), remote_tip=self.base
        )
        common = CLI.Repository(self.repo).git_common_dir()
        state_before = store.state_path(str(authorized["chain_id"])).read_bytes()
        events_before = store.events_path(str(authorized["chain_id"])).read_bytes()
        remote_before = self.git_at(
            self.origin, "rev-parse", "refs/heads/fixture-main"
        )
        acquire = self._original_common_lock
        holder = acquire(
            common,
            owner_kind="merge",
            chain_id=str(holder_chain.chain_id),
            operation="finalize",
            timeout=1,
            use_flock=False,
            no_transaction_record=True,
        )
        clock = _LogicalClock()
        requested_timeouts: list[float] = []
        sleeps: list[float] = []

        def exhaust_budget(seconds: float) -> None:
            sleeps.append(seconds)
            clock.value = 300.0

        def acquire_with_injected_budget(*args, **kwargs):
            requested_timeouts.append(float(kwargs.get("timeout", 300.0)))
            kwargs.update(
                timeout=300.0,
                use_flock=False,
                clock=clock,
                sleeper=exhaust_budget,
            )
            return acquire(*args, **kwargs)

        try:
            with mock.patch.object(
                CLI,
                "acquire_common_lock",
                side_effect=acquire_with_injected_budget,
            ), self.assertRaises(CLI.CommonLockUnavailable) as caught:
                engine.finalize()
        finally:
            holder.release()

        self.assertEqual(
            caught.exception.reason_code,
            CLI.V2ReasonCode.REBASE_LOCK_UNAVAILABLE,
        )
        self.assertEqual(caught.exception.message, "forge: common rebase lock unavailable")
        self.assertEqual(requested_timeouts, [300.0])
        self.assertEqual(clock.value, 300.0)
        self.assertEqual(len(sleeps), 1)
        self.assertGreater(sleeps[0], 0.0)
        self.assertEqual(
            store.state_path(str(authorized["chain_id"])).read_bytes(), state_before
        )
        self.assertEqual(
            store.events_path(str(authorized["chain_id"])).read_bytes(), events_before
        )
        self.assertEqual(
            self.git_at(self.origin, "rev-parse", "refs/heads/fixture-main"),
            remote_before,
        )

    def test_late_gate_two_exhausts_its_own_fresh_publication_budget(self) -> None:
        engine, store, authorized = self.authorize()
        writer = self.clone_remote_writer("late-gate-two-writer")
        remote_tip = self.push_remote_change(
            writer, "remote.txt", "force a late Gate 2 epoch\n"
        )
        chain_id = str(authorized["chain_id"])
        common = CLI.Repository(self.repo).git_common_dir()
        clock = _LogicalClock()
        acquired_locks: list[object] = []
        acquisition_starts: list[float] = []
        publication_attempts = 0
        stopped_children = 0
        target_active = False
        target_start: float | None = None
        target_state_bytes: bytes | None = None
        target_event_bytes: bytes | None = None
        ack_deadlines: list[float] = []
        publication_sleeps: list[float] = []
        gate_one_completed = 0
        real_fenced = CLI.run_fenced_command
        real_spawn = CLI._spawn_blocked_fence_child
        real_publish = CLI._publish_fence
        real_stop = CLI._stop_unstarted_child

        def publication_clock_sleep(seconds: float) -> None:
            if not target_active or target_start is None:
                clock.sleep(seconds)
                return
            publication_sleeps.append(seconds)
            if publication_attempts == 1:
                clock.value = target_start + 299.0
            else:
                clock.value = target_start + 300.0

        def acquire_with_one_clock(*args, **kwargs):
            acquisition_starts.append(clock.value)
            kwargs.update(
                timeout=CLI.COMMON_LOCK_TIMEOUT_SECONDS,
                use_flock=False,
                clock=clock,
                sleeper=publication_clock_sleep,
            )
            acquired = self._original_common_lock(*args, **kwargs)
            acquired_locks.append(acquired)
            return acquired

        def is_target_gate(argv: list[str]) -> bool:
            return any("stack:python" in argument for argument in argv)

        def run_real_until_target(lock, **kwargs):
            nonlocal gate_one_completed, target_active, target_start
            nonlocal target_state_bytes, target_event_bytes
            argv = list(kwargs.get("argv", ()))
            if kwargs.get("operation") == "gate" and is_target_gate(argv):
                target_start = clock.value
                target_state_bytes = store.state_path(chain_id).read_bytes()
                target_event_bytes = store.events_path(chain_id).read_bytes()
                target_active = True
                try:
                    return real_fenced(lock, **kwargs)
                finally:
                    target_active = False
            result = real_fenced(lock, **kwargs)
            if kwargs.get("operation") == "gate" and any(
                "gate-1" in argument for argument in argv
            ):
                gate_one_completed += 1
                clock.value += 400.0
            return result

        def spawn_target_child(*args, **kwargs):
            if not target_active:
                return real_spawn(*args, **kwargs)
            ack_deadlines.append(float(kwargs["deadline"]))
            ordinal = len(ack_deadlines)
            return CLI._BlockedFenceChild(
                pid=70_000 + ordinal,
                pgid=70_000 + ordinal,
                start_descriptor=-1,
                output_descriptor=-1,
                exec_error_descriptor=-1,
            )

        def collide_target_publication(*args, **kwargs):
            nonlocal publication_attempts
            if not target_active:
                return real_publish(*args, **kwargs)
            publication_attempts += 1
            raise FileExistsError("simulated Gate 2 publication collision")

        def stop_target_child(*args, **kwargs):
            nonlocal stopped_children
            if not target_active:
                return real_stop(*args, **kwargs)
            stopped_children += 1
            return True

        started_at = time.monotonic()
        with mock.patch.object(
            CLI,
            "acquire_common_lock",
            side_effect=acquire_with_one_clock,
        ), mock.patch.object(
            CLI,
            "run_fenced_command",
            side_effect=run_real_until_target,
        ), mock.patch.object(
            CLI,
            "_spawn_blocked_fence_child",
            side_effect=spawn_target_child,
        ), mock.patch.object(
            CLI,
            "_publish_fence",
            side_effect=collide_target_publication,
        ), mock.patch.object(
            CLI,
            "_stop_unstarted_child",
            side_effect=stop_target_child,
        ), self.assertRaises(CLI.CommonLockUnavailable) as caught:
            engine.finalize()
        wall_elapsed = time.monotonic() - started_at

        self.assertEqual(CLI.COMMON_LOCK_TIMEOUT_SECONDS, 300.0)
        self.assertEqual(len(acquired_locks), 1)
        self.assertEqual(len(acquisition_starts), 1)
        acquisition_deadline = acquired_locks[0].deadline
        self.assertEqual(
            acquisition_deadline,
            acquisition_starts[0] + CLI.COMMON_LOCK_TIMEOUT_SECONDS,
        )
        self.assertIsNotNone(target_start, caught.exception.evidence)
        self.assertGreater(target_start, acquisition_deadline)
        self.assertEqual(publication_attempts, 2)
        self.assertEqual(stopped_children, 2)
        self.assertEqual(len(ack_deadlines), 2)
        self.assertEqual(ack_deadlines[0], target_start + 5.0)
        self.assertEqual(ack_deadlines[1], target_start + 300.0)
        self.assertEqual(clock.value, target_start + 300.0)
        self.assertEqual(gate_one_completed, 1)
        self.assertEqual(len(publication_sleeps), 2)
        self.assertGreater(publication_sleeps[0], 0.0)
        self.assertGreater(publication_sleeps[1], 0.0)
        self.assertLess(wall_elapsed, 30.0)
        self.assertEqual(
            caught.exception.reason_code,
            CLI.V2ReasonCode.REBASE_LOCK_UNAVAILABLE,
        )
        self.assertEqual(
            caught.exception.message, "forge: common rebase lock unavailable"
        )
        self.assertEqual(
            caught.exception.evidence["detail"],
            "existing in-flight fence exhausted the fence-publication deadline",
        )
        self.assertEqual(
            caught.exception.evidence["error"],
            "simulated Gate 2 publication collision",
        )
        self.assertEqual(caught.exception.outcome().exit_code, 1)
        self.assertIsNotNone(target_state_bytes)
        self.assertIsNotNone(target_event_bytes)
        self.assertEqual(store.state_path(chain_id).read_bytes(), target_state_bytes)
        self.assertEqual(store.events_path(chain_id).read_bytes(), target_event_bytes)

        target = store.load(chain_id)
        plan = target["integration"]["epoch"]["gate_plan"]
        self.assertEqual(target["state"], "reverifying")
        self.assertEqual(target["candidate"]["generation"], 2)
        self.assertEqual(target["integration"]["condition"], "none")
        self.assertEqual(
            plan["suite"],
            [
                {"kind": "gate", "id": "gate-1"},
                {"kind": "scoped-mutation", "id": "scoped-mutation"},
                {"kind": "gate", "id": "stack:python"},
                {"kind": "gate", "id": "invariant:1"},
                {"kind": "gate", "id": "assertion-sensor"},
            ],
        )
        self.assertEqual(plan["cursor"], 2)
        self.assertEqual(set(target["steps"]), {"gate-1", "scoped-mutation"})
        self.assertEqual(
            [target["steps"][step][0]["result"] for step in target["steps"]],
            ["passed", "passed"],
        )
        self.assertNotIn("stack:python", target["steps"])
        events = self.events(store, chain_id)
        current_generation = str(target["candidate"]["generation_digest"])
        gate_events = [
            event
            for event in events
            if event["event"] == "gate_recorded"
            and event["generation_digest"] == current_generation
        ]
        self.assertEqual(
            [
                event["payload"]["delta"]["integration"]["epoch"][
                    "gate_plan"
                ]["cursor"]
                for event in gate_events
            ],
            [1, 2],
        )
        self.assertNotIn("push_intent", [event["event"] for event in events])
        self.assertNotIn("push_observed", [event["event"] for event in events])
        self.assertEqual(
            self.git_at(self.origin, "rev-parse", "refs/heads/fixture-main"),
            remote_tip,
        )
        self.assertFalse((common / CLI.COMMON_LOCK_INFLIGHT_NAME).exists())

    def test_each_bounded_epoch_control_is_load_bearing(self) -> None:
        engine, store, authorized = self.authorize()
        before = store.events_path(str(authorized["chain_id"])).read_bytes()
        for control in sorted(CLI._REQUIRED_MERGE_INTEGRATION_CONTROLS):
            with self.subTest(control=control), mock.patch.object(
                CLI,
                "MERGE_INTEGRATION_CONTROLS",
                CLI.MERGE_INTEGRATION_CONTROLS - {control},
            ), self.assertRaisesRegex(
                CLI.FrozenError,
                f"merge integration control is unavailable: {control}",
            ):
                engine.finalize()
            self.assertEqual(
                store.events_path(str(authorized["chain_id"])).read_bytes(), before
            )

    def test_common_lock_release_failure_preserves_and_recovers_primary_truth(self) -> None:
        engine, store, authorized = self.authorize()
        original = CLI.acquire_common_lock

        def fail_final_release(*args, **kwargs):
            def boundary(stage: str) -> None:
                if stage == "release-final-fsynced":
                    raise OSError("injected final release fsync failure")

            return original(*args, **kwargs, boundary=boundary)

        with mock.patch.object(
            CLI, "acquire_common_lock", side_effect=fail_final_release
        ), self.assertRaises(CLI.CommonLockReleaseFailure) as caught:
            engine.finalize()
        retained = store.load(str(authorized["chain_id"]))
        self.assertEqual(caught.exception.reason_code, CLI.V2ReasonCode.LOCK_RELEASE_FAILED)
        self.assertEqual(retained["state"], "pushed")
        self.assertEqual(retained["integration"]["condition"], "lock-release-failed")
        self.assertEqual(retained["integration"]["primary_condition"], "none")

        recovered = engine.recover()
        current = store.load(str(authorized["chain_id"]))
        self.assertTrue(recovered.ok)
        self.assertEqual(current["state"], "pushed")
        self.assertEqual(current["integration"]["condition"], "none")
        names = [
            event["event"]
            for event in self.events(store, str(authorized["chain_id"]))
        ]
        self.assertEqual(names.count("push_intent"), 1)
        self.assertEqual(names[-2:], ["lock_release_result", "lock_release_result"])

    def test_cleanup_results_and_close_preconditions_are_replay_bound(self) -> None:
        engine, store, authorized = self.authorize()
        engine.finalize()
        chain_id = str(authorized["chain_id"])
        original = CLI.run_fenced_command
        captured: list[tuple[str, list[str], object]] = []

        def capture_cleanup_results(lock, **kwargs):
            result = original(lock, **kwargs)
            captured.append(
                (
                    str(kwargs.get("operation")),
                    list(kwargs.get("argv", ())),
                    result,
                )
            )
            return result

        with mock.patch.object(
            CLI, "run_fenced_command", side_effect=capture_cleanup_results
        ), mock.patch.object(
            CLI.MergeEngine,
            "_head_contained",
            side_effect=AssertionError("cleanup used unfenced merge-base"),
        ), mock.patch.object(
            CLI.Repository,
            "git",
            side_effect=AssertionError("cleanup used raw Repository.git"),
        ):
            cleaned = engine.cleanup_chain()

        terminal = store.load(chain_id)
        events = self.events(store, chain_id)
        cleanup_indexes = [
            index
            for index, event in enumerate(events)
            if event["event"] in {"cleanup_intent", "cleanup_result"}
        ]
        cleanup_events = [events[index] for index in cleanup_indexes]
        release_index = cleanup_indexes[-1] + 1
        release = events[release_index]
        logical_operations = [
            "remote-fetch",
            "remote-containment",
            "branch-observation",
            "worktree-observation",
            "worktree-remove",
            "branch-delete",
        ]
        fence_operations = [
            "remote-observation",
            "containment",
            "branch-delete",
            "worktree-remove",
            "worktree-remove",
            "branch-delete",
        ]
        self.assertTrue(cleaned.ok)
        self.assertEqual(terminal["state"], "closed")
        self.assertEqual(
            [operation for operation, _argv, _result in captured],
            fence_operations,
        )
        self.assertEqual(
            [event["event"] for event in cleanup_events],
            [name for _operation in logical_operations for name in (
                "cleanup_intent",
                "cleanup_result",
            )],
        )
        self.assertEqual(len(cleanup_events), 12)
        for offset, logical_operation in enumerate(logical_operations):
            intent_event = cleanup_events[offset * 2]
            result_event = cleanup_events[offset * 2 + 1]
            intent = intent_event["payload"]["delta"]["cleanup"]["intent"]
            result = result_event["payload"]["cleanup_results"][0]
            captured_fence, captured_argv, process = captured[offset]
            with self.subTest(operation=logical_operation):
                self.assertEqual(
                    intent["schema"], "forge-merge-cleanup-step-intent/1"
                )
                self.assertEqual(intent["operation"], logical_operation)
                self.assertEqual(intent["fence_operation"], captured_fence)
                self.assertEqual(intent["argv"], captured_argv)
                self.assertEqual(
                    result["schema"], "forge-merge-cleanup-step-result/1"
                )
                self.assertEqual(result["operation"], logical_operation)
                self.assertEqual(result["fence_operation"], captured_fence)
                self.assertEqual(
                    result["operation_nonce"], intent["operation_nonce"]
                )
                self.assertEqual(
                    result["intent_event_digest"], intent_event["digest"]
                )
                self.assertEqual(result["outcome"], "passed")
                self.assertEqual(
                    result["process"],
                    {
                        **process.evidence(),
                        "output_base64": base64.b64encode(
                            process.output
                        ).decode("ascii"),
                    },
                )
                self.assertTrue(
                    CLI._merge_cleanup_step_result_valid(
                        result, terminal, intent, intent_event["digest"]
                    )
                )
        self.assertEqual(release["event"], "ownership_release_intent")

        replay = self._original_merge_replay(
            chain_id, store.events_path(chain_id).read_bytes()
        )
        prior = next(
            entry[1]
            for entry in replay.entries
            if entry[0]["digest"] == release["digest"]
        )
        cleanup_evidence = CLI._merge_cleanup_evidence_history(
            events[:release_index]
        )
        summary = CLI._merge_cleanup_history_summary(events[:release_index])
        containment_observation = summary["remote_containment"]["observation"]
        close_preconditions = {
            "schema": "forge-merge-close-preconditions/2",
            "chain_id": chain_id,
            "source_state": prior["state"],
            "landed_head": prior["integration"]["push"]["landed_head"],
            "containment_observation": copy.deepcopy(
                containment_observation
            ),
            "cleanup_evidence": cleanup_evidence,
        }
        self.assertEqual(
            release["payload"]["terminal_preconditions_digest"],
            CLI.sha256_bytes(CLI.canonical_bytes(close_preconditions)),
        )

        for result_index in cleanup_indexes[1::2]:
            with self.subTest(result_sequence=events[result_index]["sequence"]):
                tampered = copy.deepcopy(events)
                process = tampered[result_index]["payload"]["cleanup_results"][
                    0
                ]["process"]
                selected = process["output_digest"]
                process["output_digest"] = (
                    ("0" if selected[0] != "0" else "1") + selected[1:]
                )
                tampered_raw = self.reseal_suffix(tampered, result_index)
                with mock.patch.object(
                    store, "_read_root_bytes", return_value=tampered_raw
                ), self.assertRaisesRegex(
                    CLI.FrozenError,
                    rf"merge event {events[result_index]['sequence']} transition is invalid",
                ):
                    store._read_replay_locked(chain_id)

        first_intent = cleanup_events[0]["payload"]["delta"]["cleanup"][
            "intent"
        ]
        first_result = cleanup_events[1]["payload"]["cleanup_results"][0]
        malformed_results = []
        for field, value in (
            ("returncode", True),
            ("duration_seconds", True),
            ("duration_seconds", float("nan")),
            ("duration_seconds", float("inf")),
            ("timed_out", 0),
            ("fence_inode", True),
            ("output_digest", int("1" * 64)),
            ("fence_digest", int("2" * 64)),
        ):
            malformed = copy.deepcopy(first_result)
            malformed["process"][field] = value
            malformed_results.append((field, value, malformed))
        for field, value, malformed in malformed_results:
            with self.subTest(exact_process_field=field, value=value):
                self.assertFalse(
                    CLI._merge_cleanup_step_result_valid(
                        malformed,
                        terminal,
                        first_intent,
                        cleanup_events[0]["digest"],
                    )
                )

        remove_intent_event = cleanup_events[8]
        remove_intent = remove_intent_event["payload"]["delta"]["cleanup"][
            "intent"
        ]
        partial_remove = copy.deepcopy(
            cleanup_events[9]["payload"]["cleanup_results"][0]
        )
        partial_remove["process"]["returncode"] = 1
        partial_remove["outcome"] = "already-absent"
        self.assertFalse(
            CLI._merge_cleanup_step_result_valid(
                partial_remove,
                terminal,
                remove_intent,
                remove_intent_event["digest"],
            )
        )

        observation_mutations = {
            "remote-fetch": ("oid", "0" * 40),
            "branch-observation": ("oid", "0" * 40),
            "worktree-observation": ("branch", "refs/heads/other"),
        }
        for offset, logical_operation in enumerate(logical_operations):
            mutation = observation_mutations.get(logical_operation)
            if mutation is None:
                continue
            result_index = cleanup_indexes[offset * 2 + 1]
            with self.subTest(observation_bytes_binding=logical_operation):
                tampered = copy.deepcopy(events)
                field, value = mutation
                tampered[result_index]["payload"]["cleanup_results"][0][
                    "observation"
                ][field] = value
                tampered_raw = self.reseal_suffix(tampered, result_index)
                with mock.patch.object(
                    store, "_read_root_bytes", return_value=tampered_raw
                ), self.assertRaisesRegex(
                    CLI.FrozenError,
                    rf"merge event {events[result_index]['sequence']} transition is invalid",
                ):
                    store._read_replay_locked(chain_id)

        abandoned = copy.deepcopy(events)
        first_result_index = cleanup_indexes[1]
        abandoned[first_result_index]["event"] = "cleanup_intent"
        abandoned[first_result_index]["payload"] = copy.deepcopy(
            abandoned[cleanup_indexes[0]]["payload"]
        )
        abandoned_raw = self.reseal_suffix(abandoned, first_result_index)
        with mock.patch.object(
            store, "_read_root_bytes", return_value=abandoned_raw
        ), self.assertRaisesRegex(
            CLI.FrozenError,
            rf"merge event {events[first_result_index]['sequence']} transition is invalid",
        ):
            store._read_replay_locked(chain_id)

        invalid_preconditions: dict[str, dict[str, object]] = {}
        changed_digest = copy.deepcopy(close_preconditions)
        changed_digest["landed_head"] = "0" * 40
        invalid_preconditions["tamper"] = changed_digest
        reordered = copy.deepcopy(close_preconditions)
        reordered["cleanup_evidence"][0], reordered["cleanup_evidence"][1] = (
            reordered["cleanup_evidence"][1],
            reordered["cleanup_evidence"][0],
        )
        invalid_preconditions["reorder"] = reordered
        omitted = copy.deepcopy(close_preconditions)
        omitted["cleanup_evidence"] = omitted["cleanup_evidence"][1:]
        invalid_preconditions["omission"] = omitted
        for mutation, malformed in invalid_preconditions.items():
            with self.subTest(close_history=mutation):
                tampered = copy.deepcopy(events)
                tampered[release_index]["payload"][
                    "terminal_preconditions_digest"
                ] = CLI.sha256_bytes(CLI.canonical_bytes(malformed))
                tampered_raw = self.reseal_suffix(tampered, release_index)
                with mock.patch.object(
                    store, "_read_root_bytes", return_value=tampered_raw
                ), self.assertRaisesRegex(
                    CLI.FrozenError,
                    rf"merge event {release['sequence']} transition is invalid",
                ):
                    store._read_replay_locked(chain_id)

    def test_cleanup_replay_and_close_validators_are_load_bearing(self) -> None:
        engine, store, authorized = self.authorize()
        engine.finalize()
        chain_id = str(authorized["chain_id"])
        engine.cleanup_chain()
        terminal = store.load(chain_id)
        events = self.events(store, chain_id)
        result_index = next(
            index
            for index, event in enumerate(events)
            if event["event"] == "cleanup_result"
            and event["payload"]["cleanup_results"][0]["operation"]
            == "branch-observation"
        )
        release_index = next(
            index
            for index, event in enumerate(events)
            if event["event"] == "ownership_release_intent"
            and event["payload"].get("target_terminal") == "closed"
        )

        result_disabled = copy.deepcopy(events)
        result_disabled[result_index]["payload"]["cleanup_results"][0][
            "observation"
        ]["oid"] = "0" * 40
        self.reseal_suffix(result_disabled, result_index)
        result_disabled_raw = self.replay_prefix(
            result_disabled, result_index
        )
        with mock.patch.object(
            store, "_read_root_bytes", return_value=result_disabled_raw
        ), self.assertRaisesRegex(
            CLI.FrozenError,
            rf"merge event {events[result_index]['sequence']} transition is invalid",
        ):
            store._read_replay_locked(chain_id)
        with mock.patch.object(
            store, "_read_root_bytes", return_value=result_disabled_raw
        ), mock.patch.object(
            CLI, "_merge_cleanup_step_result_valid", return_value=True
        ):
            self.assertEqual(
                store._read_replay_locked(chain_id).state["state"], "pushed"
            )

        close_disabled = copy.deepcopy(events)
        selected = close_disabled[release_index]["payload"][
            "terminal_preconditions_digest"
        ]
        close_disabled[release_index]["payload"][
            "terminal_preconditions_digest"
        ] = ("0" if selected[0] != "0" else "1") + selected[1:]
        self.reseal_suffix(close_disabled, release_index)
        close_disabled_raw = self.replay_prefix(close_disabled, release_index)
        with mock.patch.object(
            store, "_read_root_bytes", return_value=close_disabled_raw
        ), self.assertRaisesRegex(
            CLI.FrozenError,
            rf"merge event {events[release_index]['sequence']} transition is invalid",
        ):
            store._read_replay_locked(chain_id)
        with mock.patch.object(
            store, "_read_root_bytes", return_value=close_disabled_raw
        ), mock.patch.object(
            CLI, "_merge_release_preconditions_valid", return_value=True
        ):
            admitted = store._read_replay_locked(chain_id).state
            self.assertEqual(admitted["state"], "pushed")
            self.assertEqual(admitted["worktree"]["claim"]["status"], "releasing")

    def test_cleanup_pending_release_cutoffs_resume_without_lock_or_children(
        self,
    ) -> None:
        engine, store, authorized = self.authorize()
        finalized = engine.finalize()
        chain_id = str(authorized["chain_id"])
        events_before = self.events(store, chain_id)
        original_transition = store.transition_locked
        original_fenced = CLI.run_fenced_command
        operations: list[str] = []

        class CleanupReleaseCutoff(RuntimeError):
            pass

        def record_cleanup_children(lock, **kwargs):
            operations.append(str(kwargs.get("operation")))
            return original_fenced(lock, **kwargs)

        def stop_after(selected_event: str):
            fired = False

            def delegated(snapshot, event_name, *args, **kwargs):
                nonlocal fired
                current = original_transition(
                    snapshot, event_name, *args, **kwargs
                )
                if event_name == selected_event and not fired:
                    fired = True
                    raise CleanupReleaseCutoff(
                        f"cleanup cutoff after {selected_event}"
                    )
                return current

            return delegated

        with mock.patch.object(
            CLI, "run_fenced_command", side_effect=record_cleanup_children
        ), mock.patch.object(
            store,
            "transition_locked",
            side_effect=stop_after("ownership_release_intent"),
        ), self.assertRaisesRegex(
            CleanupReleaseCutoff,
            "cleanup cutoff after ownership_release_intent",
        ):
            engine.cleanup_chain()

        releasing = store.load(chain_id)
        releasing_events = self.events(store, chain_id)
        release_intent = releasing_events[-1]
        self.assertTrue(finalized.ok)
        self.assertEqual(releasing["state"], "pushed")
        self.assertEqual(releasing["cleanup"]["condition"], "none")
        self.assertEqual(releasing["worktree"]["claim"]["status"], "releasing")
        self.assertEqual(release_intent["event"], "ownership_release_intent")
        self.assertEqual(release_intent["payload"]["target_terminal"], "closed")
        self.assertEqual(
            release_intent["payload"]["terminal_disposition"], "ordinary"
        )
        self.assertEqual(
            operations,
            [
                "remote-observation",
                "containment",
                "branch-delete",
                "worktree-remove",
                "worktree-remove",
                "branch-delete",
            ],
        )
        self.assertEqual(
            [event["event"] for event in releasing_events[len(events_before) :]],
            [
                name
                for _operation in range(6)
                for name in ("cleanup_intent", "cleanup_result")
            ]
            + ["ownership_release_intent"],
        )
        self.assertFalse(self.worktree.exists())

        with mock.patch.object(
            CLI,
            "run_fenced_command",
            side_effect=AssertionError("pending cleanup reran a fenced child"),
        ) as releasing_children, mock.patch.object(
            CLI,
            "acquire_common_lock",
            side_effect=AssertionError(
                "releasing cleanup acquired the common lock"
            ),
        ) as releasing_common_lock, mock.patch.object(
            store,
            "transition_locked",
            side_effect=stop_after("ownership_released"),
        ), self.assertRaisesRegex(
            CleanupReleaseCutoff,
            "cleanup cutoff after ownership_released",
        ):
            engine.cleanup_chain()
        releasing_children.assert_not_called()
        releasing_common_lock.assert_not_called()

        released = store.load(chain_id)
        released_events = self.events(store, chain_id)
        release_result = released_events[-1]
        self.assertEqual(released["state"], "pushed")
        self.assertEqual(released["worktree"]["claim"]["status"], "released")
        self.assertEqual(release_result["event"], "ownership_released")
        self.assertEqual(
            release_result["payload"]["release_intent_digest"],
            release_intent["digest"],
        )

        with mock.patch.object(
            CLI,
            "run_fenced_command",
            side_effect=AssertionError("released cleanup reran a fenced child"),
        ) as released_children, mock.patch.object(
            CLI,
            "acquire_common_lock",
            side_effect=AssertionError(
                "released cleanup acquired the common lock"
            ),
        ) as released_common_lock:
            cleaned = engine.cleanup_chain()
        released_children.assert_not_called()
        released_common_lock.assert_not_called()

        closed = store.load(chain_id)
        closed_events = self.events(store, chain_id)
        self.assertTrue(cleaned.ok)
        self.assertEqual(cleaned.state, "closed")
        self.assertEqual(cleaned.next_required_step, "none — merge chain closed")
        self.assertEqual(closed["state"], "closed")
        self.assertEqual(closed["worktree"]["claim"]["status"], "released")
        self.assertEqual(
            [event["event"] for event in closed_events[len(events_before) :]],
            [
                name
                for _operation in range(6)
                for name in ("cleanup_intent", "cleanup_result")
            ]
            + ["ownership_release_intent", "ownership_released", "closed"],
        )
        self.assertEqual(
            operations,
            [
                "remote-observation",
                "containment",
                "branch-delete",
                "worktree-remove",
                "worktree-remove",
                "branch-delete",
            ],
        )
        self.assertFalse(Path(closed["worktree"]["claim"]["path"]).exists())
        self.assertEqual(
            self.git_at(self.origin, "rev-parse", "refs/heads/fixture-main"),
            closed["candidate"]["candidate_head"],
        )

    def test_cleanup_failure_parks_without_force_or_branch_deletion(self) -> None:
        engine, store, authorized = self.authorize()
        engine.finalize()
        candidate_head = store.load(str(authorized["chain_id"]))["candidate"][
            "candidate_head"
        ]
        changed = self.worktree / "post-push.txt"
        changed.write_text("moved branch\n", encoding="utf-8")
        self.git_at(self.worktree, "add", "post-push.txt")
        self.git_at(
            self.worktree,
            "commit",
            "--quiet",
            "-m",
            "move branch before cleanup",
        )

        with self.assertRaises(CLI.Refusal) as caught:
            engine.cleanup_chain()
        chain_id = str(authorized["chain_id"])
        pending = store.load(chain_id)
        cleanup_events = [
            event
            for event in self.events(store, chain_id)
            if event["event"] in {"cleanup_intent", "cleanup_result"}
        ]
        cleanup_results = [
            event["payload"]["cleanup_results"][0]
            for event in cleanup_events
            if event["event"] == "cleanup_result"
        ]
        self.assertEqual(caught.exception.reason_code, CLI.V2ReasonCode.CLEANUP_FAILED)
        self.assertEqual(pending["state"], "cleanup_pending")
        self.assertEqual(pending["cleanup"]["condition"], "cleanup-failed")
        self.assertEqual(
            [result["operation"] for result in cleanup_results],
            ["remote-fetch", "remote-containment", "branch-observation"],
        )
        self.assertEqual(cleanup_results[-1]["outcome"], "failed")
        self.assertEqual(
            cleanup_results[-1]["observation"],
            {
                "branch": pending["branch"],
                "exists": True,
                "oid": self.git_at(self.worktree, "rev-parse", "HEAD"),
            },
        )
        self.assertTrue(cleanup_results[-1]["process"]["authorized"])
        cleanup_argv = [
            result["process"]["argv"] for result in cleanup_results
        ]
        self.assertFalse(
            any("worktree" in argv and "remove" in argv for argv in cleanup_argv)
        )
        self.assertFalse(any("update-ref" in argv for argv in cleanup_argv))
        self.assertTrue(self.worktree.exists())
        self.assertEqual(
            self.git_at(self.origin, "rev-parse", "refs/heads/fixture-main"),
            candidate_head,
        )

    def test_cleanup_pre_fence_failure_closes_intent_for_retry(self) -> None:
        engine, store, authorized = self.authorize()
        engine.finalize()
        chain_id = str(authorized["chain_id"])
        unavailable = CLI.CommonLockUnavailable(
            {"common_dir": str(self.repo), "detail": "injected pre-fence failure"}
        )

        with mock.patch.object(
            CLI, "run_fenced_command", side_effect=unavailable
        ), self.assertRaises(CLI.CommonLockUnavailable):
            engine.cleanup_chain()

        pending = store.load(chain_id)
        events = self.events(store, chain_id)
        intent_event, result_event = events[-2:]
        result = result_event["payload"]["cleanup_results"][0]
        self.assertEqual(intent_event["event"], "cleanup_intent")
        self.assertEqual(result_event["event"], "cleanup_result")
        self.assertEqual(result["operation"], "remote-fetch")
        self.assertEqual(result["outcome"], "failed")
        self.assertEqual(result["intent_event_digest"], intent_event["digest"])
        self.assertEqual(
            result["process"],
            {
                "argv": intent_event["payload"]["delta"]["cleanup"]["intent"][
                    "argv"
                ],
                "returncode": None,
                "duration_seconds": 0.0,
                "output_digest": CLI.sha256_bytes(b""),
                "timed_out": False,
                "output_limit": False,
                "launch_failed": True,
                "group_survived": False,
                "authorized": False,
                "fence_digest": None,
                "fence_inode": None,
                "output_base64": "",
            },
        )
        self.assertEqual(
            result["observation"],
            {
                "exists": None,
                "oid": None,
                "fetch_head_base64": None,
                "fetch_head_digest": None,
            },
        )
        self.assertEqual(pending["state"], "cleanup_pending")
        self.assertEqual(pending["cleanup"], {"condition": "cleanup-failed"})

        intent = intent_event["payload"]["delta"]["cleanup"]["intent"]
        impossible_results = []
        for field, value in (
            ("returncode", 0),
            ("duration_seconds", 1.0),
            ("duration_seconds", -0.0),
            ("launch_failed", False),
            ("timed_out", True),
            ("fence_digest", CLI.sha256_bytes(b"invented fence")),
            ("fence_inode", 1),
        ):
            impossible = copy.deepcopy(result)
            impossible["process"][field] = value
            impossible_results.append((field, impossible))
        impossible_observation = copy.deepcopy(result)
        impossible_observation["observation"]["exists"] = False
        impossible_results.append(("observation", impossible_observation))
        for field, impossible in impossible_results:
            with self.subTest(no_execution_field=field):
                self.assertFalse(
                    CLI._merge_cleanup_step_result_valid(
                        impossible, pending, intent, intent_event["digest"]
                    )
                )

        tampered = copy.deepcopy(events)
        tampered[-1]["payload"]["cleanup_results"][0]["process"][
            "launch_failed"
        ] = False
        tampered_raw = self.reseal_suffix(tampered, len(tampered) - 1)
        with mock.patch.object(
            store, "_read_root_bytes", return_value=tampered_raw
        ), self.assertRaisesRegex(
            CLI.FrozenError,
            rf"merge event {result_event['sequence']} transition is invalid",
        ):
            store._read_replay_locked(chain_id)

        cleaned = engine.cleanup_chain()
        self.assertTrue(cleaned.ok)
        self.assertEqual(store.load(chain_id)["state"], "closed")

    def test_cleanup_retry_retains_failed_partial_history_and_skips_completed_step(
        self,
    ) -> None:
        engine, store, authorized = self.authorize()
        engine.finalize()
        chain_id = str(authorized["chain_id"])
        original = CLI.run_fenced_command
        failed_once = False

        def fail_first_branch_delete(lock, **kwargs):
            nonlocal failed_once
            argv = list(kwargs["argv"])
            if (
                kwargs.get("operation") == "branch-delete"
                and "update-ref" in argv
                and not failed_once
            ):
                failed_once = True
                output = b"injected branch deletion failure\n"
                result = CLI.FencedProcessResult(
                    argv=argv,
                    returncode=1,
                    duration_seconds=0.01,
                    output=output,
                    output_digest=CLI.sha256_bytes(output),
                    timed_out=False,
                    output_limit=False,
                    launch_failed=False,
                    group_survived=False,
                    authorized=True,
                    fence_digest=CLI.sha256_bytes(
                        CLI.canonical_bytes(
                            {"operation": "branch-delete", "argv": argv}
                        )
                    ),
                    fence_inode=1,
                )
                kwargs["persist_result"](result)
                return result
            return original(lock, **kwargs)

        with mock.patch.object(
            CLI, "run_fenced_command", side_effect=fail_first_branch_delete
        ), self.assertRaises(CLI.Refusal) as caught:
            engine.cleanup_chain()
        interrupted = store.load(chain_id)
        first_raw = store.events_path(chain_id).read_bytes()
        first_events = self.events(store, chain_id)
        first_results = [
            event["payload"]["cleanup_results"][0]
            for event in first_events
            if event["event"] == "cleanup_result"
            and "cleanup_results" in event["payload"]
        ]
        push_intents = sum(
            event["event"] == "push_intent" for event in first_events
        )
        self.assertEqual(caught.exception.reason_code, CLI.V2ReasonCode.CLEANUP_FAILED)
        self.assertEqual(interrupted["state"], "cleanup_pending")
        self.assertEqual(interrupted["cleanup"], {"condition": "cleanup-failed"})
        self.assertFalse(self.worktree.exists())
        self.assertEqual(
            [result["operation"] for result in first_results[-6:]],
            [
                "remote-fetch",
                "remote-containment",
                "branch-observation",
                "worktree-observation",
                "worktree-remove",
                "branch-delete",
            ],
        )
        failed_result = copy.deepcopy(first_results[-1])
        self.assertEqual(failed_result["outcome"], "failed")
        self.assertIsNone(failed_result["observation"]["deleted"])
        self.assertEqual(
            self.git_at(
                self.repo,
                "rev-parse",
                str(interrupted["branch"]),
            ),
            interrupted["candidate"]["candidate_head"],
        )

        retried_operations: list[tuple[str, list[str]]] = []

        def capture_retry(lock, **kwargs):
            retried_operations.append(
                (str(kwargs.get("operation")), list(kwargs.get("argv", ())))
            )
            return original(lock, **kwargs)

        with mock.patch.object(
            CLI, "run_fenced_command", side_effect=capture_retry
        ):
            recovered = engine.cleanup_chain()
        closed = store.load(chain_id)
        final_events = self.events(store, chain_id)
        release_index = next(
            index
            for index, event in enumerate(final_events)
            if event["event"] == "ownership_release_intent"
            and event["payload"].get("target_terminal") == "closed"
        )
        cleanup_evidence = CLI._merge_cleanup_evidence_history(
            final_events[:release_index]
        )
        self.assertTrue(recovered.ok)
        self.assertEqual(closed["state"], "closed")
        self.assertFalse(Path(closed["worktree"]["claim"]["path"]).exists())
        self.assertTrue(store.events_path(chain_id).read_bytes().startswith(first_raw))
        self.assertEqual(
            [operation for operation, _argv in retried_operations],
            [
                "remote-observation",
                "containment",
                "branch-delete",
                "branch-delete",
            ],
        )
        self.assertFalse(
            any(
                "worktree" in argv and "remove" in argv
                for _operation, argv in retried_operations
            )
        )
        self.assertIn(
            failed_result,
            [
                item["payload"]["cleanup_results"][0]
                for item in cleanup_evidence
                if item["event"] == "cleanup_result"
            ],
        )
        self.assertEqual(
            sum(event["event"] == "push_intent" for event in final_events),
            push_intents,
        )

    def test_cleanup_crash_after_intent_requires_recovery_bound_restart(self) -> None:
        engine, store, authorized = self.authorize()
        engine.finalize()
        chain_id = str(authorized["chain_id"])
        common_dir = Path(str(store.load(chain_id)["worktree"]["common_dir"]))

        def crash_after_intent() -> None:
            original_transition = store.transition_locked

            def kill_after_durable_intent(snapshot, event_name, *args, **kwargs):
                current = original_transition(
                    snapshot, event_name, *args, **kwargs
                )
                if event_name == "cleanup_intent":
                    os.kill(os.getpid(), signal.SIGKILL)
                return current

            with mock.patch.object(
                store,
                "transition_locked",
                side_effect=kill_after_durable_intent,
            ):
                engine.cleanup_chain()

        self.assert_sigkill_crash(crash_after_intent)
        pending_events = self.events(store, chain_id)
        pending_intent = pending_events[-1]
        self.assertEqual(pending_intent["event"], "cleanup_intent")
        self.assertEqual(
            pending_intent["payload"]["delta"]["cleanup"]["intent"][
                "operation"
            ],
            "remote-fetch",
        )
        self.assertFalse(
            (common_dir / CLI.COMMON_LOCK_INFLIGHT_NAME).exists()
        )
        self.assertTrue(self.worktree.exists())

        with self.assertRaises(CLI.Refusal) as recovered:
            engine.recover()
        self.assertEqual(
            recovered.exception.reason_code, CLI.V2ReasonCode.STATE_PRECONDITION
        )
        recovered_events = self.events(store, chain_id)
        recovery_event = recovered_events[-1]
        recovery_proof = recovery_event["payload"]["recovery_proof"]
        self.assertEqual(recovery_event["event"], "condition_recorded")
        self.assertEqual(
            recovery_event["previous_digest"], pending_intent["digest"]
        )
        self.assertEqual(
            recovery_proof["lifecycle"]["classification"],
            "owner-death-only",
        )

        cleaned = engine.cleanup_chain()
        closed_events = self.events(store, chain_id)
        strict_intents = [
            event
            for event in closed_events
            if event["event"] == "cleanup_intent"
            and event["payload"]["delta"]["cleanup"]["intent"].get(
                "schema"
            )
            == "forge-merge-cleanup-step-intent/1"
        ]
        self.assertTrue(cleaned.ok)
        self.assertEqual(store.load(chain_id)["state"], "closed")
        self.assertEqual(
            strict_intents[0]["payload"]["delta"]["cleanup"]["intent"][
                "argv"
            ],
            strict_intents[1]["payload"]["delta"]["cleanup"]["intent"][
                "argv"
            ],
        )
        self.assertNotEqual(
            strict_intents[0]["payload"]["delta"]["cleanup"]["intent"][
                "operation_nonce"
            ],
            strict_intents[1]["payload"]["delta"]["cleanup"]["intent"][
                "operation_nonce"
            ],
        )
        self.assertEqual(
            strict_intents[1]["payload"]["delta"]["cleanup"]["intent"][
                "recovery"
            ],
            {
                "schema": "forge-merge-cleanup-recovery/1",
                "intent_event_digest": pending_intent["digest"],
                "operation": "remote-fetch",
                "fence_operation": "remote-observation",
                "recovery_event_digest": recovery_event["digest"],
            },
        )

    def _assert_cleanup_pre_result_crash_recovery(
        self, target_operation: str
    ) -> None:
        engine, store, authorized = self.authorize()
        engine.finalize()
        chain_id = str(authorized["chain_id"])
        pushed = store.load(chain_id)
        common_dir = Path(str(pushed["worktree"]["common_dir"]))

        def crash_before_result() -> None:
            def boundary(stage: str) -> None:
                if stage != "fence-before-result":
                    return
                tail = self.events(store, chain_id)[-1]
                intent = tail["payload"]["delta"]["cleanup"]["intent"]
                if intent["operation"] == target_operation:
                    os.kill(os.getpid(), signal.SIGKILL)

            def crashing_common_lock(*args, **kwargs):
                kwargs["boundary"] = boundary
                return self._original_common_lock(*args, **kwargs)

            with mock.patch.object(
                CLI,
                "acquire_common_lock",
                side_effect=crashing_common_lock,
            ):
                engine.cleanup_chain()

        self.assert_sigkill_crash(crash_before_result)
        interrupted_events = self.events(store, chain_id)
        pending_intent_event = interrupted_events[-1]
        pending_intent = pending_intent_event["payload"]["delta"]["cleanup"][
            "intent"
        ]
        fence_path = common_dir / CLI.COMMON_LOCK_INFLIGHT_NAME
        self.assertEqual(pending_intent_event["event"], "cleanup_intent")
        self.assertEqual(pending_intent["operation"], target_operation)
        self.assertTrue(fence_path.exists())
        if target_operation == "worktree-remove":
            self.assertFalse(self.worktree.exists())
        else:
            self.assertEqual(target_operation, "branch-delete")
            self.assertNotEqual(
                CLI.Repository(self.repo)
                .git(
                    ["show-ref", "--verify", str(pushed["branch"])],
                    check=False,
                )
                .returncode,
                0,
            )

        with self.assertRaises(CLI.Refusal) as recovered:
            engine.recover()
        self.assertEqual(
            recovered.exception.reason_code, CLI.V2ReasonCode.STATE_PRECONDITION
        )
        recovery_event = self.events(store, chain_id)[-1]
        proof = recovery_event["payload"]["recovery_proof"]
        self.assertEqual(
            proof["lifecycle"]["classification"],
            f"{pending_intent['fence_operation']}-intent-pending",
        )
        self.assertFalse(fence_path.exists())

        retried_operations: list[tuple[str, list[str]]] = []
        original = CLI.run_fenced_command

        def capture_retry(lock, **kwargs):
            retried_operations.append(
                (str(kwargs.get("operation")), list(kwargs.get("argv", ())))
            )
            return original(lock, **kwargs)

        with mock.patch.object(
            CLI, "run_fenced_command", side_effect=capture_retry
        ):
            cleaned = engine.cleanup_chain()
        closed_events = self.events(store, chain_id)
        recovery_index = next(
            index
            for index, event in enumerate(closed_events)
            if event["digest"] == recovery_event["digest"]
        )
        restart_intent = closed_events[recovery_index + 1]["payload"]["delta"][
            "cleanup"
        ]["intent"]
        self.assertTrue(cleaned.ok)
        self.assertEqual(store.load(chain_id)["state"], "closed")
        self.assertEqual(restart_intent["operation"], "remote-fetch")
        self.assertEqual(
            restart_intent["recovery"],
            {
                "schema": "forge-merge-cleanup-recovery/1",
                "intent_event_digest": pending_intent_event["digest"],
                "operation": target_operation,
                "fence_operation": pending_intent["fence_operation"],
                "recovery_event_digest": recovery_event["digest"],
            },
        )
        if target_operation == "worktree-remove":
            self.assertFalse(
                any(
                    "worktree" in argv and "remove" in argv
                    for _operation, argv in retried_operations
                )
            )
        else:
            self.assertFalse(
                any("update-ref" in argv for _operation, argv in retried_operations)
            )

    def test_cleanup_worktree_remove_pre_result_crash_is_observed(self) -> None:
        self._assert_cleanup_pre_result_crash_recovery("worktree-remove")

    def test_cleanup_branch_delete_pre_result_crash_is_observed(self) -> None:
        self._assert_cleanup_pre_result_crash_recovery("branch-delete")

    def test_cleanup_result_is_durable_before_fence_release_crash(self) -> None:
        engine, store, authorized = self.authorize()
        engine.finalize()
        chain_id = str(authorized["chain_id"])
        common_dir = Path(str(store.load(chain_id)["worktree"]["common_dir"]))

        def crash_after_removal_result() -> None:
            persisted_results = 0

            def boundary(stage: str) -> None:
                nonlocal persisted_results
                if stage != "fence-result-persisted":
                    return
                persisted_results += 1
                if persisted_results == 5:
                    os.kill(os.getpid(), signal.SIGKILL)

            def crashing_common_lock(*args, **kwargs):
                kwargs["boundary"] = boundary
                return self._original_common_lock(*args, **kwargs)

            with mock.patch.object(
                CLI,
                "acquire_common_lock",
                side_effect=crashing_common_lock,
            ):
                CLI.MergeEngine(
                    self.context(chain_id=chain_id)
                ).cleanup_chain()

        self.assert_sigkill_crash(crash_after_removal_result)
        interrupted = store.load(chain_id)
        interrupted_events = self.events(store, chain_id)
        durable_result = interrupted_events[-1]["payload"]["cleanup_results"][0]
        fence_path = common_dir / CLI.COMMON_LOCK_INFLIGHT_NAME
        self.assertEqual(interrupted_events[-1]["event"], "cleanup_result")
        self.assertEqual(durable_result["operation"], "worktree-remove")
        self.assertEqual(durable_result["outcome"], "passed")
        self.assertEqual(
            durable_result["process"]["fence_digest"],
            CLI.sha256_bytes(fence_path.read_bytes()),
        )
        self.assertEqual(interrupted["state"], "pushed")
        self.assertFalse(self.worktree.exists())
        self.assertTrue(fence_path.exists())

        with self.assertRaises(CLI.Refusal) as recovered:
            engine.recover()
        self.assertEqual(
            recovered.exception.reason_code, CLI.V2ReasonCode.STATE_PRECONDITION
        )
        self.assertFalse(fence_path.exists())

        retried_argv: list[list[str]] = []
        original = CLI.run_fenced_command

        def capture_retry(lock, **kwargs):
            retried_argv.append(list(kwargs.get("argv", ())))
            return original(lock, **kwargs)

        with mock.patch.object(
            CLI, "run_fenced_command", side_effect=capture_retry
        ):
            cleaned = engine.cleanup_chain()
        closed = store.load(chain_id)
        self.assertTrue(cleaned.ok)
        self.assertEqual(closed["state"], "closed")
        self.assertFalse(
            any("worktree" in argv and "remove" in argv for argv in retried_argv)
        )
        retained_results = [
            item["payload"]["cleanup_results"][0]
            for item in CLI._merge_cleanup_evidence_history(
                self.events(store, chain_id)
            )
            if item["event"] == "cleanup_result"
        ]
        self.assertIn(durable_result, retained_results)

    def test_eighth_review_cycle_attaches_residual_risk_then_stops(self) -> None:
        _admission, _generation, store, engine, _outcome, _calls = self.verify_chain()

        for iteration in range(1, 9):
            engine.review_request()
            requested = store.load(self.chain_id)
            self.assertEqual(requested["review"]["iteration"], iteration)
            verdict = self.write_verdict(
                f"integration-cap-block-{iteration}.txt",
                "BLOCK",
                requested["review"]["request"],
                ("MAJOR", f"unresolved finding {iteration}"),
            )
            engine.review_attach(str(verdict))
            attached = store.load(self.chain_id)
            self.assertEqual(attached["state"], "revising")
            self.assertEqual(attached["review"]["iteration"], iteration)
            if iteration == 8:
                break
            self.assertNotIn("residual_risk", attached["review"])
            (self.worktree / "src" / "app.py").write_text(
                f"VALUE = {iteration + 2}\n", encoding="utf-8"
            )
            self.git_at(self.worktree, "add", "src/app.py")
            self.git_at(
                self.worktree,
                "commit",
                "--quiet",
                "-m",
                f"repair review iteration {iteration}",
            )
            engine.refresh(remote_tip=self.base)
            with mock.patch.object(
                RUNTIME, "run_bounded", side_effect=self.passing_process
            ):
                engine.verify()

        capped = store.load(self.chain_id)
        self.assertEqual(capped["state"], "revising")
        self.assertEqual(capped["review"]["iteration"], 8)
        self.assertEqual(
            capped["review"]["residual_risk"],
            {
                "at": capped["review"]["residual_risk"]["at"],
                "reason": "review iteration cap reached",
                "findings": capped["review"]["verdict"]["findings"],
            },
        )
        self.assertEqual(self.events(store, self.chain_id)[-1]["event"], "review_attached")

        before_events = store.events_path(self.chain_id).read_bytes()
        before_state = store.state_path(self.chain_id).read_bytes()
        artifact_root = store.artifact_dir(self.chain_id)

        def artifact_snapshot() -> dict[str, bytes | None]:
            return {
                path.relative_to(artifact_root).as_posix(): (
                    path.read_bytes() if path.is_file() else None
                )
                for path in artifact_root.rglob("*")
            }

        before_artifacts = artifact_snapshot()
        calls = (
            (
                "request",
                engine.review_request,
                CLI.V2ReasonCode.ITERATION_CAP,
                "review iteration cap of 8 reached; no further merge review is admitted",
            ),
            (
                "attach",
                lambda: engine.review_attach(str(verdict)),
                CLI.V2ReasonCode.ITERATION_CAP,
                "forge: review attach refused — review iteration cap of 8 is final",
            ),
            (
                "disposition",
                lambda: engine.review_disposition(1, "MAJOR", "accept"),
                CLI.V2ReasonCode.ITERATION_CAP,
                "forge: review disposition refused — review iteration cap of 8 is final",
            ),
            (
                "approve",
                lambda: engine.approve(capped["candidate"]["candidate_head"]),
                CLI.V2ReasonCode.STATE_PRECONDITION,
                "forge: merge approve refused — merge transition is not admitted",
            ),
            (
                "refresh",
                lambda: engine.refresh(remote_tip=self.base),
                CLI.V2ReasonCode.ITERATION_CAP,
                "forge: merge refresh refused — review iteration cap of 8 is final",
            ),
        )
        for verb, call, reason, message in calls:
            with self.subTest(verb=verb), mock.patch.object(
                engine, "_halt"
            ), mock.patch.object(
                engine,
                "_review_package",
                side_effect=AssertionError("review package was inspected after cap"),
            ) as review_package, mock.patch.object(
                CLI,
                "_observe_current_merge_candidate",
                side_effect=AssertionError("candidate evidence was inspected after cap"),
            ) as observe_candidate, mock.patch.object(
                CLI,
                "_read_merge_artifact",
                side_effect=AssertionError("review artifact was read after cap"),
            ) as read_artifact, mock.patch.object(
                CLI,
                "_write_merge_artifact",
                side_effect=AssertionError("review artifact was written after cap"),
            ) as write_artifact, mock.patch.object(
                RUNTIME,
                "run_bounded",
                side_effect=AssertionError("bounded child ran after cap"),
            ) as bounded, mock.patch.object(
                CLI,
                "run_fenced_command",
                side_effect=AssertionError("fenced child ran after cap"),
            ) as fenced, self.assertRaises(CLI.Refusal) as caught:
                call()

            self.assertEqual(caught.exception.reason_code, reason)
            self.assertEqual(caught.exception.message, message)
            review_package.assert_not_called()
            observe_candidate.assert_not_called()
            read_artifact.assert_not_called()
            write_artifact.assert_not_called()
            bounded.assert_not_called()
            fenced.assert_not_called()
            self.assertEqual(store.events_path(self.chain_id).read_bytes(), before_events)
            self.assertEqual(store.state_path(self.chain_id).read_bytes(), before_state)
            self.assertEqual(artifact_snapshot(), before_artifacts)

    def test_gate_transcript_generation_component_prevents_stem_collision(self) -> None:
        _admission, _generation, store, engine, _outcome, _calls = self.verify_chain()
        base = store.load(self.chain_id)
        states = []
        for generation, gate_id in (
            (1, "stack:python-generation-2"),
            (2, "stack:python"),
        ):
            state = copy.deepcopy(base)
            state["steps"] = {}
            state["candidate"]["generation"] = generation
            state["candidate"]["generation_digest"] = CLI.sha256_bytes(
                CLI.canonical_bytes(
                    {
                        name: value
                        for name, value in state["candidate"].items()
                        if name != "generation_digest"
                    }
                )
            )
            process = self.passing_process(["gate", gate_id])
            with mock.patch.object(
                engine.store, "transition", return_value=state
            ) as transition:
                engine._record_gate_result(
                    state,
                    [gate_id],
                    gate_id,
                    process.argv,
                    process,
                    {},
                )
            states.append(transition.call_args.args[2]["delta"]["steps"])

        first = states[0]["stack:python-generation-2"][0]["transcript"]
        second = states[1]["stack:python"][0]["transcript"]
        prefix = f".forge/chains/{self.chain_id}/evidence"
        self.assertEqual(first, f"{prefix}/stack-python-generation-2-01.log")
        self.assertEqual(second, f"{prefix}/generation-2/stack-python-01.log")
        self.assertNotEqual(first, second)
        self.assertEqual(
            (self.repo / first).read_bytes(),
            b"pass gate stack:python-generation-2\n",
        )
        self.assertEqual(
            (self.repo / second).read_bytes(), b"pass gate stack:python\n"
        )


_MERGE_INTEGRATION_SHARD_COUNT = 3


def merge_integration_shard_suite(shard: int) -> unittest.TestSuite:
    """Partition this large real-Git matrix without weakening discovery.

    ``python3 -m unittest tests.test_cli_merge_integration`` runs shard 0 only
    (one third of ``MergeIntegrationEpochTests``); the sibling
    ``tests/test_cli_merge_integration_shard<n>.py`` modules run the rest, and
    full discovery runs all of them. To run the whole matrix focused, name all
    three modules.
    """

    if shard not in range(_MERGE_INTEGRATION_SHARD_COUNT):
        raise ValueError(f"invalid merge integration shard: {shard}")
    names = unittest.defaultTestLoader.getTestCaseNames(MergeIntegrationEpochTests)
    selected = [
        name
        for index, name in enumerate(names)
        if index % _MERGE_INTEGRATION_SHARD_COUNT == shard
    ]
    # Discovery loads this module as shard 0 and one sibling module per
    # remaining residue, so a shard count without its sibling module would
    # silently drop tests from Gate 1. Refuse that here, before any shard runs.
    expected_siblings = {
        f"test_cli_merge_integration_shard{residue}.py"
        for residue in range(1, _MERGE_INTEGRATION_SHARD_COUNT)
    }
    present_siblings = {
        candidate.name
        for candidate in Path(__file__).parent.glob(
            "test_cli_merge_integration_shard*.py"
        )
    }
    if present_siblings != expected_siblings:
        raise AssertionError(
            "merge integration shard partition is incomplete: expected "
            f"{sorted(expected_siblings)}, found {sorted(present_siblings)}"
        )
    return unittest.TestSuite(MergeIntegrationEpochTests(name) for name in selected)


def load_tests(
    _loader: unittest.TestLoader,
    _standard_tests: unittest.TestSuite,
    _pattern: str | None,
) -> unittest.TestSuite:
    return merge_integration_shard_suite(0)


if __name__ == "__main__":

    unittest.main()
