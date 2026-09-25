"""Commit-chain gate-evidence predicates (split from _commit_chain.py).

These read only persisted chain state: which gates an operator skipped, whether
the newest Gate-1 record for the current candidate is a passed run or the
docs-class skip, and whether a step's latest record is a current pass.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from forge_cli import fresh_evals as fresh_eval_module
from forge_cli.chain_core._state import FRESH_REVIEWER_EVALS_GATE


def _user_skip(state: Mapping[str, Any], gate_id: str) -> dict[str, Any] | None:
    value = state["steps"].get("user_skips", {})
    if not isinstance(value, dict):
        return None
    record = value.get(gate_id)
    return record if isinstance(record, dict) else None


DOCS_CLASS_SKIP_REASON = "docs-class candidate"


def _docs_class_candidate(state: Mapping[str, Any]) -> bool:
    """True only when the current classification proves every path docs-class.

    The proof is the classifier's own per-path evidence bound to the pinned
    policy: every recorded path carries exactly the ``docs`` category, no
    control floor, and no trigger match, and the classification record is
    current for the staged candidate.  Anything less runs Gate 1.
    """

    if not _latest_current_pass(state, "classification"):
        return False
    tier = state.get("tier")
    classification = tier.get("classification") if isinstance(tier, Mapping) else None
    evidence = classification.get("paths") if isinstance(classification, Mapping) else None
    if (
        not isinstance(tier, Mapping)
        or tier.get("control") is not False
        or not isinstance(evidence, list)
        or not evidence
        or not all(isinstance(item, Mapping) for item in evidence)
    ):
        return False
    recorded = {str(path) for path in state.get("paths", [])}
    if {str(item.get("path")) for item in evidence} != recorded:
        return False
    return all(
        item.get("categories") == ["docs"]
        and item.get("control_floor") is False
        and item.get("trigger_matches") == []
        for item in evidence
    )


def _gate_one_complete(state: Mapping[str, Any]) -> bool:
    """Gate 1 is complete after one current passed run or one docs-class skip."""

    if _user_skip(state, "gate-1") is not None:
        return True
    runs = state["steps"].get("gate-1")
    if not isinstance(runs, list):
        return False
    candidate = state["candidate"].get("sha256")
    current_runs = [
        record
        for record in runs
        if isinstance(record, dict) and record.get("candidate") == candidate
    ]
    if not current_runs:
        return False
    newest = current_runs[-1]
    if newest.get("result") == "passed":
        return True
    return (
        newest.get("result") == "skipped"
        and newest.get("reason") == DOCS_CLASS_SKIP_REASON
    )


def _latest_current_pass(state: Mapping[str, Any], step_id: str) -> bool:
    value = state["steps"].get(step_id)
    candidate = state["candidate"].get("sha256")
    if isinstance(value, list) and value:
        record = value[-1]
        return record.get("candidate") == candidate and record.get("result") == "passed"
    return False


def _stack_batch_satisfied(state: Mapping[str, Any], gate_id: str) -> bool:
    """Every cell of the newest stack batch passed for the current candidate."""

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
        return _stack_batch_satisfied(state, gate_id)
    return _latest_current_pass(state, gate_id)
