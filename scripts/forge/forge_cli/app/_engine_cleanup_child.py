from __future__ import annotations

import copy
import os
import secrets
from typing import TYPE_CHECKING, Any, Callable, Mapping, Sequence

from forge_cli import chain_core, engine, runtime
from forge_cli.envelope import REVISION9_OUTPUT_SCHEMA, FrozenError
from forge_cli.policy import sha256_bytes

if TYPE_CHECKING:
    from forge_cli.app._merge_engine import MergeEngine

def _release_to_closed_locked(
    self: "MergeEngine",
    state: dict[str, Any],
    lease: chain_core.ChainLease,
) -> dict[str, Any]:
    """Commit the FR-237 close cutoff while the ordered locks are held."""

    chain_core._require_merge_integration_control("nonforce-cleanup")
    claim = state["worktree"]["claim"]
    if claim.get("status") != "owned":
        raise FrozenError(
            "pushed merge ownership is not acquired at cleanup cutoff",
            chain_id=str(state["chain_id"]),
            observed=str(claim.get("status")),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    push = state.get("integration", {}).get("push")
    if not isinstance(push, Mapping):
        raise FrozenError(
            "cleanup cutoff lacks authenticated push containment",
            chain_id=str(state["chain_id"]),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    with self.store.event_lock(str(state["chain_id"])):
        replay = self.store._read_replay_locked(str(state["chain_id"]))
    cleanup_evidence = chain_core._merge_cleanup_evidence_history(replay.events)
    summary = chain_core._merge_cleanup_history_summary(replay.events)
    containment_result = summary.get("remote_containment")
    containment_observation = (
        containment_result.get("observation")
        if isinstance(containment_result, Mapping)
        else None
    )
    if not (
        cleanup_evidence
        and cleanup_evidence[-1].get("event") == "cleanup_result"
        and isinstance(containment_observation, Mapping)
        and containment_observation.get("landed_head")
        == push.get("landed_head")
        and containment_observation.get("contained") is True
        and summary.get("worktree_complete") is True
        and summary.get("branch_complete") is True
        and state.get("cleanup") == {"condition": "none"}
    ):
        raise FrozenError(
            "cleanup cutoff lacks the complete durable step history",
            chain_id=str(state["chain_id"]),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    preconditions = {
        "schema": chain_core._MERGE_CLEANUP_CLOSE_SCHEMA,
        "chain_id": state["chain_id"],
        "source_state": state["state"],
        "landed_head": push["landed_head"],
        "containment_observation": copy.deepcopy(
            dict(containment_observation)
        ),
        "cleanup_evidence": cleanup_evidence,
    }
    state = self._epoch_transition(
        state,
        lease,
        "ownership_release_intent",
        {
            "target_terminal": "closed",
            "terminal_disposition": "ordinary",
            "source_state": state["state"],
            "terminal_preconditions_digest": sha256_bytes(
                chain_core.canonical_bytes(preconditions)
            ),
            "release_mode": "acquired",
        },
    )
    release_intent_digest = self._tail_event_digest(
        state, "ownership_release_intent"
    )
    observed_claim = engine._remove_merge_claim(self.store, state, unlink=False)
    observation = {
        "claim_path": state["worktree"]["claim"]["path"],
        "exists": True,
        "inode": observed_claim.inode,
        "digest": observed_claim.digest,
    }
    state = self._epoch_transition(
        state,
        lease,
        "ownership_released",
        {
            "release_intent_digest": release_intent_digest,
            "release_mode": "acquired",
            "terminal_disposition": "ordinary",
            "claim_inode": state["worktree"]["claim"]["inode"],
            "claim_digest": state["worktree"]["claim"]["digest"],
            "claim_observation_digest": sha256_bytes(
                chain_core.canonical_bytes(observation)
            ),
        },
    )
    terminal = self._epoch_transition(
        state,
        lease,
        "closed",
        {"delta": {"state": "closed"}},
    )
    try:
        engine._remove_merge_claim(self.store, terminal)
    except (FrozenError, OSError):
        # The event-authoritative terminal release remains valid when its
        # materialized tombstone cannot be collected in this invocation.
        pass
    return terminal

def _cleanup_result_locked(
    self: "MergeEngine",
    state: dict[str, Any],
    lease: chain_core.ChainLease,
    *,
    result: Mapping[str, Any],
) -> dict[str, Any]:
    outcome = result.get("outcome")
    if not isinstance(outcome, str) or outcome not in {
        "passed",
        "already-absent",
        "failed",
    }:
        raise FrozenError(
            "merge cleanup result has an invalid closed outcome",
            chain_id=str(state["chain_id"]),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    failed = outcome == "failed"
    delta: dict[str, Any] = {
        "cleanup": {"condition": "cleanup-failed" if failed else "none"}
    }
    if failed and state["state"] != "cleanup_pending":
        delta["state"] = "cleanup_pending"
    return self._epoch_transition(
        state,
        lease,
        "cleanup_result",
        {
            "delta": delta,
            "cleanup_results": [copy.deepcopy(dict(result))],
        },
    )

def _run_cleanup_child(
    self: "MergeEngine",
    state: dict[str, Any],
    lock: chain_core.CommonRebaseLock,
    lease: chain_core.ChainLease,
    *,
    operation: str,
    fence_operation: str,
    subject: Mapping[str, Any],
    argv: Sequence[str],
    observe: Callable[
        [chain_core.FencedProcessResult], tuple[str, Mapping[str, Any]]
    ],
) -> tuple[dict[str, Any], chain_core.FencedProcessResult, dict[str, Any]]:
    recovery: dict[str, Any] | None = None
    existing_cleanup = state.get("cleanup")
    existing_intent = (
        existing_cleanup.get("intent")
        if isinstance(existing_cleanup, Mapping)
        else None
    )
    if (
        isinstance(existing_intent, Mapping)
        and existing_intent.get("schema") == chain_core._MERGE_CLEANUP_INTENT_SCHEMA
    ):
        with self.store.event_lock(str(state["chain_id"])):
            replay = self.store._read_replay_locked(str(state["chain_id"]))
        unmatched = chain_core._merge_cleanup_unmatched_intent(replay.events)
        if not (
            operation == "remote-fetch"
            and isinstance(unmatched, Mapping)
            and chain_core._recovery_cleanup_intent(unmatched) == existing_intent
            and chain_core._merge_cleanup_retry_proof_valid(replay.events, unmatched)
        ):
            raise FrozenError(
                "cleanup pending intent lacks its exact recovery proof",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        recovery = {
            "schema": chain_core._MERGE_CLEANUP_RECOVERY_SCHEMA,
            "intent_event_digest": unmatched["digest"],
            "operation": existing_intent["operation"],
            "fence_operation": existing_intent["fence_operation"],
            "recovery_event_digest": replay.events[-1]["digest"],
        }
    intent = {
        "schema": chain_core._MERGE_CLEANUP_INTENT_SCHEMA,
        "operation": operation,
        "fence_operation": fence_operation,
        "operation_nonce": secrets.token_hex(16),
        "generation_digest": state["candidate"]["generation_digest"],
        "subject": copy.deepcopy(dict(subject)),
        "argv": list(argv),
        "cwd": str(self.ctx.repo.root),
        "started_at": chain_core.iso_z(),
    }
    if recovery is not None:
        intent["recovery"] = recovery
    if not chain_core._merge_cleanup_intent_valid(intent, state):
        raise FrozenError(
            "cleanup child intent is malformed",
            chain_id=str(state["chain_id"]),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    cleanup = {
        "condition": str(state["cleanup"]["condition"]),
        "intent": intent,
    }
    state = self._epoch_transition(
        state,
        lease,
        "cleanup_intent",
        {"delta": {"cleanup": cleanup}},
    )
    intent_digest = self._tail_event_digest(state, "cleanup_intent")
    holder: dict[str, Any] = {}

    def intent_current() -> bool:
        try:
            fresh = self.store.load_locked(str(state["chain_id"]), lease=lease)
        except (FrozenError, OSError):
            return False
        return bool(
            fresh.get("cleanup") == cleanup
            and self._tail_event_digest(fresh, "cleanup_intent")
            == intent_digest
        )

    def persist(result: chain_core.FencedProcessResult) -> None:
        nonlocal state
        outcome, observation = observe(result)
        evidence = {
            "schema": chain_core._MERGE_CLEANUP_RESULT_SCHEMA,
            "operation": operation,
            "fence_operation": fence_operation,
            "operation_nonce": intent["operation_nonce"],
            "intent_event_digest": intent_digest,
            "outcome": outcome,
            "observation": copy.deepcopy(dict(observation)),
            "process": engine._merge_cleanup_process_record(result),
        }
        state = self._cleanup_result_locked(
            state, lease, result=evidence
        )
        holder["result"] = result
        holder["evidence"] = evidence

    environment = os.environ.copy()
    environment.pop("FORGE_SESSION_PID", None)
    environment.update(
        {
            "LC_ALL": "C",
            "LANG": "C",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_NO_LAZY_FETCH": "1",
        }
    )
    try:
        returned = chain_core.run_fenced_command(
            lock,
            operation=fence_operation,
            intent_digest=intent_digest,
            intent_validator=intent_current,
            argv=argv,
            cwd=self.ctx.repo.root,
            persist_result=persist,
            env=environment,
            timeout=runtime.COMMAND_TIMEOUT_SECONDS,
            cap=runtime.OUTPUT_CAP_BYTES,
            verbose=self.ctx.options.verbose,
        )
    except chain_core.CommonLockUnavailable:
        # ``run_fenced_command`` uses this exception only before its start
        # byte can authorize the child.  Close that durable intent with an
        # authenticated no-execution failure so an ordinary publication
        # failure cannot strand or silently overwrite the cleanup window.
        absent = chain_core.FencedProcessResult(
            argv=list(argv),
            returncode=None,
            duration_seconds=0.0,
            output=b"",
            output_digest=sha256_bytes(b""),
            timed_out=False,
            output_limit=False,
            launch_failed=True,
            group_survived=False,
            authorized=False,
            fence_digest=None,  # type: ignore[arg-type]
            fence_inode=None,  # type: ignore[arg-type]
        )
        persist(absent)
        raise
    result = holder.get("result")
    evidence = holder.get("evidence")
    if (
        not isinstance(result, chain_core.FencedProcessResult)
        or not isinstance(evidence, dict)
        or returned != result
        or evidence.get("process") != engine._merge_cleanup_process_record(result)
    ):
        raise FrozenError(
            "cleanup child produced no durable result",
            chain_id=str(state["chain_id"]),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    return state, result, evidence
