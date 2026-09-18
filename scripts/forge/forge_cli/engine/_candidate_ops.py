"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
from typing import Any, MutableMapping, Mapping, Sequence
from forge_cli.engine._classification import _run_classification as _run_classification
from forge_cli.engine._core import _transition_state as _transition_state, _write_artifact as _write_artifact, _read_bound_artifact as _read_bound_artifact
from pathlib import Path
from forge_cli import candidate as candidate_module, chain_core
from forge_cli.envelope import ReasonCode, Refusal, FrozenError, V2ReasonCode


def _invalidate_candidate_evidence(
    state: MutableMapping[str, Any],
    *,
    preserve_diff_scoped: bool = False,
    preserve_operator_cosign: bool = False,
) -> None:
    preserved: dict[str, Any] = {}
    if preserve_diff_scoped:
        for key in ("secret-scan",):
            if key in state["steps"]:
                preserved[key] = state["steps"][key]
    state["steps"] = preserved
    operator_cosign = bool(state["review"].get("operator_cosign_required"))
    state["review"]["request"] = None
    state["review"]["verdict"] = None
    state["review"]["dispositions"] = []
    state["review"]["operator_cosign_required"] = (
        operator_cosign if preserve_operator_cosign else False
    )
    state["approval"] = {}
    state["authorization"] = {}
    state["commit_result"] = {}


def _candidate_patch_ref(state: Mapping[str, Any]) -> str:
    record = state.get("candidate")
    if not isinstance(record, Mapping):
        return ""
    authorization_id = record.get("authorization_id")
    review_digest = record.get("review_diff_sha256")
    if not isinstance(authorization_id, str) or not isinstance(review_digest, str):
        return ""
    return (
        Path(".forge")
        / "chains"
        / str(state["chain_id"])
        / "candidate"
        / f"{authorization_id}-{review_digest}.patch"
    ).as_posix()


def _candidate_snapshot(
    ctx: chain_core.CommandContext, state: Mapping[str, Any]
) -> candidate_module.CandidateSnapshot:
    try:
        return ctx.repo.candidate_snapshot(computed_at=chain_core.iso_z())
    except candidate_module.CandidateError as exc:
        reason = (
            ReasonCode.STATE_PRECONDITION
            if exc.kind == "state-precondition"
            else ReasonCode.EVIDENCE_INCOMPLETE
        )
        raise Refusal(
            reason,
            f"candidate snapshot could not be completed: {exc}",
            expected="a complete bounded Git-tree candidate snapshot",
            observed=str(exc),
            remediation=chain_core._forge_command(
                state, "commit restage --paths <path>..."
            ),
            chain=state,
        ) from exc


def _install_candidate_snapshot(
    ctx: chain_core.CommandContext,
    state: MutableMapping[str, Any],
    snapshot: candidate_module.CandidateSnapshot,
) -> None:
    if state.get("run_binding") is not None:
        invalid_paths = [
            path
            for path in snapshot.paths
            if not candidate_module.valid_scope_path(path)
        ]
        if invalid_paths:
            raise Refusal(
                V2ReasonCode.RUN_TASK_BINDING_INVALID,
                "forge: commit start refused — run/task binding is invalid",
                expected=(
                    "every concrete candidate path satisfies the committed "
                    "run-scope pathname contract"
                ),
                observed=", ".join(repr(path) for path in invalid_paths),
                remediation="inspect the named run/task and retry the exact paired start",
                chain=state,
            )
    state["candidate"] = snapshot.state_record()
    state["paths"] = list(snapshot.paths)
    state["staging"]["staged_paths"] = list(snapshot.paths)
    relative = (
        Path("candidate")
        / f"{snapshot.authorization_id}-{snapshot.review_diff_sha256}.patch"
    ).as_posix()
    expected_ref = (
        Path(".forge") / "chains" / str(state["chain_id"]) / relative
    ).as_posix()
    try:
        _write_artifact(ctx, state, relative, snapshot.review_diff, exclusive=True)
    except FileExistsError:
        existing = _read_bound_artifact(
            ctx,
            state,
            expected_ref,
            snapshot.review_diff_sha256,
            "candidate review patch",
            max_bytes=candidate_module.REVIEW_DIFF_MAX_BYTES,
        )
        if existing != snapshot.review_diff:
            raise FrozenError(
                "candidate review patch identity collision",
                chain_id=str(state["chain_id"]),
                state=str(state["state"]),
            )


def _candidate_review_diff(
    ctx: chain_core.CommandContext, state: Mapping[str, Any]
) -> bytes:
    record = state.get("candidate")
    reference = _candidate_patch_ref(state)
    if not chain_core.candidate_is_v2(state) or not reference:
        raise Refusal(
            ReasonCode.STATE_PRECONDITION,
            "legacy candidate must be restaged before evidence can advance",
            expected=candidate_module.CANDIDATE_SCHEMA,
            observed=str(record.get("schema") if isinstance(record, Mapping) else None),
            remediation=chain_core._forge_command(
                state, "commit restage --paths <path>..."
            ),
            chain=state,
        )
    assert isinstance(record, Mapping)
    data = _read_bound_artifact(
        ctx,
        state,
        reference,
        str(record["review_diff_sha256"]),
        "candidate review patch",
        max_bytes=candidate_module.REVIEW_DIFF_MAX_BYTES,
    )
    if len(data) != record.get("review_diff_byte_count"):
        raise Refusal(
            ReasonCode.EVIDENCE_INCOMPLETE,
            "candidate review patch byte count changed",
            expected=str(record.get("review_diff_byte_count")),
            observed=str(len(data)),
            remediation=chain_core._forge_command(state, "commit restage --paths <path>..."),
            chain=state,
            evidence_refs=[reference],
        )
    return data


def _adopt_out_of_band_candidate(
    ctx: chain_core.CommandContext,
    state: MutableMapping[str, Any],
    observed_candidate: str,
    *,
    detected_by: str,
) -> tuple[str, bool]:
    """Adopt the complete staged set, invalidate evidence, and reclassify."""
    old_candidate = str(state["candidate"].get("sha256") or "")
    old_paths = list(state.get("paths", []))
    snapshot = _candidate_snapshot(ctx, state)
    if snapshot.authorization_id != observed_candidate:
        raise FrozenError(
            "candidate changed during out-of-band adoption",
            chain_id=str(state["chain_id"]),
            state=str(state["state"]),
        )
    _install_candidate_snapshot(ctx, state, snapshot)
    staged_paths = list(snapshot.paths)
    anomaly = {
        "at": chain_core.iso_z(),
        "kind": "out-of-band-index-change",
        "old_candidate": old_candidate,
        "new_candidate": observed_candidate,
        "old_paths": old_paths,
        "new_paths": list(staged_paths),
        "detected_by": detected_by,
    }
    state["staging"]["anomalies"].append(anomaly)
    _invalidate_candidate_evidence(state, preserve_operator_cosign=True)
    _transition_state(state, "classifying")
    ctx.store.persist(
        state,
        "candidate_invalidated",
        {
            "old_candidate": old_candidate,
            "new_candidate": observed_candidate,
            "old_paths": old_paths,
            "new_paths": list(staged_paths),
            "out_of_band": True,
            "detected_by": detected_by,
        },
    )
    has_candidate_bytes = bool(snapshot.paths)
    if has_candidate_bytes:
        _run_classification(ctx, state)
    return old_candidate, has_candidate_bytes


def _stage_paths(
    ctx: chain_core.CommandContext,
    state: MutableMapping[str, Any],
    paths: Sequence[str],
    *,
    clear_old: bool,
) -> tuple[str | None, str]:
    old_candidate = state["candidate"].get("sha256")
    if clear_old:
        staged_before = ctx.repo.staged_paths()
        if staged_before:
            ctx.repo.git(["reset", "-q", "HEAD", "--", *staged_before])
    ctx.repo.git(["add", "--", *paths])
    snapshot = _candidate_snapshot(ctx, state)
    if not snapshot.paths:
        raise Refusal(
            ReasonCode.STATE_PRECONDITION,
            "staging produced an empty candidate",
            expected="nonempty git diff --cached",
            observed="empty staged diff",
            remediation="edit the named paths before starting/restaging",
            chain=state,
        )
    if snapshot.base_commit_oid != state.get("repo_head"):
        raise Refusal(
            ReasonCode.HEAD_MOVED,
            "candidate base changed while staging",
            expected=str(state.get("repo_head")),
            observed=str(snapshot.base_commit_oid),
            remediation=chain_core._forge_command(state, "commit rebase"),
            chain=state,
        )
    _install_candidate_snapshot(ctx, state, snapshot)
    state["staging"]["staged_at"] = chain_core.iso_z()
    return (
        str(old_candidate) if old_candidate else None,
        snapshot.authorization_id,
    )
