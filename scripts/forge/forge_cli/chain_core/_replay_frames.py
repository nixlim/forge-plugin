"""Typed transient inputs and shared results for ordered replay checks.

Raw JSON slots are checked by their producing step before subsequent steps use
these types. Scratch fields are assigned in that order; function-local values
stay local rather than adding unvalidated state to a frame.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(kw_only=True)
class MergeGenerationFrame:
    candidate: object
    digest: str = field(init=False)
    preimage: dict[str, Any] = field(init=False)

@dataclass(kw_only=True)
class MergeReviewIterationFrame:
    iteration: int = field(init=False)
    state: dict[str, Any]

@dataclass(kw_only=True)
class MergeWorktreeClaimFrame:
    claim: dict[str, Any] = field(init=False)
    digest: object = field(init=False)
    expected_claim_path: Path = field(init=False)
    inode: object = field(init=False)
    state: dict[str, Any]
    worktree: dict[str, Any] = field(init=False)

@dataclass(kw_only=True)
class MergeCurrentGateFactsFrame:
    facts: tuple[dict[str, Any], ...] = field(init=False)
    generation_digest: str
    step_id: str
    value: object

@dataclass(kw_only=True)
class MergeIntroducedGateFactFrame:
    current: dict[str, Any]
    fact: object = field(init=False)
    prior: dict[str, Any]
    step_id: str = field(init=False)

@dataclass(kw_only=True)
class MergePendingDispositionCosignFrame:
    dispositions: list[Any] = field(init=False)
    state: dict[str, Any]

@dataclass(kw_only=True)
class MergeRequiredGateIdsFrame:
    body: str = field(init=False)
    context: dict[str, Any] | None
    intrinsic: set[str] = field(init=False)
    policy: dict[str, Any] = field(init=False)
    repository: str = field(init=False)
    rows: list[list[str]] = field(init=False)
    selected: set[str] | frozenset[str] = field(init=False)
    state: dict[str, Any]

@dataclass(kw_only=True)
class MergeConditionTransitionValidFrame:
    after: str
    before: str
    condition: str | None = field(init=False)
    current: dict[str, Any]

@dataclass(kw_only=True)
class MergePayloadDeltaFrame:
    claim: dict[str, Any] | None = field(init=False)
    direct_fields: frozenset[str] | None = field(init=False)
    event: dict[str, Any]
    event_name: str = field(init=False)
    integration: dict[str, Any] | None = field(init=False)
    payload: dict[str, Any] = field(init=False)
    prior: dict[str, Any] | None
    projected: dict[str, Any] = field(init=False)
    worktree: dict[str, Any] | None = field(init=False)

@dataclass(kw_only=True)
class MergeObservationShapeValidFrame:
    attempted_heads: Sequence[str]
    contains: object = field(init=False)
    exists: object = field(init=False)
    observed: object
    oid: object = field(init=False)
    vector_values: list[object] = field(init=False)

@dataclass(kw_only=True)
class MergeIntroducedDispositionValidFrame:
    current: dict[str, Any]
    current_review: dict[str, Any] = field(init=False)
    pending: bool = field(init=False)
    prior: dict[str, Any]

@dataclass(kw_only=True)
class MergeStateEdgeValidFrame:
    after: str
    before: str
    current: dict[str, Any]
    delta: dict[str, Any] = field(init=False)
    event_name: str
    evidence: tuple[bool, dict[str, Any], str | None]
    observation_phase: str | None = field(init=False)
    prior_inactive: bool = field(init=False)

@dataclass(kw_only=True)
class MergeNestedStateValidFrame:
    generation: tuple[dict[str, Any], str] | None = field(init=False)
    integration: dict[str, Any] = field(init=False)
    observed: dict[str, Any] | None = field(init=False)
    policy: dict[str, Any] = field(init=False)
    push: dict[str, Any] | None = field(init=False)
    state: dict[str, Any]
    target: dict[str, Any] = field(init=False)
    worktree: tuple[dict[str, Any], dict[str, Any]] | None = field(init=False)

@dataclass(kw_only=True)
class MergeEventEvidenceValidFrame:
    admitted: dict[str, Any] | None = field(init=False)
    admitted_nonce: object = field(init=False)
    bootstrap_fetch_result: bool = field(init=False)
    cleanup: dict[str, Any] | None = field(init=False)
    cleanup_state: dict[str, Any] | None = field(init=False)
    context: dict[str, Any] | None
    current: dict[str, Any]
    current_claim: dict[str, Any] = field(init=False)
    current_cleanup: dict[str, Any] = field(init=False)
    current_epoch: dict[str, Any] | None = field(init=False)
    current_identity: dict[str, Any] = field(init=False)
    current_integration: dict[str, Any] = field(init=False)
    current_nonce: object = field(init=False)
    disposition: object = field(init=False)
    event: dict[str, Any]
    event_at: dt.datetime | None = field(init=False)
    event_name: str = field(init=False)
    integration: dict[str, Any] | None = field(init=False)
    intent: dict[str, Any] | None = field(init=False)
    intent_names: dict[str, str] = field(init=False)
    next_context: dict[str, Any] | None = field(init=False)
    payload: dict[str, Any] = field(init=False)
    prior: dict[str, Any]
    prior_claim: dict[str, Any] = field(init=False)
    prior_cleanup: dict[str, Any] = field(init=False)
    prior_deadline: dt.datetime | None = field(init=False)
    prior_integration: dict[str, Any] = field(init=False)
    release: dict[str, Any] | None = field(init=False)
    release_mode: object = field(init=False)
    release_payload: dict[str, Any] | None = field(init=False)
    replayed_epoch: dict[str, Any] | None = field(init=False)
    result_names: dict[str, str] = field(init=False)
    successor_generation_result: bool = field(init=False)

@dataclass(kw_only=True)
class MergePushObservationEvidenceValidFrame:
    after: str = field(init=False)
    all_false: bool = field(init=False)
    before: str = field(init=False)
    classification: str | None = field(init=False)
    condition: str | None = field(init=False)
    context: dict[str, Any] | None
    current: dict[str, Any]
    current_integration: dict[str, Any] = field(init=False)
    current_push: dict[str, Any] | None = field(init=False)
    deadline: dt.datetime | None = field(init=False)
    event: dict[str, Any]
    event_at: dt.datetime | None = field(init=False)
    exists: object = field(init=False)
    inactive: bool = field(init=False)
    movement_count: int = field(init=False)
    next_count: int = field(init=False)
    observed: dict[str, Any] | None = field(init=False)
    phase: str = field(init=False)
    prior: dict[str, Any]
    prior_count: int = field(init=False)
    prior_integration: dict[str, Any] = field(init=False)
    prior_push: dict[str, Any] | None = field(init=False)

@dataclass(kw_only=True)
class StateShapeValidFrame:
    chain_id: str
    family: str
    state: object

@dataclass(kw_only=True)
class MergeCompleteTupleValidFrame:
    after: str = field(init=False)
    before: str = field(init=False)
    context: dict[str, Any] | None
    current: dict[str, Any]
    current_iteration: int | None = field(init=False)
    current_review: dict[str, Any] = field(init=False)
    event_name: str
    prior: dict[str, Any]
    prior_iteration: int | None = field(init=False)
    prior_review: dict[str, Any] = field(init=False)
    tier: dict[str, Any] | None = field(init=False)

@dataclass(kw_only=True)
class MergeTransitionValidFrame:
    _current_worktree: dict[str, Any] = field(init=False)
    after_state: str = field(init=False)
    before_state: str = field(init=False)
    context: dict[str, Any] | None
    current: dict[str, Any]
    current_claim: dict[str, Any] = field(init=False)
    current_epoch: dict[str, Any] | None = field(init=False)
    current_generation: tuple[dict[str, Any], str] | None = field(init=False)
    current_integration: dict[str, Any] = field(init=False)
    current_push_history: dict[str, Any] | None = field(init=False)
    current_status: str = field(init=False)
    current_worktree: tuple[dict[str, Any], dict[str, Any]] | None = field(init=False)
    delta: dict[str, Any] = field(init=False)
    event: dict[str, Any]
    event_at: dt.datetime | None = field(init=False)
    event_name: str = field(init=False)
    expected_inactive_after: dt.datetime | None = field(init=False)
    inactive_after: dt.datetime | None = field(init=False)
    is_receipt: bool = field(init=False)
    observation_phase: str | None = field(init=False)
    prior: dict[str, Any] | None
    prior_claim: dict[str, Any] = field(init=False)
    prior_claim_status: str = field(init=False)
    prior_epoch: dict[str, Any] | None = field(init=False)
    prior_generation: tuple[dict[str, Any], str] | None = field(init=False)
    prior_inactive: bool = field(init=False)
    prior_integration: dict[str, Any] = field(init=False)
    prior_push_history: dict[str, Any] | None = field(init=False)
    prior_status: str = field(init=False)
