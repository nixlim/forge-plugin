#!/usr/bin/env python3
"""Persisted Forge commit-chain engine (FR-210..FR-220).

The module is deliberately import-safe.  All repository discovery, filesystem
access, subprocess execution, and argument parsing happen from ``main``.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import contextlib
import copy
import dataclasses
import datetime as dt
import errno
import functools
import fcntl  # retained: tests and tooling reach these stdlib modules through the shim namespace
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import re
import secrets
import selectors
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Callable, Collection, Iterable, Mapping, MutableMapping, Sequence

# cli split phase 1 (bead forge-plugin-95e.2): the response envelope and the committed-policy
# parser live in the interpreter-loaded forge_cli package beside this shim. Explicit named
# imports keep every historical `CLI.<name>` attribute resolvable on this module.
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from forge_cli.envelope import (  # noqa: E402
    ENVELOPE_KEYS,
    FrozenError,
    OUTPUT_SCHEMA,
    Outcome,
    REVISION9_OUTPUT_SCHEMA,
    ReasonCode,
    Refusal,
    Revision9ReasonCode,
    V2ReasonCode,
)
from forge_cli.policy import (  # noqa: E402
    Policy,
    PolicyError,
    REGION_ORDER,
    _FENCE_CLOSE_LINE,
    _FENCE_OPEN_LINE,
    _dedent_fenced_cell,
    _fence_lines,
    _fenced_shell_cells,
    _parse_changelog,
    _parse_invariants,
    _parse_regions,
    _separator,
    _split_markdown_row,
    parse_policy,
    sha256_bytes,
)
from forge_cli import runtime  # noqa: E402
from forge_cli import chain_core  # noqa: E402
from forge_cli import engine  # noqa: E402
from forge_cli import app  # noqa: E402


def __getattr__(name: str) -> Any:
    """Forward reads of moved runtime controls to the canonical module (PEP 562).

    ``CLI.utc_now`` and friends stay readable on this shim, and always reflect the live
    value on ``forge_cli.runtime``; patch them there, never here.
    """

    if name in runtime.__all__:
        return getattr(runtime, name)
    if name in chain_core.__all__:
        return getattr(chain_core, name)
    if name in engine.__all__:
        return getattr(engine, name)
    if name in app.__all__:
        return getattr(app, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# Verbs that may touch a chain past its inactivity deadline or the iteration
# cap: status, abort, and (Revision 13) the retrospective abort disposition,
# which by construction targets chains nobody has touched for a long time.
# Explicit FR-211 transition authority.  Self-transitions are operational
# no-ops (for example a repeated classification) and are admitted by
# ``_transition_state`` without appearing in this table.
# Slice 8 is the only candidate authorized to flip this switch.  Keeping the
# grammar construction immediately adjacent to the flag makes dormancy a
# mechanically testable property rather than a deployment convention.

# Lazy coordination imports preserve the phase-1 module's import-safe and
# old-face behavior.  The shared task-03 modules are imported only for a
# Revision-9 face or when replay discovers a bound chain.

# ``flock`` calls made through separately opened descriptors can deadlock a
# process against itself.  A process-local re-entrant lock makes the
# worktree-level file lock safely nest across Engine methods and ChainStore
# instances while the file lock serializes independent CLI processes.


# Test seams.  Tests may replace these module globals without touching the real
# plugin controls or the live repository.


# Detached review launcher.  It owns the child exit status and publishes one
# fsync'd atomic completion sidecar; review collection never infers success
# merely from a vanished/reused PID or a pre-existing verdict file.


# FR-223 mutation seam.  Every entry is looked up by name at finalize time, so
# a focused test can replace exactly one predicate in memory.


if __name__ == "__main__":
    raise SystemExit(app.main())
