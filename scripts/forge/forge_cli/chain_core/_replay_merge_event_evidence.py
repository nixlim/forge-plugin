"""Authenticate replay merge event evidence; no journal or run authority."""

from __future__ import annotations

import copy
from typing import Any

from ._core import canonical_bytes
from ._replay_frames import MergeEventEvidenceValidFrame
from ._replay_merge_bootstrap_evidence import _check_merge_ownership_claim_evidence
from ._replay_merge_candidates import _merge_claim_record_digest
from ._replay_merge_lifecycle_evidence import (
    _check_merge_epoch_context,
    _check_merge_epoch_intent_binding,
    _check_merge_event_worktree_inputs,
    _check_merge_intent_result_context,
)
from ._replay_merge_payload import _merge_predecessor_pair_valid
from ._replay_vocabulary import _CONTINUE_REPLAY, _MERGE_EVENT_EVIDENCE_FIELDS
from forge_cli.policy import sha256_bytes


def _check_merge_publish_replay_context(frame: MergeEventEvidenceValidFrame) -> Any:
    if frame.context is not None and frame.next_context is not None:
        frame.context.clear()
        frame.context.update(frame.next_context)
    return True


def _check_merge_ownership_intent_evidence(frame: MergeEventEvidenceValidFrame) -> Any:
    if frame.event_name == "ownership_intent":
        identity = {
            name: frame.current_identity[name] for name in ("path", "git_dir", "common_dir")
        }
        intended_claim_digest = _merge_claim_record_digest(
            frame.current, frame.current_identity
        )
        if (
            isinstance(frame.context, dict)
            and "ownership_intent" in frame.context
            or frame.payload.get("worktree_digest") != sha256_bytes(canonical_bytes(identity))
            or frame.payload.get("claim_path") != frame.current_claim.get("path")
            or (frame.payload.get("intended_claim_digest") != intended_claim_digest)
            or (frame.current_claim.get("digest") != intended_claim_digest)
            or (not _merge_predecessor_pair_valid(frame.payload))
        ):
            return False
        if frame.next_context is not None:
            frame.next_context["ownership_intent"] = {
                "digest": frame.event.get("digest"),
                "payload": {
                    name: copy.deepcopy(frame.payload[name])
                    for name in _MERGE_EVENT_EVIDENCE_FIELDS[frame.event_name]
                },
            }
    else:
        result = _check_merge_ownership_claim_evidence(frame)
        if result is not _CONTINUE_REPLAY:
            return result
    if frame.next_context is not None:
        result = _check_merge_epoch_context(frame)
        if result is not _CONTINUE_REPLAY:
            return result
        result = _check_merge_intent_result_context(frame)
        if result is not _CONTINUE_REPLAY:
            return result
    return _CONTINUE_REPLAY


def _merge_event_evidence_valid(
    event: dict[str, Any],
    prior: dict[str, Any],
    current: dict[str, Any],
    *,
    context: dict[str, Any] | None,
) -> bool:
    frame = MergeEventEvidenceValidFrame(event=event, prior=prior, current=current, context=context)
    for check in (
        _check_merge_event_worktree_inputs,
        _check_merge_epoch_intent_binding,
        _check_merge_ownership_intent_evidence,
        _check_merge_publish_replay_context,
    ):
        result = check(frame)
        if result is not _CONTINUE_REPLAY:
            return result
    raise AssertionError("replay checks did not terminate")
