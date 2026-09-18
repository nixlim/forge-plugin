"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
from pathlib import Path
from typing import Any, Mapping, Sequence
from forge_cli.engine._core import inspect_common_lock as inspect_common_lock, _write_artifact as _write_artifact, _read_bound_artifact as _read_bound_artifact
from forge_cli import chain_core, runtime
from forge_cli.policy import sha256_bytes, Policy
from forge_cli.envelope import V2ReasonCode, FrozenError, REVISION9_OUTPUT_SCHEMA
import os
import dataclasses


def _merge_run_directory(state: Mapping[str, Any]) -> tuple[Path, Path] | None:
    binding = state.get("run_binding")
    if not isinstance(binding, Mapping):
        return None
    repository = Path(str(binding["repository"]))
    return (
        repository,
        repository
        / ".codex-orchestrator"
        / "runs"
        / str(binding["run_id"]),
    )


def _write_merge_artifact(
    ctx: chain_core.CommandContext,
    state: Mapping[str, Any],
    relative: str,
    data: bytes,
    *,
    master_package: bool = False,
) -> str:
    bound = _merge_run_directory(state)
    if bound is None:
        return _write_artifact(ctx, state, relative, data, exclusive=True)
    repository, run_dir = bound
    chain_core._require_merge_adapter_control("run-relative-evidence")
    return chain_core._capture_ingest_blob(
        repository,
        run_dir,
        digest=sha256_bytes(data),
        name="state.json" if master_package else "events.jsonl",
        data=data,
    )


def _read_merge_artifact(
    ctx: chain_core.CommandContext,
    state: Mapping[str, Any],
    relative: str,
    expected_digest: str,
    label: str,
) -> bytes:
    bound = _merge_run_directory(state)
    parsed = (
        chain_core._parsed_run_captured_path(relative, str(state["run_binding"]["run_id"]))
        if bound is not None
        else None
    )
    if bound is None or parsed is None:
        return _read_bound_artifact(
            ctx, state, relative, expected_digest, label
        )
    repository, run_dir = bound
    data = chain_core._read_ingest_input(
        repository,
        relative,
        "ingest.captured_package",
        run_dir=run_dir,
        expected_capture_name=parsed.name,
    )
    if sha256_bytes(data) != expected_digest:
        raise chain_core._merge_refusal(
            V2ReasonCode.REVIEW_VERDICT_INVALID,
            f"{label} artifact changed after review request",
            expected=expected_digest,
            observed=sha256_bytes(data),
            chain=state,
            evidence_refs=[relative],
        )
    return data


def _merge_gate_suite(
    state: Mapping[str, Any], policy: Policy
) -> tuple[str, ...]:
    chain_core._require_merge_adapter_control("ordered-gate-suite")
    tier = state.get("tier")
    categories = tier.get("categories", []) if isinstance(tier, Mapping) else []
    return (
        "gate-1",
        *(
            f"stack:{category}"
            for category in sorted(
                {str(value) for value in categories},
                key=lambda value: value.encode("utf-8"),
            )
        ),
        *(
            f"invariant:{row['row_number']}"
            for row in sorted(
                policy.invariants,
                key=lambda value: int(value["row_number"]),
            )
            if row["enforcement"] == "merge"
        ),
        "assertion-sensor",
    )


def _merge_gate_current(
    state: Mapping[str, Any], step_id: str
) -> bool:
    candidate = state.get("candidate")
    steps = state.get("steps")
    if not isinstance(candidate, Mapping) or not isinstance(steps, Mapping):
        return False
    return (
        chain_core._merge_current_gate_facts(
            step_id,
            steps.get(step_id),
            str(candidate.get("generation_digest", "")),
        )
        is not None
    )


def _merge_event_digest(
    store: chain_core.MergeChainStore, chain_id: str, event_name: str
) -> str | None:
    """Return a digest only from an authenticated, lease-stable event replay."""

    with store.event_lock(chain_id):
        replay = store._read_replay_locked(chain_id)
    matches = [
        event.get("digest")
        for event in replay.events
        if isinstance(event, dict) and event.get("event") == event_name
    ]
    return str(matches[-1]) if matches and chain_core.SHA256_RE.fullmatch(str(matches[-1])) else None


def _merge_epoch_fetch_observation_digest(
    store: chain_core.MergeChainStore, chain_id: str, evidence: object
) -> str | None:
    """Resolve one raw epoch-fetch fact only from authenticated event replay."""

    if not isinstance(evidence, Mapping):
        return None
    with store.event_lock(chain_id):
        replay = store._read_replay_locked(chain_id)
    matches: list[object] = []
    for index, event in enumerate(replay.events):
        direct_predecessor = bool(
            isinstance(event, Mapping)
            and event.get("previous_digest")
            == evidence.get("fetch_intent_event_digest")
        )
        previous_event = replay.events[index - 1] if index else None
        previous_payload = (
            previous_event.get("payload")
            if isinstance(previous_event, Mapping)
            else None
        )
        recovery_proof = (
            previous_payload.get("recovery_proof")
            if isinstance(previous_payload, Mapping)
            else None
        )
        lifecycle = (
            recovery_proof.get("lifecycle")
            if isinstance(recovery_proof, Mapping)
            else None
        )
        owner_death_predecessor = bool(
            isinstance(event, Mapping)
            and isinstance(previous_event, Mapping)
            and isinstance(lifecycle, Mapping)
            and event.get("previous_digest") == previous_event.get("digest")
            and previous_event.get("previous_digest")
            == evidence.get("fetch_intent_event_digest")
            and lifecycle.get("operation") is None
            and lifecycle.get("intent_digest") is None
            and lifecycle.get("classification") == "owner-death-only"
        )
        if (
            not isinstance(event, Mapping)
            or event.get("event") != "condition_recorded"
            or not (direct_predecessor or owner_death_predecessor)
        ):
            continue
        payload = event.get("payload")
        delta = payload.get("delta") if isinstance(payload, Mapping) else None
        integration = delta.get("integration") if isinstance(delta, Mapping) else None
        if (
            isinstance(integration, Mapping)
            and integration.get("intent") == evidence
        ):
            matches.append(event.get("digest"))
    if len(matches) != 1 or chain_core.SHA256_RE.fullmatch(str(matches[0])) is None:
        return None
    return str(matches[0])


def _merge_inactive(state: Mapping[str, Any]) -> bool:
    try:
        return runtime.utc_now() >= chain_core.parse_time(str(state["inactive_after"]))
    except (KeyError, TypeError, ValueError):
        raise FrozenError(
            "merge inactivity deadline is malformed",
            chain_id=str(state.get("chain_id") or "") or None,
            schema=REVISION9_OUTPUT_SCHEMA,
        )


def _merge_has_attempt(state: Mapping[str, Any]) -> bool:
    integration = state.get("integration")
    push = integration.get("push") if isinstance(integration, Mapping) else None
    attempts = push.get("attempted_heads") if isinstance(push, Mapping) else None
    return isinstance(attempts, list) and bool(attempts)


def _merge_inactive_epoch_has_no_started_child(
    state: Mapping[str, Any], history: Sequence[Mapping[str, Any]]
) -> bool:
    """Recognize the exact epoch-intent cutoff before its first child intent."""

    integration = state.get("integration")
    epoch = integration.get("epoch") if isinstance(integration, Mapping) else None
    if state.get("state") not in {"rebasing", "reverifying"} or not isinstance(
        epoch, Mapping
    ):
        return False
    epoch_index = next(
        (
            index
            for index, member in reversed(tuple(enumerate(history)))
            if member.get("event") == "epoch_intent"
            and member.get("digest") == epoch.get("intent_digest")
        ),
        None,
    )
    if epoch_index is None:
        return False

    def non_child_suffix(member: Mapping[str, Any]) -> bool:
        if member.get("event") in {"journal_receipted", "lock_release_result"}:
            return True
        payload = member.get("payload")
        proof = payload.get("recovery_proof") if isinstance(payload, Mapping) else None
        lifecycle = proof.get("lifecycle") if isinstance(proof, Mapping) else None
        return bool(
            member.get("event") == "condition_recorded"
            and isinstance(payload, Mapping)
            and payload.get("delta") == {}
            and isinstance(lifecycle, Mapping)
            and lifecycle.get("operation") is None
            and lifecycle.get("intent_digest") is None
            and lifecycle.get("classification") == "owner-death-only"
        )

    return all(non_child_suffix(member) for member in history[epoch_index + 1 :])


def _require_active_merge_epoch(state: Mapping[str, Any]) -> None:
    """Forbid every not-yet-admitted epoch child after authority expires."""

    if not _merge_inactive(state):
        return
    chain_id = str(state.get("chain_id") or "") or None
    raise chain_core._merge_refusal(
        V2ReasonCode.STATE_PRECONDITION,
        "forge: merge epoch refused — inactive authority cannot start another child",
        expected="status, observation-only recovery, or safe abort",
        observed=str(state.get("state")),
        remediation=(
            f"forge status --chain-id {chain_id}"
            if chain_id is not None
            else "forge status"
        ),
        chain=state,
    )


def _merge_process_unresolved(
    state: Mapping[str, Any], *, allow_current_abort_lock: bool = False
) -> bool:
    integration = state.get("integration")
    if not isinstance(integration, Mapping):
        return True
    if integration.get("condition") == "foreign-git-state":
        return True
    intent = integration.get("intent")
    if isinstance(intent, Mapping) and any(
        intent.get(name) is True
        for name in ("live", "process_live", "group_survived", "unresolved")
    ):
        return True
    try:
        inspection = inspect_common_lock(Path(str(state["worktree"]["common_dir"])))
    except (KeyError, OSError, ValueError, FrozenError):
        return True
    artifacts = inspection.artifacts or {}
    owns_abort_lock = bool(
        allow_current_abort_lock
        and inspection.topology == "complete"
        and inspection.outer is not None
        and inspection.inner is not None
        and inspection.outer.record.get("owner_kind") == "merge"
        and inspection.outer.record.get("chain_id") == state.get("chain_id")
        and inspection.outer.record.get("operation") == "abort"
        and inspection.outer.record.get("pid") == os.getpid()
    )
    return bool(
        (inspection.topology != "free" and not owns_abort_lock)
        or "inflight" in artifacts
        or inspection.detail
    )


@dataclasses.dataclass
class _MergeEpochBudget:
    fetches: int = 0
    rebases: int = 0
    suites: int = 0
    pushes: int = 0
    pre_observations: int = 0
    post_observations: int = 0

    def consume(self, member: str) -> None:
        chain_core._require_merge_integration_control("bounded-epoch-budget")
        limits = {
            "fetches": 1,
            "rebases": 1,
            "suites": 1,
            "pushes": 1,
            "pre_observations": 1,
            "post_observations": 1,
        }
        if member not in limits:
            raise ValueError(f"unknown merge epoch budget member: {member}")
        value = int(getattr(self, member)) + 1
        if value > limits[member]:
            raise FrozenError(
                f"merge epoch exceeded its {member.replace('_', '-')} budget",
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        setattr(self, member, value)


def _merge_epoch_suite(
    state: Mapping[str, Any], policy: Policy
) -> list[dict[str, str]]:
    ordered = list(_merge_gate_suite(state, policy))
    if not ordered or ordered[0] != "gate-1":
        raise FrozenError(
            "merge Gate 1 is missing from the deterministic epoch suite",
            chain_id=str(state.get("chain_id") or "") or None,
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    suite = [
        {"kind": "gate", "id": "gate-1"},
        {"kind": "scoped-mutation", "id": "scoped-mutation"},
    ]
    for gate_id in ordered[1:]:
        repeats = len(policy.stack_commands) if gate_id.startswith("stack:") else 1
        suite.extend({"kind": "gate", "id": gate_id} for _index in range(repeats))
    return suite


def _remote_observation_intent(
    state: Mapping[str, Any], *, phase: str, push_intent_digest: str | None = None
) -> dict[str, Any]:
    if phase not in {"final-prepush", "post-push"}:
        raise ValueError("remote observation phase is invalid")
    integration = state.get("integration")
    epoch = integration.get("epoch") if isinstance(integration, Mapping) else None
    if not isinstance(epoch, Mapping):
        raise FrozenError(
            "remote observation lacks an active merge epoch",
            chain_id=str(state.get("chain_id") or "") or None,
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    if phase == "final-prepush" and push_intent_digest is not None:
        raise ValueError("final-prepush observation cannot cite push intent")
    if phase == "post-push" and (
        push_intent_digest is None
        or chain_core.SHA256_RE.fullmatch(push_intent_digest) is None
    ):
        raise ValueError("post-push observation requires its exact push intent")
    return {
        "schema": "forge-remote-observation-intent/1",
        "transaction": "merge",
        "chain_id": state["chain_id"],
        "attempt_identity": epoch["intent_digest"],
        "phase": phase,
        "push_intent_digest": push_intent_digest,
    }
