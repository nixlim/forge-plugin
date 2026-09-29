"""Collect and cancel typed launches above the shared request-free lane."""

from __future__ import annotations

import dataclasses
import datetime as dt
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from forge_cli import chain_core, runtime
from forge_cli.engine import _launch_lane, _review_attempt, _review_lane_api, _review_launch
from forge_cli.envelope import Outcome, Refusal, V2ReasonCode

if TYPE_CHECKING:
    from forge_cli.engine._engine import Engine

IDENTITY_REFRESH_LIMIT = 8
_BINDING_FIELDS = (
    "attempt",
    "provider",
    "route_source",
    "route_sha256",
    "sandbox",
    "argv_digest",
    "prompt_digest",
    "wrapper_pid",
    "pgid",
    "reviewer_pid",
)
# These AttemptRecordError prefixes identify completion-to-request binding failures.
_BINDING_ERROR_PREFIXES = (
    "completion.json ",
    "abandoned completion ",
)


@dataclasses.dataclass(frozen=True)
class BoundExecution:
    run: _launch_lane.RunState
    record: dict[str, object]
    result: dict[str, object] | None
    paths: _launch_lane.LaunchPaths
    marker: dict[str, Any]


def _execution_record(state: Any, execution: str, verb: str) -> dict[str, object]:
    matches = [
        dict(record)
        for record in state.records
        if record.get("type") == "execution" and record.get("execution") == execution
    ]
    if len(matches) != 1:
        raise Refusal(
            V2ReasonCode.STATE_PRECONDITION,
            f"forge: launch {verb} refused — execution {execution} does not exist",
        )
    return matches[0]


def _binding_refusal(verb: str, execution: str, field: str) -> Refusal:
    return Refusal(
        V2ReasonCode.BINDING_INVALID,
        f"forge: launch {verb} refused — launch marker does not bind execution "
        f"{execution}: {field}",
    )


def _marker_paths(
    run_dir: Path,
    record: Mapping[str, object],
    execution: str,
    verb: str,
) -> _launch_lane.LaunchPaths:
    marker_ref = record.get("launch_marker")
    if not isinstance(marker_ref, str):
        suffix = "; collect a prose launch by prose" if verb == "collect" else ""
        raise Refusal(
            V2ReasonCode.STATE_PRECONDITION,
            f"forge: launch {verb} refused — execution {execution} has no "
            f"launch_marker{suffix}",
        )
    agent = record.get("agent")
    if not _launch_lane.valid_component(agent):
        raise _binding_refusal(verb, execution, "agent")
    try:
        paths = _launch_lane.LaunchPaths(run_dir, str(agent), execution)
    except ValueError as exc:
        raise _binding_refusal(verb, execution, "execution") from exc
    if marker_ref != paths.reference(_launch_lane.MARKER_NAME):
        raise _binding_refusal(verb, execution, "launch_marker")
    return paths


def _load_marker(
    ctx: chain_core.CommandContext,
    record: Mapping[str, object],
    paths: _launch_lane.LaunchPaths,
    run_id: str,
    verb: str,
    execution: str,
) -> dict[str, Any]:
    try:
        marker = _launch_lane.read_marker(paths.leaf(_launch_lane.MARKER_NAME))
        if marker.get("run_id") != run_id:
            raise _binding_refusal(verb, execution, "run_id")
        field = _launch_lane.bind_marker(ctx, marker, record, paths)
    except Refusal:
        raise
    except (OSError, ValueError) as exc:
        raise _binding_refusal(verb, execution, "marker") from exc
    if field is not None:
        raise _binding_refusal(verb, execution, field)
    return marker


def _bound_execution(self: Engine, execution: str, verb: str) -> BoundExecution:
    """Bind a journal owner to its validated marker after shared checkpoints."""

    chain_core.register_coordination_seams()
    _launch_lane.require_no_halt(self.ctx)
    run_id = _launch_lane.require_run_id(self.ctx)
    run = _launch_lane.run_state(self.ctx, run_id)
    record = _execution_record(run.state, execution, verb)
    paths = _marker_paths(run.run_dir, record, execution, verb)
    marker = _load_marker(self.ctx, record, paths, run_id, verb, execution)
    result = _launch_lane.result_record(run.state, execution, paths.agent)
    return BoundExecution(run, record, result, paths, marker)


def _attempt_refusal(verb: str, execution: str, detail: object) -> Refusal:
    return Refusal(
        V2ReasonCode.EVIDENCE_INCOMPLETE,
        f"forge: launch {verb} refused — attempt record is invalid for "
        f"{execution}: {detail}",
    )


def _binding_field(exc: Exception) -> str:
    return next((field for field in _BINDING_FIELDS if field in str(exc)), "completion")


def _completion_binding_refusal(verb: str, execution: str, field: str) -> Refusal:
    return Refusal(
        V2ReasonCode.BINDING_INVALID,
        f"forge: launch {verb} refused — completion does not bind execution "
        f"{execution}: {field}",
    )


def _attempt_or_binding_refusal(verb: str, execution: str, exc: Exception) -> Refusal:
    """Classify message-prefixed attempt errors that are binding failures."""

    detail = str(exc)
    if detail.startswith(_BINDING_ERROR_PREFIXES) or detail == "attempt binding differs":
        return _completion_binding_refusal(verb, execution, _binding_field(exc))
    return _attempt_refusal(verb, execution, exc)


def _cancel_terminal(execution: str) -> Refusal:
    message = (
        f"forge: launch cancel refused — execution {execution} already has a "
        "completion or a terminal result; run launch collect"
    )
    return Refusal(V2ReasonCode.STATE_PRECONDITION, message)


def _identity_unproven(
    verb: str, execution: str, members: Sequence[int], pgid: object
) -> Refusal:
    code = (
        V2ReasonCode.EVIDENCE_INCOMPLETE
        if verb == "collect"
        else V2ReasonCode.STATE_PRECONDITION
    )
    return Refusal(
        code,
        f"forge: launch {verb} refused — identity-unproven for {execution}; "
        f"member PIDs {list(members)}; recorded PGID {pgid}; nothing was signalled",
    )


def _observe(
    bound: BoundExecution, attempt_fd: int
) -> _review_attempt.AttemptObservation:
    deadline = chain_core.parse_time(str(bound.marker["requested_at"])) + dt.timedelta(
        seconds=_review_launch.IDENTITY_DEADLINE_SECONDS
    )
    try:
        return _review_attempt.observe_attempt(
            attempt_fd,
            str(bound.marker["attempt"]),
            deadline,
            runtime.utc_now(),
        )
    except _review_attempt.AttemptRecordError as exc:
        if str(exc) == "attempt binding differs":
            raise _completion_binding_refusal(
                "collect", bound.paths.execution, "attempt"
            ) from exc
        raise _attempt_refusal("collect", bound.paths.execution, exc) from exc


def _publish_wrapper_lost(
    bound: BoundExecution,
    attempt_fd: int,
    observation: _review_attempt.AttemptObservation,
) -> _review_attempt.AttemptObservation:
    try:
        published, completion = _review_lane_api.publish_or_read_terminal(
            attempt_fd,
            _launch_lane.marker_binding(bound.marker),
            "wrapper-lost",
            observation.identity,
        )
        if published:
            return dataclasses.replace(
                observation,
                outcome="completed",
                completion=completion,
            )
        return _observe(bound, attempt_fd)
    except _review_attempt.AttemptRecordError as exc:
        raise _attempt_or_binding_refusal(
            "collect", bound.paths.execution, exc
        ) from exc


def _classify_attempt(
    bound: BoundExecution, attempt_fd: int
) -> _review_attempt.AttemptObservation:
    """Claim abandonable attempts before mapping wrapper loss to completion."""

    observation = _observe(bound, attempt_fd)
    if observation.outcome in {"abandonable", "abandoned-claimed"}:
        try:
            _review_attempt.claim_abandoned(
                attempt_fd,
                _launch_lane.marker_binding(bound.marker),
            )
        except _review_attempt.AttemptRecordError as exc:
            raise _attempt_or_binding_refusal(
                "collect", bound.paths.execution, exc
            ) from exc
        observation = _observe(bound, attempt_fd)
    if observation.outcome == "wrapper-lost":
        observation = _publish_wrapper_lost(bound, attempt_fd, observation)
    return observation


def _nonterminal_refusal(
    bound: BoundExecution, observation: _review_attempt.AttemptObservation
) -> Refusal:
    execution = bound.paths.execution
    if observation.outcome in _review_lane_api.NO_SIGNAL_OUTCOMES:
        identity = observation.identity or {}
        return _identity_unproven(
            "collect",
            execution,
            observation.members,
            identity.get("pgid"),
        )
    if observation.outcome == "launching":
        return Refusal(
            V2ReasonCode.EVIDENCE_INCOMPLETE,
            f"forge: launch collect refused — execution {execution} is still "
            "launching; retry after the identity deadline",
        )
    if observation.outcome in {"running", "wrapper-alive / child-dead"}:
        return Refusal(
            V2ReasonCode.EVIDENCE_INCOMPLETE,
            f"forge: launch collect refused — execution {execution} is still running",
        )
    if observation.outcome == "wrapper-dead / child-alive":
        return Refusal(
            V2ReasonCode.EVIDENCE_INCOMPLETE,
            f"forge: launch collect refused — wrapper-dead / child-alive for "
            f"{execution}; run launch cancel --repo {bound.run.repository} --run-id "
            f"{bound.run.run_dir.name} --execution {execution}",
        )
    return Refusal(
        V2ReasonCode.EVIDENCE_INCOMPLETE,
        f"forge: launch collect refused — execution {execution} is "
        f"{observation.outcome}",
    )


def _validated_completion(
    bound: BoundExecution, observation: _review_attempt.AttemptObservation
) -> dict[str, Any]:
    completion = observation.completion
    if completion is None:
        raise _attempt_refusal(
            "collect", bound.paths.execution, "completed attempt has no completion"
        )
    try:
        _review_attempt.validate_completion_binding(
            completion,
            _launch_lane.marker_binding(bound.marker),
            observation.identity,
        )
    except _review_attempt.AttemptRecordError as exc:
        raise _completion_binding_refusal(
            "collect", bound.paths.execution, _binding_field(exc)
        ) from exc
    return completion


def launch_collect(self: Engine, execution: str) -> Outcome:
    """Collect one typed execution without synthesizing terminal evidence."""

    bound = _bound_execution(self, execution, "collect")
    if bound.result is not None:
        _launch_lane.mark_collected(
            bound.paths,
            bound.marker,
            bound.result.get("status"),
        )
        return _launch_lane.terminal_outcome(bound.paths, bound.result)
    try:
        attempt_fd = _launch_lane.open_attempt(bound.paths)
    except OSError as exc:
        raise _attempt_refusal("collect", execution, exc) from exc
    try:
        observation = _classify_attempt(bound, attempt_fd)
        if observation.outcome != "completed":
            raise _nonterminal_refusal(bound, observation)
        completion = _validated_completion(bound, observation)
    finally:
        os.close(attempt_fd)
    try:
        raw = _launch_lane.read_private_record(
            bound.paths.leaf(_review_attempt.COMPLETION_NAME)
        )
    except OSError as exc:
        raise _attempt_refusal("collect", execution, exc) from exc
    mapped = _launch_lane.map_completion(bound.record, bound.paths, completion)
    result, _repeated = _launch_lane.append_execution_result(
        bound.run,
        bound.paths,
        task=str(bound.record["task"]),
        result=mapped,
        completion_raw=raw,
    )
    _launch_lane.mark_collected(bound.paths, bound.marker, result.get("status"))
    return _launch_lane.terminal_outcome(bound.paths, result, message=mapped.message)


def _read_cancel_identity(
    bound: BoundExecution, attempt_fd: int
) -> dict[str, Any]:
    try:
        completion = _review_attempt.read_completion(
            attempt_fd,
            str(bound.marker["attempt"]),
        )
        identity = _review_attempt.read_identity(
            attempt_fd,
            str(bound.marker["attempt"]),
        )
    except _review_attempt.AttemptRecordError as exc:
        raise _attempt_refusal("cancel", bound.paths.execution, exc) from exc
    if completion is not None:
        raise _cancel_terminal(bound.paths.execution)
    if identity is None:
        raise Refusal(
            V2ReasonCode.STATE_PRECONDITION,
            f"forge: launch cancel refused — execution {bound.paths.execution} has no "
            "wrapper identity yet; run launch collect",
        )
    return identity


def _cancel_group(bound: BoundExecution, identity: Mapping[str, Any]) -> str:
    proof = _review_attempt.prove_group_ownership(identity)
    if proof.outcome in _review_lane_api.NO_SIGNAL_OUTCOMES:
        raise _identity_unproven(
            "cancel", bound.paths.execution, proof.members, proof.pgid
        )
    if proof.outcome in {"wrapper-alive", "reviewer-alive"}:
        proof = _review_attempt.terminate_owned_group(
            identity,
            _review_launch.TERMINATE_GRACE_SECONDS,
        )
    if proof.outcome in _review_lane_api.NO_SIGNAL_OUTCOMES:
        raise _identity_unproven(
            "cancel", bound.paths.execution, proof.members, proof.pgid
        )
    if proof.outcome == "kill-unconfirmed":
        raise Refusal(
            V2ReasonCode.EVIDENCE_INCOMPLETE,
            f"forge: launch cancel refused — kill-unconfirmed for "
            f"{bound.paths.execution}: {list(proof.members)}",
        )
    if proof.outcome == "cancelled":
        return "cancelled"
    if proof.outcome in _review_lane_api.LOST_OUTCOMES:
        return "wrapper-lost"
    raise Refusal(
        V2ReasonCode.STATE_PRECONDITION,
        f"forge: launch cancel refused — unexpected group proof {proof.outcome} "
        f"for {bound.paths.execution}",
    )


def _settle_identity(
    bound: BoundExecution,
    attempt_fd: int,
    identity: dict[str, Any],
    outcome: str,
) -> tuple[dict[str, Any], str]:
    for _index in range(IDENTITY_REFRESH_LIMIT):
        try:
            current = _review_attempt.read_identity(
                attempt_fd,
                str(bound.marker["attempt"]),
            )
        except _review_attempt.AttemptRecordError as exc:
            raise _attempt_refusal("cancel", bound.paths.execution, exc) from exc
        if current is None or any(
            current.get(field) != identity.get(field)
            for field in _review_lane_api.IMMUTABLE_IDENTITY_FIELDS
        ):
            raise _attempt_refusal(
                "cancel",
                bound.paths.execution,
                "identity.json changed group identity before completion publication",
            )
        changed = any(
            current.get(field) != identity.get(field)
            for field in _review_lane_api.REFRESH_RECHECK_FIELDS
        )
        identity = current
        if not changed:
            return identity, outcome
        outcome = _cancel_group(bound, identity)
    else:
        raise _attempt_refusal(
            "cancel",
            bound.paths.execution,
            "identity.json kept changing before completion publication",
        )


def _publish_cancel(
    bound: BoundExecution, attempt_fd: int, identity: dict[str, Any]
) -> None:
    """Re-prove an identity whose reviewer fields may refresh, then publish."""

    outcome = _cancel_group(bound, identity)
    identity, outcome = _settle_identity(bound, attempt_fd, identity, outcome)
    try:
        _review_lane_api.publish_or_read_terminal(
            attempt_fd,
            _launch_lane.marker_binding(bound.marker),
            outcome,
            identity,
        )
    except _review_attempt.AttemptRecordError as exc:
        raise _attempt_or_binding_refusal(
            "cancel", bound.paths.execution, exc
        ) from exc
    # A completion published by either winner of the race is collected below.


def _cancel_unlaunched(bound: BoundExecution, attempt_fd: int) -> None:
    try:
        _review_attempt.claim_abandoned(
            attempt_fd,
            _launch_lane.marker_binding(bound.marker),
        )
    except _review_attempt.AttemptRecordError as exc:
        raise _attempt_or_binding_refusal(
            "cancel", bound.paths.execution, exc
        ) from exc


def launch_cancel(self: Engine, execution: str) -> Outcome:
    """Cancel only a proven owned group, including refreshed reviewer identity."""

    bound = _bound_execution(self, execution, "cancel")
    if bound.result is not None:
        raise _cancel_terminal(execution)
    try:
        attempt_fd = _launch_lane.open_attempt(bound.paths)
    except OSError as exc:
        raise _attempt_refusal("cancel", execution, exc) from exc
    try:
        with _review_attempt.attempt_publication_lock(attempt_fd) as acquired:
            if not acquired:
                raise Refusal(
                    V2ReasonCode.STATE_PRECONDITION,
                    f"forge: launch cancel refused — attempt publication lock was not "
                    f"acquired for {execution}",
                )
            state = bound.run.journal._scan_run(bound.run.run_dir)
            if _launch_lane.result_record(state, execution, bound.paths.agent) is not None:
                raise _cancel_terminal(execution)
            identity = _read_cancel_identity(bound, attempt_fd)
            if identity.get("wrapper_pid") is None:
                _cancel_unlaunched(bound, attempt_fd)
            else:
                _publish_cancel(bound, attempt_fd, identity)
    finally:
        os.close(attempt_fd)
    return self.launch_collect(execution)
