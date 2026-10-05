"""Focused tests for Revision-21 compressed chain-event evidence."""

from __future__ import annotations

import base64
import hashlib
import inspect
import lzma
import textwrap
import types
import unittest
from pathlib import Path
from types import FunctionType
from unittest import mock

from tests._cli_loader import load_cached, package_module

ROOT = Path(__file__).resolve().parents[1]
CODEC_PATH = ROOT / "scripts" / "forge" / "chain_evidence_codec.py"
ARCHIVER_PATH = ROOT / "scripts" / "forge" / "archive-run.py"
codec = load_cached("chain_evidence_codec", CODEC_PATH)
archive = load_cached("_forge_revision21_codec_archive", ARCHIVER_PATH)
archive_engine = package_module("engine._archive")
envelope = package_module("envelope")

EMPTY_DIGEST = hashlib.sha256(b"").hexdigest()
SAMPLE = b"forge chain evidence\n"
SAMPLE_DIGEST = "a020b733a28ab18a17ecd0e77f8ab225113e0b8541535d33a2fcefcb17da394c"
EMPTY_XZ_PAYLOAD = "_Td6WFoAAATm1rRGAAAAABzfRCEftvN9AQAAAAAEWVo"
SAMPLE_XZ_PAYLOAD = (
    "_Td6WFoAAATm1rRGAgAhARYAAAB0L-WjAQAUZm9yZ2UgY2hhaW4gZXZpZGVuY2UK"
    "AAAAAJwtfOdIh62GAAEtFS8LcW0ftvN9AQAAAAAEWVo"
)
LARGE_DICTIONARY_PAYLOAD = (
    "_Td6WFoAAATm1rRGAgAhAR4AAACbB1FmAQAAeAAAAABFru-D-O4WCgABGQGlLIHM"
    "H7bzfQEAAAAABFla"
)


class _ImportReached(Exception):
    pass


def _mutated_function(
    function: FunctionType,
    anchor: str,
    replacement: str,
) -> FunctionType:
    """Compile one exact in-memory mutant with production globals."""

    source = textwrap.dedent(inspect.getsource(function))
    if source.count(anchor) != 1:
        raise AssertionError(f"mutation anchor drifted for {function.__name__}")
    namespace = dict(function.__globals__)
    exec(
        compile(
            source.replace(anchor, replacement, 1),
            function.__code__.co_filename,
            "exec",
        ),
        namespace,
    )
    mutant = namespace[function.__name__]
    if not isinstance(mutant, FunctionType):
        raise AssertionError(f"mutation did not define {function.__name__}")
    return mutant


def _compressed_block(
    payload: str,
    raw_size: int | str = 0,
    digest: str = EMPTY_DIGEST,
    encoded_size: int | str | None = None,
) -> str:
    encoded = len(payload.encode("utf-8")) if encoded_size is None else encoded_size
    return (
        "<!-- FORGE:CHAIN-EVIDENCE v1 encoding=xz+base64url "
        f"bytes={raw_size} encoded_bytes={encoded} sha256={digest} -->\n"
        f"{payload}\n"
        "<!-- /FORGE:CHAIN-EVIDENCE -->\n"
    )


def _legacy_block(raw: bytes, payload: str | None = None) -> str:
    if payload is None:
        payload = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    return (
        "<!-- FORGE:CHAIN-EVIDENCE v1 encoding=base64url "
        f"bytes={len(raw)} sha256={hashlib.sha256(raw).hexdigest()} -->\n"
        f"{payload}\n"
        "<!-- /FORGE:CHAIN-EVIDENCE -->\n"
    )


def _block_for_stream(
    compressed: bytes,
    raw: bytes,
    raw_size: int | None = None,
    digest: str | None = None,
) -> str:
    payload = base64.urlsafe_b64encode(compressed).rstrip(b"=").decode("ascii")
    return _compressed_block(
        payload,
        len(raw) if raw_size is None else raw_size,
        hashlib.sha256(raw).hexdigest() if digest is None else digest,
    )


def _xz(raw: bytes, check: int = lzma.CHECK_CRC64) -> bytes:
    return lzma.compress(raw, format=lzma.FORMAT_XZ, check=check, preset=6)


class ChainEvidenceEncodingTests(unittest.TestCase):
    def test_encoder_golden_vectors_pin_fixed_xz_bytes(self) -> None:
        self.assertEqual(
            codec.encode_chain_evidence(b""),
            "<!-- FORGE:CHAIN-EVIDENCE v1 encoding=xz+base64url "
            f"bytes=0 encoded_bytes=43 sha256={EMPTY_DIGEST} -->\n"
            f"{EMPTY_XZ_PAYLOAD}\n"
            "<!-- /FORGE:CHAIN-EVIDENCE -->\n",
        )
        self.assertEqual(
            codec.encode_chain_evidence(SAMPLE),
            "<!-- FORGE:CHAIN-EVIDENCE v1 encoding=xz+base64url "
            f"bytes=21 encoded_bytes=107 sha256={SAMPLE_DIGEST} -->\n"
            f"{SAMPLE_XZ_PAYLOAD}\n"
            "<!-- /FORGE:CHAIN-EVIDENCE -->\n",
        )

    def test_encoder_calls_standard_library_with_exact_fixed_parameters(self) -> None:
        compressor = mock.Mock(return_value=b"xz")
        fake_lzma = types.SimpleNamespace(
            FORMAT_XZ=101,
            CHECK_CRC64=202,
            compress=compressor,
        )
        with mock.patch.object(codec.importlib, "import_module", return_value=fake_lzma):
            rendered = codec.encode_chain_evidence(b"raw")
        compressor.assert_called_once_with(
            b"raw", format=101, check=202, preset=6
        )
        self.assertIn("encoding=xz+base64url", rendered)
        self.assertNotIn("encoding=base64url ", rendered)

    def test_encoded_boundary_is_inclusive_then_uses_unembedded(self) -> None:
        at_limit = b"\0" * 1_572_864
        first_xz_aligned_over_limit = b"\0" * 1_572_868
        self.assertEqual(
            len(base64.urlsafe_b64encode(first_xz_aligned_over_limit).rstrip(b"=")),
            2_097_158,
        )
        compressor = mock.Mock(side_effect=[at_limit, first_xz_aligned_over_limit])
        fake_lzma = types.SimpleNamespace(
            FORMAT_XZ=lzma.FORMAT_XZ,
            CHECK_CRC64=lzma.CHECK_CRC64,
            compress=compressor,
        )
        with mock.patch.object(codec.importlib, "import_module", return_value=fake_lzma):
            embedded = codec.encode_chain_evidence(b"a")
            unembedded = codec.encode_chain_evidence(b"b")
        self.assertIn("encoded_bytes=2097152", embedded)
        self.assertIn("encoding=xz+base64url", embedded)
        self.assertEqual(len(embedded.splitlines()[1]), 2_097_152)
        self.assertIn("encoding=UNEMBEDDED", unembedded)
        self.assertNotIn("encoded_bytes=", unembedded)

    def test_raw_ceiling_and_first_over_limit_are_exact(self) -> None:
        self.assertEqual(codec.RAW_LOG_MAX_BYTES, 67_108_864)
        boundary = b"\0" * codec.RAW_LOG_MAX_BYTES
        self.assertIn(
            "bytes=67108864 encoded_bytes=",
            codec.encode_chain_evidence(boundary),
        )
        del boundary

        over_limit = b"\0" * (codec.RAW_LOG_MAX_BYTES + 1)
        with mock.patch.object(
            codec.importlib,
            "import_module",
            side_effect=AssertionError("over-limit raw bytes imported lzma"),
        ) as loader:
            rendered = codec.encode_chain_evidence(over_limit)
        loader.assert_not_called()
        self.assertIn("encoding=UNEMBEDDED bytes=67108865", rendered)

    def test_missing_lzma_refuses_exactly_without_legacy_fallback(self) -> None:
        with mock.patch.object(
            codec.importlib, "import_module", side_effect=ImportError("no lzma")
        ), self.assertRaisesRegex(
            codec.ChainEvidenceError,
            "^forge: archive refused — Python lzma module unavailable$",
        ):
            codec.encode_chain_evidence(b"raw")

    def test_encoder_requires_exact_bytes(self) -> None:
        with self.assertRaisesRegex(TypeError, "^raw chain evidence must be bytes$"):
            codec.encode_chain_evidence(bytearray(b"raw"))


class ChainEvidenceCompatibilityTests(unittest.TestCase):
    def test_both_encoding_golden_vectors_decode(self) -> None:
        self.assertEqual(codec.decode_chain_evidence(_legacy_block(SAMPLE)), SAMPLE)
        self.assertEqual(
            codec.decode_chain_evidence(
                _compressed_block(SAMPLE_XZ_PAYLOAD, len(SAMPLE), SAMPLE_DIGEST)
            ),
            SAMPLE,
        )

    def test_zero_byte_legacy_and_compressed_framing(self) -> None:
        self.assertEqual(codec.decode_chain_evidence(_legacy_block(b"")), b"")
        self.assertEqual(
            codec.decode_chain_evidence(_compressed_block(EMPTY_XZ_PAYLOAD)), b""
        )

    def test_unembedded_above_raw_ceiling_needs_no_lzma(self) -> None:
        raw_size = codec.RAW_LOG_MAX_BYTES + 1
        block = (
            "<!-- FORGE:CHAIN-EVIDENCE v1 encoding=UNEMBEDDED "
            f"bytes={raw_size} sha256={EMPTY_DIGEST} -->\n"
            "<!-- /FORGE:CHAIN-EVIDENCE -->\n"
        )
        with mock.patch.object(
            codec.importlib,
            "import_module",
            side_effect=AssertionError("UNEMBEDDED imported lzma"),
        ) as loader:
            self.assertIsNone(codec.decode_chain_evidence(block))
        loader.assert_not_called()

    def test_legacy_decoding_needs_no_lzma(self) -> None:
        with mock.patch.object(
            codec.importlib,
            "import_module",
            side_effect=AssertionError("legacy decode imported lzma"),
        ) as loader:
            self.assertEqual(codec.decode_chain_evidence(_legacy_block(SAMPLE)), SAMPLE)
        loader.assert_not_called()

    def test_legacy_raw_limit_and_canonical_payload_rules_remain_strict(self) -> None:
        oversized = _legacy_block(b"").replace("bytes=0", "bytes=2097153", 1)
        with self.assertRaisesRegex(
            codec.ChainEvidenceError, "declared raw bytes exceed limit$"
        ):
            codec.decode_chain_evidence(oversized)
        for label, payload in {
            "padding": "eA==",
            "whitespace": "eA ",
            "trailing bits": "eB",
        }.items():
            with self.subTest(label=label), self.assertRaisesRegex(
                codec.ChainEvidenceError, "malformed base64url payload$"
            ):
                codec.decode_chain_evidence(_legacy_block(b"x", payload))

        oversized_payload = _legacy_block(b"", "AAAA")
        with mock.patch.object(
            codec.base64,
            "b64decode",
            side_effect=AssertionError("legacy length guard ran after decode"),
        ) as decoder, self.assertRaisesRegex(
            codec.ChainEvidenceError, "decoded output is long$"
        ):
            codec.decode_chain_evidence(oversized_payload)
        decoder.assert_not_called()


class ChainEvidencePreImportRefusalTests(unittest.TestCase):
    def assert_pre_import_refusal(self, block: str, message: str) -> None:
        with mock.patch.object(
            codec.importlib,
            "import_module",
            side_effect=AssertionError("invalid payload imported lzma"),
        ) as loader, self.assertRaisesRegex(
            codec.ChainEvidenceError, f"^{message}$"
        ):
            codec.decode_chain_evidence(block)
        loader.assert_not_called()

    def test_header_field_and_framing_refusals_precede_import(self) -> None:
        valid = _compressed_block(EMPTY_XZ_PAYLOAD)
        header, payload, closing = valid.rstrip("\n").split("\n")
        cases = {
            "missing field": valid.replace(" encoded_bytes=43", ""),
            "extra field": valid.replace(" sha256=", " extra=1 sha256="),
            "reordered": valid.replace(
                "bytes=0 encoded_bytes=43", "encoded_bytes=43 bytes=0"
            ),
            "hybrid compressed": valid.replace(" encoded_bytes=43", ""),
            "hybrid legacy": _legacy_block(b"").replace(
                " bytes=0", " bytes=0 encoded_bytes=0"
            ),
            "unknown encoding": valid.replace("xz+base64url", "zstd+base64url"),
            "noncanonical N": valid.replace("bytes=0", "bytes=00", 1),
            "noncanonical E": valid.replace("encoded_bytes=43", "encoded_bytes=043"),
            "uppercase digest": valid.replace(EMPTY_DIGEST, EMPTY_DIGEST.upper()),
            "missing final LF": valid.rstrip("\n"),
            "CRLF": valid.replace("\n", "\r\n"),
            "missing closing": f"{header}\n{payload}\n",
            "extra line": f"{header}\n{payload}\nextra\n{closing}\n",
        }
        for label, block in cases.items():
            with self.subTest(label=label):
                self.assert_pre_import_refusal(block, codec.MALFORMED_BLOCK)

    def test_unembedded_payload_line_is_refused(self) -> None:
        block = (
            "<!-- FORGE:CHAIN-EVIDENCE v1 encoding=UNEMBEDDED "
            f"bytes=0 sha256={EMPTY_DIGEST} -->\n"
            "payload\n"
            "<!-- /FORGE:CHAIN-EVIDENCE -->\n"
        )
        self.assert_pre_import_refusal(block, codec.MALFORMED_BLOCK)

    def test_declared_n_max_and_n_max_plus_one(self) -> None:
        at_limit = _compressed_block(EMPTY_XZ_PAYLOAD, codec.RAW_LOG_MAX_BYTES)
        with mock.patch.object(
            codec.importlib, "import_module", side_effect=_ImportReached
        ) as loader, self.assertRaises(_ImportReached):
            codec.decode_chain_evidence(at_limit)
        loader.assert_called_once_with("lzma")

        over_limit = _compressed_block(
            EMPTY_XZ_PAYLOAD, codec.RAW_LOG_MAX_BYTES + 1
        )
        with mock.patch.object(
            codec,
            "_decode_base64url",
            side_effect=AssertionError("N_max guard ran after base64 decode"),
        ) as decoder:
            self.assert_pre_import_refusal(over_limit, codec.RAW_SIZE_LIMIT)
        decoder.assert_not_called()

    def test_encoded_length_binding_refuses_before_import(self) -> None:
        self.assert_pre_import_refusal(
            _compressed_block(EMPTY_XZ_PAYLOAD, encoded_size=42),
            codec.ENCODED_LENGTH_MISMATCH,
        )

    def test_padding_ascii_and_unicode_whitespace_refuse_before_import(self) -> None:
        for label, payload in {
            "padding": "AA==",
            "invalid alphabet": "AA!",
            "space": "AA ",
            "tab": "AA\t",
            "unicode whitespace": "AA\u2003",
        }.items():
            with self.subTest(label=label):
                self.assert_pre_import_refusal(
                    _compressed_block(payload), codec.MALFORMED_BASE64URL
                )

    def test_invalid_modulo_and_both_nonzero_trailing_bit_forms_precede_import(
        self,
    ) -> None:
        for label, payload in {
            "length modulo one": "A",
            "low four bits": "AB",
            "low two bits": "AAB",
        }.items():
            with self.subTest(label=label):
                self.assert_pre_import_refusal(
                    _compressed_block(payload), codec.MALFORMED_BASE64URL
                )

    def test_exact_encoded_limit_reaches_import(self) -> None:
        payload = "A" * codec.ENCODED_PAYLOAD_MAX_BYTES
        with mock.patch.object(
            codec.importlib, "import_module", side_effect=_ImportReached
        ) as loader, self.assertRaises(_ImportReached):
            codec.decode_chain_evidence(_compressed_block(payload))
        loader.assert_called_once_with("lzma")

    def test_modulo_one_over_limit_is_malformed_not_threshold_evidence(self) -> None:
        payload = "A" * 2_097_153
        self.assert_pre_import_refusal(
            _compressed_block(payload), codec.MALFORMED_BASE64URL
        )

    def test_first_valid_xz_aligned_over_limit_refuses_as_size(self) -> None:
        payload = "A" * 2_097_158
        self.assert_pre_import_refusal(
            _compressed_block(payload), codec.ENCODED_SIZE_LIMIT
        )

    def test_missing_lzma_after_canonical_payload_uses_exact_literal(self) -> None:
        with mock.patch.object(
            codec.importlib, "import_module", side_effect=ImportError("no lzma")
        ), self.assertRaisesRegex(
            codec.ChainEvidenceError,
            "^forge: chain-evidence decode refused — Python lzma module unavailable$",
        ):
            codec.decode_chain_evidence(_compressed_block(EMPTY_XZ_PAYLOAD))


class ChainEvidenceXzRefusalTests(unittest.TestCase):
    def assert_decode_refused(self, block: str, message: str) -> None:
        with self.assertRaisesRegex(codec.ChainEvidenceError, f"^{message}$"):
            codec.decode_chain_evidence(block)

    def test_decompressor_call_is_single_bounded_and_exact(self) -> None:
        calls: list[tuple[int, int]] = []
        max_lengths: list[int] = []

        class RecordingDecompressor:
            def __init__(self, *, format: int, memlimit: int) -> None:
                calls.append((format, memlimit))
                self.inner = lzma.LZMADecompressor(format=format, memlimit=memlimit)

            def decompress(self, data: bytes, max_length: int = -1) -> bytes:
                max_lengths.append(max_length)
                return self.inner.decompress(data, max_length=max_length)

            def __getattr__(self, name: str) -> object:
                return getattr(self.inner, name)

        fake_lzma = types.SimpleNamespace(
            CHECK_CRC64=lzma.CHECK_CRC64,
            FORMAT_XZ=lzma.FORMAT_XZ,
            LZMAError=lzma.LZMAError,
            LZMADecompressor=RecordingDecompressor,
        )
        with mock.patch.object(codec.importlib, "import_module", return_value=fake_lzma):
            self.assertEqual(
                codec.decode_chain_evidence(_block_for_stream(_xz(SAMPLE), SAMPLE)),
                SAMPLE,
            )
        self.assertEqual(calls, [(lzma.FORMAT_XZ, 67_108_864)])
        self.assertEqual(max_lengths, [len(SAMPLE) + 1])

    def test_malformed_and_truncated_streams_refuse(self) -> None:
        self.assert_decode_refused(
            _block_for_stream(b"not an xz stream", b""),
            codec.XZ_DECOMPRESSION_FAILED,
        )
        compressed = _xz(SAMPLE)
        self.assert_decode_refused(
            _block_for_stream(compressed[:-12], SAMPLE), codec.XZ_TRUNCATED
        )

    def test_every_decompressor_exception_refuses(self) -> None:
        fake_lzma = types.SimpleNamespace(
            CHECK_CRC64=lzma.CHECK_CRC64,
            FORMAT_XZ=lzma.FORMAT_XZ,
            LZMADecompressor=mock.Mock(side_effect=RuntimeError("unexpected")),
        )
        with mock.patch.object(
            codec.importlib, "import_module", return_value=fake_lzma
        ), self.assertRaisesRegex(
            codec.ChainEvidenceError,
            "XZ decompression failed$",
        ):
            codec.decode_chain_evidence(_compressed_block(EMPTY_XZ_PAYLOAD))

    def test_non_crc64_check_refuses(self) -> None:
        self.assert_decode_refused(
            _block_for_stream(_xz(SAMPLE, lzma.CHECK_CRC32), SAMPLE),
            codec.XZ_CHECK_INVALID,
        )

    def test_checksum_failure_refuses(self) -> None:
        corrupted = bytearray(_xz(SAMPLE))
        index_size = (int.from_bytes(corrupted[-8:-4], "little") + 1) * 4
        index_start = len(corrupted) - 12 - index_size
        corrupted[index_start - 1] ^= 1
        self.assert_decode_refused(
            _block_for_stream(bytes(corrupted), SAMPLE),
            codec.XZ_DECOMPRESSION_FAILED,
        )

    def test_multiple_stream_padding_and_trailing_data_refuse(self) -> None:
        compressed = _xz(SAMPLE)
        cases = {
            "multiple streams": compressed + _xz(b"second"),
            "stream padding": compressed + b"\0\0\0\0",
            "trailing data": compressed + b"junk",
        }
        for label, hostile in cases.items():
            with self.subTest(label=label):
                self.assert_decode_refused(
                    _block_for_stream(hostile, SAMPLE), codec.XZ_TRAILING_DATA
                )

    def test_short_and_long_output_refuse(self) -> None:
        compressed = _xz(SAMPLE)
        self.assert_decode_refused(
            _block_for_stream(compressed, SAMPLE, raw_size=len(SAMPLE) + 1),
            codec.RAW_LENGTH_SHORT,
        )
        self.assert_decode_refused(
            _block_for_stream(compressed, SAMPLE, raw_size=len(SAMPLE) - 1),
            codec.RAW_LENGTH_LONG,
        )

    def test_digest_mismatch_refuses(self) -> None:
        self.assert_decode_refused(
            _block_for_stream(_xz(SAMPLE), SAMPLE, digest=EMPTY_DIGEST),
            codec.RAW_DIGEST_MISMATCH,
        )

    def test_large_dictionary_stream_exceeds_exact_memlimit(self) -> None:
        self.assert_decode_refused(
            _compressed_block(
                LARGE_DICTIONARY_PAYLOAD,
                raw_size=1,
                digest=hashlib.sha256(b"x").hexdigest(),
            ),
            codec.XZ_DECOMPRESSION_FAILED,
        )


class ChainEvidenceActualGuardMutationTests(unittest.TestCase):
    def assert_guard_mutation(
        self,
        function: FunctionType,
        arguments: tuple[object, ...],
        message: str,
        anchor: str,
        replacement: str = "",
    ) -> None:
        def assert_refused(candidate: FunctionType) -> None:
            with self.assertRaisesRegex(codec.ChainEvidenceError, f"^{message}$"):
                candidate(*arguments)

        assert_refused(function)
        mutant = _mutated_function(function, anchor, replacement)
        with self.assertRaises(AssertionError):
            assert_refused(mutant)

    def assert_trailing_mutant_reaches_decoder(
        self, payload: str, anchor: str
    ) -> None:
        trailing_mutant = _mutated_function(
            codec._validate_trailing_bits, anchor, ""
        )
        with mock.patch.object(
            codec.base64, "b64decode", side_effect=_ImportReached
        ) as decoder, self.assertRaisesRegex(
            codec.ChainEvidenceError,
            f"^{codec.MALFORMED_BASE64URL}$",
        ):
            codec._decode_base64url(payload, str(len(payload)))
        decoder.assert_not_called()
        with mock.patch.object(
            codec.base64, "b64decode", side_effect=_ImportReached
        ), mock.patch.object(
            codec, "_validate_trailing_bits", trailing_mutant
        ), self.assertRaises(
            _ImportReached
        ):
            codec._decode_base64url(payload, str(len(payload)))

    def test_header_and_declared_raw_limit_guards_are_load_bearing(self) -> None:
        self.assert_guard_mutation(
            codec._parse_block,
            ("not a chain-evidence block",),
            codec.MALFORMED_BLOCK,
            '        return _ParsedBlock(\n'
            '            "UNEMBEDDED", match["raw"], None, match["digest"], None\n'
            '        )\n'
            '    raise ChainEvidenceError(MALFORMED_BLOCK)\n',
            '        return _ParsedBlock(\n'
            '            "UNEMBEDDED", match["raw"], None, match["digest"], None\n'
            '        )\n'
            '    return _ParsedBlock("UNEMBEDDED", "0", None, "0" * 64, None)\n',
        )
        parsed = codec._parse_block(
            _compressed_block(EMPTY_XZ_PAYLOAD, codec.RAW_LOG_MAX_BYTES + 1)
        )
        anchor = (
            "    if _decimal_above(block.raw_size, RAW_LOG_MAX_BYTES):\n"
            "        raise ChainEvidenceError(RAW_SIZE_LIMIT)\n"
        )
        mutant = _mutated_function(
            codec._decode_compressed,
            anchor,
            "",
        )
        with mock.patch.object(
            codec, "_decode_base64url", side_effect=_ImportReached
        ) as decoder:
            with self.assertRaisesRegex(
                codec.ChainEvidenceError, f"^{codec.RAW_SIZE_LIMIT}$"
            ):
                codec._decode_compressed(parsed)
            decoder.assert_not_called()
            mutant.__globals__["_decode_base64url"] = decoder
            with self.assertRaises(_ImportReached):
                mutant(parsed)

    def test_count_modulo_and_size_guards_are_load_bearing(self) -> None:
        cases = (
            (
                ("AA", "3", None),
                codec.ENCODED_LENGTH_MISMATCH,
                "        if encoded_size != str(observed_size):\n"
                "            raise ChainEvidenceError(ENCODED_LENGTH_MISMATCH)\n",
            ),
        )
        for arguments, message, anchor in cases:
            with self.subTest(message=message):
                self.assert_guard_mutation(
                    codec._validate_payload_size,
                    arguments,
                    message,
                    anchor,
                    "        pass\n",
                )

        self.assert_guard_mutation(
            codec._validate_payload_size,
            ("A" * 2_097_153, "2097153", None),
            codec.MALFORMED_BASE64URL,
            "    if remainder == 1:\n"
            "        raise ChainEvidenceError(MALFORMED_BASE64URL)\n",
        )
        self.assert_guard_mutation(
            codec._validate_payload_size,
            ("A" * 2_097_158, "2097158", None),
            codec.ENCODED_SIZE_LIMIT,
            "        if observed_size > ENCODED_PAYLOAD_MAX_BYTES:\n"
            "            raise ChainEvidenceError(ENCODED_SIZE_LIMIT)\n",
            "        pass\n",
        )

    def test_legacy_payload_prebound_is_load_bearing_before_allocation(self) -> None:
        payload = "A" * (((codec.LEGACY_RAW_MAX_BYTES * 4 + 2) // 3) + 1)
        anchor = (
            "        if observed_size > legacy_encoded_max:\n"
            "            raise ChainEvidenceError(RAW_LENGTH_LONG)\n"
        )
        mutant = _mutated_function(codec._validate_payload_size, anchor, "")
        with mock.patch.object(
            codec, "_payload_ascii", side_effect=_ImportReached
        ) as allocator:
            with self.assertRaisesRegex(
                codec.ChainEvidenceError, f"^{codec.RAW_LENGTH_LONG}$"
            ):
                codec._decode_base64url(payload, None, 0)
            allocator.assert_not_called()
            with mock.patch.object(codec, "_validate_payload_size", mutant):
                with self.assertRaises(_ImportReached):
                    codec._decode_base64url(payload, None, 0)

    def test_alphabet_and_trailing_bit_guards_are_load_bearing(self) -> None:
        self.assert_guard_mutation(
            codec._validate_payload_size,
            ("A\u2003", "2", None),
            codec.MALFORMED_BASE64URL,
            "    if not payload.isascii():\n"
            "        raise ChainEvidenceError(MALFORMED_BASE64URL)\n",
        )
        alphabet_anchor = (
            "    if _PAYLOAD.fullmatch(payload) is None:\n"
            "        raise ChainEvidenceError(MALFORMED_BASE64URL)\n"
        )
        self.assert_guard_mutation(
            codec._payload_ascii,
            ("A!A",),
            codec.MALFORMED_BASE64URL,
            alphabet_anchor,
        )
        alphabet_mutant = _mutated_function(
            codec._payload_ascii, alphabet_anchor, ""
        )
        with mock.patch.object(
            codec.base64, "b64decode", side_effect=_ImportReached
        ) as decoder:
            with self.assertRaisesRegex(
                codec.ChainEvidenceError, f"^{codec.MALFORMED_BASE64URL}$"
            ):
                codec._decode_base64url("A!A", "3")
            decoder.assert_not_called()
            with mock.patch.object(codec, "_payload_ascii", alphabet_mutant):
                with self.assertRaises(_ImportReached):
                    codec._decode_base64url("A!A", "3")

        trailing_anchor = (
            "    if _BASE64URL_VALUES[payload[-1]] & unused_mask:\n"
            "        raise ChainEvidenceError(MALFORMED_BASE64URL)\n"
        )
        for payload in ("AB", "AAB"):
            with self.subTest(payload=payload):
                self.assert_guard_mutation(
                    codec._validate_trailing_bits,
                    (payload,),
                    codec.MALFORMED_BASE64URL,
                    trailing_anchor,
                )
                self.assert_trailing_mutant_reaches_decoder(
                    payload, trailing_anchor
                )

    def test_canonical_base64_guard_is_load_bearing(self) -> None:
        anchor = (
            '    if base64.urlsafe_b64encode(decoded).rstrip(b"=") != payload_bytes:\n'
            "        raise ChainEvidenceError(MALFORMED_BASE64URL)\n"
        )
        with mock.patch.object(codec, "_validate_trailing_bits", return_value=None):
            self.assert_guard_mutation(
                codec._decode_base64url,
                ("AB", "2", None),
                codec.MALFORMED_BASE64URL,
                anchor,
            )

    def test_base64_lzma_and_decompressor_exception_mappings_are_load_bearing(
        self,
    ) -> None:
        base64_mutant = _mutated_function(
            codec._decode_base64url,
            "    except (binascii.Error, ValueError) as exc:\n"
            "        raise ChainEvidenceError(MALFORMED_BASE64URL) from exc\n",
            "    except () as exc:\n"
            "        raise ChainEvidenceError(MALFORMED_BASE64URL) from exc\n",
        )
        with mock.patch.object(codec.base64, "b64decode", side_effect=ValueError):
            with self.assertRaisesRegex(
                codec.ChainEvidenceError, f"^{codec.MALFORMED_BASE64URL}$"
            ):
                codec._decode_base64url("AA", "2")
            with self.assertRaises(ValueError):
                base64_mutant("AA", "2")

        load_mutant = _mutated_function(
            codec._load_lzma,
            "    except ImportError as exc:\n"
            "        raise ChainEvidenceError(refusal) from exc\n",
            "    except () as exc:\n"
            "        raise ChainEvidenceError(refusal) from exc\n",
        )
        with mock.patch.object(
            codec.importlib, "import_module", side_effect=ImportError
        ):
            with self.assertRaisesRegex(
                codec.ChainEvidenceError, f"^{codec.DECODE_LZMA_UNAVAILABLE}$"
            ):
                codec._load_lzma(codec.DECODE_LZMA_UNAVAILABLE)
            with self.assertRaises(ImportError):
                load_mutant(codec.DECODE_LZMA_UNAVAILABLE)

        fake_lzma = types.SimpleNamespace(
            FORMAT_XZ=lzma.FORMAT_XZ,
            LZMADecompressor=mock.Mock(side_effect=RuntimeError("disabled")),
        )
        decompress_mutant = _mutated_function(
            codec._decompress_xz,
            "    except Exception as exc:\n"
            "        raise ChainEvidenceError(XZ_DECOMPRESSION_FAILED) from exc\n",
            "    except () as exc:\n"
            "        raise ChainEvidenceError(XZ_DECOMPRESSION_FAILED) from exc\n",
        )
        with self.assertRaisesRegex(
            codec.ChainEvidenceError, f"^{codec.XZ_DECOMPRESSION_FAILED}$"
        ):
            codec._decompress_xz(b"xz", 0, fake_lzma)
        with self.assertRaises(RuntimeError):
            decompress_mutant(b"xz", 0, fake_lzma)

    def test_memlimit_and_one_byte_probe_are_load_bearing(self) -> None:
        calls: list[tuple[int, int | None]] = []
        limits: list[int] = []

        class RecordingDecompressor:
            eof = True
            needs_input = True

            def __init__(self, *, format: int, memlimit: int | None) -> None:
                calls.append((format, memlimit))

            def decompress(self, _data: bytes, max_length: int) -> bytes:
                limits.append(max_length)
                return b""

        fake_lzma = types.SimpleNamespace(
            FORMAT_XZ=lzma.FORMAT_XZ,
            LZMADecompressor=RecordingDecompressor,
        )

        def assert_resources(function: FunctionType) -> None:
            calls.clear()
            limits.clear()
            function(b"xz", 0, fake_lzma)
            self.assertEqual(calls, [(lzma.FORMAT_XZ, 67_108_864)])
            self.assertEqual(limits, [1])

        assert_resources(codec._decompress_xz)
        memlimit_mutant = _mutated_function(
            codec._decompress_xz,
            "            format=lzma.FORMAT_XZ, memlimit=LZMA_MEMLIMIT\n",
            "            format=lzma.FORMAT_XZ, memlimit=None\n",
        )
        with self.assertRaises(AssertionError):
            assert_resources(memlimit_mutant)

        class LimitSensitiveDecompressor:
            eof = True
            needs_input = True

            def __init__(self, *, format: int, memlimit: int | None) -> None:
                if memlimit is not None:
                    raise RuntimeError("dictionary exceeds configured limit")

            def decompress(self, _data: bytes, max_length: int) -> bytes:
                return b"x"

        limit_sensitive_lzma = types.SimpleNamespace(
            FORMAT_XZ=lzma.FORMAT_XZ,
            LZMADecompressor=LimitSensitiveDecompressor,
        )
        with self.assertRaisesRegex(
            codec.ChainEvidenceError, f"^{codec.XZ_DECOMPRESSION_FAILED}$"
        ):
            codec._decompress_xz(b"xz", 1, limit_sensitive_lzma)
        self.assertEqual(
            memlimit_mutant(b"xz", 1, limit_sensitive_lzma)[0],
            b"x",
        )

        probe_mutant = _mutated_function(
            codec._decompress_xz,
            "        chunk = decompressor.decompress(compressed, max_length=raw_size + 1)\n",
            "        chunk = decompressor.decompress(compressed, max_length=raw_size)\n",
        )
        with self.assertRaises(AssertionError):
            assert_resources(probe_mutant)

    def test_xz_terminal_length_and_digest_guards_are_load_bearing(self) -> None:
        self.assert_guard_mutation(
            codec._append_output,
            ([], hashlib.sha256(), b"x", 0, 0),
            codec.RAW_LENGTH_LONG,
            "    if total > raw_size:\n"
            "        raise ChainEvidenceError(RAW_LENGTH_LONG)\n",
        )
        good = types.SimpleNamespace(
            check=lzma.CHECK_CRC64,
            eof=True,
            unused_data=b"",
        )
        cases = (
            (
                (
                    b"",
                    EMPTY_DIGEST,
                    types.SimpleNamespace(
                        **{**vars(good), "check": lzma.CHECK_CRC32}
                    ),
                    0,
                    EMPTY_DIGEST,
                    lzma,
                ),
                codec.XZ_CHECK_INVALID,
                "    if decompressor.check != lzma.CHECK_CRC64:\n"
                "        raise ChainEvidenceError(XZ_CHECK_INVALID)\n",
            ),
            (
                (
                    b"",
                    EMPTY_DIGEST,
                    types.SimpleNamespace(**{**vars(good), "eof": False}),
                    0,
                    EMPTY_DIGEST,
                    lzma,
                ),
                codec.XZ_TRUNCATED,
                "    if not decompressor.eof:\n"
                "        raise ChainEvidenceError(XZ_TRUNCATED)\n",
            ),
            (
                (
                    b"",
                    EMPTY_DIGEST,
                    types.SimpleNamespace(
                        **{**vars(good), "unused_data": b"x"}
                    ),
                    0,
                    EMPTY_DIGEST,
                    lzma,
                ),
                codec.XZ_TRAILING_DATA,
                "    if decompressor.unused_data:\n"
                "        raise ChainEvidenceError(XZ_TRAILING_DATA)\n",
            ),
            (
                (b"", EMPTY_DIGEST, good, 1, EMPTY_DIGEST, lzma),
                codec.RAW_LENGTH_SHORT,
                "    if len(raw) < expected_size:\n"
                "        raise ChainEvidenceError(RAW_LENGTH_SHORT)\n",
            ),
            (
                (
                    b"x",
                    hashlib.sha256(b"x").hexdigest(),
                    good,
                    0,
                    hashlib.sha256(b"x").hexdigest(),
                    lzma,
                ),
                codec.RAW_LENGTH_LONG,
                "    if len(raw) > expected_size:\n"
                "        raise ChainEvidenceError(RAW_LENGTH_LONG)\n",
            ),
            (
                (
                    b"x",
                    hashlib.sha256(b"x").hexdigest(),
                    good,
                    1,
                    EMPTY_DIGEST,
                    lzma,
                ),
                codec.RAW_DIGEST_MISMATCH,
                "    if observed_digest != expected_digest:\n"
                "        raise ChainEvidenceError(RAW_DIGEST_MISMATCH)\n",
            ),
        )
        for arguments, message, anchor in cases:
            with self.subTest(message=message):
                self.assert_guard_mutation(
                    codec._verify_xz,
                    arguments,
                    message,
                    anchor,
                )

    def test_legacy_digest_guard_is_load_bearing(self) -> None:
        block = codec._parse_block(
            _legacy_block(SAMPLE).replace(SAMPLE_DIGEST, EMPTY_DIGEST, 1)
        )
        self.assert_guard_mutation(
            codec._decode_legacy,
            (block,),
            codec.RAW_DIGEST_MISMATCH,
            "    if hashlib.sha256(raw).hexdigest() != block.digest:\n"
            "        raise ChainEvidenceError(RAW_DIGEST_MISMATCH)\n",
        )


class ChainEvidenceArchiveIntegrationTests(unittest.TestCase):
    def test_no_cited_chain_never_reaches_lzma(self) -> None:
        package = archive.ChainPackage(None, None, (), ())
        bindings = archive.binding_history.ResolvedBindings({}, {})
        with mock.patch.object(
            codec.importlib,
            "import_module",
            side_effect=AssertionError("empty chain section imported lzma"),
        ) as loader:
            rendered = archive.render_chain_sections(package, [], bindings, [])
        loader.assert_not_called()
        self.assertEqual(rendered, ["## Chain evidence", "", archive.NONE, ""])

    def test_same_compressor_bytes_are_equal_and_changed_bytes_mismatch(self) -> None:
        candidate = codec.encode_chain_evidence(SAMPLE)
        rerendered = codec.encode_chain_evidence(SAMPLE)
        self.assertEqual(candidate.encode(), rerendered.encode())

        alternate = lzma.compress(
            SAMPLE,
            format=lzma.FORMAT_XZ,
            check=lzma.CHECK_CRC64,
            preset=0,
        )
        fake_lzma = types.SimpleNamespace(
            FORMAT_XZ=lzma.FORMAT_XZ,
            CHECK_CRC64=lzma.CHECK_CRC64,
            compress=mock.Mock(return_value=alternate),
        )
        with mock.patch.object(codec.importlib, "import_module", return_value=fake_lzma):
            changed = codec.encode_chain_evidence(SAMPLE)
        self.assertNotEqual(candidate.encode(), changed.encode())
        self.assertEqual(codec.decode_chain_evidence(changed), SAMPLE)

    def test_renderer_wrapper_and_cli_lzma_reason_mapping_are_exact(self) -> None:
        error = codec.ChainEvidenceError(codec.ARCHIVE_LZMA_UNAVAILABLE)
        wrapper_mutant = _mutated_function(
            archive.render_chain_event_block,
            "        if str(exc) == chain_evidence_codec.ARCHIVE_LZMA_UNAVAILABLE:\n",
            "        if False:\n",
        )
        with mock.patch.object(
            codec, "encode_chain_evidence", side_effect=error
        ), self.assertRaisesRegex(
            archive.ArchiveRefusal,
            "^forge: archive refused — Python lzma module unavailable$",
        ):
            archive.render_chain_event_block(b"raw")
        with mock.patch.object(codec, "encode_chain_evidence", side_effect=error):
            with self.assertRaises(codec.ChainEvidenceError):
                wrapper_mutant(b"raw")

        def refuse(**_kwargs: object) -> bytes:
            raise archive.ArchiveRefusal(codec.ARCHIVE_LZMA_UNAVAILABLE)

        renderer = types.SimpleNamespace(render_archive_candidate=refuse)
        context = types.SimpleNamespace(
            store=types.SimpleNamespace(common_root=Path("/common")),
            repo=types.SimpleNamespace(root=Path("/repo")),
        )
        metadata = {
            "run_id": "run-test",
            "post_close_validation": "/validation",
        }

        def assert_lzma_reason(function: FunctionType) -> None:
            with self.assertRaises(envelope.Refusal) as raised:
                function(context, metadata)
            refusal = raised.exception
            self.assertEqual(refusal.reason_code.value, "lzma-unavailable")
            self.assertEqual(refusal.schema, "forge-cli/2")
            self.assertEqual(refusal.outcome().exit_code, 1)

        with mock.patch.object(
            archive_engine, "_archive_module", return_value=renderer
        ):
            assert_lzma_reason(archive_engine._render_archive_bytes)

        call_site_mutant = _mutated_function(
            archive_engine._render_archive_bytes,
            "            raise _archive_renderer_refusal(\n",
            "            raise _archive_refusal(\n",
        )
        call_site_mutant.__globals__["_archive_module"] = lambda: renderer
        with self.assertRaises(AssertionError):
            assert_lzma_reason(call_site_mutant)


if __name__ == "__main__":
    unittest.main()
