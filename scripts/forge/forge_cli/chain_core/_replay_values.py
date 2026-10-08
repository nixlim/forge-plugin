"""Authenticate replay values; no journal or run authority."""

from __future__ import annotations

import datetime as dt
from typing import Any

from ._state import SHA256_RE


def _merge_hex(value: Any) -> bool:
    return bool(isinstance(value, str) and SHA256_RE.fullmatch(value) is not None)


def _utc_value(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        result = dt.datetime.fromisoformat(value[:-1] + "+00:00")
        return result if result.tzinfo is not None else None
    except ValueError:
        return None
