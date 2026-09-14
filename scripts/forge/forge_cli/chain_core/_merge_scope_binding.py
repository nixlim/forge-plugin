"""Extracted from scripts/forge/forge_cli/chain_core/__init__.py."""
from __future__ import annotations
from typing import Any, Mapping, Callable
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
import copy
from forge_cli.policy import sha256_bytes
from pathlib import Path


def _merge_scope_environment_contract() -> dict[str, Any]:
    return {
        "unset_prefixes": ["GIT_CONFIG_"],
        "unset_names": sorted(_MERGE_SCOPE_UNSET),
        "overlay": dict(sorted(_MERGE_SCOPE_OVERLAY.items())),
    }


def _validate_merge_scope_request(
    value: object,
    *,
    state: Mapping[str, Any],
) -> dict[str, Any] | None:
    binding = state.get("run_binding")
    if binding is None:
        if value is not None:
            raise ValueError("unbound merge scope request is not null")
        return None
    if not isinstance(binding, Mapping) or not isinstance(value, dict) or set(value) != {
        "run_id",
        "task_id",
        "task_files",
        "admitted_scope",
        "command_template",
        "command_template_digest",
        "environment_digest",
    }:
        raise ValueError("run-bound merge scope request is malformed")
    template = value.get("command_template")
    candidate = state.get("candidate")
    intent = state.get("integration", {}).get("intent")
    expected_head = (
        intent.get("pre_fetch_head")
        if isinstance(intent, Mapping)
        else candidate.get("candidate_head")
        if isinstance(candidate, Mapping)
        else None
    )
    if (
        value.get("run_id") != binding.get("run_id")
        or value.get("task_id") != binding.get("task_id")
        or not _valid_sorted_unique_strings(value.get("task_files"))
        or not _valid_sorted_unique_strings(value.get("admitted_scope"))
        or not isinstance(template, dict)
        or set(template)
        != {"schema", "worktree", "candidate_head", "remote_tip_source"}
        or template.get("schema") != "forge-run-scope-command-template/1"
        or template.get("worktree") != state.get("worktree", {}).get("path")
        or template.get("candidate_head") != expected_head
        or template.get("remote_tip_source")
        != "scope_fetch_binding.remote_tip"
        or value.get("command_template_digest")
        != sha256_bytes(canonical_bytes(template))
        or value.get("environment_digest")
        != sha256_bytes(canonical_bytes(_merge_scope_environment_contract()))
    ):
        raise ValueError("run-bound merge scope request binding is invalid")
    return copy.deepcopy(value)


def _merge_retained_inflight(fence: PublishedLockRecord) -> dict[str, Any]:
    return {
        "path": fence.path,
        "device": fence.device,
        "inode": fence.inode,
        "inflight_digest": fence.digest,
        **copy.deepcopy(fence.record),
    }


def _validate_merge_scope_fetch_binding(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "schema",
        "chain_id",
        "fetch_intent_digest",
        "scope_request_digest",
        "candidate_head",
        "remote_tip",
        "command_template_digest",
        "command_digest",
        "full_patch_command_digest",
        "full_patch_output_digest",
        "environment_digest",
        "publication",
        "retained_inflight",
        "child_result",
        "recorded_at",
        "digest",
    }:
        raise ValueError("scope-fetch binding has an invalid key set")
    body = {name: value[name] for name in value if name != "digest"}
    publication = value.get("publication")
    retained = value.get("retained_inflight")
    child = value.get("child_result")
    retained_keys = {
        "path",
        "device",
        "inode",
        "inflight_digest",
        "schema",
        "owner_kind",
        "chain_id",
        "operation",
        "host",
        "pid",
        "pgid",
        "started_at",
        "intent_digest",
        "nonce",
    }
    if not isinstance(retained, dict) or set(retained) != retained_keys:
        raise ValueError("scope-fetch retained fence is malformed")
    retained_record = {
        name: copy.deepcopy(retained[name])
        for name in (
            "schema",
            "owner_kind",
            "chain_id",
            "operation",
            "host",
            "pid",
            "pgid",
            "started_at",
            "intent_digest",
            "nonce",
        )
    }
    try:
        _validate_fence_record(retained_record)
    except ValueError as exc:
        raise ValueError("scope-fetch retained fence record is invalid") from exc
    bound = value.get("scope_request_digest") is not None
    nullable_scope_members = (
        value.get("scope_request_digest"),
        value.get("command_template_digest"),
        value.get("command_digest"),
    )
    if (
        value.get("schema") != "forge-run-scope-fetch-binding/2"
        or not isinstance(value.get("chain_id"), str)
        or CHAIN_ID_RE.fullmatch(str(value["chain_id"])) is None
        or any(
            not isinstance(value.get(name), str)
            or SHA256_RE.fullmatch(value[name]) is None
            for name in (
                "fetch_intent_digest",
                "full_patch_command_digest",
                "full_patch_output_digest",
                "environment_digest",
                "digest",
            )
        )
        or (
            bound
            and any(
                not isinstance(member, str)
                or SHA256_RE.fullmatch(member) is None
                for member in nullable_scope_members
            )
        )
        or (not bound and nullable_scope_members != (None, None, None))
        or not isinstance(value.get("candidate_head"), str)
        or COMMIT_RE.fullmatch(value["candidate_head"]) is None
        or not isinstance(value.get("remote_tip"), str)
        or COMMIT_RE.fullmatch(value["remote_tip"]) is None
        or not _valid_utc_second(value.get("recorded_at"))
        or not isinstance(publication, dict)
        or set(publication)
        != {"canonical_path", "temporary_path", "device", "inode"}
        or not isinstance(publication.get("canonical_path"), str)
        or publication.get("temporary_path")
        != f"{publication.get('canonical_path')}.tmp-{retained.get('nonce') if isinstance(retained, Mapping) else ''}"
        or not _valid_nonnegative_int(publication.get("device"))
        or not _valid_nonnegative_int(publication.get("inode"))
        or not isinstance(retained.get("path"), str)
        or not Path(str(retained["path"])).is_absolute()
        or Path(str(retained["path"])).name != COMMON_LOCK_INFLIGHT_NAME
        or not _valid_nonnegative_int(retained.get("device"))
        or not _valid_nonnegative_int(retained.get("inode"))
        or retained.get("inflight_digest")
        != sha256_bytes(canonical_bytes(retained_record))
        or retained.get("schema") != "forge-rebase-inflight/1"
        or retained.get("owner_kind") != "merge"
        or retained.get("chain_id") != value.get("chain_id")
        or retained.get("operation") not in {"fetch", "tip-resolution"}
        or retained.get("intent_digest") != value.get("fetch_intent_digest")
        or not isinstance(retained.get("inflight_digest"), str)
        or SHA256_RE.fullmatch(retained["inflight_digest"]) is None
        or not isinstance(child, dict)
        or set(child)
        != {
            "operation",
            "intent_digest",
            "inflight_digest",
            "host",
            "pid",
            "pgid",
            "exit",
            "output_digest",
            "launch_failed",
            "timed_out",
            "output_limit_exceeded",
            "group_dead_at",
            "resolved_tip",
            "recorded_at",
        }
        or any(
            child.get(name) != retained.get(name)
            for name in (
                "operation",
                "intent_digest",
                "inflight_digest",
                "host",
                "pid",
                "pgid",
            )
        )
        or not _valid_nonnegative_int(child.get("exit"))
        or child.get("exit") != 0
        or child.get("launch_failed") is not False
        or child.get("timed_out") is not False
        or child.get("output_limit_exceeded") is not False
        or not isinstance(child.get("output_digest"), str)
        or SHA256_RE.fullmatch(child["output_digest"]) is None
        or not _valid_utc_second(child.get("group_dead_at"))
        or not _valid_utc_second(child.get("recorded_at"))
        or child.get("resolved_tip") != value.get("remote_tip")
        or (
            bound
            and child.get("output_digest")
            != value.get("child_result", {}).get("output_digest")
        )
        or (
            not bound
            and child.get("output_digest") != sha256_bytes(b"")
        )
        or value.get("digest") != sha256_bytes(canonical_bytes(body))
    ):
        raise ValueError("scope-fetch binding fields are invalid")
    return copy.deepcopy(value)


def _merge_scope_binding_names(
    chain_id: str, fetch_intent_digest: str, fence: PublishedLockRecord
) -> tuple[str, str, str, str]:
    canonical_name = f"scope-fetch-{fetch_intent_digest}-{fence.digest}.json"
    temporary_name = f"{canonical_name}.tmp-{fence.record['nonce']}"
    canonical_path = f".forge/chains/{chain_id}/{canonical_name}"
    temporary_path = f"{canonical_path}.tmp-{fence.record['nonce']}"
    return canonical_name, temporary_name, canonical_path, temporary_path


def _merge_full_patch_argv(
    worktree: Path, remote_tip: str, candidate_head: str
) -> list[str]:
    """Return Revision-12's exact fixed-object full-patch argv."""

    return [
        "git",
        "--no-pager",
        "--no-replace-objects",
        "-c",
        "core.quotePath=false",
        "-c",
        "color.ui=false",
        "-c",
        "diff.renames=copies",
        "-c",
        "diff.renameLimit=0",
        "-c",
        "diff.algorithm=myers",
        "-C",
        str(worktree),
        "diff",
        "--patch",
        "--no-color",
        "-O/dev/null",
        "--find-renames=50%",
        "--find-copies=50%",
        "--find-copies-harder",
        "-l0",
        "--no-ext-diff",
        "--no-textconv",
        "--ignore-submodules=none",
        "--diff-filter=ACDMRTUXB",
        f"{remote_tip}...{candidate_head}",
        "--",
    ]


def _merge_scope_argv(worktree: Path, remote_tip: str, candidate_head: str) -> list[str]:
    return [
        "git",
        "--no-pager",
        "--no-replace-objects",
        "-c",
        "core.quotePath=false",
        "-c",
        "color.ui=false",
        "-c",
        "diff.renames=copies",
        "-c",
        "diff.renameLimit=0",
        "-c",
        "diff.algorithm=myers",
        "-C",
        str(worktree),
        "diff",
        "--no-color",
        "-O/dev/null",
        "--name-status",
        "-z",
        "--find-renames=50%",
        "--find-copies=50%",
        "--find-copies-harder",
        "-l0",
        "--no-ext-diff",
        "--no-textconv",
        "--ignore-submodules=none",
        "--diff-filter=ACDMRTUXB",
        f"{remote_tip}...{candidate_head}",
        "--",
    ]


def _merge_scope_binding_validator(
    state: Mapping[str, Any],
    *,
    fetch_intent_digest: str,
    scope_request: Mapping[str, Any] | None,
    fence: PublishedLockRecord,
    result: FencedProcessResult | None = None,
) -> Callable[[Any], dict[str, Any]]:
    """Bind strict sidecar bytes to the authenticated intent and live fence."""

    chain_id = str(state["chain_id"])
    _validate_fence_record(fence.record)
    if scope_request is not None:
        _validate_merge_scope_request(dict(scope_request), state=state)
    canonical_name, _temporary_name, canonical_path, temporary_path = (
        _merge_scope_binding_names(chain_id, fetch_intent_digest, fence)
    )
    del canonical_name
    intent = state.get("integration", {}).get("intent")
    expected_head = (
        intent.get("pre_fetch_head") if isinstance(intent, Mapping) else None
    )
    retained = _merge_retained_inflight(fence)

    def validate(value: Any) -> dict[str, Any]:
        binding = _validate_merge_scope_fetch_binding(value)
        worktree = Path(str(state["worktree"]["path"]))
        command = (
            _merge_scope_argv(
                worktree,
                str(binding["remote_tip"]),
                str(binding["candidate_head"]),
            )
            if scope_request is not None
            else None
        )
        full_patch_command = _merge_full_patch_argv(
            worktree,
            str(binding["remote_tip"]),
            str(binding["candidate_head"]),
        )
        child = binding["child_result"]
        metadata = result.metadata if result is not None else None
        if (
            fence.record.get("owner_kind") != "merge"
            or fence.record.get("chain_id") != chain_id
            or fence.record.get("operation") not in {"fetch", "tip-resolution"}
            or fence.record.get("intent_digest") != fetch_intent_digest
            or fence.digest != sha256_bytes(canonical_bytes(fence.record))
            or binding.get("chain_id") != chain_id
            or binding.get("fetch_intent_digest") != fetch_intent_digest
            or binding.get("scope_request_digest")
            != (
                sha256_bytes(canonical_bytes(dict(scope_request)))
                if scope_request is not None
                else None
            )
            or binding.get("candidate_head") != expected_head
            or binding.get("command_template_digest")
            != (
                scope_request.get("command_template_digest")
                if scope_request is not None
                else None
            )
            or binding.get("environment_digest")
            != sha256_bytes(canonical_bytes(_merge_scope_environment_contract()))
            or binding.get("command_digest")
            != (
                sha256_bytes(canonical_bytes(command))
                if command is not None
                else None
            )
            or binding.get("full_patch_command_digest")
            != sha256_bytes(canonical_bytes(full_patch_command))
            or binding.get("publication", {}).get("canonical_path")
            != canonical_path
            or binding.get("publication", {}).get("temporary_path")
            != temporary_path
            or binding.get("retained_inflight") != retained
            or retained.get("path")
            != str(
                Path(str(state["worktree"]["common_dir"]))
                / COMMON_LOCK_INFLIGHT_NAME
            )
            or retained.get("device") != fence.device
            or retained.get("inode") != fence.inode
            or (
                result is not None
                and (
                    child.get("exit") != result.returncode
                    or child.get("output_digest") != result.output_digest
                    or child.get("launch_failed") != result.launch_failed
                    or child.get("timed_out") != result.timed_out
                    or child.get("output_limit_exceeded") != result.output_limit
                    or not isinstance(metadata, Mapping)
                    or binding.get("full_patch_output_digest")
                    != metadata.get("full_patch", {}).get("output_digest")
                )
            )
        ):
            raise ValueError("scope-fetch binding diverges from its authenticated context")
        return binding

    return validate
