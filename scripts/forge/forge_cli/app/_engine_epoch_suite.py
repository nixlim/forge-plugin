from __future__ import annotations

import copy
import os
import re
import sys
from typing import TYPE_CHECKING, Any, Callable, Mapping

from forge_cli import chain_core, engine, runtime
from forge_cli.app._candidate_observation import _observe_current_merge_candidate
from forge_cli.app._mutation_journal import _persist_deferred_mutation_result
from forge_cli.envelope import REVISION9_OUTPUT_SCHEMA, FrozenError, Refusal, V2ReasonCode
from forge_cli.policy import sha256_bytes

if TYPE_CHECKING:
    from forge_cli.app._merge_engine import MergeEngine

def _run_epoch_suite(
    self: "MergeEngine",
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
