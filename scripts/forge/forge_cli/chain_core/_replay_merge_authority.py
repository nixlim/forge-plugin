"""Authenticate replay merge authority; no journal or run authority."""

from __future__ import annotations

import copy
import re
import subprocess
from typing import Any, cast

from ._replay_frames import (
    MergeCurrentGateFactsFrame,
    MergeIntroducedDispositionValidFrame,
    MergeIntroducedGateFactFrame,
    MergePendingDispositionCosignFrame,
    MergeRequiredGateIdsFrame,
)
from ._replay_merge_candidates import _merge_generation, _merge_review_iteration
from ._replay_values import _merge_hex, _utc_value
from ._replay_vocabulary import _CONTINUE_REPLAY, REVIEW_ROLES, REVIEW_VERDICTS
from ._state import SHA256_RE
from forge_cli.policy import sha256_bytes


def _review_binding_for_state(state: dict[str, Any]) -> dict[str, Any] | None:
    review = state.get("review")
    if not isinstance(review, dict):
        return None
    verdict = review.get("verdict")
    request = review.get("request")
    if not isinstance(verdict, dict):
        return None
    reviewer_role = verdict.get("reviewer_role")
    if reviewer_role is None and isinstance(request, dict):
        reviewer_role = request.get("reviewer")
    candidate = {
        "verdict": verdict.get("verdict"),
        "iteration": review.get("iteration"),
        "reviewer_role": reviewer_role,
        "package_digest": verdict.get("package_digest"),
    }
    if (
        candidate["verdict"] not in REVIEW_VERDICTS
        or type(candidate["iteration"]) is not int
        or int(candidate["iteration"]) <= 0
        or (candidate["reviewer_role"] not in REVIEW_ROLES)
        or (not isinstance(candidate["package_digest"], str))
        or (SHA256_RE.fullmatch(str(candidate["package_digest"])) is None)
    ):
        return None
    return candidate


def _merge_iteration_cap_residual_current(state: dict[str, Any]) -> bool:
    """Require the durable residual-risk fact for an eighth BLOCK."""
    review = state.get("review")
    verdict = review.get("verdict") if isinstance(review, dict) else None
    residual = review.get("residual_risk") if isinstance(review, dict) else None
    return bool(
        isinstance(verdict, dict)
        and verdict.get("verdict") == "BLOCK"
        and isinstance(residual, dict)
        and isinstance(residual.get("reason"), str)
        and bool(str(residual["reason"]).strip())
        and isinstance(residual.get("findings"), list)
        and (residual.get("findings") == verdict.get("findings", []))
        and (residual.get("at") is None or _utc_value(residual.get("at")) is not None)
    )


def _check_merge_gate_fact_batch(frame: MergeCurrentGateFactsFrame) -> Any:
    if isinstance(frame.value, dict):
        frame.facts = (frame.value,)
    elif (
        isinstance(frame.value, list)
        and frame.value
        and all(isinstance(item, dict) for item in frame.value)
    ):
        values = [item for item in frame.value if isinstance(item, dict)]
        if frame.step_id.startswith("stack:"):
            latest = values[-1]
            batch_id = latest.get("batch_id")
            cell_count = latest.get("cell_count")
            if (
                not isinstance(batch_id, str)
                or not batch_id
                or type(cell_count) is not int
                or (cell_count <= 0)
            ):
                return None
            frame.facts = tuple(
                item for item in values if item.get("batch_id") == batch_id
            )
            if len(frame.facts) != cell_count or {
                item.get("cell_index") for item in frame.facts
            } != set(range(1, cell_count + 1)):
                return None
        else:
            frame.facts = (values[-1],)
    else:
        return None
    prefix = "gate-1: " if frame.step_id == "gate-1" else "gate-2: "
    if any(
        fact.get("result") != "passed"
        or fact.get("generation_digest") != frame.generation_digest
        or (not isinstance(fact.get("criterion"), str))
        or (not str(fact["criterion"]).startswith(prefix))
        for fact in frame.facts
    ):
        return None
    return _CONTINUE_REPLAY


def _check_merge_gate_fact_result(frame: MergeCurrentGateFactsFrame) -> Any:
    return tuple(copy.deepcopy(fact) for fact in frame.facts)


def _check_merge_introduced_gate_delta(frame: MergeIntroducedGateFactFrame) -> Any:
    prior_steps = frame.prior.get("steps")
    current_steps = frame.current.get("steps")
    if not isinstance(prior_steps, dict) or not isinstance(current_steps, dict):
        return None
    changed = [
        name
        for name in set(prior_steps) | set(current_steps)
        if prior_steps.get(name) != current_steps.get(name)
    ]
    if len(changed) != 1:
        return None
    frame.step_id = str(changed[0])
    old_value = prior_steps.get(frame.step_id)
    new_value = current_steps.get(frame.step_id)
    frame.fact = new_value
    if isinstance(new_value, list):
        old_runs = old_value if isinstance(old_value, list) else []
        if (
            len(new_value) != len(old_runs) + 1
            or new_value[:-1] != old_runs
        ):
            return None
        frame.fact = new_value[-1]
    elif old_value is not None:
        return None
    return _CONTINUE_REPLAY


def _check_merge_introduced_gate_result(frame: MergeIntroducedGateFactFrame) -> Any:
    if not isinstance(frame.fact, dict):
        return None
    return (frame.step_id, frame.fact)


def _check_merge_disposition_cosign_inputs(frame: MergePendingDispositionCosignFrame) -> Any:
    review = frame.state.get("review")
    if not isinstance(review, dict):
        return False
    if review.get("operator_cosign_required") is True:
        return True
    frame.dispositions = review.get("dispositions", [])
    if not isinstance(frame.dispositions, list):
        return True
    return _CONTINUE_REPLAY


def _check_merge_disposition_cosign_required(frame: MergePendingDispositionCosignFrame) -> Any:
    for replay_disposition in frame.dispositions:
        disposition = replay_disposition
        if not isinstance(disposition, dict):
            return True
        severity = disposition.get(
            "finding_severity", disposition.get("severity")
        )
        approval = frame.state.get("approval")
        separately_cosigned = bool(
            isinstance(approval, dict)
            and approval.get("purpose") == "finding-disposition"
            and (approval.get("chain_id") == frame.state.get("chain_id"))
            and (approval.get("finding") == disposition.get("finding"))
            and (approval.get("resolution") == disposition.get("resolution"))
        )
        if severity in {"CRITICAL", "MAJOR"} and (
            not (
                disposition.get("operator_cosign") is True
                or disposition.get("cosigned") is True
                or separately_cosigned
            )
        ):
            return True
    return False


def _check_merge_gate_requirements_inputs(frame: MergeRequiredGateIdsFrame) -> Any:
    tier = frame.state.get("tier")
    if not isinstance(tier, dict) or not isinstance(tier.get("categories"), list):
        return None
    frame.intrinsic = {
        "gate-1",
        "assertion-sensor",
        *(
            f"stack:{category}"
            for category in tier["categories"]
            if isinstance(category, str) and category
        ),
    }
    supplied = (
        frame.context.get("required_gate_ids") if isinstance(frame.context, dict) else None
    )
    if supplied is not None:
        if not isinstance(supplied, (list, tuple, frozenset, set)) or not all(
            isinstance(value, str) and value for value in supplied
        ):
            return None
        frame.selected = frozenset(str(value) for value in supplied)
        return frame.selected if frame.intrinsic <= frame.selected else None
    frame.policy = cast(dict[str, Any], frame.state.get("policy_source"))
    frame.repository = cast(str, frame.state.get("repository"))
    if not isinstance(frame.policy, dict) or not isinstance(frame.repository, str):
        return None
    return _CONTINUE_REPLAY


def _check_merge_committed_invariant_region(frame: MergeRequiredGateIdsFrame) -> Any:
    try:
        raw = subprocess.run(
            [
                "git",
                "-C",
                frame.repository,
                "show",
                f"{frame.policy.get('commit')}:forge-project.md",
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if raw.returncode != 0 or sha256_bytes(raw.stdout) != frame.policy.get("digest"):
        return None
    try:
        text = raw.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None
    begin = "<!-- FORGE:REGION invariants BEGIN -->"
    end = "<!-- FORGE:REGION invariants END -->"
    if text.count(begin) != 1 or text.count(end) != 1:
        return None
    frame.body = text.split(begin, 1)[1].split(end, 1)[0]
    frame.rows = []
    return _CONTINUE_REPLAY


def _check_merge_invariant_table_rows(frame: MergeRequiredGateIdsFrame) -> Any:
    for replay_line in frame.body.splitlines():
        line = replay_line
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = []
        current = []
        escaped = False
        for replay_character in stripped[1:-1]:
            character = replay_character
            if escaped:
                current.append("|" if character == "|" else f"\\{character}")
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == "|":
                cells.append("".join(current).strip().strip("`"))
                current = []
            else:
                current.append(character)
        if escaped:
            current.append("\\")
        cells.append("".join(current).strip().strip("`"))
        frame.rows.append(cells)
    return _CONTINUE_REPLAY


def _check_merge_required_invariant_ids(frame: MergeRequiredGateIdsFrame) -> Any:
    if (
        len(frame.rows) < 2
        or [value.lower() for value in frame.rows[0]]
        != ["invariant", "check command", "enforcement point"]
        or (not all(re.fullmatch(":?-{3,}:?", value) for value in frame.rows[1]))
    ):
        return None
    frame.selected = set(frame.intrinsic)
    for replay_row_number, replay_row in enumerate(frame.rows[2:], 1):
        row_number, row = (replay_row_number, replay_row)
        if (
            len(row) != 3
            or any(not value for value in row)
            or row[2] not in {"commit", "merge", "hook"}
            or any(character in row[1] for character in "\r\n\x00")
        ):
            return None
        if row[2] == "merge":
            frame.selected.add(f"invariant:{row_number}")
    return frozenset(frame.selected)


def _check_merge_disposition_cosign_projection(frame: MergeIntroducedDispositionValidFrame) -> Any:
    return frame.current_review.get("operator_cosign_required", False) is frame.pending


def _merge_current_gate_facts(
    step_id: str, value: Any, generation_digest: str
) -> tuple[dict[str, Any], ...] | None:
    frame = MergeCurrentGateFactsFrame(
        step_id=step_id, value=value, generation_digest=generation_digest
    )
    for check in (_check_merge_gate_fact_batch, _check_merge_gate_fact_result):
        result = check(frame)
        if result is not _CONTINUE_REPLAY:
            return result
    raise AssertionError("replay checks did not terminate")


def _merge_introduced_gate_fact(
    prior: dict[str, Any], current: dict[str, Any]
) -> tuple[str, dict[str, Any]] | None:
    frame = MergeIntroducedGateFactFrame(prior=prior, current=current)
    for check in (_check_merge_introduced_gate_delta, _check_merge_introduced_gate_result):
        result = check(frame)
        if result is not _CONTINUE_REPLAY:
            return result
    raise AssertionError("replay checks did not terminate")


def _merge_pending_disposition_cosign(state: dict[str, Any]) -> bool:
    frame = MergePendingDispositionCosignFrame(state=state)
    for check in (
        _check_merge_disposition_cosign_inputs,
        _check_merge_disposition_cosign_required,
    ):
        result = check(frame)
        if result is not _CONTINUE_REPLAY:
            return result
    raise AssertionError("replay checks did not terminate")


def _merge_required_gate_ids(
    state: dict[str, Any], context: dict[str, Any] | None
) -> frozenset[str] | None:
    frame = MergeRequiredGateIdsFrame(state=state, context=context)
    for check in (
        _check_merge_gate_requirements_inputs,
        _check_merge_committed_invariant_region,
        _check_merge_invariant_table_rows,
        _check_merge_required_invariant_ids,
    ):
        result = check(frame)
        if result is not _CONTINUE_REPLAY:
            return result
    raise AssertionError("replay checks did not terminate")


def _check_merge_introduced_disposition(frame: MergeIntroducedDispositionValidFrame) -> Any:
    prior_review = frame.prior.get("review")
    frame.current_review = cast(dict[str, Any], frame.current.get("review"))
    generation = _merge_generation(frame.current.get("candidate"))
    if (
        not isinstance(prior_review, dict)
        or not isinstance(frame.current_review, dict)
        or generation is None
    ):
        return False
    old_dispositions = prior_review.get("dispositions", [])
    dispositions = frame.current_review.get("dispositions")
    if (
        not isinstance(old_dispositions, list)
        or not isinstance(dispositions, list)
        or len(dispositions) != len(old_dispositions) + 1
        or (dispositions[:-1] != old_dispositions)
        or (not isinstance(dispositions[-1], dict))
    ):
        return False
    introduced = dispositions[-1]
    finding = introduced.get("finding")
    severity = introduced.get("severity")
    resolution = introduced.get("resolution")
    verdict = frame.current_review.get("verdict")
    findings = verdict.get("findings") if isinstance(verdict, dict) else None
    if (
        type(finding) is not int
        or finding <= 0
        or severity not in {"CRITICAL", "MAJOR", "MINOR"}
        or (not isinstance(resolution, str))
        or (not resolution.strip())
        or (introduced.get("candidate") != generation[0].get("candidate_head"))
        or (introduced.get("generation_digest") != generation[1])
        or (_utc_value(introduced.get("recorded_at")) is None)
        or (not isinstance(findings, list))
        or (finding > len(findings))
        or (not isinstance(findings[finding - 1], dict))
        or (findings[finding - 1].get("severity") != severity)
    ):
        return False
    retained = set(prior_review) | set(frame.current_review)
    retained -= {"dispositions", "operator_cosign_required"}
    if any(
        prior_review.get(name) != frame.current_review.get(name) for name in retained
    ):
        return False
    frame.pending = severity in {"CRITICAL", "MAJOR"}
    return _CONTINUE_REPLAY


def _merge_remote_churn_approval_current(state: dict[str, Any]) -> bool:
    generation = _merge_generation(state.get("candidate"))
    approval = state.get("approval")
    return bool(
        generation is not None
        and isinstance(approval, dict)
        and (approval.get("purpose") == "remote-churn")
        and (approval.get("chain_id") == state.get("chain_id"))
        and (approval.get("candidate") == generation[0].get("candidate_head"))
        and (approval.get("generation_digest") == generation[1])
    )


def _merge_finding_cosign_current(state: dict[str, Any]) -> bool:
    generation = _merge_generation(state.get("candidate"))
    review = state.get("review")
    approval = state.get("approval")
    dispositions = review.get("dispositions") if isinstance(review, dict) else None
    if (
        generation is None
        or not isinstance(approval, dict)
        or approval.get("purpose") != "finding-disposition"
        or (approval.get("chain_id") != state.get("chain_id"))
        or (approval.get("candidate") != generation[0].get("candidate_head"))
        or (approval.get("generation_digest") != generation[1])
        or (not isinstance(dispositions, list))
    ):
        return False
    return any(
        isinstance(disposition, dict)
        and disposition.get("finding") == approval.get("finding")
        and (disposition.get("resolution") == approval.get("resolution"))
        and (disposition.get("severity") in {"CRITICAL", "MAJOR"})
        for disposition in dispositions
    )


def _merge_gate4_approval_current(state: dict[str, Any]) -> bool:
    generation = _merge_generation(state.get("candidate"))
    approval = state.get("approval")
    return bool(
        generation is not None
        and isinstance(approval, dict)
        and (approval.get("purpose") == "gate-4")
        and (approval.get("chain_id") == state.get("chain_id"))
        and (approval.get("candidate") == generation[0].get("candidate_head"))
        and (approval.get("generation_digest") == generation[1])
    )


def _merge_invalidated_review_projection(state: dict[str, Any]) -> dict[str, Any] | None:
    """Retain only the completed review-cycle count across invalidation."""
    iteration = _merge_review_iteration(state)
    if iteration is None:
        return None
    return {} if iteration == 0 else {"iteration": iteration}


def _merge_review_request_current(state: dict[str, Any]) -> bool:
    generation = _merge_generation(state.get("candidate"))
    review = state.get("review")
    iteration = _merge_review_iteration(state)
    request = review.get("request") if isinstance(review, dict) else None
    return bool(
        generation is not None
        and iteration is not None
        and (1 <= iteration <= 8)
        and isinstance(request, dict)
        and (request.get("candidate") == generation[0].get("candidate_head"))
        and (request.get("reviewer") == "review-final")
        and (request.get("iteration") == iteration)
        and isinstance(request.get("package"), str)
        and bool(request["package"])
        and _merge_hex(request.get("package_digest"))
    )


def _merge_mechanical_gates_current(state: dict[str, Any], context: dict[str, Any] | None) -> bool:
    """Prove every gate ID derivable from the materialized tuple is current."""
    generation = _merge_generation(state.get("candidate"))
    tier = state.get("tier")
    steps = state.get("steps")
    if (
        generation is None
        or not isinstance(tier, dict)
        or (not isinstance(tier.get("categories"), list))
        or (not isinstance(steps, dict))
    ):
        return False
    required = _merge_required_gate_ids(state, context)
    if required is None:
        return False
    gate_ids = set(steps)
    return required == gate_ids and all(
        _merge_current_gate_facts(name, steps.get(name), generation[1]) is not None
        for name in gate_ids
    )


def _merge_introduced_disposition_valid(prior: dict[str, Any], current: dict[str, Any]) -> bool:
    frame = MergeIntroducedDispositionValidFrame(prior=prior, current=current)
    for check in (
        _check_merge_introduced_disposition,
        _check_merge_disposition_cosign_projection,
    ):
        result = check(frame)
        if result is not _CONTINUE_REPLAY:
            return result
    raise AssertionError("replay checks did not terminate")


def _merge_review_verdict_current(state: dict[str, Any], verdict_value: str | None = None) -> bool:
    generation = _merge_generation(state.get("candidate"))
    review = state.get("review")
    iteration = _merge_review_iteration(state)
    request = review.get("request") if isinstance(review, dict) else None
    verdict = review.get("verdict") if isinstance(review, dict) else None
    if (
        generation is None
        or iteration is None
        or (not 1 <= iteration <= 8)
        or (not _merge_review_request_current(state))
        or (not isinstance(request, dict))
        or (not isinstance(verdict, dict))
        or (verdict.get("verdict") not in {"PASS", "BLOCK"})
        or (verdict_value is not None and verdict.get("verdict") != verdict_value)
        or (verdict.get("candidate") != generation[0].get("candidate_head"))
        or (verdict.get("package_digest") != request.get("package_digest"))
        or (verdict.get("reviewer_role") != "review-final")
        or (verdict.get("iteration") != iteration)
    ):
        return False
    return _review_binding_for_state(state) is not None


def _merge_gate4_summary_current(state: dict[str, Any]) -> bool:
    generation = _merge_generation(state.get("candidate"))
    authorization = state.get("authorization")
    if (
        generation is None
        or not isinstance(authorization, dict)
        or set(authorization)
        != {
            "candidate_head",
            "generation_digest",
            "diff_summary",
            "control_paths",
            "review_verdict",
            "recorded_at",
        }
        or (authorization.get("candidate_head") != generation[0].get("candidate_head"))
        or (authorization.get("generation_digest") != generation[1])
        or (not isinstance(authorization.get("diff_summary"), str))
        or (not isinstance(authorization.get("control_paths"), list))
        or (not all(isinstance(path, str) and path for path in authorization["control_paths"]))
        or (authorization.get("review_verdict") != "PASS")
        or (_utc_value(authorization.get("recorded_at")) is None)
    ):
        return False
    return _merge_review_verdict_current(state, "PASS")
