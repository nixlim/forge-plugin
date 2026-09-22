from __future__ import annotations

import copy
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

from forge_cli import chain_core, engine, runtime
from forge_cli.envelope import REVISION9_OUTPUT_SCHEMA, FrozenError

if TYPE_CHECKING:
    from forge_cli.app._merge_engine import MergeEngine

def _epoch_replay_context(
    self: "MergeEngine", state: Mapping[str, Any]
) -> dict[str, Any]:
    """Return context only from a replay matching the locked projection."""

    chain_id = str(state["chain_id"])
    with self.store.event_lock(chain_id):
        replay = self.store._read_replay_locked(chain_id)
    if replay.state != state:
        raise FrozenError(
            "merge epoch observation projection diverges from event replay",
            chain_id=chain_id,
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    context = copy.deepcopy(replay.context)
    context["_authenticated_tail_event"] = (
        copy.deepcopy(replay.events[-1]) if replay.events else None
    )
    return context

def _run_carried_successor_ancestry(
    self: "MergeEngine",
    state: dict[str, Any],
    fetched_tip: str,
    lock: chain_core.CommonRebaseLock,
    lease: chain_core.ChainLease,
    *,
    resume_intent: bool = False,
) -> tuple[dict[str, Any], bool | None]:
    """Fence or consume the carried-tip ancestry decision before sealing."""

    chain_core._require_merge_integration_control("successor-ancestry-observation")
    integration = state.get("integration")
    epoch = integration.get("epoch") if isinstance(integration, Mapping) else None
    plan = epoch.get("gate_plan") if isinstance(epoch, Mapping) else None
    candidate = state.get("candidate")
    authorization = state.get("authorization")
    source_intent = (
        integration.get("intent") if isinstance(integration, Mapping) else None
    )
    replay_context = self._epoch_replay_context(state)
    fetch_observation = replay_context.get("epoch_fetch_observation")
    candidate_observation = replay_context.get("candidate_observation")
    raw_evidence = (
        fetch_observation.get("evidence")
        if isinstance(fetch_observation, Mapping)
        else None
    )
    observation_evidence = (
        candidate_observation.get("evidence")
        if isinstance(candidate_observation, Mapping)
        else None
    )
    if (
        state.get("state") != "rebasing"
        or not isinstance(epoch, Mapping)
        or not isinstance(plan, Mapping)
        or plan.get("status") != "unsealed"
        or not isinstance(candidate, Mapping)
        or not isinstance(authorization, Mapping)
        or candidate.get("remote_tip") != fetched_tip
        or authorization.get("candidate_head") != candidate.get("candidate_head")
        or authorization.get("review_verdict") != "PASS"
        or authorization.get("generation_digest")
        == candidate.get("generation_digest")
        or not isinstance(fetch_observation, Mapping)
        or not isinstance(raw_evidence, Mapping)
        or not chain_core._epoch_fetch_observation_record_valid(state, raw_evidence)
        or not chain_core._epoch_fetch_observation_passed(raw_evidence)
        or fetch_observation.get("digest")
        != engine._merge_epoch_fetch_observation_digest(
            self.store, str(state["chain_id"]), raw_evidence
        )
        or not isinstance(candidate_observation, Mapping)
        or not chain_core._merge_candidate_observation_evidence_valid(
            state, observation_evidence
        )
        or candidate_observation.get("source_intent") != raw_evidence
        or candidate_observation.get("evidence_digest")
        != observation_evidence.get("evidence_digest")
        or observation_evidence.get("remote_tip") != fetched_tip
        or observation_evidence.get("expected_head")
        != candidate.get("candidate_head")
        or observation_evidence.get("classify") is not True
    ):
        raise FrozenError(
            "carried successor ancestry observation lacks its exact fetch binding",
            chain_id=str(state["chain_id"]),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    if resume_intent:
        if (
            not chain_core._epoch_ancestry_record_valid(state, source_intent)
            or not isinstance(source_intent, Mapping)
            or source_intent.get("phase") not in {"intent", "result"}
            or source_intent.get("fetch_observation_event_digest")
            != fetch_observation.get("digest")
            or source_intent.get("candidate_observation_digest")
            != candidate_observation.get("evidence_digest")
        ):
            raise FrozenError(
                "interrupted carried successor ancestry intent is malformed",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        if source_intent.get("phase") == "result":
            contained = _replayed_ancestry_containment(replay_context, source_intent, state)
            return state, contained if type(contained) is bool else None
        ancestry_intent = copy.deepcopy(dict(source_intent))
        argv = list(ancestry_intent["argv"])
    else:
        if (
            not isinstance(source_intent, Mapping)
            or source_intent != raw_evidence
            or self._tail_event_digest(state, "condition_recorded")
            != candidate_observation.get("restore_event_digest")
        ):
            raise FrozenError(
                "carried successor ancestry observation lacks its exact raw fetch result",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        argv = chain_core._remote_containment_argv(
            state, fetched_tip, str(candidate["candidate_head"])
        )
        ancestry_intent = {
            "schema": "forge-epoch-ancestry-intent/1",
            "chain_id": state["chain_id"],
            "epoch_intent_digest": epoch["intent_digest"],
            "operation_nonce": epoch["operation_nonce"],
            "generation_digest": candidate["generation_digest"],
            "fetch_observation_event_digest": fetch_observation["digest"],
            "candidate_observation_digest": candidate_observation[
                "evidence_digest"
            ],
            "fetched_tip": fetched_tip,
            "candidate_head": candidate["candidate_head"],
            "argv": argv,
            "phase": "intent",
            "recorded_at": chain_core.iso_z(),
        }
    if not chain_core._epoch_ancestry_record_valid(state, ancestry_intent):
        raise FrozenError(
            "carried successor ancestry intent is malformed",
            chain_id=str(state["chain_id"]),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    if not resume_intent:
        next_integration = copy.deepcopy(state["integration"])
        next_integration["intent"] = ancestry_intent
        state = self._epoch_transition(
            state,
            lease,
            "condition_recorded",
            {"delta": {"integration": next_integration}},
        )
    ancestry_intent_digest = self._tail_event_digest(state, "condition_recorded")

    def intent_current() -> bool:
        try:
            fresh = self.store.load_locked(str(state["chain_id"]), lease=lease)
        except (FrozenError, OSError):
            return False
        return bool(
            fresh.get("state") == "rebasing"
            and fresh.get("integration", {}).get("intent") == ancestry_intent
            and self._tail_event_digest(fresh, "condition_recorded")
            == ancestry_intent_digest
        )

    def persist(result: chain_core.FencedProcessResult) -> None:
        nonlocal state
        ordinary = bool(
            result.authorized
            and type(result.returncode) is int
            and result.returncode in {0, 1}
            and not result.launch_failed
            and not result.timed_out
            and not result.output_limit
            and not result.group_survived
        )
        contained = result.returncode == 0 if ordinary else None
        result_intent = {
            **ancestry_intent,
            "phase": "result",
            "intent_event_digest": ancestry_intent_digest,
            "child_result": {
                "authorized": result.authorized,
                "exit": result.returncode,
                "inflight_digest": result.fence_digest,
                "output_digest": result.output_digest,
                "launch_failed": result.launch_failed,
                "timed_out": result.timed_out,
                "output_limit_exceeded": result.output_limit,
                "group_survived": result.group_survived,
                "contained": contained,
            },
            "recorded_at": chain_core.iso_z(),
        }
        result_integration = copy.deepcopy(state["integration"])
        result_integration["intent"] = result_intent
        state = self._epoch_transition(
            state,
            lease,
            "condition_recorded",
            {"delta": {"integration": result_integration}},
        )

    environment = engine._merge_scope_environment()
    environment.pop("FORGE_SESSION_PID", None)
    result = chain_core.run_fenced_command(
        lock,
        operation="containment",
        intent_digest=ancestry_intent_digest,
        intent_validator=intent_current,
        argv=argv,
        cwd=Path(str(state["worktree"]["path"])),
        persist_result=persist,
        env=environment,
        timeout=runtime.COMMAND_TIMEOUT_SECONDS,
        cap=runtime.OUTPUT_CAP_BYTES,
        verbose=self.ctx.options.verbose,
    )
    contained = _durable_ancestry_containment(state, result)
    return state, contained if type(contained) is bool else None

def _durable_ancestry_containment(state, result):
    durable = state.get("integration", {}).get("intent")
    if (
        not chain_core._epoch_ancestry_record_valid(state, durable)
        or not isinstance(durable, Mapping)
        or durable.get("phase") != "result"
        or durable.get("child_result", {}).get("inflight_digest")
        != result.fence_digest
        or durable.get("child_result", {}).get("output_digest")
        != result.output_digest
    ):
        raise FrozenError(
            "carried successor ancestry result was not durably retained",
            chain_id=str(state["chain_id"]),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    contained = durable["child_result"].get("contained")
    return contained

def _replayed_ancestry_containment(replay_context, source_intent, state):
    replayed = replay_context.get("epoch_ancestry_observation")
    tail = replay_context.get("_authenticated_tail_event")
    recovery_bridge = replay_context.get(
        "recovery_proof_bridge"
    )
    replayed_at_tail = bool(
        isinstance(replayed, Mapping)
        and isinstance(tail, Mapping)
        and replayed.get("digest") == tail.get("digest")
    )
    replayed_before_recovery_proof = bool(
        isinstance(replayed, Mapping)
        and isinstance(tail, Mapping)
        and isinstance(recovery_bridge, Mapping)
        and tail.get("digest")
        == recovery_bridge.get("event_digest")
        and recovery_bridge.get("previous_digest")
        == replayed.get("digest")
        and (
            recovery_bridge.get("operation") == "containment"
            and recovery_bridge.get("intent_digest")
            == source_intent.get("intent_event_digest")
            and recovery_bridge.get("classification")
            == "containment-result-persisted"
            or recovery_bridge.get("operation") is None
            and recovery_bridge.get("intent_digest") is None
            and recovery_bridge.get("classification")
            == "owner-death-only"
        )
    )
    if (
        not isinstance(replayed, Mapping)
        or not (
            replayed_at_tail or replayed_before_recovery_proof
        )
        or replayed.get("evidence") != source_intent
    ):
        raise FrozenError(
            "interrupted carried successor ancestry result is unauthenticated",
            chain_id=str(state["chain_id"]),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    contained = source_intent.get("child_result", {}).get(
        "contained"
    )
    return contained
