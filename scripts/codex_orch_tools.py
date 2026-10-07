#!/usr/bin/env python3
"""Run-journal logging, structural validation, and managed agent inspection."""

# forge: modified from upstream — record plain run facts without lifecycle authority.

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from codex_orchestrator.cli import add_inspection_commands
from codex_orchestrator.journal import (
    APPEND_IO_ERROR,
    CoordinationRefusal,
    append_run_record,
    require_run_id,
)


def _identity(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--reference", action="append", default=[])


def _execution_route(parser: argparse.ArgumentParser) -> None:
    for name in ("task", "role", "provider", "model", "effort", "worktree"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--agent")
    parser.add_argument("--sandbox", required=True)
    parser.add_argument("--session-id")
    parser.add_argument("--route-source", required=True)
    parser.add_argument("--route-sha256", required=True)
    parser.add_argument("--event-source")
    parser.add_argument("--events")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codex_orch_tools.py")
    commands = parser.add_subparsers(dest="command", required=True)
    add_inspection_commands(commands)
    opened = commands.add_parser("run-open")
    _identity(opened)
    opened.add_argument("--intent", required=True)
    opened.add_argument("--actor", required=True)

    closed = commands.add_parser("run-close")
    _identity(closed)
    closed.add_argument("--outcome", required=True)

    journal = commands.add_parser("journal")
    verbs = journal.add_subparsers(dest="journal_command", required=True)
    started = verbs.add_parser("task-start")
    _identity(started)
    started.add_argument("--task", required=True)
    started.add_argument("--title", required=True)
    started.add_argument("--scope", required=True)

    finished = verbs.add_parser("task-finish")
    _identity(finished)
    finished.add_argument("--task", required=True)
    finished.add_argument("--title", required=True)
    finished.add_argument("--scope", required=True)
    finished.add_argument("--status", required=True)

    execution = verbs.add_parser("execution-start")
    _identity(execution)
    _execution_route(execution)
    execution.add_argument("--execution", required=True)
    execution.add_argument("--started-at")

    result = verbs.add_parser("execution-result")
    _identity(result)
    _execution_route(result)
    result.add_argument("--execution", required=True)
    result.add_argument("--attempt")
    result.add_argument("--started-at", required=True)
    result.add_argument("--ended-at")
    result.add_argument("--status", required=True)
    result.add_argument("--exit-status", type=int, required=True)
    result.add_argument("--output", required=True)
    result.add_argument("--input-tokens", type=int)
    result.add_argument("--output-tokens", type=int)

    decision = verbs.add_parser("decision-add")
    _identity(decision)
    decision.add_argument("--text", required=True)
    decision.add_argument("--actor", required=True)
    return parser


def _timestamp() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _route(args: argparse.Namespace) -> dict[str, object]:
    record: dict[str, object] = {
        "task_id": args.task,
        "role": args.role,
        "provider": args.provider,
        "model": args.model,
        "effort": args.effort,
        "worktree": args.worktree,
    }
    for source, target in (
        ("agent", "agent"),
        ("sandbox", "sandbox"),
        ("session_id", "session_id"),
        ("route_source", "route_source"),
        ("route_sha256", "route_sha256"),
        ("event_source", "event_source"),
        ("events", "events"),
    ):
        value = getattr(args, source)
        if value is not None:
            record[target] = value
    return record


def _record(args: argparse.Namespace) -> dict[str, object]:
    if args.command == "run-open":
        return {
            "kind": "run_started",
            "run_id": args.run_id,
            "repository": str(Path(args.repo)),
            "intent": args.intent,
            "actor": args.actor,
        }
    if args.command == "run-close":
        return {"kind": "run_closed", "run_id": args.run_id, "outcome": args.outcome}
    if args.journal_command in {"task-start", "task-finish"}:
        record = {
            "kind": "task",
            "run_id": args.run_id,
            "task_id": args.task,
            "title": args.title,
            "scope": args.scope,
        }
        if args.journal_command == "task-finish":
            record["description"] = args.status
        return record
    if args.journal_command == "execution-start":
        return {
            "kind": "execution_started",
            "run_id": args.run_id,
            **_route(args),
            "execution_id": args.execution,
            "started_at": args.started_at or _timestamp(),
        }
    if args.journal_command == "execution-result":
        record = {
            "kind": "execution_finished",
            "run_id": args.run_id,
            **_route(args),
            "execution_id": args.execution,
            "started_at": args.started_at,
            "ended_at": args.ended_at or _timestamp(),
            "status": args.status,
            "exit_status": args.exit_status,
            "output": args.output,
        }
        for name in ("input_tokens", "output_tokens"):
            value = getattr(args, name)
            if value is not None:
                record[name] = value
        if args.attempt is not None:
            record["attempt_id"] = args.attempt
        return record
    return {
        "kind": "decision",
        "run_id": args.run_id,
        "text": args.text,
        "actor": args.actor,
    }


def _repository(repo: str) -> Path:
    import route_config  # noqa: PLC0415 - cli imports monitor, which adds the forge runtime path.

    try:
        root = Path(repo).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise OSError("repository is not a directory")
    except (OSError, RuntimeError, ValueError) as exc:
        raise CoordinationRefusal(APPEND_IO_ERROR) from exc
    try:
        return route_config.common_root(root)
    except route_config.RouteRefusal as exc:
        if (root / ".git").exists():
            raise CoordinationRefusal(APPEND_IO_ERROR) from exc
        return root


def main(argv: list[str] | None = None) -> int:
    selected = list(sys.argv[1:] if argv is None else argv)
    args = _parser().parse_args(selected)
    if args.command in {"state", "monitor", "validate"}:
        return args.func(args)
    operation = (
        args.command
        if args.command != "journal"
        else f"journal {args.journal_command}"
    )
    try:
        require_run_id(operation, args.run_id)
        repo = _repository(args.repo)
        record = _record(args)
        if args.reference:
            record["references"] = args.reference
        append_run_record(repo, args.run_id, record, operation=operation)
    except CoordinationRefusal as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(record, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
