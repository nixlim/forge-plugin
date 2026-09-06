"""Committed forge-project.md policy parsing for the Forge CLI.

Moved verbatim from scripts/forge/cli.py in cli split phase 1 (bead forge-plugin-95e.2).
The fence helpers here are the canonical patch seams for the policy-fence tests.
"""

from __future__ import annotations

import bisect
import dataclasses
import hashlib
import re
from typing import Any, Sequence



def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@dataclasses.dataclass
class Policy:
    sha: str
    raw: bytes
    digest: str
    regions: dict[str, str]
    gate1: str
    stack_commands: list[str]
    invariants: list[dict[str, str | int]]
    changelog: dict[str, Any] | None


REGION_ORDER = (
    "project-overview",
    "file-categories",
    "stack-validations",
    "gate1-test-command",
    "changelog-policy",
    "review-prompt-project-focus",
    "project-triggers",
    "completeness-project-items",
    "agent-project-context",
    "mutation-testing",
    "invariants",
    "risk-tiers",
    "drift-config",
    "trigger-paths",
)


class PolicyError(ValueError):
    pass


def _parse_regions(raw: bytes) -> dict[str, str]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PolicyError("committed forge-project.md is not UTF-8") from exc
    begin_re = re.compile(r"^<!-- FORGE:REGION ([a-z0-9-]+) BEGIN -->$")
    end_re = re.compile(r"^<!-- FORGE:REGION ([a-z0-9-]+) END -->$")
    result: dict[str, str] = {}
    active: str | None = None
    body: list[str] = []
    seen_order: list[str] = []
    for line in text.splitlines(keepends=True):
        plain = line.rstrip("\r\n")
        begin = begin_re.fullmatch(plain)
        end = end_re.fullmatch(plain)
        if begin:
            if active is not None:
                raise PolicyError("nested Forge region marker")
            active = begin.group(1)
            if active in result or active in seen_order:
                raise PolicyError(f"duplicate Forge region: {active}")
            seen_order.append(active)
            body = []
            continue
        if end:
            if active != end.group(1):
                raise PolicyError("mismatched Forge region marker")
            result[active] = "".join(body)
            active = None
            body = []
            continue
        if active is not None:
            body.append(line)
    if active is not None:
        raise PolicyError(f"unterminated Forge region: {active}")
    if tuple(seen_order) != REGION_ORDER:
        raise PolicyError("Forge region inventory/order does not match committed schema")
    return result


_FENCE_OPEN_LINE = re.compile(r"([ \t]*)```(?:bash|sh)\r?")


_FENCE_CLOSE_LINE = re.compile(r"([ \t]*)```[ \t]*\r?")


def _fence_lines(lines: list[str]) -> tuple[list[tuple[int, str]], dict[str, list[int]]]:
    """Classify fence lines in one linear pass.

    Returns the opening fences as ``(line index, prefix)`` pairs and, for every
    prefix, the ascending line indexes of the closing fences at exactly that
    indentation.  A closing fence must sit at the opening fence's exact column.
    """
    openings: list[tuple[int, str]] = []
    closings: dict[str, list[int]] = {}
    for index, line in enumerate(lines):
        match = _FENCE_OPEN_LINE.fullmatch(line)
        if match:
            openings.append((index, match.group(1)))
            continue
        match = _FENCE_CLOSE_LINE.fullmatch(line)
        if match:
            closings.setdefault(match.group(1), []).append(index)
    return openings, closings


def _dedent_fenced_cell(cell: str, prefix: str) -> str:
    """Strip the opening fence's exact indentation from every nonblank cell line.

    An indented fence (for example one nested under a Markdown list item, as
    ``/forge:init`` writes it) must yield byte-identical cell text to the same
    fence at column 0.  A nonblank line that does not carry the fence's exact
    prefix is a misaligned or mixed-indentation cell and is malformed policy.
    """
    if not prefix:
        return cell
    lines: list[str] = []
    for line in cell.split("\n"):
        if not line.strip():
            # A blank line inside the cell carries no prefix to strip; keep
            # only its line ending so CRLF cells stay internally consistent.
            lines.append("\r" if line.endswith("\r") else "")
            continue
        if not line.startswith(prefix):
            raise PolicyError("forge: executable policy row malformed")
        lines.append(line[len(prefix):])
    return "\n".join(lines)


def _fenced_shell_cells(body: str) -> list[str]:
    """Return every ``bash``/``sh`` fenced cell of ``body`` as flat cell text.

    A line scan with per-prefix closing-fence indexes keeps parsing linear in
    the body size; a hostile policy full of unmatched or indented openings
    cannot stall the reader.  An opening fence that never closes at its own
    column is skipped, and the search resumes after each closed cell.
    """
    lines = body.split("\n")
    openings, closings = _fence_lines(lines)
    cells: list[str] = []
    resume_after = -1
    for index, prefix in openings:
        if index <= resume_after:
            continue
        candidates = closings.get(prefix, [])
        position = bisect.bisect_right(candidates, index)
        if position == len(candidates):
            continue
        close = candidates[position]
        cell = "\n".join(lines[index + 1 : close])
        if cell.endswith("\r"):
            cell = cell[:-1]
        if not cell.strip() or "\x00" in cell:
            # The complete fenced cell is one argv element to ``bash -c``;
            # embedded newlines remain bytes inside that one cell.
            raise PolicyError("forge: executable policy row malformed")
        cells.append(_dedent_fenced_cell(cell, prefix))
        resume_after = close
    return cells


def _split_markdown_row(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in stripped[1:-1]:
        if escaped:
            if char == "|":
                current.append("|")
            else:
                current.extend(("\\", char))
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "|":
            cells.append("".join(current).strip().strip("`"))
            current = []
        else:
            current.append(char)
    if escaped:
        current.append("\\")
    cells.append("".join(current).strip().strip("`"))
    return cells


def _separator(cells: Sequence[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def _parse_invariants(body: str) -> list[dict[str, str | int]]:
    rows = [_split_markdown_row(line) for line in body.splitlines()]
    rows = [row for row in rows if row is not None]
    if not rows:
        return []
    if [cell.lower() for cell in rows[0]] != [
        "invariant",
        "check command",
        "enforcement point",
    ]:
        raise PolicyError("forge: executable policy row malformed")
    if len(rows) < 2 or not _separator(rows[1]):
        raise PolicyError("forge: executable policy row malformed")
    parsed: list[dict[str, str | int]] = []
    for row_number, row in enumerate(rows[2:], 1):
        if len(row) != 3 or any(not value for value in row):
            raise PolicyError("forge: executable policy row malformed")
        if row[2] not in {"commit", "merge", "hook"}:
            raise PolicyError("forge: executable policy row malformed")
        if any(char in row[1] for char in "\r\n\x00"):
            raise PolicyError("forge: executable policy row malformed")
        parsed.append(
            {
                "row_number": row_number,
                "invariant": row[0],
                "command": row[1],
                "enforcement": row[2],
            }
        )
    return parsed


def _parse_changelog(body: str) -> dict[str, Any] | None:
    normalized = body.strip()
    if re.fullmatch(
        r"No changelog gate (?:is configured|applies)(?: for| to)?(?: this)? .*?repository\.",
        normalized,
        re.IGNORECASE | re.DOTALL,
    ):
        return None
    cells = _fenced_shell_cells(body)
    if len(cells) != 1:
        raise PolicyError("configured changelog gate must contain exactly one shell cell")
    outputs: list[str] = []
    output_match = re.search(r"(?im)^output paths?:\s*(.+?)\s*$", body)
    if output_match:
        outputs.extend(
            token.strip().strip("`")
            for token in output_match.group(1).split(",")
            if token.strip()
        )
    for line in body.splitlines():
        row = _split_markdown_row(line)
        if row and len(row) >= 2 and row[0].lower() in {"output", "output path", "output paths"}:
            outputs.extend(token.strip() for token in row[1].split(",") if token.strip())
    outputs = list(dict.fromkeys(outputs))
    if not outputs:
        raise PolicyError("configured changelog gate must declare output paths")
    return {"command": cells[0], "outputs": outputs, "mutating": True}


def parse_policy(sha: str, raw: bytes) -> Policy:
    regions = _parse_regions(raw)
    for required in ("file-categories", "stack-validations", "gate1-test-command"):
        if not regions[required].strip() or "forge-init:" in regions[required]:
            raise PolicyError(f"forge: {required} not configured — run /forge:init")
    gate_cells = _fenced_shell_cells(regions["gate1-test-command"])
    if len(gate_cells) != 1:
        raise PolicyError("gate1-test-command must contain exactly one shell cell")
    stack_cells = _fenced_shell_cells(regions["stack-validations"])
    if not stack_cells:
        raise PolicyError("forge: stack-validations not configured — run /forge:init")
    return Policy(
        sha=sha,
        raw=raw,
        digest=sha256_bytes(raw),
        regions=regions,
        gate1=gate_cells[0],
        stack_commands=stack_cells,
        invariants=_parse_invariants(regions["invariants"]),
        changelog=_parse_changelog(regions["changelog-policy"]),
    )
