import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "scripts/codex_orch_tools.py"

sys.path.insert(0, str(ROOT / "scripts"))

RECORDED_AT = "2026-08-26T12:00:00Z"
