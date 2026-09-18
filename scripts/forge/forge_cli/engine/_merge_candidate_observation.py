"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
import base64
import binascii
from typing import Any, Mapping
from forge_cli import chain_core
from forge_cli.engine._merge_worktree import _parse_plugin_manifest as _parse_plugin_manifest
import os
from pathlib import Path
from forge_cli.envelope import FrozenError, REVISION9_OUTPUT_SCHEMA, V2ReasonCode
from forge_cli.policy import Policy, PolicyError, parse_policy, sha256_bytes


def _merge_candidate_observation_outputs(
    state: Mapping[str, Any], value: object
) -> dict[str, bytes] | None:
    if not chain_core._merge_candidate_observation_evidence_valid(state, value):
        return None
    assert isinstance(value, Mapping)
    outputs: dict[str, bytes] = {}
    for record in value["steps"]:
        child = record["child_result"]
        try:
            output = base64.b64decode(child["output_b64"], validate=True)
        except (ValueError, binascii.Error):
            return None
        if (
            child.get("authorized") is not True
            or child.get("exit") != 0
            or child.get("launch_failed") is not False
            or child.get("timed_out") is not False
            or child.get("output_limit_exceeded") is not False
            or child.get("group_survived") is not False
        ):
            return None
        outputs[str(record["step"])] = output
    return outputs


def _parse_merge_candidate_observation(
    state: Mapping[str, Any],
    value: object,
    *,
    verb: str,
    require_current_generation: bool,
) -> tuple[chain_core.Repository, Policy, tuple[str, ...], bytes, bytes | None]:
    """Consume only authenticated durable bytes; this function launches nothing."""

    outputs = _merge_candidate_observation_outputs(state, value)
    if outputs is None or not isinstance(value, Mapping) or value.get("verb") != verb:
        raise chain_core._merge_refusal(
            V2ReasonCode.EVIDENCE_INCOMPLETE,
            f"forge: {verb} refused — candidate observation evidence is invalid",
            chain=state,
        )
    worktree = state.get("worktree")
    target = state.get("target")
    if not isinstance(worktree, Mapping) or not isinstance(target, Mapping):
        raise FrozenError(
            "merge candidate observation lacks its recorded identity",
            chain_id=str(state.get("chain_id", "")) or None,
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    expected_head = str(value.get("expected_head", ""))
    remote_tip = str(value.get("remote_tip", ""))
    identity = outputs["identity"]
    try:
        identity_lines = identity.decode("utf-8").splitlines(keepends=True)
    except UnicodeDecodeError as exc:
        raise chain_core._merge_refusal(
            V2ReasonCode.WORKTREE_INVALID,
            f"forge: {verb} refused — recorded worktree identity is invalid",
            observed=str(exc),
            chain=state,
        ) from exc
    if (
        len(identity_lines) != 4
        or any(not line.endswith("\n") or "\r" in line for line in identity_lines)
    ):
        raise chain_core._merge_refusal(
            V2ReasonCode.WORKTREE_INVALID,
            f"forge: {verb} refused — recorded worktree identity is invalid",
            observed="malformed combined rev-parse output",
            chain=state,
        )
    git_dir_raw, common_dir_raw, root_raw, head_raw = (
        line.removesuffix("\n") for line in identity_lines
    )
    if chain_core.COMMIT_RE.fullmatch(head_raw) is None:
        raise chain_core._merge_refusal(
            V2ReasonCode.WORKTREE_INVALID,
            f"forge: {verb} refused — recorded worktree HEAD is invalid",
            observed=head_raw,
            chain=state,
        )
    observed_identity = {
        "path": os.path.realpath(root_raw),
        "git_dir": os.path.realpath(git_dir_raw),
        "common_dir": os.path.realpath(common_dir_raw),
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
    try:
        inventory = chain_core._parse_registered_worktrees(outputs["worktrees"])
    except OSError as exc:
        raise chain_core._merge_refusal(
            V2ReasonCode.WORKTREE_INVALID,
            f"forge: {verb} refused — registered worktree inventory is invalid",
            observed=str(exc),
            chain=state,
        ) from exc
    matches = [
        entry
        for entry in inventory
        if os.path.realpath(str(entry.get("worktree", "")))
        == expected_identity["path"]
    ]
    if (
        len(matches) != 1
        or not inventory
        or os.path.realpath(str(inventory[0].get("worktree", "")))
        == expected_identity["path"]
        or matches[0].get("HEAD") != head_raw
        or matches[0].get("branch") != state.get("branch")
        or outputs["branch"] != f"{state.get('branch')}\n".encode("utf-8")
    ):
        raise chain_core._merge_refusal(
            V2ReasonCode.WORKTREE_INVALID,
            f"forge: {verb} refused — recorded worktree registration changed",
            expected="one exact registered non-main worktree/branch/HEAD tuple",
            observed=str(matches),
            chain=state,
        )
    if head_raw != expected_head:
        raise chain_core._merge_refusal(
            V2ReasonCode.CANDIDATE_STALE,
            f"forge: {verb} refused — candidate HEAD is stale",
            expected=expected_head,
            observed=head_raw,
            chain=state,
        )
    if outputs["status"] != b"":
        raise chain_core._merge_refusal(
            V2ReasonCode.DIRTY_WORKTREE,
            f"forge: {verb} refused — source worktree is not clean",
            expected="zero exact status bytes",
            observed=outputs["status"].decode("utf-8", "replace"),
            chain=state,
        )
    for marker in (
        "MERGE_HEAD",
        "CHERRY_PICK_HEAD",
        "REVERT_HEAD",
        "BISECT_LOG",
        "rebase-apply",
        "rebase-merge",
        "sequencer",
    ):
        try:
            os.lstat(Path(expected_identity["git_dir"]) / marker)
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise chain_core._merge_refusal(
                V2ReasonCode.WORKTREE_INVALID,
                f"forge: {verb} refused — Git operation metadata is unreadable",
                observed=str(exc),
                chain=state,
            ) from exc
        raise chain_core._merge_refusal(
            V2ReasonCode.DIRTY_WORKTREE,
            f"forge: {verb} refused — source worktree is not clean",
            observed=f"in-progress Git operation: {marker}",
            chain=state,
        )
    main_head = outputs["main-head"]
    manifest_commit = str(target.get("manifest_commit", ""))
    if main_head != f"{manifest_commit}\n".encode("ascii"):
        raise chain_core._merge_refusal(
            V2ReasonCode.PUSH_TARGET_INVALID,
            f"forge: {verb} refused — fixed merge target changed",
            expected=manifest_commit,
            observed=main_head.decode("ascii", "replace").strip(),
            chain=state,
        )
    try:
        default_branch = _parse_plugin_manifest(outputs["manifest"])
    except (UnicodeError, ValueError) as exc:
        raise chain_core._merge_refusal(
            V2ReasonCode.PUSH_TARGET_INVALID,
            f"forge: {verb} refused — committed target manifest is invalid",
            observed=str(exc),
            chain=state,
        ) from exc
    observed_target = {
        "remote": "origin",
        "destination_ref": f"refs/heads/{default_branch}",
        "manifest_commit": manifest_commit,
    }
    if observed_target != dict(target) or not outputs["origin"].strip():
        raise chain_core._merge_refusal(
            V2ReasonCode.PUSH_TARGET_INVALID,
            f"forge: {verb} refused — fixed merge target changed",
            expected=chain_core.canonical_bytes(dict(target)).decode("utf-8"),
            observed=chain_core.canonical_bytes(observed_target).decode("utf-8"),
            chain=state,
        )
    try:
        policy = parse_policy(expected_head, outputs["policy"])
    except (PolicyError, UnicodeError) as exc:
        raise chain_core._merge_refusal(
            V2ReasonCode.POLICY_UNREADABLE,
            f"forge: {verb} refused — committed candidate policy is unreadable: {exc}",
            observed=str(exc),
            chain=state,
        ) from exc
    if outputs["tip"] != f"{remote_tip}\n".encode("ascii"):
        raise chain_core._merge_refusal(
            V2ReasonCode.FETCH_FAILED,
            f"forge: {verb} refused — fetched target tip is invalid",
            expected=remote_tip,
            observed=outputs["tip"].decode("ascii", "replace").strip(),
            chain=state,
        )
    try:
        changed_paths = tuple(
            sorted(
                {
                    item.decode("utf-8")
                    for item in outputs["names"].split(b"\0")
                    if item
                },
                key=lambda path: path.encode("utf-8"),
            )
        )
    except UnicodeDecodeError as exc:
        raise chain_core._merge_refusal(
            V2ReasonCode.WORKTREE_INVALID,
            f"forge: {verb} refused — candidate paths are not UTF-8",
            observed=str(exc),
            chain=state,
        ) from exc
    if require_current_generation:
        candidate = state.get("candidate")
        policy_source = state.get("policy_source")
        if not isinstance(candidate, Mapping) or not isinstance(
            policy_source, Mapping
        ):
            raise FrozenError(
                "merge candidate tuple is unavailable",
                chain_id=str(state.get("chain_id", "")) or None,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
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
        preimage = {
            "remote": "origin",
            "destination_ref": str(target["destination_ref"]),
            "remote_tip": remote_tip,
            "candidate_head": expected_head,
            "diff_sha256": sha256_bytes(outputs["diff"]),
            "policy_commit": policy.sha,
            "policy_digest": policy.digest,
            "worktree_identity": observed_identity,
            "generation": candidate.get("generation"),
        }
        observed_candidate = {
            **preimage,
            "generation_digest": sha256_bytes(chain_core.canonical_bytes(preimage)),
        }
        if observed_candidate != dict(candidate):
            raise chain_core._merge_refusal(
                V2ReasonCode.CANDIDATE_STALE,
                f"forge: {verb} refused — merge generation tuple is stale",
                expected=str(candidate.get("generation_digest")),
                observed=observed_candidate["generation_digest"],
                chain=state,
            )
    return (
        chain_core.Repository(Path(expected_identity["path"])),
        policy,
        changed_paths,
        outputs["diff"],
        outputs.get("classifier"),
    )
