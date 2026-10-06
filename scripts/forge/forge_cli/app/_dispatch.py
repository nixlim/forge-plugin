"""Extracted from scripts/forge/forge_cli/app/__init__.py."""
from __future__ import annotations
from forge_cli import chain_core, engine as _engine_module, runtime, engine
from forge_cli.app._merge_engine import MergeEngine
import argparse
from forge_cli.envelope import FrozenError, Outcome, ReasonCode, Refusal, OUTPUT_SCHEMA, REVISION9_OUTPUT_SCHEMA
import dataclasses
import sys
from typing import Sequence


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


def _dispatch_launch(engine: engine.Engine, args: argparse.Namespace) -> Outcome:
    if args.launch_command == "collect":
        return engine.launch_collect(args.execution)
    if args.launch_command == "cancel":
        return engine.launch_cancel(args.execution)
    return engine.launch(
        role=args.role, task=args.task, worktree=args.worktree, brief=args.brief
    )


def _dispatch_commit_start(
    command_engine: engine.Engine, args: argparse.Namespace
) -> Outcome:
    return command_engine.start(args.paths, args.declare_tier)


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
        if args.review_command == "cancel":
            return routed.review_cancel()
        if args.review_command == "attach":
            return routed.review_attach(args.verdict_file)
        if args.review_command == "disposition":
            return routed.review_disposition(
                args.finding, args.severity, args.resolution
            )
    if args.command == "launch":
        return _dispatch_launch(engine, args)
    if args.command == "commit":
        if args.commit_command == "start":
            return _dispatch_commit_start(engine, args)
        if args.commit_command == "restage":
            return engine.restage(args.paths)
        if args.commit_command == "rebase":
            return engine.rebase()
        if args.commit_command == "abort":
            return engine.abort(args.reason)
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
            raw_command in {"common-lock", "launch"}
            or (runtime.MERGE_LIFECYCLE_ACTIVE and raw_command == "merge")
        ),
    )
    try:
        options, command_argv = engine._extract_global_options(raw_argv)
        # Establish the envelope generation before argparse can refuse a
        # malformed new face.  Old phase-1 commands that merely use --repo or
        # --chain-id remain v1.
        options.revision9_face = bool(
            bool(command_argv and command_argv[0] == "launch")
            or bool(command_argv and command_argv[0] == "common-lock")
            or bool(
                runtime.MERGE_LIFECYCLE_ACTIVE
                and command_argv
                and command_argv[0] == "merge"
            )
        )
        args = engine.build_parser().parse_args(command_argv)
        engine._validate_revision9_cross_options(options, args)
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
