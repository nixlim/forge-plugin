"""Single loader for the Forge CLI under test (cli split phase 0, bead forge-plugin-95e.1).

Every test module that needs the CLI loads it through :func:`load_cli` so that later split
phases retarget the import mechanics in one place. The semantics are exactly those of the
per-module ``load_script`` helpers this replaces: a fresh module object is created from the
file location under the caller-chosen name, registered in ``sys.modules`` under that name
before execution (so intra-module imports and dataclass machinery resolve), and executed
once. Distinct names yield distinct module objects with independent globals, which is what
keeps ``mock.patch.object(CLI, ...)`` in one test module invisible to every other.

Only the interpreter-loaded entry point is loaded here: ``scripts/forge/cli.py`` stays the
shim path the FR-221 guard matcher and the fr223 corpora pin, and nothing under
``scripts/forge/`` gains an executable bit through this helper.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts" / "forge"
CLI_PATH = SCRIPTS_DIR / "cli.py"
CLI_PACKAGE_DIR = SCRIPTS_DIR / "forge_cli"


def load_script(name: str, path: Path) -> ModuleType:
    """Load ``path`` as a fresh module registered under ``name``."""

    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_cli(name: str) -> ModuleType:
    """Load the Forge CLI entry point as a fresh, independently patchable module."""

    return load_script(name, CLI_PATH)


def load_cached(name: str, path: Path) -> ModuleType:
    """Return the module already registered under ``name``, else load it once."""

    cached = sys.modules.get(name)
    if cached is not None:
        return cached
    return load_script(name, path)
