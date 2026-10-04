"""Archive-only authentication of replayed historical journal bindings."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

from . import journal, landed_evidence

SUPERSEDED = "superseded candidate"
ABORTED = "aborted chain"
RECHECKED = "failed gate cleared by passing recheck"
RERUN = "earlier run of the same step"
CURRENT = "current"

_CONTROL_BY_REASON = {
    SUPERSEDED: "historical-binding",
    ABORTED: "historical-abort",
    RECHECKED: "historical-recheck",
    RERUN: "historical-rerun",
}
_CURRENCY_BY_REASON = {
    SUPERSEDED: frozenset({"superseded"}),
    ABORTED: frozenset({"current", "rerun"}),
    RECHECKED: frozenset({"rerun"}),
    RERUN: frozenset({"rerun"}),
}
_GATE_PREFIXES = ("gate-1: ", "gate-2: ", "gate-3: ")


@dataclass(frozen=True)
class ResolutionContext:
    """Patched archive seams and immutable inputs for live-chain replay."""

    repository: Path
    run_id: str
    directory: int
    chains: Mapping[str, Any]
    journal_records: Sequence[dict[str, Any]]
    controls: frozenset[str]
    builders: Any
    require_exact: Callable[[Any, str, Mapping[str, object]], None]
    refuse: Callable[[str], NoReturn]


@dataclass(frozen=True)
class ResolvedBindings(Mapping[int, dict[str, object]]):
    """Resolved bindings with an explicit display classification per line."""

    bindings: Mapping[int, dict[str, object]]
    classifications: Mapping[int, str]

    def __post_init__(self) -> None:
        bindings = dict(self.bindings)
        classifications = dict(self.classifications)
        allowed = {CURRENT, *_CONTROL_BY_REASON}
        if set(bindings) != set(classifications) or not set(
            classifications.values()
        ) <= allowed:
            raise ValueError("incomplete binding classifications")
        object.__setattr__(self, "bindings", bindings)
        object.__setattr__(self, "classifications", classifications)

    def __getitem__(self, line: int) -> dict[str, object]:
        return self.bindings[line]

    def __iter__(self) -> Iterator[int]:
        return iter(self.bindings)

    def __len__(self) -> int:
        return len(self.bindings)


def historical_reason(
    bindings: Mapping[int, dict[str, object]],
    line: int,
    refuse: Callable[[str], NoReturn],
) -> str | None:
    if not isinstance(bindings, ResolvedBindings) or line not in bindings.classifications:
        refuse("structured_chain_mismatch")
    classification = bindings.classifications[line]
    return None if classification == CURRENT else classification


def binding_status(binding_id: object, reason: str | None) -> str:
    """Render the one historical status grammar without altering current rows."""

    if reason is None:
        return f"BOUND ({binding_id})"
    return (
        "BOUND — source-authenticated history; NOT LANDING EVIDENCE "
        f"({reason}; {binding_id})"
    )


def status_for(
    bindings: Mapping[int, dict[str, object]],
    line: int,
    binding_id: object,
    refuse: Callable[[str], NoReturn],
) -> str:
    return binding_status(binding_id, historical_reason(bindings, line, refuse))


def journal_mapping(
    bindings: Mapping[int, dict[str, object]],
    line: int,
    binding_id: object,
    refuse: Callable[[str], NoReturn],
) -> str:
    reason = historical_reason(bindings, line, refuse)
    value = binding_status(binding_id, reason) if reason else str(binding_id)
    return f"- line {line}: {value}"


def decision_history_lines(
    bindings: Mapping[int, dict[str, object]],
    line: int,
    binding: Mapping[str, object],
    refuse: Callable[[str], NoReturn],
) -> list[str]:
    reason = historical_reason(bindings, line, refuse)
    source = binding.get("source_record")
    if reason is None or not isinstance(source, dict):
        return []
    return [
        f"Binding source: {source['chain_id']}@{source['event_digest']}",
        "",
        f"Binding status: {binding_status(binding['binding_id'], reason)}",
        "",
    ]


def v2_authorization_id(candidate: Mapping[str, object]) -> str | None:
    value = candidate.get("value")
    authorization_id = value.get("authorization_id") if isinstance(value, dict) else None
    if (
        candidate.get("kind") == "git-tree-candidate-v2"
        and isinstance(authorization_id, str)
        and journal.HEX_SHA256_PATTERN.fullmatch(authorization_id)
    ):
        return authorization_id
    return None


def _refuse(context: ResolutionContext) -> NoReturn:
    context.refuse("structured_chain_mismatch")


def _ordered_records(
    required_by_chain: Mapping[str, Sequence[dict[str, Any]]],
    live_ids: set[str],
) -> list[dict[str, Any]]:
    return [
        record
        for chain_id in sorted(live_ids, key=lambda value: value.encode())
        for record in required_by_chain[chain_id]
    ]


def _record_parts(
    context: ResolutionContext, record: dict[str, Any]
) -> tuple[int, dict[str, object], str]:
    line = record.get("_line")
    binding = record.get("binding")
    source = binding.get("source_record") if isinstance(binding, dict) else None
    chain_id = source.get("chain_id") if isinstance(source, dict) else None
    if (
        type(line) is not int
        or int(line) <= 0
        or not isinstance(binding, dict)
        or not isinstance(chain_id, str)
        or chain_id not in context.chains
    ):
        _refuse(context)
    return int(line), binding, chain_id


def _replay(
    context: ResolutionContext,
    record: dict[str, Any],
    *,
    historical: bool,
) -> dict[str, object]:
    _line, binding, chain_id = _record_parts(context, record)
    expected_fields = {
        name: value for name, value in record.items() if name not in {"_line", "binding"}
    }
    task_id = record.get("task")
    options = {"historical": True} if historical else {}
    return context.builders._resolve_binding_from_descriptor(
        context.repository,
        context.directory,
        chain_id,
        str(binding["binding_id"]),
        expected_type=str(record.get("type")),
        expected_fields=expected_fields,
        expected_run_id=context.run_id,
        expected_task_id=task_id if isinstance(task_id, str) else None,
        **options,
    )


def _resolve_current(
    context: ResolutionContext, records: Sequence[dict[str, Any]]
) -> tuple[dict[int, dict[str, object]], dict[int, str], list[dict[str, Any]]]:
    resolved: dict[int, dict[str, object]] = {}
    currency: dict[int, str] = {}
    deferred: list[dict[str, Any]] = []
    for record in records:
        line, binding, chain_id = _record_parts(context, record)
        context.require_exact(
            context.chains[chain_id], str(binding["binding_id"]), record
        )
        try:
            replayed = _replay(context, record, historical=False)
        except (OSError, RuntimeError, TypeError, ValueError, journal.CoordinationRefusal):
            deferred.append(record)
            continue
        if replayed != binding or line in resolved:
            _refuse(context)
        resolved[line] = dict(binding)
        currency[line] = "current"
    return resolved, currency, deferred


def _resolve_deferred(
    context: ResolutionContext,
    records: Sequence[dict[str, Any]],
    resolved: dict[int, dict[str, object]],
    currency: dict[int, str],
) -> None:
    for record in records:
        line, binding, _chain_id = _record_parts(context, record)
        try:
            replayed = _replay(context, record, historical=True)
        except (OSError, RuntimeError, TypeError, ValueError, journal.CoordinationRefusal):
            _refuse(context)
        if (
            set(replayed) != {"binding", "currency"}
            or replayed.get("binding") != binding
            or replayed.get("currency") not in {"superseded", "rerun"}
            or line in resolved
        ):
            _refuse(context)
        resolved[line] = dict(binding)
        currency[line] = str(replayed["currency"])


def _terminal_anchors(
    context: ResolutionContext,
    records: Sequence[dict[str, Any]],
    currency: Mapping[int, str],
) -> dict[str, str]:
    anchors: dict[str, str] = {}
    by_chain: dict[str, list[str]] = {}
    for record in records:
        line, _binding, chain_id = _record_parts(context, record)
        outcome = record.get("outcome")
        if currency.get(line) == "current" and outcome in {
            "chain-landing",
            "chain-abort",
        }:
            by_chain.setdefault(chain_id, []).append(str(outcome))
    for chain_id, outcomes in by_chain.items():
        state = getattr(context.chains[chain_id], "state", None)
        if not isinstance(state, dict):
            _refuse(context)
        if state.get("state") == "closed" and outcomes == ["chain-landing"]:
            anchors[chain_id] = "chain-landing"
        elif (
            state.get("state") == "aborted"
            and state.get("journal_outbox") is None
            and outcomes == ["chain-abort"]
        ):
            anchors[chain_id] = "chain-abort"
        else:
            _refuse(context)
    return anchors


def _same_pair(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_bound = journal._binding_chain_and_candidate(left)
    right_bound = journal._binding_chain_and_candidate(right)
    return bool(
        left_bound is not None
        and right_bound is not None
        and left_bound[:2] == right_bound[:2]
    )


def _cleared_by_current_recheck(
    record: dict[str, Any],
    verifications: Sequence[dict[str, Any]],
    recheck: Callable[[list[dict[str, object]], int], bool],
    current_lines: set[int],
) -> bool:
    if record.get("result") != "failed" or record not in verifications:
        return False
    index = verifications.index(record)
    if not recheck(list(verifications), index):
        return False
    return any(
        later.get("criterion") == record.get("criterion")
        and later.get("result") == "passed"
        and later.get("_line") in current_lines
        and _same_pair(record, later)
        for later in verifications[index + 1 :]
    )


def _step_key(record: dict[str, Any]) -> tuple[str, str, bytes] | None:
    criterion = record.get("criterion")
    bound = journal._binding_chain_and_candidate(record)
    if record.get("type") != "verification" or not isinstance(criterion, str):
        return None
    if bound is None:
        return None
    return criterion, bound[0], bound[1]


def _newest_steps(
    verifications: Sequence[dict[str, Any]],
) -> dict[tuple[str, str, bytes], dict[str, Any]]:
    newest: dict[tuple[str, str, bytes], dict[str, Any]] = {}
    for record in verifications:
        key = _step_key(record)
        if key is not None:
            newest[key] = record
    return newest


def _reason_for(
    record: dict[str, Any],
    *,
    superseded: set[str],
    aborted: bool,
    cleared: bool,
    newest_steps: Mapping[tuple[str, str, bytes], dict[str, Any]],
    current_lines: set[int],
) -> str | None:
    binding = record.get("binding")
    binding_id = binding.get("binding_id") if isinstance(binding, dict) else None
    if binding_id in superseded:
        return SUPERSEDED
    if aborted:
        return ABORTED
    if cleared:
        return RECHECKED
    if record.get("result") == "failed":
        return None
    key = _step_key(record)
    newest = newest_steps.get(key) if key is not None else None
    if (
        newest is not None
        and newest is not record
        and newest.get("_line") in current_lines
    ):
        return RERUN
    return None


def _historical_record_allowed(record: dict[str, Any]) -> bool:
    criterion = record.get("criterion")
    return bool(
        (
            record.get("type") == "verification"
            and isinstance(criterion, str)
            and criterion.startswith(_GATE_PREFIXES)
        )
        or (
            record.get("type") == "decision"
            and record.get("outcome") in {"chain-approval", "chain-skip"}
        )
    )


def _classify(
    context: ResolutionContext,
    records: Sequence[dict[str, Any]],
    currency: Mapping[int, str],
) -> dict[int, str]:
    anchors = _terminal_anchors(context, records, currency)
    journal_records = list(context.journal_records)
    superseded = journal._superseded_binding_ids(journal_records)
    retired = landed_evidence.retirement_predicate(journal_records)
    verifications = [
        record for record in journal_records if record.get("type") == "verification"
    ]
    recheck = landed_evidence.recheck_source(journal_records)
    newest_steps = _newest_steps(verifications)
    current_lines = {line for line, value in currency.items() if value == "current"}
    historical: dict[int, str] = {}
    for record in records:
        line, binding, chain_id = _record_parts(context, record)
        anchor = anchors.get(chain_id)
        binding_id = binding.get("binding_id")
        journal_aborted = retired(record)
        if binding_id not in superseded and (
            (anchor == "chain-abort") != journal_aborted
        ):
            _refuse(context)
        cleared = _cleared_by_current_recheck(
            record, verifications, recheck, current_lines
        )
        reason = _reason_for(
            record,
            superseded=superseded,
            aborted=anchor == "chain-abort" and journal_aborted,
            cleared=cleared,
            newest_steps=newest_steps,
            current_lines=current_lines,
        )
        if reason is None:
            if currency[line] != "current":
                _refuse(context)
            continue
        if (
            anchor is None
            or _CONTROL_BY_REASON[reason] not in context.controls
            or currency[line] not in _CURRENCY_BY_REASON[reason]
            or (currency[line] != "current" and not _historical_record_allowed(record))
        ):
            _refuse(context)
        historical[line] = reason
    return historical


def resolve_live_bindings(
    context: ResolutionContext,
    required_by_chain: Mapping[str, Sequence[dict[str, Any]]],
    live_ids: set[str],
) -> tuple[dict[int, dict[str, object]], dict[int, str]]:
    """Resolve current anchors first, then authenticate and classify history."""

    records = _ordered_records(required_by_chain, live_ids)
    resolved, currency, deferred = _resolve_current(context, records)
    _resolve_deferred(context, deferred, resolved, currency)
    historical = _classify(context, records, currency)
    classifications: dict[int, str] = {}
    for line in resolved:
        reason = historical.get(line)
        if reason is None and currency.get(line) != CURRENT:
            _refuse(context)
        classifications[line] = reason or CURRENT
    return resolved, classifications
