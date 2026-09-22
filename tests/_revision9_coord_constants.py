"""Preamble constants and the ``key`` helper of ``tests/test_revision9_coordination.py``.

The one hand-written preparation commit of the test_revision9_coordination split (bead
forge-plugin-6g67; overnight brief 2026-09-23, section 4 item 2 and section 11 item 1: the
plugin's ``rope_move.py`` cannot relocate ``Path(__file__)``-derived constants). Every statement
below is the source module's top-level statement verbatim, in its original order. ``ROOT``
resolves to the same repository root from this path, and the ``sys.path`` line mirrors the
source's own so the support mixin's ``codex_orchestrator`` import resolves without PYTHONPATH.
Not a discovered test module: nothing here starts with ``test``.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "scripts/codex_orch_tools.py"
FIXTURES = ROOT / "tests/fixtures"
PREFIX_WEDGE_FIXTURE = ROOT / "tests/_fixtures/prefix-wedge-d77d997"
UNREPLAYABLE_CHAIN_ID = "c-2026-08-21T223925Z-1490"
UNREPLAYABLE_CHAIN_FIXTURE = (
    ROOT / "tests/_fixtures/unreplayable-chain-1490"
)

sys.path.insert(0, str(ROOT / "scripts"))


JOURNAL_FIXTURE_SHA256 = (
    "dd0695b47a37506a10efa9f7889855ada36e7cf9d09fdfdae284c57b049eed86"
)
OUTPUT_FIXTURE_SHA256 = (
    "41e563086b48340bb03f35734b6469551d9aab26efe14f12d38f88aebda3aa60"
)
PREFIX_WEDGE_FIXTURE_SHA256 = {
    "intent.json": "0f3f28e6bfaba51a172ca4dc6a54d52bcb18dc5578e1929a8a1cb907a8afc42f",
    "journal.jsonl": "c7a2e5fb6c56d1ba4e47e968d061a28a3b6fb4b7079d8571402bd1bd4ef73e58",
    "owner.txt": "e0766d0114f351c944033ff4d0025cceed6b6ba7a33ede13be40239bbfeee284",
    "receipts.jsonl": "bcbb1b44db79cfa604fb520def49c4dd80b50d82af6f78ea69dcae799fc4aae7",
    "registry.json": "d92f7d6301da5f0aa5adbc54ca13dc726ee258f758fb798e3d6879bd721f1e25",
}
UNREPLAYABLE_CHAIN_FIXTURE_SHA256 = {
    f"{UNREPLAYABLE_CHAIN_ID}.events.jsonl": (
        "7563e6cdeca3f2218a288c70520e15136db38e9648cae462ffab0259b8c471f3"
    ),
    f"{UNREPLAYABLE_CHAIN_ID}.json": (
        "db0fae7dd4337fb36e14a50b833a48ba0ed5ff19bc93c6adac21a0e60e87658f"
    ),
}


def key(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()
