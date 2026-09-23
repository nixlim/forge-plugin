"""Shared route vocabulary; literal exec-stream paths must end in ``/events.jsonl``."""

from __future__ import annotations

import re

ROLE_IDS = ("implementer", "review-cheap", "review-final", "plan", "monitoring")
PROVIDER_IDS = ("codex", "claude")
EVENT_SOURCE_IDS = ("exec", "claude")
MODE_IDS = ("headless", "detached", "subagent", "teammate")
SANDBOX_IDS = ("workspace-write", "read-only", "instruction-bounded")
MODEL_ID_RE = r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}(\[1m\])?$"

_IMPLEMENTER_ALIASES = frozenset(("implementation", "implement", "implementer"))
_REVIEW_ALIASES = frozenset(("review", "reviewer"))
_NON_MUTATING_IDS = frozenset(
    ("review", "reviewer", "review-cheap", "review-final", "plan", "monitoring")
)
_MODEL_FAMILIES = ("fable", "opus", "sonnet", "haiku")
_MODEL_TOKEN_RE = re.compile(r"[._:/@+\-]+")


def canonical_role(raw_role: str, provider: str) -> str | None:
    """Return the canonical execution role for one historical spelling."""

    if not isinstance(raw_role, str) or not isinstance(provider, str):
        return None
    if raw_role in ROLE_IDS:
        return raw_role
    if raw_role in _IMPLEMENTER_ALIASES:
        return "implementer"
    if raw_role not in _REVIEW_ALIASES:
        return None
    return {"codex": "review-cheap", "claude": "review-final"}.get(
        canonical_provider(provider)
    )


def canonical_provider(raw: str) -> str | None:
    """Return the canonical launching-runtime provider."""

    if not isinstance(raw, str):
        return None
    if raw == "codex-cli":
        return "codex"
    return raw if raw in PROVIDER_IDS else None


def canonical_event_source(raw: str) -> str | None:
    """Return the canonical event transport for a historical spelling."""

    if not isinstance(raw, str):
        return None
    mapped = {"exec": "exec", "claude": "claude", "codex": "exec", "agent-tool": "claude"}
    if raw in mapped:
        return mapped[raw]
    return "exec" if raw.endswith("/events.jsonl") else None


def canonical_mode(raw: str) -> tuple[str | None, str | None]:
    """Return ``(launch_mode, legacy_sandbox)`` for a historical mode value."""

    if not isinstance(raw, str):
        return None, None
    if raw in MODE_IDS:
        return raw, None
    if raw in {"read-only", "workspace-write"}:
        return None, raw
    return None, None


def is_non_mutating(raw_role: str) -> bool:
    """Classify non-mutating work from the raw persisted role spelling."""

    return isinstance(raw_role, str) and raw_role in _NON_MUTATING_IDS


def normalize_model_id(raw: str) -> str:
    """Strip at most one host-rendered emphasis suffix from a model id."""

    return raw.removesuffix("[1m]")


def model_family(raw: str) -> str | None:
    """Recognize a Claude family alias or full Claude model identifier."""

    if not isinstance(raw, str) or re.fullmatch(MODEL_ID_RE, raw) is None:
        return None
    normalized = normalize_model_id(raw)
    if normalized in _MODEL_FAMILIES:
        return normalized
    tokens = [token for token in _MODEL_TOKEN_RE.split(normalized) if token]
    families = [
        (index, token)
        for index, token in enumerate(tokens)
        if token in _MODEL_FAMILIES
    ]
    if len(families) != 1:
        return None
    index, family = families[0]
    return family if "claude" in tokens[:index] and index + 1 < len(tokens) else None
