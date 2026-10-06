"""Authenticate replay state shape; no journal or run authority."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ._replay_frames import StateShapeValidFrame
from ._replay_merge_state import _merge_nested_state_valid
from ._replay_values import _utc_value
from ._replay_vocabulary import (
    _CONTINUE_REPLAY,
    _MERGE_STATE_KEYS,
)


def _check_merge_state_envelope(frame: StateShapeValidFrame) -> Any:
    expected_keys = _MERGE_STATE_KEYS
    expected_schema = "forge-merge-chain/1"
    if (
        not isinstance(frame.state, dict)
        or set(frame.state) - {"run_binding", "journal_outbox"} != expected_keys
        or frame.state.get("schema") != expected_schema
        or (frame.state.get("chain_id") != frame.chain_id)
        or (frame.state.get("kind") != frame.family)
        or any(
            _utc_value(frame.state.get(name)) is None
            for name in ("created_at", "last_event_at", "inactive_after")
        )
    ):
        return False
    return _CONTINUE_REPLAY


def _check_merge_state_nested_shape(frame: StateShapeValidFrame) -> Any:
    assert isinstance(frame.state, dict)
    if (
        not isinstance(frame.state.get("repository"), str)
        or not Path(str(frame.state["repository"])).is_absolute()
        or (not isinstance(frame.state.get("worktree"), dict))
        or (not isinstance(frame.state.get("policy_source"), dict))
        or (not isinstance(frame.state.get("steps"), dict))
        or (not isinstance(frame.state.get("review"), dict))
        or (not isinstance(frame.state.get("approval"), dict))
        or (not isinstance(frame.state.get("authorization"), dict))
        or (not isinstance(frame.state.get("integration"), dict))
        or (not isinstance(frame.state.get("cleanup"), dict))
        or (not _merge_nested_state_valid(frame.state))
    ):
        return False
    return _CONTINUE_REPLAY


def _state_shape_valid(state: Any, chain_id: str, family: str) -> bool:
    frame = StateShapeValidFrame(state=state, chain_id=chain_id, family=family)
    for check in (
        _check_merge_state_envelope,
        _check_merge_state_nested_shape,
    ):
        result = check(frame)
        if result is not _CONTINUE_REPLAY:
            return result
    return True
