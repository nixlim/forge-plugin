"""Prepare receipts and mechanically check the interactive FR-223(a) probe."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shlex
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


STATE_SCHEMA = "fr223-bang-bypass-state/1"
RECEIPT_SCHEMA = "fr223-bang-bypass-receipt/1"
OBSERVATION_SCHEMA = "fr223-pretool-observation/1"
DENIAL = "forge: FR-223 bang-bypass probe observed model Bash path"
NONCE = re.compile(r"^[0-9a-f]{64}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
MAX_FILE_BYTES = 1024 * 1024
STATE_KEYS = {
    "schema",
    "created_at",
    "nonce",
    "model_command",
    "bang_command",
    "model_receipt",
    "bang_receipt",
    "observation_log",
}
OBSERVATION_KEYS = {
    "schema",
    "recorded_at",
    "nonce",
    "tool_name",
    "command",
    "command_sha256",
    "decision",
    "reason",
}


class ProbeError(RuntimeError):
    """Raised for malformed or unsafe ephemeral probe state."""


def _canonical(payload: object) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProbeError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_json(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        metadata = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
            raise ProbeError(f"{path} is not a regular non-symlink file")
        if metadata.st_size > MAX_FILE_BYTES:
            raise ProbeError(f"{path} exceeds the probe size limit")
        raw = path.read_bytes()
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_object_without_duplicates
        )
    except ProbeError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProbeError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ProbeError(f"{path} must contain a JSON object")
    return value, raw


def _write_exclusive(path: Path, payload: object) -> None:
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        data = _canonical(payload)
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(descriptor)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(parent.resolve(strict=True))
    except ValueError:
        return False
    return True


def _receipt_command(state_path: Path, leg: str, nonce: str) -> str:
    return shlex.join(
        (
            sys.executable,
            str(Path(__file__).resolve()),
            "receipt",
            "--state",
            str(state_path),
            "--leg",
            leg,
            "--nonce",
            nonce,
        )
    )


def prepare(run_dir: Path) -> dict[str, object]:
    """Create nonce-bound state and return the two exact commands to exercise."""

    root = Path(run_dir).resolve(strict=True)
    if not root.is_dir():
        raise ProbeError("run directory must be a directory")
    state_path = root / "state.json"
    nonce = secrets.token_hex(32)
    state = {
        "schema": STATE_SCHEMA,
        "created_at": _utc_now(),
        "nonce": nonce,
        "model_command": _receipt_command(state_path, "model", nonce),
        "bang_command": _receipt_command(state_path, "bang", nonce),
        "model_receipt": str(root / "model-receipt.json"),
        "bang_receipt": str(root / "bang-receipt.json"),
        "observation_log": str(root / "hook-observations.jsonl"),
    }
    _write_exclusive(state_path, state)
    return {
        "state_path": str(state_path),
        "nonce": nonce,
        "model_command": state["model_command"],
        "bang_command": state["bang_command"],
    }


def _validated_state(state_path: Path) -> tuple[dict[str, Any], bytes]:
    path = Path(state_path).resolve(strict=True)
    state, raw = _read_json(path)
    if set(state) != STATE_KEYS or state.get("schema") != STATE_SCHEMA:
        raise ProbeError("probe state has invalid schema or keys")
    nonce = state.get("nonce")
    if not isinstance(nonce, str) or NONCE.fullmatch(nonce) is None:
        raise ProbeError("probe state nonce is invalid")
    if not isinstance(state.get("created_at"), str):
        raise ProbeError("probe state creation timestamp is invalid")
    parent = path.parent
    expected_paths = {
        "model_receipt": parent / "model-receipt.json",
        "bang_receipt": parent / "bang-receipt.json",
        "observation_log": parent / "hook-observations.jsonl",
    }
    for key, expected_path in expected_paths.items():
        value = state.get(key)
        if not isinstance(value, str):
            raise ProbeError(f"probe state {key} is invalid")
        candidate = Path(value).resolve(strict=False)
        if (
            not Path(value).is_absolute()
            or not _inside(candidate, parent)
            or candidate != expected_path
        ):
            raise ProbeError(f"probe state {key} escapes the run directory")
    for leg in ("model", "bang"):
        expected = _receipt_command(path, leg, nonce)
        if state.get(f"{leg}_command") != expected:
            raise ProbeError(f"probe state {leg} command changed")
    return state, raw


def record_receipt(state_path: Path, leg: str, nonce: str) -> Path:
    state, state_raw = _validated_state(state_path)
    if leg not in {"model", "bang"}:
        raise ProbeError("receipt leg must be model or bang")
    if nonce != state["nonce"]:
        raise ProbeError("receipt nonce does not match probe state")
    receipt_path = Path(state[f"{leg}_receipt"])
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "recorded_at": _utc_now(),
        "nonce": nonce,
        "leg": leg,
        "state_digest": hashlib.sha256(state_raw).hexdigest(),
    }
    _write_exclusive(receipt_path, receipt)
    return receipt_path


def _valid_receipt(
    path: Path, *, leg: str, nonce: str, state_digest: str
) -> tuple[bool, str | None, dict[str, Any] | None]:
    if not path.exists():
        return False, None, None
    try:
        payload, raw = _read_json(path)
    except ProbeError:
        return False, None, None
    expected = {
        "schema",
        "recorded_at",
        "nonce",
        "leg",
        "state_digest",
    }
    valid = (
        set(payload) == expected
        and isinstance(payload.get("recorded_at"), str)
        and payload.get("nonce") == nonce
        and payload.get("leg") == leg
        and payload.get("state_digest") == state_digest
    )
    return (
        valid,
        hashlib.sha256(raw).hexdigest() if valid else None,
        payload if valid else None,
    )


def _observations(path: Path) -> tuple[list[dict[str, Any]], bool]:
    if not path.exists():
        return [], True
    try:
        metadata = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
            return [], False
        if metadata.st_size > MAX_FILE_BYTES:
            return [], False
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return [], False
    records: list[dict[str, Any]] = []
    for line in lines:
        try:
            record = json.loads(line, object_pairs_hook=_object_without_duplicates)
        except (ProbeError, json.JSONDecodeError):
            return [], False
        if not isinstance(record, dict) or set(record) != OBSERVATION_KEYS:
            return [], False
        records.append(record)
    return records, True


def check(state_path: Path) -> dict[str, object]:
    """Derive PASS or failure solely from receipts and nonce-scoped hook records."""

    path = Path(state_path).resolve(strict=True)
    state, state_raw = _validated_state(path)
    nonce = state["nonce"]
    state_digest = hashlib.sha256(state_raw).hexdigest()
    model_path = Path(state["model_receipt"])
    bang_path = Path(state["bang_receipt"])
    model_valid, model_digest, model_receipt = _valid_receipt(
        model_path, leg="model", nonce=nonce, state_digest=state_digest
    )
    bang_valid, bang_digest, bang_receipt = _valid_receipt(
        bang_path, leg="bang", nonce=nonce, state_digest=state_digest
    )
    observations, observations_valid = _observations(Path(state["observation_log"]))
    structurally_valid = [
        record
        for record in observations
        if record.get("schema") == OBSERVATION_SCHEMA
        and record.get("nonce") == nonce
        and record.get("tool_name") == "Bash"
        and isinstance(record.get("command"), str)
        and record.get("command_sha256")
        == hashlib.sha256(record["command"].encode("utf-8")).hexdigest()
        and record.get("decision") == "deny"
        and record.get("reason") == DENIAL
    ]
    model_hits = [
        record for record in structurally_valid if record["command"] == state["model_command"]
    ]
    bang_hits = [
        record for record in structurally_valid if record["command"] == state["bang_command"]
    ]
    checks = {
        "model_receipt_absent": not model_path.exists() and not model_valid,
        "bang_receipt_valid": bang_valid,
        "observation_log_valid": observations_valid
        and len(structurally_valid) == len(observations),
        "model_hook_observed_once": len(model_hits) == 1,
        "bang_hook_not_observed": len(bang_hits) == 0,
        "exactly_one_nonce_hook_event": len(observations) == 1,
    }
    return {
        "nonce": nonce,
        "state_digest": state_digest,
        "state": state,
        "model_command": state["model_command"],
        "bang_command": state["bang_command"],
        "receipts": {"model": model_receipt, "bang": bang_receipt},
        "receipt_digests": {"model": model_digest, "bang": bang_digest},
        "observations": observations,
        "checks": checks,
        "ok": all(checks.values()),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="probe.py")
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--run-dir", required=True)
    receipt_parser = subparsers.add_parser("receipt")
    receipt_parser.add_argument("--state", required=True)
    receipt_parser.add_argument("--leg", choices=("model", "bang"), required=True)
    receipt_parser.add_argument("--nonce", required=True)
    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("--state", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "prepare":
            result = prepare(Path(arguments.run_dir))
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 0
        if arguments.command == "receipt":
            path = record_receipt(Path(arguments.state), arguments.leg, arguments.nonce)
            print(path)
            return 0
        result = check(Path(arguments.state))
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["ok"] else 1
    except ProbeError as exc:
        print(f"forge: FR-223 probe failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"forge: FR-223 probe internal failure: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
