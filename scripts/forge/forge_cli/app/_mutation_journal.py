"""Extracted from scripts/forge/forge_cli/app/__init__.py."""
from __future__ import annotations
from typing import Sequence, Any
from forge_cli import runtime, chain_core
from pathlib import Path
from forge_cli.policy import sha256_bytes
import dataclasses
import json


_MUTATION_JOURNAL_SCHEMA = "forge-scoped-mutation-journal/1"


_MUTATION_JOURNAL_SIDEBAND_PREFIX = b"\x00FMJ1\x00"


_MUTATION_PERSISTENCE_ADVISORY = (
    "forge: scoped mutation journal persistence unavailable — advisory evidence emitted only"
)


_MUTATION_JOURNAL_REQUEST_KEYS = frozenset(
    {
        "schema",
        "repository",
        "run_id",
        "task",
        "base",
        "head",
        "criterion",
        "method",
        "check",
        "result",
        "truncated_observation",
        "evidence",
        "idempotency_key",
    }
)


_MUTATION_JOURNAL_PREIMAGE_KEYS = (
    "schema",
    "repository",
    "run_id",
    "task",
    "base",
    "head",
    "criterion",
    "result",
    "check",
    "truncated_observation",
    "evidence",
)


class _DeferredMutationRequestError(ValueError):
    """Private sideband validation failure; never an operator refusal literal."""


def _mutation_persistence_error(error: Exception) -> bytes:
    detail = str(error)
    if isinstance(error, _DeferredMutationRequestError) or not detail.startswith("forge: "):
        detail = ""
    lines = ([detail] if detail else []) + [_MUTATION_PERSISTENCE_ADVISORY]
    return ("\n".join(lines) + "\n").encode("utf-8", "backslashreplace")


def _bounded_mutation_output(
    public_parts: Sequence[bytes], diagnostics: Sequence[bytes]
) -> bytes:
    public_output = b"".join(public_parts)
    diagnostic_output = b"".join(diagnostics)
    limit = runtime.OUTPUT_CAP_BYTES
    if len(public_output) + len(diagnostic_output) <= limit:
        return public_output + diagnostic_output
    if len(diagnostic_output) <= limit:
        return public_output[: limit - len(diagnostic_output)] + diagnostic_output
    advisory = (_MUTATION_PERSISTENCE_ADVISORY + "\n").encode("utf-8")
    return diagnostic_output[: limit - len(advisory)] + advisory


def _validate_deferred_mutation_request(
    request: object,
    *,
    repository: Path,
    run_id: str,
    task: str,
    base: str,
    head: str,
) -> dict[str, Any]:
    if not isinstance(request, dict) or frozenset(request) != _MUTATION_JOURNAL_REQUEST_KEYS:
        raise _DeferredMutationRequestError("malformed deferred mutation request")
    for field in (
        "schema",
        "repository",
        "run_id",
        "task",
        "base",
        "head",
        "criterion",
        "method",
        "check",
        "result",
        "truncated_observation",
        "idempotency_key",
    ):
        if not isinstance(request.get(field), str):
            raise _DeferredMutationRequestError("malformed deferred mutation request")
    evidence = request.get("evidence")
    if not isinstance(evidence, list) or not all(
        isinstance(item, str) for item in evidence
    ):
        raise _DeferredMutationRequestError("malformed deferred mutation request")
    expected_identity = {
        "schema": _MUTATION_JOURNAL_SCHEMA,
        "repository": str(repository.resolve()),
        "run_id": run_id,
        "task": task,
        "base": base,
        "head": head,
    }
    if any(request.get(field) != value for field, value in expected_identity.items()):
        raise _DeferredMutationRequestError("deferred mutation request diverged")
    preimage = {field: request[field] for field in _MUTATION_JOURNAL_PREIMAGE_KEYS}
    expected_key = sha256_bytes(chain_core.canonical_bytes(preimage))
    if request.get("idempotency_key") != expected_key:
        raise _DeferredMutationRequestError("deferred mutation request diverged")
    return request


def _persist_deferred_mutation_result(
    result: chain_core.FencedProcessResult,
    *,
    repository: Path,
    run_id: str,
    task: str,
    base: str,
    head: str,
) -> chain_core.FencedProcessResult:
    """Strip trusted sideband and persist it inside the lock-owning parent."""

    public_parts: list[bytes] = []
    requests: list[dict[str, Any]] = []
    diagnostics: list[bytes] = []
    for line in result.output.splitlines(keepends=True):
        if not line.startswith(_MUTATION_JOURNAL_SIDEBAND_PREFIX):
            public_parts.append(line)
            continue
        try:
            if not line.endswith(b"\n"):
                raise _DeferredMutationRequestError(
                    "malformed deferred mutation request"
                )
            payload = line[len(_MUTATION_JOURNAL_SIDEBAND_PREFIX) : -1]
            request = json.loads(payload.decode("utf-8"))
            if chain_core.canonical_bytes(request) != payload:
                raise _DeferredMutationRequestError(
                    "malformed deferred mutation request"
                )
            requests.append(
                _validate_deferred_mutation_request(
                    request,
                    repository=repository,
                    run_id=run_id,
                    task=task,
                    base=base,
                    head=head,
                )
            )
        except (UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
            if not isinstance(error, _DeferredMutationRequestError):
                error = _DeferredMutationRequestError(
                    "malformed deferred mutation request"
                )
            diagnostics.append(_mutation_persistence_error(error))

    if requests:
        try:
            _batch, builders, _journal = runtime._coordination_modules()
        except Exception as error:
            diagnostics.extend(_mutation_persistence_error(error) for _ in requests)
        else:
            for request in requests:
                try:
                    builders.verification_add(
                        repository,
                        run_id,
                        idempotency_key=str(request["idempotency_key"]),
                        task=str(request["task"]),
                        criterion=str(request["criterion"]),
                        method=str(request["method"]),
                        check=str(request["check"]),
                        result=str(request["result"]),
                        observation=str(request["truncated_observation"]),
                        evidence=list(request["evidence"]),
                        binding_chain=None,
                        binding_id=None,
                    )
                except Exception as error:
                    diagnostics.append(_mutation_persistence_error(error))

    output = _bounded_mutation_output(public_parts, diagnostics)
    return dataclasses.replace(
        result,
        output=output,
        output_digest=sha256_bytes(output),
    )
