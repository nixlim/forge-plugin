"""Hermetic real-remote coverage for the dormant bounded merge epoch."""

from __future__ import annotations

import copy
import json
import os
import signal
import subprocess
import time
from collections import OrderedDict
from pathlib import Path
from unittest import mock

from tests import test_cli_merge_adapters as ADAPTERS


CLI = ADAPTERS.CLI


class _LogicalClock:
    """Advance lock and lease retry deadlines without wall-clock sleeps."""

    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += max(0.0, seconds)


class MergeIntegrationEpochTests(ADAPTERS.MergeAdapterFixture):
    _LOCK_TIMEOUT_SECONDS = 1.0
    _LOCK_POLL_SECONDS = 0.01
    _PROCESS_TIMEOUT_SECONDS = 5.0
    _REPLAY_CACHE_ENTRIES = 8
    _SIGKILL_DEADLINE_SECONDS = 10.0
    _SIGKILL_POLL_SECONDS = 0.01

    def setUp(self) -> None:
        super().setUp()
        clock = _LogicalClock()
        original_common_lock = CLI.acquire_common_lock
        original_chain_lease = CLI.acquire_chain_lease
        original_fenced_command = CLI.run_fenced_command
        original_bounded_command = CLI.run_bounded
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
        captured_context = {}
        preparing_event = 0

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
                float(
                    kwargs.get(
                        "timeout", CLI.COMMON_LOCK_TIMEOUT_SECONDS
                    )
                ),
                self._LOCK_TIMEOUT_SECONDS,
            )
            kwargs.setdefault("clock", clock)
            kwargs.setdefault("sleeper", clock.sleep)
            acquired = original_common_lock(*args, **kwargs)
            # Acquisition contention advances only the logical clock.  Once
            # acquired, retain a short real deadline for child publication and
            # termination so the OS has a fair scheduling window.
            acquired._clock = time.monotonic
            acquired._sleeper = time.sleep
            acquired.deadline = time.monotonic() + self._LOCK_TIMEOUT_SECONDS
            return acquired

        def bounded_chain_lease(*args, **kwargs):
            kwargs["timeout"] = min(
                float(
                    kwargs.get(
                        "timeout", CLI.COMMON_LOCK_TIMEOUT_SECONDS
                    )
                ),
                self._LOCK_TIMEOUT_SECONDS,
            )
            kwargs.setdefault("clock", clock)
            kwargs.setdefault("sleeper", clock.sleep)
            return original_chain_lease(*args, **kwargs)

        def bounded_fenced_command(*args, **kwargs):
            kwargs["timeout"] = min(
                float(kwargs.get("timeout", CLI.COMMAND_TIMEOUT_SECONDS)),
                self._PROCESS_TIMEOUT_SECONDS,
            )
            return original_fenced_command(*args, **kwargs)

        def bounded_command(*args, **kwargs):
            kwargs["timeout"] = min(
                float(kwargs.get("timeout", CLI.COMMAND_TIMEOUT_SECONDS)),
                self._PROCESS_TIMEOUT_SECONDS,
            )
            return original_bounded_command(*args, **kwargs)

        patches = (
            mock.patch.object(
                CLI,
                "COMMON_LOCK_TIMEOUT_SECONDS",
                self._LOCK_TIMEOUT_SECONDS,
            ),
            mock.patch.object(
                CLI, "COMMON_LOCK_POLL_SECONDS", self._LOCK_POLL_SECONDS
            ),
            mock.patch.object(
                CLI, "COMMAND_TIMEOUT_SECONDS", self._PROCESS_TIMEOUT_SECONDS
            ),
            mock.patch.object(
                CLI, "acquire_common_lock", new=bounded_common_lock
            ),
            mock.patch.object(
                CLI, "acquire_chain_lease", new=bounded_chain_lease
            ),
            mock.patch.object(
                CLI, "run_fenced_command", new=bounded_fenced_command
            ),
            mock.patch.object(CLI, "run_bounded", new=bounded_command),
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
            CLI, "run_bounded", side_effect=self.passing_process
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

    @staticmethod
    def replay_prefix(events: list[dict[str, object]], stop: int) -> bytes:
        return b"".join(
            CLI.canonical_bytes(event) + b"\n" for event in events[: stop + 1]
        )

    @staticmethod
    def reseal_event(event: dict[str, object]) -> None:
        event.pop("digest", None)
        event["digest"] = CLI.sha256_bytes(CLI.canonical_bytes(event))

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
        original = store.transition
        crashed = False

        def crash_after_release_intent(snapshot, event_name, *args, **kwargs):
            nonlocal crashed
            current = original(snapshot, event_name, *args, **kwargs)
            if event_name == "ownership_release_intent" and not crashed:
                crashed = True
                raise RuntimeError("simulated crash after ownership release intent")
            return current

        with mock.patch.object(
            store, "transition", side_effect=crash_after_release_intent
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

    def test_recovery_uses_the_sealed_cursor_after_rebase(self) -> None:
        engine, store, authorized = self.authorize()
        writer = self.clone_remote_writer("gate-crash-writer")
        self.push_remote_change(writer, "remote.txt", "remote generation\n")
        original = CLI.run_fenced_command

        def kill_before_gate_record(lock, **kwargs):
            if kwargs.get("operation") == "gate":
                os.kill(os.getpid(), signal.SIGKILL)
            return original(lock, **kwargs)

        def crash() -> None:
            with mock.patch.object(
                CLI, "run_fenced_command", side_effect=kill_before_gate_record
            ):
                engine.finalize()

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

        def kill_before_post_observation(lock, **kwargs):
            nonlocal observations
            if kwargs.get("operation") == "remote-observation":
                observations += 1
                if observations == 2:
                    os.kill(os.getpid(), signal.SIGKILL)
            return original(lock, **kwargs)

        def crash() -> None:
            with mock.patch.object(
                CLI,
                "run_fenced_command",
                side_effect=kill_before_post_observation,
            ):
                engine.finalize()

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

    def test_recovery_retries_when_no_authorized_push_result_survived(self) -> None:
        engine, store, authorized = self.authorize()
        original = CLI.run_fenced_command
        reject = self.origin / "hooks" / "pre-receive"
        reject.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        reject.chmod(0o755)

        def kill_before_push_result(lock, **kwargs):
            if kwargs.get("operation") == "push":
                kwargs["persist_result"] = lambda _result: os.kill(
                    os.getpid(), signal.SIGKILL
                )
            return original(lock, **kwargs)

        def crash() -> None:
            with mock.patch.object(
                CLI, "run_fenced_command", side_effect=kill_before_push_result
            ):
                engine.finalize()

        self.assert_sigkill_crash(crash)
        reject.unlink()
        interrupted = store.load(str(authorized["chain_id"]))
        self.assertEqual(interrupted["state"], "pushing")
        self.assertIsNone(interrupted["integration"]["push"]["result"])
        self.assertEqual(
            self.git_at(self.origin, "rev-parse", "refs/heads/fixture-main"),
            self.base,
        )

        observed = engine.recover()
        awaiting_retry = store.load(str(authorized["chain_id"]))
        self.assertTrue(observed.ok)
        self.assertEqual(awaiting_retry["state"], "pushing")
        self.assertIsNone(awaiting_retry["integration"]["push"]["result"])
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
        with mock.patch.object(CLI, "run_bounded", side_effect=self.passing_process):
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
            CLI, "run_bounded", side_effect=record_mode_read
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
            CLI, "run_bounded", side_effect=unsupported
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
            CLI, "run_bounded", side_effect=bounded
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
                engine.finalize()

        self.assert_sigkill_crash(crash)
        chain_id = str(authorized["chain_id"])
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
                engine.finalize()

        self.assert_sigkill_crash(crash)
        chain_id = str(authorized["chain_id"])
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

        def move_during_final_observation(lock, **kwargs):
            nonlocal moved, remote_tip
            if kwargs.get("operation") == "remote-observation" and not moved:
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

    def test_two_chain_ids_contend_on_the_same_common_lock(self) -> None:
        first = CLI.MergeEngine(self.context()).start_chain(
            str(self.worktree), remote_tip=self.base
        )
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
        second = CLI.MergeEngine(self.context()).start_chain(
            str(second_worktree), remote_tip=self.base
        )
        common = CLI.Repository(self.repo).git_common_dir()
        holder = CLI.acquire_common_lock(
            common,
            owner_kind="merge",
            chain_id=str(first.chain_id),
            operation="finalize",
            timeout=1,
            use_flock=False,
            no_transaction_record=True,
        )
        try:
            with self.assertRaises(CLI.CommonLockUnavailable) as caught:
                CLI.acquire_common_lock(
                    common,
                    owner_kind="merge",
                    chain_id=str(second.chain_id),
                    operation="finalize",
                    timeout=0.05,
                    use_flock=False,
                    no_transaction_record=True,
                )
            self.assertEqual(
                caught.exception.reason_code,
                CLI.V2ReasonCode.REBASE_LOCK_UNAVAILABLE,
            )
        finally:
            holder.release()

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
        pending = store.load(str(authorized["chain_id"]))
        self.assertEqual(caught.exception.reason_code, CLI.V2ReasonCode.CLEANUP_FAILED)
        self.assertEqual(pending["state"], "cleanup_pending")
        self.assertEqual(pending["cleanup"]["condition"], "cleanup-failed")
        self.assertTrue(self.worktree.exists())
        self.assertEqual(
            self.git_at(self.origin, "rev-parse", "refs/heads/fixture-main"),
            candidate_head,
        )

    def test_cleanup_retries_after_worktree_removal_crash(self) -> None:
        engine, store, authorized = self.authorize()
        engine.finalize()
        original = CLI.run_fenced_command
        crashed = False

        def crash_after_worktree_remove(lock, **kwargs):
            nonlocal crashed
            result = original(lock, **kwargs)
            if kwargs.get("operation") == "worktree-remove" and not crashed:
                crashed = True
                raise RuntimeError("simulated cleanup parent crash")
            return result

        with mock.patch.object(
            CLI, "run_fenced_command", side_effect=crash_after_worktree_remove
        ), self.assertRaisesRegex(RuntimeError, "cleanup parent crash"):
            engine.cleanup_chain()
        interrupted = store.load(str(authorized["chain_id"]))
        self.assertEqual(interrupted["state"], "pushed")
        self.assertFalse(self.worktree.exists())

        recovered = engine.cleanup_chain()
        closed = store.load(str(authorized["chain_id"]))
        self.assertTrue(recovered.ok)
        self.assertEqual(closed["state"], "closed")
        self.assertFalse(Path(closed["worktree"]["claim"]["path"]).exists())


if __name__ == "__main__":
    import unittest

    unittest.main()
