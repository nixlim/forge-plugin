"""Extracted from scripts/forge/forge_cli/app/__init__.py."""
from __future__ import annotations
import contextlib
from pathlib import Path
from typing import Any, Mapping
from forge_cli import chain_core, engine
from forge_cli.envelope import FrozenError, REVISION9_OUTPUT_SCHEMA, ReasonCode, Refusal, V2ReasonCode
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
from . import _engine_epoch_rebase
from . import _engine_epoch_suite
from . import _engine_epoch_push
from . import _engine_rebase_recovery
from . import _engine_conflict_observation
from . import _engine_recover_conflict
from . import _engine_recover_bootstrap
from . import _engine_recover
from . import _engine_finalize


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
    _recover_merge_bootstrap_scope_binding = _engine_recover_bootstrap._recover_merge_bootstrap_scope_binding
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
    _run_epoch_rebase = _engine_epoch_rebase._run_epoch_rebase
    _run_epoch_suite = _engine_epoch_suite._run_epoch_suite
    _parse_remote_observation = staticmethod(_engine_observation._parse_remote_observation)
    _parse_fetched_remote_observation = staticmethod(_engine_observation._parse_fetched_remote_observation)
    _head_contained = staticmethod(_engine_observation._head_contained)
    _run_remote_observation = _engine_observe_remote._run_remote_observation
    _push_classification = staticmethod(_engine_epoch_push._push_classification)
    _final_history_mutation_mode = _engine_final_mode._final_history_mutation_mode
    _park_invalid_final_history_mode = _engine_final_mode._park_invalid_final_history_mode
    _run_epoch_push = _engine_epoch_push._run_epoch_push
    _park_integrated_review = _engine_finalize._park_integrated_review
    _release_to_closed_locked = _engine_cleanup_child._release_to_closed_locked
    _cleanup_result_locked = _engine_cleanup_child._cleanup_result_locked
    _run_cleanup_child = _engine_cleanup_child._run_cleanup_child
    _current_merge_authority = staticmethod(_engine_final_mode._current_merge_authority)
    _complete_pending_release_locked = _engine_release_pending._complete_pending_release_locked
    _resume_pending_release = _engine_release_pending._resume_pending_release
    _attempted_release_preconditions_locked = _engine_abort._attempted_release_preconditions_locked
    _release_historical_landing_locked = _engine_release_pending._release_historical_landing_locked
    _record_foreign_git_locked = _engine_rebase_recovery._record_foreign_git_locked
    _restore_integrated_rebase_observation_intent_locked = _engine_epoch_rebase._restore_integrated_rebase_observation_intent_locked
    _run_integrated_rebase_observation_locked = _engine_epoch_rebase._run_integrated_rebase_observation_locked
    _materialize_rebase_success_locked = _engine_rebase_recovery._materialize_rebase_success_locked
    _recover_rebase_observation_locked = _engine_rebase_recovery._recover_rebase_observation_locked
    _finish_recovered_epoch_locked = _engine_finalize._finish_recovered_epoch_locked
    _run_conflict_observation_locked = _engine_conflict_observation._run_conflict_observation_locked
    _recover_conflict_locked = _engine_recover_conflict._recover_conflict_locked
    _bootstrap_pending_classification_inputs_locked = _engine_recover_bootstrap._bootstrap_pending_classification_inputs_locked
    _recover_classifying_bootstrap_v12_locked = _engine_recover_bootstrap._recover_classifying_bootstrap_v12_locked
    _recover_classifying_bootstrap_locked = _engine_recover_bootstrap._recover_classifying_bootstrap_locked
    recover = _engine_recover.recover
    cleanup_chain = _engine_cleanup.cleanup_chain
    finalize = _engine_finalize.finalize
