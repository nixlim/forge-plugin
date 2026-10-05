"""Encode and decode bounded DM-012 chain-event evidence blocks."""

from __future__ import annotations

import base64
import binascii
import hashlib
import importlib
import re
from dataclasses import dataclass
from types import ModuleType
from typing import Protocol

RAW_LOG_MAX_BYTES = 67_108_864
ENCODED_PAYLOAD_MAX_BYTES = 2_097_152
LEGACY_RAW_MAX_BYTES = 2_097_152
LZMA_MEMLIMIT = 67_108_864

ARCHIVE_LZMA_UNAVAILABLE = "forge: archive refused — Python lzma module unavailable"
DECODE_LZMA_UNAVAILABLE = (
    "forge: chain-evidence decode refused — Python lzma module unavailable"
)
MALFORMED_BLOCK = "forge: chain-evidence decode refused — malformed block"
RAW_SIZE_LIMIT = "forge: chain-evidence decode refused — declared raw bytes exceed limit"
ENCODED_SIZE_LIMIT = (
    "forge: chain-evidence decode refused — encoded payload exceeds 2 MiB"
)
ENCODED_LENGTH_MISMATCH = (
    "forge: chain-evidence decode refused — encoded payload length mismatch"
)
MALFORMED_BASE64URL = (
    "forge: chain-evidence decode refused — malformed base64url payload"
)
XZ_DECOMPRESSION_FAILED = (
    "forge: chain-evidence decode refused — XZ decompression failed"
)
XZ_CHECK_INVALID = "forge: chain-evidence decode refused — XZ check is not CRC64"
XZ_TRUNCATED = "forge: chain-evidence decode refused — truncated XZ stream"
XZ_TRAILING_DATA = "forge: chain-evidence decode refused — trailing XZ data"
RAW_LENGTH_SHORT = "forge: chain-evidence decode refused — decoded output is short"
RAW_LENGTH_LONG = "forge: chain-evidence decode refused — decoded output is long"
RAW_DIGEST_MISMATCH = "forge: chain-evidence decode refused — raw SHA-256 mismatch"

_MARKER = "FORGE:CHAIN-EVIDENCE"
_CLOSING_LINE = f"<!-- /{_MARKER} -->"
_DECIMAL = r"(?:0|[1-9][0-9]*)"
_DIGEST = r"[0-9a-f]{64}"
_COMPRESSED_HEADER = re.compile(
    rf"<!-- {_MARKER} v1 encoding=xz\+base64url bytes=(?P<raw>{_DECIMAL}) "
    rf"encoded_bytes=(?P<encoded>{_DECIMAL}) sha256=(?P<digest>{_DIGEST}) -->",
    flags=re.ASCII,
)
_LEGACY_HEADER = re.compile(
    rf"<!-- {_MARKER} v1 encoding=base64url bytes=(?P<raw>{_DECIMAL}) "
    rf"sha256=(?P<digest>{_DIGEST}) -->",
    flags=re.ASCII,
)
_UNEMBEDDED_HEADER = re.compile(
    rf"<!-- {_MARKER} v1 encoding=UNEMBEDDED bytes=(?P<raw>{_DECIMAL}) "
    rf"sha256=(?P<digest>{_DIGEST}) -->",
    flags=re.ASCII,
)
_PAYLOAD = re.compile(r"[A-Za-z0-9_-]*", flags=re.ASCII)
_BASE64URL_VALUES = {
    character: index
    for index, character in enumerate(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    )
}

class ChainEvidenceError(ValueError):
    """A chain-evidence block cannot be encoded or decoded safely."""


class _Hash(Protocol):
    def update(self, value: bytes) -> None:
        ...

    def hexdigest(self) -> str:
        ...


class _Decompressor(Protocol):
    check: int
    eof: bool
    needs_input: bool
    unused_data: bytes

    def decompress(self, data: bytes, max_length: int = -1) -> bytes:
        ...


@dataclass(frozen=True)
class _ParsedBlock:
    encoding: str
    raw_size: str
    encoded_size: str | None
    digest: str
    payload: str | None


def _load_lzma(refusal: str) -> ModuleType:
    try:
        return importlib.import_module("lzma")
    except ImportError as exc:
        raise ChainEvidenceError(refusal) from exc


def _unembedded_block(raw: bytes) -> str:
    digest = hashlib.sha256(raw).hexdigest()
    return (
        f"<!-- {_MARKER} v1 encoding=UNEMBEDDED bytes={len(raw)} sha256={digest} -->\n"
        f"{_CLOSING_LINE}\n"
    )


def encode_chain_evidence(raw: bytes) -> str:
    """Render one new-write Revision-21 chain-evidence block."""

    if not isinstance(raw, bytes):
        raise TypeError("raw chain evidence must be bytes")
    if len(raw) > RAW_LOG_MAX_BYTES:
        return _unembedded_block(raw)
    lzma = _load_lzma(ARCHIVE_LZMA_UNAVAILABLE)
    compressed = lzma.compress(
        raw,
        format=lzma.FORMAT_XZ,
        check=lzma.CHECK_CRC64,
        preset=6,
    )
    payload = base64.urlsafe_b64encode(compressed).rstrip(b"=").decode("ascii")
    if len(payload) > ENCODED_PAYLOAD_MAX_BYTES:
        return _unembedded_block(raw)
    digest = hashlib.sha256(raw).hexdigest()
    return (
        f"<!-- {_MARKER} v1 encoding=xz+base64url bytes={len(raw)} "
        f"encoded_bytes={len(payload)} sha256={digest} -->\n"
        f"{payload}\n"
        f"{_CLOSING_LINE}\n"
    )


def _parse_block(block: str) -> _ParsedBlock:
    if not isinstance(block, str):
        raise ChainEvidenceError(MALFORMED_BLOCK)
    lines = block.split("\n")
    header = lines[0] if lines else ""
    match = _COMPRESSED_HEADER.fullmatch(header)
    if match is not None and len(lines) == 4 and lines[2:] == [_CLOSING_LINE, ""]:
        return _ParsedBlock(
            "xz+base64url",
            match["raw"],
            match["encoded"],
            match["digest"],
            lines[1],
        )
    match = _LEGACY_HEADER.fullmatch(header)
    if match is not None and len(lines) == 4 and lines[2:] == [_CLOSING_LINE, ""]:
        return _ParsedBlock(
            "base64url", match["raw"], None, match["digest"], lines[1]
        )
    match = _UNEMBEDDED_HEADER.fullmatch(header)
    if match is not None and lines == [header, _CLOSING_LINE, ""]:
        return _ParsedBlock(
            "UNEMBEDDED", match["raw"], None, match["digest"], None
        )
    raise ChainEvidenceError(MALFORMED_BLOCK)


def _decimal_above(value: str, limit: int) -> bool:
    canonical_limit = str(limit)
    return len(value) > len(canonical_limit) or (
        len(value) == len(canonical_limit) and value > canonical_limit
    )


def _payload_ascii(payload: str) -> bytes:
    try:
        encoded = payload.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ChainEvidenceError(MALFORMED_BASE64URL) from exc
    if _PAYLOAD.fullmatch(payload) is None:
        raise ChainEvidenceError(MALFORMED_BASE64URL)
    return encoded


def _validate_payload_size(
    payload: str, encoded_size: str | None, decoded_size: int | None
) -> None:
    observed_size = len(payload)
    if not payload.isascii():
        raise ChainEvidenceError(MALFORMED_BASE64URL)
    if encoded_size is not None:
        if encoded_size != str(observed_size):
            raise ChainEvidenceError(ENCODED_LENGTH_MISMATCH)
    if decoded_size is not None:
        legacy_encoded_max = (LEGACY_RAW_MAX_BYTES * 4 + 2) // 3
        if observed_size > legacy_encoded_max:
            raise ChainEvidenceError(RAW_LENGTH_LONG)
    remainder = observed_size % 4
    if remainder == 1:
        raise ChainEvidenceError(MALFORMED_BASE64URL)
    if encoded_size is not None:
        if observed_size > ENCODED_PAYLOAD_MAX_BYTES:
            raise ChainEvidenceError(ENCODED_SIZE_LIMIT)


def _validate_trailing_bits(payload: str) -> None:
    remainder = len(payload) % 4
    if not payload or remainder == 0:
        return
    unused_mask = 0x0F if remainder == 2 else 0x03
    if _BASE64URL_VALUES[payload[-1]] & unused_mask:
        raise ChainEvidenceError(MALFORMED_BASE64URL)


def _decode_base64url(
    payload: str, encoded_size: str | None, decoded_size: int | None = None
) -> bytes:
    _validate_payload_size(payload, encoded_size, decoded_size)
    payload_bytes = _payload_ascii(payload)
    _validate_trailing_bits(payload)
    if decoded_size is not None:
        expected_encoded_size = (decoded_size * 4 + 2) // 3
        if len(payload_bytes) < expected_encoded_size:
            raise ChainEvidenceError(RAW_LENGTH_SHORT)
        if len(payload_bytes) > expected_encoded_size:
            raise ChainEvidenceError(RAW_LENGTH_LONG)
    padding = b"=" * (-len(payload_bytes) % 4)
    try:
        decoded = base64.b64decode(
            payload_bytes + padding, altchars=b"-_", validate=True
        )
    except (binascii.Error, ValueError) as exc:
        raise ChainEvidenceError(MALFORMED_BASE64URL) from exc
    if base64.urlsafe_b64encode(decoded).rstrip(b"=") != payload_bytes:
        raise ChainEvidenceError(MALFORMED_BASE64URL)
    return decoded


def _append_output(
    parts: list[bytes], hasher: _Hash, chunk: bytes, total: int, raw_size: int
) -> int:
    if chunk:
        parts.append(chunk)
        hasher.update(chunk)
        total += len(chunk)
    if total > raw_size:
        raise ChainEvidenceError(RAW_LENGTH_LONG)
    return total


def _decompress_xz(
    compressed: bytes, raw_size: int, lzma: ModuleType
) -> tuple[bytes, str, _Decompressor]:
    try:
        decompressor = lzma.LZMADecompressor(
            format=lzma.FORMAT_XZ, memlimit=LZMA_MEMLIMIT
        )
        parts: list[bytes] = []
        hasher = hashlib.sha256()
        chunk = decompressor.decompress(compressed, max_length=raw_size + 1)
        total = _append_output(parts, hasher, chunk, 0, raw_size)
        while not decompressor.eof and not decompressor.needs_input:
            before = total
            chunk = decompressor.decompress(b"", max_length=raw_size + 1 - total)
            total = _append_output(parts, hasher, chunk, total, raw_size)
            if total == before:
                raise ChainEvidenceError(XZ_DECOMPRESSION_FAILED)
    except ChainEvidenceError:
        raise
    except Exception as exc:
        raise ChainEvidenceError(XZ_DECOMPRESSION_FAILED) from exc
    return b"".join(parts), hasher.hexdigest(), decompressor


def _verify_xz(
    raw: bytes,
    observed_digest: str,
    decompressor: _Decompressor,
    expected_size: int,
    expected_digest: str,
    lzma: ModuleType,
) -> bytes:
    if decompressor.check != lzma.CHECK_CRC64:
        raise ChainEvidenceError(XZ_CHECK_INVALID)
    if not decompressor.eof:
        raise ChainEvidenceError(XZ_TRUNCATED)
    if decompressor.unused_data:
        raise ChainEvidenceError(XZ_TRAILING_DATA)
    if len(raw) < expected_size:
        raise ChainEvidenceError(RAW_LENGTH_SHORT)
    if len(raw) > expected_size:
        raise ChainEvidenceError(RAW_LENGTH_LONG)
    if observed_digest != expected_digest:
        raise ChainEvidenceError(RAW_DIGEST_MISMATCH)
    return raw


def _decode_compressed(block: _ParsedBlock) -> bytes:
    if _decimal_above(block.raw_size, RAW_LOG_MAX_BYTES):
        raise ChainEvidenceError(RAW_SIZE_LIMIT)
    if block.payload is None or block.encoded_size is None:
        raise ChainEvidenceError(MALFORMED_BLOCK)
    compressed = _decode_base64url(block.payload, block.encoded_size)
    lzma = _load_lzma(DECODE_LZMA_UNAVAILABLE)
    expected_size = int(block.raw_size)
    raw, digest, decompressor = _decompress_xz(compressed, expected_size, lzma)
    return _verify_xz(
        raw, digest, decompressor, expected_size, block.digest, lzma
    )


def _decode_legacy(block: _ParsedBlock) -> bytes:
    if _decimal_above(block.raw_size, LEGACY_RAW_MAX_BYTES):
        raise ChainEvidenceError(RAW_SIZE_LIMIT)
    if block.payload is None:
        raise ChainEvidenceError(MALFORMED_BLOCK)
    expected_size = int(block.raw_size)
    raw = _decode_base64url(block.payload, None, expected_size)
    if len(raw) < expected_size:
        raise ChainEvidenceError(RAW_LENGTH_SHORT)
    if len(raw) > expected_size:
        raise ChainEvidenceError(RAW_LENGTH_LONG)
    if hashlib.sha256(raw).hexdigest() != block.digest:
        raise ChainEvidenceError(RAW_DIGEST_MISMATCH)
    return raw

def decode_chain_evidence(block: str) -> bytes | None:
    """Decode one exact legacy, compressed, or digest-only evidence block."""

    parsed = _parse_block(block)
    if parsed.encoding == "UNEMBEDDED":
        return None
    if parsed.encoding == "base64url":
        return _decode_legacy(parsed)
    return _decode_compressed(parsed)


__all__ = [
    "ARCHIVE_LZMA_UNAVAILABLE",
    "ChainEvidenceError",
    "DECODE_LZMA_UNAVAILABLE",
    "ENCODED_PAYLOAD_MAX_BYTES",
    "LZMA_MEMLIMIT",
    "RAW_LOG_MAX_BYTES",
    "decode_chain_evidence",
    "encode_chain_evidence",
]
