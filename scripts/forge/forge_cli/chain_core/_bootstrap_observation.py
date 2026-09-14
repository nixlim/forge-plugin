"""Extracted from scripts/forge/forge_cli/chain_core/__init__.py."""
from __future__ import annotations
from typing import Any, Mapping
from forge_cli.chain_core._controls import COMMON_LOCK_OWNER_KINDS as COMMON_LOCK_OWNER_KINDS, COMMON_LOCK_OPERATIONS as COMMON_LOCK_OPERATIONS, COMMON_LOCK_FENCE_OPERATIONS as COMMON_LOCK_FENCE_OPERATIONS, COMMON_LOCK_RECOVERY_KINDS as COMMON_LOCK_RECOVERY_KINDS, _COMMON_LOCK_OWNER_KEYS as _COMMON_LOCK_OWNER_KEYS, _COMMON_LOCK_FENCE_KEYS as _COMMON_LOCK_FENCE_KEYS, _COMMON_LOCK_RECOVERY_KEYS as _COMMON_LOCK_RECOVERY_KEYS, _CHAIN_LEASE_KEYS as _CHAIN_LEASE_KEYS, _REQUIRED_COMMON_LOCK_CONTROLS as _REQUIRED_COMMON_LOCK_CONTROLS, COMMON_LOCK_CONTROLS as COMMON_LOCK_CONTROLS, CHAIN_TOMBSTONE_SCHEMA as CHAIN_TOMBSTONE_SCHEMA, CHAIN_TOMBSTONE_EVENT as CHAIN_TOMBSTONE_EVENT, CHAIN_TOMBSTONE_KEYS as CHAIN_TOMBSTONE_KEYS, _REQUIRED_MERGE_STORE_CONTROLS as _REQUIRED_MERGE_STORE_CONTROLS, MERGE_STORE_CONTROLS as MERGE_STORE_CONTROLS, _REQUIRED_MERGE_ADAPTER_CONTROLS as _REQUIRED_MERGE_ADAPTER_CONTROLS, MERGE_ADAPTER_CONTROLS as MERGE_ADAPTER_CONTROLS, _REQUIRED_MERGE_INTEGRATION_CONTROLS as _REQUIRED_MERGE_INTEGRATION_CONTROLS, MERGE_INTEGRATION_CONTROLS as MERGE_INTEGRATION_CONTROLS, INGEST_PROOF_ORDER as INGEST_PROOF_ORDER, _REQUIRED_INGEST_PROOF_CONTROLS as _REQUIRED_INGEST_PROOF_CONTROLS, INGEST_PROOF_CONTROLS as INGEST_PROOF_CONTROLS, _MERGE_CLEANUP_INTENT_SCHEMA as _MERGE_CLEANUP_INTENT_SCHEMA, _MERGE_CLEANUP_RESULT_SCHEMA as _MERGE_CLEANUP_RESULT_SCHEMA, _MERGE_CLEANUP_CLOSE_SCHEMA as _MERGE_CLEANUP_CLOSE_SCHEMA, _MERGE_CLEANUP_RECOVERY_SCHEMA as _MERGE_CLEANUP_RECOVERY_SCHEMA, _MERGE_CLEANUP_FENCE_OPERATIONS as _MERGE_CLEANUP_FENCE_OPERATIONS, _EPOCH_FETCH_OBSERVATION_SCHEMA as _EPOCH_FETCH_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA, _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA as _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA
from forge_cli.chain_core._core import canonical_bytes as canonical_bytes, _chain_storage_root as _chain_storage_root, _validated_commitment_path as _validated_commitment_path, _parsed_run_captured_path as _parsed_run_captured_path, _require_ingest_proof as _require_ingest_proof, iso_z as iso_z, parse_time as parse_time, _require_merge_store_control as _require_merge_store_control, _require_merge_adapter_control as _require_merge_adapter_control, _require_merge_integration_control as _require_merge_integration_control, _require_common_lock_control as _require_common_lock_control, CommonLockBoundaryCrash as CommonLockBoundaryCrash, PublishedLockRecord as PublishedLockRecord, CommonLockInspection as CommonLockInspection, CommonLockUnavailable as CommonLockUnavailable, CommonLockReleaseFailure as CommonLockReleaseFailure, ChainLeaseUnavailable as ChainLeaseUnavailable, FencedChildSurvived as FencedChildSurvived, _valid_utc_second as _valid_utc_second, _valid_positive_int as _valid_positive_int, _valid_nonnegative_int as _valid_nonnegative_int, _valid_host as _valid_host, _valid_nonce as _valid_nonce, _valid_nullable_chain as _valid_nullable_chain, _write_all as _write_all, _PublicationCleanupFailure as _PublicationCleanupFailure, _process_probe as _process_probe, _group_probe as _group_probe, _sleep_with_deadline as _sleep_with_deadline, _require_deadline_open as _require_deadline_open, FencedProcessResult as FencedProcessResult, merge_gate_intent_digest as merge_gate_intent_digest, _forge_command as _forge_command, MergeRunTaskSnapshot as MergeRunTaskSnapshot, _merge_refusal as _merge_refusal, _valid_sorted_unique_strings as _valid_sorted_unique_strings
from forge_cli.chain_core._state import SCHEMA as SCHEMA, KIND as KIND, FRESH_REVIEWER_EVALS_GATE as FRESH_REVIEWER_EVALS_GATE, FRESH_REVIEWER_EVALS_REQUESTS as FRESH_REVIEWER_EVALS_REQUESTS, FRESH_REVIEWER_EVALS_REQUESTED_EVENT as FRESH_REVIEWER_EVALS_REQUESTED_EVENT, STATES as STATES, STATE_KEYS as STATE_KEYS, EVENT_KEYS as EVENT_KEYS, MERGE_STATE_KEYS as MERGE_STATE_KEYS, _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES as _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES, _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES as _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES, MERGE_EVENT_KEYS as MERGE_EVENT_KEYS, MERGE_EVENT_NAMES as MERGE_EVENT_NAMES, MERGE_CONSEQUENTIAL_EVENTS as MERGE_CONSEQUENTIAL_EVENTS, TIER_RANK as TIER_RANK, INACTIVE_SECONDS as INACTIVE_SECONDS, FENCED_CHILD_ACK_TIMEOUT_SECONDS as FENCED_CHILD_ACK_TIMEOUT_SECONDS, FENCED_CHILD_DRAIN_SECONDS as FENCED_CHILD_DRAIN_SECONDS, FENCED_CHILD_DRAIN_CAP_BYTES as FENCED_CHILD_DRAIN_CAP_BYTES, FENCED_CHILD_STOP_GRACE_SECONDS as FENCED_CHILD_STOP_GRACE_SECONDS, FENCED_CHILD_REAP_SECONDS as FENCED_CHILD_REAP_SECONDS, ZERO_DIGEST as ZERO_DIGEST, COMMON_LOCK_TIMEOUT_SECONDS as COMMON_LOCK_TIMEOUT_SECONDS, COMMON_LOCK_POLL_SECONDS as COMMON_LOCK_POLL_SECONDS, COMMON_LOCK_RECORD_CAP_BYTES as COMMON_LOCK_RECORD_CAP_BYTES, MERGE_SCOPE_BINDING_CAP_BYTES as MERGE_SCOPE_BINDING_CAP_BYTES, COMMON_LOCK_INTENT_NAME as COMMON_LOCK_INTENT_NAME, COMMON_LOCK_DIRECTORY_NAME as COMMON_LOCK_DIRECTORY_NAME, COMMON_LOCK_OWNER_NAME as COMMON_LOCK_OWNER_NAME, COMMON_LOCK_FLOCK_NAME as COMMON_LOCK_FLOCK_NAME, COMMON_LOCK_RECOVERY_NAME as COMMON_LOCK_RECOVERY_NAME, COMMON_LOCK_INFLIGHT_NAME as COMMON_LOCK_INFLIGHT_NAME, CHAIN_ID_RE as CHAIN_ID_RE, SHA256_RE as SHA256_RE, COMMIT_RE as COMMIT_RE, RUN_ID_RE as RUN_ID_RE, _WORKTREE_LOCKS_GUARD as _WORKTREE_LOCKS_GUARD, _WORKTREE_LOCKS as _WORKTREE_LOCKS, _WORKTREE_LOCK_STATE as _WORKTREE_LOCK_STATE, _exclusive_descriptor_lock as _exclusive_descriptor_lock, _MERGE_REMOTE_ONLY_IDENTITY_FIELDS as _MERGE_REMOTE_ONLY_IDENTITY_FIELDS, _MERGE_SCOPE_UNSET as _MERGE_SCOPE_UNSET, _MERGE_SCOPE_OVERLAY as _MERGE_SCOPE_OVERLAY


def _bootstrap_fetch_observation_record_valid(
    state: Mapping[str, Any], value: object
) -> bool:
    if not isinstance(value, Mapping) or set(value) != {
        "schema",
        "chain_id",
        "generation_digest",
        "source_intent",
        "operation",
        "fetch_intent_event_digest",
        "argv",
        "resolved_tip",
        "child_result",
        "recorded_at",
    }:
        return False
    candidate = state.get("candidate")
    generation_digest = (
        candidate.get("generation_digest")
        if isinstance(candidate, Mapping)
        else None
    )
    source = value.get("source_intent")
    child = value.get("child_result")
    operation = value.get("operation")
    argv = value.get("argv")
    worktree = state.get("worktree")
    target = state.get("target")
    resolved_tip = value.get("resolved_tip")
    expected_fetch_argv = (
        [
            "git",
            "--no-pager",
            "-C",
            str(worktree.get("path", "")),
            "fetch",
            "--no-tags",
            "--quiet",
            "origin",
            str(target.get("destination_ref", "")),
        ]
        if isinstance(worktree, Mapping) and isinstance(target, Mapping)
        else None
    )
    tip_argv = bool(
        isinstance(worktree, Mapping)
        and isinstance(argv, list)
        and len(argv) == 7
        and argv[:6]
        == [
            "git",
            "--no-pager",
            "-C",
            str(worktree.get("path", "")),
            "cat-file",
            "-e",
        ]
    )
    tip_argument = argv[-1] if tip_argv else ""
    requested_tip = (
        tip_argument.removesuffix("^{commit}")
        if tip_argument.endswith("^{commit}")
        else ""
    )
    if (
        value.get("schema") != _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA
        or value.get("chain_id") != state.get("chain_id")
        or value.get("generation_digest") != generation_digest
        or not isinstance(source, Mapping)
        or source.get("operation") != "fetch"
        or not _valid_nonce(source.get("operation_nonce"))
        or not _valid_positive_int(source.get("attempt"))
        or operation not in {"fetch", "tip-resolution"}
        or not isinstance(argv, list)
        or not argv
        or not all(isinstance(member, str) and member for member in argv)
        or SHA256_RE.fullmatch(
            str(value.get("fetch_intent_event_digest", ""))
        )
        is None
        or not _valid_utc_second(value.get("recorded_at"))
        or not isinstance(child, Mapping)
        or set(child)
        != {
            "authorized",
            "exit",
            "inflight_digest",
            "output_digest",
            "launch_failed",
            "timed_out",
            "output_limit_exceeded",
            "group_survived",
        }
    ):
        return False
    child_valid = bool(
        type(child.get("authorized")) is bool
        and (child.get("exit") is None or type(child.get("exit")) is int)
        and SHA256_RE.fullmatch(str(child.get("inflight_digest", "")))
        is not None
        and SHA256_RE.fullmatch(str(child.get("output_digest", ""))) is not None
        and all(
            type(child.get(name)) is bool
            for name in (
                "launch_failed",
                "timed_out",
                "output_limit_exceeded",
                "group_survived",
            )
        )
    )
    if not child_valid:
        return False
    child_passed = bool(
        child.get("authorized") is True
        and child.get("exit") == 0
        and child.get("launch_failed") is False
        and child.get("timed_out") is False
        and child.get("output_limit_exceeded") is False
        and child.get("group_survived") is False
    )
    if operation == "fetch":
        argv_valid = argv == expected_fetch_argv
    else:
        argv_valid = bool(
            tip_argv
            and COMMIT_RE.fullmatch(requested_tip) is not None
        )
    return bool(
        argv_valid
        and (
            resolved_tip is None
            or isinstance(resolved_tip, str)
            and COMMIT_RE.fullmatch(resolved_tip) is not None
        )
        and (
            not child_passed
            or operation != "tip-resolution"
            or resolved_tip == requested_tip
        )
    )


def _bootstrap_fetch_observation_transition_valid(
    prior: Mapping[str, Any], current: Mapping[str, Any]
) -> bool:
    prior_integration = prior.get("integration")
    current_integration = current.get("integration")
    if not isinstance(prior_integration, Mapping) or not isinstance(
        current_integration, Mapping
    ):
        return False
    prior_intent = prior_integration.get("intent")
    current_intent = current_integration.get("intent")
    if any(
        prior_integration.get(name) != current_integration.get(name)
        for name in (set(prior_integration) | set(current_integration)) - {"intent"}
    ):
        return False
    if _bootstrap_fetch_observation_record_valid(current, current_intent):
        assert isinstance(current_intent, Mapping)
        return bool(
            isinstance(prior_intent, Mapping)
            and prior_intent.get("operation") == "fetch"
            and current_intent.get("source_intent") == prior_intent
        )
    return bool(
        _bootstrap_fetch_observation_record_valid(prior, prior_intent)
        and isinstance(prior_intent, Mapping)
        and current_intent == prior_intent.get("source_intent")
    )
