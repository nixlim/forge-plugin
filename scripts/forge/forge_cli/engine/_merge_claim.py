"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
import copy
from typing import Any, Iterable, Mapping
from forge_cli import chain_core
from forge_cli.engine._core import _require_merge_lifecycle_control as _require_merge_lifecycle_control
import contextlib
import os
import stat
from pathlib import Path
from forge_cli.policy import sha256_bytes
from forge_cli.envelope import FrozenError, REVISION9_OUTPUT_SCHEMA, Refusal, V2ReasonCode


def _validate_merge_claim_record(value: Any) -> dict[str, Any]:
    _require_merge_lifecycle_control("atomic-worktree-ownership")
    if not isinstance(value, dict) or set(value) != {
        "chain_id",
        "host",
        "pid",
        "session",
        "started_at",
        "worktree_digest",
    }:
        raise ValueError("merge ownership claim has an invalid key set")
    if (
        not isinstance(value.get("chain_id"), str)
        or chain_core.CHAIN_ID_RE.fullmatch(str(value["chain_id"])) is None
        or not chain_core._valid_host(value.get("host"))
        or not chain_core._valid_positive_int(value.get("pid"))
        or not isinstance(value.get("session"), str)
        or not value["session"]
        or "\x00" in value["session"]
        or not chain_core._valid_utc_second(value.get("started_at"))
        or not isinstance(value.get("worktree_digest"), str)
        or chain_core.SHA256_RE.fullmatch(str(value["worktree_digest"])) is None
    ):
        raise ValueError("merge ownership claim fields are invalid")
    return copy.deepcopy(value)


@contextlib.contextmanager
def _merge_owner_directory(store: chain_core.MergeChainStore) -> Iterable[tuple[int, Path]]:
    store.ensure_root()
    with store.root_descriptor() as root:
        owners = store._open_child_directory(root, "owners", create=True)
        try:
            opened = os.fstat(owners)
            if not stat.S_ISDIR(opened.st_mode) or opened.st_uid != os.geteuid():
                raise OSError("merge ownership directory is not owner-controlled")
            os.fchmod(owners, 0o700)
            yield owners, store.root / "owners"
        finally:
            os.close(owners)


def _merge_claim_identity(
    store: chain_core.MergeChainStore, worktree_identity: Mapping[str, str]
) -> tuple[str, str, Path]:
    worktree_digest = sha256_bytes(chain_core.canonical_bytes(dict(worktree_identity)))
    name = f"{worktree_digest}.claim"
    return worktree_digest, name, store.root / "owners" / name


def _read_merge_claim(
    store: chain_core.MergeChainStore, name: str, path: Path
) -> chain_core.PublishedLockRecord | None:
    with _merge_owner_directory(store) as (owners, _owners_path):
        return chain_core._record_at_if_present(
            owners, name, path, _validate_merge_claim_record
        )


def _publish_merge_claim(
    store: chain_core.MergeChainStore,
    name: str,
    path: Path,
    record: Mapping[str, Any],
) -> chain_core.PublishedLockRecord:
    _require_merge_lifecycle_control("atomic-worktree-ownership")
    with _merge_owner_directory(store) as (owners, owners_path):
        temporary, private = chain_core._create_private_record_at(
            owners,
            owners_path,
            name,
            record,
            boundary=None,
            stage="merge-claim-temp-fsynced",
        )
        published = False
        try:
            chain_core._publish_no_replace_link(owners, temporary, owners, name)
            published = True
            os.fsync(owners)
            canonical = chain_core._read_owned_record_at(
                owners, name, path, _validate_merge_claim_record
            )
            if not chain_core._same_published_record(canonical, private):
                raise OSError("published merge claim changed inode or digest")
            return canonical
        finally:
            try:
                chain_core._unlink_revalidated_record_at(
                    owners,
                    temporary,
                    owners_path / temporary,
                    private,
                    _validate_merge_claim_record,
                )
                os.fsync(owners)
            except FileNotFoundError:
                if not published:
                    raise


def _merge_publication_failure(
    store: chain_core.MergeChainStore,
    state: Mapping[str, Any],
    claim_path: Path,
    intended_record: Mapping[str, Any],
    error: OSError,
) -> Refusal:
    """Classify a publication race without trusting the collided pathname."""

    try:
        existing = _read_merge_claim(store, claim_path.name, claim_path)
    except (OSError, ValueError) as exc:
        raise FrozenError(
            "merge ownership publication collision is malformed",
            chain_id=str(state["chain_id"]),
            observed=f"{claim_path}: {exc}",
            schema=REVISION9_OUTPUT_SCHEMA,
        ) from exc
    if existing is None:
        if isinstance(error, FileExistsError):
            raise FrozenError(
                "merge ownership publication collision vanished before authentication",
                chain_id=str(state["chain_id"]),
                observed=str(claim_path),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        return chain_core._merge_refusal(
            V2ReasonCode.STATE_PRECONDITION,
            "forge: merge start refused — ownership claim publication failed",
            expected="one atomic no-replace owner claim",
            observed=str(error),
            remediation=f"forge status --chain-id {state['chain_id']}",
            chain=state,
        )

    intended_digest = sha256_bytes(chain_core.canonical_bytes(dict(intended_record)))
    if (
        existing.record == dict(intended_record)
        and existing.digest == intended_digest
        and existing.record.get("chain_id") == state["chain_id"]
        and state["worktree"]["claim"].get("status") == "unpublished"
        and state["worktree"]["claim"].get("digest") == intended_digest
    ):
        return chain_core._merge_refusal(
            V2ReasonCode.STATE_PRECONDITION,
            "forge: merge start refused — ownership publication requires recovery",
            expected="completion of the authenticated publish-before-event claim",
            observed=str(claim_path),
            remediation=f"forge merge recover --chain-id {state['chain_id']}",
            chain=state,
        )

    prior_id = str(existing.record.get("chain_id", ""))
    try:
        with store.event_lock(prior_id):
            replay = store._read_replay_locked(prior_id)
            store._projection_status(replay)
    except (FrozenError, ValueError) as exc:
        raise FrozenError(
            "merge ownership publication collision names an unverifiable chain",
            chain_id=prior_id or str(state["chain_id"]),
            observed=str(claim_path),
            schema=REVISION9_OUTPUT_SCHEMA,
        ) from exc
    prior = replay.state
    prior_claim = prior.get("worktree", {}).get("claim")
    same_identity = all(
        prior.get("worktree", {}).get(name) == state["worktree"].get(name)
        for name in ("path", "git_dir", "common_dir")
    )
    exact_acquired = bool(
        isinstance(prior_claim, Mapping)
        and prior_claim.get("status") in {"owned", "releasing"}
        and prior_claim.get("path") == str(claim_path)
        and prior_claim.get("inode") == existing.inode
        and prior_claim.get("digest") == existing.digest
    )
    exact_publish_window = bool(
        isinstance(prior_claim, Mapping)
        and prior_claim.get("status") == "unpublished"
        and prior_claim.get("path") == str(claim_path)
        and prior_claim.get("inode") is None
        and prior_claim.get("digest") == existing.digest
    )
    if (
        same_identity
        and prior.get("state") not in {"closed", "aborted"}
        and (exact_acquired or exact_publish_window)
    ):
        return chain_core._merge_refusal(
            V2ReasonCode.LIVE_MERGE_CHAIN_EXISTS,
            "forge: merge start refused — selected worktree already has a live merge owner",
            expected="an unowned registered worktree",
            observed=prior_id,
            remediation=f"forge status --chain-id {prior_id}",
            chain=prior,
        )
    raise FrozenError(
        "merge ownership publication collision does not match an authoritative live owner",
        chain_id=prior_id or str(state["chain_id"]),
        observed=chain_core.canonical_bytes(existing.evidence()).decode("utf-8"),
        schema=REVISION9_OUTPUT_SCHEMA,
    )


def _remove_merge_claim(
    store: chain_core.MergeChainStore,
    state: Mapping[str, Any],
    *,
    unlink: bool = True,
) -> chain_core.PublishedLockRecord:
    _require_merge_lifecycle_control("atomic-worktree-ownership")
    claim = state["worktree"]["claim"]
    path = Path(str(claim["path"]))
    identity = {
        name: str(state["worktree"][name])
        for name in ("path", "git_dir", "common_dir")
    }
    _worktree_digest, expected_name, expected_path = _merge_claim_identity(
        store, identity
    )
    with _merge_owner_directory(store) as (owners, owners_path):
        if (
            path != expected_path
            or path.parent != owners_path
            or path.name != expected_name
        ):
            raise FrozenError(
                "merge ownership claim path is not canonical",
                chain_id=str(state["chain_id"]),
                observed=str(path),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        try:
            existing = chain_core._read_owned_record_at(
                owners, path.name, path, _validate_merge_claim_record
            )
        except (FileNotFoundError, OSError, ValueError) as exc:
            raise FrozenError(
                "acquired merge ownership claim is absent or invalid",
                chain_id=str(state["chain_id"]),
                observed=str(exc),
                schema=REVISION9_OUTPUT_SCHEMA,
            ) from exc
        if (
            existing.record.get("chain_id") != state["chain_id"]
            or existing.inode != claim.get("inode")
            or existing.digest != claim.get("digest")
        ):
            raise FrozenError(
                "merge ownership claim diverges from its chain projection",
                chain_id=str(state["chain_id"]),
                observed=chain_core.canonical_bytes(existing.evidence()).decode("utf-8"),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        if unlink:
            chain_core._unlink_revalidated_record_at(
                owners,
                path.name,
                path,
                existing,
                _validate_merge_claim_record,
            )
            os.fsync(owners)
        return existing


def _merge_unpublished_claim_absent(
    state: Mapping[str, Any], store: chain_core.MergeChainStore
) -> bool:
    try:
        path = Path(str(state["worktree"]["claim"]["path"]))
        identity = {
            name: str(state["worktree"][name])
            for name in ("path", "git_dir", "common_dir")
        }
        _digest, expected_name, expected_path = _merge_claim_identity(
            store, identity
        )
        if path != expected_path or path.name != expected_name:
            return False
        with _merge_owner_directory(store) as (owners, _owners_path):
            os.stat(path.name, dir_fd=owners, follow_symlinks=False)
    except FileNotFoundError:
        return True
    except (KeyError, TypeError, OSError, ValueError):
        return False
    return False
