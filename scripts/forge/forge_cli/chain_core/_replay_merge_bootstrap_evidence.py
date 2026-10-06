"""Authenticate replay merge bootstrap evidence; no journal or run authority."""

from __future__ import annotations

import copy
import re
from typing import Any

from ._core import canonical_bytes
from ._replay_frames import MergeEventEvidenceValidFrame
from ._replay_merge_candidates import (
    _merge_current_head_contained,
    _merge_older_head_only_contained,
)
from ._replay_merge_lifecycle_evidence import _check_merge_terminal_or_condition_evidence
from ._replay_merge_payload import _merge_predecessor_pair_valid
from ._replay_values import _merge_hex, _utc_value
from ._replay_vocabulary import (
    _CONTINUE_REPLAY,
    _MERGE_BOOTSTRAP_FETCH_EVIDENCE_FIELDS,
    _MERGE_EVENT_EVIDENCE_FIELDS,
)
from ._state import COMMIT_RE
from forge_cli.policy import sha256_bytes


def _check_merge_ownership_release_evidence(frame: MergeEventEvidenceValidFrame) -> Any:
    if frame.event_name == "ownership_released":
        frame.release = frame.context.get("release_intent") if frame.context is not None else None
        frame.release_payload = (
            frame.release.get("payload") if isinstance(frame.release, dict) else None
        )
        frame.release_mode = frame.payload.get("release_mode")
        observation = {
            "claim_path": frame.current_claim.get("path"),
            "exists": frame.release_mode == "acquired",
            "inode": frame.current_claim.get("inode") if frame.release_mode == "acquired" else None,
            "digest": frame.current_claim.get("digest")
            if frame.release_mode == "acquired"
            else None,
        }
        expected_observation_digest = sha256_bytes(canonical_bytes(observation))
        if (
            isinstance(frame.context, dict)
            and "release_result" in frame.context
            or frame.payload.get("release_intent_digest") != frame.event.get("previous_digest")
            or (not _merge_hex(frame.payload.get("release_intent_digest")))
            or (frame.payload.get("release_mode") not in {"acquired", "never-published"})
            or (
                frame.payload.get("terminal_disposition")
                not in {"ordinary", "historical-landed-superseded"}
            )
            or (frame.payload.get("claim_inode") != frame.current_claim.get("inode"))
            or (frame.payload.get("claim_digest") != frame.current_claim.get("digest"))
            or (not _merge_hex(frame.payload.get("claim_digest")))
            or (frame.payload.get("claim_observation_digest") != expected_observation_digest)
            or (
                frame.context is not None
                and (
                    not isinstance(frame.release, dict)
                    or frame.release.get("digest") != frame.payload.get("release_intent_digest")
                    or (not isinstance(frame.release_payload, dict))
                    or (
                        frame.release_payload.get("release_mode")
                        != frame.payload.get("release_mode")
                    )
                    or (
                        frame.release_payload.get("terminal_disposition")
                        != frame.payload.get("terminal_disposition")
                    )
                )
            )
        ):
            return False
        if frame.next_context is not None:
            frame.next_context["release_result"] = {
                "digest": frame.event.get("digest"),
                "payload": {
                    name: copy.deepcopy(frame.payload[name])
                    for name in _MERGE_EVENT_EVIDENCE_FIELDS[frame.event_name]
                },
            }
    else:
        result = _check_merge_terminal_or_condition_evidence(frame)
        if result is not _CONTINUE_REPLAY:
            return result
    return _CONTINUE_REPLAY


def _check_merge_release_intent_evidence(frame: MergeEventEvidenceValidFrame) -> Any:
    if frame.event_name == "ownership_release_intent":
        frame.release_mode = frame.payload.get("release_mode")
        frame.disposition = frame.payload.get("terminal_disposition")
        target = frame.payload.get("target_terminal")
        source_state = frame.payload.get("source_state")
        frame.cleanup = frame.prior.get("cleanup")
        frame.event_at = _utc_value(frame.event.get("at"))
        frame.prior_deadline = _utc_value(frame.prior.get("inactive_after"))
        if (
            isinstance(frame.context, dict)
            and ("release_intent" in frame.context or "release_result" in frame.context)
            or target not in {"aborted", "closed"}
            or frame.disposition not in {"ordinary", "historical-landed-superseded"}
            or (source_state != frame.prior.get("state"))
            or (not _merge_hex(frame.payload.get("terminal_preconditions_digest")))
            or (
                frame.release_mode
                != ("acquired" if frame.prior_claim.get("status") == "owned" else "never-published")
            )
            or (
                target == "closed" and source_state not in {"pushed", "cleanup_pending"}
            )
            or (target == "aborted" and source_state in {"pushed", "cleanup_pending"})
            or (frame.disposition == "historical-landed-superseded" and target != "aborted")
            or (
                target == "closed"
                and (
                    not isinstance(frame.cleanup, dict)
                    or frame.cleanup.get("condition") != "none"
                    or (not _merge_current_head_contained(frame.prior))
                )
            )
            or (
                frame.disposition == "historical-landed-superseded"
                and (
                    frame.event_at is None
                    or frame.prior_deadline is None
                    or frame.event_at < frame.prior_deadline
                    or (not _merge_older_head_only_contained(frame.prior))
                )
            )
        ):
            return False
        if frame.next_context is not None:
            frame.next_context["release_intent"] = {
                "digest": frame.event.get("digest"),
                "payload": {
                    name: copy.deepcopy(frame.payload[name])
                    for name in _MERGE_EVENT_EVIDENCE_FIELDS[frame.event_name]
                },
            }
            frame.next_context.pop("release_result", None)
    else:
        result = _check_merge_ownership_release_evidence(frame)
        if result is not _CONTINUE_REPLAY:
            return result
    return _CONTINUE_REPLAY


def _check_merge_bootstrap_fetch_evidence(frame: MergeEventEvidenceValidFrame) -> Any:
    if frame.event_name == "fetch_intent" and frame.event.get("generation_digest") is None:
        frame.integration = frame.current.get("integration")
        frame.intent = (
            frame.integration.get("intent") if isinstance(frame.integration, dict) else None
        )
        if (
            frame.payload.get("repository") != frame.current.get("repository")
            or frame.payload.get("worktree")
            != {name: frame.current_identity[name] for name in ("path", "git_dir", "common_dir")}
            or frame.payload.get("branch") != frame.current.get("branch")
            or (frame.payload.get("target") != frame.current.get("target"))
            or (not isinstance(frame.payload.get("pre_fetch_head"), str))
            or (COMMIT_RE.fullmatch(str(frame.payload["pre_fetch_head"])) is None)
            or (not _merge_hex(frame.payload.get("policy_digest")))
            or (not isinstance(frame.payload.get("operation_nonce"), str))
            or (re.fullmatch("[0-9a-f]{32}", str(frame.payload["operation_nonce"])) is None)
            or (type(frame.payload.get("attempt")) is not int)
            or (int(frame.payload["attempt"]) <= 0)
            or (not isinstance(frame.intent, dict))
            or any(
                frame.intent.get(name) != frame.payload.get(name)
                for name in _MERGE_BOOTSTRAP_FETCH_EVIDENCE_FIELDS
            )
        ):
            return False
    else:
        result = _check_merge_release_intent_evidence(frame)
        if result is not _CONTINUE_REPLAY:
            return result
    return _CONTINUE_REPLAY


def _check_merge_ownership_claim_evidence(frame: MergeEventEvidenceValidFrame) -> Any:
    if frame.event_name == "ownership_claimed":
        frame.intent = frame.context.get("ownership_intent") if frame.context is not None else None
        intent_payload = (
            frame.intent.get("payload") if isinstance(frame.intent, dict) else None
        )
        if (
            isinstance(frame.context, dict)
            and "ownership_claimed" in frame.context
            or frame.payload.get("ownership_intent_digest") != frame.event.get("previous_digest")
            or (not _merge_hex(frame.payload.get("ownership_intent_digest")))
            or (frame.payload.get("claim_inode") != frame.current_claim.get("inode"))
            or (frame.payload.get("claim_digest") != frame.current_claim.get("digest"))
            or (not _merge_hex(frame.payload.get("claim_digest")))
            or (not _merge_predecessor_pair_valid(frame.payload))
            or (
                frame.context is not None
                and (
                    not isinstance(frame.intent, dict)
                    or frame.intent.get("digest") != frame.payload.get("ownership_intent_digest")
                    or (not isinstance(intent_payload, dict))
                    or (
                        intent_payload.get("intended_claim_digest")
                        != frame.payload.get("claim_digest")
                    )
                    or (intent_payload.get("claim_path") != frame.current_claim.get("path"))
                    or (
                        intent_payload.get("predecessor_chain_id")
                        != frame.payload.get("predecessor_chain_id")
                    )
                    or (
                        intent_payload.get("predecessor_release_digest")
                        != frame.payload.get("predecessor_release_digest")
                    )
                )
            )
        ):
            return False
        if frame.next_context is not None:
            frame.next_context["ownership_claimed"] = {"digest": frame.event.get("digest")}
    else:
        result = _check_merge_bootstrap_fetch_evidence(frame)
        if result is not _CONTINUE_REPLAY:
            return result
    return _CONTINUE_REPLAY
