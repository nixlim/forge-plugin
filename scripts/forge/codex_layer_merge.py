"""Prepare Forge-owned Codex files without dropping project-owned content."""

from __future__ import annotations

import copy
import json
import math
import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:  # pragma: no cover - exercised by an in-memory control check
    tomllib = None  # type: ignore[assignment]


HOOK_MARKER = ": 'forge-managed';"
MAX_INPUT_BYTES = 1024 * 1024
CODEX_FILENAMES = ("config.toml", "hooks.json")
CONFIG_ROOT_KEYS = frozenset({"approval_policy", "sandbox_mode", "agents"})
OWNED_TOML_COMMENT_PREFIXES = (
    "# forge-managed",
    "# forge: modified from upstream —",
)


class CodexLayerError(ValueError):
    """A fail-closed Codex-layer preparation error."""


@dataclass(frozen=True)
class JsonNumber:
    """A validated JSON number retained without Python numeric coercion."""

    token: str


@dataclass(frozen=True)
class PreparedFile:
    """Bytes to install and whether they target the ordinary or sibling path."""

    action: str
    content: bytes


def _duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise CodexLayerError("duplicate JSON key")
        value[key] = item
    return value


def _invalid_json_constant(_value: str) -> None:
    raise CodexLayerError("invalid JSON constant")


def _validate_json_unicode(value: object, label: str) -> None:
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise CodexLayerError(f"forge install: malformed {label}") from exc
    elif isinstance(value, list):
        for item in value:
            _validate_json_unicode(item, label)
    elif isinstance(value, dict):
        for key, item in value.items():
            _validate_json_unicode(key, label)
            _validate_json_unicode(item, label)
    elif isinstance(value, float) and not math.isfinite(value):
        raise CodexLayerError(f"forge install: malformed {label}")


def _decode(data: bytes, label: str, *, enforce_limit: bool = True) -> str:
    if enforce_limit and len(data) > MAX_INPUT_BYTES:
        raise CodexLayerError(f"forge install: malformed {label}")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CodexLayerError(f"forge install: malformed {label}") from exc


def _validate_hook_handler(handler: object, label: str) -> None:
    if not isinstance(handler, dict) or type(handler.get("command")) is not str:
        raise CodexLayerError(f"forge install: malformed {label}")


def _validate_hook_groups(groups: object, label: str) -> None:
    if not isinstance(groups, list):
        raise CodexLayerError(f"forge install: malformed {label}")
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
            raise CodexLayerError(f"forge install: malformed {label}")
        for handler in group["hooks"]:
            _validate_hook_handler(handler, label)


def _parse_json(data: bytes, label: str, *, enforce_limit: bool = True) -> Any:
    try:
        value = json.loads(
            _decode(data, label, enforce_limit=enforce_limit),
            object_pairs_hook=_duplicate_keys,
            parse_float=JsonNumber,
            parse_int=JsonNumber,
            parse_constant=_invalid_json_constant,
        )
        _validate_json_unicode(value, label)
    except (ValueError, RecursionError) as exc:
        if isinstance(exc, CodexLayerError) and str(exc).startswith("forge install:"):
            raise
        raise CodexLayerError(f"forge install: malformed {label}") from exc
    return value


def _parse_json_object(
    data: bytes, label: str, *, enforce_limit: bool = True
) -> dict[str, Any]:
    """Parse one strict JSON object, rejecting duplicate keys and extensions."""

    value = _parse_json(data, label, enforce_limit=enforce_limit)
    if not isinstance(value, dict):
        raise CodexLayerError(f"forge install: malformed {label}")
    return value


def _parse_hooks(
    data: bytes, label: str, *, enforce_limit: bool
) -> dict[str, Any]:
    value = _parse_json_object(data, label, enforce_limit=enforce_limit)
    if not isinstance(value.get("hooks"), dict):
        raise CodexLayerError(f"forge install: malformed {label}")
    for groups in value["hooks"].values():
        _validate_hook_groups(groups, label)
    return value


def parse_hooks(data: bytes, label: str = ".codex/hooks.json") -> dict[str, Any]:
    """Parse and validate one bounded Codex hooks input."""

    return _parse_hooks(data, label, enforce_limit=True)


def is_plugin_handler(handler: dict[str, Any]) -> bool:
    """Return whether the exact Forge marker claims this handler."""

    return HOOK_MARKER in handler["command"]


def _foreign_groups(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    retained: list[dict[str, Any]] = []
    for group in groups:
        foreign = [
            copy.deepcopy(handler)
            for handler in group["hooks"]
            if not is_plugin_handler(handler)
        ]
        if foreign or set(group) != {"hooks"}:
            copied = copy.deepcopy(group)
            copied["hooks"] = foreign
            retained.append(copied)
    return retained


def _validate_hook_template(template: dict[str, Any]) -> None:
    for groups in template["hooks"].values():
        for group in groups:
            if not all(
                is_plugin_handler(handler) for handler in group["hooks"]
            ):
                raise CodexLayerError(
                    "forge install: malformed Codex template: hooks.json"
                )


def _render_json(value: object, depth: int = 0) -> str:
    if isinstance(value, JsonNumber):
        return value.token
    if value is None or isinstance(value, (bool, int, float, str)):
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    if isinstance(value, list):
        if not value:
            return "[]"
        indent = " " * (2 * (depth + 1))
        rendered = (indent + _render_json(item, depth + 1) for item in value)
        return "[\n" + ",\n".join(rendered) + "\n" + " " * (2 * depth) + "]"
    if isinstance(value, dict):
        if not value:
            return "{}"
        indent = " " * (2 * (depth + 1))
        rendered = (
            indent
            + json.dumps(key, ensure_ascii=False)
            + ": "
            + _render_json(item, depth + 1)
            for key, item in value.items()
        )
        return "{\n" + ",\n".join(rendered) + "\n" + " " * (2 * depth) + "}"
    raise CodexLayerError("forge install: Codex hooks merge verification failed")


def _render_json_document(value: dict[str, Any]) -> bytes:
    return (_render_json(value) + "\n").encode("utf-8")


def _has_plugin_handlers(value: dict[str, Any]) -> bool:
    return any(
        is_plugin_handler(handler)
        for groups in value["hooks"].values()
        for group in groups
        for handler in group["hooks"]
    )


def _groups_have_plugin_handlers(groups: list[dict[str, Any]]) -> bool:
    return any(
        is_plugin_handler(handler)
        for group in groups
        for handler in group["hooks"]
    )


def merge_hooks(template_data: bytes, existing_data: bytes) -> bytes:
    """Replace marker-owned handlers and retain foreign hook content in stable order."""

    template = parse_hooks(template_data, "Codex template hooks.json")
    existing = parse_hooks(existing_data)
    _validate_hook_template(template)

    try:
        merged = copy.deepcopy(template)
        merged_hooks = merged["hooks"]
        for event, groups in existing["hooks"].items():
            foreign = _foreign_groups(groups)
            if event in merged_hooks:
                if foreign:
                    merged_hooks[event].extend(foreign)
            elif foreign or not groups or not _groups_have_plugin_handlers(groups):
                merged_hooks[event] = foreign
        for key, value in existing.items():
            if key != "hooks":
                if key in merged:
                    del merged[key]
                merged[key] = copy.deepcopy(value)
        rendered = _render_json_document(merged)
        _verify_hook_output(rendered, merged)
    except RecursionError as exc:
        raise CodexLayerError("forge install: malformed .codex/hooks.json") from exc
    if len(rendered) > MAX_INPUT_BYTES:
        raise CodexLayerError("forge install: Codex hooks merge output is oversized")
    return rendered


def _verify_hook_output(rendered: bytes, expected: dict[str, Any]) -> None:
    try:
        actual = _parse_hooks(
            rendered, "merged Codex hooks.json", enforce_limit=False
        )
    except CodexLayerError as exc:
        raise CodexLayerError("forge install: Codex hooks merge verification failed") from exc
    if not _json_equal_ordered(actual, expected):
        raise CodexLayerError("forge install: Codex hooks merge verification failed")


def _json_equal_ordered(left: object, right: object) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict) and isinstance(right, dict):
        return list(left) == list(right) and all(
            _json_equal_ordered(left[key], right[key]) for key in left
        )
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _json_equal_ordered(left_item, right_item)
            for left_item, right_item in zip(left, right, strict=True)
        )
    return left == right


def _parse_toml(data: bytes, label: str) -> dict[str, Any]:
    if tomllib is None:
        raise CodexLayerError("forge install: Python tomllib is unavailable")
    try:
        value = tomllib.loads(_decode(data, label))
    except (tomllib.TOMLDecodeError, CodexLayerError) as exc:
        if isinstance(exc, CodexLayerError) and str(exc).startswith("forge install:"):
            raise
        raise CodexLayerError(f"forge install: malformed {label}") from exc
    if not isinstance(value, dict):
        raise CodexLayerError(f"forge install: malformed {label}")
    return value


def _tree_has_unknown(existing: object, template: object) -> bool:
    if isinstance(existing, list):
        return any(_tree_has_unknown(item, template) for item in existing)
    if not isinstance(existing, dict):
        return False
    if not isinstance(template, dict):
        return bool(existing)
    for key, value in existing.items():
        if key not in template or _tree_has_unknown(value, template[key]):
            return True
    return False


def _advance_toml_string(text: str, index: int, quote: str) -> tuple[int, str]:
    if quote == '"':
        if text[index] == "\\":
            return index + 2, quote
        return index + 1, "" if text[index] == '"' else quote
    if quote == "'":
        return index + 1, "" if text[index] == "'" else quote
    if text.startswith(quote, index):
        delimiter = quote[0]
        while index < len(text) and text[index] == delimiter:
            index += 1
        return index, ""
    if quote == '"""' and text[index] == "\\":
        return index + 2, quote
    return index + 1, quote


def _toml_comment_tokens(data: bytes) -> tuple[str, ...]:
    text = _decode(data, ".codex/config.toml")
    index = 0
    quote = ""
    comments: list[str] = []
    while index < len(text):
        if quote:
            index, quote = _advance_toml_string(text, index, quote)
        elif text.startswith(('"""', "'''"), index):
            quote = text[index : index + 3]
            index += 3
        elif text[index] in {'"', "'"}:
            quote = text[index]
            index += 1
        elif text[index] == "#":
            end = text.find("\n", index)
            comment = text[index:] if end < 0 else text[index:end]
            comments.append(comment)
            index = len(text) if end < 0 else end + 1
        else:
            index += 1
    return tuple(comments)


def _has_foreign_toml_comment(data: bytes) -> bool:
    return any(
        not comment.startswith(OWNED_TOML_COMMENT_PREFIXES)
        for comment in _toml_comment_tokens(data)
    )


def config_requires_collision(existing_data: bytes, template_data: bytes) -> bool:
    """Return whether a managed config contains content outside Forge ownership."""

    if tomllib is None:
        return True
    existing = _parse_toml(existing_data, ".codex/config.toml")
    template = _parse_toml(template_data, "Codex template config.toml")
    if any(key not in CONFIG_ROOT_KEYS for key in existing):
        return True
    if _has_foreign_toml_comment(existing_data):
        return True
    if "agents" not in existing:
        return False
    return _tree_has_unknown(existing["agents"], template.get("agents"))


def _is_managed_config(data: bytes) -> bool:
    return any(
        comment.startswith(OWNED_TOML_COMMENT_PREFIXES)
        for comment in _toml_comment_tokens(data)
    )


def _read_bounded(
    path: Path,
    label: str,
    *,
    missing_ok: bool,
    nonregular: str,
) -> bytes | None:
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise CodexLayerError("forge install: no-follow file reads are unavailable")
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | nofollow)
    except FileNotFoundError as exc:
        if missing_ok:
            return None
        raise CodexLayerError(f"forge install: missing {label}: {path}") from exc
    except OSError as exc:
        raise CodexLayerError(nonregular) from exc
    try:
        status = os.fstat(descriptor)
        if not stat.S_ISREG(status.st_mode):
            raise CodexLayerError(nonregular)
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            data = handle.read(MAX_INPUT_BYTES + 1)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(data) > MAX_INPUT_BYTES:
        raise CodexLayerError(f"forge install: malformed {label}")
    return data


def _read_regular(path: Path, label: str) -> bytes:
    data = _read_bounded(
        path,
        label,
        missing_ok=False,
        nonregular=f"forge install: destination is not a regular file: {path}",
    )
    assert data is not None
    return data


def _read_existing(path: Path, label: str | None = None) -> bytes | None:
    return _read_bounded(
        path,
        label or str(path),
        missing_ok=True,
        nonregular=f"forge install: destination is not a regular file: {path}",
    )


def _validate_target_directory(path: Path) -> None:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return
    if not stat.S_ISDIR(mode):
        raise CodexLayerError(
            f"forge install: Codex destination is not a directory: {path}"
        )


def _validate_template_data(path: Path, data: bytes, label: str) -> None:
    _decode(data, label)
    if path.suffix == ".json":
        _parse_json(data, label)
    elif path.suffix == ".toml" and tomllib is not None:
        _parse_toml(data, label)


def _validate_template_tree(root: Path) -> dict[Path, bytes]:
    try:
        root_mode = root.lstat().st_mode
    except FileNotFoundError as exc:
        raise CodexLayerError(f"forge install: missing Codex template directory: {root}") from exc
    if not stat.S_ISDIR(root_mode):
        raise CodexLayerError(f"forge install: Codex template is not a directory: {root}")

    files: dict[Path, bytes] = {}
    pending = [root]
    while pending:
        directory = pending.pop()
        for path in sorted(directory.iterdir(), key=lambda item: item.name, reverse=True):
            mode = path.lstat().st_mode
            if stat.S_ISDIR(mode):
                pending.append(path)
                continue
            if not stat.S_ISREG(mode):
                raise CodexLayerError(
                    f"forge install: Codex template is not a regular file: {path}"
                )
            relative = path.relative_to(root).as_posix()
            label = f"Codex template {relative}"
            data = _read_bounded(
                path,
                label,
                missing_ok=False,
                nonregular=(
                    f"forge install: Codex template is not a regular file: {path}"
                ),
            )
            assert data is not None
            _validate_template_data(path, data, label)
            files[path] = data
    return files


def stage_templates(
    source_root: Path,
    output_root: Path,
    project_name: str,
    install_date: str,
    manifest: Path | None = None,
) -> None:
    """Snapshot, render, and validate the complete Codex template tree."""

    replacements = {
        b"{{FORGE_PROJECT_NAME}}": project_name.encode("utf-8"),
        b"{{FORGE_INSTALL_DATE}}": install_date.encode("ascii"),
    }
    files = _validate_template_tree(source_root)
    output_root.mkdir(parents=True)
    destinations: list[Path] = []
    ordered = sorted(
        files,
        key=lambda path: os.fsencode(path.relative_to(source_root)),
    )
    for source in ordered:
        data = files[source]
        relative = source.relative_to(source_root)
        rendered = data
        for token, value in replacements.items():
            rendered = rendered.replace(token, value)
        _validate_template_data(
            relative, rendered, f"Codex template {relative.as_posix()}"
        )
        destination = output_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(rendered)
        destinations.append(destination)
    if manifest is not None:
        manifest.write_bytes(b"".join(os.fsencode(path) + b"\0" for path in destinations))


def _validate_install_destinations(
    target_dir: Path, template_root: Path, templates: dict[Path, bytes]
) -> None:
    checked_directories = {target_dir}
    for template in templates:
        relative = template.relative_to(template_root)
        parent = target_dir
        for part in relative.parts[:-1]:
            parent /= part
            if parent in checked_directories:
                continue
            _validate_target_directory(parent)
            checked_directories.add(parent)
        destination = target_dir / relative
        try:
            mode = destination.lstat().st_mode
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(mode):
            raise CodexLayerError(
                f"forge install: destination is not a regular file: {destination}"
            )


def _prepare_config(template: bytes, existing: bytes | None, replace: bool) -> PreparedFile:
    _decode(template, "Codex template config.toml")
    if tomllib is not None:
        _parse_toml(template, "Codex template config.toml")
    if existing is None:
        return PreparedFile("install", template)
    _decode(existing, ".codex/config.toml")
    if tomllib is None:
        return PreparedFile("collision", template)
    _parse_toml(existing, ".codex/config.toml")
    collision = not (replace or existing == template) and (
        not _is_managed_config(existing)
        or config_requires_collision(existing, template)
    )
    return PreparedFile("collision" if collision else "install", template)


def _prepare_hooks(template: bytes, existing: bytes | None, replace: bool) -> PreparedFile:
    parsed_template = parse_hooks(template, "Codex template hooks.json")
    _validate_hook_template(parsed_template)
    if existing is None:
        return PreparedFile("install", template)
    parsed_existing = parse_hooks(existing)
    if replace:
        return PreparedFile("install", template)
    if existing == template:
        return PreparedFile("install", template)
    if not _has_plugin_handlers(parsed_existing):
        return PreparedFile("collision", template)
    return PreparedFile("install", merge_hooks(template, existing))


def _validate_sidecar(target: Path, filename: str, template: bytes) -> bytes | None:
    sibling = target / f"{filename}.forge-new"
    existing = _read_existing(sibling)
    if existing is None or existing == template:
        return existing
    raise CodexLayerError(
        f"forge install: refusing to overwrite non-forge collision sibling: {sibling}"
    )


def _write_preconditions(
    output_dir: Path,
    existing: dict[str, bytes | None],
    sidecars: dict[str, bytes | None],
) -> None:
    preconditions = output_dir / "preconditions"
    preconditions.mkdir(exist_ok=True)
    for name in CODEX_FILENAMES:
        (preconditions / name).unlink(missing_ok=True)
        (preconditions / f"{name}.forge-new").unlink(missing_ok=True)
        if existing[name] is not None:
            (preconditions / name).write_bytes(existing[name])
        if sidecars[name] is not None:
            (preconditions / f"{name}.forge-new").write_bytes(sidecars[name])


def verify_preconditions(
    preconditions: Path,
    target_dir: Path,
    filenames: tuple[str, ...] = CODEX_FILENAMES,
) -> None:
    """Refuse when a Codex input changed after the preparation snapshot."""

    _validate_target_directory(target_dir)
    if not filenames or not set(filenames) <= set(CODEX_FILENAMES):
        raise CodexLayerError("forge install: invalid Codex precondition selection")
    for name in filenames:
        for relative in (name, f"{name}.forge-new"):
            expected_path = preconditions / relative
            expected = _read_existing(expected_path)
            actual = _read_existing(target_dir / relative)
            if actual != expected:
                raise CodexLayerError(
                    "forge install: Codex input changed after preflight: "
                    f"{target_dir / relative}"
                )


def snapshot_inputs(target_dir: Path, output_dir: Path) -> None:
    """Capture bounded regular Codex inputs for signature classification."""

    _validate_target_directory(target_dir)
    output_dir.mkdir(parents=True)
    for name in CODEX_FILENAMES:
        data = _read_existing(target_dir / name, f".codex/{name}")
        if data is not None:
            (output_dir / name).write_bytes(data)


def _parse_replace_set(value: str) -> frozenset[str]:
    if value == "none":
        return frozenset()
    result = frozenset(item for item in value.split(",") if item)
    if not result <= set(CODEX_FILENAMES):
        raise CodexLayerError("forge install: invalid Codex replacement plan")
    return result


def prepare(
    template_dir: Path,
    target_dir: Path,
    output_dir: Path,
    replace: str,
    validation_dir: Path | None = None,
) -> None:
    """Validate both files and stage deterministic candidates plus an action plan."""

    template_root = validation_dir or template_dir
    install_templates = _validate_template_tree(template_root)
    _validate_target_directory(target_dir)
    _validate_install_destinations(target_dir, template_root, install_templates)
    replacements = _parse_replace_set(replace)
    templates = {
        name: _read_regular(template_dir / name, f"Codex template {name}")
        for name in CODEX_FILENAMES
    }
    existing = {
        name: _read_existing(target_dir / name, f".codex/{name}")
        for name in CODEX_FILENAMES
    }
    prepared = {
        "config.toml": _prepare_config(
            templates["config.toml"],
            existing["config.toml"],
            "config.toml" in replacements,
        ),
        "hooks.json": _prepare_hooks(
            templates["hooks.json"],
            existing["hooks.json"],
            "hooks.json" in replacements,
        ),
    }
    sidecars = {
        name: _validate_sidecar(target_dir, name, templates[name])
        for name in CODEX_FILENAMES
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_preconditions(output_dir, existing, sidecars)
    for name in CODEX_FILENAMES:
        (output_dir / name).write_bytes(prepared[name].content)
    plan = "".join(f"{name}={prepared[name].action}\n" for name in CODEX_FILENAMES)
    (output_dir / "plan").write_text(plan, encoding="ascii")


def _usage() -> int:
    print(
        "usage: codex_layer_merge.py prepare TEMPLATE_DIR TARGET_DIR OUTPUT_DIR "
        "REPLACE_SET [VALIDATION_DIR]\n"
        "       codex_layer_merge.py stage SOURCE_DIR OUTPUT_DIR PROJECT DATE [MANIFEST]\n"
        "       codex_layer_merge.py snapshot TARGET_DIR OUTPUT_DIR\n"
        "       codex_layer_merge.py verify PRECONDITIONS_DIR TARGET_DIR [FILE]",
        file=sys.stderr,
    )
    return 2


def _dispatch(arguments: list[str]) -> int:
    if arguments and arguments[0] == "stage":
        if len(arguments) not in {5, 6}:
            return _usage()
        stage_templates(
            Path(arguments[1]),
            Path(arguments[2]),
            arguments[3],
            arguments[4],
            Path(arguments[5]) if len(arguments) == 6 else None,
        )
    elif arguments and arguments[0] == "verify":
        if len(arguments) not in {3, 4}:
            return _usage()
        verify_preconditions(
            Path(arguments[1]),
            Path(arguments[2]),
            (arguments[3],) if len(arguments) == 4 else CODEX_FILENAMES,
        )
    elif arguments and arguments[0] == "snapshot":
        if len(arguments) != 3:
            return _usage()
        snapshot_inputs(Path(arguments[1]), Path(arguments[2]))
    elif arguments and arguments[0] == "prepare":
        if len(arguments) not in {5, 6}:
            return _usage()
        prepare(
            Path(arguments[1]),
            Path(arguments[2]),
            Path(arguments[3]),
            arguments[4],
            Path(arguments[5]) if len(arguments) == 6 else None,
        )
    else:
        return _usage()
    return 0


def main(arguments: list[str]) -> int:
    try:
        return _dispatch(arguments)
    except (CodexLayerError, OSError, UnicodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
