#!/usr/bin/env python3
"""Run-journal validation and Codex agent monitoring tools.

Invoked by path from the plugin skills, so this stable entry point remains in
``scripts/``. Command coordination lives in ``codex_orchestrator.cli``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from codex_orchestrator.cli import main as upstream_main
from codex_orchestrator import batch, builders
from codex_orchestrator.journal import (
    CoordinationRefusal,
    INVALID_JOURNAL_RECORD,
    append_run_record,
    close_run,
    open_run,
    retire_run,
)


# forge: modified from upstream — expose D13 run coordination at the stable entry point
COORDINATION_COMMANDS = {
    "run-open",
    "journal",
    "journal-append",
    "run-readmit",
    "run-close",
    "run-retire",
}

TYPED_REPEATED_OPTIONS = frozenset(
    {
        "--scope",
        "--acceptance",
        "--file",
        "--file-changed",
        "--caveat",
        "--evidence",
        "--basis",
        "--risk",
        "--follow-up",
    }
)
TYPED_SINGLETON_OPTIONS = frozenset(
    {
        "--repo",
        "--run-id",
        "--idempotency-key",
        "--goal",
        "--plugin-ref",
        "--successor-of",
        "--judgment",
        "--summary",
        "--task",
        "--status",
        "--agent",
        "--provider",
        "--role",
        "--mode",
        "--model",
        "--effort",
        "--worktree",
        "--head",
        "--prompt",
        "--handoff",
        "--event-source",
        "--events",
        "--execution",
        "--criterion",
        "--method",
        "--check",
        "--result",
        "--observation",
        "--resolution",
        "--finding",
        "--outcome",
        "--binding-chain",
        "--binding-id",
    }
)


def _option_values(argv: list[str], option: str) -> list[str]:
    values: list[str] = []
    for index, argument in enumerate(argv):
        if argument == option:
            values.append(
                argv[index + 1]
                if index + 1 < len(argv) and not argv[index + 1].startswith("--")
                else ""
            )
        elif argument.startswith(option + "="):
            values.append(argument[len(option) + 1 :])
    return values


def _typed_singleton_refusal(argv: list[str], *, recovery: bool) -> str | None:
    singleton_options = set(TYPED_SINGLETON_OPTIONS) - {"--idempotency-key"}
    if argv[:1] == ["run-close"]:
        singleton_options.discard("--risk")
    for option in sorted(singleton_options):
        values = _option_values(argv, option)
        if len(values) > 1:
            return f"forge: CLI option refused — duplicate {option}"
        if values and not values[0]:
            return f"forge: CLI option refused — empty {option}"
    keys = _option_values(argv, "--idempotency-key")
    if recovery:
        if keys:
            return batch.journal.BATCH_KEY_REFUSAL
    elif (
        len(keys) != 1
        or not keys[0]
        or batch.journal.HEX_SHA256_PATTERN.fullmatch(keys[0]) is None
    ):
        return batch.journal.BATCH_KEY_REFUSAL
    return None


def _record(path: str) -> object:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise CoordinationRefusal(INVALID_JOURNAL_RECORD) from exc
    return value


def _coordination_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codex_orch_tools.py")
    subparsers = parser.add_subparsers(dest="command", required=True)

    opened = subparsers.add_parser("run-open")
    opened.add_argument("--repo", required=True)
    opened.add_argument("--run-id", required=True)
    opened.add_argument("--scope", action="append", required=True)
    opened.add_argument("--record-json", required=True)
    opened.add_argument("--successor-of")

    appended = subparsers.add_parser("journal-append")
    appended.add_argument("--repo", required=True)
    appended.add_argument("--run-id", required=True)
    appended.add_argument("--record-json", required=True)

    closed = subparsers.add_parser("run-close")
    closed.add_argument("--repo", required=True)
    closed.add_argument("--run-id", required=True)
    closed.add_argument("--record-json", required=True)

    retired = subparsers.add_parser("run-retire")
    retired.add_argument("--repo", required=True)
    retired.add_argument("--run-id", required=True)
    return parser


def _typed_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codex_orch_tools.py")
    subparsers = parser.add_subparsers(dest="command", required=True)

    opened = subparsers.add_parser("run-open")
    _typed_identity(opened)
    opened.add_argument("--goal", required=True)
    opened.add_argument("--scope", action="append", required=True)
    opened.add_argument("--plugin-ref", required=True)
    opened.add_argument("--successor-of")

    closed = subparsers.add_parser("run-close")
    _typed_identity(closed)
    closed.add_argument("--judgment", choices=("passed", "blocked"), required=True)
    closed.add_argument("--summary", required=True)
    closed.add_argument("--risk", action="append", default=[])
    closed.add_argument("--follow-up", action="append", default=[])

    readmitted = subparsers.add_parser("run-readmit")
    _typed_identity(readmitted)
    readmitted.add_argument("--scope", action="append", required=True)
    readmitted.add_argument("--replace", action="store_true")

    journal_parser = subparsers.add_parser("journal")
    journal_subparsers = journal_parser.add_subparsers(
        dest="journal_command", required=True
    )

    task_started = journal_subparsers.add_parser("task-start")
    _typed_identity(task_started)
    task_started.add_argument("--task", required=True)
    task_started.add_argument("--goal", required=True)
    task_started.add_argument("--acceptance", action="append", required=True)
    task_started.add_argument("--file", action="append", required=True)

    task_finished = journal_subparsers.add_parser("task-finish")
    _typed_identity(task_finished)
    task_finished.add_argument("--task", required=True)
    task_finished.add_argument(
        "--status", choices=tuple(sorted({"complete", "blocked", "failed"})), required=True
    )

    execution_started = journal_subparsers.add_parser("execution-start")
    _typed_identity(execution_started)
    for name in (
        "agent",
        "task",
        "provider",
        "role",
        "mode",
        "model",
        "effort",
        "worktree",
        "head",
        "prompt",
        "handoff",
        "event-source",
    ):
        execution_started.add_argument(f"--{name}", required=True)
    execution_started.add_argument("--events")

    execution_finished = journal_subparsers.add_parser("execution-result")
    _typed_identity(execution_finished)
    for name in ("execution", "agent", "task", "summary"):
        execution_finished.add_argument(f"--{name}", required=True)
    execution_finished.add_argument(
        "--status", choices=tuple(sorted({"complete", "blocked", "failed"})), required=True
    )
    execution_finished.add_argument("--file-changed", action="append", default=[])
    execution_finished.add_argument("--caveat", action="append", default=[])
    execution_finished.add_argument("--handoff")

    verified = journal_subparsers.add_parser("verification-add")
    _typed_identity(verified)
    for name in ("task", "criterion", "method", "check", "observation"):
        verified.add_argument(f"--{name}", required=True)
    verified.add_argument(
        "--result",
        choices=tuple(sorted({"passed", "failed", "inconclusive", "skipped"})),
        required=True,
    )
    verified.add_argument("--evidence", action="append", default=[])
    verified.add_argument("--binding-chain")
    verified.add_argument("--binding-id")

    decided = journal_subparsers.add_parser("decision-add")
    _typed_identity(decided)
    decided.add_argument("--task")
    decided.add_argument("--resolution", required=True)
    decided.add_argument("--finding")
    decided.add_argument("--outcome")
    decided.add_argument("--risk")
    decided.add_argument("--basis", action="append", default=[])
    decided.add_argument("--binding-chain")
    decided.add_argument("--binding-id")

    recovered = journal_subparsers.add_parser("batch-recover")
    recovered.add_argument("--repo", required=True)
    recovered.add_argument("--run-id", required=True)
    return parser


def _typed_identity(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--idempotency-key", required=True)


def _typed_main(argv: list[str]) -> int:
    recovery = len(argv) >= 2 and argv[:2] == ["journal", "batch-recover"]
    refusal = _typed_singleton_refusal(argv, recovery=recovery)
    if refusal is not None:
        print(refusal, file=sys.stderr)
        return 1
    args = _typed_parser().parse_args(argv)
    repo = Path(args.repo)
    try:
        if not repo.is_absolute():
            raise CoordinationRefusal(
                "forge: journal builder refused — repository must be absolute"
            )
        if args.command == "run-open":
            outcome = builders.run_open(
                repo,
                args.run_id,
                idempotency_key=args.idempotency_key,
                goal=args.goal,
                scope=args.scope,
                plugin_ref=args.plugin_ref,
                successor_of=args.successor_of,
            )
        elif args.command == "run-close":
            outcome = builders.run_close(
                repo,
                args.run_id,
                idempotency_key=args.idempotency_key,
                judgment=args.judgment,
                summary=args.summary,
                risks=args.risk,
                follow_ups=args.follow_up,
            )
        elif args.command == "run-readmit":
            outcome = builders.scope_change(
                repo,
                args.run_id,
                idempotency_key=args.idempotency_key,
                scope=args.scope,
                replace=args.replace,
            )
        elif args.journal_command == "batch-recover":
            outcome = batch.recover_batch(repo, args.run_id)
        elif args.journal_command == "task-start":
            outcome = builders.task_start(
                repo,
                args.run_id,
                idempotency_key=args.idempotency_key,
                task=args.task,
                goal=args.goal,
                acceptance=args.acceptance,
                files=args.file,
            )
        elif args.journal_command == "task-finish":
            outcome = builders.task_finish(
                repo,
                args.run_id,
                idempotency_key=args.idempotency_key,
                task=args.task,
                status=args.status,
            )
        elif args.journal_command == "execution-start":
            outcome = builders.execution_start(
                repo,
                args.run_id,
                idempotency_key=args.idempotency_key,
                agent=args.agent,
                task=args.task,
                provider=args.provider,
                role=args.role,
                mode=args.mode,
                model=args.model,
                effort=args.effort,
                worktree=args.worktree,
                head=args.head,
                prompt=args.prompt,
                handoff=args.handoff,
                event_source=args.event_source,
                events=args.events,
            )
        elif args.journal_command == "execution-result":
            outcome = builders.execution_result(
                repo,
                args.run_id,
                idempotency_key=args.idempotency_key,
                execution=args.execution,
                agent=args.agent,
                task=args.task,
                status=args.status,
                summary=args.summary,
                files_changed=args.file_changed,
                caveats=args.caveat,
                handoff=args.handoff,
            )
        elif args.journal_command == "verification-add":
            outcome = builders.verification_add(
                repo,
                args.run_id,
                idempotency_key=args.idempotency_key,
                task=args.task,
                criterion=args.criterion,
                method=args.method,
                check=args.check,
                result=args.result,
                observation=args.observation,
                evidence=args.evidence,
                binding_chain=args.binding_chain,
                binding_id=args.binding_id,
            )
        else:
            outcome = builders.decision_add(
                repo,
                args.run_id,
                idempotency_key=args.idempotency_key,
                task=args.task,
                resolution=args.resolution,
                finding=args.finding,
                outcome=args.outcome,
                risk=args.risk,
                basis=args.basis,
                binding_chain=args.binding_chain,
                binding_id=args.binding_id,
            )
        print(json.dumps(outcome.payload(), sort_keys=True, separators=(",", ":")))
    except CoordinationRefusal as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception:
        print("forge: run coordination refused — internal error", file=sys.stderr)
        return 1
    return 0


def _coordination_main(argv: list[str]) -> int:
    args = _coordination_parser().parse_args(argv)
    repo = Path(args.repo)
    try:
        if args.command == "run-open":
            target = open_run(
                repo,
                args.run_id,
                args.scope,
                _record(args.record_json),
                successor_of=args.successor_of,
            )
            print(target)
        elif args.command == "journal-append":
            append_run_record(repo, args.run_id, _record(args.record_json))
        elif args.command == "run-close":
            close_run(repo, args.run_id, _record(args.record_json))
        else:
            retire_run(repo, args.run_id)
    except CoordinationRefusal as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception:
        print("forge: run coordination refused — internal error", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    selected = list(sys.argv[1:] if argv is None else argv)
    has_record_json = any(
        argument == "--record-json" or argument.startswith("--record-json=")
        for argument in selected
    )
    typed = bool(
        selected
        and (
            selected[0] == "journal"
            or (
                (
                    selected[0] in {"run-open", "run-close"}
                    and not has_record_json
                )
                or selected[0] == "run-readmit"
            )
        )
    )
    if typed:
        return _typed_main(selected)
    if selected and selected[0] in COORDINATION_COMMANDS:
        return _coordination_main(selected)
    return upstream_main(selected)

if __name__ == "__main__":
    raise SystemExit(main())
