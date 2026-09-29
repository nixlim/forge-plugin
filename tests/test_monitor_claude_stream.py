"""Claude stream-json coverage for the vendored execution monitor."""

# forge: modified from upstream — cover engine-launched Claude stream monitoring

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "codex_orch_tools.py"
FIXTURES = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(ROOT / "scripts"))

from codex_orchestrator import events as stream_events  # noqa: E402
from codex_orchestrator import monitor  # noqa: E402


def run_monitor(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "monitor", *args],
        check=False,
        text=True,
        capture_output=True,
        cwd=ROOT,
        timeout=5,
    )


def write_stream(path: Path, records: list[dict[str, object] | str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [record if isinstance(record, str) else json.dumps(record) for record in records]
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")


def claude_init(session_id: str = "claude-session") -> dict[str, object]:
    return {
        "type": "system",
        "subtype": "init",
        "session_id": session_id,
    }


def claude_assistant(session_id: str = "claude-session") -> dict[str, object]:
    return {
        "type": "assistant",
        "session_id": session_id,
        "message": {
            "type": "message",
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Working"},
                {
                    "type": "tool_use",
                    "id": "tool-1",
                    "name": "Read",
                    "input": {"file_path": "README.md"},
                },
            ],
        },
    }


def execution_record(
    *,
    agent: str = "claude-impl-01",
    execution: str = "execution-01",
    events: str | None = None,
    mode: str = "detached",
) -> dict[str, object]:
    record: dict[str, object] = {
        "type": "execution",
        "recorded_at": "2026-09-28T12:00:00Z",
        "task": "task-01",
        "agent": agent,
        "execution": execution,
        "provider": "claude",
        "event_source": "claude",
        "mode": mode,
    }
    if events is not None:
        record["events"] = events
    return record


def make_run(root: Path, records: list[dict[str, object]]) -> Path:
    run_dir = root / ".codex-orchestrator" / "runs" / "run-claude"
    run_dir.mkdir(parents=True)
    journal = [
        {
            "type": "run_started",
            "recorded_at": "2026-09-28T12:00:00Z",
            "run_id": "run-claude",
        },
        *records,
    ]
    write_stream(run_dir / "journal.jsonl", journal)
    return run_dir


class ClaudeStreamMonitorTests(unittest.TestCase):
    def test_auto_detects_starting_active_and_complete_claude_stream(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            write_stream(path, [claude_init()])
            starting = stream_events.summarize_stream(path)

            write_stream(path, [claude_init(), claude_assistant()])
            active = stream_events.summarize_stream(path)

            write_stream(
                path,
                [
                    claude_init(),
                    claude_assistant(),
                    {
                        "type": "system",
                        "subtype": "thinking_tokens",
                        "session_id": "claude-session",
                    },
                    {
                        "type": "user",
                        "session_id": "claude-session",
                        "message": {
                            "content": [
                                {"type": "tool_result", "tool_use_id": "tool-1"}
                            ]
                        },
                    },
                    {"type": "tool_progress", "session_id": "claude-session"},
                    {"type": "rate_limit_event", "session_id": "claude-session"},
                    {
                        "type": "result",
                        "subtype": "success",
                        "is_error": False,
                        "session_id": "claude-session",
                        "usage": {"input_tokens": 12, "output_tokens": 5},
                        "result": "done",
                    },
                ],
            )
            complete = stream_events.summarize_stream(path)
            result = run_monitor("--log", str(path), "--once")

        self.assertEqual("starting", starting.status)
        self.assertEqual("claude", starting.event_source)
        self.assertEqual("active", active.status)
        self.assertEqual("Working", active.last_agent_message)
        self.assertEqual("complete", complete.status)
        self.assertEqual(5, complete.usage["output_tokens"])
        self.assertEqual("high", stream_events.compatibility(complete)["parse_confidence"])
        self.assertEqual(set(), complete.unknown_event_types)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("codex_agent_complete", payload["type"])
        self.assertEqual("claude", payload["source"])
        self.assertEqual("claude-session", payload["thread_id"])
        self.assertEqual(5, payload["usage"]["output_tokens"])

    def test_claude_result_and_error_events_report_failure(self) -> None:
        cases = (
            (
                {
                    "type": "result",
                    "subtype": "error_during_execution",
                    "is_error": True,
                    "session_id": "claude-session",
                    "result": "result failure",
                },
                "error",
                "result failure",
            ),
            (
                {
                    "type": "error",
                    "session_id": "claude-session",
                    "message": "stream failure",
                },
                "message",
                "stream failure",
            ),
        )
        for terminal, field, expected in cases:
            with self.subTest(terminal=terminal["type"]), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "events.jsonl"
                write_stream(path, [claude_init(), claude_assistant(), terminal])
                result = run_monitor(
                    "--log",
                    str(path),
                    "--once",
                    "--fail-on-agent-failure",
                )

            self.assertEqual(result.returncode, 1, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual("codex_agent_failed", payload["type"])
            self.assertEqual("claude", payload["source"])
            self.assertEqual(expected, payload[field])

    def test_unparseable_and_unrecognised_claude_content_is_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            relative = "claude-impl-01/execution-01/events.jsonl"
            run_dir = make_run(root, [execution_record(events=relative)])
            write_stream(
                run_dir / relative,
                [claude_init(), "not json", {"type": "future.claude.event"}],
            )
            result = run_monitor(
                "--repo",
                str(root),
                "--run-id",
                "run-claude",
                "--once",
            )

        self.assertEqual(result.returncode, 2, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("codex_agent_unknown", payload["type"])
        self.assertEqual("claude", payload["source"])
        self.assertEqual(1, payload["parse_errors"])
        self.assertEqual("low", payload["compatibility"]["parse_confidence"])
        self.assertEqual(
            ["<invalid-json>", "future.claude.event"],
            payload["compatibility"]["unknown_event_types"],
        )

    def test_auto_detection_defers_undecidable_leading_claude_records(self) -> None:
        cases: tuple[dict[str, object] | str, ...] = (
            "not json",
            {"type": "future.claude.event"},
        )
        for leading in cases:
            with self.subTest(leading=leading), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "events.jsonl"
                write_stream(
                    path,
                    [
                        leading,
                        claude_init(),
                        {
                            "type": "result",
                            "is_error": False,
                            "session_id": "claude-session",
                        },
                    ],
                )
                summary = stream_events.summarize_stream(path)
                result = run_monitor("--log", str(path), "--once")

            self.assertEqual("complete", summary.status)
            self.assertEqual("claude", summary.event_source)
            self.assertEqual(
                "high", stream_events.compatibility(summary)["parse_confidence"]
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual("codex_agent_complete", payload["type"])
            self.assertEqual("claude", payload["source"])

    def test_unchanged_claude_stream_uses_mtime_staleness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            write_stream(path, [claude_init(), claude_assistant()])
            old = time.time() - 20
            os.utime(path, (old, old))
            result = run_monitor(
                "--log",
                str(path),
                "--once",
                "--stale-seconds",
                "1",
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("codex_agent_stale", payload["type"])
        self.assertEqual("claude", payload["source"])
        self.assertGreaterEqual(payload["idle_seconds"], 1)

    def test_selects_claude_with_events_and_skips_subagent_without_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            relative = "claude-impl-01/execution-01/events.jsonl"
            records = [
                execution_record(events=relative),
                execution_record(
                    agent="claude-plan-01",
                    execution="execution-02",
                    mode="subagent",
                ),
            ]
            run_dir = make_run(root, records)
            write_stream(
                run_dir / relative,
                [
                    claude_init(),
                    {
                        "type": "result",
                        "is_error": False,
                        "session_id": "claude-session",
                    },
                ],
            )
            targets, errors = monitor.inflight_targets(run_dir)

        self.assertEqual([], errors)
        self.assertEqual(1, len(targets))
        self.assertEqual("claude-impl-01", targets[0].agent)
        self.assertEqual("claude", targets[0].event_source)

    def test_claude_parser_control_is_load_bearing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            write_stream(
                path,
                [claude_init(), {"type": "result", "is_error": False}],
            )
            intact = stream_events.summarize_stream(path, event_source="claude")
            with mock.patch.object(stream_events, "CLAUDE_EVENT_TYPES", set()):
                disabled = stream_events.summarize_stream(path, event_source="claude")

        self.assertEqual("complete", intact.status)
        self.assertNotEqual("complete", disabled.status)
        self.assertEqual("low", stream_events.compatibility(disabled)["parse_confidence"])

    def test_claude_selection_control_is_load_bearing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            relative = "claude-impl-01/execution-01/events.jsonl"
            run_dir = make_run(root, [execution_record(events=relative)])
            write_stream(run_dir / relative, [claude_init()])
            intact, intact_errors = monitor.inflight_targets(run_dir)
            with mock.patch.object(
                monitor,
                "MONITORED_EVENT_SOURCES",
                frozenset({"exec"}),
            ):
                disabled, disabled_errors = monitor.inflight_targets(run_dir)

        self.assertEqual(1, len(intact))
        self.assertEqual([], intact_errors)
        self.assertEqual([], disabled)
        self.assertEqual(1, len(disabled_errors))
        self.assertIn("unsupported event source", disabled_errors[0]["message"])

    def test_codex_summary_and_monitor_payload_are_unchanged(self) -> None:
        path = FIXTURES / "exec_stream.jsonl"
        summary = stream_events.summarize_stream(path)
        result = run_monitor("--log", str(path), "--once")

        self.assertEqual("exec", summary.event_source)
        self.assertEqual("complete", summary.status)
        self.assertEqual("exec-complete-001", summary.thread_id)
        self.assertEqual("Implemented the scoped change.", summary.last_agent_message)
        self.assertEqual({"input_tokens": 120, "output_tokens": 45}, summary.usage)
        self.assertEqual(6, summary.known_count)
        self.assertEqual(set(), summary.unknown_event_types)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("codex_agent_complete", payload["type"])
        self.assertEqual("exec", payload["source"])
        self.assertEqual("exec-complete-001", payload["thread_id"])
        self.assertEqual(45, payload["usage"]["output_tokens"])


if __name__ == "__main__":
    unittest.main()
