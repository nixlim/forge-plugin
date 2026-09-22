from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

from forge_cli import chain_core, engine, runtime
from forge_cli.app._engine_observe_remote_steps import _persist_remote_observation_delta
from forge_cli.envelope import REVISION9_OUTPUT_SCHEMA, FrozenError, Refusal
from forge_cli.policy import sha256_bytes

if TYPE_CHECKING:
    from forge_cli.app._merge_engine import MergeEngine

def _run_remote_observation(
    self: "MergeEngine",
    state: dict[str, Any],
    lock: chain_core.CommonRebaseLock,
    lease: chain_core.ChainLease,
    budget: engine._MergeEpochBudget,
    *,
    phase: str,
    budget_member: str | None = None,
    allow_inactive_observation: bool = False,
) -> dict[str, Any]:
    selected_budget = budget_member or (
        "pre_observations" if phase == "final-prepush" else "post_observations"
    )
    if budget_member is not None and not (
        phase == "post-push" and budget_member == "pre_observations"
    ):
        raise ValueError("merge recovery observation budget is invalid")
    budget.consume(selected_budget)
    push_intent_digest = (
        self._tail_event_digest(state, "push_intent")
        if phase == "post-push"
        else None
    )
    intent = engine._remote_observation_intent(
        state,
        phase=phase,
        push_intent_digest=push_intent_digest,
    )
    intent_digest = sha256_bytes(chain_core.canonical_bytes(intent))
    integration = copy.deepcopy(state["integration"])
    integration["intent"] = intent
    state = self._epoch_transition(
        state,
        lease,
        "condition_recorded",
        {"delta": {"integration": integration}},
    )

    def intent_current() -> bool:
        try:
            fresh = self.store.load_locked(str(state["chain_id"]), lease=lease)
        except (FrozenError, OSError):
            return False
        return fresh.get("integration", {}).get("intent") == intent

    heads = chain_core._remote_observation_heads(state)
    fetch_argv = chain_core._remote_observation_fetch_argv(state)

    def persist(result: chain_core.FencedProcessResult) -> None:
        nonlocal state
        exists, oid = self._parse_fetched_remote_observation(
            result,
            str(state["target"]["destination_ref"]),
            Path(str(state["worktree"]["git_dir"])),
        )
        progress = {
            **intent,
            "schema": "forge-remote-observation-progress/1",
            "stage": "fetch-result",
            "fetch_result": {
                "argv": list(result.argv),
                "authorized": result.authorized,
                "exit": result.returncode,
                "exists": exists,
                "oid": oid,
                "inflight_digest": result.fence_digest,
                "output_digest": result.output_digest,
                "launch_failed": result.launch_failed,
                "timed_out": result.timed_out,
                "output_limit_exceeded": result.output_limit,
                "group_survived": result.group_survived,
            },
            "heads": list(heads),
            "cursor": 0,
            "head": None,
            "argv": None,
            "completed": [],
            "recorded_at": chain_core.iso_z(),
        }
        next_integration = copy.deepcopy(state["integration"])
        next_integration["intent"] = progress
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
    fetch_result = chain_core.run_fenced_command(
        lock,
        operation="remote-observation",
        intent_digest=intent_digest,
        intent_validator=intent_current,
        argv=fetch_argv,
        cwd=Path(str(state["worktree"]["path"])),
        persist_result=persist,
        env=environment,
        timeout=runtime.COMMAND_TIMEOUT_SECONDS,
        cap=runtime.OUTPUT_CAP_BYTES,
        verbose=self.ctx.options.verbose,
    )
    progress = state.get("integration", {}).get("intent")
    if (
        not chain_core._remote_observation_progress_valid(state, progress)
        or not isinstance(progress, Mapping)
        or progress.get("stage") != "fetch-result"
        or progress.get("fetch_result", {}).get("inflight_digest")
        != fetch_result.fence_digest
        or progress.get("fetch_result", {}).get("output_digest")
        != fetch_result.output_digest
    ):
        raise FrozenError(
            "remote observation fetch result was not durably retained",
            chain_id=str(state["chain_id"]),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    progress = copy.deepcopy(dict(progress))
    fetch_evidence = progress["fetch_result"]
    exists = fetch_evidence["exists"]
    oid = fetch_evidence["oid"]
    environment = dict(environment)
    for cursor, head in enumerate(heads):
        if exists is not True or oid is None or (
            engine._merge_inactive(state) and not allow_inactive_observation
        ):
            break
        if any(
            item.get("contained") is None
            for item in progress.get("completed", [])
        ):
            break
        containment_argv = chain_core._remote_containment_argv(state, head, str(oid))
        containment_intent = {
            **progress,
            "stage": "containment-intent",
            "cursor": cursor,
            "head": head,
            "argv": containment_argv,
            "recorded_at": chain_core.iso_z(),
        }
        next_integration = copy.deepcopy(state["integration"])
        next_integration["intent"] = containment_intent
        state = self._epoch_transition(
            state,
            lease,
            "condition_recorded",
            {"delta": {"integration": next_integration}},
        )
        containment_digest = sha256_bytes(chain_core.canonical_bytes(containment_intent))

        def containment_current() -> bool:
            try:
                fresh = self.store.load_locked(
                    str(state["chain_id"]), lease=lease
                )
            except (FrozenError, OSError):
                return False
            return fresh.get("integration", {}).get("intent") == containment_intent

        def persist_containment(result: chain_core.FencedProcessResult) -> None:
            nonlocal state, progress
            ordinary = bool(
                result.authorized
                and result.returncode in {0, 1}
                and not result.launch_failed
                and not result.timed_out
                and not result.output_limit
                and not result.group_survived
            )
            evidence = {
                "head": head,
                "tip": str(oid),
                "argv": list(result.argv),
                "authorized": result.authorized,
                "exit": result.returncode,
                "inflight_digest": result.fence_digest,
                "output_digest": result.output_digest,
                "launch_failed": result.launch_failed,
                "timed_out": result.timed_out,
                "output_limit_exceeded": result.output_limit,
                "group_survived": result.group_survived,
                "contained": (
                    result.returncode == 0 if ordinary else None
                ),
            }
            completed = copy.deepcopy(containment_intent["completed"])
            completed.append(evidence)
            result_progress = {
                **containment_intent,
                "stage": "containment-result",
                "completed": completed,
                "recorded_at": chain_core.iso_z(),
            }
            result_integration = copy.deepcopy(state["integration"])
            result_integration["intent"] = result_progress
            state = self._epoch_transition(
                state,
                lease,
                "condition_recorded",
                {"delta": {"integration": result_integration}},
            )
            progress = result_progress

        containment_result = chain_core.run_fenced_command(
            lock,
            operation="containment",
            intent_digest=containment_digest,
            intent_validator=containment_current,
            argv=containment_argv,
            cwd=Path(str(state["worktree"]["path"])),
            persist_result=persist_containment,
            env=environment,
            timeout=runtime.COMMAND_TIMEOUT_SECONDS,
            cap=runtime.OUTPUT_CAP_BYTES,
            verbose=self.ctx.options.verbose,
        )
        durable = state.get("integration", {}).get("intent")
        if (
            not chain_core._remote_observation_progress_valid(state, durable)
            or not isinstance(durable, Mapping)
            or durable.get("stage") != "containment-result"
            or durable.get("completed", [{}])[-1].get("inflight_digest")
            != containment_result.fence_digest
            or durable.get("completed", [{}])[-1].get("output_digest")
            != containment_result.output_digest
        ):
            raise FrozenError(
                "remote containment result was not durably retained",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        progress = copy.deepcopy(dict(durable))

    completed = progress.get("completed", [])
    complete_containment = bool(
        exists is True
        and len(completed) == len(heads)
        and all(type(item.get("contained")) is bool for item in completed)
    )
    if complete_containment:
        vector_values = [bool(item["contained"]) for item in completed]
    elif exists is False:
        vector_values = [False for _head in heads]
    else:
        exists = None
        oid = None
        vector_values = [None for _head in heads]

    restored_integration = copy.deepcopy(state["integration"])
    restored_integration["intent"] = intent
    state = self._epoch_transition(
        state,
        lease,
        "condition_recorded",
        {"delta": {"integration": restored_integration}},
    )

    push = state["integration"].get("push")
    attempts = (
        list(push.get("attempted_heads", []))
        if isinstance(push, Mapping)
        else []
    )
    attempted_vector = [
        {"head": head, "contained": contained}
        for head, contained in zip(attempts, vector_values[-len(attempts) :])
    ]
    contains_intended: bool | None = vector_values[-1] if vector_values else None
    observed = {
        "exists": exists,
        "oid": oid,
        "contains_intended_head": contains_intended,
        "attempted_head_containment": attempted_vector,
        "observed_at": chain_core.iso_z(),
        "inflight_digest": fetch_result.fence_digest,
        "output_digest": fetch_result.output_digest,
    }
    next_integration = copy.deepcopy(state["integration"])
    next_integration["observed"] = observed
    prior_count = int(next_integration["remote_movement_count"])
    next_state = str(state["state"])
    carried_generation: engine.MergeCandidateGeneration | None = None
    if phase == "final-prepush":
        if exists is True and oid == state["candidate"]["remote_tip"]:
            next_integration.update(
                {"condition": "none", "primary_condition": "none"}
            )
        elif exists in {True, False}:
            count = prior_count + 1
            next_integration.update(
                {
                    "condition": "remote-churn" if count == 8 else "remote-moved",
                    "primary_condition": "none",
                    "remote_movement_count": count,
                }
            )
            next_state = "awaiting_approval" if count == 8 else "authorized"
            if exists is True and oid is not None:
                try:
                    state, candidate_observation = (
                        self._run_candidate_observation_locked(
                            state,
                            lock,
                            lease,
                            verb="merge finalize",
                            remote_tip=oid,
                            expected_head=str(
                                state["candidate"]["candidate_head"]
                            ),
                            classify=True,
                        )
                    )
                    admission = self._admission_from_candidate_observation(
                        state,
                        candidate_observation,
                        verb="merge finalize",
                        require_current_generation=False,
                    )
                    proposed = engine.bind_merge_candidate_generation(
                        self.ctx,
                        admission,
                        oid,
                        generation=int(state["candidate"]["generation"]) + 1,
                        observation=candidate_observation,
                    )
                    prior_candidate = state["candidate"]
                    if (
                        all(
                            prior_candidate.get(name)
                            == proposed.candidate.get(name)
                            for name in chain_core._MERGE_REMOTE_ONLY_IDENTITY_FIELDS
                        )
                        and proposed.tier == state.get("tier")
                        and not (
                            proposed.scope is not None
                            and proposed.scope.result == "exceeded"
                        )
                    ):
                        carried_generation = proposed
                        next_integration["epoch"] = None
                except (KeyError, OSError, Refusal, ValueError):
                    carried_generation = None
        else:
            engine._reset_merge_nonmovement_counter(next_integration)
            next_integration.update(
                {"condition": "fetch-failed", "primary_condition": "none"}
            )
            next_state = "authorized"
    else:
        assert isinstance(push, Mapping)
        next_push = copy.deepcopy(dict(push))
        landed = None
        for member in reversed(attempted_vector):
            if member["contained"] is True:
                landed = member["head"]
                break
        next_push["landed_head"] = landed
        next_integration["push"] = next_push
        classification = (
            next_push.get("result", {}).get("classification")
            if isinstance(next_push.get("result"), Mapping)
            else None
        )
        current_contained = bool(
            attempts
            and attempts[-1] == state["candidate"]["candidate_head"]
            and contains_intended is True
        )
        if current_contained:
            engine._reset_merge_nonmovement_counter(next_integration)
            next_state = "pushed"
            next_integration.update(
                {"condition": "none", "primary_condition": "none"}
            )
        elif landed is not None:
            engine._reset_merge_nonmovement_counter(next_integration)
            if engine._merge_inactive(state):
                next_state = "pushing"
                next_integration.update(
                    {"condition": "none", "primary_condition": "none"}
                )
            else:
                next_state = "authorized"
                next_integration.update(
                    {
                        "condition": "remote-moved",
                        "primary_condition": "none",
                    }
                )
        elif exists is None:
            engine._reset_merge_nonmovement_counter(next_integration)
            next_state = "pushing"
            next_integration.update(
                {
                    "condition": "push-outcome-unknown",
                    "primary_condition": "none",
                }
            )
        elif exists is True and oid == next_push["expected_old_tip"]:
            engine._reset_merge_nonmovement_counter(next_integration)
            next_integration.update(
                {
                    "condition": (
                        "push-failed"
                        if classification == "known-failure"
                        else "none"
                    ),
                    "primary_condition": "none",
                }
            )
        else:
            independent = classification in {"success", "non-fast-forward"}
            if independent:
                count = prior_count + 1
            else:
                engine._reset_merge_nonmovement_counter(next_integration)
                count = 0
            next_state = "awaiting_approval" if count == 8 else "authorized"
            next_integration.update(
                {
                    "condition": (
                        "remote-churn"
                        if count == 8
                        else "non-fast-forward"
                        if classification == "non-fast-forward"
                        else "remote-moved"
                    ),
                    "primary_condition": "none",
                    "remote_movement_count": count,
                }
            )
        if (
            engine._merge_inactive(state)
            and exists in {True, False}
            and attempted_vector
            and all(member["contained"] is False for member in attempted_vector)
        ):
            next_state = "pushing"
            next_integration.update(
                {
                    "condition": "none",
                    "primary_condition": "none",
                    "remote_movement_count": 0,
                }
            )
    state = _persist_remote_observation_delta(next_integration, next_state, state, carried_generation, self, lease)
    return state
