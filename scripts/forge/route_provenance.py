"""FR-247 task-completion provenance over journal records."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from typing import NoReturn

import route_vocab

IMPLEMENTER_EXECUTION = "implementer-execution"
CHAIN_LANDING = "chain-landing"
ORCHESTRATOR_OWNED = "orchestrator-owned"
ORCHESTRATOR_PREFIX = "orchestrator-owned: "
HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
CHAIN_ID = re.compile(r"c-\d{4}-\d{2}-\d{2}T\d{6}Z-[0-9a-f]{4}\Z")
GIT_OBJECT_ID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
CANDIDATE_KINDS = frozenset(
    ("git-tree-candidate-v2", "staged-diff-sha256", "git-commit", "git-range")
)
OBJECT_FORMAT_LENGTHS = {"sha1": 40, "sha256": 64}
TREE_CANDIDATE_DOMAIN = b"forge-commit-candidate/2\0"


def route_aware(records: Sequence[dict[str, object]]) -> bool:
    """Whether the run-opening record physically carries the J-era snapshot."""

    return bool(
        records
        and records[0].get("type") == "run_started"
        and "route" in records[0]
    )


def is_orchestrator_owned(record: dict[str, object], task_id: str) -> bool:
    """Recognize the exact FR-247(c) typed-decision grammar."""

    resolution = record.get("resolution")
    basis = record.get("basis")
    return bool(
        record.get("type") == "decision"
        and record.get("task") == task_id
        and isinstance(resolution, str)
        and resolution.startswith(ORCHESTRATOR_PREFIX)
        and resolution.removeprefix(ORCHESTRATOR_PREFIX).strip()
        and isinstance(basis, list)
        and basis
        and all(isinstance(item, str) and item for item in basis)
    )


def _tree_authorization_id(object_format: object, tree_oid: object) -> str | None:
    if (
        not isinstance(object_format, str)
        or object_format not in OBJECT_FORMAT_LENGTHS
        or not isinstance(tree_oid, str)
        or re.fullmatch(
            rf"[0-9a-f]{{{OBJECT_FORMAT_LENGTHS[object_format]}}}", tree_oid
        )
        is None
    ):
        return None
    return hashlib.sha256(
        TREE_CANDIDATE_DOMAIN
        + object_format.encode("ascii")
        + b"\0"
        + tree_oid.encode("ascii")
        + b"\n"
    ).hexdigest()


def _valid_candidate(candidate: object) -> bool:
    if not isinstance(candidate, dict) or set(candidate) != {"kind", "value"}:
        return False
    kind, value = candidate.get("kind"), candidate.get("value")
    if kind not in CANDIDATE_KINDS:
        return False
    if kind == "staged-diff-sha256":
        return isinstance(value, str) and HEX_SHA256.fullmatch(value) is not None
    if kind == "git-tree-candidate-v2":
        return bool(
            isinstance(value, dict)
            and set(value) == {"authorization_id", "object_format", "tree_oid"}
            and isinstance(value.get("authorization_id"), str)
            and value.get("authorization_id")
            == _tree_authorization_id(value.get("object_format"), value.get("tree_oid"))
        )
    if kind == "git-commit":
        return isinstance(value, str) and GIT_OBJECT_ID.fullmatch(value) is not None
    return bool(
        isinstance(value, dict)
        and set(value) == {"base", "head"}
        and all(
            isinstance(value.get(name), str)
            and GIT_OBJECT_ID.fullmatch(value[name]) is not None
            for name in ("base", "head")
        )
    )


def _bound_landing(record: dict[str, object], task_id: str) -> bool:
    if (
        record.get("type") != "decision"
        or record.get("task") != task_id
        or record.get("outcome") != CHAIN_LANDING
    ):
        return False
    binding = record.get("binding")
    if not isinstance(binding, dict) or set(binding) != {
        "schema",
        "source_record",
        "candidate",
        "review",
        "binding_id",
    }:
        return False
    source = binding.get("source_record")
    if (
        binding.get("schema") != "forge-gate-binding/1"
        or binding.get("review") is not None
        or not isinstance(source, dict)
        or set(source) != {"chain_id", "event_digest"}
        or not isinstance(source.get("chain_id"), str)
        or CHAIN_ID.fullmatch(str(source["chain_id"])) is None
        or not isinstance(source.get("event_digest"), str)
        or HEX_SHA256.fullmatch(str(source["event_digest"])) is None
        or not _valid_candidate(binding.get("candidate"))
    ):
        return False
    preimage = {
        "schema": binding["schema"],
        "source_record": source,
        "candidate": binding["candidate"],
        "review": None,
    }
    try:
        canonical = json.dumps(
            preimage, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        return False
    return binding.get("binding_id") == hashlib.sha256(canonical).hexdigest()


def _terminal_results(
    records: Sequence[dict[str, object]],
) -> dict[tuple[object, object], dict[str, object]]:
    results: dict[tuple[object, object], dict[str, object]] = {}
    for record in records:
        agent, execution = record.get("agent"), record.get("execution")
        if (
            record.get("type") == "execution_result"
            and isinstance(agent, str)
            and isinstance(execution, str)
        ):
            results.setdefault((agent, execution), record)
    return results


def _complete_implementer(
    records: Sequence[dict[str, object]], task_id: str
) -> bool:
    results = _terminal_results(records)
    for record in records:
        if record.get("type") != "execution" or record.get("task") != task_id:
            continue
        agent, execution = record.get("agent"), record.get("execution")
        if not isinstance(agent, str) or not isinstance(execution, str):
            continue
        provider_value, role_value = record.get("provider"), record.get("role")
        provider = (
            route_vocab.canonical_provider(provider_value)
            if isinstance(provider_value, str)
            else None
        )
        role = (
            route_vocab.canonical_role(role_value, provider or "")
            if isinstance(role_value, str)
            else None
        )
        result = results.get((agent, execution))
        if (
            role == "implementer"
            and isinstance(result, dict)
            and result.get("task") == task_id
            and result.get("status") == "complete"
        ):
            return True
    return False


def completion_provenance(
    records: Sequence[dict[str, object]], task_id: str
) -> str | None:
    """Return the FR-247 admitting provenance kind, or ``None``."""

    if _complete_implementer(records, task_id):
        return IMPLEMENTER_EXECUTION
    if any(_bound_landing(record, task_id) for record in records):
        return CHAIN_LANDING
    if any(is_orchestrator_owned(record, task_id) for record in records):
        return ORCHESTRATOR_OWNED
    return None


def complete_tasks(records: Sequence[dict[str, object]]) -> list[str]:
    """Return every task ever recorded complete, bytewise sorted."""

    tasks = {
        str(record["id"])
        for record in records
        if record.get("type") == "task"
        and record.get("status") == "complete"
        and isinstance(record.get("id"), str)
    }
    return sorted(tasks, key=lambda value: value.encode("utf-8"))


def _raise(message: str, refusal: type[Exception]) -> NoReturn:
    raise refusal(message)


def enforce_task_finish(
    records: Sequence[dict[str, object]],
    task_id: str,
    status: str,
    files: object,
    *,
    refusal: type[Exception] = RuntimeError,
) -> None:
    """Apply the route-aware task-finish half of FR-247."""

    if (
        route_aware(records)
        and status == "complete"
        and isinstance(files, list)
        and files
        and completion_provenance(records, task_id) is None
    ):
        _raise(
            f"forge: task-finish refused — task {task_id} has no completion "
            "provenance (FR-247: implementer execution with a complete result, "
            "bound chain-landing decision, or an 'orchestrator-owned: <reason>' "
            "decision with basis)",
            refusal,
        )


def enforce_run_close(
    records: Sequence[dict[str, object]],
    judgment: str,
    *,
    refusal: type[Exception] = RuntimeError,
) -> None:
    """Apply the route-aware passed-run close half of FR-247."""

    if not route_aware(records) or judgment != "passed":
        return
    offenders = [
        task_id
        for task_id in complete_tasks(records)
        if completion_provenance(records, task_id) is None
    ]
    if offenders:
        _raise(
            "\n".join(
                f"forge: run-close refused — task {task_id} recorded complete "
                "without completion provenance (FR-247)"
                for task_id in offenders
            ),
            refusal,
        )
