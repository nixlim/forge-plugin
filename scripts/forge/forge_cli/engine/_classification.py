"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
import sys
from typing import Any, Mapping, MutableMapping
from forge_cli import chain_core, candidate as candidate_module, runtime
from forge_cli.engine._cli_options import _message_from_args as _message_from_args, _validate_revision9_cross_options as _validate_revision9_cross_options, render as render
from forge_cli.engine._core import commit_message_bytes as commit_message_bytes, chain_id_now as chain_id_now, promoted_tier as promoted_tier, _transition_state as _transition_state, _require_merge_lifecycle_control as _require_merge_lifecycle_control, inspect_common_lock as inspect_common_lock, _archive_refusal as _archive_refusal, _archive_contamination_refusal as _archive_contamination_refusal, _archive_metadata as _archive_metadata, _env_fingerprint as _env_fingerprint, _evidence_record as _evidence_record, _write_artifact as _write_artifact, _read_bound_artifact as _read_bound_artifact, _record_process_step as _record_process_step, _run_halt as _run_halt, MergeAdmission as MergeAdmission, MergeScopeResult as MergeScopeResult, MergeCandidateGeneration as MergeCandidateGeneration, MergeBootstrapClassification as MergeBootstrapClassification
from forge_cli.engine._parser import ContractArgumentParser as ContractArgumentParser, _extract_global_options as _extract_global_options, _attach_merge_lifecycle_parser as _attach_merge_lifecycle_parser, build_parser as build_parser, _raw_top_level_command as _raw_top_level_command
from forge_cli.engine._state import TERMINAL_STATES as TERMINAL_STATES, TERMINAL_TOUCH_VERBS as TERMINAL_TOUCH_VERBS, STATE_TRANSITIONS as STATE_TRANSITIONS, TOKEN_TTL_SECONDS as TOKEN_TTL_SECONDS, _REQUIRED_MERGE_LIFECYCLE_CONTROLS as _REQUIRED_MERGE_LIFECYCLE_CONTROLS, MERGE_LIFECYCLE_CONTROLS as MERGE_LIFECYCLE_CONTROLS, _REQUIRED_ARCHIVE_RECHECK_CONTROLS as _REQUIRED_ARCHIVE_RECHECK_CONTROLS, ARCHIVE_RECHECK_CONTROLS as ARCHIVE_RECHECK_CONTROLS, _CHAIN_CAPABILITY_LOCK as _CHAIN_CAPABILITY_LOCK, _CHAIN_CAPABILITIES as _CHAIN_CAPABILITIES, CODEX_EXECUTABLE as CODEX_EXECUTABLE, FRESH_REVIEWER_EVAL_REQUEST_SCHEMA as FRESH_REVIEWER_EVAL_REQUEST_SCHEMA, REVIEW_DIRECT_PACKAGE_MAX_BYTES as REVIEW_DIRECT_PACKAGE_MAX_BYTES, REVIEW_MASTER_WINDOW_BYTES as REVIEW_MASTER_WINDOW_BYTES, REVIEW_COMPLETE_PACKAGE_REFUSAL as REVIEW_COMPLETE_PACKAGE_REFUSAL, PRODUCED_COMMIT_MISMATCH as PRODUCED_COMMIT_MISMATCH, REVIEW_INSTRUCTION as REVIEW_INSTRUCTION, REVIEW_LAUNCHER_CODE as REVIEW_LAUNCHER_CODE, GLOBAL_OPTIONS_HELP as GLOBAL_OPTIONS_HELP, ARCHIVE_CONTAMINATION as ARCHIVE_CONTAMINATION, SECRET_RULES as SECRET_RULES, PLACEHOLDER_RE as PLACEHOLDER_RE, ABORT_DISPOSITION_PRECONDITIONS as ABORT_DISPOSITION_PRECONDITIONS, _MERGE_CANDIDATE_IDENTITY_FIELDS as _MERGE_CANDIDATE_IDENTITY_FIELDS, _MERGE_BOOTSTRAP_CHILD_SOURCE as _MERGE_BOOTSTRAP_CHILD_SOURCE, _DERIVE_MERGE_SCOPE as _DERIVE_MERGE_SCOPE, _MERGE_INITIAL_INTEGRATION as _MERGE_INITIAL_INTEGRATION
import os
import json
from forge_cli.envelope import ReasonCode, Refusal


def _classification_argv(
    ctx: chain_core.CommandContext,
    state: Mapping[str, Any],
    *,
    require_effective: str | None = None,
) -> list[str]:
    argv = [
        sys.executable,
        str(ctx.helper("risk_tier.py")),
        "--repo",
        str(ctx.repo.root),
        "--policy-sha",
        str(state["policy_source"]["sha"]),
        "--staged",
    ]
    declared = state["tier"].get("declared")
    if declared:
        argv.extend(["--declared-tier", str(declared)])
    if require_effective:
        argv.extend(["--require-effective", require_effective])
    return argv


def _classification_environment(
    ctx: chain_core.CommandContext, state: Mapping[str, Any]
) -> dict[str, str]:
    context = ctx.repo.candidate_context()
    environment = candidate_module.context_from_paths(
        worktree_root=context.worktree_root,
        git_dir=context.git_dir,
        common_dir=context.common_dir,
        index_file=context.index_file,
        bare=context.bare,
        environment=os.environ,
        effective_cwd=context.worktree_root,
    ).environment()
    for key in tuple(environment):
        if key.startswith("FORGE_CANDIDATE_"):
            environment.pop(key, None)
    record = state.get("candidate")
    if not chain_core.candidate_is_v2(state) or not isinstance(record, Mapping):
        return environment
    environment.update(
        {
            "FORGE_CANDIDATE_SCHEMA": candidate_module.CANDIDATE_SCHEMA,
            "FORGE_CANDIDATE_AUTHORIZATION_ID": str(record["authorization_id"]),
            "FORGE_CANDIDATE_OBJECT_FORMAT": str(record["object_format"]),
            "FORGE_CANDIDATE_TREE_OID": str(record["tree_oid"]),
            "FORGE_CANDIDATE_BASE_COMMIT_OID": str(record["base_commit_oid"] or ""),
        }
    )
    return environment


def _run_classification(
    ctx: chain_core.CommandContext,
    state: MutableMapping[str, Any],
    *,
    persist_event: bool = True,
) -> dict[str, Any]:
    policy = chain_core._policy_for_state(ctx, state)
    argv = _classification_argv(ctx, state)
    process = runtime.run_bounded(
        argv,
        cwd=ctx.repo.root,
        env=_classification_environment(ctx, state),
        timeout=runtime.COMMAND_TIMEOUT_SECONDS,
        verbose=ctx.options.verbose,
    )
    if process.returncode != 0 or process.timed_out or process.output_limit:
        if persist_event:
            record = _record_process_step(ctx, state, "classification", argv, process)
        else:
            record = {}
        raise Refusal(
            ReasonCode.EVIDENCE_INCOMPLETE,
            "risk-tier classification did not pass",
            expected="risk_tier.py exit 0 with one JSON object",
            observed=(
                f"exit={process.returncode}, timeout={process.timed_out}, "
                f"output_limit={process.output_limit}"
            ),
            remediation=f"forge classify --chain-id {state['chain_id']}",
            chain=state,
            evidence_refs=[record.get("transcript", "")] if record else (),
        )
    try:
        evidence = json.loads(process.output)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Refusal(
            ReasonCode.EVIDENCE_INCOMPLETE,
            "risk-tier classifier returned malformed evidence",
            expected="one JSON object",
            observed=process.output.decode("utf-8", "replace")[:200],
            remediation=f"forge classify --chain-id {state['chain_id']}",
            chain=state,
        ) from exc
    if not isinstance(evidence, dict) or evidence.get("policy_sha") != policy.sha:
        raise Refusal(
            ReasonCode.EVIDENCE_INCOMPLETE,
            "risk-tier evidence did not bind to the pinned policy",
            expected=policy.sha,
            observed=str(evidence.get("policy_sha")) if isinstance(evidence, dict) else None,
            remediation=f"forge classify --chain-id {state['chain_id']}",
            chain=state,
        )
    derived = evidence.get("derived_tier")
    computed_effective = evidence.get("effective_tier")
    if derived not in chain_core.TIER_RANK or computed_effective not in chain_core.TIER_RANK:
        raise Refusal(
            ReasonCode.EVIDENCE_INCOMPLETE,
            "risk-tier evidence contains an invalid tier",
            observed=str(computed_effective),
            remediation=f"forge classify --chain-id {state['chain_id']}",
            chain=state,
        )
    path_evidence = evidence.get("paths")
    evidence_paths = (
        [item.get("path") for item in path_evidence]
        if isinstance(path_evidence, list)
        and all(isinstance(item, dict) for item in path_evidence)
        else []
    )
    if (
        any(not isinstance(path, str) for path in evidence_paths)
        or len(evidence_paths) != len(set(evidence_paths))
        or sorted(str(path) for path in evidence_paths)
        != sorted(str(path) for path in state.get("paths", []))
    ):
        raise Refusal(
            ReasonCode.EVIDENCE_INCOMPLETE,
            "risk-tier evidence path set differs from the candidate snapshot",
            expected=str(state.get("paths", [])),
            observed=str(evidence_paths),
            remediation=f"forge classify --chain-id {state['chain_id']}",
            chain=state,
        )
    categories: set[str] = set()
    # Classification is promote-only across the lifetime of a chain.  A
    # control floor discovered for any candidate cannot later be erased by
    # restaging a lower-risk path set inside that same chain.
    control = bool(state["tier"].get("control"))
    for path_record in path_evidence:
        if not isinstance(path_record, dict):
            continue
        categories.update(
            str(value) for value in path_record.get("categories", []) if value
        )
        control = control or bool(path_record.get("control_floor"))
    old_effective = state["tier"].get("effective")
    effective = promoted_tier(old_effective, str(computed_effective))
    if control:
        effective = "hard"
    state["tier"].update(
        {
            "derived": derived,
            "effective": effective,
            "control": control,
            "categories": sorted(categories),
            "classification": evidence,
        }
    )
    state["staging"]["classification_runs"] = int(
        state["staging"].get("classification_runs", 0)
    ) + 1
    _transition_state(state, "verifying")
    preimage, fingerprint = _env_fingerprint(ctx, state, argv)
    state["steps"]["classification"] = [
        {
            "candidate": state["candidate"]["sha256"],
            "recorded_at": chain_core.iso_z(),
            "result": "passed",
            "repo_head": ctx.repo.head(),
            "command_argv": argv,
            "command_digest": preimage["command_digest"],
            "env_fingerprint_preimage": preimage,
            "env_fingerprint": fingerprint,
            "evidence": evidence,
        }
    ]
    if persist_event:
        ctx.store.persist(
            state,
            "classified",
            {"effective_tier": effective, "control": control},
        )
    return evidence
