from __future__ import annotations

import copy
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

from forge_cli import chain_core, engine, runtime
from forge_cli.envelope import REVISION9_OUTPUT_SCHEMA, FrozenError, Refusal, V2ReasonCode

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
