"""Single loader for the Forge CLI under test (cli split phase 0, bead forge-plugin-95e.1).

Every test module that needs the CLI loads it through :func:`load_cli` so that later split
phases retarget the import mechanics in one place. The semantics are exactly those of the
per-module ``load_script`` helpers this replaces: a fresh module object is created from the
file location under the caller-chosen name, registered in ``sys.modules`` under that name
before execution (so intra-module imports and dataclass machinery resolve), and executed
once. Distinct names yield distinct module objects with independent globals, which is what
keeps ``mock.patch.object(CLI, ...)`` on a name still defined in the shim invisible to every
other test module. Names that have moved into ``forge_cli`` are different: the package modules
are process-global (see :func:`package_module`), so a patch on a moved control must target the
canonical package module and must always run inside a restoring context.

Only the interpreter-loaded entry point is loaded here: ``scripts/forge/cli.py`` stays the
shim path the FR-221 guard matcher and the fr223 corpora pin, and nothing under
``scripts/forge/`` gains an executable bit through this helper.
"""

from __future__ import annotations

import importlib
import importlib.util
import pkgutil
import sys
from pathlib import Path
from types import ModuleType
from unittest import mock

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


def package_module(name: str) -> ModuleType:
    """Import ``forge_cli.<name>`` once, exactly as the shim does, and return it.

    The package modules are canonical (one object shared by every loaded CLI
    instance), so a test that patches a moved control patches it here, not on a
    per-module copy of the name.
    """

    scripts_dir = str(SCRIPTS_DIR)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    return importlib.import_module(f"forge_cli.{name}")


def _package_modules(package: str) -> list[ModuleType]:
    """The canonical ``forge_cli.<package>`` module plus, once it is a package, every
    submodule of it (imported so their globals exist), root first."""

    root = package_module(package)
    modules = [root]
    for info in pkgutil.iter_modules(getattr(root, "__path__", [])):
        modules.append(importlib.import_module(f"forge_cli.{package}.{info.name}"))
    return modules


def _chain_core_modules() -> list[ModuleType]:
    return _package_modules("chain_core")


def _engine_modules() -> list[ModuleType]:
    return _package_modules("engine")


def _app_modules() -> list[ModuleType]:
    return _package_modules("app")


class _PackagePatch:
    """``mock.patch.object`` applied to every module of ``forge_cli.<package>`` that
    binds ``name``, so one test patch keeps intercepting a control after it moves out of
    the package root: the root binding receives the patch first (its replacement value
    is what ``with ... as m`` yields, exactly as ``mock.patch.object`` does), and every
    submodule that also binds the name is patched with that same object. A name the root
    does not bind is refused, like ``mock.patch.object`` without ``create=True``. On a
    package that is still a single module it is exactly ``mock.patch.object``."""

    def __init__(self, package: str, name: str, args: tuple, kwargs: dict) -> None:
        self._package = package
        self._name = name
        self._args = args
        self._kwargs = kwargs
        self._active: list = []

    def __enter__(self):
        root, *rest = _package_modules(self._package)
        if self._name not in vars(root):
            raise AttributeError(
                f"forge_cli.{self._package} has no attribute {self._name!r}"
            )
        first = mock.patch.object(root, self._name, *self._args, **self._kwargs)
        value = first.__enter__()
        self._active.append(first)
        try:
            for module in rest:
                if self._name in vars(module):
                    extra = mock.patch.object(module, self._name, value)
                    extra.__enter__()
                    self._active.append(extra)
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return value

    def __exit__(self, *exc_info) -> None:
        while self._active:
            self._active.pop().__exit__(*exc_info)

    def start(self):
        """Activate like ``mock.patch.object(...).start()``; pair with :meth:`stop`."""

        return self.__enter__()

    def stop(self) -> None:
        self.__exit__(None, None, None)


def patch_chain_core(name: str, /, *args, **kwargs) -> _PackagePatch:
    """Patch ``name`` on the canonical ``forge_cli.chain_core`` module and on every
    package submodule that binds it (see :class:`_PackagePatch`); a context manager
    with the ``mock.patch.object(package_module("chain_core"), name, ...)`` signature.
    Use it for every patch of a chain-core control so tests are indifferent to which
    file inside the package a control lives in."""

    return _PackagePatch("chain_core", name, args, kwargs)


def patch_engine(name: str, /, *args, **kwargs) -> _PackagePatch:
    """Patch ``name`` on the canonical ``forge_cli.engine`` module (the package root
    once the engine is a package) and on every ``forge_cli.engine.*`` submodule that
    binds it (see :class:`_PackagePatch`); a context manager with the
    ``mock.patch.object(package_module("engine"), name, ...)`` signature. Use it for
    every module-level patch of an engine control so tests are indifferent to which
    file inside the package a control lives in; patches on ``Engine`` instances are
    not module patches and stay as ``mock.patch.object``."""

    return _PackagePatch("engine", name, args, kwargs)


def patch_app(name: str, /, *args, **kwargs) -> _PackagePatch:
    """Patch ``name`` on the canonical ``forge_cli.app`` module (the package root once
    the application layer is a package) and on every ``forge_cli.app.*`` submodule that
    binds it (see :class:`_PackagePatch`); a context manager with the
    ``mock.patch.object(package_module("app"), name, ...)`` signature. Use it for every
    module-level patch of an app-layer control so tests are indifferent to which file
    inside the package a control lives in; patches on ``MergeEngine`` (the class) or
    its instances are not module patches and stay as ``mock.patch.object``."""

    return _PackagePatch("app", name, args, kwargs)
