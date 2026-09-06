"""Forge CLI response envelope: reason codes, refusal/frozen exceptions, and the outcome record.

Moved verbatim from scripts/forge/cli.py in cli split phase 1 (bead forge-plugin-95e.2).
"""

from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Any, Iterable, Mapping


class ReasonCode(str, Enum):
    """The closed FR-220 reason-code corpus; values must remain literal."""

    AMBIGUOUS_TARGET = "ambiguous-target"
    APPROVAL_REQUIRED = "approval-required"
    CANDIDATE_STALE = "candidate-stale"
    CITATION_OUT_OF_ROOT = "citation-out-of-root"
    DIRTY_INDEX = "dirty-index"
    DRIFT_TREE_INDEX = "drift-tree-index"
    EVIDENCE_INCOMPLETE = "evidence-incomplete"
    FROZEN_CHAIN = "frozen-chain"
    HALT_ENGAGED = "halt-engaged"
    HEAD_MOVED = "head-moved"
    INACTIVE_CHAIN = "inactive-chain"
    ITERATION_CAP = "iteration-cap"
    LIVE_CHAIN_EXISTS = "live-chain-exists"
    LOCK_UNAVAILABLE = "lock-unavailable"
    MUTATING_GATE_PENDING = "mutating-gate-pending"
    OK = "ok"
    OPERATOR_VERB_DENIED = "operator-verb-denied"
    PATH_MISSING = "path-missing"
    POLICY_CHANGED = "policy-changed"
    POLICY_UNREADABLE = "policy-unreadable"
    REVIEW_VERDICT_INVALID = "review-verdict-invalid"
    SKIP_NOT_PERMITTED = "skip-not-permitted"
    STATE_PRECONDITION = "state-precondition"
    TOKEN_CONSUMED = "token-consumed"
    TTL_EXPIRED = "ttl-expired"


class V2ReasonCode(str, Enum):
    """The complete additive 54-member ``forge-cli/2`` reason union."""

    AMBIGUOUS_TARGET = "ambiguous-target"
    APPROVAL_REQUIRED = "approval-required"
    ARCHIVE_RERENDER_MISMATCH = "archive-rerender-mismatch"
    ARCHIVE_SIZE_LIMIT = "archive-size-limit"
    BATCH_IDEMPOTENCY_CONFLICT = "batch-idempotency-conflict"
    BATCH_PENDING = "batch-pending"
    BINDING_INVALID = "binding-invalid"
    CANDIDATE_STALE = "candidate-stale"
    CITATION_OUT_OF_ROOT = "citation-out-of-root"
    CLEANUP_FAILED = "cleanup-failed"
    DIRTY_INDEX = "dirty-index"
    DIRTY_WORKTREE = "dirty-worktree"
    DRIFT_TREE_INDEX = "drift-tree-index"
    EVIDENCE_INCOMPLETE = "evidence-incomplete"
    FETCH_FAILED = "fetch-failed"
    FROZEN_CHAIN = "frozen-chain"
    HALT_ENGAGED = "halt-engaged"
    HEAD_MOVED = "head-moved"
    INACTIVE_CHAIN = "inactive-chain"
    INGEST_PROOF_INVALID = "ingest-proof-invalid"
    ITERATION_CAP = "iteration-cap"
    JOURNAL_OUTBOX_PENDING = "journal-outbox-pending"
    LEGACY_RECOVERY_APPROVAL_REQUIRED = "legacy-recovery-approval-required"
    LIVE_CHAIN_EXISTS = "live-chain-exists"
    LIVE_MERGE_CHAIN_EXISTS = "live-merge-chain-exists"
    LOCK_RELEASE_FAILED = "lock-release-failed"
    LOCK_UNAVAILABLE = "lock-unavailable"
    MERGE_GATE_FAILED = "merge-gate-failed"
    MUTATING_GATE_PENDING = "mutating-gate-pending"
    NON_FAST_FORWARD = "non-fast-forward"
    OK = "ok"
    OPERATOR_VERB_DENIED = "operator-verb-denied"
    OPTION_DUPLICATE = "option-duplicate"
    OPTION_EMPTY = "option-empty"
    PATH_MISSING = "path-missing"
    POLICY_CHANGED = "policy-changed"
    POLICY_UNREADABLE = "policy-unreadable"
    PUSH_FAILED = "push-failed"
    PUSH_OUTCOME_UNKNOWN = "push-outcome-unknown"
    PUSH_TARGET_INVALID = "push-target-invalid"
    REBASE_CONFLICT = "rebase-conflict"
    REBASE_FAILED = "rebase-failed"
    REBASE_LOCK_UNAVAILABLE = "rebase-lock-unavailable"
    REMOTE_CHURN = "remote-churn"
    REVIEW_VERDICT_INVALID = "review-verdict-invalid"
    RUN_TASK_BINDING_INVALID = "run-task-binding-invalid"
    RUN_TASK_BINDING_REQUIRED = "run-task-binding-required"
    RUN_SCOPE_EXCEEDED = "run-scope-exceeded"
    SKIP_NOT_PERMITTED = "skip-not-permitted"
    STATE_PRECONDITION = "state-precondition"
    TOKEN_CONSUMED = "token-consumed"
    TTL_EXPIRED = "ttl-expired"
    WORKTREE_INVALID = "worktree-invalid"
    WORKTREE_MISSING = "worktree-missing"


# Descriptive compatibility alias for callers that imported the initial Revision-9
# implementation name; the enum itself is V2ReasonCode.
Revision9ReasonCode = V2ReasonCode


OUTPUT_SCHEMA = "forge-cli/1"


REVISION9_OUTPUT_SCHEMA = "forge-cli/2"


ENVELOPE_KEYS = {
    "chain_id",
    "evidence_refs",
    "expected",
    "message",
    "next_required_step",
    "observed",
    "ok",
    "reason_code",
    "remediation",
    "schema",
    "state",
}


@dataclasses.dataclass(frozen=True)
class Outcome:
    ok: bool
    reason_code: ReasonCode | Revision9ReasonCode
    message: str
    chain_id: str | None = None
    state: str | None = None
    expected: str | None = None
    observed: str | None = None
    remediation: str | None = None
    next_required_step: str = "none — chain closed"
    evidence_refs: tuple[str, ...] = ()
    schema: str = OUTPUT_SCHEMA

    @property
    def exit_code(self) -> int:
        if self.reason_code.value == "ok" and self.ok:
            return 0
        if self.reason_code.value == "frozen-chain":
            return 2
        return 1

    def envelope(self) -> dict[str, Any]:
        result = {
            "chain_id": self.chain_id,
            "evidence_refs": list(self.evidence_refs),
            "expected": self.expected,
            "message": self.message,
            "next_required_step": self.next_required_step,
            "observed": self.observed,
            "ok": self.ok,
            "reason_code": self.reason_code.value,
            "remediation": self.remediation,
            "schema": self.schema,
            "state": self.state,
        }
        assert set(result) == ENVELOPE_KEYS
        return result


class Refusal(Exception):
    def __init__(
        self,
        reason_code: ReasonCode | Revision9ReasonCode,
        message: str,
        *,
        expected: str | None = None,
        observed: str | None = None,
        remediation: str | None = None,
        next_required_step: str | None = None,
        chain: Mapping[str, Any] | None = None,
        evidence_refs: Iterable[str] = (),
        schema: str | None = None,
    ) -> None:
        super().__init__(message)
        if reason_code.value in {"ok", "frozen-chain"}:
            raise ValueError("refusal must use an exit-1 reason code")
        self.reason_code = reason_code
        self.message = message
        self.expected = expected or "the command precondition to be satisfied"
        self.observed = observed or message
        self.remediation = remediation or "inspect chain status and follow the required step"
        self.next_required_step = next_required_step or self.remediation
        self.chain = chain
        self.evidence_refs = tuple(evidence_refs)
        chain_is_revision9 = bool(
            isinstance(chain, Mapping)
            and (
                chain.get("kind") == "merge"
                or chain.get("schema") == "forge-merge-chain/1"
                or chain.get("run_binding") is not None
                or isinstance(chain.get("staging"), Mapping)
                and chain.get("staging", {}).get("archive") is not None
            )
        )
        self.schema = schema or (
            REVISION9_OUTPUT_SCHEMA
            if isinstance(reason_code, V2ReasonCode) or chain_is_revision9
            else OUTPUT_SCHEMA
        )

    def outcome(self) -> Outcome:
        return Outcome(
            ok=False,
            reason_code=self.reason_code,
            message=self.message,
            chain_id=str(self.chain["chain_id"]) if self.chain else None,
            state=str(self.chain["state"]) if self.chain else None,
            expected=self.expected,
            observed=self.observed or "on-disk state unavailable or invalid",
            remediation=self.remediation,
            next_required_step=self.next_required_step,
            evidence_refs=self.evidence_refs,
            schema=self.schema,
        )


class FrozenError(Exception):
    def __init__(
        self,
        message: str,
        *,
        chain_id: str | None = None,
        state: str | None = None,
        observed: str | None = None,
        schema: str = OUTPUT_SCHEMA,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.chain_id = chain_id
        self.state = state
        self.observed = observed
        self.schema = schema

    def outcome(self) -> Outcome:
        remediation = (
            f"forge status --chain-id {self.chain_id}"
            if self.chain_id
            else "forge status"
        )
        return Outcome(
            ok=False,
            reason_code=ReasonCode.FROZEN_CHAIN,
            message=(
                f"{self.message}; chain frozen pending status/abort, never a guessed recovery"
            ),
            chain_id=self.chain_id,
            state=self.state,
            expected="digest-valid reconstructible chain state",
            observed=self.observed,
            remediation=remediation,
            next_required_step=remediation,
            schema=self.schema,
        )
