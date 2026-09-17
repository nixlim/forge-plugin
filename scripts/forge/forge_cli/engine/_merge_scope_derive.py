"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
import os
from forge_cli import chain_core, runtime
from forge_cli.engine._cli_options import _message_from_args as _message_from_args, _validate_revision9_cross_options as _validate_revision9_cross_options, render as render
from forge_cli.engine._core import commit_message_bytes as commit_message_bytes, chain_id_now as chain_id_now, promoted_tier as promoted_tier, _transition_state as _transition_state, _require_merge_lifecycle_control as _require_merge_lifecycle_control, inspect_common_lock as inspect_common_lock, _archive_refusal as _archive_refusal, _archive_contamination_refusal as _archive_contamination_refusal, _archive_metadata as _archive_metadata, _env_fingerprint as _env_fingerprint, _evidence_record as _evidence_record, _write_artifact as _write_artifact, _read_bound_artifact as _read_bound_artifact, _record_process_step as _record_process_step, _run_halt as _run_halt, MergeAdmission as MergeAdmission, MergeScopeResult as MergeScopeResult, MergeCandidateGeneration as MergeCandidateGeneration, MergeBootstrapClassification as MergeBootstrapClassification
from forge_cli.engine._parser import ContractArgumentParser as ContractArgumentParser, _extract_global_options as _extract_global_options, _attach_merge_lifecycle_parser as _attach_merge_lifecycle_parser, build_parser as build_parser, _raw_top_level_command as _raw_top_level_command
from forge_cli.engine._state import TERMINAL_STATES as TERMINAL_STATES, TERMINAL_TOUCH_VERBS as TERMINAL_TOUCH_VERBS, STATE_TRANSITIONS as STATE_TRANSITIONS, TOKEN_TTL_SECONDS as TOKEN_TTL_SECONDS, _REQUIRED_MERGE_LIFECYCLE_CONTROLS as _REQUIRED_MERGE_LIFECYCLE_CONTROLS, MERGE_LIFECYCLE_CONTROLS as MERGE_LIFECYCLE_CONTROLS, _REQUIRED_ARCHIVE_RECHECK_CONTROLS as _REQUIRED_ARCHIVE_RECHECK_CONTROLS, ARCHIVE_RECHECK_CONTROLS as ARCHIVE_RECHECK_CONTROLS, _CHAIN_CAPABILITY_LOCK as _CHAIN_CAPABILITY_LOCK, _CHAIN_CAPABILITIES as _CHAIN_CAPABILITIES, CODEX_EXECUTABLE as CODEX_EXECUTABLE, FRESH_REVIEWER_EVAL_REQUEST_SCHEMA as FRESH_REVIEWER_EVAL_REQUEST_SCHEMA, REVIEW_DIRECT_PACKAGE_MAX_BYTES as REVIEW_DIRECT_PACKAGE_MAX_BYTES, REVIEW_MASTER_WINDOW_BYTES as REVIEW_MASTER_WINDOW_BYTES, REVIEW_COMPLETE_PACKAGE_REFUSAL as REVIEW_COMPLETE_PACKAGE_REFUSAL, PRODUCED_COMMIT_MISMATCH as PRODUCED_COMMIT_MISMATCH, REVIEW_INSTRUCTION as REVIEW_INSTRUCTION, REVIEW_LAUNCHER_CODE as REVIEW_LAUNCHER_CODE, GLOBAL_OPTIONS_HELP as GLOBAL_OPTIONS_HELP, ARCHIVE_CONTAMINATION as ARCHIVE_CONTAMINATION, SECRET_RULES as SECRET_RULES, PLACEHOLDER_RE as PLACEHOLDER_RE, ABORT_DISPOSITION_PRECONDITIONS as ABORT_DISPOSITION_PRECONDITIONS, _MERGE_CANDIDATE_IDENTITY_FIELDS as _MERGE_CANDIDATE_IDENTITY_FIELDS, _MERGE_BOOTSTRAP_CHILD_SOURCE as _MERGE_BOOTSTRAP_CHILD_SOURCE, _DERIVE_MERGE_SCOPE as _DERIVE_MERGE_SCOPE, _MERGE_INITIAL_INTEGRATION as _MERGE_INITIAL_INTEGRATION
import dataclasses
import hashlib
from typing import Mapping, Any
import stat
from pathlib import Path
import re
from forge_cli.policy import sha256_bytes
import copy
from forge_cli.envelope import FrozenError, REVISION9_OUTPUT_SCHEMA, Refusal, V2ReasonCode


def _merge_scope_environment() -> dict[str, str]:
    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("GIT_CONFIG_") and name not in chain_core._MERGE_SCOPE_UNSET
    }
    environment.update(chain_core._MERGE_SCOPE_OVERLAY)
    return environment


@dataclasses.dataclass(frozen=True)
class _GitNoLazyFetchQualification:
    """Invocation-local proof that the selected Git accepts no-lazy-fetch."""

    executable_path: str
    resolved_path: str
    device: int
    inode: int
    mode: int
    size: int
    mtime_ns: int
    ctime_ns: int
    environment_digest: str
    argv: tuple[str, ...]
    output: bytes
    output_digest: str


def _git_environment_digest(environment: Mapping[str, str]) -> str:
    """Digest an environment without assuming all OS bytes are Unicode."""

    digest = hashlib.sha256()
    for name in sorted(environment, key=os.fsencode):
        encoded_name = os.fsencode(name)
        encoded_value = os.fsencode(environment[name])
        digest.update(len(encoded_name).to_bytes(8, "big"))
        digest.update(encoded_name)
        digest.update(len(encoded_value).to_bytes(8, "big"))
        digest.update(encoded_value)
    return digest.hexdigest()


def _git_executable_qualification(
    cwd: Path, environment: Mapping[str, str]
) -> tuple[str, str, int, int, int, int, int, int]:
    """Resolve the exact PATH-selected Git executable and stable stat tuple."""

    search_path = environment.get("PATH", os.defpath)
    for member in search_path.split(os.pathsep):
        directory = cwd if member == "" else Path(member)
        if not directory.is_absolute():
            directory = cwd / directory
        executable_path = os.path.abspath(os.fspath(directory / "git"))
        try:
            if not os.access(executable_path, os.X_OK):
                continue
            resolved = Path(executable_path).resolve(strict=True)
            observed = os.stat(resolved, follow_symlinks=False)
        except OSError:
            continue
        if not stat.S_ISREG(observed.st_mode):
            continue
        return (
            executable_path,
            str(resolved),
            observed.st_dev,
            observed.st_ino,
            stat.S_IMODE(observed.st_mode),
            observed.st_size,
            observed.st_mtime_ns,
            observed.st_ctime_ns,
        )
    raise OSError("Git executable is unavailable on the qualified PATH")


def _qualify_git_no_lazy_fetch(
    cwd: Path, *, verbose: bool = False
) -> _GitNoLazyFetchQualification:
    """Prove before lock admission that this invocation's Git accepts the control."""

    environment = _merge_scope_environment()
    before = _git_executable_qualification(cwd, environment)
    argv = ["git", "--no-lazy-fetch", "--version"]
    result = runtime.run_bounded(
        argv,
        cwd=cwd,
        env=environment,
        timeout=min(runtime.COMMAND_TIMEOUT_SECONDS, chain_core.COMMON_LOCK_TIMEOUT_SECONDS),
        cap=runtime.OUTPUT_CAP_BYTES,
        verbose=verbose,
    )
    after = _git_executable_qualification(cwd, environment)
    if (
        before != after
        or result.argv != argv
        or type(result.returncode) is not int
        or result.returncode != 0
        or result.timed_out is not False
        or result.output_limit is not False
        or not isinstance(result.output, bytes)
        or result.output_digest != sha256_bytes(result.output)
        or re.fullmatch(rb"git version [0-9][ -~]*\n", result.output) is None
    ):
        raise OSError("Git does not support the required no-lazy-fetch control")
    return _GitNoLazyFetchQualification(
        executable_path=before[0],
        resolved_path=before[1],
        device=before[2],
        inode=before[3],
        mode=before[4],
        size=before[5],
        mtime_ns=before[6],
        ctime_ns=before[7],
        environment_digest=_git_environment_digest(environment),
        argv=tuple(argv),
        output=result.output,
        output_digest=result.output_digest,
    )


def _require_git_no_lazy_fetch_qualification(
    qualification: object,
    cwd: Path,
    environment: Mapping[str, str],
) -> None:
    """Rebind an invocation-local qualification immediately before use."""

    if not isinstance(qualification, _GitNoLazyFetchQualification):
        raise OSError("Git no-lazy-fetch qualification is unavailable")
    expected = (
        qualification.executable_path,
        qualification.resolved_path,
        qualification.device,
        qualification.inode,
        qualification.mode,
        qualification.size,
        qualification.mtime_ns,
        qualification.ctime_ns,
    )
    if (
        qualification.argv != ("git", "--no-lazy-fetch", "--version")
        or re.fullmatch(rb"git version [0-9][ -~]*\n", qualification.output)
        is None
        or qualification.output_digest != sha256_bytes(qualification.output)
        or qualification.environment_digest != _git_environment_digest(environment)
        or _git_executable_qualification(cwd, environment) != expected
    ):
        raise OSError("qualified Git executable or environment changed")


def _discover_merge_scope_fence_from_sidecar(
    store: chain_core.MergeChainStore,
    state: Mapping[str, Any],
    *,
    fetch_intent_digest: str,
) -> chain_core.PublishedLockRecord | None:
    """Recover cleared fence identity only from the current intent's sidecar.

    A common-lock recovery may have durably proved death and cleared the
    canonical fence before the chain lease is reacquired.  The immutable
    sidecar deliberately carries the complete original fence record and
    physical identity, so recovery can reconstruct that evidence without a
    tracking ref, FETCH_HEAD, or remote query.  No matching deterministic name
    means the normative both-absent pre-publication window.
    """

    chain_id = str(state["chain_id"])
    prefix = f"scope-fetch-{fetch_intent_digest}-"
    pattern = re.compile(
        rf"^{re.escape(prefix)}([0-9a-f]{{64}})\.json(?:\.tmp-([0-9a-f]{{32}}))?$"
    )
    try:
        with store.artifact_parent_descriptor(
            chain_id, f"{prefix}{'0' * 64}.json", create=False
        ) as (parent, _name):
            related = sorted(
                name for name in os.listdir(parent) if name.startswith(prefix)
            )
            if not related:
                return None
            matches = [(name, pattern.fullmatch(name)) for name in related]
            if any(match is None for _name, match in matches):
                raise OSError("current scope-fetch intent has a conflicting artifact name")
            digests = {str(match.group(1)) for _name, match in matches if match}
            if len(digests) != 1:
                raise OSError("current scope-fetch intent names multiple fence digests")
            fence_digest = next(iter(digests))
            candidate_name = related[0]
            observed = chain_core._read_owned_record_at(
                parent,
                candidate_name,
                store.root / chain_id / candidate_name,
                chain_core._validate_merge_scope_fetch_binding,
                cap=chain_core.MERGE_SCOPE_BINDING_CAP_BYTES,
            )
    except FileNotFoundError:
        return None
    except FrozenError:
        raise
    except (OSError, ValueError, Refusal) as exc:
        raise FrozenError(
            "merge scope-fetch fence evidence is divergent",
            chain_id=chain_id,
            observed=str(exc),
            schema=REVISION9_OUTPUT_SCHEMA,
        ) from exc
    retained = observed.record["retained_inflight"]
    record = {
        name: copy.deepcopy(retained[name])
        for name in (
            "schema",
            "owner_kind",
            "chain_id",
            "operation",
            "host",
            "pid",
            "pgid",
            "started_at",
            "intent_digest",
            "nonce",
        )
    }
    try:
        chain_core._validate_fence_record(record)
        if (
            retained.get("inflight_digest") != fence_digest
            or retained.get("inflight_digest")
            != sha256_bytes(chain_core.canonical_bytes(record))
            or retained.get("intent_digest") != fetch_intent_digest
            or retained.get("chain_id") != chain_id
            or retained.get("owner_kind") != "merge"
            or retained.get("operation") not in {"fetch", "tip-resolution"}
        ):
            raise ValueError("embedded retained fence does not bind the current intent")
    except ValueError as exc:
        raise FrozenError(
            "merge scope-fetch retained fence is divergent",
            chain_id=chain_id,
            observed=str(exc),
            schema=REVISION9_OUTPUT_SCHEMA,
        ) from exc
    recovered = chain_core.PublishedLockRecord(
        path=str(retained["path"]),
        device=int(retained["device"]),
        inode=int(retained["inode"]),
        digest=fence_digest,
        record=record,
        mode=0o600,
        links=1,
    )
    canonical_name, temporary_name, _canonical_path, _temporary_path = (
        chain_core._merge_scope_binding_names(chain_id, fetch_intent_digest, recovered)
    )
    if not set(related) <= {canonical_name, temporary_name}:
        raise FrozenError(
            "merge scope-fetch deterministic names diverge from retained fence",
            chain_id=chain_id,
            observed=chain_core.canonical_bytes(related).decode("utf-8"),
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    return recovered


def _parse_merge_name_status_output(raw: bytes) -> tuple[str, ...]:
    """Parse one exact ``git diff --name-status -z`` byte stream."""

    if raw and not raw.endswith(b"\0"):
        raise ValueError("scope output is not NUL terminated")
    fields = raw.split(b"\0")[:-1] if raw else []
    paths: list[str] = []
    index = 0
    _batch, _builders, journal = runtime._coordination_modules()
    while index < len(fields):
        try:
            status = fields[index].decode("ascii")
        except UnicodeDecodeError as exc:
            raise ValueError("scope status is not ASCII") from exc
        index += 1
        path_count = 1
        if re.fullmatch(r"[RC][0-9]{1,3}", status):
            score = int(status[1:])
            if score > 100:
                raise ValueError("scope rename/copy score is invalid")
            path_count = 2
        elif re.fullmatch(r"[ADMTUXB]", status) is None:
            raise ValueError("scope status is invalid")
        if index + path_count > len(fields):
            raise ValueError("scope status lacks its path field")
        for raw_path in fields[index : index + path_count]:
            try:
                path = raw_path.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError("scope path is not UTF-8") from exc
            if not journal._valid_scope_item(path):
                raise ValueError("scope path is not a canonical repository path")
            paths.append(path)
        index += path_count
    return tuple(sorted(set(paths), key=lambda value: value.encode("utf-8")))


def _parse_merge_scope_output(raw: bytes) -> tuple[str, ...]:
    """Retain the parent adapter name while sharing the composite parser."""

    return _parse_merge_name_status_output(raw)


def _derive_merge_scope(
    admission: MergeAdmission,
    remote_tip: str,
) -> MergeScopeResult | None:
    snapshot = admission.run_task
    if snapshot is None:
        return None
    argv = chain_core._merge_scope_argv(
        admission.worktree, remote_tip, admission.candidate_head
    )
    environment = _merge_scope_environment()
    try:
        process = runtime.run_bounded(
            argv,
            cwd=admission.worktree,
            env=environment,
            timeout=runtime.COMMAND_TIMEOUT_SECONDS,
            cap=runtime.OUTPUT_CAP_BYTES,
        )
    except OSError as exc:
        raise chain_core._merge_refusal(
            V2ReasonCode.RUN_TASK_BINDING_INVALID,
            "forge: merge start refused — run/task scope derivation is invalid",
            expected="the exact fixed-object scope child to launch",
            observed=str(exc),
        ) from exc
    if (
        process.returncode != 0
        or process.timed_out
        or process.output_limit
    ):
        raise chain_core._merge_refusal(
            V2ReasonCode.RUN_TASK_BINDING_INVALID,
            "forge: merge start refused — run/task scope derivation is invalid",
            expected="complete exit 0 scope derivation within the fixed bounds",
            observed=(
                f"exit={process.returncode}, timeout={process.timed_out}, "
                f"output_limit={process.output_limit}"
            ),
        )
    try:
        changed_paths = _parse_merge_scope_output(process.output)
    except ValueError as exc:
        raise chain_core._merge_refusal(
            V2ReasonCode.RUN_TASK_BINDING_INVALID,
            "forge: merge start refused — run/task scope derivation is invalid",
            expected="the exact NUL-delimited name-status grammar",
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
    return MergeScopeResult(
        argv=tuple(argv),
        command_digest=sha256_bytes(chain_core.canonical_bytes(argv)),
        environment_digest=sha256_bytes(
            chain_core.canonical_bytes(chain_core._merge_scope_environment_contract())
        ),
        output_digest=process.output_digest,
        changed_paths=changed_paths,
        out_of_scope_paths=out_of_scope,
        result="exceeded" if out_of_scope else "contained",
    )
