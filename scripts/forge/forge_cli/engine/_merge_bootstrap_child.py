"""Extracted from scripts/forge/forge_cli/engine/__init__.py."""
from __future__ import annotations
import base64
import hashlib
import json
import os
import selectors
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence
from forge_cli import chain_core, runtime
from forge_cli.engine._core import MergeAdmission as MergeAdmission
from forge_cli.engine._merge_scope_derive import _git_environment_digest as _git_environment_digest, _parse_merge_name_status_output as _parse_merge_name_status_output
from forge_cli.engine._state import _MERGE_BOOTSTRAP_CHILD_SOURCE as _MERGE_BOOTSTRAP_CHILD_SOURCE
import sys


def _merge_bootstrap_child_main(encoded_payload: str) -> int:
    """Execute the Revision-12 composite child protocol.

    This entry point runs only inside the already fenced, isolated process
    group.  Full-patch stdout is fed directly into SHA-256 and is never added
    to a bytearray, protocol record, diagnostic, or parent pipe.
    """

    try:
        payload = json.loads(base64.urlsafe_b64decode(encoded_payload.encode("ascii")))
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        os.write(1, chain_core.canonical_bytes({"schema": "forge-bootstrap-composite-error/1", "error": str(exc)}))
        return 2
    cap = int(payload.get("cap", runtime.OUTPUT_CAP_BYTES))
    worktree = Path(str(payload["worktree"]))
    candidate_head = str(payload["candidate_head"])
    supplied_tip = payload.get("remote_tip")
    run_bound = payload.get("run_bound") is True

    def stop(process: subprocess.Popen[bytes]) -> None:
        try:
            process.terminate()
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=chain_core.FENCED_CHILD_STOP_GRACE_SECONDS)
            return
        except subprocess.TimeoutExpired:
            pass
        try:
            process.kill()
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=chain_core.FENCED_CHILD_REAP_SECONDS)
        except subprocess.TimeoutExpired:
            pass

    def run_constituent(
        argv: Sequence[str], *, retain_stdout: bool, stream_stdout: bool
    ) -> tuple[dict[str, Any], bytes]:
        direct_argv = [str(value) for value in argv]
        stdout_digest = hashlib.sha256()
        stderr_digest = hashlib.sha256()
        stdout_total = 0
        stderr_total = 0
        kept = bytearray()
        try:
            process = subprocess.Popen(
                direct_argv,
                cwd=worktree,
                env=dict(os.environ),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=False,
            )
        except OSError:
            return (
                {
                    "argv": direct_argv,
                    "exit": None,
                    "output_digest": hashlib.sha256(b"").hexdigest(),
                    "stderr_digest": hashlib.sha256(b"").hexdigest(),
                    "launch_failed": True,
                    "output_limit_exceeded": False,
                },
                b"",
            )
        assert process.stdout is not None and process.stderr is not None
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        limited = False
        try:
            while selector.get_map():
                for key, _mask in selector.select(0.05):
                    chunk = os.read(key.fileobj.fileno(), 8192)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    if key.data == "stdout":
                        stdout_digest.update(chunk)
                        stdout_total += len(chunk)
                        if retain_stdout and len(kept) < cap:
                            kept.extend(chunk[: cap - len(kept)])
                        if not stream_stdout and stdout_total > cap:
                            limited = True
                    else:
                        stderr_digest.update(chunk)
                        stderr_total += len(chunk)
                    if (
                        stderr_total > cap
                        if stream_stdout
                        else stdout_total + stderr_total > cap
                    ):
                        limited = True
                    if limited:
                        stop(process)
                        break
                if limited:
                    break
            if not limited:
                returncode = process.wait()
            else:
                returncode = process.returncode
        finally:
            selector.close()
            process.stdout.close()
            process.stderr.close()
        return (
            {
                "argv": direct_argv,
                "exit": returncode,
                "output_digest": stdout_digest.hexdigest(),
                "stderr_digest": stderr_digest.hexdigest(),
                "launch_failed": False,
                "output_limit_exceeded": limited,
            },
            bytes(kept),
        )

    def passed(record: Mapping[str, Any]) -> bool:
        return bool(
            record.get("exit") == 0
            and record.get("launch_failed") is False
            and record.get("output_limit_exceeded") is False
        )

    fetch_argv = payload.get("fetch_argv")
    if not isinstance(fetch_argv, list):
        return 2
    constituent_order: list[str] = ["fetch"]
    fetch, _fetch_output = run_constituent(
        [str(value) for value in fetch_argv],
        retain_stdout=False,
        stream_stdout=False,
    )
    resolved_tip: str | None = None
    if passed(fetch):
        if isinstance(supplied_tip, str):
            resolved_tip = supplied_tip
        else:
            try:
                raw = Path(str(payload["git_dir"]), "FETCH_HEAD").read_bytes()
                rows = raw.splitlines()
                oid = rows[0].split(b"\t", 1)[0].decode("ascii")
                if (
                    len(raw) > chain_core.MERGE_SCOPE_BINDING_CAP_BYTES
                    or not raw.endswith(b"\n")
                    or len(rows) != 1
                    or chain_core.COMMIT_RE.fullmatch(oid) is None
                ):
                    raise ValueError("invalid FETCH_HEAD")
                resolved_tip = oid
            except (OSError, UnicodeError, ValueError, IndexError):
                fetch = {**fetch, "exit": 1}

    scope: dict[str, Any] | None = None
    changed_paths: list[str] | None = None
    if passed(fetch) and resolved_tip is not None and run_bound:
        constituent_order.append("name-status")
        scope_argv = chain_core._merge_scope_argv(worktree, resolved_tip, candidate_head)
        scope, scope_output = run_constituent(
            scope_argv, retain_stdout=True, stream_stdout=False
        )
        if passed(scope):
            try:
                changed_paths = list(_parse_merge_name_status_output(scope_output))
            except (UnicodeError, ValueError):
                scope = {**scope, "exit": 1}
                changed_paths = None

    full_patch: dict[str, Any] | None = None
    if (
        passed(fetch)
        and resolved_tip is not None
        and (scope is None or passed(scope))
    ):
        constituent_order.append("full-patch")
        full_patch, _never_retained = run_constituent(
            chain_core._merge_full_patch_argv(worktree, resolved_tip, candidate_head),
            retain_stdout=False,
            stream_stdout=True,
        )
    protocol = {
        "schema": "forge-bootstrap-composite-result/1",
        "constituent_order": constituent_order,
        "environment_digest": _git_environment_digest(os.environ),
        "resolved_tip": resolved_tip,
        "fetch": fetch,
        "scope": scope,
        "scope_changed_paths": changed_paths,
        "full_patch": full_patch,
    }
    encoded = chain_core.canonical_bytes(protocol)
    if len(encoded) > runtime.OUTPUT_CAP_BYTES:
        return 3
    os.write(1, encoded)
    return 0


def _merge_bootstrap_child_argv(
    admission: MergeAdmission,
    *,
    fetch_argv: Sequence[str],
    remote_tip: str | None,
) -> list[str]:
    payload = {
        "schema": "forge-bootstrap-composite-request/1",
        "worktree": str(admission.worktree),
        "git_dir": str(admission.worktree_identity["git_dir"]),
        "candidate_head": admission.candidate_head,
        "remote_tip": remote_tip,
        "run_bound": admission.run_task is not None,
        "fetch_argv": list(fetch_argv),
        "cap": runtime.OUTPUT_CAP_BYTES,
    }
    encoded = base64.urlsafe_b64encode(chain_core.canonical_bytes(payload)).decode("ascii")
    return [
        sys.executable,
        "-c",
        _MERGE_BOOTSTRAP_CHILD_SOURCE,
        # phase 3: the re-exec target stays the shim entry point (scripts/forge/cli.py),
        # which forwards _merge_bootstrap_child_main to this module when loaded standalone;
        # resolved from runtime's own location so it does not depend on this file's depth.
        str(Path(runtime.__file__).resolve().parents[1] / "cli.py"),
        encoded,
    ]
