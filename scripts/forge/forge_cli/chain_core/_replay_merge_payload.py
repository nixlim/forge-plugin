"""Authenticate replay merge payload; no journal or run authority."""

from __future__ import annotations

import copy
from typing import Any, cast

from ._replay_frames import MergePayloadDeltaFrame
from ._replay_values import _merge_hex
from ._replay_vocabulary import (
    _CONTINUE_REPLAY,
    _MERGE_BOOTSTRAP_FETCH_EVIDENCE_FIELDS,
    _MERGE_DERIVED_STATE_FIELDS,
    _MERGE_EVENT_EVIDENCE_FIELDS,
    _MERGE_EVENT_NAMES,
    _MERGE_HISTORICAL_ABORT_EVIDENCE_FIELDS,
    _MERGE_QUARANTINE_EVIDENCE_FIELDS,
)
from ._state import CHAIN_ID_RE


def _merge_predecessor_pair_valid(payload: dict[str, Any]) -> bool:
    predecessor_chain = payload.get("predecessor_chain_id")
    predecessor_release = payload.get("predecessor_release_digest")
    if predecessor_chain is None or predecessor_release is None:
        return predecessor_chain is None and predecessor_release is None
    return bool(
        isinstance(predecessor_chain, str)
        and CHAIN_ID_RE.fullmatch(predecessor_chain) is not None
        and _merge_hex(predecessor_release)
    )


def _check_merge_ownership_claim_delta(frame: MergePayloadDeltaFrame) -> Any:
    assert frame.direct_fields is not None
    if set(frame.payload) != set(frame.direct_fields) or frame.prior is None:
        raise ValueError("merge direct event payload is malformed")
    if frame.event_name in {"ownership_intent", "ownership_claimed"}:
        frame.worktree = copy.deepcopy(frame.prior.get("worktree"))
        frame.claim = frame.worktree.get("claim") if isinstance(frame.worktree, dict) else None
        if not isinstance(frame.claim, dict):
            raise ValueError("merge ownership projection is malformed")
        if frame.event_name == "ownership_intent":
            frame.claim.update(
                {
                    "status": "unpublished",
                    "path": frame.payload["claim_path"],
                    "inode": None,
                    "digest": frame.payload["intended_claim_digest"],
                }
            )
        else:
            frame.claim.update(
                {
                    "status": "owned",
                    "inode": frame.payload["claim_inode"],
                    "digest": frame.payload["claim_digest"],
                }
            )
        return {"worktree": frame.worktree}
    return _CONTINUE_REPLAY


def _check_merge_release_or_fetch_delta(frame: MergePayloadDeltaFrame) -> Any:
    assert frame.prior is not None
    if frame.event_name in {"ownership_release_intent", "ownership_released"}:
        frame.worktree = copy.deepcopy(frame.prior.get("worktree"))
        frame.claim = frame.worktree.get("claim") if isinstance(frame.worktree, dict) else None
        if not isinstance(frame.claim, dict):
            raise ValueError("merge release projection is malformed")
        if frame.event_name == "ownership_release_intent":
            frame.claim["status"] = "releasing"
        else:
            frame.claim.update(
                {
                    "status": "released",
                    "inode": frame.payload["claim_inode"],
                    "digest": frame.payload["claim_digest"],
                }
            )
        return {"worktree": frame.worktree}
    if frame.event_name == "fetch_intent":
        frame.integration = copy.deepcopy(frame.prior.get("integration"))
        if not isinstance(frame.integration, dict):
            raise ValueError("merge fetch projection is malformed")
        frame.integration["intent"] = {"operation": "fetch", **copy.deepcopy(frame.payload)}
        return {"integration": frame.integration}
    return _CONTINUE_REPLAY


def _check_merge_condition_or_abort_delta(frame: MergePayloadDeltaFrame) -> Any:
    assert frame.prior is not None
    if frame.event_name == "condition_recorded":
        frame.integration = copy.deepcopy(frame.prior.get("integration"))
        if not isinstance(frame.integration, dict):
            raise ValueError("merge condition projection is malformed")
        frame.integration["condition"] = frame.payload["condition"]
        return {"integration": frame.integration}
    if frame.event_name == "aborted":
        return {"state": "aborted"}
    raise ValueError("unsupported merge direct event payload")


def _check_merge_payload_envelope(frame: MergePayloadDeltaFrame) -> Any:
    frame.event_name = cast(str, frame.event.get("event"))
    frame.payload = cast(dict[str, Any], frame.event.get("payload"))
    if (
        frame.event_name not in _MERGE_EVENT_NAMES
        or frame.event_name == "journal_receipted"
        or (not isinstance(frame.payload, dict))
    ):
        raise ValueError("merge transition payload is malformed")
    frame.direct_fields = _MERGE_EVENT_EVIDENCE_FIELDS.get(str(frame.event_name))
    if frame.event_name == "fetch_intent" and frame.event.get("generation_digest") is None:
        frame.direct_fields = _MERGE_BOOTSTRAP_FETCH_EVIDENCE_FIELDS
    elif frame.event_name == "condition_recorded" and "quarantine" in frame.payload:
        frame.direct_fields = _MERGE_QUARANTINE_EVIDENCE_FIELDS
    elif frame.event_name == "aborted" and "terminal_disposition" in frame.payload:
        frame.direct_fields = _MERGE_HISTORICAL_ABORT_EVIDENCE_FIELDS
    return _CONTINUE_REPLAY


def _check_merge_epoch_intent_delta(frame: MergePayloadDeltaFrame) -> Any:
    if frame.event_name == "epoch_intent":
        frame.integration = frame.projected.get("integration")
        epoch = (
            frame.integration.get("epoch") if isinstance(frame.integration, dict) else None
        )
        if (
            not isinstance(epoch, dict)
            or set(epoch)
            != {"operation_nonce", "generation_digest", "intent_digest", "started_at"}
            or epoch.get("intent_digest") is not None
            or (not _merge_hex(frame.event.get("digest")))
        ):
            raise ValueError("merge epoch intent projection is malformed")
        epoch["intent_digest"] = frame.event["digest"]
    return frame.projected


def _check_merge_explicit_payload_delta(frame: MergePayloadDeltaFrame) -> Any:
    if frame.direct_fields is not None:
        result = _check_merge_ownership_claim_delta(frame)
        if result is not _CONTINUE_REPLAY:
            return result
        result = _check_merge_release_or_fetch_delta(frame)
        if result is not _CONTINUE_REPLAY:
            return result
        result = _check_merge_condition_or_abort_delta(frame)
        if result is not _CONTINUE_REPLAY:
            return result
    ordinary = {
        name: value
        for name, value in frame.payload.items()
        if name not in {"source_event_digest", "journal_batch"}
    }
    delta = ordinary.get("delta")
    if (
        set(ordinary) != {"delta"}
        or not isinstance(delta, dict)
        or (not delta)
        or any(name in _MERGE_DERIVED_STATE_FIELDS for name in delta)
    ):
        raise ValueError("merge transition payload is malformed")
    frame.projected = copy.deepcopy(delta)
    return _CONTINUE_REPLAY


def _merge_payload_delta(
    event: dict[str, Any], prior: dict[str, Any] | None = None
) -> dict[str, Any]:
    frame = MergePayloadDeltaFrame(event=event, prior=prior)
    for check in (
        _check_merge_payload_envelope,
        _check_merge_explicit_payload_delta,
        _check_merge_epoch_intent_delta,
    ):
        result = check(frame)
        if result is not _CONTINUE_REPLAY:
            return result
    raise AssertionError("replay checks did not terminate")
