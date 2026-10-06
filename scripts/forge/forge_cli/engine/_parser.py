"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
import argparse
import re
from forge_cli.engine._core import _require_merge_lifecycle_control as _require_merge_lifecycle_control
from forge_cli.engine._state import GLOBAL_OPTIONS_HELP as GLOBAL_OPTIONS_HELP
from forge_cli.envelope import ReasonCode, Refusal, Revision9ReasonCode
from typing import Sequence
from forge_cli import chain_core, runtime


class ContractArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        message = re.sub(
            r"[\x00-\x1f\x7f-\x9f\u2028\u2029]", lambda match: f"\\x{ord(match[0]):02x}", message
        )
        raise Refusal(
            ReasonCode.STATE_PRECONDITION,
            f"invalid CLI invocation: {message}",
            expected="a valid Forge CLI verb and arguments",
            observed=message,
            remediation="forge status",
        )


def _extract_global_options(argv: Sequence[str]) -> tuple[chain_core.CLIOptions, list[str]]:
    options = chain_core.CLIOptions(original_argv=tuple(argv))
    remaining: list[str] = []
    # Global flags are accepted before or after the verb, but an option-shaped
    # value belonging to a verb must remain data.  In particular, commit
    # messages and operator reasons may legitimately equal ``--json`` or a
    # global ``--name=value`` spelling.
    verb_value_options = {
        "--declare-tier",
        "--reason",
        "--candidate",
        "--message",
        "--message-file",
        "--verdict-file",
        "--finding",
        "--severity",
        "--resolution",
        "--task",
    }
    if runtime.MERGE_LIFECYCLE_ACTIVE:
        verb_value_options.add("--worktree")
    seen_singletons: set[str] = set()
    index = 0
    while index < len(argv):
        argument = argv[index]
        if argument == "--":
            remaining.extend(argv[index:])
            break
        if argument in verb_value_options:
            if index + 1 < len(argv):
                value = argv[index + 1]
                if value.startswith("-"):
                    remaining.append(f"{argument}={value}")
                else:
                    remaining.extend((argument, value))
                index += 2
            else:
                remaining.append(argument)
                index += 1
        elif argument == "--json":
            options.json = True
            index += 1
        elif argument == "--verbose":
            options.verbose = True
            index += 1
        elif argument in {"--chain-id", "--repo", "--run-id"}:
            if argument in seen_singletons:
                raise Refusal(
                    Revision9ReasonCode.OPTION_DUPLICATE,
                    f"forge: CLI option refused — duplicate {argument}",
                    expected=f"exactly one nonempty {argument}",
                    observed=f"duplicate {argument}",
                    remediation=f"remove the duplicate {argument} and retry",
                )
            seen_singletons.add(argument)
            if index + 1 >= len(argv):
                raise Refusal(
                    ReasonCode.STATE_PRECONDITION,
                    f"invalid CLI invocation: {argument} requires a value",
                    observed=argument,
                    remediation="forge status",
                )
            value = argv[index + 1]
            if value == "":
                raise Refusal(
                    Revision9ReasonCode.OPTION_EMPTY,
                    f"forge: CLI option refused — empty {argument}",
                    expected=f"one nonempty value for {argument}",
                    observed=f"empty {argument}",
                    remediation=f"supply a nonempty {argument} value",
                )
            if argument == "--chain-id":
                options.chain_id = value
            elif argument == "--repo":
                options.repo = value
            else:
                options.run_id = value
            index += 2
        elif any(
            argument.startswith(f"{name}=")
            for name in ("--chain-id", "--repo", "--run-id")
        ):
            name, _, value = argument.partition("=")
            if name in seen_singletons:
                raise Refusal(
                    Revision9ReasonCode.OPTION_DUPLICATE,
                    f"forge: CLI option refused — duplicate {name}",
                    expected=f"exactly one nonempty {name}",
                    observed=f"duplicate {name}",
                    remediation=f"remove the duplicate {name} and retry",
                )
            seen_singletons.add(name)
            if value == "":
                raise Refusal(
                    Revision9ReasonCode.OPTION_EMPTY,
                    f"forge: CLI option refused — empty {name}",
                    expected=f"one nonempty value for {name}",
                    observed=f"empty {name}",
                    remediation=f"supply a nonempty {name} value",
                )
            if name == "--chain-id":
                options.chain_id = value
            elif name == "--repo":
                options.repo = value
            else:
                options.run_id = value
            index += 1
        else:
            remaining.append(argument)
            index += 1
    if (
        options.chain_id
        and not chain_core.CHAIN_ID_RE.fullmatch(options.chain_id)
        and (not remaining or remaining[0] != "launch")
    ):
        raise Refusal(
            ReasonCode.STATE_PRECONDITION,
            "invalid --chain-id grammar",
            expected="c-YYYY-MM-DDTHHMMSSZ-4hex",
            observed=options.chain_id,
            remediation="forge status",
        )
    return options, remaining


def _attach_merge_lifecycle_parser(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Attach the dormant phase-3 merge lifecycle grammar."""

    _require_merge_lifecycle_control("dormant-parser-gate")
    merge = commands.add_parser("merge")
    merge_commands = merge.add_subparsers(dest="merge_command", required=True)
    start = merge_commands.add_parser("start")
    start.add_argument("--task", help=argparse.SUPPRESS)
    start.add_argument("--worktree", required=True)
    start.add_argument("--declare-tier", choices=tuple(chain_core.TIER_RANK))
    merge_commands.add_parser("refresh")
    merge_commands.add_parser("verify")
    gate = merge_commands.add_parser("gate")
    gate_commands = gate.add_subparsers(dest="merge_gate_command", required=True)
    gate_run = gate_commands.add_parser("run")
    gate_run.add_argument("gate_id")
    approve = merge_commands.add_parser("approve")
    approve.add_argument("--candidate", required=True)
    merge_commands.add_parser("finalize")
    recover = merge_commands.add_parser("recover")
    recover_mode = recover.add_mutually_exclusive_group()
    recover_mode.add_argument("--continue", dest="continue_rebase", action="store_true")
    recover_mode.add_argument("--abort-rebase", action="store_true")
    recover.add_argument("--paths", nargs="+")
    merge_commands.add_parser("cleanup")
    abort = merge_commands.add_parser("abort")
    abort.add_argument("--reason")


def build_parser() -> ContractArgumentParser:
    parser = ContractArgumentParser(
        prog="forge",
        add_help=True,
        description="Forge commit and merge gate chain CLI.",
        epilog=GLOBAL_OPTIONS_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    commands.add_parser("verify")
    commands.add_parser("classify")
    if runtime.MERGE_LIFECYCLE_ACTIVE:
        _attach_merge_lifecycle_parser(commands)

    commit = commands.add_parser("commit")
    commit_commands = commit.add_subparsers(dest="commit_command", required=True)
    start = commit_commands.add_parser(
        "start",
        description="Open a commit chain for explicit target paths.",
        epilog=GLOBAL_OPTIONS_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    start.add_argument("--paths", nargs="+", required=True, help="explicit target paths")
    start.add_argument("--task", help=argparse.SUPPRESS)
    start.add_argument("--declare-tier", choices=tuple(chain_core.TIER_RANK))
    restage = commit_commands.add_parser("restage")
    restage.add_argument("--paths", nargs="+", required=True)
    commit_commands.add_parser("rebase")
    abort = commit_commands.add_parser("abort")
    abort.add_argument("--reason")
    approve = commit_commands.add_parser("approve")
    approve.add_argument("--candidate", required=True)
    skip = commit_commands.add_parser("skip")
    targets = skip.add_mutually_exclusive_group(required=True)
    targets.add_argument("gate_id", nargs="?")
    targets.add_argument("--index-drift", action="store_true")
    skip.add_argument("--reason", required=True)
    finalize = commit_commands.add_parser("finalize")
    messages = finalize.add_mutually_exclusive_group(required=True)
    messages.add_argument("--message")
    messages.add_argument("--message-file")

    gate = commands.add_parser("gate")
    gate_commands = gate.add_subparsers(dest="gate_command", required=True)
    gate_run = gate_commands.add_parser("run")
    gate_run.add_argument("gate_id")

    scan = commands.add_parser("scan")
    scan_commands = scan.add_subparsers(dest="scan_command", required=True)
    scan_commands.add_parser("secrets")

    review = commands.add_parser("review")
    review_commands = review.add_subparsers(dest="review_command", required=True)
    review_commands.add_parser("request")
    review_commands.add_parser("collect")
    review_commands.add_parser("cancel")
    attach = review_commands.add_parser("attach")
    attach.add_argument("--verdict-file", required=True)
    disposition = review_commands.add_parser("disposition")
    disposition.add_argument("--finding", type=int, required=True)
    disposition.add_argument(
        "--severity", choices=("CRITICAL", "MAJOR", "MINOR"), required=True
    )
    disposition.add_argument("--resolution", required=True)

    chain = commands.add_parser("chain")
    chain_commands = chain.add_subparsers(dest="chain_command", required=True)
    tombstone = chain_commands.add_parser("tombstone")
    tombstone.add_argument("--reason", required=True)

    common_lock = commands.add_parser("common-lock")
    common_lock_commands = common_lock.add_subparsers(
        dest="common_lock_command", required=True
    )
    common_lock_hold = common_lock_commands.add_parser("hold")
    common_lock_hold.add_argument(
        "--owner-kind", choices=tuple(sorted(chain_core.COMMON_LOCK_OWNER_KINDS)), required=True
    )
    common_lock_hold.add_argument(
        "--operation", choices=tuple(sorted(chain_core.COMMON_LOCK_OPERATIONS)), required=True
    )
    common_lock_hold.add_argument("--ready-fd", type=int, required=True)

    launch = commands.add_parser("launch", allow_abbrev=False)
    launch.add_argument("launch_command", nargs="?", choices=("collect", "cancel"))
    launch.add_argument("--role", choices=("implementer", "plan"))
    launch.add_argument("--task")
    launch.add_argument("--worktree")
    launch.add_argument("--brief")
    launch.add_argument("--execution")
    return parser


def _raw_top_level_command(argv: Sequence[str]) -> str | None:
    """Find the command without consuming verb-owned option values."""

    index = 0
    while index < len(argv):
        argument = argv[index]
        if argument in {"--json", "--verbose"}:
            index += 1
            continue
        if argument in {"--chain-id", "--repo", "--run-id"}:
            index += 2
            continue
        if any(
            argument.startswith(f"{name}=")
            for name in ("--chain-id", "--repo", "--run-id")
        ):
            index += 1
            continue
        return argument
    return None
