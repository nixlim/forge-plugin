"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
import dataclasses
import os
import secrets
import stat
from pathlib import Path
from typing import Any, Mapping
from forge_cli import chain_core, fresh_evals as fresh_eval_module
from forge_cli.engine._core import _write_artifact as _write_artifact, _read_bound_artifact as _read_bound_artifact, _run_halt as _run_halt
from forge_cli.engine._state import FRESH_REVIEWER_EVAL_REQUEST_SCHEMA as FRESH_REVIEWER_EVAL_REQUEST_SCHEMA, _FRESH_REVIEWER_REQUEST_CANDIDATE_KEYS as _FRESH_REVIEWER_REQUEST_CANDIDATE_KEYS
from forge_cli.envelope import FrozenError, Refusal
import copy


@dataclasses.dataclass(frozen=True)
class _FreshEvalArtifactIO:
    """Adapt owner-controlled chain artifacts to the fresh evaluator protocol."""

    ctx: chain_core.CommandContext
    state: Mapping[str, Any]

    def write(self, relative: str, data: bytes, *, exclusive: bool) -> str:
        if relative.endswith(("/completion.json", "/manifest.json")):
            return self._write_atomic(relative, data, exclusive=exclusive)
        return _write_artifact(
            self.ctx, self.state, relative, data, exclusive=exclusive
        )

    def _write_atomic(self, relative: str, data: bytes, *, exclusive: bool) -> str:
        """Publish a complete document with one atomic same-directory link/rename."""

        chain_id = str(self.state["chain_id"])
        temporary_name = f".fresh-{secrets.token_hex(16)}.tmp"
        descriptor = -1
        with self.ctx.store.artifact_parent_descriptor(
            chain_id, relative, create=True
        ) as (parent, name):
            try:
                descriptor = os.open(
                    temporary_name,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_CLOEXEC", 0)
                    | getattr(os, "O_NONBLOCK", 0),
                    0o600,
                    dir_fd=parent,
                )
                opened = os.fstat(descriptor)
                if not stat.S_ISREG(opened.st_mode) or opened.st_uid != os.geteuid():
                    raise OSError(
                        "temporary artifact is not an owner-controlled regular file"
                    )
                os.fchmod(descriptor, 0o600)
                offset = 0
                while offset < len(data):
                    written = os.write(descriptor, data[offset:])
                    if written <= 0:
                        raise OSError("short atomic artifact write")
                    offset += written
                os.fsync(descriptor)
                os.close(descriptor)
                descriptor = -1
                if exclusive:
                    # linkat is the stdlib no-replace publication primitive:
                    # EEXIST cannot overwrite an earlier request artifact.
                    os.link(
                        temporary_name,
                        name,
                        src_dir_fd=parent,
                        dst_dir_fd=parent,
                        follow_symlinks=False,
                    )
                    os.unlink(temporary_name, dir_fd=parent)
                else:
                    os.replace(
                        temporary_name,
                        name,
                        src_dir_fd=parent,
                        dst_dir_fd=parent,
                    )
                os.fsync(parent)
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
                try:
                    os.unlink(temporary_name, dir_fd=parent)
                except FileNotFoundError:
                    pass
        return (
            Path(".forge") / "chains" / chain_id / relative
        ).as_posix()

    def read(
        self, reference: str, expected_digest: str | None, *, max_bytes: int
    ) -> bytes:
        return _read_bound_artifact(
            self.ctx,
            self.state,
            reference,
            expected_digest,
            "fresh reviewer evaluation",
            max_bytes=max_bytes,
        )

    def absolute(self, reference: str) -> Path:
        prefix = Path(".forge") / "chains" / str(self.state["chain_id"])
        try:
            inner = Path(reference).relative_to(prefix)
        except (TypeError, ValueError) as exc:
            raise fresh_eval_module.FreshEvalError(
                "artifact path escapes the owning chain"
            ) from exc
        if not inner.parts or any(part in {"", ".", ".."} for part in inner.parts):
            raise fresh_eval_module.FreshEvalError(
                "artifact path escapes the owning chain"
            )
        return self.ctx.store.common_root / prefix / inner


class _FreshEvalControlAbort(BaseException):
    """Carry an outer halt/frozen refusal through collector fail-closed catches."""

    def __init__(self, problem: Refusal | FrozenError) -> None:
        self.problem = problem
        super().__init__(str(problem))


def _fresh_eval_requests(state: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    steps = state.get("steps")
    requests = (
        steps.get(chain_core.FRESH_REVIEWER_EVALS_REQUESTS)
        if isinstance(steps, Mapping)
        else None
    )
    if not isinstance(requests, list) or any(
        not isinstance(item, Mapping) for item in requests
    ):
        raise fresh_eval_module.FreshEvalError(
            "durable fresh evaluation request history is missing or malformed"
        )
    return requests


def _fresh_eval_request_for_step(
    state: Mapping[str, Any], step: Mapping[str, Any]
) -> Mapping[str, Any]:
    request_id = step.get("request_id")
    for request in reversed(_fresh_eval_requests(state)):
        if request.get("request_id") == request_id:
            return request
    raise fresh_eval_module.FreshEvalError(
        "fresh reviewer manifest has no durable request predecessor"
    )


def _fresh_eval_evaluation(
    ctx: chain_core.CommandContext,
    state: Mapping[str, Any],
    request: Mapping[str, Any],
) -> Any:
    expected_keys = {
        "schema",
        "chain_id",
        "request_id",
        "requested_at",
        "iteration",
        "candidate",
        "paths",
        "policy_sha",
        "trigger",
        "suite",
        "fixture_packages",
        "artifact_prefix",
    }
    policy = ctx.policy or chain_core._policy_for_state(ctx, state)
    candidate = state.get("candidate")
    try:
        candidate_binding = (
            fresh_eval_module.candidate_binding(candidate)
            if isinstance(candidate, Mapping)
            else None
        )
        computed_at = (
            chain_core.parse_time(str(candidate.get("computed_at")))
            if isinstance(candidate, Mapping)
            else None
        )
    except (TypeError, ValueError, fresh_eval_module.FreshEvalError):
        candidate_binding = None
        computed_at = None
    paths = state.get("paths")
    if (
        set(request) != expected_keys
        or request.get("schema") != FRESH_REVIEWER_EVAL_REQUEST_SCHEMA
        or request.get("chain_id") != state.get("chain_id")
        or not isinstance(candidate, Mapping)
        or set(candidate) != _FRESH_REVIEWER_REQUEST_CANDIDATE_KEYS
        or candidate_binding is None
        or computed_at is None
        or candidate.get("sha256") != candidate.get("authorization_id")
        or request.get("candidate") != candidate
        or request.get("paths") != paths
        or request.get("policy_sha") != policy.sha
        or not isinstance(request.get("request_id"), str)
        or not isinstance(request.get("requested_at"), str)
        or type(request.get("iteration")) is not int
        or not isinstance(request.get("suite"), Mapping)
        or not isinstance(request.get("fixture_packages"), list)
        or not isinstance(request.get("artifact_prefix"), str)
        or not isinstance(paths, list)
    ):
        raise fresh_eval_module.FreshEvalError(
            "durable fresh evaluation request binding is malformed"
        )
    expected_prefix = (
        "fresh-reviewer-evals/"
        f"iteration-{int(request['iteration']):02d}/{request['request_id']}"
    )
    if request.get("artifact_prefix") != expected_prefix:
        raise fresh_eval_module.FreshEvalError(
            "durable fresh evaluation artifact prefix is malformed"
        )
    trigger = fresh_eval_module.derive_trigger(
        ctx.repo.candidate_context(), policy, candidate, tuple(paths)
    )
    if request.get("trigger") != trigger or not fresh_eval_module.trigger_required(
        trigger
    ):
        raise fresh_eval_module.FreshEvalError(
            "durable fresh evaluation trigger binding is stale or malformed"
        )
    suite, fixture_packages = fresh_eval_module.prepare_request_plan(
        ctx.repo.candidate_context(), candidate_binding, str(request["request_id"])
    )
    if (
        request.get("suite") != suite
        or request.get("fixture_packages") != fixture_packages
    ):
        raise fresh_eval_module.FreshEvalError(
            "durable fresh evaluation suite/package plan is stale or malformed"
        )

    request_copy = copy.deepcopy(dict(request))

    def persisted() -> bool:
        try:
            loaded = ctx.store.load(str(state["chain_id"]))
            durable = _fresh_eval_requests(loaded)
        except (FrozenError, Refusal, fresh_eval_module.FreshEvalError):
            return False
        return bool(durable and durable[-1] == request_copy)

    def halt() -> None:
        try:
            _run_halt(ctx, state)
        except (Refusal, FrozenError) as exc:
            # ``collect`` deliberately converts ordinary evaluator Exceptions
            # to INVALID.  A global halt/frozen chain is outer control flow,
            # so carry it through without publishing a fresh step.
            raise _FreshEvalControlAbort(exc) from exc

    return fresh_eval_module.EvaluationRequest(
        chain_id=str(state["chain_id"]),
        request_id=str(request["request_id"]),
        requested_at=str(request["requested_at"]),
        iteration=int(request["iteration"]),
        candidate=candidate_binding,
        paths=tuple(paths),
        policy=policy,
        source_context=ctx.repo.candidate_context(),
        artifact_prefix=str(request["artifact_prefix"]),
        suite=request["suite"],
        fixture_packages=tuple(request["fixture_packages"]),
        request_is_persisted=persisted,
        halt_checker=halt,
        final_index_observation=ctx.repo.candidate_observation,
    )


def _validated_fresh_reviewer_manifest(
    ctx: chain_core.CommandContext,
    state: Mapping[str, Any],
    *,
    reobserve_index: bool,
) -> tuple[Mapping[str, object], bytes]:
    candidate = str(state.get("candidate", {}).get("sha256") or "")
    if not fresh_eval_module.current_step_satisfied(
        state, expected_candidate=candidate
    ):
        raise fresh_eval_module.FreshEvalError(
            "current-candidate fresh reviewer PASS record is missing or malformed"
        )
    runs = state["steps"][chain_core.FRESH_REVIEWER_EVALS_GATE]
    step = runs[-1]
    request = _fresh_eval_request_for_step(state, step)
    evaluation = _fresh_eval_evaluation(ctx, state, request)
    artifacts = _FreshEvalArtifactIO(ctx, state)
    expected_manifest_ref = (
        Path(".forge")
        / "chains"
        / str(state["chain_id"])
        / str(request["artifact_prefix"])
        / "manifest.json"
    ).as_posix()
    if step.get("manifest") != expected_manifest_ref:
        raise fresh_eval_module.FreshEvalError(
            "fresh reviewer manifest path is stale or foreign"
        )
    raw = artifacts.read(
        str(step["manifest"]),
        str(step["manifest_sha256"]),
        max_bytes=fresh_eval_module.MANIFEST_CAP_BYTES,
    )
    manifest_byte_count = step.get("manifest_byte_count")
    if (
        type(manifest_byte_count) is not int
        or not 1 <= manifest_byte_count <= fresh_eval_module.MANIFEST_CAP_BYTES
        or len(raw) != manifest_byte_count
    ):
        raise fresh_eval_module.FreshEvalError(
            "fresh reviewer manifest byte count is missing or changed"
        )
    manifest = fresh_eval_module.validate_manifest(
        raw,
        evaluation,
        artifacts,
        reobserve_index=reobserve_index,
    )
    if manifest.get("outcome") != "PASS":
        raise fresh_eval_module.FreshEvalError(
            "current fresh reviewer manifest is not a PASS"
        )
    return manifest, raw
