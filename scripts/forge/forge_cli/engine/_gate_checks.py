"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
from pathlib import Path
from typing import Any, Mapping, MutableMapping
from forge_cli import chain_core, fresh_evals as fresh_eval_module
from forge_cli.engine._core import _evidence_record as _evidence_record
from forge_cli.engine._core import _fresh_eval_invalid_refusal as _fresh_eval_invalid_refusal
from forge_cli.engine._core import _write_artifact as _write_artifact
from forge_cli.engine._fresh_eval import _validated_fresh_reviewer_manifest as _validated_fresh_reviewer_manifest
from forge_cli.engine._state import SECRET_RULES as SECRET_RULES, PLACEHOLDER_RE as PLACEHOLDER_RE
from forge_cli.envelope import ReasonCode, Refusal
import dataclasses
import hashlib
import re


def _current_test_paths(
    ctx: chain_core.CommandContext, state: Mapping[str, Any] | None = None
) -> list[str]:
    result: list[str] = []
    paths = state.get("paths", []) if isinstance(state, Mapping) else ctx.repo.staged_paths()
    for path in paths:
        name = Path(path).name.lower()
        if (
            "tests/" in path.replace("\\", "/")
            or name.startswith("test_")
            or name.endswith("_test.py")
            or ".test." in name
            or ".spec." in name
        ):
            result.append(path)
    return result


def _record_docs_class_gate_one_skip(
    ctx: chain_core.CommandContext, state: MutableMapping[str, Any]
) -> dict[str, Any]:
    """Record the docs-class Gate-1 skip as durable step evidence.

    The record sits in the ``gate-1`` step list under the same ID as a run,
    with ``result`` ``skipped`` and the fixed reason, so replay, ingest, and
    archives see why no test process was launched.  It is admitted only after
    the classifier's per-path evidence proved every staged path docs-class.
    """

    if not chain_core._docs_class_candidate(state):
        raise Refusal(
            ReasonCode.STATE_PRECONDITION,
            "gate-1 docs-class skip refused: candidate is not docs-class",
            expected="every classified path carries only the docs category",
            observed=", ".join(str(path) for path in state.get("paths", [])),
            remediation=chain_core._forge_command(state, "gate run gate-1"),
            chain=state,
        )
    runs = state["steps"].get("gate-1")
    run_number = len(runs) + 1 if isinstance(runs, list) else 1
    output = (
        "forge: gate-1 skipped — docs-class candidate; no test process launched\n"
        + "".join(f"path: {path}\n" for path in state.get("paths", []))
    ).encode("utf-8")
    transcript = _write_artifact(
        ctx, state, f"evidence/gate-1-{run_number:02d}.log", output
    )
    record = _evidence_record(
        ctx,
        state,
        [],
        result="skipped",
        exit_code=0,
        duration_seconds=0.0,
        output_digest=hashlib.sha256(output).hexdigest(),
        transcript=transcript,
        details={
            "kind": "gate-1",
            "skipped": True,
            "reason": chain_core.DOCS_CLASS_SKIP_REASON,
            "timed_out": False,
            "output_limit": False,
        },
    )
    if not isinstance(runs, list):
        runs = []
        state["steps"]["gate-1"] = runs
    runs.append(record)
    ctx.store.persist(
        state,
        "step_recorded",
        {"step_id": "gate-1", "result": "skipped", "run": run_number},
    )
    return record


def _fresh_reviewer_pass_claimed(state: Mapping[str, Any]) -> bool:
    """Distinguish an absent fresh gate from malformed claimed-PASS evidence."""

    steps = state.get("steps")
    runs = (
        steps.get(chain_core.FRESH_REVIEWER_EVALS_GATE)
        if isinstance(steps, Mapping)
        else None
    )
    latest = runs[-1] if isinstance(runs, list) and runs else None
    candidate = state.get("candidate")
    expected = candidate.get("sha256") if isinstance(candidate, Mapping) else None
    return bool(
        isinstance(latest, Mapping)
        and latest.get("candidate") == expected
        and (
            latest.get("result") == "passed"
            or latest.get("outcome") == "PASS"
            or latest.get("exit_code") == 0
        )
    )


def _fresh_reviewer_block_claimed(state: Mapping[str, Any]) -> bool:
    """Recognize the current terminal BLOCK that an operator may waive."""

    steps = state.get("steps")
    runs = (
        steps.get(chain_core.FRESH_REVIEWER_EVALS_GATE)
        if isinstance(steps, Mapping)
        else None
    )
    latest = runs[-1] if isinstance(runs, list) and runs else None
    candidate = state.get("candidate")
    expected = candidate.get("sha256") if isinstance(candidate, Mapping) else None
    return bool(
        isinstance(latest, Mapping)
        and latest.get("candidate") == expected
        and latest.get("result") == "failed"
        and latest.get("outcome") == "BLOCK"
    )


def _mechanical_complete(ctx: chain_core.CommandContext, state: Mapping[str, Any]) -> bool:
    needed = chain_core._required_steps(ctx, state)
    for step_id in needed:
        if step_id == "gate-1":
            if not chain_core._gate_one_complete(state):
                return False
        elif step_id == chain_core.FRESH_REVIEWER_EVALS_GATE:
            if chain_core._user_skip(state, step_id) is not None:
                continue
            if not _fresh_reviewer_pass_claimed(state):
                return False
            try:
                _validated_fresh_reviewer_manifest(
                    ctx, state, reobserve_index=False
                )
            except fresh_eval_module.FreshEvalError as exc:
                raise _fresh_eval_invalid_refusal(state, str(exc)) from exc
            except Refusal as exc:
                raise _fresh_eval_invalid_refusal(
                    state, exc.message, evidence_refs=exc.evidence_refs
                ) from exc
        elif not chain_core._gate_satisfied(state, step_id):
            return False
    return True


def _next_incomplete(ctx: chain_core.CommandContext, state: Mapping[str, Any]) -> str | None:
    for step_id in chain_core._required_steps(ctx, state):
        if step_id == "gate-1":
            if not chain_core._gate_one_complete(state):
                return "gate-1"
            continue
        if step_id == chain_core.FRESH_REVIEWER_EVALS_GATE:
            if chain_core._user_skip(state, step_id) is not None:
                continue
            if not _fresh_reviewer_pass_claimed(state):
                return step_id
            try:
                _validated_fresh_reviewer_manifest(
                    ctx, state, reobserve_index=False
                )
            except fresh_eval_module.FreshEvalError as exc:
                raise _fresh_eval_invalid_refusal(state, str(exc)) from exc
            except Refusal as exc:
                raise _fresh_eval_invalid_refusal(
                    state, exc.message, evidence_refs=exc.evidence_refs
                ) from exc
            continue
        if not chain_core._gate_satisfied(state, step_id):
            return step_id
    return None


@dataclasses.dataclass(frozen=True)
class SecretFinding:
    rule_id: str
    path: str
    line: int

    def as_dict(self) -> dict[str, Any]:
        return {"line": self.line, "path": self.path, "rule_id": self.rule_id}


def scan_added_secrets(diff: bytes) -> list[SecretFinding]:
    text = diff.decode("utf-8", "replace")
    current_path = ""
    new_line = 0
    findings: list[SecretFinding] = []
    env_assignments: dict[str, list[int]] = {}
    for raw_line in text.splitlines():
        if raw_line.startswith("+++ "):
            label = raw_line[4:]
            current_path = label[2:] if label.startswith("b/") else label
            continue
        hunk = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", raw_line)
        if hunk:
            new_line = int(hunk.group(1))
            continue
        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            content = raw_line[1:]
            for rule_id, pattern in SECRET_RULES:
                match = pattern.search(content)
                if not match:
                    continue
                if rule_id == "generic-secret-assignment" and PLACEHOLDER_RE.fullmatch(
                    match.group(1)
                ):
                    continue
                findings.append(SecretFinding(rule_id, current_path, new_line))
            if re.fullmatch(r"(?:^|.*/)\.env(?:\.[^/]*)?", current_path) and re.match(
                r"^[A-Za-z_][A-Za-z0-9_]*=.+", content
            ):
                env_assignments.setdefault(current_path, []).append(new_line)
            new_line += 1
        elif raw_line.startswith("-") and not raw_line.startswith("---"):
            continue
        elif raw_line.startswith(" "):
            new_line += 1
    for path, lines in env_assignments.items():
        if len(lines) >= 5:
            findings.append(SecretFinding("env-file-bulk-add", path, lines[0]))
    unique = {(item.rule_id, item.path, item.line): item for item in findings}
    return [unique[key] for key in sorted(unique)]
