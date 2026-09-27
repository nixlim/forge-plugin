from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from typing import Any

from forge_cli import chain_core, runtime
from forge_cli.engine import _review_attempt, _review_lane_api, _review_launch
from forge_cli.engine._approval import _success as _success
from forge_cli.engine._state import TERMINAL_STATES
from forge_cli.envelope import Outcome, ReasonCode, Refusal

NEWER_REQUEST_LITERAL = (
    "forge: review request shape newer than this plugin — finish or abort the chain "
    "on the requesting version"
)
SUPPORTED_CANCEL_LANES = frozenset({"forge-review-lane/1"})


def _attempt_relative(request: Mapping[str, Any]) -> str:
    return f"review/iteration-{int(request['iteration']):02d}/{request['attempt']}"


def _attempt_fd(self, state: Mapping[str, Any], request: Mapping[str, Any]):
    return self.ctx.store.artifact_parent_descriptor(
        str(state["chain_id"]),
        f"{_attempt_relative(request)}/completion.json",
        create=False,
    )


def _clear_request(
    self, state: MutableMapping[str, Any], request: Mapping[str, Any], outcome: str
) -> None:
    cleared = dict(request)
    cleared["cleared"] = {"outcome": outcome, "at": chain_core.iso_z()}
    state["review"]["request"] = cleared
    self.ctx.store.persist(
        state,
        "review_requested",
        {
            "candidate": request["candidate"],
            "package_digest": request["package_digest"],
            "reviewer": request["reviewer"],
            "iteration": request["iteration"],
        },
    )


def _record_refusal(state: Mapping[str, Any], exc: Exception) -> Refusal:
    return Refusal(
        ReasonCode.EVIDENCE_INCOMPLETE,
        f"review attempt record is invalid: {exc}",
        observed=str(exc),
        remediation=chain_core._forge_command(state, "review cancel"),
        chain=state,
    )


def _read_open_attempt(
    state: Mapping[str, Any], request: Mapping[str, Any], attempt_fd: int
) -> dict[str, Any]:
    try:
        identity = _review_attempt.read_identity(attempt_fd, str(request["attempt"]))
        completion = _review_attempt.read_completion(attempt_fd, str(request["attempt"]))
    except _review_attempt.AttemptShapeNewer as exc:
        raise Refusal(
            ReasonCode.STATE_PRECONDITION,
            NEWER_REQUEST_LITERAL,
            observed=str(exc),
            remediation=chain_core._forge_command(state, "commit abort"),
            chain=state,
        ) from exc
    except _review_attempt.AttemptRecordError as exc:
        raise _record_refusal(state, exc) from exc
    if identity is None:
        raise Refusal(
            ReasonCode.STATE_PRECONDITION,
            "review cancel requires a published identity; attempt is still launching",
            observed="identity.json absent",
            remediation=chain_core._forge_command(state, "review collect"),
            chain=state,
        )
    if completion is not None:
        raise Refusal(
            ReasonCode.STATE_PRECONDITION,
            "review attempt already has a completion record",
            observed=str(completion.get("error")),
            remediation=chain_core._forge_command(state, "review collect"),
            chain=state,
        )
    return identity


def _cancel_group(
    state: Mapping[str, Any], identity: Mapping[str, Any]
) -> tuple[str, _review_attempt.GroupProof]:
    proof = _review_attempt.prove_group_ownership(identity)
    if proof.outcome in _review_lane_api.NO_SIGNAL_OUTCOMES:
        raise Refusal(
            ReasonCode.STATE_PRECONDITION,
            _review_attempt.cancel_identity_unproven_message(proof),
            observed=f"{proof.outcome}; members={list(proof.members)}; pgid={proof.pgid}",
            remediation=chain_core._forge_command(state, "review cancel"),
            chain=state,
        )
    result = proof
    if proof.outcome in {"wrapper-alive", "reviewer-alive"}:
        result = _review_attempt.terminate_owned_group(
            identity, _review_launch.TERMINATE_GRACE_SECONDS
        )
        if result.outcome in _review_lane_api.NO_SIGNAL_OUTCOMES:
            raise Refusal(
                ReasonCode.STATE_PRECONDITION,
                _review_attempt.cancel_identity_unproven_message(result),
                observed=f"{result.outcome}; members={list(result.members)}; pgid={result.pgid}",
                remediation=chain_core._forge_command(state, "review cancel"),
                chain=state,
            )
        if result.outcome == "kill-unconfirmed":
            raise Refusal(
                ReasonCode.STATE_PRECONDITION,
                _review_lane_api.cancel_kill_unconfirmed_message(result.members),
                observed=str(list(result.members)),
                remediation=chain_core._forge_command(state, "review cancel"),
                chain=state,
            )
    if result.outcome in _review_lane_api.LOST_OUTCOMES:
        return "wrapper-lost", result
    if result.outcome == "cancelled":
        return "cancelled", result
    raise Refusal(
        ReasonCode.STATE_PRECONDITION,
        f"review cancel refused — unexpected group proof {result.outcome}",
        observed=str(list(result.members)),
        remediation=chain_core._forge_command(state, "review cancel"),
        chain=state,
    )


def _publish_completion(
    self,
    state: Mapping[str, Any],
    request: Mapping[str, Any],
    identity: Mapping[str, Any],
    attempt_fd: int,
    outcome: str,
) -> tuple[str, _review_attempt.GroupProof | None, Outcome | None]:
    refreshed_proof: _review_attempt.GroupProof | None = None
    try:
        current = _review_attempt.read_identity(attempt_fd, str(request["attempt"]))
        if current is None:
            raise _review_attempt.AttemptRecordError(
                "identity.json disappeared before completion publication"
            )
        if any(
            current.get(field) != identity.get(field)
            for field in _review_lane_api.IMMUTABLE_IDENTITY_FIELDS
        ):
            raise _review_attempt.AttemptRecordError(
                "identity.json changed group identity before completion publication"
            )
        if any(
            current.get(field) != identity.get(field)
            for field in _review_lane_api.REFRESH_RECHECK_FIELDS
        ):
            outcome, refreshed_proof = _cancel_group(state, current)
        identity = current
        record = _review_attempt.make_terminal_completion(
            request, outcome, identity=identity,
            overrides={"reviewer_pid": identity.get("reviewer_pid")},
        )
        published = _review_attempt.publish_terminal_completion(attempt_fd, record)
        if published:
            return outcome, refreshed_proof, None
        existing = _review_attempt.read_completion(attempt_fd, str(request["attempt"]))
        if existing is None:
            raise Refusal(
                ReasonCode.EVIDENCE_INCOMPLETE,
                "review completion raced review cancel but is unreadable",
                remediation=chain_core._forge_command(state, "review cancel"),
                chain=state,
            )
        _review_attempt.validate_completion_binding(existing, request, identity)
    except _review_attempt.AttemptShapeNewer as exc:
        raise Refusal(
            ReasonCode.STATE_PRECONDITION,
            NEWER_REQUEST_LITERAL,
            observed=str(exc),
            remediation=chain_core._forge_command(state, "commit abort"),
            chain=state,
        ) from exc
    except _review_attempt.AttemptRecordError as exc:
        raise _record_refusal(state, exc) from exc
    existing_error = existing.get("error")
    if existing_error in {"cancelled", "wrapper-lost"}:
        return str(existing_error), refreshed_proof, None
    result = _success(
        state,
        "review attempt already completed",
        self.next_step(state),
        evidence_refs=[str(request["completion_path"])],
    )
    return outcome, refreshed_proof, result


def _completion_only(state: Mapping[str, Any]) -> bool:
    inactive = runtime.utc_now() >= chain_core.parse_time(str(state["inactive_after"]))
    capped = int(state["review"].get("iteration", 0)) >= 8
    terminal = state.get("state") in TERMINAL_STATES
    if state.get("state") != "reviewing" and not (inactive or capped or terminal):
        raise Refusal(
            ReasonCode.STATE_PRECONDITION,
            "review cancel requires a reviewing, inactive, iteration-capped, or terminal chain",
            observed=str(state.get("state")),
            remediation=chain_core._forge_command(state, "status"), chain=state,
        )
    return inactive or capped or terminal


def review_cancel(self) -> Outcome:
    state = self.select(include_terminal=True)
    self._preflight(state, "review cancel", allow_head_moved=True, check_candidate=False)
    request = state.get("review", {}).get("request")
    lane = request.get("lane") if isinstance(request, dict) else None
    if lane is not None and lane not in SUPPORTED_CANCEL_LANES:
        raise Refusal(
            ReasonCode.STATE_PRECONDITION, NEWER_REQUEST_LITERAL,
            observed=str(lane), remediation=chain_core._forge_command(state, "commit abort"),
            chain=state,
        )
    completion_only = _completion_only(state)
    if (
        not isinstance(request, dict)
        or request.get("lane") != "forge-review-lane/1"
        or not request.get("attempt")
    ):
        raise Refusal(
            ReasonCode.STATE_PRECONDITION,
            "review cancel requires a new-lane attempt with a published identity",
            observed=str(request),
            remediation=self.next_step(state),
            chain=state,
        )
    with _attempt_fd(self, state, request) as (attempt_fd, _name):
        with _review_attempt.attempt_publication_lock(attempt_fd) as acquired:
            if not acquired:
                raise _record_refusal(
                    state, _review_attempt.AttemptRecordError(
                        "attempt publication lock was not acquired"
                    )
                )
            identity = _read_open_attempt(state, request, attempt_fd)
            if identity.get("wrapper_pid") is None:
                try:
                    won, record = _review_attempt.claim_abandoned(attempt_fd, request)
                except _review_attempt.AttemptRecordError as exc:
                    raise _record_refusal(state, exc) from exc
                outcome = str(record.get("error"))
                proof = _review_attempt.GroupProof("group-empty", None)
                finished = None if won else _success(
                    state, "review attempt already completed", self.next_step(state),
                    evidence_refs=[str(request["completion_path"])],
                )
            else:
                outcome, proof = _cancel_group(state, identity)
                outcome, refreshed_proof, finished = _publish_completion(
                    self, state, request, identity, attempt_fd, outcome
                )
                proof = refreshed_proof or proof
    if finished is not None:
        return finished
    if not completion_only:
        _clear_request(self, state, request, outcome)
    member_note = (
        f"; identity-unproven members={list(proof.members)}"
        if proof.outcome == "identity-unproven"
        else ""
    )
    next_required = self.next_step(state)
    if completion_only and state["state"] == "reviewing":
        next_required = chain_core._forge_command(
            state, "commit abort --reason review-cancelled"
        )
    return _success(
        state,
        f"review attempt {outcome}{member_note}",
        next_required,
        evidence_refs=[str(request["completion_path"])],
    )
