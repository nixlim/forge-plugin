from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

from forge_cli import chain_core, engine
from forge_cli.app._candidate_observation import _observe_current_merge_candidate
from forge_cli.envelope import REVISION9_OUTPUT_SCHEMA, FrozenError, Refusal
from forge_cli.policy import sha256_bytes

if TYPE_CHECKING:
    from forge_cli.app._merge_engine import MergeEngine

def _record_foreign_git_locked(
    self: "MergeEngine", state: dict[str, Any], lease: chain_core.ChainLease
) -> dict[str, Any]:
    integration = state.get("integration")
    if not isinstance(integration, Mapping):
        raise FrozenError(
            "merge integration projection is malformed",
            chain_id=str(state["chain_id"]),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    if integration.get("condition") == "foreign-git-state":
        return state
    updated = copy.deepcopy(dict(integration))
    updated.update(
        {"condition": "foreign-git-state", "primary_condition": "none"}
    )
    engine._reset_merge_nonmovement_counter(updated)
    return self._epoch_transition(
        state,
        lease,
        "condition_recorded",
        {"delta": {"integration": updated}},
    )

def _materialize_rebase_success_locked(
    self: "MergeEngine",
    state: dict[str, Any],
    lock: chain_core.CommonRebaseLock,
    lease: chain_core.ChainLease,
    *,
    fetched_tip: str,
    inflight_digest: str,
    output_digest: str,
    observation: Mapping[str, Any],
) -> dict[str, Any]:
    expected_head = str(observation.get("observed_head", ""))
    state, candidate_observation = self._run_candidate_observation_locked(
        state,
        lock,
        lease,
        verb="merge recover",
        remote_tip=fetched_tip,
        expected_head=expected_head,
        classify=True,
    )
    admission = self._admission_from_candidate_observation(
        state,
        candidate_observation,
        verb="merge recover",
        require_current_generation=False,
    )
    generation = engine.bind_merge_candidate_generation(
        self.ctx,
        admission,
        fetched_tip,
        generation=int(state["candidate"]["generation"]) + 1,
        observation=candidate_observation,
    )
    if (
        admission.candidate_head != expected_head
        or generation.candidate.get("candidate_head") != expected_head
        or not engine._merge_rebase_integrated_predicate(state, observation)
    ):
        raise ValueError("rebase observation changed before materialization")
    suite = engine._merge_epoch_suite(
        {
            **state,
            "candidate": generation.candidate,
            "tier": generation.tier,
        },
        admission.policy,
    )
    integration = copy.deepcopy(state["integration"])
    epoch = integration.get("epoch")
    pre_rebase = integration.get("pre_rebase")
    if not isinstance(epoch, Mapping) or not isinstance(pre_rebase, Mapping):
        raise FrozenError(
            "rebase result lacks its durable epoch and pre-rebase identity",
            chain_id=str(state["chain_id"]),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    integration.update(
        {
            "condition": "none",
            "primary_condition": "none",
            "conflict": None,
            "intent": {
                "operation": "rebase-result",
                "operation_nonce": epoch["operation_nonce"],
                "result": "success",
                "pre_operation_head": pre_rebase["head"],
                "rebased_head": generation.candidate["candidate_head"],
                "fetched_tip": fetched_tip,
                "inflight_digest": inflight_digest,
                "output_digest": output_digest,
                "recorded_at": chain_core.iso_z(),
            },
        }
    )
    integration["epoch"]["generation_digest"] = generation.candidate[
        "generation_digest"
    ]
    integration["epoch"]["gate_plan"] = self._sealed_plan(
        {**state, "candidate": generation.candidate},
        admission.policy,
        suite,
    )
    prior_review = state.get("review")
    iteration = (
        prior_review.get("iteration")
        if isinstance(prior_review, Mapping)
        else None
    )
    retained_review = {"iteration": iteration} if type(iteration) is int else {}
    rebase_projection = {
        "state": "reverifying",
        "policy_source": {
            "commit": admission.policy.sha,
            "digest": admission.policy.digest,
        },
        "candidate": copy.deepcopy(generation.candidate),
        "tier": copy.deepcopy(generation.tier),
        "steps": {},
        "review": retained_review,
        "approval": {},
        "authorization": {},
        "integration": integration,
    }
    rebase_delta = {
        name: value
        for name, value in rebase_projection.items()
        if state.get(name) != value
    }
    return self._epoch_transition(
        state,
        lease,
        "rebase_result",
        {"delta": rebase_delta},
        generation_digest=str(generation.candidate["generation_digest"]),
    )

def _recover_rebase_observation_locked(
    self: "MergeEngine",
    state: dict[str, Any],
    lock: chain_core.CommonRebaseLock,
    lease: chain_core.ChainLease,
) -> dict[str, Any]:
    """Classify a crashed rebase from bounded, fenced Git observations."""

    state, restored_intent = (
        self._restore_integrated_rebase_observation_intent_locked(state, lease)
    )
    if restored_intent is None:
        return self._record_foreign_git_locked(state, lease)
    git_dir = Path(str(state["worktree"]["git_dir"]))
    integration = state.get("integration")
    pre_rebase = (
        integration.get("pre_rebase")
        if isinstance(integration, Mapping)
        else None
    )
    epoch = integration.get("epoch") if isinstance(integration, Mapping) else None
    result_class = chain_core._merge_rebase_result_classification(state)
    if (
        not isinstance(pre_rebase, Mapping)
        or not isinstance(epoch, Mapping)
        or result_class == "foreign"
    ):
        return self._record_foreign_git_locked(state, lease)
    metadata: list[str] = []
    for name in (
        "MERGE_HEAD",
        "CHERRY_PICK_HEAD",
        "REVERT_HEAD",
        "BISECT_LOG",
        "rebase-apply",
        "rebase-merge",
        "sequencer",
    ):
        try:
            os.lstat(git_dir / name)
        except FileNotFoundError:
            continue
        except OSError:
            return self._record_foreign_git_locked(state, lease)
        metadata.append(name)
    rebase_live = any(name in metadata for name in ("rebase-merge", "rebase-apply"))
    if rebase_live:
        intent = integration.get("intent")
        exact_nonzero = bool(
            isinstance(intent, Mapping)
            and result_class == "failed"
            and type(intent.get("exit")) is int
            and intent.get("exit") != 0
            and intent.get("launch_failed") is False
            and intent.get("timed_out") is False
            and intent.get("output_limit_exceeded") is False
            and intent.get("group_survived") is False
        )
        if result_class != "absent" and not exact_nonzero:
            return self._record_foreign_git_locked(state, lease)
        state, observation = self._run_conflict_observation_locked(
            state, lock, lease, kind="conflict"
        )
        if observation is None:
            return self._record_foreign_git_locked(state, lease)
        integration = state["integration"]
        intent = integration.get("intent")
        result_class = chain_core._merge_rebase_result_classification(state)
        exact_nonzero = bool(
            isinstance(intent, Mapping)
            and result_class == "failed"
            and type(intent.get("exit")) is int
            and intent.get("exit") != 0
            and intent.get("launch_failed") is False
            and intent.get("timed_out") is False
            and intent.get("output_limit_exceeded") is False
            and intent.get("group_survived") is False
        )
        evidence_digest = sha256_bytes(chain_core.canonical_bytes(observation))
        inflight_digest = (
            str(intent["inflight_digest"])
            if isinstance(intent, Mapping) and exact_nonzero
            else evidence_digest
        )
        output_digest = (
            str(intent["output_digest"])
            if isinstance(intent, Mapping) and exact_nonzero
            else evidence_digest
        )
        updated = copy.deepcopy(dict(integration))
        updated["conflict"] = engine._merge_conflict_record(
            state,
            observation,
            inflight_digest=inflight_digest,
            output_digest=output_digest,
        )
        engine._reset_merge_nonmovement_counter(updated)
        return self._epoch_transition(
            state,
            lease,
            "rebase_conflict",
            {"delta": {"state": "rebase_conflict", "integration": updated}},
        )
    if metadata:
        return self._record_foreign_git_locked(state, lease)
    state, observation = self._run_integrated_rebase_observation_locked(
        state, lock, lease
    )
    if observation is None:
        return self._record_foreign_git_locked(state, lease)
    integration = state.get("integration")
    pre_rebase = (
        integration.get("pre_rebase")
        if isinstance(integration, Mapping)
        else None
    )
    result_class = chain_core._merge_rebase_result_classification(state)
    current_head = str(observation.get("observed_head", ""))
    evidence_digest = str(observation.get("evidence_digest", ""))
    if (
        not isinstance(integration, Mapping)
        or not isinstance(pre_rebase, Mapping)
        or chain_core.SHA256_RE.fullmatch(evidence_digest) is None
        or observation.get("status_empty") is not True
        or observation.get("branch") != state.get("branch")
    ):
        return self._record_foreign_git_locked(state, lease)
    if result_class in {"absent", "success"}:
        try:
            integrated = engine._merge_rebase_integrated_predicate(state, observation)
        except (OSError, ValueError):
            integrated = False
        if integrated:
            intent = integration.get("intent")
            inflight_digest = (
                str(intent["inflight_digest"])
                if isinstance(intent, Mapping) and result_class == "success"
                else evidence_digest
            )
            output_digest = (
                str(intent["output_digest"])
                if isinstance(intent, Mapping) and result_class == "success"
                else evidence_digest
            )
            try:
                return self._materialize_rebase_success_locked(
                    state,
                    lock,
                    lease,
                    fetched_tip=str(pre_rebase["fetched_tip"]),
                    inflight_digest=inflight_digest,
                    output_digest=output_digest,
                    observation=observation,
                )
            except (KeyError, OSError, Refusal, ValueError):
                return self._record_foreign_git_locked(state, lease)
    if current_head == pre_rebase.get("head"):
        try:
            state, candidate_observation = (
                self._run_candidate_observation_locked(
                    state,
                    lock,
                    lease,
                    verb="merge recover",
                    remote_tip=str(state["candidate"]["remote_tip"]),
                    expected_head=str(state["candidate"]["candidate_head"]),
                    classify=False,
                )
            )
            _observe_current_merge_candidate(
                self.ctx,
                state,
                verb="merge recover",
                observation=candidate_observation,
            )
        except (KeyError, OSError, Refusal, ValueError):
            return self._record_foreign_git_locked(state, lease)
        updated = copy.deepcopy(dict(integration))
        if result_class == "failed":
            updated.update(
                {
                    "condition": "rebase-failed",
                    "primary_condition": "none",
                    "epoch": None,
                    "conflict": None,
                }
            )
            next_state = "revising"
        else:
            updated.update(
                {
                    "condition": "none",
                    "primary_condition": "none",
                    "epoch": None,
                    "intent": None,
                    "conflict": None,
                }
            )
            next_state = "authorized"
        engine._reset_merge_nonmovement_counter(updated)
        return self._epoch_transition(
            state,
            lease,
            "rebase_result",
            {"delta": {"state": next_state, "integration": updated}},
        )
    return self._record_foreign_git_locked(state, lease)
