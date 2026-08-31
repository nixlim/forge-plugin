from __future__ import annotations

import base64
import binascii
import fcntl
import json
import os
import re
import socket
import stat
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, Sequence

from . import journal
from commitment_paths import (
    CommitmentPathSurface,
    commitment_surface,
    validate_surface_path,
)


_BATCH_INTENT_SURFACE = commitment_surface("batch.intent")
_BATCH_RECEIPT_SURFACE = commitment_surface("batch.receipt")


@dataclass(frozen=True)
class BatchOutcome:
    receipt: dict[str, object]
    records: tuple[dict[str, object], ...]
    repeated: bool

    def payload(self) -> dict[str, object]:
        return {
            "receipt": self.receipt,
            "records": list(self.records),
            "repeated": self.repeated,
        }


@dataclass(frozen=True)
class BatchLock:
    run_dir: Path
    run_descriptor: int
    lock_descriptor: int
    lock_observation: journal.FileObservation


@dataclass(frozen=True)
class _ChainBatchAuthorization:
    repository: str
    run_id: str
    task_id: str
    chain_id: str
    source_event_digest: str
    request_sha256: str
    batch_bytes: bytes
    record_count: int
    journal_exact: journal.ExactFile
    receipts_exact: journal.ExactFile


RecordBuilder = Callable[
    [journal.RunState, Path], Sequence[dict[str, object]]
]
RecordResolver = Callable[
    [journal.RunState, Path, Sequence[dict[str, object]]],
    Sequence[dict[str, object]],
]
RelationProver = Callable[
    [journal.RunState, Path, Sequence[dict[str, object]]], None
]
InputValidator = Callable[[], None]
CitationValidator = Callable[[Path, Path], None]
RecordSchemaValidator = Callable[[journal.RunState, Path], None]
TransactionBaseValidator = Callable[
    [journal.ExactFile, journal.ExactFile], None
]
ExistingBatchValidator = Callable[
    [Sequence[dict[str, object]]], None
]
ChainBatchAuthorizer = Callable[..., object]
_ACTIVE_LOCKS = threading.local()
_UNSET_SIDECAR = object()
_INTENT_TEMP_PREFIXES = (
    f"{journal.BATCH_INTENT_NAME}.",
    f".{journal.BATCH_INTENT_NAME}.",
)
_INTENT_TEMP_PATTERN = re.compile(
    rf"{re.escape(journal.BATCH_INTENT_NAME)}\.[0-9a-f]{{64}}\.tmp\Z"
)
_INTENT_TEMP_AUTHORITY_SCHEMA = "forge-journal-batch-intent-stage/1"
_INTENT_QUARANTINE_NAME = f"{journal.BATCH_INTENT_NAME}.quarantine"
_CHAIN_BATCH_AUTHORIZATION_REQUIRED = frozenset(
    {
        "registered-authorizer",
        "opaque-capability",
        "identity-binding",
        "request-binding",
        "batch-binding",
        "snapshot-binding",
    }
)
CHAIN_BATCH_AUTHORIZATION_CONTROLS = _CHAIN_BATCH_AUTHORIZATION_REQUIRED
_CHAIN_BATCH_AUTHORIZER_LOCK = threading.Lock()
_CHAIN_BATCH_AUTHORIZER: ChainBatchAuthorizer | None = None
_BATCH_GAP_REPAIR_REQUIRED = frozenset({"canonical-gap-receipt"})
BATCH_GAP_REPAIR_CONTROLS = _BATCH_GAP_REPAIR_REQUIRED
_SCOPE_CHANGE_TRANSACTION_REQUIRED = frozenset(
    {"registry-lock", "readmission-validation"}
)
SCOPE_CHANGE_TRANSACTION_CONTROLS = _SCOPE_CHANGE_TRANSACTION_REQUIRED
_BATCH_GAP_REPAIR_SCHEMA = "forge-journal-batch-gap-repair/1"
_BATCH_GAP_REPAIR_REASON = (
    "reconstructed from canonical journal bytes and byte-exact following receipt"
)


def _register_chain_batch_authorizer(
    callback: ChainBatchAuthorizer,
) -> None:
    """Register the sole task-04 capability verifier for this process."""

    global _CHAIN_BATCH_AUTHORIZER
    if not callable(callback):
        raise journal.CoordinationRefusal(journal.INVALID_JOURNAL_RECORD)
    with _CHAIN_BATCH_AUTHORIZER_LOCK:
        if _CHAIN_BATCH_AUTHORIZER is not None:
            raise journal.CoordinationRefusal(
                journal.INVALID_JOURNAL_RECORD
            )
        _CHAIN_BATCH_AUTHORIZER = callback


def _active_locks() -> dict[str, BatchLock]:
    active = getattr(_ACTIVE_LOCKS, "values", None)
    if active is None:
        active = {}
        _ACTIVE_LOCKS.values = active
    return active


def normalized_request(
    repository: Path,
    run_id: str,
    verb: str,
    inputs: dict[str, object],
) -> tuple[dict[str, object], str]:
    request = {
        "schema": journal.BATCH_REQUEST_SCHEMA,
        "verb": verb,
        "repository": str(repository),
        "run_id": run_id,
        "inputs": inputs,
    }
    return request, journal._sha256(journal._canonical_json_bytes(request))


def validate_idempotency_key(value: object) -> str:
    if (
        not isinstance(value, str)
        or journal.HEX_SHA256_PATTERN.fullmatch(value) is None
    ):
        raise journal.CoordinationRefusal(journal.BATCH_KEY_REFUSAL)
    return value


def _regular_stat(value: os.stat_result) -> bool:
    return (
        stat.S_ISREG(value.st_mode)
        and not stat.S_ISLNK(value.st_mode)
        and value.st_nlink == 1
        and value.st_uid == os.geteuid()
    )


def _observation(value: os.stat_result) -> journal.FileObservation:
    return journal.FileObservation(value.st_dev, value.st_ino, value.st_mode)


def _same(value: os.stat_result, expected: journal.FileObservation) -> bool:
    return _regular_stat(value) and _observation(value) == expected


def _safe_open_flags(flags: int, *, nonblocking: bool = False) -> int:
    """Return fail-closed flags for a name that may be attacker-controlled."""

    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    result = flags | nofollow | getattr(os, "O_CLOEXEC", 0)
    if nonblocking:
        nonblock = getattr(os, "O_NONBLOCK", None)
        if nonblock is None:
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        result |= nonblock
    return result


def _fsync_directory(descriptor: int) -> None:
    os.fsync(descriptor)


def _write_all(descriptor: int, payload: bytes) -> None:
    remaining = memoryview(payload)
    while remaining:
        count = os.write(descriptor, remaining)
        if count <= 0:
            raise OSError("short journal batch write")
        remaining = remaining[count:]


def _create_empty_at(
    directory_descriptor: int, name: str
) -> journal.FileObservation:
    descriptor = os.open(
        name,
        _safe_open_flags(os.O_WRONLY | os.O_CREAT | os.O_EXCL),
        0o600,
        dir_fd=directory_descriptor,
    )
    try:
        os.fsync(descriptor)
        opened = os.fstat(descriptor)
        rebound = os.stat(
            name, dir_fd=directory_descriptor, follow_symlinks=False
        )
        created = _observation(opened)
        if (
            not _regular_stat(opened)
            or not _same(rebound, created)
            or opened.st_size != 0
            or rebound.st_size != 0
        ):
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    finally:
        os.close(descriptor)
    _fsync_directory(directory_descriptor)
    return created


def _validate_named_file(
    directory_descriptor: int, name: str
) -> tuple[os.stat_result, journal.FileObservation]:
    value = os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False)
    if not _regular_stat(value):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    return value, _observation(value)


def _read_named_file(
    directory_descriptor: int, name: str
) -> tuple[bytes, journal.FileObservation]:
    before, observed = _validate_named_file(directory_descriptor, name)
    descriptor = os.open(
        name,
        _safe_open_flags(os.O_RDONLY, nonblocking=True),
        dir_fd=directory_descriptor,
    )
    try:
        if not _same(os.fstat(descriptor), observed):
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        raw = journal._read_descriptor(descriptor)
        after = os.fstat(descriptor)
        rebound = os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False)
        if (
            not _same(after, observed)
            or not _same(rebound, observed)
            or len(raw) != before.st_size
            or after.st_size != before.st_size
            or rebound.st_size != before.st_size
        ):
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        return raw, observed
    finally:
        os.close(descriptor)


def _append_named_file(
    locked: BatchLock,
    name: str,
    payload: bytes,
    expected: journal.FileObservation,
    *,
    expected_size: int,
    expected_sha256: str,
    protected: Sequence[tuple[str, journal.ExactFile]] = (),
) -> None:
    descriptor = os.open(
        name,
        _safe_open_flags(
            os.O_RDWR | os.O_APPEND, nonblocking=True
        ),
        dir_fd=locked.run_descriptor,
    )
    try:
        opened = os.fstat(descriptor)
        rebound = os.stat(
            name, dir_fd=locked.run_descriptor, follow_symlinks=False
        )
        if (
            not _same(opened, expected)
            or not _same(rebound, expected)
            or opened.st_size != expected_size
        ):
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        current = os.pread(descriptor, expected_size, 0)
        if (
            len(current) != expected_size
            or journal._sha256(current) != expected_sha256
        ):
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        _validate_batch_lock(locked)
        rebound = os.stat(
            name, dir_fd=locked.run_descriptor, follow_symlinks=False
        )
        if (
            not _same(os.fstat(descriptor), expected)
            or not _same(rebound, expected)
        ):
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        for protected_name, exact in protected:
            _require_exact_named_file(locked, protected_name, exact)
        _validate_batch_lock(locked)
        for protected_name, exact in protected:
            _require_exact_named_file(locked, protected_name, exact)
        _write_all(descriptor, payload)
        os.fsync(descriptor)
        after = os.fstat(descriptor)
        rebound = os.stat(
            name, dir_fd=locked.run_descriptor, follow_symlinks=False
        )
        final_size = expected_size + len(payload)
        if (
            not _same(after, expected)
            or not _same(rebound, expected)
            or after.st_size != final_size
            or rebound.st_size != final_size
        ):
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        _validate_batch_lock(locked)
        for protected_name, exact in protected:
            _require_exact_named_file(locked, protected_name, exact)
    finally:
        os.close(descriptor)


def _validate_batch_lock(locked: BatchLock) -> None:
    try:
        opened = os.fstat(locked.lock_descriptor)
        rebound = os.stat(
            journal.BATCH_LOCK_NAME,
            dir_fd=locked.run_descriptor,
            follow_symlinks=False,
        )
        run_rebound = os.lstat(locked.run_dir)
        run_opened = os.fstat(locked.run_descriptor)
    except OSError as exc:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED) from exc
    if (
        not _same(opened, locked.lock_observation)
        or not _same(rebound, locked.lock_observation)
        or _observation(run_rebound) != _observation(run_opened)
    ):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)


def _first_journal_record(run_descriptor: int) -> dict[str, object] | None:
    """Read only the historical opening object, without canonicalizing history."""

    try:
        raw, _ = _read_named_file(run_descriptor, "journal.jsonl")
    except FileNotFoundError:
        return None
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            opening = json.loads(line.decode("utf-8"))
        except (UnicodeError, ValueError, RecursionError):
            return None
        return opening if isinstance(opening, dict) else None
    return None


def _writer_contract_activated(run_descriptor: int) -> bool:
    opening = _first_journal_record(run_descriptor)
    return bool(
        opening is not None
        and opening.get("type") == "run_started"
        and opening.get("writer_contract") == journal.WRITER_CONTRACT
    )


def _legacy_batch_first_use(run_descriptor: int) -> bool:
    """Return whether an existing journal predates the activated sidecars."""

    opening = _first_journal_record(run_descriptor)
    return bool(
        opening is not None
        and opening.get("type") == "run_started"
        and opening.get("writer_contract") != journal.WRITER_CONTRACT
    )


def _intent_temporary_name(
    idempotency_key: object, request_sha256: object
) -> str:
    """Return the sole staging slot authorized by one normalized request."""

    if not _sha_member(idempotency_key) or not _sha_member(request_sha256):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    binding = {
        "schema": _INTENT_TEMP_AUTHORITY_SCHEMA,
        "idempotency_key": idempotency_key,
        "request_sha256": request_sha256,
    }
    digest = journal._sha256(journal._canonical_json_bytes(binding))
    return f"{journal.BATCH_INTENT_NAME}.{digest}.tmp"


def _validate_no_orphan_intent_temporary(
    locked: BatchLock,
) -> str | None:
    """Classify one request-bound stage without trusting or deleting its bytes."""

    _validate_batch_lock(locked)
    names = frozenset(os.listdir(locked.run_descriptor))
    if _INTENT_QUARANTINE_NAME in names:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    candidate_names = tuple(
        name
        for name in names
        if name.endswith(".tmp")
        and any(name.startswith(prefix) for prefix in _INTENT_TEMP_PREFIXES)
    )
    if not candidate_names:
        _validate_batch_lock(locked)
        return None
    if (
        len(candidate_names) != 1
        or _INTENT_TEMP_PATTERN.fullmatch(candidate_names[0]) is None
        or journal.BATCH_INTENT_NAME in names
    ):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    candidate = candidate_names[0]
    _validate_named_file(locked.run_descriptor, candidate)
    if frozenset(os.listdir(locked.run_descriptor)) != names:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    _validate_batch_lock(locked)
    return candidate


def _matching_intent_temporary(
    locked: BatchLock,
    idempotency_key: object,
    request_sha256: object,
) -> str | None:
    staged = _validate_no_orphan_intent_temporary(locked)
    if staged is None:
        return None
    if staged != _intent_temporary_name(idempotency_key, request_sha256):
        raise journal.CoordinationRefusal(journal.BATCH_PENDING)
    return staged


@contextmanager
def batch_lock(run_dir: Path, *, create: bool) -> Iterator[BatchLock]:
    key = os.path.abspath(os.fspath(run_dir))
    active = _active_locks()
    if key in active:
        _validate_no_orphan_intent_temporary(active[key])
        yield active[key]
        return
    run_descriptor: int | None = None
    lock_descriptor: int | None = None
    try:
        run_descriptor, _ = journal._open_bound_directory(run_dir)
        try:
            _, lock_observation = _validate_named_file(
                run_descriptor, journal.BATCH_LOCK_NAME
            )
        except FileNotFoundError:
            if not create or not _legacy_batch_first_use(run_descriptor):
                raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
            _create_empty_at(run_descriptor, journal.BATCH_LOCK_NAME)
            _, lock_observation = _validate_named_file(
                run_descriptor, journal.BATCH_LOCK_NAME
            )
        lock_descriptor = os.open(
            journal.BATCH_LOCK_NAME,
            _safe_open_flags(os.O_RDWR, nonblocking=True),
            dir_fd=run_descriptor,
        )
        if not _same(os.fstat(lock_descriptor), lock_observation):
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
        locked = BatchLock(
            run_dir, run_descriptor, lock_descriptor, lock_observation
        )
        _validate_batch_lock(locked)
        _validate_no_orphan_intent_temporary(locked)
        journal._mark_batch_lock(run_dir, held=True)
        active[key] = locked
        try:
            yield locked
        finally:
            active.pop(key, None)
            journal._mark_batch_lock(run_dir, held=False)
    except FileNotFoundError:
        if run_descriptor is None:
            raise
        raise journal.CoordinationRefusal(
            journal.BATCH_DIVERGED
        ) from None
    except journal.CoordinationRefusal:
        raise
    except OSError as exc:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED) from exc
    finally:
        if lock_descriptor is not None:
            try:
                fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
            except OSError:
                pass
            os.close(lock_descriptor)
        if run_descriptor is not None:
            os.close(run_descriptor)


def _canonical_sidecar(value: dict[str, object]) -> bytes:
    return journal._canonical_json_bytes(value) + b"\n"


def _decode_base64url(value: object) -> bytes:
    if not isinstance(value, str) or "=" in value:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    try:
        raw = value.encode("ascii")
        decoded = base64.b64decode(
            raw + b"=" * (-len(raw) % 4), altchars=b"-_", validate=True
        )
        if _encode_base64url(decoded) != value:
            raise ValueError("noncanonical base64url")
        return decoded
    except (UnicodeError, ValueError, binascii.Error) as exc:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED) from exc


def _encode_base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _intent_keys() -> set[str]:
    return {
        "schema",
        "idempotency_key",
        "request_sha256",
        "base_size",
        "base_sha256",
        "record_count",
        "batch_bytes",
        "batch_sha256",
        "receipt_base_size",
        "receipt_base_sha256",
        "receipt_bytes",
    }


def _receipt_keys() -> set[str]:
    return {
        "schema",
        "idempotency_key",
        "request_sha256",
        "base_size",
        "batch_sha256",
        "record_count",
        "journal_size",
        "journal_sha256",
        "recorded_at",
    }


def _repair_receipt_keys() -> set[str]:
    return _receipt_keys() | {"repaired", "repair_reason"}


def _sha_member(value: object) -> bool:
    return isinstance(value, str) and journal.HEX_SHA256_PATTERN.fullmatch(value) is not None


def _validate_intent(value: object) -> dict[str, object]:
    if (
        not isinstance(value, dict)
        or set(value) != _intent_keys()
        or value.get("schema") != journal.BATCH_INTENT_SCHEMA
        or not all(
            _sha_member(value.get(name))
            for name in (
                "idempotency_key",
                "request_sha256",
                "base_sha256",
                "batch_sha256",
                "receipt_base_sha256",
            )
        )
        or any(
            type(value.get(name)) is not int or int(value[name]) < 0
            for name in ("base_size", "record_count", "receipt_base_size")
        )
    ):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    batch_bytes = _decode_base64url(value.get("batch_bytes"))
    receipt_bytes = _decode_base64url(value.get("receipt_bytes"))
    if (
        not batch_bytes
        or not batch_bytes.endswith(b"\n")
        or not receipt_bytes
        or not receipt_bytes.endswith(b"\n")
        or journal._sha256(batch_bytes) != value["batch_sha256"]
    ):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    records = _records_from_batch(batch_bytes)
    if len(records) != value["record_count"] or not records:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    try:
        receipt_value = json.loads(receipt_bytes.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED) from exc
    receipt = _validate_receipt(receipt_value)
    if (
        set(receipt) != _receipt_keys()
        or receipt_bytes != _canonical_sidecar(receipt)
        or receipt["idempotency_key"] != value["idempotency_key"]
        or receipt["request_sha256"] != value["request_sha256"]
        or receipt["base_size"] != value["base_size"]
        or receipt["batch_sha256"] != value["batch_sha256"]
        or receipt["record_count"] != value["record_count"]
        or receipt["journal_size"] != int(value["base_size"]) + len(batch_bytes)
    ):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    return value


def _validate_receipt(value: object) -> dict[str, object]:
    keys = set(value) if isinstance(value, dict) else set()
    repair = keys == _repair_receipt_keys()
    if (
        not isinstance(value, dict)
        or keys not in (_receipt_keys(), _repair_receipt_keys())
        or value.get("schema") != journal.BATCH_RECEIPT_SCHEMA
        or any(
            not _sha_member(value.get(name))
            for name in (
                "idempotency_key",
                "request_sha256",
                "batch_sha256",
                "journal_sha256",
            )
        )
        or any(
            type(value.get(name)) is not int or int(value[name]) < 0
            for name in ("base_size", "record_count", "journal_size")
        )
        or not isinstance(value.get("recorded_at"), str)
        or not journal._valid_utc(str(value["recorded_at"]))
        or int(value.get("record_count", 0)) <= 0
        or int(value.get("base_size", 0)) > int(value.get("journal_size", 0))
        or (
            repair
            and (
                value.get("repaired") is not True
                or value.get("repair_reason") != _BATCH_GAP_REPAIR_REASON
            )
        )
    ):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    return value


def _validate_batch_surface_path(
    locked: BatchLock,
    *,
    surface: CommitmentPathSurface,
    name: str,
) -> None:
    if validate_surface_path(
        surface,
        name,
        repository=locked.run_dir,
        run_dir=locked.run_dir,
        direct_parent=locked.run_dir,
    ) is None:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)


def _load_intent(
    locked: BatchLock,
) -> tuple[dict[str, object], journal.FileObservation] | None:
    _validate_batch_surface_path(
        locked,
        surface=_BATCH_INTENT_SURFACE,
        name=journal.BATCH_INTENT_NAME,
    )
    _refuse_intent_quarantine(locked)
    try:
        raw, observed = _read_named_file(
            locked.run_descriptor, journal.BATCH_INTENT_NAME
        )
    except FileNotFoundError:
        return None
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED) from exc
    intent = _validate_intent(value)
    if raw != _canonical_sidecar(intent):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    return intent, observed


def _ensure_receipt_ledger(
    locked: BatchLock, *, allow_preintent: bool = False
) -> None:
    _validate_batch_surface_path(
        locked,
        surface=_BATCH_RECEIPT_SURFACE,
        name=journal.BATCH_RECEIPTS_NAME,
    )
    try:
        _validate_named_file(locked.run_descriptor, journal.BATCH_RECEIPTS_NAME)
    except FileNotFoundError:
        if not allow_preintent and not _legacy_batch_first_use(
            locked.run_descriptor
        ):
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        _validate_batch_lock(locked)
        _create_empty_at(
            locked.run_descriptor, journal.BATCH_RECEIPTS_NAME
        )
        _validate_batch_lock(locked)
        _validate_named_file(
            locked.run_descriptor, journal.BATCH_RECEIPTS_NAME
        )


def _load_receipts(
    locked: BatchLock,
    *,
    create: bool = False,
) -> tuple[
    list[dict[str, object]], bytes, journal.FileObservation | None
]:
    _validate_batch_surface_path(
        locked,
        surface=_BATCH_RECEIPT_SURFACE,
        name=journal.BATCH_RECEIPTS_NAME,
    )
    try:
        raw, observed = _read_named_file(
            locked.run_descriptor, journal.BATCH_RECEIPTS_NAME
        )
    except FileNotFoundError:
        if not create:
            if _writer_contract_activated(locked.run_descriptor):
                raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
            return [], b"", None
        _ensure_receipt_ledger(locked)
        raw, observed = _read_named_file(
            locked.run_descriptor, journal.BATCH_RECEIPTS_NAME
        )
    if raw and not raw.endswith(b"\n"):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    receipts = _parse_receipt_lines(raw)
    activated = _writer_contract_activated(locked.run_descriptor)
    if activated and not receipts:
        journal_raw, _ = _read_named_file(
            locked.run_descriptor, "journal.jsonl"
        )
        if journal_raw:
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    _validate_receipt_chain(receipts, require_zero_base=activated)
    for receipt in receipts:
        _verify_receipt_journal(locked, receipt)
    _validate_repair_receipts(locked, receipts)
    return receipts, raw, observed


def _parse_receipt_lines(raw: bytes) -> list[dict[str, object]]:
    """Decode complete canonical receipt lines without assuming continuity."""

    receipts: list[dict[str, object]] = []
    for line in raw.splitlines(keepends=True):
        try:
            value = json.loads(line.decode("utf-8"))
        except (UnicodeError, ValueError, RecursionError) as exc:
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED) from exc
        receipt = _validate_receipt(value)
        if line != _canonical_sidecar(receipt):
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        receipts.append(receipt)
    return receipts


def _validate_receipt_chain(
    receipts: Sequence[dict[str, object]], *, require_zero_base: bool = False
) -> None:
    """Validate the logical chain, including append-only backfill receipts."""

    if require_zero_base and receipts and int(receipts[0]["base_size"]) != 0:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)

    keys: set[str] = set()
    for receipt in receipts:
        key = str(receipt["idempotency_key"])
        if key in keys:
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        keys.add(key)

    repair_entries = [
        (index, receipt)
        for index, receipt in enumerate(receipts)
        if receipt.get("repaired") is True
    ]
    if not repair_entries:
        previous_journal_size: int | None = None
        for receipt in receipts:
            if (
                previous_journal_size is not None
                and receipt["base_size"] != previous_journal_size
            ):
                raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
            previous_journal_size = int(receipt["journal_size"])
        return

    normal_entries = [
        (index, receipt)
        for index, receipt in enumerate(receipts)
        if receipt.get("repaired") is not True
    ]
    previous_normal_end: int | None = None
    for _index, receipt in normal_entries:
        base_size = int(receipt["base_size"])
        if previous_normal_end is not None and base_size < previous_normal_end:
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        previous_normal_end = int(receipt["journal_size"])

    ordered = sorted(
        receipts,
        key=lambda receipt: (
            int(receipt["base_size"]),
            int(receipt["journal_size"]),
        ),
    )
    previous_journal_size = None
    for receipt in ordered:
        if (
            previous_journal_size is not None
            and int(receipt["base_size"]) != previous_journal_size
        ):
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        previous_journal_size = int(receipt["journal_size"])

    for repair_index, repair in repair_entries:
        if not any(
            normal_index < repair_index
            and int(candidate["base_size"])
            == int(repair["journal_size"])
            for normal_index, candidate in normal_entries
        ):
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)


def _repair_receipt_value(
    *,
    repository: str,
    run_id: str,
    gap_base: int,
    gap_end: int,
    gap_bytes: bytes,
    following: dict[str, object],
    journal_raw: bytes,
) -> dict[str, object]:
    """Derive the sole canonical repair receipt from durable evidence."""

    gap_records = _records_from_batch(gap_bytes)
    if len(gap_records) != 1 or gap_records[0].get("run_id") != run_id:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    repair_identity = {
        "schema": _BATCH_GAP_REPAIR_SCHEMA,
        "repository": repository,
        "run_id": run_id,
        "base_size": gap_base,
        "journal_size": gap_end,
        "batch_sha256": journal._sha256(gap_bytes),
        "record_count": 1,
        "following_idempotency_key": following["idempotency_key"],
    }
    repair_key = journal._sha256(
        journal._canonical_json_bytes(repair_identity)
    )
    repair_request = {
        "schema": journal.BATCH_REQUEST_SCHEMA,
        "verb": "journal batch-recover",
        "repository": repository,
        "run_id": run_id,
        "inputs": repair_identity,
    }
    repair_receipt = {
        "schema": journal.BATCH_RECEIPT_SCHEMA,
        "idempotency_key": repair_key,
        "request_sha256": journal._sha256(
            journal._canonical_json_bytes(repair_request)
        ),
        "base_size": gap_base,
        "batch_sha256": journal._sha256(gap_bytes),
        "record_count": 1,
        "journal_size": gap_end,
        "journal_sha256": journal._sha256(journal_raw[:gap_end]),
        "recorded_at": following["recorded_at"],
        "repaired": True,
        "repair_reason": _BATCH_GAP_REPAIR_REASON,
    }
    return _validate_receipt(repair_receipt)


def _validate_repair_receipts(
    locked: BatchLock, receipts: Sequence[dict[str, object]]
) -> None:
    """Re-derive every persisted repair receipt on every ledger load."""

    repair_entries = [
        (index, receipt)
        for index, receipt in enumerate(receipts)
        if receipt.get("repaired") is True
    ]
    if not repair_entries:
        return
    journal_raw, journal_observation = _read_named_file(
        locked.run_descriptor, "journal.jsonl"
    )
    try:
        state = journal._scan_run(
            locked.run_dir,
            raw=journal_raw,
            directory_observation=journal._file_observation(
                os.fstat(locked.run_descriptor)
            ),
            journal_observation=journal_observation,
        )
        repository = state.records[0]["repo"]
    except (KeyError, journal.CoordinationRefusal) as exc:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED) from exc
    if not isinstance(repository, str) or not repository:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)

    for repair_index, repair in repair_entries:
        if repair_index == 0:
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        following = receipts[repair_index - 1]
        gap_base = int(repair["base_size"])
        gap_end = int(repair["journal_size"])
        if (
            following.get("repaired") is True
            or int(following["base_size"]) != gap_end
            or int(repair["record_count"]) != 1
            or not 0 <= gap_base < gap_end <= len(journal_raw)
        ):
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        expected = _repair_receipt_value(
            repository=repository,
            run_id=state.run_id,
            gap_base=gap_base,
            gap_end=gap_end,
            gap_bytes=journal_raw[gap_base:gap_end],
            following=following,
            journal_raw=journal_raw,
        )
        if repair != expected:
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)


def _records_from_batch(value: bytes) -> tuple[dict[str, object], ...]:
    try:
        records = journal._parse_raw_records(value)
    except journal.CoordinationRefusal as exc:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED) from exc
    if b"".join(journal._journal_line(record) for record in records) != value:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    return tuple(records)


def _verify_receipt_journal(
    locked: BatchLock,
    receipt: dict[str, object],
    *,
    expected_journal: journal.ExactFile | None = None,
) -> tuple[dict[str, object], ...]:
    raw, observed = _read_named_file(
        locked.run_descriptor, "journal.jsonl"
    )
    if expected_journal is not None and (
        raw != expected_journal.payload
        or observed != expected_journal.observation
    ):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    journal_size = int(receipt["journal_size"])
    base_size = int(receipt["base_size"])
    if len(raw) < journal_size or not (0 <= base_size <= journal_size):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    prefix = raw[:journal_size]
    batch_bytes = prefix[base_size:journal_size]
    records = _records_from_batch(batch_bytes)
    if (
        journal._sha256(prefix) != receipt["journal_sha256"]
        or journal._sha256(batch_bytes) != receipt["batch_sha256"]
        or len(records) != receipt["record_count"]
    ):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    return records


def _repair_receipt_gap_locked(
    locked: BatchLock,
    intent: dict[str, object],
    intent_observation: journal.FileObservation,
    *,
    repository: Path,
    run_id: str,
) -> bool:
    """Backfill one journal-proven interior receipt gap, if present."""

    ledger_raw, ledger_observation = _read_named_file(
        locked.run_descriptor, journal.BATCH_RECEIPTS_NAME
    )
    if ledger_raw.endswith(b"\n"):
        complete_ledger = ledger_raw
        trailing = b""
    else:
        boundary = ledger_raw.rfind(b"\n") + 1
        complete_ledger = ledger_raw[:boundary]
        trailing = ledger_raw[boundary:]

    receipts = _parse_receipt_lines(complete_ledger)
    if len({str(receipt["idempotency_key"]) for receipt in receipts}) != len(
        receipts
    ):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)

    journal_raw, journal_observation = _read_named_file(
        locked.run_descriptor, "journal.jsonl"
    )
    journal_exact = journal.ExactFile(journal_raw, journal_observation)
    for receipt in receipts:
        _verify_receipt_journal(
            locked, receipt, expected_journal=journal_exact
        )

    activated = _writer_contract_activated(locked.run_descriptor)
    if activated and (
        (receipts and int(receipts[0]["base_size"]) != 0)
        or (not receipts and int(intent["base_size"]) != 0)
    ):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    if any(receipt.get("repaired") is True for receipt in receipts):
        _validate_receipt_chain(receipts, require_zero_base=activated)
        _validate_repair_receipts(locked, receipts)

    ordered = sorted(
        receipts,
        key=lambda receipt: (
            int(receipt["base_size"]),
            int(receipt["journal_size"]),
        ),
    )
    gaps: list[tuple[int, int, dict[str, object]]] = []
    previous_end: int | None = None
    for receipt in ordered:
        base_size = int(receipt["base_size"])
        if previous_end is not None:
            if base_size < previous_end:
                raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
            if base_size > previous_end:
                gaps.append((previous_end, base_size, receipt))
        previous_end = int(receipt["journal_size"])
    if not gaps:
        receipted_end = previous_end if previous_end is not None else 0
        if activated and receipted_end < int(intent["base_size"]):
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        return False
    if len(gaps) != 1 or BATCH_GAP_REPAIR_CONTROLS != _BATCH_GAP_REPAIR_REQUIRED:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)

    gap_base, gap_end, following = gaps[0]
    if (
        following is not receipts[-1]
        or int(following["journal_size"]) != len(journal_raw)
        or not 0 <= gap_base < gap_end <= len(journal_raw)
    ):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    gap_bytes = journal_raw[gap_base:gap_end]
    gap_records = _records_from_batch(gap_bytes)
    if len(gap_records) != 1:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    try:
        state = journal._scan_run(
            locked.run_dir,
            raw=journal_raw,
            directory_observation=journal._file_observation(
                os.fstat(locked.run_descriptor)
            ),
            journal_observation=journal_observation,
        )
    except journal.CoordinationRefusal as exc:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED) from exc
    if state.run_id != run_id or any(
        record.get("run_id") != run_id for record in gap_records
    ):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)

    intent_exact = journal.ExactFile(
        _canonical_sidecar(intent), intent_observation
    )
    _require_exact_named_file(
        locked, journal.BATCH_INTENT_NAME, intent_exact
    )
    intended_batch = _decode_base64url(intent["batch_bytes"])
    intended_base = int(intent["base_size"])
    intended_end = intended_base + len(intended_batch)
    following_line = _canonical_sidecar(following)
    intended_receipt = _decode_base64url(intent["receipt_bytes"])
    line_offset = 0
    following_offset: int | None = None
    for receipt in receipts:
        line = _canonical_sidecar(receipt)
        if receipt is following:
            following_offset = line_offset
        line_offset += len(line)
    if (
        intended_base != gap_end
        or intended_end != len(journal_raw)
        or journal_raw[intended_base:intended_end] != intended_batch
        or journal._sha256(journal_raw[:intended_base])
        != intent["base_sha256"]
        or intended_receipt != following_line
        or following_offset is None
        or intent["receipt_base_size"] != following_offset
        or journal._sha256(complete_ledger[:following_offset])
        != intent["receipt_base_sha256"]
    ):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)

    try:
        recorded_repository = state.records[0]["repo"]
    except KeyError as exc:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED) from exc
    if recorded_repository != str(repository):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    repair_receipt = _repair_receipt_value(
        repository=str(recorded_repository),
        run_id=run_id,
        gap_base=gap_base,
        gap_end=gap_end,
        gap_bytes=gap_bytes,
        following=following,
        journal_raw=journal_raw,
    )
    repair_key = str(repair_receipt["idempotency_key"])
    if any(
        receipt.get("idempotency_key") == repair_key
        for receipt in receipts
    ):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    repair_bytes = _canonical_sidecar(repair_receipt)
    if trailing and not repair_bytes.startswith(trailing):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)

    ledger_exact = journal.ExactFile(ledger_raw, ledger_observation)
    repaired_ledger = _append_missing_prefix(
        locked,
        journal.BATCH_RECEIPTS_NAME,
        len(complete_ledger),
        journal._sha256(complete_ledger),
        repair_bytes,
        expected_file=ledger_exact,
        protected=(
            ("journal.jsonl", journal_exact),
            (journal.BATCH_INTENT_NAME, intent_exact),
        ),
    )
    loaded, loaded_raw, loaded_observation = _load_receipts(locked)
    if (
        loaded_raw != repaired_ledger.payload
        or loaded_observation != repaired_ledger.observation
        or sum(
            receipt.get("idempotency_key") == repair_key
            for receipt in loaded
        )
        != 1
    ):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    return True


def _matching_receipt(
    locked: BatchLock,
    idempotency_key: str,
    request_sha256: str,
) -> BatchOutcome | None:
    receipts, _, _ = _load_receipts(locked)
    matches = [
        receipt
        for receipt in receipts
        if receipt.get("idempotency_key") == idempotency_key
    ]
    if len(matches) > 1:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    if not matches:
        return None
    receipt = matches[0]
    if receipt.get("request_sha256") != request_sha256:
        raise journal.CoordinationRefusal(journal.BATCH_KEY_CONFLICT)
    records = _verify_receipt_journal(locked, receipt)
    return BatchOutcome(receipt, records, True)


def _finalize_lifecycle_registry(
    repository: Path,
    run_id: str,
    records: Sequence[dict[str, object]],
) -> None:
    lifecycle = [
        record.get("type") for record in records if record.get("type") in {"run_started", "run_closed"}
    ]
    if lifecycle not in (["run_started"], ["run_closed"]):
        return
    _, state_root = journal._resolve_repository(repository, "journal batch")
    with journal._registry_lock(state_root) as registry_lock:
        snapshot = journal._read_registry_snapshot(state_root, locked=registry_lock)
        states, _placeholders, _owners, runs_root_observation = journal._classify_runs(
            state_root,
            frozenset(snapshot.open_runs),
            owner_target_ids=frozenset({run_id}),
        )
        state = states.get(run_id)
        expected_disposition = "open" if lifecycle == ["run_started"] else "closed"
        if state is None or state.disposition != expected_disposition:
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        try:
            reservations = journal._derive_reservations(states)
        except journal.CoordinationRefusal as exc:
            raise journal.CoordinationRefusal(
                journal.BATCH_DIVERGED
            ) from exc
        expected = {
            candidate_id: candidate.scope
            for candidate_id, candidate in states.items()
            if candidate.disposition == "open" and not candidate.pre_coordination
        }
        if lifecycle == ["run_closed"] and state.was_retired:
            if (
                state.successor_of is None
                or run_id in reservations
                or snapshot.open_runs != expected
            ):
                raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
            return
        if snapshot.open_runs == expected:
            return
        actual_other = {
            candidate_id: scope
            for candidate_id, scope in snapshot.open_runs.items()
            if candidate_id != run_id
        }
        expected_other = {
            candidate_id: scope
            for candidate_id, scope in expected.items()
            if candidate_id != run_id
        }
        if actual_other != expected_other:
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        if lifecycle == ["run_started"]:
            if run_id in snapshot.open_runs or expected.get(run_id) != state.scope:
                raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        elif snapshot.open_runs.get(run_id) != state.scope or run_id in expected:
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        try:
            journal._write_registry(
                state_root,
                expected,
                locked=registry_lock,
                expected_runs_root=runs_root_observation,
            )
        except journal.CoordinationRefusal as exc:
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED) from exc


def _require_exact_named_file(
    locked: BatchLock, name: str, expected: journal.ExactFile
) -> None:
    if name == journal.BATCH_INTENT_NAME:
        _refuse_intent_quarantine(locked)
    raw, observed = _read_named_file(locked.run_descriptor, name)
    if raw != expected.payload or observed != expected.observation:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)


def _optional_exact_named_file(
    locked: BatchLock, name: str
) -> journal.ExactFile | None:
    if name == journal.BATCH_INTENT_NAME:
        _refuse_intent_quarantine(locked)
    try:
        raw, observed = _read_named_file(locked.run_descriptor, name)
    except FileNotFoundError:
        return None
    return journal.ExactFile(raw, observed)


def _require_named_snapshot(
    locked: BatchLock,
    name: str,
    expected: journal.ExactFile | None,
) -> None:
    current = _optional_exact_named_file(locked, name)
    if current != expected:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)


def _refuse_intent_quarantine(locked: BatchLock) -> None:
    """Treat the durable publication-failure marker as permanent divergence."""

    _validate_batch_lock(locked)
    names = frozenset(os.listdir(locked.run_descriptor))
    if _INTENT_QUARANTINE_NAME in names:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    if frozenset(os.listdir(locked.run_descriptor)) != names:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    _validate_batch_lock(locked)


def _quarantine_published_intent(
    locked: BatchLock,
    suspect: journal.ExactFile | None,
) -> None:
    """Move a rejected canonical name aside without deleting any bytes."""

    _validate_batch_lock(locked)
    before = frozenset(os.listdir(locked.run_descriptor))
    if (
        _INTENT_QUARANTINE_NAME in before
        or journal.BATCH_INTENT_NAME not in before
    ):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    expected = (
        before - {journal.BATCH_INTENT_NAME}
    ) | {_INTENT_QUARANTINE_NAME}
    try:
        journal._move_name_noreplace_at(
            locked.run_descriptor,
            journal.BATCH_INTENT_NAME,
            _INTENT_QUARANTINE_NAME,
        )
        _fsync_directory(locked.run_descriptor)
    except OSError as exc:
        raise journal.CoordinationRefusal(
            journal.BATCH_DIVERGED
        ) from exc
    _validate_batch_lock(locked)
    after = frozenset(os.listdir(locked.run_descriptor))
    if after != expected:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    if suspect is None:
        _validate_named_file(
            locked.run_descriptor, _INTENT_QUARANTINE_NAME
        )
    else:
        _require_exact_named_file(
            locked, _INTENT_QUARANTINE_NAME, suspect
        )
    if frozenset(os.listdir(locked.run_descriptor)) != after:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    _validate_batch_lock(locked)


def _write_intent(
    locked: BatchLock,
    intent: dict[str, object],
) -> journal.ExactFile:
    """Publish exact bytes from a request-bound, zero-authority staging slot."""

    payload = _canonical_sidecar(intent)
    temporary = _intent_temporary_name(
        intent.get("idempotency_key"), intent.get("request_sha256")
    )
    descriptor: int | None = None
    temporary_observation: journal.FileObservation | None = None
    staged_exact: journal.ExactFile | None = None
    moved = False
    suspect: journal.ExactFile | None = None
    publication_failed = False
    try:
        staged = _matching_intent_temporary(
            locked,
            intent.get("idempotency_key"),
            intent.get("request_sha256"),
        )
        if _optional_exact_named_file(
            locked, journal.BATCH_INTENT_NAME
        ) is not None:
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        if staged is None:
            descriptor = os.open(
                temporary,
                _safe_open_flags(os.O_RDWR | os.O_CREAT | os.O_EXCL),
                0o600,
                dir_fd=locked.run_descriptor,
            )
        else:
            _, temporary_observation = _validate_named_file(
                locked.run_descriptor, temporary
            )
            descriptor = os.open(
                temporary,
                _safe_open_flags(os.O_RDWR, nonblocking=True),
                dir_fd=locked.run_descriptor,
            )
        opened = os.fstat(descriptor)
        if temporary_observation is None:
            temporary_observation = _observation(opened)
        rebound = os.stat(
            temporary,
            dir_fd=locked.run_descriptor,
            follow_symlinks=False,
        )
        if not _same(opened, temporary_observation) or not _same(
            rebound, temporary_observation
        ):
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        _validate_batch_lock(locked)
        if (
            _matching_intent_temporary(
                locked,
                intent.get("idempotency_key"),
                intent.get("request_sha256"),
            )
            != temporary
            or _optional_exact_named_file(
                locked, journal.BATCH_INTENT_NAME
            )
            is not None
        ):
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)

        # Bytes left by a dead writer are not an intent and are never parsed or
        # promoted.  The freshly authorized caller owns only this deterministic
        # request slot, so it rewrites the same bound inode from offset zero.
        os.ftruncate(descriptor, 0)
        os.lseek(descriptor, 0, os.SEEK_SET)
        _write_all(descriptor, payload)
        os.fsync(descriptor)
        opened = os.fstat(descriptor)
        rebound = os.stat(
            temporary,
            dir_fd=locked.run_descriptor,
            follow_symlinks=False,
        )
        if (
            not _same(opened, temporary_observation)
            or not _same(rebound, temporary_observation)
            or opened.st_size != len(payload)
            or rebound.st_size != len(payload)
            or journal._read_descriptor(descriptor) != payload
            or not _same(os.fstat(descriptor), temporary_observation)
        ):
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        staged_exact = journal.ExactFile(payload, temporary_observation)
        _validate_batch_lock(locked)
        if (
            _matching_intent_temporary(
                locked,
                intent.get("idempotency_key"),
                intent.get("request_sha256"),
            )
            != temporary
        ):
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        _require_exact_named_file(locked, temporary, staged_exact)
        journal._move_name_noreplace_at(
            locked.run_descriptor,
            temporary,
            journal.BATCH_INTENT_NAME,
        )
        moved = True
        try:
            _fsync_directory(locked.run_descriptor)
            _validate_batch_lock(locked)
            raw, observation = _read_named_file(
                locked.run_descriptor, journal.BATCH_INTENT_NAME
            )
            suspect = journal.ExactFile(raw, observation)
            opened = os.fstat(descriptor)
            if (
                raw != payload
                or observation != temporary_observation
                or not _same(opened, temporary_observation)
                or opened.st_size != len(payload)
                or journal._read_descriptor(descriptor) != payload
            ):
                raise journal.CoordinationRefusal(
                    journal.BATCH_DIVERGED
                )
        except BaseException:
            # Never delete a rejected published name: another actor may have
            # substituted it after the last observation.  Move whichever name
            # is present into the sole no-replace quarantine slot and retain it
            # permanently as a divergence marker.  An indeterminate move or
            # revalidation preserves all remaining names and still fails closed.
            if moved:
                publication_failed = True
                _quarantine_published_intent(locked, suspect)
            raise
        return journal.ExactFile(payload, observation)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if staged_exact is not None and not publication_failed:
            try:
                if (
                    _optional_exact_named_file(locked, temporary)
                    == staged_exact
                ):
                    os.unlink(temporary, dir_fd=locked.run_descriptor)
                    _fsync_directory(locked.run_descriptor)
            except FileNotFoundError:
                pass


def _validate_published_intent(
    expected: dict[str, object],
    stored: dict[str, object],
    observation: journal.FileObservation,
    published: object,
) -> None:
    payload = _canonical_sidecar(expected)
    if (
        stored != expected
        or not isinstance(published, journal.ExactFile)
        or payload != published.payload
        or observation != published.observation
    ):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)


def _unlink_intent(
    locked: BatchLock,
    expected: journal.ExactFile,
    *,
    protected: Sequence[tuple[str, journal.ExactFile]] = (),
) -> None:
    _require_exact_named_file(locked, journal.BATCH_INTENT_NAME, expected)
    _validate_batch_lock(locked)
    for name, exact in protected:
        _require_exact_named_file(locked, name, exact)
    _validate_batch_lock(locked)
    for name, exact in protected:
        _require_exact_named_file(locked, name, exact)
    _require_exact_named_file(
        locked, journal.BATCH_INTENT_NAME, expected
    )
    _validate_batch_lock(locked)
    os.unlink(journal.BATCH_INTENT_NAME, dir_fd=locked.run_descriptor)
    _fsync_directory(locked.run_descriptor)
    _validate_batch_lock(locked)
    for name, exact in protected:
        _require_exact_named_file(locked, name, exact)
    try:
        _validate_named_file(
            locked.run_descriptor, journal.BATCH_INTENT_NAME
        )
    except FileNotFoundError:
        return
    raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)


def _append_missing_prefix(
    locked: BatchLock,
    name: str,
    base_size: int,
    base_sha256: str,
    intended: bytes,
    *,
    append_enabled: bool = True,
    expected_file: journal.ExactFile | None | object = _UNSET_SIDECAR,
    protected: Sequence[tuple[str, journal.ExactFile]] = (),
) -> journal.ExactFile:
    current, observed = _read_named_file(locked.run_descriptor, name)
    if expected_file is not _UNSET_SIDECAR and (
        not isinstance(expected_file, journal.ExactFile)
        or current != expected_file.payload
        or observed != expected_file.observation
    ):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    if (
        len(current) < base_size
        or journal._sha256(current[:base_size]) != base_sha256
    ):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    suffix = current[base_size:]
    if len(suffix) > len(intended) or not intended.startswith(suffix):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    missing = intended[len(suffix) :]
    if missing and not append_enabled:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    if missing:
        _append_named_file(
            locked,
            name,
            missing,
            observed,
            expected_size=len(current),
            expected_sha256=journal._sha256(current),
            protected=protected,
        )
    final, final_observed = _read_named_file(locked.run_descriptor, name)
    if (
        final != current[:base_size] + intended
        or final_observed != observed
    ):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    return journal.ExactFile(final, final_observed)


def _recover_locked(
    locked: BatchLock,
    intent: dict[str, object],
    intent_observation: journal.FileObservation,
    *,
    repeated: bool,
    repository: Path | None = None,
    run_id: str | None = None,
    expected_journal: journal.ExactFile | None | object = _UNSET_SIDECAR,
    expected_receipts: journal.ExactFile | None | object = _UNSET_SIDECAR,
) -> BatchOutcome:
    _validate_batch_lock(locked)
    if expected_journal is _UNSET_SIDECAR:
        expected_journal = _optional_exact_named_file(
            locked, "journal.jsonl"
        )
    if expected_receipts is _UNSET_SIDECAR:
        expected_receipts = _optional_exact_named_file(
            locked, journal.BATCH_RECEIPTS_NAME
        )
    if expected_journal is not None and not isinstance(
        expected_journal, journal.ExactFile
    ):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    if not isinstance(expected_receipts, journal.ExactFile):
        # The durable empty ledger precedes every published intent.
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    _require_named_snapshot(
        locked,
        "journal.jsonl",
        expected_journal,
    )
    _require_named_snapshot(
        locked,
        journal.BATCH_RECEIPTS_NAME,
        expected_receipts,
    )
    intent_exact = journal.ExactFile(
        _canonical_sidecar(intent), intent_observation
    )
    _require_exact_named_file(
        locked, journal.BATCH_INTENT_NAME, intent_exact
    )
    batch_bytes = _decode_base64url(intent["batch_bytes"])
    receipt_bytes = _decode_base64url(intent["receipt_bytes"])
    records = _records_from_batch(batch_bytes)
    if len(records) != intent["record_count"]:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)

    if repository is not None and run_id is not None:
        _ensure_recovery_owner(
            locked,
            intent,
            repository,
            run_id,
            expected_journal=expected_journal,
            expected_intent=intent_exact,
        )
    _require_exact_named_file(
        locked, journal.BATCH_INTENT_NAME, intent_exact
    )
    _require_named_snapshot(
        locked, "journal.jsonl", expected_journal
    )
    _require_exact_named_file(
        locked, journal.BATCH_RECEIPTS_NAME, expected_receipts
    )

    try:
        journal_exact = _append_missing_prefix(
            locked,
            "journal.jsonl",
            int(intent["base_size"]),
            str(intent["base_sha256"]),
            batch_bytes,
            append_enabled=(
                "journal-suffix" in journal.BATCH_TRANSACTION_CONTROLS
            ),
            expected_file=expected_journal,
            protected=(
                (journal.BATCH_RECEIPTS_NAME, expected_receipts),
                (journal.BATCH_INTENT_NAME, intent_exact),
            ),
        )
    except FileNotFoundError:
        # A run-open may die after its zero-base intent is durable but before
        # the journal name is created.  Only that exact activated opening may
        # create the first same-inode journal, and only with the control live.
        if (
            "journal-suffix" not in journal.BATCH_TRANSACTION_CONTROLS
            or intent["base_size"] != 0
            or intent["base_sha256"] != journal._sha256(b"")
            or len(records) != 1
            or records[0].get("type") != "run_started"
            or records[0].get("writer_contract")
            != journal.WRITER_CONTRACT
        ):
            raise journal.CoordinationRefusal(
                journal.BATCH_DIVERGED
            ) from None
        _validate_batch_lock(locked)
        created_journal = _create_empty_at(
            locked.run_descriptor, "journal.jsonl"
        )
        _validate_batch_lock(locked)
        journal_exact = _append_missing_prefix(
            locked,
            "journal.jsonl",
            0,
            journal._sha256(b""),
            batch_bytes,
            expected_file=journal.ExactFile(b"", created_journal),
            protected=(
                (journal.BATCH_RECEIPTS_NAME, expected_receipts),
                (journal.BATCH_INTENT_NAME, intent_exact),
            ),
        )

    _require_exact_named_file(
        locked, "journal.jsonl", journal_exact
    )
    receipt_base_size = int(intent["receipt_base_size"])
    receipt_suffix = expected_receipts.payload[receipt_base_size:]
    if len(receipt_suffix) > len(receipt_bytes):
        if (
            journal._sha256(
                expected_receipts.payload[:receipt_base_size]
            )
            != intent["receipt_base_sha256"]
            or not receipt_suffix.startswith(receipt_bytes)
        ):
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        _load_receipts(locked)
        receipt_exact = expected_receipts
    else:
        receipt_exact = _append_missing_prefix(
            locked,
            journal.BATCH_RECEIPTS_NAME,
            receipt_base_size,
            str(intent["receipt_base_sha256"]),
            receipt_bytes,
            append_enabled=(
                "receipt" in journal.BATCH_TRANSACTION_CONTROLS
            ),
            expected_file=expected_receipts,
            protected=(
                ("journal.jsonl", journal_exact),
                (journal.BATCH_INTENT_NAME, intent_exact),
            ),
        )

    try:
        receipt_value = json.loads(receipt_bytes.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED) from exc
    receipt = _validate_receipt(receipt_value)
    if (
        set(receipt) != _receipt_keys()
        or receipt_bytes != _canonical_sidecar(receipt)
    ):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    if (
        receipt["idempotency_key"] != intent["idempotency_key"]
        or receipt["request_sha256"] != intent["request_sha256"]
        or receipt["base_size"] != intent["base_size"]
        or receipt["batch_sha256"] != intent["batch_sha256"]
        or receipt["record_count"] != intent["record_count"]
    ):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    _verify_receipt_journal(
        locked, receipt, expected_journal=journal_exact
    )
    receipts, ledger_bytes, ledger_observation = _load_receipts(locked)
    if (
        ledger_observation is None
        or ledger_bytes != receipt_exact.payload
        or ledger_observation != receipt_exact.observation
        or sum(
            candidate.get("idempotency_key")
            == receipt["idempotency_key"]
            for candidate in receipts
        )
        != 1
    ):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    _require_exact_named_file(
        locked, "journal.jsonl", journal_exact
    )
    _require_exact_named_file(
        locked, journal.BATCH_RECEIPTS_NAME, receipt_exact
    )
    _require_exact_named_file(
        locked, journal.BATCH_INTENT_NAME, intent_exact
    )
    if "intent" not in journal.BATCH_TRANSACTION_CONTROLS:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    _unlink_intent(
        locked,
        intent_exact,
        protected=(
            (journal.BATCH_RECEIPTS_NAME, receipt_exact),
            ("journal.jsonl", journal_exact),
        ),
    )
    if repository is not None and run_id is not None:
        _finalize_lifecycle_registry(repository, run_id, records)
    return BatchOutcome(receipt, records, repeated)


def _recover_current_locked(
    locked: BatchLock,
    intent: dict[str, object],
    intent_observation: journal.FileObservation,
    *,
    repeated: bool,
    repository: Path | None = None,
    run_id: str | None = None,
    expected_journal: journal.ExactFile | None | object = _UNSET_SIDECAR,
    expected_receipts: journal.ExactFile | None | object = _UNSET_SIDECAR,
) -> BatchOutcome:
    """Bind every present sidecar before entering the recovery state machine."""

    if expected_journal is _UNSET_SIDECAR:
        expected_journal = _optional_exact_named_file(
            locked, "journal.jsonl"
        )
    if expected_receipts is _UNSET_SIDECAR:
        expected_receipts = _optional_exact_named_file(
            locked, journal.BATCH_RECEIPTS_NAME
        )
    return _recover_locked(
        locked,
        intent,
        intent_observation,
        repeated=repeated,
        repository=repository,
        run_id=run_id,
        expected_journal=expected_journal,
        expected_receipts=expected_receipts,
    )


def _prepare_intent(
    locked: BatchLock,
    idempotency_key: str,
    request_sha256: str,
    records: Sequence[dict[str, object]],
) -> tuple[
    dict[str, object],
    dict[str, object],
    journal.ExactFile,
    journal.ExactFile,
]:
    journal_bytes, journal_observation = _read_named_file(
        locked.run_descriptor, "journal.jsonl"
    )
    batch_bytes = b"".join(journal._journal_line(record) for record in records)
    if not records or not batch_bytes:
        raise journal.CoordinationRefusal(journal.INVALID_JOURNAL_RECORD)
    receipts, ledger_bytes, ledger_observation = _load_receipts(
        locked, create=True
    )
    if ledger_observation is None:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    if _writer_contract_activated(locked.run_descriptor) and (
        not receipts
        or max(int(receipt["journal_size"]) for receipt in receipts)
        != len(journal_bytes)
    ):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    journal_exact = journal.ExactFile(
        journal_bytes, journal_observation
    )
    ledger_exact = journal.ExactFile(ledger_bytes, ledger_observation)
    receipt = {
        "schema": journal.BATCH_RECEIPT_SCHEMA,
        "idempotency_key": idempotency_key,
        "request_sha256": request_sha256,
        "base_size": len(journal_bytes),
        "batch_sha256": journal._sha256(batch_bytes),
        "record_count": len(records),
        "journal_size": len(journal_bytes) + len(batch_bytes),
        "journal_sha256": journal._sha256(journal_bytes + batch_bytes),
        "recorded_at": journal._utc_now(),
    }
    receipt_bytes = _canonical_sidecar(receipt)
    intent = {
        "schema": journal.BATCH_INTENT_SCHEMA,
        "idempotency_key": idempotency_key,
        "request_sha256": request_sha256,
        "base_size": len(journal_bytes),
        "base_sha256": journal._sha256(journal_bytes),
        "record_count": len(records),
        "batch_bytes": _encode_base64url(batch_bytes),
        "batch_sha256": journal._sha256(batch_bytes),
        "receipt_base_size": len(ledger_bytes),
        "receipt_base_sha256": journal._sha256(ledger_bytes),
        "receipt_bytes": _encode_base64url(receipt_bytes),
    }
    _require_exact_named_file(locked, "journal.jsonl", journal_exact)
    _require_exact_named_file(
        locked, journal.BATCH_RECEIPTS_NAME, ledger_exact
    )
    return intent, receipt, journal_exact, ledger_exact


def prepare_open_artifacts(
    repository: Path,
    run_id: str,
    *,
    idempotency_key: str,
    inputs: dict[str, object],
    opening: dict[str, object],
) -> tuple[bytes, bytes]:
    """Construct the immutable zero-base run-open intent and receipt."""

    key = validate_idempotency_key(idempotency_key)
    _, request_sha256 = normalized_request(
        repository, run_id, "run-open", inputs
    )
    opening_bytes = journal._journal_line(opening)
    receipt = {
        "schema": journal.BATCH_RECEIPT_SCHEMA,
        "idempotency_key": key,
        "request_sha256": request_sha256,
        "base_size": 0,
        "batch_sha256": journal._sha256(opening_bytes),
        "record_count": 1,
        "journal_size": len(opening_bytes),
        "journal_sha256": journal._sha256(opening_bytes),
        "recorded_at": journal._utc_now(),
    }
    receipt_bytes = _canonical_sidecar(receipt)
    intent = {
        "schema": journal.BATCH_INTENT_SCHEMA,
        "idempotency_key": key,
        "request_sha256": request_sha256,
        "base_size": 0,
        "base_sha256": journal._sha256(b""),
        "record_count": 1,
        "batch_bytes": _encode_base64url(opening_bytes),
        "batch_sha256": journal._sha256(opening_bytes),
        "receipt_base_size": 0,
        "receipt_base_sha256": journal._sha256(b""),
        "receipt_bytes": _encode_base64url(receipt_bytes),
    }
    _validate_intent(intent)
    return _canonical_sidecar(intent), receipt_bytes


_OPEN_PREINTENT_NAMES = frozenset(
    {
        frozenset({journal.BATCH_LOCK_NAME}),
        frozenset(
            {journal.BATCH_LOCK_NAME, journal.BATCH_RECEIPTS_NAME}
        ),
        frozenset(
            {
                journal.BATCH_LOCK_NAME,
                journal.BATCH_RECEIPTS_NAME,
                "owner",
            }
        ),
    }
)


def _locked_names(locked: BatchLock) -> frozenset[str]:
    _validate_batch_lock(locked)
    names = frozenset(os.listdir(locked.run_descriptor))
    _validate_batch_lock(locked)
    return names


def _opening_owner_is_current(locked: BatchLock) -> bool:
    try:
        raw, _ = _read_named_file(locked.run_descriptor, "owner")
    except FileNotFoundError:
        return False
    owner = journal._parse_owner_bytes(raw)
    current = journal._session_owner()
    if owner is None or owner.host != current.host or owner.pid != current.pid:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    return True


def lookup_existing_open_batch(
    repo: Path,
    run_id: str,
    *,
    idempotency_key: str,
    inputs: dict[str, object],
) -> BatchOutcome | None:
    """Resolve a completed or intent-bearing run-open before allocation.

    An exact pre-intent creation prefix is only classified here.  It remains
    byte-identical until caller validation and fresh derived-value allocation
    complete in ``resume_open_creation``.
    """

    key = validate_idempotency_key(idempotency_key)
    run_id = journal._operation_run_id("run open", run_id)
    repository, state_root = journal._resolve_repository(repo, "run open")
    _, request_sha256 = normalized_request(
        repository, run_id, "run-open", inputs
    )
    run_dir = state_root / ".codex-orchestrator/runs" / run_id
    try:
        with batch_lock(run_dir, create=False) as locked:
            staged = _matching_intent_temporary(
                locked, key, request_sha256
            )
            names = _locked_names(locked)
            authoritative_names = (
                names - {staged} if staged is not None else names
            )
            if authoritative_names in _OPEN_PREINTENT_NAMES:
                if "owner" in names:
                    _opening_owner_is_current(locked)
                return None
            pending = _load_intent(locked)
            if pending is not None:
                intent, observed = pending
                if intent["idempotency_key"] != key:
                    raise journal.CoordinationRefusal(journal.BATCH_PENDING)
                if intent["request_sha256"] != request_sha256:
                    raise journal.CoordinationRefusal(
                        journal.BATCH_KEY_CONFLICT
                    )
                _opening_owner_is_current(locked)
                return _recover_current_locked(
                    locked,
                    intent,
                    observed,
                    repeated=True,
                    repository=repository,
                    run_id=run_id,
                )
            completed = _matching_receipt(locked, key, request_sha256)
            if completed is not None:
                _finalize_lifecycle_registry(
                    repository, run_id, completed.records
                )
            return completed
    except FileNotFoundError:
        return None


def resume_open_creation(
    repo: Path,
    run_id: str,
    *,
    intent_bytes: bytes,
) -> BatchOutcome | None:
    """Finish an exact pre-intent run-open creation prefix, if present."""

    repository, state_root = journal._resolve_repository(repo, "run open")
    run_dir = state_root / ".codex-orchestrator/runs" / run_id
    try:
        with batch_lock(run_dir, create=False) as locked:
            names = _locked_names(locked)
            try:
                value = json.loads(intent_bytes.decode("utf-8"))
            except (UnicodeError, ValueError, RecursionError) as exc:
                raise journal.CoordinationRefusal(
                    journal.BATCH_DIVERGED
                ) from exc
            intent = _validate_intent(value)
            if intent_bytes != _canonical_sidecar(intent):
                raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
            staged = _matching_intent_temporary(
                locked,
                intent.get("idempotency_key"),
                intent.get("request_sha256"),
            )
            authoritative_names = (
                names - {staged} if staged is not None else names
            )
            if authoritative_names not in _OPEN_PREINTENT_NAMES:
                return None
            if journal.BATCH_RECEIPTS_NAME not in authoritative_names:
                _ensure_receipt_ledger(locked, allow_preintent=True)
            if "owner" not in authoritative_names:
                current = journal._session_owner()
                journal._write_exclusive_at(
                    locked.run_descriptor,
                    "owner",
                    journal._owner_bytes(current),
                )
                _fsync_directory(locked.run_descriptor)
            _opening_owner_is_current(locked)
            expected_journal = _optional_exact_named_file(
                locked, "journal.jsonl"
            )
            expected_receipts = _optional_exact_named_file(
                locked, journal.BATCH_RECEIPTS_NAME
            )
            if expected_receipts is None:
                raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
            _require_named_snapshot(
                locked, "journal.jsonl", expected_journal
            )
            _require_exact_named_file(
                locked, journal.BATCH_RECEIPTS_NAME, expected_receipts
            )
            published = _write_intent(locked, intent)
            _require_named_snapshot(
                locked, "journal.jsonl", expected_journal
            )
            _require_exact_named_file(
                locked, journal.BATCH_RECEIPTS_NAME, expected_receipts
            )
            pending = _load_intent(locked)
            if pending is None:
                raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
            stored, observed = pending
            _validate_published_intent(
                intent, stored, observed, published
            )
            return _recover_current_locked(
                locked,
                stored,
                observed,
                repeated=True,
                repository=repository,
                run_id=run_id,
                expected_journal=expected_journal,
                expected_receipts=expected_receipts,
            )
    except FileNotFoundError:
        return None


def _read_only_session_owner() -> journal.Owner:
    """Resolve the phase-4 owner identity without allocating a timestamp."""

    raw_pid = os.environ.get("FORGE_SESSION_PID", "")
    if re.fullmatch(r"[1-9][0-9]*", raw_pid) is None:
        raise journal.CoordinationRefusal(journal.SESSION_PID_INVALID)
    try:
        pid = int(raw_pid)
    except (OverflowError, ValueError) as exc:
        raise journal.CoordinationRefusal(
            journal.SESSION_PID_NOT_LIVE
        ) from exc
    if journal._pid_is_live(pid) is not True:
        raise journal.CoordinationRefusal(journal.SESSION_PID_NOT_LIVE)
    try:
        host = socket.gethostname()
    except OSError as exc:
        raise journal.CoordinationRefusal(
            journal.SESSION_PID_NOT_LIVE
        ) from exc
    if not journal._safe_diagnostic_text(host):
        raise journal.CoordinationRefusal(journal.SESSION_PID_NOT_LIVE)
    # _classify_owner compares only pid/host.  The sentinel is never serialized;
    # the durable owner timestamp is allocated at the phase-8 adoption boundary.
    return journal.Owner(pid=pid, host=host, started_at="1970-01-01T00:00:00Z")


def _validate_target_lifecycle(
    state: journal.RunState, *, close: bool
) -> None:
    if state.disposition == "open" or (
        close and state.disposition == "retired"
    ):
        return
    raise journal.CoordinationRefusal(
        f"forge: journal append refused — run {state.run_id} is {state.disposition}"
    )


def _typed_binding_key(record: dict[str, object]) -> tuple[str, str] | None:
    """Return the immutable source-chain/binding identity for typed rows."""

    if record.get("type") not in {"verification", "decision"}:
        return None
    binding = record.get("binding")
    source = binding.get("source_record") if isinstance(binding, dict) else None
    chain_id = source.get("chain_id") if isinstance(source, dict) else None
    binding_id = binding.get("binding_id") if isinstance(binding, dict) else None
    if not isinstance(chain_id, str) or not isinstance(binding_id, str):
        return None
    return chain_id, binding_id


def _prevalidate_records(
    repository: Path,
    state: journal.RunState,
    records: Sequence[dict[str, object]],
    *,
    close: bool,
    defer_binding: bool = False,
    scope_change: bool = False,
) -> None:
    """Validate final IDs, relations, binding, and the projected journal."""

    if not records:
        raise journal.CoordinationRefusal(journal.INVALID_JOURNAL_RECORD)
    projected = list(state.records)
    id_fields = {
        "execution": "execution",
        "verification": "id",
        "decision": "id",
    }
    seen = {
        kind: {
            str(record[field])
            for record in projected
            if record.get("type") == kind
            and isinstance(record.get(field), str)
        }
        for kind, field in id_fields.items()
    }
    seen_bindings = {
        binding
        for record in projected
        if (binding := _typed_binding_key(record)) is not None
    }
    # Phase 3 validates caller spellings before journal state is inspected, but
    # builders and chain authorization may replace those spellings.  Apply the
    # same append-time guard unconditionally to every final record before any
    # projected-record schema validation.
    for record in records:
        journal._validate_append_citations(
            repository,
            state.run_dir,
            record,
        )
    for index, record in enumerate(records):
        journal._validate_citation_targets(record, projected)
        journal._validate_proposed_record(
            record,
            run_id=state.run_id,
            repo_root=repository,
            scope=state.scope,
            prior_records=tuple(projected),
            _defer_binding=defer_binding,
        )
        binding = _typed_binding_key(record)
        if binding is not None:
            if binding in seen_bindings:
                raise journal.CoordinationRefusal(
                    journal.DUPLICATE_CHAIN_BINDING
                )
            seen_bindings.add(binding)
        kind = record.get("type")
        if close:
            if len(records) != 1 or index != 0 or kind != "run_closed":
                raise journal.CoordinationRefusal(
                    "forge: journal append refused — lifecycle command required"
                )
        elif journal._ordinary_append_requires_lifecycle_command(record):
            readmission = bool(
                scope_change
                and len(records) == 1
                and index == 0
                and kind == "decision"
                and record.get("resolution")
                == journal.READMISSION_RESOLUTION
            )
            if not readmission:
                raise journal.CoordinationRefusal(
                    "forge: journal append refused — lifecycle command required"
                )
        if kind in seen:
            field = id_fields[str(kind)]
            record_id = record.get(field)
            if not isinstance(record_id, str) or record_id in seen[str(kind)]:
                raise journal.CoordinationRefusal(
                    f"{journal.INVALID_JOURNAL_RECORD}: {kind}.{field} must be unique"
                )
            seen[str(kind)].add(record_id)
        projected.append(record)


def _adopt_owner_before_intent(
    repository: Path,
    state_root: Path,
    run_id: str,
    *,
    close: bool,
) -> None:
    """Complete the FR-019 owner mutation boundary before intent publish."""

    current = journal._session_owner()
    with journal._registry_lock(state_root) as registry_lock:
        view = journal._coordination_view(
            state_root,
            owner_target_ids=frozenset({run_id}),
            locked=registry_lock,
        )
        state = journal._target_state(
            view,
            run_id,
            "run close" if close else "journal append",
            allow_reserving_retired_close=close,
        )
        recorded = journal._recorded_repository_root(
            state.run_dir, state_root, records=state.records
        )
        if recorded != repository:
            raise journal.CoordinationRefusal(journal.REGISTRY_UNAVAILABLE)
        with journal._locked_journal(state) as locked_journal:
            classification = journal._classify_owner(
                state,
                current,
                adopt_missing=state.pre_coordination,
                locked=locked_journal,
            )
            with journal._owner_takeover_transaction(
                state,
                current,
                classification,
                adopt_missing=state.pre_coordination,
                locked=locked_journal,
            ) as takeover:
                journal._validate_registry_lock(state_root, registry_lock)
                if (
                    journal._read_registry_snapshot(
                        state_root, locked=registry_lock
                    )
                    != view.registry
                ):
                    raise journal.CoordinationRefusal(
                        journal.REGISTRY_UNAVAILABLE
                    )
                journal._validate_owner_takeover(
                    locked_journal, takeover
                )


def _recovery_coordination_view(
    state_root: Path,
    registry_lock: journal.RegistryLock,
    target_state: journal.RunState,
    target_journal: journal.ExactFile,
    target_base: bytes,
) -> journal.CoordinationView:
    """Classify every run while substituting an authenticated target base."""

    snapshot = journal._read_registry_snapshot(
        state_root, locked=registry_lock
    )
    runs_root = state_root / ".codex-orchestrator/runs"
    root_descriptor: int | None = None
    try:
        root_descriptor, root_observation = journal._open_bound_directory(
            runs_root
        )
        if not journal._readable_mode(root_observation.mode, directory=True):
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        names = os.listdir(root_descriptor)
        states: dict[str, journal.RunState] = {}
        placeholders: dict[str, journal.PlaceholderObservation] = {}
        owners: dict[str, journal.OwnerObservation] = {}
        for name in sorted(names, key=os.fsencode):
            run_descriptor: int | None = None
            try:
                entry_stat = os.stat(
                    name, dir_fd=root_descriptor, follow_symlinks=False
                )
                if stat.S_ISREG(entry_stat.st_mode) and not name.startswith(
                    "."
                ):
                    rebound_regular = os.stat(
                        name,
                        dir_fd=root_descriptor,
                        follow_symlinks=False,
                    )
                    if journal._file_observation(
                        rebound_regular
                    ) != journal._file_observation(entry_stat):
                        raise journal.CoordinationRefusal(
                            journal.BATCH_DIVERGED
                        )
                    continue
                if (
                    not journal._safe_run_entry_name(name)
                    or name.startswith(".")
                    or not stat.S_ISDIR(entry_stat.st_mode)
                    or stat.S_ISLNK(entry_stat.st_mode)
                    or not journal._readable_mode(
                        entry_stat.st_mode, directory=True
                    )
                ):
                    raise journal.CoordinationRefusal(
                        journal.BATCH_DIVERGED
                    )
                run_descriptor, run_observation = (
                    journal._open_bound_child_directory(
                        root_descriptor, name, entry_stat
                    )
                )
                children = os.listdir(run_descriptor)
                child_names = set(children)
                has_journal = "journal.jsonl" in child_names
                has_owner = "owner" in child_names
                run_dir = runs_root / name
                if not has_journal:
                    rebound = os.stat(
                        name,
                        dir_fd=root_descriptor,
                        follow_symlinks=False,
                    )
                    if not journal._matches_observation(
                        rebound, run_observation
                    ):
                        raise journal.CoordinationRefusal(
                            journal.BATCH_DIVERGED
                        )
                    if (
                        name in snapshot.open_runs
                        or has_owner
                        or children
                        or "classify"
                        not in journal.ORPHAN_CLASSIFICATION_CONTROLS
                    ):
                        raise journal.CoordinationRefusal(
                            journal.BATCH_DIVERGED
                        )
                    placeholders[name] = journal.PlaceholderObservation(
                        path=run_dir,
                        device=run_observation.device,
                        inode=run_observation.inode,
                        mode=run_observation.mode,
                    )
                    continue
                if name == target_state.run_id:
                    raw, journal_observation = _read_named_file(
                        run_descriptor, "journal.jsonl"
                    )
                    if (
                        run_observation
                        != target_state.directory_observation
                        or raw != target_journal.payload
                        or not raw.startswith(target_base)
                        or journal_observation
                        != target_journal.observation
                    ):
                        raise journal.CoordinationRefusal(
                            journal.BATCH_DIVERGED
                        )
                    state = target_state
                else:
                    raw, journal_observation = journal._read_bound_regular(
                        run_descriptor,
                        "journal.jsonl",
                        require_nonempty=True,
                    )
                    state = journal._scan_run(
                        run_dir,
                        raw=raw,
                        directory_observation=run_observation,
                        journal_observation=journal_observation,
                    )
                owner_result = journal._read_owner_observation_at(
                    run_descriptor
                )
                rebound = os.stat(
                    name,
                    dir_fd=root_descriptor,
                    follow_symlinks=False,
                )
                if not journal._matches_observation(
                    rebound, run_observation
                ):
                    raise journal.CoordinationRefusal(
                        journal.BATCH_DIVERGED
                    )
                if state.run_id in states:
                    raise journal.CoordinationRefusal(
                        journal.BATCH_DIVERGED
                    )
                states[state.run_id] = state
                if owner_result is None:
                    if (
                        not state.pre_coordination
                        and not state.legacy
                        and state.run_id != target_state.run_id
                    ):
                        raise journal.CoordinationRefusal(
                            journal.BATCH_DIVERGED
                        )
                else:
                    owners[state.run_id] = owner_result[0]
            finally:
                if run_descriptor is not None:
                    os.close(run_descriptor)
        rebound_root = os.lstat(runs_root)
        if (
            not journal._matches_observation(
                rebound_root, root_observation
            )
            or frozenset(os.listdir(root_descriptor))
            != frozenset(names)
        ):
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        open_runs = journal._reconcile_registry(snapshot, states)
        reservations = journal._derive_reservations(states)
        journal._validate_registry_lock(state_root, registry_lock)
        if (
            journal._read_registry_snapshot(
                state_root, locked=registry_lock
            )
            != snapshot
        ):
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        return journal.CoordinationView(
            snapshot,
            states,
            open_runs,
            reservations,
            placeholders,
            owners,
            root_observation,
        )
    except journal.CoordinationRefusal:
        raise
    except OSError as exc:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED) from exc
    finally:
        if root_descriptor is not None:
            os.close(root_descriptor)


def _validate_recovery_view_fences(
    state_root: Path,
    registry_lock: journal.RegistryLock,
    view: journal.CoordinationView,
    locked: BatchLock,
    intent_exact: journal.ExactFile,
    journal_exact: journal.ExactFile,
    target_state: journal.RunState,
    target_base: bytes,
) -> None:
    current_view = _recovery_coordination_view(
        state_root,
        registry_lock,
        target_state,
        journal_exact,
        target_base,
    )
    if current_view != view:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    journal._validate_registry_lock(state_root, registry_lock)
    if (
        journal._read_registry_snapshot(
            state_root, locked=registry_lock
        )
        != view.registry
    ):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    runs_root = state_root / ".codex-orchestrator/runs"
    try:
        rebound_root = os.lstat(runs_root)
    except OSError as exc:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED) from exc
    if (
        view.runs_root_observation is None
        or not journal._matches_observation(
            rebound_root, view.runs_root_observation
        )
    ):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    _validate_batch_lock(locked)
    _require_exact_named_file(
        locked, journal.BATCH_INTENT_NAME, intent_exact
    )
    _require_exact_named_file(locked, "journal.jsonl", journal_exact)


def _ensure_recovery_owner(
    locked: BatchLock,
    intent: dict[str, object],
    repository: Path,
    run_id: str,
    *,
    expected_journal: journal.ExactFile | None,
    expected_intent: journal.ExactFile,
) -> None:
    """Prove/adopt ownership before recovery appends stored intent bytes."""

    base_size = int(intent["base_size"])
    if base_size == 0:
        _opening_owner_is_current(locked)
        return
    if not isinstance(expected_journal, journal.ExactFile):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    raw, journal_observation = _read_named_file(
        locked.run_descriptor, "journal.jsonl"
    )
    if (
        raw != expected_journal.payload
        or journal_observation != expected_journal.observation
        or len(raw) < base_size
        or journal._sha256(raw[:base_size]) != intent["base_sha256"]
    ):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    try:
        state = journal._scan_run(
            locked.run_dir,
            raw=raw[:base_size],
            directory_observation=journal._file_observation(
                os.fstat(locked.run_descriptor)
            ),
            journal_observation=journal_observation,
        )
    except journal.CoordinationRefusal as exc:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED) from exc
    _, state_root = journal._resolve_repository(repository, "journal batch")
    current = journal._session_owner()
    intended_records = _records_from_batch(
        _decode_base64url(intent["batch_bytes"])
    )
    reserving_retired_close = bool(
        state.disposition == "retired"
        and state.was_retired
        and state.successor_of is not None
        and len(intended_records) == 1
        and intended_records[0].get("type") == "run_closed"
    )
    with journal._registry_lock(state_root) as registry_lock:
        recovery_view: journal.CoordinationView | None = None
        if reserving_retired_close:
            intended = _decode_base64url(intent["batch_bytes"])
            suffix = raw[base_size:]
            if (
                len(suffix) > len(intended)
                or not intended.startswith(suffix)
            ):
                raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
            try:
                recovery_view = _recovery_coordination_view(
                    state_root,
                    registry_lock,
                    state,
                    expected_journal,
                    raw[:base_size],
                )
                classified = journal._target_state(
                    recovery_view,
                    run_id,
                    "run close",
                    allow_reserving_retired_close=True,
                )
            except journal.CoordinationRefusal as exc:
                raise journal.CoordinationRefusal(
                    journal.BATCH_DIVERGED
                ) from exc
            if (
                classified.records != state.records
                or classified.scope != state.scope
                or classified.successor_of != state.successor_of
                or classified.directory_observation
                != state.directory_observation
                or classified.journal_observation
                != state.journal_observation
            ):
                raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
            snapshot = recovery_view.registry
        else:
            snapshot = journal._read_registry_snapshot(
                state_root, locked=registry_lock
            )
            if snapshot.open_runs.get(run_id) != state.scope:
                raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        if recovery_view is not None:
            _validate_recovery_view_fences(
                state_root,
                registry_lock,
                recovery_view,
                locked,
                expected_intent,
                expected_journal,
                state,
                raw[:base_size],
            )
        else:
            journal._validate_registry_lock(state_root, registry_lock)
            _validate_batch_lock(locked)
            _require_exact_named_file(
                locked, journal.BATCH_INTENT_NAME, expected_intent
            )
            _require_exact_named_file(
                locked, "journal.jsonl", expected_journal
            )
        with journal._locked_journal(
            state, _expected_prefix=raw[:base_size]
        ) as locked_journal:
            classification = journal._classify_owner(
                state,
                current,
                adopt_missing=state.pre_coordination,
                locked=locked_journal,
            )
            if recovery_view is not None:
                _validate_recovery_view_fences(
                    state_root,
                    registry_lock,
                    recovery_view,
                    locked,
                    expected_intent,
                    expected_journal,
                    state,
                    raw[:base_size],
                )
            else:
                journal._validate_registry_lock(
                    state_root, registry_lock
                )
                _validate_batch_lock(locked)
                _require_exact_named_file(
                    locked,
                    journal.BATCH_INTENT_NAME,
                    expected_intent,
                )
                _require_exact_named_file(
                    locked, "journal.jsonl", expected_journal
                )
            with journal._owner_takeover_transaction(
                state,
                current,
                classification,
                adopt_missing=state.pre_coordination,
                locked=locked_journal,
            ) as takeover:
                _validate_batch_lock(locked)
                journal._validate_registry_lock(state_root, registry_lock)
                if (
                    journal._read_registry_snapshot(
                        state_root, locked=registry_lock
                    )
                    != snapshot
                ):
                    raise journal.CoordinationRefusal(
                        journal.BATCH_DIVERGED
                    )
                journal._validate_owner_takeover(
                    locked_journal, takeover
                )
    _require_exact_named_file(
        locked, "journal.jsonl", expected_journal
    )


def _scope_change_record(
    records: Sequence[dict[str, object]],
    *,
    run_id: str,
    scope: tuple[str, ...] | None = None,
) -> dict[str, object]:
    if len(records) != 1:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    record = records[0]
    record_scope = record.get("scope")
    if (
        record.get("type") != "decision"
        or record.get("resolution") != journal.READMISSION_RESOLUTION
        or record.get("run_id") != run_id
        or not isinstance(record_scope, list)
        or not all(isinstance(value, str) for value in record_scope)
        or (scope is not None and record_scope != list(scope))
    ):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    return record


def _adopt_owner_in_coordination_view(
    state_root: Path,
    state: journal.RunState,
    view: journal.CoordinationView,
    registry_lock: journal.RegistryLock,
    *,
    expected_prefix: bytes | None = None,
) -> journal.Owner:
    current = journal._session_owner()
    with journal._locked_journal(
        state, _expected_prefix=expected_prefix
    ) as locked_journal:
        classification = journal._classify_owner(
            state,
            current,
            adopt_missing=state.pre_coordination,
            locked=locked_journal,
        )
        with journal._owner_takeover_transaction(
            state,
            current,
            classification,
            adopt_missing=state.pre_coordination,
            locked=locked_journal,
        ) as takeover:
            journal._validate_registry_lock(state_root, registry_lock)
            if (
                journal._read_registry_snapshot(
                    state_root, locked=registry_lock
                )
                != view.registry
            ):
                raise journal.CoordinationRefusal(
                    journal.REGISTRY_UNAVAILABLE
                )
            journal._validate_owner_takeover(locked_journal, takeover)
    return current


def _scope_change_recovery_context(
    locked: BatchLock,
    state_root: Path,
    registry_lock: journal.RegistryLock,
    *,
    run_id: str,
    record: dict[str, object],
    base_size: int,
) -> tuple[
    journal.CoordinationView,
    journal.RunState,
    tuple[str, ...],
    bool,
    bytes,
]:
    journal_raw, journal_observation = _read_named_file(
        locked.run_descriptor, "journal.jsonl"
    )
    if not 0 <= base_size <= len(journal_raw):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    base = journal_raw[:base_size]
    try:
        base_state = journal._scan_run(
            locked.run_dir,
            raw=base,
            directory_observation=journal._file_observation(
                os.fstat(locked.run_descriptor)
            ),
            journal_observation=journal_observation,
        )
        scope = journal.canonical_scope(list(record["scope"]))
    except (KeyError, journal.CoordinationRefusal) as exc:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED) from exc
    if base_state.run_id != run_id:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)

    snapshot = journal._read_registry_snapshot(
        state_root, locked=registry_lock
    )
    if snapshot.open_runs.get(run_id) == base_state.scope:
        expected_journal = journal.ExactFile(
            journal_raw, journal_observation
        )
        try:
            view = _recovery_coordination_view(
                state_root,
                registry_lock,
                base_state,
                expected_journal,
                base,
            )
            classified = journal._target_state(
                view, run_id, "run readmit"
            )
        except journal.CoordinationRefusal as exc:
            raise journal.CoordinationRefusal(
                journal.BATCH_DIVERGED
            ) from exc
        if classified.records != base_state.records:
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        return view, base_state, scope, False, base

    if snapshot.open_runs.get(run_id) != scope:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    try:
        view = journal._coordination_view(
            state_root,
            owner_target_ids=frozenset({run_id}),
            locked=registry_lock,
        )
        state = journal._target_state(view, run_id, "run readmit")
    except journal.CoordinationRefusal as exc:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED) from exc
    if state.scope != scope:
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    return view, state, scope, True, base


def _publish_scope_change(
    state_root: Path,
    view: journal.CoordinationView,
    registry_lock: journal.RegistryLock,
    *,
    run_id: str,
    scope: tuple[str, ...],
    record: dict[str, object],
    current: journal.Owner,
    already_published: bool,
) -> None:
    if already_published:
        journal._assert_coordination_view_unchanged(
            state_root, view, locked=registry_lock
        )
        return
    updated = dict(view.open_runs)
    updated[run_id] = scope
    journal._write_registry(
        state_root,
        updated,
        view=view,
        changed_run_id=run_id,
        appended_record=record,
        expected_owner=current,
        locked=registry_lock,
        expected_runs_root=view.runs_root_observation,
    )


def _recover_scope_change_locked(
    locked: BatchLock,
    intent: dict[str, object],
    intent_observation: journal.FileObservation,
    *,
    repository: Path,
    state_root: Path,
    run_id: str,
    repeated: bool,
    replace: bool | None,
) -> BatchOutcome:
    if (
        SCOPE_CHANGE_TRANSACTION_CONTROLS
        != _SCOPE_CHANGE_TRANSACTION_REQUIRED
    ):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    records = _records_from_batch(_decode_base64url(intent["batch_bytes"]))
    record = _scope_change_record(records, run_id=run_id)
    expected_journal = _optional_exact_named_file(
        locked, "journal.jsonl"
    )
    expected_receipts = _optional_exact_named_file(
        locked, journal.BATCH_RECEIPTS_NAME
    )
    if not isinstance(expected_journal, journal.ExactFile):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    with journal._registry_lock(state_root) as registry_lock:
        view, state, scope, published, base = (
            _scope_change_recovery_context(
                locked,
                state_root,
                registry_lock,
                run_id=run_id,
                record=record,
                base_size=int(intent["base_size"]),
            )
        )
        try:
            recorded_repository = journal._recorded_repository_root(
                state.run_dir, state_root, records=state.records
            )
        except journal.CoordinationRefusal as exc:
            raise journal.CoordinationRefusal(
                journal.BATCH_DIVERGED
            ) from exc
        if recorded_repository != repository:
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        if not published:
            # Standalone recovery has no durable proof of --replace.  It may
            # safely recover a widening request, while a shrinking request is
            # left pending for an identical caller-bound retry.
            journal._validate_readmission_scope(
                view,
                state,
                run_id=run_id,
                scope=scope,
                replace=False if replace is None else replace,
            )
        current = _adopt_owner_in_coordination_view(
            state_root,
            state,
            view,
            registry_lock,
            expected_prefix=base if not published else None,
        )
        outcome = _recover_locked(
            locked,
            intent,
            intent_observation,
            repeated=repeated,
            expected_journal=expected_journal,
            expected_receipts=expected_receipts,
        )
        _publish_scope_change(
            state_root,
            view,
            registry_lock,
            run_id=run_id,
            scope=scope,
            record=record,
            current=current,
            already_published=published,
        )
        return outcome


def _finalize_scope_change_receipt_locked(
    locked: BatchLock,
    outcome: BatchOutcome,
    *,
    state_root: Path,
    run_id: str,
    replace: bool,
) -> BatchOutcome:
    if (
        SCOPE_CHANGE_TRANSACTION_CONTROLS
        != _SCOPE_CHANGE_TRANSACTION_REQUIRED
    ):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    record = _scope_change_record(outcome.records, run_id=run_id)
    with journal._registry_lock(state_root) as registry_lock:
        view, state, scope, published, base = (
            _scope_change_recovery_context(
                locked,
                state_root,
                registry_lock,
                run_id=run_id,
                record=record,
                base_size=int(outcome.receipt["base_size"]),
            )
        )
        if published:
            journal._assert_coordination_view_unchanged(
                state_root, view, locked=registry_lock
            )
            return outcome
        journal._validate_readmission_scope(
            view,
            state,
            run_id=run_id,
            scope=scope,
            replace=replace,
        )
        current = _adopt_owner_in_coordination_view(
            state_root,
            state,
            view,
            registry_lock,
            expected_prefix=base,
        )
        _publish_scope_change(
            state_root,
            view,
            registry_lock,
            run_id=run_id,
            scope=scope,
            record=record,
            current=current,
            already_published=False,
        )
    return outcome


def execute_scope_change_batch(
    repo: Path,
    run_id: str,
    *,
    idempotency_key: str,
    inputs: dict[str, object],
    scope: tuple[str, ...],
    replace: bool,
    build_records: RecordBuilder,
) -> BatchOutcome:
    """Execute one typed readmission under the batch and registry locks."""

    key = validate_idempotency_key(idempotency_key)
    if (
        SCOPE_CHANGE_TRANSACTION_CONTROLS
        != _SCOPE_CHANGE_TRANSACTION_REQUIRED
    ):
        raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
    if (
        type(replace) is not bool
        or not scope
        or inputs != {"scope": list(scope), "replace": replace}
    ):
        raise journal.CoordinationRefusal(journal.INVALID_JOURNAL_RECORD)
    run_id = journal._operation_run_id("run readmit", run_id)
    repository, state_root = journal._resolve_repository(
        repo, "run readmit"
    )
    _, request_sha256 = normalized_request(
        repository, run_id, "run-readmit", inputs
    )
    run_dir = state_root / ".codex-orchestrator/runs" / run_id

    try:
        os.lstat(run_dir)
    except FileNotFoundError as exc:
        raise journal.CoordinationRefusal(
            f"forge: run readmit refused — run {run_id} does not exist"
        ) from exc
    except OSError as exc:
        raise journal.CoordinationRefusal(
            journal.REGISTRY_UNAVAILABLE
        ) from exc

    # Legacy runs have no batch sidecars yet.  Repeat their read-only
    # coordination checks before allocating the first lock file so a refused
    # readmission remains byte- and name-identical to the prior state.
    try:
        os.lstat(run_dir / journal.BATCH_LOCK_NAME)
    except FileNotFoundError:
        with journal._registry_lock(state_root) as registry_lock:
            view = journal._coordination_view(
                state_root,
                owner_target_ids=frozenset({run_id}),
                locked=registry_lock,
            )
            state = journal._target_state(view, run_id, "run readmit")
            recorded_repository = journal._recorded_repository_root(
                state.run_dir, state_root, records=state.records
            )
            if recorded_repository != repository:
                raise journal.CoordinationRefusal(
                    journal.REGISTRY_UNAVAILABLE
                )
            journal._classify_owner(
                state,
                _read_only_session_owner(),
                adopt_missing=state.pre_coordination,
            )
            journal._validate_readmission_scope(
                view,
                state,
                run_id=run_id,
                scope=scope,
                replace=replace,
            )
    except OSError as exc:
        raise journal.CoordinationRefusal(
            journal.REGISTRY_UNAVAILABLE
        ) from exc

    with batch_lock(run_dir, create=True) as locked:
        _matching_intent_temporary(locked, key, request_sha256)
        pending = _load_intent(locked)
        if pending is not None:
            intent, observed = pending
            if intent["idempotency_key"] != key:
                raise journal.CoordinationRefusal(journal.BATCH_PENDING)
            if intent["request_sha256"] != request_sha256:
                raise journal.CoordinationRefusal(
                    journal.BATCH_KEY_CONFLICT
                )
            _scope_change_record(
                _records_from_batch(
                    _decode_base64url(intent["batch_bytes"])
                ),
                run_id=run_id,
                scope=scope,
            )
            return _recover_scope_change_locked(
                locked,
                intent,
                observed,
                repository=repository,
                state_root=state_root,
                run_id=run_id,
                repeated=True,
                replace=replace,
            )

        completed = _matching_receipt(locked, key, request_sha256)
        if completed is not None:
            _scope_change_record(
                completed.records, run_id=run_id, scope=scope
            )
            return _finalize_scope_change_receipt_locked(
                locked,
                completed,
                state_root=state_root,
                run_id=run_id,
                replace=replace,
            )

        with journal._registry_lock(state_root) as registry_lock:
            view = journal._coordination_view(
                state_root,
                owner_target_ids=frozenset({run_id}),
                locked=registry_lock,
            )
            state = journal._target_state(view, run_id, "run readmit")
            recorded_repository = journal._recorded_repository_root(
                state.run_dir, state_root, records=state.records
            )
            if recorded_repository != repository:
                raise journal.CoordinationRefusal(
                    journal.REGISTRY_UNAVAILABLE
                )
            _validate_target_lifecycle(state, close=False)
            journal._classify_owner(
                state,
                _read_only_session_owner(),
                adopt_missing=state.pre_coordination,
            )
            journal._validate_readmission_scope(
                view,
                state,
                run_id=run_id,
                scope=scope,
                replace=replace,
            )
            records = tuple(build_records(state, repository))
            _scope_change_record(
                records, run_id=run_id, scope=scope
            )
            _prevalidate_records(
                repository,
                state,
                records,
                close=False,
                scope_change=True,
            )
            current = _adopt_owner_in_coordination_view(
                state_root,
                state,
                view,
                registry_lock,
            )
            intent, _receipt, expected_journal, expected_receipts = (
                _prepare_intent(
                    locked, key, request_sha256, records
                )
            )
            if "intent" not in journal.BATCH_TRANSACTION_CONTROLS:
                raise journal.CoordinationRefusal(
                    journal.BATCH_DIVERGED
                )
            published = _write_intent(locked, intent)
            _require_exact_named_file(
                locked, "journal.jsonl", expected_journal
            )
            _require_exact_named_file(
                locked,
                journal.BATCH_RECEIPTS_NAME,
                expected_receipts,
            )
            pending = _load_intent(locked)
            if pending is None:
                raise journal.CoordinationRefusal(
                    journal.BATCH_DIVERGED
                )
            stored_intent, observed = pending
            _validate_published_intent(
                intent, stored_intent, observed, published
            )
            outcome = _recover_locked(
                locked,
                stored_intent,
                observed,
                repeated=False,
                expected_journal=expected_journal,
                expected_receipts=expected_receipts,
            )
            _publish_scope_change(
                state_root,
                view,
                registry_lock,
                run_id=run_id,
                scope=scope,
                record=records[0],
                current=current,
                already_published=False,
            )
            return outcome


def execute_existing_batch(
    repo: Path,
    run_id: str,
    *,
    idempotency_key: str,
    verb: str,
    inputs: dict[str, object],
    build_records: RecordBuilder,
    validate_inputs: InputValidator,
    validate_citations: CitationValidator,
    validate_record_schema: RecordSchemaValidator,
    resolve_records: RecordResolver | None = None,
    prove_relations: RelationProver | None = None,
    validate_transaction_base: TransactionBaseValidator | None = None,
    validate_existing: ExistingBatchValidator | None = None,
    close: bool = False,
) -> BatchOutcome:
    key = validate_idempotency_key(idempotency_key)
    run_id = journal._operation_run_id("journal batch", run_id)
    repository, state_root = journal._resolve_repository(repo, "journal batch")
    _, request_sha256 = normalized_request(repository, run_id, verb, inputs)
    run_dir = state_root / ".codex-orchestrator/runs" / run_id

    with batch_lock(run_dir, create=True) as locked:
        _matching_intent_temporary(locked, key, request_sha256)
        pending = _load_intent(locked)
        if pending is not None:
            intent, observed = pending
            if intent["idempotency_key"] != key:
                raise journal.CoordinationRefusal(journal.BATCH_PENDING)
            if intent["request_sha256"] != request_sha256:
                raise journal.CoordinationRefusal(journal.BATCH_KEY_CONFLICT)
            if validate_existing is not None:
                validate_existing(
                    _records_from_batch(
                        _decode_base64url(intent["batch_bytes"])
                    )
                )
            return _recover_current_locked(
                locked,
                intent,
                observed,
                repeated=True,
                repository=repository,
                run_id=run_id,
            )
        repeated = _matching_receipt(locked, key, request_sha256)
        if repeated is not None:
            if validate_existing is not None:
                validate_existing(repeated.records)
            _finalize_lifecycle_registry(repository, run_id, repeated.records)
            return repeated

        # Phase 2: only caller-controlled syntax and object/type envelopes.
        validate_inputs()

        # Phase 3: caller citations and capture inputs precede journal state and
        # owner inspection.  This callback must not scan the target journal.
        validate_citations(repository, run_dir)

        # Phase 4: lifecycle and owner classification are read-only.  The
        # session identity deliberately carries no newly allocated timestamp.
        state = journal._scan_run(run_dir)
        recorded_repository = journal._recorded_repository_root(
            state.run_dir, state_root, records=state.records
        )
        if recorded_repository != repository:
            raise journal.CoordinationRefusal(journal.REGISTRY_UNAVAILABLE)
        _validate_target_lifecycle(state, close=close)
        journal._classify_owner(
            state,
            _read_only_session_owner(),
            adopt_missing=state.pre_coordination,
        )

        # Phase 5: typed-record schema and writer-contract conditionals are
        # pure.  No builder ID/time allocation, relation lookup, Git access, or
        # binding replay is reachable before this callback succeeds.
        validate_record_schema(state, repository)

        # Phase 6: allocate derived fields, validate relations/IDs/bindings,
        # and validate each successive projected-journal prefix.
        records = tuple(build_records(state, repository))
        _prevalidate_records(
            repository,
            state,
            records,
            close=close,
            defer_binding=resolve_records is not None,
        )
        if resolve_records is not None:
            records = tuple(resolve_records(state, repository, records))
            _prevalidate_records(
                repository, state, records, close=close
            )

        # Phase 7: terminal chain replay/capture proof is read-only.
        if prove_relations is not None:
            prove_relations(state, repository, records)

        # Phase 8: ownership mutation is permitted only after every read-only
        # validation and proof above has succeeded.
        _adopt_owner_before_intent(
            repository, state_root, run_id, close=close
        )

        # Phases 9 and 10: transaction bytes, then lifecycle registry update
        # inside _recover_locked after the receipt is durable.
        intent, _, expected_journal, expected_receipts = _prepare_intent(
            locked, key, request_sha256, records
        )
        if validate_transaction_base is not None:
            validate_transaction_base(
                expected_journal, expected_receipts
            )
        if "intent" in journal.BATCH_TRANSACTION_CONTROLS:
            _require_exact_named_file(
                locked, "journal.jsonl", expected_journal
            )
            _require_exact_named_file(
                locked, journal.BATCH_RECEIPTS_NAME, expected_receipts
            )
            published = _write_intent(locked, intent)
            _require_exact_named_file(
                locked, "journal.jsonl", expected_journal
            )
            _require_exact_named_file(
                locked, journal.BATCH_RECEIPTS_NAME, expected_receipts
            )
            pending = _load_intent(locked)
            if pending is None:
                raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
            stored_intent, observed = pending
            _validate_published_intent(
                intent, stored_intent, observed, published
            )
        else:
            stored_intent = intent
            observed = journal.FileObservation(0, 0, 0)

        if "intent" not in journal.BATCH_TRANSACTION_CONTROLS:
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        return _recover_current_locked(
            locked,
            stored_intent,
            observed,
            repeated=False,
            repository=repository,
            run_id=run_id,
            expected_journal=expected_journal,
            expected_receipts=expected_receipts,
        )


def lookup_existing_batch(
    repo: Path,
    run_id: str,
    *,
    idempotency_key: str,
    verb: str,
    inputs: dict[str, object],
) -> BatchOutcome | None:
    """Perform only the pre-allocation lookup phase for a known run path."""

    key = validate_idempotency_key(idempotency_key)
    run_id = journal._operation_run_id("journal batch", run_id)
    repository, state_root = journal._resolve_repository(repo, "journal batch")
    _, request_sha256 = normalized_request(repository, run_id, verb, inputs)
    run_dir = state_root / ".codex-orchestrator/runs" / run_id
    with batch_lock(run_dir, create=False) as locked:
        _matching_intent_temporary(locked, key, request_sha256)
        pending = _load_intent(locked)
        if pending is not None:
            intent, observed = pending
            if intent["idempotency_key"] != key:
                raise journal.CoordinationRefusal(journal.BATCH_PENDING)
            if intent["request_sha256"] != request_sha256:
                raise journal.CoordinationRefusal(journal.BATCH_KEY_CONFLICT)
            return _recover_current_locked(
                locked,
                intent,
                observed,
                repeated=True,
                repository=repository,
                run_id=run_id,
            )
        completed = _matching_receipt(locked, key, request_sha256)
        if completed is not None:
            _finalize_lifecycle_registry(repository, run_id, completed.records)
        return completed


def recover_batch(repo: Path, run_id: str) -> BatchOutcome:
    run_id = journal._operation_run_id("journal batch recovery", run_id)
    repository, state_root = journal._resolve_repository(
        repo, "journal batch recovery"
    )
    run_dir = state_root / ".codex-orchestrator/runs" / run_id
    with batch_lock(run_dir, create=False) as locked:
        pending = _load_intent(locked)
        if pending is None:
            if _validate_no_orphan_intent_temporary(locked) is not None:
                raise journal.CoordinationRefusal(journal.BATCH_PENDING)
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        intent, observed = pending
        _repair_receipt_gap_locked(
            locked,
            intent,
            observed,
            repository=repository,
            run_id=run_id,
        )
        records = _records_from_batch(
            _decode_base64url(intent["batch_bytes"])
        )
        if (
            len(records) == 1
            and records[0].get("type") == "decision"
            and records[0].get("resolution")
            == journal.READMISSION_RESOLUTION
        ):
            return _recover_scope_change_locked(
                locked,
                intent,
                observed,
                repository=repository,
                state_root=state_root,
                run_id=run_id,
                repeated=True,
                replace=None,
            )
        return _recover_current_locked(
            locked,
            intent,
            observed,
            repeated=True,
            repository=repository,
            run_id=run_id,
        )


def validate_pending_outbox_receipt(
    pending: dict[str, object], receipt: dict[str, object]
) -> None:
    """Shared task-04 seam for the review-MINOR pre-acknowledgement check."""

    _validate_receipt(receipt)
    if (
        set(receipt) != _receipt_keys()
        or set(pending) != {
            "idempotency_key",
            "batch_digest",
            "record_count",
            "source_event_digest",
        }
        or pending.get("idempotency_key") != receipt.get("idempotency_key")
        or not _sha_member(pending.get("idempotency_key"))
        or pending.get("source_event_digest")
        != pending.get("idempotency_key")
        or not _sha_member(pending.get("source_event_digest"))
        or pending.get("batch_digest") != receipt.get("batch_sha256")
        or not _sha_member(pending.get("batch_digest"))
        or pending.get("record_count") != receipt.get("record_count")
        or type(pending.get("record_count")) is not int
        or int(pending["record_count"]) <= 0
    ):
        raise journal.CoordinationRefusal(journal.JOURNAL_RECEIPT_MISMATCH)


def journal_receipted_details(
    pending: dict[str, object], receipt: dict[str, object]
) -> dict[str, object]:
    """Return the exact non-batch DM-012 acknowledgement carrier."""

    validate_pending_outbox_receipt(pending, receipt)
    return {
        "idempotency_key": receipt["idempotency_key"],
        "batch_digest": receipt["batch_sha256"],
        "receipt_digest": journal._sha256(_canonical_sidecar(receipt)),
    }


def drain_chain_batch(
    repo: Path,
    run_id: str,
    *,
    chain_id: str,
    source_event_digest: str,
    records: Sequence[dict[str, object]],
    capability: object | None = None,
) -> BatchOutcome:
    """Drain records only after task-04 authenticates an opaque capability."""

    key = validate_idempotency_key(source_event_digest)
    run_id = journal._operation_run_id("journal batch", run_id)
    repository, state_root = journal._resolve_repository(
        repo, "journal batch"
    )
    candidate_records = tuple(records)
    batch_bytes = b"".join(
        journal._journal_line(record) for record in candidate_records
    )
    supplied_records = _records_from_batch(batch_bytes)
    task_values = {
        record.get("task")
        for record in supplied_records
        if isinstance(record.get("task"), str)
    }
    task_id = (
        next(iter(task_values))
        if len(task_values) == 1
        and all(record.get("task") in task_values for record in supplied_records)
        else ""
    )
    inputs = {
        "chain_id": chain_id,
        "source_event_digest": source_event_digest,
        "batch_digest": journal._sha256(batch_bytes),
        "record_count": len(supplied_records),
    }
    _, request_sha256 = normalized_request(
        repository, run_id, "chain outbox-drain", inputs
    )
    run_dir = state_root / ".codex-orchestrator/runs" / run_id
    authorized: _ChainBatchAuthorization | None = None

    def validate_inputs() -> None:
        if (
            CHAIN_BATCH_AUTHORIZATION_CONTROLS
            != _CHAIN_BATCH_AUTHORIZATION_REQUIRED
            or _CHAIN_BATCH_AUTHORIZER is None
            or capability is None
            or not isinstance(chain_id, str)
            or journal.CHAIN_ID_PATTERN.fullmatch(chain_id) is None
            or not task_id
            or not supplied_records
            or supplied_records != candidate_records
        ):
            raise journal.CoordinationRefusal(journal.INVALID_JOURNAL_RECORD)
        for record in supplied_records:
            journal._validate_record_envelope(record)

    def validate_citations(repository: Path, run_dir: Path) -> None:
        for record in supplied_records:
            journal._validate_append_citations(
                repository, run_dir, record
            )

    def validate_record_schema(
        state: journal.RunState, repository: Path
    ) -> None:
        projected = list(state.records)
        for record in supplied_records:
            candidate = dict(record)
            candidate.pop("binding", None)
            journal._validate_proposed_record(
                candidate,
                run_id=state.run_id,
                repo_root=repository,
                scope=state.scope,
                prior_records=tuple(projected),
                _defer_binding=True,
            )
            projected.append(candidate)

    def authorize_supplied_records() -> tuple[dict[str, object], ...]:
        nonlocal authorized
        if authorized is not None:
            return _records_from_batch(authorized.batch_bytes)
        if (
            CHAIN_BATCH_AUTHORIZATION_CONTROLS
            != _CHAIN_BATCH_AUTHORIZATION_REQUIRED
            or _CHAIN_BATCH_AUTHORIZER is None
            or capability is None
        ):
            raise journal.CoordinationRefusal(
                journal.INVALID_JOURNAL_RECORD
            )
        try:
            candidate = _CHAIN_BATCH_AUTHORIZER(
                capability=capability,
                repository=repository,
                run_id=run_id,
                task_id=task_id,
                chain_id=chain_id,
                source_event_digest=source_event_digest,
                supplied_records=supplied_records,
            )
        except journal.CoordinationRefusal:
            raise
        except Exception as exc:
            raise journal.CoordinationRefusal(
                journal.INVALID_JOURNAL_RECORD
            ) from exc
        if type(candidate) is not _ChainBatchAuthorization:
            raise journal.CoordinationRefusal(
                journal.INVALID_JOURNAL_RECORD
            )
        try:
            authoritative_records = _records_from_batch(
                candidate.batch_bytes
            )
        except journal.CoordinationRefusal as exc:
            raise journal.CoordinationRefusal(
                journal.INVALID_JOURNAL_RECORD
            ) from exc
        if (
            candidate.repository != str(repository)
            or candidate.run_id != run_id
            or candidate.task_id != task_id
            or candidate.chain_id != chain_id
            or candidate.source_event_digest != source_event_digest
            or candidate.request_sha256 != request_sha256
            or candidate.batch_bytes != batch_bytes
            or type(candidate.record_count) is not int
            or candidate.record_count != len(supplied_records)
            or authoritative_records != supplied_records
            or not isinstance(candidate.journal_exact, journal.ExactFile)
            or not isinstance(candidate.receipts_exact, journal.ExactFile)
        ):
            raise journal.CoordinationRefusal(
                journal.INVALID_JOURNAL_RECORD
            )
        _require_exact_named_file(
            authority_lock, "journal.jsonl", candidate.journal_exact
        )
        _require_exact_named_file(
            authority_lock,
            journal.BATCH_RECEIPTS_NAME,
            candidate.receipts_exact,
        )
        for record in authoritative_records:
            binding = record.get("binding")
            source = (
                binding.get("source_record")
                if isinstance(binding, dict)
                else None
            )
            if (
                not isinstance(source, dict)
                or source.get("chain_id") != chain_id
                or source.get("event_digest") != source_event_digest
            ):
                raise journal.CoordinationRefusal(
                    journal.INVALID_JOURNAL_RECORD
                )
        authorized = candidate
        return authoritative_records

    def validate_existing_records(
        existing_records: Sequence[dict[str, object]],
    ) -> None:
        if tuple(existing_records) != supplied_records:
            raise journal.CoordinationRefusal(
                journal.INVALID_JOURNAL_RECORD
            )
        authorize_supplied_records()

    def build_records(
        _state: journal.RunState, _repository: Path
    ) -> Sequence[dict[str, object]]:
        return authorize_supplied_records()

    def prove_authorized_snapshots(
        _state: journal.RunState,
        _repository: Path,
        _records: Sequence[dict[str, object]],
    ) -> None:
        if (
            CHAIN_BATCH_AUTHORIZATION_CONTROLS
            != _CHAIN_BATCH_AUTHORIZATION_REQUIRED
            or authorized is None
        ):
            raise journal.CoordinationRefusal(
                journal.INVALID_JOURNAL_RECORD
            )
        _require_exact_named_file(
            authority_lock, "journal.jsonl", authorized.journal_exact
        )
        _require_exact_named_file(
            authority_lock,
            journal.BATCH_RECEIPTS_NAME,
            authorized.receipts_exact,
        )

    def validate_authorized_transaction_base(
        journal_exact: journal.ExactFile,
        receipts_exact: journal.ExactFile,
    ) -> None:
        if (
            CHAIN_BATCH_AUTHORIZATION_CONTROLS
            != _CHAIN_BATCH_AUTHORIZATION_REQUIRED
            or authorized is None
            or journal_exact != authorized.journal_exact
            or receipts_exact != authorized.receipts_exact
        ):
            raise journal.CoordinationRefusal(
                journal.INVALID_JOURNAL_RECORD
            )

    with batch_lock(run_dir, create=False) as authority_lock:
        return execute_existing_batch(
            repository,
            run_id,
            idempotency_key=key,
            verb="chain outbox-drain",
            inputs=inputs,
            build_records=build_records,
            validate_inputs=validate_inputs,
            validate_citations=validate_citations,
            validate_record_schema=validate_record_schema,
            prove_relations=prove_authorized_snapshots,
            validate_transaction_base=validate_authorized_transaction_base,
            validate_existing=validate_existing_records,
        )


def complete_open_batch(
    repo: Path,
    run_id: str,
    *,
    idempotency_key: str,
    inputs: dict[str, object],
    expected_opening: dict[str, object],
    repeated: bool,
) -> BatchOutcome:
    """Receipt an activated opening that `open_run` published atomically."""

    key = validate_idempotency_key(idempotency_key)
    run_id = journal._operation_run_id("run open", run_id)
    repository, state_root = journal._resolve_repository(repo, "run open")
    _, request_sha256 = normalized_request(
        repository, run_id, "run-open", inputs
    )
    run_dir = state_root / ".codex-orchestrator/runs" / run_id
    with batch_lock(run_dir, create=True) as locked:
        _matching_intent_temporary(locked, key, request_sha256)
        pending = _load_intent(locked)
        if pending is not None:
            intent, observed = pending
            if intent["idempotency_key"] != key:
                raise journal.CoordinationRefusal(journal.BATCH_PENDING)
            if intent["request_sha256"] != request_sha256:
                raise journal.CoordinationRefusal(journal.BATCH_KEY_CONFLICT)
            return _recover_current_locked(
                locked,
                intent,
                observed,
                repeated=True,
                repository=repository,
                run_id=run_id,
            )
        completed = _matching_receipt(locked, key, request_sha256)
        if completed is not None:
            _finalize_lifecycle_registry(repository, run_id, completed.records)
            return BatchOutcome(
                completed.receipt, completed.records, repeated
            )

        receipts, ledger_bytes, ledger_observation = _load_receipts(locked)
        if receipts:
            raise journal.CoordinationRefusal(journal.BATCH_KEY_CONFLICT)
        state = journal._scan_run(run_dir)
        if not state.records:
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        opening = dict(state.records[0])
        for name, value in expected_opening.items():
            if opening.get(name) != value:
                raise journal.CoordinationRefusal(journal.BATCH_KEY_CONFLICT)
        if opening.get("writer_contract") != journal.WRITER_CONTRACT:
            raise journal.CoordinationRefusal(journal.BATCH_KEY_CONFLICT)
        opening_bytes = journal._journal_line(opening)
        current, journal_observation = _read_named_file(
            locked.run_descriptor, "journal.jsonl"
        )
        if current != opening_bytes or ledger_bytes:
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        _, confirmed_ledger_bytes, confirmed_ledger_observation = _load_receipts(
            locked, create=True
        )
        if (
            confirmed_ledger_bytes != ledger_bytes
            or confirmed_ledger_observation is None
            or (
                ledger_observation is not None
                and confirmed_ledger_observation != ledger_observation
            )
        ):
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        expected_journal = journal.ExactFile(
            current, journal_observation
        )
        expected_receipts = journal.ExactFile(
            confirmed_ledger_bytes, confirmed_ledger_observation
        )

        receipt = {
            "schema": journal.BATCH_RECEIPT_SCHEMA,
            "idempotency_key": key,
            "request_sha256": request_sha256,
            "base_size": 0,
            "batch_sha256": journal._sha256(opening_bytes),
            "record_count": 1,
            "journal_size": len(opening_bytes),
            "journal_sha256": journal._sha256(opening_bytes),
            "recorded_at": journal._utc_now(),
        }
        receipt_bytes = _canonical_sidecar(receipt)
        intent = {
            "schema": journal.BATCH_INTENT_SCHEMA,
            "idempotency_key": key,
            "request_sha256": request_sha256,
            "base_size": 0,
            "base_sha256": journal._sha256(b""),
            "record_count": 1,
            "batch_bytes": _encode_base64url(opening_bytes),
            "batch_sha256": journal._sha256(opening_bytes),
            "receipt_base_size": 0,
            "receipt_base_sha256": journal._sha256(b""),
            "receipt_bytes": _encode_base64url(receipt_bytes),
        }
        _require_exact_named_file(
            locked, "journal.jsonl", expected_journal
        )
        _require_exact_named_file(
            locked, journal.BATCH_RECEIPTS_NAME, expected_receipts
        )
        published = _write_intent(locked, intent)
        _require_exact_named_file(
            locked, "journal.jsonl", expected_journal
        )
        _require_exact_named_file(
            locked, journal.BATCH_RECEIPTS_NAME, expected_receipts
        )
        pending = _load_intent(locked)
        if pending is None:
            raise journal.CoordinationRefusal(journal.BATCH_DIVERGED)
        stored, observed = pending
        _validate_published_intent(intent, stored, observed, published)
        return _recover_current_locked(
            locked,
            stored,
            observed,
            repeated=repeated,
            repository=repository,
            run_id=run_id,
            expected_journal=expected_journal,
            expected_receipts=expected_receipts,
        )
