"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
import sys
from typing import Any, Mapping, MutableMapping
from forge_cli import candidate as candidate_module, chain_core, runtime
from forge_cli.engine._archive import _archive_recheck as _archive_recheck
from forge_cli.engine._candidate_ops import _adopt_out_of_band_candidate as _adopt_out_of_band_candidate
from forge_cli.engine._command_lock import _serialize_worktree_command as _serialize_worktree_command
from forge_cli.engine._core import _archive_metadata as _archive_metadata, _run_halt as _run_halt
from forge_cli.engine._state import TERMINAL_STATES as TERMINAL_STATES, TERMINAL_TOUCH_VERBS as TERMINAL_TOUCH_VERBS
from forge_cli.envelope import FrozenError, REVISION9_OUTPUT_SCHEMA, ReasonCode, Refusal
from . import _verbs_tombstone
from . import _verbs_status
from . import _verbs_lifecycle
from . import _verbs_gate
from . import _verbs_gate_evals
from . import _verbs_decision
from . import _verbs_review_request
from . import _verbs_review_collect
from . import _verbs_finalize


class Engine:
    def __init__(self, ctx: chain_core.CommandContext) -> None:
        self.ctx = ctx
    _require_tombstone_control = staticmethod(_verbs_tombstone._require_tombstone_control)
    _tombstone_outcome = _verbs_tombstone._tombstone_outcome
    operator_tombstone = _serialize_worktree_command(_verbs_tombstone.operator_tombstone)
    journal_batch_recover = _verbs_status.journal_batch_recover
    journal_ingest_chain = _verbs_status.journal_ingest_chain

    def _chains_for_worktree(self) -> list[dict[str, Any]]:
        chains: list[dict[str, Any]] = []
        for chain_id in self.ctx.store.list_ids(family="commit"):
            try:
                state = self.ctx.store.load(chain_id)
            except FrozenError:
                # Explicit selection surfaces this chain's own failure.  An
                # unrelated frozen file never blocks a healthy worktree chain.
                print(
                    "forge: warning — skipped unreadable chain "
                    f"{chain_id} while enumerating commit chains",
                    file=sys.stderr,
                )
                continue
            if state["staging"].get("worktree_root") == str(self.ctx.repo.root):
                chains.append(state)
        return chains

    def select(
        self, *, include_terminal: bool = True, family_proven: bool = False
    ) -> dict[str, Any]:
        if self.ctx.options.chain_id:
            if (
                not family_proven
                and self.ctx.store.chain_family(self.ctx.options.chain_id)
                != "commit"
            ):
                raise FrozenError(
                    "commit selection refused a merge-family chain",
                    chain_id=self.ctx.options.chain_id,
                    schema=REVISION9_OUTPUT_SCHEMA,
                )
            state = self.ctx.store.load(
                self.ctx.options.chain_id, family_proven=family_proven
            )
            if state.get("journal_outbox") is not None:
                state = self.ctx.store.recover_pending_outbox(state)
            if state["staging"].get("worktree_root") != str(self.ctx.repo.root):
                raise Refusal(
                    ReasonCode.CANDIDATE_STALE,
                    "chain belongs to a different worktree/index",
                    expected=str(self.ctx.repo.root),
                    observed=str(state["staging"].get("worktree_root")),
                    remediation="run the command from the chain's recorded worktree",
                    chain=state,
                )
            return state
        chains = self._chains_for_worktree()
        live = [state for state in chains if state["state"] not in TERMINAL_STATES]
        candidates = live or (chains if include_terminal else [])
        if not candidates:
            raise Refusal(
                ReasonCode.STATE_PRECONDITION,
                "no commit chain exists for this worktree",
                expected="a chain created by commit start",
                observed="none",
                remediation="forge commit start --paths <path>...",
            )
        selected = max(candidates, key=lambda item: str(item["created_at"]))
        if selected.get("journal_outbox") is not None:
            selected = self.ctx.store.recover_pending_outbox(selected)
        return selected
    _live_chain = _verbs_lifecycle._live_chain

    def _record_head_moved(self, state: MutableMapping[str, Any], current: str) -> None:
        old = str(state["repo_head"])
        marker = state["steps"].get("head_moved")
        if isinstance(marker, dict) and marker.get("old") == old and marker.get("new") == current:
            return
        state["steps"]["head_moved"] = {
            "old": old,
            "new": current,
            "diagnostic": "out-of-band commit, not chain corruption",
            "recorded_at": chain_core.iso_z(),
        }
        self.ctx.store.persist(
            state,
            "head_moved",
            {
                "old": old,
                "new": current,
                "diagnostic": "out-of-band commit, not chain corruption",
            },
        )

    def _preflight(
        self,
        state: MutableMapping[str, Any],
        verb: str,
        *,
        mutating: bool = True,
        allow_head_moved: bool = False,
        allow_committing: bool = False,
        check_candidate: bool = True,
    ) -> None:
        if mutating:
            _run_halt(self.ctx, state)
        if _archive_metadata(state) is not None and verb not in {
            "status",
            "commit abort",
        }:
            # Archive chains are immutable single-path candidates.  Recheck
            # before generic candidate adoption or any other state mutation,
            # so an edited renderer input/index cannot erase archive mode.
            _archive_recheck(self.ctx, state, "transition")
        if state.get("run_binding") is not None:
            chain_core._validate_bound_chain_state(state)
        if (
            state.get("candidate", {}).get("sha256")
            and not chain_core.candidate_is_v2(state)
            and verb not in {"commit restage", "commit abort"}
        ):
            raise Refusal(
                ReasonCode.STATE_PRECONDITION,
                "legacy candidate must be restaged before the chain can advance",
                expected=candidate_module.CANDIDATE_SCHEMA,
                observed="legacy staged-diff candidate",
                remediation=chain_core._forge_command(
                    state, "commit restage --paths <path>..."
                ),
                chain=state,
            )
        if state["state"] == "committing" and not allow_committing:
            raise Refusal(
                ReasonCode.STATE_PRECONDITION,
                "chain is in the finalize crash window; non-recovery verb refused",
                expected="status or commit finalize recovery",
                observed=verb,
                remediation=chain_core._forge_command(state, "status"),
                chain=state,
            )
        if (
            runtime.utc_now() >= chain_core.parse_time(str(state["inactive_after"]))
            and verb not in TERMINAL_TOUCH_VERBS
        ):
            raise Refusal(
                ReasonCode.INACTIVE_CHAIN,
                "chain is inactive after 24 hours without an event",
                expected=f"command before {state['inactive_after']}",
                observed=chain_core.iso_z(),
                remediation=chain_core._forge_command(state, "commit abort --reason inactive"),
                chain=state,
            )
        if (
            int(state["review"].get("iteration", 0)) >= 8
            and verb not in TERMINAL_TOUCH_VERBS
        ):
            raise Refusal(
                ReasonCode.ITERATION_CAP,
                "review iteration cap of 8 reached; no further state advancement is admitted",
                expected="PASS before iteration 8",
                observed=str(state["review"].get("iteration")),
                remediation=chain_core._forge_command(state, "commit abort --reason iteration-cap"),
                chain=state,
            )
        current_head = self.ctx.repo.head()
        if current_head != state["repo_head"]:
            self._record_head_moved(state, current_head)
            if not allow_head_moved:
                raise Refusal(
                    ReasonCode.HEAD_MOVED,
                    (
                        "out-of-band commit, not chain corruption: "
                        f"{state['repo_head']} -> {current_head}"
                    ),
                    expected=str(state["repo_head"]),
                    observed=current_head,
                    remediation=chain_core._forge_command(state, "commit rebase"),
                    chain=state,
                )
        if (
            check_candidate
            and state["state"] not in TERMINAL_STATES | {"committing"}
            and state["candidate"].get("sha256")
        ):
            observed = self.ctx.repo.candidate_hash()
            expected = state["candidate"]["sha256"]
            if observed != expected:
                old, has_candidate_bytes = _adopt_out_of_band_candidate(
                    self.ctx,
                    state,
                    observed,
                    detected_by=verb,
                )
                raise Refusal(
                    ReasonCode.CANDIDATE_STALE,
                    "out-of-band index change invalidated candidate evidence and reran classification",
                    expected=str(old),
                    observed=observed,
                    remediation=chain_core._forge_command(
                        state,
                        "verify"
                        if has_candidate_bytes
                        else "commit restage --paths <path>...",
                    ),
                    chain=state,
                )
    status = _serialize_worktree_command(_verbs_status.status)

    def next_step(self, state: Mapping[str, Any]) -> str:
        if (
            state.get("candidate", {}).get("sha256")
            and not chain_core.candidate_is_v2(state)
            and state.get("state") not in TERMINAL_STATES | {"committing"}
        ):
            return chain_core._forge_command(state, "commit restage --paths <path>...")
        state_name = state["state"]
        if state_name == "classifying":
            return chain_core._forge_command(state, "classify")
        if state_name == "verifying":
            return chain_core._forge_command(state, "verify")
        if state_name == "reviewing":
            request = state["review"].get("request")
            if not request:
                return chain_core._forge_command(state, "review request")
            if request.get("reviewer") == "review-cheap":
                return chain_core._forge_command(state, "review collect")
            return chain_core._forge_command(state, "review attach --verdict-file <path>")
        if state_name == "revising":
            return chain_core._forge_command(state, "commit restage --paths <path>...")
        if state_name == "awaiting_approval":
            return chain_core._forge_command(
                state,
                f"commit approve --candidate {state['candidate'].get('sha256')}",
            )
        if state_name == "authorized":
            return chain_core._forge_command(state, "commit finalize --message <message>")
        if state_name == "committing":
            return chain_core._forge_command(state, "status")
        if state_name == "aborted":
            return "forge commit start --paths <path>..."
        return "none — chain closed"
    start = _serialize_worktree_command(_verbs_lifecycle.start)
    classify = _serialize_worktree_command(_verbs_lifecycle.classify)
    restage = _serialize_worktree_command(_verbs_lifecycle.restage)
    abort = _serialize_worktree_command(_verbs_tombstone.abort)
    abort_disposition = _serialize_worktree_command(_verbs_tombstone.abort_disposition)
    _tombstone_abort_disposition = _verbs_tombstone._tombstone_abort_disposition

    def _wrong_state(self, state: Mapping[str, Any], expected: str, verb: str) -> None:
        reason = (
            ReasonCode.APPROVAL_REQUIRED
            if state["state"] == "awaiting_approval" and verb == "commit finalize"
            else ReasonCode.STATE_PRECONDITION
        )
        raise Refusal(
            reason,
            f"{verb} is not admitted from state {state['state']}",
            expected=expected,
            observed=str(state["state"]),
            remediation=self.next_step(state),
            chain=state,
        )
    rebase = _serialize_worktree_command(_verbs_lifecycle.rebase)
    _pending_mutating_gate = _verbs_gate._pending_mutating_gate
    _resolve_gate = _verbs_gate._resolve_gate
    _run_fresh_reviewer_evals = _verbs_gate_evals._run_fresh_reviewer_evals
    gate_run = _serialize_worktree_command(_verbs_gate.gate_run)
    scan_secrets = _serialize_worktree_command(_verbs_gate.scan_secrets)
    verify = _serialize_worktree_command(_verbs_decision.verify)
    _profiles_for_path = staticmethod(_verbs_review_request._profiles_for_path)
    _review_package = _verbs_review_request._review_package
    review_request = _serialize_worktree_command(_verbs_review_request.review_request)
    _parse_verdict = staticmethod(_verbs_review_collect._parse_verdict)
    _apply_verdict = _verbs_review_collect._apply_verdict
    review_collect = _serialize_worktree_command(_verbs_review_collect.review_collect)
    review_attach = _serialize_worktree_command(_verbs_review_collect.review_attach)
    review_disposition = _serialize_worktree_command(_verbs_decision.review_disposition)
    approve = _serialize_worktree_command(_verbs_decision.approve)
    skip = _serialize_worktree_command(_verbs_decision.skip)

    def _emit_decision(self, state: Mapping[str, Any], event: str, reason: str) -> None:
        candidate = str(state["candidate"].get("sha256") or "")
        if event in {"gate_commit", "fast_allowed"}:
            candidate = str(state["commit_result"].get("commit_sha") or "")
        argv = [
            sys.executable,
            str(self.ctx.helper("emit-decision-event.py")),
            "--candidate",
            candidate,
            "--event",
            event,
            "--policy-sha",
            str(state["policy_source"].get("sha") or ""),
            "--reason",
            reason,
            "--surface",
            "forge-cli",
        ]
        try:
            process = runtime.run_bounded(
                argv,
                cwd=self.ctx.repo.root,
                timeout=30.0,
                verbose=self.ctx.options.verbose,
            )
            if process.returncode != 0 and self.ctx.options.verbose:
                print(
                    f"forge: advisory decision-event emission exited {process.returncode}",
                    file=sys.stderr,
                )
        except Exception as exc:
            if self.ctx.options.verbose:
                print(f"forge: advisory decision-event emission failed: {exc}", file=sys.stderr)
    finalize = _serialize_worktree_command(_verbs_finalize.finalize)
    _release_lock = _verbs_finalize._release_lock
    _recover_committing = _verbs_finalize._recover_committing
