"""Extracted from scripts/forge/forge_cli/app/__init__.py."""
from __future__ import annotations
from pathlib import Path
from typing import Any, Mapping
from forge_cli import chain_core, engine
from forge_cli.app._admission import prepare_merge_admission
from forge_cli.envelope import FrozenError, REVISION9_OUTPUT_SCHEMA, V2ReasonCode
from forge_cli.policy import Policy, PolicyError, parse_policy, sha256_bytes


def _observe_current_merge_candidate(
    ctx: chain_core.CommandContext,
    state: Mapping[str, Any],
    *,
    verb: str,
    observation: Mapping[str, Any] | None = None,
) -> tuple[chain_core.Repository, Policy, tuple[str, ...]]:
    """Recompute every FR-233 post-executable generation member."""

    chain_core._require_merge_adapter_control("admission-and-generation")
    if observation is not None:
        repository, policy, changed_paths, _diff, _classifier = (
            engine._parse_merge_candidate_observation(
                state,
                observation,
                verb=verb,
                require_current_generation=True,
            )
        )
        return repository, policy, changed_paths
    candidate = state.get("candidate")
    worktree = state.get("worktree")
    target = state.get("target")
    policy_source = state.get("policy_source")
    if not all(
        isinstance(value, Mapping)
        for value in (candidate, worktree, target, policy_source)
    ):
        raise FrozenError(
            "merge candidate tuple is unavailable",
            chain_id=str(state.get("chain_id") or "") or None,
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    assert isinstance(candidate, Mapping)
    assert isinstance(worktree, Mapping)
    assert isinstance(target, Mapping)
    assert isinstance(policy_source, Mapping)
    path = Path(str(worktree.get("path", "")))
    if not path.exists():
        raise chain_core._merge_refusal(
            V2ReasonCode.STATE_PRECONDITION,
            f"forge: {verb} refused — recorded worktree is missing",
            expected=str(path),
            observed="foreign-git-state",
            remediation=f"forge status --chain-id {state['chain_id']}",
            chain=state,
        )
    repository = chain_core.Repository(path)
    try:
        git_dir = engine._absolute_git_path(repository, "--git-dir")
        common_dir = engine._absolute_git_path(repository, "--git-common-dir")
    except OSError as exc:
        raise chain_core._merge_refusal(
            V2ReasonCode.WORKTREE_INVALID,
            f"forge: {verb} refused — recorded worktree identity is invalid",
            observed=str(exc),
            chain=state,
        ) from exc
    observed_identity = {
        "path": str(repository.root),
        "git_dir": str(git_dir),
        "common_dir": str(common_dir),
    }
    expected_identity = {
        name: str(worktree.get(name, ""))
        for name in ("path", "git_dir", "common_dir")
    }
    if observed_identity != expected_identity:
        raise chain_core._merge_refusal(
            V2ReasonCode.WORKTREE_INVALID,
            f"forge: {verb} refused — recorded worktree identity changed",
            expected=chain_core.canonical_bytes(expected_identity).decode("utf-8"),
            observed=chain_core.canonical_bytes(observed_identity).decode("utf-8"),
            chain=state,
        )
    engine._merge_worktree_status(repository, git_dir, verb=verb)
    current_head = repository.head()
    expected_head = str(candidate.get("candidate_head", ""))
    if current_head != expected_head:
        raise chain_core._merge_refusal(
            V2ReasonCode.CANDIDATE_STALE,
            f"forge: {verb} refused — candidate HEAD is stale",
            expected=expected_head,
            observed=current_head,
            remediation=f"forge merge refresh --chain-id {state['chain_id']}",
            chain=state,
        )

    main = chain_core.Repository(Path(str(state["repository"])))
    manifest_commit = main.head()
    manifest = main.git(
        ["show", f"{manifest_commit}:.forge-manifest"], check=False
    )
    try:
        default_branch = (
            engine._parse_plugin_manifest(manifest.stdout)
            if manifest.returncode == 0
            else ""
        )
    except ValueError:
        default_branch = ""
    observed_target = {
        "remote": "origin",
        "destination_ref": f"refs/heads/{default_branch}",
        "manifest_commit": manifest_commit,
    }
    if observed_target != dict(target):
        raise chain_core._merge_refusal(
            V2ReasonCode.PUSH_TARGET_INVALID,
            f"forge: {verb} refused — fixed merge target changed",
            expected=chain_core.canonical_bytes(dict(target)).decode("utf-8"),
            observed=chain_core.canonical_bytes(observed_target).decode("utf-8"),
            chain=state,
        )
    try:
        policy_commit, policy_raw = repository.policy(current_head)
        policy = parse_policy(policy_commit, policy_raw)
    except (OSError, PolicyError, UnicodeError) as exc:
        raise chain_core._merge_refusal(
            V2ReasonCode.POLICY_UNREADABLE,
            f"forge: {verb} refused — committed candidate policy is unreadable: {exc}",
            observed=str(exc),
            chain=state,
        ) from exc
    if (
        policy.sha != policy_source.get("commit")
        or policy.digest != policy_source.get("digest")
    ):
        raise chain_core._merge_refusal(
            V2ReasonCode.CANDIDATE_STALE,
            f"forge: {verb} refused — committed candidate policy changed",
            expected=str(policy_source.get("digest")),
            observed=policy.digest,
            chain=state,
        )
    remote_tip = str(candidate.get("remote_tip", ""))
    diff = repository.git(
        ["diff", f"{remote_tip}...{current_head}"], check=False
    )
    if diff.returncode != 0:
        raise chain_core._merge_refusal(
            V2ReasonCode.CANDIDATE_STALE,
            f"forge: {verb} refused — fixed candidate range is unavailable",
            observed=diff.stderr.decode("utf-8", "replace").strip(),
            chain=state,
        )
    observed_preimage = {
        "remote": "origin",
        "destination_ref": str(target["destination_ref"]),
        "remote_tip": remote_tip,
        "candidate_head": current_head,
        "diff_sha256": sha256_bytes(diff.stdout),
        "policy_commit": policy.sha,
        "policy_digest": policy.digest,
        "worktree_identity": observed_identity,
        "generation": candidate.get("generation"),
    }
    observed_candidate = {
        **observed_preimage,
        "generation_digest": sha256_bytes(chain_core.canonical_bytes(observed_preimage)),
    }
    if observed_candidate != dict(candidate):
        raise chain_core._merge_refusal(
            V2ReasonCode.CANDIDATE_STALE,
            f"forge: {verb} refused — merge generation tuple is stale",
            expected=str(candidate.get("generation_digest")),
            observed=observed_candidate["generation_digest"],
            remediation=f"forge merge refresh --chain-id {state['chain_id']}",
            chain=state,
        )
    names = repository.git(
        [
            "diff",
            "--name-only",
            "-z",
            "--diff-filter=ACDMRTUXB",
            f"{remote_tip}...{current_head}",
            "--",
        ]
    ).stdout
    try:
        changed_paths = tuple(
            sorted(
                {item.decode("utf-8") for item in names.split(b"\0") if item},
                key=lambda value: value.encode("utf-8"),
            )
        )
    except UnicodeDecodeError as exc:
        raise chain_core._merge_refusal(
            V2ReasonCode.WORKTREE_INVALID,
            f"forge: {verb} refused — candidate paths are not UTF-8",
            observed=str(exc),
            chain=state,
        ) from exc
    return repository, policy, changed_paths
