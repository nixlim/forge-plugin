"""Extracted from scripts/forge/forge_cli/chain_core/__init__.py."""
from __future__ import annotations
import contextlib
import copy
import hashlib
import json
import os
import re
import secrets
import socket
import stat
import sys
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from forge_cli.chain_core._bootstrap_observation import _bootstrap_fetch_observation_record_valid as _bootstrap_fetch_observation_record_valid, _bootstrap_fetch_observation_transition_valid as _bootstrap_fetch_observation_transition_valid
from forge_cli.chain_core._candidate_v2 import candidate_is_v2 as candidate_is_v2, _candidate_binding_for_state_with_candidate_v2 as _candidate_binding_for_state_with_candidate_v2, _binding_shape_valid_with_candidate_v2 as _binding_shape_valid_with_candidate_v2, _event_batch_records_with_candidate_v2 as _event_batch_records_with_candidate_v2, _binding_matches_source_fact_with_candidate_v2 as _binding_matches_source_fact_with_candidate_v2, _binding_is_current_with_candidate_v2 as _binding_is_current_with_candidate_v2
from forge_cli.chain_core._chain_state import validate_state as validate_state
from forge_cli.chain_core._controls import COMMON_LOCK_OWNER_KINDS as COMMON_LOCK_OWNER_KINDS, COMMON_LOCK_OPERATIONS as COMMON_LOCK_OPERATIONS, COMMON_LOCK_FENCE_OPERATIONS as COMMON_LOCK_FENCE_OPERATIONS, COMMON_LOCK_RECOVERY_KINDS as COMMON_LOCK_RECOVERY_KINDS, _COMMON_LOCK_OWNER_KEYS as _COMMON_LOCK_OWNER_KEYS, _COMMON_LOCK_FENCE_KEYS as _COMMON_LOCK_FENCE_KEYS, _COMMON_LOCK_RECOVERY_KEYS as _COMMON_LOCK_RECOVERY_KEYS, _CHAIN_LEASE_KEYS as _CHAIN_LEASE_KEYS, _REQUIRED_COMMON_LOCK_CONTROLS as _REQUIRED_COMMON_LOCK_CONTROLS, COMMON_LOCK_CONTROLS as COMMON_LOCK_CONTROLS, CHAIN_TOMBSTONE_SCHEMA as CHAIN_TOMBSTONE_SCHEMA, CHAIN_TOMBSTONE_EVENT as CHAIN_TOMBSTONE_EVENT, CHAIN_TOMBSTONE_KEYS as CHAIN_TOMBSTONE_KEYS, _REQUIRED_MERGE_STORE_CONTROLS as _REQUIRED_MERGE_STORE_CONTROLS, MERGE_STORE_CONTROLS as MERGE_STORE_CONTROLS, _REQUIRED_MERGE_ADAPTER_CONTROLS as _REQUIRED_MERGE_ADAPTER_CONTROLS, MERGE_ADAPTER_CONTROLS as MERGE_ADAPTER_CONTROLS, _REQUIRED_MERGE_INTEGRATION_CONTROLS as _REQUIRED_MERGE_INTEGRATION_CONTROLS, MERGE_INTEGRATION_CONTROLS as MERGE_INTEGRATION_CONTROLS, INGEST_PROOF_ORDER as INGEST_PROOF_ORDER, _REQUIRED_INGEST_PROOF_CONTROLS as _REQUIRED_INGEST_PROOF_CONTROLS, INGEST_PROOF_CONTROLS as INGEST_PROOF_CONTROLS, _MERGE_CLEANUP_INTENT_SCHEMA as _MERGE_CLEANUP_INTENT_SCHEMA, _MERGE_CLEANUP_RESULT_SCHEMA as _MERGE_CLEANUP_RESULT_SCHEMA, _MERGE_CLEANUP_CLOSE_SCHEMA as _MERGE_CLEANUP_CLOSE_SCHEMA, _MERGE_CLEANUP_RECOVERY_SCHEMA as _MERGE_CLEANUP_RECOVERY_SCHEMA, _MERGE_CLEANUP_FENCE_OPERATIONS as _MERGE_CLEANUP_FENCE_OPERATIONS, _EPOCH_FETCH_OBSERVATION_SCHEMA as _EPOCH_FETCH_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA, _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA as _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA
from forge_cli.chain_core._core import canonical_bytes as canonical_bytes, _chain_storage_root as _chain_storage_root, _validated_commitment_path as _validated_commitment_path, _parsed_run_captured_path as _parsed_run_captured_path, _require_ingest_proof as _require_ingest_proof, iso_z as iso_z, parse_time as parse_time, _require_merge_store_control as _require_merge_store_control, _require_merge_adapter_control as _require_merge_adapter_control, _require_merge_integration_control as _require_merge_integration_control, _require_common_lock_control as _require_common_lock_control, CommonLockBoundaryCrash as CommonLockBoundaryCrash, PublishedLockRecord as PublishedLockRecord, CommonLockInspection as CommonLockInspection, CommonLockUnavailable as CommonLockUnavailable, CommonLockReleaseFailure as CommonLockReleaseFailure, ChainLeaseUnavailable as ChainLeaseUnavailable, FencedChildSurvived as FencedChildSurvived, _valid_utc_second as _valid_utc_second, _valid_positive_int as _valid_positive_int, _valid_nonnegative_int as _valid_nonnegative_int, _valid_host as _valid_host, _valid_nonce as _valid_nonce, _valid_nullable_chain as _valid_nullable_chain, _write_all as _write_all, _PublicationCleanupFailure as _PublicationCleanupFailure, _process_probe as _process_probe, _group_probe as _group_probe, _sleep_with_deadline as _sleep_with_deadline, _require_deadline_open as _require_deadline_open, FencedProcessResult as FencedProcessResult, merge_gate_intent_digest as merge_gate_intent_digest, _forge_command as _forge_command, MergeRunTaskSnapshot as MergeRunTaskSnapshot, _merge_refusal as _merge_refusal, _valid_sorted_unique_strings as _valid_sorted_unique_strings
from forge_cli.chain_core._fenced_child import _BlockedFenceChild as _BlockedFenceChild, _pipe_cloexec as _pipe_cloexec, _read_child_ack as _read_child_ack, _waitpid_nohang as _waitpid_nohang, _wait_for_child_exit as _wait_for_child_exit, _spawn_blocked_fence_child as _spawn_blocked_fence_child, _terminate_fenced_group as _terminate_fenced_group, _stop_unstarted_child as _stop_unstarted_child, _collect_fenced_child as _collect_fenced_child
from forge_cli.chain_core._ingest_capture import _read_ingest_input as _read_ingest_input, _capture_ingest_blob as _capture_ingest_blob, _capture_run_evidence as _capture_run_evidence, _capture_ingest_record_evidence as _capture_ingest_record_evidence
from forge_cli.chain_core._ingest_currency import _ingest_captured_paths as _ingest_captured_paths, _ingest_step_is_current as _ingest_step_is_current, _ingest_secret_scan_is_current as _ingest_secret_scan_is_current, _prove_ingest_live_chain as _prove_ingest_live_chain
from forge_cli.chain_core._ingest_merge import _merge_ingest_binding as _merge_ingest_binding, _merge_gate_event_fact as _merge_gate_event_fact, _merge_current_gate_facts as _merge_current_gate_facts, _merge_ingest_record_templates as _merge_ingest_record_templates, _verify_and_build_merge_ingest_records as _verify_and_build_merge_ingest_records
from forge_cli.chain_core._lock_record_io import _read_owned_record_at as _read_owned_record_at, _same_published_record as _same_published_record, _open_lock_directory as _open_lock_directory, _opaque_path_evidence_at as _opaque_path_evidence_at, _inspect_common_lock_fd as _inspect_common_lock_fd, _create_private_record_at as _create_private_record_at, _publish_no_replace_link as _publish_no_replace_link, _revalidate_record_at as _revalidate_record_at, _unlink_revalidated_record_at as _unlink_revalidated_record_at, _record_at_if_present as _record_at_if_present
from forge_cli.chain_core._lock_record_validators import _validate_owner_record as _validate_owner_record, _validate_fence_record as _validate_fence_record, _validate_recovery_record as _validate_recovery_record, _validate_chain_lease_record as _validate_chain_lease_record
from forge_cli.chain_core._merge_candidate_observation import _merge_candidate_observation_record_valid as _merge_candidate_observation_record_valid, _merge_candidate_observation_transition_valid as _merge_candidate_observation_transition_valid, _merge_candidate_observation_evidence as _merge_candidate_observation_evidence, _merge_candidate_observation_evidence_valid as _merge_candidate_observation_evidence_valid
from forge_cli.chain_core._merge_candidate_observation_steps import _merge_candidate_observation_step_specs as _merge_candidate_observation_step_specs, _merge_candidate_observation_step_names as _merge_candidate_observation_step_names, _merge_candidate_observation_binding as _merge_candidate_observation_binding
from forge_cli.chain_core._merge_cleanup_history import _merge_cleanup_evidence_history as _merge_cleanup_evidence_history, _merge_cleanup_history_summary as _merge_cleanup_history_summary, _merge_cleanup_unmatched_intent as _merge_cleanup_unmatched_intent, _merge_cleanup_retry_proof_valid as _merge_cleanup_retry_proof_valid, _merge_cleanup_intent_transition_valid as _merge_cleanup_intent_transition_valid, _merge_history_has_git_mutation_intent as _merge_history_has_git_mutation_intent
from forge_cli.chain_core._merge_cleanup_intent import _recovery_event_intent as _recovery_event_intent, _recovery_cleanup_intent as _recovery_cleanup_intent, _merge_cleanup_expected_subject as _merge_cleanup_expected_subject, _merge_cleanup_expected_argv as _merge_cleanup_expected_argv, _merge_cleanup_intent_valid as _merge_cleanup_intent_valid
from forge_cli.chain_core._merge_cleanup_observation import _merge_cleanup_process_output as _merge_cleanup_process_output, _merge_cleanup_process_complete as _merge_cleanup_process_complete, _merge_cleanup_branch_observation as _merge_cleanup_branch_observation, _merge_cleanup_worktree_inventory as _merge_cleanup_worktree_inventory, _merge_cleanup_fetch_head_bytes as _merge_cleanup_fetch_head_bytes, _merge_cleanup_observation_valid as _merge_cleanup_observation_valid
from forge_cli.chain_core._merge_cleanup_result import _merge_cleanup_process_result_valid as _merge_cleanup_process_result_valid, _merge_cleanup_step_result_valid as _merge_cleanup_step_result_valid, _merge_cleanup_results_valid as _merge_cleanup_results_valid, _merge_cleanup_result_transition_valid as _merge_cleanup_result_transition_valid
from forge_cli.chain_core._merge_epoch import _epoch_fetch_observation_record_valid as _epoch_fetch_observation_record_valid, _epoch_fetch_observation_passed as _epoch_fetch_observation_passed, _epoch_ancestry_record_valid as _epoch_ancestry_record_valid, _epoch_fetch_result_intent_digest as _epoch_fetch_result_intent_digest
from forge_cli.chain_core._merge_events import _merge_event_outbox as _merge_event_outbox, _merge_payload_delta as _merge_payload_delta, reduce_merge_event as reduce_merge_event
from forge_cli.chain_core._merge_plan import _merge_plan_position_fact as _merge_plan_position_fact, _merge_carried_gate_steps as _merge_carried_gate_steps, _merge_gate_step_generation_digests as _merge_gate_step_generation_digests, _merge_current_authority_valid as _merge_current_authority_valid, _merge_remote_only_equality_proof as _merge_remote_only_equality_proof, _merge_carry_payload_valid as _merge_carry_payload_valid, _merge_plan_transition_valid as _merge_plan_transition_valid
from forge_cli.chain_core._merge_rebase import _parse_registered_worktrees as _parse_registered_worktrees, _merge_rebase_action as _merge_rebase_action, _merge_rebase_result_classification as _merge_rebase_result_classification, _merge_containment as _merge_containment, _merge_old_tip_all_false as _merge_old_tip_all_false, _merge_latest_contained_attempt as _merge_latest_contained_attempt, _merge_inactive_post_attempt_recovery_ready as _merge_inactive_post_attempt_recovery_ready, _remote_observation_heads as _remote_observation_heads, _remote_observation_fetch_argv as _remote_observation_fetch_argv, _remote_containment_argv as _remote_containment_argv
from forge_cli.chain_core._merge_recovery_lifecycle import _published_recovery_evidence_valid as _published_recovery_evidence_valid, _recovery_value_carries_inflight as _recovery_value_carries_inflight, _recovery_cleanup_result_matches as _recovery_cleanup_result_matches, _classify_merge_recovery_lifecycle as _classify_merge_recovery_lifecycle
from forge_cli.chain_core._merge_recovery_proof import _merge_recovery_proof_transition_valid as _merge_recovery_proof_transition_valid, _epoch_fetch_observation_predecessor_valid as _epoch_fetch_observation_predecessor_valid, _recovered_absent_rebase_intent_digest as _recovered_absent_rebase_intent_digest
from forge_cli.chain_core._merge_release import _merge_attempted_release_preconditions_valid as _merge_attempted_release_preconditions_valid, _merge_release_preconditions_valid as _merge_release_preconditions_valid
from forge_cli.chain_core._merge_replay import validate_merge_state as validate_merge_state, MergeReplayResult as MergeReplayResult, _replay_merge_event_bytes as _replay_merge_event_bytes
from forge_cli.chain_core._merge_scope import _validate_merge_scope_proof as _validate_merge_scope_proof, _merge_scope_event_binding_valid as _merge_scope_event_binding_valid, _merge_scope_transition_valid as _merge_scope_transition_valid
from forge_cli.chain_core._merge_scope_binding import _merge_scope_environment_contract as _merge_scope_environment_contract, _validate_merge_scope_request as _validate_merge_scope_request, _merge_retained_inflight as _merge_retained_inflight, _validate_merge_scope_fetch_binding as _validate_merge_scope_fetch_binding, _merge_scope_binding_names as _merge_scope_binding_names, _merge_full_patch_argv as _merge_full_patch_argv, _merge_scope_argv as _merge_scope_argv, _merge_scope_binding_validator as _merge_scope_binding_validator
from forge_cli.chain_core._merge_state_shape import _merge_gate_plan_valid as _merge_gate_plan_valid, _merge_epoch_valid as _merge_epoch_valid, _merge_bootstrap_classification_pending as _merge_bootstrap_classification_pending, _merge_revision9_compatibility_view as _merge_revision9_compatibility_view, _merge_state_shape_valid as _merge_state_shape_valid, _merge_ingest_state_shape_valid as _merge_ingest_state_shape_valid, _merge_history_uses_additive_grammar as _merge_history_uses_additive_grammar
from forge_cli.chain_core._merge_transition import _merge_transition_valid as _merge_transition_valid, _merge_ingest_transition_valid as _merge_ingest_transition_valid
from forge_cli.chain_core._receipt_snapshot import _ReceiptRunSnapshot as _ReceiptRunSnapshot, _chain_receipt_snapshot_lock as _chain_receipt_snapshot_lock, _receipt_run_snapshot as _receipt_run_snapshot
from forge_cli.chain_core._remote_observation import _remote_containment_evidence_valid as _remote_containment_evidence_valid, _remote_observation_progress_valid as _remote_observation_progress_valid, _remote_observation_progress_transition_valid as _remote_observation_progress_transition_valid, _remote_observation_progress_matches_observed as _remote_observation_progress_matches_observed, _replayed_remote_observation_completed as _replayed_remote_observation_completed
from forge_cli.chain_core._repository import Repository as Repository, _committed_changelog_output_paths as _committed_changelog_output_paths
from forge_cli.chain_core._state import SCHEMA as SCHEMA, KIND as KIND, FRESH_REVIEWER_EVALS_GATE as FRESH_REVIEWER_EVALS_GATE, FRESH_REVIEWER_EVALS_REQUESTS as FRESH_REVIEWER_EVALS_REQUESTS, FRESH_REVIEWER_EVALS_REQUESTED_EVENT as FRESH_REVIEWER_EVALS_REQUESTED_EVENT, STATES as STATES, STATE_KEYS as STATE_KEYS, EVENT_KEYS as EVENT_KEYS, MERGE_STATE_KEYS as MERGE_STATE_KEYS, _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES as _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES, _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES as _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES, MERGE_EVENT_KEYS as MERGE_EVENT_KEYS, MERGE_EVENT_NAMES as MERGE_EVENT_NAMES, MERGE_CONSEQUENTIAL_EVENTS as MERGE_CONSEQUENTIAL_EVENTS, TIER_RANK as TIER_RANK, INACTIVE_SECONDS as INACTIVE_SECONDS, FENCED_CHILD_ACK_TIMEOUT_SECONDS as FENCED_CHILD_ACK_TIMEOUT_SECONDS, FENCED_CHILD_DRAIN_SECONDS as FENCED_CHILD_DRAIN_SECONDS, FENCED_CHILD_DRAIN_CAP_BYTES as FENCED_CHILD_DRAIN_CAP_BYTES, FENCED_CHILD_STOP_GRACE_SECONDS as FENCED_CHILD_STOP_GRACE_SECONDS, FENCED_CHILD_REAP_SECONDS as FENCED_CHILD_REAP_SECONDS, ZERO_DIGEST as ZERO_DIGEST, COMMON_LOCK_TIMEOUT_SECONDS as COMMON_LOCK_TIMEOUT_SECONDS, COMMON_LOCK_POLL_SECONDS as COMMON_LOCK_POLL_SECONDS, COMMON_LOCK_RECORD_CAP_BYTES as COMMON_LOCK_RECORD_CAP_BYTES, MERGE_SCOPE_BINDING_CAP_BYTES as MERGE_SCOPE_BINDING_CAP_BYTES, COMMON_LOCK_INTENT_NAME as COMMON_LOCK_INTENT_NAME, COMMON_LOCK_DIRECTORY_NAME as COMMON_LOCK_DIRECTORY_NAME, COMMON_LOCK_OWNER_NAME as COMMON_LOCK_OWNER_NAME, COMMON_LOCK_FLOCK_NAME as COMMON_LOCK_FLOCK_NAME, COMMON_LOCK_RECOVERY_NAME as COMMON_LOCK_RECOVERY_NAME, COMMON_LOCK_INFLIGHT_NAME as COMMON_LOCK_INFLIGHT_NAME, CHAIN_ID_RE as CHAIN_ID_RE, SHA256_RE as SHA256_RE, COMMIT_RE as COMMIT_RE, RUN_ID_RE as RUN_ID_RE, _WORKTREE_LOCKS_GUARD as _WORKTREE_LOCKS_GUARD, _WORKTREE_LOCKS as _WORKTREE_LOCKS, _WORKTREE_LOCK_STATE as _WORKTREE_LOCK_STATE, _exclusive_descriptor_lock as _exclusive_descriptor_lock, _MERGE_REMOTE_ONLY_IDENTITY_FIELDS as _MERGE_REMOTE_ONLY_IDENTITY_FIELDS, _MERGE_SCOPE_UNSET as _MERGE_SCOPE_UNSET, _MERGE_SCOPE_OVERLAY as _MERGE_SCOPE_OVERLAY
from forge_cli.envelope import FrozenError, OUTPUT_SCHEMA, REVISION9_OUTPUT_SCHEMA, ReasonCode, Refusal
from forge_cli.policy import sha256_bytes


class _ChainStoragePrimitives:
    """Shared descriptor-safe primitives for both chain storage families."""

    def __init__(
        self,
        common_root: Path,
        *,
        boundary: Callable[[str], None] | None = None,
    ) -> None:
        self.common_root = Path(os.path.realpath(common_root))
        self.root = self.common_root / ".forge" / "chains"
        self._state_versions: dict[int, tuple[dict[str, Any], int, str]] = {}
        self._storage_boundary = boundary

    def _boundary(self, stage: str) -> None:
        if self._storage_boundary is not None:
            self._storage_boundary(stage)

    @staticmethod
    def _owned_directory(descriptor: int, label: str) -> None:
        opened = os.fstat(descriptor)
        if not stat.S_ISDIR(opened.st_mode) or opened.st_uid != os.geteuid():
            raise OSError(f"{label} is not an owner-controlled directory")

    @classmethod
    def _open_child_directory(
        cls, parent: int, name: str, *, create: bool
    ) -> int:
        if create:
            try:
                os.mkdir(name, 0o700, dir_fd=parent)
            except FileExistsError:
                pass
        descriptor = os.open(
            name,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent,
        )
        try:
            cls._owned_directory(descriptor, name)
            os.fchmod(descriptor, 0o700)
            return descriptor
        except BaseException:
            os.close(descriptor)
            raise

    def _open_root_descriptor(self, *, create: bool = True) -> int:
        common = os.open(
            self.common_root,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
        forge = -1
        chains = -1
        try:
            self._owned_directory(common, "git common root")
            forge = self._open_child_directory(common, ".forge", create=create)
            chains = self._open_child_directory(forge, "chains", create=create)
            result = chains
            chains = -1
            return result
        except OSError as exc:
            raise FrozenError(
                "chain storage hierarchy is unsafe",
                observed=str(exc),
            ) from exc
        finally:
            if chains >= 0:
                os.close(chains)
            if forge >= 0:
                os.close(forge)
            os.close(common)

    @contextlib.contextmanager
    def root_descriptor(self) -> Iterable[int]:
        descriptor = self._open_root_descriptor(create=True)
        try:
            yield descriptor
        finally:
            os.close(descriptor)

    def ensure_root(self) -> None:
        with self.root_descriptor():
            pass

    def _open_lock_descriptor(self, name: str) -> int:
        name = self._root_name(name)
        with self.root_descriptor() as root:
            return os.open(
                name,
                os.O_RDWR
                | os.O_CREAT
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=root,
            )

    @contextlib.contextmanager
    def admission_lock(self, worktree_root: Path) -> Iterable[None]:
        """Serialize each same-worktree command and every index mutation.

        Different linked worktrees retain independent locks and can review in
        parallel.  Nesting is deliberately re-entrant because ``verify``
        dispatches individual gate methods and finalize recovery re-enters
        ordinary engine helpers in-process.
        """
        self.ensure_root()
        identity = sha256_bytes(os.path.realpath(worktree_root).encode("utf-8"))[:24]
        name = f".admission-{identity}.lock"
        with _exclusive_descriptor_lock(
            str(self.root / name), lambda: self._open_lock_descriptor(name)
        ):
            yield

    @contextlib.contextmanager
    def event_lock(
        self,
        chain_id: str,
        *,
        deadline: float | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> Iterable[None]:
        """Serialize event-tail reads/appends and their materialized replace."""
        self.ensure_root()
        self._validate_id(chain_id)
        name = f".{chain_id}.events.lock"
        with _exclusive_descriptor_lock(
            str(self.root / name),
            lambda: self._open_lock_descriptor(name),
            deadline=deadline,
            clock=clock,
            sleeper=sleeper,
        ):
            yield

    def state_path(self, chain_id: str) -> Path:
        self._validate_id(chain_id)
        return self.root / f"{chain_id}.json"

    def events_path(self, chain_id: str) -> Path:
        self._validate_id(chain_id)
        return self.root / f"{chain_id}.events.jsonl"

    @staticmethod
    def _tombstone_artifact_fact(root: int, name: str) -> dict[str, Any]:
        try:
            before = os.stat(name, dir_fd=root, follow_symlinks=False)
        except FileNotFoundError:
            return {"status": "absent"}
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or before.st_nlink != 1
        ):
            raise FrozenError("chain artifact is unsafe for operator tombstone")
        descriptor = os.open(
            name,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=root,
        )
        try:
            opened = os.fstat(descriptor)
            if (
                opened.st_dev != before.st_dev
                or opened.st_ino != before.st_ino
                or opened.st_mode != before.st_mode
                or opened.st_uid != before.st_uid
                or opened.st_nlink != before.st_nlink
            ):
                raise FrozenError("chain artifact changed during operator tombstone")
            digest = hashlib.sha256()
            total = 0
            while True:
                chunk = os.read(descriptor, 65536)
                if not chunk:
                    break
                digest.update(chunk)
                total += len(chunk)
            after = os.fstat(descriptor)
            rebound = os.stat(name, dir_fd=root, follow_symlinks=False)
            if (
                after.st_dev != before.st_dev
                or after.st_ino != before.st_ino
                or after.st_mode != before.st_mode
                or after.st_size != before.st_size
                or rebound.st_dev != before.st_dev
                or rebound.st_ino != before.st_ino
                or total != before.st_size
            ):
                raise FrozenError("chain artifact changed during operator tombstone")
            return {
                "status": "captured",
                "sha256": digest.hexdigest(),
                "bytes": total,
            }
        finally:
            os.close(descriptor)

    @staticmethod
    def _valid_tombstone_record(value: object, chain_id: str) -> bool:
        if not isinstance(value, dict) or set(value) != CHAIN_TOMBSTONE_KEYS:
            return False
        operator = value.get("operator")
        artifacts = value.get("artifacts")
        reason = value.get("reason")
        try:
            reason_bytes = reason.encode("utf-8") if isinstance(reason, str) else b""
        except UnicodeError:
            return False
        if (
            value.get("schema") != CHAIN_TOMBSTONE_SCHEMA
            or value.get("chain_id") != chain_id
            or value.get("event") != CHAIN_TOMBSTONE_EVENT
            or not isinstance(reason, str)
            or not reason.strip()
            or not reason_bytes
            or len(reason_bytes) > 4096
            or "\x00" in reason
            or not isinstance(value.get("recorded_at"), str)
            or not isinstance(operator, dict)
            or set(operator) != {"host", "pid", "uid"}
            or not isinstance(operator.get("host"), str)
            or not operator.get("host")
            or type(operator.get("pid")) is not int
            or int(operator["pid"]) <= 0
            or type(operator.get("uid")) is not int
            or not isinstance(artifacts, dict)
            or set(artifacts) != {"state", "events"}
        ):
            return False
        try:
            parse_time(str(value["recorded_at"]))
        except ValueError:
            return False
        statuses: list[str] = []
        for fact in artifacts.values():
            if not isinstance(fact, dict):
                return False
            status_value = fact.get("status")
            statuses.append(str(status_value))
            if status_value == "absent":
                if set(fact) != {"status"}:
                    return False
            elif status_value == "captured":
                if (
                    set(fact) != {"status", "sha256", "bytes"}
                    or not isinstance(fact.get("sha256"), str)
                    or SHA256_RE.fullmatch(str(fact["sha256"])) is None
                    or type(fact.get("bytes")) is not int
                    or int(fact["bytes"]) < 0
                ):
                    return False
            else:
                return False
        return len(set(statuses)) == 1

    @staticmethod
    def _tombstone_publication_alias(
        tombstones: int,
        chain_id: str,
        final_name: str,
        opened: os.stat_result,
    ) -> str | None:
        """Recognize only the temp alias left by one interrupted publication."""

        if opened.st_nlink == 1:
            return None
        if opened.st_nlink != 2:
            raise FrozenError(
                "chain tombstone has an unsafe hardlink topology",
                chain_id=chain_id,
            )
        temporary_pattern = re.compile(
            rf"\.{re.escape(chain_id)}\.[1-9][0-9]*\.[0-9a-f]{{16}}\.tmp"
        )
        aliases: list[str] = []
        try:
            names = os.listdir(tombstones)
        except OSError as exc:
            raise FrozenError(
                "chain tombstone hardlink topology is unreadable",
                chain_id=chain_id,
                observed=str(exc),
            ) from exc
        for candidate in names:
            try:
                candidate_stat = os.stat(
                    candidate, dir_fd=tombstones, follow_symlinks=False
                )
            except FileNotFoundError:
                continue
            except OSError as exc:
                raise FrozenError(
                    "chain tombstone hardlink topology is unreadable",
                    chain_id=chain_id,
                    observed=str(exc),
                ) from exc
            if (
                candidate_stat.st_dev == opened.st_dev
                and candidate_stat.st_ino == opened.st_ino
            ):
                aliases.append(candidate)
        temporary_aliases = [
            name
            for name in aliases
            if name != final_name and temporary_pattern.fullmatch(name) is not None
        ]
        if sorted(aliases) != sorted([final_name, *temporary_aliases]) or len(
            temporary_aliases
        ) != 1:
            raise FrozenError(
                "chain tombstone has an unsafe hardlink topology",
                chain_id=chain_id,
            )
        return temporary_aliases[0]

    @staticmethod
    def _recover_tombstone_publication(
        tombstones: int,
        chain_id: str,
        final_name: str,
        temporary_alias: str | None,
        opened: os.stat_result,
    ) -> None:
        """Durably remove one authenticated publication alias on mutation."""

        try:
            if temporary_alias is not None:
                final = os.stat(
                    final_name, dir_fd=tombstones, follow_symlinks=False
                )
                temporary = os.stat(
                    temporary_alias, dir_fd=tombstones, follow_symlinks=False
                )
                if any(
                    (entry.st_dev, entry.st_ino) != (opened.st_dev, opened.st_ino)
                    or not stat.S_ISREG(entry.st_mode)
                    or entry.st_uid != os.geteuid()
                    or entry.st_nlink != 2
                    for entry in (final, temporary)
                ):
                    raise OSError("publication alias changed inode")
                os.unlink(temporary_alias, dir_fd=tombstones)
                rebound = os.stat(
                    final_name, dir_fd=tombstones, follow_symlinks=False
                )
                if (
                    (rebound.st_dev, rebound.st_ino)
                    != (opened.st_dev, opened.st_ino)
                    or not stat.S_ISREG(rebound.st_mode)
                    or rebound.st_uid != os.geteuid()
                    or rebound.st_nlink != 1
                ):
                    raise OSError("published tombstone changed during alias cleanup")
            os.fsync(tombstones)
        except OSError as exc:
            raise FrozenError(
                "chain tombstone publication recovery failed",
                chain_id=chain_id,
                observed=str(exc),
            ) from exc

    def _read_tombstone_locked(
        self, chain_id: str, *, recover_publication: bool = False
    ) -> dict[str, Any] | None:
        self._validate_id(chain_id)
        with self.root_descriptor() as root:
            try:
                tombstones = self._open_child_directory(
                    root, "tombstones", create=False
                )
            except FileNotFoundError:
                return None
            try:
                name = f"{chain_id}.json"
                try:
                    before = os.stat(
                        name, dir_fd=tombstones, follow_symlinks=False
                    )
                    descriptor = os.open(
                        name,
                        os.O_RDONLY
                        | getattr(os, "O_NOFOLLOW", 0)
                        | getattr(os, "O_CLOEXEC", 0),
                        dir_fd=tombstones,
                    )
                except FileNotFoundError:
                    return None
                try:
                    opened = os.fstat(descriptor)
                    if (
                        not stat.S_ISREG(opened.st_mode)
                        or opened.st_uid != os.geteuid()
                        or opened.st_nlink not in {1, 2}
                        or opened.st_size > 65536
                        or opened.st_dev != before.st_dev
                        or opened.st_ino != before.st_ino
                        or opened.st_mode != before.st_mode
                        or opened.st_uid != before.st_uid
                        or opened.st_nlink != before.st_nlink
                    ):
                        raise FrozenError(
                            "chain tombstone is not an owner-controlled regular file",
                            chain_id=chain_id,
                        )
                    raw = b""
                    while len(raw) <= 65536:
                        chunk = os.read(descriptor, 65537 - len(raw))
                        if not chunk:
                            break
                        raw += chunk
                    after = os.fstat(descriptor)
                    rebound = os.stat(
                        name, dir_fd=tombstones, follow_symlinks=False
                    )
                    if (
                        len(raw) > 65536
                        or len(raw) != opened.st_size
                        or after.st_dev != before.st_dev
                        or after.st_ino != before.st_ino
                        or after.st_mode != before.st_mode
                        or after.st_size != before.st_size
                        or after.st_uid != before.st_uid
                        or after.st_nlink != before.st_nlink
                        or rebound.st_dev != before.st_dev
                        or rebound.st_ino != before.st_ino
                        or rebound.st_mode != before.st_mode
                        or rebound.st_uid != before.st_uid
                        or rebound.st_nlink != before.st_nlink
                    ):
                        raise FrozenError(
                            "chain tombstone exceeds its size bound or changed",
                            chain_id=chain_id,
                        )
                    temporary_alias = self._tombstone_publication_alias(
                        tombstones, chain_id, name, opened
                    )
                finally:
                    os.close(descriptor)
                try:
                    value = json.loads(raw)
                except (UnicodeError, ValueError, RecursionError) as exc:
                    raise FrozenError(
                        "chain tombstone is malformed", chain_id=chain_id
                    ) from exc
                if (
                    raw != canonical_bytes(value) + b"\n"
                    or not self._valid_tombstone_record(value, chain_id)
                ):
                    raise FrozenError(
                        "chain tombstone is malformed", chain_id=chain_id
                    )
                assert isinstance(value, dict)
                facts = {
                    "state": self._tombstone_artifact_fact(root, f"{chain_id}.json"),
                    "events": self._tombstone_artifact_fact(
                        root, f"{chain_id}.events.jsonl"
                    ),
                }
                statuses = {fact["status"] for fact in facts.values()}
                if len(statuses) != 1:
                    raise FrozenError(
                        "tombstoned chain has partial artifacts", chain_id=chain_id
                    )
                recorded_facts = value["artifacts"]
                assert isinstance(recorded_facts, dict)
                if "captured" in statuses and facts != recorded_facts:
                    raise FrozenError(
                        "tombstoned chain artifacts changed", chain_id=chain_id
                    )
                if recover_publication:
                    self._recover_tombstone_publication(
                        tombstones,
                        chain_id,
                        name,
                        temporary_alias,
                        opened,
                    )
                return copy.deepcopy(value)
            finally:
                os.close(tombstones)

    def tombstone(
        self, chain_id: str, *, recover_publication: bool = False
    ) -> dict[str, Any] | None:
        with self.event_lock(chain_id):
            return self._read_tombstone_locked(
                chain_id, recover_publication=recover_publication
            )

    def create_tombstone(
        self,
        chain_id: str,
        reason: str,
        *,
        frozen_proven: bool,
    ) -> dict[str, Any]:
        self._validate_id(chain_id)
        try:
            reason_bytes = reason.encode("utf-8") if isinstance(reason, str) else b""
        except UnicodeError:
            reason_bytes = b""
        if (
            not isinstance(reason, str)
            or not reason.strip()
            or not reason_bytes
            or len(reason_bytes) > 4096
            or "\x00" in reason
        ):
            raise Refusal(
                ReasonCode.STATE_PRECONDITION,
                "forge: chain tombstone refused — a nonempty bounded reason is required",
                observed="invalid tombstone reason",
                remediation="rerun with --reason <operator-reason>",
            )
        with self.event_lock(chain_id):
            existing = self._read_tombstone_locked(
                chain_id, recover_publication=True
            )
            if existing is not None:
                return existing
            with self.root_descriptor() as root:
                facts = {
                    "state": self._tombstone_artifact_fact(root, f"{chain_id}.json"),
                    "events": self._tombstone_artifact_fact(
                        root, f"{chain_id}.events.jsonl"
                    ),
                }
                statuses = {fact["status"] for fact in facts.values()}
                if len(statuses) != 1:
                    raise FrozenError(
                        "operator tombstone refused partial chain artifacts",
                        chain_id=chain_id,
                    )
                if "captured" in statuses and not frozen_proven:
                    raise Refusal(
                        ReasonCode.STATE_PRECONDITION,
                        "forge: chain tombstone refused — readable chain is not frozen",
                        observed=chain_id,
                        remediation=f"forge status --chain-id {chain_id}",
                    )
                record = {
                    "schema": CHAIN_TOMBSTONE_SCHEMA,
                    "chain_id": chain_id,
                    "event": CHAIN_TOMBSTONE_EVENT,
                    "reason": reason,
                    "recorded_at": iso_z(),
                    "operator": {
                        "host": socket.gethostname(),
                        "pid": os.getpid(),
                        "uid": os.geteuid(),
                    },
                    "artifacts": facts,
                }
                encoded = canonical_bytes(record) + b"\n"
                tombstones = self._open_child_directory(
                    root, "tombstones", create=True
                )
                descriptor = -1
                temporary_name = (
                    f".{chain_id}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
                )
                final_name = f"{chain_id}.json"
                try:
                    descriptor = os.open(
                        temporary_name,
                        os.O_WRONLY
                        | os.O_CREAT
                        | os.O_EXCL
                        | getattr(os, "O_NOFOLLOW", 0)
                        | getattr(os, "O_CLOEXEC", 0),
                        0o600,
                        dir_fd=tombstones,
                    )
                    written = 0
                    while written < len(encoded):
                        count = os.write(descriptor, encoded[written:])
                        if count <= 0:
                            raise OSError("short tombstone write")
                        written += count
                    os.fsync(descriptor)
                    os.close(descriptor)
                    descriptor = -1
                    self._boundary("tombstone-before-link")
                    os.link(
                        temporary_name,
                        final_name,
                        src_dir_fd=tombstones,
                        dst_dir_fd=tombstones,
                        follow_symlinks=False,
                    )
                    self._boundary("tombstone-final-linked")
                    os.unlink(temporary_name, dir_fd=tombstones)
                    self._boundary("tombstone-temp-unlinked")
                    os.fsync(tombstones)
                    self._boundary("tombstone-directory-fsynced")
                except FileExistsError:
                    observed = self._read_tombstone_locked(
                        chain_id, recover_publication=True
                    )
                    if observed is None:
                        raise FrozenError(
                            "chain tombstone publication raced", chain_id=chain_id
                        )
                    return observed
                except OSError as exc:
                    raise FrozenError(
                        "chain tombstone publication failed",
                        chain_id=chain_id,
                        observed=str(exc),
                        schema=REVISION9_OUTPUT_SCHEMA,
                    ) from exc
                finally:
                    if descriptor >= 0:
                        os.close(descriptor)
                    try:
                        os.unlink(temporary_name, dir_fd=tombstones)
                    except FileNotFoundError:
                        pass
                    os.close(tombstones)
                return record

    def artifact_dir(self, chain_id: str) -> Path:
        self._validate_id(chain_id)
        path = self.root / chain_id
        with self.root_descriptor() as root:
            descriptor = self._open_child_directory(root, chain_id, create=True)
            os.close(descriptor)
        return path

    @contextlib.contextmanager
    def artifact_parent_descriptor(
        self, chain_id: str, relative: str, *, create: bool
    ) -> Iterable[tuple[int, str]]:
        self._validate_id(chain_id)
        candidate = Path(relative)
        parts = candidate.parts
        if (
            candidate.is_absolute()
            or not parts
            or any(part in {"", ".", ".."} or "/" in part for part in parts)
        ):
            raise Refusal(
                ReasonCode.CITATION_OUT_OF_ROOT,
                f"artifact path escapes chain directory: {relative}",
                observed=relative,
                remediation="use a repository-contained chain artifact path",
                chain={"chain_id": chain_id, "state": "unknown"},
            )
        descriptors: list[int] = []
        try:
            root = self._open_root_descriptor(create=True)
            descriptors.append(root)
            current = self._open_child_directory(root, chain_id, create=create)
            descriptors.append(current)
            for component in parts[:-1]:
                current = self._open_child_directory(
                    current, component, create=create
                )
                descriptors.append(current)
            yield current, parts[-1]
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)

    @staticmethod
    def _root_name(name: str) -> str:
        if not name or "/" in name or name in {".", ".."}:
            raise FrozenError("invalid chain storage filename", observed=name)
        return name

    def _read_root_bytes(self, name: str) -> bytes:
        name = self._root_name(name)
        with self.root_descriptor() as root:
            descriptor = os.open(
                name,
                os.O_RDONLY
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NONBLOCK", 0),
                dir_fd=root,
            )
            try:
                opened = os.fstat(descriptor)
                if not stat.S_ISREG(opened.st_mode) or opened.st_uid != os.geteuid():
                    raise OSError("chain storage entry is not an owner-controlled regular file")
                chunks: list[bytes] = []
                while True:
                    chunk = os.read(descriptor, 65536)
                    if not chunk:
                        return b"".join(chunks)
                    chunks.append(chunk)
            finally:
                os.close(descriptor)

    def _canonical_raw_commit_state(
        self, chain_id: str
    ) -> dict[str, Any] | None:
        """Read stable canonical raw identity without replaying the event log."""

        self._validate_id(chain_id)
        name = self.state_path(chain_id).name
        try:
            with self.root_descriptor() as root:
                before = os.stat(name, dir_fd=root, follow_symlinks=False)
                descriptor = os.open(
                    name,
                    os.O_RDONLY
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_CLOEXEC", 0)
                    | getattr(os, "O_NONBLOCK", 0),
                    dir_fd=root,
                )
                try:
                    opened = os.fstat(descriptor)
                    if (
                        not stat.S_ISREG(opened.st_mode)
                        or opened.st_uid != os.geteuid()
                        or opened.st_nlink != 1
                        or opened.st_dev != before.st_dev
                        or opened.st_ino != before.st_ino
                        or opened.st_mode != before.st_mode
                        or opened.st_uid != before.st_uid
                        or opened.st_nlink != before.st_nlink
                        or opened.st_size != before.st_size
                    ):
                        return None
                    chunks: list[bytes] = []
                    remaining = opened.st_size
                    while remaining:
                        chunk = os.read(descriptor, min(65536, remaining))
                        if not chunk:
                            return None
                        chunks.append(chunk)
                        remaining -= len(chunk)
                    if os.read(descriptor, 1):
                        return None
                    after = os.fstat(descriptor)
                    rebound = os.stat(
                        name, dir_fd=root, follow_symlinks=False
                    )
                    for current in (after, rebound):
                        if (
                            current.st_dev != before.st_dev
                            or current.st_ino != before.st_ino
                            or current.st_mode != before.st_mode
                            or current.st_uid != before.st_uid
                            or current.st_nlink != before.st_nlink
                            or current.st_size != before.st_size
                            or current.st_mtime_ns != before.st_mtime_ns
                            or current.st_ctime_ns != before.st_ctime_ns
                        ):
                            return None
                finally:
                    os.close(descriptor)
        except (FileNotFoundError, OSError):
            return None
        raw = b"".join(chunks)
        try:
            value = json.loads(raw)
        except (UnicodeError, ValueError, RecursionError):
            return None
        if not (
            isinstance(value, dict)
            and value.get("chain_id") == chain_id
            and value.get("kind") == "commit"
            and raw == canonical_bytes(value) + b"\n"
        ):
            return None
        try:
            return copy.deepcopy(validate_state(value, chain_id))
        except FrozenError:
            return None

    def raw_state_proves_commit_family(self, chain_id: str) -> bool:
        """Prove commit family from canonical raw identity when events cannot."""

        return self._canonical_raw_commit_state(chain_id) is not None

    def _root_entry_exists(self, name: str) -> bool:
        name = self._root_name(name)
        with self.root_descriptor() as root:
            try:
                os.stat(name, dir_fd=root, follow_symlinks=False)
            except FileNotFoundError:
                return False
            return True

    @staticmethod
    def _validate_id(chain_id: str) -> None:
        if not CHAIN_ID_RE.fullmatch(chain_id):
            raise FrozenError("invalid chain identifier", chain_id=chain_id)

    def list_ids(self, *, family: str | None = None) -> list[str]:
        result: set[str] = set()
        with self.root_descriptor() as root:
            for name in os.listdir(root):
                if name.startswith("c-") and name.endswith(".json"):
                    chain_id = name[:-5]
                    if CHAIN_ID_RE.fullmatch(chain_id):
                        result.add(chain_id)
                if name.startswith("c-") and name.endswith(".events.jsonl"):
                    chain_id = name[: -len(".events.jsonl")]
                    if CHAIN_ID_RE.fullmatch(chain_id):
                        result.add(chain_id)
        ordered = sorted(result)
        if family is None:
            return ordered
        _require_merge_store_control("family-isolated-enumeration")
        if family not in {"commit", "merge"}:
            raise ValueError(f"unknown chain family: {family}")
        selected: list[str] = []
        for chain_id in ordered:
            try:
                if self.tombstone(chain_id) is not None:
                    continue
                if self.chain_family(chain_id) == family:
                    selected.append(chain_id)
            except FrozenError:
                # An unreadable chain remains addressable by its explicit ID,
                # but never wedges selection for another authenticated chain.
                print(
                    "forge: warning — skipped unreadable chain "
                    f"{chain_id} while enumerating {family} chains",
                    file=sys.stderr,
                )
                continue
        return selected

    def chain_family(self, chain_id: str) -> str:
        """Authenticate family from event one without consulting state JSON."""

        _require_merge_store_control("event-first-family")
        self._validate_id(chain_id)
        path = self.events_path(chain_id)
        try:
            with self.event_lock(chain_id):
                data = self._read_root_bytes(path.name)
        except FileNotFoundError as exc:
            raise FrozenError(
                "chain event log is missing",
                chain_id=chain_id,
                observed=str(path),
            ) from exc
        except OSError as exc:
            raise FrozenError(
                "chain event log is unreadable",
                chain_id=chain_id,
                observed=str(exc),
            ) from exc
        if not data or not data.endswith(b"\n"):
            raise FrozenError(
                "chain event log is empty or has a partial final record",
                chain_id=chain_id,
            )
        first = data.splitlines(keepends=True)[0]
        try:
            event = json.loads(first)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FrozenError(
                "chain event 1 is malformed",
                chain_id=chain_id,
            ) from exc
        if first != canonical_bytes(event) + b"\n":
            raise FrozenError(
                "chain event 1 is not canonical",
                chain_id=chain_id,
                schema=(
                    REVISION9_OUTPUT_SCHEMA
                    if isinstance(event, dict)
                    and event.get("schema") == "forge-merge-event/1"
                    else OUTPUT_SCHEMA
                ),
            )
        if isinstance(event, dict) and set(event) == EVENT_KEYS:
            payload = event.get("payload")
            unsigned = {
                "sequence": event.get("sequence"),
                "prev_digest": event.get("prev_digest"),
                "payload": payload,
            }
            if (
                event.get("sequence") != 1
                or event.get("prev_digest") != ZERO_DIGEST
                or event.get("digest")
                != sha256_bytes(canonical_bytes(unsigned))
                or not isinstance(payload, dict)
                or set(payload) != {"at", "details", "event", "state"}
            ):
                raise FrozenError(
                    "chain event 1 does not authenticate a chain family",
                    chain_id=chain_id,
                )
            try:
                validate_state(payload.get("state"), chain_id)
            except FrozenError as exc:
                raise FrozenError(
                    "chain event 1 does not authenticate a commit family",
                    chain_id=chain_id,
                    observed=str(exc),
                ) from exc
            return "commit"
        if (
            isinstance(event, dict)
            and set(event) == MERGE_EVENT_KEYS
            and event.get("schema") == "forge-merge-event/1"
        ):
            try:
                replay = _replay_merge_event_bytes(
                    chain_id,
                    first,
                )
            except FrozenError:
                raise
            except (KeyError, TypeError, ValueError, RuntimeError) as exc:
                raise FrozenError(
                    "chain event 1 does not authenticate a merge family",
                    chain_id=chain_id,
                    observed=str(exc),
                    schema=REVISION9_OUTPUT_SCHEMA,
                ) from exc
            if len(replay.events) != 1:
                raise FrozenError(
                    "chain event 1 does not authenticate a merge family",
                    chain_id=chain_id,
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            return "merge"
        raise FrozenError(
            "chain event 1 does not authenticate a chain family",
            chain_id=chain_id,
            schema=(
                REVISION9_OUTPUT_SCHEMA
                if isinstance(event, dict)
                and event.get("schema") == "forge-merge-event/1"
                else OUTPUT_SCHEMA
            ),
        )

    def _remember_version(
        self, state: dict[str, Any], sequence: int, digest: str
    ) -> None:
        self._state_versions[id(state)] = (state, sequence, digest)

    def _require_tail_version(
        self,
        state: dict[str, Any],
        sequence: int,
        digest: str,
        *,
        family: str,
        refusal_chain: Mapping[str, Any] | None = None,
    ) -> None:
        version_entry = self._state_versions.get(id(state))
        snapshot_version = (
            (version_entry[1], version_entry[2])
            if version_entry is not None and version_entry[0] is state
            else None
        )
        current_version = (sequence, digest)
        if snapshot_version != current_version:
            raise Refusal(
                ReasonCode.STATE_PRECONDITION,
                "chain state changed concurrently; stale result was not persisted",
                expected=(
                    "a versioned snapshot"
                    if snapshot_version is None
                    else f"event tail {snapshot_version[0]}:{snapshot_version[1]}"
                ),
                observed=f"current event tail {sequence}:{digest}",
                remediation=_forge_command(state, "status"),
                chain=(refusal_chain if refusal_chain is not None else state),
                schema=(
                    REVISION9_OUTPUT_SCHEMA if family == "merge" else None
                ),
            )

    def _append_event_bytes(
        self,
        chain_id: str,
        encoded: bytes,
        *,
        initial: bool,
    ) -> None:
        """Append one already-canonical event and fsync its regular file."""

        flags = (
            os.O_WRONLY
            | os.O_APPEND
            | os.O_CREAT
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NONBLOCK", 0)
        )
        if initial:
            flags |= os.O_EXCL
        descriptor: int | None = None
        with self.root_descriptor() as root:
            try:
                descriptor = os.open(
                    self.events_path(chain_id).name,
                    flags,
                    0o600,
                    dir_fd=root,
                )
                opened = os.fstat(descriptor)
                if not stat.S_ISREG(opened.st_mode) or opened.st_uid != os.geteuid():
                    raise OSError(
                        "event log is not an owner-controlled regular file"
                    )
                os.fchmod(descriptor, 0o600)
                written = 0
                while written < len(encoded):
                    count = os.write(descriptor, encoded[written:])
                    if count <= 0:
                        raise OSError("short event-log write")
                    written += count
                os.fsync(descriptor)
            finally:
                if descriptor is not None:
                    os.close(descriptor)
            os.fsync(root)

    def _atomic_state(self, state: Mapping[str, Any]) -> None:
        """Atomically replace one canonical state projection and fsync it."""

        chain_id = str(state["chain_id"])
        self.ensure_root()
        temporary_name = f".{chain_id}.{secrets.token_hex(8)}.tmp"
        descriptor = -1
        with self.root_descriptor() as root:
            try:
                descriptor = os.open(
                    temporary_name,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_CLOEXEC", 0),
                    0o600,
                    dir_fd=root,
                )
                opened = os.fstat(descriptor)
                if not stat.S_ISREG(opened.st_mode) or opened.st_uid != os.geteuid():
                    raise OSError(
                        "temporary state is not an owner-controlled regular file"
                    )
                os.fchmod(descriptor, 0o600)
                encoded = canonical_bytes(state) + b"\n"
                written = 0
                while written < len(encoded):
                    count = os.write(descriptor, encoded[written:])
                    if count <= 0:
                        raise OSError("short state write")
                    written += count
                os.fsync(descriptor)
                os.close(descriptor)
                descriptor = -1
                os.replace(
                    temporary_name,
                    self.state_path(chain_id).name,
                    src_dir_fd=root,
                    dst_dir_fd=root,
                )
                os.fsync(root)
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
                try:
                    os.unlink(temporary_name, dir_fd=root)
                except FileNotFoundError:
                    pass

    @staticmethod
    def _fsync_dir(path: Path) -> None:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        descriptor = os.open(path, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
