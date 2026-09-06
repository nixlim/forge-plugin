"""Forge CLI chain core: the fenced process runner, the FR-235 common-lock arbiter and
chain leases, chain and merge-chain storage, merge state/transition validation, and the
ingest verifiers (cli split phase 2b, bead forge-plugin-95e.3).

Moved verbatim from scripts/forge/cli.py. Runtime controls are read through
``forge_cli.runtime``; the chain journal-record builder stays in the shim and is reached
through the late-bound ``runtime._build_chain_journal_records`` seam.
"""

from __future__ import annotations

from typing import Any, Callable, Collection, Iterable, Mapping, MutableMapping, Sequence
from pathlib import Path
import base64
import binascii
import contextlib
import copy
import dataclasses
import datetime as dt
import errno
import fcntl
import hashlib
import json
import math
import os
import re
import secrets
import selectors
import signal
import socket
import stat
import subprocess
import sys
import threading
import time

from forge_cli import runtime
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


SCHEMA = "forge-chain/1"


KIND = "commit"


STATES = {
    "classifying",
    "verifying",
    "reviewing",
    "revising",
    "awaiting_approval",
    "authorized",
    "committing",
    "closed",
    "aborted",
}


STATE_KEYS = {
    "schema",
    "chain_id",
    "kind",
    "state",
    "created_at",
    "last_event_at",
    "inactive_after",
    "repo_head",
    "policy_source",
    "paths",
    "staging",
    "candidate",
    "tier",
    "steps",
    "review",
    "approval",
    "authorization",
    "commit_result",
    "run_binding",
    "journal_outbox",
}


EVENT_KEYS = {"sequence", "prev_digest", "payload", "digest"}


MERGE_STATE_KEYS = frozenset(
    {
        "schema",
        "chain_id",
        "kind",
        "state",
        "created_at",
        "last_event_at",
        "inactive_after",
        "owner",
        "run",
        "repository",
        "worktree",
        "branch",
        "target",
        "policy_source",
        "candidate",
        "tier",
        "steps",
        "review",
        "approval",
        "authorization",
        "integration",
        "cleanup",
        "run_binding",
        "journal_outbox",
    }
)


_MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES = frozenset(
    {
        "classifying",
        "verifying",
        "reviewing",
        "revising",
        "awaiting_approval",
        "authorized",
        "reverifying",
        "reverification_failed",
        "pushing",
    }
)


_MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES = frozenset(
    {"authorized", "awaiting_approval", "pushing"}
)


MERGE_EVENT_KEYS = frozenset(
    {
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
)


MERGE_EVENT_NAMES = frozenset(
    {
        "chain_started",
        "ownership_intent",
        "ownership_claimed",
        "ownership_release_intent",
        "ownership_released",
        "gate_recorded",
        "review_requested",
        "review_attached",
        "review_disposition",
        "approval_recorded",
        "generation_refreshed",
        "generation_carried_forward",
        "epoch_intent",
        "fetch_intent",
        "fetch_result",
        "rebase_intent",
        "rebase_conflict",
        "rebase_result",
        "reverification_result",
        "push_intent",
        "push_observed",
        "cleanup_intent",
        "cleanup_result",
        "condition_recorded",
        "lock_release_result",
        "aborted",
        "closed",
        "journal_receipted",
    }
)


MERGE_CONSEQUENTIAL_EVENTS = frozenset(
    {
        "gate_recorded",
        "review_attached",
        "approval_recorded",
        "generation_carried_forward",
        "push_observed",
    }
)


TIER_RANK = {"fast": 0, "standard": 1, "hard": 2}


INACTIVE_SECONDS = 24 * 60 * 60


FENCED_CHILD_ACK_TIMEOUT_SECONDS = 1.0


FENCED_CHILD_DRAIN_SECONDS = 0.1


FENCED_CHILD_DRAIN_CAP_BYTES = runtime.OUTPUT_CAP_BYTES + 1


FENCED_CHILD_STOP_GRACE_SECONDS = 0.25


FENCED_CHILD_REAP_SECONDS = 0.5


ZERO_DIGEST = "0" * 64


COMMON_LOCK_TIMEOUT_SECONDS = 300.0


COMMON_LOCK_POLL_SECONDS = 0.05


COMMON_LOCK_RECORD_CAP_BYTES = 16384


MERGE_SCOPE_BINDING_CAP_BYTES = 16384


COMMON_LOCK_INTENT_NAME = "agent-rebase.lock.intent"


COMMON_LOCK_DIRECTORY_NAME = "agent-rebase.lockdir"


COMMON_LOCK_OWNER_NAME = "owner.json"


COMMON_LOCK_FLOCK_NAME = "agent-rebase.lock"


COMMON_LOCK_RECOVERY_NAME = "agent-rebase.recover"


COMMON_LOCK_INFLIGHT_NAME = "agent-rebase.inflight"


COMMON_LOCK_OWNER_KINDS = frozenset({"merge", "push", "phase5"})


COMMON_LOCK_OPERATIONS = frozenset(
    {
        "start",
        "refresh",
        "finalize",
        "recover",
        "cleanup",
        "abort",
        "push",
        "phase5-scan",
    }
)


COMMON_LOCK_FENCE_OPERATIONS = frozenset(
    {
        "gate",
        "fetch",
        "tip-resolution",
        "remote-observation",
        "attribution-observation",
        "rebase",
        "continue",
        "abort",
        "push",
        "containment",
        "worktree-remove",
        "branch-delete",
    }
)


COMMON_LOCK_RECOVERY_KINDS = frozenset(
    {"fallback-owner", "fallback-owner-and-fence", "flock-held-dead-fence"}
)


_COMMON_LOCK_OWNER_KEYS = frozenset(
    {
        "schema",
        "owner_kind",
        "chain_id",
        "host",
        "pid",
        "nonce",
        "operation",
        "started_at",
    }
)


_COMMON_LOCK_FENCE_KEYS = frozenset(
    {
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
)


_COMMON_LOCK_RECOVERY_KEYS = frozenset(
    {
        "schema",
        "recovery_kind",
        "host",
        "pid",
        "nonce",
        "started_at",
        "stale_owner_inode",
        "stale_owner_digest",
        "stale_owner_host",
        "stale_owner_pid",
        "stale_owner_kind",
        "stale_owner_chain_id",
        "inflight_inode",
        "inflight_digest",
        "inflight_host",
        "inflight_pgid",
        "inflight_owner_kind",
        "inflight_chain_id",
        "owner_dead_at",
        "group_dead_at",
    }
)


_CHAIN_LEASE_KEYS = frozenset(
    {"chain_id", "host", "nonce", "pid", "session", "started_at"}
)


_REQUIRED_COMMON_LOCK_CONTROLS = frozenset(
    {
        "canonical-records",
        "no-replace-publication",
        "portable-before-flock",
        "single-deadline",
        "three-topology-recovery",
        "immutable-recovery-reservation",
        "reservation-held-lifecycle-classification",
        "death-proof-revalidation",
        "reverse-release-order",
        "release-identity-revalidation",
        "fence-start-pipe",
        "fence-intent-revalidation",
        "fence-result-before-release",
        "process-group-termination",
        "bounded-output",
        "chain-lease-hardlink",
        "chain-lease-write-revalidation",
    }
)


COMMON_LOCK_CONTROLS = _REQUIRED_COMMON_LOCK_CONTROLS


CHAIN_ID_RE = re.compile(r"^c-\d{4}-\d{2}-\d{2}T\d{6}Z-[0-9a-f]{4}$")


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


COMMIT_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")


RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


CHAIN_TOMBSTONE_SCHEMA = "forge-chain-tombstone/1"


CHAIN_TOMBSTONE_EVENT = "frozen-abort"


CHAIN_TOMBSTONE_KEYS = frozenset(
    {"schema", "chain_id", "event", "reason", "recorded_at", "operator", "artifacts"}
)


_REQUIRED_MERGE_STORE_CONTROLS = frozenset(
    {
        "event-first-family",
        "family-isolated-enumeration",
        "separate-merge-grammar",
        "lease-tail-authentication",
        "nonrecursive-source-digest",
        "typed-journal-builders",
        "consequential-event-set",
        "projected-journal-outbox",
        "builder-transition-validation",
        "event-before-state",
        "post-serialization-journal-drain",
        "replay-projection-repair",
    }
)


MERGE_STORE_CONTROLS = _REQUIRED_MERGE_STORE_CONTROLS


_REQUIRED_MERGE_ADAPTER_CONTROLS = frozenset(
    {
        "admission-and-generation",
        "halt",
        "ordered-gate-suite",
        "mandatory-review-final",
        "run-relative-evidence",
    }
)


MERGE_ADAPTER_CONTROLS = _REQUIRED_MERGE_ADAPTER_CONTROLS


_REQUIRED_MERGE_INTEGRATION_CONTROLS = frozenset(
    {
        "bounded-epoch-budget",
        "composite-bootstrap-streaming",
        "conflict-continue-contract",
        "final-intended-head-mode",
        "loud-recover-flags",
        "nonmovement-counter-reset",
        "sealed-gate-plan",
        "post-fetch-scope-proof",
        "observation-first-recovery",
        "nonforce-cleanup",
        "push-retry",
        "rebase-result-proof",
        "scope-release-clean-status",
        "scope-sidecar-recovery",
        "successor-ancestry-observation",
    }
)


MERGE_INTEGRATION_CONTROLS = _REQUIRED_MERGE_INTEGRATION_CONTROLS


INGEST_PROOF_ORDER = (
    "chain-schema-and-digest-replay",
    "materialized-state",
    "repository",
    "policy",
    "generation",
    "current-gates",
    "review-package",
    "reviewer-role",
    "reviewer-iteration",
    "reviewer-verdict",
    "operator-approval",
    "landing-proof",
    "monotonic-transitions",
    "closing-head-containment",
    "task-membership",
    "scope-membership",
)


_REQUIRED_INGEST_PROOF_CONTROLS = frozenset(INGEST_PROOF_ORDER)


INGEST_PROOF_CONTROLS = _REQUIRED_INGEST_PROOF_CONTROLS


_WORKTREE_LOCKS_GUARD = threading.Lock()


_WORKTREE_LOCKS: dict[str, threading.RLock] = {}


_WORKTREE_LOCK_STATE: dict[tuple[str, int], tuple[int, int]] = {}


@contextlib.contextmanager
def _exclusive_descriptor_lock(
    lock_key: str,
    opener: Callable[[], int],
    *,
    deadline: float | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> Iterable[None]:
    """Cross-process exclusive lock with safe same-thread re-entry."""
    with _WORKTREE_LOCKS_GUARD:
        local_lock = _WORKTREE_LOCKS.setdefault(lock_key, threading.RLock())

    def wait_for_deadline(stage: str) -> None:
        if deadline is None:
            return
        remaining = deadline - clock()
        if remaining <= 0:
            raise TimeoutError(f"{stage} exhausted the shared deadline")
        sleeper(min(COMMON_LOCK_POLL_SECONDS, remaining))

    if deadline is None:
        local_lock.acquire()
    else:
        while not local_lock.acquire(blocking=False):
            wait_for_deadline("process-local descriptor lock acquisition")
    try:
        state_key = (lock_key, threading.get_ident())
        with _WORKTREE_LOCKS_GUARD:
            held = _WORKTREE_LOCK_STATE.get(state_key)
            if held is not None:
                descriptor, depth = held
                _WORKTREE_LOCK_STATE[state_key] = (descriptor, depth + 1)
            else:
                descriptor = -1
        if held is None:
            descriptor = opener()
            try:
                opened = os.fstat(descriptor)
                if not stat.S_ISREG(opened.st_mode) or opened.st_uid != os.geteuid():
                    raise OSError("lock path is not an owner-controlled regular file")
                os.fchmod(descriptor, 0o600)
                if deadline is None:
                    fcntl.flock(descriptor, fcntl.LOCK_EX)
                else:
                    while True:
                        try:
                            fcntl.flock(
                                descriptor,
                                fcntl.LOCK_EX | fcntl.LOCK_NB,
                            )
                            break
                        except OSError as exc:
                            if exc.errno not in {errno.EACCES, errno.EAGAIN}:
                                raise
                            wait_for_deadline(
                                "cross-process descriptor lock acquisition"
                            )
            except BaseException:
                os.close(descriptor)
                raise
            with _WORKTREE_LOCKS_GUARD:
                _WORKTREE_LOCK_STATE[state_key] = (descriptor, 1)
        try:
            yield
        finally:
            release = False
            with _WORKTREE_LOCKS_GUARD:
                current_descriptor, depth = _WORKTREE_LOCK_STATE[state_key]
                if depth == 1:
                    del _WORKTREE_LOCK_STATE[state_key]
                    release = True
                else:
                    _WORKTREE_LOCK_STATE[state_key] = (
                        current_descriptor,
                        depth - 1,
                    )
            if release:
                try:
                    fcntl.flock(current_descriptor, fcntl.LOCK_UN)
                finally:
                    os.close(current_descriptor)
    finally:
        local_lock.release()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _chain_storage_root(repository: Path) -> Path:
    """Resolve the shared Git-common DM-012/DM-014 authority root."""

    runtime._coordination_modules()
    from codex_orchestrator.chain_paths import chain_storage_root

    return chain_storage_root(repository)


def _validated_commitment_path(
    label: str,
    value: str,
    *,
    repository: Path,
    run_dir: Path | None = None,
    direct_parent: Path | None = None,
    require_file: bool = False,
) -> object | None:
    """Project one CLI path decision through the shared FR-017 inventory."""

    runtime._coordination_modules()
    from commitment_paths import commitment_surface, validate_surface_path

    try:
        surface = commitment_surface(label)
    except KeyError:
        return None
    return validate_surface_path(
        surface,
        value,
        repository=repository,
        run_dir=run_dir,
        direct_parent=direct_parent,
        require_file=require_file,
    )


def _parsed_run_captured_path(value: str, run_id: str) -> object | None:
    """Apply the shared grammar for run-relative ingest captures."""

    runtime._coordination_modules()
    from commitment_paths import parse_run_captured_path

    return parse_run_captured_path(value, run_id=run_id)


def _require_ingest_proof(
    name: str, completed: list[str] | None = None
) -> None:
    """Fail closed when a named proof is disabled or reached out of order."""

    _batch, builders, journal = runtime._coordination_modules()
    if (
        name not in _REQUIRED_INGEST_PROOF_CONTROLS
        or name not in INGEST_PROOF_CONTROLS
        or (
            completed is not None
            and (
                len(completed) >= len(INGEST_PROOF_ORDER)
                or INGEST_PROOF_ORDER[len(completed)] != name
            )
        )
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    if completed is not None:
        completed.append(name)


def _merge_event_outbox(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    has_source = "source_event_digest" in payload
    has_batch = "journal_batch" in payload
    if not has_source and not has_batch:
        return None
    carried = payload.get("journal_batch")
    source = payload.get("source_event_digest")
    if (
        not has_source
        or not has_batch
        or not isinstance(source, str)
        or SHA256_RE.fullmatch(source) is None
        or not isinstance(carried, Mapping)
        or set(carried)
        != {"idempotency_key", "batch_digest", "record_count", "records"}
        or carried.get("idempotency_key") != source
        or not isinstance(carried.get("batch_digest"), str)
        or SHA256_RE.fullmatch(str(carried["batch_digest"])) is None
        or type(carried.get("record_count")) is not int
        or int(carried["record_count"]) <= 0
        or not isinstance(carried.get("records"), list)
        or len(carried["records"]) != carried["record_count"]
    ):
        raise ValueError("merge journal batch is malformed")
    return {
        "idempotency_key": source,
        "batch_digest": carried["batch_digest"],
        "record_count": carried["record_count"],
        "source_event_digest": source,
    }


def reduce_merge_event(
    previous: dict[str, object] | None, event: dict[str, object]
) -> dict[str, object]:
    """Reduce one DM-014 event from an explicit top-level delta only.

    The implementation-owned payload grammar is deliberately small:
    consequential and ordinary events carry ``payload.delta`` containing only
    changed materialized top-level members; the optional event-carried batch
    pair is adjacent in ``payload``.  ``payload.state`` is never consulted and
    is rejected as an unknown member.  ``journal_receipted`` instead carries
    only its exact three receipt members and clears the pending outbox.
    """

    if not isinstance(event, dict) or not isinstance(event.get("payload"), dict):
        raise ValueError("merge event payload is malformed")
    payload = event["payload"]
    assert isinstance(payload, dict)
    event_name = event.get("event")
    at = event.get("at")
    if not isinstance(at, str):
        raise ValueError("merge event timestamp is malformed")
    parsed_at = parse_time(at)

    if event_name == "journal_receipted":
        if previous is None or set(payload) != {
            "idempotency_key",
            "batch_digest",
            "receipt_digest",
        }:
            raise ValueError("merge receipt transition is malformed")
        state: dict[str, object] = copy.deepcopy(previous)
        state["journal_outbox"] = None
    else:
        _batch, builders, _journal = runtime._coordination_modules()
        try:
            delta = _merge_payload_delta(event, previous, builders=builders)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("merge transition lacks an explicit state delta")
        assert isinstance(delta, dict)
        if previous is None:
            if event_name != "chain_started":
                raise ValueError("merge history does not start with chain_started")
            state = copy.deepcopy(delta)
        else:
            if event_name == "chain_started":
                raise ValueError("merge chain_started is not repeatable")
            state = copy.deepcopy(previous)
            for name, value in delta.items():
                state[name] = copy.deepcopy(value)
        outbox = _merge_event_outbox(payload)
        if outbox is not None:
            state["journal_outbox"] = outbox
        elif "journal_outbox" not in state:
            state["journal_outbox"] = None
    state["last_event_at"] = at
    prior_deadline = None
    if previous is not None:
        deadline_value = previous.get("inactive_after")
        if not isinstance(deadline_value, str):
            raise ValueError("merge inactivity deadline is malformed")
        prior_deadline = parse_time(deadline_value)
    if prior_deadline is not None and parsed_at >= prior_deadline:
        state["inactive_after"] = str(previous["inactive_after"])
    else:
        state["inactive_after"] = (
            parsed_at + dt.timedelta(seconds=INACTIVE_SECONDS)
        ).isoformat().replace("+00:00", "Z")
    return state


def _merge_gate_plan_valid(
    value: object,
    *,
    generation_digest: str | None = None,
    policy_digest: str | None = None,
) -> bool:
    """Validate Revision-10's exact sealed/unsealed epoch plan grammar."""

    if not isinstance(value, dict) or set(value) != {
        "status",
        "generation_digest",
        "policy_digest",
        "suite",
        "suite_digest",
        "cursor",
        "seal_event_digest",
    }:
        return False
    if value.get("status") == "unsealed":
        return all(value.get(name) is None for name in set(value) - {"status"})
    if value.get("status") != "sealed":
        return False
    suite = value.get("suite")
    cursor = value.get("cursor")
    if (
        not isinstance(value.get("generation_digest"), str)
        or SHA256_RE.fullmatch(str(value["generation_digest"])) is None
        or not isinstance(value.get("policy_digest"), str)
        or SHA256_RE.fullmatch(str(value["policy_digest"])) is None
        or not isinstance(suite, list)
        or type(cursor) is not int
        or int(cursor) < 0
        or int(cursor) > len(suite)
        or not isinstance(value.get("suite_digest"), str)
        or value.get("suite_digest") != sha256_bytes(canonical_bytes(suite))
        or not isinstance(value.get("seal_event_digest"), str)
        or SHA256_RE.fullmatch(str(value["seal_event_digest"])) is None
        or (
            generation_digest is not None
            and value.get("generation_digest") != generation_digest
        )
        or (
            policy_digest is not None
            and value.get("policy_digest") != policy_digest
        )
    ):
        return False
    for member in suite:
        if (
            not isinstance(member, dict)
            or set(member) != {"kind", "id"}
            or member.get("kind") not in {"gate", "scoped-mutation"}
            or not isinstance(member.get("id"), str)
            or not member["id"]
            or (
                member.get("kind") == "scoped-mutation"
                and member.get("id") != "scoped-mutation"
            )
        ):
            return False
    return True


def _merge_epoch_valid(state: Mapping[str, Any]) -> bool:
    integration = state.get("integration")
    if not isinstance(integration, Mapping):
        return False
    epoch = integration.get("epoch")
    if epoch is None:
        return True
    candidate = state.get("candidate")
    policy = state.get("policy_source")
    if (
        not isinstance(epoch, Mapping)
        or set(epoch)
        != {
            "operation_nonce",
            "generation_digest",
            "intent_digest",
            "started_at",
            "gate_plan",
        }
        or not _valid_nonce(epoch.get("operation_nonce"))
        or not isinstance(epoch.get("generation_digest"), str)
        or SHA256_RE.fullmatch(str(epoch["generation_digest"])) is None
        or not isinstance(epoch.get("intent_digest"), str)
        or SHA256_RE.fullmatch(str(epoch["intent_digest"])) is None
        or not _valid_utc_second(epoch.get("started_at"))
        or not isinstance(candidate, Mapping)
        or epoch.get("generation_digest") != candidate.get("generation_digest")
        or not isinstance(policy, Mapping)
        or not _merge_gate_plan_valid(
            epoch.get("gate_plan"),
            generation_digest=str(candidate.get("generation_digest", "")),
            policy_digest=(
                str(policy.get("digest", ""))
                if isinstance(epoch.get("gate_plan"), Mapping)
                and epoch["gate_plan"].get("status") == "sealed"
                else None
            ),
        )
    ):
        return False
    return True


def _merge_payload_delta(
    event: Mapping[str, Any],
    previous: Mapping[str, Any] | None,
    *,
    builders: Any,
) -> dict[str, Any]:
    """Reduce the Revision-10 additions without widening legacy payloads."""

    payload = event.get("payload")
    event_name = event.get("event")
    if not isinstance(payload, Mapping):
        raise ValueError("merge transition payload is malformed")
    generation_digest = event.get("generation_digest")
    if (
        event_name == "fetch_intent"
        and generation_digest is None
        and "scope_request" in payload
    ):
        expected = {
            "repository",
            "worktree",
            "branch",
            "target",
            "pre_fetch_head",
            "policy_digest",
            "operation_nonce",
            "attempt",
            "scope_request",
        }
        if previous is None or set(payload) != expected:
            raise ValueError("merge bootstrap scope intent is malformed")
        integration = copy.deepcopy(previous.get("integration"))
        if not isinstance(integration, dict):
            raise ValueError("merge fetch projection is malformed")
        integration["intent"] = {"operation": "fetch", **copy.deepcopy(dict(payload))}
        return {"integration": integration}

    extra_result_members = {"scope_fetch_binding", "scope_proof"}
    if event_name == "generation_carried_forward":
        allowed = {
            "delta",
            "prior_generation_digest",
            "successor_generation_digest",
            "equality_proof",
        }
        if "source_event_digest" in payload or "journal_batch" in payload:
            allowed.update({"source_event_digest", "journal_batch"})
        if set(payload) != allowed or not isinstance(payload.get("delta"), Mapping):
            raise ValueError("merge carry-forward payload is malformed")
        projected = copy.deepcopy(dict(payload["delta"]))
    elif event_name == "fetch_result" and extra_result_members <= set(payload):
        allowed = {"delta", *extra_result_members}
        if "source_event_digest" in payload or "journal_batch" in payload:
            allowed.update({"source_event_digest", "journal_batch"})
        if set(payload) != allowed or not isinstance(payload.get("delta"), Mapping):
            raise ValueError("merge scope fetch result payload is malformed")
        projected = copy.deepcopy(dict(payload["delta"]))
    elif event_name == "cleanup_result" and "cleanup_results" in payload:
        if set(payload) != {"delta", "cleanup_results"} or not isinstance(
            payload.get("delta"), Mapping
        ):
            raise ValueError("merge cleanup result payload is malformed")
        projected = copy.deepcopy(dict(payload["delta"]))
    elif event_name in {"epoch_intent", "condition_recorded"} and isinstance(
        payload.get("delta"), Mapping
    ):
        allowed = {"delta"}
        if event_name == "condition_recorded" and "recovery_proof" in payload:
            allowed.add("recovery_proof")
        if "source_event_digest" in payload or "journal_batch" in payload:
            allowed.update({"source_event_digest", "journal_batch"})
        if set(payload) != allowed or not isinstance(payload.get("delta"), Mapping):
            raise ValueError("merge integration intent payload is malformed")
        projected = copy.deepcopy(dict(payload["delta"]))
    else:
        projected = builders._merge_payload_delta(dict(event), previous)

    integration = projected.get("integration")
    epoch = integration.get("epoch") if isinstance(integration, dict) else None
    if isinstance(epoch, dict):
        if event_name == "epoch_intent":
            if epoch.get("intent_digest") is not None:
                raise ValueError("merge epoch intent digest slot is not null")
            epoch["intent_digest"] = event.get("digest")
        plan = epoch.get("gate_plan")
        if (
            isinstance(plan, dict)
            and plan.get("status") == "sealed"
            and plan.get("seal_event_digest") is None
        ):
            if event_name not in {
                "epoch_intent",
                "fetch_result",
                "rebase_result",
                "generation_carried_forward",
            }:
                raise ValueError("merge gate plan has an unauthorized sealer")
            plan["seal_event_digest"] = event.get("digest")
    return projected


def _merge_bootstrap_classification_pending(
    state: Mapping[str, Any] | None,
) -> bool:
    """Recognize Revision-12's sole complete-but-unclassified generation.

    The shared Revision-9 builder couples a non-null candidate to a populated
    tier.  Revision 12 deliberately separates those facts across the
    successful ``fetch_result`` and the later ``generation_refreshed`` event,
    so this predicate is kept deliberately narrow before the compatibility
    projection supplies the legacy validator's in-memory tier shape.
    """

    if not isinstance(state, Mapping):
        return False
    candidate = state.get("candidate")
    policy_source = state.get("policy_source")
    worktree = state.get("worktree")
    claim = worktree.get("claim") if isinstance(worktree, Mapping) else None
    review = state.get("review")
    integration = state.get("integration")
    intent = integration.get("intent") if isinstance(integration, Mapping) else None
    return bool(
        state.get("state") in {"classifying", "aborted"}
        and isinstance(candidate, Mapping)
        and isinstance(policy_source, Mapping)
        and policy_source.get("commit") == candidate.get("policy_commit")
        and policy_source.get("digest") == candidate.get("policy_digest")
        and isinstance(claim, Mapping)
        and (
            state.get("state") == "classifying"
            and claim.get("status") in {"owned", "releasing", "released"}
            or state.get("state") == "aborted"
            and claim.get("status") == "released"
        )
        and state.get("tier") is None
        and state.get("steps") == {}
        and (
            review == {}
            or isinstance(review, Mapping)
            and set(review) == {"iteration"}
            and type(review.get("iteration")) is int
            and 0 <= int(review["iteration"]) <= 8
        )
        and state.get("approval") == {}
        and state.get("authorization") == {}
        and isinstance(integration, Mapping)
        and integration.get("condition") == "none"
        and integration.get("primary_condition") == "none"
        and integration.get("epoch") is None
        and integration.get("observed") is None
        and integration.get("pre_rebase") is None
        and integration.get("conflict") is None
        and integration.get("push") is None
        and isinstance(intent, Mapping)
        and set(intent)
        == {
            "operation",
            "operation_nonce",
            "attempt",
            "result",
            "resolved_tip",
        }
        and intent.get("operation") == "fetch-result"
        and _valid_nonce(intent.get("operation_nonce"))
        and _valid_positive_int(intent.get("attempt"))
        and intent.get("result") == "success"
        and COMMIT_RE.fullmatch(str(intent.get("resolved_tip", ""))) is not None
        and intent.get("resolved_tip") == candidate.get("remote_tip")
    )


def _merge_revision9_compatibility_view(
    event: Mapping[str, Any] | None,
    state: Mapping[str, Any] | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Project only Revision-10 additive members away for the shared validator."""

    classification_pending = _merge_bootstrap_classification_pending(state)
    compat_state = copy.deepcopy(dict(state)) if isinstance(state, Mapping) else None
    if compat_state is not None:
        if classification_pending:
            # Validator-only projection.  This value is never durable and is
            # intentionally not the result of risk classification.
            if compat_state.get("state") == "classifying":
                compat_state["state"] = "verifying"
            compat_state["tier"] = {"control": False, "categories": []}
        steps = compat_state.get("steps")
        if isinstance(steps, dict):
            # Revision 10 gives scoped mutation its own sealed-plan position;
            # Revision 9 represented the same proof only inside Gate 1.
            steps.pop("scoped-mutation", None)
        integration = compat_state.get("integration")
        if isinstance(integration, dict):
            epoch = integration.get("epoch")
            if isinstance(epoch, dict):
                epoch.pop("gate_plan", None)
            intent = integration.get("intent")
            if isinstance(intent, dict):
                intent.pop("scope_request", None)
    compat_event = copy.deepcopy(dict(event)) if isinstance(event, Mapping) else None
    if compat_event is not None and isinstance(compat_event.get("payload"), dict):
        payload = compat_event["payload"]
        if compat_event.get("event") == "fetch_intent":
            payload.pop("scope_request", None)
        if compat_event.get("event") == "fetch_result":
            payload.pop("scope_fetch_binding", None)
            payload.pop("scope_proof", None)
        if compat_event.get("event") == "cleanup_result":
            payload.pop("cleanup_results", None)
        if compat_event.get("event") == "generation_carried_forward":
            payload.pop("prior_generation_digest", None)
            payload.pop("successor_generation_digest", None)
            payload.pop("equality_proof", None)
        if compat_event.get("event") == "condition_recorded":
            payload.pop("recovery_proof", None)
        if (
            classification_pending
            and compat_event.get("event") == "ownership_release_intent"
            and payload.get("source_state") == "classifying"
        ):
            payload["source_state"] = "verifying"
        delta = payload.get("delta")
        if (
            classification_pending
            and compat_event.get("event") == "fetch_result"
            and isinstance(delta, dict)
        ):
            # The successful fetch introduces the candidate while the durable
            # tier remains null.  Mirror only the compatibility state's
            # validator-only legacy shape in the copied event delta.
            delta["state"] = "verifying"
            delta["tier"] = {"control": False, "categories": []}
        if isinstance(delta, dict) and isinstance(delta.get("steps"), dict):
            delta["steps"].pop("scoped-mutation", None)
        if isinstance(delta, dict) and isinstance(delta.get("integration"), dict):
            epoch = delta["integration"].get("epoch")
            if isinstance(epoch, dict):
                epoch.pop("gate_plan", None)
            intent = delta["integration"].get("intent")
            if isinstance(intent, dict):
                intent.pop("scope_request", None)
    return compat_event, compat_state


def _merge_state_shape_valid(
    builders: Any, state: Mapping[str, Any], chain_id: str
) -> bool:
    if not _merge_epoch_valid(state):
        return False
    _event, compat = _merge_revision9_compatibility_view(None, state)
    return bool(
        compat is not None and builders._state_shape_valid(compat, chain_id, "merge")
    )


def _merge_ingest_state_shape_valid(
    builders: Any, state: Mapping[str, Any], chain_id: str
) -> bool:
    """Accept immutable Revision-9 captures without widening live replay."""

    return bool(
        _merge_state_shape_valid(builders, state, chain_id)
        or builders._state_shape_valid(state, chain_id, "merge")
    )


def _merge_history_uses_additive_grammar(
    history: Sequence[Mapping[str, Any]],
) -> bool:
    """Select the strict grammar only after a genuine additive carrier."""

    for event in history:
        payload = event.get("payload")
        if not isinstance(payload, Mapping):
            continue
        if any(
            name in payload
            for name in ("scope_request", "scope_fetch_binding", "cleanup_results")
        ):
            return True
        delta = payload.get("delta")
        if not isinstance(delta, Mapping):
            continue
        cleanup = delta.get("cleanup")
        cleanup_intent = (
            cleanup.get("intent") if isinstance(cleanup, Mapping) else None
        )
        if (
            event.get("event") == "cleanup_intent"
            and isinstance(cleanup_intent, Mapping)
            and cleanup_intent.get("schema")
            == "forge-merge-cleanup-step-intent/1"
        ):
            return True
        integration = delta.get("integration")
        epoch = (
            integration.get("epoch") if isinstance(integration, Mapping) else None
        )
        if isinstance(epoch, Mapping) and "gate_plan" in epoch:
            return True
        approval = delta.get("approval")
        if (
            event.get("event") == "approval_recorded"
            and isinstance(approval, Mapping)
            and approval.get("purpose") == "remote-churn"
        ):
            return True
    return False


def _merge_ingest_transition_valid(
    builders: Any,
    event: Mapping[str, Any],
    prior: Mapping[str, Any] | None,
    current: Mapping[str, Any],
    *,
    context: MutableMapping[str, Any],
    history: Sequence[Mapping[str, Any]] = (),
) -> bool:
    """Keep captured Revision-9 epochs on their immutable grammar."""

    if not _merge_history_uses_additive_grammar((*history, event)):
        return bool(
            builders._merge_transition_valid(
                event, prior, current, context=context
            )
        )
    return _merge_transition_valid(
        builders,
        event,
        prior,
        current,
        context=context,
        history=history,
    )


def _merge_plan_position_fact(
    prior: Mapping[str, Any], current: Mapping[str, Any]
) -> Mapping[str, Any] | None:
    prior_steps = prior.get("steps")
    current_steps = current.get("steps")
    if not isinstance(prior_steps, Mapping) or not isinstance(current_steps, Mapping):
        return None
    for step_id, current_value in current_steps.items():
        prior_value = prior_steps.get(step_id)
        if current_value == prior_value:
            continue
        if isinstance(current_value, list) and current_value:
            fact = current_value[-1]
            if isinstance(fact, Mapping) and isinstance(
                fact.get("gate_plan_position"), Mapping
            ):
                return fact
    return None


def _merge_carried_gate_steps(
    steps: object,
    *,
    prior_generation_digests: Collection[str],
    successor_generation_digest: str,
) -> dict[str, Any]:
    """Build a compatibility projection without rewriting durable gate facts.

    FR-234 retains the predecessor records byte-for-byte.  The shared
    Revision-9 validator predates that rule and expects current-generation
    mechanical facts while it validates the next epoch, so this helper is
    used only on an in-memory compatibility copy.  Fresh successor facts may
    already be present later in a run list and are left unchanged.
    """

    if not isinstance(steps, Mapping):
        raise ValueError("merge carried gate steps are malformed")
    carried = copy.deepcopy(dict(steps))
    admitted_predecessors = frozenset(prior_generation_digests)
    if not all(SHA256_RE.fullmatch(digest) for digest in admitted_predecessors):
        raise ValueError("merge carried gate generation history is malformed")

    def rebind(value: object) -> None:
        if isinstance(value, dict):
            if "generation_digest" in value:
                if value["generation_digest"] in admitted_predecessors:
                    value["generation_digest"] = successor_generation_digest
                elif value["generation_digest"] != successor_generation_digest:
                    raise ValueError("merge carried gate fact is not predecessor-bound")
            for member in value.values():
                rebind(member)
        elif isinstance(value, list):
            for member in value:
                rebind(member)

    rebind(carried)
    return carried


def _merge_gate_step_generation_digests(steps: object) -> frozenset[str]:
    """Collect only generation digests from an authenticated prior step tree."""

    if not isinstance(steps, Mapping):
        raise ValueError("merge carried gate steps are malformed")
    digests: set[str] = set()

    def collect(value: object) -> None:
        if isinstance(value, Mapping):
            if "generation_digest" in value:
                digest = value["generation_digest"]
                if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
                    raise ValueError("merge carried gate generation history is malformed")
                digests.add(digest)
            for member in value.values():
                collect(member)
        elif isinstance(value, list):
            for member in value:
                collect(member)

    collect(steps)
    return frozenset(digests)


def _merge_current_authority_valid(state: Mapping[str, Any]) -> bool:
    """Recognize retained Gate-4 authority and an exact churn re-arm."""

    candidate = state.get("candidate")
    authorization = state.get("authorization")
    review = state.get("review")
    verdict = review.get("verdict") if isinstance(review, Mapping) else None
    if not isinstance(candidate, Mapping) or not isinstance(
        authorization, Mapping
    ):
        return False
    authorization_digest = str(authorization.get("generation_digest", ""))
    if not (
        authorization.get("candidate_head") == candidate.get("candidate_head")
        and SHA256_RE.fullmatch(authorization_digest) is not None
        and isinstance(verdict, Mapping)
        and verdict.get("verdict") == "PASS"
    ):
        return False
    tier = state.get("tier")
    approval = state.get("approval")
    if not isinstance(tier, Mapping):
        return False
    if tier.get("control") is not True and not (
        isinstance(approval, Mapping) and approval.get("purpose") == "remote-churn"
    ):
        return True
    if not (
        isinstance(approval, Mapping)
        and approval.get("chain_id") == state.get("chain_id")
        and approval.get("candidate") == candidate.get("candidate_head")
    ):
        return False
    purpose = approval.get("purpose")
    approval_digest = str(approval.get("generation_digest", ""))
    if purpose == "gate-4":
        return approval_digest == authorization_digest
    if purpose == "remote-churn":
        # Replay admits this record only after eight authenticated remote-only
        # defeats of an already-authorized tuple.  It acknowledges that exact
        # candidate and re-arms one later epoch without rewriting the retained
        # Gate-4 decision or its immutable generation binding.
        return SHA256_RE.fullmatch(approval_digest) is not None
    return False


_MERGE_REMOTE_ONLY_IDENTITY_FIELDS = (
    "remote",
    "destination_ref",
    "candidate_head",
    "diff_sha256",
    "policy_commit",
    "policy_digest",
    "worktree_identity",
)


def _merge_remote_only_equality_proof(
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    """Return DM-014's explicit equality witness for a remote-only successor."""

    return {
        name: copy.deepcopy(candidate.get(name))
        for name in _MERGE_REMOTE_ONLY_IDENTITY_FIELDS
    }


def _merge_carry_payload_valid(
    event: Mapping[str, Any],
    prior_candidate: Mapping[str, Any],
    carried_candidate: Mapping[str, Any],
) -> bool:
    payload = event.get("payload")
    required = {
        "delta",
        "prior_generation_digest",
        "successor_generation_digest",
        "equality_proof",
    }
    if not isinstance(payload, Mapping):
        return False
    members = frozenset(payload)
    if members not in {
        frozenset(required),
        frozenset({*required, "source_event_digest", "journal_batch"}),
    }:
        return False
    proof = payload.get("equality_proof")
    expected = _merge_remote_only_equality_proof(prior_candidate)
    return bool(
        payload.get("prior_generation_digest")
        == prior_candidate.get("generation_digest")
        and payload.get("successor_generation_digest")
        == carried_candidate.get("generation_digest")
        and proof == expected
        and proof == _merge_remote_only_equality_proof(carried_candidate)
    )


def _merge_plan_transition_valid(
    event: Mapping[str, Any],
    prior: Mapping[str, Any] | None,
    current: Mapping[str, Any],
) -> bool:
    if prior is None:
        return current.get("integration", {}).get("epoch") is None
    prior_integration = prior.get("integration")
    current_integration = current.get("integration")
    if not isinstance(prior_integration, Mapping) or not isinstance(
        current_integration, Mapping
    ):
        return False
    before = prior_integration.get("epoch")
    after = current_integration.get("epoch")
    event_name = event.get("event")
    if event_name == "epoch_intent":
        if not isinstance(after, Mapping) or after == before:
            return False
        plan = after.get("gate_plan")
        normal = (
            prior.get("state") == "authorized"
            and current.get("state") == "rebasing"
            and isinstance(plan, Mapping)
            and plan.get("status") == "unsealed"
        )
        retry = (
            prior.get("state") == "reverification_failed"
            and current.get("state") == "reverifying"
            and isinstance(plan, Mapping)
            and plan.get("status") == "sealed"
            and plan.get("seal_event_digest") == event.get("digest")
        )
        return bool(
            (normal or retry)
            and after.get("intent_digest") == event.get("digest")
        )
    if before is None:
        return after is None
    if after is None:
        return event_name in {
            "generation_refreshed",
            "generation_carried_forward",
            "fetch_result",
            "push_intent",
            "push_observed",
            "rebase_result",
            "reverification_result",
            "condition_recorded",
            "ownership_release_intent",
            "aborted",
            "closed",
        }
    if not isinstance(before, Mapping) or not isinstance(after, Mapping):
        return False
    identity_changed = any(
        before.get(name) != after.get(name)
        for name in ("operation_nonce", "generation_digest", "intent_digest", "started_at")
    )
    if identity_changed:
        successor = bool(
            event_name in {"rebase_result", "generation_carried_forward"}
            and before.get("operation_nonce") == after.get("operation_nonce")
            and before.get("intent_digest") == after.get("intent_digest")
            and before.get("started_at") == after.get("started_at")
            and before.get("gate_plan", {}).get("status") == "unsealed"
            and after.get("gate_plan", {}).get("status") == "sealed"
        )
        if not successor:
            return False
    before_plan = before.get("gate_plan")
    after_plan = after.get("gate_plan")
    if before_plan == after_plan:
        return True
    if not isinstance(before_plan, Mapping) or not isinstance(after_plan, Mapping):
        return False
    if (
        before_plan.get("status") == "unsealed"
        and after_plan.get("status") == "sealed"
    ):
        return bool(
            event_name
            in {"fetch_result", "rebase_result", "generation_carried_forward"}
            and after_plan.get("seal_event_digest") == event.get("digest")
            and after_plan.get("cursor") == 0
        )
    if event_name != "gate_recorded":
        return False
    immutable = {
        "status",
        "generation_digest",
        "policy_digest",
        "suite",
        "suite_digest",
        "seal_event_digest",
    }
    if any(before_plan.get(name) != after_plan.get(name) for name in immutable):
        return False
    cursor = before_plan.get("cursor")
    suite = before_plan.get("suite")
    if (
        type(cursor) is not int
        or not isinstance(suite, list)
        or cursor >= len(suite)
        or after_plan.get("cursor") != cursor + 1
    ):
        return False
    fact = _merge_plan_position_fact(prior, current)
    position = fact.get("gate_plan_position") if isinstance(fact, Mapping) else None
    selected = suite[cursor]
    return bool(
        isinstance(position, Mapping)
        and set(position)
        == {"seal_event_digest", "suite_digest", "cursor", "kind", "id"}
        and position.get("seal_event_digest") == before_plan.get("seal_event_digest")
        and position.get("suite_digest") == before_plan.get("suite_digest")
        and position.get("cursor") == cursor
        and position.get("kind") == selected.get("kind")
        and position.get("id") == selected.get("id")
        and fact.get("gate_intent_digest") is not None
        and SHA256_RE.fullmatch(str(fact["gate_intent_digest"])) is not None
        and fact.get("inflight_digest") is not None
        and SHA256_RE.fullmatch(str(fact["inflight_digest"])) is not None
    )


def _validate_merge_scope_proof(
    value: object,
    *,
    state: Mapping[str, Any],
    binding: Mapping[str, Any],
    scope_request: Mapping[str, Any],
) -> bool:
    if not isinstance(value, dict) or set(value) != {
        "schema",
        "run_id",
        "task_id",
        "generation_digest",
        "remote_tip",
        "candidate_head",
        "command_template_digest",
        "command_digest",
        "environment_digest",
        "scope_fetch_binding_digest",
        "output_digest",
        "task_files",
        "admitted_scope",
        "changed_paths",
        "out_of_scope_paths",
        "result",
        "digest",
    }:
        return False
    candidate = state.get("candidate")
    body = {name: value[name] for name in value if name != "digest"}
    containment_valid = False
    if (
        _valid_sorted_unique_strings(value.get("changed_paths"))
        and _valid_sorted_unique_strings(value.get("out_of_scope_paths"))
        and _valid_sorted_unique_strings(value.get("task_files"))
        and _valid_sorted_unique_strings(value.get("admitted_scope"))
    ):
        try:
            _batch, _builders, journal = runtime._coordination_modules()
            expected_out_of_scope = [
                path
                for path in value["changed_paths"]
                if not any(
                    journal.pathspec_contained(path, pattern)
                    for pattern in value["task_files"]
                )
                or not any(
                    journal.pathspec_contained(path, pattern)
                    for pattern in value["admitted_scope"]
                )
            ]
            containment_valid = value["out_of_scope_paths"] == expected_out_of_scope
        except (OSError, RuntimeError, TypeError, ValueError):
            containment_valid = False
    return bool(
        value.get("schema") == "forge-run-scope-proof/1"
        and isinstance(candidate, Mapping)
        and value.get("run_id") == scope_request.get("run_id")
        and value.get("task_id") == scope_request.get("task_id")
        and value.get("generation_digest") == candidate.get("generation_digest")
        and value.get("remote_tip") == candidate.get("remote_tip")
        and value.get("candidate_head") == candidate.get("candidate_head")
        and value.get("command_template_digest")
        == scope_request.get("command_template_digest")
        == binding.get("command_template_digest")
        and value.get("command_digest") == binding.get("command_digest")
        and value.get("environment_digest")
        == scope_request.get("environment_digest")
        == binding.get("environment_digest")
        and value.get("scope_fetch_binding_digest") == binding.get("digest")
        and isinstance(value.get("output_digest"), str)
        and SHA256_RE.fullmatch(value["output_digest"]) is not None
        and value.get("output_digest")
        == binding.get("child_result", {}).get("output_digest")
        and value.get("task_files") == scope_request.get("task_files")
        and value.get("admitted_scope") == scope_request.get("admitted_scope")
        and _valid_sorted_unique_strings(value.get("changed_paths"))
        and _valid_sorted_unique_strings(value.get("out_of_scope_paths"))
        and containment_valid
        and value.get("result")
        == ("exceeded" if value["out_of_scope_paths"] else "contained")
        and value.get("digest") == sha256_bytes(canonical_bytes(body))
    )


def _merge_scope_event_binding_valid(
    binding: Mapping[str, Any],
    *,
    prior: Mapping[str, Any],
    fetch_intent_digest: str,
    scope_request: Mapping[str, Any] | None,
) -> bool:
    """Revalidate a copied Revision-12 sidecar against replay context."""

    retained = binding.get("retained_inflight")
    if not isinstance(retained, Mapping):
        return False
    try:
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
        fence = PublishedLockRecord(
            path=str(retained["path"]),
            device=int(retained["device"]),
            inode=int(retained["inode"]),
            digest=str(retained["inflight_digest"]),
            record=retained_record,
            mode=0o600,
            links=1,
        )
        validator = _merge_scope_binding_validator(
            prior,
            fetch_intent_digest=fetch_intent_digest,
            scope_request=scope_request,
            fence=fence,
        )
        validator(dict(binding))
    except (KeyError, OSError, TypeError, ValueError, Refusal):
        return False
    return True


def _merge_scope_transition_valid(
    event: Mapping[str, Any],
    prior: Mapping[str, Any] | None,
    current: Mapping[str, Any],
) -> bool:
    """Authenticate Revision-10 scope additions before legacy projection."""

    if prior is None:
        return True
    event_name = event.get("event")
    payload = event.get("payload")
    if not isinstance(payload, Mapping):
        return False
    if event_name == "fetch_intent":
        if event.get("generation_digest") is None:
            if "scope_request" not in payload:
                # Pre-Revision-10 fixture/events remain replayable; every
                # newly emitted bootstrap intent includes the additive slot.
                return True
            scope_request = payload.get("scope_request")
        else:
            delta = payload.get("delta")
            integration = (
                delta.get("integration") if isinstance(delta, Mapping) else None
            )
            intent = (
                integration.get("intent")
                if isinstance(integration, Mapping)
                else None
            )
            scope_request = (
                intent.get("scope_request")
                if isinstance(intent, Mapping)
                else None
            )
        if scope_request is None and prior.get("run_binding") is None:
            # Legacy fixtures remain replayable while all newly produced
            # bootstrap intents use the Revision-10 exact member.
            return True
        try:
            _validate_merge_scope_request(scope_request, state=current)
        except (KeyError, TypeError, ValueError):
            return False
        return True
    if event_name != "fetch_result":
        return True
    has_binding = "scope_fetch_binding" in payload
    has_proof = "scope_proof" in payload
    if not has_binding and not has_proof:
        return True
    if has_binding != has_proof:
        return False
    scope_request = prior.get("integration", {}).get("intent", {}).get(
        "scope_request"
    )
    sidecar = payload.get("scope_fetch_binding")
    proof = payload.get("scope_proof")
    if sidecar is None:
        return proof is None and (
            current.get("candidate") is None
            or current.get("candidate") == prior.get("candidate")
        )
    try:
        binding = _validate_merge_scope_fetch_binding(sidecar)
    except (KeyError, TypeError, ValueError):
        return False
    source_intent_digest = str(binding.get("fetch_intent_digest", ""))
    if SHA256_RE.fullmatch(source_intent_digest) is None:
        return False
    if not _merge_scope_event_binding_valid(
        binding,
        prior=prior,
        fetch_intent_digest=source_intent_digest,
        scope_request=(
            scope_request if isinstance(scope_request, Mapping) else None
        ),
    ):
        return False
    candidate = current.get("candidate")
    if (
        binding.get("chain_id") != current.get("chain_id")
        or (
            isinstance(candidate, Mapping)
            and (
                binding.get("candidate_head")
                != candidate.get("candidate_head")
                or binding.get("remote_tip") != candidate.get("remote_tip")
                or binding.get("full_patch_output_digest")
                != candidate.get("diff_sha256")
            )
        )
    ):
        return False
    if scope_request is None:
        return bool(
            binding.get("scope_request_digest") is None
            and binding.get("command_template_digest") is None
            and binding.get("command_digest") is None
            and proof is None
            and isinstance(candidate, Mapping)
        )
    if (
        binding.get("scope_request_digest")
        != sha256_bytes(canonical_bytes(scope_request))
        or binding.get("candidate_head")
        != scope_request.get("command_template", {}).get("candidate_head")
    ):
        return False
    if proof is None:
        return current.get("candidate") is None
    return _validate_merge_scope_proof(
        proof,
        state=current,
        binding=binding,
        scope_request=scope_request,
    )


def _published_recovery_evidence_valid(
    value: object,
    *,
    path: Path,
    validator: Callable[[Any], dict[str, Any]],
) -> bool:
    if not isinstance(value, Mapping) or set(value) != {
        "path",
        "device",
        "inode",
        "digest",
        "record",
    }:
        return False
    try:
        record = validator(copy.deepcopy(value.get("record")))
    except (TypeError, ValueError):
        return False
    return bool(
        value.get("path") == str(path)
        and _valid_nonnegative_int(value.get("device"))
        and _valid_nonnegative_int(value.get("inode"))
        and SHA256_RE.fullmatch(str(value.get("digest", ""))) is not None
        and value.get("digest") == sha256_bytes(canonical_bytes(record))
    )


def _recovery_event_intent(event: Mapping[str, Any]) -> Mapping[str, Any] | None:
    payload = event.get("payload")
    delta = payload.get("delta") if isinstance(payload, Mapping) else None
    integration = delta.get("integration") if isinstance(delta, Mapping) else None
    intent = integration.get("intent") if isinstance(integration, Mapping) else None
    return intent if isinstance(intent, Mapping) else None


def _recovery_value_carries_inflight(value: object, digest: str) -> bool:
    """Find only an explicitly named child-result fence digest."""

    if isinstance(value, Mapping):
        return (
            value.get("inflight_digest") == digest
            or value.get("fence_digest") == digest
            or any(
                _recovery_value_carries_inflight(member, digest)
                for name, member in value.items()
                if name != "recovery_proof"
            )
        )
    if isinstance(value, list):
        return any(
            _recovery_value_carries_inflight(member, digest) for member in value
        )
    return False


def _recovery_cleanup_intent(
    event: Mapping[str, Any] | None,
) -> Mapping[str, Any] | None:
    payload = event.get("payload") if isinstance(event, Mapping) else None
    delta = payload.get("delta") if isinstance(payload, Mapping) else None
    cleanup = delta.get("cleanup") if isinstance(delta, Mapping) else None
    intent = cleanup.get("intent") if isinstance(cleanup, Mapping) else None
    return intent if isinstance(intent, Mapping) else None


def _recovery_cleanup_result_matches(
    event: Mapping[str, Any],
    state: Mapping[str, Any],
    intent: Mapping[str, Any],
    *,
    intent_digest: str,
    fence_digest: str,
    fence_operation: str,
) -> bool:
    payload = event.get("payload")
    results = (
        payload.get("cleanup_results") if isinstance(payload, Mapping) else None
    )
    result = (
        results[0]
        if isinstance(results, list)
        and len(results) == 1
        and isinstance(results[0], Mapping)
        else None
    )
    process = result.get("process") if isinstance(result, Mapping) else None
    return bool(
        event.get("event") == "cleanup_result"
        and isinstance(result, Mapping)
        and isinstance(process, Mapping)
        and result.get("intent_event_digest") == intent_digest
        and result.get("fence_operation") == fence_operation
        and process.get("fence_digest") == fence_digest
        and _merge_cleanup_step_result_valid(
            result, state, intent, intent_digest
        )
    )


def _classify_merge_recovery_lifecycle(
    state: Mapping[str, Any],
    history: Sequence[Mapping[str, Any]],
    *,
    fence_record: Mapping[str, Any],
    fence_digest: str,
) -> str | None:
    """Recompute the closed lifecycle label from authenticated prefix events."""

    operation = fence_record.get("operation")
    intent_digest = fence_record.get("intent_digest")
    chain_id = state.get("chain_id")
    if (
        operation
        not in {
            "fetch",
            "tip-resolution",
            "gate",
            "remote-observation",
            "rebase",
            "continue",
            "abort",
            "push",
            "containment",
            "worktree-remove",
            "branch-delete",
        }
        or not isinstance(intent_digest, str)
        or SHA256_RE.fullmatch(intent_digest) is None
        or SHA256_RE.fullmatch(fence_digest) is None
    ):
        return None
    events = [event for event in history if isinstance(event, Mapping)]
    by_digest = {
        str(event.get("digest")): event
        for event in events
        if SHA256_RE.fullmatch(str(event.get("digest", ""))) is not None
    }
    attributed = by_digest.get(intent_digest)
    prefix = "fetch" if operation in {"fetch", "tip-resolution"} else str(operation)
    result_names: set[str]
    intent_valid = False

    if operation in {"fetch", "tip-resolution"}:
        intent_valid = bool(
            attributed is not None and attributed.get("event") == "fetch_intent"
        )
        result_names = {"fetch_result"}
        if not intent_valid:
            return None
        fetch_results = [
            event
            for event in events
            if event.get("event") == "fetch_result"
            and event.get("previous_digest") == intent_digest
        ]
        raw_fetch_results: list[Mapping[str, Any]] = []
        for event in events:
            if event.get("event") != "condition_recorded":
                continue
            payload = event.get("payload")
            delta = payload.get("delta") if isinstance(payload, Mapping) else None
            integration = (
                delta.get("integration") if isinstance(delta, Mapping) else None
            )
            observation = (
                integration.get("intent")
                if isinstance(integration, Mapping)
                else None
            )
            if (
                isinstance(observation, Mapping)
                and observation.get("schema") == _EPOCH_FETCH_OBSERVATION_SCHEMA
                and observation.get("fetch_intent_event_digest") == intent_digest
                and observation.get("child_result", {}).get("inflight_digest")
                == fence_digest
                and _epoch_fetch_observation_record_valid(state, observation)
            ):
                raw_fetch_results.append(event)
        if len(fetch_results) > 1 or len(raw_fetch_results) > 1:
            return None
        if raw_fetch_results:
            return "fetch-result-persisted"
        if fetch_results:
            result_event = fetch_results[0]
            payload = result_event.get("payload")
            delta = payload.get("delta") if isinstance(payload, Mapping) else None
            integration = (
                delta.get("integration") if isinstance(delta, Mapping) else None
            )
            result_intent = (
                integration.get("intent")
                if isinstance(integration, Mapping)
                else None
            )
            result = (
                result_intent.get("result")
                if isinstance(result_intent, Mapping)
                else None
            )
            binding = (
                payload.get("scope_fetch_binding")
                if isinstance(payload, Mapping)
                else None
            )
            proof = (
                payload.get("scope_proof")
                if isinstance(payload, Mapping)
                else None
            )
            copied_fence = _recovery_value_carries_inflight(
                binding, fence_digest
            )
            failed_result = bool(
                result_intent is not None
                and result_intent.get("operation") == "fetch-result"
                and result == "failed"
                and proof is None
                and (
                    (binding is None and result_event.get("generation_digest") is None)
                    or (isinstance(binding, Mapping) and copied_fence)
                )
            )
            successful_result = bool(
                result_intent is not None
                and result_intent.get("operation") == "fetch-result"
                and result == "success"
                and isinstance(binding, Mapping)
                and copied_fence
            )
            if not (failed_result or successful_result):
                return None
            return "fetch-result-persisted"
    elif operation == "gate":
        result_names = {"gate_recorded"}
        result_facts = [
            event
            for event in events
            if event.get("event") == "gate_recorded"
            and _recovery_value_carries_inflight(event.get("payload"), fence_digest)
            and any(
                isinstance(member, Mapping)
                and member.get("gate_intent_digest") == intent_digest
                for member in (
                    event.get("payload", {}).get("delta", {}).get("steps", {}).values()
                    if isinstance(event.get("payload"), Mapping)
                    and isinstance(event.get("payload", {}).get("delta"), Mapping)
                    and isinstance(
                        event.get("payload", {}).get("delta", {}).get("steps"),
                        Mapping,
                    )
                    else ()
                )
            )
        ]
        if result_facts:
            intent_valid = True
        else:
            integration = state.get("integration")
            epoch = integration.get("epoch") if isinstance(integration, Mapping) else None
            plan = epoch.get("gate_plan") if isinstance(epoch, Mapping) else None
            cursor = plan.get("cursor") if isinstance(plan, Mapping) else None
            suite = plan.get("suite") if isinstance(plan, Mapping) else None
            if (
                isinstance(plan, Mapping)
                and plan.get("status") == "sealed"
                and _valid_nonnegative_int(cursor)
                and isinstance(suite, list)
                and int(cursor) < len(suite)
                and isinstance(suite[int(cursor)], Mapping)
            ):
                authorizer = (
                    str(plan.get("seal_event_digest"))
                    if int(cursor) == 0
                    else next(
                        (
                            str(event.get("digest"))
                            for event in reversed(events)
                            if event.get("event") == "gate_recorded"
                        ),
                        "",
                    )
                )
                member = suite[int(cursor)]
                try:
                    intent_valid = merge_gate_intent_digest(
                        chain_id=str(chain_id),
                        epoch_intent_digest=str(epoch.get("intent_digest")),
                        seal_event_digest=str(plan.get("seal_event_digest")),
                        generation_digest=str(plan.get("generation_digest")),
                        policy_digest=str(plan.get("policy_digest")),
                        suite_digest=str(plan.get("suite_digest")),
                        cursor=int(cursor),
                        kind=str(member.get("kind")),
                        gate_id=str(member.get("id")),
                        authorizing_event_digest=authorizer,
                    ) == intent_digest
                except (TypeError, ValueError):
                    intent_valid = False
    elif operation == "remote-observation":
        result_names = {"condition_recorded", "cleanup_result"}
        for event in events:
            intent = _recovery_event_intent(event)
            if not isinstance(intent, Mapping):
                continue
            base = {
                name: copy.deepcopy(intent.get(name))
                for name in (
                    "schema",
                    "transaction",
                    "chain_id",
                    "attempt_identity",
                    "phase",
                    "push_intent_digest",
                )
            }
            if (
                base.get("schema") == "forge-remote-observation-intent/1"
                and base.get("transaction") == "merge"
                and base.get("chain_id") == chain_id
                and base.get("phase") in {"final-prepush", "post-push"}
                and sha256_bytes(canonical_bytes(base)) == intent_digest
            ):
                intent_valid = True
                break
        if not intent_valid:
            cleanup_intent = _recovery_cleanup_intent(attributed)
            intent_valid = bool(
                attributed is not None
                and attributed.get("event") == "cleanup_intent"
                and isinstance(cleanup_intent, Mapping)
                and cleanup_intent.get("fence_operation") == operation
                and _merge_cleanup_intent_valid(cleanup_intent, state)
            )
    elif operation in {"rebase", "continue", "abort"}:
        result_names = {"rebase_intent"}
        intent = _recovery_event_intent(attributed) if attributed is not None else None
        intent_valid = bool(
            attributed is not None
            and attributed.get("event") in {"rebase_intent", "condition_recorded"}
            and isinstance(intent, Mapping)
            and intent.get("operation") == operation
        )
    elif operation == "push":
        result_names = {"condition_recorded"}
        intent_valid = bool(
            attributed is not None and attributed.get("event") == "push_intent"
        )
    elif operation in {"worktree-remove", "branch-delete"}:
        result_names = {"cleanup_result"}
        cleanup_intent = _recovery_cleanup_intent(attributed)
        intent_valid = bool(
            attributed is not None
            and attributed.get("event") == "cleanup_intent"
            and isinstance(cleanup_intent, Mapping)
            and cleanup_intent.get("fence_operation") == operation
            and _merge_cleanup_intent_valid(cleanup_intent, state)
        )
    else:  # containment
        result_names = {"condition_recorded", "cleanup_result", "rebase_intent"}
        cleanup_intent = _recovery_cleanup_intent(attributed)
        intent_valid = bool(
            attributed is not None
            and (
                attributed.get("event")
                in {"condition_recorded", "fetch_result", "rebase_intent"}
                or attributed.get("event") == "cleanup_intent"
                and isinstance(cleanup_intent, Mapping)
                and cleanup_intent.get("fence_operation") == operation
                and _merge_cleanup_intent_valid(cleanup_intent, state)
            )
        )
        if not intent_valid:
            intent_valid = any(
                isinstance(_recovery_event_intent(event), Mapping)
                and sha256_bytes(
                    canonical_bytes(dict(_recovery_event_intent(event) or {}))
                )
                == intent_digest
                for event in events
            )
    if not intent_valid:
        return None

    cleanup_intent = _recovery_cleanup_intent(attributed)
    results = []
    for event in events:
        if event.get("event") not in result_names:
            continue
        if event.get("event") == "cleanup_result" and isinstance(
            cleanup_intent, Mapping
        ):
            matched = _recovery_cleanup_result_matches(
                event,
                state,
                cleanup_intent,
                intent_digest=intent_digest,
                fence_digest=fence_digest,
                fence_operation=str(operation),
            )
        else:
            matched = _recovery_value_carries_inflight(
                event.get("payload"), fence_digest
            )
        if matched:
            results.append(event)
    if len(results) > 1:
        return None
    return f"{prefix}-result-persisted" if results else f"{prefix}-intent-pending"


def _merge_recovery_proof_transition_valid(
    event: Mapping[str, Any],
    prior: Mapping[str, Any] | None,
    current: Mapping[str, Any],
    *,
    history: Sequence[Mapping[str, Any]] = (),
) -> bool:
    """Authenticate the durable reservation-held fence-death carrier."""

    payload = event.get("payload")
    if event.get("event") != "condition_recorded":
        return not (
            isinstance(payload, Mapping) and "recovery_proof" in payload
        )
    if not isinstance(payload, Mapping) or "recovery_proof" not in payload:
        return True
    proof = payload.get("recovery_proof")
    if (
        prior is None
        or not isinstance(proof, Mapping)
        or set(payload) != {"delta", "recovery_proof"}
        or payload.get("delta") != {}
        or set(proof)
        != {
            "schema",
            "chain_id",
            "reservation",
            "fence",
            "lifecycle",
            "recorded_at",
            "digest",
        }
        or proof.get("schema") != "forge-merge-fence-recovery-proof/1"
        or proof.get("chain_id") != current.get("chain_id")
        or proof.get("recorded_at") != event.get("at")
        or proof.get("digest")
        != sha256_bytes(
            canonical_bytes(
                {name: copy.deepcopy(value) for name, value in proof.items() if name != "digest"}
            )
        )
    ):
        return False
    common_dir = Path(str(current.get("worktree", {}).get("common_dir", "")))
    reservation = proof.get("reservation")
    fence = proof.get("fence")
    lifecycle = proof.get("lifecycle")
    if not (
        _published_recovery_evidence_valid(
            reservation,
            path=common_dir / COMMON_LOCK_RECOVERY_NAME,
            validator=_validate_recovery_record,
        )
        and isinstance(reservation, Mapping)
        and isinstance(lifecycle, Mapping)
        and set(lifecycle)
        == {
            "operation",
            "intent_digest",
            "classification",
            "state_digest",
            "tail_digest",
        }
        and isinstance(lifecycle.get("classification"), str)
        and bool(lifecycle.get("classification"))
        and lifecycle.get("state_digest")
        == sha256_bytes(canonical_bytes(dict(prior)))
        and lifecycle.get("tail_digest") == event.get("previous_digest")
    ):
        return False
    reservation_record = reservation.get("record")
    if not isinstance(reservation_record, Mapping):
        return False
    if fence is None:
        if not (
            reservation_record.get("recovery_kind") == "fallback-owner"
            and reservation_record.get("stale_owner_kind") == "merge"
            and reservation_record.get("stale_owner_chain_id")
            == current.get("chain_id")
            and reservation_record.get("stale_owner_inode") is not None
            and reservation_record.get("stale_owner_digest") is not None
            and reservation_record.get("owner_dead_at") is not None
            and lifecycle.get("operation") is None
            and lifecycle.get("intent_digest") is None
            and lifecycle.get("classification") == "owner-death-only"
        ):
            return False
        ignored = {"last_event_at", "inactive_after"}
        return all(
            prior.get(name) == current.get(name)
            for name in MERGE_STATE_KEYS - ignored
        )
    if not (
        _published_recovery_evidence_valid(
            fence,
            path=common_dir / COMMON_LOCK_INFLIGHT_NAME,
            validator=_validate_fence_record,
        )
        and isinstance(fence, Mapping)
    ):
        return False
    fence_record = fence.get("record")
    if not isinstance(fence_record, Mapping):
        return False
    recovery_kind = reservation_record.get("recovery_kind")
    if recovery_kind == "fallback-owner-and-fence":
        recovery_topology_valid = bool(
            reservation_record.get("stale_owner_kind") == "merge"
            and reservation_record.get("stale_owner_chain_id")
            == current.get("chain_id")
            and reservation_record.get("stale_owner_inode") is not None
            and reservation_record.get("stale_owner_digest") is not None
            and reservation_record.get("owner_dead_at") is not None
        )
    elif recovery_kind == "flock-held-dead-fence":
        recovery_topology_valid = all(
            reservation_record.get(name) is None
            for name in (
                "stale_owner_inode",
                "stale_owner_digest",
                "stale_owner_host",
                "stale_owner_pid",
                "stale_owner_kind",
                "stale_owner_chain_id",
                "owner_dead_at",
            )
        )
    else:
        recovery_topology_valid = False
    operation = fence_record.get("operation")
    label_prefix = (
        "fetch" if operation in {"fetch", "tip-resolution"} else operation
    )
    allowed_classifications = (
        {
            f"{label_prefix}-intent-pending",
            f"{label_prefix}-result-persisted",
        }
        if isinstance(label_prefix, str)
        and label_prefix
        in {
            "fetch",
            "gate",
            "remote-observation",
            "rebase",
            "continue",
            "abort",
            "push",
            "containment",
            "worktree-remove",
            "branch-delete",
        }
        else set()
    )
    if (
        not recovery_topology_valid
        or lifecycle.get("operation") != fence_record.get("operation")
        or lifecycle.get("intent_digest") != fence_record.get("intent_digest")
        or lifecycle.get("classification") not in allowed_classifications
        or reservation_record.get("inflight_inode") != fence.get("inode")
        or reservation_record.get("inflight_digest") != fence.get("digest")
        or reservation_record.get("inflight_host") != fence_record.get("host")
        or reservation_record.get("inflight_pgid") != fence_record.get("pgid")
        or reservation_record.get("inflight_owner_kind")
        != fence_record.get("owner_kind")
        or reservation_record.get("inflight_chain_id")
        != fence_record.get("chain_id")
        or reservation_record.get("group_dead_at") is None
        or fence_record.get("owner_kind") != "merge"
        or fence_record.get("chain_id") != current.get("chain_id")
    ):
        return False
    expected_classification = _classify_merge_recovery_lifecycle(
        prior,
        history,
        fence_record=fence_record,
        fence_digest=str(fence.get("digest")),
    )
    if lifecycle.get("classification") != expected_classification:
        return False
    for prior_event in history:
        prior_payload = prior_event.get("payload")
        prior_proof = (
            prior_payload.get("recovery_proof")
            if isinstance(prior_payload, Mapping)
            else None
        )
        if isinstance(prior_proof, Mapping) and (
            prior_proof.get("reservation") == reservation
            or (
                prior_proof.get("fence") is not None
                and prior_proof.get("fence") == fence
            )
        ):
            return False
    ignored = {"last_event_at", "inactive_after"}
    return all(
        prior.get(name) == current.get(name)
        for name in MERGE_STATE_KEYS - ignored
    )


def _epoch_fetch_observation_predecessor_valid(
    event: Mapping[str, Any],
    current_intent: Mapping[str, Any],
    prior_intent: Mapping[str, Any],
    context: Mapping[str, Any],
) -> bool:
    """Admit direct adjacency or one exact owner-death recovery carrier."""

    intent_digest = current_intent.get("fetch_intent_event_digest")
    if event.get("previous_digest") == intent_digest:
        return True
    bridge = context.get("recovery_proof_bridge")
    admitted = context.get("fetch_intent")
    return bool(
        isinstance(bridge, Mapping)
        and isinstance(admitted, Mapping)
        and event.get("previous_digest") == bridge.get("event_digest")
        and bridge.get("previous_digest") == intent_digest
        and bridge.get("operation") is None
        and bridge.get("intent_digest") is None
        and bridge.get("classification") == "owner-death-only"
        and admitted.get("digest") == intent_digest
        and admitted.get("generation_digest") == event.get("generation_digest")
        and admitted.get("evidence") == prior_intent
        and admitted.get("admitted_active") is True
    )


def _recovered_absent_rebase_intent_digest(
    event: Mapping[str, Any],
    prior: Mapping[str, Any] | None,
    context: Mapping[str, Any],
) -> str | None:
    """Authenticate the observation interposed before an absent rebase result."""

    if (
        event.get("event") != "rebase_result"
        or prior is None
        or _merge_rebase_result_classification(prior) != "absent"
    ):
        return None
    prior_integration = prior.get("integration")
    prior_intent = (
        prior_integration.get("intent")
        if isinstance(prior_integration, Mapping)
        else None
    )
    prior_candidate = prior.get("candidate")
    replayed = context.get("rebase_intent")
    candidate = context.get("candidate_observation")
    evidence = candidate.get("evidence") if isinstance(candidate, Mapping) else None
    if not (
        isinstance(prior_intent, Mapping)
        and isinstance(prior_candidate, Mapping)
        and isinstance(replayed, Mapping)
        and isinstance(candidate, Mapping)
        and isinstance(evidence, Mapping)
        and isinstance(replayed.get("digest"), str)
        and replayed.get("evidence") == prior_intent
        and replayed.get("admitted_active") is True
        and candidate.get("source_intent") == prior_intent
        and candidate.get("generation_digest") == event.get("generation_digest")
        and event.get("generation_digest")
        == prior_candidate.get("generation_digest")
        and candidate.get("restore_event_digest")
        == event.get("previous_digest")
        and candidate.get("evidence_digest") == evidence.get("evidence_digest")
        and _merge_candidate_observation_evidence_valid(prior, evidence)
        and evidence.get("source_intent") == prior_intent
        and evidence.get("verb") == "merge recover"
        and evidence.get("classify") is False
        and evidence.get("remote_tip") == prior_candidate.get("remote_tip")
        and evidence.get("expected_head")
        == prior_candidate.get("candidate_head")
    ):
        return None
    return str(replayed["digest"])


def _merge_attempted_release_preconditions_valid(
    event: Mapping[str, Any],
    prior: Mapping[str, Any] | None,
    history: Sequence[Mapping[str, Any]],
) -> bool:
    """Recompute every durable member of an attempted-head abort cutoff."""

    if event.get("event") != "ownership_release_intent" or prior is None:
        return True
    integration = prior.get("integration")
    push = integration.get("push") if isinstance(integration, Mapping) else None
    attempted = (
        list(push.get("attempted_heads", [])) if isinstance(push, Mapping) else []
    )
    if not attempted:
        return True
    payload = event.get("payload")
    if not isinstance(payload, Mapping):
        return False
    # Attempted-head aborts carry the FR-236 terminal precondition digest.
    # A successful published-chain cleanup also has attempted heads, but its
    # independently validated release target is ``closed`` and does not use
    # that abort-only preimage.
    if payload.get("target_terminal") != "aborted":
        return True
    observed = (
        integration.get("observed") if isinstance(integration, Mapping) else None
    )
    candidate = prior.get("candidate")
    worktree = prior.get("worktree")
    if not (
        payload.get("terminal_disposition")
        in {"ordinary", "historical-landed-superseded"}
        and isinstance(push, Mapping)
        and isinstance(observed, Mapping)
        and isinstance(candidate, Mapping)
        and isinstance(worktree, Mapping)
    ):
        return False
    containment, vector = _merge_containment(prior)
    expected_containment = (
        "older"
        if payload.get("terminal_disposition") == "historical-landed-superseded"
        else "all-false"
    )
    if containment != expected_containment or len(vector) != len(attempted):
        return False
    observation_event = next(
        (
            member
            for member in reversed(history)
            if member.get("event") == "push_observed"
        ),
        None,
    )
    if (
        not isinstance(observation_event, Mapping)
        or event.get("previous_digest") != observation_event.get("digest")
    ):
        return False
    push_intent_digests = [
        str(member.get("digest"))
        for member in history
        if member.get("event") == "push_intent"
    ]
    push_result_digests: list[str] = []
    replayed: dict[str, Any] | None = None
    try:
        for member in history:
            before_push = (
                replayed.get("integration", {}).get("push")
                if isinstance(replayed, Mapping)
                else None
            )
            before_result = (
                before_push.get("result")
                if isinstance(before_push, Mapping)
                else None
            )
            replayed = reduce_merge_event(replayed, copy.deepcopy(dict(member)))
            after_push = replayed.get("integration", {}).get("push")
            after_result = (
                after_push.get("result") if isinstance(after_push, Mapping) else None
            )
            if after_result != before_result and isinstance(after_result, Mapping):
                push_result_digests.append(str(member.get("digest")))
    except (KeyError, TypeError, ValueError):
        return False
    if len(push_intent_digests) != len(attempted):
        return False
    preconditions = {
        "schema": "forge-merge-attempted-release-preconditions/1",
        "chain_id": prior.get("chain_id"),
        "source_state": prior.get("state"),
        "target_terminal": "aborted",
        "terminal_disposition": payload.get("terminal_disposition"),
        "reason": None,
        "attempted_heads": attempted,
        "attempted_head_containment": [
            {"head": head, "contained": contained}
            for head, contained in zip(attempted, vector)
        ],
        "landed_head": push.get("landed_head"),
        "superseded_head": push.get("intended_head"),
        "observation": copy.deepcopy(dict(observed)),
        "observation_event_digest": observation_event.get("digest"),
        "push_intent_event_digests": push_intent_digests,
        "push_result_event_digests": push_result_digests,
        "worktree_identity": {
            name: worktree.get(name) for name in ("path", "git_dir", "common_dir")
        },
        "branch": prior.get("branch"),
        "current_head": candidate.get("candidate_head"),
        "status_output_digest": sha256_bytes(b""),
        "unresolved_fence_digests": [],
    }
    return payload.get("terminal_preconditions_digest") == sha256_bytes(
        canonical_bytes(preconditions)
    )


_MERGE_CLEANUP_INTENT_SCHEMA = "forge-merge-cleanup-step-intent/1"


_MERGE_CLEANUP_RESULT_SCHEMA = "forge-merge-cleanup-step-result/1"


_MERGE_CLEANUP_CLOSE_SCHEMA = "forge-merge-close-preconditions/2"


_MERGE_CLEANUP_RECOVERY_SCHEMA = "forge-merge-cleanup-recovery/1"


_MERGE_CLEANUP_FENCE_OPERATIONS = {
    "remote-fetch": "remote-observation",
    "remote-containment": "containment",
    "worktree-observation": "worktree-remove",
    "worktree-remove": "worktree-remove",
    "branch-observation": "branch-delete",
    "branch-delete": "branch-delete",
}


def _merge_cleanup_expected_subject(
    state: Mapping[str, Any], operation: str, subject: object
) -> dict[str, Any] | None:
    """Return the exact cleanup subject or reject a dynamic mismatch."""

    candidate = state.get("candidate")
    integration = state.get("integration")
    push = integration.get("push") if isinstance(integration, Mapping) else None
    worktree = state.get("worktree")
    target = state.get("target")
    if not (
        isinstance(candidate, Mapping)
        and isinstance(push, Mapping)
        and isinstance(worktree, Mapping)
        and isinstance(target, Mapping)
        and isinstance(subject, Mapping)
    ):
        return None
    landed_head = push.get("landed_head")
    candidate_head = candidate.get("candidate_head")
    if operation == "remote-fetch":
        expected = {
            "destination_ref": target.get("destination_ref"),
            "landed_head": landed_head,
        }
    elif operation == "remote-containment":
        expected = {
            "landed_head": landed_head,
            "remote_tip": subject.get("remote_tip"),
        }
        if not isinstance(expected["remote_tip"], str) or COMMIT_RE.fullmatch(
            expected["remote_tip"]
        ) is None:
            return None
    elif operation in {"worktree-observation", "worktree-remove"}:
        expected = {
            "path": worktree.get("path"),
            "branch": state.get("branch"),
            "candidate_head": candidate_head,
        }
    elif operation in {"branch-observation", "branch-delete"}:
        expected = {
            "branch": state.get("branch"),
            "candidate_head": candidate_head,
        }
    else:
        return None
    return expected if dict(subject) == expected else None


def _merge_cleanup_expected_argv(
    state: Mapping[str, Any], operation: str, subject: Mapping[str, Any]
) -> list[str] | None:
    repository = str(state.get("repository"))
    if operation == "remote-fetch":
        return [
            "git",
            "--no-pager",
            "-C",
            repository,
            "fetch",
            "--no-tags",
            "--quiet",
            "origin",
            str(subject["destination_ref"]),
        ]
    if operation == "remote-containment":
        return [
            "git",
            "--no-pager",
            "-C",
            repository,
            "merge-base",
            "--is-ancestor",
            str(subject["landed_head"]),
            str(subject["remote_tip"]),
        ]
    if operation == "worktree-observation":
        return [
            "git",
            "--no-pager",
            "-C",
            repository,
            "worktree",
            "list",
            "--porcelain",
            "-z",
        ]
    if operation == "worktree-remove":
        return [
            "git",
            "--no-pager",
            "-C",
            repository,
            "worktree",
            "remove",
            str(subject["path"]),
        ]
    if operation == "branch-observation":
        return [
            "git",
            "--no-pager",
            "-C",
            repository,
            "rev-parse",
            "--verify",
            "--quiet",
            f"{subject['branch']}^{{commit}}",
        ]
    if operation == "branch-delete":
        return [
            "git",
            "--no-pager",
            "-C",
            repository,
            "update-ref",
            "-d",
            str(subject["branch"]),
            str(subject["candidate_head"]),
        ]
    return None


def _merge_cleanup_intent_valid(
    value: object, state: Mapping[str, Any]
) -> bool:
    required = {
        "schema",
        "operation",
        "fence_operation",
        "operation_nonce",
        "generation_digest",
        "subject",
        "argv",
        "cwd",
        "started_at",
    }
    if not isinstance(value, Mapping):
        return False
    keys = set(value)
    if keys != required and keys != required | {"recovery"}:
        return False
    operation = value.get("operation")
    candidate = state.get("candidate")
    if (
        not isinstance(operation, str)
        or operation not in _MERGE_CLEANUP_FENCE_OPERATIONS
        or value.get("schema") != _MERGE_CLEANUP_INTENT_SCHEMA
        or value.get("fence_operation")
        != _MERGE_CLEANUP_FENCE_OPERATIONS[operation]
        or not _valid_nonce(value.get("operation_nonce"))
        or not isinstance(candidate, Mapping)
        or value.get("generation_digest") != candidate.get("generation_digest")
        or value.get("cwd") != state.get("repository")
        or not _valid_utc_second(value.get("started_at"))
    ):
        return False
    subject = _merge_cleanup_expected_subject(state, operation, value.get("subject"))
    if subject is None:
        return False
    recovery = value.get("recovery")
    if ("recovery" in value) != (recovery is not None):
        return False
    if recovery is not None and not (
        operation == "remote-fetch"
        and isinstance(recovery, Mapping)
        and set(recovery)
        == {
            "schema",
            "intent_event_digest",
            "operation",
            "fence_operation",
            "recovery_event_digest",
        }
        and recovery.get("schema") == _MERGE_CLEANUP_RECOVERY_SCHEMA
        and isinstance(recovery.get("intent_event_digest"), str)
        and SHA256_RE.fullmatch(recovery["intent_event_digest"]) is not None
        and recovery.get("operation") in _MERGE_CLEANUP_FENCE_OPERATIONS
        and recovery.get("fence_operation")
        == _MERGE_CLEANUP_FENCE_OPERATIONS[recovery["operation"]]
        and isinstance(recovery.get("recovery_event_digest"), str)
        and SHA256_RE.fullmatch(recovery["recovery_event_digest"]) is not None
    ):
        return False
    return value.get("argv") == _merge_cleanup_expected_argv(
        state, operation, subject
    )


def _merge_cleanup_process_result_valid(
    value: object, expected_argv: Sequence[str]
) -> bool:
    if not isinstance(value, Mapping) or set(value) != {
        "argv",
        "returncode",
        "duration_seconds",
        "output_base64",
        "output_digest",
        "timed_out",
        "output_limit",
        "launch_failed",
        "group_survived",
        "authorized",
        "fence_digest",
        "fence_inode",
    }:
        return False
    returncode = value.get("returncode")
    duration = value.get("duration_seconds")
    output_base64 = value.get("output_base64")
    try:
        output = (
            base64.b64decode(output_base64, validate=True)
            if isinstance(output_base64, str)
            else None
        )
    except (binascii.Error, ValueError):
        output = None
    canonical_not_authorized = bool(
        value.get("authorized") is False
        and returncode is None
        and type(duration) is float
        and duration == 0.0
        and math.copysign(1.0, duration) == 1.0
        and output == b""
        and value.get("output_digest") == sha256_bytes(b"")
        and value.get("timed_out") is False
        and value.get("output_limit") is False
        and value.get("launch_failed") is True
        and value.get("group_survived") is False
        and value.get("fence_digest") is None
        and value.get("fence_inode") is None
    )
    return bool(
        value.get("argv") == list(expected_argv)
        and (
            returncode is None
            or isinstance(returncode, int)
            and not isinstance(returncode, bool)
        )
        and isinstance(duration, (int, float))
        and not isinstance(duration, bool)
        and math.isfinite(duration)
        and duration >= 0
        and isinstance(output, bytes)
        and len(output) <= runtime.OUTPUT_CAP_BYTES
        and base64.b64encode(output).decode("ascii") == output_base64
        and isinstance(value.get("output_digest"), str)
        and SHA256_RE.fullmatch(value["output_digest"]) is not None
        and (
            value.get("output_limit") is True
            and len(output) == runtime.OUTPUT_CAP_BYTES
            or value.get("output_limit") is False
            and sha256_bytes(output) == value.get("output_digest")
        )
        and type(value.get("timed_out")) is bool
        and type(value.get("output_limit")) is bool
        and type(value.get("launch_failed")) is bool
        and type(value.get("group_survived")) is bool
        and type(value.get("authorized")) is bool
        and (
            canonical_not_authorized
            or value.get("authorized") is True
            and isinstance(value.get("fence_digest"), str)
            and SHA256_RE.fullmatch(value["fence_digest"]) is not None
            and _valid_positive_int(value.get("fence_inode"))
        )
    )


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


def _merge_cleanup_step_result_valid(
    value: object,
    state: Mapping[str, Any],
    intent: Mapping[str, Any],
    intent_digest: str,
) -> bool:
    if not isinstance(value, Mapping) or set(value) != {
        "schema",
        "operation",
        "fence_operation",
        "operation_nonce",
        "intent_event_digest",
        "outcome",
        "observation",
        "process",
    }:
        return False
    operation = intent.get("operation")
    outcome = value.get("outcome")
    process = value.get("process")
    subject = intent.get("subject")
    if not (
        _merge_cleanup_intent_valid(intent, state)
        and value.get("schema") == _MERGE_CLEANUP_RESULT_SCHEMA
        and value.get("operation") == operation
        and value.get("fence_operation") == intent.get("fence_operation")
        and value.get("operation_nonce") == intent.get("operation_nonce")
        and value.get("intent_event_digest") == intent_digest
        and isinstance(outcome, str)
        and outcome in {"passed", "already-absent", "failed"}
        and isinstance(subject, Mapping)
        and isinstance(process, Mapping)
        and _merge_cleanup_process_result_valid(process, intent.get("argv", ()))
    ):
        return False
    return _merge_cleanup_observation_valid(
        str(operation), value.get("observation"), subject, process, str(outcome)
    )


def _merge_cleanup_results_valid(
    value: object,
    state: Mapping[str, Any],
    intent: Mapping[str, Any],
    intent_digest: str,
) -> bool:
    """Validate one result event from the repeated FR-236 cleanup protocol."""

    return bool(
        isinstance(value, list)
        and len(value) == 1
        and _merge_cleanup_step_result_valid(
            value[0], state, intent, intent_digest
        )
    )


def _merge_cleanup_evidence_history(
    history: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Project every cleanup carrier, including immutable Revision-9 facts."""

    evidence: list[dict[str, Any]] = []
    for member in history:
        payload = member.get("payload")
        if (
            member.get("event") not in {"cleanup_intent", "cleanup_result"}
            or not isinstance(payload, Mapping)
        ):
            continue
        evidence.append(
            {
                "event": member.get("event"),
                "event_digest": member.get("digest"),
                "payload": copy.deepcopy(dict(payload)),
            }
        )
    return evidence


def _merge_cleanup_history_summary(
    history: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Reduce authenticated cleanup results for retry and close admission."""

    results: list[Mapping[str, Any]] = []
    for item in _merge_cleanup_evidence_history(history):
        payload = item.get("payload")
        carried = (
            payload.get("cleanup_results")
            if isinstance(payload, Mapping)
            else None
        )
        if (
            item.get("event") == "cleanup_result"
            and isinstance(carried, list)
            and len(carried) == 1
            and isinstance(carried[0], Mapping)
        ):
            results.append(carried[0])
    remote_fetch: Mapping[str, Any] | None = None
    remote_containment: Mapping[str, Any] | None = None
    worktree_complete = False
    branch_complete = False
    worktree_observed_present = False
    branch_observed_present = False
    branch_observed_absent = False
    for result in results:
        operation = result.get("operation")
        outcome = result.get("outcome")
        if operation == "remote-fetch":
            remote_fetch = result if outcome == "passed" else None
            remote_containment = None
            branch_observed_present = False
            branch_observed_absent = False
        elif operation == "remote-containment":
            observation = result.get("observation")
            fetched = (
                remote_fetch.get("observation")
                if isinstance(remote_fetch, Mapping)
                else None
            )
            if (
                outcome == "passed"
                and isinstance(observation, Mapping)
                and isinstance(fetched, Mapping)
                and observation.get("remote_tip") == fetched.get("oid")
            ):
                remote_containment = result
            else:
                remote_containment = None
        elif operation == "worktree-observation":
            worktree_observed_present = outcome == "passed"
            worktree_complete = outcome == "already-absent"
        elif operation == "worktree-remove":
            worktree_complete = bool(
                outcome == "passed" and worktree_observed_present
            )
            worktree_observed_present = False
        elif operation == "branch-observation":
            branch_observed_present = outcome == "passed"
            branch_observed_absent = outcome == "already-absent"
            branch_complete = branch_observed_absent
        elif operation == "branch-delete":
            branch_complete = bool(
                outcome == "passed" and branch_observed_present
            )
            branch_observed_present = False
            branch_observed_absent = False
    return {
        "results": results,
        "last_result": results[-1] if results else None,
        "remote_fetch": remote_fetch,
        "remote_containment": remote_containment,
        "worktree_complete": worktree_complete,
        "branch_complete": branch_complete,
        "worktree_observed_present": worktree_observed_present,
        "branch_observed_present": branch_observed_present,
        "branch_observed_absent": branch_observed_absent,
    }


def _merge_cleanup_unmatched_intent(
    history: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    """Return the sole strict cleanup intent without its immediate result."""

    unmatched: Mapping[str, Any] | None = None
    for event in history:
        if event.get("event") == "cleanup_intent":
            intent = _recovery_cleanup_intent(event)
            if (
                isinstance(intent, Mapping)
                and intent.get("schema") == _MERGE_CLEANUP_INTENT_SCHEMA
            ):
                unmatched = event
        elif event.get("event") == "cleanup_result" and unmatched is not None:
            payload = event.get("payload")
            results = (
                payload.get("cleanup_results")
                if isinstance(payload, Mapping)
                else None
            )
            result = (
                results[0]
                if isinstance(results, list)
                and len(results) == 1
                and isinstance(results[0], Mapping)
                else None
            )
            if (
                isinstance(result, Mapping)
                and result.get("intent_event_digest") == unmatched.get("digest")
            ):
                unmatched = None
    return unmatched


def _merge_cleanup_retry_proof_valid(
    history: Sequence[Mapping[str, Any]],
    unmatched: Mapping[str, Any],
) -> bool:
    """Admit a restart only after exact recovery closed the intent window."""

    if not history or history[-1].get("event") != "condition_recorded":
        return False
    recovery_event = history[-1]
    payload = recovery_event.get("payload")
    proof = payload.get("recovery_proof") if isinstance(payload, Mapping) else None
    lifecycle = proof.get("lifecycle") if isinstance(proof, Mapping) else None
    fence = proof.get("fence") if isinstance(proof, Mapping) else None
    intent = _recovery_cleanup_intent(unmatched)
    if not (
        recovery_event.get("previous_digest") == unmatched.get("digest")
        and isinstance(intent, Mapping)
        and isinstance(lifecycle, Mapping)
    ):
        return False
    if fence is None:
        return bool(
            lifecycle.get("operation") is None
            and lifecycle.get("intent_digest") is None
            and lifecycle.get("classification") == "owner-death-only"
        )
    fence_record = fence.get("record") if isinstance(fence, Mapping) else None
    fence_operation = intent.get("fence_operation")
    return bool(
        isinstance(fence_record, Mapping)
        and fence_record.get("intent_digest") == unmatched.get("digest")
        and fence_record.get("operation") == fence_operation
        and lifecycle.get("operation") == fence_operation
        and lifecycle.get("intent_digest") == unmatched.get("digest")
        and lifecycle.get("classification")
        == f"{fence_operation}-intent-pending"
    )


def _merge_cleanup_intent_transition_valid(
    event: Mapping[str, Any],
    prior: Mapping[str, Any] | None,
    current: Mapping[str, Any],
    history: Sequence[Mapping[str, Any]],
) -> bool:
    if event.get("event") != "cleanup_intent":
        return True
    if prior is None:
        return False
    payload = event.get("payload")
    prior_cleanup = prior.get("cleanup")
    cleanup = current.get("cleanup")
    intent = cleanup.get("intent") if isinstance(cleanup, Mapping) else None
    if not (
        isinstance(payload, Mapping)
        and isinstance(prior_cleanup, Mapping)
        and isinstance(cleanup, Mapping)
        and set(cleanup) == {"condition", "intent"}
        and cleanup.get("condition") == prior_cleanup.get("condition")
        and payload.get("delta") == {"cleanup": cleanup}
        and _merge_cleanup_intent_valid(intent, current)
    ):
        return False
    summary = _merge_cleanup_history_summary(history)
    operation = intent.get("operation") if isinstance(intent, Mapping) else None
    last = summary["last_result"]
    unmatched = _merge_cleanup_unmatched_intent(history)
    recovery = intent.get("recovery") if isinstance(intent, Mapping) else None
    if unmatched is not None:
        unmatched_intent = _recovery_cleanup_intent(unmatched)
        if not (
            operation == "remote-fetch"
            and isinstance(unmatched_intent, Mapping)
            and _merge_cleanup_retry_proof_valid(history, unmatched)
            and isinstance(recovery, Mapping)
            and recovery
            == {
                "schema": _MERGE_CLEANUP_RECOVERY_SCHEMA,
                "intent_event_digest": unmatched.get("digest"),
                "operation": unmatched_intent.get("operation"),
                "fence_operation": unmatched_intent.get("fence_operation"),
                "recovery_event_digest": history[-1].get("digest"),
            }
        ):
            return False
    elif recovery is not None:
        return False
    if operation == "remote-fetch":
        return True
    if not isinstance(last, Mapping) or last.get("outcome") == "failed":
        return False
    if operation == "remote-containment":
        subject = intent.get("subject")
        observation = last.get("observation")
        return bool(
            last.get("operation") == "remote-fetch"
            and last.get("outcome") == "passed"
            and isinstance(subject, Mapping)
            and isinstance(observation, Mapping)
            and subject.get("remote_tip") == observation.get("oid")
        )
    if summary["remote_containment"] is None:
        return False
    if operation == "branch-observation":
        return bool(
            not summary["branch_observed_present"]
            and not summary["branch_observed_absent"]
            and (
                not summary["worktree_complete"]
                or not summary["branch_complete"]
            )
        )
    if operation == "worktree-observation":
        return bool(
            not summary["worktree_complete"]
            and (
                summary["branch_observed_present"]
                or summary["branch_observed_absent"]
            )
        )
    if operation == "worktree-remove":
        return bool(
            last.get("operation") == "worktree-observation"
            and last.get("outcome") == "passed"
        )
    if operation == "branch-delete":
        return bool(
            summary["worktree_complete"]
            and not summary["branch_complete"]
            and summary["branch_observed_present"]
        )
    return False


def _merge_cleanup_result_transition_valid(
    event: Mapping[str, Any],
    prior: Mapping[str, Any] | None,
    current: Mapping[str, Any],
) -> bool:
    """Authenticate each durable cleanup result before compatibility projection."""

    if event.get("event") != "cleanup_result":
        return True
    payload = event.get("payload")
    if not isinstance(payload, Mapping):
        return False
    if prior is None or set(payload) != {"delta", "cleanup_results"}:
        return False
    prior_cleanup = prior.get("cleanup")
    intent = (
        prior_cleanup.get("intent") if isinstance(prior_cleanup, Mapping) else None
    )
    results = payload.get("cleanup_results")
    if not (
        isinstance(intent, Mapping)
        and _merge_cleanup_results_valid(
            results, prior, intent, str(event.get("previous_digest", ""))
        )
        and isinstance(results, list)
        and isinstance(results[0], Mapping)
    ):
        return False
    failed = results[0].get("outcome") == "failed"
    expected_delta: dict[str, Any] = {
        "cleanup": {"condition": "cleanup-failed" if failed else "none"}
    }
    expected_state = prior.get("state")
    if failed and prior.get("state") != "cleanup_pending":
        expected_delta["state"] = "cleanup_pending"
        expected_state = "cleanup_pending"
    return bool(
        payload.get("delta") == expected_delta
        and current.get("cleanup") == expected_delta["cleanup"]
        and current.get("state") == expected_state
    )


def _merge_history_has_git_mutation_intent(
    history: Sequence[Mapping[str, Any]],
) -> bool:
    """Recognize every FR-231 scope-release Git-mutation intent carrier."""

    for member in history:
        if member.get("event") in {"rebase_intent", "push_intent", "cleanup_intent"}:
            return True
        intent = _recovery_event_intent(member)
        if not isinstance(intent, Mapping):
            continue
        if intent.get("operation") in {
            "rebase",
            "continue",
            "abort",
            "push",
            "containment",
            "worktree-remove",
            "branch-delete",
        }:
            return True
        if (
            intent.get("schema") == "forge-remote-observation-progress/1"
            and intent.get("stage") in {"containment-intent", "containment-result"}
        ) or (
            intent.get("schema") == "forge-epoch-ancestry-intent/1"
            and intent.get("phase") in {"intent", "result"}
        ):
            return True
    return False


def _merge_release_preconditions_valid(
    event: Mapping[str, Any],
    prior: Mapping[str, Any] | None,
    history: Sequence[Mapping[str, Any]],
) -> bool:
    """Reconstruct every live merge release cutoff from authenticated facts."""

    if event.get("event") != "ownership_release_intent" or prior is None:
        return True
    payload = event.get("payload")
    if not isinstance(payload, Mapping):
        return False
    target = payload.get("target_terminal")
    integration = prior.get("integration")
    push = integration.get("push") if isinstance(integration, Mapping) else None
    attempted = (
        list(push.get("attempted_heads", [])) if isinstance(push, Mapping) else []
    )
    if target == "closed":
        cleanup_evidence = _merge_cleanup_evidence_history(history)
        summary = _merge_cleanup_history_summary(history)
        containment_result = summary.get("remote_containment")
        containment_observation = (
            containment_result.get("observation")
            if isinstance(containment_result, Mapping)
            else None
        )
        if not (
            cleanup_evidence
            and cleanup_evidence[-1].get("event") == "cleanup_result"
            and event.get("previous_digest")
            == cleanup_evidence[-1].get("event_digest")
            and isinstance(push, Mapping)
            and isinstance(containment_observation, Mapping)
            and containment_observation.get("landed_head")
            == push.get("landed_head")
            and containment_observation.get("contained") is True
            and summary.get("worktree_complete") is True
            and summary.get("branch_complete") is True
        ):
            return False
        preconditions = {
            "schema": _MERGE_CLEANUP_CLOSE_SCHEMA,
            "chain_id": prior.get("chain_id"),
            "source_state": prior.get("state"),
            "landed_head": push.get("landed_head"),
            "containment_observation": copy.deepcopy(
                dict(containment_observation)
            ),
            "cleanup_evidence": cleanup_evidence,
        }
        return payload.get("terminal_preconditions_digest") == sha256_bytes(
            canonical_bytes(preconditions)
        )
    if target != "aborted":
        return False
    scope_events = [
        member
        for member in history
        if member.get("event") == "fetch_result"
        and isinstance(member.get("payload"), Mapping)
        and isinstance(member["payload"].get("scope_proof"), Mapping)
        and member["payload"]["scope_proof"].get("result") == "exceeded"
    ]
    scope_event = scope_events[0] if len(scope_events) == 1 else None
    candidate = prior.get("candidate")
    worktree = prior.get("worktree")
    if scope_events:
        if scope_event is None:
            return False
        scope_payload = scope_event["payload"]
        proof = scope_payload["scope_proof"]
        if not (
            event.get("previous_digest") == scope_event.get("digest")
            and isinstance(candidate, Mapping)
            and isinstance(worktree, Mapping)
            and not attempted
            and not _merge_history_has_git_mutation_intent(history)
        ):
            return False
        preconditions = {
            "schema": "forge-run-scope-abort-preconditions/1",
            "target_terminal": "aborted",
            "terminal_disposition": "ordinary",
            "release_mode": "acquired",
            "source_state": "classifying",
            "scope_proof_digest": proof.get("digest"),
            "fetch_result_event_digest": scope_event.get("digest"),
            "generation_digest": candidate.get("generation_digest"),
            "worktree_identity": {
                name: worktree.get(name)
                for name in ("path", "git_dir", "common_dir")
            },
            "branch": prior.get("branch"),
            "candidate_head": candidate.get("candidate_head"),
            "current_head": candidate.get("candidate_head"),
            "status_output_digest": sha256_bytes(b""),
            "push_intent_event_digests": [],
            "git_mutation_intent_event_digests": [],
            "unresolved_fence_digests": [],
        }
    else:
        if attempted:
            return _merge_attempted_release_preconditions_valid(
                event, prior, history
            )
        if any(member.get("event") == "push_intent" for member in history):
            return False
        if not isinstance(worktree, Mapping):
            return False
        preconditions = {
            "schema": "forge-merge-abort-preconditions/1",
            "chain_id": prior.get("chain_id"),
            "source_state": prior.get("state"),
            "candidate": copy.deepcopy(candidate),
            "integration": copy.deepcopy(integration),
            "claim": copy.deepcopy(worktree.get("claim")),
            "reason": None,
        }
    return payload.get("terminal_preconditions_digest") == sha256_bytes(
        canonical_bytes(preconditions)
    )


def _merge_transition_valid(
    builders: Any,
    event: Mapping[str, Any],
    prior: Mapping[str, Any] | None,
    current: Mapping[str, Any],
    *,
    context: MutableMapping[str, Any] | None,
    history: Sequence[Mapping[str, Any]] = (),
) -> bool:
    """Compose strict Revision-10 checks over the shared Revision-9 grammar."""

    chain_id = str(event.get("chain_id", ""))
    if (
        not _merge_state_shape_valid(builders, current, chain_id)
        or (prior is not None and not _merge_state_shape_valid(builders, prior, chain_id))
        or not _merge_plan_transition_valid(event, prior, current)
        or not _merge_scope_transition_valid(event, prior, current)
        or not _merge_recovery_proof_transition_valid(
            event, prior, current, history=history
        )
        or not _merge_cleanup_intent_transition_valid(
            event, prior, current, history
        )
        or not _merge_cleanup_result_transition_valid(event, prior, current)
        or not _merge_release_preconditions_valid(event, prior, history)
    ):
        return False
    compat_event, compat_current = _merge_revision9_compatibility_view(event, current)
    _unused, compat_prior = _merge_revision9_compatibility_view(None, prior)
    if compat_event is None or compat_current is None:
        return False
    prior_integration = prior.get("integration") if prior is not None else None
    current_integration = current.get("integration")
    gate_nonmovement_reset = bool(
        event.get("event") == "gate_recorded"
        and prior is not None
        and prior.get("state") == "reverifying"
        and current.get("state") == "reverification_failed"
        and isinstance(prior_integration, Mapping)
        and isinstance(current_integration, Mapping)
        and current_integration.get("remote_movement_count") == 0
        and all(
            prior_integration.get(name) == current_integration.get(name)
            for name in set(prior_integration)
            - {"epoch", "remote_movement_count"}
        )
    )
    if gate_nonmovement_reset and compat_prior is not None:
        compat_prior_integration = compat_prior.get("integration")
        compat_current_integration = compat_current.get("integration")
        if not isinstance(compat_prior_integration, dict) or not isinstance(
            compat_current_integration, dict
        ):
            return False
        compat_current_integration["remote_movement_count"] = (
            compat_prior_integration["remote_movement_count"]
        )
        compat_gate_payload = compat_event.get("payload")
        compat_delta = (
            compat_gate_payload.get("delta")
            if isinstance(compat_gate_payload, dict)
            else None
        )
        compat_delta_integration = (
            compat_delta.get("integration")
            if isinstance(compat_delta, dict)
            else None
        )
        if not isinstance(compat_delta_integration, dict):
            return False
        compat_delta_integration["remote_movement_count"] = (
            compat_prior_integration["remote_movement_count"]
        )
    compat_payload = compat_event.get("payload")
    if isinstance(compat_payload, dict) and isinstance(
        compat_payload.get("delta"), dict
    ):
        delta = compat_payload["delta"]
        if "integration" in delta and compat_prior is not None:
            if delta["integration"] == compat_prior.get("integration"):
                delta.pop("integration")
        if (
            event.get("event") == "generation_refreshed"
            and _merge_bootstrap_classification_pending(prior)
            and compat_prior is not None
        ):
            # Pending is projected to the legacy verifying/tier shape.  Do
            # not leave validator-only no-op members in the copied delta.
            for name in ("state", "tier"):
                if compat_prior.get(name) == compat_current.get(name):
                    delta.pop(name, None)
    trial_context = copy.deepcopy(dict(context)) if context is not None else {}
    current_epoch = current.get("integration", {}).get("epoch")
    replayed_epoch = trial_context.get("epoch_intent")
    if (
        isinstance(current_epoch, Mapping)
        and isinstance(current_epoch.get("gate_plan"), Mapping)
        and current_epoch["gate_plan"].get("status") == "sealed"
        and isinstance(replayed_epoch, dict)
        and replayed_epoch.get("digest") == current_epoch.get("intent_digest")
        and current_epoch.get("generation_digest")
        != replayed_epoch.get("generation_digest")
    ):
        # Revision 10 permits its authenticated sealer to bind the successor
        # generation while retaining the original epoch-event identity.
        replayed_epoch["generation_digest"] = current_epoch.get(
            "generation_digest"
        )
    if event.get("event") != "generation_carried_forward" and compat_prior is not None:
        prior_candidate = compat_prior.get("candidate")
        current_candidate = compat_current.get("candidate")
        if (
            isinstance(prior_candidate, Mapping)
            and isinstance(current_candidate, Mapping)
            and prior_candidate == current_candidate
        ):
            current_digest = str(current_candidate.get("generation_digest", ""))
            current_head = current_candidate.get("candidate_head")
            prior_authorization = compat_prior.get("authorization")
            current_authorization = compat_current.get("authorization")
            retained_authority = bool(
                isinstance(prior_authorization, dict)
                and isinstance(current_authorization, dict)
                and prior_authorization == current_authorization
                and prior_authorization.get("candidate_head") == current_head
                and prior_authorization.get("review_verdict") == "PASS"
                and SHA256_RE.fullmatch(
                    str(prior_authorization.get("generation_digest", ""))
                )
                is not None
                and prior_authorization.get("generation_digest") != current_digest
            )
            if retained_authority:
                prior_digest = str(prior_authorization["generation_digest"])
                historical_gate_digests = _merge_gate_step_generation_digests(
                    compat_prior.get("steps")
                )
                if historical_gate_digests and prior_digest not in (
                    historical_gate_digests
                ):
                    raise ValueError(
                        "merge carried gate facts lost their authorizing generation"
                    )
                for projection in (compat_prior, compat_current):
                    projection["steps"] = _merge_carried_gate_steps(
                        projection.get("steps"),
                        prior_generation_digests=historical_gate_digests,
                        successor_generation_digest=current_digest,
                    )
                    projection["authorization"] = copy.deepcopy(
                        projection["authorization"]
                    )
                    projection["authorization"][
                        "generation_digest"
                    ] = current_digest
                    approval = projection.get("approval")
                    if (
                        isinstance(approval, dict)
                        and approval.get("purpose") in {"gate-4", "remote-churn"}
                        and approval.get("candidate") == current_head
                    ):
                        projection["approval"] = copy.deepcopy(approval)
                        projection["approval"]["generation_digest"] = current_digest
                if isinstance(compat_payload, dict):
                    compat_delta = compat_payload.get("delta")
                    if isinstance(compat_delta, dict) and "steps" in compat_delta:
                        compat_delta["steps"] = _merge_carried_gate_steps(
                            compat_delta["steps"],
                            prior_generation_digests=historical_gate_digests,
                            successor_generation_digest=current_digest,
                        )
    if event.get("event") != "approval_recorded" and compat_prior is not None:
        prior_approval = prior.get("approval") if prior is not None else None
        current_approval = current.get("approval")
        if (
            isinstance(prior_approval, Mapping)
            and isinstance(current_approval, Mapping)
            and prior_approval == current_approval
            and prior_approval.get("purpose") == "remote-churn"
            and prior_approval.get("chain_id") == current.get("chain_id")
            and prior_approval.get("candidate")
            == current.get("candidate", {}).get("candidate_head")
            and SHA256_RE.fullmatch(
                str(prior_approval.get("generation_digest", ""))
            )
            is not None
        ):
            # Revision 9's shared validator predates the FR-232 churn re-arm
            # and recognizes only the retained Gate-4 purpose on later epoch
            # transitions.  Project the already replay-authenticated churn
            # acknowledgement back to that predecessor authority in memory;
            # the durable acknowledgement remains byte-for-byte unchanged.
            for projection in (compat_prior, compat_current):
                projection_approval = projection.get("approval")
                projection_candidate = projection.get("candidate")
                if not isinstance(projection_approval, dict) or not isinstance(
                    projection_candidate, Mapping
                ):
                    raise ValueError(
                        "merge remote-churn authority projection is malformed"
                    )
                projection_approval["purpose"] = "gate-4"
                projection_approval["generation_digest"] = projection_candidate[
                    "generation_digest"
                ]
    occupied_slot_above_minor_disposition = bool(
        event.get("event") == "review_disposition"
        and prior is not None
        and isinstance(prior.get("review"), Mapping)
        and isinstance(current.get("review"), Mapping)
        and prior["review"].get("operator_cosign_required") is True
        and isinstance(prior["review"].get("dispositions"), list)
        and isinstance(current["review"].get("dispositions"), list)
        and len(current["review"]["dispositions"])
        == len(prior["review"]["dispositions"]) + 1
        and current["review"]["dispositions"][:-1]
        == prior["review"]["dispositions"]
        and isinstance(current["review"]["dispositions"][-1], Mapping)
        and current["review"]["dispositions"][-1].get("severity")
        in {"CRITICAL", "MAJOR"}
    )
    if occupied_slot_above_minor_disposition:
        # Runtime serialization is not sufficient: replay is the system of
        # record, so a digest-valid carrier must not be able to introduce a
        # second above-MINOR disposition while the sole slot is occupied.
        return False
    pending_slot_minor_disposition = bool(
        event.get("event") == "review_disposition"
        and prior is not None
        and prior.get("state") == current.get("state")
        and prior.get("state") in {"reviewing", "revising"}
        and isinstance(prior.get("review"), Mapping)
        and isinstance(current.get("review"), Mapping)
        and prior["review"].get("operator_cosign_required") is True
        and current["review"].get("operator_cosign_required") is True
        and isinstance(prior["review"].get("dispositions"), list)
        and isinstance(current["review"].get("dispositions"), list)
        and len(current["review"]["dispositions"])
        == len(prior["review"]["dispositions"]) + 1
        and current["review"]["dispositions"][:-1]
        == prior["review"]["dispositions"]
        and isinstance(current["review"]["dispositions"][-1], Mapping)
        and current["review"]["dispositions"][-1].get("severity") == "MINOR"
    )
    if pending_slot_minor_disposition:
        projected_review = compat_current.get("review")
        projected_delta = (
            compat_event.get("payload", {}).get("delta")
            if isinstance(compat_event, Mapping)
            else None
        )
        projected_delta_review = (
            projected_delta.get("review")
            if isinstance(projected_delta, Mapping)
            else None
        )
        if not isinstance(projected_review, dict) or not isinstance(
            projected_delta_review, dict
        ):
            raise ValueError("merge MINOR disposition projection is malformed")
        # Revision 9 treated the flag as the severity of the newly appended
        # disposition.  Revision 10 makes it the one-slot aggregate.  Present
        # the legacy false value only to the shared validator; durable state
        # retains the already-occupied slot while the complete appended MINOR
        # object is still validated there.
        projected_review["operator_cosign_required"] = False
        projected_delta_review["operator_cosign_required"] = False
    remote_churn_approval_carrier = False
    if (
        event.get("event") == "approval_recorded"
        and prior is not None
        and compat_prior is not None
        and isinstance(prior.get("run_binding"), Mapping)
        and isinstance(prior.get("integration"), Mapping)
        and prior["integration"].get("condition") == "remote-churn"
        and isinstance(current.get("approval"), Mapping)
        and current["approval"].get("purpose") == "remote-churn"
    ):
        try:
            records, event_outbox, source_digest = builders._event_batch_records(
                copy.deepcopy(dict(event)), "merge"
            )
        except (KeyError, TypeError, ValueError):
            records, event_outbox, source_digest = (), None, None
        semantic_event = copy.deepcopy(compat_event)
        semantic_current = copy.deepcopy(compat_current)
        semantic_payload = semantic_event.get("payload")
        if isinstance(semantic_payload, dict):
            semantic_payload.pop("source_event_digest", None)
            semantic_payload.pop("journal_batch", None)
        semantic_current["journal_outbox"] = compat_prior.get("journal_outbox")
        remote_churn_approval_carrier = bool(
            len(records) == 1
            and records[0].get("type") == "decision"
            and records[0].get("outcome") == "chain-approval"
            and isinstance(source_digest, str)
            and SHA256_RE.fullmatch(source_digest) is not None
            and event_outbox == current.get("journal_outbox")
            and isinstance(records[0].get("binding"), Mapping)
            and builders._binding_matches_source_fact(
                records[0]["binding"],
                records[0],
                event,
                prior,
                current,
                family="merge",
            )
            and builders._merge_transition_valid(
                semantic_event,
                compat_prior,
                semantic_current,
                context=copy.deepcopy(trial_context),
            )
        )
    shared_pass = bool(
        remote_churn_approval_carrier
        or builders._merge_transition_valid(
            compat_event,
            compat_prior,
            compat_current,
            context=trial_context,
        )
    )
    recovery_proof_event = bool(
        event.get("event") == "condition_recorded"
        and isinstance(event.get("payload"), Mapping)
        and "recovery_proof" in event["payload"]
        and _merge_recovery_proof_transition_valid(
            event, prior, current, history=history
        )
    )
    if not shared_pass and recovery_proof_event:
        # The shared Revision-9 grammar has no state-neutral condition carrier.
        # Revision 12 adds exactly this authenticated proof without changing
        # any materialized lifecycle member.
        shared_pass = True
    if shared_pass and recovery_proof_event:
        recovery_proof = event.get("payload", {}).get("recovery_proof")
        lifecycle = (
            recovery_proof.get("lifecycle")
            if isinstance(recovery_proof, Mapping)
            else None
        )
        if isinstance(lifecycle, Mapping):
            trial_context["recovery_proof_bridge"] = {
                "event_digest": event.get("digest"),
                "previous_digest": event.get("previous_digest"),
                "operation": lifecycle.get("operation"),
                "intent_digest": lifecycle.get("intent_digest"),
                "classification": lifecycle.get("classification"),
            }
        if (
            isinstance(lifecycle, Mapping)
            and lifecycle.get("classification") == "fetch-intent-pending"
            and SHA256_RE.fullmatch(str(lifecycle.get("intent_digest", "")))
            is not None
        ):
            trial_context["bootstrap_recovery_proof"] = {
                "event_digest": event.get("digest"),
                "fetch_intent_event_digest": lifecycle.get("intent_digest"),
            }
    event_name = event.get("event")
    replay_event_at = builders._utc_value(event.get("at"))
    replay_prior_deadline = (
        builders._utc_value(prior.get("inactive_after"))
        if prior is not None
        else None
    )
    replay_current_integration = current.get("integration")
    replay_current_intent = (
        replay_current_integration.get("intent")
        if isinstance(replay_current_integration, Mapping)
        else None
    )
    inactive_post_push_observation = bool(
        event_name == "push_observed"
        and replay_event_at is not None
        and replay_prior_deadline is not None
        and replay_event_at >= replay_prior_deadline
        and isinstance(replay_current_intent, Mapping)
        and replay_current_intent.get("schema")
        == "forge-remote-observation-intent/1"
        and replay_current_intent.get("phase") == "post-push"
    )
    if inactive_post_push_observation:
        if not _replayed_remote_observation_completed(
            event, current, trial_context
        ):
            return False
        _require_merge_integration_control("observation-first-recovery")
    epoch_fetch_intent_digest = _epoch_fetch_result_intent_digest(
        event, prior, current, trial_context
    )
    interposed_epoch_fetch = bool(
        event_name == "fetch_result"
        and prior is not None
        and prior.get("state") == "rebasing"
        and isinstance(trial_context.get("epoch_fetch_observation"), Mapping)
    )
    if interposed_epoch_fetch and epoch_fetch_intent_digest is None:
        return False
    if not shared_pass and epoch_fetch_intent_digest is not None:
        bridged_event = copy.deepcopy(compat_event)
        bridged_event["previous_digest"] = epoch_fetch_intent_digest
        bridged_current = copy.deepcopy(compat_current)
        if (
            prior is not None
            and prior.get("state") == "rebasing"
            and current.get("state") == "reverifying"
        ):
            bridged_current["state"] = "rebasing"
            bridged_payload = bridged_event.get("payload")
            bridged_delta = (
                bridged_payload.get("delta")
                if isinstance(bridged_payload, dict)
                else None
            )
            if not isinstance(bridged_delta, dict):
                return False
            bridged_delta.pop("state", None)
        bridged_context = copy.deepcopy(trial_context)
        for name in (
            "epoch_fetch_observation",
            "candidate_observation_active",
            "candidate_observation",
            "epoch_ancestry_observation",
        ):
            bridged_context.pop(name, None)
        if builders._merge_transition_valid(
            bridged_event,
            compat_prior,
            bridged_current,
            context=bridged_context,
        ):
            shared_pass = True
            trial_context = bridged_context
    replayed_bootstrap = trial_context.get("bootstrap_fetch_observation")
    bootstrap_candidate = trial_context.get("candidate_observation")
    bootstrap_evidence = (
        replayed_bootstrap.get("evidence")
        if isinstance(replayed_bootstrap, Mapping)
        and isinstance(replayed_bootstrap.get("evidence"), Mapping)
        else None
    )
    bootstrap_result_predecessor = bool(
        isinstance(bootstrap_evidence, Mapping)
        and (
            event.get("previous_digest")
            == replayed_bootstrap.get("restore_event_digest")
            or (
                isinstance(bootstrap_candidate, Mapping)
                and bootstrap_candidate.get("source_intent")
                == bootstrap_evidence.get("source_intent")
                and event.get("previous_digest")
                == bootstrap_candidate.get("restore_event_digest")
            )
        )
    )
    if (
        not shared_pass
        and event_name == "fetch_result"
        and prior is not None
        and isinstance(replayed_bootstrap, Mapping)
        and isinstance(replayed_bootstrap.get("evidence"), Mapping)
        and prior.get("integration", {}).get("intent")
        == replayed_bootstrap["evidence"].get("source_intent")
        and bootstrap_result_predecessor
    ):
        bridged_event = copy.deepcopy(compat_event)
        bridged_event["previous_digest"] = replayed_bootstrap.get(
            "fetch_intent_event_digest"
        )
        bridged_context = copy.deepcopy(trial_context)
        for name in (
            "bootstrap_fetch_observation",
            "candidate_observation_active",
            "candidate_observation",
        ):
            bridged_context.pop(name, None)
        if builders._merge_transition_valid(
            bridged_event,
            compat_prior,
            compat_current,
            context=bridged_context,
        ):
            shared_pass = True
            trial_context = bridged_context
    recovery_bridge = trial_context.get("bootstrap_recovery_proof")
    if (
        not shared_pass
        and event_name == "fetch_result"
        and prior is not None
        and isinstance(recovery_bridge, Mapping)
        and event.get("previous_digest") == recovery_bridge.get("event_digest")
        and prior.get("integration", {}).get("intent", {}).get("operation")
        == "fetch"
    ):
        bridged_event = copy.deepcopy(compat_event)
        bridged_event["previous_digest"] = recovery_bridge.get(
            "fetch_intent_event_digest"
        )
        bridged_context = copy.deepcopy(trial_context)
        bridged_context.pop("bootstrap_recovery_proof", None)
        if builders._merge_transition_valid(
            bridged_event,
            compat_prior,
            compat_current,
            context=bridged_context,
        ):
            shared_pass = True
            trial_context = bridged_context
    raw_result = trial_context.get("rebase_raw_result")
    replayed_rebase_intent = trial_context.get("rebase_intent")
    if (
        not shared_pass
        and event_name in {"rebase_conflict", "rebase_result"}
        and prior is not None
        and isinstance(raw_result, Mapping)
        and isinstance(replayed_rebase_intent, Mapping)
        and raw_result.get("digest") == event.get("previous_digest")
        and raw_result.get("intent_digest") == replayed_rebase_intent.get("digest")
        and raw_result.get("generation_digest") == event.get("generation_digest")
        and raw_result.get("evidence") == prior.get("integration", {}).get("intent")
        and _merge_rebase_result_classification(prior) in {"success", "failed"}
    ):
        bridged_event = copy.deepcopy(compat_event)
        bridged_event["previous_digest"] = replayed_rebase_intent["digest"]
        bridged_context = copy.deepcopy(trial_context)
        bridged_context.pop("rebase_raw_result", None)
        if builders._merge_transition_valid(
            bridged_event,
            compat_prior,
            compat_current,
            context=bridged_context,
        ):
            shared_pass = True
            trial_context = bridged_context
    recovered_absent_rebase_intent = _recovered_absent_rebase_intent_digest(
        event, prior, trial_context
    )
    if not shared_pass and recovered_absent_rebase_intent is not None:
        bridged_event = copy.deepcopy(compat_event)
        bridged_event["previous_digest"] = recovered_absent_rebase_intent
        bridged_context = copy.deepcopy(trial_context)
        for name in (
            "candidate_observation_active",
            "candidate_observation",
            "recovery_proof_bridge",
        ):
            bridged_context.pop(name, None)
        if builders._merge_transition_valid(
            bridged_event,
            compat_prior,
            compat_current,
            context=bridged_context,
        ):
            shared_pass = True
            trial_context = bridged_context
    if (
        shared_pass
        and event_name == "rebase_result"
        and prior is not None
        and prior.get("state") == current.get("state") == "rebasing"
        and prior.get("candidate") == current.get("candidate")
        and _merge_rebase_result_classification(current) in {"success", "failed"}
        and isinstance(trial_context.get("rebase_intent"), Mapping)
    ):
        trial_context["rebase_raw_result"] = {
            "digest": event.get("digest"),
            "intent_digest": trial_context["rebase_intent"].get("digest"),
            "generation_digest": event.get("generation_digest"),
            "evidence": copy.deepcopy(current.get("integration", {}).get("intent")),
        }
    if not shared_pass:
        direct_retry = bool(
            event_name == "epoch_intent"
            and prior is not None
            and prior.get("state") == "reverification_failed"
            and current.get("state") == "reverifying"
        )
        fact = _merge_plan_position_fact(prior or {}, current)
        scoped_position = bool(
            event_name == "gate_recorded"
            and isinstance(fact, Mapping)
            and fact.get("gate_plan_position", {}).get("kind") == "scoped-mutation"
            and prior is not None
            and prior.get("state") == current.get("state") == "reverifying"
        )
        payload = event.get("payload")
        prior_push = (
            prior_integration.get("push")
            if isinstance(prior_integration, Mapping)
            else None
        )
        current_push = (
            current_integration.get("push")
            if isinstance(current_integration, Mapping)
            else None
        )
        event_at = builders._utc_value(event.get("at"))
        prior_deadline = (
            builders._utc_value(prior.get("inactive_after"))
            if prior is not None
            else None
        )
        current_deadline = builders._utc_value(current.get("inactive_after"))
        active_event = bool(
            event_at is not None
            and prior_deadline is not None
            and current_deadline is not None
            and event_at < prior_deadline
            and current.get("last_event_at") == event.get("at")
            and current_deadline == event_at + dt.timedelta(hours=24)
        )
        delta = payload.get("delta") if isinstance(payload, Mapping) else None
        plain_delta = bool(
            isinstance(payload, Mapping)
            and set(payload) == {"delta"}
            and isinstance(delta, Mapping)
        )
        replayed_push = trial_context.get("push_intent")
        replayed_remote_observation = trial_context.get("remote_observation")
        scope_exceeded_result = bool(
            event_name == "fetch_result"
            and prior is not None
            and current.get("candidate") is not None
            and current.get("state") == "classifying"
            and isinstance(payload, Mapping)
            and isinstance(payload.get("scope_proof"), Mapping)
            and payload["scope_proof"].get("result") == "exceeded"
        )
        sealed_fetch_to_reverify = bool(
            event_name == "fetch_result"
            and epoch_fetch_intent_digest is None
            and prior is not None
            and prior.get("state") == "rebasing"
            and current.get("state") == "reverifying"
            and isinstance(current_integration, Mapping)
            and isinstance(current_integration.get("epoch"), Mapping)
            and current_integration["epoch"].get("gate_plan", {}).get("status")
            == "sealed"
        )
        sealed_rebase_successor = bool(
            event_name == "rebase_result"
            and prior is not None
            and prior.get("state") in {"rebasing", "rebase_conflict"}
            and current.get("state") == "reverifying"
            and isinstance(prior_integration, Mapping)
            and isinstance(current_integration, Mapping)
            and isinstance(prior_integration.get("epoch"), Mapping)
            and isinstance(current_integration.get("epoch"), Mapping)
            and prior_integration["epoch"].get("gate_plan", {}).get("status")
            == "unsealed"
            and current_integration["epoch"].get("gate_plan", {}).get("status")
            == "sealed"
            and prior.get("candidate") != current.get("candidate")
        )
        current_remote_intent = (
            current_integration.get("intent")
            if isinstance(current_integration, Mapping)
            else None
        )
        remote_observation_intent_valid = bool(
            isinstance(current_remote_intent, Mapping)
            and set(current_remote_intent)
            == {
                "schema",
                "transaction",
                "chain_id",
                "attempt_identity",
                "phase",
                "push_intent_digest",
            }
            and current_remote_intent.get("schema")
            == "forge-remote-observation-intent/1"
            and current_remote_intent.get("transaction") == "merge"
            and current_remote_intent.get("chain_id") == current.get("chain_id")
            and isinstance(current_epoch, Mapping)
            and current_remote_intent.get("attempt_identity")
            == current_epoch.get("intent_digest")
            and isinstance(replayed_epoch, Mapping)
            and replayed_epoch.get("digest") == current_epoch.get("intent_digest")
            and replayed_epoch.get("generation_digest")
            == current.get("candidate", {}).get("generation_digest")
            and (
                (
                    current_remote_intent.get("phase") == "final-prepush"
                    and current_remote_intent.get("push_intent_digest") is None
                    and replayed_epoch.get("push_consumed") is False
                )
                or (
                    current_remote_intent.get("phase") == "post-push"
                    and replayed_epoch.get("push_consumed") is True
                    and isinstance(replayed_push, Mapping)
                    and replayed_push.get("generation_digest")
                    == event.get("generation_digest")
                    and current_remote_intent.get("push_intent_digest")
                    == replayed_push.get("digest")
                )
            )
        )
        inactive_post_attempt_observation_intent = bool(
            prior is not None
            and isinstance(prior_integration, Mapping)
            and remote_observation_intent_valid
            and _merge_inactive_post_attempt_recovery_ready(prior, history)
            and event_at is not None
            and prior_deadline is not None
            and event_at >= prior_deadline
            and current_deadline == prior_deadline
            and current.get("last_event_at") == event.get("at")
            and current_remote_intent.get("phase") == "post-push"
            and current_remote_intent.get("attempt_identity")
            == prior_integration.get("epoch", {}).get("intent_digest")
        )
        observation_progress_restore = bool(
            prior is not None
            and isinstance(prior_integration, Mapping)
            and isinstance(prior_integration.get("intent"), Mapping)
            and isinstance(current_remote_intent, Mapping)
            and _remote_observation_progress_valid(
                prior, prior_integration["intent"]
            )
            and prior_integration["intent"].get("stage")
            in {"fetch-result", "containment-result"}
            and isinstance(replayed_remote_observation, Mapping)
            and replayed_remote_observation.get("generation_digest")
            == event.get("generation_digest")
            and replayed_remote_observation.get("progress_event_digest")
            == event.get("previous_digest")
            and replayed_remote_observation.get("progress")
            == prior_integration["intent"]
            and replayed_remote_observation.get("intent")
            == current_remote_intent
        )
        observation_intent = bool(
            event_name == "condition_recorded"
            and prior is not None
            and prior.get("state") == current.get("state")
            and isinstance(prior_integration, Mapping)
            and isinstance(current_integration, Mapping)
            and current_integration.get("condition")
            == prior_integration.get("condition")
            and current_integration.get("primary_condition")
            == prior_integration.get("primary_condition")
            and isinstance(current_integration.get("intent"), Mapping)
            and current_integration["intent"].get("schema")
            == "forge-remote-observation-intent/1"
            and remote_observation_intent_valid
            and all(
                prior_integration.get(name) == current_integration.get(name)
                for name in set(prior_integration) - {"intent"}
            )
            and plain_delta
            and delta == {"integration": current_integration}
            and all(
                prior.get(name) == current.get(name)
                for name in MERGE_STATE_KEYS
                - {"last_event_at", "inactive_after", "integration"}
            )
            and (
                active_event
                or inactive_post_attempt_observation_intent
                or observation_progress_restore
            )
        )
        push_result_recorded = bool(
            event_name == "condition_recorded"
            and prior is not None
            and prior.get("state") == current.get("state") == "pushing"
            and isinstance(prior_push, Mapping)
            and isinstance(current_push, Mapping)
            and prior_push.get("result") is None
            and isinstance(current_push.get("result"), Mapping)
            and all(
                prior_push.get(name) == current_push.get(name)
                for name in set(prior_push) - {"result"}
            )
            and isinstance(prior_integration, Mapping)
            and isinstance(current_integration, Mapping)
            and all(
                prior_integration.get(name) == current_integration.get(name)
                for name in set(prior_integration) - {"push"}
            )
        )
        candidate_observation_progress = bool(
            event_name == "condition_recorded"
            and prior is not None
            and prior.get("state") == current.get("state")
            and plain_delta
            and delta == {"integration": current_integration}
            and all(
                prior.get(name) == current.get(name)
                for name in MERGE_STATE_KEYS
                - {"last_event_at", "inactive_after", "integration"}
            )
            and _merge_candidate_observation_transition_valid(prior, current)
        )
        bootstrap_fetch_observation = bool(
            event_name == "condition_recorded"
            and prior is not None
            and prior.get("state") == current.get("state") == "classifying"
            and plain_delta
            and delta == {"integration": current_integration}
            and all(
                prior.get(name) == current.get(name)
                for name in MERGE_STATE_KEYS
                - {"last_event_at", "inactive_after", "integration"}
            )
            and _bootstrap_fetch_observation_transition_valid(prior, current)
        )
        stable_push_boundary = bool(
            prior is not None
            and all(
                prior.get(name) == current.get(name)
                for name in MERGE_STATE_KEYS
                - {
                    "last_event_at",
                    "inactive_after",
                    "state",
                    "review",
                    "approval",
                    "authorization",
                    "integration",
                }
            )
        )
        current_intent = (
            current_integration.get("intent")
            if isinstance(current_integration, Mapping)
            else None
        )
        prior_intent = (
            prior_integration.get("intent")
            if isinstance(prior_integration, Mapping)
            else None
        )
        remote_observation_progress_predecessor = bool(
            isinstance(replayed_remote_observation, Mapping)
            and replayed_remote_observation.get("generation_digest")
            == event.get("generation_digest")
            and isinstance(replayed_remote_observation.get("intent"), Mapping)
            and isinstance(current_intent, Mapping)
            and all(
                replayed_remote_observation["intent"].get(name)
                == current_intent.get(name)
                for name in {
                    "transaction",
                    "chain_id",
                    "attempt_identity",
                    "phase",
                    "push_intent_digest",
                }
            )
            and (
                (
                    replayed_remote_observation.get("intent_event_digest")
                    == event.get("previous_digest")
                    and replayed_remote_observation.get("intent") == prior_intent
                    and replayed_remote_observation.get("progress_event_digest")
                    is None
                    and replayed_remote_observation.get("restore_event_digest")
                    is None
                    and replayed_remote_observation.get("completed_progress") is None
                )
                or (
                    replayed_remote_observation.get("progress_event_digest")
                    == event.get("previous_digest")
                    and replayed_remote_observation.get("progress") == prior_intent
                )
            )
        )
        replayed_fetch_observation = trial_context.get("epoch_fetch_observation")
        replayed_candidate_observation = trial_context.get(
            "candidate_observation"
        )
        epoch_fetch_observation = bool(
            event_name == "condition_recorded"
            and prior is not None
            and prior.get("state") == current.get("state") == "rebasing"
            and active_event
            and plain_delta
            and isinstance(prior_integration, Mapping)
            and isinstance(current_integration, Mapping)
            and isinstance(prior_intent, Mapping)
            and prior_intent.get("operation") == "fetch"
            and isinstance(current_intent, Mapping)
            and _epoch_fetch_observation_record_valid(current, current_intent)
            and _epoch_fetch_observation_predecessor_valid(
                event, current_intent, prior_intent, trial_context
            )
            and all(
                prior_integration.get(name) == current_integration.get(name)
                for name in set(prior_integration) - {"intent"}
            )
            and all(
                prior.get(name) == current.get(name)
                for name in MERGE_STATE_KEYS
                - {"last_event_at", "inactive_after", "integration"}
            )
            and delta == {"integration": current_integration}
            and isinstance(replayed_epoch, Mapping)
            and replayed_epoch.get("digest")
            == current_integration.get("epoch", {}).get("intent_digest")
            and replayed_epoch.get("generation_digest")
            == current.get("candidate", {}).get("generation_digest")
        )
        ancestry_intent_transition = bool(
            isinstance(current_intent, Mapping)
            and current_intent.get("phase") == "intent"
            and _epoch_ancestry_record_valid(current, current_intent)
            and isinstance(prior_intent, Mapping)
            and _epoch_fetch_observation_record_valid(prior or {}, prior_intent)
            and _epoch_fetch_observation_passed(prior_intent)
            and isinstance(replayed_fetch_observation, Mapping)
            and current_intent.get("fetch_observation_event_digest")
            == replayed_fetch_observation.get("digest")
            and replayed_fetch_observation.get("evidence") == prior_intent
            and isinstance(replayed_candidate_observation, Mapping)
            and replayed_candidate_observation.get("source_intent")
            == prior_intent
            and current_intent.get("candidate_observation_digest")
            == replayed_candidate_observation.get("evidence_digest")
            and event.get("previous_digest")
            == replayed_candidate_observation.get("restore_event_digest")
            and prior is not None
            and prior.get("state") == current.get("state") == "rebasing"
            and all(
                prior_integration.get(name) == current_integration.get(name)
                for name in set(prior_integration) - {"intent"}
            )
        )
        ancestry_result_transition = bool(
            isinstance(prior_intent, Mapping)
            and prior_intent.get("phase") == "intent"
            and _epoch_ancestry_record_valid(prior or {}, prior_intent)
            and isinstance(current_intent, Mapping)
            and current_intent.get("phase") == "result"
            and _epoch_ancestry_record_valid(current, current_intent)
            and current_intent.get("intent_event_digest")
            == event.get("previous_digest")
            and all(
                prior_intent.get(name) == current_intent.get(name)
                for name in set(prior_intent) - {"phase", "recorded_at"}
            )
            and isinstance(prior_integration, Mapping)
            and isinstance(current_integration, Mapping)
            and all(
                prior_integration.get(name) == current_integration.get(name)
                for name in set(prior_integration) - {"intent", "epoch"}
            )
            and isinstance(prior_integration.get("epoch"), Mapping)
            and isinstance(current_integration.get("epoch"), Mapping)
            and all(
                prior_integration["epoch"].get(name)
                == current_integration["epoch"].get(name)
                for name in set(prior_integration["epoch"])
            )
            and current_integration["epoch"].get("gate_plan", {}).get("status")
            == "unsealed"
            and prior is not None
            and prior.get("state") == current.get("state") == "rebasing"
        )
        epoch_ancestry_progress = bool(
            event_name == "condition_recorded"
            and prior is not None
            and active_event
            and plain_delta
            and all(
                prior.get(name) == current.get(name)
                for name in MERGE_STATE_KEYS
                - {"last_event_at", "inactive_after", "integration"}
            )
            and (ancestry_intent_transition or ancestry_result_transition)
            and isinstance(replayed_epoch, Mapping)
            and replayed_epoch.get("digest")
            == current_integration.get("epoch", {}).get("intent_digest")
            and replayed_epoch.get("generation_digest")
            == current.get("candidate", {}).get("generation_digest")
            and delta
            == {"integration": current_integration}
        )
        post_push_observation_intent = bool(
            isinstance(current_intent, Mapping)
            and set(current_intent)
            == {
                "schema",
                "transaction",
                "chain_id",
                "attempt_identity",
                "phase",
                "push_intent_digest",
            }
            and current_intent.get("schema")
            == "forge-remote-observation-intent/1"
            and current_intent.get("transaction") == "merge"
            and current_intent.get("chain_id") == current.get("chain_id")
            and current_intent.get("phase") == "post-push"
            and isinstance(current_epoch, Mapping)
            and current_intent.get("attempt_identity")
            == current_epoch.get("intent_digest")
            and isinstance(replayed_push, Mapping)
            and current_intent.get("push_intent_digest")
            == replayed_push.get("digest")
        )
        observation_progress = bool(
            event_name == "condition_recorded"
            and stable_push_boundary
            and prior is not None
            and prior.get("state") == current.get("state")
            and isinstance(prior_integration, Mapping)
            and isinstance(current_integration, Mapping)
            and all(
                prior_integration.get(name) == current_integration.get(name)
                for name in set(prior_integration) - {"intent"}
            )
            and _remote_observation_progress_transition_valid(prior, current)
            and isinstance(current_intent, Mapping)
            and remote_observation_progress_predecessor
            and (
                current_intent.get("stage") != "containment-intent"
                or active_event
                or replayed_remote_observation.get("admitted_inactive") is True
            )
            and isinstance(replayed_epoch, Mapping)
            and replayed_epoch.get("digest")
            == current_integration.get("epoch", {}).get("intent_digest")
            and replayed_epoch.get("generation_digest")
            == current.get("candidate", {}).get("generation_digest")
            and (
                (
                    current_intent.get("phase") == "final-prepush"
                    and replayed_epoch.get("push_consumed") is False
                    and current_intent.get("push_intent_digest") is None
                )
                or (
                    current_intent.get("phase") == "post-push"
                    and replayed_epoch.get("push_consumed") is True
                    and isinstance(replayed_push, Mapping)
                    and current_intent.get("push_intent_digest")
                    == replayed_push.get("digest")
                )
            )
            and plain_delta
            and delta == {"integration": current_integration}
        )
        inactive_observation_completed = _replayed_remote_observation_completed(
            event, current, trial_context
        )
        push_result = (
            current_push.get("result")
            if isinstance(current_push, Mapping)
            else None
        )
        normalized_old_tip_observation = bool(
            event_name == "push_observed"
            and active_event
            and stable_push_boundary
            and prior is not None
            and prior.get("state") == current.get("state") == "pushing"
            and prior.get("review") == current.get("review")
            and prior.get("approval") == current.get("approval")
            and prior.get("authorization") == current.get("authorization")
            and isinstance(prior_integration, Mapping)
            and isinstance(current_integration, Mapping)
            and isinstance(prior_push, Mapping)
            and prior_push == current_push
            and isinstance(push_result, Mapping)
            and push_result.get("classification")
            in {"outcome-unknown", "non-fast-forward"}
            and isinstance(replayed_epoch, Mapping)
            and replayed_epoch.get("digest")
            == current_integration.get("epoch", {}).get("intent_digest")
            and replayed_epoch.get("generation_digest")
            == current.get("candidate", {}).get("generation_digest")
            and replayed_epoch.get("push_consumed") is True
            and post_push_observation_intent
            and _merge_old_tip_all_false(current)
            and current_integration.get("condition") == "none"
            and current_integration.get("primary_condition") == "none"
            and current_integration.get("remote_movement_count") == 0
            and all(
                prior_integration.get(name) == current_integration.get(name)
                for name in set(prior_integration)
                - {"condition", "primary_condition", "observed"}
            )
            and plain_delta
            and delta == {"integration": current_integration}
        )
        push_stable_except_landed = bool(
            isinstance(prior_push, Mapping)
            and isinstance(current_push, Mapping)
            and set(prior_push) == set(current_push)
            and all(
                prior_push.get(name) == current_push.get(name)
                for name in set(prior_push) - {"landed_head"}
            )
        )
        latest_contained_attempt = _merge_latest_contained_attempt(current)
        inactive_current_observation = bool(
            event_name == "push_observed"
            and not active_event
            and stable_push_boundary
            and prior is not None
            and prior.get("state") in _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES
            and prior.get("state") != "pushed"
            and current.get("state") == "pushed"
            and prior.get("review") == current.get("review")
            and prior.get("approval") == current.get("approval")
            and prior.get("authorization") == current.get("authorization")
            and isinstance(prior_integration, Mapping)
            and isinstance(current_integration, Mapping)
            and push_stable_except_landed
            and isinstance(current_push, Mapping)
            and current_push.get("landed_head") == latest_contained_attempt
            and latest_contained_attempt == current_push.get("intended_head")
            and isinstance(current.get("candidate"), Mapping)
            and latest_contained_attempt
            == current["candidate"].get("candidate_head")
            and isinstance(replayed_epoch, Mapping)
            and replayed_epoch.get("digest")
            == current_integration.get("epoch", {}).get("intent_digest")
            and replayed_epoch.get("generation_digest")
            == current.get("candidate", {}).get("generation_digest")
            and replayed_epoch.get("push_consumed") is True
            and post_push_observation_intent
            and inactive_observation_completed
            and _merge_containment(current)[0] == "current"
            and current_integration.get("condition") == "none"
            and current_integration.get("primary_condition") == "none"
            and current_integration.get("remote_movement_count") == 0
            and all(
                prior_integration.get(name) == current_integration.get(name)
                for name in set(prior_integration)
                - {
                    "condition",
                    "primary_condition",
                    "remote_movement_count",
                    "observed",
                    "push",
                }
            )
            and plain_delta
            and delta == {"state": "pushed", "integration": current_integration}
        )
        inactive_all_false_observation = bool(
            event_name == "push_observed"
            and not active_event
            and stable_push_boundary
            and prior is not None
            and prior.get("state") in _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES
            and current.get("state") == "pushing"
            and prior.get("review") == current.get("review")
            and prior.get("approval") == current.get("approval")
            and prior.get("authorization") == current.get("authorization")
            and isinstance(prior_integration, Mapping)
            and isinstance(current_integration, Mapping)
            and push_stable_except_landed
            and isinstance(current_push, Mapping)
            and current_push.get("landed_head") is None
            and latest_contained_attempt is None
            and isinstance(replayed_epoch, Mapping)
            and replayed_epoch.get("digest")
            == current_integration.get("epoch", {}).get("intent_digest")
            and replayed_epoch.get("generation_digest")
            == current.get("candidate", {}).get("generation_digest")
            and replayed_epoch.get("push_consumed") is True
            and post_push_observation_intent
            and inactive_observation_completed
            and _merge_containment(current)[0] == "all-false"
            and current_integration.get("condition") == "none"
            and current_integration.get("primary_condition") == "none"
            and current_integration.get("remote_movement_count") == 0
            and all(
                prior_integration.get(name) == current_integration.get(name)
                for name in set(prior_integration)
                - {
                    "condition",
                    "primary_condition",
                    "remote_movement_count",
                    "observed",
                    "push",
                }
            )
            and plain_delta
            and delta
            == (
                {"integration": current_integration}
                if prior.get("state") == "pushing"
                else {"state": "pushing", "integration": current_integration}
            )
        )
        inactive_older_observation = bool(
            event_name == "push_observed"
            and not active_event
            and stable_push_boundary
            and prior is not None
            and prior.get("state") in _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES
            and current.get("state") == "pushing"
            and prior.get("review") == current.get("review")
            and prior.get("approval") == current.get("approval")
            and prior.get("authorization") == current.get("authorization")
            and isinstance(prior_integration, Mapping)
            and isinstance(current_integration, Mapping)
            and push_stable_except_landed
            and isinstance(current_push, Mapping)
            and current_push.get("landed_head") == latest_contained_attempt
            and latest_contained_attempt is not None
            and latest_contained_attempt != current_push.get("intended_head")
            and isinstance(replayed_epoch, Mapping)
            and replayed_epoch.get("digest")
            == current_integration.get("epoch", {}).get("intent_digest")
            and replayed_epoch.get("generation_digest")
            == current.get("candidate", {}).get("generation_digest")
            and replayed_epoch.get("push_consumed") is True
            and post_push_observation_intent
            and inactive_observation_completed
            and _merge_containment(current)[0] == "older"
            and current_integration.get("condition") == "none"
            and current_integration.get("primary_condition") == "none"
            and current_integration.get("remote_movement_count") == 0
            and all(
                prior_integration.get(name) == current_integration.get(name)
                for name in set(prior_integration)
                - {
                    "condition",
                    "primary_condition",
                    "remote_movement_count",
                    "observed",
                    "push",
                }
            )
            and plain_delta
            and delta
            == (
                {"integration": current_integration}
                if prior.get("state") == "pushing"
                else {"state": "pushing", "integration": current_integration}
            )
        )
        inactive_unavailable_observation = bool(
            event_name == "push_observed"
            and not active_event
            and stable_push_boundary
            and prior is not None
            and prior.get("state") in _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES
            and current.get("state") == "pushing"
            and prior.get("review") == current.get("review")
            and prior.get("approval") == current.get("approval")
            and prior.get("authorization") == current.get("authorization")
            and isinstance(prior_integration, Mapping)
            and isinstance(current_integration, Mapping)
            and push_stable_except_landed
            and isinstance(current_push, Mapping)
            and current_push.get("landed_head") is None
            and isinstance(replayed_epoch, Mapping)
            and replayed_epoch.get("digest")
            == current_integration.get("epoch", {}).get("intent_digest")
            and replayed_epoch.get("generation_digest")
            == current.get("candidate", {}).get("generation_digest")
            and replayed_epoch.get("push_consumed") is True
            and post_push_observation_intent
            and inactive_observation_completed
            and _merge_containment(current)[0] == "unresolved"
            and isinstance(current_integration.get("observed"), Mapping)
            and current_integration["observed"].get("exists") is None
            and current_integration["observed"].get("oid") is None
            and current_integration["observed"].get("contains_intended_head")
            is None
            and current_integration.get("condition") == "push-outcome-unknown"
            and current_integration.get("primary_condition") == "none"
            and current_integration.get("remote_movement_count") == 0
            and all(
                prior_integration.get(name) == current_integration.get(name)
                for name in set(prior_integration)
                - {
                    "condition",
                    "primary_condition",
                    "remote_movement_count",
                    "observed",
                    "push",
                }
            )
            and plain_delta
            and delta
            == (
                {"integration": current_integration}
                if prior.get("state") == "pushing"
                else {"state": "pushing", "integration": current_integration}
            )
        )

        retry_epoch = (
            prior_integration.get("epoch")
            if isinstance(prior_integration, Mapping)
            else None
        )
        retry_plan = (
            retry_epoch.get("gate_plan")
            if isinstance(retry_epoch, Mapping)
            else None
        )
        retry_intent = (
            prior_integration.get("intent")
            if isinstance(prior_integration, Mapping)
            else None
        )
        replayed_retry_observation = trial_context.get("push_retry_observation")
        preceding_retry_observation = (
            replayed_retry_observation.get("previous")
            if isinstance(replayed_retry_observation, Mapping)
            else None
        )
        prior_observed = (
            prior_integration.get("observed")
            if isinstance(prior_integration, Mapping)
            else None
        )
        retry_attempts = (
            prior_push.get("attempted_heads")
            if isinstance(prior_push, Mapping)
            else None
        )
        current_attempts = (
            current_push.get("attempted_heads")
            if isinstance(current_push, Mapping)
            else None
        )
        candidate = current.get("candidate")
        current_authority = _merge_current_authority_valid(current)
        retry_push_intent = bool(
            event_name == "push_intent"
            and active_event
            and stable_push_boundary
            and prior is not None
            and prior.get("state") == current.get("state") == "pushing"
            and prior.get("review") == current.get("review")
            and prior.get("approval") == current.get("approval")
            and prior.get("authorization") == current.get("authorization")
            and isinstance(prior_integration, Mapping)
            and isinstance(current_integration, Mapping)
            and isinstance(prior_push, Mapping)
            and (
                prior_push.get("result") is None
                or isinstance(prior_push.get("result"), Mapping)
            )
            and isinstance(current_push, Mapping)
            and isinstance(retry_epoch, Mapping)
            and current_epoch == retry_epoch
            and isinstance(retry_plan, Mapping)
            and retry_plan.get("status") == "sealed"
            and retry_plan.get("cursor") == len(retry_plan.get("suite", []))
            and isinstance(replayed_epoch, Mapping)
            and replayed_epoch.get("digest") == retry_epoch.get("intent_digest")
            and replayed_epoch.get("generation_digest")
            == retry_epoch.get("generation_digest")
            and replayed_epoch.get("push_consumed") is True
            and isinstance(retry_intent, Mapping)
            and set(retry_intent)
            == {
                "schema",
                "transaction",
                "chain_id",
                "attempt_identity",
                "phase",
                "push_intent_digest",
            }
            and retry_intent.get("schema")
            == "forge-remote-observation-intent/1"
            and retry_intent.get("transaction") == "merge"
            and retry_intent.get("chain_id") == prior.get("chain_id")
            and retry_intent.get("attempt_identity")
            == retry_epoch.get("intent_digest")
            and retry_intent.get("phase") == "post-push"
            and retry_intent.get("push_intent_digest")
            == (
                replayed_push.get("digest")
                if isinstance(replayed_push, Mapping)
                else None
            )
            and isinstance(replayed_retry_observation, Mapping)
            and set(replayed_retry_observation)
            == {
                "digest",
                "generation_digest",
                "push_intent_digest",
                "inflight_digest",
                "old_tip_all_false",
                "previous",
            }
            and replayed_retry_observation.get("generation_digest")
            == retry_epoch.get("generation_digest")
            and replayed_retry_observation.get("push_intent_digest")
            == retry_intent.get("push_intent_digest")
            and isinstance(prior_observed, Mapping)
            and replayed_retry_observation.get("inflight_digest")
            == prior_observed.get("inflight_digest")
            and replayed_retry_observation.get("old_tip_all_false") is True
            and isinstance(preceding_retry_observation, Mapping)
            and set(preceding_retry_observation)
            == {
                "digest",
                "push_intent_digest",
                "inflight_digest",
                "old_tip_all_false",
            }
            and preceding_retry_observation.get("push_intent_digest")
            == retry_intent.get("push_intent_digest")
            and preceding_retry_observation.get("old_tip_all_false") is True
            and replayed_retry_observation.get("digest")
            != preceding_retry_observation.get("digest")
            and replayed_retry_observation.get("inflight_digest")
            != preceding_retry_observation.get("inflight_digest")
            and _merge_old_tip_all_false(prior)
            and current_authority
            and current_integration.get("condition") == "none"
            and current_integration.get("primary_condition") == "none"
            and current_integration.get("remote_movement_count") == 0
            and current_integration.get("observed") is None
            and isinstance(current_intent, Mapping)
            and set(current_intent) == {"operation", "operation_nonce", "attempt"}
            and current_intent.get("operation") == "push"
            and current_intent.get("operation_nonce")
            == retry_epoch.get("operation_nonce")
            and isinstance(retry_attempts, list)
            and isinstance(current_attempts, list)
            and current_attempts
            == [*retry_attempts, candidate.get("candidate_head")]
            and current_intent.get("attempt") == len(current_attempts)
            and current_push.get("expected_old_tip")
            == candidate.get("remote_tip")
            and current_push.get("intended_head")
            == candidate.get("candidate_head")
            and current_push.get("destination_ref")
            == candidate.get("destination_ref")
            and current_push.get("intended_at") == event.get("at")
            and current_push.get("result") is None
            and current_push.get("landed_head") == prior_push.get("landed_head")
            and all(
                prior_integration.get(name) == current_integration.get(name)
                for name in set(prior_integration)
                - {
                    "condition",
                    "primary_condition",
                    "intent",
                    "observed",
                    "push",
                }
            )
            and plain_delta
            and delta == {"integration": current_integration}
        )

        invalid_mode_intent = (
            current_integration.get("intent")
            if isinstance(current_integration, Mapping)
            else None
        )
        prior_plan = (
            prior_integration.get("epoch", {}).get("gate_plan")
            if isinstance(prior_integration, Mapping)
            and isinstance(prior_integration.get("epoch"), Mapping)
            else None
        )
        prior_mode_intent = (
            prior_integration.get("intent")
            if isinstance(prior_integration, Mapping)
            else None
        )
        prior_mode_observed = (
            prior_integration.get("observed")
            if isinstance(prior_integration, Mapping)
            else None
        )
        prior_iteration = (
            prior.get("review", {}).get("iteration")
            if prior is not None and isinstance(prior.get("review"), Mapping)
            else None
        )
        expected_invalid_delta = (
            {
                name: current.get(name)
                for name in (
                    "state",
                    "review",
                    "approval",
                    "authorization",
                    "integration",
                )
                if prior is not None and prior.get(name) != current.get(name)
            }
            if prior is not None
            else {}
        )
        invalid_final_mode_park = bool(
            event_name == "reverification_result"
            and active_event
            and stable_push_boundary
            and prior is not None
            and prior.get("state") in {"rebasing", "reverifying"}
            and current.get("state") == "revising"
            and isinstance(prior_integration, Mapping)
            and isinstance(current_integration, Mapping)
            and prior_integration.get("condition") == "none"
            and prior_integration.get("primary_condition") == "none"
            and isinstance(prior_plan, Mapping)
            and prior_plan.get("status") == "sealed"
            and prior_plan.get("cursor") == len(prior_plan.get("suite", []))
            and isinstance(replayed_epoch, Mapping)
            and replayed_epoch.get("digest")
            == prior_integration.get("epoch", {}).get("intent_digest")
            and replayed_epoch.get("generation_digest")
            == prior_integration.get("epoch", {}).get("generation_digest")
            and replayed_epoch.get("push_consumed") is False
            and isinstance(prior_mode_intent, Mapping)
            and set(prior_mode_intent)
            == {
                "schema",
                "transaction",
                "chain_id",
                "attempt_identity",
                "phase",
                "push_intent_digest",
            }
            and prior_mode_intent.get("schema")
            == "forge-remote-observation-intent/1"
            and prior_mode_intent.get("transaction") == "merge"
            and prior_mode_intent.get("chain_id") == prior.get("chain_id")
            and prior_mode_intent.get("attempt_identity")
            == prior_integration.get("epoch", {}).get("intent_digest")
            and prior_mode_intent.get("phase") == "final-prepush"
            and prior_mode_intent.get("push_intent_digest") is None
            and isinstance(prior_mode_observed, Mapping)
            and prior_mode_observed.get("exists") is True
            and prior_mode_observed.get("oid")
            == current.get("candidate", {}).get("remote_tip")
            and current_integration.get("epoch") is None
            and current_integration.get("condition") == "none"
            and current_integration.get("primary_condition") == "none"
            and current_integration.get("remote_movement_count") == 0
            and isinstance(invalid_mode_intent, Mapping)
            and set(invalid_mode_intent)
            == {
                "schema",
                "operation",
                "candidate_head",
                "manifest_digest",
                "result",
                "recorded_at",
            }
            and invalid_mode_intent.get("schema")
            == "forge-history-mutation-mode-result/1"
            and invalid_mode_intent.get("operation") == "history-mutation-mode"
            and invalid_mode_intent.get("candidate_head")
            == candidate.get("candidate_head")
            and SHA256_RE.fullmatch(
                str(invalid_mode_intent.get("manifest_digest", ""))
            )
            is not None
            and invalid_mode_intent.get("result") == "invalid"
            and builders._utc_value(invalid_mode_intent.get("recorded_at"))
            is not None
            and all(
                prior_integration.get(name) == current_integration.get(name)
                for name in set(prior_integration)
                - {
                    "condition",
                    "primary_condition",
                    "remote_movement_count",
                    "epoch",
                    "intent",
                }
            )
            and current.get("review")
            == ({"iteration": prior_iteration} if type(prior_iteration) is int else {})
            and current.get("approval") == {}
            and current.get("authorization") == {}
            and plain_delta
            and delta == expected_invalid_delta
        )
        parked_completed_plan = bool(
            event_name == "reverification_result"
            and prior is not None
            and prior.get("state") == "reverifying"
            and current.get("state") == "reviewing"
            and isinstance(prior_integration, Mapping)
            and isinstance(prior_integration.get("epoch"), Mapping)
            and isinstance(
                prior_integration["epoch"].get("gate_plan"), Mapping
            )
            and prior_integration["epoch"]["gate_plan"].get("status")
            == "sealed"
            and prior_integration["epoch"]["gate_plan"].get("cursor")
            == len(prior_integration["epoch"]["gate_plan"].get("suite", []))
            and isinstance(current_integration, Mapping)
            and current_integration.get("epoch") is None
            and current.get("steps") == prior.get("steps")
        )
        prior_candidate = prior.get("candidate") if prior is not None else None
        carried_candidate = current.get("candidate")
        prior_review = prior.get("review") if prior is not None else None
        prior_iteration = (
            prior_review.get("iteration")
            if isinstance(prior_review, Mapping)
            else None
        )
        gate_tuple_reclassified = bool(
            event_name == "generation_refreshed"
            and prior is not None
            and prior.get("state") == "reverifying"
            and current.get("state") == "verifying"
            and isinstance(prior_candidate, Mapping)
            and isinstance(carried_candidate, Mapping)
            and carried_candidate.get("generation")
            == int(prior_candidate.get("generation", 0)) + 1
            and carried_candidate != prior_candidate
            and isinstance(prior_integration, Mapping)
            and isinstance(prior_integration.get("epoch"), Mapping)
            and isinstance(current_integration, Mapping)
            and current_integration.get("epoch") is None
            and current_integration.get("condition") == "none"
            and current_integration.get("primary_condition") == "none"
            and all(
                prior_integration.get(name) == current_integration.get(name)
                for name in set(prior_integration)
                - {
                    "condition",
                    "primary_condition",
                    "epoch",
                    "remote_movement_count",
                }
            )
            and current_integration.get("remote_movement_count") == 0
            and current.get("steps") == {}
            and current.get("review")
            == ({"iteration": prior_iteration} if type(prior_iteration) is int else {})
            and current.get("approval") == {}
            and current.get("authorization") == {}
        )
        remote_only_carry = bool(
            event_name == "generation_carried_forward"
            and prior is not None
            and active_event
            and prior.get("state") in {"rebasing", "reverifying"}
            and current.get("state") in {"authorized", "awaiting_approval"}
            and isinstance(prior_candidate, Mapping)
            and isinstance(carried_candidate, Mapping)
            and carried_candidate.get("remote_tip")
            != prior_candidate.get("remote_tip")
            and all(
                carried_candidate.get(name) == prior_candidate.get(name)
                for name in _MERGE_REMOTE_ONLY_IDENTITY_FIELDS
            )
            and carried_candidate.get("generation")
            == int(prior_candidate.get("generation", 0)) + 1
            and prior.get("tier") == current.get("tier")
            and prior.get("policy_source") == current.get("policy_source")
            and current.get("steps") == prior.get("steps")
            and prior.get("review") == current.get("review")
            and prior.get("approval") == current.get("approval")
            and prior.get("authorization") == current.get("authorization")
            and isinstance(prior_integration, Mapping)
            and isinstance(current_integration, Mapping)
            and current_integration.get("epoch") is None
            and current_integration.get("primary_condition") == "none"
            and current_integration.get("condition")
            in {"remote-moved", "remote-churn"}
            and current_integration.get("remote_movement_count")
            == int(prior_integration.get("remote_movement_count", 0)) + 1
            and isinstance(current_integration.get("observed"), Mapping)
            and current_integration["observed"].get("exists") is True
            and current_integration["observed"].get("oid")
            == carried_candidate.get("remote_tip")
            and all(
                prior_integration.get(name) == current_integration.get(name)
                for name in set(prior_integration)
                - {"condition", "epoch", "remote_movement_count", "observed"}
            )
            and _merge_carry_payload_valid(
                event, prior_candidate, carried_candidate
            )
        )
        if not (
            direct_retry
            or scoped_position
            or scope_exceeded_result
            or sealed_fetch_to_reverify
            or sealed_rebase_successor
            or observation_intent
            or candidate_observation_progress
            or bootstrap_fetch_observation
            or epoch_fetch_observation
            or observation_progress
            or epoch_ancestry_progress
            or push_result_recorded
            or normalized_old_tip_observation
            or inactive_current_observation
            or inactive_all_false_observation
            or inactive_older_observation
            or inactive_unavailable_observation
            or retry_push_intent
            or invalid_final_mode_park
            or parked_completed_plan
            or gate_tuple_reclassified
            or remote_only_carry
        ):
            return False
        if normalized_old_tip_observation or retry_push_intent:
            _require_merge_integration_control("push-retry")
        if (
            inactive_current_observation
            or inactive_all_false_observation
            or inactive_older_observation
            or inactive_unavailable_observation
        ):
            _require_merge_integration_control("observation-first-recovery")
        if context is not None and observation_intent:
            if observation_progress_restore:
                completed_observation = copy.deepcopy(
                    dict(replayed_remote_observation)
                )
                completed_observation.update(
                    {
                        "intent_event_digest": event.get("digest"),
                        "intent": copy.deepcopy(current_intent),
                        "progress_event_digest": None,
                        "progress": None,
                        "restore_event_digest": event.get("digest"),
                        "completed_progress": copy.deepcopy(prior_intent),
                    }
                )
                trial_context["remote_observation"] = completed_observation
            else:
                trial_context["remote_observation"] = {
                    "intent_event_digest": event.get("digest"),
                    "generation_digest": event.get("generation_digest"),
                    "intent": copy.deepcopy(current_intent),
                    "admitted_inactive": inactive_post_attempt_observation_intent,
                    "progress_event_digest": None,
                    "progress": None,
                    "restore_event_digest": None,
                    "completed_progress": None,
                }
        if context is not None and observation_progress:
            active_observation = copy.deepcopy(dict(replayed_remote_observation))
            active_observation.update(
                {
                    "progress_event_digest": event.get("digest"),
                    "progress": copy.deepcopy(current_intent),
                    "restore_event_digest": None,
                    "completed_progress": None,
                }
            )
            trial_context["remote_observation"] = active_observation
        if candidate_observation_progress:
            _require_merge_integration_control("observation-first-recovery")
            observation_record = (
                current_intent
                if _merge_candidate_observation_record_valid(
                    current, current_intent
                )
                else prior_intent
                if prior is not None
                and _merge_candidate_observation_record_valid(
                    prior, prior_intent
                )
                else None
            )
            if not isinstance(observation_record, Mapping):
                return False
            active = trial_context.get("candidate_observation_active")
            if (
                isinstance(current_intent, Mapping)
                and current_intent.get("schema")
                == _MERGE_CANDIDATE_OBSERVATION_SCHEMA
                and current_intent.get("stage") == "intent"
            ):
                step_names = _merge_candidate_observation_step_names(
                    current,
                    remote_tip=str(current_intent.get("remote_tip", "")),
                    expected_head=str(current_intent.get("expected_head", "")),
                    classify=current_intent.get("classify"),
                    declared_tier=current_intent.get("declared_tier"),
                )
                if step_names is None:
                    return False
                if current_intent.get("step") == step_names[0]:
                    active = {
                        "observation_binding": current_intent.get(
                            "observation_binding"
                        ),
                        "steps": [],
                    }
                    trial_context["candidate_observation_active"] = active
                elif (
                    not isinstance(active, Mapping)
                    or active.get("observation_binding")
                    != current_intent.get("observation_binding")
                    or not isinstance(active.get("steps"), list)
                    or len(active["steps"]) >= len(step_names)
                    or current_intent.get("step")
                    != step_names[len(active["steps"])]
                ):
                    return False
            elif (
                isinstance(current_intent, Mapping)
                and current_intent.get("schema")
                == _MERGE_CANDIDATE_OBSERVATION_SCHEMA
                and current_intent.get("stage") == "result"
            ):
                if (
                    not isinstance(active, Mapping)
                    or active.get("observation_binding")
                    != current_intent.get("observation_binding")
                    or not isinstance(active.get("steps"), list)
                ):
                    return False
                active_steps = copy.deepcopy(active["steps"])
                active_steps.append(copy.deepcopy(dict(current_intent)))
                evidence = _merge_candidate_observation_evidence(
                    current, active_steps
                )
                trial_context["candidate_observation_active"] = {
                    "observation_binding": current_intent.get(
                        "observation_binding"
                    ),
                    "steps": active_steps,
                }
                if evidence is not None:
                    trial_context["candidate_observation"] = {
                        "event_digest": event.get("digest"),
                        "generation_digest": event.get("generation_digest"),
                        "source_intent": copy.deepcopy(
                            current_intent.get("source_intent")
                        ),
                        "evidence": evidence,
                        "evidence_digest": evidence["evidence_digest"],
                    }
            elif (
                isinstance(prior_intent, Mapping)
                and prior_intent.get("schema")
                == _MERGE_CANDIDATE_OBSERVATION_SCHEMA
                and prior_intent.get("stage") == "result"
                and current_intent == prior_intent.get("source_intent")
            ):
                completed = trial_context.get("candidate_observation")
                if (
                    isinstance(completed, dict)
                    and completed.get("event_digest")
                    == event.get("previous_digest")
                ):
                    completed["restore_event_digest"] = event.get("digest")
        if bootstrap_fetch_observation:
            _require_merge_integration_control("post-fetch-scope-proof")
            selected_bootstrap = (
                current_intent
                if _bootstrap_fetch_observation_record_valid(
                    current, current_intent
                )
                else prior_intent
                if prior is not None
                and _bootstrap_fetch_observation_record_valid(
                    prior, prior_intent
                )
                else None
            )
            if not isinstance(selected_bootstrap, Mapping):
                return False
            if _bootstrap_fetch_observation_record_valid(
                current, current_intent
            ):
                trial_context["bootstrap_fetch_observation"] = {
                    "digest": event.get("digest"),
                    "generation_digest": event.get("generation_digest"),
                    "evidence": copy.deepcopy(current_intent),
                    "fetch_intent_event_digest": current_intent.get(
                        "fetch_intent_event_digest"
                    ),
                }
            else:
                retained_bootstrap = trial_context.get(
                    "bootstrap_fetch_observation"
                )
                if (
                    isinstance(retained_bootstrap, dict)
                    and retained_bootstrap.get("evidence") == prior_intent
                ):
                    retained_bootstrap["restore_event_digest"] = event.get(
                        "digest"
                    )
        if epoch_fetch_observation or epoch_ancestry_progress:
            _require_merge_integration_control("successor-ancestry-observation")
        if invalid_final_mode_park:
            _require_merge_integration_control("final-intended-head-mode")
        if context is not None and direct_retry:
            trial_context["epoch_intent"] = {
                "digest": event.get("digest"),
                "generation_digest": event.get("generation_digest"),
                "push_consumed": False,
            }
        if context is not None and retry_push_intent:
            trial_context["push_intent"] = {
                "digest": event.get("digest"),
                "generation_digest": event.get("generation_digest"),
                "evidence": copy.deepcopy(current_intent),
                "admitted_active": True,
            }
        if context is not None and epoch_fetch_observation:
            trial_context["epoch_fetch_observation"] = {
                "digest": event.get("digest"),
                "generation_digest": event.get("generation_digest"),
                "evidence": copy.deepcopy(current_intent),
            }
        if (
            context is not None
            and ancestry_result_transition
            and isinstance(current_intent, Mapping)
        ):
            trial_context["epoch_ancestry_observation"] = {
                "digest": event.get("digest"),
                "generation_digest": event.get("generation_digest"),
                "evidence": copy.deepcopy(current_intent),
            }
        if invalid_final_mode_park:
            trial_context.pop("epoch_intent", None)
        if gate_tuple_reclassified:
            trial_context.pop("epoch_intent", None)
    if context is not None and event_name == "push_intent":
        trial_context.pop("push_retry_observation", None)
    elif context is not None and event_name == "push_observed":
        trial_context.pop("remote_observation", None)
        accepted_integration = current.get("integration")
        accepted_intent = (
            accepted_integration.get("intent")
            if isinstance(accepted_integration, Mapping)
            else None
        )
        accepted_observed = (
            accepted_integration.get("observed")
            if isinstance(accepted_integration, Mapping)
            else None
        )
        if (
            isinstance(accepted_intent, Mapping)
            and accepted_intent.get("phase") == "post-push"
            and isinstance(accepted_observed, Mapping)
        ):
            previous_observation = trial_context.get("push_retry_observation")
            previous_evidence = None
            if (
                isinstance(previous_observation, Mapping)
                and previous_observation.get("push_intent_digest")
                == accepted_intent.get("push_intent_digest")
            ):
                previous_evidence = {
                    name: previous_observation.get(name)
                    for name in (
                        "digest",
                        "push_intent_digest",
                        "inflight_digest",
                        "old_tip_all_false",
                    )
                }
            trial_context["push_retry_observation"] = {
                "digest": event.get("digest"),
                "generation_digest": event.get("generation_digest"),
                "push_intent_digest": accepted_intent.get("push_intent_digest"),
                "inflight_digest": accepted_observed.get("inflight_digest"),
                "old_tip_all_false": _merge_old_tip_all_false(current),
                "previous": previous_evidence,
            }
    if context is not None and epoch_fetch_intent_digest is not None:
        for name in (
            "epoch_fetch_observation",
            "candidate_observation_active",
            "candidate_observation",
            "epoch_ancestry_observation",
            "recovery_proof_bridge",
        ):
            trial_context.pop(name, None)
    if context is not None:
        context.clear()
        context.update(trial_context)
    return True


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
    chains_root = _chain_storage_root(repository)
    chains_descriptor: int | None = None
    try:
        chains_descriptor, chains_observation = journal._open_bound_directory(
            chains_root
        )
        replayed = builders._resolve_binding_from_descriptor(
            repository,
            chains_descriptor,
            chain_id,
            "0" * 64,
            expected_type=None,
            expected_fields=None,
            expected_run_id=None,
            expected_task_id=None,
            replay_only=True,
            allow_pending=True,
        )
        binding = replayed.get("run_binding")
        pending = replayed.get("journal_outbox")
        if (
            not isinstance(binding, dict)
            or binding.get("run_id") != authority["run_id"]
            or binding.get("task_id") != authority["task_id"]
            or binding.get("repository") != str(repository)
            or not isinstance(pending, dict)
            or pending.get("source_event_digest")
            != authority["source_event_digest"]
            or journal._file_observation(os.fstat(chains_descriptor))
            != chains_observation
            or journal._file_observation(os.lstat(chains_root))
            != chains_observation
        ):
            raise journal.CoordinationRefusal(journal.INVALID_JOURNAL_RECORD)
    finally:
        if chains_descriptor is not None:
            os.close(chains_descriptor)

    _canonical_repository, state_root = journal._resolve_repository(
        repository, "journal batch"
    )
    run_dir = state_root / ".codex-orchestrator" / "runs" / str(authority["run_id"])
    active = batch._active_locks().get(os.path.abspath(os.fspath(run_dir)))
    if active is None:
        raise journal.CoordinationRefusal(journal.INVALID_JOURNAL_RECORD)
    journal_exact = batch._optional_exact_named_file(active, "journal.jsonl")
    receipts_exact = batch._optional_exact_named_file(
        active, journal.BATCH_RECEIPTS_NAME
    )
    if journal_exact is None or receipts_exact is None:
        raise journal.CoordinationRefusal(journal.INVALID_JOURNAL_RECORD)
    records = tuple(authority["records"])
    batch_bytes = b"".join(journal._journal_line(record) for record in records)
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


def _ingest_captured_paths(
    repository: Path,
    run_dir: Path,
    inputs: Mapping[str, object],
) -> dict[str, str]:
    """Derive the only citable paths from the request's captured digests."""

    _batch, builders, journal = runtime._coordination_modules()
    names = {
        "state_file": "state.json",
        "events_file": "events.jsonl",
        "outcome_map": "outcome-map.json",
    }
    result: dict[str, str] = {}
    for field, name in names.items():
        digest = inputs.get(f"{field}_sha256")
        if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
        path = run_dir / "captured" / "sha256" / digest / name
        try:
            capture_relative = path.relative_to(run_dir).as_posix()
        except ValueError as exc:
            raise journal.CoordinationRefusal(
                builders.INGEST_PROOF_INVALID
            ) from exc
        if _validated_commitment_path(
            "ingest.captured_package",
            capture_relative,
            repository=repository,
            run_dir=run_dir,
            direct_parent=path.parent,
            require_file=True,
        ) is None or _parsed_run_captured_path(
            capture_relative, run_dir.name
        ) is None:
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
        result[field] = capture_relative
    return result


def _ingest_step_is_current(
    final_state: Mapping[str, Any],
    event_state: Mapping[str, Any],
    details: Mapping[str, Any],
) -> bool:
    step_id = details.get("step_id")
    run_number = details.get("run")
    if (
        not isinstance(step_id, str)
        or step_id
        in {"classification", "fast-eligibility", "fast-finalize-eligibility"}
        or type(run_number) is not int
        or run_number <= 0
    ):
        return False
    final_runs = final_state.get("steps", {}).get(step_id)
    event_runs = event_state.get("steps", {}).get(step_id)
    index = run_number - 1
    if (
        not isinstance(final_runs, list)
        or not isinstance(event_runs, list)
        or index >= len(final_runs)
        or index >= len(event_runs)
        or final_runs[index] != event_runs[index]
        or not isinstance(final_runs[index], dict)
        or final_runs[index].get("candidate")
        != final_state.get("candidate", {}).get("sha256")
    ):
        return False
    current = [
        position
        for position, fact in enumerate(final_runs)
        if isinstance(fact, dict)
        and fact.get("candidate") == final_state.get("candidate", {}).get("sha256")
    ]
    if not current:
        return False
    if step_id == "gate-1":
        active = set(current[-2:])
    elif step_id.startswith("stack:"):
        latest = final_runs[current[-1]]
        batch_id = latest.get("batch_id") if isinstance(latest, dict) else None
        active = {
            position
            for position in current
            if isinstance(final_runs[position], dict)
            and final_runs[position].get("batch_id") == batch_id
        }
    else:
        active = {current[-1]}
    return index in active


def _ingest_secret_scan_is_current(
    final_state: Mapping[str, Any],
    event: dict[str, object],
    prior_state: dict[str, object] | None,
    event_state: dict[str, object],
) -> bool:
    """Select only the exact latest current-candidate secret-scan append."""

    _batch, builders, _journal = runtime._coordination_modules()
    introduced = builders._commit_secret_scan_delta(
        event, prior_state, event_state
    )
    final_steps = final_state.get("steps")
    final_runs = (
        final_steps.get("secret-scan")
        if isinstance(final_steps, Mapping)
        else None
    )
    candidate = final_state.get("candidate")
    candidate_sha = (
        candidate.get("sha256") if isinstance(candidate, Mapping) else None
    )
    if (
        introduced is None
        or not isinstance(final_runs, list)
        or introduced[0] >= len(final_runs)
        or final_runs[introduced[0]] != introduced[1]
        or introduced[1].get("candidate") != candidate_sha
    ):
        return False
    current = [
        index
        for index, fact in enumerate(final_runs)
        if isinstance(fact, Mapping) and fact.get("candidate") == candidate_sha
    ]
    return bool(current and introduced[0] == current[-1])


def _merge_ingest_binding(
    builders: Any,
    state: dict[str, object],
    source_event_digest: str,
    review: dict[str, object] | None,
) -> dict[str, object]:
    candidate = builders._candidate_binding_for_state("merge", state)
    if candidate is None:
        raise ValueError("merge candidate cannot be bound")
    preimage: dict[str, object] = {
        "schema": "forge-gate-binding/1",
        "source_record": {
            "chain_id": state["chain_id"],
            "event_digest": source_event_digest,
        },
        "candidate": candidate,
        "review": copy.deepcopy(review),
    }
    return {
        **preimage,
        "binding_id": sha256_bytes(canonical_bytes(preimage)),
    }


def _prove_ingest_live_chain(
    repository: Path,
    chain_id: str,
    materialized: dict[str, object],
    captured_state: bytes,
    captured_events: bytes,
) -> None:
    """Bind captured bytes to the stable live chain without consuming grammar."""

    _batch, builders, journal = runtime._coordination_modules()
    chains_root = _chain_storage_root(repository)
    descriptor: int | None = None
    try:
        descriptor, observation = journal._open_bound_directory(chains_root)
        with builders._chain_event_lock(
            chains_root,
            chain_id,
            root_descriptor=descriptor,
            root_observation=observation,
        ):
            live_state_bytes = builders._read_regular_bytes_at(
                descriptor, f"{chain_id}.json"
            )
            live_events = builders._read_regular_bytes_at(
                descriptor, f"{chain_id}.events.jsonl"
            )
            try:
                live_state = json.loads(live_state_bytes.decode("utf-8"))
            except (UnicodeError, ValueError, RecursionError) as exc:
                raise journal.CoordinationRefusal(
                    builders.INGEST_PROOF_INVALID
                ) from exc
            if (
                live_state_bytes != captured_state
                or live_events != captured_events
                or live_state != materialized
            ):
                raise journal.CoordinationRefusal(
                    builders.INGEST_PROOF_INVALID
                )
            if (
                journal._file_observation(os.fstat(descriptor))
                != observation
                or journal._file_observation(os.lstat(chains_root))
                != observation
            ):
                raise journal.CoordinationRefusal(
                    builders.INGEST_PROOF_INVALID
                )
    except journal.CoordinationRefusal as exc:
        if str(exc) == builders.INGEST_PROOF_INVALID:
            raise
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID) from exc
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _merge_gate_event_fact(
    prior: Mapping[str, object] | None,
    current: Mapping[str, object],
) -> tuple[str, dict[str, object]] | None:
    """Return the one gate fact introduced by a DM-014 gate event."""

    if prior is None:
        return None
    prior_steps = prior.get("steps")
    current_steps = current.get("steps")
    if not isinstance(prior_steps, Mapping) or not isinstance(
        current_steps, Mapping
    ):
        return None
    changed = {
        name
        for name in set(prior_steps) | set(current_steps)
        if prior_steps.get(name) != current_steps.get(name)
    }
    if len(changed) != 1:
        return None
    step_id = next(iter(changed))
    old_value = prior_steps.get(step_id)
    new_value = current_steps.get(step_id)
    if isinstance(new_value, list):
        old_runs = old_value if isinstance(old_value, list) else []
        if len(new_value) != len(old_runs) + 1 or new_value[:-1] != old_runs:
            return None
        fact = new_value[-1]
    else:
        fact = new_value
    if not isinstance(step_id, str) or not isinstance(fact, dict):
        return None
    return step_id, copy.deepcopy(fact)


def _merge_current_gate_facts(
    step_id: str,
    value: object,
    generation_digest: str,
) -> tuple[dict[str, object], ...] | None:
    """Validate the final current-generation fact(s) for one merge gate."""

    if isinstance(value, dict):
        facts = (value,)
    elif isinstance(value, list) and value and all(
        isinstance(item, dict) for item in value
    ):
        current = [item for item in value if isinstance(item, dict)]
        if step_id.startswith("stack:"):
            latest = current[-1]
            batch_id = latest.get("batch_id")
            cell_count = latest.get("cell_count")
            if (
                not isinstance(batch_id, str)
                or type(cell_count) is not int
                or cell_count <= 0
            ):
                return None
            facts = tuple(
                item for item in current if item.get("batch_id") == batch_id
            )
            if (
                len(facts) != cell_count
                or {item.get("cell_index") for item in facts}
                != set(range(1, cell_count + 1))
            ):
                return None
        else:
            facts = (current[-1],)
    else:
        return None
    expected_prefix = "gate-1: " if step_id == "gate-1" else "gate-2: "
    if any(
        fact.get("result") != "passed"
        or fact.get("generation_digest") != generation_digest
        or not isinstance(fact.get("criterion"), str)
        or not str(fact["criterion"]).startswith(expected_prefix)
        for fact in facts
    ):
        return None
    return tuple(copy.deepcopy(fact) for fact in facts)


def _merge_ingest_record_templates(
    builders: Any,
    journal: Any,
    event: dict[str, object],
    prior: dict[str, object] | None,
    current: dict[str, object],
    *,
    task: str,
    approval_required: bool,
    required_gate_ids: frozenset[str],
) -> tuple[tuple[dict[str, object], str | None], ...]:
    """Derive ordinary records solely from one authenticated merge delta."""

    event_name = event.get("event")
    templates: list[tuple[dict[str, object], str | None]] = []
    if event_name == "gate_recorded":
        introduced = _merge_gate_event_fact(prior, current)
        if introduced is None:
            return ()
        step_id, fact = introduced
        if step_id not in required_gate_ids:
            return ()
        result = fact.get("result")
        criterion = fact.get("criterion")
        if result not in {"passed", "failed"} or not isinstance(
            criterion, str
        ):
            return ()
        argv = fact.get("command_argv")
        transcript = fact.get("transcript")
        templates.append(
            (
                {
                    "type": "verification",
                    "task": task,
                    "criterion": criterion,
                    "method": "Forge CLI merge chain",
                    "check": (
                        " ".join(str(value) for value in argv)
                        if isinstance(argv, list) and argv
                        else step_id
                    ),
                    "result": result,
                    "observation": (
                        f"Forge CLI recorded merge {step_id} result {result}"
                    ),
                    "evidence": (
                        [transcript] if isinstance(transcript, str) else []
                    ),
                },
                step_id,
            )
        )

    if event_name in {"review_attached", "generation_carried_forward"}:
        authority_state = (
            prior
            if event_name == "generation_carried_forward" and prior is not None
            else current
        )
        review = builders._review_binding_for_state(authority_state)
        if (
            isinstance(review, dict)
            and review.get("verdict") in {"PASS", "BLOCK"}
            and review.get("reviewer_role") == "review-final"
        ):
            review_result = (
                "passed" if review["verdict"] == "PASS" else "failed"
            )
            review_state = current.get("review")
            verdict = (
                review_state.get("verdict")
                if isinstance(review_state, dict)
                else None
            )
            verdict_path = (
                verdict.get("verdict_path")
                if isinstance(verdict, dict)
                else None
            )
            templates.append(
                (
                    {
                        "type": "verification",
                        "task": task,
                        "criterion": journal.GATE_3_CRITERION,
                        "method": "independent review-final",
                        "check": "validated merge review-final verdict transport",
                        "result": review_result,
                        "observation": (
                            "Forge CLI recorded merge review-final verdict "
                            f"{review['verdict']}"
                        ),
                        "evidence": (
                            [verdict_path]
                            if isinstance(verdict_path, str)
                            else []
                        ),
                    },
                    None,
                )
            )

    if event_name in {
        "approval_recorded",
        "generation_carried_forward",
    }:
        authority_state = (
            prior
            if event_name == "generation_carried_forward" and prior is not None
            else current
        )
        approval = authority_state.get("approval")
        candidate = authority_state.get("candidate")
        gate4_approval = bool(
            approval_required
            and isinstance(approval, dict)
            and isinstance(candidate, dict)
            and approval.get("purpose") == "gate-4"
            and approval.get("chain_id") == authority_state.get("chain_id")
            and approval.get("candidate") == candidate.get("candidate_head")
            and approval.get("generation_digest")
            == candidate.get("generation_digest")
        )
        churn_approval = bool(
            isinstance(approval, dict)
            and approval.get("purpose") == "remote-churn"
            and _merge_current_authority_valid(authority_state)
        )
        if gate4_approval or churn_approval:
            templates.append(
                (
                    {
                        "type": "decision",
                        "task": task,
                        "resolution": (
                            "Forge merge chain Gate-4 approval recorded"
                            if gate4_approval
                            else "Forge merge chain remote-churn acknowledgement recorded"
                        ),
                        "outcome": "chain-approval",
                        "basis": [],
                    },
                    None,
                )
            )

    if event_name == "push_observed":
        integration = current.get("integration")
        push = (
            integration.get("push")
            if isinstance(integration, dict)
            else None
        )
        landed = push.get("landed_head") if isinstance(push, dict) else None
        if (
            isinstance(landed, str)
            and isinstance(prior, dict)
            and prior.get("state") != "pushed"
            and current.get("state") == "pushed"
            and builders._merge_current_head_contained(current)
        ):
            templates.append(
                (
                    {
                        "type": "decision",
                        "task": task,
                        "resolution": (
                            f"Forge merge chain landing recorded: {landed}"
                        ),
                        "outcome": "chain-landing",
                        "basis": [],
                    },
                    None,
                )
            )
    return tuple(templates)


def _verify_and_build_merge_ingest_records(
    *,
    canonical_repository: Path,
    run_id: str,
    run_dir: Path,
    inputs: dict[str, object],
    materialized: dict[str, object],
    outcome_map: object,
    events: Sequence[
        tuple[
            dict[str, object],
            dict[str, object] | None,
            dict[str, object],
        ]
    ],
    existing_records: tuple[dict[str, object], ...] | None,
    base_records: list[dict[str, object]] | None,
    captured_state: bytes,
    captured_events: bytes,
    completed_proofs: list[str],
) -> tuple[Sequence[dict[str, object]], tuple[str, ...]]:
    """Prove a closed DM-014 landing and synthesize its ordinary journal rows."""

    _batch, builders, journal = runtime._coordination_modules()

    # Proof 3: the terminal, previously unbound merge chain belongs to the
    # repository selected by the caller.
    _require_ingest_proof("repository", completed_proofs)
    candidate = materialized.get("candidate")
    worktree = materialized.get("worktree")
    integration = materialized.get("integration")
    cleanup = materialized.get("cleanup")
    policy_source = materialized.get("policy_source")
    tier = materialized.get("tier")
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
        materialized.get("schema") != "forge-merge-chain/1"
        or materialized.get("kind") != "merge"
        or materialized.get("state") != "closed"
        or materialized.get("run") is not None
        or materialized.get("run_binding") is not None
        or materialized.get("journal_outbox") is not None
        or materialized.get("repository") != str(canonical_repository)
        or not isinstance(candidate, dict)
        or opening_repository != canonical_repository
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    # Proof 4: the final generation names exact committed policy bytes.
    # ``policy_source``'s inner field names were not fixed by DM-014, so require
    # it to carry both normative values rather than accepting guessed aliases.
    _require_ingest_proof("policy", completed_proofs)
    if (
        not isinstance(policy_source, dict)
        or candidate.get("policy_digest") not in policy_source.values()
        or candidate.get("policy_commit") not in policy_source.values()
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    policy = subprocess.run(
        [
            "git",
            "-C",
            str(canonical_repository),
            "show",
            f"{candidate['policy_commit']}:forge-project.md",
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if (
        policy.returncode != 0
        or sha256_bytes(policy.stdout) != candidate.get("policy_digest")
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    try:
        parsed_policy = parse_policy(str(candidate["policy_commit"]), policy.stdout)
    except (KeyError, PolicyError, UnicodeError) as exc:
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID) from exc

    # Proof 5: the generation is well formed and is still the exact live chain
    # materialization under task-03's native event lock.
    _require_ingest_proof("generation", completed_proofs)
    generation = builders._merge_generation(candidate)
    if generation is None:
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    generation_digest = str(candidate["generation_digest"])
    candidate_head = str(candidate["candidate_head"])
    remote_tip = str(candidate["remote_tip"])
    _prove_ingest_live_chain(
        canonical_repository,
        str(materialized["chain_id"]),
        materialized,
        captured_state,
        captured_events,
    )

    # Proof 6: every gate required by the final policy/tier is present, passing,
    # and bound to the current generation.
    _require_ingest_proof("current-gates", completed_proofs)
    if (
        not isinstance(tier, dict)
        or type(tier.get("control")) is not bool
        or not isinstance(tier.get("categories"), list)
        or not all(
            isinstance(category, str) and category
            for category in tier["categories"]
        )
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    required_gate_ids = {
        "gate-1",
        "assertion-sensor",
        *(
            f"stack:{category}"
            for category in sorted(set(str(value) for value in tier["categories"]))
        ),
        *(
            f"invariant:{invariant['row_number']}"
            for invariant in parsed_policy.invariants
            if invariant["enforcement"] == "merge"
        ),
    }
    steps = materialized.get("steps")
    if not isinstance(steps, dict) or any(
        _merge_current_gate_facts(
            gate_id, steps.get(gate_id), generation_digest
        )
        is None
        for gate_id in required_gate_ids
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    # Proofs 7–10: re-open the exact package, then bind role, iteration, and
    # verdict independently in the normative order.
    review = materialized.get("review")
    review_binding = builders._review_binding_for_state(materialized)
    request = review.get("request") if isinstance(review, dict) else None
    verdict = review.get("verdict") if isinstance(review, dict) else None

    _require_ingest_proof("review-package", completed_proofs)
    if (
        not isinstance(review, dict)
        or not isinstance(review_binding, dict)
        or not isinstance(request, dict)
        or not isinstance(verdict, dict)
        or request.get("candidate") != candidate_head
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
    if (
        review_binding.get("reviewer_role") != "review-final"
        or request.get("reviewer") != "review-final"
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    _require_ingest_proof("reviewer-iteration", completed_proofs)
    if (
        type(review.get("iteration")) is not int
        or int(review["iteration"]) <= 0
        or request.get("iteration") != review.get("iteration")
        or review_binding.get("iteration") != review.get("iteration")
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    _require_ingest_proof("reviewer-verdict", completed_proofs)
    if (
        review_binding.get("verdict") != "PASS"
        or verdict.get("verdict") != "PASS"
        or verdict.get("candidate") != candidate_head
        or verdict.get("package_digest") != request.get("package_digest")
        or review_binding.get("package_digest") != request.get("package_digest")
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    # Proof 11: a control generation requires authenticated operator authority.
    # An exact remote-churn acknowledgement is the current authority only after
    # replay has proved the retained Gate-4/review tuple that it re-armed.
    _require_ingest_proof("operator-approval", completed_proofs)
    approval = materialized.get("approval")
    approval_required = bool(
        tier["control"]
        or isinstance(approval, Mapping)
        and approval.get("purpose") == "remote-churn"
    )
    if approval_required and not _merge_current_authority_valid(materialized):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    # Proof 12: recompute the exact DM-014 range and prove the durable remote
    # landing observation.  Closing-HEAD containment remains a separate proof.
    _require_ingest_proof("landing-proof", completed_proofs)
    if (
        not isinstance(worktree, dict)
        or set(worktree) != {"path", "git_dir", "common_dir", "claim"}
        or not isinstance(worktree.get("claim"), dict)
        or set(worktree["claim"]) != {"status", "path", "inode", "digest"}
        or worktree["claim"].get("status") != "released"
        or not isinstance(integration, dict)
        or set(integration)
        != {
            "condition",
            "primary_condition",
            "epoch",
            "remote_movement_count",
            "intent",
            "observed",
            "pre_rebase",
            "conflict",
            "push",
        }
        or integration.get("condition") != "none"
        or integration.get("primary_condition") != "none"
        or not isinstance(cleanup, dict)
        or cleanup.get("condition") != "none"
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    diff = subprocess.run(
        [
            "git",
            "-C",
            str(canonical_repository),
            "diff",
            f"{remote_tip}...{candidate_head}",
        ],
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
            f"{remote_tip}...{candidate_head}",
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if (
        diff.returncode != 0
        or names.returncode != 0
        or sha256_bytes(diff.stdout) != candidate.get("diff_sha256")
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    try:
        changed_paths = tuple(
            item.decode("utf-8") for item in names.stdout.split(b"\0") if item
        )
    except UnicodeDecodeError as exc:
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID) from exc
    if not changed_paths or not all(
        journal._valid_scope_item(path) for path in changed_paths
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    push = integration.get("push")
    observed = integration.get("observed")
    if (
        not isinstance(push, dict)
        or set(push)
        != {
            "expected_old_tip",
            "intended_head",
            "destination_ref",
            "intended_at",
            "result",
            "attempted_heads",
            "landed_head",
        }
        or push.get("intended_head") != candidate_head
        or push.get("destination_ref") != candidate.get("destination_ref")
        or push.get("landed_head") != candidate_head
        or not isinstance(push.get("attempted_heads"), list)
        or not push["attempted_heads"]
        or push["attempted_heads"][-1] != candidate_head
        or not all(
            isinstance(head, str) and COMMIT_RE.fullmatch(head) is not None
            for head in push["attempted_heads"]
        )
        or not isinstance(observed, dict)
        or set(observed)
        != {
            "exists",
            "oid",
            "contains_intended_head",
            "attempted_head_containment",
            "observed_at",
            "inflight_digest",
            "output_digest",
        }
        or observed.get("exists") is not True
        or observed.get("contains_intended_head") is not True
        or not isinstance(observed.get("oid"), str)
        or COMMIT_RE.fullmatch(str(observed["oid"])) is None
        or not isinstance(observed.get("attempted_head_containment"), list)
        or len(observed["attempted_head_containment"])
        != len(push["attempted_heads"])
        or any(
            not isinstance(entry, dict)
            or set(entry) != {"head", "contained"}
            or entry.get("head") != head
            or type(entry.get("contained")) is not bool
            for entry, head in zip(
                observed["attempted_head_containment"],
                push["attempted_heads"],
            )
        )
        or observed["attempted_head_containment"][-1].get("contained") is not True
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    remote_contains = subprocess.run(
        [
            "git",
            "-C",
            str(canonical_repository),
            "merge-base",
            "--is-ancestor",
            candidate_head,
            str(observed["oid"]),
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if remote_contains.returncode != 0:
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    # Proof 13: every DM-014 transition is monotonic.  This is intentionally
    # deferred until after the landing proof instead of being conflated with
    # digest replay.
    _require_ingest_proof("monotonic-transitions", completed_proofs)
    merge_context: dict[str, object] = {}
    merge_history: list[dict[str, Any]] = []
    for event, prior_state, event_state in events:
        if not _merge_ingest_transition_valid(
            builders,
            event,
            prior_state,
            event_state,
            context=merge_context,
            history=tuple(merge_history),
        ):
            raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
        merge_history.append(copy.deepcopy(event))

    # Proof 14: the landed head is contained by the caller's proposed closing
    # HEAD, independently of the durable remote observation above.
    _require_ingest_proof("closing-head-containment", completed_proofs)
    closing_head = inputs.get("closing_head")
    if (
        not isinstance(closing_head, str)
        or COMMIT_RE.fullmatch(closing_head) is None
    ):
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)
    closing_contains = subprocess.run(
        [
            "git",
            "-C",
            str(canonical_repository),
            "merge-base",
            "--is-ancestor",
            candidate_head,
            closing_head,
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if closing_contains.returncode != 0:
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    # Proof 15: the explicit task belongs to this run/repository and remains
    # active until this one terminal batch is appended.
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
        or outcome_map.get("chain_id") != materialized.get("chain_id")
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

    # Proof 16: every changed path is admitted by both task and run scope.
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
        if not any(
            isinstance(pattern, str)
            and journal.pathspec_contained(path, pattern)
            for pattern in files
        ) or not any(
            journal.pathspec_contained(path, admitted)
            for admitted in run_state.scope
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

    replay_entries = tuple(
        (event, prior, event_state, (), str(event["digest"]))
        for event, prior, event_state in events
    )
    projected = list(proof_records)
    records: list[dict[str, object]] = []
    selected_digests: list[str] = []
    covered_gates: set[str] = set()
    captured = _ingest_captured_paths(
        canonical_repository, run_dir, inputs
    )
    captured_citations = [
        captured["state_file"],
        captured["events_file"],
        captured["outcome_map"],
    ]
    gate3_count = 0
    approval_count = 0
    landing_count = 0
    for event, prior, event_state in events:
        accepted_event = False
        templates = _merge_ingest_record_templates(
            builders,
            journal,
            event,
            prior,
            event_state,
            task=task,
            approval_required=approval_required,
            required_gate_ids=frozenset(required_gate_ids),
        )
        for template, gate_id in templates:
            record = copy.deepcopy(template)
            record_type = str(record["type"])
            record["id"] = builders._allocate_id(projected, record_type)
            record["run_id"] = run_id
            record["recorded_at"] = event["at"]
            review_for_binding = (
                review_binding
                if record.get("criterion") == journal.GATE_3_CRITERION
                else None
            )
            record["binding"] = _merge_ingest_binding(
                builders,
                event_state,
                str(event["digest"]),
                review_for_binding,
            )
            _capture_ingest_record_evidence(
                canonical_repository,
                run_dir,
                record,
            )
            if record.get("outcome") == "chain-landing":
                record["basis"] = list(captured_citations)
            binding = record["binding"]
            assert isinstance(binding, dict)
            if not builders._binding_matches_source_fact(
                binding,
                record,
                event,
                prior,
                event_state,
                family="merge",
            ) or not builders._binding_is_current(
                materialized,
                binding,
                record,
                event,
                prior,
                event_state,
                replay_entries,
                chain_family="merge",
            ):
                continue
            accepted_event = True
            if gate_id is not None:
                covered_gates.add(gate_id)
            if record.get("criterion") == journal.GATE_3_CRITERION:
                gate3_count += 1
            if record.get("outcome") == "chain-approval":
                approval_count += 1
            if record.get("outcome") == "chain-landing":
                landing_count += 1
            records.append(record)
            projected.append(record)
        if accepted_event:
            selected_digests.append(str(event["digest"]))

    if (
        selected_digests != outcome_map["event_digests"]
        or covered_gates != required_gate_ids
        or gate3_count != 1
        or landing_count != 1
        or approval_count != (1 if approval_required else 0)
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
        "recorded_at": events[-1][0]["at"],
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
        not builders._commit_transition_valid(event, prior_state, event_state)
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
        elif event_name in {"commit_produced", "commit_close_recovered"}:
            active = details.get("commit_sha") == commit_sha
        if active and event_state.get("candidate", {}).get("sha256") == final_candidate:
            selected.append((event, prior_state, event_state))
    selected_digests = [
        str(event["digest"]) for event, _prior, _state in selected
    ]
    if selected_digests != outcome_map["event_digests"]:
        raise journal.CoordinationRefusal(builders.INGEST_PROOF_INVALID)

    projected = list(proof_records)
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
                or not builders._binding_matches_source_fact(
                    record_binding,
                    record,
                    event,
                    prior_state,
                    event_state,
                    family="commit",
                )
                or not builders._binding_is_current(
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


def register_coordination_seams() -> None:
    """Idempotently install task-04 authority in the shared task-03 modules."""

    batch, builders, _journal = runtime._coordination_modules()
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
for _seam in (reduce_merge_event, _authorize_chain_batch, _ingest_proof_verifier):
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


def iso_z(value: dt.datetime | None = None) -> str:
    current = value or runtime.utc_now()
    current = current.astimezone(dt.timezone.utc).replace(microsecond=0)
    return current.isoformat().replace("+00:00", "Z")


def parse_time(value: str) -> dt.datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("timestamp is not UTC Z form")
    parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.tzinfo is None:
        raise ValueError("timestamp lacks timezone")
    return parsed.astimezone(dt.timezone.utc)


class Repository:
    def __init__(self, root: Path) -> None:
        self.root = Path(os.path.realpath(root))

    @classmethod
    def discover(cls, explicit: str | None = None) -> "Repository":
        cwd = Path(explicit).resolve() if explicit else Path.cwd()
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            raise FrozenError(
                "cannot resolve Git worktree while attempting Forge CLI command",
                observed=result.stderr.decode("utf-8", "replace").strip() or "not a repository",
            )
        return cls(Path(os.fsdecode(result.stdout.rstrip(b"\n"))))

    def git(
        self,
        args: Sequence[str],
        *,
        input_bytes: bytes | None = None,
        check: bool = True,
        env: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        result = subprocess.run(
            ["git", *args],
            cwd=str(self.root),
            input=input_bytes,
            stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=dict(env) if env is not None else None,
            check=False,
        )
        if check and result.returncode != 0:
            detail = result.stderr.decode("utf-8", "replace").strip()
            raise OSError(f"git {' '.join(args)} failed: {detail}")
        return result

    def head(self) -> str:
        value = self.git(["rev-parse", "HEAD"]).stdout.decode("ascii").strip()
        if not COMMIT_RE.fullmatch(value):
            raise OSError("Git returned a malformed HEAD")
        return value

    def common_root(self) -> Path:
        runtime._coordination_modules()
        from codex_orchestrator.chain_paths import common_worktree_root

        return common_worktree_root(self.root)

    def git_common_dir(self) -> Path:
        """Resolve the canonical Git common directory for portable locking."""

        for arguments, require_absolute in (
            (["rev-parse", "--path-format=absolute", "--git-common-dir"], True),
            (["rev-parse", "--git-common-dir"], False),
        ):
            result = self.git(arguments, check=False)
            rendered = os.fsdecode(result.stdout.rstrip(b"\n"))
            if (
                result.returncode != 0
                or not rendered
                or "\n" in rendered
                or "\r" in rendered
            ):
                continue
            candidate = Path(rendered)
            if require_absolute and not candidate.is_absolute():
                continue
            if not candidate.is_absolute():
                candidate = self.root / candidate
            try:
                canonical = candidate.resolve(strict=True)
            except OSError:
                continue
            if canonical.is_dir():
                return canonical
        raise FrozenError(
            "Git common directory is unavailable for portable locking",
            observed=str(self.root),
            schema=REVISION9_OUTPUT_SCHEMA,
        )

    def policy(self, sha: str | None = None) -> tuple[str, bytes]:
        resolved = sha or self.head()
        result = self.git(["show", f"{resolved}:forge-project.md"], check=False)
        if result.returncode != 0:
            raise OSError(
                result.stderr.decode("utf-8", "replace").strip()
                or "committed forge-project.md is unavailable"
            )
        return resolved, result.stdout

    def candidate_bytes(self) -> bytes:
        # DM-012 binds candidate identity to this command's exact stdout.
        return self.git(["diff", "--cached"]).stdout

    def candidate_hash(self) -> str:
        return sha256_bytes(self.candidate_bytes())

    def staged_paths(self) -> list[str]:
        raw = self.git(
            ["diff", "--cached", "--name-only", "-z", "--diff-filter=ACDMRTUXB"]
        ).stdout
        return [os.fsdecode(item) for item in raw.split(b"\0") if item]

    def commit_message_argument_digest(self, commit_sha: str) -> str:
        """Return the digest of the exact message body in a commit object."""
        result = self.git(["cat-file", "commit", commit_sha], check=False)
        if result.returncode != 0 or b"\n\n" not in result.stdout:
            return ""
        message = result.stdout.split(b"\n\n", 1)[1]
        return sha256_bytes(message)

    def tree_index_drift(self, paths: Sequence[str]) -> list[str]:
        if not paths:
            return []
        result = self.git(["diff", "--name-only", "-z", "--", *paths])
        return [os.fsdecode(item) for item in result.stdout.split(b"\0") if item]

    def normalize_paths(self, values: Sequence[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            candidate = Path(value)
            absolute = candidate if candidate.is_absolute() else self.root / candidate
            resolved_parent = Path(os.path.realpath(absolute.parent))
            resolved = resolved_parent / absolute.name
            try:
                relative = resolved.relative_to(self.root)
            except ValueError:
                raise Refusal(
                    ReasonCode.PATH_MISSING,
                    f"named path is outside the repository: {value}",
                    observed=value,
                    remediation="forge commit start --paths <repository-relative-path>...",
                )
            label = relative.as_posix()
            tracked = self.git(["ls-files", "--error-unmatch", "--", label], check=False)
            if not resolved.exists() and tracked.returncode != 0:
                raise Refusal(
                    ReasonCode.PATH_MISSING,
                    f"named path does not exist: {label}",
                    observed=label,
                    remediation=f"create {label} or remove it from --paths",
                )
            if label not in normalized:
                normalized.append(label)
        return normalized


def _committed_changelog_output_paths(policy: Policy) -> frozenset[str]:
    """Return only exact outputs from an already authenticated policy snapshot."""

    if policy.changelog is None:
        return frozenset()
    outputs = policy.changelog.get("outputs")
    if not isinstance(outputs, list) or not outputs or not all(
        isinstance(item, str) and item for item in outputs
    ):
        raise PolicyError("configured changelog gate has malformed output paths")
    return frozenset(outputs)


def validate_state(state: Any, chain_id: str | None = None) -> dict[str, Any]:
    if runtime.REVISION9_STATE_CONTROLS != runtime._REQUIRED_REVISION9_STATE_CONTROLS:
        raise FrozenError(
            "Revision-9 chain-state validation control is unavailable",
            chain_id=chain_id,
        )
    if isinstance(state, dict) and set(state) == STATE_KEYS - {
        "run_binding",
        "journal_outbox",
    }:
        # A pre-Revision-9 chain file lacks the two added keys; absence reads
        # as null (unbound / drained), which is exactly what a legacy chain
        # is. Every new write includes both keys explicitly.
        state["run_binding"] = None
        state["journal_outbox"] = None
    if not isinstance(state, dict) or set(state) != STATE_KEYS:
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
    candidate = state["candidate"].get("sha256")
    if candidate is not None and not SHA256_RE.fullmatch(str(candidate)):
        raise FrozenError("chain candidate digest is malformed", chain_id=actual_id)
    archive = state["staging"].get("archive")
    if archive is not None:
        archive_keys = {
            "run_id",
            "path",
            "closing_head",
            "legacy_recovered_head",
            "legacy_approval",
            "post_close_validation",
            "dispense_targets",
            "dispense_reason",
            "rendered_sha256",
        }
        normal = bool(
            isinstance(archive, dict)
            and isinstance(archive.get("closing_head"), str)
            and COMMIT_RE.fullmatch(str(archive["closing_head"])) is not None
            and archive.get("legacy_recovered_head") is None
            and archive.get("legacy_approval") is None
        )
        legacy = bool(
            isinstance(archive, dict)
            and archive.get("closing_head") is None
            and isinstance(archive.get("legacy_recovered_head"), str)
            and COMMIT_RE.fullmatch(str(archive["legacy_recovered_head"]))
            is not None
            and isinstance(archive.get("legacy_approval"), str)
            and archive["legacy_approval"]
        )
        if (
            not isinstance(archive, dict)
            or set(archive) != archive_keys
            or not isinstance(archive.get("run_id"), str)
            or RUN_ID_RE.fullmatch(str(archive["run_id"])) is None
            or archive.get("path")
            != f".forge/history/runs/{archive.get('run_id')}.md"
            or normal is legacy
            or not isinstance(archive.get("post_close_validation"), str)
            or not Path(str(archive["post_close_validation"])).is_absolute()
            or not isinstance(archive.get("dispense_targets"), list)
            or not all(
                isinstance(value, str) and value
                for value in archive["dispense_targets"]
            )
            or archive.get("dispense_reason") is not None
            and not isinstance(archive.get("dispense_reason"), str)
            or bool(archive.get("dispense_targets"))
            != bool(archive.get("dispense_reason"))
            or not isinstance(archive.get("rendered_sha256"), str)
            or SHA256_RE.fullmatch(str(archive["rendered_sha256"])) is None
            or state.get("run_binding") is not None
            or state.get("paths") != [archive.get("path")]
        ):
            raise FrozenError("chain archive metadata is malformed", chain_id=actual_id)
    run_binding = state.get("run_binding")
    if run_binding is not None:
        if (
            not isinstance(run_binding, dict)
            or set(run_binding)
            != {"run_id", "task_id", "repository", "policy_digest"}
            or not isinstance(run_binding.get("run_id"), str)
            or not RUN_ID_RE.fullmatch(str(run_binding["run_id"]))
            or not isinstance(run_binding.get("task_id"), str)
            or not run_binding["task_id"]
            or not isinstance(run_binding.get("repository"), str)
            or not Path(str(run_binding["repository"])).is_absolute()
            or run_binding.get("repository")
            != state["staging"].get("worktree_root")
            or not isinstance(run_binding.get("policy_digest"), str)
            or SHA256_RE.fullmatch(str(run_binding["policy_digest"])) is None
            or run_binding.get("policy_digest")
            != state["policy_source"].get("digest")
        ):
            raise FrozenError("chain run binding is malformed", chain_id=actual_id)
    journal_outbox = state.get("journal_outbox")
    if journal_outbox is not None:
        if (
            not isinstance(journal_outbox, dict)
            or set(journal_outbox)
            != {
                "idempotency_key",
                "batch_digest",
                "record_count",
                "source_event_digest",
            }
            or not isinstance(journal_outbox.get("idempotency_key"), str)
            or SHA256_RE.fullmatch(str(journal_outbox["idempotency_key"])) is None
            or not isinstance(journal_outbox.get("batch_digest"), str)
            or SHA256_RE.fullmatch(str(journal_outbox["batch_digest"])) is None
            or type(journal_outbox.get("record_count")) is not int
            or int(journal_outbox["record_count"]) <= 0
            or journal_outbox.get("source_event_digest")
            != journal_outbox.get("idempotency_key")
        ):
            raise FrozenError("chain journal outbox is malformed", chain_id=actual_id)
    return state


def _require_merge_store_control(name: str) -> None:
    if (
        name not in _REQUIRED_MERGE_STORE_CONTROLS
        or name not in MERGE_STORE_CONTROLS
    ):
        raise FrozenError(
            f"merge storage control is unavailable: {name}",
            schema=REVISION9_OUTPUT_SCHEMA,
        )


def _require_merge_adapter_control(name: str) -> None:
    if (
        name not in _REQUIRED_MERGE_ADAPTER_CONTROLS
        or name not in MERGE_ADAPTER_CONTROLS
    ):
        raise FrozenError(
            f"merge adapter control is unavailable: {name}",
            schema=REVISION9_OUTPUT_SCHEMA,
        )


def _require_merge_integration_control(name: str) -> None:
    if (
        name not in _REQUIRED_MERGE_INTEGRATION_CONTROLS
        or name not in MERGE_INTEGRATION_CONTROLS
    ):
        raise FrozenError(
            f"merge integration control is unavailable: {name}",
            schema=REVISION9_OUTPUT_SCHEMA,
        )


def validate_merge_state(
    state: Any, chain_id: str | None = None
) -> dict[str, Any]:
    """Validate the separate 24-key DM-014 materialized projection."""

    _require_merge_store_control("separate-merge-grammar")
    if not isinstance(state, dict) or set(state) != MERGE_STATE_KEYS:
        raise FrozenError(
            "materialized merge state has an invalid top-level key set",
            chain_id=chain_id,
            observed=(
                ",".join(sorted(state))
                if isinstance(state, dict)
                else type(state).__name__
            ),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    actual_id = state.get("chain_id")
    if not isinstance(actual_id, str) or CHAIN_ID_RE.fullmatch(actual_id) is None:
        raise FrozenError(
            "merge state has an invalid chain_id",
            chain_id=chain_id,
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    if chain_id is not None and actual_id != chain_id:
        raise FrozenError(
            "merge filename and payload identity diverge",
            chain_id=chain_id,
            observed=str(actual_id),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    _batch, builders, _journal = runtime._coordination_modules()
    if (
        MERGE_STATE_KEYS != builders._MERGE_STATE_KEYS
        or MERGE_EVENT_NAMES != builders._MERGE_EVENT_NAMES
        or not _merge_state_shape_valid(builders, state, actual_id)
    ):
        raise FrozenError(
            "materialized merge state is invalid",
            chain_id=actual_id,
            state=str(state.get("state")),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    return state


@dataclasses.dataclass(frozen=True)
class MergeReplayResult:
    """Authenticated DM-014 replay before materialized-state comparison."""

    state: dict[str, Any]
    events: tuple[dict[str, Any], ...]
    entries: tuple[
        tuple[
            dict[str, Any],
            dict[str, Any] | None,
            dict[str, Any],
            tuple[dict[str, Any], ...],
            str | None,
        ],
        ...,
    ]
    prefix_state_bytes: tuple[bytes, ...]
    context: dict[str, Any]
    raw_events: bytes
    tail_sequence: int
    tail_digest: str


def _replay_merge_event_bytes(
    chain_id: str,
    raw_events: bytes,
    *,
    verify_receipts: bool = True,
) -> MergeReplayResult:
    """Replay DM-014 by composing the registered reducer and builder grammar."""

    _require_merge_store_control("separate-merge-grammar")
    if not raw_events or not raw_events.endswith(b"\n"):
        raise FrozenError(
            "merge event log is empty or has a partial final record",
            chain_id=chain_id,
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    _batch, builders, _journal = runtime._coordination_modules()
    if (
        MERGE_STATE_KEYS != builders._MERGE_STATE_KEYS
        or MERGE_EVENT_NAMES != builders._MERGE_EVENT_NAMES
    ):
        raise FrozenError(
            "merge grammar authority is unavailable",
            chain_id=chain_id,
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    previous_digest = ZERO_DIGEST
    replayed: dict[str, Any] | None = None
    events: list[dict[str, Any]] = []
    entries: list[
        tuple[
            dict[str, Any],
            dict[str, Any] | None,
            dict[str, Any],
            tuple[dict[str, Any], ...],
            str | None,
        ]
    ] = []
    prefix_state_bytes: list[bytes] = []
    context: dict[str, Any] = {}
    pending_outbox: dict[str, Any] | None = None
    pending_records: tuple[dict[str, Any], ...] = ()
    for sequence, raw in enumerate(raw_events.splitlines(keepends=True), 1):
        try:
            event = json.loads(raw.decode("utf-8"))
        except (UnicodeError, ValueError, RecursionError) as exc:
            raise FrozenError(
                f"merge event {sequence} is malformed",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            ) from exc
        if (
            not isinstance(event, dict)
            or set(event) != MERGE_EVENT_KEYS
            or event.get("schema") != "forge-merge-event/1"
            or event.get("chain_id") != chain_id
            or event.get("sequence") != sequence
            or event.get("previous_digest") != previous_digest
            or event.get("event") not in MERGE_EVENT_NAMES
            or builders._utc_value(event.get("at")) is None
        ):
            raise FrozenError(
                f"merge event {sequence} has an invalid identity or key set",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        if raw != canonical_bytes(event) + b"\n":
            raise FrozenError(
                f"merge event {sequence} is not canonical",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        projection = {name: event[name] for name in event if name != "digest"}
        digest = event.get("digest")
        if (
            not isinstance(digest, str)
            or SHA256_RE.fullmatch(digest) is None
            or digest != sha256_bytes(canonical_bytes(projection))
        ):
            raise FrozenError(
                f"merge event {sequence} digest is invalid",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        prior = copy.deepcopy(replayed)
        try:
            records, event_outbox, source_digest = builders._event_batch_records(
                event, "merge"
            )
            event_name = event.get("event")
            is_receipt = event_name == "journal_receipted"
            if pending_outbox is not None and not is_receipt:
                raise ValueError("pending merge outbox was bypassed")
            if pending_outbox is None and is_receipt:
                raise ValueError("merge receipt has no pending outbox")
            receipt = (
                builders._receipt_metadata(event, "merge")
                if is_receipt
                else None
            )
            if is_receipt:
                if (
                    receipt is None
                    or records
                    or event_outbox is not None
                    or source_digest is not None
                    or receipt.get("idempotency_key")
                    != pending_outbox.get("idempotency_key")
                    or receipt.get("batch_digest")
                    != pending_outbox.get("batch_digest")
                    or replayed is None
                ):
                    raise ValueError("merge receipt identity is invalid")
                if verify_receipts:
                    builders._verify_receipted_batch(
                        Path(str(replayed["repository"])),
                        chain_id,
                        replayed,
                        pending_outbox,
                        pending_records,
                        receipt,
                    )
            elif event_outbox is not None and pending_outbox is not None:
                raise ValueError("merge event introduced a second pending outbox")

            current = reduce_merge_event(prior, copy.deepcopy(event))
        except (
            KeyError,
            OSError,
            TypeError,
            ValueError,
            RuntimeError,
            _journal.CoordinationRefusal,
        ) as exc:
            raise FrozenError(
                f"merge event {sequence} payload is invalid",
                chain_id=chain_id,
                observed=str(exc),
                schema=REVISION9_OUTPUT_SCHEMA,
            ) from exc
        additive_history = _merge_history_uses_additive_grammar((*events, event))
        state_shape_valid = (
            _merge_state_shape_valid(builders, current, chain_id)
            if additive_history
            else builders._state_shape_valid(current, chain_id, "merge")
        )
        if not state_shape_valid or not (
            _merge_ingest_transition_valid(
                builders,
                event,
                prior,
                current,
                context=context,
                history=tuple(events),
            )
        ):
            raise FrozenError(
                f"merge event {sequence} transition is invalid",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        if is_receipt:
            if current.get("journal_outbox") is not None or prior is None:
                raise FrozenError(
                    f"merge event {sequence} receipt did not clear its outbox",
                    chain_id=chain_id,
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            ignored = {"last_event_at", "inactive_after", "journal_outbox"}
            if any(
                prior.get(name) != current.get(name)
                for name in MERGE_STATE_KEYS - ignored
            ):
                raise FrozenError(
                    f"merge event {sequence} receipt changed chain authority",
                    chain_id=chain_id,
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            pending_outbox = None
            pending_records = ()
        elif event_outbox is not None:
            if current.get("journal_outbox") != event_outbox:
                raise FrozenError(
                    f"merge event {sequence} outbox projection is invalid",
                    chain_id=chain_id,
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            pending_outbox = copy.deepcopy(event_outbox)
            pending_records = tuple(copy.deepcopy(records))
        elif current.get("journal_outbox") != pending_outbox:
            raise FrozenError(
                f"merge event {sequence} changed its pending outbox",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        for carried_record in records:
            carried_binding = carried_record.get("binding")
            if not isinstance(
                carried_binding, dict
            ) or not builders._binding_matches_source_fact(
                carried_binding,
                carried_record,
                event,
                prior,
                current,
                family="merge",
            ):
                raise FrozenError(
                    f"merge event {sequence} carries an invalid journal binding",
                    chain_id=chain_id,
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
        replayed = copy.deepcopy(current)
        event_copy = copy.deepcopy(event)
        current_copy = copy.deepcopy(current)
        events.append(event_copy)
        entries.append(
            (
                event_copy,
                prior,
                current_copy,
                tuple(copy.deepcopy(records)),
                source_digest,
            )
        )
        prefix_state_bytes.append(canonical_bytes(current) + b"\n")
        previous_digest = digest
    if replayed is None or not events:
        raise FrozenError(
            "merge event replay is empty",
            chain_id=chain_id,
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    replayed_state = (
        validate_merge_state(replayed, chain_id)
        if _merge_history_uses_additive_grammar(events)
        else copy.deepcopy(replayed)
    )
    return MergeReplayResult(
        state=replayed_state,
        events=tuple(events),
        entries=tuple(entries),
        prefix_state_bytes=tuple(prefix_state_bytes),
        context=copy.deepcopy(context),
        raw_events=raw_events,
        tail_sequence=len(events),
        tail_digest=previous_digest,
    )


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
                if not isinstance(current, dict) or not builders._commit_transition_valid(
                    event, replayed, current
                ):
                    raise ValueError("commit transition is invalid")
                records, event_outbox, source_digest = builders._event_batch_records(
                    event, "commit"
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
                for record in records:
                    record_binding = record.get("binding")
                    if (
                        not isinstance(record_binding, dict)
                        or not builders._binding_matches_source_fact(
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
                for record in records:
                    record_binding = record.get("binding")
                    current_fact = bool(
                        isinstance(record_binding, dict)
                        and builders._binding_is_current(
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
                    # ``commit_produced`` is the authoritative landing fact,
                    # while the following ``chain_closed`` projection is a
                    # separate non-consequential event.  A crash after the
                    # landing batch was receipted therefore leaves one valid
                    # in-flight landing in ``committing``.  Admit only that
                    # exact recovery window; every other stale fact freezes.
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
                        current_fact = bool(
                            record.get("outcome") == "chain-landing"
                            and current.get("state") == "committing"
                            and isinstance(final_result, dict)
                            and isinstance(final_candidate, dict)
                            and isinstance(source_payload, dict)
                            and source_payload.get("event") == "commit_produced"
                            and isinstance(source_details, dict)
                            and isinstance(bound_candidate, dict)
                            and bound_candidate.get("kind")
                            == "staged-diff-sha256"
                            and bound_candidate.get("value")
                            == final_candidate.get("sha256")
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
                with batch.batch_lock(run_dir, create=False):
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
                    state["journal_outbox"] = copy.deepcopy(pending_outbox)
                    payload["state"] = copy.deepcopy(state)
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
                with batch.batch_lock(run_dir, create=False):
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
            with batch.batch_lock(run_dir, create=False):
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
    _batch, builders, journal = runtime._coordination_modules()
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
    projected = list(run_state.records)
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
    if records:
        _batch._prevalidate_records(
            _canonical_repository,
            run_state,
            records,
            close=False,
            defer_binding=True,
        )
    return tuple(records)


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
        self, binding: Mapping[str, Any] | None
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
            with batch.batch_lock(run_dir, create=False):
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
            binding if isinstance(binding, Mapping) else None
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
            for record in records:
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


def _require_common_lock_control(name: str) -> None:
    if name not in _REQUIRED_COMMON_LOCK_CONTROLS:
        raise ValueError(f"unknown common-lock control: {name}")
    if name not in COMMON_LOCK_CONTROLS:
        raise FrozenError(
            f"FR-235/FR-236 common-lock control is unavailable: {name}",
            observed=name,
            schema=REVISION9_OUTPUT_SCHEMA,
        )


class CommonLockBoundaryCrash(BaseException):
    """Test/embedding seam that models a process disappearing at a boundary.

    The lock implementation deliberately does not catch this ``BaseException``.
    A caller using it must do so only in an expendable process, because the
    canonical artifacts and any child are intentionally abandoned exactly as
    they would be after a crash.
    """


@dataclasses.dataclass(frozen=True)
class PublishedLockRecord:
    path: str
    device: int
    inode: int
    digest: str
    record: dict[str, Any]
    mode: int
    links: int

    def evidence(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "device": self.device,
            "inode": self.inode,
            "digest": self.digest,
            "record": copy.deepcopy(self.record),
        }


@dataclasses.dataclass(frozen=True)
class CommonLockInspection:
    topology: str
    outer: PublishedLockRecord | None = None
    inner: PublishedLockRecord | None = None
    detail: str | None = None
    artifacts: dict[str, Any] | None = None

    @property
    def recoverable(self) -> bool:
        return self.topology in {
            "complete",
            "outer-only",
            "outer-empty-directory",
        }

    def evidence(self, common_dir: Path) -> dict[str, Any]:
        result: dict[str, Any] = {
            "common_dir": str(common_dir),
            "topology": self.topology,
            "detail": self.detail,
        }
        if self.outer is not None:
            result["owner"] = self.outer.evidence()
        if self.inner is not None:
            result["inner"] = self.inner.evidence()
        if self.artifacts is not None:
            result["artifacts"] = copy.deepcopy(self.artifacts)
        return result


class CommonLockUnavailable(Refusal):
    """The exact envelope-only FR-235 acquisition refusal."""

    def __init__(self, evidence: Mapping[str, Any]) -> None:
        rendered = canonical_bytes(dict(evidence)).decode("utf-8")
        super().__init__(
            V2ReasonCode.REBASE_LOCK_UNAVAILABLE,
            "forge: common rebase lock unavailable",
            expected=(
                "complete mandatory portable ownership and any secondary flock "
                "within the shared 300-second deadline"
            ),
            observed=rendered,
            remediation=(
                "inspect the reported immutable owner, reservation, and fence; "
                "do not remove or replace them automatically"
            ),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
        self.evidence = copy.deepcopy(dict(evidence))


class CommonLockReleaseFailure(Refusal):
    """Release-only failure after the caller's primary truth is durable."""

    def __init__(self, evidence: Mapping[str, Any]) -> None:
        rendered = canonical_bytes(dict(evidence)).decode("utf-8")
        super().__init__(
            V2ReasonCode.LOCK_RELEASE_FAILED,
            "forge: common rebase lock release failed",
            expected="reverse-order release of the exact acquired lock identity",
            observed=rendered,
            remediation="retry only release recovery for the recorded lock identity",
            schema=REVISION9_OUTPUT_SCHEMA,
        )
        self.evidence = copy.deepcopy(dict(evidence))


class ChainLeaseUnavailable(Refusal):
    """Fail-closed per-chain serialization refusal."""

    def __init__(self, chain_id: str, evidence: Mapping[str, Any]) -> None:
        rendered = canonical_bytes(dict(evidence)).decode("utf-8")
        super().__init__(
            V2ReasonCode.STATE_PRECONDITION,
            "forge: merge chain lease unavailable",
            expected=f"exclusive current lease for {chain_id}",
            observed=rendered,
            remediation=f"forge status --chain-id {chain_id}",
            next_required_step=f"forge status --chain-id {chain_id}",
            chain={"chain_id": chain_id, "state": "unknown"},
            schema=REVISION9_OUTPUT_SCHEMA,
        )
        self.evidence = copy.deepcopy(dict(evidence))


class FencedChildSurvived(RuntimeError):
    """A fenced process group remains live or cannot be proved gone."""

    def __init__(self, result: "FencedProcessResult") -> None:
        super().__init__("fenced process group survived termination")
        self.result = result


def _valid_utc_second(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return iso_z(parse_time(value)) == value
    except (TypeError, ValueError):
        return False


def _valid_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _valid_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _valid_host(value: Any) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value.encode("utf-8")) <= 255
        and "\x00" not in value
    )


def _valid_nonce(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{32}", value) is not None


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


def _valid_nullable_chain(kind: Any, chain_id: Any, *, allow_phase5: bool) -> bool:
    if kind == "merge":
        return isinstance(chain_id, str) and CHAIN_ID_RE.fullmatch(chain_id) is not None
    allowed = {"push", "phase5"} if allow_phase5 else {"push"}
    return kind in allowed and chain_id is None


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


def _write_all(descriptor: int, value: bytes) -> None:
    position = 0
    while position < len(value):
        written = os.write(descriptor, value[position:])
        if written <= 0:
            raise OSError("short write")
        position += written


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


class _PublicationCleanupFailure(OSError):
    """A failed publication left an attempt-owned name unproved or undurable."""


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


def _process_probe(pid: int) -> str:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return "dead"
    except PermissionError:
        return "unprovable"
    except OSError as exc:
        return "dead" if exc.errno == errno.ESRCH else "unprovable"
    return "live"


def _group_probe(pgid: int) -> str:
    try:
        os.kill(-pgid, 0)
    except ProcessLookupError:
        return "dead"
    except PermissionError:
        return "unprovable"
    except OSError as exc:
        return "dead" if exc.errno == errno.ESRCH else "unprovable"
    return "live"


def _sleep_with_deadline(
    deadline: float,
    clock: Callable[[], float],
    sleeper: Callable[[float], None],
) -> bool:
    remaining = deadline - clock()
    if remaining <= 0:
        return False
    sleeper(min(COMMON_LOCK_POLL_SECONDS, remaining))
    return clock() < deadline


def _require_deadline_open(
    deadline: float, clock: Callable[[], float], operation: str
) -> None:
    _require_common_lock_control("single-deadline")
    if clock() >= deadline:
        raise TimeoutError(f"{operation} exhausted the shared common-lock deadline")


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


@dataclasses.dataclass(frozen=True)
class FencedProcessResult:
    argv: list[str]
    returncode: int | None
    duration_seconds: float
    output: bytes
    output_digest: str
    timed_out: bool
    output_limit: bool
    launch_failed: bool
    group_survived: bool
    authorized: bool
    fence_digest: str
    fence_inode: int
    metadata: Mapping[str, Any] | None = None

    def evidence(self) -> dict[str, Any]:
        return {
            "argv": list(self.argv),
            "returncode": self.returncode,
            "duration_seconds": self.duration_seconds,
            "output_digest": self.output_digest,
            "timed_out": self.timed_out,
            "output_limit": self.output_limit,
            "launch_failed": self.launch_failed,
            "group_survived": self.group_survived,
            "authorized": self.authorized,
            "fence_digest": self.fence_digest,
            "fence_inode": self.fence_inode,
        }


def merge_gate_intent_digest(
    *,
    chain_id: str,
    epoch_intent_digest: str,
    seal_event_digest: str,
    generation_digest: str,
    policy_digest: str,
    suite_digest: str,
    cursor: int,
    kind: str,
    gate_id: str,
    authorizing_event_digest: str,
) -> str:
    """Return Revision-10's exact cursor-selected gate-intent digest."""

    _require_common_lock_control("fence-intent-revalidation")
    if not CHAIN_ID_RE.fullmatch(chain_id):
        raise ValueError("gate intent chain identifier is invalid")
    digests = (
        epoch_intent_digest,
        seal_event_digest,
        generation_digest,
        policy_digest,
        suite_digest,
        authorizing_event_digest,
    )
    if any(SHA256_RE.fullmatch(value) is None for value in digests):
        raise ValueError("gate intent contains a malformed digest")
    if not _valid_nonnegative_int(cursor):
        raise ValueError("gate intent cursor is invalid")
    if kind not in {"gate", "scoped-mutation"}:
        raise ValueError("gate intent kind is invalid")
    if not isinstance(gate_id, str) or not gate_id:
        raise ValueError("gate intent id is invalid")
    if kind == "scoped-mutation" and gate_id != "scoped-mutation":
        raise ValueError("scoped-mutation gate intent id is invalid")
    if cursor == 0 and authorizing_event_digest != seal_event_digest:
        raise ValueError("cursor-zero gate intent is not authorized by its seal")
    preimage = {
        "schema": "forge-merge-gate-intent/1",
        "chain_id": chain_id,
        "epoch_intent_digest": epoch_intent_digest,
        "seal_event_digest": seal_event_digest,
        "generation_digest": generation_digest,
        "policy_digest": policy_digest,
        "suite_digest": suite_digest,
        "cursor": cursor,
        "kind": kind,
        "id": gate_id,
        "authorizing_event_digest": authorizing_event_digest,
    }
    return sha256_bytes(canonical_bytes(preimage))


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
    if _user_skip(state, gate_id) is not None:
        return True
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


def _forge_command(state: Mapping[str, Any] | None, verb: str) -> str:
    suffix = f" --chain-id {state['chain_id']}" if state else ""
    return f"forge {verb}{suffix}"


@dataclasses.dataclass(frozen=True)
class MergeRunTaskSnapshot:
    """Immutable journal values captured before a run-bound merge fetch."""

    binding: dict[str, str]
    task_files: tuple[str, ...]
    admitted_scope: tuple[str, ...]


def _merge_refusal(
    reason: V2ReasonCode,
    message: str,
    *,
    expected: str | None = None,
    observed: str | None = None,
    remediation: str | None = None,
    chain: Mapping[str, Any] | None = None,
    evidence_refs: Sequence[str] = (),
) -> Refusal:
    return Refusal(
        reason,
        message,
        expected=expected,
        observed=observed,
        remediation=remediation,
        chain=chain,
        evidence_refs=evidence_refs,
        schema=REVISION9_OUTPUT_SCHEMA,
    )


def _parse_registered_worktrees(raw: bytes) -> tuple[dict[str, str], ...]:
    records: list[dict[str, str]] = []
    for block in raw.split(b"\0\0"):
        if not block:
            continue
        record: dict[str, str] = {}
        for raw_field in block.split(b"\0"):
            if not raw_field:
                continue
            try:
                field = raw_field.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise OSError("Git worktree inventory is not UTF-8") from exc
            name, separator, value = field.partition(" ")
            if not separator:
                if name not in {"bare", "detached", "locked", "prunable"}:
                    raise OSError("Git worktree inventory is malformed")
                value = ""
            if name in record:
                raise OSError("Git worktree inventory is malformed")
            record[name] = value
        if "worktree" not in record or "HEAD" not in record:
            raise OSError("Git worktree inventory is incomplete")
        records.append(record)
    return tuple(records)


def _merge_rebase_action(state: Mapping[str, Any]) -> str | None:
    integration = state.get("integration")
    epoch = integration.get("epoch") if isinstance(integration, Mapping) else None
    pre_rebase = (
        integration.get("pre_rebase") if isinstance(integration, Mapping) else None
    )
    if not isinstance(epoch, Mapping) or not isinstance(pre_rebase, Mapping):
        return None
    nonce = epoch.get("operation_nonce")
    generation_digest = pre_rebase.get("generation_digest")
    if not _valid_nonce(nonce) or SHA256_RE.fullmatch(str(generation_digest or "")) is None:
        return None
    return (
        f"forge-merge-rebase:{state.get('chain_id')}:"
        f"{generation_digest}:{nonce}"
    )


def _merge_rebase_result_classification(state: Mapping[str, Any]) -> str:
    """Classify only a nonce/generation-bound raw result or its absent intent."""

    integration = state.get("integration")
    pre_rebase = (
        integration.get("pre_rebase") if isinstance(integration, Mapping) else None
    )
    epoch = integration.get("epoch") if isinstance(integration, Mapping) else None
    intent = integration.get("intent") if isinstance(integration, Mapping) else None
    action = _merge_rebase_action(state)
    if (
        not isinstance(pre_rebase, Mapping)
        or not isinstance(epoch, Mapping)
        or not isinstance(intent, Mapping)
        or action is None
        or intent.get("operation_nonce") != epoch.get("operation_nonce")
        or intent.get("pre_operation_head") != pre_rebase.get("head")
        or intent.get("fetched_tip") != pre_rebase.get("fetched_tip")
        or intent.get("branch") != state.get("branch")
        or intent.get("generation_digest") != pre_rebase.get("generation_digest")
        or intent.get("reflog_action") != action
    ):
        return "foreign"
    if intent.get("operation") in {"rebase", "continue"}:
        return "absent"
    raw_fields = {
        "operation",
        "operation_nonce",
        "result",
        "pre_operation_head",
        "fetched_tip",
        "branch",
        "generation_digest",
        "reflog_action",
        "exit",
        "inflight_digest",
        "output_digest",
        "launch_failed",
        "timed_out",
        "output_limit_exceeded",
        "group_survived",
        "recorded_at",
    }
    if (
        intent.get("operation") != "rebase-result"
        or set(intent) != raw_fields
        or (
            intent.get("exit") is not None
            and type(intent.get("exit")) is not int
        )
        or any(
            type(intent.get(name)) is not bool
            for name in (
                "launch_failed",
                "timed_out",
                "output_limit_exceeded",
                "group_survived",
            )
        )
        or SHA256_RE.fullmatch(str(intent.get("inflight_digest", ""))) is None
        or SHA256_RE.fullmatch(str(intent.get("output_digest", ""))) is None
        or not _valid_utc_second(intent.get("recorded_at"))
    ):
        return "foreign"
    succeeded = bool(
        intent.get("exit") == 0
        and intent.get("launch_failed") is False
        and intent.get("timed_out") is False
        and intent.get("output_limit_exceeded") is False
        and intent.get("group_survived") is False
    )
    if intent.get("result") != ("success" if succeeded else "failed"):
        return "foreign"
    if intent.get("group_survived") is True:
        return "foreign"
    return "success" if succeeded else "failed"


def _prove_merge_run_task_binding(
    repository: Path,
    common_root: Path,
    run_id: str,
    task_id: str,
    policy_digest: str,
) -> MergeRunTaskSnapshot:
    batch, _builders, journal = runtime._coordination_modules()
    run_dir = common_root / ".codex-orchestrator" / "runs" / run_id
    try:
        with batch.batch_lock(run_dir, create=False):
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


_MERGE_SCOPE_UNSET = frozenset(
    {
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_COMMON_DIR",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_NAMESPACE",
        "GIT_PREFIX",
        "GIT_EXTERNAL_DIFF",
        "GIT_DIFF_OPTS",
        "GIT_SHALLOW_FILE",
        "GIT_GRAFT_FILE",
    }
)


_MERGE_SCOPE_OVERLAY = {
    "LC_ALL": "C",
    "LANG": "C",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_ATTR_NOSYSTEM": "1",
    "GIT_OPTIONAL_LOCKS": "0",
    "GIT_NO_REPLACE_OBJECTS": "1",
    "GIT_NO_LAZY_FETCH": "1",
    "GIT_PAGER": "cat",
    "PAGER": "cat",
}


def _merge_scope_environment_contract() -> dict[str, Any]:
    return {
        "unset_prefixes": ["GIT_CONFIG_"],
        "unset_names": sorted(_MERGE_SCOPE_UNSET),
        "overlay": dict(sorted(_MERGE_SCOPE_OVERLAY.items())),
    }


def _valid_sorted_unique_strings(value: object) -> bool:
    return bool(
        isinstance(value, list)
        and all(isinstance(item, str) for item in value)
        and value
        == sorted(set(value), key=lambda item: item.encode("utf-8"))
    )


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


def _merge_containment(
    state: Mapping[str, Any],
) -> tuple[str, tuple[bool, ...]]:
    integration = state.get("integration")
    candidate = state.get("candidate")
    if not isinstance(integration, Mapping) or not isinstance(candidate, Mapping):
        return "none", ()
    push = integration.get("push")
    observed = integration.get("observed")
    if not isinstance(push, Mapping) or not isinstance(observed, Mapping):
        return "none", ()
    attempts = push.get("attempted_heads")
    vector = observed.get("attempted_head_containment")
    if (
        observed.get("exists") not in {True, False}
        or not isinstance(attempts, list)
        or not attempts
        or not isinstance(vector, list)
        or len(vector) != len(attempts)
    ):
        return "unresolved", ()
    flags: list[bool] = []
    for head, item in zip(attempts, vector):
        if (
            not isinstance(head, str)
            or not isinstance(item, Mapping)
            or item.get("head") != head
            or type(item.get("contained")) is not bool
        ):
            return "unresolved", ()
        flags.append(bool(item["contained"]))
    current_head = candidate.get("candidate_head")
    current_attempt = push.get("intended_head")
    if current_head != current_attempt or attempts[-1] != current_attempt:
        return "unresolved", tuple(flags)
    if observed.get("contains_intended_head") is not flags[-1]:
        return "unresolved", tuple(flags)
    if flags[-1]:
        return "current", tuple(flags)
    if any(flags[:-1]):
        return "older", tuple(flags)
    return "all-false", tuple(flags)


def _merge_old_tip_all_false(state: Mapping[str, Any]) -> bool:
    """Match one authoritative present-old-tip, all-attempts-absent fact."""

    integration = state.get("integration")
    if not isinstance(integration, Mapping):
        return False
    push = integration.get("push")
    observed = integration.get("observed")
    containment, vector = _merge_containment(state)
    return bool(
        isinstance(push, Mapping)
        and isinstance(observed, Mapping)
        and observed.get("exists") is True
        and observed.get("oid") == push.get("expected_old_tip")
        and containment == "all-false"
        and vector
        and all(flag is False for flag in vector)
    )


def _merge_latest_contained_attempt(state: Mapping[str, Any]) -> str | None:
    """Return only the latest attempted HEAD proved contained by observation."""

    integration = state.get("integration")
    push = integration.get("push") if isinstance(integration, Mapping) else None
    observed = (
        integration.get("observed") if isinstance(integration, Mapping) else None
    )
    attempts = push.get("attempted_heads") if isinstance(push, Mapping) else None
    vector = (
        observed.get("attempted_head_containment")
        if isinstance(observed, Mapping)
        else None
    )
    if not isinstance(attempts, list) or not isinstance(vector, list) or len(
        attempts
    ) != len(vector):
        return None
    latest: str | None = None
    for head, member in zip(attempts, vector):
        if not (
            isinstance(head, str)
            and COMMIT_RE.fullmatch(head) is not None
            and isinstance(member, Mapping)
            and member.get("head") == head
            and type(member.get("contained")) is bool
        ):
            return None
        if member["contained"] is True:
            latest = head
    return latest


def _merge_inactive_post_attempt_recovery_ready(
    state: Mapping[str, Any], history: Sequence[Mapping[str, Any]]
) -> bool:
    """Select only a push-consuming current epoch for inactive observation."""

    if state.get("state") not in _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES:
        return False
    integration = state.get("integration")
    epoch = integration.get("epoch") if isinstance(integration, Mapping) else None
    push = integration.get("push") if isinstance(integration, Mapping) else None
    candidate = state.get("candidate")
    attempts = push.get("attempted_heads") if isinstance(push, Mapping) else None
    if not (
        isinstance(epoch, Mapping)
        and isinstance(push, Mapping)
        and isinstance(candidate, Mapping)
        and isinstance(attempts, list)
        and bool(attempts)
        and attempts[-1] == push.get("intended_head")
        and push.get("intended_head") == candidate.get("candidate_head")
        and epoch.get("generation_digest") == candidate.get("generation_digest")
        and SHA256_RE.fullmatch(str(epoch.get("intent_digest", ""))) is not None
    ):
        return False
    epoch_event = next(
        (
            member
            for member in reversed(history)
            if member.get("event") == "epoch_intent"
            and member.get("digest") == epoch.get("intent_digest")
        ),
        None,
    )
    push_event = next(
        (member for member in reversed(history) if member.get("event") == "push_intent"),
        None,
    )
    return bool(
        isinstance(epoch_event, Mapping)
        and isinstance(push_event, Mapping)
        and type(epoch_event.get("sequence")) is int
        and type(push_event.get("sequence")) is int
        and int(push_event["sequence"]) > int(epoch_event["sequence"])
        and push_event.get("generation_digest") == candidate.get("generation_digest")
    )


def _remote_observation_heads(state: Mapping[str, Any]) -> list[str]:
    integration = state.get("integration")
    push = integration.get("push") if isinstance(integration, Mapping) else None
    attempts = push.get("attempted_heads") if isinstance(push, Mapping) else None
    if isinstance(attempts, list) and attempts:
        return [str(head) for head in attempts]
    candidate = state.get("candidate")
    if not isinstance(candidate, Mapping):
        raise ValueError("remote observation candidate is unavailable")
    return [str(candidate["candidate_head"])]


def _remote_observation_fetch_argv(state: Mapping[str, Any]) -> list[str]:
    return [
        "git",
        "--no-pager",
        "-C",
        str(state["worktree"]["path"]),
        "fetch",
        "--no-tags",
        "--quiet",
        "origin",
        str(state["target"]["destination_ref"]),
    ]


def _remote_containment_argv(
    state: Mapping[str, Any], head: str, tip: str
) -> list[str]:
    return [
        "git",
        "--no-pager",
        "--no-replace-objects",
        "-C",
        str(state["worktree"]["path"]),
        "merge-base",
        "--is-ancestor",
        head,
        tip,
    ]


_EPOCH_FETCH_OBSERVATION_SCHEMA = "forge-epoch-fetch-observation/1"


def _epoch_fetch_observation_record_valid(
    state: Mapping[str, Any], value: object
) -> bool:
    """Validate the non-sealing result of an epoch's fenced fetch child."""

    if not isinstance(value, Mapping) or set(value) != {
        "schema",
        "chain_id",
        "epoch_intent_digest",
        "operation_nonce",
        "generation_digest",
        "fetch_intent_event_digest",
        "target",
        "argv",
        "child_result",
        "recorded_at",
    }:
        return False
    integration = state.get("integration")
    epoch = integration.get("epoch") if isinstance(integration, Mapping) else None
    plan = epoch.get("gate_plan") if isinstance(epoch, Mapping) else None
    candidate = state.get("candidate")
    expected_argv = [
        "git",
        "--no-pager",
        "-C",
        str(state.get("worktree", {}).get("path", "")),
        "fetch",
        "--no-tags",
        "--quiet",
        "origin",
        str(state.get("target", {}).get("destination_ref", "")),
    ]
    if (
        value.get("schema") != _EPOCH_FETCH_OBSERVATION_SCHEMA
        or value.get("chain_id") != state.get("chain_id")
        or not isinstance(epoch, Mapping)
        or not isinstance(plan, Mapping)
        or plan.get("status") != "unsealed"
        or value.get("epoch_intent_digest") != epoch.get("intent_digest")
        or value.get("operation_nonce") != epoch.get("operation_nonce")
        or not isinstance(candidate, Mapping)
        or value.get("generation_digest") != candidate.get("generation_digest")
        or value.get("generation_digest") != epoch.get("generation_digest")
        or SHA256_RE.fullmatch(str(value.get("fetch_intent_event_digest", "")))
        is None
        or value.get("target") != state.get("target")
        or value.get("argv") != expected_argv
        or not _valid_utc_second(value.get("recorded_at"))
    ):
        return False
    child = value.get("child_result")
    if not isinstance(child, Mapping) or set(child) != {
        "authorized",
        "exit",
        "inflight_digest",
        "output_digest",
        "launch_failed",
        "timed_out",
        "output_limit_exceeded",
        "group_survived",
    }:
        return False
    return bool(
        type(child.get("authorized")) is bool
        and (child.get("exit") is None or type(child.get("exit")) is int)
        and SHA256_RE.fullmatch(str(child.get("inflight_digest", ""))) is not None
        and SHA256_RE.fullmatch(str(child.get("output_digest", ""))) is not None
        and all(
            type(child.get(name)) is bool
            for name in (
                "launch_failed",
                "timed_out",
                "output_limit_exceeded",
                "group_survived",
            )
        )
    )


def _epoch_fetch_observation_passed(value: Mapping[str, Any]) -> bool:
    child = value.get("child_result")
    return bool(
        isinstance(child, Mapping)
        and child.get("authorized") is True
        and child.get("exit") == 0
        and child.get("launch_failed") is False
        and child.get("timed_out") is False
        and child.get("output_limit_exceeded") is False
        and child.get("group_survived") is False
    )


def _epoch_fetch_result_intent_digest(
    event: Mapping[str, Any],
    prior: Mapping[str, Any] | None,
    current: Mapping[str, Any],
    context: Mapping[str, Any],
) -> str | None:
    """Authenticate an interposed raw-fetch/observation result chain.

    The shared Revision-9 grammar expects ``fetch_result`` to immediately
    follow ``fetch_intent``.  Revision 10 first retains the fenced child's raw
    result and, when the fetched tip is unchanged, the separately fenced
    candidate and carried-successor observations.  This helper proves that
    complete chain and returns the original intent digest for an in-memory
    compatibility bridge; it never relaxes the shared validator.
    """

    if event.get("event") != "fetch_result" or prior is None:
        return None

    def follows_authenticated_result(
        result_digest: object,
        *,
        operation: str,
    ) -> bool:
        if event.get("previous_digest") == result_digest:
            return True
        bridge = context.get("recovery_proof_bridge")
        return bool(
            isinstance(result_digest, str)
            and isinstance(bridge, Mapping)
            and event.get("previous_digest") == bridge.get("event_digest")
            and bridge.get("previous_digest") == result_digest
            and (
                bridge.get("operation") == operation
                and bridge.get("classification")
                == f"{operation}-result-persisted"
                or bridge.get("operation") is None
                and bridge.get("intent_digest") is None
                and bridge.get("classification") == "owner-death-only"
            )
        )

    admitted = context.get("fetch_intent")
    raw = context.get("epoch_fetch_observation")
    if not isinstance(admitted, Mapping) or not isinstance(raw, Mapping):
        return None
    admitted_evidence = admitted.get("evidence")
    raw_evidence = raw.get("evidence")
    prior_candidate = prior.get("candidate")
    prior_integration = prior.get("integration")
    current_integration = current.get("integration")
    current_result = (
        current_integration.get("intent")
        if isinstance(current_integration, Mapping)
        else None
    )
    if (
        not isinstance(admitted_evidence, Mapping)
        or not isinstance(raw_evidence, Mapping)
        or not isinstance(prior_candidate, Mapping)
        or not isinstance(prior_integration, Mapping)
        or not isinstance(current_integration, Mapping)
        or not isinstance(current_result, Mapping)
        or set(current_result)
        != {
            "operation",
            "operation_nonce",
            "attempt",
            "result",
            "resolved_tip",
        }
        or current_result.get("operation") != "fetch-result"
        or current_result.get("operation_nonce")
        != admitted_evidence.get("operation_nonce")
        or current_result.get("attempt") != admitted_evidence.get("attempt")
        or admitted_evidence.get("operation") != "fetch"
        or raw.get("generation_digest") != event.get("generation_digest")
        or raw.get("generation_digest")
        != prior_candidate.get("generation_digest")
        or raw_evidence.get("fetch_intent_event_digest")
        != admitted.get("digest")
        or raw_evidence.get("operation_nonce")
        != admitted_evidence.get("operation_nonce")
        or raw_evidence.get("target") != admitted_evidence.get("target")
        or not _epoch_fetch_observation_record_valid(prior, raw_evidence)
    ):
        return None

    passed = _epoch_fetch_observation_passed(raw_evidence)
    if current_result.get("result") != ("success" if passed else "failed"):
        return None
    if not passed:
        if (
            current_result.get("resolved_tip") is not None
            or not follows_authenticated_result(
                raw.get("digest"), operation="fetch"
            )
            or current.get("state") != "authorized"
            or current_integration.get("epoch") is not None
        ):
            return None
        return str(admitted.get("digest"))

    fetched_tip = current_result.get("resolved_tip")
    if not isinstance(fetched_tip, str) or COMMIT_RE.fullmatch(fetched_tip) is None:
        return None
    unchanged = fetched_tip == prior_candidate.get("remote_tip")
    before_epoch = prior_integration.get("epoch")
    after_epoch = current_integration.get("epoch")
    before_plan = (
        before_epoch.get("gate_plan") if isinstance(before_epoch, Mapping) else None
    )
    after_plan = (
        after_epoch.get("gate_plan") if isinstance(after_epoch, Mapping) else None
    )
    if (
        not isinstance(before_plan, Mapping)
        or before_plan.get("status") != "unsealed"
        or not isinstance(after_plan, Mapping)
    ):
        return None
    if not unchanged:
        if (
            not follows_authenticated_result(
                raw.get("digest"), operation="fetch"
            )
            or after_plan != before_plan
            or current.get("state") != prior.get("state")
            or current.get("state") != "rebasing"
        ):
            return None
        return str(admitted.get("digest"))

    candidate_observation = context.get("candidate_observation")
    if not isinstance(candidate_observation, Mapping):
        return None
    observation = candidate_observation.get("evidence")
    if (
        not _merge_candidate_observation_evidence_valid(prior, observation)
        or candidate_observation.get("generation_digest")
        != prior_candidate.get("generation_digest")
        or candidate_observation.get("source_intent") != raw_evidence
        or candidate_observation.get("evidence_digest")
        != observation.get("evidence_digest")
        or observation.get("source_intent") != raw_evidence
        or observation.get("remote_tip") != fetched_tip
        or observation.get("expected_head")
        != prior_candidate.get("candidate_head")
        or observation.get("classify") is not True
    ):
        return None

    authorization = prior.get("authorization")
    carried = bool(
        isinstance(authorization, Mapping)
        and authorization.get("candidate_head")
        == prior_candidate.get("candidate_head")
        and authorization.get("review_verdict") == "PASS"
        and SHA256_RE.fullmatch(
            str(authorization.get("generation_digest", ""))
        )
        is not None
        and authorization.get("generation_digest")
        != prior_candidate.get("generation_digest")
    )
    if carried:
        ancestry = context.get("epoch_ancestry_observation")
        ancestry_evidence = (
            ancestry.get("evidence") if isinstance(ancestry, Mapping) else None
        )
        if (
            not isinstance(ancestry, Mapping)
            or not isinstance(ancestry_evidence, Mapping)
            or ancestry.get("generation_digest")
            != prior_candidate.get("generation_digest")
            or not follows_authenticated_result(
                ancestry.get("digest"), operation="containment"
            )
            or not _epoch_ancestry_record_valid(prior, ancestry_evidence)
            or ancestry_evidence.get("phase") != "result"
            or ancestry_evidence.get("fetch_observation_event_digest")
            != raw.get("digest")
            or ancestry_evidence.get("candidate_observation_digest")
            != candidate_observation.get("evidence_digest")
        ):
            return None
        contained = ancestry_evidence.get("child_result", {}).get("contained")
        if contained is True:
            if (
                after_plan.get("status") != "sealed"
                or current.get("state")
                != ("reverifying" if after_plan.get("suite") else "rebasing")
            ):
                return None
        elif contained is False or contained is None:
            if after_plan != before_plan or current.get("state") != "rebasing":
                return None
        else:
            return None
    else:
        if (
            not isinstance(authorization, Mapping)
            or authorization.get("candidate_head")
            != prior_candidate.get("candidate_head")
            or authorization.get("review_verdict") != "PASS"
            or authorization.get("generation_digest")
            != prior_candidate.get("generation_digest")
            or event.get("previous_digest")
            != candidate_observation.get("restore_event_digest")
            or after_plan.get("status") != "sealed"
            or current.get("state")
            != ("reverifying" if after_plan.get("suite") else "rebasing")
        ):
            return None
    return str(admitted.get("digest"))


def _epoch_ancestry_record_valid(
    state: Mapping[str, Any], value: object
) -> bool:
    """Validate the fenced carried-generation ancestry intent or result."""

    if not isinstance(value, Mapping):
        return False
    base_fields = {
        "schema",
        "chain_id",
        "epoch_intent_digest",
        "operation_nonce",
        "generation_digest",
        "fetch_observation_event_digest",
        "candidate_observation_digest",
        "fetched_tip",
        "candidate_head",
        "argv",
        "phase",
        "recorded_at",
    }
    phase = value.get("phase")
    if set(value) != (
        base_fields
        if phase == "intent"
        else {*base_fields, "intent_event_digest", "child_result"}
    ):
        return False
    integration = state.get("integration")
    epoch = integration.get("epoch") if isinstance(integration, Mapping) else None
    plan = epoch.get("gate_plan") if isinstance(epoch, Mapping) else None
    candidate = state.get("candidate")
    authorization = state.get("authorization")
    if (
        value.get("schema") != "forge-epoch-ancestry-intent/1"
        or phase not in {"intent", "result"}
        or value.get("chain_id") != state.get("chain_id")
        or not isinstance(epoch, Mapping)
        or value.get("epoch_intent_digest") != epoch.get("intent_digest")
        or value.get("operation_nonce") != epoch.get("operation_nonce")
        or value.get("generation_digest") != epoch.get("generation_digest")
        or not isinstance(plan, Mapping)
        or plan.get("status") != "unsealed"
        or not isinstance(candidate, Mapping)
        or value.get("generation_digest") != candidate.get("generation_digest")
        or value.get("fetched_tip") != candidate.get("remote_tip")
        or value.get("candidate_head") != candidate.get("candidate_head")
        or not isinstance(authorization, Mapping)
        or authorization.get("candidate_head") != candidate.get("candidate_head")
        or authorization.get("review_verdict") != "PASS"
        or SHA256_RE.fullmatch(str(authorization.get("generation_digest", "")))
        is None
        or authorization.get("generation_digest") == candidate.get("generation_digest")
        or SHA256_RE.fullmatch(str(value.get("fetch_observation_event_digest", "")))
        is None
        or SHA256_RE.fullmatch(str(value.get("candidate_observation_digest", "")))
        is None
        or value.get("argv")
        != _remote_containment_argv(
            state, str(value.get("fetched_tip")), str(value.get("candidate_head"))
        )
        or not _valid_utc_second(value.get("recorded_at"))
    ):
        return False
    if phase == "intent":
        return True
    if SHA256_RE.fullmatch(str(value.get("intent_event_digest", ""))) is None:
        return False
    child = value.get("child_result")
    if not isinstance(child, Mapping) or set(child) != {
        "authorized",
        "exit",
        "inflight_digest",
        "output_digest",
        "launch_failed",
        "timed_out",
        "output_limit_exceeded",
        "group_survived",
        "contained",
    }:
        return False
    exit_code = child.get("exit")
    ordinary = bool(
        child.get("authorized") is True
        and type(exit_code) is int
        and exit_code in {0, 1}
        and child.get("launch_failed") is False
        and child.get("timed_out") is False
        and child.get("output_limit_exceeded") is False
        and child.get("group_survived") is False
    )
    return bool(
        type(child.get("authorized")) is bool
        and (exit_code is None or type(exit_code) is int)
        and SHA256_RE.fullmatch(str(child.get("inflight_digest", ""))) is not None
        and SHA256_RE.fullmatch(str(child.get("output_digest", ""))) is not None
        and type(child.get("launch_failed")) is bool
        and type(child.get("timed_out")) is bool
        and type(child.get("output_limit_exceeded")) is bool
        and type(child.get("group_survived")) is bool
        and child.get("contained") == ((exit_code == 0) if ordinary else None)
    )


def _remote_containment_evidence_valid(
    state: Mapping[str, Any], value: object, *, head: str, tip: str
) -> bool:
    if not isinstance(value, Mapping) or set(value) != {
        "head",
        "tip",
        "argv",
        "authorized",
        "exit",
        "inflight_digest",
        "output_digest",
        "launch_failed",
        "timed_out",
        "output_limit_exceeded",
        "group_survived",
        "contained",
    }:
        return False
    exit_code = value.get("exit")
    ordinary = bool(
        value.get("authorized") is True
        and type(exit_code) is int
        and exit_code in {0, 1}
        and value.get("launch_failed") is False
        and value.get("timed_out") is False
        and value.get("output_limit_exceeded") is False
        and value.get("group_survived") is False
    )
    return bool(
        value.get("head") == head
        and value.get("tip") == tip
        and value.get("argv") == _remote_containment_argv(state, head, tip)
        and type(value.get("authorized")) is bool
        and (exit_code is None or type(exit_code) is int)
        and SHA256_RE.fullmatch(str(value.get("inflight_digest", ""))) is not None
        and SHA256_RE.fullmatch(str(value.get("output_digest", ""))) is not None
        and type(value.get("launch_failed")) is bool
        and type(value.get("timed_out")) is bool
        and type(value.get("output_limit_exceeded")) is bool
        and type(value.get("group_survived")) is bool
        and value.get("contained")
        == ((exit_code == 0) if ordinary else None)
    )


def _remote_observation_progress_valid(
    state: Mapping[str, Any], value: object
) -> bool:
    if not isinstance(value, Mapping) or set(value) != {
        "schema",
        "transaction",
        "chain_id",
        "attempt_identity",
        "phase",
        "push_intent_digest",
        "stage",
        "fetch_result",
        "heads",
        "cursor",
        "head",
        "argv",
        "completed",
        "recorded_at",
    }:
        return False
    integration = state.get("integration")
    epoch = integration.get("epoch") if isinstance(integration, Mapping) else None
    phase = value.get("phase")
    push_intent_digest = value.get("push_intent_digest")
    if (
        value.get("schema") != "forge-remote-observation-progress/1"
        or value.get("transaction") != "merge"
        or value.get("chain_id") != state.get("chain_id")
        or not isinstance(epoch, Mapping)
        or value.get("attempt_identity") != epoch.get("intent_digest")
        or phase not in {"final-prepush", "post-push"}
        or (
            phase == "final-prepush" and push_intent_digest is not None
        )
        or (
            phase == "post-push"
            and SHA256_RE.fullmatch(str(push_intent_digest or "")) is None
        )
        or not _valid_utc_second(value.get("recorded_at"))
    ):
        return False
    heads = value.get("heads")
    expected_heads = _remote_observation_heads(state)
    if heads != expected_heads:
        return False
    fetch = value.get("fetch_result")
    if not isinstance(fetch, Mapping) or set(fetch) != {
        "argv",
        "authorized",
        "exit",
        "exists",
        "oid",
        "inflight_digest",
        "output_digest",
        "launch_failed",
        "timed_out",
        "output_limit_exceeded",
        "group_survived",
    }:
        return False
    exists = fetch.get("exists")
    oid = fetch.get("oid")
    exit_code = fetch.get("exit")
    if (
        fetch.get("argv") != _remote_observation_fetch_argv(state)
        or fetch.get("authorized") is not True
        or (exit_code is not None and type(exit_code) is not int)
        or (exists is not True and exists is not False and exists is not None)
        or (
            exists is True
            and (
                not isinstance(oid, str) or COMMIT_RE.fullmatch(oid) is None
            )
        )
        or (exists is not True and oid is not None)
        or SHA256_RE.fullmatch(str(fetch.get("inflight_digest", ""))) is None
        or SHA256_RE.fullmatch(str(fetch.get("output_digest", ""))) is None
        or type(fetch.get("launch_failed")) is not bool
        or type(fetch.get("timed_out")) is not bool
        or type(fetch.get("output_limit_exceeded")) is not bool
        or type(fetch.get("group_survived")) is not bool
    ):
        return False
    completed = value.get("completed")
    if not isinstance(completed, list) or len(completed) > len(expected_heads):
        return False
    tip = str(oid or "")
    if any(
        not _remote_containment_evidence_valid(
            state, evidence, head=expected_heads[index], tip=tip
        )
        for index, evidence in enumerate(completed)
    ):
        return False
    stage = value.get("stage")
    cursor = value.get("cursor")
    head = value.get("head")
    argv = value.get("argv")
    if stage == "fetch-result":
        return bool(
            cursor == 0
            and head is None
            and argv is None
            and completed == []
        )
    if exists is not True or type(cursor) is not int:
        return False
    if stage == "containment-intent":
        return bool(
            cursor == len(completed)
            and cursor < len(expected_heads)
            and head == expected_heads[cursor]
            and argv == _remote_containment_argv(state, str(head), tip)
            and all(item.get("contained") is not None for item in completed)
        )
    if stage == "containment-result":
        return bool(
            completed
            and cursor == len(completed) - 1
            and cursor < len(expected_heads)
            and head == expected_heads[cursor]
            and argv == _remote_containment_argv(state, str(head), tip)
            and completed[-1].get("head") == head
        )
    return False


def _remote_observation_progress_transition_valid(
    prior: Mapping[str, Any], current: Mapping[str, Any]
) -> bool:
    prior_integration = prior.get("integration")
    current_integration = current.get("integration")
    if not isinstance(prior_integration, Mapping) or not isinstance(
        current_integration, Mapping
    ):
        return False
    prior_intent = prior_integration.get("intent")
    current_intent = current_integration.get("intent")
    if not _remote_observation_progress_valid(current, current_intent):
        return False
    assert isinstance(current_intent, Mapping)
    stage = current_intent.get("stage")
    identity_fields = {
        "schema",
        "transaction",
        "chain_id",
        "attempt_identity",
        "phase",
        "push_intent_digest",
        "fetch_result",
        "heads",
    }
    if stage == "fetch-result":
        return bool(
            isinstance(prior_intent, Mapping)
            and set(prior_intent)
            == {
                "schema",
                "transaction",
                "chain_id",
                "attempt_identity",
                "phase",
                "push_intent_digest",
            }
            and prior_intent.get("schema")
            == "forge-remote-observation-intent/1"
            and all(
                prior_intent.get(name) == current_intent.get(name)
                for name in {
                    "transaction",
                    "chain_id",
                    "attempt_identity",
                    "phase",
                    "push_intent_digest",
                }
            )
        )
    if not _remote_observation_progress_valid(prior, prior_intent):
        return False
    assert isinstance(prior_intent, Mapping)
    if any(prior_intent.get(name) != current_intent.get(name) for name in identity_fields):
        return False
    if stage == "containment-intent":
        return bool(
            prior_intent.get("stage") in {"fetch-result", "containment-result"}
            and prior_intent.get("completed") == current_intent.get("completed")
            and current_intent.get("cursor")
            == len(current_intent.get("completed", []))
        )
    if stage == "containment-result":
        prior_completed = prior_intent.get("completed")
        current_completed = current_intent.get("completed")
        return bool(
            prior_intent.get("stage") == "containment-intent"
            and prior_intent.get("cursor") == current_intent.get("cursor")
            and prior_intent.get("head") == current_intent.get("head")
            and prior_intent.get("argv") == current_intent.get("argv")
            and isinstance(prior_completed, list)
            and isinstance(current_completed, list)
            and current_completed[:-1] == prior_completed
        )
    return False


def _remote_observation_progress_matches_observed(
    state: Mapping[str, Any],
    progress: object,
    observed: object,
    *,
    event_at: object,
) -> bool:
    """Bind a final observation vector to its authenticated child progress."""

    if (
        not _remote_observation_progress_valid(state, progress)
        or not isinstance(progress, Mapping)
        or not isinstance(observed, Mapping)
        or set(observed)
        != {
            "exists",
            "oid",
            "contains_intended_head",
            "attempted_head_containment",
            "observed_at",
            "inflight_digest",
            "output_digest",
        }
    ):
        return False
    fetch = progress.get("fetch_result")
    heads = progress.get("heads")
    completed = progress.get("completed")
    if not (
        isinstance(fetch, Mapping)
        and isinstance(heads, list)
        and isinstance(completed, list)
    ):
        return False
    exists = fetch.get("exists")
    oid = fetch.get("oid")
    complete_containment = bool(
        exists is True
        and len(completed) == len(heads)
        and all(type(member.get("contained")) is bool for member in completed)
    )
    if complete_containment:
        vector_values: list[bool | None] = [
            bool(member["contained"]) for member in completed
        ]
    elif exists is False:
        vector_values = [False for _head in heads]
    else:
        exists = None
        oid = None
        vector_values = [None for _head in heads]
    integration = state.get("integration")
    push = integration.get("push") if isinstance(integration, Mapping) else None
    attempts = (
        list(push.get("attempted_heads", []))
        if isinstance(push, Mapping)
        else []
    )
    attempted_vector = [
        {"head": head, "contained": contained}
        for head, contained in zip(attempts, vector_values[-len(attempts) :])
    ]
    contains_intended = vector_values[-1] if vector_values else None
    progress_at = (
        parse_time(str(progress.get("recorded_at")))
        if _valid_utc_second(progress.get("recorded_at"))
        else None
    )
    observed_at = (
        parse_time(str(observed.get("observed_at")))
        if _valid_utc_second(observed.get("observed_at"))
        else None
    )
    recorded_event_at = (
        parse_time(str(event_at)) if _valid_utc_second(event_at) else None
    )
    return bool(
        progress_at is not None
        and observed_at is not None
        and recorded_event_at is not None
        and progress_at <= observed_at <= recorded_event_at
        and observed.get("exists") is exists
        and observed.get("oid") == oid
        and observed.get("contains_intended_head") is contains_intended
        and observed.get("attempted_head_containment") == attempted_vector
        and observed.get("inflight_digest") == fetch.get("inflight_digest")
        and observed.get("output_digest") == fetch.get("output_digest")
    )


def _replayed_remote_observation_completed(
    event: Mapping[str, Any],
    state: Mapping[str, Any],
    context: Mapping[str, Any],
) -> bool:
    """Require a final vector to immediately follow its restored progress."""

    integration = state.get("integration")
    intent = integration.get("intent") if isinstance(integration, Mapping) else None
    observed = (
        integration.get("observed") if isinstance(integration, Mapping) else None
    )
    replayed = context.get("remote_observation")
    return bool(
        isinstance(intent, Mapping)
        and intent.get("schema") == "forge-remote-observation-intent/1"
        and intent.get("phase") == "post-push"
        and isinstance(replayed, Mapping)
        and replayed.get("generation_digest") == event.get("generation_digest")
        and replayed.get("intent_event_digest") == event.get("previous_digest")
        and replayed.get("restore_event_digest") == event.get("previous_digest")
        and replayed.get("intent") == intent
        and isinstance(replayed.get("completed_progress"), Mapping)
        and _remote_observation_progress_matches_observed(
            state,
            replayed["completed_progress"],
            observed,
            event_at=event.get("at"),
        )
    )


_MERGE_CANDIDATE_OBSERVATION_SCHEMA = "forge-merge-candidate-observation/1"


_MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA = (
    "forge-merge-candidate-observation-evidence/1"
)


_BOOTSTRAP_FETCH_OBSERVATION_SCHEMA = "forge-bootstrap-fetch-observation/1"


def _bootstrap_fetch_observation_record_valid(
    state: Mapping[str, Any], value: object
) -> bool:
    if not isinstance(value, Mapping) or set(value) != {
        "schema",
        "chain_id",
        "generation_digest",
        "source_intent",
        "operation",
        "fetch_intent_event_digest",
        "argv",
        "resolved_tip",
        "child_result",
        "recorded_at",
    }:
        return False
    candidate = state.get("candidate")
    generation_digest = (
        candidate.get("generation_digest")
        if isinstance(candidate, Mapping)
        else None
    )
    source = value.get("source_intent")
    child = value.get("child_result")
    operation = value.get("operation")
    argv = value.get("argv")
    worktree = state.get("worktree")
    target = state.get("target")
    resolved_tip = value.get("resolved_tip")
    expected_fetch_argv = (
        [
            "git",
            "--no-pager",
            "-C",
            str(worktree.get("path", "")),
            "fetch",
            "--no-tags",
            "--quiet",
            "origin",
            str(target.get("destination_ref", "")),
        ]
        if isinstance(worktree, Mapping) and isinstance(target, Mapping)
        else None
    )
    tip_argv = bool(
        isinstance(worktree, Mapping)
        and isinstance(argv, list)
        and len(argv) == 7
        and argv[:6]
        == [
            "git",
            "--no-pager",
            "-C",
            str(worktree.get("path", "")),
            "cat-file",
            "-e",
        ]
    )
    tip_argument = argv[-1] if tip_argv else ""
    requested_tip = (
        tip_argument.removesuffix("^{commit}")
        if tip_argument.endswith("^{commit}")
        else ""
    )
    if (
        value.get("schema") != _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA
        or value.get("chain_id") != state.get("chain_id")
        or value.get("generation_digest") != generation_digest
        or not isinstance(source, Mapping)
        or source.get("operation") != "fetch"
        or not _valid_nonce(source.get("operation_nonce"))
        or not _valid_positive_int(source.get("attempt"))
        or operation not in {"fetch", "tip-resolution"}
        or not isinstance(argv, list)
        or not argv
        or not all(isinstance(member, str) and member for member in argv)
        or SHA256_RE.fullmatch(
            str(value.get("fetch_intent_event_digest", ""))
        )
        is None
        or not _valid_utc_second(value.get("recorded_at"))
        or not isinstance(child, Mapping)
        or set(child)
        != {
            "authorized",
            "exit",
            "inflight_digest",
            "output_digest",
            "launch_failed",
            "timed_out",
            "output_limit_exceeded",
            "group_survived",
        }
    ):
        return False
    child_valid = bool(
        type(child.get("authorized")) is bool
        and (child.get("exit") is None or type(child.get("exit")) is int)
        and SHA256_RE.fullmatch(str(child.get("inflight_digest", "")))
        is not None
        and SHA256_RE.fullmatch(str(child.get("output_digest", ""))) is not None
        and all(
            type(child.get(name)) is bool
            for name in (
                "launch_failed",
                "timed_out",
                "output_limit_exceeded",
                "group_survived",
            )
        )
    )
    if not child_valid:
        return False
    child_passed = bool(
        child.get("authorized") is True
        and child.get("exit") == 0
        and child.get("launch_failed") is False
        and child.get("timed_out") is False
        and child.get("output_limit_exceeded") is False
        and child.get("group_survived") is False
    )
    if operation == "fetch":
        argv_valid = argv == expected_fetch_argv
    else:
        argv_valid = bool(
            tip_argv
            and COMMIT_RE.fullmatch(requested_tip) is not None
        )
    return bool(
        argv_valid
        and (
            resolved_tip is None
            or isinstance(resolved_tip, str)
            and COMMIT_RE.fullmatch(resolved_tip) is not None
        )
        and (
            not child_passed
            or operation != "tip-resolution"
            or resolved_tip == requested_tip
        )
    )


def _bootstrap_fetch_observation_transition_valid(
    prior: Mapping[str, Any], current: Mapping[str, Any]
) -> bool:
    prior_integration = prior.get("integration")
    current_integration = current.get("integration")
    if not isinstance(prior_integration, Mapping) or not isinstance(
        current_integration, Mapping
    ):
        return False
    prior_intent = prior_integration.get("intent")
    current_intent = current_integration.get("intent")
    if any(
        prior_integration.get(name) != current_integration.get(name)
        for name in (set(prior_integration) | set(current_integration)) - {"intent"}
    ):
        return False
    if _bootstrap_fetch_observation_record_valid(current, current_intent):
        assert isinstance(current_intent, Mapping)
        return bool(
            isinstance(prior_intent, Mapping)
            and prior_intent.get("operation") == "fetch"
            and current_intent.get("source_intent") == prior_intent
        )
    return bool(
        _bootstrap_fetch_observation_record_valid(prior, prior_intent)
        and isinstance(prior_intent, Mapping)
        and current_intent == prior_intent.get("source_intent")
    )


def _merge_candidate_observation_step_specs(
    state: Mapping[str, Any],
    *,
    remote_tip: str,
    expected_head: str,
    classify: bool,
    declared_tier: str | None,
) -> tuple[tuple[str, Path, list[str]], ...] | None:
    """Return the closed direct-argv observation program for one candidate."""

    worktree = state.get("worktree")
    target = state.get("target")
    if not isinstance(worktree, Mapping) or not isinstance(target, Mapping):
        return None
    worktree_path = Path(str(worktree.get("path", "")))
    repository_path = Path(str(state.get("repository", "")))
    manifest_commit = str(target.get("manifest_commit", ""))
    if (
        not worktree_path.is_absolute()
        or not repository_path.is_absolute()
        or COMMIT_RE.fullmatch(remote_tip) is None
        or COMMIT_RE.fullmatch(expected_head) is None
        or COMMIT_RE.fullmatch(manifest_commit) is None
        or type(classify) is not bool
        or (declared_tier is not None and declared_tier not in TIER_RANK)
    ):
        return None
    range_value = f"{remote_tip}...{expected_head}"
    steps: list[tuple[str, Path, list[str]]] = [
        (
            "worktrees",
            repository_path,
            ["git", "--no-pager", "worktree", "list", "--porcelain", "-z"],
        ),
        (
            "identity",
            worktree_path,
            [
                "git",
                "--no-pager",
                "rev-parse",
                "--path-format=absolute",
                "--git-dir",
                "--git-common-dir",
                "--show-toplevel",
                "HEAD",
            ],
        ),
        (
            "branch",
            worktree_path,
            ["git", "--no-pager", "symbolic-ref", "-q", "HEAD"],
        ),
        (
            "status",
            worktree_path,
            [
                "git",
                "-c",
                "core.fsmonitor=false",
                "-c",
                "core.untrackedCache=false",
                "--no-optional-locks",
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
                "--ignore-submodules=none",
            ],
        ),
        (
            "main-head",
            repository_path,
            ["git", "--no-pager", "rev-parse", "--verify", "HEAD"],
        ),
        (
            "manifest",
            repository_path,
            [
                "git",
                "--no-pager",
                "cat-file",
                "blob",
                f"{manifest_commit}:.forge-manifest",
            ],
        ),
        (
            "policy",
            worktree_path,
            [
                "git",
                "--no-pager",
                "cat-file",
                "blob",
                f"{expected_head}:forge-project.md",
            ],
        ),
        (
            "origin",
            worktree_path,
            ["git", "--no-pager", "remote", "get-url", "origin"],
        ),
        (
            "tip",
            worktree_path,
            [
                "git",
                "--no-pager",
                "rev-parse",
                "--verify",
                f"{remote_tip}^{{commit}}",
            ],
        ),
        (
            "diff",
            worktree_path,
            [
                "git",
                "--no-pager",
                "diff",
                "--no-ext-diff",
                "--no-textconv",
                range_value,
                "--",
            ],
        ),
        (
            "names",
            worktree_path,
            [
                "git",
                "--no-pager",
                "diff",
                "--no-ext-diff",
                "--no-textconv",
                "--name-only",
                "-z",
                "--diff-filter=ACDMRTUXB",
                range_value,
                "--",
            ],
        ),
    ]
    if isinstance(state.get("run_binding"), Mapping):
        steps.append(
            (
                "scope",
                worktree_path,
                _merge_scope_argv(worktree_path, remote_tip, expected_head),
            )
        )
    if classify:
        classifier = [
            sys.executable,
            str(runtime.SCRIPT_DIR / "risk_tier.py"),
            "--repo",
            str(worktree_path),
            "--policy-sha",
            expected_head,
            "--range",
            range_value,
        ]
        if declared_tier is not None:
            classifier.extend(["--declared-tier", declared_tier])
        steps.append(("classifier", worktree_path, classifier))
    return tuple(steps)


def _merge_candidate_observation_step_names(
    state: Mapping[str, Any],
    *,
    remote_tip: str,
    expected_head: str,
    classify: bool,
    declared_tier: str | None,
) -> tuple[str, ...] | None:
    specs = _merge_candidate_observation_step_specs(
        state,
        remote_tip=remote_tip,
        expected_head=expected_head,
        classify=classify,
        declared_tier=declared_tier,
    )
    return tuple(name for name, _cwd, _argv in specs) if specs is not None else None


def _merge_candidate_observation_binding(
    state: Mapping[str, Any],
    source_intent: object,
    *,
    verb: str,
    remote_tip: str,
    expected_head: str,
    classify: bool,
    declared_tier: str | None,
) -> str | None:
    candidate = state.get("candidate")
    generation_digest = (
        candidate.get("generation_digest") if isinstance(candidate, Mapping) else None
    )
    if (
        not isinstance(verb, str)
        or not verb
        or COMMIT_RE.fullmatch(remote_tip) is None
        or COMMIT_RE.fullmatch(expected_head) is None
        or type(classify) is not bool
        or (
            declared_tier is not None
            and declared_tier not in TIER_RANK
        )
        or (
            generation_digest is not None
            and SHA256_RE.fullmatch(str(generation_digest)) is None
        )
    ):
        return None
    return sha256_bytes(
        canonical_bytes(
            {
                "schema": "forge-merge-candidate-observation-binding/1",
                "chain_id": state.get("chain_id"),
                "generation_digest": generation_digest,
                "source_intent": copy.deepcopy(source_intent),
                "verb": verb,
                "remote_tip": remote_tip,
                "expected_head": expected_head,
                "classify": classify,
                "declared_tier": declared_tier,
            }
        )
    )


def _merge_candidate_observation_record_valid(
    state: Mapping[str, Any], value: object
) -> bool:
    if not isinstance(value, Mapping):
        return False
    base_keys = {
        "schema",
        "chain_id",
        "generation_digest",
        "source_intent",
        "verb",
        "remote_tip",
        "expected_head",
        "classify",
        "declared_tier",
        "observation_binding",
        "stage",
        "step",
        "cwd",
        "argv",
        "started_at",
    }
    stage = value.get("stage")
    expected_keys = (
        base_keys
        if stage == "intent"
        else {*base_keys, "child_result", "recorded_at"}
        if stage == "result"
        else set()
    )
    candidate = state.get("candidate")
    generation_digest = (
        candidate.get("generation_digest") if isinstance(candidate, Mapping) else None
    )
    binding = _merge_candidate_observation_binding(
        state,
        value.get("source_intent"),
        verb=str(value.get("verb", "")),
        remote_tip=str(value.get("remote_tip", "")),
        expected_head=str(value.get("expected_head", "")),
        classify=value.get("classify") if type(value.get("classify")) is bool else False,
        declared_tier=(
            value.get("declared_tier")
            if isinstance(value.get("declared_tier"), str)
            else None
        ),
    )
    specs = _merge_candidate_observation_step_specs(
        state,
        remote_tip=str(value.get("remote_tip", "")),
        expected_head=str(value.get("expected_head", "")),
        classify=value.get("classify") if type(value.get("classify")) is bool else False,
        declared_tier=(
            value.get("declared_tier")
            if isinstance(value.get("declared_tier"), str)
            else None
        ),
    )
    expected_step = next(
        (
            (str(cwd), argv)
            for name, cwd, argv in (specs or ())
            if name == value.get("step")
        ),
        None,
    )
    if (
        set(value) != expected_keys
        or value.get("schema") != _MERGE_CANDIDATE_OBSERVATION_SCHEMA
        or value.get("chain_id") != state.get("chain_id")
        or value.get("generation_digest") != generation_digest
        or type(value.get("classify")) is not bool
        or (
            value.get("declared_tier") is not None
            and value.get("declared_tier") not in TIER_RANK
        )
        or binding is None
        or value.get("observation_binding") != binding
        or expected_step is None
        or value.get("cwd") != expected_step[0]
        or value.get("argv") != expected_step[1]
        or not isinstance(value.get("step"), str)
        or not value.get("step")
        or not isinstance(value.get("argv"), list)
        or not value.get("argv")
        or not all(isinstance(member, str) and member for member in value["argv"])
        or not _valid_utc_second(value.get("started_at"))
    ):
        return False
    if stage == "intent":
        return True
    child = value.get("child_result")
    if not isinstance(child, Mapping) or set(child) != {
        "authorized",
        "exit",
        "inflight_digest",
        "output_digest",
        "stored_output_digest",
        "output_b64",
        "launch_failed",
        "timed_out",
        "output_limit_exceeded",
        "group_survived",
    }:
        return False
    try:
        output = base64.b64decode(str(child.get("output_b64", "")), validate=True)
    except (ValueError, binascii.Error):
        return False
    return bool(
        type(child.get("authorized")) is bool
        and (child.get("exit") is None or type(child.get("exit")) is int)
        and SHA256_RE.fullmatch(str(child.get("inflight_digest", ""))) is not None
        and SHA256_RE.fullmatch(str(child.get("output_digest", ""))) is not None
        and len(output) <= runtime.OUTPUT_CAP_BYTES
        and SHA256_RE.fullmatch(str(child.get("stored_output_digest", "")))
        is not None
        and sha256_bytes(output) == child.get("stored_output_digest")
        and all(
            type(child.get(name)) is bool
            for name in (
                "launch_failed",
                "timed_out",
                "output_limit_exceeded",
                "group_survived",
            )
        )
        and _valid_utc_second(value.get("recorded_at"))
    )


def _merge_candidate_observation_transition_valid(
    prior: Mapping[str, Any], current: Mapping[str, Any]
) -> bool:
    prior_integration = prior.get("integration")
    current_integration = current.get("integration")
    if not isinstance(prior_integration, Mapping) or not isinstance(
        current_integration, Mapping
    ):
        return False
    prior_intent = prior_integration.get("intent")
    current_intent = current_integration.get("intent")
    if any(
        prior_integration.get(name) != current_integration.get(name)
        for name in (set(prior_integration) | set(current_integration)) - {"intent"}
    ):
        return False
    prior_observation = _merge_candidate_observation_record_valid(
        prior, prior_intent
    )
    current_observation = _merge_candidate_observation_record_valid(
        current, current_intent
    )
    if current_observation:
        assert isinstance(current_intent, Mapping)
        if current_intent.get("stage") == "intent":
            return bool(
                not prior_observation
                and current_intent.get("source_intent") == prior_intent
            )
        if not prior_observation or not isinstance(prior_intent, Mapping):
            return False
        return bool(
            prior_intent.get("stage") == "intent"
            and all(
                prior_intent.get(name) == current_intent.get(name)
                for name in set(prior_intent) - {"stage"}
            )
        )
    return bool(
        prior_observation
        and isinstance(prior_intent, Mapping)
        and prior_intent.get("stage") == "result"
        and current_intent == prior_intent.get("source_intent")
    )


def _merge_candidate_observation_evidence(
    state: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    """Build the pure, digest-bound view of already durable child results."""

    if not records:
        return None
    first = records[0]
    binding = first.get("observation_binding")
    names = _merge_candidate_observation_step_names(
        state,
        remote_tip=str(first.get("remote_tip", "")),
        expected_head=str(first.get("expected_head", "")),
        classify=first.get("classify") if type(first.get("classify")) is bool else False,
        declared_tier=(
            first.get("declared_tier")
            if isinstance(first.get("declared_tier"), str)
            else None
        ),
    )
    if names is None or tuple(record.get("step") for record in records) != names:
        return None
    normalized: list[dict[str, Any]] = []
    for record in records:
        if (
            not _merge_candidate_observation_record_valid(state, record)
            or record.get("stage") != "result"
            or record.get("observation_binding") != binding
            or any(
                record.get(name) != first.get(name)
                for name in (
                    "chain_id",
                    "generation_digest",
                    "source_intent",
                    "verb",
                    "remote_tip",
                    "expected_head",
                    "classify",
                    "declared_tier",
                )
            )
        ):
            return None
        normalized.append(copy.deepcopy(dict(record)))
    evidence: dict[str, Any] = {
        "schema": _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA,
        "chain_id": first.get("chain_id"),
        "generation_digest": first.get("generation_digest"),
        "source_intent": copy.deepcopy(first.get("source_intent")),
        "verb": first.get("verb"),
        "remote_tip": first.get("remote_tip"),
        "expected_head": first.get("expected_head"),
        "classify": first.get("classify"),
        "declared_tier": first.get("declared_tier"),
        "observation_binding": binding,
        "steps": normalized,
    }
    evidence["evidence_digest"] = sha256_bytes(canonical_bytes(evidence))
    return evidence


def _merge_candidate_observation_evidence_valid(
    state: Mapping[str, Any], value: object
) -> bool:
    if not isinstance(value, Mapping) or set(value) != {
        "schema",
        "chain_id",
        "generation_digest",
        "source_intent",
        "verb",
        "remote_tip",
        "expected_head",
        "classify",
        "declared_tier",
        "observation_binding",
        "steps",
        "evidence_digest",
    }:
        return False
    steps = value.get("steps")
    rebuilt = (
        _merge_candidate_observation_evidence(state, steps)
        if isinstance(steps, list)
        and all(isinstance(record, Mapping) for record in steps)
        else None
    )
    return bool(rebuilt is not None and dict(value) == rebuilt)


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
    'validate_state',
]
