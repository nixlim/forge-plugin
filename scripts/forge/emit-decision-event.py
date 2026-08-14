#!/usr/bin/env python3
"""Append one FR-157 decision event with one atomic POSIX append write."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import secrets
import subprocess
import sys
import time
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
    "assertion_blocking",
    "assertion_advisory",
    "assertion_waived",
    "review_cheap_finding",
    "review_final_finding",
}
HEX_CANDIDATE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
HEX_POLICY = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
SAFE_TEXT = re.compile(r"/?[A-Za-z0-9][A-Za-z0-9._:/-]*\Z")
EVENT_LOCK = ".forge/tmp/events.lock"
EVENT_WRITERS = ".forge/tmp/event-writers"
EVENT_LOCK_WAIT_SECONDS = 5.0
EVENT_LOCK_POLL_SECONDS = 0.01
EVENT_LOCK_TIMEOUT = "event-append-lock-timeout"
EVENT_LOCK_RECOVERY_FAILED = "event-append-lock-recovery-failed"
AUDIT_UNAVAILABLE_DIAGNOSTIC = "forge: decision event failure audit unavailable"


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
        "assertion_blocking",
        "assertion_advisory",
        "assertion_waived",
        "review_cheap_finding",
        "review_final_finding",
    }:
        measurement = args.event.startswith("assertion_") or (
            args.event.startswith("review_") and args.event.endswith("_finding")
        )
        if measurement and len(args.candidate) != 64:
            parser.error(
                "argument --candidate: assertion and reviewer-finding events require a diff SHA-256"
            )
        if not measurement and args.candidate and len(args.candidate) != 64:
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
    print(diagnostic, file=sys.stderr, flush=True)
    if main_root is None:
        print(AUDIT_UNAVAILABLE_DIAGNOSTIC, file=sys.stderr, flush=True)
        return
    try:
        audit_path = main_root / ".forge/tmp/halt-audit.log"
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        payload = f"{at} decision event append skipped (code {code})\n".encode()
        descriptor = os.open(
            audit_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600
        )
        try:
            # One durable audit line is the failure count. Keep it atomic too,
            # so concurrent append failures cannot hide one another.
            if os.write(descriptor, payload) != len(payload):
                raise OSError("short audit write")
        finally:
            os.close(descriptor)
    except OSError:
        # Detached decision surfaces use this non-secret status line to avoid
        # double-counting a failure this function already recorded while still
        # taking ownership when the audit append itself was unavailable.
        print(AUDIT_UNAVAILABLE_DIAGNOSTIC, file=sys.stderr, flush=True)


def register_writer(main_root: Path) -> Path:
    writer_dir = main_root / EVENT_WRITERS
    writer_dir.mkdir(parents=True, exist_ok=True)
    token = writer_dir / f"{os.getpid()}-{secrets.token_hex(16)}"
    descriptor = os.open(token, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    return token


def unregister_writer(token: Path) -> None:
    try:
        token.unlink()
    except OSError:
        # A leftover token can only defer pruning: the pruner treats it as live
        # while this process exists and conservatively reclaims it after exit.
        pass


def prune_lock_present(main_root: Path) -> bool:
    try:
        os.lstat(main_root / EVENT_LOCK)
    except FileNotFoundError:
        return False
    return True


def recover_stale_prune_lock(main_root: Path) -> int:
    """Revalidate a seen prune lock under its state mutex.

    The helper returns 0 after an absent/stale lock, 75 while a live owner or
    another state operation is present, and another status for infrastructure
    failure.  It never creates or acquires ``events.lock``.
    """

    helper = Path(__file__).resolve(strict=True).with_name("acquire-commit-lock.sh")
    try:
        result = subprocess.run(
            [str(helper), "--recover-only", EVENT_LOCK],
            cwd=main_root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return 1
    return result.returncode


def test_pause_after_registration() -> None:
    """Deterministic append/prune race seam; inert outside the test suite."""

    ready_value = os.environ.get("FORGE_TEST_EVENT_REGISTERED_READY")
    release_value = os.environ.get("FORGE_TEST_EVENT_REGISTERED_RELEASE")
    if ready_value is None and release_value is None:
        return
    if not ready_value or not release_value:
        raise OSError("incomplete event registration test seam")
    ready = Path(ready_value)
    release = Path(release_value)
    ready.parent.mkdir(parents=True, exist_ok=True)
    ready.touch()
    deadline = time.monotonic() + 15
    while not release.exists():
        if time.monotonic() >= deadline:
            raise OSError("event registration test seam timed out")
        time.sleep(0.005)


def test_barrier_after_open(token: Path) -> None:
    """Make concurrent descriptors share their initial offset for a mutant."""

    barrier_value = os.environ.get("FORGE_TEST_EVENT_OPEN_BARRIER_DIR")
    expected_value = os.environ.get("FORGE_TEST_EVENT_OPEN_BARRIER_COUNT")
    if barrier_value is None and expected_value is None:
        return
    if not barrier_value or not expected_value or not expected_value.isascii():
        raise OSError("invalid event open barrier")
    try:
        expected = int(expected_value)
    except ValueError as exc:
        raise OSError("invalid event open barrier") from exc
    if expected < 1:
        raise OSError("invalid event open barrier")
    barrier = Path(barrier_value)
    barrier.mkdir(parents=True, exist_ok=True)
    marker = barrier / token.name
    marker.touch(exist_ok=False)
    deadline = time.monotonic() + 15
    while True:
        try:
            arrived = sum(1 for item in barrier.iterdir() if item.is_file())
        except OSError as exc:
            raise OSError("event open barrier unavailable") from exc
        if arrived >= expected:
            return
        if time.monotonic() >= deadline:
            raise OSError("event open barrier timed out")
        time.sleep(0.005)


def append_payload(main_root: Path, payload: bytes) -> str:
    decisions = main_root / ".forge/tmp/decisions"
    try:
        decisions.mkdir(parents=True, exist_ok=True)
    except OSError:
        return "event-append-registration-failed"

    prune_lock_deadline: float | None = None
    while True:
        try:
            token = register_writer(main_root)
        except OSError:
            return "event-append-registration-failed"
        retry = False
        append_failure = ""
        try:
            try:
                retry = prune_lock_present(main_root)
            except OSError:
                return "event-append-registration-failed"
            if not retry:
                try:
                    test_pause_after_registration()
                    descriptor = os.open(
                        decisions / "events.jsonl",
                        os.O_WRONLY | os.O_APPEND | os.O_CREAT,
                        0o600,
                    )
                except OSError:
                    append_failure = "event-append-write-failed"
                else:
                    try:
                        try:
                            test_barrier_after_open(token)
                            written = os.write(descriptor, payload)
                            if written != len(payload):
                                append_failure = "event-append-write-failed"
                        except OSError:
                            append_failure = "event-append-write-failed"
                    finally:
                        try:
                            os.close(descriptor)
                        except OSError:
                            append_failure = "event-append-write-failed"
        finally:
            unregister_writer(token)
        if append_failure:
            return append_failure
        if retry:
            if prune_lock_deadline is None:
                prune_lock_deadline = time.monotonic() + EVENT_LOCK_WAIT_SECONDS
            if time.monotonic() >= prune_lock_deadline:
                return EVENT_LOCK_TIMEOUT
            recovery_status = recover_stale_prune_lock(main_root)
            if recovery_status == 0:
                continue
            if recovery_status != 75:
                return EVENT_LOCK_RECOVERY_FAILED
            remaining = prune_lock_deadline - time.monotonic()
            if remaining <= 0:
                return EVENT_LOCK_TIMEOUT
            time.sleep(min(EVENT_LOCK_POLL_SECONDS, remaining))
            continue
        return ""


def main() -> int:
    args = parse_args()
    if args.at is None:
        args.at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace(
            "+00:00", "Z"
        )
    main_root: Path | None = None

    try:
        main_root = main_checkout_root()
    except (OSError, subprocess.CalledProcessError, UnicodeError):
        audit_failure(None, args.at, "event-append-repository-unavailable")
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
    append_failure = append_payload(main_root, payload)
    if append_failure:
        audit_failure(main_root, args.at, append_failure)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
