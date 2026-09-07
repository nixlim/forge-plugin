#!/usr/bin/env python3
"""Classify an exact Git diff using committed Forge risk policy."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence, TypeVar

from forge_cli import candidate as candidate_module


TIERS = {"fast": 0, "standard": 1, "hard": 2}
REGION_RE = re.compile(
    r"<!-- FORGE:REGION ([a-z0-9-]+) BEGIN -->\n(.*?)"
    r"<!-- FORGE:REGION \1 END -->",
    re.DOTALL,
)
DEPENDENCY_BEGIN = "<!-- FORGE:DEPENDENCY-MANIFEST-PATHS BEGIN -->"
DEPENDENCY_END = "<!-- FORGE:DEPENDENCY-MANIFEST-PATHS END -->"
BUILTIN_CONTROL = (
    "forge-project.md",
    ".forge-manifest",
    ".codex/**",
    ".forge/evals/tasks/**",
    "AGENTS.md",
    "CLAUDE.md",
    ".claude/settings*.json",
    ".github/workflows/**",
)
EVAL_CANDIDATES = ".forge/evals/candidates/**"
FIXED_DEPENDENCIES = (
    "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "requirements*.txt", "pyproject.toml", "poetry.lock", "uv.lock",
    "Cargo.toml", "Cargo.lock", "go.mod", "go.sum", "Gemfile", "Gemfile.lock",
    "pom.xml", "build.gradle*", "composer.json", "composer.lock",
)
FORMATTING_EXCLUSIONS = {
    "python", "yaml", "make", "shell", "bash", "haskell", "nim"
}
GENERIC_CATEGORIES = {"bash", "docs", "config", "control"}
GIT_OBJECT_ID_MAX_BYTES = 80
POLICY_MAX_BYTES = 16 * 1024 * 1024


T = TypeVar("T")


class PolicyError(ValueError):
    pass


@dataclass(frozen=True)
class DiffEntry:
    status: str
    path: str
    old_path: str | None = None


@dataclass(frozen=True)
class Policy:
    sha: str
    tier_rows: tuple[tuple[str, tuple[str, ...]], ...]
    formatting_categories: frozenset[str]
    dependency_patterns: tuple[str, ...]
    category_rows: tuple[tuple[str, tuple[str, ...]], ...]
    trigger_patterns: tuple[str, ...]
    trigger_malformed: bool
    risk_malformed: bool


@dataclass(frozen=True)
class TreeSource:
    context: candidate_module.GitContext
    base_tree_oid: str
    candidate_tree_oid: str


_TREE_SOURCE: TreeSource | None = None
_GIT_CONTEXT: candidate_module.GitContext | None = None


def policy_candidate(action: Callable[[], T]) -> T:
    """Translate shared candidate-plumbing failures into classifier failures."""

    try:
        return action()
    except candidate_module.CandidateError as exc:
        raise PolicyError(str(exc)) from exc


def git_context(repo: Path) -> candidate_module.GitContext:
    """Discover one Git context, then reuse its sanitized environment."""

    global _GIT_CONTEXT
    if _GIT_CONTEXT is None:
        _GIT_CONTEXT = policy_candidate(
            lambda: candidate_module.discover_context(repo)
        )
    return _GIT_CONTEXT


def run_git(
    repo: Path,
    *args: str,
    input_bytes: bytes | None = None,
    stdout_limit: int = POLICY_MAX_BYTES,
) -> bytes:
    """Run bounded, sanitized Git plumbing in the pinned repository context."""

    return policy_candidate(
        lambda: candidate_module.git_output(
            git_context(repo),
            ["--no-pager", "--no-replace-objects", *args],
            stdout_limit=stdout_limit,
            input_bytes=input_bytes,
        )
    )


def single_ascii_line(raw: bytes, label: str) -> str:
    if not raw.endswith(b"\n") or raw.count(b"\n") != 1:
        raise PolicyError(f"Git returned malformed {label}")
    try:
        return raw[:-1].decode("ascii")
    except UnicodeDecodeError as exc:
        raise PolicyError(f"Git returned malformed {label}") from exc


def supplied_candidate_matches(
    observation: candidate_module.CandidateObservation,
    base_commit_oid: str | None,
    supplied: dict[str, str | None],
) -> bool:
    supplied_base = str(supplied["base_commit_oid"]) or None
    return (
        observation.authorization_id == supplied["authorization_id"]
        and observation.object_format == supplied["object_format"]
        and observation.tree_oid == supplied["tree_oid"]
        and base_commit_oid == supplied_base
    )


def staged_tree_source(repo: Path) -> TreeSource:
    """Bind staged classification to one immutable candidate tree pair."""

    global _TREE_SOURCE
    if _TREE_SOURCE is not None:
        return _TREE_SOURCE
    context = git_context(repo)
    supplied = {
        "schema": os.environ.get("FORGE_CANDIDATE_SCHEMA"),
        "authorization_id": os.environ.get("FORGE_CANDIDATE_AUTHORIZATION_ID"),
        "object_format": os.environ.get("FORGE_CANDIDATE_OBJECT_FORMAT"),
        "tree_oid": os.environ.get("FORGE_CANDIDATE_TREE_OID"),
        "base_commit_oid": os.environ.get("FORGE_CANDIDATE_BASE_COMMIT_OID"),
    }
    has_supplied_candidate = any(value is not None for value in supplied.values())
    if has_supplied_candidate:
        if (
            supplied["schema"] != candidate_module.CANDIDATE_SCHEMA
            or not all(
                isinstance(supplied[key], str) and supplied[key]
                for key in ("authorization_id", "object_format", "tree_oid")
            )
            or not isinstance(supplied["base_commit_oid"], str)
        ):
            raise PolicyError("candidate tree environment is incomplete")
    base_commit_oid, base_tree_oid = policy_candidate(
        lambda: candidate_module.base_identity(context)
    )
    observation = policy_candidate(lambda: candidate_module.observe_index(context))
    repeated_base = policy_candidate(lambda: candidate_module.base_identity(context))
    if repeated_base != (base_commit_oid, base_tree_oid):
        raise PolicyError("Git HEAD changed during risk-tier classification")
    if has_supplied_candidate and not supplied_candidate_matches(
        observation, base_commit_oid, supplied
    ):
        raise PolicyError("live index tree differs from supplied candidate")
    _TREE_SOURCE = TreeSource(
        context=context,
        base_tree_oid=base_tree_oid,
        candidate_tree_oid=observation.tree_oid,
    )
    return _TREE_SOURCE


def range_tree_source(repo: Path, range_spec: str) -> TreeSource:
    """Resolve one three-dot commit range to its immutable compared trees."""

    global _TREE_SOURCE
    if _TREE_SOURCE is not None:
        return _TREE_SOURCE
    base, head = range_spec.split("...", 1)
    base = full_commit(repo, base)
    head = full_commit(repo, head)
    merge_base = single_ascii_line(
        run_git(
            repo,
            "merge-base",
            base,
            head,
            stdout_limit=GIT_OBJECT_ID_MAX_BYTES,
        ),
        "merge-base OID",
    )
    merge_base = full_commit(repo, merge_base)
    context = git_context(repo)
    base_tree_oid = policy_candidate(
        lambda: candidate_module.resolve_base_tree(context, merge_base)
    )
    candidate_tree_oid = policy_candidate(
        lambda: candidate_module.resolve_base_tree(context, head)
    )
    _TREE_SOURCE = TreeSource(
        context=context,
        base_tree_oid=base_tree_oid,
        candidate_tree_oid=candidate_tree_oid,
    )
    return _TREE_SOURCE


def diff_tree_source(
    repo: Path, *, staged: bool, range_spec: str | None
) -> TreeSource:
    if staged:
        return staged_tree_source(repo)
    if range_spec is not None:
        return range_tree_source(repo, range_spec)
    raise PolicyError("exactly one diff source is required")


def full_commit(repo: Path, revision: str) -> str:
    if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", revision):
        raise PolicyError("policy SHA must be a full lowercase commit SHA")
    value = single_ascii_line(
        run_git(
            repo,
            "rev-parse",
            "--verify",
            f"{revision}^{{commit}}",
            stdout_limit=GIT_OBJECT_ID_MAX_BYTES,
        ),
        "commit OID",
    )
    if value != revision:
        raise PolicyError("policy SHA did not resolve exactly")
    return value


def committed_policy(repo: Path, sha: str) -> str:
    context = git_context(repo)
    tree_oid = policy_candidate(
        lambda: candidate_module.resolve_base_tree(context, sha)
    )
    raw = policy_candidate(
        lambda: candidate_module.tree_blob(context, tree_oid, "forge-project.md")
    )
    if raw is None:
        raise PolicyError("committed forge-project.md is unavailable")
    if len(raw) > POLICY_MAX_BYTES:
        raise PolicyError("committed forge-project.md exceeded its byte ceiling")
    return raw.decode("utf-8", "strict")


def regions(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for match in REGION_RE.finditer(text):
        name = match.group(1)
        if name in found:
            raise PolicyError(f"duplicate policy region: {name}")
        found[name] = match.group(2)
    return found


def table_rows(body: str, header: tuple[str, ...]) -> tuple[list[list[str]], bool]:
    lines = body.splitlines()
    header_indexes: list[int] = []
    for index, raw in enumerate(lines):
        line = raw.strip()
        if not (line.startswith("|") and line.endswith("|")):
            continue
        cells = [cell.strip() for cell in line[1:-1].split("|")]
        if tuple(cell.lower() for cell in cells) == header:
            header_indexes.append(index)
    if len(header_indexes) != 1:
        return [], True

    result: list[list[str]] = []
    malformed = False
    separator_seen = False
    for raw in lines[header_indexes[0] + 1:]:
        line = raw.strip()
        if line.startswith("<!--"):
            if separator_seen:
                break
            continue
        if not line:
            if separator_seen:
                break
            continue
        if not (line.startswith("|") and line.endswith("|")):
            malformed = True
            break
        cells = [cell.strip() for cell in line[1:-1].split("|")]
        if not separator_seen:
            separator_seen = True
            if len(cells) != len(header) or not all(
                re.fullmatch(r":?-{3,}:?", cell) for cell in cells
            ):
                malformed = True
                break
            continue
        if len(cells) != len(header) or any(not cell for cell in cells):
            malformed = True
        else:
            result.append(cells)
    return result, malformed or not separator_seen


def split_patterns(value: str) -> tuple[str, ...]:
    items = tuple(strip_code(item.strip()) for item in value.split(","))
    if not items or any(not item or invalid_pattern(item) for item in items):
        raise PolicyError("invalid path pattern")
    return items


def strip_code(value: str) -> str:
    if len(value) >= 2 and value.startswith("`") and value.endswith("`"):
        return value[1:-1]
    return value


def invalid_pattern(pattern: str) -> bool:
    return (
        pattern.startswith(("!", ":!", ":^", "/"))
        or pattern.startswith(":(")
        or ".." in Path(pattern).parts
        or "\\" in pattern
        or "\x00" in pattern
    )


def parse_policy(text: str, sha: str) -> Policy:
    policy_regions = regions(text)
    risk = policy_regions.get("risk-tiers")
    categories = policy_regions.get("file-categories")
    if risk is None or categories is None:
        raise PolicyError("required committed policy region missing")

    tier_cells, tier_bad = table_rows(risk, ("tier", "path patterns"))
    tier_rows: list[tuple[str, tuple[str, ...]]] = []
    risk_malformed = tier_bad
    for cells in tier_cells:
        tier = cells[0].lower()
        try:
            patterns = split_patterns(cells[1])
        except PolicyError:
            risk_malformed = True
            continue
        if tier not in TIERS:
            risk_malformed = True
            continue
        tier_rows.append((tier, patterns))

    formatting_cells, formatting_bad = table_rows(
        risk, ("formatting-only category",)
    )
    formatting_categories: set[str] = set()
    for cells in formatting_cells:
        category = strip_code(cells[0].strip()).lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", category):
            formatting_bad = True
        else:
            formatting_categories.add(category)
    risk_malformed = risk_malformed or formatting_bad

    start = risk.find(DEPENDENCY_BEGIN)
    end = risk.find(DEPENDENCY_END)
    dependency_patterns: list[str] = []
    if (
        start < 0 or end < 0 or end <= start
        or risk.count(DEPENDENCY_BEGIN) != 1
        or risk.count(DEPENDENCY_END) != 1
    ):
        risk_malformed = True
    else:
        block = risk[start + len(DEPENDENCY_BEGIN):end]
        expected_block = "\n" + "\n".join(FIXED_DEPENDENCIES) + "\n"
        if block != expected_block:
            risk_malformed = True
        for raw in block.splitlines():
            value = raw.strip()
            if not value:
                continue
            if invalid_pattern(value):
                risk_malformed = True
            else:
                dependency_patterns.append(value)
        if tuple(dependency_patterns) != FIXED_DEPENDENCIES:
            risk_malformed = True
            dependency_patterns = list(FIXED_DEPENDENCIES)

    category_cells, category_bad = table_rows(
        categories, ("category", "file patterns")
    )
    category_rows: list[tuple[str, tuple[str, ...]]] = []
    for cells in category_cells:
        category = strip_code(cells[0]).lower()
        try:
            patterns = split_patterns(cells[1])
        except PolicyError:
            category_bad = True
            continue
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", category):
            category_bad = True
        else:
            category_rows.append((category, patterns))
    if category_bad:
        risk_malformed = True

    trigger = policy_regions.get("trigger-paths")
    trigger_patterns: list[str] = []
    trigger_malformed = False
    if trigger is not None:
        meaningful = [
            line.strip() for line in trigger.splitlines()
            if line.strip() and not line.strip().startswith("<!--")
        ]
        if meaningful != ["No trigger paths configured."]:
            trigger_cells, trigger_bad = table_rows(trigger, ("path pattern",))
            trigger_malformed = trigger_bad
            for cells in trigger_cells:
                pattern = cells[0]
                if invalid_pattern(pattern) or "," in pattern:
                    trigger_malformed = True
                else:
                    trigger_patterns.append(pattern)
            if not trigger_patterns and meaningful:
                trigger_malformed = True

    return Policy(
        sha=sha,
        tier_rows=tuple(tier_rows),
        formatting_categories=frozenset(formatting_categories),
        dependency_patterns=tuple(dependency_patterns),
        category_rows=tuple(category_rows),
        trigger_patterns=tuple(trigger_patterns),
        trigger_malformed=trigger_malformed,
        risk_malformed=risk_malformed,
    )


def matched_paths(
    repo: Path, pattern: str, *, staged: bool, range_spec: str | None
) -> frozenset[str]:
    source = diff_tree_source(repo, staged=staged, range_spec=range_spec)
    return frozenset(
        policy_candidate(
            lambda: candidate_module.paths_matching_pattern(
                source.context,
                source.base_tree_oid,
                source.candidate_tree_oid,
                pattern,
            )
        )
    )


def valid_tree_diff_status(status: str) -> bool:
    """Accept only statuses possible from the pinned no-renames tree diff."""

    return re.fullmatch(r"[ADMT]", status) is not None


def parse_diff_entries(raw: bytes) -> list[DiffEntry]:
    """Parse exact ``--name-status -z`` output without recovery or guessing."""

    if not raw:
        return []
    if not raw.endswith(b"\0"):
        raise PolicyError("malformed Git diff status")
    fields = raw[:-1].split(b"\0")
    if any(not field for field in fields):
        raise PolicyError("malformed Git diff status")

    entries: list[DiffEntry] = []
    seen_paths: set[str] = set()
    index = 0
    while index < len(fields):
        try:
            status = fields[index].decode("ascii")
        except UnicodeDecodeError as exc:
            raise PolicyError("malformed Git diff status") from exc
        index += 1
        if not valid_tree_diff_status(status):
            raise PolicyError("malformed Git diff status")
        if index >= len(fields):
            raise PolicyError("malformed Git diff status")
        try:
            path = fields[index].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PolicyError("malformed Git diff status") from exc
        index += 1
        if path in seen_paths:
            raise PolicyError("malformed Git diff status")
        seen_paths.add(path)
        entries.append(DiffEntry(status, path))
    return sorted(entries, key=lambda entry: entry.path.encode("utf-8"))


def diff_entries(repo: Path, *, staged: bool, range_spec: str | None) -> list[DiffEntry]:
    source = diff_tree_source(repo, staged=staged, range_spec=range_spec)
    raw = policy_candidate(
        lambda: candidate_module.name_status_tree_pair(
            source.context, source.base_tree_oid, source.candidate_tree_oid
        )
    )
    return parse_diff_entries(raw)


def matched_categories(
    policy: Policy, path: str, pattern_matches: dict[str, frozenset[str]]
) -> list[str]:
    return sorted({
        category
        for category, patterns in policy.category_rows
        if any(path in pattern_matches[pattern] for pattern in patterns)
    })


def category_covers_dependency(
    category_patterns: Sequence[str], dependency_patterns: Sequence[str]
) -> bool:
    """Return whether a category names a committed DM-003 pattern entry."""
    return not set(category_patterns).isdisjoint(dependency_patterns)


def text_lines(value: bytes) -> list[tuple[bytes, bool]] | None:
    if b"\x00" in value:
        return None
    normalized = value.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    terminal = normalized.endswith(b"\n")
    pieces = normalized.split(b"\n")
    if terminal:
        pieces.pop()
    return [(piece, terminal and index == len(pieces) - 1) for index, piece in enumerate(pieces)]


def leading_prefix(line: bytes) -> bytes:
    match = re.match(br"[ \t]*", line)
    assert match is not None
    return match.group(0)


def file_modes_match(old_mode: bytes, new_mode: bytes) -> bool:
    """Keep file-mode equality independently disableable for mutation checks."""

    return old_mode == new_mode


def formatting_only(
    repo: Path,
    entry: DiffEntry,
    categories: Sequence[str],
    opt_ins: frozenset[str],
    *,
    staged: bool,
    range_spec: str | None,
) -> tuple[bool, str]:
    if entry.status != "M":
        return False, f"status-{entry.status}"
    if not categories:
        return False, "unclassified"
    if FORMATTING_EXCLUSIONS.intersection(categories):
        return False, "excluded-category"
    if not set(categories).intersection(opt_ins):
        return False, "category-not-opted-in"
    source = diff_tree_source(repo, staged=staged, range_spec=range_spec)
    old = policy_candidate(
        lambda: candidate_module.tree_blob(
            source.context, source.base_tree_oid, entry.path
        )
    )
    new = policy_candidate(
        lambda: candidate_module.tree_blob(
            source.context, source.candidate_tree_oid, entry.path
        )
    )
    if old is None or new is None:
        return False, "missing-blob"
    old_entry = policy_candidate(
        lambda: candidate_module.tree_entry(
            source.context, source.base_tree_oid, entry.path
        )
    )
    new_entry = policy_candidate(
        lambda: candidate_module.tree_entry(
            source.context, source.candidate_tree_oid, entry.path
        )
    )
    old_mode_fields = [old_entry.mode.encode("ascii")] if old_entry else []
    new_mode_fields = [new_entry.mode.encode("ascii")] if new_entry else []
    if (
        not old_mode_fields or not new_mode_fields
        or not re.fullmatch(rb"100[0-7]{3}", old_mode_fields[0])
        or not re.fullmatch(rb"100[0-7]{3}", new_mode_fields[0])
    ):
        return False, "non-regular-file"
    if not file_modes_match(old_mode_fields[0], new_mode_fields[0]):
        return False, "file-mode-changed"
    old_lines = text_lines(old)
    new_lines = text_lines(new)
    if old_lines is None or new_lines is None:
        return False, "binary"
    old_terminal = old.replace(b"\r\n", b"\n").replace(b"\r", b"\n").endswith(b"\n")
    new_terminal = new.replace(b"\r\n", b"\n").replace(b"\r", b"\n").endswith(b"\n")
    if len(old_lines) != len(new_lines) or old_terminal != new_terminal:
        return False, "line-shape"
    for (old_line, _), (new_line, _) in zip(old_lines, new_lines):
        if leading_prefix(old_line) != leading_prefix(new_line):
            return False, "leading-whitespace"
        if old_line.rstrip(b" \t") != new_line.rstrip(b" \t"):
            return False, "semantic-bytes"
    return True, "trailing-whitespace-or-line-endings"


def classify(
    repo: Path,
    policy: Policy,
    entries: Sequence[DiffEntry],
    *,
    staged: bool,
    range_spec: str | None,
    declared_tier: str | None,
) -> dict[str, object]:
    path_evidence: list[dict[str, object]] = []
    detected_stack_categories = {
        category for category, _patterns in policy.category_rows
        if category not in GENERIC_CATEGORIES
    }
    unknown_stack_categories = sorted(
        category
        for category, patterns in policy.category_rows
        if category in detected_stack_categories
        and not category_covers_dependency(patterns, policy.dependency_patterns)
    )
    derived_value = TIERS["standard"] if policy.risk_malformed else TIERS["fast"]
    if unknown_stack_categories:
        derived_value = max(derived_value, TIERS["standard"])
    if policy.trigger_malformed:
        derived_value = TIERS["hard"]

    all_patterns = {
        pattern
        for _tier, patterns in policy.tier_rows
        for pattern in patterns
        if pattern != "@formatting-only"
    }
    all_patterns.update(BUILTIN_CONTROL)
    all_patterns.add(EVAL_CANDIDATES)
    all_patterns.update(policy.trigger_patterns)
    all_patterns.update(policy.dependency_patterns)
    all_patterns.update(
        pattern for _category, patterns in policy.category_rows for pattern in patterns
    )
    pattern_matches = {
        pattern: matched_paths(repo, pattern, staged=staged, range_spec=range_spec)
        for pattern in all_patterns
    }

    for entry in entries:
        path = entry.path
        eval_candidate = path in pattern_matches[EVAL_CANDIDATES]
        categories = matched_categories(policy, path, pattern_matches)
        if eval_candidate:
            categories = [category for category in categories if category != "control"]
        formatted, formatting_reason = formatting_only(
            repo, entry, categories, policy.formatting_categories,
            staged=staged, range_spec=range_spec,
        )
        matches: list[dict[str, str]] = []
        path_value = TIERS["standard"]
        for tier, patterns in policy.tier_rows:
            for pattern in patterns:
                matched = formatted if pattern == "@formatting-only" else path in pattern_matches[pattern]
                if matched:
                    path_value = max(path_value if matches else TIERS["fast"], TIERS[tier])
                    matches.append({"tier": tier, "pattern": pattern})

        control = not eval_candidate and (
            any(path in pattern_matches[pattern] for pattern in BUILTIN_CONTROL)
            or "control" in categories
        )
        trigger_matches = [
            pattern for pattern in policy.trigger_patterns if path in pattern_matches[pattern]
        ]
        dependency_matches = [
            pattern for pattern in policy.dependency_patterns if path in pattern_matches[pattern]
        ]
        unknown_manifest = bool(unknown_stack_categories)
        if control or trigger_matches or policy.trigger_malformed:
            path_value = TIERS["hard"]
        elif dependency_matches:
            path_value = max(path_value, TIERS["standard"])
        derived_value = max(derived_value, path_value)
        path_evidence.append({
            "path": path,
            "status": entry.status,
            "categories": categories,
            "matched_rows": matches,
            "formatting_only": formatted,
            "formatting_decision": formatting_reason,
            "dependency_decision": dependency_matches,
            "unknown_manifest_floor": unknown_manifest,
            "control_floor": control,
            "trigger_matches": trigger_matches,
            "path_tier": next(name for name, value in TIERS.items() if value == path_value),
        })

    if not entries:
        derived_value = max(derived_value, TIERS["standard"])
    derived = next(name for name, value in TIERS.items() if value == derived_value)
    declared_value = TIERS[declared_tier] if declared_tier else None
    effective_value = max(derived_value, declared_value) if declared_value is not None else derived_value
    effective = next(name for name, value in TIERS.items() if value == effective_value)
    return {
        "policy_sha": policy.sha,
        "paths": path_evidence,
        "matched_rows": [
            {"path": item["path"], **match}
            for item in path_evidence
            for match in item["matched_rows"]  # type: ignore[union-attr]
        ],
        "formatting_decisions": [
            {"path": item["path"], "eligible": item["formatting_only"],
             "reason": item["formatting_decision"]}
            for item in path_evidence
        ],
        "dependency_decision": [
            {"path": item["path"], "patterns": item["dependency_decision"],
             "unknown_manifest": item["unknown_manifest_floor"]}
            for item in path_evidence
        ],
        "declared_tier": declared_tier or "unspecified",
        "derived_tier": derived,
        "effective_tier": effective,
        "policy_malformed": policy.risk_malformed,
        "trigger_malformed": policy.trigger_malformed,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--repo", required=True)
    result.add_argument("--policy-sha", required=True)
    source = result.add_mutually_exclusive_group(required=True)
    source.add_argument("--staged", action="store_true")
    source.add_argument("--range", dest="range_spec")
    result.add_argument("--declared-tier", choices=tuple(TIERS))
    result.add_argument("--require-effective", choices=tuple(TIERS))
    return result


def main(argv: Sequence[str] | None = None) -> int:
    global _GIT_CONTEXT, _TREE_SOURCE
    _GIT_CONTEXT = None
    _TREE_SOURCE = None
    args = parser().parse_args(argv)
    try:
        if args.range_spec is not None and not re.fullmatch(
            r"[0-9a-f]{40,64}\.\.\.[0-9a-f]{40,64}", args.range_spec
        ):
            raise PolicyError(
                "--range must be two full lowercase hexadecimal commit IDs "
                "separated by '...'"
            )
        repo = Path(args.repo).resolve()
        sha = full_commit(repo, args.policy_sha)
        policy = parse_policy(committed_policy(repo, sha), sha)
        entries = diff_entries(repo, staged=args.staged, range_spec=args.range_spec)
        evidence = classify(
            repo, policy, entries, staged=args.staged, range_spec=args.range_spec,
            declared_tier=args.declared_tier,
        )
    except (
        OSError,
        UnicodeError,
        PolicyError,
        ValueError,
    ) as exc:
        print(f"forge: risk-tier classification failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(evidence, sort_keys=True, separators=(",", ":")))
    if args.require_effective and evidence["effective_tier"] != args.require_effective:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
