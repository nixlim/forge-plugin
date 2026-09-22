from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from forge_cli import chain_core, engine
from forge_cli.app._candidate_observation import _observe_current_merge_candidate
from forge_cli.envelope import REVISION9_OUTPUT_SCHEMA, FrozenError, Outcome, V2ReasonCode
from forge_cli.policy import Policy, sha256_bytes

if TYPE_CHECKING:
    from forge_cli.app._merge_engine import MergeEngine

def _review_package(
    self: MergeEngine,
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

def review_request(self: MergeEngine) -> Outcome:
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
    oversized = engine._review_package_is_oversized(package)
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
    }
    if oversized:
        bound = engine._merge_run_directory(state)
        package_path = (
            self.ctx.store.common_root / package_ref
            if bound is None
            else bound[1] / package_ref
        )
        request.update(
            {
                "transport": "single-master-package",
                "window_size": engine.REVIEW_MASTER_WINDOW_BYTES,
                "window_count": engine._review_master_window_count(len(package)),
                "invocation": (
                    "spawn one review-final with oversized "
                    + engine._review_master_transport(
                        package_path, len(package), package_digest
                    )
                    + f" candidate={state['candidate']['candidate_head']}"
                    + f" generation={state['candidate']['generation_digest']}"
                    + f" target={state['target']['destination_ref']}"
                    + f" package={package_digest}"
                ),
            }
        )
    else:
        request["invocation"] = (
            "spawn one review-final with master package "
            f"{package_ref} candidate {state['candidate']['candidate_head']} "
            f"generation {state['candidate']['generation_digest']} "
            f"target {state['target']['destination_ref']} digest {package_digest}"
        )
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
            f"review-final oversized; invocation={request['invocation']}"
            if oversized
            else (
                f"review-final package={package_ref} digest={package_digest}; "
                f"invocation={request['invocation']}"
            )
        ),
        f"forge review attach --verdict-file <path> --chain-id {state['chain_id']}",
        evidence_refs=[package_ref],
    )

def review_collect(self: MergeEngine) -> Outcome:
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
