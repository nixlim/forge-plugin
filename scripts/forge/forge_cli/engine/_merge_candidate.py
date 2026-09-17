"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
from typing import Any, Mapping
from forge_cli import chain_core
from forge_cli.engine._cli_options import _message_from_args as _message_from_args, _validate_revision9_cross_options as _validate_revision9_cross_options, render as render
from forge_cli.engine._core import commit_message_bytes as commit_message_bytes, chain_id_now as chain_id_now, promoted_tier as promoted_tier, _transition_state as _transition_state, _require_merge_lifecycle_control as _require_merge_lifecycle_control, inspect_common_lock as inspect_common_lock, _archive_refusal as _archive_refusal, _archive_contamination_refusal as _archive_contamination_refusal, _archive_metadata as _archive_metadata, _env_fingerprint as _env_fingerprint, _evidence_record as _evidence_record, _write_artifact as _write_artifact, _read_bound_artifact as _read_bound_artifact, _record_process_step as _record_process_step, _run_halt as _run_halt, MergeAdmission as MergeAdmission, MergeScopeResult as MergeScopeResult, MergeCandidateGeneration as MergeCandidateGeneration, MergeBootstrapClassification as MergeBootstrapClassification
from forge_cli.engine._parser import ContractArgumentParser as ContractArgumentParser, _extract_global_options as _extract_global_options, _attach_merge_lifecycle_parser as _attach_merge_lifecycle_parser, build_parser as build_parser, _raw_top_level_command as _raw_top_level_command
from forge_cli.engine._state import TERMINAL_STATES as TERMINAL_STATES, TERMINAL_TOUCH_VERBS as TERMINAL_TOUCH_VERBS, STATE_TRANSITIONS as STATE_TRANSITIONS, TOKEN_TTL_SECONDS as TOKEN_TTL_SECONDS, _REQUIRED_MERGE_LIFECYCLE_CONTROLS as _REQUIRED_MERGE_LIFECYCLE_CONTROLS, MERGE_LIFECYCLE_CONTROLS as MERGE_LIFECYCLE_CONTROLS, _REQUIRED_ARCHIVE_RECHECK_CONTROLS as _REQUIRED_ARCHIVE_RECHECK_CONTROLS, ARCHIVE_RECHECK_CONTROLS as ARCHIVE_RECHECK_CONTROLS, _CHAIN_CAPABILITY_LOCK as _CHAIN_CAPABILITY_LOCK, _CHAIN_CAPABILITIES as _CHAIN_CAPABILITIES, CODEX_EXECUTABLE as CODEX_EXECUTABLE, FRESH_REVIEWER_EVAL_REQUEST_SCHEMA as FRESH_REVIEWER_EVAL_REQUEST_SCHEMA, REVIEW_DIRECT_PACKAGE_MAX_BYTES as REVIEW_DIRECT_PACKAGE_MAX_BYTES, REVIEW_MASTER_WINDOW_BYTES as REVIEW_MASTER_WINDOW_BYTES, REVIEW_COMPLETE_PACKAGE_REFUSAL as REVIEW_COMPLETE_PACKAGE_REFUSAL, PRODUCED_COMMIT_MISMATCH as PRODUCED_COMMIT_MISMATCH, REVIEW_INSTRUCTION as REVIEW_INSTRUCTION, REVIEW_LAUNCHER_CODE as REVIEW_LAUNCHER_CODE, GLOBAL_OPTIONS_HELP as GLOBAL_OPTIONS_HELP, ARCHIVE_CONTAMINATION as ARCHIVE_CONTAMINATION, SECRET_RULES as SECRET_RULES, PLACEHOLDER_RE as PLACEHOLDER_RE, ABORT_DISPOSITION_PRECONDITIONS as ABORT_DISPOSITION_PRECONDITIONS, _MERGE_CANDIDATE_IDENTITY_FIELDS as _MERGE_CANDIDATE_IDENTITY_FIELDS, _MERGE_BOOTSTRAP_CHILD_SOURCE as _MERGE_BOOTSTRAP_CHILD_SOURCE, _DERIVE_MERGE_SCOPE as _DERIVE_MERGE_SCOPE, _MERGE_INITIAL_INTEGRATION as _MERGE_INITIAL_INTEGRATION
import copy
from forge_cli.policy import sha256_bytes
from pathlib import Path
from forge_cli.envelope import FrozenError, REVISION9_OUTPUT_SCHEMA, V2ReasonCode


def _reset_merge_nonmovement_counter(integration: dict[str, Any]) -> None:
    """End a non-remote-only epoch without retaining a churn streak."""

    chain_core._require_merge_integration_control("nonmovement-counter-reset")
    integration["remote_movement_count"] = 0


def _materialize_merge_candidate_tuple(
    admission: MergeAdmission,
    remote_tip: str,
    *,
    generation: int,
    diff_output_digest: str,
) -> dict[str, Any]:
    """Construct DM-014's complete immutable generation without a subprocess."""

    if (
        chain_core.COMMIT_RE.fullmatch(remote_tip) is None
        or not chain_core._valid_positive_int(generation)
        or chain_core.SHA256_RE.fullmatch(diff_output_digest) is None
    ):
        raise ValueError("merge candidate tuple inputs are malformed")
    preimage: dict[str, Any] = {
        "remote": "origin",
        "destination_ref": admission.target["destination_ref"],
        "remote_tip": remote_tip,
        "candidate_head": admission.candidate_head,
        "diff_sha256": diff_output_digest,
        "policy_commit": admission.candidate_head,
        "policy_digest": admission.policy.digest,
        "worktree_identity": copy.deepcopy(admission.worktree_identity),
        "generation": generation,
    }
    return {
        **preimage,
        "generation_digest": sha256_bytes(chain_core.canonical_bytes(preimage)),
    }


def _retain_or_advance_merge_candidate(
    admission: MergeAdmission,
    remote_tip: str,
    *,
    prior_candidate: object,
    generation: int,
    diff_output_digest: str,
) -> dict[str, Any]:
    """Retain an identical generation or materialize its exact successor."""

    proposed = _materialize_merge_candidate_tuple(
        admission,
        remote_tip,
        generation=generation,
        diff_output_digest=diff_output_digest,
    )
    if isinstance(prior_candidate, Mapping) and all(
        prior_candidate.get(name) == proposed.get(name)
        for name in _MERGE_CANDIDATE_IDENTITY_FIELDS
    ):
        return copy.deepcopy(dict(prior_candidate))
    return proposed


def _merge_scope_request(admission: MergeAdmission) -> dict[str, Any] | None:
    snapshot = admission.run_task
    if snapshot is None:
        return None
    template = {
        "schema": "forge-run-scope-command-template/1",
        "worktree": str(admission.worktree),
        "candidate_head": admission.candidate_head,
        "remote_tip_source": "scope_fetch_binding.remote_tip",
    }
    return {
        "run_id": snapshot.binding["run_id"],
        "task_id": snapshot.binding["task_id"],
        "task_files": list(snapshot.task_files),
        "admitted_scope": list(snapshot.admitted_scope),
        "command_template": template,
        "command_template_digest": sha256_bytes(chain_core.canonical_bytes(template)),
        "environment_digest": sha256_bytes(
            chain_core.canonical_bytes(chain_core._merge_scope_environment_contract())
        ),
    }


def _merge_scope_proof(
    admission: MergeAdmission,
    candidate: Mapping[str, Any],
    scope: MergeScopeResult,
    binding: Mapping[str, Any],
) -> dict[str, Any]:
    snapshot = admission.run_task
    if snapshot is None:
        raise ValueError("scope proof requires an immutable run/task snapshot")
    body = {
        "schema": "forge-run-scope-proof/1",
        "run_id": snapshot.binding["run_id"],
        "task_id": snapshot.binding["task_id"],
        "generation_digest": candidate["generation_digest"],
        "remote_tip": candidate["remote_tip"],
        "candidate_head": candidate["candidate_head"],
        "command_template_digest": binding["command_template_digest"],
        "command_digest": binding["command_digest"],
        "environment_digest": binding["environment_digest"],
        "scope_fetch_binding_digest": binding["digest"],
        "output_digest": scope.output_digest,
        "task_files": list(snapshot.task_files),
        "admitted_scope": list(snapshot.admitted_scope),
        "changed_paths": list(scope.changed_paths),
        "out_of_scope_paths": list(scope.out_of_scope_paths),
        "result": scope.result,
    }
    return {**body, "digest": sha256_bytes(chain_core.canonical_bytes(body))}


def _merge_released_predecessor(
    store: chain_core.MergeChainStore,
    claim_path: Path,
    worktree_identity: Mapping[str, Any],
) -> tuple[str | None, str | None]:
    """Authenticate the complete causal ownership line and select its tail.

    Wall-clock order is not ownership authority.  Every acquired claimant is
    instead linked to the immediately preceding released claimant by the
    immutable event digests recorded in the ownership intent.
    """

    expected_identity = {
        name: str(worktree_identity[name])
        for name in ("path", "git_dir", "common_dir")
    }
    summaries: dict[str, dict[str, Any]] = {}
    for chain_id in store.list_ids(family="merge"):
        with store.event_lock(chain_id):
            try:
                replay = store._read_replay_locked(chain_id)
            except FrozenError as exc:
                # Event one remains the authenticated family/identity router.
                # A corrupt unrelated tail must not become a repository-wide
                # denial of service, while a corrupt same-slot tail freezes.
                raw = store._read_root_bytes(store.events_path(chain_id).name)
                first = raw.splitlines(keepends=True)[0] if raw else b""
                opening = chain_core._replay_merge_event_bytes(chain_id, first)
                opening_worktree = opening.state.get("worktree")
                opening_identity = (
                    {
                        name: opening_worktree.get(name)
                        for name in ("path", "git_dir", "common_dir")
                    }
                    if isinstance(opening_worktree, Mapping)
                    else None
                )
                if opening_identity == expected_identity:
                    raise exc
                continue
        state = replay.state
        identity = state.get("worktree")
        if not isinstance(identity, Mapping) or {
            name: identity.get(name)
            for name in ("path", "git_dir", "common_dir")
        } != expected_identity:
            continue
        with store.event_lock(chain_id):
            replay = store._read_replay_locked(chain_id)
            store._projection_status(replay)
        state = replay.state
        identity = state["worktree"]

        claim = identity.get("claim")
        if not isinstance(claim, Mapping) or claim.get("path") != str(claim_path):
            raise FrozenError(
                "merge ownership lineage has a noncanonical claim path",
                chain_id=chain_id,
                observed=str(claim.get("path") if isinstance(claim, Mapping) else None),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        intent = next(
            (
                event
                for event in replay.events
                if event.get("event") == "ownership_intent"
            ),
            None,
        )
        if not isinstance(intent, Mapping) or not isinstance(
            intent.get("payload"), Mapping
        ):
            raise FrozenError(
                "merge ownership lineage lacks an authenticated intent",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        claimed = next(
            (
                event
                for event in replay.events
                if event.get("event") == "ownership_claimed"
            ),
            None,
        )
        released = next(
            (
                event
                for event in reversed(replay.events)
                if event.get("event") == "ownership_released"
                and isinstance(event.get("payload"), Mapping)
                and event["payload"].get("release_mode") == "acquired"
            ),
            None,
        )
        terminal = state.get("state") in {"closed", "aborted"}
        claim_status = claim.get("status")
        if claimed is None:
            if not terminal or claim_status != "released":
                raise chain_core._merge_refusal(
                    V2ReasonCode.LIVE_MERGE_CHAIN_EXISTS,
                    "forge: merge start refused — selected worktree already has a live merge owner",
                    expected="an unowned registered worktree",
                    observed=chain_id,
                    remediation=f"forge status --chain-id {chain_id}",
                    chain=state,
                )
            # A never-published terminal release never became a lineage node.
            continue
        if not terminal:
            if claim_status == "released":
                raise chain_core._merge_refusal(
                    V2ReasonCode.STATE_PRECONDITION,
                    "forge: merge start refused — ownership release completion is pending",
                    expected="the cutoff-selected terminal event",
                    observed=chain_id,
                    remediation=f"forge merge recover --chain-id {chain_id}",
                    chain=state,
                )
            raise chain_core._merge_refusal(
                V2ReasonCode.LIVE_MERGE_CHAIN_EXISTS,
                "forge: merge start refused — selected worktree already has a live merge owner",
                expected="an unowned registered worktree",
                observed=chain_id,
                remediation=f"forge status --chain-id {chain_id}",
                chain=state,
            )
        if claim_status != "released" or not isinstance(released, Mapping):
            raise FrozenError(
                "terminal acquired merge ownership is not durably released",
                chain_id=chain_id,
                observed=str(claim_status),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        payload = intent["payload"]
        summaries[chain_id] = {
            "predecessor_chain_id": payload.get("predecessor_chain_id"),
            "predecessor_release_digest": payload.get(
                "predecessor_release_digest"
            ),
            "released_digest": released.get("digest"),
        }

    if not summaries:
        return None, None

    children: dict[tuple[Any, Any], list[str]] = {}
    referenced: set[str] = set()
    roots: list[str] = []
    for chain_id, summary in summaries.items():
        predecessor_id = summary["predecessor_chain_id"]
        predecessor_digest = summary["predecessor_release_digest"]
        edge = (predecessor_id, predecessor_digest)
        children.setdefault(edge, []).append(chain_id)
        if predecessor_id is None:
            if predecessor_digest is not None:
                raise FrozenError(
                    "merge ownership lineage has a partial root edge",
                    chain_id=chain_id,
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            roots.append(chain_id)
            continue
        predecessor = summaries.get(str(predecessor_id))
        if (
            predecessor is None
            or predecessor.get("released_digest") != predecessor_digest
        ):
            raise FrozenError(
                "merge ownership lineage has a missing predecessor edge",
                chain_id=chain_id,
                observed=str(predecessor_id),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        referenced.add(str(predecessor_id))
    if len(roots) != 1 or any(len(values) != 1 for values in children.values()):
        raise FrozenError(
            "merge ownership lineage is forked",
            observed=",".join(sorted(summaries)),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    tails = [chain_id for chain_id in summaries if chain_id not in referenced]
    if len(tails) != 1:
        raise FrozenError(
            "merge ownership lineage is cyclic or has no unique tail",
            observed=",".join(sorted(summaries)),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    cursor: str | None = tails[0]
    visited: set[str] = set()
    while cursor is not None:
        if cursor in visited or len(visited) >= len(summaries):
            raise FrozenError(
                "merge ownership lineage contains a cycle",
                chain_id=cursor,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        visited.add(cursor)
        predecessor = summaries[cursor]["predecessor_chain_id"]
        cursor = str(predecessor) if predecessor is not None else None
    if len(visited) != len(summaries):
        raise FrozenError(
            "merge ownership lineage is disconnected",
            observed=",".join(sorted(summaries)),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    tail_id = tails[0]
    tail_digest = str(summaries[tail_id]["released_digest"])
    if chain_core.SHA256_RE.fullmatch(tail_digest) is None:
        raise FrozenError(
            "merge ownership lineage tail digest is invalid",
            chain_id=tail_id,
            observed=tail_digest,
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    return tail_id, tail_digest


def _resolve_recorded_merge_tip(
    admission: MergeAdmission, *, verb: str
) -> str:
    destination = admission.target["destination_ref"]
    branch = destination.removeprefix("refs/heads/")
    tracking = f"refs/remotes/origin/{branch}"
    repository = chain_core.Repository(admission.worktree)
    result = repository.git(
        ["rev-parse", "--verify", f"{tracking}^{{commit}}"], check=False
    )
    try:
        value = result.stdout.decode("ascii").strip()
    except UnicodeDecodeError:
        value = ""
    if result.returncode != 0 or chain_core.COMMIT_RE.fullmatch(value) is None:
        raise chain_core._merge_refusal(
            V2ReasonCode.FETCH_FAILED,
            f"forge: {verb} refused — fixed target tip is unavailable",
            expected=f"an already-fetched full commit at {tracking}",
            observed=(
                result.stderr.decode("utf-8", "replace").strip()
                or value
                or "missing tracking tip"
            ),
            remediation=f"forge merge {verb.split()[-1]} --chain-id <id>",
        )
    return value
