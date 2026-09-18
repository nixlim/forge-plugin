"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
from forge_cli.engine._state import STATE_TRANSITIONS as STATE_TRANSITIONS, _REQUIRED_MERGE_LIFECYCLE_CONTROLS as _REQUIRED_MERGE_LIFECYCLE_CONTROLS, MERGE_LIFECYCLE_CONTROLS as MERGE_LIFECYCLE_CONTROLS, ARCHIVE_CONTAMINATION as ARCHIVE_CONTAMINATION
import datetime as dt
import secrets
from forge_cli import runtime, chain_core
from typing import Any, MutableMapping, Mapping, Sequence, Iterable
from forge_cli.envelope import FrozenError, REVISION9_OUTPUT_SCHEMA, Refusal, V2ReasonCode, ReasonCode
import os
from pathlib import Path
import sys
from forge_cli.policy import sha256_bytes, Policy
import stat
import re
import dataclasses


def commit_message_bytes(message: str) -> bytes:
    """Bytes Git stores for one verbatim ``-m`` argument."""
    encoded = message.encode("utf-8")
    return encoded if encoded.endswith(b"\n") else encoded + b"\n"


def chain_id_now() -> str:
    stamp = runtime.utc_now().astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    return f"c-{stamp}-{secrets.token_hex(2)}"


def promoted_tier(*tiers: str | None) -> str:
    present = [tier for tier in tiers if tier in chain_core.TIER_RANK]
    return max(present, key=chain_core.TIER_RANK.__getitem__) if present else "standard"


def _transition_state(state: MutableMapping[str, Any], target: str) -> None:
    """Apply one transition through the closed FR-211 state table."""
    current = str(state.get("state"))
    if current == target:
        return
    if current not in STATE_TRANSITIONS or target not in STATE_TRANSITIONS[current]:
        raise FrozenError(
            f"internal state transition is not admitted: {current} -> {target}",
            chain_id=str(state.get("chain_id") or "") or None,
            state=current if current in chain_core.STATES else None,
            observed=f"{current} -> {target}",
        )
    state["state"] = target


def _require_merge_lifecycle_control(name: str) -> None:
    if (
        name not in _REQUIRED_MERGE_LIFECYCLE_CONTROLS
        or name not in MERGE_LIFECYCLE_CONTROLS
    ):
        raise FrozenError(
            f"merge lifecycle control is unavailable: {name}",
            schema=REVISION9_OUTPUT_SCHEMA,
        )


def inspect_common_lock(common_dir: Path) -> chain_core.CommonLockInspection:
    """Return the strict FR-235 portable topology without changing it."""

    chain_core._require_common_lock_control("three-topology-recovery")
    canonical, descriptor = chain_core._open_owned_directory(common_dir)
    try:
        return chain_core._inspect_common_lock_fd(descriptor, canonical)
    finally:
        os.close(descriptor)


def _commit_start_binding_refusal(exc: BaseException) -> Refusal:
    return Refusal(
        V2ReasonCode.RUN_TASK_BINDING_INVALID,
        "forge: commit start refused — run/task binding is invalid",
        expected="matching repository, active task, admitted paths, and committed policy",
        observed=str(exc),
        remediation="inspect the named run/task and retry the exact paired start",
    )


def _archive_refusal(message: str, *, chain: Mapping[str, Any] | None = None) -> Refusal:
    if "exceeds 16 MiB" in message or "16,777,216" in message:
        reason = V2ReasonCode.ARCHIVE_SIZE_LIMIT
    elif "legacy" in message.lower() and (
        "approval" in message.lower() or "recovered" in message.lower()
    ):
        reason = V2ReasonCode.LEGACY_RECOVERY_APPROVAL_REQUIRED
    elif "differ" in message.lower() or "mismatch" in message.lower():
        reason = V2ReasonCode.ARCHIVE_RERENDER_MISMATCH
    else:
        reason = V2ReasonCode.BINDING_INVALID
    return Refusal(
        reason,
        message,
        expected="a safe archive-only candidate equal to deterministic rerender",
        observed=message,
        remediation="repair the immutable archive inputs and retry archive commit start",
        chain=chain,
    )


def _archive_contamination_refusal(
    *, chain: Mapping[str, Any] | None = None
) -> Refusal:
    return Refusal(
        ReasonCode.STATE_PRECONDITION,
        ARCHIVE_CONTAMINATION,
        expected="only the deterministic archive candidate in the index",
        observed="unrelated staged, tracked, or untracked close-tree content",
        remediation="restore a clean close tree and restart archive commit",
        chain=chain,
        schema=REVISION9_OUTPUT_SCHEMA,
    )


def _archive_metadata(state: Mapping[str, Any]) -> Mapping[str, Any] | None:
    staging = state.get("staging")
    metadata = staging.get("archive") if isinstance(staging, Mapping) else None
    return metadata if isinstance(metadata, Mapping) else None


def _env_fingerprint(
    ctx: chain_core.CommandContext,
    state: Mapping[str, Any],
    argv: Sequence[str],
) -> tuple[dict[str, str], str]:
    policy = ctx.policy or chain_core._policy_for_state(ctx, state)
    preimage = {
        "command_digest": ctx.command_digest(argv),
        "cwd": os.path.realpath(ctx.repo.root),
        "platform": sys.platform,
        "policy_digest": policy.digest,
        "python_version": (
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        ),
        "repo_head": ctx.repo.head(),
    }
    return preimage, sha256_bytes(chain_core.canonical_bytes(preimage))


def _evidence_record(
    ctx: chain_core.CommandContext,
    state: Mapping[str, Any],
    argv: Sequence[str],
    *,
    result: str,
    exit_code: int,
    duration_seconds: float,
    output_digest: str,
    transcript: str | None,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    preimage, fingerprint = _env_fingerprint(ctx, state, argv)
    record: dict[str, Any] = {
        "candidate": state["candidate"].get("sha256"),
        "recorded_at": chain_core.iso_z(),
        "result": result,
        "exit_code": exit_code,
        "duration_seconds": round(duration_seconds, 6),
        "stdout_stderr_digest": output_digest,
        "transcript": transcript,
        "command_argv": list(argv),
        "command_digest": preimage["command_digest"],
        "env_fingerprint_preimage": preimage,
        "env_fingerprint": fingerprint,
        "repo_head": preimage["repo_head"],
    }
    if details:
        record.update(dict(details))
    return record


def _write_artifact(
    ctx: chain_core.CommandContext,
    state: Mapping[str, Any],
    relative: str,
    data: bytes,
    *,
    exclusive: bool = False,
) -> str:
    chain_id = str(state["chain_id"])
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    flags |= os.O_EXCL if exclusive else os.O_TRUNC
    with ctx.store.artifact_parent_descriptor(
        chain_id, relative, create=True
    ) as (parent, name):
        descriptor = os.open(name, flags, 0o600, dir_fd=parent)
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode) or opened.st_uid != os.geteuid():
                raise OSError("artifact is not an owner-controlled regular file")
            os.fchmod(descriptor, 0o600)
            written = 0
            while written < len(data):
                count = os.write(descriptor, data[written:])
                if count <= 0:
                    raise OSError("short artifact write")
                written += count
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.fsync(parent)
    return (Path(".forge") / "chains" / chain_id / relative).as_posix()


def _read_bound_artifact(
    ctx: chain_core.CommandContext,
    state: Mapping[str, Any],
    relative: str,
    expected_digest: str | None,
    label: str,
    *,
    max_bytes: int | None = None,
) -> bytes:
    """Read a chain artifact without following a replacement symlink."""
    chain_id = str(state["chain_id"])
    prefix = Path(".forge") / "chains" / chain_id
    try:
        inner = Path(relative).relative_to(prefix).as_posix()
    except ValueError as exc:
        raise Refusal(
            ReasonCode.CITATION_OUT_OF_ROOT,
            f"{label} path escapes the chain artifact directory",
            expected=prefix.as_posix(),
            observed=relative,
            remediation=chain_core._forge_command(state, "review request"),
            chain=state,
        ) from exc
    descriptor: int | None = None
    try:
        with ctx.store.artifact_parent_descriptor(
            chain_id, inner, create=False
        ) as (parent, name):
            descriptor = os.open(
                name,
                os.O_RDONLY
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NONBLOCK", 0),
                dir_fd=parent,
            )
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode) or opened.st_uid != os.geteuid():
                raise OSError("artifact is not an owner-controlled regular file")
            chunks: list[bytes] = []
            while True:
                chunk = os.read(descriptor, 65536)
                if not chunk:
                    break
                chunks.append(chunk)
                if max_bytes is not None and sum(len(part) for part in chunks) > max_bytes:
                    raise OSError(f"artifact exceeds {max_bytes} bytes")
            data = b"".join(chunks)
    except OSError as exc:
        raise Refusal(
            ReasonCode.REVIEW_VERDICT_INVALID,
            f"{label} artifact is unavailable: {exc}",
            expected=f"readable artifact with digest {expected_digest}",
            observed=str(exc),
            remediation=chain_core._forge_command(state, "review request"),
            chain=state,
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    observed_digest = sha256_bytes(data)
    if expected_digest is not None and observed_digest != expected_digest:
        raise Refusal(
            ReasonCode.REVIEW_VERDICT_INVALID,
            f"{label} artifact changed after review request",
            expected=expected_digest,
            observed=observed_digest,
            remediation=chain_core._forge_command(state, "review request"),
            chain=state,
            evidence_refs=[relative],
        )
    return data


def _fresh_eval_invalid_refusal(
    state: Mapping[str, Any],
    diagnostic: str,
    *,
    evidence_refs: Iterable[str] = (),
) -> Refusal:
    if not diagnostic.startswith("forge: fresh reviewer eval evidence invalid: "):
        diagnostic = f"forge: fresh reviewer eval evidence invalid: {diagnostic}"
    return Refusal(
        ReasonCode.EVIDENCE_INCOMPLETE,
        diagnostic,
        expected="complete, current-candidate fresh reviewer evidence",
        observed=diagnostic,
        remediation=chain_core._forge_command(
            state, f"gate run {chain_core.FRESH_REVIEWER_EVALS_GATE}"
        ),
        next_required_step=chain_core._forge_command(
            state, f"gate run {chain_core.FRESH_REVIEWER_EVALS_GATE}"
        ),
        chain=state,
        evidence_refs=evidence_refs,
        exit_code_override=2,
    )


def _record_process_step(
    ctx: chain_core.CommandContext,
    state: MutableMapping[str, Any],
    step_id: str,
    argv: Sequence[str],
    process: runtime.ProcessResult,
    *,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "-", step_id)
    runs = state["steps"].get(step_id)
    run_number = len(runs) + 1 if isinstance(runs, list) else 1
    transcript = _write_artifact(
        ctx,
        state,
        f"evidence/{safe_name}-{run_number:02d}.log",
        process.output,
    )
    passed = (
        process.returncode == 0 and not process.timed_out and not process.output_limit
    )
    record = _evidence_record(
        ctx,
        state,
        argv,
        result="passed" if passed else "failed",
        exit_code=process.returncode,
        duration_seconds=process.duration_seconds,
        output_digest=process.output_digest,
        transcript=transcript,
        details={
            **(dict(details) if details else {}),
            "timed_out": process.timed_out,
            "output_limit": process.output_limit,
        },
    )
    if not isinstance(runs, list):
        runs = []
        state["steps"][step_id] = runs
    runs.append(record)
    ctx.store.persist(
        state,
        "step_recorded",
        {"step_id": step_id, "result": record["result"], "run": run_number},
    )
    return record


def _run_halt(
    ctx: chain_core.CommandContext,
    state: Mapping[str, Any] | None = None,
    *,
    scope: str = "commit",
    cwd: Path | None = None,
) -> None:
    argv = ["bash", str(ctx.helper("check-halt.sh")), scope]
    try:
        process = runtime.run_bounded(
            argv,
            cwd=cwd or ctx.repo.root,
            timeout=30.0,
            verbose=ctx.options.verbose,
        )
    except OSError as exc:
        raise Refusal(
            (
                V2ReasonCode.HALT_ENGAGED
                if scope == "merge"
                else ReasonCode.HALT_ENGAGED
            ),
            "operator halt check refused state mutation",
            expected="check-halt.sh exit 0",
            observed=str(exc),
            remediation="operator must inspect and clear the applicable AGENT_HALT sentinel",
            next_required_step=chain_core._forge_command(state, "status"),
            chain=state,
        ) from exc
    if process.returncode != 0 or process.timed_out or process.output_limit:
        raise Refusal(
            (
                V2ReasonCode.HALT_ENGAGED
                if scope == "merge"
                else ReasonCode.HALT_ENGAGED
            ),
            "operator halt check refused state mutation",
            expected="check-halt.sh exit 0",
            observed=process.output.decode("utf-8", "replace").strip() or f"exit {process.returncode}",
            remediation="operator must inspect and clear the applicable AGENT_HALT sentinel",
            next_required_step=chain_core._forge_command(state, "status"),
            chain=state,
        )


@dataclasses.dataclass(frozen=True)
class MergeAdmission:
    """Read-only FR-231 admission tuple; no chain or Git history is mutated."""

    repository: Path
    worktree: Path
    worktree_identity: dict[str, str]
    branch: str
    target: dict[str, str]
    candidate_head: str
    policy: Policy
    declared_tier: str | None
    run_task: chain_core.MergeRunTaskSnapshot | None
    status_output_digest: str


@dataclasses.dataclass(frozen=True)
class MergeScopeResult:
    argv: tuple[str, ...]
    command_digest: str
    environment_digest: str
    output_digest: str
    changed_paths: tuple[str, ...]
    out_of_scope_paths: tuple[str, ...]
    result: str


@dataclasses.dataclass(frozen=True)
class MergeCandidateGeneration:
    candidate: dict[str, Any]
    tier: dict[str, Any]
    classification: dict[str, Any]
    changed_paths: tuple[str, ...]
    scope: MergeScopeResult | None


@dataclasses.dataclass(frozen=True)
class MergeBootstrapClassification:
    """Durable candidate inputs awaiting post-common-lock classification."""

    candidate: dict[str, Any]
    scope: MergeScopeResult | None
    full_patch_output_digest: str
    scope_proof_digest: str | None = None
    fetch_result_event_digest: str | None = None
    verb: str = "merge start"
