"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
import copy
import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence
from forge_cli import chain_core, runtime


def _decode_merge_bootstrap_result(
    raw: chain_core.FencedProcessResult,
    *,
    run_bound: bool,
    fetch_argv: Sequence[str] | None = None,
    worktree: Path | None = None,
    candidate_head: str | None = None,
    environment_digest: str | None = None,
) -> chain_core.FencedProcessResult:
    """Authenticate the bounded protocol and expose one composite result."""

    zero_digest = hashlib.sha256(b"").hexdigest()
    if (
        raw.returncode != 0
        or raw.launch_failed
        or raw.timed_out
        or raw.output_limit
        or raw.group_survived
    ):
        return dataclasses.replace(raw, output=b"", output_digest=zero_digest)
    try:
        protocol = json.loads(raw.output)
        if (
            not isinstance(protocol, dict)
            or set(protocol)
            != {
                "schema",
                "constituent_order",
                "environment_digest",
                "resolved_tip",
                "fetch",
                "scope",
                "scope_changed_paths",
                "full_patch",
            }
            or protocol.get("schema") != "forge-bootstrap-composite-result/1"
        ):
            raise ValueError("composite result envelope is malformed")
        observed_environment_digest = protocol.get("environment_digest")
        if (
            not isinstance(observed_environment_digest, str)
            or chain_core.SHA256_RE.fullmatch(observed_environment_digest) is None
            or (
                environment_digest is not None
                and observed_environment_digest != environment_digest
            )
        ):
            raise ValueError("composite environment diverges from its exact contract")

        def constituent(value: Any, label: str) -> dict[str, Any]:
            if not isinstance(value, dict) or set(value) != {
                "argv",
                "exit",
                "output_digest",
                "stderr_digest",
                "launch_failed",
                "output_limit_exceeded",
            }:
                raise ValueError(f"{label} result is malformed")
            argv = value.get("argv")
            if (
                not isinstance(argv, list)
                or not argv
                or not all(
                    isinstance(item, str) and "\x00" not in item for item in argv
                )
                or (
                    value.get("exit") is not None
                    and (
                        not isinstance(value.get("exit"), int)
                        or isinstance(value.get("exit"), bool)
                    )
                )
                or any(
                    not isinstance(value.get(name), str)
                    or chain_core.SHA256_RE.fullmatch(str(value[name])) is None
                    for name in ("output_digest", "stderr_digest")
                )
                or type(value.get("launch_failed")) is not bool
                or type(value.get("output_limit_exceeded")) is not bool
            ):
                raise ValueError(f"{label} result fields are malformed")
            return value

        def passed(record: Mapping[str, Any]) -> bool:
            return bool(
                record.get("exit") == 0
                and record.get("launch_failed") is False
                and record.get("output_limit_exceeded") is False
            )

        order = protocol.get("constituent_order")
        if not isinstance(order, list) or not all(
            isinstance(label, str) for label in order
        ):
            raise ValueError("composite constituent order is malformed")
        fetch = constituent(protocol.get("fetch"), "fetch")
        if fetch_argv is not None and fetch.get("argv") != list(fetch_argv):
            raise ValueError("composite fetch argv diverges from admission")
        resolved_tip = protocol.get("resolved_tip")
        scope: dict[str, Any] | None = None
        patch: dict[str, Any] | None = None
        records: list[dict[str, Any]] = [fetch]
        expected_order = ["fetch"]

        if passed(fetch):
            if (
                not isinstance(resolved_tip, str)
                or chain_core.COMMIT_RE.fullmatch(resolved_tip) is None
            ):
                raise ValueError("composite resolved tip is malformed")
            if worktree is None or candidate_head is None:
                raise ValueError("composite argv context is unavailable")
            if run_bound:
                expected_order.append("name-status")
                scope = constituent(protocol.get("scope"), "name-status")
                records.append(scope)
                if scope.get("argv") != chain_core._merge_scope_argv(
                    worktree, resolved_tip, candidate_head
                ):
                    raise ValueError("composite name-status argv diverges")
                paths = protocol.get("scope_changed_paths")
                if passed(scope):
                    _batch, _builders, journal = runtime._coordination_modules()
                    if not chain_core._valid_sorted_unique_strings(paths) or not all(
                        journal._valid_scope_item(path) for path in paths
                    ):
                        raise ValueError("scope changed-path set is malformed")
                elif paths is not None:
                    raise ValueError("failed name-status invented changed paths")
            elif (
                protocol.get("scope") is not None
                or protocol.get("scope_changed_paths") is not None
            ):
                raise ValueError("unbound composite invented a scope constituent")

            if scope is None or passed(scope):
                expected_order.append("full-patch")
                patch = constituent(protocol.get("full_patch"), "full-patch")
                records.append(patch)
                if patch.get("argv") != chain_core._merge_full_patch_argv(
                    worktree, resolved_tip, candidate_head
                ):
                    raise ValueError("composite full-patch argv diverges")
            elif protocol.get("full_patch") is not None:
                raise ValueError("full-patch ran after failed name-status")
        else:
            if resolved_tip is not None:
                raise ValueError("failed fetch invented a resolved tip")
            if (
                protocol.get("scope") is not None
                or protocol.get("scope_changed_paths") is not None
                or protocol.get("full_patch") is not None
            ):
                raise ValueError("a constituent ran after failed fetch")

        if order != expected_order:
            raise ValueError("composite constituent order diverges")
        complete = bool(
            expected_order[-1] == "full-patch" and all(passed(record) for record in records)
        )
        slot_digest = str(scope["output_digest"]) if scope is not None else zero_digest
        return dataclasses.replace(
            raw,
            returncode=(
                0
                if complete
                else next(
                    (
                        int(record["exit"])
                        for record in records
                        if isinstance(record.get("exit"), int)
                        and record.get("exit") != 0
                    ),
                    1,
                )
            ),
            output=b"",
            output_digest=slot_digest,
            output_limit=any(
                record.get("output_limit_exceeded") is True for record in records
            ),
            launch_failed=any(
                record.get("launch_failed") is True for record in records
            ),
            metadata=copy.deepcopy(protocol),
        )
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        return dataclasses.replace(
            raw,
            returncode=1,
            output=b"",
            output_digest=zero_digest,
            launch_failed=True,
            metadata={"protocol_error": str(exc)},
        )
