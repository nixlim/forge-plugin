"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
from typing import Any, Iterable, Mapping, MutableMapping
from forge_cli.engine._archive import _archive_recheck as _archive_recheck
from forge_cli.engine._core import _transition_state as _transition_state, _archive_metadata as _archive_metadata, _record_process_step as _record_process_step
from forge_cli.engine._state import TOKEN_TTL_SECONDS as TOKEN_TTL_SECONDS
from forge_cli.envelope import OUTPUT_SCHEMA, Outcome, REVISION9_OUTPUT_SCHEMA, ReasonCode, V2ReasonCode, FrozenError, Refusal
import datetime as dt
import secrets
from forge_cli import chain_core, runtime
import errno
import os
from pathlib import Path
import json
import re
import sys


def _success(
    state: Mapping[str, Any] | None,
    message: str,
    next_step: str,
    *,
    evidence_refs: Iterable[str] = (),
) -> Outcome:
    revision9 = bool(
        isinstance(state, Mapping)
        and (
            state.get("kind") == "merge"
            or state.get("schema") == "forge-merge-chain/1"
            or state.get("run_binding") is not None
            or isinstance(state.get("staging"), Mapping)
            and state.get("staging", {}).get("archive") is not None
        )
    )
    return Outcome(
        ok=True,
        reason_code=V2ReasonCode.OK if revision9 else ReasonCode.OK,
        message=message,
        chain_id=str(state["chain_id"]) if state else None,
        state=str(state["state"]) if state else None,
        next_required_step=next_step,
        evidence_refs=tuple(item for item in evidence_refs if item),
        schema=REVISION9_OUTPUT_SCHEMA if revision9 else OUTPUT_SCHEMA,
    )


def _issue_authorization(
    state: MutableMapping[str, Any], ctx: chain_core.CommandContext | None = None
) -> None:
    if _archive_metadata(state) is not None:
        if ctx is None:
            raise FrozenError(
                "archive authorization lacks its rerender context",
                chain_id=str(state.get("chain_id") or "") or None,
                state=str(state.get("state") or "") or None,
                schema=REVISION9_OUTPUT_SCHEMA,
            )
        _archive_recheck(ctx, state, "authorization")
    issued = runtime.utc_now()
    state["authorization"] = {
        "token": secrets.token_hex(16),
        "candidate": state["candidate"]["sha256"],
        "issued_at": chain_core.iso_z(issued),
        "expires_at": chain_core.iso_z(issued + dt.timedelta(seconds=TOKEN_TTL_SECONDS)),
        "consumed": False,
        "consumed_at": None,
    }
    _transition_state(state, "authorized")


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        waited, _status = os.waitpid(pid, os.WNOHANG)
        if waited == pid:
            return False
    except ChildProcessError:
        pass
    except OSError:
        pass
    try:
        os.kill(pid, 0)
    except OSError as exc:
        return exc.errno == errno.EPERM
    proc_stat = Path(f"/proc/{pid}/stat")
    try:
        fields = proc_stat.read_text(encoding="ascii").split()
        if len(fields) > 2 and fields[2] == "Z":
            return False
    except (OSError, UnicodeError):
        pass
    return True


def _authorization_problem(state: Mapping[str, Any]) -> Refusal | None:
    authorization = state.get("authorization", {})
    if authorization.get("consumed"):
        return Refusal(
            ReasonCode.TOKEN_CONSUMED,
            "authorization token was already consumed",
            expected="consumed=false",
            observed="consumed=true",
            remediation=chain_core._forge_command(state, "status"),
            chain=state,
        )
    authorization_nonce = authorization.get("token")
    if not isinstance(authorization_nonce, str) or re.fullmatch(r"[0-9a-f]{32}", authorization_nonce) is None:
        return Refusal(
            ReasonCode.EVIDENCE_INCOMPLETE,
            "authorization record has no valid 32-hex token",
            expected="token=32 lowercase hexadecimal characters",
            observed=str(authorization_nonce),
            remediation=chain_core._forge_command(state, "verify"),
            chain=state,
        )
    issued_at = authorization.get("issued_at")
    expires_at = authorization.get("expires_at")
    if not issued_at or not expires_at:
        return Refusal(
            ReasonCode.EVIDENCE_INCOMPLETE,
            "authorization record is incomplete",
            expected="token, candidate, issued_at, expires_at, consumed=false",
            observed=json.dumps(authorization, sort_keys=True),
            remediation=chain_core._forge_command(state, "verify"),
            chain=state,
        )
    try:
        issued = chain_core.parse_time(str(issued_at))
        stored_expiry = chain_core.parse_time(str(expires_at))
    except ValueError:
        return Refusal(
            ReasonCode.EVIDENCE_INCOMPLETE,
            "authorization timestamps are malformed",
            expected="valid issued_at and expires_at timestamps",
            observed=f"issued_at={issued_at}; expires_at={expires_at}",
            remediation=chain_core._forge_command(state, "verify"),
            chain=state,
        )
    derived_expiry = issued + dt.timedelta(seconds=TOKEN_TTL_SECONDS)
    if stored_expiry != derived_expiry:
        return Refusal(
            ReasonCode.EVIDENCE_INCOMPLETE,
            "authorization TTL is not exactly 30 minutes from issuance",
            expected=chain_core.iso_z(derived_expiry),
            observed=str(expires_at),
            remediation=chain_core._forge_command(state, "verify"),
            chain=state,
        )
    if runtime.utc_now() >= derived_expiry:
        return Refusal(
            ReasonCode.TTL_EXPIRED,
            "authorization token expired 30 minutes after issuance",
            expected=f"current time before {chain_core.iso_z(derived_expiry)}",
            observed=chain_core.iso_z(),
            remediation=chain_core._forge_command(state, "commit restage --paths <path>..."),
            chain=state,
        )
    if authorization.get("candidate") != state["candidate"].get("sha256"):
        return Refusal(
            ReasonCode.CANDIDATE_STALE,
            "authorization is bound to a different candidate",
            expected=str(state["candidate"].get("sha256")),
            observed=str(authorization.get("candidate")),
            remediation=chain_core._forge_command(state, "commit restage --paths <path>..."),
            chain=state,
        )
    return None


def _verify_operator_harness(
    ctx: chain_core.CommandContext, state: MutableMapping[str, Any]
) -> dict[str, Any]:
    """Compose the committed FR-223 evaluator before accepting approval."""
    argv = [
        sys.executable,
        str(ctx.helper("fr223_eval.py")),
        "verify",
        "--root",
        str(ctx.plugin_root()),
    ]
    try:
        process = runtime.run_bounded(
            argv,
            cwd=ctx.repo.root,
            timeout=120.0,
            verbose=ctx.options.verbose,
        )
    except OSError as exc:
        raise Refusal(
            ReasonCode.APPROVAL_REQUIRED,
            f"operator-channel harness qualification is unavailable: {exc}",
            expected="current FR-223 bang-bypass qualification",
            observed=str(exc),
            remediation="rerun the committed FR-223 bang-bypass protocol, then retry approval",
            chain=state,
        ) from exc
    record = _record_process_step(
        ctx,
        state,
        "approval-qualification",
        argv,
        process,
        details={"kind": "fr223-harness-qualification"},
    )
    if record["result"] != "passed":
        raise Refusal(
            ReasonCode.APPROVAL_REQUIRED,
            "operator-channel harness qualification is stale or unavailable",
            expected="fr223_eval.py verify exit 0 for current version/channel",
            observed=(
                process.output.decode("utf-8", "replace").strip()
                or f"exit {process.returncode}"
            ),
            remediation="rerun the committed FR-223 bang-bypass protocol, then retry approval",
            chain=state,
            evidence_refs=[str(record.get("transcript") or "")],
        )
    return record
