"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
import base64
from typing import Any, Mapping
from forge_cli import chain_core
from forge_cli.engine._cli_options import _message_from_args as _message_from_args, _validate_revision9_cross_options as _validate_revision9_cross_options, render as render
from forge_cli.engine._core import commit_message_bytes as commit_message_bytes, chain_id_now as chain_id_now, promoted_tier as promoted_tier, _transition_state as _transition_state, _require_merge_lifecycle_control as _require_merge_lifecycle_control, inspect_common_lock as inspect_common_lock, _archive_refusal as _archive_refusal, _archive_contamination_refusal as _archive_contamination_refusal, _archive_metadata as _archive_metadata, _env_fingerprint as _env_fingerprint, _evidence_record as _evidence_record, _write_artifact as _write_artifact, _read_bound_artifact as _read_bound_artifact, _record_process_step as _record_process_step, _run_halt as _run_halt, MergeAdmission as MergeAdmission, MergeScopeResult as MergeScopeResult, MergeCandidateGeneration as MergeCandidateGeneration, MergeBootstrapClassification as MergeBootstrapClassification
from forge_cli.engine._parser import ContractArgumentParser as ContractArgumentParser, _extract_global_options as _extract_global_options, _attach_merge_lifecycle_parser as _attach_merge_lifecycle_parser, build_parser as build_parser, _raw_top_level_command as _raw_top_level_command
from forge_cli.engine._state import TERMINAL_STATES as TERMINAL_STATES, TERMINAL_TOUCH_VERBS as TERMINAL_TOUCH_VERBS, STATE_TRANSITIONS as STATE_TRANSITIONS, TOKEN_TTL_SECONDS as TOKEN_TTL_SECONDS, _REQUIRED_MERGE_LIFECYCLE_CONTROLS as _REQUIRED_MERGE_LIFECYCLE_CONTROLS, MERGE_LIFECYCLE_CONTROLS as MERGE_LIFECYCLE_CONTROLS, _REQUIRED_ARCHIVE_RECHECK_CONTROLS as _REQUIRED_ARCHIVE_RECHECK_CONTROLS, ARCHIVE_RECHECK_CONTROLS as ARCHIVE_RECHECK_CONTROLS, _CHAIN_CAPABILITY_LOCK as _CHAIN_CAPABILITY_LOCK, _CHAIN_CAPABILITIES as _CHAIN_CAPABILITIES, CODEX_EXECUTABLE as CODEX_EXECUTABLE, FRESH_REVIEWER_EVAL_REQUEST_SCHEMA as FRESH_REVIEWER_EVAL_REQUEST_SCHEMA, REVIEW_DIRECT_PACKAGE_MAX_BYTES as REVIEW_DIRECT_PACKAGE_MAX_BYTES, REVIEW_MASTER_WINDOW_BYTES as REVIEW_MASTER_WINDOW_BYTES, REVIEW_COMPLETE_PACKAGE_REFUSAL as REVIEW_COMPLETE_PACKAGE_REFUSAL, PRODUCED_COMMIT_MISMATCH as PRODUCED_COMMIT_MISMATCH, REVIEW_INSTRUCTION as REVIEW_INSTRUCTION, REVIEW_LAUNCHER_CODE as REVIEW_LAUNCHER_CODE, GLOBAL_OPTIONS_HELP as GLOBAL_OPTIONS_HELP, ARCHIVE_CONTAMINATION as ARCHIVE_CONTAMINATION, SECRET_RULES as SECRET_RULES, PLACEHOLDER_RE as PLACEHOLDER_RE, ABORT_DISPOSITION_PRECONDITIONS as ABORT_DISPOSITION_PRECONDITIONS, _MERGE_CANDIDATE_IDENTITY_FIELDS as _MERGE_CANDIDATE_IDENTITY_FIELDS, _MERGE_BOOTSTRAP_CHILD_SOURCE as _MERGE_BOOTSTRAP_CHILD_SOURCE, _DERIVE_MERGE_SCOPE as _DERIVE_MERGE_SCOPE, _MERGE_INITIAL_INTEGRATION as _MERGE_INITIAL_INTEGRATION
import os
import stat
from pathlib import Path
from forge_cli.policy import sha256_bytes, REGION_ORDER
from forge_cli.envelope import V2ReasonCode


def _merge_cleanup_process_record(result: chain_core.FencedProcessResult) -> dict[str, Any]:
    return {
        **result.evidence(),
        "output_base64": base64.b64encode(result.output).decode("ascii"),
    }


def _read_merge_git_metadata(path: Path, *, cap: int = 4096) -> bytes:
    """Read one no-follow, owner-controlled Git metadata file under a fixed cap."""

    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.geteuid()
            or opened.st_size < 0
            or opened.st_size > cap
        ):
            raise OSError("Git metadata is not a bounded owner-controlled regular file")
        raw = os.read(descriptor, cap + 1)
        if len(raw) != opened.st_size:
            raise OSError("Git metadata changed while it was read")
        return raw
    finally:
        os.close(descriptor)


def _merge_cleanup_remote_fetch_observation(
    result: chain_core.FencedProcessResult,
    destination_ref: str,
    git_dir: Path,
) -> dict[str, Any]:
    process = _merge_cleanup_process_record(result)
    complete = bool(
        result.authorized is True
        and type(result.returncode) is int
        and result.launch_failed is False
        and result.timed_out is False
        and result.output_limit is False
        and result.group_survived is False
    )
    exists: bool | None = None
    oid: str | None = None
    raw: bytes | None = None
    if complete and result.returncode == 0:
        try:
            candidate_raw = _read_merge_git_metadata(
                git_dir / "FETCH_HEAD", cap=chain_core.MERGE_SCOPE_BINDING_CAP_BYTES
            )
        except OSError:
            candidate_raw = None
        if (
            isinstance(candidate_raw, bytes)
            and len(candidate_raw) <= chain_core.MERGE_SCOPE_BINDING_CAP_BYTES
        ):
            raw = candidate_raw
            exists, oid = chain_core._merge_cleanup_fetch_head_bytes(raw)
    elif (
        complete
        and result.returncode != 0
        and chain_core._merge_cleanup_process_output(process)
        == f"fatal: couldn't find remote ref {destination_ref}\n".encode("utf-8")
    ):
        exists = False
    return {
        "exists": exists,
        "oid": oid,
        "fetch_head_base64": (
            base64.b64encode(raw).decode("ascii") if raw is not None else None
        ),
        "fetch_head_digest": sha256_bytes(raw) if raw is not None else None,
    }


def _parse_plugin_manifest(raw: bytes) -> str:
    """Return the committed plugin-schema default branch, or fail closed."""

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("committed .forge-manifest is not UTF-8") from exc
    if not text.endswith("\n") or "\r" in text or "\x00" in text:
        raise ValueError("committed .forge-manifest has malformed line encoding")
    lines = text.splitlines()
    if len(lines) < 6:
        raise ValueError("committed .forge-manifest is incomplete")
    fixed_names = (
        "forge_version",
        "plugin_ref",
        "installed",
        "project_name",
        "default_branch",
        "init_completed",
    )
    fixed: dict[str, str] = {}
    for index, name in enumerate(fixed_names):
        prefix = f"{name}: "
        if not lines[index].startswith(prefix):
            raise ValueError("committed .forge-manifest is not plugin schema")
        value = lines[index][len(prefix) :]
        if not value:
            raise ValueError("committed .forge-manifest has an empty fixed field")
        fixed[name] = value
    remainder = lines[len(fixed_names) :]
    history_rows = [
        row for row in remainder if row.startswith("history_mutation_mode:")
    ]
    if history_rows:
        if (
            len(history_rows) != 1
            or remainder[0] != history_rows[0]
            or history_rows[0]
            not in {
                "history_mutation_mode: legacy-v1",
                "history_mutation_mode: forge-verbs-v1",
            }
        ):
            raise ValueError("committed .forge-manifest activation field is invalid")
        remainder = remainder[1:]
    if (
        fixed["forge_version"] != "1"
        or fixed["init_completed"] != "true"
        or remainder != [f"region: {name}" for name in REGION_ORDER]
    ):
        raise ValueError("committed .forge-manifest is not an initialized plugin schema")
    default_branch = fixed["default_branch"]
    if (
        not default_branch
        or default_branch.startswith("-")
        or any(character in default_branch for character in "\r\n\x00")
    ):
        raise ValueError("committed .forge-manifest default branch is invalid")
    return default_branch


def _parse_history_mutation_mode(raw: bytes) -> str:
    """Return DM-015's canonical committed mode, rejecting every invalid form."""

    _parse_plugin_manifest(raw)
    text = raw.decode("utf-8")
    rows = [
        row
        for row in text.splitlines()
        if row.startswith("history_mutation_mode:")
    ]
    if not rows:
        return "legacy-v1"
    # ``_parse_plugin_manifest`` already proved singleton placement and value.
    return rows[0].split(": ", 1)[1]


def _absolute_git_path(repository: chain_core.Repository, argument: str) -> Path:
    for argv in (
        ["rev-parse", "--path-format=absolute", argument],
        ["rev-parse", argument],
    ):
        process = repository.git(argv, check=False)
        rendered = os.fsdecode(process.stdout.rstrip(b"\n"))
        if (
            process.returncode != 0
            or not rendered
            or "\n" in rendered
            or "\r" in rendered
        ):
            continue
        candidate = Path(rendered)
        if not candidate.is_absolute():
            candidate = repository.root / candidate
        try:
            return candidate.resolve(strict=True)
        except OSError:
            continue
    raise OSError(f"Git did not resolve {argument}")


def _registered_worktrees(repository: chain_core.Repository) -> tuple[dict[str, str], ...]:
    process = repository.git(["worktree", "list", "--porcelain", "-z"])
    return chain_core._parse_registered_worktrees(process.stdout)


def _merge_worktree_status(
    repository: chain_core.Repository, git_dir: Path, *, verb: str = "merge start"
) -> bytes:
    try:
        status = repository.git(
            ["status", "--porcelain=v1", "--untracked-files=all"],
            check=False,
        )
    except OSError as exc:
        raise chain_core._merge_refusal(
            V2ReasonCode.WORKTREE_INVALID,
            f"forge: {verb} refused — source worktree status is unavailable",
            expected="a complete Git status observation",
            observed=str(exc),
            remediation="inspect the recorded worktree and retry",
        ) from exc
    if status.returncode != 0:
        raise chain_core._merge_refusal(
            V2ReasonCode.WORKTREE_INVALID,
            f"forge: {verb} refused — source worktree status is unavailable",
            expected="a complete Git status observation",
            observed=(
                status.stderr.decode("utf-8", "replace").strip()
                or "git status failed"
            ),
            remediation="inspect the recorded worktree and retry",
        )
    operation_markers = (
        "MERGE_HEAD",
        "CHERRY_PICK_HEAD",
        "REVERT_HEAD",
        "BISECT_LOG",
        "rebase-apply",
        "rebase-merge",
        "sequencer",
    )
    if status.stdout or any((git_dir / marker).exists() for marker in operation_markers):
        raise chain_core._merge_refusal(
            V2ReasonCode.DIRTY_WORKTREE,
            f"forge: {verb} refused — source worktree is not clean",
            expected="zero status bytes and no in-progress Git operation",
            observed=(
                status.stdout.decode("utf-8", "replace")
                or "in-progress Git operation"
            ),
            remediation="restore the source worktree to exact clean status",
        )
    return status.stdout


def _merge_owned_rebase_metadata(state: Mapping[str, Any]) -> bool:
    """Prove that the sole live rebase directory belongs to this chain epoch."""

    chain_core._require_merge_integration_control("rebase-result-proof")
    integration = state.get("integration")
    pre_rebase = (
        integration.get("pre_rebase") if isinstance(integration, Mapping) else None
    )
    intent = integration.get("intent") if isinstance(integration, Mapping) else None
    action = chain_core._merge_rebase_action(state)
    if (
        not isinstance(pre_rebase, Mapping)
        or not isinstance(intent, Mapping)
        or action is None
        or intent.get("operation") not in {"rebase", "continue", "rebase-result"}
        or intent.get("operation_nonce")
        != state.get("integration", {}).get("epoch", {}).get("operation_nonce")
        or intent.get("branch") != state.get("branch")
        or intent.get("generation_digest") != pre_rebase.get("generation_digest")
        or intent.get("pre_operation_head") != pre_rebase.get("head")
        or intent.get("fetched_tip") != pre_rebase.get("fetched_tip")
        or intent.get("reflog_action") != action
    ):
        return False
    git_dir = Path(str(state.get("worktree", {}).get("git_dir", "")))
    live: list[Path] = []
    for name in ("rebase-merge", "rebase-apply"):
        path = git_dir / name
        try:
            os.lstat(path)
        except FileNotFoundError:
            continue
        except OSError:
            return False
        live.append(path)
    if len(live) != 1:
        return False
    for name in (
        "MERGE_HEAD",
        "CHERRY_PICK_HEAD",
        "REVERT_HEAD",
        "BISECT_LOG",
        "sequencer",
    ):
        try:
            os.lstat(git_dir / name)
        except FileNotFoundError:
            continue
        except OSError:
            return False
        return False
    try:
        directory = os.lstat(live[0])
        if not stat.S_ISDIR(directory.st_mode) or directory.st_uid != os.geteuid():
            return False
        head_name = _read_merge_git_metadata(live[0] / "head-name")
        original_head = _read_merge_git_metadata(live[0] / "orig-head")
        onto = _read_merge_git_metadata(live[0] / "onto")
    except OSError:
        return False
    return bool(
        head_name == f"{state.get('branch')}\n".encode("utf-8")
        and original_head == f"{pre_rebase.get('head')}\n".encode("ascii")
        and onto == f"{pre_rebase.get('fetched_tip')}\n".encode("ascii")
    )


def _require_loud_merge_recovery_mode(
    state: Mapping[str, Any],
    *,
    continue_rebase: bool,
    abort_rebase: bool,
) -> None:
    """Refuse explicit conflict modes outside the exact owned conflict tuple."""

    chain_core._require_merge_integration_control("loud-recover-flags")
    if not (continue_rebase or abort_rebase):
        return
    actual = str(state.get("state"))
    if actual == "rebase_conflict" and _merge_owned_rebase_metadata(state):
        return
    raise chain_core._merge_refusal(
        V2ReasonCode.STATE_PRECONDITION,
        (
            "forge: merge recover refused — explicit conflict recovery requires "
            f"the exact owned rebase_conflict state (actual state: {actual})"
        ),
        expected="the exact owned rebase_conflict state and Git metadata tuple",
        observed=actual,
        remediation=f"forge merge recover --chain-id {state.get('chain_id')}",
        chain=state,
    )
