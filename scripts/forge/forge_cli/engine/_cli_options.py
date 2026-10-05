"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
import argparse
from pathlib import Path
from forge_cli.envelope import ReasonCode, Refusal, REVISION9_OUTPUT_SCHEMA, V2ReasonCode, Outcome
from forge_cli import chain_core, runtime
import re
import sys

LAUNCH_RUN_ID_REQUIRED = "forge: launch refused — explicit --repo and --run-id are required"

_BACKFILL_MODE_CONFLICT = (
    "forge: archive refused — backfill closing mode cannot be combined with "
    "normal or legacy closing mode"
)
_BACKFILL_APPROVAL_REFUSAL = (
    "forge: archive refused — backfill approval missing or mismatched"
)


def _message_from_args(args: argparse.Namespace) -> str:
    if args.message is not None:
        message = args.message
    else:
        path = Path(args.message_file)
        try:
            message = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise Refusal(
                ReasonCode.STATE_PRECONDITION,
                f"commit message file is unreadable: {exc}",
                observed=str(path),
                remediation="forge commit finalize --message <message>",
            ) from exc
    if not message.strip() or "\x00" in message:
        raise Refusal(
            ReasonCode.STATE_PRECONDITION,
            "commit message must be nonempty UTF-8 without NUL",
            observed="empty or NUL-containing message",
            remediation="forge commit finalize --message <message>",
        )
    return message


def _validate_commit_start_closing_options(
    args: argparse.Namespace,
) -> tuple[tuple[bool, bool], tuple[bool, bool]]:
    """Validate archive closing-mode tuples before repository discovery."""

    legacy_pair = (
        args.legacy_recovered_head is not None,
        args.legacy_approval is not None,
    )
    backfill_pair = (
        args.backfill_closing_head is not None,
        args.backfill_approval is not None,
    )
    if any(backfill_pair) and (
        args.closing_head is not None or any(legacy_pair)
    ):
        raise Refusal(
            V2ReasonCode.LEGACY_RECOVERY_APPROVAL_REQUIRED,
            _BACKFILL_MODE_CONFLICT,
            expected="one closing mode",
            observed="backfill and normal or legacy closing flags",
            remediation="remove the normal and legacy flags or the backfill flags",
        )
    if backfill_pair[0] != backfill_pair[1]:
        raise Refusal(
            V2ReasonCode.LEGACY_RECOVERY_APPROVAL_REQUIRED,
            _BACKFILL_APPROVAL_REFUSAL,
            expected="paired --backfill-closing-head and --backfill-approval",
            observed="exactly one backfill flag",
            remediation="supply both backfill flags with the reviewed tuple",
        )
    if args.closing_head is not None and any(legacy_pair):
        raise Refusal(
            V2ReasonCode.LEGACY_RECOVERY_APPROVAL_REQUIRED,
            "forge: archive refused — legacy recovery approval missing or mismatched",
            expected="normal or paired legacy closing mode",
            observed="normal and legacy closing flags",
            remediation="remove --closing-head or both legacy recovery flags",
        )
    return legacy_pair, backfill_pair


def _validate_revision9_cross_options(
    options: chain_core.CLIOptions, args: argparse.Namespace
) -> None:
    """Refuse Revision-9 flag tuples before repository discovery."""

    if args.command == "launch":
        options.revision9_face = True
        if options.repo is None or options.run_id is None:
            raise Refusal(
                V2ReasonCode.RUN_TASK_BINDING_INVALID,
                LAUNCH_RUN_ID_REQUIRED,
                expected="one nonempty --repo and --run-id",
                observed="missing launch repository or run identity",
                remediation="rerun launch with the exact --repo and --run-id",
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        if options.chain_id is not None:
            raise Refusal(
                V2ReasonCode.RUN_TASK_BINDING_INVALID,
                "forge: launch refused — --chain-id is not admitted",
                expected="no chain identity",
                observed=options.chain_id,
                remediation="remove --chain-id and retry launch",
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        command = args.launch_command
        start_values = (args.role, args.task, args.worktree, args.brief)
        if command is None:
            if any(value is None for value in start_values) or args.execution is not None:
                raise Refusal(
                    V2ReasonCode.STATE_PRECONDITION,
                    "forge: launch refused — --role, --task, --worktree and --brief "
                    "are required, and --execution is not admitted",
                    expected="the exact launch start option tuple",
                    observed="missing or conflicting launch start options",
                    remediation="supply the four start options and remove --execution",
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            return
        execution = args.execution
        if any(value is not None for value in start_values) or not isinstance(
            execution, str
        ) or re.fullmatch(r"execution-[0-9]{2}", execution) is None:
            raise Refusal(
                V2ReasonCode.STATE_PRECONDITION,
                f"forge: launch {command} refused — exactly --execution execution-NN "
                "is required",
                expected="one two-digit execution identity and no start options",
                observed="missing, malformed, or conflicting launch options",
                remediation=f"rerun launch {command} with exactly --execution execution-NN",
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        return

    if args.command == "chain" and args.chain_command == "tombstone":
        options.revision9_face = True
        if options.chain_id is None:
            raise Refusal(
                V2ReasonCode.STATE_PRECONDITION,
                "forge: chain tombstone refused — explicit --chain-id is required",
                expected="one exact frozen or absent chain identity",
                observed="missing chain identity",
                remediation="rerun with --chain-id <chain-id>",
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        return

    if (
        runtime.MERGE_LIFECYCLE_ACTIVE
        and args.command == "merge"
        and args.merge_command == "start"
    ):
        if (options.run_id is None) != (args.task is None):
            raise Refusal(
                V2ReasonCode.RUN_TASK_BINDING_REQUIRED,
                "forge: merge start refused — --run-id and --task must be supplied together",
                expected="both --run-id and --task, or neither",
                observed="exactly one run/task binding flag",
                remediation="rerun merge start with both binding flags or neither",
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        if options.chain_id is not None:
            raise Refusal(
                V2ReasonCode.STATE_PRECONDITION,
                "forge: merge start refused — --chain-id is not admitted for a new chain",
                expected="no preselected chain identity",
                observed=options.chain_id,
                remediation="remove --chain-id and retry merge start",
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        return
    if runtime.MERGE_LIFECYCLE_ACTIVE and args.command == "merge":
        if options.chain_id is None:
            raise Refusal(
                V2ReasonCode.STATE_PRECONDITION,
                "forge: merge shared verb refused — explicit --chain-id is required",
                expected="one exact merge chain identity",
                observed="missing chain identity",
                remediation="rerun with --chain-id <chain-id>",
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        if args.merge_command == "recover":
            continuing = bool(getattr(args, "continue_rebase", False))
            paths = getattr(args, "paths", None)
            if continuing != bool(paths):
                raise Refusal(
                    V2ReasonCode.STATE_PRECONDITION,
                    "forge: merge recover refused — --continue requires --paths and --paths requires --continue",
                    expected="--continue --paths <path>... or neither",
                    observed="incomplete conflict-resolution tuple",
                    remediation="retry with the exact recover surface",
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
        return
    if args.command != "commit" or args.commit_command != "start":
        return
    legacy_pair, backfill_pair = _validate_commit_start_closing_options(args)
    task = args.task
    if (options.run_id is None) != (task is None):
        raise Refusal(
            V2ReasonCode.RUN_TASK_BINDING_REQUIRED,
            "forge: commit start refused — --run-id and --task must be supplied together",
            expected="both --run-id and --task, or neither",
            observed="exactly one run/task binding flag",
            remediation="rerun commit start with both binding flags or neither",
        )
    if legacy_pair[0] != legacy_pair[1]:
        raise Refusal(
            V2ReasonCode.LEGACY_RECOVERY_APPROVAL_REQUIRED,
            "forge: archive refused — legacy recovery approval missing or mismatched",
            expected="paired --legacy-recovered-head and --legacy-approval",
            observed="exactly one legacy recovery flag",
            remediation="supply both legacy recovery flags with the reviewed tuple",
        )
    if args.archive_run_id is not None and (
        args.task is not None or options.run_id is not None
    ):
        raise Refusal(
            V2ReasonCode.RUN_TASK_BINDING_INVALID,
            "forge: archive refused — archive-only chains cannot carry a run/task binding",
            expected="--archive-run-id without --run-id or --task",
            observed="archive and run/task binding flags",
            remediation="remove --run-id and --task from archive commit start",
        )
    if args.archive_run_id is None and (
        any(backfill_pair)
    ):
        raise Refusal(
            V2ReasonCode.LEGACY_RECOVERY_APPROVAL_REQUIRED,
            _BACKFILL_APPROVAL_REFUSAL,
            expected="backfill flags only with --archive-run-id",
            observed="backfill flag on an ordinary commit start",
            remediation="supply --archive-run-id or remove backfill flags",
        )
    if args.archive_run_id is None and (
        args.closing_head is not None
        or any(legacy_pair)
        or args.dispense_citation
        or args.dispense_reason
    ):
        raise Refusal(
            V2ReasonCode.LEGACY_RECOVERY_APPROVAL_REQUIRED,
            "forge: archive refused — legacy recovery approval missing or mismatched",
            expected="archive flags only with --archive-run-id",
            observed="archive-only flag on an ordinary commit start",
            remediation="supply --archive-run-id or remove archive-only flags",
        )


def render(outcome: Outcome, *, as_json: bool) -> None:
    if as_json:
        sys.stdout.write(chain_core.canonical_bytes(outcome.envelope()).decode("utf-8") + "\n")
        return
    sys.stdout.write(outcome.message.rstrip("\n") + "\n")
    if not outcome.ok:
        sys.stdout.write(f"reason code: {outcome.reason_code.value}\n")
        if outcome.state is not None:
            sys.stdout.write(f"state: {outcome.state}\n")
        if outcome.expected is not None:
            expected = outcome.expected
            if re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", expected):
                expected = expected[:12] + "…"
            sys.stdout.write(f"expected: {expected}\n")
        if outcome.observed is not None:
            observed = outcome.observed
            if re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", observed):
                observed = observed[:12] + "…"
            sys.stdout.write(f"observed: {observed}\n")
        if outcome.remediation is not None:
            sys.stdout.write(f"remediation: {outcome.remediation}\n")
    sys.stdout.write(f"next required step: {outcome.next_required_step}\n")
