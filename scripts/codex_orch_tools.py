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
from codex_orchestrator.journal import (
    CoordinationRefusal,
    INVALID_JOURNAL_RECORD,
    append_run_record,
    close_run,
    open_run,
    readmit_run,
    retire_run,
)


# forge: modified from upstream — expose D13 run coordination at the stable entry point
COORDINATION_COMMANDS = {
    "run-open",
    "journal-append",
    "run-readmit",
    "run-close",
    "run-retire",
}


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

    admitted = subparsers.add_parser("run-readmit")
    admitted.add_argument("--repo", required=True)
    admitted.add_argument("--run-id", required=True)
    admitted.add_argument("--scope", action="append", required=True)

    closed = subparsers.add_parser("run-close")
    closed.add_argument("--repo", required=True)
    closed.add_argument("--run-id", required=True)
    closed.add_argument("--record-json", required=True)

    retired = subparsers.add_parser("run-retire")
    retired.add_argument("--repo", required=True)
    retired.add_argument("--run-id", required=True)
    return parser


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
        elif args.command == "run-readmit":
            readmit_run(repo, args.run_id, args.scope)
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
    if selected and selected[0] in COORDINATION_COMMANDS:
        return _coordination_main(selected)
    return upstream_main(selected)

if __name__ == "__main__":
    raise SystemExit(main())
