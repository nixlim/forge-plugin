"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
import os
from forge_cli import chain_core, runtime
from forge_cli.engine._core import MergeAdmission as MergeAdmission
import dataclasses
import hashlib
from typing import Mapping, Any
import stat
from pathlib import Path
import re
from forge_cli.policy import sha256_bytes
import copy
from forge_cli.envelope import FrozenError, REVISION9_OUTPUT_SCHEMA, Refusal


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
