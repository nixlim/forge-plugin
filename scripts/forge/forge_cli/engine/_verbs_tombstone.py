from __future__ import annotations

from typing import Mapping

from forge_cli import chain_core
from forge_cli.engine._approval import _success as _success
from forge_cli.engine._core import _run_halt as _run_halt
from forge_cli.engine._core import _transition_state as _transition_state
from forge_cli.engine._state import TERMINAL_STATES as TERMINAL_STATES
from forge_cli.envelope import REVISION9_OUTPUT_SCHEMA, FrozenError, Outcome, Refusal, V2ReasonCode

TOMBSTONE_CONTROLS = frozenset({"tombstone"})


def _require_tombstone_control() -> None:
    if "tombstone" not in TOMBSTONE_CONTROLS:
        raise FrozenError(
            "chain tombstone control is unavailable",
            schema=REVISION9_OUTPUT_SCHEMA,
        )

def _tombstone_outcome(
    self, chain_id: str, *, created: bool
) -> Outcome:
    return Outcome(
        ok=True,
        reason_code=V2ReasonCode.OK,
        message=(
            f"frozen chain {chain_id} aborted with operator tombstone"
            if created
            else f"frozen chain {chain_id} is operator-tombstoned"
        ),
        chain_id=chain_id,
        state="aborted",
        next_required_step="none — frozen chain is sealed",
        schema=REVISION9_OUTPUT_SCHEMA,
    )

def operator_tombstone(self, reason: str) -> Outcome:
    self._require_tombstone_control()
    chain_id = self.ctx.options.chain_id
    if chain_id is None:
        raise Refusal(
            V2ReasonCode.STATE_PRECONDITION,
            "forge: chain tombstone refused — explicit --chain-id is required",
            remediation="rerun with --chain-id <chain-id>",
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    existing = self.ctx.store.tombstone(
        chain_id, recover_publication=True
    )
    if existing is not None:
        return self._tombstone_outcome(chain_id, created=False)
    frozen = False
    try:
        family = self.ctx.store.chain_family(chain_id)
        if family != "commit":
            raise Refusal(
                V2ReasonCode.STATE_PRECONDITION,
                "forge: chain tombstone refused — chain is not commit-family",
                observed=family,
                remediation=f"forge status --chain-id {chain_id}",
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        self.ctx.store.load(chain_id)
    except FrozenError:
        frozen = self.ctx.store.raw_state_proves_commit_family(chain_id)
        if not frozen:
            # The migration surface may seal a fully quarantined identity,
            # but captured bytes never inherit a guessed family.
            self.ctx.store.create_tombstone(
                chain_id, reason, frozen_proven=False
            )
            return self._tombstone_outcome(chain_id, created=True)
    if not frozen:
        raise Refusal(
            V2ReasonCode.STATE_PRECONDITION,
            "forge: chain tombstone refused — readable chain is not frozen",
            observed=chain_id,
            remediation=f"forge commit abort --chain-id {chain_id}",
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    self.ctx.store.create_tombstone(
        chain_id, reason, frozen_proven=True
    )
    return self._tombstone_outcome(chain_id, created=True)

def abort(self, reason: str | None) -> Outcome:
    chain_id = self.ctx.options.chain_id
    family_proven = False
    if chain_id is not None:
        try:
            family = self.ctx.store.chain_family(chain_id)
        except FrozenError as failure:
            self._require_tombstone_control()
            if not self.ctx.store.raw_state_proves_commit_family(chain_id):
                raise Refusal(
                    V2ReasonCode.STATE_PRECONDITION,
                    "forge: commit abort refused — commit-family identity is not authenticated",
                    expected=(
                        "an authenticated commit event family or canonical raw state "
                        "with the selected chain_id and kind=commit"
                    ),
                    observed=chain_id,
                    remediation=(
                        f"forge chain tombstone --chain-id {chain_id} "
                        "--reason <operator-reason>"
                    ),
                    schema=REVISION9_OUTPUT_SCHEMA,
                ) from failure
            self.ctx.store.create_tombstone(
                chain_id,
                reason or "operator aborted frozen chain",
                frozen_proven=True,
            )
            return self._tombstone_outcome(chain_id, created=True)
        if family != "commit":
            raise FrozenError(
                "commit selection refused a merge-family chain",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        family_proven = True
    try:
        state = self.select(family_proven=family_proven)
    except FrozenError:
        self._require_tombstone_control()
        if chain_id is None:
            raise
        self.ctx.store.create_tombstone(
            chain_id,
            reason or "operator aborted frozen chain",
            frozen_proven=True,
        )
        return self._tombstone_outcome(chain_id, created=True)
    if state["state"] == "committing":
        _run_halt(self.ctx, state)
        identity = state.get("commit_result", {}).get("identity")
        authorization = state.get("authorization", {})
        if not (
            state.get("commit_result", {}).get("mismatch_latched") is True
            and isinstance(identity, Mapping)
            and identity.get("result") == "failed"
            and isinstance(identity.get("produced_sha"), str)
            and authorization.get("consumed") is False
            and authorization.get("consumed_at") is None
        ):
            self._preflight(
                state,
                "commit abort",
                mutating=False,
                allow_head_moved=True,
                check_candidate=False,
            )
    else:
        self._preflight(
            state,
            "commit abort",
            allow_head_moved=True,
            check_candidate=False,
        )
    if state["state"] in TERMINAL_STATES:
        # Revision 13: abort is a transition, never a retry or a landing
        # rewrite. A terminal chain refuses before any state or event
        # mutation so its landing (or earlier abort) stays intact.
        self._wrong_state(state, "a nonterminal chain", "commit abort")
    _transition_state(state, "aborted")
    if state.get("commit_result", {}).get("mismatch_latched") is True:
        state["commit_result"]["aborted_at"] = chain_core.iso_z()
        state["commit_result"]["reason"] = reason or ""
        state["authorization"] = {}
    else:
        state["commit_result"] = {
            "aborted_at": chain_core.iso_z(),
            "reason": reason or "",
        }
    self.ctx.store.persist(state, "chain_aborted", {"reason": reason or ""})
    return _success(
        state,
        f"chain {state['chain_id']} aborted",
        "forge commit start --paths <path>...",
    )
