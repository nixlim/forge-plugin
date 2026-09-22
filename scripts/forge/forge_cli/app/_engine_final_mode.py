from __future__ import annotations

import copy
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

from forge_cli import chain_core, engine, runtime
from forge_cli.envelope import (
    REVISION9_OUTPUT_SCHEMA,
    FrozenError,
    ReasonCode,
    Refusal,
    V2ReasonCode,
)

if TYPE_CHECKING:
    from forge_cli.app._merge_engine import MergeEngine

def _final_mode_unavailable(
    state: Mapping[str, Any], observed: str
) -> Refusal:
    return chain_core._merge_refusal(
        V2ReasonCode.REBASE_LOCK_UNAVAILABLE,
        "forge: merge finalize refused — final intended HEAD mode is unavailable",
        expected="a complete bounded read of the candidate .forge-manifest blob",
        observed=observed,
        remediation=f"forge merge recover --chain-id {state['chain_id']}",
        chain=state,
    )

def _prepare_git_no_lazy_fetch_qualification(
    self: "MergeEngine", state: Mapping[str, Any]
) -> None:
    """Qualify and rebind Git before this invocation publishes its lock."""

    chain_core._require_merge_integration_control("final-intended-head-mode")
    self._git_no_lazy_fetch_qualification = None
    worktree = Path(str(state["worktree"]["path"]))
    try:
        qualification = engine._qualify_git_no_lazy_fetch(
            worktree, verbose=self.ctx.options.verbose
        )
        engine._require_git_no_lazy_fetch_qualification(
            qualification, worktree, engine._merge_scope_environment()
        )
    except OSError as exc:
        raise self._final_mode_unavailable(state, str(exc)) from exc
    self._git_no_lazy_fetch_qualification = qualification

def _prepare_bootstrap_git_no_lazy_fetch_qualification(
    self: "MergeEngine",
    admission: engine.MergeAdmission,
    *,
    verb: str,
) -> None:
    """Qualify the exact Git selected by the composite before locking."""

    chain_core._require_merge_integration_control("composite-bootstrap-streaming")
    self._git_no_lazy_fetch_qualification = None
    try:
        qualification = engine._qualify_git_no_lazy_fetch(
            admission.worktree,
            verbose=self.ctx.options.verbose,
        )
        engine._require_git_no_lazy_fetch_qualification(
            qualification,
            admission.worktree,
            engine._merge_scope_environment(),
        )
    except OSError as exc:
        run_bound = admission.run_task is not None
        raise chain_core._merge_refusal(
            (
                V2ReasonCode.RUN_TASK_BINDING_INVALID
                if run_bound
                else V2ReasonCode.FETCH_FAILED
            ),
            (
                f"forge: {verb} refused — run/task scope derivation is invalid"
                if run_bound
                else f"forge: {verb} refused — fixed target fetch failed"
            ),
            expected="Git with proven GIT_NO_LAZY_FETCH support",
            observed=str(exc),
        ) from exc
    self._git_no_lazy_fetch_qualification = qualification

def _final_history_mutation_mode(
    self: "MergeEngine", state: Mapping[str, Any], lock: chain_core.CommonRebaseLock
) -> tuple[str | None, str]:
    """Read DM-015 from the exact final intended commit under the lock."""

    chain_core._require_merge_integration_control("final-intended-head-mode")
    candidate = state.get("candidate")
    if not isinstance(candidate, Mapping):
        raise FrozenError(
            "merge final intended HEAD is unavailable",
            chain_id=str(state.get("chain_id") or "") or None,
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    worktree = Path(str(state["worktree"]["path"]))
    candidate_head = str(candidate["candidate_head"])
    argv = [
        "git",
        "cat-file",
        "blob",
        f"{candidate_head}:.forge-manifest",
    ]
    environment = engine._merge_scope_environment()
    try:
        lock.assert_held()
        engine._require_git_no_lazy_fetch_qualification(
            self._git_no_lazy_fetch_qualification,
            worktree,
            environment,
        )
        result = runtime.run_bounded(
            argv,
            cwd=worktree,
            env=environment,
            timeout=runtime.COMMAND_TIMEOUT_SECONDS,
            cap=runtime.OUTPUT_CAP_BYTES,
            verbose=self.ctx.options.verbose,
        )
        lock.assert_held()
    except (OSError, TimeoutError) as exc:
        raise self._final_mode_unavailable(state, str(exc)) from exc
    if result.timed_out or result.output_limit:
        raise chain_core._merge_refusal(
            V2ReasonCode.REBASE_LOCK_UNAVAILABLE,
            "forge: merge finalize refused — final intended HEAD mode is unavailable",
            expected="a complete bounded read of the candidate .forge-manifest blob",
            observed=(
                f"exit={result.returncode}, timeout={result.timed_out}, "
                f"output_limit={result.output_limit}"
            ),
            remediation=f"forge merge recover --chain-id {state['chain_id']}",
            chain=state,
        )
    if result.returncode != 0:
        return None, result.output_digest
    try:
        mode = engine._parse_history_mutation_mode(result.output)
    except ValueError:
        return None, result.output_digest
    return mode, result.output_digest

def _park_invalid_final_history_mode(
    self: "MergeEngine",
    state: dict[str, Any],
    lease: chain_core.ChainLease,
    *,
    manifest_digest: str,
) -> dict[str, Any]:
    integration = copy.deepcopy(state["integration"])
    engine._reset_merge_nonmovement_counter(integration)
    integration.update(
        {
            "condition": "none",
            "primary_condition": "none",
            "epoch": None,
            "intent": {
                "schema": "forge-history-mutation-mode-result/1",
                "operation": "history-mutation-mode",
                "candidate_head": state["candidate"]["candidate_head"],
                "manifest_digest": manifest_digest,
                "result": "invalid",
                "recorded_at": chain_core.iso_z(),
            },
        }
    )
    review = state.get("review")
    iteration = review.get("iteration") if isinstance(review, Mapping) else None
    projection = {
        "state": "revising",
        "review": {"iteration": iteration} if type(iteration) is int else {},
        "approval": {},
        "authorization": {},
        "integration": integration,
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

def _current_merge_authority(state: Mapping[str, Any]) -> bool:
    return chain_core._merge_current_authority_valid(state)

def _recover_can_reach_final_mode(
    cls: "type[MergeEngine]",
    state: Mapping[str, Any],
    *,
    continue_rebase: bool,
    abort_rebase: bool,
) -> bool:
    """Select only recovery tuples that can invoke ``_run_epoch_push``.

        Release, bootstrap, foreign-state, and conflict reconciliation are
        observation-only in this invocation.  A raw rebase observation also
        either restores, conflicts, or creates a generation whose authority is
        cleared, so it cannot reach the final-mode read before parking.

        Explicit conflict modes never receive a push-capable qualification.
        The legacy router can ignore those flags outside the conflict state;
        withholding the token makes any such route fail closed at the final
        read rather than authorizing a push.
        """

    if continue_rebase or abort_rebase:
        return False
    integration = state.get("integration")
    claim = state.get("worktree", {}).get("claim")
    if (
        not isinstance(integration, Mapping)
        or not isinstance(claim, Mapping)
        or claim.get("status") != "owned"
        or integration.get("condition")
        in {"foreign-git-state", "lock-release-failed"}
        or integration.get("primary_condition") != "none"
        or engine._merge_inactive(state)
        or not cls._current_merge_authority(state)
    ):
        return False
    state_name = state.get("state")
    plan = integration.get("epoch")
    gate_plan = plan.get("gate_plan") if isinstance(plan, Mapping) else None
    if state_name == "pushing":
        push = integration.get("push")
        result = push.get("result") if isinstance(push, Mapping) else None
        return bool(
            chain_core._merge_old_tip_all_false(state)
            and isinstance(push, Mapping)
            and (result is None or isinstance(result, Mapping))
            and isinstance(gate_plan, Mapping)
            and gate_plan.get("status") == "sealed"
            and type(gate_plan.get("cursor")) is int
            and isinstance(gate_plan.get("suite"), list)
            and gate_plan["cursor"] == len(gate_plan["suite"])
        )
    if state_name == "reverification_failed":
        return True
    if state_name == "reverifying":
        return bool(
            isinstance(gate_plan, Mapping)
            and gate_plan.get("status") == "sealed"
        )
    if state_name == "authorized":
        return integration.get("condition") in {
            "fetch-failed",
            "remote-moved",
            "non-fast-forward",
        }
    if state_name != "rebasing":
        return False
    intent = integration.get("intent")
    if (
        isinstance(intent, Mapping)
        and intent.get("schema") == chain_core._MERGE_CANDIDATE_OBSERVATION_SCHEMA
        and isinstance(intent.get("source_intent"), Mapping)
    ):
        intent = intent["source_intent"]
    if isinstance(intent, Mapping) and intent.get("schema") == (
        chain_core._EPOCH_FETCH_OBSERVATION_SCHEMA
    ):
        return chain_core._epoch_fetch_observation_passed(intent)
    if isinstance(intent, Mapping) and intent.get("schema") == (
        "forge-epoch-ancestry-intent/1"
    ):
        phase = intent.get("phase")
        return bool(
            phase == "intent"
            or phase == "result"
            and intent.get("child_result", {}).get("contained") is True
        )
    if isinstance(gate_plan, Mapping) and gate_plan.get("status") == "sealed":
        return True
    if not isinstance(intent, Mapping):
        return intent is None
    if intent.get("operation") in {"rebase", "rebase-result"}:
        return False
    if (
        intent.get("operation") == "continue"
        and isinstance(intent.get("phase"), str)
        and str(intent["phase"]).startswith("forge-conflict-observation:")
    ):
        return False
    if (
        intent.get("operation") == "fetch-result"
        and intent.get("result") == "success"
    ):
        return False
    return intent.get("operation") == "fetch"

def _read_only_recovery_flag_state(self: "MergeEngine") -> dict[str, Any]:
    """Read replay truth without repairing bytes before a loud-flag refusal."""

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
    self.store._validate_id(chain_id)
    if self.store.chain_family(chain_id) != "merge":
        raise FrozenError(
            "merge store refused a commit-family chain",
            chain_id=chain_id,
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    with self.store.event_lock(chain_id):
        replay = self.store._read_replay_locked(chain_id)
        return self.store._resolve_replayed_projection(replay)
