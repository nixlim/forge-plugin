from __future__ import annotations

import copy
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

from forge_cli import chain_core, engine
from forge_cli.app._admission import prepare_merge_admission
from forge_cli.envelope import REVISION9_OUTPUT_SCHEMA, FrozenError, Outcome, V2ReasonCode

if TYPE_CHECKING:
    from forge_cli.app._merge_engine import MergeEngine

def start(
    self: MergeEngine,
    worktree: str,
    declared_tier: str | None = None,
    *,
    task: str | None = None,
) -> engine.MergeAdmission:
    """Expose dormant read-only admission without creating a chain."""

    return prepare_merge_admission(
        self.ctx,
        worktree,
        declared_tier,
        task=task,
    )

def bind_candidate(
    self: MergeEngine,
    admission: engine.MergeAdmission,
    remote_tip: str,
    *,
    generation: int = 1,
) -> engine.MergeCandidateGeneration:
    return engine.bind_merge_candidate_generation(
        self.ctx,
        admission,
        remote_tip,
        generation=generation,
    )

def _preflight_lifecycle(
    self: MergeEngine,
    state: dict[str, Any],
    verb: str,
    *,
    persist_missing: bool = True,
) -> dict[str, Any]:
    """Apply FR-232 priority rows before an ordinary scalar-state row."""

    engine._require_merge_lifecycle_control("admission-priority")
    claim = state.get("worktree", {}).get("claim")
    claim_status = claim.get("status") if isinstance(claim, Mapping) else None
    if claim_status == "unpublished":
        next_step = (
            f"forge merge abort --chain-id {state['chain_id']}"
            if engine._merge_unpublished_claim_absent(state, self.store)
            else f"forge merge recover --chain-id {state['chain_id']}"
        )
        raise chain_core._merge_refusal(
            V2ReasonCode.STATE_PRECONDITION,
            f"forge: {verb} refused — ownership publication requires recovery",
            expected="owned or terminal merge ownership",
            observed="unpublished",
            remediation=next_step,
            chain=state,
        )
    if claim_status in {"releasing", "released"} and state["state"] not in {
        "closed",
        "aborted",
    }:
        raise chain_core._merge_refusal(
            V2ReasonCode.STATE_PRECONDITION,
            f"forge: {verb} refused — ownership release completion is pending",
            expected="the cutoff-selected terminal event",
            observed=str(claim_status),
            remediation=f"forge merge recover --chain-id {state['chain_id']}",
            chain=state,
        )
    containment, _vector = chain_core._merge_containment(state)
    if containment == "current" and state["state"] != "pushed":
        raise chain_core._merge_refusal(
            V2ReasonCode.STATE_PRECONDITION,
            f"forge: {verb} refused — current intended HEAD containment requires recovery",
            expected="durable current-generation pushed truth",
            observed="current intended HEAD is contained",
            remediation=f"forge merge recover --chain-id {state['chain_id']}",
            chain=state,
        )
    if containment == "older":
        raise chain_core._merge_refusal(
            V2ReasonCode.STATE_PRECONDITION,
            f"forge: {verb} refused — older attempted HEAD containment requires recovery",
            expected="historical landing reconciliation before another transition",
            observed="only an older attempted HEAD is contained",
            remediation=f"forge merge recover --chain-id {state['chain_id']}",
            chain=state,
        )
    if engine._merge_inactive(state):
        raise chain_core._merge_refusal(
            V2ReasonCode.STATE_PRECONDITION,
            f"forge: {verb} refused — merge chain is inactive",
            expected="an active merge transition tuple",
            observed=str(state["inactive_after"]),
            remediation=f"forge status --chain-id {state['chain_id']}",
            chain=state,
        )
    worktree = Path(str(state.get("worktree", {}).get("path", "")))
    if not worktree.exists():
        current = state
        integration = state.get("integration")
        if (
            persist_missing
            and isinstance(integration, dict)
            and integration.get("condition") != "foreign-git-state"
        ):
            updated = copy.deepcopy(integration)
            updated["condition"] = "foreign-git-state"
            updated["primary_condition"] = "none"
            engine._reset_merge_nonmovement_counter(updated)
            generation = state.get("candidate")
            current = self.store.transition(
                state,
                "condition_recorded",
                {"delta": {"integration": updated}},
                generation_digest=(
                    str(generation["generation_digest"])
                    if isinstance(generation, Mapping)
                    else None
                ),
                at=chain_core.iso_z(),
            )
        raise chain_core._merge_refusal(
            V2ReasonCode.STATE_PRECONDITION,
            f"forge: {verb} refused — recorded worktree is missing",
            expected=str(worktree),
            observed="foreign-git-state",
            remediation=f"forge status --chain-id {state['chain_id']}",
            chain=current,
        )
    return state

def approve(self: MergeEngine, candidate: str) -> Outcome:
    engine._require_merge_lifecycle_control("candidate-bound-approval")
    state = self._preflight_lifecycle(self._load(), "merge approve")
    self._halt(state)
    review = state.get("review")
    pending = bool(
        state["state"] in {"reviewing", "revising"}
        and isinstance(review, Mapping)
        and review.get("operator_cosign_required") is True
    )
    iteration = review.get("iteration", 0) if isinstance(review, Mapping) else 0
    if type(iteration) is not int:
        raise FrozenError(
            "merge review iteration is malformed",
            chain_id=str(state["chain_id"]),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    if pending and iteration >= 8:
        raise chain_core._merge_refusal(
            V2ReasonCode.ITERATION_CAP,
            "forge: merge approve refused — review iteration cap of 8 is final",
            expected="status or safe abort after the eighth review cycle",
            observed=str(iteration),
            chain=state,
        )
    if not pending and state["state"] != "awaiting_approval":
        self._wrong_state(
            state,
            "a sole pending disposition or awaiting_approval",
            "merge approve",
        )
    generation = state.get("candidate")
    if not isinstance(generation, Mapping):
        raise FrozenError(
            "merge approval generation is unavailable",
            chain_id=str(state["chain_id"]),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    expected = str(generation.get("candidate_head", ""))
    if chain_core.COMMIT_RE.fullmatch(candidate) is None or candidate != expected:
        raise chain_core._merge_refusal(
            V2ReasonCode.CANDIDATE_STALE,
            "forge: merge approve refused — candidate HEAD does not match the current generation",
            expected=expected,
            observed=candidate,
            remediation=f"forge merge approve --candidate {expected} --chain-id {state['chain_id']}",
            chain=state,
        )
    now = chain_core.iso_z()
    if pending:
        dispositions = review.get("dispositions")
        approval = state.get("approval")
        unresolved = []
        if isinstance(dispositions, list):
            for disposition in dispositions:
                if not isinstance(disposition, Mapping) or disposition.get(
                    "severity"
                ) not in {"CRITICAL", "MAJOR"}:
                    continue
                separately_cosigned = bool(
                    isinstance(approval, Mapping)
                    and approval.get("purpose") == "finding-disposition"
                    and approval.get("finding") == disposition.get("finding")
                    and approval.get("resolution") == disposition.get("resolution")
                )
                if not separately_cosigned:
                    unresolved.append(disposition)
        if len(unresolved) != 1:
            raise FrozenError(
                "merge disposition co-sign projection is ambiguous",
                chain_id=str(state["chain_id"]),
                observed=str(len(unresolved)),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        selected = unresolved[0]
        current_review = copy.deepcopy(dict(review))
        current_review["operator_cosign_required"] = False
        approval_record = {
            "purpose": "finding-disposition",
            "chain_id": state["chain_id"],
            "finding": selected["finding"],
            "severity": selected["severity"],
            "resolution": selected["resolution"],
            "candidate": expected,
            "generation_digest": state["candidate"]["generation_digest"],
            "recorded_at": now,
            "directed_by": "operator",
        }
        delta = {"review": current_review, "approval": approval_record}
        message = f"merge finding {selected['finding']} operator co-sign recorded"
    elif state["state"] == "awaiting_approval":
        integration = state.get("integration")
        if not isinstance(integration, dict):
            raise FrozenError(
                "merge integration projection is malformed",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        if integration.get("condition") == "remote-churn":
            purpose = "remote-churn"
            updated_integration = copy.deepcopy(integration)
            updated_integration.update(
                {
                    "condition": "none",
                    "primary_condition": "none",
                    "remote_movement_count": 0,
                }
            )
            delta = {"state": "authorized", "integration": updated_integration}
            message = "merge remote-churn acknowledgement recorded"
        else:
            purpose = "gate-4"
            delta = {"state": "authorized"}
            message = "merge Gate-4 operator approval recorded"
        approval_record = {
            "purpose": purpose,
            "chain_id": state["chain_id"],
            "candidate": expected,
            "generation_digest": state["candidate"]["generation_digest"],
            "recorded_at": now,
            "directed_by": "operator",
        }
        delta["approval"] = approval_record
    state = self.store.transition(
        state,
        "approval_recorded",
        {"delta": delta},
        generation_digest=str(state["candidate"]["generation_digest"]),
        at=now,
    )
    return engine._success(
        state,
        message,
        f"forge status --chain-id {state['chain_id']}",
    )

def status(self: MergeEngine) -> Outcome:
    state = self._load()
    claim = state.get("worktree", {}).get("claim")
    if isinstance(claim, Mapping) and claim.get("status") == "unpublished":
        next_step = (
            f"forge merge abort --chain-id {state['chain_id']}"
            if engine._merge_unpublished_claim_absent(state, self.store)
            else f"forge merge recover --chain-id {state['chain_id']}"
        )
    elif isinstance(claim, Mapping) and claim.get("status") in {
        "releasing",
        "released",
    } and state["state"] not in {"closed", "aborted"}:
        next_step = f"forge merge recover --chain-id {state['chain_id']}"
    else:
        candidate = state.get("candidate")
        candidate_head = (
            candidate.get("candidate_head")
            if isinstance(candidate, Mapping)
            else "<unavailable>"
        )
        next_steps = {
            "classifying": f"forge merge refresh --chain-id {state['chain_id']}",
            "verifying": f"forge merge verify --chain-id {state['chain_id']}",
            "reviewing": f"forge review request --chain-id {state['chain_id']}",
            "revising": f"forge merge refresh --chain-id {state['chain_id']}",
            "awaiting_approval": (
                "forge merge approve --candidate "
                f"{candidate_head} "
                f"--chain-id {state['chain_id']}"
            ),
            "authorized": f"forge merge finalize --chain-id {state['chain_id']}",
            "rebasing": f"forge merge recover --chain-id {state['chain_id']}",
            "rebase_conflict": f"forge merge recover --chain-id {state['chain_id']}",
            "reverifying": f"forge merge verify --chain-id {state['chain_id']}",
            "reverification_failed": f"forge merge recover --chain-id {state['chain_id']}",
            "pushing": f"forge merge recover --chain-id {state['chain_id']}",
            "pushed": f"forge merge cleanup --chain-id {state['chain_id']}",
            "cleanup_pending": f"forge merge cleanup --chain-id {state['chain_id']}",
            "closed": "none — merge chain closed",
            "aborted": "none — merge chain aborted",
        }
        next_step = next_steps[str(state["state"])]
    return engine._success(
        state,
        f"merge chain {state['chain_id']} is {state['state']}",
        next_step,
    )
