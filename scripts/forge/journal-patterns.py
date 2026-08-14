#!/usr/bin/env python3
"""Extract deterministic learning patterns from Forge orchestration journals."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import datetime as dt
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Any, Iterable


COMMIT_ID = re.compile(r"[0-9a-f]{7,64}\Z")
ITERATION_RE = re.compile(r"\biteration[ :]([0-9]+)(?:\s+of\s+[0-9]+)?\b", re.IGNORECASE)
GATE3_FINDINGS_RE = re.compile(
    r"^(?:PASS|BLOCK); (?P<blocking>[0-9]+) (?P<label>[^;\r\n]+) findings; "
    r"(?:severities CRITICAL=(?P<critical>[0-9]+),MAJOR=(?P<major>[0-9]+),"
    r"MINOR=(?P<minor>[0-9]+); reviewer (?P<reviewer>review-cheap|review-final); )?"
    r"iteration [0-9]+ of [0-9]+\.(?: .*)?$"
)
OBSERVATION_DIAGNOSTIC_RE = re.compile(r"(?:^|;\s*)diagnostic=(.*)\Z")
TOML_STRING = re.compile(
    r'^\s*(model|model_reasoning_effort)\s*=\s*(["\'])(.*?)\2\s*(?:#.*)?$'
)
YAML_STRING = re.compile(r"^\s*(model|effort):\s*([^#\s][^#]*?)\s*(?:#.*)?$")
VERIFICATION_RESULTS = {"passed", "failed", "inconclusive", "skipped"}


class ExtractionFailure(RuntimeError):
    """A stable, non-secret extraction failure."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def byte_key(value: str) -> bytes:
    return value.encode("utf-8")


def ordered_counts(values: Counter[str]) -> dict[str, int]:
    return {key: values[key] for key in sorted(values, key=byte_key)}


def empty_patterns(*, available: bool, failure: str) -> dict[str, Any]:
    return {
        "available": available,
        "decision_outcomes": {},
        "diagnostics": [],
        "failure": failure,
        "findings": {"by_reviewer_role": {}, "by_severity": {}},
        "routing": [],
        "tasks": [],
    }


def canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ) + "\n"


def canonical_bytes(value: dict[str, Any]) -> bytes:
    return canonical_json(value).encode("utf-8")


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def confined_regular_file(path: Path, repo: Path) -> Path:
    root = Path(os.path.abspath(repo))
    lexical = Path(os.path.abspath(path))
    try:
        relative = lexical.relative_to(root)
    except ValueError as exc:
        raise ExtractionFailure("journal-path") from exc

    current = root
    for part in relative.parts:
        current = current / part
        try:
            metadata = current.lstat()
        except OSError as exc:
            raise ExtractionFailure("journal-path") from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise ExtractionFailure("journal-path")
        if current == lexical:
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise ExtractionFailure("journal-path")
        elif not stat.S_ISDIR(metadata.st_mode):
            raise ExtractionFailure("journal-path")
    return lexical


def read_journal(path: Path) -> tuple[str, list[dict[str, Any]]]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise ExtractionFailure("journal-read") from exc
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ExtractionFailure("journal-encoding") from exc

    records: list[dict[str, Any]] = []
    for raw_line in text.splitlines():
        if not raw_line.strip():
            continue
        try:
            record = json.loads(raw_line, object_pairs_hook=reject_duplicate_keys)
        except (json.JSONDecodeError, RecursionError, ValueError) as exc:
            raise ExtractionFailure("journal-json") from exc
        if not isinstance(record, dict):
            raise ExtractionFailure("journal-record")
        records.append(record)
    if not records or records[0].get("type") != "run_started":
        raise ExtractionFailure("journal-run-id")
    run_id = records[0].get("run_id")
    if not isinstance(run_id, str) or not run_id:
        run_id = records[0].get("id")
    if not isinstance(run_id, str) or not run_id:
        raise ExtractionFailure("journal-run-id")
    return run_id, records


def git_show(repo: Path, revision: str, path: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "show", f"{revision}:{path}"],
            cwd=repo,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    try:
        return result.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None


def parse_toml_route(text: str) -> tuple[str, str] | None:
    values: dict[str, str] = {}
    for line in text.splitlines():
        match = TOML_STRING.match(line)
        if match:
            values[match.group(1)] = match.group(3)
    model = values.get("model", "")
    effort = values.get("model_reasoning_effort", "")
    return (model, effort) if model and effort else None


def parse_yaml_route(text: str) -> tuple[str, str] | None:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    values: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        match = YAML_STRING.match(line)
        if match:
            values[match.group(1)] = match.group(2).strip().strip('"\'')
    model = values.get("model", "")
    effort = values.get("effort", "")
    return (model, effort) if model and effort else None


def committed_route(repo: Path, execution: dict[str, Any]) -> tuple[str, str] | None:
    head = execution.get("head")
    provider = execution.get("provider")
    role = execution.get("role")
    if not isinstance(head, str) or COMMIT_ID.fullmatch(head) is None:
        return None

    candidates: tuple[tuple[str, str], ...]
    if provider == "codex" and role == "implementation":
        candidates = (
            (".codex/agents/implementer.toml", "toml"),
            ("system/codex/agents/implementer.toml", "toml"),
        )
    elif provider == "codex" and role == "review":
        candidates = (
            (".codex/agents/review-cheap.toml", "toml"),
            ("system/codex/agents/review-cheap.toml", "toml"),
        )
    elif provider == "claude" and role == "review":
        candidates = (("agents/review-final.md", "yaml"),)
    else:
        return None

    for path, kind in candidates:
        text = git_show(repo, head, path)
        if text is None:
            continue
        parsed = parse_toml_route(text) if kind == "toml" else parse_yaml_route(text)
        if parsed is not None:
            return parsed
    return None


def iter_diagnostics(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "diagnostic" and isinstance(child, str) and child:
                yield child
            yield from iter_diagnostics(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_diagnostics(child)


def observation_diagnostic(record: dict[str, Any]) -> str | None:
    if record.get("type") != "verification":
        return None
    observation = record.get("observation")
    if not isinstance(observation, str):
        return None
    match = OBSERVATION_DIAGNOSTIC_RE.search(observation)
    if match is None or not match.group(1):
        return None
    return match.group(1)


def standard_gate3_findings(
    record: dict[str, Any],
) -> tuple[dict[str, int], str | None] | None:
    if (
        record.get("type") != "verification"
        or record.get("criterion") != "gate-3: review-final verdict"
    ):
        return None
    observation = record.get("observation")
    if not isinstance(observation, str):
        return None
    match = GATE3_FINDINGS_RE.fullmatch(observation)
    if match is None:
        return None
    blocking = int(match.group("blocking"))
    critical = match.group("critical")
    if critical is None:
        counts = {match.group("label"): blocking} if blocking else {}
        # Legacy Gate-3 observations did not record the actual reviewer.  The
        # criterion name is not evidence of the role: standard commit reviews
        # also used review-cheap while retaining the review-final criterion.
        return counts, None
    counts = {
        "CRITICAL": int(critical),
        "MAJOR": int(match.group("major")),
        "MINOR": int(match.group("minor")),
    }
    if (
        match.group("label") != "CRITICAL/MAJOR"
        or counts["CRITICAL"] + counts["MAJOR"] != blocking
    ):
        return None
    return {key: count for key, count in counts.items() if count}, match.group("reviewer")


def record_time(record: dict[str, Any]) -> dt.datetime | None:
    raw = record.get("recorded_at", record.get("timestamp"))
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(dt.timezone.utc)


def explicit_iteration(record: dict[str, Any]) -> int:
    value = record.get("iteration")
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    observation = record.get("observation")
    if not isinstance(observation, str):
        return 0
    match = ITERATION_RE.search(observation)
    return int(match.group(1)) if match else 0


def latency_ms(records: list[dict[str, Any]]) -> int | None:
    first_failed_seen = False
    failed_at: dt.datetime | None = None
    for record in records:
        if record.get("criterion") != "gate-3: review-final verdict":
            continue
        result = record.get("result")
        if not first_failed_seen and result == "failed":
            first_failed_seen = True
            failed_at = record_time(record)
            continue
        if first_failed_seen and result == "passed":
            passed_at = record_time(record)
            if failed_at is None or passed_at is None:
                return None
            delta = passed_at - failed_at
            microseconds = (
                (delta.days * 86400 + delta.seconds) * 1_000_000
                + delta.microseconds
            )
            return microseconds // 1000 if microseconds >= 0 else None
    return None


def extract(paths: list[Path], repo: Path | str, revision: str) -> dict[str, Any]:
    repo = Path(repo)
    if not repo.is_dir():
        raise ExtractionFailure("repo")

    journals = sorted(
        (Path(path) for path in paths), key=lambda path: str(path).encode("utf-8")
    )
    ordered_paths: list[Path] = []
    seen_paths: set[str] = set()
    for path in journals:
        identity = str(path)
        if identity not in seen_paths:
            seen_paths.add(identity)
            ordered_paths.append(path)
    if not ordered_paths:
        return empty_patterns(available=True, failure="")

    outcome_counts: Counter[str] = Counter()
    diagnostic_counts: Counter[str] = Counter()
    reviewer_counts: Counter[str] = Counter()
    severity_counts: Counter[str] = Counter()
    routing: list[dict[str, Any]] = []
    verifications: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    review_execution_counts: Counter[tuple[str, str]] = Counter()
    gate3_iterations: Counter[tuple[str, str]] = Counter()
    explicit_iterations: dict[tuple[str, str], int] = defaultdict(int)

    for path in ordered_paths:
        safe_path = confined_regular_file(path, repo)
        run_id, records = read_journal(safe_path)
        for record in records:
            record_type = record.get("type")
            task = record.get("task")
            task_key = (run_id, task) if isinstance(task, str) and task else None

            if record_type == "decision":
                outcome = record.get("outcome")
                if isinstance(outcome, str) and outcome:
                    outcome_counts[outcome] += 1

            record_diagnostics = list(iter_diagnostics(record))
            for diagnostic in record_diagnostics:
                diagnostic_counts[diagnostic] += 1
            embedded_diagnostic = observation_diagnostic(record)
            if embedded_diagnostic is not None and embedded_diagnostic not in record_diagnostics:
                diagnostic_counts[embedded_diagnostic] += 1
            gate3_findings = standard_gate3_findings(record)
            observation = record.get("observation")
            if (
                record_type == "verification"
                and record.get("result") in {"failed", "inconclusive"}
                and isinstance(observation, str)
                and observation
                and (observation.startswith("forge:") or gate3_findings is not None)
                and observation not in record_diagnostics
            ):
                diagnostic_counts[observation] += 1

            if gate3_findings is not None:
                gate3_counts, gate3_reviewer = gate3_findings
                for severity, count in gate3_counts.items():
                    severity_counts[severity] += count
                if gate3_reviewer is not None:
                    reviewer_counts[gate3_reviewer] += sum(gate3_counts.values())

            if record_type == "execution":
                execution = record.get("execution")
                if not isinstance(execution, str):
                    execution = ""
                agent = record.get("agent")
                recorded_model = record.get("model")
                recorded_effort = record.get("effort")
                route = committed_route(repo, record)
                committed_model, committed_effort = route or ("", "")
                strings = (agent, recorded_model, recorded_effort)
                if route is None or not all(isinstance(item, str) and item for item in strings):
                    status = "unavailable"
                elif (
                    committed_model == recorded_model
                    and committed_effort == recorded_effort
                ):
                    status = "matched"
                else:
                    status = "mismatched"
                routing.append(
                    {
                        "agent": agent if isinstance(agent, str) else "",
                        "committed_effort": committed_effort,
                        "committed_model": committed_model,
                        "execution": execution,
                        "recorded_effort": recorded_effort if isinstance(recorded_effort, str) else "",
                        "recorded_model": recorded_model if isinstance(recorded_model, str) else "",
                        "run_id": run_id,
                        "status": status,
                    }
                )
                if task_key is not None and record.get("role") == "review":
                    review_execution_counts[task_key] += 1

            if task_key is not None:
                explicit_iterations[task_key] = max(
                    explicit_iterations[task_key], explicit_iteration(record)
                )

            if record_type == "verification" and task_key is not None:
                result = record.get("result")
                if not isinstance(result, str) or result not in VERIFICATION_RESULTS:
                    raise ExtractionFailure("verification-result")
                verifications[task_key].append(record)
                if record.get("criterion") == "gate-3: review-final verdict":
                    gate3_iterations[task_key] += 1

    task_rows: list[dict[str, Any]] = []
    for run_id, task in sorted(
        verifications, key=lambda key: (byte_key(key[0]), byte_key(key[1]))
    ):
        key = (run_id, task)
        records = verifications[key]
        results = [record["result"] for record in records]
        task_rows.append(
            {
                "block_to_pass_latency_ms": latency_ms(records),
                "iterations": max(
                    review_execution_counts[(run_id, task)],
                    gate3_iterations[key],
                    explicit_iterations[key],
                ),
                "results": results,
                "run_id": run_id,
                "task": task,
            }
        )

    routing.sort(key=lambda row: (byte_key(row["run_id"]), byte_key(row["execution"])))
    return {
        "available": True,
        "decision_outcomes": ordered_counts(outcome_counts),
        "diagnostics": [
            {"count": diagnostic_counts[value], "diagnostic": value}
            for value in sorted(diagnostic_counts, key=byte_key)
        ],
        "failure": "",
        "findings": {
            "by_reviewer_role": ordered_counts(reviewer_counts),
            "by_severity": ordered_counts(severity_counts),
        },
        "routing": routing,
        "tasks": task_rows,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--revision")
    parser.add_argument("journals", nargs="*")
    args = parser.parse_args(argv)
    try:
        patterns = extract(
            [Path(value) for value in args.journals],
            Path(args.repo),
            args.revision or "HEAD",
        )
        code = 0
    except ExtractionFailure as exc:
        patterns = empty_patterns(available=False, failure=exc.code)
        code = 2
    except (OSError, RecursionError, ValueError):
        patterns = empty_patterns(available=False, failure="extractor")
        code = 2
    sys.stdout.buffer.write(canonical_bytes(patterns))
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
