from __future__ import annotations

import hashlib
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = (ROOT / "docs/specs/forge-plugin-spec.md").read_text(encoding="utf-8")

# Task TA removes all thirty-one markers and empties this set after implementation lands.
DEFERRED = frozenset({"TA"})
RUN_ID = "run-20261004-backfill"
AUTHORITY_MARKER = "(Revision 21 authority; deferred to task TA of run-20261004-backfill)"
MARKER_RE = re.compile(r"\(Revision 21 authority;[^)]*\)")
EXPECTED_MARKER_COUNT = 31

ENCODED_PAYLOAD_LIMIT = "2,097,152"
FIRST_VALID_OVER_LIMIT = "2,097,158"
INVALID_BASE64URL_LENGTH = "2,097,153"
RAW_LOG_CEILING = "67,108,864"
RESOURCE_LIMIT_LITERAL = "67_108_864"
DECOMPRESSOR_LITERAL = (
    "lzma.LZMADecompressor(format=lzma.FORMAT_XZ, memlimit=67_108_864)"
)
RENDERER_LZMA_REFUSAL = "forge: archive refused — Python lzma module unavailable"
DECODER_LZMA_REFUSAL = (
    "forge: chain-evidence decode refused — Python lzma module unavailable"
)
LZMA_REASON = "lzma-unavailable"

HEADER_LITERALS = (
    "**Revised**: 2026-10-05",
    "**Status**: Draft (Revision 21)",
    (
        "**Revision 21 marker scope**: A Revision-21 marker scopes only the Revision-21 "
        "sentence(s) it directly follows, never older in-force text on the same line; task TA "
        "removes each task marker only after the named implementation lands."
    ),
)

NEW_HEADER = (
    "<!-- FORGE:CHAIN-EVIDENCE v1 encoding=xz+base64url bytes=N encoded_bytes=E sha256=H -->"
)
LEGACY_HEADER = "<!-- FORGE:CHAIN-EVIDENCE v1 encoding=base64url bytes=N sha256=H -->"
UNEMBEDDED_BLOCK = (
    "<!-- FORGE:CHAIN-EVIDENCE v1 encoding=UNEMBEDDED bytes=N sha256=H -->\n"
    "<!-- /FORGE:CHAIN-EVIDENCE -->"
)
ARCHIVE_REFUSAL = "forge: archive refused — rendered archive exceeds 16 MiB"
ARCHIVE_SIZE_ROW = (
    "| Final rendered UTF-8 archive exceeds 16,777,216 bytes | archive renderer / "
    "archive commit mode | refusal, `forge: archive refused — rendered archive "
    "exceeds 16 MiB`; `archive-size-limit` | Checked before creating or replacing a "
    "destination; no estimator or truncation |"
)

PARAGRAPH_HEADINGS = {
    "NON_GOALS": "Revision-21 size-control amendment to **Revision 9 Non-goals**:",
    "DM012": "Revision-21 compressed-evidence amendment to **DM-012**",
    "DM016": "Revision-21 amendment to **DM-016**:",
    "FR170": "Revision-21 compression amendment to **FR-170** archive mode:",
    "FR171": "Revision-21 compression amendment to **FR-171 contents**:",
    "FR173": "Revision-21 compressor-build residual for **FR-173** and **DM-008**:",
    "FORMAT8": "Revision-21 archive-format amendment:",
    "FR220": "Revision-21 `forge-cli/2` reason-union amendment to **FR-220**:",
    "SC029": "Revision-21 amendment to **SC-029**:",
}

LINE_PREFIXES = {
    "ERR_UNEMBEDDED": "| Revision-21 raw event log exceeds",
    "ERR_RENDERER_LZMA": "| Revision-21 rendering has passed journal",
    "ERR_ARCHIVE_SIZE": "| Revision-21 compression is active and the final",
    "ERR_RERENDER": "| Revision-21 compressed archive candidate differs",
    "TEST_PLAN": "- Revision-21 compressed-chain-evidence tests cover",
    "TRACEABILITY": ("| DM-008/DM-012; FR-170..FR-174 | Revision-21 compressed chain-evidence"),
}

SCENARIO_HEADINGS = {
    "LEGACY_BOUNDARY": (
        "### Scenario: Archive embeds exact chain evidence and commits only equal bytes"
    ),
    "ENCODED_BOUNDARY": (
        "### Scenario: Revision-21 archive embeds compressed evidence at encoded boundaries"
    ),
    "COMPATIBILITY": (
        "### Scenario: Exact XZ-plus-base64url evidence and legacy decode compatibility"
    ),
    "UNSAFE_EVIDENCE": "### Scenario: Unsafe or ambiguous compressed evidence refuses",
}

SCENARIO_MARKER_COUNTS = {
    "ENCODED_BOUNDARY": 6,
    "COMPATIBILITY": 5,
    "UNSAFE_EVIDENCE": 5,
}

AMENDMENT_LITERALS = {
    "NON_GOALS": (
        "one-line unpadded base64url payload after DM-012's exact XZ compression",
        "not the raw event-log length",
        f"at most {ENCODED_PAYLOAD_LIMIT} bytes is embedded",
        f"above {ENCODED_PAYLOAD_LIMIT} bytes uses the unchanged digest-only "
        "`encoding=UNEMBEDDED` block",
        f"`N_max` is {RAW_LOG_CEILING} bytes (64 MiB)",
        "`scripts/codex_orchestrator/builders.py`'s activation-replay "
        f"`_ACTIVATION_EVENTS_CAP_BYTES = {RESOURCE_LIMIT_LITERAL}`",
        "a larger raw log uses the unchanged `UNEMBEDDED` form without compression",
        "a compressed-block decoder refuses a declared `N` above that ceiling",
        "it is not an archive-cap increase",
        "does not invalidate an `UNEMBEDDED` declaration above it",
        "16 MiB (16,777,216 bytes)",
        "event-format changes",
        "local retention or pruning",
        "automatic garbage collection",
        "every cap increase remain out of scope",
    ),
    "DM012": (
        f"`N` exceeds `N_max = {RAW_LOG_CEILING}`",
        "writes the unchanged digest-only `encoding=UNEMBEDDED` block without compression",
        "lzma.compress(raw, format=lzma.FORMAT_XZ, check=lzma.CHECK_CRC64, preset=6)",
        "default preset 6 filter chain with no custom filters",
        'base64.urlsafe_b64encode(compressed).rstrip(b"=")',
        NEW_HEADER,
        "`E` is the exact ASCII byte length of the payload line excluding its LF",
        "`H` is the lowercase SHA-256 of the raw event-log bytes",
        "canonical nonnegative decimal (`0` or a nonzero digit followed by digits)",
        "the fields and spaces occur only in that order",
        f"`E` is at most {ENCODED_PAYLOAD_LIMIT} bytes",
        "existing digest-only `UNEMBEDDED` block applies unchanged",
        "candidate, start, authorization, and commit rerenders use exact whole-archive byte "
        "equality, including every compressed header and payload byte",
        f"`E` equal to the observed line length and no greater than {ENCODED_PAYLOAD_LIMIT}",
        f"`N` no greater than {RAW_LOG_CEILING}",
        "only the unpadded base64url alphabet `[A-Za-z0-9_-]*`",
        "any ASCII or Unicode whitespace",
        "a length congruent to 1 modulo 4",
        "nonzero unused trailing bits in the final base64url sextet",
        "low four bits when `E % 4 == 2`",
        "low two bits when `E % 4 == 3`",
        "noncanonical or malformed base64url",
        "any missing, extra, reordered, or mixed-encoding field",
        "rejects a declared `N` above `N_max` before base64url decoding or decompressor "
        "construction",
        DECOMPRESSOR_LITERAL,
        "without preallocating `N` or materializing unbounded output",
        "`N` raw bytes plus a one-byte overflow probe",
        f"The {RAW_LOG_CEILING}-byte (64 MiB) decompressor memory limit",
        "roughly 9 MiB required by preset 6",
        "bounding hostile dictionaries and filter chains",
        "any stream whose dictionary or filter chain requires more is refused",
        "decompressor.check == lzma.CHECK_CRC64",
        "end-of-stream after all compressed input",
        "empty `unused_data`",
        "exactly one .xz stream",
        "exactly `N` output bytes",
        "malformed or truncated XZ",
        "a non-CRC64 check",
        "checksum failure",
        "every decompression exception",
        "short output, long output, trailing data or stream padding, and multiple streams",
        "first imports the standard-library `lzma` module only when rendering reaches an "
        "event log",
        RENDERER_LZMA_REFUSAL,
        "never falls back to legacy base64url",
        "no cited event log, or with every cited event log above `N_max`, never imports `lzma`",
        "compressed-block decoder imports `lzma` only after it reaches an "
        "`encoding=xz+base64url` payload",
        "completes that payload line's framing, alphabet, length-modulo, and canonical "
        "trailing-bit validation",
        "Payload canonicality therefore belongs to the pre-import validation",
        "a payload with nonzero unused trailing bits",
        "one malformed under another pre-import framing, alphabet, or length-modulo check",
        "If the import is unavailable only after all those checks pass",
        DECODER_LZMA_REFUSAL,
        "Decoding already committed `encoding=base64url` and `encoding=UNEMBEDDED` forms "
        "remains available without importing `lzma`",
        "Archives already committed with `encoding=base64url` remain valid and decodable",
        f"raw {ENCODED_PAYLOAD_LIMIT}-byte threshold, without `encoded_bytes`",
        "the renderer writes only `encoding=xz+base64url` for an embedded event log",
        "Unknown or hybrid forms fail closed",
    ),
    "DM016": (
        f"new `{LZMA_REASON}` reason reserves the next additive reason-code generation after v5",
        "system/fr223/reason-codes-v6.json",
        ".forge/evals/tasks/fr223-reason-code-enum-v6.md",
        ".forge/evals/tasks/fr223-reason-code-enum-v6.result",
        ".forge/evals/tasks/fr223-reason-code-enum-v6.manifest.json",
        "corpus schema is `fr223-reason-codes/6`",
        "manifest schema is `fr223-reason-code-enum-manifest/6`",
        "predecessor array binds generations 1 through 5 in order",
        "no v1-v5 artifact or row is edited or reminted",
    ),
    "FR170": (
        "fixed compression parameters",
        "raw `N_max` disposition",
        "encoded-payload threshold and final archive cap",
        "fresh deterministic render",
        "within-chain candidate equality: byte equality of the whole archive",
        "including every compressed byte",
        "different bytes within that chain fails closed as a rerender mismatch",
        "16,777,216-byte final archive cap",
        "pre-destination-mutation timing",
        "its refusal remain unchanged",
    ),
    "FR171": (
        f"raw length `N` above {RAW_LOG_CEILING}",
        "unchanged visible digest-only `encoding=UNEMBEDDED` block without compression",
        "`N` at or below that ceiling",
        "exact `encoding=xz+base64url` header and payload",
        f"compressed payload line above {ENCODED_PAYLOAD_LIMIT} bytes",
        "payload threshold is encoded size",
        f"a raw log above {ENCODED_PAYLOAD_LIMIT} bytes may embed",
        "a raw log at or below that size is `UNEMBEDDED`",
        "An `UNEMBEDDED` declaration remains valid when `N` exceeds `N_max`",
        "Exact state carriage",
        "visible `UNBOUND` rule are unchanged",
    ),
    "FR173": (
        "compressor build change between the archive commit and a later `/forge:report` rerender",
        "forge: report refused — committed archive differs from deterministic rerender: "
        ".forge/history/runs/<run-id>.md",
        "known residual is tracked by bead `forge-plugin-c2i8`",
        "`/forge:report` normally runs immediately after the archive commit on the same host",
    ),
    "FORMAT8": (
        "decoder grammar for already committed `encoding=base64url` archives",
        "an `UNEMBEDDED` declaration remains valid above `N_max`",
        NEW_HEADER,
        "one unpadded base64url line encoding the single XZ stream",
        "`N` and `H` name the raw event-log bytes",
        "`E` names the payload line's ASCII byte length excluding LF",
        f"Raw `N > {RAW_LOG_CEILING}` writes `UNEMBEDDED` before compression",
        f"`E <= {ENCODED_PAYLOAD_LIMIT}` embeds",
        "canonical decimal counts",
        f"`N <= {RAW_LOG_CEILING}`",
        "64 lowercase-hex `H`",
        "canonical unpadded whitespace-free base64url",
        "one `FORMAT_XZ` stream with `CRC64`",
        DECOMPRESSOR_LITERAL,
        "bounds streaming output to exactly `N` bytes plus the one-byte overflow probe",
        "end-of-stream with no trailing input or `unused_data`",
        "raw SHA-256 equal to `H`",
        "refuses a dictionary or filter chain above that memory limit",
        "short output, long output, trailing data, multiple streams",
        "padding or whitespace",
        "malformed base64url or XZ",
        "a wrong check",
        "a count or digest mismatch",
        "every unknown or hybrid encoding",
        "one-byte overflow probe does not authorize an extra output byte",
        "Without `lzma`, compressed decoding uses the exact DM-012 refusal",
        "legacy `encoding=base64url` and `encoding=UNEMBEDDED` decoding remain available",
        "Archives already committed with `encoding=base64url` remain valid and decodable",
        "renderer writes only `encoding=xz+base64url` for a new embedded block",
        "16,777,216-byte pre-mutation final cap remain in force",
    ),
    "FR220": (
        "no existing reason member is broadened to cover compression capability",
        "additive `fr223-reason-codes/6` corpus",
        "complete sorted 56-member union",
        "every v5 row byte-identical",
        f"exactly `{LZMA_REASON}` with exit class 1",
        "Required Revision-21 XZ compression reached its import point and the Python "
        "standard-library lzma module is unavailable",
        "Revision-21 renderer refusal in §9 uses this reason code when surfaced through "
        "`forge-cli/2`",
    ),
    "ERR_UNEMBEDDED": (
        f"raw event log exceeds {RAW_LOG_CEILING} bytes",
        f"encoded event payload line exceeds {ENCODED_PAYLOAD_LIMIT} bytes",
        "unchanged digest-only block with `encoding=UNEMBEDDED`",
        "replaces the legacy `Chain event log exceeds 2,097,152 bytes` condition",
        "retaining its `digest-only block with encoding=UNEMBEDDED; rendering continues` result",
        "raw ceiling is applied before compression and the encoded ceiling afterward",
        "payload is never truncated or split",
        "an `UNEMBEDDED` declaration above the raw ceiling remains valid",
        "legacy committed `encoding=base64url` remains governed by its inherited raw threshold",
    ),
    "ERR_RENDERER_LZMA": (
        "passed journal, binding, and applicable legacy/backfill approval validation",
        f"first event log with `N <= {RAW_LOG_CEILING}`",
        "Python standard-library `lzma` module is unavailable",
        RENDERER_LZMA_REFUSAL,
        f"`{LZMA_REASON}` for `forge-cli/2`",
        "Earlier journal, binding, and applicable approval refusals retain precedence",
        "fires at the first log that requires compression",
        "before its encoded-size disposition, the final archive-cap check, or any same-chain "
        "rerender equality check",
        "no cited event log, or only logs with `N > 67,108,864`, never imports `lzma`",
    ),
    "ERR_ARCHIVE_SIZE": (
        "final rendered UTF-8 archive exceeds 16,777,216 bytes",
        "`forge: archive refused — rendered archive exceeds 16 MiB`; `archive-size-limit`",
        "16,777,216-byte cap",
        "refusal literal",
        "pre-destination check",
        "no-truncation rule remain byte-identical",
    ),
    "ERR_RERENDER": (
        "compressed archive candidate differs from a fresh rerender within the same "
        "archive-creation chain",
        "`forge: archive refused — rerendered bytes differ from candidate`; "
        "`archive-rerender-mismatch`",
        "Whole-archive byte equality includes every compressed header and payload byte",
    ),
    "TEST_PLAN": (
        "exact `xz+base64url` header and field order",
        "fixed `FORMAT_XZ`, default preset-6 filter chain, and `CHECK_CRC64` output",
        "raw length/digest and encoded-length bindings",
        "golden decoder vectors for both `encoding=base64url` and `encoding=xz+base64url`",
        "nonempty compressed payload for zero raw bytes",
        "inherited empty legacy payload",
        "decoder-framing-only inputs",
        f"encoded payloads exactly {ENCODED_PAYLOAD_LIMIT} bytes",
        f"first XZ-aligned valid over-limit length {FIRST_VALID_OVER_LIMIT}",
        f"{INVALID_BASE64URL_LENGTH} separately refused as malformed base64url rather than "
        "threshold evidence",
        f"raw lengths exactly {RAW_LOG_CEILING} and 67,108,865",
        "renders `UNEMBEDDED` before compression",
        "such an `UNEMBEDDED` declaration remains valid",
        f"exact `memlimit={RESOURCE_LIMIT_LITERAL}`",
        "preset-6's roughly 9 MiB need",
        "excessive-dictionary/filter refusal",
        "missing, extra, reordered, mixed, padded, whitespace-bearing, noncanonical",
        "nonzero-unused-trailing-bit header/payload cases",
        "both `E % 4 == 2` and `E % 4 == 3` trailing-bit forms refused before importing `lzma`",
        "wrong-check, checksum-failing, short-output",
        "long-output, trailing-data",
        "stream-padding, multiple-stream, and digest-mismatch XZ cases",
        "bounded streaming with the sole one-byte overflow probe",
        "same-chain whole-archive byte mismatch under different compression bytes",
        "both exact missing-`lzma` refusals",
        f"renderer refusal's `{LZMA_REASON}` reason",
        "no renderer import when no cited log requires compression",
        "no decoder import before payload framing and canonicality pass",
        "legacy and `UNEMBEDDED` decoding without that module",
        "new-write-only compressed encoding",
        "unchanged legacy decoding, `UNEMBEDDED` framing, 16,777,216-byte cap",
        "archive-size refusal",
        "whole-archive report equality with the documented compressor-build residual",
    ),
    "SC029": (
        "exact raw length and digest",
        "deterministic preset-6 CRC64 XZ stream's unpadded base64url payload",
        f"Raw length above {RAW_LOG_CEILING} writes the unchanged visible digest-only "
        "`UNEMBEDDED` block before compression",
        f"payload length through {ENCODED_PAYLOAD_LIMIT} bytes embeds",
        "a greater payload length selects the same form",
        f"Decoding uses `memlimit={RESOURCE_LIMIT_LITERAL}`",
        "exactly one complete raw stream",
        "no padding, whitespace, short or long output, trailing data, or second stream",
        "declared-raw-length ceiling and one-byte overflow probe",
        "Existing `encoding=base64url` archives remain decodable",
        "including without `lzma`",
        "new rendering emits only `encoding=xz+base64url` when embedded",
        "Within one archive-creation chain every candidate rerender remains whole-archive "
        "byte-exact, including compressed bytes",
        "16 MiB final cap and all other SC-029 conditions remain unchanged",
    ),
    "TRACEABILITY": (
        "Revision-21 compressed chain-evidence carriage",
        "Revision-21 archive embeds compressed evidence at encoded boundaries",
        "Exact XZ-plus-base64url evidence and legacy decode compatibility",
        "Unsafe or ambiguous compressed evidence refuses",
        "exact header/length/digest grammar",
        "fixed compressor output",
        "encoded-size and raw-size boundaries",
        "both decoder families",
        "64 MiB decompressor and raw ceilings",
        "bounded streaming/short/long/trailing/multiple-stream/checksum/hash negatives",
        "nonzero trailing-bit refusal before `lzma` import",
        "both exact missing-`lzma` refusals",
        "additive renderer reason",
        "same-chain whole-archive byte equality",
        "documented whole-archive report-refusal residual",
        "unchanged final cap",
        "large compressible chain package archives below the unchanged cap",
        "same-chain incompatible compressed bytes fail closed",
        "Success: SC-029",
    ),
}

SCENARIO_LITERALS = {
    "ENCODED_BOUNDARY": (
        "**Traces to**: DM-008, DM-012, FR-170, FR-171, FR-174",
        "**Category**: Error Path",
        "replaces only the first five `Given`/`When`/`Then`/`When`/`Then` bullets of "
        "`### Scenario: Archive embeds exact chain evidence and commits only equal bytes`",
        "unmarked `But` refusal bullet remains in force",
        f"raw length satisfies `N <= {RAW_LOG_CEILING}`",
        "compressed unpadded base64url payload has encoded length "
        f"`E = {ENCODED_PAYLOAD_LIMIT}`",
        "`commit start --archive-run-id <run-id>` begins",
        "event block uses `encoding=xz+base64url`",
        "start, authorization, and commit each require exact whole-archive byte equality "
        "including the compressed bytes",
        "archive-only index state",
        "another otherwise-valid compressed payload under the same raw ceiling",
        "first XZ-aligned encoded length above the boundary, "
        f"`E = {FIRST_VALID_OVER_LIMIT}`",
        "unchanged digest/count block labeled `UNEMBEDDED`",
        f"`{INVALID_BASE64URL_LENGTH}` is malformed base64url and is not threshold evidence",
    ),
    "COMPATIBILITY": (
        "**Traces to**: DM-012, FR-170, FR-171",
        "**Category**: Edge Case",
        f"new-render raw event log at or below `N_max = {RAW_LOG_CEILING}`",
        "fixed preset-6 CRC64 XZ compressor",
        "distinct committed legacy `encoding=base64url` block",
        f"raw `N` is at most {ENCODED_PAYLOAD_LIMIT}",
        "applicable decoder verifies an embedded payload's exact framing",
        "new block binds raw `N`, encoded `E`, and raw `H`",
        f"inherited raw {ENCODED_PAYLOAD_LIMIT}-byte threshold without importing `lzma`",
        "same-chain candidate rerenders compare every archive byte exactly",
        "raw event log above `N_max` renders as the unchanged valid `UNEMBEDDED` form before "
        "compression",
        "declared `N` or `H` that does not match the decoded raw bytes",
        "invalid framing, or an invalid compressed stream refuses",
    ),
    "UNSAFE_EVIDENCE": (
        "**Traces to**: DM-012, FR-170, FR-171",
        "**Category**: Error Path",
        "excessive declared raw length",
        "excessive decoder-memory demand",
        "ambiguous base64url or XZ framing",
        "unavailable Python `lzma` support",
        f"rejects `N > {RAW_LOG_CEILING}` before decoding",
        f"dictionary or filter chain above `memlimit={RESOURCE_LIMIT_LITERAL}`",
        f"encoded length {INVALID_BASE64URL_LENGTH} as malformed base64url rather than "
        "over-threshold evidence",
        "rejects nonzero unused trailing bits before importing `lzma`",
        "refuses any missing, extra, reordered, or mixed-encoding header field",
        "short or long output, padding, whitespace, trailing data, stream padding, multiple "
        "streams, wrong checks, checksum failure, digest mismatch, and malformed base64url or "
        "XZ all refuse",
        RENDERER_LZMA_REFUSAL,
        DECODER_LZMA_REFUSAL,
        f"uses `{LZMA_REASON}` through `forge-cli/2`",
        "never falls back",
        "no effect on legacy base64url or `UNEMBEDDED` decoding",
    ),
}

# Filled from the marker-stripped exact amendment text.
AMENDMENT_SHA256 = {
    "NON_GOALS": "519ed49785355ab5e32fd99cbc1c32acb3c9ba654ed17b123c6f9ab0c5090a4b",
    "DM012": "7b4914334f7a0e6766266f616cd57b499566c3a95fe5b9065fced7211878fd49",
    "DM016": "c7fa69728e368b6c8d300ee91e4471d27f3c5d89a322a6d10d60f252c8659095",
    "FR170": "40aabfcae1014f9621f4860111fc0346c7cd3b7c98adce1624e1878fd2641d7a",
    "FR171": "02b426db537525e4cb9c966befcc50b01f48355b09a7cffc0d0003c230ac79cd",
    "FR173": "fae90c2afb5d72a2c0b8f11c061718eb7b3f295112dc3e86a3de391d8e21ae3c",
    "FORMAT8": "d45a9825fc29743b395855f9c2692ea5145db714116e00b0113a622b02a265c4",
    "FR220": "4437e68ea5ab815f54947492fdd8f8293718e6b90bbd434e1b2bfd0401111be1",
    "ERR_UNEMBEDDED": "5a0f703fed5dd98162207ab3255df3a8202924dea778ceb5dbac9cb236867c82",
    "ERR_RENDERER_LZMA": "54ef5ad97392946b84c3a2ddc1c9d9bce7d791b78be95efc3e845459aec3e485",
    "ERR_ARCHIVE_SIZE": "9d9bcf89504d61de5daf97ee908860b7d057f450fa0481663b9b726bd87b25a8",
    "ERR_RERENDER": "f87d4c65957f51da2c99d6aa4112b9d267bb1a14ed6d8d64222f7b713409f06c",
    "TEST_PLAN": "7f296d808d9b56c419c7f77159467b450200b00d6e9c4ad991711d24aa5b2741",
    "SC029": "39a2f52b5ba084d21d0e8d5ee4ede78ac9936374f208517e0171a22c56baca4c",
    "TRACEABILITY": "f9b43a8c7939e2748549d8ca04f1eb2fb87e0b87b463bba836e714bf2424ae42",
}

# Filled from the marker-stripped exact scenario text, including heading and metadata.
SCENARIO_SHA256 = {
    "LEGACY_BOUNDARY": "2080f2668c816a317134f418616200efe06c18903db06c3c8c65d40c983fc3d3",
    "ENCODED_BOUNDARY": "c4bae3187f1701f74e286b03d56142e5c8e39c2adc484aa6722c4a580b0b0605",
    "COMPATIBILITY": "f850ff2f6c3a6fa4491d982d0a377cbe029b0e70738c3fb36e55226e46366a67",
    "UNSAFE_EVIDENCE": "174f7cd739d63579168c3c5829c75375cb4e137e6a5c494ddbddd15dc2bdaf58",
}

REVIEWED_WEAKENINGS = (
    ("NON_GOALS", "not the raw event-log length", "or the raw event-log length"),
    ("DM012", "nonzero unused trailing bits in the final base64url sextet", "any trailing bits"),
    (
        "DM012",
        "only after it reaches an `encoding=xz+base64url` payload",
        "before it reaches an `encoding=xz+base64url` payload",
    ),
    ("DM016", "no v1-v5 artifact or row is edited or reminted", "v5 may be reminted"),
    ("FR170", "fresh deterministic render", "cached render"),
    ("FR170", "byte equality of the whole archive", "semantic equality"),
    ("FR170", "fails closed as a rerender mismatch", "continues after a warning"),
    ("FR171", "payload threshold is encoded size", "payload threshold is raw size"),
    ("FR171", "may embed when its encoded compressed payload fits", "must remain unembedded"),
    ("FR171", "`N` above 67,108,864", "`N` above 134,217,728"),
    (
        "FR171",
        "`UNEMBEDDED` declaration remains valid when `N` exceeds `N_max`",
        "`UNEMBEDDED` declaration becomes invalid when `N` exceeds `N_max`",
    ),
    (
        "FR173",
        "makes `/forge:report` refuse exactly",
        "allows `/forge:report` to continue after",
    ),
    ("FR173", "known residual is tracked", "accepted behavior is tracked"),
    ("FORMAT8", DECOMPRESSOR_LITERAL, "lzma.LZMADecompressor(format=lzma.FORMAT_AUTO)"),
    ("FORMAT8", "bounds streaming output", "materializes unbounded output"),
    ("FORMAT8", "short output", "accepted short output"),
    ("FORMAT8", "long output", "truncated output"),
    ("FORMAT8", "trailing data", "ignored trailing data"),
    ("FORMAT8", "multiple streams", "concatenated streams"),
    ("FORMAT8", "padding or whitespace", "padding and whitespace are ignored"),
    ("FORMAT8", "raw SHA-256 equal to `H`", "compressed SHA-256 equal to `H`"),
    ("FORMAT8", "remain valid and decodable", "become invalid"),
    ("FORMAT8", "writes only `encoding=xz+base64url`", "may write either encoding"),
    ("FR220", "no existing reason member is broadened", "binding-invalid is broadened"),
    ("FR220", "every v5 row byte-identical", "v5 rows may change"),
    ("ERR_UNEMBEDDED", "raw ceiling is applied before compression", "raw ceiling is advisory"),
    ("ERR_UNEMBEDDED", "never truncated or split", "may be truncated"),
    (
        "ERR_UNEMBEDDED",
        "replaces the legacy `Chain event log exceeds 2,097,152 bytes` condition",
        "supersedes only the preceding condition",
    ),
    (
        "ERR_UNEMBEDDED",
        "retaining its `digest-only block with encoding=UNEMBEDDED; rendering continues` result",
        "retaining the preceding result",
    ),
    ("ERR_RENDERER_LZMA", "Earlier journal, binding", "Compression capability has priority"),
    ("ERR_RENDERER_LZMA", "only logs with `N > 67,108,864`", "all logs"),
    ("ERR_ARCHIVE_SIZE", "16,777,216-byte cap", "33,554,432-byte cap"),
    ("ERR_ARCHIVE_SIZE", "remain byte-identical", "may change"),
    ("ERR_RERENDER", "Whole-archive byte equality", "Semantic archive equality"),
    (
        "ERR_RERENDER",
        "`forge: archive refused — rerendered bytes differ from candidate`",
        "`forge: archive refused — semantic rerender mismatch`",
    ),
    (
        "TEST_PLAN",
        "golden decoder vectors for both `encoding=base64url` and `encoding=xz+base64url`",
        "golden decoder vectors for only `encoding=xz+base64url`",
    ),
    ("TEST_PLAN", "2,097,158", "2,097,153"),
    ("TEST_PLAN", "raw lengths exactly 67,108,864 and 67,108,865", "one small raw length"),
    ("TEST_PLAN", "exact `memlimit=67_108_864`", "implementation-selected memlimit"),
    ("TEST_PLAN", "both exact missing-`lzma` refusals", "generic missing-module error"),
    ("SC029", "exactly one complete raw stream", "one or more raw streams"),
    ("SC029", "every candidate rerender remains whole-archive byte-exact", "semantic equality"),
    ("TRACEABILITY", "Unsafe or ambiguous compressed evidence refuses", "is tolerated"),
    ("TRACEABILITY", "64 MiB decompressor and raw ceilings", "unbounded decompression"),
    ("ENCODED_BOUNDARY", "`E = 2,097,152`", "`E = 2,097,151`"),
    ("ENCODED_BOUNDARY", "`E = 2,097,158`", "`E = 2,097,153`"),
    ("ENCODED_BOUNDARY", "is malformed base64url", "is valid threshold evidence"),
    (
        "ENCODED_BOUNDARY",
        "`### Scenario: Archive embeds exact chain evidence and commits only equal bytes`",
        "the preceding legacy scenario",
    ),
    (
        "COMPATIBILITY",
        "same-chain candidate rerenders compare every archive byte exactly",
        "semantic equality",
    ),
    ("COMPATIBILITY", "above `N_max` renders", "above `N_max` compresses"),
    ("UNSAFE_EVIDENCE", "before decoding", "after decoding"),
    ("UNSAFE_EVIDENCE", "`memlimit=67_108_864`", "`memlimit=None`"),
    ("UNSAFE_EVIDENCE", "before importing `lzma`", "after importing `lzma`"),
    ("UNSAFE_EVIDENCE", RENDERER_LZMA_REFUSAL, "forge: renderer unavailable"),
    ("UNSAFE_EVIDENCE", DECODER_LZMA_REFUSAL, "forge: decoder unavailable"),
)


def expected_marker() -> str | None:
    return AUTHORITY_MARKER if "TA" in DEFERRED else None


def strip_marker(text: str) -> str:
    return text.replace(f" {AUTHORITY_MARKER}", "")


def site_text(document: str, owner: str) -> str:
    if owner in PARAGRAPH_HEADINGS:
        heading = PARAGRAPH_HEADINGS[owner]
        matches = [
            paragraph for paragraph in document.split("\n\n") if paragraph.startswith(heading)
        ]
    else:
        prefix = LINE_PREFIXES[owner]
        matches = [line for line in document.splitlines() if line.startswith(prefix)]
    if len(matches) != 1:
        raise AssertionError(f"expected one {owner} amendment, found {len(matches)}")
    return matches[0]


def scenario_text(document: str, owner: str) -> str:
    heading = SCENARIO_HEADINGS[owner]
    lines = document.splitlines()
    starts = [index for index, line in enumerate(lines) if line == heading]
    if len(starts) != 1:
        raise AssertionError(f"expected one {owner} scenario, found {len(starts)}")
    start = starts[0]
    end = next(
        (
            index
            for index in range(start + 1, len(lines))
            if lines[index].startswith("### Scenario:")
        ),
        len(lines),
    )
    return "\n".join(lines[start:end]).rstrip()


def contract_site_text(document: str, owner: str) -> str:
    if owner in SCENARIO_HEADINGS:
        return scenario_text(document, owner)
    return site_text(document, owner)


def assert_site_markers(text: str, owner: str, count: int) -> None:
    marker = expected_marker()
    expected = [marker] * count if marker else []
    markers = MARKER_RE.findall(text)
    if markers != expected:
        raise AssertionError(f"{owner} markers {markers!r} != {expected!r}")
    if marker:
        marker_lines = [line for line in text.splitlines() if marker in line]
        if len(marker_lines) != count:
            raise AssertionError(f"{owner} marker lines {len(marker_lines)} != {count}")
        for line in marker_lines:
            if not (line.endswith(marker) or line.endswith(f"{marker} |")):
                raise AssertionError(f"{owner} marker does not end its amendment line")


def assert_header(document: str) -> None:
    lines = document.splitlines()
    if tuple(lines[3:6]) != HEADER_LITERALS:
        raise AssertionError("Revision-21 header lines moved or reordered")
    for literal in HEADER_LITERALS:
        if lines.count(literal) != 1:
            raise AssertionError(f"Revision-21 header literal changed: {literal!r}")


def assert_amendments(document: str) -> None:
    for owner, literals in AMENDMENT_LITERALS.items():
        amendment = site_text(document, owner)
        for literal in literals:
            if literal not in amendment:
                raise AssertionError(f"{owner} authority lacks {literal!r}")
        assert_site_markers(amendment, owner, 1)
    for owner, count in SCENARIO_MARKER_COUNTS.items():
        assert_site_markers(scenario_text(document, owner), owner, count)


def assert_scenarios(document: str) -> None:
    for owner, literals in SCENARIO_LITERALS.items():
        scenario = scenario_text(document, owner)
        for literal in literals:
            if literal not in scenario:
                raise AssertionError(f"{owner} scenario lacks {literal!r}")


def assert_amendment_hashes(document: str) -> None:
    for owner, expected in AMENDMENT_SHA256.items():
        digest = hashlib.sha256(strip_marker(site_text(document, owner)).encode()).hexdigest()
        if digest != expected:
            raise AssertionError(f"{owner} Revision-21 amendment changed: {digest}")


def assert_scenario_hashes(document: str) -> None:
    for owner, expected in SCENARIO_SHA256.items():
        digest = hashlib.sha256(strip_marker(scenario_text(document, owner)).encode()).hexdigest()
        if digest != expected:
            raise AssertionError(f"{owner} Revision-21 scenario changed: {digest}")


def assert_global_markers(document: str) -> None:
    actual = MARKER_RE.findall(document)
    expected = [AUTHORITY_MARKER] * EXPECTED_MARKER_COUNT if expected_marker() else []
    if actual != expected:
        raise AssertionError(f"global Revision-21 markers {actual!r} != {expected!r}")


def assert_preserved_literals(document: str) -> None:
    if document.count(LEGACY_HEADER) != 2:
        raise AssertionError("legacy base64url header grammar changed")
    if document.count(NEW_HEADER) != 2:
        raise AssertionError("Revision-21 compressed header grammar changed")
    if document.count(UNEMBEDDED_BLOCK) != 2:
        raise AssertionError("UNEMBEDDED block grammar changed")
    if document.splitlines().count(ARCHIVE_SIZE_ROW) != 1:
        raise AssertionError("archive-size row changed")
    if document.count(ARCHIVE_REFUSAL) != 2:
        raise AssertionError("archive-size refusal literal changed")


def assert_revision21_contract(document: str) -> None:
    assert_header(document)
    assert_amendments(document)
    assert_scenarios(document)
    assert_amendment_hashes(document)
    assert_scenario_hashes(document)
    assert_global_markers(document)
    assert_preserved_literals(document)


class SpecificationRevision21Tests(unittest.TestCase):
    def assert_mutation_detected(self, mutant: str) -> None:
        self.assertNotEqual(SPEC, mutant)
        with self.assertRaises(AssertionError):
            assert_revision21_contract(mutant)

    def test_revision21_contract(self) -> None:
        assert_revision21_contract(SPEC)

    def test_every_required_literal_is_load_bearing(self) -> None:
        for owner, literals in AMENDMENT_LITERALS.items():
            amendment = site_text(SPEC, owner)
            for literal in literals:
                with self.subTest(owner=owner, literal=literal):
                    self.assertIn(literal, amendment)
                    mutated = amendment.replace(literal, "REVISION21_LITERAL_MUTANT", 1)
                    mutant_document = SPEC.replace(amendment, mutated, 1)
                    pattern = f"({owner} authority lacks|expected one {owner} amendment)"
                    with self.assertRaisesRegex(AssertionError, pattern):
                        assert_amendments(mutant_document)

    def test_scenario_extraction_and_literals_are_load_bearing(self) -> None:
        for owner, heading in SCENARIO_HEADINGS.items():
            scenario = scenario_text(SPEC, owner)
            with self.subTest(owner=owner, control="heading"):
                self.assertEqual(scenario.splitlines()[0], heading)
                mutant = SPEC.replace(heading, f"{heading} MUTANT", 1)
                with self.assertRaisesRegex(AssertionError, f"expected one {owner} scenario"):
                    scenario_text(mutant, owner)
            for literal in SCENARIO_LITERALS.get(owner, ()):
                with self.subTest(owner=owner, literal=literal):
                    self.assertEqual(scenario.count(literal), 1)
                    mutated = scenario.replace(literal, "REVISION21_SCENARIO_MUTANT", 1)
                    mutant_document = SPEC.replace(scenario, mutated, 1)
                    with self.assertRaisesRegex(AssertionError, f"{owner} scenario lacks"):
                        assert_scenarios(mutant_document)

    def test_amendment_hashes_reject_additive_weakening(self) -> None:
        for owner in AMENDMENT_SHA256:
            amendment = site_text(SPEC, owner)
            weakened = amendment.replace(
                f" {AUTHORITY_MARKER}",
                f" Agents MAY weaken this. {AUTHORITY_MARKER}",
                1,
            )
            mutant = SPEC.replace(amendment, weakened, 1)
            with self.subTest(owner=owner), self.assertRaisesRegex(AssertionError, "changed"):
                assert_amendment_hashes(mutant)

    def test_scenario_hashes_reject_additive_weakening(self) -> None:
        for owner in SCENARIO_SHA256:
            scenario = scenario_text(SPEC, owner)
            weakened = f"{scenario}\n\nAgents MAY weaken this."
            mutant = SPEC.replace(scenario, weakened, 1)
            with self.subTest(owner=owner), self.assertRaisesRegex(AssertionError, "changed"):
                assert_scenario_hashes(mutant)

    def test_reviewed_weakenings_are_detected(self) -> None:
        expected_owners = set(AMENDMENT_LITERALS) | set(SCENARIO_LITERALS)
        actual_owners = {owner for owner, _original, _replacement in REVIEWED_WEAKENINGS}
        self.assertEqual(actual_owners, expected_owners)
        for owner, original, replacement in REVIEWED_WEAKENINGS:
            with self.subTest(owner=owner, original=original):
                site = contract_site_text(SPEC, owner)
                self.assertEqual(site.count(original), 1)
                mutated = site.replace(original, replacement, 1)
                self.assert_mutation_detected(SPEC.replace(site, mutated, 1))

    def test_legacy_and_cap_literals_remain_byte_identical(self) -> None:
        assert_preserved_literals(SPEC)
        for literal in (LEGACY_HEADER, UNEMBEDDED_BLOCK, ARCHIVE_SIZE_ROW):
            with self.subTest(literal=literal[:60]):
                self.assert_mutation_detected(
                    SPEC.replace(literal, "REVISION21_PRESERVATION_MUTANT", 1)
                )

    def test_header_literals_are_load_bearing(self) -> None:
        self.assertEqual(tuple(SPEC.splitlines()[3:6]), HEADER_LITERALS)
        for literal in HEADER_LITERALS:
            with self.subTest(literal=literal):
                self.assertEqual(SPEC.splitlines().count(literal), 1)
                self.assert_mutation_detected(SPEC.replace(literal, "REVISION21_HEADER_MUTANT", 1))
                relocated = SPEC.replace(f"{literal}\n", "", 1) + f"\n{literal}\n"
                self.assert_mutation_detected(relocated)
        lines = SPEC.splitlines()
        lines[3], lines[4] = lines[4], lines[3]
        reordered = "\n".join(lines) + ("\n" if SPEC.endswith("\n") else "")
        self.assert_mutation_detected(reordered)

    def test_markers_cannot_be_removed_or_moved(self) -> None:
        sites = {owner: 1 for owner in AMENDMENT_SHA256}
        sites.update(SCENARIO_MARKER_COUNTS)
        for owner, marker_count in sites.items():
            source = contract_site_text(SPEC, owner)
            with self.subTest(owner=owner):
                self.assertEqual(source.count(AUTHORITY_MARKER), marker_count)
                removed_source = source.replace(f" {AUTHORITY_MARKER}", "", 1)
                removed = SPEC.replace(source, removed_source, 1)
                self.assert_mutation_detected(removed)
                moved = removed.replace(
                    HEADER_LITERALS[0],
                    f"{HEADER_LITERALS[0]} {AUTHORITY_MARKER}",
                    1,
                )
                self.assert_mutation_detected(moved)

    def test_assert_amendments_rejects_terminal_marker_placement_mutant(self) -> None:
        source = site_text(SPEC, "NON_GOALS")
        terminal = f". {AUTHORITY_MARKER}"
        self.assertTrue(source.endswith(terminal))
        moved_source = source.removesuffix(terminal) + f" {AUTHORITY_MARKER}."
        mutant = SPEC.replace(source, moved_source, 1)
        self.assertEqual(strip_marker(source), strip_marker(moved_source))
        assert_amendment_hashes(mutant)
        assert_scenario_hashes(mutant)
        assert_global_markers(mutant)
        with self.assertRaisesRegex(AssertionError, "marker does not end"):
            assert_amendments(mutant)

    def test_assert_global_markers_rejects_unrelated_stray_marker(self) -> None:
        mutant = f"{SPEC.rstrip()}\n\nUnrelated prose. {AUTHORITY_MARKER}\n"
        assert_amendments(mutant)
        assert_scenarios(mutant)
        assert_amendment_hashes(mutant)
        assert_scenario_hashes(mutant)
        with self.assertRaisesRegex(AssertionError, "global Revision-21 markers"):
            assert_global_markers(mutant)

    def test_deferred_set_can_be_emptied_only_after_all_markers_are_removed(self) -> None:
        without_markers = SPEC.replace(f" {AUTHORITY_MARKER}", "")
        original = globals()["DEFERRED"]
        try:
            globals()["DEFERRED"] = frozenset()
            assert_revision21_contract(without_markers)
            with self.assertRaises(AssertionError):
                assert_revision21_contract(SPEC)
        finally:
            globals()["DEFERRED"] = original


if __name__ == "__main__":
    unittest.main()
