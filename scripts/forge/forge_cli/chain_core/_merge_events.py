"""Extracted from scripts/forge/forge_cli/chain_core/__init__.py."""
from __future__ import annotations
from typing import Any, Mapping
from forge_cli.chain_core._controls import COMMON_LOCK_OWNER_KINDS as COMMON_LOCK_OWNER_KINDS, COMMON_LOCK_OPERATIONS as COMMON_LOCK_OPERATIONS, COMMON_LOCK_FENCE_OPERATIONS as COMMON_LOCK_FENCE_OPERATIONS, COMMON_LOCK_RECOVERY_KINDS as COMMON_LOCK_RECOVERY_KINDS, _COMMON_LOCK_OWNER_KEYS as _COMMON_LOCK_OWNER_KEYS, _COMMON_LOCK_FENCE_KEYS as _COMMON_LOCK_FENCE_KEYS, _COMMON_LOCK_RECOVERY_KEYS as _COMMON_LOCK_RECOVERY_KEYS, _CHAIN_LEASE_KEYS as _CHAIN_LEASE_KEYS, _REQUIRED_COMMON_LOCK_CONTROLS as _REQUIRED_COMMON_LOCK_CONTROLS, COMMON_LOCK_CONTROLS as COMMON_LOCK_CONTROLS, CHAIN_TOMBSTONE_SCHEMA as CHAIN_TOMBSTONE_SCHEMA, CHAIN_TOMBSTONE_EVENT as CHAIN_TOMBSTONE_EVENT, CHAIN_TOMBSTONE_KEYS as CHAIN_TOMBSTONE_KEYS, _REQUIRED_MERGE_STORE_CONTROLS as _REQUIRED_MERGE_STORE_CONTROLS, MERGE_STORE_CONTROLS as MERGE_STORE_CONTROLS, _REQUIRED_MERGE_ADAPTER_CONTROLS as _REQUIRED_MERGE_ADAPTER_CONTROLS, MERGE_ADAPTER_CONTROLS as MERGE_ADAPTER_CONTROLS, _REQUIRED_MERGE_INTEGRATION_CONTROLS as _REQUIRED_MERGE_INTEGRATION_CONTROLS, MERGE_INTEGRATION_CONTROLS as MERGE_INTEGRATION_CONTROLS, INGEST_PROOF_ORDER as INGEST_PROOF_ORDER, _REQUIRED_INGEST_PROOF_CONTROLS as _REQUIRED_INGEST_PROOF_CONTROLS, INGEST_PROOF_CONTROLS as INGEST_PROOF_CONTROLS, _MERGE_CLEANUP_INTENT_SCHEMA as _MERGE_CLEANUP_INTENT_SCHEMA, _MERGE_CLEANUP_RESULT_SCHEMA as _MERGE_CLEANUP_RESULT_SCHEMA, _MERGE_CLEANUP_CLOSE_SCHEMA as _MERGE_CLEANUP_CLOSE_SCHEMA, _MERGE_CLEANUP_RECOVERY_SCHEMA as _MERGE_CLEANUP_RECOVERY_SCHEMA, _MERGE_CLEANUP_FENCE_OPERATIONS as _MERGE_CLEANUP_FENCE_OPERATIONS, _EPOCH_FETCH_OBSERVATION_SCHEMA as _EPOCH_FETCH_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA, _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA as _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA
from forge_cli.chain_core._core import canonical_bytes as canonical_bytes, _chain_storage_root as _chain_storage_root, _validated_commitment_path as _validated_commitment_path, _parsed_run_captured_path as _parsed_run_captured_path, _require_ingest_proof as _require_ingest_proof, iso_z as iso_z, parse_time as parse_time, _require_merge_store_control as _require_merge_store_control, _require_merge_adapter_control as _require_merge_adapter_control, _require_merge_integration_control as _require_merge_integration_control, _require_common_lock_control as _require_common_lock_control, CommonLockBoundaryCrash as CommonLockBoundaryCrash, PublishedLockRecord as PublishedLockRecord, CommonLockInspection as CommonLockInspection, CommonLockUnavailable as CommonLockUnavailable, CommonLockReleaseFailure as CommonLockReleaseFailure, ChainLeaseUnavailable as ChainLeaseUnavailable, FencedChildSurvived as FencedChildSurvived, _valid_utc_second as _valid_utc_second, _valid_positive_int as _valid_positive_int, _valid_nonnegative_int as _valid_nonnegative_int, _valid_host as _valid_host, _valid_nonce as _valid_nonce, _valid_nullable_chain as _valid_nullable_chain, _write_all as _write_all, _PublicationCleanupFailure as _PublicationCleanupFailure, _process_probe as _process_probe, _group_probe as _group_probe, _sleep_with_deadline as _sleep_with_deadline, _require_deadline_open as _require_deadline_open, FencedProcessResult as FencedProcessResult, merge_gate_intent_digest as merge_gate_intent_digest, _forge_command as _forge_command, MergeRunTaskSnapshot as MergeRunTaskSnapshot, _merge_refusal as _merge_refusal, _valid_sorted_unique_strings as _valid_sorted_unique_strings
from forge_cli.chain_core._state import SCHEMA as SCHEMA, KIND as KIND, FRESH_REVIEWER_EVALS_GATE as FRESH_REVIEWER_EVALS_GATE, FRESH_REVIEWER_EVALS_REQUESTS as FRESH_REVIEWER_EVALS_REQUESTS, FRESH_REVIEWER_EVALS_REQUESTED_EVENT as FRESH_REVIEWER_EVALS_REQUESTED_EVENT, STATES as STATES, STATE_KEYS as STATE_KEYS, EVENT_KEYS as EVENT_KEYS, MERGE_STATE_KEYS as MERGE_STATE_KEYS, _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES as _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES, _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES as _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES, MERGE_EVENT_KEYS as MERGE_EVENT_KEYS, MERGE_EVENT_NAMES as MERGE_EVENT_NAMES, MERGE_CONSEQUENTIAL_EVENTS as MERGE_CONSEQUENTIAL_EVENTS, TIER_RANK as TIER_RANK, INACTIVE_SECONDS as INACTIVE_SECONDS, FENCED_CHILD_ACK_TIMEOUT_SECONDS as FENCED_CHILD_ACK_TIMEOUT_SECONDS, FENCED_CHILD_DRAIN_SECONDS as FENCED_CHILD_DRAIN_SECONDS, FENCED_CHILD_DRAIN_CAP_BYTES as FENCED_CHILD_DRAIN_CAP_BYTES, FENCED_CHILD_STOP_GRACE_SECONDS as FENCED_CHILD_STOP_GRACE_SECONDS, FENCED_CHILD_REAP_SECONDS as FENCED_CHILD_REAP_SECONDS, ZERO_DIGEST as ZERO_DIGEST, COMMON_LOCK_TIMEOUT_SECONDS as COMMON_LOCK_TIMEOUT_SECONDS, COMMON_LOCK_POLL_SECONDS as COMMON_LOCK_POLL_SECONDS, COMMON_LOCK_RECORD_CAP_BYTES as COMMON_LOCK_RECORD_CAP_BYTES, MERGE_SCOPE_BINDING_CAP_BYTES as MERGE_SCOPE_BINDING_CAP_BYTES, COMMON_LOCK_INTENT_NAME as COMMON_LOCK_INTENT_NAME, COMMON_LOCK_DIRECTORY_NAME as COMMON_LOCK_DIRECTORY_NAME, COMMON_LOCK_OWNER_NAME as COMMON_LOCK_OWNER_NAME, COMMON_LOCK_FLOCK_NAME as COMMON_LOCK_FLOCK_NAME, COMMON_LOCK_RECOVERY_NAME as COMMON_LOCK_RECOVERY_NAME, COMMON_LOCK_INFLIGHT_NAME as COMMON_LOCK_INFLIGHT_NAME, CHAIN_ID_RE as CHAIN_ID_RE, SHA256_RE as SHA256_RE, COMMIT_RE as COMMIT_RE, RUN_ID_RE as RUN_ID_RE, _WORKTREE_LOCKS_GUARD as _WORKTREE_LOCKS_GUARD, _WORKTREE_LOCKS as _WORKTREE_LOCKS, _WORKTREE_LOCK_STATE as _WORKTREE_LOCK_STATE, _exclusive_descriptor_lock as _exclusive_descriptor_lock, _MERGE_REMOTE_ONLY_IDENTITY_FIELDS as _MERGE_REMOTE_ONLY_IDENTITY_FIELDS, _MERGE_SCOPE_UNSET as _MERGE_SCOPE_UNSET, _MERGE_SCOPE_OVERLAY as _MERGE_SCOPE_OVERLAY
import copy
import datetime as dt
from forge_cli import runtime


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
