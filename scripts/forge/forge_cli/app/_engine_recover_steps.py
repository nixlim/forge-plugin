from __future__ import annotations

from forge_cli import chain_core
from forge_cli.envelope import V2ReasonCode


def _recover_next_steps(current, action):
    if current["state"] == "pushing":
        condition = current["integration"]["condition"]
        reason = (
            V2ReasonCode.PUSH_FAILED
            if condition == "push-failed"
            else V2ReasonCode.PUSH_OUTCOME_UNKNOWN
            if condition == "push-outcome-unknown"
            else V2ReasonCode.NON_FAST_FORWARD
            if condition == "non-fast-forward"
            else None
        )
        if reason is not None:
            raise chain_core._merge_refusal(
                reason,
                f"forge: merge recover observed {condition}",
                remediation=f"forge merge recover --chain-id {current['chain_id']}",
                chain=current,
            )
    next_steps = {
        "pushed": f"forge merge cleanup --chain-id {current['chain_id']}",
        "pushing": f"forge merge recover --chain-id {current['chain_id']}",
        "reviewing": f"forge review request --chain-id {current['chain_id']}",
        "authorized": f"forge merge finalize --chain-id {current['chain_id']}",
        "revising": f"forge merge refresh --chain-id {current['chain_id']}",
        "rebase_conflict": (
            f"forge merge recover --continue --paths <path>... --chain-id {current['chain_id']}"
        ),
        "closed": "none — merge chain closed",
        "aborted": "none — merge chain aborted",
    }
    if action == "historical-landed-superseded":
        next_steps["aborted"] = (
            "forge merge start --worktree "
            f"{current['worktree']['path']}"
        )
    elif action == "inactive-not-landed":
        next_steps["pushing"] = (
            f"forge merge abort --chain-id {current['chain_id']}"
        )
    return next_steps
