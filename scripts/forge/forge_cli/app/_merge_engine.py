"""Extracted from scripts/forge/forge_cli/app/__init__.py."""
from __future__ import annotations
import contextlib
import copy
from pathlib import Path
from typing import Any, Mapping, Sequence
from forge_cli import chain_core, engine
from forge_cli.app._candidate_observation import _observe_current_merge_candidate
from forge_cli.envelope import FrozenError, Outcome, REVISION9_OUTPUT_SCHEMA, ReasonCode, Refusal, V2ReasonCode
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
    _record_foreign_git_locked = _engine_rebase_recovery._record_foreign_git_locked
    _restore_integrated_rebase_observation_intent_locked = _engine_epoch_rebase._restore_integrated_rebase_observation_intent_locked
    _run_integrated_rebase_observation_locked = _engine_epoch_rebase._run_integrated_rebase_observation_locked
    _materialize_rebase_success_locked = _engine_rebase_recovery._materialize_rebase_success_locked
    _recover_rebase_observation_locked = _engine_rebase_recovery._recover_rebase_observation_locked

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
    _run_conflict_observation_locked = _engine_conflict_observation._run_conflict_observation_locked
    _recover_conflict_locked = _engine_recover_conflict._recover_conflict_locked

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
