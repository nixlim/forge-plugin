"""Authenticate replay merge observations; no journal or run authority."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ._replay_frames import MergeObservationShapeValidFrame
from ._replay_merge_candidates import _merge_generation
from ._replay_values import _merge_hex, _utc_value
from ._replay_vocabulary import _CONTINUE_REPLAY, _MERGE_REMOTE_OBSERVATION_INTENT_FIELDS
from ._state import COMMIT_RE


def _check_merge_observation_envelope(frame: MergeObservationShapeValidFrame) -> Any:
    if not isinstance(frame.observed, dict) or set(frame.observed) != {
        "exists",
        "oid",
        "contains_intended_head",
        "attempted_head_containment",
        "observed_at",
        "inflight_digest",
        "output_digest",
    }:
        return False
    vector = frame.observed.get("attempted_head_containment")
    if (
        frame.observed.get("exists") not in {True, False, None}
        or frame.observed.get("contains_intended_head") not in {True, False, None}
        or _utc_value(frame.observed.get("observed_at")) is None
        or (not _merge_hex(frame.observed.get("inflight_digest")))
        or (not _merge_hex(frame.observed.get("output_digest")))
        or (not isinstance(vector, list))
        or (len(vector) != len(frame.attempted_heads))
        or any(
            (
                not isinstance(item, dict)
                or set(item) != {"head", "contained"}
                or item.get("head") != head
                or (item.get("contained") not in {True, False, None})
                for item, head in zip(vector, frame.attempted_heads, strict=True)
            )
        )
    ):
        return False
    frame.exists = frame.observed.get("exists")
    frame.oid = frame.observed.get("oid")
    frame.contains = frame.observed.get("contains_intended_head")
    frame.vector_values = [item.get("contained") for item in vector if isinstance(item, dict)]
    return _CONTINUE_REPLAY


def _check_merge_observation_containment_values(frame: MergeObservationShapeValidFrame) -> Any:
    if frame.exists is True:
        if (
            not isinstance(frame.oid, str)
            or COMMIT_RE.fullmatch(frame.oid) is None
            or type(frame.contains) is not bool
            or any(type(value) is not bool for value in frame.vector_values)
        ):
            return False
    elif frame.exists is False:
        if (
            frame.oid is not None
            or frame.contains is not False
            or any(value is not False for value in frame.vector_values)
        ):
            return False
    elif (
        frame.oid is not None
        or frame.contains is not None
        or any(value is not None for value in frame.vector_values)
    ):
        return False
    return not frame.vector_values or frame.contains == frame.vector_values[-1]


def _merge_observation_shape_valid(observed: Any, attempted_heads: Sequence[str]) -> bool:
    frame = MergeObservationShapeValidFrame(observed=observed, attempted_heads=attempted_heads)
    for check in (_check_merge_observation_envelope, _check_merge_observation_containment_values):
        result = check(frame)
        if result is not _CONTINUE_REPLAY:
            return result
    raise AssertionError("replay checks did not terminate")


def _merge_remote_observation_phase(
    current: dict[str, Any], context: dict[str, Any] | None
) -> str | None:
    integration = current.get("integration")
    intent = integration.get("intent") if isinstance(integration, dict) else None
    epoch = context.get("epoch_intent") if isinstance(context, dict) else None
    push_intent = context.get("push_intent") if isinstance(context, dict) else None
    generation = _merge_generation(current.get("candidate"))
    if (
        not isinstance(intent, dict)
        or set(intent) != _MERGE_REMOTE_OBSERVATION_INTENT_FIELDS
        or intent.get("schema") != "forge-remote-observation-intent/1"
        or (intent.get("transaction") != "merge")
        or (intent.get("chain_id") != current.get("chain_id"))
        or (intent.get("phase") not in {"final-prepush", "post-push"})
        or (not isinstance(epoch, dict))
        or (not _merge_hex(epoch.get("digest")))
        or (intent.get("attempt_identity") != epoch.get("digest"))
        or (generation is None)
        or (epoch.get("generation_digest") != generation[1])
    ):
        return None
    phase = str(intent["phase"])
    if phase == "final-prepush":
        if intent.get("push_intent_digest") is not None or epoch.get("push_consumed") is not False:
            return None
    elif (
        not isinstance(push_intent, dict)
        or not _merge_hex(push_intent.get("digest"))
        or push_intent.get("generation_digest") != generation[1]
        or (intent.get("push_intent_digest") != push_intent.get("digest"))
        or (epoch.get("push_consumed") is not True)
    ):
        return None
    return phase
