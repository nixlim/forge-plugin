"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
import copy
from typing import Any, Mapping
from forge_cli import chain_core, runtime
from forge_cli.engine._core import MergeAdmission as MergeAdmission, MergeScopeResult as MergeScopeResult, MergeCandidateGeneration as MergeCandidateGeneration
from forge_cli.engine._merge_candidate_observation import _merge_candidate_observation_outputs as _merge_candidate_observation_outputs, _parse_merge_candidate_observation as _parse_merge_candidate_observation
from forge_cli.engine._merge_scope_derive import _parse_merge_scope_output as _parse_merge_scope_output, _derive_merge_scope as _derive_merge_scope
from forge_cli.engine._merge_worktree import _merge_worktree_status as _merge_worktree_status
from forge_cli.engine._state import _DERIVE_MERGE_SCOPE as _DERIVE_MERGE_SCOPE
from forge_cli.envelope import V2ReasonCode
from forge_cli.policy import sha256_bytes
import json
import sys
from pathlib import Path


def _merge_scope_from_candidate_observation(
    admission: MergeAdmission, observation: Mapping[str, Any]
) -> MergeScopeResult | None:
    snapshot = admission.run_task
    if snapshot is None:
        return None
    synthetic_state = {
        "chain_id": observation.get("chain_id"),
        "repository": str(admission.repository),
        "worktree": copy.deepcopy(admission.worktree_identity),
        "branch": admission.branch,
        "target": copy.deepcopy(admission.target),
        "run_binding": copy.deepcopy(snapshot.binding),
        "candidate": (
            {"generation_digest": observation.get("generation_digest")}
            if observation.get("generation_digest") is not None
            else None
        ),
    }
    outputs = _merge_candidate_observation_outputs(
        synthetic_state, observation
    )
    if outputs is None or "scope" not in outputs:
        raise chain_core._merge_refusal(
            V2ReasonCode.RUN_TASK_BINDING_INVALID,
            "forge: merge start refused — durable run/task scope evidence is unavailable",
        )
    try:
        changed_paths = _parse_merge_scope_output(outputs["scope"])
    except ValueError as exc:
        raise chain_core._merge_refusal(
            V2ReasonCode.RUN_TASK_BINDING_INVALID,
            "forge: merge start refused — durable run/task scope evidence is malformed",
            observed=str(exc),
        ) from exc
    _batch, _builders, journal = runtime._coordination_modules()
    out_of_scope = tuple(
        path
        for path in changed_paths
        if not any(
            journal.pathspec_contained(path, pattern)
            for pattern in snapshot.task_files
        )
        or not any(
            journal.pathspec_contained(path, pattern)
            for pattern in snapshot.admitted_scope
        )
    )
    argv = chain_core._merge_scope_argv(
        admission.worktree,
        str(observation["remote_tip"]),
        admission.candidate_head,
    )
    scope_record = next(
        record
        for record in observation["steps"]
        if record.get("step") == "scope"
    )
    return MergeScopeResult(
        argv=tuple(argv),
        command_digest=sha256_bytes(chain_core.canonical_bytes(argv)),
        environment_digest=sha256_bytes(
            chain_core.canonical_bytes(chain_core._merge_scope_environment_contract())
        ),
        output_digest=str(scope_record["child_result"]["output_digest"]),
        changed_paths=changed_paths,
        out_of_scope_paths=out_of_scope,
        result="exceeded" if out_of_scope else "contained",
    )


def bind_merge_candidate_generation(
    ctx: chain_core.CommandContext,
    admission: MergeAdmission,
    remote_tip: str,
    *,
    generation: int = 1,
    scope_result: MergeScopeResult | None | object = _DERIVE_MERGE_SCOPE,
    fixed_tip_bound: bool = False,
    observation: Mapping[str, Any] | None = None,
    diff_output_digest: str | None = None,
) -> MergeCandidateGeneration:
    """Bind one fixed fetched base to the exact DM-014 generation tuple."""

    chain_core._require_merge_adapter_control("admission-and-generation")
    if (
        chain_core.COMMIT_RE.fullmatch(remote_tip) is None
        or generation <= 0
        or (
            diff_output_digest is not None
            and chain_core.SHA256_RE.fullmatch(diff_output_digest) is None
        )
    ):
        raise chain_core._merge_refusal(
            V2ReasonCode.FETCH_FAILED,
            "forge: merge start refused — fetched target tip is invalid",
            expected="a full fixed Git object ID and positive generation",
            observed=remote_tip,
        )
    candidate_repo = chain_core.Repository(admission.worktree)
    observed_paths: tuple[str, ...] | None = None
    classifier_output: bytes | None = None
    if observation is not None:
        observation_generation = observation.get("generation_digest")
        observation_state: dict[str, Any] = {
            "chain_id": observation.get("chain_id"),
            "repository": str(admission.repository),
            "worktree": copy.deepcopy(admission.worktree_identity),
            "branch": admission.branch,
            "target": copy.deepcopy(admission.target),
            "run_binding": (
                copy.deepcopy(admission.run_task.binding)
                if admission.run_task is not None
                else None
            ),
            "candidate": (
                {"generation_digest": observation_generation}
                if observation_generation is not None
                else None
            ),
        }
        if (
            observation.get("expected_head") != admission.candidate_head
            or observation.get("remote_tip") != remote_tip
            or observation.get("classify") is not True
            or observation.get("declared_tier") != admission.declared_tier
        ):
            raise chain_core._merge_refusal(
                V2ReasonCode.EVIDENCE_INCOMPLETE,
                "forge: merge start refused — candidate observation is not generation-bound",
                expected="one complete generation-bound classification observation",
                observed=str(observation.get("evidence_digest")),
            )
        (
            candidate_repo,
            observed_policy,
            observed_paths,
            diff,
            classifier_output,
        ) = _parse_merge_candidate_observation(
            observation_state,
            observation,
            verb=str(observation.get("verb", "merge start")),
            require_current_generation=False,
        )
        if (
            observed_policy.sha != admission.policy.sha
            or observed_policy.digest != admission.policy.digest
        ):
            raise chain_core._merge_refusal(
                V2ReasonCode.CANDIDATE_STALE,
                "forge: merge start refused — committed candidate policy changed",
                expected=admission.policy.digest,
                observed=observed_policy.digest,
            )
    elif not fixed_tip_bound:
        resolved_tip = candidate_repo.git(
            ["rev-parse", "--verify", f"{remote_tip}^{{commit}}"], check=False
        )
        if (
            resolved_tip.returncode != 0
            or resolved_tip.stdout.decode("ascii", "replace").strip() != remote_tip
        ):
            raise chain_core._merge_refusal(
                V2ReasonCode.FETCH_FAILED,
                "forge: merge start refused — fetched target tip is invalid",
                expected="a locally available full fixed commit object ID",
                observed=remote_tip,
            )
    if observation is None and candidate_repo.head() != admission.candidate_head:
        raise chain_core._merge_refusal(
            V2ReasonCode.CANDIDATE_STALE,
            "forge: merge start refused — candidate HEAD changed after admission",
            expected=admission.candidate_head,
            observed=candidate_repo.head(),
        )
    if observation is None:
        _merge_worktree_status(
            candidate_repo, Path(admission.worktree_identity["git_dir"])
        )
        if diff_output_digest is None:
            try:
                diff = candidate_repo.git(
                    ["diff", f"{remote_tip}...{admission.candidate_head}"]
                ).stdout
            except OSError as exc:
                raise chain_core._merge_refusal(
                    V2ReasonCode.EVIDENCE_INCOMPLETE,
                    "forge: merge start refused — fixed candidate diff is unavailable",
                    expected=f"git diff {remote_tip}...{admission.candidate_head}",
                    observed=str(exc),
                ) from exc
    generation_preimage: dict[str, Any] = {
        "remote": "origin",
        "destination_ref": admission.target["destination_ref"],
        "remote_tip": remote_tip,
        "candidate_head": admission.candidate_head,
        "diff_sha256": (
            diff_output_digest
            if diff_output_digest is not None
            else sha256_bytes(diff)
        ),
        "policy_commit": admission.candidate_head,
        "policy_digest": admission.policy.digest,
        "worktree_identity": copy.deepcopy(admission.worktree_identity),
        "generation": generation,
    }
    candidate = {
        **generation_preimage,
        "generation_digest": sha256_bytes(chain_core.canonical_bytes(generation_preimage)),
    }
    # FR-231 requires the run-bound scope proof before classification.  The
    # lifecycle adapter invokes this function immediately after its fenced
    # fixed-tip fetch; this pure adapter must not reverse those two judgments.
    scope = (
        _merge_scope_from_candidate_observation(admission, observation)
        if observation is not None and scope_result is _DERIVE_MERGE_SCOPE
        else _derive_merge_scope(admission, remote_tip)
        if scope_result is _DERIVE_MERGE_SCOPE
        else scope_result
    )
    if scope is not None and not isinstance(scope, MergeScopeResult):
        raise TypeError("merge scope override is malformed")
    if scope is not None:
        changed_paths = scope.changed_paths
    elif observed_paths is not None:
        changed_paths = observed_paths
    else:
        try:
            names = candidate_repo.git(
                [
                    "diff",
                    "--name-only",
                    "-z",
                    "--diff-filter=ACDMRTUXB",
                    f"{remote_tip}...{admission.candidate_head}",
                    "--",
                ]
            ).stdout
        except OSError as exc:
            raise chain_core._merge_refusal(
                V2ReasonCode.EVIDENCE_INCOMPLETE,
                "forge: merge start refused — candidate path set is unavailable",
                expected="the complete fixed-range changed-path set",
                observed=str(exc),
            ) from exc
        try:
            changed_paths = tuple(
                sorted(
                    {
                        value.decode("utf-8")
                        for value in names.split(b"\0")
                        if value
                    },
                    key=lambda value: value.encode("utf-8"),
                )
            )
        except UnicodeDecodeError as exc:
            raise chain_core._merge_refusal(
                V2ReasonCode.WORKTREE_INVALID,
                "forge: merge start refused — candidate paths are not UTF-8",
                observed=str(exc),
            ) from exc
    if classifier_output is None:
        argv = [
            sys.executable,
            str(ctx.helper("risk_tier.py")),
            "--repo",
            str(admission.worktree),
            "--policy-sha",
            admission.candidate_head,
            "--range",
            f"{remote_tip}...{admission.candidate_head}",
        ]
        if admission.declared_tier is not None:
            argv.extend(["--declared-tier", admission.declared_tier])
        try:
            process = runtime.run_bounded(
                argv,
                cwd=admission.worktree,
                timeout=runtime.COMMAND_TIMEOUT_SECONDS,
                cap=runtime.OUTPUT_CAP_BYTES,
                verbose=ctx.options.verbose,
            )
        except OSError as exc:
            raise chain_core._merge_refusal(
                V2ReasonCode.EVIDENCE_INCOMPLETE,
                "forge: merge start refused — risk-tier classification did not pass",
                expected="risk_tier.py --range to launch within the fixed bounds",
                observed=str(exc),
            ) from exc
        if (
            process.returncode != 0
            or process.timed_out
            or process.output_limit
        ):
            raise chain_core._merge_refusal(
                V2ReasonCode.EVIDENCE_INCOMPLETE,
                "forge: merge start refused — risk-tier classification did not pass",
                expected="risk_tier.py --range exit 0 within the fixed bounds",
                observed=f"exit={process.returncode}",
            )
        classifier_output = process.output
    try:
        evidence = json.loads(classifier_output)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise chain_core._merge_refusal(
            V2ReasonCode.EVIDENCE_INCOMPLETE,
            "forge: merge start refused — risk-tier classification is malformed",
            observed=str(exc),
        ) from exc
    if (
        not isinstance(evidence, dict)
        or evidence.get("policy_sha") != admission.candidate_head
        or evidence.get("derived_tier") not in chain_core.TIER_RANK
        or evidence.get("effective_tier") not in chain_core.TIER_RANK
        or not isinstance(evidence.get("paths"), list)
    ):
        raise chain_core._merge_refusal(
            V2ReasonCode.EVIDENCE_INCOMPLETE,
            "forge: merge start refused — risk-tier evidence is not candidate-bound",
            expected=admission.candidate_head,
            observed=str(evidence),
        )
    categories: set[str] = set()
    control = False
    classified_paths: list[str] = []
    for path_evidence in evidence["paths"]:
        path_tier = (
            path_evidence.get("path_tier")
            if isinstance(path_evidence, dict)
            and "path_tier" in path_evidence
            else path_evidence.get("tier")
            if isinstance(path_evidence, dict)
            else None
        )
        if (
            not isinstance(path_evidence, dict)
            or not isinstance(path_evidence.get("path"), str)
            or not isinstance(path_evidence.get("categories"), list)
            or not all(
                isinstance(value, str) and value
                for value in path_evidence["categories"]
            )
            or path_tier not in chain_core.TIER_RANK
            or (
                "path_tier" in path_evidence
                and "tier" in path_evidence
                and path_evidence.get("path_tier") != path_evidence.get("tier")
            )
            or type(path_evidence.get("control_floor")) is not bool
        ):
            raise chain_core._merge_refusal(
                V2ReasonCode.EVIDENCE_INCOMPLETE,
                "forge: merge start refused — risk-tier evidence is not candidate-bound",
                expected="one complete classifier row for every exact changed path",
                observed=str(path_evidence),
            )
        classified_paths.append(str(path_evidence["path"]))
        categories.update(
            str(value)
            for value in path_evidence["categories"]
        )
        control = control or bool(path_evidence.get("control_floor"))
    if (
        len(classified_paths) != len(set(classified_paths))
        or tuple(
            sorted(classified_paths, key=lambda value: value.encode("utf-8"))
        )
        != changed_paths
    ):
        raise chain_core._merge_refusal(
            V2ReasonCode.EVIDENCE_INCOMPLETE,
            "forge: merge start refused — risk-tier evidence is not candidate-bound",
            expected=str(changed_paths),
            observed=str(classified_paths),
        )
    return MergeCandidateGeneration(
        candidate=candidate,
        tier={"control": control, "categories": sorted(categories)},
        classification=copy.deepcopy(evidence),
        changed_paths=changed_paths,
        scope=scope,
    )
