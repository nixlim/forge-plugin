from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

from forge_cli import chain_core, engine, runtime
from forge_cli.app._candidate_observation import _observe_current_merge_candidate
from forge_cli.envelope import REVISION9_OUTPUT_SCHEMA, FrozenError, V2ReasonCode

if TYPE_CHECKING:
    from forge_cli.app._merge_engine import MergeEngine

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

def _run_epoch_push(
    self: "MergeEngine",
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
