"""Authenticate replay merge lifecycle evidence; no journal or run authority."""

from __future__ import annotations

import copy
import re
from typing import Any, cast

from ._replay_frames import MergeEventEvidenceValidFrame
from ._replay_merge_candidates import (
    _merge_current_head_contained,
    _merge_generation,
    _merge_worktree_claim,
)
from ._replay_merge_observations import _merge_remote_observation_phase
from ._replay_values import _merge_hex, _utc_value
from ._replay_vocabulary import (
    _CONTINUE_REPLAY,
    _MERGE_HISTORICAL_ABORT_EVIDENCE_FIELDS,
    _MERGE_QUARANTINE_EVIDENCE_FIELDS,
)


def _check_merge_terminal_release_link(frame: MergeEventEvidenceValidFrame) -> Any:
    frame.release = frame.context.get("release_intent") if frame.context is not None else None
    released = frame.context.get("release_result") if frame.context is not None else None
    frame.release_payload = (
        frame.release.get("payload") if isinstance(frame.release, dict) else None
    )
    if frame.context is not None and (
        not isinstance(frame.release, dict)
        or not isinstance(released, dict)
        or released.get("digest") != frame.event.get("previous_digest")
        or (not isinstance(frame.release_payload, dict))
        or (frame.release_payload.get("target_terminal") != frame.event_name)
        or (frame.release_payload.get("source_state") != frame.prior.get("state"))
    ):
        return False
    frame.disposition = (
        frame.release_payload.get("terminal_disposition")
        if isinstance(frame.release_payload, dict)
        else None
    )
    return _CONTINUE_REPLAY


def _check_merge_historical_abort_evidence(frame: MergeEventEvidenceValidFrame) -> Any:
    if frame.disposition == "historical-landed-superseded":
        frame.integration = frame.current.get("integration")
        push = frame.integration.get("push") if isinstance(frame.integration, dict) else None
        observed = (
            frame.integration.get("observed") if isinstance(frame.integration, dict) else None
        )
        if (
            frame.event_name != "aborted"
            or set(frame.payload) != set(_MERGE_HISTORICAL_ABORT_EVIDENCE_FIELDS)
            or frame.payload.get("terminal_disposition") != frame.disposition
            or (not isinstance(push, dict))
            or (frame.payload.get("landed_head") != push.get("landed_head"))
            or (frame.payload.get("superseded_head") != push.get("intended_head"))
            or (not isinstance(observed, dict))
            or (
                frame.payload.get("observation_digest")
                not in {observed.get("output_digest"), observed.get("inflight_digest")}
            )
        ):
            return False
    elif any(name in frame.payload for name in _MERGE_HISTORICAL_ABORT_EVIDENCE_FIELDS):
        return False
    return _CONTINUE_REPLAY


def _check_merge_condition_inputs(frame: MergeEventEvidenceValidFrame) -> Any:
    frame.prior_integration = cast(dict[str, Any], frame.prior.get("integration"))
    frame.current_integration = cast(dict[str, Any], frame.current.get("integration"))
    frame.prior_cleanup = cast(dict[str, Any], frame.prior.get("cleanup"))
    frame.current_cleanup = cast(dict[str, Any], frame.current.get("cleanup"))
    return _CONTINUE_REPLAY


def _check_merge_condition_evidence(frame: MergeEventEvidenceValidFrame) -> Any:
    if any(name in frame.payload for name in _MERGE_QUARANTINE_EVIDENCE_FIELDS):
        if (
            frame.payload.get("condition") != "foreign-git-state"
            or not isinstance(frame.payload.get("quarantine"), list)
            or (not frame.payload["quarantine"])
            or (not _merge_hex(frame.payload.get("observation_digest")))
            or (not isinstance(frame.current_integration, dict))
            or (frame.current_integration.get("condition") != "foreign-git-state")
        ):
            return False
    elif not (
        isinstance(frame.prior_integration, dict)
        and isinstance(frame.current_integration, dict)
        and isinstance(frame.prior_cleanup, dict)
        and isinstance(frame.current_cleanup, dict)
    ):
        return False
    else:
        integration_condition_changed = frame.prior_integration.get(
            "condition"
        ) != frame.current_integration.get("condition") or frame.prior_integration.get(
            "primary_condition"
        ) != frame.current_integration.get("primary_condition")
        cleanup_condition_changed = frame.prior_cleanup.get(
            "condition"
        ) != frame.current_cleanup.get("condition")
        if integration_condition_changed == cleanup_condition_changed:
            return False
        if cleanup_condition_changed:
            if (
                frame.current_cleanup.get("condition") != "cleanup-failed"
                or frame.current_integration != frame.prior_integration
            ):
                return False
        else:
            condition = frame.current_integration.get("condition")
            primary = frame.current_integration.get("primary_condition")
            if (
                frame.current_cleanup != frame.prior_cleanup
                or condition == frame.prior_integration.get("condition")
                or condition == "none"
                or (
                    condition == "lock-release-failed"
                    and primary != frame.prior_integration.get("condition")
                )
                or (condition != "lock-release-failed" and primary != "none")
            ):
                return False
    return _CONTINUE_REPLAY


def _check_merge_cleanup_and_lock_evidence(frame: MergeEventEvidenceValidFrame) -> Any:
    if frame.event_name == "cleanup_intent":
        frame.cleanup = frame.current.get("cleanup")
        cleanup_intent = (
            frame.cleanup.get("intent") if isinstance(frame.cleanup, dict) else None
        )
        if (
            frame.prior.get("state") not in {"pushed", "cleanup_pending"}
            or frame.current.get("state") != frame.prior.get("state")
            or (not _merge_current_head_contained(frame.prior))
            or (not _merge_current_head_contained(frame.current))
            or (not isinstance(cleanup_intent, dict))
            or (not isinstance(cleanup_intent.get("operation_nonce"), str))
            or (re.fullmatch("[0-9a-f]{32}", str(cleanup_intent["operation_nonce"])) is None)
            or (
                cleanup_intent.get("generation_digest")
                != frame.event.get("generation_digest")
            )
            or (_utc_value(cleanup_intent.get("started_at")) is None)
        ):
            return False
    elif frame.event_name == "cleanup_result":
        frame.cleanup = frame.current.get("cleanup")
        if (
            frame.prior.get("state") not in {"pushed", "cleanup_pending"}
            or not _merge_current_head_contained(frame.prior)
            or (not _merge_current_head_contained(frame.current))
            or (not isinstance(frame.cleanup, dict))
            or (
                frame.cleanup.get("condition") == "cleanup-failed"
                and frame.current.get("state") != "cleanup_pending"
            )
        ):
            return False
    elif frame.event_name == "lock_release_result":
        frame.prior_integration = cast(dict[str, Any], frame.prior.get("integration"))
        frame.current_integration = cast(dict[str, Any], frame.current.get("integration"))
        if not isinstance(frame.prior_integration, dict) or not isinstance(
            frame.current_integration, dict
        ):
            return False
        retained_keys = set(frame.prior_integration) - {"condition", "primary_condition"}
        if any(
            frame.prior_integration.get(name) != frame.current_integration.get(name)
            for name in retained_keys
        ):
            return False
        failed_release = bool(
            frame.prior_integration.get("condition") != "lock-release-failed"
            and frame.current_integration.get("condition") == "lock-release-failed"
            and (
                frame.current_integration.get("primary_condition")
                == frame.prior_integration.get("condition")
            )
        )
        completed_release = bool(
            frame.prior_integration.get("condition") == "lock-release-failed"
            and frame.current_integration.get("condition")
            == frame.prior_integration.get("primary_condition")
            and (frame.current_integration.get("primary_condition") == "none")
        )
        if not (failed_release or completed_release):
            return False
    return _CONTINUE_REPLAY


def _check_merge_result_intent_binding(frame: MergeEventEvidenceValidFrame) -> Any:
    if (
        not isinstance(frame.admitted, dict)
        or frame.admitted.get("digest") != frame.event.get("previous_digest")
        or (
            frame.admitted.get("generation_digest") != frame.event.get("generation_digest")
            and (not frame.bootstrap_fetch_result)
            and (not frame.successor_generation_result)
        )
        or (frame.admitted.get("admitted_active") is not True)
        or (
            frame.admitted_nonce is not None
            and frame.current_nonce is not None
            and (frame.current_nonce != frame.admitted_nonce)
        )
    ):
        return False
    return _CONTINUE_REPLAY


def _check_merge_epoch_intent_binding(frame: MergeEventEvidenceValidFrame) -> Any:
    if frame.current_epoch is not None:
        if not isinstance(frame.current_epoch, dict):
            return False
        if frame.event_name == "epoch_intent":
            if frame.current_epoch.get("intent_digest") != frame.event.get("digest"):
                return False
        elif (
            not isinstance(frame.replayed_epoch, dict)
            or frame.current_epoch.get("intent_digest") != frame.replayed_epoch.get("digest")
            or frame.current_epoch.get("generation_digest")
            != frame.replayed_epoch.get("generation_digest")
        ):
            return False
    return _CONTINUE_REPLAY


def _check_merge_condition_or_cleanup_evidence(frame: MergeEventEvidenceValidFrame) -> Any:
    if frame.event_name == "condition_recorded":
        result = _check_merge_condition_inputs(frame)
        if result is not _CONTINUE_REPLAY:
            return result
        result = _check_merge_condition_evidence(frame)
        if result is not _CONTINUE_REPLAY:
            return result
    else:
        result = _check_merge_cleanup_and_lock_evidence(frame)
        if result is not _CONTINUE_REPLAY:
            return result
    return _CONTINUE_REPLAY


def _check_merge_result_intent_inputs(frame: MergeEventEvidenceValidFrame) -> Any:
    operation = frame.result_names[frame.event_name]
    frame.admitted = (
        frame.context.get(f"{operation}_intent") if frame.context is not None else None
    )
    frame.integration = frame.current.get("integration")
    frame.cleanup_state = frame.current.get("cleanup")
    if operation == "cleanup":
        current_evidence = (
            frame.cleanup_state.get("intent") if isinstance(frame.cleanup_state, dict) else None
        )
    else:
        current_evidence = (
            frame.integration.get("intent") if isinstance(frame.integration, dict) else None
        )
    admitted_evidence = (
        frame.admitted.get("evidence") if isinstance(frame.admitted, dict) else None
    )
    frame.admitted_nonce = (
        admitted_evidence.get("operation_nonce")
        if isinstance(admitted_evidence, dict)
        else None
    )
    frame.current_nonce = (
        current_evidence.get("operation_nonce")
        if isinstance(current_evidence, dict)
        else None
    )
    frame.bootstrap_fetch_result = bool(
        operation == "fetch"
        and isinstance(frame.admitted, dict)
        and (frame.admitted.get("generation_digest") is None)
        and (frame.prior.get("candidate") is None)
        and (_merge_generation(frame.current.get("candidate")) is not None)
    )
    prior_result_generation = _merge_generation(frame.prior.get("candidate"))
    current_result_generation = _merge_generation(frame.current.get("candidate"))
    frame.successor_generation_result = bool(
        operation in {"fetch", "rebase"}
        and isinstance(frame.admitted, dict)
        and (prior_result_generation is not None)
        and (current_result_generation is not None)
        and (frame.admitted.get("generation_digest") == prior_result_generation[1])
        and (frame.event.get("generation_digest") == current_result_generation[1])
    )
    return _CONTINUE_REPLAY


def _check_merge_event_worktree_inputs(frame: MergeEventEvidenceValidFrame) -> Any:
    frame.event_name = str(frame.event.get("event"))
    frame.payload = cast(dict[str, Any], frame.event.get("payload"))
    if not isinstance(frame.payload, dict):
        return False
    prior_worktree = _merge_worktree_claim(frame.prior)
    current_worktree = _merge_worktree_claim(frame.current)
    if prior_worktree is None or current_worktree is None:
        return False
    prior_identity, frame.prior_claim = prior_worktree
    frame.current_identity, frame.current_claim = current_worktree
    frame.next_context = copy.deepcopy(frame.context) if frame.context is not None else None
    frame.current_integration = cast(dict[str, Any], frame.current.get("integration"))
    frame.current_epoch = (
        frame.current_integration.get("epoch")
        if isinstance(frame.current_integration, dict)
        else None
    )
    frame.replayed_epoch = (
        frame.context.get("epoch_intent") if isinstance(frame.context, dict) else None
    )
    return _CONTINUE_REPLAY


def _check_merge_terminal_or_condition_evidence(frame: MergeEventEvidenceValidFrame) -> Any:
    if frame.event_name in {"closed", "aborted"}:
        result = _check_merge_terminal_release_link(frame)
        if result is not _CONTINUE_REPLAY:
            return result
        result = _check_merge_historical_abort_evidence(frame)
        if result is not _CONTINUE_REPLAY:
            return result
    else:
        result = _check_merge_condition_or_cleanup_evidence(frame)
        if result is not _CONTINUE_REPLAY:
            return result
    return _CONTINUE_REPLAY


def _check_merge_epoch_context(frame: MergeEventEvidenceValidFrame) -> Any:
    assert frame.next_context is not None
    frame.event_at = _utc_value(frame.event.get("at"))
    frame.prior_deadline = _utc_value(frame.prior.get("inactive_after"))
    if frame.event_name == "epoch_intent":
        frame.next_context["epoch_intent"] = {
            "digest": frame.event.get("digest"),
            "generation_digest": frame.event.get("generation_digest"),
            "push_consumed": False,
        }
    if frame.event_name == "push_intent":
        epoch_intent = (
            frame.context.get("epoch_intent") if frame.context is not None else None
        )
        if (
            not isinstance(epoch_intent, dict)
            or epoch_intent.get("generation_digest") != frame.event.get("generation_digest")
            or epoch_intent.get("push_consumed") is True
        ):
            return False
        frame.next_context["epoch_intent"]["push_consumed"] = True
    if (
        frame.event_name == "push_observed"
        and _merge_remote_observation_phase(frame.current, frame.context) == "final-prepush"
    ):
        frame.current_integration = cast(dict[str, Any], frame.current.get("integration"))
        if frame.current.get("state") != frame.prior.get("state") or (
            isinstance(frame.current_integration, dict)
            and frame.current_integration.get("condition") != "none"
        ):
            frame.next_context["epoch_intent"]["push_consumed"] = True
    frame.intent_names = {
        "fetch_intent": "fetch",
        "rebase_intent": "rebase",
        "push_intent": "push",
        "cleanup_intent": "cleanup",
    }
    frame.result_names = {
        "fetch_result": "fetch",
        "rebase_conflict": "rebase",
        "rebase_result": "rebase",
        "cleanup_result": "cleanup",
    }
    return _CONTINUE_REPLAY


def _check_merge_intent_result_context(frame: MergeEventEvidenceValidFrame) -> Any:
    assert frame.next_context is not None
    if frame.event_name in frame.intent_names:
        frame.integration = frame.current.get("integration")
        frame.cleanup_state = frame.current.get("cleanup")
        if frame.event_name == "cleanup_intent":
            intent_value = (
                frame.cleanup_state.get("intent") if isinstance(frame.cleanup_state, dict) else None
            )
        else:
            intent_value = (
                frame.integration.get("intent") if isinstance(frame.integration, dict) else None
            )
        frame.next_context[f"{frame.intent_names[frame.event_name]}_intent"] = {
            "digest": frame.event.get("digest"),
            "generation_digest": frame.event.get("generation_digest"),
            "evidence": copy.deepcopy(intent_value),
            "admitted_active": bool(
                frame.event_at is not None
                and frame.prior_deadline is not None
                and (frame.event_at < frame.prior_deadline)
                or (
                    frame.event_name == "cleanup_intent"
                    and frame.prior.get("state") in {"pushed", "cleanup_pending"}
                    and _merge_current_head_contained(frame.prior)
                )
            ),
        }
    if frame.event_name in frame.result_names:
        result = _check_merge_result_intent_inputs(frame)
        if result is not _CONTINUE_REPLAY:
            return result
        result = _check_merge_result_intent_binding(frame)
        if result is not _CONTINUE_REPLAY:
            return result
    return _CONTINUE_REPLAY
