"""Authenticate replay merge transitions; no journal or run authority."""

from __future__ import annotations

import copy
import datetime as dt
import re
from typing import Any, cast

from ._replay_frames import MergeCompleteTupleValidFrame, MergeTransitionValidFrame
from ._replay_merge_authority import (
    _merge_finding_cosign_current,
    _merge_gate4_approval_current,
    _merge_gate4_summary_current,
    _merge_introduced_disposition_valid,
    _merge_introduced_gate_fact,
    _merge_invalidated_review_projection,
    _merge_iteration_cap_residual_current,
    _merge_mechanical_gates_current,
    _merge_pending_disposition_cosign,
    _merge_remote_churn_approval_current,
    _merge_review_request_current,
    _merge_review_verdict_current,
    _review_binding_for_state,
)
from ._replay_merge_candidates import (
    _merge_generation,
    _merge_review_iteration,
    _merge_worktree_claim,
)
from ._replay_merge_event_evidence import _merge_event_evidence_valid
from ._replay_merge_observations import _merge_remote_observation_phase
from ._replay_merge_payload import _merge_payload_delta
from ._replay_merge_push_evidence import _merge_push_observation_evidence_valid
from ._replay_merge_state import _merge_state_edge_valid
from ._replay_state_shape import _state_shape_valid
from ._replay_values import _utc_value
from ._replay_vocabulary import (
    _CONTINUE_REPLAY,
    _MERGE_BOOTSTRAP_EVENTS,
    _MERGE_DERIVED_STATE_FIELDS,
    _MERGE_EVENT_NAMES,
    _MERGE_EVENT_REQUIRED_CHANGES,
    _MERGE_EVENT_TOP_LEVEL_CHANGES,
    _MERGE_INITIAL_DELTA_FIELDS,
    _MERGE_NONTERMINAL_STATES,
    _MERGE_STATE_KEYS,
)


def _check_merge_claim_lifecycle(frame: MergeTransitionValidFrame) -> Any:
    if frame.event_name == "ownership_claimed":
        if not (
            frame.prior_status == "unpublished"
            and frame.current_status == "owned"
            and (frame.prior_claim.get("path") == frame.current_claim.get("path"))
            and (type(frame.current_claim.get("inode")) is int)
            and isinstance(frame.current_claim.get("digest"), str)
        ):
            return False
    elif frame.event_name == "ownership_release_intent":
        expected_claim = copy.deepcopy(frame.prior_claim)
        expected_claim["status"] = "releasing"
        if not (
            frame.prior_status in {"unpublished", "owned"}
            and frame.current_claim == expected_claim
            and isinstance(frame.prior_claim.get("digest"), str)
        ):
            return False
    elif frame.event_name == "ownership_released":
        expected_claim = copy.deepcopy(frame.prior_claim)
        expected_claim["status"] = "released"
        if frame.prior_status != "releasing" or frame.current_claim != expected_claim:
            return False
    elif frame.event_name in {"aborted", "closed"}:
        if (
            frame.prior_status != frame.current_status
            or frame.current_status != "released"
            or (
                frame.event_name == "aborted"
                and frame.before_state in {"pushed", "cleanup_pending"}
            )
        ):
            return False
    elif frame.current_claim != frame.prior_claim:
        return False
    return _CONTINUE_REPLAY


def _check_merge_initial_state_and_clock(frame: MergeTransitionValidFrame) -> Any:
    assert frame.event_at is not None
    if frame.current_worktree is None:
        return False
    frame._current_worktree, frame.current_claim = frame.current_worktree
    if frame.prior is None:
        owner = frame.current.get("owner")
        integration = frame.current.get("integration")
        return bool(
            frame.event.get("sequence") == 1
            and frame.event_name == "chain_started"
            and (set(frame.current) - {"run_binding", "journal_outbox"} == _MERGE_STATE_KEYS)
            and (
                set(frame.delta) - {"run_binding", "journal_outbox"} == _MERGE_INITIAL_DELTA_FIELDS
            )
            and all((frame.current.get(name) == value for name, value in frame.delta.items()))
            and (frame.current.get("schema") == "forge-merge-chain/1")
            and (frame.current.get("chain_id") == frame.event.get("chain_id"))
            and (frame.current.get("kind") == "merge")
            and (frame.current.get("state") == "classifying")
            and (frame.current.get("created_at") == frame.event.get("at"))
            and (frame.inactive_after == frame.event_at + dt.timedelta(hours=24))
            and (frame.current.get("candidate") is None)
            and (frame.current.get("tier") is None)
            and (frame.current.get("steps") == {})
            and (frame.current.get("review") == {})
            and (frame.current.get("approval") == {})
            and (frame.current.get("authorization") == {})
            and isinstance(owner, dict)
            and (set(owner) == {"pid", "host", "session", "started_at"})
            and (type(owner.get("pid")) is int)
            and (int(owner["pid"]) > 0)
            and isinstance(owner.get("host"), str)
            and bool(owner["host"])
            and isinstance(owner.get("session"), str)
            and bool(owner["session"])
            and (owner.get("started_at") == frame.current.get("created_at"))
            and (
                integration
                == {
                    "condition": "none",
                    "primary_condition": "none",
                    "epoch": None,
                    "remote_movement_count": 0,
                    "intent": None,
                    "observed": None,
                    "pre_rebase": None,
                    "conflict": None,
                    "push": None,
                }
            )
            and (frame.current.get("cleanup") == {"condition": "none"})
            and (frame.current_claim.get("status") == "unpublished")
            and (frame.current_claim.get("digest") is None)
            and (frame.current_claim.get("inode") is None)
        )
    if (
        frame.event_name == "chain_started"
        or set(frame.prior) - {"run_binding", "journal_outbox"} != _MERGE_STATE_KEYS
        or frame.context is None
    ):
        return False
    prior_at = _utc_value(frame.prior.get("last_event_at"))
    prior_inactive_after = _utc_value(frame.prior.get("inactive_after"))
    if (
        prior_at is None
        or prior_inactive_after is None
        or frame.event_at < prior_at
    ):
        return False
    frame.prior_inactive = frame.event_at >= prior_inactive_after
    frame.expected_inactive_after = (
        prior_inactive_after
        if frame.prior_inactive
        else frame.event_at + dt.timedelta(hours=24)
    )
    return _CONTINUE_REPLAY


def _check_merge_epoch_lifecycle(frame: MergeTransitionValidFrame) -> Any:
    if (
        frame.event_name not in {"push_intent", "push_observed"}
        and frame.current_push_history != frame.prior_push_history
    ):
        return False
    if frame.event_name == "epoch_intent":
        if frame.current_epoch is None or frame.current_epoch == frame.prior_epoch:
            return False
    elif frame.current_epoch != frame.prior_epoch:
        epoch_parked = frame.after_state in {
            "authorized",
            "awaiting_approval",
            "revising",
            "reverification_failed",
            "pushed",
            "cleanup_pending",
            "closed",
            "aborted",
        }
        if frame.current_epoch is not None or not (
            frame.event_name
            in {"generation_refreshed", "generation_carried_forward", "push_intent"}
            or epoch_parked
        ):
            return False
    if frame.event_name == "push_intent" and frame.prior_epoch is None:
        return False
    return _CONTINUE_REPLAY


def _check_merge_push_intent_history(frame: MergeTransitionValidFrame) -> Any:
    if frame.event_name == "push_intent":
        prior_push = (
            frame.prior_integration.get("push")
            if isinstance(frame.prior_integration, dict)
            else None
        )
        push = (
            frame.current_integration.get("push")
            if isinstance(frame.current_integration, dict)
            else None
        )
        attempts = push.get("attempted_heads") if isinstance(push, dict) else None
        prior_attempts = (
            prior_push.get("attempted_heads") if isinstance(prior_push, dict) else []
        )
        candidate = frame.current.get("candidate")
        integration_intent = (
            frame.current_integration.get("intent")
            if isinstance(frame.current_integration, dict)
            else None
        )
        expected_old_landed = (
            prior_push.get("landed_head") if isinstance(prior_push, dict) else None
        )
        if (
            not isinstance(push, dict)
            or not isinstance(attempts, list)
            or (not attempts)
            or (not isinstance(prior_attempts, list))
            or (not isinstance(candidate, dict))
            or (push.get("expected_old_tip") != candidate.get("remote_tip"))
            or (push.get("intended_head") != candidate.get("candidate_head"))
            or (push.get("destination_ref") != candidate.get("destination_ref"))
            or (push.get("intended_at") != frame.event.get("at"))
            or (push.get("result") is not None)
            or (push.get("landed_head") != expected_old_landed)
            or (attempts[-1] != push.get("intended_head"))
            or (attempts != [*prior_attempts, push.get("intended_head")])
            or (not isinstance(integration_intent, dict))
            or (integration_intent.get("operation") != "push")
            or (not isinstance(frame.current_epoch, dict))
            or (
                integration_intent.get("operation_nonce")
                != frame.current_epoch.get("operation_nonce")
            )
            or (frame.current_integration.get("observed") is not None)
        ):
            return False
    return _CONTINUE_REPLAY


def _check_merge_ownership_intent_and_epoch_inputs(frame: MergeTransitionValidFrame) -> Any:
    assert frame.prior is not None
    if frame.event_name == "ownership_intent":
        if not (
            frame.prior_status == frame.current_status == "unpublished"
            and frame.prior_claim.get("path") == frame.current_claim.get("path")
            and (frame.prior_claim.get("inode") is None)
            and (frame.current_claim.get("inode") is None)
            and (frame.current_claim.get("digest") != frame.prior_claim.get("digest"))
            and isinstance(frame.current_claim.get("digest"), str)
        ):
            return False
    else:
        result = _check_merge_claim_lifecycle(frame)
        if result is not _CONTINUE_REPLAY:
            return result
    frame.prior_integration = cast(dict[str, Any], frame.prior.get("integration"))
    frame.current_integration = cast(dict[str, Any], frame.current.get("integration"))
    frame.prior_epoch = (
        frame.prior_integration.get("epoch") if isinstance(frame.prior_integration, dict) else None
    )
    frame.current_epoch = (
        frame.current_integration.get("epoch")
        if isinstance(frame.current_integration, dict)
        else None
    )
    frame.prior_push_history = (
        frame.prior_integration.get("push") if isinstance(frame.prior_integration, dict) else None
    )
    frame.current_push_history = (
        frame.current_integration.get("push")
        if isinstance(frame.current_integration, dict)
        else None
    )
    return _CONTINUE_REPLAY


def _check_merge_immutable_identity(frame: MergeTransitionValidFrame) -> Any:
    assert frame.prior is not None
    if frame.inactive_after != frame.expected_inactive_after:
        return False
    immutable = (
        "schema",
        "chain_id",
        "kind",
        "created_at",
        "owner",
        "run",
        "repository",
        "branch",
        "target",
    )
    if any(frame.prior.get(name) != frame.current.get(name) for name in immutable):
        return False
    prior_worktree = _merge_worktree_claim(frame.prior)
    if prior_worktree is None:
        return False
    prior_worktree_value, frame.prior_claim = prior_worktree
    if any(
        prior_worktree_value.get(name) != frame._current_worktree.get(name)
        for name in ("path", "git_dir", "common_dir")
    ):
        return False
    frame.prior_claim_status = cast(str, frame.prior_claim.get("status"))
    return _CONTINUE_REPLAY


def _check_merge_transition_delta(frame: MergeTransitionValidFrame) -> Any:
    assert frame.prior is not None
    if frame.prior_claim_status == "releasing" and frame.event_name != "ownership_released":
        return False
    if (
        frame.prior_claim_status == "released"
        and frame.prior.get("state") in _MERGE_NONTERMINAL_STATES
        and (frame.event_name not in {"closed", "aborted"})
    ):
        return False
    changed = {
        name
        for name in _MERGE_STATE_KEYS - _MERGE_DERIVED_STATE_FIELDS
        if frame.prior.get(name) != frame.current.get(name)
    }
    if frame.is_receipt:
        if changed:
            return False
    else:
        required_changes = _MERGE_EVENT_REQUIRED_CHANGES.get(
            str(frame.event_name), frozenset()
        )
        if (
            set(frame.delta) != changed
            or any((frame.current.get(name) != value for name, value in frame.delta.items()))
            or (not required_changes <= changed)
            or (not changed <= _MERGE_EVENT_TOP_LEVEL_CHANGES[frame.event_name])
        ):
            return False
    frame.before_state = cast(str, frame.prior.get("state"))
    frame.after_state = cast(str, frame.current.get("state"))
    frame.observation_phase = (
        _merge_remote_observation_phase(frame.current, frame.context)
        if frame.event_name == "push_observed"
        else None
    )
    return _CONTINUE_REPLAY


def _check_merge_generation_identity_change(frame: MergeTransitionValidFrame) -> Any:
    assert frame.prior is not None
    if frame.prior_generation is None or frame.current_generation is None:
        return False
    else:
        before = frame.prior_generation[0]
        after = frame.current_generation[0]
        before_identity = {
            name: before[name] for name in before if name != "generation"
        }
        after_identity = {
            name: after[name] for name in after if name != "generation"
        }
        if before_identity == after_identity:
            if frame.current.get("candidate") != frame.prior.get("candidate"):
                return False
            invalidates_evidence = frame.event_name == "generation_refreshed"
        else:
            if after.get("generation") != int(
                before["generation"]
            ) + 1 or frame.event_name not in {
                "fetch_result",
                "generation_refreshed",
                "generation_carried_forward",
                "rebase_result",
            }:
                return False
            if frame.event_name == "generation_carried_forward":
                identity_changes = {
                    name
                    for name in before_identity
                    if before_identity[name] != after_identity[name]
                }
                if identity_changes != {"remote_tip"}:
                    return False
            invalidates_evidence = frame.event_name != "generation_carried_forward"
        if invalidates_evidence:
            retained_review = _merge_invalidated_review_projection(frame.prior)
            if retained_review is None or any(
                (
                    frame.current.get(name) != empty
                    for name, empty in (
                        ("steps", {}),
                        ("review", retained_review),
                        ("approval", {}),
                        ("authorization", {}),
                    )
                )
            ):
                return False
    return _CONTINUE_REPLAY


def _check_merge_review_iteration_transition(frame: MergeCompleteTupleValidFrame) -> Any:
    frame.prior_iteration = _merge_review_iteration(frame.prior)
    frame.current_iteration = _merge_review_iteration(frame.current)
    if frame.prior_iteration is None or frame.current_iteration is None:
        return False
    frame.before = cast(str, frame.prior.get("state"))
    frame.after = cast(str, frame.current.get("state"))
    if frame.event_name == "gate_recorded" and frame.after == "reviewing":
        return _merge_mechanical_gates_current(frame.current, frame.context)
    if frame.event_name == "reverification_result" and frame.after == "reviewing":
        return _merge_mechanical_gates_current(frame.current, frame.context)
    if frame.event_name == "review_requested":
        frame.current_review = cast(dict[str, Any], frame.current.get("review"))
        return bool(
            frame.prior_iteration < 8
            and frame.current_iteration == frame.prior_iteration + 1
            and isinstance(frame.current_review, dict)
            and (set(frame.current_review) == {"iteration", "request"})
            and _merge_review_request_current(frame.current)
        )
    return _CONTINUE_REPLAY


def _check_merge_review_verdict_transition(frame: MergeCompleteTupleValidFrame) -> Any:
    assert frame.current_iteration is not None
    frame.prior_review = cast(dict[str, Any], frame.prior.get("review"))
    frame.current_review = cast(dict[str, Any], frame.current.get("review"))
    if (
        frame.current_iteration != frame.prior_iteration
        or not isinstance(frame.prior_review, dict)
        or (not isinstance(frame.current_review, dict))
        or (set(frame.prior_review) != {"iteration", "request"})
        or (frame.current_review.get("request") != frame.prior_review.get("request"))
        or (not _merge_review_request_current(frame.prior))
        or (not _merge_review_verdict_current(frame.current))
    ):
        return False
    verdict = frame.current["review"]["verdict"]["verdict"]
    allowed_review_fields = {"iteration", "request", "verdict"}
    if verdict == "BLOCK" and frame.current_iteration == 8:
        allowed_review_fields.add("residual_risk")
    if set(frame.current_review) != allowed_review_fields:
        return False
    if verdict == "BLOCK":
        return bool(
            frame.after == "revising"
            and (
                frame.current_iteration < 8 or _merge_iteration_cap_residual_current(frame.current)
            )
        )
    if frame.after == "reviewing":
        return False
    return _CONTINUE_REPLAY


def _check_merge_push_landing(frame: MergeTransitionValidFrame) -> Any:
    assert frame.prior is not None
    if frame.event_name == "push_observed":
        if not _merge_push_observation_evidence_valid(
            frame.event, frame.prior, frame.current, frame.context
        ):
            return False
        if _merge_remote_observation_phase(frame.current, frame.context) == "post-push":
            current_push = (
                frame.current_integration.get("push")
                if isinstance(frame.current_integration, dict)
                else None
            )
            observed = (
                frame.current_integration.get("observed")
                if isinstance(frame.current_integration, dict)
                else None
            )
            containment = (
                observed.get("attempted_head_containment")
                if isinstance(observed, dict)
                else None
            )
            latest_landed = (
                next(
                    (
                        item.get("head")
                        for item in reversed(containment)
                        if isinstance(item, dict) and item.get("contained") is True
                    ),
                    None,
                )
                if isinstance(containment, list)
                else None
            )
            if (
                not isinstance(current_push, dict)
                or current_push.get("landed_head") != latest_landed
            ):
                return False
    return _CONTINUE_REPLAY


def _check_merge_review_completion_authority(frame: MergeCompleteTupleValidFrame) -> Any:
    if _merge_pending_disposition_cosign(frame.current):
        return False
    frame.tier = frame.current.get("tier")
    if not isinstance(frame.tier, dict) or not _merge_gate4_summary_current(frame.current):
        return False
    return frame.after == (
        "awaiting_approval" if frame.tier.get("control") is True else "authorized"
    )


def _check_merge_approval_transition(frame: MergeCompleteTupleValidFrame) -> Any:
    assert frame.prior_iteration is not None
    if frame.event_name == "approval_recorded":
        if frame.before == frame.after:
            frame.prior_review = cast(dict[str, Any], frame.prior.get("review"))
            frame.current_review = cast(dict[str, Any], frame.current.get("review"))
            if not isinstance(frame.prior_review, dict) or not isinstance(
                frame.current_review, dict
            ):
                return False
            retained_review = set(frame.prior_review) | set(frame.current_review)
            retained_review.discard("operator_cosign_required")
            return bool(
                frame.prior_iteration < 8
                and _merge_pending_disposition_cosign(frame.prior)
                and (not _merge_pending_disposition_cosign(frame.current))
                and _merge_finding_cosign_current(frame.current)
                and (frame.prior_review.get("operator_cosign_required") is True)
                and (frame.current_review.get("operator_cosign_required") is False)
                and all(
                    frame.prior_review.get(name) == frame.current_review.get(name)
                    for name in retained_review
                )
                and (frame.current.get("authorization") == frame.prior.get("authorization"))
                and (frame.current.get("integration") == frame.prior.get("integration"))
            )
        prior_integration = frame.prior.get("integration")
        current_integration = frame.current.get("integration")
        if (
            isinstance(prior_integration, dict)
            and prior_integration.get("condition") == "remote-churn"
        ):
            retained = set(prior_integration) - {
                "condition",
                "primary_condition",
                "remote_movement_count",
            }
            return bool(
                frame.before == "awaiting_approval"
                and frame.after == "authorized"
                and isinstance(current_integration, dict)
                and all(
                    current_integration.get(name) == prior_integration.get(name)
                    for name in retained
                )
                and (current_integration.get("condition") == "none")
                and (current_integration.get("primary_condition") == "none")
                and (current_integration.get("remote_movement_count") == 0)
                and _merge_remote_churn_approval_current(frame.current)
                and _merge_gate4_summary_current(frame.current)
                and (frame.current.get("review") == frame.prior.get("review"))
                and (frame.current.get("authorization") == frame.prior.get("authorization"))
            )
        frame.tier = frame.current.get("tier")
        return bool(
            frame.before == "awaiting_approval"
            and frame.after == "authorized"
            and isinstance(frame.tier, dict)
            and (frame.tier.get("control") is True)
            and (not _merge_pending_disposition_cosign(frame.current))
            and _merge_mechanical_gates_current(frame.current, frame.context)
            and _merge_gate4_summary_current(frame.current)
            and _merge_gate4_approval_current(frame.current)
            and (frame.current.get("review") == frame.prior.get("review"))
            and (frame.current.get("authorization") == frame.prior.get("authorization"))
            and (frame.current.get("integration") == frame.prior.get("integration"))
        )
    return _CONTINUE_REPLAY


def _check_merge_generation_authority(frame: MergeCompleteTupleValidFrame) -> Any:
    assert frame.prior_iteration is not None
    if frame.event_name == "generation_carried_forward":
        if (
            frame.current.get("review") != frame.prior.get("review")
            or frame.current.get("approval") != frame.prior.get("approval")
            or frame.current.get("authorization") != frame.prior.get("authorization")
        ):
            return False
        if frame.after in {"authorized", "awaiting_approval"}:
            frame.tier = frame.prior.get("tier")
            return bool(
                isinstance(frame.tier, dict)
                and _merge_mechanical_gates_current(frame.current, frame.context)
                and _merge_review_verdict_current(frame.prior, "PASS")
                and _merge_gate4_summary_current(frame.prior)
                and (
                    frame.tier.get("control") is not True
                    or _merge_gate4_approval_current(frame.prior)
                )
            )
        return frame.after == "reverifying"
    if frame.event_name == "generation_refreshed":
        if frame.prior_iteration >= 8 or _merge_pending_disposition_cosign(frame.prior):
            return False
    return _CONTINUE_REPLAY


def _check_merge_integration_authority(frame: MergeCompleteTupleValidFrame) -> Any:
    if frame.event_name in {"epoch_intent", "push_intent"} or (
        frame.event_name == "fetch_intent" and frame.before == "authorized"
    ):
        frame.tier = frame.prior.get("tier")
        if (
            not isinstance(frame.tier, dict)
            or _merge_pending_disposition_cosign(frame.prior)
            or (not _merge_mechanical_gates_current(frame.prior, frame.context))
            or (not _merge_gate4_summary_current(frame.prior))
            or (
                frame.tier.get("control") is True
                and (not _merge_gate4_approval_current(frame.prior))
            )
        ):
            return False
        if frame.current.get("authorization") != frame.prior.get("authorization"):
            return False
    return True


def _check_merge_review_disposition_transition(frame: MergeCompleteTupleValidFrame) -> Any:
    assert frame.prior_iteration is not None
    if frame.event_name == "review_attached":
        result = _check_merge_review_verdict_transition(frame)
        if result is not _CONTINUE_REPLAY:
            return result
        result = _check_merge_review_completion_authority(frame)
        if result is not _CONTINUE_REPLAY:
            return result
    if frame.event_name == "review_disposition":
        return frame.prior_iteration < 8 and _merge_introduced_disposition_valid(
            frame.prior, frame.current
        )
    return _CONTINUE_REPLAY


def _check_merge_transition_envelope(frame: MergeTransitionValidFrame) -> Any:
    frame.event_name = cast(str, frame.event.get("event"))
    payload = frame.event.get("payload")
    frame.event_at = _utc_value(frame.event.get("at"))
    created_at = _utc_value(frame.current.get("created_at"))
    last_event_at = _utc_value(frame.current.get("last_event_at"))
    frame.inactive_after = _utc_value(frame.current.get("inactive_after"))
    chain_id = frame.event.get("chain_id")
    if (
        frame.event_name not in _MERGE_EVENT_NAMES
        or frame.event_name not in _MERGE_EVENT_TOP_LEVEL_CHANGES
        or (not isinstance(chain_id, str))
        or (not _state_shape_valid(frame.current, chain_id, "merge"))
        or (
            frame.prior is not None
            and (not _state_shape_valid(frame.prior, chain_id, "merge"))
        )
        or (not isinstance(payload, dict))
        or (frame.event_at is None)
        or (created_at is None)
        or (last_event_at is None)
        or (frame.inactive_after is None)
        or (frame.event_at != last_event_at)
        or (frame.event_at < created_at)
    ):
        return False
    frame.is_receipt = frame.event_name == "journal_receipted"
    if frame.is_receipt:
        frame.delta = {}
    else:
        try:
            frame.delta = _merge_payload_delta(frame.event, frame.prior)
        except (KeyError, TypeError, ValueError):
            return False
    frame.current_generation = _merge_generation(frame.current.get("candidate"))
    if frame.current_generation is None:
        if (
            frame.current.get("candidate") is not None
            or frame.event.get("generation_digest") is not None
            or frame.event_name not in _MERGE_BOOTSTRAP_EVENTS
        ):
            return False
    elif frame.event.get("generation_digest") != frame.current_generation[1]:
        return False
    frame.current_worktree = _merge_worktree_claim(frame.current)
    return _CONTINUE_REPLAY


def _merge_complete_tuple_valid(
    event_name: str, prior: dict[str, Any], current: dict[str, Any], context: dict[str, Any] | None
) -> bool:
    frame = MergeCompleteTupleValidFrame(
        event_name=event_name, prior=prior, current=current, context=context
    )
    for check in (
        _check_merge_review_iteration_transition,
        _check_merge_review_disposition_transition,
        _check_merge_approval_transition,
        _check_merge_generation_authority,
        _check_merge_integration_authority,
    ):
        result = check(frame)
        if result is not _CONTINUE_REPLAY:
            return result
    raise AssertionError("replay checks did not terminate")


def _check_merge_state_edge_and_gate_fact(frame: MergeTransitionValidFrame) -> Any:
    assert frame.prior is not None
    if (
        not isinstance(frame.before_state, str)
        or not isinstance(frame.after_state, str)
        or (
            frame.prior_inactive
            and frame.event_name
            not in {
                "ownership_release_intent",
                "ownership_released",
                "fetch_result",
                "rebase_conflict",
                "rebase_result",
                "reverification_result",
                "push_observed",
                "cleanup_intent",
                "cleanup_result",
                "condition_recorded",
                "lock_release_result",
                "aborted",
                "closed",
                "journal_receipted",
            }
            and (
                not (
                    frame.event_name == "rebase_intent" and frame.before_state == "rebase_conflict"
                )
            )
        )
        or (
            not _merge_state_edge_valid(
                str(frame.event_name),
                frame.before_state,
                frame.after_state,
                frame.current,
                evidence=(frame.prior_inactive, frame.delta, frame.observation_phase),
            )
        )
        or (
            not _merge_complete_tuple_valid(
                str(frame.event_name), frame.prior, frame.current, frame.context
            )
        )
    ):
        return False
    if frame.event_name == "gate_recorded":
        introduced = _merge_introduced_gate_fact(frame.prior, frame.current)
        if introduced is None:
            return False
        step_id, fact = introduced
        criterion = fact.get("criterion")
        valid_step = bool(
            step_id == "gate-1"
            or step_id == "assertion-sensor"
            or re.fullmatch("stack:[a-z0-9][a-z0-9_-]*", step_id)
            or re.fullmatch("invariant:[1-9][0-9]*", step_id)
        )
        expected_prefix = "gate-1: " if step_id == "gate-1" else "gate-2: "
        if (
            not valid_step
            or not isinstance(criterion, str)
            or (not criterion.startswith(expected_prefix))
            or (fact.get("result") not in {"passed", "failed"})
            or (fact.get("generation_digest") != frame.event.get("generation_digest"))
            or (frame.after_state == "reviewing" and fact.get("result") != "passed")
            or (
                frame.after_state == "reverification_failed"
                and fact.get("result") != "failed"
            )
        ):
            return False
    if frame.event_name == "review_attached" and frame.after_state != "reviewing":
        if _review_binding_for_state(frame.current) is None:
            return False
    frame.prior_status = cast(str, frame.prior_claim.get("status"))
    frame.current_status = cast(str, frame.current_claim.get("status"))
    return _CONTINUE_REPLAY


def _check_merge_candidate_transition(frame: MergeTransitionValidFrame) -> Any:
    assert frame.prior is not None
    frame.prior_generation = _merge_generation(frame.prior.get("candidate"))
    if frame.prior.get("candidate") is None:
        if frame.current_generation is not None and (
            frame.event_name != "fetch_result"
            or frame.current_generation[0].get("generation") != 1
            or any(
                
                    frame.current.get(name) != {}
                    for name in ("steps", "review", "approval", "authorization")
                
            )
        ):
            return False
        if frame.event_name == "fetch_result" and (
            frame.current_generation is None
            and frame.current.get("state") != "classifying"
            or (frame.current_generation is not None and frame.current.get("state") != "verifying")
        ):
            return False
    else:
        result = _check_merge_generation_identity_change(frame)
        if result is not _CONTINUE_REPLAY:
            return result
    return _merge_event_evidence_valid(
        frame.event, frame.prior, frame.current, context=frame.context
    )


def _validate_merge_transition(
    event: dict[str, Any],
    prior: dict[str, Any] | None,
    current: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> bool:
    frame = MergeTransitionValidFrame(event=event, prior=prior, current=current, context=context)
    for check in (
        _check_merge_transition_envelope,
        _check_merge_initial_state_and_clock,
        _check_merge_immutable_identity,
        _check_merge_transition_delta,
        _check_merge_state_edge_and_gate_fact,
        _check_merge_ownership_intent_and_epoch_inputs,
        _check_merge_epoch_lifecycle,
        _check_merge_push_intent_history,
        _check_merge_push_landing,
        _check_merge_candidate_transition,
    ):
        result = check(frame)
        if result is not _CONTINUE_REPLAY:
            return result
    raise AssertionError("replay checks did not terminate")
