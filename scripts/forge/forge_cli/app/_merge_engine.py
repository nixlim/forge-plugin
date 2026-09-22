"""Extracted from scripts/forge/forge_cli/app/__init__.py."""
from __future__ import annotations
import contextlib
import copy
import os
import re
import secrets
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from forge_cli import chain_core, runtime, engine
from forge_cli.app._candidate_observation import _observe_current_merge_candidate
from forge_cli.app._mutation_journal import _persist_deferred_mutation_result
from forge_cli.envelope import FrozenError, Outcome, REVISION9_OUTPUT_SCHEMA, ReasonCode, Refusal, V2ReasonCode
from forge_cli.policy import sha256_bytes
from . import _engine_final_mode
from . import _engine_gate
from . import _engine_lifecycle
from . import _engine_review_request
from . import _engine_review_verdict
from . import _engine_refresh
from . import _engine_start_chain
from . import _engine_bootstrap
from . import _engine_release_aborted
from . import _engine_abort
from . import _engine_release_pending
from . import _engine_cleanup_child
from . import _engine_cleanup
from . import _engine_observation
from . import _engine_lock
from . import _engine_observe_remote
from . import _engine_epoch_fetch
from . import _engine_epoch_ancestry


class MergeEngine:
    """Dormant merge-family target for explicit shared CLI verbs."""

    def __init__(self, ctx: chain_core.CommandContext) -> None:
        self.ctx = ctx
        self._git_no_lazy_fetch_qualification: (
            engine._GitNoLazyFetchQualification | None
        ) = None
    _final_mode_unavailable = staticmethod(_engine_final_mode._final_mode_unavailable)
    _prepare_git_no_lazy_fetch_qualification = _engine_final_mode._prepare_git_no_lazy_fetch_qualification
    _prepare_bootstrap_git_no_lazy_fetch_qualification = _engine_final_mode._prepare_bootstrap_git_no_lazy_fetch_qualification
    _recover_can_reach_final_mode = classmethod(_engine_final_mode._recover_can_reach_final_mode)

    @property
    def store(self) -> chain_core.MergeChainStore:
        if not isinstance(self.ctx.store, chain_core.MergeChainStore):
            raise FrozenError(
                "merge routing lacks the merge-family store",
                chain_id=self.ctx.options.chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        return self.ctx.store

    def _load(self) -> dict[str, Any]:
        if self.ctx.options.run_id is not None:
            raise chain_core._merge_refusal(
                V2ReasonCode.RUN_TASK_BINDING_INVALID,
                "forge: merge transition refused — later verbs inherit the immutable run/task binding",
                expected="no --run-id or --task after merge start",
                observed=self.ctx.options.run_id,
                remediation="retry with only the recorded --chain-id",
            )
        chain_id = self.ctx.options.chain_id
        if chain_id is None:
            raise Refusal(
                ReasonCode.STATE_PRECONDITION,
                "forge: merge shared verb refused — explicit --chain-id is required",
                remediation="forge status --chain-id <id>",
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        state = self.store.load(chain_id)
        if state.get("journal_outbox") is not None:
            state = self.store.recover_pending_outbox(chain_id)
        return state
    _read_only_recovery_flag_state = _engine_final_mode._read_only_recovery_flag_state

    def _halt(self, state: Mapping[str, Any]) -> None:
        chain_core._require_merge_adapter_control("halt")
        worktree = state.get("worktree")
        candidate_root = (
            Path(str(worktree["path"]))
            if isinstance(worktree, Mapping)
            and isinstance(worktree.get("path"), str)
            and Path(str(worktree["path"])).exists()
            else self.ctx.repo.root
        )
        engine._run_halt(
            self.ctx,
            state,
            scope="merge",
            cwd=candidate_root,
        )
    _record_common_release_failure = _engine_lock._record_common_release_failure
    _recording_common_lock = contextlib.contextmanager(_engine_lock._recording_common_lock)
    _candidate_observation_transition = _engine_observation._candidate_observation_transition
    _restore_candidate_observation_intent_locked = _engine_observation._restore_candidate_observation_intent_locked
    _restore_bootstrap_fetch_observation_locked = _engine_observation._restore_bootstrap_fetch_observation_locked
    _run_candidate_observation_locked = _engine_observation._run_candidate_observation_locked
    start = _engine_lifecycle.start
    bind_candidate = _engine_lifecycle.bind_candidate
    _preflight_lifecycle = _engine_lifecycle._preflight_lifecycle
    _claim_slot = _engine_start_chain._claim_slot
    _allocate_chain_id = _engine_start_chain._allocate_chain_id
    _initial_merge_state = _engine_start_chain._initial_merge_state
    _record_bootstrap_failure = _engine_start_chain._record_bootstrap_failure
    _bootstrap_fetch_argv = staticmethod(_engine_bootstrap._bootstrap_fetch_argv)
    _resolved_fetch_tip = staticmethod(_engine_bootstrap._resolved_fetch_tip)

    def _recover_merge_bootstrap_scope_binding(
        self,
        state: Mapping[str, Any],
        admission: engine.MergeAdmission,
        *,
        fence: chain_core.PublishedLockRecord | None = None,
    ) -> dict[str, Any] | None:
        """Resume a crashed run-bound sidecar without resolving a tip again.

        ``None`` is the exact both-names-absent pre-publication result.  When
        common-lock recovery already cleared the dead fence, its complete
        identity is recovered from the immutable sidecar's
        ``retained_inflight`` member.
        """

        chain_core._require_merge_integration_control("scope-sidecar-recovery")
        fetch_intent_digest = engine._merge_event_digest(
            self.store, str(state["chain_id"]), "fetch_intent"
        )
        if fetch_intent_digest is None:
            raise FrozenError(
                "merge bootstrap fetch intent digest is unavailable",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        intent = state.get("integration", {}).get("intent")
        scope_request = (
            intent.get("scope_request") if isinstance(intent, Mapping) else None
        )
        expected_request = engine._merge_scope_request(admission)
        if (
            (scope_request is not None and not isinstance(scope_request, Mapping))
            or (
                dict(scope_request)
                if isinstance(scope_request, Mapping)
                else None
            )
            != expected_request
        ):
            raise FrozenError(
                "merge bootstrap scope request diverges from admission",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        selected_fence = fence or engine._discover_merge_scope_fence_from_sidecar(
            self.store,
            state,
            fetch_intent_digest=fetch_intent_digest,
        )
        if selected_fence is None:
            return None
        return engine._resume_merge_scope_binding(
            self.store,
            state,
            fetch_intent_digest=fetch_intent_digest,
            scope_request=scope_request,
            fence=selected_fence,
        )
    _run_bootstrap_generation_composite = _engine_bootstrap._run_bootstrap_generation_composite
    _run_bootstrap_generation = _engine_bootstrap._run_bootstrap_generation
    _complete_bootstrap_classification = _engine_start_chain._complete_bootstrap_classification
    start_chain = _engine_start_chain.start_chain
    _admission_from_candidate_observation = _engine_refresh._admission_from_candidate_observation
    _admission_for_refresh = _engine_refresh._admission_for_refresh
    _refresh_iteration = _engine_refresh._refresh_iteration
    refresh = _engine_refresh.refresh
    approve = _engine_lifecycle.approve
    _release_to_aborted = _engine_release_aborted._release_to_aborted
    _release_to_aborted_locked = _engine_release_aborted._release_to_aborted_locked
    _release_scope_exceeded = _engine_release_aborted._release_scope_exceeded
    abort = _engine_abort.abort
    status = _engine_lifecycle.status

    @staticmethod
    def _wrong_state(
        state: Mapping[str, Any], expected: str, verb: str
    ) -> None:
        raise chain_core._merge_refusal(
            V2ReasonCode.STATE_PRECONDITION,
            f"forge: {verb} refused — merge transition is not admitted",
            expected=expected,
            observed=str(state.get("state")),
            remediation=f"forge status --chain-id {state['chain_id']}",
            chain=state,
        )
    _resolve_gate = _engine_gate._resolve_gate
    _run_scoped_mutation = _engine_gate._run_scoped_mutation
    _record_gate_result = _engine_gate._record_gate_result
    gate_run = _engine_gate.gate_run
    verify = _engine_gate.verify
    _review_package = _engine_review_request._review_package
    review_request = _engine_review_request.review_request
    review_collect = _engine_review_request.review_collect
    review_attach = _engine_review_verdict.review_attach
    review_disposition = _engine_review_verdict.review_disposition

    def _epoch_transition(
        self,
        state: dict[str, Any],
        lease: chain_core.ChainLease,
        event_name: str,
        payload: Mapping[str, Any],
        *,
        generation_digest: str | None = None,
        at: str | None = None,
    ) -> dict[str, Any]:
        generation = state.get("candidate")
        selected = (
            generation_digest
            if generation_digest is not None
            else str(generation["generation_digest"])
            if isinstance(generation, Mapping)
            else None
        )
        return self.store.transition_locked(
            state,
            event_name,
            payload,
            generation_digest=selected,
            lease=lease,
            at=at or chain_core.iso_z(),
        )

    def _tail_event_digest(
        self, state: Mapping[str, Any], event_name: str
    ) -> str:
        digest = engine._merge_event_digest(
            self.store, str(state["chain_id"]), event_name
        )
        if digest is None:
            raise FrozenError(
                f"merge {event_name} event digest is unavailable",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        return digest
    _sealed_plan = staticmethod(_engine_epoch_fetch._sealed_plan)
    _begin_epoch = _engine_epoch_fetch._begin_epoch
    _epoch_fetch_argv = staticmethod(_engine_epoch_fetch._epoch_fetch_argv)
    _epoch_replay_context = _engine_epoch_ancestry._epoch_replay_context
    _resolved_epoch_fetch_tip = staticmethod(_engine_epoch_fetch._resolved_epoch_fetch_tip)
    _run_carried_successor_ancestry = _engine_epoch_ancestry._run_carried_successor_ancestry
    _run_epoch_fetch = _engine_epoch_fetch._run_epoch_fetch
    _complete_epoch_fetch_locked = _engine_epoch_fetch._complete_epoch_fetch_locked

    def _run_epoch_rebase(
        self,
        state: dict[str, Any],
        fetched_tip: str,
        lock: chain_core.CommonRebaseLock,
        lease: chain_core.ChainLease,
        budget: engine._MergeEpochBudget,
    ) -> dict[str, Any]:
        engine._require_active_merge_epoch(state)
        budget.consume("rebases")
        pre_head = str(state["candidate"]["candidate_head"])
        integration = copy.deepcopy(state["integration"])
        epoch = integration["epoch"]
        reflog_action = (
            f"forge-merge-rebase:{state['chain_id']}:"
            f"{state['candidate']['generation_digest']}:"
            f"{epoch['operation_nonce']}"
        )
        integration.update(
            {
                "pre_rebase": {
                    "head": pre_head,
                    "fetched_tip": fetched_tip,
                    "generation_digest": state["candidate"]["generation_digest"],
                    "recorded_at": chain_core.iso_z(),
                },
                "conflict": None,
                "intent": {
                    "operation": "rebase",
                    "operation_nonce": epoch["operation_nonce"],
                    "pre_operation_head": pre_head,
                    "fetched_tip": fetched_tip,
                    "branch": state["branch"],
                    "generation_digest": state["candidate"]["generation_digest"],
                    "reflog_action": reflog_action,
                    "started_at": chain_core.iso_z(),
                },
            }
        )
        state = self._epoch_transition(
            state, lease, "rebase_intent", {"delta": {"integration": integration}}
        )
        intent_digest = self._tail_event_digest(state, "rebase_intent")

        def intent_current() -> bool:
            return self._tail_event_digest(state, "rebase_intent") == intent_digest

        def persist(result: chain_core.FencedProcessResult) -> None:
            nonlocal state
            succeeded = bool(
                result.returncode == 0
                and not result.launch_failed
                and not result.timed_out
                and not result.output_limit
                and not result.group_survived
            )
            result_integration = copy.deepcopy(state["integration"])
            result_integration["intent"] = {
                "operation": "rebase-result",
                "operation_nonce": epoch["operation_nonce"],
                "result": "success" if succeeded else "failed",
                "pre_operation_head": pre_head,
                "fetched_tip": fetched_tip,
                "branch": state["branch"],
                "generation_digest": state["candidate"]["generation_digest"],
                "reflog_action": reflog_action,
                "exit": result.returncode,
                "inflight_digest": result.fence_digest,
                "output_digest": result.output_digest,
                "launch_failed": result.launch_failed,
                "timed_out": result.timed_out,
                "output_limit_exceeded": result.output_limit,
                "group_survived": result.group_survived,
                "recorded_at": chain_core.iso_z(),
            }
            state = self._epoch_transition(
                state,
                lease,
                "rebase_result",
                {"delta": {"integration": result_integration}},
            )

        environment = os.environ.copy()
        environment.pop("FORGE_SESSION_PID", None)
        environment.update(
            {
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_NO_LAZY_FETCH": "1",
                "GIT_REFLOG_ACTION": reflog_action,
            }
        )
        chain_core.run_fenced_command(
            lock,
            operation="rebase",
            intent_digest=intent_digest,
            intent_validator=intent_current,
            argv=[
                "git",
                "--no-pager",
                "-C",
                str(state["worktree"]["path"]),
                "rebase",
                fetched_tip,
            ],
            cwd=Path(str(state["worktree"]["path"])),
            persist_result=persist,
            env=environment,
            timeout=runtime.COMMAND_TIMEOUT_SECONDS,
            cap=runtime.OUTPUT_CAP_BYTES,
            verbose=self.ctx.options.verbose,
        )
        state = self._recover_rebase_observation_locked(state, lock, lease)
        if state["state"] == "rebase_conflict":
            raise chain_core._merge_refusal(
                V2ReasonCode.REBASE_CONFLICT,
                "forge: merge finalize refused — integration has a recoverable rebase conflict",
                remediation=(
                    f"forge merge recover --continue --paths <path>... --chain-id {state['chain_id']}"
                ),
                chain=state,
            )
        if (
            state["state"] == "revising"
            and state.get("integration", {}).get("condition") == "rebase-failed"
        ):
            raise chain_core._merge_refusal(
                V2ReasonCode.REBASE_FAILED,
                "forge: merge finalize refused — integration rebase failed",
                remediation=f"forge merge refresh --chain-id {state['chain_id']}",
                chain=state,
            )
        if state.get("integration", {}).get("condition") == "foreign-git-state":
            if engine._merge_rebase_result_failed(state):
                raise chain_core._merge_refusal(
                    V2ReasonCode.REBASE_FAILED,
                    "forge: merge finalize refused — integration rebase failed",
                    observed="foreign-git-state",
                    remediation=f"forge status --chain-id {state['chain_id']}",
                    chain=state,
                )
            raise chain_core._merge_refusal(
                V2ReasonCode.STATE_PRECONDITION,
                "forge: merge finalize refused — rebase result is not attributable to the recorded intent",
                observed="foreign-git-state",
                remediation=f"forge status --chain-id {state['chain_id']}",
                chain=state,
            )
        if state["state"] != "reverifying":
            raise FrozenError(
                "merge rebase produced no authenticated successor generation",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        return state

    def _run_epoch_suite(
        self,
        state: dict[str, Any],
        lock: chain_core.CommonRebaseLock,
        lease: chain_core.ChainLease,
        budget: engine._MergeEpochBudget,
    ) -> dict[str, Any]:
        engine._require_active_merge_epoch(state)
        plan = state.get("integration", {}).get("epoch", {}).get("gate_plan")
        if not isinstance(plan, Mapping) or plan.get("status") != "sealed":
            raise FrozenError(
                "merge epoch gate plan is not sealed",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        if int(plan["cursor"]) >= len(plan["suite"]):
            return state
        budget.consume("suites")
        state, candidate_observation = self._run_candidate_observation_locked(
            state,
            lock,
            lease,
            verb="merge finalize",
            remote_tip=str(state["candidate"]["remote_tip"]),
            expected_head=str(state["candidate"]["candidate_head"]),
            classify=False,
        )
        repository, policy, changed_paths = _observe_current_merge_candidate(
            self.ctx,
            state,
            verb="merge finalize",
            observation=candidate_observation,
        )
        expected = engine._merge_epoch_suite(state, policy)
        if expected != plan["suite"] or sha256_bytes(
            chain_core.canonical_bytes(expected)
        ) != plan["suite_digest"]:
            raise FrozenError(
                "merge epoch gate plan diverges from committed policy",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        while True:
            engine._require_active_merge_epoch(state)
            plan = state["integration"]["epoch"]["gate_plan"]
            cursor = int(plan["cursor"])
            if cursor >= len(plan["suite"]):
                return state
            member = plan["suite"][cursor]
            gate_id = str(member["id"])
            authorizing_digest = (
                str(plan["seal_event_digest"])
                if cursor == 0
                else self._tail_event_digest(state, "gate_recorded")
            )
            intent_digest = chain_core.merge_gate_intent_digest(
                chain_id=str(state["chain_id"]),
                epoch_intent_digest=str(state["integration"]["epoch"]["intent_digest"]),
                seal_event_digest=str(plan["seal_event_digest"]),
                generation_digest=str(plan["generation_digest"]),
                policy_digest=str(plan["policy_digest"]),
                suite_digest=str(plan["suite_digest"]),
                cursor=cursor,
                kind=str(member["kind"]),
                gate_id=gate_id,
                authorizing_event_digest=authorizing_digest,
            )
            mutation_result_transform: (
                Callable[
                    [chain_core.FencedProcessResult],
                    chain_core.FencedProcessResult,
                ]
                | None
            ) = None
            if member["kind"] == "scoped-mutation":
                argv = [
                    sys.executable,
                    str(self.ctx.helper("run-scoped-mutation.py")),
                    "--base",
                    str(state["candidate"]["remote_tip"]),
                    "--head",
                    str(state["candidate"]["candidate_head"]),
                ]
                bound = engine._merge_run_directory(state)
                if bound is not None:
                    bound_repository, _run_dir = bound
                    bound_run_id = str(state["run_binding"]["run_id"])
                    bound_task = str(state["run_binding"]["task_id"])
                    candidate_base = str(state["candidate"]["remote_tip"])
                    candidate_head = str(state["candidate"]["candidate_head"])
                    argv.extend(
                        [
                            "--repository",
                            str(bound_repository),
                            "--run-id",
                            bound_run_id,
                            "--task",
                            bound_task,
                            "--defer-journal",
                        ]
                    )
                    mutation_result_transform = lambda result: (
                        _persist_deferred_mutation_result(
                            result,
                            repository=bound_repository,
                            run_id=bound_run_id,
                            task=bound_task,
                            base=candidate_base,
                            head=candidate_head,
                        )
                    )
                details: dict[str, Any] = {"kind": "scoped-mutation"}
            else:
                argv, remaining, details = self._resolve_gate(
                    state, policy, changed_paths, gate_id
                )
                if gate_id.startswith("stack:"):
                    commands = [argv, *(
                        ["bash", "-c", cell, "forge", *changed_paths]
                        for cell in remaining
                    )]
                    cell_index = 1 + sum(
                        1
                        for prior_member in plan["suite"][:cursor]
                        if prior_member == member
                    )
                    if cell_index > len(commands):
                        raise FrozenError(
                            "stack cursor exceeds its committed command cells",
                            chain_id=str(state["chain_id"]),
                            observed=gate_id,
                            schema=REVISION9_OUTPUT_SCHEMA,
                        )
                    argv = commands[cell_index - 1]
                    details.update(
                        {
                            "batch_id": sha256_bytes(
                                chain_core.canonical_bytes(
                                    {
                                        "epoch": state["integration"]["epoch"][
                                            "intent_digest"
                                        ],
                                        "suite": plan["suite_digest"],
                                        "gate": gate_id,
                                    }
                                )
                            )[:16],
                            "cell_count": len(commands),
                            "cell_index": cell_index,
                        }
                    )
            holder: dict[str, Any] = {}

            def intent_current() -> bool:
                try:
                    fresh = self.store.load_locked(str(state["chain_id"]), lease=lease)
                    current_plan = fresh["integration"]["epoch"]["gate_plan"]
                    return bool(
                        current_plan == state["integration"]["epoch"]["gate_plan"]
                        and int(current_plan["cursor"]) == cursor
                    )
                except (KeyError, FrozenError, OSError, TypeError):
                    return False

            def persist(result: chain_core.FencedProcessResult) -> None:
                nonlocal state
                passed = bool(
                    result.returncode == 0
                    and not result.launch_failed
                    and not result.timed_out
                    and not result.output_limit
                    and not result.group_survived
                )
                transcript = engine._write_merge_artifact(
                    self.ctx,
                    state,
                    (
                        "evidence/epoch-"
                        f"{state['integration']['epoch']['operation_nonce']}-"
                        f"{cursor:02d}-{re.sub(r'[^A-Za-z0-9_.-]+', '-', gate_id)}.log"
                    ),
                    result.output,
                )
                fact = {
                    "result": (
                        "passed"
                        if passed
                        else "inconclusive"
                        if member["kind"] == "scoped-mutation"
                        else "failed"
                    ),
                    "generation_digest": state["candidate"]["generation_digest"],
                    "criterion": (
                        "mutation: scoped"
                        if member["kind"] == "scoped-mutation"
                        else f"gate-1: {gate_id}"
                        if gate_id == "gate-1"
                        else f"gate-2: {gate_id}"
                    ),
                    "command_argv": list(argv),
                    "exit_code": result.returncode,
                    "duration_seconds": round(result.duration_seconds, 6),
                    "stdout_stderr_digest": result.output_digest,
                    "timed_out": result.timed_out,
                    "output_limit": result.output_limit,
                    "launch_failed": result.launch_failed,
                    "transcript": transcript,
                    "gate_plan_position": {
                        "seal_event_digest": plan["seal_event_digest"],
                        "suite_digest": plan["suite_digest"],
                        "cursor": cursor,
                        "kind": member["kind"],
                        "id": gate_id,
                    },
                    "gate_intent_digest": intent_digest,
                    "inflight_digest": result.fence_digest,
                    **copy.deepcopy(details),
                }
                steps = copy.deepcopy(state["steps"])
                runs = copy.deepcopy(steps.get(gate_id, []))
                if not isinstance(runs, list):
                    runs = []
                runs.append(fact)
                steps[gate_id] = runs
                integration = copy.deepcopy(state["integration"])
                integration["epoch"]["gate_plan"]["cursor"] = cursor + 1
                delta: dict[str, Any] = {
                    "steps": steps,
                    "integration": integration,
                }
                if not passed and member["kind"] == "gate":
                    engine._reset_merge_nonmovement_counter(integration)
                    delta["state"] = "reverification_failed"
                state = self._epoch_transition(
                    state,
                    lease,
                    "gate_recorded",
                    {"delta": delta},
                )
                holder["passed"] = passed or member["kind"] == "scoped-mutation"

            environment = os.environ.copy()
            if mutation_result_transform is None:
                environment.pop("FORGE_SESSION_PID", None)
            transform_options = (
                {"result_transform": mutation_result_transform}
                if mutation_result_transform is not None
                else {}
            )
            chain_core.run_fenced_command(
                lock,
                operation="gate",
                intent_digest=intent_digest,
                intent_validator=intent_current,
                argv=argv,
                cwd=repository.root,
                persist_result=persist,
                env=environment,
                timeout=runtime.COMMAND_TIMEOUT_SECONDS,
                cap=runtime.OUTPUT_CAP_BYTES,
                verbose=self.ctx.options.verbose,
                **transform_options,
            )
            try:
                state, candidate_observation = (
                    self._run_candidate_observation_locked(
                        state,
                        lock,
                        lease,
                        verb="merge finalize",
                        remote_tip=str(state["candidate"]["remote_tip"]),
                        expected_head=str(state["candidate"]["candidate_head"]),
                        classify=False,
                    )
                )
                _observe_current_merge_candidate(
                    self.ctx,
                    state,
                    verb="merge finalize",
                    observation=candidate_observation,
                )
            except Refusal as exc:
                if exc.reason_code == V2ReasonCode.CANDIDATE_STALE:
                    observed_outputs = engine._merge_candidate_observation_outputs(
                        state, candidate_observation
                    )
                    observed_head = ""
                    if observed_outputs is not None:
                        try:
                            observed_head = (
                                observed_outputs["identity"]
                                .decode("utf-8")
                                .splitlines()[-1]
                            )
                        except (IndexError, UnicodeDecodeError):
                            observed_head = ""
                    state, refreshed_observation = (
                        self._run_candidate_observation_locked(
                            state,
                            lock,
                            lease,
                            verb="merge finalize",
                            remote_tip=str(state["candidate"]["remote_tip"]),
                            expected_head=observed_head,
                            classify=True,
                        )
                    )
                    admission = self._admission_from_candidate_observation(
                        state,
                        refreshed_observation,
                        verb="merge finalize",
                        require_current_generation=False,
                    )
                    generation = engine.bind_merge_candidate_generation(
                        self.ctx,
                        admission,
                        str(state["candidate"]["remote_tip"]),
                        generation=int(state["candidate"]["generation"]) + 1,
                        observation=refreshed_observation,
                    )
                    integration = copy.deepcopy(state["integration"])
                    engine._reset_merge_nonmovement_counter(integration)
                    integration.update(
                        {
                            "condition": "none",
                            "primary_condition": "none",
                            "epoch": None,
                        }
                    )
                    review = state.get("review")
                    iteration = (
                        review.get("iteration")
                        if isinstance(review, Mapping)
                        else None
                    )
                    retained_review = (
                        {"iteration": iteration}
                        if type(iteration) is int
                        else {}
                    )
                    state = self._epoch_transition(
                        state,
                        lease,
                        "generation_refreshed",
                        {
                            "delta": {
                                "state": "verifying",
                                "policy_source": {
                                    "commit": admission.policy.sha,
                                    "digest": admission.policy.digest,
                                },
                                "candidate": copy.deepcopy(
                                    generation.candidate
                                ),
                                "tier": copy.deepcopy(generation.tier),
                                "integration": integration,
                                "steps": {},
                                "review": retained_review,
                                "approval": {},
                                "authorization": {},
                            }
                        },
                        generation_digest=str(
                            generation.candidate["generation_digest"]
                        ),
                    )
                    exc.chain = state
                    exc.remediation = (
                        f"forge merge refresh --chain-id {state['chain_id']}"
                    )
                    exc.next_required_step = exc.remediation
                raise
            if not holder.get("passed"):
                raise chain_core._merge_refusal(
                    V2ReasonCode.MERGE_GATE_FAILED,
                    f"forge: merge gate failed — {gate_id}",
                    remediation=f"forge merge recover --chain-id {state['chain_id']}",
                    chain=state,
                    evidence_refs=[
                        str(state["steps"][gate_id][-1]["transcript"])
                    ],
                )
    _parse_remote_observation = staticmethod(_engine_observation._parse_remote_observation)
    _parse_fetched_remote_observation = staticmethod(_engine_observation._parse_fetched_remote_observation)
    _head_contained = staticmethod(_engine_observation._head_contained)
    _run_remote_observation = _engine_observe_remote._run_remote_observation

    @staticmethod
    def _push_classification(
        result: chain_core.FencedProcessResult, destination_ref: str
    ) -> str:
        if (
            result.launch_failed
            or result.timed_out
            or result.output_limit
            or result.group_survived
            or result.returncode is None
        ):
            return "outcome-unknown"
        if result.returncode == 0:
            return "success"
        try:
            decoded = result.output.decode("utf-8")
        except UnicodeDecodeError:
            return "known-failure"
        target_rows: list[tuple[str, str]] = []
        for row in decoded.splitlines():
            fields = row.split("\t")
            if len(fields) != 3 or ":" not in fields[1]:
                continue
            _source, destination = fields[1].rsplit(":", 1)
            if destination == destination_ref:
                target_rows.append((fields[0], fields[2]))
        if len(target_rows) == 1 and target_rows[0] in {
            ("!", "[rejected] (non-fast-forward)"),
            ("!", "[rejected] (fetch first)"),
        }:
            return "non-fast-forward"
        return "known-failure"
    _final_history_mutation_mode = _engine_final_mode._final_history_mutation_mode
    _park_invalid_final_history_mode = _engine_final_mode._park_invalid_final_history_mode

    def _run_epoch_push(
        self,
        state: dict[str, Any],
        lock: chain_core.CommonRebaseLock,
        lease: chain_core.ChainLease,
        budget: engine._MergeEpochBudget,
        *,
        retry: bool = False,
    ) -> dict[str, Any]:
        engine._require_active_merge_epoch(state)
        plan = state["integration"]["epoch"]["gate_plan"]
        if plan.get("status") != "sealed" or plan.get("cursor") != len(
            plan.get("suite", [])
        ):
            raise FrozenError(
                "merge push intent precedes completion of its sealed gate plan",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        if retry:
            chain_core._require_merge_integration_control("push-retry")
            prior_result = state.get("integration", {}).get("push", {}).get(
                "result"
            )
            if (
                state.get("state") != "pushing"
                or engine._merge_inactive(state)
                or not (
                    prior_result is None or isinstance(prior_result, Mapping)
                )
                or not chain_core._merge_old_tip_all_false(state)
                or not self._current_merge_authority(state)
            ):
                raise FrozenError(
                    "merge duplicate push lacks an active authorized old-tip observation",
                    chain_id=str(state["chain_id"]),
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
        state, candidate_observation = self._run_candidate_observation_locked(
            state,
            lock,
            lease,
            verb="merge finalize",
            remote_tip=str(state["candidate"]["remote_tip"]),
            expected_head=str(state["candidate"]["candidate_head"]),
            classify=False,
        )
        _observe_current_merge_candidate(
            self.ctx,
            state,
            verb="merge finalize",
            observation=candidate_observation,
        )
        mode, manifest_digest = self._final_history_mutation_mode(state, lock)
        if mode is None:
            state = self._park_invalid_final_history_mode(
                state,
                lease,
                manifest_digest=manifest_digest,
            )
            raise chain_core._merge_refusal(
                V2ReasonCode.STATE_PRECONDITION,
                "forge: history mutation mode invalid — repair committed .forge-manifest through Forge CLI",
                remediation=(
                    "repair committed .forge-manifest through Forge CLI, then "
                    f"forge merge refresh --chain-id {state['chain_id']}"
                ),
                chain=state,
            )
        budget.consume("pushes")
        candidate = state["candidate"]
        integration = copy.deepcopy(state["integration"])
        epoch = integration["epoch"]
        prior_push = integration.get("push")
        attempted = (
            list(prior_push.get("attempted_heads", []))
            if isinstance(prior_push, Mapping)
            else []
        )
        attempted.append(str(candidate["candidate_head"]))
        intended_at = chain_core.iso_z()
        engine._reset_merge_nonmovement_counter(integration)
        integration.update(
            {
                "condition": "none",
                "primary_condition": "none",
                "intent": {
                    "operation": "push",
                    "operation_nonce": epoch["operation_nonce"],
                    "attempt": len(attempted),
                },
                "observed": None,
                "push": {
                    "expected_old_tip": candidate["remote_tip"],
                    "intended_head": candidate["candidate_head"],
                    "destination_ref": candidate["destination_ref"],
                    "intended_at": intended_at,
                    "result": None,
                    "attempted_heads": attempted,
                    "landed_head": (
                        prior_push.get("landed_head")
                        if isinstance(prior_push, Mapping)
                        else None
                    ),
                },
            }
        )
        push_delta: dict[str, Any] = {"integration": integration}
        if state["state"] != "pushing":
            push_delta["state"] = "pushing"
        state = self._epoch_transition(
            state,
            lease,
            "push_intent",
            {"delta": push_delta},
            at=intended_at,
        )
        intent_digest = self._tail_event_digest(state, "push_intent")

        def intent_current() -> bool:
            return self._tail_event_digest(state, "push_intent") == intent_digest

        def persist(result: chain_core.FencedProcessResult) -> None:
            nonlocal state
            next_integration = copy.deepcopy(state["integration"])
            next_push = copy.deepcopy(next_integration["push"])
            next_push["result"] = {
                "classification": self._push_classification(
                    result, str(next_push["destination_ref"])
                ),
                "exit": result.returncode,
                "inflight_digest": result.fence_digest,
                "output_digest": result.output_digest,
                "launch_failed": result.launch_failed,
                "timed_out": result.timed_out,
                "output_limit_exceeded": result.output_limit,
                "recorded_at": chain_core.iso_z(),
            }
            next_integration["push"] = next_push
            state = self._epoch_transition(
                state,
                lease,
                "condition_recorded",
                {"delta": {"integration": next_integration}},
            )

        environment = os.environ.copy()
        environment.pop("FORGE_SESSION_PID", None)
        environment.update(
            {
                "LC_ALL": "C",
                "LANG": "C",
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_NO_LAZY_FETCH": "1",
            }
        )
        chain_core.run_fenced_command(
            lock,
            operation="push",
            intent_digest=intent_digest,
            intent_validator=intent_current,
            argv=[
                "git",
                "--no-pager",
                "-C",
                str(state["worktree"]["path"]),
                "push",
                "--porcelain",
                "origin",
                (
                    f"{candidate['candidate_head']}:"
                    f"{candidate['destination_ref']}"
                ),
            ],
            cwd=Path(str(state["worktree"]["path"])),
            persist_result=persist,
            env=environment,
            timeout=runtime.COMMAND_TIMEOUT_SECONDS,
            cap=runtime.OUTPUT_CAP_BYTES,
            verbose=self.ctx.options.verbose,
        )
        state = self._run_remote_observation(
            state,
            lock,
            lease,
            budget,
            phase="post-push",
        )
        if state["state"] == "pushing":
            condition = state["integration"]["condition"]
            classification = state["integration"].get("push", {}).get(
                "result", {}
            ).get("classification")
            if chain_core._merge_old_tip_all_false(state):
                if classification != "known-failure":
                    return state
                condition = "push-failed"
            reason = (
                V2ReasonCode.PUSH_OUTCOME_UNKNOWN
                if condition == "push-outcome-unknown"
                else V2ReasonCode.PUSH_FAILED
            )
            raise chain_core._merge_refusal(
                reason,
                (
                    "forge: merge push outcome cannot be observed authoritatively"
                    if reason == V2ReasonCode.PUSH_OUTCOME_UNKNOWN
                    else "forge: merge push failed"
                ),
                remediation=f"forge merge recover --chain-id {state['chain_id']}",
                chain=state,
            )
        return state

    def _park_integrated_review(
        self, state: dict[str, Any], lease: chain_core.ChainLease
    ) -> dict[str, Any]:
        integration = copy.deepcopy(state["integration"])
        engine._reset_merge_nonmovement_counter(integration)
        integration["epoch"] = None
        integration["condition"] = "none"
        integration["primary_condition"] = "none"
        prior_review = state.get("review")
        iteration = (
            prior_review.get("iteration")
            if isinstance(prior_review, Mapping)
            else None
        )
        retained_review = {"iteration": iteration} if type(iteration) is int else {}
        projection = {
            "state": "reviewing",
            "integration": integration,
            "review": retained_review,
            "approval": {},
            "authorization": {},
        }
        return self._epoch_transition(
            state,
            lease,
            "reverification_result",
            {
                "delta": {
                    name: value
                    for name, value in projection.items()
                    if state.get(name) != value
                }
            },
        )
    _release_to_closed_locked = _engine_cleanup_child._release_to_closed_locked
    _cleanup_result_locked = _engine_cleanup_child._cleanup_result_locked
    _run_cleanup_child = _engine_cleanup_child._run_cleanup_child
    _current_merge_authority = staticmethod(_engine_final_mode._current_merge_authority)
    _complete_pending_release_locked = _engine_release_pending._complete_pending_release_locked
    _resume_pending_release = _engine_release_pending._resume_pending_release
    _attempted_release_preconditions_locked = _engine_abort._attempted_release_preconditions_locked
    _release_historical_landing_locked = _engine_release_pending._release_historical_landing_locked

    def _record_foreign_git_locked(
        self, state: dict[str, Any], lease: chain_core.ChainLease
    ) -> dict[str, Any]:
        integration = state.get("integration")
        if not isinstance(integration, Mapping):
            raise FrozenError(
                "merge integration projection is malformed",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        if integration.get("condition") == "foreign-git-state":
            return state
        updated = copy.deepcopy(dict(integration))
        updated.update(
            {"condition": "foreign-git-state", "primary_condition": "none"}
        )
        engine._reset_merge_nonmovement_counter(updated)
        return self._epoch_transition(
            state,
            lease,
            "condition_recorded",
            {"delta": {"integration": updated}},
        )

    def _restore_integrated_rebase_observation_intent_locked(
        self, state: dict[str, Any], lease: chain_core.ChainLease
    ) -> tuple[dict[str, Any], Mapping[str, Any] | None]:
        """Restore the raw rebase fact after a crash in a read-only proof leg."""

        integration = state.get("integration")
        current_intent = (
            integration.get("intent") if isinstance(integration, Mapping) else None
        )
        phase = (
            current_intent.get("phase")
            if isinstance(current_intent, Mapping)
            else None
        )
        prefix = "forge-integrated-observation:"
        if not isinstance(phase, str) or not phase.startswith(prefix):
            return state, current_intent if isinstance(current_intent, Mapping) else None
        source_intent = current_intent.get("source_intent")
        parts = phase.split(":")
        if (
            len(parts) != 3
            or parts[0] != "forge-integrated-observation"
            or parts[1] not in {"branch", "head", "status", "ancestry"}
            or parts[2] not in {"intent", "result"}
            or current_intent.get("observation_step") != parts[1]
            or not isinstance(source_intent, Mapping)
        ):
            return state, None
        source_state = copy.deepcopy(state)
        source_state["integration"]["intent"] = copy.deepcopy(dict(source_intent))
        binding = engine._merge_rebase_integrated_observation_binding(
            source_state, source_intent
        )
        pre_rebase = source_state["integration"].get("pre_rebase")
        epoch = source_state["integration"].get("epoch")
        if (
            binding is None
            or not isinstance(pre_rebase, Mapping)
            or not isinstance(epoch, Mapping)
            or current_intent.get("operation") != "rebase"
            or current_intent.get("operation_nonce") != epoch.get("operation_nonce")
            or current_intent.get("pre_operation_head") != pre_rebase.get("head")
            or current_intent.get("fetched_tip") != pre_rebase.get("fetched_tip")
            or current_intent.get("branch") != source_state.get("branch")
            or current_intent.get("generation_digest")
            != pre_rebase.get("generation_digest")
            or current_intent.get("reflog_action")
            != chain_core._merge_rebase_action(source_state)
            or current_intent.get("observation_binding") != binding
        ):
            return state, None
        restored = copy.deepcopy(state["integration"])
        restored["intent"] = copy.deepcopy(dict(source_intent))
        state = self._epoch_transition(
            state,
            lease,
            "rebase_intent",
            {"delta": {"integration": restored}},
        )
        return state, source_intent

    def _run_integrated_rebase_observation_locked(
        self,
        state: dict[str, Any],
        lock: chain_core.CommonRebaseLock,
        lease: chain_core.ChainLease,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """Collect the integrated-result tuple through durable fenced reads."""

        chain_core._require_merge_integration_control("observation-first-recovery")
        state, source_intent = (
            self._restore_integrated_rebase_observation_intent_locked(state, lease)
        )
        integration = state.get("integration")
        pre_rebase = (
            integration.get("pre_rebase")
            if isinstance(integration, Mapping)
            else None
        )
        epoch = integration.get("epoch") if isinstance(integration, Mapping) else None
        action = chain_core._merge_rebase_action(state)
        if (
            not isinstance(source_intent, Mapping)
            or not isinstance(pre_rebase, Mapping)
            or not isinstance(epoch, Mapping)
            or action is None
        ):
            return state, None
        observation_binding = engine._merge_rebase_integrated_observation_binding(
            state, source_intent
        )
        if observation_binding is None:
            return state, None
        identity = {
            "operation_nonce": epoch.get("operation_nonce"),
            "pre_operation_head": pre_rebase.get("head"),
            "fetched_tip": pre_rebase.get("fetched_tip"),
            "branch": state.get("branch"),
            "generation_digest": pre_rebase.get("generation_digest"),
            "reflog_action": action,
        }
        worktree = Path(str(state["worktree"]["path"]))
        environment = engine._merge_scope_environment()
        environment.pop("FORGE_SESSION_PID", None)
        step_results: dict[str, dict[str, Any]] = {}
        output_digests: dict[str, str] = {}

        def restore_source() -> None:
            nonlocal state
            state, _restored = (
                self._restore_integrated_rebase_observation_intent_locked(
                    state, lease
                )
            )

        def run_step(
            name: str,
            argv: Sequence[str],
            *,
            allowed_exits: frozenset[int] = frozenset({0}),
        ) -> bytes | None:
            nonlocal state
            observation_intent = {
                "operation": "rebase",
                **identity,
                "phase": f"forge-integrated-observation:{name}:intent",
                "observation_binding": observation_binding,
                "observation_step": name,
                "prior_output_digests": copy.deepcopy(output_digests),
                "source_intent": copy.deepcopy(dict(source_intent)),
                "started_at": chain_core.iso_z(),
            }
            updated = copy.deepcopy(state["integration"])
            updated["intent"] = copy.deepcopy(observation_intent)
            state = self._epoch_transition(
                state,
                lease,
                "rebase_intent",
                {"delta": {"integration": updated}},
            )
            intent_digest = self._tail_event_digest(state, "rebase_intent")

            def intent_current() -> bool:
                try:
                    fresh = self.store.load_locked(
                        str(state["chain_id"]), lease=lease
                    )
                    return bool(
                        fresh.get("state") == state.get("state")
                        and fresh.get("integration", {}).get("condition") == "none"
                        and fresh.get("integration", {}).get("intent")
                        == observation_intent
                        and self._tail_event_digest(fresh, "rebase_intent")
                        == intent_digest
                    )
                except (FrozenError, KeyError, OSError, Refusal, ValueError):
                    return False

            def persist_observation(result: chain_core.FencedProcessResult) -> None:
                nonlocal state
                result_intent = {
                    **copy.deepcopy(observation_intent),
                    "phase": f"forge-integrated-observation:{name}:result",
                    "child_result": {
                        "authorized": result.authorized,
                        "exit": result.returncode,
                        "inflight_digest": result.fence_digest,
                        "output_digest": result.output_digest,
                        "launch_failed": result.launch_failed,
                        "timed_out": result.timed_out,
                        "output_limit_exceeded": result.output_limit,
                        "group_survived": result.group_survived,
                    },
                    "recorded_at": chain_core.iso_z(),
                }
                result_integration = copy.deepcopy(state["integration"])
                result_integration["intent"] = result_intent
                state = self._epoch_transition(
                    state,
                    lease,
                    "rebase_intent",
                    {"delta": {"integration": result_integration}},
                )

            result = chain_core.run_fenced_command(
                lock,
                operation="containment",
                intent_digest=intent_digest,
                intent_validator=intent_current,
                argv=argv,
                cwd=worktree,
                persist_result=persist_observation,
                env=environment,
                timeout=runtime.COMMAND_TIMEOUT_SECONDS,
                cap=runtime.OUTPUT_CAP_BYTES,
                verbose=self.ctx.options.verbose,
            )
            durable = state.get("integration", {}).get("intent", {}).get(
                "child_result"
            )
            if (
                not isinstance(durable, Mapping)
                or durable.get("authorized") is not True
                or durable.get("exit") not in allowed_exits
                or durable.get("launch_failed") is not False
                or durable.get("timed_out") is not False
                or durable.get("output_limit_exceeded") is not False
                or durable.get("group_survived") is not False
                or durable.get("inflight_digest") != result.fence_digest
                or durable.get("output_digest") != result.output_digest
                or result.returncode != durable.get("exit")
            ):
                restore_source()
                return None
            step_results[name] = {
                "intent_digest": intent_digest,
                "inflight_digest": result.fence_digest,
                "output_digest": result.output_digest,
                "exit": result.returncode,
            }
            output_digests[name] = result.output_digest
            return result.output

        branch_output = run_step(
            "branch", ["git", "--no-pager", "symbolic-ref", "-q", "HEAD"]
        )
        if branch_output is None:
            return state, None
        head_output = run_step(
            "head", ["git", "--no-pager", "rev-parse", "--verify", "HEAD"]
        )
        if head_output is None:
            return state, None
        try:
            observed_head = head_output.decode("ascii").removesuffix("\n")
        except UnicodeDecodeError:
            observed_head = ""
        if (
            chain_core.COMMIT_RE.fullmatch(observed_head) is None
            or head_output != f"{observed_head}\n".encode("ascii")
        ):
            restore_source()
            return state, None
        status_output = run_step(
            "status",
            [
                "git",
                "-c",
                "core.fsmonitor=false",
                "-c",
                "core.untrackedCache=false",
                "--no-optional-locks",
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
                "--ignore-submodules=none",
            ],
        )
        if status_output is None:
            return state, None
        ancestry_output = run_step(
            "ancestry",
            [
                "git",
                "--no-pager",
                "merge-base",
                "--is-ancestor",
                str(pre_rebase["fetched_tip"]),
                observed_head,
            ],
            allowed_exits=frozenset({0, 1}),
        )
        if ancestry_output is None:
            return state, None
        try:
            branch = branch_output.removesuffix(b"\n").decode("utf-8")
        except UnicodeDecodeError:
            branch = ""
        observation: dict[str, Any] = {
            "schema": "forge-merge-integrated-observation/1",
            "observation_binding": observation_binding,
            "operation_nonce": identity["operation_nonce"],
            "generation_digest": identity["generation_digest"],
            "pre_operation_head": identity["pre_operation_head"],
            "fetched_tip": identity["fetched_tip"],
            "branch": branch,
            "observed_head": observed_head,
            "status_digest": sha256_bytes(status_output),
            "status_empty": status_output == b"",
            "fetched_tip_ancestor": bool(
                step_results["ancestry"]["exit"] == 0 and ancestry_output == b""
            ),
            "steps": copy.deepcopy(step_results),
        }
        observation["evidence_digest"] = sha256_bytes(chain_core.canonical_bytes(observation))
        restore_source()
        return state, observation

    def _materialize_rebase_success_locked(
        self,
        state: dict[str, Any],
        lock: chain_core.CommonRebaseLock,
        lease: chain_core.ChainLease,
        *,
        fetched_tip: str,
        inflight_digest: str,
        output_digest: str,
        observation: Mapping[str, Any],
    ) -> dict[str, Any]:
        expected_head = str(observation.get("observed_head", ""))
        state, candidate_observation = self._run_candidate_observation_locked(
            state,
            lock,
            lease,
            verb="merge recover",
            remote_tip=fetched_tip,
            expected_head=expected_head,
            classify=True,
        )
        admission = self._admission_from_candidate_observation(
            state,
            candidate_observation,
            verb="merge recover",
            require_current_generation=False,
        )
        generation = engine.bind_merge_candidate_generation(
            self.ctx,
            admission,
            fetched_tip,
            generation=int(state["candidate"]["generation"]) + 1,
            observation=candidate_observation,
        )
        if (
            admission.candidate_head != expected_head
            or generation.candidate.get("candidate_head") != expected_head
            or not engine._merge_rebase_integrated_predicate(state, observation)
        ):
            raise ValueError("rebase observation changed before materialization")
        suite = engine._merge_epoch_suite(
            {
                **state,
                "candidate": generation.candidate,
                "tier": generation.tier,
            },
            admission.policy,
        )
        integration = copy.deepcopy(state["integration"])
        epoch = integration.get("epoch")
        pre_rebase = integration.get("pre_rebase")
        if not isinstance(epoch, Mapping) or not isinstance(pre_rebase, Mapping):
            raise FrozenError(
                "rebase result lacks its durable epoch and pre-rebase identity",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        integration.update(
            {
                "condition": "none",
                "primary_condition": "none",
                "conflict": None,
                "intent": {
                    "operation": "rebase-result",
                    "operation_nonce": epoch["operation_nonce"],
                    "result": "success",
                    "pre_operation_head": pre_rebase["head"],
                    "rebased_head": generation.candidate["candidate_head"],
                    "fetched_tip": fetched_tip,
                    "inflight_digest": inflight_digest,
                    "output_digest": output_digest,
                    "recorded_at": chain_core.iso_z(),
                },
            }
        )
        integration["epoch"]["generation_digest"] = generation.candidate[
            "generation_digest"
        ]
        integration["epoch"]["gate_plan"] = self._sealed_plan(
            {**state, "candidate": generation.candidate},
            admission.policy,
            suite,
        )
        prior_review = state.get("review")
        iteration = (
            prior_review.get("iteration")
            if isinstance(prior_review, Mapping)
            else None
        )
        retained_review = {"iteration": iteration} if type(iteration) is int else {}
        rebase_projection = {
            "state": "reverifying",
            "policy_source": {
                "commit": admission.policy.sha,
                "digest": admission.policy.digest,
            },
            "candidate": copy.deepcopy(generation.candidate),
            "tier": copy.deepcopy(generation.tier),
            "steps": {},
            "review": retained_review,
            "approval": {},
            "authorization": {},
            "integration": integration,
        }
        rebase_delta = {
            name: value
            for name, value in rebase_projection.items()
            if state.get(name) != value
        }
        return self._epoch_transition(
            state,
            lease,
            "rebase_result",
            {"delta": rebase_delta},
            generation_digest=str(generation.candidate["generation_digest"]),
        )

    def _recover_rebase_observation_locked(
        self,
        state: dict[str, Any],
        lock: chain_core.CommonRebaseLock,
        lease: chain_core.ChainLease,
    ) -> dict[str, Any]:
        """Classify a crashed rebase from bounded, fenced Git observations."""

        state, restored_intent = (
            self._restore_integrated_rebase_observation_intent_locked(state, lease)
        )
        if restored_intent is None:
            return self._record_foreign_git_locked(state, lease)
        git_dir = Path(str(state["worktree"]["git_dir"]))
        integration = state.get("integration")
        pre_rebase = (
            integration.get("pre_rebase")
            if isinstance(integration, Mapping)
            else None
        )
        epoch = integration.get("epoch") if isinstance(integration, Mapping) else None
        result_class = chain_core._merge_rebase_result_classification(state)
        if (
            not isinstance(pre_rebase, Mapping)
            or not isinstance(epoch, Mapping)
            or result_class == "foreign"
        ):
            return self._record_foreign_git_locked(state, lease)
        metadata: list[str] = []
        for name in (
            "MERGE_HEAD",
            "CHERRY_PICK_HEAD",
            "REVERT_HEAD",
            "BISECT_LOG",
            "rebase-apply",
            "rebase-merge",
            "sequencer",
        ):
            try:
                os.lstat(git_dir / name)
            except FileNotFoundError:
                continue
            except OSError:
                return self._record_foreign_git_locked(state, lease)
            metadata.append(name)
        rebase_live = any(name in metadata for name in ("rebase-merge", "rebase-apply"))
        if rebase_live:
            intent = integration.get("intent")
            exact_nonzero = bool(
                isinstance(intent, Mapping)
                and result_class == "failed"
                and type(intent.get("exit")) is int
                and intent.get("exit") != 0
                and intent.get("launch_failed") is False
                and intent.get("timed_out") is False
                and intent.get("output_limit_exceeded") is False
                and intent.get("group_survived") is False
            )
            if result_class != "absent" and not exact_nonzero:
                return self._record_foreign_git_locked(state, lease)
            state, observation = self._run_conflict_observation_locked(
                state, lock, lease, kind="conflict"
            )
            if observation is None:
                return self._record_foreign_git_locked(state, lease)
            integration = state["integration"]
            intent = integration.get("intent")
            result_class = chain_core._merge_rebase_result_classification(state)
            exact_nonzero = bool(
                isinstance(intent, Mapping)
                and result_class == "failed"
                and type(intent.get("exit")) is int
                and intent.get("exit") != 0
                and intent.get("launch_failed") is False
                and intent.get("timed_out") is False
                and intent.get("output_limit_exceeded") is False
                and intent.get("group_survived") is False
            )
            evidence_digest = sha256_bytes(chain_core.canonical_bytes(observation))
            inflight_digest = (
                str(intent["inflight_digest"])
                if isinstance(intent, Mapping) and exact_nonzero
                else evidence_digest
            )
            output_digest = (
                str(intent["output_digest"])
                if isinstance(intent, Mapping) and exact_nonzero
                else evidence_digest
            )
            updated = copy.deepcopy(dict(integration))
            updated["conflict"] = engine._merge_conflict_record(
                state,
                observation,
                inflight_digest=inflight_digest,
                output_digest=output_digest,
            )
            engine._reset_merge_nonmovement_counter(updated)
            return self._epoch_transition(
                state,
                lease,
                "rebase_conflict",
                {"delta": {"state": "rebase_conflict", "integration": updated}},
            )
        if metadata:
            return self._record_foreign_git_locked(state, lease)
        state, observation = self._run_integrated_rebase_observation_locked(
            state, lock, lease
        )
        if observation is None:
            return self._record_foreign_git_locked(state, lease)
        integration = state.get("integration")
        pre_rebase = (
            integration.get("pre_rebase")
            if isinstance(integration, Mapping)
            else None
        )
        result_class = chain_core._merge_rebase_result_classification(state)
        current_head = str(observation.get("observed_head", ""))
        evidence_digest = str(observation.get("evidence_digest", ""))
        if (
            not isinstance(integration, Mapping)
            or not isinstance(pre_rebase, Mapping)
            or chain_core.SHA256_RE.fullmatch(evidence_digest) is None
            or observation.get("status_empty") is not True
            or observation.get("branch") != state.get("branch")
        ):
            return self._record_foreign_git_locked(state, lease)
        if result_class in {"absent", "success"}:
            try:
                integrated = engine._merge_rebase_integrated_predicate(state, observation)
            except (OSError, ValueError):
                integrated = False
            if integrated:
                intent = integration.get("intent")
                inflight_digest = (
                    str(intent["inflight_digest"])
                    if isinstance(intent, Mapping) and result_class == "success"
                    else evidence_digest
                )
                output_digest = (
                    str(intent["output_digest"])
                    if isinstance(intent, Mapping) and result_class == "success"
                    else evidence_digest
                )
                try:
                    return self._materialize_rebase_success_locked(
                        state,
                        lock,
                        lease,
                        fetched_tip=str(pre_rebase["fetched_tip"]),
                        inflight_digest=inflight_digest,
                        output_digest=output_digest,
                        observation=observation,
                    )
                except (KeyError, OSError, Refusal, ValueError):
                    return self._record_foreign_git_locked(state, lease)
        if current_head == pre_rebase.get("head"):
            try:
                state, candidate_observation = (
                    self._run_candidate_observation_locked(
                        state,
                        lock,
                        lease,
                        verb="merge recover",
                        remote_tip=str(state["candidate"]["remote_tip"]),
                        expected_head=str(state["candidate"]["candidate_head"]),
                        classify=False,
                    )
                )
                _observe_current_merge_candidate(
                    self.ctx,
                    state,
                    verb="merge recover",
                    observation=candidate_observation,
                )
            except (KeyError, OSError, Refusal, ValueError):
                return self._record_foreign_git_locked(state, lease)
            updated = copy.deepcopy(dict(integration))
            if result_class == "failed":
                updated.update(
                    {
                        "condition": "rebase-failed",
                        "primary_condition": "none",
                        "epoch": None,
                        "conflict": None,
                    }
                )
                next_state = "revising"
            else:
                updated.update(
                    {
                        "condition": "none",
                        "primary_condition": "none",
                        "epoch": None,
                        "intent": None,
                        "conflict": None,
                    }
                )
                next_state = "authorized"
            engine._reset_merge_nonmovement_counter(updated)
            return self._epoch_transition(
                state,
                lease,
                "rebase_result",
                {"delta": {"state": next_state, "integration": updated}},
            )
        return self._record_foreign_git_locked(state, lease)

    def _finish_recovered_epoch_locked(
        self,
        state: dict[str, Any],
        lock: chain_core.CommonRebaseLock,
        lease: chain_core.ChainLease,
        budget: engine._MergeEpochBudget,
    ) -> tuple[dict[str, Any], str]:
        state = self._run_epoch_suite(state, lock, lease, budget)
        engine._require_active_merge_epoch(state)
        if not self._current_merge_authority(state):
            return self._park_integrated_review(state, lease), "review"
        state = self._run_remote_observation(
            state, lock, lease, budget, phase="final-prepush"
        )
        if state["state"] in {"authorized", "awaiting_approval"}:
            return state, "parked"
        engine._require_active_merge_epoch(state)
        state = self._run_epoch_push(state, lock, lease, budget)
        return state, "pushed" if state["state"] == "pushed" else "observed"

    def _run_conflict_observation_locked(
        self,
        state: dict[str, Any],
        lock: chain_core.CommonRebaseLock,
        lease: chain_core.ChainLease,
        *,
        kind: str,
        paths: Sequence[str] = (),
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """Run one conflict snapshot as three bounded, durable fenced reads."""

        chain_core._require_merge_integration_control("conflict-continue-contract")
        if kind not in {"conflict", "post-add"}:
            raise ValueError("invalid conflict observation kind")
        try:
            selected_paths = (
                engine._normalize_merge_conflict_paths(paths)
                if kind == "post-add" or paths
                else ()
            )
        except (TypeError, ValueError):
            return state, None
        integration = state.get("integration")
        epoch = integration.get("epoch") if isinstance(integration, Mapping) else None
        pre_rebase = (
            integration.get("pre_rebase")
            if isinstance(integration, Mapping)
            else None
        )
        current_intent = (
            integration.get("intent") if isinstance(integration, Mapping) else None
        )
        phase = current_intent.get("phase") if isinstance(current_intent, Mapping) else None
        source_intent = (
            current_intent.get("source_intent")
            if isinstance(current_intent, Mapping)
            and isinstance(phase, str)
            and phase.startswith("forge-conflict-observation:")
            else current_intent
        )
        action = chain_core._merge_rebase_action(state)
        if (
            not isinstance(epoch, Mapping)
            or not isinstance(pre_rebase, Mapping)
            or not isinstance(source_intent, Mapping)
            or action is None
        ):
            return state, None
        identity = {
            "operation_nonce": epoch.get("operation_nonce"),
            "pre_operation_head": pre_rebase.get("head"),
            "fetched_tip": pre_rebase.get("fetched_tip"),
            "branch": state.get("branch"),
            "generation_digest": pre_rebase.get("generation_digest"),
            "reflog_action": action,
        }
        source_state = copy.deepcopy(state)
        source_state["integration"]["intent"] = copy.deepcopy(dict(source_intent))
        if not engine._merge_owned_rebase_metadata(source_state):
            return state, None
        commands: tuple[tuple[str, list[str]], ...] = (
            ("unmerged", ["git", "diff", "--name-only", "--diff-filter=U", "-z", "--"]),
            ("index", ["git", "ls-files", "--stage", "-z", "--"]),
            (
                "status",
                ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
            ),
        )
        environment = os.environ.copy()
        environment.pop("FORGE_SESSION_PID", None)
        environment.update(
            {
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_NO_LAZY_FETCH": "1",
                "GIT_REFLOG_ACTION": action,
            }
        )
        observation_nonce = secrets.token_hex(16)
        observation_binding = sha256_bytes(
            chain_core.canonical_bytes(
                {
                    "kind": kind,
                    "observation_nonce": observation_nonce,
                    "paths": list(selected_paths),
                    "source_intent": source_intent,
                }
            )
        )

        def restore_source_intent() -> None:
            nonlocal state
            if state.get("integration", {}).get("intent") == source_intent:
                return
            restored = copy.deepcopy(state["integration"])
            restored["intent"] = copy.deepcopy(dict(source_intent))
            state = self._epoch_transition(
                state,
                lease,
                "rebase_intent",
                {"delta": {"integration": restored}},
            )

        outputs: dict[str, bytes] = {}
        output_digests: dict[str, str] = {}
        worktree = Path(str(state["worktree"]["path"]))
        for name, argv in commands:
            if not engine._merge_owned_rebase_metadata(
                {
                    **state,
                    "integration": {
                        **state["integration"],
                        "intent": {
                            "operation": "continue",
                            **identity,
                        },
                    },
                }
            ):
                restore_source_intent()
                return state, None
            observation_intent = {
                "operation": "continue",
                **identity,
                "phase": f"forge-conflict-observation:{kind}:{name}:intent",
                "observation_nonce": observation_nonce,
                "observation_binding": observation_binding,
                "observation_kind": kind,
                "observation_step": name,
                "authorized_paths": list(selected_paths),
                "prior_output_digests": copy.deepcopy(output_digests),
                "source_intent": copy.deepcopy(dict(source_intent)),
                "started_at": chain_core.iso_z(),
            }
            updated = copy.deepcopy(state["integration"])
            updated["intent"] = copy.deepcopy(observation_intent)
            state = self._epoch_transition(
                state,
                lease,
                "rebase_intent",
                {"delta": {"integration": updated}},
            )
            intent_digest = self._tail_event_digest(state, "rebase_intent")

            def intent_current(
                expected: Mapping[str, Any] = observation_intent,
                expected_digest: str = intent_digest,
            ) -> bool:
                try:
                    fresh = self.store.load_locked(
                        str(state["chain_id"]), lease=lease
                    )
                    return bool(
                        fresh.get("state") == state.get("state")
                        and fresh.get("integration", {}).get("condition") == "none"
                        and fresh.get("integration", {}).get("intent") == expected
                        and self._tail_event_digest(fresh, "rebase_intent")
                        == expected_digest
                    )
                except (FrozenError, KeyError, OSError, Refusal, ValueError):
                    return False

            def persist_observation(result: chain_core.FencedProcessResult) -> None:
                nonlocal state
                result_intent = {
                    **copy.deepcopy(observation_intent),
                    "phase": f"forge-conflict-observation:{kind}:{name}:result",
                    "child_result": {
                        "authorized": result.authorized,
                        "exit": result.returncode,
                        "inflight_digest": result.fence_digest,
                        "output_digest": result.output_digest,
                        "launch_failed": result.launch_failed,
                        "timed_out": result.timed_out,
                        "output_limit_exceeded": result.output_limit,
                        "group_survived": result.group_survived,
                    },
                    "recorded_at": chain_core.iso_z(),
                }
                result_integration = copy.deepcopy(state["integration"])
                result_integration["intent"] = result_intent
                state = self._epoch_transition(
                    state,
                    lease,
                    "rebase_intent",
                    {"delta": {"integration": result_integration}},
                )

            result = chain_core.run_fenced_command(
                lock,
                operation="continue",
                intent_digest=intent_digest,
                intent_validator=intent_current,
                argv=argv,
                cwd=worktree,
                persist_result=persist_observation,
                env=environment,
                timeout=runtime.COMMAND_TIMEOUT_SECONDS,
                cap=runtime.OUTPUT_CAP_BYTES,
                verbose=self.ctx.options.verbose,
            )
            durable_result = state.get("integration", {}).get("intent", {}).get(
                "child_result"
            )
            if (
                not isinstance(durable_result, Mapping)
                or durable_result.get("authorized") is not True
                or durable_result.get("exit") != 0
                or durable_result.get("launch_failed") is not False
                or durable_result.get("timed_out") is not False
                or durable_result.get("output_limit_exceeded") is not False
                or durable_result.get("group_survived") is not False
                or durable_result.get("inflight_digest") != result.fence_digest
                or durable_result.get("output_digest") != result.output_digest
            ):
                restore_source_intent()
                return state, None
            outputs[name] = result.output
            output_digests[name] = result.output_digest
        if not engine._merge_owned_rebase_metadata(state):
            restore_source_intent()
            return state, None
        observation = (
            engine._observe_merge_conflict(
                outputs["unmerged"], outputs["index"], outputs["status"]
            )
            if kind == "conflict"
            else engine._observe_merge_post_add(
                selected_paths,
                outputs["unmerged"],
                outputs["index"],
                outputs["status"],
            )
        )
        restore_source_intent()
        return state, observation

    def _recover_conflict_locked(
        self,
        state: dict[str, Any],
        lock: chain_core.CommonRebaseLock,
        lease: chain_core.ChainLease,
        *,
        continue_rebase: bool,
        abort_rebase: bool,
        paths: Sequence[str] | None,
    ) -> dict[str, Any]:
        integration = copy.deepcopy(state["integration"])
        epoch = integration.get("epoch")
        pre_rebase = integration.get("pre_rebase")
        durable_intent = integration.get("intent")
        durable_phase = (
            durable_intent.get("phase")
            if isinstance(durable_intent, Mapping)
            else None
        )
        conflict_observation_pending = bool(
            isinstance(durable_intent, Mapping)
            and isinstance(durable_phase, str)
            and durable_phase.startswith("forge-conflict-observation:")
            and isinstance(durable_intent.get("source_intent"), Mapping)
        )
        integrated_observation_pending = bool(
            isinstance(durable_intent, Mapping)
            and isinstance(durable_phase, str)
            and durable_phase.startswith("forge-integrated-observation:")
            and isinstance(durable_intent.get("source_intent"), Mapping)
        )
        observation_pending = bool(
            conflict_observation_pending or integrated_observation_pending
        )
        prior_intent = (
            durable_intent.get("source_intent")
            if observation_pending and isinstance(durable_intent, Mapping)
            else durable_intent
        )
        prior_conflict = integration.get("conflict")
        continuation_marker = (
            prior_conflict.get("continuation_result")
            if isinstance(prior_conflict, Mapping)
            else None
        )
        abort_marker = (
            prior_conflict.get("abort_result")
            if isinstance(prior_conflict, Mapping)
            else None
        )
        abort_result_pending = bool(
            isinstance(prior_intent, Mapping)
            and prior_intent.get("operation") == "rebase-result"
            and isinstance(abort_marker, Mapping)
            and abort_marker.get("operation_nonce")
            == prior_intent.get("operation_nonce")
            and abort_marker.get("inflight_digest")
            == prior_intent.get("inflight_digest")
            and abort_marker.get("output_digest")
            == prior_intent.get("output_digest")
        )
        continuation_phase = (
            "continue-result"
            if isinstance(prior_intent, Mapping)
            and prior_intent.get("operation") == "rebase-result"
            and isinstance(continuation_marker, Mapping)
            and not abort_result_pending
            and not abort_rebase
            else str(prior_intent.get("phase"))
            if isinstance(prior_intent, Mapping)
            and prior_intent.get("operation") == "continue"
            and prior_intent.get("phase") in {"stage-result", "rebase"}
            and not abort_rebase
            else None
        )
        resume_continue = bool(
            continuation_phase is not None
            or conflict_observation_pending
            or integrated_observation_pending
            and isinstance(continuation_marker, Mapping)
            and not abort_result_pending
        )
        resume_abort = abort_result_pending
        if (
            not continue_rebase
            and not abort_rebase
            and not resume_continue
            and not resume_abort
        ):
            return state
        if not isinstance(epoch, Mapping) or not isinstance(pre_rebase, Mapping):
            return self._record_foreign_git_locked(state, lease)
        worktree = Path(str(state["worktree"]["path"]))
        reflog_action = chain_core._merge_rebase_action(state)
        if reflog_action is None:
            return self._record_foreign_git_locked(state, lease)
        identity = {
            "operation_nonce": epoch["operation_nonce"],
            "pre_operation_head": pre_rebase["head"],
            "fetched_tip": pre_rebase["fetched_tip"],
            "branch": state["branch"],
            "generation_digest": pre_rebase["generation_digest"],
            "reflog_action": reflog_action,
        }
        environment = os.environ.copy()
        environment.pop("FORGE_SESSION_PID", None)
        environment.update(
            {
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_NO_LAZY_FETCH": "1",
                "GIT_REFLOG_ACTION": reflog_action,
            }
        )

        if continue_rebase or resume_continue:
            source_paths: Sequence[str] = (
                paths or ()
                if continue_rebase
                else durable_intent.get("authorized_paths", ())
                if conflict_observation_pending
                and isinstance(durable_intent, Mapping)
                else prior_conflict.get("authorized_paths", ())
                if continuation_phase == "continue-result"
                and isinstance(prior_conflict, Mapping)
                else prior_intent.get("authorized_paths", ())
                if isinstance(prior_intent, Mapping)
                else ()
            )
            try:
                selected_paths = engine._normalize_merge_conflict_paths(source_paths)
            except (TypeError, ValueError):
                raise chain_core._merge_refusal(
                    V2ReasonCode.STATE_PRECONDITION,
                    "forge: merge recover refused — conflict paths are invalid",
                    chain=state,
                )
            conflict = integration.get("conflict")
            conflict_digest = (
                sha256_bytes(chain_core.canonical_bytes(dict(conflict)))
                if isinstance(conflict, Mapping)
                else None
            )

            def mark_foreign() -> None:
                nonlocal state
                state = self._record_foreign_git_locked(state, lease)

            def refuse_changed_conflict() -> None:
                raise chain_core._merge_refusal(
                    V2ReasonCode.STATE_PRECONDITION,
                    "forge: merge recover refused — conflict ownership or baselines changed",
                    expected="the recorded conflict set and non-conflict byte baselines",
                    observed="foreign or changed Git conflict state",
                    remediation=(
                        f"forge merge recover --abort-rebase --chain-id {state['chain_id']}"
                    ),
                    chain=state,
                )

            def phase_intent_valid(
                candidate: object, *, operation: str, phase: str
            ) -> bool:
                return bool(
                    isinstance(candidate, Mapping)
                    and candidate.get("operation") == operation
                    and candidate.get("phase") == phase
                    and candidate.get("authorized_paths") == list(selected_paths)
                    and candidate.get("conflict_digest") == conflict_digest
                    and isinstance(conflict, Mapping)
                    and candidate.get("index_baseline_digest")
                    == conflict.get("index_baseline_digest")
                    and candidate.get("status_baseline_digest")
                    == conflict.get("status_baseline_digest")
                    and all(candidate.get(name) == value for name, value in identity.items())
                )

            def exact_stage_success(candidate: Mapping[str, Any]) -> bool:
                result = candidate.get("stage_result")
                return bool(
                    isinstance(result, Mapping)
                    and result.get("authorized") is True
                    and type(result.get("exit")) is int
                    and result.get("exit") == 0
                    and result.get("launch_failed") is False
                    and result.get("timed_out") is False
                    and result.get("output_limit_exceeded") is False
                    and result.get("group_survived") is False
                    and chain_core.SHA256_RE.fullmatch(str(result.get("inflight_digest", "")))
                    is not None
                    and chain_core.SHA256_RE.fullmatch(str(result.get("output_digest", "")))
                    is not None
                )

            def classify_continue_result() -> str:
                nonlocal state
                result_intent = state.get("integration", {}).get("intent")
                current_conflict = state.get("integration", {}).get("conflict")
                marker = (
                    current_conflict.get("continuation_result")
                    if isinstance(current_conflict, Mapping)
                    else None
                )
                result_class = chain_core._merge_rebase_result_classification(state)
                if (
                    not isinstance(result_intent, Mapping)
                    or not isinstance(marker, Mapping)
                    or marker.get("operation_nonce")
                    != identity["operation_nonce"]
                    or marker.get("inflight_digest")
                    != result_intent.get("inflight_digest")
                    or marker.get("output_digest")
                    != result_intent.get("output_digest")
                ):
                    mark_foreign()
                    return "foreign"
                if result_class == "foreign":
                    mark_foreign()
                    return (
                        "failed-foreign"
                        if result_intent.get("group_survived") is True
                        else "foreign"
                    )
                normal = bool(
                    type(result_intent.get("exit")) is int
                    and result_intent.get("launch_failed") is False
                    and result_intent.get("timed_out") is False
                    and result_intent.get("output_limit_exceeded") is False
                    and result_intent.get("group_survived") is False
                    and chain_core.SHA256_RE.fullmatch(
                        str(result_intent.get("inflight_digest", ""))
                    )
                    is not None
                    and chain_core.SHA256_RE.fullmatch(
                        str(result_intent.get("output_digest", ""))
                    )
                    is not None
                )
                ordinary_nonzero = bool(
                    normal and int(result_intent.get("exit", 0)) > 0
                )
                if ordinary_nonzero:
                    state, next_conflict = self._run_conflict_observation_locked(
                        state,
                        lock,
                        lease,
                        kind="conflict",
                        paths=selected_paths,
                    )
                    if next_conflict is not None:
                        updated = copy.deepcopy(state["integration"])
                        updated["conflict"] = engine._merge_conflict_record(
                            state,
                            next_conflict,
                            inflight_digest=str(result_intent["inflight_digest"]),
                            output_digest=str(result_intent["output_digest"]),
                        )
                        updated["intent"] = {
                            "operation": "continue",
                            **identity,
                            "phase": "conflict",
                            "recorded_at": chain_core.iso_z(),
                        }
                        engine._reset_merge_nonmovement_counter(updated)
                        state = self._epoch_transition(
                            state,
                            lease,
                            "rebase_conflict",
                            {
                                "delta": {
                                    "state": "rebase_conflict",
                                    "integration": updated,
                                }
                            },
                        )
                        return "conflict"
                if normal and result_intent.get("exit") == 0:
                    state, integrated_observation = (
                        self._run_integrated_rebase_observation_locked(
                            state, lock, lease
                        )
                    )
                    if (
                        isinstance(integrated_observation, Mapping)
                        and engine._merge_rebase_integrated_predicate(
                            state, integrated_observation
                        )
                    ):
                        observed_head = str(
                            integrated_observation.get("observed_head", "")
                        )
                        try:
                            state = self._materialize_rebase_success_locked(
                                state,
                                lock,
                                lease,
                                fetched_tip=str(pre_rebase["fetched_tip"]),
                                inflight_digest=str(
                                    result_intent["inflight_digest"]
                                ),
                                output_digest=str(result_intent["output_digest"]),
                                observation=integrated_observation,
                            )
                        except (KeyError, OSError, Refusal, ValueError):
                            pass
                        else:
                            return "continued"
                    updated = copy.deepcopy(state["integration"])
                    updated.update(
                        {
                            "condition": "foreign-git-state",
                            "primary_condition": "none",
                        }
                    )
                    engine._reset_merge_nonmovement_counter(updated)
                    state = self._epoch_transition(
                        state,
                        lease,
                        "rebase_result",
                        {"delta": {"integration": updated}},
                    )
                    return "foreign"
                if not normal:
                    mark_foreign()
                    return "failed-foreign"
                state, restoration_observation = (
                    self._run_integrated_rebase_observation_locked(
                        state, lock, lease
                    )
                )
                restored = bool(
                    isinstance(restoration_observation, Mapping)
                    and restoration_observation.get("status_empty") is True
                    and restoration_observation.get("observed_head")
                    == pre_rebase.get("head")
                    and restoration_observation.get("branch") == state.get("branch")
                    and engine._merge_rebase_operation_metadata_absent(state)
                )
                if not restored:
                    mark_foreign()
                    return "failed-foreign"
                updated = copy.deepcopy(state["integration"])
                updated.update(
                    {
                        "condition": "rebase-failed",
                        "primary_condition": "none",
                        "epoch": None,
                        "conflict": None,
                    }
                )
                engine._reset_merge_nonmovement_counter(updated)
                state = self._epoch_transition(
                    state,
                    lease,
                    "rebase_result",
                    {
                        "delta": {
                            "state": "revising",
                            "integration": updated,
                        }
                    },
                )
                return "failed"

            if resume_continue:
                if not isinstance(prior_intent, Mapping):
                    mark_foreign()
                    refuse_changed_conflict()
                try:
                    durable_paths = engine._normalize_merge_conflict_paths(
                        conflict.get("authorized_paths", ())
                        if continuation_phase == "continue-result"
                        and isinstance(conflict, Mapping)
                        else durable_intent.get("authorized_paths", ())
                        if observation_pending
                        and isinstance(durable_intent, Mapping)
                        else prior_intent.get("authorized_paths", ())
                    )
                except (TypeError, ValueError):
                    durable_paths = ()
                if selected_paths != durable_paths:
                    raise chain_core._merge_refusal(
                        V2ReasonCode.STATE_PRECONDITION,
                        "forge: merge recover refused — requested paths differ from the durable continuation intent",
                        chain=state,
                    )

            if continuation_phase == "continue-result":
                disposition = classify_continue_result()
                if disposition in {"failed", "failed-foreign"}:
                    raise chain_core._merge_refusal(
                        V2ReasonCode.REBASE_FAILED,
                        "forge: merge recover refused — rebase continuation failed",
                        remediation=f"forge merge refresh --chain-id {state['chain_id']}",
                        chain=state,
                    )
                if disposition == "foreign":
                    refuse_changed_conflict()
                return state

            if continuation_phase is None:
                try:
                    stored_paths = engine._normalize_merge_conflict_paths(
                        conflict.get("authorized_paths", ())
                        if isinstance(conflict, Mapping)
                        else ()
                    )
                except (TypeError, ValueError):
                    stored_paths = ()
                if selected_paths != stored_paths:
                    raise chain_core._merge_refusal(
                        V2ReasonCode.STATE_PRECONDITION,
                        "forge: merge recover refused — requested paths differ from the recorded conflict set",
                        expected=str(list(stored_paths)),
                        observed=str(list(selected_paths)),
                        chain=state,
                    )
                state, observation = self._run_conflict_observation_locked(
                    state,
                    lock,
                    lease,
                    kind="conflict",
                    paths=selected_paths,
                )
                if observation is None:
                    mark_foreign()
                    refuse_changed_conflict()
                fresh_paths = tuple(observation["authorized_paths"])
                if selected_paths != fresh_paths:
                    raise chain_core._merge_refusal(
                        V2ReasonCode.STATE_PRECONDITION,
                        "forge: merge recover refused — requested paths differ from the exact unmerged set",
                        expected=str(list(fresh_paths)),
                        observed=str(list(selected_paths)),
                        chain=state,
                    )
                if not engine._merge_conflict_record_matches(state, observation):
                    mark_foreign()
                    refuse_changed_conflict()
                stage_intent = {
                    "operation": "continue",
                    **identity,
                    "phase": "stage",
                    "authorized_paths": list(selected_paths),
                    "conflict_digest": conflict_digest,
                    "index_baseline_digest": observation["index_baseline_digest"],
                    "status_baseline_digest": observation["status_baseline_digest"],
                    "started_at": chain_core.iso_z(),
                }
                staged = copy.deepcopy(state["integration"])
                staged["intent"] = copy.deepcopy(stage_intent)
                state = self._epoch_transition(
                    state,
                    lease,
                    "rebase_intent",
                    {"delta": {"integration": staged}},
                )
                stage_intent_digest = self._tail_event_digest(state, "rebase_intent")

                def stage_intent_current() -> bool:
                    try:
                        fresh = self.store.load_locked(
                            str(state["chain_id"]), lease=lease
                        )
                        return bool(
                            fresh.get("state") == "rebase_conflict"
                            and fresh.get("integration", {}).get("condition") == "none"
                            and fresh.get("integration", {}).get("intent") == stage_intent
                            and self._tail_event_digest(fresh, "rebase_intent")
                            == stage_intent_digest
                        )
                    except (FrozenError, KeyError, OSError, Refusal, ValueError):
                        return False

                def persist_stage(result: chain_core.FencedProcessResult) -> None:
                    nonlocal state
                    stage_result = {
                        **copy.deepcopy(stage_intent),
                        "phase": "stage-result",
                        "stage_result": {
                            "authorized": result.authorized,
                            "exit": result.returncode,
                            "inflight_digest": result.fence_digest,
                            "output_digest": result.output_digest,
                            "launch_failed": result.launch_failed,
                            "timed_out": result.timed_out,
                            "output_limit_exceeded": result.output_limit,
                            "group_survived": result.group_survived,
                        },
                        "recorded_at": chain_core.iso_z(),
                    }
                    updated = copy.deepcopy(state["integration"])
                    updated["intent"] = stage_result
                    state = self._epoch_transition(
                        state,
                        lease,
                        "rebase_intent",
                        {"delta": {"integration": updated}},
                    )

                chain_core.run_fenced_command(
                    lock,
                    operation="continue",
                    intent_digest=stage_intent_digest,
                    intent_validator=stage_intent_current,
                    argv=["git", "--literal-pathspecs", "add", "--", *selected_paths],
                    cwd=worktree,
                    persist_result=persist_stage,
                    env=environment,
                    timeout=runtime.COMMAND_TIMEOUT_SECONDS,
                    cap=runtime.OUTPUT_CAP_BYTES,
                    verbose=self.ctx.options.verbose,
                )
                continuation_phase = "stage-result"

            if continuation_phase == "stage-result":
                stage_result = state.get("integration", {}).get("intent")
                if (
                    not phase_intent_valid(
                        stage_result, operation="continue", phase="stage-result"
                    )
                    or not isinstance(stage_result, Mapping)
                    or not exact_stage_success(stage_result)
                ):
                    mark_foreign()
                    raise chain_core._merge_refusal(
                        V2ReasonCode.REBASE_FAILED,
                        "forge: merge recover refused — literal conflict staging failed",
                        remediation=(
                            f"forge merge recover --abort-rebase --chain-id {state['chain_id']}"
                        ),
                        chain=state,
                    )
                state, post_add = self._run_conflict_observation_locked(
                    state,
                    lock,
                    lease,
                    kind="post-add",
                    paths=selected_paths,
                )
                if (
                    post_add is None
                    or post_add["nonconflict_index_digest"]
                    != stage_result.get("index_baseline_digest")
                    or post_add["nonconflict_status_digest"]
                    != stage_result.get("status_baseline_digest")
                ):
                    mark_foreign()
                    refuse_changed_conflict()
                rebase_intent = {
                    **copy.deepcopy(dict(stage_result)),
                    "phase": "rebase",
                    "post_add_index_digest": post_add["index_digest"],
                    "post_add_status_digest": post_add["status_digest"],
                    "post_add_nonconflict_index_digest": post_add[
                        "nonconflict_index_digest"
                    ],
                    "post_add_nonconflict_status_digest": post_add[
                        "nonconflict_status_digest"
                    ],
                    "recorded_at": chain_core.iso_z(),
                }
                updated = copy.deepcopy(state["integration"])
                updated["intent"] = rebase_intent
                state = self._epoch_transition(
                    state,
                    lease,
                    "rebase_intent",
                    {"delta": {"integration": updated}},
                )
                continuation_phase = "rebase"

            rebase_intent = state.get("integration", {}).get("intent")
            state, post_add = self._run_conflict_observation_locked(
                state,
                lock,
                lease,
                kind="post-add",
                paths=selected_paths,
            )
            if (
                continuation_phase != "rebase"
                or not phase_intent_valid(
                    rebase_intent, operation="continue", phase="rebase"
                )
                or not isinstance(rebase_intent, Mapping)
                or not exact_stage_success(rebase_intent)
                or post_add is None
                or post_add["index_digest"]
                != rebase_intent.get("post_add_index_digest")
                or post_add["status_digest"]
                != rebase_intent.get("post_add_status_digest")
                or post_add["nonconflict_index_digest"]
                != rebase_intent.get("index_baseline_digest")
                or post_add["nonconflict_status_digest"]
                != rebase_intent.get("status_baseline_digest")
                or post_add["nonconflict_index_digest"]
                != rebase_intent.get("post_add_nonconflict_index_digest")
                or post_add["nonconflict_status_digest"]
                != rebase_intent.get("post_add_nonconflict_status_digest")
            ):
                mark_foreign()
                refuse_changed_conflict()
            rebase_intent_digest = self._tail_event_digest(state, "rebase_intent")

            def rebase_intent_current() -> bool:
                try:
                    fresh = self.store.load_locked(
                        str(state["chain_id"]), lease=lease
                    )
                    return bool(
                        fresh.get("state") == "rebase_conflict"
                        and fresh.get("integration", {}).get("condition") == "none"
                        and fresh.get("integration", {}).get("intent")
                        == rebase_intent
                        and self._tail_event_digest(fresh, "rebase_intent")
                        == rebase_intent_digest
                    )
                except (FrozenError, KeyError, OSError, Refusal, ValueError):
                    return False

            def persist_continue(result: chain_core.FencedProcessResult) -> None:
                nonlocal state
                succeeded = bool(
                    result.returncode == 0
                    and not result.launch_failed
                    and not result.timed_out
                    and not result.output_limit
                    and not result.group_survived
                )
                result_intent = {
                    "operation": "rebase-result",
                    **identity,
                    "result": "success" if succeeded else "failed",
                    "exit": result.returncode,
                    "inflight_digest": result.fence_digest,
                    "output_digest": result.output_digest,
                    "launch_failed": result.launch_failed,
                    "timed_out": result.timed_out,
                    "output_limit_exceeded": result.output_limit,
                    "group_survived": result.group_survived,
                    "recorded_at": chain_core.iso_z(),
                }
                updated = copy.deepcopy(state["integration"])
                updated["intent"] = result_intent
                updated_conflict = copy.deepcopy(updated.get("conflict"))
                if not isinstance(updated_conflict, dict):
                    raise FrozenError(
                        "merge continuation result lost its conflict identity",
                        chain_id=str(state["chain_id"]),
                        schema=REVISION9_OUTPUT_SCHEMA,
                    )
                updated_conflict["continuation_result"] = {
                    "operation_nonce": identity["operation_nonce"],
                    "inflight_digest": result.fence_digest,
                    "output_digest": result.output_digest,
                }
                updated["conflict"] = updated_conflict
                state = self._epoch_transition(
                    state,
                    lease,
                    "rebase_intent",
                    {"delta": {"integration": updated}},
                )

            continue_environment = environment.copy()
            continue_environment["GIT_EDITOR"] = "true"
            chain_core.run_fenced_command(
                lock,
                operation="continue",
                intent_digest=rebase_intent_digest,
                intent_validator=rebase_intent_current,
                argv=["git", "rebase", "--continue"],
                cwd=worktree,
                persist_result=persist_continue,
                env=continue_environment,
                timeout=runtime.COMMAND_TIMEOUT_SECONDS,
                cap=runtime.OUTPUT_CAP_BYTES,
                verbose=self.ctx.options.verbose,
            )
            disposition = classify_continue_result()
            if disposition in {"failed", "failed-foreign"}:
                raise chain_core._merge_refusal(
                    V2ReasonCode.REBASE_FAILED,
                    "forge: merge recover refused — rebase continuation failed",
                    remediation=f"forge merge refresh --chain-id {state['chain_id']}",
                    chain=state,
                )
            if disposition == "foreign":
                refuse_changed_conflict()
            return state

        if not resume_abort:
            abort_intent = {
                "operation": "abort",
                **identity,
                "started_at": chain_core.iso_z(),
            }
            integration["intent"] = copy.deepcopy(abort_intent)
            state = self._epoch_transition(
                state,
                lease,
                "rebase_intent",
                {"delta": {"integration": integration}},
            )
            intent_digest = self._tail_event_digest(state, "rebase_intent")

            def abort_intent_current() -> bool:
                try:
                    fresh = self.store.load_locked(
                        str(state["chain_id"]), lease=lease
                    )
                    return bool(
                        fresh.get("state") == "rebase_conflict"
                        and fresh.get("integration", {}).get("condition") == "none"
                        and fresh.get("integration", {}).get("intent")
                        == abort_intent
                        and self._tail_event_digest(fresh, "rebase_intent")
                        == intent_digest
                    )
                except (FrozenError, KeyError, OSError, Refusal, ValueError):
                    return False

            def persist_abort(result: chain_core.FencedProcessResult) -> None:
                nonlocal state
                succeeded = bool(
                    result.returncode == 0
                    and not result.launch_failed
                    and not result.timed_out
                    and not result.output_limit
                    and not result.group_survived
                )
                result_intent = {
                    "operation": "rebase-result",
                    **identity,
                    "result": "success" if succeeded else "failed",
                    "exit": result.returncode,
                    "inflight_digest": result.fence_digest,
                    "output_digest": result.output_digest,
                    "launch_failed": result.launch_failed,
                    "timed_out": result.timed_out,
                    "output_limit_exceeded": result.output_limit,
                    "group_survived": result.group_survived,
                    "recorded_at": chain_core.iso_z(),
                }
                updated = copy.deepcopy(state["integration"])
                updated["intent"] = result_intent
                updated_conflict = copy.deepcopy(updated.get("conflict"))
                if not isinstance(updated_conflict, dict):
                    raise FrozenError(
                        "merge abort result lost its conflict identity",
                        chain_id=str(state["chain_id"]),
                        schema=REVISION9_OUTPUT_SCHEMA,
                    )
                updated_conflict["abort_result"] = {
                    "operation_nonce": identity["operation_nonce"],
                    "inflight_digest": result.fence_digest,
                    "output_digest": result.output_digest,
                }
                updated["conflict"] = updated_conflict
                state = self._epoch_transition(
                    state,
                    lease,
                    "rebase_intent",
                    {"delta": {"integration": updated}},
                )

            chain_core.run_fenced_command(
                lock,
                operation="abort",
                intent_digest=intent_digest,
                intent_validator=abort_intent_current,
                argv=[
                    "git",
                    "--no-pager",
                    "-C",
                    str(worktree),
                    "rebase",
                    "--abort",
                ],
                cwd=worktree,
                persist_result=persist_abort,
                env=environment,
                timeout=runtime.COMMAND_TIMEOUT_SECONDS,
                cap=runtime.OUTPUT_CAP_BYTES,
                verbose=self.ctx.options.verbose,
            )

        raw_abort_result = state.get("integration", {}).get("intent")
        current_conflict = state.get("integration", {}).get("conflict")
        current_abort_marker = (
            current_conflict.get("abort_result")
            if isinstance(current_conflict, Mapping)
            else None
        )
        result_class = chain_core._merge_rebase_result_classification(state)
        if (
            not isinstance(raw_abort_result, Mapping)
            or not isinstance(current_abort_marker, Mapping)
            or current_abort_marker.get("operation_nonce")
            != identity["operation_nonce"]
            or current_abort_marker.get("inflight_digest")
            != raw_abort_result.get("inflight_digest")
            or current_abort_marker.get("output_digest")
            != raw_abort_result.get("output_digest")
            or result_class not in {"success", "failed"}
        ):
            return self._record_foreign_git_locked(state, lease)

        state, restoration_observation = (
            self._run_integrated_rebase_observation_locked(state, lock, lease)
        )
        restored = bool(
            isinstance(restoration_observation, Mapping)
            and restoration_observation.get("status_empty") is True
            and restoration_observation.get("observed_head")
            == pre_rebase.get("head")
            and restoration_observation.get("branch") == state.get("branch")
            and engine._merge_rebase_operation_metadata_absent(state)
        )
        if not restored:
            return self._record_foreign_git_locked(state, lease)
        updated = copy.deepcopy(state["integration"])
        engine._reset_merge_nonmovement_counter(updated)
        updated.update(
            {
                "condition": "rebase-failed",
                "primary_condition": "none",
                "epoch": None,
                "conflict": None,
            }
        )
        state = self._epoch_transition(
            state,
            lease,
            "rebase_result",
            {
                "delta": {
                    "state": "revising",
                    "integration": updated,
                }
            },
        )
        return state

    def _bootstrap_pending_classification_inputs_locked(
        self,
        state: Mapping[str, Any],
        admission: engine.MergeAdmission,
    ) -> engine.MergeBootstrapClassification:
        """Recover the authenticated inputs carried by a successful result."""

        if not chain_core._merge_bootstrap_classification_pending(state):
            raise FrozenError(
                "merge bootstrap classification snapshot is not pending",
                chain_id=str(state.get("chain_id", "")) or None,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        candidate = state["candidate"]
        with self.store.event_lock(str(state["chain_id"])):
            replay = self.store._read_replay_locked(str(state["chain_id"]))
        selected: Mapping[str, Any] | None = None
        for event in reversed(replay.events):
            payload = event.get("payload")
            delta = payload.get("delta") if isinstance(payload, Mapping) else None
            integration = (
                delta.get("integration") if isinstance(delta, Mapping) else None
            )
            if (
                event.get("event") == "fetch_result"
                and event.get("generation_digest")
                == candidate.get("generation_digest")
                and isinstance(payload, Mapping)
                and integration == state.get("integration")
            ):
                selected = event
                break
        if selected is None:
            raise FrozenError(
                "merge bootstrap classification result evidence is unavailable",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        payload = selected["payload"]
        try:
            binding = chain_core._validate_merge_scope_fetch_binding(
                payload.get("scope_fetch_binding")
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise FrozenError(
                "merge bootstrap classification sidecar is malformed",
                chain_id=str(state["chain_id"]),
                observed=str(exc),
                schema=REVISION9_OUTPUT_SCHEMA,
            ) from exc
        if (
            binding.get("chain_id") != state.get("chain_id")
            or binding.get("candidate_head") != candidate.get("candidate_head")
            or binding.get("remote_tip") != candidate.get("remote_tip")
            or binding.get("full_patch_output_digest")
            != candidate.get("diff_sha256")
        ):
            raise FrozenError(
                "merge bootstrap classification sidecar changed its candidate",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        proof = payload.get("scope_proof")
        scope: engine.MergeScopeResult | None = None
        if admission.run_task is not None:
            scope_request = engine._merge_scope_request(admission)
            if not chain_core._validate_merge_scope_proof(
                proof,
                state=state,
                binding=binding,
                scope_request=scope_request,
            ):
                raise FrozenError(
                    "merge bootstrap classification scope proof is malformed",
                    chain_id=str(state["chain_id"]),
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            assert isinstance(proof, Mapping)
            scope = engine.MergeScopeResult(
                argv=tuple(
                    chain_core._merge_scope_argv(
                        admission.worktree,
                        str(candidate["remote_tip"]),
                        str(candidate["candidate_head"]),
                    )
                ),
                command_digest=str(proof["command_digest"]),
                environment_digest=str(proof["environment_digest"]),
                output_digest=str(proof["output_digest"]),
                changed_paths=tuple(proof["changed_paths"]),
                out_of_scope_paths=tuple(proof["out_of_scope_paths"]),
                result=str(proof["result"]),
            )
        elif proof is not None:
            raise FrozenError(
                "unbound merge bootstrap carried a scope proof",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        return engine.MergeBootstrapClassification(
            candidate=copy.deepcopy(dict(candidate)),
            scope=scope,
            full_patch_output_digest=str(binding["full_patch_output_digest"]),
            scope_proof_digest=(
                str(proof["digest"]) if isinstance(proof, Mapping) else None
            ),
            fetch_result_event_digest=str(selected["digest"]),
            verb="merge recover",
        )

    def _recover_classifying_bootstrap_v12_locked(
        self,
        state: dict[str, Any],
        lease: chain_core.ChainLease,
    ) -> tuple[
        dict[str, Any],
        str,
        engine.MergeAdmission | None,
        engine.MergeBootstrapClassification | None,
    ]:
        """Classify the Revision-12 pre-sidecar and surviving-sidecar windows."""

        chain_core._require_merge_integration_control("composite-bootstrap-streaming")
        intent = state.get("integration", {}).get("intent")
        if chain_core._merge_bootstrap_classification_pending(state):
            admission = self._admission_for_refresh(
                state, verb="merge recover"
            )
            pending = self._bootstrap_pending_classification_inputs_locked(
                state, admission
            )
            return state, "classification-pending", admission, pending
        if (
            state.get("state") == "classifying"
            and state.get("integration", {}).get("condition") == "fetch-failed"
            and state.get("candidate") is None
            and state.get("tier") is None
            and not isinstance(state.get("run_binding"), Mapping)
            and isinstance(intent, Mapping)
            and set(intent)
            == {
                "operation",
                "operation_nonce",
                "attempt",
                "result",
                "resolved_tip",
            }
            and intent.get("operation") == "fetch-result"
            and chain_core._valid_nonce(intent.get("operation_nonce"))
            and chain_core._valid_positive_int(intent.get("attempt"))
            and intent.get("result") == "failed"
            and intent.get("resolved_tip") is None
        ):
            raise chain_core._merge_refusal(
                V2ReasonCode.FETCH_FAILED,
                "forge: merge recover refused — fixed target fetch failed",
                expected="merge refresh to begin one fresh bootstrap epoch",
                observed="the prior composite bootstrap did not PASS",
                remediation=(
                    f"forge merge refresh --chain-id {state['chain_id']}"
                ),
                chain=state,
            )
        if (
            not isinstance(intent, Mapping)
            or intent.get("operation") != "fetch"
            or not chain_core._valid_nonce(intent.get("operation_nonce"))
            or not chain_core._valid_positive_int(intent.get("attempt"))
            or chain_core.COMMIT_RE.fullmatch(str(intent.get("pre_fetch_head", ""))) is None
        ):
            raise FrozenError(
                "interrupted merge bootstrap intent is malformed",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        operation_nonce = str(intent["operation_nonce"])
        attempt = int(intent["attempt"])
        run_bound = isinstance(state.get("run_binding"), Mapping)
        admission = self._admission_for_refresh(
            state, verb="merge recover"
        )
        binding = self._recover_merge_bootstrap_scope_binding(
            state, admission, fence=None
        )

        def record_failure(
            sidecar: Mapping[str, Any] | None,
        ) -> dict[str, Any]:
            integration = copy.deepcopy(state["integration"])
            integration.update(
                {
                    "condition": "none" if run_bound else "fetch-failed",
                    "primary_condition": "none",
                    "intent": {
                        "operation": "fetch-result",
                        "operation_nonce": operation_nonce,
                        "attempt": attempt,
                        "result": "failed",
                        "resolved_tip": None,
                    },
                }
            )
            return self._epoch_transition(
                state,
                lease,
                "fetch_result",
                {
                    "delta": {"integration": integration},
                    "scope_fetch_binding": (
                        copy.deepcopy(dict(sidecar))
                        if isinstance(sidecar, Mapping)
                        else None
                    ),
                    "scope_proof": None,
                },
                generation_digest=(
                    str(state["candidate"]["generation_digest"])
                    if isinstance(state.get("candidate"), Mapping)
                    else None
                ),
            )

        if binding is None:
            failed = record_failure(None)
            if not run_bound:
                return failed, "fetch-failed", None, None
            terminal = self._release_to_aborted_locked(
                failed,
                lease,
                reason="run/task scope derivation is invalid",
            )
            raise chain_core._merge_refusal(
                V2ReasonCode.RUN_TASK_BINDING_INVALID,
                "forge: merge recover refused — run/task scope derivation is invalid",
                expected="a surviving authenticated composite-bootstrap sidecar",
                observed="scope-fetch sidecar absent",
                chain=terminal,
            )
        if run_bound:
            failed = record_failure(binding)
            terminal = self._release_to_aborted_locked(
                failed,
                lease,
                reason="run/task scope derivation is invalid",
            )
            raise chain_core._merge_refusal(
                V2ReasonCode.RUN_TASK_BINDING_INVALID,
                "forge: merge recover refused — run/task scope derivation is invalid",
                expected="ordinary abort after the surviving run-bound sidecar",
                observed=str(binding.get("digest")),
                chain=terminal,
            )

        fixed_tip = str(binding["remote_tip"])
        generation_number = (
            int(state["candidate"]["generation"]) + 1
            if isinstance(state.get("candidate"), Mapping)
            else 1
        )
        try:
            candidate = engine._retain_or_advance_merge_candidate(
                admission,
                fixed_tip,
                prior_candidate=state.get("candidate"),
                generation=generation_number,
                diff_output_digest=str(binding["full_patch_output_digest"]),
            )
        except (TypeError, ValueError) as exc:
            raise FrozenError(
                "surviving composite-bootstrap sidecar cannot materialize its generation",
                chain_id=str(state["chain_id"]),
                observed=str(exc),
                schema=REVISION9_OUTPUT_SCHEMA,
            ) from exc
        integration = copy.deepcopy(state["integration"])
        integration.update(
            {
                "condition": "none",
                "primary_condition": "none",
                "intent": {
                    "operation": "fetch-result",
                    "operation_nonce": operation_nonce,
                    "attempt": attempt,
                    "result": "success",
                    "resolved_tip": fixed_tip,
                },
            }
        )
        desired = {
            "candidate": copy.deepcopy(candidate),
            "tier": None,
            "state": "classifying",
            "policy_source": {
                "commit": admission.policy.sha,
                "digest": admission.policy.digest,
            },
            "steps": {},
            "review": (
                {"iteration": state["review"]["iteration"]}
                if isinstance(state.get("review"), Mapping)
                and type(state["review"].get("iteration")) is int
                else {}
            ),
            "approval": {},
            "authorization": {},
            "integration": integration,
        }
        current = self._epoch_transition(
            state,
            lease,
            "fetch_result",
            {
                "delta": {
                    name: value
                    for name, value in desired.items()
                    if state.get(name) != value or name == "state"
                },
                "scope_fetch_binding": copy.deepcopy(dict(binding)),
                "scope_proof": None,
            },
            generation_digest=str(candidate["generation_digest"]),
        )
        pending = self._bootstrap_pending_classification_inputs_locked(
            current, admission
        )
        return current, "classification-pending", admission, pending

    def _recover_classifying_bootstrap_locked(
        self,
        state: dict[str, Any],
        lock: chain_core.CommonRebaseLock,
        lease: chain_core.ChainLease,
    ) -> tuple[
        dict[str, Any],
        str,
        engine.MergeAdmission | None,
        engine.MergeBootstrapClassification | None,
    ]:
        """Finish one interrupted bootstrap from its durable raw child result."""

        del lock
        return self._recover_classifying_bootstrap_v12_locked(state, lease)


    def recover(
        self,
        *,
        continue_rebase: bool = False,
        paths: Sequence[str] | None = None,
        abort_rebase: bool = False,
    ) -> Outcome:
        """Observation-first reconciliation for one dormant merge chain."""

        self._git_no_lazy_fetch_qualification = None
        for control in chain_core._REQUIRED_MERGE_INTEGRATION_CONTROLS:
            chain_core._require_merge_integration_control(control)
        explicit_conflict_mode = bool(continue_rebase or abort_rebase)
        state = (
            self._read_only_recovery_flag_state()
            if explicit_conflict_mode
            else self._load()
        )
        if continue_rebase and abort_rebase:
            raise chain_core._merge_refusal(
                V2ReasonCode.STATE_PRECONDITION,
                "forge: merge recover refused — recovery modes are mutually exclusive",
                chain=state,
            )
        if bool(paths) != bool(continue_rebase):
            raise chain_core._merge_refusal(
                V2ReasonCode.STATE_PRECONDITION,
                "forge: merge recover refused — --continue requires --paths and --paths requires --continue",
                chain=state,
            )
        engine._require_loud_merge_recovery_mode(
            state,
            continue_rebase=continue_rebase,
            abort_rebase=abort_rebase,
        )
        if explicit_conflict_mode:
            state = self._load()
            engine._require_loud_merge_recovery_mode(
                state,
                continue_rebase=continue_rebase,
                abort_rebase=abort_rebase,
            )
        self._halt(state)
        try:
            resumed_release = self._resume_pending_release(state)
        except chain_core.ChainLeaseUnavailable:
            # A crashed writer may have left the release intent and its lease
            # together.  Only the common-lock recovery path below has the
            # death-proof authority to reclaim that lease.
            resumed_release = None
        if resumed_release is not None:
            current, disposition = resumed_release
            historical = disposition == "historical-landed-superseded"
            return engine._success(
                current,
                "merge recovery "
                f"{'historical-landed-superseded' if historical else 'terminal'} "
                f"for chain {current['chain_id']}",
                (
                    "forge merge start --worktree "
                    f"{current['worktree']['path']}"
                    if historical
                    else "none — merge chain closed"
                    if current["state"] == "closed"
                    else "none — merge chain aborted"
                ),
            )
        pending_claim = state.get("worktree", {}).get("claim")
        pending_release = bool(
            isinstance(pending_claim, Mapping)
            and pending_claim.get("status") in {"releasing", "released"}
            and state.get("state") not in {"closed", "aborted"}
        )
        if (
            not pending_release
            and engine._merge_inactive(state)
            and state.get("state") in {"rebasing", "reverifying"}
        ):
            with self.store.event_lock(str(state["chain_id"])):
                inactive_replay = self.store._read_replay_locked(
                    str(state["chain_id"])
                )
            if engine._merge_inactive_epoch_has_no_started_child(
                state, inactive_replay.events
            ):
                raise chain_core._merge_refusal(
                    V2ReasonCode.STATE_PRECONDITION,
                    "forge: merge recover refused — inactive epoch has no started child",
                    expected="status or safe abort after inactivity",
                    observed=str(state["state"]),
                    remediation=f"forge status --chain-id {state['chain_id']}",
                    chain=state,
                )
        if not pending_release and self._recover_can_reach_final_mode(
            state,
            continue_rebase=continue_rebase,
            abort_rebase=abort_rebase,
        ):
            self._prepare_git_no_lazy_fetch_qualification(state)
        binding = state.get("run_binding")
        action = "observed"
        pending_admission: engine.MergeAdmission | None = None
        pending_classification: engine.MergeBootstrapClassification | None = None
        budget = engine._MergeEpochBudget()
        with self.store._journal_outer(
            binding if isinstance(binding, Mapping) else None
        ):
            with self._recording_common_lock(
                Path(str(state["worktree"]["common_dir"])),
                chain_id=str(state["chain_id"]),
                operation="recover",
            ) as common_lock:
                with chain_core.acquire_chain_lease(
                    self.store.root,
                    chain_id=str(state["chain_id"]),
                    session=self.store._session(None),
                    exclusion=common_lock,
                ) as lease:
                    current = self.store.load_locked(
                        str(state["chain_id"]), lease=lease
                    )
                    engine._require_loud_merge_recovery_mode(
                        current,
                        continue_rebase=continue_rebase,
                        abort_rebase=abort_rebase,
                    )
                    claim_status = current.get("worktree", {}).get(
                        "claim", {}
                    ).get("status")
                    if claim_status in {"releasing", "released"} and current[
                        "state"
                    ] not in {"closed", "aborted"}:
                        current, completed_disposition = (
                            self._complete_pending_release_locked(current, lease)
                        )
                        historical = (
                            completed_disposition
                            == "historical-landed-superseded"
                        )
                        return engine._success(
                            current,
                            "merge recovery "
                            f"{'historical-landed-superseded' if historical else 'terminal'} "
                            f"for chain {current['chain_id']}",
                            (
                                "forge merge start --worktree "
                                f"{current['worktree']['path']}"
                                if historical
                                else "none — merge chain closed"
                                if current["state"] == "closed"
                                else "none — merge chain aborted"
                            ),
                        )
                    if engine._merge_inactive(current) and current.get("state") in {
                        "rebasing",
                        "reverifying",
                    }:
                        with self.store.event_lock(str(current["chain_id"])):
                            inactive_replay = self.store._read_replay_locked(
                                str(current["chain_id"])
                            )
                        if engine._merge_inactive_epoch_has_no_started_child(
                            current, inactive_replay.events
                        ):
                            raise chain_core._merge_refusal(
                                V2ReasonCode.STATE_PRECONDITION,
                                "forge: merge recover refused — inactive epoch has no started child",
                                expected="status or safe abort after inactivity",
                                observed=str(current["state"]),
                                remediation=(
                                    "forge status --chain-id "
                                    f"{current['chain_id']}"
                                ),
                                chain=current,
                            )
                    interrupted_candidate_observation = bool(
                        isinstance(
                            current.get("integration", {}).get("intent"),
                            Mapping,
                        )
                        and current["integration"]["intent"].get("schema")
                        == chain_core._MERGE_CANDIDATE_OBSERVATION_SCHEMA
                    )
                    current, _source_intent, observation_restored = (
                        self._restore_candidate_observation_intent_locked(
                            current, lease
                        )
                    )
                    if not observation_restored:
                        current = self._record_foreign_git_locked(
                            current, lease
                        )
                    bootstrap_intent = current.get("integration", {}).get(
                        "intent"
                    )
                    if (
                        isinstance(bootstrap_intent, Mapping)
                        and bootstrap_intent.get("schema")
                        == chain_core._BOOTSTRAP_FETCH_OBSERVATION_SCHEMA
                        and not chain_core._bootstrap_fetch_observation_record_valid(
                            current, bootstrap_intent
                        )
                    ):
                        current = self._record_foreign_git_locked(
                            current, lease
                        )
                    inactive_post_attempt_ready = False
                    if engine._merge_inactive(current) and engine._merge_has_attempt(current):
                        with self.store.event_lock(str(current["chain_id"])):
                            current_replay = self.store._read_replay_locked(
                                str(current["chain_id"])
                            )
                        inactive_post_attempt_ready = (
                            chain_core._merge_inactive_post_attempt_recovery_ready(
                                current, current_replay.events
                            )
                        )
                    if current.get("integration", {}).get("condition") == (
                        "lock-release-failed"
                    ):
                        integration = copy.deepcopy(current["integration"])
                        integration.update(
                            {
                                "condition": integration["primary_condition"],
                                "primary_condition": "none",
                            }
                        )
                        current = self._epoch_transition(
                            current,
                            lease,
                            "lock_release_result",
                            {"delta": {"integration": integration}},
                        )
                        action = "lock-release"
                    elif (
                        inactive_post_attempt_ready
                    ):
                        prior_observation_digest = self._tail_event_digest(
                            current, "push_observed"
                        )
                        current = self._run_remote_observation(
                            current,
                            common_lock,
                            lease,
                            budget,
                            phase="post-push",
                            allow_inactive_observation=True,
                        )
                        fresh_observation_digest = self._tail_event_digest(
                            current, "push_observed"
                        )
                        if fresh_observation_digest == prior_observation_digest:
                            raise FrozenError(
                                "inactive merge recovery did not retain a fresh remote observation",
                                chain_id=str(current["chain_id"]),
                                schema=REVISION9_OUTPUT_SCHEMA,
                            )
                        containment, _containment_vector = chain_core._merge_containment(
                            current
                        )
                        if containment == "older":
                            current = self._release_historical_landing_locked(
                                current,
                                common_lock,
                                lease,
                                observation_event_digest=fresh_observation_digest,
                            )
                            action = "historical-landed-superseded"
                        elif containment == "all-false":
                            action = "inactive-not-landed"
                        else:
                            action = (
                                "pushed"
                                if current.get("state") == "pushed"
                                else "observed"
                            )
                    elif current["state"] == "classifying":
                        if continue_rebase or abort_rebase:
                            self._wrong_state(
                                current,
                                "bare recovery for an interrupted bootstrap",
                                "merge recover",
                            )
                        (
                            current,
                            action,
                            pending_admission,
                            pending_classification,
                        ) = self._recover_classifying_bootstrap_locked(
                            current, common_lock, lease
                        )
                    elif current["state"] == "pushing":
                        retry_candidate = bool(
                            not engine._merge_inactive(current)
                            and chain_core._merge_old_tip_all_false(current)
                            and isinstance(
                                current.get("integration", {}).get("push"),
                                Mapping,
                            )
                            and (
                                current.get("integration", {})
                                .get("push", {})
                                .get("result")
                                is None
                                or isinstance(
                                    current.get("integration", {})
                                    .get("push", {})
                                    .get("result"),
                                    Mapping,
                                )
                            )
                        )
                        prior_observation_digest = self._tail_event_digest(
                            current, "push_observed"
                        )
                        current = self._run_remote_observation(
                            current,
                            common_lock,
                            lease,
                            budget,
                            phase="post-push",
                            budget_member=(
                                "pre_observations" if retry_candidate else None
                            ),
                            allow_inactive_observation=True,
                        )
                        fresh_observation_digest = self._tail_event_digest(
                            current, "push_observed"
                        )
                        containment, _containment_vector = chain_core._merge_containment(current)
                        if (
                            containment == "older"
                            and engine._merge_inactive(current)
                            and fresh_observation_digest != prior_observation_digest
                        ):
                            current = self._release_historical_landing_locked(
                                current,
                                common_lock,
                                lease,
                                observation_event_digest=fresh_observation_digest,
                            )
                            action = "historical-landed-superseded"
                        elif (
                            containment == "all-false"
                            and engine._merge_inactive(current)
                            and fresh_observation_digest
                            != prior_observation_digest
                        ):
                            action = "inactive-not-landed"
                        elif (
                            retry_candidate
                            and fresh_observation_digest
                            != prior_observation_digest
                            and current["state"] == "pushing"
                            and not engine._merge_inactive(current)
                            and chain_core._merge_old_tip_all_false(current)
                        ):
                            current = self._run_epoch_push(
                                current,
                                common_lock,
                                lease,
                                budget,
                                retry=True,
                            )
                        if action not in {
                            "historical-landed-superseded",
                            "inactive-not-landed",
                        }:
                            action = (
                                "pushed"
                                if current["state"] == "pushed"
                                else "observed"
                            )
                    elif current["state"] == "reverification_failed":
                        current, candidate_observation = (
                            self._run_candidate_observation_locked(
                                current,
                                common_lock,
                                lease,
                                verb="merge recover",
                                remote_tip=str(
                                    current["candidate"]["remote_tip"]
                                ),
                                expected_head=str(
                                    current["candidate"]["candidate_head"]
                                ),
                                classify=False,
                            )
                        )
                        _repository, observed_policy, _paths = (
                            _observe_current_merge_candidate(
                                self.ctx,
                                current,
                                verb="merge recover",
                                observation=candidate_observation,
                            )
                        )
                        current = self._begin_epoch(
                            current,
                            lease,
                            retry=True,
                            observed_policy=observed_policy,
                        )
                        current, action = self._finish_recovered_epoch_locked(
                            current, common_lock, lease, budget
                        )
                    elif current["state"] == "reverifying":
                        current, action = self._finish_recovered_epoch_locked(
                            current, common_lock, lease, budget
                        )
                    elif current["state"] == "rebase_conflict":
                        current = self._recover_conflict_locked(
                            current,
                            common_lock,
                            lease,
                            continue_rebase=continue_rebase,
                            abort_rebase=abort_rebase,
                            paths=paths,
                        )
                        if current["state"] == "reverifying":
                            current, action = self._finish_recovered_epoch_locked(
                                current, common_lock, lease, budget
                            )
                        else:
                            action = "conflict"
                    elif current["state"] == "rebasing":
                        intent = current.get("integration", {}).get("intent")
                        plan = current.get("integration", {}).get("epoch", {}).get(
                            "gate_plan"
                        )
                        fetch_observation_phase = bool(
                            isinstance(intent, Mapping)
                            and (
                                intent.get("schema")
                                == chain_core._EPOCH_FETCH_OBSERVATION_SCHEMA
                                or intent.get("schema")
                                == "forge-epoch-ancestry-intent/1"
                                or (
                                    intent.get("schema")
                                    == chain_core._MERGE_CANDIDATE_OBSERVATION_SCHEMA
                                    and isinstance(
                                        intent.get("source_intent"), Mapping
                                    )
                                    and intent.get("source_intent", {}).get(
                                        "schema"
                                    )
                                    == chain_core._EPOCH_FETCH_OBSERVATION_SCHEMA
                                )
                            )
                        )
                        if fetch_observation_phase:
                            current, fetched_tip, unchanged = (
                                self._complete_epoch_fetch_locked(
                                    current, common_lock, lease
                                )
                            )
                            if not unchanged:
                                current = self._run_epoch_rebase(
                                    current,
                                    fetched_tip,
                                    common_lock,
                                    lease,
                                    budget,
                                )
                            current, action = self._finish_recovered_epoch_locked(
                                current, common_lock, lease, budget
                            )
                        elif isinstance(plan, Mapping) and plan.get("status") == "sealed":
                            current, action = self._finish_recovered_epoch_locked(
                                current, common_lock, lease, budget
                            )
                        elif isinstance(intent, Mapping) and (
                            intent.get("operation") in {"rebase", "rebase-result"}
                            or intent.get("operation") == "continue"
                            and isinstance(intent.get("phase"), str)
                            and str(intent["phase"]).startswith(
                                "forge-conflict-observation:"
                            )
                        ):
                            current = self._recover_rebase_observation_locked(
                                current, common_lock, lease
                            )
                            if current["state"] == "reverifying":
                                current, action = self._finish_recovered_epoch_locked(
                                    current, common_lock, lease, budget
                                )
                        elif isinstance(intent, Mapping) and intent.get(
                            "operation"
                        ) == "fetch-result" and intent.get("result") == "success":
                            current = self._run_epoch_rebase(
                                current,
                                str(intent["resolved_tip"]),
                                common_lock,
                                lease,
                                budget,
                            )
                            current, action = self._finish_recovered_epoch_locked(
                                current, common_lock, lease, budget
                            )
                        else:
                            current, fetched_tip, unchanged = self._run_epoch_fetch(
                                current,
                                common_lock,
                                lease,
                                budget,
                                resume_intent=bool(
                                    isinstance(intent, Mapping)
                                    and intent.get("operation") == "fetch"
                                ),
                            )
                            if not unchanged:
                                current = self._run_epoch_rebase(
                                    current,
                                    fetched_tip,
                                    common_lock,
                                    lease,
                                    budget,
                                )
                            current, action = self._finish_recovered_epoch_locked(
                                current, common_lock, lease, budget
                            )
                    elif current["state"] == "authorized" and current.get(
                        "integration", {}
                    ).get("condition") in {
                        "fetch-failed",
                        "remote-moved",
                        "non-fast-forward",
                    }:
                        current = self._begin_epoch(current, lease)
                        current, fetched_tip, unchanged = self._run_epoch_fetch(
                            current, common_lock, lease, budget
                        )
                        if not unchanged:
                            current = self._run_epoch_rebase(
                                current,
                                fetched_tip,
                                common_lock,
                                lease,
                                budget,
                            )
                        current, action = self._finish_recovered_epoch_locked(
                            current, common_lock, lease, budget
                        )
                    elif current.get("integration", {}).get("condition") == (
                        "foreign-git-state"
                    ):
                        current = self._record_foreign_git_locked(current, lease)
                        action = "foreign"
                    elif interrupted_candidate_observation:
                        action = "observed"
                    else:
                        self._wrong_state(
                            current,
                            "a recoverable merge condition or interrupted epoch",
                            "merge recover",
                        )
        if pending_classification is not None:
            if pending_admission is None:
                raise FrozenError(
                    "merge bootstrap recovery lost its classification admission",
                    chain_id=str(current["chain_id"]),
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            current, _generation = self._complete_bootstrap_classification(
                current,
                pending_admission,
                pending_classification,
            )
            action = "classified"
        if current["state"] == "pushing":
            condition = current["integration"]["condition"]
            reason = (
                V2ReasonCode.PUSH_FAILED
                if condition == "push-failed"
                else V2ReasonCode.PUSH_OUTCOME_UNKNOWN
                if condition == "push-outcome-unknown"
                else V2ReasonCode.NON_FAST_FORWARD
                if condition == "non-fast-forward"
                else None
            )
            if reason is not None:
                raise chain_core._merge_refusal(
                    reason,
                    f"forge: merge recover observed {condition}",
                    remediation=f"forge merge recover --chain-id {current['chain_id']}",
                    chain=current,
                )
        next_steps = {
            "pushed": f"forge merge cleanup --chain-id {current['chain_id']}",
            "pushing": f"forge merge recover --chain-id {current['chain_id']}",
            "reviewing": f"forge review request --chain-id {current['chain_id']}",
            "authorized": f"forge merge finalize --chain-id {current['chain_id']}",
            "revising": f"forge merge refresh --chain-id {current['chain_id']}",
            "rebase_conflict": (
                f"forge merge recover --continue --paths <path>... --chain-id {current['chain_id']}"
            ),
            "closed": "none — merge chain closed",
            "aborted": "none — merge chain aborted",
        }
        if action == "historical-landed-superseded":
            next_steps["aborted"] = (
                "forge merge start --worktree "
                f"{current['worktree']['path']}"
            )
        elif action == "inactive-not-landed":
            next_steps["pushing"] = (
                f"forge merge abort --chain-id {current['chain_id']}"
            )
        return engine._success(
            current,
            f"merge recovery {action} for chain {current['chain_id']}",
            next_steps.get(
                str(current["state"]),
                f"forge status --chain-id {current['chain_id']}",
            ),
        )
    cleanup_chain = _engine_cleanup.cleanup_chain

    def finalize(self) -> Outcome:
        """Execute one FR-235 bounded epoch under the ordered lock stack."""

        self._git_no_lazy_fetch_qualification = None
        for control in chain_core._REQUIRED_MERGE_INTEGRATION_CONTROLS:
            chain_core._require_merge_integration_control(control)
        state = self._preflight_lifecycle(self._load(), "merge finalize")
        self._halt(state)
        if state["state"] != "authorized":
            self._wrong_state(state, "authorized", "merge finalize")
        self._prepare_git_no_lazy_fetch_qualification(state)
        binding = state.get("run_binding")
        budget = engine._MergeEpochBudget()
        with self.store._journal_outer(
            binding if isinstance(binding, Mapping) else None
        ):
            with self._recording_common_lock(
                Path(str(state["worktree"]["common_dir"])),
                chain_id=str(state["chain_id"]),
                operation="finalize",
            ) as common_lock:
                with chain_core.acquire_chain_lease(
                    self.store.root,
                    chain_id=str(state["chain_id"]),
                    session=self.store._session(None),
                    exclusion=common_lock,
                ) as lease:
                    current = self.store.load_locked(
                        str(state["chain_id"]), lease=lease
                    )
                    if current["state"] != "authorized":
                        self._wrong_state(current, "authorized", "merge finalize")
                    current, candidate_observation = (
                        self._run_candidate_observation_locked(
                            current,
                            common_lock,
                            lease,
                            verb="merge finalize",
                            remote_tip=str(current["candidate"]["remote_tip"]),
                            expected_head=str(
                                current["candidate"]["candidate_head"]
                            ),
                            classify=False,
                        )
                    )
                    _observe_current_merge_candidate(
                        self.ctx,
                        current,
                        verb="merge finalize",
                        observation=candidate_observation,
                    )
                    starting_generation = str(
                        current["candidate"]["generation_digest"]
                    )
                    current = self._begin_epoch(current, lease)
                    current, fetched_tip, unchanged = self._run_epoch_fetch(
                        current, common_lock, lease, budget
                    )
                    if not unchanged:
                        current = self._run_epoch_rebase(
                            current,
                            fetched_tip,
                            common_lock,
                            lease,
                            budget,
                        )
                    current = self._run_epoch_suite(
                        current, common_lock, lease, budget
                    )
                    if (
                        str(current["candidate"]["generation_digest"])
                        != starting_generation
                    ):
                        current = self._park_integrated_review(current, lease)
                        return engine._success(
                            current,
                            "integrated generation passed its mechanical suite and is parked for fresh review",
                            f"forge review request --chain-id {current['chain_id']}",
                        )
                    current = self._run_remote_observation(
                        current,
                        common_lock,
                        lease,
                        budget,
                        phase="final-prepush",
                    )
                    if current["state"] == "authorized":
                        return engine._success(
                            current,
                            "merge epoch parked after authoritative remote movement",
                            f"forge merge finalize --chain-id {current['chain_id']}",
                        )
                    if current["state"] == "awaiting_approval":
                        raise chain_core._merge_refusal(
                            V2ReasonCode.REMOTE_CHURN,
                            "forge: merge finalize refused — remote churn exhausted the bounded retry counter",
                            remediation=(
                                "forge merge approve --candidate "
                                f"{current['candidate']['candidate_head']} --chain-id {current['chain_id']}"
                            ),
                            chain=current,
                        )
                    if current["state"] not in {"rebasing", "reverifying"}:
                        self._wrong_state(
                            current,
                            "an unchanged post-observation epoch",
                            "merge finalize",
                        )
                    current = self._run_epoch_push(
                        current, common_lock, lease, budget
                    )
        if current["state"] == "pushing":
            return engine._success(
                current,
                "merge push attempt was authoritatively observed as not landed",
                f"forge merge recover --chain-id {current['chain_id']}",
            )
        return engine._success(
            current,
            f"merge candidate {current['candidate']['candidate_head']} is durably pushed",
            f"forge merge cleanup --chain-id {current['chain_id']}",
        )
