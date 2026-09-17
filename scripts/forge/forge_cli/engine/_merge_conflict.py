"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
from forge_cli.engine._cli_options import _message_from_args as _message_from_args, _validate_revision9_cross_options as _validate_revision9_cross_options, render as render
from forge_cli.engine._core import commit_message_bytes as commit_message_bytes, chain_id_now as chain_id_now, promoted_tier as promoted_tier, _transition_state as _transition_state, _require_merge_lifecycle_control as _require_merge_lifecycle_control, inspect_common_lock as inspect_common_lock, _archive_refusal as _archive_refusal, _archive_contamination_refusal as _archive_contamination_refusal, _archive_metadata as _archive_metadata, _env_fingerprint as _env_fingerprint, _evidence_record as _evidence_record, _write_artifact as _write_artifact, _read_bound_artifact as _read_bound_artifact, _record_process_step as _record_process_step, _run_halt as _run_halt, MergeAdmission as MergeAdmission, MergeScopeResult as MergeScopeResult, MergeCandidateGeneration as MergeCandidateGeneration, MergeBootstrapClassification as MergeBootstrapClassification
from forge_cli.engine._parser import ContractArgumentParser as ContractArgumentParser, _extract_global_options as _extract_global_options, _attach_merge_lifecycle_parser as _attach_merge_lifecycle_parser, build_parser as build_parser, _raw_top_level_command as _raw_top_level_command
from forge_cli.engine._state import TERMINAL_STATES as TERMINAL_STATES, TERMINAL_TOUCH_VERBS as TERMINAL_TOUCH_VERBS, STATE_TRANSITIONS as STATE_TRANSITIONS, TOKEN_TTL_SECONDS as TOKEN_TTL_SECONDS, _REQUIRED_MERGE_LIFECYCLE_CONTROLS as _REQUIRED_MERGE_LIFECYCLE_CONTROLS, MERGE_LIFECYCLE_CONTROLS as MERGE_LIFECYCLE_CONTROLS, _REQUIRED_ARCHIVE_RECHECK_CONTROLS as _REQUIRED_ARCHIVE_RECHECK_CONTROLS, ARCHIVE_RECHECK_CONTROLS as ARCHIVE_RECHECK_CONTROLS, _CHAIN_CAPABILITY_LOCK as _CHAIN_CAPABILITY_LOCK, _CHAIN_CAPABILITIES as _CHAIN_CAPABILITIES, CODEX_EXECUTABLE as CODEX_EXECUTABLE, FRESH_REVIEWER_EVAL_REQUEST_SCHEMA as FRESH_REVIEWER_EVAL_REQUEST_SCHEMA, REVIEW_DIRECT_PACKAGE_MAX_BYTES as REVIEW_DIRECT_PACKAGE_MAX_BYTES, REVIEW_MASTER_WINDOW_BYTES as REVIEW_MASTER_WINDOW_BYTES, REVIEW_COMPLETE_PACKAGE_REFUSAL as REVIEW_COMPLETE_PACKAGE_REFUSAL, PRODUCED_COMMIT_MISMATCH as PRODUCED_COMMIT_MISMATCH, REVIEW_INSTRUCTION as REVIEW_INSTRUCTION, REVIEW_LAUNCHER_CODE as REVIEW_LAUNCHER_CODE, GLOBAL_OPTIONS_HELP as GLOBAL_OPTIONS_HELP, ARCHIVE_CONTAMINATION as ARCHIVE_CONTAMINATION, SECRET_RULES as SECRET_RULES, PLACEHOLDER_RE as PLACEHOLDER_RE, ABORT_DISPOSITION_PRECONDITIONS as ABORT_DISPOSITION_PRECONDITIONS, _MERGE_CANDIDATE_IDENTITY_FIELDS as _MERGE_CANDIDATE_IDENTITY_FIELDS, _MERGE_BOOTSTRAP_CHILD_SOURCE as _MERGE_BOOTSTRAP_CHILD_SOURCE, _DERIVE_MERGE_SCOPE as _DERIVE_MERGE_SCOPE, _MERGE_INITIAL_INTEGRATION as _MERGE_INITIAL_INTEGRATION
from forge_cli import runtime, chain_core
from typing import Sequence, Any, Mapping
from forge_cli.policy import sha256_bytes
import copy


def _merge_conflict_path_is_canonical(path: str) -> bool:
    """Reject every path form that could alter Git's pathspec interpretation."""

    return bool(
        path
        and not path.startswith(("/", ":"))
        and all(part not in {"", ".", ".."} for part in path.split("/"))
    )


def _parse_merge_conflict_paths(raw: bytes) -> tuple[str, ...]:
    if not raw or not raw.endswith(b"\0") or len(raw) > runtime.OUTPUT_CAP_BYTES:
        raise ValueError("conflict path output is not bounded NUL-delimited data")
    fields = raw[:-1].split(b"\0")
    if not fields or any(not field for field in fields):
        raise ValueError("conflict path output contains an empty record")
    paths: list[str] = []
    for field in fields:
        try:
            path = field.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("conflict path is not UTF-8") from exc
        if not _merge_conflict_path_is_canonical(path):
            raise ValueError("conflict path is not canonical repository-relative data")
        paths.append(path)
    if len(set(paths)) != len(paths):
        raise ValueError("conflict path output contains a duplicate")
    return tuple(sorted(paths, key=lambda value: value.encode("utf-8")))


def _normalize_merge_conflict_paths(paths: Sequence[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for path in paths:
        if not isinstance(path, str) or "\0" in path:
            raise ValueError("conflict path contains invalid bytes")
        try:
            encoded = path.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("conflict path is not UTF-8") from exc
        if not encoded or not _merge_conflict_path_is_canonical(path):
            raise ValueError("conflict path is not canonical repository-relative data")
        normalized.append(path)
    if not normalized or len(set(normalized)) != len(normalized):
        raise ValueError("conflict path set is empty or contains a duplicate")
    return tuple(sorted(normalized, key=lambda value: value.encode("utf-8")))


def _merge_nonconflict_index_bytes(raw: bytes, paths: Sequence[str]) -> bytes:
    if len(raw) > runtime.OUTPUT_CAP_BYTES or (raw and not raw.endswith(b"\0")):
        raise ValueError("index baseline is not NUL-delimited")
    excluded = {path.encode("utf-8") for path in paths}
    kept: list[bytes] = []
    for record in raw[:-1].split(b"\0") if raw else ():
        header, separator, path = record.partition(b"\t")
        if not separator or not header or not path:
            raise ValueError("index baseline record is malformed")
        if path not in excluded:
            kept.append(record + b"\0")
    return b"".join(kept)


def _merge_nonconflict_status_bytes(raw: bytes, paths: Sequence[str]) -> bytes:
    if len(raw) > runtime.OUTPUT_CAP_BYTES or (raw and not raw.endswith(b"\0")):
        raise ValueError("status baseline is not NUL-delimited")
    excluded = {path.encode("utf-8") for path in paths}
    fields = raw[:-1].split(b"\0") if raw else []
    kept: list[bytes] = []
    index = 0
    while index < len(fields):
        first = fields[index]
        if len(first) < 4 or first[2:3] != b" ":
            raise ValueError("status baseline record is malformed")
        record_fields = [first]
        record_paths = [first[3:]]
        renamed = first[0:1] in {b"R", b"C"} or first[1:2] in {b"R", b"C"}
        if renamed:
            index += 1
            if index >= len(fields) or not fields[index]:
                raise ValueError("status rename/copy record is incomplete")
            record_fields.append(fields[index])
            record_paths.append(fields[index])
        if not any(path in excluded for path in record_paths):
            kept.append(b"\0".join(record_fields) + b"\0")
        index += 1
    return b"".join(kept)


def _observe_merge_conflict(
    unmerged_raw: bytes, index_raw: bytes, status_raw: bytes
) -> dict[str, Any] | None:
    """Parse an exact bounded U-set and its non-conflict byte baselines."""

    chain_core._require_merge_integration_control("conflict-continue-contract")
    try:
        paths = _parse_merge_conflict_paths(unmerged_raw)
        index_bytes = _merge_nonconflict_index_bytes(index_raw, paths)
        status_bytes = _merge_nonconflict_status_bytes(status_raw, paths)
    except ValueError:
        return None
    return {
        "authorized_paths": list(paths),
        "index_baseline_digest": sha256_bytes(index_bytes),
        "status_baseline_digest": sha256_bytes(status_bytes),
    }


def _observe_merge_post_add(
    paths: Sequence[str], unmerged_raw: bytes, index_raw: bytes, status_raw: bytes
) -> dict[str, str] | None:
    """Parse unchanged non-conflict bytes and the full post-add image."""

    chain_core._require_merge_integration_control("conflict-continue-contract")
    try:
        authorized_paths = _normalize_merge_conflict_paths(paths)
    except (TypeError, ValueError):
        return None
    if (
        any(len(raw) > runtime.OUTPUT_CAP_BYTES for raw in (unmerged_raw, index_raw, status_raw))
        or unmerged_raw != b""
    ):
        return None
    try:
        index_bytes = _merge_nonconflict_index_bytes(index_raw, ())
        status_bytes = _merge_nonconflict_status_bytes(status_raw, ())
        nonconflict_index = _merge_nonconflict_index_bytes(index_raw, authorized_paths)
        nonconflict_status = _merge_nonconflict_status_bytes(status_raw, authorized_paths)
    except ValueError:
        return None
    return {
        "index_digest": sha256_bytes(index_bytes),
        "status_digest": sha256_bytes(status_bytes),
        "nonconflict_index_digest": sha256_bytes(nonconflict_index),
        "nonconflict_status_digest": sha256_bytes(nonconflict_status),
    }


def _merge_conflict_record(
    state: Mapping[str, Any], observation: Mapping[str, Any], *,
    inflight_digest: str, output_digest: str,
) -> dict[str, Any]:
    integration = state["integration"]
    epoch = integration["epoch"]
    pre_rebase = integration["pre_rebase"]
    return {
        "operation_nonce": epoch["operation_nonce"],
        "pre_operation_head": pre_rebase["head"],
        "fetched_tip": pre_rebase["fetched_tip"],
        "generation_digest": pre_rebase["generation_digest"],
        "reflog_action": chain_core._merge_rebase_action(state),
        "authorized_paths": copy.deepcopy(observation["authorized_paths"]),
        "index_baseline_digest": observation["index_baseline_digest"],
        "status_baseline_digest": observation["status_baseline_digest"],
        "inflight_digest": inflight_digest,
        "output_digest": output_digest,
        "recorded_at": chain_core.iso_z(),
    }


def _merge_conflict_record_matches(
    state: Mapping[str, Any], observation: Mapping[str, Any]
) -> bool:
    conflict = state.get("integration", {}).get("conflict")
    pre_rebase = state.get("integration", {}).get("pre_rebase")
    epoch = state.get("integration", {}).get("epoch")
    return bool(
        isinstance(conflict, Mapping)
        and isinstance(pre_rebase, Mapping)
        and isinstance(epoch, Mapping)
        and conflict.get("operation_nonce") == epoch.get("operation_nonce")
        and conflict.get("pre_operation_head") == pre_rebase.get("head")
        and conflict.get("fetched_tip") == pre_rebase.get("fetched_tip")
        and conflict.get("generation_digest") == pre_rebase.get("generation_digest")
        and conflict.get("reflog_action") == chain_core._merge_rebase_action(state)
        and conflict.get("authorized_paths") == observation.get("authorized_paths")
        and conflict.get("index_baseline_digest")
        == observation.get("index_baseline_digest")
        and conflict.get("status_baseline_digest")
        == observation.get("status_baseline_digest")
    )


def _merge_rebase_result_failed(state: Mapping[str, Any]) -> bool:
    return chain_core._merge_rebase_result_classification(state) == "failed"
