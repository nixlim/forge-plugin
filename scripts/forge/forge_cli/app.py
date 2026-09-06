"""Forge CLI application layer (cli split phase 3, bead forge-plugin-95e.4).

Moved verbatim from scripts/forge/cli.py: the MergeEngine class, the shared chain-verb
router, and the argument-parsing and dispatch entry points; parser construction and other
helpers are read as ``engine.<name>`` through the canonical ``forge_cli.engine`` module."""

from __future__ import annotations

from typing import Any, Callable, Collection, Iterable, Mapping, MutableMapping, Sequence
from pathlib import Path
import argparse
import base64
from forge_cli import chain_core
import contextlib
import copy
import dataclasses
import os
import re
from forge_cli import runtime
import secrets
import socket
import stat
import sys

from forge_cli import engine as _engine_module
from forge_cli import runtime
from forge_cli import engine
from forge_cli.envelope import (
    FrozenError,
    OUTPUT_SCHEMA,
    Outcome,
    REVISION9_OUTPUT_SCHEMA,
    ReasonCode,
    Refusal,
    V2ReasonCode,
)
from forge_cli.policy import (
    Policy,
    PolicyError,
    parse_policy,
    sha256_bytes,
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


def prepare_merge_admission(
    ctx: chain_core.CommandContext,
    worktree: str,
    declared_tier: str | None,
    *,
    task: str | None = None,
) -> engine.MergeAdmission:
    """Prove the read-only half of FR-231 without activating merge routing."""

    chain_core._require_merge_adapter_control("admission-and-generation")
    chain_core._require_merge_adapter_control("halt")
    engine._run_halt(ctx, scope="merge")
    if declared_tier is not None and declared_tier not in chain_core.TIER_RANK:
        raise chain_core._merge_refusal(
            V2ReasonCode.WORKTREE_INVALID,
            "forge: merge start refused — declared tier is invalid",
            expected="fast, standard, hard, or no declaration",
            observed=str(declared_tier),
        )
    if (ctx.options.run_id is None) != (task is None):
        raise chain_core._merge_refusal(
            V2ReasonCode.RUN_TASK_BINDING_REQUIRED,
            "forge: merge start refused — --run-id and --task must be supplied together",
            expected="both binding flags or neither binding flag",
            observed=f"run_id={ctx.options.run_id!r}, task={task!r}",
            remediation="retry start with the exact paired --run-id and --task",
        )
    supplied = Path(worktree)
    lexical = Path(os.path.abspath(os.fspath(supplied)))
    if not lexical.exists():
        raise chain_core._merge_refusal(
            V2ReasonCode.WORKTREE_MISSING,
            "forge: merge start refused — worktree path does not exist",
            expected="an existing registered linked worktree",
            observed=str(lexical),
        )
    try:
        canonical = lexical.resolve(strict=True)
    except OSError as exc:
        raise chain_core._merge_refusal(
            V2ReasonCode.WORKTREE_INVALID,
            "forge: merge start refused — worktree path is invalid",
            observed=str(exc),
        ) from exc
    if canonical != lexical:
        raise chain_core._merge_refusal(
            V2ReasonCode.WORKTREE_INVALID,
            "forge: merge start refused — worktree path has an ambiguous symlink spelling",
            expected=str(canonical),
            observed=str(lexical),
        )

    main = chain_core.Repository(ctx.repo.common_root())
    main_head = main.head()
    manifest_process = main.git(
        ["show", f"{main_head}:.forge-manifest"], check=False
    )
    if manifest_process.returncode != 0:
        raise chain_core._merge_refusal(
            V2ReasonCode.PUSH_TARGET_INVALID,
            "forge: merge start refused — committed target manifest is unreadable",
            expected=f"git show {main_head}:.forge-manifest",
            observed=manifest_process.stderr.decode("utf-8", "replace").strip(),
        )
    try:
        default_branch = engine._parse_plugin_manifest(manifest_process.stdout)
    except ValueError as exc:
        raise chain_core._merge_refusal(
            V2ReasonCode.PUSH_TARGET_INVALID,
            "forge: merge start refused — committed target manifest is invalid",
            expected="the committed initialized plugin-schema .forge-manifest",
            observed=str(exc),
        ) from exc
    destination_ref = f"refs/heads/{default_branch}"
    if main.git(["check-ref-format", destination_ref], check=False).returncode != 0:
        raise chain_core._merge_refusal(
            V2ReasonCode.PUSH_TARGET_INVALID,
            "forge: merge start refused — manifest default branch is not a valid ref",
            observed=default_branch,
        )

    try:
        inventory = engine._registered_worktrees(main)
    except OSError as exc:
        raise chain_core._merge_refusal(
            V2ReasonCode.WORKTREE_INVALID,
            "forge: merge start refused — registered worktree inventory is invalid",
            observed=str(exc),
        ) from exc
    matches = []
    for entry in inventory:
        try:
            registered = Path(entry["worktree"]).resolve(strict=True)
        except OSError:
            continue
        if registered == canonical:
            matches.append(entry)
    main_path = Path(inventory[0]["worktree"]).resolve(strict=True) if inventory else main.root
    if len(matches) != 1 or canonical == main_path:
        raise chain_core._merge_refusal(
            V2ReasonCode.WORKTREE_INVALID,
            "forge: merge start refused — source is not one registered non-main worktree",
            expected="exactly one registered linked worktree entry",
            observed=str(canonical),
        )
    entry = matches[0]
    branch = entry.get("branch")
    if (
        not isinstance(branch, str)
        or not branch.startswith("refs/heads/")
        or branch == destination_ref
    ):
        raise chain_core._merge_refusal(
            V2ReasonCode.WORKTREE_INVALID,
            "forge: merge start refused — source worktree branch is not an eligible local branch",
            expected=f"a local non-{destination_ref} branch",
            observed=str(branch or "detached"),
        )
    candidate = chain_core.Repository(canonical)
    if candidate.git(["show-ref", "--verify", branch], check=False).returncode != 0:
        raise chain_core._merge_refusal(
            V2ReasonCode.WORKTREE_INVALID,
            "forge: merge start refused — source branch is not local",
            observed=branch,
        )
    candidate_head = candidate.head()
    if candidate_head != entry.get("HEAD"):
        raise chain_core._merge_refusal(
            V2ReasonCode.WORKTREE_INVALID,
            "forge: merge start refused — registered worktree HEAD changed during admission",
            expected=str(entry.get("HEAD")),
            observed=candidate_head,
        )
    try:
        git_dir = engine._absolute_git_path(candidate, "--git-dir")
        common_dir = engine._absolute_git_path(candidate, "--git-common-dir")
    except OSError as exc:
        raise chain_core._merge_refusal(
            V2ReasonCode.WORKTREE_INVALID,
            "forge: merge start refused — worktree Git identity is invalid",
            observed=str(exc),
        ) from exc
    if common_dir != main.git_common_dir():
        raise chain_core._merge_refusal(
            V2ReasonCode.WORKTREE_INVALID,
            "forge: merge start refused — worktree has a foreign Git common directory",
            expected=str(main.git_common_dir()),
            observed=str(common_dir),
        )
    if candidate.git(["remote", "get-url", "origin"], check=False).returncode != 0:
        raise chain_core._merge_refusal(
            V2ReasonCode.PUSH_TARGET_INVALID,
            "forge: merge start refused — fixed origin target is unavailable",
            expected="configured remote origin",
            observed=str(canonical),
        )
    status = engine._merge_worktree_status(candidate, git_dir)
    try:
        policy_commit, policy_raw = candidate.policy(candidate_head)
        policy = parse_policy(policy_commit, policy_raw)
    except (OSError, PolicyError, UnicodeError) as exc:
        raise chain_core._merge_refusal(
            V2ReasonCode.POLICY_UNREADABLE,
            f"forge: merge start refused — committed candidate policy is unreadable: {exc}",
            expected=f"valid {candidate_head}:forge-project.md",
            observed=str(exc),
        ) from exc
    run_task = None
    if ctx.options.run_id is not None and task is not None:
        run_task = chain_core._prove_merge_run_task_binding(
            main.root,
            ctx.store.common_root,
            ctx.options.run_id,
            task,
            policy.digest,
        )
    return engine.MergeAdmission(
        repository=main.root,
        worktree=candidate.root,
        worktree_identity={
            "path": str(candidate.root),
            "git_dir": str(git_dir),
            "common_dir": str(common_dir),
        },
        branch=branch,
        target={
            "remote": "origin",
            "destination_ref": destination_ref,
            "manifest_commit": main_head,
        },
        candidate_head=candidate_head,
        policy=policy,
        declared_tier=declared_tier,
        run_task=run_task,
        status_output_digest=sha256_bytes(status),
    )


def _observe_current_merge_candidate(
    ctx: chain_core.CommandContext,
    state: Mapping[str, Any],
    *,
    verb: str,
    observation: Mapping[str, Any] | None = None,
) -> tuple[chain_core.Repository, Policy, tuple[str, ...]]:
    """Recompute every FR-233 post-executable generation member."""

    chain_core._require_merge_adapter_control("admission-and-generation")
    if observation is not None:
        repository, policy, changed_paths, _diff, _classifier = (
            engine._parse_merge_candidate_observation(
                state,
                observation,
                verb=verb,
                require_current_generation=True,
            )
        )
        return repository, policy, changed_paths
    candidate = state.get("candidate")
    worktree = state.get("worktree")
    target = state.get("target")
    policy_source = state.get("policy_source")
    if not all(
        isinstance(value, Mapping)
        for value in (candidate, worktree, target, policy_source)
    ):
        raise FrozenError(
            "merge candidate tuple is unavailable",
            chain_id=str(state.get("chain_id") or "") or None,
            schema=REVISION9_OUTPUT_SCHEMA,
        )
    assert isinstance(candidate, Mapping)
    assert isinstance(worktree, Mapping)
    assert isinstance(target, Mapping)
    assert isinstance(policy_source, Mapping)
    path = Path(str(worktree.get("path", "")))
    if not path.exists():
        raise chain_core._merge_refusal(
            V2ReasonCode.STATE_PRECONDITION,
            f"forge: {verb} refused — recorded worktree is missing",
            expected=str(path),
            observed="foreign-git-state",
            remediation=f"forge status --chain-id {state['chain_id']}",
            chain=state,
        )
    repository = chain_core.Repository(path)
    try:
        git_dir = engine._absolute_git_path(repository, "--git-dir")
        common_dir = engine._absolute_git_path(repository, "--git-common-dir")
    except OSError as exc:
        raise chain_core._merge_refusal(
            V2ReasonCode.WORKTREE_INVALID,
            f"forge: {verb} refused — recorded worktree identity is invalid",
            observed=str(exc),
            chain=state,
        ) from exc
    observed_identity = {
        "path": str(repository.root),
        "git_dir": str(git_dir),
        "common_dir": str(common_dir),
    }
    expected_identity = {
        name: str(worktree.get(name, ""))
        for name in ("path", "git_dir", "common_dir")
    }
    if observed_identity != expected_identity:
        raise chain_core._merge_refusal(
            V2ReasonCode.WORKTREE_INVALID,
            f"forge: {verb} refused — recorded worktree identity changed",
            expected=chain_core.canonical_bytes(expected_identity).decode("utf-8"),
            observed=chain_core.canonical_bytes(observed_identity).decode("utf-8"),
            chain=state,
        )
    engine._merge_worktree_status(repository, git_dir, verb=verb)
    current_head = repository.head()
    expected_head = str(candidate.get("candidate_head", ""))
    if current_head != expected_head:
        raise chain_core._merge_refusal(
            V2ReasonCode.CANDIDATE_STALE,
            f"forge: {verb} refused — candidate HEAD is stale",
            expected=expected_head,
            observed=current_head,
            remediation=f"forge merge refresh --chain-id {state['chain_id']}",
            chain=state,
        )

    main = chain_core.Repository(Path(str(state["repository"])))
    manifest_commit = main.head()
    manifest = main.git(
        ["show", f"{manifest_commit}:.forge-manifest"], check=False
    )
    try:
        default_branch = (
            engine._parse_plugin_manifest(manifest.stdout)
            if manifest.returncode == 0
            else ""
        )
    except ValueError:
        default_branch = ""
    observed_target = {
        "remote": "origin",
        "destination_ref": f"refs/heads/{default_branch}",
        "manifest_commit": manifest_commit,
    }
    if observed_target != dict(target):
        raise chain_core._merge_refusal(
            V2ReasonCode.PUSH_TARGET_INVALID,
            f"forge: {verb} refused — fixed merge target changed",
            expected=chain_core.canonical_bytes(dict(target)).decode("utf-8"),
            observed=chain_core.canonical_bytes(observed_target).decode("utf-8"),
            chain=state,
        )
    try:
        policy_commit, policy_raw = repository.policy(current_head)
        policy = parse_policy(policy_commit, policy_raw)
    except (OSError, PolicyError, UnicodeError) as exc:
        raise chain_core._merge_refusal(
            V2ReasonCode.POLICY_UNREADABLE,
            f"forge: {verb} refused — committed candidate policy is unreadable: {exc}",
            observed=str(exc),
            chain=state,
        ) from exc
    if (
        policy.sha != policy_source.get("commit")
        or policy.digest != policy_source.get("digest")
    ):
        raise chain_core._merge_refusal(
            V2ReasonCode.CANDIDATE_STALE,
            f"forge: {verb} refused — committed candidate policy changed",
            expected=str(policy_source.get("digest")),
            observed=policy.digest,
            chain=state,
        )
    remote_tip = str(candidate.get("remote_tip", ""))
    diff = repository.git(
        ["diff", f"{remote_tip}...{current_head}"], check=False
    )
    if diff.returncode != 0:
        raise chain_core._merge_refusal(
            V2ReasonCode.CANDIDATE_STALE,
            f"forge: {verb} refused — fixed candidate range is unavailable",
            observed=diff.stderr.decode("utf-8", "replace").strip(),
            chain=state,
        )
    observed_preimage = {
        "remote": "origin",
        "destination_ref": str(target["destination_ref"]),
        "remote_tip": remote_tip,
        "candidate_head": current_head,
        "diff_sha256": sha256_bytes(diff.stdout),
        "policy_commit": policy.sha,
        "policy_digest": policy.digest,
        "worktree_identity": observed_identity,
        "generation": candidate.get("generation"),
    }
    observed_candidate = {
        **observed_preimage,
        "generation_digest": sha256_bytes(chain_core.canonical_bytes(observed_preimage)),
    }
    if observed_candidate != dict(candidate):
        raise chain_core._merge_refusal(
            V2ReasonCode.CANDIDATE_STALE,
            f"forge: {verb} refused — merge generation tuple is stale",
            expected=str(candidate.get("generation_digest")),
            observed=observed_candidate["generation_digest"],
            remediation=f"forge merge refresh --chain-id {state['chain_id']}",
            chain=state,
        )
    names = repository.git(
        [
            "diff",
            "--name-only",
            "-z",
            "--diff-filter=ACDMRTUXB",
            f"{remote_tip}...{current_head}",
            "--",
        ]
    ).stdout
    try:
        changed_paths = tuple(
            sorted(
                {item.decode("utf-8") for item in names.split(b"\0") if item},
                key=lambda value: value.encode("utf-8"),
            )
        )
    except UnicodeDecodeError as exc:
        raise chain_core._merge_refusal(
            V2ReasonCode.WORKTREE_INVALID,
            f"forge: {verb} refused — candidate paths are not UTF-8",
            observed=str(exc),
            chain=state,
        ) from exc
    return repository, policy, changed_paths


class MergeEngine:
    """Dormant merge-family target for explicit shared CLI verbs."""

    def __init__(self, ctx: chain_core.CommandContext) -> None:
        self.ctx = ctx
        self._git_no_lazy_fetch_qualification: (
            engine._GitNoLazyFetchQualification | None
        ) = None

    @staticmethod
    def _final_mode_unavailable(
        state: Mapping[str, Any], observed: str
    ) -> Refusal:
        return chain_core._merge_refusal(
            V2ReasonCode.REBASE_LOCK_UNAVAILABLE,
            "forge: merge finalize refused — final intended HEAD mode is unavailable",
            expected="a complete bounded read of the candidate .forge-manifest blob",
            observed=observed,
            remediation=f"forge merge recover --chain-id {state['chain_id']}",
            chain=state,
        )

    def _prepare_git_no_lazy_fetch_qualification(
        self, state: Mapping[str, Any]
    ) -> None:
        """Qualify and rebind Git before this invocation publishes its lock."""

        chain_core._require_merge_integration_control("final-intended-head-mode")
        self._git_no_lazy_fetch_qualification = None
        worktree = Path(str(state["worktree"]["path"]))
        try:
            qualification = engine._qualify_git_no_lazy_fetch(
                worktree, verbose=self.ctx.options.verbose
            )
            engine._require_git_no_lazy_fetch_qualification(
                qualification, worktree, engine._merge_scope_environment()
            )
        except OSError as exc:
            raise self._final_mode_unavailable(state, str(exc)) from exc
        self._git_no_lazy_fetch_qualification = qualification

    def _prepare_bootstrap_git_no_lazy_fetch_qualification(
        self,
        admission: engine.MergeAdmission,
        *,
        verb: str,
    ) -> None:
        """Qualify the exact Git selected by the composite before locking."""

        chain_core._require_merge_integration_control("composite-bootstrap-streaming")
        self._git_no_lazy_fetch_qualification = None
        try:
            qualification = engine._qualify_git_no_lazy_fetch(
                admission.worktree,
                verbose=self.ctx.options.verbose,
            )
            engine._require_git_no_lazy_fetch_qualification(
                qualification,
                admission.worktree,
                engine._merge_scope_environment(),
            )
        except OSError as exc:
            run_bound = admission.run_task is not None
            raise chain_core._merge_refusal(
                (
                    V2ReasonCode.RUN_TASK_BINDING_INVALID
                    if run_bound
                    else V2ReasonCode.FETCH_FAILED
                ),
                (
                    f"forge: {verb} refused — run/task scope derivation is invalid"
                    if run_bound
                    else f"forge: {verb} refused — fixed target fetch failed"
                ),
                expected="Git with proven GIT_NO_LAZY_FETCH support",
                observed=str(exc),
            ) from exc
        self._git_no_lazy_fetch_qualification = qualification

    @classmethod
    def _recover_can_reach_final_mode(
        cls,
        state: Mapping[str, Any],
        *,
        continue_rebase: bool,
        abort_rebase: bool,
    ) -> bool:
        """Select only recovery tuples that can invoke ``_run_epoch_push``.

        Release, bootstrap, foreign-state, and conflict reconciliation are
        observation-only in this invocation.  A raw rebase observation also
        either restores, conflicts, or creates a generation whose authority is
        cleared, so it cannot reach the final-mode read before parking.

        Explicit conflict modes never receive a push-capable qualification.
        The legacy router can ignore those flags outside the conflict state;
        withholding the token makes any such route fail closed at the final
        read rather than authorizing a push.
        """

        if continue_rebase or abort_rebase:
            return False
        integration = state.get("integration")
        claim = state.get("worktree", {}).get("claim")
        if (
            not isinstance(integration, Mapping)
            or not isinstance(claim, Mapping)
            or claim.get("status") != "owned"
            or integration.get("condition")
            in {"foreign-git-state", "lock-release-failed"}
            or integration.get("primary_condition") != "none"
            or engine._merge_inactive(state)
            or not cls._current_merge_authority(state)
        ):
            return False
        state_name = state.get("state")
        plan = integration.get("epoch")
        gate_plan = plan.get("gate_plan") if isinstance(plan, Mapping) else None
        if state_name == "pushing":
            push = integration.get("push")
            result = push.get("result") if isinstance(push, Mapping) else None
            return bool(
                chain_core._merge_old_tip_all_false(state)
                and isinstance(push, Mapping)
                and (result is None or isinstance(result, Mapping))
                and isinstance(gate_plan, Mapping)
                and gate_plan.get("status") == "sealed"
                and type(gate_plan.get("cursor")) is int
                and isinstance(gate_plan.get("suite"), list)
                and gate_plan["cursor"] == len(gate_plan["suite"])
            )
        if state_name == "reverification_failed":
            return True
        if state_name == "reverifying":
            return bool(
                isinstance(gate_plan, Mapping)
                and gate_plan.get("status") == "sealed"
            )
        if state_name == "authorized":
            return integration.get("condition") in {
                "fetch-failed",
                "remote-moved",
                "non-fast-forward",
            }
        if state_name != "rebasing":
            return False
        intent = integration.get("intent")
        if (
            isinstance(intent, Mapping)
            and intent.get("schema") == chain_core._MERGE_CANDIDATE_OBSERVATION_SCHEMA
            and isinstance(intent.get("source_intent"), Mapping)
        ):
            intent = intent["source_intent"]
        if isinstance(intent, Mapping) and intent.get("schema") == (
            chain_core._EPOCH_FETCH_OBSERVATION_SCHEMA
        ):
            return chain_core._epoch_fetch_observation_passed(intent)
        if isinstance(intent, Mapping) and intent.get("schema") == (
            "forge-epoch-ancestry-intent/1"
        ):
            phase = intent.get("phase")
            return bool(
                phase == "intent"
                or phase == "result"
                and intent.get("child_result", {}).get("contained") is True
            )
        if isinstance(gate_plan, Mapping) and gate_plan.get("status") == "sealed":
            return True
        if not isinstance(intent, Mapping):
            return intent is None
        if intent.get("operation") in {"rebase", "rebase-result"}:
            return False
        if (
            intent.get("operation") == "continue"
            and isinstance(intent.get("phase"), str)
            and str(intent["phase"]).startswith("forge-conflict-observation:")
        ):
            return False
        if (
            intent.get("operation") == "fetch-result"
            and intent.get("result") == "success"
        ):
            return False
        return intent.get("operation") == "fetch"

    @property
    def store(self) -> chain_core.MergeChainStore:
        if not isinstance(self.ctx.store, chain_core.MergeChainStore):
            raise FrozenError(
                "merge routing lacks the merge-family store",
                chain_id=self.ctx.options.chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        return self.ctx.store

    def _load(self) -> dict[str, Any]:
        if self.ctx.options.run_id is not None:
            raise chain_core._merge_refusal(
                V2ReasonCode.RUN_TASK_BINDING_INVALID,
                "forge: merge transition refused — later verbs inherit the immutable run/task binding",
                expected="no --run-id or --task after merge start",
                observed=self.ctx.options.run_id,
                remediation="retry with only the recorded --chain-id",
            )
        chain_id = self.ctx.options.chain_id
        if chain_id is None:
            raise Refusal(
                ReasonCode.STATE_PRECONDITION,
                "forge: merge shared verb refused — explicit --chain-id is required",
                remediation="forge status --chain-id <id>",
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        state = self.store.load(chain_id)
        if state.get("journal_outbox") is not None:
            state = self.store.recover_pending_outbox(chain_id)
        return state

    def _read_only_recovery_flag_state(self) -> dict[str, Any]:
        """Read replay truth without repairing bytes before a loud-flag refusal."""

        if self.ctx.options.run_id is not None:
            raise chain_core._merge_refusal(
                V2ReasonCode.RUN_TASK_BINDING_INVALID,
                "forge: merge transition refused — later verbs inherit the immutable run/task binding",
                expected="no --run-id or --task after merge start",
                observed=self.ctx.options.run_id,
                remediation="retry with only the recorded --chain-id",
            )
        chain_id = self.ctx.options.chain_id
        if chain_id is None:
            raise Refusal(
                ReasonCode.STATE_PRECONDITION,
                "forge: merge shared verb refused — explicit --chain-id is required",
                remediation="forge status --chain-id <id>",
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        self.store._validate_id(chain_id)
        if self.store.chain_family(chain_id) != "merge":
            raise FrozenError(
                "merge store refused a commit-family chain",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        with self.store.event_lock(chain_id):
            replay = self.store._read_replay_locked(chain_id)
            return self.store._resolve_replayed_projection(replay)

    def _halt(self, state: Mapping[str, Any]) -> None:
        chain_core._require_merge_adapter_control("halt")
        worktree = state.get("worktree")
        candidate_root = (
            Path(str(worktree["path"]))
            if isinstance(worktree, Mapping)
            and isinstance(worktree.get("path"), str)
            and Path(str(worktree["path"])).exists()
            else self.ctx.repo.root
        )
        engine._run_halt(
            self.ctx,
            state,
            scope="merge",
            cwd=candidate_root,
        )

    def _record_common_release_failure(
        self, chain_id: str, failure: chain_core.CommonLockReleaseFailure
    ) -> dict[str, Any] | None:
        """Preserve durable primary truth before exposing a release refusal."""

        try:
            current = self.store.load(chain_id)
        except (FrozenError, OSError, Refusal):
            return None
        integration = current.get("integration")
        if not isinstance(integration, dict):
            return None
        if integration.get("condition") == "lock-release-failed":
            return current
        updated = copy.deepcopy(integration)
        updated.update(
            {
                "condition": "lock-release-failed",
                "primary_condition": integration.get("condition", "none"),
            }
        )
        generation = current.get("candidate")
        recorded = self.store.transition(
            current,
            "lock_release_result",
            {"delta": {"integration": updated}},
            generation_digest=(
                str(generation["generation_digest"])
                if isinstance(generation, Mapping)
                else None
            ),
            at=chain_core.iso_z(),
        )
        failure.chain = recorded
        failure.remediation = f"forge merge recover --chain-id {chain_id}"
        failure.next_required_step = failure.remediation
        return recorded

    @contextlib.contextmanager
    def _recording_common_lock(
        self,
        common_dir: Path,
        *,
        chain_id: str,
        operation: str,
    ) -> Iterable[chain_core.CommonRebaseLock]:
        def event_intent(event: Mapping[str, Any]) -> Mapping[str, Any] | None:
            payload = event.get("payload")
            delta = payload.get("delta") if isinstance(payload, Mapping) else None
            integration = (
                delta.get("integration") if isinstance(delta, Mapping) else None
            )
            intent = (
                integration.get("intent")
                if isinstance(integration, Mapping)
                else None
            )
            return intent if isinstance(intent, Mapping) else None

        def carries_fence_digest(value: object, digest: str) -> bool:
            if isinstance(value, Mapping):
                if value.get("inflight_digest") == digest or value.get(
                    "fence_digest"
                ) == digest:
                    return True
                return any(
                    carries_fence_digest(member, digest)
                    for member in value.values()
                )
            if isinstance(value, list):
                return any(carries_fence_digest(member, digest) for member in value)
            return False

        def lifecycle_classification(
            state: Mapping[str, Any],
            replay: chain_core.MergeReplayResult,
            fence: chain_core.PublishedLockRecord,
        ) -> str:
            operation_name = str(fence.record["operation"])
            intent_digest = str(fence.record["intent_digest"])
            events = [
                event for event in replay.events if isinstance(event, Mapping)
            ]
            by_digest = {
                str(event.get("digest")): event
                for event in events
                if chain_core.SHA256_RE.fullmatch(str(event.get("digest", ""))) is not None
            }
            attributed = by_digest.get(intent_digest)
            cleanup_intent = chain_core._recovery_cleanup_intent(attributed)
            if isinstance(cleanup_intent, Mapping):
                result_persisted = any(
                    chain_core._recovery_cleanup_result_matches(
                        event,
                        state,
                        cleanup_intent,
                        intent_digest=intent_digest,
                        fence_digest=fence.digest,
                        fence_operation=operation_name,
                    )
                    for event in events
                )
            else:
                result_persisted = any(
                    carries_fence_digest(event.get("payload"), fence.digest)
                    for event in events
                )

            if operation_name in {"fetch", "tip-resolution"}:
                if attributed is None or attributed.get("event") != "fetch_intent":
                    raise FrozenError(
                        "reserved fetch fence diverges from chain lifecycle",
                        chain_id=chain_id,
                        schema=REVISION9_OUTPUT_SCHEMA,
                    )
                attributed_payload = attributed.get("payload")
                if not isinstance(attributed_payload, Mapping):
                    raise FrozenError(
                        "reserved fetch intent payload is malformed",
                        chain_id=chain_id,
                        schema=REVISION9_OUTPUT_SCHEMA,
                    )
                if attributed.get("generation_digest") is None:
                    request = attributed_payload.get("scope_request")
                    if request is not None and not isinstance(request, Mapping):
                        raise FrozenError(
                            "reserved bootstrap scope request is malformed",
                            chain_id=chain_id,
                            schema=REVISION9_OUTPUT_SCHEMA,
                        )
                    classification_state = copy.deepcopy(dict(state))
                    classification_integration = copy.deepcopy(
                        classification_state.get("integration")
                    )
                    if not isinstance(classification_integration, dict):
                        raise FrozenError(
                            "reserved bootstrap integration is malformed",
                            chain_id=chain_id,
                            schema=REVISION9_OUTPUT_SCHEMA,
                        )
                    classification_integration["intent"] = {
                        "operation": "fetch",
                        **copy.deepcopy(dict(attributed_payload)),
                    }
                    classification_state["integration"] = classification_integration
                    inspection = engine._classify_merge_scope_binding(
                        self.store,
                        classification_state,
                        fetch_intent_digest=intent_digest,
                        scope_request=(
                            request if isinstance(request, Mapping) else None
                        ),
                        fence=fence,
                    )
                    result_events = [
                        event
                        for event in events
                        if event.get("event") == "fetch_result"
                        and event.get("previous_digest") == intent_digest
                    ]
                    if not result_events:
                        current_intent = state.get("integration", {}).get("intent")
                        if (
                            state.get("state") != "classifying"
                            or not isinstance(current_intent, Mapping)
                            or current_intent.get("operation") != "fetch"
                        ):
                            raise FrozenError(
                                "reserved bootstrap fence lacks its pending lifecycle",
                                chain_id=chain_id,
                                schema=REVISION9_OUTPUT_SCHEMA,
                            )
                    elif len(result_events) == 1:
                        copied = result_events[0].get("payload", {}).get(
                            "scope_fetch_binding"
                        )
                        current_intent = state.get("integration", {}).get("intent")
                        if (
                            not isinstance(current_intent, Mapping)
                            or current_intent.get("operation") != "fetch-result"
                            or (copied is None and inspection.topology != "absent")
                            or (
                                isinstance(copied, Mapping)
                                and (
                                    inspection.topology != "canonical-one-link"
                                    or inspection.canonical is None
                                    or inspection.canonical.record != copied
                                )
                            )
                            or (
                                copied is not None
                                and not isinstance(copied, Mapping)
                            )
                        ):
                            raise FrozenError(
                                "reserved bootstrap result diverges from its sidecar",
                                chain_id=chain_id,
                                schema=REVISION9_OUTPUT_SCHEMA,
                            )
                    else:
                        raise FrozenError(
                            "reserved bootstrap fence has multiple lifecycle results",
                            chain_id=chain_id,
                            schema=REVISION9_OUTPUT_SCHEMA,
                        )
                return (
                    "fetch-result-persisted"
                    if result_persisted
                    else "fetch-intent-pending"
                )

            if operation_name == "gate":
                gate_result = any(
                    event.get("event") == "gate_recorded"
                    and carries_fence_digest(event.get("payload"), fence.digest)
                    and carries_fence_digest(event.get("payload"), intent_digest)
                    for event in events
                )
                if not gate_result:
                    integration = state.get("integration")
                    epoch = (
                        integration.get("epoch")
                        if isinstance(integration, Mapping)
                        else None
                    )
                    plan = epoch.get("gate_plan") if isinstance(epoch, Mapping) else None
                    if not isinstance(plan, Mapping) or plan.get("status") != "sealed":
                        raise FrozenError(
                            "reserved gate fence lacks a sealed cursor",
                            chain_id=chain_id,
                            schema=REVISION9_OUTPUT_SCHEMA,
                        )
                    cursor = plan.get("cursor")
                    suite = plan.get("suite")
                    if (
                        not chain_core._valid_nonnegative_int(cursor)
                        or not isinstance(suite, list)
                        or int(cursor) >= len(suite)
                        or not isinstance(suite[int(cursor)], Mapping)
                    ):
                        raise FrozenError(
                            "reserved gate fence cursor is malformed",
                            chain_id=chain_id,
                            schema=REVISION9_OUTPUT_SCHEMA,
                        )
                    authorizer = (
                        str(plan.get("seal_event_digest"))
                        if int(cursor) == 0
                        else next(
                            (
                                str(event.get("digest"))
                                for event in reversed(events)
                                if event.get("event") == "gate_recorded"
                            ),
                            "",
                        )
                    )
                    member = suite[int(cursor)]
                    expected = chain_core.merge_gate_intent_digest(
                        chain_id=chain_id,
                        epoch_intent_digest=str(epoch.get("intent_digest")),
                        seal_event_digest=str(plan.get("seal_event_digest")),
                        generation_digest=str(plan.get("generation_digest")),
                        policy_digest=str(plan.get("policy_digest")),
                        suite_digest=str(plan.get("suite_digest")),
                        cursor=int(cursor),
                        kind=str(member.get("kind")),
                        gate_id=str(member.get("id")),
                        authorizing_event_digest=authorizer,
                    )
                    if expected != intent_digest:
                        raise FrozenError(
                            "reserved gate fence diverges from the sealed cursor",
                            chain_id=chain_id,
                            schema=REVISION9_OUTPUT_SCHEMA,
                        )
                return "gate-result-persisted" if gate_result else "gate-intent-pending"

            if operation_name == "remote-observation":
                matched = False
                for event in events:
                    intent = event_intent(event)
                    if not isinstance(intent, Mapping):
                        continue
                    base = {
                        name: copy.deepcopy(intent.get(name))
                        for name in (
                            "schema",
                            "transaction",
                            "chain_id",
                            "attempt_identity",
                            "phase",
                            "push_intent_digest",
                        )
                    }
                    base["schema"] = "forge-remote-observation-intent/1"
                    if (
                        base.get("transaction") == "merge"
                        and base.get("chain_id") == chain_id
                        and base.get("phase") in {"final-prepush", "post-push"}
                        and sha256_bytes(chain_core.canonical_bytes(base)) == intent_digest
                    ):
                        matched = True
                        break
                if (
                    not matched
                    and attributed is not None
                    and attributed.get("event") == "cleanup_intent"
                ):
                    attributed_payload = attributed.get("payload")
                    attributed_delta = (
                        attributed_payload.get("delta")
                        if isinstance(attributed_payload, Mapping)
                        else None
                    )
                    attributed_cleanup = (
                        attributed_delta.get("cleanup")
                        if isinstance(attributed_delta, Mapping)
                        else None
                    )
                    cleanup_intent = (
                        attributed_cleanup.get("intent")
                        if isinstance(attributed_cleanup, Mapping)
                        else None
                    )
                    matched = bool(
                        isinstance(cleanup_intent, Mapping)
                        and cleanup_intent.get("schema")
                        == chain_core._MERGE_CLEANUP_INTENT_SCHEMA
                        and cleanup_intent.get("fence_operation")
                        == "remote-observation"
                        and chain_core._merge_cleanup_intent_valid(cleanup_intent, state)
                    )
                if not matched:
                    raise FrozenError(
                        "reserved remote-observation fence lacks its exact phase intent",
                        chain_id=chain_id,
                        schema=REVISION9_OUTPUT_SCHEMA,
                    )
            elif operation_name in {"rebase", "continue", "abort"}:
                expected_intents = {
                    "rebase": {"rebase"},
                    "continue": {"continue"},
                    "abort": {"abort"},
                }[operation_name]
                intent = event_intent(attributed) if attributed is not None else None
                if (
                    attributed is None
                    or attributed.get("event")
                    not in {"rebase_intent", "condition_recorded"}
                    or not isinstance(intent, Mapping)
                    or intent.get("operation") not in expected_intents
                ):
                    raise FrozenError(
                        f"reserved {operation_name} fence lacks its exact intent",
                        chain_id=chain_id,
                        schema=REVISION9_OUTPUT_SCHEMA,
                    )
            elif operation_name == "push":
                if attributed is None or attributed.get("event") != "push_intent":
                    raise FrozenError(
                        "reserved push fence lacks its exact intent",
                        chain_id=chain_id,
                        schema=REVISION9_OUTPUT_SCHEMA,
                    )
            elif operation_name in {"worktree-remove", "branch-delete"}:
                cleanup_intent = chain_core._recovery_cleanup_intent(attributed)
                if (
                    attributed is None
                    or attributed.get("event") != "cleanup_intent"
                    or not isinstance(cleanup_intent, Mapping)
                    or cleanup_intent.get("fence_operation") != operation_name
                    or not chain_core._merge_cleanup_intent_valid(cleanup_intent, state)
                ):
                    raise FrozenError(
                        f"reserved {operation_name} fence lacks its cleanup intent",
                        chain_id=chain_id,
                        schema=REVISION9_OUTPUT_SCHEMA,
                    )
            elif operation_name == "containment":
                cleanup_intent = chain_core._recovery_cleanup_intent(attributed)
                matched = bool(
                    attributed is not None
                    and (
                        attributed.get("event")
                        in {"condition_recorded", "fetch_result"}
                        or attributed.get("event") == "cleanup_intent"
                        and isinstance(cleanup_intent, Mapping)
                        and cleanup_intent.get("fence_operation")
                        == operation_name
                        and chain_core._merge_cleanup_intent_valid(
                            cleanup_intent, state
                        )
                    )
                )
                if not matched:
                    matched = any(
                        isinstance(event_intent(event), Mapping)
                        and sha256_bytes(
                            chain_core.canonical_bytes(dict(event_intent(event) or {}))
                        )
                        == intent_digest
                        for event in events
                    )
                if not matched:
                    raise FrozenError(
                        "reserved containment fence lacks its exact read intent",
                        chain_id=chain_id,
                        schema=REVISION9_OUTPUT_SCHEMA,
                    )
            else:
                raise FrozenError(
                    "reserved merge fence operation is not recoverable",
                    chain_id=chain_id,
                    observed=operation_name,
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            return (
                f"{operation_name}-result-persisted"
                if result_persisted
                else f"{operation_name}-intent-pending"
            )

        def classify_reserved_fence(
            reservation: chain_core.RecoveryReservation,
            fence: chain_core.PublishedLockRecord | None,
        ) -> dict[str, Any]:
            """Classify and durably record death while reservation-held."""

            chain_core._require_common_lock_control(
                "reservation-held-lifecycle-classification"
            )
            selected_chain = reservation.affected_merge_chain()
            if fence is not None and (
                fence.record.get("owner_kind") != "merge"
                or fence.record.get("chain_id") != selected_chain
            ):
                raise FrozenError(
                    "reserved merge fence does not belong to the requested chain",
                    chain_id=selected_chain,
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            reservation.assert_current(
                "merge lifecycle recovery before chain lease"
            )
            with chain_core.acquire_chain_lease(
                self.store.root,
                chain_id=selected_chain,
                session=self.store._session(None),
                exclusion=reservation,
                timeout=reservation.remaining_timeout(
                    "reservation-held chain lease acquisition"
                ),
                clock=reservation.clock,
                sleeper=reservation.sleeper,
            ) as lease:
                state = self.store.load_locked(selected_chain, lease=lease)
                with self.store.event_lock(
                    selected_chain,
                    deadline=reservation.deadline,
                    clock=reservation.clock,
                    sleeper=reservation.sleeper,
                ):
                    replay = self.store._read_replay_locked(selected_chain)
                if (
                    fence is None
                    and engine._merge_inactive(state)
                    and engine._merge_inactive_epoch_has_no_started_child(
                        state, replay.events
                    )
                ):
                    raise chain_core._merge_refusal(
                        V2ReasonCode.STATE_PRECONDITION,
                        "forge: merge recover refused — inactive epoch has no started child",
                        expected="status or safe abort after inactivity",
                        observed=str(state["state"]),
                        remediation=f"forge status --chain-id {selected_chain}",
                        chain=state,
                    )
                if fence is None:
                    classification = "owner-death-only"
                else:
                    # Bootstrap recovery additionally authenticates the
                    # surviving sidecar topology.  Its return value is not
                    # authoritative: all persisted lifecycle labels come from
                    # the same pure prefix-history classifier used by replay.
                    if fence.record.get("operation") in {
                        "fetch",
                        "tip-resolution",
                    }:
                        lifecycle_classification(state, replay, fence)
                    classification = chain_core._classify_merge_recovery_lifecycle(
                        state,
                        replay.events,
                        fence_record=fence.record,
                        fence_digest=fence.digest,
                    )
                    if classification is None:
                        raise FrozenError(
                            "reserved merge fence lifecycle is not uniquely classifiable",
                            chain_id=selected_chain,
                            schema=REVISION9_OUTPUT_SCHEMA,
                        )
                recorded_at = chain_core.iso_z()
                unsigned = {
                    "schema": "forge-merge-fence-recovery-proof/1",
                    "chain_id": selected_chain,
                    "reservation": reservation.identity.evidence(),
                    "fence": fence.evidence() if fence is not None else None,
                    "lifecycle": {
                        "operation": (
                            fence.record.get("operation")
                            if fence is not None
                            else None
                        ),
                        "intent_digest": (
                            fence.record.get("intent_digest")
                            if fence is not None
                            else None
                        ),
                        "classification": classification,
                        "state_digest": sha256_bytes(chain_core.canonical_bytes(state)),
                        "tail_digest": replay.tail_digest,
                    },
                    "recorded_at": recorded_at,
                }
                proof = {
                    **unsigned,
                    "digest": sha256_bytes(chain_core.canonical_bytes(unsigned)),
                }
                current = self._epoch_transition(
                    state,
                    lease,
                    "condition_recorded",
                    {"delta": {}, "recovery_proof": proof},
                    at=recorded_at,
                )
                reservation.assert_current(
                    "merge lifecycle recovery after proof append"
                )
                with self.store.event_lock(
                    selected_chain,
                    deadline=reservation.deadline,
                    clock=reservation.clock,
                    sleeper=reservation.sleeper,
                ):
                    retained = self.store._read_replay_locked(selected_chain)
                tail_payload = retained.events[-1].get("payload")
                if (
                    current != retained.state
                    or not isinstance(tail_payload, Mapping)
                    or tail_payload.get("recovery_proof") != proof
                ):
                    raise FrozenError(
                        "merge fence recovery proof was not durably retained",
                        chain_id=selected_chain,
                        schema=REVISION9_OUTPUT_SCHEMA,
                    )
                proof_event_digest = str(retained.events[-1]["digest"])
            reservation.assert_current(
                "merge lifecycle recovery receipt"
            )
            return {
                "schema": "forge-merge-fence-recovery-receipt/1",
                "chain_id": selected_chain,
                "chain_store": str(self.store.root),
                "reservation_digest": reservation.identity.digest,
                "fence_digest": fence.digest if fence is not None else None,
                "proof_digest": str(proof["digest"]),
                "event_digest": proof_event_digest,
            }

        def unexpected_split_recovery_proof(_proof: dict[str, Any]) -> None:
            raise OSError(
                "reservation lifecycle and death proof were not persisted atomically"
            )

        lock = chain_core.acquire_common_lock(
            common_dir,
            owner_kind="merge",
            chain_id=chain_id,
            operation=operation,
            no_transaction_record=operation != "recover",
            recovery_recorder=(
                unexpected_split_recovery_proof
                if operation == "recover"
                else None
            ),
            recovery_classifier=(
                classify_reserved_fence if operation == "recover" else None
            ),
        )
        try:
            with lock as acquired:
                yield acquired
        except chain_core.CommonLockReleaseFailure as exc:
            self._record_common_release_failure(chain_id, exc)
            raise

    def _candidate_observation_transition(
        self,
        state: dict[str, Any],
        lease: chain_core.ChainLease | None,
        integration: Mapping[str, Any],
    ) -> dict[str, Any]:
        payload = {"delta": {"integration": copy.deepcopy(dict(integration))}}
        generation = state.get("candidate")
        generation_digest = (
            str(generation["generation_digest"])
            if isinstance(generation, Mapping)
            else None
        )
        if lease is not None:
            return self._epoch_transition(
                state,
                lease,
                "condition_recorded",
                payload,
                generation_digest=generation_digest,
            )
        return self.store.transition(
            state,
            "condition_recorded",
            payload,
            generation_digest=generation_digest,
            at=chain_core.iso_z(),
        )

    def _restore_candidate_observation_intent_locked(
        self,
        state: dict[str, Any],
        lease: chain_core.ChainLease | None,
    ) -> tuple[dict[str, Any], object, bool]:
        integration = state.get("integration")
        intent = integration.get("intent") if isinstance(integration, Mapping) else None
        if not (
            isinstance(intent, Mapping)
            and intent.get("schema") == chain_core._MERGE_CANDIDATE_OBSERVATION_SCHEMA
        ):
            return state, copy.deepcopy(intent), True
        if not chain_core._merge_candidate_observation_record_valid(state, intent):
            return state, None, False
        restored = copy.deepcopy(dict(integration))
        source_intent = copy.deepcopy(intent.get("source_intent"))
        restored["intent"] = source_intent
        return (
            self._candidate_observation_transition(state, lease, restored),
            source_intent,
            True,
        )

    def _restore_bootstrap_fetch_observation_locked(
        self,
        state: dict[str, Any],
        lease: chain_core.ChainLease | None,
    ) -> tuple[dict[str, Any], bool]:
        integration = state.get("integration")
        intent = integration.get("intent") if isinstance(integration, Mapping) else None
        if not (
            isinstance(intent, Mapping)
            and intent.get("schema") == chain_core._BOOTSTRAP_FETCH_OBSERVATION_SCHEMA
        ):
            return state, True
        if not chain_core._bootstrap_fetch_observation_record_valid(state, intent):
            return state, False
        restored = copy.deepcopy(dict(integration))
        restored["intent"] = copy.deepcopy(intent.get("source_intent"))
        return self._candidate_observation_transition(state, lease, restored), True

    def _run_candidate_observation_locked(
        self,
        state: dict[str, Any],
        lock: chain_core.CommonRebaseLock,
        lease: chain_core.ChainLease | None,
        *,
        verb: str,
        remote_tip: str,
        expected_head: str,
        classify: bool,
        declared_tier: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Run the closed candidate proof as separately fenced durable reads."""

        chain_core._require_merge_integration_control("observation-first-recovery")
        state, source_intent, restored = (
            self._restore_candidate_observation_intent_locked(state, lease)
        )
        if not restored:
            raise FrozenError(
                "merge candidate observation intent is malformed",
                chain_id=str(state.get("chain_id", "")) or None,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        specs = chain_core._merge_candidate_observation_step_specs(
            state,
            remote_tip=remote_tip,
            expected_head=expected_head,
            classify=classify,
            declared_tier=declared_tier,
        )
        binding = chain_core._merge_candidate_observation_binding(
            state,
            source_intent,
            verb=verb,
            remote_tip=remote_tip,
            expected_head=expected_head,
            classify=classify,
            declared_tier=declared_tier,
        )
        if specs is None or binding is None:
            raise FrozenError(
                "merge candidate observation request is malformed",
                chain_id=str(state.get("chain_id", "")) or None,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        records: list[dict[str, Any]] = []
        environment = engine._merge_scope_environment()
        environment.pop("FORGE_SESSION_PID", None)

        def restore_source() -> None:
            nonlocal state
            integration = copy.deepcopy(state["integration"])
            integration["intent"] = copy.deepcopy(source_intent)
            state = self._candidate_observation_transition(
                state, lease, integration
            )

        for step, cwd, argv in specs:
            started_at = chain_core.iso_z()
            generation = state.get("candidate")
            record: dict[str, Any] = {
                "schema": chain_core._MERGE_CANDIDATE_OBSERVATION_SCHEMA,
                "chain_id": state["chain_id"],
                "generation_digest": (
                    generation.get("generation_digest")
                    if isinstance(generation, Mapping)
                    else None
                ),
                "source_intent": copy.deepcopy(source_intent),
                "verb": verb,
                "remote_tip": remote_tip,
                "expected_head": expected_head,
                "classify": classify,
                "declared_tier": declared_tier,
                "observation_binding": binding,
                "stage": "intent",
                "step": step,
                "cwd": str(cwd),
                "argv": list(argv),
                "started_at": started_at,
            }
            integration = copy.deepcopy(state["integration"])
            integration["intent"] = copy.deepcopy(record)
            state = self._candidate_observation_transition(
                state, lease, integration
            )
            intent_digest = self._tail_event_digest(
                state, "condition_recorded"
            )

            def intent_current(expected: Mapping[str, Any] = record) -> bool:
                try:
                    current = (
                        self.store.load_locked(
                            str(state["chain_id"]), lease=lease
                        )
                        if lease is not None
                        # The common lock and journal-outer transaction make
                        # this invocation's just-persisted projection the
                        # sole mutable value.  Reloading here can observe its
                        # own not-yet-drained outbox descriptor.
                        else state
                    )
                except (FrozenError, OSError, Refusal):
                    return False
                return bool(
                    current.get("integration", {}).get("intent") == expected
                    and engine._merge_event_digest(
                        self.store,
                        str(current["chain_id"]),
                        "condition_recorded",
                    )
                    == intent_digest
                )

            def persist_observation(result: chain_core.FencedProcessResult) -> None:
                nonlocal state
                durable = {
                    **copy.deepcopy(record),
                    "stage": "result",
                    "child_result": {
                        "authorized": result.authorized,
                        "exit": result.returncode,
                        "inflight_digest": result.fence_digest,
                        "output_digest": result.output_digest,
                        "stored_output_digest": sha256_bytes(result.output),
                        "output_b64": base64.b64encode(result.output).decode(
                            "ascii"
                        ),
                        "launch_failed": result.launch_failed,
                        "timed_out": result.timed_out,
                        "output_limit_exceeded": result.output_limit,
                        "group_survived": result.group_survived,
                    },
                    "recorded_at": chain_core.iso_z(),
                }
                updated = copy.deepcopy(state["integration"])
                updated["intent"] = durable
                state = self._candidate_observation_transition(
                    state, lease, updated
                )

            result = chain_core.run_fenced_command(
                lock,
                operation="containment",
                intent_digest=intent_digest,
                intent_validator=intent_current,
                argv=argv,
                cwd=cwd,
                persist_result=persist_observation,
                env=environment,
                timeout=runtime.COMMAND_TIMEOUT_SECONDS,
                cap=runtime.OUTPUT_CAP_BYTES,
                verbose=self.ctx.options.verbose,
            )
            durable = state.get("integration", {}).get("intent")
            complete = bool(
                isinstance(durable, Mapping)
                and chain_core._merge_candidate_observation_record_valid(state, durable)
                and durable.get("stage") == "result"
                and durable.get("step") == step
                and durable.get("observation_binding") == binding
                and durable.get("child_result", {}).get("authorized") is True
                and durable.get("child_result", {}).get("exit") == 0
                and durable.get("child_result", {}).get("launch_failed") is False
                and durable.get("child_result", {}).get("timed_out") is False
                and durable.get("child_result", {}).get("output_limit_exceeded")
                is False
                and durable.get("child_result", {}).get("group_survived") is False
                and durable.get("child_result", {}).get("inflight_digest")
                == result.fence_digest
                and durable.get("child_result", {}).get("output_digest")
                == result.output_digest
            )
            if not complete:
                restore_source()
                raise chain_core._merge_refusal(
                    V2ReasonCode.EVIDENCE_INCOMPLETE,
                    f"forge: {verb} refused — candidate observation did not complete",
                    expected=f"one complete exit-0 {step} observation",
                    observed=(
                        f"exit={result.returncode}, launch={result.launch_failed}, "
                        f"timeout={result.timed_out}, output_limit={result.output_limit}, "
                        f"group_survived={result.group_survived}"
                    ),
                    chain=state,
                )
            records.append(copy.deepcopy(dict(durable)))
            restore_source()

        evidence = chain_core._merge_candidate_observation_evidence(state, records)
        if evidence is None:
            raise FrozenError(
                "merge candidate observation evidence is incomplete",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        return state, evidence

    def start(
        self,
        worktree: str,
        declared_tier: str | None = None,
        *,
        task: str | None = None,
    ) -> engine.MergeAdmission:
        """Expose dormant read-only admission without creating a chain."""

        return prepare_merge_admission(
            self.ctx,
            worktree,
            declared_tier,
            task=task,
        )

    def bind_candidate(
        self,
        admission: engine.MergeAdmission,
        remote_tip: str,
        *,
        generation: int = 1,
    ) -> engine.MergeCandidateGeneration:
        return engine.bind_merge_candidate_generation(
            self.ctx,
            admission,
            remote_tip,
            generation=generation,
        )

    def _preflight_lifecycle(
        self,
        state: dict[str, Any],
        verb: str,
        *,
        persist_missing: bool = True,
    ) -> dict[str, Any]:
        """Apply FR-232 priority rows before an ordinary scalar-state row."""

        engine._require_merge_lifecycle_control("admission-priority")
        claim = state.get("worktree", {}).get("claim")
        claim_status = claim.get("status") if isinstance(claim, Mapping) else None
        if claim_status == "unpublished":
            next_step = (
                f"forge merge abort --chain-id {state['chain_id']}"
                if engine._merge_unpublished_claim_absent(state, self.store)
                else f"forge merge recover --chain-id {state['chain_id']}"
            )
            raise chain_core._merge_refusal(
                V2ReasonCode.STATE_PRECONDITION,
                f"forge: {verb} refused — ownership publication requires recovery",
                expected="owned or terminal merge ownership",
                observed="unpublished",
                remediation=next_step,
                chain=state,
            )
        if claim_status in {"releasing", "released"} and state["state"] not in {
            "closed",
            "aborted",
        }:
            raise chain_core._merge_refusal(
                V2ReasonCode.STATE_PRECONDITION,
                f"forge: {verb} refused — ownership release completion is pending",
                expected="the cutoff-selected terminal event",
                observed=str(claim_status),
                remediation=f"forge merge recover --chain-id {state['chain_id']}",
                chain=state,
            )
        containment, _vector = chain_core._merge_containment(state)
        if containment == "current" and state["state"] != "pushed":
            raise chain_core._merge_refusal(
                V2ReasonCode.STATE_PRECONDITION,
                f"forge: {verb} refused — current intended HEAD containment requires recovery",
                expected="durable current-generation pushed truth",
                observed="current intended HEAD is contained",
                remediation=f"forge merge recover --chain-id {state['chain_id']}",
                chain=state,
            )
        if containment == "older":
            raise chain_core._merge_refusal(
                V2ReasonCode.STATE_PRECONDITION,
                f"forge: {verb} refused — older attempted HEAD containment requires recovery",
                expected="historical landing reconciliation before another transition",
                observed="only an older attempted HEAD is contained",
                remediation=f"forge merge recover --chain-id {state['chain_id']}",
                chain=state,
            )
        if engine._merge_inactive(state):
            raise chain_core._merge_refusal(
                V2ReasonCode.STATE_PRECONDITION,
                f"forge: {verb} refused — merge chain is inactive",
                expected="an active merge transition tuple",
                observed=str(state["inactive_after"]),
                remediation=f"forge status --chain-id {state['chain_id']}",
                chain=state,
            )
        worktree = Path(str(state.get("worktree", {}).get("path", "")))
        if not worktree.exists():
            current = state
            integration = state.get("integration")
            if (
                persist_missing
                and isinstance(integration, dict)
                and integration.get("condition") != "foreign-git-state"
            ):
                updated = copy.deepcopy(integration)
                updated["condition"] = "foreign-git-state"
                updated["primary_condition"] = "none"
                engine._reset_merge_nonmovement_counter(updated)
                generation = state.get("candidate")
                current = self.store.transition(
                    state,
                    "condition_recorded",
                    {"delta": {"integration": updated}},
                    generation_digest=(
                        str(generation["generation_digest"])
                        if isinstance(generation, Mapping)
                        else None
                    ),
                    at=chain_core.iso_z(),
                )
            raise chain_core._merge_refusal(
                V2ReasonCode.STATE_PRECONDITION,
                f"forge: {verb} refused — recorded worktree is missing",
                expected=str(worktree),
                observed="foreign-git-state",
                remediation=f"forge status --chain-id {state['chain_id']}",
                chain=current,
            )
        return state

    def _claim_slot(
        self,
        admission: engine.MergeAdmission,
    ) -> tuple[str, str, Path, str | None, str | None]:
        worktree_digest, name, path = engine._merge_claim_identity(
            self.store, admission.worktree_identity
        )
        try:
            existing = engine._read_merge_claim(self.store, name, path)
        except (OSError, ValueError) as exc:
            raise FrozenError(
                "merge ownership slot is malformed or unreadable",
                observed=f"{path}: {exc}",
                schema=REVISION9_OUTPUT_SCHEMA,
            ) from exc
        if existing is not None:
            prior_id = str(existing.record["chain_id"])
            try:
                prior = self.store.load(prior_id)
            except (FrozenError, Refusal) as exc:
                raise FrozenError(
                    "merge ownership slot names an unverifiable chain",
                    chain_id=prior_id,
                    observed=str(path),
                    schema=REVISION9_OUTPUT_SCHEMA,
                ) from exc
            claim = prior.get("worktree", {}).get("claim")
            publish_before_event = bool(
                isinstance(claim, Mapping)
                and claim.get("status") == "unpublished"
                and claim.get("path") == str(path)
                and claim.get("inode") is None
                and claim.get("digest") == existing.digest
            )
            exact = bool(
                isinstance(claim, Mapping)
                and claim.get("path") == str(path)
                and claim.get("inode") == existing.inode
                and claim.get("digest") == existing.digest
            )
            if not exact and not publish_before_event:
                raise FrozenError(
                    "merge ownership slot diverges from its named chain",
                    chain_id=prior_id,
                    observed=chain_core.canonical_bytes(existing.evidence()).decode("utf-8"),
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            if prior.get("state") not in {"closed", "aborted"}:
                raise chain_core._merge_refusal(
                    V2ReasonCode.LIVE_MERGE_CHAIN_EXISTS,
                    "forge: merge start refused — selected worktree already has a live merge owner",
                    expected="an unowned registered worktree",
                    observed=prior_id,
                    remediation=f"forge status --chain-id {prior_id}",
                    chain=prior,
                )
            if claim.get("status") != "released":
                raise FrozenError(
                    "terminal merge ownership projection is not released",
                    chain_id=prior_id,
                    observed=str(claim.get("status")),
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            engine._remove_merge_claim(self.store, prior)
        predecessor_id, predecessor_digest = engine._merge_released_predecessor(
            self.store, path, admission.worktree_identity
        )
        return worktree_digest, name, path, predecessor_id, predecessor_digest

    def _allocate_chain_id(self) -> str:
        for _attempt in range(32):
            chain_id = engine.chain_id_now()
            if (
                not self.store.state_path(chain_id).exists()
                and not self.store.events_path(chain_id).exists()
            ):
                return chain_id
        raise FrozenError(
            "unable to allocate a collision-free merge chain identifier",
            schema=REVISION9_OUTPUT_SCHEMA,
        )

    def _initial_merge_state(
        self,
        chain_id: str,
        admission: engine.MergeAdmission,
        claim_path: Path,
        *,
        at: str,
    ) -> dict[str, Any]:
        session = self.store._session(None)
        owner = {
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "session": session,
            "started_at": at,
        }
        binding = (
            copy.deepcopy(admission.run_task.binding)
            if admission.run_task is not None
            else None
        )
        return {
            "schema": "forge-merge-chain/1",
            "chain_id": chain_id,
            "kind": "merge",
            "state": "classifying",
            "created_at": at,
            "owner": owner,
            "run": binding["run_id"] if binding is not None else None,
            "repository": str(admission.repository),
            "worktree": {
                **copy.deepcopy(admission.worktree_identity),
                "claim": {
                    "status": "unpublished",
                    "path": str(claim_path),
                    "inode": None,
                    "digest": None,
                },
            },
            "branch": admission.branch,
            "target": copy.deepcopy(admission.target),
            "policy_source": {
                "commit": admission.policy.sha,
                "digest": admission.policy.digest,
            },
            "candidate": None,
            "tier": None,
            "steps": {},
            "review": {},
            "approval": {},
            "authorization": {},
            "integration": copy.deepcopy(engine._MERGE_INITIAL_INTEGRATION),
            "cleanup": {"condition": "none"},
            "run_binding": binding,
        }

    def _record_bootstrap_failure(
        self,
        state: dict[str, Any],
        operation_nonce: str,
        refusal: Refusal,
        *,
        attempt: int = 1,
    ) -> Refusal:
        integration = copy.deepcopy(state["integration"])
        integration.update(
            {
                "condition": "fetch-failed",
                "primary_condition": "none",
                "intent": {
                    "operation": "fetch-result",
                    "operation_nonce": operation_nonce,
                    "attempt": attempt,
                    "result": "failed",
                    "resolved_tip": None,
                },
            }
        )
        current = self.store.transition(
            state,
            "fetch_result",
            {
                "delta": {"integration": integration},
                "scope_fetch_binding": None,
                "scope_proof": None,
            },
            generation_digest=None,
            at=chain_core.iso_z(),
        )
        return chain_core._merge_refusal(
            refusal.reason_code,
            refusal.message,
            expected=refusal.expected,
            observed=refusal.observed,
            remediation=f"forge merge refresh --chain-id {state['chain_id']}",
            chain=current,
            evidence_refs=refusal.evidence_refs,
        )

    @staticmethod
    def _bootstrap_fetch_argv(
        admission: engine.MergeAdmission, remote_tip: str | None
    ) -> tuple[str, list[str]]:
        if remote_tip is not None:
            return (
                "tip-resolution",
                [
                    "git",
                    "--no-pager",
                    "-C",
                    str(admission.worktree),
                    "cat-file",
                    "-e",
                    f"{remote_tip}^{{commit}}",
                ],
            )
        return (
            "fetch",
            [
                "git",
                "--no-pager",
                "-C",
                str(admission.worktree),
                "fetch",
                "--no-tags",
                "--quiet",
                "origin",
                admission.target["destination_ref"],
            ],
        )

    @staticmethod
    def _resolved_fetch_tip(
        admission: engine.MergeAdmission, supplied: str | None
    ) -> str:
        if supplied is not None:
            return supplied
        fetch_head = Path(admission.worktree_identity["git_dir"]) / "FETCH_HEAD"
        try:
            raw = fetch_head.read_bytes()
        except OSError as exc:
            raise ValueError(f"FETCH_HEAD is unavailable: {exc}") from exc
        if len(raw) > chain_core.MERGE_SCOPE_BINDING_CAP_BYTES or not raw.endswith(b"\n"):
            raise ValueError("FETCH_HEAD is malformed")
        rows = raw.splitlines()
        if len(rows) != 1:
            raise ValueError("FETCH_HEAD does not identify one fixed target")
        raw_oid = rows[0].split(b"\t", 1)[0]
        try:
            oid = raw_oid.decode("ascii")
        except UnicodeDecodeError as exc:
            raise ValueError("FETCH_HEAD object ID is not ASCII") from exc
        if chain_core.COMMIT_RE.fullmatch(oid) is None:
            raise ValueError("FETCH_HEAD object ID is invalid")
        return oid

    def _recover_merge_bootstrap_scope_binding(
        self,
        state: Mapping[str, Any],
        admission: engine.MergeAdmission,
        *,
        fence: chain_core.PublishedLockRecord | None = None,
    ) -> dict[str, Any] | None:
        """Resume a crashed run-bound sidecar without resolving a tip again.

        ``None`` is the exact both-names-absent pre-publication result.  When
        common-lock recovery already cleared the dead fence, its complete
        identity is recovered from the immutable sidecar's
        ``retained_inflight`` member.
        """

        chain_core._require_merge_integration_control("scope-sidecar-recovery")
        fetch_intent_digest = engine._merge_event_digest(
            self.store, str(state["chain_id"]), "fetch_intent"
        )
        if fetch_intent_digest is None:
            raise FrozenError(
                "merge bootstrap fetch intent digest is unavailable",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        intent = state.get("integration", {}).get("intent")
        scope_request = (
            intent.get("scope_request") if isinstance(intent, Mapping) else None
        )
        expected_request = engine._merge_scope_request(admission)
        if (
            (scope_request is not None and not isinstance(scope_request, Mapping))
            or (
                dict(scope_request)
                if isinstance(scope_request, Mapping)
                else None
            )
            != expected_request
        ):
            raise FrozenError(
                "merge bootstrap scope request diverges from admission",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        selected_fence = fence or engine._discover_merge_scope_fence_from_sidecar(
            self.store,
            state,
            fetch_intent_digest=fetch_intent_digest,
        )
        if selected_fence is None:
            return None
        return engine._resume_merge_scope_binding(
            self.store,
            state,
            fetch_intent_digest=fetch_intent_digest,
            scope_request=scope_request,
            fence=selected_fence,
        )

    def _run_bootstrap_generation_composite(
        self,
        state: dict[str, Any],
        admission: engine.MergeAdmission,
        lock: chain_core.CommonRebaseLock,
        *,
        operation_nonce: str,
        attempt: int,
        remote_tip: str | None,
        generation_number: int,
        verb: str,
    ) -> tuple[dict[str, Any], engine.MergeBootstrapClassification]:
        """Run Revision-12's child and retain a post-lock classification input."""

        chain_core._require_merge_integration_control("composite-bootstrap-streaming")
        chain_core._require_merge_integration_control("post-fetch-scope-proof")
        fetch_intent_digest = engine._merge_event_digest(
            self.store, str(state["chain_id"]), "fetch_intent"
        )
        if fetch_intent_digest is None:
            raise FrozenError(
                "merge bootstrap fetch intent digest is unavailable",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        operation, fetch_argv = self._bootstrap_fetch_argv(admission, remote_tip)
        scope_request = engine._merge_scope_request(admission)
        holder: dict[str, Any] = {}

        def intent_current() -> bool:
            return (
                engine._merge_event_digest(
                    self.store, str(state["chain_id"]), "fetch_intent"
                )
                == fetch_intent_digest
            )

        def failed_result(
            binding: Mapping[str, Any] | None,
        ) -> None:
            nonlocal state
            integration = copy.deepcopy(state["integration"])
            integration.update(
                {
                    # A run-bound composite failure takes the established
                    # run-task-binding-invalid ordinary-abort edge; only the
                    # unbound pre-sidecar failure remains classifying with
                    # the durable fetch-failed condition.
                    "condition": (
                        "none"
                        if admission.run_task is not None
                        else "fetch-failed"
                    ),
                    "primary_condition": "none",
                    "intent": {
                        "operation": "fetch-result",
                        "operation_nonce": operation_nonce,
                        "attempt": attempt,
                        "result": "failed",
                        "resolved_tip": None,
                    },
                }
            )
            state = self.store.transition(
                state,
                "fetch_result",
                {
                    "delta": {"integration": integration},
                    "scope_fetch_binding": (
                        copy.deepcopy(dict(binding))
                        if isinstance(binding, Mapping)
                        else None
                    ),
                    "scope_proof": None,
                },
                generation_digest=(
                    str(state["candidate"]["generation_digest"])
                    if isinstance(state.get("candidate"), Mapping)
                    else None
                ),
                at=chain_core.iso_z(),
            )

        def materialize_success(
            binding: Mapping[str, Any],
            metadata: Mapping[str, Any],
            fixed_tip: str,
        ) -> tuple[dict[str, Any], engine.MergeScopeResult | None, object]:
            """Materialize the complete candidate while the child fence survives."""

            nonlocal state
            scope: engine.MergeScopeResult | None = None
            if admission.run_task is not None:
                scope_record = metadata.get("scope")
                changed = metadata.get("scope_changed_paths")
                if (
                    not isinstance(scope_record, Mapping)
                    or not chain_core._valid_sorted_unique_strings(changed)
                ):
                    raise FrozenError(
                        "composite bootstrap scope evidence is malformed",
                        chain_id=str(state["chain_id"]),
                        schema=REVISION9_OUTPUT_SCHEMA,
                    )
                _batch, _builders, journal = runtime._coordination_modules()
                snapshot = admission.run_task
                out_of_scope = tuple(
                    path
                    for path in changed
                    if not any(
                        journal.pathspec_contained(path, pattern)
                        for pattern in snapshot.task_files
                    )
                    or not any(
                        journal.pathspec_contained(path, pattern)
                        for pattern in snapshot.admitted_scope
                    )
                )
                scope = engine.MergeScopeResult(
                    argv=tuple(
                        chain_core._merge_scope_argv(
                            admission.worktree,
                            fixed_tip,
                            admission.candidate_head,
                        )
                    ),
                    command_digest=str(binding["command_digest"]),
                    environment_digest=str(binding["environment_digest"]),
                    output_digest=str(scope_record["output_digest"]),
                    changed_paths=tuple(changed),
                    out_of_scope_paths=out_of_scope,
                    result="exceeded" if out_of_scope else "contained",
                )
            candidate = engine._retain_or_advance_merge_candidate(
                admission,
                fixed_tip,
                prior_candidate=state.get("candidate"),
                generation=generation_number,
                diff_output_digest=str(binding["full_patch_output_digest"]),
            )
            proof = (
                engine._merge_scope_proof(
                    admission, candidate, scope, binding
                )
                if scope is not None
                else None
            )
            integration = copy.deepcopy(state["integration"])
            integration.update(
                {
                    "condition": "none",
                    "primary_condition": "none",
                    "intent": {
                        "operation": "fetch-result",
                        "operation_nonce": operation_nonce,
                        "attempt": attempt,
                        "result": "success",
                        "resolved_tip": fixed_tip,
                    },
                }
            )
            review = state.get("review")
            iteration = (
                review.get("iteration") if isinstance(review, Mapping) else None
            )
            retained_review = (
                {"iteration": iteration} if type(iteration) is int else {}
            )
            desired = {
                "candidate": copy.deepcopy(candidate),
                "tier": None,
                "state": "classifying",
                "policy_source": {
                    "commit": admission.policy.sha,
                    "digest": admission.policy.digest,
                },
                "steps": {},
                "review": retained_review,
                "approval": {},
                "authorization": {},
                "integration": integration,
            }
            state = self.store.transition(
                state,
                "fetch_result",
                {
                    "delta": {
                        name: value
                        for name, value in desired.items()
                        if state.get(name) != value or name == "state"
                    },
                    "scope_fetch_binding": copy.deepcopy(dict(binding)),
                    "scope_proof": copy.deepcopy(proof),
                },
                generation_digest=str(candidate["generation_digest"]),
                at=chain_core.iso_z(),
            )
            return candidate, scope, proof

        def persist(result: chain_core.FencedProcessResult) -> None:
            metadata = result.metadata
            complete = bool(
                result.authorized
                and result.returncode == 0
                and not result.launch_failed
                and not result.timed_out
                and not result.output_limit
                and not result.group_survived
                and isinstance(metadata, Mapping)
                and isinstance(metadata.get("full_patch"), Mapping)
                and isinstance(metadata.get("resolved_tip"), str)
            )
            binding: dict[str, Any] | None = None
            candidate: dict[str, Any] | None = None
            scope: engine.MergeScopeResult | None = None
            proof: object = None
            error: str | None = None
            fixed_tip = (
                str(metadata["resolved_tip"])
                if complete and isinstance(metadata, Mapping)
                else None
            )
            if complete and fixed_tip is not None:
                try:
                    fence, fence_error, _evidence = chain_core._read_fence_for_recovery(
                        lock._common, lock.common_dir
                    )
                    if (
                        fence_error is not None
                        or fence is None
                        or fence.digest != result.fence_digest
                        or fence.inode != result.fence_inode
                        or fence.record.get("intent_digest") != fetch_intent_digest
                        or fence.record.get("operation") != operation
                    ):
                        raise OSError(
                            "retained bootstrap fence is unavailable or mismatched"
                        )
                    binding = engine._publish_merge_scope_binding(
                        self.store,
                        state,
                        fetch_intent_digest=fetch_intent_digest,
                        scope_request=scope_request,
                        remote_tip=fixed_tip,
                        fence=fence,
                        result=result,
                    )
                    # Classification is deliberately excluded from this
                    # callback, but the successful result itself belongs to
                    # the fenced composite: after the /2 sidecar is durable,
                    # materialize its complete candidate before the original
                    # fence is cleared.
                    candidate, scope, proof = materialize_success(
                        binding, metadata, fixed_tip
                    )
                except (OSError, TypeError, ValueError, Refusal) as exc:
                    error = str(exc)
            if not complete or error is not None:
                failed_result(binding)
            holder.update(
                {
                    "complete": bool(
                        complete
                        and error is None
                        and binding is not None
                        and candidate is not None
                    ),
                    "fixed_tip": fixed_tip,
                    "binding": copy.deepcopy(binding),
                    "candidate": copy.deepcopy(candidate),
                    "scope": copy.deepcopy(scope),
                    "proof": copy.deepcopy(proof),
                    "error": error,
                    "metadata": copy.deepcopy(metadata),
                }
            )

        environment = engine._merge_scope_environment()
        try:
            engine._require_git_no_lazy_fetch_qualification(
                self._git_no_lazy_fetch_qualification,
                admission.worktree,
                environment,
            )
        except OSError as exc:
            failed_result(None)
            holder.update(
                {
                    "complete": False,
                    "fixed_tip": None,
                    "binding": None,
                    "error": str(exc),
                    "metadata": None,
                }
            )
            scope_failure = admission.run_task is not None
            reason = (
                V2ReasonCode.RUN_TASK_BINDING_INVALID
                if scope_failure
                else V2ReasonCode.FETCH_FAILED
            )
            refusal = chain_core._merge_refusal(
                reason,
                (
                    f"forge: {verb} refused — run/task scope derivation is invalid"
                    if scope_failure
                    else f"forge: {verb} refused — fixed target fetch failed"
                ),
                expected="the pre-lock Git qualification to remain exact",
                observed=str(exc),
                chain=state,
            )
            if scope_failure:
                state = self._release_to_aborted(
                    state, reason="run/task scope derivation is invalid"
                )
                refusal.chain = state
            raise refusal from exc
        composite_result = chain_core.run_fenced_command(
            lock,
            operation=operation,
            intent_digest=fetch_intent_digest,
            intent_validator=intent_current,
            argv=engine._merge_bootstrap_child_argv(
                admission,
                fetch_argv=fetch_argv,
                remote_tip=remote_tip,
            ),
            cwd=admission.worktree,
            persist_result=persist,
            env=environment,
            timeout=runtime.COMMAND_TIMEOUT_SECONDS,
            cap=runtime.OUTPUT_CAP_BYTES,
            verbose=False,
            result_transform=lambda raw: engine._decode_merge_bootstrap_result(
                raw,
                run_bound=admission.run_task is not None,
                fetch_argv=fetch_argv,
                worktree=admission.worktree,
                candidate_head=admission.candidate_head,
                environment_digest=engine._git_environment_digest(environment),
            ),
        )
        if not holder.get("complete"):
            scope_failure = admission.run_task is not None
            reason = (
                V2ReasonCode.RUN_TASK_BINDING_INVALID
                if scope_failure
                else V2ReasonCode.FETCH_FAILED
            )
            refusal = chain_core._merge_refusal(
                reason,
                (
                    f"forge: {verb} refused — run/task scope derivation is invalid"
                    if scope_failure
                    else f"forge: {verb} refused — fixed target fetch failed"
                ),
                expected="one complete composite bootstrap child",
                observed=str(holder.get("error") or composite_result.evidence()),
                chain=state,
            )
            if scope_failure:
                state = self._release_to_aborted(
                    state, reason="run/task scope derivation is invalid"
                )
                refusal.chain = state
            raise refusal

        binding = holder.get("binding")
        candidate = holder.get("candidate")
        scope = holder.get("scope")
        proof = holder.get("proof")
        if (
            not isinstance(binding, Mapping)
            or not isinstance(candidate, Mapping)
            or (scope is not None and not isinstance(scope, engine.MergeScopeResult))
        ):
            raise FrozenError(
                "composite bootstrap sidecar was not durably retained",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        exceeded = bool(scope is not None and scope.result == "exceeded")
        if exceeded:
            fetch_digest = engine._merge_event_digest(
                self.store, str(state["chain_id"]), "fetch_result"
            )
            if not isinstance(proof, Mapping) or fetch_digest is None:
                raise FrozenError(
                    "run-scope refusal lacks its authenticated result proof",
                    chain_id=str(state["chain_id"]),
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            state = self._release_scope_exceeded(
                state,
                scope_proof_digest=str(proof["digest"]),
                fetch_result_event_digest=fetch_digest,
                verb=verb,
            )
            raise chain_core._merge_refusal(
                V2ReasonCode.RUN_SCOPE_EXCEEDED,
                f"forge: {verb} refused — changed paths exceed bound task scope",
                expected="every changed path within task files and admitted run scope",
                observed=str(scope.out_of_scope_paths if scope is not None else ()),
                chain=state,
            )
        return state, engine.MergeBootstrapClassification(
            candidate=copy.deepcopy(dict(candidate)),
            scope=copy.deepcopy(scope),
            full_patch_output_digest=str(binding["full_patch_output_digest"]),
            verb=verb,
        )

    def _run_bootstrap_generation(
        self,
        state: dict[str, Any],
        admission: engine.MergeAdmission,
        lock: chain_core.CommonRebaseLock,
        *,
        operation_nonce: str,
        attempt: int,
        remote_tip: str | None,
        generation_number: int,
        verb: str = "merge start",
    ) -> tuple[dict[str, Any], engine.MergeBootstrapClassification]:
        """Run the fenced bootstrap and retain its classification inputs."""

        return self._run_bootstrap_generation_composite(
            state,
            admission,
            lock,
            operation_nonce=operation_nonce,
            attempt=attempt,
            remote_tip=remote_tip,
            generation_number=generation_number,
            verb=verb,
        )

    def _complete_bootstrap_classification(
        self,
        state: dict[str, Any],
        admission: engine.MergeAdmission,
        pending: engine.MergeBootstrapClassification,
    ) -> tuple[dict[str, Any], engine.MergeCandidateGeneration]:
        """Classify a durable candidate while holding only its chain lease."""

        if (
            not chain_core._merge_bootstrap_classification_pending(state)
            or state.get("candidate") != pending.candidate
            or state.get("candidate", {}).get("diff_sha256")
            != pending.full_patch_output_digest
        ):
            raise FrozenError(
                "merge bootstrap classification input diverges from its generation",
                chain_id=str(state.get("chain_id", "")) or None,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        if pending.scope is not None and pending.scope.result == "exceeded":
            if (
                pending.scope_proof_digest is None
                or pending.fetch_result_event_digest is None
            ):
                raise FrozenError(
                    "run-scope refusal lacks its authenticated result proof",
                    chain_id=str(state["chain_id"]),
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            terminal = self._release_scope_exceeded(
                state,
                scope_proof_digest=pending.scope_proof_digest,
                fetch_result_event_digest=pending.fetch_result_event_digest,
                verb="merge recover",
            )
            raise chain_core._merge_refusal(
                V2ReasonCode.RUN_SCOPE_EXCEEDED,
                "forge: merge recover refused — changed paths exceed bound task scope",
                expected="every changed path within task files and admitted run scope",
                observed=str(pending.scope.out_of_scope_paths),
                chain=terminal,
            )
        binding = state.get("run_binding")
        with self.store._journal_outer(
            binding if isinstance(binding, Mapping) else None
        ), chain_core.acquire_chain_lease(
            self.store.root,
            chain_id=str(state["chain_id"]),
            session=self.store._session(None),
        ) as lease:
            current = self.store.load_locked(str(state["chain_id"]), lease=lease)
            if current != state or not chain_core._merge_bootstrap_classification_pending(current):
                raise FrozenError(
                    "merge bootstrap classification snapshot changed",
                    chain_id=str(state["chain_id"]),
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            generation = engine.bind_merge_candidate_generation(
                self.ctx,
                admission,
                str(pending.candidate["remote_tip"]),
                generation=int(pending.candidate["generation"]),
                scope_result=pending.scope,
                fixed_tip_bound=True,
                observation=None,
                diff_output_digest=pending.full_patch_output_digest,
            )
            if generation.candidate != pending.candidate:
                raise FrozenError(
                    "merge bootstrap classification changed the immutable candidate",
                    chain_id=str(state["chain_id"]),
                    expected=str(pending.candidate.get("generation_digest")),
                    observed=str(generation.candidate.get("generation_digest")),
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            candidate_repo = chain_core.Repository(admission.worktree)
            observed_head = candidate_repo.head()
            if observed_head != pending.candidate["candidate_head"]:
                raise chain_core._merge_refusal(
                    V2ReasonCode.CANDIDATE_STALE,
                    f"forge: {pending.verb} refused — candidate HEAD changed during classification",
                    expected=str(pending.candidate["candidate_head"]),
                    observed=observed_head,
                    chain=current,
                )
            engine._merge_worktree_status(
                candidate_repo,
                Path(admission.worktree_identity["git_dir"]),
                verb=pending.verb,
            )
            integration = copy.deepcopy(current["integration"])
            integration["intent"] = None
            current = self.store.transition_locked(
                current,
                "generation_refreshed",
                {
                    "delta": {
                        "state": "verifying",
                        "tier": copy.deepcopy(generation.tier),
                        "integration": integration,
                    }
                },
                generation_digest=str(pending.candidate["generation_digest"]),
                lease=lease,
                at=chain_core.iso_z(),
            )
        return current, generation


    def start_chain(
        self,
        worktree: str,
        declared_tier: str | None = None,
        *,
        task: str | None = None,
        remote_tip: str | None = None,
    ) -> Outcome:
        """Create and classify one dormant DM-014 chain."""

        engine._require_merge_lifecycle_control("atomic-worktree-ownership")
        if self.ctx.options.chain_id is not None:
            raise chain_core._merge_refusal(
                V2ReasonCode.STATE_PRECONDITION,
                "forge: merge start refused — --chain-id is not admitted for a new chain",
                observed=self.ctx.options.chain_id,
            )
        admission = prepare_merge_admission(
            self.ctx, worktree, declared_tier, task=task
        )
        self._prepare_bootstrap_git_no_lazy_fetch_qualification(
            admission,
            verb="merge start",
        )
        chain_id = self._allocate_chain_id()
        journal_binding = (
            admission.run_task.binding if admission.run_task is not None else None
        )
        with self.store._journal_outer(journal_binding):
            with self.store.admission_lock(
                admission.worktree
            ), self._recording_common_lock(
                Path(admission.worktree_identity["common_dir"]),
                chain_id=chain_id,
                operation="start",
            ) as common_lock:
                (
                    worktree_digest,
                    claim_name,
                    claim_path,
                    predecessor_id,
                    predecessor_digest,
                ) = self._claim_slot(admission)
                started_at = chain_core.iso_z()
                initial = self._initial_merge_state(
                    chain_id, admission, claim_path, at=started_at
                )
                state = self.store.create(initial, at=started_at)
                claim_record = {
                    "chain_id": chain_id,
                    "host": initial["owner"]["host"],
                    "pid": initial["owner"]["pid"],
                    "session": initial["owner"]["session"],
                    "started_at": started_at,
                    "worktree_digest": worktree_digest,
                }
                claim_digest = sha256_bytes(chain_core.canonical_bytes(claim_record))
                state = self.store.transition(
                    state,
                    "ownership_intent",
                    {
                        "worktree_digest": worktree_digest,
                        "claim_path": str(claim_path),
                        "intended_claim_digest": claim_digest,
                        "predecessor_chain_id": predecessor_id,
                        "predecessor_release_digest": predecessor_digest,
                    },
                    generation_digest=None,
                    at=chain_core.iso_z(),
                )
                ownership_intent_digest = engine._merge_event_digest(
                    self.store, chain_id, "ownership_intent"
                )
                if ownership_intent_digest is None:
                    raise FrozenError(
                        "merge ownership intent digest is unavailable",
                        chain_id=chain_id,
                        schema=REVISION9_OUTPUT_SCHEMA,
                    )
                try:
                    published = engine._publish_merge_claim(
                        self.store, claim_name, claim_path, claim_record
                    )
                except OSError as exc:
                    raise engine._merge_publication_failure(
                        self.store,
                        state,
                        claim_path,
                        claim_record,
                        exc,
                    ) from exc
                state = self.store.transition(
                    state,
                    "ownership_claimed",
                    {
                        "ownership_intent_digest": ownership_intent_digest,
                        "claim_inode": published.inode,
                        "claim_digest": published.digest,
                        "predecessor_chain_id": predecessor_id,
                        "predecessor_release_digest": predecessor_digest,
                    },
                    generation_digest=None,
                    at=chain_core.iso_z(),
                )
                observed_admission = prepare_merge_admission(
                    self.ctx, worktree, declared_tier, task=task
                )
                if observed_admission != admission:
                    raise chain_core._merge_refusal(
                        V2ReasonCode.WORKTREE_INVALID,
                        "forge: merge start refused — admission changed under the common lock",
                        expected=str(admission),
                        observed=str(observed_admission),
                        chain=state,
                    )
                admission = observed_admission
                engine._require_git_no_lazy_fetch_qualification(
                    self._git_no_lazy_fetch_qualification,
                    admission.worktree,
                    engine._merge_scope_environment(),
                )
                operation_nonce = secrets.token_hex(16)
                state = self.store.transition(
                    state,
                    "fetch_intent",
                    {
                        "repository": str(admission.repository),
                        "worktree": copy.deepcopy(admission.worktree_identity),
                        "branch": admission.branch,
                        "target": copy.deepcopy(admission.target),
                        "pre_fetch_head": admission.candidate_head,
                        "policy_digest": admission.policy.digest,
                        "operation_nonce": operation_nonce,
                        "attempt": 1,
                        "scope_request": engine._merge_scope_request(admission),
                    },
                    generation_digest=None,
                    at=chain_core.iso_z(),
                )
                state, pending = self._run_bootstrap_generation(
                    state,
                    admission,
                    common_lock,
                    operation_nonce=operation_nonce,
                    attempt=1,
                    remote_tip=remote_tip,
                    generation_number=1,
                )
        state, generation = self._complete_bootstrap_classification(
            state, admission, pending
        )
        return engine._success(
            state,
            f"merge chain {chain_id} started for {admission.worktree}",
            f"forge merge verify --chain-id {chain_id}",
        )

    def _admission_from_candidate_observation(
        self,
        state: Mapping[str, Any],
        observation: Mapping[str, Any],
        *,
        verb: str,
        require_current_generation: bool,
    ) -> engine.MergeAdmission:
        repository, policy, _paths, _diff, _classification = (
            engine._parse_merge_candidate_observation(
                state,
                observation,
                verb=verb,
                require_current_generation=require_current_generation,
            )
        )
        binding = state.get("run_binding")
        run_task = None
        if isinstance(binding, Mapping):
            run_task = chain_core._prove_merge_run_task_binding(
                Path(str(state["repository"])),
                self.store.common_root,
                str(binding["run_id"]),
                str(binding["task_id"]),
                policy.digest,
            )
            if run_task.binding != dict(binding):
                raise chain_core._merge_refusal(
                    V2ReasonCode.RUN_TASK_BINDING_INVALID,
                    f"forge: {verb} refused — run/task binding changed during observation",
                    expected=str(dict(binding)),
                    observed=str(run_task.binding),
                    chain=state,
                )
        return engine.MergeAdmission(
            repository=Path(str(state["repository"])),
            worktree=repository.root,
            worktree_identity={
                name: str(state["worktree"][name])
                for name in ("path", "git_dir", "common_dir")
            },
            branch=str(state["branch"]),
            target=copy.deepcopy(dict(state["target"])),
            candidate_head=str(observation["expected_head"]),
            policy=policy,
            declared_tier=(
                str(observation["declared_tier"])
                if observation.get("declared_tier") is not None
                else None
            ),
            run_task=run_task,
            status_output_digest=sha256_bytes(b""),
        )

    def _admission_for_refresh(
        self,
        state: Mapping[str, Any],
        *,
        observation: Mapping[str, Any] | None = None,
        verb: str = "merge refresh",
    ) -> engine.MergeAdmission:
        if observation is not None:
            return self._admission_from_candidate_observation(
                state,
                observation,
                verb=verb,
                require_current_generation=True,
            )
        binding = state.get("run_binding")
        options = dataclasses.replace(
            self.ctx.options,
            chain_id=None,
            run_id=(str(binding["run_id"]) if isinstance(binding, Mapping) else None),
        )
        context = chain_core.CommandContext(
            repo=self.ctx.repo,
            store=self.store,
            options=options,
            policy=self.ctx.policy,
        )
        admission = prepare_merge_admission(
            context,
            str(state["worktree"]["path"]),
            None,
            task=(
                str(binding["task_id"])
                if isinstance(binding, Mapping)
                else None
            ),
        )
        if (
            admission.repository != Path(str(state["repository"]))
            or admission.worktree_identity
            != {
                name: state["worktree"][name]
                for name in ("path", "git_dir", "common_dir")
            }
            or admission.branch != state["branch"]
            or admission.target != state["target"]
        ):
            raise chain_core._merge_refusal(
                V2ReasonCode.WORKTREE_INVALID,
                "forge: merge refresh refused — recorded admission identity changed",
                expected="the immutable repository/worktree/branch/target tuple",
                observed=str(admission),
                chain=state,
            )
        return admission

    def _refresh_iteration(self, state: Mapping[str, Any]) -> int:
        """Apply the ordinary scalar row before review-specific refusals."""

        integration = state.get("integration")
        condition = integration.get("condition") if isinstance(integration, Mapping) else None
        admitted_conditions = {
            ("classifying", "fetch-failed"),
            ("revising", "rebase-failed"),
        }
        if condition != "none" and (state["state"], condition) not in admitted_conditions:
            self._wrong_state(
                state,
                "an ordinary active pre-push tuple or retryable refresh condition",
                "merge refresh",
            )
        if state["state"] not in {
            "classifying",
            "verifying",
            "reviewing",
            "revising",
            "awaiting_approval",
            "authorized",
        }:
            self._wrong_state(state, "an active mutable pre-push state", "merge refresh")
        review = state.get("review")
        iteration = review.get("iteration", 0) if isinstance(review, Mapping) else 0
        if type(iteration) is not int:
            raise FrozenError(
                "merge review iteration is malformed",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        if iteration >= 8:
            raise chain_core._merge_refusal(
                V2ReasonCode.ITERATION_CAP,
                "forge: merge refresh refused — review iteration cap of 8 is final",
                expected="safe abort after the eighth review cycle",
                observed=str(iteration),
                chain=state,
            )
        if isinstance(review, Mapping) and review.get("operator_cosign_required") is True:
            raise chain_core._merge_refusal(
                V2ReasonCode.STATE_PRECONDITION,
                "forge: merge refresh refused — above-MINOR disposition awaits operator co-sign",
                expected="merge approve for the sole outstanding disposition",
                observed="pending finding-disposition",
                chain=state,
            )
        return iteration

    def refresh(self, *, remote_tip: str | None = None) -> Outcome:
        engine._require_merge_lifecycle_control("admission-priority")
        state = self._preflight_lifecycle(self._load(), "merge refresh")
        self._halt(state)
        self._refresh_iteration(state)
        prelock_admission = self._admission_for_refresh(
            state, verb="merge refresh"
        )
        self._prepare_bootstrap_git_no_lazy_fetch_qualification(
            prelock_admission,
            verb="merge refresh",
        )
        binding = state.get("run_binding")
        with self.store._journal_outer(
            binding if isinstance(binding, Mapping) else None
        ), self._recording_common_lock(
            Path(str(state["worktree"]["common_dir"])),
            chain_id=str(state["chain_id"]),
            operation="refresh",
        ) as common_lock:
            state = self._preflight_lifecycle(self._load(), "merge refresh")
            iteration = self._refresh_iteration(state)
            prior_candidate = state.get("candidate")
            prior_integration = state.get("integration")
            prior_operation = (
                prior_integration.get("intent")
                if isinstance(prior_integration, Mapping)
                else None
            )
            admission_head = (
                str(prior_candidate["candidate_head"])
                if isinstance(prior_candidate, Mapping)
                else str(prior_operation.get("pre_fetch_head", ""))
                if isinstance(prior_operation, Mapping)
                else ""
            )
            admission_tip = (
                str(prior_candidate["remote_tip"])
                if isinstance(prior_candidate, Mapping)
                else admission_head
            )
            admission = self._admission_for_refresh(
                state, verb="merge refresh"
            )
            engine._require_git_no_lazy_fetch_qualification(
                self._git_no_lazy_fetch_qualification,
                admission.worktree,
                engine._merge_scope_environment(),
            )
            prior_intent = state.get("integration", {}).get("intent")
            attempt = 1
            if isinstance(prior_intent, Mapping) and type(
                prior_intent.get("attempt")
            ) is int:
                attempt = int(prior_intent["attempt"]) + 1
            operation_nonce = secrets.token_hex(16)
            scope_request = engine._merge_scope_request(admission)
            if prior_candidate is None:
                state = self.store.transition(
                    state,
                    "fetch_intent",
                    {
                        "repository": str(admission.repository),
                        "worktree": copy.deepcopy(admission.worktree_identity),
                        "branch": admission.branch,
                        "target": copy.deepcopy(admission.target),
                        "pre_fetch_head": admission.candidate_head,
                        "policy_digest": admission.policy.digest,
                        "operation_nonce": operation_nonce,
                        "attempt": attempt,
                        "scope_request": scope_request,
                    },
                    generation_digest=None,
                    at=chain_core.iso_z(),
                )
            else:
                integration = copy.deepcopy(state["integration"])
                engine._reset_merge_nonmovement_counter(integration)
                integration.update(
                    {
                        "condition": "none",
                        "primary_condition": "none",
                        "epoch": None,
                        "intent": {
                            "operation": "fetch",
                            "operation_nonce": operation_nonce,
                            "attempt": attempt,
                            "target": copy.deepcopy(admission.target),
                            "pre_fetch_head": admission.candidate_head,
                            "scope_request": scope_request,
                        },
                    }
                )
                state = self.store.transition(
                    state,
                    "fetch_intent",
                    {"delta": {"state": "classifying", "integration": integration}},
                    generation_digest=str(prior_candidate["generation_digest"]),
                    at=chain_core.iso_z(),
                )
            next_number = (
                int(prior_candidate["generation"]) + 1
                if isinstance(prior_candidate, Mapping)
                else 1
            )
            state, pending = self._run_bootstrap_generation(
                state,
                admission,
                common_lock,
                operation_nonce=operation_nonce,
                attempt=attempt,
                remote_tip=remote_tip,
                generation_number=next_number,
                verb="merge refresh",
            )
        state, generation = self._complete_bootstrap_classification(
            state, admission, pending
        )
        candidate = copy.deepcopy(generation.candidate)
        return engine._success(
            state,
            f"merge chain {state['chain_id']} refreshed to generation {candidate['generation']}",
            f"forge merge verify --chain-id {state['chain_id']}",
        )

    def approve(self, candidate: str) -> Outcome:
        engine._require_merge_lifecycle_control("candidate-bound-approval")
        state = self._preflight_lifecycle(self._load(), "merge approve")
        self._halt(state)
        review = state.get("review")
        pending = bool(
            state["state"] in {"reviewing", "revising"}
            and isinstance(review, Mapping)
            and review.get("operator_cosign_required") is True
        )
        iteration = review.get("iteration", 0) if isinstance(review, Mapping) else 0
        if type(iteration) is not int:
            raise FrozenError(
                "merge review iteration is malformed",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        if pending and iteration >= 8:
            raise chain_core._merge_refusal(
                V2ReasonCode.ITERATION_CAP,
                "forge: merge approve refused — review iteration cap of 8 is final",
                expected="status or safe abort after the eighth review cycle",
                observed=str(iteration),
                chain=state,
            )
        if not pending and state["state"] != "awaiting_approval":
            self._wrong_state(
                state,
                "a sole pending disposition or awaiting_approval",
                "merge approve",
            )
        generation = state.get("candidate")
        if not isinstance(generation, Mapping):
            raise FrozenError(
                "merge approval generation is unavailable",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        expected = str(generation.get("candidate_head", ""))
        if chain_core.COMMIT_RE.fullmatch(candidate) is None or candidate != expected:
            raise chain_core._merge_refusal(
                V2ReasonCode.CANDIDATE_STALE,
                "forge: merge approve refused — candidate HEAD does not match the current generation",
                expected=expected,
                observed=candidate,
                remediation=f"forge merge approve --candidate {expected} --chain-id {state['chain_id']}",
                chain=state,
            )
        now = chain_core.iso_z()
        if pending:
            dispositions = review.get("dispositions")
            approval = state.get("approval")
            unresolved = []
            if isinstance(dispositions, list):
                for disposition in dispositions:
                    if not isinstance(disposition, Mapping) or disposition.get(
                        "severity"
                    ) not in {"CRITICAL", "MAJOR"}:
                        continue
                    separately_cosigned = bool(
                        isinstance(approval, Mapping)
                        and approval.get("purpose") == "finding-disposition"
                        and approval.get("finding") == disposition.get("finding")
                        and approval.get("resolution") == disposition.get("resolution")
                    )
                    if not separately_cosigned:
                        unresolved.append(disposition)
            if len(unresolved) != 1:
                raise FrozenError(
                    "merge disposition co-sign projection is ambiguous",
                    chain_id=str(state["chain_id"]),
                    observed=str(len(unresolved)),
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            selected = unresolved[0]
            current_review = copy.deepcopy(dict(review))
            current_review["operator_cosign_required"] = False
            approval_record = {
                "purpose": "finding-disposition",
                "chain_id": state["chain_id"],
                "finding": selected["finding"],
                "severity": selected["severity"],
                "resolution": selected["resolution"],
                "candidate": expected,
                "generation_digest": state["candidate"]["generation_digest"],
                "recorded_at": now,
                "directed_by": "operator",
            }
            delta = {"review": current_review, "approval": approval_record}
            message = f"merge finding {selected['finding']} operator co-sign recorded"
        elif state["state"] == "awaiting_approval":
            integration = state.get("integration")
            if not isinstance(integration, dict):
                raise FrozenError(
                    "merge integration projection is malformed",
                    chain_id=str(state["chain_id"]),
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            if integration.get("condition") == "remote-churn":
                purpose = "remote-churn"
                updated_integration = copy.deepcopy(integration)
                updated_integration.update(
                    {
                        "condition": "none",
                        "primary_condition": "none",
                        "remote_movement_count": 0,
                    }
                )
                delta = {"state": "authorized", "integration": updated_integration}
                message = "merge remote-churn acknowledgement recorded"
            else:
                purpose = "gate-4"
                delta = {"state": "authorized"}
                message = "merge Gate-4 operator approval recorded"
            approval_record = {
                "purpose": purpose,
                "chain_id": state["chain_id"],
                "candidate": expected,
                "generation_digest": state["candidate"]["generation_digest"],
                "recorded_at": now,
                "directed_by": "operator",
            }
            delta["approval"] = approval_record
        state = self.store.transition(
            state,
            "approval_recorded",
            {"delta": delta},
            generation_digest=str(state["candidate"]["generation_digest"]),
            at=now,
        )
        return engine._success(
            state,
            message,
            f"forge status --chain-id {state['chain_id']}",
        )

    def _release_to_aborted(
        self,
        state: dict[str, Any],
        *,
        reason: str | None,
        terminal_preconditions: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        claim = state["worktree"]["claim"]
        release_mode = (
            "acquired" if claim["status"] == "owned" else "never-published"
        )
        preconditions = (
            copy.deepcopy(dict(terminal_preconditions))
            if terminal_preconditions is not None
            else {
                "schema": "forge-merge-abort-preconditions/1",
                "chain_id": state["chain_id"],
                "source_state": state["state"],
                "candidate": copy.deepcopy(state.get("candidate")),
                "integration": copy.deepcopy(state["integration"]),
                "claim": copy.deepcopy(claim),
                # The operator-facing prose is not a durable event member;
                # bind only replay-reconstructible authority facts.
                "reason": None,
            }
        )
        generation = state.get("candidate")
        generation_digest = (
            str(generation["generation_digest"])
            if isinstance(generation, Mapping)
            else None
        )
        claim_path = Path(str(claim["path"]))
        if (
            release_mode == "never-published"
            and not engine._merge_unpublished_claim_absent(state, self.store)
        ):
            raise FrozenError(
                "unpublished merge ownership path unexpectedly exists",
                chain_id=str(state["chain_id"]),
                observed=str(claim_path),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        state = self.store.transition(
            state,
            "ownership_release_intent",
            {
                "target_terminal": "aborted",
                "terminal_disposition": "ordinary",
                "source_state": state["state"],
                "terminal_preconditions_digest": sha256_bytes(
                    chain_core.canonical_bytes(preconditions)
                ),
                "release_mode": release_mode,
            },
            generation_digest=generation_digest,
            at=chain_core.iso_z(),
        )
        release_intent_digest = engine._merge_event_digest(
            self.store, str(state["chain_id"]), "ownership_release_intent"
        )
        if release_intent_digest is None:
            raise FrozenError(
                "merge ownership release intent digest is unavailable",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        if release_mode == "acquired":
            observed_claim = engine._remove_merge_claim(self.store, state, unlink=False)
            exists = True
            observed_inode = observed_claim.inode
            observed_digest = observed_claim.digest
        else:
            if not engine._merge_unpublished_claim_absent(state, self.store):
                raise FrozenError(
                    "unpublished merge ownership path unexpectedly exists",
                    chain_id=str(state["chain_id"]),
                    observed=str(claim_path),
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            exists = False
            observed_inode = None
            observed_digest = None
        observation = {
            "claim_path": state["worktree"]["claim"]["path"],
            "exists": exists,
            "inode": observed_inode,
            "digest": observed_digest,
        }
        state = self.store.transition(
            state,
            "ownership_released",
            {
                "release_intent_digest": release_intent_digest,
                "release_mode": release_mode,
                "terminal_disposition": "ordinary",
                "claim_inode": state["worktree"]["claim"]["inode"],
                "claim_digest": state["worktree"]["claim"]["digest"],
                "claim_observation_digest": sha256_bytes(
                    chain_core.canonical_bytes(observation)
                ),
            },
            generation_digest=generation_digest,
            at=chain_core.iso_z(),
        )
        if (
            release_mode == "never-published"
            and not engine._merge_unpublished_claim_absent(state, self.store)
        ):
            raise FrozenError(
                "unpublished merge ownership path unexpectedly exists",
                chain_id=str(state["chain_id"]),
                observed=str(claim_path),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        terminal = self.store.transition(
            state,
            "aborted",
            {"delta": {"state": "aborted"}},
            generation_digest=generation_digest,
            at=chain_core.iso_z(),
        )
        if release_mode == "acquired":
            try:
                engine._remove_merge_claim(self.store, terminal)
            except (FrozenError, OSError):
                # Terminal truth is event-authoritative; tombstone collection
                # is best effort and must never revoke the durable release.
                pass
        return terminal

    def _release_to_aborted_locked(
        self,
        state: dict[str, Any],
        lease: chain_core.ChainLease,
        *,
        reason: str | None,
        terminal_preconditions: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Perform an ordinary release while recovery owns its chain lease."""

        claim = state["worktree"]["claim"]
        claim_status = claim.get("status")
        if claim_status not in {"owned", "unpublished"}:
            raise FrozenError(
                "bootstrap recovery cannot release its recorded worktree claim",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        release_mode = (
            "acquired" if claim_status == "owned" else "never-published"
        )
        claim_path = Path(str(claim["path"]))
        if (
            release_mode == "never-published"
            and not engine._merge_unpublished_claim_absent(state, self.store)
        ):
            raise FrozenError(
                "unpublished merge ownership path unexpectedly exists",
                chain_id=str(state["chain_id"]),
                observed=str(claim_path),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        preconditions = (
            copy.deepcopy(dict(terminal_preconditions))
            if terminal_preconditions is not None
            else {
                "schema": "forge-merge-abort-preconditions/1",
                "chain_id": state["chain_id"],
                "source_state": state["state"],
                "candidate": copy.deepcopy(state.get("candidate")),
                "integration": copy.deepcopy(state["integration"]),
                "claim": copy.deepcopy(claim),
                # The operator-facing prose is not a durable event member;
                # bind only replay-reconstructible authority facts.
                "reason": None,
            }
        )
        state = self._epoch_transition(
            state,
            lease,
            "ownership_release_intent",
            {
                "target_terminal": "aborted",
                "terminal_disposition": "ordinary",
                "source_state": state["state"],
                "terminal_preconditions_digest": sha256_bytes(
                    chain_core.canonical_bytes(preconditions)
                ),
                "release_mode": release_mode,
            },
        )
        release_intent_digest = self._tail_event_digest(
            state, "ownership_release_intent"
        )
        if release_mode == "acquired":
            observed_claim = engine._remove_merge_claim(self.store, state, unlink=False)
            exists = True
            observed_inode = observed_claim.inode
            observed_digest = observed_claim.digest
        else:
            if not engine._merge_unpublished_claim_absent(state, self.store):
                raise FrozenError(
                    "unpublished merge ownership path unexpectedly exists",
                    chain_id=str(state["chain_id"]),
                    observed=str(claim_path),
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            exists = False
            observed_inode = None
            observed_digest = None
        observation = {
            "claim_path": state["worktree"]["claim"]["path"],
            "exists": exists,
            "inode": observed_inode,
            "digest": observed_digest,
        }
        state = self._epoch_transition(
            state,
            lease,
            "ownership_released",
            {
                "release_intent_digest": release_intent_digest,
                "release_mode": release_mode,
                "terminal_disposition": "ordinary",
                "claim_inode": state["worktree"]["claim"]["inode"],
                "claim_digest": state["worktree"]["claim"]["digest"],
                "claim_observation_digest": sha256_bytes(
                    chain_core.canonical_bytes(observation)
                ),
            },
        )
        if (
            release_mode == "never-published"
            and not engine._merge_unpublished_claim_absent(state, self.store)
        ):
            raise FrozenError(
                "unpublished merge ownership path unexpectedly exists",
                chain_id=str(state["chain_id"]),
                observed=str(claim_path),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        terminal = self._epoch_transition(
            state, lease, "aborted", {"delta": {"state": "aborted"}}
        )
        if release_mode == "acquired":
            try:
                engine._remove_merge_claim(self.store, terminal)
            except (FrozenError, OSError):
                pass
        return terminal

    def _release_scope_exceeded(
        self,
        state: dict[str, Any],
        *,
        scope_proof_digest: str,
        fetch_result_event_digest: str,
        verb: str = "merge start",
    ) -> dict[str, Any]:
        chain_core._require_merge_integration_control("scope-release-clean-status")
        candidate = state.get("candidate")
        if (
            not isinstance(candidate, Mapping)
            or chain_core.SHA256_RE.fullmatch(scope_proof_digest) is None
            or chain_core.SHA256_RE.fullmatch(fetch_result_event_digest) is None
        ):
            raise FrozenError(
                "run-scope abort evidence is malformed",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        repository = chain_core.Repository(Path(str(state["worktree"]["path"])))
        current_head = repository.head()
        status = engine._merge_worktree_status(
            repository,
            Path(str(state["worktree"]["git_dir"])),
            verb=verb,
        )
        if status != b"":
            raise FrozenError(
                "run-scope abort worktree status is not exact clean",
                chain_id=str(state["chain_id"]),
                observed=(
                    f"bytes={len(status)};sha256={sha256_bytes(status)}"
                ),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        if current_head != candidate["candidate_head"]:
            raise FrozenError(
                "run-scope abort candidate changed before release",
                chain_id=str(state["chain_id"]),
                observed=current_head,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        preconditions = {
            "schema": "forge-run-scope-abort-preconditions/1",
            "target_terminal": "aborted",
            "terminal_disposition": "ordinary",
            "release_mode": "acquired",
            "source_state": "classifying",
            "scope_proof_digest": scope_proof_digest,
            "fetch_result_event_digest": fetch_result_event_digest,
            "generation_digest": candidate["generation_digest"],
            "worktree_identity": {
                name: state["worktree"][name]
                for name in ("path", "git_dir", "common_dir")
            },
            "branch": state["branch"],
            "candidate_head": candidate["candidate_head"],
            "current_head": current_head,
            "status_output_digest": sha256_bytes(b""),
            "push_intent_event_digests": [],
            "git_mutation_intent_event_digests": [],
            "unresolved_fence_digests": [],
        }
        return self._release_to_aborted(
            state,
            reason="changed paths exceed bound task scope",
            terminal_preconditions=preconditions,
        )

    def abort(self, reason: str | None = None) -> Outcome:
        engine._require_merge_lifecycle_control("admission-priority")
        state = self._load()
        claim = state.get("worktree", {}).get("claim")
        if isinstance(claim, Mapping) and claim.get("status") in {
            "releasing",
            "released",
        } and state["state"] not in {"closed", "aborted"}:
            raise chain_core._merge_refusal(
                V2ReasonCode.STATE_PRECONDITION,
                "forge: merge abort refused — ownership release completion is pending",
                expected="the cutoff-selected terminal event",
                observed=str(claim.get("status")),
                remediation=f"forge merge recover --chain-id {state['chain_id']}",
                chain=state,
            )
        containment, _vector = chain_core._merge_containment(state)
        inactive = engine._merge_inactive(state)
        if containment == "current":
            raise chain_core._merge_refusal(
                V2ReasonCode.STATE_PRECONDITION,
                "forge: merge abort refused — current intended HEAD is already contained",
                expected="pushed classification and cleanup",
                observed="current intended HEAD contained",
                remediation=f"forge merge recover --chain-id {state['chain_id']}",
                chain=state,
            )
        if containment == "older" and not inactive:
            raise chain_core._merge_refusal(
                V2ReasonCode.STATE_PRECONDITION,
                "forge: merge abort refused — an older attempted HEAD is contained",
                expected="historical landing reconciliation",
                observed="newest attempted HEAD uncontained",
                remediation=f"forge merge recover --chain-id {state['chain_id']}",
                chain=state,
            )
        attempted = engine._merge_has_attempt(state)
        worktree = Path(str(state.get("worktree", {}).get("path", "")))
        if not worktree.exists():
            if inactive:
                raise chain_core._merge_refusal(
                    V2ReasonCode.STATE_PRECONDITION,
                    "forge: merge abort refused — inactive chain cannot prove missing-worktree safety",
                    expected="an unchanged worktree or observation-only recovery",
                    observed="recorded worktree is missing",
                    remediation=f"forge status --chain-id {state['chain_id']}",
                    chain=state,
                )
            self._preflight_lifecycle(state, "merge abort")
        if state["state"] in {"closed", "aborted"}:
            self._wrong_state(state, "a nonterminal pre-push chain", "merge abort")
        if state["state"] in {"pushed", "cleanup_pending"}:
            raise chain_core._merge_refusal(
                V2ReasonCode.STATE_PRECONDITION,
                "forge: merge abort refused — durable pushed truth requires cleanup",
                expected="merge cleanup after pushed truth",
                observed=str(state["state"]),
                chain=state,
            )
        if state["state"] in {"rebasing", "rebase_conflict"}:
            raise chain_core._merge_refusal(
                V2ReasonCode.STATE_PRECONDITION,
                "forge: merge abort refused — active rebase restoration is required",
                expected="owned rebase abort/restoration before logical release",
                observed=str(state["state"]),
                remediation=f"forge merge recover --abort-rebase --chain-id {state['chain_id']}",
                chain=state,
            )
        if attempted and not inactive and containment != "all-false":
            raise chain_core._merge_refusal(
                V2ReasonCode.STATE_PRECONDITION,
                "forge: merge abort refused — attempted heads lack authoritative all-false containment",
                expected="fresh all-false attempted-head containment",
                observed=containment,
                remediation=f"forge merge recover --chain-id {state['chain_id']}",
                chain=state,
            )
        if engine._merge_process_unresolved(state):
            raise chain_core._merge_refusal(
                V2ReasonCode.STATE_PRECONDITION,
                "forge: merge abort refused — a live or unresolved process remains",
                expected="no live or unresolved fence/process",
                observed="repository mutation ownership is unresolved",
                remediation=f"forge merge recover --chain-id {state['chain_id']}",
                chain=state,
            )
        self._halt(state)
        binding = state.get("run_binding")
        terminal_disposition = "ordinary"
        with self.store._journal_outer(
            binding if isinstance(binding, Mapping) else None
        ), self._recording_common_lock(
            Path(str(state["worktree"]["common_dir"])),
            chain_id=str(state["chain_id"]),
            operation="abort",
        ) as common_lock:
            with chain_core.acquire_chain_lease(
                self.store.root,
                chain_id=str(state["chain_id"]),
                session=self.store._session(None),
                exclusion=common_lock,
            ) as lease:
                current = self.store.load_locked(
                    str(state["chain_id"]), lease=lease
                )
                current_containment, _current_vector = chain_core._merge_containment(current)
                current_inactive = engine._merge_inactive(current)
                if current_containment == "current":
                    raise chain_core._merge_refusal(
                        V2ReasonCode.STATE_PRECONDITION,
                        "forge: merge abort refused — current intended HEAD is already contained",
                        expected="pushed classification and cleanup",
                        observed="current intended HEAD contained",
                        remediation=f"forge merge recover --chain-id {current['chain_id']}",
                        chain=current,
                    )
                if current_containment == "older" and not current_inactive:
                    raise chain_core._merge_refusal(
                        V2ReasonCode.STATE_PRECONDITION,
                        "forge: merge abort refused — an older attempted HEAD is contained",
                        expected="historical landing reconciliation",
                        observed="newest attempted HEAD uncontained",
                        remediation=f"forge merge recover --chain-id {current['chain_id']}",
                        chain=current,
                    )
                if (
                    engine._merge_has_attempt(current)
                    and not current_inactive
                    and current_containment != "all-false"
                ):
                    raise chain_core._merge_refusal(
                        V2ReasonCode.STATE_PRECONDITION,
                        "forge: merge abort refused — attempted heads lack authoritative all-false containment",
                        expected="fresh all-false attempted-head containment",
                        observed=current_containment,
                        remediation=f"forge merge recover --chain-id {current['chain_id']}",
                        chain=current,
                    )
                if current != state:
                    raise chain_core._merge_refusal(
                        V2ReasonCode.STATE_PRECONDITION,
                        "forge: merge abort refused — merge state changed before release",
                        expected=str(state["last_event_at"]),
                        observed=str(current["last_event_at"]),
                        chain=current,
                    )
                if engine._merge_has_attempt(current):
                    prior_observation = self._tail_event_digest(
                        current, "push_observed"
                    )
                    current = self._run_remote_observation(
                        current,
                        common_lock,
                        lease,
                        engine._MergeEpochBudget(),
                        phase="post-push",
                        allow_inactive_observation=True,
                    )
                    fresh_observation = self._tail_event_digest(
                        current, "push_observed"
                    )
                    current_containment, _current_vector = chain_core._merge_containment(
                        current
                    )
                    if fresh_observation == prior_observation:
                        raise FrozenError(
                            "merge abort did not retain a fresh remote observation",
                            chain_id=str(current["chain_id"]),
                            schema=REVISION9_OUTPUT_SCHEMA,
                        )
                    if current_containment == "current":
                        raise chain_core._merge_refusal(
                            V2ReasonCode.STATE_PRECONDITION,
                            "forge: merge abort refused — current intended HEAD is already contained",
                            expected="pushed classification and cleanup",
                            observed="current intended HEAD contained",
                            remediation=(
                                f"forge merge cleanup --chain-id {current['chain_id']}"
                            ),
                            chain=current,
                        )
                    if current_containment == "older":
                        if engine._merge_inactive(current):
                            current = self._release_historical_landing_locked(
                                current,
                                common_lock,
                                lease,
                                observation_event_digest=fresh_observation,
                            )
                            terminal_disposition = "historical-landed-superseded"
                        else:
                            raise chain_core._merge_refusal(
                                V2ReasonCode.STATE_PRECONDITION,
                                "forge: merge abort refused — an older attempted HEAD is contained",
                                expected="historical landing reconciliation",
                                observed="newest attempted HEAD uncontained",
                                remediation=(
                                    f"forge merge finalize --chain-id {current['chain_id']}"
                                ),
                                chain=current,
                            )
                    elif current_containment == "all-false":
                        assert fresh_observation is not None
                        preconditions = (
                            self._attempted_release_preconditions_locked(
                                current,
                                common_lock,
                                expected_containment="all-false",
                                observation_event_digest=fresh_observation,
                                terminal_disposition="ordinary",
                            )
                        )
                        current = self._release_to_aborted_locked(
                            current,
                            lease,
                            reason=reason,
                            terminal_preconditions=preconditions,
                        )
                    else:
                        raise chain_core._merge_refusal(
                            V2ReasonCode.STATE_PRECONDITION,
                            "forge: merge abort refused — attempted heads lack authoritative all-false containment",
                            expected="fresh all-false attempted-head containment",
                            observed=current_containment,
                            remediation=(
                                f"forge merge recover --chain-id {current['chain_id']}"
                            ),
                            chain=current,
                        )
                else:
                    if engine._merge_process_unresolved(
                        current, allow_current_abort_lock=True
                    ):
                        raise chain_core._merge_refusal(
                            V2ReasonCode.STATE_PRECONDITION,
                            "forge: merge abort refused — a live or unresolved process remains",
                            expected="no live or unresolved fence/process",
                            observed="repository mutation ownership is unresolved",
                            remediation=(
                                f"forge merge recover --chain-id {current['chain_id']}"
                            ),
                            chain=current,
                        )
                    current = self._release_to_aborted_locked(
                        current, lease, reason=reason
                    )
                state = current
        next_step = (
            f"forge merge start --worktree {state['worktree']['path']}"
            if terminal_disposition == "historical-landed-superseded"
            else "none — merge chain aborted"
        )
        return engine._success(
            state,
            f"merge chain {state['chain_id']} aborted",
            next_step,
        )

    def status(self) -> Outcome:
        state = self._load()
        claim = state.get("worktree", {}).get("claim")
        if isinstance(claim, Mapping) and claim.get("status") == "unpublished":
            next_step = (
                f"forge merge abort --chain-id {state['chain_id']}"
                if engine._merge_unpublished_claim_absent(state, self.store)
                else f"forge merge recover --chain-id {state['chain_id']}"
            )
        elif isinstance(claim, Mapping) and claim.get("status") in {
            "releasing",
            "released",
        } and state["state"] not in {"closed", "aborted"}:
            next_step = f"forge merge recover --chain-id {state['chain_id']}"
        else:
            candidate = state.get("candidate")
            candidate_head = (
                candidate.get("candidate_head")
                if isinstance(candidate, Mapping)
                else "<unavailable>"
            )
            next_steps = {
                "classifying": f"forge merge refresh --chain-id {state['chain_id']}",
                "verifying": f"forge merge verify --chain-id {state['chain_id']}",
                "reviewing": f"forge review request --chain-id {state['chain_id']}",
                "revising": f"forge merge refresh --chain-id {state['chain_id']}",
                "awaiting_approval": (
                    "forge merge approve --candidate "
                    f"{candidate_head} "
                    f"--chain-id {state['chain_id']}"
                ),
                "authorized": f"forge merge finalize --chain-id {state['chain_id']}",
                "rebasing": f"forge merge recover --chain-id {state['chain_id']}",
                "rebase_conflict": f"forge merge recover --chain-id {state['chain_id']}",
                "reverifying": f"forge merge verify --chain-id {state['chain_id']}",
                "reverification_failed": f"forge merge recover --chain-id {state['chain_id']}",
                "pushing": f"forge merge recover --chain-id {state['chain_id']}",
                "pushed": f"forge merge cleanup --chain-id {state['chain_id']}",
                "cleanup_pending": f"forge merge cleanup --chain-id {state['chain_id']}",
                "closed": "none — merge chain closed",
                "aborted": "none — merge chain aborted",
            }
            next_step = next_steps[str(state["state"])]
        return engine._success(
            state,
            f"merge chain {state['chain_id']} is {state['state']}",
            next_step,
        )

    @staticmethod
    def _wrong_state(
        state: Mapping[str, Any], expected: str, verb: str
    ) -> None:
        raise chain_core._merge_refusal(
            V2ReasonCode.STATE_PRECONDITION,
            f"forge: {verb} refused — merge transition is not admitted",
            expected=expected,
            observed=str(state.get("state")),
            remediation=f"forge status --chain-id {state['chain_id']}",
            chain=state,
        )

    def _resolve_gate(
        self,
        state: Mapping[str, Any],
        policy: Policy,
        changed_paths: Sequence[str],
        gate_id: str,
    ) -> tuple[list[str], list[str], dict[str, Any]]:
        if gate_id == "gate-1":
            return (
                ["bash", "-c", policy.gate1, "forge", *changed_paths],
                [],
                {"kind": "gate-1"},
            )
        if gate_id.startswith("stack:"):
            category = gate_id.partition(":")[2]
            if category not in state.get("tier", {}).get("categories", []):
                self._wrong_state(state, "an applicable stack category", f"merge gate run {gate_id}")
            return (
                ["bash", "-c", policy.stack_commands[0], "forge", *changed_paths],
                list(policy.stack_commands[1:]),
                {"kind": "stack", "category": category},
            )
        if gate_id.startswith("invariant:"):
            suffix = gate_id.partition(":")[2]
            if re.fullmatch(r"[1-9][0-9]*", suffix) is None:
                self._wrong_state(state, "a canonical merge invariant ID", f"merge gate run {gate_id}")
            row_number = int(suffix)
            rows = [
                row
                for row in policy.invariants
                if row["row_number"] == row_number
                and row["enforcement"] == "merge"
            ]
            if len(rows) != 1:
                self._wrong_state(state, "a configured merge invariant", f"merge gate run {gate_id}")
            row = rows[0]
            return (
                ["bash", "-c", str(row["command"]), "forge", *changed_paths],
                [],
                {
                    "kind": "invariant",
                    "invariant": row["invariant"],
                    "row_number": row_number,
                },
            )
        if gate_id == "assertion-sensor":
            test_paths = [
                path
                for path in changed_paths
                if (
                    "tests/" in path.replace("\\", "/")
                    or Path(path).name.lower().startswith("test_")
                    or Path(path).name.lower().endswith("_test.py")
                    or ".test." in Path(path).name.lower()
                    or ".spec." in Path(path).name.lower()
                )
            ]
            return (
                [
                    sys.executable,
                    str(self.ctx.helper("check-test-quality.py")),
                    "--",
                    *test_paths,
                ],
                [],
                {"kind": "assertion-sensor", "test_paths": test_paths},
            )
        self._wrong_state(state, "the next canonical merge gate ID", f"merge gate run {gate_id}")
        raise AssertionError("unreachable")

    def _run_scoped_mutation(
        self,
        state: Mapping[str, Any],
        repository: chain_core.Repository,
    ) -> dict[str, Any]:
        candidate = state["candidate"]
        argv = [
            sys.executable,
            str(self.ctx.helper("run-scoped-mutation.py")),
            "--base",
            str(candidate["remote_tip"]),
            "--head",
            str(candidate["candidate_head"]),
        ]
        bound = engine._merge_run_directory(state)
        if bound is not None:
            _repository, run_dir = bound
            argv.extend(
                [
                    "--journal",
                    str(run_dir / "journal.jsonl"),
                    "--task",
                    str(state["run_binding"]["task_id"]),
                ]
            )
        environment = os.environ.copy()
        environment.pop("FORGE_SESSION_PID", None)
        try:
            process = runtime.run_bounded(
                argv,
                cwd=repository.root,
                env=environment,
                timeout=runtime.COMMAND_TIMEOUT_SECONDS,
                cap=runtime.OUTPUT_CAP_BYTES,
                verbose=self.ctx.options.verbose,
            )
        except OSError as exc:
            output = chain_core.canonical_bytes(
                {
                    "type": "mutation_evidence",
                    "criterion": "mutation: policy",
                    "result": "inconclusive",
                    "check": "scoped mutation runner",
                    "observation": (
                        "tool=mutation-testing runner; scope=policy; "
                        f"outcome=unavailable; diagnostic={exc}"
                    ),
                }
            ) + b"\n"
            process = runtime.ProcessResult(
                argv=argv,
                returncode=127,
                duration_seconds=0.0,
                output=output,
                output_digest=sha256_bytes(output),
            )
        _observe_current_merge_candidate(
            self.ctx, state, verb="merge scoped mutation"
        )
        transcript = engine._write_merge_artifact(
            self.ctx,
            state,
            f"evidence/scoped-mutation-{candidate['generation']}.log",
            process.output,
        )
        return {
            "criterion": "mutation: scoped",
            "result": (
                "passed"
                if process.returncode == 0
                and not process.timed_out
                and not process.output_limit
                else "inconclusive"
            ),
            "command_argv": list(argv),
            "exit_code": process.returncode,
            "duration_seconds": round(process.duration_seconds, 6),
            "stdout_stderr_digest": process.output_digest,
            "timed_out": process.timed_out,
            "output_limit": process.output_limit,
            "transcript": transcript,
        }

    def _record_gate_result(
        self,
        state: dict[str, Any],
        suite: Sequence[str],
        gate_id: str,
        argv: Sequence[str],
        process: runtime.ProcessResult,
        details: Mapping[str, Any],
    ) -> dict[str, Any]:
        candidate = state["candidate"]
        existing = state.get("steps", {}).get(gate_id)
        runs = copy.deepcopy(existing) if isinstance(existing, list) else []
        run_number = len(runs) + 1
        transcript_stem = re.sub(r"[^A-Za-z0-9_.-]+", "-", gate_id)
        transcript_parent = "evidence"
        if int(candidate["generation"]) > 1:
            transcript_parent += f"/generation-{candidate['generation']}"
        transcript = engine._write_merge_artifact(
            self.ctx,
            state,
            f"{transcript_parent}/{transcript_stem}-{run_number:02d}.log",
            process.output,
        )
        passed = (
            process.returncode == 0
            and not process.timed_out
            and not process.output_limit
        )
        fact = {
            "result": "passed" if passed else "failed",
            "generation_digest": candidate["generation_digest"],
            "criterion": (
                f"gate-1: {gate_id}"
                if gate_id == "gate-1"
                else f"gate-2: {gate_id}"
            ),
            "command_argv": list(argv),
            "exit_code": process.returncode,
            "duration_seconds": round(process.duration_seconds, 6),
            "stdout_stderr_digest": process.output_digest,
            "timed_out": process.timed_out,
            "output_limit": process.output_limit,
            "transcript": transcript,
            **copy.deepcopy(dict(details)),
        }
        runs.append(fact)
        steps = copy.deepcopy(state["steps"])
        steps[gate_id] = runs
        projected = copy.deepcopy(state)
        projected["steps"] = steps
        delta: dict[str, Any] = {"steps": steps}
        if passed and all(
            engine._merge_gate_current(projected, required) for required in suite
        ):
            delta["state"] = "reviewing"
        return self.store.transition(
            state,
            "gate_recorded",
            {"delta": delta},
            generation_digest=str(candidate["generation_digest"]),
            at=chain_core.iso_z(),
        )

    def gate_run(self, gate_id: str) -> Outcome:
        chain_core._require_merge_adapter_control("ordered-gate-suite")
        state = self._preflight_lifecycle(
            self._load(), f"merge gate run {gate_id}"
        )
        self._halt(state)
        if state["state"] != "verifying":
            self._wrong_state(state, "verifying", f"merge gate run {gate_id}")
        repository, policy, changed_paths = _observe_current_merge_candidate(
            self.ctx, state, verb=f"merge gate run {gate_id}"
        )
        suite = engine._merge_gate_suite(state, policy)
        next_gate = next(
            (name for name in suite if not engine._merge_gate_current(state, name)),
            None,
        )
        if gate_id != next_gate:
            self._wrong_state(
                state,
                f"next incomplete gate {next_gate or 'none'}",
                f"merge gate run {gate_id}",
            )
        argv, remaining, details = self._resolve_gate(
            state, policy, changed_paths, gate_id
        )
        environment = os.environ.copy()
        environment.pop("FORGE_SESSION_PID", None)
        batch_id = (
            secrets.token_hex(8)
            if details.get("kind") == "stack"
            else None
        )
        cells = [argv, *(
            ["bash", "-c", cell, "forge", *changed_paths]
            for cell in remaining
        )]
        evidence_refs: list[str] = []
        for cell_index, cell_argv in enumerate(cells, 1):
            if gate_id == "assertion-sensor" and not details["test_paths"]:
                output = b"forge: no touched test files - assertion sensor not applicable\n"
                process = runtime.ProcessResult(
                    argv=list(cell_argv),
                    returncode=0,
                    duration_seconds=0.0,
                    output=output,
                    output_digest=sha256_bytes(output),
                )
                cell_details = {**details, "not_applicable": True}
            else:
                try:
                    process = runtime.run_bounded(
                        cell_argv,
                        cwd=repository.root,
                        env=environment,
                        timeout=runtime.COMMAND_TIMEOUT_SECONDS,
                        cap=runtime.OUTPUT_CAP_BYTES,
                        verbose=self.ctx.options.verbose,
                    )
                except OSError as exc:
                    output = f"forge: merge gate launch failed: {exc}\n".encode(
                        "utf-8", "replace"
                    )
                    process = runtime.ProcessResult(
                        argv=list(cell_argv),
                        returncode=127,
                        duration_seconds=0.0,
                        output=output,
                        output_digest=sha256_bytes(output),
                    )
                cell_details = dict(details)
            _observe_current_merge_candidate(
                self.ctx, state, verb=f"merge gate run {gate_id}"
            )
            if batch_id is not None:
                cell_details.update(
                    {
                        "batch_id": batch_id,
                        "cell_index": cell_index,
                        "cell_count": len(cells),
                    }
                )
            if gate_id == "gate-1" and (
                process.returncode == 0
                and not process.timed_out
                and not process.output_limit
            ):
                cell_details["scoped_mutation"] = self._run_scoped_mutation(
                    state, repository
                )
            state = self._record_gate_result(
                state,
                suite,
                gate_id,
                cell_argv,
                process,
                cell_details,
            )
            current_fact = state["steps"][gate_id][-1]
            evidence_refs.append(str(current_fact["transcript"]))
            if current_fact["result"] != "passed":
                if details.get("kind") == "invariant":
                    diagnostic = (
                        f"forge: invariant timed out (merge): {details['invariant']}"
                        if process.timed_out
                        else f"forge: invariant failed (merge): {details['invariant']}"
                    )
                else:
                    diagnostic = f"forge: merge gate failed — {gate_id}"
                raise chain_core._merge_refusal(
                    V2ReasonCode.MERGE_GATE_FAILED,
                    diagnostic,
                    expected="exit 0 within 1200 seconds and 65536 output bytes",
                    observed=(
                        f"exit={process.returncode}, timeout={process.timed_out}, "
                        f"output_limit={process.output_limit}"
                    ),
                    remediation=f"forge merge gate run {gate_id} --chain-id {state['chain_id']}",
                    chain=state,
                    evidence_refs=evidence_refs,
                )
        return engine._success(
            state,
            f"merge gate {gate_id} passed",
            (
                f"forge review request --chain-id {state['chain_id']}"
                if state["state"] == "reviewing"
                else f"forge merge verify --chain-id {state['chain_id']}"
            ),
            evidence_refs=evidence_refs,
        )

    def verify(self) -> Outcome:
        chain_core._require_merge_adapter_control("ordered-gate-suite")
        state = self._preflight_lifecycle(self._load(), "merge verify")
        repository, policy, _changed_paths = _observe_current_merge_candidate(
            self.ctx, state, verb="merge verify"
        )
        del repository
        suite = engine._merge_gate_suite(state, policy)
        if state["state"] == "reviewing" and all(
            engine._merge_gate_current(state, gate_id) for gate_id in suite
        ):
            return engine._success(
                state,
                "merge mechanical verification already complete; no-op",
                f"forge review request --chain-id {state['chain_id']}",
            )
        if state["state"] != "verifying":
            self._wrong_state(state, "verifying", "merge verify")
        while state["state"] == "verifying":
            next_gate = next(
                (name for name in suite if not engine._merge_gate_current(state, name)),
                None,
            )
            if next_gate is None:
                raise FrozenError(
                    "complete merge gate tuple did not enter reviewing",
                    chain_id=str(state["chain_id"]),
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            self.gate_run(next_gate)
            state = self._load()
        return engine._success(
            state,
            "all required merge mechanical gates are complete",
            f"forge review request --chain-id {state['chain_id']}",
        )

    def _review_package(
        self,
        state: Mapping[str, Any],
        repository: chain_core.Repository,
        policy: Policy,
        changed_paths: Sequence[str],
    ) -> tuple[bytes, list[str], dict[str, list[str]]]:
        chain_core._require_merge_adapter_control("mandatory-review-final")
        profiles_by_path = {
            path: engine.Engine._profiles_for_path(path) for path in changed_paths
        }
        profiles = sorted(
            {
                profile
                for selected in profiles_by_path.values()
                for profile in selected
            }
        )
        constitution_path = self.ctx.plugin_root() / "rules" / "review-constitution.md"
        role_path = self.ctx.plugin_root() / "agents" / "review-final.md"
        try:
            constitution = constitution_path.read_bytes()
            role = role_path.read_bytes()
        except OSError as exc:
            raise chain_core._merge_refusal(
                V2ReasonCode.EVIDENCE_INCOMPLETE,
                f"forge: review refused — reviewer doctrine is unavailable: {exc}",
                observed=str(exc),
                chain=state,
            ) from exc
        gotchas_result = repository.git(
            ["show", f"{policy.sha}:.forge/history/gotchas.md"], check=False
        )
        gotchas = gotchas_result.stdout if gotchas_result.returncode == 0 else b""
        candidate = state["candidate"]
        header = (
            "FORGE MERGE REVIEW MASTER PACKAGE v1\n"
            f"candidate: {candidate['candidate_head']}\n"
            f"generation: {candidate['generation_digest']}\n"
            f"base: {candidate['remote_tip']}\n"
            f"target: {chain_core.canonical_bytes(state['target']).decode('utf-8')}\n"
            "reviewer: review-final\n"
            f"profiles: {','.join(profiles)}\n"
            f"profile-map: {chain_core.canonical_bytes(profiles_by_path).decode('utf-8')}\n"
        ).encode("utf-8")
        control = (
            b"\n--- BEGIN CONTROLLING REVIEW POLICY ---\n"
            + role
            + b"\n--- review constitution ---\n"
            + constitution
            + (
                "\n--- committed agent-project-context ---\n"
                f"{policy.regions['agent-project-context']}"
                "\n--- committed review-prompt-project-focus ---\n"
                f"{policy.regions['review-prompt-project-focus']}"
                "\n--- committed project-triggers ---\n"
                f"{policy.regions['project-triggers']}"
                "\n--- committed completeness-project-items ---\n"
                f"{policy.regions['completeness-project-items']}"
                "\n--- committed gotchas ---\n"
            ).encode("utf-8")
            + gotchas
            + b"\n--- END CONTROLLING REVIEW POLICY ---\n"
        )
        mutation_evidence = [
            fact.get("scoped_mutation")
            for facts in state.get("steps", {}).values()
            if isinstance(facts, list)
            for fact in facts
            if isinstance(fact, dict) and isinstance(fact.get("scoped_mutation"), dict)
        ]
        try:
            diff = repository.git(
                [
                    "diff",
                    f"{candidate['remote_tip']}...{candidate['candidate_head']}",
                ]
            ).stdout
        except OSError as exc:
            raise chain_core._merge_refusal(
                V2ReasonCode.EVIDENCE_INCOMPLETE,
                "forge: review request refused — authoritative candidate diff is unavailable",
                expected="the complete fixed-generation three-dot diff",
                observed=str(exc),
                chain=state,
            ) from exc
        package = (
            header
            + control
            + b"\n--- BEGIN ADVISORY MUTATION EVIDENCE ---\n"
            + chain_core.canonical_bytes(mutation_evidence)
            + b"\n--- END ADVISORY MUTATION EVIDENCE ---\n"
            + b"\n--- BEGIN UNTRUSTED CANDIDATE DIFF ---\n"
            + diff
            + b"\n--- END UNTRUSTED CANDIDATE DIFF ---\n"
        )
        return package, profiles, profiles_by_path

    def review_request(self) -> Outcome:
        chain_core._require_merge_adapter_control("mandatory-review-final")
        state = self._preflight_lifecycle(self._load(), "review request")
        self._halt(state)
        review = state.get("review")
        prior_iteration = (
            review.get("iteration", 0) if isinstance(review, Mapping) else 0
        )
        if type(prior_iteration) is not int:
            raise FrozenError(
                "merge review iteration is malformed",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        if state["state"] in {"reviewing", "revising"} and prior_iteration >= 8:
            raise chain_core._merge_refusal(
                V2ReasonCode.ITERATION_CAP,
                "review iteration cap of 8 reached; no further merge review is admitted",
                expected="PASS before iteration 8",
                observed=str(prior_iteration),
                chain=state,
            )
        if state["state"] != "reviewing":
            self._wrong_state(state, "reviewing", "review request")
        repository, policy, changed_paths = _observe_current_merge_candidate(
            self.ctx, state, verb="review request"
        )
        suite = engine._merge_gate_suite(state, policy)
        if not all(engine._merge_gate_current(state, gate_id) for gate_id in suite):
            raise chain_core._merge_refusal(
                V2ReasonCode.EVIDENCE_INCOMPLETE,
                "forge: review request refused — merge mechanical evidence is incomplete",
                expected="every current-generation merge gate PASS",
                chain=state,
            )
        if not isinstance(review, dict) or "request" in review:
            self._wrong_state(state, "no outstanding review request", "review request")
        package, profiles, profile_map = self._review_package(
            state, repository, policy, changed_paths
        )
        iteration = prior_iteration + 1
        package_digest = sha256_bytes(package)
        if len(package) > runtime.OUTPUT_CAP_BYTES:
            bound = engine._merge_run_directory(state)
            package_ref = (
                (
                    Path("captured")
                    / "sha256"
                    / package_digest
                    / "state.json"
                ).as_posix()
                if bound is not None
                else (
                    Path(".forge")
                    / "chains"
                    / str(state["chain_id"])
                    / "review"
                    / f"iteration-{iteration:02d}"
                    / "master-package.txt"
                ).as_posix()
            )
            raise chain_core._merge_refusal(
                V2ReasonCode.EVIDENCE_INCOMPLETE,
                "forge: review refused — reviewer cannot inspect the complete authoritative package",
                expected="one reviewer inspecting every master-package byte through verified bounded windows",
                observed=f"master bytes={len(package)}; bounded-window adapter not active",
                remediation="escalate for the bounded-window review transport adapter",
                chain=state,
                evidence_refs=[package_ref],
            )
        package_ref = engine._write_merge_artifact(
            self.ctx,
            state,
            f"review/iteration-{iteration:02d}/master-package.txt",
            package,
            master_package=True,
        )
        request = {
            "candidate": state["candidate"]["candidate_head"],
            "package": package_ref,
            "package_digest": package_digest,
            "reviewer": "review-final",
            "iteration": iteration,
            "requested_at": chain_core.iso_z(),
            "generation_digest": state["candidate"]["generation_digest"],
            "target": copy.deepcopy(state["target"]),
            "profiles": profiles,
            "profile_map": profile_map,
            "byte_length": len(package),
            "invocation": (
                "spawn one review-final with master package "
                f"{package_ref} candidate {state['candidate']['candidate_head']} "
                f"generation {state['candidate']['generation_digest']} "
                f"target {state['target']['destination_ref']} digest {package_digest}"
            ),
        }
        current = self.store.transition(
            state,
            "review_requested",
            {"delta": {"review": {"iteration": iteration, "request": request}}},
            generation_digest=str(state["candidate"]["generation_digest"]),
            at=chain_core.iso_z(),
        )
        return engine._success(
            current,
            (
                f"review-final package={package_ref} digest={package_digest}; "
                f"invocation={request['invocation']}"
            ),
            f"forge review attach --verdict-file <path> --chain-id {state['chain_id']}",
            evidence_refs=[package_ref],
        )

    def review_collect(self) -> Outcome:
        state = self._preflight_lifecycle(self._load(), "review collect")
        if state["state"] != "reviewing":
            self._wrong_state(state, "reviewing", "review collect")
        raise chain_core._merge_refusal(
            V2ReasonCode.SKIP_NOT_PERMITTED,
            "forge: review collect refused — merge review-final cannot be skipped or replaced",
            expected="review attach for the mandatory review-final package",
            remediation=f"forge review attach --verdict-file <path> --chain-id {state['chain_id']}",
            chain=state,
        )

    def review_attach(self, verdict_file: str) -> Outcome:
        chain_core._require_merge_adapter_control("mandatory-review-final")
        state = self._preflight_lifecycle(self._load(), "review attach")
        self._halt(state)
        review = state.get("review")
        iteration = review.get("iteration", 0) if isinstance(review, Mapping) else 0
        if type(iteration) is not int:
            raise FrozenError(
                "merge review iteration is malformed",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        request = review.get("request") if isinstance(review, Mapping) else None
        eighth_request_pending = bool(
            state["state"] == "reviewing"
            and iteration == 8
            and isinstance(review, Mapping)
            and set(review) == {"iteration", "request"}
            and isinstance(request, Mapping)
            and request.get("iteration") == 8
        )
        if (
            state["state"] in {"reviewing", "revising"}
            and iteration >= 8
            and not eighth_request_pending
        ):
            raise chain_core._merge_refusal(
                V2ReasonCode.ITERATION_CAP,
                "forge: review attach refused — review iteration cap of 8 is final",
                expected="status or safe abort after the eighth review cycle",
                observed=str(iteration),
                chain=state,
            )
        if state["state"] != "reviewing":
            self._wrong_state(state, "reviewing", "review attach")
        _repository, _policy, changed_paths = _observe_current_merge_candidate(
            self.ctx, state, verb="review attach"
        )
        if (
            not isinstance(request, dict)
            or request.get("reviewer") != "review-final"
        ):
            self._wrong_state(state, "a current review-final request", "review attach")
        engine._read_merge_artifact(
            self.ctx,
            state,
            str(request["package"]),
            str(request["package_digest"]),
            "review master package",
        )
        source = Path(verdict_file)
        if not source.is_absolute():
            source = Path.cwd() / source
        descriptor: int | None = None
        try:
            descriptor = os.open(
                source,
                os.O_RDONLY
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NONBLOCK", 0),
            )
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode) or opened.st_uid != os.geteuid():
                raise OSError("verdict is not an owner-controlled regular file")
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = os.read(descriptor, runtime.OUTPUT_CAP_BYTES + 1 - total)
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > runtime.OUTPUT_CAP_BYTES:
                    raise OSError(f"verdict exceeds {runtime.OUTPUT_CAP_BYTES} bytes")
            data = b"".join(chunks)
        except OSError as exc:
            raise chain_core._merge_refusal(
                V2ReasonCode.REVIEW_VERDICT_INVALID,
                f"review-final verdict is unreadable: {exc}",
                observed=str(source),
                chain=state,
            ) from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
        try:
            verdict = engine.Engine._parse_verdict(
                data,
                str(state["candidate"]["candidate_head"]),
                str(request["package_digest"]),
            )
        except ValueError as exc:
            raise chain_core._merge_refusal(
                V2ReasonCode.REVIEW_VERDICT_INVALID,
                f"review-final verdict is invalid: {exc}",
                expected="VERDICT plus exact candidate and master-package citations",
                observed=str(exc),
                chain=state,
            ) from exc
        verdict_ref = engine._write_merge_artifact(
            self.ctx,
            state,
            f"review/iteration-{review['iteration']:02d}/verdict.txt",
            data,
        )
        verdict.update(
            {
                "reviewer_role": "review-final",
                "iteration": review["iteration"],
                "recorded_at": chain_core.iso_z(),
                "verdict_path": verdict_ref,
            }
        )
        current_review = {**copy.deepcopy(review), "verdict": verdict}
        delta: dict[str, Any] = {"review": current_review}
        if verdict["verdict"] == "BLOCK":
            delta["state"] = "revising"
            if int(review["iteration"]) == 8:
                current_review["residual_risk"] = {
                    "at": chain_core.iso_z(),
                    "reason": "review iteration cap reached",
                    "findings": copy.deepcopy(verdict["findings"]),
                }
        else:
            control_paths = list(changed_paths) if state["tier"]["control"] else []
            delta["authorization"] = {
                "candidate_head": state["candidate"]["candidate_head"],
                "generation_digest": state["candidate"]["generation_digest"],
                "diff_summary": (
                    f"{len(changed_paths)} changed path(s); "
                    f"diff_sha256={state['candidate']['diff_sha256']}"
                ),
                "control_paths": control_paths,
                "review_verdict": "PASS",
                "recorded_at": chain_core.iso_z(),
            }
            delta["state"] = (
                "awaiting_approval"
                if state["tier"]["control"]
                else "authorized"
            )
        current = self.store.transition(
            state,
            "review_attached",
            {"delta": delta},
            generation_digest=str(state["candidate"]["generation_digest"]),
            at=chain_core.iso_z(),
        )
        return engine._success(
            current,
            f"merge review {verdict['verdict']} recorded",
            f"forge status --chain-id {state['chain_id']}",
            evidence_refs=[verdict_ref],
        )

    def review_disposition(
        self, finding: int, severity: str, resolution: str
    ) -> Outcome:
        chain_core._require_merge_adapter_control("mandatory-review-final")
        state = self._preflight_lifecycle(self._load(), "review disposition")
        self._halt(state)

        def validated_review(current: dict[str, Any]) -> tuple[dict[str, Any], bool]:
            if current["state"] not in {"reviewing", "revising"}:
                self._wrong_state(
                    current, "reviewing or revising", "review disposition"
                )
            selected_review = current.get("review")
            iteration = (
                selected_review.get("iteration", 0)
                if isinstance(selected_review, Mapping)
                else 0
            )
            if type(iteration) is not int:
                raise FrozenError(
                    "merge review iteration is malformed",
                    chain_id=str(current["chain_id"]),
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            if iteration >= 8:
                raise chain_core._merge_refusal(
                    V2ReasonCode.ITERATION_CAP,
                    "forge: review disposition refused — review iteration cap of 8 is final",
                    expected="status or safe abort after the eighth review cycle",
                    observed=str(iteration),
                    chain=current,
                )
            verdict = (
                selected_review.get("verdict")
                if isinstance(selected_review, dict)
                else None
            )
            findings = verdict.get("findings") if isinstance(verdict, dict) else None
            if (
                not isinstance(findings, list)
                or finding < 1
                or finding > len(findings)
            ):
                self._wrong_state(
                    current, "an attached finding number", "review disposition"
                )
            selected = findings[finding - 1]
            expected_severity = (
                str(selected.get("severity")) if isinstance(selected, dict) else ""
            )
            if severity != expected_severity:
                raise chain_core._merge_refusal(
                    V2ReasonCode.STATE_PRECONDITION,
                    "forge: review disposition refused — severity does not match the finding",
                    expected=expected_severity,
                    observed=severity,
                    chain=current,
                )
            if not isinstance(resolution, str) or not resolution.strip():
                raise chain_core._merge_refusal(
                    V2ReasonCode.STATE_PRECONDITION,
                    "forge: review disposition refused — resolution must be nonempty",
                    observed=resolution,
                    chain=current,
                )
            if not isinstance(selected_review, dict):
                raise FrozenError(
                    "merge review dispositions are malformed",
                    chain_id=str(current["chain_id"]),
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            return selected_review, severity in {"CRITICAL", "MAJOR"}

        # Validate once before waiting, then repeat from the lease-protected
        # state so concurrent MINOR submissions serialize and two competing
        # above-MINOR submissions cannot both observe an empty slot.
        validated_review(state)
        binding = state.get("run_binding")
        with self.store._journal_outer(
            binding if isinstance(binding, Mapping) else None
        ):
            with chain_core.acquire_chain_lease(
                self.store.root,
                chain_id=str(state["chain_id"]),
                session=self.store._session(None),
            ) as lease:
                fresh = self.store.load_locked(
                    str(state["chain_id"]), lease=lease
                )
                fresh = self._preflight_lifecycle(
                    fresh, "review disposition", persist_missing=False
                )
                fresh_review, above_minor = validated_review(fresh)
                slot_occupied = (
                    fresh_review.get("operator_cosign_required") is True
                )
                if above_minor and slot_occupied:
                    raise chain_core._merge_refusal(
                        V2ReasonCode.STATE_PRECONDITION,
                        "forge: review disposition refused — above-MINOR disposition already awaits operator co-sign",
                        expected="zero outstanding above-MINOR dispositions",
                        observed="one outstanding above-MINOR disposition",
                        chain=fresh,
                    )
                dispositions = copy.deepcopy(
                    fresh_review.get("dispositions", [])
                )
                if not isinstance(dispositions, list):
                    raise FrozenError(
                        "merge review dispositions are malformed",
                        chain_id=str(fresh["chain_id"]),
                        schema=REVISION9_OUTPUT_SCHEMA,
                    )
                recorded_at = chain_core.iso_z()
                dispositions.append(
                    {
                        "finding": finding,
                        "severity": severity,
                        "resolution": resolution.strip(),
                        "candidate": fresh["candidate"]["candidate_head"],
                        "generation_digest": fresh["candidate"][
                            "generation_digest"
                        ],
                        "recorded_at": recorded_at,
                    }
                )
                current_review = {
                    **copy.deepcopy(fresh_review),
                    "dispositions": dispositions,
                    "operator_cosign_required": slot_occupied or above_minor,
                }
                current = self.store.transition_locked(
                    fresh,
                    "review_disposition",
                    {"delta": {"review": current_review}},
                    generation_digest=str(
                        fresh["candidate"]["generation_digest"]
                    ),
                    lease=lease,
                    at=recorded_at,
                )
        if above_minor:
            raise chain_core._merge_refusal(
                V2ReasonCode.APPROVAL_REQUIRED,
                "above-MINOR disposition is parked pending operator co-sign",
                expected="merge approve for the sole outstanding disposition",
                observed=severity,
                chain=current,
            )
        return engine._success(
            current,
            f"merge finding {finding} disposition recorded",
            f"forge status --chain-id {state['chain_id']}",
        )

    def _epoch_transition(
        self,
        state: dict[str, Any],
        lease: chain_core.ChainLease,
        event_name: str,
        payload: Mapping[str, Any],
        *,
        generation_digest: str | None = None,
        at: str | None = None,
    ) -> dict[str, Any]:
        generation = state.get("candidate")
        selected = (
            generation_digest
            if generation_digest is not None
            else str(generation["generation_digest"])
            if isinstance(generation, Mapping)
            else None
        )
        return self.store.transition_locked(
            state,
            event_name,
            payload,
            generation_digest=selected,
            lease=lease,
            at=at or chain_core.iso_z(),
        )

    def _tail_event_digest(
        self, state: Mapping[str, Any], event_name: str
    ) -> str:
        digest = engine._merge_event_digest(
            self.store, str(state["chain_id"]), event_name
        )
        if digest is None:
            raise FrozenError(
                f"merge {event_name} event digest is unavailable",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        return digest

    @staticmethod
    def _sealed_plan(
        state: Mapping[str, Any], policy: Policy, suite: Sequence[Mapping[str, str]]
    ) -> dict[str, Any]:
        chain_core._require_merge_integration_control("sealed-gate-plan")
        candidate = state["candidate"]
        canonical_suite = [copy.deepcopy(dict(member)) for member in suite]
        return {
            "status": "sealed",
            "generation_digest": candidate["generation_digest"],
            "policy_digest": policy.digest,
            "suite": canonical_suite,
            "suite_digest": sha256_bytes(chain_core.canonical_bytes(canonical_suite)),
            "cursor": 0,
            "seal_event_digest": None,
        }

    def _begin_epoch(
        self,
        state: dict[str, Any],
        lease: chain_core.ChainLease,
        *,
        retry: bool = False,
        observed_policy: Policy | None = None,
    ) -> dict[str, Any]:
        candidate = state.get("candidate")
        if not isinstance(candidate, Mapping):
            raise FrozenError(
                "merge epoch lacks a candidate generation",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        integration = copy.deepcopy(state["integration"])
        if retry:
            if observed_policy is None:
                raise FrozenError(
                    "merge retry epoch lacks its durable candidate observation",
                    chain_id=str(state["chain_id"]),
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            policy = observed_policy
            plan = self._sealed_plan(state, policy, engine._merge_epoch_suite(state, policy))
        else:
            plan = {
                "status": "unsealed",
                "generation_digest": None,
                "policy_digest": None,
                "suite": None,
                "suite_digest": None,
                "cursor": None,
                "seal_event_digest": None,
            }
        integration.update(
            {
                "condition": "none",
                "primary_condition": "none",
                "epoch": {
                    "operation_nonce": secrets.token_hex(16),
                    "generation_digest": candidate["generation_digest"],
                    "intent_digest": None,
                    "started_at": chain_core.iso_z(),
                    "gate_plan": plan,
                },
                "observed": None,
            }
        )
        return self._epoch_transition(
            state,
            lease,
            "epoch_intent",
            {
                "delta": {
                    "state": "reverifying" if retry else "rebasing",
                    "integration": integration,
                }
            },
        )

    @staticmethod
    def _epoch_fetch_argv(state: Mapping[str, Any]) -> list[str]:
        return [
            "git",
            "--no-pager",
            "-C",
            str(state["worktree"]["path"]),
            "fetch",
            "--no-tags",
            "--quiet",
            "origin",
            str(state["target"]["destination_ref"]),
        ]

    def _epoch_replay_context(
        self, state: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Return context only from a replay matching the locked projection."""

        chain_id = str(state["chain_id"])
        with self.store.event_lock(chain_id):
            replay = self.store._read_replay_locked(chain_id)
        if replay.state != state:
            raise FrozenError(
                "merge epoch observation projection diverges from event replay",
                chain_id=chain_id,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        context = copy.deepcopy(replay.context)
        context["_authenticated_tail_event"] = (
            copy.deepcopy(replay.events[-1]) if replay.events else None
        )
        return context

    @staticmethod
    def _resolved_epoch_fetch_tip(state: Mapping[str, Any]) -> str:
        """Resolve the single fixed-target FETCH_HEAD without launching a child."""

        fetch_head = Path(str(state["worktree"]["git_dir"])) / "FETCH_HEAD"
        try:
            raw = fetch_head.read_bytes()
        except OSError as exc:
            raise ValueError(f"FETCH_HEAD is unavailable: {exc}") from exc
        if len(raw) > chain_core.MERGE_SCOPE_BINDING_CAP_BYTES or not raw.endswith(b"\n"):
            raise ValueError("FETCH_HEAD is malformed")
        rows = raw.splitlines()
        if len(rows) != 1:
            raise ValueError("FETCH_HEAD does not identify one fixed target")
        raw_oid = rows[0].split(b"\t", 1)[0]
        try:
            oid = raw_oid.decode("ascii")
        except UnicodeDecodeError as exc:
            raise ValueError("FETCH_HEAD object ID is not ASCII") from exc
        if chain_core.COMMIT_RE.fullmatch(oid) is None:
            raise ValueError("FETCH_HEAD object ID is invalid")
        return oid

    def _run_carried_successor_ancestry(
        self,
        state: dict[str, Any],
        fetched_tip: str,
        lock: chain_core.CommonRebaseLock,
        lease: chain_core.ChainLease,
        *,
        resume_intent: bool = False,
    ) -> tuple[dict[str, Any], bool | None]:
        """Fence or consume the carried-tip ancestry decision before sealing."""

        chain_core._require_merge_integration_control("successor-ancestry-observation")
        integration = state.get("integration")
        epoch = integration.get("epoch") if isinstance(integration, Mapping) else None
        plan = epoch.get("gate_plan") if isinstance(epoch, Mapping) else None
        candidate = state.get("candidate")
        authorization = state.get("authorization")
        source_intent = (
            integration.get("intent") if isinstance(integration, Mapping) else None
        )
        replay_context = self._epoch_replay_context(state)
        fetch_observation = replay_context.get("epoch_fetch_observation")
        candidate_observation = replay_context.get("candidate_observation")
        raw_evidence = (
            fetch_observation.get("evidence")
            if isinstance(fetch_observation, Mapping)
            else None
        )
        observation_evidence = (
            candidate_observation.get("evidence")
            if isinstance(candidate_observation, Mapping)
            else None
        )
        if (
            state.get("state") != "rebasing"
            or not isinstance(epoch, Mapping)
            or not isinstance(plan, Mapping)
            or plan.get("status") != "unsealed"
            or not isinstance(candidate, Mapping)
            or not isinstance(authorization, Mapping)
            or candidate.get("remote_tip") != fetched_tip
            or authorization.get("candidate_head") != candidate.get("candidate_head")
            or authorization.get("review_verdict") != "PASS"
            or authorization.get("generation_digest")
            == candidate.get("generation_digest")
            or not isinstance(fetch_observation, Mapping)
            or not isinstance(raw_evidence, Mapping)
            or not chain_core._epoch_fetch_observation_record_valid(state, raw_evidence)
            or not chain_core._epoch_fetch_observation_passed(raw_evidence)
            or fetch_observation.get("digest")
            != engine._merge_epoch_fetch_observation_digest(
                self.store, str(state["chain_id"]), raw_evidence
            )
            or not isinstance(candidate_observation, Mapping)
            or not chain_core._merge_candidate_observation_evidence_valid(
                state, observation_evidence
            )
            or candidate_observation.get("source_intent") != raw_evidence
            or candidate_observation.get("evidence_digest")
            != observation_evidence.get("evidence_digest")
            or observation_evidence.get("remote_tip") != fetched_tip
            or observation_evidence.get("expected_head")
            != candidate.get("candidate_head")
            or observation_evidence.get("classify") is not True
        ):
            raise FrozenError(
                "carried successor ancestry observation lacks its exact fetch binding",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        if resume_intent:
            if (
                not chain_core._epoch_ancestry_record_valid(state, source_intent)
                or not isinstance(source_intent, Mapping)
                or source_intent.get("phase") not in {"intent", "result"}
                or source_intent.get("fetch_observation_event_digest")
                != fetch_observation.get("digest")
                or source_intent.get("candidate_observation_digest")
                != candidate_observation.get("evidence_digest")
            ):
                raise FrozenError(
                    "interrupted carried successor ancestry intent is malformed",
                    chain_id=str(state["chain_id"]),
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            if source_intent.get("phase") == "result":
                replayed = replay_context.get("epoch_ancestry_observation")
                tail = replay_context.get("_authenticated_tail_event")
                recovery_bridge = replay_context.get(
                    "recovery_proof_bridge"
                )
                replayed_at_tail = bool(
                    isinstance(replayed, Mapping)
                    and isinstance(tail, Mapping)
                    and replayed.get("digest") == tail.get("digest")
                )
                replayed_before_recovery_proof = bool(
                    isinstance(replayed, Mapping)
                    and isinstance(tail, Mapping)
                    and isinstance(recovery_bridge, Mapping)
                    and tail.get("digest")
                    == recovery_bridge.get("event_digest")
                    and recovery_bridge.get("previous_digest")
                    == replayed.get("digest")
                    and (
                        recovery_bridge.get("operation") == "containment"
                        and recovery_bridge.get("intent_digest")
                        == source_intent.get("intent_event_digest")
                        and recovery_bridge.get("classification")
                        == "containment-result-persisted"
                        or recovery_bridge.get("operation") is None
                        and recovery_bridge.get("intent_digest") is None
                        and recovery_bridge.get("classification")
                        == "owner-death-only"
                    )
                )
                if (
                    not isinstance(replayed, Mapping)
                    or not (
                        replayed_at_tail or replayed_before_recovery_proof
                    )
                    or replayed.get("evidence") != source_intent
                ):
                    raise FrozenError(
                        "interrupted carried successor ancestry result is unauthenticated",
                        chain_id=str(state["chain_id"]),
                        schema=REVISION9_OUTPUT_SCHEMA,
                    )
                contained = source_intent.get("child_result", {}).get(
                    "contained"
                )
                return state, contained if type(contained) is bool else None
            ancestry_intent = copy.deepcopy(dict(source_intent))
            argv = list(ancestry_intent["argv"])
        else:
            if (
                not isinstance(source_intent, Mapping)
                or source_intent != raw_evidence
                or self._tail_event_digest(state, "condition_recorded")
                != candidate_observation.get("restore_event_digest")
            ):
                raise FrozenError(
                    "carried successor ancestry observation lacks its exact raw fetch result",
                    chain_id=str(state["chain_id"]),
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            argv = chain_core._remote_containment_argv(
                state, fetched_tip, str(candidate["candidate_head"])
            )
            ancestry_intent = {
                "schema": "forge-epoch-ancestry-intent/1",
                "chain_id": state["chain_id"],
                "epoch_intent_digest": epoch["intent_digest"],
                "operation_nonce": epoch["operation_nonce"],
                "generation_digest": candidate["generation_digest"],
                "fetch_observation_event_digest": fetch_observation["digest"],
                "candidate_observation_digest": candidate_observation[
                    "evidence_digest"
                ],
                "fetched_tip": fetched_tip,
                "candidate_head": candidate["candidate_head"],
                "argv": argv,
                "phase": "intent",
                "recorded_at": chain_core.iso_z(),
            }
        if not chain_core._epoch_ancestry_record_valid(state, ancestry_intent):
            raise FrozenError(
                "carried successor ancestry intent is malformed",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        if not resume_intent:
            next_integration = copy.deepcopy(state["integration"])
            next_integration["intent"] = ancestry_intent
            state = self._epoch_transition(
                state,
                lease,
                "condition_recorded",
                {"delta": {"integration": next_integration}},
            )
        ancestry_intent_digest = self._tail_event_digest(state, "condition_recorded")

        def intent_current() -> bool:
            try:
                fresh = self.store.load_locked(str(state["chain_id"]), lease=lease)
            except (FrozenError, OSError):
                return False
            return bool(
                fresh.get("state") == "rebasing"
                and fresh.get("integration", {}).get("intent") == ancestry_intent
                and self._tail_event_digest(fresh, "condition_recorded")
                == ancestry_intent_digest
            )

        def persist(result: chain_core.FencedProcessResult) -> None:
            nonlocal state
            ordinary = bool(
                result.authorized
                and type(result.returncode) is int
                and result.returncode in {0, 1}
                and not result.launch_failed
                and not result.timed_out
                and not result.output_limit
                and not result.group_survived
            )
            contained = result.returncode == 0 if ordinary else None
            result_intent = {
                **ancestry_intent,
                "phase": "result",
                "intent_event_digest": ancestry_intent_digest,
                "child_result": {
                    "authorized": result.authorized,
                    "exit": result.returncode,
                    "inflight_digest": result.fence_digest,
                    "output_digest": result.output_digest,
                    "launch_failed": result.launch_failed,
                    "timed_out": result.timed_out,
                    "output_limit_exceeded": result.output_limit,
                    "group_survived": result.group_survived,
                    "contained": contained,
                },
                "recorded_at": chain_core.iso_z(),
            }
            result_integration = copy.deepcopy(state["integration"])
            result_integration["intent"] = result_intent
            state = self._epoch_transition(
                state,
                lease,
                "condition_recorded",
                {"delta": {"integration": result_integration}},
            )

        environment = engine._merge_scope_environment()
        environment.pop("FORGE_SESSION_PID", None)
        result = chain_core.run_fenced_command(
            lock,
            operation="containment",
            intent_digest=ancestry_intent_digest,
            intent_validator=intent_current,
            argv=argv,
            cwd=Path(str(state["worktree"]["path"])),
            persist_result=persist,
            env=environment,
            timeout=runtime.COMMAND_TIMEOUT_SECONDS,
            cap=runtime.OUTPUT_CAP_BYTES,
            verbose=self.ctx.options.verbose,
        )
        durable = state.get("integration", {}).get("intent")
        if (
            not chain_core._epoch_ancestry_record_valid(state, durable)
            or not isinstance(durable, Mapping)
            or durable.get("phase") != "result"
            or durable.get("child_result", {}).get("inflight_digest")
            != result.fence_digest
            or durable.get("child_result", {}).get("output_digest")
            != result.output_digest
        ):
            raise FrozenError(
                "carried successor ancestry result was not durably retained",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        contained = durable["child_result"].get("contained")
        return state, contained if type(contained) is bool else None

    def _run_epoch_fetch(
        self,
        state: dict[str, Any],
        lock: chain_core.CommonRebaseLock,
        lease: chain_core.ChainLease,
        budget: engine._MergeEpochBudget,
        *,
        resume_intent: bool = False,
    ) -> tuple[dict[str, Any], str, bool]:
        """Run one fenced fetch, then classify only its durable raw result."""

        if not resume_intent:
            engine._require_active_merge_epoch(state)
        budget.consume("fetches")
        integration = copy.deepcopy(state["integration"])
        epoch = integration["epoch"]
        if resume_intent:
            intent = integration.get("intent")
            if (
                not isinstance(intent, Mapping)
                or intent.get("operation") != "fetch"
                or intent.get("operation_nonce") != epoch.get("operation_nonce")
                or intent.get("target") != state.get("target")
            ):
                raise FrozenError(
                    "interrupted merge fetch intent is malformed",
                    chain_id=str(state["chain_id"]),
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
        else:
            integration["intent"] = {
                "operation": "fetch",
                "operation_nonce": epoch["operation_nonce"],
                "attempt": 1,
                "target": copy.deepcopy(state["target"]),
            }
            state = self._epoch_transition(
                state,
                lease,
                "fetch_intent",
                {"delta": {"integration": integration}},
            )
        intent_digest = self._tail_event_digest(state, "fetch_intent")
        fetch_intent = copy.deepcopy(state["integration"]["intent"])
        fetch_argv = self._epoch_fetch_argv(state)

        def intent_current() -> bool:
            try:
                fresh = self.store.load_locked(str(state["chain_id"]), lease=lease)
            except (FrozenError, OSError, Refusal):
                return False
            return bool(
                fresh.get("state") == "rebasing"
                and fresh.get("integration", {}).get("intent") == fetch_intent
                and self._tail_event_digest(fresh, "fetch_intent")
                == intent_digest
            )

        def persist(result: chain_core.FencedProcessResult) -> None:
            nonlocal state
            observation = {
                "schema": chain_core._EPOCH_FETCH_OBSERVATION_SCHEMA,
                "chain_id": state["chain_id"],
                "epoch_intent_digest": epoch["intent_digest"],
                "operation_nonce": epoch["operation_nonce"],
                "generation_digest": state["candidate"]["generation_digest"],
                "fetch_intent_event_digest": intent_digest,
                "target": copy.deepcopy(state["target"]),
                "argv": copy.deepcopy(fetch_argv),
                "child_result": {
                    "authorized": result.authorized,
                    "exit": result.returncode,
                    "inflight_digest": result.fence_digest,
                    "output_digest": result.output_digest,
                    "launch_failed": result.launch_failed,
                    "timed_out": result.timed_out,
                    "output_limit_exceeded": result.output_limit,
                    "group_survived": result.group_survived,
                },
                "recorded_at": chain_core.iso_z(),
            }
            next_integration = copy.deepcopy(state["integration"])
            next_integration["intent"] = observation
            state = self._epoch_transition(
                state,
                lease,
                "condition_recorded",
                {"delta": {"integration": next_integration}},
            )

        environment = os.environ.copy()
        environment.pop("FORGE_SESSION_PID", None)
        environment.update({"GIT_OPTIONAL_LOCKS": "0", "GIT_NO_LAZY_FETCH": "1"})
        result = chain_core.run_fenced_command(
            lock,
            operation="fetch",
            intent_digest=intent_digest,
            intent_validator=intent_current,
            argv=fetch_argv,
            cwd=Path(str(state["worktree"]["path"])),
            persist_result=persist,
            env=environment,
            timeout=runtime.COMMAND_TIMEOUT_SECONDS,
            cap=runtime.OUTPUT_CAP_BYTES,
            verbose=self.ctx.options.verbose,
        )
        durable = state.get("integration", {}).get("intent")
        if (
            not chain_core._epoch_fetch_observation_record_valid(state, durable)
            or not isinstance(durable, Mapping)
            or durable.get("fetch_intent_event_digest") != intent_digest
            or durable.get("child_result", {}).get("inflight_digest")
            != result.fence_digest
            or durable.get("child_result", {}).get("output_digest")
            != result.output_digest
        ):
            raise FrozenError(
                "merge epoch fetch result was not durably retained",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        return self._complete_epoch_fetch_locked(state, lock, lease)

    def _complete_epoch_fetch_locked(
        self,
        state: dict[str, Any],
        lock: chain_core.CommonRebaseLock,
        lease: chain_core.ChainLease,
    ) -> tuple[dict[str, Any], str, bool]:
        """Resume raw fetch/candidate/ancestry phases without another fetch."""

        chain_core._require_merge_integration_control("successor-ancestry-observation")
        replay_context = self._epoch_replay_context(state)
        raw = replay_context.get("epoch_fetch_observation")
        raw_evidence = raw.get("evidence") if isinstance(raw, Mapping) else None
        if (
            not isinstance(raw, Mapping)
            or not isinstance(raw_evidence, Mapping)
            or not chain_core._epoch_fetch_observation_record_valid(state, raw_evidence)
            or raw.get("digest")
            != engine._merge_epoch_fetch_observation_digest(
                self.store, str(state["chain_id"]), raw_evidence
            )
        ):
            raise FrozenError(
                "merge epoch raw fetch result is unavailable or mismatched",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        epoch = state["integration"]["epoch"]
        if not chain_core._epoch_fetch_observation_passed(raw_evidence):
            failed_integration = copy.deepcopy(state["integration"])
            engine._reset_merge_nonmovement_counter(failed_integration)
            failed_integration.update(
                {
                    "condition": "fetch-failed",
                    "primary_condition": "none",
                    "epoch": None,
                    "intent": {
                        "operation": "fetch-result",
                        "operation_nonce": epoch["operation_nonce"],
                        "attempt": 1,
                        "result": "failed",
                        "resolved_tip": None,
                    },
                }
            )
            state = self._epoch_transition(
                state,
                lease,
                "fetch_result",
                {
                    "delta": {
                        "state": "authorized",
                        "integration": failed_integration,
                    }
                },
            )
            raise chain_core._merge_refusal(
                V2ReasonCode.FETCH_FAILED,
                "forge: merge finalize refused — fixed target fetch failed",
                observed="fenced fetch did not PASS",
                remediation=f"forge merge finalize --chain-id {state['chain_id']}",
                chain=state,
            )

        current_intent = state.get("integration", {}).get("intent")
        if (
            isinstance(current_intent, Mapping)
            and current_intent.get("schema")
            == "forge-epoch-ancestry-intent/1"
        ):
            fetched_tip = str(current_intent.get("fetched_tip", ""))
        elif (
            isinstance(current_intent, Mapping)
            and current_intent.get("schema")
            == chain_core._MERGE_CANDIDATE_OBSERVATION_SCHEMA
        ):
            if current_intent.get("source_intent") != raw_evidence:
                raise FrozenError(
                    "merge candidate observation is bound to another fetch",
                    chain_id=str(state["chain_id"]),
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            fetched_tip = str(current_intent.get("remote_tip", ""))
        else:
            candidate_context = replay_context.get("candidate_observation")
            candidate_evidence = (
                candidate_context.get("evidence")
                if isinstance(candidate_context, Mapping)
                and candidate_context.get("source_intent") == raw_evidence
                else None
            )
            fetched_tip = (
                str(candidate_evidence.get("remote_tip", ""))
                if isinstance(candidate_evidence, Mapping)
                else self._resolved_epoch_fetch_tip(state)
            )
        if chain_core.COMMIT_RE.fullmatch(fetched_tip) is None:
            raise FrozenError(
                "merge epoch fetched tip is malformed",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )

        candidate = state["candidate"]
        unchanged = fetched_tip == candidate["remote_tip"]
        policy: Policy | None = None
        contained: bool | None = True
        carried = False
        if unchanged:
            candidate_context = replay_context.get("candidate_observation")
            observation = (
                candidate_context.get("evidence")
                if isinstance(candidate_context, Mapping)
                and candidate_context.get("source_intent") == raw_evidence
                and candidate_context.get("evidence_digest")
                == candidate_context.get("evidence", {}).get("evidence_digest")
                else None
            )
            if observation is None:
                state, observation = self._run_candidate_observation_locked(
                    state,
                    lock,
                    lease,
                    verb="merge finalize",
                    remote_tip=fetched_tip,
                    expected_head=str(candidate["candidate_head"]),
                    classify=True,
                )
                replay_context = self._epoch_replay_context(state)
                candidate_context = replay_context.get("candidate_observation")
            if (
                not isinstance(candidate_context, Mapping)
                or not chain_core._merge_candidate_observation_evidence_valid(
                    state, observation
                )
                or candidate_context.get("source_intent") != raw_evidence
                or candidate_context.get("evidence_digest")
                != observation.get("evidence_digest")
            ):
                raise FrozenError(
                    "merge candidate observation is not fetch-bound",
                    chain_id=str(state["chain_id"]),
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            _repository, policy, _paths = _observe_current_merge_candidate(
                self.ctx,
                state,
                verb="merge finalize",
                observation=observation,
            )
            authorization = state.get("authorization")
            carried = bool(
                isinstance(authorization, Mapping)
                and authorization.get("candidate_head")
                == candidate["candidate_head"]
                and authorization.get("review_verdict") == "PASS"
                and authorization.get("generation_digest")
                != candidate["generation_digest"]
            )
            if carried:
                ancestry_intent = state.get("integration", {}).get("intent")
                state, contained = self._run_carried_successor_ancestry(
                    state,
                    fetched_tip,
                    lock,
                    lease,
                    resume_intent=bool(
                        isinstance(ancestry_intent, Mapping)
                        and ancestry_intent.get("schema")
                        == "forge-epoch-ancestry-intent/1"
                    ),
                )

        next_integration = copy.deepcopy(state["integration"])
        next_integration["intent"] = {
            "operation": "fetch-result",
            "operation_nonce": epoch["operation_nonce"],
            "attempt": 1,
            "result": "success",
            "resolved_tip": fetched_tip,
        }
        safe_unchanged = bool(unchanged and (not carried or contained is True))
        next_state = str(state["state"])
        if safe_unchanged:
            assert policy is not None
            suite = (
                engine._merge_epoch_suite(state, policy)
                if int(candidate["generation"]) > 1
                else []
            )
            next_integration["epoch"]["gate_plan"] = self._sealed_plan(
                state, policy, suite
            )
            if suite:
                next_state = "reverifying"
        fetch_delta: dict[str, Any] = {"integration": next_integration}
        if next_state != state["state"]:
            fetch_delta["state"] = next_state
        state = self._epoch_transition(
            state,
            lease,
            "fetch_result",
            {"delta": fetch_delta},
        )
        if carried and contained is None:
            state = self._record_foreign_git_locked(state, lease)
            raise chain_core._merge_refusal(
                V2ReasonCode.STATE_PRECONDITION,
                "forge: merge finalize refused — carried successor ancestry is unavailable",
                observed="foreign-git-state",
                remediation=f"forge status --chain-id {state['chain_id']}",
                chain=state,
            )
        return state, fetched_tip, safe_unchanged

    def _run_epoch_rebase(
        self,
        state: dict[str, Any],
        fetched_tip: str,
        lock: chain_core.CommonRebaseLock,
        lease: chain_core.ChainLease,
        budget: engine._MergeEpochBudget,
    ) -> dict[str, Any]:
        engine._require_active_merge_epoch(state)
        budget.consume("rebases")
        pre_head = str(state["candidate"]["candidate_head"])
        integration = copy.deepcopy(state["integration"])
        epoch = integration["epoch"]
        reflog_action = (
            f"forge-merge-rebase:{state['chain_id']}:"
            f"{state['candidate']['generation_digest']}:"
            f"{epoch['operation_nonce']}"
        )
        integration.update(
            {
                "pre_rebase": {
                    "head": pre_head,
                    "fetched_tip": fetched_tip,
                    "generation_digest": state["candidate"]["generation_digest"],
                    "recorded_at": chain_core.iso_z(),
                },
                "conflict": None,
                "intent": {
                    "operation": "rebase",
                    "operation_nonce": epoch["operation_nonce"],
                    "pre_operation_head": pre_head,
                    "fetched_tip": fetched_tip,
                    "branch": state["branch"],
                    "generation_digest": state["candidate"]["generation_digest"],
                    "reflog_action": reflog_action,
                    "started_at": chain_core.iso_z(),
                },
            }
        )
        state = self._epoch_transition(
            state, lease, "rebase_intent", {"delta": {"integration": integration}}
        )
        intent_digest = self._tail_event_digest(state, "rebase_intent")

        def intent_current() -> bool:
            return self._tail_event_digest(state, "rebase_intent") == intent_digest

        def persist(result: chain_core.FencedProcessResult) -> None:
            nonlocal state
            succeeded = bool(
                result.returncode == 0
                and not result.launch_failed
                and not result.timed_out
                and not result.output_limit
                and not result.group_survived
            )
            result_integration = copy.deepcopy(state["integration"])
            result_integration["intent"] = {
                "operation": "rebase-result",
                "operation_nonce": epoch["operation_nonce"],
                "result": "success" if succeeded else "failed",
                "pre_operation_head": pre_head,
                "fetched_tip": fetched_tip,
                "branch": state["branch"],
                "generation_digest": state["candidate"]["generation_digest"],
                "reflog_action": reflog_action,
                "exit": result.returncode,
                "inflight_digest": result.fence_digest,
                "output_digest": result.output_digest,
                "launch_failed": result.launch_failed,
                "timed_out": result.timed_out,
                "output_limit_exceeded": result.output_limit,
                "group_survived": result.group_survived,
                "recorded_at": chain_core.iso_z(),
            }
            state = self._epoch_transition(
                state,
                lease,
                "rebase_result",
                {"delta": {"integration": result_integration}},
            )

        environment = os.environ.copy()
        environment.pop("FORGE_SESSION_PID", None)
        environment.update(
            {
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_NO_LAZY_FETCH": "1",
                "GIT_REFLOG_ACTION": reflog_action,
            }
        )
        chain_core.run_fenced_command(
            lock,
            operation="rebase",
            intent_digest=intent_digest,
            intent_validator=intent_current,
            argv=[
                "git",
                "--no-pager",
                "-C",
                str(state["worktree"]["path"]),
                "rebase",
                fetched_tip,
            ],
            cwd=Path(str(state["worktree"]["path"])),
            persist_result=persist,
            env=environment,
            timeout=runtime.COMMAND_TIMEOUT_SECONDS,
            cap=runtime.OUTPUT_CAP_BYTES,
            verbose=self.ctx.options.verbose,
        )
        state = self._recover_rebase_observation_locked(state, lock, lease)
        if state["state"] == "rebase_conflict":
            raise chain_core._merge_refusal(
                V2ReasonCode.REBASE_CONFLICT,
                "forge: merge finalize refused — integration has a recoverable rebase conflict",
                remediation=(
                    f"forge merge recover --continue --paths <path>... --chain-id {state['chain_id']}"
                ),
                chain=state,
            )
        if (
            state["state"] == "revising"
            and state.get("integration", {}).get("condition") == "rebase-failed"
        ):
            raise chain_core._merge_refusal(
                V2ReasonCode.REBASE_FAILED,
                "forge: merge finalize refused — integration rebase failed",
                remediation=f"forge merge refresh --chain-id {state['chain_id']}",
                chain=state,
            )
        if state.get("integration", {}).get("condition") == "foreign-git-state":
            if engine._merge_rebase_result_failed(state):
                raise chain_core._merge_refusal(
                    V2ReasonCode.REBASE_FAILED,
                    "forge: merge finalize refused — integration rebase failed",
                    observed="foreign-git-state",
                    remediation=f"forge status --chain-id {state['chain_id']}",
                    chain=state,
                )
            raise chain_core._merge_refusal(
                V2ReasonCode.STATE_PRECONDITION,
                "forge: merge finalize refused — rebase result is not attributable to the recorded intent",
                observed="foreign-git-state",
                remediation=f"forge status --chain-id {state['chain_id']}",
                chain=state,
            )
        if state["state"] != "reverifying":
            raise FrozenError(
                "merge rebase produced no authenticated successor generation",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        return state

    def _run_epoch_suite(
        self,
        state: dict[str, Any],
        lock: chain_core.CommonRebaseLock,
        lease: chain_core.ChainLease,
        budget: engine._MergeEpochBudget,
    ) -> dict[str, Any]:
        engine._require_active_merge_epoch(state)
        plan = state.get("integration", {}).get("epoch", {}).get("gate_plan")
        if not isinstance(plan, Mapping) or plan.get("status") != "sealed":
            raise FrozenError(
                "merge epoch gate plan is not sealed",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        if int(plan["cursor"]) >= len(plan["suite"]):
            return state
        budget.consume("suites")
        state, candidate_observation = self._run_candidate_observation_locked(
            state,
            lock,
            lease,
            verb="merge finalize",
            remote_tip=str(state["candidate"]["remote_tip"]),
            expected_head=str(state["candidate"]["candidate_head"]),
            classify=False,
        )
        repository, policy, changed_paths = _observe_current_merge_candidate(
            self.ctx,
            state,
            verb="merge finalize",
            observation=candidate_observation,
        )
        expected = engine._merge_epoch_suite(state, policy)
        if expected != plan["suite"] or sha256_bytes(
            chain_core.canonical_bytes(expected)
        ) != plan["suite_digest"]:
            raise FrozenError(
                "merge epoch gate plan diverges from committed policy",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        while True:
            engine._require_active_merge_epoch(state)
            plan = state["integration"]["epoch"]["gate_plan"]
            cursor = int(plan["cursor"])
            if cursor >= len(plan["suite"]):
                return state
            member = plan["suite"][cursor]
            gate_id = str(member["id"])
            authorizing_digest = (
                str(plan["seal_event_digest"])
                if cursor == 0
                else self._tail_event_digest(state, "gate_recorded")
            )
            intent_digest = chain_core.merge_gate_intent_digest(
                chain_id=str(state["chain_id"]),
                epoch_intent_digest=str(state["integration"]["epoch"]["intent_digest"]),
                seal_event_digest=str(plan["seal_event_digest"]),
                generation_digest=str(plan["generation_digest"]),
                policy_digest=str(plan["policy_digest"]),
                suite_digest=str(plan["suite_digest"]),
                cursor=cursor,
                kind=str(member["kind"]),
                gate_id=gate_id,
                authorizing_event_digest=authorizing_digest,
            )
            if member["kind"] == "scoped-mutation":
                argv = [
                    sys.executable,
                    str(self.ctx.helper("run-scoped-mutation.py")),
                    "--base",
                    str(state["candidate"]["remote_tip"]),
                    "--head",
                    str(state["candidate"]["candidate_head"]),
                ]
                bound = engine._merge_run_directory(state)
                if bound is not None:
                    _repository, run_dir = bound
                    argv.extend(
                        [
                            "--journal",
                            str(run_dir / "journal.jsonl"),
                            "--task",
                            str(state["run_binding"]["task_id"]),
                        ]
                    )
                details: dict[str, Any] = {"kind": "scoped-mutation"}
            else:
                argv, remaining, details = self._resolve_gate(
                    state, policy, changed_paths, gate_id
                )
                if gate_id.startswith("stack:"):
                    commands = [argv, *(
                        ["bash", "-c", cell, "forge", *changed_paths]
                        for cell in remaining
                    )]
                    cell_index = 1 + sum(
                        1
                        for prior_member in plan["suite"][:cursor]
                        if prior_member == member
                    )
                    if cell_index > len(commands):
                        raise FrozenError(
                            "stack cursor exceeds its committed command cells",
                            chain_id=str(state["chain_id"]),
                            observed=gate_id,
                            schema=REVISION9_OUTPUT_SCHEMA,
                        )
                    argv = commands[cell_index - 1]
                    details.update(
                        {
                            "batch_id": sha256_bytes(
                                chain_core.canonical_bytes(
                                    {
                                        "epoch": state["integration"]["epoch"][
                                            "intent_digest"
                                        ],
                                        "suite": plan["suite_digest"],
                                        "gate": gate_id,
                                    }
                                )
                            )[:16],
                            "cell_count": len(commands),
                            "cell_index": cell_index,
                        }
                    )
            holder: dict[str, Any] = {}

            def intent_current() -> bool:
                try:
                    fresh = self.store.load_locked(str(state["chain_id"]), lease=lease)
                    current_plan = fresh["integration"]["epoch"]["gate_plan"]
                    return bool(
                        current_plan == state["integration"]["epoch"]["gate_plan"]
                        and int(current_plan["cursor"]) == cursor
                    )
                except (KeyError, FrozenError, OSError, TypeError):
                    return False

            def persist(result: chain_core.FencedProcessResult) -> None:
                nonlocal state
                passed = bool(
                    result.returncode == 0
                    and not result.launch_failed
                    and not result.timed_out
                    and not result.output_limit
                    and not result.group_survived
                )
                transcript = engine._write_merge_artifact(
                    self.ctx,
                    state,
                    (
                        "evidence/epoch-"
                        f"{state['integration']['epoch']['operation_nonce']}-"
                        f"{cursor:02d}-{re.sub(r'[^A-Za-z0-9_.-]+', '-', gate_id)}.log"
                    ),
                    result.output,
                )
                fact = {
                    "result": (
                        "passed"
                        if passed
                        else "inconclusive"
                        if member["kind"] == "scoped-mutation"
                        else "failed"
                    ),
                    "generation_digest": state["candidate"]["generation_digest"],
                    "criterion": (
                        "mutation: scoped"
                        if member["kind"] == "scoped-mutation"
                        else f"gate-1: {gate_id}"
                        if gate_id == "gate-1"
                        else f"gate-2: {gate_id}"
                    ),
                    "command_argv": list(argv),
                    "exit_code": result.returncode,
                    "duration_seconds": round(result.duration_seconds, 6),
                    "stdout_stderr_digest": result.output_digest,
                    "timed_out": result.timed_out,
                    "output_limit": result.output_limit,
                    "launch_failed": result.launch_failed,
                    "transcript": transcript,
                    "gate_plan_position": {
                        "seal_event_digest": plan["seal_event_digest"],
                        "suite_digest": plan["suite_digest"],
                        "cursor": cursor,
                        "kind": member["kind"],
                        "id": gate_id,
                    },
                    "gate_intent_digest": intent_digest,
                    "inflight_digest": result.fence_digest,
                    **copy.deepcopy(details),
                }
                steps = copy.deepcopy(state["steps"])
                runs = copy.deepcopy(steps.get(gate_id, []))
                if not isinstance(runs, list):
                    runs = []
                runs.append(fact)
                steps[gate_id] = runs
                integration = copy.deepcopy(state["integration"])
                integration["epoch"]["gate_plan"]["cursor"] = cursor + 1
                delta: dict[str, Any] = {
                    "steps": steps,
                    "integration": integration,
                }
                if not passed and member["kind"] == "gate":
                    engine._reset_merge_nonmovement_counter(integration)
                    delta["state"] = "reverification_failed"
                state = self._epoch_transition(
                    state,
                    lease,
                    "gate_recorded",
                    {"delta": delta},
                )
                holder["passed"] = passed or member["kind"] == "scoped-mutation"

            environment = os.environ.copy()
            environment.pop("FORGE_SESSION_PID", None)
            chain_core.run_fenced_command(
                lock,
                operation="gate",
                intent_digest=intent_digest,
                intent_validator=intent_current,
                argv=argv,
                cwd=repository.root,
                persist_result=persist,
                env=environment,
                timeout=runtime.COMMAND_TIMEOUT_SECONDS,
                cap=runtime.OUTPUT_CAP_BYTES,
                verbose=self.ctx.options.verbose,
            )
            try:
                state, candidate_observation = (
                    self._run_candidate_observation_locked(
                        state,
                        lock,
                        lease,
                        verb="merge finalize",
                        remote_tip=str(state["candidate"]["remote_tip"]),
                        expected_head=str(state["candidate"]["candidate_head"]),
                        classify=False,
                    )
                )
                _observe_current_merge_candidate(
                    self.ctx,
                    state,
                    verb="merge finalize",
                    observation=candidate_observation,
                )
            except Refusal as exc:
                if exc.reason_code == V2ReasonCode.CANDIDATE_STALE:
                    observed_outputs = engine._merge_candidate_observation_outputs(
                        state, candidate_observation
                    )
                    observed_head = ""
                    if observed_outputs is not None:
                        try:
                            observed_head = (
                                observed_outputs["identity"]
                                .decode("utf-8")
                                .splitlines()[-1]
                            )
                        except (IndexError, UnicodeDecodeError):
                            observed_head = ""
                    state, refreshed_observation = (
                        self._run_candidate_observation_locked(
                            state,
                            lock,
                            lease,
                            verb="merge finalize",
                            remote_tip=str(state["candidate"]["remote_tip"]),
                            expected_head=observed_head,
                            classify=True,
                        )
                    )
                    admission = self._admission_from_candidate_observation(
                        state,
                        refreshed_observation,
                        verb="merge finalize",
                        require_current_generation=False,
                    )
                    generation = engine.bind_merge_candidate_generation(
                        self.ctx,
                        admission,
                        str(state["candidate"]["remote_tip"]),
                        generation=int(state["candidate"]["generation"]) + 1,
                        observation=refreshed_observation,
                    )
                    integration = copy.deepcopy(state["integration"])
                    engine._reset_merge_nonmovement_counter(integration)
                    integration.update(
                        {
                            "condition": "none",
                            "primary_condition": "none",
                            "epoch": None,
                        }
                    )
                    review = state.get("review")
                    iteration = (
                        review.get("iteration")
                        if isinstance(review, Mapping)
                        else None
                    )
                    retained_review = (
                        {"iteration": iteration}
                        if type(iteration) is int
                        else {}
                    )
                    state = self._epoch_transition(
                        state,
                        lease,
                        "generation_refreshed",
                        {
                            "delta": {
                                "state": "verifying",
                                "policy_source": {
                                    "commit": admission.policy.sha,
                                    "digest": admission.policy.digest,
                                },
                                "candidate": copy.deepcopy(
                                    generation.candidate
                                ),
                                "tier": copy.deepcopy(generation.tier),
                                "integration": integration,
                                "steps": {},
                                "review": retained_review,
                                "approval": {},
                                "authorization": {},
                            }
                        },
                        generation_digest=str(
                            generation.candidate["generation_digest"]
                        ),
                    )
                    exc.chain = state
                    exc.remediation = (
                        f"forge merge refresh --chain-id {state['chain_id']}"
                    )
                    exc.next_required_step = exc.remediation
                raise
            if not holder.get("passed"):
                raise chain_core._merge_refusal(
                    V2ReasonCode.MERGE_GATE_FAILED,
                    f"forge: merge gate failed — {gate_id}",
                    remediation=f"forge merge recover --chain-id {state['chain_id']}",
                    chain=state,
                    evidence_refs=[
                        str(state["steps"][gate_id][-1]["transcript"])
                    ],
                )

    @staticmethod
    def _parse_remote_observation(
        result: chain_core.FencedProcessResult, destination_ref: str
    ) -> tuple[bool | None, str | None]:
        complete = bool(
            result.returncode == 0
            and not result.launch_failed
            and not result.timed_out
            and not result.output_limit
            and not result.group_survived
        )
        if not complete:
            return None, None
        if not result.output:
            return False, None
        try:
            decoded = result.output.decode("ascii")
        except UnicodeDecodeError:
            return None, None
        rows = decoded.splitlines()
        if len(rows) != 1:
            return None, None
        fields = rows[0].split("\t")
        if (
            len(fields) != 2
            or fields[1] != destination_ref
            or chain_core.COMMIT_RE.fullmatch(fields[0]) is None
        ):
            return None, None
        return True, fields[0]

    @staticmethod
    def _parse_fetched_remote_observation(
        result: chain_core.FencedProcessResult,
        destination_ref: str,
        git_dir: Path,
    ) -> tuple[bool | None, str | None]:
        """Classify the single fixed-ref observation fetch without a stale ref."""

        complete = bool(
            result.authorized
            and not result.launch_failed
            and not result.timed_out
            and not result.output_limit
            and not result.group_survived
            and result.returncode is not None
        )
        if not complete:
            return None, None
        if result.returncode != 0:
            expected = f"couldn't find remote ref {destination_ref}".encode("utf-8")
            return (False, None) if expected in result.output else (None, None)
        fetch_head = git_dir / "FETCH_HEAD"
        try:
            raw = fetch_head.read_bytes()
        except OSError:
            return None, None
        if len(raw) > chain_core.MERGE_SCOPE_BINDING_CAP_BYTES or not raw.endswith(b"\n"):
            return None, None
        rows = raw.splitlines()
        if len(rows) != 1:
            return None, None
        raw_oid = rows[0].split(b"\t", 1)[0]
        try:
            oid = raw_oid.decode("ascii")
        except UnicodeDecodeError:
            return None, None
        if chain_core.COMMIT_RE.fullmatch(oid) is None:
            return None, None
        return True, oid

    @staticmethod
    def _head_contained(repository: chain_core.Repository, head: str, tip: str) -> bool:
        return (
            repository.git(
                ["merge-base", "--is-ancestor", head, tip], check=False
            ).returncode
            == 0
        )

    def _run_remote_observation(
        self,
        state: dict[str, Any],
        lock: chain_core.CommonRebaseLock,
        lease: chain_core.ChainLease,
        budget: engine._MergeEpochBudget,
        *,
        phase: str,
        budget_member: str | None = None,
        allow_inactive_observation: bool = False,
    ) -> dict[str, Any]:
        selected_budget = budget_member or (
            "pre_observations" if phase == "final-prepush" else "post_observations"
        )
        if budget_member is not None and not (
            phase == "post-push" and budget_member == "pre_observations"
        ):
            raise ValueError("merge recovery observation budget is invalid")
        budget.consume(selected_budget)
        push_intent_digest = (
            self._tail_event_digest(state, "push_intent")
            if phase == "post-push"
            else None
        )
        intent = engine._remote_observation_intent(
            state,
            phase=phase,
            push_intent_digest=push_intent_digest,
        )
        intent_digest = sha256_bytes(chain_core.canonical_bytes(intent))
        integration = copy.deepcopy(state["integration"])
        integration["intent"] = intent
        state = self._epoch_transition(
            state,
            lease,
            "condition_recorded",
            {"delta": {"integration": integration}},
        )

        def intent_current() -> bool:
            try:
                fresh = self.store.load_locked(str(state["chain_id"]), lease=lease)
            except (FrozenError, OSError):
                return False
            return fresh.get("integration", {}).get("intent") == intent

        heads = chain_core._remote_observation_heads(state)
        fetch_argv = chain_core._remote_observation_fetch_argv(state)

        def persist(result: chain_core.FencedProcessResult) -> None:
            nonlocal state
            exists, oid = self._parse_fetched_remote_observation(
                result,
                str(state["target"]["destination_ref"]),
                Path(str(state["worktree"]["git_dir"])),
            )
            progress = {
                **intent,
                "schema": "forge-remote-observation-progress/1",
                "stage": "fetch-result",
                "fetch_result": {
                    "argv": list(result.argv),
                    "authorized": result.authorized,
                    "exit": result.returncode,
                    "exists": exists,
                    "oid": oid,
                    "inflight_digest": result.fence_digest,
                    "output_digest": result.output_digest,
                    "launch_failed": result.launch_failed,
                    "timed_out": result.timed_out,
                    "output_limit_exceeded": result.output_limit,
                    "group_survived": result.group_survived,
                },
                "heads": list(heads),
                "cursor": 0,
                "head": None,
                "argv": None,
                "completed": [],
                "recorded_at": chain_core.iso_z(),
            }
            next_integration = copy.deepcopy(state["integration"])
            next_integration["intent"] = progress
            state = self._epoch_transition(
                state,
                lease,
                "condition_recorded",
                {"delta": {"integration": next_integration}},
            )

        environment = os.environ.copy()
        environment.pop("FORGE_SESSION_PID", None)
        environment.update(
            {
                "LC_ALL": "C",
                "LANG": "C",
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_NO_LAZY_FETCH": "1",
            }
        )
        fetch_result = chain_core.run_fenced_command(
            lock,
            operation="remote-observation",
            intent_digest=intent_digest,
            intent_validator=intent_current,
            argv=fetch_argv,
            cwd=Path(str(state["worktree"]["path"])),
            persist_result=persist,
            env=environment,
            timeout=runtime.COMMAND_TIMEOUT_SECONDS,
            cap=runtime.OUTPUT_CAP_BYTES,
            verbose=self.ctx.options.verbose,
        )
        progress = state.get("integration", {}).get("intent")
        if (
            not chain_core._remote_observation_progress_valid(state, progress)
            or not isinstance(progress, Mapping)
            or progress.get("stage") != "fetch-result"
            or progress.get("fetch_result", {}).get("inflight_digest")
            != fetch_result.fence_digest
            or progress.get("fetch_result", {}).get("output_digest")
            != fetch_result.output_digest
        ):
            raise FrozenError(
                "remote observation fetch result was not durably retained",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        progress = copy.deepcopy(dict(progress))
        fetch_evidence = progress["fetch_result"]
        exists = fetch_evidence["exists"]
        oid = fetch_evidence["oid"]
        environment = dict(environment)
        for cursor, head in enumerate(heads):
            if exists is not True or oid is None or (
                engine._merge_inactive(state) and not allow_inactive_observation
            ):
                break
            if any(
                item.get("contained") is None
                for item in progress.get("completed", [])
            ):
                break
            containment_argv = chain_core._remote_containment_argv(state, head, str(oid))
            containment_intent = {
                **progress,
                "stage": "containment-intent",
                "cursor": cursor,
                "head": head,
                "argv": containment_argv,
                "recorded_at": chain_core.iso_z(),
            }
            next_integration = copy.deepcopy(state["integration"])
            next_integration["intent"] = containment_intent
            state = self._epoch_transition(
                state,
                lease,
                "condition_recorded",
                {"delta": {"integration": next_integration}},
            )
            containment_digest = sha256_bytes(chain_core.canonical_bytes(containment_intent))

            def containment_current() -> bool:
                try:
                    fresh = self.store.load_locked(
                        str(state["chain_id"]), lease=lease
                    )
                except (FrozenError, OSError):
                    return False
                return fresh.get("integration", {}).get("intent") == containment_intent

            def persist_containment(result: chain_core.FencedProcessResult) -> None:
                nonlocal state, progress
                ordinary = bool(
                    result.authorized
                    and result.returncode in {0, 1}
                    and not result.launch_failed
                    and not result.timed_out
                    and not result.output_limit
                    and not result.group_survived
                )
                evidence = {
                    "head": head,
                    "tip": str(oid),
                    "argv": list(result.argv),
                    "authorized": result.authorized,
                    "exit": result.returncode,
                    "inflight_digest": result.fence_digest,
                    "output_digest": result.output_digest,
                    "launch_failed": result.launch_failed,
                    "timed_out": result.timed_out,
                    "output_limit_exceeded": result.output_limit,
                    "group_survived": result.group_survived,
                    "contained": (
                        result.returncode == 0 if ordinary else None
                    ),
                }
                completed = copy.deepcopy(containment_intent["completed"])
                completed.append(evidence)
                result_progress = {
                    **containment_intent,
                    "stage": "containment-result",
                    "completed": completed,
                    "recorded_at": chain_core.iso_z(),
                }
                result_integration = copy.deepcopy(state["integration"])
                result_integration["intent"] = result_progress
                state = self._epoch_transition(
                    state,
                    lease,
                    "condition_recorded",
                    {"delta": {"integration": result_integration}},
                )
                progress = result_progress

            containment_result = chain_core.run_fenced_command(
                lock,
                operation="containment",
                intent_digest=containment_digest,
                intent_validator=containment_current,
                argv=containment_argv,
                cwd=Path(str(state["worktree"]["path"])),
                persist_result=persist_containment,
                env=environment,
                timeout=runtime.COMMAND_TIMEOUT_SECONDS,
                cap=runtime.OUTPUT_CAP_BYTES,
                verbose=self.ctx.options.verbose,
            )
            durable = state.get("integration", {}).get("intent")
            if (
                not chain_core._remote_observation_progress_valid(state, durable)
                or not isinstance(durable, Mapping)
                or durable.get("stage") != "containment-result"
                or durable.get("completed", [{}])[-1].get("inflight_digest")
                != containment_result.fence_digest
                or durable.get("completed", [{}])[-1].get("output_digest")
                != containment_result.output_digest
            ):
                raise FrozenError(
                    "remote containment result was not durably retained",
                    chain_id=str(state["chain_id"]),
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            progress = copy.deepcopy(dict(durable))

        completed = progress.get("completed", [])
        complete_containment = bool(
            exists is True
            and len(completed) == len(heads)
            and all(type(item.get("contained")) is bool for item in completed)
        )
        if complete_containment:
            vector_values = [bool(item["contained"]) for item in completed]
        elif exists is False:
            vector_values = [False for _head in heads]
        else:
            exists = None
            oid = None
            vector_values = [None for _head in heads]

        restored_integration = copy.deepcopy(state["integration"])
        restored_integration["intent"] = intent
        state = self._epoch_transition(
            state,
            lease,
            "condition_recorded",
            {"delta": {"integration": restored_integration}},
        )

        push = state["integration"].get("push")
        attempts = (
            list(push.get("attempted_heads", []))
            if isinstance(push, Mapping)
            else []
        )
        attempted_vector = [
            {"head": head, "contained": contained}
            for head, contained in zip(attempts, vector_values[-len(attempts) :])
        ]
        contains_intended: bool | None = vector_values[-1] if vector_values else None
        observed = {
            "exists": exists,
            "oid": oid,
            "contains_intended_head": contains_intended,
            "attempted_head_containment": attempted_vector,
            "observed_at": chain_core.iso_z(),
            "inflight_digest": fetch_result.fence_digest,
            "output_digest": fetch_result.output_digest,
        }
        next_integration = copy.deepcopy(state["integration"])
        next_integration["observed"] = observed
        prior_count = int(next_integration["remote_movement_count"])
        next_state = str(state["state"])
        carried_generation: engine.MergeCandidateGeneration | None = None
        if phase == "final-prepush":
            if exists is True and oid == state["candidate"]["remote_tip"]:
                next_integration.update(
                    {"condition": "none", "primary_condition": "none"}
                )
            elif exists in {True, False}:
                count = prior_count + 1
                next_integration.update(
                    {
                        "condition": "remote-churn" if count == 8 else "remote-moved",
                        "primary_condition": "none",
                        "remote_movement_count": count,
                    }
                )
                next_state = "awaiting_approval" if count == 8 else "authorized"
                if exists is True and oid is not None:
                    try:
                        state, candidate_observation = (
                            self._run_candidate_observation_locked(
                                state,
                                lock,
                                lease,
                                verb="merge finalize",
                                remote_tip=oid,
                                expected_head=str(
                                    state["candidate"]["candidate_head"]
                                ),
                                classify=True,
                            )
                        )
                        admission = self._admission_from_candidate_observation(
                            state,
                            candidate_observation,
                            verb="merge finalize",
                            require_current_generation=False,
                        )
                        proposed = engine.bind_merge_candidate_generation(
                            self.ctx,
                            admission,
                            oid,
                            generation=int(state["candidate"]["generation"]) + 1,
                            observation=candidate_observation,
                        )
                        prior_candidate = state["candidate"]
                        if (
                            all(
                                prior_candidate.get(name)
                                == proposed.candidate.get(name)
                                for name in chain_core._MERGE_REMOTE_ONLY_IDENTITY_FIELDS
                            )
                            and proposed.tier == state.get("tier")
                            and not (
                                proposed.scope is not None
                                and proposed.scope.result == "exceeded"
                            )
                        ):
                            carried_generation = proposed
                            next_integration["epoch"] = None
                    except (KeyError, OSError, Refusal, ValueError):
                        carried_generation = None
            else:
                engine._reset_merge_nonmovement_counter(next_integration)
                next_integration.update(
                    {"condition": "fetch-failed", "primary_condition": "none"}
                )
                next_state = "authorized"
        else:
            assert isinstance(push, Mapping)
            next_push = copy.deepcopy(dict(push))
            landed = None
            for member in reversed(attempted_vector):
                if member["contained"] is True:
                    landed = member["head"]
                    break
            next_push["landed_head"] = landed
            next_integration["push"] = next_push
            classification = (
                next_push.get("result", {}).get("classification")
                if isinstance(next_push.get("result"), Mapping)
                else None
            )
            current_contained = bool(
                attempts
                and attempts[-1] == state["candidate"]["candidate_head"]
                and contains_intended is True
            )
            if current_contained:
                engine._reset_merge_nonmovement_counter(next_integration)
                next_state = "pushed"
                next_integration.update(
                    {"condition": "none", "primary_condition": "none"}
                )
            elif landed is not None:
                engine._reset_merge_nonmovement_counter(next_integration)
                if engine._merge_inactive(state):
                    next_state = "pushing"
                    next_integration.update(
                        {"condition": "none", "primary_condition": "none"}
                    )
                else:
                    next_state = "authorized"
                    next_integration.update(
                        {
                            "condition": "remote-moved",
                            "primary_condition": "none",
                        }
                    )
            elif exists is None:
                engine._reset_merge_nonmovement_counter(next_integration)
                next_state = "pushing"
                next_integration.update(
                    {
                        "condition": "push-outcome-unknown",
                        "primary_condition": "none",
                    }
                )
            elif exists is True and oid == next_push["expected_old_tip"]:
                engine._reset_merge_nonmovement_counter(next_integration)
                next_integration.update(
                    {
                        "condition": (
                            "push-failed"
                            if classification == "known-failure"
                            else "none"
                        ),
                        "primary_condition": "none",
                    }
                )
            else:
                independent = classification in {"success", "non-fast-forward"}
                if independent:
                    count = prior_count + 1
                else:
                    engine._reset_merge_nonmovement_counter(next_integration)
                    count = 0
                next_state = "awaiting_approval" if count == 8 else "authorized"
                next_integration.update(
                    {
                        "condition": (
                            "remote-churn"
                            if count == 8
                            else "non-fast-forward"
                            if classification == "non-fast-forward"
                            else "remote-moved"
                        ),
                        "primary_condition": "none",
                        "remote_movement_count": count,
                    }
                )
            if (
                engine._merge_inactive(state)
                and exists in {True, False}
                and attempted_vector
                and all(member["contained"] is False for member in attempted_vector)
            ):
                next_state = "pushing"
                next_integration.update(
                    {
                        "condition": "none",
                        "primary_condition": "none",
                        "remote_movement_count": 0,
                    }
                )
        observation_delta: dict[str, Any] = {"integration": next_integration}
        if next_state != state["state"]:
            observation_delta["state"] = next_state
        if carried_generation is not None:
            observation_delta["candidate"] = copy.deepcopy(
                carried_generation.candidate
            )
            observation_delta["steps"] = copy.deepcopy(state.get("steps"))
        transition_payload: dict[str, Any] = {"delta": observation_delta}
        if carried_generation is not None:
            transition_payload.update(
                {
                    "prior_generation_digest": state["candidate"][
                        "generation_digest"
                    ],
                    "successor_generation_digest": carried_generation.candidate[
                        "generation_digest"
                    ],
                    "equality_proof": chain_core._merge_remote_only_equality_proof(
                        state["candidate"]
                    ),
                }
            )
        state = self._epoch_transition(
            state,
            lease,
            (
                "generation_carried_forward"
                if carried_generation is not None
                else "push_observed"
            ),
            transition_payload,
            generation_digest=(
                str(carried_generation.candidate["generation_digest"])
                if carried_generation is not None
                else None
            ),
        )
        return state

    @staticmethod
    def _push_classification(
        result: chain_core.FencedProcessResult, destination_ref: str
    ) -> str:
        if (
            result.launch_failed
            or result.timed_out
            or result.output_limit
            or result.group_survived
            or result.returncode is None
        ):
            return "outcome-unknown"
        if result.returncode == 0:
            return "success"
        try:
            decoded = result.output.decode("utf-8")
        except UnicodeDecodeError:
            return "known-failure"
        target_rows: list[tuple[str, str]] = []
        for row in decoded.splitlines():
            fields = row.split("\t")
            if len(fields) != 3 or ":" not in fields[1]:
                continue
            _source, destination = fields[1].rsplit(":", 1)
            if destination == destination_ref:
                target_rows.append((fields[0], fields[2]))
        if len(target_rows) == 1 and target_rows[0] in {
            ("!", "[rejected] (non-fast-forward)"),
            ("!", "[rejected] (fetch first)"),
        }:
            return "non-fast-forward"
        return "known-failure"

    def _final_history_mutation_mode(
        self, state: Mapping[str, Any], lock: chain_core.CommonRebaseLock
    ) -> tuple[str | None, str]:
        """Read DM-015 from the exact final intended commit under the lock."""

        chain_core._require_merge_integration_control("final-intended-head-mode")
        candidate = state.get("candidate")
        if not isinstance(candidate, Mapping):
            raise FrozenError(
                "merge final intended HEAD is unavailable",
                chain_id=str(state.get("chain_id") or "") or None,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        worktree = Path(str(state["worktree"]["path"]))
        candidate_head = str(candidate["candidate_head"])
        argv = [
            "git",
            "cat-file",
            "blob",
            f"{candidate_head}:.forge-manifest",
        ]
        environment = engine._merge_scope_environment()
        try:
            lock.assert_held()
            engine._require_git_no_lazy_fetch_qualification(
                self._git_no_lazy_fetch_qualification,
                worktree,
                environment,
            )
            result = runtime.run_bounded(
                argv,
                cwd=worktree,
                env=environment,
                timeout=runtime.COMMAND_TIMEOUT_SECONDS,
                cap=runtime.OUTPUT_CAP_BYTES,
                verbose=self.ctx.options.verbose,
            )
            lock.assert_held()
        except (OSError, TimeoutError) as exc:
            raise self._final_mode_unavailable(state, str(exc)) from exc
        if result.timed_out or result.output_limit:
            raise chain_core._merge_refusal(
                V2ReasonCode.REBASE_LOCK_UNAVAILABLE,
                "forge: merge finalize refused — final intended HEAD mode is unavailable",
                expected="a complete bounded read of the candidate .forge-manifest blob",
                observed=(
                    f"exit={result.returncode}, timeout={result.timed_out}, "
                    f"output_limit={result.output_limit}"
                ),
                remediation=f"forge merge recover --chain-id {state['chain_id']}",
                chain=state,
            )
        if result.returncode != 0:
            return None, result.output_digest
        try:
            mode = engine._parse_history_mutation_mode(result.output)
        except ValueError:
            return None, result.output_digest
        return mode, result.output_digest

    def _park_invalid_final_history_mode(
        self,
        state: dict[str, Any],
        lease: chain_core.ChainLease,
        *,
        manifest_digest: str,
    ) -> dict[str, Any]:
        integration = copy.deepcopy(state["integration"])
        engine._reset_merge_nonmovement_counter(integration)
        integration.update(
            {
                "condition": "none",
                "primary_condition": "none",
                "epoch": None,
                "intent": {
                    "schema": "forge-history-mutation-mode-result/1",
                    "operation": "history-mutation-mode",
                    "candidate_head": state["candidate"]["candidate_head"],
                    "manifest_digest": manifest_digest,
                    "result": "invalid",
                    "recorded_at": chain_core.iso_z(),
                },
            }
        )
        review = state.get("review")
        iteration = review.get("iteration") if isinstance(review, Mapping) else None
        projection = {
            "state": "revising",
            "review": {"iteration": iteration} if type(iteration) is int else {},
            "approval": {},
            "authorization": {},
            "integration": integration,
        }
        return self._epoch_transition(
            state,
            lease,
            "reverification_result",
            {
                "delta": {
                    name: value
                    for name, value in projection.items()
                    if state.get(name) != value
                }
            },
        )

    def _run_epoch_push(
        self,
        state: dict[str, Any],
        lock: chain_core.CommonRebaseLock,
        lease: chain_core.ChainLease,
        budget: engine._MergeEpochBudget,
        *,
        retry: bool = False,
    ) -> dict[str, Any]:
        engine._require_active_merge_epoch(state)
        plan = state["integration"]["epoch"]["gate_plan"]
        if plan.get("status") != "sealed" or plan.get("cursor") != len(
            plan.get("suite", [])
        ):
            raise FrozenError(
                "merge push intent precedes completion of its sealed gate plan",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        if retry:
            chain_core._require_merge_integration_control("push-retry")
            prior_result = state.get("integration", {}).get("push", {}).get(
                "result"
            )
            if (
                state.get("state") != "pushing"
                or engine._merge_inactive(state)
                or not (
                    prior_result is None or isinstance(prior_result, Mapping)
                )
                or not chain_core._merge_old_tip_all_false(state)
                or not self._current_merge_authority(state)
            ):
                raise FrozenError(
                    "merge duplicate push lacks an active authorized old-tip observation",
                    chain_id=str(state["chain_id"]),
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
        state, candidate_observation = self._run_candidate_observation_locked(
            state,
            lock,
            lease,
            verb="merge finalize",
            remote_tip=str(state["candidate"]["remote_tip"]),
            expected_head=str(state["candidate"]["candidate_head"]),
            classify=False,
        )
        _observe_current_merge_candidate(
            self.ctx,
            state,
            verb="merge finalize",
            observation=candidate_observation,
        )
        mode, manifest_digest = self._final_history_mutation_mode(state, lock)
        if mode is None:
            state = self._park_invalid_final_history_mode(
                state,
                lease,
                manifest_digest=manifest_digest,
            )
            raise chain_core._merge_refusal(
                V2ReasonCode.STATE_PRECONDITION,
                "forge: history mutation mode invalid — repair committed .forge-manifest through Forge CLI",
                remediation=(
                    "repair committed .forge-manifest through Forge CLI, then "
                    f"forge merge refresh --chain-id {state['chain_id']}"
                ),
                chain=state,
            )
        budget.consume("pushes")
        candidate = state["candidate"]
        integration = copy.deepcopy(state["integration"])
        epoch = integration["epoch"]
        prior_push = integration.get("push")
        attempted = (
            list(prior_push.get("attempted_heads", []))
            if isinstance(prior_push, Mapping)
            else []
        )
        attempted.append(str(candidate["candidate_head"]))
        intended_at = chain_core.iso_z()
        engine._reset_merge_nonmovement_counter(integration)
        integration.update(
            {
                "condition": "none",
                "primary_condition": "none",
                "intent": {
                    "operation": "push",
                    "operation_nonce": epoch["operation_nonce"],
                    "attempt": len(attempted),
                },
                "observed": None,
                "push": {
                    "expected_old_tip": candidate["remote_tip"],
                    "intended_head": candidate["candidate_head"],
                    "destination_ref": candidate["destination_ref"],
                    "intended_at": intended_at,
                    "result": None,
                    "attempted_heads": attempted,
                    "landed_head": (
                        prior_push.get("landed_head")
                        if isinstance(prior_push, Mapping)
                        else None
                    ),
                },
            }
        )
        push_delta: dict[str, Any] = {"integration": integration}
        if state["state"] != "pushing":
            push_delta["state"] = "pushing"
        state = self._epoch_transition(
            state,
            lease,
            "push_intent",
            {"delta": push_delta},
            at=intended_at,
        )
        intent_digest = self._tail_event_digest(state, "push_intent")

        def intent_current() -> bool:
            return self._tail_event_digest(state, "push_intent") == intent_digest

        def persist(result: chain_core.FencedProcessResult) -> None:
            nonlocal state
            next_integration = copy.deepcopy(state["integration"])
            next_push = copy.deepcopy(next_integration["push"])
            next_push["result"] = {
                "classification": self._push_classification(
                    result, str(next_push["destination_ref"])
                ),
                "exit": result.returncode,
                "inflight_digest": result.fence_digest,
                "output_digest": result.output_digest,
                "launch_failed": result.launch_failed,
                "timed_out": result.timed_out,
                "output_limit_exceeded": result.output_limit,
                "recorded_at": chain_core.iso_z(),
            }
            next_integration["push"] = next_push
            state = self._epoch_transition(
                state,
                lease,
                "condition_recorded",
                {"delta": {"integration": next_integration}},
            )

        environment = os.environ.copy()
        environment.pop("FORGE_SESSION_PID", None)
        environment.update(
            {
                "LC_ALL": "C",
                "LANG": "C",
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_NO_LAZY_FETCH": "1",
            }
        )
        chain_core.run_fenced_command(
            lock,
            operation="push",
            intent_digest=intent_digest,
            intent_validator=intent_current,
            argv=[
                "git",
                "--no-pager",
                "-C",
                str(state["worktree"]["path"]),
                "push",
                "--porcelain",
                "origin",
                (
                    f"{candidate['candidate_head']}:"
                    f"{candidate['destination_ref']}"
                ),
            ],
            cwd=Path(str(state["worktree"]["path"])),
            persist_result=persist,
            env=environment,
            timeout=runtime.COMMAND_TIMEOUT_SECONDS,
            cap=runtime.OUTPUT_CAP_BYTES,
            verbose=self.ctx.options.verbose,
        )
        state = self._run_remote_observation(
            state,
            lock,
            lease,
            budget,
            phase="post-push",
        )
        if state["state"] == "pushing":
            condition = state["integration"]["condition"]
            classification = state["integration"].get("push", {}).get(
                "result", {}
            ).get("classification")
            if chain_core._merge_old_tip_all_false(state):
                if classification != "known-failure":
                    return state
                condition = "push-failed"
            reason = (
                V2ReasonCode.PUSH_OUTCOME_UNKNOWN
                if condition == "push-outcome-unknown"
                else V2ReasonCode.PUSH_FAILED
            )
            raise chain_core._merge_refusal(
                reason,
                (
                    "forge: merge push outcome cannot be observed authoritatively"
                    if reason == V2ReasonCode.PUSH_OUTCOME_UNKNOWN
                    else "forge: merge push failed"
                ),
                remediation=f"forge merge recover --chain-id {state['chain_id']}",
                chain=state,
            )
        return state

    def _park_integrated_review(
        self, state: dict[str, Any], lease: chain_core.ChainLease
    ) -> dict[str, Any]:
        integration = copy.deepcopy(state["integration"])
        engine._reset_merge_nonmovement_counter(integration)
        integration["epoch"] = None
        integration["condition"] = "none"
        integration["primary_condition"] = "none"
        prior_review = state.get("review")
        iteration = (
            prior_review.get("iteration")
            if isinstance(prior_review, Mapping)
            else None
        )
        retained_review = {"iteration": iteration} if type(iteration) is int else {}
        projection = {
            "state": "reviewing",
            "integration": integration,
            "review": retained_review,
            "approval": {},
            "authorization": {},
        }
        return self._epoch_transition(
            state,
            lease,
            "reverification_result",
            {
                "delta": {
                    name: value
                    for name, value in projection.items()
                    if state.get(name) != value
                }
            },
        )

    def _release_to_closed_locked(
        self,
        state: dict[str, Any],
        lease: chain_core.ChainLease,
    ) -> dict[str, Any]:
        """Commit the FR-237 close cutoff while the ordered locks are held."""

        chain_core._require_merge_integration_control("nonforce-cleanup")
        claim = state["worktree"]["claim"]
        if claim.get("status") != "owned":
            raise FrozenError(
                "pushed merge ownership is not acquired at cleanup cutoff",
                chain_id=str(state["chain_id"]),
                observed=str(claim.get("status")),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        push = state.get("integration", {}).get("push")
        if not isinstance(push, Mapping):
            raise FrozenError(
                "cleanup cutoff lacks authenticated push containment",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        with self.store.event_lock(str(state["chain_id"])):
            replay = self.store._read_replay_locked(str(state["chain_id"]))
        cleanup_evidence = chain_core._merge_cleanup_evidence_history(replay.events)
        summary = chain_core._merge_cleanup_history_summary(replay.events)
        containment_result = summary.get("remote_containment")
        containment_observation = (
            containment_result.get("observation")
            if isinstance(containment_result, Mapping)
            else None
        )
        if not (
            cleanup_evidence
            and cleanup_evidence[-1].get("event") == "cleanup_result"
            and isinstance(containment_observation, Mapping)
            and containment_observation.get("landed_head")
            == push.get("landed_head")
            and containment_observation.get("contained") is True
            and summary.get("worktree_complete") is True
            and summary.get("branch_complete") is True
            and state.get("cleanup") == {"condition": "none"}
        ):
            raise FrozenError(
                "cleanup cutoff lacks the complete durable step history",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        preconditions = {
            "schema": chain_core._MERGE_CLEANUP_CLOSE_SCHEMA,
            "chain_id": state["chain_id"],
            "source_state": state["state"],
            "landed_head": push["landed_head"],
            "containment_observation": copy.deepcopy(
                dict(containment_observation)
            ),
            "cleanup_evidence": cleanup_evidence,
        }
        state = self._epoch_transition(
            state,
            lease,
            "ownership_release_intent",
            {
                "target_terminal": "closed",
                "terminal_disposition": "ordinary",
                "source_state": state["state"],
                "terminal_preconditions_digest": sha256_bytes(
                    chain_core.canonical_bytes(preconditions)
                ),
                "release_mode": "acquired",
            },
        )
        release_intent_digest = self._tail_event_digest(
            state, "ownership_release_intent"
        )
        observed_claim = engine._remove_merge_claim(self.store, state, unlink=False)
        observation = {
            "claim_path": state["worktree"]["claim"]["path"],
            "exists": True,
            "inode": observed_claim.inode,
            "digest": observed_claim.digest,
        }
        state = self._epoch_transition(
            state,
            lease,
            "ownership_released",
            {
                "release_intent_digest": release_intent_digest,
                "release_mode": "acquired",
                "terminal_disposition": "ordinary",
                "claim_inode": state["worktree"]["claim"]["inode"],
                "claim_digest": state["worktree"]["claim"]["digest"],
                "claim_observation_digest": sha256_bytes(
                    chain_core.canonical_bytes(observation)
                ),
            },
        )
        terminal = self._epoch_transition(
            state,
            lease,
            "closed",
            {"delta": {"state": "closed"}},
        )
        try:
            engine._remove_merge_claim(self.store, terminal)
        except (FrozenError, OSError):
            # The event-authoritative terminal release remains valid when its
            # materialized tombstone cannot be collected in this invocation.
            pass
        return terminal

    def _cleanup_result_locked(
        self,
        state: dict[str, Any],
        lease: chain_core.ChainLease,
        *,
        result: Mapping[str, Any],
    ) -> dict[str, Any]:
        outcome = result.get("outcome")
        if not isinstance(outcome, str) or outcome not in {
            "passed",
            "already-absent",
            "failed",
        }:
            raise FrozenError(
                "merge cleanup result has an invalid closed outcome",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        failed = outcome == "failed"
        delta: dict[str, Any] = {
            "cleanup": {"condition": "cleanup-failed" if failed else "none"}
        }
        if failed and state["state"] != "cleanup_pending":
            delta["state"] = "cleanup_pending"
        return self._epoch_transition(
            state,
            lease,
            "cleanup_result",
            {
                "delta": delta,
                "cleanup_results": [copy.deepcopy(dict(result))],
            },
        )

    def _run_cleanup_child(
        self,
        state: dict[str, Any],
        lock: chain_core.CommonRebaseLock,
        lease: chain_core.ChainLease,
        *,
        operation: str,
        fence_operation: str,
        subject: Mapping[str, Any],
        argv: Sequence[str],
        observe: Callable[
            [chain_core.FencedProcessResult], tuple[str, Mapping[str, Any]]
        ],
    ) -> tuple[dict[str, Any], chain_core.FencedProcessResult, dict[str, Any]]:
        recovery: dict[str, Any] | None = None
        existing_cleanup = state.get("cleanup")
        existing_intent = (
            existing_cleanup.get("intent")
            if isinstance(existing_cleanup, Mapping)
            else None
        )
        if (
            isinstance(existing_intent, Mapping)
            and existing_intent.get("schema") == chain_core._MERGE_CLEANUP_INTENT_SCHEMA
        ):
            with self.store.event_lock(str(state["chain_id"])):
                replay = self.store._read_replay_locked(str(state["chain_id"]))
            unmatched = chain_core._merge_cleanup_unmatched_intent(replay.events)
            if not (
                operation == "remote-fetch"
                and isinstance(unmatched, Mapping)
                and chain_core._recovery_cleanup_intent(unmatched) == existing_intent
                and chain_core._merge_cleanup_retry_proof_valid(replay.events, unmatched)
            ):
                raise FrozenError(
                    "cleanup pending intent lacks its exact recovery proof",
                    chain_id=str(state["chain_id"]),
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            recovery = {
                "schema": chain_core._MERGE_CLEANUP_RECOVERY_SCHEMA,
                "intent_event_digest": unmatched["digest"],
                "operation": existing_intent["operation"],
                "fence_operation": existing_intent["fence_operation"],
                "recovery_event_digest": replay.events[-1]["digest"],
            }
        intent = {
            "schema": chain_core._MERGE_CLEANUP_INTENT_SCHEMA,
            "operation": operation,
            "fence_operation": fence_operation,
            "operation_nonce": secrets.token_hex(16),
            "generation_digest": state["candidate"]["generation_digest"],
            "subject": copy.deepcopy(dict(subject)),
            "argv": list(argv),
            "cwd": str(self.ctx.repo.root),
            "started_at": chain_core.iso_z(),
        }
        if recovery is not None:
            intent["recovery"] = recovery
        if not chain_core._merge_cleanup_intent_valid(intent, state):
            raise FrozenError(
                "cleanup child intent is malformed",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        cleanup = {
            "condition": str(state["cleanup"]["condition"]),
            "intent": intent,
        }
        state = self._epoch_transition(
            state,
            lease,
            "cleanup_intent",
            {"delta": {"cleanup": cleanup}},
        )
        intent_digest = self._tail_event_digest(state, "cleanup_intent")
        holder: dict[str, Any] = {}

        def intent_current() -> bool:
            try:
                fresh = self.store.load_locked(str(state["chain_id"]), lease=lease)
            except (FrozenError, OSError):
                return False
            return bool(
                fresh.get("cleanup") == cleanup
                and self._tail_event_digest(fresh, "cleanup_intent")
                == intent_digest
            )

        def persist(result: chain_core.FencedProcessResult) -> None:
            nonlocal state
            outcome, observation = observe(result)
            evidence = {
                "schema": chain_core._MERGE_CLEANUP_RESULT_SCHEMA,
                "operation": operation,
                "fence_operation": fence_operation,
                "operation_nonce": intent["operation_nonce"],
                "intent_event_digest": intent_digest,
                "outcome": outcome,
                "observation": copy.deepcopy(dict(observation)),
                "process": engine._merge_cleanup_process_record(result),
            }
            state = self._cleanup_result_locked(
                state, lease, result=evidence
            )
            holder["result"] = result
            holder["evidence"] = evidence

        environment = os.environ.copy()
        environment.pop("FORGE_SESSION_PID", None)
        environment.update(
            {
                "LC_ALL": "C",
                "LANG": "C",
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_NO_LAZY_FETCH": "1",
            }
        )
        try:
            returned = chain_core.run_fenced_command(
                lock,
                operation=fence_operation,
                intent_digest=intent_digest,
                intent_validator=intent_current,
                argv=argv,
                cwd=self.ctx.repo.root,
                persist_result=persist,
                env=environment,
                timeout=runtime.COMMAND_TIMEOUT_SECONDS,
                cap=runtime.OUTPUT_CAP_BYTES,
                verbose=self.ctx.options.verbose,
            )
        except chain_core.CommonLockUnavailable:
            # ``run_fenced_command`` uses this exception only before its start
            # byte can authorize the child.  Close that durable intent with an
            # authenticated no-execution failure so an ordinary publication
            # failure cannot strand or silently overwrite the cleanup window.
            absent = chain_core.FencedProcessResult(
                argv=list(argv),
                returncode=None,
                duration_seconds=0.0,
                output=b"",
                output_digest=sha256_bytes(b""),
                timed_out=False,
                output_limit=False,
                launch_failed=True,
                group_survived=False,
                authorized=False,
                fence_digest=None,  # type: ignore[arg-type]
                fence_inode=None,  # type: ignore[arg-type]
            )
            persist(absent)
            raise
        result = holder.get("result")
        evidence = holder.get("evidence")
        if (
            not isinstance(result, chain_core.FencedProcessResult)
            or not isinstance(evidence, dict)
            or returned != result
            or evidence.get("process") != engine._merge_cleanup_process_record(result)
        ):
            raise FrozenError(
                "cleanup child produced no durable result",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        return state, result, evidence

    @staticmethod
    def _current_merge_authority(state: Mapping[str, Any]) -> bool:
        return chain_core._merge_current_authority_valid(state)

    def _complete_pending_release_locked(
        self,
        state: dict[str, Any],
        lease: chain_core.ChainLease,
        *,
        expected_target: str | None = None,
    ) -> tuple[dict[str, Any], str]:
        """Resume only the event-selected ownership terminal transaction."""

        claim = state.get("worktree", {}).get("claim")
        if not isinstance(claim, Mapping) or claim.get("status") not in {
            "releasing",
            "released",
        }:
            return state, "ordinary"
        with self.store.event_lock(str(state["chain_id"])):
            replay = self.store._read_replay_locked(str(state["chain_id"]))
        intent = next(
            (
                event
                for event in reversed(replay.events)
                if event.get("event") == "ownership_release_intent"
            ),
            None,
        )
        if not isinstance(intent, Mapping) or not isinstance(
            intent.get("payload"), Mapping
        ):
            raise FrozenError(
                "pending ownership release lacks its authenticated intent",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        release = intent["payload"]
        target = str(release.get("target_terminal"))
        mode = str(release.get("release_mode"))
        disposition = str(release.get("terminal_disposition"))
        if target not in {"closed", "aborted"} or mode not in {
            "acquired",
            "never-published",
        }:
            raise FrozenError(
                "pending ownership release carries an invalid terminal selection",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        if expected_target is not None and target != expected_target:
            raise chain_core._merge_refusal(
                V2ReasonCode.STATE_PRECONDITION,
                "forge: merge cleanup refused — pending ownership release selects another terminal",
                expected=expected_target,
                observed=target,
                remediation=f"forge merge recover --chain-id {state['chain_id']}",
                chain=state,
            )
        if claim.get("status") == "releasing":
            if mode == "acquired":
                observed_claim = engine._remove_merge_claim(
                    self.store, state, unlink=False
                )
                observation = {
                    "claim_path": claim["path"],
                    "exists": True,
                    "inode": observed_claim.inode,
                    "digest": observed_claim.digest,
                }
            else:
                if not engine._merge_unpublished_claim_absent(state, self.store):
                    raise FrozenError(
                        "never-published release observed an ownership pathname",
                        chain_id=str(state["chain_id"]),
                        schema=REVISION9_OUTPUT_SCHEMA,
                    )
                observation = {
                    "claim_path": claim["path"],
                    "exists": False,
                    "inode": None,
                    "digest": None,
                }
            state = self._epoch_transition(
                state,
                lease,
                "ownership_released",
                {
                    "release_intent_digest": intent["digest"],
                    "release_mode": mode,
                    "terminal_disposition": disposition,
                    "claim_inode": claim.get("inode"),
                    "claim_digest": claim.get("digest"),
                    "claim_observation_digest": sha256_bytes(
                        chain_core.canonical_bytes(observation)
                    ),
                },
            )
        if state["worktree"]["claim"]["status"] != "released":
            raise FrozenError(
                "ownership release result did not materialize released truth",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        terminal_payload: dict[str, Any] = {"delta": {"state": target}}
        if disposition == "historical-landed-superseded":
            push = state.get("integration", {}).get("push")
            observed = state.get("integration", {}).get("observed")
            if not isinstance(push, Mapping) or not isinstance(observed, Mapping):
                raise FrozenError(
                    "historical release lost its containment evidence",
                    chain_id=str(state["chain_id"]),
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            terminal_payload = {
                "terminal_disposition": disposition,
                "landed_head": push.get("landed_head"),
                "superseded_head": push.get("intended_head"),
                "observation_digest": observed.get("output_digest"),
            }
        state = self._epoch_transition(
            state, lease, target, terminal_payload
        )
        if mode == "acquired":
            try:
                engine._remove_merge_claim(self.store, state)
            except (FrozenError, OSError):
                pass
        return state, disposition

    def _resume_pending_release(
        self,
        state: dict[str, Any],
        *,
        expected_target: str | None = None,
    ) -> tuple[dict[str, Any], str] | None:
        """Complete an event-selected terminal cutoff without the common lock."""

        claim = state.get("worktree", {}).get("claim")
        if (
            not isinstance(claim, Mapping)
            or claim.get("status") not in {"releasing", "released"}
            or state.get("state") in {"closed", "aborted"}
        ):
            return None
        # A chain-only completion may not reclaim an abandoned lease: that
        # requires repository-wide recovery exclusion.  If the published
        # lease name already exists, route the caller through its ordinary
        # common-lock recovery path instead of spending a second, shorter
        # acquisition budget here.
        lease_path = self.store.root / f"{state['chain_id']}.lock"
        try:
            lease_path.lstat()
        except FileNotFoundError:
            pass
        except OSError:
            return None
        else:
            return None
        binding = state.get("run_binding")
        with self.store._journal_outer(
            binding if isinstance(binding, Mapping) else None
        ):
            with chain_core.acquire_chain_lease(
                self.store.root,
                chain_id=str(state["chain_id"]),
                session=self.store._session(None),
                single_attempt=True,
            ) as lease:
                current = self.store.load_locked(
                    str(state["chain_id"]), lease=lease
                )
                current_claim = current.get("worktree", {}).get("claim")
                if (
                    not isinstance(current_claim, Mapping)
                    or current_claim.get("status") not in {"releasing", "released"}
                    or current.get("state") in {"closed", "aborted"}
                ):
                    raise chain_core._merge_refusal(
                        V2ReasonCode.STATE_PRECONDITION,
                        "forge: pending ownership release changed before completion",
                        expected=str(claim.get("status")),
                        observed=str(
                            current_claim.get("status")
                            if isinstance(current_claim, Mapping)
                            else None
                        ),
                        remediation=f"forge status --chain-id {state['chain_id']}",
                        chain=current,
                    )
                return self._complete_pending_release_locked(
                    current, lease, expected_target=expected_target
                )

    def _attempted_release_preconditions_locked(
        self,
        state: dict[str, Any],
        lock: chain_core.CommonRebaseLock,
        *,
        expected_containment: str,
        observation_event_digest: str,
        terminal_disposition: str,
    ) -> dict[str, Any]:
        """Revalidate and bind one post-attempt logical-release cutoff.

        Operator prose is deliberately not a parameter: the replay-verifiable
        preimage pins ``"reason": None`` so a later caller cannot believe the
        text is bound.
        """

        lock.assert_held()
        containment, vector = chain_core._merge_containment(state)
        integration = state.get("integration")
        push = integration.get("push") if isinstance(integration, Mapping) else None
        observed = (
            integration.get("observed") if isinstance(integration, Mapping) else None
        )
        attempted = (
            list(push.get("attempted_heads", []))
            if isinstance(push, Mapping)
            else []
        )
        if (
            state.get("state") != "pushing"
            or containment != expected_containment
            or not vector
            or not isinstance(push, Mapping)
            or not isinstance(observed, Mapping)
            or chain_core.SHA256_RE.fullmatch(observation_event_digest) is None
            or (
                expected_containment == "older"
                and (len(attempted) < 2 or len(set(attempted)) < 2)
            )
        ):
            raise FrozenError(
                "attempted merge release lacks its exact containment tuple",
                chain_id=str(state.get("chain_id") or "") or None,
                observed=containment,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        worktree = Path(str(state["worktree"]["path"]))
        repository = chain_core.Repository(worktree)
        current_head = repository.head()
        status = engine._merge_worktree_status(
            repository,
            Path(str(state["worktree"]["git_dir"])),
            verb="merge abort",
        )
        branch_result = repository.git(
            ["symbolic-ref", "--quiet", "HEAD"], check=False
        )
        try:
            current_branch = branch_result.stdout.rstrip(b"\n").decode("utf-8")
        except UnicodeDecodeError as exc:
            raise FrozenError(
                "attempted merge release branch is not UTF-8",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            ) from exc
        if (
            status != b""
            or current_head != state["candidate"]["candidate_head"]
            or branch_result.returncode != 0
            or current_branch != state["branch"]
        ):
            raise FrozenError(
                "attempted merge release worktree identity changed",
                chain_id=str(state["chain_id"]),
                observed=(
                    f"head={current_head};branch={current_branch};"
                    f"status={sha256_bytes(status)}"
                ),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        with self.store.event_lock(str(state["chain_id"])):
            replay = self.store._read_replay_locked(str(state["chain_id"]))
        observation_event = next(
            (
                event
                for event in reversed(replay.events)
                if event.get("digest") == observation_event_digest
            ),
            None,
        )
        if (
            not isinstance(observation_event, Mapping)
            or observation_event.get("event") != "push_observed"
        ):
            raise FrozenError(
                "attempted merge release lacks its fresh observation event",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        push_intent_digests = [
            str(event["digest"])
            for event in replay.events
            if event.get("event") == "push_intent"
        ]
        push_result_digests: list[str] = []
        for event, prior, current, _records, _source in replay.entries:
            prior_push = (
                prior.get("integration", {}).get("push")
                if isinstance(prior, Mapping)
                else None
            )
            current_push = current.get("integration", {}).get("push")
            prior_result = (
                prior_push.get("result") if isinstance(prior_push, Mapping) else None
            )
            current_result = (
                current_push.get("result")
                if isinstance(current_push, Mapping)
                else None
            )
            if current_result != prior_result and isinstance(current_result, Mapping):
                push_result_digests.append(str(event["digest"]))
        if len(push_intent_digests) != len(attempted):
            raise FrozenError(
                "attempted merge release history diverges from its push intents",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        return {
            "schema": "forge-merge-attempted-release-preconditions/1",
            "chain_id": state["chain_id"],
            "source_state": state["state"],
            "target_terminal": "aborted",
            "terminal_disposition": terminal_disposition,
            # The optional operator prose is not durable elsewhere and cannot
            # participate in a replay-verifiable safety cutoff.
            "reason": None,
            "attempted_heads": attempted,
            "attempted_head_containment": [
                {"head": head, "contained": contained}
                for head, contained in zip(attempted, vector)
            ],
            "landed_head": push.get("landed_head"),
            "superseded_head": push.get("intended_head"),
            "observation": copy.deepcopy(dict(observed)),
            "observation_event_digest": observation_event_digest,
            "push_intent_event_digests": push_intent_digests,
            "push_result_event_digests": push_result_digests,
            "worktree_identity": {
                name: state["worktree"][name]
                for name in ("path", "git_dir", "common_dir")
            },
            "branch": state["branch"],
            "current_head": current_head,
            "status_output_digest": sha256_bytes(status),
            "unresolved_fence_digests": [],
        }

    def _release_historical_landing_locked(
        self,
        state: dict[str, Any],
        lock: chain_core.CommonRebaseLock,
        lease: chain_core.ChainLease,
        *,
        observation_event_digest: str | None = None,
    ) -> dict[str, Any]:
        """Release only an inactive newer head after older-only landing truth."""

        if not engine._merge_inactive(state):
            raise FrozenError(
                "historical merge release requires inactive authority",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        selected_observation = observation_event_digest or self._tail_event_digest(
            state, "push_observed"
        )
        if selected_observation is None:
            raise FrozenError(
                "historical merge release lacks a fresh observation",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        preconditions = self._attempted_release_preconditions_locked(
            state,
            lock,
            expected_containment="older",
            observation_event_digest=selected_observation,
            terminal_disposition="historical-landed-superseded",
        )
        claim = state["worktree"]["claim"]
        state = self._epoch_transition(
            state,
            lease,
            "ownership_release_intent",
            {
                "target_terminal": "aborted",
                "terminal_disposition": "historical-landed-superseded",
                "source_state": state["state"],
                "terminal_preconditions_digest": sha256_bytes(
                    chain_core.canonical_bytes(preconditions)
                ),
                "release_mode": "acquired",
            },
        )
        release_intent_digest = self._tail_event_digest(
            state, "ownership_release_intent"
        )
        observed_claim = engine._remove_merge_claim(self.store, state, unlink=False)
        observation = {
            "claim_path": claim["path"],
            "exists": True,
            "inode": observed_claim.inode,
            "digest": observed_claim.digest,
        }
        state = self._epoch_transition(
            state,
            lease,
            "ownership_released",
            {
                "release_intent_digest": release_intent_digest,
                "release_mode": "acquired",
                "terminal_disposition": "historical-landed-superseded",
                "claim_inode": claim["inode"],
                "claim_digest": claim["digest"],
                "claim_observation_digest": sha256_bytes(
                    chain_core.canonical_bytes(observation)
                ),
            },
        )
        push = state["integration"]["push"]
        observed = state["integration"]["observed"]
        terminal = self._epoch_transition(
            state,
            lease,
            "aborted",
            {
                "terminal_disposition": "historical-landed-superseded",
                "landed_head": push["landed_head"],
                "superseded_head": push["intended_head"],
                "observation_digest": observed["output_digest"],
            },
        )
        try:
            engine._remove_merge_claim(self.store, terminal)
        except (FrozenError, OSError):
            pass
        return terminal

    def _record_foreign_git_locked(
        self, state: dict[str, Any], lease: chain_core.ChainLease
    ) -> dict[str, Any]:
        integration = state.get("integration")
        if not isinstance(integration, Mapping):
            raise FrozenError(
                "merge integration projection is malformed",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        if integration.get("condition") == "foreign-git-state":
            return state
        updated = copy.deepcopy(dict(integration))
        updated.update(
            {"condition": "foreign-git-state", "primary_condition": "none"}
        )
        engine._reset_merge_nonmovement_counter(updated)
        return self._epoch_transition(
            state,
            lease,
            "condition_recorded",
            {"delta": {"integration": updated}},
        )

    def _restore_integrated_rebase_observation_intent_locked(
        self, state: dict[str, Any], lease: chain_core.ChainLease
    ) -> tuple[dict[str, Any], Mapping[str, Any] | None]:
        """Restore the raw rebase fact after a crash in a read-only proof leg."""

        integration = state.get("integration")
        current_intent = (
            integration.get("intent") if isinstance(integration, Mapping) else None
        )
        phase = (
            current_intent.get("phase")
            if isinstance(current_intent, Mapping)
            else None
        )
        prefix = "forge-integrated-observation:"
        if not isinstance(phase, str) or not phase.startswith(prefix):
            return state, current_intent if isinstance(current_intent, Mapping) else None
        source_intent = current_intent.get("source_intent")
        parts = phase.split(":")
        if (
            len(parts) != 3
            or parts[0] != "forge-integrated-observation"
            or parts[1] not in {"branch", "head", "status", "ancestry"}
            or parts[2] not in {"intent", "result"}
            or current_intent.get("observation_step") != parts[1]
            or not isinstance(source_intent, Mapping)
        ):
            return state, None
        source_state = copy.deepcopy(state)
        source_state["integration"]["intent"] = copy.deepcopy(dict(source_intent))
        binding = engine._merge_rebase_integrated_observation_binding(
            source_state, source_intent
        )
        pre_rebase = source_state["integration"].get("pre_rebase")
        epoch = source_state["integration"].get("epoch")
        if (
            binding is None
            or not isinstance(pre_rebase, Mapping)
            or not isinstance(epoch, Mapping)
            or current_intent.get("operation") != "rebase"
            or current_intent.get("operation_nonce") != epoch.get("operation_nonce")
            or current_intent.get("pre_operation_head") != pre_rebase.get("head")
            or current_intent.get("fetched_tip") != pre_rebase.get("fetched_tip")
            or current_intent.get("branch") != source_state.get("branch")
            or current_intent.get("generation_digest")
            != pre_rebase.get("generation_digest")
            or current_intent.get("reflog_action")
            != chain_core._merge_rebase_action(source_state)
            or current_intent.get("observation_binding") != binding
        ):
            return state, None
        restored = copy.deepcopy(state["integration"])
        restored["intent"] = copy.deepcopy(dict(source_intent))
        state = self._epoch_transition(
            state,
            lease,
            "rebase_intent",
            {"delta": {"integration": restored}},
        )
        return state, source_intent

    def _run_integrated_rebase_observation_locked(
        self,
        state: dict[str, Any],
        lock: chain_core.CommonRebaseLock,
        lease: chain_core.ChainLease,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """Collect the integrated-result tuple through durable fenced reads."""

        chain_core._require_merge_integration_control("observation-first-recovery")
        state, source_intent = (
            self._restore_integrated_rebase_observation_intent_locked(state, lease)
        )
        integration = state.get("integration")
        pre_rebase = (
            integration.get("pre_rebase")
            if isinstance(integration, Mapping)
            else None
        )
        epoch = integration.get("epoch") if isinstance(integration, Mapping) else None
        action = chain_core._merge_rebase_action(state)
        if (
            not isinstance(source_intent, Mapping)
            or not isinstance(pre_rebase, Mapping)
            or not isinstance(epoch, Mapping)
            or action is None
        ):
            return state, None
        observation_binding = engine._merge_rebase_integrated_observation_binding(
            state, source_intent
        )
        if observation_binding is None:
            return state, None
        identity = {
            "operation_nonce": epoch.get("operation_nonce"),
            "pre_operation_head": pre_rebase.get("head"),
            "fetched_tip": pre_rebase.get("fetched_tip"),
            "branch": state.get("branch"),
            "generation_digest": pre_rebase.get("generation_digest"),
            "reflog_action": action,
        }
        worktree = Path(str(state["worktree"]["path"]))
        environment = engine._merge_scope_environment()
        environment.pop("FORGE_SESSION_PID", None)
        step_results: dict[str, dict[str, Any]] = {}
        output_digests: dict[str, str] = {}

        def restore_source() -> None:
            nonlocal state
            state, _restored = (
                self._restore_integrated_rebase_observation_intent_locked(
                    state, lease
                )
            )

        def run_step(
            name: str,
            argv: Sequence[str],
            *,
            allowed_exits: frozenset[int] = frozenset({0}),
        ) -> bytes | None:
            nonlocal state
            observation_intent = {
                "operation": "rebase",
                **identity,
                "phase": f"forge-integrated-observation:{name}:intent",
                "observation_binding": observation_binding,
                "observation_step": name,
                "prior_output_digests": copy.deepcopy(output_digests),
                "source_intent": copy.deepcopy(dict(source_intent)),
                "started_at": chain_core.iso_z(),
            }
            updated = copy.deepcopy(state["integration"])
            updated["intent"] = copy.deepcopy(observation_intent)
            state = self._epoch_transition(
                state,
                lease,
                "rebase_intent",
                {"delta": {"integration": updated}},
            )
            intent_digest = self._tail_event_digest(state, "rebase_intent")

            def intent_current() -> bool:
                try:
                    fresh = self.store.load_locked(
                        str(state["chain_id"]), lease=lease
                    )
                    return bool(
                        fresh.get("state") == state.get("state")
                        and fresh.get("integration", {}).get("condition") == "none"
                        and fresh.get("integration", {}).get("intent")
                        == observation_intent
                        and self._tail_event_digest(fresh, "rebase_intent")
                        == intent_digest
                    )
                except (FrozenError, KeyError, OSError, Refusal, ValueError):
                    return False

            def persist_observation(result: chain_core.FencedProcessResult) -> None:
                nonlocal state
                result_intent = {
                    **copy.deepcopy(observation_intent),
                    "phase": f"forge-integrated-observation:{name}:result",
                    "child_result": {
                        "authorized": result.authorized,
                        "exit": result.returncode,
                        "inflight_digest": result.fence_digest,
                        "output_digest": result.output_digest,
                        "launch_failed": result.launch_failed,
                        "timed_out": result.timed_out,
                        "output_limit_exceeded": result.output_limit,
                        "group_survived": result.group_survived,
                    },
                    "recorded_at": chain_core.iso_z(),
                }
                result_integration = copy.deepcopy(state["integration"])
                result_integration["intent"] = result_intent
                state = self._epoch_transition(
                    state,
                    lease,
                    "rebase_intent",
                    {"delta": {"integration": result_integration}},
                )

            result = chain_core.run_fenced_command(
                lock,
                operation="containment",
                intent_digest=intent_digest,
                intent_validator=intent_current,
                argv=argv,
                cwd=worktree,
                persist_result=persist_observation,
                env=environment,
                timeout=runtime.COMMAND_TIMEOUT_SECONDS,
                cap=runtime.OUTPUT_CAP_BYTES,
                verbose=self.ctx.options.verbose,
            )
            durable = state.get("integration", {}).get("intent", {}).get(
                "child_result"
            )
            if (
                not isinstance(durable, Mapping)
                or durable.get("authorized") is not True
                or durable.get("exit") not in allowed_exits
                or durable.get("launch_failed") is not False
                or durable.get("timed_out") is not False
                or durable.get("output_limit_exceeded") is not False
                or durable.get("group_survived") is not False
                or durable.get("inflight_digest") != result.fence_digest
                or durable.get("output_digest") != result.output_digest
                or result.returncode != durable.get("exit")
            ):
                restore_source()
                return None
            step_results[name] = {
                "intent_digest": intent_digest,
                "inflight_digest": result.fence_digest,
                "output_digest": result.output_digest,
                "exit": result.returncode,
            }
            output_digests[name] = result.output_digest
            return result.output

        branch_output = run_step(
            "branch", ["git", "--no-pager", "symbolic-ref", "-q", "HEAD"]
        )
        if branch_output is None:
            return state, None
        head_output = run_step(
            "head", ["git", "--no-pager", "rev-parse", "--verify", "HEAD"]
        )
        if head_output is None:
            return state, None
        try:
            observed_head = head_output.decode("ascii").removesuffix("\n")
        except UnicodeDecodeError:
            observed_head = ""
        if (
            chain_core.COMMIT_RE.fullmatch(observed_head) is None
            or head_output != f"{observed_head}\n".encode("ascii")
        ):
            restore_source()
            return state, None
        status_output = run_step(
            "status",
            [
                "git",
                "-c",
                "core.fsmonitor=false",
                "-c",
                "core.untrackedCache=false",
                "--no-optional-locks",
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
                "--ignore-submodules=none",
            ],
        )
        if status_output is None:
            return state, None
        ancestry_output = run_step(
            "ancestry",
            [
                "git",
                "--no-pager",
                "merge-base",
                "--is-ancestor",
                str(pre_rebase["fetched_tip"]),
                observed_head,
            ],
            allowed_exits=frozenset({0, 1}),
        )
        if ancestry_output is None:
            return state, None
        try:
            branch = branch_output.removesuffix(b"\n").decode("utf-8")
        except UnicodeDecodeError:
            branch = ""
        observation: dict[str, Any] = {
            "schema": "forge-merge-integrated-observation/1",
            "observation_binding": observation_binding,
            "operation_nonce": identity["operation_nonce"],
            "generation_digest": identity["generation_digest"],
            "pre_operation_head": identity["pre_operation_head"],
            "fetched_tip": identity["fetched_tip"],
            "branch": branch,
            "observed_head": observed_head,
            "status_digest": sha256_bytes(status_output),
            "status_empty": status_output == b"",
            "fetched_tip_ancestor": bool(
                step_results["ancestry"]["exit"] == 0 and ancestry_output == b""
            ),
            "steps": copy.deepcopy(step_results),
        }
        observation["evidence_digest"] = sha256_bytes(chain_core.canonical_bytes(observation))
        restore_source()
        return state, observation

    def _materialize_rebase_success_locked(
        self,
        state: dict[str, Any],
        lock: chain_core.CommonRebaseLock,
        lease: chain_core.ChainLease,
        *,
        fetched_tip: str,
        inflight_digest: str,
        output_digest: str,
        observation: Mapping[str, Any],
    ) -> dict[str, Any]:
        expected_head = str(observation.get("observed_head", ""))
        state, candidate_observation = self._run_candidate_observation_locked(
            state,
            lock,
            lease,
            verb="merge recover",
            remote_tip=fetched_tip,
            expected_head=expected_head,
            classify=True,
        )
        admission = self._admission_from_candidate_observation(
            state,
            candidate_observation,
            verb="merge recover",
            require_current_generation=False,
        )
        generation = engine.bind_merge_candidate_generation(
            self.ctx,
            admission,
            fetched_tip,
            generation=int(state["candidate"]["generation"]) + 1,
            observation=candidate_observation,
        )
        if (
            admission.candidate_head != expected_head
            or generation.candidate.get("candidate_head") != expected_head
            or not engine._merge_rebase_integrated_predicate(state, observation)
        ):
            raise ValueError("rebase observation changed before materialization")
        suite = engine._merge_epoch_suite(
            {
                **state,
                "candidate": generation.candidate,
                "tier": generation.tier,
            },
            admission.policy,
        )
        integration = copy.deepcopy(state["integration"])
        epoch = integration.get("epoch")
        pre_rebase = integration.get("pre_rebase")
        if not isinstance(epoch, Mapping) or not isinstance(pre_rebase, Mapping):
            raise FrozenError(
                "rebase result lacks its durable epoch and pre-rebase identity",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        integration.update(
            {
                "condition": "none",
                "primary_condition": "none",
                "conflict": None,
                "intent": {
                    "operation": "rebase-result",
                    "operation_nonce": epoch["operation_nonce"],
                    "result": "success",
                    "pre_operation_head": pre_rebase["head"],
                    "rebased_head": generation.candidate["candidate_head"],
                    "fetched_tip": fetched_tip,
                    "inflight_digest": inflight_digest,
                    "output_digest": output_digest,
                    "recorded_at": chain_core.iso_z(),
                },
            }
        )
        integration["epoch"]["generation_digest"] = generation.candidate[
            "generation_digest"
        ]
        integration["epoch"]["gate_plan"] = self._sealed_plan(
            {**state, "candidate": generation.candidate},
            admission.policy,
            suite,
        )
        prior_review = state.get("review")
        iteration = (
            prior_review.get("iteration")
            if isinstance(prior_review, Mapping)
            else None
        )
        retained_review = {"iteration": iteration} if type(iteration) is int else {}
        rebase_projection = {
            "state": "reverifying",
            "policy_source": {
                "commit": admission.policy.sha,
                "digest": admission.policy.digest,
            },
            "candidate": copy.deepcopy(generation.candidate),
            "tier": copy.deepcopy(generation.tier),
            "steps": {},
            "review": retained_review,
            "approval": {},
            "authorization": {},
            "integration": integration,
        }
        rebase_delta = {
            name: value
            for name, value in rebase_projection.items()
            if state.get(name) != value
        }
        return self._epoch_transition(
            state,
            lease,
            "rebase_result",
            {"delta": rebase_delta},
            generation_digest=str(generation.candidate["generation_digest"]),
        )

    def _recover_rebase_observation_locked(
        self,
        state: dict[str, Any],
        lock: chain_core.CommonRebaseLock,
        lease: chain_core.ChainLease,
    ) -> dict[str, Any]:
        """Classify a crashed rebase from bounded, fenced Git observations."""

        state, restored_intent = (
            self._restore_integrated_rebase_observation_intent_locked(state, lease)
        )
        if restored_intent is None:
            return self._record_foreign_git_locked(state, lease)
        git_dir = Path(str(state["worktree"]["git_dir"]))
        integration = state.get("integration")
        pre_rebase = (
            integration.get("pre_rebase")
            if isinstance(integration, Mapping)
            else None
        )
        epoch = integration.get("epoch") if isinstance(integration, Mapping) else None
        result_class = chain_core._merge_rebase_result_classification(state)
        if (
            not isinstance(pre_rebase, Mapping)
            or not isinstance(epoch, Mapping)
            or result_class == "foreign"
        ):
            return self._record_foreign_git_locked(state, lease)
        metadata: list[str] = []
        for name in (
            "MERGE_HEAD",
            "CHERRY_PICK_HEAD",
            "REVERT_HEAD",
            "BISECT_LOG",
            "rebase-apply",
            "rebase-merge",
            "sequencer",
        ):
            try:
                os.lstat(git_dir / name)
            except FileNotFoundError:
                continue
            except OSError:
                return self._record_foreign_git_locked(state, lease)
            metadata.append(name)
        rebase_live = any(name in metadata for name in ("rebase-merge", "rebase-apply"))
        if rebase_live:
            intent = integration.get("intent")
            exact_nonzero = bool(
                isinstance(intent, Mapping)
                and result_class == "failed"
                and type(intent.get("exit")) is int
                and intent.get("exit") != 0
                and intent.get("launch_failed") is False
                and intent.get("timed_out") is False
                and intent.get("output_limit_exceeded") is False
                and intent.get("group_survived") is False
            )
            if result_class != "absent" and not exact_nonzero:
                return self._record_foreign_git_locked(state, lease)
            state, observation = self._run_conflict_observation_locked(
                state, lock, lease, kind="conflict"
            )
            if observation is None:
                return self._record_foreign_git_locked(state, lease)
            integration = state["integration"]
            intent = integration.get("intent")
            result_class = chain_core._merge_rebase_result_classification(state)
            exact_nonzero = bool(
                isinstance(intent, Mapping)
                and result_class == "failed"
                and type(intent.get("exit")) is int
                and intent.get("exit") != 0
                and intent.get("launch_failed") is False
                and intent.get("timed_out") is False
                and intent.get("output_limit_exceeded") is False
                and intent.get("group_survived") is False
            )
            evidence_digest = sha256_bytes(chain_core.canonical_bytes(observation))
            inflight_digest = (
                str(intent["inflight_digest"])
                if isinstance(intent, Mapping) and exact_nonzero
                else evidence_digest
            )
            output_digest = (
                str(intent["output_digest"])
                if isinstance(intent, Mapping) and exact_nonzero
                else evidence_digest
            )
            updated = copy.deepcopy(dict(integration))
            updated["conflict"] = engine._merge_conflict_record(
                state,
                observation,
                inflight_digest=inflight_digest,
                output_digest=output_digest,
            )
            engine._reset_merge_nonmovement_counter(updated)
            return self._epoch_transition(
                state,
                lease,
                "rebase_conflict",
                {"delta": {"state": "rebase_conflict", "integration": updated}},
            )
        if metadata:
            return self._record_foreign_git_locked(state, lease)
        state, observation = self._run_integrated_rebase_observation_locked(
            state, lock, lease
        )
        if observation is None:
            return self._record_foreign_git_locked(state, lease)
        integration = state.get("integration")
        pre_rebase = (
            integration.get("pre_rebase")
            if isinstance(integration, Mapping)
            else None
        )
        result_class = chain_core._merge_rebase_result_classification(state)
        current_head = str(observation.get("observed_head", ""))
        evidence_digest = str(observation.get("evidence_digest", ""))
        if (
            not isinstance(integration, Mapping)
            or not isinstance(pre_rebase, Mapping)
            or chain_core.SHA256_RE.fullmatch(evidence_digest) is None
            or observation.get("status_empty") is not True
            or observation.get("branch") != state.get("branch")
        ):
            return self._record_foreign_git_locked(state, lease)
        if result_class in {"absent", "success"}:
            try:
                integrated = engine._merge_rebase_integrated_predicate(state, observation)
            except (OSError, ValueError):
                integrated = False
            if integrated:
                intent = integration.get("intent")
                inflight_digest = (
                    str(intent["inflight_digest"])
                    if isinstance(intent, Mapping) and result_class == "success"
                    else evidence_digest
                )
                output_digest = (
                    str(intent["output_digest"])
                    if isinstance(intent, Mapping) and result_class == "success"
                    else evidence_digest
                )
                try:
                    return self._materialize_rebase_success_locked(
                        state,
                        lock,
                        lease,
                        fetched_tip=str(pre_rebase["fetched_tip"]),
                        inflight_digest=inflight_digest,
                        output_digest=output_digest,
                        observation=observation,
                    )
                except (KeyError, OSError, Refusal, ValueError):
                    return self._record_foreign_git_locked(state, lease)
        if current_head == pre_rebase.get("head"):
            try:
                state, candidate_observation = (
                    self._run_candidate_observation_locked(
                        state,
                        lock,
                        lease,
                        verb="merge recover",
                        remote_tip=str(state["candidate"]["remote_tip"]),
                        expected_head=str(state["candidate"]["candidate_head"]),
                        classify=False,
                    )
                )
                _observe_current_merge_candidate(
                    self.ctx,
                    state,
                    verb="merge recover",
                    observation=candidate_observation,
                )
            except (KeyError, OSError, Refusal, ValueError):
                return self._record_foreign_git_locked(state, lease)
            updated = copy.deepcopy(dict(integration))
            if result_class == "failed":
                updated.update(
                    {
                        "condition": "rebase-failed",
                        "primary_condition": "none",
                        "epoch": None,
                        "conflict": None,
                    }
                )
                next_state = "revising"
            else:
                updated.update(
                    {
                        "condition": "none",
                        "primary_condition": "none",
                        "epoch": None,
                        "intent": None,
                        "conflict": None,
                    }
                )
                next_state = "authorized"
            engine._reset_merge_nonmovement_counter(updated)
            return self._epoch_transition(
                state,
                lease,
                "rebase_result",
                {"delta": {"state": next_state, "integration": updated}},
            )
        return self._record_foreign_git_locked(state, lease)

    def _finish_recovered_epoch_locked(
        self,
        state: dict[str, Any],
        lock: chain_core.CommonRebaseLock,
        lease: chain_core.ChainLease,
        budget: engine._MergeEpochBudget,
    ) -> tuple[dict[str, Any], str]:
        state = self._run_epoch_suite(state, lock, lease, budget)
        engine._require_active_merge_epoch(state)
        if not self._current_merge_authority(state):
            return self._park_integrated_review(state, lease), "review"
        state = self._run_remote_observation(
            state, lock, lease, budget, phase="final-prepush"
        )
        if state["state"] in {"authorized", "awaiting_approval"}:
            return state, "parked"
        engine._require_active_merge_epoch(state)
        state = self._run_epoch_push(state, lock, lease, budget)
        return state, "pushed" if state["state"] == "pushed" else "observed"

    def _run_conflict_observation_locked(
        self,
        state: dict[str, Any],
        lock: chain_core.CommonRebaseLock,
        lease: chain_core.ChainLease,
        *,
        kind: str,
        paths: Sequence[str] = (),
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """Run one conflict snapshot as three bounded, durable fenced reads."""

        chain_core._require_merge_integration_control("conflict-continue-contract")
        if kind not in {"conflict", "post-add"}:
            raise ValueError("invalid conflict observation kind")
        try:
            selected_paths = (
                engine._normalize_merge_conflict_paths(paths)
                if kind == "post-add" or paths
                else ()
            )
        except (TypeError, ValueError):
            return state, None
        integration = state.get("integration")
        epoch = integration.get("epoch") if isinstance(integration, Mapping) else None
        pre_rebase = (
            integration.get("pre_rebase")
            if isinstance(integration, Mapping)
            else None
        )
        current_intent = (
            integration.get("intent") if isinstance(integration, Mapping) else None
        )
        phase = current_intent.get("phase") if isinstance(current_intent, Mapping) else None
        source_intent = (
            current_intent.get("source_intent")
            if isinstance(current_intent, Mapping)
            and isinstance(phase, str)
            and phase.startswith("forge-conflict-observation:")
            else current_intent
        )
        action = chain_core._merge_rebase_action(state)
        if (
            not isinstance(epoch, Mapping)
            or not isinstance(pre_rebase, Mapping)
            or not isinstance(source_intent, Mapping)
            or action is None
        ):
            return state, None
        identity = {
            "operation_nonce": epoch.get("operation_nonce"),
            "pre_operation_head": pre_rebase.get("head"),
            "fetched_tip": pre_rebase.get("fetched_tip"),
            "branch": state.get("branch"),
            "generation_digest": pre_rebase.get("generation_digest"),
            "reflog_action": action,
        }
        source_state = copy.deepcopy(state)
        source_state["integration"]["intent"] = copy.deepcopy(dict(source_intent))
        if not engine._merge_owned_rebase_metadata(source_state):
            return state, None
        commands: tuple[tuple[str, list[str]], ...] = (
            ("unmerged", ["git", "diff", "--name-only", "--diff-filter=U", "-z", "--"]),
            ("index", ["git", "ls-files", "--stage", "-z", "--"]),
            (
                "status",
                ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
            ),
        )
        environment = os.environ.copy()
        environment.pop("FORGE_SESSION_PID", None)
        environment.update(
            {
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_NO_LAZY_FETCH": "1",
                "GIT_REFLOG_ACTION": action,
            }
        )
        observation_nonce = secrets.token_hex(16)
        observation_binding = sha256_bytes(
            chain_core.canonical_bytes(
                {
                    "kind": kind,
                    "observation_nonce": observation_nonce,
                    "paths": list(selected_paths),
                    "source_intent": source_intent,
                }
            )
        )

        def restore_source_intent() -> None:
            nonlocal state
            if state.get("integration", {}).get("intent") == source_intent:
                return
            restored = copy.deepcopy(state["integration"])
            restored["intent"] = copy.deepcopy(dict(source_intent))
            state = self._epoch_transition(
                state,
                lease,
                "rebase_intent",
                {"delta": {"integration": restored}},
            )

        outputs: dict[str, bytes] = {}
        output_digests: dict[str, str] = {}
        worktree = Path(str(state["worktree"]["path"]))
        for name, argv in commands:
            if not engine._merge_owned_rebase_metadata(
                {
                    **state,
                    "integration": {
                        **state["integration"],
                        "intent": {
                            "operation": "continue",
                            **identity,
                        },
                    },
                }
            ):
                restore_source_intent()
                return state, None
            observation_intent = {
                "operation": "continue",
                **identity,
                "phase": f"forge-conflict-observation:{kind}:{name}:intent",
                "observation_nonce": observation_nonce,
                "observation_binding": observation_binding,
                "observation_kind": kind,
                "observation_step": name,
                "authorized_paths": list(selected_paths),
                "prior_output_digests": copy.deepcopy(output_digests),
                "source_intent": copy.deepcopy(dict(source_intent)),
                "started_at": chain_core.iso_z(),
            }
            updated = copy.deepcopy(state["integration"])
            updated["intent"] = copy.deepcopy(observation_intent)
            state = self._epoch_transition(
                state,
                lease,
                "rebase_intent",
                {"delta": {"integration": updated}},
            )
            intent_digest = self._tail_event_digest(state, "rebase_intent")

            def intent_current(
                expected: Mapping[str, Any] = observation_intent,
                expected_digest: str = intent_digest,
            ) -> bool:
                try:
                    fresh = self.store.load_locked(
                        str(state["chain_id"]), lease=lease
                    )
                    return bool(
                        fresh.get("state") == state.get("state")
                        and fresh.get("integration", {}).get("condition") == "none"
                        and fresh.get("integration", {}).get("intent") == expected
                        and self._tail_event_digest(fresh, "rebase_intent")
                        == expected_digest
                    )
                except (FrozenError, KeyError, OSError, Refusal, ValueError):
                    return False

            def persist_observation(result: chain_core.FencedProcessResult) -> None:
                nonlocal state
                result_intent = {
                    **copy.deepcopy(observation_intent),
                    "phase": f"forge-conflict-observation:{kind}:{name}:result",
                    "child_result": {
                        "authorized": result.authorized,
                        "exit": result.returncode,
                        "inflight_digest": result.fence_digest,
                        "output_digest": result.output_digest,
                        "launch_failed": result.launch_failed,
                        "timed_out": result.timed_out,
                        "output_limit_exceeded": result.output_limit,
                        "group_survived": result.group_survived,
                    },
                    "recorded_at": chain_core.iso_z(),
                }
                result_integration = copy.deepcopy(state["integration"])
                result_integration["intent"] = result_intent
                state = self._epoch_transition(
                    state,
                    lease,
                    "rebase_intent",
                    {"delta": {"integration": result_integration}},
                )

            result = chain_core.run_fenced_command(
                lock,
                operation="continue",
                intent_digest=intent_digest,
                intent_validator=intent_current,
                argv=argv,
                cwd=worktree,
                persist_result=persist_observation,
                env=environment,
                timeout=runtime.COMMAND_TIMEOUT_SECONDS,
                cap=runtime.OUTPUT_CAP_BYTES,
                verbose=self.ctx.options.verbose,
            )
            durable_result = state.get("integration", {}).get("intent", {}).get(
                "child_result"
            )
            if (
                not isinstance(durable_result, Mapping)
                or durable_result.get("authorized") is not True
                or durable_result.get("exit") != 0
                or durable_result.get("launch_failed") is not False
                or durable_result.get("timed_out") is not False
                or durable_result.get("output_limit_exceeded") is not False
                or durable_result.get("group_survived") is not False
                or durable_result.get("inflight_digest") != result.fence_digest
                or durable_result.get("output_digest") != result.output_digest
            ):
                restore_source_intent()
                return state, None
            outputs[name] = result.output
            output_digests[name] = result.output_digest
        if not engine._merge_owned_rebase_metadata(state):
            restore_source_intent()
            return state, None
        observation = (
            engine._observe_merge_conflict(
                outputs["unmerged"], outputs["index"], outputs["status"]
            )
            if kind == "conflict"
            else engine._observe_merge_post_add(
                selected_paths,
                outputs["unmerged"],
                outputs["index"],
                outputs["status"],
            )
        )
        restore_source_intent()
        return state, observation

    def _recover_conflict_locked(
        self,
        state: dict[str, Any],
        lock: chain_core.CommonRebaseLock,
        lease: chain_core.ChainLease,
        *,
        continue_rebase: bool,
        abort_rebase: bool,
        paths: Sequence[str] | None,
    ) -> dict[str, Any]:
        integration = copy.deepcopy(state["integration"])
        epoch = integration.get("epoch")
        pre_rebase = integration.get("pre_rebase")
        durable_intent = integration.get("intent")
        durable_phase = (
            durable_intent.get("phase")
            if isinstance(durable_intent, Mapping)
            else None
        )
        conflict_observation_pending = bool(
            isinstance(durable_intent, Mapping)
            and isinstance(durable_phase, str)
            and durable_phase.startswith("forge-conflict-observation:")
            and isinstance(durable_intent.get("source_intent"), Mapping)
        )
        integrated_observation_pending = bool(
            isinstance(durable_intent, Mapping)
            and isinstance(durable_phase, str)
            and durable_phase.startswith("forge-integrated-observation:")
            and isinstance(durable_intent.get("source_intent"), Mapping)
        )
        observation_pending = bool(
            conflict_observation_pending or integrated_observation_pending
        )
        prior_intent = (
            durable_intent.get("source_intent")
            if observation_pending and isinstance(durable_intent, Mapping)
            else durable_intent
        )
        prior_conflict = integration.get("conflict")
        continuation_marker = (
            prior_conflict.get("continuation_result")
            if isinstance(prior_conflict, Mapping)
            else None
        )
        abort_marker = (
            prior_conflict.get("abort_result")
            if isinstance(prior_conflict, Mapping)
            else None
        )
        abort_result_pending = bool(
            isinstance(prior_intent, Mapping)
            and prior_intent.get("operation") == "rebase-result"
            and isinstance(abort_marker, Mapping)
            and abort_marker.get("operation_nonce")
            == prior_intent.get("operation_nonce")
            and abort_marker.get("inflight_digest")
            == prior_intent.get("inflight_digest")
            and abort_marker.get("output_digest")
            == prior_intent.get("output_digest")
        )
        continuation_phase = (
            "continue-result"
            if isinstance(prior_intent, Mapping)
            and prior_intent.get("operation") == "rebase-result"
            and isinstance(continuation_marker, Mapping)
            and not abort_result_pending
            and not abort_rebase
            else str(prior_intent.get("phase"))
            if isinstance(prior_intent, Mapping)
            and prior_intent.get("operation") == "continue"
            and prior_intent.get("phase") in {"stage-result", "rebase"}
            and not abort_rebase
            else None
        )
        resume_continue = bool(
            continuation_phase is not None
            or conflict_observation_pending
            or integrated_observation_pending
            and isinstance(continuation_marker, Mapping)
            and not abort_result_pending
        )
        resume_abort = abort_result_pending
        if (
            not continue_rebase
            and not abort_rebase
            and not resume_continue
            and not resume_abort
        ):
            return state
        if not isinstance(epoch, Mapping) or not isinstance(pre_rebase, Mapping):
            return self._record_foreign_git_locked(state, lease)
        worktree = Path(str(state["worktree"]["path"]))
        reflog_action = chain_core._merge_rebase_action(state)
        if reflog_action is None:
            return self._record_foreign_git_locked(state, lease)
        identity = {
            "operation_nonce": epoch["operation_nonce"],
            "pre_operation_head": pre_rebase["head"],
            "fetched_tip": pre_rebase["fetched_tip"],
            "branch": state["branch"],
            "generation_digest": pre_rebase["generation_digest"],
            "reflog_action": reflog_action,
        }
        environment = os.environ.copy()
        environment.pop("FORGE_SESSION_PID", None)
        environment.update(
            {
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_NO_LAZY_FETCH": "1",
                "GIT_REFLOG_ACTION": reflog_action,
            }
        )

        if continue_rebase or resume_continue:
            source_paths: Sequence[str] = (
                paths or ()
                if continue_rebase
                else durable_intent.get("authorized_paths", ())
                if conflict_observation_pending
                and isinstance(durable_intent, Mapping)
                else prior_conflict.get("authorized_paths", ())
                if continuation_phase == "continue-result"
                and isinstance(prior_conflict, Mapping)
                else prior_intent.get("authorized_paths", ())
                if isinstance(prior_intent, Mapping)
                else ()
            )
            try:
                selected_paths = engine._normalize_merge_conflict_paths(source_paths)
            except (TypeError, ValueError):
                raise chain_core._merge_refusal(
                    V2ReasonCode.STATE_PRECONDITION,
                    "forge: merge recover refused — conflict paths are invalid",
                    chain=state,
                )
            conflict = integration.get("conflict")
            conflict_digest = (
                sha256_bytes(chain_core.canonical_bytes(dict(conflict)))
                if isinstance(conflict, Mapping)
                else None
            )

            def mark_foreign() -> None:
                nonlocal state
                state = self._record_foreign_git_locked(state, lease)

            def refuse_changed_conflict() -> None:
                raise chain_core._merge_refusal(
                    V2ReasonCode.STATE_PRECONDITION,
                    "forge: merge recover refused — conflict ownership or baselines changed",
                    expected="the recorded conflict set and non-conflict byte baselines",
                    observed="foreign or changed Git conflict state",
                    remediation=(
                        f"forge merge recover --abort-rebase --chain-id {state['chain_id']}"
                    ),
                    chain=state,
                )

            def phase_intent_valid(
                candidate: object, *, operation: str, phase: str
            ) -> bool:
                return bool(
                    isinstance(candidate, Mapping)
                    and candidate.get("operation") == operation
                    and candidate.get("phase") == phase
                    and candidate.get("authorized_paths") == list(selected_paths)
                    and candidate.get("conflict_digest") == conflict_digest
                    and isinstance(conflict, Mapping)
                    and candidate.get("index_baseline_digest")
                    == conflict.get("index_baseline_digest")
                    and candidate.get("status_baseline_digest")
                    == conflict.get("status_baseline_digest")
                    and all(candidate.get(name) == value for name, value in identity.items())
                )

            def exact_stage_success(candidate: Mapping[str, Any]) -> bool:
                result = candidate.get("stage_result")
                return bool(
                    isinstance(result, Mapping)
                    and result.get("authorized") is True
                    and type(result.get("exit")) is int
                    and result.get("exit") == 0
                    and result.get("launch_failed") is False
                    and result.get("timed_out") is False
                    and result.get("output_limit_exceeded") is False
                    and result.get("group_survived") is False
                    and chain_core.SHA256_RE.fullmatch(str(result.get("inflight_digest", "")))
                    is not None
                    and chain_core.SHA256_RE.fullmatch(str(result.get("output_digest", "")))
                    is not None
                )

            def classify_continue_result() -> str:
                nonlocal state
                result_intent = state.get("integration", {}).get("intent")
                current_conflict = state.get("integration", {}).get("conflict")
                marker = (
                    current_conflict.get("continuation_result")
                    if isinstance(current_conflict, Mapping)
                    else None
                )
                result_class = chain_core._merge_rebase_result_classification(state)
                if (
                    not isinstance(result_intent, Mapping)
                    or not isinstance(marker, Mapping)
                    or marker.get("operation_nonce")
                    != identity["operation_nonce"]
                    or marker.get("inflight_digest")
                    != result_intent.get("inflight_digest")
                    or marker.get("output_digest")
                    != result_intent.get("output_digest")
                ):
                    mark_foreign()
                    return "foreign"
                if result_class == "foreign":
                    mark_foreign()
                    return (
                        "failed-foreign"
                        if result_intent.get("group_survived") is True
                        else "foreign"
                    )
                normal = bool(
                    type(result_intent.get("exit")) is int
                    and result_intent.get("launch_failed") is False
                    and result_intent.get("timed_out") is False
                    and result_intent.get("output_limit_exceeded") is False
                    and result_intent.get("group_survived") is False
                    and chain_core.SHA256_RE.fullmatch(
                        str(result_intent.get("inflight_digest", ""))
                    )
                    is not None
                    and chain_core.SHA256_RE.fullmatch(
                        str(result_intent.get("output_digest", ""))
                    )
                    is not None
                )
                ordinary_nonzero = bool(
                    normal and int(result_intent.get("exit", 0)) > 0
                )
                if ordinary_nonzero:
                    state, next_conflict = self._run_conflict_observation_locked(
                        state,
                        lock,
                        lease,
                        kind="conflict",
                        paths=selected_paths,
                    )
                    if next_conflict is not None:
                        updated = copy.deepcopy(state["integration"])
                        updated["conflict"] = engine._merge_conflict_record(
                            state,
                            next_conflict,
                            inflight_digest=str(result_intent["inflight_digest"]),
                            output_digest=str(result_intent["output_digest"]),
                        )
                        updated["intent"] = {
                            "operation": "continue",
                            **identity,
                            "phase": "conflict",
                            "recorded_at": chain_core.iso_z(),
                        }
                        engine._reset_merge_nonmovement_counter(updated)
                        state = self._epoch_transition(
                            state,
                            lease,
                            "rebase_conflict",
                            {
                                "delta": {
                                    "state": "rebase_conflict",
                                    "integration": updated,
                                }
                            },
                        )
                        return "conflict"
                if normal and result_intent.get("exit") == 0:
                    state, integrated_observation = (
                        self._run_integrated_rebase_observation_locked(
                            state, lock, lease
                        )
                    )
                    if (
                        isinstance(integrated_observation, Mapping)
                        and engine._merge_rebase_integrated_predicate(
                            state, integrated_observation
                        )
                    ):
                        observed_head = str(
                            integrated_observation.get("observed_head", "")
                        )
                        try:
                            state = self._materialize_rebase_success_locked(
                                state,
                                lock,
                                lease,
                                fetched_tip=str(pre_rebase["fetched_tip"]),
                                inflight_digest=str(
                                    result_intent["inflight_digest"]
                                ),
                                output_digest=str(result_intent["output_digest"]),
                                observation=integrated_observation,
                            )
                        except (KeyError, OSError, Refusal, ValueError):
                            pass
                        else:
                            return "continued"
                    updated = copy.deepcopy(state["integration"])
                    updated.update(
                        {
                            "condition": "foreign-git-state",
                            "primary_condition": "none",
                        }
                    )
                    engine._reset_merge_nonmovement_counter(updated)
                    state = self._epoch_transition(
                        state,
                        lease,
                        "rebase_result",
                        {"delta": {"integration": updated}},
                    )
                    return "foreign"
                if not normal:
                    mark_foreign()
                    return "failed-foreign"
                state, restoration_observation = (
                    self._run_integrated_rebase_observation_locked(
                        state, lock, lease
                    )
                )
                restored = bool(
                    isinstance(restoration_observation, Mapping)
                    and restoration_observation.get("status_empty") is True
                    and restoration_observation.get("observed_head")
                    == pre_rebase.get("head")
                    and restoration_observation.get("branch") == state.get("branch")
                    and engine._merge_rebase_operation_metadata_absent(state)
                )
                if not restored:
                    mark_foreign()
                    return "failed-foreign"
                updated = copy.deepcopy(state["integration"])
                updated.update(
                    {
                        "condition": "rebase-failed",
                        "primary_condition": "none",
                        "epoch": None,
                        "conflict": None,
                    }
                )
                engine._reset_merge_nonmovement_counter(updated)
                state = self._epoch_transition(
                    state,
                    lease,
                    "rebase_result",
                    {
                        "delta": {
                            "state": "revising",
                            "integration": updated,
                        }
                    },
                )
                return "failed"

            if resume_continue:
                if not isinstance(prior_intent, Mapping):
                    mark_foreign()
                    refuse_changed_conflict()
                try:
                    durable_paths = engine._normalize_merge_conflict_paths(
                        conflict.get("authorized_paths", ())
                        if continuation_phase == "continue-result"
                        and isinstance(conflict, Mapping)
                        else durable_intent.get("authorized_paths", ())
                        if observation_pending
                        and isinstance(durable_intent, Mapping)
                        else prior_intent.get("authorized_paths", ())
                    )
                except (TypeError, ValueError):
                    durable_paths = ()
                if selected_paths != durable_paths:
                    raise chain_core._merge_refusal(
                        V2ReasonCode.STATE_PRECONDITION,
                        "forge: merge recover refused — requested paths differ from the durable continuation intent",
                        chain=state,
                    )

            if continuation_phase == "continue-result":
                disposition = classify_continue_result()
                if disposition in {"failed", "failed-foreign"}:
                    raise chain_core._merge_refusal(
                        V2ReasonCode.REBASE_FAILED,
                        "forge: merge recover refused — rebase continuation failed",
                        remediation=f"forge merge refresh --chain-id {state['chain_id']}",
                        chain=state,
                    )
                if disposition == "foreign":
                    refuse_changed_conflict()
                return state

            if continuation_phase is None:
                try:
                    stored_paths = engine._normalize_merge_conflict_paths(
                        conflict.get("authorized_paths", ())
                        if isinstance(conflict, Mapping)
                        else ()
                    )
                except (TypeError, ValueError):
                    stored_paths = ()
                if selected_paths != stored_paths:
                    raise chain_core._merge_refusal(
                        V2ReasonCode.STATE_PRECONDITION,
                        "forge: merge recover refused — requested paths differ from the recorded conflict set",
                        expected=str(list(stored_paths)),
                        observed=str(list(selected_paths)),
                        chain=state,
                    )
                state, observation = self._run_conflict_observation_locked(
                    state,
                    lock,
                    lease,
                    kind="conflict",
                    paths=selected_paths,
                )
                if observation is None:
                    mark_foreign()
                    refuse_changed_conflict()
                fresh_paths = tuple(observation["authorized_paths"])
                if selected_paths != fresh_paths:
                    raise chain_core._merge_refusal(
                        V2ReasonCode.STATE_PRECONDITION,
                        "forge: merge recover refused — requested paths differ from the exact unmerged set",
                        expected=str(list(fresh_paths)),
                        observed=str(list(selected_paths)),
                        chain=state,
                    )
                if not engine._merge_conflict_record_matches(state, observation):
                    mark_foreign()
                    refuse_changed_conflict()
                stage_intent = {
                    "operation": "continue",
                    **identity,
                    "phase": "stage",
                    "authorized_paths": list(selected_paths),
                    "conflict_digest": conflict_digest,
                    "index_baseline_digest": observation["index_baseline_digest"],
                    "status_baseline_digest": observation["status_baseline_digest"],
                    "started_at": chain_core.iso_z(),
                }
                staged = copy.deepcopy(state["integration"])
                staged["intent"] = copy.deepcopy(stage_intent)
                state = self._epoch_transition(
                    state,
                    lease,
                    "rebase_intent",
                    {"delta": {"integration": staged}},
                )
                stage_intent_digest = self._tail_event_digest(state, "rebase_intent")

                def stage_intent_current() -> bool:
                    try:
                        fresh = self.store.load_locked(
                            str(state["chain_id"]), lease=lease
                        )
                        return bool(
                            fresh.get("state") == "rebase_conflict"
                            and fresh.get("integration", {}).get("condition") == "none"
                            and fresh.get("integration", {}).get("intent") == stage_intent
                            and self._tail_event_digest(fresh, "rebase_intent")
                            == stage_intent_digest
                        )
                    except (FrozenError, KeyError, OSError, Refusal, ValueError):
                        return False

                def persist_stage(result: chain_core.FencedProcessResult) -> None:
                    nonlocal state
                    stage_result = {
                        **copy.deepcopy(stage_intent),
                        "phase": "stage-result",
                        "stage_result": {
                            "authorized": result.authorized,
                            "exit": result.returncode,
                            "inflight_digest": result.fence_digest,
                            "output_digest": result.output_digest,
                            "launch_failed": result.launch_failed,
                            "timed_out": result.timed_out,
                            "output_limit_exceeded": result.output_limit,
                            "group_survived": result.group_survived,
                        },
                        "recorded_at": chain_core.iso_z(),
                    }
                    updated = copy.deepcopy(state["integration"])
                    updated["intent"] = stage_result
                    state = self._epoch_transition(
                        state,
                        lease,
                        "rebase_intent",
                        {"delta": {"integration": updated}},
                    )

                chain_core.run_fenced_command(
                    lock,
                    operation="continue",
                    intent_digest=stage_intent_digest,
                    intent_validator=stage_intent_current,
                    argv=["git", "--literal-pathspecs", "add", "--", *selected_paths],
                    cwd=worktree,
                    persist_result=persist_stage,
                    env=environment,
                    timeout=runtime.COMMAND_TIMEOUT_SECONDS,
                    cap=runtime.OUTPUT_CAP_BYTES,
                    verbose=self.ctx.options.verbose,
                )
                continuation_phase = "stage-result"

            if continuation_phase == "stage-result":
                stage_result = state.get("integration", {}).get("intent")
                if (
                    not phase_intent_valid(
                        stage_result, operation="continue", phase="stage-result"
                    )
                    or not isinstance(stage_result, Mapping)
                    or not exact_stage_success(stage_result)
                ):
                    mark_foreign()
                    raise chain_core._merge_refusal(
                        V2ReasonCode.REBASE_FAILED,
                        "forge: merge recover refused — literal conflict staging failed",
                        remediation=(
                            f"forge merge recover --abort-rebase --chain-id {state['chain_id']}"
                        ),
                        chain=state,
                    )
                state, post_add = self._run_conflict_observation_locked(
                    state,
                    lock,
                    lease,
                    kind="post-add",
                    paths=selected_paths,
                )
                if (
                    post_add is None
                    or post_add["nonconflict_index_digest"]
                    != stage_result.get("index_baseline_digest")
                    or post_add["nonconflict_status_digest"]
                    != stage_result.get("status_baseline_digest")
                ):
                    mark_foreign()
                    refuse_changed_conflict()
                rebase_intent = {
                    **copy.deepcopy(dict(stage_result)),
                    "phase": "rebase",
                    "post_add_index_digest": post_add["index_digest"],
                    "post_add_status_digest": post_add["status_digest"],
                    "post_add_nonconflict_index_digest": post_add[
                        "nonconflict_index_digest"
                    ],
                    "post_add_nonconflict_status_digest": post_add[
                        "nonconflict_status_digest"
                    ],
                    "recorded_at": chain_core.iso_z(),
                }
                updated = copy.deepcopy(state["integration"])
                updated["intent"] = rebase_intent
                state = self._epoch_transition(
                    state,
                    lease,
                    "rebase_intent",
                    {"delta": {"integration": updated}},
                )
                continuation_phase = "rebase"

            rebase_intent = state.get("integration", {}).get("intent")
            state, post_add = self._run_conflict_observation_locked(
                state,
                lock,
                lease,
                kind="post-add",
                paths=selected_paths,
            )
            if (
                continuation_phase != "rebase"
                or not phase_intent_valid(
                    rebase_intent, operation="continue", phase="rebase"
                )
                or not isinstance(rebase_intent, Mapping)
                or not exact_stage_success(rebase_intent)
                or post_add is None
                or post_add["index_digest"]
                != rebase_intent.get("post_add_index_digest")
                or post_add["status_digest"]
                != rebase_intent.get("post_add_status_digest")
                or post_add["nonconflict_index_digest"]
                != rebase_intent.get("index_baseline_digest")
                or post_add["nonconflict_status_digest"]
                != rebase_intent.get("status_baseline_digest")
                or post_add["nonconflict_index_digest"]
                != rebase_intent.get("post_add_nonconflict_index_digest")
                or post_add["nonconflict_status_digest"]
                != rebase_intent.get("post_add_nonconflict_status_digest")
            ):
                mark_foreign()
                refuse_changed_conflict()
            rebase_intent_digest = self._tail_event_digest(state, "rebase_intent")

            def rebase_intent_current() -> bool:
                try:
                    fresh = self.store.load_locked(
                        str(state["chain_id"]), lease=lease
                    )
                    return bool(
                        fresh.get("state") == "rebase_conflict"
                        and fresh.get("integration", {}).get("condition") == "none"
                        and fresh.get("integration", {}).get("intent")
                        == rebase_intent
                        and self._tail_event_digest(fresh, "rebase_intent")
                        == rebase_intent_digest
                    )
                except (FrozenError, KeyError, OSError, Refusal, ValueError):
                    return False

            def persist_continue(result: chain_core.FencedProcessResult) -> None:
                nonlocal state
                succeeded = bool(
                    result.returncode == 0
                    and not result.launch_failed
                    and not result.timed_out
                    and not result.output_limit
                    and not result.group_survived
                )
                result_intent = {
                    "operation": "rebase-result",
                    **identity,
                    "result": "success" if succeeded else "failed",
                    "exit": result.returncode,
                    "inflight_digest": result.fence_digest,
                    "output_digest": result.output_digest,
                    "launch_failed": result.launch_failed,
                    "timed_out": result.timed_out,
                    "output_limit_exceeded": result.output_limit,
                    "group_survived": result.group_survived,
                    "recorded_at": chain_core.iso_z(),
                }
                updated = copy.deepcopy(state["integration"])
                updated["intent"] = result_intent
                updated_conflict = copy.deepcopy(updated.get("conflict"))
                if not isinstance(updated_conflict, dict):
                    raise FrozenError(
                        "merge continuation result lost its conflict identity",
                        chain_id=str(state["chain_id"]),
                        schema=REVISION9_OUTPUT_SCHEMA,
                    )
                updated_conflict["continuation_result"] = {
                    "operation_nonce": identity["operation_nonce"],
                    "inflight_digest": result.fence_digest,
                    "output_digest": result.output_digest,
                }
                updated["conflict"] = updated_conflict
                state = self._epoch_transition(
                    state,
                    lease,
                    "rebase_intent",
                    {"delta": {"integration": updated}},
                )

            continue_environment = environment.copy()
            continue_environment["GIT_EDITOR"] = "true"
            chain_core.run_fenced_command(
                lock,
                operation="continue",
                intent_digest=rebase_intent_digest,
                intent_validator=rebase_intent_current,
                argv=["git", "rebase", "--continue"],
                cwd=worktree,
                persist_result=persist_continue,
                env=continue_environment,
                timeout=runtime.COMMAND_TIMEOUT_SECONDS,
                cap=runtime.OUTPUT_CAP_BYTES,
                verbose=self.ctx.options.verbose,
            )
            disposition = classify_continue_result()
            if disposition in {"failed", "failed-foreign"}:
                raise chain_core._merge_refusal(
                    V2ReasonCode.REBASE_FAILED,
                    "forge: merge recover refused — rebase continuation failed",
                    remediation=f"forge merge refresh --chain-id {state['chain_id']}",
                    chain=state,
                )
            if disposition == "foreign":
                refuse_changed_conflict()
            return state

        if not resume_abort:
            abort_intent = {
                "operation": "abort",
                **identity,
                "started_at": chain_core.iso_z(),
            }
            integration["intent"] = copy.deepcopy(abort_intent)
            state = self._epoch_transition(
                state,
                lease,
                "rebase_intent",
                {"delta": {"integration": integration}},
            )
            intent_digest = self._tail_event_digest(state, "rebase_intent")

            def abort_intent_current() -> bool:
                try:
                    fresh = self.store.load_locked(
                        str(state["chain_id"]), lease=lease
                    )
                    return bool(
                        fresh.get("state") == "rebase_conflict"
                        and fresh.get("integration", {}).get("condition") == "none"
                        and fresh.get("integration", {}).get("intent")
                        == abort_intent
                        and self._tail_event_digest(fresh, "rebase_intent")
                        == intent_digest
                    )
                except (FrozenError, KeyError, OSError, Refusal, ValueError):
                    return False

            def persist_abort(result: chain_core.FencedProcessResult) -> None:
                nonlocal state
                succeeded = bool(
                    result.returncode == 0
                    and not result.launch_failed
                    and not result.timed_out
                    and not result.output_limit
                    and not result.group_survived
                )
                result_intent = {
                    "operation": "rebase-result",
                    **identity,
                    "result": "success" if succeeded else "failed",
                    "exit": result.returncode,
                    "inflight_digest": result.fence_digest,
                    "output_digest": result.output_digest,
                    "launch_failed": result.launch_failed,
                    "timed_out": result.timed_out,
                    "output_limit_exceeded": result.output_limit,
                    "group_survived": result.group_survived,
                    "recorded_at": chain_core.iso_z(),
                }
                updated = copy.deepcopy(state["integration"])
                updated["intent"] = result_intent
                updated_conflict = copy.deepcopy(updated.get("conflict"))
                if not isinstance(updated_conflict, dict):
                    raise FrozenError(
                        "merge abort result lost its conflict identity",
                        chain_id=str(state["chain_id"]),
                        schema=REVISION9_OUTPUT_SCHEMA,
                    )
                updated_conflict["abort_result"] = {
                    "operation_nonce": identity["operation_nonce"],
                    "inflight_digest": result.fence_digest,
                    "output_digest": result.output_digest,
                }
                updated["conflict"] = updated_conflict
                state = self._epoch_transition(
                    state,
                    lease,
                    "rebase_intent",
                    {"delta": {"integration": updated}},
                )

            chain_core.run_fenced_command(
                lock,
                operation="abort",
                intent_digest=intent_digest,
                intent_validator=abort_intent_current,
                argv=[
                    "git",
                    "--no-pager",
                    "-C",
                    str(worktree),
                    "rebase",
                    "--abort",
                ],
                cwd=worktree,
                persist_result=persist_abort,
                env=environment,
                timeout=runtime.COMMAND_TIMEOUT_SECONDS,
                cap=runtime.OUTPUT_CAP_BYTES,
                verbose=self.ctx.options.verbose,
            )

        raw_abort_result = state.get("integration", {}).get("intent")
        current_conflict = state.get("integration", {}).get("conflict")
        current_abort_marker = (
            current_conflict.get("abort_result")
            if isinstance(current_conflict, Mapping)
            else None
        )
        result_class = chain_core._merge_rebase_result_classification(state)
        if (
            not isinstance(raw_abort_result, Mapping)
            or not isinstance(current_abort_marker, Mapping)
            or current_abort_marker.get("operation_nonce")
            != identity["operation_nonce"]
            or current_abort_marker.get("inflight_digest")
            != raw_abort_result.get("inflight_digest")
            or current_abort_marker.get("output_digest")
            != raw_abort_result.get("output_digest")
            or result_class not in {"success", "failed"}
        ):
            return self._record_foreign_git_locked(state, lease)

        state, restoration_observation = (
            self._run_integrated_rebase_observation_locked(state, lock, lease)
        )
        restored = bool(
            isinstance(restoration_observation, Mapping)
            and restoration_observation.get("status_empty") is True
            and restoration_observation.get("observed_head")
            == pre_rebase.get("head")
            and restoration_observation.get("branch") == state.get("branch")
            and engine._merge_rebase_operation_metadata_absent(state)
        )
        if not restored:
            return self._record_foreign_git_locked(state, lease)
        updated = copy.deepcopy(state["integration"])
        engine._reset_merge_nonmovement_counter(updated)
        updated.update(
            {
                "condition": "rebase-failed",
                "primary_condition": "none",
                "epoch": None,
                "conflict": None,
            }
        )
        state = self._epoch_transition(
            state,
            lease,
            "rebase_result",
            {
                "delta": {
                    "state": "revising",
                    "integration": updated,
                }
            },
        )
        return state

    def _bootstrap_pending_classification_inputs_locked(
        self,
        state: Mapping[str, Any],
        admission: engine.MergeAdmission,
    ) -> engine.MergeBootstrapClassification:
        """Recover the authenticated inputs carried by a successful result."""

        if not chain_core._merge_bootstrap_classification_pending(state):
            raise FrozenError(
                "merge bootstrap classification snapshot is not pending",
                chain_id=str(state.get("chain_id", "")) or None,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        candidate = state["candidate"]
        with self.store.event_lock(str(state["chain_id"])):
            replay = self.store._read_replay_locked(str(state["chain_id"]))
        selected: Mapping[str, Any] | None = None
        for event in reversed(replay.events):
            payload = event.get("payload")
            delta = payload.get("delta") if isinstance(payload, Mapping) else None
            integration = (
                delta.get("integration") if isinstance(delta, Mapping) else None
            )
            if (
                event.get("event") == "fetch_result"
                and event.get("generation_digest")
                == candidate.get("generation_digest")
                and isinstance(payload, Mapping)
                and integration == state.get("integration")
            ):
                selected = event
                break
        if selected is None:
            raise FrozenError(
                "merge bootstrap classification result evidence is unavailable",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        payload = selected["payload"]
        try:
            binding = chain_core._validate_merge_scope_fetch_binding(
                payload.get("scope_fetch_binding")
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise FrozenError(
                "merge bootstrap classification sidecar is malformed",
                chain_id=str(state["chain_id"]),
                observed=str(exc),
                schema=REVISION9_OUTPUT_SCHEMA,
            ) from exc
        if (
            binding.get("chain_id") != state.get("chain_id")
            or binding.get("candidate_head") != candidate.get("candidate_head")
            or binding.get("remote_tip") != candidate.get("remote_tip")
            or binding.get("full_patch_output_digest")
            != candidate.get("diff_sha256")
        ):
            raise FrozenError(
                "merge bootstrap classification sidecar changed its candidate",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        proof = payload.get("scope_proof")
        scope: engine.MergeScopeResult | None = None
        if admission.run_task is not None:
            scope_request = engine._merge_scope_request(admission)
            if not chain_core._validate_merge_scope_proof(
                proof,
                state=state,
                binding=binding,
                scope_request=scope_request,
            ):
                raise FrozenError(
                    "merge bootstrap classification scope proof is malformed",
                    chain_id=str(state["chain_id"]),
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            assert isinstance(proof, Mapping)
            scope = engine.MergeScopeResult(
                argv=tuple(
                    chain_core._merge_scope_argv(
                        admission.worktree,
                        str(candidate["remote_tip"]),
                        str(candidate["candidate_head"]),
                    )
                ),
                command_digest=str(proof["command_digest"]),
                environment_digest=str(proof["environment_digest"]),
                output_digest=str(proof["output_digest"]),
                changed_paths=tuple(proof["changed_paths"]),
                out_of_scope_paths=tuple(proof["out_of_scope_paths"]),
                result=str(proof["result"]),
            )
        elif proof is not None:
            raise FrozenError(
                "unbound merge bootstrap carried a scope proof",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        return engine.MergeBootstrapClassification(
            candidate=copy.deepcopy(dict(candidate)),
            scope=scope,
            full_patch_output_digest=str(binding["full_patch_output_digest"]),
            scope_proof_digest=(
                str(proof["digest"]) if isinstance(proof, Mapping) else None
            ),
            fetch_result_event_digest=str(selected["digest"]),
            verb="merge recover",
        )

    def _recover_classifying_bootstrap_v12_locked(
        self,
        state: dict[str, Any],
        lease: chain_core.ChainLease,
    ) -> tuple[
        dict[str, Any],
        str,
        engine.MergeAdmission | None,
        engine.MergeBootstrapClassification | None,
    ]:
        """Classify the Revision-12 pre-sidecar and surviving-sidecar windows."""

        chain_core._require_merge_integration_control("composite-bootstrap-streaming")
        intent = state.get("integration", {}).get("intent")
        if chain_core._merge_bootstrap_classification_pending(state):
            admission = self._admission_for_refresh(
                state, verb="merge recover"
            )
            pending = self._bootstrap_pending_classification_inputs_locked(
                state, admission
            )
            return state, "classification-pending", admission, pending
        if (
            state.get("state") == "classifying"
            and state.get("integration", {}).get("condition") == "fetch-failed"
            and state.get("candidate") is None
            and state.get("tier") is None
            and not isinstance(state.get("run_binding"), Mapping)
            and isinstance(intent, Mapping)
            and set(intent)
            == {
                "operation",
                "operation_nonce",
                "attempt",
                "result",
                "resolved_tip",
            }
            and intent.get("operation") == "fetch-result"
            and chain_core._valid_nonce(intent.get("operation_nonce"))
            and chain_core._valid_positive_int(intent.get("attempt"))
            and intent.get("result") == "failed"
            and intent.get("resolved_tip") is None
        ):
            raise chain_core._merge_refusal(
                V2ReasonCode.FETCH_FAILED,
                "forge: merge recover refused — fixed target fetch failed",
                expected="merge refresh to begin one fresh bootstrap epoch",
                observed="the prior composite bootstrap did not PASS",
                remediation=(
                    f"forge merge refresh --chain-id {state['chain_id']}"
                ),
                chain=state,
            )
        if (
            not isinstance(intent, Mapping)
            or intent.get("operation") != "fetch"
            or not chain_core._valid_nonce(intent.get("operation_nonce"))
            or not chain_core._valid_positive_int(intent.get("attempt"))
            or chain_core.COMMIT_RE.fullmatch(str(intent.get("pre_fetch_head", ""))) is None
        ):
            raise FrozenError(
                "interrupted merge bootstrap intent is malformed",
                chain_id=str(state["chain_id"]),
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        operation_nonce = str(intent["operation_nonce"])
        attempt = int(intent["attempt"])
        run_bound = isinstance(state.get("run_binding"), Mapping)
        admission = self._admission_for_refresh(
            state, verb="merge recover"
        )
        binding = self._recover_merge_bootstrap_scope_binding(
            state, admission, fence=None
        )

        def record_failure(
            sidecar: Mapping[str, Any] | None,
        ) -> dict[str, Any]:
            integration = copy.deepcopy(state["integration"])
            integration.update(
                {
                    "condition": "none" if run_bound else "fetch-failed",
                    "primary_condition": "none",
                    "intent": {
                        "operation": "fetch-result",
                        "operation_nonce": operation_nonce,
                        "attempt": attempt,
                        "result": "failed",
                        "resolved_tip": None,
                    },
                }
            )
            return self._epoch_transition(
                state,
                lease,
                "fetch_result",
                {
                    "delta": {"integration": integration},
                    "scope_fetch_binding": (
                        copy.deepcopy(dict(sidecar))
                        if isinstance(sidecar, Mapping)
                        else None
                    ),
                    "scope_proof": None,
                },
                generation_digest=(
                    str(state["candidate"]["generation_digest"])
                    if isinstance(state.get("candidate"), Mapping)
                    else None
                ),
            )

        if binding is None:
            failed = record_failure(None)
            if not run_bound:
                return failed, "fetch-failed", None, None
            terminal = self._release_to_aborted_locked(
                failed,
                lease,
                reason="run/task scope derivation is invalid",
            )
            raise chain_core._merge_refusal(
                V2ReasonCode.RUN_TASK_BINDING_INVALID,
                "forge: merge recover refused — run/task scope derivation is invalid",
                expected="a surviving authenticated composite-bootstrap sidecar",
                observed="scope-fetch sidecar absent",
                chain=terminal,
            )
        if run_bound:
            failed = record_failure(binding)
            terminal = self._release_to_aborted_locked(
                failed,
                lease,
                reason="run/task scope derivation is invalid",
            )
            raise chain_core._merge_refusal(
                V2ReasonCode.RUN_TASK_BINDING_INVALID,
                "forge: merge recover refused — run/task scope derivation is invalid",
                expected="ordinary abort after the surviving run-bound sidecar",
                observed=str(binding.get("digest")),
                chain=terminal,
            )

        fixed_tip = str(binding["remote_tip"])
        generation_number = (
            int(state["candidate"]["generation"]) + 1
            if isinstance(state.get("candidate"), Mapping)
            else 1
        )
        try:
            candidate = engine._retain_or_advance_merge_candidate(
                admission,
                fixed_tip,
                prior_candidate=state.get("candidate"),
                generation=generation_number,
                diff_output_digest=str(binding["full_patch_output_digest"]),
            )
        except (TypeError, ValueError) as exc:
            raise FrozenError(
                "surviving composite-bootstrap sidecar cannot materialize its generation",
                chain_id=str(state["chain_id"]),
                observed=str(exc),
                schema=REVISION9_OUTPUT_SCHEMA,
            ) from exc
        integration = copy.deepcopy(state["integration"])
        integration.update(
            {
                "condition": "none",
                "primary_condition": "none",
                "intent": {
                    "operation": "fetch-result",
                    "operation_nonce": operation_nonce,
                    "attempt": attempt,
                    "result": "success",
                    "resolved_tip": fixed_tip,
                },
            }
        )
        desired = {
            "candidate": copy.deepcopy(candidate),
            "tier": None,
            "state": "classifying",
            "policy_source": {
                "commit": admission.policy.sha,
                "digest": admission.policy.digest,
            },
            "steps": {},
            "review": (
                {"iteration": state["review"]["iteration"]}
                if isinstance(state.get("review"), Mapping)
                and type(state["review"].get("iteration")) is int
                else {}
            ),
            "approval": {},
            "authorization": {},
            "integration": integration,
        }
        current = self._epoch_transition(
            state,
            lease,
            "fetch_result",
            {
                "delta": {
                    name: value
                    for name, value in desired.items()
                    if state.get(name) != value or name == "state"
                },
                "scope_fetch_binding": copy.deepcopy(dict(binding)),
                "scope_proof": None,
            },
            generation_digest=str(candidate["generation_digest"]),
        )
        pending = self._bootstrap_pending_classification_inputs_locked(
            current, admission
        )
        return current, "classification-pending", admission, pending

    def _recover_classifying_bootstrap_locked(
        self,
        state: dict[str, Any],
        lock: chain_core.CommonRebaseLock,
        lease: chain_core.ChainLease,
    ) -> tuple[
        dict[str, Any],
        str,
        engine.MergeAdmission | None,
        engine.MergeBootstrapClassification | None,
    ]:
        """Finish one interrupted bootstrap from its durable raw child result."""

        del lock
        return self._recover_classifying_bootstrap_v12_locked(state, lease)


    def recover(
        self,
        *,
        continue_rebase: bool = False,
        paths: Sequence[str] | None = None,
        abort_rebase: bool = False,
    ) -> Outcome:
        """Observation-first reconciliation for one dormant merge chain."""

        self._git_no_lazy_fetch_qualification = None
        for control in chain_core._REQUIRED_MERGE_INTEGRATION_CONTROLS:
            chain_core._require_merge_integration_control(control)
        explicit_conflict_mode = bool(continue_rebase or abort_rebase)
        state = (
            self._read_only_recovery_flag_state()
            if explicit_conflict_mode
            else self._load()
        )
        if continue_rebase and abort_rebase:
            raise chain_core._merge_refusal(
                V2ReasonCode.STATE_PRECONDITION,
                "forge: merge recover refused — recovery modes are mutually exclusive",
                chain=state,
            )
        if bool(paths) != bool(continue_rebase):
            raise chain_core._merge_refusal(
                V2ReasonCode.STATE_PRECONDITION,
                "forge: merge recover refused — --continue requires --paths and --paths requires --continue",
                chain=state,
            )
        engine._require_loud_merge_recovery_mode(
            state,
            continue_rebase=continue_rebase,
            abort_rebase=abort_rebase,
        )
        if explicit_conflict_mode:
            state = self._load()
            engine._require_loud_merge_recovery_mode(
                state,
                continue_rebase=continue_rebase,
                abort_rebase=abort_rebase,
            )
        self._halt(state)
        try:
            resumed_release = self._resume_pending_release(state)
        except chain_core.ChainLeaseUnavailable:
            # A crashed writer may have left the release intent and its lease
            # together.  Only the common-lock recovery path below has the
            # death-proof authority to reclaim that lease.
            resumed_release = None
        if resumed_release is not None:
            current, disposition = resumed_release
            historical = disposition == "historical-landed-superseded"
            return engine._success(
                current,
                "merge recovery "
                f"{'historical-landed-superseded' if historical else 'terminal'} "
                f"for chain {current['chain_id']}",
                (
                    "forge merge start --worktree "
                    f"{current['worktree']['path']}"
                    if historical
                    else "none — merge chain closed"
                    if current["state"] == "closed"
                    else "none — merge chain aborted"
                ),
            )
        pending_claim = state.get("worktree", {}).get("claim")
        pending_release = bool(
            isinstance(pending_claim, Mapping)
            and pending_claim.get("status") in {"releasing", "released"}
            and state.get("state") not in {"closed", "aborted"}
        )
        if (
            not pending_release
            and engine._merge_inactive(state)
            and state.get("state") in {"rebasing", "reverifying"}
        ):
            with self.store.event_lock(str(state["chain_id"])):
                inactive_replay = self.store._read_replay_locked(
                    str(state["chain_id"])
                )
            if engine._merge_inactive_epoch_has_no_started_child(
                state, inactive_replay.events
            ):
                raise chain_core._merge_refusal(
                    V2ReasonCode.STATE_PRECONDITION,
                    "forge: merge recover refused — inactive epoch has no started child",
                    expected="status or safe abort after inactivity",
                    observed=str(state["state"]),
                    remediation=f"forge status --chain-id {state['chain_id']}",
                    chain=state,
                )
        if not pending_release and self._recover_can_reach_final_mode(
            state,
            continue_rebase=continue_rebase,
            abort_rebase=abort_rebase,
        ):
            self._prepare_git_no_lazy_fetch_qualification(state)
        binding = state.get("run_binding")
        action = "observed"
        pending_admission: engine.MergeAdmission | None = None
        pending_classification: engine.MergeBootstrapClassification | None = None
        budget = engine._MergeEpochBudget()
        with self.store._journal_outer(
            binding if isinstance(binding, Mapping) else None
        ):
            with self._recording_common_lock(
                Path(str(state["worktree"]["common_dir"])),
                chain_id=str(state["chain_id"]),
                operation="recover",
            ) as common_lock:
                with chain_core.acquire_chain_lease(
                    self.store.root,
                    chain_id=str(state["chain_id"]),
                    session=self.store._session(None),
                    exclusion=common_lock,
                ) as lease:
                    current = self.store.load_locked(
                        str(state["chain_id"]), lease=lease
                    )
                    engine._require_loud_merge_recovery_mode(
                        current,
                        continue_rebase=continue_rebase,
                        abort_rebase=abort_rebase,
                    )
                    claim_status = current.get("worktree", {}).get(
                        "claim", {}
                    ).get("status")
                    if claim_status in {"releasing", "released"} and current[
                        "state"
                    ] not in {"closed", "aborted"}:
                        current, completed_disposition = (
                            self._complete_pending_release_locked(current, lease)
                        )
                        historical = (
                            completed_disposition
                            == "historical-landed-superseded"
                        )
                        return engine._success(
                            current,
                            "merge recovery "
                            f"{'historical-landed-superseded' if historical else 'terminal'} "
                            f"for chain {current['chain_id']}",
                            (
                                "forge merge start --worktree "
                                f"{current['worktree']['path']}"
                                if historical
                                else "none — merge chain closed"
                                if current["state"] == "closed"
                                else "none — merge chain aborted"
                            ),
                        )
                    if engine._merge_inactive(current) and current.get("state") in {
                        "rebasing",
                        "reverifying",
                    }:
                        with self.store.event_lock(str(current["chain_id"])):
                            inactive_replay = self.store._read_replay_locked(
                                str(current["chain_id"])
                            )
                        if engine._merge_inactive_epoch_has_no_started_child(
                            current, inactive_replay.events
                        ):
                            raise chain_core._merge_refusal(
                                V2ReasonCode.STATE_PRECONDITION,
                                "forge: merge recover refused — inactive epoch has no started child",
                                expected="status or safe abort after inactivity",
                                observed=str(current["state"]),
                                remediation=(
                                    "forge status --chain-id "
                                    f"{current['chain_id']}"
                                ),
                                chain=current,
                            )
                    interrupted_candidate_observation = bool(
                        isinstance(
                            current.get("integration", {}).get("intent"),
                            Mapping,
                        )
                        and current["integration"]["intent"].get("schema")
                        == chain_core._MERGE_CANDIDATE_OBSERVATION_SCHEMA
                    )
                    current, _source_intent, observation_restored = (
                        self._restore_candidate_observation_intent_locked(
                            current, lease
                        )
                    )
                    if not observation_restored:
                        current = self._record_foreign_git_locked(
                            current, lease
                        )
                    bootstrap_intent = current.get("integration", {}).get(
                        "intent"
                    )
                    if (
                        isinstance(bootstrap_intent, Mapping)
                        and bootstrap_intent.get("schema")
                        == chain_core._BOOTSTRAP_FETCH_OBSERVATION_SCHEMA
                        and not chain_core._bootstrap_fetch_observation_record_valid(
                            current, bootstrap_intent
                        )
                    ):
                        current = self._record_foreign_git_locked(
                            current, lease
                        )
                    inactive_post_attempt_ready = False
                    if engine._merge_inactive(current) and engine._merge_has_attempt(current):
                        with self.store.event_lock(str(current["chain_id"])):
                            current_replay = self.store._read_replay_locked(
                                str(current["chain_id"])
                            )
                        inactive_post_attempt_ready = (
                            chain_core._merge_inactive_post_attempt_recovery_ready(
                                current, current_replay.events
                            )
                        )
                    if current.get("integration", {}).get("condition") == (
                        "lock-release-failed"
                    ):
                        integration = copy.deepcopy(current["integration"])
                        integration.update(
                            {
                                "condition": integration["primary_condition"],
                                "primary_condition": "none",
                            }
                        )
                        current = self._epoch_transition(
                            current,
                            lease,
                            "lock_release_result",
                            {"delta": {"integration": integration}},
                        )
                        action = "lock-release"
                    elif (
                        inactive_post_attempt_ready
                    ):
                        prior_observation_digest = self._tail_event_digest(
                            current, "push_observed"
                        )
                        current = self._run_remote_observation(
                            current,
                            common_lock,
                            lease,
                            budget,
                            phase="post-push",
                            allow_inactive_observation=True,
                        )
                        fresh_observation_digest = self._tail_event_digest(
                            current, "push_observed"
                        )
                        if fresh_observation_digest == prior_observation_digest:
                            raise FrozenError(
                                "inactive merge recovery did not retain a fresh remote observation",
                                chain_id=str(current["chain_id"]),
                                schema=REVISION9_OUTPUT_SCHEMA,
                            )
                        containment, _containment_vector = chain_core._merge_containment(
                            current
                        )
                        if containment == "older":
                            current = self._release_historical_landing_locked(
                                current,
                                common_lock,
                                lease,
                                observation_event_digest=fresh_observation_digest,
                            )
                            action = "historical-landed-superseded"
                        elif containment == "all-false":
                            action = "inactive-not-landed"
                        else:
                            action = (
                                "pushed"
                                if current.get("state") == "pushed"
                                else "observed"
                            )
                    elif current["state"] == "classifying":
                        if continue_rebase or abort_rebase:
                            self._wrong_state(
                                current,
                                "bare recovery for an interrupted bootstrap",
                                "merge recover",
                            )
                        (
                            current,
                            action,
                            pending_admission,
                            pending_classification,
                        ) = self._recover_classifying_bootstrap_locked(
                            current, common_lock, lease
                        )
                    elif current["state"] == "pushing":
                        retry_candidate = bool(
                            not engine._merge_inactive(current)
                            and chain_core._merge_old_tip_all_false(current)
                            and isinstance(
                                current.get("integration", {}).get("push"),
                                Mapping,
                            )
                            and (
                                current.get("integration", {})
                                .get("push", {})
                                .get("result")
                                is None
                                or isinstance(
                                    current.get("integration", {})
                                    .get("push", {})
                                    .get("result"),
                                    Mapping,
                                )
                            )
                        )
                        prior_observation_digest = self._tail_event_digest(
                            current, "push_observed"
                        )
                        current = self._run_remote_observation(
                            current,
                            common_lock,
                            lease,
                            budget,
                            phase="post-push",
                            budget_member=(
                                "pre_observations" if retry_candidate else None
                            ),
                            allow_inactive_observation=True,
                        )
                        fresh_observation_digest = self._tail_event_digest(
                            current, "push_observed"
                        )
                        containment, _containment_vector = chain_core._merge_containment(current)
                        if (
                            containment == "older"
                            and engine._merge_inactive(current)
                            and fresh_observation_digest != prior_observation_digest
                        ):
                            current = self._release_historical_landing_locked(
                                current,
                                common_lock,
                                lease,
                                observation_event_digest=fresh_observation_digest,
                            )
                            action = "historical-landed-superseded"
                        elif (
                            containment == "all-false"
                            and engine._merge_inactive(current)
                            and fresh_observation_digest
                            != prior_observation_digest
                        ):
                            action = "inactive-not-landed"
                        elif (
                            retry_candidate
                            and fresh_observation_digest
                            != prior_observation_digest
                            and current["state"] == "pushing"
                            and not engine._merge_inactive(current)
                            and chain_core._merge_old_tip_all_false(current)
                        ):
                            current = self._run_epoch_push(
                                current,
                                common_lock,
                                lease,
                                budget,
                                retry=True,
                            )
                        if action not in {
                            "historical-landed-superseded",
                            "inactive-not-landed",
                        }:
                            action = (
                                "pushed"
                                if current["state"] == "pushed"
                                else "observed"
                            )
                    elif current["state"] == "reverification_failed":
                        current, candidate_observation = (
                            self._run_candidate_observation_locked(
                                current,
                                common_lock,
                                lease,
                                verb="merge recover",
                                remote_tip=str(
                                    current["candidate"]["remote_tip"]
                                ),
                                expected_head=str(
                                    current["candidate"]["candidate_head"]
                                ),
                                classify=False,
                            )
                        )
                        _repository, observed_policy, _paths = (
                            _observe_current_merge_candidate(
                                self.ctx,
                                current,
                                verb="merge recover",
                                observation=candidate_observation,
                            )
                        )
                        current = self._begin_epoch(
                            current,
                            lease,
                            retry=True,
                            observed_policy=observed_policy,
                        )
                        current, action = self._finish_recovered_epoch_locked(
                            current, common_lock, lease, budget
                        )
                    elif current["state"] == "reverifying":
                        current, action = self._finish_recovered_epoch_locked(
                            current, common_lock, lease, budget
                        )
                    elif current["state"] == "rebase_conflict":
                        current = self._recover_conflict_locked(
                            current,
                            common_lock,
                            lease,
                            continue_rebase=continue_rebase,
                            abort_rebase=abort_rebase,
                            paths=paths,
                        )
                        if current["state"] == "reverifying":
                            current, action = self._finish_recovered_epoch_locked(
                                current, common_lock, lease, budget
                            )
                        else:
                            action = "conflict"
                    elif current["state"] == "rebasing":
                        intent = current.get("integration", {}).get("intent")
                        plan = current.get("integration", {}).get("epoch", {}).get(
                            "gate_plan"
                        )
                        fetch_observation_phase = bool(
                            isinstance(intent, Mapping)
                            and (
                                intent.get("schema")
                                == chain_core._EPOCH_FETCH_OBSERVATION_SCHEMA
                                or intent.get("schema")
                                == "forge-epoch-ancestry-intent/1"
                                or (
                                    intent.get("schema")
                                    == chain_core._MERGE_CANDIDATE_OBSERVATION_SCHEMA
                                    and isinstance(
                                        intent.get("source_intent"), Mapping
                                    )
                                    and intent.get("source_intent", {}).get(
                                        "schema"
                                    )
                                    == chain_core._EPOCH_FETCH_OBSERVATION_SCHEMA
                                )
                            )
                        )
                        if fetch_observation_phase:
                            current, fetched_tip, unchanged = (
                                self._complete_epoch_fetch_locked(
                                    current, common_lock, lease
                                )
                            )
                            if not unchanged:
                                current = self._run_epoch_rebase(
                                    current,
                                    fetched_tip,
                                    common_lock,
                                    lease,
                                    budget,
                                )
                            current, action = self._finish_recovered_epoch_locked(
                                current, common_lock, lease, budget
                            )
                        elif isinstance(plan, Mapping) and plan.get("status") == "sealed":
                            current, action = self._finish_recovered_epoch_locked(
                                current, common_lock, lease, budget
                            )
                        elif isinstance(intent, Mapping) and (
                            intent.get("operation") in {"rebase", "rebase-result"}
                            or intent.get("operation") == "continue"
                            and isinstance(intent.get("phase"), str)
                            and str(intent["phase"]).startswith(
                                "forge-conflict-observation:"
                            )
                        ):
                            current = self._recover_rebase_observation_locked(
                                current, common_lock, lease
                            )
                            if current["state"] == "reverifying":
                                current, action = self._finish_recovered_epoch_locked(
                                    current, common_lock, lease, budget
                                )
                        elif isinstance(intent, Mapping) and intent.get(
                            "operation"
                        ) == "fetch-result" and intent.get("result") == "success":
                            current = self._run_epoch_rebase(
                                current,
                                str(intent["resolved_tip"]),
                                common_lock,
                                lease,
                                budget,
                            )
                            current, action = self._finish_recovered_epoch_locked(
                                current, common_lock, lease, budget
                            )
                        else:
                            current, fetched_tip, unchanged = self._run_epoch_fetch(
                                current,
                                common_lock,
                                lease,
                                budget,
                                resume_intent=bool(
                                    isinstance(intent, Mapping)
                                    and intent.get("operation") == "fetch"
                                ),
                            )
                            if not unchanged:
                                current = self._run_epoch_rebase(
                                    current,
                                    fetched_tip,
                                    common_lock,
                                    lease,
                                    budget,
                                )
                            current, action = self._finish_recovered_epoch_locked(
                                current, common_lock, lease, budget
                            )
                    elif current["state"] == "authorized" and current.get(
                        "integration", {}
                    ).get("condition") in {
                        "fetch-failed",
                        "remote-moved",
                        "non-fast-forward",
                    }:
                        current = self._begin_epoch(current, lease)
                        current, fetched_tip, unchanged = self._run_epoch_fetch(
                            current, common_lock, lease, budget
                        )
                        if not unchanged:
                            current = self._run_epoch_rebase(
                                current,
                                fetched_tip,
                                common_lock,
                                lease,
                                budget,
                            )
                        current, action = self._finish_recovered_epoch_locked(
                            current, common_lock, lease, budget
                        )
                    elif current.get("integration", {}).get("condition") == (
                        "foreign-git-state"
                    ):
                        current = self._record_foreign_git_locked(current, lease)
                        action = "foreign"
                    elif interrupted_candidate_observation:
                        action = "observed"
                    else:
                        self._wrong_state(
                            current,
                            "a recoverable merge condition or interrupted epoch",
                            "merge recover",
                        )
        if pending_classification is not None:
            if pending_admission is None:
                raise FrozenError(
                    "merge bootstrap recovery lost its classification admission",
                    chain_id=str(current["chain_id"]),
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            current, _generation = self._complete_bootstrap_classification(
                current,
                pending_admission,
                pending_classification,
            )
            action = "classified"
        if current["state"] == "pushing":
            condition = current["integration"]["condition"]
            reason = (
                V2ReasonCode.PUSH_FAILED
                if condition == "push-failed"
                else V2ReasonCode.PUSH_OUTCOME_UNKNOWN
                if condition == "push-outcome-unknown"
                else V2ReasonCode.NON_FAST_FORWARD
                if condition == "non-fast-forward"
                else None
            )
            if reason is not None:
                raise chain_core._merge_refusal(
                    reason,
                    f"forge: merge recover observed {condition}",
                    remediation=f"forge merge recover --chain-id {current['chain_id']}",
                    chain=current,
                )
        next_steps = {
            "pushed": f"forge merge cleanup --chain-id {current['chain_id']}",
            "pushing": f"forge merge recover --chain-id {current['chain_id']}",
            "reviewing": f"forge review request --chain-id {current['chain_id']}",
            "authorized": f"forge merge finalize --chain-id {current['chain_id']}",
            "revising": f"forge merge refresh --chain-id {current['chain_id']}",
            "rebase_conflict": (
                f"forge merge recover --continue --paths <path>... --chain-id {current['chain_id']}"
            ),
            "closed": "none — merge chain closed",
            "aborted": "none — merge chain aborted",
        }
        if action == "historical-landed-superseded":
            next_steps["aborted"] = (
                "forge merge start --worktree "
                f"{current['worktree']['path']}"
            )
        elif action == "inactive-not-landed":
            next_steps["pushing"] = (
                f"forge merge abort --chain-id {current['chain_id']}"
            )
        return engine._success(
            current,
            f"merge recovery {action} for chain {current['chain_id']}",
            next_steps.get(
                str(current["state"]),
                f"forge status --chain-id {current['chain_id']}",
            ),
        )

    def cleanup_chain(self) -> Outcome:
        """Remove only the contained worktree and unmoved branch, without force."""

        for control in chain_core._REQUIRED_MERGE_INTEGRATION_CONTROLS:
            chain_core._require_merge_integration_control(control)
        state = self._load()
        if state["state"] not in {"pushed", "cleanup_pending"}:
            self._wrong_state(state, "pushed or cleanup_pending", "merge cleanup")
        self._halt(state)
        try:
            resumed_release = self._resume_pending_release(
                state, expected_target="closed"
            )
        except chain_core.ChainLeaseUnavailable:
            # A publication race after the lock-name observation is resolved
            # under the repository-wide exclusion below.
            resumed_release = None
        if resumed_release is not None:
            current, _disposition = resumed_release
            return engine._success(
                current,
                f"merge chain {current['chain_id']} cleanup is durably closed",
                "none — merge chain closed",
            )
        binding = state.get("run_binding")
        results: list[dict[str, Any]] = []
        with self.store._journal_outer(
            binding if isinstance(binding, Mapping) else None
        ):
            with self._recording_common_lock(
                Path(str(state["worktree"]["common_dir"])),
                chain_id=str(state["chain_id"]),
                operation="cleanup",
            ) as common_lock:
                with chain_core.acquire_chain_lease(
                    self.store.root,
                    chain_id=str(state["chain_id"]),
                    session=self.store._session(None),
                    exclusion=common_lock,
                ) as lease:
                    current = self.store.load_locked(
                        str(state["chain_id"]), lease=lease
                    )
                    claim_status = current.get("worktree", {}).get(
                        "claim", {}
                    ).get("status")
                    if claim_status in {"releasing", "released"} and current[
                        "state"
                    ] not in {"closed", "aborted"}:
                        current, _completed_disposition = (
                            self._complete_pending_release_locked(
                                current, lease, expected_target="closed"
                            )
                        )
                        return engine._success(
                            current,
                            f"merge chain {current['chain_id']} cleanup is durably closed",
                            "none — merge chain closed",
                        )
                    if current["state"] not in {"pushed", "cleanup_pending"}:
                        self._wrong_state(
                            current, "pushed or cleanup_pending", "merge cleanup"
                        )
                    containment, _vector = chain_core._merge_containment(current)
                    if containment != "current":
                        raise FrozenError(
                            "cleanup lost current-generation containment truth",
                            chain_id=str(current["chain_id"]),
                            observed=containment,
                            schema=REVISION9_OUTPUT_SCHEMA,
                        )
                    repository = str(current["repository"])
                    landed_head = str(
                        current["integration"]["push"]["landed_head"]
                    )
                    destination_ref = str(
                        current["target"]["destination_ref"]
                    )

                    def child_complete(
                        result: chain_core.FencedProcessResult,
                        *returncodes: int,
                    ) -> bool:
                        return bool(
                            result.authorized is True
                            and type(result.returncode) is int
                            and result.returncode in returncodes
                            and result.launch_failed is False
                            and result.timed_out is False
                            and result.output_limit is False
                            and result.group_survived is False
                        )

                    def path_presence(path: Path) -> bool | None:
                        try:
                            os.lstat(path)
                        except FileNotFoundError:
                            return False
                        except OSError:
                            return None
                        return True

                    def fail_step(
                        evidence: Mapping[str, Any], message: str
                    ) -> None:
                        if evidence.get("outcome") != "failed":
                            return
                        raise chain_core._merge_refusal(
                            V2ReasonCode.CLEANUP_FAILED,
                            message,
                            observed=chain_core.canonical_bytes(
                                evidence.get("observation")
                            ).decode("utf-8"),
                            remediation=(
                                f"forge merge cleanup --chain-id {current['chain_id']}"
                            ),
                            chain=current,
                        )

                    remote_subject = {
                        "destination_ref": destination_ref,
                        "landed_head": landed_head,
                    }
                    remote_argv = chain_core._merge_cleanup_expected_argv(
                        current, "remote-fetch", remote_subject
                    )
                    assert remote_argv is not None

                    def observe_remote_fetch(
                        result: chain_core.FencedProcessResult,
                    ) -> tuple[str, Mapping[str, Any]]:
                        observation = engine._merge_cleanup_remote_fetch_observation(
                            result,
                            destination_ref,
                            Path(str(current["worktree"]["common_dir"])),
                        )
                        outcome = (
                            "passed"
                            if child_complete(result, 0)
                            and observation["exists"] is True
                            else "failed"
                        )
                        return outcome, observation

                    current, _remote_result, remote_evidence = (
                        self._run_cleanup_child(
                            current,
                            common_lock,
                            lease,
                            operation="remote-fetch",
                            fence_operation="remote-observation",
                            subject=remote_subject,
                            argv=remote_argv,
                            observe=observe_remote_fetch,
                        )
                    )
                    fail_step(
                        remote_evidence,
                        "forge: merge cleanup failed — remote observation did not PASS",
                    )
                    remote_observation = remote_evidence["observation"]
                    remote_tip = str(remote_observation["oid"])
                    containment_subject = {
                        "landed_head": landed_head,
                        "remote_tip": remote_tip,
                    }
                    containment_argv = chain_core._merge_cleanup_expected_argv(
                        current, "remote-containment", containment_subject
                    )
                    assert containment_argv is not None

                    def observe_containment(
                        result: chain_core.FencedProcessResult,
                    ) -> tuple[str, Mapping[str, Any]]:
                        ordinary = child_complete(result, 0, 1)
                        contained = (
                            result.returncode == 0 if ordinary else None
                        )
                        observation = {
                            "landed_head": landed_head,
                            "remote_tip": remote_tip,
                            "contained": contained,
                        }
                        return (
                            "passed" if contained is True else "failed",
                            observation,
                        )

                    current, _containment_result, containment_evidence = (
                        self._run_cleanup_child(
                            current,
                            common_lock,
                            lease,
                            operation="remote-containment",
                            fence_operation="containment",
                            subject=containment_subject,
                            argv=containment_argv,
                            observe=observe_containment,
                        )
                    )
                    fail_step(
                        containment_evidence,
                        "forge: merge cleanup failed — landed HEAD containment is not current",
                    )

                    with self.store.event_lock(str(current["chain_id"])):
                        cleanup_replay = self.store._read_replay_locked(
                            str(current["chain_id"])
                        )
                    summary = chain_core._merge_cleanup_history_summary(
                        cleanup_replay.events
                    )
                    worktree = Path(str(current["worktree"]["path"]))
                    local_subject = {
                        "path": str(worktree),
                        "branch": str(current["branch"]),
                        "candidate_head": str(
                            current["candidate"]["candidate_head"]
                        ),
                    }
                    branch_subject = {
                        "branch": local_subject["branch"],
                        "candidate_head": local_subject["candidate_head"],
                    }
                    if not (
                        summary.get("worktree_complete") is True
                        and summary.get("branch_complete") is True
                    ):
                        branch_observation_argv = chain_core._merge_cleanup_expected_argv(
                            current, "branch-observation", branch_subject
                        )
                        assert branch_observation_argv is not None

                        def observe_branch(
                            result: chain_core.FencedProcessResult,
                        ) -> tuple[str, Mapping[str, Any]]:
                            observation = chain_core._merge_cleanup_branch_observation(
                                engine._merge_cleanup_process_record(result),
                                branch_subject["branch"],
                            )
                            if (
                                observation["exists"] is True
                                and observation["oid"]
                                == branch_subject["candidate_head"]
                            ):
                                outcome = "passed"
                            elif observation["exists"] is False:
                                outcome = "already-absent"
                            else:
                                outcome = "failed"
                            return outcome, observation

                        current, _branch_observation, branch_evidence = (
                            self._run_cleanup_child(
                                current,
                                common_lock,
                                lease,
                                operation="branch-observation",
                                fence_operation="branch-delete",
                                subject=branch_subject,
                                argv=branch_observation_argv,
                                observe=observe_branch,
                            )
                        )
                        fail_step(
                            branch_evidence,
                            "forge: merge cleanup failed — recorded branch moved or is unobservable",
                        )

                    if summary.get("worktree_complete") is not True:
                        worktree_observation_argv = (
                            chain_core._merge_cleanup_expected_argv(
                                current,
                                "worktree-observation",
                                local_subject,
                            )
                        )
                        assert worktree_observation_argv is not None

                        def observe_worktree(
                            result: chain_core.FencedProcessResult,
                        ) -> tuple[str, Mapping[str, Any]]:
                            registered, head, branch = (
                                chain_core._merge_cleanup_worktree_inventory(
                                    engine._merge_cleanup_process_record(result),
                                    str(worktree),
                                )
                            )
                            path_exists = (
                                path_presence(worktree)
                                if result.authorized is True
                                else None
                            )
                            observation = {
                                "path": str(worktree),
                                "path_exists": path_exists,
                                "registered": registered,
                                "head": head,
                                "branch": branch,
                            }
                            if (
                                registered is True
                                and head == local_subject["candidate_head"]
                                and branch == local_subject["branch"]
                                and path_exists is True
                            ):
                                outcome = "passed"
                            elif registered is False and path_exists is False:
                                outcome = "already-absent"
                            else:
                                outcome = "failed"
                            return outcome, observation

                        current, _worktree_observation, worktree_evidence = (
                            self._run_cleanup_child(
                                current,
                                common_lock,
                                lease,
                                operation="worktree-observation",
                                fence_operation="worktree-remove",
                                subject=local_subject,
                                argv=worktree_observation_argv,
                                observe=observe_worktree,
                            )
                        )
                        fail_step(
                            worktree_evidence,
                            "forge: merge cleanup failed — worktree observation did not PASS",
                        )
                        if worktree_evidence["outcome"] == "passed":
                            worktree_remove_argv = chain_core._merge_cleanup_expected_argv(
                                current, "worktree-remove", local_subject
                            )
                            assert worktree_remove_argv is not None

                            def observe_worktree_removal(
                                result: chain_core.FencedProcessResult,
                            ) -> tuple[str, Mapping[str, Any]]:
                                exists = (
                                    path_presence(worktree)
                                    if result.authorized is True
                                    else None
                                )
                                observation = {
                                    "path": str(worktree),
                                    "exists": exists,
                                }
                                return (
                                    "passed"
                                    if child_complete(result, 0)
                                    and exists is False
                                    else "failed",
                                    observation,
                                )

                            current, _worktree_result, worktree_result_evidence = (
                                self._run_cleanup_child(
                                    current,
                                    common_lock,
                                    lease,
                                    operation="worktree-remove",
                                    fence_operation="worktree-remove",
                                    subject=local_subject,
                                    argv=worktree_remove_argv,
                                    observe=observe_worktree_removal,
                                )
                            )
                            fail_step(
                                worktree_result_evidence,
                                "forge: merge cleanup failed — worktree-remove did not PASS",
                            )

                    with self.store.event_lock(str(current["chain_id"])):
                        cleanup_replay = self.store._read_replay_locked(
                            str(current["chain_id"])
                        )
                    summary = chain_core._merge_cleanup_history_summary(
                        cleanup_replay.events
                    )
                    if summary.get("worktree_complete") is not True:
                        raise FrozenError(
                            "cleanup worktree step did not become durable",
                            chain_id=str(current["chain_id"]),
                            schema=REVISION9_OUTPUT_SCHEMA,
                        )
                    if summary.get("branch_complete") is not True:
                        if summary.get("branch_observed_present") is not True:
                            raise FrozenError(
                                "cleanup branch deletion lacks its fresh unmoved observation",
                                chain_id=str(current["chain_id"]),
                                schema=REVISION9_OUTPUT_SCHEMA,
                            )
                        branch_delete_argv = chain_core._merge_cleanup_expected_argv(
                            current, "branch-delete", branch_subject
                        )
                        assert branch_delete_argv is not None

                        def observe_branch_deletion(
                            result: chain_core.FencedProcessResult,
                        ) -> tuple[str, Mapping[str, Any]]:
                            passed = child_complete(result, 0)
                            observation = {
                                "branch": branch_subject["branch"],
                                "expected_oid": branch_subject[
                                    "candidate_head"
                                ],
                                "deleted": True if passed else None,
                            }
                            return (
                                "passed" if passed else "failed",
                                observation,
                            )

                        current, _branch_result, branch_result_evidence = (
                            self._run_cleanup_child(
                                current,
                                common_lock,
                                lease,
                                operation="branch-delete",
                                fence_operation="branch-delete",
                                subject=branch_subject,
                                argv=branch_delete_argv,
                                observe=observe_branch_deletion,
                            )
                        )
                        fail_step(
                            branch_result_evidence,
                            "forge: merge cleanup failed — branch-delete did not PASS",
                        )

                    with self.store.event_lock(str(current["chain_id"])):
                        cleanup_replay = self.store._read_replay_locked(
                            str(current["chain_id"])
                        )
                    summary = chain_core._merge_cleanup_history_summary(
                        cleanup_replay.events
                    )
                    if not (
                        summary.get("remote_containment") is not None
                        and summary.get("worktree_complete") is True
                        and summary.get("branch_complete") is True
                    ):
                        raise FrozenError(
                            "cleanup did not durably complete every required step",
                            chain_id=str(current["chain_id"]),
                            schema=REVISION9_OUTPUT_SCHEMA,
                        )
                    current = self._release_to_closed_locked(current, lease)
        return engine._success(
            current,
            f"merge chain {current['chain_id']} cleanup is durably closed",
            "none — merge chain closed",
        )

    def finalize(self) -> Outcome:
        """Execute one FR-235 bounded epoch under the ordered lock stack."""

        self._git_no_lazy_fetch_qualification = None
        for control in chain_core._REQUIRED_MERGE_INTEGRATION_CONTROLS:
            chain_core._require_merge_integration_control(control)
        state = self._preflight_lifecycle(self._load(), "merge finalize")
        self._halt(state)
        if state["state"] != "authorized":
            self._wrong_state(state, "authorized", "merge finalize")
        self._prepare_git_no_lazy_fetch_qualification(state)
        binding = state.get("run_binding")
        budget = engine._MergeEpochBudget()
        with self.store._journal_outer(
            binding if isinstance(binding, Mapping) else None
        ):
            with self._recording_common_lock(
                Path(str(state["worktree"]["common_dir"])),
                chain_id=str(state["chain_id"]),
                operation="finalize",
            ) as common_lock:
                with chain_core.acquire_chain_lease(
                    self.store.root,
                    chain_id=str(state["chain_id"]),
                    session=self.store._session(None),
                    exclusion=common_lock,
                ) as lease:
                    current = self.store.load_locked(
                        str(state["chain_id"]), lease=lease
                    )
                    if current["state"] != "authorized":
                        self._wrong_state(current, "authorized", "merge finalize")
                    current, candidate_observation = (
                        self._run_candidate_observation_locked(
                            current,
                            common_lock,
                            lease,
                            verb="merge finalize",
                            remote_tip=str(current["candidate"]["remote_tip"]),
                            expected_head=str(
                                current["candidate"]["candidate_head"]
                            ),
                            classify=False,
                        )
                    )
                    _observe_current_merge_candidate(
                        self.ctx,
                        current,
                        verb="merge finalize",
                        observation=candidate_observation,
                    )
                    starting_generation = str(
                        current["candidate"]["generation_digest"]
                    )
                    current = self._begin_epoch(current, lease)
                    current, fetched_tip, unchanged = self._run_epoch_fetch(
                        current, common_lock, lease, budget
                    )
                    if not unchanged:
                        current = self._run_epoch_rebase(
                            current,
                            fetched_tip,
                            common_lock,
                            lease,
                            budget,
                        )
                    current = self._run_epoch_suite(
                        current, common_lock, lease, budget
                    )
                    if (
                        str(current["candidate"]["generation_digest"])
                        != starting_generation
                    ):
                        current = self._park_integrated_review(current, lease)
                        return engine._success(
                            current,
                            "integrated generation passed its mechanical suite and is parked for fresh review",
                            f"forge review request --chain-id {current['chain_id']}",
                        )
                    current = self._run_remote_observation(
                        current,
                        common_lock,
                        lease,
                        budget,
                        phase="final-prepush",
                    )
                    if current["state"] == "authorized":
                        return engine._success(
                            current,
                            "merge epoch parked after authoritative remote movement",
                            f"forge merge finalize --chain-id {current['chain_id']}",
                        )
                    if current["state"] == "awaiting_approval":
                        raise chain_core._merge_refusal(
                            V2ReasonCode.REMOTE_CHURN,
                            "forge: merge finalize refused — remote churn exhausted the bounded retry counter",
                            remediation=(
                                "forge merge approve --candidate "
                                f"{current['candidate']['candidate_head']} --chain-id {current['chain_id']}"
                            ),
                            chain=current,
                        )
                    if current["state"] not in {"rebasing", "reverifying"}:
                        self._wrong_state(
                            current,
                            "an unchanged post-observation epoch",
                            "merge finalize",
                        )
                    current = self._run_epoch_push(
                        current, common_lock, lease, budget
                    )
        if current["state"] == "pushing":
            return engine._success(
                current,
                "merge push attempt was authoritatively observed as not landed",
                f"forge merge recover --chain-id {current['chain_id']}",
            )
        return engine._success(
            current,
            f"merge candidate {current['candidate']['candidate_head']} is durably pushed",
            f"forge merge cleanup --chain-id {current['chain_id']}",
        )


__all__ = [
    'MergeEngine',
    '_merge_command_engine',
    '_observe_current_merge_candidate',
    '_route_shared_chain_engine',
    'dispatch',
    'main',
    'prepare_merge_admission',
]
