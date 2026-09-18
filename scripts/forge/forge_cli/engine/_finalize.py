"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
import dataclasses
from typing import TYPE_CHECKING, Any, MutableMapping, Callable, Mapping

if TYPE_CHECKING:
    from forge_cli.engine._engine import Engine
from forge_cli.engine._approval import _authorization_problem as _authorization_problem
from forge_cli.engine._core import _archive_metadata as _archive_metadata, _write_artifact as _write_artifact, _run_halt as _run_halt, _fresh_eval_invalid_refusal as _fresh_eval_invalid_refusal
from forge_cli.engine._fresh_eval import _validated_fresh_reviewer_manifest as _validated_fresh_reviewer_manifest
from forge_cli.engine._gate_checks import _mechanical_complete as _mechanical_complete, _next_incomplete as _next_incomplete
from forge_cli.engine._state import PRODUCED_COMMIT_MISMATCH as PRODUCED_COMMIT_MISMATCH
from forge_cli.policy import Policy, sha256_bytes
from forge_cli import candidate as candidate_module, chain_core, runtime, fresh_evals as fresh_eval_module
import copy
from forge_cli.envelope import FrozenError, OUTPUT_SCHEMA, Outcome, REVISION9_OUTPUT_SCHEMA, ReasonCode, Refusal
import os
import re


@dataclasses.dataclass
class FinalizeContext:
    engine: Engine
    state: MutableMapping[str, Any]
    policy: Policy
    message: str
    lock_acquired: bool = False
    lock_session_pid: str = ""
    produced_sha: str | None = None
    produced_identity: dict[str, Any] | None = None


@dataclasses.dataclass(frozen=True)
class ProducedCommitContext:
    pre_head: str
    expected_tree_oid: str
    expected_message_digest: str
    produced_sha: str
    commit: candidate_module.CommitObject


def _produced_head_moved(context: ProducedCommitContext) -> bool:
    return context.produced_sha != context.pre_head


def _produced_single_parent(context: ProducedCommitContext) -> bool:
    return context.commit.parent_headers == (context.pre_head,)


def _produced_exact_tree(context: ProducedCommitContext) -> bool:
    return context.commit.tree_headers == (context.expected_tree_oid,)


def _produced_exact_message(context: ProducedCommitContext) -> bool:
    return sha256_bytes(context.commit.message) == context.expected_message_digest


PRODUCED_COMMIT_CHECKS: dict[str, Callable[[ProducedCommitContext], bool]] = {
    "head-movement": _produced_head_moved,
    "exact-single-parent": _produced_single_parent,
    "exact-tree": _produced_exact_tree,
    "exact-message": _produced_exact_message,
}


def _finalize_produced_identity(context: FinalizeContext) -> bool:
    """Inspect one produced commit through bounded plumbing and all four seams."""

    state = context.state
    intent = state.get("commit_result", {}).get("intent")
    produced_sha = context.produced_sha
    if not isinstance(intent, Mapping) or not isinstance(produced_sha, str):
        context.produced_identity = {
            "result": "failed",
            "produced_sha": str(produced_sha or ""),
            "expected": {},
            "observed": {"error": "produced commit intent is incomplete"},
            "checks": {name: False for name in PRODUCED_COMMIT_CHECKS},
        }
        return False
    expected = {
        "parent": str(intent.get("pre_head") or ""),
        "tree": str(intent.get("expected_tree_oid") or ""),
        "message_digest": str(intent.get("message_digest") or ""),
    }
    try:
        commit = context.engine.ctx.repo.read_commit_object(produced_sha)
        produced_context = ProducedCommitContext(
            pre_head=expected["parent"],
            expected_tree_oid=expected["tree"],
            expected_message_digest=expected["message_digest"],
            produced_sha=produced_sha,
            commit=commit,
        )
        checks = {
            name: bool(predicate(produced_context))
            for name, predicate in PRODUCED_COMMIT_CHECKS.items()
        }
        observed = {
            "parent": list(commit.parent_headers[:2]),
            "parent_count": len(commit.parent_headers),
            "tree": list(commit.tree_headers[:2]),
            "tree_count": len(commit.tree_headers),
            "message_digest": sha256_bytes(commit.message),
        }
        raw = commit.raw
    except (candidate_module.CandidateError, OSError, ValueError) as exc:
        checks = {name: False for name in PRODUCED_COMMIT_CHECKS}
        observed = {"error": str(exc), "parent": [], "tree": [], "message_digest": ""}
        raw = chain_core.canonical_bytes({"error": str(exc), "produced_sha": produced_sha})
    result = "passed" if all(checks.values()) else "failed"
    transcript_ref = _write_artifact(
        context.engine.ctx,
        state,
        f"commit/identity-{produced_sha}.txt",
        raw,
        exclusive=False,
    )
    context.produced_identity = {
        "result": result,
        "produced_sha": produced_sha,
        "expected": expected,
        "observed": observed,
        "checks": checks,
        "transcript": transcript_ref,
    }
    return result == "passed"


def _record_produced_identity(
    context: FinalizeContext,
) -> dict[str, Any]:
    state = context.state
    existing = state.get("commit_result", {}).get("identity")
    if isinstance(existing, dict):
        return existing
    result = context.produced_identity
    if not isinstance(result, dict):
        raise FrozenError(
            "produced commit identity result is unavailable",
            chain_id=str(state["chain_id"]),
            state="committing",
        )
    state["commit_result"]["identity"] = copy.deepcopy(result)
    if result.get("result") == "failed":
        state["commit_result"]["mismatch_latched"] = True
    context.engine.ctx.store.persist(
        state,
        "commit_identity_checked",
        copy.deepcopy(result),
    )
    return result


def _produced_mismatch_outcome(
    state: Mapping[str, Any], result: Mapping[str, Any]
) -> Outcome:
    expected = chain_core.canonical_bytes(result.get("expected", {})).decode("utf-8")
    observed = chain_core.canonical_bytes(result.get("observed", {})).decode("utf-8")
    transcript = result.get("transcript")
    revision9 = state.get("run_binding") is not None or _archive_metadata(state) is not None
    return Outcome(
        ok=False,
        reason_code=ReasonCode.FROZEN_CHAIN,
        message=PRODUCED_COMMIT_MISMATCH,
        chain_id=str(state["chain_id"]),
        state="committing",
        expected=expected,
        observed=observed,
        remediation=chain_core._forge_command(state, "status"),
        next_required_step=chain_core._forge_command(state, "status"),
        evidence_refs=(str(transcript),) if isinstance(transcript, str) else (),
        schema=REVISION9_OUTPUT_SCHEMA if revision9 else OUTPUT_SCHEMA,
    )


def _finalize_halt(context: FinalizeContext) -> bool:
    _run_halt(context.engine.ctx, context.state)
    return True


def _finalize_lock(context: FinalizeContext) -> bool:
    session_pid = os.environ.get("FORGE_SESSION_PID") or str(os.getpid())
    if not re.fullmatch(r"[1-9][0-9]*", session_pid):
        session_pid = str(os.getpid())
    environment = os.environ.copy()
    environment["FORGE_SESSION_PID"] = session_pid
    try:
        process = runtime.run_bounded(
            ["bash", str(context.engine.ctx.helper("acquire-commit-lock.sh"))],
            cwd=context.engine.ctx.repo.root,
            env=environment,
            timeout=305.0,
            verbose=context.engine.ctx.options.verbose,
        )
    except OSError as exc:
        raise Refusal(
            ReasonCode.LOCK_UNAVAILABLE,
            f"commit lock could not be launched: {exc}",
            expected="acquire-commit-lock.sh exit 0",
            observed=str(exc),
            remediation=chain_core._forge_command(context.state, "commit finalize --message <message>"),
            chain=context.state,
        ) from exc
    if process.returncode != 0 or process.timed_out or process.output_limit:
        raise Refusal(
            ReasonCode.LOCK_UNAVAILABLE,
            "commit lock acquisition failed or timed out",
            expected="acquire-commit-lock.sh exit 0",
            observed=process.output.decode("utf-8", "replace").strip() or f"exit {process.returncode}",
            remediation=chain_core._forge_command(context.state, "commit finalize --message <message>"),
            chain=context.state,
        )
    context.lock_acquired = True
    context.lock_session_pid = session_pid
    return True


def _finalize_candidate(context: FinalizeContext) -> bool:
    current_head = context.engine.ctx.repo.head()
    if current_head != context.state["repo_head"]:
        context.engine._record_head_moved(context.state, current_head)
        raise Refusal(
            ReasonCode.HEAD_MOVED,
            (
                "out-of-band commit, not chain corruption: "
                f"{context.state['repo_head']} -> {current_head}"
            ),
            expected=str(context.state["repo_head"]),
            observed=current_head,
            remediation=chain_core._forge_command(context.state, "commit rebase"),
            chain=context.state,
        )
    record = context.state["candidate"]
    if not chain_core.candidate_is_v2(context.state):
        raise Refusal(
            ReasonCode.STATE_PRECONDITION,
            "legacy candidate must be restaged before finalize",
            expected=candidate_module.CANDIDATE_SCHEMA,
            observed=str(record.get("schema")),
            remediation=chain_core._forge_command(
                context.state, "commit restage --paths <path>..."
            ),
            chain=context.state,
        )
    expected = str(record.get("sha256"))
    try:
        observation = context.engine.ctx.repo.candidate_observation()
    except candidate_module.CandidateError as exc:
        raise Refusal(
            ReasonCode.EVIDENCE_INCOMPLETE,
            "finalize candidate byte-identity check failed",
            expected=expected,
            observed=str(exc),
            remediation=chain_core._forge_command(
                context.state, "commit restage --paths <path>..."
            ),
            chain=context.state,
        ) from exc
    observed = observation.authorization_id
    if (
        observed != expected
        or observation.object_format != record.get("object_format")
        or observation.tree_oid != record.get("tree_oid")
    ):
        raise Refusal(
            ReasonCode.CANDIDATE_STALE,
            "finalize candidate byte-identity check failed",
            expected=expected,
            observed=observed,
            remediation=chain_core._forge_command(context.state, "commit restage --paths <path>..."),
            chain=context.state,
        )
    return True


def _finalize_evidence(context: FinalizeContext) -> bool:
    state = context.state
    if not chain_core._latest_current_pass(state, "classification"):
        raise Refusal(
            ReasonCode.EVIDENCE_INCOMPLETE,
            "finalize requires current-candidate classification evidence",
            expected=f"classification PASS naming {state['candidate'].get('sha256')}",
            observed=str(state["steps"].get("classification")),
            remediation=chain_core._forge_command(state, "classify"),
            chain=state,
        )
    fast_skips = runtime._fast_mechanical_skips(state)
    if fast_skips:
        raise Refusal(
            ReasonCode.EVIDENCE_INCOMPLETE,
            "fast tier cannot rely on an operator skip for a mechanical control",
            expected="all fast-tier mechanical rows PASS without skips",
            observed=", ".join(fast_skips),
            remediation=chain_core._forge_command(state, "commit restage --paths <path>..."),
            chain=state,
        )
    if state["tier"].get("effective") == "fast" and not chain_core._latest_current_pass(
        state, "fast-eligibility"
    ):
        raise Refusal(
            ReasonCode.EVIDENCE_INCOMPLETE,
            "fast finalize requires authorization-time eligibility evidence",
            expected="current-candidate fast-eligibility PASS",
            observed=str(state["steps"].get("fast-eligibility")),
            remediation=chain_core._forge_command(state, "verify"),
            chain=state,
        )
    if not _mechanical_complete(context.engine.ctx, state):
        missing = _next_incomplete(context.engine.ctx, state)
        raise Refusal(
            ReasonCode.EVIDENCE_INCOMPLETE,
            f"finalize evidence is incomplete at required step: {missing}",
            expected="every required mechanical step current-candidate PASS or operator skip",
            observed=str(missing),
            remediation=chain_core._forge_command(state, "verify"),
            chain=state,
        )
    effective = state["tier"].get("effective")
    if effective != "fast":
        review = state["review"].get("verdict")
        skipped_review = chain_core._user_skip(state, "review") is not None
        if not (
            isinstance(review, dict)
            and review.get("verdict") == "PASS"
            and review.get("candidate") == state["candidate"].get("sha256")
        ) and not skipped_review:
            raise Refusal(
                ReasonCode.EVIDENCE_INCOMPLETE,
                "required reviewer PASS is absent or bound to a stale candidate",
                expected=f"PASS naming {state['candidate'].get('sha256')}",
                observed=str(review),
                remediation=chain_core._forge_command(state, "review request"),
                chain=state,
            )
    if state["tier"].get("control") or state["review"].get(
        "operator_cosign_required"
    ):
        approval = state.get("approval", {})
        if approval.get("candidate") != state["candidate"].get("sha256") or not approval.get(
            "approved_at"
        ) or not isinstance(approval.get("qualification"), dict) or not chain_core._latest_current_pass(
            state, "approval-qualification"
        ):
            raise Refusal(
                ReasonCode.APPROVAL_REQUIRED,
                "finalize requires qualified operator approval naming the current candidate",
                expected=str(state["candidate"].get("sha256")),
                observed=str(approval.get("candidate")),
                remediation=chain_core._forge_command(
                    state,
                    f"commit approve --candidate {state['candidate'].get('sha256')}",
                ),
                chain=state,
            )
    return True


def _finalize_fresh_reviewer_evals(context: FinalizeContext) -> bool:
    """Re-prove triggered fresh evidence, including a live index observation."""

    if (
        chain_core._user_skip(
            context.state, chain_core.FRESH_REVIEWER_EVALS_GATE
        )
        is not None
    ):
        return True
    if not chain_core._fresh_reviewer_evals_required(
        context.engine.ctx, context.state
    ):
        return True
    try:
        _validated_fresh_reviewer_manifest(
            context.engine.ctx, context.state, reobserve_index=True
        )
    except fresh_eval_module.FreshEvalError as exc:
        raise _fresh_eval_invalid_refusal(context.state, str(exc)) from exc
    except Refusal as exc:
        raise _fresh_eval_invalid_refusal(
            context.state, exc.message, evidence_refs=exc.evidence_refs
        ) from exc
    return True


def _finalize_ttl(context: FinalizeContext) -> bool:
    problem = _authorization_problem(context.state)
    if problem is not None:
        raise problem
    return True


def _finalize_tree_drift(context: FinalizeContext) -> bool:
    paths = list(context.state.get("paths", []))
    drift = context.engine.ctx.repo.tree_index_drift(paths)
    if drift and chain_core._user_skip(context.state, "index-drift") is None:
        raise Refusal(
            ReasonCode.DRIFT_TREE_INDEX,
            f"working tree differs from staged candidate at finalize: {', '.join(drift)}",
            expected="tree bytes equal staged bytes or operator index-drift skip",
            observed=", ".join(drift),
            remediation=chain_core._forge_command(context.state, "commit restage --paths <path>..."),
            chain=context.state,
        )
    return True


FINALIZE_CHECKS: dict[str, Callable[[FinalizeContext], bool | None]] = {
    "evidence-completeness": _finalize_evidence,
    "fresh-reviewer-evals": _finalize_fresh_reviewer_evals,
    "candidate-byte-identity": _finalize_candidate,
    "produced-commit-identity": _finalize_produced_identity,
    "ttl-token": _finalize_ttl,
    "tree-index-drift": _finalize_tree_drift,
    "halt": _finalize_halt,
    "lock": _finalize_lock,
}
