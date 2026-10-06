"""Authenticate replay merge candidates; no journal or run authority."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, cast

from ._core import canonical_bytes
from ._replay_frames import MergeGenerationFrame, MergeReviewIterationFrame, MergeWorktreeClaimFrame
from ._replay_values import _utc_value
from ._replay_vocabulary import _CONTINUE_REPLAY
from ._state import COMMIT_RE, SHA256_RE
from forge_cli.policy import sha256_bytes


def _merge_older_head_only_contained(current: dict[str, Any]) -> bool:
    candidate = current.get("candidate")
    integration = current.get("integration")
    push = integration.get("push") if isinstance(integration, dict) else None
    observed = integration.get("observed") if isinstance(integration, dict) else None
    attempts = push.get("attempted_heads") if isinstance(push, dict) else None
    candidate_head = candidate.get("candidate_head") if isinstance(candidate, dict) else None
    landed_head = push.get("landed_head") if isinstance(push, dict) else None
    containment = observed.get("attempted_head_containment") if isinstance(observed, dict) else None
    return bool(
        isinstance(candidate_head, str)
        and isinstance(push, dict)
        and isinstance(attempts, list)
        and (len(attempts) >= 2)
        and (attempts[-1] == candidate_head)
        and (push.get("intended_head") == candidate_head)
        and isinstance(landed_head, str)
        and (landed_head != candidate_head)
        and (landed_head in attempts[:-1])
        and isinstance(observed, dict)
        and (observed.get("contains_intended_head") is False)
        and isinstance(containment, list)
        and any(
            isinstance(item, dict)
            and item.get("head") == landed_head
            and (item.get("contained") is True)
            for item in containment
        )
    )


def _merge_current_head_contained(current: dict[str, Any]) -> bool:
    candidate = current.get("candidate")
    integration = current.get("integration")
    push = integration.get("push") if isinstance(integration, dict) else None
    observed = integration.get("observed") if isinstance(integration, dict) else None
    attempts = push.get("attempted_heads") if isinstance(push, dict) else None
    candidate_head = candidate.get("candidate_head") if isinstance(candidate, dict) else None
    return bool(
        isinstance(candidate_head, str)
        and isinstance(push, dict)
        and isinstance(attempts, list)
        and attempts
        and (attempts[-1] == candidate_head)
        and (push.get("intended_head") == candidate_head)
        and (push.get("landed_head") == candidate_head)
        and isinstance(observed, dict)
        and (observed.get("contains_intended_head") is True)
    )


def _merge_claim_record_digest(
    state: dict[str, Any], worktree_identity: dict[str, Any]
) -> str | None:
    owner = state.get("owner")
    if (
        not isinstance(owner, dict)
        or set(owner) != {"pid", "host", "session", "started_at"}
        or type(owner.get("pid")) is not int
        or (int(owner["pid"]) <= 0)
        or (not isinstance(owner.get("host"), str))
        or (not owner["host"])
        or (not isinstance(owner.get("session"), str))
        or (not owner["session"])
        or (_utc_value(owner.get("started_at")) is None)
    ):
        return None
    identity = {name: worktree_identity[name] for name in ("path", "git_dir", "common_dir")}
    worktree_digest = sha256_bytes(canonical_bytes(identity))
    record = {
        "chain_id": state.get("chain_id"),
        "host": owner["host"],
        "pid": owner["pid"],
        "session": owner["session"],
        "started_at": owner["started_at"],
        "worktree_digest": worktree_digest,
    }
    return sha256_bytes(canonical_bytes(record))


def _check_merge_generation_shape(frame: MergeGenerationFrame) -> Any:
    if frame.candidate is None:
        return None
    if not isinstance(frame.candidate, dict) or set(frame.candidate) != {
        "remote",
        "destination_ref",
        "remote_tip",
        "candidate_head",
        "diff_sha256",
        "policy_commit",
        "policy_digest",
        "worktree_identity",
        "generation",
        "generation_digest",
    }:
        return None
    worktree = frame.candidate.get("worktree_identity")
    generation = frame.candidate.get("generation")
    if (
        frame.candidate.get("remote") != "origin"
        or not isinstance(frame.candidate.get("destination_ref"), str)
        or (not str(frame.candidate["destination_ref"]).startswith("refs/heads/"))
        or any(
            not isinstance(frame.candidate.get(name), str)
            or COMMIT_RE.fullmatch(str(frame.candidate[name])) is None
            for name in ("remote_tip", "candidate_head", "policy_commit")
        )
        or any(
            not isinstance(frame.candidate.get(name), str)
            or SHA256_RE.fullmatch(str(frame.candidate[name])) is None
            for name in ("diff_sha256", "policy_digest", "generation_digest")
        )
        or (not isinstance(worktree, dict))
        or (set(worktree) != {"path", "git_dir", "common_dir"})
        or (
            not all(
                isinstance(worktree.get(name), str)
                and Path(str(worktree[name])).is_absolute()
                for name in ("path", "git_dir", "common_dir")
            )
        )
        or (type(generation) is not int)
        or (int(generation) <= 0)
    ):
        return None
    frame.preimage = {
        name: frame.candidate[name]
        for name in (
            "remote",
            "destination_ref",
            "remote_tip",
            "candidate_head",
            "diff_sha256",
            "policy_commit",
            "policy_digest",
            "worktree_identity",
            "generation",
        )
    }
    frame.digest = sha256_bytes(canonical_bytes(frame.preimage))
    if frame.digest != frame.candidate.get("generation_digest"):
        return None
    return _CONTINUE_REPLAY


def _check_merge_generation_result(frame: MergeGenerationFrame) -> Any:
    return (frame.preimage, frame.digest)


def _check_merge_review_iteration_shape(frame: MergeReviewIterationFrame) -> Any:
    review = frame.state.get("review")
    if not isinstance(review, dict):
        return None
    if not review:
        return 0
    frame.iteration = cast(int, review.get("iteration"))
    if type(frame.iteration) is not int or not 1 <= int(frame.iteration) <= 8:
        return None
    for replay_name in ("request", "verdict"):
        name = replay_name
        value = review.get(name)
        if isinstance(value, dict) and (
            "iteration" in value and value.get("iteration") != frame.iteration
        ):
            return None
    return _CONTINUE_REPLAY


def _check_merge_review_iteration_result(frame: MergeReviewIterationFrame) -> Any:
    return int(frame.iteration)


def _check_merge_worktree_identity(frame: MergeWorktreeClaimFrame) -> Any:
    frame.worktree = cast(dict[str, Any], frame.state.get("worktree"))
    if not isinstance(frame.worktree, dict) or set(frame.worktree) != {
        "path",
        "git_dir",
        "common_dir",
        "claim",
    }:
        return None
    if any(
        not isinstance(frame.worktree.get(name), str)
        or not Path(str(frame.worktree[name])).is_absolute()
        for name in ("path", "git_dir", "common_dir")
    ):
        return None
    frame.claim = cast(dict[str, Any], frame.worktree.get("claim"))
    if not isinstance(frame.claim, dict) or set(frame.claim) != {
        "status",
        "path",
        "inode",
        "digest",
    }:
        return None
    identity = {name: frame.worktree[name] for name in ("path", "git_dir", "common_dir")}
    if any(os.path.realpath(str(value)) != value for value in identity.values()):
        return None
    worktree_digest = sha256_bytes(canonical_bytes(identity))
    frame.expected_claim_path = (
        Path(str(frame.worktree["common_dir"])).parent
        / ".forge"
        / "chains"
        / "owners"
        / f"{worktree_digest}.claim"
    )
    frame.inode = frame.claim.get("inode")
    frame.digest = frame.claim.get("digest")
    return _CONTINUE_REPLAY


def _check_merge_claim_shape(frame: MergeWorktreeClaimFrame) -> Any:
    if (
        frame.claim.get("status") not in {"unpublished", "owned", "releasing", "released"}
        or frame.claim.get("path") != str(frame.expected_claim_path)
        or (frame.inode is not None and (type(frame.inode) is not int or int(frame.inode) <= 0))
        or (
            frame.digest is not None
            and (not isinstance(frame.digest, str) or SHA256_RE.fullmatch(frame.digest) is None)
        )
    ):
        return None
    return (frame.worktree, frame.claim)


def _merge_generation(candidate: Any) -> tuple[dict[str, Any], str] | None:
    frame = MergeGenerationFrame(candidate=candidate)
    for check in (_check_merge_generation_shape, _check_merge_generation_result):
        result = check(frame)
        if result is not _CONTINUE_REPLAY:
            return result
    raise AssertionError("replay checks did not terminate")


def _merge_review_iteration(state: dict[str, Any]) -> int | None:
    frame = MergeReviewIterationFrame(state=state)
    for check in (_check_merge_review_iteration_shape, _check_merge_review_iteration_result):
        result = check(frame)
        if result is not _CONTINUE_REPLAY:
            return result
    raise AssertionError("replay checks did not terminate")


def _merge_worktree_claim(state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]] | None:
    frame = MergeWorktreeClaimFrame(state=state)
    for check in (_check_merge_worktree_identity, _check_merge_claim_shape):
        result = check(frame)
        if result is not _CONTINUE_REPLAY:
            return result
    raise AssertionError("replay checks did not terminate")
