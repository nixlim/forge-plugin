"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
import importlib.util
import sys
from typing import Any, Iterable, Mapping, Sequence
from forge_cli import runtime, chain_core
from forge_cli.engine._cli_options import _message_from_args as _message_from_args, _validate_revision9_cross_options as _validate_revision9_cross_options, render as render
from forge_cli.engine._core import commit_message_bytes as commit_message_bytes, chain_id_now as chain_id_now, promoted_tier as promoted_tier, _transition_state as _transition_state, _require_merge_lifecycle_control as _require_merge_lifecycle_control, inspect_common_lock as inspect_common_lock, _archive_refusal as _archive_refusal, _archive_contamination_refusal as _archive_contamination_refusal, _archive_metadata as _archive_metadata, _env_fingerprint as _env_fingerprint, _evidence_record as _evidence_record, _write_artifact as _write_artifact, _read_bound_artifact as _read_bound_artifact, _record_process_step as _record_process_step, _run_halt as _run_halt, MergeAdmission as MergeAdmission, MergeScopeResult as MergeScopeResult, MergeCandidateGeneration as MergeCandidateGeneration, MergeBootstrapClassification as MergeBootstrapClassification
from forge_cli.engine._parser import ContractArgumentParser as ContractArgumentParser, _extract_global_options as _extract_global_options, _attach_merge_lifecycle_parser as _attach_merge_lifecycle_parser, build_parser as build_parser, _raw_top_level_command as _raw_top_level_command
from forge_cli.engine._state import TERMINAL_STATES as TERMINAL_STATES, TERMINAL_TOUCH_VERBS as TERMINAL_TOUCH_VERBS, STATE_TRANSITIONS as STATE_TRANSITIONS, TOKEN_TTL_SECONDS as TOKEN_TTL_SECONDS, _REQUIRED_MERGE_LIFECYCLE_CONTROLS as _REQUIRED_MERGE_LIFECYCLE_CONTROLS, MERGE_LIFECYCLE_CONTROLS as MERGE_LIFECYCLE_CONTROLS, _REQUIRED_ARCHIVE_RECHECK_CONTROLS as _REQUIRED_ARCHIVE_RECHECK_CONTROLS, ARCHIVE_RECHECK_CONTROLS as ARCHIVE_RECHECK_CONTROLS, _CHAIN_CAPABILITY_LOCK as _CHAIN_CAPABILITY_LOCK, _CHAIN_CAPABILITIES as _CHAIN_CAPABILITIES, CODEX_EXECUTABLE as CODEX_EXECUTABLE, FRESH_REVIEWER_EVAL_REQUEST_SCHEMA as FRESH_REVIEWER_EVAL_REQUEST_SCHEMA, REVIEW_DIRECT_PACKAGE_MAX_BYTES as REVIEW_DIRECT_PACKAGE_MAX_BYTES, REVIEW_MASTER_WINDOW_BYTES as REVIEW_MASTER_WINDOW_BYTES, REVIEW_COMPLETE_PACKAGE_REFUSAL as REVIEW_COMPLETE_PACKAGE_REFUSAL, PRODUCED_COMMIT_MISMATCH as PRODUCED_COMMIT_MISMATCH, REVIEW_INSTRUCTION as REVIEW_INSTRUCTION, REVIEW_LAUNCHER_CODE as REVIEW_LAUNCHER_CODE, GLOBAL_OPTIONS_HELP as GLOBAL_OPTIONS_HELP, ARCHIVE_CONTAMINATION as ARCHIVE_CONTAMINATION, SECRET_RULES as SECRET_RULES, PLACEHOLDER_RE as PLACEHOLDER_RE, ABORT_DISPOSITION_PRECONDITIONS as ABORT_DISPOSITION_PRECONDITIONS, _MERGE_CANDIDATE_IDENTITY_FIELDS as _MERGE_CANDIDATE_IDENTITY_FIELDS, _MERGE_BOOTSTRAP_CHILD_SOURCE as _MERGE_BOOTSTRAP_CHILD_SOURCE, _DERIVE_MERGE_SCOPE as _DERIVE_MERGE_SCOPE, _MERGE_INITIAL_INTEGRATION as _MERGE_INITIAL_INTEGRATION
import os
import contextlib
import stat
from pathlib import Path
import io
from forge_cli.envelope import FrozenError, REVISION9_OUTPUT_SCHEMA, Refusal, V2ReasonCode
from forge_cli.policy import sha256_bytes
import threading


def _archive_module() -> Any:
    global _ARCHIVE_MODULE
    if _ARCHIVE_MODULE is not None:
        return _ARCHIVE_MODULE
    with _ARCHIVE_MODULE_LOCK:
        if _ARCHIVE_MODULE is not None:
            return _ARCHIVE_MODULE
        path = runtime.SCRIPT_DIR / "archive-run.py"
        specification = importlib.util.spec_from_file_location(
            "forge_archive_run_revision9", path
        )
        if specification is None or specification.loader is None:
            raise RuntimeError("archive renderer module is unavailable")
        existing = sys.modules.get(specification.name)
        if existing is not None:
            if not callable(getattr(existing, "render_archive_candidate", None)):
                raise RuntimeError("archive renderer module identity is occupied")
            _ARCHIVE_MODULE = existing
            return existing
        module = importlib.util.module_from_spec(specification)
        sys.modules[specification.name] = module
        try:
            specification.loader.exec_module(module)
        except BaseException:
            if sys.modules.get(specification.name) is module:
                sys.modules.pop(specification.name, None)
            raise
        _ARCHIVE_MODULE = module
        return module


def _nul_git_paths(value: bytes) -> list[str]:
    return [os.fsdecode(item) for item in value.split(b"\0") if item]


def _archive_close_tree_clean(
    repository: chain_core.Repository,
    relative: str,
    *,
    before_staging: bool,
) -> bool:
    staged = repository.staged_paths()
    unstaged = _nul_git_paths(
        repository.git(["diff", "--name-only", "-z"]).stdout
    )
    untracked = _nul_git_paths(
        repository.git(
            ["ls-files", "--others", "--exclude-standard", "-z"]
        ).stdout
    )
    if before_staging:
        return not staged and not unstaged and untracked in ([], [relative])
    return staged == [relative] and not unstaged and not untracked


@contextlib.contextmanager
def _archive_parent_descriptor(repository: Path, *, create: bool) -> Iterable[int]:
    """Open the fixed archive parent one no-follow component at a time."""

    root = Path(os.path.realpath(repository))
    descriptor = os.open(
        root,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        opened_root = os.fstat(descriptor)
        if not stat.S_ISDIR(opened_root.st_mode) or opened_root.st_uid != os.geteuid():
            raise OSError("repository is not an owner-controlled directory")
        for name in (".forge", "history", "runs"):
            if create:
                try:
                    os.mkdir(name, 0o700, dir_fd=descriptor)
                    os.fsync(descriptor)
                except FileExistsError:
                    pass
            child = os.open(
                name,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=descriptor,
            )
            child_stat = os.fstat(child)
            named_stat = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            if (
                not stat.S_ISDIR(child_stat.st_mode)
                or stat.S_ISLNK(named_stat.st_mode)
                or child_stat.st_uid != os.geteuid()
                or (child_stat.st_dev, child_stat.st_ino)
                != (named_stat.st_dev, named_stat.st_ino)
            ):
                os.close(child)
                raise OSError("archive destination parent is unsafe")
            os.close(descriptor)
            descriptor = child
        yield descriptor
    finally:
        os.close(descriptor)


def _read_archive_candidate_at(parent: int, name: str) -> bytes:
    descriptor: int | None = None
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NONBLOCK", 0),
            dir_fd=parent,
        )
        opened = os.fstat(descriptor)
        rebound = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if (
            not stat.S_ISREG(opened.st_mode)
            or stat.S_ISLNK(rebound.st_mode)
            or opened.st_uid != os.geteuid()
            or opened.st_nlink != 1
            or (opened.st_dev, opened.st_ino) != (rebound.st_dev, rebound.st_ino)
            or opened.st_size > 16_777_216
        ):
            raise OSError("archive candidate is not a safe owner-controlled regular file")
        data = b""
        while len(data) <= 16_777_216:
            chunk = os.read(descriptor, min(65536, 16_777_217 - len(data)))
            if not chunk:
                break
            data += chunk
        if len(data) > 16_777_216:
            raise OSError("archive candidate exceeds 16 MiB")
        after = os.fstat(descriptor)
        final_named = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if (
            (after.st_dev, after.st_ino, after.st_size)
            != (opened.st_dev, opened.st_ino, opened.st_size)
            or (final_named.st_dev, final_named.st_ino)
            != (opened.st_dev, opened.st_ino)
        ):
            raise OSError("archive candidate changed while read")
        return data
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _read_archive_candidate(repository: Path, run_id: str) -> bytes:
    with _archive_parent_descriptor(repository, create=False) as parent:
        return _read_archive_candidate_at(parent, f"{run_id}.md")


def _render_archive_bytes(
    ctx: chain_core.CommandContext, metadata: Mapping[str, Any]
) -> bytes:
    renderer = _archive_module()
    run_dir = (
        ctx.store.common_root
        / ".codex-orchestrator"
        / "runs"
        / str(metadata["run_id"])
    )
    captured_stdout = io.BytesIO()
    captured_text = io.TextIOWrapper(captured_stdout, encoding="utf-8")
    try:
        try:
            with contextlib.redirect_stdout(captured_text):
                rendered = renderer.render_archive_candidate(
                    repo=ctx.repo.root,
                    run_dir=run_dir,
                    closing_head=metadata.get("closing_head"),
                    legacy_recovered_head=metadata.get("legacy_recovered_head"),
                    legacy_approval=metadata.get("legacy_approval"),
                    post_close_validation=Path(
                        str(metadata["post_close_validation"])
                    ),
                    dispense_targets=tuple(metadata.get("dispense_targets", ())),
                    dispense_reason=metadata.get("dispense_reason"),
                )
        except SystemExit as exc:
            captured_text.flush()
            diagnostic = captured_stdout.getvalue().decode(
                "utf-8", "replace"
            ).strip()
            suffix = f": {diagnostic}" if diagnostic else ""
            raise _archive_refusal(
                "forge: archive refused — commitments audit failed "
                f"(exit {exc.code}){suffix}"
            ) from exc
    except Exception as exc:
        if exc.__class__.__name__ == "ArchiveRefusal":
            raise _archive_refusal(str(getattr(exc, "message", exc))) from exc
        raise
    finally:
        try:
            captured_text.detach()
        except (ValueError, OSError):
            pass
    if not isinstance(rendered, bytes):
        raise FrozenError(
            "archive renderer returned a non-byte candidate",
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    if len(rendered) > 16_777_216:
        raise Refusal(
            V2ReasonCode.ARCHIVE_SIZE_LIMIT,
            "forge: archive refused — rendered archive exceeds 16 MiB",
            remediation="reduce citable evidence without truncating authority",
        )
    return rendered


def _prepare_archive_candidate(
    ctx: chain_core.CommandContext,
    run_id: str,
    *,
    legacy_recovered_head: str | None,
    legacy_approval: str | None,
    dispense_targets: Sequence[str],
    dispense_reason: str | None,
) -> tuple[list[str], dict[str, Any]]:
    if chain_core.RUN_ID_RE.fullmatch(run_id) is None:
        raise _archive_refusal("forge: archive refused — invalid run identity")
    if legacy_recovered_head is not None and chain_core.COMMIT_RE.fullmatch(
        legacy_recovered_head
    ) is None:
        raise _archive_refusal(
            "forge: archive refused — legacy recovery approval missing or mismatched"
        )
    relative = f".forge/history/runs/{run_id}.md"
    if Path(relative).parts != (".forge", "history", "runs", f"{run_id}.md"):
        raise _archive_refusal("forge: archive refused — unsafe archive candidate path")
    if not _archive_close_tree_clean(
        ctx.repo, relative, before_staging=True
    ):
        raise _archive_contamination_refusal()
    committed = ctx.repo.git(["cat-file", "-e", f"HEAD:{relative}"], check=False)
    if committed.returncode == 0:
        raise _archive_refusal(
            f"forge: archive refused — archive already exists in HEAD: {relative}"
        )
    run_dir = (
        ctx.store.common_root / ".codex-orchestrator" / "runs" / run_id
    )
    metadata: dict[str, Any] = {
        "run_id": run_id,
        "path": relative,
        "closing_head": None if legacy_recovered_head is not None else ctx.repo.head(),
        "legacy_recovered_head": legacy_recovered_head,
        "legacy_approval": legacy_approval,
        "post_close_validation": str(run_dir / "post-close-validation.json"),
        "dispense_targets": list(dispense_targets),
        "dispense_reason": dispense_reason,
    }
    rendered = _render_archive_bytes(ctx, metadata)
    try:
        with _archive_parent_descriptor(ctx.repo.root, create=True) as parent:
            try:
                existing = _read_archive_candidate_at(parent, f"{run_id}.md")
            except FileNotFoundError:
                descriptor = os.open(
                    f"{run_id}.md",
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_CLOEXEC", 0),
                    0o600,
                    dir_fd=parent,
                )
                try:
                    opened = os.fstat(descriptor)
                    if (
                        not stat.S_ISREG(opened.st_mode)
                        or opened.st_uid != os.geteuid()
                        or opened.st_nlink != 1
                    ):
                        raise OSError("new archive candidate is unsafe")
                    written = 0
                    while written < len(rendered):
                        count = os.write(descriptor, rendered[written:])
                        if count <= 0:
                            raise OSError("short archive candidate write")
                        written += count
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                os.fsync(parent)
                existing = _read_archive_candidate_at(parent, f"{run_id}.md")
    except OSError as exc:
        raise _archive_refusal(f"forge: archive refused — {exc}") from exc
    if chain_core._validated_commitment_path(
        "archive.candidate",
        relative,
        repository=ctx.repo.root,
        direct_parent=ctx.repo.root / ".forge" / "history" / "runs",
        require_file=True,
    ) is None:
        raise _archive_refusal(
            "forge: archive refused — unsafe archive candidate path"
        )
    if existing != rendered:
        raise Refusal(
            V2ReasonCode.ARCHIVE_RERENDER_MISMATCH,
            "forge: archive refused — rerendered bytes differ from candidate",
            expected=sha256_bytes(rendered),
            observed=sha256_bytes(existing),
            remediation="remove the mismatched uncommitted archive and rerender",
        )
    metadata["rendered_sha256"] = sha256_bytes(rendered)
    return [relative], metadata


def _archive_recheck(
    ctx: chain_core.CommandContext,
    state: Mapping[str, Any],
    phase: str,
    *,
    require_staged: bool = True,
) -> None:
    if ARCHIVE_RECHECK_CONTROLS != _REQUIRED_ARCHIVE_RECHECK_CONTROLS:
        raise FrozenError(
            "Revision-9 archive rerender control is unavailable",
            chain_id=str(state.get("chain_id") or "") or None,
            state=str(state.get("state") or "") or None,
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    staging = state.get("staging")
    metadata = (
        staging.get("archive")
        if isinstance(staging, Mapping)
        else None
    )
    if metadata is None:
        return
    if not isinstance(metadata, Mapping) or set(metadata) != {
        "run_id",
        "path",
        "closing_head",
        "legacy_recovered_head",
        "legacy_approval",
        "post_close_validation",
        "dispense_targets",
        "dispense_reason",
        "rendered_sha256",
    }:
        raise _archive_refusal("forge: archive refused — malformed archive chain metadata", chain=state)
    relative = str(metadata["path"])
    if relative != f".forge/history/runs/{metadata['run_id']}.md":
        raise _archive_refusal("forge: archive refused — unsafe archive candidate path", chain=state)
    if chain_core._validated_commitment_path(
        "archive.candidate",
        relative,
        repository=ctx.repo.root,
        direct_parent=ctx.repo.root / ".forge" / "history" / "runs",
        require_file=True,
    ) is None:
        raise _archive_refusal(
            "forge: archive refused — unsafe archive candidate path",
            chain=state,
        )
    if ctx.repo.git(["cat-file", "-e", f"HEAD:{relative}"], check=False).returncode == 0:
        raise _archive_refusal("forge: archive refused — archive already exists in HEAD", chain=state)
    rendered = _render_archive_bytes(ctx, metadata)
    try:
        candidate = _read_archive_candidate(
            ctx.repo.root, str(metadata["run_id"])
        )
    except OSError as exc:
        raise _archive_refusal(f"forge: archive refused — {exc}", chain=state) from exc
    if candidate != rendered or sha256_bytes(rendered) != metadata["rendered_sha256"]:
        raise Refusal(
            V2ReasonCode.ARCHIVE_RERENDER_MISMATCH,
            "forge: archive refused — rerendered bytes differ from candidate",
            expected=str(metadata["rendered_sha256"]),
            observed=sha256_bytes(candidate),
            remediation=f"restart archive commit after {phase} mismatch",
            chain=state,
        )
    if require_staged and not _archive_close_tree_clean(
        ctx.repo, relative, before_staging=False
    ):
        raise _archive_contamination_refusal(chain=state)


_ARCHIVE_MODULE: Any | None = None


_ARCHIVE_MODULE_LOCK = threading.Lock()
