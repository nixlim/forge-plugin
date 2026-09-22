from __future__ import annotations

import copy
import os
import re
import secrets
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from forge_cli import chain_core, engine, runtime
from forge_cli.app._candidate_observation import _observe_current_merge_candidate
from forge_cli.envelope import REVISION9_OUTPUT_SCHEMA, FrozenError, Outcome, V2ReasonCode
from forge_cli.policy import Policy, sha256_bytes

if TYPE_CHECKING:
    from forge_cli.app._merge_engine import MergeEngine

def _resolve_gate(
    self: MergeEngine,
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
    self: MergeEngine,
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
        bound_repository, _run_dir = bound
        argv.extend(
            [
                "--repository",
                str(bound_repository),
                "--run-id",
                str(state["run_binding"]["run_id"]),
                "--task",
                str(state["run_binding"]["task_id"]),
            ]
        )
    environment = os.environ.copy()
    if bound is None:
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
    self: MergeEngine,
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

def gate_run(self: MergeEngine, gate_id: str) -> Outcome:
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

def verify(self: MergeEngine) -> Outcome:
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
