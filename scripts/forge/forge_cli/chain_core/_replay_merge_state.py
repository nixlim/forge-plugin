"""Authenticate replay merge state; no journal or run authority."""

from __future__ import annotations

import re
from typing import Any, cast

from ._replay_frames import (
    MergeConditionTransitionValidFrame,
    MergeNestedStateValidFrame,
    MergeStateEdgeValidFrame,
)
from ._replay_merge_candidates import (
    _merge_current_head_contained,
    _merge_generation,
    _merge_older_head_only_contained,
    _merge_worktree_claim,
)
from ._replay_merge_observations import _merge_observation_shape_valid
from ._replay_values import _merge_hex, _utc_value
from ._replay_vocabulary import (
    _CONTINUE_REPLAY,
    _MERGE_MUTABLE_PREPUSH_STATES,
    _MERGE_NONTERMINAL_STATES,
    _MERGE_STATES,
)
from ._state import COMMIT_RE


def _merge_condition_state_coherent(state: dict[str, Any]) -> bool:
    """Apply DM-014's closed retained-state table to every projection."""
    integration = state.get("integration")
    cleanup = state.get("cleanup")
    scalar = state.get("state")
    if not isinstance(integration, dict) or not isinstance(cleanup, dict):
        return False
    if cleanup.get("condition") == "cleanup-failed":
        return scalar == "cleanup_pending"
    condition = integration.get("condition")
    if condition == "lock-release-failed":
        condition = integration.get("primary_condition")
    retained: dict[str, frozenset[str] | None] = {
        "none": None,
        "fetch-failed": frozenset({"classifying", "authorized"}),
        "rebase-failed": frozenset({"revising"}),
        "remote-moved": frozenset({"authorized"}),
        "remote-churn": frozenset({"awaiting_approval"}),
        "push-failed": frozenset({"pushing"}),
        "non-fast-forward": frozenset({"authorized"}),
        "push-outcome-unknown": frozenset({"pushing"}),
        "foreign-git-state": None,
    }
    allowed = retained.get(str(condition))
    return condition in retained and (allowed is None or scalar in allowed)


def _check_merge_cleanup_condition_edge(frame: MergeConditionTransitionValidFrame) -> Any:
    integration = frame.current.get("integration")
    cleanup = frame.current.get("cleanup")
    cleanup_condition = (
        cleanup.get("condition") if isinstance(cleanup, dict) else None
    )
    if cleanup_condition == "cleanup-failed":
        return frame.before in {"pushed", "cleanup_pending"} and frame.after == "cleanup_pending"
    frame.condition = (
        integration.get("condition") if isinstance(integration, dict) else None
    )
    if frame.condition == "none":
        return frame.after == frame.before
    if frame.condition == "fetch-failed":
        return frame.before in {"classifying", "rebasing", "reverifying"} and frame.after in {
            "classifying",
            "authorized",
        }
    if frame.condition == "rebase-failed":
        return frame.before in {"rebasing", "rebase_conflict"} and frame.after == "revising"
    return _CONTINUE_REPLAY


def _check_merge_integration_condition_edge(frame: MergeConditionTransitionValidFrame) -> Any:
    if frame.condition == "remote-moved":
        return (
            frame.before in {"authorized", "rebasing", "reverifying", "pushing"}
            and frame.after == "authorized"
        )
    if frame.condition == "remote-churn":
        return (
            frame.before
            in {"authorized", "awaiting_approval", "rebasing", "reverifying", "pushing"}
            and frame.after == "awaiting_approval"
        )
    if frame.condition in {"push-failed", "push-outcome-unknown"}:
        return frame.before == frame.after == "pushing"
    if frame.condition == "non-fast-forward":
        return frame.before == "pushing" and frame.after == "authorized"
    return _CONTINUE_REPLAY


def _check_merge_lock_condition_edge(frame: MergeConditionTransitionValidFrame) -> Any:
    if frame.condition in {"lock-release-failed", "foreign-git-state"}:
        return frame.after == frame.before
    return False


def _check_merge_push_observation_edge(frame: MergeStateEdgeValidFrame) -> Any:
    if "integration" not in frame.delta:
        return False
    if frame.observation_phase == "final-prepush":
        return frame.before in {"rebasing", "reverifying"} and frame.after in {
            frame.before,
            "authorized",
            "awaiting_approval",
        }
    if _merge_current_head_contained(frame.current):
        return frame.before in _MERGE_NONTERMINAL_STATES and frame.after == "pushed"
    if frame.prior_inactive:
        return frame.before in _MERGE_NONTERMINAL_STATES and frame.after == frame.before
    return _CONTINUE_REPLAY


def _check_merge_push_failure_edge(frame: MergeStateEdgeValidFrame) -> Any:
    if _merge_older_head_only_contained(frame.current):
        return frame.before in _MERGE_NONTERMINAL_STATES and frame.after == "authorized"
    if frame.before in {"rebasing", "reverifying"}:
        return frame.after in {frame.before, "authorized", "awaiting_approval"}
    if frame.before == "pushing":
        return frame.after in {"pushing", "authorized", "awaiting_approval"}
    return False


def _check_merge_bootstrap_state_edge(frame: MergeStateEdgeValidFrame) -> Any:
    frame.prior_inactive, frame.delta, frame.observation_phase = frame.evidence
    if frame.before not in _MERGE_STATES or frame.after not in _MERGE_STATES:
        return False
    if frame.event_name in {"ownership_intent", "ownership_claimed"}:
        return frame.before == frame.after == "classifying"
    if frame.event_name in {"ownership_release_intent", "ownership_released"}:
        return frame.before in _MERGE_NONTERMINAL_STATES and frame.after == frame.before
    if frame.event_name == "gate_recorded":
        return (
            frame.before == "verifying"
            and frame.after in {"verifying", "reviewing"}
            or (
                frame.before == "reverifying"
                and frame.after in {"reverifying", "reverification_failed"}
            )
        )
    return _CONTINUE_REPLAY


def _check_merge_review_state_edge(frame: MergeStateEdgeValidFrame) -> Any:
    if frame.event_name == "review_requested":
        return frame.before == frame.after == "reviewing"
    if frame.event_name == "review_attached":
        return frame.before == "reviewing" and frame.after in {
            "reviewing",
            "revising",
            "awaiting_approval",
            "authorized",
        }
    if frame.event_name == "review_disposition":
        return frame.before == frame.after and frame.before in {"reviewing", "revising"}
    if frame.event_name == "approval_recorded":
        return (
            frame.before == frame.after
            and frame.before in {"reviewing", "revising"}
            or (frame.before == "awaiting_approval" and frame.after == "authorized")
        )
    return _CONTINUE_REPLAY


def _check_merge_generation_state_edge(frame: MergeStateEdgeValidFrame) -> Any:
    if frame.event_name == "generation_refreshed":
        return frame.before in _MERGE_MUTABLE_PREPUSH_STATES and frame.after == "verifying"
    if frame.event_name == "generation_carried_forward":
        return frame.before in {"rebasing", "reverifying"} and frame.after in {
            "reverifying",
            "authorized",
            "awaiting_approval",
        }
    if frame.event_name == "epoch_intent":
        return frame.before == "authorized" and frame.after == "rebasing"
    if frame.event_name == "fetch_intent":
        return (
            frame.before in _MERGE_MUTABLE_PREPUSH_STATES
            and frame.after == "classifying"
            or frame.before == frame.after == "rebasing"
        )
    return _CONTINUE_REPLAY


def _check_merge_fetch_rebase_state_edge(frame: MergeStateEdgeValidFrame) -> Any:
    if frame.event_name == "fetch_result":
        return (
            frame.before == "classifying"
            and frame.after in {"classifying", "verifying"}
            or (
                frame.before in {"rebasing", "reverifying"}
                and frame.after in {"rebasing", "authorized"}
            )
        )
    if frame.event_name == "rebase_intent":
        return frame.before == frame.after and frame.before in {"rebasing", "rebase_conflict"}
    if frame.event_name == "rebase_conflict":
        return frame.before in {"rebasing", "rebase_conflict"} and frame.after == "rebase_conflict"
    if frame.event_name == "rebase_result":
        return (
            frame.before == "rebasing"
            and frame.after
            in {"rebasing", "rebase_conflict", "reverifying", "revising", "authorized"}
            or (
                frame.before == "rebase_conflict"
                and frame.after in {"rebase_conflict", "reverifying", "revising"}
            )
        )
    return _CONTINUE_REPLAY


def _check_merge_terminal_state_edge(frame: MergeStateEdgeValidFrame) -> Any:
    if frame.event_name == "aborted":
        return frame.before in _MERGE_NONTERMINAL_STATES and frame.after == "aborted"
    if frame.event_name == "closed":
        return frame.before in {"pushed", "cleanup_pending"} and frame.after == "closed"
    return False


def _check_merge_candidate_epoch_shape(frame: MergeNestedStateValidFrame) -> Any:
    assert frame.worktree is not None
    if frame.state.get("candidate") is None:
        if (
            frame.state.get("tier") is not None
            or frame.state.get("steps") != {}
            or frame.state.get("review") != {}
            or (frame.state.get("approval") != {})
            or (frame.state.get("authorization") != {})
        ):
            return False
    else:
        tier = frame.state.get("tier")
        if (
            frame.generation is None
            or not isinstance(tier, dict)
            or set(tier) != {"control", "categories"}
            or (type(tier.get("control")) is not bool)
            or (not isinstance(tier.get("categories"), list))
            or (not all(isinstance(value, str) and value for value in tier["categories"]))
        ):
            return False
        candidate = frame.generation[0]
        worktree_identity = frame.worktree[0]
        if (
            candidate.get("remote") != frame.target.get("remote")
            or candidate.get("destination_ref") != frame.target.get("destination_ref")
            or candidate.get("policy_commit") != frame.policy.get("commit")
            or (candidate.get("policy_digest") != frame.policy.get("digest"))
            or (
                candidate.get("worktree_identity")
                != {
                    name: worktree_identity[name]
                    for name in ("path", "git_dir", "common_dir")
                }
            )
        ):
            return False
    epoch = frame.integration.get("epoch")
    if epoch is not None:
        if (
            not isinstance(epoch, dict)
            or set(epoch)
            != {"operation_nonce", "generation_digest", "intent_digest", "started_at"}
            or (not isinstance(epoch.get("operation_nonce"), str))
            or (re.fullmatch("[0-9a-f]{32}", str(epoch["operation_nonce"])) is None)
            or (not _merge_hex(epoch.get("generation_digest")))
            or (not _merge_hex(epoch.get("intent_digest")))
            or (_utc_value(epoch.get("started_at")) is None)
            or (frame.generation is None)
            or (epoch.get("generation_digest") != frame.generation[1])
        ):
            return False
    frame.push = frame.integration.get("push")
    frame.observed = frame.integration.get("observed")
    return _CONTINUE_REPLAY


def _merge_condition_transition_valid(before: str, after: str, current: dict[str, Any]) -> bool:
    frame = MergeConditionTransitionValidFrame(before=before, after=after, current=current)
    for check in (
        _check_merge_cleanup_condition_edge,
        _check_merge_integration_condition_edge,
        _check_merge_lock_condition_edge,
    ):
        result = check(frame)
        if result is not _CONTINUE_REPLAY:
            return result
    raise AssertionError("replay checks did not terminate")


def _check_merge_verification_push_state_edge(frame: MergeStateEdgeValidFrame) -> Any:
    if frame.event_name == "reverification_result":
        return frame.before == "reverifying" and frame.after in {
            "reverifying",
            "reverification_failed",
            "reviewing",
            "revising",
        }
    if frame.event_name == "push_intent":
        return frame.before in {"rebasing", "reverifying"} and frame.after == "pushing"
    if frame.event_name == "push_observed":
        result = _check_merge_push_observation_edge(frame)
        if result is not _CONTINUE_REPLAY:
            return result
        result = _check_merge_push_failure_edge(frame)
        if result is not _CONTINUE_REPLAY:
            return result
    return _CONTINUE_REPLAY


def _check_merge_nested_state_identity(frame: MergeNestedStateValidFrame) -> Any:
    frame.worktree = _merge_worktree_claim(frame.state)
    branch = frame.state.get("branch")
    frame.target = cast(dict[str, Any], frame.state.get("target"))
    frame.policy = cast(dict[str, Any], frame.state.get("policy_source"))
    frame.integration = cast(dict[str, Any], frame.state.get("integration"))
    cleanup = frame.state.get("cleanup")
    if (
        frame.state.get("state") not in _MERGE_STATES
        or frame.worktree is None
        or (not isinstance(frame.state.get("owner"), dict))
        or (not isinstance(branch, str))
        or (not branch.startswith("refs/heads/"))
        or (not isinstance(frame.target, dict))
        or (set(frame.target) != {"remote", "destination_ref", "manifest_commit"})
        or (frame.target.get("remote") != "origin")
        or (not isinstance(frame.target.get("destination_ref"), str))
        or (not str(frame.target["destination_ref"]).startswith("refs/heads/"))
        or (not isinstance(frame.target.get("manifest_commit"), str))
        or (COMMIT_RE.fullmatch(str(frame.target["manifest_commit"])) is None)
        or (not isinstance(frame.policy, dict))
        or (set(frame.policy) != {"commit", "digest"})
        or (not isinstance(frame.policy.get("commit"), str))
        or (COMMIT_RE.fullmatch(str(frame.policy["commit"])) is None)
        or (not _merge_hex(frame.policy.get("digest")))
        or (not isinstance(frame.integration, dict))
        or (
            set(frame.integration)
            != {
                "condition",
                "primary_condition",
                "epoch",
                "remote_movement_count",
                "intent",
                "observed",
                "pre_rebase",
                "conflict",
                "push",
            }
        )
        or (
            frame.integration.get("condition")
            not in {
                "none",
                "fetch-failed",
                "rebase-failed",
                "remote-moved",
                "remote-churn",
                "push-failed",
                "non-fast-forward",
                "push-outcome-unknown",
                "lock-release-failed",
                "foreign-git-state",
            }
        )
        or (type(frame.integration.get("remote_movement_count")) is not int)
        or (int(frame.integration["remote_movement_count"]) < 0)
        or (not isinstance(cleanup, dict))
        or (cleanup.get("condition") not in {"none", "cleanup-failed"})
    ):
        return False
    primary = frame.integration.get("primary_condition")
    if (
        frame.integration.get("condition") == "lock-release-failed"
        and primary
        not in {
            "none",
            "fetch-failed",
            "rebase-failed",
            "remote-moved",
            "remote-churn",
            "push-failed",
            "non-fast-forward",
            "push-outcome-unknown",
            "foreign-git-state",
        }
        or (frame.integration.get("condition") != "lock-release-failed" and primary != "none")
    ):
        return False
    if not _merge_condition_state_coherent(frame.state):
        return False
    frame.generation = _merge_generation(frame.state.get("candidate"))
    return _CONTINUE_REPLAY


def _check_merge_cleanup_state_edge(frame: MergeStateEdgeValidFrame) -> Any:
    if frame.event_name == "cleanup_intent":
        return frame.before == frame.after and frame.before in {"pushed", "cleanup_pending"}
    if frame.event_name == "cleanup_result":
        return (
            frame.before == "pushed"
            and frame.after in {"pushed", "cleanup_pending"}
            or frame.before == frame.after == "cleanup_pending"
        )
    if frame.event_name == "condition_recorded":
        return _merge_condition_transition_valid(frame.before, frame.after, frame.current)
    if frame.event_name in {"lock_release_result", "journal_receipted"}:
        return frame.after == frame.before
    return _CONTINUE_REPLAY


def _check_merge_push_observation_shape(frame: MergeNestedStateValidFrame) -> Any:
    if frame.push is None:
        if frame.observed is not None and (not _merge_observation_shape_valid(frame.observed, ())):
            return False
    else:
        push_result = frame.push.get("result")
        if (
            not isinstance(frame.push, dict)
            or set(frame.push)
            != {
                "expected_old_tip",
                "intended_head",
                "destination_ref",
                "intended_at",
                "result",
                "attempted_heads",
                "landed_head",
            }
            or any(
                not isinstance(frame.push.get(name), str)
                or COMMIT_RE.fullmatch(str(frame.push[name])) is None
                for name in ("expected_old_tip", "intended_head")
            )
            or (frame.push.get("destination_ref") != frame.target.get("destination_ref"))
            or (_utc_value(frame.push.get("intended_at")) is None)
            or (not isinstance(frame.push.get("attempted_heads"), list))
            or (not frame.push["attempted_heads"])
            or (
                not all(
                    isinstance(head, str) and COMMIT_RE.fullmatch(head) is not None
                    for head in frame.push["attempted_heads"]
                )
            )
            or (frame.push["attempted_heads"][-1] != frame.push.get("intended_head"))
            or (
                frame.push.get("landed_head") is not None
                and frame.push.get("landed_head") not in frame.push["attempted_heads"]
            )
            or (
                push_result is not None
                and (
                    not isinstance(push_result, dict)
                    or set(push_result)
                    != {
                        "classification",
                        "exit",
                        "inflight_digest",
                        "output_digest",
                        "launch_failed",
                        "timed_out",
                        "output_limit_exceeded",
                        "recorded_at",
                    }
                    or push_result.get("classification")
                    not in {"success", "non-fast-forward", "known-failure", "outcome-unknown"}
                    or (
                        push_result.get("exit") is not None
                        and type(push_result.get("exit")) is not int
                    )
                    or (not _merge_hex(push_result.get("inflight_digest")))
                    or (not _merge_hex(push_result.get("output_digest")))
                    or any(
                        type(push_result.get(name)) is not bool
                        for name in ("launch_failed", "timed_out", "output_limit_exceeded")
                    )
                    or (_utc_value(push_result.get("recorded_at")) is None)
                )
            )
        ):
            return False
        if frame.observed is not None and (
            not _merge_observation_shape_valid(frame.observed, frame.push["attempted_heads"])
        ):
            return False
    return True


def _merge_state_edge_valid(
    event_name: str, before: str, after: str, current: dict[str, Any], *, evidence: Any
) -> bool:
    frame = MergeStateEdgeValidFrame(
        event_name=event_name, before=before, after=after, current=current, evidence=evidence
    )
    for check in (
        _check_merge_bootstrap_state_edge,
        _check_merge_review_state_edge,
        _check_merge_generation_state_edge,
        _check_merge_fetch_rebase_state_edge,
        _check_merge_verification_push_state_edge,
        _check_merge_cleanup_state_edge,
        _check_merge_terminal_state_edge,
    ):
        result = check(frame)
        if result is not _CONTINUE_REPLAY:
            return result
    raise AssertionError("replay checks did not terminate")


def _merge_nested_state_valid(state: dict[str, Any]) -> bool:
    frame = MergeNestedStateValidFrame(state=state)
    for check in (
        _check_merge_nested_state_identity,
        _check_merge_candidate_epoch_shape,
        _check_merge_push_observation_shape,
    ):
        result = check(frame)
        if result is not _CONTINUE_REPLAY:
            return result
    raise AssertionError("replay checks did not terminate")
