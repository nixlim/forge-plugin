from __future__ import annotations

import hashlib
import os
import secrets
import sys
import time
from typing import Any, Mapping, MutableMapping

from forge_cli import candidate as candidate_module
from forge_cli import chain_core, runtime
from forge_cli import fresh_evals as fresh_eval_module
from forge_cli.engine._approval import _success as _success
from forge_cli.engine._candidate_ops import (
    _adopt_out_of_band_candidate as _adopt_out_of_band_candidate,
)
from forge_cli.engine._candidate_ops import _candidate_review_diff as _candidate_review_diff
from forge_cli.engine._candidate_ops import _candidate_snapshot as _candidate_snapshot
from forge_cli.engine._candidate_ops import (
    _install_candidate_snapshot as _install_candidate_snapshot,
)
from forge_cli.engine._candidate_ops import (
    _invalidate_candidate_evidence as _invalidate_candidate_evidence,
)
from forge_cli.engine._classification import _run_classification as _run_classification
from forge_cli.engine._core import _archive_metadata as _archive_metadata
from forge_cli.engine._core import _evidence_record as _evidence_record
from forge_cli.engine._core import _record_process_step as _record_process_step
from forge_cli.engine._core import _transition_state as _transition_state
from forge_cli.engine._gate_checks import _current_test_paths as _current_test_paths
from forge_cli.engine._gate_checks import (
    _void_mismatched_gate_one_pair as _void_mismatched_gate_one_pair,
)
from forge_cli.engine._gate_checks import scan_added_secrets as scan_added_secrets
from forge_cli.envelope import FrozenError, Outcome, ReasonCode, Refusal, V2ReasonCode
from forge_cli.policy import sha256_bytes


def _pending_mutating_gate(self, state: Mapping[str, Any]) -> str | None:
    policy = self.ctx.policy or chain_core._policy_for_state(self.ctx, state)
    if policy.changelog is not None and not chain_core._gate_satisfied(state, "changelog"):
        return "changelog"
    return None

def _resolve_gate(self, state: Mapping[str, Any], gate_id: str) -> tuple[list[str], list[str], dict[str, Any]]:
    policy = self.ctx.policy or chain_core._policy_for_state(self.ctx, state)
    paths = list(state["paths"])
    if gate_id == "gate-1":
        return ["bash", "-c", policy.gate1, "forge", *paths], [], {"kind": "gate-1"}
    if gate_id.startswith("stack:"):
        category = gate_id.partition(":")[2]
        if category not in state["tier"].get("categories", []):
            raise Refusal(
                ReasonCode.STATE_PRECONDITION,
                f"stack gate is not required for untouched category: {category}",
                observed=category,
                remediation=chain_core._forge_command(state, "verify"),
                chain=state,
            )
        commands = policy.stack_commands
        return ["bash", "-c", commands[0], "forge", *paths], commands[1:], {
            "kind": "stack",
            "category": category,
        }
    if gate_id.startswith("invariant:"):
        try:
            row_number = int(gate_id.partition(":")[2])
        except ValueError:
            row_number = -1
        matched = [
            row
            for row in policy.invariants
            if row["row_number"] == row_number and row["enforcement"] == "commit"
        ]
        if not matched:
            raise Refusal(
                ReasonCode.STATE_PRECONDITION,
                f"unknown commit invariant gate: {gate_id}",
                observed=gate_id,
                remediation=chain_core._forge_command(state, "verify"),
                chain=state,
            )
        row = matched[0]
        return ["bash", "-c", str(row["command"]), "forge", *paths], [], {
            "kind": "invariant",
            "invariant": row["invariant"],
            "row_number": row_number,
        }
    if gate_id == "assertion-sensor":
        test_paths = _current_test_paths(self.ctx, state)
        return [
            sys.executable,
            str(self.ctx.helper("check-test-quality.py")),
            "--",
            *test_paths,
        ], [], {"kind": "assertion-sensor", "test_paths": test_paths}
    if gate_id == "strict-evals":
        return ["bash", str(self.ctx.helper("run-evals.sh"))], [], {
            "kind": "strict-evals",
            "environment": {"STRICT": "1"},
        }
    if gate_id == "changelog" and policy.changelog is not None:
        return [
            "bash",
            "-c",
            str(policy.changelog["command"]),
            "forge",
            *paths,
        ], [], {"kind": "changelog", "outputs": policy.changelog["outputs"]}
    raise Refusal(
        ReasonCode.STATE_PRECONDITION,
        f"unknown or unconfigured gate id: {gate_id}",
        observed=gate_id,
        remediation=chain_core._forge_command(state, "verify"),
        chain=state,
    )

def gate_run(self, gate_id: str) -> Outcome:
    state = self.select(include_terminal=False)
    self._preflight(state, f"gate run {gate_id}")
    if state["state"] != "verifying":
        self._wrong_state(state, "verifying", f"gate run {gate_id}")
    chain_core._policy_for_state(self.ctx, state)
    pending = self._pending_mutating_gate(state)
    if pending and gate_id != pending:
        raise Refusal(
            ReasonCode.MUTATING_GATE_PENDING,
            f"non-mutating gate refused while mutating gate is pending: {pending}",
            expected=pending,
            observed=gate_id,
            remediation=chain_core._forge_command(state, f"gate run {pending}"),
            chain=state,
        )
    if gate_id == "changelog" and _archive_metadata(state) is not None:
        raise Refusal(
            V2ReasonCode.BINDING_INVALID,
            "forge: archive refused — archive-only index cannot admit a mutating gate",
            expected="no staged path except the deterministic run archive",
            observed="configured changelog mutation",
            remediation=chain_core._forge_command(state, "commit abort --reason archive-policy"),
            chain=state,
        )
    if gate_id == "assertion-sensor":
        drift = self.ctx.repo.tree_index_drift(list(state.get("paths", [])))
        if drift and chain_core._user_skip(state, "index-drift") is None:
            raise Refusal(
                ReasonCode.DRIFT_TREE_INDEX,
                (
                    "working tree differs from staged candidate before assertion sensor: "
                    f"{', '.join(drift)}"
                ),
                expected="tree bytes equal staged candidate bytes",
                observed=", ".join(drift),
                remediation=chain_core._forge_command(
                    state, "commit restage --paths <path>..."
                ),
                chain=state,
            )
        if not _current_test_paths(self.ctx, state):
            # The sensor contract runs only over touched test files; with
            # none staged the step is complete without executing the tool,
            # whose empty-path invocation is a sensor failure by contract.
            output = (
                b"forge: no touched test files - assertion sensor not applicable\n"
            )
            synthetic = runtime.ProcessResult(
                argv=[
                    sys.executable,
                    str(self.ctx.helper("check-test-quality.py")),
                    "--",
                ],
                returncode=0,
                duration_seconds=0.0,
                output=output,
                output_digest=hashlib.sha256(output).hexdigest(),
            )
            record = _record_process_step(
                self.ctx,
                state,
                gate_id,
                synthetic.argv,
                synthetic,
                details={
                    "kind": "assertion-sensor",
                    "test_paths": [],
                    "not_applicable": True,
                },
            )
            return _success(
                state,
                f"gate {gate_id} passed",
                chain_core._forge_command(state, "verify"),
                evidence_refs=[record["transcript"]],
            )
    if gate_id == "secret-scan":
        return self.scan_secrets(state=state, preflight=False)
    if gate_id == chain_core.FRESH_REVIEWER_EVALS_GATE:
        return self._run_fresh_reviewer_evals(state)
    argv, remaining_cells, details = self._resolve_gate(state, gate_id)
    if gate_id.startswith("stack:"):
        details = {
            **details,
            "batch_id": secrets.token_hex(8),
            "cell_index": 1,
            "cell_count": 1 + len(remaining_cells),
        }
    environment = os.environ.copy()
    # The DM-010 session identity is coordination state, not gate
    # context: an inherited live FORGE_SESSION_PID collides with the
    # hermetic fixture owners the test suites create, so gate children
    # never see it. Lock and coordination subprocesses keep it.
    environment.pop("FORGE_SESSION_PID", None)
    if gate_id == "strict-evals":
        try:
            baseline_candidate = fresh_eval_module.candidate_binding(
                state["candidate"]
            )
            with fresh_eval_module.materialize_candidate(
                self.ctx.repo.candidate_context(), baseline_candidate
            ) as materialized:
                environment = materialized.context.environment()
                environment.pop("FORGE_SESSION_PID", None)
                environment["STRICT"] = "1"
                process = runtime.run_bounded(
                    argv,
                    cwd=materialized.path,
                    env=environment,
                    timeout=runtime.COMMAND_TIMEOUT_SECONDS,
                    verbose=self.ctx.options.verbose,
                )
                materialized.verify()
        except fresh_eval_module.FreshEvalError as exc:
            raise Refusal(
                ReasonCode.EVIDENCE_INCOMPLETE,
                "recorded-baseline integrity candidate checkout is invalid: "
                f"{exc.reason}",
                expected="an exact disposable materialization of the current v2 candidate",
                observed=exc.reason,
                remediation=chain_core._forge_command(
                    state, "commit restage --paths <path>..."
                ),
                chain=state,
            ) from exc

        try:
            baseline_observation = self.ctx.repo.candidate_observation()
        except (OSError, candidate_module.CandidateError) as exc:
            raise Refusal(
                ReasonCode.EVIDENCE_INCOMPLETE,
                "recorded-baseline integrity could not re-observe the live index",
                expected="the current v2 candidate after the baseline process",
                observed=type(exc).__name__,
                remediation=chain_core._forge_command(
                    state, "commit restage --paths <path>..."
                ),
                chain=state,
            ) from exc
        if (
            baseline_observation.authorization_id
            != baseline_candidate["authorization_id"]
            or baseline_observation.object_format
            != baseline_candidate["object_format"]
            or baseline_observation.tree_oid != baseline_candidate["tree_oid"]
        ):
            old_candidate, has_candidate_bytes = _adopt_out_of_band_candidate(
                self.ctx,
                state,
                baseline_observation.authorization_id,
                detected_by="gate run strict-evals",
            )
            raise Refusal(
                ReasonCode.CANDIDATE_STALE,
                "out-of-band index change invalidated candidate evidence and reran classification",
                expected=old_candidate,
                observed=baseline_observation.authorization_id,
                remediation=chain_core._forge_command(
                    state,
                    "verify"
                    if has_candidate_bytes
                    else "commit restage --paths <path>...",
                ),
                chain=state,
            )
    else:
        process = runtime.run_bounded(
            argv,
            cwd=self.ctx.repo.root,
            env=environment,
            timeout=runtime.COMMAND_TIMEOUT_SECONDS,
            verbose=self.ctx.options.verbose,
        )
    # A mutating writer is recorded only after its declared outputs join
    # the candidate, so its PASS binds to the bytes it produced.
    if gate_id == "changelog" and process.returncode == 0 and not process.timed_out and not process.output_limit:
        outputs = self.ctx.repo.normalize_paths([str(item) for item in details["outputs"]])
        combined_paths = list(dict.fromkeys([*state["paths"], *outputs]))
        old_candidate = state["candidate"].get("sha256")
        self.ctx.repo.git(["add", "--", *outputs])
        snapshot = _candidate_snapshot(self.ctx, state)
        if snapshot.base_commit_oid != state.get("repo_head"):
            raise Refusal(
                ReasonCode.HEAD_MOVED,
                "candidate base changed while staging mutating-gate outputs",
                expected=str(state.get("repo_head")),
                observed=str(snapshot.base_commit_oid),
                remediation=chain_core._forge_command(state, "commit rebase"),
                chain=state,
            )
        if set(snapshot.paths) != set(combined_paths):
            combined_paths = list(snapshot.paths)
        _install_candidate_snapshot(self.ctx, state, snapshot)
        _invalidate_candidate_evidence(
            state, preserve_operator_cosign=True
        )
        _transition_state(state, "classifying")
        self.ctx.store.persist(
            state,
            "mutating_gate_restaged",
            {
                "gate_id": gate_id,
                "old_candidate": old_candidate,
                "new_candidate": state["candidate"]["sha256"],
                "outputs": outputs,
            },
        )
        _run_classification(self.ctx, state)
        # Classification returns to verifying; now persist the mutating
        # gate evidence against the new candidate.
    record = _record_process_step(
        self.ctx, state, gate_id, argv, process, details=details
    )
    if gate_id == "gate-1" and record["result"] == "passed":
        _void_mismatched_gate_one_pair(self.ctx, state)
    if gate_id == "assertion-sensor":
        for line in process.output.decode("utf-8", "replace").splitlines():
            if line.startswith("forge: assertion-free test detected:"):
                self._emit_decision(state, "assertion_blocking", "assertion-free-test")
            elif line.startswith("forge: assertion waiver:"):
                self._emit_decision(state, "assertion_waived", "assertion-waiver")
            elif "advisory only" in line:
                self._emit_decision(state, "assertion_advisory", "assertion-advisory")
    if record["result"] != "passed":
        diagnostic = (
            f"forge: invariant failed (commit): {details['invariant']}"
            if details.get("kind") == "invariant" and not process.timed_out
            else (
                f"forge: invariant timed out (commit): {details['invariant']}"
                if details.get("kind") == "invariant"
                else f"gate {gate_id} did not pass"
            )
        )
        raise Refusal(
            ReasonCode.EVIDENCE_INCOMPLETE,
            diagnostic,
            expected="exit 0 within 1200 seconds and 65536 output bytes",
            observed=(
                f"exit={process.returncode}, timeout={process.timed_out}, "
                f"output_limit={process.output_limit}"
            ),
            remediation=chain_core._forge_command(state, f"gate run {gate_id}"),
            chain=state,
            evidence_refs=[record["transcript"]],
        )
    for cell_index, cell in enumerate(remaining_cells, 2):
        extra_argv = ["bash", "-c", cell, "forge", *state["paths"]]
        extra_process = runtime.run_bounded(
            extra_argv,
            cwd=self.ctx.repo.root,
            env=environment,
            timeout=runtime.COMMAND_TIMEOUT_SECONDS,
            verbose=self.ctx.options.verbose,
        )
        extra_record = _record_process_step(
            self.ctx,
            state,
            gate_id,
            extra_argv,
            extra_process,
            details={**details, "cell_index": cell_index},
        )
        if extra_record["result"] != "passed":
            raise Refusal(
                ReasonCode.EVIDENCE_INCOMPLETE,
                f"gate {gate_id} cell {cell_index} did not pass",
                expected="all committed shell cells pass",
                observed=f"exit={extra_process.returncode}",
                remediation=chain_core._forge_command(state, f"gate run {gate_id}"),
                chain=state,
                evidence_refs=[extra_record["transcript"]],
            )
    return _success(
        state,
        f"gate {gate_id} passed",
        chain_core._forge_command(state, "verify"),
        evidence_refs=[record["transcript"]],
    )

def scan_secrets(
    self,
    *,
    state: MutableMapping[str, Any] | None = None,
    preflight: bool = True,
) -> Outcome:
    if state is None:
        state = self.select(include_terminal=False)
    if preflight:
        self._preflight(state, "scan secrets")
    if state["state"] != "verifying":
        self._wrong_state(state, "verifying", "scan secrets")
    argv = ["forge-cli", "scan", "secrets", "--staged"]
    started = time.monotonic()
    diff = _candidate_review_diff(self.ctx, state)
    findings = scan_added_secrets(diff)
    duration = time.monotonic() - started
    summary_bytes = chain_core.canonical_bytes([item.as_dict() for item in findings])
    record = _evidence_record(
        self.ctx,
        state,
        argv,
        result="failed" if findings else "passed",
        exit_code=1 if findings else 0,
        duration_seconds=duration,
        output_digest=sha256_bytes(summary_bytes),
        transcript=None,
        details={"findings": [item.as_dict() for item in findings]},
    )
    runs = state["steps"].setdefault("secret-scan", [])
    if not isinstance(runs, list):
        raise FrozenError(
            "secret-scan evidence container is malformed",
            chain_id=str(state["chain_id"]),
            state=str(state["state"]),
        )
    runs.append(record)
    self.ctx.store.persist(
        state,
        "secret_scan_recorded",
        {"result": record["result"], "finding_count": len(findings)},
    )
    if findings:
        finding_details = [item.as_dict() for item in findings]
        affected_paths = sorted({item.path for item in findings if item.path})
        state["staging"]["anomalies"].append(
            {
                "at": chain_core.iso_z(),
                "kind": "secret-findings",
                "findings": finding_details,
                "values_suppressed": True,
            }
        )
        if affected_paths:
            self.ctx.repo.git(
                ["reset", "-q", "HEAD", "--", *affected_paths]
            )
            observed_candidate = self.ctx.repo.candidate_hash()
            _adopt_out_of_band_candidate(
                self.ctx,
                state,
                observed_candidate,
                detected_by="secret-scan-unstage",
            )
        observed = ", ".join(
            f"{item.rule_id}:{item.path}:{item.line}" for item in findings
        )
        raise Refusal(
            ReasonCode.EVIDENCE_INCOMPLETE,
            f"staged secret scan found {len(findings)} added-line finding(s); values suppressed",
            expected="no secret findings in staged added lines",
            observed=observed,
            remediation="remove or rotate the secrets, restage, and rerun scan secrets",
            chain=state,
        )
    return _success(
        state,
        "staged added-line secret scan passed",
        chain_core._forge_command(state, "verify"),
    )