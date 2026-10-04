"""Run the frozen FR-223 verifier from Git or an installed plugin root.

Git top-level roots retain the historical invocation, while nested roots refuse.
Installed mode binds the frozen evaluator and replaces its committed-spec reader;
it proves cache self-consistency, not authenticity against a local cache writer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from types import FunctionType, ModuleType
from typing import NoReturn

MANIFEST_PATH = Path(".forge/evals/tasks/fr223-phase0-v1.manifest.json")
EVALUATOR_PATH = Path("scripts/forge/fr223_eval.py")
SPEC_PATH = Path("docs/specs/forge-plugin-spec.md")
PINNED_MANIFEST_SHA256 = (
    "7741b877b1ed45047d680a077c5303b2314cd1f3ef0339821bd7105ac9acd5c9"
)
PINNED_MANIFEST_LINE = (
    f"{PINNED_MANIFEST_SHA256}  {MANIFEST_PATH.as_posix()}"
)
READ_LIMIT = 16 * 1024 * 1024
READ_CHUNK = 64 * 1024
EVALUATOR_MODULE = "forge_fr223_installed_evaluator"
VERIFICATION_LEGS = frozenset(
    {
        "evaluator-digest",
        "evaluator-seam",
        "manifest-digest",
        "regular-files",
        "root-mode",
        "spec-manifest-pin",
        "spec-utf8",
    }
)
_REPOSITORY_ENVIRONMENT = (
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_CEILING_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_DIR",
    "GIT_DISCOVERY_ACROSS_FILESYSTEM",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_WORK_TREE",
)


class VerificationError(RuntimeError):
    """The invoking plugin root cannot be verified safely."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fr223_verify.py",
        description="Verify the frozen FR-223 package from a Git or installed root.",
    )
    parser.add_argument("command", choices=("verify",))
    parser.add_argument("--root", required=True, help="invoking plugin root")
    return parser


def _resolve_root(value: str) -> Path:
    try:
        root = Path(value).expanduser().resolve(strict=True)
        metadata = root.stat()
    except (OSError, RuntimeError, ValueError) as exc:
        raise VerificationError(f"invalid plugin root: {exc}") from exc
    if not stat.S_ISDIR(metadata.st_mode):
        raise VerificationError("plugin root must name a directory")
    return root


def _git_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for name in _REPOSITORY_ENVIRONMENT:
        environment.pop(name, None)
    return environment


def _git_entry_exists(root: Path) -> bool:
    try:
        (root / ".git").lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise VerificationError(f"cannot inspect plugin root .git entry: {exc}") from exc
    return True


def _git_top_level(root: Path) -> tuple[Path | None, str]:
    try:
        completed = subprocess.run(
            [
                "git",
                "-c",
                "safe.directory=*",
                "-C",
                str(root),
                "rev-parse",
                "--show-toplevel",
            ],
            check=False,
            capture_output=True,
            timeout=8,
            env=_git_environment(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise VerificationError(f"cannot classify plugin root with git: {exc}") from exc
    diagnostic = completed.stderr.decode("utf-8", errors="replace").strip()[:500]
    if completed.returncode != 0:
        return None, diagnostic or f"git exited {completed.returncode}"
    if not completed.stdout.endswith(b"\n"):
        raise VerificationError("git returned a malformed work-tree top level")
    try:
        top_level = Path(os.fsdecode(completed.stdout[:-1])).resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise VerificationError(f"cannot resolve git work-tree top level: {exc}") from exc
    return top_level, diagnostic


def _root_mode(root: Path) -> str:
    has_git_entry = _git_entry_exists(root)
    top_level, diagnostic = _git_top_level(root)
    if top_level == root:
        return "git"
    if "root-mode" not in VERIFICATION_LEGS:
        return "installed"
    if top_level is not None:
        raise VerificationError(
            f"plugin root is nested in git work tree {top_level}"
        )
    if has_git_entry:
        raise VerificationError(
            f"plugin root has an unusable .git entry: {diagnostic}"
        )
    return "installed"


def _open_regular(path: Path, label: str) -> int:
    try:
        before = path.lstat()
    except OSError as exc:
        raise VerificationError(f"cannot read {label}: {exc}") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise VerificationError(f"{label} is not a regular non-symlink file")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise VerificationError(f"cannot read {label}: {exc}") from exc
    try:
        after = os.fstat(descriptor)
    except OSError as exc:
        os.close(descriptor)
        raise VerificationError(f"cannot read {label}: {exc}") from exc
    if (
        not stat.S_ISREG(after.st_mode)
        or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
        or after.st_size > READ_LIMIT
    ):
        os.close(descriptor)
        raise VerificationError(f"{label} is not a bounded regular input")
    return descriptor


def _read_descriptor(descriptor: int, label: str) -> bytes:
    chunks: list[bytes] = []
    retained = 0
    while retained <= READ_LIMIT:
        chunk = os.read(descriptor, min(READ_CHUNK, READ_LIMIT - retained + 1))
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)
        retained += len(chunk)
    raise VerificationError(f"{label} exceeds the input limit")


def _read_regular_bytes(path: Path, label: str) -> bytes:
    if "regular-files" not in VERIFICATION_LEGS:
        try:
            return path.read_bytes()
        except OSError as exc:
            raise VerificationError(f"cannot read {label}: {exc}") from exc
    descriptor = _open_regular(path, label)
    try:
        return _read_descriptor(descriptor, label)
    except OSError as exc:
        raise VerificationError(f"cannot read {label}: {exc}") from exc
    finally:
        os.close(descriptor)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _require_manifest_digest(source: bytes) -> None:
    if (
        "manifest-digest" in VERIFICATION_LEGS
        and _digest(source) != PINNED_MANIFEST_SHA256
    ):
        raise VerificationError("phase-0 manifest does not match its DM-016 digest")


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _manifest_evaluator_digest(source: bytes) -> str:
    try:
        payload = json.loads(source.decode("utf-8"))
        artifacts = payload["artifacts"]
        matches = [
            entry
            for entry in artifacts
            if isinstance(entry, dict)
            and entry.get("path") == EVALUATOR_PATH.as_posix()
        ]
    except (KeyError, TypeError, UnicodeError, ValueError) as exc:
        raise VerificationError(f"cannot read pinned phase-0 manifest: {exc}") from exc
    if len(matches) != 1 or not _is_sha256(matches[0].get("sha256")):
        raise VerificationError("phase-0 manifest has no unique evaluator digest")
    return str(matches[0]["sha256"])


def _require_evaluator_digest(source: bytes, expected: str) -> None:
    if "evaluator-digest" in VERIFICATION_LEGS and _digest(source) != expected:
        raise VerificationError("FR-223 evaluator does not match its manifest digest")


def _load_evaluator(path: Path, source: bytes) -> ModuleType:
    try:
        source_text = source.decode("utf-8")
        code = compile(source_text, str(path), "exec", dont_inherit=True)
    except (UnicodeError, SyntaxError) as exc:
        raise VerificationError(f"cannot compile FR-223 evaluator: {exc}") from exc
    module = ModuleType(EVALUATOR_MODULE)
    module.__file__ = str(path)
    module.__package__ = ""
    sys.modules[EVALUATOR_MODULE] = module
    try:
        exec(code, module.__dict__)
    except Exception as exc:
        sys.modules.pop(EVALUATOR_MODULE, None)
        raise VerificationError(f"cannot load FR-223 evaluator: {exc}") from exc
    return module


def _decode_spec(source: bytes) -> str:
    try:
        return source.decode(
            "utf-8", errors="strict" if "spec-utf8" in VERIFICATION_LEGS else "ignore"
        )
    except UnicodeError as exc:
        raise VerificationError("installed plugin specification is not UTF-8") from exc


def _installed_spec(root: Path) -> str:
    source = _read_regular_bytes(root / SPEC_PATH, "installed plugin specification")
    text = _decode_spec(source)
    if (
        "spec-manifest-pin" in VERIFICATION_LEGS
        and PINNED_MANIFEST_LINE not in text.splitlines()
    ):
        raise VerificationError(
            "installed plugin specification lacks the DM-016 manifest digest line"
        )
    return text


def _seam_package_issues(module: ModuleType) -> FunctionType:
    try:
        committed_spec = module.__dict__["_committed_spec"]
        package_issues = module.__dict__["_package_issues"]
        verify = module.__dict__["_verify"]
    except KeyError as exc:
        raise VerificationError("FR-223 evaluator has no committed-spec seam") from exc
    if (
        not callable(committed_spec)
        or not isinstance(package_issues, FunctionType)
        or not isinstance(verify, FunctionType)
        or "_committed_spec" not in package_issues.__code__.co_names
        or "_package_issues" not in verify.__code__.co_names
        or verify.__globals__.get("_package_issues") is not package_issues
    ):
        raise VerificationError("FR-223 evaluator has no committed-spec seam")
    return package_issues


def _replace_committed_spec(module: ModuleType) -> None:
    def replacement(root: Path) -> str:
        return _installed_spec(Path(root))

    package_issues = (
        _seam_package_issues(module)
        if "evaluator-seam" in VERIFICATION_LEGS
        else None
    )
    module._committed_spec = replacement
    if package_issues is None:
        return
    try:
        active_reader = package_issues.__globals__["_committed_spec"]
    except KeyError as exc:
        raise VerificationError("FR-223 evaluator has no committed-spec seam") from exc
    if active_reader is not replacement:
        raise VerificationError("FR-223 evaluator committed-spec seam is not active")


def _run_installed(root: Path) -> int:
    manifest = _read_regular_bytes(root / MANIFEST_PATH, "phase-0 manifest")
    _require_manifest_digest(manifest)
    expected = _manifest_evaluator_digest(manifest)
    evaluator_path = root / EVALUATOR_PATH
    evaluator = _read_regular_bytes(evaluator_path, "FR-223 evaluator")
    _require_evaluator_digest(evaluator, expected)
    module = _load_evaluator(evaluator_path, evaluator)
    _replace_committed_spec(module)
    main = getattr(module, "main", None)
    if not callable(main):
        raise VerificationError("FR-223 evaluator has no callable main")
    result = main(["verify", "--root", str(root)])
    if type(result) is not int:
        raise VerificationError("FR-223 evaluator returned a non-integer status")
    return result


def _run_git(root: Path) -> NoReturn:
    argv = [
        sys.executable,
        str(root / EVALUATOR_PATH),
        "verify",
        "--root",
        str(root),
    ]
    os.execv(sys.executable, argv)
    raise VerificationError("cannot execute frozen FR-223 evaluator")


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        root = _resolve_root(arguments.root)
        if _root_mode(root) == "git":
            _run_git(root)
        return _run_installed(root)
    except VerificationError as exc:
        print(f"forge: FR-223 verifier internal failure: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"forge: FR-223 verifier internal failure: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
