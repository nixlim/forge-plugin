from __future__ import annotations

import copy
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

from forge_cli import chain_core, engine
from forge_cli.app._candidate_observation import _observe_current_merge_candidate
from forge_cli.envelope import Outcome, V2ReasonCode

if TYPE_CHECKING:
    from forge_cli.app._merge_engine import MergeEngine

def _park_integrated_review(
    self: MergeEngine, state: dict[str, Any], lease: chain_core.ChainLease
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

def _finish_recovered_epoch_locked(
    self: MergeEngine,
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

def finalize(self: MergeEngine) -> Outcome:
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
