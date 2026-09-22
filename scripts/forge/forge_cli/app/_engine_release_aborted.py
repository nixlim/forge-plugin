from __future__ import annotations

import copy
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

from forge_cli import chain_core, engine
from forge_cli.envelope import REVISION9_OUTPUT_SCHEMA, FrozenError
from forge_cli.policy import sha256_bytes

if TYPE_CHECKING:
    from forge_cli.app._merge_engine import MergeEngine

def _release_to_aborted(
    self: "MergeEngine",
    state: dict[str, Any],
    *,
    reason: str | None,
    terminal_preconditions: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    claim = state["worktree"]["claim"]
    release_mode = (
        "acquired" if claim["status"] == "owned" else "never-published"
    )
    preconditions = (
        copy.deepcopy(dict(terminal_preconditions))
        if terminal_preconditions is not None
        else {
            "schema": "forge-merge-abort-preconditions/1",
            "chain_id": state["chain_id"],
            "source_state": state["state"],
            "candidate": copy.deepcopy(state.get("candidate")),
            "integration": copy.deepcopy(state["integration"]),
            "claim": copy.deepcopy(claim),
            # The operator-facing prose is not a durable event member;
            # bind only replay-reconstructible authority facts.
            "reason": None,
        }
    )
    generation = state.get("candidate")
    generation_digest = (
        str(generation["generation_digest"])
        if isinstance(generation, Mapping)
        else None
    )
    claim_path = Path(str(claim["path"]))
    if (
        release_mode == "never-published"
        and not engine._merge_unpublished_claim_absent(state, self.store)
    ):
        raise FrozenError(
            "unpublished merge ownership path unexpectedly exists",
            chain_id=str(state["chain_id"]),
            observed=str(claim_path),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    state = self.store.transition(
        state,
        "ownership_release_intent",
        {
            "target_terminal": "aborted",
            "terminal_disposition": "ordinary",
            "source_state": state["state"],
            "terminal_preconditions_digest": sha256_bytes(
                chain_core.canonical_bytes(preconditions)
            ),
            "release_mode": release_mode,
        },
        generation_digest=generation_digest,
        at=chain_core.iso_z(),
    )
    release_intent_digest = engine._merge_event_digest(
        self.store, str(state["chain_id"]), "ownership_release_intent"
    )
    if release_intent_digest is None:
        raise FrozenError(
            "merge ownership release intent digest is unavailable",
            chain_id=str(state["chain_id"]),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    if release_mode == "acquired":
        observed_claim = engine._remove_merge_claim(self.store, state, unlink=False)
        exists = True
        observed_inode = observed_claim.inode
        observed_digest = observed_claim.digest
    else:
        if not engine._merge_unpublished_claim_absent(state, self.store):
            raise FrozenError(
                "unpublished merge ownership path unexpectedly exists",
                chain_id=str(state["chain_id"]),
                observed=str(claim_path),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        exists = False
        observed_inode = None
        observed_digest = None
    observation = {
        "claim_path": state["worktree"]["claim"]["path"],
        "exists": exists,
        "inode": observed_inode,
        "digest": observed_digest,
    }
    state = self.store.transition(
        state,
        "ownership_released",
        {
            "release_intent_digest": release_intent_digest,
            "release_mode": release_mode,
            "terminal_disposition": "ordinary",
            "claim_inode": state["worktree"]["claim"]["inode"],
            "claim_digest": state["worktree"]["claim"]["digest"],
            "claim_observation_digest": sha256_bytes(
                chain_core.canonical_bytes(observation)
            ),
        },
        generation_digest=generation_digest,
        at=chain_core.iso_z(),
    )
    if (
        release_mode == "never-published"
        and not engine._merge_unpublished_claim_absent(state, self.store)
    ):
        raise FrozenError(
            "unpublished merge ownership path unexpectedly exists",
            chain_id=str(state["chain_id"]),
            observed=str(claim_path),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    terminal = self.store.transition(
        state,
        "aborted",
        {"delta": {"state": "aborted"}},
        generation_digest=generation_digest,
        at=chain_core.iso_z(),
    )
    if release_mode == "acquired":
        try:
            engine._remove_merge_claim(self.store, terminal)
        except (FrozenError, OSError):
            # Terminal truth is event-authoritative; tombstone collection
            # is best effort and must never revoke the durable release.
            pass
    return terminal

def _release_to_aborted_locked(
    self: "MergeEngine",
    state: dict[str, Any],
    lease: chain_core.ChainLease,
    *,
    reason: str | None,
    terminal_preconditions: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Perform an ordinary release while recovery owns its chain lease."""

    claim = state["worktree"]["claim"]
    claim_status = claim.get("status")
    if claim_status not in {"owned", "unpublished"}:
        raise FrozenError(
            "bootstrap recovery cannot release its recorded worktree claim",
            chain_id=str(state["chain_id"]),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    release_mode = (
        "acquired" if claim_status == "owned" else "never-published"
    )
    claim_path = Path(str(claim["path"]))
    if (
        release_mode == "never-published"
        and not engine._merge_unpublished_claim_absent(state, self.store)
    ):
        raise FrozenError(
            "unpublished merge ownership path unexpectedly exists",
            chain_id=str(state["chain_id"]),
            observed=str(claim_path),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    preconditions = (
        copy.deepcopy(dict(terminal_preconditions))
        if terminal_preconditions is not None
        else {
            "schema": "forge-merge-abort-preconditions/1",
            "chain_id": state["chain_id"],
            "source_state": state["state"],
            "candidate": copy.deepcopy(state.get("candidate")),
            "integration": copy.deepcopy(state["integration"]),
            "claim": copy.deepcopy(claim),
            # The operator-facing prose is not a durable event member;
            # bind only replay-reconstructible authority facts.
            "reason": None,
        }
    )
    state = self._epoch_transition(
        state,
        lease,
        "ownership_release_intent",
        {
            "target_terminal": "aborted",
            "terminal_disposition": "ordinary",
            "source_state": state["state"],
            "terminal_preconditions_digest": sha256_bytes(
                chain_core.canonical_bytes(preconditions)
            ),
            "release_mode": release_mode,
        },
    )
    release_intent_digest = self._tail_event_digest(
        state, "ownership_release_intent"
    )
    if release_mode == "acquired":
        observed_claim = engine._remove_merge_claim(self.store, state, unlink=False)
        exists = True
        observed_inode = observed_claim.inode
        observed_digest = observed_claim.digest
    else:
        if not engine._merge_unpublished_claim_absent(state, self.store):
            raise FrozenError(
                "unpublished merge ownership path unexpectedly exists",
                chain_id=str(state["chain_id"]),
                observed=str(claim_path),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        exists = False
        observed_inode = None
        observed_digest = None
    observation = {
        "claim_path": state["worktree"]["claim"]["path"],
        "exists": exists,
        "inode": observed_inode,
        "digest": observed_digest,
    }
    state = self._epoch_transition(
        state,
        lease,
        "ownership_released",
        {
            "release_intent_digest": release_intent_digest,
            "release_mode": release_mode,
            "terminal_disposition": "ordinary",
            "claim_inode": state["worktree"]["claim"]["inode"],
            "claim_digest": state["worktree"]["claim"]["digest"],
            "claim_observation_digest": sha256_bytes(
                chain_core.canonical_bytes(observation)
            ),
        },
    )
    if (
        release_mode == "never-published"
        and not engine._merge_unpublished_claim_absent(state, self.store)
    ):
        raise FrozenError(
            "unpublished merge ownership path unexpectedly exists",
            chain_id=str(state["chain_id"]),
            observed=str(claim_path),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    terminal = self._epoch_transition(
        state, lease, "aborted", {"delta": {"state": "aborted"}}
    )
    if release_mode == "acquired":
        try:
            engine._remove_merge_claim(self.store, terminal)
        except (FrozenError, OSError):
            pass
    return terminal

def _release_scope_exceeded(
    self: "MergeEngine",
    state: dict[str, Any],
    *,
    scope_proof_digest: str,
    fetch_result_event_digest: str,
    verb: str = "merge start",
) -> dict[str, Any]:
    chain_core._require_merge_integration_control("scope-release-clean-status")
    candidate = state.get("candidate")
    if (
        not isinstance(candidate, Mapping)
        or chain_core.SHA256_RE.fullmatch(scope_proof_digest) is None
        or chain_core.SHA256_RE.fullmatch(fetch_result_event_digest) is None
    ):
        raise FrozenError(
            "run-scope abort evidence is malformed",
            chain_id=str(state["chain_id"]),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    repository = chain_core.Repository(Path(str(state["worktree"]["path"])))
    current_head = repository.head()
    status = engine._merge_worktree_status(
        repository,
        Path(str(state["worktree"]["git_dir"])),
        verb=verb,
    )
    if status != b"":
        raise FrozenError(
            "run-scope abort worktree status is not exact clean",
            chain_id=str(state["chain_id"]),
            observed=(
                f"bytes={len(status)};sha256={sha256_bytes(status)}"
            ),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    if current_head != candidate["candidate_head"]:
        raise FrozenError(
            "run-scope abort candidate changed before release",
            chain_id=str(state["chain_id"]),
            observed=current_head,
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    preconditions = {
        "schema": "forge-run-scope-abort-preconditions/1",
        "target_terminal": "aborted",
        "terminal_disposition": "ordinary",
        "release_mode": "acquired",
        "source_state": "classifying",
        "scope_proof_digest": scope_proof_digest,
        "fetch_result_event_digest": fetch_result_event_digest,
        "generation_digest": candidate["generation_digest"],
        "worktree_identity": {
            name: state["worktree"][name]
            for name in ("path", "git_dir", "common_dir")
        },
        "branch": state["branch"],
        "candidate_head": candidate["candidate_head"],
        "current_head": current_head,
        "status_output_digest": sha256_bytes(b""),
        "push_intent_event_digests": [],
        "git_mutation_intent_event_digests": [],
        "unresolved_fence_digests": [],
    }
    return self._release_to_aborted(
        state,
        reason="changed paths exceed bound task scope",
        terminal_preconditions=preconditions,
    )
