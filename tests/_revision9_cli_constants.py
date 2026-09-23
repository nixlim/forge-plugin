from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = ROOT / "scripts" / "forge" / "cli.py"
ENVELOPE_KEYS = {
    "chain_id",
    "evidence_refs",
    "expected",
    "message",
    "next_required_step",
    "observed",
    "ok",
    "reason_code",
    "remediation",
    "schema",
    "state",
}


from tests._cli_loader import (  # cli split phase 0: one shared loader
    load_script,
    package_module,
    patch_chain_core,
    patch_engine,
)

CLI = load_script("forge_revision9_cli_surface_tests", CLI_PATH)
CORE = package_module("chain_core")  # cli split phase 2b: canonical chain-core module
RUNTIME = package_module("runtime")  # cli split phase 2a: canonical patch seam for runtime controls
ENGINE = package_module("engine")  # cli split phase 3: canonical engine patch seam
CANDIDATE = package_module("candidate")
CLI_FIXTURE_SUPPORT = load_script(
    "forge_revision9_cli_fixture_support", ROOT / "tests" / "test_cli_chain.py"
)


def key(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()
