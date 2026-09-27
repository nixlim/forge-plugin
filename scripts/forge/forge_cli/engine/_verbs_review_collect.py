from __future__ import annotations

import datetime as dt
import json
import os
import re
import stat
from pathlib import Path
from typing import Any, Mapping, MutableMapping

from forge_cli import chain_core, runtime
from forge_cli.engine import _review_attempt, _review_lane_api, _review_launch
from forge_cli.engine._approval import _issue_authorization as _issue_authorization
from forge_cli.engine._approval import _pid_is_running as _pid_is_running
from forge_cli.engine._approval import _success as _success
from forge_cli.engine._core import _read_bound_artifact as _read_bound_artifact
from forge_cli.engine._core import _transition_state as _transition_state
from forge_cli.engine._core import _write_artifact as _write_artifact
from forge_cli.envelope import Outcome, ReasonCode, Refusal
from forge_cli.policy import sha256_bytes

NEWER_REQUEST_LITERAL = (
    "forge: review request shape newer than this plugin — finish or abort the chain "
    "on the requesting version"
)
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
        match = re.fullmatch(r"finding: (CRITICAL|MAJOR|MINOR) (.+)", line)
        if not match:
            raise ValueError(
                "finding line has invalid grammar"
                if line.startswith("finding: ")
                else f"unexpected verdict line: {line}"
            )
        findings.append({"severity": match.group(1), "text": match.group(2)})
    verdict_value = lines[0].partition(": ")[2]
    if verdict_value == "PASS" and any(
        finding["severity"] in {"CRITICAL", "MAJOR"} for finding in findings
    ):
        raise ValueError("PASS verdict cannot contain CRITICAL or MAJOR findings")
    return {"verdict": verdict_value, "candidate": candidate,
            "package_digest": package, "findings": findings}


def _apply_verdict(
    self, state: MutableMapping[str, Any], verdict: MutableMapping[str, Any],
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
                "at": chain_core.iso_z(), "reason": "review iteration cap reached",
                "findings": verdict["findings"]}
        self.ctx.store.persist(state, "review_blocked", {
            "iteration": iteration, "finding_count": len(verdict["findings"])})
        for finding in verdict.get("findings", []):
            self._emit_decision(
                state, reviewer_event,
                f"finding-{str(finding.get('severity', '')).lower()}")
        self._emit_decision(state, "review_block", "review-block")
        if iteration >= 8:
            raise Refusal(
                ReasonCode.ITERATION_CAP,
                "review BLOCK reached iteration cap 8; residual risk recorded",
                expected="PASS before iteration 8",
                observed="BLOCK at iteration 8",
                remediation=chain_core._forge_command(
                    state, "commit abort --reason iteration-cap"
                ),
                chain=state,
                evidence_refs=[verdict_ref],
            )
        return _success(state, f"review BLOCK recorded at iteration {iteration}",
                        self.next_step(state), evidence_refs=[verdict_ref])
    state["review"]["iteration"] = max(iteration, 1)
    if state["tier"].get("control") or state["review"].get("operator_cosign_required"):
        _transition_state(state, "awaiting_approval")
        required = "control" if state["tier"].get("control") else "finding-disposition"
        state["approval"] = {"required_for": required, "candidate": state["candidate"]["sha256"]}
    else:
        _issue_authorization(state, self.ctx)
    self.ctx.store.persist(state, "review_passed", {
        "candidate": state["candidate"]["sha256"],
        "awaiting_approval": state["state"] == "awaiting_approval"})
    for finding in verdict.get("findings", []):
        self._emit_decision(
            state, reviewer_event,
            f"finding-{str(finding.get('severity', '')).lower()}")
    return _success(
        state, "review PASS recorded", self.next_step(state), evidence_refs=[verdict_ref]
    )


def _attempt_relative(request: Mapping[str, Any]) -> str:
    return f"review/iteration-{int(request['iteration']):02d}/{request['attempt']}"


def _attempt_fd(self, state: Mapping[str, Any], request: Mapping[str, Any]):
    return self.ctx.store.artifact_parent_descriptor(
        str(state["chain_id"]), f"{_attempt_relative(request)}/completion.json",
        create=False)


def _persist_cleared(
    self, state: MutableMapping[str, Any], request: Mapping[str, Any], outcome: str
) -> None:
    cleared = dict(request)
    cleared["cleared"] = {"outcome": outcome, "at": chain_core.iso_z()}
    state["review"]["request"] = cleared
    details = {
        "candidate": request["candidate"], "package_digest": request["package_digest"],
        "reviewer": request["reviewer"], "iteration": request["iteration"]}
    self.ctx.store.persist(state, "review_requested", details)


def _collect_refusal(
    state: Mapping[str, Any], request: Mapping[str, Any], message: str, observed: str,
    stale: tuple[str, ...] = (),
    remediation: str = "review collect",
) -> Refusal:
    return Refusal(
        ReasonCode.STATE_PRECONDITION,
        message,
        expected="the current attempt to publish an atomic completion record",
        observed=observed,
        remediation=chain_core._forge_command(state, remediation),
        chain=state,
        evidence_refs=[str(request.get("events_path") or ""), *stale],
    )


def _observe_attempt(self, state, request, attempt_fd, deadline):
    try:
        return _review_attempt.observe_attempt(
            attempt_fd, str(request["attempt"]), deadline, runtime.utc_now()
        )
    except _review_attempt.AttemptRecordError as exc:
        newer = isinstance(exc, _review_attempt.AttemptShapeNewer)
        raise Refusal(
            ReasonCode.STATE_PRECONDITION if newer else ReasonCode.EVIDENCE_INCOMPLETE,
            NEWER_REQUEST_LITERAL if newer else "review attempt record is invalid",
            observed=str(exc), remediation=chain_core._forge_command(
                state, "commit abort"
            ), chain=state, evidence_refs=[str(request.get("completion_path") or "")],
        ) from exc


def _legacy_collect(self, state: MutableMapping[str, Any], request: Mapping[str, Any]) -> Outcome:
    _read_bound_artifact(
        self.ctx, state, str(request["package"]), str(request["package_digest"]),
        "review package",
    )
    _read_bound_artifact(
        self.ctx, state, str(request["prompt_path"]), str(request["prompt_digest"]),
        "review prompt",
    )
    pid = int(request.get("pid", 0))
    if _pid_is_running(pid):
        raise _collect_refusal(
            state, request, "review-cheap process has not completed", "process still running"
        )
    completion_ref = str(request.get("completion_path") or "")
    raw = _read_bound_artifact(
        self.ctx, state, completion_ref, None, "review completion",
        max_bytes=runtime.OUTPUT_CAP_BYTES,
    )
    try:
        completion = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise Refusal(
            ReasonCode.EVIDENCE_INCOMPLETE,
            f"review-cheap completion record is malformed: {exc}",
            observed=str(exc), remediation=chain_core._forge_command(state, "review request"),
            chain=state, evidence_refs=[completion_ref],
        ) from exc
    keys = {
        "argv_digest", "completed_at", "error", "prompt_digest", "returncode",
        "reviewer_pid", "schema", "started_at", "verdict_digest", "verdict_size",
        "wrapper_pid",
    }
    valid = (
        isinstance(completion, dict) and set(completion) == keys
        and completion.get("schema") == "forge-review-process/1"
        and completion.get("wrapper_pid") == pid
        and completion.get("argv_digest") == request.get("argv_digest")
        and completion.get("prompt_digest") == request.get("prompt_digest")
        and isinstance(completion.get("returncode"), int)
        and isinstance(completion.get("verdict_digest"), str)
        and chain_core.SHA256_RE.fullmatch(str(completion.get("verdict_digest")))
        and type(completion.get("verdict_size")) is int
    )
    if not valid:
        raise Refusal(
            ReasonCode.EVIDENCE_INCOMPLETE,
            "review-cheap completion record does not bind to the launched reviewer",
            observed=sha256_bytes(raw),
            remediation=chain_core._forge_command(state, "review request"),
            chain=state, evidence_refs=[completion_ref],
        )
    if completion["returncode"] != 0 or completion.get("error") is not None:
        raise Refusal(
            ReasonCode.EVIDENCE_INCOMPLETE, "review-cheap process completed unsuccessfully",
            expected="reviewer exit 0",
            observed=f"exit {completion['returncode']}; error={completion.get('error')}",
            remediation=chain_core._forge_command(state, "review request"), chain=state,
            evidence_refs=[completion_ref, str(request.get("events_path") or "")],
        )
    verdict_ref = str(request["verdict_path"])
    data = _read_bound_artifact(
        self.ctx, state, verdict_ref, str(completion["verdict_digest"]), "review verdict",
        max_bytes=runtime.OUTPUT_CAP_BYTES,
    )
    if len(data) != completion["verdict_size"] or not data:
        raise Refusal(
            ReasonCode.REVIEW_VERDICT_INVALID,
            "review-cheap exited successfully without a valid nonempty verdict",
            remediation=chain_core._forge_command(state, "review request"), chain=state,
            evidence_refs=[completion_ref, verdict_ref],
        )
    try:
        verdict = self._parse_verdict(
            data, str(state["candidate"]["sha256"]), str(request["package_digest"])
        )
    except ValueError as exc:
        raise Refusal(
            ReasonCode.REVIEW_VERDICT_INVALID, f"review-cheap verdict is invalid: {exc}",
            expected="VERDICT line plus exact candidate and package citations", observed=str(exc),
            remediation=chain_core._forge_command(state, "review request"), chain=state,
            evidence_refs=[verdict_ref],
        ) from exc
    return self._apply_verdict(state, verdict, verdict_ref)


def _synthetic_block(
    self, state: MutableMapping[str, Any], request: Mapping[str, Any], error: str
) -> Outcome:
    completion_ref = str(request["completion_path"])
    text = f"no reviewer verdict — {error}; completion {completion_ref}"
    verdict = {
        "verdict": "BLOCK", "candidate": str(state["candidate"]["sha256"]),
        "package_digest": str(request["package_digest"]),
        "findings": [{"severity": "MAJOR", "text": text}],
    }
    relative = f"{_attempt_relative(request)}/synthetic-verdict.txt"
    content = (
        "VERDICT: BLOCK\n" f"candidate: {verdict['candidate']}\n"
        f"package: {verdict['package_digest']}\n" f"finding: MAJOR {text}\n"
    ).encode()
    try:
        verdict_ref = _write_artifact(self.ctx, state, relative, content, exclusive=True)
    except FileExistsError:
        verdict_ref = (Path(".forge") / "chains" / str(state["chain_id"]) / relative).as_posix()
        _read_bound_artifact(
            self.ctx, state, verdict_ref, sha256_bytes(content), "synthetic review verdict"
        )
    return self._apply_verdict(state, verdict, verdict_ref)


def _finish_terminal(
    self, state: MutableMapping[str, Any], request: Mapping[str, Any], outcome: str,
    stale: tuple[str, ...],
) -> Outcome:
    _persist_cleared(self, state, request, outcome)
    if outcome == "not-logged-in":
        literal = (
            _review_launch.CODEX_NOT_LOGGED_IN
            if request.get("provider") == "codex"
            else _review_launch.CLAUDE_NOT_LOGGED_IN
        )
        refusal = Refusal(
            ReasonCode.EVIDENCE_INCOMPLETE, literal, observed=outcome,
            remediation=literal.rsplit("; ", 1)[-1], chain=state,
            evidence_refs=[str(request.get("completion_path") or "")],
        )
        raise _review_attempt.with_stale_evidence(refusal, stale)
    result = _success(
        state, f"review attempt {outcome}; retry is admitted", self.next_step(state),
        evidence_refs=[str(request.get("completion_path") or "")],
    )
    return _review_attempt.with_stale_evidence(result, stale)


def _new_lane_collect(
    self, state: MutableMapping[str, Any], request: Mapping[str, Any]
) -> Outcome:
    _read_bound_artifact(
        self.ctx, state, str(request["package"]), str(request["package_digest"]),
        "review package",
    )
    _read_bound_artifact(
        self.ctx, state, str(request["prompt_path"]), str(request["prompt_digest"]),
        "review prompt",
    )
    stale = _review_attempt.mark_stale_attempts(
        self.ctx.store, str(state["chain_id"]), _attempt_relative(request)
    )
    deadline = chain_core.parse_time(str(request["requested_at"])) + dt.timedelta(
        seconds=_review_launch.IDENTITY_DEADLINE_SECONDS
    )
    with _attempt_fd(self, state, request) as (attempt_fd, _name):
        observed = _observe_attempt(self, state, request, attempt_fd, deadline)
        if observed.outcome in {"abandonable", "abandoned-claimed"}:
            won, _completion = _review_attempt.claim_abandoned(attempt_fd, request)
            if won:
                return _finish_terminal(self, state, request, "abandoned", stale)
            observed = _observe_attempt(self, state, request, attempt_fd, deadline)
        if observed.outcome == "wrapper-lost":
            record = _review_attempt.make_terminal_completion(
                request, "wrapper-lost", identity=observed.identity
            )
            if _review_attempt.publish_terminal_completion(attempt_fd, record):
                return _finish_terminal(self, state, request, "wrapper-lost", stale)
            observed = _observe_attempt(self, state, request, attempt_fd, deadline)
        if observed.outcome != "completed":
            if observed.outcome in _review_lane_api.CANCEL_REQUIRED_OUTCOMES:
                raise _collect_refusal(
                    state, request,
                    f"review attempt is {observed.outcome}; use review cancel",
                    f"{observed.reason or observed.outcome}; members={list(observed.members)}",
                    stale, "review cancel",
                )
            raise _collect_refusal(
                state, request, f"review attempt is {observed.outcome}",
                observed.reason or observed.outcome, stale,
            )
        completion = observed.completion
        assert completion is not None
        try:
            _review_attempt.validate_completion_binding(
                completion, request, observed.identity
            )
        except _review_attempt.AttemptRecordError as exc:
            raise Refusal(
                ReasonCode.EVIDENCE_INCOMPLETE,
                "review completion record does not bind to the current attempt",
                expected="matching route, attempt, digests, and recorded process identities",
                observed=str(exc), remediation=chain_core._forge_command(state, "commit abort"),
                chain=state, evidence_refs=[str(request["completion_path"])],
            ) from exc
    error = completion.get("error")
    terminal = error in {"cancelled", "abandoned", "wrapper-lost", "not-logged-in"}
    if terminal or isinstance(error, str) and error.startswith("launch-failed: "):
        return _finish_terminal(self, state, request, str(error), stale)
    if error is not None or completion.get("timed_out") or completion.get("returncode") != 0:
        fallback = "timeout" if completion.get("timed_out") else (
            f"provider exit {completion.get('returncode')}"
        )
        return _review_attempt.with_stale_evidence(
            _synthetic_block(self, state, request, str(error or fallback)), stale
        )
    verdict_ref = str(request["verdict_path"])
    try:
        data = _read_bound_artifact(
            self.ctx, state, verdict_ref, str(completion["verdict_digest"]), "review verdict",
            max_bytes=runtime.OUTPUT_CAP_BYTES,
        )
        if len(data) != completion["verdict_size"] or not data:
            raise ValueError("missing, empty or size-mismatched verdict")
        verdict = self._parse_verdict(
            data, str(state["candidate"]["sha256"]), str(request["package_digest"])
        )
    except (Refusal, ValueError) as exc:
        return _review_attempt.with_stale_evidence(
            _synthetic_block(self, state, request, f"invalid verdict: {exc}"), stale
        )
    return _review_attempt.with_stale_evidence(
        self._apply_verdict(state, verdict, verdict_ref), stale
    )


def review_collect(self) -> Outcome:
    state = self.select(include_terminal=False)
    self._preflight(state, "review collect")
    if state["state"] != "reviewing":
        self._wrong_state(state, "reviewing", "review collect")
    request = state["review"].get("request")
    if not isinstance(request, dict) or request.get("cleared"):
        raise Refusal(
            ReasonCode.STATE_PRECONDITION, "review collect requires an outstanding request",
            observed=str(request), remediation=chain_core._forge_command(state, "review request"),
            chain=state,
        )
    if request.get("lane") == "forge-review-lane/1":
        return _new_lane_collect(self, state, request)
    if request.get("lane") is not None or request.get("provider") or request.get("attempt"):
        raise Refusal(
            ReasonCode.STATE_PRECONDITION, NEWER_REQUEST_LITERAL, observed=str(request.get("lane")),
            remediation=chain_core._forge_command(state, "commit abort"), chain=state,
        )
    if request.get("reviewer") == "review-cheap" and request.get("pid"):
        return _legacy_collect(self, state, request)
    raise Refusal(
        ReasonCode.STATE_PRECONDITION,
        "legacy review-final requests complete through review attach",
        expected="a new-lane request or legacy review-cheap PID", observed=str(request),
        remediation=chain_core._forge_command(state, "review attach --verdict-file <path>"),
        chain=state,
    )


def _legacy_attach_request(state: Mapping[str, Any]) -> Mapping[str, Any]:
    request = state["review"].get("request")
    if isinstance(request, dict) and request.get("lane") not in (
        None, "forge-review-lane/1"
    ):
        raise Refusal(
            ReasonCode.STATE_PRECONDITION, NEWER_REQUEST_LITERAL,
            observed=str(request.get("lane")),
            remediation=chain_core._forge_command(state, "commit abort"), chain=state,
        )
    if isinstance(request, dict) and any(
        key in request for key in ("lane", "provider", "pid", "attempt")
    ):
        raise Refusal(
            ReasonCode.STATE_PRECONDITION,
            "review attach is retired for launched requests; use review collect",
            expected="legacy review-final invocation with no pid, provider, or attempt",
            observed=str(request), remediation=chain_core._forge_command(state, "review collect"),
            chain=state,
        )
    if (
        not isinstance(request, dict)
        or request.get("reviewer") != "review-final"
        or not request.get("invocation")
    ):
        raise Refusal(
            ReasonCode.STATE_PRECONDITION,
            "review attach requires a legacy review-final invocation",
            expected="pre-upgrade review-final request with invocation", observed=str(request),
            remediation=chain_core._forge_command(state, "review request"), chain=state,
        )
    return request


def review_attach(self, verdict_file: str) -> Outcome:
    state = self.select(include_terminal=False)
    self._preflight(state, "review attach")
    if state["state"] != "reviewing":
        self._wrong_state(state, "reviewing", "review attach")
    request = _legacy_attach_request(state)
    _read_bound_artifact(
        self.ctx, state, str(request["package"]), str(request["package_digest"]),
        "review package",
    )
    source = Path(verdict_file)
    if not source.is_absolute():
        source = Path.cwd() / source
    descriptor: int | None = None
    try:
        descriptor = os.open(
            source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0),
        )
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_uid != os.geteuid():
            raise OSError("verdict is not an owner-controlled regular file")
        parts: list[bytes] = []
        total = 0
        while total <= runtime.OUTPUT_CAP_BYTES:
            chunk = os.read(descriptor, runtime.OUTPUT_CAP_BYTES + 1 - total)
            if not chunk:
                break
            parts.append(chunk)
            total += len(chunk)
        if total > runtime.OUTPUT_CAP_BYTES:
            raise OSError(f"verdict exceeds {runtime.OUTPUT_CAP_BYTES} bytes")
        data = b"".join(parts)
    except OSError as exc:
        raise Refusal(
            ReasonCode.REVIEW_VERDICT_INVALID, f"verdict file is unreadable: {exc}",
            observed=str(source),
            remediation=chain_core._forge_command(state, "review attach --verdict-file <path>"),
            chain=state,
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    try:
        verdict = self._parse_verdict(
            data, str(state["candidate"]["sha256"]), str(request["package_digest"])
        )
    except ValueError as exc:
        raise Refusal(
            ReasonCode.REVIEW_VERDICT_INVALID, f"review-final verdict is invalid: {exc}",
            expected="VERDICT line plus exact candidate and package citations", observed=str(exc),
            remediation=chain_core._forge_command(state, "review attach --verdict-file <path>"),
            chain=state,
        ) from exc
    attempt_dir = (
        (self.ctx.store.common_root / str(request["package"])).parent.relative_to(
            self.ctx.store.artifact_dir(str(state["chain_id"]))
        )
    )
    verdict_ref = _write_artifact(
        self.ctx, state, (attempt_dir / "verdict.txt").as_posix(), data, exclusive=True
    )
    return self._apply_verdict(state, verdict, verdict_ref)
