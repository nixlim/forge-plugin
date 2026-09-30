from __future__ import annotations

from collections.abc import Callable

from . import journal

LANDED_EVIDENCE_CONTROLS = frozenset({"landed-candidate-evidence"})


def retirement_predicate(
    records: list[dict[str, object]],
) -> Callable[[dict[str, object]], bool]:
    """Return the correlation rule for superseded and aborted bindings.

    Supersession intentionally remains global by binding id, matching
    ``journal._superseded_binding_ids`` and the original correlation rule.
    Abort retirement is scoped to the bound record's own task and chain.
    """

    superseded = journal._superseded_binding_ids(records)
    aborted = {
        (task, bound[0])
        for record in records
        if record.get("type") == "decision"
        and record.get("outcome") == "chain-abort"
        and isinstance((task := record.get("task")), str)
        and (bound := journal._binding_chain_and_candidate(record)) is not None
    }

    def retired(record: dict[str, object]) -> bool:
        task = record.get("task")
        bound = journal._binding_chain_and_candidate(record)
        return bound is not None and (
            bound[2] in superseded
            or (isinstance(task, str) and (task, bound[0]) in aborted)
        )

    return retired


def landed_keys(records: list[dict[str, object]]) -> set[tuple[str, bytes]]:
    """Return the bound ``(chain, candidate)`` pairs recorded as landed."""

    return {
        (bound[0], bound[1])
        for record in records
        if record.get("type") == "decision"
        and record.get("outcome") == "chain-landing"
        and (bound := journal._binding_chain_and_candidate(record)) is not None
    }


def _counting_predicate(
    records: list[dict[str, object]],
) -> Callable[[dict[str, object]], bool]:
    if (
        "landed-candidate-evidence" not in LANDED_EVIDENCE_CONTROLS
        or not journal._writer_contract_active(records)
    ):
        return lambda _verification: True
    retired = retirement_predicate(records)
    landed = landed_keys(records)

    def counts(verification: dict[str, object]) -> bool:
        bound = journal._binding_chain_and_candidate(verification)
        return (
            bound is not None
            and not retired(verification)
            and (bound[0], bound[1]) in landed
        )

    return counts


def missing_gate_issues(
    records: list[dict[str, object]],
    verifications: list[dict[str, object]],
    last_line: int,
    unterminated: bool,
) -> list[str]:
    """Report FR-021 gates missing after the mutation boundary."""

    required_gates = (
        ("gate-1", lambda criterion: criterion.startswith("gate-1: ")),
        ("gate-2", lambda criterion: criterion.startswith("gate-2: ")),
        (
            journal.GATE_3_CRITERION,
            lambda criterion: criterion == journal.GATE_3_CRITERION,
        ),
    )
    counts = _counting_predicate(records)
    issues: list[str] = []
    for gate_name, criterion_matches in required_gates:
        has_passing_gate = not unterminated and any(
            verification.get("result") == "passed"
            and isinstance((criterion := verification.get("criterion")), str)
            and criterion_matches(criterion)
            and int(verification.get("_line", 0)) > last_line
            and counts(verification)
            for verification in verifications
        )
        if not has_passing_gate:
            issues.append(
                "run closed as passed without a passing "
                f"'{gate_name}' verification after the last mutating execution"
            )
    return issues
