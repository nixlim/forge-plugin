from __future__ import annotations

import copy
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

from forge_cli import chain_core, engine, runtime
from forge_cli.envelope import REVISION9_OUTPUT_SCHEMA, FrozenError, Refusal, V2ReasonCode

if TYPE_CHECKING:
    from forge_cli.app._merge_engine import MergeEngine

def _bootstrap_fetch_argv(
    admission: engine.MergeAdmission, remote_tip: str | None
) -> tuple[str, list[str]]:
    if remote_tip is not None:
        return (
            "tip-resolution",
            [
                "git",
                "--no-pager",
                "-C",
                str(admission.worktree),
                "cat-file",
                "-e",
                f"{remote_tip}^{{commit}}",
            ],
        )
    return (
        "fetch",
        [
            "git",
            "--no-pager",
            "-C",
            str(admission.worktree),
            "fetch",
            "--no-tags",
            "--quiet",
            "origin",
            admission.target["destination_ref"],
        ],
    )

def _resolved_fetch_tip(
    admission: engine.MergeAdmission, supplied: str | None
) -> str:
    if supplied is not None:
        return supplied
    fetch_head = Path(admission.worktree_identity["git_dir"]) / "FETCH_HEAD"
    try:
        raw = fetch_head.read_bytes()
    except OSError as exc:
        raise ValueError(f"FETCH_HEAD is unavailable: {exc}") from exc
    if len(raw) > chain_core.MERGE_SCOPE_BINDING_CAP_BYTES or not raw.endswith(b"\n"):
        raise ValueError("FETCH_HEAD is malformed")
    rows = raw.splitlines()
    if len(rows) != 1:
        raise ValueError("FETCH_HEAD does not identify one fixed target")
    raw_oid = rows[0].split(b"\t", 1)[0]
    try:
        oid = raw_oid.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError("FETCH_HEAD object ID is not ASCII") from exc
    if chain_core.COMMIT_RE.fullmatch(oid) is None:
        raise ValueError("FETCH_HEAD object ID is invalid")
    return oid

def _run_bootstrap_generation_composite(
    self: MergeEngine,
    state: dict[str, Any],
    admission: engine.MergeAdmission,
    lock: chain_core.CommonRebaseLock,
    *,
    operation_nonce: str,
    attempt: int,
    remote_tip: str | None,
    generation_number: int,
    verb: str,
) -> tuple[dict[str, Any], engine.MergeBootstrapClassification]:
    """Run Revision-12's child and retain a post-lock classification input."""

    chain_core._require_merge_integration_control("composite-bootstrap-streaming")
    chain_core._require_merge_integration_control("post-fetch-binding")
    fetch_intent_digest = engine._merge_event_digest(
        self.store, str(state["chain_id"]), "fetch_intent"
    )
    if fetch_intent_digest is None:
        raise FrozenError(
            "merge bootstrap fetch intent digest is unavailable",
            chain_id=str(state["chain_id"]),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    operation, fetch_argv = self._bootstrap_fetch_argv(admission, remote_tip)
    holder: dict[str, Any] = {}

    def intent_current() -> bool:
        return (
            engine._merge_event_digest(
                self.store, str(state["chain_id"]), "fetch_intent"
            )
            == fetch_intent_digest
        )

    def failed_result(
        binding: Mapping[str, Any] | None,
    ) -> None:
        nonlocal state
        integration = copy.deepcopy(state["integration"])
        integration.update(
            {
                "condition": "fetch-failed",
                "primary_condition": "none",
                "intent": {
                    "operation": "fetch-result",
                    "operation_nonce": operation_nonce,
                    "attempt": attempt,
                    "result": "failed",
                    "resolved_tip": None,
                },
            }
        )
        state = self.store.transition(
            state,
            "fetch_result",
            {
                "delta": {"integration": integration},
                "scope_proof": None,
                "scope_fetch_binding": (
                    copy.deepcopy(dict(binding))
                    if isinstance(binding, Mapping)
                    else None
                ),
            },
            generation_digest=(
                str(state["candidate"]["generation_digest"])
                if isinstance(state.get("candidate"), Mapping)
                else None
            ),
            at=chain_core.iso_z(),
        )

    def materialize_success(
        binding: Mapping[str, Any],
        fixed_tip: str,
    ) -> dict[str, Any]:
        """Materialize the complete candidate while the child fence survives."""

        nonlocal state
        candidate = engine._retain_or_advance_merge_candidate(
            admission,
            fixed_tip,
            prior_candidate=state.get("candidate"),
            generation=generation_number,
            diff_output_digest=str(binding["full_patch_output_digest"]),
        )
        integration = copy.deepcopy(state["integration"])
        integration.update(
            {
                "condition": "none",
                "primary_condition": "none",
                "intent": {
                    "operation": "fetch-result",
                    "operation_nonce": operation_nonce,
                    "attempt": attempt,
                    "result": "success",
                    "resolved_tip": fixed_tip,
                },
            }
        )
        review = state.get("review")
        iteration = (
            review.get("iteration") if isinstance(review, Mapping) else None
        )
        retained_review = (
            {"iteration": iteration} if type(iteration) is int else {}
        )
        desired = {
            "candidate": copy.deepcopy(candidate),
            "tier": None,
            "state": "classifying",
            "policy_source": {
                "commit": admission.policy.sha,
                "digest": admission.policy.digest,
            },
            "steps": {},
            "review": retained_review,
            "approval": {},
            "authorization": {},
            "integration": integration,
        }
        state = self.store.transition(
            state,
            "fetch_result",
            {
                "delta": {
                    name: value
                    for name, value in desired.items()
                    if state.get(name) != value or name == "state"
                },
                "scope_proof": None,
                "scope_fetch_binding": copy.deepcopy(dict(binding)),
            },
            generation_digest=str(candidate["generation_digest"]),
            at=chain_core.iso_z(),
        )
        return candidate

    def persist(result: chain_core.FencedProcessResult) -> None:
        metadata = result.metadata
        complete = bool(
            result.authorized
            and result.returncode == 0
            and not result.launch_failed
            and not result.timed_out
            and not result.output_limit
            and not result.group_survived
            and isinstance(metadata, Mapping)
            and isinstance(metadata.get("full_patch"), Mapping)
            and isinstance(metadata.get("resolved_tip"), str)
        )
        binding: dict[str, Any] | None = None
        candidate: dict[str, Any] | None = None
        error: str | None = None
        fixed_tip = (
            str(metadata["resolved_tip"])
            if complete and isinstance(metadata, Mapping)
            else None
        )
        if complete and fixed_tip is not None:
            try:
                fence, fence_error, _evidence = chain_core._read_fence_for_recovery(
                    lock._common, lock.common_dir
                )
                if (
                    fence_error is not None
                    or fence is None
                    or fence.digest != result.fence_digest
                    or fence.inode != result.fence_inode
                    or fence.record.get("intent_digest") != fetch_intent_digest
                    or fence.record.get("operation") != operation
                ):
                    raise OSError(
                        "retained bootstrap fence is unavailable or mismatched"
                    )
                binding = engine._publish_merge_scope_binding(
                    self.store,
                    state,
                    fetch_intent_digest=fetch_intent_digest,
                    remote_tip=fixed_tip,
                    fence=fence,
                    result=result,
                )
                # Classification is deliberately excluded from this
                # callback, but the successful result itself belongs to
                # the fenced composite: after the /2 sidecar is durable,
                # materialize its complete candidate before the original
                # fence is cleared.
                candidate = materialize_success(
                    binding, fixed_tip
                )
            except (OSError, TypeError, ValueError, Refusal) as exc:
                error = str(exc)
        if not complete or error is not None:
            failed_result(binding)
        holder.update(
            {
                "complete": bool(
                    complete
                    and error is None
                    and binding is not None
                    and candidate is not None
                ),
                "fixed_tip": fixed_tip,
                "binding": copy.deepcopy(binding),
                "candidate": copy.deepcopy(candidate),
                "error": error,
                "metadata": copy.deepcopy(metadata),
            }
        )

    environment = engine._merge_scope_environment()
    try:
        engine._require_git_no_lazy_fetch_qualification(
            self._git_no_lazy_fetch_qualification,
            admission.worktree,
            environment,
        )
    except OSError as exc:
        failed_result(None)
        holder.update(
            {
                "complete": False,
                "fixed_tip": None,
                "binding": None,
                "error": str(exc),
                "metadata": None,
            }
        )
        refusal = chain_core._merge_refusal(
            V2ReasonCode.FETCH_FAILED,
            f"forge: {verb} refused — fixed target fetch failed",
            expected="the pre-lock Git qualification to remain exact",
            observed=str(exc),
            chain=state,
        )
        raise refusal from exc
    composite_result = chain_core.run_fenced_command(
        lock,
        operation=operation,
        intent_digest=fetch_intent_digest,
        intent_validator=intent_current,
        argv=engine._merge_bootstrap_child_argv(
            admission,
            fetch_argv=fetch_argv,
            remote_tip=remote_tip,
        ),
        cwd=admission.worktree,
        persist_result=persist,
        env=environment,
        timeout=runtime.COMMAND_TIMEOUT_SECONDS,
        cap=runtime.OUTPUT_CAP_BYTES,
        verbose=False,
        result_transform=lambda raw: engine._decode_merge_bootstrap_result(
            raw,
            fetch_argv=fetch_argv,
            worktree=admission.worktree,
            candidate_head=admission.candidate_head,
            environment_digest=engine._git_environment_digest(environment),
        ),
    )
    if not holder.get("complete"):
        refusal = _incomplete_bootstrap_refusal(verb, holder, composite_result, state)
        raise refusal

    binding = holder.get("binding")
    candidate = holder.get("candidate")
    if (
        not isinstance(binding, Mapping)
        or not isinstance(candidate, Mapping)
    ):
        raise FrozenError(
            "composite bootstrap sidecar was not durably retained",
            chain_id=str(state["chain_id"]),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    return state, engine.MergeBootstrapClassification(
        candidate=copy.deepcopy(dict(candidate)),
        full_patch_output_digest=str(binding["full_patch_output_digest"]),
        verb=verb,
    )

def _run_bootstrap_generation(
    self: MergeEngine,
    state: dict[str, Any],
    admission: engine.MergeAdmission,
    lock: chain_core.CommonRebaseLock,
    *,
    operation_nonce: str,
    attempt: int,
    remote_tip: str | None,
    generation_number: int,
    verb: str = "merge start",
) -> tuple[dict[str, Any], engine.MergeBootstrapClassification]:
    """Run the fenced bootstrap and retain its classification inputs."""

    return self._run_bootstrap_generation_composite(
        state,
        admission,
        lock,
        operation_nonce=operation_nonce,
        attempt=attempt,
        remote_tip=remote_tip,
        generation_number=generation_number,
        verb=verb,
    )


def _incomplete_bootstrap_refusal(verb, holder, composite_result, state):
    refusal = chain_core._merge_refusal(
        V2ReasonCode.FETCH_FAILED,
        f"forge: {verb} refused — fixed target fetch failed",
        expected="one complete composite bootstrap child",
        observed=str(holder.get("error") or composite_result.evidence()),
        chain=state,
    )
    return refusal
