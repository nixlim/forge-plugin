"""Focused dormant merge lifecycle and carried-regression tests."""

from __future__ import annotations

import copy
import contextlib
import datetime as dt
import io
import json
import os
import subprocess
from pathlib import Path
from unittest import mock

from tests import test_cli_merge_adapters as ADAPTERS


CLI = ADAPTERS.CLI


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
        self.assertEqual(
            [
                json.loads(line)["event"]
                for line in store.events_path(str(outcome.chain_id))
                .read_text(encoding="utf-8")
                .splitlines()
            ],
            [
                "chain_started",
                "ownership_intent",
                "ownership_claimed",
                "fetch_intent",
                "fetch_result",
            ],
        )

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
        with mock.patch.object(
            CLI,
            "_resolve_recorded_merge_tip",
            side_effect=CLI._merge_refusal(
                CLI.V2ReasonCode.FETCH_FAILED,
                "forge: merge start refused — fixed target tip is unavailable",
            ),
        ), self.assertRaises(CLI.Refusal) as first:
            engine.start_chain(str(self.worktree))
        self.assertEqual(first.exception.reason_code, CLI.V2ReasonCode.FETCH_FAILED)
        chain_id = first.exception.chain["chain_id"]
        failed = engine.store.load(chain_id)
        self.assertEqual(failed["state"], "classifying")
        self.assertIsNone(failed["candidate"])
        self.assertEqual(failed["integration"]["condition"], "fetch-failed")

        retry = CLI.MergeEngine(self.context(chain_id=chain_id))
        outcome = retry.refresh(remote_tip=self.base)
        current = retry.store.load(chain_id)
        self.assertTrue(outcome.ok)
        self.assertEqual(current["state"], "verifying")
        self.assertEqual(current["candidate"]["generation"], 1)
        events = [
            json.loads(line)["event"]
            for line in retry.store.events_path(chain_id)
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        self.assertEqual(events[-2:], ["fetch_intent", "fetch_result"])
        self.assertEqual(current["integration"]["intent"]["attempt"], 2)

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
                with original_common(*args, **kwargs):
                    yield

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
        original = CLI.bind_merge_candidate_generation

        def exceed_scope(*args, **kwargs):
            generation = original(*args, **kwargs)
            assert generation.scope is not None
            scope = CLI.dataclasses.replace(
                generation.scope,
                result="exceeded",
                out_of_scope_paths=("outside/task.py",),
            )
            return CLI.dataclasses.replace(generation, scope=scope)

        engine = CLI.MergeEngine(self.context(run_id=self.run_id))
        with mock.patch.object(
            CLI, "bind_merge_candidate_generation", side_effect=exceed_scope
        ), self.assertRaises(CLI.Refusal) as caught:
            engine.start_chain(
                str(self.worktree),
                task=self.task_id,
                remote_tip=self.base,
            )

        self.assertEqual(
            caught.exception.reason_code,
            CLI.V2ReasonCode.RUN_TASK_BINDING_INVALID,
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


class MergeLifecycleRefreshTests(ADAPTERS.MergeAdapterFixture):
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
                "forge: merge abort refused — ownership release completion is pending",
            ),
            (
                "owned",
                "current",
                "pushed",
                "forge: merge abort refused — current intended HEAD is already contained",
            ),
            (
                "owned",
                "older",
                "pushed",
                "forge: merge abort refused — an older attempted HEAD is contained",
            ),
        )
        for claim_status, containment, scalar, message in priority:
            state = copy.deepcopy(base)
            state["worktree"]["claim"]["status"] = claim_status
            state["worktree"]["path"] = missing
            state["inactive_after"] = past
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

    def test_persisted_all_false_attempt_waits_for_slice_five_observation(self) -> None:
        _store, engine, base = self.start_owned_chain()
        attempted = copy.deepcopy(base)
        attempted["integration"]["push"] = {"attempted_heads": [self.candidate_head]}
        with mock.patch.object(engine, "_load", return_value=attempted), mock.patch.object(
            CLI, "_merge_containment", return_value=("all-false", (False,))
        ), mock.patch.object(
            CLI, "_merge_process_unresolved", return_value=False
        ), mock.patch.object(
            engine, "_release_to_aborted"
        ) as release, self.assertRaises(CLI.Refusal) as caught:
            engine.abort("not landed")
        self.assertEqual(
            caught.exception.message,
            "forge: merge abort refused — fresh attempted-head observation requires recovery",
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
    def test_lifecycle_adds_no_reason_enum_member(self) -> None:
        self.assertEqual(len(CLI.V2ReasonCode), 53)
        self.assertNotIn("run-scope-exceeded", {item.value for item in CLI.V2ReasonCode})

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
            (["merge", "abort", "--reason", "stop"], "abort"),
        )
        with mock.patch.object(CLI, "MERGE_LIFECYCLE_ACTIVE", True):
            for argv, command in cases:
                with self.subTest(argv=argv):
                    parsed = CLI.build_parser().parse_args(argv)
                self.assertEqual(parsed.command, "merge")
                self.assertEqual(parsed.merge_command, command)
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(
                CLI.Refusal
            ):
                CLI.build_parser().parse_args(["merge", "skip", "gate-1"])
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(
                CLI.Refusal
            ):
                CLI.build_parser().parse_args(["merge", "finalize"])

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
        with mock.patch.object(CLI, "MERGE_LIFECYCLE_ACTIVE", False):
            dormant = vars(CLI.build_parser().parse_args(argv))
        with mock.patch.object(CLI, "MERGE_LIFECYCLE_ACTIVE", True):
            active = vars(CLI.build_parser().parse_args(argv))
        self.assertEqual(active, dormant)

    def test_active_merge_start_run_task_pairing_is_checked_before_discovery(self) -> None:
        with mock.patch.object(CLI, "MERGE_LIFECYCLE_ACTIVE", True):
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

        with mock.patch.object(CLI, "MERGE_LIFECYCLE_ACTIVE", True), mock.patch.object(
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
        with mock.patch.object(CLI, "MERGE_LIFECYCLE_ACTIVE", True), mock.patch.object(
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
            (["merge", "abort", "--reason", "stop"], ("abort", "stop")),
        )
        with mock.patch.object(CLI, "MERGE_LIFECYCLE_ACTIVE", True), mock.patch.object(
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
                mock.patch.object(CLI, "MERGE_LIFECYCLE_ACTIVE", True)
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
