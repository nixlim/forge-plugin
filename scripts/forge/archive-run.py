#!/usr/bin/env python3
"""Render and stage the deterministic durable-intent archive for a closed run."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence

# Use the journal reader shared by validation. The script lives one directory
# below the import root when installed by the plugin.
SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from codex_orchestrator.journal import (
    read_journal as read_shared_journal,
    validate_run,
)
from commitment_paths import path_tokens


CONTAMINATION = "forge: archive refused — close tree contains unrelated changes"
NONE = "None recorded"
HEX_HEAD = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
HEAD_IN_TEXT = re.compile(r"(?<![0-9a-f])[0-9a-f]{40}(?:[0-9a-f]{24})?(?![0-9a-f])")
HEAD_RANGE_IN_TEXT = re.compile(
    r"(?<![0-9a-f])[0-9a-f]{40}(?:[0-9a-f]{24})?"
    r"\.\."
    r"[0-9a-f]{40}(?:[0-9a-f]{24})?(?![0-9a-f])"
)
ITERATION_IN_TEXT = re.compile(r"\biteration\s+(\d+)\b", re.IGNORECASE)
VERDICT_IN_TEXT = re.compile(r"\b(PASS|BLOCK)\b")


class ArchiveRefusal(Exception):
    """A fail-closed archive precondition or transaction failure."""

    def __init__(self, message: str, *, contamination: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.contamination = contamination


class ContractArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ArchiveRefusal(f"forge: archive refused — invalid invocation: {message}")


def run_git(repo: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ["git", *arguments],
            cwd=repo,
            check=False,
            capture_output=True,
        )
    except OSError as exc:
        raise ArchiveRefusal(f"forge: archive refused — git failed: {exc}") from exc


def git_stdout(repo: Path, *arguments: str) -> bytes:
    result = run_git(repo, *arguments)
    if result.returncode != 0:
        diagnostic = result.stderr.decode("utf-8", errors="replace").strip()
        suffix = f": {diagnostic}" if diagnostic else ""
        raise ArchiveRefusal(f"forge: archive refused — git failed{suffix}")
    return result.stdout


def repository_root() -> Path:
    result = run_git(Path.cwd(), "rev-parse", "--show-toplevel")
    if result.returncode != 0:
        raise ArchiveRefusal("forge: archive refused — current directory is not a repository")
    try:
        return Path(result.stdout.decode("utf-8").strip()).resolve(strict=True)
    except (OSError, UnicodeError, ValueError) as exc:
        raise ArchiveRefusal("forge: archive refused — repository root is invalid") from exc


def nul_paths(value: bytes) -> list[bytes]:
    return [item for item in value.split(b"\0") if item]


def dirty_paths(repo: Path) -> list[bytes]:
    return nul_paths(
        git_stdout(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    )


def prove_clean(repo: Path) -> None:
    if dirty_paths(repo):
        raise ArchiveRefusal(CONTAMINATION, contamination=True)


def resolve_run_dir(value: str) -> Path:
    try:
        path = Path(value).expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ArchiveRefusal("forge: archive refused — run directory does not exist") from exc
    if not path.is_dir():
        raise ArchiveRefusal("forge: archive refused — run directory does not exist")
    return path


def read_json_file(path_value: str, purpose: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path_value).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ArchiveRefusal(f"forge: archive refused — invalid {purpose}") from exc
    if not isinstance(value, dict):
        raise ArchiveRefusal(f"forge: archive refused — invalid {purpose}")
    return value


def read_journal(run_dir: Path) -> list[dict[str, Any]]:
    records, issues = read_shared_journal(run_dir / "journal.jsonl")
    if issues:
        raise ArchiveRefusal("forge: archive refused — invalid run journal")
    return records


def only_record(records: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    matches = [record for record in records if record.get("type") == kind]
    if len(matches) != 1:
        raise ArchiveRefusal("forge: archive refused — invalid run journal")
    return matches[0]


def display(value: object) -> str:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return NONE


def markdown_list(value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        return [NONE]
    rendered = [f"- {display(item)}" for item in value]
    return rendered or [NONE]


def table_cell(value: object) -> str:
    text = display(value)
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\r", " ").replace("\n", "<br>")


def canonical_json(value: object) -> list[str]:
    if value is None:
        return [NONE]
    return ["```json", json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2), "```"]


def canonical_payload(value: object) -> dict[str, object] | None:
    """Return a validation payload without dictionary insertion-order concerns."""

    if not isinstance(value, dict):
        return None
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True))


def is_passing_gated_payload(value: object) -> bool:
    return (
        isinstance(value, dict)
        and value.get("ok") is True
        and value.get("profile") == "gates"
        and value.get("issues") == []
    )


def recompute_pre_close_validation(
    run_dir: Path, records: list[dict[str, Any]]
) -> dict[str, object] | None:
    """Run gated validation against the journal prefix before ``run_closed``."""

    if not records or records[-1].get("type") != "run_closed":
        raise ArchiveRefusal("forge: archive refused — run_closed must be final")
    try:
        prefix = b"".join(
            json.dumps(
                {key: value for key, value in record.items() if key != "_line"},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
            for record in records[:-1]
        )
        with tempfile.TemporaryDirectory(prefix="forge-pre-close-") as temporary:
            mirror = Path(temporary) / run_dir.name
            mirror.mkdir()
            for child in run_dir.iterdir():
                if child.name == "journal.jsonl":
                    continue
                os.symlink(
                    child.resolve(),
                    mirror / child.name,
                    target_is_directory=child.is_dir(),
                )
            (mirror / "journal.jsonl").write_bytes(prefix)
            return canonical_payload(validate_run(mirror, gates=True))
    except (OSError, TypeError, ValueError) as exc:
        raise ArchiveRefusal(
            f"forge: archive refused — could not recompute pre-close validation: {exc}"
        ) from exc


def candidate_for(record: dict[str, Any]) -> str:
    candidate = record.get("candidate")
    if isinstance(candidate, str) and candidate:
        return candidate
    check = record.get("check")
    if not isinstance(check, str):
        return NONE
    reviewed_range = HEAD_RANGE_IN_TEXT.search(check)
    if reviewed_range:
        return reviewed_range.group(0)
    matches = HEAD_IN_TEXT.findall(check)
    return matches[-1] if matches else NONE


def verdict_for(record: dict[str, Any]) -> str:
    verdict = record.get("verdict")
    if isinstance(verdict, str) and verdict:
        return verdict
    observation = record.get("observation")
    match = VERDICT_IN_TEXT.search(observation) if isinstance(observation, str) else None
    return match.group(1) if match else NONE


def iteration_for(record: dict[str, Any]) -> str:
    iteration = record.get("iteration")
    if isinstance(iteration, int) and not isinstance(iteration, bool) and iteration > 0:
        return str(iteration)
    for field in ("observation", "check"):
        value = record.get(field)
        match = ITERATION_IN_TEXT.search(value) if isinstance(value, str) else None
        if match:
            return match.group(1)
    return NONE


def document_references(value: str) -> list[str]:
    """Extract document paths while retaining ``value`` as the archive label."""

    return path_tokens(value, context="basis")


def basis_label(value: str) -> str:
    """Keep the basis text as the delimiter label after resolving references."""

    return value


def document_path(repo: Path, run_dir: Path, value: str) -> Path | None:
    raw = Path(value)
    if raw.is_absolute():
        return None
    candidates = ((run_dir, run_dir / raw), (repo, repo / raw))
    for root, candidate in candidates:
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root.resolve(strict=True))
        except (OSError, RuntimeError, ValueError):
            continue
        if resolved.is_file():
            return resolved
    return None


def basis_documents(
    repo: Path, run_dir: Path, decisions: list[dict[str, Any]]
) -> list[tuple[str, str, Path]]:
    documents: list[tuple[str, str, Path]] = []
    seen: set[Path] = set()
    for decision in decisions:
        basis = decision.get("basis")
        if not isinstance(basis, list):
            continue
        for value in basis:
            if not isinstance(value, str) or not value:
                continue
            for reference in document_references(value):
                path = document_path(repo, run_dir, reference)
                if path is None or path in seen:
                    continue
                try:
                    # read_text() performs universal-newline conversion. Decode
                    # bytes directly so the delimited body remains byte-exact.
                    content = path.read_bytes().decode("utf-8")
                except (OSError, UnicodeError) as exc:
                    raise ArchiveRefusal(
                        f"forge: archive refused — basis document is not UTF-8: {value}"
                    ) from exc
                seen.add(path)
                documents.append((value, content, path))
    return documents


def render_archive(
    *,
    repo: Path,
    run_dir: Path,
    records: list[dict[str, Any]],
    closing_head: str,
    post_close: dict[str, Any],
    audit_fragment: str,
) -> str:
    started = only_record(records, "run_started")
    closed = only_record(records, "run_closed")
    run_id = run_dir.name
    if started.get("run_id") != run_id or closed.get("judgment") != "passed":
        raise ArchiveRefusal("forge: archive refused — invalid run journal")
    recorded_repo = started.get("repo")
    try:
        same_repo = (
            isinstance(recorded_repo, str)
            and Path(recorded_repo).expanduser().resolve(strict=True) == repo
        )
    except (OSError, RuntimeError, ValueError):
        same_repo = False
    if not same_repo:
        raise ArchiveRefusal(
            "forge: archive refused — run repository does not match current repository"
        )
    starting_head = started.get("repo_head")
    if not isinstance(starting_head, str) or not HEX_HEAD.fullmatch(starting_head):
        raise ArchiveRefusal("forge: archive refused — invalid starting HEAD")
    start_commit = run_git(repo, "cat-file", "-e", f"{starting_head}^{{commit}}")
    if start_commit.returncode != 0:
        raise ArchiveRefusal("forge: archive refused — starting HEAD is not a repository commit")
    pre_close = canonical_payload(closed.get("validation"))
    if not is_passing_gated_payload(pre_close):
        raise ArchiveRefusal("forge: archive refused — pre-close gated validation did not pass")

    latest_tasks: dict[str, dict[str, Any]] = {}
    task_order: list[str] = []
    for record in records:
        if record.get("type") != "task":
            continue
        task_id = record.get("id")
        if not isinstance(task_id, str) or not task_id:
            continue
        if task_id not in latest_tasks:
            task_order.append(task_id)
        # Terminal task updates are permitted to be terse. Carry the durable
        # task contract forward while taking the final outcome from the latest
        # entry.
        previous = latest_tasks.get(task_id, {})
        merged = dict(record)
        if "goal" not in record and "goal" in previous:
            merged["goal"] = previous["goal"]
        if "acceptance" not in record and "acceptance" in previous:
            merged["acceptance"] = previous["acceptance"]
        latest_tasks[task_id] = merged
    decisions = [record for record in records if record.get("type") == "decision"]
    gates = [
        record
        for record in records
        if record.get("type") == "verification"
        and isinstance(record.get("criterion"), str)
        and record["criterion"].startswith(("gate-1: ", "gate-2: ", "gate-3: "))
    ]

    lines = [
        f"# Durable intent archive: {run_id}",
        "",
        "## Goal",
        "",
        display(started.get("goal")),
        "",
        "## Tasks",
        "",
    ]
    if not task_order:
        lines.extend([NONE, ""])
    for task_id in task_order:
        task = latest_tasks[task_id]
        final_outcome = task.get("outcome")
        lines.extend(
            [
                f"### {task_id}",
                "",
                f"Goal: {display(task.get('goal'))}",
                "",
                "Acceptance criteria:",
                "",
                *markdown_list(task.get("acceptance")),
                "",
                f"Final status: {display(task.get('status'))}",
                "",
                f"Final outcome: {display(final_outcome)}",
                "",
            ]
        )

    lines.extend(["## Decisions", ""])
    if not decisions:
        lines.extend([NONE, ""])
    for number, decision in enumerate(decisions, start=1):
        decision_id = display(decision.get("id"))
        if decision_id == NONE:
            decision_id = f"Decision {number}"
        lines.extend(
            [
                f"### {decision_id}",
                "",
                f"Task: {display(decision.get('task'))}",
                "",
                f"Finding: {display(decision.get('finding'))}",
                "",
                f"Outcome: {display(decision.get('outcome'))}",
                "",
                f"Resolution: {display(decision.get('resolution'))}",
                "",
                "Basis:",
                "",
                *markdown_list(decision.get("basis")),
                "",
            ]
        )

    lines.extend(["## Verbatim basis documents", ""])
    documents = basis_documents(repo, run_dir, decisions)
    referenced_documents = {
        path.resolve()
        for decision in decisions
        for value in decision.get("basis", [])
        if isinstance(value, str)
        for reference in document_references(value)
        if (path := document_path(repo, run_dir, reference)) is not None
    }
    if {path.resolve() for _, _, path in documents} != referenced_documents:
        raise ArchiveRefusal("forge: archive refused — could not copy every basis document")
    if not documents:
        lines.extend([NONE, ""])
    for source, content, _ in documents:
        lines.extend([f"### {source}", "", f"<!-- BEGIN VERBATIM DOCUMENT: {source} -->"])
        # Do not normalize, trim, or add bytes inside the delimited source body.
        lines[-1] += "\n" + content + f"<!-- END VERBATIM DOCUMENT: {source} -->"
        lines.append("")

    lines.extend(
        [
            "## Gate evidence",
            "",
            "| Gate | Check | Candidate | Result | Reviewer verdict | Iteration |",
            "|---|---|---|---|---|---|",
        ]
    )
    if not gates:
        lines.append(
            f"| {NONE} | {NONE} | {NONE} | {NONE} | {NONE} | {NONE} |"
        )
    else:
        for gate in gates:
            check = gate.get("check")
            lines.append(
                "| "
                + " | ".join(
                    table_cell(value)
                    for value in (
                        gate.get("criterion"),
                        check,
                        candidate_for(gate),
                        gate.get("result"),
                        verdict_for(gate),
                        iteration_for(gate),
                    )
                )
                + " |"
            )
    lines.extend(["", audit_fragment.rstrip("\n"), "", "## Provenance", ""])
    lines.extend(
        [
            f"Run ID: {run_id}",
            "",
            f"Starting HEAD: {starting_head}",
            "",
            f"Closing HEAD: {closing_head}",
            "",
            "### Pre-close validation payload embedded in `run_closed`",
            "",
            *canonical_json(pre_close),
            "",
            "### Post-close validation result",
            "",
            *canonical_json(post_close),
            "",
        ]
    )
    return "\n".join(lines)


def run_audit(run_dir: Path) -> str:
    audit = Path(__file__).with_name("audit-commitments.py")
    try:
        result = subprocess.run(
            [sys.executable, str(audit), "--run-dir", str(run_dir)],
            check=False,
            capture_output=True,
        )
    except OSError as exc:
        raise ArchiveRefusal(f"forge: archive refused — commitments audit failed: {exc}") from exc
    if result.returncode:
        if result.stdout:
            sys.stdout.buffer.write(result.stdout)
        if result.stderr:
            sys.stderr.buffer.write(result.stderr)
        raise SystemExit(result.returncode)
    if result.stderr:
        sys.stderr.buffer.write(result.stderr)
    try:
        fragment = result.stdout.decode("utf-8")
    except UnicodeError as exc:
        raise ArchiveRefusal("forge: archive refused — commitments audit output is invalid") from exc
    if not fragment.endswith("\n"):
        raise ArchiveRefusal("forge: archive refused — commitments audit output is invalid")
    return fragment


def cleanup_archive(repo: Path, archive_path: Path, relative: str) -> None:
    failed = False
    try:
        removed = run_git(
            repo, "rm", "--cached", "--force", "--ignore-unmatch", "--", relative
        )
        failed = removed.returncode != 0
    except BaseException:
        # Unlinking must still be attempted if Git cannot be launched.
        failed = True
    try:
        archive_path.unlink(missing_ok=True)
    except BaseException:
        failed = True
    try:
        staged = nul_paths(git_stdout(repo, "diff", "--cached", "--name-only", "-z"))
        failed = failed or os.fsencode(relative) in staged
    except BaseException:
        failed = True
    try:
        failed = failed or archive_path.exists()
    except BaseException:
        failed = True
    if failed:
        raise ArchiveRefusal("forge: archive refused — transaction rollback failed")


def write_and_stage(repo: Path, relative: str, content: str) -> None:
    archive_path = repo / relative
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        try:
            handle = archive_path.open("x", encoding="utf-8", newline="")
        except FileExistsError as exc:
            raise ArchiveRefusal(
                f"forge: archive refused — archive already exists: {relative}"
            ) from exc
        created = True
        with handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException as original:
        if created:
            try:
                cleanup_archive(repo, archive_path, relative)
            except ArchiveRefusal as rollback:
                raise rollback from original
        if isinstance(original, OSError):
            raise ArchiveRefusal(
                f"forge: archive refused — could not write archive: {original}"
            ) from original
        raise

    try:
        if nul_paths(git_stdout(repo, "diff", "--name-only", "-z")):
            raise ArchiveRefusal(CONTAMINATION, contamination=True)
        if nul_paths(git_stdout(repo, "diff", "--cached", "--name-only", "-z")):
            raise ArchiveRefusal(CONTAMINATION, contamination=True)
        if nul_paths(git_stdout(repo, "ls-files", "--others", "--exclude-standard", "-z")) != [
            os.fsencode(relative)
        ]:
            raise ArchiveRefusal(CONTAMINATION, contamination=True)

        add = run_git(repo, "add", "--", relative)
        if add.returncode != 0:
            raise ArchiveRefusal("forge: archive refused — could not stage archive")

        staged_blob = git_stdout(repo, "show", f":{relative}")
        rendered_bytes = content.encode("utf-8")
        if staged_blob != rendered_bytes:
            raise ArchiveRefusal(
                "forge: archive refused — staged archive bytes differ from rendered archive"
            )

        staged = nul_paths(git_stdout(repo, "diff", "--cached", "--name-only", "-z"))
        unstaged = nul_paths(git_stdout(repo, "diff", "--name-only", "-z"))
        untracked = nul_paths(git_stdout(repo, "ls-files", "--others", "--exclude-standard", "-z"))
        if staged != [os.fsencode(relative)] or unstaged or untracked:
            raise ArchiveRefusal(CONTAMINATION, contamination=True)
    except BaseException as original:
        try:
            cleanup_archive(repo, archive_path, relative)
        except ArchiveRefusal as rollback:
            raise rollback from original
        raise


def parser() -> argparse.ArgumentParser:
    result = ContractArgumentParser(description=__doc__)
    result.add_argument("--run-dir", required=True)
    result.add_argument("--closing-head", required=True)
    result.add_argument("--post-close-validation", required=True)
    return result


def archive(arguments: argparse.Namespace) -> str:
    repo = repository_root()
    run_dir = resolve_run_dir(arguments.run_dir)
    run_id = run_dir.name
    relative = f".forge/history/runs/{run_id}.md"
    archive_path = repo / relative

    if archive_path.exists() or archive_path.is_symlink():
        raise ArchiveRefusal(f"forge: archive refused — archive already exists: {relative}")
    prove_clean(repo)

    closing_head = arguments.closing_head
    if not isinstance(closing_head, str) or not HEX_HEAD.fullmatch(closing_head):
        raise ArchiveRefusal("forge: archive refused — invalid closing HEAD")
    recorded_head = git_stdout(repo, "rev-parse", "HEAD").decode("ascii").strip()
    if closing_head != recorded_head:
        raise ArchiveRefusal("forge: archive refused — closing HEAD does not match repository HEAD")

    records = read_journal(run_dir)
    closed_records = [record for record in records if record.get("type") == "run_closed"]
    if len(closed_records) != 1:
        raise ArchiveRefusal("forge: archive refused — journal must contain one run_closed entry")
    closed = closed_records[0]
    embedded_pre_close = canonical_payload(closed.get("validation"))
    if not is_passing_gated_payload(embedded_pre_close):
        raise ArchiveRefusal("forge: archive refused — pre-close gated validation did not pass")

    post_close = canonical_payload(
        read_json_file(arguments.post_close_validation, "post-close gated validation")
    )
    if not is_passing_gated_payload(post_close):
        raise ArchiveRefusal("forge: archive refused — post-close gated validation did not pass")

    ignored = run_git(repo, "check-ignore", "-q", "--", relative)
    if ignored.returncode == 0:
        raise ArchiveRefusal(f"forge: archive refused — archive path is ignored: {relative}")
    if ignored.returncode != 1:
        raise ArchiveRefusal("forge: archive refused — could not verify archive ignore state")

    audit_fragment = run_audit(run_dir)
    fresh_pre_close = recompute_pre_close_validation(run_dir, records)
    if not is_passing_gated_payload(fresh_pre_close) or embedded_pre_close != fresh_pre_close:
        raise ArchiveRefusal(
            "forge: archive refused — pre-close gated validation is stale or does not match journal"
        )
    fresh_validation = canonical_payload(validate_run(run_dir, gates=True))
    if not is_passing_gated_payload(fresh_validation) or post_close != fresh_validation:
        raise ArchiveRefusal(
            "forge: archive refused — post-close gated validation is stale or does not match journal"
        )
    content = render_archive(
        repo=repo,
        run_dir=run_dir,
        records=records,
        closing_head=closing_head,
        post_close=post_close,
        audit_fragment=audit_fragment,
    )
    write_and_stage(repo, relative, content)
    return relative


def main(argv: Sequence[str] | None = None) -> int:
    try:
        arguments = parser().parse_args(argv)
        relative = archive(arguments)
    except ArchiveRefusal as exc:
        print(exc.message, file=sys.stderr)
        return 1
    print(relative)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
