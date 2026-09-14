"""Extracted from scripts/forge/forge_cli/chain_core/__init__.py."""
from __future__ import annotations
import dataclasses
from forge_cli.chain_core._controls import COMMON_LOCK_OWNER_KINDS as COMMON_LOCK_OWNER_KINDS, COMMON_LOCK_OPERATIONS as COMMON_LOCK_OPERATIONS, COMMON_LOCK_FENCE_OPERATIONS as COMMON_LOCK_FENCE_OPERATIONS, COMMON_LOCK_RECOVERY_KINDS as COMMON_LOCK_RECOVERY_KINDS, _COMMON_LOCK_OWNER_KEYS as _COMMON_LOCK_OWNER_KEYS, _COMMON_LOCK_FENCE_KEYS as _COMMON_LOCK_FENCE_KEYS, _COMMON_LOCK_RECOVERY_KEYS as _COMMON_LOCK_RECOVERY_KEYS, _CHAIN_LEASE_KEYS as _CHAIN_LEASE_KEYS, _REQUIRED_COMMON_LOCK_CONTROLS as _REQUIRED_COMMON_LOCK_CONTROLS, COMMON_LOCK_CONTROLS as COMMON_LOCK_CONTROLS, CHAIN_TOMBSTONE_SCHEMA as CHAIN_TOMBSTONE_SCHEMA, CHAIN_TOMBSTONE_EVENT as CHAIN_TOMBSTONE_EVENT, CHAIN_TOMBSTONE_KEYS as CHAIN_TOMBSTONE_KEYS, _REQUIRED_MERGE_STORE_CONTROLS as _REQUIRED_MERGE_STORE_CONTROLS, MERGE_STORE_CONTROLS as MERGE_STORE_CONTROLS, _REQUIRED_MERGE_ADAPTER_CONTROLS as _REQUIRED_MERGE_ADAPTER_CONTROLS, MERGE_ADAPTER_CONTROLS as MERGE_ADAPTER_CONTROLS, _REQUIRED_MERGE_INTEGRATION_CONTROLS as _REQUIRED_MERGE_INTEGRATION_CONTROLS, MERGE_INTEGRATION_CONTROLS as MERGE_INTEGRATION_CONTROLS, INGEST_PROOF_ORDER as INGEST_PROOF_ORDER, _REQUIRED_INGEST_PROOF_CONTROLS as _REQUIRED_INGEST_PROOF_CONTROLS, INGEST_PROOF_CONTROLS as INGEST_PROOF_CONTROLS, _MERGE_CLEANUP_INTENT_SCHEMA as _MERGE_CLEANUP_INTENT_SCHEMA, _MERGE_CLEANUP_RESULT_SCHEMA as _MERGE_CLEANUP_RESULT_SCHEMA, _MERGE_CLEANUP_CLOSE_SCHEMA as _MERGE_CLEANUP_CLOSE_SCHEMA, _MERGE_CLEANUP_RECOVERY_SCHEMA as _MERGE_CLEANUP_RECOVERY_SCHEMA, _MERGE_CLEANUP_FENCE_OPERATIONS as _MERGE_CLEANUP_FENCE_OPERATIONS, _EPOCH_FETCH_OBSERVATION_SCHEMA as _EPOCH_FETCH_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA, _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA as _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA
from forge_cli.chain_core._core import canonical_bytes as canonical_bytes, _chain_storage_root as _chain_storage_root, _validated_commitment_path as _validated_commitment_path, _parsed_run_captured_path as _parsed_run_captured_path, _require_ingest_proof as _require_ingest_proof, iso_z as iso_z, parse_time as parse_time, _require_merge_store_control as _require_merge_store_control, _require_merge_adapter_control as _require_merge_adapter_control, _require_merge_integration_control as _require_merge_integration_control, _require_common_lock_control as _require_common_lock_control, CommonLockBoundaryCrash as CommonLockBoundaryCrash, PublishedLockRecord as PublishedLockRecord, CommonLockInspection as CommonLockInspection, CommonLockUnavailable as CommonLockUnavailable, CommonLockReleaseFailure as CommonLockReleaseFailure, ChainLeaseUnavailable as ChainLeaseUnavailable, FencedChildSurvived as FencedChildSurvived, _valid_utc_second as _valid_utc_second, _valid_positive_int as _valid_positive_int, _valid_nonnegative_int as _valid_nonnegative_int, _valid_host as _valid_host, _valid_nonce as _valid_nonce, _valid_nullable_chain as _valid_nullable_chain, _write_all as _write_all, _PublicationCleanupFailure as _PublicationCleanupFailure, _process_probe as _process_probe, _group_probe as _group_probe, _sleep_with_deadline as _sleep_with_deadline, _require_deadline_open as _require_deadline_open, FencedProcessResult as FencedProcessResult, merge_gate_intent_digest as merge_gate_intent_digest, _forge_command as _forge_command, MergeRunTaskSnapshot as MergeRunTaskSnapshot, _merge_refusal as _merge_refusal, _valid_sorted_unique_strings as _valid_sorted_unique_strings
from forge_cli.chain_core._state import SCHEMA as SCHEMA, KIND as KIND, FRESH_REVIEWER_EVALS_GATE as FRESH_REVIEWER_EVALS_GATE, FRESH_REVIEWER_EVALS_REQUESTS as FRESH_REVIEWER_EVALS_REQUESTS, FRESH_REVIEWER_EVALS_REQUESTED_EVENT as FRESH_REVIEWER_EVALS_REQUESTED_EVENT, STATES as STATES, STATE_KEYS as STATE_KEYS, EVENT_KEYS as EVENT_KEYS, MERGE_STATE_KEYS as MERGE_STATE_KEYS, _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES as _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES, _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES as _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES, MERGE_EVENT_KEYS as MERGE_EVENT_KEYS, MERGE_EVENT_NAMES as MERGE_EVENT_NAMES, MERGE_CONSEQUENTIAL_EVENTS as MERGE_CONSEQUENTIAL_EVENTS, TIER_RANK as TIER_RANK, INACTIVE_SECONDS as INACTIVE_SECONDS, FENCED_CHILD_ACK_TIMEOUT_SECONDS as FENCED_CHILD_ACK_TIMEOUT_SECONDS, FENCED_CHILD_DRAIN_SECONDS as FENCED_CHILD_DRAIN_SECONDS, FENCED_CHILD_DRAIN_CAP_BYTES as FENCED_CHILD_DRAIN_CAP_BYTES, FENCED_CHILD_STOP_GRACE_SECONDS as FENCED_CHILD_STOP_GRACE_SECONDS, FENCED_CHILD_REAP_SECONDS as FENCED_CHILD_REAP_SECONDS, ZERO_DIGEST as ZERO_DIGEST, COMMON_LOCK_TIMEOUT_SECONDS as COMMON_LOCK_TIMEOUT_SECONDS, COMMON_LOCK_POLL_SECONDS as COMMON_LOCK_POLL_SECONDS, COMMON_LOCK_RECORD_CAP_BYTES as COMMON_LOCK_RECORD_CAP_BYTES, MERGE_SCOPE_BINDING_CAP_BYTES as MERGE_SCOPE_BINDING_CAP_BYTES, COMMON_LOCK_INTENT_NAME as COMMON_LOCK_INTENT_NAME, COMMON_LOCK_DIRECTORY_NAME as COMMON_LOCK_DIRECTORY_NAME, COMMON_LOCK_OWNER_NAME as COMMON_LOCK_OWNER_NAME, COMMON_LOCK_FLOCK_NAME as COMMON_LOCK_FLOCK_NAME, COMMON_LOCK_RECOVERY_NAME as COMMON_LOCK_RECOVERY_NAME, COMMON_LOCK_INFLIGHT_NAME as COMMON_LOCK_INFLIGHT_NAME, CHAIN_ID_RE as CHAIN_ID_RE, SHA256_RE as SHA256_RE, COMMIT_RE as COMMIT_RE, RUN_ID_RE as RUN_ID_RE, _WORKTREE_LOCKS_GUARD as _WORKTREE_LOCKS_GUARD, _WORKTREE_LOCKS as _WORKTREE_LOCKS, _WORKTREE_LOCK_STATE as _WORKTREE_LOCK_STATE, _exclusive_descriptor_lock as _exclusive_descriptor_lock, _MERGE_REMOTE_ONLY_IDENTITY_FIELDS as _MERGE_REMOTE_ONLY_IDENTITY_FIELDS, _MERGE_SCOPE_UNSET as _MERGE_SCOPE_UNSET, _MERGE_SCOPE_OVERLAY as _MERGE_SCOPE_OVERLAY
import os
from typing import Callable, Mapping, Sequence, Any
import signal
from pathlib import Path
import hashlib
import selectors
import sys


@dataclasses.dataclass
class _BlockedFenceChild:
    pid: int
    pgid: int
    start_descriptor: int
    output_descriptor: int
    exec_error_descriptor: int


def _pipe_cloexec() -> tuple[int, int]:
    if hasattr(os, "pipe2"):
        return os.pipe2(getattr(os, "O_CLOEXEC", 0))
    readers, writers = os.pipe()
    try:
        os.set_inheritable(readers, False)
        os.set_inheritable(writers, False)
    except BaseException:
        os.close(readers)
        os.close(writers)
        raise
    return readers, writers


def _read_child_ack(
    descriptor: int,
    *,
    deadline: float,
    clock: Callable[[], float],
    sleeper: Callable[[float], None],
) -> tuple[int, int]:
    os.set_blocking(descriptor, False)
    raw = bytearray()
    while len(raw) <= 128:
        try:
            chunk = os.read(descriptor, 128 - len(raw))
        except BlockingIOError:
            chunk = None
        if chunk == b"":
            break
        if chunk:
            raw.extend(chunk)
            if raw.endswith(b"\n"):
                break
        if not _sleep_with_deadline(deadline, clock, sleeper):
            raise TimeoutError("blocked child did not acknowledge its process group")
    try:
        decoded = raw.decode("ascii", "strict").rstrip("\n")
        pid_text, pgid_text = decoded.split(":", 1)
        pid = int(pid_text)
        pgid = int(pgid_text)
    except (UnicodeError, ValueError) as exc:
        raise OSError("blocked child process-group acknowledgement is malformed") from exc
    if not _valid_positive_int(pid) or not _valid_positive_int(pgid):
        raise OSError("blocked child acknowledged an invalid PID/PGID")
    return pid, pgid


def _waitpid_nohang(pid: int) -> tuple[bool, int | None]:
    try:
        observed, status_value = os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        return True, None
    if observed == 0:
        return False, None
    return True, os.waitstatus_to_exitcode(status_value)


def _wait_for_child_exit(
    pid: int,
    *,
    deadline: float,
    clock: Callable[[], float],
    sleeper: Callable[[float], None],
) -> bool:
    while True:
        reaped, _returncode = _waitpid_nohang(pid)
        if reaped:
            return True
        remaining = deadline - clock()
        if remaining <= 0:
            return False
        sleeper(min(0.01, remaining))


def _spawn_blocked_fence_child(
    argv: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str] | None,
    deadline: float,
    clock: Callable[[], float],
    sleeper: Callable[[float], None],
) -> _BlockedFenceChild:
    if not argv or not all(isinstance(item, str) and "\x00" not in item for item in argv):
        raise ValueError("fenced child argv must be a nonempty NUL-free string vector")
    descriptors: list[int] = []
    try:
        for _index in range(4):
            descriptors.extend(_pipe_cloexec())
    except BaseException:
        for descriptor in descriptors:
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise
    (
        start_read,
        start_write,
        ack_read,
        ack_write,
        output_read,
        output_write,
        error_read,
        error_write,
    ) = descriptors
    try:
        pid = os.fork()
    except BaseException:
        for descriptor in descriptors:
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise
    if pid == 0:  # pragma: no cover - assertions observe the parent-visible protocol
        try:
            os.close(start_write)
            os.close(ack_read)
            os.close(output_read)
            os.close(error_read)
            os.setsid()
            child_pid = os.getpid()
            child_pgid = os.getpgrp()
            os.write(ack_write, f"{child_pid}:{child_pgid}\n".encode("ascii"))
            os.close(ack_write)
            start = os.read(start_read, 1)
            os.close(start_read)
            if start != b"\x01":
                os._exit(125)
            os.chdir(cwd)
            null_input = os.open(os.devnull, os.O_RDONLY)
            os.dup2(null_input, 0)
            os.close(null_input)
            os.dup2(output_write, 1)
            os.dup2(output_write, 2)
            os.close(output_write)
            execution_env = dict(os.environ if env is None else env)
            os.execvpe(argv[0], list(argv), execution_env)
        except BaseException as exc:
            try:
                error = f"{type(exc).__name__}:{getattr(exc, 'errno', '')}".encode(
                    "ascii", "replace"
                )
                os.write(error_write, error[:256])
            except BaseException:
                pass
            os._exit(127)
    parent_open = set(descriptors)
    spawn_error: BaseException | None = None
    result: _BlockedFenceChild | None = None
    try:
        for descriptor in (start_read, ack_write, output_write, error_write):
            os.close(descriptor)
            parent_open.discard(descriptor)
        acknowledged_pid, acknowledged_pgid = _read_child_ack(
            ack_read, deadline=deadline, clock=clock, sleeper=sleeper
        )
        if acknowledged_pid != pid or acknowledged_pgid != pid:
            raise OSError("child did not establish the expected isolated process group")
        try:
            if os.getpgid(pid) != acknowledged_pgid:
                raise OSError("child process-group identity changed before fencing")
        except ProcessLookupError as exc:
            raise OSError("blocked child exited before fencing") from exc
        result = _BlockedFenceChild(
            pid=pid,
            pgid=acknowledged_pgid,
            start_descriptor=start_write,
            output_descriptor=output_read,
            exec_error_descriptor=error_read,
        )
        os.close(ack_read)
        parent_open.discard(ack_read)
    except BaseException as exc:
        spawn_error = exc
    if spawn_error is not None:
        descriptor_errors: list[str] = []
        for descriptor in descriptors:
            if descriptor not in parent_open:
                continue
            try:
                os.close(descriptor)
                parent_open.discard(descriptor)
            except OSError:
                descriptor_errors.append(str(descriptor))
        reaped = False
        try:
            reaped = _wait_for_child_exit(
                pid,
                deadline=clock() + FENCED_CHILD_STOP_GRACE_SECONDS,
                clock=clock,
                sleeper=sleeper,
            )
            if not reaped:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                reaped = _wait_for_child_exit(
                    pid,
                    deadline=clock() + FENCED_CHILD_REAP_SECONDS,
                    clock=clock,
                    sleeper=sleeper,
                )
        except BaseException:
            reaped = False
        if not reaped:
            raise ChildProcessError(
                "blocked child could not be reaped after acknowledgement failure"
            ) from spawn_error
        if descriptor_errors or parent_open:
            raise ChildProcessError(
                "blocked child descriptor cleanup could not be proved"
            ) from spawn_error
        raise spawn_error
    assert result is not None
    return result


def _terminate_fenced_group(
    child: _BlockedFenceChild,
    *,
    signal_group: Callable[[int, int], Any],
    group_probe: Callable[[int], str],
    clock: Callable[[], float],
    sleeper: Callable[[float], None],
) -> tuple[int | None, bool]:
    _require_common_lock_control("process-group-termination")
    returncode: int | None = None
    reaped = False
    try:
        signal_group(child.pgid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    term_deadline = clock() + 0.25
    while clock() < term_deadline:
        if not reaped:
            reaped, observed = _waitpid_nohang(child.pid)
            if reaped:
                returncode = observed
        if group_probe(child.pgid) == "dead":
            return returncode, False
        sleeper(min(0.01, max(0.0, term_deadline - clock())))
    try:
        signal_group(child.pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    kill_deadline = clock() + 0.5
    while clock() < kill_deadline:
        if not reaped:
            reaped, observed = _waitpid_nohang(child.pid)
            if reaped:
                returncode = observed
        if group_probe(child.pgid) == "dead":
            return returncode, False
        sleeper(min(0.01, max(0.0, kill_deadline - clock())))
    if not reaped:
        reaped, observed = _waitpid_nohang(child.pid)
        if reaped:
            returncode = observed
    return returncode, group_probe(child.pgid) != "dead"


def _stop_unstarted_child(
    child: _BlockedFenceChild,
    *,
    clock: Callable[[], float],
    sleeper: Callable[[float], None],
) -> bool:
    try:
        os.close(child.start_descriptor)
    except OSError:
        pass
    try:
        if _wait_for_child_exit(
            child.pid,
            deadline=clock() + FENCED_CHILD_STOP_GRACE_SECONDS,
            clock=clock,
            sleeper=sleeper,
        ):
            return True
        try:
            os.killpg(child.pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        return _wait_for_child_exit(
            child.pid,
            deadline=clock() + FENCED_CHILD_REAP_SECONDS,
            clock=clock,
            sleeper=sleeper,
        )
    finally:
        for descriptor in (child.output_descriptor, child.exec_error_descriptor):
            try:
                os.close(descriptor)
            except OSError:
                pass


def _collect_fenced_child(
    child: _BlockedFenceChild,
    *,
    argv: Sequence[str],
    started: float,
    timeout: float,
    cap: int,
    clock: Callable[[], float],
    sleeper: Callable[[float], None],
    group_probe: Callable[[int], str],
    signal_group: Callable[[int, int], Any],
    verbose: bool,
) -> tuple[int | None, bytes, str, bool, bool, bool, bool]:
    _require_common_lock_control("bounded-output")
    os.set_blocking(child.output_descriptor, False)
    os.set_blocking(child.exec_error_descriptor, False)
    selector = selectors.DefaultSelector()
    selector.register(child.output_descriptor, selectors.EVENT_READ)
    kept = bytearray()
    digest = hashlib.sha256()
    total = 0
    timed_out = False
    output_limit = False
    returncode: int | None = None
    reaped = False
    output_eof = False
    terminated = False
    group_survived = False
    drain_deadline: float | None = None
    drain_bytes = 0

    def begin_bounded_drain() -> None:
        nonlocal drain_deadline
        if drain_deadline is None:
            drain_deadline = clock() + FENCED_CHILD_DRAIN_SECONDS

    try:
        while True:
            if not reaped:
                reaped, observed = _waitpid_nohang(child.pid)
                if reaped:
                    returncode = observed
            if not terminated and clock() - started >= timeout:
                timed_out = True
                returncode, group_survived = _terminate_fenced_group(
                    child,
                    signal_group=signal_group,
                    group_probe=group_probe,
                    clock=clock,
                    sleeper=sleeper,
                )
                reaped = returncode is not None
                terminated = True
                begin_bounded_drain()
            elif reaped and not terminated:
                if group_probe(child.pgid) != "dead":
                    terminated_returncode, group_survived = _terminate_fenced_group(
                        child,
                        signal_group=signal_group,
                        group_probe=group_probe,
                        clock=clock,
                        sleeper=sleeper,
                    )
                    if terminated_returncode is not None:
                        returncode = terminated_returncode
                terminated = True
                begin_bounded_drain()

            select_timeout = 0.02
            if drain_deadline is not None:
                remaining_time = drain_deadline - clock()
                if remaining_time <= 0:
                    break
                select_timeout = min(select_timeout, remaining_time)
            events = selector.select(select_timeout)
            drain_exhausted = False
            for _key, _mask in events:
                if drain_deadline is not None:
                    if clock() >= drain_deadline:
                        drain_exhausted = True
                        break
                    remaining_bytes = FENCED_CHILD_DRAIN_CAP_BYTES - drain_bytes
                    if remaining_bytes <= 0:
                        drain_exhausted = True
                        break
                    read_size = min(8192, remaining_bytes)
                else:
                    # Cross the configured cap by at most one byte so a
                    # continuously ready writer cannot monopolize this loop
                    # before termination begins.
                    read_size = min(8192, max(1, cap + 1 - total))
                try:
                    part = os.read(child.output_descriptor, read_size)
                except BlockingIOError:
                    continue
                if not part:
                    output_eof = True
                    break
                digest.update(part)
                total += len(part)
                if drain_deadline is not None:
                    drain_bytes += len(part)
                if len(kept) < cap:
                    kept.extend(part[: cap - len(kept)])
                # Never let a post-termination survivor block this parent on
                # diagnostic relay; the retained transcript/digest stay bound.
                if verbose and drain_deadline is None:
                    sys.stderr.write(part.decode("utf-8", "replace"))
                    sys.stderr.flush()
                if total > cap:
                    output_limit = True
            if output_limit and not terminated:
                returncode, group_survived = _terminate_fenced_group(
                    child,
                    signal_group=signal_group,
                    group_probe=group_probe,
                    clock=clock,
                    sleeper=sleeper,
                )
                reaped = returncode is not None
                terminated = True
                begin_bounded_drain()
            if terminated:
                assert drain_deadline is not None
                if (
                    output_eof
                    or not events
                    or drain_exhausted
                    or drain_bytes >= FENCED_CHILD_DRAIN_CAP_BYTES
                    or clock() >= drain_deadline
                ):
                    break
        if not reaped:
            observed_reaped, observed = _waitpid_nohang(child.pid)
            if observed_reaped:
                returncode = observed
                reaped = True
        if not group_survived:
            group_survived = group_probe(child.pgid) != "dead"
        try:
            launch_bytes = os.read(child.exec_error_descriptor, 257)
        except BlockingIOError:
            launch_bytes = b""
        launch_failed = bool(launch_bytes)
        return (
            returncode,
            bytes(kept),
            digest.hexdigest(),
            timed_out,
            output_limit,
            launch_failed,
            group_survived,
        )
    finally:
        selector.close()
        os.close(child.output_descriptor)
        os.close(child.exec_error_descriptor)
