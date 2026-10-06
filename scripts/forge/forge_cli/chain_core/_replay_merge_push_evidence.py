"""Authenticate replay merge push evidence; no journal or run authority."""

from __future__ import annotations

from typing import Any, cast

from ._replay_frames import MergePushObservationEvidenceValidFrame
from ._replay_merge_candidates import (
    _merge_current_head_contained,
    _merge_older_head_only_contained,
)
from ._replay_merge_observations import _merge_remote_observation_phase
from ._replay_values import _utc_value
from ._replay_vocabulary import _CONTINUE_REPLAY


def _check_merge_push_observation_clock(
    frame: MergePushObservationEvidenceValidFrame,
) -> Any:
    assert frame.observed is not None
    if frame.event_at is None or frame.deadline is None:
        return False
    frame.inactive = frame.event_at >= frame.deadline
    frame.exists = frame.observed.get("exists")
    return _CONTINUE_REPLAY


def _check_merge_prepush_observation(
    frame: MergePushObservationEvidenceValidFrame,
) -> Any:
    assert frame.observed is not None
    if frame.phase == "final-prepush":
        if (
            frame.inactive
            or frame.before not in {"rebasing", "reverifying"}
            or frame.current_integration.get("push") != frame.prior_integration.get("push")
        ):
            return False
        candidate = frame.current.get("candidate")
        remote_tip = (
            candidate.get("remote_tip") if isinstance(candidate, dict) else None
        )
        if frame.exists is True and frame.observed.get("oid") == remote_tip:
            return bool(
                frame.after == frame.before
                and frame.condition == "none"
                and (frame.movement_count == frame.prior_count)
            )
        if frame.exists in {True, False}:
            frame.next_count = int(frame.prior_count) + 1
            return (
                bool(
                    frame.next_count < 8
                    and frame.after == "authorized"
                    and (frame.condition == "remote-moved")
                    or (
                        frame.next_count == 8
                        and frame.after == "awaiting_approval"
                        and (frame.condition == "remote-churn")
                    )
                )
                and frame.movement_count == frame.next_count
            )
        return bool(
            frame.exists is None
            and frame.after == "authorized"
            and (frame.condition == "fetch-failed")
            and (frame.movement_count == 0)
        )
    frame.prior_push = frame.prior_integration.get("push")
    frame.current_push = frame.current_integration.get("push")
    return _CONTINUE_REPLAY


def _check_merge_postpush_observation(
    frame: MergePushObservationEvidenceValidFrame,
) -> Any:
    assert frame.observed is not None
    if (
        frame.before != "pushing"
        or not isinstance(frame.prior_push, dict)
        or (not isinstance(frame.current_push, dict))
        or any(
            frame.prior_push.get(name) != frame.current_push.get(name)
            for name in (
                "expected_old_tip",
                "intended_head",
                "destination_ref",
                "intended_at",
                "attempted_heads",
            )
        )
        or (
            frame.prior_push.get("result") is not None
            and frame.prior_push.get("result") != frame.current_push.get("result")
        )
    ):
        return False
    result = frame.current_push.get("result")
    frame.classification = (
        result.get("classification") if isinstance(result, dict) else None
    )
    if _merge_current_head_contained(frame.current):
        return bool(
            frame.after == "pushed" and frame.condition == "none" and (frame.movement_count == 0)
        )
    if _merge_older_head_only_contained(frame.current):
        return bool(
            frame.after == (frame.before if frame.inactive else "authorized")
            and frame.condition == "remote-moved"
            and (frame.movement_count == 0)
        )
    vector = frame.observed.get("attempted_head_containment")
    frame.all_false = bool(
        frame.observed.get("contains_intended_head") is False
        and isinstance(vector, list)
        and vector
        and all(isinstance(item, dict) and item.get("contained") is False for item in vector)
    )
    if frame.exists is None:
        return bool(
            frame.after == "pushing"
            and frame.condition == "push-outcome-unknown"
            and (frame.movement_count == 0)
        )
    return _CONTINUE_REPLAY


def _check_merge_push_failure_observation(
    frame: MergePushObservationEvidenceValidFrame,
) -> Any:
    assert frame.current_push is not None
    assert frame.observed is not None
    if not frame.all_false:
        return False
    if frame.inactive:
        expected_inactive_condition = {
            "known-failure": "push-failed",
            "outcome-unknown": "push-outcome-unknown",
        }.get(cast(str, frame.classification), frame.prior_integration.get("condition"))
        return bool(
            frame.after == "pushing"
            and frame.condition == expected_inactive_condition
            and (frame.condition in {"none", "push-failed", "push-outcome-unknown"})
            and (frame.movement_count == 0)
        )
    old_tip_unchanged = bool(
        frame.exists is True
        and frame.observed.get("oid") == frame.current_push.get("expected_old_tip")
    )
    if old_tip_unchanged:
        expected_condition = {
            "known-failure": "push-failed",
            "outcome-unknown": "push-outcome-unknown",
            "non-fast-forward": "non-fast-forward",
        }.get(cast(str, frame.classification), "none")
        return bool(
            frame.after == "pushing"
            and frame.condition == expected_condition
            and (frame.movement_count == 0)
        )
    if frame.classification in {"success", "non-fast-forward"}:
        frame.next_count = int(frame.prior_count) + 1
        expected_condition = (
            "remote-churn"
            if frame.next_count == 8
            else "non-fast-forward"
            if frame.classification == "non-fast-forward"
            else "remote-moved"
        )
        expected_state = "awaiting_approval" if frame.next_count == 8 else "authorized"
        return bool(
            frame.next_count <= 8
            and frame.after == expected_state
            and (frame.condition == expected_condition)
            and (frame.movement_count == frame.next_count)
        )
    return _CONTINUE_REPLAY


def _check_merge_remote_movement_reset(
    frame: MergePushObservationEvidenceValidFrame,
) -> Any:
    assert frame.current_push is not None
    assert frame.observed is not None
    return bool(
        frame.after == "authorized"
        and frame.condition == "remote-moved"
        and (frame.movement_count == 0)
    )


def _check_merge_push_observation_inputs(
    frame: MergePushObservationEvidenceValidFrame,
) -> Any:
    frame.phase = cast(str, _merge_remote_observation_phase(frame.current, frame.context))
    frame.prior_integration = cast(dict[str, Any], frame.prior.get("integration"))
    frame.current_integration = cast(dict[str, Any], frame.current.get("integration"))
    if (
        frame.phase is None
        or not isinstance(frame.prior_integration, dict)
        or (not isinstance(frame.current_integration, dict))
    ):
        return False
    frame.observed = frame.current_integration.get("observed")
    if not isinstance(frame.observed, dict):
        return False
    if any(
        frame.prior_integration.get(name) != frame.current_integration.get(name)
        for name in ("epoch", "pre_rebase", "conflict")
    ):
        return False
    frame.condition = frame.current_integration.get("condition")
    primary = frame.current_integration.get("primary_condition")
    frame.movement_count = cast(int, frame.current_integration.get("remote_movement_count"))
    frame.prior_count = cast(int, frame.prior_integration.get("remote_movement_count"))
    if (
        primary != "none"
        or type(frame.movement_count) is not int
        or type(frame.prior_count) is not int
    ):
        return False
    frame.before = cast(str, frame.prior.get("state"))
    frame.after = cast(str, frame.current.get("state"))
    frame.event_at = _utc_value(frame.event.get("at"))
    frame.deadline = _utc_value(frame.prior.get("inactive_after"))
    return _CONTINUE_REPLAY


def _merge_push_observation_evidence_valid(
    event: dict[str, Any],
    prior: dict[str, Any],
    current: dict[str, Any],
    context: dict[str, Any] | None,
) -> bool:
    frame = MergePushObservationEvidenceValidFrame(
        event=event, prior=prior, current=current, context=context
    )
    for check in (
        _check_merge_push_observation_inputs,
        _check_merge_push_observation_clock,
        _check_merge_prepush_observation,
        _check_merge_postpush_observation,
        _check_merge_push_failure_observation,
        _check_merge_remote_movement_reset,
    ):
        result = check(frame)
        if result is not _CONTINUE_REPLAY:
            return result
    raise AssertionError("replay checks did not terminate")
