"""Headless provider-routed review lane for merge chains."""

from __future__ import annotations

import copy
import datetime as dt
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from forge_cli import chain_core, engine, runtime
from forge_cli.app._candidate_observation import _observe_current_merge_candidate
from forge_cli.engine import _review_lane_api
from forge_cli.envelope import REVISION9_OUTPUT_SCHEMA, FrozenError, Outcome, Refusal, V2ReasonCode
from forge_cli.policy import sha256_bytes

if TYPE_CHECKING:
    from forge_cli.app._merge_engine import MergeEngine


_LANE = "forge-review-lane/1"
_RETRYABLE = frozenset("abandoned wrapper-lost cancelled launch-failed not-logged-in".split())
def _terminal_error(error: object) -> bool:
    return error in _RETRYABLE or isinstance(error, str) and error.startswith("launch-failed: ")


def _immutable_identity_matches(before: Mapping[str, Any], after: Mapping[str, Any]) -> bool:
    return all(
        before.get(name) == after.get(name)
        for name in _review_lane_api.IMMUTABLE_IDENTITY_FIELDS
    )


def _iteration(state: Mapping[str, Any]) -> int:
    review = state.get("review")
    if type(value := review.get("iteration", 0) if isinstance(review, Mapping) else 0) is not int:
        raise FrozenError(
            "merge review iteration is malformed", chain_id=str(state["chain_id"]),
            schema=REVISION9_OUTPUT_SCHEMA)
    return value


def _request(state: Mapping[str, Any]) -> Mapping[str, Any] | None:
    review = state.get("review")
    request = review.get("request") if isinstance(review, Mapping) else None
    return request if isinstance(request, Mapping) else None


def _attempt_relative(request: Mapping[str, Any]) -> str:
    return f"review/iteration-{int(request['iteration']):02d}/{request['attempt']}"


def _attempt_descriptor(self: MergeEngine, state, request):
    relative = f"{_attempt_relative(request)}/completion.json"
    return self.ctx.store.artifact_parent_descriptor(str(state["chain_id"]), relative, create=False)


def _shape_refusal(state: Mapping[str, Any], observed: object) -> Refusal:
    return chain_core._merge_refusal(
        V2ReasonCode.STATE_PRECONDITION, engine.NEWER_SHAPE_LITERAL,
        expected=_LANE, observed=str(observed),
        remediation=f"forge merge abort --chain-id {state['chain_id']} --reason newer-review-shape",
        chain=state)


def _observe(self: MergeEngine, state, request) -> engine.AttemptObservation:
    deadline = chain_core.parse_time(str(request["requested_at"])) + dt.timedelta(
        seconds=engine.IDENTITY_DEADLINE_SECONDS)
    try:
        with _attempt_descriptor(self, state, request) as (directory, _name):
            return engine.observe_attempt(
                directory, str(request["attempt"]), deadline, runtime.utc_now())
    except engine.AttemptShapeNewer as exc:
        raise _shape_refusal(state, exc) from exc
    except engine.AttemptRecordError as exc:
        raise chain_core._merge_refusal(
            V2ReasonCode.EVIDENCE_INCOMPLETE,
            "forge: review attempt record is invalid",
            expected="canonical owner-only identity and completion records",
            observed=str(exc),
            remediation=f"forge review cancel --chain-id {state['chain_id']}",
            chain=state,
        ) from exc


def _publish_lost(
    self: MergeEngine,
    state: Mapping[str, Any],
    request: Mapping[str, Any],
    observation: engine.AttemptObservation,
) -> dict[str, Any]:
    with _attempt_descriptor(self, state, request) as (directory, _name):
        _published, completion = engine.publish_or_read_terminal(
            directory, request, "wrapper-lost", observation.identity
        )
        completed = engine.AttemptObservation(
            "completed", identity=observation.identity, completion=completion)
        return self._validated_review_completion(state, request, completed)


def _recover_retryable(self: MergeEngine, state, request) -> bool:
    lane = request.get("lane")
    if lane != _LANE:
        if lane is not None or "provider" in request or "attempt" in request:
            raise _shape_refusal(state, lane)
        return False
    observed = _observe(self, state, request)
    if observed.outcome == "completed":
        completion = self._validated_review_completion(state, request, observed)
        return _terminal_error(completion.get("error"))
    if observed.outcome in {"abandonable", "abandoned-claimed"}:
        with _attempt_descriptor(self, state, request) as (directory, _name):
            won, _completion = engine.claim_abandoned(directory, request)
        if won:
            return True
        observed = _observe(self, state, request)
    if observed.outcome == "wrapper-lost":
        completion = _publish_lost(self, state, request, observed)
        return _terminal_error(completion.get("error"))
    return False


def _routed_package(
    package_parts: tuple[bytes, list[str], dict[str, list[str]]],
    route: engine.ReviewRoute,
    paths: engine.ReviewPaths,
) -> tuple[bytes, list[str], dict[str, list[str]]]:
    package, profiles, profile_map = package_parts
    lines = (
        f"route: {route.provider}/{route.model}/{route.effort}/"
        f"{route.route_source}/{route.route_sha256}\n"
        f"sandbox: {route.sandbox}\n"
        f"plugin-root: {paths.plugin_root}\n"
        f"role-body-digest: {paths.role_body_digest}\n"
    ).encode()
    marker = b"reviewer: review-final\n"
    package = package.replace(marker, marker + lines, 1) if marker in package else lines + package
    role_start = b"--- BEGIN CONTROLLING REVIEW POLICY ---\n"
    role_end = b"\n--- review constitution ---\n"
    before, found, after = package.partition(role_start)
    if found and role_end in after:
        _old_role, _end, after = after.partition(role_end)
        package = before + role_start + paths.role_body + role_end + after
    else:
        package += b"\n--- derived review-final body ---\n" + paths.role_body
    return package, profiles, profile_map


def _review_prompt(
    state: Mapping[str, Any],
    package: bytes,
    package_path,
    package_digest: str,
    route: engine.ReviewRoute,
    paths: engine.ReviewPaths,
) -> bytes:
    candidate = str(state["candidate"]["candidate_head"])
    if engine._review_package_is_oversized(package):
        prompt = engine._review_master_pointer_prompt(
            package_path, len(package), package_digest, candidate
        )
    else:
        prompt = package + (
            "\n--- BEGIN CONTROLLING OUTPUT CONTRACT ---\n"
            "Remain read-only and return exactly this verdict grammar:\n"
            "VERDICT: PASS|BLOCK\n"
            "Cite the package header's candidate exactly once in the verdict.\n"
            f"package: {package_digest}\n"
            "Optional repeated line: finding: <CRITICAL|MAJOR|MINOR> <text>\n"
            "--- END CONTROLLING OUTPUT CONTRACT ---\n"
        ).encode()
    if route.provider == "codex":
        prompt = paths.role_body + b"\n" + prompt
    return prompt


def _request_record(
    state: Mapping[str, Any],
    launch: engine.ReviewLaunch,
    package_info: tuple[str, str, list[str], dict[str, list[str]], int],
) -> dict[str, Any]:
    package_ref, package_digest, profiles, profile_map, byte_length = package_info
    request: dict[str, Any] = {
        "candidate": state["candidate"]["candidate_head"],
        "package": package_ref,
        "package_digest": package_digest,
        "reviewer": "review-final",
        "iteration": _iteration(state) + 1,
        "requested_at": chain_core.iso_z(),
        "generation_digest": state["candidate"]["generation_digest"],
        "target": copy.deepcopy(state["target"]),
        "profiles": profiles,
        "profile_map": profile_map,
        "byte_length": byte_length,
    }
    request.update(launch.request_fields())
    if byte_length > engine.REVIEW_DIRECT_PACKAGE_MAX_BYTES:
        request.update(
            {
                "transport": "single-master-package",
                "window_size": engine.REVIEW_MASTER_WINDOW_BYTES,
                "window_count": engine._review_master_window_count(byte_length),
            }
        )
    return request


def _ensure_request_admitted(
    self: MergeEngine, state: dict[str, Any], request: Mapping[str, Any] | None
) -> None:
    if request is not None and not _recover_retryable(self, state, request):
        next_verb = "review collect" if request.get("lane") == _LANE else "review attach"
        raise chain_core._merge_refusal(
            V2ReasonCode.STATE_PRECONDITION,
            f"forge: review request refused — a review request is outstanding; use {next_verb}",
            expected="a terminal prior review attempt",
            observed=str(request.get("attempt") or request.get("reviewer")),
            remediation=f"forge {next_verb} --chain-id {state['chain_id']}",
            chain=state,
        )


def _next_request_iteration(state: Mapping[str, Any]) -> int:
    iteration = _iteration(state)
    if iteration >= 8:
        raise chain_core._merge_refusal(
            V2ReasonCode.ITERATION_CAP,
            "review iteration cap of 8 reached; no further merge review is admitted",
            expected="PASS before iteration 8",
            observed=str(iteration),
            chain=state,
        )
    return iteration + 1


def review_request(self: MergeEngine) -> Outcome:
    chain_core._require_merge_adapter_control("mandatory-review-final")
    state = self._load()
    self._halt(state)
    state = self._preflight_lifecycle(state, "review request")
    iteration = _next_request_iteration(state)
    if state["state"] != "reviewing":
        self._wrong_state(state, "reviewing", "review request")
    _ensure_request_admitted(self, state, _request(state))
    repository, policy, changed = _observe_current_merge_candidate(
        self.ctx, state, verb="review request"
    )
    suite = engine._merge_gate_suite(state, policy)
    if not all(engine._merge_gate_current(state, gate_id) for gate_id in suite):
        raise chain_core._merge_refusal(
            V2ReasonCode.EVIDENCE_INCOMPLETE,
            "forge: review request refused — merge mechanical evidence is incomplete",
            expected="every current-generation merge gate PASS",
            chain=state,
        )
    route = engine.resolve_review_route(
        self.ctx, "review-final", str(state["candidate"]["remote_tip"]), state=state
    )
    attempt = engine.new_attempt_id()
    relative = f"review/iteration-{iteration:02d}/{attempt}"
    worktree = self.ctx.repo.root.parent / str(state["worktree"]["path"])
    paths = engine.prepare_review_paths(
        self.ctx, str(state["chain_id"]), relative, worktree, "review-final", state
    )
    package_parts = self._review_package(state, repository, policy, list(changed))
    package, profiles, profile_map = _routed_package(
        package_parts, route, paths
    )
    package_digest = sha256_bytes(package)
    package_ref = engine._write_merge_artifact(
        self.ctx, state, f"{relative}/package.txt",
        package, master_package=True,
    )
    bound = engine._merge_run_directory(state)
    package_path = (
        self.ctx.store.common_root / package_ref if bound is None else bound[1] / package_ref
    )
    prompt = _review_prompt(state, package, package_path, package_digest, route, paths)
    launch = engine.prepare_review_launch(self.ctx, state, paths, route, prompt)
    package_info = (package_ref, package_digest, profiles, profile_map, len(package))
    request = _request_record(state, launch, package_info)
    try:
        current = self.store.transition(
            state, "review_requested", {"delta": {"review": {
                "iteration": iteration, "request": request,
            }}}, generation_digest=str(state["candidate"]["generation_digest"]),
            at=chain_core.iso_z(),
        )
    except BaseException:
        engine.close_review_launch(launch)
        raise
    try:
        process = engine.launch_review_wrapper(launch)
    except Exception as exc:
        failure = engine.launch_failure(exc)
        with _attempt_descriptor(self, current, request) as (directory, _name):
            self._publish_launch_failure(
                current, directory, request, failure
            )
        raise chain_core._merge_refusal(
            V2ReasonCode.EVIDENCE_INCOMPLETE,
            "forge: review request failed — reviewer launch failed: "
            f"{failure.removeprefix('launch-failed: ')}",
            expected="a detached provider reviewer",
            observed=failure.removeprefix("launch-failed: "),
            remediation=(
                f"forge review request --chain-id {state['chain_id']}"
                if iteration < 8
                else f"forge merge abort --chain-id {state['chain_id']} "
                "--reason iteration-cap"
            ),
            chain=current,
        ) from exc
    refs = [package_ref] + [str(request[f"{name}_path"]) for name in (
        "prompt", "events", "stderr", "identity", "completion", "verdict",
    )]
    return engine._success(
        current,
        f"review-final launched detached with wrapper PID {process.pid}",
        f"forge review collect --chain-id {state['chain_id']}",
        evidence_refs=refs,
    )


def _collect_pending(
    state: Mapping[str, Any], request: Mapping[str, Any], observed: engine.AttemptObservation,
    stale: tuple[str, ...],
) -> Refusal:
    suffix = (
        "; use review cancel"
        if observed.outcome in _review_lane_api.CANCEL_REQUIRED_OUTCOMES
        else ""
    )
    return chain_core._merge_refusal(
        V2ReasonCode.STATE_PRECONDITION,
        f"forge: review collect refused — review attempt is {observed.outcome}{suffix}",
        expected="the current attempt to publish an atomic completion record",
        observed=f"{observed.reason or observed.outcome}; members={list(observed.members)}",
        remediation=(f"forge review cancel --chain-id {state['chain_id']}" if suffix
                     else f"forge review collect --chain-id {state['chain_id']}"),
        chain=state,
        evidence_refs=[str(request.get("events_path") or ""), *stale],
    )


def _synthetic_block(
    self: MergeEngine,
    state: dict[str, Any],
    request: Mapping[str, Any],
    error: str,
    changed_paths: list[str],
) -> Outcome:
    text = f"no reviewer verdict — {error}; completion {request['completion_path']}"
    data = (
        "VERDICT: BLOCK\n"
        f"candidate: {state['candidate']['candidate_head']}\n"
        f"package: {request['package_digest']}\n"
        f"finding: MAJOR {text}\n"
    ).encode()
    verdict = engine.Engine._parse_verdict(
        data, str(state["candidate"]["candidate_head"]), str(request["package_digest"])
    )
    return self._record_review_verdict(state, verdict, data, changed_paths)


def _completed_review(
    self: MergeEngine,
    state: dict[str, Any],
    request: Mapping[str, Any],
    observed: engine.AttemptObservation,
    changed_paths: list[str],
) -> Outcome:
    completion = self._validated_review_completion(state, request, observed)
    return _finish_completed_review(self, state, request, completion, changed_paths)


def _finish_completed_review(
    self: MergeEngine,
    state: dict[str, Any],
    request: Mapping[str, Any],
    completion: Mapping[str, Any],
    changed_paths: list[str],
) -> Outcome:
    error = completion.get("error")
    if _terminal_error(error):
        return self._review_retry_outcome(state, request, str(error))
    if error is not None or completion.get("timed_out") or completion.get("returncode") != 0:
        failure = error or ("timeout" if completion.get("timed_out") else "nonzero exit")
        return _synthetic_block(self, state, request, str(failure), changed_paths)
    try:
        data = engine._read_bound_artifact(
            self.ctx, state, str(request["verdict_path"]),
            str(completion["verdict_digest"]), "review verdict",
            max_bytes=runtime.OUTPUT_CAP_BYTES,
        )
        if not data or len(data) != completion["verdict_size"]:
            raise ValueError("missing, empty or size-mismatched verdict")
        verdict = engine.Engine._parse_verdict(
            data, str(state["candidate"]["candidate_head"]), str(request["package_digest"])
        )
    except (Refusal, KeyError, TypeError, ValueError) as exc:
        return _synthetic_block(self, state, request, f"invalid verdict: {exc}", changed_paths)
    return self._record_review_verdict(state, verdict, data, changed_paths)


def _collect_iteration_admitted(state: Mapping[str, Any]) -> None:
    iteration = _iteration(state)
    request = _request(state)
    eighth_pending = bool(
        state["state"] == "reviewing" and iteration == 8
        and isinstance(state.get("review"), Mapping)
        and set(state["review"]) == {"iteration", "request"}
        and request is not None and request.get("iteration") == 8
    )
    if state["state"] in {"reviewing", "revising"} and iteration >= 8 and not eighth_pending:
        raise chain_core._merge_refusal(
            V2ReasonCode.ITERATION_CAP,
            "forge: review collect refused — review iteration cap of 8 is final",
            expected="status or safe abort after the eighth review cycle",
            observed=str(iteration), chain=state,
        )


def review_collect(self: MergeEngine) -> Outcome:
    chain_core._require_merge_adapter_control("mandatory-review-final")
    state = self._load()
    self._halt(state)
    state = self._preflight_lifecycle(state, "review collect")
    _collect_iteration_admitted(state)
    if state["state"] != "reviewing":
        self._wrong_state(state, "reviewing", "review collect")
    request = _request(state)
    if request is None or request.get("lane") != _LANE:
        if request is not None and (
            request.get("lane") is not None
            or "provider" in request
            or "attempt" in request
        ):
            raise _shape_refusal(state, request.get("lane"))
        self._wrong_state(state, "a launched review-final request", "review collect")
    assert request is not None
    engine._read_merge_artifact(
        self.ctx, state, str(request["package"]), str(request["package_digest"]),
        "review master package",
    )
    engine._read_bound_artifact(
        self.ctx, state, str(request["prompt_path"]), str(request["prompt_digest"]),
        "review prompt",
    )
    stale = engine.mark_stale_attempts(
        self.ctx.store, str(state["chain_id"]), _attempt_relative(request)
    )
    observed = _observe(self, state, request)
    if observed.outcome in {"abandonable", "abandoned-claimed"}:
        with _attempt_descriptor(self, state, request) as (directory, _name):
            won, completion = engine.claim_abandoned(directory, request)
        if won:
            return engine.with_stale_evidence(
                self._review_retry_outcome(state, request, str(completion["error"])), stale
            )
        observed = _observe(self, state, request)
    if observed.outcome == "wrapper-lost":
        completion = _publish_lost(self, state, request, observed)
        if _terminal_error(completion.get("error")):
            return engine.with_stale_evidence(
                self._review_retry_outcome(state, request, str(completion["error"])), stale
            )
        observed = engine.AttemptObservation(
            "completed", identity=observed.identity, completion=completion
        )
    if observed.outcome != "completed":
        raise _collect_pending(state, request, observed, stale)
    _repository, _policy, changed = _observe_current_merge_candidate(
        self.ctx, state, verb="review collect"
    )
    try:
        outcome = _completed_review(self, state, request, observed, list(changed))
    except Refusal as exc:
        engine.with_stale_evidence(exc, stale)
        raise
    return engine.with_stale_evidence(outcome, stale)


def review_cancel(self: MergeEngine) -> Outcome:
    chain_core._require_merge_adapter_control("mandatory-review-final")
    state = self._load()
    self._halt(state)
    request = _request(state)
    if request is not None and request.get("lane") not in {None, _LANE}:
        raise _shape_refusal(state, request.get("lane"))
    if request is None or request.get("lane") != _LANE or not request.get("attempt"):
        raise chain_core._merge_refusal(
            V2ReasonCode.STATE_PRECONDITION,
            "forge: review cancel refused — a new-lane attempt with a published "
            "identity is required",
            observed=str(request), remediation=f"forge status --chain-id {state['chain_id']}",
            chain=state,
        )
    self._review_cancel_admitted(state)
    with _attempt_descriptor(self, state, request) as (directory, _name):
        with engine.attempt_publication_lock(directory):
            identity, completion = self._read_cancel_records(state, directory, request)
            if identity is None:
                raise chain_core._merge_refusal(
                    V2ReasonCode.STATE_PRECONDITION,
                    "forge: review cancel refused — identity unpublished; attempt is launching",
                    observed="identity.json absent",
                    remediation=f"forge review collect --chain-id {state['chain_id']}", chain=state,
                )
            if completion is not None:
                raise chain_core._merge_refusal(
                    V2ReasonCode.STATE_PRECONDITION,
                    "forge: review cancel refused — attempt already has a completion record",
                    observed=str(completion.get("error")),
                    remediation=f"forge review collect --chain-id {state['chain_id']}", chain=state,
                )
            if identity.get("wrapper_pid") is None:
                _won, record = engine.claim_abandoned(directory, request)
                return self._review_retry_outcome(state, request, str(record["error"]))
            prior_identity = identity
            proof = engine.prove_group_ownership(identity)
            terminal_outcome, proof = self._cancel_group_outcome(state, identity, proof)
            identity, _raced_completion = self._read_cancel_records(state, directory, request)
            if identity is None:
                raise chain_core._merge_refusal(
                    V2ReasonCode.EVIDENCE_INCOMPLETE,
                    "forge: review cancel refused — identity disappeared before publication",
                    remediation=f"forge merge abort --chain-id {state['chain_id']} --reason lost",
                    chain=state,
                )
            if identity != prior_identity:
                if not _immutable_identity_matches(prior_identity, identity):
                    raise chain_core._merge_refusal(
                        V2ReasonCode.EVIDENCE_INCOMPLETE,
                        "forge: review cancel refused — immutable identity changed", chain=state,
                        remediation=f"forge merge abort --chain-id {state['chain_id']}")
                proof = engine.prove_group_ownership(identity)
                terminal_outcome, proof = self._cancel_group_outcome(state, identity, proof)
            published_outcome = self._publish_cancel_completion(
                state, directory, request, identity, terminal_outcome)
            if published_outcome is None:
                return engine._success(
                    state, "merge review attempt already completed",
                    f"forge review collect --chain-id {state['chain_id']}",
                    evidence_refs=[str(request["completion_path"])],
                )
    note = (
        f"; identity-unproven members={list(proof.members)}"
        if proof.outcome == "identity-unproven" else ""
    )
    return self._review_retry_outcome(state, request, published_outcome, note)
