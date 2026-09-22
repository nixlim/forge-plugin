from __future__ import annotations

import copy
import dataclasses
import secrets
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

from forge_cli import chain_core, engine
from forge_cli.app._admission import prepare_merge_admission
from forge_cli.envelope import REVISION9_OUTPUT_SCHEMA, FrozenError, Outcome, V2ReasonCode
from forge_cli.policy import sha256_bytes

if TYPE_CHECKING:
    from forge_cli.app._merge_engine import MergeEngine

def _admission_from_candidate_observation(
    self: "MergeEngine",
    state: Mapping[str, Any],
    observation: Mapping[str, Any],
    *,
    verb: str,
    require_current_generation: bool,
) -> engine.MergeAdmission:
    repository, policy, _paths, _diff, _classification = (
        engine._parse_merge_candidate_observation(
            state,
            observation,
            verb=verb,
            require_current_generation=require_current_generation,
        )
    )
    binding = state.get("run_binding")
    run_task = None
    if isinstance(binding, Mapping):
        run_task = chain_core._prove_merge_run_task_binding(
            Path(str(state["repository"])),
            self.store.common_root,
            str(binding["run_id"]),
            str(binding["task_id"]),
            policy.digest,
        )
        if run_task.binding != dict(binding):
            raise chain_core._merge_refusal(
                V2ReasonCode.RUN_TASK_BINDING_INVALID,
                f"forge: {verb} refused — run/task binding changed during observation",
                expected=str(dict(binding)),
                observed=str(run_task.binding),
                chain=state,
            )
    return engine.MergeAdmission(
        repository=Path(str(state["repository"])),
        worktree=repository.root,
        worktree_identity={
            name: str(state["worktree"][name])
            for name in ("path", "git_dir", "common_dir")
        },
        branch=str(state["branch"]),
        target=copy.deepcopy(dict(state["target"])),
        candidate_head=str(observation["expected_head"]),
        policy=policy,
        declared_tier=(
            str(observation["declared_tier"])
            if observation.get("declared_tier") is not None
            else None
        ),
        run_task=run_task,
        status_output_digest=sha256_bytes(b""),
    )

def _admission_for_refresh(
    self: "MergeEngine",
    state: Mapping[str, Any],
    *,
    observation: Mapping[str, Any] | None = None,
    verb: str = "merge refresh",
) -> engine.MergeAdmission:
    if observation is not None:
        return self._admission_from_candidate_observation(
            state,
            observation,
            verb=verb,
            require_current_generation=True,
        )
    binding = state.get("run_binding")
    options = dataclasses.replace(
        self.ctx.options,
        chain_id=None,
        run_id=(str(binding["run_id"]) if isinstance(binding, Mapping) else None),
    )
    context = chain_core.CommandContext(
        repo=self.ctx.repo,
        store=self.store,
        options=options,
        policy=self.ctx.policy,
    )
    admission = prepare_merge_admission(
        context,
        str(state["worktree"]["path"]),
        None,
        task=(
            str(binding["task_id"])
            if isinstance(binding, Mapping)
            else None
        ),
    )
    if (
        admission.repository != Path(str(state["repository"]))
        or admission.worktree_identity
        != {
            name: state["worktree"][name]
            for name in ("path", "git_dir", "common_dir")
        }
        or admission.branch != state["branch"]
        or admission.target != state["target"]
    ):
        raise chain_core._merge_refusal(
            V2ReasonCode.WORKTREE_INVALID,
            "forge: merge refresh refused — recorded admission identity changed",
            expected="the immutable repository/worktree/branch/target tuple",
            observed=str(admission),
            chain=state,
        )
    return admission

def _refresh_iteration(self: "MergeEngine", state: Mapping[str, Any]) -> int:
    """Apply the ordinary scalar row before review-specific refusals."""

    integration = state.get("integration")
    condition = integration.get("condition") if isinstance(integration, Mapping) else None
    admitted_conditions = {
        ("classifying", "fetch-failed"),
        ("revising", "rebase-failed"),
    }
    if condition != "none" and (state["state"], condition) not in admitted_conditions:
        self._wrong_state(
            state,
            "an ordinary active pre-push tuple or retryable refresh condition",
            "merge refresh",
        )
    if state["state"] not in {
        "classifying",
        "verifying",
        "reviewing",
        "revising",
        "awaiting_approval",
        "authorized",
    }:
        self._wrong_state(state, "an active mutable pre-push state", "merge refresh")
    review = state.get("review")
    iteration = review.get("iteration", 0) if isinstance(review, Mapping) else 0
    if type(iteration) is not int:
        raise FrozenError(
            "merge review iteration is malformed",
            chain_id=str(state["chain_id"]),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    if iteration >= 8:
        raise chain_core._merge_refusal(
            V2ReasonCode.ITERATION_CAP,
            "forge: merge refresh refused — review iteration cap of 8 is final",
            expected="safe abort after the eighth review cycle",
            observed=str(iteration),
            chain=state,
        )
    if isinstance(review, Mapping) and review.get("operator_cosign_required") is True:
        raise chain_core._merge_refusal(
            V2ReasonCode.STATE_PRECONDITION,
            "forge: merge refresh refused — above-MINOR disposition awaits operator co-sign",
            expected="merge approve for the sole outstanding disposition",
            observed="pending finding-disposition",
            chain=state,
        )
    return iteration

def refresh(self: "MergeEngine", *, remote_tip: str | None = None) -> Outcome:
    engine._require_merge_lifecycle_control("admission-priority")
    state = self._preflight_lifecycle(self._load(), "merge refresh")
    self._halt(state)
    self._refresh_iteration(state)
    prelock_admission = self._admission_for_refresh(
        state, verb="merge refresh"
    )
    self._prepare_bootstrap_git_no_lazy_fetch_qualification(
        prelock_admission,
        verb="merge refresh",
    )
    binding = state.get("run_binding")
    with self.store._journal_outer(
        binding if isinstance(binding, Mapping) else None
    ), self._recording_common_lock(
        Path(str(state["worktree"]["common_dir"])),
        chain_id=str(state["chain_id"]),
        operation="refresh",
    ) as common_lock:
        state = self._preflight_lifecycle(self._load(), "merge refresh")
        iteration = self._refresh_iteration(state)
        prior_candidate = state.get("candidate")
        prior_integration = state.get("integration")
        prior_operation = (
            prior_integration.get("intent")
            if isinstance(prior_integration, Mapping)
            else None
        )
        admission_head = (
            str(prior_candidate["candidate_head"])
            if isinstance(prior_candidate, Mapping)
            else str(prior_operation.get("pre_fetch_head", ""))
            if isinstance(prior_operation, Mapping)
            else ""
        )
        admission_tip = (
            str(prior_candidate["remote_tip"])
            if isinstance(prior_candidate, Mapping)
            else admission_head
        )
        admission = self._admission_for_refresh(
            state, verb="merge refresh"
        )
        engine._require_git_no_lazy_fetch_qualification(
            self._git_no_lazy_fetch_qualification,
            admission.worktree,
            engine._merge_scope_environment(),
        )
        prior_intent = state.get("integration", {}).get("intent")
        attempt = 1
        if isinstance(prior_intent, Mapping) and type(
            prior_intent.get("attempt")
        ) is int:
            attempt = int(prior_intent["attempt"]) + 1
        operation_nonce = secrets.token_hex(16)
        scope_request = engine._merge_scope_request(admission)
        if prior_candidate is None:
            state = self.store.transition(
                state,
                "fetch_intent",
                {
                    "repository": str(admission.repository),
                    "worktree": copy.deepcopy(admission.worktree_identity),
                    "branch": admission.branch,
                    "target": copy.deepcopy(admission.target),
                    "pre_fetch_head": admission.candidate_head,
                    "policy_digest": admission.policy.digest,
                    "operation_nonce": operation_nonce,
                    "attempt": attempt,
                    "scope_request": scope_request,
                },
                generation_digest=None,
                at=chain_core.iso_z(),
            )
        else:
            integration = copy.deepcopy(state["integration"])
            engine._reset_merge_nonmovement_counter(integration)
            integration.update(
                {
                    "condition": "none",
                    "primary_condition": "none",
                    "epoch": None,
                    "intent": {
                        "operation": "fetch",
                        "operation_nonce": operation_nonce,
                        "attempt": attempt,
                        "target": copy.deepcopy(admission.target),
                        "pre_fetch_head": admission.candidate_head,
                        "scope_request": scope_request,
                    },
                }
            )
            state = self.store.transition(
                state,
                "fetch_intent",
                {"delta": {"state": "classifying", "integration": integration}},
                generation_digest=str(prior_candidate["generation_digest"]),
                at=chain_core.iso_z(),
            )
        next_number = (
            int(prior_candidate["generation"]) + 1
            if isinstance(prior_candidate, Mapping)
            else 1
        )
        state, pending = self._run_bootstrap_generation(
            state,
            admission,
            common_lock,
            operation_nonce=operation_nonce,
            attempt=attempt,
            remote_tip=remote_tip,
            generation_number=next_number,
            verb="merge refresh",
        )
    state, generation = self._complete_bootstrap_classification(
        state, admission, pending
    )
    candidate = copy.deepcopy(generation.candidate)
    return engine._success(
        state,
        f"merge chain {state['chain_id']} refreshed to generation {candidate['generation']}",
        f"forge merge verify --chain-id {state['chain_id']}",
    )
