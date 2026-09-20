from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path
from typing import Any, MutableMapping

from forge_cli import chain_core, runtime
from forge_cli.engine._approval import _issue_authorization as _issue_authorization
from forge_cli.engine._approval import _pid_is_running as _pid_is_running
from forge_cli.engine._approval import _success as _success
from forge_cli.engine._core import _read_bound_artifact as _read_bound_artifact
from forge_cli.engine._core import _transition_state as _transition_state
from forge_cli.engine._core import _write_artifact as _write_artifact
from forge_cli.envelope import Outcome, ReasonCode, Refusal
from forge_cli.policy import sha256_bytes


def _parse_verdict(data: bytes, candidate: str, package: str) -> dict[str, Any]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("verdict is not UTF-8") from exc
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines or lines[0] not in {"VERDICT: PASS", "VERDICT: BLOCK"}:
        raise ValueError("first non-empty line must be VERDICT: PASS or VERDICT: BLOCK")
    candidate_lines = [line for line in lines if line.startswith("candidate: ")]
    package_lines = [line for line in lines if line.startswith("package: ")]
    if candidate_lines != [f"candidate: {candidate}"]:
        raise ValueError("verdict must cite the current candidate exactly once")
    if package_lines != [f"package: {package}"]:
        raise ValueError("verdict must cite the package digest exactly once")
    findings: list[dict[str, str]] = []
    for index, line in enumerate(lines):
        if index == 0 or line in candidate_lines or line in package_lines:
            continue
        if not line.startswith("finding: "):
            raise ValueError(f"unexpected verdict line: {line}")
        match = re.fullmatch(r"finding: (CRITICAL|MAJOR|MINOR) (.+)", line)
        if not match:
            raise ValueError("finding line has invalid grammar")
        findings.append({"severity": match.group(1), "text": match.group(2)})
    verdict_value = lines[0].partition(": ")[2]
    if verdict_value == "PASS" and any(
        finding["severity"] in {"CRITICAL", "MAJOR"} for finding in findings
    ):
        raise ValueError("PASS verdict cannot contain CRITICAL or MAJOR findings")
    return {
        "verdict": verdict_value,
        "candidate": candidate,
        "package_digest": package,
        "findings": findings,
    }

def _apply_verdict(
    self,
    state: MutableMapping[str, Any],
    verdict: MutableMapping[str, Any],
    verdict_ref: str,
) -> Outcome:
    verdict["recorded_at"] = chain_core.iso_z()
    verdict["verdict_path"] = verdict_ref
    state["review"]["verdict"] = dict(verdict)
    reviewer_event = (
        "review_cheap_finding"
        if (state["review"].get("request") or {}).get("reviewer") == "review-cheap"
        else "review_final_finding"
    )
    iteration = int(state["review"].get("iteration", 0)) + 1
    if verdict["verdict"] == "BLOCK":
        state["review"]["iteration"] = iteration
        _transition_state(state, "revising")
        if iteration >= 8:
            state["review"]["residual_risk"] = {
                "at": chain_core.iso_z(),
                "reason": "review iteration cap reached",
                "findings": verdict["findings"],
            }
        self.ctx.store.persist(
            state,
            "review_blocked",
            {"iteration": iteration, "finding_count": len(verdict["findings"])},
        )
        for finding in verdict.get("findings", []):
            self._emit_decision(
                state,
                reviewer_event,
                f"finding-{str(finding.get('severity', '')).lower()}",
            )
        self._emit_decision(state, "review_block", "review-block")
        if iteration >= 8:
            raise Refusal(
                ReasonCode.ITERATION_CAP,
                "review BLOCK reached iteration cap 8; residual risk recorded",
                expected="PASS before iteration 8",
                observed="BLOCK at iteration 8",
                remediation=chain_core._forge_command(state, "commit abort --reason iteration-cap"),
                chain=state,
                evidence_refs=[verdict_ref],
            )
        return _success(
            state,
            f"review BLOCK recorded at iteration {iteration}",
            self.next_step(state),
            evidence_refs=[verdict_ref],
        )
    state["review"]["iteration"] = max(iteration, 1)
    if state["tier"].get("control") or state["review"].get("operator_cosign_required"):
        _transition_state(state, "awaiting_approval")
        state["approval"] = {
            "required_for": "control" if state["tier"].get("control") else "finding-disposition",
            "candidate": state["candidate"]["sha256"],
        }
    else:
        _issue_authorization(state, self.ctx)
    self.ctx.store.persist(
        state,
        "review_passed",
        {
            "candidate": state["candidate"]["sha256"],
            "awaiting_approval": state["state"] == "awaiting_approval",
        },
    )
    for finding in verdict.get("findings", []):
        self._emit_decision(
            state,
            reviewer_event,
            f"finding-{str(finding.get('severity', '')).lower()}",
        )
    return _success(
        state,
        "review PASS recorded",
        self.next_step(state),
        evidence_refs=[verdict_ref],
    )

def review_collect(self) -> Outcome:
    state = self.select(include_terminal=False)
    self._preflight(state, "review collect")
    if state["state"] != "reviewing":
        self._wrong_state(state, "reviewing", "review collect")
    request = state["review"].get("request")
    if not isinstance(request, dict) or request.get("reviewer") != "review-cheap":
        raise Refusal(
            ReasonCode.STATE_PRECONDITION,
            "review collect requires a CLI-launched review-cheap request",
            expected="review request with reviewer=review-cheap",
            observed=str(request),
            remediation=chain_core._forge_command(state, "review request"),
            chain=state,
        )
    _read_bound_artifact(
        self.ctx,
        state,
        str(request["package"]),
        str(request["package_digest"]),
        "review package",
    )
    _read_bound_artifact(
        self.ctx,
        state,
        str(request["prompt_path"]),
        str(request["prompt_digest"]),
        "review prompt",
    )
    verdict_ref = str(request["verdict_path"])
    completion_ref = str(request.get("completion_path") or "")
    pid = int(request.get("pid", 0))
    alive = _pid_is_running(pid)
    if alive:
        raise Refusal(
            ReasonCode.STATE_PRECONDITION,
            "review-cheap process has not completed",
            expected=f"detached wrapper PID {pid} exited with an atomic completion record",
            observed="process still running",
            remediation=chain_core._forge_command(state, "review collect"),
            chain=state,
            evidence_refs=[str(request.get("events_path", ""))],
        )
    try:
        completion_raw = _read_bound_artifact(
            self.ctx,
            state,
            completion_ref,
            None,
            "review completion",
            max_bytes=runtime.OUTPUT_CAP_BYTES,
        )
    except Refusal as exc:
        raise Refusal(
            ReasonCode.EVIDENCE_INCOMPLETE,
            f"review-cheap completion record is absent or unsafe: {exc.message}",
            expected=f"atomic owner-controlled completion record at {completion_ref}",
            observed=exc.observed,
            remediation=chain_core._forge_command(state, "review request"),
            chain=state,
            evidence_refs=[str(request.get("events_path", ""))],
        ) from exc
    try:
        completion = json.loads(completion_raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise Refusal(
            ReasonCode.EVIDENCE_INCOMPLETE,
            f"review-cheap completion record is malformed: {exc}",
            expected=f"atomic completion record at {completion_ref}",
            observed=str(exc),
            remediation=chain_core._forge_command(state, "review request"),
            chain=state,
            evidence_refs=[str(request.get("events_path", ""))],
        ) from exc
    completion_keys = {
        "argv_digest",
        "completed_at",
        "error",
        "prompt_digest",
        "returncode",
        "reviewer_pid",
        "schema",
        "started_at",
        "verdict_digest",
        "verdict_size",
        "wrapper_pid",
    }
    completion_valid = (
        isinstance(completion, dict)
        and set(completion) == completion_keys
        and completion.get("schema") == "forge-review-process/1"
        and completion.get("wrapper_pid") == pid
        and completion.get("argv_digest") == request.get("argv_digest")
        and completion.get("prompt_digest") == request.get("prompt_digest")
        and isinstance(completion.get("returncode"), int)
        and isinstance(completion.get("started_at"), str)
        and isinstance(completion.get("completed_at"), str)
        and isinstance(completion.get("verdict_digest"), str)
        and chain_core.SHA256_RE.fullmatch(str(completion.get("verdict_digest"))) is not None
        and type(completion.get("verdict_size")) is int
        and int(completion.get("verdict_size", -1)) >= 0
        and (
            completion.get("error") is None
            or isinstance(completion.get("error"), str)
        )
        and (
            completion.get("reviewer_pid") is None
            or type(completion.get("reviewer_pid")) is int
        )
    )
    if not completion_valid:
        raise Refusal(
            ReasonCode.EVIDENCE_INCOMPLETE,
            "review-cheap completion record does not bind to the launched reviewer",
            expected=f"schema, wrapper PID {pid}, and argv digest {request.get('argv_digest')}",
            observed=sha256_bytes(completion_raw),
            remediation=chain_core._forge_command(state, "review request"),
            chain=state,
            evidence_refs=[completion_ref],
        )
    if completion["returncode"] != 0 or completion.get("error") is not None:
        raise Refusal(
            ReasonCode.EVIDENCE_INCOMPLETE,
            "review-cheap process completed unsuccessfully",
            expected="reviewer exit 0",
            observed=(
                f"exit {completion['returncode']}; error={completion.get('error')}"
            ),
            remediation=chain_core._forge_command(state, "review request"),
            chain=state,
            evidence_refs=[completion_ref, str(request.get("events_path", ""))],
        )
    data = _read_bound_artifact(
        self.ctx,
        state,
        verdict_ref,
        str(completion["verdict_digest"]),
        "review verdict",
        max_bytes=runtime.OUTPUT_CAP_BYTES,
    )
    if len(data) != int(completion["verdict_size"]):
        raise Refusal(
            ReasonCode.REVIEW_VERDICT_INVALID,
            "review-cheap verdict size does not match the launcher completion record",
            expected=str(completion["verdict_size"]),
            observed=str(len(data)),
            remediation=chain_core._forge_command(state, "review request"),
            chain=state,
            evidence_refs=[completion_ref, verdict_ref],
        )
    if not data:
        raise Refusal(
            ReasonCode.REVIEW_VERDICT_INVALID,
            "review-cheap exited successfully without a nonempty verdict",
            expected=f"nonempty verdict at {verdict_ref}",
            observed="verdict absent after successful process exit",
            remediation=chain_core._forge_command(state, "review request"),
            chain=state,
            evidence_refs=[completion_ref, str(request.get("events_path", ""))],
        )
    try:
        verdict = self._parse_verdict(
            data,
            str(state["candidate"]["sha256"]),
            str(request["package_digest"]),
        )
    except ValueError as exc:
        raise Refusal(
            ReasonCode.REVIEW_VERDICT_INVALID,
            f"review-cheap verdict is invalid: {exc}",
            expected="VERDICT line plus exact candidate and package citations",
            observed=str(exc),
            remediation=chain_core._forge_command(state, "review request"),
            chain=state,
            evidence_refs=[verdict_ref],
        ) from exc
    return self._apply_verdict(state, verdict, verdict_ref)

def review_attach(self, verdict_file: str) -> Outcome:
    state = self.select(include_terminal=False)
    self._preflight(state, "review attach")
    if state["state"] != "reviewing":
        self._wrong_state(state, "reviewing", "review attach")
    request = state["review"].get("request")
    if not isinstance(request, dict) or request.get("reviewer") != "review-final":
        raise Refusal(
            ReasonCode.STATE_PRECONDITION,
            "review attach requires a review-final package request",
            expected="review request with reviewer=review-final",
            observed=str(request),
            remediation=chain_core._forge_command(state, "review request"),
            chain=state,
        )
    _read_bound_artifact(
        self.ctx,
        state,
        str(request["package"]),
        str(request["package_digest"]),
        "review package",
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
        parts: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, runtime.OUTPUT_CAP_BYTES + 1 - total)
            if not chunk:
                break
            parts.append(chunk)
            total += len(chunk)
            if total > runtime.OUTPUT_CAP_BYTES:
                raise OSError(
                    f"verdict exceeds {runtime.OUTPUT_CAP_BYTES} bytes"
                )
        data = b"".join(parts)
    except OSError as exc:
        raise Refusal(
            ReasonCode.REVIEW_VERDICT_INVALID,
            f"verdict file is unreadable: {exc}",
            observed=str(source),
            remediation=chain_core._forge_command(state, "review attach --verdict-file <path>"),
            chain=state,
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    try:
        verdict = self._parse_verdict(
            data,
            str(state["candidate"]["sha256"]),
            str(request["package_digest"]),
        )
    except ValueError as exc:
        raise Refusal(
            ReasonCode.REVIEW_VERDICT_INVALID,
            f"review-final verdict is invalid: {exc}",
            expected="VERDICT line plus exact candidate and package citations",
            observed=str(exc),
            remediation=chain_core._forge_command(state, "review attach --verdict-file <path>"),
            chain=state,
        ) from exc
    attempt_dir = (
        (self.ctx.store.common_root / str(request["package"])).parent.relative_to(
            self.ctx.store.artifact_dir(str(state["chain_id"]))
        )
    )
    verdict_ref = _write_artifact(
        self.ctx,
        state,
        (attempt_dir / "verdict.txt").as_posix(),
        data,
        exclusive=True,
    )
    return self._apply_verdict(state, verdict, verdict_ref)