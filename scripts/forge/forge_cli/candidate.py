"""Immutable Git-tree commit-candidate plumbing shared by Forge CLI and guard.

The helpers in this module intentionally use only the Python standard library and
Git plumbing.  Candidate authorization is an identity of the tree Git will commit;
the separately hashed patch is review evidence only.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import tempfile
import time
from typing import Callable, Mapping, Sequence


CANDIDATE_SCHEMA = "forge-commit-candidate/2"
CANDIDATE_DOMAIN = b"forge-commit-candidate/2\0"
ENUMERATION_MAX_BYTES = 16 * 1024 * 1024
REVIEW_DIFF_MAX_BYTES = 16 * 1024 * 1024
COMMIT_OBJECT_MAX_BYTES = 16 * 1024 * 1024
DIAGNOSTIC_MAX_BYTES = 64 * 1024
GIT_TIMEOUT_SECONDS = 120.0

_OBJECT_FORMAT_LENGTHS = {"sha1": 40, "sha256": 64}
_DISCOVERY_MAX_BYTES = 4096
_SCOPE_MAGIC_CHARS = "*?["
_TRANSIENT_SCOPE_ROOTS = (".forge", ".codex-orchestrator", ".worktrees")
_SANITIZED_EXACT = {
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_REPLACE_REF_BASE",
    "GIT_EXTERNAL_DIFF",
    "GIT_DIFF_OPTS",
    "GIT_LITERAL_PATHSPECS",
    "GIT_GLOB_PATHSPECS",
    "GIT_NOGLOB_PATHSPECS",
    "GIT_ICASE_PATHSPECS",
    "GIT_ATTR_NOSYSTEM",
    "GIT_ATTR_SOURCE",
}


class CandidateError(RuntimeError):
    """A fail-closed candidate-plumbing error with a stable control class."""

    def __init__(self, message: str, *, kind: str = "evidence-incomplete") -> None:
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True)
class GitContext:
    """One resolved worktree/index identity used by every post-discovery call."""

    worktree_root: Path
    git_dir: Path
    common_dir: Path
    index_file: Path
    bare: bool = False
    base_environment: Mapping[str, str] | None = None

    def environment(self) -> dict[str, str]:
        source = dict(
            self.base_environment if self.base_environment is not None else os.environ
        )
        for key in tuple(source):
            if key in _SANITIZED_EXACT or key.startswith("GIT_CONFIG_"):
                source.pop(key, None)
        for key in ("GIT_DIR", "GIT_COMMON_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE"):
            source.pop(key, None)
        source["GIT_DIR"] = str(self.git_dir)
        source["GIT_COMMON_DIR"] = str(self.common_dir)
        source["GIT_INDEX_FILE"] = str(self.index_file)
        if not self.bare:
            source["GIT_WORK_TREE"] = str(self.worktree_root)
        source["GIT_NO_REPLACE_OBJECTS"] = "1"
        source["GIT_OPTIONAL_LOCKS"] = "0"
        source["LC_ALL"] = "C"
        source["LANG"] = "C"
        source["GIT_PAGER"] = "cat"
        return source


@dataclass(frozen=True)
class CandidateObservation:
    object_format: str
    tree_oid: str
    authorization_id: str


@dataclass(frozen=True)
class CandidateSnapshot:
    schema: str
    object_format: str
    tree_oid: str
    authorization_id: str
    base_commit_oid: str | None
    base_tree_oid: str
    review_diff_sha256: str
    review_diff_byte_count: int
    paths: tuple[str, ...]
    path_bytes: tuple[bytes, ...]
    review_diff: bytes
    computed_at: str

    def state_record(self) -> dict[str, object]:
        """Return the DM-012 nested record, retaining ``sha256`` as a v1 key."""

        return {
            "schema": self.schema,
            "sha256": self.authorization_id,
            "authorization_id": self.authorization_id,
            "object_format": self.object_format,
            "tree_oid": self.tree_oid,
            "base_commit_oid": self.base_commit_oid,
            "review_diff_sha256": self.review_diff_sha256,
            "review_diff_byte_count": self.review_diff_byte_count,
            "computed_at": self.computed_at,
        }


@dataclass(frozen=True)
class CommitObject:
    sha: str
    tree_headers: tuple[str, ...]
    parent_headers: tuple[str, ...]
    message: bytes
    raw: bytes


@dataclass(frozen=True)
class AuthorizationMarker:
    authorization_id: str
    object_format: str
    tree_oid: str
    authorized_at: datetime
    skip: bool = False
    fast_policy: str | None = None


@dataclass(frozen=True)
class TreeEntry:
    mode: str
    object_type: str
    oid: str
    path: str


@dataclass(frozen=True)
class _GitResult:
    returncode: int
    stdout: bytes
    stderr: bytes


def _terminate(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        if process.poll() is None:
            try:
                process.terminate()
            except OSError:
                return


def _kill(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        if process.poll() is None:
            try:
                process.kill()
            except OSError:
                return


def _run_bounded(
    argv: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    stdout_limit: int,
    stderr_limit: int = DIAGNOSTIC_MAX_BYTES,
    input_bytes: bytes | None = None,
    timeout: float = GIT_TIMEOUT_SECONDS,
) -> _GitResult:
    """Run one process while retaining at most each ceiling plus one probe byte."""

    if stdout_limit < 0 or stderr_limit < 0 or timeout <= 0:
        raise CandidateError("invalid bounded Git execution parameters")
    try:
        process = subprocess.Popen(
            list(argv),
            cwd=str(cwd),
            env=dict(env),
            stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except OSError as exc:
        raise CandidateError(f"Git plumbing could not be launched: {exc}") from exc
    assert process.stdout is not None and process.stderr is not None
    os.set_blocking(process.stdout.fileno(), False)
    os.set_blocking(process.stderr.fileno(), False)
    if input_bytes is not None:
        assert process.stdin is not None
        try:
            process.stdin.write(input_bytes)
            process.stdin.close()
        except (BrokenPipeError, OSError):
            pass

    streams = selectors.DefaultSelector()
    streams.register(process.stdout, selectors.EVENT_READ, ("stdout", stdout_limit))
    streams.register(process.stderr, selectors.EVENT_READ, ("stderr", stderr_limit))
    buffers: dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}
    overflow: str | None = None
    deadline = time.monotonic() + timeout
    terminated_at: float | None = None
    try:
        while streams.get_map():
            now = time.monotonic()
            if now >= deadline and terminated_at is None:
                _terminate(process)
                terminated_at = now
            if terminated_at is not None and now - terminated_at >= 1.0:
                _kill(process)
            events = streams.select(0.05)
            if not events and process.poll() is not None:
                events = [
                    (selectors.SelectorKey(fileobj=key.fileobj, fd=key.fd, events=key.events, data=key.data), 0)
                    for key in list(streams.get_map().values())
                ]
            for key, _mask in events:
                name, limit = key.data
                try:
                    chunk = os.read(key.fd, 65536)
                except (InterruptedError, BlockingIOError):
                    continue
                except OSError:
                    chunk = b""
                if not chunk:
                    try:
                        streams.unregister(key.fileobj)
                    except (KeyError, ValueError):
                        pass
                    continue
                retained = buffers[name]
                remaining = limit + 1 - len(retained)
                if remaining > 0:
                    retained.extend(chunk[:remaining])
                if len(retained) > limit and overflow is None:
                    overflow = name
                    _terminate(process)
                    terminated_at = time.monotonic()
        try:
            returncode = process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            _kill(process)
            returncode = process.wait()
    finally:
        streams.close()
        for stream in (process.stdout, process.stderr):
            try:
                stream.close()
            except OSError:
                pass
    if overflow is not None:
        raise CandidateError(f"Git plumbing {overflow} exceeded its byte ceiling")
    if terminated_at is not None and time.monotonic() >= deadline:
        raise CandidateError("Git plumbing timed out")
    return _GitResult(returncode, bytes(buffers["stdout"]), bytes(buffers["stderr"]))


def _diagnostic(result: _GitResult) -> str:
    return result.stderr.decode("utf-8", "replace").strip() or f"exit {result.returncode}"


def _git(
    context: GitContext,
    arguments: Sequence[str],
    *,
    stdout_limit: int,
    input_bytes: bytes | None = None,
    check: bool = True,
) -> _GitResult:
    result = _run_bounded(
        ["git", *arguments],
        cwd=context.worktree_root,
        env=context.environment(),
        stdout_limit=stdout_limit,
        input_bytes=input_bytes,
    )
    if check and result.returncode != 0:
        raise CandidateError(f"git {' '.join(arguments)} failed: {_diagnostic(result)}")
    return result


def git_output(
    context: GitContext,
    arguments: Sequence[str],
    *,
    stdout_limit: int,
    input_bytes: bytes | None = None,
) -> bytes:
    """Run bounded Git plumbing in an already-discovered pinned context."""

    return _git(
        context,
        arguments,
        stdout_limit=stdout_limit,
        input_bytes=input_bytes,
    ).stdout


def _isolated_object_git(
    context: GitContext,
    arguments: Sequence[str],
    *,
    object_format: str,
    attribute_source: str,
    stdout_limit: int,
) -> _GitResult:
    """Run object-only plumbing without repository/user presentation config.

    Tree diffs otherwise consult the live worktree's attributes, the mutable
    ``info/attributes`` file, and arbitrary ``diff.<driver>`` configuration.
    A minimal temporary Git directory keeps those presentation inputs out while
    the explicitly pinned object directory supplies only immutable objects.
    """

    if object_format not in _OBJECT_FORMAT_LENGTHS or not _valid_oid(
        attribute_source, object_format
    ):
        raise CandidateError("isolated Git object context is malformed")
    with tempfile.TemporaryDirectory(prefix="forge-candidate-objects-") as raw_temp:
        temporary_git = Path(raw_temp)
        (temporary_git / "refs" / "heads").mkdir(parents=True)
        (temporary_git / "HEAD").write_text(
            "ref: refs/heads/forge-candidate\n", encoding="ascii"
        )
        config = (
            "[core]\n"
            f"\trepositoryformatversion = {1 if object_format != 'sha1' else 0}\n"
            "\tbare = true\n"
        )
        if object_format != "sha1":
            config += f"[extensions]\n\tobjectFormat = {object_format}\n"
        (temporary_git / "config").write_text(config, encoding="ascii")
        environment = context.environment()
        for key in (
            "GIT_WORK_TREE",
            "GIT_INDEX_FILE",
            "GIT_COMMON_DIR",
        ):
            environment.pop(key, None)
        environment["GIT_DIR"] = str(temporary_git)
        # This is a resolved repository-owned object database, never an inherited
        # override. Its on-disk alternates file remains legitimate repo structure.
        environment["GIT_OBJECT_DIRECTORY"] = str(context.common_dir / "objects")
        environment["GIT_CONFIG_NOSYSTEM"] = "1"
        environment["GIT_CONFIG_GLOBAL"] = os.devnull
        environment["GIT_CONFIG_SYSTEM"] = os.devnull
        environment["HOME"] = raw_temp
        environment["XDG_CONFIG_HOME"] = raw_temp
        environment["GIT_ATTR_NOSYSTEM"] = "1"
        environment["GIT_ATTR_SOURCE"] = attribute_source
        result = _run_bounded(
            ["git", *arguments],
            cwd=context.worktree_root,
            env=environment,
            stdout_limit=stdout_limit,
        )
        if result.returncode != 0:
            raise CandidateError(
                f"git {' '.join(arguments)} failed: {_diagnostic(result)}"
            )
        return result


def _single_line_ascii(raw: bytes, label: str) -> str:
    if not raw.endswith(b"\n") or raw.count(b"\n") != 1:
        raise CandidateError(f"Git returned malformed {label}")
    try:
        return raw[:-1].decode("ascii")
    except UnicodeDecodeError as exc:
        raise CandidateError(f"Git returned malformed {label}") from exc


def _valid_oid(value: str, object_format: str) -> bool:
    length = _OBJECT_FORMAT_LENGTHS.get(object_format)
    return bool(length and re.fullmatch(rf"[0-9a-f]{{{length}}}", value))


def _object_format(context: GitContext) -> str:
    result = _git(
        context,
        ["--no-pager", "--no-replace-objects", "rev-parse", "--show-object-format"],
        stdout_limit=32,
    )
    value = _single_line_ascii(result.stdout, "object format")
    if value not in _OBJECT_FORMAT_LENGTHS:
        raise CandidateError("Git returned an unsupported object format")
    return value


def _write_index_tree(context: GitContext, object_format: str) -> str:
    # `git write-tree` is logically read-only but may refresh the cache-tree
    # extension in the index it opens.  Run it against an exact owner-controlled
    # copy so candidate observation never changes the real worktree index.
    with tempfile.TemporaryDirectory(prefix="forge-candidate-index-") as raw_temp:
        temporary_index = Path(raw_temp) / "index"
        source_descriptor: int | None = None
        destination_descriptor: int | None = None
        try:
            try:
                source_descriptor = os.open(
                    context.index_file,
                    os.O_RDONLY
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_CLOEXEC", 0),
                )
            except FileNotFoundError:
                source_descriptor = None
            if source_descriptor is not None:
                before = os.fstat(source_descriptor)
                if not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid():
                    raise CandidateError("Git index is not an owner-controlled regular file")
                destination_descriptor = os.open(
                    temporary_index,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
                    0o600,
                )
                copied = 0
                while True:
                    chunk = os.read(source_descriptor, 1024 * 1024)
                    if not chunk:
                        break
                    view = memoryview(chunk)
                    while view:
                        written = os.write(destination_descriptor, view)
                        if written <= 0:
                            raise CandidateError("Git index snapshot write was incomplete")
                        view = view[written:]
                        copied += written
                after = os.fstat(source_descriptor)
                stable_fields = (
                    "st_dev",
                    "st_ino",
                    "st_mode",
                    "st_uid",
                    "st_size",
                    "st_mtime_ns",
                    "st_ctime_ns",
                )
                if (
                    copied != before.st_size
                    or any(getattr(before, name) != getattr(after, name) for name in stable_fields)
                ):
                    raise CandidateError("Git index changed during candidate observation")
                os.fsync(destination_descriptor)
        except OSError as exc:
            raise CandidateError(f"Git index could not be snapshotted: {exc}") from exc
        finally:
            for descriptor in (destination_descriptor, source_descriptor):
                if descriptor is not None:
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass
        temporary_context = replace(context, index_file=temporary_index)
        result = _git(
            temporary_context,
            ["--no-pager", "--no-replace-objects", "write-tree"],
            stdout_limit=80,
        )
    tree_oid = _single_line_ascii(result.stdout, "tree OID")
    if not _valid_oid(tree_oid, object_format):
        raise CandidateError("Git returned a malformed tree OID")
    return tree_oid


def authorization_id(object_format: str, tree_oid: str) -> str:
    if object_format not in _OBJECT_FORMAT_LENGTHS or not _valid_oid(tree_oid, object_format):
        raise CandidateError("candidate tree identity is malformed")
    preimage = CANDIDATE_DOMAIN + object_format.encode("ascii") + b"\0" + tree_oid.encode("ascii") + b"\n"
    return hashlib.sha256(preimage).hexdigest()


def observe_index(context: GitContext) -> CandidateObservation:
    object_format = _object_format(context)
    tree_oid = CANDIDATE_CONTROLS["pinned-index-tree"](context, object_format)
    return CandidateObservation(
        object_format=object_format,
        tree_oid=tree_oid,
        authorization_id=authorization_id(object_format, tree_oid),
    )


def _base_identity(context: GitContext, object_format: str) -> tuple[str | None, str]:
    head = _git(
        context,
        ["--no-pager", "--no-replace-objects", "rev-parse", "--verify", "HEAD^{commit}"],
        stdout_limit=80,
        check=False,
    )
    if head.returncode == 0:
        commit_oid = _single_line_ascii(head.stdout, "HEAD OID")
        if not _valid_oid(commit_oid, object_format):
            raise CandidateError("Git returned a malformed HEAD OID")
        return commit_oid, resolve_base_tree(
            context, commit_oid, object_format=object_format
        )
    symbolic = _git(
        context,
        ["--no-pager", "--no-replace-objects", "symbolic-ref", "-q", "HEAD"],
        stdout_limit=1024,
        check=False,
    )
    if symbolic.returncode != 0:
        raise CandidateError(f"Git HEAD cannot be resolved: {_diagnostic(head)}")
    symbolic_ref = _single_line_ascii(symbolic.stdout, "symbolic HEAD")
    exists = _git(
        context,
        [
            "--no-pager",
            "--no-replace-objects",
            "show-ref",
            "--verify",
            "--quiet",
            symbolic_ref,
        ],
        stdout_limit=1,
        check=False,
    )
    if exists.returncode != 1:
        raise CandidateError(f"Git HEAD cannot be resolved: {_diagnostic(head)}")
    return None, resolve_base_tree(context, None, object_format=object_format)


def base_identity(context: GitContext) -> tuple[str | None, str]:
    """Return the replacement-proof current HEAD commit and its tree."""

    object_format = _object_format(context)
    return _base_identity(context, object_format)


def resolve_base_tree(
    context: GitContext,
    base_commit_oid: str | None,
    *,
    object_format: str | None = None,
) -> str:
    """Resolve a recorded base commit to its tree, including an unborn base."""

    resolved_format = object_format or _object_format(context)
    if resolved_format not in _OBJECT_FORMAT_LENGTHS:
        raise CandidateError("Git returned an unsupported object format")
    if base_commit_oid is None:
        result = _git(
            context,
            ["--no-pager", "--no-replace-objects", "mktree"],
            stdout_limit=80,
            input_bytes=b"",
        )
        label = "empty tree OID"
    else:
        if not _valid_oid(base_commit_oid, resolved_format):
            raise CandidateError("candidate base commit identity is malformed")
        result = _git(
            context,
            [
                "--no-pager",
                "--no-replace-objects",
                "rev-parse",
                "--verify",
                f"{base_commit_oid}^{{tree}}",
            ],
            stdout_limit=80,
        )
        label = "base tree OID"
    tree_oid = _single_line_ascii(result.stdout, label)
    if not _valid_oid(tree_oid, resolved_format):
        raise CandidateError(f"Git returned a malformed {label}")
    return tree_oid


def _enumerate_paths(
    context: GitContext, base_tree_oid: str, candidate_tree_oid: str
) -> tuple[tuple[bytes, ...], tuple[str, ...]]:
    result = _git(
        context,
        [
            "--no-pager",
            "--no-replace-objects",
            "diff-tree",
            "-r",
            "--no-commit-id",
            "--name-only",
            "-z",
            "--no-renames",
            "--no-ext-diff",
            "--no-textconv",
            "--ignore-submodules=none",
            base_tree_oid,
            candidate_tree_oid,
            "--",
        ],
        stdout_limit=ENUMERATION_MAX_BYTES,
    )
    raw = result.stdout
    if raw and not raw.endswith(b"\0"):
        raise CandidateError("Git returned malformed NUL-framed candidate paths")
    parts = raw.split(b"\0")
    if raw and (parts[-1] != b"" or any(not value for value in parts[:-1])):
        raise CandidateError("Git returned malformed NUL-framed candidate paths")
    values = parts[:-1] if raw else []
    if len(values) != len(set(values)):
        raise CandidateError("Git returned duplicate candidate paths")
    ordered = tuple(sorted(values))
    decoded: list[str] = []
    for value in ordered:
        try:
            label = value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CandidateError("candidate pathname is not valid UTF-8") from exc
        if os.fsencode(os.fsdecode(value)) != value:
            raise CandidateError("candidate pathname cannot round-trip through the filesystem")
        decoded.append(label)
    return ordered, tuple(decoded)


def _render_review_patch(
    context: GitContext, base_tree_oid: str, candidate_tree_oid: str
) -> bytes:
    # The isolated context removes live attributes, info/attributes, user/repo
    # configuration, and arbitrary diff-driver settings. GIT_ATTR_SOURCE binds
    # committed attributes to the immutable candidate tree.
    object_format = _object_format(context)
    result = _isolated_object_git(
        context,
        [
            "--no-pager",
            "--no-replace-objects",
            "-c",
            "diff.noprefix=false",
            "-c",
            "diff.mnemonicPrefix=false",
            "-c",
            "core.quotePath=true",
            "-c",
            "diff.suppressBlankEmpty=false",
            "diff-tree",
            "-r",
            "--no-commit-id",
            "-p",
            "--binary",
            "--full-index",
            "--no-renames",
            "--no-ext-diff",
            "--no-textconv",
            "--ignore-submodules=none",
            "--submodule=short",
            "--no-color",
            "--no-relative",
            "--src-prefix=a/",
            "--dst-prefix=b/",
            "--line-prefix=",
            "--unified=3",
            "--inter-hunk-context=0",
            "--diff-algorithm=myers",
            "--no-indent-heuristic",
            "-O",
            os.devnull,
            base_tree_oid,
            candidate_tree_oid,
            "--",
        ],
        object_format=object_format,
        attribute_source=candidate_tree_oid,
        stdout_limit=REVIEW_DIFF_MAX_BYTES,
    )
    return result.stdout


def snapshot(context: GitContext, *, computed_at: str) -> CandidateSnapshot:
    object_format = _object_format(context)
    base_commit_oid, base_tree_oid = _base_identity(context, object_format)
    tree_oid = CANDIDATE_CONTROLS["pinned-index-tree"](context, object_format)
    observation = CandidateObservation(
        object_format=object_format,
        tree_oid=tree_oid,
        authorization_id=authorization_id(object_format, tree_oid),
    )
    repeated_base_commit, repeated_base_tree = _base_identity(
        context, observation.object_format
    )
    if (repeated_base_commit, repeated_base_tree) != (base_commit_oid, base_tree_oid):
        raise CandidateError("Git HEAD changed during candidate snapshot")
    path_bytes, paths = enumerate_tree_pair(
        context, base_tree_oid, observation.tree_oid
    )
    review_diff = render_tree_pair(context, base_tree_oid, observation.tree_oid)
    return CandidateSnapshot(
        schema=CANDIDATE_SCHEMA,
        object_format=observation.object_format,
        tree_oid=observation.tree_oid,
        authorization_id=observation.authorization_id,
        base_commit_oid=base_commit_oid,
        base_tree_oid=base_tree_oid,
        review_diff_sha256=hashlib.sha256(review_diff).hexdigest(),
        review_diff_byte_count=len(review_diff),
        paths=paths,
        path_bytes=path_bytes,
        review_diff=review_diff,
        computed_at=computed_at,
    )


def index_paths(context: GitContext) -> tuple[str, ...]:
    """Enumerate the live index candidate without rendering review evidence."""

    object_format = _object_format(context)
    base_commit_oid, base_tree_oid = _base_identity(context, object_format)
    tree_oid = CANDIDATE_CONTROLS["pinned-index-tree"](context, object_format)
    repeated_base_commit, repeated_base_tree = _base_identity(context, object_format)
    if (repeated_base_commit, repeated_base_tree) != (base_commit_oid, base_tree_oid):
        raise CandidateError("Git HEAD changed during candidate path enumeration")
    _path_bytes, paths = enumerate_tree_pair(context, base_tree_oid, tree_oid)
    return paths


def _read_raw_commit(context: GitContext, commit_sha: str) -> bytes:
    object_format = _object_format(context)
    if not _valid_oid(commit_sha, object_format):
        raise CandidateError("produced commit OID is malformed")
    result = _git(
        context,
        ["--no-pager", "--no-replace-objects", "cat-file", "commit", commit_sha],
        stdout_limit=COMMIT_OBJECT_MAX_BYTES,
    )
    return result.stdout


def read_commit_object(context: GitContext, commit_sha: str) -> CommitObject:
    object_format = _object_format(context)
    if not _valid_oid(commit_sha, object_format):
        raise CandidateError("produced commit OID is malformed")
    raw = CANDIDATE_CONTROLS["raw-produced-object-reading"](context, commit_sha)
    if not isinstance(raw, bytes) or len(raw) > COMMIT_OBJECT_MAX_BYTES:
        raise CandidateError("Git plumbing stdout exceeded its byte ceiling")
    if b"\n\n" not in raw:
        raise CandidateError("produced commit object is malformed")
    header, message = raw.split(b"\n\n", 1)
    if not header or b"\x00" in header or b"\r" in header:
        raise CandidateError("produced commit object is malformed")
    tree_headers: list[str] = []
    parent_headers: list[str] = []
    header_counts: dict[bytes, int] = {}
    previous_key: bytes | None = None
    for line in header.split(b"\n"):
        if line.startswith(b" "):
            if previous_key is None or previous_key in {b"tree", b"parent"}:
                raise CandidateError("produced commit object is malformed")
            continue
        key, separator, value = line.partition(b" ")
        if (
            separator != b" "
            or not value
            or re.fullmatch(rb"[a-z][a-z0-9-]*", key) is None
        ):
            raise CandidateError("produced commit object is malformed")
        previous_key = key
        header_counts[key] = header_counts.get(key, 0) + 1
        if key == b"tree":
            try:
                tree_oid = value.decode("ascii")
            except UnicodeDecodeError as exc:
                raise CandidateError("produced commit tree header is malformed") from exc
            if not _valid_oid(tree_oid, object_format):
                raise CandidateError("produced commit tree header is malformed")
            tree_headers.append(tree_oid)
        elif key == b"parent":
            try:
                parent_oid = value.decode("ascii")
            except UnicodeDecodeError as exc:
                raise CandidateError("produced commit parent header is malformed") from exc
            if not _valid_oid(parent_oid, object_format):
                raise CandidateError("produced commit parent header is malformed")
            parent_headers.append(parent_oid)
    if (
        len(tree_headers) != 1
        or header_counts.get(b"author") != 1
        or header_counts.get(b"committer") != 1
    ):
        raise CandidateError("produced commit object is malformed")
    object_bytes = b"commit " + str(len(raw)).encode("ascii") + b"\x00" + raw
    if hashlib.new(object_format, object_bytes).hexdigest() != commit_sha:
        raise CandidateError("produced commit object identity is malformed")
    return CommitObject(
        sha=commit_sha,
        tree_headers=tuple(tree_headers),
        parent_headers=tuple(parent_headers),
        message=message,
        raw=raw,
    )


def render_marker(
    observation: CandidateObservation,
    authorized_at: str,
    *,
    skip: bool = False,
    fast_policy: str | None = None,
) -> bytes:
    """Render one exact LF-terminated DM-006 v2 marker."""

    if skip and fast_policy is not None:
        raise CandidateError("marker annotations are mutually exclusive")
    try:
        parsed_at = datetime.strptime(authorized_at, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise CandidateError("marker authorization timestamp is malformed") from exc
    del parsed_at
    if fast_policy is not None and re.fullmatch(
        r"(?:[0-9a-f]{40}|[0-9a-f]{64})", fast_policy
    ) is None:
        raise CandidateError("marker fast policy is malformed")
    lines = [
        f"format: {CANDIDATE_SCHEMA}",
        f"candidate: {observation.authorization_id}",
        f"tree: {observation.object_format}:{observation.tree_oid}",
        f"authorized-at: {authorized_at}",
    ]
    if skip:
        lines.append("skip: user-directed")
    elif fast_policy is not None:
        lines.extend(("tier: fast", f"policy: {fast_policy}"))
    return ("\n".join(lines) + "\n").encode("ascii")


def parse_marker(
    raw: bytes,
    *,
    filename: str,
    observation: CandidateObservation,
    now: datetime | None = None,
) -> tuple[AuthorizationMarker | None, str | None]:
    """Parse a selected v2 marker and return the existing denial suffix."""

    if (
        not raw.endswith(b"\n")
        or b"\r" in raw
        or b"\0" in raw
        or raw.count(b"\n") not in {4, 5, 6}
    ):
        return None, "marker malformed"
    try:
        lines = raw[:-1].decode("ascii").split("\n")
    except UnicodeDecodeError:
        return None, "marker malformed"
    if len(lines) not in {4, 5, 6} or lines[0] != f"format: {CANDIDATE_SCHEMA}":
        return None, "marker malformed"
    if not lines[1].startswith("candidate: ") or not lines[2].startswith("tree: "):
        return None, "marker malformed"
    if not lines[3].startswith("authorized-at: "):
        return None, "marker malformed"
    marker_id = lines[1][len("candidate: ") :]
    tree_value = lines[2][len("tree: ") :]
    if ":" not in tree_value:
        return None, "marker malformed"
    object_format, tree_oid = tree_value.split(":", 1)
    oid_length = _OBJECT_FORMAT_LENGTHS.get(object_format)
    if (
        re.fullmatch(r"[0-9a-f]{64}", marker_id) is None
        or oid_length is None
        or re.fullmatch(rf"[0-9a-f]{{{oid_length}}}", tree_oid) is None
    ):
        return None, "marker malformed"
    skip = False
    fast_policy: str | None = None
    if len(lines) == 5:
        if lines[4] != "skip: user-directed":
            return None, "marker malformed"
        skip = True
    elif len(lines) == 6:
        if lines[4] != "tier: fast" or not lines[5].startswith("policy: "):
            return None, "marker malformed"
        fast_policy = lines[5][len("policy: ") :]
        if re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", fast_policy) is None:
            return None, "marker malformed"
    try:
        authorized_at = datetime.strptime(
            lines[3][len("authorized-at: ") :], "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc)
    except ValueError:
        return None, "marker malformed"
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    age_seconds = (current - authorized_at).total_seconds()
    if age_seconds < -120:
        return None, "marker malformed"
    if age_seconds > 1800:
        return None, "marker stale"
    try:
        derived = authorization_id(object_format, tree_oid)
    except CandidateError:
        return None, "marker malformed"
    if (
        filename != marker_id
        or marker_id != derived
        or marker_id != observation.authorization_id
        or object_format != observation.object_format
        or tree_oid != observation.tree_oid
    ):
        return None, "marker hash mismatch"
    return (
        AuthorizationMarker(
            authorization_id=marker_id,
            object_format=object_format,
            tree_oid=tree_oid,
            authorized_at=authorized_at,
            skip=skip,
            fast_policy=fast_policy,
        ),
        None,
    )


def marker_timestamp_for_cleanup(raw: bytes) -> datetime | None:
    """Return a strict v2 or legacy timestamp solely for stale cleanup."""

    if not raw.endswith(b"\n") or b"\r" in raw or b"\0" in raw:
        return None
    try:
        lines = raw[:-1].decode("ascii").split("\n")
    except UnicodeDecodeError:
        return None
    value: str | None = None
    if len(lines) in {4, 5, 6} and lines[0] == f"format: {CANDIDATE_SCHEMA}":
        if lines[3].startswith("authorized-at: "):
            value = lines[3][len("authorized-at: ") :]
    elif len(lines) in {2, 3, 4} and re.fullmatch(r"[0-9a-f]{64}", lines[0]):
        value = lines[1]
    if value is None:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


def valid_scope_path(value: object) -> bool:
    """Mirror the committed run-journal contract for one concrete Git path.

    Candidate installation uses this shared predicate for run-bound chains so
    a broad requested directory cannot smuggle a path that retrospective
    journal ingest would later reject. Archive-only and unbound candidates
    retain their separate path authority.
    """

    if not isinstance(value, str) or not value or value != value.strip():
        return False
    if value.startswith(("/", "!", "^", "-", ":", "./")):
        return False
    if "\\" in value or "\0" in value:
        return False
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return False
    first = parts[0]
    if first in _TRANSIENT_SCOPE_ROOTS or any(
        character in first for character in _SCOPE_MAGIC_CHARS
    ):
        return False
    try:
        value.encode("utf-8")
    except UnicodeError:
        return False
    return True


def enumerate_tree_pair(
    context: GitContext, base_tree_oid: str, candidate_tree_oid: str
) -> tuple[tuple[bytes, ...], tuple[str, ...]]:
    object_format = _object_format(context)
    if not _valid_oid(base_tree_oid, object_format) or not _valid_oid(
        candidate_tree_oid, object_format
    ):
        raise CandidateError("tree pair identity is malformed")
    result = CANDIDATE_CONTROLS["config-proof-tree-enumeration"](
        context, base_tree_oid, candidate_tree_oid
    )
    if not isinstance(result, tuple) or len(result) != 2:
        raise CandidateError("tree enumeration control returned malformed output")
    return result


def render_tree_pair(
    context: GitContext, base_tree_oid: str, candidate_tree_oid: str
) -> bytes:
    object_format = _object_format(context)
    if not _valid_oid(base_tree_oid, object_format) or not _valid_oid(
        candidate_tree_oid, object_format
    ):
        raise CandidateError("tree pair identity is malformed")
    result = CANDIDATE_CONTROLS["deterministic-review-patch"](
        context, base_tree_oid, candidate_tree_oid
    )
    if not isinstance(result, bytes):
        raise CandidateError("review patch control returned malformed output")
    return result


def name_status_tree_pair(
    context: GitContext, base_tree_oid: str, candidate_tree_oid: str
) -> bytes:
    object_format = _object_format(context)
    if not _valid_oid(base_tree_oid, object_format) or not _valid_oid(
        candidate_tree_oid, object_format
    ):
        raise CandidateError("tree pair identity is malformed")
    return _git(
        context,
        [
            "--no-pager",
            "--no-replace-objects",
            "diff-tree",
            "-r",
            "--no-commit-id",
            "--name-status",
            "-z",
            "--no-renames",
            "--no-ext-diff",
            "--no-textconv",
            "--ignore-submodules=none",
            base_tree_oid,
            candidate_tree_oid,
            "--",
        ],
        stdout_limit=ENUMERATION_MAX_BYTES,
    ).stdout


def paths_matching_pattern(
    context: GitContext,
    base_tree_oid: str,
    candidate_tree_oid: str,
    pattern: str,
) -> tuple[str, ...]:
    object_format = _object_format(context)
    if not _valid_oid(base_tree_oid, object_format) or not _valid_oid(
        candidate_tree_oid, object_format
    ):
        raise CandidateError("tree pair identity is malformed")
    result = _git(
        context,
        [
            "--no-pager",
            "--no-replace-objects",
            "diff-tree",
            "-r",
            "--no-commit-id",
            "--name-only",
            "-z",
            "--no-renames",
            "--no-ext-diff",
            "--no-textconv",
            "--ignore-submodules=none",
            base_tree_oid,
            candidate_tree_oid,
            "--",
            pattern,
        ],
        stdout_limit=ENUMERATION_MAX_BYTES,
    )
    raw = result.stdout
    parts = raw.split(b"\0")
    if raw and (parts[-1] != b"" or any(not value for value in parts[:-1])):
        raise CandidateError("Git returned malformed pattern path enumeration")
    values = parts[:-1] if raw else []
    if len(values) != len(set(values)):
        raise CandidateError("Git returned duplicate pattern path enumeration")
    ordered = tuple(sorted(values))
    try:
        decoded = tuple(value.decode("utf-8") for value in ordered)
    except UnicodeDecodeError as exc:
        raise CandidateError("candidate pathname is not valid UTF-8") from exc
    if any(
        os.fsencode(value) != raw_value
        for value, raw_value in zip(decoded, ordered)
    ):
        raise CandidateError("candidate pathname cannot round-trip through the filesystem")
    return decoded


def tree_entry(context: GitContext, tree_oid: str, path: str) -> TreeEntry | None:
    object_format = _object_format(context)
    if not _valid_oid(tree_oid, object_format) or "\0" in path:
        raise CandidateError("tree entry request is malformed")
    result = _git(
        context,
        [
            "--no-pager",
            "--no-replace-objects",
            "ls-tree",
            "-z",
            "--full-name",
            tree_oid,
            "--",
            f":(literal){path}",
        ],
        stdout_limit=ENUMERATION_MAX_BYTES,
    )
    if not result.stdout:
        return None
    if not result.stdout.endswith(b"\0") or result.stdout.count(b"\0") != 1:
        raise CandidateError("Git returned malformed tree entry")
    record = result.stdout[:-1]
    try:
        metadata, raw_path = record.split(b"\t", 1)
        mode, object_type, oid = metadata.decode("ascii").split(" ", 2)
        decoded_path = raw_path.decode("utf-8")
    except (UnicodeDecodeError, ValueError) as exc:
        raise CandidateError("Git returned malformed tree entry") from exc
    if decoded_path != path or not _valid_oid(oid, object_format):
        raise CandidateError("Git returned mismatched tree entry")
    return TreeEntry(mode=mode, object_type=object_type, oid=oid, path=decoded_path)


def tree_blob(context: GitContext, tree_oid: str, path: str) -> bytes | None:
    entry = tree_entry(context, tree_oid, path)
    if entry is None or entry.object_type != "blob":
        return None
    return _git(
        context,
        ["--no-pager", "--no-replace-objects", "cat-file", "blob", entry.oid],
        stdout_limit=REVIEW_DIFF_MAX_BYTES,
    ).stdout


def context_from_paths(
    *,
    worktree_root: Path,
    git_dir: Path,
    common_dir: Path,
    index_file: Path,
    bare: bool = False,
    environment: Mapping[str, str] | None = None,
    effective_cwd: Path | None = None,
) -> GitContext:
    invocation_root = Path(
        os.path.realpath(effective_cwd if effective_cwd is not None else Path.cwd())
    )

    def resolved(value: Path, *, canonical: bool) -> Path:
        selected = value if value.is_absolute() else invocation_root / value
        normalized = os.path.realpath(selected) if canonical else os.path.abspath(
            os.path.normpath(selected)
        )
        return Path(normalized)

    return GitContext(
        worktree_root=resolved(worktree_root, canonical=True),
        git_dir=resolved(git_dir, canonical=True),
        common_dir=resolved(common_dir, canonical=True),
        index_file=resolved(index_file, canonical=False),
        bare=bare,
        base_environment=dict(environment if environment is not None else os.environ),
    )


def _discover_raw_line(
    root: Path, environment: Mapping[str, str], arguments: Sequence[str], label: str
) -> bytes:
    result = _run_bounded(
        ["git", *arguments],
        cwd=root,
        env=environment,
        stdout_limit=_DISCOVERY_MAX_BYTES,
    )
    if result.returncode != 0:
        raise CandidateError(f"cannot resolve Git {label}: {_diagnostic(result)}")
    raw = result.stdout
    if not raw.endswith(b"\n") or raw.count(b"\n") != 1 or b"\0" in raw:
        raise CandidateError(f"Git returned malformed {label}")
    return raw[:-1]


def _discover_line(
    root: Path, environment: Mapping[str, str], arguments: Sequence[str], label: str
) -> str:
    raw = _discover_raw_line(root, environment, arguments, label)
    try:
        return raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise CandidateError(f"Git returned malformed {label}") from exc


def _discover_path(
    root: Path, environment: Mapping[str, str], arguments: Sequence[str], label: str
) -> str:
    return os.fsdecode(_discover_raw_line(root, environment, arguments, label))


def discover_context(
    root: Path, *, environment: Mapping[str, str] | None = None
) -> GitContext:
    """Resolve context with caller Git overrides, then sanitize every consumer."""

    cwd = Path(os.path.realpath(root))
    discovery_env = dict(environment if environment is not None else os.environ)
    bare = _discover_line(
        cwd, discovery_env, ["rev-parse", "--is-bare-repository"], "bare state"
    ) == "true"
    top = (
        cwd
        if bare
        else Path(
            _discover_path(
                cwd, discovery_env, ["rev-parse", "--show-toplevel"], "worktree root"
            )
        )
    )
    git_dir_raw = _discover_path(
        cwd, discovery_env, ["rev-parse", "--absolute-git-dir"], "Git directory"
    )
    common_raw_result = _run_bounded(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=cwd,
        env=discovery_env,
        stdout_limit=_DISCOVERY_MAX_BYTES,
    )
    if common_raw_result.returncode == 0:
        raw = common_raw_result.stdout
        if not raw.endswith(b"\n") or raw.count(b"\n") != 1 or b"\0" in raw:
            raise CandidateError("Git returned malformed Git common directory")
        common_raw = os.fsdecode(raw[:-1])
    else:
        common_raw = _discover_path(
            cwd, discovery_env, ["rev-parse", "--git-common-dir"], "Git common directory"
        )
    index_result = _run_bounded(
        ["git", "rev-parse", "--path-format=absolute", "--git-path", "index"],
        cwd=cwd,
        env=discovery_env,
        stdout_limit=_DISCOVERY_MAX_BYTES,
    )
    if index_result.returncode == 0:
        raw = index_result.stdout
        if not raw.endswith(b"\n") or raw.count(b"\n") != 1 or b"\0" in raw:
            raise CandidateError("Git returned malformed Git index")
        index_raw = os.fsdecode(raw[:-1])
    else:
        index_raw = _discover_path(
            cwd, discovery_env, ["rev-parse", "--git-path", "index"], "Git index"
        )

    def absolute(value: str) -> Path:
        candidate = Path(value)
        return candidate if candidate.is_absolute() else cwd / candidate

    return context_from_paths(
        worktree_root=top,
        git_dir=absolute(git_dir_raw),
        common_dir=absolute(common_raw),
        index_file=absolute(index_raw),
        bare=bare,
        environment=discovery_env,
        effective_cwd=cwd,
    )


CANDIDATE_CONTROLS: dict[str, Callable[..., object]] = {
    "pinned-index-tree": _write_index_tree,
    "config-proof-tree-enumeration": _enumerate_paths,
    "deterministic-review-patch": _render_review_patch,
    "raw-produced-object-reading": _read_raw_commit,
}


__all__ = [
    "CANDIDATE_CONTROLS",
    "CANDIDATE_SCHEMA",
    "AuthorizationMarker",
    "CandidateError",
    "CandidateObservation",
    "CandidateSnapshot",
    "CommitObject",
    "GitContext",
    "TreeEntry",
    "authorization_id",
    "base_identity",
    "context_from_paths",
    "discover_context",
    "enumerate_tree_pair",
    "git_output",
    "index_paths",
    "marker_timestamp_for_cleanup",
    "name_status_tree_pair",
    "observe_index",
    "parse_marker",
    "paths_matching_pattern",
    "read_commit_object",
    "resolve_base_tree",
    "render_tree_pair",
    "render_marker",
    "snapshot",
    "tree_blob",
    "tree_entry",
    "valid_scope_path",
]
