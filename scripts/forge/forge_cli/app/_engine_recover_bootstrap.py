from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any, Mapping

from forge_cli import chain_core, engine
from forge_cli.envelope import REVISION9_OUTPUT_SCHEMA, FrozenError, V2ReasonCode

if TYPE_CHECKING:
    from forge_cli.app._merge_engine import MergeEngine

def _recover_merge_bootstrap_scope_binding(
    self: "MergeEngine",
    state: Mapping[str, Any],
    admission: engine.MergeAdmission,
    *,
    fence: chain_core.PublishedLockRecord | None = None,
) -> dict[str, Any] | None:
    """Resume a crashed run-bound sidecar without resolving a tip again.

        ``None`` is the exact both-names-absent pre-publication result.  When
        common-lock recovery already cleared the dead fence, its complete
        identity is recovered from the immutable sidecar's
        ``retained_inflight`` member.
        """

    chain_core._require_merge_integration_control("scope-sidecar-recovery")
    fetch_intent_digest = engine._merge_event_digest(
        self.store, str(state["chain_id"]), "fetch_intent"
    )
    if fetch_intent_digest is None:
        raise FrozenError(
            "merge bootstrap fetch intent digest is unavailable",
            chain_id=str(state["chain_id"]),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    intent = state.get("integration", {}).get("intent")
    scope_request = (
        intent.get("scope_request") if isinstance(intent, Mapping) else None
    )
    expected_request = engine._merge_scope_request(admission)
    if (
        (scope_request is not None and not isinstance(scope_request, Mapping))
        or (
            dict(scope_request)
            if isinstance(scope_request, Mapping)
            else None
        )
        != expected_request
    ):
        raise FrozenError(
            "merge bootstrap scope request diverges from admission",
            chain_id=str(state["chain_id"]),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    selected_fence = fence or engine._discover_merge_scope_fence_from_sidecar(
        self.store,
        state,
        fetch_intent_digest=fetch_intent_digest,
    )
    if selected_fence is None:
        return None
    return engine._resume_merge_scope_binding(
        self.store,
        state,
        fetch_intent_digest=fetch_intent_digest,
        scope_request=scope_request,
        fence=selected_fence,
    )

def _bootstrap_pending_classification_inputs_locked(
    self: "MergeEngine",
    state: Mapping[str, Any],
    admission: engine.MergeAdmission,
) -> engine.MergeBootstrapClassification:
    """Recover the authenticated inputs carried by a successful result."""

    if not chain_core._merge_bootstrap_classification_pending(state):
        raise FrozenError(
            "merge bootstrap classification snapshot is not pending",
            chain_id=str(state.get("chain_id", "")) or None,
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    candidate = state["candidate"]
    with self.store.event_lock(str(state["chain_id"])):
        replay = self.store._read_replay_locked(str(state["chain_id"]))
    selected: Mapping[str, Any] | None = None
    for event in reversed(replay.events):
        payload = event.get("payload")
        delta = payload.get("delta") if isinstance(payload, Mapping) else None
        integration = (
            delta.get("integration") if isinstance(delta, Mapping) else None
        )
        if (
            event.get("event") == "fetch_result"
            and event.get("generation_digest")
            == candidate.get("generation_digest")
            and isinstance(payload, Mapping)
            and integration == state.get("integration")
        ):
            selected = event
            break
    if selected is None:
        raise FrozenError(
            "merge bootstrap classification result evidence is unavailable",
            chain_id=str(state["chain_id"]),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    payload = selected["payload"]
    try:
        binding = chain_core._validate_merge_scope_fetch_binding(
            payload.get("scope_fetch_binding")
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise FrozenError(
            "merge bootstrap classification sidecar is malformed",
            chain_id=str(state["chain_id"]),
            observed=str(exc),
            schema=REVISION9_OUTPUT_SCHEMA,
        ) from exc
    if (
        binding.get("chain_id") != state.get("chain_id")
        or binding.get("candidate_head") != candidate.get("candidate_head")
        or binding.get("remote_tip") != candidate.get("remote_tip")
        or binding.get("full_patch_output_digest")
        != candidate.get("diff_sha256")
    ):
        raise FrozenError(
            "merge bootstrap classification sidecar changed its candidate",
            chain_id=str(state["chain_id"]),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    proof = payload.get("scope_proof")
    scope: engine.MergeScopeResult | None = None
    if admission.run_task is not None:
        scope_request = engine._merge_scope_request(admission)
        if not chain_core._validate_merge_scope_proof(
            proof,
            state=state,
            binding=binding,
            scope_request=scope_request,
        ):
            raise FrozenError(
                "merge bootstrap classification scope proof is malformed",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        assert isinstance(proof, Mapping)
        scope = engine.MergeScopeResult(
            argv=tuple(
                chain_core._merge_scope_argv(
                    admission.worktree,
                    str(candidate["remote_tip"]),
                    str(candidate["candidate_head"]),
                )
            ),
            command_digest=str(proof["command_digest"]),
            environment_digest=str(proof["environment_digest"]),
            output_digest=str(proof["output_digest"]),
            changed_paths=tuple(proof["changed_paths"]),
            out_of_scope_paths=tuple(proof["out_of_scope_paths"]),
            result=str(proof["result"]),
        )
    elif proof is not None:
        raise FrozenError(
            "unbound merge bootstrap carried a scope proof",
            chain_id=str(state["chain_id"]),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    return engine.MergeBootstrapClassification(
        candidate=copy.deepcopy(dict(candidate)),
        scope=scope,
        full_patch_output_digest=str(binding["full_patch_output_digest"]),
        scope_proof_digest=(
            str(proof["digest"]) if isinstance(proof, Mapping) else None
        ),
        fetch_result_event_digest=str(selected["digest"]),
        verb="merge recover",
    )

def _recover_classifying_bootstrap_v12_locked(
    self: "MergeEngine",
    state: dict[str, Any],
    lease: chain_core.ChainLease,
) -> tuple[
    dict[str, Any],
    str,
    engine.MergeAdmission | None,
    engine.MergeBootstrapClassification | None,
]:
    """Classify the Revision-12 pre-sidecar and surviving-sidecar windows."""

    chain_core._require_merge_integration_control("composite-bootstrap-streaming")
    intent = state.get("integration", {}).get("intent")
    if chain_core._merge_bootstrap_classification_pending(state):
        admission = self._admission_for_refresh(
            state, verb="merge recover"
        )
        pending = self._bootstrap_pending_classification_inputs_locked(
            state, admission
        )
        return state, "classification-pending", admission, pending
    if (
        state.get("state") == "classifying"
        and state.get("integration", {}).get("condition") == "fetch-failed"
        and state.get("candidate") is None
        and state.get("tier") is None
        and not isinstance(state.get("run_binding"), Mapping)
        and isinstance(intent, Mapping)
        and set(intent)
        == {
            "operation",
            "operation_nonce",
            "attempt",
            "result",
            "resolved_tip",
        }
        and intent.get("operation") == "fetch-result"
        and chain_core._valid_nonce(intent.get("operation_nonce"))
        and chain_core._valid_positive_int(intent.get("attempt"))
        and intent.get("result") == "failed"
        and intent.get("resolved_tip") is None
    ):
        raise chain_core._merge_refusal(
            V2ReasonCode.FETCH_FAILED,
            "forge: merge recover refused — fixed target fetch failed",
            expected="merge refresh to begin one fresh bootstrap epoch",
            observed="the prior composite bootstrap did not PASS",
            remediation=(
                f"forge merge refresh --chain-id {state['chain_id']}"
            ),
            chain=state,
        )
    if (
        not isinstance(intent, Mapping)
        or intent.get("operation") != "fetch"
        or not chain_core._valid_nonce(intent.get("operation_nonce"))
        or not chain_core._valid_positive_int(intent.get("attempt"))
        or chain_core.COMMIT_RE.fullmatch(str(intent.get("pre_fetch_head", ""))) is None
    ):
        raise FrozenError(
            "interrupted merge bootstrap intent is malformed",
            chain_id=str(state["chain_id"]),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    operation_nonce = str(intent["operation_nonce"])
    attempt = int(intent["attempt"])
    run_bound = isinstance(state.get("run_binding"), Mapping)
    admission = self._admission_for_refresh(
        state, verb="merge recover"
    )
    binding = self._recover_merge_bootstrap_scope_binding(
        state, admission, fence=None
    )

    def record_failure(
        sidecar: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        integration = copy.deepcopy(state["integration"])
        integration.update(
            {
                "condition": "none" if run_bound else "fetch-failed",
                "primary_condition": "none",
                "intent": {
                    "operation": "fetch-result",
                    "operation_nonce": operation_nonce,
                    "attempt": attempt,
                    "result": "failed",
                    "resolved_tip": None,
                },
            }
        )
        return self._epoch_transition(
            state,
            lease,
            "fetch_result",
            {
                "delta": {"integration": integration},
                "scope_fetch_binding": (
                    copy.deepcopy(dict(sidecar))
                    if isinstance(sidecar, Mapping)
                    else None
                ),
                "scope_proof": None,
            },
            generation_digest=(
                str(state["candidate"]["generation_digest"])
                if isinstance(state.get("candidate"), Mapping)
                else None
            ),
        )

    if binding is None:
        failed = record_failure(None)
        if not run_bound:
            return failed, "fetch-failed", None, None
        terminal = self._release_to_aborted_locked(
            failed,
            lease,
            reason="run/task scope derivation is invalid",
        )
        raise chain_core._merge_refusal(
            V2ReasonCode.RUN_TASK_BINDING_INVALID,
            "forge: merge recover refused — run/task scope derivation is invalid",
            expected="a surviving authenticated composite-bootstrap sidecar",
            observed="scope-fetch sidecar absent",
            chain=terminal,
        )
    if run_bound:
        failed = record_failure(binding)
        terminal = self._release_to_aborted_locked(
            failed,
            lease,
            reason="run/task scope derivation is invalid",
        )
        raise chain_core._merge_refusal(
            V2ReasonCode.RUN_TASK_BINDING_INVALID,
            "forge: merge recover refused — run/task scope derivation is invalid",
            expected="ordinary abort after the surviving run-bound sidecar",
            observed=str(binding.get("digest")),
            chain=terminal,
        )

    fixed_tip = str(binding["remote_tip"])
    generation_number = (
        int(state["candidate"]["generation"]) + 1
        if isinstance(state.get("candidate"), Mapping)
        else 1
    )
    try:
        candidate = engine._retain_or_advance_merge_candidate(
            admission,
            fixed_tip,
            prior_candidate=state.get("candidate"),
            generation=generation_number,
            diff_output_digest=str(binding["full_patch_output_digest"]),
        )
    except (TypeError, ValueError) as exc:
        raise FrozenError(
            "surviving composite-bootstrap sidecar cannot materialize its generation",
            chain_id=str(state["chain_id"]),
            observed=str(exc),
            schema=REVISION9_OUTPUT_SCHEMA,
        ) from exc
    integration = copy.deepcopy(state["integration"])
    integration.update(
        {
            "condition": "none",
            "primary_condition": "none",
            "intent": {
                "operation": "fetch-result",
                "operation_nonce": operation_nonce,
                "attempt": attempt,
                "result": "success",
                "resolved_tip": fixed_tip,
            },
        }
    )
    desired = {
        "candidate": copy.deepcopy(candidate),
        "tier": None,
        "state": "classifying",
        "policy_source": {
            "commit": admission.policy.sha,
            "digest": admission.policy.digest,
        },
        "steps": {},
        "review": (
            {"iteration": state["review"]["iteration"]}
            if isinstance(state.get("review"), Mapping)
            and type(state["review"].get("iteration")) is int
            else {}
        ),
        "approval": {},
        "authorization": {},
        "integration": integration,
    }
    current = self._epoch_transition(
        state,
        lease,
        "fetch_result",
        {
            "delta": {
                name: value
                for name, value in desired.items()
                if state.get(name) != value or name == "state"
            },
            "scope_fetch_binding": copy.deepcopy(dict(binding)),
            "scope_proof": None,
        },
        generation_digest=str(candidate["generation_digest"]),
    )
    pending = self._bootstrap_pending_classification_inputs_locked(
        current, admission
    )
    return current, "classification-pending", admission, pending

def _recover_classifying_bootstrap_locked(
    self: "MergeEngine",
    state: dict[str, Any],
    lock: chain_core.CommonRebaseLock,
    lease: chain_core.ChainLease,
) -> tuple[
    dict[str, Any],
    str,
    engine.MergeAdmission | None,
    engine.MergeBootstrapClassification | None,
]:
    """Finish one interrupted bootstrap from its durable raw child result."""

    del lock
    return self._recover_classifying_bootstrap_v12_locked(state, lease)
