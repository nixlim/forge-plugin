from __future__ import annotations

from forge_cli import chain_core, runtime
from forge_cli.engine._approval import _success as _success
from forge_cli.engine._candidate_ops import (
    _adopt_out_of_band_candidate as _adopt_out_of_band_candidate,
)
from forge_cli.engine._core import _run_halt as _run_halt
from forge_cli.engine._finalize import FINALIZE_CHECKS as FINALIZE_CHECKS
from forge_cli.engine._finalize import FinalizeContext as FinalizeContext
from forge_cli.engine._state import TERMINAL_STATES as TERMINAL_STATES
from forge_cli.envelope import (
    FrozenError,
    Outcome,
    ReasonCode,
    Refusal,
)


def status(self) -> Outcome:
    selected_id = self.ctx.options.chain_id
    if selected_id is not None:
        if self.ctx.store.tombstone(selected_id) is not None:
            self._require_tombstone_control()
            return self._tombstone_outcome(selected_id, created=False)
    try:
        state = self.select()
    except Refusal as exc:
        if exc.reason_code is ReasonCode.STATE_PRECONDITION:
            return _success(None, "no commit chain exists for this worktree", "forge commit start --paths <path>...")
        raise
    if (
        state["state"] not in TERMINAL_STATES | {"committing"}
        and state.get("candidate", {}).get("sha256")
        and not chain_core.candidate_is_v2(state)
    ):
        return _success(
            state,
            "legacy candidate is readable but must be restaged before advancement",
            chain_core._forge_command(state, "commit restage --paths <path>..."),
        )
    if state["state"] == "committing":
        policy = chain_core._policy_for_state(self.ctx, state)
        finalize_ctx = FinalizeContext(
            engine=self, state=state, policy=policy, message=""
        )
        halt_result = FINALIZE_CHECKS["halt"](finalize_ctx)
        if halt_result is False:
            raise FrozenError(
                "finalize check halt returned an unstructured failure",
                chain_id=str(state["chain_id"]),
                state="committing",
            )
        try:
            lock_result = FINALIZE_CHECKS["lock"](finalize_ctx)
            if lock_result is False:
                raise FrozenError(
                    "finalize check lock returned an unstructured failure",
                    chain_id=str(state["chain_id"]),
                    state="committing",
                )
            state = self.ctx.store.load(str(state["chain_id"]))
            finalize_ctx.state = state
            if state["state"] == "committing":
                return self._recover_committing(
                    state, diagnose_only=False, release_lock=False
                )
            # A concurrent recovery completed while this caller waited.
            # Continue as an ordinary status read of the fresh snapshot.
        finally:
            if finalize_ctx.lock_acquired:
                release_problem = self._release_lock(
                    finalize_ctx.lock_session_pid
                )
                finalize_ctx.lock_acquired = False
                if release_problem and not (
                    state.get("commit_result", {}).get("mismatch_latched") is True
                    and state.get("commit_result", {})
                    .get("identity", {})
                    .get("result")
                    == "failed"
                ):
                    raise FrozenError(
                        f"commit recovery lock release failed: {release_problem}",
                        chain_id=str(state["chain_id"]),
                        state=str(state["state"]),
                    )
    if (
        state["state"] not in TERMINAL_STATES
        and runtime.utc_now() >= chain_core.parse_time(str(state["inactive_after"]))
    ):
        return _success(
            state,
            "chain is inactive after 24 hours without an event; only status or abort is admitted",
            chain_core._forge_command(state, "commit abort --reason inactive"),
        )
    current = self.ctx.repo.head()
    if current != state["repo_head"]:
        _run_halt(self.ctx, state)
        self._record_head_moved(state, current)
        return _success(
            state,
            (
                "out-of-band commit, not chain corruption: "
                f"{state['repo_head']} -> {current}"
            ),
            chain_core._forge_command(state, "commit rebase"),
        )
    if (
        state["state"] not in TERMINAL_STATES
        and state["candidate"].get("sha256")
    ):
        observed_candidate = self.ctx.repo.candidate_hash()
        expected_candidate = str(state["candidate"]["sha256"])
        if observed_candidate != expected_candidate:
            _run_halt(self.ctx, state)
            _old, has_candidate_bytes = _adopt_out_of_band_candidate(
                self.ctx,
                state,
                observed_candidate,
                detected_by="status",
            )
            raise Refusal(
                ReasonCode.CANDIDATE_STALE,
                "out-of-band index change invalidated candidate evidence and reran classification",
                expected=expected_candidate,
                observed=observed_candidate,
                remediation=chain_core._forge_command(
                    state,
                    "verify"
                    if has_candidate_bytes
                    else "commit restage --paths <path>...",
                ),
                chain=state,
            )
    if state["state"] == "closed":
        next_step = "none — chain closed"
    elif state["state"] == "aborted":
        next_step = "forge commit start --paths <path>..."
    else:
        next_step = self.next_step(state)
    message = f"chain {state['chain_id']} is {state['state']}"
    return _success(state, message, next_step)
