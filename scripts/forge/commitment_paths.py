"""Deterministic lexical extraction for journal path citations."""

from __future__ import annotations

import re
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
