from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import selectors
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Callable, NamedTuple
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = Path(".forge/evals/tasks/fr230-phase3-4-v2.manifest.json")
MANIFEST = ROOT / MANIFEST_PATH
HEX64 = re.compile(r"^[0-9a-f]{64}$")
ROOT_KEYS = (
    "schema",
    "generation",
    "phase",
    "previous_manifest_sha256",
    "artifacts",
    "v1_artifacts",
    "subjects",
    "result_bindings",
)
ARTIFACT_PATHS = (
    ".forge/evals/tasks/fr223-hook-argv-matcher-v2.md",
    ".forge/evals/tasks/fr223-hook-argv-matcher-v2.result",
    ".forge/evals/tasks/fr223-reason-code-enum-v2.md",
    ".forge/evals/tasks/fr223-reason-code-enum-v2.result",
    "system/fr223/hook-argv-cases-v2.json",
    "system/fr223/reason-codes-v2.json",
)
V1_HASHES = {
    ".forge/evals/tasks/fr223-phase0-v1.manifest.json": (
        "7741b877b1ed45047d680a077c5303b2314cd1f3ef0339821bd7105ac9acd5c9"
    ),
    "system/fr223/hook-argv-cases-v1.json": (
        "1850257d7899a4c7199e9bcbe12ffd39b0905bb44e49d16348c10e438ea05db7"
    ),
    "system/fr223/reason-codes-v1.json": (
        "3646227d8437789e0407117dc09e00d6116edccb63e89354c746d4b9059c264b"
    ),
}
SLOTS = (
    "activated-denial",
    "cleanup",
    "merge-last-line",
    "merge-transition",
    "push",
    "push-last-line",
    "re-verification-matrix",
    "recovery",
)
GENERATION_ONE_PENDING = {
    "activated-denial",
    "push",
    "push-last-line",
}
RESULT_EVIDENCE_DIR = Path("tests/fixtures/fr230-results")
RESULT_KEYS = (
    "schema",
    "result_id",
    "slot",
    "status",
    "subject_candidate_sha256",
    "command",
    "returncode",
    "tests_run",
    "suite_tail",
)
RESULT_ID = re.compile(r"^fr230-phase-[34]-[a-z][a-z0-9-]*$")
# Measured: 10.5-11.5s unloaded, 23s at 2x and 45s at 4x oversubscription.
# The runner is 1.4-2.5x slower; 120s is about 11x unloaded and 2.7x worst.
RESULT_TEST_TIMEOUT_SECONDS = 120
RESULT_OUTPUT_LIMIT = 65536
RESULT_OUTPUT_TAIL_LIMIT = 4096
RESULT_STREAM_POLL_SECONDS = 0.05
RESULT_TERM_GRACE_SECONDS = 0.25
RESULT_KILL_GRACE_SECONDS = 1.0
MANIFEST_SIZE_LIMIT = 1024 * 1024
FILE_SIZE_LIMIT = 16 * 1024 * 1024
FILE_READ_CHUNK = 65536
HISTORY_COMMAND_TIMEOUT_SECONDS = 10
HISTORY_LIST_OUTPUT_LIMIT = 65536
PHASE3_RESULT_TESTS = {
    "cleanup": (
        "tests.test_cli_merge_integration.MergeIntegrationEpochTests."
        "test_full_epoch_push_and_nonforce_cleanup"
    ),
    "merge-last-line": (
        "tests.test_cli_merge_integration.MergeIntegrationEpochTests."
        "test_each_bounded_epoch_control_is_load_bearing"
    ),
    "merge-transition": (
        "tests.test_cli_merge_lifecycle.MergeLifecycleStartTests."
        "test_start_publishes_ownership_and_generation_before_success"
    ),
    "re-verification-matrix": (
        "tests.test_cli_merge_integration.MergeIntegrationEpochTests."
        "test_remote_only_successor_is_carried_then_pushed_in_a_new_epoch"
    ),
    "recovery": (
        "tests.test_cli_merge_integration.MergeIntegrationEpochTests."
        "test_recovery_resumes_the_single_fetch_intent"
    ),
}
PHASE3_RESULT_IDS = {
    slot: f"fr230-phase-3-{slot}" for slot in PHASE3_RESULT_TESTS
}
# These phase-4 mappings qualify the only evidence shape a future generation-2
# manifest may resolve.  They do not assert that the tests have produced PASS
# evidence in generation 1: its three corresponding slots remain mandatory
# ``pending-phase-4`` non-evidence.
PHASE4_RESULT_TESTS = {
    "activated-denial": (
        "tests.test_fr223_v2_hook.V2HookExecutionTests."
        "test_all_18_additive_cases_execute_against_their_activation_context"
    ),
    "push": (
        "tests.test_cli_merge_integration.MergeIntegrationEpochTests."
        "test_transient_known_push_failure_retries_after_fresh_old_tip"
    ),
    "push-last-line": (
        "tests.test_cli_merge_integration.MergeIntegrationEpochTests."
        "test_invalid_final_mode_control_is_load_bearing_at_push_boundary"
    ),
}
PHASE4_RESULT_IDS = {
    slot: f"fr230-phase-4-{slot}" for slot in PHASE4_RESULT_TESTS
}
RESULT_TESTS = {**PHASE3_RESULT_TESTS, **PHASE4_RESULT_TESTS}
RESULT_IDS = {**PHASE3_RESULT_IDS, **PHASE4_RESULT_IDS}
PROCESS_FAILURE_REASONS = (
    "timed_out",
    "output_exceeded",
    "stream_failed",
    "remaining_group_after_exit",
    "cleanup_not_proven",
)


class StructuredResult(NamedTuple):
    data: bytes | None
    reason: str | None
    elapsed_seconds: float = 0.0
    tail: bytes = b""


INVALID_RESULT = StructuredResult(None, "evidence_invalid")


class DuplicateMember(ValueError):
    pass


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateMember(key)
        result[key] = value
    return result


def canonical_json(payload: object) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def read_bounded_regular(path: Path, limit: int) -> bytes:
    """Read a regular non-symlink file without retaining bytes beyond ``limit``."""

    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > limit:
            raise ValueError("file is not bounded regular input")
        chunks: list[bytes] = []
        retained = 0
        while True:
            chunk = os.read(descriptor, min(FILE_READ_CHUNK, limit - retained + 1))
            if not chunk:
                break
            retained += len(chunk)
            if retained > limit:
                raise ValueError("file exceeds input limit")
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def sha256_path(path: Path, limit: int = FILE_SIZE_LIMIT) -> str:
    """Hash a bounded regular non-symlink file using fixed-size reads."""

    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > limit:
            raise ValueError("file is not bounded regular input")
        digest = hashlib.sha256()
        consumed = 0
        while True:
            chunk = os.read(descriptor, FILE_READ_CHUNK)
            if not chunk:
                break
            consumed += len(chunk)
            if consumed > limit:
                raise ValueError("file exceeds input limit")
            digest.update(chunk)
        return digest.hexdigest()
    finally:
        os.close(descriptor)


def load_manifest_bytes(raw: bytes) -> dict[str, object]:
    payload = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
    if not isinstance(payload, dict):
        raise ValueError("manifest root must be an object")
    return payload


def subject_candidate(root: Path, subjects: object) -> str:
    if not isinstance(subjects, dict):
        raise ValueError("subjects must be an object")
    preimage: dict[str, object] = {
        "schema": "fr230-subject-candidate/1",
        "subjects": {},
    }
    rendered: dict[str, list[dict[str, str]]] = {}
    for category in ("production", "tests"):
        paths = subjects.get(category)
        if not isinstance(paths, list) or not paths:
            raise ValueError(f"subjects.{category} must be an array")
        prefix = "tests/" if category == "tests" else "scripts/"
        if any(
            not isinstance(path, str)
            or not path.startswith(prefix)
            or Path(path).is_absolute()
            or ".." in Path(path).parts
            for path in paths
        ):
            raise ValueError(f"subjects.{category} contains an invalid path")
        rendered[category] = [
            {"path": path, "sha256": sha256_path(root / path)} for path in paths
        ]
    preimage["subjects"] = rendered
    return hashlib.sha256(canonical_json(preimage)).hexdigest()


def result_evidence(
    slot: str,
    result_id: str,
    test_id: str,
    candidate: str,
) -> bytes:
    return (
        json.dumps(
        {
            "schema": "fr230-test-result/1",
            "result_id": result_id,
            "slot": slot,
            "status": "PASS",
            "subject_candidate_sha256": candidate,
            "command": ["python3", "-m", "unittest", test_id],
            "returncode": 0,
            "tests_run": 1,
            "suite_tail": "OK",
        },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")


_LIVE_RESULT_CACHE: dict[tuple[str, str, str, str], StructuredResult] = {}


def result_process_group_exists(process_group: int) -> bool:
    """Return true unless absence of the owned process group is proven."""

    try:
        os.killpg(process_group, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def wait_for_result_process_group_exit(
    process: subprocess.Popen[bytes], deadline: float
) -> bool:
    while True:
        process.poll()
        if (
            process.returncode is not None
            and not result_process_group_exists(process.pid)
        ):
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(0.01, remaining))


def signal_result_process_group(
    process: subprocess.Popen[bytes], chosen_signal: int
) -> None:
    try:
        os.killpg(process.pid, chosen_signal)
    except ProcessLookupError:
        pass
    except OSError:
        # The group signal remains authoritative.  Signalling the leader too is
        # only best-effort cleanup when the group operation itself is unproved.
        try:
            process.send_signal(chosen_signal)
        except OSError:
            pass


def terminate_result_process_group(process: subprocess.Popen[bytes]) -> bool:
    """Terminate all remaining members and prove both group exit and reaping."""

    process.poll()
    if (
        process.returncode is not None
        and not result_process_group_exists(process.pid)
    ):
        return True

    signal_result_process_group(process, signal.SIGTERM)
    if wait_for_result_process_group_exit(
        process, time.monotonic() + RESULT_TERM_GRACE_SECONDS
    ):
        return True

    signal_result_process_group(process, signal.SIGKILL)
    return wait_for_result_process_group_exit(
        process, time.monotonic() + RESULT_KILL_GRACE_SECONDS
    )


def read_available_result_output(
    descriptor: int, output: bytearray, limit: int
) -> tuple[bool, bool]:
    """Drain currently available bytes without retaining beyond the hard cap."""

    reached_eof = False
    while True:
        available = limit - len(output)
        try:
            chunk = os.read(descriptor, min(8192, available + 1))
        except BlockingIOError:
            break
        except InterruptedError:
            continue
        if not chunk:
            reached_eof = True
            break
        output.extend(chunk[:available])
        if len(chunk) > available:
            return reached_eof, True
    return reached_eof, False


def bounded_process_output(
    root: Path,
    argv: list[str],
    *,
    environment: dict[str, str],
    timeout: float,
    max_output: int,
    merge_stderr: bool,
) -> StructuredResult:
    """Run one isolated process with bounded output and proven group cleanup."""

    started = time.monotonic()
    try:
        process = subprocess.Popen(
            argv,
            cwd=root,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT if merge_stderr else subprocess.DEVNULL,
            start_new_session=True,
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return StructuredResult(b"", "stream_failed", time.monotonic() - started)

    assert process.stdout is not None
    output = bytearray()
    returncode: int | None = None
    failures: set[str] = set()
    reached_eof = False
    cleanup_proven = False
    selector: selectors.BaseSelector | None = None
    try:
        descriptor = process.stdout.fileno()
        os.set_blocking(descriptor, False)
        selector = selectors.DefaultSelector()
        selector.register(descriptor, selectors.EVENT_READ)
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                failures.add("timed_out")
                break
            events = selector.select(min(remaining, RESULT_STREAM_POLL_SECONDS))
            if events and not reached_eof:
                reached_eof, output_exceeded = read_available_result_output(
                    descriptor, output, max_output
                )
                if output_exceeded:
                    failures.add("output_exceeded")
                if reached_eof:
                    selector.unregister(descriptor)
                if output_exceeded:
                    # Cleanup begins in this iteration, rather than waiting for
                    # the leader to exit or allowing further output to accrue.
                    break
            observed = process.poll()
            if observed is None:
                continue
            returncode = observed
            if not reached_eof:
                reached_eof, output_exceeded = read_available_result_output(
                    descriptor, output, max_output
                )
                if output_exceeded:
                    failures.add("output_exceeded")
            if output_exceeded:
                break
            # poll() reaped the leader.  A still-existing group therefore
            # proves a descendant remains and cannot be allowed to earn PASS.
            if result_process_group_exists(process.pid):
                failures.add("remaining_group_after_exit")
            break
    except (OSError, ValueError, subprocess.SubprocessError):
        failures.add("stream_failed")
    finally:
        # This executes for success, failure, timeout, cap breach, parser I/O
        # failure, and exceptions.  No terminal path can leave group members
        # alive while the evidence is accepted.
        try:
            cleanup_proven = terminate_result_process_group(process)
        except (OSError, ChildProcessError, subprocess.SubprocessError):
            signal_result_process_group(process, signal.SIGKILL)
            cleanup_proven = False
        finally:
            if selector is not None:
                selector.close()
            process.stdout.close()

    if not cleanup_proven:
        failures.add("cleanup_not_proven")
    retained = bytes(output)
    reason = next((item for item in PROCESS_FAILURE_REASONS if item in failures), None)
    if reason is None and returncode != 0:
        reason = f"returncode {returncode}"
    return StructuredResult(
        retained,
        reason,
        time.monotonic() - started,
        retained[-RESULT_OUTPUT_TAIL_LIMIT:],
    )


def live_result_test_passes(root: Path, test_id: str) -> StructuredResult:
    """Rerun one exact unittest with bounded streaming and group-death proof."""

    environment = os.environ.copy()
    environment.pop("FORGE_SESSION_PID", None)
    completed = bounded_process_output(
        root,
        [sys.executable, "-m", "unittest", test_id],
        environment=environment,
        timeout=RESULT_TEST_TIMEOUT_SECONDS,
        max_output=RESULT_OUTPUT_LIMIT,
        merge_stderr=True,
    )
    if completed.reason is not None:
        return completed
    try:
        assert completed.data is not None
        decoded = completed.data.decode("utf-8")
    except UnicodeDecodeError:
        return completed._replace(reason="invalid_result_output")
    lines = [line for line in decoded.splitlines() if line]
    ran = [
        int(match.group(1))
        for line in lines
        if (match := re.fullmatch(r"Ran ([0-9]+) tests? in [0-9.]+s", line))
    ]
    if lines[-1:] != ["OK"] or ran[-1:] != [1]:
        return completed._replace(reason="invalid_result_output")
    return completed


def resolve_live_result(
    root: Path,
    slot: str,
    result_id: str,
    candidate: str,
) -> StructuredResult:
    if RESULT_ID.fullmatch(result_id) is None:
        return INVALID_RESULT
    evidence_path = root / RESULT_EVIDENCE_DIR / f"{result_id}.json"
    try:
        evidence_stat = evidence_path.lstat()
    except OSError:
        return INVALID_RESULT
    if not stat.S_ISREG(evidence_stat.st_mode) or evidence_stat.st_size > 65536:
        return INVALID_RESULT
    try:
        raw = read_bounded_regular(evidence_path, RESULT_OUTPUT_LIMIT)
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError, DuplicateMember):
        return INVALID_RESULT
    if not isinstance(payload, dict) or tuple(payload) != RESULT_KEYS:
        return INVALID_RESULT
    command = payload.get("command")
    if (
        payload.get("schema") != "fr230-test-result/1"
        or payload.get("result_id") != result_id
        or payload.get("slot") != slot
        or payload.get("status") != "PASS"
        or payload.get("subject_candidate_sha256") != candidate
        or not isinstance(command, list)
        or len(command) != 4
        or command[:3] != ["python3", "-m", "unittest"]
        or not isinstance(command[3], str)
        or re.fullmatch(r"tests(?:\.[A-Za-z_][A-Za-z0-9_]*)+", command[3]) is None
        or type(payload.get("returncode")) is not int
        or payload.get("returncode") != 0
        or type(payload.get("tests_run")) is not int
        or payload.get("tests_run") != 1
        or payload.get("suite_tail") != "OK"
        or raw != result_evidence(slot, result_id, command[3], candidate)
    ):
        return INVALID_RESULT
    if result_id != RESULT_IDS.get(slot) or command[3] != RESULT_TESTS.get(slot):
        return INVALID_RESULT
    evidence_digest = hashlib.sha256(raw).hexdigest()
    key = (slot, result_id, candidate, evidence_digest)
    if key in _LIVE_RESULT_CACHE:
        return _LIVE_RESULT_CACHE[key]
    completed = live_result_test_passes(root, command[3])
    resolved = StructuredResult(
        raw if completed.reason is None else None,
        completed.reason,
        completed.elapsed_seconds,
        completed.tail,
    )
    _LIVE_RESULT_CACHE[key] = resolved
    return resolved


Resolver = Callable[[Path, str, str, str], StructuredResult]


def unresolved_result_issue(slot: str, resolution: StructuredResult) -> str:
    reason = resolution.reason or "unknown"
    return (
        f"PASS result evidence is unresolved: {slot} "
        f"({reason}, {resolution.elapsed_seconds:.1f}s)"
    )


def validate_manifest(
    root: Path,
    payload: dict[str, object],
    *,
    resolver: Resolver = resolve_live_result,
    previous_bytes: bytes | None = None,
) -> list[str]:
    issues: list[str] = []
    if tuple(payload) != ROOT_KEYS:
        issues.append("manifest root members or member order are invalid")
    generation = payload.get("generation")
    phase = payload.get("phase")
    previous_digest = payload.get("previous_manifest_sha256")
    if type(generation) is not int:
        issues.append("manifest generation type is invalid")
    if type(generation) is int and generation == 1:
        if phase != "phase-3" or previous_digest is not None or previous_bytes is not None:
            issues.append("generation 1 phase/predecessor tuple is invalid")
    elif type(generation) is int and generation == 2:
        if phase != "phase-4" or previous_bytes is None:
            issues.append("generation 2 phase/predecessor tuple is invalid")
        elif len(previous_bytes) > MANIFEST_SIZE_LIMIT:
            issues.append("generation 2 predecessor exceeds size limit")
        elif previous_digest != hashlib.sha256(previous_bytes).hexdigest():
            issues.append("generation 2 predecessor digest is invalid")
    elif type(generation) is int:
        issues.append("manifest generation is invalid")
    if payload.get("schema") != "fr230-phase3-4-manifest/2":
        issues.append("manifest schema is invalid")

    artifacts = payload.get("artifacts")
    artifact_paths: list[object] = []
    if not isinstance(artifacts, list):
        issues.append("artifacts must be an array")
    else:
        artifact_entries_valid = True
        for index, entry in enumerate(artifacts):
            if not isinstance(entry, dict) or tuple(entry) != ("path", "sha256"):
                issues.append(f"artifacts[{index}] members are invalid")
                artifact_entries_valid = False
                continue
            path = entry.get("path")
            digest = entry.get("sha256")
            artifact_paths.append(path)
            if (
                not isinstance(path, str)
                or Path(path).is_absolute()
                or ".." in Path(path).parts
                or path == MANIFEST_PATH.as_posix()
            ):
                issues.append(f"artifacts[{index}] path is invalid or self-referential")
                artifact_entries_valid = False
            if not isinstance(digest, str) or HEX64.fullmatch(digest) is None:
                issues.append(f"artifacts[{index}] digest is invalid")
                artifact_entries_valid = False
        if artifact_paths != list(ARTIFACT_PATHS):
            issues.append("artifact inventory or bytewise order is invalid")
            artifact_entries_valid = False
        if artifact_entries_valid:
            for entry in artifacts:
                path = entry["path"]
                try:
                    actual = sha256_path(root / path)
                except (OSError, ValueError):
                    issues.append(f"artifact is unresolved: {path}")
                else:
                    if actual != entry["sha256"]:
                        issues.append(f"artifact digest mismatch: {path}")

    v1_artifacts = payload.get("v1_artifacts")
    if not isinstance(v1_artifacts, list):
        issues.append("v1_artifacts must be an array")
    else:
        expected_v1 = [
            {"path": path, "sha256": digest}
            for path, digest in sorted(V1_HASHES.items())
        ]
        if v1_artifacts != expected_v1:
            issues.append("v1 artifact inventory or pins are invalid")
        for path, digest in V1_HASHES.items():
            artifact = root / path
            try:
                actual = sha256_path(artifact)
            except (OSError, ValueError):
                issues.append(f"v1 artifact is unresolved: {path}")
            else:
                if actual != digest:
                    issues.append(f"v1 artifact bytes changed: {path}")

    subjects = payload.get("subjects")
    candidate = ""
    if not isinstance(subjects, dict) or tuple(subjects) != ("production", "tests"):
        issues.append("subjects members or member order are invalid")
    else:
        for category in ("production", "tests"):
            paths = subjects.get(category)
            if (
                not isinstance(paths, list)
                or not paths
                or not all(isinstance(path, str) and path for path in paths)
                or paths != sorted(paths)
                or len(paths) != len(set(paths))
            ):
                issues.append(f"subjects.{category} is not nonempty, unique, and sorted")
                continue
            required_prefix = "tests/" if category == "tests" else "scripts/"
            for path in paths:
                candidate_path = root / path
                if (
                    not path.startswith(required_prefix)
                    or Path(path).is_absolute()
                    or ".." in Path(path).parts
                ):
                    issues.append(f"subjects.{category} path is invalid: {path}")
                    continue
                try:
                    metadata = candidate_path.lstat()
                except OSError:
                    issues.append(f"subjects.{category} path is invalid: {path}")
                    continue
                if candidate_path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
                    issues.append(f"subjects.{category} path is invalid: {path}")
        if not any(issue.startswith("subjects.") for issue in issues):
            try:
                candidate = subject_candidate(root, subjects)
            except (OSError, ValueError) as exc:
                issues.append(f"subject candidate is unresolved: {exc}")

    bindings = payload.get("result_bindings")
    binding_by_slot: dict[str, dict[str, object]] = {}
    if not isinstance(bindings, list):
        issues.append("result_bindings must be an array")
    else:
        slots: list[object] = []
        for index, binding in enumerate(bindings):
            if not isinstance(binding, dict) or tuple(binding) != (
                "slot",
                "status",
                "result_id",
                "result_sha256",
            ):
                issues.append(f"result_bindings[{index}] members are invalid")
                continue
            slot = binding.get("slot")
            slots.append(slot)
            if isinstance(slot, str) and slot not in binding_by_slot:
                binding_by_slot[slot] = binding
            else:
                issues.append(f"result binding slot is invalid or duplicated: {slot}")
        if slots != list(SLOTS):
            issues.append("result binding inventory or bytewise order is invalid")

    previous_payload: dict[str, object] | None = None
    if (
        generation == 2
        and previous_bytes is not None
        and len(previous_bytes) <= MANIFEST_SIZE_LIMIT
    ):
        try:
            previous_payload = load_manifest_bytes(previous_bytes)
        except (UnicodeError, json.JSONDecodeError, DuplicateMember, ValueError):
            issues.append("generation 2 predecessor bytes are not a valid manifest")
        else:
            if previous_payload.get("generation") != 1:
                issues.append("generation 2 predecessor is not generation 1")
            predecessor_issues = validate_manifest(
                root,
                previous_payload,
                resolver=resolver,
            )
            issues.extend(
                f"generation 2 predecessor invalid: {issue}"
                for issue in predecessor_issues
            )
            for member in ("artifacts", "v1_artifacts", "subjects"):
                if payload.get(member) != previous_payload.get(member):
                    issues.append(f"generation 2 changed immutable {member}")

    resolved_result_ids: list[str] = []
    resolved_test_ids: list[str] = []
    for slot in SLOTS:
        binding = binding_by_slot.get(slot)
        if binding is None:
            continue
        status = binding.get("status")
        result_id = binding.get("result_id")
        result_sha256 = binding.get("result_sha256")
        if generation == 1 and slot in GENERATION_ONE_PENDING:
            if (
                status != "pending-phase-4"
                or result_id is not None
                or result_sha256 is not None
            ):
                issues.append(f"generation 1 pending binding is invalid: {slot}")
            continue
        if status != "PASS":
            issues.append(f"resolved binding is not PASS: {slot}")
            continue
        if (
            not isinstance(result_id, str)
            or not result_id
            or not isinstance(result_sha256, str)
            or HEX64.fullmatch(result_sha256) is None
        ):
            issues.append(f"PASS binding fields are invalid: {slot}")
            continue
        if result_id != RESULT_IDS.get(slot):
            issues.append(
                f"generation {generation} PASS result ID is invalid: {slot}"
            )
            continue
        resolved_result_ids.append(result_id)
        if not candidate:
            issues.append(f"PASS binding has no resolved subject candidate: {slot}")
            continue
        resolution = resolver(root, slot, result_id, candidate)
        evidence = resolution.data
        if evidence is None:
            issues.append(unresolved_result_issue(slot, resolution))
            continue
        if hashlib.sha256(evidence).hexdigest() != result_sha256:
            issues.append(f"PASS result evidence digest mismatches: {slot}")
            continue
        try:
            evidence_payload = json.loads(
                evidence.decode("utf-8"), object_pairs_hook=unique_object
            )
        except (UnicodeError, json.JSONDecodeError, DuplicateMember):
            issues.append(f"PASS result evidence is malformed: {slot}")
            continue
        if (
            not isinstance(evidence_payload, dict)
            or tuple(evidence_payload) != RESULT_KEYS
            or evidence_payload.get("schema") != "fr230-test-result/1"
            or evidence_payload.get("status") != "PASS"
            or evidence_payload.get("result_id") != result_id
            or evidence_payload.get("slot") != slot
            or evidence_payload.get("subject_candidate_sha256") != candidate
            or evidence_payload.get("returncode") != 0
            or evidence_payload.get("tests_run") != 1
            or evidence_payload.get("suite_tail") != "OK"
        ):
            issues.append(f"PASS result evidence outcome or candidate is invalid: {slot}")
            continue
        expected_test_id = RESULT_TESTS[slot]
        if evidence_payload.get("command") != [
            "python3",
            "-m",
            "unittest",
            expected_test_id,
        ]:
            issues.append(
                f"generation {generation} PASS command is invalid: {slot}"
            )
            continue
        resolved_test_ids.append(expected_test_id)

    if len(resolved_result_ids) != len(set(resolved_result_ids)):
        issues.append("PASS result IDs are duplicated across slots")
    if len(resolved_test_ids) != len(set(resolved_test_ids)):
        issues.append("PASS result commands are duplicated across slots")

    if generation == 2 and previous_payload is not None:
        prior_bindings = {
            binding.get("slot"): binding
            for binding in previous_payload.get("result_bindings", [])
            if isinstance(binding, dict)
        }
        for slot in set(SLOTS) - GENERATION_ONE_PENDING:
            if binding_by_slot.get(slot) != prior_bindings.get(slot):
                issues.append(f"generation 2 changed prior PASS binding: {slot}")
        for slot in GENERATION_ONE_PENDING:
            if binding_by_slot.get(slot, {}).get("status") != "PASS":
                issues.append(f"generation 2 did not resolve pending slot: {slot}")
    return issues


def static_resolver(
    root: Path,
    slot: str,
    result_id: str,
    candidate: str,
) -> StructuredResult:
    del root
    if result_id != RESULT_IDS.get(slot):
        return INVALID_RESULT
    evidence = result_evidence(slot, result_id, RESULT_TESTS[slot], candidate)
    return StructuredResult(evidence, None)


def historical_predecessor(root: Path, expected_digest: object) -> bytes | None:
    if not isinstance(expected_digest, str) or HEX64.fullmatch(expected_digest) is None:
        return None
    environment = os.environ.copy()
    environment.pop("FORGE_SESSION_PID", None)
    history = bounded_process_output(
        root,
        [
            "git",
            "rev-list",
            "--first-parent",
            "--max-count=8",
            "HEAD",
            "--",
            MANIFEST_PATH.as_posix(),
        ],
        environment=environment,
        timeout=HISTORY_COMMAND_TIMEOUT_SECONDS,
        max_output=HISTORY_LIST_OUTPUT_LIMIT,
        merge_stderr=False,
    )
    if history.reason is not None:
        return None
    try:
        assert history.data is not None
        commits = history.data.decode("ascii").splitlines()
    except UnicodeDecodeError:
        return None
    for commit in commits:
        if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit) is None:
            return None
        shown = bounded_process_output(
            root,
            ["git", "show", f"{commit}:{MANIFEST_PATH.as_posix()}"],
            environment=environment,
            timeout=HISTORY_COMMAND_TIMEOUT_SECONDS,
            max_output=MANIFEST_SIZE_LIMIT,
            merge_stderr=False,
        )
        if shown.reason is not None:
            return None
        assert shown.data is not None
        if hashlib.sha256(shown.data).hexdigest() == expected_digest:
            return shown.data
    return None


def validate_current_manifest(
    root: Path,
    *,
    resolver: Resolver = resolve_live_result,
) -> list[str]:
    """Validate the installed generation, resolving a generation-2 predecessor."""

    try:
        raw = read_bounded_regular(root / MANIFEST_PATH, MANIFEST_SIZE_LIMIT)
        payload = load_manifest_bytes(raw)
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError, DuplicateMember):
        return ["current manifest is unreadable or malformed"]
    previous_bytes = None
    if payload.get("generation") == 2:
        previous_bytes = historical_predecessor(
            root, payload.get("previous_manifest_sha256")
        )
        if previous_bytes is None:
            return ["generation 2 predecessor is unresolved"]
    return validate_manifest(
        root,
        payload,
        resolver=resolver,
        previous_bytes=previous_bytes,
    )


class LiveResultRunnerTests(unittest.TestCase):
    @staticmethod
    def run_probe(root: Path, source: str) -> StructuredResult:
        return bounded_process_output(
            root,
            [sys.executable, "-c", source],
            environment=os.environ.copy(),
            timeout=RESULT_TEST_TIMEOUT_SECONDS,
            max_output=RESULT_OUTPUT_LIMIT,
            merge_stderr=True,
        )

    @staticmethod
    def stop_probe(pid_path: Path) -> None:
        try:
            process_id = int(pid_path.read_text(encoding="ascii"))
        except (OSError, UnicodeError, ValueError):
            return
        if process_id <= 1:
            return
        try:
            os.kill(process_id, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def test_each_bounded_failure_reason_is_forced_and_load_bearing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="forge-fr230-runner-") as raw:
            root = Path(raw)
            pid_path = root / "probe.pid"
            survived = root / "probe-survived"
            def source(*lines: str) -> str:
                return "\n".join(lines) + "\n"

            leader_prefix = source(
                "import os",
                "import time",
                "from pathlib import Path",
                f"pid_path = Path({str(pid_path)!r})",
                "pid_path.write_text(str(os.getpid()), encoding='ascii')",
            )
            descendant = source(
                "import os",
                "import signal",
                "import time",
                "from pathlib import Path",
                "signal.signal(signal.SIGTERM, signal.SIG_IGN)",
                f"Path({str(pid_path)!r}).write_text(str(os.getpid()), encoding='ascii')",
                "time.sleep(0.75)",
                f"Path({str(survived)!r}).write_text('survived\\n', encoding='utf-8')",
                "time.sleep(2)",
            )
            scripts = {
                "timed_out": leader_prefix + source(
                    "time.sleep(0.5)",
                    f"Path({str(survived)!r}).write_text('survived\\n', encoding='utf-8')",
                ),
                "output_exceeded": leader_prefix + source(
                    f"os.write(1, b'x' * ({RESULT_OUTPUT_LIMIT} + 1))",
                    "time.sleep(0.5)",
                    f"Path({str(survived)!r}).write_text('survived\\n', encoding='utf-8')",
                    "time.sleep(2)",
                ),
                "stream_failed": "print('ready')",
                "remaining_group_after_exit": source(
                    "import subprocess",
                    "import sys",
                    "import time",
                    "from pathlib import Path",
                    f"subprocess.Popen([sys.executable, '-c', {descendant!r}])",
                    f"pid_path = Path({str(pid_path)!r})",
                    "deadline = time.monotonic() + 2",
                    "while not pid_path.exists() and time.monotonic() < deadline:",
                    "    time.sleep(0.01)",
                    "assert pid_path.exists()",
                ),
                "cleanup_not_proven": "pass",
                "returncode 7": "raise SystemExit(7)",
            }
            manifest = load_manifest_bytes(read_bounded_regular(MANIFEST, MANIFEST_SIZE_LIMIT))
            slot = "cleanup"
            result_id = RESULT_IDS[slot]
            evidence_path = ROOT / RESULT_EVIDENCE_DIR / f"{result_id}.json"
            evidence = read_bounded_regular(evidence_path, RESULT_OUTPUT_LIMIT)
            stored_candidate = json.loads(evidence.decode("utf-8"))["subject_candidate_sha256"]
            cases = (
                ("timed_out", "timed_out", 0.05, 0.6),
                ("output_exceeded", "output_exceeded", 120, 0.65),
                ("stream_failed", "stream_failed", 120, 0),
                ("remaining_group_after_exit", "remaining_group_after_exit", 120, 0.9),
                ("cleanup_not_proven", "cleanup_not_proven", 120, 0),
                ("returncode 7", "returncode 7", 120, 0),
            )
            for mode, expected, timeout, side_effect_wait in cases:
                pid_path.unlink(missing_ok=True)
                survived.unlink(missing_ok=True)
                try:
                    with mock.patch.object(sys.modules[__name__], "RESULT_TEST_TIMEOUT_SECONDS", timeout):
                        if mode == "stream_failed":
                            with mock.patch.object(
                                sys.modules[__name__],
                                "read_available_result_output",
                                side_effect=OSError("forced stream failure"),
                            ):
                                completed = self.run_probe(root, scripts[mode])
                        elif mode == "cleanup_not_proven":
                            with mock.patch.object(
                                sys.modules[__name__],
                                "terminate_result_process_group",
                                return_value=False,
                            ):
                                completed = self.run_probe(root, scripts[mode])
                        else:
                            completed = self.run_probe(root, scripts[mode])
                    with self.subTest(reason=expected):
                        self.assertEqual(completed.reason, expected)
                        self.assertGreaterEqual(completed.elapsed_seconds, 0)
                        self.assertLessEqual(len(completed.tail), RESULT_OUTPUT_TAIL_LIMIT)
                    if side_effect_wait:
                        time.sleep(side_effect_wait)
                        self.assertFalse(survived.exists(), f"{expected} left its process group alive")
                finally:
                    self.stop_probe(pid_path)

                marker = f"tail:{expected}".encode("ascii")
                diagnostic = completed._replace(elapsed_seconds=1.2, tail=marker)
                expected_issue = f"PASS result evidence is unresolved: {slot} ({expected}, 1.2s)"

                def diagnostic_issues(result: StructuredResult) -> list[str]:
                    _LIVE_RESULT_CACHE.clear()
                    with mock.patch.object(
                        sys.modules[__name__], "subject_candidate", return_value=stored_candidate
                    ), mock.patch.object(
                        sys.modules[__name__], "bounded_process_output", return_value=result
                    ):
                        issues = validate_manifest(ROOT, manifest)
                        cached = resolve_live_result(ROOT, slot, result_id, stored_candidate)
                    self.assertEqual(cached.tail, marker)
                    return issues

                self.assertIn(expected_issue, diagnostic_issues(diagnostic))
                disabled_issues = diagnostic_issues(diagnostic._replace(reason=None))
                _LIVE_RESULT_CACHE.clear()
                self.assertNotIn(expected_issue, disabled_issues)

class Phase34ManifestTests(unittest.TestCase):
    def payload(self) -> dict[str, object]:
        return load_manifest_bytes(read_bounded_regular(MANIFEST, MANIFEST_SIZE_LIMIT))

    def manifest_issues(
        self,
        payload: dict[str, object],
        previous_bytes: bytes | None,
        resolver: Resolver = static_resolver,
    ) -> list[str]:
        return validate_manifest(
            ROOT, payload, resolver=resolver, previous_bytes=previous_bytes
        )

    def current_predecessor(
        self, payload: dict[str, object]
    ) -> bytes | None:
        generation = payload.get("generation")
        if generation == 1:
            return None
        if generation != 2:
            return None
        predecessor = historical_predecessor(
            ROOT, payload.get("previous_manifest_sha256")
        )
        self.assertIsNotNone(
            predecessor,
            "generation 2 does not resolve its exact committed generation-1 predecessor",
        )
        return predecessor

    def test_current_manifest_generation_resolves_real_pass_results(self) -> None:
        payload = self.payload()
        self.assertIn(payload.get("generation"), (1, 2))
        self.assertEqual(validate_current_manifest(ROOT), [])

    def test_generation_one_pending_partition_and_result_contract_are_exact(
        self,
    ) -> None:
        payload = self.payload()
        self.assertEqual(set(PHASE3_RESULT_TESTS), set(SLOTS) - GENERATION_ONE_PENDING)
        self.assertEqual(set(PHASE4_RESULT_TESTS), GENERATION_ONE_PENDING)
        self.assertEqual(set(RESULT_IDS), set(SLOTS))
        self.assertEqual(set(RESULT_TESTS), set(SLOTS))
        self.assertEqual(len(set(RESULT_IDS.values())), len(SLOTS))
        self.assertEqual(len(set(RESULT_TESTS.values())), len(SLOTS))
        bindings = {item["slot"]: item for item in payload["result_bindings"]}
        pending = {
            slot
            for slot, item in bindings.items()
            if item["status"] == "pending-phase-4"
        }
        if payload.get("generation") == 1:
            self.assertEqual(pending, GENERATION_ONE_PENDING)
            self.assertEqual(
                {
                    slot: item["result_id"]
                    for slot, item in bindings.items()
                    if slot not in GENERATION_ONE_PENDING
                },
                PHASE3_RESULT_IDS,
            )
        else:
            self.assertEqual(payload.get("generation"), 2)
            self.assertEqual(pending, set())
            self.assertEqual(
                {slot: item["result_id"] for slot, item in bindings.items()},
                RESULT_IDS,
            )

    def test_pending_and_fictional_pass_rows_fail_closed(self) -> None:
        baseline = self.payload()
        previous_bytes = self.current_predecessor(baseline)
        candidate = subject_candidate(ROOT, baseline["subjects"])
        mutants: dict[str, dict[str, object]] = {}

        pending_outside = copy.deepcopy(baseline)
        cleanup = pending_outside["result_bindings"][1]
        cleanup.update(
            {"status": "pending-phase-4", "result_id": None, "result_sha256": None}
        )
        mutants["pending outside exact partition"] = pending_outside

        pending_with_evidence = copy.deepcopy(baseline)
        pending_with_evidence["result_bindings"][0].update(
            {
                "status": "pending-phase-4",
                "result_id": "invented",
                "result_sha256": "0" * 64,
            }
        )
        mutants["pending carries asserted evidence"] = pending_with_evidence

        fictional = copy.deepcopy(baseline)
        binding = fictional["result_bindings"][1]
        fictional_id = PHASE3_RESULT_IDS["cleanup"]
        fictional_test = (
            "tests.test_fr223_v2_byte_pins.V2ArtifactBytePinTests."
            "test_all_seven_artifacts_match_the_generation_contract"
        )
        binding["result_id"] = fictional_id
        binding["result_sha256"] = hashlib.sha256(
            result_evidence("cleanup", fictional_id, fictional_test, candidate)
        ).hexdigest()
        mutants["unrelated real passing test cannot fill a slot"] = fictional

        bad_digest = copy.deepcopy(baseline)
        bad_digest["result_bindings"][1]["result_sha256"] = "0" * 64
        mutants["resolved result digest mismatch"] = bad_digest

        def known_only(
            root: Path,
            slot: str,
            result_id: str,
            current: str,
        ) -> StructuredResult:
            del root
            test_id = fictional_test if slot == "cleanup" else RESULT_TESTS[slot]
            return StructuredResult(result_evidence(slot, result_id, test_id, current), None)

        for label, mutant in mutants.items():
            with self.subTest(label=label):
                self.assertTrue(
                    self.manifest_issues(mutant, previous_bytes, known_only),
                    "invalid result binding was accepted",
                )

    def test_layout_inventory_and_candidate_mutants_fail_closed(self) -> None:
        baseline = self.payload()
        previous_bytes = self.current_predecessor(baseline)
        mutants: dict[str, dict[str, object]] = {}
        reordered_root = {key: baseline[key] for key in reversed(ROOT_KEYS)}
        mutants["root order"] = reordered_root
        missing_artifact = copy.deepcopy(baseline)
        missing_artifact["artifacts"].pop()
        mutants["artifact missing"] = missing_artifact
        self_hash = copy.deepcopy(baseline)
        self_hash["artifacts"][0]["path"] = MANIFEST_PATH.as_posix()
        mutants["manifest self hash"] = self_hash
        absolute_artifact = copy.deepcopy(baseline)
        absolute_artifact["artifacts"][0]["path"] = "/outside/forge-v2.json"
        mutants["absolute artifact"] = absolute_artifact
        traversal_artifact = copy.deepcopy(baseline)
        traversal_artifact["artifacts"][0]["path"] = "../outside/forge-v2.json"
        mutants["traversal artifact"] = traversal_artifact
        bad_v1 = copy.deepcopy(baseline)
        bad_v1["v1_artifacts"][0]["sha256"] = "0" * 64
        mutants["v1 remint"] = bad_v1
        duplicate_subject = copy.deepcopy(baseline)
        duplicate_subject["subjects"]["tests"].append(
            duplicate_subject["subjects"]["tests"][0]
        )
        mutants["duplicate subject"] = duplicate_subject
        duplicate_slot = copy.deepcopy(baseline)
        duplicate_slot["result_bindings"][1]["slot"] = "activated-denial"
        mutants["duplicate slot"] = duplicate_slot
        boolean_generation = copy.deepcopy(baseline)
        boolean_generation["generation"] = True
        mutants["boolean generation"] = boolean_generation
        floating_generation = copy.deepcopy(baseline)
        floating_generation["generation"] = 1.0
        mutants["floating generation"] = floating_generation

        for label, mutant in mutants.items():
            with self.subTest(label=label):
                self.assertTrue(
                    self.manifest_issues(mutant, previous_bytes),
                    "invalid manifest layout was accepted",
                )

    def test_invalid_artifact_paths_are_rejected_before_hash_io(self) -> None:
        baseline = self.payload()
        previous_bytes = self.current_predecessor(baseline)
        for malicious in ("/outside/forge-v2.json", "../outside/forge-v2.json"):
            mutant = copy.deepcopy(baseline)
            mutant["artifacts"][0]["path"] = malicious
            forbidden = ROOT / malicious
            real_hash = sha256_path

            def guarded_hash(path: Path, limit: int = FILE_SIZE_LIMIT) -> str:
                if path == forbidden:
                    self.fail("validator read an artifact before inventory acceptance")
                return real_hash(path, limit)

            with mock.patch.object(
                sys.modules[__name__], "sha256_path", side_effect=guarded_hash
            ):
                issues = self.manifest_issues(mutant, previous_bytes)
            with self.subTest(path=malicious):
                self.assertIn("artifact inventory or bytewise order is invalid", issues)

    def test_file_and_predecessor_size_limits_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="forge-fr230-bounded-file-") as raw:
            oversized = Path(raw) / "oversized"
            oversized.write_bytes(b"12345")
            with self.assertRaises(ValueError):
                read_bounded_regular(oversized, 4)
            with self.assertRaises(ValueError):
                sha256_path(oversized, 4)

        baseline = self.payload()
        generation_two = copy.deepcopy(baseline)
        generation_two["generation"] = 2
        generation_two["phase"] = "phase-4"
        oversized_predecessor = b"x" * (MANIFEST_SIZE_LIMIT + 1)
        generation_two["previous_manifest_sha256"] = hashlib.sha256(
            oversized_predecessor
        ).hexdigest()
        issues = self.manifest_issues(generation_two, oversized_predecessor)
        self.assertIn("generation 2 predecessor exceeds size limit", issues)

    def test_duplicate_json_member_is_rejected(self) -> None:
        raw = read_bounded_regular(MANIFEST, MANIFEST_SIZE_LIMIT)
        duplicate = raw.replace(
            b'{\n  "schema":', b'{\n  "schema": "duplicate",\n  "schema":', 1
        )
        with self.assertRaises(DuplicateMember):
            load_manifest_bytes(duplicate)

    def test_current_entry_point_resolves_generation_two_predecessor(self) -> None:
        previous_bytes = read_bounded_regular(MANIFEST, MANIFEST_SIZE_LIMIT)
        previous = load_manifest_bytes(previous_bytes)
        if previous.get("generation") == 2:
            resolved = self.current_predecessor(previous)
            assert resolved is not None
            previous_bytes = resolved
            previous = load_manifest_bytes(previous_bytes)
        self.assertEqual(previous.get("generation"), 1)
        generation_two = copy.deepcopy(previous)
        generation_two["generation"] = 2
        generation_two["phase"] = "phase-4"
        generation_two["previous_manifest_sha256"] = hashlib.sha256(
            previous_bytes
        ).hexdigest()
        candidate = subject_candidate(ROOT, generation_two["subjects"])
        for binding in generation_two["result_bindings"]:
            if binding["slot"] not in GENERATION_ONE_PENDING:
                continue
            slot = binding["slot"]
            result_id = PHASE4_RESULT_IDS[slot]
            test_id = PHASE4_RESULT_TESTS[slot]
            binding.update(
                {
                    "status": "PASS",
                    "result_id": result_id,
                    "result_sha256": hashlib.sha256(
                        result_evidence(slot, result_id, test_id, candidate)
                    ).hexdigest(),
                }
            )
        rendered = (
            json.dumps(generation_two, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
        real_read = read_bounded_regular

        def installed_manifest(path: Path, limit: int) -> bytes:
            if path == MANIFEST:
                self.assertLessEqual(len(rendered), limit)
                return rendered
            return real_read(path, limit)

        with (
            mock.patch.object(
                sys.modules[__name__],
                "read_bounded_regular",
                side_effect=installed_manifest,
            ),
            mock.patch.object(
                sys.modules[__name__],
                "historical_predecessor",
                return_value=previous_bytes,
            ) as predecessor_resolver,
        ):
            self.assertEqual(
                validate_current_manifest(ROOT, resolver=static_resolver), []
            )
        predecessor_resolver.assert_called_once_with(
            ROOT, generation_two["previous_manifest_sha256"]
        )

    def test_generation_two_requires_predecessor_and_only_pending_replacement(self) -> None:
        current = self.payload()
        if current.get("generation") == 1:
            previous_bytes = read_bounded_regular(MANIFEST, MANIFEST_SIZE_LIMIT)
            generation_two = copy.deepcopy(load_manifest_bytes(previous_bytes))
            generation_two["generation"] = 2
            generation_two["phase"] = "phase-4"
            generation_two["previous_manifest_sha256"] = hashlib.sha256(
                previous_bytes
            ).hexdigest()
            candidate = subject_candidate(ROOT, generation_two["subjects"])
            for binding in generation_two["result_bindings"]:
                if binding["slot"] not in GENERATION_ONE_PENDING:
                    continue
                slot = binding["slot"]
                result_id = PHASE4_RESULT_IDS[slot]
                test_id = PHASE4_RESULT_TESTS[slot]
                binding.update(
                    {
                        "status": "PASS",
                        "result_id": result_id,
                        "result_sha256": hashlib.sha256(
                            result_evidence(slot, result_id, test_id, candidate)
                        ).hexdigest(),
                    }
                )
        else:
            self.assertEqual(current.get("generation"), 2)
            previous_bytes = self.current_predecessor(current)
            assert previous_bytes is not None
            generation_two = copy.deepcopy(current)
            candidate = subject_candidate(ROOT, generation_two["subjects"])
        self.assertEqual(
            self.manifest_issues(generation_two, previous_bytes),
            [],
        )
        # This candidate exists only in memory to exercise generation-aware
        # validation.  It neither writes result evidence nor persists a
        # generation-2 PASS assertion in the generation-1 repository.
        for slot in SLOTS:
            expected_id = RESULT_IDS[slot]
            expected_test = RESULT_TESTS[slot]
            recycled_slot = next(item for item in SLOTS if item != slot)
            recycled_test = RESULT_TESTS[recycled_slot]

            wrong_id = copy.deepcopy(generation_two)
            wrong_binding = next(
                item for item in wrong_id["result_bindings"] if item["slot"] == slot
            )
            recycled_id = RESULT_IDS[recycled_slot]
            wrong_binding["result_id"] = recycled_id
            wrong_binding["result_sha256"] = hashlib.sha256(
                result_evidence(slot, recycled_id, expected_test, candidate)
            ).hexdigest()
            wrong_id_issues = self.manifest_issues(wrong_id, previous_bytes)
            with self.subTest(slot=slot, mutation="recycled result ID"):
                self.assertIn(
                    f"generation 2 PASS result ID is invalid: {slot}",
                    wrong_id_issues,
                )

            unrelated_command = copy.deepcopy(generation_two)
            unrelated_binding = next(
                item
                for item in unrelated_command["result_bindings"]
                if item["slot"] == slot
            )
            unrelated_evidence = result_evidence(
                slot, expected_id, recycled_test, candidate
            )
            unrelated_binding["result_sha256"] = hashlib.sha256(
                unrelated_evidence
            ).hexdigest()

            def unrelated_resolver(
                root: Path,
                current_slot: str,
                result_id: str,
                current_candidate: str,
            ) -> StructuredResult:
                if current_slot == slot and result_id == expected_id:
                    return StructuredResult(
                        result_evidence(
                            current_slot,
                            result_id,
                            recycled_test,
                            current_candidate,
                        ),
                        None,
                    )
                return static_resolver(
                    root, current_slot, result_id, current_candidate
                )

            unrelated_issues = self.manifest_issues(
                unrelated_command, previous_bytes, unrelated_resolver
            )
            with self.subTest(slot=slot, mutation="recycled test command"):
                self.assertIn(
                    f"generation 2 PASS command is invalid: {slot}",
                    unrelated_issues,
                )

        predecessor_mismatch = copy.deepcopy(generation_two)
        predecessor_mismatch["previous_manifest_sha256"] = "0" * 64
        still_pending = copy.deepcopy(generation_two)
        still_pending["result_bindings"][0].update(
            {"status": "pending-phase-4", "result_id": None, "result_sha256": None}
        )
        changed_artifact = copy.deepcopy(generation_two)
        changed_artifact["artifacts"][0]["sha256"] = "0" * 64
        changed_pass = copy.deepcopy(generation_two)
        changed_result_id = "fr230-phase-4-cleanup"
        changed_pass["result_bindings"][1]["result_id"] = changed_result_id
        changed_pass["result_bindings"][1]["result_sha256"] = hashlib.sha256(
            result_evidence(
                "cleanup",
                changed_result_id,
                PHASE3_RESULT_TESTS["cleanup"],
                candidate,
            )
        ).hexdigest()
        reordered_predecessor = {
            key: self.payload()[key] for key in reversed(ROOT_KEYS)
        }
        reordered_predecessor_bytes = (
            json.dumps(reordered_predecessor, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
        bad_predecessor = copy.deepcopy(generation_two)
        bad_predecessor["previous_manifest_sha256"] = hashlib.sha256(
            reordered_predecessor_bytes
        ).hexdigest()
        for label, mutant in {
            "predecessor mismatch": predecessor_mismatch,
            "pending survived": still_pending,
            "artifact replacement": changed_artifact,
            "prior PASS replacement": changed_pass,
        }.items():
            with self.subTest(label=label):
                self.assertTrue(
                    self.manifest_issues(mutant, previous_bytes)
                )

        self.assertTrue(
            self.manifest_issues(bad_predecessor, reordered_predecessor_bytes)
        )


if __name__ == "__main__":
    unittest.main()
