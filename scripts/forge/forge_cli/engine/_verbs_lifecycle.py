from __future__ import annotations

import copy
from typing import Any, Sequence

from forge_cli import chain_core
from forge_cli.engine._approval import _authorization_problem as _authorization_problem
from forge_cli.engine._approval import _success as _success
from forge_cli.engine._candidate_ops import (
    _invalidate_candidate_evidence as _invalidate_candidate_evidence,
)
from forge_cli.engine._candidate_ops import _stage_paths as _stage_paths
from forge_cli.engine._candidate_ops import _tree_delta as _tree_delta
from forge_cli.engine._classification import _run_classification as _run_classification
from forge_cli.engine._command_lock import _new_state as _new_state
from forge_cli.engine._core import _run_halt as _run_halt
from forge_cli.engine._core import _transition_state as _transition_state
from forge_cli.engine._core import chain_id_now as chain_id_now
from forge_cli.engine._state import TERMINAL_STATES as TERMINAL_STATES
from forge_cli.envelope import (
    FrozenError,
    Outcome,
    ReasonCode,
    Refusal,
)
from forge_cli.policy import PolicyError, parse_policy, sha256_bytes


def _live_chain(self) -> dict[str, Any] | None:
    for state in self._chains_for_worktree():
        if state["state"] not in TERMINAL_STATES:
            return state
    return None

def start(
    self,
    paths: Sequence[str],
    declared_tier: str | None,
) -> Outcome:
    _run_halt(self.ctx)
    with self.ctx.store.admission_lock(self.ctx.repo.root):
        live = self._live_chain()
        if live is not None:
            # ``start`` is still a command against the current owner when
            # one exists.  Apply the same inactivity, crash-window, HEAD,
            # and candidate invalidation precedence as every other verb
            # before reporting the ordinary one-live-chain refusal.  The
            # composed halt check already ran immediately above.
            self._preflight(live, "commit start", mutating=False)
            remediation = (
                chain_core._forge_command(live, "commit finalize --message <message>")
                if live["state"] == "authorized"
                else chain_core._forge_command(live, "commit abort --reason superseded")
            )
            raise Refusal(
                ReasonCode.LIVE_CHAIN_EXISTS,
                f"live commit chain already exists for this worktree: {live['chain_id']}",
                expected="no live chain for this worktree/index",
                observed=str(live["chain_id"]),
                remediation=remediation,
                chain=live,
            )
        staged = self.ctx.repo.staged_paths()
        if staged:
            names = ", ".join(staged)
            raise Refusal(
                ReasonCode.DIRTY_INDEX,
                f"pre-existing staged content belongs to no chain: {names}",
                expected="empty Git index diff",
                observed=names,
                remediation="unstage the named paths, then rerun commit start",
            )
        normalized = self.ctx.repo.normalize_paths(paths)
        try:
            head, raw = self.ctx.repo.policy()
            policy = parse_policy(head, raw)
        except (OSError, PolicyError, UnicodeError) as exc:
            raise Refusal(
                ReasonCode.POLICY_UNREADABLE,
                f"committed policy is unreadable: {exc}",
                expected="git show HEAD:forge-project.md with valid configured regions",
                observed=str(exc),
                remediation="commit a valid forge-project.md or use the separate bootstrap flow",
            ) from exc
        self.ctx.policy = policy
        for _attempt in range(32):
            chain_id = chain_id_now()
            if not self.ctx.store.state_path(chain_id).exists() and not self.ctx.store.events_path(chain_id).exists():
                break
        else:
            raise FrozenError("unable to allocate a collision-free chain identifier")
        state = _new_state(
            chain_id,
            self.ctx.repo,
            head,
            policy,
            normalized,
            declared_tier,
        )
        self.ctx.store.create(state, "chain_started", {"paths": normalized})
        _old, candidate = _stage_paths(
            self.ctx, state, normalized, clear_old=False
        )
        self.ctx.store.persist(
            state,
            "candidate_staged",
            {"candidate": candidate, "paths": list(state["paths"])},
        )
    try:
        _run_classification(self.ctx, state)
    except Exception:
        # The admitted chain remains visible and recoverable; staged bytes
        # are never silently detached from their chain after admission.
        raise
    return _success(
        state,
        f"commit chain {chain_id} started and classified as {state['tier']['effective']}",
        self.next_step(state),
    )

def classify(self) -> Outcome:
    state = self.select(include_terminal=False)
    self._preflight(state, "classify")
    if state["state"] not in {"classifying", "verifying"}:
        self._wrong_state(state, "classifying or verifying", "classify")
    if not state.get("paths"):
        raise Refusal(
            ReasonCode.CANDIDATE_STALE,
            "classification refuses an empty staged candidate",
            expected="nonempty exact git diff --cached bytes",
            observed="empty staged diff",
            remediation=chain_core._forge_command(
                state, "commit restage --paths <path>..."
            ),
            chain=state,
        )
    current = self.ctx.repo.candidate_hash()
    if current != state["candidate"].get("sha256"):
        raise Refusal(
            ReasonCode.CANDIDATE_STALE,
            "classification candidate differs from the recorded staged bytes",
            expected=str(state["candidate"].get("sha256")),
            observed=current,
            remediation=chain_core._forge_command(state, "commit restage --paths <path>..."),
            chain=state,
        )
    _run_classification(self.ctx, state)
    return _success(
        state,
        f"candidate classified as {state['tier']['effective']}",
        self.next_step(state),
    )

def restage(self, paths: Sequence[str]) -> Outcome:
    state = self.select(include_terminal=False)
    legacy_migration = bool(
        state.get("candidate", {}).get("sha256")
        and not chain_core.candidate_is_v2(state)
    )
    self._preflight(
        state,
        "commit restage",
        allow_head_moved=legacy_migration,
        check_candidate=False,
    )
    if state["state"] not in {"revising", "classifying", "verifying", "reviewing", "awaiting_approval", "authorized"}:
        self._wrong_state(state, "a live pre-commit state", "commit restage")
    if int(state["review"].get("iteration", 0)) >= 8:
        state["review"]["residual_risk"] = {
            "at": chain_core.iso_z(),
            "reason": "review iteration cap reached",
            "findings": (state["review"].get("verdict") or {}).get("findings", []),
        }
        self.ctx.store.persist(state, "iteration_cap", {"iteration": 8})
        raise Refusal(
            ReasonCode.ITERATION_CAP,
            "review iteration cap of 8 reached; residual risk recorded",
            expected="fewer than 8 BLOCK iterations",
            observed=str(state["review"].get("iteration")),
            remediation=chain_core._forge_command(state, "commit abort --reason iteration-cap"),
            chain=state,
        )
    if legacy_migration:
        current_head = self.ctx.repo.head()
        if current_head != state["repo_head"]:
            try:
                _sha, current_policy_bytes = self.ctx.repo.policy(current_head)
            except OSError as exc:
                raise Refusal(
                    ReasonCode.POLICY_UNREADABLE,
                    f"new-HEAD policy is unreadable during restage migration: {exc}",
                    expected=f"git show {current_head}:forge-project.md",
                    observed=str(exc),
                    remediation=chain_core._forge_command(
                        state, "commit abort --reason policy-unreadable"
                    ),
                    chain=state,
                ) from exc
            current_policy_digest = sha256_bytes(current_policy_bytes)
            if current_policy_digest != state["policy_source"].get("digest"):
                raise Refusal(
                    ReasonCode.POLICY_CHANGED,
                    "committed policy bytes changed at the new HEAD; legacy candidate cannot migrate",
                    expected=str(state["policy_source"].get("digest")),
                    observed=current_policy_digest,
                    remediation=chain_core._forge_command(
                        state, "commit abort --reason policy-changed"
                    ),
                    chain=state,
                )
            state["repo_head"] = current_head
            state["policy_source"]["sha"] = current_head
            state["steps"].pop("head_moved", None)
    normalized = self.ctx.repo.normalize_paths(paths)
    old_record = copy.deepcopy(state["candidate"])
    old_tree = str(old_record.get("tree_oid") or self.ctx.repo.candidate_snapshot().tree_oid)
    old, candidate = _stage_paths(self.ctx, state, normalized, clear_old=True)
    delta = _tree_delta(self.ctx, old_tree, str(state["candidate"]["tree_oid"]))
    _invalidate_candidate_evidence(state, preserve_operator_cosign=True)
    _transition_state(state, "classifying")
    self.ctx.store.persist(
        state,
        "candidate_restaged",
        {
            "old_candidate": old,
            "new_candidate": candidate,
            "old_candidate_identity": old_record,
            "new_candidate_identity": copy.deepcopy(state["candidate"]),
            "old_tree": old_tree,
            "new_tree": state["candidate"]["tree_oid"],
            "delta": delta,
            "paths": list(state["paths"]),
        },
    )
    _run_classification(self.ctx, state)
    return _success(
        state,
        f"candidate restaged and reclassified: {candidate}",
        self.next_step(state),
    )

def rebase(self) -> Outcome:
    state = self.select(include_terminal=False)
    self._preflight(
        state,
        "commit rebase",
        allow_head_moved=True,
        check_candidate=False,
    )
    if state["state"] in TERMINAL_STATES:
        self._wrong_state(state, "a live pre-commit state", "commit rebase")
    current_head = self.ctx.repo.head()
    if current_head == state["repo_head"] and "head_moved" not in state["steps"]:
        raise Refusal(
            ReasonCode.STATE_PRECONDITION,
            "commit rebase requires diagnosed out-of-band HEAD movement",
            expected="current HEAD different from recorded repo_head",
            observed=current_head,
            remediation=self.next_step(state),
            chain=state,
        )
    try:
        _sha, raw = self.ctx.repo.policy(current_head)
    except OSError as exc:
        raise Refusal(
            ReasonCode.POLICY_UNREADABLE,
            f"new-HEAD policy is unreadable during rebase: {exc}",
            expected=f"git show {current_head}:forge-project.md",
            observed=str(exc),
            remediation=chain_core._forge_command(state, "commit abort --reason policy-unreadable"),
            chain=state,
        ) from exc
    old_policy_digest = state["policy_source"].get("digest")
    new_policy_digest = sha256_bytes(raw)
    if new_policy_digest != old_policy_digest:
        old_head = state["repo_head"]
        _transition_state(state, "aborted")
        state["commit_result"] = {
            "aborted_at": chain_core.iso_z(),
            "reason": "policy-changed",
            "old_head": old_head,
            "new_head": current_head,
        }
        self.ctx.store.persist(
            state,
            "policy_changed",
            {
                "old_digest": old_policy_digest,
                "new_digest": new_policy_digest,
                "old_head": old_head,
                "new_head": current_head,
            },
        )
        raise Refusal(
            ReasonCode.POLICY_CHANGED,
            "committed policy bytes changed at the new HEAD; chain ended and must restart",
            expected=str(old_policy_digest),
            observed=new_policy_digest,
            remediation="forge commit start --paths <path>...",
            chain=state,
        )
    try:
        current_policy = parse_policy(current_head, raw)
    except (PolicyError, UnicodeError) as exc:
        raise Refusal(
            ReasonCode.POLICY_UNREADABLE,
            f"byte-identical new-HEAD policy is unreadable during rebase: {exc}",
            expected=f"valid committed policy at {current_head}",
            observed=str(exc),
            remediation=chain_core._forge_command(
                state, "commit abort --reason policy-unreadable"
            ),
            chain=state,
        ) from exc
    self.ctx.policy = current_policy
    old_candidate = str(state["candidate"].get("sha256"))
    old_candidate_record = copy.deepcopy(state["candidate"])
    old_head = str(state["repo_head"])
    old_review = copy.deepcopy(state["review"])
    old_secret = copy.deepcopy(state["steps"].get("secret-scan"))
    old_approval = copy.deepcopy(state.get("approval", {}))
    old_authorization = copy.deepcopy(state.get("authorization", {}))
    state["repo_head"] = current_head
    state["policy_source"]["sha"] = current_head
    paths = list(state["paths"])
    _old, new_candidate = _stage_paths(self.ctx, state, paths, clear_old=False)
    unchanged = new_candidate == old_candidate
    review_unchanged = bool(
        chain_core.candidate_is_v2({"candidate": old_candidate_record})
        and old_candidate_record.get("review_diff_sha256")
        == state["candidate"].get("review_diff_sha256")
        and old_candidate_record.get("review_diff_byte_count")
        == state["candidate"].get("review_diff_byte_count")
        and sorted(paths) == sorted(state.get("paths", []))
    )
    _invalidate_candidate_evidence(
        state,
        preserve_diff_scoped=review_unchanged,
        preserve_operator_cosign=True,
    )
    if review_unchanged:
        if old_secret is not None:
            state["steps"]["secret-scan"] = old_secret
        if (
            old_review.get("verdict")
            and old_review["verdict"].get("candidate") == new_candidate
        ):
            state["review"] = old_review
            state["review"]["request"] = None
    if unchanged and review_unchanged:
        if old_authorization and _authorization_problem(
            {**state, "authorization": old_authorization}
        ) is None:
            state["approval"] = old_approval
            state["authorization"] = old_authorization
    state["steps"].pop("head_moved", None)
    _transition_state(state, "classifying")
    self.ctx.store.persist(
        state,
        "head_rebased",
        {
            "old_head": old_head,
            "new_head": current_head,
            "old_candidate": old_candidate,
            "new_candidate": new_candidate,
            "candidate_unchanged": unchanged,
            "diagnostic": "out-of-band commit, not chain corruption",
        },
    )
    _run_classification(self.ctx, state)
    return _success(
        state,
        (
            "re-pinned to moved HEAD; candidate unchanged and diff-scoped evidence retained"
            if unchanged and review_unchanged
            else "re-pinned to moved HEAD; changed candidate invalidated diff-scoped evidence"
        ),
        self.next_step(state),
    )
