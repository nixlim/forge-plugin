"""Provider-neutral preparation and launch for detached Forge reviewers."""

from __future__ import annotations

import dataclasses
import errno
import os
import stat
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import route_config
import route_evidence
import route_floor

from forge_cli import chain_core
from forge_cli.engine import _review_lane_api
from forge_cli.engine._state import CLAUDE_EXECUTABLE as CLAUDE_EXECUTABLE
from forge_cli.engine._state import CODEX_EXECUTABLE as CODEX_EXECUTABLE
from forge_cli.envelope import FrozenError, ReasonCode, Refusal
from forge_cli.policy import sha256_bytes

PROFILE_TIMEOUT_SECONDS = {"review": 2400, "implementer": 14400, "plan": 1200}
VERSION_PROBE_TIMEOUT_SECONDS = 10
VERSION_PROBE_LIMIT_BYTES = 4096
IDENTITY_DEADLINE_SECONDS = 60
_PROBE_SUPPORT = route_config._probe_support()
TERMINATE_GRACE_SECONDS: int = int(_PROBE_SUPPORT.TERMINATE_GRACE_SECONDS)
CODEX_NOT_LOGGED_IN: str = str(_PROBE_SUPPORT.CODEX_NOT_LOGGED_IN)
CLAUDE_NOT_LOGGED_IN: str = str(_PROBE_SUPPORT.CLAUDE_NOT_LOGGED_IN)
_ATTEMPT_NAMES = {
    "package": "package.txt", "prompt": "prompt.txt", "events": "events.jsonl",
    "stderr": "stderr.log", "identity": "identity.json",
    "completion": "completion.json", "verdict": "verdict.txt",
    "staging": "verdict.staging", "role_body": "review-final-body.md",
}


@dataclasses.dataclass(frozen=True)
class ReviewRoute:
    role: str
    provider: str
    model: str
    effort: str
    route_source: str
    route_sha256: str
    sandbox: str

    def route_fields(self) -> dict[str, str]:
        """Return exactly the five DM-018 request-route fields."""
        return {field: str(getattr(self, field)) for field in route_evidence.ROUTE_FIELDS}


@dataclasses.dataclass(frozen=True)
class ReviewPaths:
    chain_id: str
    attempt: str
    attempt_relative: str
    attempt_dir: Path
    worktree: Path
    plugin_root: Path
    package_path: Path
    prompt_path: Path
    events_path: Path
    stderr_path: Path
    identity_path: Path
    completion_path: Path
    verdict_path: Path
    staging_path: Path
    role_body_path: Path | None
    role_body: bytes
    role_body_digest: str | None

    def artifact_ref(self, name: str) -> str:
        """Return the common-root-relative durable reference for one leaf."""

        leaf = _ATTEMPT_NAMES[name]
        return (Path(".forge") / "chains" / self.chain_id / self.attempt_relative / leaf).as_posix()


@dataclasses.dataclass(frozen=True)
class ReviewLaunch:
    paths: ReviewPaths
    route: ReviewRoute
    environment: dict[str, str]
    environment_names: tuple[str, ...]
    omitted_short: tuple[str, ...]
    provider_version: str
    reviewer_argv: tuple[str, ...]
    reviewer_argv_digest: str
    prompt_digest: str
    config_json: str
    launcher_argv: tuple[str, ...]
    launcher_argv_digest: str
    attempt_fd: int

    def request_fields(self) -> dict[str, object]:
        """Return the new-lane fields shared by commit and merge requests."""

        path = self.paths
        fields: dict[str, object] = {
            "lane": "forge-review-lane/1", "attempt": path.attempt,
            "route": self.route.route_fields(), "provider": self.route.provider,
            "sandbox": self.route.sandbox,
            "argv_digest": self.reviewer_argv_digest,
            "launcher_argv_digest": self.launcher_argv_digest,
            "prompt_digest": self.prompt_digest,
            "environment_names": list(self.environment_names),
            "omitted_short": list(self.omitted_short),
        }
        for name in ("events", "stderr", "identity", "completion", "verdict", "prompt"):
            fields[f"{name}_path"] = path.artifact_ref(name)
        return fields


def _review_refusal(
    message: str,
    state: Mapping[str, Any] | None,
    *,
    expected: str = "a launchable reviewer route",
    verb: str = "review request",
) -> Refusal:
    remediation = (chain_core._forge_command(state, verb) if state is not None
                   else f"repair the reviewer route and retry forge {verb}")
    return Refusal(ReasonCode.EVIDENCE_INCOMPLETE, message, expected=expected,
                   observed=message, remediation=remediation, chain=state)


def resolve_review_route(
    ctx: chain_core.CommandContext,
    role: str,
    head: str,
    state: Mapping[str, Any] | None = None,
) -> ReviewRoute:
    try:
        resolved = route_config.resolve(Path(ctx.repo.root), role, head)
        sandbox = route_config.profile_sandbox(resolved.provider, role)
    except route_config.RouteRefusal as exc:
        raise _review_refusal(str(exc), state) from exc
    route = ReviewRoute(role, resolved.provider, resolved.model, resolved.effort,
                        resolved.route_source, resolved.route_sha256, sandbox)
    return route


def allowed_environment(
    provider: str, environ: Mapping[str, str] | None = None
) -> tuple[dict[str, str], tuple[str, ...], tuple[str, ...]]:
    admitted = _PROBE_SUPPORT._allowed_environment(provider, environ)
    omitted = tuple(sorted(name for name, value in admitted.items() if len(value.encode()) < 4))
    environment = {name: value for name, value in admitted.items() if name not in omitted}
    return environment, tuple(sorted(environment)), omitted


def _read_role_template(plugin_root: Path) -> bytes:
    source = plugin_root / "agents" / "review-final.md"
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(source, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise OSError("review-final role template is not a regular file")
        chunks: list[bytes] = []
        while chunk := os.read(descriptor, 65536):
            chunks.append(chunk)
    finally:
        os.close(descriptor)
    raw = b"".join(chunks)
    if not raw.startswith(b"---\n"):
        raise OSError("review-final role template lacks frontmatter")
    end = raw.find(b"\n---\n", 4)
    if end < 0:
        raise OSError("review-final role template has unterminated frontmatter")
    return raw[end + 5 :].replace(b"${CLAUDE_PLUGIN_ROOT}", os.fsencode(plugin_root))


def _write_owner_file(parent: int, name: str, data: bytes) -> None:
    flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_CLOEXEC", 0))
    descriptor = os.open(name, flags, 0o600, dir_fd=parent)
    try:
        os.fchmod(descriptor, 0o600)
        offset = 0
        while offset < len(data):
            written = os.write(descriptor, data[offset:])
            if written <= 0:
                raise OSError(f"short write for {name}")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.fsync(parent)


def materialize_review_final_body(plugin_root: Path, attempt_dir: Path) -> tuple[Path, bytes, str]:
    body = _read_role_template(plugin_root)
    flags = (os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_CLOEXEC", 0))
    directory = os.open(attempt_dir, flags)
    try:
        metadata = os.fstat(directory)
        if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.geteuid():
            raise OSError("review attempt directory is not owner-controlled")
        _write_owner_file(directory, _ATTEMPT_NAMES["role_body"], body)
    finally:
        os.close(directory)
    path = attempt_dir / _ATTEMPT_NAMES["role_body"]
    return path, body, sha256_bytes(body)


def prepare_review_paths(
    ctx: chain_core.CommandContext,
    chain_id: str,
    attempt_relative: str,
    worktree: Path,
    role: str,
    state: Mapping[str, Any] | None = None,
) -> ReviewPaths:
    try:
        directory: int
        _name: str
        with ctx.store.artifact_parent_descriptor(
            chain_id, f"{attempt_relative}/{_ATTEMPT_NAMES['package']}", create=True
        ) as (directory, _name):
            metadata = os.fstat(directory)
            if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.geteuid():
                raise OSError("review attempt directory is not owner-controlled")
        base = ctx.store.common_root / ".forge" / "chains" / chain_id / attempt_relative
        plugin_root = ctx.plugin_root()
        body_path: Path | None = None
        body = b""
        body_digest: str | None = None
        if role == "review-final":
            body_path, body, body_digest = materialize_review_final_body(plugin_root, base)
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise FrozenError(
                "review attempt path hierarchy is unsafe",
                chain_id=str(state["chain_id"]) if state is not None else None,
                state=str(state.get("state")) if state is not None else None,
                observed=str(exc),
            ) from exc
        message = f"forge: review request refused — review path preparation failed: {exc}"
        raise _review_refusal(message, state, expected="owner-only review attempt paths") from exc
    attempt = Path(attempt_relative).name
    paths = {name: base / leaf for name, leaf in _ATTEMPT_NAMES.items()}
    return ReviewPaths(
        chain_id, attempt, attempt_relative, base, Path(worktree), plugin_root,
        paths["package"], paths["prompt"], paths["events"], paths["stderr"],
        paths["identity"], paths["completion"], paths["verdict"], paths["staging"],
        body_path, body, body_digest,
    )


def reviewer_argv(
    provider: str,
    role: str,
    model: str,
    effort: str,
    paths: ReviewPaths,
) -> list[str]:
    if provider == "codex":
        return [
            CODEX_EXECUTABLE, "exec", "--json", "--output-last-message",
            str(paths.staging_path), "-s", "read-only", "-c", "approval_policy=never",
            "-c", f"model={model}", "-c", f"model_reasoning_effort={effort}",
            "-C", str(paths.worktree), "-",
        ]
    if provider != "claude" or role not in {"review-cheap", "review-final"}:
        raise ValueError(f"unsupported reviewer cell: {provider}/{role}")
    if role == "review-cheap":
        system_prompt = paths.plugin_root / "system/claude/prompts/review-cheap.md"
        tools = "Read,Grep,Glob,Bash"
    else:
        if paths.role_body_path is None:
            raise ValueError("review-final body was not materialized")
        system_prompt = paths.role_body_path
        tools = "Read,Bash,Glob,Grep"
    return [
        CLAUDE_EXECUTABLE, "-p", "--safe-mode", "--strict-mcp-config",
        "--output-format", "stream-json", "--verbose", "--model", model,
        "--effort", effort, "--system-prompt-file", str(system_prompt),
        "--tools", tools, "--permission-prompts", "none",
        "--dangerously-skip-permissions", "--no-session-persistence",
    ]


def probe_provider_version(
    provider: str,
    executable: str,
    environment: Mapping[str, str],
    cwd: Path,
    state: Mapping[str, Any] | None = None,
    *,
    verb: str = "review request",
) -> str:
    try:
        return route_floor.check_floor(
            provider,
            executable,
            environment,
            cwd=cwd,
            verb=verb,
            timeout_seconds=VERSION_PROBE_TIMEOUT_SECONDS,
            limit_bytes=VERSION_PROBE_LIMIT_BYTES,
            grace_seconds=TERMINATE_GRACE_SECONDS,
        )
    except route_floor.FloorRefusal as exc:
        expected = (
            f"available {executable} executable"
            if exc.kind == "unavailable"
            else "a launchable reviewer route"
        )
        raise _review_refusal(
            exc.message, state, expected=expected, verb=verb
        ) from exc


def _prepare_live_files(paths: ReviewPaths, prompt: bytes) -> None:
    flags = (os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_CLOEXEC", 0))
    directory = os.open(paths.attempt_dir, flags)
    try:
        _write_owner_file(directory, _ATTEMPT_NAMES["prompt"], prompt)
    finally:
        os.close(directory)


def _open_attempt(paths: ReviewPaths) -> int:
    return _review_lane_api.open_attempt_directory(paths.attempt_dir)


def prepare_review_launch(
    ctx: chain_core.CommandContext,
    state: Mapping[str, Any] | None,
    paths: ReviewPaths,
    route: ReviewRoute,
    prompt: bytes,
) -> ReviewLaunch:
    environment, environment_names, omitted_short = allowed_environment(route.provider)
    executable = CODEX_EXECUTABLE if route.provider == "codex" else CLAUDE_EXECUTABLE
    version = probe_provider_version(route.provider, executable, environment, paths.worktree, state)
    argv = tuple(reviewer_argv(route.provider, route.role, route.model, route.effort, paths))
    prompt_digest = sha256_bytes(prompt)
    argv_digest = ctx.command_digest(argv)
    config = {
        "attempt": paths.attempt, "provider": route.provider,
        "route_source": route.route_source, "route_sha256": route.route_sha256,
        "sandbox": route.sandbox, "argv": list(argv), "argv_digest": argv_digest,
        "prompt_digest": prompt_digest, "timeout": PROFILE_TIMEOUT_SECONDS["review"],
        "grace": TERMINATE_GRACE_SECONDS, "environment_names": list(environment_names),
        "omitted_short": list(omitted_short), "role_body_digest": paths.role_body_digest
    }
    try:
        attempt_fd = _open_attempt(paths)
    except OSError as exc:
        message = f"forge: review request refused — review launch preparation failed: {exc}"
        raise _review_refusal(message, state, expected="owner-only review launch files") from exc
    try:
        config_json, launcher_argv, launcher_argv_digest = (
            _review_lane_api.wrapper_launcher(ctx, attempt_fd, config)
        )
        _prepare_live_files(paths, prompt)
    except RuntimeError as exc:
        os.close(attempt_fd)
        message = f"forge: review request refused — review wrapper source is unavailable: {exc}"
        raise _review_refusal(message, state) from exc
    except OSError as exc:
        os.close(attempt_fd)
        message = f"forge: review request refused — review launch preparation failed: {exc}"
        raise _review_refusal(message, state, expected="owner-only review launch files") from exc
    return ReviewLaunch(
        paths, route, environment, environment_names, omitted_short, version, argv,
        argv_digest, prompt_digest, config_json, launcher_argv,
        launcher_argv_digest, attempt_fd,
    )


def close_review_launch(launch: ReviewLaunch) -> None:
    """Close a prepared launch when the owner event could not be persisted."""

    try:
        os.close(launch.attempt_fd)
    except OSError:
        pass


def launch_review_wrapper(launch: ReviewLaunch) -> subprocess.Popen[bytes]:
    """Start the detached group-leading wrapper after its owner event exists."""

    try:
        return _review_lane_api.spawn_wrapper(
            launch.launcher_argv,
            cwd=launch.paths.worktree,
            environment=launch.environment,
            attempt_fd=launch.attempt_fd,
        )
    finally:
        close_review_launch(launch)
