"""Forge CLI chain core: the fenced process runner, the FR-235 common-lock arbiter and
chain leases, chain and merge-chain storage, merge state/transition validation, and the
ingest verifiers (cli split phase 2b, bead forge-plugin-95e.3).

Moved verbatim from scripts/forge/cli.py. Runtime controls are read through
``forge_cli.runtime``; the chain journal-record builder stays in the shim and is reached
through the late-bound ``runtime._build_chain_journal_records`` seam.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping, Sequence
from pathlib import Path
import contextlib
import copy
import dataclasses
import datetime as dt
import errno
import fcntl
import hashlib
import json
import os
import re
import secrets
import socket
import stat
import subprocess
import sys
import threading
import time

from forge_cli import candidate as candidate_module, fresh_evals as fresh_eval_module, runtime
from forge_cli.envelope import (
    FrozenError,
    OUTPUT_SCHEMA,
    Outcome,
    REVISION9_OUTPUT_SCHEMA,
    ReasonCode,
    Refusal,
    V2ReasonCode,
)
from forge_cli.policy import (
    Policy,
    PolicyError,
    parse_policy,
    sha256_bytes,
)
from ._state import (
    SCHEMA as SCHEMA,
    KIND as KIND,
    FRESH_REVIEWER_EVALS_GATE as FRESH_REVIEWER_EVALS_GATE,
    FRESH_REVIEWER_EVALS_REQUESTS as FRESH_REVIEWER_EVALS_REQUESTS,
    FRESH_REVIEWER_EVALS_REQUESTED_EVENT as FRESH_REVIEWER_EVALS_REQUESTED_EVENT,
    STATES as STATES,
    STATE_KEYS as STATE_KEYS,
    EVENT_KEYS as EVENT_KEYS,
    MERGE_STATE_KEYS as MERGE_STATE_KEYS,
    _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES as _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES,
    _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES as _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES,
    MERGE_EVENT_KEYS as MERGE_EVENT_KEYS,
    MERGE_EVENT_NAMES as MERGE_EVENT_NAMES,
    MERGE_CONSEQUENTIAL_EVENTS as MERGE_CONSEQUENTIAL_EVENTS,
    TIER_RANK as TIER_RANK,
    INACTIVE_SECONDS as INACTIVE_SECONDS,
    FENCED_CHILD_ACK_TIMEOUT_SECONDS as FENCED_CHILD_ACK_TIMEOUT_SECONDS,
    FENCED_CHILD_DRAIN_SECONDS as FENCED_CHILD_DRAIN_SECONDS,
    FENCED_CHILD_DRAIN_CAP_BYTES as FENCED_CHILD_DRAIN_CAP_BYTES,
    FENCED_CHILD_STOP_GRACE_SECONDS as FENCED_CHILD_STOP_GRACE_SECONDS,
    FENCED_CHILD_REAP_SECONDS as FENCED_CHILD_REAP_SECONDS,
    ZERO_DIGEST as ZERO_DIGEST,
    COMMON_LOCK_TIMEOUT_SECONDS as COMMON_LOCK_TIMEOUT_SECONDS,
    COMMON_LOCK_POLL_SECONDS as COMMON_LOCK_POLL_SECONDS,
    COMMON_LOCK_RECORD_CAP_BYTES as COMMON_LOCK_RECORD_CAP_BYTES,
    MERGE_SCOPE_BINDING_CAP_BYTES as MERGE_SCOPE_BINDING_CAP_BYTES,
    COMMON_LOCK_INTENT_NAME as COMMON_LOCK_INTENT_NAME,
    COMMON_LOCK_DIRECTORY_NAME as COMMON_LOCK_DIRECTORY_NAME,
    COMMON_LOCK_OWNER_NAME as COMMON_LOCK_OWNER_NAME,
    COMMON_LOCK_FLOCK_NAME as COMMON_LOCK_FLOCK_NAME,
    COMMON_LOCK_RECOVERY_NAME as COMMON_LOCK_RECOVERY_NAME,
    COMMON_LOCK_INFLIGHT_NAME as COMMON_LOCK_INFLIGHT_NAME,
    CHAIN_ID_RE as CHAIN_ID_RE,
    SHA256_RE as SHA256_RE,
    COMMIT_RE as COMMIT_RE,
    RUN_ID_RE as RUN_ID_RE,
    _WORKTREE_LOCKS_GUARD as _WORKTREE_LOCKS_GUARD,
    _WORKTREE_LOCKS as _WORKTREE_LOCKS,
    _WORKTREE_LOCK_STATE as _WORKTREE_LOCK_STATE,
    _exclusive_descriptor_lock as _exclusive_descriptor_lock,
    _MERGE_REMOTE_ONLY_IDENTITY_FIELDS as _MERGE_REMOTE_ONLY_IDENTITY_FIELDS,
    _MERGE_SCOPE_UNSET as _MERGE_SCOPE_UNSET,
    _MERGE_SCOPE_OVERLAY as _MERGE_SCOPE_OVERLAY,
)
from ._controls import (
    COMMON_LOCK_OWNER_KINDS as COMMON_LOCK_OWNER_KINDS,
    COMMON_LOCK_OPERATIONS as COMMON_LOCK_OPERATIONS,
    COMMON_LOCK_FENCE_OPERATIONS as COMMON_LOCK_FENCE_OPERATIONS,
    COMMON_LOCK_RECOVERY_KINDS as COMMON_LOCK_RECOVERY_KINDS,
    _COMMON_LOCK_OWNER_KEYS as _COMMON_LOCK_OWNER_KEYS,
    _COMMON_LOCK_FENCE_KEYS as _COMMON_LOCK_FENCE_KEYS,
    _COMMON_LOCK_RECOVERY_KEYS as _COMMON_LOCK_RECOVERY_KEYS,
    _CHAIN_LEASE_KEYS as _CHAIN_LEASE_KEYS,
    _REQUIRED_COMMON_LOCK_CONTROLS as _REQUIRED_COMMON_LOCK_CONTROLS,
    COMMON_LOCK_CONTROLS as COMMON_LOCK_CONTROLS,
    CHAIN_TOMBSTONE_SCHEMA as CHAIN_TOMBSTONE_SCHEMA,
    CHAIN_TOMBSTONE_EVENT as CHAIN_TOMBSTONE_EVENT,
    CHAIN_TOMBSTONE_KEYS as CHAIN_TOMBSTONE_KEYS,
    _REQUIRED_MERGE_STORE_CONTROLS as _REQUIRED_MERGE_STORE_CONTROLS,
    MERGE_STORE_CONTROLS as MERGE_STORE_CONTROLS,
    _REQUIRED_MERGE_ADAPTER_CONTROLS as _REQUIRED_MERGE_ADAPTER_CONTROLS,
    MERGE_ADAPTER_CONTROLS as MERGE_ADAPTER_CONTROLS,
    _REQUIRED_MERGE_INTEGRATION_CONTROLS as _REQUIRED_MERGE_INTEGRATION_CONTROLS,
    MERGE_INTEGRATION_CONTROLS as MERGE_INTEGRATION_CONTROLS,
    INGEST_PROOF_ORDER as INGEST_PROOF_ORDER,
    _REQUIRED_INGEST_PROOF_CONTROLS as _REQUIRED_INGEST_PROOF_CONTROLS,
    INGEST_PROOF_CONTROLS as INGEST_PROOF_CONTROLS,
    _MERGE_CLEANUP_INTENT_SCHEMA as _MERGE_CLEANUP_INTENT_SCHEMA,
    _MERGE_CLEANUP_RESULT_SCHEMA as _MERGE_CLEANUP_RESULT_SCHEMA,
    _MERGE_CLEANUP_CLOSE_SCHEMA as _MERGE_CLEANUP_CLOSE_SCHEMA,
    _MERGE_CLEANUP_RECOVERY_SCHEMA as _MERGE_CLEANUP_RECOVERY_SCHEMA,
    _MERGE_CLEANUP_FENCE_OPERATIONS as _MERGE_CLEANUP_FENCE_OPERATIONS,
    _EPOCH_FETCH_OBSERVATION_SCHEMA as _EPOCH_FETCH_OBSERVATION_SCHEMA,
    _MERGE_CANDIDATE_OBSERVATION_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_SCHEMA,
    _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA,
    _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA as _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA,
)
from ._core import (
    canonical_bytes as canonical_bytes,
    _chain_storage_root as _chain_storage_root,
    _validated_commitment_path as _validated_commitment_path,
    _parsed_run_captured_path as _parsed_run_captured_path,
    _require_ingest_proof as _require_ingest_proof,
    iso_z as iso_z,
    parse_time as parse_time,
    _require_merge_store_control as _require_merge_store_control,
    _require_merge_adapter_control as _require_merge_adapter_control,
    _require_merge_integration_control as _require_merge_integration_control,
    _require_common_lock_control as _require_common_lock_control,
    CommonLockBoundaryCrash as CommonLockBoundaryCrash,
    PublishedLockRecord as PublishedLockRecord,
    CommonLockInspection as CommonLockInspection,
    CommonLockUnavailable as CommonLockUnavailable,
    CommonLockReleaseFailure as CommonLockReleaseFailure,
    ChainLeaseUnavailable as ChainLeaseUnavailable,
    FencedChildSurvived as FencedChildSurvived,
    _valid_utc_second as _valid_utc_second,
    _valid_positive_int as _valid_positive_int,
    _valid_nonnegative_int as _valid_nonnegative_int,
    _valid_host as _valid_host,
    _valid_nonce as _valid_nonce,
    _valid_nullable_chain as _valid_nullable_chain,
    _write_all as _write_all,
    _PublicationCleanupFailure as _PublicationCleanupFailure,
    _process_probe as _process_probe,
    _group_probe as _group_probe,
    _sleep_with_deadline as _sleep_with_deadline,
    _require_deadline_open as _require_deadline_open,
    FencedProcessResult as FencedProcessResult,
    merge_gate_intent_digest as merge_gate_intent_digest,
    _forge_command as _forge_command,
    MergeRunTaskSnapshot as MergeRunTaskSnapshot,
    _merge_refusal as _merge_refusal,
    _valid_sorted_unique_strings as _valid_sorted_unique_strings,
)
from ._candidate_v2 import (
    candidate_is_v2 as candidate_is_v2,
    _candidate_binding_for_state_with_candidate_v2 as _candidate_binding_for_state_with_candidate_v2,
    _binding_shape_valid_with_candidate_v2 as _binding_shape_valid_with_candidate_v2,
    _event_batch_records_with_candidate_v2 as _event_batch_records_with_candidate_v2,
    _binding_matches_source_fact_with_candidate_v2 as _binding_matches_source_fact_with_candidate_v2,
    _binding_is_current_with_candidate_v2 as _binding_is_current_with_candidate_v2,
    _commit_transition_valid_with_candidate_v2 as _commit_transition_valid_with_candidate_v2,
)
from ._receipt_snapshot import (
    _ReceiptRunSnapshot as _ReceiptRunSnapshot,
    _chain_receipt_snapshot_lock as _chain_receipt_snapshot_lock,
    _receipt_run_snapshot as _receipt_run_snapshot,
    _ChainReceiptSnapshotVerifier as _ChainReceiptSnapshotVerifier,
)
from ._merge_plan import (
    _merge_plan_position_fact as _merge_plan_position_fact,
    _merge_carried_gate_steps as _merge_carried_gate_steps,
    _merge_gate_step_generation_digests as _merge_gate_step_generation_digests,
    _merge_current_authority_valid as _merge_current_authority_valid,
    _merge_remote_only_equality_proof as _merge_remote_only_equality_proof,
    _merge_carry_payload_valid as _merge_carry_payload_valid,
    _merge_plan_transition_valid as _merge_plan_transition_valid,
)
from ._bootstrap_observation import (
    _bootstrap_fetch_observation_record_valid as _bootstrap_fetch_observation_record_valid,
    _bootstrap_fetch_observation_transition_valid as _bootstrap_fetch_observation_transition_valid,
)
from ._fenced_child import (
    _BlockedFenceChild as _BlockedFenceChild,
    _pipe_cloexec as _pipe_cloexec,
    _read_child_ack as _read_child_ack,
    _waitpid_nohang as _waitpid_nohang,
    _wait_for_child_exit as _wait_for_child_exit,
    _spawn_blocked_fence_child as _spawn_blocked_fence_child,
    _terminate_fenced_group as _terminate_fenced_group,
    _stop_unstarted_child as _stop_unstarted_child,
    _collect_fenced_child as _collect_fenced_child,
)
from ._ingest_capture import (
    _read_ingest_input as _read_ingest_input,
    _capture_ingest_blob as _capture_ingest_blob,
    _capture_run_evidence as _capture_run_evidence,
    _capture_ingest_record_evidence as _capture_ingest_record_evidence,
)
from ._chain_state import (
    validate_state as validate_state,
)
from ._ingest_currency import (
    _ingest_captured_paths as _ingest_captured_paths,
    _ingest_step_is_current as _ingest_step_is_current,
    _ingest_secret_scan_is_current as _ingest_secret_scan_is_current,
    _prove_ingest_live_chain as _prove_ingest_live_chain,
)
from ._lock_record_validators import (
    _validate_owner_record as _validate_owner_record,
    _validate_fence_record as _validate_fence_record,
    _validate_recovery_record as _validate_recovery_record,
    _validate_chain_lease_record as _validate_chain_lease_record,
)
from ._merge_cleanup_intent import (
    _recovery_event_intent as _recovery_event_intent,
    _recovery_cleanup_intent as _recovery_cleanup_intent,
    _merge_cleanup_expected_subject as _merge_cleanup_expected_subject,
    _merge_cleanup_expected_argv as _merge_cleanup_expected_argv,
    _merge_cleanup_intent_valid as _merge_cleanup_intent_valid,
)
from ._merge_events import (
    _merge_event_outbox as _merge_event_outbox,
    _merge_payload_delta as _merge_payload_delta,
    reduce_merge_event as reduce_merge_event,
)
from ._merge_rebase import (
    _parse_registered_worktrees as _parse_registered_worktrees,
    _merge_rebase_action as _merge_rebase_action,
    _merge_rebase_result_classification as _merge_rebase_result_classification,
    _merge_containment as _merge_containment,
    _merge_old_tip_all_false as _merge_old_tip_all_false,
    _merge_latest_contained_attempt as _merge_latest_contained_attempt,
    _merge_inactive_post_attempt_recovery_ready as _merge_inactive_post_attempt_recovery_ready,
    _remote_observation_heads as _remote_observation_heads,
    _remote_observation_fetch_argv as _remote_observation_fetch_argv,
    _remote_containment_argv as _remote_containment_argv,
)
from ._merge_state_shape import (
    _merge_gate_plan_valid as _merge_gate_plan_valid,
    _merge_epoch_valid as _merge_epoch_valid,
    _merge_bootstrap_classification_pending as _merge_bootstrap_classification_pending,
    _merge_revision9_compatibility_view as _merge_revision9_compatibility_view,
    _merge_state_shape_valid as _merge_state_shape_valid,
    _merge_ingest_state_shape_valid as _merge_ingest_state_shape_valid,
    _merge_history_uses_additive_grammar as _merge_history_uses_additive_grammar,
)
from ._repository import (
    Repository as Repository,
    _committed_changelog_output_paths as _committed_changelog_output_paths,
)
from ._lock_record_io import (
    _read_owned_record_at as _read_owned_record_at,
    _same_published_record as _same_published_record,
    _open_lock_directory as _open_lock_directory,
    _opaque_path_evidence_at as _opaque_path_evidence_at,
    _inspect_common_lock_fd as _inspect_common_lock_fd,
    _create_private_record_at as _create_private_record_at,
    _publish_no_replace_link as _publish_no_replace_link,
    _revalidate_record_at as _revalidate_record_at,
    _unlink_revalidated_record_at as _unlink_revalidated_record_at,
    _record_at_if_present as _record_at_if_present,
)
from ._merge_cleanup_history import (
    _merge_cleanup_evidence_history as _merge_cleanup_evidence_history,
    _merge_cleanup_history_summary as _merge_cleanup_history_summary,
    _merge_cleanup_unmatched_intent as _merge_cleanup_unmatched_intent,
    _merge_cleanup_retry_proof_valid as _merge_cleanup_retry_proof_valid,
    _merge_cleanup_intent_transition_valid as _merge_cleanup_intent_transition_valid,
    _merge_history_has_git_mutation_intent as _merge_history_has_git_mutation_intent,
)
from ._merge_cleanup_observation import (
    _merge_cleanup_process_output as _merge_cleanup_process_output,
    _merge_cleanup_process_complete as _merge_cleanup_process_complete,
    _merge_cleanup_branch_observation as _merge_cleanup_branch_observation,
    _merge_cleanup_worktree_inventory as _merge_cleanup_worktree_inventory,
    _merge_cleanup_fetch_head_bytes as _merge_cleanup_fetch_head_bytes,
    _merge_cleanup_observation_valid as _merge_cleanup_observation_valid,
)
from ._merge_scope_binding import (
    _merge_scope_environment_contract as _merge_scope_environment_contract,
    _validate_merge_scope_request as _validate_merge_scope_request,
    _merge_retained_inflight as _merge_retained_inflight,
    _validate_merge_scope_fetch_binding as _validate_merge_scope_fetch_binding,
    _merge_scope_binding_names as _merge_scope_binding_names,
    _merge_full_patch_argv as _merge_full_patch_argv,
    _merge_scope_argv as _merge_scope_argv,
    _merge_scope_binding_validator as _merge_scope_binding_validator,
)
from ._remote_observation import (
    _remote_containment_evidence_valid as _remote_containment_evidence_valid,
    _remote_observation_progress_valid as _remote_observation_progress_valid,
    _remote_observation_progress_transition_valid as _remote_observation_progress_transition_valid,
    _remote_observation_progress_matches_observed as _remote_observation_progress_matches_observed,
    _replayed_remote_observation_completed as _replayed_remote_observation_completed,
)
from ._merge_candidate_observation_steps import (
    _merge_candidate_observation_step_specs as _merge_candidate_observation_step_specs,
    _merge_candidate_observation_step_names as _merge_candidate_observation_step_names,
    _merge_candidate_observation_binding as _merge_candidate_observation_binding,
)
from ._merge_cleanup_result import (
    _merge_cleanup_process_result_valid as _merge_cleanup_process_result_valid,
    _merge_cleanup_step_result_valid as _merge_cleanup_step_result_valid,
    _merge_cleanup_results_valid as _merge_cleanup_results_valid,
    _merge_cleanup_result_transition_valid as _merge_cleanup_result_transition_valid,
)
from ._merge_release import (
    _merge_attempted_release_preconditions_valid as _merge_attempted_release_preconditions_valid,
    _merge_release_preconditions_valid as _merge_release_preconditions_valid,
)
from ._merge_scope import (
    _validate_merge_scope_proof as _validate_merge_scope_proof,
    _merge_scope_event_binding_valid as _merge_scope_event_binding_valid,
    _merge_scope_transition_valid as _merge_scope_transition_valid,
)
from ._merge_candidate_observation import (
    _merge_candidate_observation_record_valid as _merge_candidate_observation_record_valid,
    _merge_candidate_observation_transition_valid as _merge_candidate_observation_transition_valid,
    _merge_candidate_observation_evidence as _merge_candidate_observation_evidence,
    _merge_candidate_observation_evidence_valid as _merge_candidate_observation_evidence_valid,
)
from ._merge_epoch import (
    _epoch_fetch_observation_record_valid as _epoch_fetch_observation_record_valid,
    _epoch_fetch_observation_passed as _epoch_fetch_observation_passed,
    _epoch_ancestry_record_valid as _epoch_ancestry_record_valid,
    _epoch_fetch_result_intent_digest as _epoch_fetch_result_intent_digest,
)
from ._merge_recovery_lifecycle import (
    _published_recovery_evidence_valid as _published_recovery_evidence_valid,
    _recovery_value_carries_inflight as _recovery_value_carries_inflight,
    _recovery_cleanup_result_matches as _recovery_cleanup_result_matches,
    _classify_merge_recovery_lifecycle as _classify_merge_recovery_lifecycle,
)
from ._merge_recovery_proof import (
    _merge_recovery_proof_transition_valid as _merge_recovery_proof_transition_valid,
    _epoch_fetch_observation_predecessor_valid as _epoch_fetch_observation_predecessor_valid,
    _recovered_absent_rebase_intent_digest as _recovered_absent_rebase_intent_digest,
)
from ._merge_transition import (
    _merge_transition_valid as _merge_transition_valid,
    _merge_ingest_transition_valid as _merge_ingest_transition_valid,
)
from forge_cli.chain_core._ingest_merge import (
    _merge_ingest_binding,
    _merge_gate_event_fact,
    _merge_current_gate_facts,
    _merge_ingest_record_templates,
    _ingest_allocation_records,
    _verify_and_build_merge_ingest_records,
)
from forge_cli.chain_core._merge_replay import (
    validate_merge_state,
    MergeReplayResult,
    _replay_merge_event_bytes,
)


@dataclasses.dataclass(frozen=True)
class _ChainActivationSnapshot:
    """One bounded, event-authoritative chain projection and its carrier."""

    family: str
    state: dict[str, object]
    raw_events: bytes
    raw_state: bytes
    tail_records: tuple[dict[str, object], ...]
    tail_source_event_digest: str | None


def _resolve_chain_activation_snapshot(
    repository: Path,
    chains_descriptor: int,
    chain_id: str,
    *,
    allow_pending: bool,
    validate_lineage: bool,
    verify_external: bool = True,
    state_cap: int | None = None,
    events_cap: int | None = None,
    expected_binding: Mapping[str, object] | None = None,
    receipt_verifier: _ChainReceiptSnapshotVerifier | None = None,
) -> _ChainActivationSnapshot:
    """Replay one bound chain for first-use reservation or authorization.

    The shared builder remains authoritative for commit and historical merge
    histories.  Revision-10 additive merge histories use the DM-014 replay
    owned by this module; the shared Revision-9 transition validator cannot
    consume their additive compatibility projection.
    """

    _batch, builders, journal = runtime._coordination_modules()
    effective_state_cap = (
        builders._ACTIVATION_STATE_CAP_BYTES
        if state_cap is None
        else state_cap
    )
    effective_events_cap = (
        builders._ACTIVATION_EVENTS_CAP_BYTES
        if events_cap is None
        else events_cap
    )
    authority = builders._activation_event_one_binding_authority(
        chains_descriptor, chain_id
    )
    try:
        raw_events = builders._read_regular_bytes_at(
            chains_descriptor,
            f"{chain_id}.events.jsonl",
            cap=effective_events_cap,
        )
        try:
            first_event = json.loads(raw_events.splitlines()[0].decode("utf-8"))
        except (IndexError, UnicodeError, ValueError, RecursionError) as exc:
            raise builders._binding_replay_refusal() from exc
        merge_history = bool(
            isinstance(first_event, dict)
            and first_event.get("schema") == "forge-merge-event/1"
        )
        if expected_binding is not None and (
            authority is None
            or authority[0] != ("merge" if merge_history else "commit")
            or authority[1] != dict(expected_binding)
        ):
            raise builders._binding_replay_refusal()
        if merge_history:
            authority_binding = authority[1] if authority is not None else None
            if authority is not None and authority[0] != "merge":
                raise builders._binding_replay_refusal()
            replay = _replay_merge_event_bytes(
                chain_id,
                raw_events,
                verify_receipts=verify_external,
                receipt_repository=repository,
                expected_run_binding=(
                    dict(expected_binding)
                    if expected_binding is not None
                    else authority_binding
                    if isinstance(authority_binding, Mapping)
                    else None
                ),
                receipt_verifier=receipt_verifier,
            )
            if receipt_verifier is not None:
                receipt_verifier.recheck()
            if _merge_history_uses_additive_grammar(replay.events):
                raw_state = builders._read_regular_bytes_at(
                    chains_descriptor,
                    f"{chain_id}.json",
                    cap=effective_state_cap,
                )
                try:
                    materialized = json.loads(raw_state.decode("utf-8"))
                except (UnicodeError, ValueError, RecursionError) as exc:
                    raise builders._binding_replay_refusal() from exc
                if (
                    raw_state != canonical_bytes(replay.state) + b"\n"
                    or materialized != replay.state
                ):
                    raise builders._binding_replay_refusal()
                replay_binding = replay.state.get("run_binding")
                if expected_binding is not None:
                    if (
                        authority is None
                        or not isinstance(replay_binding, dict)
                        or replay_binding != dict(expected_binding)
                        or authority_binding != replay_binding
                    ):
                        raise builders._binding_replay_refusal()
                elif replay_binding is not None:
                    if (
                        not isinstance(replay_binding, dict)
                        or not builders._run_binding_valid(replay_binding)
                        or replay_binding.get("repository") != str(repository)
                        or authority_binding != replay_binding
                    ):
                        raise builders._binding_replay_refusal()
                elif authority is not None and authority_binding is not None:
                    raise builders._binding_replay_refusal()
                if (
                    replay.state.get("journal_outbox") is not None
                    and not allow_pending
                ):
                    raise journal.CoordinationRefusal(builders.JOURNAL_OUTBOX_PENDING)
                if validate_lineage:
                    _validate_chain_activation_lineage(
                        repository,
                        chains_descriptor,
                        chain_id,
                        replay.state,
                        raw_events=raw_events,
                        raw_state=raw_state,
                    )
                if (
                    builders._read_regular_bytes_at(
                        chains_descriptor,
                        f"{chain_id}.events.jsonl",
                        cap=effective_events_cap,
                    )
                    != raw_events
                ):
                    raise builders._binding_replay_refusal()
                if receipt_verifier is not None:
                    receipt_verifier.recheck()
                tail = replay.entries[-1]
                return _ChainActivationSnapshot(
                    family="merge",
                    state=copy.deepcopy(replay.state),
                    raw_events=raw_events,
                    raw_state=raw_state,
                    tail_records=tuple(copy.deepcopy(tail[3])),
                    tail_source_event_digest=tail[4],
                )

        builder_verify_external = verify_external and (
            receipt_verifier is None or not merge_history
        )
        builder_receipt_verifier = (
            receipt_verifier
            if verify_external and not merge_history
            else None
        )
        replayed = builders._resolve_binding_from_descriptor(
            repository,
            chains_descriptor,
            chain_id,
            ZERO_DIGEST,
            expected_type=None,
            expected_fields=None,
            expected_run_id=None,
            expected_task_id=None,
            replay_only=True,
            allow_pending=allow_pending,
            validate_lineage=False,
            verify_external=builder_verify_external,
            receipt_verifier=builder_receipt_verifier,
            resolve_tombstone=False,
            state_cap=effective_state_cap,
            events_cap=effective_events_cap,
        )
        rebound_events = builders._read_regular_bytes_at(
            chains_descriptor,
            f"{chain_id}.events.jsonl",
            cap=effective_events_cap,
        )
        raw_state = builders._read_regular_bytes_at(
            chains_descriptor,
            f"{chain_id}.json",
            cap=effective_state_cap,
        )
        family = replayed.get("kind")
        binding = replayed.get("run_binding")
        if (
            raw_events != rebound_events
            or raw_state != canonical_bytes(replayed) + b"\n"
            or family not in {"commit", "merge"}
            or (
                authority is not None
                and (authority[0] != family or authority[1] != binding)
            )
            or (binding is not None and authority is None)
            or (
                binding is not None
                and (
                    not isinstance(binding, dict)
                    or not builders._run_binding_valid(binding)
                    or binding.get("repository") != str(repository)
                )
            )
            or (
                expected_binding is not None
                and (
                    authority is None
                    or binding != dict(expected_binding)
                )
            )
        ):
            raise builders._binding_replay_refusal()
        try:
            tail_event = json.loads(raw_events.splitlines()[-1].decode("utf-8"))
        except (IndexError, UnicodeError, ValueError, RecursionError) as exc:
            raise builders._binding_replay_refusal() from exc
        if not isinstance(tail_event, dict):
            raise builders._binding_replay_refusal()
        tail_records, _tail_outbox, tail_source = builders._event_batch_records(
            tail_event, str(family)
        )
        if family == "merge" and validate_lineage:
            _validate_chain_activation_lineage(
                repository,
                chains_descriptor,
                chain_id,
                replayed,
                raw_events=raw_events,
                raw_state=raw_state,
            )
        if receipt_verifier is not None:
            receipt_verifier.recheck()
        return _ChainActivationSnapshot(
            family=str(family),
            state=copy.deepcopy(replayed),
            raw_events=raw_events,
            raw_state=raw_state,
            tail_records=tuple(copy.deepcopy(tail_records)),
            tail_source_event_digest=tail_source,
        )
    except journal.CoordinationRefusal:
        raise
    except (FrozenError, MemoryError, OSError) as exc:
        raise builders._binding_replay_refusal() from exc


def _resolve_chain_activation_projection(
    repository: Path,
    chains_descriptor: int,
    chain_id: str,
    *,
    allow_pending: bool,
    validate_lineage: bool,
    verify_external: bool = True,
    state_cap: int | None = None,
    events_cap: int | None = None,
    expected_binding: Mapping[str, object] | None = None,
    receipt_verifier: _ChainReceiptSnapshotVerifier | None = None,
) -> dict[str, object]:
    """Return the state from one exact activation replay snapshot."""

    return _resolve_chain_activation_snapshot(
        repository,
        chains_descriptor,
        chain_id,
        allow_pending=allow_pending,
        validate_lineage=validate_lineage,
        verify_external=verify_external,
        state_cap=state_cap,
        events_cap=events_cap,
        expected_binding=expected_binding,
        receipt_verifier=receipt_verifier,
    ).state


def _chain_activation_ownership_summary(
    repository: Path,
    chains_descriptor: int,
    chain_id: str,
    *,
    receipt_verifier: _ChainReceiptSnapshotVerifier | None = None,
) -> dict[str, object]:
    """Return one bounded ownership summary through the current grammar."""

    _batch, builders, _journal = runtime._coordination_modules()
    owns_verifier = receipt_verifier is None
    if receipt_verifier is None:
        receipt_verifier = _ChainReceiptSnapshotVerifier(repository)
    snapshot = _resolve_chain_activation_snapshot(
        repository,
        chains_descriptor,
        chain_id,
        allow_pending=True,
        validate_lineage=False,
        verify_external=True,
        state_cap=builders._ACTIVATION_STATE_CAP_BYTES,
        events_cap=builders._ACTIVATION_EVENTS_CAP_BYTES,
        receipt_verifier=receipt_verifier,
    )
    if snapshot.family == "commit":
        summary = {
            "family": "commit",
            "snapshot_event_digest": hashlib.sha256(
                snapshot.raw_events
            ).hexdigest(),
            "snapshot_state": copy.deepcopy(snapshot.state),
        }
        if owns_verifier:
            receipt_verifier.recheck()
        return summary
    try:
        events = tuple(
            json.loads(line.decode("utf-8"))
            for line in snapshot.raw_events.splitlines(keepends=False)
        )
        if not all(isinstance(event, dict) for event in events):
            raise ValueError("merge ownership event is not an object")
        summary = builders._merge_ownership_summary(
            chain_id,
            snapshot.state,
            events,
            snapshot.raw_events,
        )
        if owns_verifier:
            receipt_verifier.recheck()
        return summary
    except (
        UnicodeError,
        ValueError,
        RecursionError,
        MemoryError,
        _journal.CoordinationRefusal,
    ) as exc:
        raise builders._binding_replay_refusal() from exc


def _validate_chain_activation_lineage(
    repository: Path,
    chains_descriptor: int,
    chain_id: str,
    state: dict[str, object],
    *,
    raw_events: bytes,
    raw_state: bytes,
) -> None:
    """Apply DM-014's bounded ownership graph to either merge grammar."""

    _batch, builders, journal = runtime._coordination_modules()
    current_worktree = builders._merge_worktree_claim(state)
    if current_worktree is None:
        raise builders._binding_replay_refusal()
    current_identity = {
        name: current_worktree[0][name]
        for name in ("path", "git_dir", "common_dir")
    }
    try:
        names = builders._activation_chain_names(chains_descriptor)
    except OSError as exc:
        raise builders._binding_replay_refusal() from exc
    relevant_names = frozenset(
        name
        for name in names
        if (
            name.endswith(".events.jsonl")
            and journal.CHAIN_ID_PATTERN.fullmatch(
                name.removesuffix(".events.jsonl")
            )
            is not None
        )
        or (
            name.endswith(".json")
            and journal.CHAIN_ID_PATTERN.fullmatch(name.removesuffix(".json"))
            is not None
        )
    )
    chain_ids = sorted(
        {
            candidate_id
            for name in relevant_names
            for candidate_id in (
                name.removesuffix(".events.jsonl")
                if name.endswith(".events.jsonl")
                else name.removesuffix(".json")
                if name.endswith(".json")
                else "",
            )
            if journal.CHAIN_ID_PATTERN.fullmatch(candidate_id) is not None
        }
    )
    if chain_id not in chain_ids:
        raise builders._binding_replay_refusal()
    cap = len(chain_ids)
    summaries: dict[str, dict[str, object]] = {}
    snapshots: dict[str, dict[str, object]] = {}
    receipt_verifier = _ChainReceiptSnapshotVerifier(repository)
    for candidate_id in chain_ids:
        try:
            summary = _chain_activation_ownership_summary(
                repository,
                chains_descriptor,
                candidate_id,
                receipt_verifier=receipt_verifier,
            )
        except (journal.CoordinationRefusal, MemoryError) as exc:
            raise builders._binding_replay_refusal() from exc
        snapshots[candidate_id] = summary
        if summary.get("family") == "commit":
            continue
        if summary.get("identity") == current_identity:
            summaries[candidate_id] = summary
    current = summaries.get(chain_id)
    if (
        current is None
        or current.get("chain_id") != chain_id
        or current.get("snapshot_event_digest")
        != hashlib.sha256(raw_events).hexdigest()
        or current.get("snapshot_state") != state
        or canonical_bytes(current.get("snapshot_state")) + b"\n" != raw_state
    ):
        raise builders._binding_replay_refusal()
    current_is_durable_predecessor = bool(
        current.get("terminal") is True
        and current.get("claim_status") == "released"
    )

    acquired = {
        name: summary
        for name, summary in summaries.items()
        if summary.get("acquired") is True
    }
    children: dict[tuple[object, object], list[str]] = {}
    for name, summary in acquired.items():
        predecessor = (
            summary.get("predecessor_chain_id"),
            summary.get("predecessor_release_digest"),
        )
        children.setdefault(predecessor, []).append(name)
        predecessor_chain, predecessor_digest = predecessor
        if predecessor_chain is None:
            if predecessor_digest is not None:
                raise builders._binding_replay_refusal()
            continue
        predecessor_summary = acquired.get(str(predecessor_chain))
        if not current_is_durable_predecessor and (
            predecessor_summary is None
            or predecessor_summary.get("released_digest") != predecessor_digest
            or predecessor_summary.get("terminal") is not True
            or predecessor_summary.get("claim_status") != "released"
            or predecessor_summary.get("identity") != current_identity
        ):
            raise builders._binding_replay_refusal()

    cursor: dict[str, object] | None = current
    visited: set[str] = set()
    for _ in range(cap + 1):
        if cursor is None:
            break
        predecessor_chain = cursor.get("predecessor_chain_id")
        predecessor_digest = cursor.get("predecessor_release_digest")
        if predecessor_chain is None:
            if predecessor_digest is not None:
                raise builders._binding_replay_refusal()
            cursor = None
            break
        if not isinstance(predecessor_chain, str) or predecessor_chain in visited:
            raise builders._binding_replay_refusal()
        visited.add(predecessor_chain)
        predecessor = acquired.get(predecessor_chain)
        if (
            predecessor is None
            or predecessor.get("released_digest") != predecessor_digest
            or predecessor.get("terminal") is not True
        ):
            raise builders._binding_replay_refusal()
        cursor = predecessor
    if cursor is not None:
        raise builders._binding_replay_refusal()

    if not current_is_durable_predecessor:
        if any(len(values) > 1 for values in children.values()):
            raise builders._binding_replay_refusal()
        others = {
            name: value for name, value in acquired.items() if name != chain_id
        }
        parent_names = {
            str(value.get("predecessor_chain_id"))
            for value in others.values()
            if value.get("predecessor_chain_id") is not None
        }
        tails = [
            value
            for name, value in others.items()
            if name not in parent_names
            and value.get("terminal") is True
            and value.get("released_digest") is not None
        ]
        expected = (
            (None, None)
            if not others
            else (
                (tails[0].get("chain_id"), tails[0].get("released_digest"))
                if len(tails) == 1
                else None
            )
        )
        observed = (
            current.get("predecessor_chain_id"),
            current.get("predecessor_release_digest"),
        )
        if expected is None or observed != expected:
            raise builders._binding_replay_refusal()
    else:
        current_edge = (
            current.get("predecessor_chain_id"),
            current.get("predecessor_release_digest"),
        )
        terminal_siblings = [
            name
            for name in children.get(current_edge, [])
            if name != chain_id
            and acquired[name].get("terminal") is True
            and acquired[name].get("claim_status") == "released"
        ]
        if terminal_siblings:
            raise builders._binding_replay_refusal()

    for candidate_id, snapshot in snapshots.items():
        try:
            raw_events = builders._read_regular_bytes_at(
                chains_descriptor,
                f"{candidate_id}.events.jsonl",
                cap=builders._ACTIVATION_EVENTS_CAP_BYTES,
            )
            raw_state = builders._read_regular_bytes_at(
                chains_descriptor,
                f"{candidate_id}.json",
                cap=builders._ACTIVATION_STATE_CAP_BYTES,
            )
        except (journal.CoordinationRefusal, MemoryError) as exc:
            raise builders._binding_replay_refusal() from exc
        if (
            hashlib.sha256(raw_events).hexdigest()
            != snapshot.get("snapshot_event_digest")
            or raw_state
            != canonical_bytes(snapshot.get("snapshot_state")) + b"\n"
        ):
            raise builders._binding_replay_refusal()
    try:
        final_names = builders._activation_chain_names(chains_descriptor)
    except OSError as exc:
        raise builders._binding_replay_refusal() from exc
    final_relevant_names = frozenset(
        name
        for name in final_names
        if (
            name.endswith(".events.jsonl")
            and journal.CHAIN_ID_PATTERN.fullmatch(
                name.removesuffix(".events.jsonl")
            )
            is not None
        )
        or (
            name.endswith(".json")
            and journal.CHAIN_ID_PATTERN.fullmatch(name.removesuffix(".json"))
            is not None
        )
    )
    if final_relevant_names != relevant_names:
        raise builders._binding_replay_refusal()
    receipt_verifier.recheck()


def _require_no_pending_chain_activation_outbox(
    repository: Path, run_id: str
) -> None:
    """Reserve legacy first use across commit and additive merge outboxes."""

    _batch, builders, journal = runtime._coordination_modules()
    chains_root = builders.chain_storage_root(repository)
    descriptor: int | None = None
    try:
        descriptor, root_observation = journal._open_bound_directory(chains_root)
        names = builders._activation_chain_names(descriptor)
        if (
            journal._file_observation(os.fstat(descriptor)) != root_observation
            or journal._file_observation(os.lstat(chains_root)) != root_observation
        ):
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    except FileNotFoundError:
        return
    except journal.CoordinationRefusal:
        raise
    except OSError as exc:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED) from exc

    try:
        warned: set[str] = set()

        def warn_unreadable(chain_id: str, family: str = "activation") -> None:
            if chain_id in warned:
                return
            warned.add(chain_id)
            print(
                "forge: warning — skipped unreadable chain "
                f"{chain_id} while enumerating {family} chains",
                file=sys.stderr,
            )

        def bound_materialized_states(
            observed_names: Iterable[str],
        ) -> dict[str, object]:
            state_ids = {
                name[:-5]
                for name in observed_names
                if name.endswith(".json")
                and journal.CHAIN_ID_PATTERN.fullmatch(name[:-5]) is not None
            }
            event_ids = {
                name[: -len(".events.jsonl")]
                for name in observed_names
                if name.endswith(".events.jsonl")
                and journal.CHAIN_ID_PATTERN.fullmatch(
                    name[: -len(".events.jsonl")]
                )
                is not None
            }
            bound: dict[str, object] = {}
            for chain_id in sorted(state_ids | event_ids, key=os.fsencode):
                authority = (
                    builders._activation_event_one_binding_authority(
                        descriptor, chain_id
                    )
                    if chain_id in event_ids
                    else None
                )
                authority_family, authority_binding = (
                    authority if authority is not None else ("activation", None)
                )
                authority_targets_run = builders._activation_chain_bound_to_run(
                    authority_binding, repository, run_id
                )
                if chain_id not in state_ids:
                    if authority_targets_run:
                        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
                    warn_unreadable(chain_id, authority_family)
                    continue
                try:
                    state = builders._read_json_at(
                        descriptor,
                        f"{chain_id}.json",
                        cap=builders._ACTIVATION_STATE_CAP_BYTES,
                    )
                except journal.CoordinationRefusal as exc:
                    if authority_targets_run:
                        raise journal.CoordinationRefusal(
                            journal.BATCH_DIVERGED
                        ) from exc
                    warn_unreadable(chain_id, authority_family)
                    continue
                if not isinstance(state, dict):
                    if authority_targets_run:
                        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
                    warn_unreadable(chain_id)
                    continue
                family = (
                    str(state["kind"])
                    if state.get("kind") in {"commit", "merge"}
                    else "activation"
                )
                binding = state.get("run_binding")
                state_targets_run = builders._activation_chain_bound_to_run(
                    binding, repository, run_id
                )
                if authority is None:
                    if state_targets_run:
                        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
                    warn_unreadable(chain_id, family)
                    continue
                if (
                    family != authority_family
                    or binding != authority_binding
                ):
                    if authority_targets_run or state_targets_run:
                        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
                    warn_unreadable(chain_id, family)
                    continue
                if authority_targets_run:
                    bound[chain_id] = copy.deepcopy(authority_binding)
            return bound

        bound = bound_materialized_states(names)
        for chain_id in sorted(bound, key=os.fsencode):
            binding = bound[chain_id]
            try:
                replayed = _resolve_chain_activation_projection(
                    repository,
                    descriptor,
                    chain_id,
                    allow_pending=True,
                    validate_lineage=False,
                    state_cap=builders._ACTIVATION_STATE_CAP_BYTES,
                    events_cap=builders._ACTIVATION_EVENTS_CAP_BYTES,
                    expected_binding=(
                        binding if isinstance(binding, Mapping) else None
                    ),
                )
            except (journal.CoordinationRefusal, MemoryError) as exc:
                raise journal.CoordinationRefusal(
                    journal.BATCH_DIVERGED
                ) from exc
            if replayed.get("run_binding") != binding:
                raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
            if replayed.get("journal_outbox") is not None:
                raise journal.CoordinationRefusal(
                    builders.JOURNAL_OUTBOX_PENDING
                )

        final_names = builders._activation_chain_names(descriptor)
        final_bound = bound_materialized_states(final_names)
        required_artifacts = {
            artifact
            for chain_id in final_bound
            for artifact in (
                f"{chain_id}.json",
                f"{chain_id}.events.jsonl",
            )
        }
        if (
            journal._file_observation(os.fstat(descriptor)) != root_observation
            or journal._file_observation(os.lstat(chains_root)) != root_observation
            or not builders._activation_bound_set_stable(bound, final_bound)
            or not required_artifacts.issubset(final_names)
        ):
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _prepare_merge_activation_preamble(
    repository: Path, state: Any
) -> tuple[dict[str, object], ...]:
    """Construct one authenticated additive-merge first-use preamble."""

    batch, builders, journal = runtime._coordination_modules()
    run_dir = getattr(state, "run_dir", None)
    active = batch._active_locks().get(os.path.abspath(os.fspath(run_dir)))
    if active is None:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    if (
        batch._validate_no_orphan_intent_temporary(active) is not None
        or batch._load_intent(active) is not None
    ):
        raise journal.CoordinationRefusal(journal.BATCH_PENDING)
    _require_no_pending_chain_activation_outbox(repository, state.run_id)
    origin, origin_sha256 = batch._legacy_activation_origin_locked(active)
    marker = builders._writer_activation_decision(
        state,
        receipt_origin_size=origin,
        receipt_origin_sha256=origin_sha256,
    )
    return batch._activation_preamble_records(
        active,
        state,
        repository,
        (marker,),
        carried=True,
    )


def _prevalidate_chain_batch_carrier(
    state: Mapping[str, Any],
    pending_outbox: Mapping[str, Any],
    carried_records: Sequence[dict[str, Any]],
) -> None:
    """Validate and bootstrap one commit carrier before it becomes durable.

    The outer run lock is already held by ``ChainStore.persist``.  Complete
    every deterministic run/record check, then create and rebind a legacy
    receipt ledger while the prospective event still exists only in memory.
    The ordinary drain repeats these checks against the durable carrier.
    """

    batch, builders, journal = runtime._coordination_modules()
    binding = state.get("run_binding")
    records = tuple(carried_records)
    if (
        not isinstance(binding, Mapping)
        or not builders._run_binding_valid(dict(binding))
        or not records
        or not all(isinstance(record, dict) for record in records)
    ):
        raise journal.CoordinationRefusal(journal.INVALID_JOURNAL_RECORD)
    repository = Path(str(binding["repository"]))
    run_id = str(binding["run_id"])
    batch_bytes = b"".join(journal._journal_line(record) for record in records)
    expected_outbox = {
        "idempotency_key": pending_outbox.get("source_event_digest"),
        "batch_digest": journal._sha256(batch_bytes),
        "record_count": len(records),
        "source_event_digest": pending_outbox.get("source_event_digest"),
    }
    if (
        dict(pending_outbox) != expected_outbox
        or state.get("journal_outbox") != expected_outbox
    ):
        raise journal.CoordinationRefusal(journal.INVALID_JOURNAL_RECORD)

    _canonical_repository, state_root = journal._resolve_repository(
        repository, "journal batch"
    )
    run_dir = state_root / ".codex-orchestrator" / "runs" / run_id
    active = batch._active_locks().get(os.path.abspath(os.fspath(run_dir)))
    if active is None:
        raise journal.CoordinationRefusal(journal.INVALID_JOURNAL_RECORD)

    # Mirror execute_existing_batch's read-only schema/lifecycle phases before
    # the carrier exists.  Binding authentication itself is supplied by the
    # prospective event replay in ChainStore.persist below.
    batch._validate_batch_lock(active)
    batch._validate_no_orphan_intent_temporary(active)
    if batch._load_intent(active) is not None:
        raise journal.CoordinationRefusal(journal.BATCH_PENDING)
    journal_exact = batch._optional_exact_named_file(active, "journal.jsonl")
    if journal_exact is None:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    run_state = journal._scan_run(
        run_dir,
        raw=journal_exact.payload,
        directory_observation=journal._file_observation(
            os.fstat(active.run_descriptor)
        ),
        journal_observation=journal_exact.observation,
    )
    if (
        run_state.run_id != run_id
        or binding.get("task_id") not in {
            record.get("id")
            for record in run_state.records
            if record.get("type") == "task"
            and record.get("status") == "active"
        }
        or journal._recorded_repository_root(
            run_state.run_dir, state_root, records=run_state.records
        )
        != _canonical_repository
    ):
        raise journal.CoordinationRefusal(journal.INVALID_JOURNAL_RECORD)
    batch._validate_target_lifecycle(run_state, close=False)
    journal._classify_owner(
        run_state,
        batch._read_only_session_owner(),
        adopt_missing=run_state.pre_coordination,
    )
    for record in records:
        journal._validate_record_envelope(record)
    batch._prevalidate_records(
        _canonical_repository,
        run_state,
        records,
        close=False,
        defer_binding=True,
    )

    try:
        if (
            batch._activation_preamble_records(
                active,
                run_state,
                _canonical_repository,
                records,
                carried=True,
            )
            != records
        ):
            raise journal.CoordinationRefusal(journal.INVALID_JOURNAL_RECORD)
        receipts_exact = batch._optional_exact_named_file(
            active, journal.BATCH_RECEIPTS_NAME
        )
        if receipts_exact is None:
            if not batch._legacy_batch_first_use(active.run_descriptor):
                raise journal.CoordinationRefusal(journal.INVALID_JOURNAL_RECORD)
            created = batch._ensure_receipt_ledger(active)
            receipts_exact = batch._optional_exact_named_file(
                active, journal.BATCH_RECEIPTS_NAME
            )
            if receipts_exact != journal.ExactFile(b"", created):
                raise journal.CoordinationRefusal(journal.INVALID_JOURNAL_RECORD)
        _receipts, receipts_raw, receipts_observation = batch._load_receipts(
            active
        )
        if (
            receipts_exact
            != journal.ExactFile(receipts_raw, receipts_observation)
            or batch._optional_exact_named_file(active, "journal.jsonl")
            != journal_exact
            or batch._load_intent(active) is not None
            or batch._activation_preamble_records(
                active,
                run_state,
                _canonical_repository,
                records,
                carried=True,
            )
            != records
        ):
            raise journal.CoordinationRefusal(journal.INVALID_JOURNAL_RECORD)
        batch._validate_no_orphan_intent_temporary(active)
        batch._validate_batch_lock(active)
    except (OSError, FrozenError, journal.CoordinationRefusal) as exc:
        raise journal.CoordinationRefusal(
            journal.INVALID_JOURNAL_RECORD
        ) from exc


def _authorize_chain_batch(**arguments: Any) -> object:
    """Exchange one process-local opaque capability for task-03 authority."""

    batch, builders, journal = runtime._coordination_modules()
    capability = arguments.get("capability")
    registry = getattr(batch, "_FORGE_CLI_CHAIN_CAPABILITIES", None)
    registry_lock = getattr(batch, "_FORGE_CLI_CHAIN_CAPABILITIES_LOCK", None)
    if not isinstance(registry, dict) or registry_lock is None:
        raise journal.CoordinationRefusal(journal.INVALID_JOURNAL_RECORD)
    with registry_lock:
        registered = registry.get(id(capability))
        if (
            not isinstance(registered, tuple)
            or len(registered) != 2
            or registered[0] is not capability
        ):
            raise journal.CoordinationRefusal(journal.INVALID_JOURNAL_RECORD)
        authority = copy.deepcopy(registered[1])
    if not isinstance(authority, dict):
        raise journal.CoordinationRefusal(journal.INVALID_JOURNAL_RECORD)
    required = {
        "repository",
        "run_id",
        "task_id",
        "chain_id",
        "run_binding",
        "pending_outbox",
        "source_event_digest",
        "records",
    }
    if set(authority) != required or any(
        arguments.get(name) != authority[name]
        for name in (
            "repository",
            "run_id",
            "task_id",
            "chain_id",
            "source_event_digest",
        )
    ) or tuple(arguments.get("supplied_records", ())) != tuple(authority["records"]):
        raise journal.CoordinationRefusal(journal.INVALID_JOURNAL_RECORD)

    repository = Path(str(authority["repository"]))
    chain_id = str(authority["chain_id"])
    run_binding = authority["run_binding"]
    pending_outbox = authority["pending_outbox"]
    records = tuple(authority["records"])
    source_event_digest = authority["source_event_digest"]
    if (
        not isinstance(run_binding, dict)
        or not builders._run_binding_valid(run_binding)
        or run_binding
        != {
            "run_id": authority["run_id"],
            "task_id": authority["task_id"],
            "repository": str(repository),
            "policy_digest": run_binding.get("policy_digest"),
        }
        or not isinstance(pending_outbox, dict)
        or not isinstance(source_event_digest, str)
        or journal.HEX_SHA256_PATTERN.fullmatch(source_event_digest) is None
        or not records
        or not all(isinstance(record, dict) for record in records)
    ):
        raise journal.CoordinationRefusal(journal.INVALID_JOURNAL_RECORD)
    batch_bytes = b"".join(journal._journal_line(record) for record in records)
    expected_outbox = {
        "idempotency_key": source_event_digest,
        "batch_digest": journal._sha256(batch_bytes),
        "record_count": len(records),
        "source_event_digest": source_event_digest,
    }
    if pending_outbox != expected_outbox:
        raise journal.CoordinationRefusal(journal.INVALID_JOURNAL_RECORD)

    chains_root = _chain_storage_root(repository)
    chains_descriptor: int | None = None
    try:
        chains_descriptor, chains_observation = journal._open_bound_directory(
            chains_root
        )
        with builders._chain_event_lock(
            chains_root,
            chain_id,
            root_descriptor=chains_descriptor,
            root_observation=chains_observation,
        ):
            snapshot = _resolve_chain_activation_snapshot(
                repository,
                chains_descriptor,
                chain_id,
                allow_pending=True,
                validate_lineage=True,
                state_cap=builders._ACTIVATION_STATE_CAP_BYTES,
                events_cap=builders._ACTIVATION_EVENTS_CAP_BYTES,
                expected_binding=run_binding,
            )
            if (
                snapshot.state.get("run_binding") != run_binding
                or snapshot.state.get("journal_outbox") != expected_outbox
                or snapshot.tail_records != records
                or snapshot.tail_source_event_digest != source_event_digest
                or journal._file_observation(os.fstat(chains_descriptor))
                != chains_observation
                or journal._file_observation(os.lstat(chains_root))
                != chains_observation
            ):
                raise journal.CoordinationRefusal(
                    journal.INVALID_JOURNAL_RECORD
                )

            _canonical_repository, state_root = journal._resolve_repository(
                repository, "journal batch"
            )
            run_dir = (
                state_root
                / ".codex-orchestrator"
                / "runs"
                / str(authority["run_id"])
            )
            active = batch._active_locks().get(
                os.path.abspath(os.fspath(run_dir))
            )
            if active is None:
                raise journal.CoordinationRefusal(
                    journal.INVALID_JOURNAL_RECORD
                )
            journal_exact = batch._optional_exact_named_file(
                active, "journal.jsonl"
            )
            receipts_exact = batch._optional_exact_named_file(
                active, journal.BATCH_RECEIPTS_NAME
            )
            if journal_exact is None:
                raise journal.CoordinationRefusal(
                    journal.INVALID_JOURNAL_RECORD
                )
            state = journal._scan_run(run_dir, raw=journal_exact.payload)
            if (
                batch._activation_preamble_records(
                    active,
                    state,
                    repository,
                    records,
                    carried=True,
                )
                != records
            ):
                raise journal.CoordinationRefusal(
                    journal.INVALID_JOURNAL_RECORD
                )
            if receipts_exact is None:
                if (
                    not batch._legacy_batch_first_use(active.run_descriptor)
                ):
                    raise journal.CoordinationRefusal(
                        journal.INVALID_JOURNAL_RECORD
                    )
                rebound_snapshot = _resolve_chain_activation_snapshot(
                    repository,
                    chains_descriptor,
                    chain_id,
                    allow_pending=True,
                    validate_lineage=True,
                    state_cap=builders._ACTIVATION_STATE_CAP_BYTES,
                    events_cap=builders._ACTIVATION_EVENTS_CAP_BYTES,
                    expected_binding=run_binding,
                )
                if rebound_snapshot != snapshot:
                    raise journal.CoordinationRefusal(
                        journal.INVALID_JOURNAL_RECORD
                    )
                created = batch._ensure_receipt_ledger(active)
                receipts_exact = batch._optional_exact_named_file(
                    active, journal.BATCH_RECEIPTS_NAME
                )
                rebound_journal = batch._optional_exact_named_file(
                    active, "journal.jsonl"
                )
                final_snapshot = _resolve_chain_activation_snapshot(
                    repository,
                    chains_descriptor,
                    chain_id,
                    allow_pending=True,
                    validate_lineage=True,
                    state_cap=builders._ACTIVATION_STATE_CAP_BYTES,
                    events_cap=builders._ACTIVATION_EVENTS_CAP_BYTES,
                    expected_binding=run_binding,
                )
                if (
                    receipts_exact != journal.ExactFile(b"", created)
                    or rebound_journal != journal_exact
                    or final_snapshot != snapshot
                ):
                    raise journal.CoordinationRefusal(
                        journal.INVALID_JOURNAL_RECORD
                    )
    except (OSError, FrozenError, journal.CoordinationRefusal) as exc:
        raise journal.CoordinationRefusal(
            journal.INVALID_JOURNAL_RECORD
        ) from exc
    finally:
        if chains_descriptor is not None:
            os.close(chains_descriptor)
    _, request_sha256 = batch.normalized_request(
        repository,
        str(authority["run_id"]),
        "chain outbox-drain",
        {
            "chain_id": chain_id,
            "source_event_digest": authority["source_event_digest"],
            "batch_digest": journal._sha256(batch_bytes),
            "record_count": len(records),
        },
    )
    return batch._ChainBatchAuthorization(
        repository=str(repository),
        run_id=str(authority["run_id"]),
        task_id=str(authority["task_id"]),
        chain_id=chain_id,
        source_event_digest=str(authority["source_event_digest"]),
        request_sha256=request_sha256,
        batch_bytes=batch_bytes,
        record_count=len(records),
        journal_exact=journal_exact,
        receipts_exact=receipts_exact,
    )


def _verify_and_build_ingest_records(
    repository: Path, run_id: str, inputs: dict[str, object]
) -> tuple[Sequence[dict[str, object]], tuple[str, ...]]:
    """Prove and synthesize one terminal, previously unbound commit/merge chain.

    The specification intentionally leaves the outcome-map dialect open.  This
    implementation owns one strict, versioned form: exactly ``schema``,
    ``chain_id``, ``task``, ``task_status``, and the ordered
    ``event_digests`` selected for ordinary records.  Unknown members fail
    closed instead of becoming implicit authority.
    """

    _batch, builders, journal = runtime._coordination_modules()
    if (
        INGEST_PROOF_CONTROLS != _REQUIRED_INGEST_PROOF_CONTROLS
        or tuple(builders._INGEST_PROOF_ORDER) != INGEST_PROOF_ORDER
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    required_inputs = {
        "task",
        "state_file",
        "events_file",
        "outcome_map",
        "state_file_sha256",
        "events_file_sha256",
        "outcome_map_sha256",
        "closing_head",
        "task_status",
    }
    if set(inputs) != required_inputs:
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    canonical_repository, state_root = journal._resolve_repository(
        repository, "journal ingest-chain"
    )
    run_dir = state_root / ".codex-orchestrator" / "runs" / run_id

    # Matching intent/receipt recovery is handled by task-03's pre-allocation
    # lookup before this verifier is entered.  Proof must never search receipts
    # by request digest or re-authorize an already receipted terminal batch.
    existing_records: tuple[dict[str, object], ...] | None = None
    base_records: list[dict[str, object]] | None = None
    captured_paths = _ingest_captured_paths(
        canonical_repository, run_dir, inputs
    )
    raw: dict[str, bytes] = {}
    capture_names = {
        "state_file": "state.json",
        "events_file": "events.jsonl",
        "outcome_map": "outcome-map.json",
    }
    for field in ("state_file", "events_file", "outcome_map"):
        path = inputs.get(field)
        digest = inputs.get(f"{field}_sha256")
        if not isinstance(path, str) or not isinstance(digest, str):
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
        raw[field] = _read_ingest_input(
            canonical_repository,
            captured_paths[field],
            f"ingest.{field}",
            run_dir=run_dir,
            expected_capture_name=capture_names[field],
        )
        if sha256_bytes(raw[field]) != digest:
            raise journal.CoordinationRefusal(
                "forge: journal append refused — record cites path outside run or "
                "repository: ingest.captured_package: "
                f"{captured_paths[field]}"
            )
    try:
        materialized = json.loads(raw["state_file"].decode("utf-8"))
        outcome_map = json.loads(raw["outcome_map"].decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID) from exc
    if not isinstance(materialized, dict):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    chain_id = materialized.get("chain_id")
    family = materialized.get("kind")
    if not isinstance(chain_id, str):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    if family == "commit":
        try:
            validate_state(materialized, chain_id)
        except FrozenError as exc:
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID) from exc
    elif family == "merge":
        if not _merge_ingest_state_shape_valid(builders, materialized, chain_id):
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    else:
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    completed_proofs: list[str] = []

    # Proof 1: canonical schema and digest replay in original event order.
    _require_ingest_proof(
        "chain-schema-and-digest-replay", completed_proofs
    )
    event_bytes = raw["events_file"]
    if not event_bytes or not event_bytes.endswith(b"\n"):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    replayed: dict[str, object] | None = None
    events: list[
        tuple[
            dict[str, object],
            dict[str, object] | None,
            dict[str, object],
        ]
    ] = []
    previous_digest = ZERO_DIGEST
    for sequence, line in enumerate(event_bytes.splitlines(keepends=True), 1):
        try:
            event = json.loads(line.decode("utf-8"))
        except (UnicodeError, ValueError, RecursionError) as exc:
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID) from exc
        if family == "commit":
            event_shape_valid = bool(
                isinstance(event, dict)
                and set(event) == EVENT_KEYS
                and event.get("sequence") == sequence
                and event.get("prev_digest") == previous_digest
            )
        else:
            event_shape_valid = bool(
                isinstance(event, dict)
                and set(event)
                == {
                    "schema",
                    "chain_id",
                    "sequence",
                    "at",
                    "event",
                    "generation_digest",
                    "previous_digest",
                    "payload",
                    "digest",
                }
                and event.get("schema") == "forge-merge-event/1"
                and event.get("chain_id") == chain_id
                and event.get("sequence") == sequence
                and event.get("previous_digest") == previous_digest
            )
        if (
            not event_shape_valid
            or not isinstance(event, dict)
            or line != canonical_bytes(event) + b"\n"
        ):
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
        projection = {name: event[name] for name in event if name != "digest"}
        if sha256_bytes(canonical_bytes(projection)) != event.get("digest"):
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
        payload = event.get("payload")
        prior_state = copy.deepcopy(replayed)
        if family == "commit":
            if not isinstance(payload, dict) or set(payload) != {
                "at",
                "details",
                "event",
                "state",
            }:
                raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
            details = payload.get("details")
            state = payload.get("state")
            if (
                not isinstance(details, dict)
                or "journal_batch" in details
                or "source_event_digest" in details
                or not isinstance(state, dict)
            ):
                raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
            try:
                validate_state(state, chain_id)
            except FrozenError as exc:
                raise journal.CoordinationRefusal(
                    builders.INGEST_PROOF_INVALID
                ) from exc
            next_state = copy.deepcopy(state)
        else:
            if (
                not isinstance(payload, dict)
                or "state" in payload
                or "journal_batch" in payload
                or "source_event_digest" in payload
                or event.get("event") == "journal_receipted"
            ):
                raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
            try:
                next_state = reduce_merge_event(replayed, event)
            except (KeyError, TypeError, ValueError, RuntimeError) as exc:
                raise journal.CoordinationRefusal(
                    builders.INGEST_PROOF_INVALID
                ) from exc
            if (
                not _merge_ingest_state_shape_valid(builders, next_state, chain_id)
            ):
                raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
        replayed = copy.deepcopy(next_state)
        events.append((event, prior_state, copy.deepcopy(next_state)))
        previous_digest = str(event["digest"])
    # Proof 2: the exact replay result is the caller-supplied materialization.
    _require_ingest_proof("materialized-state", completed_proofs)
    if replayed != materialized:
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    if family == "merge":
        return _verify_and_build_merge_ingest_records(
            canonical_repository=canonical_repository,
            run_id=run_id,
            run_dir=run_dir,
            inputs=inputs,
            materialized=materialized,
            outcome_map=outcome_map,
            events=events,
            existing_records=existing_records,
            base_records=base_records,
            captured_state=raw["state_file"],
            captured_events=raw["events_file"],
            completed_proofs=completed_proofs,
        )

    # Proof 3: the terminal unbound chain names this repository.  A bound or
    # carried chain belongs to the autoappend path and cannot be ingested.
    _require_ingest_proof("repository", completed_proofs)
    run_state = journal._scan_run(run_dir)
    proof_records = base_records if base_records is not None else run_state.records
    opening = proof_records[0] if proof_records else None
    try:
        opening_repository = (
            Path(str(opening.get("repo", ""))).resolve(strict=True)
            if isinstance(opening, dict)
            else None
        )
    except OSError as exc:
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID) from exc
    if (
        materialized.get("kind") != "commit"
        or materialized.get("state") != "closed"
        or materialized.get("run_binding") is not None
        or materialized.get("journal_outbox") is not None
        or materialized.get("staging", {}).get("worktree_root")
        != str(canonical_repository)
        or not isinstance(materialized.get("candidate"), dict)
        or SHA256_RE.fullmatch(
            str(materialized.get("candidate", {}).get("sha256", ""))
        )
        is None
        or opening_repository != canonical_repository
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    # Proof 4: the generation's policy identity resolves to exact committed
    # bytes, not a mutable worktree copy.
    _require_ingest_proof("policy", completed_proofs)
    policy_source = materialized.get("policy_source")
    if not isinstance(policy_source, dict):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    policy = subprocess.run(
        [
            "git",
            "-C",
            str(canonical_repository),
            "show",
            f"{policy_source.get('sha')}:forge-project.md",
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if (
        policy.returncode != 0
        or sha256_bytes(policy.stdout) != policy_source.get("digest")
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    try:
        parsed_policy = parse_policy(str(policy_source["sha"]), policy.stdout)
    except (KeyError, PolicyError, UnicodeError) as exc:
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID) from exc

    # Proof 5: freshness is established against the live authoritative chain
    # while holding its native event lock, including byte-identical events.
    _require_ingest_proof("generation", completed_proofs)
    _prove_ingest_live_chain(
        canonical_repository,
        chain_id,
        materialized,
        raw["state_file"],
        raw["events_file"],
    )

    # Proof 6: every required gate remains satisfied by the current candidate.
    _require_ingest_proof("current-gates", completed_proofs)
    context = CommandContext(
        repo=Repository(canonical_repository),
        store=ChainStore(Repository(canonical_repository).common_root()),
        options=CLIOptions(repo=str(canonical_repository), revision9_face=True),
        policy=parsed_policy,
    )
    tier = materialized.get("tier")
    if (
        not isinstance(tier, dict)
        or tier.get("effective") not in TIER_RANK
        or tier.get("derived") not in TIER_RANK
        or (
            tier.get("declared") is not None
            and tier.get("declared") not in TIER_RANK
        )
        or type(tier.get("control")) is not bool
        or not _latest_current_pass(materialized, "classification")
        or (
            tier.get("effective") == "fast"
            and (
                bool(runtime._fast_mechanical_skips(materialized))
                or not _latest_current_pass(materialized, "fast-eligibility")
                or not _latest_current_pass(
                    materialized, "fast-finalize-eligibility"
                )
            )
        )
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    required_steps = _required_steps(context, materialized)
    if (
        not _gate_one_complete(materialized)
        or not all(
            _gate_satisfied(materialized, step)
            for step in set(required_steps) - {"gate-1"}
        )
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    # Proofs 7–10: independently re-open the current review package, then bind
    # role, iteration, and verdict in normative order.  Fast chains make the
    # predicates vacuous, but every control remains load-bearing.
    review = materialized.get("review")
    if not isinstance(review, dict) or not isinstance(tier, dict):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    review_required = tier.get("effective") != "fast"
    request = review.get("request")
    verdict = review.get("verdict")

    _require_ingest_proof("review-package", completed_proofs)
    if review_required:
        if (
            not isinstance(request, dict)
            or not isinstance(verdict, dict)
            or request.get("candidate")
            != materialized["candidate"]["sha256"]
            or not isinstance(request.get("package"), str)
            or not isinstance(request.get("package_digest"), str)
            or SHA256_RE.fullmatch(str(request["package_digest"])) is None
        ):
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
        package = _read_ingest_input(
            canonical_repository,
            str(request["package"]),
            "ingest.reviewer_package",
        )
        if sha256_bytes(package) != request.get("package_digest"):
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    _require_ingest_proof("reviewer-role", completed_proofs)
    if review_required:
        assert isinstance(request, dict)
        expected_role = (
            "review-cheap"
            if tier.get("effective") == "standard"
            else "review-final"
        )
        if request.get("reviewer") != expected_role:
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    _require_ingest_proof("reviewer-iteration", completed_proofs)
    if review_required:
        assert isinstance(request, dict)
        if (
            type(review.get("iteration")) is not int
            or int(review["iteration"]) <= 0
            or request.get("iteration") != review.get("iteration")
        ):
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    _require_ingest_proof("reviewer-verdict", completed_proofs)
    if review_required:
        assert isinstance(request, dict) and isinstance(verdict, dict)
        if (
            verdict.get("verdict") != "PASS"
            or verdict.get("candidate")
            != materialized["candidate"]["sha256"]
            or verdict.get("package_digest") != request.get("package_digest")
        ):
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    # Proof 11: approval is required exactly for the native parked classes.
    _require_ingest_proof("operator-approval", completed_proofs)
    approval_required = bool(
        tier.get("control") or review.get("operator_cosign_required")
    )
    approval = materialized.get("approval")
    if approval_required and (
        not isinstance(approval, dict)
        or approval.get("candidate") != materialized["candidate"]["sha256"]
        or not isinstance(approval.get("approved_at"), str)
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    # Proof 12: the staged candidate is exactly the produced commit.
    _require_ingest_proof("landing-proof", completed_proofs)
    result = materialized.get("commit_result")
    commit_sha = result.get("commit_sha") if isinstance(result, dict) else None
    intent = result.get("intent") if isinstance(result, dict) else None
    if (
        not isinstance(commit_sha, str)
        or COMMIT_RE.fullmatch(commit_sha) is None
        or not isinstance(intent, dict)
        or intent.get("candidate") != materialized["candidate"]["sha256"]
        or not isinstance(intent.get("pre_head"), str)
        or COMMIT_RE.fullmatch(str(intent["pre_head"])) is None
        or not isinstance(intent.get("message_digest"), str)
        or SHA256_RE.fullmatch(str(intent["message_digest"])) is None
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    if candidate_is_v2(materialized):
        candidate_record = materialized["candidate"]
        identity = result.get("identity") if isinstance(result, dict) else None
        if (
            intent.get("authorization_id") != candidate_record.get("authorization_id")
            or intent.get("object_format") != candidate_record.get("object_format")
            or intent.get("expected_tree_oid") != candidate_record.get("tree_oid")
            or candidate_record.get("base_commit_oid") != intent.get("pre_head")
            or not isinstance(identity, dict)
            or identity.get("result") != "passed"
            or identity.get("produced_sha") != commit_sha
        ):
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
        try:
            candidate_context = candidate_module.discover_context(canonical_repository)
            committed = candidate_module.read_commit_object(
                candidate_context, commit_sha
            )
            parent_object = candidate_module.read_commit_object(
                candidate_context, str(intent["pre_head"])
            )
            if len(parent_object.tree_headers) != 1:
                raise candidate_module.CandidateError(
                    "pre-commit object has malformed tree headers"
                )
            _path_bytes, changed_paths = candidate_module.enumerate_tree_pair(
                candidate_context,
                parent_object.tree_headers[0],
                str(candidate_record["tree_oid"]),
            )
        except (candidate_module.CandidateError, KeyError, OSError) as exc:
            raise journal.CoordinationRefusal(
                builders.INGEST_PROOF_INVALID
            ) from exc
        if (
            committed.parent_headers != (str(intent["pre_head"]),)
            or committed.tree_headers != (str(candidate_record["tree_oid"]),)
            or sha256_bytes(committed.message) != intent["message_digest"]
            or tuple(materialized.get("paths", ())) != changed_paths
            or not changed_paths
            or not all(journal._valid_scope_item(path) for path in changed_paths)
        ):
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    else:
        parent = subprocess.run(
            ["git", "-C", str(canonical_repository), "rev-parse", f"{commit_sha}^"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        if parent.returncode != 0:
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
        parent_sha = parent.stdout.decode("ascii", "replace").strip()
        commit_object = subprocess.run(
            ["git", "-C", str(canonical_repository), "cat-file", "commit", commit_sha],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        try:
            commit_headers, commit_message = commit_object.stdout.split(b"\n\n", 1)
        except IndexError as exc:
            raise journal.CoordinationRefusal(
                builders.INGEST_PROOF_INVALID
            ) from exc
        parent_headers = [
            line[len(b"parent ") :]
            for line in commit_headers.splitlines()
            if line.startswith(b"parent ")
        ]
        diff = subprocess.run(
            ["git", "-C", str(canonical_repository), "diff", parent_sha, commit_sha],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        names = subprocess.run(
            [
                "git",
                "-C",
                str(canonical_repository),
                "diff",
                "--name-only",
                "-z",
                parent_sha,
                commit_sha,
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        try:
            changed_paths = tuple(
                item.decode("utf-8") for item in names.stdout.split(b"\0") if item
            )
        except UnicodeDecodeError as exc:
            raise journal.CoordinationRefusal(
                builders.INGEST_PROOF_INVALID
            ) from exc
        if (
            parent_sha != intent["pre_head"]
            or commit_object.returncode != 0
            or parent_headers != [str(intent["pre_head"]).encode("ascii")]
            or sha256_bytes(commit_message) != intent["message_digest"]
            or diff.returncode != 0
            or names.returncode != 0
            or sha256_bytes(diff.stdout) != materialized["candidate"]["sha256"]
            or not changed_paths
            or not all(journal._valid_scope_item(path) for path in changed_paths)
        ):
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    # Proof 13: every native transition is monotonic in its original order.
    _require_ingest_proof("monotonic-transitions", completed_proofs)
    if any(
        not _commit_transition_valid_with_candidate_v2(
            builders, event, prior_state, event_state
        )
        for event, prior_state, event_state in events
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    # Proof 14: the landed commit is contained by the caller's proposed
    # closing HEAD.
    _require_ingest_proof("closing-head-containment", completed_proofs)
    closing_head = inputs.get("closing_head")
    if not isinstance(closing_head, str) or COMMIT_RE.fullmatch(closing_head) is None:
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    contained = subprocess.run(
        [
            "git",
            "-C",
            str(canonical_repository),
            "merge-base",
            "--is-ancestor",
            commit_sha,
            closing_head,
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if contained.returncode != 0:
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    # Proof 15: the explicit task belongs to this run and is still active.
    _require_ingest_proof("task-membership", completed_proofs)
    task = inputs.get("task")
    task_status = inputs.get("task_status")
    task_records = [
        record
        for record in proof_records
        if record.get("type") == "task" and record.get("id") == task
    ]
    if (
        not isinstance(task, str)
        or not task_records
        or task_records[-1].get("status") != "active"
        or task_status not in journal.TERMINAL_TASK_STATUSES
        or not isinstance(outcome_map, dict)
        or set(outcome_map)
        != {"schema", "chain_id", "task", "task_status", "event_digests"}
        or outcome_map.get("schema")
        != "forge-chain-ingest-outcome-map/1"
        or outcome_map.get("chain_id") != chain_id
        or outcome_map.get("task") != task
        or outcome_map.get("task_status") != task_status
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    if existing_records is not None:
        terminal_tasks = [
            record
            for record in existing_records
            if record.get("type") == "task" and record.get("id") == task
        ]
        if (
            len(terminal_tasks) != 1
            or terminal_tasks[0].get("status") != task_status
        ):
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    task_record = task_records[-1]

    # Proof 16: every landed path is admitted by both task and run scope.
    _require_ingest_proof("scope-membership", completed_proofs)
    files = task_record.get("files")
    if not isinstance(files, list) or not files:
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    try:
        mechanical_outputs = _committed_changelog_output_paths(parsed_policy)
    except PolicyError as exc:
        raise journal.CoordinationRefusal(
            builders.INGEST_PROOF_INVALID
        ) from exc
    for path in changed_paths:
        if path in mechanical_outputs:
            continue
        if (
            not any(
                journal.pathspec_contained(path, pattern)
                for pattern in files
                if isinstance(pattern, str)
            )
            or not any(
                journal.pathspec_contained(path, admitted)
                for admitted in run_state.scope
            )
        ):
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    assert isinstance(outcome_map, dict)
    if (
        not isinstance(outcome_map.get("event_digests"), list)
        or not all(
            isinstance(value, str) and SHA256_RE.fullmatch(value) is not None
            for value in outcome_map["event_digests"]
        )
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    binding = {
        "run_id": run_id,
        "task_id": task,
        "repository": str(canonical_repository),
        "policy_digest": policy_source["digest"],
    }
    selected: list[
        tuple[
            dict[str, object],
            dict[str, object] | None,
            dict[str, object],
        ]
    ] = []
    final_candidate = materialized["candidate"]["sha256"]
    for event, prior_state, event_state in events:
        payload = event["payload"]
        assert isinstance(payload, dict)
        details = payload["details"]
        assert isinstance(details, dict)
        event_name = payload.get("event")
        active = False
        if event_name == "step_recorded":
            active = _ingest_step_is_current(materialized, event_state, details)
        elif event_name == "secret_scan_recorded":
            active = _ingest_secret_scan_is_current(
                materialized, event, prior_state, event_state
            )
        elif event_name in {"review_passed", "review_blocked"}:
            active = bool(
                tier.get("effective") == "hard"
                and event_name == "review_passed"
                and event_state.get("review", {}).get("verdict")
                == materialized.get("review", {}).get("verdict")
            )
        elif event_name == "operator_approved":
            active = bool(approval_required and event_state.get("approval") == approval)
        elif event_name == "operator_skip":
            gate_id = details.get("gate_id")
            active = bool(
                isinstance(gate_id, str)
                and _user_skip(materialized, gate_id)
                == _user_skip(event_state, gate_id)
            )
        elif event_name == "commit_identity_checked":
            active = bool(
                event_state.get("commit_result", {}).get("identity")
                == materialized.get("commit_result", {}).get("identity")
                and details.get("result") == "passed"
            )
        elif event_name in {"commit_produced", "commit_close_recovered"}:
            active = details.get("commit_sha") == commit_sha
        if active and event_state.get("candidate", {}).get("sha256") == final_candidate:
            selected.append((event, prior_state, event_state))
    selected_digests = [
        str(event["digest"]) for event, _prior, _state in selected
    ]
    if selected_digests != outcome_map["event_digests"]:
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    projected = _ingest_allocation_records(
        canonical_repository, run_state
    )
    records: list[dict[str, object]] = []
    captured_citations = [
        captured_paths["state_file"],
        captured_paths["events_file"],
        captured_paths["outcome_map"],
    ]
    replay_entries = tuple(
        (
            event,
            prior_state,
            event_state,
            (),
            str(event["digest"]),
        )
        for event, prior_state, event_state in events
    )
    for event, prior_state, event_state in selected:
        payload = event["payload"]
        assert isinstance(payload, dict)
        details = payload["details"]
        assert isinstance(details, dict)
        event_name = str(payload["event"])
        bound_state = copy.deepcopy(event_state)
        bound_state["run_binding"] = copy.deepcopy(binding)
        generated = runtime._build_chain_journal_records(
            canonical_repository,
            bound_state,
            event_name,
            details,
            str(event["digest"]),
            retrospective_ingest=True,
        )
        for generated_record in generated:
            record = copy.deepcopy(generated_record)
            record_type = str(record["type"])
            record["id"] = builders._allocate_id(projected, record_type)
            record["run_id"] = run_id
            record["recorded_at"] = payload["at"]
            _capture_ingest_record_evidence(
                canonical_repository,
                run_dir,
                record,
            )
            if record.get("outcome") == "chain-landing":
                record["basis"] = list(captured_citations)
            record_binding = record.get("binding")
            if (
                not isinstance(record_binding, dict)
                or not _binding_matches_source_fact_with_candidate_v2(
                    builders,
                    journal,
                    record_binding,
                    record,
                    event,
                    prior_state,
                    event_state,
                    family="commit",
                )
                or not _binding_is_current_with_candidate_v2(
                    builders,
                    journal,
                    materialized,
                    record_binding,
                    record,
                    event,
                    prior_state,
                    event_state,
                    replay_entries,
                    chain_family="commit",
                )
            ):
                raise journal.CoordinationRefusal(
                    builders.INGEST_PROOF_INVALID
                )
            records.append(record)
            projected.append(record)
    if not any(record.get("outcome") == "chain-landing" for record in records):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    if approval_required and not any(
        record.get("outcome") == "chain-approval" for record in records
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    terminal = {
        "type": "task",
        "id": task,
        "status": task_status,
        "goal": task_record["goal"],
        "acceptance": copy.deepcopy(task_record["acceptance"]),
        "files": copy.deepcopy(task_record["files"]),
        "run_id": run_id,
        "recorded_at": events[-1][0]["payload"]["at"],
    }
    records.append(terminal)
    completed_records = tuple(records)
    if existing_records is not None:
        if completed_records != existing_records:
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
        completed_records = existing_records
    completed = tuple(completed_proofs)
    if completed != INGEST_PROOF_ORDER:
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    return completed_records, completed


def _ingest_proof_verifier(
    repository: Path, run_id: str, inputs: dict[str, object]
) -> tuple[Sequence[dict[str, object]], tuple[str, ...]]:
    return _verify_and_build_ingest_records(repository, run_id, inputs)


def register_activation_reservation_seam() -> None:
    """Install the grammar-aware first-use scanner without healing other seams."""

    batch, builders, _journal = runtime._coordination_modules()
    existing_scanner = builders._require_no_pending_activation_outbox
    original_scanner = getattr(
        builders, "_FORGE_CLI_ORIGINAL_ACTIVATION_SCANNER", None
    )
    if original_scanner is None:
        if (
            getattr(existing_scanner, "__name__", None)
            != "_require_no_pending_activation_outbox"
            or getattr(existing_scanner, "__module__", None)
            != builders.__name__
        ):
            raise RuntimeError("activation reservation scanner registration conflict")
        builders._FORGE_CLI_ORIGINAL_ACTIVATION_SCANNER = existing_scanner
        original_scanner = existing_scanner
    if existing_scanner is original_scanner:
        builders._require_no_pending_activation_outbox = (
            _require_no_pending_chain_activation_outbox
        )
    elif existing_scanner is not _require_no_pending_chain_activation_outbox:
        raise RuntimeError("activation reservation scanner registration conflict")


def register_coordination_seams() -> None:
    """Idempotently install task-04 authority in the shared task-03 modules."""

    batch, builders, _journal = runtime._coordination_modules()
    register_activation_reservation_seam()

    existing_reducer = builders.MERGE_TRANSITION_REDUCER
    if existing_reducer is None:
        builders.register_merge_transition_reducer(reduce_merge_event)
    elif not getattr(existing_reducer, "_forge_cli_revision9_seam", False):
        raise RuntimeError("merge transition reducer registration conflict")

    existing_verifier = builders._INGEST_PROOF_VERIFIER
    if existing_verifier is None:
        builders._register_ingest_proof_verifier(_ingest_proof_verifier)
    elif not getattr(existing_verifier, "_forge_cli_revision9_seam", False):
        raise RuntimeError("ingest proof verifier registration conflict")

    existing_authorizer = batch._CHAIN_BATCH_AUTHORIZER
    if existing_authorizer is None:
        if not hasattr(batch, "_FORGE_CLI_CHAIN_CAPABILITIES"):
            batch._FORGE_CLI_CHAIN_CAPABILITIES = {}
            batch._FORGE_CLI_CHAIN_CAPABILITIES_LOCK = threading.Lock()
        batch._register_chain_batch_authorizer(_authorize_chain_batch)
    elif not getattr(existing_authorizer, "_forge_cli_revision9_seam", False):
        raise RuntimeError("chain batch authorizer registration conflict")
    elif not hasattr(batch, "_FORGE_CLI_CHAIN_CAPABILITIES"):
        # A module-alias import may reach the shared registrar after another
        # alias installed the callback; the registry itself lives on task-03's
        # shared batch module so both aliases exchange the same capabilities.
        batch._FORGE_CLI_CHAIN_CAPABILITIES = {}
        batch._FORGE_CLI_CHAIN_CAPABILITIES_LOCK = threading.Lock()


# The Revision-9 seam marker rides on the callables themselves so the registrar above can
# tell an already-installed forge seam from a foreign registration (moved here from the
# shim in cli split phase 3; the shim no longer defines any seam callable).
for _seam in (
    reduce_merge_event,
    _authorize_chain_batch,
    _ingest_proof_verifier,
    _require_no_pending_chain_activation_outbox,
):
    setattr(_seam, "_forge_cli_revision9_seam", True)


def _coordination_refusal(exc: BaseException) -> Refusal | FrozenError:
    """Map task-03 diagnostics onto the closed Revision-9 CLI union."""

    batch, builders, journal = runtime._coordination_modules()
    message = str(exc)
    if message == journal.BATCH_PENDING:
        return Refusal(
            V2ReasonCode.BATCH_PENDING,
            message,
            remediation="run journal batch-recover for the named run",
        )
    if message == journal.BATCH_KEY_CONFLICT:
        return Refusal(
            V2ReasonCode.BATCH_IDEMPOTENCY_CONFLICT,
            message,
            remediation="reuse the exact original request or choose a new idempotency key",
        )
    if message == journal.BATCH_KEY_REFUSAL:
        return Refusal(
            V2ReasonCode.STATE_PRECONDITION,
            message,
            remediation="supply exactly one 64-lowercase-hex idempotency key",
        )
    if "cites path outside run or repository" in message:
        return Refusal(
            V2ReasonCode.CITATION_OUT_OF_ROOT,
            message,
            remediation="supply an owner-controlled repository-relative ingest input",
        )
    if message in {builders.INGEST_PROOF_INVALID, builders.TERMINAL_CHAIN_INVALID}:
        return Refusal(
            V2ReasonCode.INGEST_PROOF_INVALID
            if message == builders.INGEST_PROOF_INVALID
            else V2ReasonCode.BINDING_INVALID,
            message,
            remediation="repair the authoritative chain proof and retry",
        )
    if message == builders.JOURNAL_OUTBOX_PENDING:
        return Refusal(
            V2ReasonCode.JOURNAL_OUTBOX_PENDING,
            message,
            remediation="replay and drain the pending chain journal outbox",
        )
    if message == journal.BATCH_DIVERGED:
        return FrozenError(
            message,
            observed="journal transaction suffix or inode divergence",
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    if "binding" in message or message == journal.INVALID_JOURNAL_RECORD:
        return Refusal(
            V2ReasonCode.BINDING_INVALID,
            message,
            remediation="repair the structured chain binding and retry",
        )
    return Refusal(
        V2ReasonCode.INGEST_PROOF_INVALID,
        message,
        remediation="inspect the Revision-9 coordination proof and retry",
    )


def _validate_chain_batch_target(
    repository: Path,
    run_id: str,
) -> None:
    """Re-prove the existing run/repository/owner tuple without mutating it."""

    batch, _builders, journal = runtime._coordination_modules()
    validated_run_id = journal._operation_run_id("journal append", run_id)
    canonical_repository, state_root = journal._resolve_repository(
        repository, "journal append"
    )
    with journal._registry_lock(state_root) as registry_lock:
        view = journal._coordination_view(
            state_root,
            owner_target_ids=frozenset({validated_run_id}),
            locked=registry_lock,
        )
        state = journal._target_state(view, validated_run_id, "journal append")
        recorded_repository = journal._recorded_repository_root(
            state.run_dir, state_root, records=state.records
        )
        if recorded_repository != canonical_repository:
            raise journal.CoordinationRefusal(journal.REGISTRY_UNAVAILABLE)
        with journal._locked_journal(state) as locked:
            journal._classify_owner(
                state,
                batch._read_only_session_owner(),
                adopt_missing=state.pre_coordination,
                locked=locked,
            )


@contextlib.contextmanager
def _chain_batch_lock(
    run_dir: Path,
    repository: Path,
    run_id: str,
    *,
    create: bool,
    before_create: Callable[[], None] | None = None,
) -> Iterable[None]:
    """Conditionally create a mutation lock only around a validated run target."""

    register_coordination_seams()
    batch, _builders, journal = runtime._coordination_modules()
    create_missing = False
    if create:
        try:
            os.lstat(run_dir / journal.BATCH_LOCK_NAME)
        except FileNotFoundError:
            _validate_chain_batch_target(repository, run_id)
            if before_create is not None:
                before_create()
            create_missing = True
        except OSError:
            # Let the stable batch-lock implementation classify every unsafe
            # or unreadable existing topology with its established diagnostic.
            pass
    with batch.batch_lock(run_dir, create=create_missing):
        if create_missing:
            # Creation reserves only the stable outer lock. Every mutation
            # that admitted this missing target re-proves it under the required
            # batch -> registry -> journal order before any write is reached.
            _validate_chain_batch_target(repository, run_id)
        yield


def _drain_chain_batch_capability(
    state: Mapping[str, Any],
    pending_outbox: Mapping[str, Any],
    carried_records: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Drain one exact carrier through Revision-9's opaque authority path."""

    binding = state.get("run_binding")
    if not isinstance(binding, Mapping):
        raise FrozenError(
            "pending journal outbox lacks an immutable run binding",
            chain_id=str(state.get("chain_id") or "") or None,
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    batch, _builders, _journal = runtime._coordination_modules()
    capability = object()
    registry = batch._FORGE_CLI_CHAIN_CAPABILITIES
    registry_lock = batch._FORGE_CLI_CHAIN_CAPABILITIES_LOCK
    with registry_lock:
        registry[id(capability)] = (
            capability,
            {
                "repository": Path(str(binding["repository"])),
                "run_id": str(binding["run_id"]),
                "task_id": str(binding["task_id"]),
                "chain_id": str(state["chain_id"]),
                "run_binding": copy.deepcopy(dict(binding)),
                "pending_outbox": copy.deepcopy(dict(pending_outbox)),
                "source_event_digest": pending_outbox[
                    "source_event_digest"
                ],
                "records": tuple(copy.deepcopy(tuple(carried_records))),
            },
        )
    try:
        outcome = batch.drain_chain_batch(
            Path(str(binding["repository"])),
            str(binding["run_id"]),
            chain_id=str(state["chain_id"]),
            source_event_digest=str(pending_outbox["source_event_digest"]),
            records=carried_records,
            capability=capability,
        )
    finally:
        with registry_lock:
            registered = registry.get(id(capability))
            if isinstance(registered, tuple) and registered[0] is capability:
                registry.pop(id(capability), None)
    return batch.journal_receipted_details(dict(pending_outbox), outcome.receipt)


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


class ChainStore(_ChainStoragePrimitives):
    """Commit-family snapshot log over the shared storage primitives."""

    def _events(self, chain_id: str) -> list[dict[str, Any]]:
        with self.event_lock(chain_id):
            return self._events_unlocked(chain_id)

    def _events_unlocked(self, chain_id: str) -> list[dict[str, Any]]:
        path = self.events_path(chain_id)
        try:
            data = self._read_root_bytes(path.name)
        except FileNotFoundError as exc:
            raise FrozenError(
                "chain event log is missing",
                chain_id=chain_id,
                observed=str(path),
            ) from exc
        except OSError as exc:
            raise FrozenError(
                "chain event log is unreadable", chain_id=chain_id, observed=str(exc)
            ) from exc
        if not data or not data.endswith(b"\n"):
            raise FrozenError(
                "chain event log is empty or has a partial final record",
                chain_id=chain_id,
            )
        events: list[dict[str, Any]] = []
        previous = ZERO_DIGEST
        for sequence, line in enumerate(data.splitlines(keepends=True), 1):
            try:
                event = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise FrozenError(
                    f"chain event {sequence} is malformed", chain_id=chain_id
                ) from exc
            if not isinstance(event, dict) or set(event) != EVENT_KEYS:
                raise FrozenError(
                    f"chain event {sequence} has an invalid key set", chain_id=chain_id
                )
            if line != canonical_bytes(event) + b"\n":
                raise FrozenError(
                    f"chain event {sequence} is not canonical", chain_id=chain_id
                )
            if event["sequence"] != sequence or event["prev_digest"] != previous:
                raise FrozenError(
                    f"chain event {sequence} sequence/digest predecessor is invalid",
                    chain_id=chain_id,
                )
            unsigned = {
                "sequence": event["sequence"],
                "prev_digest": event["prev_digest"],
                "payload": event["payload"],
            }
            expected = sha256_bytes(canonical_bytes(unsigned))
            if event["digest"] != expected:
                raise FrozenError(
                    f"chain event {sequence} digest is invalid", chain_id=chain_id
                )
            payload = event["payload"]
            if not isinstance(payload, dict) or set(payload) != {
                "at",
                "details",
                "event",
                "state",
            }:
                raise FrozenError(
                    f"chain event {sequence} payload is malformed", chain_id=chain_id
                )
            validate_state(payload["state"], chain_id)
            previous = event["digest"]
            events.append(event)
        return events

    def load(
        self, chain_id: str, *, family_proven: bool = False
    ) -> dict[str, Any]:
        self._validate_id(chain_id)
        if not family_proven and self.chain_family(chain_id) != "commit":
            raise FrozenError(
                "commit store refused a merge-family chain",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        with self.event_lock(chain_id):
            return self._load_locked(chain_id)

    def _validate_bound_event_history(
        self,
        chain_id: str,
        events: Sequence[dict[str, Any]],
        binding: Mapping[str, Any],
    ) -> None:
        """Validate the nonrecursive batch/receipt algebra before repair.

        Materialized state is recoverable from an fsynced event, so the
        task-03 resolver cannot be called until after a missing/stale state
        projection is repaired.  This pre-repair pass applies its transition,
        source-projection, carried-record, pending-outbox, and durable receipt
        predicates to the event authority first.
        """

        register_coordination_seams()
        batch, builders, journal = runtime._coordination_modules()
        run_dir = (
            self.common_root
            / ".codex-orchestrator"
            / "runs"
            / str(binding.get("run_id"))
        )
        if batch._active_locks().get(os.path.abspath(os.fspath(run_dir))) is None:
            raise FrozenError(
                "bound chain replay lacks the outer journal lock",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        repository = Path(str(binding.get("repository")))
        replayed: dict[str, object] | None = None
        pending: dict[str, object] | None = None
        pending_records: tuple[dict[str, object], ...] = ()
        replay_entries: list[
            tuple[
                dict[str, object],
                dict[str, object] | None,
                dict[str, object],
                tuple[dict[str, object], ...],
                str | None,
            ]
        ] = []
        try:
            for event in events:
                payload = event.get("payload")
                if not isinstance(payload, dict):
                    raise ValueError("event payload is malformed")
                current = payload.get("state")
                if not isinstance(current, dict) or not _commit_transition_valid_with_candidate_v2(
                    builders, event, replayed, current
                ):
                    raise ValueError("commit transition is invalid")
                records, event_outbox, source_digest = _event_batch_records_with_candidate_v2(
                    builders, journal, event, "commit"
                )
                event_name = payload.get("event")
                is_receipt = event_name == "journal_receipted"
                if pending is not None and not is_receipt:
                    raise ValueError("pending outbox was bypassed")
                if pending is None and is_receipt:
                    raise ValueError("receipt has no pending outbox")
                if is_receipt:
                    acknowledgement = builders._receipt_metadata(event, "commit")
                    if (
                        acknowledgement is None
                        or records
                        or event_outbox is not None
                        or source_digest is not None
                        or acknowledgement.get("idempotency_key")
                        != pending.get("idempotency_key")
                        or acknowledgement.get("batch_digest")
                        != pending.get("batch_digest")
                        or replayed is None
                    ):
                        raise ValueError("receipt transition is invalid")
                    builders._verify_receipted_batch(
                        repository,
                        chain_id,
                        replayed,
                        pending,
                        pending_records,
                        acknowledgement,
                    )
                    if current.get("journal_outbox") is not None:
                        raise ValueError("receipt did not clear outbox")
                    pending = None
                    pending_records = ()
                elif event_outbox is not None:
                    if pending is not None or current.get("journal_outbox") != event_outbox:
                        raise ValueError("event outbox projection is invalid")
                    pending = event_outbox
                    pending_records = records
                elif current.get("journal_outbox") != pending:
                    raise ValueError("event changed the pending outbox")
                activation_preamble = (
                    records[:1]
                    if records
                    and journal._writer_activation_candidate(records[0])
                    else ()
                )
                for record in records[len(activation_preamble) :]:
                    record_binding = record.get("binding")
                    if (
                        not isinstance(record_binding, dict)
                        or not _binding_matches_source_fact_with_candidate_v2(
                            builders,
                            journal,
                            record_binding,
                            record,
                            event,
                            replayed,
                            current,
                            family="commit",
                        )
                    ):
                        raise ValueError("carried binding fact is invalid")
                replay_entries.append(
                    (
                        copy.deepcopy(event),
                        copy.deepcopy(replayed),
                        copy.deepcopy(current),
                        tuple(copy.deepcopy(records)),
                        source_digest,
                    )
                )
                replayed = copy.deepcopy(current)
            if replayed is None:
                raise ValueError("bound chain replay is empty")
            frozen_entries = tuple(replay_entries)
            latest_record_index = next(
                (
                    index
                    for index in range(len(frozen_entries) - 1, -1, -1)
                    if frozen_entries[index][3]
                ),
                None,
            )
            for index, (
                event,
                prior,
                current,
                records,
                _source_digest,
            ) in enumerate(frozen_entries):
                # Receipted records are authenticated historical facts.  Only
                # the newest appended set can still be live authority, and it
                # is checked against the exact state/prefix at its append.
                if index != latest_record_index:
                    continue
                appended_history = frozen_entries[: index + 1]
                activation_preamble = (
                    records[:1]
                    if records
                    and journal._writer_activation_candidate(records[0])
                    else ()
                )
                for record in records[len(activation_preamble) :]:
                    record_binding = record.get("binding")
                    current_fact = bool(
                        isinstance(record_binding, dict)
                        and _binding_is_current_with_candidate_v2(
                            builders,
                            journal,
                            current,
                            record_binding,
                            record,
                            event,
                            prior,
                            current,
                            appended_history,
                            chain_family="commit",
                        )
                    )
                    # A receipted v2 landing remains current in the narrow
                    # committing crash window only after the durable produced
                    # identity PASS that authorized the landing projection.
                    if not current_fact and isinstance(record_binding, dict):
                        final_result = current.get("commit_result")
                        final_candidate = current.get("candidate")
                        source_payload = event.get("payload")
                        source_details = (
                            source_payload.get("details")
                            if isinstance(source_payload, dict)
                            else None
                        )
                        bound_candidate = record_binding.get("candidate")
                        legacy_binding = bool(
                            isinstance(bound_candidate, dict)
                            and bound_candidate.get("kind")
                            == "staged-diff-sha256"
                            and bound_candidate.get("value")
                            == final_candidate.get("sha256")
                        )
                        v2_value = (
                            bound_candidate.get("value")
                            if isinstance(bound_candidate, dict)
                            and bound_candidate.get("kind")
                            == "git-tree-candidate-v2"
                            else None
                        )
                        identity = (
                            final_result.get("identity")
                            if isinstance(final_result, dict)
                            else None
                        )
                        v2_binding = bool(
                            candidate_is_v2(current)
                            and isinstance(v2_value, dict)
                            and v2_value
                            == {
                                "authorization_id": final_candidate.get(
                                    "authorization_id"
                                ),
                                "object_format": final_candidate.get("object_format"),
                                "tree_oid": final_candidate.get("tree_oid"),
                            }
                            and isinstance(identity, dict)
                            and identity.get("result") == "passed"
                            and identity.get("produced_sha")
                            == final_result.get("commit_sha")
                        )
                        current_fact = bool(
                            record.get("outcome") == "chain-landing"
                            and current.get("state") == "committing"
                            and isinstance(final_result, dict)
                            and isinstance(final_candidate, dict)
                            and isinstance(source_payload, dict)
                            and source_payload.get("event") == "commit_produced"
                            and isinstance(source_details, dict)
                            and (legacy_binding or v2_binding)
                            and isinstance(final_result.get("intent"), dict)
                            and final_result["intent"].get("candidate")
                            == final_candidate.get("sha256")
                            and source_details.get("commit_sha")
                            == final_result.get("commit_sha")
                        )
                    if (
                        not isinstance(record_binding, dict)
                        or not current_fact
                    ):
                        raise ValueError("carried binding fact is stale")
        except (KeyError, TypeError, ValueError, RuntimeError, journal.CoordinationRefusal) as exc:
            raise FrozenError(
                "bound chain event replay failed",
                chain_id=chain_id,
                observed=str(exc),
                schema=REVISION9_OUTPUT_SCHEMA,
            ) from exc

    def _load_locked(self, chain_id: str) -> dict[str, Any]:
        events = self._events_unlocked(chain_id)
        replayed = copy.deepcopy(events[-1]["payload"]["state"])
        binding = replayed.get("run_binding")
        if isinstance(binding, Mapping):
            self._validate_bound_event_history(chain_id, events, binding)
        path = self.state_path(chain_id)
        materialized: dict[str, Any] | None = None
        try:
            raw = self._read_root_bytes(path.name)
            loaded = json.loads(raw)
            materialized = validate_state(loaded, chain_id)
        except FileNotFoundError:
            materialized = None
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, FrozenError):
            materialized = None
        if materialized is None or canonical_bytes(materialized) != canonical_bytes(replayed):
            # Event-first persistence makes the last valid event authoritative.
            # A materialized committing snapshot is never replaced by an older
            # event; that ordering would be impossible without external writes.
            if materialized and materialized.get("state") == "committing" and replayed.get(
                "state"
            ) != "committing":
                raise FrozenError(
                    "materialized committing state is ahead of its event log",
                    chain_id=chain_id,
                    state="committing",
                )
            self._atomic_state(replayed)
        if isinstance(binding, Mapping):
            _batch, builders, journal = runtime._coordination_modules()
            try:
                with self.root_descriptor() as root:
                    root_observation = journal._file_observation(os.fstat(root))
                    authoritative = builders._resolve_binding_from_descriptor(
                        Path(str(binding["repository"])),
                        root,
                        chain_id,
                        ZERO_DIGEST,
                        expected_type=None,
                        expected_fields=None,
                        expected_run_id=None,
                        expected_task_id=None,
                        replay_only=True,
                        allow_pending=True,
                    )
                    if (
                        authoritative != replayed
                        or journal._file_observation(os.fstat(root))
                        != root_observation
                    ):
                        raise ValueError("authoritative replay changed")
            except (KeyError, OSError, TypeError, ValueError, RuntimeError, journal.CoordinationRefusal) as exc:
                raise FrozenError(
                    "bound chain authority replay failed",
                    chain_id=chain_id,
                    observed=str(exc),
                    schema=REVISION9_OUTPUT_SCHEMA,
                ) from exc
        self._remember_version(
            replayed,
            int(events[-1]["sequence"]),
            str(events[-1]["digest"]),
        )
        return replayed

    def create(self, state: dict[str, Any], event: str, details: Mapping[str, Any]) -> None:
        self.ensure_root()
        chain_id = str(state["chain_id"])
        if self._root_entry_exists(self.state_path(chain_id).name) or self._root_entry_exists(
            self.events_path(chain_id).name
        ):
            raise FrozenError("generated chain identity already exists", chain_id=chain_id)
        self.persist(state, event, details, initial=True)

    def persist(
        self,
        state: dict[str, Any],
        event: str,
        details: Mapping[str, Any],
        *,
        initial: bool = False,
        touch: bool = True,
        _journal_locked: bool = False,
    ) -> None:
        validate_state(state, str(state.get("chain_id")))
        self.ensure_root()
        chain_id = str(state["chain_id"])
        binding = state.get("run_binding")
        if isinstance(binding, Mapping) and not _journal_locked:
            register_coordination_seams()
            batch, _builders, journal = runtime._coordination_modules()
            run_dir = (
                self.common_root
                / ".codex-orchestrator"
                / "runs"
                / str(binding["run_id"])
            )
            try:
                with _chain_batch_lock(
                    run_dir,
                    Path(str(binding["repository"])),
                    str(binding["run_id"]),
                    create=True,
                ):
                    self.persist(
                        state,
                        event,
                        details,
                        initial=initial,
                        touch=touch,
                        _journal_locked=True,
                    )
                return
            except journal.CoordinationRefusal as exc:
                raise _coordination_refusal(exc) from exc
        if isinstance(binding, Mapping):
            _validate_bound_chain_state(state)
        if state.get("journal_outbox") is not None and event != "journal_receipted":
            raise Refusal(
                V2ReasonCode.JOURNAL_OUTBOX_PENDING,
                "forge: chain transition refused — journal outbox is pending",
                expected="a receipted null journal_outbox",
                observed=str(state.get("journal_outbox")),
                remediation=_forge_command(state, "status"),
                chain=state,
            )
        carried_records: tuple[dict[str, Any], ...] = ()
        pending_outbox: dict[str, Any] | None = None
        with self.event_lock(chain_id):
            existing: list[dict[str, Any]] = []
            if not initial:
                existing = self._events_unlocked(chain_id)
                self._require_tail_version(
                    state,
                    int(existing[-1]["sequence"]),
                    str(existing[-1]["digest"]),
                    family="commit",
                    refusal_chain=existing[-1]["payload"]["state"],
                )
            elif self._root_entry_exists(self.events_path(chain_id).name):
                raise FrozenError("initial event log already exists", chain_id=chain_id)
            when = runtime.utc_now()
            if touch:
                state["last_event_at"] = iso_z(when)
                state["inactive_after"] = iso_z(
                    when + dt.timedelta(seconds=INACTIVE_SECONDS)
                )
            validate_state(state, chain_id)
            sequence = len(existing) + 1
            previous = existing[-1]["digest"] if existing else ZERO_DIGEST
            payload = {
                "at": iso_z(when),
                "details": dict(details),
                "event": event,
                "state": copy.deepcopy(state),
            }
            unsigned = {
                "sequence": sequence,
                "prev_digest": previous,
                "payload": payload,
            }
            if isinstance(binding, Mapping) and event != "journal_receipted":
                source_event_digest = sha256_bytes(canonical_bytes(unsigned))
                carried_records = runtime._build_chain_journal_records(
                    Path(str(binding["repository"])),
                    state,
                    event,
                    details,
                    source_event_digest,
                )
                if carried_records:
                    _batch, _builders, journal = runtime._coordination_modules()
                    batch_bytes = b"".join(
                        journal._journal_line(record)
                        for record in carried_records
                    )
                    batch_digest = sha256_bytes(batch_bytes)
                    pending_outbox = {
                        "idempotency_key": source_event_digest,
                        "batch_digest": batch_digest,
                        "record_count": len(carried_records),
                        "source_event_digest": source_event_digest,
                    }
                    prospective_state = copy.deepcopy(state)
                    prospective_state["journal_outbox"] = copy.deepcopy(
                        pending_outbox
                    )
                    payload["state"] = prospective_state
                    payload["details"] = {
                        **dict(details),
                        "source_event_digest": source_event_digest,
                        "journal_batch": {
                            "idempotency_key": source_event_digest,
                            "batch_digest": batch_digest,
                            "record_count": len(carried_records),
                            "records": copy.deepcopy(list(carried_records)),
                        },
                    }
                    unsigned["payload"] = payload
            record = {**unsigned, "digest": sha256_bytes(canonical_bytes(unsigned))}
            if pending_outbox is not None:
                assert isinstance(binding, Mapping)
                prospective_events = (*existing, record)
                self._validate_bound_event_history(
                    chain_id, prospective_events, binding
                )
                prospective_state = record["payload"]["state"]
                assert isinstance(prospective_state, Mapping)
                _prevalidate_chain_batch_carrier(
                    prospective_state,
                    pending_outbox,
                    carried_records,
                )
                state["journal_outbox"] = copy.deepcopy(pending_outbox)
            encoded = canonical_bytes(record) + b"\n"
            self._append_event_bytes(chain_id, encoded, initial=initial)
            self._atomic_state(state)
            self._remember_version(state, sequence, str(record["digest"]))
        if pending_outbox is not None:
            self._drain_pending_batch(
                state,
                pending_outbox,
                carried_records,
                journal_locked=True,
            )

    def _drain_pending_batch(
        self,
        state: dict[str, Any],
        pending_outbox: Mapping[str, Any],
        carried_records: Sequence[dict[str, Any]],
        *,
        journal_locked: bool,
    ) -> None:
        binding = state.get("run_binding")
        if not isinstance(binding, Mapping):
            raise FrozenError(
                "pending journal outbox lacks an immutable run binding",
                chain_id=str(state.get("chain_id") or "") or None,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        if not journal_locked:
            register_coordination_seams()
            batch, _builders, journal = runtime._coordination_modules()
            run_dir = (
                self.common_root
                / ".codex-orchestrator"
                / "runs"
                / str(binding["run_id"])
            )
            try:
                with _chain_batch_lock(
                    run_dir,
                    Path(str(binding["repository"])),
                    str(binding["run_id"]),
                    create=True,
                ):
                    self._drain_pending_batch(
                        state,
                        pending_outbox,
                        carried_records,
                        journal_locked=True,
                    )
                return
            except journal.CoordinationRefusal as exc:
                raise _coordination_refusal(exc) from exc

        receipt_details = _drain_chain_batch_capability(
            state,
            pending_outbox,
            carried_records,
        )
        if state.get("journal_outbox") != pending_outbox:
            raise FrozenError(
                "pending journal outbox identity changed before acknowledgement",
                chain_id=str(state["chain_id"]),
                state=str(state.get("state")),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        state["journal_outbox"] = None
        self.persist(
            state,
            "journal_receipted",
            receipt_details,
            _journal_locked=True,
        )

    def recover_pending_outbox(self, state: dict[str, Any]) -> dict[str, Any]:
        """Replay and receipt the exact last unacknowledged carried batch."""

        pending = state.get("journal_outbox")
        if pending is None:
            return state
        binding = state.get("run_binding")
        if not isinstance(binding, Mapping) or not isinstance(pending, dict):
            raise FrozenError(
                "pending journal outbox is not recoverable",
                chain_id=str(state.get("chain_id") or "") or None,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        register_coordination_seams()
        batch, _builders, journal = runtime._coordination_modules()
        run_dir = (
            self.common_root
            / ".codex-orchestrator"
            / "runs"
            / str(binding["run_id"])
        )
        try:
            with _chain_batch_lock(
                run_dir,
                Path(str(binding["repository"])),
                str(binding["run_id"]),
                create=True,
            ):
                with self.event_lock(str(state["chain_id"])):
                    fresh = self._load_locked(str(state["chain_id"]))
                    current_pending = fresh.get("journal_outbox")
                    if current_pending is None:
                        return fresh
                    if current_pending != pending:
                        raise FrozenError(
                            "pending journal outbox changed during replay",
                            chain_id=str(state["chain_id"]),
                            schema=REVISION9_OUTPUT_SCHEMA,
                        )
                    events = self._events_unlocked(str(state["chain_id"]))
                    carrier = events[-1]["payload"].get("details")
                    carried = (
                        carrier.get("journal_batch")
                        if isinstance(carrier, dict)
                        else None
                    )
                    if (
                        not isinstance(carried, dict)
                        or set(carried)
                        != {
                            "idempotency_key",
                            "batch_digest",
                            "record_count",
                            "records",
                        }
                        or carried.get("idempotency_key")
                        != current_pending.get("idempotency_key")
                        or carried.get("batch_digest")
                        != current_pending.get("batch_digest")
                        or carried.get("record_count")
                        != current_pending.get("record_count")
                        or not isinstance(carried.get("records"), list)
                    ):
                        raise FrozenError(
                            "pending journal outbox lacks its exact carried batch",
                            chain_id=str(state["chain_id"]),
                            schema=REVISION9_OUTPUT_SCHEMA,
                        )
                    records = tuple(copy.deepcopy(carried["records"]))
                self._drain_pending_batch(
                    fresh,
                    current_pending,
                    records,
                    journal_locked=True,
                )
                return fresh
        except journal.CoordinationRefusal as exc:
            raise _coordination_refusal(exc) from exc


def _build_merge_chain_journal_records(
    repository: Path,
    event: dict[str, Any],
    prior: dict[str, Any] | None,
    current: dict[str, Any],
    source_event_digest: str,
) -> tuple[dict[str, Any], ...]:
    """Build live merge rows through the retrospective ingest templates."""

    binding = current.get("run_binding")
    if not isinstance(binding, Mapping):
        return ()
    _require_merge_store_control("typed-journal-builders")
    _require_merge_store_control("consequential-event-set")
    if MERGE_CONSEQUENTIAL_EVENTS != {
        "gate_recorded",
        "review_attached",
        "approval_recorded",
        "generation_carried_forward",
        "push_observed",
    }:
        raise FrozenError(
            "merge consequential event authority is unavailable",
            chain_id=str(current.get("chain_id") or "") or None,
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    run_id = str(binding["run_id"])
    task_id = str(binding["task_id"])
    batch, builders, journal = runtime._coordination_modules()
    _canonical_repository, state_root = journal._resolve_repository(
        repository, "journal batch"
    )
    run_dir = state_root / ".codex-orchestrator" / "runs" / run_id
    run_state = journal._scan_run(run_dir)
    task_records = [
        record
        for record in run_state.records
        if record.get("type") == "task" and record.get("id") == task_id
    ]
    if not task_records or task_records[-1].get("status") != "active":
        raise journal.CoordinationRefusal(journal.INVALID_JOURNAL_RECORD)

    introduced = _merge_gate_event_fact(prior, current)
    if (
        introduced is not None
        and isinstance(introduced[1], Mapping)
        and isinstance(introduced[1].get("gate_plan_position"), Mapping)
        and introduced[1]["gate_plan_position"].get("kind") == "scoped-mutation"
    ):
        return ()
    required_gate_ids = frozenset(
        {introduced[0]} if introduced is not None else set()
    )
    templates = _merge_ingest_record_templates(
        builders,
        journal,
        event,
        prior,
        current,
        task=task_id,
        approval_required=bool(
            isinstance(current.get("tier"), Mapping)
            and current["tier"].get("control") is True
        ),
        required_gate_ids=required_gate_ids,
    )
    if templates and event.get("event") not in MERGE_CONSEQUENTIAL_EVENTS:
        raise FrozenError(
            "non-consequential merge event attempted to carry journal records",
            chain_id=str(current.get("chain_id") or "") or None,
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    if not templates:
        return ()
    activation_preamble = (
        ()
        if journal._writer_contract_active(run_state.records)
        else _prepare_merge_activation_preamble(
            _canonical_repository, run_state
        )
    )
    projected = [*run_state.records, *activation_preamble]
    records: list[dict[str, Any]] = []
    review_binding = builders._review_binding_for_state(current)
    for template, _gate_id in templates:
        record = copy.deepcopy(template)
        record_type = str(record["type"])
        record["id"] = builders._allocate_id(projected, record_type)
        record["run_id"] = run_id
        record["recorded_at"] = event["at"]
        record["binding"] = _merge_ingest_binding(
            builders,
            current,
            source_event_digest,
            (
                review_binding
                if record.get("criterion") == journal.GATE_3_CRITERION
                else None
            ),
        )
        evidence = record.get("evidence")
        if isinstance(evidence, list):
            for citation in evidence:
                if (
                    not isinstance(citation, str)
                    or _parsed_run_captured_path(citation, run_id) is None
                ):
                    raise journal.CoordinationRefusal(
                        journal.INVALID_JOURNAL_RECORD
                    )
        records.append(record)
        projected.append(record)
    carried_records = (*activation_preamble, *records)
    batch._prevalidate_records(
        _canonical_repository,
        run_state,
        carried_records,
        close=False,
        defer_binding=True,
    )
    return carried_records


def _new_merge_record_is_current(
    builders: Any,
    state: dict[str, Any],
    binding: dict[str, Any],
    record: dict[str, Any],
    source_event: dict[str, Any],
    source_prior: dict[str, Any] | None,
    source_state: dict[str, Any],
    replay_entries: Sequence[
        tuple[
            dict[str, Any],
            dict[str, Any] | None,
            dict[str, Any],
            tuple[dict[str, Any], ...],
            str | None,
        ]
    ],
) -> bool:
    """Apply currentness only to the newly proposed carried merge fact."""

    if builders._binding_is_current(
        state,
        binding,
        record,
        source_event,
        source_prior,
        source_state,
        replay_entries,
        chain_family="merge",
    ):
        return True
    return bool(
        record.get("type") == "decision"
        and record.get("outcome") == "chain-landing"
        and state.get("state") == "pushed"
        and builders._merge_current_head_contained(state)
        and builders._binding_matches_source_fact(
            binding,
            record,
            source_event,
            source_prior,
            source_state,
            family="merge",
        )
    )


class MergeChainStore(_ChainStoragePrimitives):
    """DM-014 delta log with lease-owned event-first materialization."""

    _TRANSITION_CONTROLS = (
        "lease-tail-authentication",
        "nonrecursive-source-digest",
        "typed-journal-builders",
        "projected-journal-outbox",
        "builder-transition-validation",
        "event-before-state",
        "post-serialization-journal-drain",
    )

    @staticmethod
    def _session(value: str | None) -> str:
        selected = (
            value
            or os.environ.get("CLAUDE_SESSION_ID")
            or os.environ.get("FORGE_SESSION_PID")
            or f"forge-merge-store-{os.getpid()}"
        )
        if not selected or "\x00" in selected:
            raise ValueError("merge store session must be nonempty and NUL-free")
        return selected

    @contextlib.contextmanager
    def _journal_outer(
        self, binding: Mapping[str, Any] | None, *, create: bool = True
    ) -> Iterable[None]:
        if not isinstance(binding, Mapping):
            yield
            return
        register_coordination_seams()
        batch, _builders, journal = runtime._coordination_modules()
        run_dir = (
            self.common_root
            / ".codex-orchestrator"
            / "runs"
            / str(binding["run_id"])
        )
        try:
            with _chain_batch_lock(
                run_dir,
                Path(str(binding["repository"])),
                str(binding["run_id"]),
                create=create,
            ):
                yield
        except journal.CoordinationRefusal as exc:
            raise _coordination_refusal(exc) from exc

    def _read_replay_locked(
        self, chain_id: str, *, verify_receipts: bool = True
    ) -> MergeReplayResult:
        try:
            raw = self._read_root_bytes(self.events_path(chain_id).name)
        except FileNotFoundError as exc:
            raise FrozenError(
                "merge event log is missing",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            ) from exc
        except OSError as exc:
            raise FrozenError(
                "merge event log is unreadable",
                chain_id=chain_id,
                observed=str(exc),
                schema=REVISION9_OUTPUT_SCHEMA,
            ) from exc
        return _replay_merge_event_bytes(
            chain_id, raw, verify_receipts=verify_receipts
        )

    def _projection_status(
        self, replay: MergeReplayResult
    ) -> tuple[str, bytes | None]:
        state_name = self.state_path(str(replay.state["chain_id"])).name
        try:
            raw = self._read_root_bytes(state_name)
        except FileNotFoundError:
            return "missing", None
        except OSError as exc:
            raise FrozenError(
                "merge materialized state is unreadable",
                chain_id=str(replay.state["chain_id"]),
                observed=str(exc),
                schema=REVISION9_OUTPUT_SCHEMA,
            ) from exc
        final = canonical_bytes(replay.state) + b"\n"
        if raw == final:
            return "current", raw
        if raw in replay.prefix_state_bytes[:-1]:
            return "stale", raw
        raise FrozenError(
            "merge materialized state contradicts authenticated event replay",
            chain_id=str(replay.state["chain_id"]),
            observed=sha256_bytes(raw),
            schema=REVISION9_OUTPUT_SCHEMA,
        )

    def _resolve_replayed_projection(
        self, replay: MergeReplayResult
    ) -> dict[str, Any]:
        binding = replay.state.get("run_binding")
        if _merge_history_uses_additive_grammar(replay.events):
            if isinstance(binding, Mapping):
                try:
                    snapshot = _prove_merge_run_task_binding(
                        Path(str(binding["repository"])),
                        self.common_root,
                        str(binding["run_id"]),
                        str(binding["task_id"]),
                        str(binding["policy_digest"]),
                    )
                except (KeyError, OSError, Refusal, ValueError) as exc:
                    raise FrozenError(
                        "merge binding authority replay failed",
                        chain_id=str(replay.state["chain_id"]),
                        observed=str(exc),
                        schema=REVISION9_OUTPUT_SCHEMA,
                    ) from exc
                if snapshot.binding != dict(binding):
                    raise FrozenError(
                        "merge binding authority replay changed",
                        chain_id=str(replay.state["chain_id"]),
                        schema=REVISION9_OUTPUT_SCHEMA,
                    )
            return copy.deepcopy(replay.state)
        register_coordination_seams()
        _batch, builders, journal = runtime._coordination_modules()
        try:
            with self.root_descriptor() as root:
                root_observation = journal._file_observation(os.fstat(root))
                authoritative = builders._resolve_binding_from_descriptor(
                    Path(
                        str(
                            binding["repository"]
                            if isinstance(binding, Mapping)
                            else replay.state["repository"]
                        )
                    ),
                    root,
                    str(replay.state["chain_id"]),
                    ZERO_DIGEST,
                    expected_type=None,
                    expected_fields=None,
                    expected_run_id=None,
                    expected_task_id=None,
                    replay_only=True,
                    allow_pending=True,
                )
                if (
                    authoritative != replay.state
                    or journal._file_observation(os.fstat(root))
                    != root_observation
                ):
                    raise ValueError("authoritative merge replay changed")
        except (
            KeyError,
            OSError,
            TypeError,
            ValueError,
            RuntimeError,
            journal.CoordinationRefusal,
        ) as exc:
            raise FrozenError(
                "merge binding authority replay failed",
                chain_id=str(replay.state["chain_id"]),
                observed=str(exc),
                schema=REVISION9_OUTPUT_SCHEMA,
            ) from exc
        return copy.deepcopy(replay.state)

    def _load_with_outer(
        self, chain_id: str, *, session: str | None
    ) -> dict[str, Any]:
        with self.event_lock(chain_id):
            replay = self._read_replay_locked(chain_id)
            projection_status, _raw = self._projection_status(replay)
        if projection_status != "current":
            _require_merge_store_control("replay-projection-repair")
            lease = acquire_chain_lease(
                self.root,
                chain_id=chain_id,
                session=self._session(session),
            )
            try:
                with self.event_lock(chain_id):
                    replay = self._read_replay_locked(chain_id)
                    projection_status, _raw = self._projection_status(replay)
                    if projection_status != "current":
                        lease.before_state_replace()
                        self._atomic_state(replay.state)
                        self._boundary("merge-replay-state-replaced")
            finally:
                lease.release()
        with self.event_lock(chain_id):
            replay = self._read_replay_locked(chain_id)
            if self._projection_status(replay)[0] != "current":
                raise FrozenError(
                    "merge projection did not stabilize after replay repair",
                    chain_id=chain_id,
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            state = self._resolve_replayed_projection(replay)
            self._remember_version(
                state, replay.tail_sequence, replay.tail_digest
            )
            return state

    def load(
        self, chain_id: str, *, session: str | None = None
    ) -> dict[str, Any]:
        self._validate_id(chain_id)
        if self.chain_family(chain_id) != "merge":
            raise FrozenError(
                "merge store refused a commit-family chain",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        with self.event_lock(chain_id):
            preliminary = self._read_replay_locked(
                chain_id, verify_receipts=False
            )
        binding = preliminary.state.get("run_binding")
        with self._journal_outer(
            binding if isinstance(binding, Mapping) else None,
            create=False,
        ):
            return self._load_with_outer(chain_id, session=session)

    def _prepare_event(
        self,
        replay: MergeReplayResult | None,
        *,
        chain_id: str,
        event_name: str,
        generation_digest: str | None,
        payload: Mapping[str, Any],
        at: str,
    ) -> tuple[
        dict[str, Any],
        dict[str, Any],
        tuple[dict[str, Any], ...],
        dict[str, Any] | None,
    ]:
        _require_merge_store_control("nonrecursive-source-digest")
        if event_name not in MERGE_EVENT_NAMES or event_name == "journal_receipted":
            raise ValueError("public merge transition event is invalid")
        if "source_event_digest" in payload or "journal_batch" in payload:
            raise ValueError("merge journal carrier members are store-owned")
        previous_state = replay.state if replay is not None else None
        sequence = replay.tail_sequence + 1 if replay is not None else 1
        previous_digest = replay.tail_digest if replay is not None else ZERO_DIGEST
        unsigned_source: dict[str, Any] = {
            "schema": "forge-merge-event/1",
            "chain_id": chain_id,
            "sequence": sequence,
            "at": at,
            "event": event_name,
            "generation_digest": generation_digest,
            "previous_digest": previous_digest,
            "payload": copy.deepcopy(dict(payload)),
        }
        source_event_digest = sha256_bytes(canonical_bytes(unsigned_source))
        provisional_event = {
            **copy.deepcopy(unsigned_source),
            "digest": source_event_digest,
        }
        try:
            provisional_state = reduce_merge_event(
                copy.deepcopy(previous_state), copy.deepcopy(provisional_event)
            )
        except (KeyError, TypeError, ValueError, RuntimeError) as exc:
            raise FrozenError(
                "proposed merge delta cannot be reduced",
                chain_id=chain_id,
                observed=str(exc),
                schema=REVISION9_OUTPUT_SCHEMA,
            ) from exc
        records = _build_merge_chain_journal_records(
            Path(str(provisional_state.get("repository"))),
            provisional_event,
            copy.deepcopy(previous_state),
            provisional_state,
            source_event_digest,
        )
        final_payload = copy.deepcopy(dict(payload))
        pending_outbox: dict[str, Any] | None = None
        if records:
            _require_merge_store_control("projected-journal-outbox")
            _batch, _builders, journal = runtime._coordination_modules()
            batch_bytes = b"".join(journal._journal_line(record) for record in records)
            batch_digest = sha256_bytes(batch_bytes)
            final_payload.update(
                {
                    "source_event_digest": source_event_digest,
                    "journal_batch": {
                        "idempotency_key": source_event_digest,
                        "batch_digest": batch_digest,
                        "record_count": len(records),
                        "records": copy.deepcopy(list(records)),
                    },
                }
            )
            pending_outbox = {
                "idempotency_key": source_event_digest,
                "batch_digest": batch_digest,
                "record_count": len(records),
                "source_event_digest": source_event_digest,
            }
        unsigned_outer = {**unsigned_source, "payload": final_payload}
        event = {
            **unsigned_outer,
            "digest": sha256_bytes(canonical_bytes(unsigned_outer)),
        }
        try:
            current = reduce_merge_event(
                copy.deepcopy(previous_state), copy.deepcopy(event)
            )
        except (KeyError, TypeError, ValueError, RuntimeError) as exc:
            raise FrozenError(
                "proposed merge carrier cannot be reduced",
                chain_id=chain_id,
                observed=str(exc),
                schema=REVISION9_OUTPUT_SCHEMA,
            ) from exc
        _require_merge_store_control("builder-transition-validation")
        _batch, builders, _journal = runtime._coordination_modules()
        validation_context = (
            copy.deepcopy(replay.context) if replay is not None else {}
        )
        if not _merge_state_shape_valid(builders, current, chain_id) or not (
            _merge_transition_valid(
                builders,
                event,
                copy.deepcopy(previous_state),
                current,
                context=validation_context,
                history=(replay.events if replay is not None else ()),
            )
        ):
            raise FrozenError(
                "proposed merge transition is not admitted by DM-014",
                chain_id=chain_id,
                state=str(current.get("state")),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        if bool(records) != bool(pending_outbox):
            raise FrozenError(
                "merge journal outbox projection is inconsistent",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        if records:
            replay_entries = tuple(replay.entries if replay is not None else ()) + (
                (
                    copy.deepcopy(event),
                    copy.deepcopy(previous_state),
                    copy.deepcopy(current),
                    tuple(copy.deepcopy(records)),
                    source_event_digest,
                ),
            )
            activation_preamble = (
                records[:1]
                if records
                and _journal._writer_activation_candidate(records[0])
                else ()
            )
            for record in records[len(activation_preamble) :]:
                record_binding = record.get("binding")
                if (
                    not isinstance(record_binding, dict)
                    or not builders._binding_matches_source_fact(
                        record_binding,
                        record,
                        event,
                        copy.deepcopy(previous_state),
                        current,
                        family="merge",
                    )
                    or not _new_merge_record_is_current(
                        builders,
                        current,
                        record_binding,
                        record,
                        event,
                        copy.deepcopy(previous_state),
                        current,
                        replay_entries,
                    )
                ):
                    raise FrozenError(
                        "new merge journal binding is not current",
                        chain_id=chain_id,
                        schema=REVISION9_OUTPUT_SCHEMA,
                    )
        return event, current, records, pending_outbox

    def _write_transition_with_outer(
        self,
        snapshot: dict[str, Any] | None,
        *,
        chain_id: str,
        event_name: str,
        generation_digest: str | None,
        payload: Mapping[str, Any],
        at: str,
        session: str | None,
        initial: bool,
        drain: bool,
        lease: ChainLease | None = None,
    ) -> dict[str, Any]:
        for control in self._TRANSITION_CONTROLS:
            _require_merge_store_control(control)
        self.ensure_root()
        owned_lease = lease is None
        active_lease = lease or acquire_chain_lease(
            self.root,
            chain_id=chain_id,
            session=self._session(session),
        )
        if active_lease.chain_id != chain_id:
            raise FrozenError(
                "merge transition lease names another chain",
                chain_id=chain_id,
                observed=active_lease.chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        exclusion = getattr(active_lease, "_exclusion", None)
        event_lock_arguments: dict[str, Any] = {}
        if isinstance(exclusion, RecoveryReservation):
            event_lock_arguments = {
                "deadline": exclusion.deadline,
                "clock": exclusion.clock,
                "sleeper": exclusion.sleeper,
            }
        records: tuple[dict[str, Any], ...] = ()
        pending_outbox: dict[str, Any] | None = None
        try:
            with self.event_lock(chain_id, **event_lock_arguments):
                replay: MergeReplayResult | None = None
                if initial:
                    if self._root_entry_exists(
                        self.events_path(chain_id).name
                    ) or self._root_entry_exists(self.state_path(chain_id).name):
                        raise FrozenError(
                            "generated merge chain identity already exists",
                            chain_id=chain_id,
                            schema=REVISION9_OUTPUT_SCHEMA,
                        )
                else:
                    replay = self._read_replay_locked(chain_id)
                    if snapshot is None:
                        raise ValueError("merge transition requires a loaded snapshot")
                    _require_merge_store_control("lease-tail-authentication")
                    self._require_tail_version(
                        snapshot,
                        replay.tail_sequence,
                        replay.tail_digest,
                        family="merge",
                        refusal_chain=replay.state,
                    )
                    if canonical_bytes(snapshot) != canonical_bytes(replay.state):
                        raise FrozenError(
                            "merge transition snapshot contradicts event replay",
                            chain_id=chain_id,
                            schema=REVISION9_OUTPUT_SCHEMA,
                        )
                    if replay.state.get("journal_outbox") is not None:
                        raise Refusal(
                            V2ReasonCode.JOURNAL_OUTBOX_PENDING,
                            "forge: merge transition refused — journal outbox is pending",
                            remediation=f"forge status --chain-id {chain_id}",
                            chain=replay.state,
                            schema=REVISION9_OUTPUT_SCHEMA,
                        )
                event, current, records, pending_outbox = self._prepare_event(
                    replay,
                    chain_id=chain_id,
                    event_name=event_name,
                    generation_digest=generation_digest,
                    payload=payload,
                    at=at,
                )
                _require_merge_store_control("event-before-state")
                active_lease.before_event_append()
                self._append_event_bytes(
                    chain_id,
                    canonical_bytes(event) + b"\n",
                    initial=initial,
                )
                self._boundary("merge-event-appended")
                active_lease.before_state_replace()
                self._atomic_state(current)
                self._boundary("merge-state-replaced")
                with self.root_descriptor() as root:
                    os.fsync(root)
                self._boundary("merge-directory-fsynced")
                self._remember_version(
                    current,
                    int(event["sequence"]),
                    str(event["digest"]),
                )
        finally:
            if owned_lease:
                active_lease.release()
                self._boundary("merge-chain-serialization-released")
        if pending_outbox is not None and drain:
            _require_merge_store_control("post-serialization-journal-drain")
            receipt = _drain_chain_batch_capability(
                current,
                pending_outbox,
                records,
            )
            self._boundary("merge-journal-drained")
            return self._append_receipt_with_outer(
                current,
                receipt,
                session=session,
                lease=lease,
            )
        return current

    def _append_receipt_with_outer(
        self,
        snapshot: dict[str, Any],
        receipt: Mapping[str, Any],
        *,
        session: str | None,
        lease: ChainLease | None = None,
    ) -> dict[str, Any]:
        for control in (
            "lease-tail-authentication",
            "builder-transition-validation",
            "event-before-state",
        ):
            _require_merge_store_control(control)
        chain_id = str(snapshot["chain_id"])
        if set(receipt) != {
            "idempotency_key",
            "batch_digest",
            "receipt_digest",
        }:
            raise FrozenError(
                "merge journal receipt is malformed",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        owned_lease = lease is None
        active_lease = lease or acquire_chain_lease(
            self.root,
            chain_id=chain_id,
            session=self._session(session),
        )
        if active_lease.chain_id != chain_id:
            raise FrozenError(
                "merge receipt lease names another chain",
                chain_id=chain_id,
                observed=active_lease.chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        exclusion = getattr(active_lease, "_exclusion", None)
        event_lock_arguments: dict[str, Any] = {}
        if isinstance(exclusion, RecoveryReservation):
            event_lock_arguments = {
                "deadline": exclusion.deadline,
                "clock": exclusion.clock,
                "sleeper": exclusion.sleeper,
            }
        try:
            with self.event_lock(chain_id, **event_lock_arguments):
                replay = self._read_replay_locked(chain_id)
                self._require_tail_version(
                    snapshot,
                    replay.tail_sequence,
                    replay.tail_digest,
                    family="merge",
                    refusal_chain=replay.state,
                )
                pending = replay.state.get("journal_outbox")
                if not isinstance(pending, dict) or (
                    receipt.get("idempotency_key")
                    != pending.get("idempotency_key")
                    or receipt.get("batch_digest") != pending.get("batch_digest")
                ):
                    raise FrozenError(
                        "merge journal receipt does not match pending outbox",
                        chain_id=chain_id,
                        schema=REVISION9_OUTPUT_SCHEMA,
                    )
                unsigned = {
                    "schema": "forge-merge-event/1",
                    "chain_id": chain_id,
                    "sequence": replay.tail_sequence + 1,
                    "at": iso_z(),
                    "event": "journal_receipted",
                    "generation_digest": (
                        replay.state.get("candidate", {}).get("generation_digest")
                        if isinstance(replay.state.get("candidate"), dict)
                        else None
                    ),
                    "previous_digest": replay.tail_digest,
                    "payload": copy.deepcopy(dict(receipt)),
                }
                event = {
                    **unsigned,
                    "digest": sha256_bytes(canonical_bytes(unsigned)),
                }
                current = reduce_merge_event(
                    copy.deepcopy(replay.state), copy.deepcopy(event)
                )
                _batch, builders, _journal = runtime._coordination_modules()
                context = copy.deepcopy(replay.context)
                if not _merge_state_shape_valid(
                    builders, current, chain_id
                ) or not _merge_transition_valid(
                    builders,
                    event,
                    replay.state,
                    current,
                    context=context,
                    history=replay.events,
                ):
                    raise FrozenError(
                        "merge journal receipt transition is invalid",
                        chain_id=chain_id,
                        schema=REVISION9_OUTPUT_SCHEMA,
                    )
                active_lease.before_event_append()
                self._append_event_bytes(
                    chain_id, canonical_bytes(event) + b"\n", initial=False
                )
                self._boundary("merge-receipt-appended")
                active_lease.before_state_replace()
                self._atomic_state(current)
                self._boundary("merge-receipt-state-replaced")
                self._remember_version(
                    current,
                    int(event["sequence"]),
                    str(event["digest"]),
                )
        finally:
            if owned_lease:
                active_lease.release()
        return current

    def create(
        self,
        initial_delta: Mapping[str, Any],
        *,
        at: str | None = None,
        session: str | None = None,
    ) -> dict[str, Any]:
        chain_id = str(initial_delta.get("chain_id", ""))
        self._validate_id(chain_id)
        binding = initial_delta.get("run_binding")
        with self._journal_outer(
            binding if isinstance(binding, Mapping) else None
        ):
            return self._write_transition_with_outer(
                None,
                chain_id=chain_id,
                event_name="chain_started",
                generation_digest=None,
                payload={"delta": copy.deepcopy(dict(initial_delta))},
                at=at or iso_z(),
                session=session,
                initial=True,
                drain=True,
            )

    def transition(
        self,
        snapshot: dict[str, Any],
        event_name: str,
        payload: Mapping[str, Any],
        *,
        generation_digest: str | None,
        at: str | None = None,
        session: str | None = None,
    ) -> dict[str, Any]:
        validate_merge_state(snapshot, str(snapshot.get("chain_id", "")))
        chain_id = str(snapshot["chain_id"])
        if self.chain_family(chain_id) != "merge":
            raise FrozenError(
                "merge transition routed to a non-merge family",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        binding = snapshot.get("run_binding")
        with self._journal_outer(
            binding if isinstance(binding, Mapping) else None
        ):
            return self._write_transition_with_outer(
                snapshot,
                chain_id=chain_id,
                event_name=event_name,
                generation_digest=generation_digest,
                payload=payload,
                at=at or iso_z(),
                session=session,
                initial=False,
                drain=True,
            )

    def transition_locked(
        self,
        snapshot: dict[str, Any],
        event_name: str,
        payload: Mapping[str, Any],
        *,
        generation_digest: str | None,
        lease: ChainLease,
        at: str | None = None,
        session: str | None = None,
    ) -> dict[str, Any]:
        """Append while an outer journal/common-lock/chain-lease epoch is held."""

        validate_merge_state(snapshot, str(snapshot.get("chain_id", "")))
        chain_id = str(snapshot["chain_id"])
        if self.chain_family(chain_id) != "merge":
            raise FrozenError(
                "merge transition routed to a non-merge family",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        return self._write_transition_with_outer(
            snapshot,
            chain_id=chain_id,
            event_name=event_name,
            generation_digest=generation_digest,
            payload=payload,
            at=at or iso_z(),
            session=session,
            initial=False,
            drain=True,
            lease=lease,
        )

    def load_locked(self, chain_id: str, *, lease: ChainLease) -> dict[str, Any]:
        """Re-read one current projection while its external lease is owned."""

        self._validate_id(chain_id)
        if lease.chain_id != chain_id or self.chain_family(chain_id) != "merge":
            raise FrozenError(
                "merge locked load has a mismatched family or lease",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        lease._revalidate("locked-load")
        exclusion = getattr(lease, "_exclusion", None)
        event_lock_arguments: dict[str, Any] = {}
        if isinstance(exclusion, RecoveryReservation):
            event_lock_arguments = {
                "deadline": exclusion.deadline,
                "clock": exclusion.clock,
                "sleeper": exclusion.sleeper,
            }
        with self.event_lock(chain_id, **event_lock_arguments):
            replay = self._read_replay_locked(chain_id)
            if self._projection_status(replay)[0] != "current":
                raise FrozenError(
                    "merge projection is stale inside a locked epoch",
                    chain_id=chain_id,
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            state = self._resolve_replayed_projection(replay)
            self._remember_version(state, replay.tail_sequence, replay.tail_digest)
            return state

    def recover_pending_outbox(
        self, chain_id: str, *, session: str | None = None
    ) -> dict[str, Any]:
        _require_merge_store_control("post-serialization-journal-drain")
        self._validate_id(chain_id)
        if self.chain_family(chain_id) != "merge":
            raise FrozenError(
                "merge outbox recovery routed to a non-merge family",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        with self.event_lock(chain_id):
            preliminary = self._read_replay_locked(
                chain_id, verify_receipts=False
            )
        binding = preliminary.state.get("run_binding")
        if not isinstance(binding, Mapping):
            raise FrozenError(
                "pending merge outbox lacks an immutable run binding",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        with self._journal_outer(binding):
            state = self._load_with_outer(chain_id, session=session)
            pending = state.get("journal_outbox")
            if pending is None:
                return state
            with self.event_lock(chain_id):
                replay = self._read_replay_locked(chain_id)
                carrier = replay.entries[-1]
                records = carrier[3]
                if (
                    not records
                    or carrier[4] != pending.get("source_event_digest")
                ):
                    raise FrozenError(
                        "pending merge outbox lacks its exact carried batch",
                        chain_id=chain_id,
                        schema=REVISION9_OUTPUT_SCHEMA,
                    )
            receipt = _drain_chain_batch_capability(state, pending, records)
            self._boundary("merge-journal-drained")
            return self._append_receipt_with_outer(
                state,
                receipt,
                session=session,
            )


def _open_owned_directory(path: Path) -> tuple[Path, int]:
    canonical = Path(os.path.realpath(path))
    descriptor = os.open(
        canonical,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        ChainStore._owned_directory(descriptor, str(canonical))
        return canonical, descriptor
    except BaseException:
        os.close(descriptor)
        raise


@dataclasses.dataclass(frozen=True)
class RecoveryReservation:
    common_dir: Path
    identity: PublishedLockRecord
    deadline: float
    clock: Callable[[], float] = dataclasses.field(
        repr=False, compare=False
    )
    sleeper: Callable[[float], None] = dataclasses.field(
        repr=False, compare=False
    )

    @property
    def record(self) -> dict[str, Any]:
        return copy.deepcopy(self.identity.record)

    def assert_current(self, operation: str) -> None:
        """Revalidate this exact reservation inside its original deadline."""

        _require_deadline_open(self.deadline, self.clock, operation)
        canonical, common = _open_owned_directory(self.common_dir)
        try:
            _revalidate_record_at(
                common,
                COMMON_LOCK_RECOVERY_NAME,
                canonical / COMMON_LOCK_RECOVERY_NAME,
                self.identity,
                _validate_recovery_record,
            )
        finally:
            os.close(common)

    def remaining_timeout(self, operation: str) -> float:
        self.assert_current(operation)
        remaining = self.deadline - self.clock()
        if remaining <= 0:
            raise TimeoutError(
                f"{operation} exhausted the shared common-lock deadline"
            )
        return remaining

    def affected_merge_chain(self) -> str:
        """Return the reservation's one affected merge chain, or fail closed."""

        record = self.identity.record
        identities = [
            (record.get("stale_owner_kind"), record.get("stale_owner_chain_id")),
            (record.get("inflight_owner_kind"), record.get("inflight_chain_id")),
        ]
        chains = {
            str(selected_chain)
            for kind, selected_chain in identities
            if kind is not None or selected_chain is not None
            if kind == "merge"
            and isinstance(selected_chain, str)
            and CHAIN_ID_RE.fullmatch(selected_chain) is not None
        }
        populated = [
            (kind, selected_chain)
            for kind, selected_chain in identities
            if kind is not None or selected_chain is not None
        ]
        if not populated or len(chains) != 1 or any(
            kind != "merge" or selected_chain not in chains
            for kind, selected_chain in populated
        ):
            raise OSError(
                "recovery reservation does not identify one affected merge chain"
            )
        return next(iter(chains))

    def matches_chain(self, chain_id: str) -> bool:
        try:
            return self.affected_merge_chain() == chain_id
        except OSError:
            return False


def _new_owner_record(
    owner_kind: str,
    chain_id: str | None,
    operation: str,
    *,
    host: str,
    pid: int,
    now: Callable[[], dt.datetime],
) -> dict[str, Any]:
    return _validate_owner_record(
        {
            "schema": "forge-rebase-lock/1",
            "owner_kind": owner_kind,
            "chain_id": chain_id,
            "host": host,
            "pid": pid,
            "nonce": secrets.token_hex(16),
            "operation": operation,
            "started_at": iso_z(now()),
        }
    )


def _fence_matches_owner(
    fence: PublishedLockRecord, owner: PublishedLockRecord
) -> bool:
    return (
        fence.record.get("owner_kind") == owner.record.get("owner_kind")
        and fence.record.get("chain_id") == owner.record.get("chain_id")
    )


def _publish_portable_owner(
    common: int,
    common_dir: Path,
    record: Mapping[str, Any],
    boundary: Callable[[str], None] | None,
) -> PublishedLockRecord:
    _require_common_lock_control("portable-before-flock")
    temporary, temporary_identity = _create_private_record_at(
        common,
        common_dir,
        "agent-rebase.lock.intent",
        record,
        boundary=boundary,
        stage="owner-temp-fsynced",
    )
    published = False
    outer: PublishedLockRecord | None = None
    lockdir = -1
    try:
        _publish_no_replace_link(
            common, temporary, common, COMMON_LOCK_INTENT_NAME
        )
        published = True
        os.fsync(common)
        outer = _read_owned_record_at(
            common,
            COMMON_LOCK_INTENT_NAME,
            common_dir / COMMON_LOCK_INTENT_NAME,
            _validate_owner_record,
        )
        if not _same_published_record(outer, temporary_identity):
            raise OSError("published intent differs from its private inode")
        if boundary is not None:
            boundary("owner-intent-published")
        _unlink_revalidated_record_at(
            common,
            temporary,
            common_dir / temporary,
            temporary_identity,
            _validate_owner_record,
        )
        os.fsync(common)
        if boundary is not None:
            boundary("owner-temp-unlinked")
        os.mkdir(COMMON_LOCK_DIRECTORY_NAME, 0o700, dir_fd=common)
        lockdir = _open_lock_directory(common, common_dir)
        os.fchmod(lockdir, 0o700)
        if boundary is not None:
            boundary("owner-lockdir-created")
        _publish_no_replace_link(
            common,
            COMMON_LOCK_INTENT_NAME,
            lockdir,
            COMMON_LOCK_OWNER_NAME,
        )
        if boundary is not None:
            boundary("owner-inner-linked")
        os.fsync(lockdir)
        os.fsync(common)
        if boundary is not None:
            boundary("owner-portable-fsynced")
        inspection = _inspect_common_lock_fd(common, common_dir)
        if (
            inspection.topology != "complete"
            or inspection.outer is None
            or not _same_published_record(inspection.outer, outer)
        ):
            raise OSError("portable ownership did not validate as one complete pair")
        return inspection.outer
    except BaseException as exc:
        if isinstance(exc, CommonLockBoundaryCrash):
            raise
        try:
            os.unlink(temporary, dir_fd=common)
            os.fsync(common)
        except (FileNotFoundError, OSError):
            pass
        if published and outer is not None:
            try:
                _release_portable_identity(
                    common,
                    common_dir,
                    outer,
                    boundary=None,
                    prefix="failed-acquisition",
                    complete_partial=False,
                )
            except (OSError, ValueError):
                pass
        raise
    finally:
        if lockdir >= 0:
            os.close(lockdir)


def _release_portable_identity(
    common: int,
    common_dir: Path,
    outer: PublishedLockRecord,
    *,
    boundary: Callable[[str], None] | None,
    prefix: str,
    complete_partial: bool,
) -> None:
    _require_common_lock_control("reverse-release-order")
    inspection = _inspect_common_lock_fd(common, common_dir)
    if inspection.topology == "free":
        os.fsync(common)
        return
    if (
        not inspection.recoverable
        or inspection.outer is None
        or not _same_published_record(inspection.outer, outer)
    ):
        raise OSError("portable owner topology or identity changed before release")
    if complete_partial and inspection.topology != "complete":
        if inspection.topology == "outer-only":
            os.mkdir(COMMON_LOCK_DIRECTORY_NAME, 0o700, dir_fd=common)
            lockdir = _open_lock_directory(common, common_dir)
            os.fchmod(lockdir, 0o700)
            if boundary is not None:
                boundary(f"{prefix}-lockdir-completed")
        else:
            lockdir = _open_lock_directory(common, common_dir)
        try:
            _revalidate_record_at(
                common,
                COMMON_LOCK_INTENT_NAME,
                common_dir / COMMON_LOCK_INTENT_NAME,
                outer,
                _validate_owner_record,
            )
            _publish_no_replace_link(
                common,
                COMMON_LOCK_INTENT_NAME,
                lockdir,
                COMMON_LOCK_OWNER_NAME,
            )
            os.fsync(lockdir)
            os.fsync(common)
            if boundary is not None:
                boundary(f"{prefix}-inner-completed")
        finally:
            os.close(lockdir)
        inspection = _inspect_common_lock_fd(common, common_dir)
    if inspection.topology == "complete":
        lockdir = _open_lock_directory(common, common_dir)
        try:
            inner = _read_owned_record_at(
                lockdir,
                COMMON_LOCK_OWNER_NAME,
                common_dir / COMMON_LOCK_DIRECTORY_NAME / COMMON_LOCK_OWNER_NAME,
                _validate_owner_record,
            )
            if not _same_published_record(inner, outer):
                raise OSError("inner owner identity changed before release")
            _unlink_revalidated_record_at(
                lockdir,
                COMMON_LOCK_OWNER_NAME,
                common_dir / COMMON_LOCK_DIRECTORY_NAME / COMMON_LOCK_OWNER_NAME,
                inner,
                _validate_owner_record,
            )
            if boundary is not None:
                boundary(f"{prefix}-inner-unlinked")
            os.fsync(lockdir)
            if boundary is not None:
                boundary(f"{prefix}-inner-fsynced")
        finally:
            os.close(lockdir)
        os.rmdir(COMMON_LOCK_DIRECTORY_NAME, dir_fd=common)
        if boundary is not None:
            boundary(f"{prefix}-lockdir-removed")
        os.fsync(common)
        if boundary is not None:
            boundary(f"{prefix}-parent-fsynced")
    elif inspection.topology == "outer-empty-directory":
        lockdir = _open_lock_directory(common, common_dir)
        try:
            if os.listdir(lockdir):
                raise OSError("lock directory ceased to be empty")
            os.fsync(lockdir)
        finally:
            os.close(lockdir)
        os.rmdir(COMMON_LOCK_DIRECTORY_NAME, dir_fd=common)
        if boundary is not None:
            boundary(f"{prefix}-lockdir-removed")
        os.fsync(common)
        if boundary is not None:
            boundary(f"{prefix}-parent-fsynced")
    elif inspection.topology == "outer-only":
        # This topology is also the crash window after rmdir but before its
        # parent fsync.  Always establish that durability boundary again
        # before the identifying outer intent can be removed.
        os.fsync(common)
        if boundary is not None:
            boundary(f"{prefix}-parent-fsynced")
    else:
        raise OSError("portable owner is not releasable")
    _unlink_revalidated_record_at(
        common,
        COMMON_LOCK_INTENT_NAME,
        common_dir / COMMON_LOCK_INTENT_NAME,
        outer,
        _validate_owner_record,
    )
    if boundary is not None:
        boundary(f"{prefix}-intent-unlinked")
    os.fsync(common)
    if boundary is not None:
        boundary(f"{prefix}-final-fsynced")


def _publish_recovery_reservation(
    common: int,
    common_dir: Path,
    record: Mapping[str, Any],
    boundary: Callable[[str], None] | None,
    *,
    deadline: float,
    clock: Callable[[], float],
    sleeper: Callable[[float], None],
) -> RecoveryReservation | None:
    _require_common_lock_control("immutable-recovery-reservation")
    temporary, temporary_identity = _create_private_record_at(
        common,
        common_dir,
        "agent-rebase.recover",
        record,
        boundary=boundary,
        stage="recovery-temp-fsynced",
    )
    try:
        try:
            _publish_no_replace_link(
                common, temporary, common, COMMON_LOCK_RECOVERY_NAME
            )
        except FileExistsError:
            _unlink_revalidated_record_at(
                common,
                temporary,
                common_dir / temporary,
                temporary_identity,
                _validate_recovery_record,
            )
            os.fsync(common)
            return None
        os.fsync(common)
        canonical = _read_owned_record_at(
            common,
            COMMON_LOCK_RECOVERY_NAME,
            common_dir / COMMON_LOCK_RECOVERY_NAME,
            _validate_recovery_record,
        )
        if not _same_published_record(canonical, temporary_identity):
            raise OSError("recovery reservation publication changed identity")
        if boundary is not None:
            boundary("recovery-reservation-published")
        _unlink_revalidated_record_at(
            common,
            temporary,
            common_dir / temporary,
            temporary_identity,
            _validate_recovery_record,
        )
        os.fsync(common)
        if boundary is not None:
            boundary("recovery-temp-unlinked")
        return RecoveryReservation(
            common_dir,
            canonical,
            deadline,
            clock,
            sleeper,
        )
    except BaseException as exc:
        if isinstance(exc, CommonLockBoundaryCrash):
            raise
        try:
            os.unlink(temporary, dir_fd=common)
            os.fsync(common)
        except (FileNotFoundError, OSError):
            pass
        # A published canonical reservation is immutable even when a later
        # step fails.  Never roll it back here.
        raise


def _reservation_evidence(common: int, common_dir: Path) -> dict[str, Any] | None:
    try:
        reservation = _read_owned_record_at(
            common,
            COMMON_LOCK_RECOVERY_NAME,
            common_dir / COMMON_LOCK_RECOVERY_NAME,
            _validate_recovery_record,
        )
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        return {
            "reservation": _opaque_path_evidence_at(
                common,
                COMMON_LOCK_RECOVERY_NAME,
                common_dir / COMMON_LOCK_RECOVERY_NAME,
            ),
            "detail": f"immutable reservation is malformed or unreadable: {exc}",
        }
    return {"reservation": reservation.evidence()}


def _clear_owned_reservation(
    common: int,
    common_dir: Path,
    reservation: RecoveryReservation,
    boundary: Callable[[str], None] | None,
) -> None:
    _require_common_lock_control("immutable-recovery-reservation")
    _unlink_revalidated_record_at(
        common,
        COMMON_LOCK_RECOVERY_NAME,
        common_dir / COMMON_LOCK_RECOVERY_NAME,
        reservation.identity,
        _validate_recovery_record,
    )
    os.fsync(common)
    if boundary is not None:
        boundary("recovery-reservation-cleared")


def _recovery_record(
    recovery_kind: str,
    *,
    stale_owner: PublishedLockRecord | None,
    inflight: PublishedLockRecord | None,
    host: str,
    pid: int,
    now: Callable[[], dt.datetime],
) -> dict[str, Any]:
    stamp = iso_z(now())
    stale = stale_owner.record if stale_owner is not None else {}
    fence = inflight.record if inflight is not None else {}
    return _validate_recovery_record(
        {
            "schema": "forge-rebase-recovery/1",
            "recovery_kind": recovery_kind,
            "host": host,
            "pid": pid,
            "nonce": secrets.token_hex(16),
            "started_at": stamp,
            "stale_owner_inode": stale_owner.inode if stale_owner is not None else None,
            "stale_owner_digest": stale_owner.digest if stale_owner is not None else None,
            "stale_owner_host": stale.get("host"),
            "stale_owner_pid": stale.get("pid"),
            "stale_owner_kind": stale.get("owner_kind"),
            "stale_owner_chain_id": stale.get("chain_id"),
            "inflight_inode": inflight.inode if inflight is not None else None,
            "inflight_digest": inflight.digest if inflight is not None else None,
            "inflight_host": fence.get("host"),
            "inflight_pgid": fence.get("pgid"),
            "inflight_owner_kind": fence.get("owner_kind"),
            "inflight_chain_id": fence.get("chain_id"),
            "owner_dead_at": stamp if stale_owner is not None else None,
            "group_dead_at": stamp if inflight is not None else None,
        }
    )


def _fence_death_proof(
    fence: PublishedLockRecord,
    *,
    group_dead_at: str,
) -> dict[str, Any]:
    return {
        "schema": "forge-rebase-fence-death/1",
        "operation": fence.record["operation"],
        "intent_digest": fence.record["intent_digest"],
        "fence_digest": fence.digest,
        "host": fence.record["host"],
        "pgid": fence.record["pgid"],
        "group_dead_at": group_dead_at,
    }


def _require_recovery_proof_recorder(
    owner_kinds: Sequence[str],
    recorder: Callable[[dict[str, Any]], Any] | None,
    *,
    no_transaction_record: bool,
) -> None:
    _require_common_lock_control("death-proof-revalidation")
    if (
        recorder is None
        and not no_transaction_record
        and any(kind in {"merge", "push"} for kind in owner_kinds)
    ):
        raise OSError(
            "common-lock recovery recorder is required before proof-dependent unlink"
        )


def _persist_recovery_proof(
    proof: Mapping[str, Any],
    recorder: Callable[[dict[str, Any]], Any] | None,
    *,
    owner_kinds: Sequence[str],
    no_transaction_record: bool,
    proof_already_persisted: bool = False,
) -> None:
    _require_recovery_proof_recorder(
        owner_kinds,
        recorder,
        no_transaction_record=no_transaction_record,
    )
    if proof_already_persisted or recorder is None:
        return
    recorder(copy.deepcopy(dict(proof)))


def _recovery_classification_receipt_valid(
    value: object,
    *,
    reservation: RecoveryReservation,
    fence: PublishedLockRecord | None,
) -> bool:
    """Validate the exact receipt returned by transactional classification."""

    if not isinstance(value, Mapping) or set(value) != {
        "schema",
        "chain_id",
        "chain_store",
        "reservation_digest",
        "fence_digest",
        "proof_digest",
        "event_digest",
    }:
        return False
    try:
        selected_chain = reservation.affected_merge_chain()
    except OSError:
        return False
    fields_valid = bool(
        value.get("schema") == "forge-merge-fence-recovery-receipt/1"
        and value.get("chain_id") == selected_chain
        and isinstance(value.get("chain_store"), str)
        and os.path.isabs(str(value.get("chain_store")))
        and value.get("reservation_digest") == reservation.identity.digest
        and value.get("fence_digest")
        == (fence.digest if fence is not None else None)
        and SHA256_RE.fullmatch(str(value.get("proof_digest", ""))) is not None
        and SHA256_RE.fullmatch(str(value.get("event_digest", ""))) is not None
    )
    if not fields_valid:
        return False
    try:
        chain_store = Path(str(value["chain_store"]))
        store = MergeChainStore(chain_store.parent.parent)
        if Path(os.path.realpath(store.root)) != Path(
            os.path.realpath(chain_store)
        ):
            return False
        reservation.assert_current(
            "reservation-held recovery receipt validation"
        )
        with store.event_lock(
            selected_chain,
            deadline=reservation.deadline,
            clock=reservation.clock,
            sleeper=reservation.sleeper,
        ):
            replay = store._read_replay_locked(selected_chain)
        if replay.tail_digest != value.get("event_digest") or not replay.events:
            return False
        retained_event = replay.events[-1]
        retained_payload = retained_event.get("payload")
        retained_proof = (
            retained_payload.get("recovery_proof")
            if isinstance(retained_payload, Mapping)
            else None
        )
        return bool(
            retained_event.get("event") == "condition_recorded"
            and retained_event.get("digest") == value.get("event_digest")
            and isinstance(retained_proof, Mapping)
            and retained_proof.get("digest") == value.get("proof_digest")
            and retained_proof.get("chain_id") == selected_chain
            and retained_proof.get("reservation")
            == reservation.identity.evidence()
            and retained_proof.get("fence")
            == (fence.evidence() if fence is not None else None)
        )
    except (FrozenError, OSError, ValueError):
        return False


class CommonRebaseLock:
    """One long-lived FR-235 portable owner and optional secondary flock."""

    def __init__(
        self,
        *,
        common_dir: Path,
        common_descriptor: int,
        owner: PublishedLockRecord,
        flock_descriptor: int | None,
        flock_impl: Callable[[int, int], Any],
        boundary: Callable[[str], None] | None,
        deadline: float,
        clock: Callable[[], float],
        sleeper: Callable[[float], None],
        pid_probe: Callable[[int], str],
        group_probe: Callable[[int], str],
        recovery_recorder: Callable[[dict[str, Any]], Any] | None,
        no_transaction_record: bool,
    ) -> None:
        self.common_dir = common_dir
        self._common = common_descriptor
        self.owner = owner
        self._flock = flock_descriptor
        self._flock_impl = flock_impl
        self._boundary = boundary
        self.deadline = deadline
        self._clock = clock
        self._sleeper = sleeper
        self._pid_probe = pid_probe
        self._group_probe = group_probe
        self._recovery_recorder = recovery_recorder
        self._no_transaction_record = no_transaction_record
        self._flock_released = flock_descriptor is None
        self._released = False
        self._release_pending = False
        self._unresolved_fence: PublishedLockRecord | None = None

    @property
    def record(self) -> dict[str, Any]:
        return copy.deepcopy(self.owner.record)

    @property
    def digest(self) -> str:
        return self.owner.digest

    @property
    def released(self) -> bool:
        return self._released

    def _emit_boundary(self, stage: str) -> None:
        if self._boundary is not None:
            self._boundary(stage)

    def assert_held(self, *, allow_fence: bool = False) -> None:
        if self._released or self._common < 0:
            raise OSError("common rebase lock is already released")
        if self._release_pending:
            raise OSError("common rebase lock admits release recovery only")
        inspection = _inspect_common_lock_fd(self._common, self.common_dir)
        if (
            inspection.topology != "complete"
            or inspection.outer is None
            or not _same_published_record(inspection.outer, self.owner)
        ):
            raise OSError("common rebase lock portable identity changed")
        if not self._flock_released and self._flock is None:
            raise OSError("common rebase lock lost its secondary flock descriptor")
        if _reservation_evidence(self._common, self.common_dir) is not None:
            raise OSError("common rebase lock has an unresolved recovery reservation")
        fence_present = _common_fence_path_present(self._common)
        if fence_present and not allow_fence:
            raise OSError("common rebase lock has an unresolved in-flight fence")

    def recover_owned_fence(
        self,
        fence: PublishedLockRecord,
        *,
        persist_proof: Callable[[dict[str, Any]], Any] | None = None,
        lifecycle_classifier: (
            Callable[[RecoveryReservation, PublishedLockRecord | None], Any] | None
        ) = None,
    ) -> None:
        """Classify and release a proven-dead fence under one reservation."""

        release_was_pending = self._release_pending
        if release_was_pending:
            # This method is itself the sole admitted release-recovery step.
            self._release_pending = False
        try:
            self.assert_held(allow_fence=True)
        finally:
            self._release_pending = release_was_pending
        current = _revalidate_record_at(
            self._common,
            COMMON_LOCK_INFLIGHT_NAME,
            self.common_dir / COMMON_LOCK_INFLIGHT_NAME,
            fence,
            _validate_fence_record,
        )
        if current.record.get("host") != self.owner.record.get("host"):
            raise OSError("in-flight fence host is not local")
        if not _fence_matches_owner(current, self.owner):
            raise OSError("in-flight fence does not belong to this common-lock owner")
        if self._group_probe(int(current.record["pgid"])) != "dead":
            raise OSError("in-flight process group is live or unprovable")
        recorder = (
            persist_proof
            if persist_proof is not None
            else self._recovery_recorder
        )
        _require_recovery_proof_recorder(
            (str(current.record["owner_kind"]),),
            recorder,
            no_transaction_record=self._no_transaction_record,
        )
        classifier = lifecycle_classifier
        reservation: RecoveryReservation | None = None
        try:
            reservation = _publish_recovery_reservation(
                self._common,
                self.common_dir,
                _recovery_record(
                    "flock-held-dead-fence",
                    stale_owner=None,
                    inflight=current,
                    host=str(self.owner.record["host"]),
                    pid=int(self.owner.record["pid"]),
                    now=runtime.utc_now,
                ),
                self._boundary,
                deadline=self.deadline,
                clock=self._clock,
                sleeper=self._sleeper,
            )
            if reservation is None:
                raise OSError("another recovery reservation won publication")
            _clear_reserved_fence(
                self._common,
                self.common_dir,
                reservation,
                group_probe=self._group_probe,
                deadline=self.deadline,
                clock=self._clock,
                boundary=self._boundary,
                recovery_recorder=recorder,
                no_transaction_record=self._no_transaction_record,
                lifecycle_classifier=classifier,
            )
            _clear_owned_reservation(
                self._common, self.common_dir, reservation, self._boundary
            )
            reservation = None
            self._unresolved_fence = None
            self._emit_boundary("fence-recovered")
        except BaseException as exc:
            if isinstance(exc, CommonLockBoundaryCrash):
                raise
            if reservation is not None:
                if self._no_transaction_record:
                    try:
                        _clear_owned_reservation(
                            self._common,
                            self.common_dir,
                            reservation,
                            boundary=None,
                        )
                    except (OSError, ValueError):
                        pass
            raise

    def release(self) -> None:
        if self._released:
            return
        evidence = {
            "intent_path": str(self.common_dir / COMMON_LOCK_INTENT_NAME),
            "inode": self.owner.inode,
            "digest": self.owner.digest,
        }
        try:
            if self._unresolved_fence is not None:
                raise OSError("an unresolved fenced process permits only fence recovery")
            if _common_fence_path_present(self._common):
                raise OSError("in-flight fence remains at common-lock release")
            _require_common_lock_control("reverse-release-order")
            if not self._flock_released:
                assert self._flock is not None
                self._flock_impl(self._flock, fcntl.LOCK_UN)
                os.close(self._flock)
                self._flock = None
                self._flock_released = True
                self._emit_boundary("release-flock")
            _release_portable_identity(
                self._common,
                self.common_dir,
                self.owner,
                boundary=self._boundary,
                prefix="release",
                complete_partial=False,
            )
            self._released = True
            self._release_pending = False
            os.close(self._common)
            self._common = -1
        except BaseException as exc:
            if isinstance(exc, CommonLockBoundaryCrash):
                raise
            self._release_pending = True
            evidence["error"] = str(exc)
            evidence["flock_released"] = self._flock_released
            raise CommonLockReleaseFailure(evidence) from exc

    def retry_release(self) -> None:
        """Retry only the recorded reverse-order release after a failure."""

        if not self._release_pending:
            self.release()
            return
        self._release_pending = False
        self.release()

    def __enter__(self) -> "CommonRebaseLock":
        self.assert_held()
        return self

    def __exit__(self, _kind: object, _value: object, _traceback: object) -> None:
        self.release()


def _acquire_secondary_flock(
    common: int,
    common_dir: Path,
    owner_record: Mapping[str, Any],
    *,
    deadline: float,
    clock: Callable[[], float],
    sleeper: Callable[[float], None],
    flock_impl: Callable[[int, int], Any],
    boundary: Callable[[str], None] | None,
) -> int:
    descriptor = os.open(
        COMMON_LOCK_FLOCK_NAME,
        os.O_RDWR
        | os.O_CREAT
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        0o600,
        dir_fd=common,
    )
    acquired = False
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_uid != os.geteuid():
            raise OSError("secondary flock path is not owner-controlled and regular")
        os.fchmod(descriptor, 0o600)
        while True:
            try:
                flock_impl(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                _require_deadline_open(deadline, clock, "secondary flock acquisition")
                break
            except (BlockingIOError, InterruptedError) as exc:
                if isinstance(exc, BlockingIOError) and exc.errno not in {
                    None,
                    errno.EACCES,
                    errno.EAGAIN,
                }:
                    raise
                if not _sleep_with_deadline(deadline, clock, sleeper):
                    raise TimeoutError("secondary flock exhausted the shared deadline")
        if boundary is not None:
            boundary("flock-acquired")
        encoded = canonical_bytes(dict(owner_record))
        os.lseek(descriptor, 0, os.SEEK_SET)
        os.ftruncate(descriptor, 0)
        _write_all(descriptor, encoded)
        os.fsync(descriptor)
        if boundary is not None:
            boundary("flock-record-fsynced")
        return descriptor
    except BaseException:
        if acquired:
            try:
                flock_impl(descriptor, fcntl.LOCK_UN)
            except OSError:
                pass
        os.close(descriptor)
        raise


def _read_fence_for_recovery(
    common: int, common_dir: Path
) -> tuple[PublishedLockRecord | None, str | None, dict[str, Any] | None]:
    try:
        return (
            _record_at_if_present(
                common,
                COMMON_LOCK_INFLIGHT_NAME,
                common_dir / COMMON_LOCK_INFLIGHT_NAME,
                _validate_fence_record,
            ),
            None,
            None,
        )
    except (OSError, ValueError) as exc:
        return (
            None,
            str(exc),
            {
                "fence": _opaque_path_evidence_at(
                    common,
                    COMMON_LOCK_INFLIGHT_NAME,
                    common_dir / COMMON_LOCK_INFLIGHT_NAME,
                )
            },
        )


def _common_fence_path_present(common: int) -> bool:
    """Observe only whether the physical fence name exists.

    Revision 12 permits an ordinary contender to notice that the reserved
    name is occupied, but not to open, parse, probe, classify, or clear the
    occupant.  In particular this check runs before portable/flock
    publication so an ordinary refusal is byte preserving for every lock
    artifact.
    """

    try:
        os.stat(
            COMMON_LOCK_INFLIGHT_NAME,
            dir_fd=common,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return False
    return True


def _recover_stale_portable_owner(
    common: int,
    common_dir: Path,
    stale: PublishedLockRecord,
    inflight: PublishedLockRecord | None,
    reservation: RecoveryReservation,
    *,
    pid_probe: Callable[[int], str],
    group_probe: Callable[[int], str],
    deadline: float,
    clock: Callable[[], float],
    boundary: Callable[[str], None] | None,
    recovery_recorder: Callable[[dict[str, Any]], Any] | None,
    no_transaction_record: bool,
    proof_already_persisted: bool = False,
) -> None:
    _require_common_lock_control("death-proof-revalidation")
    reservation.assert_current("stale-owner reservation revalidation")
    canonical_reservation = _revalidate_record_at(
        common,
        COMMON_LOCK_RECOVERY_NAME,
        common_dir / COMMON_LOCK_RECOVERY_NAME,
        reservation.identity,
        _validate_recovery_record,
    )
    inspection = _inspect_common_lock_fd(common, common_dir)
    if (
        not inspection.recoverable
        or inspection.outer is None
        or not _same_published_record(inspection.outer, stale)
    ):
        raise OSError("stale portable owner changed after reservation")
    if pid_probe(int(stale.record["pid"])) != "dead":
        raise OSError("stale portable owner death could not be re-proved")
    _require_deadline_open(deadline, clock, "stale-owner death proof")
    proof = copy.deepcopy(canonical_reservation.record)
    current_inflight: PublishedLockRecord | None = None
    if inflight is not None:
        current_inflight = _revalidate_record_at(
            common,
            COMMON_LOCK_INFLIGHT_NAME,
            common_dir / COMMON_LOCK_INFLIGHT_NAME,
            inflight,
            _validate_fence_record,
        )
        if group_probe(int(current_inflight.record["pgid"])) != "dead":
            raise OSError("in-flight group death could not be re-proved")
        _require_deadline_open(deadline, clock, "in-flight group death proof")
    _persist_recovery_proof(
        proof,
        recovery_recorder,
        owner_kinds=(str(stale.record["owner_kind"]),),
        no_transaction_record=no_transaction_record,
        proof_already_persisted=proof_already_persisted,
    )
    if current_inflight is not None:
        _persist_recovery_proof(
            _fence_death_proof(
                current_inflight,
                group_dead_at=str(canonical_reservation.record["group_dead_at"]),
            ),
            recovery_recorder,
            owner_kinds=(str(current_inflight.record["owner_kind"]),),
            no_transaction_record=no_transaction_record,
            proof_already_persisted=proof_already_persisted,
        )
    if pid_probe(int(stale.record["pid"])) != "dead":
        raise OSError("stale portable owner PID became live or unprovable")
    reservation.assert_current("stale-owner release")
    _release_portable_identity(
        common,
        common_dir,
        stale,
        boundary=boundary,
        prefix="recovery-release",
        complete_partial=True,
    )
    if boundary is not None:
        boundary("recovery-stale-owner-released")


def _clear_reserved_fence(
    common: int,
    common_dir: Path,
    reservation: RecoveryReservation,
    *,
    group_probe: Callable[[int], str],
    deadline: float,
    clock: Callable[[], float],
    boundary: Callable[[str], None] | None,
    recovery_recorder: Callable[[dict[str, Any]], Any] | None,
    no_transaction_record: bool,
    lifecycle_classifier: (
        Callable[[RecoveryReservation, PublishedLockRecord | None], Any] | None
    ),
    classification_already_performed: bool = False,
    proof_already_persisted: bool = False,
) -> None:
    _require_common_lock_control("death-proof-revalidation")
    record = reservation.identity.record
    if record.get("inflight_inode") is None:
        return
    reservation.assert_current("reservation-held fence inspection")
    fence = _read_owned_record_at(
        common,
        COMMON_LOCK_INFLIGHT_NAME,
        common_dir / COMMON_LOCK_INFLIGHT_NAME,
        _validate_fence_record,
    )
    if (
        fence.inode != record["inflight_inode"]
        or fence.digest != record["inflight_digest"]
        or fence.record.get("host") != record["inflight_host"]
        or fence.record.get("pgid") != record["inflight_pgid"]
    ):
        raise OSError("in-flight fence changed after recovery reservation")
    if group_probe(int(fence.record["pgid"])) != "dead":
        raise OSError("in-flight group death could not be re-proved")
    _require_deadline_open(deadline, clock, "in-flight group death proof")
    _require_common_lock_control("reservation-held-lifecycle-classification")
    if not classification_already_performed:
        if lifecycle_classifier is None:
            raise OSError(
                "reservation-held lifecycle classification is required before fence clearing"
            )
        reservation.assert_current(
            "reservation-held lifecycle classification"
        )
        classification_result = lifecycle_classifier(reservation, fence)
        receipt_valid = _recovery_classification_receipt_valid(
            classification_result,
            reservation=reservation,
            fence=fence,
        )
        if not no_transaction_record and not receipt_valid:
            raise OSError(
                "reservation-held lifecycle classification did not return its exact durable receipt"
            )
        if receipt_valid:
            proof_already_persisted = True
    reservation.assert_current("reservation-held fence revalidation")
    _revalidate_record_at(
        common,
        COMMON_LOCK_INFLIGHT_NAME,
        common_dir / COMMON_LOCK_INFLIGHT_NAME,
        fence,
        _validate_fence_record,
    )
    if boundary is not None:
        boundary("recovery-fence-lifecycle-classified")
    if proof_already_persisted:
        _persist_recovery_proof(
            record,
            recovery_recorder,
            owner_kinds=(str(fence.record["owner_kind"]),),
            no_transaction_record=no_transaction_record,
            proof_already_persisted=True,
        )
    else:
        _persist_recovery_proof(
            record,
            recovery_recorder,
            owner_kinds=(str(fence.record["owner_kind"]),),
            no_transaction_record=no_transaction_record,
        )
        _persist_recovery_proof(
            _fence_death_proof(
                fence,
                group_dead_at=str(record["group_dead_at"]),
            ),
            recovery_recorder,
            owner_kinds=(str(fence.record["owner_kind"]),),
            no_transaction_record=no_transaction_record,
        )
    if group_probe(int(fence.record["pgid"])) != "dead":
        raise OSError("in-flight group became live or unprovable")
    reservation.assert_current("in-flight fence release")
    _unlink_revalidated_record_at(
        common,
        COMMON_LOCK_INFLIGHT_NAME,
        common_dir / COMMON_LOCK_INFLIGHT_NAME,
        fence,
        _validate_fence_record,
    )
    os.fsync(common)
    if boundary is not None:
        boundary("recovery-fence-cleared")


def acquire_common_lock(
    common_dir: Path,
    *,
    owner_kind: str,
    chain_id: str | None,
    operation: str,
    timeout: float = COMMON_LOCK_TIMEOUT_SECONDS,
    use_flock: bool | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
    now: Callable[[], dt.datetime] = runtime.utc_now,
    host: str | None = None,
    pid: int | None = None,
    pid_probe: Callable[[int], str] = _process_probe,
    group_probe: Callable[[int], str] = _group_probe,
    flock_impl: Callable[[int, int], Any] = fcntl.flock,
    admission_recheck: Callable[[], bool] | None = None,
    recovery_recorder: Callable[[dict[str, Any]], Any] | None = None,
    recovery_classifier: (
        Callable[[RecoveryReservation, PublishedLockRecord | None], Any] | None
    ) = None,
    no_transaction_record: bool = False,
    boundary: Callable[[str], None] | None = None,
) -> CommonRebaseLock:
    """Acquire the universal FR-235 common lock under one monotonic budget."""

    _require_common_lock_control("single-deadline")
    _require_common_lock_control("portable-before-flock")
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError("common-lock timeout must be positive")
    if recovery_recorder is not None and not callable(recovery_recorder):
        raise ValueError("common-lock recovery recorder must be callable")
    if recovery_classifier is not None and not callable(recovery_classifier):
        raise ValueError("common-lock recovery classifier must be callable")
    if recovery_classifier is not None and operation != "recover":
        raise ValueError(
            "common-lock recovery classifier requires an explicit recovery operation"
        )
    if not isinstance(no_transaction_record, bool):
        raise ValueError("common-lock no-transaction opt-out must be boolean")
    local_host = host or socket.gethostname()
    claimant_pid = pid or os.getpid()
    owner_record = _new_owner_record(
        owner_kind,
        chain_id,
        operation,
        host=local_host,
        pid=claimant_pid,
        now=now,
    )
    if recovery_recorder is not None and no_transaction_record:
        raise ValueError(
            "common-lock recovery recorder conflicts with no-transaction opt-out"
        )
    if owner_kind in {"merge", "push"}:
        try:
            _require_recovery_proof_recorder(
                (owner_kind,),
                recovery_recorder,
                no_transaction_record=no_transaction_record,
            )
        except OSError as exc:
            raise ValueError(str(exc)) from exc
    lifecycle_classifier = recovery_classifier
    flock_enabled = hasattr(fcntl, "flock") if use_flock is None else use_flock
    canonical, common = _open_owned_directory(common_dir)
    deadline = clock() + float(timeout)
    last_evidence: dict[str, Any] = {"common_dir": str(canonical)}
    reservation: RecoveryReservation | None = None
    classified_reservation_digest: str | None = None
    proof_persisted_reservation_digest: str | None = None
    portable: PublishedLockRecord | None = None
    flock_descriptor: int | None = None
    try:
        while True:
            if clock() >= deadline:
                raise CommonLockUnavailable(last_evidence)
            existing_reservation = _reservation_evidence(common, canonical)
            if existing_reservation is not None and reservation is None:
                last_evidence = {
                    "common_dir": str(canonical),
                    **existing_reservation,
                }
                if not _sleep_with_deadline(deadline, clock, sleeper):
                    raise CommonLockUnavailable(last_evidence)
                continue
            if operation != "recover":
                try:
                    fence_name_present = _common_fence_path_present(common)
                except OSError as exc:
                    fence_name_present = True
                    last_evidence = {
                        "common_dir": str(canonical),
                        "detail": (
                            "surviving in-flight fence requires explicit "
                            f"recovery: {exc}"
                        ),
                    }
                if fence_name_present:
                    last_evidence = {
                        **last_evidence,
                        "detail": (
                            "surviving in-flight fence requires explicit recovery"
                        ),
                    }
                    if not _sleep_with_deadline(deadline, clock, sleeper):
                        raise CommonLockUnavailable(last_evidence)
                    continue
            inspection = _inspect_common_lock_fd(common, canonical)
            last_evidence = inspection.evidence(canonical)
            if inspection.topology == "free":
                try:
                    _require_deadline_open(
                        deadline, clock, "portable owner publication"
                    )
                    portable = _publish_portable_owner(
                        common, canonical, owner_record, boundary
                    )
                except FileExistsError:
                    portable = None
                    if not _sleep_with_deadline(deadline, clock, sleeper):
                        raise CommonLockUnavailable(last_evidence)
                    continue
                except (OSError, ValueError) as exc:
                    portable = None
                    last_evidence = {
                        **last_evidence,
                        "mechanism": "no-replace hard-link publication",
                        "error": str(exc),
                    }
                    if reservation is not None or not _sleep_with_deadline(
                        deadline, clock, sleeper
                    ):
                        raise CommonLockUnavailable(last_evidence)
                    continue
            elif reservation is None and inspection.recoverable and inspection.outer is not None:
                stale = inspection.outer
                if stale.record.get("host") != local_host:
                    last_evidence["detail"] = "portable owner host is foreign"
                elif pid_probe(int(stale.record["pid"])) != "dead":
                    last_evidence["detail"] = "portable owner PID is live or unprovable"
                elif (
                    operation != "recover"
                    and stale.record.get("owner_kind") == "merge"
                ):
                    last_evidence["detail"] = (
                        "stale merge portable owner requires explicit recovery"
                    )
                elif operation != "recover" and _common_fence_path_present(
                    common
                ):
                    last_evidence["detail"] = (
                        "surviving in-flight fence requires explicit recovery"
                    )
                else:
                    if operation == "recover":
                        fence, fence_error, fence_evidence = (
                            _read_fence_for_recovery(common, canonical)
                        )
                    else:
                        # Ordinary legacy-owner recovery is admitted only
                        # after the presence-only check above.  It never opens,
                        # parses, probes, classifies, or clears a fence.
                        fence, fence_error, fence_evidence = None, None, None
                    recovery_kind = "fallback-owner"
                    if fence_error is not None:
                        last_evidence["detail"] = f"in-flight fence is unprovable: {fence_error}"
                        if fence_evidence is not None:
                            last_evidence.update(fence_evidence)
                    elif fence is not None:
                        if (
                            not _fence_matches_owner(fence, stale)
                            or fence.record.get("host") != local_host
                            or group_probe(int(fence.record["pgid"])) != "dead"
                        ):
                            last_evidence["detail"] = "in-flight fence is live, foreign, mismatched, or unprovable"
                        else:
                            recovery_kind = "fallback-owner-and-fence"
                    if fence_error is None and (
                        fence is None or recovery_kind == "fallback-owner-and-fence"
                    ):
                        if (
                            operation != "recover"
                            and stale.record.get("owner_kind") == "merge"
                        ):
                            # A dead portable owner is still transaction
                            # evidence.  Ordinary acquisition has no authority
                            # to classify or remove it (with or without a
                            # surviving fence); explicit recovery must first
                            # publish the immutable reservation and durable
                            # lifecycle/death proof.
                            last_evidence["detail"] = (
                                "stale portable owner requires explicit recovery"
                            )
                            if not _sleep_with_deadline(
                                deadline, clock, sleeper
                            ):
                                raise CommonLockUnavailable(last_evidence)
                            continue
                        _require_recovery_proof_recorder(
                            (
                                str(stale.record["owner_kind"]),
                                *(
                                    (str(fence.record["owner_kind"]),)
                                    if fence is not None
                                    else ()
                                ),
                            ),
                            recovery_recorder,
                            no_transaction_record=no_transaction_record,
                        )
                        _require_deadline_open(
                            deadline, clock, "stale-owner and fence proof"
                        )
                        record = _recovery_record(
                            recovery_kind,
                            stale_owner=stale,
                            inflight=fence,
                            host=local_host,
                            pid=claimant_pid,
                            now=now,
                        )
                        reservation = _publish_recovery_reservation(
                            common,
                            canonical,
                            record,
                            boundary,
                            deadline=deadline,
                            clock=clock,
                            sleeper=sleeper,
                        )
                        if reservation is not None:
                            _require_deadline_open(
                                deadline, clock, "recovery reservation publication"
                            )
                            try:
                                transactional_recovery = bool(
                                    stale.record.get("owner_kind")
                                    in {"merge", "push"}
                                    or (
                                        fence is not None
                                        and fence.record.get("owner_kind")
                                        in {"merge", "push"}
                                    )
                                )
                                if not transactional_recovery and fence is None:
                                    classification_result = None
                                else:
                                    _require_common_lock_control(
                                        "reservation-held-lifecycle-classification"
                                    )
                                    if lifecycle_classifier is None:
                                        raise OSError(
                                            "reservation-held lifecycle classification is required before stale-owner recovery"
                                        )
                                    reservation.assert_current(
                                        "reservation-held lifecycle classification"
                                    )
                                    classification_result = lifecycle_classifier(
                                        reservation, fence
                                    )
                                    if (
                                        transactional_recovery
                                        and not no_transaction_record
                                        and not (
                                            _recovery_classification_receipt_valid(
                                                classification_result,
                                                reservation=reservation,
                                                fence=fence,
                                            )
                                        )
                                    ):
                                        raise OSError(
                                            "reservation-held lifecycle classification did not return its exact durable receipt"
                                        )
                            except BaseException as classification_error:
                                if isinstance(
                                    classification_error,
                                    CommonLockBoundaryCrash,
                                ):
                                    raise
                                if isinstance(classification_error, Refusal):
                                    _clear_owned_reservation(
                                        common,
                                        canonical,
                                        reservation,
                                        boundary=None,
                                    )
                                    reservation = None
                                    raise
                                if no_transaction_record:
                                    _clear_owned_reservation(
                                        common,
                                        canonical,
                                        reservation,
                                        boundary=None,
                                    )
                                    reservation = None
                                if isinstance(classification_error, FrozenError):
                                    raise
                                raise CommonLockUnavailable(
                                    {
                                        **last_evidence,
                                        "detail": str(classification_error),
                                    }
                                ) from classification_error
                            classified_reservation_digest = (
                                reservation.identity.digest
                            )
                            if _recovery_classification_receipt_valid(
                                classification_result,
                                reservation=reservation,
                                fence=fence,
                            ):
                                proof_persisted_reservation_digest = (
                                    reservation.identity.digest
                                )
                            if fence is not None and boundary is not None:
                                boundary(
                                    "recovery-fence-lifecycle-classified"
                                )
                            _recover_stale_portable_owner(
                                common,
                                canonical,
                                stale,
                                fence,
                                reservation,
                                pid_probe=pid_probe,
                                group_probe=group_probe,
                                deadline=deadline,
                                clock=clock,
                                boundary=boundary,
                                recovery_recorder=recovery_recorder,
                                no_transaction_record=no_transaction_record,
                                proof_already_persisted=(
                                    proof_persisted_reservation_digest
                                    == reservation.identity.digest
                                ),
                            )
                            continue
            if portable is None:
                if not _sleep_with_deadline(deadline, clock, sleeper):
                    raise CommonLockUnavailable(last_evidence)
                continue
            try:
                if flock_enabled:
                    flock_descriptor = _acquire_secondary_flock(
                        common,
                        canonical,
                        owner_record,
                        deadline=deadline,
                        clock=clock,
                        sleeper=sleeper,
                        flock_impl=flock_impl,
                        boundary=boundary,
                    )
                _require_deadline_open(
                    deadline, clock, "in-flight admission inspection"
                )
                if operation != "recover":
                    if _common_fence_path_present(common):
                        raise OSError(
                            "surviving in-flight fence requires explicit recovery"
                        )
                    fence, fence_error, fence_evidence = None, None, None
                else:
                    if (
                        reservation is None
                        and flock_descriptor is None
                        and _common_fence_path_present(common)
                    ):
                        raise OSError(
                            "outer-owner-absent fence recovery requires the secondary flock"
                        )
                    fence, fence_error, fence_evidence = _read_fence_for_recovery(
                        common, canonical
                    )
                if fence_error is not None:
                    raise OSError(
                        canonical_bytes(
                            {
                                "detail": f"in-flight fence is unprovable: {fence_error}",
                                **(fence_evidence or {}),
                            }
                        ).decode("utf-8")
                    )
                if fence is not None:
                    if reservation is not None:
                        _clear_reserved_fence(
                            common,
                            canonical,
                            reservation,
                            group_probe=group_probe,
                            deadline=deadline,
                            clock=clock,
                            boundary=boundary,
                            recovery_recorder=recovery_recorder,
                            no_transaction_record=no_transaction_record,
                            lifecycle_classifier=lifecycle_classifier,
                            classification_already_performed=(
                                classified_reservation_digest
                                == reservation.identity.digest
                            ),
                            proof_already_persisted=(
                                proof_persisted_reservation_digest
                                == reservation.identity.digest
                            ),
                        )
                    elif (
                        operation == "recover"
                        and flock_descriptor is not None
                        and _fence_matches_owner(fence, portable)
                        and fence.record.get("host") == local_host
                        and group_probe(int(fence.record["pgid"])) == "dead"
                    ):
                        _require_deadline_open(
                            deadline, clock, "dead-fence recovery proof"
                        )
                        record = _recovery_record(
                            "flock-held-dead-fence",
                            stale_owner=None,
                            inflight=fence,
                            host=local_host,
                            pid=claimant_pid,
                            now=now,
                        )
                        _require_recovery_proof_recorder(
                            (str(fence.record["owner_kind"]),),
                            recovery_recorder,
                            no_transaction_record=no_transaction_record,
                        )
                        reservation = _publish_recovery_reservation(
                            common,
                            canonical,
                            record,
                            boundary,
                            deadline=deadline,
                            clock=clock,
                            sleeper=sleeper,
                        )
                        if reservation is None:
                            raise OSError("another recovery reservation won publication")
                        _clear_reserved_fence(
                            common,
                            canonical,
                            reservation,
                            group_probe=group_probe,
                            deadline=deadline,
                            clock=clock,
                            boundary=boundary,
                            recovery_recorder=recovery_recorder,
                            no_transaction_record=no_transaction_record,
                            lifecycle_classifier=lifecycle_classifier,
                        )
                    else:
                        raise OSError("in-flight fence is live, mismatched, or unrecoverable")
                if reservation is not None:
                    _require_deadline_open(
                        deadline, clock, "recovery reservation release"
                    )
                    _clear_owned_reservation(common, canonical, reservation, boundary)
                    reservation = None
                    classified_reservation_digest = None
                    proof_persisted_reservation_digest = None
                if admission_recheck is not None and not admission_recheck():
                    raise OSError("locked admission recheck did not pass")
                if clock() >= deadline:
                    raise TimeoutError("locked admission recheck exhausted the shared deadline")
                return CommonRebaseLock(
                    common_dir=canonical,
                    common_descriptor=common,
                    owner=portable,
                    flock_descriptor=flock_descriptor,
                    flock_impl=flock_impl,
                    boundary=boundary,
                    deadline=deadline,
                    clock=clock,
                    sleeper=sleeper,
                    pid_probe=pid_probe,
                    group_probe=group_probe,
                    recovery_recorder=recovery_recorder,
                    no_transaction_record=no_transaction_record,
                )
            except BaseException as exc:
                if isinstance(exc, CommonLockBoundaryCrash):
                    raise
                last_evidence = {
                    "common_dir": str(canonical),
                    "owner": portable.evidence(),
                    "error": str(exc),
                }
                if reservation is not None and (
                    no_transaction_record or owner_kind not in {"merge", "push"}
                ):
                    try:
                        _clear_owned_reservation(
                            common, canonical, reservation, boundary=None
                        )
                        reservation = None
                    except (OSError, ValueError) as reservation_error:
                        last_evidence["reservation_release_error"] = str(
                            reservation_error
                        )
                        raise CommonLockUnavailable(last_evidence) from reservation_error
                if flock_descriptor is not None:
                    try:
                        flock_impl(flock_descriptor, fcntl.LOCK_UN)
                    finally:
                        os.close(flock_descriptor)
                    flock_descriptor = None
                try:
                    _release_portable_identity(
                        common,
                        canonical,
                        portable,
                        boundary=None,
                        prefix="failed-acquisition",
                        complete_partial=False,
                    )
                except (OSError, ValueError) as release_error:
                    last_evidence["release_error"] = str(release_error)
                    raise CommonLockUnavailable(last_evidence) from release_error
                portable = None
                if isinstance(exc, FrozenError):
                    raise
                if isinstance(exc, CommonLockUnavailable):
                    raise
                if reservation is not None:
                    raise CommonLockUnavailable(last_evidence) from exc
                if not _sleep_with_deadline(deadline, clock, sleeper):
                    raise CommonLockUnavailable(last_evidence) from exc
    except BaseException as exc:
        if flock_descriptor is not None:
            try:
                flock_impl(flock_descriptor, fcntl.LOCK_UN)
            except OSError:
                pass
            os.close(flock_descriptor)
        os.close(common)
        if isinstance(exc, TimeoutError):
            raise CommonLockUnavailable(
                {**last_evidence, "error": str(exc)}
            ) from exc
        raise


class ChainLease:
    """FR-237 hard-link lease with mandatory pre-write ABA checks."""

    def __init__(
        self,
        *,
        chains_dir: Path,
        directory_descriptor: int,
        identity: PublishedLockRecord,
        boundary: Callable[[str], None] | None,
        exclusion: CommonRebaseLock | RecoveryReservation | None,
    ) -> None:
        self.chains_dir = chains_dir
        self._directory = directory_descriptor
        self.identity = identity
        self._boundary = boundary
        self._exclusion = exclusion
        self._released = False

    @property
    def record(self) -> dict[str, Any]:
        return copy.deepcopy(self.identity.record)

    @property
    def chain_id(self) -> str:
        return str(self.identity.record["chain_id"])

    @property
    def path(self) -> Path:
        return self.chains_dir / f"{self.chain_id}.lock"

    def _revalidate(self, operation: str) -> None:
        _require_common_lock_control("chain-lease-write-revalidation")
        if self._released or self._directory < 0:
            raise OSError("chain lease is already released")
        if self._exclusion is not None and not _lease_exclusion_is_current(
            self._exclusion, self.chain_id
        ):
            raise OSError(
                "chain lease lost its repository-wide recovery exclusion"
            )
        _revalidate_record_at(
            self._directory,
            self.path.name,
            self.path,
            self.identity,
            _validate_chain_lease_record,
        )
        if self._boundary is not None:
            self._boundary(f"chain-lease-before-{operation}")

    def before_event_append(self) -> None:
        self._revalidate("append")

    def before_state_replace(self) -> None:
        self._revalidate("state-replace")

    def protected_append(self, writer: Callable[[], Any]) -> Any:
        self.before_event_append()
        return writer()

    def protected_state_replace(self, writer: Callable[[], Any]) -> Any:
        self.before_state_replace()
        return writer()

    def release(self) -> None:
        if self._released:
            return
        _require_common_lock_control("chain-lease-write-revalidation")
        try:
            self._revalidate("release")
            _unlink_revalidated_record_at(
                self._directory,
                self.path.name,
                self.path,
                self.identity,
                _validate_chain_lease_record,
            )
            if self._boundary is not None:
                self._boundary("chain-lease-unlinked")
            os.fsync(self._directory)
            if self._boundary is not None:
                self._boundary("chain-lease-parent-fsynced")
            self._released = True
            os.close(self._directory)
            self._directory = -1
        except BaseException:
            raise

    def __enter__(self) -> "ChainLease":
        self._revalidate("use")
        return self

    def __exit__(self, _kind: object, _value: object, _traceback: object) -> None:
        self.release()


def _lease_exclusion_is_current(
    exclusion: CommonRebaseLock | RecoveryReservation | None,
    chain_id: str,
) -> bool:
    if isinstance(exclusion, CommonRebaseLock):
        try:
            exclusion.assert_held(allow_fence=True)
        except OSError:
            return False
        owner = exclusion.owner.record
        return owner.get("owner_kind") == "merge" and owner.get("chain_id") == chain_id
    if isinstance(exclusion, RecoveryReservation):
        if not exclusion.matches_chain(chain_id):
            return False
        try:
            exclusion.assert_current("chain lease recovery exclusion")
            return True
        except (OSError, TimeoutError, ValueError):
            return False
    return False


def _lease_reclaim_authority_is_current(
    exclusion: CommonRebaseLock | RecoveryReservation | None,
    chain_id: str,
) -> bool:
    """Require bare-recover authority, not merely an ordinary held lock."""

    if isinstance(exclusion, RecoveryReservation):
        return _lease_exclusion_is_current(exclusion, chain_id)
    if isinstance(exclusion, CommonRebaseLock):
        return bool(
            exclusion.owner.record.get("operation") == "recover"
            and _lease_exclusion_is_current(exclusion, chain_id)
        )
    return False


def _repository_recovery_reservation_present(chains_dir: Path) -> bool:
    """Observe only the repository-wide reservation name from a lease path."""

    try:
        (chains_dir.parent.parent / COMMON_LOCK_RECOVERY_NAME).lstat()
    except FileNotFoundError:
        return False
    return True


def _reconcile_merge_projection_for_lease_reclaim(
    chains_dir: Path,
    chain_id: str,
    *,
    exclusion: CommonRebaseLock | RecoveryReservation,
    repair_with: ChainLease | None,
    deadline: float,
    clock: Callable[[], float],
    sleeper: Callable[[float], None],
) -> None:
    """Authenticate event truth and repair only after the new lease exists."""

    events_path = chains_dir / f"{chain_id}.events.jsonl"
    state_path = chains_dir / f"{chain_id}.json"
    try:
        events_path.lstat()
        events_exists = True
    except FileNotFoundError:
        events_exists = False
    try:
        state_path.lstat()
        state_exists = True
    except FileNotFoundError:
        state_exists = False
    if not events_exists and not state_exists:
        # Low-level lock-mechanism tests deliberately have no transaction.
        if (
            isinstance(exclusion, CommonRebaseLock)
            and exclusion._no_transaction_record
        ):
            return
        raise FrozenError(
            "stale merge lease lacks event/state evidence for reconciliation",
            chain_id=chain_id,
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    common_root = chains_dir.parent.parent
    store = MergeChainStore(common_root)
    if Path(os.path.realpath(store.root)) != chains_dir:
        raise FrozenError(
            "stale merge lease storage identity is not canonical",
            chain_id=chain_id,
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    with store.event_lock(
        chain_id,
        deadline=deadline,
        clock=clock,
        sleeper=sleeper,
    ):
        replay = store._read_replay_locked(chain_id)
        status, _raw = store._projection_status(replay)
        if status not in {"current", "stale", "missing"}:
            raise FrozenError(
                "stale merge lease projection cannot be reconciled",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        if repair_with is not None and status != "current":
            repair_with.before_state_replace()
            store._atomic_state(replay.state)
            store._boundary("merge-replay-state-replaced")
            replay = store._read_replay_locked(chain_id)
            if store._projection_status(replay)[0] != "current":
                raise FrozenError(
                    "stale merge lease projection repair did not stabilize",
                    chain_id=chain_id,
                    schema=REVISION9_OUTPUT_SCHEMA,
                )


def acquire_chain_lease(
    chains_dir: Path,
    *,
    chain_id: str,
    session: str,
    timeout: float = COMMON_LOCK_TIMEOUT_SECONDS,
    exclusion: CommonRebaseLock | RecoveryReservation | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
    now: Callable[[], dt.datetime] = runtime.utc_now,
    host: str | None = None,
    pid: int | None = None,
    pid_probe: Callable[[int], str] = _process_probe,
    boundary: Callable[[str], None] | None = None,
    single_attempt: bool = False,
) -> ChainLease:
    """Acquire one FR-237 lease, reclaiming only under repository exclusion."""

    _require_common_lock_control("chain-lease-hardlink")
    _require_common_lock_control("single-deadline")
    if not CHAIN_ID_RE.fullmatch(chain_id):
        raise ValueError("invalid chain identifier for lease")
    if not isinstance(session, str) or not session or "\x00" in session:
        raise ValueError("chain lease session must be nonempty and NUL-free")
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError("chain lease timeout must be positive")
    if type(single_attempt) is not bool:
        raise ValueError("chain lease single-attempt selector must be boolean")
    canonical, directory = _open_owned_directory(chains_dir)
    local_host = host or socket.gethostname()
    claimant_pid = pid or os.getpid()
    record = _validate_chain_lease_record(
        {
            "chain_id": chain_id,
            "host": local_host,
            "nonce": secrets.token_hex(16),
            "pid": claimant_pid,
            "session": session,
            "started_at": iso_z(now()),
        }
    )
    path = canonical / f"{chain_id}.lock"
    if isinstance(exclusion, RecoveryReservation):
        if exclusion.affected_merge_chain() != chain_id:
            raise ValueError(
                "recovery reservation does not bind the requested chain lease"
            )
        clock = exclusion.clock
        sleeper = exclusion.sleeper
        deadline = exclusion.deadline
        exclusion.assert_current("chain lease acquisition")
    else:
        deadline = clock() + float(timeout)
    last_evidence: dict[str, Any] = {"path": str(path)}
    reclaimed_stale = False
    try:
        while True:
            if clock() >= deadline:
                raise ChainLeaseUnavailable(chain_id, last_evidence)
            existing: PublishedLockRecord | None
            try:
                existing = _record_at_if_present(
                    directory, path.name, path, _validate_chain_lease_record
                )
            except (OSError, ValueError) as exc:
                existing = None
                last_evidence = {
                    "lease": _opaque_path_evidence_at(directory, path.name, path),
                    "detail": f"lease is malformed or unreadable: {exc}",
                }
                if single_attempt:
                    raise ChainLeaseUnavailable(chain_id, last_evidence) from exc
                if not _sleep_with_deadline(deadline, clock, sleeper):
                    raise ChainLeaseUnavailable(chain_id, last_evidence)
                continue
            if existing is not None:
                last_evidence = {"lease": existing.evidence()}
                stale = (
                    existing.record.get("host") == local_host
                    and pid_probe(int(existing.record["pid"])) == "dead"
                )
                if stale and _lease_reclaim_authority_is_current(
                    exclusion, chain_id
                ):
                    _require_common_lock_control("death-proof-revalidation")
                    if pid_probe(int(existing.record["pid"])) != "dead":
                        last_evidence["detail"] = "lease PID death could not be re-proved"
                    else:
                        assert exclusion is not None
                        _reconcile_merge_projection_for_lease_reclaim(
                            canonical,
                            chain_id,
                            exclusion=exclusion,
                            repair_with=None,
                            deadline=deadline,
                            clock=clock,
                            sleeper=sleeper,
                        )
                        if not _lease_exclusion_is_current(exclusion, chain_id):
                            raise OSError(
                                "repository exclusion changed during stale lease reconciliation"
                            )
                        if pid_probe(int(existing.record["pid"])) != "dead":
                            raise OSError(
                                "lease PID death changed after reconciliation"
                            )
                        _unlink_revalidated_record_at(
                            directory,
                            path.name,
                            path,
                            existing,
                            _validate_chain_lease_record,
                        )
                        os.fsync(directory)
                        if boundary is not None:
                            boundary("chain-lease-stale-reclaimed")
                        reclaimed_stale = True
                        continue
                else:
                    last_evidence["detail"] = (
                        "lease owner is live/foreign/unprovable or repository exclusion is absent"
                    )
                if single_attempt:
                    raise ChainLeaseUnavailable(chain_id, last_evidence)
                if not _sleep_with_deadline(deadline, clock, sleeper):
                    raise ChainLeaseUnavailable(chain_id, last_evidence)
                continue
            if exclusion is not None and not _lease_exclusion_is_current(
                exclusion, chain_id
            ):
                raise OSError(
                    "repository exclusion changed before chain lease publication"
                )
            if exclusion is None and _repository_recovery_reservation_present(
                canonical
            ):
                last_evidence["detail"] = (
                    "repository recovery reservation excludes ordinary lease publication"
                )
                if single_attempt:
                    raise ChainLeaseUnavailable(chain_id, last_evidence)
                if not _sleep_with_deadline(deadline, clock, sleeper):
                    raise ChainLeaseUnavailable(chain_id, last_evidence)
                continue
            temporary, temporary_identity = _create_private_record_at(
                directory,
                canonical,
                f"{chain_id}.lock",
                record,
                boundary=boundary,
                stage="chain-lease-temp-fsynced",
            )
            try:
                try:
                    if exclusion is not None and not _lease_exclusion_is_current(
                        exclusion, chain_id
                    ):
                        raise OSError(
                            "repository exclusion changed before chain lease publication"
                        )
                    if (
                        exclusion is None
                        and _repository_recovery_reservation_present(canonical)
                    ):
                        raise OSError(
                            "repository recovery reservation appeared before chain lease publication"
                        )
                    _publish_no_replace_link(
                        directory, temporary, directory, path.name
                    )
                except FileExistsError:
                    _unlink_revalidated_record_at(
                        directory,
                        temporary,
                        canonical / temporary,
                        temporary_identity,
                        _validate_chain_lease_record,
                    )
                    os.fsync(directory)
                    if single_attempt:
                        raise ChainLeaseUnavailable(chain_id, last_evidence)
                    if not _sleep_with_deadline(deadline, clock, sleeper):
                        raise ChainLeaseUnavailable(chain_id, last_evidence)
                    continue
                os.fsync(directory)
                canonical_identity = _read_owned_record_at(
                    directory,
                    path.name,
                    path,
                    _validate_chain_lease_record,
                )
                if not _same_published_record(canonical_identity, temporary_identity):
                    raise OSError("published chain lease changed inode or digest")
                if boundary is not None:
                    boundary("chain-lease-published")
                _unlink_revalidated_record_at(
                    directory,
                    temporary,
                    canonical / temporary,
                    temporary_identity,
                    _validate_chain_lease_record,
                )
                os.fsync(directory)
                if boundary is not None:
                    boundary("chain-lease-temp-unlinked")
                acquired = ChainLease(
                    chains_dir=canonical,
                    directory_descriptor=directory,
                    identity=canonical_identity,
                    boundary=boundary,
                    exclusion=exclusion,
                )
                if reclaimed_stale:
                    _reconcile_merge_projection_for_lease_reclaim(
                        canonical,
                        chain_id,
                        exclusion=exclusion,
                        repair_with=acquired,
                        deadline=deadline,
                        clock=clock,
                        sleeper=sleeper,
                    )
                return acquired
            except BaseException as exc:
                if isinstance(exc, (CommonLockBoundaryCrash, ChainLeaseUnavailable)):
                    raise
                try:
                    os.unlink(temporary, dir_fd=directory)
                    os.fsync(directory)
                except (FileNotFoundError, OSError):
                    pass
                raise
    except BaseException:
        os.close(directory)
        raise


def _publish_fence(
    lock: CommonRebaseLock,
    record: Mapping[str, Any],
) -> PublishedLockRecord:
    temporary, temporary_identity = _create_private_record_at(
        lock._common,
        lock.common_dir,
        "agent-rebase.inflight",
        record,
        boundary=lock._boundary,
        stage="fence-temp-fsynced",
    )
    link_created = False
    try:
        _publish_no_replace_link(
            lock._common,
            temporary,
            lock._common,
            COMMON_LOCK_INFLIGHT_NAME,
        )
        link_created = True
        os.fsync(lock._common)
        observed = _read_owned_record_at(
            lock._common,
            COMMON_LOCK_INFLIGHT_NAME,
            lock.common_dir / COMMON_LOCK_INFLIGHT_NAME,
            _validate_fence_record,
        )
        if not _same_published_record(observed, temporary_identity):
            raise OSError("published fence changed inode or digest")
        lock._emit_boundary("fence-published")
        _unlink_revalidated_record_at(
            lock._common,
            temporary,
            lock.common_dir / temporary,
            temporary_identity,
            _validate_fence_record,
        )
        os.fsync(lock._common)
        lock._emit_boundary("fence-temp-unlinked")
        return observed
    except BaseException as exc:
        if isinstance(exc, CommonLockBoundaryCrash):
            raise
        cleanup_errors: list[str] = []
        removed_name = False
        if link_created:
            try:
                _unlink_revalidated_record_at(
                    lock._common,
                    COMMON_LOCK_INFLIGHT_NAME,
                    lock.common_dir / COMMON_LOCK_INFLIGHT_NAME,
                    temporary_identity,
                    _validate_fence_record,
                )
                removed_name = True
            except FileNotFoundError:
                pass
            except (OSError, ValueError) as cleanup_error:
                cleanup_errors.append(f"canonical: {cleanup_error}")
        try:
            _unlink_revalidated_record_at(
                lock._common,
                temporary,
                lock.common_dir / temporary,
                temporary_identity,
                _validate_fence_record,
            )
            removed_name = True
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as cleanup_error:
            cleanup_errors.append(f"temporary: {cleanup_error}")
        if removed_name:
            try:
                os.fsync(lock._common)
            except OSError as cleanup_error:
                cleanup_errors.append(f"directory fsync: {cleanup_error}")
        if cleanup_errors:
            raise _PublicationCleanupFailure(
                "fence publication cleanup could not prove durable removal: "
                + "; ".join(cleanup_errors)
            ) from exc
        raise


def run_fenced_command(
    lock: CommonRebaseLock,
    *,
    operation: str,
    intent_digest: str,
    intent_validator: Callable[[], bool],
    argv: Sequence[str],
    cwd: Path,
    persist_result: Callable[[FencedProcessResult], Any],
    env: Mapping[str, str] | None = None,
    timeout: float = runtime.COMMAND_TIMEOUT_SECONDS,
    cap: int = runtime.OUTPUT_CAP_BYTES,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
    group_probe: Callable[[int], str] | None = None,
    signal_group: Callable[[int, int], Any] = os.killpg,
    verbose: bool = False,
    result_transform: (
        Callable[[FencedProcessResult], FencedProcessResult] | None
    ) = None,
) -> FencedProcessResult:
    """Authorize exactly one child through FR-236's durable start-pipe fence."""

    _require_common_lock_control("fence-start-pipe")
    _require_common_lock_control("fence-intent-revalidation")
    _require_common_lock_control("fence-result-before-release")
    if operation not in COMMON_LOCK_FENCE_OPERATIONS:
        raise ValueError("invalid fenced operation")
    if operation == "attribution-observation" and lock.owner.record["owner_kind"] != "push":
        raise ValueError("attribution observation requires standalone push ownership")
    if lock.owner.record["owner_kind"] not in {"merge", "push"}:
        raise ValueError("phase5 ownership cannot publish an FR-236 fence")
    if not SHA256_RE.fullmatch(intent_digest):
        raise ValueError("fenced intent digest must be a lowercase SHA-256")
    if (
        not callable(intent_validator)
        or not callable(persist_result)
        or (result_transform is not None and not callable(result_transform))
    ):
        raise ValueError("fenced command requires intent and result persistence callbacks")
    if (
        not isinstance(timeout, (int, float))
        or timeout <= 0
        or cap <= 0
        or cap > runtime.OUTPUT_CAP_BYTES
    ):
        raise ValueError(
            "fenced timeout must be positive and output cap must be within the fixed maximum"
        )
    lock.assert_held()
    if not intent_validator():
        raise CommonLockUnavailable(
            {
                "common_dir": str(lock.common_dir),
                "detail": "durable operation intent did not validate before child fork",
            }
        )
    probe = group_probe or lock._group_probe
    child: _BlockedFenceChild | None = None
    fence: PublishedLockRecord | None = None
    authorized = False
    fence_ack_window = min(
        max(float(timeout), FENCED_CHILD_ACK_TIMEOUT_SECONDS),
        COMMON_LOCK_TIMEOUT_SECONDS,
    )
    publication_deadline = lock._clock() + COMMON_LOCK_TIMEOUT_SECONDS
    fence_ack_deadline = min(
        publication_deadline,
        lock._clock() + fence_ack_window,
    )
    try:
        while True:
            try:
                child = _spawn_blocked_fence_child(
                    argv,
                    cwd=Path(cwd),
                    env=env,
                    deadline=fence_ack_deadline,
                    clock=lock._clock,
                    sleeper=lock._sleeper,
                )
            except ChildProcessError as exc:
                raise CommonLockUnavailable(
                    {
                        "common_dir": str(lock.common_dir),
                        "detail": "blocked child could not be reaped after acknowledgement failure",
                        "error": str(exc),
                    }
                ) from exc
            except OSError as exc:
                if not _sleep_with_deadline(
                    publication_deadline, lock._clock, lock._sleeper
                ):
                    raise CommonLockUnavailable(
                        {
                            "common_dir": str(lock.common_dir),
                            "detail": "blocked-child acknowledgement exhausted the fence-publication retry deadline",
                            "error": str(exc),
                        }
                    ) from exc
                fence_ack_deadline = min(
                    publication_deadline,
                    lock._clock() + fence_ack_window,
                )
                lock.assert_held(allow_fence=True)
                continue
            lock._emit_boundary("fence-child-blocked")
            record = _validate_fence_record(
                {
                    "schema": "forge-rebase-inflight/1",
                    "owner_kind": lock.owner.record["owner_kind"],
                    "chain_id": lock.owner.record["chain_id"],
                    "operation": operation,
                    "host": lock.owner.record["host"],
                    "pid": child.pid,
                    "pgid": child.pgid,
                    "started_at": iso_z(),
                    "intent_digest": intent_digest,
                    "nonce": secrets.token_hex(16),
                }
            )
            try:
                fence = _publish_fence(lock, record)
                break
            except _PublicationCleanupFailure as exc:
                stopped = _stop_unstarted_child(
                    child,
                    clock=lock._clock,
                    sleeper=lock._sleeper,
                )
                child = None
                if not stopped:
                    detail = "publication cleanup and blocked-child reap both failed"
                else:
                    detail = "fence publication cleanup could not prove durable removal"
                raise CommonLockUnavailable(
                    {
                        "common_dir": str(lock.common_dir),
                        "detail": detail,
                        "error": str(exc),
                    }
                ) from exc
            except (OSError, ValueError) as exc:
                stopped = _stop_unstarted_child(
                    child,
                    clock=lock._clock,
                    sleeper=lock._sleeper,
                )
                child = None
                if not stopped:
                    raise CommonLockUnavailable(
                        {
                            "common_dir": str(lock.common_dir),
                            "detail": "blocked child could not be reaped after failed fence publication",
                        }
                    )
                if not _sleep_with_deadline(
                    publication_deadline, lock._clock, lock._sleeper
                ):
                    detail = (
                        "existing in-flight fence exhausted the fence-publication deadline"
                        if isinstance(exc, FileExistsError)
                        else "incomplete fence publication exhausted the fence-publication deadline"
                    )
                    raise CommonLockUnavailable(
                        {
                            "common_dir": str(lock.common_dir),
                            "detail": detail,
                            "error": str(exc),
                        }
                    )
                fence_ack_deadline = min(
                    publication_deadline,
                    lock._clock() + fence_ack_window,
                )
                lock.assert_held(allow_fence=True)
        lock.assert_held(allow_fence=True)
        assert child is not None and fence is not None
        _revalidate_record_at(
            lock._common,
            COMMON_LOCK_INFLIGHT_NAME,
            lock.common_dir / COMMON_LOCK_INFLIGHT_NAME,
            fence,
            _validate_fence_record,
        )
        if not intent_validator():
            stopped = _stop_unstarted_child(
                child,
                clock=lock._clock,
                sleeper=lock._sleeper,
            )
            child = None
            if not stopped:
                lock._unresolved_fence = fence
                raise CommonLockUnavailable(
                    {
                        "common_dir": str(lock.common_dir),
                        "detail": "blocked child could not be reaped after intent revalidation failed",
                    }
                )
            _unlink_revalidated_record_at(
                lock._common,
                COMMON_LOCK_INFLIGHT_NAME,
                lock.common_dir / COMMON_LOCK_INFLIGHT_NAME,
                fence,
                _validate_fence_record,
            )
            os.fsync(lock._common)
            fence = None
            raise CommonLockUnavailable(
                {
                    "common_dir": str(lock.common_dir),
                    "detail": "durable operation intent changed before the start byte",
                }
            )
        lock._emit_boundary("fence-before-authorization")
        os.write(child.start_descriptor, b"\x01")
        os.close(child.start_descriptor)
        child.start_descriptor = -1
        authorized = True
        lock._emit_boundary("fence-after-authorization")
        started = clock()
        (
            returncode,
            output,
            output_digest,
            timed_out,
            output_limit,
            launch_failed,
            group_survived,
        ) = _collect_fenced_child(
            child,
            argv=argv,
            started=started,
            timeout=float(timeout),
            cap=cap,
            clock=clock,
            sleeper=sleeper,
            group_probe=probe,
            signal_group=signal_group,
            verbose=verbose,
        )
        child = None
        result = FencedProcessResult(
            argv=list(argv),
            returncode=returncode,
            duration_seconds=clock() - started,
            output=output,
            output_digest=output_digest,
            timed_out=timed_out,
            output_limit=output_limit,
            launch_failed=launch_failed,
            group_survived=group_survived,
            authorized=authorized,
            fence_digest=fence.digest,
            fence_inode=fence.inode,
        )
        if result_transform is not None:
            result = result_transform(result)
            if not isinstance(result, FencedProcessResult):
                raise TypeError("fenced result transform returned a malformed result")
        # The collection loop's final probe and result transformation precede
        # the durable callback.  Re-prove group death once more here so the
        # persisted envelope can never claim ``group_survived=false`` and then
        # be contradicted by the pre-unlink probe.
        if result.group_survived or probe(int(fence.record["pgid"])) != "dead":
            result = dataclasses.replace(result, group_survived=True)
        lock._emit_boundary("fence-before-result")
        persist_result(result)
        lock._emit_boundary("fence-result-persisted")
        if result.group_survived:
            lock._unresolved_fence = fence
            raise FencedChildSurvived(result)
        if probe(int(fence.record["pgid"])) != "dead":
            lock._unresolved_fence = fence
            raise FencedChildSurvived(dataclasses.replace(result, group_survived=True))
        try:
            _unlink_revalidated_record_at(
                lock._common,
                COMMON_LOCK_INFLIGHT_NAME,
                lock.common_dir / COMMON_LOCK_INFLIGHT_NAME,
                fence,
                _validate_fence_record,
            )
            os.fsync(lock._common)
            lock._emit_boundary("fence-released")
        except (OSError, ValueError) as exc:
            lock._unresolved_fence = fence
            lock._release_pending = True
            raise CommonLockReleaseFailure(
                {
                    "path": str(lock.common_dir / COMMON_LOCK_INFLIGHT_NAME),
                    "inode": fence.inode,
                    "digest": fence.digest,
                    "error": str(exc),
                }
            ) from exc
        return result
    except BaseException as exc:
        if isinstance(exc, CommonLockBoundaryCrash):
            raise
        if child is not None:
            if child.start_descriptor >= 0 and not authorized:
                stopped = _stop_unstarted_child(
                    child,
                    clock=lock._clock,
                    sleeper=lock._sleeper,
                )
                if not stopped:
                    if fence is not None:
                        lock._unresolved_fence = fence
                    raise CommonLockUnavailable(
                        {
                            "common_dir": str(lock.common_dir),
                            "detail": "blocked child could not be reaped during failure cleanup",
                        }
                    ) from exc
            else:
                try:
                    _terminate_fenced_group(
                        child,
                        signal_group=signal_group,
                        group_probe=probe,
                        clock=clock,
                        sleeper=sleeper,
                    )
                finally:
                    for descriptor in (
                        child.output_descriptor,
                        child.exec_error_descriptor,
                    ):
                        try:
                            os.close(descriptor)
                        except OSError:
                            pass
        if fence is not None and not isinstance(
            exc, (FencedChildSurvived, CommonLockReleaseFailure)
        ):
            # Once authorization may have occurred, an absent durable result
            # is a recovery fact: retain the fence for observation.  Before
            # authorization, ordinary validation/publication failures may
            # release the proven fence after the blocked child exits.
            if authorized:
                lock._unresolved_fence = fence
        raise


def hold_common_lock(
    repository: Repository,
    *,
    owner_kind: str,
    chain_id: str | None,
    operation: str,
    ready_fd: int,
    input_stream: Any | None = None,
) -> Outcome:
    """Long-lived wrapper protocol for future non-Python lock consumers.

    The caller supplies a writable descriptor numbered three or higher.  Once
    the complete common lock is held, the wrapper writes exactly one canonical
    LF-terminated ``forge-common-lock-ready/1`` record there.  It then accepts
    exactly one stdin frame, the eight bytes ``release\n``, and closes stdin.
    Only after the
    reverse-order release completes does stdout receive the ordinary single
    ``forge-cli/2`` outcome from ``main``.
    """

    if not isinstance(ready_fd, int) or isinstance(ready_fd, bool) or ready_fd < 3:
        raise Refusal(
            V2ReasonCode.STATE_PRECONDITION,
            "forge: common-lock hold refused — --ready-fd must name a writable inherited descriptor >= 3",
            expected="one writable inherited readiness descriptor numbered 3 or higher",
            observed=str(ready_fd),
            remediation="open a dedicated readiness pipe and retry common-lock hold",
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    try:
        os.fstat(ready_fd)
        os.write(ready_fd, b"")
    except OSError as exc:
        raise Refusal(
            V2ReasonCode.STATE_PRECONDITION,
            "forge: common-lock hold refused — readiness descriptor is unavailable",
            expected="a writable inherited readiness descriptor",
            observed=str(exc),
            remediation="open a dedicated readiness pipe and retry common-lock hold",
            schema=REVISION9_OUTPUT_SCHEMA,
        ) from exc
    try:
        lock = acquire_common_lock(
            repository.git_common_dir(),
            owner_kind=owner_kind,
            chain_id=chain_id,
            operation=operation,
            # This dormant physical-lock wrapper has no transaction store.
            # Consuming merge/push verbs must replace this explicit opt-out
            # with their synchronous transaction recorder before activation.
            no_transaction_record=owner_kind in {"merge", "push"},
        )
    except ValueError as exc:
        raise Refusal(
            V2ReasonCode.STATE_PRECONDITION,
            "forge: common-lock hold refused — owner tuple is invalid",
            expected="an FR-235 owner-kind, chain-id, and operation tuple",
            observed=str(exc),
            remediation="supply the exact owner tuple for the calling Forge operation",
            schema=REVISION9_OUTPUT_SCHEMA,
        ) from exc
    protocol_error: Refusal | None = None
    try:
        ready = {
            "schema": "forge-common-lock-ready/1",
            "owner_digest": lock.digest,
            "nonce": lock.owner.record["nonce"],
            "pid": lock.owner.record["pid"],
        }
        try:
            _write_all(ready_fd, canonical_bytes(ready) + b"\n")
        except OSError as exc:
            protocol_error = Refusal(
                V2ReasonCode.STATE_PRECONDITION,
                "forge: common-lock hold refused — readiness acknowledgement failed",
                expected="one complete readiness record",
                observed=str(exc),
                remediation="repair the readiness pipe and retry common-lock hold",
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        if protocol_error is None:
            stream = input_stream if input_stream is not None else sys.stdin.buffer
            try:
                frame = stream.readline(129)
                trailing = stream.read(1) if frame == b"release\n" else b""
            except (OSError, ValueError) as exc:
                frame = b""
                trailing = b""
                protocol_error = Refusal(
                    V2ReasonCode.STATE_PRECONDITION,
                    "forge: common-lock hold refused — release frame could not be read",
                    observed=str(exc),
                    remediation="send exactly release followed by LF on stdin",
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            if protocol_error is None and (frame != b"release\n" or trailing != b""):
                protocol_error = Refusal(
                    V2ReasonCode.STATE_PRECONDITION,
                    "forge: common-lock hold refused — invalid release frame",
                    expected="the exact stdin bytes release followed by LF",
                    observed=repr(frame + trailing),
                    remediation="send exactly release followed by LF on stdin",
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
    finally:
        lock.release()
    if protocol_error is not None:
        raise protocol_error
    return Outcome(
        ok=True,
        reason_code=V2ReasonCode.OK,
        message="forge: common rebase lock released",
        chain_id=chain_id,
        next_required_step="none — common rebase lock released",
        evidence_refs=(
            str(lock.common_dir / COMMON_LOCK_INTENT_NAME),
        ),
        schema=REVISION9_OUTPUT_SCHEMA,
    )


@dataclasses.dataclass
class CLIOptions:
    json: bool = False
    verbose: bool = False
    chain_id: str | None = None
    repo: str | None = None
    run_id: str | None = None
    original_argv: tuple[str, ...] = ()
    revision9_face: bool = False


@dataclasses.dataclass
class CommandContext:
    repo: Repository
    store: ChainStore
    options: CLIOptions
    policy: Policy | None = None

    def scripts_dir(self) -> Path:
        plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
        if plugin_root:
            return (Path(plugin_root).resolve() / "scripts" / "forge")
        return runtime.SCRIPT_DIR

    def plugin_root(self) -> Path:
        plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
        if plugin_root:
            return Path(plugin_root).resolve()
        return runtime.PLUGIN_ROOT

    def helper(self, name: str) -> Path:
        return self.scripts_dir() / name

    def command_digest(self, argv: Sequence[str]) -> str:
        return sha256_bytes(canonical_bytes(list(argv)))

    def validate_run_id(self) -> Path | None:
        if self.options.run_id is None:
            return None
        candidates = [
            self.repo.root / ".codex-orchestrator" / "runs" / self.options.run_id,
            self.store.common_root
            / ".codex-orchestrator"
            / "runs"
            / self.options.run_id,
        ]
        for candidate in candidates:
            resolved = Path(os.path.realpath(candidate))
            if resolved.is_dir():
                for allowed in (self.repo.root, self.store.common_root):
                    try:
                        resolved.relative_to(Path(os.path.realpath(allowed)))
                        return resolved
                    except ValueError:
                        continue
        raise Refusal(
            ReasonCode.CITATION_OUT_OF_ROOT,
            f"explicit run id does not resolve to a repository-contained run: {self.options.run_id}",
            expected="an existing .codex-orchestrator/runs/<run-id> directory",
            observed=self.options.run_id,
            remediation="rerun without --run-id or pass the exact open run id",
        )


def _policy_for_state(ctx: CommandContext, state: Mapping[str, Any]) -> Policy:
    sha = str(state["policy_source"].get("sha", ""))
    try:
        resolved, raw = ctx.repo.policy(sha)
        policy = parse_policy(resolved, raw)
    except (OSError, PolicyError, UnicodeError) as exc:
        raise Refusal(
            ReasonCode.POLICY_UNREADABLE,
            f"committed policy is unreadable while loading chain: {exc}",
            expected=f"git show {sha}:forge-project.md",
            observed=str(exc),
            remediation="restore readable committed policy, then abort and restart the chain",
            chain=state,
        ) from exc
    if policy.digest != state["policy_source"].get("digest"):
        raise FrozenError(
            "pinned committed policy digest no longer matches its Git object",
            chain_id=str(state["chain_id"]),
            state=str(state["state"]),
        )
    ctx.policy = policy
    return policy


def _validate_bound_chain_state(state: Mapping[str, Any]) -> None:
    """Re-prove a bound chain against current journal and committed policy."""

    binding = state.get("run_binding")
    if not isinstance(binding, Mapping):
        return
    batch, _builders, journal = runtime._coordination_modules()
    repository = Path(str(binding.get("repository", "")))
    run_id = str(binding.get("run_id", ""))
    task_id = str(binding.get("task_id", ""))
    try:
        canonical_repository, state_root = journal._resolve_repository(
            repository, "chain binding"
        )
        run_dir = state_root / ".codex-orchestrator" / "runs" / run_id
        with batch.batch_lock(run_dir, create=False):
            run_state = journal._scan_run(run_dir)
            opening = run_state.records[0] if run_state.records else None
            if (
                run_state.disposition != "open"
                or not isinstance(opening, dict)
                or Path(str(opening.get("repo", ""))).resolve(strict=True)
                != canonical_repository
            ):
                raise ValueError("run is terminal or belongs to another repository")
            tasks = [
                record
                for record in run_state.records
                if record.get("type") == "task" and record.get("id") == task_id
            ]
            if not tasks or tasks[-1].get("status") != "active":
                raise ValueError("bound task is not active")
            files = tasks[-1].get("files")
            if not isinstance(files, list) or not files:
                raise ValueError("bound task files are malformed")
            policy_source = state.get("policy_source")
            if not isinstance(policy_source, Mapping):
                raise ValueError("chain policy source is malformed")
            policy = subprocess.run(
                [
                    "git",
                    "-C",
                    str(canonical_repository),
                    "show",
                    f"{policy_source.get('sha')}:forge-project.md",
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            if (
                policy.returncode != 0
                or sha256_bytes(policy.stdout) != policy_source.get("digest")
                or policy_source.get("digest") != binding.get("policy_digest")
            ):
                raise ValueError("committed policy identity changed")
            try:
                parsed_policy = parse_policy(
                    str(policy_source.get("sha")), policy.stdout
                )
                mechanical_outputs = _committed_changelog_output_paths(
                    parsed_policy
                )
            except (PolicyError, UnicodeError) as exc:
                raise ValueError("committed policy is malformed") from exc
            for path in state.get("paths", ()):
                if path in mechanical_outputs:
                    continue
                if not isinstance(path, str) or not any(
                    journal.pathspec_contained(path, pattern)
                    for pattern in files
                    if isinstance(pattern, str)
                ):
                    raise ValueError(
                        f"chain path {path} is outside bound task membership"
                    )
                if not any(
                    journal.pathspec_contained(path, admitted)
                    for admitted in run_state.scope
                ):
                    raise ValueError(
                        f"chain path {path} is outside admitted run scope"
                    )
    except (OSError, RuntimeError, ValueError, journal.CoordinationRefusal) as exc:
        raise Refusal(
            V2ReasonCode.RUN_TASK_BINDING_INVALID,
            "forge: chain transition refused — run/task binding is invalid",
            expected="open run, active task, matching repository/scope/policy binding",
            observed=str(exc),
            remediation=_forge_command(state, "status"),
            chain=state,
        ) from exc


def _latest_current_pass(state: Mapping[str, Any], step_id: str) -> bool:
    value = state["steps"].get(step_id)
    candidate = state["candidate"].get("sha256")
    if isinstance(value, list) and value:
        record = value[-1]
        return record.get("candidate") == candidate and record.get("result") == "passed"
    return False


def _user_skip(state: Mapping[str, Any], gate_id: str) -> dict[str, Any] | None:
    value = state["steps"].get("user_skips", {})
    if not isinstance(value, dict):
        return None
    record = value.get(gate_id)
    return record if isinstance(record, dict) else None


def _gate_satisfied(state: Mapping[str, Any], gate_id: str) -> bool:
    # Recorded-baseline integrity is mandatory for control candidates.  Keep
    # the legacy generic skip behavior only where this gate is not a binding
    # control-class requirement.
    if gate_id == "strict-evals" and bool(state.get("tier", {}).get("control")):
        return _latest_current_pass(state, gate_id)
    if _user_skip(state, gate_id) is not None:
        return True
    # Without an explicit operator skip, the fresh-reviewer gate retains its
    # stronger candidate/request/manifest validation instead of falling back
    # to the generic latest-process-result predicate.
    if gate_id == FRESH_REVIEWER_EVALS_GATE:
        try:
            return fresh_eval_module.current_step_satisfied(
                state,
                expected_candidate=str(state["candidate"].get("sha256") or ""),
            )
        except (KeyError, TypeError, fresh_eval_module.FreshEvalError):
            return False
    if gate_id.startswith("stack:"):
        runs = state["steps"].get(gate_id)
        if not isinstance(runs, list) or not runs:
            return False
        latest = runs[-1]
        batch_id = latest.get("batch_id")
        count = latest.get("cell_count")
        if not isinstance(batch_id, str) or not isinstance(count, int) or count < 1:
            return False
        batch = [record for record in runs if record.get("batch_id") == batch_id]
        return (
            len(batch) == count
            and {record.get("cell_index") for record in batch} == set(range(1, count + 1))
            and all(
                record.get("candidate") == state["candidate"].get("sha256")
                and record.get("result") == "passed"
                for record in batch
            )
        )
    return _latest_current_pass(state, gate_id)


def _fresh_reviewer_evals_required(
    ctx: CommandContext, state: Mapping[str, Any]
) -> bool:
    """Derive fresh-eval applicability from the pinned base policy and tree pair.

    A malformed/unreadable trigger derivation remains required for a control
    candidate so the dedicated gate can surface its exit-2 INVALID result.  It
    must never degrade into an untriggered fast path.
    """

    if not bool(state.get("tier", {}).get("control")):
        return False
    policy = ctx.policy or _policy_for_state(ctx, state)
    try:
        trigger = fresh_eval_module.derive_trigger(
            ctx.repo.candidate_context(),
            policy,
            state["candidate"],
            tuple(str(path) for path in state.get("paths", ())),
        )
    except (KeyError, TypeError, fresh_eval_module.FreshEvalError):
        return True
    return fresh_eval_module.trigger_required(trigger)


def _required_steps(ctx: CommandContext, state: Mapping[str, Any]) -> list[str]:
    policy = ctx.policy or _policy_for_state(ctx, state)
    result: list[str] = []
    if policy.changelog is not None:
        result.append("changelog")
    result.extend(["gate-1", "gate-1"])
    categories = [str(value) for value in state["tier"].get("categories", [])]
    for category in sorted(set(categories)):
        result.append(f"stack:{category}")
    result.append("assertion-sensor")
    for invariant in policy.invariants:
        if invariant["enforcement"] == "commit":
            result.append(f"invariant:{invariant['row_number']}")
    result.append("secret-scan")
    if state["tier"].get("control"):
        result.append("strict-evals")
        if _fresh_reviewer_evals_required(ctx, state):
            result.append(FRESH_REVIEWER_EVALS_GATE)
    return result


def _gate_one_complete(state: Mapping[str, Any]) -> bool:
    runs = state["steps"].get("gate-1")
    if _user_skip(state, "gate-1") is not None:
        return True
    if not isinstance(runs, list) or len(runs) < 2:
        return False
    candidate = state["candidate"].get("sha256")
    current_runs = [
        record
        for record in runs
        if isinstance(record, dict) and record.get("candidate") == candidate
    ]
    if len(current_runs) < 2:
        return False
    last_two = current_runs[-2:]
    return all(
        record.get("result") == "passed" and not record.get("pair_voided")
        for record in last_two
    ) and last_two[0].get("env_fingerprint") == last_two[1].get("env_fingerprint")


def _prove_merge_run_task_binding(
    repository: Path,
    common_root: Path,
    run_id: str,
    task_id: str,
    policy_digest: str,
    *,
    create_batch_lock: bool = False,
) -> MergeRunTaskSnapshot:
    batch, _builders, journal = runtime._coordination_modules()
    run_dir = common_root / ".codex-orchestrator" / "runs" / run_id
    try:
        with _chain_batch_lock(
            run_dir,
            repository,
            run_id,
            create=create_batch_lock,
        ):
            run_state = journal._scan_run(run_dir)
            opening = run_state.records[0] if run_state.records else None
            if (
                run_state.disposition != "open"
                or not isinstance(opening, dict)
                or Path(str(opening.get("repo", ""))).resolve(strict=True)
                != repository
            ):
                raise ValueError("run is not open for the merge repository")
            tasks = [
                record
                for record in run_state.records
                if record.get("type") == "task" and record.get("id") == task_id
            ]
            if not tasks or tasks[-1].get("status") != "active":
                raise ValueError("task is not active")
            files = tasks[-1].get("files")
            scope = run_state.scope
            if (
                not isinstance(files, list)
                or not files
                or not all(isinstance(value, str) and value for value in files)
                or not isinstance(scope, tuple)
                or not scope
                or not all(isinstance(value, str) and value for value in scope)
            ):
                raise ValueError("task files or admitted scope are malformed")
    except (OSError, RuntimeError, ValueError, journal.CoordinationRefusal) as exc:
        raise _merge_refusal(
            V2ReasonCode.RUN_TASK_BINDING_INVALID,
            "forge: merge start refused — run/task binding is invalid",
            expected="matching repository, active task, immutable scope, and committed policy",
            observed=str(exc),
            remediation="inspect the named run/task and retry the exact paired start",
        ) from exc
    return MergeRunTaskSnapshot(
        binding={
            "run_id": run_id,
            "task_id": task_id,
            "repository": str(repository),
            "policy_digest": policy_digest,
        },
        task_files=tuple(sorted(set(files), key=lambda value: value.encode("utf-8"))),
        admitted_scope=tuple(
            sorted(set(scope), key=lambda value: value.encode("utf-8"))
        ),
    )


__all__ = [
    'CHAIN_ID_RE',
    'CHAIN_TOMBSTONE_EVENT',
    'CHAIN_TOMBSTONE_KEYS',
    'CHAIN_TOMBSTONE_SCHEMA',
    'CLIOptions',
    'COMMIT_RE',
    'COMMON_LOCK_CONTROLS',
    'COMMON_LOCK_DIRECTORY_NAME',
    'COMMON_LOCK_FENCE_OPERATIONS',
    'COMMON_LOCK_FLOCK_NAME',
    'COMMON_LOCK_INFLIGHT_NAME',
    'COMMON_LOCK_INTENT_NAME',
    'COMMON_LOCK_OPERATIONS',
    'COMMON_LOCK_OWNER_KINDS',
    'COMMON_LOCK_OWNER_NAME',
    'COMMON_LOCK_POLL_SECONDS',
    'COMMON_LOCK_RECORD_CAP_BYTES',
    'COMMON_LOCK_RECOVERY_KINDS',
    'COMMON_LOCK_RECOVERY_NAME',
    'COMMON_LOCK_TIMEOUT_SECONDS',
    'ChainLease',
    'ChainLeaseUnavailable',
    'ChainStore',
    'CommandContext',
    'CommonLockBoundaryCrash',
    'CommonLockInspection',
    'CommonLockReleaseFailure',
    'CommonLockUnavailable',
    'CommonRebaseLock',
    'EVENT_KEYS',
    'FENCED_CHILD_ACK_TIMEOUT_SECONDS',
    'FENCED_CHILD_DRAIN_CAP_BYTES',
    'FENCED_CHILD_DRAIN_SECONDS',
    'FENCED_CHILD_REAP_SECONDS',
    'FENCED_CHILD_STOP_GRACE_SECONDS',
    'FRESH_REVIEWER_EVALS_GATE',
    'FRESH_REVIEWER_EVALS_REQUESTED_EVENT',
    'FRESH_REVIEWER_EVALS_REQUESTS',
    'FencedChildSurvived',
    'FencedProcessResult',
    'INACTIVE_SECONDS',
    'INGEST_PROOF_CONTROLS',
    'INGEST_PROOF_ORDER',
    'KIND',
    'MERGE_ADAPTER_CONTROLS',
    'MERGE_CONSEQUENTIAL_EVENTS',
    'MERGE_EVENT_KEYS',
    'MERGE_EVENT_NAMES',
    'MERGE_INTEGRATION_CONTROLS',
    'MERGE_SCOPE_BINDING_CAP_BYTES',
    'MERGE_STATE_KEYS',
    'MERGE_STORE_CONTROLS',
    'MergeChainStore',
    'MergeReplayResult',
    'MergeRunTaskSnapshot',
    'PublishedLockRecord',
    'RUN_ID_RE',
    'RecoveryReservation',
    'Repository',
    'candidate_is_v2',
    '_binding_is_current_with_candidate_v2',
    '_binding_matches_source_fact_with_candidate_v2',
    '_binding_shape_valid_with_candidate_v2',
    '_candidate_binding_for_state_with_candidate_v2',
    '_event_batch_records_with_candidate_v2',
    'SCHEMA',
    'SHA256_RE',
    'STATES',
    'STATE_KEYS',
    'TIER_RANK',
    'ZERO_DIGEST',
    '_BOOTSTRAP_FETCH_OBSERVATION_SCHEMA',
    '_BlockedFenceChild',
    '_CHAIN_LEASE_KEYS',
    '_COMMON_LOCK_FENCE_KEYS',
    '_COMMON_LOCK_OWNER_KEYS',
    '_COMMON_LOCK_RECOVERY_KEYS',
    '_ChainStoragePrimitives',
    '_EPOCH_FETCH_OBSERVATION_SCHEMA',
    '_MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA',
    '_MERGE_CANDIDATE_OBSERVATION_SCHEMA',
    '_MERGE_CLEANUP_CLOSE_SCHEMA',
    '_MERGE_CLEANUP_FENCE_OPERATIONS',
    '_MERGE_CLEANUP_INTENT_SCHEMA',
    '_MERGE_CLEANUP_RECOVERY_SCHEMA',
    '_MERGE_CLEANUP_RESULT_SCHEMA',
    '_MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES',
    '_MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES',
    '_MERGE_REMOTE_ONLY_IDENTITY_FIELDS',
    '_MERGE_SCOPE_OVERLAY',
    '_MERGE_SCOPE_UNSET',
    '_PublicationCleanupFailure',
    '_REQUIRED_COMMON_LOCK_CONTROLS',
    '_REQUIRED_INGEST_PROOF_CONTROLS',
    '_REQUIRED_MERGE_ADAPTER_CONTROLS',
    '_REQUIRED_MERGE_INTEGRATION_CONTROLS',
    '_REQUIRED_MERGE_STORE_CONTROLS',
    '_WORKTREE_LOCKS',
    '_WORKTREE_LOCKS_GUARD',
    '_WORKTREE_LOCK_STATE',
    '_acquire_secondary_flock',
    '_authorize_chain_batch',
    '_bootstrap_fetch_observation_record_valid',
    '_bootstrap_fetch_observation_transition_valid',
    '_build_merge_chain_journal_records',
    '_capture_ingest_blob',
    '_capture_ingest_record_evidence',
    '_capture_run_evidence',
    '_chain_storage_root',
    '_classify_merge_recovery_lifecycle',
    '_clear_owned_reservation',
    '_clear_reserved_fence',
    '_collect_fenced_child',
    '_committed_changelog_output_paths',
    '_common_fence_path_present',
    '_coordination_refusal',
    '_create_private_record_at',
    '_drain_chain_batch_capability',
    '_epoch_ancestry_record_valid',
    '_epoch_fetch_observation_passed',
    '_epoch_fetch_observation_predecessor_valid',
    '_epoch_fetch_observation_record_valid',
    '_epoch_fetch_result_intent_digest',
    '_exclusive_descriptor_lock',
    '_fence_death_proof',
    '_fence_matches_owner',
    '_forge_command',
    '_fresh_reviewer_evals_required',
    '_gate_one_complete',
    '_gate_satisfied',
    '_group_probe',
    '_ingest_captured_paths',
    '_ingest_proof_verifier',
    '_ingest_secret_scan_is_current',
    '_ingest_step_is_current',
    '_inspect_common_lock_fd',
    '_latest_current_pass',
    '_lease_exclusion_is_current',
    '_lease_reclaim_authority_is_current',
    '_merge_attempted_release_preconditions_valid',
    '_merge_bootstrap_classification_pending',
    '_merge_candidate_observation_binding',
    '_merge_candidate_observation_evidence',
    '_merge_candidate_observation_evidence_valid',
    '_merge_candidate_observation_record_valid',
    '_merge_candidate_observation_step_names',
    '_merge_candidate_observation_step_specs',
    '_merge_candidate_observation_transition_valid',
    '_merge_carried_gate_steps',
    '_merge_carry_payload_valid',
    '_merge_cleanup_branch_observation',
    '_merge_cleanup_evidence_history',
    '_merge_cleanup_expected_argv',
    '_merge_cleanup_expected_subject',
    '_merge_cleanup_fetch_head_bytes',
    '_merge_cleanup_history_summary',
    '_merge_cleanup_intent_transition_valid',
    '_merge_cleanup_intent_valid',
    '_merge_cleanup_observation_valid',
    '_merge_cleanup_process_complete',
    '_merge_cleanup_process_output',
    '_merge_cleanup_process_result_valid',
    '_merge_cleanup_result_transition_valid',
    '_merge_cleanup_results_valid',
    '_merge_cleanup_retry_proof_valid',
    '_merge_cleanup_step_result_valid',
    '_merge_cleanup_unmatched_intent',
    '_merge_cleanup_worktree_inventory',
    '_merge_containment',
    '_merge_current_authority_valid',
    '_merge_current_gate_facts',
    '_merge_epoch_valid',
    '_merge_event_outbox',
    '_merge_full_patch_argv',
    '_merge_gate_event_fact',
    '_merge_gate_plan_valid',
    '_merge_gate_step_generation_digests',
    '_merge_history_has_git_mutation_intent',
    '_merge_history_uses_additive_grammar',
    '_merge_inactive_post_attempt_recovery_ready',
    '_merge_ingest_binding',
    '_merge_ingest_record_templates',
    '_merge_ingest_state_shape_valid',
    '_merge_ingest_transition_valid',
    '_merge_latest_contained_attempt',
    '_merge_old_tip_all_false',
    '_merge_payload_delta',
    '_merge_plan_position_fact',
    '_merge_plan_transition_valid',
    '_merge_rebase_action',
    '_merge_rebase_result_classification',
    '_merge_recovery_proof_transition_valid',
    '_merge_refusal',
    '_merge_release_preconditions_valid',
    '_merge_remote_only_equality_proof',
    '_merge_retained_inflight',
    '_merge_revision9_compatibility_view',
    '_merge_scope_argv',
    '_merge_scope_binding_names',
    '_merge_scope_binding_validator',
    '_merge_scope_environment_contract',
    '_merge_scope_event_binding_valid',
    '_merge_scope_transition_valid',
    '_merge_state_shape_valid',
    '_merge_transition_valid',
    '_new_merge_record_is_current',
    '_new_owner_record',
    '_opaque_path_evidence_at',
    '_open_lock_directory',
    '_open_owned_directory',
    '_parse_registered_worktrees',
    '_parsed_run_captured_path',
    '_persist_recovery_proof',
    '_pipe_cloexec',
    '_policy_for_state',
    '_process_probe',
    '_prove_ingest_live_chain',
    '_prove_merge_run_task_binding',
    '_publish_fence',
    '_publish_no_replace_link',
    '_publish_portable_owner',
    '_publish_recovery_reservation',
    '_published_recovery_evidence_valid',
    '_read_child_ack',
    '_read_fence_for_recovery',
    '_read_ingest_input',
    '_read_owned_record_at',
    '_reconcile_merge_projection_for_lease_reclaim',
    '_record_at_if_present',
    '_recover_stale_portable_owner',
    '_recovered_absent_rebase_intent_digest',
    '_recovery_classification_receipt_valid',
    '_recovery_cleanup_intent',
    '_recovery_cleanup_result_matches',
    '_recovery_event_intent',
    '_recovery_record',
    '_recovery_value_carries_inflight',
    '_release_portable_identity',
    '_remote_containment_argv',
    '_remote_containment_evidence_valid',
    '_remote_observation_fetch_argv',
    '_remote_observation_heads',
    '_remote_observation_progress_matches_observed',
    '_remote_observation_progress_transition_valid',
    '_remote_observation_progress_valid',
    '_replay_merge_event_bytes',
    '_replayed_remote_observation_completed',
    '_repository_recovery_reservation_present',
    '_require_common_lock_control',
    '_require_deadline_open',
    '_require_ingest_proof',
    '_require_merge_adapter_control',
    '_require_merge_integration_control',
    '_require_merge_store_control',
    '_require_recovery_proof_recorder',
    '_required_steps',
    '_reservation_evidence',
    '_revalidate_record_at',
    '_same_published_record',
    '_sleep_with_deadline',
    '_spawn_blocked_fence_child',
    '_stop_unstarted_child',
    '_terminate_fenced_group',
    '_unlink_revalidated_record_at',
    '_user_skip',
    '_valid_host',
    '_valid_nonce',
    '_valid_nonnegative_int',
    '_valid_nullable_chain',
    '_valid_positive_int',
    '_valid_sorted_unique_strings',
    '_valid_utc_second',
    '_validate_bound_chain_state',
    '_validate_chain_lease_record',
    '_validate_fence_record',
    '_validate_merge_scope_fetch_binding',
    '_validate_merge_scope_proof',
    '_validate_merge_scope_request',
    '_validate_owner_record',
    '_validate_recovery_record',
    '_validated_commitment_path',
    '_verify_and_build_ingest_records',
    '_verify_and_build_merge_ingest_records',
    '_wait_for_child_exit',
    '_waitpid_nohang',
    '_write_all',
    'acquire_chain_lease',
    'acquire_common_lock',
    'canonical_bytes',
    'hold_common_lock',
    'iso_z',
    'merge_gate_intent_digest',
    'parse_time',
    'reduce_merge_event',
    'register_coordination_seams',
    'run_fenced_command',
    'validate_merge_state',
    'validate_state', "_ReceiptRunSnapshot", "_chain_receipt_snapshot_lock", "_receipt_run_snapshot",
]
