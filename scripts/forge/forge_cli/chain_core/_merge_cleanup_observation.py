"""Extracted from scripts/forge/forge_cli/chain_core/__init__.py."""
from __future__ import annotations
import base64
import binascii
from typing import Any, Mapping
from forge_cli.chain_core._bootstrap_observation import _bootstrap_fetch_observation_record_valid as _bootstrap_fetch_observation_record_valid, _bootstrap_fetch_observation_transition_valid as _bootstrap_fetch_observation_transition_valid
from forge_cli.chain_core._candidate_v2 import candidate_is_v2 as candidate_is_v2, _candidate_binding_for_state_with_candidate_v2 as _candidate_binding_for_state_with_candidate_v2, _binding_shape_valid_with_candidate_v2 as _binding_shape_valid_with_candidate_v2, _event_batch_records_with_candidate_v2 as _event_batch_records_with_candidate_v2, _binding_matches_source_fact_with_candidate_v2 as _binding_matches_source_fact_with_candidate_v2, _binding_is_current_with_candidate_v2 as _binding_is_current_with_candidate_v2
from forge_cli.chain_core._chain_state import validate_state as validate_state
from forge_cli.chain_core._controls import COMMON_LOCK_OWNER_KINDS as COMMON_LOCK_OWNER_KINDS, COMMON_LOCK_OPERATIONS as COMMON_LOCK_OPERATIONS, COMMON_LOCK_FENCE_OPERATIONS as COMMON_LOCK_FENCE_OPERATIONS, COMMON_LOCK_RECOVERY_KINDS as COMMON_LOCK_RECOVERY_KINDS, _COMMON_LOCK_OWNER_KEYS as _COMMON_LOCK_OWNER_KEYS, _COMMON_LOCK_FENCE_KEYS as _COMMON_LOCK_FENCE_KEYS, _COMMON_LOCK_RECOVERY_KEYS as _COMMON_LOCK_RECOVERY_KEYS, _CHAIN_LEASE_KEYS as _CHAIN_LEASE_KEYS, _REQUIRED_COMMON_LOCK_CONTROLS as _REQUIRED_COMMON_LOCK_CONTROLS, COMMON_LOCK_CONTROLS as COMMON_LOCK_CONTROLS, CHAIN_TOMBSTONE_SCHEMA as CHAIN_TOMBSTONE_SCHEMA, CHAIN_TOMBSTONE_EVENT as CHAIN_TOMBSTONE_EVENT, CHAIN_TOMBSTONE_KEYS as CHAIN_TOMBSTONE_KEYS, _REQUIRED_MERGE_STORE_CONTROLS as _REQUIRED_MERGE_STORE_CONTROLS, MERGE_STORE_CONTROLS as MERGE_STORE_CONTROLS, _REQUIRED_MERGE_ADAPTER_CONTROLS as _REQUIRED_MERGE_ADAPTER_CONTROLS, MERGE_ADAPTER_CONTROLS as MERGE_ADAPTER_CONTROLS, _REQUIRED_MERGE_INTEGRATION_CONTROLS as _REQUIRED_MERGE_INTEGRATION_CONTROLS, MERGE_INTEGRATION_CONTROLS as MERGE_INTEGRATION_CONTROLS, INGEST_PROOF_ORDER as INGEST_PROOF_ORDER, _REQUIRED_INGEST_PROOF_CONTROLS as _REQUIRED_INGEST_PROOF_CONTROLS, INGEST_PROOF_CONTROLS as INGEST_PROOF_CONTROLS, _MERGE_CLEANUP_INTENT_SCHEMA as _MERGE_CLEANUP_INTENT_SCHEMA, _MERGE_CLEANUP_RESULT_SCHEMA as _MERGE_CLEANUP_RESULT_SCHEMA, _MERGE_CLEANUP_CLOSE_SCHEMA as _MERGE_CLEANUP_CLOSE_SCHEMA, _MERGE_CLEANUP_RECOVERY_SCHEMA as _MERGE_CLEANUP_RECOVERY_SCHEMA, _MERGE_CLEANUP_FENCE_OPERATIONS as _MERGE_CLEANUP_FENCE_OPERATIONS, _EPOCH_FETCH_OBSERVATION_SCHEMA as _EPOCH_FETCH_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA, _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA as _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA
from forge_cli.chain_core._core import canonical_bytes as canonical_bytes, _chain_storage_root as _chain_storage_root, _validated_commitment_path as _validated_commitment_path, _parsed_run_captured_path as _parsed_run_captured_path, _require_ingest_proof as _require_ingest_proof, iso_z as iso_z, parse_time as parse_time, _require_merge_store_control as _require_merge_store_control, _require_merge_adapter_control as _require_merge_adapter_control, _require_merge_integration_control as _require_merge_integration_control, _require_common_lock_control as _require_common_lock_control, CommonLockBoundaryCrash as CommonLockBoundaryCrash, PublishedLockRecord as PublishedLockRecord, CommonLockInspection as CommonLockInspection, CommonLockUnavailable as CommonLockUnavailable, CommonLockReleaseFailure as CommonLockReleaseFailure, ChainLeaseUnavailable as ChainLeaseUnavailable, FencedChildSurvived as FencedChildSurvived, _valid_utc_second as _valid_utc_second, _valid_positive_int as _valid_positive_int, _valid_nonnegative_int as _valid_nonnegative_int, _valid_host as _valid_host, _valid_nonce as _valid_nonce, _valid_nullable_chain as _valid_nullable_chain, _write_all as _write_all, _PublicationCleanupFailure as _PublicationCleanupFailure, _process_probe as _process_probe, _group_probe as _group_probe, _sleep_with_deadline as _sleep_with_deadline, _require_deadline_open as _require_deadline_open, FencedProcessResult as FencedProcessResult, merge_gate_intent_digest as merge_gate_intent_digest, _forge_command as _forge_command, MergeRunTaskSnapshot as MergeRunTaskSnapshot, _merge_refusal as _merge_refusal, _valid_sorted_unique_strings as _valid_sorted_unique_strings
from forge_cli.chain_core._fenced_child import _BlockedFenceChild as _BlockedFenceChild, _pipe_cloexec as _pipe_cloexec, _read_child_ack as _read_child_ack, _waitpid_nohang as _waitpid_nohang, _wait_for_child_exit as _wait_for_child_exit, _spawn_blocked_fence_child as _spawn_blocked_fence_child, _terminate_fenced_group as _terminate_fenced_group, _stop_unstarted_child as _stop_unstarted_child, _collect_fenced_child as _collect_fenced_child
from forge_cli.chain_core._ingest_capture import _read_ingest_input as _read_ingest_input, _capture_ingest_blob as _capture_ingest_blob, _capture_run_evidence as _capture_run_evidence, _capture_ingest_record_evidence as _capture_ingest_record_evidence
from forge_cli.chain_core._ingest_currency import _ingest_captured_paths as _ingest_captured_paths, _ingest_step_is_current as _ingest_step_is_current, _ingest_secret_scan_is_current as _ingest_secret_scan_is_current, _prove_ingest_live_chain as _prove_ingest_live_chain
from forge_cli.chain_core._lock_record_validators import _validate_owner_record as _validate_owner_record, _validate_fence_record as _validate_fence_record, _validate_recovery_record as _validate_recovery_record, _validate_chain_lease_record as _validate_chain_lease_record
from forge_cli.chain_core._merge_cleanup_intent import _recovery_event_intent as _recovery_event_intent, _recovery_cleanup_intent as _recovery_cleanup_intent, _merge_cleanup_expected_subject as _merge_cleanup_expected_subject, _merge_cleanup_expected_argv as _merge_cleanup_expected_argv, _merge_cleanup_intent_valid as _merge_cleanup_intent_valid
from forge_cli.chain_core._merge_events import _merge_event_outbox as _merge_event_outbox, _merge_payload_delta as _merge_payload_delta, reduce_merge_event as reduce_merge_event
from forge_cli.chain_core._merge_plan import _merge_plan_position_fact as _merge_plan_position_fact, _merge_carried_gate_steps as _merge_carried_gate_steps, _merge_gate_step_generation_digests as _merge_gate_step_generation_digests, _merge_current_authority_valid as _merge_current_authority_valid, _merge_remote_only_equality_proof as _merge_remote_only_equality_proof, _merge_carry_payload_valid as _merge_carry_payload_valid, _merge_plan_transition_valid as _merge_plan_transition_valid
from forge_cli.chain_core._merge_rebase import _parse_registered_worktrees as _parse_registered_worktrees, _merge_rebase_action as _merge_rebase_action, _merge_rebase_result_classification as _merge_rebase_result_classification, _merge_containment as _merge_containment, _merge_old_tip_all_false as _merge_old_tip_all_false, _merge_latest_contained_attempt as _merge_latest_contained_attempt, _merge_inactive_post_attempt_recovery_ready as _merge_inactive_post_attempt_recovery_ready, _remote_observation_heads as _remote_observation_heads, _remote_observation_fetch_argv as _remote_observation_fetch_argv, _remote_containment_argv as _remote_containment_argv
from forge_cli.chain_core._merge_state_shape import _merge_gate_plan_valid as _merge_gate_plan_valid, _merge_epoch_valid as _merge_epoch_valid, _merge_bootstrap_classification_pending as _merge_bootstrap_classification_pending, _merge_revision9_compatibility_view as _merge_revision9_compatibility_view, _merge_state_shape_valid as _merge_state_shape_valid, _merge_ingest_state_shape_valid as _merge_ingest_state_shape_valid, _merge_history_uses_additive_grammar as _merge_history_uses_additive_grammar
from forge_cli.chain_core._receipt_snapshot import _ReceiptRunSnapshot as _ReceiptRunSnapshot, _chain_receipt_snapshot_lock as _chain_receipt_snapshot_lock, _receipt_run_snapshot as _receipt_run_snapshot
from forge_cli.chain_core._repository import Repository as Repository, _committed_changelog_output_paths as _committed_changelog_output_paths
from forge_cli.chain_core._state import SCHEMA as SCHEMA, KIND as KIND, FRESH_REVIEWER_EVALS_GATE as FRESH_REVIEWER_EVALS_GATE, FRESH_REVIEWER_EVALS_REQUESTS as FRESH_REVIEWER_EVALS_REQUESTS, FRESH_REVIEWER_EVALS_REQUESTED_EVENT as FRESH_REVIEWER_EVALS_REQUESTED_EVENT, STATES as STATES, STATE_KEYS as STATE_KEYS, EVENT_KEYS as EVENT_KEYS, MERGE_STATE_KEYS as MERGE_STATE_KEYS, _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES as _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES, _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES as _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES, MERGE_EVENT_KEYS as MERGE_EVENT_KEYS, MERGE_EVENT_NAMES as MERGE_EVENT_NAMES, MERGE_CONSEQUENTIAL_EVENTS as MERGE_CONSEQUENTIAL_EVENTS, TIER_RANK as TIER_RANK, INACTIVE_SECONDS as INACTIVE_SECONDS, FENCED_CHILD_ACK_TIMEOUT_SECONDS as FENCED_CHILD_ACK_TIMEOUT_SECONDS, FENCED_CHILD_DRAIN_SECONDS as FENCED_CHILD_DRAIN_SECONDS, FENCED_CHILD_DRAIN_CAP_BYTES as FENCED_CHILD_DRAIN_CAP_BYTES, FENCED_CHILD_STOP_GRACE_SECONDS as FENCED_CHILD_STOP_GRACE_SECONDS, FENCED_CHILD_REAP_SECONDS as FENCED_CHILD_REAP_SECONDS, ZERO_DIGEST as ZERO_DIGEST, COMMON_LOCK_TIMEOUT_SECONDS as COMMON_LOCK_TIMEOUT_SECONDS, COMMON_LOCK_POLL_SECONDS as COMMON_LOCK_POLL_SECONDS, COMMON_LOCK_RECORD_CAP_BYTES as COMMON_LOCK_RECORD_CAP_BYTES, MERGE_SCOPE_BINDING_CAP_BYTES as MERGE_SCOPE_BINDING_CAP_BYTES, COMMON_LOCK_INTENT_NAME as COMMON_LOCK_INTENT_NAME, COMMON_LOCK_DIRECTORY_NAME as COMMON_LOCK_DIRECTORY_NAME, COMMON_LOCK_OWNER_NAME as COMMON_LOCK_OWNER_NAME, COMMON_LOCK_FLOCK_NAME as COMMON_LOCK_FLOCK_NAME, COMMON_LOCK_RECOVERY_NAME as COMMON_LOCK_RECOVERY_NAME, COMMON_LOCK_INFLIGHT_NAME as COMMON_LOCK_INFLIGHT_NAME, CHAIN_ID_RE as CHAIN_ID_RE, SHA256_RE as SHA256_RE, COMMIT_RE as COMMIT_RE, RUN_ID_RE as RUN_ID_RE, _WORKTREE_LOCKS_GUARD as _WORKTREE_LOCKS_GUARD, _WORKTREE_LOCKS as _WORKTREE_LOCKS, _WORKTREE_LOCK_STATE as _WORKTREE_LOCK_STATE, _exclusive_descriptor_lock as _exclusive_descriptor_lock, _MERGE_REMOTE_ONLY_IDENTITY_FIELDS as _MERGE_REMOTE_ONLY_IDENTITY_FIELDS, _MERGE_SCOPE_UNSET as _MERGE_SCOPE_UNSET, _MERGE_SCOPE_OVERLAY as _MERGE_SCOPE_OVERLAY
from forge_cli.policy import sha256_bytes


def _merge_cleanup_process_output(process: Mapping[str, Any]) -> bytes | None:
    encoded = process.get("output_base64")
    if not isinstance(encoded, str):
        return None
    try:
        output = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        return None
    return (
        output
        if base64.b64encode(output).decode("ascii") == encoded
        else None
    )


def _merge_cleanup_process_complete(
    process: Mapping[str, Any], *returncodes: int
) -> bool:
    return bool(
        process.get("authorized") is True
        and type(process.get("returncode")) is int
        and process.get("returncode") in returncodes
        and process.get("launch_failed") is False
        and process.get("timed_out") is False
        and process.get("output_limit") is False
        and process.get("group_survived") is False
    )


def _merge_cleanup_branch_observation(
    process: Mapping[str, Any], branch: object
) -> dict[str, Any]:
    exists: bool | None = None
    oid: str | None = None
    output = _merge_cleanup_process_output(process)
    if _merge_cleanup_process_complete(process, 0) and isinstance(output, bytes):
        rows = output.splitlines()
        if len(rows) == 1:
            try:
                candidate_oid = rows[0].decode("ascii")
            except UnicodeDecodeError:
                candidate_oid = ""
            if COMMIT_RE.fullmatch(candidate_oid):
                exists = True
                oid = candidate_oid
    elif _merge_cleanup_process_complete(process, 1) and output == b"":
        exists = False
    return {"branch": branch, "exists": exists, "oid": oid}


def _merge_cleanup_worktree_inventory(
    process: Mapping[str, Any], path: object
) -> tuple[bool | None, str | None, str | None]:
    output = _merge_cleanup_process_output(process)
    if not (
        isinstance(path, str)
        and isinstance(output, bytes)
        and _merge_cleanup_process_complete(process, 0)
    ):
        return None, None, None
    try:
        inventory = _parse_registered_worktrees(output)
    except OSError:
        return None, None, None
    matches = [item for item in inventory if item.get("worktree") == path]
    if not matches:
        return False, None, None
    if len(matches) != 1:
        return None, None, None
    observed_head = matches[0].get("HEAD")
    observed_branch = matches[0].get("branch")
    head = (
        observed_head
        if isinstance(observed_head, str)
        and COMMIT_RE.fullmatch(observed_head)
        else None
    )
    branch = observed_branch if isinstance(observed_branch, str) else None
    return True, head, branch


def _merge_cleanup_fetch_head_bytes(
    raw: bytes,
) -> tuple[bool | None, str | None]:
    if (
        len(raw) > MERGE_SCOPE_BINDING_CAP_BYTES
        or not raw.endswith(b"\n")
        or len(raw.splitlines()) != 1
    ):
        return None, None
    raw_oid = raw.split(b"\t", 1)[0]
    try:
        oid = raw_oid.decode("ascii")
    except UnicodeDecodeError:
        return None, None
    return (
        (True, oid)
        if COMMIT_RE.fullmatch(oid) is not None
        else (None, None)
    )


def _merge_cleanup_observation_valid(
    operation: str,
    observation: object,
    subject: Mapping[str, Any],
    process: Mapping[str, Any],
    outcome: str,
) -> bool:
    if not isinstance(observation, Mapping):
        return False
    complete = bool(
        process.get("authorized") is True
        and process.get("launch_failed") is False
        and process.get("timed_out") is False
        and process.get("output_limit") is False
        and process.get("group_survived") is False
    )
    if process.get("authorized") is False:
        no_execution = {
            "remote-fetch": {
                "exists": None,
                "oid": None,
                "fetch_head_base64": None,
                "fetch_head_digest": None,
            },
            "remote-containment": {
                "landed_head": subject.get("landed_head"),
                "remote_tip": subject.get("remote_tip"),
                "contained": None,
            },
            "worktree-observation": {
                "path": subject.get("path"),
                "path_exists": None,
                "registered": None,
                "head": None,
                "branch": None,
            },
            "worktree-remove": {
                "path": subject.get("path"),
                "exists": None,
            },
            "branch-observation": {
                "branch": subject.get("branch"),
                "exists": None,
                "oid": None,
            },
            "branch-delete": {
                "branch": subject.get("branch"),
                "expected_oid": subject.get("candidate_head"),
                "deleted": None,
            },
        }.get(operation)
        return bool(
            no_execution is not None
            and dict(observation) == no_execution
            and outcome == "failed"
        )
    expected_outcome = "failed"
    if operation == "remote-fetch":
        if set(observation) != {
            "exists",
            "oid",
            "fetch_head_base64",
            "fetch_head_digest",
        }:
            return False
        output = _merge_cleanup_process_output(process)
        raw_encoded = observation.get("fetch_head_base64")
        raw_digest = observation.get("fetch_head_digest")
        raw: bytes | None = None
        if isinstance(raw_encoded, str):
            try:
                raw = base64.b64decode(raw_encoded, validate=True)
            except (binascii.Error, ValueError):
                raw = None
            if not (
                isinstance(raw, bytes)
                and len(raw) <= MERGE_SCOPE_BINDING_CAP_BYTES
                and base64.b64encode(raw).decode("ascii") == raw_encoded
                and isinstance(raw_digest, str)
                and SHA256_RE.fullmatch(raw_digest) is not None
                and sha256_bytes(raw) == raw_digest
            ):
                return False
        elif raw_encoded is not None or raw_digest is not None:
            return False
        expected_exists: bool | None = None
        expected_oid: str | None = None
        if complete and process.get("returncode") == 0 and raw is not None:
            expected_exists, expected_oid = _merge_cleanup_fetch_head_bytes(raw)
        elif (
            complete
            and type(process.get("returncode")) is int
            and process.get("returncode") != 0
            and output
            == f"fatal: couldn't find remote ref {subject.get('destination_ref')}\n".encode(
                "utf-8"
            )
            and raw is None
        ):
            expected_exists = False
        if observation.get("exists") is not expected_exists or observation.get(
            "oid"
        ) != expected_oid:
            return False
        if expected_exists is True:
            expected_outcome = "passed"
    elif operation == "remote-containment":
        if set(observation) != {"landed_head", "remote_tip", "contained"}:
            return False
        contained = observation.get("contained")
        ordinary = bool(complete and process.get("returncode") in {0, 1})
        if (
            observation.get("landed_head") != subject.get("landed_head")
            or observation.get("remote_tip") != subject.get("remote_tip")
            or (type(contained) is bool) != ordinary
            or ordinary and contained is not (process.get("returncode") == 0)
            or not ordinary and contained is not None
        ):
            return False
        if ordinary and contained is True:
            expected_outcome = "passed"
    elif operation == "worktree-observation":
        if set(observation) != {
            "path",
            "path_exists",
            "registered",
            "head",
            "branch",
        }:
            return False
        registered, head, branch = _merge_cleanup_worktree_inventory(
            process, subject.get("path")
        )
        if (
            observation.get("path") != subject.get("path")
            or (
                type(observation.get("path_exists")) is not bool
                and observation.get("path_exists") is not None
            )
            or (
                observation.get("registered") is not registered
            )
            or observation.get("head") != head
            or observation.get("branch") != branch
        ):
            return False
        if (
            complete
            and process.get("returncode") == 0
            and registered is True
            and head == subject.get("candidate_head")
            and branch == subject.get("branch")
            and observation.get("path_exists") is True
        ):
            expected_outcome = "passed"
        elif (
            complete
            and process.get("returncode") == 0
            and registered is False
            and observation.get("path_exists") is False
        ):
            expected_outcome = "already-absent"
    elif operation == "worktree-remove":
        if set(observation) != {"path", "exists"} or (
            observation.get("path") != subject.get("path")
            or (
                type(observation.get("exists")) is not bool
                and observation.get("exists") is not None
            )
        ):
            return False
        if (
            complete
            and process.get("returncode") == 0
            and observation.get("exists") is False
        ):
            expected_outcome = "passed"
    elif operation == "branch-observation":
        if set(observation) != {"branch", "exists", "oid"}:
            return False
        expected = _merge_cleanup_branch_observation(
            process, subject.get("branch")
        )
        if dict(observation) != expected:
            return False
        exists = expected["exists"]
        oid = expected["oid"]
        if (
            complete
            and process.get("returncode") == 0
            and exists is True
            and oid == subject.get("candidate_head")
        ):
            expected_outcome = "passed"
        elif (
            complete
            and process.get("returncode") == 1
            and process.get("output_digest") == sha256_bytes(b"")
            and exists is False
        ):
            expected_outcome = "already-absent"
    elif operation == "branch-delete":
        if set(observation) != {"branch", "expected_oid", "deleted"}:
            return False
        deleted = observation.get("deleted")
        if (
            observation.get("branch") != subject.get("branch")
            or observation.get("expected_oid") != subject.get("candidate_head")
            or (deleted is not True and deleted is not None)
        ):
            return False
        if complete and process.get("returncode") == 0 and deleted is True:
            expected_outcome = "passed"
    else:
        return False
    return outcome == expected_outcome
