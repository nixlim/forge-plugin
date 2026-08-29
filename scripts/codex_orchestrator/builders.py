from __future__ import annotations

import copy
import datetime as dt
import fcntl
import json
import math
import os
import re
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterable, Iterator, Sequence

from . import batch, journal
from .chain_paths import chain_storage_root

# ``journal`` installs the sibling ``scripts/forge`` directory before this
# import, including dynamic archive/CLI load orders used by installed surfaces.
from commitment_paths import (  # noqa: E402
    commitment_surface,
    parse_run_captured_path,
    validate_surface_path,
)


BUILDER_VALIDATION_CONTROLS = frozenset(
    {"derived-fields", "relations", "binding-replay"}
)
_INGEST_PROOF_ORDER = (
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
_REQUIRED_INGEST_PROOFS = frozenset(_INGEST_PROOF_ORDER)
INGEST_PROOF_CONTROLS = _REQUIRED_INGEST_PROOFS
INGEST_PROOF_INVALID = "forge: journal ingest refused — chain proof is invalid"
_INGEST_CAPTURE_CITATION_PREFIX = (
    "forge: journal append refused — record cites path outside run or repository: "
    "ingest.captured_package: "
)
TERMINAL_CHAIN_CONTROLS = frozenset(
    {"enumeration", "lock", "binding", "replay", "outbox", "landing"}
)
TERMINAL_CHAIN_INVALID = (
    "forge: journal builder refused — bound chain proof is invalid"
)
JOURNAL_OUTBOX_PENDING = (
    "forge: journal builder refused — bound chain journal outbox is pending"
)
RUN_CLOSE_VALIDATION_REFUSAL = (
    "forge: journal builder refused — passing run validation failed"
)

# DM-014 events are deltas, not the full-state snapshots carried by DM-012.
# The merge engine must install its own authoritative reducer before a merge
# binding can be resolved.  Treating an optional ``payload.state`` member as
# authority would admit a digest-valid, entirely invented history.
MergeTransitionReducer = Callable[
    [dict[str, object] | None, dict[str, object]], dict[str, object]
]
MERGE_TRANSITION_REDUCER: MergeTransitionReducer | None = None

# Task-04 owns capture plus the ordered FR-210 retrospective proof.  The
# shared builder accepts its derived rows only from one registered verifier;
# the public ``records`` sequence remains equality-checked engine plumbing and
# can never confer authority by itself.
IngestProofVerifier = Callable[
    [Path, str, dict[str, object]],
    tuple[Sequence[dict[str, object]], tuple[str, ...]],
]
_INGEST_PROOF_VERIFIER: IngestProofVerifier | None = None


def register_merge_transition_reducer(reducer: MergeTransitionReducer) -> None:
    """Install task-04's authoritative DM-014 delta reducer exactly once."""

    global MERGE_TRANSITION_REDUCER
    if not callable(reducer) or (
        MERGE_TRANSITION_REDUCER is not None
        and MERGE_TRANSITION_REDUCER is not reducer
    ):
        raise RuntimeError("merge transition reducer registration conflict")
    MERGE_TRANSITION_REDUCER = reducer


def _register_ingest_proof_verifier(verifier: IngestProofVerifier) -> None:
    """Install task-04's proof-complete ingest verifier exactly once."""

    global _INGEST_PROOF_VERIFIER
    if not callable(verifier) or (
        _INGEST_PROOF_VERIFIER is not None
        and _INGEST_PROOF_VERIFIER is not verifier
    ):
        raise RuntimeError("ingest proof verifier registration conflict")
    _INGEST_PROOF_VERIFIER = verifier

_COMMIT_EVENT_NAMES = frozenset(
    {
        "authorization_consumed",
        "authorized",
        "candidate_invalidated",
        "candidate_restaged",
        "candidate_staged",
        "chain_aborted",
        "chain_closed",
        "chain_started",
        "classified",
        "commit_close_recovered",
        "commit_intent",
        "commit_intent_rolled_back",
        "commit_produced",
        "finding_dispositioned",
        "gate_1_pair_voided",
        "head_moved",
        "head_rebased",
        "iteration_cap",
        "journal_receipted",
        "mechanical_verification_complete",
        "mutating_gate_restaged",
        "operator_approved",
        "operator_skip",
        "policy_changed",
        "retained_review_reauthorized",
        "review_blocked",
        "review_passed",
        "review_requested",
        "secret_scan_recorded",
        "step_recorded",
    }
)
_MERGE_EVENT_NAMES = frozenset(
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
_MERGE_BOOTSTRAP_EVENTS = frozenset(
    {
        "chain_started",
        "ownership_intent",
        "ownership_claimed",
        "fetch_intent",
        "fetch_result",
        "condition_recorded",
        "lock_release_result",
        "ownership_release_intent",
        "ownership_released",
        "aborted",
    }
)
_COMMIT_STATES = frozenset(
    {
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
)
_COMMIT_STATE_TRANSITIONS = {
    "classifying": frozenset({"classifying", "verifying", "aborted"}),
    "verifying": frozenset(
        {"verifying", "classifying", "reviewing", "authorized", "aborted"}
    ),
    "reviewing": frozenset(
        {
            "reviewing",
            "classifying",
            "revising",
            "awaiting_approval",
            "authorized",
            "aborted",
        }
    ),
    "revising": frozenset({"revising", "classifying", "aborted"}),
    "awaiting_approval": frozenset(
        {"awaiting_approval", "classifying", "authorized", "aborted"}
    ),
    "authorized": frozenset(
        {"authorized", "classifying", "committing", "aborted"}
    ),
    "committing": frozenset({"committing", "authorized", "closed"}),
    # A receipted landing acknowledgement is the sole terminal self-event.
    "closed": frozenset({"closed", "aborted"}),
    "aborted": frozenset({"aborted"}),
}
_COMMIT_STATE_KEYS = frozenset(
    {
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
)
_MERGE_STATE_KEYS = frozenset(
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
_MERGE_STATES = frozenset(
    {
        "classifying",
        "verifying",
        "reviewing",
        "revising",
        "awaiting_approval",
        "authorized",
        "rebasing",
        "rebase_conflict",
        "reverifying",
        "reverification_failed",
        "pushing",
        "pushed",
        "cleanup_pending",
        "closed",
        "aborted",
    }
)
_MERGE_NONTERMINAL_STATES = _MERGE_STATES - {"closed", "aborted"}
_MERGE_MUTABLE_PREPUSH_STATES = frozenset(
    {
        "classifying",
        "verifying",
        "reviewing",
        "revising",
        "awaiting_approval",
        "authorized",
    }
)
_MERGE_DERIVED_STATE_FIELDS = frozenset(
    {"last_event_at", "inactive_after", "journal_outbox"}
)
_MERGE_INITIAL_DELTA_FIELDS = _MERGE_STATE_KEYS - _MERGE_DERIVED_STATE_FIELDS
_MERGE_EVENT_TOP_LEVEL_CHANGES: dict[str, frozenset[str]] = {
    "chain_started": _MERGE_INITIAL_DELTA_FIELDS,
    "ownership_intent": frozenset({"worktree"}),
    "ownership_claimed": frozenset({"worktree"}),
    "ownership_release_intent": frozenset({"worktree"}),
    "ownership_released": frozenset({"worktree"}),
    "gate_recorded": frozenset({"state", "steps"}),
    "review_requested": frozenset({"review"}),
    "review_attached": frozenset(
        {"state", "review", "approval", "authorization"}
    ),
    "review_disposition": frozenset({"review"}),
    "approval_recorded": frozenset(
        {"state", "review", "approval", "authorization", "integration"}
    ),
    "generation_refreshed": frozenset(
        {
            "state",
            "policy_source",
            "candidate",
            "tier",
            "steps",
            "review",
            "approval",
            "authorization",
            "integration",
        }
    ),
    "generation_carried_forward": frozenset(
        {"state", "candidate", "steps", "integration"}
    ),
    "epoch_intent": frozenset({"state", "integration"}),
    "fetch_intent": frozenset({"state", "integration"}),
    "fetch_result": frozenset(
        {
            "state",
            "policy_source",
            "candidate",
            "tier",
            "steps",
            "review",
            "approval",
            "authorization",
            "integration",
        }
    ),
    "rebase_intent": frozenset({"state", "integration"}),
    "rebase_conflict": frozenset({"state", "integration"}),
    "rebase_result": frozenset(
        {
            "state",
            "policy_source",
            "candidate",
            "tier",
            "steps",
            "review",
            "approval",
            "authorization",
            "integration",
        }
    ),
    "reverification_result": frozenset(
        {"state", "steps", "review", "approval", "authorization", "integration"}
    ),
    "push_intent": frozenset({"state", "integration", "authorization"}),
    "push_observed": frozenset({"state", "integration"}),
    "cleanup_intent": frozenset({"state", "cleanup"}),
    "cleanup_result": frozenset({"state", "cleanup"}),
    "condition_recorded": frozenset({"state", "integration", "authorization"}),
    "lock_release_result": frozenset({"state", "integration"}),
    "aborted": frozenset({"state"}),
    "closed": frozenset({"state"}),
    "journal_receipted": frozenset({"journal_outbox"}),
}
_MERGE_OUTBOX_PRODUCERS = frozenset(
    {
        "gate_recorded",
        "review_attached",
        "approval_recorded",
        "generation_carried_forward",
        "push_observed",
    }
)
_MERGE_EVENT_EVIDENCE_FIELDS: dict[str, frozenset[str]] = {
    "ownership_intent": frozenset(
        {
            "worktree_digest",
            "claim_path",
            "intended_claim_digest",
            "predecessor_chain_id",
            "predecessor_release_digest",
        }
    ),
    "ownership_claimed": frozenset(
        {
            "ownership_intent_digest",
            "claim_inode",
            "claim_digest",
            "predecessor_chain_id",
            "predecessor_release_digest",
        }
    ),
    "ownership_release_intent": frozenset(
        {
            "target_terminal",
            "terminal_disposition",
            "source_state",
            "terminal_preconditions_digest",
            "release_mode",
        }
    ),
    "ownership_released": frozenset(
        {
            "release_intent_digest",
            "release_mode",
            "terminal_disposition",
            "claim_inode",
            "claim_digest",
            "claim_observation_digest",
        }
    ),
}
_MERGE_BOOTSTRAP_FETCH_EVIDENCE_FIELDS = frozenset(
    {
        "repository",
        "worktree",
        "branch",
        "target",
        "pre_fetch_head",
        "policy_digest",
        "operation_nonce",
        "attempt",
    }
)
_MERGE_QUARANTINE_EVIDENCE_FIELDS = frozenset(
    {"condition", "quarantine", "observation_digest"}
)
_MERGE_HISTORICAL_ABORT_EVIDENCE_FIELDS = frozenset(
    {
        "terminal_disposition",
        "landed_head",
        "superseded_head",
        "observation_digest",
    }
)
_MERGE_REMOTE_OBSERVATION_INTENT_FIELDS = frozenset(
    {
        "schema",
        "transaction",
        "chain_id",
        "attempt_identity",
        "phase",
        "push_intent_digest",
    }
)
_MERGE_EVENT_REQUIRED_CHANGES: dict[str, frozenset[str]] = {
    "ownership_intent": frozenset({"worktree"}),
    "ownership_claimed": frozenset({"worktree"}),
    "ownership_release_intent": frozenset({"worktree"}),
    "ownership_released": frozenset({"worktree"}),
    "gate_recorded": frozenset({"steps"}),
    "review_requested": frozenset({"review"}),
    "review_attached": frozenset({"review"}),
    "review_disposition": frozenset({"review"}),
    "approval_recorded": frozenset({"approval"}),
    "generation_refreshed": frozenset({"integration"}),
    "generation_carried_forward": frozenset({"candidate", "integration"}),
    "epoch_intent": frozenset({"integration"}),
    "fetch_intent": frozenset({"integration"}),
    "fetch_result": frozenset({"integration"}),
    "rebase_intent": frozenset({"integration"}),
    "rebase_conflict": frozenset({"state", "integration"}),
    "rebase_result": frozenset({"integration"}),
    "reverification_result": frozenset({"steps", "integration"}),
    "push_intent": frozenset({"state", "integration"}),
    "push_observed": frozenset({"integration"}),
    "cleanup_intent": frozenset({"cleanup"}),
    "cleanup_result": frozenset({"cleanup"}),
    "condition_recorded": frozenset(),
    "lock_release_result": frozenset({"integration"}),
    "aborted": frozenset({"state"}),
    "closed": frozenset({"state"}),
}
_COMMIT_EVENT_TOP_LEVEL_CHANGES: dict[str, frozenset[str]] = {
    "authorization_consumed": frozenset({"authorization"}),
    "authorized": frozenset({"state", "authorization"}),
    "candidate_invalidated": frozenset(
        {
            "state",
            "paths",
            "staging",
            "candidate",
            "steps",
            "review",
            "approval",
            "authorization",
            "commit_result",
        }
    ),
    "candidate_restaged": frozenset(
        {
            "state",
            "paths",
            "staging",
            "candidate",
            "steps",
            "review",
            "approval",
            "authorization",
            "commit_result",
        }
    ),
    "candidate_staged": frozenset({"paths", "staging", "candidate"}),
    "chain_aborted": frozenset({"state", "commit_result"}),
    "chain_closed": frozenset({"state", "commit_result"}),
    "chain_started": frozenset(_COMMIT_STATE_KEYS),
    "classified": frozenset({"state", "staging", "tier", "steps"}),
    "commit_close_recovered": frozenset(
        {"state", "repo_head", "authorization", "commit_result"}
    ),
    "commit_intent": frozenset({"state", "commit_result"}),
    "commit_intent_rolled_back": frozenset({"state", "commit_result"}),
    "commit_produced": frozenset({"repo_head", "commit_result"}),
    "finding_dispositioned": frozenset({"review"}),
    "gate_1_pair_voided": frozenset({"steps"}),
    "head_moved": frozenset({"steps"}),
    "head_rebased": frozenset(
        {
            "state",
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
        }
    ),
    "iteration_cap": frozenset({"review"}),
    "journal_receipted": frozenset(),
    "mechanical_verification_complete": frozenset({"state"}),
    "mutating_gate_restaged": frozenset(
        {
            "state",
            "paths",
            "staging",
            "candidate",
            "steps",
            "review",
            "approval",
            "authorization",
            "commit_result",
        }
    ),
    "operator_approved": frozenset({"state", "approval", "authorization"}),
    "operator_skip": frozenset(
        {"state", "steps", "review", "approval", "authorization"}
    ),
    "policy_changed": frozenset({"state", "commit_result"}),
    "retained_review_reauthorized": frozenset(
        {"state", "approval", "authorization"}
    ),
    "review_blocked": frozenset({"state", "review"}),
    "review_passed": frozenset(
        {"state", "review", "approval", "authorization"}
    ),
    "review_requested": frozenset({"review"}),
    "secret_scan_recorded": frozenset({"steps"}),
    "step_recorded": frozenset({"steps"}),
}
_COMMIT_DETAIL_KEYS: dict[str, frozenset[str]] = {
    "authorization_consumed": frozenset({"candidate"}),
    "authorized": frozenset({"candidate", "tier"}),
    "candidate_invalidated": frozenset(
        {
            "old_candidate",
            "new_candidate",
            "old_paths",
            "new_paths",
            "out_of_band",
            "detected_by",
        }
    ),
    "candidate_restaged": frozenset({"old_candidate", "new_candidate", "paths"}),
    "candidate_staged": frozenset({"candidate", "paths"}),
    "chain_aborted": frozenset({"reason"}),
    "chain_closed": frozenset({"commit_sha"}),
    "chain_started": frozenset({"paths"}),
    "classified": frozenset({"effective_tier", "control"}),
    "commit_close_recovered": frozenset({"commit_sha", "candidate"}),
    "commit_intent": frozenset({"candidate", "pre_head"}),
    "commit_intent_rolled_back": frozenset({"pre_head", "candidate"}),
    "commit_produced": frozenset({"commit_sha", "candidate"}),
    "finding_dispositioned": frozenset(
        {"finding", "severity", "operator_cosign"}
    ),
    "gate_1_pair_voided": frozenset({"reason", "fingerprints"}),
    "head_moved": frozenset({"old", "new", "diagnostic"}),
    "head_rebased": frozenset(
        {
            "old_head",
            "new_head",
            "old_candidate",
            "new_candidate",
            "candidate_unchanged",
            "diagnostic",
        }
    ),
    "iteration_cap": frozenset({"iteration"}),
    "journal_receipted": frozenset(
        {"idempotency_key", "batch_digest", "receipt_digest"}
    ),
    "mechanical_verification_complete": frozenset(
        {"candidate", "retained_review"}
    ),
    "mutating_gate_restaged": frozenset(
        {"gate_id", "old_candidate", "new_candidate", "outputs"}
    ),
    "operator_approved": frozenset({"candidate", "directed_by"}),
    "operator_skip": frozenset({"gate_id", "directed_by", "reason"}),
    "policy_changed": frozenset(
        {"old_digest", "new_digest", "old_head", "new_head"}
    ),
    "retained_review_reauthorized": frozenset(
        {"candidate", "retained_review"}
    ),
    "review_blocked": frozenset({"iteration", "finding_count"}),
    "review_passed": frozenset({"candidate", "awaiting_approval"}),
    "review_requested": frozenset(
        {"candidate", "package_digest", "reviewer", "iteration"}
    ),
    "secret_scan_recorded": frozenset({"result", "finding_count"}),
    "step_recorded": frozenset({"step_id", "result", "run"}),
}


def _require_text(name: str, value: object, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value:
        raise journal.CoordinationRefusal(
            f"{journal.INVALID_JOURNAL_RECORD}: {name} must be a nonempty string"
        )
    return value


def _caller_text(
    kind: str, field: str, value: object, *, optional: bool = False
) -> None:
    if value is None and optional:
        return
    if not isinstance(value, str):
        journal._invalid_record_field(kind, field, "must be a string")
    if not value:
        journal._invalid_record_field(kind, field, "must be nonempty")


def _caller_array(
    kind: str, field: str, values: object, *, nonempty: bool = False
) -> None:
    if not isinstance(values, (list, tuple)):
        journal._invalid_record_field(kind, field, "must be an array")
    if nonempty and not values:
        journal._invalid_record_field(kind, field, "must be nonempty")
    for index, value in enumerate(values):
        if not isinstance(value, str) or not value:
            journal._invalid_record_field(
                kind, f"{field}[{index}]", "must be a nonempty string"
            )


def _no_citations(_repository: Path, _run_dir: Path) -> None:
    """Explicit fail-closed phase callback for records with no FR-017 surface."""


def _validate_citation_record(
    repository: Path,
    run_dir: Path,
    record: dict[str, object],
) -> None:
    journal._validate_append_citations(repository, run_dir, record)


def _git_lines(repository: Path, *arguments: str) -> list[str]:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository), *arguments],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise journal.CoordinationRefusal(
            "forge: journal builder refused — repository facts unavailable"
        ) from exc
    if completed.returncode != 0:
        raise journal.CoordinationRefusal(
            "forge: journal builder refused — repository facts unavailable"
        )
    return completed.stdout.splitlines()


def _git_one(repository: Path, *arguments: str) -> str:
    lines = _git_lines(repository, *arguments)
    if len(lines) != 1 or not lines[0]:
        raise journal.CoordinationRefusal(
            "forge: journal builder refused — repository facts unavailable"
        )
    return lines[0]


def _with_derived(record: dict[str, object], run_id: str) -> dict[str, object]:
    if "derived-fields" not in BUILDER_VALIDATION_CONTROLS:
        return record
    return {
        **record,
        "run_id": run_id,
        "recorded_at": journal._utc_now(),
    }


def _latest_task(
    state: journal.RunState, task_id: str
) -> dict[str, object] | None:
    for record in reversed(state.records):
        if record.get("type") == "task" and record.get("id") == task_id:
            return record
    return None


def _require_active_task(state: journal.RunState, task_id: str) -> dict[str, object]:
    task = _latest_task(state, task_id)
    if task is None or task.get("status") != "active":
        raise journal.CoordinationRefusal(
            f"forge: journal builder refused — task {task_id} is not active"
        )
    return task


def _allocate_id(
    records: Iterable[dict[str, object]], kind: str
) -> str:
    field = "execution" if kind == "execution" else "id"
    highest = 0
    prefix = {
        "execution": "execution-",
        "verification": "check-",
        "decision": "decision-",
    }[kind]
    for record in records:
        if record.get("type") != kind:
            continue
        value = record.get(field)
        if not isinstance(value, str) or not value.startswith(prefix):
            continue
        suffix = value[len(prefix) :]
        if suffix.isdigit():
            highest = max(highest, int(suffix))
    return f"{prefix}{highest + 1:02d}"


def _require_new_chain_binding(
    state: journal.RunState, chain_id: str, binding_id: str
) -> None:
    """Refuse a fresh transaction that would replay an existing binding row."""

    for record in state.records:
        binding = record.get("binding")
        source = (
            binding.get("source_record") if isinstance(binding, dict) else None
        )
        if (
            isinstance(source, dict)
            and source.get("chain_id") == chain_id
            and binding.get("binding_id") == binding_id
        ):
            raise journal.CoordinationRefusal(journal.DUPLICATE_CHAIN_BINDING)


def _chain_paths(repository: Path, chain_id: str) -> tuple[Path, Path]:
    if (
        not isinstance(chain_id, str)
        or journal.CHAIN_ID_PATTERN.fullmatch(chain_id) is None
    ):
        raise journal.CoordinationRefusal(
            f"{journal.INVALID_JOURNAL_RECORD}: binding source chain is invalid"
        )
    root = chain_storage_root(repository)
    return root / f"{chain_id}.json", root / f"{chain_id}.events.jsonl"


def _read_regular_bytes_at(root_descriptor: int, name: str) -> bytes:
    descriptor: int | None = None
    try:
        before = os.stat(name, dir_fd=root_descriptor, follow_symlinks=False)
        if not journal._batch_regular_stat_valid(before):
            raise ValueError
        descriptor = os.open(
            name,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=root_descriptor,
        )
        opened = os.fstat(descriptor)
        if journal._file_observation(opened) != journal._file_observation(before):
            raise ValueError
        raw = journal._read_descriptor(descriptor)
        after = os.fstat(descriptor)
        rebound = os.stat(name, dir_fd=root_descriptor, follow_symlinks=False)
        if (
            journal._file_observation(after) != journal._file_observation(before)
            or journal._file_observation(rebound)
            != journal._file_observation(before)
            or after.st_size != before.st_size
            or len(raw) != before.st_size
        ):
            raise ValueError
        return raw
    except (OSError, ValueError) as exc:
        raise _binding_replay_refusal() from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _read_json_at(root_descriptor: int, name: str) -> object:
    try:
        return json.loads(_read_regular_bytes_at(root_descriptor, name).decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise _binding_replay_refusal() from exc


def _binding_replay_refusal() -> journal.CoordinationRefusal:
    return journal.CoordinationRefusal(
        f"{journal.INVALID_JOURNAL_RECORD}: binding chain replay failed"
    )


def _utc_value(value: object) -> dt.datetime | None:
    if not isinstance(value, str) or not journal._valid_utc(value):
        return None
    try:
        return dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return None


def _run_binding_valid(value: object) -> bool:
    if value is None:
        return True
    return bool(
        isinstance(value, dict)
        and set(value) == {"run_id", "task_id", "repository", "policy_digest"}
        and isinstance(value.get("run_id"), str)
        and bool(value["run_id"])
        and isinstance(value.get("task_id"), str)
        and bool(value["task_id"])
        and isinstance(value.get("repository"), str)
        and Path(str(value["repository"])).is_absolute()
        and isinstance(value.get("policy_digest"), str)
        and journal.HEX_SHA256_PATTERN.fullmatch(str(value["policy_digest"]))
        is not None
    )


def _outbox_valid(value: object) -> bool:
    if value is None:
        return True
    if not isinstance(value, dict) or set(value) != {
        "idempotency_key",
        "batch_digest",
        "record_count",
        "source_event_digest",
    }:
        return False
    return bool(
        isinstance(value.get("idempotency_key"), str)
        and journal.HEX_SHA256_PATTERN.fullmatch(str(value["idempotency_key"]))
        is not None
        and isinstance(value.get("batch_digest"), str)
        and journal.HEX_SHA256_PATTERN.fullmatch(str(value["batch_digest"]))
        is not None
        and type(value.get("record_count")) is int
        and int(value["record_count"]) > 0
        and value.get("source_event_digest") == value.get("idempotency_key")
    )


def _merge_observation_shape_valid(
    observed: object, attempted_heads: Sequence[str]
) -> bool:
    if not isinstance(observed, dict) or set(observed) != {
        "exists",
        "oid",
        "contains_intended_head",
        "attempted_head_containment",
        "observed_at",
        "inflight_digest",
        "output_digest",
    }:
        return False
    vector = observed.get("attempted_head_containment")
    if (
        observed.get("exists") not in {True, False, None}
        or observed.get("contains_intended_head") not in {True, False, None}
        or _utc_value(observed.get("observed_at")) is None
        or not _merge_hex(observed.get("inflight_digest"))
        or not _merge_hex(observed.get("output_digest"))
        or not isinstance(vector, list)
        or len(vector) != len(attempted_heads)
        or any(
            not isinstance(item, dict)
            or set(item) != {"head", "contained"}
            or item.get("head") != head
            or item.get("contained") not in {True, False, None}
            for item, head in zip(vector, attempted_heads, strict=True)
        )
    ):
        return False
    exists = observed.get("exists")
    oid = observed.get("oid")
    contains = observed.get("contains_intended_head")
    vector_values = [
        item.get("contained") for item in vector if isinstance(item, dict)
    ]
    if exists is True:
        if (
            not isinstance(oid, str)
            or journal.GIT_OBJECT_ID_PATTERN.fullmatch(oid) is None
            or type(contains) is not bool
            or any(type(value) is not bool for value in vector_values)
        ):
            return False
    elif exists is False:
        if (
            oid is not None
            or contains is not False
            or any(value is not False for value in vector_values)
        ):
            return False
    elif (
        oid is not None
        or contains is not None
        or any(value is not None for value in vector_values)
    ):
        return False
    return not vector_values or contains == vector_values[-1]


def _merge_nested_state_valid(state: dict[str, object]) -> bool:
    worktree = _merge_worktree_claim(state)
    branch = state.get("branch")
    target = state.get("target")
    policy = state.get("policy_source")
    integration = state.get("integration")
    cleanup = state.get("cleanup")
    if (
        state.get("state") not in _MERGE_STATES
        or worktree is None
        or not isinstance(state.get("owner"), dict)
        or not isinstance(branch, str)
        or not branch.startswith("refs/heads/")
        or not isinstance(target, dict)
        or set(target) != {"remote", "destination_ref", "manifest_commit"}
        or target.get("remote") != "origin"
        or not isinstance(target.get("destination_ref"), str)
        or not str(target["destination_ref"]).startswith("refs/heads/")
        or not isinstance(target.get("manifest_commit"), str)
        or journal.GIT_OBJECT_ID_PATTERN.fullmatch(str(target["manifest_commit"]))
        is None
        or not isinstance(policy, dict)
        or set(policy) != {"commit", "digest"}
        or not isinstance(policy.get("commit"), str)
        or journal.GIT_OBJECT_ID_PATTERN.fullmatch(str(policy["commit"])) is None
        or not _merge_hex(policy.get("digest"))
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
        or integration.get("condition")
        not in {
            "none",
            "fetch-failed",
            "rebase-failed",
            "remote-moved",
            "remote-churn",
            "push-failed",
            "non-fast-forward",
            "push-outcome-unknown",
            "lock-release-failed",
            "foreign-git-state",
        }
        or type(integration.get("remote_movement_count")) is not int
        or int(integration["remote_movement_count"]) < 0
        or not isinstance(cleanup, dict)
        or cleanup.get("condition") not in {"none", "cleanup-failed"}
    ):
        return False
    primary = integration.get("primary_condition")
    if (
        integration.get("condition") == "lock-release-failed"
        and primary
        not in {
            "none",
            "fetch-failed",
            "rebase-failed",
            "remote-moved",
            "remote-churn",
            "push-failed",
            "non-fast-forward",
            "push-outcome-unknown",
            "foreign-git-state",
        }
    ) or (
        integration.get("condition") != "lock-release-failed"
        and primary != "none"
    ):
        return False
    if not _merge_condition_state_coherent(state):
        return False

    generation = _merge_generation(state.get("candidate"))
    if state.get("candidate") is None:
        if (
            state.get("tier") is not None
            or state.get("steps") != {}
            or state.get("review") != {}
            or state.get("approval") != {}
            or state.get("authorization") != {}
        ):
            return False
    else:
        tier = state.get("tier")
        if (
            generation is None
            or not isinstance(tier, dict)
            or set(tier) != {"control", "categories"}
            or type(tier.get("control")) is not bool
            or not isinstance(tier.get("categories"), list)
            or not all(
                isinstance(value, str) and value for value in tier["categories"]
            )
        ):
            return False
        candidate = generation[0]
        worktree_identity = worktree[0]
        if (
            candidate.get("remote") != target.get("remote")
            or candidate.get("destination_ref") != target.get("destination_ref")
            or candidate.get("policy_commit") != policy.get("commit")
            or candidate.get("policy_digest") != policy.get("digest")
            or candidate.get("worktree_identity")
            != {
                name: worktree_identity[name]
                for name in ("path", "git_dir", "common_dir")
            }
        ):
            return False

    epoch = integration.get("epoch")
    if epoch is not None:
        if (
            not isinstance(epoch, dict)
            or set(epoch)
            != {
                "operation_nonce",
                "generation_digest",
                "intent_digest",
                "started_at",
            }
            or not isinstance(epoch.get("operation_nonce"), str)
            or re.fullmatch(r"[0-9a-f]{32}", str(epoch["operation_nonce"]))
            is None
            or not _merge_hex(epoch.get("generation_digest"))
            or not _merge_hex(epoch.get("intent_digest"))
            or _utc_value(epoch.get("started_at")) is None
            or generation is None
            or epoch.get("generation_digest") != generation[1]
        ):
            return False

    push = integration.get("push")
    observed = integration.get("observed")
    if push is None:
        if observed is not None and not _merge_observation_shape_valid(observed, ()):
            return False
    else:
        push_result = push.get("result")
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
            or any(
                not isinstance(push.get(name), str)
                or journal.GIT_OBJECT_ID_PATTERN.fullmatch(str(push[name])) is None
                for name in ("expected_old_tip", "intended_head")
            )
            or push.get("destination_ref") != target.get("destination_ref")
            or _utc_value(push.get("intended_at")) is None
            or not isinstance(push.get("attempted_heads"), list)
            or not push["attempted_heads"]
            or not all(
                isinstance(head, str)
                and journal.GIT_OBJECT_ID_PATTERN.fullmatch(head) is not None
                for head in push["attempted_heads"]
            )
            or push["attempted_heads"][-1] != push.get("intended_head")
            or (
                push.get("landed_head") is not None
                and push.get("landed_head") not in push["attempted_heads"]
            )
            or (
                push_result is not None
                and (
                    not isinstance(push_result, dict)
                    or set(push_result)
                    != {
                        "classification",
                        "exit",
                        "inflight_digest",
                        "output_digest",
                        "launch_failed",
                        "timed_out",
                        "output_limit_exceeded",
                        "recorded_at",
                    }
                    or push_result.get("classification")
                    not in {
                        "success",
                        "non-fast-forward",
                        "known-failure",
                        "outcome-unknown",
                    }
                    or (
                        push_result.get("exit") is not None
                        and type(push_result.get("exit")) is not int
                    )
                    or not _merge_hex(push_result.get("inflight_digest"))
                    or not _merge_hex(push_result.get("output_digest"))
                    or any(
                        type(push_result.get(name)) is not bool
                        for name in (
                            "launch_failed",
                            "timed_out",
                            "output_limit_exceeded",
                        )
                    )
                    or _utc_value(push_result.get("recorded_at")) is None
                )
            )
        ):
            return False
        if observed is not None and not _merge_observation_shape_valid(
            observed, push["attempted_heads"]
        ):
            return False
    return True


def _merge_condition_state_coherent(state: dict[str, object]) -> bool:
    """Apply DM-014's closed retained-state table to every projection."""

    integration = state.get("integration")
    cleanup = state.get("cleanup")
    scalar = state.get("state")
    if not isinstance(integration, dict) or not isinstance(cleanup, dict):
        return False
    if cleanup.get("condition") == "cleanup-failed":
        return scalar == "cleanup_pending"

    condition = integration.get("condition")
    if condition == "lock-release-failed":
        condition = integration.get("primary_condition")
    retained: dict[str, frozenset[str] | None] = {
        "none": None,
        "fetch-failed": frozenset({"classifying", "authorized"}),
        "rebase-failed": frozenset({"revising"}),
        "remote-moved": frozenset({"authorized"}),
        "remote-churn": frozenset({"awaiting_approval"}),
        "push-failed": frozenset({"pushing"}),
        "non-fast-forward": frozenset({"authorized"}),
        "push-outcome-unknown": frozenset({"pushing"}),
        "foreign-git-state": None,
    }
    allowed = retained.get(str(condition))
    return condition in retained and (allowed is None or scalar in allowed)


def _merge_current_gate_facts(
    step_id: str,
    value: object,
    generation_digest: str,
) -> tuple[dict[str, object], ...] | None:
    """Return the current PASS fact set for one intrinsic merge gate."""

    if isinstance(value, dict):
        facts = (value,)
    elif isinstance(value, list) and value and all(
        isinstance(item, dict) for item in value
    ):
        values = [item for item in value if isinstance(item, dict)]
        if step_id.startswith("stack:"):
            latest = values[-1]
            batch_id = latest.get("batch_id")
            cell_count = latest.get("cell_count")
            if (
                not isinstance(batch_id, str)
                or not batch_id
                or type(cell_count) is not int
                or cell_count <= 0
            ):
                return None
            facts = tuple(
                item for item in values if item.get("batch_id") == batch_id
            )
            if (
                len(facts) != cell_count
                or {item.get("cell_index") for item in facts}
                != set(range(1, cell_count + 1))
            ):
                return None
        else:
            facts = (values[-1],)
    else:
        return None
    prefix = "gate-1: " if step_id == "gate-1" else "gate-2: "
    if any(
        fact.get("result") != "passed"
        or fact.get("generation_digest") != generation_digest
        or not isinstance(fact.get("criterion"), str)
        or not str(fact["criterion"]).startswith(prefix)
        for fact in facts
    ):
        return None
    return tuple(copy.deepcopy(fact) for fact in facts)


def _merge_required_gate_ids(
    state: dict[str, object], context: dict[str, object] | None
) -> frozenset[str] | None:
    tier = state.get("tier")
    if not isinstance(tier, dict) or not isinstance(tier.get("categories"), list):
        return None
    intrinsic = {
        "gate-1",
        "assertion-sensor",
        *(
            f"stack:{category}"
            for category in tier["categories"]
            if isinstance(category, str) and category
        ),
    }
    supplied = context.get("required_gate_ids") if isinstance(context, dict) else None
    if supplied is not None:
        if (
            not isinstance(supplied, (list, tuple, frozenset, set))
            or not all(isinstance(value, str) and value for value in supplied)
        ):
            return None
        selected = frozenset(str(value) for value in supplied)
        return selected if intrinsic <= selected else None

    policy = state.get("policy_source")
    repository = state.get("repository")
    if not isinstance(policy, dict) or not isinstance(repository, str):
        return None
    try:
        raw = subprocess.run(
            [
                "git",
                "-C",
                repository,
                "show",
                f"{policy.get('commit')}:forge-project.md",
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if raw.returncode != 0 or journal._sha256(raw.stdout) != policy.get("digest"):
        return None
    try:
        text = raw.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None
    begin = "<!-- FORGE:REGION invariants BEGIN -->"
    end = "<!-- FORGE:REGION invariants END -->"
    if text.count(begin) != 1 or text.count(end) != 1:
        return None
    body = text.split(begin, 1)[1].split(end, 1)[0]
    rows: list[list[str]] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells: list[str] = []
        current: list[str] = []
        escaped = False
        for character in stripped[1:-1]:
            if escaped:
                current.append("|" if character == "|" else f"\\{character}")
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == "|":
                cells.append("".join(current).strip().strip("`"))
                current = []
            else:
                current.append(character)
        if escaped:
            current.append("\\")
        cells.append("".join(current).strip().strip("`"))
        rows.append(cells)
    if (
        len(rows) < 2
        or [value.lower() for value in rows[0]]
        != ["invariant", "check command", "enforcement point"]
        or not all(re.fullmatch(r":?-{3,}:?", value) for value in rows[1])
    ):
        return None
    selected = set(intrinsic)
    for row_number, row in enumerate(rows[2:], 1):
        if (
            len(row) != 3
            or any(not value for value in row)
            or row[2] not in {"commit", "merge", "hook"}
            or any(character in row[1] for character in "\r\n\x00")
        ):
            return None
        if row[2] == "merge":
            selected.add(f"invariant:{row_number}")
    return frozenset(selected)


def _merge_mechanical_gates_current(
    state: dict[str, object], context: dict[str, object] | None
) -> bool:
    """Prove every gate ID derivable from the materialized tuple is current."""

    generation = _merge_generation(state.get("candidate"))
    tier = state.get("tier")
    steps = state.get("steps")
    if (
        generation is None
        or not isinstance(tier, dict)
        or not isinstance(tier.get("categories"), list)
        or not isinstance(steps, dict)
    ):
        return False
    required = _merge_required_gate_ids(state, context)
    if required is None:
        return False
    gate_ids = set(steps)
    return required == gate_ids and all(
        _merge_current_gate_facts(name, steps.get(name), generation[1]) is not None
        for name in gate_ids
    )


def _merge_review_iteration(state: dict[str, object]) -> int | None:
    review = state.get("review")
    if not isinstance(review, dict):
        return None
    if not review:
        return 0
    iteration = review.get("iteration")
    if type(iteration) is not int or not 1 <= int(iteration) <= 8:
        return None
    for name in ("request", "verdict"):
        value = review.get(name)
        if isinstance(value, dict) and (
            "iteration" in value and value.get("iteration") != iteration
        ):
            return None
    return int(iteration)


def _merge_invalidated_review_projection(
    state: dict[str, object],
) -> dict[str, object] | None:
    """Retain only the completed review-cycle count across invalidation."""

    iteration = _merge_review_iteration(state)
    if iteration is None:
        return None
    return {} if iteration == 0 else {"iteration": iteration}


def _merge_review_request_current(state: dict[str, object]) -> bool:
    generation = _merge_generation(state.get("candidate"))
    review = state.get("review")
    iteration = _merge_review_iteration(state)
    request = review.get("request") if isinstance(review, dict) else None
    return bool(
        generation is not None
        and iteration is not None
        and 1 <= iteration <= 8
        and isinstance(request, dict)
        and request.get("candidate") == generation[0].get("candidate_head")
        and request.get("reviewer") == "review-final"
        and request.get("iteration") == iteration
        and isinstance(request.get("package"), str)
        and bool(request["package"])
        and _merge_hex(request.get("package_digest"))
    )


def _merge_review_verdict_current(
    state: dict[str, object], verdict_value: str | None = None
) -> bool:
    generation = _merge_generation(state.get("candidate"))
    review = state.get("review")
    iteration = _merge_review_iteration(state)
    request = review.get("request") if isinstance(review, dict) else None
    verdict = review.get("verdict") if isinstance(review, dict) else None
    if (
        generation is None
        or iteration is None
        or not 1 <= iteration <= 8
        or not _merge_review_request_current(state)
        or not isinstance(request, dict)
        or not isinstance(verdict, dict)
        or verdict.get("verdict") not in {"PASS", "BLOCK"}
        or (
            verdict_value is not None
            and verdict.get("verdict") != verdict_value
        )
        or verdict.get("candidate") != generation[0].get("candidate_head")
        or verdict.get("package_digest") != request.get("package_digest")
        or verdict.get("reviewer_role") != "review-final"
        or verdict.get("iteration") != iteration
    ):
        return False
    return _review_binding_for_state(state) is not None


def _merge_iteration_cap_residual_current(state: dict[str, object]) -> bool:
    """Require the durable residual-risk fact for an eighth BLOCK."""

    review = state.get("review")
    verdict = review.get("verdict") if isinstance(review, dict) else None
    residual = review.get("residual_risk") if isinstance(review, dict) else None
    return bool(
        isinstance(verdict, dict)
        and verdict.get("verdict") == "BLOCK"
        and isinstance(residual, dict)
        and isinstance(residual.get("reason"), str)
        and bool(str(residual["reason"]).strip())
        and isinstance(residual.get("findings"), list)
        and residual.get("findings") == verdict.get("findings", [])
        and (
            residual.get("at") is None
            or _utc_value(residual.get("at")) is not None
        )
    )


def _merge_pending_disposition_cosign(state: dict[str, object]) -> bool:
    review = state.get("review")
    if not isinstance(review, dict):
        return False
    if review.get("operator_cosign_required") is True:
        return True
    dispositions = review.get("dispositions", [])
    if not isinstance(dispositions, list):
        return True
    for disposition in dispositions:
        if not isinstance(disposition, dict):
            return True
        severity = disposition.get(
            "finding_severity", disposition.get("severity")
        )
        approval = state.get("approval")
        separately_cosigned = bool(
            isinstance(approval, dict)
            and approval.get("purpose") == "finding-disposition"
            and approval.get("chain_id") == state.get("chain_id")
            and approval.get("finding") == disposition.get("finding")
            and approval.get("resolution") == disposition.get("resolution")
        )
        if severity in {"CRITICAL", "MAJOR"} and not (
            disposition.get("operator_cosign") is True
            or disposition.get("cosigned") is True
            or separately_cosigned
        ):
            return True
    return False


def _merge_introduced_disposition_valid(
    prior: dict[str, object], current: dict[str, object]
) -> bool:
    prior_review = prior.get("review")
    current_review = current.get("review")
    generation = _merge_generation(current.get("candidate"))
    if (
        not isinstance(prior_review, dict)
        or not isinstance(current_review, dict)
        or generation is None
    ):
        return False
    old_dispositions = prior_review.get("dispositions", [])
    dispositions = current_review.get("dispositions")
    if (
        not isinstance(old_dispositions, list)
        or not isinstance(dispositions, list)
        or len(dispositions) != len(old_dispositions) + 1
        or dispositions[:-1] != old_dispositions
        or not isinstance(dispositions[-1], dict)
    ):
        return False
    introduced = dispositions[-1]
    finding = introduced.get("finding")
    severity = introduced.get("severity")
    resolution = introduced.get("resolution")
    verdict = current_review.get("verdict")
    findings = verdict.get("findings") if isinstance(verdict, dict) else None
    if (
        type(finding) is not int
        or finding <= 0
        or severity not in {"CRITICAL", "MAJOR", "MINOR"}
        or not isinstance(resolution, str)
        or not resolution.strip()
        or introduced.get("candidate") != generation[0].get("candidate_head")
        or introduced.get("generation_digest") != generation[1]
        or _utc_value(introduced.get("recorded_at")) is None
        or not isinstance(findings, list)
        or finding > len(findings)
        or not isinstance(findings[finding - 1], dict)
        or findings[finding - 1].get("severity") != severity
    ):
        return False
    retained = set(prior_review) | set(current_review)
    retained -= {"dispositions", "operator_cosign_required"}
    if any(prior_review.get(name) != current_review.get(name) for name in retained):
        return False
    pending = severity in {"CRITICAL", "MAJOR"}
    return current_review.get("operator_cosign_required", False) is pending


def _merge_finding_cosign_current(state: dict[str, object]) -> bool:
    generation = _merge_generation(state.get("candidate"))
    review = state.get("review")
    approval = state.get("approval")
    dispositions = review.get("dispositions") if isinstance(review, dict) else None
    if (
        generation is None
        or not isinstance(approval, dict)
        or approval.get("purpose") != "finding-disposition"
        or approval.get("chain_id") != state.get("chain_id")
        or approval.get("candidate") != generation[0].get("candidate_head")
        or approval.get("generation_digest") != generation[1]
        or not isinstance(dispositions, list)
    ):
        return False
    return any(
        isinstance(disposition, dict)
        and disposition.get("finding") == approval.get("finding")
        and disposition.get("resolution") == approval.get("resolution")
        and disposition.get("severity") in {"CRITICAL", "MAJOR"}
        for disposition in dispositions
    )


def _merge_gate4_summary_current(state: dict[str, object]) -> bool:
    generation = _merge_generation(state.get("candidate"))
    authorization = state.get("authorization")
    if (
        generation is None
        or not isinstance(authorization, dict)
        or set(authorization)
        != {
            "candidate_head",
            "generation_digest",
            "diff_summary",
            "control_paths",
            "review_verdict",
            "recorded_at",
        }
        or authorization.get("candidate_head")
        != generation[0].get("candidate_head")
        or authorization.get("generation_digest") != generation[1]
        or not isinstance(authorization.get("diff_summary"), str)
        or not isinstance(authorization.get("control_paths"), list)
        or not all(
            isinstance(path, str) and path
            for path in authorization["control_paths"]
        )
        or authorization.get("review_verdict") != "PASS"
        or _utc_value(authorization.get("recorded_at")) is None
    ):
        return False
    return _merge_review_verdict_current(state, "PASS")


def _merge_gate4_approval_current(state: dict[str, object]) -> bool:
    generation = _merge_generation(state.get("candidate"))
    approval = state.get("approval")
    return bool(
        generation is not None
        and isinstance(approval, dict)
        and approval.get("purpose") == "gate-4"
        and approval.get("chain_id") == state.get("chain_id")
        and approval.get("candidate") == generation[0].get("candidate_head")
        and approval.get("generation_digest") == generation[1]
    )


def _merge_remote_churn_approval_current(state: dict[str, object]) -> bool:
    generation = _merge_generation(state.get("candidate"))
    approval = state.get("approval")
    return bool(
        generation is not None
        and isinstance(approval, dict)
        and approval.get("purpose") == "remote-churn"
        and approval.get("chain_id") == state.get("chain_id")
        and approval.get("candidate") == generation[0].get("candidate_head")
        and approval.get("generation_digest") == generation[1]
    )


def _merge_complete_tuple_valid(
    event_name: str,
    prior: dict[str, object],
    current: dict[str, object],
    context: dict[str, object] | None,
) -> bool:
    """Enforce FR-232's non-scalar gate/review/approval tuple members."""

    prior_iteration = _merge_review_iteration(prior)
    current_iteration = _merge_review_iteration(current)
    if prior_iteration is None or current_iteration is None:
        return False
    before = prior.get("state")
    after = current.get("state")
    if event_name == "gate_recorded" and after == "reviewing":
        return _merge_mechanical_gates_current(current, context)
    if event_name == "reverification_result" and after == "reviewing":
        return _merge_mechanical_gates_current(current, context)
    if event_name == "review_requested":
        current_review = current.get("review")
        return bool(
            prior_iteration < 8
            and current_iteration == prior_iteration + 1
            and isinstance(current_review, dict)
            and set(current_review) == {"iteration", "request"}
            and _merge_review_request_current(current)
        )
    if event_name == "review_attached":
        prior_review = prior.get("review")
        current_review = current.get("review")
        if (
            current_iteration != prior_iteration
            or not isinstance(prior_review, dict)
            or not isinstance(current_review, dict)
            or set(prior_review) != {"iteration", "request"}
            or current_review.get("request") != prior_review.get("request")
            or not _merge_review_request_current(prior)
            or not _merge_review_verdict_current(current)
        ):
            return False
        verdict = current["review"]["verdict"]["verdict"]
        allowed_review_fields = {"iteration", "request", "verdict"}
        if verdict == "BLOCK" and current_iteration == 8:
            allowed_review_fields.add("residual_risk")
        if set(current_review) != allowed_review_fields:
            return False
        if verdict == "BLOCK":
            return bool(
                after == "revising"
                and (
                    current_iteration < 8
                    or _merge_iteration_cap_residual_current(current)
                )
            )
        if after == "reviewing":
            return False
        if _merge_pending_disposition_cosign(current):
            return False
        tier = current.get("tier")
        if not isinstance(tier, dict) or not _merge_gate4_summary_current(current):
            return False
        return after == (
            "awaiting_approval" if tier.get("control") is True else "authorized"
        )
    if event_name == "review_disposition":
        return prior_iteration < 8 and _merge_introduced_disposition_valid(
            prior, current
        )
    if event_name == "approval_recorded":
        if before == after:
            approval = current.get("approval")
            prior_review = prior.get("review")
            current_review = current.get("review")
            if not isinstance(prior_review, dict) or not isinstance(
                current_review, dict
            ):
                return False
            retained_review = set(prior_review) | set(current_review)
            retained_review.discard("operator_cosign_required")
            return bool(
                prior_iteration < 8
                and _merge_pending_disposition_cosign(prior)
                and not _merge_pending_disposition_cosign(current)
                and _merge_finding_cosign_current(current)
                and prior_review.get("operator_cosign_required") is True
                and current_review.get("operator_cosign_required") is False
                and all(
                    prior_review.get(name) == current_review.get(name)
                    for name in retained_review
                )
                and current.get("authorization") == prior.get("authorization")
                and current.get("integration") == prior.get("integration")
            )
        prior_integration = prior.get("integration")
        current_integration = current.get("integration")
        if (
            isinstance(prior_integration, dict)
            and prior_integration.get("condition") == "remote-churn"
        ):
            retained = set(prior_integration) - {
                "condition",
                "primary_condition",
                "remote_movement_count",
            }
            return bool(
                before == "awaiting_approval"
                and after == "authorized"
                and isinstance(current_integration, dict)
                and all(
                    current_integration.get(name) == prior_integration.get(name)
                    for name in retained
                )
                and current_integration.get("condition") == "none"
                and current_integration.get("primary_condition") == "none"
                and current_integration.get("remote_movement_count") == 0
                and _merge_remote_churn_approval_current(current)
                and _merge_gate4_summary_current(current)
                and current.get("review") == prior.get("review")
                and current.get("authorization")
                == prior.get("authorization")
            )
        tier = current.get("tier")
        return bool(
            before == "awaiting_approval"
            and after == "authorized"
            and isinstance(tier, dict)
            and tier.get("control") is True
            and not _merge_pending_disposition_cosign(current)
            and _merge_mechanical_gates_current(current, context)
            and _merge_gate4_summary_current(current)
            and _merge_gate4_approval_current(current)
            and current.get("review") == prior.get("review")
            and current.get("authorization") == prior.get("authorization")
            and current.get("integration") == prior.get("integration")
        )
    if event_name == "generation_carried_forward":
        if (
            current.get("review") != prior.get("review")
            or current.get("approval") != prior.get("approval")
            or current.get("authorization") != prior.get("authorization")
        ):
            return False
        if after in {"authorized", "awaiting_approval"}:
            tier = prior.get("tier")
            return bool(
                isinstance(tier, dict)
                and _merge_mechanical_gates_current(current, context)
                and _merge_review_verdict_current(prior, "PASS")
                and _merge_gate4_summary_current(prior)
                and (
                    tier.get("control") is not True
                    or _merge_gate4_approval_current(prior)
                )
            )
        return after == "reverifying"
    if event_name == "generation_refreshed":
        if prior_iteration >= 8 or _merge_pending_disposition_cosign(prior):
            return False
    if event_name in {"epoch_intent", "push_intent"} or (
        event_name == "fetch_intent" and before == "authorized"
    ):
        tier = prior.get("tier")
        if (
            not isinstance(tier, dict)
            or _merge_pending_disposition_cosign(prior)
            or not _merge_mechanical_gates_current(prior, context)
            or not _merge_gate4_summary_current(prior)
            or (tier.get("control") is True and not _merge_gate4_approval_current(prior))
        ):
            return False
        if current.get("authorization") != prior.get("authorization"):
            return False
    return True


def _state_shape_valid(
    state: object,
    chain_id: str,
    family: str,
) -> bool:
    expected_keys = _COMMIT_STATE_KEYS if family == "commit" else _MERGE_STATE_KEYS
    expected_schema = "forge-chain/1" if family == "commit" else "forge-merge-chain/1"
    if (
        not isinstance(state, dict)
        or set(state) != expected_keys
        or state.get("schema") != expected_schema
        or state.get("chain_id") != chain_id
        or state.get("kind") != family
        or not _run_binding_valid(state.get("run_binding"))
        or not _outbox_valid(state.get("journal_outbox"))
        or any(
            _utc_value(state.get(name)) is None
            for name in ("created_at", "last_event_at", "inactive_after")
        )
    ):
        return False
    if family == "commit":
        if (
            state.get("state") not in _COMMIT_STATES
            or not isinstance(state.get("repo_head"), str)
            or journal.GIT_OBJECT_ID_PATTERN.fullmatch(str(state["repo_head"]))
            is None
            or not isinstance(state.get("policy_source"), dict)
            or not isinstance(state.get("paths"), list)
            or not all(isinstance(path, str) and path for path in state["paths"])
            or not all(
                isinstance(state.get(name), dict)
                for name in (
                    "staging",
                    "candidate",
                    "tier",
                    "steps",
                    "review",
                    "approval",
                    "authorization",
                    "commit_result",
                )
            )
        ):
            return False
        candidate = state["candidate"].get("sha256")
        if candidate is not None and (
            not isinstance(candidate, str)
            or journal.HEX_SHA256_PATTERN.fullmatch(candidate) is None
        ):
            return False
    else:
        if (
            not isinstance(state.get("repository"), str)
            or not Path(str(state["repository"])).is_absolute()
            or not isinstance(state.get("worktree"), dict)
            or not isinstance(state.get("policy_source"), dict)
            or not isinstance(state.get("steps"), dict)
            or not isinstance(state.get("review"), dict)
            or not isinstance(state.get("approval"), dict)
            or not isinstance(state.get("authorization"), dict)
            or not isinstance(state.get("integration"), dict)
            or not isinstance(state.get("cleanup"), dict)
            or not _merge_nested_state_valid(state)
        ):
            return False
        run_binding = state.get("run_binding")
        expected_run = (
            run_binding.get("run_id") if isinstance(run_binding, dict) else None
        )
        if state.get("run") != expected_run:
            return False
    run_binding = state.get("run_binding")
    if isinstance(run_binding, dict):
        policy_source = state.get("policy_source")
        if (
            not isinstance(policy_source, dict)
            or policy_source.get("digest") != run_binding.get("policy_digest")
        ):
            return False
        if family == "commit":
            staging = state.get("staging")
            if (
                not isinstance(staging, dict)
                or staging.get("worktree_root") != run_binding.get("repository")
            ):
                return False
        elif state.get("repository") != run_binding.get("repository"):
            return False
    return True


def _merge_generation(candidate: object) -> tuple[dict[str, object], str] | None:
    if candidate is None:
        return None
    if not isinstance(candidate, dict) or set(candidate) != {
        "remote",
        "destination_ref",
        "remote_tip",
        "candidate_head",
        "diff_sha256",
        "policy_commit",
        "policy_digest",
        "worktree_identity",
        "generation",
        "generation_digest",
    }:
        return None
    worktree = candidate.get("worktree_identity")
    generation = candidate.get("generation")
    if (
        candidate.get("remote") != "origin"
        or not isinstance(candidate.get("destination_ref"), str)
        or not str(candidate["destination_ref"]).startswith("refs/heads/")
        or any(
            not isinstance(candidate.get(name), str)
            or journal.GIT_OBJECT_ID_PATTERN.fullmatch(str(candidate[name])) is None
            for name in ("remote_tip", "candidate_head", "policy_commit")
        )
        or any(
            not isinstance(candidate.get(name), str)
            or journal.HEX_SHA256_PATTERN.fullmatch(str(candidate[name])) is None
            for name in ("diff_sha256", "policy_digest", "generation_digest")
        )
        or not isinstance(worktree, dict)
        or set(worktree) != {"path", "git_dir", "common_dir"}
        or not all(
            isinstance(worktree.get(name), str)
            and Path(str(worktree[name])).is_absolute()
            for name in ("path", "git_dir", "common_dir")
        )
        or type(generation) is not int
        or int(generation) <= 0
    ):
        return None
    preimage = {
        name: candidate[name]
        for name in (
            "remote",
            "destination_ref",
            "remote_tip",
            "candidate_head",
            "diff_sha256",
            "policy_commit",
            "policy_digest",
            "worktree_identity",
            "generation",
        )
    }
    digest = journal._sha256(journal._canonical_json_bytes(preimage))
    if digest != candidate.get("generation_digest"):
        return None
    return preimage, digest


def _commit_initial_state_valid(state: dict[str, object]) -> bool:
    staging = state.get("staging")
    review = state.get("review")
    candidate = state.get("candidate")
    tier = state.get("tier")
    return bool(
        state.get("state") == "classifying"
        and state.get("journal_outbox") is None
        and isinstance(candidate, dict)
        and candidate.get("sha256") is None
        and state.get("steps") == {}
        and state.get("approval") == {}
        and state.get("authorization") == {}
        and state.get("commit_result") == {}
        and isinstance(staging, dict)
        and staging.get("staged_paths") == []
        and staging.get("classification_runs") == 0
        and staging.get("anomalies") == []
        and isinstance(review, dict)
        and review.get("iteration") == 0
        and review.get("request") is None
        and review.get("verdict") is None
        and review.get("dispositions") == []
        and isinstance(tier, dict)
        and tier.get("derived") is None
        and tier.get("control") is False
        and tier.get("categories") == []
        and tier.get("classification") is None
    )


def _ordinary_commit_details(event: dict[str, object]) -> dict[str, object]:
    payload = event.get("payload")
    if not isinstance(payload, dict) or set(payload) != {
        "at",
        "details",
        "event",
        "state",
    }:
        raise _binding_replay_refusal()
    details = payload.get("details")
    if not isinstance(details, dict):
        raise _binding_replay_refusal()
    ordinary = copy.deepcopy(details)
    ordinary.pop("source_event_digest", None)
    ordinary.pop("journal_batch", None)
    return ordinary


def _commit_skip_delta(
    event: dict[str, object],
    prior: dict[str, object] | None,
    current: dict[str, object],
) -> tuple[str, dict[str, object]] | None:
    """Return the one exact user-skip fact introduced by an operator event."""

    payload = event.get("payload")
    if (
        prior is None
        or not isinstance(payload, dict)
        or payload.get("event") != "operator_skip"
    ):
        return None
    details = _ordinary_commit_details(event)
    gate_id = details.get("gate_id")
    prior_steps = prior.get("steps")
    current_steps = current.get("steps")
    if (
        not isinstance(gate_id, str)
        or not gate_id
        or not isinstance(prior_steps, dict)
        or not isinstance(current_steps, dict)
    ):
        return None
    old_container = prior_steps.get("user_skips")
    current_container = current_steps.get("user_skips")
    if (
        old_container is not None
        and not isinstance(old_container, dict)
    ) or not isinstance(current_container, dict):
        return None
    old_skips = old_container if isinstance(old_container, dict) else {}
    fact = current_container.get(gate_id)
    if (
        not isinstance(fact, dict)
        or old_skips.get(gate_id) == fact
        or fact.get("directed_by") != details.get("directed_by")
        or fact.get("reason") != details.get("reason")
    ):
        return None
    expected_skips = copy.deepcopy(old_skips)
    expected_skips[gate_id] = copy.deepcopy(fact)
    expected_steps = copy.deepcopy(prior_steps)
    expected_steps["user_skips"] = expected_skips
    if current_steps != expected_steps:
        return None
    return gate_id, copy.deepcopy(fact)


def _commit_secret_scan_delta(
    event: dict[str, object],
    prior: dict[str, object] | None,
    current: dict[str, object],
) -> tuple[int, dict[str, object]] | None:
    """Return the exact append-one ``secret-scan`` fact for its native event."""

    payload = event.get("payload")
    if (
        prior is None
        or not isinstance(payload, dict)
        or payload.get("event") != "secret_scan_recorded"
    ):
        return None
    details = _ordinary_commit_details(event)
    if set(details) != {"result", "finding_count"}:
        return None
    result = details.get("result")
    finding_count = details.get("finding_count")
    if (
        result not in {"passed", "failed"}
        or type(finding_count) is not int
        or int(finding_count) < 0
    ):
        return None
    prior_steps = prior.get("steps")
    current_steps = current.get("steps")
    if not isinstance(prior_steps, dict) or not isinstance(current_steps, dict):
        return None
    prior_runs_value = prior_steps.get("secret-scan")
    current_runs = current_steps.get("secret-scan")
    prior_runs = prior_runs_value if isinstance(prior_runs_value, list) else []
    if (
        (prior_runs_value is not None and not isinstance(prior_runs_value, list))
        or not isinstance(current_runs, list)
        or len(current_runs) != len(prior_runs) + 1
        or current_runs[:-1] != prior_runs
        or not isinstance(current_runs[-1], dict)
    ):
        return None
    fact = current_runs[-1]
    if not _commit_secret_scan_fact_valid(
        fact,
        current,
        result=result,
        finding_count=finding_count,
    ):
        return None
    expected_steps = copy.deepcopy(prior_steps)
    expected_steps["secret-scan"] = copy.deepcopy(current_runs)
    if current_steps != expected_steps:
        return None
    return len(current_runs) - 1, copy.deepcopy(fact)


_COMMIT_SECRET_SCAN_ARGV = ("forge-cli", "scan", "secrets", "--staged")
_COMMIT_SECRET_SCAN_FACT_FIELDS = frozenset(
    {
        "candidate",
        "recorded_at",
        "result",
        "exit_code",
        "duration_seconds",
        "stdout_stderr_digest",
        "transcript",
        "command_argv",
        "command_digest",
        "env_fingerprint_preimage",
        "env_fingerprint",
        "repo_head",
        "findings",
    }
)
_COMMIT_ENV_FINGERPRINT_FIELDS = frozenset(
    {
        "command_digest",
        "cwd",
        "platform",
        "policy_digest",
        "python_version",
        "repo_head",
    }
)


def _commit_secret_scan_fact_valid(
    fact: object,
    current: dict[str, object],
    *,
    result: object,
    finding_count: object,
) -> bool:
    """Match the exact fact emitted by the native staged-secret scanner."""

    candidate = current.get("candidate")
    policy = current.get("policy_source")
    staging = current.get("staging")
    if (
        not isinstance(fact, dict)
        or set(fact) != _COMMIT_SECRET_SCAN_FACT_FIELDS
        or result not in {"passed", "failed"}
        or type(finding_count) is not int
        or int(finding_count) < 0
        or not isinstance(candidate, dict)
        or not _merge_hex(candidate.get("sha256"))
        or fact.get("candidate") != candidate.get("sha256")
        or fact.get("result") != result
        or _utc_value(fact.get("recorded_at")) is None
        or type(fact.get("duration_seconds")) is not float
        or not math.isfinite(float(fact["duration_seconds"]))
        or float(fact["duration_seconds"]) < 0
        or fact.get("transcript") is not None
        or fact.get("command_argv") != list(_COMMIT_SECRET_SCAN_ARGV)
        or not isinstance(policy, dict)
        or not _merge_hex(policy.get("digest"))
        or not isinstance(staging, dict)
        or not isinstance(staging.get("worktree_root"), str)
        or not Path(str(staging["worktree_root"])).is_absolute()
        or not isinstance(current.get("repo_head"), str)
        or journal.GIT_OBJECT_ID_PATTERN.fullmatch(str(current["repo_head"]))
        is None
    ):
        return False

    findings = fact.get("findings")
    if (
        not isinstance(findings, list)
        or len(findings) != finding_count
        or any(
            not isinstance(finding, dict)
            or set(finding) != {"line", "path", "rule_id"}
            or type(finding.get("line")) is not int
            or int(finding["line"]) <= 0
            or not isinstance(finding.get("path"), str)
            or not finding["path"]
            or "\x00" in str(finding["path"])
            or not isinstance(finding.get("rule_id"), str)
            or not finding["rule_id"]
            for finding in findings
        )
        or result != ("failed" if findings else "passed")
        or fact.get("exit_code") != (1 if findings else 0)
    ):
        return False

    command_digest = journal._sha256(
        journal._canonical_json_bytes(list(_COMMIT_SECRET_SCAN_ARGV))
    )
    preimage = fact.get("env_fingerprint_preimage")
    if (
        fact.get("command_digest") != command_digest
        or fact.get("stdout_stderr_digest")
        != journal._sha256(journal._canonical_json_bytes(findings))
        or not isinstance(preimage, dict)
        or set(preimage) != _COMMIT_ENV_FINGERPRINT_FIELDS
        or preimage.get("command_digest") != command_digest
        or preimage.get("cwd") != os.path.realpath(str(staging["worktree_root"]))
        or not isinstance(preimage.get("platform"), str)
        or not preimage["platform"]
        or preimage.get("policy_digest") != policy.get("digest")
        or not isinstance(preimage.get("python_version"), str)
        or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", str(preimage["python_version"]))
        is None
        or preimage.get("repo_head") != current.get("repo_head")
        or fact.get("repo_head") != current.get("repo_head")
        or fact.get("env_fingerprint")
        != journal._sha256(journal._canonical_json_bytes(preimage))
    ):
        return False
    return True


def _commit_candidate_authority_cleared(state: dict[str, object]) -> bool:
    """Match the native invalidation performed for a new commit candidate."""

    steps = state.get("steps")
    review = state.get("review")
    if not isinstance(steps, dict) or not isinstance(review, dict):
        return False
    skips = steps.get("user_skips")
    return bool(
        (skips is None or skips == {})
        and review.get("request") is None
        and review.get("verdict") is None
        and review.get("dispositions") == []
        and state.get("approval") == {}
        and state.get("authorization") == {}
        and state.get("commit_result") == {}
    )


def _commit_transition_valid(
    event: dict[str, object],
    prior: dict[str, object] | None,
    current: dict[str, object],
) -> bool:
    payload = event["payload"]
    assert isinstance(payload, dict)
    event_name = payload.get("event")
    if event_name not in _COMMIT_EVENT_NAMES:
        return False
    event_at = _utc_value(payload.get("at"))
    created_at = _utc_value(current.get("created_at"))
    inactive_at = _utc_value(current.get("inactive_after"))
    if (
        event_at is None
        or created_at is None
        or inactive_at is None
        or current.get("last_event_at") != payload.get("at")
        or event_at < created_at
        or inactive_at <= event_at
    ):
        return False
    details = _ordinary_commit_details(event)
    expected_details = _COMMIT_DETAIL_KEYS.get(str(event_name))
    if expected_details is None or set(details) != expected_details:
        return False
    if prior is None:
        return bool(
            event.get("sequence") == 1
            and event_name == "chain_started"
            and _commit_initial_state_valid(current)
            and details.get("paths") == current.get("paths")
        )
    if event_name == "chain_started":
        return False
    if any(
        prior.get(name) != current.get(name)
        for name in ("schema", "chain_id", "kind", "created_at", "run_binding")
    ):
        return False
    prior_at = _utc_value(prior.get("last_event_at"))
    if prior_at is None or event_at < prior_at:
        return False
    before_state = prior.get("state")
    after_state = current.get("state")
    if (
        not isinstance(before_state, str)
        or not isinstance(after_state, str)
        or after_state not in _COMMIT_STATE_TRANSITIONS.get(before_state, frozenset())
    ):
        return False

    if event_name == "gate_recorded":
        prior_steps = prior.get("steps")
        current_steps = current.get("steps")
        if not isinstance(prior_steps, dict) or not isinstance(current_steps, dict):
            return False
        changed_steps = {
            name
            for name in set(prior_steps) | set(current_steps)
            if prior_steps.get(name) != current_steps.get(name)
        }
        if len(changed_steps) != 1:
            return False
        step_id = next(iter(changed_steps))
        old_runs = prior_steps.get(step_id)
        new_runs = current_steps.get(step_id)
        old_list = old_runs if isinstance(old_runs, list) else []
        appended = bool(
            isinstance(new_runs, list)
            and (old_runs is None or isinstance(old_runs, list))
            and len(new_runs) == len(old_list) + 1
            and new_runs[:-1] == old_list
            and isinstance(new_runs[-1], dict)
            and new_runs[-1].get("result") in {"passed", "failed"}
        )
        singleton = bool(
            old_runs is None
            and isinstance(new_runs, dict)
            and new_runs.get("result") in {"passed", "failed"}
        )
        if not (appended or singleton):
            return False
    if event_name == "review_attached" and after_state != "reviewing":
        review = current.get("review")
        verdict = review.get("verdict") if isinstance(review, dict) else None
        if not isinstance(verdict, dict) or verdict.get("verdict") not in {
            "PASS",
            "BLOCK",
        }:
            return False
    if event_name == "approval_recorded":
        approval = current.get("approval")
        if not isinstance(approval, dict) or not approval:
            return False
        if after_state == "authorized":
            authorization = current.get("authorization")
            if not isinstance(authorization, dict) or not authorization:
                return False
    if event_name == "condition_recorded" and not (
        {"integration", "cleanup"} & changed
    ):
        return False
    ignored = {"last_event_at", "inactive_after", "journal_outbox"}
    changed = {
        name
        for name in _COMMIT_STATE_KEYS - ignored
        if prior.get(name) != current.get(name)
    }
    if not changed <= _COMMIT_EVENT_TOP_LEVEL_CHANGES[str(event_name)]:
        return False

    prior_candidate = prior.get("candidate")
    current_candidate = current.get("candidate")
    prior_sha = (
        prior_candidate.get("sha256") if isinstance(prior_candidate, dict) else None
    )
    current_sha = (
        current_candidate.get("sha256")
        if isinstance(current_candidate, dict)
        else None
    )
    candidate_events = {
        "candidate_staged",
        "candidate_invalidated",
        "candidate_restaged",
        "head_rebased",
        "mutating_gate_restaged",
    }
    if prior_sha != current_sha and event_name not in candidate_events:
        return False
    if (
        prior_sha != current_sha
        and not _commit_candidate_authority_cleared(current)
    ):
        return False
    if event_name == "candidate_staged":
        staging = current.get("staging")
        return bool(
            prior_sha is None
            and details.get("candidate") == current_sha
            and details.get("paths") == prior.get("paths")
            and isinstance(staging, dict)
            and staging.get("staged_paths") == current.get("paths")
        )
    if event_name in {"candidate_restaged", "mutating_gate_restaged"}:
        return bool(
            details.get("old_candidate") == prior_sha
            and details.get("new_candidate") == current_sha
        )
    if event_name == "candidate_invalidated":
        return bool(
            details.get("old_candidate") == prior_sha
            and details.get("new_candidate") == current_sha
            and after_state == "classifying"
        )
    if event_name == "classified":
        tier = current.get("tier")
        return bool(
            after_state == "verifying"
            and isinstance(tier, dict)
            and details.get("effective_tier") == tier.get("effective")
            and details.get("control") == tier.get("control")
        )
    if event_name == "step_recorded":
        step_id = details.get("step_id")
        steps = current.get("steps")
        previous_steps = prior.get("steps")
        runs = steps.get(step_id) if isinstance(steps, dict) else None
        old_runs = previous_steps.get(step_id) if isinstance(previous_steps, dict) else None
        expected_steps = copy.deepcopy(previous_steps)
        if isinstance(expected_steps, dict) and isinstance(step_id, str):
            expected_steps[step_id] = runs
        return bool(
            isinstance(step_id, str)
            and isinstance(runs, list)
            and runs
            and (old_runs is None or isinstance(old_runs, list))
            and runs[:-1] == (old_runs or [])
            and details.get("run") == len(runs)
            and isinstance(runs[-1], dict)
            and runs[-1].get("result") == details.get("result")
            and runs[-1].get("candidate") == current_sha
            and steps == expected_steps
        )
    if event_name == "review_requested":
        review = current.get("review")
        old_review = prior.get("review")
        return bool(
            isinstance(review, dict)
            and isinstance(old_review, dict)
            and review.get("request") != old_review.get("request")
            and review.get("request") is not None
        )
    if event_name == "review_blocked":
        review = current.get("review")
        return bool(
            after_state == "revising"
            and isinstance(review, dict)
            and isinstance(review.get("verdict"), dict)
            and review["verdict"].get("verdict") == "BLOCK"
            and review.get("iteration") == details.get("iteration")
        )
    if event_name == "review_passed":
        review = current.get("review")
        return bool(
            after_state in {"authorized", "awaiting_approval"}
            and isinstance(review, dict)
            and isinstance(review.get("verdict"), dict)
            and review["verdict"].get("verdict") == "PASS"
            and details.get("candidate") == current_sha
            and details.get("awaiting_approval")
            is (after_state == "awaiting_approval")
        )
    if event_name == "operator_approved":
        approval = current.get("approval")
        return bool(
            before_state == "awaiting_approval"
            and after_state == "authorized"
            and isinstance(approval, dict)
            and prior.get("approval") != approval
            and approval.get("candidate") == current_sha == details.get("candidate")
            and details.get("directed_by") == "operator"
        )
    if event_name == "operator_skip":
        return _commit_skip_delta(event, prior, current) is not None
    if event_name == "commit_intent":
        result = current.get("commit_result")
        intent = result.get("intent") if isinstance(result, dict) else None
        return bool(
            after_state == "committing"
            and isinstance(intent, dict)
            and intent.get("candidate") == current_sha == details.get("candidate")
            and intent.get("pre_head") == details.get("pre_head")
        )
    if event_name == "authorization_consumed":
        authorization = current.get("authorization")
        return bool(
            after_state == "committing"
            and isinstance(authorization, dict)
            and authorization.get("consumed") is True
            and details.get("candidate") == current_sha
        )
    if event_name == "commit_produced":
        result = current.get("commit_result")
        old_result = prior.get("commit_result")
        commit_sha = result.get("commit_sha") if isinstance(result, dict) else None
        old_commit = (
            old_result.get("commit_sha") if isinstance(old_result, dict) else None
        )
        return bool(
            old_commit is None
            and isinstance(commit_sha, str)
            and journal.GIT_OBJECT_ID_PATTERN.fullmatch(commit_sha) is not None
            and details.get("commit_sha") == commit_sha
            and details.get("candidate") == current_sha
        )
    if event_name == "commit_close_recovered":
        result = current.get("commit_result")
        old_result = prior.get("commit_result")
        commit_sha = result.get("commit_sha") if isinstance(result, dict) else None
        old_commit = (
            old_result.get("commit_sha") if isinstance(old_result, dict) else None
        )
        intent = old_result.get("intent") if isinstance(old_result, dict) else None
        return bool(
            after_state == "closed"
            and isinstance(commit_sha, str)
            and journal.GIT_OBJECT_ID_PATTERN.fullmatch(commit_sha) is not None
            and old_commit in {None, commit_sha}
            and details.get("commit_sha") == commit_sha
            and details.get("candidate") == current_sha
            and (
                old_commit == commit_sha
                or (
                    isinstance(intent, dict)
                    and intent.get("candidate") == current_sha
                )
            )
        )
    if event_name == "chain_closed":
        result = current.get("commit_result")
        old_result = prior.get("commit_result")
        return bool(
            after_state == "closed"
            and isinstance(result, dict)
            and isinstance(old_result, dict)
            and result.get("commit_sha") == old_result.get("commit_sha")
            and result.get("commit_sha") == details.get("commit_sha")
        )
    if event_name in {"chain_aborted", "policy_changed"}:
        return after_state == "aborted"
    if event_name == "commit_intent_rolled_back":
        return after_state == "authorized"
    if event_name == "mechanical_verification_complete":
        return after_state == "reviewing"
    if event_name in {"authorized", "retained_review_reauthorized"}:
        return after_state in {"authorized", "awaiting_approval"}
    return True


def _event_batch_records(
    event: dict[str, object],
    family: str,
) -> tuple[
    tuple[dict[str, object], ...],
    dict[str, object] | None,
    str | None,
]:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        raise _binding_replay_refusal()
    if family == "commit":
        details = payload.get("details")
        if not isinstance(details, dict):
            raise _binding_replay_refusal()
        carrier = details
    else:
        carrier = payload
    has_source = "source_event_digest" in carrier
    has_batch = "journal_batch" in carrier
    if not has_source and not has_batch:
        return (), None, None
    source_digest = carrier.get("source_event_digest")
    carried = carrier.get("journal_batch")
    if (
        not has_source
        or not has_batch
        or not isinstance(source_digest, str)
        or journal.HEX_SHA256_PATTERN.fullmatch(source_digest) is None
        or not isinstance(carried, dict)
        or set(carried)
        != {"idempotency_key", "batch_digest", "record_count", "records"}
        or carried.get("idempotency_key") != source_digest
        or not isinstance(carried.get("batch_digest"), str)
        or journal.HEX_SHA256_PATTERN.fullmatch(str(carried["batch_digest"])) is None
        or type(carried.get("record_count")) is not int
        or int(carried["record_count"]) <= 0
        or not isinstance(carried.get("records"), list)
        or len(carried["records"]) != carried["record_count"]
        or not all(isinstance(record, dict) for record in carried["records"])
    ):
        raise _binding_replay_refusal()
    records = tuple(dict(record) for record in carried["records"])
    batch_bytes = b"".join(journal._journal_line(record) for record in records)
    if journal._sha256(batch_bytes) != carried["batch_digest"]:
        raise _binding_replay_refusal()

    source_projection = copy.deepcopy(event)
    source_projection.pop("digest", None)
    projection_payload = source_projection.get("payload")
    assert isinstance(projection_payload, dict)
    if family == "commit":
        projection_carrier = projection_payload.get("details")
        if not isinstance(projection_carrier, dict):
            raise _binding_replay_refusal()
    else:
        projection_carrier = projection_payload
    projection_carrier.pop("source_event_digest", None)
    projection_carrier.pop("journal_batch", None)
    projected_state = projection_payload.get("state")
    if isinstance(projected_state, dict) and "journal_outbox" in projected_state:
        projected_state["journal_outbox"] = None
    if journal._sha256(journal._canonical_json_bytes(source_projection)) != source_digest:
        raise _binding_replay_refusal()

    expected_outbox: dict[str, object] = {
        "idempotency_key": source_digest,
        "batch_digest": carried["batch_digest"],
        "record_count": carried["record_count"],
        "source_event_digest": source_digest,
    }
    snapshotted_state = payload.get("state")
    if (
        isinstance(snapshotted_state, dict)
        and snapshotted_state.get("journal_outbox") != expected_outbox
    ):
        raise _binding_replay_refusal()

    chain_id = event.get("chain_id")
    if family == "commit" and isinstance(snapshotted_state, dict):
        chain_id = snapshotted_state.get("chain_id")
    for record in records:
        binding = record.get("binding")
        if (
            record.get("type") not in {"verification", "decision"}
            or not isinstance(binding, dict)
            or not journal._binding_shape_valid(binding, record=record)
        ):
            raise _binding_replay_refusal()
        source = binding.get("source_record")
        if (
            not isinstance(source, dict)
            or source.get("chain_id") != chain_id
            or source.get("event_digest") != source_digest
        ):
            raise _binding_replay_refusal()
    return records, expected_outbox, str(source_digest)


def _merge_worktree_claim(
    state: dict[str, object],
) -> tuple[dict[str, object], dict[str, object]] | None:
    worktree = state.get("worktree")
    if not isinstance(worktree, dict) or set(worktree) != {
        "path",
        "git_dir",
        "common_dir",
        "claim",
    }:
        return None
    if any(
        not isinstance(worktree.get(name), str)
        or not Path(str(worktree[name])).is_absolute()
        for name in ("path", "git_dir", "common_dir")
    ):
        return None
    claim = worktree.get("claim")
    if not isinstance(claim, dict) or set(claim) != {
        "status",
        "path",
        "inode",
        "digest",
    }:
        return None
    identity = {
        name: worktree[name] for name in ("path", "git_dir", "common_dir")
    }
    if any(os.path.realpath(str(value)) != value for value in identity.values()):
        return None
    worktree_digest = journal._sha256(journal._canonical_json_bytes(identity))
    expected_claim_path = (
        Path(str(worktree["common_dir"])).parent
        / ".forge"
        / "chains"
        / "owners"
        / f"{worktree_digest}.claim"
    )
    inode = claim.get("inode")
    digest = claim.get("digest")
    if (
        claim.get("status")
        not in {"unpublished", "owned", "releasing", "released"}
        or claim.get("path") != str(expected_claim_path)
        or (inode is not None and (type(inode) is not int or int(inode) <= 0))
        or (
            digest is not None
            and (
                not isinstance(digest, str)
                or journal.HEX_SHA256_PATTERN.fullmatch(digest) is None
            )
        )
    ):
        return None
    return worktree, claim


def _merge_claim_record_digest(
    state: dict[str, object], worktree_identity: dict[str, object]
) -> str | None:
    owner = state.get("owner")
    if (
        not isinstance(owner, dict)
        or set(owner) != {"pid", "host", "session", "started_at"}
        or type(owner.get("pid")) is not int
        or int(owner["pid"]) <= 0
        or not isinstance(owner.get("host"), str)
        or not owner["host"]
        or not isinstance(owner.get("session"), str)
        or not owner["session"]
        or _utc_value(owner.get("started_at")) is None
    ):
        return None
    identity = {
        name: worktree_identity[name]
        for name in ("path", "git_dir", "common_dir")
    }
    worktree_digest = journal._sha256(journal._canonical_json_bytes(identity))
    record = {
        "chain_id": state.get("chain_id"),
        "host": owner["host"],
        "pid": owner["pid"],
        "session": owner["session"],
        "started_at": owner["started_at"],
        "worktree_digest": worktree_digest,
    }
    return journal._sha256(journal._canonical_json_bytes(record))


def _merge_condition_transition_valid(
    before: str, after: str, current: dict[str, object]
) -> bool:
    integration = current.get("integration")
    cleanup = current.get("cleanup")
    cleanup_condition = (
        cleanup.get("condition") if isinstance(cleanup, dict) else None
    )
    if cleanup_condition == "cleanup-failed":
        return before in {"pushed", "cleanup_pending"} and after == "cleanup_pending"
    condition = (
        integration.get("condition") if isinstance(integration, dict) else None
    )
    if condition == "none":
        return after == before
    if condition == "fetch-failed":
        return before in {"classifying", "rebasing", "reverifying"} and after in {
            "classifying",
            "authorized",
        }
    if condition == "rebase-failed":
        return before in {"rebasing", "rebase_conflict"} and after == "revising"
    if condition == "remote-moved":
        return before in {
            "authorized",
            "rebasing",
            "reverifying",
            "pushing",
        } and after == "authorized"
    if condition == "remote-churn":
        return before in {
            "authorized",
            "awaiting_approval",
            "rebasing",
            "reverifying",
            "pushing",
        } and after == "awaiting_approval"
    if condition in {"push-failed", "push-outcome-unknown"}:
        return before == after == "pushing"
    if condition == "non-fast-forward":
        return before == "pushing" and after == "authorized"
    if condition in {"lock-release-failed", "foreign-git-state"}:
        return after == before
    return False


def _merge_current_head_contained(current: dict[str, object]) -> bool:
    candidate = current.get("candidate")
    integration = current.get("integration")
    push = integration.get("push") if isinstance(integration, dict) else None
    observed = (
        integration.get("observed") if isinstance(integration, dict) else None
    )
    attempts = push.get("attempted_heads") if isinstance(push, dict) else None
    candidate_head = (
        candidate.get("candidate_head") if isinstance(candidate, dict) else None
    )
    return bool(
        isinstance(candidate_head, str)
        and isinstance(push, dict)
        and isinstance(attempts, list)
        and attempts
        and attempts[-1] == candidate_head
        and push.get("intended_head") == candidate_head
        and push.get("landed_head") == candidate_head
        and isinstance(observed, dict)
        and observed.get("contains_intended_head") is True
    )


def _merge_older_head_only_contained(current: dict[str, object]) -> bool:
    candidate = current.get("candidate")
    integration = current.get("integration")
    push = integration.get("push") if isinstance(integration, dict) else None
    observed = (
        integration.get("observed") if isinstance(integration, dict) else None
    )
    attempts = push.get("attempted_heads") if isinstance(push, dict) else None
    candidate_head = (
        candidate.get("candidate_head") if isinstance(candidate, dict) else None
    )
    landed_head = push.get("landed_head") if isinstance(push, dict) else None
    containment = (
        observed.get("attempted_head_containment")
        if isinstance(observed, dict)
        else None
    )
    return bool(
        isinstance(candidate_head, str)
        and isinstance(push, dict)
        and isinstance(attempts, list)
        and len(attempts) >= 2
        and attempts[-1] == candidate_head
        and push.get("intended_head") == candidate_head
        and isinstance(landed_head, str)
        and landed_head != candidate_head
        and landed_head in attempts[:-1]
        and isinstance(observed, dict)
        and observed.get("contains_intended_head") is False
        and isinstance(containment, list)
        and any(
            isinstance(item, dict)
            and item.get("head") == landed_head
            and item.get("contained") is True
            for item in containment
        )
    )


def _merge_remote_observation_phase(
    current: dict[str, object], context: dict[str, object] | None
) -> str | None:
    integration = current.get("integration")
    intent = integration.get("intent") if isinstance(integration, dict) else None
    epoch = context.get("epoch_intent") if isinstance(context, dict) else None
    push_intent = context.get("push_intent") if isinstance(context, dict) else None
    generation = _merge_generation(current.get("candidate"))
    if (
        not isinstance(intent, dict)
        or set(intent) != _MERGE_REMOTE_OBSERVATION_INTENT_FIELDS
        or intent.get("schema") != "forge-remote-observation-intent/1"
        or intent.get("transaction") != "merge"
        or intent.get("chain_id") != current.get("chain_id")
        or intent.get("phase") not in {"final-prepush", "post-push"}
        or not isinstance(epoch, dict)
        or not _merge_hex(epoch.get("digest"))
        or intent.get("attempt_identity") != epoch.get("digest")
        or generation is None
        or epoch.get("generation_digest") != generation[1]
    ):
        return None
    phase = str(intent["phase"])
    if phase == "final-prepush":
        if (
            intent.get("push_intent_digest") is not None
            or epoch.get("push_consumed") is not False
        ):
            return None
    elif (
        not isinstance(push_intent, dict)
        or not _merge_hex(push_intent.get("digest"))
        or push_intent.get("generation_digest") != generation[1]
        or intent.get("push_intent_digest") != push_intent.get("digest")
        or epoch.get("push_consumed") is not True
    ):
        return None
    return phase


def _merge_push_observation_evidence_valid(
    event: dict[str, object],
    prior: dict[str, object],
    current: dict[str, object],
    context: dict[str, object] | None,
) -> bool:
    """Validate the closed final-prepush/post-push observation classifiers."""

    phase = _merge_remote_observation_phase(current, context)
    prior_integration = prior.get("integration")
    current_integration = current.get("integration")
    if (
        phase is None
        or not isinstance(prior_integration, dict)
        or not isinstance(current_integration, dict)
    ):
        return False
    observed = current_integration.get("observed")
    if not isinstance(observed, dict):
        return False
    if any(
        prior_integration.get(name) != current_integration.get(name)
        for name in ("epoch", "pre_rebase", "conflict")
    ):
        return False
    condition = current_integration.get("condition")
    primary = current_integration.get("primary_condition")
    movement_count = current_integration.get("remote_movement_count")
    prior_count = prior_integration.get("remote_movement_count")
    if (
        primary != "none"
        or type(movement_count) is not int
        or type(prior_count) is not int
    ):
        return False
    before = prior.get("state")
    after = current.get("state")
    event_at = _utc_value(event.get("at"))
    deadline = _utc_value(prior.get("inactive_after"))
    if event_at is None or deadline is None:
        return False
    inactive = event_at >= deadline
    exists = observed.get("exists")

    if phase == "final-prepush":
        if (
            inactive
            or before not in {"rebasing", "reverifying"}
            or current_integration.get("push") != prior_integration.get("push")
        ):
            return False
        candidate = current.get("candidate")
        remote_tip = (
            candidate.get("remote_tip") if isinstance(candidate, dict) else None
        )
        if exists is True and observed.get("oid") == remote_tip:
            return bool(
                after == before
                and condition == "none"
                and movement_count == prior_count
            )
        if exists in {True, False}:
            next_count = int(prior_count) + 1
            return bool(
                (next_count < 8 and after == "authorized" and condition == "remote-moved")
                or (
                    next_count == 8
                    and after == "awaiting_approval"
                    and condition == "remote-churn"
                )
            ) and movement_count == next_count
        return bool(
            exists is None
            and after == "authorized"
            and condition == "fetch-failed"
            and movement_count == 0
        )

    prior_push = prior_integration.get("push")
    current_push = current_integration.get("push")
    if (
        before != "pushing"
        or not isinstance(prior_push, dict)
        or not isinstance(current_push, dict)
        or any(
            prior_push.get(name) != current_push.get(name)
            for name in (
                "expected_old_tip",
                "intended_head",
                "destination_ref",
                "intended_at",
                "attempted_heads",
            )
        )
        or (
            prior_push.get("result") is not None
            and prior_push.get("result") != current_push.get("result")
        )
    ):
        return False
    result = current_push.get("result")
    classification = result.get("classification") if isinstance(result, dict) else None
    if _merge_current_head_contained(current):
        return bool(
            after == "pushed"
            and condition == "none"
            and movement_count == 0
        )
    if _merge_older_head_only_contained(current):
        return bool(
            after == (before if inactive else "authorized")
            and condition == "remote-moved"
            and movement_count == 0
        )
    vector = observed.get("attempted_head_containment")
    all_false = bool(
        observed.get("contains_intended_head") is False
        and isinstance(vector, list)
        and vector
        and all(
            isinstance(item, dict) and item.get("contained") is False
            for item in vector
        )
    )
    if exists is None:
        return bool(
            after == "pushing"
            and condition == "push-outcome-unknown"
            and movement_count == 0
        )
    if not all_false:
        return False
    if inactive:
        expected_inactive_condition = {
            "known-failure": "push-failed",
            "outcome-unknown": "push-outcome-unknown",
        }.get(classification, prior_integration.get("condition"))
        return bool(
            after == "pushing"
            and condition == expected_inactive_condition
            and condition in {"none", "push-failed", "push-outcome-unknown"}
            and movement_count == 0
        )
    old_tip_unchanged = bool(
        exists is True and observed.get("oid") == current_push.get("expected_old_tip")
    )
    if old_tip_unchanged:
        expected_condition = {
            "known-failure": "push-failed",
            "outcome-unknown": "push-outcome-unknown",
            "non-fast-forward": "non-fast-forward",
        }.get(classification, "none")
        return bool(
            after == "pushing"
            and condition == expected_condition
            and movement_count == 0
        )
    if classification in {"success", "non-fast-forward"}:
        next_count = int(prior_count) + 1
        expected_condition = (
            "remote-churn"
            if next_count == 8
            else "non-fast-forward"
            if classification == "non-fast-forward"
            else "remote-moved"
        )
        expected_state = "awaiting_approval" if next_count == 8 else "authorized"
        return bool(
            next_count <= 8
            and after == expected_state
            and condition == expected_condition
            and movement_count == next_count
        )
    return bool(
        after == "authorized"
        and condition == "remote-moved"
        and movement_count == 0
    )


def _merge_introduced_gate_fact(
    prior: dict[str, object], current: dict[str, object]
) -> tuple[str, dict[str, object]] | None:
    prior_steps = prior.get("steps")
    current_steps = current.get("steps")
    if not isinstance(prior_steps, dict) or not isinstance(current_steps, dict):
        return None
    changed = [
        name
        for name in set(prior_steps) | set(current_steps)
        if prior_steps.get(name) != current_steps.get(name)
    ]
    if len(changed) != 1:
        return None
    step_id = str(changed[0])
    old_value = prior_steps.get(step_id)
    new_value = current_steps.get(step_id)
    fact: object = new_value
    if isinstance(new_value, list):
        old_runs = old_value if isinstance(old_value, list) else []
        if len(new_value) != len(old_runs) + 1 or new_value[:-1] != old_runs:
            return None
        fact = new_value[-1]
    elif old_value is not None:
        return None
    if not isinstance(fact, dict):
        return None
    return step_id, fact


def _merge_expected_record_signatures(
    event_name: str,
    prior: dict[str, object],
    current: dict[str, object],
) -> tuple[tuple[str, str, str], ...]:
    """Derive the ordinary rows for facts first made durable by an event."""

    signatures: list[tuple[str, str, str]] = []
    if event_name == "gate_recorded":
        introduced = _merge_introduced_gate_fact(prior, current)
        fact = introduced[1] if introduced is not None else None
        if (
            isinstance(fact, dict)
            and fact.get("result") in {"passed", "failed"}
            and isinstance(fact.get("criterion"), str)
        ):
            signatures.append(
                ("verification", "criterion", str(fact["criterion"]))
            )

    if event_name in {"review_attached", "generation_carried_forward"}:
        review = _review_binding_for_state(current)
        prior_review = _review_binding_for_state(prior)
        if review is not None and (
            event_name == "generation_carried_forward" or review != prior_review
        ):
            signatures.append(
                ("verification", "criterion", journal.GATE_3_CRITERION)
            )

    if event_name in {"approval_recorded", "generation_carried_forward"}:
        approval = current.get("approval")
        prior_approval = prior.get("approval")
        candidate = _merge_generation(current.get("candidate"))
        if (
            isinstance(approval, dict)
            and candidate is not None
            and (
                event_name == "generation_carried_forward"
                or approval != prior_approval
            )
            and approval.get("purpose") == "gate-4"
            and approval.get("chain_id") == current.get("chain_id")
            and approval.get("candidate") == candidate[0].get("candidate_head")
            and approval.get("generation_digest") == candidate[1]
        ):
            signatures.append(("decision", "outcome", "chain-approval"))

    if event_name == "push_observed":
        if (
            prior.get("state") != "pushed"
            and current.get("state") == "pushed"
            and _merge_current_head_contained(current)
        ):
            signatures.append(("decision", "outcome", "chain-landing"))
    return tuple(signatures)


def _merge_outbox_matches_expected_records(
    event_name: str,
    payload: dict[str, object],
    prior: dict[str, object],
    current: dict[str, object],
) -> bool:
    """Require a batch iff this bound event first establishes journal facts."""

    signatures = _merge_expected_record_signatures(event_name, prior, current)
    expected = signatures if current.get("run_binding") is not None else ()
    has_batch = "journal_batch" in payload
    if has_batch != bool(expected):
        return False
    if not has_batch:
        return True
    batch_value = payload.get("journal_batch")
    if not isinstance(batch_value, dict):
        return False
    records = batch_value.get("records")
    if (
        not isinstance(records, list)
        or len(records) != len(expected)
        or batch_value.get("record_count") != len(expected)
    ):
        return False
    return all(
        isinstance(record, dict)
        and record.get("type") == record_type
        and record.get(field) == value
        for record, (record_type, field, value) in zip(
            records, expected, strict=True
        )
    )


def _merge_state_edge_valid(
    event_name: str,
    before: str,
    after: str,
    current: dict[str, object],
    *,
    prior_inactive: bool,
    delta: dict[str, object],
    observation_phase: str | None = None,
) -> bool:
    if before not in _MERGE_STATES or after not in _MERGE_STATES:
        return False
    if event_name in {"ownership_intent", "ownership_claimed"}:
        return before == after == "classifying"
    if event_name in {"ownership_release_intent", "ownership_released"}:
        return before in _MERGE_NONTERMINAL_STATES and after == before
    if event_name == "gate_recorded":
        return (before == "verifying" and after in {"verifying", "reviewing"}) or (
            before == "reverifying"
            and after in {"reverifying", "reverification_failed"}
        )
    if event_name == "review_requested":
        return before == after == "reviewing"
    if event_name == "review_attached":
        return before == "reviewing" and after in {
            "reviewing",
            "revising",
            "awaiting_approval",
            "authorized",
        }
    if event_name == "review_disposition":
        return before == after and before in {"reviewing", "revising"}
    if event_name == "approval_recorded":
        return (before == after and before in {"reviewing", "revising"}) or (
            before == "awaiting_approval" and after == "authorized"
        )
    if event_name == "generation_refreshed":
        return before in _MERGE_MUTABLE_PREPUSH_STATES and after == "verifying"
    if event_name == "generation_carried_forward":
        return before in {"rebasing", "reverifying"} and after in {
            "reverifying",
            "authorized",
            "awaiting_approval",
        }
    if event_name == "epoch_intent":
        return before == "authorized" and after == "rebasing"
    if event_name == "fetch_intent":
        return (
            (before in _MERGE_MUTABLE_PREPUSH_STATES and after == "classifying")
            or (before == after == "rebasing")
        )
    if event_name == "fetch_result":
        return (before == "classifying" and after in {"classifying", "verifying"}) or (
            before in {"rebasing", "reverifying"}
            and after in {"rebasing", "authorized"}
        )
    if event_name == "rebase_intent":
        return before == after and before in {"rebasing", "rebase_conflict"}
    if event_name == "rebase_conflict":
        return before in {"rebasing", "rebase_conflict"} and after == "rebase_conflict"
    if event_name == "rebase_result":
        return (
            before == "rebasing"
            and after
            in {"rebasing", "rebase_conflict", "reverifying", "revising", "authorized"}
        ) or (
            before == "rebase_conflict"
            and after in {"rebase_conflict", "reverifying", "revising"}
        )
    if event_name == "reverification_result":
        return before == "reverifying" and after in {
            "reverifying",
            "reverification_failed",
            "reviewing",
            "revising",
        }
    if event_name == "push_intent":
        return before in {"rebasing", "reverifying"} and after == "pushing"
    if event_name == "push_observed":
        if "integration" not in delta:
            return False
        if observation_phase == "final-prepush":
            return before in {"rebasing", "reverifying"} and after in {
                before,
                "authorized",
                "awaiting_approval",
            }
        if _merge_current_head_contained(current):
            return before in _MERGE_NONTERMINAL_STATES and after == "pushed"
        if prior_inactive:
            return before in _MERGE_NONTERMINAL_STATES and after == before
        if _merge_older_head_only_contained(current):
            return before in _MERGE_NONTERMINAL_STATES and after == "authorized"
        if before in {"rebasing", "reverifying"}:
            return after in {before, "authorized", "awaiting_approval"}
        if before == "pushing":
            return after in {"pushing", "authorized", "awaiting_approval"}
        return False
    if event_name == "cleanup_intent":
        return before == after and before in {"pushed", "cleanup_pending"}
    if event_name == "cleanup_result":
        return (before == "pushed" and after in {"pushed", "cleanup_pending"}) or (
            before == after == "cleanup_pending"
        )
    if event_name == "condition_recorded":
        return _merge_condition_transition_valid(before, after, current)
    if event_name in {"lock_release_result", "journal_receipted"}:
        return after == before
    if event_name == "aborted":
        return before in _MERGE_NONTERMINAL_STATES and after == "aborted"
    if event_name == "closed":
        return before in {"pushed", "cleanup_pending"} and after == "closed"
    return False


def _merge_payload_delta(
    event: dict[str, object], prior: dict[str, object] | None = None
) -> dict[str, object]:
    """Return the normative projection change for one exact event carrier."""

    event_name = event.get("event")
    payload = event.get("payload")
    if (
        event_name not in _MERGE_EVENT_NAMES
        or event_name == "journal_receipted"
        or not isinstance(payload, dict)
    ):
        raise ValueError("merge transition payload is malformed")
    direct_fields = _MERGE_EVENT_EVIDENCE_FIELDS.get(str(event_name))
    if event_name == "fetch_intent" and event.get("generation_digest") is None:
        direct_fields = _MERGE_BOOTSTRAP_FETCH_EVIDENCE_FIELDS
    elif event_name == "condition_recorded" and "quarantine" in payload:
        direct_fields = _MERGE_QUARANTINE_EVIDENCE_FIELDS
    elif event_name == "aborted" and "terminal_disposition" in payload:
        direct_fields = _MERGE_HISTORICAL_ABORT_EVIDENCE_FIELDS
    if direct_fields is not None:
        if set(payload) != set(direct_fields) or prior is None:
            raise ValueError("merge direct event payload is malformed")
        if event_name in {"ownership_intent", "ownership_claimed"}:
            worktree = copy.deepcopy(prior.get("worktree"))
            claim = worktree.get("claim") if isinstance(worktree, dict) else None
            if not isinstance(claim, dict):
                raise ValueError("merge ownership projection is malformed")
            if event_name == "ownership_intent":
                claim.update(
                    {
                        "status": "unpublished",
                        "path": payload["claim_path"],
                        "inode": None,
                        "digest": payload["intended_claim_digest"],
                    }
                )
            else:
                claim.update(
                    {
                        "status": "owned",
                        "inode": payload["claim_inode"],
                        "digest": payload["claim_digest"],
                    }
                )
            return {"worktree": worktree}
        if event_name in {"ownership_release_intent", "ownership_released"}:
            worktree = copy.deepcopy(prior.get("worktree"))
            claim = worktree.get("claim") if isinstance(worktree, dict) else None
            if not isinstance(claim, dict):
                raise ValueError("merge release projection is malformed")
            if event_name == "ownership_release_intent":
                claim["status"] = "releasing"
            else:
                claim.update(
                    {
                        "status": "released",
                        "inode": payload["claim_inode"],
                        "digest": payload["claim_digest"],
                    }
                )
            return {"worktree": worktree}
        if event_name == "fetch_intent":
            integration = copy.deepcopy(prior.get("integration"))
            if not isinstance(integration, dict):
                raise ValueError("merge fetch projection is malformed")
            integration["intent"] = {
                "operation": "fetch",
                **copy.deepcopy(payload),
            }
            return {"integration": integration}
        if event_name == "condition_recorded":
            integration = copy.deepcopy(prior.get("integration"))
            if not isinstance(integration, dict):
                raise ValueError("merge condition projection is malformed")
            integration["condition"] = payload["condition"]
            return {"integration": integration}
        if event_name == "aborted":
            return {"state": "aborted"}
        raise ValueError("unsupported merge direct event payload")
    has_source = "source_event_digest" in payload
    has_batch = "journal_batch" in payload
    carried = payload.get("journal_batch")
    allowed = {"delta"}
    if has_source or has_batch:
        allowed.update({"source_event_digest", "journal_batch"})
    delta = payload.get("delta")
    if (
        has_source != has_batch
        or set(payload) != allowed
        or not isinstance(delta, dict)
        or not delta
        or any(name in _MERGE_DERIVED_STATE_FIELDS for name in delta)
        or (has_batch and event_name not in _MERGE_OUTBOX_PRODUCERS)
        or (
            has_source
            and (
                not _merge_hex(payload.get("source_event_digest"))
                or not isinstance(carried, dict)
                or set(carried)
                != {"idempotency_key", "batch_digest", "record_count", "records"}
                or carried.get("idempotency_key")
                != payload.get("source_event_digest")
                or not _merge_hex(carried.get("batch_digest"))
                or type(carried.get("record_count")) is not int
                or int(carried["record_count"]) <= 0
                or not isinstance(carried.get("records"), list)
                or len(carried["records"]) != carried["record_count"]
                or not all(
                    isinstance(record, dict) for record in carried["records"]
                )
            )
        )
    ):
        raise ValueError("merge transition payload is malformed")
    projected = copy.deepcopy(delta)
    if event_name == "epoch_intent":
        integration = projected.get("integration")
        epoch = integration.get("epoch") if isinstance(integration, dict) else None
        if (
            not isinstance(epoch, dict)
            or set(epoch)
            != {
                "operation_nonce",
                "generation_digest",
                "intent_digest",
                "started_at",
            }
            or epoch.get("intent_digest") is not None
            or not _merge_hex(event.get("digest"))
        ):
            raise ValueError("merge epoch intent projection is malformed")
        # The authoritative fresh-attempt identity is the outer epoch event's
        # digest.  Its hashed delta carries a null derived slot so the digest is
        # nonrecursive; replay fills that slot only after the outer event digest
        # has been authenticated by the event-log reader.
        epoch["intent_digest"] = event["digest"]
    return projected


def _merge_hex(value: object) -> bool:
    return bool(
        isinstance(value, str)
        and journal.HEX_SHA256_PATTERN.fullmatch(value) is not None
    )


def _merge_predecessor_pair_valid(payload: dict[str, object]) -> bool:
    predecessor_chain = payload.get("predecessor_chain_id")
    predecessor_release = payload.get("predecessor_release_digest")
    if predecessor_chain is None or predecessor_release is None:
        return predecessor_chain is None and predecessor_release is None
    return bool(
        isinstance(predecessor_chain, str)
        and journal.CHAIN_ID_PATTERN.fullmatch(predecessor_chain) is not None
        and _merge_hex(predecessor_release)
    )


def _merge_event_evidence_valid(
    event: dict[str, object],
    prior: dict[str, object],
    current: dict[str, object],
    *,
    context: dict[str, object] | None,
) -> bool:
    """Validate and, on success, advance cross-event DM-014 evidence."""

    event_name = str(event.get("event"))
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return False
    prior_worktree = _merge_worktree_claim(prior)
    current_worktree = _merge_worktree_claim(current)
    if prior_worktree is None or current_worktree is None:
        return False
    prior_identity, prior_claim = prior_worktree
    current_identity, current_claim = current_worktree
    next_context = copy.deepcopy(context) if context is not None else None

    current_integration = current.get("integration")
    current_epoch = (
        current_integration.get("epoch")
        if isinstance(current_integration, dict)
        else None
    )
    replayed_epoch = (
        context.get("epoch_intent") if isinstance(context, dict) else None
    )
    if current_epoch is not None:
        if not isinstance(current_epoch, dict):
            return False
        if event_name == "epoch_intent":
            if current_epoch.get("intent_digest") != event.get("digest"):
                return False
        elif (
            not isinstance(replayed_epoch, dict)
            or current_epoch.get("intent_digest") != replayed_epoch.get("digest")
            or current_epoch.get("generation_digest")
            != replayed_epoch.get("generation_digest")
        ):
            return False

    if event_name == "ownership_intent":
        identity = {
            name: current_identity[name]
            for name in ("path", "git_dir", "common_dir")
        }
        intended_claim_digest = _merge_claim_record_digest(current, current_identity)
        if (
            (isinstance(context, dict) and "ownership_intent" in context)
            or
            payload.get("worktree_digest")
            != journal._sha256(journal._canonical_json_bytes(identity))
            or payload.get("claim_path") != current_claim.get("path")
            or payload.get("intended_claim_digest")
            != intended_claim_digest
            or current_claim.get("digest") != intended_claim_digest
            or not _merge_predecessor_pair_valid(payload)
        ):
            return False
        if next_context is not None:
            next_context["ownership_intent"] = {
                "digest": event.get("digest"),
                "payload": {
                    name: copy.deepcopy(payload[name])
                    for name in _MERGE_EVENT_EVIDENCE_FIELDS[event_name]
                },
            }
    elif event_name == "ownership_claimed":
        intent = context.get("ownership_intent") if context is not None else None
        intent_payload = intent.get("payload") if isinstance(intent, dict) else None
        if (
            (isinstance(context, dict) and "ownership_claimed" in context)
            or
            payload.get("ownership_intent_digest")
            != event.get("previous_digest")
            or not _merge_hex(payload.get("ownership_intent_digest"))
            or payload.get("claim_inode") != current_claim.get("inode")
            or payload.get("claim_digest") != current_claim.get("digest")
            or not _merge_hex(payload.get("claim_digest"))
            or not _merge_predecessor_pair_valid(payload)
            or (
                context is not None
                and (
                    not isinstance(intent, dict)
                    or intent.get("digest") != payload.get("ownership_intent_digest")
                    or not isinstance(intent_payload, dict)
                    or intent_payload.get("intended_claim_digest")
                    != payload.get("claim_digest")
                    or intent_payload.get("claim_path")
                    != current_claim.get("path")
                    or intent_payload.get("predecessor_chain_id")
                    != payload.get("predecessor_chain_id")
                    or intent_payload.get("predecessor_release_digest")
                    != payload.get("predecessor_release_digest")
                )
            )
        ):
            return False
        if next_context is not None:
            next_context["ownership_claimed"] = {
                "digest": event.get("digest")
            }
    elif event_name == "fetch_intent" and event.get("generation_digest") is None:
        integration = current.get("integration")
        intent = integration.get("intent") if isinstance(integration, dict) else None
        if (
            payload.get("repository") != current.get("repository")
            or payload.get("worktree")
            != {
                name: current_identity[name]
                for name in ("path", "git_dir", "common_dir")
            }
            or payload.get("branch") != current.get("branch")
            or payload.get("target") != current.get("target")
            or not isinstance(payload.get("pre_fetch_head"), str)
            or journal.GIT_OBJECT_ID_PATTERN.fullmatch(
                str(payload["pre_fetch_head"])
            )
            is None
            or not _merge_hex(payload.get("policy_digest"))
            or not isinstance(payload.get("operation_nonce"), str)
            or re.fullmatch(r"[0-9a-f]{32}", str(payload["operation_nonce"]))
            is None
            or type(payload.get("attempt")) is not int
            or int(payload["attempt"]) <= 0
            or not isinstance(intent, dict)
            or any(
                intent.get(name) != payload.get(name)
                for name in _MERGE_BOOTSTRAP_FETCH_EVIDENCE_FIELDS
            )
        ):
            return False
    elif event_name == "ownership_release_intent":
        release_mode = payload.get("release_mode")
        disposition = payload.get("terminal_disposition")
        target = payload.get("target_terminal")
        source_state = payload.get("source_state")
        cleanup = prior.get("cleanup")
        event_at = _utc_value(event.get("at"))
        prior_deadline = _utc_value(prior.get("inactive_after"))
        if (
            (
                isinstance(context, dict)
                and (
                    "release_intent" in context
                    or "release_result" in context
                )
            )
            or
            target not in {"aborted", "closed"}
            or disposition
            not in {"ordinary", "historical-landed-superseded"}
            or source_state != prior.get("state")
            or not _merge_hex(payload.get("terminal_preconditions_digest"))
            or release_mode
            != ("acquired" if prior_claim.get("status") == "owned" else "never-published")
            or (target == "closed" and source_state not in {"pushed", "cleanup_pending"})
            or (target == "aborted" and source_state in {"pushed", "cleanup_pending"})
            or (disposition == "historical-landed-superseded" and target != "aborted")
            or (
                target == "closed"
                and (
                    not isinstance(cleanup, dict)
                    or cleanup.get("condition") != "none"
                    or not _merge_current_head_contained(prior)
                )
            )
            or (
                disposition == "historical-landed-superseded"
                and (
                    event_at is None
                    or prior_deadline is None
                    or event_at < prior_deadline
                    or not _merge_older_head_only_contained(prior)
                )
            )
        ):
            return False
        if next_context is not None:
            next_context["release_intent"] = {
                "digest": event.get("digest"),
                "payload": {
                    name: copy.deepcopy(payload[name])
                    for name in _MERGE_EVENT_EVIDENCE_FIELDS[event_name]
                },
            }
            next_context.pop("release_result", None)
    elif event_name == "ownership_released":
        release = context.get("release_intent") if context is not None else None
        release_payload = release.get("payload") if isinstance(release, dict) else None
        release_mode = payload.get("release_mode")
        observation = {
            "claim_path": current_claim.get("path"),
            "exists": release_mode == "acquired",
            "inode": (
                current_claim.get("inode") if release_mode == "acquired" else None
            ),
            "digest": (
                current_claim.get("digest") if release_mode == "acquired" else None
            ),
        }
        expected_observation_digest = journal._sha256(
            journal._canonical_json_bytes(observation)
        )
        if (
            (isinstance(context, dict) and "release_result" in context)
            or
            payload.get("release_intent_digest") != event.get("previous_digest")
            or not _merge_hex(payload.get("release_intent_digest"))
            or payload.get("release_mode")
            not in {"acquired", "never-published"}
            or payload.get("terminal_disposition")
            not in {"ordinary", "historical-landed-superseded"}
            or payload.get("claim_inode") != current_claim.get("inode")
            or payload.get("claim_digest") != current_claim.get("digest")
            or not _merge_hex(payload.get("claim_digest"))
            or payload.get("claim_observation_digest")
            != expected_observation_digest
            or (
                context is not None
                and (
                    not isinstance(release, dict)
                    or release.get("digest") != payload.get("release_intent_digest")
                    or not isinstance(release_payload, dict)
                    or release_payload.get("release_mode")
                    != payload.get("release_mode")
                    or release_payload.get("terminal_disposition")
                    != payload.get("terminal_disposition")
                )
            )
        ):
            return False
        if next_context is not None:
            next_context["release_result"] = {
                "digest": event.get("digest"),
                "payload": {
                    name: copy.deepcopy(payload[name])
                    for name in _MERGE_EVENT_EVIDENCE_FIELDS[event_name]
                },
            }
    elif event_name in {"closed", "aborted"}:
        release = context.get("release_intent") if context is not None else None
        released = context.get("release_result") if context is not None else None
        release_payload = release.get("payload") if isinstance(release, dict) else None
        if context is not None and (
            not isinstance(release, dict)
            or not isinstance(released, dict)
            or released.get("digest") != event.get("previous_digest")
            or not isinstance(release_payload, dict)
            or release_payload.get("target_terminal") != event_name
            or release_payload.get("source_state") != prior.get("state")
        ):
            return False
        disposition = (
            release_payload.get("terminal_disposition")
            if isinstance(release_payload, dict)
            else None
        )
        if disposition == "historical-landed-superseded":
            integration = current.get("integration")
            push = integration.get("push") if isinstance(integration, dict) else None
            observed = (
                integration.get("observed") if isinstance(integration, dict) else None
            )
            if (
                event_name != "aborted"
                or set(payload)
                != set(_MERGE_HISTORICAL_ABORT_EVIDENCE_FIELDS)
                or payload.get("terminal_disposition") != disposition
                or not isinstance(push, dict)
                or payload.get("landed_head") != push.get("landed_head")
                or payload.get("superseded_head") != push.get("intended_head")
                or not isinstance(observed, dict)
                or payload.get("observation_digest")
                not in {observed.get("output_digest"), observed.get("inflight_digest")}
            ):
                return False
        elif any(name in payload for name in _MERGE_HISTORICAL_ABORT_EVIDENCE_FIELDS):
            return False
    elif event_name == "condition_recorded":
        prior_integration = prior.get("integration")
        current_integration = current.get("integration")
        prior_cleanup = prior.get("cleanup")
        current_cleanup = current.get("cleanup")
        if any(name in payload for name in _MERGE_QUARANTINE_EVIDENCE_FIELDS):
            if (
                payload.get("condition") != "foreign-git-state"
                or not isinstance(payload.get("quarantine"), list)
                or not payload["quarantine"]
                or not _merge_hex(payload.get("observation_digest"))
                or not isinstance(current_integration, dict)
                or current_integration.get("condition") != "foreign-git-state"
            ):
                return False
        elif not (
            isinstance(prior_integration, dict)
            and isinstance(current_integration, dict)
            and isinstance(prior_cleanup, dict)
            and isinstance(current_cleanup, dict)
        ):
            return False
        else:
            integration_condition_changed = (
                prior_integration.get("condition")
                != current_integration.get("condition")
                or prior_integration.get("primary_condition")
                != current_integration.get("primary_condition")
            )
            cleanup_condition_changed = (
                prior_cleanup.get("condition")
                != current_cleanup.get("condition")
            )
            if integration_condition_changed == cleanup_condition_changed:
                return False
            if cleanup_condition_changed:
                if (
                    current_cleanup.get("condition") != "cleanup-failed"
                    or current_integration != prior_integration
                ):
                    return False
            else:
                condition = current_integration.get("condition")
                primary = current_integration.get("primary_condition")
                if (
                    current_cleanup != prior_cleanup
                    or condition == prior_integration.get("condition")
                    or condition == "none"
                    or (
                        condition == "lock-release-failed"
                        and primary != prior_integration.get("condition")
                    )
                    or (
                        condition != "lock-release-failed"
                        and primary != "none"
                    )
                ):
                    return False
    elif event_name == "cleanup_intent":
        cleanup = current.get("cleanup")
        cleanup_intent = cleanup.get("intent") if isinstance(cleanup, dict) else None
        if (
            prior.get("state") not in {"pushed", "cleanup_pending"}
            or current.get("state") != prior.get("state")
            or not _merge_current_head_contained(prior)
            or not _merge_current_head_contained(current)
            or not isinstance(cleanup_intent, dict)
            or not isinstance(cleanup_intent.get("operation_nonce"), str)
            or re.fullmatch(
                r"[0-9a-f]{32}", str(cleanup_intent["operation_nonce"])
            )
            is None
            or cleanup_intent.get("generation_digest")
            != event.get("generation_digest")
            or _utc_value(cleanup_intent.get("started_at")) is None
        ):
            return False
    elif event_name == "cleanup_result":
        cleanup = current.get("cleanup")
        if (
            prior.get("state") not in {"pushed", "cleanup_pending"}
            or not _merge_current_head_contained(prior)
            or not _merge_current_head_contained(current)
            or not isinstance(cleanup, dict)
            or (
                cleanup.get("condition") == "cleanup-failed"
                and current.get("state") != "cleanup_pending"
            )
        ):
            return False
    elif event_name == "lock_release_result":
        prior_integration = prior.get("integration")
        current_integration = current.get("integration")
        if not isinstance(prior_integration, dict) or not isinstance(
            current_integration, dict
        ):
            return False
        retained_keys = set(prior_integration) - {
            "condition",
            "primary_condition",
        }
        if any(
            prior_integration.get(name) != current_integration.get(name)
            for name in retained_keys
        ):
            return False
        failed_release = bool(
            prior_integration.get("condition") != "lock-release-failed"
            and current_integration.get("condition") == "lock-release-failed"
            and current_integration.get("primary_condition")
            == prior_integration.get("condition")
        )
        completed_release = bool(
            prior_integration.get("condition") == "lock-release-failed"
            and current_integration.get("condition")
            == prior_integration.get("primary_condition")
            and current_integration.get("primary_condition") == "none"
        )
        if not (failed_release or completed_release):
            return False

    if next_context is not None:
        event_at = _utc_value(event.get("at"))
        prior_deadline = _utc_value(prior.get("inactive_after"))
        if event_name == "epoch_intent":
            next_context["epoch_intent"] = {
                "digest": event.get("digest"),
                "generation_digest": event.get("generation_digest"),
                "push_consumed": False,
            }
        if event_name == "push_intent":
            epoch_intent = context.get("epoch_intent") if context is not None else None
            if (
                not isinstance(epoch_intent, dict)
                or epoch_intent.get("generation_digest")
                != event.get("generation_digest")
                or epoch_intent.get("push_consumed") is True
            ):
                return False
            next_context["epoch_intent"]["push_consumed"] = True
        if (
            event_name == "push_observed"
            and _merge_remote_observation_phase(current, context) == "final-prepush"
        ):
            current_integration = current.get("integration")
            if (
                current.get("state") != prior.get("state")
                or (
                    isinstance(current_integration, dict)
                    and current_integration.get("condition") != "none"
                )
            ):
                next_context["epoch_intent"]["push_consumed"] = True

        intent_names = {
            "fetch_intent": "fetch",
            "rebase_intent": "rebase",
            "push_intent": "push",
            "cleanup_intent": "cleanup",
        }
        result_names = {
            "fetch_result": "fetch",
            "rebase_conflict": "rebase",
            "rebase_result": "rebase",
            "cleanup_result": "cleanup",
        }
        if event_name in intent_names:
            integration = current.get("integration")
            cleanup_state = current.get("cleanup")
            if event_name == "cleanup_intent":
                intent_value: object = (
                    cleanup_state.get("intent")
                    if isinstance(cleanup_state, dict)
                    else None
                )
            else:
                intent_value = (
                    integration.get("intent")
                    if isinstance(integration, dict)
                    else None
                )
            next_context[f"{intent_names[event_name]}_intent"] = {
                "digest": event.get("digest"),
                "generation_digest": event.get("generation_digest"),
                "evidence": copy.deepcopy(intent_value),
                "admitted_active": bool(
                    (
                        event_at is not None
                        and prior_deadline is not None
                        and event_at < prior_deadline
                    )
                    or (
                        event_name == "cleanup_intent"
                        and prior.get("state")
                        in {"pushed", "cleanup_pending"}
                        and _merge_current_head_contained(prior)
                    )
                ),
            }
        if event_name in result_names:
            operation = result_names[event_name]
            admitted = context.get(f"{operation}_intent") if context is not None else None
            integration = current.get("integration")
            cleanup_state = current.get("cleanup")
            if operation == "cleanup":
                current_evidence: object = (
                    cleanup_state.get("intent")
                    if isinstance(cleanup_state, dict)
                    else None
                )
            else:
                current_evidence = (
                    integration.get("intent")
                    if isinstance(integration, dict)
                    else None
                )
            admitted_evidence = (
                admitted.get("evidence") if isinstance(admitted, dict) else None
            )
            admitted_nonce = (
                admitted_evidence.get("operation_nonce")
                if isinstance(admitted_evidence, dict)
                else None
            )
            current_nonce = (
                current_evidence.get("operation_nonce")
                if isinstance(current_evidence, dict)
                else None
            )
            bootstrap_fetch_result = bool(
                operation == "fetch"
                and isinstance(admitted, dict)
                and admitted.get("generation_digest") is None
                and prior.get("candidate") is None
                and _merge_generation(current.get("candidate")) is not None
            )
            prior_result_generation = _merge_generation(prior.get("candidate"))
            current_result_generation = _merge_generation(current.get("candidate"))
            successor_generation_result = bool(
                operation in {"fetch", "rebase"}
                and isinstance(admitted, dict)
                and prior_result_generation is not None
                and current_result_generation is not None
                and admitted.get("generation_digest")
                == prior_result_generation[1]
                and event.get("generation_digest")
                == current_result_generation[1]
            )
            if (
                not isinstance(admitted, dict)
                or admitted.get("digest") != event.get("previous_digest")
                or (
                    admitted.get("generation_digest")
                    != event.get("generation_digest")
                    and not bootstrap_fetch_result
                    and not successor_generation_result
                )
                or admitted.get("admitted_active") is not True
                or (
                    admitted_nonce is not None
                    and current_nonce is not None
                    and current_nonce != admitted_nonce
                )
            ):
                return False

    if context is not None and next_context is not None:
        context.clear()
        context.update(next_context)
    return True


def _merge_transition_valid(
    event: dict[str, object],
    prior: dict[str, object] | None,
    current: dict[str, object],
    context: dict[str, object] | None = None,
) -> bool:
    event_name = event.get("event")
    payload = event.get("payload")
    event_at = _utc_value(event.get("at"))
    created_at = _utc_value(current.get("created_at"))
    last_event_at = _utc_value(current.get("last_event_at"))
    inactive_after = _utc_value(current.get("inactive_after"))
    chain_id = event.get("chain_id")
    if (
        event_name not in _MERGE_EVENT_NAMES
        or event_name not in _MERGE_EVENT_TOP_LEVEL_CHANGES
        or not isinstance(chain_id, str)
        or not _state_shape_valid(current, chain_id, "merge")
        or (
            prior is not None
            and not _state_shape_valid(prior, chain_id, "merge")
        )
        or not isinstance(payload, dict)
        or event_at is None
        or created_at is None
        or last_event_at is None
        or inactive_after is None
        or event_at != last_event_at
        or event_at < created_at
    ):
        return False

    is_receipt = event_name == "journal_receipted"
    has_source = "source_event_digest" in payload
    has_batch = "journal_batch" in payload
    if is_receipt:
        if set(payload) != {"idempotency_key", "batch_digest", "receipt_digest"}:
            return False
        delta: dict[str, object] = {}
    else:
        try:
            delta = _merge_payload_delta(event, prior)
        except (KeyError, TypeError, ValueError):
            return False

    current_generation = _merge_generation(current.get("candidate"))
    if current_generation is None:
        if (
            current.get("candidate") is not None
            or event.get("generation_digest") is not None
            or event_name not in _MERGE_BOOTSTRAP_EVENTS
        ):
            return False
    elif event.get("generation_digest") != current_generation[1]:
        return False

    current_worktree = _merge_worktree_claim(current)
    if current_worktree is None:
        return False
    _current_worktree, current_claim = current_worktree
    if prior is None:
        owner = current.get("owner")
        integration = current.get("integration")
        return bool(
            event.get("sequence") == 1
            and event_name == "chain_started"
            and set(current) == _MERGE_STATE_KEYS
            and set(delta) == _MERGE_INITIAL_DELTA_FIELDS
            and all(current.get(name) == value for name, value in delta.items())
            and current.get("schema") == "forge-merge-chain/1"
            and current.get("chain_id") == event.get("chain_id")
            and current.get("kind") == "merge"
            and current.get("state") == "classifying"
            and current.get("created_at") == event.get("at")
            and inactive_after == event_at + dt.timedelta(hours=24)
            and current.get("candidate") is None
            and current.get("tier") is None
            and current.get("steps") == {}
            and current.get("review") == {}
            and current.get("approval") == {}
            and current.get("authorization") == {}
            and isinstance(owner, dict)
            and set(owner) == {"pid", "host", "session", "started_at"}
            and type(owner.get("pid")) is int
            and int(owner["pid"]) > 0
            and isinstance(owner.get("host"), str)
            and bool(owner["host"])
            and isinstance(owner.get("session"), str)
            and bool(owner["session"])
            and owner.get("started_at") == current.get("created_at")
            and integration
            == {
                "condition": "none",
                "primary_condition": "none",
                "epoch": None,
                "remote_movement_count": 0,
                "intent": None,
                "observed": None,
                "pre_rebase": None,
                "conflict": None,
                "push": None,
            }
            and current.get("cleanup") == {"condition": "none"}
            and current_claim.get("status") == "unpublished"
            and current_claim.get("digest") is None
            and current_claim.get("inode") is None
            and current.get("journal_outbox") is None
            and not has_batch
        )
    if (
        event_name == "chain_started"
        or set(prior) != _MERGE_STATE_KEYS
        or context is None
    ):
        return False

    if not _merge_outbox_matches_expected_records(
        str(event_name), payload, prior, current
    ):
        return False

    prior_at = _utc_value(prior.get("last_event_at"))
    prior_inactive_after = _utc_value(prior.get("inactive_after"))
    if prior_at is None or prior_inactive_after is None or event_at < prior_at:
        return False
    prior_inactive = event_at >= prior_inactive_after
    expected_inactive_after = (
        prior_inactive_after
        if prior_inactive
        else event_at + dt.timedelta(hours=24)
    )
    if inactive_after != expected_inactive_after:
        return False

    immutable = (
        "schema",
        "chain_id",
        "kind",
        "created_at",
        "owner",
        "run",
        "repository",
        "branch",
        "target",
        "run_binding",
    )
    if any(prior.get(name) != current.get(name) for name in immutable):
        return False
    prior_worktree = _merge_worktree_claim(prior)
    if prior_worktree is None:
        return False
    prior_worktree_value, prior_claim = prior_worktree
    if any(
        prior_worktree_value.get(name) != _current_worktree.get(name)
        for name in ("path", "git_dir", "common_dir")
    ):
        return False

    # A durable release cutoff has absolute precedence.  Once releasing, only
    # its exact result may follow; once released but not terminal, only the
    # cutoff-selected terminal event may follow.  No unrelated observation or
    # side-effect event may interpose while retaining the claim projection.
    prior_claim_status = prior_claim.get("status")
    if prior_claim_status == "releasing" and event_name != "ownership_released":
        return False
    if (
        prior_claim_status == "released"
        and prior.get("state") in _MERGE_NONTERMINAL_STATES
        and event_name not in {"closed", "aborted"}
    ):
        return False

    changed = {
        name
        for name in _MERGE_STATE_KEYS - _MERGE_DERIVED_STATE_FIELDS
        if prior.get(name) != current.get(name)
    }
    if is_receipt:
        pending = prior.get("journal_outbox")
        if (
            changed
            or not isinstance(pending, dict)
            or current.get("journal_outbox") is not None
            or payload.get("idempotency_key")
            != pending.get("idempotency_key")
            or payload.get("batch_digest") != pending.get("batch_digest")
            or not _merge_hex(payload.get("receipt_digest"))
        ):
            return False
    else:
        required_changes = _MERGE_EVENT_REQUIRED_CHANGES.get(
            str(event_name), frozenset()
        )
        if (
            set(delta) != changed
            or any(current.get(name) != value for name, value in delta.items())
            or not required_changes <= changed
            or not changed <= _MERGE_EVENT_TOP_LEVEL_CHANGES[event_name]
        ):
            return False
        if prior.get("journal_outbox") is not None:
            return False
        if has_batch:
            outbox = current.get("journal_outbox")
            carried = payload.get("journal_batch")
            if (
                not isinstance(outbox, dict)
                or not isinstance(carried, dict)
                or outbox.get("source_event_digest")
                != payload.get("source_event_digest")
                or outbox.get("idempotency_key")
                != payload.get("source_event_digest")
                or outbox.get("batch_digest") != carried.get("batch_digest")
                or outbox.get("record_count") != carried.get("record_count")
            ):
                return False
        elif current.get("journal_outbox") != prior.get("journal_outbox"):
            return False

    before_state = prior.get("state")
    after_state = current.get("state")
    observation_phase = (
        _merge_remote_observation_phase(current, context)
        if event_name == "push_observed"
        else None
    )
    if (
        not isinstance(before_state, str)
        or not isinstance(after_state, str)
        or (
            prior_inactive
            and event_name
            not in {
                "ownership_release_intent",
                "ownership_released",
                "fetch_result",
                "rebase_conflict",
                "rebase_result",
                "reverification_result",
                "push_observed",
                "cleanup_intent",
                "cleanup_result",
                "condition_recorded",
                "lock_release_result",
                "aborted",
                "closed",
                "journal_receipted",
            }
            and not (
                event_name == "rebase_intent"
                and before_state == "rebase_conflict"
            )
        )
        or not _merge_state_edge_valid(
            str(event_name),
            before_state,
            after_state,
            current,
            prior_inactive=prior_inactive,
            delta=delta,
            observation_phase=observation_phase,
        )
        or not _merge_complete_tuple_valid(
            str(event_name), prior, current, context
        )
    ):
        return False

    record_signatures = _merge_expected_record_signatures(
        str(event_name), prior, current
    )
    if event_name == "gate_recorded":
        introduced = _merge_introduced_gate_fact(prior, current)
        if introduced is None:
            return False
        step_id, fact = introduced
        criterion = fact.get("criterion")
        valid_step = bool(
            step_id == "gate-1"
            or step_id == "assertion-sensor"
            or re.fullmatch(r"stack:[a-z0-9][a-z0-9_-]*", step_id)
            or re.fullmatch(r"invariant:[1-9][0-9]*", step_id)
        )
        expected_prefix = "gate-1: " if step_id == "gate-1" else "gate-2: "
        if (
            not valid_step
            or not isinstance(criterion, str)
            or not criterion.startswith(expected_prefix)
            or fact.get("result") not in {"passed", "failed"}
            or fact.get("generation_digest") != event.get("generation_digest")
            or len(record_signatures) != 1
            or (
                after_state == "reviewing"
                and fact.get("result") != "passed"
            )
            or (
                after_state == "reverification_failed"
                and fact.get("result") != "failed"
            )
        ):
            return False
    if event_name == "review_attached" and after_state != "reviewing":
        if (
            _review_binding_for_state(current) is None
            or not any(
                signature
                == ("verification", "criterion", journal.GATE_3_CRITERION)
                for signature in record_signatures
            )
        ):
            return False
    if event_name == "approval_recorded" and after_state == "authorized":
        approval = current.get("approval")
        if (
            isinstance(approval, dict)
            and approval.get("purpose") == "gate-4"
            and ("decision", "outcome", "chain-approval")
            not in record_signatures
        ):
            return False
    if event_name == "generation_carried_forward":
        if (
            ("verification", "criterion", journal.GATE_3_CRITERION)
            not in record_signatures
            or (
                bool(current.get("approval"))
                and ("decision", "outcome", "chain-approval")
                not in record_signatures
            )
        ):
            return False

    # Claim status is an inductive release transaction.  The terminal event
    # can be admitted only after the matching releasing -> released result,
    # and that result must preserve the release-intent identity/digest.
    prior_status = prior_claim.get("status")
    current_status = current_claim.get("status")
    if event_name == "ownership_intent":
        if not (
            prior_status == current_status == "unpublished"
            and prior_claim.get("path") == current_claim.get("path")
            and prior_claim.get("inode") is None
            and current_claim.get("inode") is None
            and current_claim.get("digest") != prior_claim.get("digest")
            and isinstance(current_claim.get("digest"), str)
        ):
            return False
    elif event_name == "ownership_claimed":
        if not (
            prior_status == "unpublished"
            and current_status == "owned"
            and prior_claim.get("path") == current_claim.get("path")
            and type(current_claim.get("inode")) is int
            and isinstance(current_claim.get("digest"), str)
        ):
            return False
    elif event_name == "ownership_release_intent":
        expected_claim = copy.deepcopy(prior_claim)
        expected_claim["status"] = "releasing"
        if not (
            prior_status in {"unpublished", "owned"}
            and current_claim == expected_claim
            and isinstance(prior_claim.get("digest"), str)
        ):
            return False
    elif event_name == "ownership_released":
        expected_claim = copy.deepcopy(prior_claim)
        expected_claim["status"] = "released"
        if prior_status != "releasing" or current_claim != expected_claim:
            return False
    elif event_name in {"aborted", "closed"}:
        if (
            prior_status != current_status
            or current_status != "released"
            or (
                event_name == "aborted"
                and before_state in {"pushed", "cleanup_pending"}
            )
        ):
            return False
    elif current_claim != prior_claim:
        return False

    # Only epoch_intent may introduce a new epoch identity.  Push intent must
    # consume or retain the currently replayed epoch; it cannot invent one in
    # the same delta.
    prior_integration = prior.get("integration")
    current_integration = current.get("integration")
    prior_epoch = (
        prior_integration.get("epoch")
        if isinstance(prior_integration, dict)
        else None
    )
    current_epoch = (
        current_integration.get("epoch")
        if isinstance(current_integration, dict)
        else None
    )
    prior_push_history = (
        prior_integration.get("push")
        if isinstance(prior_integration, dict)
        else None
    )
    current_push_history = (
        current_integration.get("push")
        if isinstance(current_integration, dict)
        else None
    )
    if (
        event_name not in {"push_intent", "push_observed"}
        and current_push_history != prior_push_history
    ):
        return False
    if event_name == "epoch_intent":
        if current_epoch is None or current_epoch == prior_epoch:
            return False
    elif current_epoch != prior_epoch:
        epoch_parked = after_state in {
            "authorized",
            "awaiting_approval",
            "revising",
            "reverification_failed",
            "pushed",
            "cleanup_pending",
            "closed",
            "aborted",
        }
        if current_epoch is not None or not (
            event_name
            in {"generation_refreshed", "generation_carried_forward", "push_intent"}
            or epoch_parked
        ):
            return False
    if event_name == "push_intent" and prior_epoch is None:
        return False

    if event_name == "push_intent":
        prior_push = (
            prior_integration.get("push")
            if isinstance(prior_integration, dict)
            else None
        )
        push = (
            current_integration.get("push")
            if isinstance(current_integration, dict)
            else None
        )
        attempts = push.get("attempted_heads") if isinstance(push, dict) else None
        prior_attempts = (
            prior_push.get("attempted_heads")
            if isinstance(prior_push, dict)
            else []
        )
        candidate = current.get("candidate")
        integration_intent = (
            current_integration.get("intent")
            if isinstance(current_integration, dict)
            else None
        )
        expected_old_landed = (
            prior_push.get("landed_head") if isinstance(prior_push, dict) else None
        )
        if (
            not isinstance(push, dict)
            or not isinstance(attempts, list)
            or not attempts
            or not isinstance(prior_attempts, list)
            or not isinstance(candidate, dict)
            or push.get("expected_old_tip") != candidate.get("remote_tip")
            or push.get("intended_head") != candidate.get("candidate_head")
            or push.get("destination_ref")
            != candidate.get("destination_ref")
            or push.get("intended_at") != event.get("at")
            or push.get("result") is not None
            or push.get("landed_head") != expected_old_landed
            or attempts[-1] != push.get("intended_head")
            or attempts != [*prior_attempts, push.get("intended_head")]
            or not isinstance(integration_intent, dict)
            or integration_intent.get("operation") != "push"
            or not isinstance(current_epoch, dict)
            or integration_intent.get("operation_nonce")
            != current_epoch.get("operation_nonce")
            or current_integration.get("observed") is not None
        ):
            return False
    if event_name == "push_observed":
        if not _merge_push_observation_evidence_valid(
            event, prior, current, context
        ):
            return False
        if _merge_remote_observation_phase(current, context) == "post-push":
            current_push = (
                current_integration.get("push")
                if isinstance(current_integration, dict)
                else None
            )
            observed = (
                current_integration.get("observed")
                if isinstance(current_integration, dict)
                else None
            )
            containment = (
                observed.get("attempted_head_containment")
                if isinstance(observed, dict)
                else None
            )
            latest_landed = None
            if isinstance(containment, list):
                for item in reversed(containment):
                    if isinstance(item, dict) and item.get("contained") is True:
                        latest_landed = item.get("head")
                        break
            if (
                not isinstance(current_push, dict)
                or current_push.get("landed_head") != latest_landed
            ):
                return False

    prior_generation = _merge_generation(prior.get("candidate"))
    if prior.get("candidate") is None:
        if current_generation is not None and (
            event_name != "fetch_result"
            or current_generation[0].get("generation") != 1
            or any(
                current.get(name) != empty
                for name, empty in (
                    ("steps", {}),
                    ("review", {}),
                    ("approval", {}),
                    ("authorization", {}),
                )
            )
        ):
            return False
        if event_name == "fetch_result" and (
            (
                current_generation is None
                and current.get("state") != "classifying"
            )
            or (
                current_generation is not None
                and current.get("state") != "verifying"
            )
        ):
            return False
    elif prior_generation is None or current_generation is None:
        # Once generation 1 exists, candidate authority can never roll back to
        # bootstrap or to a malformed tuple.
        return False
    else:
        before = prior_generation[0]
        after = current_generation[0]
        before_identity = {
            name: before[name] for name in before if name != "generation"
        }
        after_identity = {
            name: after[name] for name in after if name != "generation"
        }
        if before_identity == after_identity:
            if current.get("candidate") != prior.get("candidate"):
                return False
            invalidates_evidence = event_name == "generation_refreshed"
        else:
            if (
                after.get("generation") != int(before["generation"]) + 1
                or event_name
                not in {
                    "fetch_result",
                    "generation_refreshed",
                    "generation_carried_forward",
                    "rebase_result",
                }
            ):
                return False
            if event_name == "generation_carried_forward":
                identity_changes = {
                    name
                    for name in before_identity
                    if before_identity[name] != after_identity[name]
                }
                if identity_changes != {"remote_tip"}:
                    return False
            invalidates_evidence = event_name != "generation_carried_forward"
        if invalidates_evidence:
            retained_review = _merge_invalidated_review_projection(prior)
            if retained_review is None or any(
                current.get(name) != empty
                for name, empty in (
                    ("steps", {}),
                    ("review", retained_review),
                    ("approval", {}),
                    ("authorization", {}),
                )
            ):
                # Every non-remote-only successor generation invalidates all
                # candidate-bound evidence but preserves the completed review
                # count so refresh cannot reopen the eight-cycle cap.
                return False
    return _merge_event_evidence_valid(
        event, prior, current, context=context
    )


def _receipt_metadata(
    event: dict[str, object], family: str
) -> dict[str, object] | None:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return None
    if family == "commit":
        details = payload.get("details")
        if not isinstance(details, dict):
            return None
        carrier = details
    else:
        carrier = payload
    if set(carrier) != {"idempotency_key", "batch_digest", "receipt_digest"}:
        return None
    if any(
        not isinstance(carrier.get(name), str)
        or journal.HEX_SHA256_PATTERN.fullmatch(str(carrier[name])) is None
        for name in ("idempotency_key", "batch_digest", "receipt_digest")
    ):
        return None
    return carrier


def _verify_receipted_batch(
    repository: Path,
    chain_id: str,
    state: dict[str, object],
    pending: dict[str, object],
    carried_records: tuple[dict[str, object], ...],
    acknowledgement: dict[str, object],
) -> None:
    """Bind an acknowledgement to the one durable FR-019 receipt and suffix."""

    run_binding = state.get("run_binding")
    if not isinstance(run_binding, dict):
        raise _binding_replay_refusal()
    run_id = run_binding.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise _binding_replay_refusal()
    run_dir = (
        chain_storage_root(repository).parents[1]
        / ".codex-orchestrator"
        / "runs"
        / run_id
    )
    try:
        with batch.batch_lock(run_dir, create=False) as locked:
            receipts, _raw, _observation = batch._load_receipts(locked)
            matches = [
                receipt
                for receipt in receipts
                if receipt.get("idempotency_key")
                == pending.get("idempotency_key")
            ]
            if len(matches) != 1:
                raise _binding_replay_refusal()
            receipt = matches[0]
            batch.validate_pending_outbox_receipt(pending, receipt)
            _, request_digest = batch.normalized_request(
                repository,
                run_id,
                "chain outbox-drain",
                {
                    "chain_id": chain_id,
                    "source_event_digest": pending["source_event_digest"],
                    "batch_digest": pending["batch_digest"],
                    "record_count": pending["record_count"],
                },
            )
            journal_records = batch._verify_receipt_journal(locked, receipt)
            if (
                receipt.get("request_sha256") != request_digest
                or b"".join(
                    journal._journal_line(record) for record in journal_records
                )
                != b"".join(
                    journal._journal_line(record) for record in carried_records
                )
                or acknowledgement.get("receipt_digest")
                != journal._sha256(
                    journal._canonical_json_bytes(receipt) + b"\n"
                )
            ):
                raise _binding_replay_refusal()
    except journal.CoordinationRefusal as exc:
        if str(exc) == str(_binding_replay_refusal()):
            raise
        raise _binding_replay_refusal() from exc
    except OSError as exc:
        raise _binding_replay_refusal() from exc


def _candidate_binding_for_state(
    family: str, state: dict[str, object]
) -> dict[str, object] | None:
    candidate = state.get("candidate")
    if not isinstance(candidate, dict):
        return None
    if family == "commit":
        digest = candidate.get("sha256")
        if (
            not isinstance(digest, str)
            or journal.HEX_SHA256_PATTERN.fullmatch(digest) is None
        ):
            return None
        return {"kind": "staged-diff-sha256", "value": digest}
    generation = _merge_generation(candidate)
    if generation is None:
        return None
    return {
        "kind": "git-range",
        "value": {
            "base": candidate["remote_tip"],
            "head": candidate["candidate_head"],
        },
    }


def _review_binding_for_state(state: dict[str, object]) -> dict[str, object] | None:
    review = state.get("review")
    if not isinstance(review, dict):
        return None
    verdict = review.get("verdict")
    request = review.get("request")
    if not isinstance(verdict, dict):
        return None
    reviewer_role = verdict.get("reviewer_role")
    if reviewer_role is None and isinstance(request, dict):
        reviewer_role = request.get("reviewer")
    candidate = {
        "verdict": verdict.get("verdict"),
        "iteration": review.get("iteration"),
        "reviewer_role": reviewer_role,
        "package_digest": verdict.get("package_digest"),
    }
    if (
        candidate["verdict"] not in journal.BINDING_REVIEW_VERDICTS
        or type(candidate["iteration"]) is not int
        or int(candidate["iteration"]) <= 0
        or candidate["reviewer_role"] not in journal.BINDING_REVIEW_ROLES
        or not isinstance(candidate["package_digest"], str)
        or journal.HEX_SHA256_PATTERN.fullmatch(str(candidate["package_digest"]))
        is None
    ):
        return None
    return candidate


def _merge_gate_delta(
    record: dict[str, object],
    prior: dict[str, object] | None,
    current: dict[str, object],
) -> tuple[str, object] | None:
    """Return the one exact merge gate fact introduced by this transition."""

    if prior is None:
        return None
    prior_steps = prior.get("steps")
    current_steps = current.get("steps")
    if not isinstance(prior_steps, dict) or not isinstance(current_steps, dict):
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
    fact: object
    if isinstance(new_value, list):
        old_runs = old_value if isinstance(old_value, list) else []
        if len(new_value) != len(old_runs) + 1 or new_value[:-1] != old_runs:
            return None
        fact = new_value[-1]
    else:
        fact = new_value
    if not isinstance(fact, dict) or fact.get("result") != record.get("result"):
        return None
    criterion = fact.get("criterion")
    if criterion is not None and criterion != record.get("criterion"):
        return None
    return str(step_id), copy.deepcopy(new_value)


def _binding_matches_source_fact(
    binding: dict[str, object],
    record: dict[str, object],
    event: dict[str, object],
    prior: dict[str, object] | None,
    current: dict[str, object],
    *,
    family: str,
) -> bool:
    candidate = _candidate_binding_for_state(family, current)
    if candidate is None or binding.get("candidate") != candidate:
        return False
    event_name = (
        event.get("payload", {}).get("event")
        if family == "commit" and isinstance(event.get("payload"), dict)
        else event.get("event")
    )
    criterion = record.get("criterion") if record.get("type") == "verification" else None
    outcome = record.get("outcome") if record.get("type") == "decision" else None
    old_candidate = (
        _candidate_binding_for_state(family, prior)
        if isinstance(prior, dict)
        else None
    )

    if isinstance(criterion, str) and criterion.startswith(("gate-1: ", "gate-2: ")):
        if binding.get("review") is not None:
            return False
        if family == "merge":
            if event_name != "gate_recorded":
                return False
            return _merge_gate_delta(record, prior, current) is not None
        if event_name == "secret_scan_recorded":
            introduced = _commit_secret_scan_delta(event, prior, current)
            return bool(
                criterion == "gate-2: secret-scan"
                and introduced is not None
                and introduced[1].get("result") == record.get("result")
            )
        if event_name != "step_recorded":
            return False
        payload = event.get("payload")
        details = payload.get("details") if isinstance(payload, dict) else None
        step_id = details.get("step_id") if isinstance(details, dict) else None
        return bool(
            prior is not None
            and prior.get("steps") != current.get("steps")
            and details is not None
            and details.get("result") == record.get("result")
            and (
                (criterion.startswith("gate-1: ") and step_id == "gate-1")
                or (
                    criterion.startswith("gate-2: ")
                    and isinstance(step_id, str)
                    and step_id != "gate-1"
                )
            )
        )

    if criterion == journal.GATE_3_CRITERION:
        allowed = (
            {"review_passed", "review_blocked"}
            if family == "commit"
            else {"review_attached", "generation_carried_forward"}
        )
        review = _review_binding_for_state(current)
        old_review = (
            _review_binding_for_state(prior) if isinstance(prior, dict) else None
        )
        return bool(
            event_name in allowed
            and review is not None
            and binding.get("review") == review
            and (old_review != review or old_candidate != candidate)
        )

    if record.get("type") == "verification":
        allowed = {"step_recorded"} if family == "commit" else {"gate_recorded"}
        return bool(
            event_name in allowed
            and binding.get("review") is None
            and prior is not None
            and prior.get("steps") != current.get("steps")
        )

    if outcome == "chain-approval":
        allowed = (
            {"operator_approved"}
            if family == "commit"
            else {"approval_recorded", "generation_carried_forward"}
        )
        old_approval = prior.get("approval") if isinstance(prior, dict) else None
        approval = current.get("approval")
        expected_approved = (
            candidate["value"]
            if family == "commit"
            else candidate["value"]["head"]
        )
        return bool(
            event_name in allowed
            and binding.get("review") is None
            and isinstance(approval, dict)
            and approval.get("candidate") == expected_approved
            and (
                old_approval != current.get("approval")
                or old_candidate != candidate
            )
        )
    if outcome == "chain-skip":
        if family != "commit" or event_name != "operator_skip":
            return False
        return bool(
            binding.get("review") is None
            and _commit_skip_delta(event, prior, current) is not None
        )
    if outcome == "chain-landing":
        if binding.get("review") is not None or prior is None:
            return False
        if family == "commit":
            result = current.get("commit_result")
            old_result = prior.get("commit_result")
            commit_sha = result.get("commit_sha") if isinstance(result, dict) else None
            intent = result.get("intent") if isinstance(result, dict) else None
            old_commit = (
                old_result.get("commit_sha") if isinstance(old_result, dict) else None
            )
            return bool(
                event_name in {"commit_produced", "commit_close_recovered"}
                and old_commit is None
                and isinstance(intent, dict)
                and intent.get("candidate") == candidate.get("value")
                and isinstance(commit_sha, str)
                and journal.GIT_OBJECT_ID_PATTERN.fullmatch(commit_sha) is not None
            )
        integration = current.get("integration")
        push = integration.get("push") if isinstance(integration, dict) else None
        landed = push.get("landed_head") if isinstance(push, dict) else None
        generation = current.get("candidate")
        observed = (
            integration.get("observed") if isinstance(integration, dict) else None
        )
        return bool(
            event_name == "push_observed"
            and prior.get("state") != "pushed"
            and current.get("state") == "pushed"
            and isinstance(generation, dict)
            and isinstance(push, dict)
            and push.get("intended_head") == generation.get("candidate_head")
            and landed == generation.get("candidate_head")
            and isinstance(observed, dict)
            and observed.get("contains_intended_head") is True
        )
    return False


def _merge_ownership_summary(
    chain_id: str,
    state: dict[str, object],
    events: Sequence[dict[str, object]],
    raw_event_bytes: bytes,
) -> dict[str, object]:
    """Extract authenticated ownership edges from an already replayed chain."""

    claimed = next(
        (event for event in events if event.get("event") == "ownership_claimed"),
        None,
    )
    intent: dict[str, object] | None = None
    if isinstance(claimed, dict):
        claimed_payload = claimed.get("payload")
        intended_digest = (
            claimed_payload.get("ownership_intent_digest")
            if isinstance(claimed_payload, dict)
            else None
        )
        intent = next(
            (
                event
                for event in events
                if event.get("event") == "ownership_intent"
                and event.get("digest") == intended_digest
            ),
            None,
        )
    else:
        for event in events:
            if event.get("event") == "ownership_intent":
                intent = event
    if intent is None:
        raise _binding_replay_refusal()
    intent_payload = intent.get("payload")
    if not isinstance(intent_payload, dict):
        raise _binding_replay_refusal()

    released = None
    for event in events:
        payload = event.get("payload")
        if (
            event.get("event") == "ownership_released"
            and isinstance(payload, dict)
            and payload.get("release_mode") == "acquired"
        ):
            released = event
    worktree = _merge_worktree_claim(state)
    if worktree is None:
        raise _binding_replay_refusal()
    identity, claim = worktree
    return {
        "family": "merge",
        "chain_id": chain_id,
        "identity": {
            name: identity[name] for name in ("path", "git_dir", "common_dir")
        },
        "claim_status": claim.get("status"),
        "predecessor_chain_id": intent_payload.get("predecessor_chain_id"),
        "predecessor_release_digest": intent_payload.get(
            "predecessor_release_digest"
        ),
        "acquired": claimed is not None,
        "released_digest": (
            released.get("digest") if isinstance(released, dict) else None
        ),
        "terminal": state.get("state") in {"closed", "aborted"},
        "snapshot_event_digest": journal._sha256(raw_event_bytes),
        "snapshot_state": copy.deepcopy(state),
    }


def _validate_merge_slot_lineage(
    repository: Path,
    chains_descriptor: int,
    chain_id: str,
    state: dict[str, object],
) -> None:
    """Validate the bounded causal ownership graph for one worktree slot."""

    current_worktree = _merge_worktree_claim(state)
    if current_worktree is None:
        raise _binding_replay_refusal()
    current_identity = {
        name: current_worktree[0][name]
        for name in ("path", "git_dir", "common_dir")
    }
    try:
        names = os.listdir(chains_descriptor)
    except OSError as exc:
        raise _binding_replay_refusal() from exc
    chain_ids = sorted(
        {
            candidate_id
            for name in names
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
        raise _binding_replay_refusal()
    cap = len(chain_ids)
    summaries: dict[str, dict[str, object]] = {}
    snapshots: dict[str, dict[str, object]] = {}
    for candidate_id in chain_ids:
        try:
            summary = _resolve_binding_from_descriptor(
                repository,
                chains_descriptor,
                candidate_id,
                "0" * 64,
                expected_type=None,
                expected_fields=None,
                expected_run_id=None,
                expected_task_id=None,
                replay_only=True,
                allow_pending=True,
                validate_lineage=False,
                ownership_summary=True,
            )
        except journal.CoordinationRefusal:
            raise _binding_replay_refusal()
        snapshots[candidate_id] = summary
        if summary.get("family") == "commit":
            continue
        if summary.get("identity") == current_identity:
            summaries[candidate_id] = summary
    current = summaries.get(chain_id)
    if current is None:
        raise _binding_replay_refusal()
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
                raise _binding_replay_refusal()
            continue
        predecessor_summary = acquired.get(str(predecessor_chain))
        if not current_is_durable_predecessor and (
            predecessor_summary is None
            or predecessor_summary.get("released_digest") != predecessor_digest
            or predecessor_summary.get("terminal") is not True
            or predecessor_summary.get("claim_status") != "released"
            or predecessor_summary.get("identity") != current_identity
        ):
            raise _binding_replay_refusal()

    # Follow the selected chain's immutable predecessor edges with a bound no-
    # cycle/no-missing traversal.  Never-published releases do not become graph
    # nodes and therefore cannot create a permanent fork.
    cursor: dict[str, object] | None = current
    visited: set[str] = set()
    for _ in range(cap + 1):
        if cursor is None:
            break
        predecessor_chain = cursor.get("predecessor_chain_id")
        predecessor_digest = cursor.get("predecessor_release_digest")
        if predecessor_chain is None:
            if predecessor_digest is not None:
                raise _binding_replay_refusal()
            cursor = None
            break
        if not isinstance(predecessor_chain, str) or predecessor_chain in visited:
            raise _binding_replay_refusal()
        visited.add(predecessor_chain)
        predecessor = acquired.get(predecessor_chain)
        if (
            predecessor is None
            or predecessor.get("released_digest") != predecessor_digest
            or predecessor.get("terminal") is not True
        ):
            raise _binding_replay_refusal()
        cursor = predecessor
    if cursor is not None:
        raise _binding_replay_refusal()

    if not current_is_durable_predecessor:
        # The active/unpublished claimant must be the unique causal successor
        # of the then-current tail.  Later forks cannot retroactively corrupt a
        # released predecessor, but they freeze the claimant being admitted.
        if any(len(values) > 1 for values in children.values()):
            raise _binding_replay_refusal()
        others = {name: value for name, value in acquired.items() if name != chain_id}
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
            raise _binding_replay_refusal()
    else:
        # A released predecessor is not invalidated by a later active claimant,
        # but two terminal acquired children of the same immutable release edge
        # are an irresolvable fork.  Neither sibling can be selected as the
        # authoritative continuation without silently trusting wall-clock order.
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
            raise _binding_replay_refusal()

    # Retain the authenticated bytes as the graph authority and prove no chain
    # file was substituted while the bounded multi-chain snapshot was built.
    for candidate_id, snapshot in snapshots.items():
        if (
            journal._sha256(
                _read_regular_bytes_at(
                    chains_descriptor, f"{candidate_id}.events.jsonl"
                )
            )
            != snapshot.get("snapshot_event_digest")
            or _read_json_at(chains_descriptor, f"{candidate_id}.json")
            != snapshot.get("snapshot_state")
        ):
            raise _binding_replay_refusal()


def resolve_binding(
    repository: Path,
    chain_id: str,
    binding_id: str,
    *,
    expected_type: str | None = None,
    expected_fields: dict[str, object] | None = None,
    expected_run_id: str | None = None,
    expected_task_id: str | None = None,
    _chains_descriptor: int | None = None,
    _chains_observation: journal.FileObservation | None = None,
) -> dict[str, object]:
    """Replay one immutable event stream and return its exact named binding."""

    if "binding-replay" not in BUILDER_VALIDATION_CONTROLS:
        raise journal.CoordinationRefusal(
            f"{journal.INVALID_JOURNAL_RECORD}: binding replay control unavailable"
        )
    if journal.HEX_SHA256_PATTERN.fullmatch(binding_id) is None:
        raise journal.CoordinationRefusal(
            f"{journal.INVALID_JOURNAL_RECORD}: binding id is invalid"
        )
    chains_root = chain_storage_root(repository)
    _chain_paths(repository, chain_id)
    owned_descriptor: int | None = None
    try:
        if _chains_descriptor is None:
            owned_descriptor, root_observation = journal._open_bound_directory(
                chains_root
            )
            chains_descriptor = owned_descriptor
        else:
            chains_descriptor = _chains_descriptor
            root_observation = _chains_observation
            if root_observation is None:
                raise _binding_replay_refusal()
        if (
            journal._file_observation(os.fstat(chains_descriptor))
            != root_observation
            or journal._file_observation(os.lstat(chains_root))
            != root_observation
        ):
            raise _binding_replay_refusal()
        result = _resolve_binding_from_descriptor(
            repository,
            chains_descriptor,
            chain_id,
            binding_id,
            expected_type=expected_type,
            expected_fields=expected_fields,
            expected_run_id=expected_run_id,
            expected_task_id=expected_task_id,
        )
        if (
            journal._file_observation(os.fstat(chains_descriptor))
            != root_observation
            or journal._file_observation(os.lstat(chains_root))
            != root_observation
        ):
            raise _binding_replay_refusal()
        return result
    except journal.CoordinationRefusal:
        raise
    except OSError as exc:
        raise _binding_replay_refusal() from exc
    finally:
        if owned_descriptor is not None:
            os.close(owned_descriptor)


def _resolve_binding_from_descriptor(
    repository: Path,
    chains_descriptor: int,
    chain_id: str,
    binding_id: str,
    *,
    expected_type: str | None,
    expected_fields: dict[str, object] | None,
    expected_run_id: str | None,
    expected_task_id: str | None,
    replay_only: bool = False,
    allow_pending: bool = False,
    validate_lineage: bool = True,
    ownership_summary: bool = False,
) -> dict[str, object]:
    # Event authority is read and reduced before the materialized projection.
    # A state file must never select or repair the history that authenticates it.
    raw_event_bytes = _read_regular_bytes_at(
        chains_descriptor, f"{chain_id}.events.jsonl"
    )
    if not raw_event_bytes or not raw_event_bytes.endswith(b"\n"):
        raise _binding_replay_refusal()
    raw_lines = raw_event_bytes.splitlines(keepends=True)
    previous = "0" * 64
    events: list[dict[str, object]] = []
    replay_entries: list[
        tuple[
            dict[str, object],
            dict[str, object] | None,
            dict[str, object],
            tuple[dict[str, object], ...],
            str | None,
        ]
    ] = []
    chain_family: str | None = None
    replayed_state: dict[str, object] | None = None
    pending_outbox: dict[str, object] | None = None
    pending_records: tuple[dict[str, object], ...] = ()
    merge_context: dict[str, object] = {}
    for sequence, raw in enumerate(raw_lines, start=1):
        try:
            event = json.loads(raw.decode("utf-8"))
        except (UnicodeError, ValueError, RecursionError) as exc:
            raise _binding_replay_refusal() from exc
        commit_event = bool(
            isinstance(event, dict)
            and set(event)
            == {"digest", "payload", "prev_digest", "sequence"}
            and event.get("prev_digest") == previous
        )
        merge_event = bool(
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
            and event.get("previous_digest") == previous
        )
        family = "commit" if commit_event else "merge" if merge_event else None
        if (
            family is None
            or (chain_family is not None and family != chain_family)
            or event.get("sequence") != sequence
            or not isinstance(event.get("digest"), str)
            or journal.HEX_SHA256_PATTERN.fullmatch(str(event["digest"])) is None
        ):
            raise _binding_replay_refusal()
        chain_family = family
        if raw != journal._canonical_json_bytes(event) + b"\n":
            raise _binding_replay_refusal()
        projection = {name: event[name] for name in event if name != "digest"}
        if journal._sha256(journal._canonical_json_bytes(projection)) != event["digest"]:
            raise _binding_replay_refusal()

        payload = event.get("payload")
        if not isinstance(payload, dict):
            raise _binding_replay_refusal()
        if family == "commit":
            if set(payload) != {"at", "details", "event", "state"}:
                raise _binding_replay_refusal()
            event_name = payload.get("event")
            if event_name not in _COMMIT_EVENT_NAMES:
                raise _binding_replay_refusal()
        else:
            event_name = event.get("event")
            if (
                event_name not in _MERGE_EVENT_NAMES
                or _utc_value(event.get("at")) is None
            ):
                raise _binding_replay_refusal()

        records, event_outbox, source_digest = _event_batch_records(event, family)
        is_receipt = event_name == "journal_receipted"
        if pending_outbox is not None and not is_receipt:
            raise _binding_replay_refusal()
        if pending_outbox is None and is_receipt:
            raise _binding_replay_refusal()
        receipt = _receipt_metadata(event, family) if is_receipt else None
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
            ):
                raise _binding_replay_refusal()
            if replayed_state is None:
                raise _binding_replay_refusal()
            _verify_receipted_batch(
                repository,
                chain_id,
                replayed_state,
                pending_outbox,
                pending_records,
                receipt,
            )
        elif event_outbox is not None and pending_outbox is not None:
            raise _binding_replay_refusal()

        prior_state = copy.deepcopy(replayed_state)
        if family == "commit":
            candidate_state = payload.get("state")
            if (
                not _state_shape_valid(candidate_state, chain_id, family)
                or not isinstance(candidate_state, dict)
                or not _commit_transition_valid(event, replayed_state, candidate_state)
            ):
                raise _binding_replay_refusal()
            next_state = copy.deepcopy(candidate_state)
        else:
            reducer = MERGE_TRANSITION_REDUCER
            if reducer is None:
                raise _binding_replay_refusal()
            try:
                next_state = reducer(
                    copy.deepcopy(replayed_state), copy.deepcopy(event)
                )
            except (KeyError, TypeError, ValueError, RuntimeError) as exc:
                raise _binding_replay_refusal() from exc
            if (
                not _state_shape_valid(next_state, chain_id, family)
                or not _merge_transition_valid(
                    event,
                    replayed_state,
                    next_state,
                    context=merge_context,
                )
            ):
                raise _binding_replay_refusal()

        if is_receipt:
            if next_state.get("journal_outbox") is not None:
                raise _binding_replay_refusal()
            if prior_state is None:
                raise _binding_replay_refusal()
            ignored = {"last_event_at", "inactive_after", "journal_outbox"}
            if any(
                prior_state.get(name) != next_state.get(name)
                for name in (_COMMIT_STATE_KEYS if family == "commit" else _MERGE_STATE_KEYS)
                - ignored
            ):
                raise _binding_replay_refusal()
            pending_outbox = None
            pending_records = ()
        elif event_outbox is not None:
            if next_state.get("journal_outbox") != event_outbox:
                raise _binding_replay_refusal()
            pending_outbox = event_outbox
            pending_records = records
        elif next_state.get("journal_outbox") != pending_outbox:
            raise _binding_replay_refusal()

        for carried_record in records:
            carried_binding = carried_record.get("binding")
            if (
                not isinstance(carried_binding, dict)
                or not _binding_matches_source_fact(
                    carried_binding,
                    carried_record,
                    event,
                    prior_state,
                    next_state,
                    family=family,
                )
            ):
                raise _binding_replay_refusal()

        replayed_state = next_state
        replay_entries.append(
            (event, prior_state, copy.deepcopy(next_state), records, source_digest)
        )
        previous = str(event["digest"])
        events.append(event)
    if not events or replayed_state is None:
        raise _binding_replay_refusal()

    state = _read_json_at(chains_descriptor, f"{chain_id}.json")
    if (
        not isinstance(state, dict)
        or not _state_shape_valid(state, chain_id, str(chain_family))
        or state != replayed_state
    ):
        raise _binding_replay_refusal()
    if ownership_summary:
        if chain_family == "commit":
            return {
                "family": "commit",
                "snapshot_event_digest": journal._sha256(raw_event_bytes),
                "snapshot_state": copy.deepcopy(state),
            }
        return _merge_ownership_summary(
            chain_id, state, events, raw_event_bytes
        )
    if chain_family == "merge" and validate_lineage:
        _validate_merge_slot_lineage(
            repository, chains_descriptor, chain_id, state
        )
    if pending_outbox is not None and not allow_pending:
        raise journal.CoordinationRefusal(JOURNAL_OUTBOX_PENDING)
    if replay_only:
        return state
    if expected_run_id is not None or expected_task_id is not None:
        run_binding = state.get("run_binding")
        if (
            not isinstance(run_binding, dict)
            or set(run_binding)
            != {"run_id", "task_id", "repository", "policy_digest"}
            or run_binding.get("run_id") != expected_run_id
            or run_binding.get("task_id") != expected_task_id
            or run_binding.get("repository") != str(repository)
            or not isinstance(run_binding.get("policy_digest"), str)
            or journal.HEX_SHA256_PATTERN.fullmatch(
                str(run_binding["policy_digest"])
            )
            is None
        ):
            raise _binding_replay_refusal()
    matches: list[
        tuple[
            dict[str, object],
            dict[str, object],
            dict[str, object],
            dict[str, object] | None,
            dict[str, object],
        ]
    ] = []
    for event, prior, event_state, event_records, source_digest in replay_entries:
        for record in event_records:
            if expected_type is not None and record.get("type") != expected_type:
                continue
            if expected_fields is not None and any(
                record.get(name) != value for name, value in expected_fields.items()
            ):
                continue
            candidate = record.get("binding")
            if (
                not isinstance(candidate, dict)
                or candidate.get("binding_id") != binding_id
                or not journal._binding_shape_valid(candidate, record=record)
                or source_digest is None
            ):
                continue
            source = candidate.get("source_record")
            if (
                not isinstance(source, dict)
                or source.get("chain_id") != chain_id
                or source.get("event_digest") != source_digest
                or not _binding_matches_source_fact(
                    candidate,
                    record,
                    event,
                    prior,
                    event_state,
                    family=str(chain_family),
                )
            ):
                continue
            matches.append((candidate, record, event, prior, event_state))
    if len(matches) != 1:
        raise _binding_replay_refusal()
    resolved, source_record, source_event, source_prior, source_state = matches[0]
    if not _binding_is_current(
        state,
        resolved,
        source_record,
        source_event,
        source_prior,
        source_state,
        replay_entries,
        chain_family=str(chain_family),
    ):
        raise _binding_replay_refusal()
    return dict(resolved)


def _commit_gate_fact_is_current(
    state: dict[str, object],
    binding: dict[str, object],
    record: dict[str, object],
    source_event: dict[str, object],
    source_state: dict[str, object],
    replay_entries: Sequence[
        tuple[
            dict[str, object],
            dict[str, object] | None,
            dict[str, object],
            tuple[dict[str, object], ...],
            str | None,
        ]
    ],
) -> bool:
    """Prove the exact source step is still a counted current-candidate fact."""

    payload = source_event.get("payload")
    details = payload.get("details") if isinstance(payload, dict) else None
    criterion = record.get("criterion")
    if not isinstance(details, dict) or not isinstance(criterion, str):
        return False
    if payload.get("event") == "secret_scan_recorded":
        if criterion != "gate-2: secret-scan" or binding.get("review") is not None:
            return False
        source_prior = next(
            (
                prior
                for event, prior, _event_state, _records, _digest in replay_entries
                if event.get("digest") == source_event.get("digest")
            ),
            None,
        )
        introduced = _commit_secret_scan_delta(
            source_event, source_prior, source_state
        )
        current_steps = state.get("steps")
        current_runs = (
            current_steps.get("secret-scan")
            if isinstance(current_steps, dict)
            else None
        )
        candidate = binding.get("candidate")
        candidate_value = (
            candidate.get("value") if isinstance(candidate, dict) else None
        )
        if (
            introduced is None
            or not isinstance(current_runs, list)
            or introduced[0] >= len(current_runs)
            or current_runs[introduced[0]] != introduced[1]
            or introduced[1].get("candidate") != candidate_value
            or introduced[1].get("result") != record.get("result")
        ):
            return False
        current_candidate_indexes = [
            index
            for index, fact in enumerate(current_runs)
            if isinstance(fact, dict) and fact.get("candidate") == candidate_value
        ]
        if not current_candidate_indexes or introduced[0] != current_candidate_indexes[-1]:
            return False
        latest_introduction: dict[str, object] | None = None
        for event, prior, event_state, _records, _source_digest in replay_entries:
            candidate_delta = _commit_secret_scan_delta(event, prior, event_state)
            if (
                candidate_delta is not None
                and candidate_delta[0] == introduced[0]
                and candidate_delta[1] == introduced[1]
            ):
                latest_introduction = event
        return bool(
            latest_introduction is not None
            and latest_introduction.get("digest") == source_event.get("digest")
        )
    step_id = details.get("step_id")
    run_number = details.get("run")
    if (
        not isinstance(step_id, str)
        or type(run_number) is not int
        or int(run_number) <= 0
        or (
            criterion.startswith("gate-1: ")
            and step_id != "gate-1"
        )
        or (
            criterion.startswith("gate-2: ")
            and step_id == "gate-1"
        )
    ):
        return False
    source_steps = source_state.get("steps")
    current_steps = state.get("steps")
    source_runs = (
        source_steps.get(step_id) if isinstance(source_steps, dict) else None
    )
    current_runs = (
        current_steps.get(step_id) if isinstance(current_steps, dict) else None
    )
    source_index = int(run_number) - 1
    if (
        not isinstance(source_runs, list)
        or not isinstance(current_runs, list)
        or source_index >= len(source_runs)
        or source_index >= len(current_runs)
        or source_runs[source_index] != current_runs[source_index]
        or source_index != len(source_runs) - 1
        or not isinstance(source_runs[source_index], dict)
        or source_runs[source_index].get("result") != record.get("result")
        or source_runs[source_index].get("result") != details.get("result")
    ):
        return False
    candidate = binding.get("candidate")
    candidate_value = (
        candidate.get("value") if isinstance(candidate, dict) else None
    )
    current_candidate_runs = [
        (index, value)
        for index, value in enumerate(current_runs)
        if isinstance(value, dict)
        and value.get("candidate") == candidate_value
    ]
    if not current_candidate_runs:
        return False

    active_indexes: set[int]
    if step_id == "gate-1":
        latest_index, latest = current_candidate_runs[-1]
        if latest.get("result") != "passed":
            active_indexes = {latest_index}
        elif len(current_candidate_runs) >= 2:
            previous_index, previous = current_candidate_runs[-2]
            if (
                previous.get("result") == "passed"
                and not previous.get("pair_voided")
                and not latest.get("pair_voided")
                and previous.get("env_fingerprint")
                == latest.get("env_fingerprint")
            ):
                active_indexes = {previous_index, latest_index}
            elif not latest.get("pair_voided"):
                active_indexes = {latest_index}
            else:
                active_indexes = set()
        elif not latest.get("pair_voided"):
            active_indexes = {latest_index}
        else:
            active_indexes = set()
    elif step_id.startswith("stack:"):
        _latest_index, latest = current_candidate_runs[-1]
        batch_id = latest.get("batch_id")
        cell_count = latest.get("cell_count")
        if not (
            isinstance(batch_id, str)
            and type(cell_count) is int
            and cell_count > 0
        ):
            return False
        current_batch = [
            (index, value)
            for index, value in current_candidate_runs
            if value.get("batch_id") == batch_id
        ]
        if record.get("result") == "passed":
            if not (
                len(current_batch) == cell_count
                and {
                    value.get("cell_index") for _index, value in current_batch
                }
                == set(range(1, cell_count + 1))
                and all(
                    value.get("result") == "passed"
                    for _index, value in current_batch
                )
            ):
                return False
            active_indexes = {index for index, _value in current_batch}
        else:
            active_indexes = {current_candidate_runs[-1][0]}
    else:
        active_indexes = {current_candidate_runs[-1][0]}
    if source_index not in active_indexes:
        return False

    latest_introduction: dict[str, object] | None = None
    for event, _prior, event_state, _records, _source_digest in replay_entries:
        event_payload = event.get("payload")
        event_details = (
            event_payload.get("details")
            if isinstance(event_payload, dict)
            else None
        )
        event_steps = event_state.get("steps")
        event_runs = (
            event_steps.get(step_id) if isinstance(event_steps, dict) else None
        )
        if (
            isinstance(event_details, dict)
            and event_payload.get("event") == "step_recorded"
            and event_details.get("step_id") == step_id
            and event_details.get("run") == run_number
            and isinstance(event_runs, list)
            and source_index < len(event_runs)
            and event_runs[source_index] == current_runs[source_index]
        ):
            latest_introduction = event
    return bool(
        latest_introduction is not None
        and latest_introduction.get("digest") == source_event.get("digest")
    )


def _merge_gate_fact_is_current(
    state: dict[str, object],
    record: dict[str, object],
    source_event: dict[str, object],
    source_prior: dict[str, object] | None,
    source_state: dict[str, object],
    replay_entries: Sequence[
        tuple[
            dict[str, object],
            dict[str, object] | None,
            dict[str, object],
            tuple[dict[str, object], ...],
            str | None,
        ]
    ],
) -> bool:
    """Prove the source event introduced the final reduced merge gate fact."""

    source_delta = _merge_gate_delta(record, source_prior, source_state)
    if source_delta is None:
        return False
    step_id, source_value = source_delta
    current_steps = state.get("steps")
    if (
        not isinstance(current_steps, dict)
        or current_steps.get(step_id) != source_value
    ):
        return False
    latest_change: tuple[dict[str, object], object] | None = None
    for event, prior, event_state, _records, _source_digest in replay_entries:
        prior_steps = prior.get("steps") if isinstance(prior, dict) else None
        event_steps = event_state.get("steps")
        prior_value = (
            prior_steps.get(step_id) if isinstance(prior_steps, dict) else None
        )
        event_value = (
            event_steps.get(step_id) if isinstance(event_steps, dict) else None
        )
        if prior_value != event_value:
            latest_change = (event, event_value)
    return bool(
        latest_change is not None
        and latest_change[1] == source_value
        and latest_change[0].get("digest") == source_event.get("digest")
    )


def _review_fact_is_current(
    state: dict[str, object],
    binding: dict[str, object],
    source_event: dict[str, object],
    replay_entries: Sequence[
        tuple[
            dict[str, object],
            dict[str, object] | None,
            dict[str, object],
            tuple[dict[str, object], ...],
            str | None,
        ]
    ],
    *,
    chain_family: str,
) -> bool:
    review = binding.get("review")
    if review != _review_binding_for_state(state):
        return False
    latest_introduction: dict[str, object] | None = None
    for event, prior, event_state, _records, _source_digest in replay_entries:
        event_review = _review_binding_for_state(event_state)
        prior_review = (
            _review_binding_for_state(prior) if isinstance(prior, dict) else None
        )
        event_candidate = _candidate_binding_for_state(chain_family, event_state)
        prior_candidate = (
            _candidate_binding_for_state(chain_family, prior)
            if isinstance(prior, dict)
            else None
        )
        if (
            event_review == review
            and (prior_review != event_review or prior_candidate != event_candidate)
        ):
            latest_introduction = event
    return bool(
        latest_introduction is not None
        and latest_introduction.get("digest") == source_event.get("digest")
    )


def _approval_fact_is_current(
    state: dict[str, object],
    source_event: dict[str, object],
    source_state: dict[str, object],
    replay_entries: Sequence[
        tuple[
            dict[str, object],
            dict[str, object] | None,
            dict[str, object],
            tuple[dict[str, object], ...],
            str | None,
        ]
    ],
    *,
    chain_family: str,
) -> bool:
    """Prove the source event is the current approval's latest authority."""

    approval = state.get("approval")
    if not isinstance(approval, dict) or source_state.get("approval") != approval:
        return False
    allowed = (
        {"operator_approved"}
        if chain_family == "commit"
        else {"approval_recorded", "generation_carried_forward"}
    )
    latest_introduction: dict[str, object] | None = None
    for event, prior, event_state, _records, _source_digest in replay_entries:
        event_name = (
            event.get("payload", {}).get("event")
            if chain_family == "commit" and isinstance(event.get("payload"), dict)
            else event.get("event")
        )
        event_approval = event_state.get("approval")
        prior_approval = prior.get("approval") if isinstance(prior, dict) else None
        event_candidate = _candidate_binding_for_state(chain_family, event_state)
        prior_candidate = (
            _candidate_binding_for_state(chain_family, prior)
            if isinstance(prior, dict)
            else None
        )
        authority_changed = (
            prior_approval != event_approval
            or prior_candidate != event_candidate
        )
        if authority_changed:
            # No snapshot equality may carry authority across a candidate or
            # approval transition.  Only the event that genuinely establishes
            # the final fact can become its source.
            latest_introduction = None
        if (
            event_name in allowed
            and event_approval == approval
            and authority_changed
        ):
            latest_introduction = event
    return bool(
        latest_introduction is not None
        and latest_introduction.get("digest") == source_event.get("digest")
    )


def _skip_fact_is_current(
    state: dict[str, object],
    source_event: dict[str, object],
    source_prior: dict[str, object] | None,
    source_state: dict[str, object],
    replay_entries: Sequence[
        tuple[
            dict[str, object],
            dict[str, object] | None,
            dict[str, object],
            tuple[dict[str, object], ...],
            str | None,
        ]
    ],
) -> bool:
    """Prove the named source event introduced the current exact skip fact."""

    source_delta = _commit_skip_delta(source_event, source_prior, source_state)
    if source_delta is None:
        return False
    gate_id, source_fact = source_delta
    steps = state.get("steps")
    skips = steps.get("user_skips") if isinstance(steps, dict) else None
    if not isinstance(skips, dict) or skips.get(gate_id) != source_fact:
        return False
    latest_introduction: dict[str, object] | None = None
    for event, prior, event_state, _records, _source_digest in replay_entries:
        prior_candidate = (
            _candidate_binding_for_state("commit", prior)
            if isinstance(prior, dict)
            else None
        )
        event_candidate = _candidate_binding_for_state("commit", event_state)
        prior_steps = prior.get("steps") if isinstance(prior, dict) else None
        event_steps = event_state.get("steps")
        prior_skips = (
            prior_steps.get("user_skips")
            if isinstance(prior_steps, dict)
            else None
        )
        event_skips = (
            event_steps.get("user_skips")
            if isinstance(event_steps, dict)
            else None
        )
        prior_fact = (
            prior_skips.get(gate_id) if isinstance(prior_skips, dict) else None
        )
        event_fact = (
            event_skips.get(gate_id) if isinstance(event_skips, dict) else None
        )
        if prior_candidate != event_candidate or prior_fact != event_fact:
            latest_introduction = None
        delta = _commit_skip_delta(event, prior, event_state)
        if delta == (gate_id, source_fact):
            latest_introduction = event
    return bool(
        latest_introduction is not None
        and latest_introduction.get("digest") == source_event.get("digest")
    )


def _binding_is_current(
    state: dict[str, object],
    binding: dict[str, object],
    record: dict[str, object],
    source_event: dict[str, object],
    source_prior: dict[str, object] | None,
    source_state: dict[str, object],
    replay_entries: Sequence[
        tuple[
            dict[str, object],
            dict[str, object] | None,
            dict[str, object],
            tuple[dict[str, object], ...],
            str | None,
        ]
    ],
    *,
    chain_family: str,
) -> bool:
    """Prove the generation-free journal binding against current chain state."""

    candidate = binding.get("candidate")
    current_candidate = _candidate_binding_for_state(chain_family, state)
    if not isinstance(candidate, dict) or candidate != current_candidate:
        return False
    value = candidate.get("value")
    current = state.get("candidate")
    if chain_family == "merge":
        if not isinstance(current, dict):
            return False
        generation = source_event.get("generation_digest")
        if generation != current.get("generation_digest"):
            return False

    record_type = record.get("type")
    criterion = record.get("criterion")
    if record_type == "verification" and isinstance(criterion, str):
        if criterion.startswith(("gate-1: ", "gate-2: ")):
            if chain_family == "commit":
                if not _commit_gate_fact_is_current(
                    state,
                    binding,
                    record,
                    source_event,
                    source_state,
                    replay_entries,
                ):
                    return False
            elif not _merge_gate_fact_is_current(
                state,
                record,
                source_event,
                source_prior,
                source_state,
                replay_entries,
            ):
                return False
        elif criterion == journal.GATE_3_CRITERION:
            if not _review_fact_is_current(
                state,
                binding,
                source_event,
                replay_entries,
                chain_family=chain_family,
            ):
                return False

    outcome = record.get("outcome")
    if record_type == "decision" and outcome == "chain-approval":
        approval = state.get("approval")
        if not isinstance(approval, dict):
            return False
        approved_candidate = (
            value
            if isinstance(value, str)
            else value.get("head") if isinstance(value, dict) else None
        )
        if (
            not isinstance(approved_candidate, str)
            or approval.get("candidate") != approved_candidate
        ):
            return False
        if not _approval_fact_is_current(
            state,
            source_event,
            source_state,
            replay_entries,
            chain_family=chain_family,
        ):
            return False
    if record_type == "decision" and outcome == "chain-skip":
        if (
            chain_family != "commit"
            or not _skip_fact_is_current(
                state,
                source_event,
                source_prior,
                source_state,
                replay_entries,
            )
        ):
            return False
    if record_type == "decision" and outcome == "chain-landing":
        if chain_family == "commit":
            result = state.get("commit_result")
            if state.get("state") != "closed" or not isinstance(result, dict):
                return False
            intent = result.get("intent")
            if (
                not isinstance(intent, dict)
                or not isinstance(current, dict)
                or intent.get("candidate") != current.get("sha256")
            ):
                return False
            if journal.GIT_OBJECT_ID_PATTERN.fullmatch(
                str(result.get("commit_sha", ""))
            ) is None:
                return False
        else:
            integration = state.get("integration")
            push = integration.get("push") if isinstance(integration, dict) else None
            if state.get("state") != "closed" or not isinstance(push, dict):
                return False
            if (
                not isinstance(current, dict)
                or push.get("landed_head") != current.get("candidate_head")
            ):
                return False
    return True


@contextmanager
def _chain_event_lock(
    chains_root: Path,
    chain_id: str,
    *,
    root_descriptor: int | None = None,
    root_observation: journal.FileObservation | None = None,
) -> Iterator[None]:
    owned_root_descriptor: int | None = None
    lock_descriptor: int | None = None
    name = f".{chain_id}.events.lock"
    try:
        if root_descriptor is None:
            owned_root_descriptor, root_observation = journal._open_bound_directory(
                chains_root
            )
            root_descriptor = owned_root_descriptor
        elif root_observation is None:
            raise journal.CoordinationRefusal(TERMINAL_CHAIN_INVALID)
        try:
            observed = os.stat(name, dir_fd=root_descriptor, follow_symlinks=False)
        except FileNotFoundError:
            lock_descriptor = os.open(
                name,
                os.O_RDWR
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                0o600,
                dir_fd=root_descriptor,
            )
            os.fsync(lock_descriptor)
            os.fsync(root_descriptor)
            observed = os.fstat(lock_descriptor)
        if not journal._batch_regular_stat_valid(observed):
            raise journal.CoordinationRefusal(TERMINAL_CHAIN_INVALID)
        if lock_descriptor is None:
            lock_descriptor = os.open(
                name,
                os.O_RDWR
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=root_descriptor,
            )
        observation = journal._file_observation(observed)
        if journal._file_observation(os.fstat(lock_descriptor)) != observation:
            raise journal.CoordinationRefusal(TERMINAL_CHAIN_INVALID)
        fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
        rebound = os.stat(name, dir_fd=root_descriptor, follow_symlinks=False)
        if (
            journal._file_observation(rebound) != observation
            or journal._file_observation(os.fstat(root_descriptor))
            != root_observation
            or journal._file_observation(os.lstat(chains_root))
            != root_observation
        ):
            raise journal.CoordinationRefusal(TERMINAL_CHAIN_INVALID)
        yield
        rebound = os.stat(name, dir_fd=root_descriptor, follow_symlinks=False)
        if journal._file_observation(rebound) != observation:
            raise journal.CoordinationRefusal(TERMINAL_CHAIN_INVALID)
    except journal.CoordinationRefusal:
        raise
    except OSError as exc:
        raise journal.CoordinationRefusal(TERMINAL_CHAIN_INVALID) from exc
    finally:
        if lock_descriptor is not None:
            try:
                fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
            except OSError:
                pass
            os.close(lock_descriptor)
        if owned_root_descriptor is not None:
            os.close(owned_root_descriptor)


@contextmanager
def _optional_chain_lock(
    chains_root: Path,
    chain_id: str,
    *,
    root_descriptor: int | None = None,
    root_observation: journal.FileObservation | None = None,
) -> Iterator[None]:
    if "lock" in TERMINAL_CHAIN_CONTROLS:
        with _chain_event_lock(
            chains_root,
            chain_id,
            root_descriptor=root_descriptor,
            root_observation=root_observation,
        ):
            yield
    else:
        yield


def _captured_ingest_chain_ids(
    repository: Path,
    run_id: str,
    records: Sequence[dict[str, object]],
) -> set[str]:
    """Return journal chains backed by one exact captured ingest package.

    Retrospective ingest deliberately leaves the source chain unbound.  Its
    terminal authority is instead the content-addressed three-file package
    cited by the one landing decision and its source-event binding.
    """

    try:
        run_dir = (
            chain_storage_root(repository).parents[1]
            / ".codex-orchestrator"
            / "runs"
            / run_id
        )
        surface = commitment_surface("decision.basis")
    except (KeyError, OSError, RuntimeError, ValueError):
        return set()
    result: set[str] = set()

    def read_selected(selected: object) -> bytes:
        candidate = getattr(selected, "candidate", None)
        if not isinstance(candidate, Path):
            raise OSError("captured path is unresolved")
        descriptor, observation = journal._open_bound_directory(candidate.parent)
        try:
            raw, _file_observation = journal._read_bound_regular(
                descriptor, candidate.name, require_nonempty=True
            )
            if (
                journal._file_observation(os.fstat(descriptor)) != observation
                or journal._file_observation(os.lstat(candidate.parent))
                != observation
            ):
                raise OSError("captured package parent changed")
            return raw
        finally:
            os.close(descriptor)

    landings = [
        record
        for record in records
        if record.get("type") == "decision"
        and record.get("outcome") == "chain-landing"
        and isinstance(record.get("binding"), dict)
    ]
    for landing in landings:
        binding = landing["binding"]
        assert isinstance(binding, dict)
        source = binding.get("source_record")
        basis = landing.get("basis")
        task = landing.get("task")
        if (
            not isinstance(source, dict)
            or not isinstance(source.get("chain_id"), str)
            or journal.CHAIN_ID_PATTERN.fullmatch(str(source["chain_id"])) is None
            or not isinstance(source.get("event_digest"), str)
            or journal.HEX_SHA256_PATTERN.fullmatch(str(source["event_digest"]))
            is None
            or not isinstance(task, str)
            or not isinstance(basis, list)
            or len(basis) != 3
            or not all(isinstance(value, str) for value in basis)
        ):
            continue
        chain_id = str(source["chain_id"])
        names = ("state.json", "events.jsonl", "outcome-map.json")
        captured: list[bytes] = []
        valid = True
        for value, name in zip(basis, names, strict=True):
            assert isinstance(value, str)
            captured_path = parse_run_captured_path(value, run_id=run_id)
            if captured_path is None or captured_path.name != name:
                valid = False
                break
            selected = validate_surface_path(
                surface,
                value,
                repository=repository,
                run_dir=run_dir,
                require_file=True,
            )
            if selected is None:
                valid = False
                break
            try:
                raw = read_selected(selected)
            except OSError:
                valid = False
                break
            if journal._sha256(raw) != captured_path.digest:
                valid = False
                break
            captured.append(raw)
        if not valid or len(captured) != 3:
            continue
        try:
            state = json.loads(captured[0].decode("utf-8"))
            event_lines = captured[1].splitlines(keepends=True)
            events = [json.loads(raw.decode("utf-8")) for raw in event_lines]
            outcome = json.loads(captured[2].decode("utf-8"))
        except (UnicodeError, ValueError, RecursionError):
            continue
        source_digest = str(source["event_digest"])
        latest_task = next(
            (
                record
                for record in reversed(records)
                if record.get("type") == "task" and record.get("id") == task
            ),
            None,
        )
        family = state.get("kind") if isinstance(state, dict) else None
        repository_matches = bool(
            isinstance(state, dict)
            and (
                (family == "merge" and state.get("repository") == str(repository))
                or (
                    family == "commit"
                    and isinstance(state.get("staging"), dict)
                    and state["staging"].get("worktree_root") == str(repository)
                )
            )
        )
        if (
            not isinstance(state, dict)
            or state.get("chain_id") != chain_id
            or state.get("run_binding") is not None
            or not repository_matches
            or family not in {"commit", "merge"}
            or state.get("state") != "closed"
            or binding.get("candidate")
            != _candidate_binding_for_state(str(family), state)
            or not events
            or len(event_lines) != len(events)
            or any(
                raw != journal._canonical_json_bytes(event) + b"\n"
                for raw, event in zip(event_lines, events, strict=True)
            )
            or sum(event.get("digest") == source_digest for event in events) != 1
            or not isinstance(outcome, dict)
            or set(outcome)
            != {"schema", "chain_id", "task", "task_status", "event_digests"}
            or outcome.get("schema") != "forge-chain-ingest-outcome-map/1"
            or outcome.get("chain_id") != chain_id
            or outcome.get("task") != task
            or not isinstance(outcome.get("event_digests"), list)
            or source_digest not in outcome["event_digests"]
            or latest_task is None
            or latest_task.get("status") != outcome.get("task_status")
            or latest_task.get("status") not in journal.TERMINAL_TASK_STATUSES
        ):
            continue
        result.add(chain_id)
    return result


def _terminal_chain_guard(
    repository: Path,
    run_id: str,
    records: Sequence[dict[str, object]],
    *,
    task_id: str | None,
) -> None:
    if "enumeration" not in TERMINAL_CHAIN_CONTROLS:
        return
    chains_root = chain_storage_root(repository)
    journal_chain_ids = {
        str(source["chain_id"])
        for record in records
        if isinstance(record.get("binding"), dict)
        for source in (record["binding"].get("source_record"),)
        if isinstance(source, dict)
        and isinstance(source.get("chain_id"), str)
        and journal.CHAIN_ID_PATTERN.fullmatch(str(source["chain_id"])) is not None
    }
    captured_ingest_chain_ids = _captured_ingest_chain_ids(
        repository, run_id, records
    )
    bound_journal_chain_ids = journal_chain_ids - captured_ingest_chain_ids
    chains_descriptor: int | None = None
    try:
        chains_descriptor, observed_root = journal._open_bound_directory(chains_root)
        names = os.listdir(chains_descriptor)
        if (
            journal._file_observation(os.fstat(chains_descriptor)) != observed_root
            or journal._file_observation(os.lstat(chains_root)) != observed_root
        ):
            raise journal.CoordinationRefusal(TERMINAL_CHAIN_INVALID)
    except FileNotFoundError:
        if bound_journal_chain_ids:
            raise journal.CoordinationRefusal(TERMINAL_CHAIN_INVALID)
        return
    except journal.CoordinationRefusal:
        raise
    except OSError as exc:
        raise journal.CoordinationRefusal(TERMINAL_CHAIN_INVALID) from exc
    assert chains_descriptor is not None
    try:
        artifact_chain_ids: set[str] = set()
        for name in names:
            candidate = None
            if name.endswith(".events.jsonl"):
                candidate = name[: -len(".events.jsonl")]
            elif name.endswith(".json"):
                candidate = name[:-5]
            if (
                candidate is not None
                and journal.CHAIN_ID_PATTERN.fullmatch(candidate) is not None
            ):
                artifact_chain_ids.add(candidate)
        chain_ids = sorted(
            (artifact_chain_ids - captured_ingest_chain_ids)
            | bound_journal_chain_ids,
            key=os.fsencode,
        )
        for chain_id in chain_ids:
            with _optional_chain_lock(
                chains_root,
                chain_id,
                root_descriptor=chains_descriptor,
                root_observation=observed_root,
            ):
                try:
                    state = _read_json_at(chains_descriptor, f"{chain_id}.json")
                except journal.CoordinationRefusal as exc:
                    raise journal.CoordinationRefusal(
                        TERMINAL_CHAIN_INVALID
                    ) from exc
                if not isinstance(state, dict):
                    raise journal.CoordinationRefusal(TERMINAL_CHAIN_INVALID)
                run_binding = state.get("run_binding")
                if run_binding is None:
                    if chain_id in journal_chain_ids:
                        raise journal.CoordinationRefusal(
                            TERMINAL_CHAIN_INVALID
                        )
                    continue
                if "binding" in TERMINAL_CHAIN_CONTROLS and not _run_binding_valid(
                    run_binding
                ):
                    raise journal.CoordinationRefusal(TERMINAL_CHAIN_INVALID)
                if not isinstance(run_binding, dict):
                    continue
                if (
                    run_binding.get("run_id") != run_id
                    or run_binding.get("repository") != str(repository)
                    or (
                        task_id is not None
                        and run_binding.get("task_id") != task_id
                    )
                ):
                    if chain_id in journal_chain_ids:
                        raise journal.CoordinationRefusal(
                            TERMINAL_CHAIN_INVALID
                        )
                    continue
                bound_task = run_binding.get("task_id")
                if not isinstance(bound_task, str):
                    raise journal.CoordinationRefusal(TERMINAL_CHAIN_INVALID)
                if "replay" in TERMINAL_CHAIN_CONTROLS:
                    try:
                        state = _resolve_binding_from_descriptor(
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
                    except journal.CoordinationRefusal as exc:
                        if str(exc) == JOURNAL_OUTBOX_PENDING:
                            raise
                        raise journal.CoordinationRefusal(
                            TERMINAL_CHAIN_INVALID
                        ) from exc
                    replayed_binding = state.get("run_binding")
                    if replayed_binding != run_binding:
                        raise journal.CoordinationRefusal(
                            TERMINAL_CHAIN_INVALID
                        )
                if (
                    "outbox" in TERMINAL_CHAIN_CONTROLS
                    and state.get("journal_outbox") is not None
                ):
                    raise journal.CoordinationRefusal(JOURNAL_OUTBOX_PENDING)
                landings = [
                    record
                    for record in records
                    if record.get("type") == "decision"
                    and record.get("task") == bound_task
                    and record.get("outcome") == "chain-landing"
                    and isinstance(record.get("binding"), dict)
                    and isinstance(record["binding"].get("source_record"), dict)
                    and record["binding"]["source_record"].get("chain_id")
                    == chain_id
                ]
                if "landing" in TERMINAL_CHAIN_CONTROLS and len(landings) != 1:
                    raise journal.CoordinationRefusal(TERMINAL_CHAIN_INVALID)
                if "replay" in TERMINAL_CHAIN_CONTROLS and landings:
                    landing = landings[0]
                    binding_value = landing.get("binding")
                    assert isinstance(binding_value, dict)
                    binding_id = binding_value.get("binding_id")
                    if not isinstance(binding_id, str):
                        raise journal.CoordinationRefusal(TERMINAL_CHAIN_INVALID)
                    try:
                        resolved = _resolve_binding_from_descriptor(
                            repository,
                            chains_descriptor,
                            chain_id,
                            binding_id,
                            expected_type="decision",
                            expected_fields={
                                name: landing.get(name)
                                for name in (
                                    "task",
                                    "resolution",
                                    "finding",
                                    "outcome",
                                    "risk",
                                    "basis",
                                )
                            },
                            expected_run_id=run_id,
                            expected_task_id=bound_task,
                            allow_pending=True,
                        )
                    except journal.CoordinationRefusal as exc:
                        if str(exc) == JOURNAL_OUTBOX_PENDING:
                            raise
                        raise journal.CoordinationRefusal(
                            TERMINAL_CHAIN_INVALID
                        ) from exc
                    if resolved != binding_value:
                        raise journal.CoordinationRefusal(TERMINAL_CHAIN_INVALID)
                if (
                    journal._file_observation(os.fstat(chains_descriptor))
                    != observed_root
                    or journal._file_observation(os.lstat(chains_root))
                    != observed_root
                ):
                    raise journal.CoordinationRefusal(TERMINAL_CHAIN_INVALID)
    finally:
        os.close(chains_descriptor)


def run_open(
    repo: Path,
    run_id: str,
    *,
    idempotency_key: str,
    goal: str,
    scope: Sequence[str],
    plugin_ref: str,
    successor_of: str | None = None,
) -> batch.BatchOutcome:
    batch.validate_idempotency_key(idempotency_key)
    run_id = journal._operation_run_id("new run", run_id)
    repository, state_root = journal._resolve_repository(repo, "new run")
    inputs = {
        "goal": goal,
        "scope": list(scope),
        "plugin_ref": plugin_ref,
        "successor_of": successor_of,
    }
    target = state_root / ".codex-orchestrator/runs" / run_id
    try:
        os.lstat(target)
        existed = True
    except FileNotFoundError:
        existed = False
    except OSError as exc:
        raise journal.CoordinationRefusal(journal.REGISTRY_UNAVAILABLE) from exc
    if existed:
        completed = batch.lookup_existing_open_batch(
            repository,
            run_id,
            idempotency_key=idempotency_key,
            inputs=inputs,
        )
        if completed is not None:
            return completed
    _, request_sha256 = batch.normalized_request(
        repository, run_id, "run-open", inputs
    )
    # A durable hidden publication is already the original transaction.  Read
    # its exact record/capability before allocating a replacement timestamp or
    # observing mutable Git facts, then let open_run finish publication.
    recoverable = journal._recoverable_open_batch(
        repository,
        run_id,
        idempotency_key=idempotency_key,
        request_sha256=request_sha256,
    )
    if recoverable is not None:
        stored_opening, open_batch = recoverable
        stored_scope = stored_opening.get("scope")
        stored_successor = stored_opening.get("successor_of")
        if (
            not isinstance(stored_scope, list)
            or not all(isinstance(value, str) for value in stored_scope)
            or (
                stored_successor is not None
                and not isinstance(stored_successor, str)
            )
        ):
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        journal.open_run(
            repository,
            run_id,
            list(stored_scope),
            stored_opening,
            successor_of=stored_successor,
            _batch=open_batch,
        )
        return batch.complete_open_batch(
            repository,
            run_id,
            idempotency_key=idempotency_key,
            inputs=inputs,
            expected_opening=stored_opening,
            repeated=True,
        )
    _require_text("run_started.goal", goal)
    _require_text("run_started.plugin_ref", plugin_ref)
    if successor_of is not None:
        _require_text("run_started.successor_of", successor_of)
    try:
        canonical_scope = journal.canonical_scope(list(scope))
    except journal.CoordinationRefusal as exc:
        raise journal.CoordinationRefusal(
            "forge: new run refused — invalid scope"
        ) from exc
    if not canonical_scope:
        raise journal.CoordinationRefusal("forge: new run refused — invalid scope")
    opening = _with_derived(
        {
            "type": "run_started",
            "goal": goal,
            "repo": str(repository),
            "repo_head": _git_one(repository, "rev-parse", "HEAD"),
            "repo_status": _git_lines(
                repository, "status", "--short", "--untracked-files=all"
            ),
            "plugin_ref": plugin_ref,
            "scope": list(canonical_scope),
            "writer_contract": journal.WRITER_CONTRACT,
            **(
                {"successor_of": successor_of}
                if successor_of is not None
                else {}
            ),
        },
        run_id,
    )
    intent_bytes, receipt_bytes = batch.prepare_open_artifacts(
        repository,
        run_id,
        idempotency_key=idempotency_key,
        inputs=inputs,
        opening=opening,
    )
    if existed:
        resumed = batch.resume_open_creation(
            repository,
            run_id,
            intent_bytes=intent_bytes,
        )
        if resumed is not None:
            return resumed
    open_batch = journal._validated_open_batch(
        run_id,
        opening,
        intent_bytes,
        receipt_bytes,
    )
    journal.open_run(
        repository,
        run_id,
        list(canonical_scope),
        opening,
        successor_of=successor_of,
        _batch=open_batch,
    )
    expected = {
        "type": "run_started",
        "run_id": run_id,
        "goal": goal,
        "repo": str(repository),
        "plugin_ref": plugin_ref,
        "scope": list(canonical_scope),
        "writer_contract": journal.WRITER_CONTRACT,
    }
    if successor_of is not None:
        expected["successor_of"] = successor_of
    return batch.complete_open_batch(
        repository,
        run_id,
        idempotency_key=idempotency_key,
        inputs=inputs,
        expected_opening=expected,
        repeated=existed,
    )


def task_start(
    repo: Path,
    run_id: str,
    *,
    idempotency_key: str,
    task: str,
    goal: str,
    acceptance: Sequence[str],
    files: Sequence[str],
) -> batch.BatchOutcome:
    inputs = {
        "task": task,
        "goal": goal,
        "acceptance": list(acceptance),
        "file": list(files),
    }

    def validate() -> None:
        _caller_text("task", "id", task)
        _caller_text("task", "goal", goal)
        _caller_array("task", "acceptance", acceptance, nonempty=True)
        _caller_array("task", "files", files, nonempty=True)

    def validate_schema(
        _state: journal.RunState, _repository: Path
    ) -> None:
        return None

    def build(state: journal.RunState, _repository: Path) -> Sequence[dict[str, object]]:
        if "relations" in BUILDER_VALIDATION_CONTROLS and _latest_task(state, task) is not None:
            raise journal.CoordinationRefusal(
                f"forge: journal builder refused — task {task} already exists"
            )
        return (
            _with_derived(
                {
                    "type": "task",
                    "id": task,
                    "status": "active",
                    "goal": goal,
                    "acceptance": list(acceptance),
                    "files": list(files),
                },
                run_id,
            ),
        )

    return batch.execute_existing_batch(
        repo,
        run_id,
        idempotency_key=idempotency_key,
        verb="journal task-start",
        inputs=inputs,
        build_records=build,
        validate_inputs=validate,
        validate_citations=_no_citations,
        validate_record_schema=validate_schema,
    )


def task_finish(
    repo: Path,
    run_id: str,
    *,
    idempotency_key: str,
    task: str,
    status: str,
) -> batch.BatchOutcome:
    inputs = {"task": task, "status": status}

    def validate() -> None:
        _caller_text("task", "id", task)
        if not isinstance(status, str) or status not in journal.TERMINAL_TASK_STATUSES:
            journal._invalid_record_field(
                "task", "status", "must be one of complete, blocked, failed"
            )

    def validate_schema(
        _state: journal.RunState, _repository: Path
    ) -> None:
        return None

    def build(state: journal.RunState, _repository: Path) -> Sequence[dict[str, object]]:
        prior = _require_active_task(state, task)
        record = {
            "type": "task",
            "id": task,
            "status": status,
            "goal": prior.get("goal"),
            "acceptance": prior.get("acceptance"),
            "files": prior.get("files"),
        }
        return (_with_derived(record, run_id),)

    def prove(
        state: journal.RunState,
        repository: Path,
        _records: Sequence[dict[str, object]],
    ) -> None:
        _terminal_chain_guard(
            repository, run_id, state.records, task_id=task
        )

    return batch.execute_existing_batch(
        repo,
        run_id,
        idempotency_key=idempotency_key,
        verb="journal task-finish",
        inputs=inputs,
        build_records=build,
        validate_inputs=validate,
        validate_citations=_no_citations,
        validate_record_schema=validate_schema,
        prove_relations=prove,
    )


def execution_start(
    repo: Path,
    run_id: str,
    *,
    idempotency_key: str,
    agent: str,
    task: str,
    provider: str,
    role: str,
    mode: str,
    model: str,
    effort: str,
    worktree: str,
    head: str,
    prompt: str,
    handoff: str,
    event_source: str,
    events: str | None,
) -> batch.BatchOutcome:
    inputs = {
        "agent": agent,
        "task": task,
        "provider": provider,
        "role": role,
        "mode": mode,
        "model": model,
        "effort": effort,
        "worktree": worktree,
        "head": head,
        "prompt": prompt,
        "handoff": handoff,
        "event_source": event_source,
        "events": events,
    }

    def validate() -> None:
        for field, value in (
            ("agent", agent),
            ("task", task),
            ("provider", provider),
            ("role", role),
            ("mode", mode),
            ("model", model),
            ("effort", effort),
            ("worktree", worktree),
            ("prompt", prompt),
            ("handoff", handoff),
            ("event_source", event_source),
        ):
            _caller_text("execution", field, value)
        if events is not None:
            _caller_text("execution", "events", events)
        elif event_source == "exec":
            journal._invalid_record_field("execution", "events", "is required")
        worktree_path = Path(worktree)
        if not worktree_path.is_absolute():
            raise journal.CoordinationRefusal(
                f"{journal.INVALID_JOURNAL_RECORD}: execution.worktree must be an absolute path"
            )
        if (
            not isinstance(head, str)
            or journal.GIT_OBJECT_ID_PATTERN.fullmatch(head) is None
        ):
            journal._invalid_record_field(
                "execution", "head", "must be a full Git object ID"
            )

    def validate_citations(repository: Path, run_dir: Path) -> None:
        citation_record: dict[str, object] = {
            "type": "execution",
            "prompt": prompt,
            "handoff": handoff,
        }
        if events is not None:
            citation_record["events"] = events
        _validate_citation_record(repository, run_dir, citation_record)

    def validate_schema(
        _state: journal.RunState, _repository: Path
    ) -> None:
        return None

    def build(state: journal.RunState, repository: Path) -> Sequence[dict[str, object]]:
        _require_active_task(state, task)
        worktree_path = Path(worktree)
        resolved_worktree, worktree_state = journal._resolve_repository(
            worktree_path, "journal execution-start"
        )
        _, repository_state = journal._resolve_repository(
            repository, "journal execution-start"
        )
        if (
            worktree_state != repository_state
            or _git_one(resolved_worktree, "rev-parse", "HEAD") != head
        ):
            raise journal.CoordinationRefusal(
                "forge: journal builder refused — execution worktree or HEAD mismatch"
            )
        record: dict[str, object] = {
            "type": "execution",
            "execution": _allocate_id(state.records, "execution"),
            "agent": agent,
            "task": task,
            "provider": provider,
            "role": role,
            "mode": mode,
            "model": model,
            "effort": effort,
            "worktree": str(resolved_worktree),
            "head": head,
            "prompt": prompt,
            "handoff": handoff,
            "event_source": event_source,
        }
        if events is not None:
            record["events"] = events
        return (_with_derived(record, run_id),)

    return batch.execute_existing_batch(
        repo,
        run_id,
        idempotency_key=idempotency_key,
        verb="journal execution-start",
        inputs=inputs,
        build_records=build,
        validate_inputs=validate,
        validate_citations=validate_citations,
        validate_record_schema=validate_schema,
    )


def execution_result(
    repo: Path,
    run_id: str,
    *,
    idempotency_key: str,
    execution: str,
    agent: str,
    task: str,
    status: str,
    summary: str,
    files_changed: Sequence[str],
    caveats: Sequence[str],
    handoff: str | None,
) -> batch.BatchOutcome:
    inputs = {
        "execution": execution,
        "agent": agent,
        "task": task,
        "status": status,
        "summary": summary,
        "file_changed": list(files_changed),
        "caveat": list(caveats),
        "handoff": handoff,
    }

    def validate() -> None:
        _caller_text("execution_result", "execution", execution)
        if journal.EXECUTION_ID_PATTERN.fullmatch(execution) is None:
            journal._invalid_record_field(
                "execution_result", "execution", "must match execution-NN"
            )
        for field, value in (
            ("agent", agent),
            ("task", task),
            ("summary", summary),
        ):
            _caller_text("execution_result", field, value)
        if (
            not isinstance(status, str)
            or status not in journal.TERMINAL_EXECUTION_STATUSES
        ):
            journal._invalid_record_field(
                "execution_result",
                "status",
                "must be one of complete, blocked, failed",
            )
        _caller_array("execution_result", "files_changed", files_changed)
        _caller_array("execution_result", "caveats", caveats)
        if handoff is not None:
            _caller_text("execution_result", "handoff", handoff)
        elif status == "complete":
            journal._invalid_record_field(
                "execution_result", "handoff", "is required"
            )

    def validate_citations(repository: Path, run_dir: Path) -> None:
        citation_record: dict[str, object] = {"type": "execution_result"}
        if handoff is not None:
            citation_record["handoff"] = handoff
        _validate_citation_record(repository, run_dir, citation_record)

    def validate_schema(
        _state: journal.RunState, _repository: Path
    ) -> None:
        return None

    def build(state: journal.RunState, _repository: Path) -> Sequence[dict[str, object]]:
        matching = [
            record
            for record in state.records
            if record.get("type") == "execution"
            and record.get("execution") == execution
            and record.get("agent") == agent
        ]
        duplicate = any(
            record.get("type") == "execution_result"
            and record.get("execution") == execution
            and record.get("agent") == agent
            for record in state.records
        )
        if (
            "relations" in BUILDER_VALIDATION_CONTROLS
            and (
                len(matching) != 1
                or matching[0].get("task") != task
                or duplicate
            )
        ):
            raise journal.CoordinationRefusal(
                "forge: journal builder refused — execution result does not match one open execution"
            )
        record: dict[str, object] = {
            "type": "execution_result",
            "execution": execution,
            "agent": agent,
            "task": task,
            "status": status,
            "summary": summary,
            "files_changed": list(files_changed),
            "caveats": list(caveats),
        }
        if handoff is not None:
            record["handoff"] = handoff
        return (_with_derived(record, run_id),)

    return batch.execute_existing_batch(
        repo,
        run_id,
        idempotency_key=idempotency_key,
        verb="journal execution-result",
        inputs=inputs,
        build_records=build,
        validate_inputs=validate,
        validate_citations=validate_citations,
        validate_record_schema=validate_schema,
    )


def verification_add(
    repo: Path,
    run_id: str,
    *,
    idempotency_key: str,
    task: str,
    criterion: str,
    method: str,
    check: str,
    result: str,
    observation: str,
    evidence: Sequence[str],
    binding_chain: str | None,
    binding_id: str | None,
) -> batch.BatchOutcome:
    inputs = {
        "task": task,
        "criterion": criterion,
        "method": method,
        "check": check,
        "result": result,
        "observation": observation,
        "evidence": list(evidence),
        "binding_chain": binding_chain,
        "binding_id": binding_id,
    }

    def validate() -> None:
        for field, value in (
            ("task", task),
            ("criterion", criterion),
            ("method", method),
            ("check", check),
            ("observation", observation),
        ):
            _caller_text("verification", field, value)
        if not isinstance(result, str) or result not in journal.VERIFICATION_RESULTS:
            journal._invalid_record_field(
                "verification",
                "result",
                "must be one of passed, failed, inconclusive, skipped",
            )
        _caller_array("verification", "evidence", evidence)
        if (binding_chain is None) != (binding_id is None):
            raise journal.CoordinationRefusal(
                f"{journal.INVALID_JOURNAL_RECORD}: verification binding flags must be paired"
            )

    def validate_citations(repository: Path, run_dir: Path) -> None:
        _validate_citation_record(
            repository,
            run_dir,
            {
                "type": "verification",
                "observation": observation,
                "evidence": list(evidence),
            },
        )

    def validate_schema(
        state: journal.RunState, _repository: Path
    ) -> None:
        is_gate = isinstance(criterion, str) and criterion.startswith(
            journal.GATE_VERIFICATION_PREFIXES
        )
        if (
            journal._writer_contract_active(state.records)
            and is_gate
            and binding_chain is None
        ):
            journal._invalid_record_field(
                "verification",
                "binding",
                f"is required by {journal.WRITER_CONTRACT}",
            )
        if binding_chain is not None and binding_id is not None:
            _require_new_chain_binding(state, binding_chain, binding_id)

    def build(state: journal.RunState, repository: Path) -> Sequence[dict[str, object]]:
        _require_active_task(state, task)
        record: dict[str, object] = {
            "type": "verification",
            "id": _allocate_id(state.records, "verification"),
            "task": task,
            "criterion": criterion,
            "method": method,
            "check": check,
            "result": result,
            "observation": observation,
            "evidence": list(evidence),
        }
        return (_with_derived(record, run_id),)

    def resolve(
        state: journal.RunState,
        repository: Path,
        records: Sequence[dict[str, object]],
    ) -> Sequence[dict[str, object]]:
        if binding_chain is None or binding_id is None:
            return records
        record = dict(records[0])
        record["binding"] = resolve_binding(
                repository,
                binding_chain,
                binding_id,
                expected_type="verification",
                expected_fields={
                    "task": task,
                    "criterion": criterion,
                    "method": method,
                    "check": check,
                    "result": result,
                    "observation": observation,
                    "evidence": list(evidence),
                },
                expected_run_id=run_id,
                expected_task_id=task,
            )
        return (record,)

    return batch.execute_existing_batch(
        repo,
        run_id,
        idempotency_key=idempotency_key,
        verb="journal verification-add",
        inputs=inputs,
        build_records=build,
        validate_inputs=validate,
        validate_citations=validate_citations,
        validate_record_schema=validate_schema,
        resolve_records=resolve,
    )


def decision_add(
    repo: Path,
    run_id: str,
    *,
    idempotency_key: str,
    resolution: str,
    task: str | None,
    finding: str | None,
    outcome: str | None,
    risk: str | None,
    basis: Sequence[str],
    binding_chain: str | None,
    binding_id: str | None,
) -> batch.BatchOutcome:
    inputs = {
        "task": task,
        "resolution": resolution,
        "finding": finding,
        "outcome": outcome,
        "risk": risk,
        "basis": list(basis),
        "binding_chain": binding_chain,
        "binding_id": binding_id,
    }

    def validate() -> None:
        _caller_text("decision", "resolution", resolution)
        for field, value in (
            ("task", task),
            ("finding", finding),
            ("outcome", outcome),
            ("risk", risk),
        ):
            _caller_text("decision", field, value, optional=True)
        _caller_array("decision", "basis", basis)
        if (binding_chain is None) != (binding_id is None):
            raise journal.CoordinationRefusal(
                f"{journal.INVALID_JOURNAL_RECORD}: decision binding flags must be paired"
            )
        if binding_id is not None and (
            not isinstance(outcome, str)
            or outcome not in journal.CHAIN_DECISION_OUTCOMES
        ):
            journal._invalid_record_field(
                "decision",
                "outcome",
                "must be one of chain-approval, chain-skip, chain-landing",
            )

    def validate_citations(repository: Path, run_dir: Path) -> None:
        _validate_citation_record(
            repository,
            run_dir,
            {"type": "decision", "basis": list(basis)},
        )

    def validate_schema(
        state: journal.RunState, _repository: Path
    ) -> None:
        if (
            journal._writer_contract_active(state.records)
            and outcome in journal.CHAIN_DECISION_OUTCOMES
            and binding_chain is None
        ):
            journal._invalid_record_field(
                "decision",
                "binding",
                f"is required by {journal.WRITER_CONTRACT}",
            )
        if binding_chain is not None and binding_id is not None:
            _require_new_chain_binding(state, binding_chain, binding_id)

    def build(state: journal.RunState, repository: Path) -> Sequence[dict[str, object]]:
        if task is not None:
            _require_active_task(state, task)
        record: dict[str, object] = {
            "type": "decision",
            "id": _allocate_id(state.records, "decision"),
            "resolution": resolution,
            "basis": list(basis),
        }
        for name, value in (
            ("task", task),
            ("finding", finding),
            ("outcome", outcome),
            ("risk", risk),
        ):
            if value is not None:
                record[name] = value
        return (_with_derived(record, run_id),)

    def resolve(
        state: journal.RunState,
        repository: Path,
        records: Sequence[dict[str, object]],
    ) -> Sequence[dict[str, object]]:
        if binding_chain is None or binding_id is None:
            return records
        record = dict(records[0])
        record["binding"] = resolve_binding(
                repository,
                binding_chain,
                binding_id,
                expected_type="decision",
                expected_fields={
                    "task": task,
                    "resolution": resolution,
                    "finding": finding,
                    "outcome": outcome,
                    "risk": risk,
                    "basis": list(basis),
                },
                expected_run_id=run_id,
                expected_task_id=task,
            )
        return (record,)

    return batch.execute_existing_batch(
        repo,
        run_id,
        idempotency_key=idempotency_key,
        verb="journal decision-add",
        inputs=inputs,
        build_records=build,
        validate_inputs=validate,
        validate_citations=validate_citations,
        validate_record_schema=validate_schema,
        resolve_records=resolve,
    )


def run_close(
    repo: Path,
    run_id: str,
    *,
    idempotency_key: str,
    judgment: str,
    summary: str,
    risks: Sequence[str],
    follow_ups: Sequence[str],
) -> batch.BatchOutcome:
    inputs = {
        "judgment": judgment,
        "summary": summary,
        "risk": list(risks),
        "follow_up": list(follow_ups),
    }

    def validate() -> None:
        if not isinstance(judgment, str) or judgment not in {"passed", "blocked"}:
            journal._invalid_record_field(
                "run_closed", "judgment", "must be one of passed, blocked"
            )
        _caller_text("run_closed", "summary", summary)
        _caller_array("run_closed", "risks", risks)
        _caller_array("run_closed", "follow_ups", follow_ups)

    def validate_schema(
        _state: journal.RunState, _repository: Path
    ) -> None:
        return None

    def build(state: journal.RunState, _repository: Path) -> Sequence[dict[str, object]]:
        validation = journal.validate_run(state.run_dir, gates=False)
        projected = []
        for line, prior in enumerate(state.records, start=1):
            projected.append({**prior, "_line": line})
        projected.append(
            {
                "type": "run_closed",
                "judgment": judgment,
                "_line": len(projected) + 1,
            }
        )
        declaration = journal._legacy_compatibility_declaration(projected)
        declaration_line = (
            int(declaration["_line"])
            if declaration is not None
            and isinstance(declaration.get("_line"), int)
            else None
        )
        journal.check_gate_profile(
            projected,
            validation["issues"],
            validation["warnings"],
            declaration_line,
        )
        validation["profile"] = "gates"
        validation["ok"] = not validation["issues"]
        if judgment == "passed" and not validation["ok"]:
            raise journal.CoordinationRefusal(RUN_CLOSE_VALIDATION_REFUSAL)
        record = {
            "type": "run_closed",
            "judgment": judgment,
            "summary": summary,
            "validation": validation,
            "risks": list(risks),
            "follow_ups": list(follow_ups),
        }
        return (_with_derived(record, run_id),)

    def prove(
        state: journal.RunState,
        repository: Path,
        _records: Sequence[dict[str, object]],
    ) -> None:
        _terminal_chain_guard(
            repository, run_id, state.records, task_id=None
        )

    return batch.execute_existing_batch(
        repo,
        run_id,
        idempotency_key=idempotency_key,
        verb="run-close",
        inputs=inputs,
        build_records=build,
        validate_inputs=validate,
        validate_citations=_no_citations,
        validate_record_schema=validate_schema,
        prove_relations=prove,
        close=True,
    )


def ingest_chain_records(
    repo: Path,
    run_id: str,
    *,
    idempotency_key: str,
    task: str,
    state_file: str,
    events_file: str,
    outcome_map: str,
    state_sha256: str,
    events_sha256: str,
    outcome_map_sha256: str,
    closing_head: str,
    task_status: str,
    records: Sequence[dict[str, object]],
) -> batch.BatchOutcome:
    """Task-04 engine seam after its sixteen proof and capture checks pass."""

    inputs = {
        "task": task,
        "state_file": state_file,
        "events_file": events_file,
        "outcome_map": outcome_map,
        "state_file_sha256": state_sha256,
        "events_file_sha256": events_sha256,
        "outcome_map_sha256": outcome_map_sha256,
        "closing_head": closing_head,
        "task_status": task_status,
    }

    def validate_inputs() -> None:
        for record in records:
            journal._validate_record_envelope(record)
        _caller_text("ingest", "task", task)
        for field, value in (
            ("state_file", state_file),
            ("events_file", events_file),
            ("outcome_map", outcome_map),
        ):
            _caller_text("ingest", field, value)
        for field, value in (
            ("state_file_sha256", state_sha256),
            ("events_file_sha256", events_sha256),
            ("outcome_map_sha256", outcome_map_sha256),
        ):
            if (
                not isinstance(value, str)
                or journal.HEX_SHA256_PATTERN.fullmatch(value) is None
            ):
                journal._invalid_record_field(
                    "ingest", field, "must be 64 lowercase hex"
                )
        if (
            not isinstance(closing_head, str)
            or journal.GIT_OBJECT_ID_PATTERN.fullmatch(closing_head) is None
        ):
            journal._invalid_record_field(
                "ingest", "closing_head", "must be a full Git object ID"
            )
        if task_status not in journal.TERMINAL_TASK_STATUSES:
            journal._invalid_record_field(
                "ingest",
                "task_status",
                "must be one of complete, blocked, failed",
            )

    def validate_citations(repository: Path, _run_dir: Path) -> None:
        for label, value in (
            ("ingest.state_file", state_file),
            ("ingest.events_file", events_file),
            ("ingest.outcome_map", outcome_map),
        ):
            if not isinstance(value, str):
                continue
            try:
                surface = commitment_surface(label)
            except KeyError:
                surface = None
            if surface is None or validate_surface_path(
                surface,
                value,
                repository=repository,
                require_file=True,
            ) is None:
                raise journal.CoordinationRefusal(
                    "forge: journal append refused — record cites path outside run or "
                    f"repository: {label}: {value}"
                )

    def validate_schema(
        _state: journal.RunState, _repository: Path
    ) -> None:
        return None

    def verify_authority(
        repository: Path,
        existing: Sequence[dict[str, object]] | None = None,
    ) -> tuple[dict[str, object], ...]:
        verifier = _INGEST_PROOF_VERIFIER
        if (
            INGEST_PROOF_CONTROLS != _REQUIRED_INGEST_PROOFS
            or verifier is None
        ):
            raise journal.CoordinationRefusal(INGEST_PROOF_INVALID)
        try:
            verified, completed_proofs = verifier(
                repository, run_id, copy.deepcopy(inputs)
            )
            verified_records = tuple(copy.deepcopy(tuple(verified)))
        except journal.CoordinationRefusal as exc:
            if str(exc).startswith(_INGEST_CAPTURE_CITATION_PREFIX):
                raise
            raise journal.CoordinationRefusal(INGEST_PROOF_INVALID) from exc
        except (KeyError, TypeError, ValueError, RuntimeError) as exc:
            raise journal.CoordinationRefusal(INGEST_PROOF_INVALID) from exc
        supplied_records = tuple(records)
        if (
            completed_proofs != _INGEST_PROOF_ORDER
            or not verified_records
            or not all(isinstance(record, dict) for record in verified_records)
            or verified_records != supplied_records
            or (
                existing is not None
                and tuple(existing) != verified_records
            )
        ):
            raise journal.CoordinationRefusal(INGEST_PROOF_INVALID)
        return verified_records

    authorized_records: tuple[dict[str, object], ...] | None = None

    def authorize(
        repository: Path,
        existing: Sequence[dict[str, object]] | None = None,
    ) -> tuple[dict[str, object], ...]:
        nonlocal authorized_records
        if authorized_records is not None:
            if existing is not None and tuple(existing) != authorized_records:
                raise journal.CoordinationRefusal(INGEST_PROOF_INVALID)
            return authorized_records
        authorized_records = verify_authority(repository, existing)
        return authorized_records

    def validate_existing(
        existing: Sequence[dict[str, object]],
    ) -> None:
        repository, _state_root = journal._resolve_repository(
            repo, "journal ingest-chain"
        )
        authorize(repository, existing)

    def build_records(
        _state: journal.RunState, repository: Path
    ) -> Sequence[dict[str, object]]:
        return authorize(repository)

    def validate_authorized_transaction_base(
        _journal_exact: journal.ExactFile,
        _receipts_exact: journal.ExactFile,
    ) -> None:
        if authorized_records is None:
            raise journal.CoordinationRefusal(INGEST_PROOF_INVALID)
        repository, _state_root = journal._resolve_repository(
            repo, "journal ingest-chain"
        )
        reverified = verify_authority(
            repository,
            authorized_records,
        )
        if reverified != authorized_records:
            raise journal.CoordinationRefusal(INGEST_PROOF_INVALID)

    return batch.execute_existing_batch(
        repo,
        run_id,
        idempotency_key=idempotency_key,
        verb="journal ingest-chain",
        inputs=inputs,
        build_records=build_records,
        validate_inputs=validate_inputs,
        validate_citations=validate_citations,
        validate_record_schema=validate_schema,
        validate_transaction_base=validate_authorized_transaction_base,
        validate_existing=validate_existing,
    )
