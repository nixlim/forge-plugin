"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
import os
import stat
from pathlib import Path
from typing import Any, Mapping
from forge_cli import chain_core, runtime
from forge_cli.engine._cli_options import _message_from_args as _message_from_args, _validate_revision9_cross_options as _validate_revision9_cross_options, render as render
from forge_cli.engine._core import commit_message_bytes as commit_message_bytes, chain_id_now as chain_id_now, promoted_tier as promoted_tier, _transition_state as _transition_state, _require_merge_lifecycle_control as _require_merge_lifecycle_control, inspect_common_lock as inspect_common_lock, _archive_refusal as _archive_refusal, _archive_contamination_refusal as _archive_contamination_refusal, _archive_metadata as _archive_metadata, _env_fingerprint as _env_fingerprint, _evidence_record as _evidence_record, _write_artifact as _write_artifact, _read_bound_artifact as _read_bound_artifact, _record_process_step as _record_process_step, _run_halt as _run_halt, MergeAdmission as MergeAdmission, MergeScopeResult as MergeScopeResult, MergeCandidateGeneration as MergeCandidateGeneration, MergeBootstrapClassification as MergeBootstrapClassification
from forge_cli.engine._parser import ContractArgumentParser as ContractArgumentParser, _extract_global_options as _extract_global_options, _attach_merge_lifecycle_parser as _attach_merge_lifecycle_parser, build_parser as build_parser, _raw_top_level_command as _raw_top_level_command
from forge_cli.engine._state import TERMINAL_STATES as TERMINAL_STATES, TERMINAL_TOUCH_VERBS as TERMINAL_TOUCH_VERBS, STATE_TRANSITIONS as STATE_TRANSITIONS, TOKEN_TTL_SECONDS as TOKEN_TTL_SECONDS, _REQUIRED_MERGE_LIFECYCLE_CONTROLS as _REQUIRED_MERGE_LIFECYCLE_CONTROLS, MERGE_LIFECYCLE_CONTROLS as MERGE_LIFECYCLE_CONTROLS, _REQUIRED_ARCHIVE_RECHECK_CONTROLS as _REQUIRED_ARCHIVE_RECHECK_CONTROLS, ARCHIVE_RECHECK_CONTROLS as ARCHIVE_RECHECK_CONTROLS, _CHAIN_CAPABILITY_LOCK as _CHAIN_CAPABILITY_LOCK, _CHAIN_CAPABILITIES as _CHAIN_CAPABILITIES, CODEX_EXECUTABLE as CODEX_EXECUTABLE, FRESH_REVIEWER_EVAL_REQUEST_SCHEMA as FRESH_REVIEWER_EVAL_REQUEST_SCHEMA, REVIEW_DIRECT_PACKAGE_MAX_BYTES as REVIEW_DIRECT_PACKAGE_MAX_BYTES, REVIEW_MASTER_WINDOW_BYTES as REVIEW_MASTER_WINDOW_BYTES, REVIEW_COMPLETE_PACKAGE_REFUSAL as REVIEW_COMPLETE_PACKAGE_REFUSAL, PRODUCED_COMMIT_MISMATCH as PRODUCED_COMMIT_MISMATCH, REVIEW_INSTRUCTION as REVIEW_INSTRUCTION, REVIEW_LAUNCHER_CODE as REVIEW_LAUNCHER_CODE, GLOBAL_OPTIONS_HELP as GLOBAL_OPTIONS_HELP, ARCHIVE_CONTAMINATION as ARCHIVE_CONTAMINATION, SECRET_RULES as SECRET_RULES, PLACEHOLDER_RE as PLACEHOLDER_RE, ABORT_DISPOSITION_PRECONDITIONS as ABORT_DISPOSITION_PRECONDITIONS, _MERGE_CANDIDATE_IDENTITY_FIELDS as _MERGE_CANDIDATE_IDENTITY_FIELDS, _MERGE_BOOTSTRAP_CHILD_SOURCE as _MERGE_BOOTSTRAP_CHILD_SOURCE, _DERIVE_MERGE_SCOPE as _DERIVE_MERGE_SCOPE, _MERGE_INITIAL_INTEGRATION as _MERGE_INITIAL_INTEGRATION
import copy
from forge_cli.policy import sha256_bytes


def _merge_branch_reflog_proves_integrated(
    state: Mapping[str, Any], observed_head: str
) -> bool:
    action = chain_core._merge_rebase_action(state)
    integration = state.get("integration")
    pre_rebase = (
        integration.get("pre_rebase") if isinstance(integration, Mapping) else None
    )
    if action is None or not isinstance(pre_rebase, Mapping):
        return False
    common_dir = Path(str(state.get("worktree", {}).get("common_dir", "")))
    branch = str(state.get("branch", ""))
    branch_parts = branch.split("/")
    if (
        not branch.startswith("refs/heads/")
        or any(part in {"", ".", ".."} for part in branch_parts)
        or "\\" in branch
        or "\x00" in branch
    ):
        return False
    path = common_dir / "logs" / Path(*branch_parts)
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid():
                return False
            start = max(0, before.st_size - runtime.OUTPUT_CAP_BYTES)
            os.lseek(descriptor, start, os.SEEK_SET)
            raw = os.read(descriptor, runtime.OUTPUT_CAP_BYTES + 1)
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        return False
    try:
        rebound = os.lstat(path)
    except OSError:
        return False
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or before.st_ctime_ns != after.st_ctime_ns
        or rebound.st_dev != after.st_dev
        or rebound.st_ino != after.st_ino
        or rebound.st_size != after.st_size
        or rebound.st_mtime_ns != after.st_mtime_ns
        or rebound.st_ctime_ns != after.st_ctime_ns
        or not stat.S_ISREG(rebound.st_mode)
        or rebound.st_uid != os.geteuid()
        or len(raw) > runtime.OUTPUT_CAP_BYTES
        or not raw.endswith(b"\n")
    ):
        return False
    if start:
        _partial, separator, raw = raw.partition(b"\n")
        if not separator:
            return False
    lines = raw.splitlines()
    selected: list[tuple[str, str]] = []
    prefix = action.encode("utf-8")
    for line in reversed(lines):
        metadata, separator, message = line.partition(b"\t")
        if not separator or not message.startswith(prefix):
            break
        fields = metadata.split(b" ", 2)
        if len(fields) < 2:
            return False
        try:
            old = fields[0].decode("ascii")
            new = fields[1].decode("ascii")
        except UnicodeDecodeError:
            return False
        if chain_core.COMMIT_RE.fullmatch(old) is None or chain_core.COMMIT_RE.fullmatch(new) is None:
            return False
        selected.append((old, new))
    if not selected:
        return False
    chronological = list(reversed(selected))
    return bool(
        chronological[0][0] == pre_rebase.get("head")
        and chronological[-1][1] == observed_head
        and all(
            left[1] == right[0]
            for left, right in zip(chronological, chronological[1:])
        )
    )


def _merge_rebase_integrated_observation_binding(
    state: Mapping[str, Any], source_intent: Mapping[str, Any]
) -> str | None:
    integration = state.get("integration")
    pre_rebase = (
        integration.get("pre_rebase") if isinstance(integration, Mapping) else None
    )
    epoch = integration.get("epoch") if isinstance(integration, Mapping) else None
    action = chain_core._merge_rebase_action(state)
    if (
        not isinstance(pre_rebase, Mapping)
        or not isinstance(epoch, Mapping)
        or action is None
        or chain_core._merge_rebase_result_classification(
            {
                **state,
                "integration": {
                    **dict(integration),
                    "intent": copy.deepcopy(dict(source_intent)),
                },
            }
        )
        == "foreign"
    ):
        return None
    return sha256_bytes(
        chain_core.canonical_bytes(
            {
                "schema": "forge-merge-integrated-observation-binding/1",
                "chain_id": state.get("chain_id"),
                "operation_nonce": epoch.get("operation_nonce"),
                "generation_digest": pre_rebase.get("generation_digest"),
                "pre_operation_head": pre_rebase.get("head"),
                "fetched_tip": pre_rebase.get("fetched_tip"),
                "branch": state.get("branch"),
                "reflog_action": action,
                "source_intent": copy.deepcopy(dict(source_intent)),
            }
        )
    )


def _merge_rebase_operation_metadata_absent(state: Mapping[str, Any]) -> bool:
    git_dir = Path(str(state.get("worktree", {}).get("git_dir", "")))
    for name in (
        "MERGE_HEAD",
        "CHERRY_PICK_HEAD",
        "REVERT_HEAD",
        "BISECT_LOG",
        "rebase-apply",
        "rebase-merge",
        "sequencer",
    ):
        try:
            os.lstat(git_dir / name)
        except FileNotFoundError:
            continue
        except OSError:
            return False
        return False
    return True


def _merge_rebase_integrated_predicate(
    state: Mapping[str, Any], observation: Mapping[str, Any]
) -> bool:
    """Validate only a completed, fenced integrated-result observation."""

    chain_core._require_merge_integration_control("rebase-result-proof")
    integration = state.get("integration")
    pre_rebase = (
        integration.get("pre_rebase") if isinstance(integration, Mapping) else None
    )
    epoch = integration.get("epoch") if isinstance(integration, Mapping) else None
    source_intent = (
        integration.get("intent") if isinstance(integration, Mapping) else None
    )
    steps = observation.get("steps") if isinstance(observation, Mapping) else None
    expected_binding = (
        _merge_rebase_integrated_observation_binding(state, source_intent)
        if isinstance(source_intent, Mapping)
        else None
    )
    if (
        not isinstance(pre_rebase, Mapping)
        or not isinstance(epoch, Mapping)
        or not isinstance(observation, Mapping)
        or expected_binding is None
        or set(observation)
        != {
            "schema",
            "observation_binding",
            "operation_nonce",
            "generation_digest",
            "pre_operation_head",
            "fetched_tip",
            "branch",
            "observed_head",
            "status_digest",
            "status_empty",
            "fetched_tip_ancestor",
            "steps",
            "evidence_digest",
        }
        or observation.get("schema") != "forge-merge-integrated-observation/1"
        or observation.get("observation_binding") != expected_binding
        or observation.get("operation_nonce") != epoch.get("operation_nonce")
        or observation.get("generation_digest")
        != pre_rebase.get("generation_digest")
        or observation.get("pre_operation_head") != pre_rebase.get("head")
        or observation.get("fetched_tip") != pre_rebase.get("fetched_tip")
        or observation.get("branch") != state.get("branch")
        or chain_core.COMMIT_RE.fullmatch(str(observation.get("observed_head", ""))) is None
        or observation.get("status_digest") != sha256_bytes(b"")
        or observation.get("status_empty") is not True
        or observation.get("fetched_tip_ancestor") is not True
        or not isinstance(steps, Mapping)
        or set(steps) != {"branch", "head", "status", "ancestry"}
        or any(
            not isinstance(step, Mapping)
            or set(step)
            != {"intent_digest", "inflight_digest", "output_digest", "exit"}
            or chain_core.SHA256_RE.fullmatch(str(step.get("intent_digest", ""))) is None
            or chain_core.SHA256_RE.fullmatch(str(step.get("inflight_digest", ""))) is None
            or chain_core.SHA256_RE.fullmatch(str(step.get("output_digest", ""))) is None
            or type(step.get("exit")) is not int
            for step in steps.values()
        )
        or observation.get("evidence_digest")
        != sha256_bytes(
            chain_core.canonical_bytes(
                {
                    name: copy.deepcopy(value)
                    for name, value in observation.items()
                    if name != "evidence_digest"
                }
            )
        )
        or chain_core._merge_rebase_result_classification(state) not in {"absent", "success"}
        or not _merge_rebase_operation_metadata_absent(state)
    ):
        return False
    return bool(
        steps["branch"].get("exit") == 0
        and steps["head"].get("exit") == 0
        and steps["status"].get("exit") == 0
        and steps["ancestry"].get("exit") == 0
        and _merge_branch_reflog_proves_integrated(
            state, str(observation["observed_head"])
        )
    )
