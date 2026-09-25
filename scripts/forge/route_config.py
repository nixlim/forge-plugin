#!/usr/bin/env python3
"""Validate and resolve Forge's per-clone developer routing file."""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import NoReturn

from route_config_git import RouteRefusal, git_path, run_git
from route_config_probe import ProbeSpec, UnsafeDirectoryError, probe_routes, secure_directory

ROLES = ("implementer", "review-cheap", "review-final", "plan")
PROVIDERS = frozenset({"codex", "claude"})
EFFORTS = {
    "codex": frozenset({"minimal", "low", "medium", "high", "ultra"}),
    "claude": frozenset({"low", "medium", "high", "max"})}
PLUGIN_DEFAULTS = {
    "implementer": ("codex", "gpt-5.6-sol", "ultra"),
    "review-cheap": ("codex", "gpt-5.6-sol", "high"),
    "review-final": ("claude", "fable", "high"),
    "plan": ("codex", "gpt-5.6-sol", "high")}
PROFILE_SANDBOXES = {
    ("codex", "implementer"): "workspace-write",
    ("codex", "review-cheap"): "read-only", ("codex", "review-final"): "read-only",
    ("codex", "plan"): "read-only", ("claude", "plan"): "read-only",
    ("claude", "implementer"): "instruction-bounded",
    ("claude", "review-cheap"): "instruction-bounded",
    ("claude", "review-final"): "instruction-bounded"}
MAX_ROUTES_BYTES = 16 * 1024
GIT_TIMEOUT_SECONDS = 30
ROUTES_RELATIVE = Path(".forge/local/routes.toml")
PLUGIN_ROOT = Path(__file__).resolve().parents[2]
SEED_PATH = PLUGIN_ROOT / "system/local/routes.toml.seed"
EXCLUDE_LINE = b"/.forge/local/"

BLANK_RE = re.compile(r"^[ \t]*$")
COMMENT_RE = re.compile(r"^[ \t]*#[^\r\n]*$")
SCHEMA_RE = re.compile(r'^[ \t]*schema[ \t]*=[ \t]*"forge-routes/1"[ \t]*(?:#[^\r\n]*)?$')
TABLE_RE = re.compile(
    r"^[ \t]*\[(implementer|review-cheap|review-final|plan)\]"
    r"[ \t]*(?:#[^\r\n]*)?$")
ASSIGNMENT_RE = re.compile(
    r'^[ \t]*(provider|model|effort)[ \t]*=[ \t]*"([^"\\\r\n]*)"'
    r"[ \t]*(?:#[^\r\n]*)?$")
MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}(\[1m\])?$")
_CODEX_SUFFIX = r'"[ \t]*(?:#[^\r\n]*)?$'
CODEX_ROUTE_RE = {
    "model": re.compile(r'^[ \t]*model[ \t]*=[ \t]*"([^"\\\r\n]+)' + _CODEX_SUFFIX),
    "effort": re.compile(
        r'^[ \t]*model_reasoning_effort[ \t]*=[ \t]*"([^"\\\r\n]+)' + _CODEX_SUFFIX)}
CLAUDE_ROUTE_RE = {
    "model": re.compile(r"^[ \t]*model:[ \t]*(\S+)[ \t]*$"),
    "effort": re.compile(r"^[ \t]*effort:[ \t]*(\S+)[ \t]*$")}


class UsageError(RuntimeError):
    pass


class RouteArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise UsageError(message)


@dataclass(frozen=True)
class RouteValues:
    provider: str
    model: str
    effort: str


@dataclass(frozen=True)
class ResolvedRoute:
    role: str
    provider: str
    model: str
    effort: str
    route_source: str
    route_sha256: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class RouteResolution:
    routes: tuple[ResolvedRoute, ...]
    local_present: bool

    def for_role(self, role: str) -> ResolvedRoute:
        for route in self.routes:
            if route.role == role:
                return route
        raise ValueError(f"unknown route role: {role}")


def _routes_refusal(cause: str) -> NoReturn:
    raise RouteRefusal(f"forge: routes file refused — {cause}")


def _git(
    repo: Path, *arguments: str, resolution: bool = False
) -> subprocess.CompletedProcess[bytes]:
    return run_git(
        repo, *arguments, timeout=GIT_TIMEOUT_SECONDS, resolution=resolution
    )


def _git_common_dir(repo: Path) -> Path:
    return git_path(repo, "--git-common-dir", timeout=GIT_TIMEOUT_SECONDS)


def _git_toplevel(repo: Path) -> Path:
    return git_path(repo, "--show-toplevel", timeout=GIT_TIMEOUT_SECONDS)


def common_root(repo: Path) -> Path:
    """Return the checkout root containing Git's common directory."""
    return _git_common_dir(Path(repo)).parent


def routes_path(repo: Path) -> Path:
    return common_root(Path(repo)) / ROUTES_RELATIVE


def profile_sandbox(provider: str, role: str) -> str:
    """Return the committed FR-245 sandbox cell for a provider and role."""
    try:
        return PROFILE_SANDBOXES[(provider, role)]
    except KeyError as exc:
        raise ValueError(f"unknown provider/role profile: {provider}/{role}") from exc


def _git_proof(repo: Path, *arguments: str) -> int:
    return _git(repo, *arguments).returncode


def _is_tracked(repo: Path) -> bool:
    status = _git_proof(repo, "ls-files", "--error-unmatch", "--", ROUTES_RELATIVE.as_posix())
    if status not in {0, 1}:
        _routes_refusal("unreadable")
    return status == 0


def _is_ignored(repo: Path) -> bool:
    status = _git_proof(
        repo, "check-ignore", "--no-index", "-q", "--", ROUTES_RELATIVE.as_posix()
    )
    if status not in {0, 1}:
        _routes_refusal("unreadable")
    return status == 0


def _validate_metadata(metadata: os.stat_result) -> None:
    if not stat.S_ISREG(metadata.st_mode):
        _routes_refusal("nonregular")
    if metadata.st_uid != os.geteuid():
        _routes_refusal("foreign owner")
    if metadata.st_mode & 0o022:
        _routes_refusal("group/other-writable")
    if metadata.st_size > MAX_ROUTES_BYTES:
        _routes_refusal("oversized")


def _open_local(path: Path) -> int | None:
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
    try:
        return os.open(path, flags)
    except FileNotFoundError:
        return None
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            _routes_refusal("symlink")
        try:
            mode = os.lstat(path).st_mode
            if not stat.S_ISREG(mode):
                _routes_refusal("symlink" if stat.S_ISLNK(mode) else "nonregular")
        except OSError:
            pass
        _routes_refusal("unreadable")


def _read_local(repo: Path) -> bytes | None:
    root = common_root(repo)
    top_level = _git_toplevel(repo)
    if top_level != root and os.path.lexists(top_level / ROUTES_RELATIVE):
        _routes_refusal("misplaced")
    descriptor = _open_local(root / ROUTES_RELATIVE)
    if descriptor is None:
        return None
    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode):
        os.close(descriptor)
        _routes_refusal("nonregular")
    try:
        with os.fdopen(descriptor, "rb") as stream:
            _validate_metadata(metadata)
            if _is_tracked(root):
                _routes_refusal("tracked")
            if not _is_ignored(root):
                _routes_refusal("unignored")
            data = stream.read(MAX_ROUTES_BYTES + 1)
            if len(data) > MAX_ROUTES_BYTES:
                _routes_refusal("oversized")
            return data
    except OSError as exc:
        raise RouteRefusal("forge: routes file refused — unreadable") from exc


def _validate_values(role: str, values: dict[str, str]) -> RouteValues:
    for key in ("provider", "model", "effort"):
        if key not in values:
            _routes_refusal(f"missing key {key} in [{role}]")
    provider, model, effort = (values[key] for key in ("provider", "model", "effort"))
    if provider not in PROVIDERS:
        _routes_refusal(f"invalid value for provider in [{role}]")
    if model == "inherit" or MODEL_RE.fullmatch(model) is None:
        _routes_refusal(f"invalid value for model in [{role}]")
    if effort not in EFFORTS[provider]:
        _routes_refusal(f"invalid value for effort in [{role}]")
    return RouteValues(provider, model, effort)


def _decode_routes(data: bytes) -> str:
    for token, label in ((b"\x00", "contains NUL"), (b"\r", "contains CR")):
        if token in data:
            _routes_refusal(label)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        line = data[: exc.start].count(b"\n") + 1
        _routes_refusal(f"malformed line {line}")


@dataclass
class _ParseState:
    tables: dict[str, dict[str, str]] = field(default_factory=dict)
    schema_seen: bool = False
    current: str | None = None


def _classify_active(line: str, line_number: int) -> tuple[str, tuple[str, ...]]:
    patterns = (("schema", SCHEMA_RE), ("table", TABLE_RE), ("assignment", ASSIGNMENT_RE))
    for kind, pattern in patterns:
        match = pattern.fullmatch(line)
        if match is not None:
            return kind, match.groups()
    _routes_refusal(f"malformed line {line_number}")


def _consume_active(state: _ParseState, kind: str, groups: tuple[str, ...]) -> None:
    if kind == "schema":
        if state.schema_seen:
            _routes_refusal("duplicate schema")
        state.schema_seen = True
        return
    if kind == "table":
        role = groups[0]
        if not state.schema_seen:
            _routes_refusal(f"schema must precede table [{role}]")
        if role in state.tables:
            _routes_refusal(f"duplicate table {role}")
        state.tables[role] = {}
        state.current = role
        return
    key, value = groups
    if state.current is None:
        _routes_refusal(f"assignment outside a table: {key}")
    if key in state.tables[state.current]:
        _routes_refusal(f"duplicate key {key} in [{state.current}]")
    state.tables[state.current][key] = value


def _parse_routes(data: bytes) -> dict[str, RouteValues]:
    state = _ParseState()
    for line_number, line in enumerate(_decode_routes(data).split("\n"), 1):
        if BLANK_RE.fullmatch(line) or COMMENT_RE.fullmatch(line):
            continue
        kind, groups = _classify_active(line, line_number)
        _consume_active(state, kind, groups)
    if not state.schema_seen:
        _routes_refusal("missing schema")
    return {role: _validate_values(role, values) for role, values in state.tables.items()}


def _local_routes(repo: Path) -> tuple[dict[str, RouteValues], bool]:
    return ({}, False) if (data := _read_local(repo)) is None else (_parse_routes(data), True)


def _head_oid(repo: Path, head: str) -> str:
    arguments = ("rev-parse", "--verify", "--end-of-options", f"{head}^{{commit}}")
    result = _git(repo, *arguments, resolution=True)
    if result.returncode != 0 or re.fullmatch(rb"[0-9a-fA-F]{40,64}\n?", result.stdout) is None:
        raise RouteRefusal("forge: route resolution refused — invalid head")
    return result.stdout.decode("ascii").strip()


def _git_blob(repo: Path, head: str, path: str) -> bytes | None:
    result = _git(repo, "show", f"{head}:{path}", resolution=True)
    return result.stdout if result.returncode == 0 else None


def _blob_lines(data: bytes, path: str) -> list[str]:
    try:
        return data.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise RouteRefusal(f"forge: committed route refused — malformed {path}") from exc


def _extract_route(
    lines: list[str], patterns: dict[str, re.Pattern[str]], path: str
) -> tuple[str, str]:
    values: dict[str, str] = {}
    for key, pattern in patterns.items():
        matches = [match.group(1) for line in lines if (match := pattern.fullmatch(line))]
        if len(matches) != 1:
            raise RouteRefusal(f"forge: committed route refused — malformed {path}")
        values[key] = matches[0]
    return values["model"], values["effort"]


def _committed_route(repo: Path, head: str, role: str) -> RouteValues | None:
    for path in (f".codex/agents/{role}.toml", f"system/codex/agents/{role}.toml"):
        data = _git_blob(repo, head, path)
        if data is not None:
            model, effort = _extract_route(_blob_lines(data, path), CODEX_ROUTE_RE, path)
            values = {"provider": "codex", "model": model, "effort": effort}
            return _validate_values(role, values)
    if role != "review-final":
        return None
    path = "agents/review-final.md"
    data = _git_blob(repo, head, path)
    if data is None:
        return None
    lines = _blob_lines(data, path)
    if not lines or lines[0] != "---":
        raise RouteRefusal(f"forge: committed route refused — malformed {path}")
    try:
        boundary = lines.index("---", 1)
    except ValueError as exc:
        raise RouteRefusal(f"forge: committed route refused — malformed {path}") from exc
    model, effort = _extract_route(lines[1:boundary], CLAUDE_ROUTE_RE, path)
    values = {"provider": "claude", "model": model, "effort": effort}
    return _validate_values(role, values)


def _resolved(role: str, values: RouteValues, source: str) -> ResolvedRoute:
    preimage = {
        "schema": "forge-route/1",
        "role": role,
        "provider": values.provider,
        "model": values.model,
        "effort": values.effort,
        "route_source": source,
    }
    canonical = json.dumps(
        preimage, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    return ResolvedRoute(role, values.provider, values.model, values.effort, source, digest)


def load(repo: Path, *, head: str) -> RouteResolution:
    """Validate the local file and resolve all four routes at ``head``."""
    repo = Path(repo)
    local, present = _local_routes(repo)
    oid = _head_oid(repo, head)
    resolved: list[ResolvedRoute] = []
    for role in ROLES:
        if role in local:
            resolved.append(_resolved(role, local[role], "local"))
            continue
        committed = _committed_route(repo, oid, role)
        if committed is not None:
            resolved.append(_resolved(role, committed, "committed-default"))
            continue
        resolved.append(_resolved(role, RouteValues(*PLUGIN_DEFAULTS[role]), "plugin-default"))
    return RouteResolution(tuple(resolved), present)


def resolve(repo: Path, role: str, head: str) -> ResolvedRoute:
    """Resolve one role through local, committed, then plugin precedence."""
    if role not in ROLES:
        raise ValueError(f"unknown route role: {role}")
    return load(Path(repo), head=head).for_role(role)


def _write_all(descriptor: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        offset += os.write(descriptor, data[offset:])


def _dedupe_exclude(data: bytes) -> tuple[bytes, bool]:
    pieces = data.split(b"\n")
    indexes = [index for index, piece in enumerate(pieces) if piece == EXCLUDE_LINE]
    if len(indexes) < 2:
        return data, False
    duplicates = set(indexes[1:])
    return b"\n".join(piece for index, piece in enumerate(pieces) if index not in duplicates), True


def _read_exclude(directory: int) -> tuple[bytes, int]:
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
    try:
        descriptor = os.open("exclude", flags, dir_fd=directory)
    except FileNotFoundError:
        return b"", 0o600
    except OSError as exc:
        raise RouteRefusal("forge: route init refused — unsafe info/exclude") from exc
    metadata = os.fstat(descriptor)
    unsafe = not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid()
    if unsafe or metadata.st_mode & 0o022:
        os.close(descriptor)
        raise RouteRefusal("forge: route init refused — unsafe info/exclude")
    with os.fdopen(descriptor, "rb") as stream:
        return stream.read(), stat.S_IMODE(metadata.st_mode)


def _replace_exclude(directory: int, data: bytes, mode: int) -> None:
    name = f".forge-routes-{os.getpid()}-{secrets.token_hex(8)}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        descriptor = os.open(name, flags, mode, dir_fd=directory)
        try:
            os.fchmod(descriptor, mode)
            _write_all(descriptor, data)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(name, "exclude", src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    except OSError:
        try:
            os.unlink(name, dir_fd=directory)
        except FileNotFoundError:
            pass
        raise


def _update_exclude(repo: Path, *, dedupe: bool) -> None:
    try:
        context = secure_directory(_git_common_dir(repo), ("info",), final_mode=None)
        with context as (_path, directory):
            original, mode = _read_exclude(directory)
            updated, changed = _dedupe_exclude(original) if dedupe else (original, False)
            if EXCLUDE_LINE not in updated.split(b"\n"):
                separator = b"" if not updated or updated.endswith(b"\n") else b"\n"
                updated += separator + EXCLUDE_LINE + b"\n"
                changed = True
            if changed:
                _replace_exclude(directory, updated, mode)
    except UnsafeDirectoryError as exc:
        raise RouteRefusal("forge: route init refused — unsafe info/exclude") from exc


def _rollback_route(directory: int, created: os.stat_result) -> None:
    try:
        current = os.stat("routes.toml", dir_fd=directory, follow_symlinks=False)
        if os.path.samestat(current, created):
            os.unlink("routes.toml", dir_fd=directory)
            os.fsync(directory)
    except FileNotFoundError:
        pass


def _create_route(directory: int, seed: bytes) -> os.stat_result | None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        descriptor = os.open("routes.toml", flags, 0o600, dir_fd=directory)
    except FileExistsError:
        return None
    created = os.fstat(descriptor)
    try:
        os.fchmod(descriptor, 0o600)
        _write_all(descriptor, seed)
        os.fsync(descriptor)
    except OSError:
        os.close(descriptor)
        _rollback_route(directory, created)
        raise
    os.close(descriptor)
    return created


def init_routes(repo: Path, *, dedupe: bool = False) -> Path:
    """Create the owner-only seed exactly once and update Git's local exclude."""
    repo = Path(repo)
    root = common_root(repo)
    destination = root / ROUTES_RELATIVE
    try:
        seed = SEED_PATH.read_bytes()
    except OSError as exc:
        raise RouteRefusal("forge: route init refused — seed unavailable") from exc
    try:
        with secure_directory(root, (".forge", "local")) as (_path, directory):
            created = _create_route(directory, seed)
            if created is None:
                _update_exclude(repo, dedupe=dedupe)
                raise RouteRefusal("forge: route init refused — routes file already exists")
            try:
                _update_exclude(repo, dedupe=dedupe)
            except (OSError, RouteRefusal):
                _rollback_route(directory, created)
                raise
    except UnsafeDirectoryError as exc:
        raise RouteRefusal("forge: route init refused — unsafe local directory") from exc
    return destination


def check(repo: Path) -> bool:
    return _local_routes(Path(repo))[1]


def _absolute_repo(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("must be an absolute path")
    return path


def _parser() -> RouteArgumentParser:
    parser = RouteArgumentParser(prog="route_config.py")
    commands = parser.add_subparsers(dest="command", required=True)
    init_parser = commands.add_parser("init")
    init_parser.add_argument("--repo", required=True, type=_absolute_repo)
    init_parser.add_argument("--dedupe", action="store_true")
    for name in ("show", "check", "probe"):
        command = commands.add_parser(name)
        command.add_argument("--repo", required=True, type=_absolute_repo)
        if name == "show":
            command.add_argument("--head")
        if name == "probe":
            command.add_argument("--role", choices=ROLES)
    resolve_parser = commands.add_parser("resolve")
    resolve_parser.add_argument("--repo", required=True, type=_absolute_repo)
    resolve_parser.add_argument("--role", required=True, choices=ROLES)
    resolve_parser.add_argument("--head", required=True)
    return parser


def _probe(repo: Path, role: str | None) -> tuple[list[dict[str, object]], list[str]]:
    resolution = load(repo, head="HEAD")
    selected = resolution.routes if role is None else (resolution.for_role(role),)
    grouped: dict[tuple[str, str, str], list[str]] = {}
    for route in selected:
        grouped.setdefault((route.provider, route.model, route.effort), []).append(route.role)
    specs = [ProbeSpec(*key, tuple(roles)) for key, roles in grouped.items()]
    outcomes = probe_routes(common_root(repo), PLUGIN_ROOT, specs)
    return [outcome.report for outcome in outcomes], [
        outcome.diagnostic for outcome in outcomes if outcome.diagnostic is not None
    ]


def main(argv: list[str] | None = None) -> int:
    """Run the route-config command-line interface."""
    parser = _parser()
    try:
        arguments = parser.parse_args(argv)
        if arguments.command == "init":
            path = init_routes(arguments.repo, dedupe=arguments.dedupe)
            print(f"routes file written: {path}")
        elif arguments.command == "check":
            print("routes file ok" if check(arguments.repo) else "no routes file")
        elif arguments.command == "resolve":
            print(json.dumps(resolve(arguments.repo, arguments.role, arguments.head).as_dict()))
        elif arguments.command == "show":
            head = arguments.head or "HEAD"
            print(json.dumps([route.as_dict() for route in load(arguments.repo, head=head).routes]))
        else:
            reports, diagnostics = _probe(arguments.repo, arguments.role)
            for report in reports:
                print(json.dumps(report, sort_keys=True))
            for diagnostic in diagnostics:
                print(diagnostic, file=sys.stderr)
            return 1 if diagnostics else 0
    except UsageError as exc:
        parser.print_usage(sys.stderr)
        print(f"{parser.prog}: error: {exc}", file=sys.stderr)
        return 2
    except (RouteRefusal, OSError) as exc:
        diagnostic = str(exc)
        if not diagnostic.startswith("forge: "):
            diagnostic = "forge: routes file refused — unreadable"
        print(diagnostic, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
