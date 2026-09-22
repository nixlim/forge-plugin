from __future__ import annotations

import base64
import copy
from typing import TYPE_CHECKING, Any, Mapping

from forge_cli import chain_core, engine, runtime
from forge_cli.envelope import REVISION9_OUTPUT_SCHEMA, FrozenError, Refusal, V2ReasonCode
from forge_cli.policy import sha256_bytes

if TYPE_CHECKING:
    from forge_cli.app._merge_engine import MergeEngine

def _candidate_observation_transition(
    self: "MergeEngine",
    state: dict[str, Any],
    lease: chain_core.ChainLease | None,
    integration: Mapping[str, Any],
) -> dict[str, Any]:
    payload = {"delta": {"integration": copy.deepcopy(dict(integration))}}
    generation = state.get("candidate")
    generation_digest = (
        str(generation["generation_digest"])
        if isinstance(generation, Mapping)
        else None
    )
    if lease is not None:
        return self._epoch_transition(
            state,
            lease,
            "condition_recorded",
            payload,
            generation_digest=generation_digest,
        )
    return self.store.transition(
        state,
        "condition_recorded",
        payload,
        generation_digest=generation_digest,
        at=chain_core.iso_z(),
    )

def _restore_candidate_observation_intent_locked(
    self: "MergeEngine",
    state: dict[str, Any],
    lease: chain_core.ChainLease | None,
) -> tuple[dict[str, Any], object, bool]:
    integration = state.get("integration")
    intent = integration.get("intent") if isinstance(integration, Mapping) else None
    if not (
        isinstance(intent, Mapping)
        and intent.get("schema") == chain_core._MERGE_CANDIDATE_OBSERVATION_SCHEMA
    ):
        return state, copy.deepcopy(intent), True
    if not chain_core._merge_candidate_observation_record_valid(state, intent):
        return state, None, False
    restored = copy.deepcopy(dict(integration))
    source_intent = copy.deepcopy(intent.get("source_intent"))
    restored["intent"] = source_intent
    return (
        self._candidate_observation_transition(state, lease, restored),
        source_intent,
        True,
    )

def _restore_bootstrap_fetch_observation_locked(
    self: "MergeEngine",
    state: dict[str, Any],
    lease: chain_core.ChainLease | None,
) -> tuple[dict[str, Any], bool]:
    integration = state.get("integration")
    intent = integration.get("intent") if isinstance(integration, Mapping) else None
    if not (
        isinstance(intent, Mapping)
        and intent.get("schema") == chain_core._BOOTSTRAP_FETCH_OBSERVATION_SCHEMA
    ):
        return state, True
    if not chain_core._bootstrap_fetch_observation_record_valid(state, intent):
        return state, False
    restored = copy.deepcopy(dict(integration))
    restored["intent"] = copy.deepcopy(intent.get("source_intent"))
    return self._candidate_observation_transition(state, lease, restored), True

def _run_candidate_observation_locked(
    self: "MergeEngine",
    state: dict[str, Any],
    lock: chain_core.CommonRebaseLock,
    lease: chain_core.ChainLease | None,
    *,
    verb: str,
    remote_tip: str,
    expected_head: str,
    classify: bool,
    declared_tier: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run the closed candidate proof as separately fenced durable reads."""

    chain_core._require_merge_integration_control("observation-first-recovery")
    state, source_intent, restored = (
        self._restore_candidate_observation_intent_locked(state, lease)
    )
    if not restored:
        raise FrozenError(
            "merge candidate observation intent is malformed",
            chain_id=str(state.get("chain_id", "")) or None,
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    specs = chain_core._merge_candidate_observation_step_specs(
        state,
        remote_tip=remote_tip,
        expected_head=expected_head,
        classify=classify,
        declared_tier=declared_tier,
    )
    binding = chain_core._merge_candidate_observation_binding(
        state,
        source_intent,
        verb=verb,
        remote_tip=remote_tip,
        expected_head=expected_head,
        classify=classify,
        declared_tier=declared_tier,
    )
    if specs is None or binding is None:
        raise FrozenError(
            "merge candidate observation request is malformed",
            chain_id=str(state.get("chain_id", "")) or None,
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    records: list[dict[str, Any]] = []
    environment = engine._merge_scope_environment()
    environment.pop("FORGE_SESSION_PID", None)

    def restore_source() -> None:
        nonlocal state
        integration = copy.deepcopy(state["integration"])
        integration["intent"] = copy.deepcopy(source_intent)
        state = self._candidate_observation_transition(
            state, lease, integration
        )

    for step, cwd, argv in specs:
        started_at = chain_core.iso_z()
        generation = state.get("candidate")
        record: dict[str, Any] = {
            "schema": chain_core._MERGE_CANDIDATE_OBSERVATION_SCHEMA,
            "chain_id": state["chain_id"],
            "generation_digest": (
                generation.get("generation_digest")
                if isinstance(generation, Mapping)
                else None
            ),
            "source_intent": copy.deepcopy(source_intent),
            "verb": verb,
            "remote_tip": remote_tip,
            "expected_head": expected_head,
            "classify": classify,
            "declared_tier": declared_tier,
            "observation_binding": binding,
            "stage": "intent",
            "step": step,
            "cwd": str(cwd),
            "argv": list(argv),
            "started_at": started_at,
        }
        integration = copy.deepcopy(state["integration"])
        integration["intent"] = copy.deepcopy(record)
        state = self._candidate_observation_transition(
            state, lease, integration
        )
        intent_digest = self._tail_event_digest(
            state, "condition_recorded"
        )

        def intent_current(expected: Mapping[str, Any] = record) -> bool:
            try:
                current = (
                    self.store.load_locked(
                        str(state["chain_id"]), lease=lease
                    )
                    if lease is not None
                    # The common lock and journal-outer transaction make
                    # this invocation's just-persisted projection the
                    # sole mutable value.  Reloading here can observe its
                    # own not-yet-drained outbox descriptor.
                    else state
                )
            except (FrozenError, OSError, Refusal):
                return False
            return bool(
                current.get("integration", {}).get("intent") == expected
                and engine._merge_event_digest(
                    self.store,
                    str(current["chain_id"]),
                    "condition_recorded",
                )
                == intent_digest
            )

        def persist_observation(result: chain_core.FencedProcessResult) -> None:
            nonlocal state
            durable = {
                **copy.deepcopy(record),
                "stage": "result",
                "child_result": {
                    "authorized": result.authorized,
                    "exit": result.returncode,
                    "inflight_digest": result.fence_digest,
                    "output_digest": result.output_digest,
                    "stored_output_digest": sha256_bytes(result.output),
                    "output_b64": base64.b64encode(result.output).decode(
                        "ascii"
                    ),
                    "launch_failed": result.launch_failed,
                    "timed_out": result.timed_out,
                    "output_limit_exceeded": result.output_limit,
                    "group_survived": result.group_survived,
                },
                "recorded_at": chain_core.iso_z(),
            }
            updated = copy.deepcopy(state["integration"])
            updated["intent"] = durable
            state = self._candidate_observation_transition(
                state, lease, updated
            )

        result = chain_core.run_fenced_command(
            lock,
            operation="containment",
            intent_digest=intent_digest,
            intent_validator=intent_current,
            argv=argv,
            cwd=cwd,
            persist_result=persist_observation,
            env=environment,
            timeout=runtime.COMMAND_TIMEOUT_SECONDS,
            cap=runtime.OUTPUT_CAP_BYTES,
            verbose=self.ctx.options.verbose,
        )
        durable = state.get("integration", {}).get("intent")
        complete = bool(
            isinstance(durable, Mapping)
            and chain_core._merge_candidate_observation_record_valid(state, durable)
            and durable.get("stage") == "result"
            and durable.get("step") == step
            and durable.get("observation_binding") == binding
            and durable.get("child_result", {}).get("authorized") is True
            and durable.get("child_result", {}).get("exit") == 0
            and durable.get("child_result", {}).get("launch_failed") is False
            and durable.get("child_result", {}).get("timed_out") is False
            and durable.get("child_result", {}).get("output_limit_exceeded")
            is False
            and durable.get("child_result", {}).get("group_survived") is False
            and durable.get("child_result", {}).get("inflight_digest")
            == result.fence_digest
            and durable.get("child_result", {}).get("output_digest")
            == result.output_digest
        )
        if not complete:
            restore_source()
            raise chain_core._merge_refusal(
                V2ReasonCode.EVIDENCE_INCOMPLETE,
                f"forge: {verb} refused — candidate observation did not complete",
                expected=f"one complete exit-0 {step} observation",
                observed=(
                    f"exit={result.returncode}, launch={result.launch_failed}, "
                    f"timeout={result.timed_out}, output_limit={result.output_limit}, "
                    f"group_survived={result.group_survived}"
                ),
                chain=state,
            )
        records.append(copy.deepcopy(dict(durable)))
        restore_source()

    evidence = chain_core._merge_candidate_observation_evidence(state, records)
    if evidence is None:
        raise FrozenError(
            "merge candidate observation evidence is incomplete",
            chain_id=str(state["chain_id"]),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    return state, evidence
