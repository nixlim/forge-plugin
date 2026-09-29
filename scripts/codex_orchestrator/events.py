from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

PARSER_VERSION = "0.1.0"

# forge: modified from upstream — summarize engine-launched Claude stream-json
CLAUDE_EVENT_TYPES = {
    "assistant",
    "error",
    "rate_limit_event",
    "result",
    "system",
    "tool_progress",
    "user",
}

EXEC_EVENT_TYPES = {
    "thread.started",
    "turn.started",
    "turn.completed",
    "turn.failed",
    "item.started",
    "item.updated",
    "item.completed",
    "error",
}


@dataclass(frozen=True)
class EventRecord:
    event: dict[str, object]
    event_type: str


@dataclass
class StreamSummary:
    status: str = "idle"
    event_counts: Counter[str] = field(default_factory=Counter)
    known_count: int = 0
    parse_errors: int = 0
    unknown_event_types: set[str] = field(default_factory=set)
    thread_id: str | None = None
    usage: object = None
    error: object = None
    last_agent_message: str = ""
    terminal: EventRecord | None = None
    event_source: str = "exec"

    @property
    def event_count(self) -> int:
        return self.event_counts.total()

    def consume(self, record: EventRecord) -> None:
        kind = record.event_type
        self.event_counts[kind] += 1
        if kind in {"<invalid-json>", "<non-object>"}:
            self.parse_errors += 1
        if kind in EXEC_EVENT_TYPES or is_reconnect_notice(record):
            self.known_count += 1
        else:
            self.unknown_event_types.add(kind)
        if self.status == "idle" and (
            kind in EXEC_EVENT_TYPES or is_reconnect_notice(record)
        ):
            self.status = "starting"

        event = record.event
        if kind == "thread.started":
            native_id = event.get("thread_id")
            if isinstance(native_id, str) and native_id:
                self.thread_id = native_id
            self.status = "starting"
            self.usage = None
            self.error = None
            self.last_agent_message = ""
            self.terminal = None
        elif kind == "turn.started":
            self.status = "active"
            self.usage = None
            self.error = None
            self.terminal = None
        elif kind == "turn.completed":
            self.status = "complete"
            self.usage = event.get("usage")
            self.error = None
            self.terminal = record
        elif kind == "turn.failed":
            self.status = "failed"
            self.usage = None
            self.error = event.get("error")
            self.terminal = record
        elif kind == "error" and not is_reconnect_notice(record):
            self.status = "failed"
            self.usage = None
            self.error = event.get("error") or event.get("message")
            self.terminal = record
        elif kind == "item.completed":
            item = event.get("item")
            if isinstance(item, dict) and item.get("type") == "agent_message":
                text = item.get("text")
                if isinstance(text, str):
                    self.last_agent_message = text

    # forge: modified from upstream — map Claude stream-json onto upstream states
    def consume_claude(self, record: EventRecord) -> None:
        kind = record.event_type
        self.event_counts[kind] += 1
        if kind in {"<invalid-json>", "<non-object>"}:
            self.parse_errors += 1
        if kind in CLAUDE_EVENT_TYPES:
            self.known_count += 1
        else:
            self.unknown_event_types.add(kind)
            return
        if self.status == "idle":
            self.status = "starting"

        event = record.event
        native_id = event.get("session_id")
        if isinstance(native_id, str) and native_id:
            self.thread_id = native_id
        if kind == "system" and event.get("subtype") == "init":
            self.status = "starting"
            self.usage = None
            self.error = None
            self.last_agent_message = ""
            self.terminal = None
        elif kind == "assistant":
            self.status = "active"
            self.usage = None
            self.error = None
            self.terminal = None
            text = claude_message_text(event)
            if text:
                self.last_agent_message = text
        elif kind == "result" and event.get("is_error") is False:
            self.status = "complete"
            self.usage = event.get("usage")
            self.error = None
            self.terminal = record
        elif kind == "result" and event.get("is_error") is True:
            self.status = "failed"
            self.usage = event.get("usage")
            self.error = claude_result_error(event)
            self.terminal = record
        elif kind == "error":
            self.status = "failed"
            self.usage = None
            self.error = event.get("error") or event.get("message")
            self.terminal = record

    def details(self) -> dict[str, object]:
        details: dict[str, object] = {}
        if self.usage is not None:
            details["usage"] = self.usage
        if self.error is not None:
            details["error"] = self.error
        if self.thread_id is not None:
            details["thread_id"] = self.thread_id
        if self.last_agent_message:
            details["last_agent_message"] = self.last_agent_message
        return details


def json_dumps(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def event_type(event: dict[str, object]) -> str:
    value = event.get("type")
    return value if isinstance(value, str) else "<missing>"


def claude_message_text(event: dict[str, object]) -> str:
    message = event.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if not isinstance(content, list):
        return ""
    parts = [
        block.get("text")
        for block in content
        if isinstance(block, dict)
        and block.get("type") == "text"
        and isinstance(block.get("text"), str)
    ]
    return "".join(parts)


def claude_result_error(event: dict[str, object]) -> object:
    for key in ("error", "errors", "result"):
        value = event.get(key)
        if value is not None:
            return value
    return event.get("subtype")


def detected_event_source(record: EventRecord) -> str | None:
    if record.event_type in CLAUDE_EVENT_TYPES - {"error"}:
        return "claude"
    if record.event_type == "error" and "session_id" in record.event:
        return "claude"
    if record.event_type in EXEC_EVENT_TYPES:
        return "exec"
    return None


def decode_event_line(line: str) -> EventRecord | None:
    stripped = line.strip()
    if not stripped:
        return None
    try:
        event = json.loads(stripped)
    except json.JSONDecodeError:
        return EventRecord({"_parse_error": stripped[:200]}, "<invalid-json>")
    if not isinstance(event, dict):
        return EventRecord(
            {"_parse_error": "top-level JSON value is not an object"}, "<non-object>"
        )
    return EventRecord(event, event_type(event))


def is_reconnect_notice(record: EventRecord) -> bool:
    if record.event_type != "error":
        return False
    return "reconnecting" in json_dumps(record.event).lower()


def summarize_stream(path: Path, *, event_source: str | None = None) -> StreamSummary:
    if event_source not in {None, "exec", "claude"}:
        raise ValueError(f"unsupported event source: {event_source}")
    summary = StreamSummary(event_source=event_source or "exec")
    detected = event_source
    with path.open("rb") as handle:
        while True:
            raw_line = handle.readline()
            if raw_line == b"":
                break
            terminated = raw_line.endswith(b"\n")
            try:
                line = raw_line.decode("utf-8")
            except UnicodeDecodeError:
                if not terminated:
                    if summary.status == "idle":
                        summary.status = "starting"
                    break
                summary.consume(
                    EventRecord({"_parse_error": "invalid UTF-8"}, "<invalid-json>")
                )
                continue
            record = decode_event_line(line)
            if record is None:
                continue
            if not terminated and record.event_type == "<invalid-json>":
                if summary.status == "idle":
                    summary.status = "starting"
                break
            if detected is None:
                detected = detected_event_source(record)
                if detected is None:
                    summary.consume(record)
                    continue
                summary.event_source = detected
            if detected == "claude":
                summary.consume_claude(record)
            else:
                summary.consume(record)
    return summary


def compatibility(summary: StreamSummary) -> dict[str, object]:
    warnings = [] if summary.event_count else ["no events found"]
    unknown_count = summary.event_count - summary.known_count
    confidence = (
        "low"
        if summary.event_count and unknown_count > summary.known_count
        else "high"
    )
    return {
        "parser_version": PARSER_VERSION,
        "parse_confidence": confidence,
        "unknown_event_types": sorted(summary.unknown_event_types),
        "warnings": warnings,
    }


def incompatible_message() -> str:
    return (
        f"ERROR: Codex exec JSONL appears incompatible (parser {PARSER_VERSION}). "
        "Run state --dump-event-types and update the parser. Do not infer agent status."
    )


def event_text(event: dict[str, object]) -> str:
    for key in ("message", "text", "error"):
        value = event.get(key)
        if isinstance(value, str):
            return value
    return json_dumps(event)
