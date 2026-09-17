"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
from forge_cli.engine._cli_options import _message_from_args as _message_from_args, _validate_revision9_cross_options as _validate_revision9_cross_options, render as render
from forge_cli.engine._core import commit_message_bytes as commit_message_bytes, chain_id_now as chain_id_now, promoted_tier as promoted_tier, _transition_state as _transition_state, _require_merge_lifecycle_control as _require_merge_lifecycle_control, inspect_common_lock as inspect_common_lock, _archive_refusal as _archive_refusal, _archive_contamination_refusal as _archive_contamination_refusal, _archive_metadata as _archive_metadata, _env_fingerprint as _env_fingerprint, _evidence_record as _evidence_record, _write_artifact as _write_artifact, _read_bound_artifact as _read_bound_artifact, _record_process_step as _record_process_step, _run_halt as _run_halt, MergeAdmission as MergeAdmission, MergeScopeResult as MergeScopeResult, MergeCandidateGeneration as MergeCandidateGeneration, MergeBootstrapClassification as MergeBootstrapClassification
from forge_cli.engine._parser import ContractArgumentParser as ContractArgumentParser, _extract_global_options as _extract_global_options, _attach_merge_lifecycle_parser as _attach_merge_lifecycle_parser, build_parser as build_parser, _raw_top_level_command as _raw_top_level_command
from forge_cli.engine._state import TERMINAL_STATES as TERMINAL_STATES, TERMINAL_TOUCH_VERBS as TERMINAL_TOUCH_VERBS, STATE_TRANSITIONS as STATE_TRANSITIONS, TOKEN_TTL_SECONDS as TOKEN_TTL_SECONDS, _REQUIRED_MERGE_LIFECYCLE_CONTROLS as _REQUIRED_MERGE_LIFECYCLE_CONTROLS, MERGE_LIFECYCLE_CONTROLS as MERGE_LIFECYCLE_CONTROLS, _REQUIRED_ARCHIVE_RECHECK_CONTROLS as _REQUIRED_ARCHIVE_RECHECK_CONTROLS, ARCHIVE_RECHECK_CONTROLS as ARCHIVE_RECHECK_CONTROLS, _CHAIN_CAPABILITY_LOCK as _CHAIN_CAPABILITY_LOCK, _CHAIN_CAPABILITIES as _CHAIN_CAPABILITIES, CODEX_EXECUTABLE as CODEX_EXECUTABLE, FRESH_REVIEWER_EVAL_REQUEST_SCHEMA as FRESH_REVIEWER_EVAL_REQUEST_SCHEMA, REVIEW_DIRECT_PACKAGE_MAX_BYTES as REVIEW_DIRECT_PACKAGE_MAX_BYTES, REVIEW_MASTER_WINDOW_BYTES as REVIEW_MASTER_WINDOW_BYTES, REVIEW_COMPLETE_PACKAGE_REFUSAL as REVIEW_COMPLETE_PACKAGE_REFUSAL, PRODUCED_COMMIT_MISMATCH as PRODUCED_COMMIT_MISMATCH, REVIEW_INSTRUCTION as REVIEW_INSTRUCTION, REVIEW_LAUNCHER_CODE as REVIEW_LAUNCHER_CODE, GLOBAL_OPTIONS_HELP as GLOBAL_OPTIONS_HELP, ARCHIVE_CONTAMINATION as ARCHIVE_CONTAMINATION, SECRET_RULES as SECRET_RULES, PLACEHOLDER_RE as PLACEHOLDER_RE, ABORT_DISPOSITION_PRECONDITIONS as ABORT_DISPOSITION_PRECONDITIONS, _MERGE_CANDIDATE_IDENTITY_FIELDS as _MERGE_CANDIDATE_IDENTITY_FIELDS, _MERGE_BOOTSTRAP_CHILD_SOURCE as _MERGE_BOOTSTRAP_CHILD_SOURCE, _DERIVE_MERGE_SCOPE as _DERIVE_MERGE_SCOPE, _MERGE_INITIAL_INTEGRATION as _MERGE_INITIAL_INTEGRATION
from typing import Any, Iterable, Mapping
from forge_cli.envelope import ReasonCode, Refusal
import json
import os
import stat
import hashlib
import re
from pathlib import Path


def _review_package_is_oversized(package: bytes) -> bool:
    """Return whether FR-216 requires pointer-only master-package transport."""

    return len(package) > REVIEW_DIRECT_PACKAGE_MAX_BYTES


def _review_complete_package_refusal(
    *,
    chain: Mapping[str, Any] | None = None,
    evidence_refs: Iterable[str] = (),
) -> Refusal:
    return Refusal(
        ReasonCode.EVIDENCE_INCOMPLETE,
        REVIEW_COMPLETE_PACKAGE_REFUSAL,
        expected=(
            "one reviewer inspecting every authoritative master-package byte "
            "through verified ascending raw-byte windows"
        ),
        observed=REVIEW_COMPLETE_PACKAGE_REFUSAL,
        remediation="stop without a verdict and request a fresh review package",
        chain=chain,
        evidence_refs=evidence_refs,
    )


def _review_master_window_count(byte_length: int) -> int:
    window_size = REVIEW_MASTER_WINDOW_BYTES
    if (
        type(byte_length) is not int
        or byte_length < 0
        or type(window_size) is not int
        or window_size <= 0
    ):
        raise _review_complete_package_refusal()
    return (byte_length + window_size - 1) // window_size


def _review_master_transport(
    master_path: str | os.PathLike[str], byte_length: int, master_digest: str
) -> str:
    """Render the pointer-only receipt shared by both reviewer adapters."""

    window_size = REVIEW_MASTER_WINDOW_BYTES
    window_count = _review_master_window_count(byte_length)
    path = json.dumps(os.fsdecode(os.fspath(master_path)), ensure_ascii=True)
    return (
        f"authoritative-master path={path} byte-length={byte_length} "
        f"sha256={master_digest} "
        f"windows=[{window_size}*n, min({window_size}*(n+1), byte_length)) "
        f"window-count=ceil({byte_length}/{window_size})={window_count} "
        "reader=forge_cli.engine.iter_verified_master_package_windows"
    )


def _review_master_pointer_prompt(
    master_path: str | os.PathLike[str],
    byte_length: int,
    master_digest: str,
    candidate: str,
) -> bytes:
    """Build a bounded launch prompt without copying any master-package bytes."""

    transport = _review_master_transport(master_path, byte_length, master_digest)
    return (
        "FORGE OVERSIZED REVIEW TRANSPORT v1\n"
        f"{transport}\n"
        "This launch prompt is transport only. The owner-controlled file above is the "
        "one authoritative review package; no embedded, truncated, cached, indexed, or "
        "summarized view is verdict authority.\n"
        "In this same reviewer execution, fully exhaust the named reader and inspect every "
        "yielded raw-byte window in ascending n before producing a verdict. The reader "
        "verifies identity, byte length, the complete master digest, and window "
        "concatenation. If it refuses, produce no verdict and report exactly: "
        f"{REVIEW_COMPLETE_PACKAGE_REFUSAL}\n"
        "\n--- BEGIN CONTROLLING OUTPUT CONTRACT ---\n"
        "Remain read-only and apply every controlling instruction and review profile in "
        "the authoritative master package.\n"
        "Return exactly this verdict grammar in the output-last-message file:\n"
        "VERDICT: PASS|BLOCK\n"
        f"candidate: {candidate}\n"
        f"package: {master_digest}\n"
        "Optional repeated line: finding: <CRITICAL|MAJOR|MINOR> <text>\n"
        "--- END CONTROLLING OUTPUT CONTRACT ---\n"
    ).encode("utf-8")


def _review_master_identity(value: os.stat_result) -> tuple[int, int]:
    return value.st_dev, value.st_ino


def _review_master_leaf_is_valid(
    value: os.stat_result, identity: tuple[int, int], byte_length: int
) -> bool:
    return bool(
        stat.S_ISREG(value.st_mode)
        and value.st_uid == os.geteuid()
        and value.st_nlink == 1
        and value.st_size == byte_length
        and _review_master_identity(value) == identity
    )


def _read_review_master_digest(
    descriptor: int, byte_length: int, window_size: int
) -> tuple[int, str]:
    """Hash at most the expected master length plus one growth-detection byte."""

    os.lseek(descriptor, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    total = 0
    limit = byte_length + 1
    while total < limit:
        try:
            chunk = os.read(descriptor, min(window_size, limit - total))
        except InterruptedError:
            continue
        if not chunk:
            break
        digest.update(chunk)
        total += len(chunk)
    return total, digest.hexdigest()


def _read_review_master_window(descriptor: int, start: int, end: int) -> bytes:
    """Read one exact raw-byte window, retrying short/interrupted pread calls."""

    parts: list[bytes] = []
    offset = start
    while offset < end:
        try:
            chunk = os.pread(descriptor, end - offset, offset)
        except InterruptedError:
            continue
        if not chunk:
            raise OSError("short master-package window")
        parts.append(chunk)
        offset += len(chunk)
    return b"".join(parts)


def _assert_review_master_stable(
    *,
    descriptor: int,
    absolute_path: str,
    identity: tuple[int, int],
    byte_length: int,
) -> None:
    opened = os.fstat(descriptor)
    rebound = os.stat(absolute_path, follow_symlinks=False)
    if not all(
        _review_master_leaf_is_valid(value, identity, byte_length)
        for value in (opened, rebound)
    ):
        raise OSError("master-package path identity or length changed")


def _iter_verified_master_package_windows(
    master_path: str | os.PathLike[str], byte_length: int, master_digest: str
) -> Iterable[bytes]:
    if (
        type(byte_length) is not int
        or byte_length < 0
        or not isinstance(master_digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", master_digest) is None
        or type(REVIEW_MASTER_WINDOW_BYTES) is not int
        or REVIEW_MASTER_WINDOW_BYTES <= 0
        or not hasattr(os, "O_NOFOLLOW")
        or not hasattr(os, "O_NONBLOCK")
        or not hasattr(os, "pread")
    ):
        raise OSError("master-package reader controls are unavailable")

    window_size = REVIEW_MASTER_WINDOW_BYTES
    window_count = (byte_length + window_size - 1) // window_size
    absolute_path = os.path.abspath(os.fsdecode(os.fspath(master_path)))
    if not Path(absolute_path).is_absolute():
        raise OSError("master-package path is not an absolute file path")

    leaf_flags = (
        os.O_RDONLY
        | os.O_NOFOLLOW
        | os.O_NONBLOCK
        | getattr(os, "O_CLOEXEC", 0)
    )
    descriptors: list[int] = []
    try:
        before = os.stat(absolute_path, follow_symlinks=False)
        descriptor = os.open(absolute_path, leaf_flags)
        descriptors.append(descriptor)
        opened = os.fstat(descriptor)
        rebound = os.stat(absolute_path, follow_symlinks=False)
        identity = _review_master_identity(opened)
        if not all(
            _review_master_leaf_is_valid(value, identity, byte_length)
            for value in (before, opened, rebound)
        ):
            raise OSError("master package is not one owner-controlled regular file")

        initial_length, initial_digest = _read_review_master_digest(
            descriptor, byte_length, window_size
        )
        _assert_review_master_stable(
            descriptor=descriptor,
            absolute_path=absolute_path,
            identity=identity,
            byte_length=byte_length,
        )
        if initial_length != byte_length or initial_digest != master_digest:
            raise OSError("master-package initial length or digest mismatch")

        concatenated_digest = hashlib.sha256()
        concatenated_length = 0
        final_window: bytes | None = None
        for index in range(window_count):
            start = window_size * index
            end = min(window_size * (index + 1), byte_length)
            window = _read_review_master_window(descriptor, start, end)
            if len(window) != end - start:
                raise OSError("master-package window length mismatch")
            concatenated_digest.update(window)
            concatenated_length += len(window)
            if index + 1 == window_count:
                # Hold the last view until the post-window proof succeeds. A
                # caller that receives every window has therefore received a
                # completely verified sequence without needing one extra next().
                final_window = window
            else:
                yield window

        if (
            concatenated_length != byte_length
            or concatenated_digest.hexdigest() != master_digest
        ):
            raise OSError("master-package window concatenation mismatch")
        final_length, final_digest = _read_review_master_digest(
            descriptor, byte_length, window_size
        )
        _assert_review_master_stable(
            descriptor=descriptor,
            absolute_path=absolute_path,
            identity=identity,
            byte_length=byte_length,
        )
        if final_length != byte_length or final_digest != master_digest:
            raise OSError("master-package final length or digest mismatch")
        if final_window is not None:
            yield final_window
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def iter_verified_master_package_windows(
    master_path: str | os.PathLike[str], byte_length: int, master_digest: str
) -> Iterable[bytes]:
    """Yield FR-216 raw windows or fail with its single refusal literal.

    The final window is released only after path identity, byte length, the
    complete digest, and the concatenation digest have all been re-verified.
    """

    try:
        yield from _iter_verified_master_package_windows(
            master_path, byte_length, master_digest
        )
    except Refusal:
        raise
    except (AttributeError, OSError, OverflowError, TypeError, ValueError) as exc:
        raise _review_complete_package_refusal() from exc
