#!/usr/bin/env python3
"""Append one FR-157 decision event under the repository event lock."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path


EVENTS = {
    "gate_commit",
    "fast_allowed",
    "fast_denied_policy",
    "fast_denied_eligibility",
    "user_skip",
    "review_block",
    "guard_deny",
    "halt_event",
}
HEX_CANDIDATE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
HEX_POLICY = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
SAFE_TEXT = re.compile(r"/?[A-Za-z0-9][A-Za-z0-9._:/-]*\Z")
EVENT_LOCK = ".forge/tmp/events.lock"


def utc_timestamp(value: str) -> str:
    if not value.endswith("Z"):
        raise argparse.ArgumentTypeError("must be a UTC ISO-8601 timestamp ending in Z")
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a valid UTC ISO-8601 timestamp") from exc
    if parsed.utcoffset() != dt.timedelta(0):
        raise argparse.ArgumentTypeError("must be a UTC ISO-8601 timestamp")
    return value


def policy_sha(value: str) -> str:
    if value and HEX_POLICY.fullmatch(value) is None:
        raise argparse.ArgumentTypeError("must be empty or a full hexadecimal commit ID")
    return value


def safe_text(value: str) -> str:
    if not value or SAFE_TEXT.fullmatch(value) is None:
        raise argparse.ArgumentTypeError("must be a nonempty stable code without whitespace")
    return value


def optional_safe_text(value: str) -> str:
    if value and SAFE_TEXT.fullmatch(value) is None:
        raise argparse.ArgumentTypeError("must be empty or a stable code without whitespace")
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--at", type=utc_timestamp)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--event", required=True, choices=sorted(EVENTS))
    parser.add_argument("--policy-sha", required=True, type=policy_sha)
    parser.add_argument("--reason", required=True, type=optional_safe_text)
    parser.add_argument("--surface", required=True, type=safe_text)
    args = parser.parse_args()
    if args.candidate and HEX_CANDIDATE.fullmatch(args.candidate) is None:
        parser.error("argument --candidate: must be empty or a full hexadecimal SHA/hash")
    if args.event in {"gate_commit", "fast_allowed"}:
        if len(args.candidate) not in {40, 64}:
            parser.error(
                "argument --candidate: gate_commit and fast_allowed require a full commit SHA"
            )
    elif args.event in {
        "fast_denied_policy",
        "fast_denied_eligibility",
        "user_skip",
        "review_block",
    }:
        if args.candidate and len(args.candidate) != 64:
            parser.error(
                "argument --candidate: denial, skip, and review events use a diff SHA-256 or empty"
            )
    elif args.candidate and len(args.candidate) != 64:
        parser.error(
            "argument --candidate: guard_deny and halt_event use a diff SHA-256 or empty"
        )
    return args


def git_output(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    )
    return result.stdout.decode("utf-8", "strict").strip()


def main_checkout_root() -> Path:
    common = Path(git_output("rev-parse", "--path-format=absolute", "--git-common-dir"))
    return common.resolve(strict=True).parent


def audit_failure(main_root: Path | None, at: str, code: str) -> None:
    diagnostic = f"forge: decision event append skipped ({code})"
    print(diagnostic, file=sys.stderr)
    if main_root is None:
        return
    try:
        audit_path = main_root / ".forge/tmp/halt-audit.log"
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        with audit_path.open("a", encoding="utf-8", newline="") as stream:
            stream.write(f"{at} decision event append skipped (code {code})\n")
    except OSError:
        pass


def lock_failure_code(stderr: str) -> str:
    if "failed to acquire event lock after 5s" in stderr:
        return "event-append-lock-timeout"
    return "event-append-lock-acquire-failed"


def main() -> int:
    args = parse_args()
    if args.at is None:
        args.at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace(
            "+00:00", "Z"
        )
    script_dir = Path(__file__).resolve().parent
    acquire = script_dir / "acquire-commit-lock.sh"
    release = script_dir / "release-commit-lock.sh"
    main_root: Path | None = None

    try:
        main_root = main_checkout_root()
    except (OSError, subprocess.CalledProcessError, UnicodeError):
        audit_failure(None, args.at, "event-append-repository-unavailable")
        return 0

    env = os.environ.copy()
    env.setdefault("FORGE_SESSION_PID", str(os.getpid()))
    try:
        acquired = subprocess.run(
            ["bash", str(acquire), EVENT_LOCK],
            cwd=main_root,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except OSError:
        audit_failure(main_root, args.at, "event-append-lock-acquire-failed")
        return 0

    if acquired.returncode != 0:
        audit_failure(main_root, args.at, lock_failure_code(acquired.stderr))
        return 0

    record = {
        "at": args.at,
        "candidate": args.candidate,
        "event": args.event,
        "policy_sha": args.policy_sha,
        "reason": args.reason,
        "surface": args.surface,
    }
    payload = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode()
    append_failure = ""
    try:
        decisions = main_root / ".forge/tmp/decisions"
        decisions.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(
            decisions / "events.jsonl", os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600
        )
        try:
            written = os.write(descriptor, payload)
            if written != len(payload):
                append_failure = "event-append-write-failed"
        finally:
            os.close(descriptor)
    except OSError:
        append_failure = "event-append-write-failed"

    try:
        released = subprocess.run(
            ["bash", str(release), EVENT_LOCK],
            cwd=main_root,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if released.returncode != 0 and not append_failure:
            append_failure = "event-append-lock-release-failed"
    except OSError:
        if not append_failure:
            append_failure = "event-append-lock-release-failed"

    if append_failure:
        audit_failure(main_root, args.at, append_failure)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
