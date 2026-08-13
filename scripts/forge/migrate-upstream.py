#!/usr/bin/env python3
"""Migrate a live upstream Forge installation to the plugin layout.

This helper is deliberately mechanical.  It classifies before writing, builds
every output in a staging directory, and only then replaces target files.
Operator judgment (notably divergent-region selection) remains in /forge:init.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


PLUGIN_MANIFEST_RE = re.compile(rb"^plugin_ref: ", re.MULTILINE)
UPSTREAM_COMMIT_RE = re.compile(rb"^upstream_commit:", re.MULTILINE)
UPSTREAM_REGION_LINE_RE = re.compile(
    rb"^region: [A-Za-z0-9._-]+ \([^\r\n()]+\)\s*$", re.MULTILINE
)
BEGIN_RE = re.compile(rb"<!-- FORGE:REGION ([A-Za-z0-9._-]+) BEGIN -->")

SALVAGE_SOURCES = {
    "file-categories": ".opencode/rules/commit-workflow.md",
    "stack-validations": ".opencode/rules/commit-workflow.md",
    "changelog-policy": ".opencode/rules/commit-workflow.md",
    "review-prompt-project-focus": ".opencode/rules/commit-workflow.md",
    "gate1-test-command": ".opencode/rules/worktree-workflow.md",
    "completeness-project-items": ".opencode/rules/review-constitution.md",
    "project-triggers": ".opencode/rules/review-constitution.md",
    "project-overview": "AGENTS.md",
    "agent-project-context": ".codex/agents/implementer.toml",
}

UPSTREAM_CONFIG_SIGNATURES = (
    b'approval_policy = "on-failure"',
    b'sandbox_mode = "workspace-write"',
    b'[agents."code-reviewer"]',
    b'[agents."review-final"]',
    b'config_file = "./agents/review-final.toml"',
    b'[agents."security-auditor"]',
)
UPSTREAM_HOOK_SIGNATURES = (
    b'aggregate-telemetry.sh .tmp/decisions --csv .tmp/telemetry-latest.csv',
    b'.tmp/decisions',
    b'.tmp/telemetry-latest.csv',
)


class MigrationError(RuntimeError):
    """A fail-closed migration error safe to show to an operator."""


@dataclass(frozen=True)
class Region:
    source: str
    name: str
    body: bytes


def classify_manifest(data: bytes) -> str:
    """Return exactly plugin, upstream, or malformed (plugin wins)."""
    if PLUGIN_MANIFEST_RE.search(data):
        return "plugin"
    if UPSTREAM_COMMIT_RE.search(data) or UPSTREAM_REGION_LINE_RE.search(data):
        return "upstream"
    return "malformed"


def parse_regions(data: bytes, source: str) -> list[Region]:
    markers: list[tuple[str, str, int, int]] = []
    marker_like = len(re.findall(rb"<!-- FORGE:REGION\b", data))
    marker_re = re.compile(
        rb"<!-- FORGE:REGION ([A-Za-z0-9._-]+) (BEGIN|END) -->"
    )
    for match in marker_re.finditer(data):
        markers.append(
            (
                match.group(1).decode("ascii"),
                match.group(2).decode("ascii"),
                match.start(),
                match.end(),
            )
        )
    if marker_like != len(markers):
        raise MigrationError(f"{source} has a malformed Forge region marker")

    found: list[Region] = []
    opened: tuple[str, int] | None = None
    seen: set[str] = set()
    for name, kind, start, end in markers:
        if kind == "BEGIN":
            if opened is not None:
                raise MigrationError(f"{source} has misnested Forge region markers")
            if name in seen:
                raise MigrationError(f"{source} has duplicate Forge region {name}")
            opened = (name, end)
            continue
        if opened is None:
            raise MigrationError(f"{source} has an unmatched Forge region END marker")
        if opened[0] != name:
            raise MigrationError(
                f"{source} has mismatched Forge region names: {opened[0]} and {name}"
            )
        found.append(Region(source, name, data[opened[1] : start]))
        seen.add(name)
        opened = None
    if opened is not None:
        raise MigrationError(f"{source} has an unmatched Forge region BEGIN marker")
    return found


def live_files(root: Path) -> list[Path]:
    excluded_roots = {".git", ".worktrees"}
    result: list[Path] = []
    for current, directories, files in os.walk(root):
        rel_dir = Path(current).relative_to(root)
        directories[:] = sorted(
            name
            for name in directories
            if not (rel_dir == Path(".") and name in excluded_roots)
        )
        for name in sorted(files):
            path = Path(current, name)
            if path.is_file() and not path.is_symlink():
                result.append(path)
    return result


def discover_regions(root: Path) -> list[Region]:
    regions: list[Region] = []
    for path in live_files(root):
        data = path.read_bytes()
        if b"<!-- FORGE:REGION" not in data:
            continue
        source = path.relative_to(root).as_posix()
        regions.extend(parse_regions(data, source))
    return regions


def chosen_regions(regions: list[Region], selections: dict[str, str]) -> dict[str, bytes]:
    by_name: dict[str, list[Region]] = {}
    for region in regions:
        by_name.setdefault(region.name, []).append(region)

    selected: dict[str, bytes] = {}
    for name, required_source in SALVAGE_SOURCES.items():
        copies = by_name.get(name, [])
        if not copies:
            continue
        unique = {copy.body for copy in copies}
        explicit = selections.get(name)
        if len(unique) > 1 and explicit is None:
            detail = ", ".join(
                f"{copy.source} sha256={hashlib.sha256(copy.body).hexdigest()}"
                for copy in copies
            )
            raise MigrationError(
                f"divergent region {name}; operator must select a source: {detail}"
            )
        source = explicit or required_source
        matches = [copy for copy in copies if copy.source == source]
        if not matches:
            raise MigrationError(
                f"selected source for region {name} was not found: {source}"
            )
        if explicit is None and not any(copy.source == required_source for copy in copies):
            raise MigrationError(
                f"region {name} is missing from required upstream source {required_source}"
            )
        if b"forge-init:" not in matches[0].body:
            selected[name] = matches[0].body
    return selected


def selected_sources(regions: list[Region], selections: dict[str, str]) -> dict[str, str]:
    present = {region.name for region in regions}
    return {
        name: selections.get(name, required_source)
        for name, required_source in SALVAGE_SOURCES.items()
        if name in present
    }


def plan_bytes(regions: list[Region]) -> bytes:
    by_name: dict[str, list[Region]] = {}
    for region in regions:
        by_name.setdefault(region.name, []).append(region)
    lines = ["Forge upstream migration plan", ""]
    for name in sorted(by_name):
        destination = "plugin destination" if name in SALVAGE_SOURCES else "orphan"
        lines.append(f"{name}: {destination}")
        for region in by_name[name]:
            state = "unfilled" if b"forge-init:" in region.body else "filled"
            lines.append(
                f"  {region.source} sha256={hashlib.sha256(region.body).hexdigest()} {state}"
            )
    return "\n".join(lines).encode("utf-8") + b"\n"


def splice_selected(template: bytes, selections: dict[str, bytes]) -> bytes:
    output = template
    for name, body in selections.items():
        escaped = re.escape(name.encode("ascii"))
        pattern = re.compile(
            rb"(<!-- FORGE:REGION "
            + escaped
            + rb" BEGIN -->).*?(<!-- FORGE:REGION "
            + escaped
            + rb" END -->)",
            re.DOTALL,
        )
        output, count = pattern.subn(lambda match: match.group(1) + body + match.group(2), output)
        if count != 1:
            raise MigrationError(f"plugin template is missing destination region {name}")
    return output


def safe_relative(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise MigrationError(f"unsafe eval task path: {name}")
    return path


def git_object(root: Path, spec: str) -> bytes | None:
    result = subprocess.run(
        ["git", "show", spec], cwd=root, check=False, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    )
    return result.stdout if result.returncode == 0 else None


def committed_eval_paths(root: Path, legacy_root: str) -> list[str]:
    prefix = f"{legacy_root}/evals/tasks"
    result = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", "HEAD", "--", prefix],
        cwd=root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if result.returncode != 0:
        raise MigrationError("unable to enumerate committed upstream eval artifacts")
    paths: list[str] = []
    for full in result.stdout.splitlines():
        if not full.startswith(prefix + "/"):
            continue
        relative = full[len(prefix) + 1 :]
        safe_relative(relative)
        paths.append(relative)
    return sorted(paths)


def prepare_eval_imports(root: Path, stage_tasks: Path) -> tuple[list[str], list[str]]:
    legacy_root = ".opencode"
    imported: list[str] = []
    imported_fixtures: list[str] = []
    relative_paths = committed_eval_paths(root, legacy_root)
    source = root / legacy_root / "evals/tasks"
    if not relative_paths and not source.exists():
        return imported, imported_fixtures

    committed_set = set(relative_paths)
    live_files = {
        path.relative_to(source).as_posix()
        for path in source.rglob("*")
        if path.is_file() and not path.is_symlink()
    } if source.is_dir() else set()
    unexpected = sorted(live_files - committed_set)
    if unexpected:
        raise MigrationError(f"upstream eval artifact is not committed: {unexpected[0]}")

    for relative in relative_paths:
        path = source / relative
        committed = git_object(root, f"HEAD:{legacy_root}/evals/tasks/{relative}")
        if committed is None:
            raise MigrationError(f"upstream eval artifact is not committed: {relative}")
        if not path.is_file() or path.is_symlink():
            raise MigrationError(f"committed upstream eval artifact is missing on disk: {relative}")
        live = path.read_bytes()
        if live != committed:
            raise MigrationError(f"upstream eval artifact differs from committed bytes: {relative}")
        destination = stage_tasks / relative
        if destination.exists() and destination.read_bytes() != committed:
            raise MigrationError(f"eval import collision has different bytes: {relative}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(committed)
        imported.append(relative)
        if path.suffix == ".md":
            imported_fixtures.append(relative)

    # A missing committed baseline remains pending.  It must never be minted
    # during migration; the required strict eval run will block Phase 5.
    return imported, imported_fixtures


def is_upstream_codex(data: bytes, relative: str) -> bool:
    normalized = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    signatures = (
        UPSTREAM_CONFIG_SIGNATURES if relative == "config.toml" else UPSTREAM_HOOK_SIGNATURES
    )
    if relative == "config.toml":
        lines = normalized.split(b"\n")
        return all(signature in lines for signature in signatures)
    return all(signature in normalized for signature in signatures)


def prepare_codex_backups(root: Path, stage: Path) -> list[str]:
    backed_up: list[str] = []
    for relative in ("config.toml", "hooks.json"):
        source = root / ".codex" / relative
        if not source.is_file():
            continue
        data = source.read_bytes()
        if not is_upstream_codex(data, relative):
            continue
        backup = root / ".codex" / f"{relative}.pre-migration"
        if os.path.lexists(backup):
            if backup.is_symlink() or not backup.is_file():
                raise MigrationError(
                    f"migration output is not a regular file: .codex/{relative}.pre-migration"
                )
            if backup.read_bytes() != data:
                raise MigrationError(
                    f"pre-migration backup collision: .codex/{relative}.pre-migration"
                )
        staged = stage / ".codex" / f"{relative}.pre-migration"
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_bytes(data)
        backed_up.append(f".codex/{relative}.pre-migration")
    return backed_up


def report_stamp(now: str | None) -> str:
    stamp = now or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{6}Z", stamp):
        raise MigrationError("migration timestamp must be UTC YYYY-MM-DDTHHMMSSZ")
    return stamp


def report_name(stamp: str, ordinal: int) -> str:
    return f"{stamp}.md" if ordinal == 1 else f"{stamp}-{ordinal:02d}.md"


def publish_report_exclusive(root: Path, staged: Path, stamp: str) -> Path:
    directory = root / ".forge/history/migrations"
    directory.mkdir(parents=True, exist_ok=True)
    descriptor, local_name = tempfile.mkstemp(
        prefix=".forge-migration-report-", suffix=".stage", dir=directory
    )
    local_staged = Path(local_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(staged.read_bytes())
            output.flush()
            os.fsync(output.fileno())
        local_staged.chmod(0o644)

        ordinal = 1
        while True:
            destination = directory / report_name(stamp, ordinal)
            try:
                os.link(local_staged, destination)
            except FileExistsError:
                ordinal += 1
                continue
            return destination
    finally:
        local_staged.unlink(missing_ok=True)


def legacy_artifacts(root: Path, deregistered: list[str]) -> list[str]:
    artifacts: set[str] = set(deregistered)
    legacy_root = ".opencode"
    legacy_tree = root / legacy_root
    if legacy_tree.exists():
        if legacy_tree.is_dir():
            artifacts.add(legacy_root + "/")
            artifacts.update(
                path.relative_to(root).as_posix() + ("/" if path.is_dir() else "")
                for path in sorted(legacy_tree.rglob("*"))
            )
        else:
            artifacts.add(legacy_root)
    for exact in ("opencode.jsonc", ".agents", ".tmp", ".tmp/.commit-lock"):
        if (root / exact).exists() or (root / exact).is_symlink():
            artifacts.add(exact + ("/" if (root / exact).is_dir() and exact in {".agents", ".tmp"} else ""))
    commands = root / ".claude/commands"
    if commands.is_dir():
        artifacts.update(
            path.relative_to(root).as_posix()
            for path in sorted(commands.rglob("*"))
            if path.is_file() or path.is_symlink()
        )
    settings = root / ".claude/settings.json"
    if settings.is_file() and re.search(rb'"Stop"\s*:', settings.read_bytes()):
        artifacts.add(".claude/settings.json (Stop hook present)")
    return sorted(artifacts)


def report_bytes(
    *,
    regions: list[Region],
    selected: dict[str, bytes],
    sources: dict[str, str],
    imported: list[str],
    backups: list[str],
    artifacts: list[str],
    plugin_destinations: set[str],
) -> bytes:
    lines = [
        "# Forge upstream migration",
        "",
        "## Salvaged regions",
        "",
    ]
    for name in sorted(selected):
        source = sources[name]
        lines.append(f"- `{name}` from `{source}`")
    lines += ["", "## Imported eval artifacts", ""]
    lines += [f"- `{path}`" for path in imported] or ["- None found on disk."]
    lines += ["", "## Preserved Codex originals", ""]
    lines += [f"- `{path}`" for path in backups] or ["- None matched upstream signatures."]
    lines += ["", "## Legacy artifacts left in place", ""]
    lines += [f"- `{path}`" for path in artifacts] or ["- None found on disk."]
    lines += [
        "",
        "Removal of legacy trees is an operator decision; migration did not delete them.",
        "",
        "## Cross-system lock facts",
        "",
        "- `AGENT_HALT` is shared, so the kill-switch works across both systems.",
        "- The rebase-lock path is shared, so merge serialization survives.",
        "- Commit-lock paths differ: `.tmp/.commit-lock` versus `.forge/tmp/commit-lock`.",
        "- Concurrent legacy `/commit` and `/forge:commit` are unsafe until the legacy surface is removed.",
        "",
        "## Orphan regions",
        "",
    ]
    orphaned = [region for region in regions if region.name not in plugin_destinations]
    if not orphaned:
        lines.append("No orphan regions were discovered.")
        return "\n".join(lines).encode("utf-8") + b"\n"

    output = "\n".join(lines).encode("utf-8") + b"\n"
    for region in orphaned:
        output += (
            f"\n### `{region.name}` from `{region.source}`\n\n"
            "Complete body bytes (verbatim):\n\n"
            "<!-- FORGE:ORPHAN-BODY BEGIN -->"
        ).encode("utf-8")
        output += region.body
        output += b"<!-- FORGE:ORPHAN-BODY END -->\n"
    return output


def copy_existing_tree(source: Path, destination: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, destination, dirs_exist_ok=True)


def atomic_install(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_fd, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.migration-", dir=destination.parent)
    try:
        with os.fdopen(temp_fd, "wb") as output:
            output.write(source.read_bytes())
        os.chmod(temp_name, 0o644)
        os.replace(temp_name, destination)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def preflight_output_parent(root: Path, parent: Path) -> None:
    """Require a repository-contained, traversable, writable parent chain."""
    try:
        relative = parent.relative_to(root)
    except ValueError as error:
        raise MigrationError(f"migration output escapes the repository: {parent}") from error

    nearest = root
    missing = False
    for part in relative.parts:
        current = nearest / part if not missing else current / part
        if missing:
            continue
        if os.path.lexists(current):
            if current.is_symlink() or not current.is_dir():
                shown = current.relative_to(root).as_posix()
                raise MigrationError(f"migration output parent is not a directory: {shown}")
            if not os.access(current, os.X_OK):
                shown = current.relative_to(root).as_posix()
                raise MigrationError(f"migration output parent is not traversable: {shown}")
            nearest = current
        else:
            missing = True

    if not os.access(nearest, os.W_OK | os.X_OK):
        shown = nearest.relative_to(root).as_posix() or "."
        raise MigrationError(f"migration output parent is not writable: {shown}")


def preflight_output_directory(root: Path, directory: Path) -> None:
    preflight_output_parent(root, directory.parent)
    if os.path.lexists(directory) and (
        directory.is_symlink() or not directory.is_dir()
    ):
        shown = directory.relative_to(root).as_posix()
        raise MigrationError(f"migration output parent is not a directory: {shown}")


def preflight_output_destination(root: Path, destination: Path) -> None:
    preflight_output_parent(root, destination.parent)
    if os.path.lexists(destination) and (
        destination.is_symlink() or not destination.is_file()
    ):
        shown = destination.relative_to(root).as_posix()
        raise MigrationError(f"migration output is not a regular file: {shown}")


def migrate(root: Path, plugin_root: Path, selections: dict[str, str], now: str | None) -> Path:
    git_root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if git_root.returncode != 0 or Path(git_root.stdout.strip()).resolve() != root.resolve():
        raise MigrationError(f"target is not the Git repository root: {root}")

    manifest = root / ".forge-manifest"
    if not manifest.is_file():
        raise MigrationError("no .forge-manifest to classify")
    classification = classify_manifest(manifest.read_bytes())
    if classification != "upstream":
        raise MigrationError(f"manifest classification is {classification}, not upstream")

    template = plugin_root / "system/template/forge-project.md"
    if not template.is_file():
        raise MigrationError(f"missing plugin template: {template}")
    template_bytes = template.read_bytes()
    plugin_destinations = {
        match.decode("ascii") for match in BEGIN_RE.findall(template_bytes)
    }
    regions = discover_regions(root)
    selected = chosen_regions(regions, selections)
    sources = selected_sources(regions, selections)

    signed_codex: dict[str, bytes] = {}
    for relative in ("config.toml", "hooks.json"):
        path = root / ".codex" / relative
        if path.is_file() and is_upstream_codex(path.read_bytes(), relative):
            signed_codex[relative] = path.read_bytes()
    shadow = root / ".claude/agents/review-final.md"
    if shadow.is_file():
        print(
            "forge migration: activation remains blocked by "
            ".claude/agents/review-final.md",
            file=sys.stderr,
        )

    with tempfile.TemporaryDirectory(prefix="forge-migration-") as temp:
        stage = Path(temp)
        staged_project = stage / "forge-project.md"
        staged_project.write_bytes(splice_selected(template_bytes, selected))

        staged_tasks = stage / ".forge/evals/tasks"
        copy_existing_tree(root / ".forge/evals/tasks", staged_tasks)
        staged_tasks.mkdir(parents=True, exist_ok=True)
        imported, _imported_fixtures = prepare_eval_imports(root, staged_tasks)
        backups = prepare_codex_backups(root, stage)

        prepared_codex: dict[str, Path] = {}
        for relative, original in signed_codex.items():
            payload = plugin_root / "system/codex" / relative
            if not payload.is_file():
                raise MigrationError(f"missing plugin Codex payload: {payload}")
            rendered = payload.read_bytes().replace(
                b"{{FORGE_PROJECT_NAME}}", root.name.encode("utf-8")
            )
            rendered = rendered.replace(
                b"{{FORGE_INSTALL_DATE}}", dt.date.today().isoformat().encode("ascii")
            )
            prepared = stage / ".codex-active" / relative
            prepared.parent.mkdir(parents=True, exist_ok=True)
            prepared.write_bytes(rendered)
            prepared_codex[relative] = prepared

        prepared_agent_tomls: dict[str, Path] = {}
        for relative in ("implementer.toml", "review-cheap.toml"):
            payload = plugin_root / "system/codex/agents" / relative
            if not payload.is_file():
                raise MigrationError(f"missing plugin Codex payload: {payload}")
            prepared = stage / ".codex-active/agents" / relative
            prepared.parent.mkdir(parents=True, exist_ok=True)
            prepared.write_bytes(payload.read_bytes())
            prepared_agent_tomls[relative] = prepared

        upstream_agents = root / ".codex/agents"
        plugin_agent_names = {
            path.name for path in (plugin_root / "system/codex/agents").glob("*.toml")
        }
        deregistered = sorted(
            path.relative_to(root).as_posix()
            for path in upstream_agents.glob("*.toml")
            if path.is_file() and path.name not in plugin_agent_names
        )
        artifacts = legacy_artifacts(root, deregistered)
        stamp = report_stamp(now)
        staged_report = stage / "migration-report.md"
        staged_report.parent.mkdir(parents=True, exist_ok=True)
        staged_report.write_bytes(
            report_bytes(
                regions=regions,
                selected=selected,
                sources=sources,
                imported=imported,
                backups=backups,
                artifacts=artifacts,
                plugin_destinations=plugin_destinations,
            )
        )

        output_destinations = [root / "forge-project.md"]
        output_destinations.extend(
            root / ".forge/evals/tasks" / path.relative_to(staged_tasks)
            for path in staged_tasks.rglob("*")
            if path.is_file()
        )
        output_destinations.extend(root / relative for relative in backups)
        output_destinations.extend(root / ".codex" / relative for relative in prepared_codex)
        output_destinations.extend(
            root / ".codex/agents" / relative for relative in prepared_agent_tomls
        )
        output_destinations.extend(
            (root / relative)
            for relative in ("AGENTS.md", "CLAUDE.md", ".gitignore")
        )
        codex_source = plugin_root / "system/codex"
        output_destinations.extend(
            root / ".codex" / path.relative_to(codex_source)
            for path in codex_source.rglob("*")
            if path.is_file()
            and ".devlog" not in path.relative_to(codex_source).parts
            and path.name != "CLAUDE.md"
        )
        for relative in ("config.toml", "hooks.json"):
            destination = root / ".codex" / relative
            if (
                destination.is_file()
                and relative not in signed_codex
                and not (
                    relative == "config.toml"
                    and b"# forge-managed" in destination.read_bytes().splitlines()
                )
                and not (
                    relative == "hooks.json"
                    and b": 'forge-managed';" in destination.read_bytes()
                )
            ):
                output_destinations.append(destination.with_name(destination.name + ".forge-new"))
        for destination in output_destinations:
            preflight_output_destination(root, destination)
        for directory in (
            ".forge/evals/tasks",
            ".forge/history/runs",
            ".forge/history/drift",
            ".forge/history/migrations",
            ".forge/tmp",
            ".forge/tmp/drift",
            ".forge/tmp/decisions",
        ):
            preflight_output_directory(root, root / directory)

        # The shadow is an activation blocker, not a reason to discard a
        # prepared false-manifest candidate.  Helper and mandatory installer
        # destination-shape failures have now occurred before the first target mutation.

        atomic_install(staged_project, root / "forge-project.md")
        for path in sorted(item for item in staged_tasks.rglob("*") if item.is_file()):
            atomic_install(path, root / ".forge/evals/tasks" / path.relative_to(staged_tasks))
        for relative in backups:
            atomic_install(stage / relative, root / relative)
        for relative, original in signed_codex.items():
            destination = root / ".codex" / relative
            atomic_install(prepared_codex[relative], destination)
            backup = destination.with_name(destination.name + ".pre-migration")
            if backup.read_bytes() != original:
                raise MigrationError(f"pre-migration backup verification failed: {backup}")
        for relative, prepared in prepared_agent_tomls.items():
            atomic_install(prepared, root / ".codex/agents" / relative)
        destination_report = publish_report_exclusive(root, staged_report, stamp)
    return destination_report


def parse_selections(values: list[str]) -> dict[str, str]:
    selections: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise MigrationError("--select requires REGION=SOURCE")
        name, source = value.split("=", 1)
        if name not in SALVAGE_SOURCES or not source:
            raise MigrationError(f"invalid region selection: {value}")
        selections[name] = PurePosixPath(source).as_posix()
    return selections


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--classify", type=Path)
    parser.add_argument("--target", type=Path)
    parser.add_argument("--plugin-root", type=Path)
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--select", action="append", default=[])
    parser.add_argument("--timestamp", help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        if args.classify is not None:
            print(classify_manifest(args.classify.read_bytes()))
            return 0
        if args.plan:
            if args.target is None:
                parser.error("--target is required with --plan")
            root = args.target.resolve()
            git_root = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=root,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            if git_root.returncode != 0 or Path(git_root.stdout.strip()).resolve() != root:
                raise MigrationError(f"target is not the Git repository root: {root}")
            sys.stdout.buffer.write(plan_bytes(discover_regions(root)))
            return 0
        if args.target is None or args.plugin_root is None:
            parser.error("--target and --plugin-root are required for migration")
        root = args.target.resolve()
        plugin_root = args.plugin_root.resolve()
        report = migrate(root, plugin_root, parse_selections(args.select), args.timestamp)
        print(f"forge migration: report={report.relative_to(root).as_posix()}")
        return 0
    except (MigrationError, OSError) as error:
        print(f"forge migration: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
