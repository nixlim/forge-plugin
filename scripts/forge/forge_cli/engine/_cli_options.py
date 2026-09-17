"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
import argparse
from pathlib import Path
from forge_cli.engine._core import commit_message_bytes as commit_message_bytes, chain_id_now as chain_id_now, promoted_tier as promoted_tier, _transition_state as _transition_state, _require_merge_lifecycle_control as _require_merge_lifecycle_control, inspect_common_lock as inspect_common_lock, _archive_refusal as _archive_refusal, _archive_contamination_refusal as _archive_contamination_refusal, _archive_metadata as _archive_metadata, _env_fingerprint as _env_fingerprint, _evidence_record as _evidence_record, _write_artifact as _write_artifact, _read_bound_artifact as _read_bound_artifact, _record_process_step as _record_process_step, _run_halt as _run_halt, MergeAdmission as MergeAdmission, MergeScopeResult as MergeScopeResult, MergeCandidateGeneration as MergeCandidateGeneration, MergeBootstrapClassification as MergeBootstrapClassification
from forge_cli.engine._parser import ContractArgumentParser as ContractArgumentParser, _extract_global_options as _extract_global_options, _attach_merge_lifecycle_parser as _attach_merge_lifecycle_parser, build_parser as build_parser, _raw_top_level_command as _raw_top_level_command
from forge_cli.engine._state import TERMINAL_STATES as TERMINAL_STATES, TERMINAL_TOUCH_VERBS as TERMINAL_TOUCH_VERBS, STATE_TRANSITIONS as STATE_TRANSITIONS, TOKEN_TTL_SECONDS as TOKEN_TTL_SECONDS, _REQUIRED_MERGE_LIFECYCLE_CONTROLS as _REQUIRED_MERGE_LIFECYCLE_CONTROLS, MERGE_LIFECYCLE_CONTROLS as MERGE_LIFECYCLE_CONTROLS, _REQUIRED_ARCHIVE_RECHECK_CONTROLS as _REQUIRED_ARCHIVE_RECHECK_CONTROLS, ARCHIVE_RECHECK_CONTROLS as ARCHIVE_RECHECK_CONTROLS, _CHAIN_CAPABILITY_LOCK as _CHAIN_CAPABILITY_LOCK, _CHAIN_CAPABILITIES as _CHAIN_CAPABILITIES, CODEX_EXECUTABLE as CODEX_EXECUTABLE, FRESH_REVIEWER_EVAL_REQUEST_SCHEMA as FRESH_REVIEWER_EVAL_REQUEST_SCHEMA, REVIEW_DIRECT_PACKAGE_MAX_BYTES as REVIEW_DIRECT_PACKAGE_MAX_BYTES, REVIEW_MASTER_WINDOW_BYTES as REVIEW_MASTER_WINDOW_BYTES, REVIEW_COMPLETE_PACKAGE_REFUSAL as REVIEW_COMPLETE_PACKAGE_REFUSAL, PRODUCED_COMMIT_MISMATCH as PRODUCED_COMMIT_MISMATCH, REVIEW_INSTRUCTION as REVIEW_INSTRUCTION, REVIEW_LAUNCHER_CODE as REVIEW_LAUNCHER_CODE, GLOBAL_OPTIONS_HELP as GLOBAL_OPTIONS_HELP, ARCHIVE_CONTAMINATION as ARCHIVE_CONTAMINATION, SECRET_RULES as SECRET_RULES, PLACEHOLDER_RE as PLACEHOLDER_RE, ABORT_DISPOSITION_PRECONDITIONS as ABORT_DISPOSITION_PRECONDITIONS, _MERGE_CANDIDATE_IDENTITY_FIELDS as _MERGE_CANDIDATE_IDENTITY_FIELDS, _MERGE_BOOTSTRAP_CHILD_SOURCE as _MERGE_BOOTSTRAP_CHILD_SOURCE, _DERIVE_MERGE_SCOPE as _DERIVE_MERGE_SCOPE, _MERGE_INITIAL_INTEGRATION as _MERGE_INITIAL_INTEGRATION
from forge_cli.envelope import ReasonCode, Refusal, REVISION9_OUTPUT_SCHEMA, V2ReasonCode, Outcome
from forge_cli import chain_core, runtime
import re
import sys


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


def _validate_revision9_cross_options(
    options: chain_core.CLIOptions, args: argparse.Namespace
) -> None:
    """Refuse Revision-9 flag tuples before repository discovery."""

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
    task = args.task
    if (options.run_id is None) != (task is None):
        raise Refusal(
            V2ReasonCode.RUN_TASK_BINDING_REQUIRED,
            "forge: commit start refused — --run-id and --task must be supplied together",
            expected="both --run-id and --task, or neither",
            observed="exactly one run/task binding flag",
            remediation="rerun commit start with both binding flags or neither",
        )
    legacy_pair = (
        args.legacy_recovered_head is not None,
        args.legacy_approval is not None,
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
        any(legacy_pair) or args.dispense_citation or args.dispense_reason
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
