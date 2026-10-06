"""Extracted from scripts/forge/forge_cli/chain_core/__init__.py."""
from __future__ import annotations
import re
from typing import Any
from forge_cli import candidate as candidate_module
from forge_cli.chain_core._controls import COMMON_LOCK_OWNER_KINDS as COMMON_LOCK_OWNER_KINDS, COMMON_LOCK_OPERATIONS as COMMON_LOCK_OPERATIONS, COMMON_LOCK_FENCE_OPERATIONS as COMMON_LOCK_FENCE_OPERATIONS, COMMON_LOCK_RECOVERY_KINDS as COMMON_LOCK_RECOVERY_KINDS, _COMMON_LOCK_OWNER_KEYS as _COMMON_LOCK_OWNER_KEYS, _COMMON_LOCK_FENCE_KEYS as _COMMON_LOCK_FENCE_KEYS, _COMMON_LOCK_RECOVERY_KEYS as _COMMON_LOCK_RECOVERY_KEYS, _CHAIN_LEASE_KEYS as _CHAIN_LEASE_KEYS, _REQUIRED_COMMON_LOCK_CONTROLS as _REQUIRED_COMMON_LOCK_CONTROLS, COMMON_LOCK_CONTROLS as COMMON_LOCK_CONTROLS, CHAIN_TOMBSTONE_SCHEMA as CHAIN_TOMBSTONE_SCHEMA, CHAIN_TOMBSTONE_EVENT as CHAIN_TOMBSTONE_EVENT, CHAIN_TOMBSTONE_KEYS as CHAIN_TOMBSTONE_KEYS, _REQUIRED_MERGE_STORE_CONTROLS as _REQUIRED_MERGE_STORE_CONTROLS, MERGE_STORE_CONTROLS as MERGE_STORE_CONTROLS, _REQUIRED_MERGE_ADAPTER_CONTROLS as _REQUIRED_MERGE_ADAPTER_CONTROLS, MERGE_ADAPTER_CONTROLS as MERGE_ADAPTER_CONTROLS, _REQUIRED_MERGE_INTEGRATION_CONTROLS as _REQUIRED_MERGE_INTEGRATION_CONTROLS, MERGE_INTEGRATION_CONTROLS as MERGE_INTEGRATION_CONTROLS, _MERGE_CLEANUP_INTENT_SCHEMA as _MERGE_CLEANUP_INTENT_SCHEMA, _MERGE_CLEANUP_RESULT_SCHEMA as _MERGE_CLEANUP_RESULT_SCHEMA, _MERGE_CLEANUP_CLOSE_SCHEMA as _MERGE_CLEANUP_CLOSE_SCHEMA, _MERGE_CLEANUP_RECOVERY_SCHEMA as _MERGE_CLEANUP_RECOVERY_SCHEMA, _MERGE_CLEANUP_FENCE_OPERATIONS as _MERGE_CLEANUP_FENCE_OPERATIONS, _EPOCH_FETCH_OBSERVATION_SCHEMA as _EPOCH_FETCH_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA, _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA as _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA
from forge_cli.chain_core._core import canonical_bytes as canonical_bytes, iso_z as iso_z, parse_time as parse_time, _require_merge_store_control as _require_merge_store_control, _require_merge_adapter_control as _require_merge_adapter_control, _require_merge_integration_control as _require_merge_integration_control, _require_common_lock_control as _require_common_lock_control, CommonLockBoundaryCrash as CommonLockBoundaryCrash, PublishedLockRecord as PublishedLockRecord, CommonLockInspection as CommonLockInspection, CommonLockUnavailable as CommonLockUnavailable, CommonLockReleaseFailure as CommonLockReleaseFailure, ChainLeaseUnavailable as ChainLeaseUnavailable, FencedChildSurvived as FencedChildSurvived, _valid_utc_second as _valid_utc_second, _valid_positive_int as _valid_positive_int, _valid_nonnegative_int as _valid_nonnegative_int, _valid_host as _valid_host, _valid_nonce as _valid_nonce, _valid_nullable_chain as _valid_nullable_chain, _write_all as _write_all, _PublicationCleanupFailure as _PublicationCleanupFailure, _process_probe as _process_probe, _group_probe as _group_probe, _sleep_with_deadline as _sleep_with_deadline, _require_deadline_open as _require_deadline_open, FencedProcessResult as FencedProcessResult, merge_gate_intent_digest as merge_gate_intent_digest, _forge_command as _forge_command, _merge_refusal as _merge_refusal
from forge_cli.chain_core._state import SCHEMA as SCHEMA, KIND as KIND, FRESH_REVIEWER_EVALS_GATE as FRESH_REVIEWER_EVALS_GATE, FRESH_REVIEWER_EVALS_REQUESTS as FRESH_REVIEWER_EVALS_REQUESTS, FRESH_REVIEWER_EVALS_REQUESTED_EVENT as FRESH_REVIEWER_EVALS_REQUESTED_EVENT, STATES as STATES, STATE_KEYS as STATE_KEYS, EVENT_KEYS as EVENT_KEYS, MERGE_STATE_KEYS as MERGE_STATE_KEYS, _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES as _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES, _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES as _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES, MERGE_EVENT_KEYS as MERGE_EVENT_KEYS, MERGE_EVENT_NAMES as MERGE_EVENT_NAMES, TIER_RANK as TIER_RANK, INACTIVE_SECONDS as INACTIVE_SECONDS, FENCED_CHILD_ACK_TIMEOUT_SECONDS as FENCED_CHILD_ACK_TIMEOUT_SECONDS, FENCED_CHILD_DRAIN_SECONDS as FENCED_CHILD_DRAIN_SECONDS, FENCED_CHILD_DRAIN_CAP_BYTES as FENCED_CHILD_DRAIN_CAP_BYTES, FENCED_CHILD_STOP_GRACE_SECONDS as FENCED_CHILD_STOP_GRACE_SECONDS, FENCED_CHILD_REAP_SECONDS as FENCED_CHILD_REAP_SECONDS, ZERO_DIGEST as ZERO_DIGEST, COMMON_LOCK_TIMEOUT_SECONDS as COMMON_LOCK_TIMEOUT_SECONDS, COMMON_LOCK_POLL_SECONDS as COMMON_LOCK_POLL_SECONDS, COMMON_LOCK_RECORD_CAP_BYTES as COMMON_LOCK_RECORD_CAP_BYTES, MERGE_SCOPE_BINDING_CAP_BYTES as MERGE_SCOPE_BINDING_CAP_BYTES, COMMON_LOCK_INTENT_NAME as COMMON_LOCK_INTENT_NAME, COMMON_LOCK_DIRECTORY_NAME as COMMON_LOCK_DIRECTORY_NAME, COMMON_LOCK_OWNER_NAME as COMMON_LOCK_OWNER_NAME, COMMON_LOCK_FLOCK_NAME as COMMON_LOCK_FLOCK_NAME, COMMON_LOCK_RECOVERY_NAME as COMMON_LOCK_RECOVERY_NAME, COMMON_LOCK_INFLIGHT_NAME as COMMON_LOCK_INFLIGHT_NAME, CHAIN_ID_RE as CHAIN_ID_RE, SHA256_RE as SHA256_RE, COMMIT_RE as COMMIT_RE, RUN_ID_RE as RUN_ID_RE, _WORKTREE_LOCKS_GUARD as _WORKTREE_LOCKS_GUARD, _WORKTREE_LOCKS as _WORKTREE_LOCKS, _WORKTREE_LOCK_STATE as _WORKTREE_LOCK_STATE, _exclusive_descriptor_lock as _exclusive_descriptor_lock, _MERGE_REMOTE_ONLY_IDENTITY_FIELDS as _MERGE_REMOTE_ONLY_IDENTITY_FIELDS, _MERGE_SCOPE_UNSET as _MERGE_SCOPE_UNSET, _MERGE_SCOPE_OVERLAY as _MERGE_SCOPE_OVERLAY
from forge_cli.envelope import FrozenError


def validate_state(state: Any, chain_id: str | None = None) -> dict[str, Any]:
    if not isinstance(state, dict) or set(state) not in (
        STATE_KEYS, STATE_KEYS | {"run_binding", "journal_outbox"}
    ):
        raise FrozenError(
            "materialized chain state has an invalid top-level key set",
            chain_id=chain_id,
            observed=(
                ",".join(sorted(state)) if isinstance(state, dict) else type(state).__name__
            ),
        )
    actual_id = state.get("chain_id")
    if not isinstance(actual_id, str) or not CHAIN_ID_RE.fullmatch(actual_id):
        raise FrozenError("chain state has an invalid chain_id", chain_id=chain_id)
    if chain_id is not None and actual_id != chain_id:
        raise FrozenError(
            "chain filename and payload identity diverge",
            chain_id=chain_id,
            observed=str(actual_id),
        )
    if state.get("schema") != SCHEMA or state.get("kind") != KIND:
        raise FrozenError(
            "chain state schema/kind is unsupported",
            chain_id=actual_id,
            state=str(state.get("state")),
        )
    if state.get("state") not in STATES:
        raise FrozenError(
            "chain state contains an unknown state",
            chain_id=actual_id,
            observed=str(state.get("state")),
        )
    if not isinstance(state.get("paths"), list) or not all(
        isinstance(item, str) for item in state["paths"]
    ):
        raise FrozenError("chain paths are malformed", chain_id=actual_id)
    for object_key in (
        "policy_source",
        "staging",
        "candidate",
        "tier",
        "steps",
        "review",
        "approval",
        "authorization",
        "commit_result",
    ):
        if not isinstance(state.get(object_key), dict):
            raise FrozenError(
                f"chain {object_key} record is malformed", chain_id=actual_id
            )
    try:
        parse_time(state["created_at"])
        parse_time(state["last_event_at"])
        parse_time(state["inactive_after"])
    except (KeyError, TypeError, ValueError) as exc:
        raise FrozenError("chain timestamps are malformed", chain_id=actual_id) from exc
    candidate_record = state["candidate"]
    candidate = candidate_record.get("sha256")
    if candidate is not None and not SHA256_RE.fullmatch(str(candidate)):
        raise FrozenError("chain candidate digest is malformed", chain_id=actual_id)
    candidate_schema = candidate_record.get("schema")
    if candidate_schema is not None:
        v2_keys = {
            "schema",
            "sha256",
            "authorization_id",
            "object_format",
            "tree_oid",
            "base_commit_oid",
            "review_diff_sha256",
            "review_diff_byte_count",
            "computed_at",
        }
        object_format = candidate_record.get("object_format")
        oid_length = {"sha1": 40, "sha256": 64}.get(str(object_format), 0)
        tree_oid = candidate_record.get("tree_oid")
        base_commit_oid = candidate_record.get("base_commit_oid")
        if (
            candidate_schema != candidate_module.CANDIDATE_SCHEMA
            or set(candidate_record) != v2_keys
            or candidate_record.get("authorization_id") != candidate
            or not isinstance(tree_oid, str)
            or re.fullmatch(rf"[0-9a-f]{{{oid_length}}}", tree_oid) is None
            or (
                base_commit_oid is not None
                and (
                    not isinstance(base_commit_oid, str)
                    or re.fullmatch(rf"[0-9a-f]{{{oid_length}}}", base_commit_oid)
                    is None
                )
            )
            or not isinstance(candidate_record.get("review_diff_sha256"), str)
            or SHA256_RE.fullmatch(str(candidate_record["review_diff_sha256"]))
            is None
            or type(candidate_record.get("review_diff_byte_count")) is not int
            or int(candidate_record["review_diff_byte_count"]) < 0
            or not isinstance(candidate_record.get("computed_at"), str)
        ):
            raise FrozenError("chain v2 candidate record is malformed", chain_id=actual_id)
        try:
            parse_time(str(candidate_record["computed_at"]))
            expected_authorization = candidate_module.authorization_id(
                str(object_format), tree_oid
            )
        except (ValueError, candidate_module.CandidateError) as exc:
            raise FrozenError(
                "chain v2 candidate record is malformed", chain_id=actual_id
            ) from exc
        if candidate != expected_authorization:
            raise FrozenError(
                "chain v2 candidate authorization identity is malformed",
                chain_id=actual_id,
            )
        staged_paths = state["staging"].get("staged_paths")
        try:
            bytewise_paths = sorted(
                state["paths"], key=lambda value: value.encode("utf-8")
            )
        except UnicodeEncodeError as exc:
            raise FrozenError(
                "chain v2 candidate path/evidence record is malformed",
                chain_id=actual_id,
            ) from exc
        if (
            int(candidate_record["review_diff_byte_count"])
            > candidate_module.REVIEW_DIFF_MAX_BYTES
            or any(not path for path in state["paths"])
            or len(state["paths"]) != len(set(state["paths"]))
            or state["paths"] != bytewise_paths
            or staged_paths != state["paths"]
        ):
            raise FrozenError(
                "chain v2 candidate path/evidence record is malformed",
                chain_id=actual_id,
            )

        commit_result = state["commit_result"]
        allowed_result_keys = {
            "intent",
            "identity",
            "mismatch_latched",
            "commit_sha",
            "head_at_commit",
            "committed_at",
            "closed_at",
            "recovered_at",
            "recovery",
            "aborted_at",
            "reason",
            "old_head",
            "new_head",
        }
        if not set(commit_result) <= allowed_result_keys:
            raise FrozenError(
                "chain v2 produced-commit record is malformed", chain_id=actual_id
            )
        intent = commit_result.get("intent")
        if intent is not None:
            intent_keys = {
                "candidate",
                "authorization_id",
                "object_format",
                "expected_tree_oid",
                "pre_head",
                "message_digest",
                "written_at",
                "lock_session_pid",
            }
            if (
                not isinstance(intent, dict)
                or set(intent) != intent_keys
                or intent.get("candidate") != candidate
                or intent.get("authorization_id") != candidate
                or intent.get("object_format") != object_format
                or intent.get("expected_tree_oid") != tree_oid
                or not isinstance(intent.get("pre_head"), str)
                or re.fullmatch(rf"[0-9a-f]{{{oid_length}}}", intent["pre_head"])
                is None
                or not isinstance(intent.get("message_digest"), str)
                or SHA256_RE.fullmatch(intent["message_digest"]) is None
                or not isinstance(intent.get("written_at"), str)
                or not isinstance(intent.get("lock_session_pid"), str)
                or re.fullmatch(r"[1-9][0-9]*", intent["lock_session_pid"]) is None
            ):
                raise FrozenError(
                    "chain v2 commit intent is malformed", chain_id=actual_id
                )
            try:
                parse_time(intent["written_at"])
            except ValueError as exc:
                raise FrozenError(
                    "chain v2 commit intent is malformed", chain_id=actual_id
                ) from exc
        identity = commit_result.get("identity")
        bound_base_commit = (
            intent.get("pre_head") if isinstance(intent, dict) else state.get("repo_head")
        )
        if base_commit_oid != bound_base_commit:
            raise FrozenError(
                "chain v2 candidate base does not match its authorized parent",
                chain_id=actual_id,
            )
        if state.get("state") == "committing" and intent is None:
            raise FrozenError(
                "chain v2 commit intent is malformed", chain_id=actual_id
            )
        if identity is not None:
            expected_keys = {"parent", "tree", "message_digest"}
            identity_keys = {
                "result",
                "produced_sha",
                "expected",
                "observed",
                "checks",
                "transcript",
            }
            expected_identity = identity.get("expected") if isinstance(identity, dict) else None
            observed_identity = identity.get("observed") if isinstance(identity, dict) else None
            identity_checks = identity.get("checks") if isinstance(identity, dict) else None
            if (
                intent is None
                or not isinstance(identity, dict)
                or set(identity) != identity_keys
                or identity.get("result") not in {"passed", "failed"}
                or not isinstance(identity.get("produced_sha"), str)
                or re.fullmatch(
                    rf"[0-9a-f]{{{oid_length}}}", str(identity["produced_sha"])
                )
                is None
                or not isinstance(expected_identity, dict)
                or set(expected_identity) != expected_keys
                or expected_identity
                != {
                    "parent": intent["pre_head"],
                    "tree": intent["expected_tree_oid"],
                    "message_digest": intent["message_digest"],
                }
                or not isinstance(observed_identity, dict)
                or not isinstance(identity_checks, dict)
                or set(identity_checks)
                != {
                    "head-movement",
                    "exact-single-parent",
                    "exact-tree",
                    "exact-message",
                }
                or any(type(value) is not bool for value in identity_checks.values())
                or (identity.get("result") == "passed") != all(identity_checks.values())
                or not isinstance(identity.get("transcript"), str)
            ):
                raise FrozenError(
                    "chain v2 produced-commit identity is malformed",
                    chain_id=actual_id,
                )
            mismatch_latched = commit_result.get("mismatch_latched")
            if identity["result"] == "failed":
                if mismatch_latched is not True:
                    raise FrozenError(
                        "chain v2 produced-commit mismatch latch is malformed",
                        chain_id=actual_id,
                    )
            elif "mismatch_latched" in commit_result:
                raise FrozenError(
                    "chain v2 produced-commit mismatch latch is malformed",
                    chain_id=actual_id,
                )
        elif "mismatch_latched" in commit_result:
            raise FrozenError(
                "chain v2 produced-commit mismatch latch is malformed",
                chain_id=actual_id,
            )
        commit_sha = commit_result.get("commit_sha")
        if commit_sha is not None and (
            identity is None
            or identity.get("result") != "passed"
            or commit_sha != identity.get("produced_sha")
            or commit_result.get("head_at_commit") != commit_sha
            or state.get("repo_head") != commit_sha
        ):
            raise FrozenError(
                "chain v2 produced-commit landing is malformed", chain_id=actual_id
            )
        if state.get("state") == "closed" and commit_sha is None:
            raise FrozenError(
                "chain v2 produced-commit landing is malformed", chain_id=actual_id
            )
        authorization = state["authorization"]
        if authorization.get("consumed") is True and (
            identity is None or identity.get("result") != "passed"
        ):
            raise FrozenError(
                "chain v2 authorization consumption lacks identity proof",
                chain_id=actual_id,
            )
        for oid_key in ("old_head", "new_head"):
            oid_value = commit_result.get(oid_key)
            if oid_value is not None and (
                not isinstance(oid_value, str)
                or re.fullmatch(rf"[0-9a-f]{{{oid_length}}}", oid_value) is None
            ):
                raise FrozenError(
                    "chain v2 produced-commit landing is malformed", chain_id=actual_id
                )
        for timestamp_key in ("committed_at", "closed_at", "recovered_at", "aborted_at"):
            value = commit_result.get(timestamp_key)
            if value is not None:
                try:
                    parse_time(value)
                except (TypeError, ValueError) as exc:
                    raise FrozenError(
                        "chain v2 produced-commit timestamps are malformed",
                        chain_id=actual_id,
                    ) from exc
    elif set(candidate_record) != {"sha256", "computed_at"}:
        raise FrozenError("chain legacy candidate record is malformed", chain_id=actual_id)
    elif candidate is not None:
        try:
            parse_time(str(candidate_record.get("computed_at")))
        except (TypeError, ValueError) as exc:
            raise FrozenError(
                "chain legacy candidate record is malformed", chain_id=actual_id
            ) from exc
    return state
