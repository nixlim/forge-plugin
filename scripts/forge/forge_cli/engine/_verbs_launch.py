"""Start typed implementer and plan executions through the shared launch lane."""

from __future__ import annotations

import dataclasses
import os
import shutil
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

import route_config
import route_floor

from forge_cli import chain_core
from forge_cli.engine import _launch_lane, _review_attempt, _review_lane_api, _review_launch
from forge_cli.envelope import REVISION9_OUTPUT_SCHEMA, Outcome, Refusal, V2ReasonCode
from forge_cli.policy import sha256_bytes

if TYPE_CHECKING:
    from forge_cli.engine._engine import Engine

INIT_INCOMPLETE = "forge: forge initialization incomplete — run /forge:init"


@dataclasses.dataclass(frozen=True)
class StartFacts:
    repository: Path
    run_id: str
    run_dir: Path
    task: str
    role: str
    worktree: Path
    head: str
    prompt: _launch_lane.PromptMaterial
    route: route_config.ResolvedRoute
    sandbox: str
    environment: dict[str, str]
    environment_names: tuple[str, ...]
    omitted_short: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class OwnerLaunch:
    facts: StartFacts
    draft: OwnerDraft


@dataclasses.dataclass(frozen=True)
class OwnerDraft:
    paths: _launch_lane.LaunchPaths
    marker: dict[str, Any]
    launcher_argv: tuple[str, ...]
    attempt_fd: int
    created_agent: bool


def _git_path(worktree: Path, option: str) -> Path:
    """Resolve a Git administrative path, falling back for older Git versions."""

    try:
        rendered = _launch_lane.git_text(
            worktree, "rev-parse", "--path-format=absolute", option)
    except OSError:
        rendered = _launch_lane.git_text(worktree, "rev-parse", option)
    candidate = Path(rendered)
    if not candidate.is_absolute():
        candidate = worktree / candidate
    return candidate.resolve(strict=True)


def _validate_worktree(ctx: chain_core.CommandContext, value: str, role: str) -> tuple[Path, str]:
    raw = Path(value)
    message = (
        "forge: launch refused — worktree is not a registered worktree of this "
        f"repository: {value}"
    )
    try:
        if not raw.is_absolute():
            raise OSError("relative worktree")
        worktree = raw.resolve(strict=True)
        if raw != worktree:
            raise OSError("worktree path is not canonical")
        top = Path(_launch_lane.git_text(
            worktree, "rev-parse", "--show-toplevel")).resolve(strict=True)
        common = _git_path(worktree, "--git-common-dir")
        if top != worktree or common != ctx.repo.git_common_dir():
            raise OSError("foreign worktree")
        git_dir = _git_path(worktree, "--git-dir")
        if role == "implementer" and git_dir == common:
            raise Refusal(
                V2ReasonCode.WORKTREE_INVALID,
                "forge: launch refused — implementer worktree must be a dedicated "
                f"linked worktree: {value}",
            )
        head = _launch_lane.git_text(worktree, "rev-parse", "HEAD")
        if _launch_lane.OBJECT_ID_PATTERN.fullmatch(head) is None:
            raise OSError("invalid HEAD")
        return worktree, head
    except Refusal:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise Refusal(V2ReasonCode.WORKTREE_INVALID, message) from exc


def _require_initialized(worktree: Path, head: str) -> None:
    try:
        manifest = _launch_lane.committed_file(
            worktree,
            head,
            ".forge-manifest",
        ).decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise Refusal(V2ReasonCode.STATE_PRECONDITION, INIT_INCOMPLETE) from exc
    if manifest.splitlines().count("init_completed: true") != 1:
        raise Refusal(V2ReasonCode.STATE_PRECONDITION, INIT_INCOMPLETE)


def _require_no_inflight(run: _launch_lane.RunState, worktree: Path) -> None:
    execution = _launch_lane.in_flight_execution(run, worktree)
    if execution is not None:
        raise Refusal(
            V2ReasonCode.STATE_PRECONDITION,
            f"forge: launch refused — execution {execution} is still in flight in "
            f"{worktree}; run launch collect or launch cancel",
        )


def _execution_fields(
    facts: StartFacts, paths: _launch_lane.LaunchPaths
) -> dict[str, object]:
    return {
        "agent": paths.agent,
        "provider": facts.route.provider,
        "role": facts.role,
        "mode": "detached",
        "model": facts.route.model,
        "effort": facts.route.effort,
        "worktree": str(facts.worktree),
        "head": facts.head,
        "prompt": paths.reference(_launch_lane.LAUNCH_LEAVES["prompt"]),
        "handoff": paths.reference(_launch_lane.LAUNCH_LEAVES["capture"]),
        "event_source": _launch_lane.EVENT_SOURCES[facts.route.provider],
        "events": paths.reference(_launch_lane.LAUNCH_LEAVES["events"]),
        "sandbox": facts.sandbox,
        "route_source": facts.route.route_source,
        "route_sha256": facts.route.route_sha256,
        "launch_marker": paths.reference(_launch_lane.MARKER_NAME),
    }


def _resolve_route(
    worktree: Path, head: str, role: str,
) -> tuple[route_config.ResolvedRoute, str]:
    try:
        route = route_config.resolve(worktree, role, head)
        return route, route_config.profile_sandbox(route.provider, role)
    except route_config.RouteRefusal as exc:
        raise Refusal(V2ReasonCode.STATE_PRECONDITION, str(exc)) from exc


def _provider_checks(
    route: route_config.ResolvedRoute,
    environment: Mapping[str, str],
    worktree: Path,
) -> None:
    executable = (_launch_lane.CODEX_EXECUTABLE if route.provider == "codex"
                  else _launch_lane.CLAUDE_EXECUTABLE)
    search_path = environment.get("PATH")
    if not search_path or shutil.which(executable, path=search_path) is None:
        raise Refusal(
            V2ReasonCode.EVIDENCE_INCOMPLETE,
            f"forge: {route.provider} launch refused — {route.provider} CLI could "
            "not be started",
        )
    try:
        route_floor.check_floor(
            route.provider, executable, environment, cwd=worktree, verb="launch")
    except route_floor.FloorRefusal as exc:
        raise Refusal(V2ReasonCode.EVIDENCE_INCOMPLETE, str(exc)) from exc


def _preflight(
    ctx: chain_core.CommandContext,
    role: str,
    task: str,
    worktree_value: str,
    brief_value: str,
) -> StartFacts:
    """Validate a start before writes, checking the brief before route resolution."""

    _launch_lane.require_no_halt(ctx)
    run_id = _launch_lane.require_run_id(ctx)
    worktree, head = _validate_worktree(ctx, worktree_value, role)
    _require_initialized(worktree, head)
    run = _launch_lane.run_state(ctx, run_id)
    _launch_lane.read_brief(Path(brief_value))
    route, sandbox = _resolve_route(worktree, head, role)
    prompt = _launch_lane.prepare_prompt(
        ctx,
        _launch_lane.PromptRequest(role, route.provider, worktree, head, Path(brief_value)),
    )
    environment, names, omitted = _review_launch.allowed_environment(route.provider)
    facts = StartFacts(
        repository=run.repository,
        run_id=run_id,
        run_dir=run.run_dir,
        task=task,
        role=role,
        worktree=worktree,
        head=head,
        prompt=prompt,
        route=route,
        sandbox=sandbox,
        environment=environment,
        environment_names=names,
        omitted_short=omitted,
    )
    _provider_checks(route, environment, worktree)
    _require_no_inflight(run, worktree)
    return facts


def _make_owner_dir(path: Path) -> bool:
    """Create an owner directory or validate the safe directory already present."""

    try:
        os.mkdir(path, 0o700)
    except FileExistsError:
        metadata = os.lstat(path)
        if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.geteuid():
            raise OSError("owner directory is unsafe") from None
        return False
    try:
        os.chmod(path, 0o700)
    except BaseException:
        path.rmdir()
        raise
    return True


def _require_owner_run_dir(path: Path) -> None:
    try:
        metadata = os.lstat(path)
        if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.geteuid()
                or path.resolve(strict=True) != path):
            raise OSError("run directory is unsafe")
    except (OSError, RuntimeError) as exc:
        raise Refusal(
            V2ReasonCode.EVIDENCE_INCOMPLETE,
            "forge: launch refused — launch file preparation failed",
        ) from exc


def _create_paths(
    facts: StartFacts, run: _launch_lane.RunState
) -> tuple[_launch_lane.LaunchPaths, bool]:
    existing = _launch_lane.markers(run)
    agent = _launch_lane.allocate_agent(
        existing,
        facts.route.provider,
        facts.role,
        facts.task,
    )
    agent_dir = facts.run_dir / agent
    created_agent = _make_owner_dir(agent_dir)
    reservations = facts.run_dir / _launch_lane.EXECUTION_IDS_NAME
    try:
        _make_owner_dir(reservations)
        for number in range(1, 100):
            execution = f"execution-{number:02d}"
            if any(path.parent.name != _launch_lane.EXECUTION_IDS_NAME
                   for path in facts.run_dir.glob(f"*/{execution}")):
                continue
            reserved = reservations / execution
            if not _make_owner_dir(reserved):
                continue
            paths = _launch_lane.LaunchPaths(facts.run_dir, agent, execution)
            created_execution = False
            try:
                created_execution = _make_owner_dir(paths.directory)
                if created_execution:
                    return paths, created_agent
            finally:
                if not created_execution:
                    reserved.rmdir()
        raise Refusal(
            V2ReasonCode.EVIDENCE_INCOMPLETE,
            "forge: launch refused — launch file preparation failed",
        )
    except BaseException:
        if created_agent:
            agent_dir.rmdir()
        raise


def _base_marker(
    ctx: chain_core.CommandContext, facts: StartFacts, paths: _launch_lane.LaunchPaths,
    attempt: str, argv: Sequence[str],
) -> dict[str, Any]:
    return {
        "schema": _launch_lane.LAUNCH_MARKER_SCHEMA,
        "run_id": facts.run_id,
        "task": facts.task,
        "agent": paths.agent,
        "execution": paths.execution,
        "attempt": attempt,
        "role": facts.role,
        "provider": facts.route.provider,
        "model": facts.route.model,
        "effort": facts.route.effort,
        "sandbox": facts.sandbox,
        "route_source": facts.route.route_source,
        "route_sha256": facts.route.route_sha256,
        "worktree": str(facts.worktree),
        "head": facts.head,
        "plugin_root": str(facts.prompt.plugin_root),
        "role_body_path": str(facts.prompt.role_body_path),
        "role_body_sha256": facts.prompt.role_body_sha256,
        "argv_digest": ctx.command_digest(argv),
        "prompt_digest": sha256_bytes(facts.prompt.prompt),
        "launcher_argv_digest": "pending",
        "timeout_seconds": _review_launch.PROFILE_TIMEOUT_SECONDS[facts.role],
        "environment_names": list(facts.environment_names),
        "omitted_short": list(facts.omitted_short),
        "requested_at": chain_core.iso_z(),
        "collected_at": None,
        "collected_status": None,
    }


def _cleanup(paths: _launch_lane.LaunchPaths, created_agent: bool) -> None:
    try:
        for name in (
            _launch_lane.MARKER_NAME,
            _launch_lane.WRAPPER_CONFIG_NAME,
            _launch_lane.LAUNCH_LEAVES["events"],
            _launch_lane.LAUNCH_LEAVES["prompt"],
            _launch_lane.WORKTREE_NAME,
        ):
            try:
                paths.leaf(name).unlink()
            except FileNotFoundError:
                pass
        paths.directory.rmdir()
        (paths.run_dir / _launch_lane.EXECUTION_IDS_NAME / paths.execution).rmdir()
        if created_agent:
            (paths.run_dir / paths.agent).rmdir()
    except OSError as exc:
        raise Refusal(
            V2ReasonCode.EVIDENCE_INCOMPLETE,
            f"forge: launch refused — cleanup incomplete for {paths.execution}; "
            f"remove {paths.directory} before retrying",
        ) from exc


def _prepare_owner_files(
    ctx: chain_core.CommandContext,
    facts: StartFacts,
    paths: _launch_lane.LaunchPaths,
    created_agent: bool,
) -> OwnerDraft:
    attempt = _review_lane_api.new_attempt_id()
    _launch_lane.write_owner_file(
        paths.directory,
        _launch_lane.LAUNCH_LEAVES["prompt"],
        facts.prompt.prompt,
    )
    _launch_lane.write_owner_file(
        paths.directory,
        _launch_lane.LAUNCH_LEAVES["events"],
        b"",
    )
    _launch_lane.write_owner_file(
        paths.directory,
        _launch_lane.WORKTREE_NAME,
        (str(facts.worktree) + "\n").encode("utf-8"),
    )
    argv = _launch_lane.launch_argv(
        facts.route.provider,
        facts.role,
        facts.route.model,
        facts.route.effort,
        worktree=facts.worktree,
        plugin_root=facts.prompt.plugin_root,
        staging=paths.leaf(_launch_lane.LAUNCH_LEAVES["staging"]),
    )
    marker = _base_marker(ctx, facts, paths, attempt, argv)
    attempt_fd = _launch_lane.open_attempt(paths)
    try:
        config = _launch_lane.wrapper_config(marker, argv)
        config_json, launcher_argv, digest = _review_lane_api.wrapper_launcher(
            ctx,
            attempt_fd,
            config,
        )
        _launch_lane.write_owner_file(
            paths.directory,
            _launch_lane.WRAPPER_CONFIG_NAME,
            config_json.encode("utf-8") + b"\n",
        )
        marker["launcher_argv_digest"] = digest
        _launch_lane.write_marker(paths.leaf(_launch_lane.MARKER_NAME), marker)
    except BaseException:
        _close_attempt(attempt_fd)
        raise
    return OwnerDraft(
        paths=paths,
        marker=marker,
        launcher_argv=tuple(launcher_argv),
        attempt_fd=attempt_fd,
        created_agent=created_agent,
    )


def _prepare_draft(
    ctx: chain_core.CommandContext,
    facts: StartFacts,
    paths: _launch_lane.LaunchPaths,
    created_agent: bool,
) -> OwnerDraft:
    try:
        return _prepare_owner_files(ctx, facts, paths, created_agent)
    except BaseException:
        _cleanup(paths, created_agent)
        raise


def _close_attempt(descriptor: int) -> None:
    try:
        os.close(descriptor)
    except OSError:
        pass


def _owner_record(ctx: chain_core.CommandContext, facts: StartFacts) -> OwnerLaunch:
    """Publish owner files before appending the one execution owner record."""

    run = _launch_lane.run_state(ctx, facts.run_id)
    _require_owner_run_dir(run.run_dir)
    with _launch_lane.journal_lock(run) as descriptor:
        _require_owner_run_dir(run.run_dir)
        _require_no_inflight(run, facts.worktree)
        try:
            paths, created_agent = _create_paths(facts, run)
            draft = _prepare_draft(ctx, facts, paths, created_agent)
        except Refusal:
            raise
        except BaseException as exc:
            raise Refusal(
                V2ReasonCode.EVIDENCE_INCOMPLETE,
                "forge: launch refused — launch file preparation failed",
            ) from exc
        record = {
            "kind": "execution_started", "run_id": facts.run_id,
            "execution_id": paths.execution, "attempt_id": draft.marker["attempt"],
            "task_id": facts.task, "started_at": draft.marker["requested_at"],
            **_execution_fields(facts, paths),
        }
        _launch_lane.append_record(run, record, descriptor)
        return OwnerLaunch(facts=facts, draft=draft)


def _clear_spawn_failure(
    ctx: chain_core.CommandContext, owner: OwnerLaunch, cause: str
) -> dict[str, object]:
    paths = owner.draft.paths
    raw = _launch_lane.read_private_record(
        paths.leaf(_review_attempt.COMPLETION_NAME)
    )
    changed = _launch_lane.worktree_changes(
        owner.facts.worktree,
        owner.facts.head,
        paths.execution,
    )
    result = _launch_lane.CompletionResult(
        status="failed",
        summary=_launch_lane.completion_summary(
            "failed",
            None,
            cause,
            False,
            0,
            None,
        ),
        files_changed=changed,
        caveats=(cause, *_launch_lane.plan_caveats(owner.facts.role, changed)),
        handoff=None,
        message="launch collect: failed",
    )
    run = _launch_lane.run_state(ctx, owner.facts.run_id)
    record = _launch_lane.append_execution_result(
        run,
        paths,
        task=owner.facts.task,
        result=result,
        completion_raw=raw,
    )
    _launch_lane.mark_collected(paths, owner.draft.marker, record.get("status"))
    return record


def _spawn_failure_outcome(
    self: Engine, owner: OwnerLaunch, exc: Exception
) -> Outcome:
    """Publish and clear a failed spawn, delegating a lost race through Engine."""

    draft = owner.draft
    cause = _review_attempt.launch_failure(exc)
    published, completion = _review_lane_api.publish_or_read_terminal(
        draft.attempt_fd,
        _launch_lane.marker_binding(draft.marker),
        cause,
        None,
    )
    if not published:
        # Sibling verbs cannot import each other, so Engine owns this handoff.
        return self.launch_collect(draft.paths.execution)
    recorded_cause = str(completion.get("error") or cause)
    _clear_spawn_failure(self.ctx, owner, recorded_cause)
    # The refusal reports this invocation's local spawn failure, not a raced record.
    raise Refusal(
        V2ReasonCode.EVIDENCE_INCOMPLETE,
        f"forge: launch failed for {draft.paths.execution}: {cause}",
    ) from exc


def launch(
    self: Engine, *, role: str, task: str, worktree: str, brief: str
) -> Outcome:
    """Start one fresh launch and clear any synchronous spawn failure safely."""

    facts = _preflight(self.ctx, role, task, worktree, brief)
    owner = _owner_record(self.ctx, facts)
    draft = owner.draft
    try:
        try:
            process = _review_lane_api.spawn_wrapper(
                draft.launcher_argv,
                cwd=facts.worktree,
                environment=facts.environment,
                attempt_fd=draft.attempt_fd,
            )
        except Exception as exc:
            return _spawn_failure_outcome(self, owner, exc)
    finally:
        os.close(draft.attempt_fd)
    try:
        _launch_lane.write_pid(draft.paths, process.pid)
    except OSError as exc:
        raise Refusal(
            V2ReasonCode.EVIDENCE_INCOMPLETE,
            f"forge: launch refused — pid sidecar unavailable for "
            f"{draft.paths.execution}; run launch collect",
        ) from exc
    return Outcome(
        ok=True,
        reason_code=V2ReasonCode.OK,
        message=f"launch started for {draft.paths.execution}",
        next_required_step=(
            f"forge launch collect --repo {self.ctx.repo.root} --run-id "
            f"{facts.run_id} --execution {draft.paths.execution}"
        ),
        evidence_refs=(
            draft.paths.reference(_launch_lane.LAUNCH_LEAVES["prompt"]),
            draft.paths.reference(_launch_lane.MARKER_NAME),
        ),
        schema=REVISION9_OUTPUT_SCHEMA,
    )
