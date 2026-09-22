from __future__ import annotations

import copy
from typing import Any

from forge_cli import chain_core


def _persist_remote_observation_delta(next_integration, next_state, state, carried_generation, self, lease):
    observation_delta: dict[str, Any] = {"integration": next_integration}
    if next_state != state["state"]:
        observation_delta["state"] = next_state
    if carried_generation is not None:
        observation_delta["candidate"] = copy.deepcopy(
            carried_generation.candidate
        )
        observation_delta["steps"] = copy.deepcopy(state.get("steps"))
    transition_payload: dict[str, Any] = {"delta": observation_delta}
    if carried_generation is not None:
        transition_payload.update(
            {
                "prior_generation_digest": state["candidate"][
                    "generation_digest"
                ],
                "successor_generation_digest": carried_generation.candidate[
                    "generation_digest"
                ],
                "equality_proof": chain_core._merge_remote_only_equality_proof(
                    state["candidate"]
                ),
            }
        )
    state = self._epoch_transition(
        state,
        lease,
        (
            "generation_carried_forward"
            if carried_generation is not None
            else "push_observed"
        ),
        transition_payload,
        generation_digest=(
            str(carried_generation.candidate["generation_digest"])
            if carried_generation is not None
            else None
        ),
    )
    return state
