from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping

from forge_cli import chain_core, engine
from forge_cli.envelope import REVISION9_OUTPUT_SCHEMA, FrozenError, V2ReasonCode
from forge_cli.policy import sha256_bytes

if TYPE_CHECKING:
    from forge_cli.app._merge_engine import MergeEngine

def _complete_pending_release_locked(
    self: "MergeEngine",
    state: dict[str, Any],
    lease: chain_core.ChainLease,
    *,
    expected_target: str | None = None,
) -> tuple[dict[str, Any], str]:
    """Resume only the event-selected ownership terminal transaction."""

    claim = state.get("worktree", {}).get("claim")
    if not isinstance(claim, Mapping) or claim.get("status") not in {
        "releasing",
        "released",
    }:
        return state, "ordinary"
    with self.store.event_lock(str(state["chain_id"])):
        replay = self.store._read_replay_locked(str(state["chain_id"]))
    intent = next(
        (
            event
            for event in reversed(replay.events)
            if event.get("event") == "ownership_release_intent"
        ),
        None,
    )
    if not isinstance(intent, Mapping) or not isinstance(
        intent.get("payload"), Mapping
    ):
        raise FrozenError(
            "pending ownership release lacks its authenticated intent",
            chain_id=str(state["chain_id"]),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    release = intent["payload"]
    target = str(release.get("target_terminal"))
    mode = str(release.get("release_mode"))
    disposition = str(release.get("terminal_disposition"))
    if target not in {"closed", "aborted"} or mode not in {
        "acquired",
        "never-published",
    }:
        raise FrozenError(
            "pending ownership release carries an invalid terminal selection",
            chain_id=str(state["chain_id"]),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    if expected_target is not None and target != expected_target:
        raise chain_core._merge_refusal(
            V2ReasonCode.STATE_PRECONDITION,
            "forge: merge cleanup refused — pending ownership release selects another terminal",
            expected=expected_target,
            observed=target,
            remediation=f"forge merge recover --chain-id {state['chain_id']}",
            chain=state,
        )
    if claim.get("status") == "releasing":
        if mode == "acquired":
            observed_claim = engine._remove_merge_claim(
                self.store, state, unlink=False
            )
            observation = {
                "claim_path": claim["path"],
                "exists": True,
                "inode": observed_claim.inode,
                "digest": observed_claim.digest,
            }
        else:
            if not engine._merge_unpublished_claim_absent(state, self.store):
                raise FrozenError(
                    "never-published release observed an ownership pathname",
                    chain_id=str(state["chain_id"]),
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            observation = {
                "claim_path": claim["path"],
                "exists": False,
                "inode": None,
                "digest": None,
            }
        state = self._epoch_transition(
            state,
            lease,
            "ownership_released",
            {
                "release_intent_digest": intent["digest"],
                "release_mode": mode,
                "terminal_disposition": disposition,
                "claim_inode": claim.get("inode"),
                "claim_digest": claim.get("digest"),
                "claim_observation_digest": sha256_bytes(
                    chain_core.canonical_bytes(observation)
                ),
            },
        )
    if state["worktree"]["claim"]["status"] != "released":
        raise FrozenError(
            "ownership release result did not materialize released truth",
            chain_id=str(state["chain_id"]),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    terminal_payload: dict[str, Any] = {"delta": {"state": target}}
    if disposition == "historical-landed-superseded":
        push = state.get("integration", {}).get("push")
        observed = state.get("integration", {}).get("observed")
        if not isinstance(push, Mapping) or not isinstance(observed, Mapping):
            raise FrozenError(
                "historical release lost its containment evidence",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        terminal_payload = {
            "terminal_disposition": disposition,
            "landed_head": push.get("landed_head"),
            "superseded_head": push.get("intended_head"),
            "observation_digest": observed.get("output_digest"),
        }
    state = self._epoch_transition(
        state, lease, target, terminal_payload
    )
    if mode == "acquired":
        try:
            engine._remove_merge_claim(self.store, state)
        except (FrozenError, OSError):
            pass
    return state, disposition

def _resume_pending_release(
    self: "MergeEngine",
    state: dict[str, Any],
    *,
    expected_target: str | None = None,
) -> tuple[dict[str, Any], str] | None:
    """Complete an event-selected terminal cutoff without the common lock."""

    claim = state.get("worktree", {}).get("claim")
    if (
        not isinstance(claim, Mapping)
        or claim.get("status") not in {"releasing", "released"}
        or state.get("state") in {"closed", "aborted"}
    ):
        return None
    # A chain-only completion may not reclaim an abandoned lease: that
    # requires repository-wide recovery exclusion.  If the published
    # lease name already exists, route the caller through its ordinary
    # common-lock recovery path instead of spending a second, shorter
    # acquisition budget here.
    lease_path = self.store.root / f"{state['chain_id']}.lock"
    try:
        lease_path.lstat()
    except FileNotFoundError:
        pass
    except OSError:
        return None
    else:
        return None
    binding = state.get("run_binding")
    with self.store._journal_outer(
        binding if isinstance(binding, Mapping) else None
    ):
        with chain_core.acquire_chain_lease(
            self.store.root,
            chain_id=str(state["chain_id"]),
            session=self.store._session(None),
            single_attempt=True,
        ) as lease:
            current = self.store.load_locked(
                str(state["chain_id"]), lease=lease
            )
            current_claim = current.get("worktree", {}).get("claim")
            if (
                not isinstance(current_claim, Mapping)
                or current_claim.get("status") not in {"releasing", "released"}
                or current.get("state") in {"closed", "aborted"}
            ):
                raise chain_core._merge_refusal(
                    V2ReasonCode.STATE_PRECONDITION,
                    "forge: pending ownership release changed before completion",
                    expected=str(claim.get("status")),
                    observed=str(
                        current_claim.get("status")
                        if isinstance(current_claim, Mapping)
                        else None
                    ),
                    remediation=f"forge status --chain-id {state['chain_id']}",
                    chain=current,
                )
            return self._complete_pending_release_locked(
                current, lease, expected_target=expected_target
            )

def _release_historical_landing_locked(
    self: "MergeEngine",
    state: dict[str, Any],
    lock: chain_core.CommonRebaseLock,
    lease: chain_core.ChainLease,
    *,
    observation_event_digest: str | None = None,
) -> dict[str, Any]:
    """Release only an inactive newer head after older-only landing truth."""

    if not engine._merge_inactive(state):
        raise FrozenError(
            "historical merge release requires inactive authority",
            chain_id=str(state["chain_id"]),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    selected_observation = observation_event_digest or self._tail_event_digest(
        state, "push_observed"
    )
    if selected_observation is None:
        raise FrozenError(
            "historical merge release lacks a fresh observation",
            chain_id=str(state["chain_id"]),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    preconditions = self._attempted_release_preconditions_locked(
        state,
        lock,
        expected_containment="older",
        observation_event_digest=selected_observation,
        terminal_disposition="historical-landed-superseded",
    )
    claim = state["worktree"]["claim"]
    state = self._epoch_transition(
        state,
        lease,
        "ownership_release_intent",
        {
            "target_terminal": "aborted",
            "terminal_disposition": "historical-landed-superseded",
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
        "claim_path": claim["path"],
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
            "terminal_disposition": "historical-landed-superseded",
            "claim_inode": claim["inode"],
            "claim_digest": claim["digest"],
            "claim_observation_digest": sha256_bytes(
                chain_core.canonical_bytes(observation)
            ),
        },
    )
    push = state["integration"]["push"]
    observed = state["integration"]["observed"]
    terminal = self._epoch_transition(
        state,
        lease,
        "aborted",
        {
            "terminal_disposition": "historical-landed-superseded",
            "landed_head": push["landed_head"],
            "superseded_head": push["intended_head"],
            "observation_digest": observed["output_digest"],
        },
    )
    try:
        engine._remove_merge_claim(self.store, terminal)
    except (FrozenError, OSError):
        pass
    return terminal
