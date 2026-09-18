"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
import copy
import datetime as dt
import os
from typing import TYPE_CHECKING, Any, Mapping, Sequence, Collection, Callable
from forge_cli import chain_core, runtime, candidate as candidate_module
if TYPE_CHECKING:
    from forge_cli.engine._engine import Engine
from forge_cli.engine._core import _run_halt as _run_halt, _commit_start_binding_refusal as _commit_start_binding_refusal
from forge_cli.engine._state import TERMINAL_STATES as TERMINAL_STATES, ABORT_DISPOSITION_PRECONDITIONS as ABORT_DISPOSITION_PRECONDITIONS
from forge_cli.policy import Policy
from pathlib import Path
from forge_cli.envelope import FrozenError, OUTPUT_SCHEMA, Outcome, REVISION9_OUTPUT_SCHEMA
import functools


def _new_state(
    chain_id: str,
    repo: chain_core.Repository,
    head: str,
    policy: Policy,
    paths: Sequence[str],
    declared_tier: str | None,
    run_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    now = runtime.utc_now()
    session_identity = os.environ.get("CLAUDE_SESSION_ID")
    if not session_identity:
        session_identity = f"pid:{os.environ.get('FORGE_SESSION_PID') or os.getppid()}"
    state: dict[str, Any] = {
        "schema": chain_core.SCHEMA,
        "chain_id": chain_id,
        "kind": chain_core.KIND,
        "state": "classifying",
        "created_at": chain_core.iso_z(now),
        "last_event_at": chain_core.iso_z(now),
        "inactive_after": chain_core.iso_z(now + dt.timedelta(seconds=chain_core.INACTIVE_SECONDS)),
        "repo_head": head,
        "policy_source": {
            "path": "forge-project.md",
            "sha": policy.sha,
            "digest": policy.digest,
        },
        "paths": list(paths),
        "staging": {
            "worktree_root": str(repo.root),
            "session_identity": session_identity,
            "staged_paths": [],
            "staged_at": None,
            "classification_runs": 0,
            "anomalies": [],
        },
        "candidate": {"sha256": None, "computed_at": None},
        "tier": {
            "declared": declared_tier,
            "derived": None,
            "effective": declared_tier,
            "control": False,
            "categories": [],
            "classification": None,
        },
        "steps": {},
        "review": {
            "iteration": 0,
            "request": None,
            "verdict": None,
            "dispositions": [],
            "operator_cosign_required": False,
            "residual_risk": None,
        },
        "approval": {},
        "authorization": {},
        "commit_result": {},
        "run_binding": copy.deepcopy(dict(run_binding)) if run_binding else None,
        "journal_outbox": None,
    }
    return chain_core.validate_state(state, chain_id)


def _prove_run_task_binding(
    ctx: chain_core.CommandContext,
    run_id: str,
    task_id: str,
    paths: Sequence[str],
    policy: Policy,
) -> dict[str, str]:
    """Prove the immutable run/task/repository/scope/policy start tuple."""

    batch, _builders, journal = runtime._coordination_modules()
    run_dir = ctx.store.common_root / ".codex-orchestrator" / "runs" / run_id
    try:
        with batch.batch_lock(run_dir, create=False):
            run_state = journal._scan_run(run_dir)
            if run_state.disposition != "open":
                raise ValueError("run is not open")
            opening = run_state.records[0] if run_state.records else None
            if (
                not isinstance(opening, dict)
                or Path(str(opening.get("repo", ""))).resolve(strict=True)
                != ctx.repo.root
            ):
                raise ValueError("run repository differs from chain repository")
            matching_tasks = [
                record
                for record in run_state.records
                if record.get("type") == "task" and record.get("id") == task_id
            ]
            if not matching_tasks or matching_tasks[-1].get("status") != "active":
                raise ValueError("task is not active")
            task_files = matching_tasks[-1].get("files")
            if (
                not isinstance(task_files, list)
                or not task_files
                or not all(isinstance(item, str) and item for item in task_files)
            ):
                raise ValueError("task files are malformed")
            mechanical_outputs = chain_core._committed_changelog_output_paths(policy)
            for path in paths:
                if not candidate_module.valid_scope_path(path):
                    raise ValueError(
                        f"path {path!r} violates the committed scope pathname contract"
                    )
                if path in mechanical_outputs:
                    continue
                if not any(
                    journal.pathspec_contained(path, item) for item in task_files
                ):
                    raise ValueError(f"path {path} is outside task membership")
                if not any(
                    journal.pathspec_contained(path, admitted)
                    for admitted in run_state.scope
                ):
                    raise ValueError(f"path {path} is outside admitted scope")
    except (OSError, RuntimeError, ValueError, journal.CoordinationRefusal) as exc:
        raise _commit_start_binding_refusal(exc) from exc
    return {
        "run_id": run_id,
        "task_id": task_id,
        "repository": str(ctx.repo.root),
        "policy_digest": policy.digest,
    }


def _peek_chain_state(store: chain_core.ChainStore, chain_id: str) -> dict[str, Any] | None:
    """Read only enough immutable identity to choose the outer journal lock."""

    try:
        if store.chain_family(chain_id) != "commit":
            return None
        with store.event_lock(chain_id):
            events = store._events_unlocked(chain_id)
            return copy.deepcopy(events[-1]["payload"]["state"])
    except (FileNotFoundError, OSError, UnicodeError, ValueError, FrozenError):
        return None


def _peek_raw_abort_state(
    store: chain_core.ChainStore, chain_id: str
) -> dict[str, Any] | None:
    """Peek explicit abort identity/binding without replaying a frozen log."""

    try:
        return store._canonical_raw_commit_state(chain_id)
    except (FileNotFoundError, OSError, UnicodeError, ValueError, FrozenError):
        return None


def _peek_selected_chain(
    engine: "Engine", *, include_terminal: bool
) -> dict[str, Any] | None:
    selected_id = engine.ctx.options.chain_id
    if selected_id is not None:
        return _peek_chain_state(engine.ctx.store, selected_id)
    candidates: list[dict[str, Any]] = []
    for chain_id in engine.ctx.store.list_ids(family="commit"):
        state = _peek_chain_state(engine.ctx.store, chain_id)
        if (
            isinstance(state, dict)
            and state.get("staging", {}).get("worktree_root")
            == str(engine.ctx.repo.root)
        ):
            candidates.append(state)
    live = [state for state in candidates if state.get("state") not in TERMINAL_STATES]
    choices = live or (candidates if include_terminal else [])
    if not choices:
        return None
    return max(choices, key=lambda item: str(item.get("created_at", "")))


def _command_run_lock_id(engine: "Engine", method_name: str) -> str | None:
    selected_id = engine.ctx.options.chain_id
    if method_name == "abort" and selected_id is not None:
        raw_state = _peek_raw_abort_state(engine.ctx.store, selected_id)
        if raw_state is not None:
            raw_binding = raw_state.get("run_binding")
            if (
                isinstance(raw_binding, Mapping)
                and set(raw_binding)
                == {"run_id", "task_id", "repository", "policy_digest"}
                and isinstance(raw_binding.get("run_id"), str)
                and chain_core.RUN_ID_RE.fullmatch(str(raw_binding["run_id"])) is not None
            ):
                return str(raw_binding["run_id"])
            return None
    include_terminal = method_name in {
        "status",
        "abort",
        "abort_disposition",
        "operator_tombstone",
    }
    selected = _peek_selected_chain(engine, include_terminal=include_terminal)
    binding = selected.get("run_binding") if isinstance(selected, dict) else None
    if isinstance(binding, Mapping) and isinstance(binding.get("run_id"), str):
        return str(binding["run_id"])
    if method_name == "start" and engine.ctx.options.run_id is not None:
        return engine.ctx.options.run_id
    if (
        method_name == "abort_disposition"
        and selected_id is not None
        and engine.ctx.options.run_id is not None
        and engine.ctx.store.tombstone(selected_id) is not None
    ):
        # bead forge-plugin-11a: a tombstone disposition appends to the named
        # run's journal, so that journal's lock is the outer lock. A run
        # without a journal takes no lock: the verb then refuses with its
        # named journal precondition instead of a lock failure.
        run_dir = (
            engine.ctx.store.common_root
            / ".codex-orchestrator"
            / "runs"
            / str(engine.ctx.options.run_id)
        )
        try:
            if not (run_dir / "journal.jsonl").is_file():
                return None
        except OSError:
            return None
        return engine.ctx.options.run_id
    return None


def abort_disposition_refusal(
    state: Mapping[str, Any],
    events: Sequence[Mapping[str, Any]],
    records: Sequence[Mapping[str, Any]],
    journal_issues: Sequence[str],
    *,
    controls: Collection[str] = ABORT_DISPOSITION_PRECONDITIONS,
) -> str | None:
    """Return the expected-state text refusing a retrospective disposition, or None.

    Each precondition is evaluated in order and independently so a single
    violation is attributable; ``controls`` names the checks in force (tests
    remove one at a time to prove each is load-bearing).
    """
    binding = state.get("run_binding")
    if "run-bound" in controls and not isinstance(binding, Mapping):
        return "a run-bound chain"
    if "aborted" in controls and state.get("state") != "aborted":
        return "an aborted chain"
    if "null-outbox" in controls and state.get("journal_outbox") is not None:
        return "an aborted chain with a null journal outbox"
    candidate = state.get("candidate")
    if "candidate" in controls and not (
        isinstance(candidate, Mapping) and isinstance(candidate.get("sha256"), str)
    ):
        return "an aborted chain with a staged candidate"
    result = state.get("commit_result")
    if "never-landed" in controls and not (
        isinstance(result, Mapping)
        and result.get("commit_sha") is None
        and isinstance(result.get("aborted_at"), str)
    ):
        return "an aborted chain with no landed commit"
    if "uncarried-abort" in controls:
        for event in events:
            payload = event.get("payload") if isinstance(event, Mapping) else None
            if not isinstance(payload, Mapping):
                continue
            details = payload.get("details")
            if payload.get("event") in {"chain_aborted", "abort_disposition_recorded"} and (
                isinstance(details, Mapping) and "journal_batch" in details
            ):
                return "an abort that carried no journal batch"
    if "journal-readable" in controls and journal_issues:
        return "a readable run journal"
    if "no-journaled-decision" in controls:
        chain_id = str(state.get("chain_id"))
        for record in records:
            binding_value = record.get("binding")
            source = (
                binding_value.get("source_record")
                if isinstance(binding_value, Mapping)
                else None
            )
            if (
                record.get("type") == "decision"
                and record.get("outcome") == "chain-abort"
                and isinstance(source, Mapping)
                and source.get("chain_id") == chain_id
            ):
                return "a chain without a journaled abort decision"
    return None


def _serialize_worktree_command(method: Callable[..., Outcome]) -> Callable[..., Outcome]:
    """Hold journal-outer then worktree serialization across each command."""

    @functools.wraps(method)
    def wrapped(self: "Engine", *args: Any, **kwargs: Any) -> Outcome:
        for _attempt in range(8):
            run_id = _command_run_lock_id(self, method.__name__)
            if run_id is None:
                with self.ctx.store.admission_lock(self.ctx.repo.root):
                    # A bound chain may have appeared between the identity
                    # peek and the worktree lock.  Retry with its journal lock
                    # outermost instead of acquiring in the reverse order.
                    if _command_run_lock_id(self, method.__name__) is not None:
                        continue
                    return method(self, *args, **kwargs)
            chain_core.register_coordination_seams()
            batch, _builders, journal = runtime._coordination_modules()
            run_dir = (
                self.ctx.store.common_root
                / ".codex-orchestrator"
                / "runs"
                / run_id
            )
            try:
                retry = False
                create_run_lock = method.__name__ == "start"
                with chain_core._chain_batch_lock(
                    run_dir,
                    self.ctx.repo.root,
                    run_id,
                    create=create_run_lock,
                    # A stable legacy-run lock is a durable mutation.  Keep
                    # FR-210's halt proof on the helper's authoritative
                    # create-missing edge. Engine.start repeats it after
                    # serialization so a halt engaged during acquisition wins.
                    before_create=(
                        (lambda: _run_halt(self.ctx)) if create_run_lock else None
                    ),
                ):
                    with self.ctx.store.admission_lock(self.ctx.repo.root):
                        if _command_run_lock_id(self, method.__name__) != run_id:
                            retry = True
                        else:
                            return method(self, *args, **kwargs)
                if retry:
                    continue
            except journal.CoordinationRefusal as exc:
                if (
                    method.__name__ == "start"
                    and str(exc) != journal.BATCH_DIVERGED
                ):
                    raise _commit_start_binding_refusal(exc) from exc
                raise chain_core._coordination_refusal(exc) from exc
        raise FrozenError(
            "chain identity did not stabilize for journal-outer serialization",
            chain_id=self.ctx.options.chain_id,
            schema=(
                REVISION9_OUTPUT_SCHEMA
                if self.ctx.options.revision9_face
                else OUTPUT_SCHEMA
            ),
        )

    return wrapped
