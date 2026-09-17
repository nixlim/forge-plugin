"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
import copy
import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence
from forge_cli import chain_core, runtime
from forge_cli.engine._cli_options import _message_from_args as _message_from_args, _validate_revision9_cross_options as _validate_revision9_cross_options, render as render
from forge_cli.engine._core import commit_message_bytes as commit_message_bytes, chain_id_now as chain_id_now, promoted_tier as promoted_tier, _transition_state as _transition_state, _require_merge_lifecycle_control as _require_merge_lifecycle_control, inspect_common_lock as inspect_common_lock, _archive_refusal as _archive_refusal, _archive_contamination_refusal as _archive_contamination_refusal, _archive_metadata as _archive_metadata, _env_fingerprint as _env_fingerprint, _evidence_record as _evidence_record, _write_artifact as _write_artifact, _read_bound_artifact as _read_bound_artifact, _record_process_step as _record_process_step, _run_halt as _run_halt, MergeAdmission as MergeAdmission, MergeScopeResult as MergeScopeResult, MergeCandidateGeneration as MergeCandidateGeneration, MergeBootstrapClassification as MergeBootstrapClassification
from forge_cli.engine._parser import ContractArgumentParser as ContractArgumentParser, _extract_global_options as _extract_global_options, _attach_merge_lifecycle_parser as _attach_merge_lifecycle_parser, build_parser as build_parser, _raw_top_level_command as _raw_top_level_command
from forge_cli.engine._state import TERMINAL_STATES as TERMINAL_STATES, TERMINAL_TOUCH_VERBS as TERMINAL_TOUCH_VERBS, STATE_TRANSITIONS as STATE_TRANSITIONS, TOKEN_TTL_SECONDS as TOKEN_TTL_SECONDS, _REQUIRED_MERGE_LIFECYCLE_CONTROLS as _REQUIRED_MERGE_LIFECYCLE_CONTROLS, MERGE_LIFECYCLE_CONTROLS as MERGE_LIFECYCLE_CONTROLS, _REQUIRED_ARCHIVE_RECHECK_CONTROLS as _REQUIRED_ARCHIVE_RECHECK_CONTROLS, ARCHIVE_RECHECK_CONTROLS as ARCHIVE_RECHECK_CONTROLS, _CHAIN_CAPABILITY_LOCK as _CHAIN_CAPABILITY_LOCK, _CHAIN_CAPABILITIES as _CHAIN_CAPABILITIES, CODEX_EXECUTABLE as CODEX_EXECUTABLE, FRESH_REVIEWER_EVAL_REQUEST_SCHEMA as FRESH_REVIEWER_EVAL_REQUEST_SCHEMA, REVIEW_DIRECT_PACKAGE_MAX_BYTES as REVIEW_DIRECT_PACKAGE_MAX_BYTES, REVIEW_MASTER_WINDOW_BYTES as REVIEW_MASTER_WINDOW_BYTES, REVIEW_COMPLETE_PACKAGE_REFUSAL as REVIEW_COMPLETE_PACKAGE_REFUSAL, PRODUCED_COMMIT_MISMATCH as PRODUCED_COMMIT_MISMATCH, REVIEW_INSTRUCTION as REVIEW_INSTRUCTION, REVIEW_LAUNCHER_CODE as REVIEW_LAUNCHER_CODE, GLOBAL_OPTIONS_HELP as GLOBAL_OPTIONS_HELP, ARCHIVE_CONTAMINATION as ARCHIVE_CONTAMINATION, SECRET_RULES as SECRET_RULES, PLACEHOLDER_RE as PLACEHOLDER_RE, ABORT_DISPOSITION_PRECONDITIONS as ABORT_DISPOSITION_PRECONDITIONS, _MERGE_CANDIDATE_IDENTITY_FIELDS as _MERGE_CANDIDATE_IDENTITY_FIELDS, _MERGE_BOOTSTRAP_CHILD_SOURCE as _MERGE_BOOTSTRAP_CHILD_SOURCE, _DERIVE_MERGE_SCOPE as _DERIVE_MERGE_SCOPE, _MERGE_INITIAL_INTEGRATION as _MERGE_INITIAL_INTEGRATION


def _decode_merge_bootstrap_result(
    raw: chain_core.FencedProcessResult,
    *,
    run_bound: bool,
    fetch_argv: Sequence[str] | None = None,
    worktree: Path | None = None,
    candidate_head: str | None = None,
    environment_digest: str | None = None,
) -> chain_core.FencedProcessResult:
    """Authenticate the bounded protocol and expose one composite result."""

    zero_digest = hashlib.sha256(b"").hexdigest()
    if (
        raw.returncode != 0
        or raw.launch_failed
        or raw.timed_out
        or raw.output_limit
        or raw.group_survived
    ):
        return dataclasses.replace(raw, output=b"", output_digest=zero_digest)
    try:
        protocol = json.loads(raw.output)
        if (
            not isinstance(protocol, dict)
            or set(protocol)
            != {
                "schema",
                "constituent_order",
                "environment_digest",
                "resolved_tip",
                "fetch",
                "scope",
                "scope_changed_paths",
                "full_patch",
            }
            or protocol.get("schema") != "forge-bootstrap-composite-result/1"
        ):
            raise ValueError("composite result envelope is malformed")
        observed_environment_digest = protocol.get("environment_digest")
        if (
            not isinstance(observed_environment_digest, str)
            or chain_core.SHA256_RE.fullmatch(observed_environment_digest) is None
            or (
                environment_digest is not None
                and observed_environment_digest != environment_digest
            )
        ):
            raise ValueError("composite environment diverges from its exact contract")

        def constituent(value: Any, label: str) -> dict[str, Any]:
            if not isinstance(value, dict) or set(value) != {
                "argv",
                "exit",
                "output_digest",
                "stderr_digest",
                "launch_failed",
                "output_limit_exceeded",
            }:
                raise ValueError(f"{label} result is malformed")
            argv = value.get("argv")
            if (
                not isinstance(argv, list)
                or not argv
                or not all(
                    isinstance(item, str) and "\x00" not in item for item in argv
                )
                or (
                    value.get("exit") is not None
                    and (
                        not isinstance(value.get("exit"), int)
                        or isinstance(value.get("exit"), bool)
                    )
                )
                or any(
                    not isinstance(value.get(name), str)
                    or chain_core.SHA256_RE.fullmatch(str(value[name])) is None
                    for name in ("output_digest", "stderr_digest")
                )
                or type(value.get("launch_failed")) is not bool
                or type(value.get("output_limit_exceeded")) is not bool
            ):
                raise ValueError(f"{label} result fields are malformed")
            return value

        def passed(record: Mapping[str, Any]) -> bool:
            return bool(
                record.get("exit") == 0
                and record.get("launch_failed") is False
                and record.get("output_limit_exceeded") is False
            )

        order = protocol.get("constituent_order")
        if not isinstance(order, list) or not all(
            isinstance(label, str) for label in order
        ):
            raise ValueError("composite constituent order is malformed")
        fetch = constituent(protocol.get("fetch"), "fetch")
        if fetch_argv is not None and fetch.get("argv") != list(fetch_argv):
            raise ValueError("composite fetch argv diverges from admission")
        resolved_tip = protocol.get("resolved_tip")
        scope: dict[str, Any] | None = None
        patch: dict[str, Any] | None = None
        records: list[dict[str, Any]] = [fetch]
        expected_order = ["fetch"]

        if passed(fetch):
            if (
                not isinstance(resolved_tip, str)
                or chain_core.COMMIT_RE.fullmatch(resolved_tip) is None
            ):
                raise ValueError("composite resolved tip is malformed")
            if worktree is None or candidate_head is None:
                raise ValueError("composite argv context is unavailable")
            if run_bound:
                expected_order.append("name-status")
                scope = constituent(protocol.get("scope"), "name-status")
                records.append(scope)
                if scope.get("argv") != chain_core._merge_scope_argv(
                    worktree, resolved_tip, candidate_head
                ):
                    raise ValueError("composite name-status argv diverges")
                paths = protocol.get("scope_changed_paths")
                if passed(scope):
                    _batch, _builders, journal = runtime._coordination_modules()
                    if not chain_core._valid_sorted_unique_strings(paths) or not all(
                        journal._valid_scope_item(path) for path in paths
                    ):
                        raise ValueError("scope changed-path set is malformed")
                elif paths is not None:
                    raise ValueError("failed name-status invented changed paths")
            elif (
                protocol.get("scope") is not None
                or protocol.get("scope_changed_paths") is not None
            ):
                raise ValueError("unbound composite invented a scope constituent")

            if scope is None or passed(scope):
                expected_order.append("full-patch")
                patch = constituent(protocol.get("full_patch"), "full-patch")
                records.append(patch)
                if patch.get("argv") != chain_core._merge_full_patch_argv(
                    worktree, resolved_tip, candidate_head
                ):
                    raise ValueError("composite full-patch argv diverges")
            elif protocol.get("full_patch") is not None:
                raise ValueError("full-patch ran after failed name-status")
        else:
            if resolved_tip is not None:
                raise ValueError("failed fetch invented a resolved tip")
            if (
                protocol.get("scope") is not None
                or protocol.get("scope_changed_paths") is not None
                or protocol.get("full_patch") is not None
            ):
                raise ValueError("a constituent ran after failed fetch")

        if order != expected_order:
            raise ValueError("composite constituent order diverges")
        complete = bool(
            expected_order[-1] == "full-patch" and all(passed(record) for record in records)
        )
        slot_digest = str(scope["output_digest"]) if scope is not None else zero_digest
        return dataclasses.replace(
            raw,
            returncode=(
                0
                if complete
                else next(
                    (
                        int(record["exit"])
                        for record in records
                        if isinstance(record.get("exit"), int)
                        and record.get("exit") != 0
                    ),
                    1,
                )
            ),
            output=b"",
            output_digest=slot_digest,
            output_limit=any(
                record.get("output_limit_exceeded") is True for record in records
            ),
            launch_failed=any(
                record.get("launch_failed") is True for record in records
            ),
            metadata=copy.deepcopy(protocol),
        )
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        return dataclasses.replace(
            raw,
            returncode=1,
            output=b"",
            output_digest=zero_digest,
            launch_failed=True,
            metadata={"protocol_error": str(exc)},
        )
