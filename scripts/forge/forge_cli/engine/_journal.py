"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
from pathlib import Path
from forge_cli import chain_core, runtime, candidate as candidate_module
from forge_cli.policy import sha256_bytes
from typing import Mapping, Any
import copy


def _read_ingest_sources(
    repository: Path,
    run_id: str,
    *,
    state_file: str,
    events_file: str,
    outcome_map: str,
) -> tuple[
    Path,
    Path,
    dict[str, bytes],
    dict[str, str],
    dict[str, str],
]:
    _batch, _builders, journal = runtime._coordination_modules()
    canonical_repository, state_root = journal._resolve_repository(
        repository, "journal ingest-chain"
    )
    run_dir = state_root / ".codex-orchestrator" / "runs" / run_id
    sources = {
        "state_file": (state_file, "ingest.state_file", "state.json"),
        "events_file": (events_file, "ingest.events_file", "events.jsonl"),
        "outcome_map": (outcome_map, "ingest.outcome_map", "outcome-map.json"),
    }
    data_by_field: dict[str, bytes] = {}
    captured: dict[str, str] = {}
    digests: dict[str, str] = {}
    for field, (source, label, name) in sources.items():
        data = chain_core._read_ingest_input(canonical_repository, source, label)
        digest = sha256_bytes(data)
        data_by_field[field] = data
        digests[field] = digest
        captured_path = run_dir / "captured" / "sha256" / digest / name
        capture_relative = captured_path.relative_to(run_dir).as_posix()
        if chain_core._parsed_run_captured_path(capture_relative, run_id) is None:
            raise journal.CoordinationRefusal(
                "forge: journal append refused — record cites path outside run or "
                f"repository: ingest.captured_package: {captured_path}"
            )
        captured[field] = capture_relative
    return canonical_repository, run_dir, data_by_field, captured, digests


def _install_ingest_sources(
    repository: Path,
    run_dir: Path,
    data_by_field: Mapping[str, bytes],
    digests: Mapping[str, str],
) -> None:
    names = {
        "state_file": "state.json",
        "events_file": "events.jsonl",
        "outcome_map": "outcome-map.json",
    }
    for field, name in names.items():
        chain_core._capture_ingest_blob(
            repository,
            run_dir,
            digest=str(digests[field]),
            name=name,
            data=data_by_field[field],
        )


def _capture_ingest_inputs(
    repository: Path,
    run_id: str,
    *,
    state_file: str,
    events_file: str,
    outcome_map: str,
) -> tuple[dict[str, str], dict[str, str]]:
    """Compatibility helper used by focused capture tests."""

    canonical, run_dir, data, captured, digests = _read_ingest_sources(
        repository,
        run_id,
        state_file=state_file,
        events_file=events_file,
        outcome_map=outcome_map,
    )
    _install_ingest_sources(canonical, run_dir, data, digests)
    return captured, digests


def _binding_for_commit_event(
    state: Mapping[str, Any], source_event_digest: str, review: object
) -> dict[str, Any]:
    candidate_state = state["candidate"]
    if chain_core.candidate_is_v2(state):
        candidate_binding: dict[str, Any] = {
            "kind": "git-tree-candidate-v2",
            "value": {
                "authorization_id": candidate_state["authorization_id"],
                "object_format": candidate_state["object_format"],
                "tree_oid": candidate_state["tree_oid"],
            },
        }
    else:
        candidate_binding = {
            "kind": "staged-diff-sha256",
            "value": candidate_state["sha256"],
        }
    preimage = {
        "schema": "forge-gate-binding/1",
        "source_record": {
            "chain_id": state["chain_id"],
            "event_digest": source_event_digest,
        },
        "candidate": candidate_binding,
        "review": copy.deepcopy(review),
    }
    return {**preimage, "binding_id": sha256_bytes(chain_core.canonical_bytes(preimage))}


def _passed_stack_cell_is_intermediate(fact: Mapping[str, Any]) -> bool:
    """Identify a passed cell that a live bound batch must defer."""

    batch_id = fact.get("batch_id")
    cell_index = fact.get("cell_index")
    cell_count = fact.get("cell_count")
    return bool(
        isinstance(batch_id, str)
        and batch_id
        and type(cell_index) is int
        and type(cell_count) is int
        and 0 < cell_index < cell_count
    )


def _build_chain_journal_records(
    repository: Path,
    state: Mapping[str, Any],
    event: str,
    details: Mapping[str, Any],
    source_event_digest: str,
    *,
    retrospective_ingest: bool = False,
) -> tuple[dict[str, Any], ...]:
    """Build the exact ordinary records carried by one consequential event."""

    binding = state.get("run_binding")
    if not isinstance(binding, Mapping):
        return ()
    run_id = str(binding["run_id"])
    task_id = str(binding["task_id"])
    batch, builders, journal = runtime._coordination_modules()
    _canonical_repository, state_root = journal._resolve_repository(
        repository, "journal batch"
    )
    run_dir = state_root / ".codex-orchestrator" / "runs" / run_id
    run_state = journal._scan_run(run_dir)
    task_records = [
        record
        for record in run_state.records
        if record.get("type") == "task" and record.get("id") == task_id
    ]
    if not task_records or task_records[-1].get("status") != "active":
        raise journal.CoordinationRefusal(journal.INVALID_JOURNAL_RECORD)

    activation_preamble: tuple[dict[str, Any], ...] | None = None

    def projected_run_records() -> list[dict[str, Any]]:
        nonlocal activation_preamble
        if activation_preamble is None:
            activation_preamble = (
                ()
                if journal._writer_contract_active(run_state.records)
                or retrospective_ingest
                else batch.prepare_outbox_records(
                    _canonical_repository, run_state, ()
                )
            )
        return [*run_state.records, *activation_preamble]

    record: dict[str, Any] | None = None
    binding_review: dict[str, Any] | None = None
    if event == "step_recorded":
        step_id = details.get("step_id")
        run_number = details.get("run")
        steps = state.get("steps")
        runs = steps.get(step_id) if isinstance(steps, Mapping) else None
        if (
            not isinstance(step_id, str)
            or step_id
            in {"classification", "fast-eligibility", "fast-finalize-eligibility"}
            or not isinstance(runs, list)
            or type(run_number) is not int
            or run_number <= 0
            or run_number > len(runs)
            or not isinstance(runs[run_number - 1], Mapping)
        ):
            return ()
        # Retrospective ingest may select a failed Gate-1 run and its passing
        # recheck, or several rows in one stack batch.  Bind the exact fact
        # first made durable by this event, never the current list tail.
        fact = runs[run_number - 1]
        result = fact.get("result")
        if result not in {"passed", "failed"} or details.get("result") != result:
            return ()
        if (
            not retrospective_ingest
            and result == "passed"
            and step_id.startswith("stack:")
            and _passed_stack_cell_is_intermediate(fact)
        ):
            return ()
        criterion = (
            f"gate-1: {step_id}"
            if step_id == "gate-1"
            else (
                "gate-2: Recorded-baseline integrity (strict-evals)"
                if step_id == "strict-evals"
                else (
                    "gate-2: fresh reviewer evaluation"
                    if step_id == chain_core.FRESH_REVIEWER_EVALS_GATE
                    else f"gate-2: {step_id}"
                )
            )
        )
        transcript = fact.get("transcript")
        manifest = fact.get("manifest")
        argv = fact.get("command_argv")
        record = {
            "type": "verification",
            "id": builders._allocate_id(projected_run_records(), "verification"),
            "task": task_id,
            "criterion": criterion,
            "method": (
                "Forge CLI commit chain — Recorded-baseline integrity"
                if step_id == "strict-evals"
                else (
                    "Forge CLI commit chain — Candidate-bound fresh reviewer evaluation"
                    if step_id == chain_core.FRESH_REVIEWER_EVALS_GATE
                    else "Forge CLI commit chain"
                )
            ),
            "check": (
                " ".join(str(value) for value in argv)
                if isinstance(argv, list) and argv
                else step_id
            ),
            "result": result,
            "observation": (
                f"Forge CLI recorded Recorded-baseline integrity result {result} "
                "under replay-compatible step id strict-evals"
                if step_id == "strict-evals"
                else f"Forge CLI recorded {step_id} result {result}"
            ),
            "evidence": [
                item
                for item in (transcript, manifest)
                if isinstance(item, str) and item
            ],
        }
    elif event == "secret_scan_recorded":
        steps = state.get("steps")
        runs = steps.get("secret-scan") if isinstance(steps, Mapping) else None
        result = details.get("result")
        finding_count = details.get("finding_count")
        fact = runs[-1] if isinstance(runs, list) and runs else None
        if (
            set(details) != {"result", "finding_count"}
            or not builders._commit_secret_scan_fact_valid(
                fact,
                state,
                result=result,
                finding_count=finding_count,
            )
        ):
            return ()
        assert isinstance(fact, Mapping)
        argv = fact["command_argv"]
        record = {
            "type": "verification",
            "id": builders._allocate_id(projected_run_records(), "verification"),
            "task": task_id,
            "criterion": "gate-2: secret-scan",
            "method": "Forge CLI commit chain",
            "check": " ".join(str(value) for value in argv),
            "result": result,
            "observation": f"Forge CLI recorded secret-scan result {result}",
            "evidence": [],
        }
    elif event in {"review_passed", "review_blocked"}:
        candidate_state = state.get("candidate")
        review_state = state.get("review")
        verdict = (
            review_state.get("verdict")
            if isinstance(review_state, Mapping)
            else None
        )
        request = (
            review_state.get("request")
            if isinstance(review_state, Mapping)
            else None
        )
        reviewer_role = (
            request.get("reviewer") if isinstance(request, Mapping) else None
        )
        review_check = "validated review-final verdict transport"
        if chain_core.candidate_is_v2(state):
            if (
                not isinstance(candidate_state, Mapping)
                or not isinstance(candidate_state.get("authorization_id"), str)
                or chain_core.SHA256_RE.fullmatch(
                    str(candidate_state["authorization_id"])
                )
                is None
                or not isinstance(candidate_state.get("review_diff_sha256"), str)
                or chain_core.SHA256_RE.fullmatch(
                    str(candidate_state["review_diff_sha256"])
                )
                is None
                or not isinstance(candidate_state.get("object_format"), str)
                or not isinstance(candidate_state.get("tree_oid"), str)
            ):
                return ()
            try:
                derived_authorization = candidate_module.authorization_id(
                    str(candidate_state["object_format"]),
                    str(candidate_state["tree_oid"]),
                )
            except candidate_module.CandidateError:
                return ()
            if derived_authorization != candidate_state["authorization_id"]:
                return ()
            review_check = (
                "forge-commit-candidate/2 "
                f"authorization_id={candidate_state['authorization_id']} "
                f"review_diff_sha256={candidate_state['review_diff_sha256']}"
            )
        # Gate 3 is normatively review-final; a legacy review-cheap fact is not
        # silently relabelled as that stronger authority.
        if (
            not isinstance(verdict, Mapping)
            or reviewer_role != "review-final"
            or verdict.get("verdict") not in {"PASS", "BLOCK"}
            or not isinstance(review_state.get("iteration"), int)
            or int(review_state["iteration"]) <= 0
            or not isinstance(verdict.get("package_digest"), str)
        ):
            return ()
        binding_review = {
            "verdict": verdict["verdict"],
            "iteration": review_state["iteration"],
            "reviewer_role": reviewer_role,
            "package_digest": verdict["package_digest"],
        }
        verdict_path = verdict.get("verdict_path")
        record = {
            "type": "verification",
            "id": builders._allocate_id(projected_run_records(), "verification"),
            "task": task_id,
            "criterion": journal.GATE_3_CRITERION,
            "method": "independent review-final",
            "check": review_check,
            "result": "passed" if verdict["verdict"] == "PASS" else "failed",
            "observation": (
                f"Forge CLI recorded review-final verdict {verdict['verdict']}"
            ),
            "evidence": [verdict_path] if isinstance(verdict_path, str) else [],
        }
    elif event == "commit_identity_checked":
        identity = state.get("commit_result", {}).get("identity")
        result = details.get("result")
        if (
            not isinstance(identity, Mapping)
            or identity.get("result") != result
            or result not in {"passed", "failed"}
            or details.get("produced_sha") != identity.get("produced_sha")
        ):
            return ()
        transcript = identity.get("transcript")
        record = {
            "type": "verification",
            "id": builders._allocate_id(projected_run_records(), "verification"),
            "task": task_id,
            "criterion": "gate-2: produced commit identity",
            "method": "Forge CLI bounded raw commit-object verification",
            "check": "single parent, exact tree, exact message digest, and HEAD movement",
            "result": result,
            "observation": f"Forge CLI produced commit identity check {result}",
            "evidence": [transcript] if isinstance(transcript, str) and transcript else [],
        }
    elif event in {
        "operator_approved",
        "operator_skip",
        "commit_produced",
        "commit_close_recovered",
        "chain_aborted",
        "abort_disposition_recorded",
    }:
        if event in {"chain_aborted", "abort_disposition_recorded"}:
            # Revision 13: an explicit abort of a never-landed chain carries a
            # journal-visible abort decision bound to the abandoned candidate.
            # `commit abort` refuses terminal chains before mutation, so the
            # checks below are defensive: a chain without a staged candidate
            # has nothing to bind, and a landed commit is never rewritten.
            candidate_state = state.get("candidate")
            result = state.get("commit_result")
            if (
                not isinstance(candidate_state, Mapping)
                or not isinstance(candidate_state.get("sha256"), str)
                or not isinstance(result, Mapping)
                or result.get("commit_sha") is not None
            ):
                return ()
        if event in {"commit_produced", "commit_close_recovered"}:
            identity = state.get("commit_result", {}).get("identity")
            if (
                not isinstance(identity, Mapping)
                or identity.get("result") != "passed"
                or identity.get("produced_sha") != details.get("commit_sha")
            ):
                return ()
        outcome = {
            "operator_approved": "chain-approval",
            "operator_skip": "chain-skip",
            "commit_produced": "chain-landing",
            "commit_close_recovered": "chain-landing",
            "chain_aborted": "chain-abort",
            "abort_disposition_recorded": "chain-abort",
        }[event]
        resolution = {
            "operator_approved": "Forge commit chain approval recorded",
            "operator_skip": (
                "Forge commit chain skip recorded: "
                f"{details.get('gate_id', 'unknown')}; operator reason: "
                f"{details.get('reason', 'unknown')}"
            ),
            "commit_produced": (
                "Forge commit chain landing recorded: "
                f"{details.get('commit_sha', 'unknown')}"
            ),
            "commit_close_recovered": (
                "Forge commit chain landing recovered: "
                f"{details.get('commit_sha', 'unknown')}"
            ),
            "chain_aborted": (
                "Forge commit chain abort recorded: "
                f"{details.get('reason') or 'no reason given'}"
            ),
            "abort_disposition_recorded": (
                "Forge commit chain abort disposition recorded retrospectively: "
                f"{details.get('reason') or 'no reason given'}"
            ),
        }[event]
        record = {
            "type": "decision",
            "id": builders._allocate_id(projected_run_records(), "decision"),
            "task": task_id,
            "resolution": resolution,
            "outcome": outcome,
            "basis": [],
        }
    if record is None:
        return ()
    if activation_preamble is None:
        projected_run_records()
    assert activation_preamble is not None
    record = builders._with_derived(record, run_id)
    record["binding"] = _binding_for_commit_event(
        state, source_event_digest, binding_review
    )
    return (*activation_preamble, record)


# cli split phase 2b: chain_core reaches the journal-record builder through this
# late-bound runtime seam; tests patch it on forge_cli.runtime.
runtime._build_chain_journal_records = _build_chain_journal_records
