"""Forge CLI application layer (cli split phase 3, bead forge-plugin-95e.4).

Moved verbatim from scripts/forge/cli.py: the MergeEngine class, the shared chain-verb
router, and the argument-parsing and dispatch entry points; parser construction and other
helpers are read as ``engine.<name>`` through the canonical ``forge_cli.engine`` module."""

from __future__ import annotations

from typing import Sequence
import argparse
from forge_cli import chain_core, runtime, engine as _engine_module, engine
import dataclasses
import sys

from forge_cli.envelope import (
    FrozenError,
    OUTPUT_SCHEMA,
    Outcome,
    REVISION9_OUTPUT_SCHEMA,
    ReasonCode,
    Refusal,
    V2ReasonCode,
)
from ._mutation_journal import (
    _MUTATION_JOURNAL_SCHEMA as _MUTATION_JOURNAL_SCHEMA,
    _MUTATION_JOURNAL_SIDEBAND_PREFIX as _MUTATION_JOURNAL_SIDEBAND_PREFIX,
    _MUTATION_PERSISTENCE_ADVISORY as _MUTATION_PERSISTENCE_ADVISORY,
    _MUTATION_JOURNAL_REQUEST_KEYS as _MUTATION_JOURNAL_REQUEST_KEYS,
    _MUTATION_JOURNAL_PREIMAGE_KEYS as _MUTATION_JOURNAL_PREIMAGE_KEYS,
    _DeferredMutationRequestError as _DeferredMutationRequestError,
    _mutation_persistence_error as _mutation_persistence_error,
    _bounded_mutation_output as _bounded_mutation_output,
    _validate_deferred_mutation_request as _validate_deferred_mutation_request,
    _persist_deferred_mutation_result as _persist_deferred_mutation_result,
)
from forge_cli.app._admission import (
    prepare_merge_admission as prepare_merge_admission,
)
from forge_cli.app._candidate_observation import (
    _observe_current_merge_candidate as _observe_current_merge_candidate,
)
from forge_cli.app._merge_engine import (
    MergeEngine,
)


def _route_shared_chain_engine(engine: engine.Engine) -> engine.Engine | MergeEngine:
    """Route explicit shared verbs by the authenticated event-one family."""

    chain_id = engine.ctx.options.chain_id
    if chain_id is None:
        return engine
    if engine.ctx.store.tombstone(chain_id) is not None:
        return engine
    family = engine.ctx.store.chain_family(chain_id)
    if family == "commit":
        return engine
    engine.ctx.options.revision9_face = True
    merge_context = chain_core.CommandContext(
        repo=engine.ctx.repo,
        store=chain_core.MergeChainStore(engine.ctx.store.common_root),
        options=engine.ctx.options,
        policy=engine.ctx.policy,
    )
    return MergeEngine(merge_context)


def _merge_command_engine(engine: engine.Engine) -> MergeEngine:
    """Construct the dormant merge-family engine without implicit selection."""

    _engine_module._require_merge_lifecycle_control("dormant-parser-gate")
    engine.ctx.options.revision9_face = True
    return MergeEngine(
        chain_core.CommandContext(
            repo=engine.ctx.repo,
            store=chain_core.MergeChainStore(engine.ctx.store.common_root),
            options=engine.ctx.options,
            policy=engine.ctx.policy,
        )
    )


def dispatch(engine: engine.Engine, args: argparse.Namespace) -> Outcome:
    if args.command == "common-lock" and args.common_lock_command == "hold":
        return chain_core.hold_common_lock(
            engine.ctx.repo,
            owner_kind=args.owner_kind,
            chain_id=engine.ctx.options.chain_id,
            operation=args.operation,
            ready_fd=args.ready_fd,
        )
    if args.command == "status":
        return _route_shared_chain_engine(engine).status()
    if args.command == "chain" and args.chain_command == "tombstone":
        return engine.operator_tombstone(args.reason)
    if runtime.MERGE_LIFECYCLE_ACTIVE and args.command == "merge":
        merge_engine = _merge_command_engine(engine)
        if args.merge_command == "start":
            return merge_engine.start_chain(
                args.worktree,
                args.declare_tier,
                task=args.task,
            )
        if args.merge_command == "refresh":
            return merge_engine.refresh()
        if args.merge_command == "verify":
            return merge_engine.verify()
        if args.merge_command == "gate" and args.merge_gate_command == "run":
            return merge_engine.gate_run(args.gate_id)
        if args.merge_command == "approve":
            return merge_engine.approve(args.candidate)
        if args.merge_command == "finalize":
            return merge_engine.finalize()
        if args.merge_command == "recover":
            return merge_engine.recover(
                continue_rebase=args.continue_rebase,
                paths=args.paths,
                abort_rebase=args.abort_rebase,
            )
        if args.merge_command == "cleanup":
            return merge_engine.cleanup_chain()
        if args.merge_command == "abort":
            return merge_engine.abort(args.reason)
    if args.command == "verify":
        return engine.verify()
    if args.command == "classify":
        return engine.classify()
    if args.command == "gate" and args.gate_command == "run":
        return engine.gate_run(args.gate_id)
    if args.command == "scan" and args.scan_command == "secrets":
        return engine.scan_secrets()
    if args.command == "review":
        routed = _route_shared_chain_engine(engine)
        if args.review_command == "request":
            return routed.review_request()
        if args.review_command == "collect":
            return routed.review_collect()
        if args.review_command == "attach":
            return routed.review_attach(args.verdict_file)
        if args.review_command == "disposition":
            return routed.review_disposition(
                args.finding, args.severity, args.resolution
            )
    if args.command == "journal":
        if args.journal_command == "batch-recover":
            return engine.journal_batch_recover()
        if args.journal_command == "ingest-chain":
            return engine.journal_ingest_chain(
                task=args.task,
                state_file=args.state_file,
                events_file=args.events_file,
                outcome_map=args.outcome_map,
                closing_head=args.closing_head,
                task_status=args.task_status,
                idempotency_key=args.idempotency_key,
            )
    if args.command == "commit":
        if args.commit_command == "start":
            if (engine.ctx.options.run_id is None) != (args.task is None):
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
                args.task is not None or engine.ctx.options.run_id is not None
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
            return engine.start(
                args.paths or (),
                args.declare_tier,
                task=args.task,
                archive_run_id=args.archive_run_id,
                legacy_recovered_head=args.legacy_recovered_head,
                legacy_approval=args.legacy_approval,
                dispense_targets=tuple(args.dispense_citation),
                dispense_reason=args.dispense_reason,
            )
        if args.commit_command == "restage":
            return engine.restage(args.paths)
        if args.commit_command == "rebase":
            return engine.rebase()
        if args.commit_command == "abort":
            return engine.abort(args.reason)
        if args.commit_command == "abort-disposition":
            return engine.abort_disposition()
        if args.commit_command == "approve":
            if not chain_core.SHA256_RE.fullmatch(args.candidate):
                raise Refusal(
                    ReasonCode.CANDIDATE_STALE,
                    "approval candidate must be a full lowercase SHA-256",
                    expected="64 lowercase hexadecimal characters",
                    observed=args.candidate,
                    remediation="forge status",
                )
            return engine.approve(args.candidate)
        if args.commit_command == "skip":
            return engine.skip(args.gate_id, args.index_drift, args.reason)
        if args.commit_command == "finalize":
            return engine.finalize(_engine_module._message_from_args(args))
    raise FrozenError("parsed command has no dispatch implementation")


def main(argv: Sequence[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    raw_command = engine._raw_top_level_command(raw_argv)
    options = chain_core.CLIOptions(
        json="--json" in raw_argv,
        verbose="--verbose" in raw_argv,
        original_argv=tuple(raw_argv),
        revision9_face=(
            raw_command == "common-lock"
            or (runtime.MERGE_LIFECYCLE_ACTIVE and raw_command == "merge")
        ),
    )
    try:
        options, command_argv = engine._extract_global_options(raw_argv)
        # Establish the envelope generation before argparse can refuse a
        # malformed new face.  Old phase-1 commands that merely use --repo or
        # --chain-id remain v1.
        options.revision9_face = bool(
            options.run_id is not None
            or "journal" in command_argv
            or bool(command_argv and command_argv[0] == "common-lock")
            or bool(
                runtime.MERGE_LIFECYCLE_ACTIVE
                and command_argv
                and command_argv[0] == "merge"
            )
            or any(
                token == name or token.startswith(f"{name}=")
                for token in command_argv
                for name in (
                    "--task",
                    "--archive-run-id",
                    "--legacy-recovered-head",
                    "--legacy-approval",
                    "--dispense-citation",
                    "--dispense-reason",
                )
            )
        )
        args = engine.build_parser().parse_args(command_argv)
        options.revision9_face = options.revision9_face or bool(
            args.command in {"journal", "common-lock"}
            or (runtime.MERGE_LIFECYCLE_ACTIVE and args.command == "merge")
            or (
                args.command == "commit"
                and args.commit_command == "start"
                and (
                    args.archive_run_id is not None
                    or args.task is not None
                    or options.run_id is not None
                )
            )
        )
        run_id_admitted = bool(
            args.command == "journal"
            or (
                runtime.MERGE_LIFECYCLE_ACTIVE
                and args.command == "merge"
                and args.merge_command == "start"
            )
            or (
                args.command == "commit"
                and args.commit_command == "start"
                and getattr(args, "archive_run_id", None) is None
            )
            # bead forge-plugin-11a: a tombstoned chain has no state to inherit
            # a run from, so the disposition verb names the run explicitly.
            or (args.command == "commit" and args.commit_command == "abort-disposition")
        )
        if options.run_id is not None and not run_id_admitted:
            options.revision9_face = True
            raise Refusal(
                V2ReasonCode.RUN_TASK_BINDING_INVALID,
                "forge: CLI run/task binding refused — later chain verbs inherit state and take no --run-id",
                expected="no --run-id on a later chain verb",
                observed="--run-id supplied outside chain start or journal operation",
                remediation="remove --run-id and select the immutable chain binding",
            )
        if args.command == "journal" and (
            options.repo is None or options.run_id is None
        ):
            options.revision9_face = True
            raise Refusal(
                V2ReasonCode.RUN_TASK_BINDING_INVALID,
                "forge: journal operation refused — explicit --repo and --run-id are required",
                expected="one nonempty --repo and --run-id",
                observed="missing journal repository or run identity",
                remediation="rerun with the exact --repo and --run-id",
            )
        engine._validate_revision9_cross_options(options, args)
        if options.revision9_face:
            chain_core.register_coordination_seams()
        repo = chain_core.Repository.discover(options.repo)
        store = chain_core.ChainStore(repo.common_root())
        ctx = chain_core.CommandContext(repo=repo, store=store, options=options)
        outcome = dispatch(engine.Engine(ctx), args)
    except Refusal as exc:
        outcome = exc.outcome()
    except FrozenError as exc:
        outcome = exc.outcome()
    except Exception as exc:
        # Internal failures are deliberately converted to the sole exit-2
        # envelope.  No traceback is exposed through the command surface.
        outcome = FrozenError(
            f"unexpected internal failure while attempting CLI command: {exc}",
            chain_id=options.chain_id,
            observed=type(exc).__name__,
            schema=(
                REVISION9_OUTPUT_SCHEMA
                if options.revision9_face
                else OUTPUT_SCHEMA
            ),
        ).outcome()
    if options.revision9_face and outcome.schema != REVISION9_OUTPUT_SCHEMA:
        outcome = dataclasses.replace(outcome, schema=REVISION9_OUTPUT_SCHEMA)
    engine.render(outcome, as_json=options.json)
    return outcome.exit_code


__all__ = [
    'MergeEngine',
    '_merge_command_engine',
    '_observe_current_merge_candidate',
    '_route_shared_chain_engine',
    'dispatch',
    'main',
    'prepare_merge_admission',
]
