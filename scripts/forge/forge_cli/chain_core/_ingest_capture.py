"""Extracted from scripts/forge/forge_cli/chain_core/__init__.py."""
from __future__ import annotations
import os
import stat
from pathlib import Path
from forge_cli import runtime
from forge_cli.chain_core._controls import COMMON_LOCK_OWNER_KINDS as COMMON_LOCK_OWNER_KINDS, COMMON_LOCK_OPERATIONS as COMMON_LOCK_OPERATIONS, COMMON_LOCK_FENCE_OPERATIONS as COMMON_LOCK_FENCE_OPERATIONS, COMMON_LOCK_RECOVERY_KINDS as COMMON_LOCK_RECOVERY_KINDS, _COMMON_LOCK_OWNER_KEYS as _COMMON_LOCK_OWNER_KEYS, _COMMON_LOCK_FENCE_KEYS as _COMMON_LOCK_FENCE_KEYS, _COMMON_LOCK_RECOVERY_KEYS as _COMMON_LOCK_RECOVERY_KEYS, _CHAIN_LEASE_KEYS as _CHAIN_LEASE_KEYS, _REQUIRED_COMMON_LOCK_CONTROLS as _REQUIRED_COMMON_LOCK_CONTROLS, COMMON_LOCK_CONTROLS as COMMON_LOCK_CONTROLS, CHAIN_TOMBSTONE_SCHEMA as CHAIN_TOMBSTONE_SCHEMA, CHAIN_TOMBSTONE_EVENT as CHAIN_TOMBSTONE_EVENT, CHAIN_TOMBSTONE_KEYS as CHAIN_TOMBSTONE_KEYS, _REQUIRED_MERGE_STORE_CONTROLS as _REQUIRED_MERGE_STORE_CONTROLS, MERGE_STORE_CONTROLS as MERGE_STORE_CONTROLS, _REQUIRED_MERGE_ADAPTER_CONTROLS as _REQUIRED_MERGE_ADAPTER_CONTROLS, MERGE_ADAPTER_CONTROLS as MERGE_ADAPTER_CONTROLS, _REQUIRED_MERGE_INTEGRATION_CONTROLS as _REQUIRED_MERGE_INTEGRATION_CONTROLS, MERGE_INTEGRATION_CONTROLS as MERGE_INTEGRATION_CONTROLS, INGEST_PROOF_ORDER as INGEST_PROOF_ORDER, _REQUIRED_INGEST_PROOF_CONTROLS as _REQUIRED_INGEST_PROOF_CONTROLS, INGEST_PROOF_CONTROLS as INGEST_PROOF_CONTROLS, _MERGE_CLEANUP_INTENT_SCHEMA as _MERGE_CLEANUP_INTENT_SCHEMA, _MERGE_CLEANUP_RESULT_SCHEMA as _MERGE_CLEANUP_RESULT_SCHEMA, _MERGE_CLEANUP_CLOSE_SCHEMA as _MERGE_CLEANUP_CLOSE_SCHEMA, _MERGE_CLEANUP_RECOVERY_SCHEMA as _MERGE_CLEANUP_RECOVERY_SCHEMA, _MERGE_CLEANUP_FENCE_OPERATIONS as _MERGE_CLEANUP_FENCE_OPERATIONS, _EPOCH_FETCH_OBSERVATION_SCHEMA as _EPOCH_FETCH_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA, _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA as _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA
from forge_cli.chain_core._core import canonical_bytes as canonical_bytes, _chain_storage_root as _chain_storage_root, _validated_commitment_path as _validated_commitment_path, _parsed_run_captured_path as _parsed_run_captured_path, _require_ingest_proof as _require_ingest_proof, iso_z as iso_z, parse_time as parse_time, _require_merge_store_control as _require_merge_store_control, _require_merge_adapter_control as _require_merge_adapter_control, _require_merge_integration_control as _require_merge_integration_control, _require_common_lock_control as _require_common_lock_control, CommonLockBoundaryCrash as CommonLockBoundaryCrash, PublishedLockRecord as PublishedLockRecord, CommonLockInspection as CommonLockInspection, CommonLockUnavailable as CommonLockUnavailable, CommonLockReleaseFailure as CommonLockReleaseFailure, ChainLeaseUnavailable as ChainLeaseUnavailable, FencedChildSurvived as FencedChildSurvived, _valid_utc_second as _valid_utc_second, _valid_positive_int as _valid_positive_int, _valid_nonnegative_int as _valid_nonnegative_int, _valid_host as _valid_host, _valid_nonce as _valid_nonce, _valid_nullable_chain as _valid_nullable_chain, _write_all as _write_all, _PublicationCleanupFailure as _PublicationCleanupFailure, _process_probe as _process_probe, _group_probe as _group_probe, _sleep_with_deadline as _sleep_with_deadline, _require_deadline_open as _require_deadline_open, FencedProcessResult as FencedProcessResult, merge_gate_intent_digest as merge_gate_intent_digest, _forge_command as _forge_command, MergeRunTaskSnapshot as MergeRunTaskSnapshot, _merge_refusal as _merge_refusal, _valid_sorted_unique_strings as _valid_sorted_unique_strings
from forge_cli.chain_core._state import SCHEMA as SCHEMA, KIND as KIND, FRESH_REVIEWER_EVALS_GATE as FRESH_REVIEWER_EVALS_GATE, FRESH_REVIEWER_EVALS_REQUESTS as FRESH_REVIEWER_EVALS_REQUESTS, FRESH_REVIEWER_EVALS_REQUESTED_EVENT as FRESH_REVIEWER_EVALS_REQUESTED_EVENT, STATES as STATES, STATE_KEYS as STATE_KEYS, EVENT_KEYS as EVENT_KEYS, MERGE_STATE_KEYS as MERGE_STATE_KEYS, _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES as _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES, _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES as _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES, MERGE_EVENT_KEYS as MERGE_EVENT_KEYS, MERGE_EVENT_NAMES as MERGE_EVENT_NAMES, MERGE_CONSEQUENTIAL_EVENTS as MERGE_CONSEQUENTIAL_EVENTS, TIER_RANK as TIER_RANK, INACTIVE_SECONDS as INACTIVE_SECONDS, FENCED_CHILD_ACK_TIMEOUT_SECONDS as FENCED_CHILD_ACK_TIMEOUT_SECONDS, FENCED_CHILD_DRAIN_SECONDS as FENCED_CHILD_DRAIN_SECONDS, FENCED_CHILD_DRAIN_CAP_BYTES as FENCED_CHILD_DRAIN_CAP_BYTES, FENCED_CHILD_STOP_GRACE_SECONDS as FENCED_CHILD_STOP_GRACE_SECONDS, FENCED_CHILD_REAP_SECONDS as FENCED_CHILD_REAP_SECONDS, ZERO_DIGEST as ZERO_DIGEST, COMMON_LOCK_TIMEOUT_SECONDS as COMMON_LOCK_TIMEOUT_SECONDS, COMMON_LOCK_POLL_SECONDS as COMMON_LOCK_POLL_SECONDS, COMMON_LOCK_RECORD_CAP_BYTES as COMMON_LOCK_RECORD_CAP_BYTES, MERGE_SCOPE_BINDING_CAP_BYTES as MERGE_SCOPE_BINDING_CAP_BYTES, COMMON_LOCK_INTENT_NAME as COMMON_LOCK_INTENT_NAME, COMMON_LOCK_DIRECTORY_NAME as COMMON_LOCK_DIRECTORY_NAME, COMMON_LOCK_OWNER_NAME as COMMON_LOCK_OWNER_NAME, COMMON_LOCK_FLOCK_NAME as COMMON_LOCK_FLOCK_NAME, COMMON_LOCK_RECOVERY_NAME as COMMON_LOCK_RECOVERY_NAME, COMMON_LOCK_INFLIGHT_NAME as COMMON_LOCK_INFLIGHT_NAME, CHAIN_ID_RE as CHAIN_ID_RE, SHA256_RE as SHA256_RE, COMMIT_RE as COMMIT_RE, RUN_ID_RE as RUN_ID_RE, _WORKTREE_LOCKS_GUARD as _WORKTREE_LOCKS_GUARD, _WORKTREE_LOCKS as _WORKTREE_LOCKS, _WORKTREE_LOCK_STATE as _WORKTREE_LOCK_STATE, _exclusive_descriptor_lock as _exclusive_descriptor_lock, _MERGE_REMOTE_ONLY_IDENTITY_FIELDS as _MERGE_REMOTE_ONLY_IDENTITY_FIELDS, _MERGE_SCOPE_UNSET as _MERGE_SCOPE_UNSET, _MERGE_SCOPE_OVERLAY as _MERGE_SCOPE_OVERLAY
from forge_cli.policy import sha256_bytes
from typing import MutableMapping


def _read_ingest_input(
    repository: Path,
    relative: str,
    label: str,
    *,
    run_dir: Path | None = None,
    expected_capture_name: str | None = None,
) -> bytes:
    """Read one repository input or canonical run capture without symlinks."""

    _batch, _builders, journal = runtime._coordination_modules()
    candidate_relative = Path(relative)
    inventory_labels = {
        "ingest.state_file",
        "ingest.events_file",
        "ingest.outcome_map",
    }
    read_root = repository
    if run_dir is None:
        inventory_invalid = bool(
            label in inventory_labels
            and _validated_commitment_path(
                label,
                relative,
                repository=repository,
                require_file=True,
            )
            is None
        )
    else:
        parsed_capture = _parsed_run_captured_path(relative, run_dir.name)
        capture_path = run_dir / candidate_relative
        inventory_invalid = bool(
            parsed_capture is None
            or parsed_capture.name != expected_capture_name
            or _validated_commitment_path(
                "ingest.captured_package",
                relative,
                repository=repository,
                run_dir=run_dir,
                direct_parent=capture_path.parent,
                require_file=True,
            )
            is None
        )
        read_root = run_dir
    diagnostic_label = (
        "ingest.captured_package" if run_dir is not None else label
    )
    if (
        inventory_invalid
        or not relative
        or candidate_relative.is_absolute()
        or not candidate_relative.parts
        or any(part in {"", ".", ".."} for part in candidate_relative.parts)
        or not journal._citation_is_contained(read_root, read_root, relative)
    ):
        raise journal.CoordinationRefusal(
            "forge: journal append refused — record cites path outside run or "
            f"repository: {diagnostic_label}: {relative}"
        )
    descriptors: list[int] = []

    def stable_metadata(value: os.stat_result) -> tuple[int, ...]:
        return (
            value.st_dev,
            value.st_ino,
            value.st_mode,
            value.st_uid,
            value.st_gid,
            value.st_nlink,
            value.st_size,
            value.st_mtime_ns,
            value.st_ctime_ns,
        )

    try:
        root_before = os.lstat(read_root)
        current = os.open(
            read_root,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
        descriptors.append(current)
        root_opened = os.fstat(current)
        if (
            not stat.S_ISDIR(root_opened.st_mode)
            or root_opened.st_uid != os.geteuid()
            or stable_metadata(root_before) != stable_metadata(root_opened)
        ):
            raise OSError("repository root is not owner-controlled")

        anchored: list[tuple[int, str, tuple[int, ...]]] = []
        for component in candidate_relative.parts[:-1]:
            before = os.stat(component, dir_fd=current, follow_symlinks=False)
            child = os.open(
                component,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=current,
            )
            opened = os.fstat(child)
            rebound = os.stat(
                component, dir_fd=current, follow_symlinks=False
            )
            if (
                not stat.S_ISDIR(opened.st_mode)
                or opened.st_uid != os.geteuid()
                or stable_metadata(before) != stable_metadata(opened)
                or stable_metadata(rebound) != stable_metadata(opened)
            ):
                os.close(child)
                raise OSError("input ancestor is not owner-controlled")
            anchored.append((current, component, stable_metadata(opened)))
            descriptors.append(child)
            current = child

        name = candidate_relative.parts[-1]
        before = os.stat(name, dir_fd=current, follow_symlinks=False)
        descriptor = os.open(
            name,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NONBLOCK", 0),
            dir_fd=current,
        )
        descriptors.append(descriptor)
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.geteuid()
            or opened.st_nlink != 1
            or stable_metadata(before) != stable_metadata(opened)
        ):
            raise OSError("input is not an owner-controlled regular file")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
        rebound = os.stat(name, dir_fd=current, follow_symlinks=False)
        if (
            stable_metadata(after) != stable_metadata(opened)
            or stable_metadata(rebound) != stable_metadata(opened)
        ):
            raise OSError("input changed while captured")
        for parent, component, expected in reversed(anchored):
            if stable_metadata(
                os.stat(component, dir_fd=parent, follow_symlinks=False)
            ) != expected:
                raise OSError("input ancestor changed while captured")
        if stable_metadata(os.lstat(read_root)) != stable_metadata(root_opened):
            raise OSError("input root changed while captured")
        return b"".join(chunks)
    except (FileNotFoundError, OSError) as exc:
        raise journal.CoordinationRefusal(
            "forge: journal append refused — record cites path outside run or "
            f"repository: {diagnostic_label}: {relative}"
        ) from exc
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _capture_ingest_blob(
    repository: Path,
    run_dir: Path,
    *,
    digest: str,
    name: str,
    data: bytes,
) -> str:
    """Install one immutable content-addressed direct-child capture."""

    _batch, _builders, journal = runtime._coordination_modules()
    descriptors: list[int] = []
    try:
        current, _observation = journal._open_bound_directory(run_dir)
        descriptors.append(current)
        for component in ("captured", "sha256", digest):
            try:
                os.mkdir(component, 0o700, dir_fd=current)
                os.fsync(current)
            except FileExistsError:
                pass
            before = os.stat(component, dir_fd=current, follow_symlinks=False)
            child, _ = journal._open_bound_child_directory(
                current, component, before
            )
            if os.fstat(child).st_uid != os.geteuid():
                os.close(child)
                raise OSError("capture directory has a foreign owner")
            descriptors.append(child)
            current = child
        try:
            existing, _ = journal._read_bound_regular(current, name)
        except FileNotFoundError:
            descriptor = os.open(
                name,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                0o600,
                dir_fd=current,
            )
            try:
                opened = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(opened.st_mode)
                    or opened.st_uid != os.geteuid()
                    or opened.st_nlink != 1
                ):
                    raise OSError("capture file is unsafe")
                written = 0
                while written < len(data):
                    count = os.write(descriptor, data[written:])
                    if count <= 0:
                        raise OSError("short capture write")
                    written += count
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            os.fsync(current)
            existing, _ = journal._read_bound_regular(current, name)
        if existing != data or sha256_bytes(existing) != digest:
            raise OSError("content-addressed capture differs")
    except (OSError, RuntimeError, ValueError) as exc:
        raise journal.CoordinationRefusal(
            "forge: journal append refused — record cites path outside run or "
            f"repository: ingest.captured_package: {name}"
        ) from exc
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
    path = run_dir / "captured" / "sha256" / digest / name
    capture_relative = path.relative_to(run_dir).as_posix()
    parsed_capture = _parsed_run_captured_path(capture_relative, run_dir.name)
    if _validated_commitment_path(
        "ingest.captured_package",
        capture_relative,
        repository=repository,
        run_dir=run_dir,
        direct_parent=path.parent,
        require_file=True,
    ) is None or parsed_capture is None:
        raise journal.CoordinationRefusal(
            "forge: journal append refused — record cites path outside run or "
            f"repository: ingest.captured_package: {path}"
        )
    return capture_relative


def _capture_run_evidence(
    repository: Path,
    run_dir: Path,
    data: bytes,
) -> str:
    """Capture arbitrary evidence through the existing run-package grammar.

    The shared commitment-path inventory deliberately admits only three
    direct-child names.  Evidence therefore uses the neutral ``events.jsonl``
    member under its own content digest rather than inventing a second capture
    namespace or citing the mutable chain-artifact location.
    """

    _require_merge_adapter_control("run-relative-evidence")
    return _capture_ingest_blob(
        repository,
        run_dir,
        digest=sha256_bytes(data),
        name="events.jsonl",
        data=data,
    )


def _capture_ingest_record_evidence(
    repository: Path,
    run_dir: Path,
    record: MutableMapping[str, object],
) -> None:
    """Replace repository citations with immutable run-relative captures."""

    evidence = record.get("evidence")
    if not isinstance(evidence, list):
        return
    captured: list[str] = []
    for citation in evidence:
        if not isinstance(citation, str):
            _batch, builders, journal = runtime._coordination_modules()
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
        parsed = _parsed_run_captured_path(citation, run_dir.name)
        if parsed is not None:
            _read_ingest_input(
                repository,
                citation,
                "ingest.captured_package",
                run_dir=run_dir,
                expected_capture_name=parsed.name,
            )
            captured.append(citation)
            continue
        data = _read_ingest_input(
            repository,
            citation,
            "ingest.record_evidence",
        )
        captured.append(_capture_run_evidence(repository, run_dir, data))
    record["evidence"] = captured
