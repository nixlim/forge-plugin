"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
import datetime as dt
import os
from typing import TYPE_CHECKING, Any, Callable, Sequence
from forge_cli import chain_core, runtime
if TYPE_CHECKING:
    from forge_cli.engine._engine import Engine
from forge_cli.engine._state import TERMINAL_STATES as TERMINAL_STATES
from forge_cli.policy import Policy
from forge_cli.envelope import Outcome
import functools


def _new_state(
    chain_id: str,
    repo: chain_core.Repository,
    head: str,
    policy: Policy,
    paths: Sequence[str],
    declared_tier: str | None,
) -> dict[str, Any]:
    now = runtime.utc_now()
    session_identity = os.environ.get("CLAUDE_SESSION_ID")
    if not session_identity:
        session_identity = f"pid:{os.environ.get('FORGE_SESSION_PID') or os.getppid()}"
    state: dict[str, Any] = {
        "schema": chain_core.SCHEMA,
        "chain_id": chain_id,
        "kind": chain_core.KIND,
        "state": "classifying",
        "created_at": chain_core.iso_z(now),
        "last_event_at": chain_core.iso_z(now),
        "inactive_after": chain_core.iso_z(now + dt.timedelta(seconds=chain_core.INACTIVE_SECONDS)),
        "repo_head": head,
        "policy_source": {
            "path": "forge-project.md",
            "sha": policy.sha,
            "digest": policy.digest,
        },
        "paths": list(paths),
        "staging": {
            "worktree_root": str(repo.root),
            "session_identity": session_identity,
            "staged_paths": [],
            "staged_at": None,
            "classification_runs": 0,
            "anomalies": [],
        },
        "candidate": {"sha256": None, "computed_at": None},
        "tier": {
            "declared": declared_tier,
            "derived": None,
            "effective": declared_tier,
            "control": False,
            "categories": [],
            "classification": None,
        },
        "steps": {},
        "review": {
            "iteration": 0,
            "request": None,
            "verdict": None,
            "dispositions": [],
            "operator_cosign_required": False,
            "residual_risk": None,
        },
        "approval": {},
        "authorization": {},
        "commit_result": {},
    }
    return chain_core.validate_state(state, chain_id)


def _serialize_worktree_command(method: Callable[..., Outcome]) -> Callable[..., Outcome]:
    """Serialize each command against its worktree/index."""

    @functools.wraps(method)
    def wrapped(self: "Engine", *args: Any, **kwargs: Any) -> Outcome:
        with self.ctx.store.admission_lock(self.ctx.repo.root):
            return method(self, *args, **kwargs)

    return wrapped
