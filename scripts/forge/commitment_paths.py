"""Deterministic lexical extraction for journal path citations."""

from __future__ import annotations

import os
import re
import stat
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit


WEB_URL = re.compile(r"\b(?:https?|ftp)://[^\s<>()]+", re.IGNORECASE)
MARKDOWN_TARGET = re.compile(
    r"\[[^\]]*\]\((?:<([^>]+)>|(\S+?))(?:\s+['\"][^'\"]*['\"])?\)"
)
BACKTICK = re.compile(r"`([^`]+)`")
COMMAND_WORD = re.compile(
    r"^(?:bash|cd|git|make|npm|npx|pnpm|python|python3|ruby|sh|uv|yarn)(?:\s|$)"
)
OBSERVATION_PATH = re.compile(
    r"(?=[^\r\n]*/)(?:/)?[A-Za-z0-9_@%+=:,.-]+"
    r"(?:/[A-Za-z0-9_@%+=:,.-]+)*/?\Z"
)
SLASH_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_.-])(?:\.{0,2}/)?[A-Za-z0-9_@%+=:,.-]+"
    r"(?:/[A-Za-z0-9_@%+=:,.-]+)+(?![A-Za-z0-9_.-])"
)
FILE_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_./-])(?:[A-Za-z0-9_@%+=:,-]+\.)+"
    r"[A-Za-z][A-Za-z0-9]{0,15}(?:#[A-Za-z0-9_.-]+)?"
    r"(?=$|[\s,;:!?)\]}`'\"])",
    re.IGNORECASE,
)
DOTFILE_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_./-])\.[A-Za-z][A-Za-z0-9_.#-]*"
    r"(?=$|[\s,;:!?)\]}`'\"])",
    re.IGNORECASE,
)
BARE_BASIS_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_./-])(?:Makefile|Dockerfile|Containerfile|Procfile|Gemfile|Rakefile|"
    r"Justfile|Vagrantfile|Brewfile|LICENSE|NOTICE|README)(?![A-Za-z0-9_.-])",
    re.IGNORECASE,
)
BASIS_SPACE_FILE = re.compile(
    r"^\s*([^`<>\[\]()]+\s+[^`<>\[\]()]*\.[A-Za-z][A-Za-z0-9]{0,15}"
    r"(?:#[A-Za-z0-9_.-]+)?)(?:\s+\([^)]*\))?\s*$",
    re.IGNORECASE,
)
NUMERIC_FRACTION = re.compile(r"\d+/\d+\Z")
SEVERITY_PAIR = re.compile(
    r"(?:CRITICAL|MAJOR|MINOR|WARNING|INFO)/(?:CRITICAL|MAJOR|MINOR|WARNING|INFO)\Z"
)
LINE_SUFFIX = re.compile(r":\d+(?:[-:]\d+)?\Z")
KNOWN_OBSERVATION_EXTENSIONS = frozenset(
    {
        ".c",
        ".cc",
        ".cpp",
        ".css",
        ".csv",
        ".diff",
        ".go",
        ".html",
        ".ini",
        ".java",
        ".js",
        ".json",
        ".jsonl",
        ".jsx",
        ".log",
        ".md",
        ".mjs",
        ".patch",
        ".py",
        ".rb",
        ".result",
        ".rs",
        ".rules",
        ".sh",
        ".sql",
        ".toml",
        ".ts",
        ".tsx",
        ".txt",
        ".xml",
        ".yaml",
        ".yml",
    }
)

CAPTURED_PACKAGE_NAMES = (
    "state.json",
    "events.jsonl",
    "outcome-map.json",
)
RUN_CAPTURED_PATH = re.compile(
    r"captured/sha256/(?P<digest>[0-9a-f]{64})/"
    r"(?P<name>state\.json|events\.jsonl|outcome-map\.json)\Z"
)

AUDIT_RECORD_CITATION = "record-citation"
AUDIT_CAPTURE_SURROGATE = "capture-surrogate"
AUDIT_STRUCTURED_LANDING = "structured-landing"
AUDIT_OPTIONAL_DERIVED = "optional-derived"
AUDIT_ACTIVATED_REQUIRED = "activated-required"


@dataclass(frozen=True)
class CommitmentPathSurface:
    """One immutable FR-017 path surface and its enforcement projections."""

    label: str
    owner: str
    roots: tuple[str, ...]
    enforcement: tuple[str, ...]
    record_type: str | None = None
    field: str | None = None
    extraction: str = "direct"
    context: str | None = None
    legacy_missing: bool = False
    correctable: bool = False
    dispensable: bool = False
    no_follow: bool = True
    file_type: str = "regular-file"
    direct_child_parent: str | None = None
    audit_policy: str = AUDIT_RECORD_CITATION
    owner_controlled: bool = False
    single_link: bool = False
    derived_path: str | None = None


# Keep this table in the normative FR-017/Revision-9 order.  Every append,
# capture, render, and audit projection is selected from these same frozen rows;
# adding an enforcement-point-local label instead is a coextensiveness defect.
COMMITMENT_PATH_SURFACES = (
    CommitmentPathSurface(
        "execution.prompt",
        "record",
        ("run", "repository"),
        ("append", "audit"),
        "execution",
        "prompt",
        legacy_missing=True,
    ),
    CommitmentPathSurface(
        "execution.events",
        "record",
        ("run", "repository"),
        ("append", "audit"),
        "execution",
        "events",
        legacy_missing=True,
    ),
    CommitmentPathSurface(
        "execution.handoff",
        "record",
        ("run", "repository"),
        ("append", "audit"),
        "execution",
        "handoff",
    ),
    CommitmentPathSurface(
        "execution_result.handoff",
        "record",
        ("run", "repository"),
        ("append", "audit"),
        "execution_result",
        "handoff",
    ),
    CommitmentPathSurface(
        "verification.evidence",
        "record",
        ("run", "repository"),
        ("append", "audit"),
        "verification",
        "evidence",
        "array",
        legacy_missing=True,
    ),
    CommitmentPathSurface(
        "decision.basis",
        "record",
        ("run", "repository"),
        ("append", "audit"),
        "decision",
        "basis",
        "token-array",
        "basis",
        legacy_missing=True,
        correctable=True,
        dispensable=True,
    ),
    CommitmentPathSurface(
        "verification.observation",
        "record",
        ("run", "repository"),
        ("append", "audit"),
        "verification",
        "observation",
        "tokens",
        "observation",
        legacy_missing=True,
        correctable=True,
        dispensable=True,
    ),
    CommitmentPathSurface(
        "ingest.state_file",
        "ingest-input",
        ("repository",),
        ("capture", "audit"),
        audit_policy=AUDIT_CAPTURE_SURROGATE,
    ),
    CommitmentPathSurface(
        "ingest.events_file",
        "ingest-input",
        ("repository",),
        ("capture", "audit"),
        audit_policy=AUDIT_CAPTURE_SURROGATE,
    ),
    CommitmentPathSurface(
        "ingest.outcome_map",
        "ingest-input",
        ("repository",),
        ("capture", "audit"),
        audit_policy=AUDIT_CAPTURE_SURROGATE,
    ),
    CommitmentPathSurface(
        "ingest.captured_package",
        "ingest-capture",
        ("run",),
        ("capture", "audit"),
        direct_child_parent="captured-digest",
        audit_policy=AUDIT_STRUCTURED_LANDING,
        owner_controlled=True,
        single_link=True,
    ),
    CommitmentPathSurface(
        "batch.intent",
        "batch",
        ("run",),
        ("append", "audit"),
        direct_child_parent="run",
        audit_policy=AUDIT_OPTIONAL_DERIVED,
        owner_controlled=True,
        single_link=True,
        derived_path=".journal-batch.intent",
    ),
    CommitmentPathSurface(
        "batch.receipt",
        "batch",
        ("run",),
        ("append", "audit"),
        direct_child_parent="run",
        audit_policy=AUDIT_ACTIVATED_REQUIRED,
        owner_controlled=True,
        single_link=True,
        derived_path=".journal-batch-receipts.jsonl",
    ),
    CommitmentPathSurface(
        "archive.candidate",
        "archive",
        ("repository",),
        ("render", "audit"),
        direct_child_parent="archive-history",
        audit_policy=AUDIT_OPTIONAL_DERIVED,
        owner_controlled=True,
        single_link=True,
        derived_path=".forge/history/runs/{run_id}.md",
    ),
)


@dataclass(frozen=True)
class RecordPathCitation:
    """One expanded record citation produced from the shared surface table."""

    surface: CommitmentPathSurface
    label: str
    value: str
    index: int | None = None
    token: str | None = None


@dataclass(frozen=True)
class RunCapturedPath:
    """One canonical run-relative member of an ingest capture package."""

    relative: str
    digest: str
    name: str


@dataclass(frozen=True)
class CommitmentPathResolution:
    """The ordered root selected for one resolve-then-contain decision."""

    root: Path
    candidate: Path
    resolved: Path
    contained: bool
    anchored: bool


def commitment_surfaces(
    *, enforcement: str | None = None
) -> tuple[CommitmentPathSurface, ...]:
    """Return a deterministic projection of the single committed inventory."""

    if enforcement is None:
        return COMMITMENT_PATH_SURFACES
    return tuple(
        surface
        for surface in COMMITMENT_PATH_SURFACES
        if enforcement in surface.enforcement
    )


def commitment_surface(label: str) -> CommitmentPathSurface:
    """Return one exact inventory row without accepting expanded field labels."""

    for surface in COMMITMENT_PATH_SURFACES:
        if surface.label == label:
            return surface
    raise KeyError(label)


def parse_run_captured_path(
    value: str, *, run_id: str
) -> RunCapturedPath | None:
    """Parse the sole canonical run-relative captured-package spelling.

    ``run_id`` deliberately does not appear in the accepted path.  Requiring it
    at the call site binds derivation to one run while keeping journal citations
    relative to that run's root rather than re-embedding repository layout.
    """

    if (
        not isinstance(value, str)
        or not isinstance(run_id, str)
        or not run_id
        or Path(run_id).name != run_id
        or run_id in {".", ".."}
    ):
        return None
    match = RUN_CAPTURED_PATH.fullmatch(value)
    if match is None:
        return None
    return RunCapturedPath(
        relative=value,
        digest=match.group("digest"),
        name=match.group("name"),
    )


def normalize_token(raw: str) -> str | None:
    token = raw.strip().strip("<>[]{}()'\"")
    if not token:
        return None
    markdown_title = re.match(r"^(\S+)(?:\s+['\"].*['\"])$", token)
    if markdown_title:
        token = markdown_title.group(1)
    token = unquote(token)
    parsed = urlsplit(token)
    if parsed.scheme or parsed.netloc or token.startswith("//"):
        return None
    token = token.rstrip(".,;:!?")
    token = token.split("#", 1)[0].split("?", 1)[0]
    token = LINE_SUFFIX.sub("", token)
    if not token or NUMERIC_FRACTION.fullmatch(token) or SEVERITY_PAIR.fullmatch(token):
        return None
    return token


def _backtick_is_path(raw: str) -> bool:
    """Reject obvious shell snippets while retaining explicit path citations."""

    value = raw.strip()
    if not value or "\n" in value or COMMAND_WORD.match(value):
        return False
    if any(marker in value for marker in (" && ", " || ", " | ", "; ", " > ", " < ")):
        return False
    if " " in value or "\t" in value:
        return BASIS_SPACE_FILE.fullmatch(value) is not None
    return any(
        pattern.fullmatch(value) is not None
        for pattern in (SLASH_TOKEN, FILE_TOKEN, DOTFILE_TOKEN, BARE_BASIS_TOKEN)
    )


def _observation_is_path(raw: str) -> bool:
    """Accept only delimited, unambiguous observation path citations."""

    token = normalize_token(raw)
    if (
        token is None
        or "/" not in token
        or OBSERVATION_PATH.fullmatch(token) is None
        or "\n" in raw
        or COMMAND_WORD.match(raw.strip())
        or any(
            marker in raw
            for marker in (" && ", " || ", " | ", "; ", " > ", " < ")
        )
    ):
        return False
    if token.endswith("/"):
        return True
    final = token.rsplit("/", 1)[-1]
    suffix = "." + final.rsplit(".", 1)[-1].casefold() if "." in final else ""
    return suffix in KNOWN_OBSERVATION_EXTENSIONS


def path_tokens(text: str, *, context: str) -> list[str]:
    """Return explicit relative path citations in deterministic source order.

    A basis is first-class citation context. Observation citations must be
    delimited by backticks or a Markdown link and have an unambiguous shape.
    """

    if context not in {"basis", "observation"}:
        raise ValueError(f"unknown citation context: {context}")
    found: list[tuple[int, str]] = []
    claimed: list[tuple[int, int]] = [match.span() for match in WEB_URL.finditer(text)]
    if (
        context == "basis"
        and " and " not in text
        and (space_file := BASIS_SPACE_FILE.match(text))
    ):
        found.append((space_file.start(1), space_file.group(1)))
        claimed.append(space_file.span(1))
    for pattern in (MARKDOWN_TARGET, BACKTICK):
        for match in pattern.finditer(text):
            group = 1
            if pattern is MARKDOWN_TARGET and match.group(1) is None:
                group = 2
            raw = match.group(group)
            if context == "observation":
                is_path = _observation_is_path(raw)
            else:
                is_path = pattern is not BACKTICK or _backtick_is_path(raw)
            if is_path:
                found.append((match.start(group), raw))
            claimed.append(match.span())

    if context == "observation":
        patterns = []
    else:
        patterns = [SLASH_TOKEN, FILE_TOKEN, DOTFILE_TOKEN, BARE_BASIS_TOKEN]

    def outside_claimed(start: int) -> bool:
        return not any(first <= start < last for first, last in claimed)

    for pattern in patterns:
        for match in pattern.finditer(text):
            if not outside_claimed(match.start()):
                continue
            raw = match.group(0)
            found.append((match.start(), raw))

    values: list[str] = []
    seen: set[str] = set()
    for _, raw in sorted(found):
        token = normalize_token(raw)
        if token is not None and token not in seen:
            seen.add(token)
            values.append(token)
    return values


def iter_record_citations(
    record: object, *, enforcement: str | None = None
) -> Iterator[RecordPathCitation]:
    """Expand every record-backed inventory row in deterministic field order."""

    if not isinstance(record, dict):
        return
    kind = record.get("type")
    for surface in COMMITMENT_PATH_SURFACES:
        if (
            surface.owner != "record"
            or surface.record_type != kind
            or (
                enforcement is not None
                and enforcement not in surface.enforcement
            )
        ):
            continue
        assert surface.field is not None
        value = record.get(surface.field)
        if surface.extraction == "direct":
            if isinstance(value, str) and value:
                yield RecordPathCitation(surface, surface.label, value)
            continue
        if surface.extraction == "array":
            if not isinstance(value, list):
                continue
            for index, member in enumerate(value):
                if isinstance(member, str) and member:
                    yield RecordPathCitation(
                        surface,
                        f"{surface.label}[{index}]",
                        member,
                        index=index,
                    )
            continue
        if surface.extraction == "token-array":
            if not isinstance(value, list):
                continue
            assert surface.context is not None
            for index, member in enumerate(value):
                if not isinstance(member, str):
                    continue
                for token in path_tokens(member, context=surface.context):
                    yield RecordPathCitation(
                        surface,
                        f"{surface.label}[{index}]",
                        token,
                        index=index,
                        token=token,
                    )
            continue
        if surface.extraction == "tokens":
            if not isinstance(value, str):
                continue
            assert surface.context is not None
            for token in path_tokens(value, context=surface.context):
                yield RecordPathCitation(
                    surface,
                    f"{surface.label} token {token}",
                    token,
                    token=token,
                )
            continue
        raise RuntimeError(f"unknown commitment path extraction: {surface.extraction}")


def _path_uses_symlink(root: Path, relative: Path) -> bool:
    """Return whether any existing spelling component is a symlink."""

    candidate = root
    for part in relative.parts:
        if part in {"", "."}:
            continue
        candidate = candidate.parent if part == ".." else candidate / part
        try:
            if candidate.is_symlink():
                return True
        except OSError:
            return False
    return False


def resolve_contained_path(
    value: str, roots: Iterable[Path]
) -> CommitmentPathResolution | None:
    """Select the first anchored root, then apply resolve-then-contain.

    A symlink spelling under an earlier root is an anchor even when its target
    escapes that root.  It therefore cannot fall through to a same-spelled path
    under a later root.  When no spelling is anchored, the first contained root
    is retained so append-time validation may accept a not-yet-created file.
    """

    try:
        relative = Path(value)
        if relative.is_absolute():
            return None
        fallback: CommitmentPathResolution | None = None
        for raw_root in roots:
            root = raw_root.expanduser().resolve(strict=True)
            candidate = root / relative
            resolved = candidate.resolve(strict=False)
            try:
                resolved.relative_to(root)
                contained = True
            except ValueError:
                contained = False
            anchored = (
                candidate.exists()
                or candidate.is_symlink()
                or _path_uses_symlink(root, relative)
            )
            selected = CommitmentPathResolution(
                root,
                candidate,
                resolved,
                contained,
                anchored,
            )
            if anchored:
                return selected
            if contained and fallback is None:
                fallback = selected
        return fallback
    except (OSError, RuntimeError, UnicodeError, ValueError):
        return None


def surface_roots(
    surface: CommitmentPathSurface,
    *,
    repository: Path,
    run_dir: Path | None = None,
) -> tuple[Path, ...]:
    """Expand one table row's ordered root names to concrete paths."""

    selected: list[Path] = []
    for root in surface.roots:
        if root == "run":
            if run_dir is None:
                raise ValueError(f"{surface.label} requires a run directory")
            selected.append(run_dir)
        elif root == "repository":
            selected.append(repository)
        else:
            raise ValueError(f"unknown commitment path root: {root}")
    return tuple(selected)


def resolve_surface_path(
    surface: CommitmentPathSurface,
    value: str,
    *,
    repository: Path,
    run_dir: Path | None = None,
) -> CommitmentPathResolution | None:
    """Resolve one value using only its immutable inventory row."""

    try:
        roots = surface_roots(
            surface,
            repository=repository,
            run_dir=run_dir,
        )
    except (OSError, RuntimeError, UnicodeError, ValueError):
        return None
    return resolve_contained_path(value, roots)


def surface_path_is_contained(
    surface: CommitmentPathSurface,
    value: str,
    *,
    repository: Path,
    run_dir: Path | None = None,
) -> bool:
    """Apply the shared fail-closed containment predicate to one surface."""

    selected = resolve_surface_path(
        surface,
        value,
        repository=repository,
        run_dir=run_dir,
    )
    return selected is not None and selected.contained


def resolution_matches_surface(
    surface: CommitmentPathSurface,
    selected: CommitmentPathResolution | None,
) -> bool:
    """Apply the inventory row's file-type and no-follow policy."""

    if (
        selected is None
        or not selected.contained
        or surface.file_type != "regular-file"
    ):
        return False
    try:
        observed = (
            os.lstat(selected.candidate)
            if surface.no_follow
            else os.stat(selected.candidate)
        )
    except (OSError, RuntimeError, ValueError):
        return False
    if not stat.S_ISREG(observed.st_mode):
        return False
    if surface.owner_controlled:
        try:
            if observed.st_uid != os.getuid():
                return False
        except (AttributeError, OSError):
            return False
    if surface.single_link and observed.st_nlink != 1:
        return False
    return True


def validate_surface_path(
    surface: CommitmentPathSurface,
    value: str,
    *,
    repository: Path,
    run_dir: Path | None = None,
    direct_parent: Path | None = None,
    require_file: bool = False,
) -> CommitmentPathResolution | None:
    """Apply one row's containment, direct-child, and file-type policy.

    Callers retain ownership of their exact refusal diagnostic.  ``None`` is
    the sole fail-closed outcome, so an enforcement point cannot accidentally
    reinterpret a path after one of the shared policy checks fails.
    """

    selected = resolve_surface_path(
        surface,
        value,
        repository=repository,
        run_dir=run_dir,
    )
    if selected is None or not selected.contained:
        return None
    if surface.direct_child_parent is not None:
        if direct_parent is None:
            return None
        try:
            expected_parent = direct_parent.expanduser().resolve(strict=True)
        except (OSError, RuntimeError, UnicodeError, ValueError):
            return None
        if (
            selected.candidate.parent != expected_parent
            or selected.candidate.name in {"", ".", ".."}
        ):
            return None
    if selected.anchored:
        if not resolution_matches_surface(surface, selected):
            return None
    elif require_file:
        return None
    return selected
