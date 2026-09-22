from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from forge_cli import chain_core, engine, runtime
from forge_cli.envelope import REVISION9_OUTPUT_SCHEMA, FrozenError, Refusal, V2ReasonCode
from forge_cli.policy import sha256_bytes

if TYPE_CHECKING:
    from forge_cli.app._merge_engine import MergeEngine

def _recover_conflict_locked(
    self: MergeEngine,
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
