"""Extracted from scripts/forge/forge_cli/chain_core/__init__.py."""
from __future__ import annotations
import copy
from typing import Any
from forge_cli.chain_core._controls import COMMON_LOCK_OWNER_KINDS as COMMON_LOCK_OWNER_KINDS, COMMON_LOCK_OPERATIONS as COMMON_LOCK_OPERATIONS, COMMON_LOCK_FENCE_OPERATIONS as COMMON_LOCK_FENCE_OPERATIONS, COMMON_LOCK_RECOVERY_KINDS as COMMON_LOCK_RECOVERY_KINDS, _COMMON_LOCK_OWNER_KEYS as _COMMON_LOCK_OWNER_KEYS, _COMMON_LOCK_FENCE_KEYS as _COMMON_LOCK_FENCE_KEYS, _COMMON_LOCK_RECOVERY_KEYS as _COMMON_LOCK_RECOVERY_KEYS, _CHAIN_LEASE_KEYS as _CHAIN_LEASE_KEYS, _REQUIRED_COMMON_LOCK_CONTROLS as _REQUIRED_COMMON_LOCK_CONTROLS, COMMON_LOCK_CONTROLS as COMMON_LOCK_CONTROLS, CHAIN_TOMBSTONE_SCHEMA as CHAIN_TOMBSTONE_SCHEMA, CHAIN_TOMBSTONE_EVENT as CHAIN_TOMBSTONE_EVENT, CHAIN_TOMBSTONE_KEYS as CHAIN_TOMBSTONE_KEYS, _REQUIRED_MERGE_STORE_CONTROLS as _REQUIRED_MERGE_STORE_CONTROLS, MERGE_STORE_CONTROLS as MERGE_STORE_CONTROLS, _REQUIRED_MERGE_ADAPTER_CONTROLS as _REQUIRED_MERGE_ADAPTER_CONTROLS, MERGE_ADAPTER_CONTROLS as MERGE_ADAPTER_CONTROLS, _REQUIRED_MERGE_INTEGRATION_CONTROLS as _REQUIRED_MERGE_INTEGRATION_CONTROLS, MERGE_INTEGRATION_CONTROLS as MERGE_INTEGRATION_CONTROLS, INGEST_PROOF_ORDER as INGEST_PROOF_ORDER, _REQUIRED_INGEST_PROOF_CONTROLS as _REQUIRED_INGEST_PROOF_CONTROLS, INGEST_PROOF_CONTROLS as INGEST_PROOF_CONTROLS, _MERGE_CLEANUP_INTENT_SCHEMA as _MERGE_CLEANUP_INTENT_SCHEMA, _MERGE_CLEANUP_RESULT_SCHEMA as _MERGE_CLEANUP_RESULT_SCHEMA, _MERGE_CLEANUP_CLOSE_SCHEMA as _MERGE_CLEANUP_CLOSE_SCHEMA, _MERGE_CLEANUP_RECOVERY_SCHEMA as _MERGE_CLEANUP_RECOVERY_SCHEMA, _MERGE_CLEANUP_FENCE_OPERATIONS as _MERGE_CLEANUP_FENCE_OPERATIONS, _EPOCH_FETCH_OBSERVATION_SCHEMA as _EPOCH_FETCH_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA, _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA as _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA
from forge_cli.chain_core._core import canonical_bytes as canonical_bytes, _chain_storage_root as _chain_storage_root, _validated_commitment_path as _validated_commitment_path, _parsed_run_captured_path as _parsed_run_captured_path, _require_ingest_proof as _require_ingest_proof, iso_z as iso_z, parse_time as parse_time, _require_merge_store_control as _require_merge_store_control, _require_merge_adapter_control as _require_merge_adapter_control, _require_merge_integration_control as _require_merge_integration_control, _require_common_lock_control as _require_common_lock_control, CommonLockBoundaryCrash as CommonLockBoundaryCrash, PublishedLockRecord as PublishedLockRecord, CommonLockInspection as CommonLockInspection, CommonLockUnavailable as CommonLockUnavailable, CommonLockReleaseFailure as CommonLockReleaseFailure, ChainLeaseUnavailable as ChainLeaseUnavailable, FencedChildSurvived as FencedChildSurvived, _valid_utc_second as _valid_utc_second, _valid_positive_int as _valid_positive_int, _valid_nonnegative_int as _valid_nonnegative_int, _valid_host as _valid_host, _valid_nonce as _valid_nonce, _valid_nullable_chain as _valid_nullable_chain, _write_all as _write_all, _PublicationCleanupFailure as _PublicationCleanupFailure, _process_probe as _process_probe, _group_probe as _group_probe, _sleep_with_deadline as _sleep_with_deadline, _require_deadline_open as _require_deadline_open, FencedProcessResult as FencedProcessResult, merge_gate_intent_digest as merge_gate_intent_digest, _forge_command as _forge_command, MergeRunTaskSnapshot as MergeRunTaskSnapshot, _merge_refusal as _merge_refusal, _valid_sorted_unique_strings as _valid_sorted_unique_strings
from forge_cli.chain_core._state import SCHEMA as SCHEMA, KIND as KIND, FRESH_REVIEWER_EVALS_GATE as FRESH_REVIEWER_EVALS_GATE, FRESH_REVIEWER_EVALS_REQUESTS as FRESH_REVIEWER_EVALS_REQUESTS, FRESH_REVIEWER_EVALS_REQUESTED_EVENT as FRESH_REVIEWER_EVALS_REQUESTED_EVENT, STATES as STATES, STATE_KEYS as STATE_KEYS, EVENT_KEYS as EVENT_KEYS, MERGE_STATE_KEYS as MERGE_STATE_KEYS, _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES as _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES, _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES as _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES, MERGE_EVENT_KEYS as MERGE_EVENT_KEYS, MERGE_EVENT_NAMES as MERGE_EVENT_NAMES, MERGE_CONSEQUENTIAL_EVENTS as MERGE_CONSEQUENTIAL_EVENTS, TIER_RANK as TIER_RANK, INACTIVE_SECONDS as INACTIVE_SECONDS, FENCED_CHILD_ACK_TIMEOUT_SECONDS as FENCED_CHILD_ACK_TIMEOUT_SECONDS, FENCED_CHILD_DRAIN_SECONDS as FENCED_CHILD_DRAIN_SECONDS, FENCED_CHILD_DRAIN_CAP_BYTES as FENCED_CHILD_DRAIN_CAP_BYTES, FENCED_CHILD_STOP_GRACE_SECONDS as FENCED_CHILD_STOP_GRACE_SECONDS, FENCED_CHILD_REAP_SECONDS as FENCED_CHILD_REAP_SECONDS, ZERO_DIGEST as ZERO_DIGEST, COMMON_LOCK_TIMEOUT_SECONDS as COMMON_LOCK_TIMEOUT_SECONDS, COMMON_LOCK_POLL_SECONDS as COMMON_LOCK_POLL_SECONDS, COMMON_LOCK_RECORD_CAP_BYTES as COMMON_LOCK_RECORD_CAP_BYTES, MERGE_SCOPE_BINDING_CAP_BYTES as MERGE_SCOPE_BINDING_CAP_BYTES, COMMON_LOCK_INTENT_NAME as COMMON_LOCK_INTENT_NAME, COMMON_LOCK_DIRECTORY_NAME as COMMON_LOCK_DIRECTORY_NAME, COMMON_LOCK_OWNER_NAME as COMMON_LOCK_OWNER_NAME, COMMON_LOCK_FLOCK_NAME as COMMON_LOCK_FLOCK_NAME, COMMON_LOCK_RECOVERY_NAME as COMMON_LOCK_RECOVERY_NAME, COMMON_LOCK_INFLIGHT_NAME as COMMON_LOCK_INFLIGHT_NAME, CHAIN_ID_RE as CHAIN_ID_RE, SHA256_RE as SHA256_RE, COMMIT_RE as COMMIT_RE, RUN_ID_RE as RUN_ID_RE, _WORKTREE_LOCKS_GUARD as _WORKTREE_LOCKS_GUARD, _WORKTREE_LOCKS as _WORKTREE_LOCKS, _WORKTREE_LOCK_STATE as _WORKTREE_LOCK_STATE, _exclusive_descriptor_lock as _exclusive_descriptor_lock, _MERGE_REMOTE_ONLY_IDENTITY_FIELDS as _MERGE_REMOTE_ONLY_IDENTITY_FIELDS, _MERGE_SCOPE_UNSET as _MERGE_SCOPE_UNSET, _MERGE_SCOPE_OVERLAY as _MERGE_SCOPE_OVERLAY


def _validate_owner_record(value: Any) -> dict[str, Any]:
    _require_common_lock_control("canonical-records")
    if not isinstance(value, dict) or set(value) != _COMMON_LOCK_OWNER_KEYS:
        raise ValueError("common-lock owner has an invalid key set")
    kind = value.get("owner_kind")
    operation = value.get("operation")
    chain_id = value.get("chain_id")
    if kind not in COMMON_LOCK_OWNER_KINDS:
        raise ValueError("common-lock owner kind is invalid")
    if operation not in COMMON_LOCK_OPERATIONS:
        raise ValueError("common-lock operation is invalid")
    if kind == "merge":
        if not isinstance(chain_id, str) or not CHAIN_ID_RE.fullmatch(chain_id):
            raise ValueError("merge common-lock owner lacks a valid chain")
        if operation not in {"start", "refresh", "finalize", "recover", "cleanup", "abort"}:
            raise ValueError("merge common-lock operation is invalid")
    elif chain_id is not None:
        raise ValueError("non-merge common-lock owner carries a chain")
    if kind == "push" and operation != "push":
        raise ValueError("push common-lock owner operation is invalid")
    if kind == "phase5" and operation != "phase5-scan":
        raise ValueError("phase5 common-lock owner operation is invalid")
    if (
        value.get("schema") != "forge-rebase-lock/1"
        or not _valid_host(value.get("host"))
        or not _valid_positive_int(value.get("pid"))
        or not _valid_nonce(value.get("nonce"))
        or not _valid_utc_second(value.get("started_at"))
    ):
        raise ValueError("common-lock owner fields are invalid")
    return copy.deepcopy(value)


def _validate_fence_record(value: Any) -> dict[str, Any]:
    _require_common_lock_control("canonical-records")
    if not isinstance(value, dict) or set(value) != _COMMON_LOCK_FENCE_KEYS:
        raise ValueError("in-flight fence has an invalid key set")
    kind = value.get("owner_kind")
    chain_id = value.get("chain_id")
    operation = value.get("operation")
    if kind not in {"merge", "push"} or operation not in COMMON_LOCK_FENCE_OPERATIONS:
        raise ValueError("in-flight fence kind or operation is invalid")
    if kind == "merge":
        if not isinstance(chain_id, str) or not CHAIN_ID_RE.fullmatch(chain_id):
            raise ValueError("merge in-flight fence lacks a valid chain")
    elif chain_id is not None:
        raise ValueError("push in-flight fence carries a chain")
    if operation == "attribution-observation" and kind != "push":
        raise ValueError("attribution observation is not standalone push")
    if (
        value.get("schema") != "forge-rebase-inflight/1"
        or not _valid_host(value.get("host"))
        or not _valid_positive_int(value.get("pid"))
        or not _valid_positive_int(value.get("pgid"))
        or not SHA256_RE.fullmatch(str(value.get("intent_digest") or ""))
        or not _valid_nonce(value.get("nonce"))
        or not _valid_utc_second(value.get("started_at"))
    ):
        raise ValueError("in-flight fence fields are invalid")
    return copy.deepcopy(value)


def _validate_recovery_record(value: Any) -> dict[str, Any]:
    _require_common_lock_control("canonical-records")
    if not isinstance(value, dict) or set(value) != _COMMON_LOCK_RECOVERY_KEYS:
        raise ValueError("recovery reservation has an invalid key set")
    kind = value.get("recovery_kind")
    if (
        value.get("schema") != "forge-rebase-recovery/1"
        or kind not in COMMON_LOCK_RECOVERY_KINDS
        or not _valid_host(value.get("host"))
        or not _valid_positive_int(value.get("pid"))
        or not _valid_nonce(value.get("nonce"))
        or not _valid_utc_second(value.get("started_at"))
    ):
        raise ValueError("recovery reservation identity is invalid")
    stale_fields = (
        "stale_owner_inode",
        "stale_owner_digest",
        "stale_owner_host",
        "stale_owner_pid",
        "stale_owner_kind",
        "stale_owner_chain_id",
        "owner_dead_at",
    )
    inflight_fields = (
        "inflight_inode",
        "inflight_digest",
        "inflight_host",
        "inflight_pgid",
        "inflight_owner_kind",
        "inflight_chain_id",
        "group_dead_at",
    )
    if kind.startswith("fallback-"):
        if (
            not _valid_nonnegative_int(value.get("stale_owner_inode"))
            or not SHA256_RE.fullmatch(str(value.get("stale_owner_digest") or ""))
            or not _valid_host(value.get("stale_owner_host"))
            or not _valid_positive_int(value.get("stale_owner_pid"))
            or not _valid_nullable_chain(
                value.get("stale_owner_kind"),
                value.get("stale_owner_chain_id"),
                allow_phase5=True,
            )
            or not _valid_utc_second(value.get("owner_dead_at"))
        ):
            raise ValueError("fallback reservation stale-owner fields are invalid")
    elif any(value.get(field) is not None for field in stale_fields):
        raise ValueError("flock-held reservation carries stale-owner fields")
    if kind == "fallback-owner":
        if any(value.get(field) is not None for field in inflight_fields):
            raise ValueError("owner-only reservation carries in-flight fields")
    else:
        if (
            not _valid_nonnegative_int(value.get("inflight_inode"))
            or not SHA256_RE.fullmatch(str(value.get("inflight_digest") or ""))
            or not _valid_host(value.get("inflight_host"))
            or not _valid_positive_int(value.get("inflight_pgid"))
            or not _valid_nullable_chain(
                value.get("inflight_owner_kind"),
                value.get("inflight_chain_id"),
                allow_phase5=False,
            )
            or not _valid_utc_second(value.get("group_dead_at"))
        ):
            raise ValueError("fence reservation in-flight fields are invalid")
    return copy.deepcopy(value)


def _validate_chain_lease_record(value: Any) -> dict[str, Any]:
    _require_common_lock_control("canonical-records")
    if not isinstance(value, dict) or set(value) != _CHAIN_LEASE_KEYS:
        raise ValueError("chain lease has an invalid key set")
    if (
        not isinstance(value.get("chain_id"), str)
        or CHAIN_ID_RE.fullmatch(value["chain_id"]) is None
        or not _valid_host(value.get("host"))
        or not _valid_positive_int(value.get("pid"))
        or not _valid_nonce(value.get("nonce"))
        or not isinstance(value.get("session"), str)
        or not value["session"]
        or "\x00" in value["session"]
        or not _valid_utc_second(value.get("started_at"))
    ):
        raise ValueError("chain lease fields are invalid")
    return copy.deepcopy(value)
