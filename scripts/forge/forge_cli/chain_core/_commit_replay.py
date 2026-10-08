"""Authenticate commit event facts without journal or run authority."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ._state import STATE_KEYS

LEGACY_COMMIT_EVENTS = frozenset({"journal_receipted", "abort_disposition_recorded"})


def _legacy_fact_valid(
    event: Mapping[str, Any], prior: Mapping[str, Any] | None, current: Mapping[str, Any]
) -> bool:
    if prior is None or not {"run_binding", "journal_outbox"} & set(prior):
        return False
    ignored = {"last_event_at", "inactive_after"}
    return all(prior.get(name) == current.get(name) for name in STATE_KEYS - ignored)


def _produced_identity_precedes(
    event: Mapping[str, Any], prior: Mapping[str, Any] | None, current: Mapping[str, Any]
) -> bool:
    identity = prior.get("commit_result", {}).get("identity") if prior else None
    introduced = current.get("commit_result", {}).get("identity")
    if introduced is not None and introduced != identity:
        if event["payload"]["event"] != "commit_identity_checked":
            return False
    if event["payload"]["event"] not in {"commit_produced", "commit_close_recovered"}:
        return True
    candidate = current.get("candidate", {})
    if candidate.get("schema") is None:
        return True
    if prior is None:
        return False
    return bool(
        isinstance(identity, Mapping)
        and identity.get("result") == "passed"
        and identity == current.get("commit_result", {}).get("identity")
        and identity.get("produced_sha") == current.get("commit_result", {}).get("commit_sha")
        and identity.get("expected", {}).get("tree") == candidate.get("tree_oid")
        and identity.get("expected", {}).get("parent") == candidate.get("base_commit_oid")
    )


def commit_event_fact_valid(event: Mapping[str, Any], prior: Mapping[str, Any] | None) -> bool:
    """Validate the event's exact append state; historical candidates stay historical."""
    payload = event["payload"]
    current = payload["state"]
    if not isinstance(payload.get("details"), Mapping):
        return False
    if not {"run_binding", "journal_outbox"} & set(current) and {
        "journal_batch", "source_event_digest"
    } & set(payload["details"]):
        return False
    if payload["event"] in LEGACY_COMMIT_EVENTS:
        return _legacy_fact_valid(event, prior, current)
    return _produced_identity_precedes(event, prior, current)


def new_commit_event_admitted(event: str, details: Mapping[str, Any]) -> bool:
    """Retired event carriers are reader-only, including on legacy chains."""
    return event not in LEGACY_COMMIT_EVENTS and not {"journal_batch", "source_event_digest"} & set(
        details
    )
