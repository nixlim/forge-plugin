from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping, Sequence

from forge_cli import chain_core, engine
from forge_cli.engine import _review_lane_api
from forge_cli.envelope import Outcome, V2ReasonCode
from forge_cli.policy import Policy

if TYPE_CHECKING:
    from forge_cli.app._merge_engine import MergeEngine

def _legacy_attach_request(
    self: MergeEngine, state: dict[str, Any]
) -> tuple[Mapping[str, Any] | None, Mapping[str, Any] | None]:
    review = state.get("review")
    request = review.get("request") if isinstance(review, Mapping) else None
    if isinstance(request, dict) and request.get("lane") not in {
        None,
        "forge-review-lane/1",
    }:
        raise chain_core._merge_refusal(
            V2ReasonCode.STATE_PRECONDITION,
            engine.NEWER_SHAPE_LITERAL,
            expected="forge-review-lane/1 or a legacy request",
            observed=str(request.get("lane")),
            remediation=(
                f"forge merge abort --chain-id {state['chain_id']} "
                "--reason newer-review-shape"
            ),
            chain=state,
        )
    if isinstance(request, dict) and any(
        name in request for name in ("lane", "provider", "pid", "attempt")
    ):
        raise chain_core._merge_refusal(
            V2ReasonCode.STATE_PRECONDITION,
            "forge: review attach refused — launched requests complete through review collect",
            expected="a legacy review-final invocation with no pid, provider, or attempt",
            observed=str(request.get("lane") or request.get("provider") or request.get("pid")),
            remediation=f"forge review collect --chain-id {state['chain_id']}", chain=state,
        )
    return (
        review if isinstance(review, Mapping) else None,
        request if isinstance(request, Mapping) else None,
    )


def _review_retry_outcome(
    self: MergeEngine,
    state: dict[str, Any],
    request: Mapping[str, Any],
    outcome: str,
    note: str = "",
) -> Outcome:
    review = state.get("review")
    iteration = review.get("iteration", 0) if isinstance(review, Mapping) else 0
    if outcome == "not-logged-in":
        literal = (
            engine.CODEX_NOT_LOGGED_IN
            if request.get("provider") == "codex"
            else engine.CLAUDE_NOT_LOGGED_IN
        )
        remediation = (
            f"forge merge abort --chain-id {state['chain_id']} --reason iteration-cap"
            if type(iteration) is int and iteration >= 8
            else literal.rsplit("; ", 1)[-1]
        )
        raise chain_core._merge_refusal(
            V2ReasonCode.EVIDENCE_INCOMPLETE, literal, observed=outcome,
            remediation=remediation, chain=state,
            evidence_refs=[str(request["completion_path"])],
        )
    inactive = engine._merge_inactive(state)
    if state["state"] != "reviewing" or inactive:
        next_step = f"forge status --chain-id {state['chain_id']}"
    elif type(iteration) is int and iteration < 8:
        next_step = f"forge review request --chain-id {state['chain_id']}"
    else:
        next_step = f"forge merge abort --chain-id {state['chain_id']} --reason iteration-cap"
    return engine._success(
        state, f"merge review attempt {outcome}; iteration spent{note}", next_step,
        evidence_refs=[str(request["completion_path"])],
    )


def _publish_cancel_completion(
    self: MergeEngine,
    state: dict[str, Any],
    directory: int,
    request: Mapping[str, Any],
    identity: Mapping[str, Any],
    outcome: str,
) -> str | None:
    record = engine.make_terminal_completion(request, outcome, identity=identity)
    if engine.publish_terminal_completion(directory, record):
        return outcome
    existing = engine.read_completion(directory, str(request["attempt"]))
    if existing is None:
        raise chain_core._merge_refusal(
            V2ReasonCode.EVIDENCE_INCOMPLETE,
            "review completion raced review cancel but is unreadable",
            remediation=f"forge review cancel --chain-id {state['chain_id']}", chain=state,
        )
    observed = engine.AttemptObservation(
        "completed", identity=dict(identity), completion=existing
    )
    existing = self._validated_review_completion(state, request, observed)
    error = existing.get("error")
    terminal = error in {"cancelled", "abandoned", "wrapper-lost", "not-logged-in"}
    if terminal or isinstance(error, str) and error.startswith("launch-failed: "):
        return str(error)
    return None


def _publish_launch_failure(
    self: MergeEngine,
    state: dict[str, Any],
    directory: int,
    request: Mapping[str, Any],
    failure: str,
) -> None:
    record = engine.make_terminal_completion(request, failure)
    if engine.publish_terminal_completion(directory, record):
        return
    existing = engine.read_completion(directory, str(request["attempt"]))
    if existing is None:
        raise chain_core._merge_refusal(
            V2ReasonCode.EVIDENCE_INCOMPLETE,
            "review launch-failed completion raced but is unreadable",
            remediation=f"forge review collect --chain-id {state['chain_id']}",
            chain=state,
        )
    observed = engine.AttemptObservation("completed", completion=existing)
    existing = self._validated_review_completion(state, request, observed)
    if existing.get("error") != failure:
        raise chain_core._merge_refusal(
            V2ReasonCode.EVIDENCE_INCOMPLETE,
            "review launch-failed completion raced another terminal outcome",
            observed=str(existing.get("error")),
            remediation=f"forge review collect --chain-id {state['chain_id']}",
            chain=state,
        )


def _review_cancel_admitted(self: MergeEngine, state: Mapping[str, Any]) -> None:
    state_name = state.get("state")
    review = state.get("review")
    iteration = review.get("iteration", 0) if isinstance(review, Mapping) else 0
    if (
        state_name == "reviewing"
        or state_name in engine.TERMINAL_STATES
        or type(iteration) is int and iteration >= 8
        or engine._merge_inactive(state)
    ):
        return
    self._wrong_state(
        state,
        "reviewing, inactive, iteration-capped, or terminal review attempt",
        "review cancel",
    )


def _read_cancel_records(
    state: Mapping[str, Any], directory: int, request: Mapping[str, Any]
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    try:
        identity = engine.read_identity(directory, str(request["attempt"]))
        completion = engine.read_completion(directory, str(request["attempt"]))
    except engine.AttemptShapeNewer as exc:
        raise chain_core._merge_refusal(
            V2ReasonCode.STATE_PRECONDITION,
            engine.NEWER_SHAPE_LITERAL,
            expected="forge-review-identity/1 and forge-review-process/2",
            observed=str(exc),
            remediation=(
                f"forge merge abort --chain-id {state['chain_id']} "
                "--reason newer-review-shape"
            ),
            chain=state,
        ) from exc
    except engine.AttemptRecordError as exc:
        raise chain_core._merge_refusal(
            V2ReasonCode.EVIDENCE_INCOMPLETE,
            "forge: review cancel refused — review attempt record is invalid",
            expected="a canonical identity and completion record",
            observed=str(exc),
            remediation=(
                f"forge merge abort --chain-id {state['chain_id']} "
                "--reason invalid-review-record"
            ),
            chain=state,
        ) from exc
    return identity, completion


def _refuse_wrapper_identity_unproven(
    self: MergeEngine, state: Mapping[str, Any], proof: engine.GroupProof
) -> None:
    if proof.outcome not in _review_lane_api.NO_SIGNAL_OUTCOMES:
        return
    raise chain_core._merge_refusal(
        V2ReasonCode.STATE_PRECONDITION,
        engine.cancel_identity_unproven_message(proof),
        observed=f"{proof.outcome}; members={list(proof.members)}; pgid={proof.pgid}",
        remediation=f"forge review cancel --chain-id {state['chain_id']}", chain=state,
    )


def _cancel_group_outcome(
    self: MergeEngine,
    state: dict[str, Any],
    identity: Mapping[str, Any],
    proof: engine.GroupProof,
) -> tuple[str, engine.GroupProof]:
    self._refuse_wrapper_identity_unproven(state, proof)
    result = proof
    if proof.outcome in {"wrapper-alive", "reviewer-alive"}:
        result = engine.terminate_owned_group(
            identity, engine.TERMINATE_GRACE_SECONDS
        )
        self._refuse_wrapper_identity_unproven(state, result)
    if result.outcome == "kill-unconfirmed":
        raise chain_core._merge_refusal(
            V2ReasonCode.STATE_PRECONDITION,
            _review_lane_api.cancel_kill_unconfirmed_message(result.members),
            observed=str(list(result.members)),
            remediation=f"forge review cancel --chain-id {state['chain_id']}",
            chain=state,
        )
    if result.outcome in _review_lane_api.LOST_OUTCOMES:
        return "wrapper-lost", result
    if result.outcome == "cancelled":
        return "cancelled", result
    raise chain_core._merge_refusal(
        V2ReasonCode.STATE_PRECONDITION,
        f"forge: review cancel refused — unexpected group proof {result.outcome}",
        observed=str(list(result.members)),
        remediation=f"forge review cancel --chain-id {state['chain_id']}",
        chain=state,
    )


def _validated_review_completion(
    self: MergeEngine,
    state: Mapping[str, Any],
    request: Mapping[str, Any],
    observed: engine.AttemptObservation,
) -> dict[str, Any]:
    completion = observed.completion or {}
    try:
        engine.validate_completion_binding(completion, request, observed.identity)
    except engine.AttemptRecordError as exc:
        raise chain_core._merge_refusal(
            V2ReasonCode.EVIDENCE_INCOMPLETE,
            "review completion record does not bind to the current attempt",
            expected="matching route, attempt, digests, and recorded process identities",
            observed=str(exc),
            remediation=(
                f"forge merge abort --chain-id {state['chain_id']} "
                "--reason invalid-review-completion"
            ),
            chain=state, evidence_refs=[str(request["completion_path"])],
        ) from exc
    return completion

def _review_package(
    self: MergeEngine,
    state: Mapping[str, Any],
    repository: chain_core.Repository,
    policy: Policy,
    changed_paths: Sequence[str],
) -> tuple[bytes, list[str], dict[str, list[str]]]:
    chain_core._require_merge_adapter_control("mandatory-review-final")
    profiles_by_path = {
        path: engine.Engine._profiles_for_path(path) for path in changed_paths
    }
    profiles = sorted(
        {
            profile
            for selected in profiles_by_path.values()
            for profile in selected
        }
    )
    constitution_path = self.ctx.plugin_root() / "rules" / "review-constitution.md"
    role_path = self.ctx.plugin_root() / "agents" / "review-final.md"
    try:
        constitution = constitution_path.read_bytes()
        role = role_path.read_bytes()
    except OSError as exc:
        raise chain_core._merge_refusal(
            V2ReasonCode.EVIDENCE_INCOMPLETE,
            f"forge: review refused — reviewer doctrine is unavailable: {exc}",
            observed=str(exc),
            chain=state,
        ) from exc
    candidate = state["candidate"]
    header = (
        "FORGE MERGE REVIEW MASTER PACKAGE v1\n"
        f"candidate: {candidate['candidate_head']}\n"
        f"generation: {candidate['generation_digest']}\n"
        f"base: {candidate['remote_tip']}\n"
        f"target: {chain_core.canonical_bytes(state['target']).decode('utf-8')}\n"
        "reviewer: review-final\n"
        f"profiles: {','.join(profiles)}\n"
        f"profile-map: {chain_core.canonical_bytes(profiles_by_path).decode('utf-8')}\n"
    ).encode("utf-8")
    control = (
        b"\n--- BEGIN CONTROLLING REVIEW POLICY ---\n"
        + role
        + b"\n--- review constitution ---\n"
        + constitution
        + (
            "\n--- committed agent-project-context ---\n"
            f"{policy.regions['agent-project-context']}"
            "\n--- committed review-prompt-project-focus ---\n"
            f"{policy.regions['review-prompt-project-focus']}"
            "\n--- committed project-triggers ---\n"
            f"{policy.regions['project-triggers']}"
            "\n--- committed completeness-project-items ---\n"
            f"{policy.regions['completeness-project-items']}"
        ).encode("utf-8")
        + b"\n--- END CONTROLLING REVIEW POLICY ---\n"
    )
    mutation_evidence = [
        fact.get("scoped_mutation")
        for facts in state.get("steps", {}).values()
        if isinstance(facts, list)
        for fact in facts
        if isinstance(fact, dict) and isinstance(fact.get("scoped_mutation"), dict)
    ]
    try:
        diff = repository.git(
            [
                "diff",
                f"{candidate['remote_tip']}...{candidate['candidate_head']}",
            ]
        ).stdout
    except OSError as exc:
        raise chain_core._merge_refusal(
            V2ReasonCode.EVIDENCE_INCOMPLETE,
            "forge: review request refused — authoritative candidate diff is unavailable",
            expected="the complete fixed-generation three-dot diff",
            observed=str(exc),
            chain=state,
        ) from exc
    package = (
        header
        + control
        + b"\n--- BEGIN ADVISORY MUTATION EVIDENCE ---\n"
        + chain_core.canonical_bytes(mutation_evidence)
        + b"\n--- END ADVISORY MUTATION EVIDENCE ---\n"
        + b"\n--- BEGIN UNTRUSTED CANDIDATE DIFF ---\n"
        + diff
        + b"\n--- END UNTRUSTED CANDIDATE DIFF ---\n"
    )
    return package, profiles, profiles_by_path
