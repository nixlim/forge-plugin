"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
from typing import Any, Callable, Mapping
from forge_cli import chain_core
from forge_cli.engine._cli_options import _message_from_args as _message_from_args, _validate_revision9_cross_options as _validate_revision9_cross_options, render as render
from forge_cli.engine._core import commit_message_bytes as commit_message_bytes, chain_id_now as chain_id_now, promoted_tier as promoted_tier, _transition_state as _transition_state, _require_merge_lifecycle_control as _require_merge_lifecycle_control, inspect_common_lock as inspect_common_lock, _archive_refusal as _archive_refusal, _archive_contamination_refusal as _archive_contamination_refusal, _archive_metadata as _archive_metadata, _env_fingerprint as _env_fingerprint, _evidence_record as _evidence_record, _write_artifact as _write_artifact, _read_bound_artifact as _read_bound_artifact, _record_process_step as _record_process_step, _run_halt as _run_halt, MergeAdmission as MergeAdmission, MergeScopeResult as MergeScopeResult, MergeCandidateGeneration as MergeCandidateGeneration, MergeBootstrapClassification as MergeBootstrapClassification
from forge_cli.engine._parser import ContractArgumentParser as ContractArgumentParser, _extract_global_options as _extract_global_options, _attach_merge_lifecycle_parser as _attach_merge_lifecycle_parser, build_parser as build_parser, _raw_top_level_command as _raw_top_level_command
from forge_cli.engine._state import TERMINAL_STATES as TERMINAL_STATES, TERMINAL_TOUCH_VERBS as TERMINAL_TOUCH_VERBS, STATE_TRANSITIONS as STATE_TRANSITIONS, TOKEN_TTL_SECONDS as TOKEN_TTL_SECONDS, _REQUIRED_MERGE_LIFECYCLE_CONTROLS as _REQUIRED_MERGE_LIFECYCLE_CONTROLS, MERGE_LIFECYCLE_CONTROLS as MERGE_LIFECYCLE_CONTROLS, _REQUIRED_ARCHIVE_RECHECK_CONTROLS as _REQUIRED_ARCHIVE_RECHECK_CONTROLS, ARCHIVE_RECHECK_CONTROLS as ARCHIVE_RECHECK_CONTROLS, _CHAIN_CAPABILITY_LOCK as _CHAIN_CAPABILITY_LOCK, _CHAIN_CAPABILITIES as _CHAIN_CAPABILITIES, CODEX_EXECUTABLE as CODEX_EXECUTABLE, FRESH_REVIEWER_EVAL_REQUEST_SCHEMA as FRESH_REVIEWER_EVAL_REQUEST_SCHEMA, REVIEW_DIRECT_PACKAGE_MAX_BYTES as REVIEW_DIRECT_PACKAGE_MAX_BYTES, REVIEW_MASTER_WINDOW_BYTES as REVIEW_MASTER_WINDOW_BYTES, REVIEW_COMPLETE_PACKAGE_REFUSAL as REVIEW_COMPLETE_PACKAGE_REFUSAL, PRODUCED_COMMIT_MISMATCH as PRODUCED_COMMIT_MISMATCH, REVIEW_INSTRUCTION as REVIEW_INSTRUCTION, REVIEW_LAUNCHER_CODE as REVIEW_LAUNCHER_CODE, GLOBAL_OPTIONS_HELP as GLOBAL_OPTIONS_HELP, ARCHIVE_CONTAMINATION as ARCHIVE_CONTAMINATION, SECRET_RULES as SECRET_RULES, PLACEHOLDER_RE as PLACEHOLDER_RE, ABORT_DISPOSITION_PRECONDITIONS as ABORT_DISPOSITION_PRECONDITIONS, _MERGE_CANDIDATE_IDENTITY_FIELDS as _MERGE_CANDIDATE_IDENTITY_FIELDS, _MERGE_BOOTSTRAP_CHILD_SOURCE as _MERGE_BOOTSTRAP_CHILD_SOURCE, _DERIVE_MERGE_SCOPE as _DERIVE_MERGE_SCOPE, _MERGE_INITIAL_INTEGRATION as _MERGE_INITIAL_INTEGRATION
import dataclasses
import os
from pathlib import Path
from forge_cli.envelope import FrozenError, REVISION9_OUTPUT_SCHEMA, Refusal
import copy
import stat
from forge_cli.policy import sha256_bytes


def _merge_scope_child_result(
    fence: chain_core.PublishedLockRecord,
    result: chain_core.FencedProcessResult,
    *,
    resolved_tip: str,
) -> dict[str, Any]:
    record = fence.record
    return {
        "operation": record["operation"],
        "intent_digest": record["intent_digest"],
        "inflight_digest": fence.digest,
        "host": record["host"],
        "pid": record["pid"],
        "pgid": record["pgid"],
        "exit": result.returncode,
        "output_digest": result.output_digest,
        "launch_failed": result.launch_failed,
        "timed_out": result.timed_out,
        "output_limit_exceeded": result.output_limit,
        "group_dead_at": chain_core.iso_z(),
        "resolved_tip": resolved_tip,
        "recorded_at": chain_core.iso_z(),
    }


@dataclasses.dataclass(frozen=True)
class MergeScopeBindingInspection:
    """One of FR-236's four admissible deterministic-name topologies."""

    topology: str
    canonical: chain_core.PublishedLockRecord | None
    temporary: chain_core.PublishedLockRecord | None


def _unlink_merge_scope_temporary_at(
    parent: int,
    name: str,
    absolute_path: Path,
    expected: chain_core.PublishedLockRecord,
    validator: Callable[[Any], dict[str, Any]],
) -> None:
    """Remove only the strict-valid recorded two-link publication inode."""

    chain_core._require_common_lock_control("release-identity-revalidation")
    current = chain_core._revalidate_record_at(
        parent, name, absolute_path, expected, validator
    )
    if current.links != 2:
        raise OSError("scope-fetch temporary no longer has exactly two links")
    os.unlink(name, dir_fd=parent)


def _classify_merge_scope_binding_at(
    store: chain_core.MergeChainStore,
    state: Mapping[str, Any],
    parent: int,
    *,
    fetch_intent_digest: str,
    scope_request: Mapping[str, Any] | None,
    fence: chain_core.PublishedLockRecord,
    result: chain_core.FencedProcessResult | None = None,
) -> MergeScopeBindingInspection:
    chain_id = str(state["chain_id"])
    canonical_name, temporary_name, _canonical_path, _temporary_path = (
        chain_core._merge_scope_binding_names(chain_id, fetch_intent_digest, fence)
    )
    artifact_root = store.root / chain_id
    validator = chain_core._merge_scope_binding_validator(
        state,
        fetch_intent_digest=fetch_intent_digest,
        scope_request=scope_request,
        fence=fence,
        result=result,
    )
    canonical = chain_core._record_at_if_present(
        parent, canonical_name, artifact_root / canonical_name, validator
    )
    temporary = chain_core._record_at_if_present(
        parent, temporary_name, artifact_root / temporary_name, validator
    )
    for record in (canonical, temporary):
        if record is not None and (
            record.device != record.record["publication"]["device"]
            or record.inode != record.record["publication"]["inode"]
        ):
            raise OSError("scope-fetch publication identity does not match its inode")
    if canonical is None and temporary is None:
        return MergeScopeBindingInspection("absent", None, None)
    if canonical is None and temporary is not None and temporary.links == 1:
        return MergeScopeBindingInspection("temporary-one-link", None, temporary)
    if (
        canonical is not None
        and temporary is not None
        and canonical.links == temporary.links == 2
        and chain_core._same_published_record(canonical, temporary)
    ):
        return MergeScopeBindingInspection("same-inode-two-link", canonical, temporary)
    if canonical is not None and canonical.links == 1 and temporary is None:
        return MergeScopeBindingInspection("canonical-one-link", canonical, None)
    raise OSError("scope-fetch deterministic names have an inadmissible topology")


def _classify_merge_scope_binding(
    store: chain_core.MergeChainStore,
    state: Mapping[str, Any],
    *,
    fetch_intent_digest: str,
    scope_request: Mapping[str, Any] | None,
    fence: chain_core.PublishedLockRecord,
) -> MergeScopeBindingInspection:
    """Classify the deterministic sidecar names without changing either name."""

    chain_core._require_merge_integration_control("scope-sidecar-recovery")
    chain_id = str(state["chain_id"])
    canonical_name, _temporary, _path, _temporary_path = (
        chain_core._merge_scope_binding_names(chain_id, fetch_intent_digest, fence)
    )
    try:
        with store.artifact_parent_descriptor(
            chain_id, canonical_name, create=False
        ) as (parent, _name):
            return _classify_merge_scope_binding_at(
                store,
                state,
                parent,
                fetch_intent_digest=fetch_intent_digest,
                scope_request=scope_request,
                fence=fence,
            )
    except FileNotFoundError:
        return MergeScopeBindingInspection("absent", None, None)
    except FrozenError:
        raise
    except (OSError, ValueError, Refusal) as exc:
        raise FrozenError(
            "merge scope-fetch sidecar topology is divergent",
            chain_id=chain_id,
            observed=str(exc),
            schema=REVISION9_OUTPUT_SCHEMA,
        ) from exc


def _resume_merge_scope_binding(
    store: chain_core.MergeChainStore,
    state: Mapping[str, Any],
    *,
    fetch_intent_digest: str,
    scope_request: Mapping[str, Any] | None,
    fence: chain_core.PublishedLockRecord,
) -> dict[str, Any] | None:
    """Resume only FR-236's admitted link/unlink publication suffix."""

    chain_core._require_merge_integration_control("scope-sidecar-recovery")
    chain_id = str(state["chain_id"])
    canonical_name, temporary_name, _path, _temporary_path = (
        chain_core._merge_scope_binding_names(chain_id, fetch_intent_digest, fence)
    )
    artifact_root = store.root / chain_id
    validator = chain_core._merge_scope_binding_validator(
        state,
        fetch_intent_digest=fetch_intent_digest,
        scope_request=scope_request,
        fence=fence,
    )
    try:
        with store.artifact_parent_descriptor(
            chain_id, canonical_name, create=False
        ) as (parent, _name):
            inspection = _classify_merge_scope_binding_at(
                store,
                state,
                parent,
                fetch_intent_digest=fetch_intent_digest,
                scope_request=scope_request,
                fence=fence,
            )
            if inspection.topology == "absent":
                return None
            if inspection.topology == "temporary-one-link":
                assert inspection.temporary is not None
                current_temp = chain_core._revalidate_record_at(
                    parent,
                    temporary_name,
                    artifact_root / temporary_name,
                    inspection.temporary,
                    validator,
                )
                if current_temp.links != 1:
                    raise OSError("scope-fetch temporary link count changed")
                chain_core._publish_no_replace_link(
                    parent, temporary_name, parent, canonical_name
                )
                os.fsync(parent)
                inspection = _classify_merge_scope_binding_at(
                    store,
                    state,
                    parent,
                    fetch_intent_digest=fetch_intent_digest,
                    scope_request=scope_request,
                    fence=fence,
                )
            if inspection.topology == "same-inode-two-link":
                assert inspection.temporary is not None
                _unlink_merge_scope_temporary_at(
                    parent,
                    temporary_name,
                    artifact_root / temporary_name,
                    inspection.temporary,
                    validator,
                )
                os.fsync(parent)
                inspection = _classify_merge_scope_binding_at(
                    store,
                    state,
                    parent,
                    fetch_intent_digest=fetch_intent_digest,
                    scope_request=scope_request,
                    fence=fence,
                )
            if inspection.topology != "canonical-one-link" or inspection.canonical is None:
                raise OSError("scope-fetch publication did not reach its final topology")
            return copy.deepcopy(inspection.canonical.record)
    except FrozenError:
        raise
    except (OSError, ValueError, Refusal) as exc:
        raise FrozenError(
            "merge scope-fetch sidecar recovery is divergent",
            chain_id=chain_id,
            observed=str(exc),
            schema=REVISION9_OUTPUT_SCHEMA,
        ) from exc


def _publish_merge_scope_binding(
    store: chain_core.MergeChainStore,
    state: Mapping[str, Any],
    *,
    fetch_intent_digest: str,
    scope_request: Mapping[str, Any] | None,
    remote_tip: str,
    fence: chain_core.PublishedLockRecord,
    result: chain_core.FencedProcessResult,
) -> dict[str, Any]:
    """Publish FR-231's inode-bound immutable sidecar while the fence lives."""

    chain_core._require_merge_integration_control("post-fetch-scope-proof")
    chain_core._require_merge_integration_control("composite-bootstrap-streaming")
    chain_id = str(state["chain_id"])
    candidate_head = str(state["integration"]["intent"]["pre_fetch_head"])
    worktree = Path(str(state["worktree"]["path"]))
    command = (
        chain_core._merge_scope_argv(worktree, remote_tip, candidate_head)
        if scope_request is not None
        else None
    )
    full_patch_command = chain_core._merge_full_patch_argv(
        worktree, remote_tip, candidate_head
    )
    metadata = result.metadata
    if (
        not isinstance(metadata, Mapping)
        or not isinstance(metadata.get("full_patch"), Mapping)
        or chain_core.SHA256_RE.fullmatch(
            str(metadata["full_patch"].get("output_digest", ""))
        )
        is None
    ):
        raise ValueError("composite full-patch digest is unavailable")
    canonical_name = (
        f"scope-fetch-{fetch_intent_digest}-{fence.digest}.json"
    )
    relative = f".forge/chains/{chain_id}/{canonical_name}"
    temporary_name = f"{canonical_name}.tmp-{fence.record['nonce']}"
    temporary_relative = f"{relative}.tmp-{fence.record['nonce']}"
    with store.artifact_parent_descriptor(
        chain_id, canonical_name, create=True
    ) as (parent, name):
        for candidate_name in (name, temporary_name):
            try:
                os.stat(candidate_name, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                continue
            raise FileExistsError(candidate_name)
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=parent,
        )
        opened = os.fstat(descriptor)
        try:
            if not stat.S_ISREG(opened.st_mode) or opened.st_uid != os.geteuid():
                raise OSError("scope-fetch temporary is not owner-controlled and regular")
            os.fchmod(descriptor, 0o600)
            body = {
                "schema": "forge-run-scope-fetch-binding/2",
                "chain_id": chain_id,
                "fetch_intent_digest": fetch_intent_digest,
                "scope_request_digest": (
                    sha256_bytes(chain_core.canonical_bytes(dict(scope_request)))
                    if scope_request is not None
                    else None
                ),
                "candidate_head": candidate_head,
                "remote_tip": remote_tip,
                "command_template_digest": (
                    scope_request["command_template_digest"]
                    if scope_request is not None
                    else None
                ),
                "command_digest": (
                    sha256_bytes(chain_core.canonical_bytes(command))
                    if command is not None
                    else None
                ),
                "full_patch_command_digest": sha256_bytes(
                    chain_core.canonical_bytes(full_patch_command)
                ),
                "full_patch_output_digest": str(
                    metadata["full_patch"]["output_digest"]
                ),
                "environment_digest": sha256_bytes(
                    chain_core.canonical_bytes(chain_core._merge_scope_environment_contract())
                ),
                "publication": {
                    "canonical_path": relative,
                    "temporary_path": temporary_relative,
                    "device": opened.st_dev,
                    "inode": opened.st_ino,
                },
                "retained_inflight": chain_core._merge_retained_inflight(fence),
                "child_result": _merge_scope_child_result(
                    fence, result, resolved_tip=remote_tip
                ),
                "recorded_at": chain_core.iso_z(),
            }
            record = {**body, "digest": sha256_bytes(chain_core.canonical_bytes(body))}
            validated = chain_core._validate_merge_scope_fetch_binding(record)
            encoded = chain_core.canonical_bytes(validated)
            chain_core._write_all(descriptor, encoded)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        temporary = chain_core._read_owned_record_at(
            parent,
            temporary_name,
            store.artifact_dir(chain_id) / temporary_name,
            chain_core._validate_merge_scope_fetch_binding,
            cap=chain_core.MERGE_SCOPE_BINDING_CAP_BYTES,
        )
        if (
            temporary.device != opened.st_dev
            or temporary.inode != opened.st_ino
            or temporary.links != 1
        ):
            raise OSError("scope-fetch temporary identity changed")
        chain_core._publish_no_replace_link(parent, temporary_name, parent, name)
        os.fsync(parent)
        canonical = chain_core._read_owned_record_at(
            parent,
            name,
            store.artifact_dir(chain_id) / name,
            chain_core._validate_merge_scope_fetch_binding,
            cap=chain_core.MERGE_SCOPE_BINDING_CAP_BYTES,
        )
        linked_temp = chain_core._read_owned_record_at(
            parent,
            temporary_name,
            store.artifact_dir(chain_id) / temporary_name,
            chain_core._validate_merge_scope_fetch_binding,
            cap=chain_core.MERGE_SCOPE_BINDING_CAP_BYTES,
        )
        if (
            not chain_core._same_published_record(canonical, linked_temp)
            or canonical.links != 2
            or linked_temp.links != 2
        ):
            raise OSError("scope-fetch published names do not share two links")
        _unlink_merge_scope_temporary_at(
            parent,
            temporary_name,
            store.artifact_dir(chain_id) / temporary_name,
            linked_temp,
            chain_core._validate_merge_scope_fetch_binding,
        )
        os.fsync(parent)
        final = chain_core._read_owned_record_at(
            parent,
            name,
            store.artifact_dir(chain_id) / name,
            chain_core._validate_merge_scope_fetch_binding,
            cap=chain_core.MERGE_SCOPE_BINDING_CAP_BYTES,
        )
        if final.links != 1:
            raise OSError("scope-fetch canonical sidecar does not have one link")
        try:
            os.stat(temporary_name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise OSError("scope-fetch temporary survived final publication")
        return copy.deepcopy(final.record)
