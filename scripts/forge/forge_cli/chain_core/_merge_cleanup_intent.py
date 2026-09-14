"""Extracted from scripts/forge/forge_cli/chain_core/__init__.py."""
from __future__ import annotations
from typing import Any, Mapping
from forge_cli.chain_core._controls import COMMON_LOCK_OWNER_KINDS as COMMON_LOCK_OWNER_KINDS, COMMON_LOCK_OPERATIONS as COMMON_LOCK_OPERATIONS, COMMON_LOCK_FENCE_OPERATIONS as COMMON_LOCK_FENCE_OPERATIONS, COMMON_LOCK_RECOVERY_KINDS as COMMON_LOCK_RECOVERY_KINDS, _COMMON_LOCK_OWNER_KEYS as _COMMON_LOCK_OWNER_KEYS, _COMMON_LOCK_FENCE_KEYS as _COMMON_LOCK_FENCE_KEYS, _COMMON_LOCK_RECOVERY_KEYS as _COMMON_LOCK_RECOVERY_KEYS, _CHAIN_LEASE_KEYS as _CHAIN_LEASE_KEYS, _REQUIRED_COMMON_LOCK_CONTROLS as _REQUIRED_COMMON_LOCK_CONTROLS, COMMON_LOCK_CONTROLS as COMMON_LOCK_CONTROLS, CHAIN_TOMBSTONE_SCHEMA as CHAIN_TOMBSTONE_SCHEMA, CHAIN_TOMBSTONE_EVENT as CHAIN_TOMBSTONE_EVENT, CHAIN_TOMBSTONE_KEYS as CHAIN_TOMBSTONE_KEYS, _REQUIRED_MERGE_STORE_CONTROLS as _REQUIRED_MERGE_STORE_CONTROLS, MERGE_STORE_CONTROLS as MERGE_STORE_CONTROLS, _REQUIRED_MERGE_ADAPTER_CONTROLS as _REQUIRED_MERGE_ADAPTER_CONTROLS, MERGE_ADAPTER_CONTROLS as MERGE_ADAPTER_CONTROLS, _REQUIRED_MERGE_INTEGRATION_CONTROLS as _REQUIRED_MERGE_INTEGRATION_CONTROLS, MERGE_INTEGRATION_CONTROLS as MERGE_INTEGRATION_CONTROLS, INGEST_PROOF_ORDER as INGEST_PROOF_ORDER, _REQUIRED_INGEST_PROOF_CONTROLS as _REQUIRED_INGEST_PROOF_CONTROLS, INGEST_PROOF_CONTROLS as INGEST_PROOF_CONTROLS, _MERGE_CLEANUP_INTENT_SCHEMA as _MERGE_CLEANUP_INTENT_SCHEMA, _MERGE_CLEANUP_RESULT_SCHEMA as _MERGE_CLEANUP_RESULT_SCHEMA, _MERGE_CLEANUP_CLOSE_SCHEMA as _MERGE_CLEANUP_CLOSE_SCHEMA, _MERGE_CLEANUP_RECOVERY_SCHEMA as _MERGE_CLEANUP_RECOVERY_SCHEMA, _MERGE_CLEANUP_FENCE_OPERATIONS as _MERGE_CLEANUP_FENCE_OPERATIONS, _EPOCH_FETCH_OBSERVATION_SCHEMA as _EPOCH_FETCH_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA, _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA as _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA
from forge_cli.chain_core._core import canonical_bytes as canonical_bytes, _chain_storage_root as _chain_storage_root, _validated_commitment_path as _validated_commitment_path, _parsed_run_captured_path as _parsed_run_captured_path, _require_ingest_proof as _require_ingest_proof, iso_z as iso_z, parse_time as parse_time, _require_merge_store_control as _require_merge_store_control, _require_merge_adapter_control as _require_merge_adapter_control, _require_merge_integration_control as _require_merge_integration_control, _require_common_lock_control as _require_common_lock_control, CommonLockBoundaryCrash as CommonLockBoundaryCrash, PublishedLockRecord as PublishedLockRecord, CommonLockInspection as CommonLockInspection, CommonLockUnavailable as CommonLockUnavailable, CommonLockReleaseFailure as CommonLockReleaseFailure, ChainLeaseUnavailable as ChainLeaseUnavailable, FencedChildSurvived as FencedChildSurvived, _valid_utc_second as _valid_utc_second, _valid_positive_int as _valid_positive_int, _valid_nonnegative_int as _valid_nonnegative_int, _valid_host as _valid_host, _valid_nonce as _valid_nonce, _valid_nullable_chain as _valid_nullable_chain, _write_all as _write_all, _PublicationCleanupFailure as _PublicationCleanupFailure, _process_probe as _process_probe, _group_probe as _group_probe, _sleep_with_deadline as _sleep_with_deadline, _require_deadline_open as _require_deadline_open, FencedProcessResult as FencedProcessResult, merge_gate_intent_digest as merge_gate_intent_digest, _forge_command as _forge_command, MergeRunTaskSnapshot as MergeRunTaskSnapshot, _merge_refusal as _merge_refusal, _valid_sorted_unique_strings as _valid_sorted_unique_strings
from forge_cli.chain_core._state import SCHEMA as SCHEMA, KIND as KIND, FRESH_REVIEWER_EVALS_GATE as FRESH_REVIEWER_EVALS_GATE, FRESH_REVIEWER_EVALS_REQUESTS as FRESH_REVIEWER_EVALS_REQUESTS, FRESH_REVIEWER_EVALS_REQUESTED_EVENT as FRESH_REVIEWER_EVALS_REQUESTED_EVENT, STATES as STATES, STATE_KEYS as STATE_KEYS, EVENT_KEYS as EVENT_KEYS, MERGE_STATE_KEYS as MERGE_STATE_KEYS, _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES as _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES, _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES as _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES, MERGE_EVENT_KEYS as MERGE_EVENT_KEYS, MERGE_EVENT_NAMES as MERGE_EVENT_NAMES, MERGE_CONSEQUENTIAL_EVENTS as MERGE_CONSEQUENTIAL_EVENTS, TIER_RANK as TIER_RANK, INACTIVE_SECONDS as INACTIVE_SECONDS, FENCED_CHILD_ACK_TIMEOUT_SECONDS as FENCED_CHILD_ACK_TIMEOUT_SECONDS, FENCED_CHILD_DRAIN_SECONDS as FENCED_CHILD_DRAIN_SECONDS, FENCED_CHILD_DRAIN_CAP_BYTES as FENCED_CHILD_DRAIN_CAP_BYTES, FENCED_CHILD_STOP_GRACE_SECONDS as FENCED_CHILD_STOP_GRACE_SECONDS, FENCED_CHILD_REAP_SECONDS as FENCED_CHILD_REAP_SECONDS, ZERO_DIGEST as ZERO_DIGEST, COMMON_LOCK_TIMEOUT_SECONDS as COMMON_LOCK_TIMEOUT_SECONDS, COMMON_LOCK_POLL_SECONDS as COMMON_LOCK_POLL_SECONDS, COMMON_LOCK_RECORD_CAP_BYTES as COMMON_LOCK_RECORD_CAP_BYTES, MERGE_SCOPE_BINDING_CAP_BYTES as MERGE_SCOPE_BINDING_CAP_BYTES, COMMON_LOCK_INTENT_NAME as COMMON_LOCK_INTENT_NAME, COMMON_LOCK_DIRECTORY_NAME as COMMON_LOCK_DIRECTORY_NAME, COMMON_LOCK_OWNER_NAME as COMMON_LOCK_OWNER_NAME, COMMON_LOCK_FLOCK_NAME as COMMON_LOCK_FLOCK_NAME, COMMON_LOCK_RECOVERY_NAME as COMMON_LOCK_RECOVERY_NAME, COMMON_LOCK_INFLIGHT_NAME as COMMON_LOCK_INFLIGHT_NAME, CHAIN_ID_RE as CHAIN_ID_RE, SHA256_RE as SHA256_RE, COMMIT_RE as COMMIT_RE, RUN_ID_RE as RUN_ID_RE, _WORKTREE_LOCKS_GUARD as _WORKTREE_LOCKS_GUARD, _WORKTREE_LOCKS as _WORKTREE_LOCKS, _WORKTREE_LOCK_STATE as _WORKTREE_LOCK_STATE, _exclusive_descriptor_lock as _exclusive_descriptor_lock, _MERGE_REMOTE_ONLY_IDENTITY_FIELDS as _MERGE_REMOTE_ONLY_IDENTITY_FIELDS, _MERGE_SCOPE_UNSET as _MERGE_SCOPE_UNSET, _MERGE_SCOPE_OVERLAY as _MERGE_SCOPE_OVERLAY


def _recovery_event_intent(event: Mapping[str, Any]) -> Mapping[str, Any] | None:
    payload = event.get("payload")
    delta = payload.get("delta") if isinstance(payload, Mapping) else None
    integration = delta.get("integration") if isinstance(delta, Mapping) else None
    intent = integration.get("intent") if isinstance(integration, Mapping) else None
    return intent if isinstance(intent, Mapping) else None


def _recovery_cleanup_intent(
    event: Mapping[str, Any] | None,
) -> Mapping[str, Any] | None:
    payload = event.get("payload") if isinstance(event, Mapping) else None
    delta = payload.get("delta") if isinstance(payload, Mapping) else None
    cleanup = delta.get("cleanup") if isinstance(delta, Mapping) else None
    intent = cleanup.get("intent") if isinstance(cleanup, Mapping) else None
    return intent if isinstance(intent, Mapping) else None


def _merge_cleanup_expected_subject(
    state: Mapping[str, Any], operation: str, subject: object
) -> dict[str, Any] | None:
    """Return the exact cleanup subject or reject a dynamic mismatch."""

    candidate = state.get("candidate")
    integration = state.get("integration")
    push = integration.get("push") if isinstance(integration, Mapping) else None
    worktree = state.get("worktree")
    target = state.get("target")
    if not (
        isinstance(candidate, Mapping)
        and isinstance(push, Mapping)
        and isinstance(worktree, Mapping)
        and isinstance(target, Mapping)
        and isinstance(subject, Mapping)
    ):
        return None
    landed_head = push.get("landed_head")
    candidate_head = candidate.get("candidate_head")
    if operation == "remote-fetch":
        expected = {
            "destination_ref": target.get("destination_ref"),
            "landed_head": landed_head,
        }
    elif operation == "remote-containment":
        expected = {
            "landed_head": landed_head,
            "remote_tip": subject.get("remote_tip"),
        }
        if not isinstance(expected["remote_tip"], str) or COMMIT_RE.fullmatch(
            expected["remote_tip"]
        ) is None:
            return None
    elif operation in {"worktree-observation", "worktree-remove"}:
        expected = {
            "path": worktree.get("path"),
            "branch": state.get("branch"),
            "candidate_head": candidate_head,
        }
    elif operation in {"branch-observation", "branch-delete"}:
        expected = {
            "branch": state.get("branch"),
            "candidate_head": candidate_head,
        }
    else:
        return None
    return expected if dict(subject) == expected else None


def _merge_cleanup_expected_argv(
    state: Mapping[str, Any], operation: str, subject: Mapping[str, Any]
) -> list[str] | None:
    repository = str(state.get("repository"))
    if operation == "remote-fetch":
        return [
            "git",
            "--no-pager",
            "-C",
            repository,
            "fetch",
            "--no-tags",
            "--quiet",
            "origin",
            str(subject["destination_ref"]),
        ]
    if operation == "remote-containment":
        return [
            "git",
            "--no-pager",
            "-C",
            repository,
            "merge-base",
            "--is-ancestor",
            str(subject["landed_head"]),
            str(subject["remote_tip"]),
        ]
    if operation == "worktree-observation":
        return [
            "git",
            "--no-pager",
            "-C",
            repository,
            "worktree",
            "list",
            "--porcelain",
            "-z",
        ]
    if operation == "worktree-remove":
        return [
            "git",
            "--no-pager",
            "-C",
            repository,
            "worktree",
            "remove",
            str(subject["path"]),
        ]
    if operation == "branch-observation":
        return [
            "git",
            "--no-pager",
            "-C",
            repository,
            "rev-parse",
            "--verify",
            "--quiet",
            f"{subject['branch']}^{{commit}}",
        ]
    if operation == "branch-delete":
        return [
            "git",
            "--no-pager",
            "-C",
            repository,
            "update-ref",
            "-d",
            str(subject["branch"]),
            str(subject["candidate_head"]),
        ]
    return None


def _merge_cleanup_intent_valid(
    value: object, state: Mapping[str, Any]
) -> bool:
    required = {
        "schema",
        "operation",
        "fence_operation",
        "operation_nonce",
        "generation_digest",
        "subject",
        "argv",
        "cwd",
        "started_at",
    }
    if not isinstance(value, Mapping):
        return False
    keys = set(value)
    if keys != required and keys != required | {"recovery"}:
        return False
    operation = value.get("operation")
    candidate = state.get("candidate")
    if (
        not isinstance(operation, str)
        or operation not in _MERGE_CLEANUP_FENCE_OPERATIONS
        or value.get("schema") != _MERGE_CLEANUP_INTENT_SCHEMA
        or value.get("fence_operation")
        != _MERGE_CLEANUP_FENCE_OPERATIONS[operation]
        or not _valid_nonce(value.get("operation_nonce"))
        or not isinstance(candidate, Mapping)
        or value.get("generation_digest") != candidate.get("generation_digest")
        or value.get("cwd") != state.get("repository")
        or not _valid_utc_second(value.get("started_at"))
    ):
        return False
    subject = _merge_cleanup_expected_subject(state, operation, value.get("subject"))
    if subject is None:
        return False
    recovery = value.get("recovery")
    if ("recovery" in value) != (recovery is not None):
        return False
    if recovery is not None and not (
        operation == "remote-fetch"
        and isinstance(recovery, Mapping)
        and set(recovery)
        == {
            "schema",
            "intent_event_digest",
            "operation",
            "fence_operation",
            "recovery_event_digest",
        }
        and recovery.get("schema") == _MERGE_CLEANUP_RECOVERY_SCHEMA
        and isinstance(recovery.get("intent_event_digest"), str)
        and SHA256_RE.fullmatch(recovery["intent_event_digest"]) is not None
        and recovery.get("operation") in _MERGE_CLEANUP_FENCE_OPERATIONS
        and recovery.get("fence_operation")
        == _MERGE_CLEANUP_FENCE_OPERATIONS[recovery["operation"]]
        and isinstance(recovery.get("recovery_event_digest"), str)
        and SHA256_RE.fullmatch(recovery["recovery_event_digest"]) is not None
    ):
        return False
    return value.get("argv") == _merge_cleanup_expected_argv(
        state, operation, subject
    )
