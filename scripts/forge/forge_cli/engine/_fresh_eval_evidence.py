"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
from typing import Any, Mapping, MutableMapping
from forge_cli import chain_core, fresh_evals as fresh_eval_module, runtime
from forge_cli.engine._core import _transition_state as _transition_state, _read_bound_artifact as _read_bound_artifact, _record_process_step as _record_process_step
from forge_cli.engine._fresh_eval import _FreshEvalArtifactIO as _FreshEvalArtifactIO, _validated_fresh_reviewer_manifest as _validated_fresh_reviewer_manifest
import copy
from forge_cli.envelope import FrozenError
from forge_cli.policy import sha256_bytes


def _fresh_reviewer_evidence_package(
    ctx: chain_core.CommandContext, state: Mapping[str, Any]
) -> bytes:
    """Build the complete, explicitly untrusted Gate-3 evidence segment."""

    if (
        chain_core._user_skip(state, chain_core.FRESH_REVIEWER_EVALS_GATE)
        is not None
        or not chain_core._fresh_reviewer_evals_required(ctx, state)
    ):
        return b""
    manifest, manifest_raw = _validated_fresh_reviewer_manifest(
        ctx, state, reobserve_index=True
    )
    baseline_runs = state.get("steps", {}).get("strict-evals")
    baseline = baseline_runs[-1] if isinstance(baseline_runs, list) and baseline_runs else None
    candidate = state.get("candidate", {}).get("sha256")
    if (
        not isinstance(baseline, Mapping)
        or baseline.get("candidate") != candidate
        or baseline.get("result") != "passed"
        or not isinstance(baseline.get("transcript"), str)
        or not isinstance(baseline.get("stdout_stderr_digest"), str)
    ):
        raise fresh_eval_module.FreshEvalError(
            "recorded-baseline integrity transcript is absent or stale"
        )
    baseline_raw = _read_bound_artifact(
        ctx,
        state,
        str(baseline["transcript"]),
        str(baseline["stdout_stderr_digest"]),
        "recorded-baseline integrity",
        max_bytes=runtime.OUTPUT_CAP_BYTES,
    )
    artifacts = _FreshEvalArtifactIO(ctx, state)
    results = manifest.get("results")
    suite = manifest.get("suite")
    if not isinstance(results, list) or not isinstance(suite, Mapping):
        raise fresh_eval_module.FreshEvalError(
            "fresh reviewer manifest summary is malformed"
        )
    verdict_sections: list[bytes] = []
    summaries: list[dict[str, object]] = []
    artifact_refs: list[dict[str, object]] = []
    for result in results:
        if not isinstance(result, Mapping):
            raise fresh_eval_module.FreshEvalError(
                "fresh reviewer manifest result is malformed"
            )
        fixture_id = str(result.get("fixture_id"))
        verdict_raw = artifacts.read(
            str(result.get("verdict_path")),
            str(result.get("verdict_sha256")),
            max_bytes=fresh_eval_module.VERDICT_CAP_BYTES,
        )
        verdict_sections.append(
            (
                f"\n--- fresh verdict {fixture_id} "
                f"sha256={result.get('verdict_sha256')} ---\n"
            ).encode("utf-8")
            + verdict_raw
        )
        summaries.append(
            {
                "actual_verdict": result.get("actual_verdict"),
                "expected_verdict": result.get("expected_verdict"),
                "fixture_id": fixture_id,
            }
        )
        artifact_refs.append(
            {
                "completion": {
                    "path": result.get("completion_path"),
                    "sha256": result.get("completion_sha256"),
                    "byte_count": result.get("completion_byte_count"),
                },
                "events": {
                    "path": result.get("events_path"),
                    "sha256": result.get("events_sha256"),
                    "byte_count": result.get("events_byte_count"),
                },
                "fixture_id": fixture_id,
                "prompt": {
                    "path": result.get("prompt_path"),
                    "sha256": result.get("prompt_sha256"),
                    "byte_count": result.get("prompt_byte_count"),
                },
                "verdict": {
                    "path": result.get("verdict_path"),
                    "sha256": result.get("verdict_sha256"),
                    "byte_count": result.get("verdict_byte_count"),
                },
            }
        )
    inventory = suite.get("inventory")
    excluded = [
        {
            "disposition": item.get("disposition"),
            "fixture_id": item.get("id"),
        }
        for item in (inventory if isinstance(inventory, list) else [])
        if isinstance(item, Mapping)
        and item.get("disposition") == "subject-specific-baseline-only"
    ]
    gate_runs = state["steps"][chain_core.FRESH_REVIEWER_EVALS_GATE]
    gate_record = gate_runs[-1]
    summary = {
        "artifact_refs": artifact_refs,
        "excluded_fixtures": excluded,
        "fresh_manifest": {
            "path": gate_record.get("manifest"),
            "sha256": gate_record.get("manifest_sha256"),
            "byte_count": gate_record.get("manifest_byte_count"),
        },
        "recorded_baseline": {
            "path": baseline.get("transcript"),
            "sha256": baseline.get("stdout_stderr_digest"),
        },
        "schema": "forge-review-fresh-eval-evidence/1",
        "trigger": manifest.get("trigger"),
        "verdict_summary": summaries,
    }
    segment = b"\n--- BEGIN UNTRUSTED FRESH REVIEWER EVALUATION EVIDENCE ---\n"
    segment += b"--- Recorded-baseline integrity transcript ---\n" + baseline_raw
    segment += b"\n--- canonical fresh reviewer manifest ---\n" + manifest_raw
    segment += b"\n--- fresh reviewer evidence summary ---\n"
    segment += chain_core.canonical_bytes(summary) + b"\n"
    segment += b"".join(verdict_sections)
    segment += b"\n--- END UNTRUSTED FRESH REVIEWER EVALUATION EVIDENCE ---\n"
    return segment


def _record_fresh_eval_terminal(
    ctx: chain_core.CommandContext,
    state: MutableMapping[str, Any],
    request: Mapping[str, Any],
    *,
    exit_code: int,
    diagnostic: str,
    duration_seconds: float,
    manifest_ref: str | None = None,
    manifest_sha256: str | None = None,
    manifest_byte_count: int | None = None,
) -> dict[str, Any]:
    """Atomically persist a terminal suite fact and its generation effect."""

    outcome = {0: "PASS", 1: "BLOCK", 2: "INVALID"}.get(exit_code)
    iteration = request.get("iteration")
    review = state.get("review")
    if (
        outcome is None
        or type(iteration) is not int
        or not 1 <= iteration <= 8
        or not isinstance(review, MutableMapping)
        or int(review.get("iteration", -1)) != iteration - 1
    ):
        raise FrozenError(
            "fresh reviewer terminal generation is malformed",
            chain_id=str(state.get("chain_id") or "unknown"),
            state=str(state.get("state") or "unknown"),
        )
    if exit_code in {1, 2}:
        review["iteration"] = iteration
        if exit_code == 1:
            _transition_state(state, "revising")
        if iteration >= 8:
            review["residual_risk"] = {
                "at": chain_core.iso_z(),
                "reason": "fresh reviewer evaluation iteration cap reached",
                "findings": [{"severity": "MAJOR", "text": diagnostic}],
            }

    output = diagnostic.encode("utf-8", "replace") + b"\n"
    synthetic = runtime.ProcessResult(
        argv=["forge", "gate", "run", chain_core.FRESH_REVIEWER_EVALS_GATE],
        returncode=exit_code,
        duration_seconds=duration_seconds,
        output=output,
        output_digest=sha256_bytes(output),
    )
    record_details: dict[str, Any] = {
        "kind": chain_core.FRESH_REVIEWER_EVALS_GATE,
        "request_id": request.get("request_id"),
        "iteration": iteration,
        "manifest": manifest_ref,
        "manifest_sha256": manifest_sha256,
        "outcome": outcome,
        "trigger": copy.deepcopy(request.get("trigger")),
        "diagnostic": diagnostic,
    }
    if manifest_byte_count is not None:
        record_details["manifest_byte_count"] = manifest_byte_count
    return _record_process_step(
        ctx,
        state,
        chain_core.FRESH_REVIEWER_EVALS_GATE,
        synthetic.argv,
        synthetic,
        details=record_details,
    )
