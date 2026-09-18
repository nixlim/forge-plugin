"""Extracted from scripts/forge/forge_cli/app/__init__.py."""
from __future__ import annotations
import os
from pathlib import Path
from forge_cli import chain_core, engine
from forge_cli.envelope import V2ReasonCode
from forge_cli.policy import PolicyError, parse_policy, sha256_bytes


def prepare_merge_admission(
    ctx: chain_core.CommandContext,
    worktree: str,
    declared_tier: str | None,
    *,
    task: str | None = None,
    create_run_lock: bool = False,
) -> engine.MergeAdmission:
    """Prove FR-231 admission, reserving only an opted-in start run lock."""

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
            create_batch_lock=create_run_lock,
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
