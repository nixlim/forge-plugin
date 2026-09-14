"""Extracted from scripts/forge/forge_cli/chain_core/__init__.py."""
from __future__ import annotations
from pathlib import Path
from typing import Mapping, Any
from forge_cli import runtime
from forge_cli.chain_core._controls import COMMON_LOCK_OWNER_KINDS as COMMON_LOCK_OWNER_KINDS, COMMON_LOCK_OPERATIONS as COMMON_LOCK_OPERATIONS, COMMON_LOCK_FENCE_OPERATIONS as COMMON_LOCK_FENCE_OPERATIONS, COMMON_LOCK_RECOVERY_KINDS as COMMON_LOCK_RECOVERY_KINDS, _COMMON_LOCK_OWNER_KEYS as _COMMON_LOCK_OWNER_KEYS, _COMMON_LOCK_FENCE_KEYS as _COMMON_LOCK_FENCE_KEYS, _COMMON_LOCK_RECOVERY_KEYS as _COMMON_LOCK_RECOVERY_KEYS, _CHAIN_LEASE_KEYS as _CHAIN_LEASE_KEYS, _REQUIRED_COMMON_LOCK_CONTROLS as _REQUIRED_COMMON_LOCK_CONTROLS, COMMON_LOCK_CONTROLS as COMMON_LOCK_CONTROLS, CHAIN_TOMBSTONE_SCHEMA as CHAIN_TOMBSTONE_SCHEMA, CHAIN_TOMBSTONE_EVENT as CHAIN_TOMBSTONE_EVENT, CHAIN_TOMBSTONE_KEYS as CHAIN_TOMBSTONE_KEYS, _REQUIRED_MERGE_STORE_CONTROLS as _REQUIRED_MERGE_STORE_CONTROLS, MERGE_STORE_CONTROLS as MERGE_STORE_CONTROLS, _REQUIRED_MERGE_ADAPTER_CONTROLS as _REQUIRED_MERGE_ADAPTER_CONTROLS, MERGE_ADAPTER_CONTROLS as MERGE_ADAPTER_CONTROLS, _REQUIRED_MERGE_INTEGRATION_CONTROLS as _REQUIRED_MERGE_INTEGRATION_CONTROLS, MERGE_INTEGRATION_CONTROLS as MERGE_INTEGRATION_CONTROLS, INGEST_PROOF_ORDER as INGEST_PROOF_ORDER, _REQUIRED_INGEST_PROOF_CONTROLS as _REQUIRED_INGEST_PROOF_CONTROLS, INGEST_PROOF_CONTROLS as INGEST_PROOF_CONTROLS, _MERGE_CLEANUP_INTENT_SCHEMA as _MERGE_CLEANUP_INTENT_SCHEMA, _MERGE_CLEANUP_RESULT_SCHEMA as _MERGE_CLEANUP_RESULT_SCHEMA, _MERGE_CLEANUP_CLOSE_SCHEMA as _MERGE_CLEANUP_CLOSE_SCHEMA, _MERGE_CLEANUP_RECOVERY_SCHEMA as _MERGE_CLEANUP_RECOVERY_SCHEMA, _MERGE_CLEANUP_FENCE_OPERATIONS as _MERGE_CLEANUP_FENCE_OPERATIONS, _EPOCH_FETCH_OBSERVATION_SCHEMA as _EPOCH_FETCH_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA, _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA as _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA
from forge_cli.chain_core._core import canonical_bytes as canonical_bytes, _chain_storage_root as _chain_storage_root, _validated_commitment_path as _validated_commitment_path, _parsed_run_captured_path as _parsed_run_captured_path, _require_ingest_proof as _require_ingest_proof, iso_z as iso_z, parse_time as parse_time, _require_merge_store_control as _require_merge_store_control, _require_merge_adapter_control as _require_merge_adapter_control, _require_merge_integration_control as _require_merge_integration_control, _require_common_lock_control as _require_common_lock_control, CommonLockBoundaryCrash as CommonLockBoundaryCrash, PublishedLockRecord as PublishedLockRecord, CommonLockInspection as CommonLockInspection, CommonLockUnavailable as CommonLockUnavailable, CommonLockReleaseFailure as CommonLockReleaseFailure, ChainLeaseUnavailable as ChainLeaseUnavailable, FencedChildSurvived as FencedChildSurvived, _valid_utc_second as _valid_utc_second, _valid_positive_int as _valid_positive_int, _valid_nonnegative_int as _valid_nonnegative_int, _valid_host as _valid_host, _valid_nonce as _valid_nonce, _valid_nullable_chain as _valid_nullable_chain, _write_all as _write_all, _PublicationCleanupFailure as _PublicationCleanupFailure, _process_probe as _process_probe, _group_probe as _group_probe, _sleep_with_deadline as _sleep_with_deadline, _require_deadline_open as _require_deadline_open, FencedProcessResult as FencedProcessResult, merge_gate_intent_digest as merge_gate_intent_digest, _forge_command as _forge_command, MergeRunTaskSnapshot as MergeRunTaskSnapshot, _merge_refusal as _merge_refusal, _valid_sorted_unique_strings as _valid_sorted_unique_strings
from forge_cli.chain_core._state import SCHEMA as SCHEMA, KIND as KIND, FRESH_REVIEWER_EVALS_GATE as FRESH_REVIEWER_EVALS_GATE, FRESH_REVIEWER_EVALS_REQUESTS as FRESH_REVIEWER_EVALS_REQUESTS, FRESH_REVIEWER_EVALS_REQUESTED_EVENT as FRESH_REVIEWER_EVALS_REQUESTED_EVENT, STATES as STATES, STATE_KEYS as STATE_KEYS, EVENT_KEYS as EVENT_KEYS, MERGE_STATE_KEYS as MERGE_STATE_KEYS, _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES as _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES, _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES as _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES, MERGE_EVENT_KEYS as MERGE_EVENT_KEYS, MERGE_EVENT_NAMES as MERGE_EVENT_NAMES, MERGE_CONSEQUENTIAL_EVENTS as MERGE_CONSEQUENTIAL_EVENTS, TIER_RANK as TIER_RANK, INACTIVE_SECONDS as INACTIVE_SECONDS, FENCED_CHILD_ACK_TIMEOUT_SECONDS as FENCED_CHILD_ACK_TIMEOUT_SECONDS, FENCED_CHILD_DRAIN_SECONDS as FENCED_CHILD_DRAIN_SECONDS, FENCED_CHILD_DRAIN_CAP_BYTES as FENCED_CHILD_DRAIN_CAP_BYTES, FENCED_CHILD_STOP_GRACE_SECONDS as FENCED_CHILD_STOP_GRACE_SECONDS, FENCED_CHILD_REAP_SECONDS as FENCED_CHILD_REAP_SECONDS, ZERO_DIGEST as ZERO_DIGEST, COMMON_LOCK_TIMEOUT_SECONDS as COMMON_LOCK_TIMEOUT_SECONDS, COMMON_LOCK_POLL_SECONDS as COMMON_LOCK_POLL_SECONDS, COMMON_LOCK_RECORD_CAP_BYTES as COMMON_LOCK_RECORD_CAP_BYTES, MERGE_SCOPE_BINDING_CAP_BYTES as MERGE_SCOPE_BINDING_CAP_BYTES, COMMON_LOCK_INTENT_NAME as COMMON_LOCK_INTENT_NAME, COMMON_LOCK_DIRECTORY_NAME as COMMON_LOCK_DIRECTORY_NAME, COMMON_LOCK_OWNER_NAME as COMMON_LOCK_OWNER_NAME, COMMON_LOCK_FLOCK_NAME as COMMON_LOCK_FLOCK_NAME, COMMON_LOCK_RECOVERY_NAME as COMMON_LOCK_RECOVERY_NAME, COMMON_LOCK_INFLIGHT_NAME as COMMON_LOCK_INFLIGHT_NAME, CHAIN_ID_RE as CHAIN_ID_RE, SHA256_RE as SHA256_RE, COMMIT_RE as COMMIT_RE, RUN_ID_RE as RUN_ID_RE, _WORKTREE_LOCKS_GUARD as _WORKTREE_LOCKS_GUARD, _WORKTREE_LOCKS as _WORKTREE_LOCKS, _WORKTREE_LOCK_STATE as _WORKTREE_LOCK_STATE, _exclusive_descriptor_lock as _exclusive_descriptor_lock, _MERGE_REMOTE_ONLY_IDENTITY_FIELDS as _MERGE_REMOTE_ONLY_IDENTITY_FIELDS, _MERGE_SCOPE_UNSET as _MERGE_SCOPE_UNSET, _MERGE_SCOPE_OVERLAY as _MERGE_SCOPE_OVERLAY
import json
import os


def _ingest_captured_paths(
    repository: Path,
    run_dir: Path,
    inputs: Mapping[str, object],
) -> dict[str, str]:
    """Derive the only citable paths from the request's captured digests."""

    _batch, builders, journal = runtime._coordination_modules()
    names = {
        "state_file": "state.json",
        "events_file": "events.jsonl",
        "outcome_map": "outcome-map.json",
    }
    result: dict[str, str] = {}
    for field, name in names.items():
        digest = inputs.get(f"{field}_sha256")
        if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
        path = run_dir / "captured" / "sha256" / digest / name
        try:
            capture_relative = path.relative_to(run_dir).as_posix()
        except ValueError as exc:
            raise journal.CoordinationRefusal(
                builders.INGEST_PROOF_INVALID
            ) from exc
        if _validated_commitment_path(
            "ingest.captured_package",
            capture_relative,
            repository=repository,
            run_dir=run_dir,
            direct_parent=path.parent,
            require_file=True,
        ) is None or _parsed_run_captured_path(
            capture_relative, run_dir.name
        ) is None:
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
        result[field] = capture_relative
    return result


def _ingest_step_is_current(
    final_state: Mapping[str, Any],
    event_state: Mapping[str, Any],
    details: Mapping[str, Any],
) -> bool:
    step_id = details.get("step_id")
    run_number = details.get("run")
    if (
        not isinstance(step_id, str)
        or step_id
        in {"classification", "fast-eligibility", "fast-finalize-eligibility"}
        or type(run_number) is not int
        or run_number <= 0
    ):
        return False
    final_runs = final_state.get("steps", {}).get(step_id)
    event_runs = event_state.get("steps", {}).get(step_id)
    index = run_number - 1
    if (
        not isinstance(final_runs, list)
        or not isinstance(event_runs, list)
        or index >= len(final_runs)
        or index >= len(event_runs)
        or final_runs[index] != event_runs[index]
        or not isinstance(final_runs[index], dict)
        or final_runs[index].get("candidate")
        != final_state.get("candidate", {}).get("sha256")
    ):
        return False
    current = [
        position
        for position, fact in enumerate(final_runs)
        if isinstance(fact, dict)
        and fact.get("candidate") == final_state.get("candidate", {}).get("sha256")
    ]
    if not current:
        return False
    if step_id == "gate-1":
        active = set(current[-2:])
    elif step_id.startswith("stack:"):
        latest = final_runs[current[-1]]
        batch_id = latest.get("batch_id") if isinstance(latest, dict) else None
        active = {
            position
            for position in current
            if isinstance(final_runs[position], dict)
            and final_runs[position].get("batch_id") == batch_id
        }
    else:
        active = {current[-1]}
    return index in active


def _ingest_secret_scan_is_current(
    final_state: Mapping[str, Any],
    event: dict[str, object],
    prior_state: dict[str, object] | None,
    event_state: dict[str, object],
) -> bool:
    """Select only the exact latest current-candidate secret-scan append."""

    _batch, builders, _journal = runtime._coordination_modules()
    introduced = builders._commit_secret_scan_delta(
        event, prior_state, event_state
    )
    final_steps = final_state.get("steps")
    final_runs = (
        final_steps.get("secret-scan")
        if isinstance(final_steps, Mapping)
        else None
    )
    candidate = final_state.get("candidate")
    candidate_sha = (
        candidate.get("sha256") if isinstance(candidate, Mapping) else None
    )
    if (
        introduced is None
        or not isinstance(final_runs, list)
        or introduced[0] >= len(final_runs)
        or final_runs[introduced[0]] != introduced[1]
        or introduced[1].get("candidate") != candidate_sha
    ):
        return False
    current = [
        index
        for index, fact in enumerate(final_runs)
        if isinstance(fact, Mapping) and fact.get("candidate") == candidate_sha
    ]
    return bool(current and introduced[0] == current[-1])


def _prove_ingest_live_chain(
    repository: Path,
    chain_id: str,
    materialized: dict[str, object],
    captured_state: bytes,
    captured_events: bytes,
) -> None:
    """Bind captured bytes to the stable live chain without consuming grammar."""

    _batch, builders, journal = runtime._coordination_modules()
    chains_root = _chain_storage_root(repository)
    descriptor: int | None = None
    try:
        descriptor, observation = journal._open_bound_directory(chains_root)
        with builders._chain_event_lock(
            chains_root,
            chain_id,
            root_descriptor=descriptor,
            root_observation=observation,
        ):
            live_state_bytes = builders._read_regular_bytes_at(
                descriptor, f"{chain_id}.json"
            )
            live_events = builders._read_regular_bytes_at(
                descriptor, f"{chain_id}.events.jsonl"
            )
            try:
                live_state = json.loads(live_state_bytes.decode("utf-8"))
            except (UnicodeError, ValueError, RecursionError) as exc:
                raise journal.CoordinationRefusal(
                    builders.INGEST_PROOF_INVALID
                ) from exc
            if (
                live_state_bytes != captured_state
                or live_events != captured_events
                or live_state != materialized
            ):
                raise journal.CoordinationRefusal(
                    builders.INGEST_PROOF_INVALID
                )
            if (
                journal._file_observation(os.fstat(descriptor))
                != observation
                or journal._file_observation(os.lstat(chains_root))
                != observation
            ):
                raise journal.CoordinationRefusal(
                    builders.INGEST_PROOF_INVALID
                )
    except journal.CoordinationRefusal as exc:
        if str(exc) == builders.INGEST_PROOF_INVALID:
            raise
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID) from exc
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
