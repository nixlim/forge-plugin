"""Extracted from scripts/forge/forge_cli/chain_core/__init__.py."""
from __future__ import annotations
import json
import os
import stat
from pathlib import Path
from typing import Any, Callable, Mapping
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
import copy
import secrets


def _read_owned_record_at(
    parent: int,
    name: str,
    absolute_path: Path,
    validator: Callable[[Any], dict[str, Any]],
    *,
    cap: int = COMMON_LOCK_RECORD_CAP_BYTES,
) -> PublishedLockRecord:
    before = os.stat(name, dir_fd=parent, follow_symlinks=False)
    descriptor = os.open(
        name,
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NONBLOCK", 0),
        dir_fd=parent,
    )
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.geteuid()
            or stat.S_IMODE(opened.st_mode) != 0o600
            or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
        ):
            raise OSError("record is not the same owner-controlled mode-0600 regular file")
        chunks: list[bytes] = []
        size = 0
        while True:
            chunk = os.read(descriptor, min(4096, cap + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > cap:
                raise OSError("record exceeds its byte cap")
        raw = b"".join(chunks)
    finally:
        os.close(descriptor)
    try:
        decoded = raw.decode("utf-8", "strict")
        parsed = json.loads(decoded)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise OSError("record is not strict UTF-8 JSON") from exc
    record = validator(parsed)
    if canonical_bytes(record) != raw:
        raise OSError("record is not DM-013 canonical bytes")
    return PublishedLockRecord(
        path=str(absolute_path),
        device=before.st_dev,
        inode=before.st_ino,
        digest=sha256_bytes(raw),
        record=record,
        mode=stat.S_IMODE(before.st_mode),
        links=before.st_nlink,
    )


def _same_published_record(
    left: PublishedLockRecord, right: PublishedLockRecord
) -> bool:
    return (
        left.device == right.device
        and left.inode == right.inode
        and left.digest == right.digest
        and left.record == right.record
    )


def _open_lock_directory(common: int, common_dir: Path) -> int:
    descriptor = os.open(
        COMMON_LOCK_DIRECTORY_NAME,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        dir_fd=common,
    )
    opened = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(opened.st_mode)
        or opened.st_uid != os.geteuid()
        or stat.S_IMODE(opened.st_mode) != 0o700
    ):
        os.close(descriptor)
        raise OSError(f"{common_dir / COMMON_LOCK_DIRECTORY_NAME} is not mode-0700 owner-controlled")
    return descriptor


def _opaque_path_evidence_at(parent: int, name: str, path: Path) -> dict[str, Any]:
    try:
        observed = os.stat(name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        return {"path": str(path), "exists": False}
    result: dict[str, Any] = {
        "path": str(path),
        "exists": True,
        "device": observed.st_dev,
        "inode": observed.st_ino,
        "mode": stat.S_IMODE(observed.st_mode),
        "type": stat.S_IFMT(observed.st_mode),
    }
    if stat.S_ISREG(observed.st_mode):
        try:
            descriptor = os.open(
                name,
                os.O_RDONLY
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NONBLOCK", 0),
                dir_fd=parent,
            )
            try:
                raw = os.read(descriptor, COMMON_LOCK_RECORD_CAP_BYTES + 1)
            finally:
                os.close(descriptor)
            result["digest"] = sha256_bytes(raw)
            result["bytes"] = len(raw)
        except OSError as exc:
            result["read_error"] = str(exc)
    return result


def _inspect_common_lock_fd(common: int, common_dir: Path) -> CommonLockInspection:
    try:
        outer = _read_owned_record_at(
            common,
            COMMON_LOCK_INTENT_NAME,
            common_dir / COMMON_LOCK_INTENT_NAME,
            _validate_owner_record,
        )
    except FileNotFoundError:
        outer = None
    except (OSError, ValueError) as exc:
        return CommonLockInspection(
            "unprovable",
            detail=f"outer intent: {exc}",
            artifacts={
                "outer": _opaque_path_evidence_at(
                    common,
                    COMMON_LOCK_INTENT_NAME,
                    common_dir / COMMON_LOCK_INTENT_NAME,
                )
            },
        )
    try:
        lockdir = _open_lock_directory(common, common_dir)
    except FileNotFoundError:
        if outer is None:
            return CommonLockInspection("free")
        return CommonLockInspection("outer-only", outer=outer)
    except OSError as exc:
        return CommonLockInspection(
            "unprovable",
            outer=outer,
            detail=f"lock directory: {exc}",
            artifacts={
                "lockdir": _opaque_path_evidence_at(
                    common,
                    COMMON_LOCK_DIRECTORY_NAME,
                    common_dir / COMMON_LOCK_DIRECTORY_NAME,
                )
            },
        )
    try:
        entries = sorted(os.listdir(lockdir), key=os.fsencode)
        if outer is None:
            return CommonLockInspection(
                "unprovable",
                detail="lock directory exists without an outer intent",
                artifacts={
                    "lockdir": _opaque_path_evidence_at(
                        common,
                        COMMON_LOCK_DIRECTORY_NAME,
                        common_dir / COMMON_LOCK_DIRECTORY_NAME,
                    )
                },
            )
        if not entries:
            return CommonLockInspection("outer-empty-directory", outer=outer)
        if entries != [COMMON_LOCK_OWNER_NAME]:
            return CommonLockInspection(
                "unprovable",
                outer=outer,
                detail="lock directory has a missing or extra entry",
                artifacts={"lockdir_entries": entries},
            )
        try:
            inner = _read_owned_record_at(
                lockdir,
                COMMON_LOCK_OWNER_NAME,
                common_dir / COMMON_LOCK_DIRECTORY_NAME / COMMON_LOCK_OWNER_NAME,
                _validate_owner_record,
            )
        except (OSError, ValueError) as exc:
            return CommonLockInspection(
                "unprovable",
                outer=outer,
                detail=f"inner owner: {exc}",
                artifacts={
                    "inner": _opaque_path_evidence_at(
                        lockdir,
                        COMMON_LOCK_OWNER_NAME,
                        common_dir
                        / COMMON_LOCK_DIRECTORY_NAME
                        / COMMON_LOCK_OWNER_NAME,
                    )
                },
            )
        if not _same_published_record(outer, inner):
            return CommonLockInspection(
                "unprovable",
                outer=outer,
                inner=inner,
                detail="outer and inner owners do not share one inode and digest",
            )
        return CommonLockInspection("complete", outer=outer, inner=inner)
    finally:
        os.close(lockdir)


def _create_private_record_at(
    parent: int,
    parent_path: Path,
    prefix: str,
    record: Mapping[str, Any],
    *,
    boundary: Callable[[str], None] | None,
    stage: str,
) -> tuple[str, PublishedLockRecord]:
    encoded = canonical_bytes(dict(record))
    temporary = f".{prefix}.{secrets.token_hex(16)}.tmp"
    descriptor = os.open(
        temporary,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        0o600,
        dir_fd=parent,
    )
    opened: os.stat_result | None = None
    descriptor_open = True
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_uid != os.geteuid():
            raise OSError("private record is not owner-controlled and regular")
        os.fchmod(descriptor, 0o600)
        _write_all(descriptor, encoded)
        os.fsync(descriptor)
        opened = os.fstat(descriptor)
        os.close(descriptor)
        descriptor_open = False
    except BaseException as write_error:
        cleanup_errors: list[str] = []
        try:
            expected = opened if opened is not None else os.fstat(descriptor)
            current = os.stat(temporary, dir_fd=parent, follow_symlinks=False)
            if (
                current.st_dev != expected.st_dev
                or current.st_ino != expected.st_ino
                or not stat.S_ISREG(current.st_mode)
            ):
                raise OSError("private record temporary name changed inode")
            os.unlink(temporary, dir_fd=parent)
            os.fsync(parent)
        except FileNotFoundError:
            pass
        except BaseException as exc:
            cleanup_errors.append(f"temporary: {exc}")
        if descriptor_open:
            try:
                os.close(descriptor)
                descriptor_open = False
            except OSError as exc:
                cleanup_errors.append(f"descriptor: {exc}")
        if cleanup_errors:
            raise _PublicationCleanupFailure(
                "private record cleanup could not prove durable removal: "
                + "; ".join(cleanup_errors)
            ) from write_error
        raise
    published = PublishedLockRecord(
        path=str(parent_path / temporary),
        device=opened.st_dev,
        inode=opened.st_ino,
        digest=sha256_bytes(encoded),
        record=copy.deepcopy(dict(record)),
        mode=0o600,
        links=opened.st_nlink,
    )
    if boundary is not None:
        boundary(stage)
    return temporary, published


def _publish_no_replace_link(
    source_parent: int,
    source: str,
    destination_parent: int,
    destination: str,
) -> None:
    _require_common_lock_control("no-replace-publication")
    os.link(
        source,
        destination,
        src_dir_fd=source_parent,
        dst_dir_fd=destination_parent,
        follow_symlinks=False,
    )


def _revalidate_record_at(
    parent: int,
    name: str,
    absolute_path: Path,
    expected: PublishedLockRecord,
    validator: Callable[[Any], dict[str, Any]],
) -> PublishedLockRecord:
    current = _read_owned_record_at(parent, name, absolute_path, validator)
    if not _same_published_record(current, expected):
        raise OSError(f"{absolute_path} no longer names the recorded inode/digest")
    return current


def _unlink_revalidated_record_at(
    parent: int,
    name: str,
    absolute_path: Path,
    expected: PublishedLockRecord,
    validator: Callable[[Any], dict[str, Any]],
) -> None:
    _require_common_lock_control("release-identity-revalidation")
    _revalidate_record_at(parent, name, absolute_path, expected, validator)
    os.unlink(name, dir_fd=parent)


def _record_at_if_present(
    parent: int,
    name: str,
    absolute_path: Path,
    validator: Callable[[Any], dict[str, Any]],
) -> PublishedLockRecord | None:
    try:
        return _read_owned_record_at(parent, name, absolute_path, validator)
    except FileNotFoundError:
        return None
