from __future__ import annotations

import copy
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

from forge_cli import chain_core, engine
from forge_cli.envelope import REVISION9_OUTPUT_SCHEMA, FrozenError, Outcome, V2ReasonCode
from forge_cli.policy import sha256_bytes

if TYPE_CHECKING:
    from forge_cli.app._merge_engine import MergeEngine

def abort(self: MergeEngine, reason: str | None = None) -> Outcome:
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

def _attempted_release_preconditions_locked(
    self: MergeEngine,
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
