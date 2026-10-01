"""Bounded, non-secret diagnostics for retrospective ingest proof failures."""

from __future__ import annotations

import contextvars
from collections.abc import Iterator, Sequence
from pathlib import Path

INGEST_LEGIBILITY_CONTROLS = frozenset({"proof-named"})

_PROGRESS: contextvars.ContextVar[
    tuple[Sequence[str] | None, tuple[str, ...]]
] = contextvars.ContextVar(
    "forge_ingest_proof_progress", default=(None, ())
)


def record_progress(completed: Sequence[str]) -> None:
    """Remember a snapshot of the proofs entered by the current context."""

    _PROGRESS.set((completed, tuple(completed)))


def reset_progress() -> None:
    """Clear proof progress before a new ingest attempt."""

    _PROGRESS.set((None, ()))


def close_progress(completed: Sequence[str]) -> None:
    """Mark the current verifier as past its final proof predicate."""

    _PROGRESS.set((completed, ()))


def _exception_chain(exc: BaseException) -> Iterator[BaseException]:
    """Yield an exception and its effective explicit or implicit causes once."""

    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = (
            current.__cause__
            if current.__cause__ is not None
            else current.__context__
        )


def _is_bare_refusal(exc: BaseException, base: str) -> bool:
    return type(exc).__name__ == "CoordinationRefusal" and str(exc) == base


def _classify_exception(exc: BaseException) -> str:
    if type(exc).__name__ == "FrozenError":
        return "chain state invalid"
    if isinstance(exc, (UnicodeError, ValueError, RecursionError)):
        return "malformed chain bytes"
    if isinstance(exc, OSError):
        return "filesystem read failed"
    return "internal proof error"


def _observed_failure(base: str, exc: BaseException) -> str:
    for candidate in _exception_chain(exc):
        if not _is_bare_refusal(candidate, base):
            return _classify_exception(candidate)
    return "predicate not satisfied"


def _traceback_has_owner(exc: BaseException, owner: Sequence[str]) -> bool:
    for candidate in _exception_chain(exc):
        traceback = candidate.__traceback__
        while traceback is not None:
            if any(value is owner for value in traceback.tb_frame.f_locals.values()):
                return True
            traceback = traceback.tb_next
    return False


def _proof_in_progress(
    order: Sequence[str], exc: BaseException
) -> tuple[int, str] | None:
    owner, progress = _PROGRESS.get()
    has_traceback = any(
        candidate.__traceback__ is not None for candidate in _exception_chain(exc)
    )
    if owner is None or has_traceback and not _traceback_has_owner(exc, owner):
        return 0, "inputs"
    if not progress:
        return None
    name = progress[-1]
    try:
        return tuple(order).index(name) + 1, name
    except ValueError:
        return 0, "inputs"


def _missing_proof(
    order: Sequence[str], first_missing: int
) -> tuple[int, str] | None:
    if first_missing < 0 or first_missing >= len(order):
        return None
    name = order[first_missing]
    if not isinstance(name, str):
        return None
    return first_missing + 1, name


def legible_message(
    base: str,
    order: Sequence[str],
    exc: BaseException,
    *,
    first_missing: int | None = None,
) -> str:
    """Add the active proof and a closed failure class to an ingest refusal."""

    if "proof-named" not in INGEST_LEGIBILITY_CONTROLS or str(exc) != base:
        return base
    missing = None if first_missing is None else _missing_proof(order, first_missing)
    if first_missing is not None:
        if missing is None:
            return base
        number, name = missing
        observed = "predicate not satisfied"
    else:
        active = _proof_in_progress(order, exc)
        if active is None:
            return base
        number, name = active
        observed = _observed_failure(base, exc)
    return f"{base}: proof {number} {name}: {observed}"


def _scripts_site(filename: str, line: int, scripts_root: Path) -> str | None:
    try:
        root = scripts_root.resolve(strict=False)
        relative = Path(filename).resolve(strict=False).relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return None
    if not relative.parts:
        return None
    return f"scripts/{relative.as_posix()}:{line}"


def _innermost_scripts_site(
    exceptions: Sequence[BaseException], scripts_root: Path
) -> str | None:
    site = None
    for exception in exceptions:
        traceback = exception.__traceback__
        while traceback is not None:
            candidate = _scripts_site(
                traceback.tb_frame.f_code.co_filename,
                traceback.tb_lineno,
                scripts_root,
            )
            if candidate is not None:
                site = candidate
            traceback = traceback.tb_next
    return site


def verbose_observed(message: str, exc: BaseException, scripts_root: Path) -> str:
    """Render a safe verbose observation without any exception messages."""

    if "proof-named" not in INGEST_LEGIBILITY_CONTROLS:
        return message
    exceptions = tuple(_exception_chain(exc))
    parts = [message]
    site = _innermost_scripts_site(exceptions, scripts_root)
    if site is not None:
        parts.append(f"raise site {site}")
    parts.append("causes " + " <- ".join(type(item).__name__ for item in exceptions))
    return "; ".join(parts)
