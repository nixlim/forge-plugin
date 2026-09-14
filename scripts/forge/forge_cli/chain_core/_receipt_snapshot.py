"""Extracted from scripts/forge/forge_cli/chain_core/__init__.py."""
from __future__ import annotations
import dataclasses
from pathlib import Path
from forge_cli.chain_core._controls import COMMON_LOCK_OWNER_KINDS as COMMON_LOCK_OWNER_KINDS, COMMON_LOCK_OPERATIONS as COMMON_LOCK_OPERATIONS, COMMON_LOCK_FENCE_OPERATIONS as COMMON_LOCK_FENCE_OPERATIONS, COMMON_LOCK_RECOVERY_KINDS as COMMON_LOCK_RECOVERY_KINDS, _COMMON_LOCK_OWNER_KEYS as _COMMON_LOCK_OWNER_KEYS, _COMMON_LOCK_FENCE_KEYS as _COMMON_LOCK_FENCE_KEYS, _COMMON_LOCK_RECOVERY_KEYS as _COMMON_LOCK_RECOVERY_KEYS, _CHAIN_LEASE_KEYS as _CHAIN_LEASE_KEYS, _REQUIRED_COMMON_LOCK_CONTROLS as _REQUIRED_COMMON_LOCK_CONTROLS, COMMON_LOCK_CONTROLS as COMMON_LOCK_CONTROLS, CHAIN_TOMBSTONE_SCHEMA as CHAIN_TOMBSTONE_SCHEMA, CHAIN_TOMBSTONE_EVENT as CHAIN_TOMBSTONE_EVENT, CHAIN_TOMBSTONE_KEYS as CHAIN_TOMBSTONE_KEYS, _REQUIRED_MERGE_STORE_CONTROLS as _REQUIRED_MERGE_STORE_CONTROLS, MERGE_STORE_CONTROLS as MERGE_STORE_CONTROLS, _REQUIRED_MERGE_ADAPTER_CONTROLS as _REQUIRED_MERGE_ADAPTER_CONTROLS, MERGE_ADAPTER_CONTROLS as MERGE_ADAPTER_CONTROLS, _REQUIRED_MERGE_INTEGRATION_CONTROLS as _REQUIRED_MERGE_INTEGRATION_CONTROLS, MERGE_INTEGRATION_CONTROLS as MERGE_INTEGRATION_CONTROLS, INGEST_PROOF_ORDER as INGEST_PROOF_ORDER, _REQUIRED_INGEST_PROOF_CONTROLS as _REQUIRED_INGEST_PROOF_CONTROLS, INGEST_PROOF_CONTROLS as INGEST_PROOF_CONTROLS, _MERGE_CLEANUP_INTENT_SCHEMA as _MERGE_CLEANUP_INTENT_SCHEMA, _MERGE_CLEANUP_RESULT_SCHEMA as _MERGE_CLEANUP_RESULT_SCHEMA, _MERGE_CLEANUP_CLOSE_SCHEMA as _MERGE_CLEANUP_CLOSE_SCHEMA, _MERGE_CLEANUP_RECOVERY_SCHEMA as _MERGE_CLEANUP_RECOVERY_SCHEMA, _MERGE_CLEANUP_FENCE_OPERATIONS as _MERGE_CLEANUP_FENCE_OPERATIONS, _EPOCH_FETCH_OBSERVATION_SCHEMA as _EPOCH_FETCH_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA, _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA as _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA
from forge_cli.chain_core._core import canonical_bytes as canonical_bytes, _chain_storage_root as _chain_storage_root, _validated_commitment_path as _validated_commitment_path, _parsed_run_captured_path as _parsed_run_captured_path, _require_ingest_proof as _require_ingest_proof, iso_z as iso_z, parse_time as parse_time, _require_merge_store_control as _require_merge_store_control, _require_merge_adapter_control as _require_merge_adapter_control, _require_merge_integration_control as _require_merge_integration_control, _require_common_lock_control as _require_common_lock_control, CommonLockBoundaryCrash as CommonLockBoundaryCrash, PublishedLockRecord as PublishedLockRecord, CommonLockInspection as CommonLockInspection, CommonLockUnavailable as CommonLockUnavailable, CommonLockReleaseFailure as CommonLockReleaseFailure, ChainLeaseUnavailable as ChainLeaseUnavailable, FencedChildSurvived as FencedChildSurvived, _valid_utc_second as _valid_utc_second, _valid_positive_int as _valid_positive_int, _valid_nonnegative_int as _valid_nonnegative_int, _valid_host as _valid_host, _valid_nonce as _valid_nonce, _valid_nullable_chain as _valid_nullable_chain, _write_all as _write_all, _PublicationCleanupFailure as _PublicationCleanupFailure, _process_probe as _process_probe, _group_probe as _group_probe, _sleep_with_deadline as _sleep_with_deadline, _require_deadline_open as _require_deadline_open, FencedProcessResult as FencedProcessResult, merge_gate_intent_digest as merge_gate_intent_digest, _forge_command as _forge_command, MergeRunTaskSnapshot as MergeRunTaskSnapshot, _merge_refusal as _merge_refusal, _valid_sorted_unique_strings as _valid_sorted_unique_strings
from forge_cli.chain_core._state import SCHEMA as SCHEMA, KIND as KIND, FRESH_REVIEWER_EVALS_GATE as FRESH_REVIEWER_EVALS_GATE, FRESH_REVIEWER_EVALS_REQUESTS as FRESH_REVIEWER_EVALS_REQUESTS, FRESH_REVIEWER_EVALS_REQUESTED_EVENT as FRESH_REVIEWER_EVALS_REQUESTED_EVENT, STATES as STATES, STATE_KEYS as STATE_KEYS, EVENT_KEYS as EVENT_KEYS, MERGE_STATE_KEYS as MERGE_STATE_KEYS, _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES as _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES, _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES as _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES, MERGE_EVENT_KEYS as MERGE_EVENT_KEYS, MERGE_EVENT_NAMES as MERGE_EVENT_NAMES, MERGE_CONSEQUENTIAL_EVENTS as MERGE_CONSEQUENTIAL_EVENTS, TIER_RANK as TIER_RANK, INACTIVE_SECONDS as INACTIVE_SECONDS, FENCED_CHILD_ACK_TIMEOUT_SECONDS as FENCED_CHILD_ACK_TIMEOUT_SECONDS, FENCED_CHILD_DRAIN_SECONDS as FENCED_CHILD_DRAIN_SECONDS, FENCED_CHILD_DRAIN_CAP_BYTES as FENCED_CHILD_DRAIN_CAP_BYTES, FENCED_CHILD_STOP_GRACE_SECONDS as FENCED_CHILD_STOP_GRACE_SECONDS, FENCED_CHILD_REAP_SECONDS as FENCED_CHILD_REAP_SECONDS, ZERO_DIGEST as ZERO_DIGEST, COMMON_LOCK_TIMEOUT_SECONDS as COMMON_LOCK_TIMEOUT_SECONDS, COMMON_LOCK_POLL_SECONDS as COMMON_LOCK_POLL_SECONDS, COMMON_LOCK_RECORD_CAP_BYTES as COMMON_LOCK_RECORD_CAP_BYTES, MERGE_SCOPE_BINDING_CAP_BYTES as MERGE_SCOPE_BINDING_CAP_BYTES, COMMON_LOCK_INTENT_NAME as COMMON_LOCK_INTENT_NAME, COMMON_LOCK_DIRECTORY_NAME as COMMON_LOCK_DIRECTORY_NAME, COMMON_LOCK_OWNER_NAME as COMMON_LOCK_OWNER_NAME, COMMON_LOCK_FLOCK_NAME as COMMON_LOCK_FLOCK_NAME, COMMON_LOCK_RECOVERY_NAME as COMMON_LOCK_RECOVERY_NAME, COMMON_LOCK_INFLIGHT_NAME as COMMON_LOCK_INFLIGHT_NAME, CHAIN_ID_RE as CHAIN_ID_RE, SHA256_RE as SHA256_RE, COMMIT_RE as COMMIT_RE, RUN_ID_RE as RUN_ID_RE, _WORKTREE_LOCKS_GUARD as _WORKTREE_LOCKS_GUARD, _WORKTREE_LOCKS as _WORKTREE_LOCKS, _WORKTREE_LOCK_STATE as _WORKTREE_LOCK_STATE, _exclusive_descriptor_lock as _exclusive_descriptor_lock, _MERGE_REMOTE_ONLY_IDENTITY_FIELDS as _MERGE_REMOTE_ONLY_IDENTITY_FIELDS, _MERGE_SCOPE_UNSET as _MERGE_SCOPE_UNSET, _MERGE_SCOPE_OVERLAY as _MERGE_SCOPE_OVERLAY
import contextlib
import os
from typing import Iterable
from forge_cli import runtime


@dataclasses.dataclass(frozen=True)
class _ReceiptRunSnapshot:
    """Exact run surfaces authenticated without nesting an exclusive run lock."""

    run_dir: Path
    run_observation: object
    lock_observation: object
    names: frozenset[str]
    journal_exact: object
    receipts_exact: object
    intent_exact: object


@contextlib.contextmanager
def _chain_receipt_snapshot_lock(run_dir: Path) -> Iterable[object]:
    """Reuse the current run lock or bind a foreign run by exact snapshots.

    Lineage authorization already holds its target run's exclusive lock.  A
    second flock on a sibling run would permit an A->B/B->A deadlock.  Foreign
    descriptors therefore never flock; callers bracket every read with exact
    file, directory, and stable-lock identity snapshots and refuse on change.
    """

    batch, _builders, journal = runtime._coordination_modules()
    key = os.path.abspath(os.fspath(run_dir))
    active = batch._active_locks().get(key)
    if active is not None:
        batch._validate_batch_lock(active)
        batch._validate_no_orphan_intent_temporary(active)
        try:
            yield active
        finally:
            batch._validate_no_orphan_intent_temporary(active)
            batch._validate_batch_lock(active)
        return

    run_descriptor: int | None = None
    lock_descriptor: int | None = None
    try:
        run_descriptor, run_observation = journal._open_strict_batch_directory(
            run_dir, refusal=journal.BATCH_DIVERGED
        )
        _lock_stat, lock_observation = batch._validate_named_file(
            run_descriptor, journal.BATCH_LOCK_NAME
        )
        lock_descriptor = os.open(
            journal.BATCH_LOCK_NAME,
            batch._safe_open_flags(os.O_RDONLY, nonblocking=True),
            dir_fd=run_descriptor,
        )
        if not batch._same(os.fstat(lock_descriptor), lock_observation):
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        locked = batch.BatchLock(
            run_dir,
            run_descriptor,
            lock_descriptor,
            lock_observation,
        )
        if (
            journal._file_observation(os.fstat(run_descriptor))
            != run_observation
        ):
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        batch._validate_batch_lock(locked)
        batch._validate_no_orphan_intent_temporary(locked)
        try:
            yield locked
        finally:
            batch._validate_no_orphan_intent_temporary(locked)
            batch._validate_batch_lock(locked)
    except journal.CoordinationRefusal:
        raise
    except (FileNotFoundError, OSError) as exc:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED) from exc
    finally:
        if lock_descriptor is not None:
            os.close(lock_descriptor)
        if run_descriptor is not None:
            os.close(run_descriptor)


def _receipt_run_snapshot(locked: object) -> _ReceiptRunSnapshot:
    """Capture every run surface consulted by receipt replay."""

    batch, _builders, journal = runtime._coordination_modules()
    batch._validate_batch_lock(locked)
    batch._validate_no_orphan_intent_temporary(locked)
    journal_exact = batch._optional_exact_named_file(locked, "journal.jsonl")
    if journal_exact is None:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    snapshot = _ReceiptRunSnapshot(
        run_dir=locked.run_dir,
        run_observation=journal._file_observation(
            os.fstat(locked.run_descriptor)
        ),
        lock_observation=locked.lock_observation,
        names=frozenset(os.listdir(locked.run_descriptor)),
        journal_exact=journal_exact,
        receipts_exact=batch._optional_exact_named_file(
            locked, journal.BATCH_RECEIPTS_NAME
        ),
        intent_exact=batch._optional_exact_named_file(
            locked, journal.BATCH_INTENT_NAME
        ),
    )
    if frozenset(os.listdir(locked.run_descriptor)) != snapshot.names:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    batch._validate_no_orphan_intent_temporary(locked)
    batch._validate_batch_lock(locked)
    return snapshot


class _ChainReceiptSnapshotVerifier:
    """Authenticate every sibling receipt against one closed run snapshot."""

    def __init__(self, repository: Path) -> None:
        self.repository = repository
        self._snapshots: dict[str, _ReceiptRunSnapshot] = {}

    def __call__(
        self,
        repository: Path,
        chain_id: str,
        state: dict[str, object],
        pending: dict[str, object],
        carried_records: tuple[dict[str, object], ...],
        acknowledgement: dict[str, object],
    ) -> None:
        batch, builders, journal = runtime._coordination_modules()
        run_binding = state.get("run_binding")
        if (
            repository != self.repository
            or not isinstance(run_binding, dict)
            or not builders._run_binding_valid(run_binding)
            or run_binding.get("repository") != str(self.repository)
        ):
            raise builders._binding_replay_refusal()
        run_id = run_binding.get("run_id")
        if not journal._valid_run_id(run_id):
            raise builders._binding_replay_refusal()
        assert isinstance(run_id, str)
        run_dir = (
            builders.chain_storage_root(self.repository).parents[1]
            / ".codex-orchestrator"
            / "runs"
            / run_id
        )
        key = os.path.abspath(os.fspath(run_dir))
        try:
            with _chain_receipt_snapshot_lock(run_dir) as locked:
                before = _receipt_run_snapshot(locked)
                previous = self._snapshots.get(key)
                if previous is not None and before != previous:
                    raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
                receipts, loaded_raw, loaded_observation = (
                    batch._load_receipts_for_chain_replay(locked)
                )
                loaded_exact = (
                    None
                    if loaded_observation is None
                    else journal.ExactFile(loaded_raw, loaded_observation)
                )
                matches = [
                    receipt
                    for receipt in receipts
                    if receipt.get("idempotency_key")
                    == pending.get("idempotency_key")
                ]
                if len(matches) != 1:
                    raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
                receipt = matches[0]
                batch.validate_pending_outbox_receipt(pending, receipt)
                _, request_digest = batch.normalized_request(
                    self.repository,
                    run_id,
                    "chain outbox-drain",
                    {
                        "chain_id": chain_id,
                        "source_event_digest": pending["source_event_digest"],
                        "batch_digest": pending["batch_digest"],
                        "record_count": pending["record_count"],
                    },
                )
                journal_records = batch._verify_receipt_journal(
                    locked, receipt, expected_journal=before.journal_exact
                )
                if (
                    loaded_exact != before.receipts_exact
                    or receipt.get("request_sha256") != request_digest
                    or b"".join(
                        journal._journal_line(record)
                        for record in journal_records
                    )
                    != b"".join(
                        journal._journal_line(record)
                        for record in carried_records
                    )
                    or acknowledgement.get("receipt_digest")
                    != journal._sha256(
                        journal._canonical_json_bytes(receipt) + b"\n"
                    )
                    or _receipt_run_snapshot(locked) != before
                ):
                    raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
                self._snapshots[key] = before
        except journal.CoordinationRefusal as exc:
            raise builders._binding_replay_refusal() from exc
        except (KeyError, MemoryError, OSError) as exc:
            raise builders._binding_replay_refusal() from exc

    def recheck(self) -> None:
        """Prove all sibling run snapshots stayed exact through chain replay."""

        _batch, builders, journal = runtime._coordination_modules()
        try:
            for snapshot in self._snapshots.values():
                with _chain_receipt_snapshot_lock(snapshot.run_dir) as locked:
                    if _receipt_run_snapshot(locked) != snapshot:
                        raise journal.CoordinationRefusal(
                            journal.BATCH_DIVERGED
                        )
        except journal.CoordinationRefusal as exc:
            raise builders._binding_replay_refusal() from exc
        except (MemoryError, OSError) as exc:
            raise builders._binding_replay_refusal() from exc
