"""Extracted from scripts/forge/forge_cli/chain_core/__init__.py."""
from __future__ import annotations
from forge_cli.chain_core._controls import COMMON_LOCK_OWNER_KINDS as COMMON_LOCK_OWNER_KINDS, COMMON_LOCK_OPERATIONS as COMMON_LOCK_OPERATIONS, COMMON_LOCK_FENCE_OPERATIONS as COMMON_LOCK_FENCE_OPERATIONS, COMMON_LOCK_RECOVERY_KINDS as COMMON_LOCK_RECOVERY_KINDS, _COMMON_LOCK_OWNER_KEYS as _COMMON_LOCK_OWNER_KEYS, _COMMON_LOCK_FENCE_KEYS as _COMMON_LOCK_FENCE_KEYS, _COMMON_LOCK_RECOVERY_KEYS as _COMMON_LOCK_RECOVERY_KEYS, _CHAIN_LEASE_KEYS as _CHAIN_LEASE_KEYS, _REQUIRED_COMMON_LOCK_CONTROLS as _REQUIRED_COMMON_LOCK_CONTROLS, COMMON_LOCK_CONTROLS as COMMON_LOCK_CONTROLS, CHAIN_TOMBSTONE_SCHEMA as CHAIN_TOMBSTONE_SCHEMA, CHAIN_TOMBSTONE_EVENT as CHAIN_TOMBSTONE_EVENT, CHAIN_TOMBSTONE_KEYS as CHAIN_TOMBSTONE_KEYS, _REQUIRED_MERGE_STORE_CONTROLS as _REQUIRED_MERGE_STORE_CONTROLS, MERGE_STORE_CONTROLS as MERGE_STORE_CONTROLS, _REQUIRED_MERGE_ADAPTER_CONTROLS as _REQUIRED_MERGE_ADAPTER_CONTROLS, MERGE_ADAPTER_CONTROLS as MERGE_ADAPTER_CONTROLS, _REQUIRED_MERGE_INTEGRATION_CONTROLS as _REQUIRED_MERGE_INTEGRATION_CONTROLS, MERGE_INTEGRATION_CONTROLS as MERGE_INTEGRATION_CONTROLS, INGEST_PROOF_ORDER as INGEST_PROOF_ORDER, _REQUIRED_INGEST_PROOF_CONTROLS as _REQUIRED_INGEST_PROOF_CONTROLS, INGEST_PROOF_CONTROLS as INGEST_PROOF_CONTROLS, _MERGE_CLEANUP_INTENT_SCHEMA as _MERGE_CLEANUP_INTENT_SCHEMA, _MERGE_CLEANUP_RESULT_SCHEMA as _MERGE_CLEANUP_RESULT_SCHEMA, _MERGE_CLEANUP_CLOSE_SCHEMA as _MERGE_CLEANUP_CLOSE_SCHEMA, _MERGE_CLEANUP_RECOVERY_SCHEMA as _MERGE_CLEANUP_RECOVERY_SCHEMA, _MERGE_CLEANUP_FENCE_OPERATIONS as _MERGE_CLEANUP_FENCE_OPERATIONS, _EPOCH_FETCH_OBSERVATION_SCHEMA as _EPOCH_FETCH_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA, _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA as _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA
from forge_cli.chain_core._core import canonical_bytes as canonical_bytes, _chain_storage_root as _chain_storage_root, _validated_commitment_path as _validated_commitment_path, _parsed_run_captured_path as _parsed_run_captured_path, _require_ingest_proof as _require_ingest_proof, iso_z as iso_z, parse_time as parse_time, _require_merge_store_control as _require_merge_store_control, _require_merge_adapter_control as _require_merge_adapter_control, _require_merge_integration_control as _require_merge_integration_control, _require_common_lock_control as _require_common_lock_control, CommonLockBoundaryCrash as CommonLockBoundaryCrash, PublishedLockRecord as PublishedLockRecord, CommonLockInspection as CommonLockInspection, CommonLockUnavailable as CommonLockUnavailable, CommonLockReleaseFailure as CommonLockReleaseFailure, ChainLeaseUnavailable as ChainLeaseUnavailable, FencedChildSurvived as FencedChildSurvived, _valid_utc_second as _valid_utc_second, _valid_positive_int as _valid_positive_int, _valid_nonnegative_int as _valid_nonnegative_int, _valid_host as _valid_host, _valid_nonce as _valid_nonce, _valid_nullable_chain as _valid_nullable_chain, _write_all as _write_all, _PublicationCleanupFailure as _PublicationCleanupFailure, _process_probe as _process_probe, _group_probe as _group_probe, _sleep_with_deadline as _sleep_with_deadline, _require_deadline_open as _require_deadline_open, FencedProcessResult as FencedProcessResult, merge_gate_intent_digest as merge_gate_intent_digest, _forge_command as _forge_command, MergeRunTaskSnapshot as MergeRunTaskSnapshot, _merge_refusal as _merge_refusal, _valid_sorted_unique_strings as _valid_sorted_unique_strings
from forge_cli.chain_core._state import SCHEMA as SCHEMA, KIND as KIND, FRESH_REVIEWER_EVALS_GATE as FRESH_REVIEWER_EVALS_GATE, FRESH_REVIEWER_EVALS_REQUESTS as FRESH_REVIEWER_EVALS_REQUESTS, FRESH_REVIEWER_EVALS_REQUESTED_EVENT as FRESH_REVIEWER_EVALS_REQUESTED_EVENT, STATES as STATES, STATE_KEYS as STATE_KEYS, EVENT_KEYS as EVENT_KEYS, MERGE_STATE_KEYS as MERGE_STATE_KEYS, _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES as _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES, _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES as _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES, MERGE_EVENT_KEYS as MERGE_EVENT_KEYS, MERGE_EVENT_NAMES as MERGE_EVENT_NAMES, MERGE_CONSEQUENTIAL_EVENTS as MERGE_CONSEQUENTIAL_EVENTS, TIER_RANK as TIER_RANK, INACTIVE_SECONDS as INACTIVE_SECONDS, FENCED_CHILD_ACK_TIMEOUT_SECONDS as FENCED_CHILD_ACK_TIMEOUT_SECONDS, FENCED_CHILD_DRAIN_SECONDS as FENCED_CHILD_DRAIN_SECONDS, FENCED_CHILD_DRAIN_CAP_BYTES as FENCED_CHILD_DRAIN_CAP_BYTES, FENCED_CHILD_STOP_GRACE_SECONDS as FENCED_CHILD_STOP_GRACE_SECONDS, FENCED_CHILD_REAP_SECONDS as FENCED_CHILD_REAP_SECONDS, ZERO_DIGEST as ZERO_DIGEST, COMMON_LOCK_TIMEOUT_SECONDS as COMMON_LOCK_TIMEOUT_SECONDS, COMMON_LOCK_POLL_SECONDS as COMMON_LOCK_POLL_SECONDS, COMMON_LOCK_RECORD_CAP_BYTES as COMMON_LOCK_RECORD_CAP_BYTES, MERGE_SCOPE_BINDING_CAP_BYTES as MERGE_SCOPE_BINDING_CAP_BYTES, COMMON_LOCK_INTENT_NAME as COMMON_LOCK_INTENT_NAME, COMMON_LOCK_DIRECTORY_NAME as COMMON_LOCK_DIRECTORY_NAME, COMMON_LOCK_OWNER_NAME as COMMON_LOCK_OWNER_NAME, COMMON_LOCK_FLOCK_NAME as COMMON_LOCK_FLOCK_NAME, COMMON_LOCK_RECOVERY_NAME as COMMON_LOCK_RECOVERY_NAME, COMMON_LOCK_INFLIGHT_NAME as COMMON_LOCK_INFLIGHT_NAME, CHAIN_ID_RE as CHAIN_ID_RE, SHA256_RE as SHA256_RE, COMMIT_RE as COMMIT_RE, RUN_ID_RE as RUN_ID_RE, _WORKTREE_LOCKS_GUARD as _WORKTREE_LOCKS_GUARD, _WORKTREE_LOCKS as _WORKTREE_LOCKS, _WORKTREE_LOCK_STATE as _WORKTREE_LOCK_STATE, _exclusive_descriptor_lock as _exclusive_descriptor_lock, _MERGE_REMOTE_ONLY_IDENTITY_FIELDS as _MERGE_REMOTE_ONLY_IDENTITY_FIELDS, _MERGE_SCOPE_UNSET as _MERGE_SCOPE_UNSET, _MERGE_SCOPE_OVERLAY as _MERGE_SCOPE_OVERLAY
from typing import Any, Mapping, Sequence


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
