#!/usr/bin/env python3
"""Fail when a Python file exceeds a code-line budget.

Counts *code* lines (blank lines and comment-only lines are ignored; docstrings
are counted because they cost agent context too).

Modes:
    check_file_length.py [--max N] [--baseline FILE] path [path ...]
        Check explicit files/dirs. Exit 1 on any violation.

    check_file_length.py --hook
        Read a Claude Code PostToolUse JSON payload on stdin, extract
        tool_input.file_path, check it. Exit 2 with a message on stderr so the
        agent sees it; exit 0 otherwise.

    check_file_length.py --write-baseline FILE path [path ...]
        Record current counts of files currently over budget so they are
        grandfathered (they may shrink but not grow).

Config precedence: --max flag > REFACTOR_MAX_LINES env > 500.
Baseline default: .refactor-baseline.json in the current directory.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "build", "dist", ".tox", ".mypy_cache", "migrations"}
DEFAULT_BASELINE = ".refactor-baseline.json"


def code_lines(path: str) -> int:
    n = 0
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            n += 1
    return n


def iter_py(paths):
    for p in paths:
        if os.path.isfile(p):
            if p.endswith(".py"):
                yield p
        elif os.path.isdir(p):
            for dirpath, dirnames, filenames in os.walk(p):
                dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
                for fn in filenames:
                    if fn.endswith(".py"):
                        yield os.path.join(dirpath, fn)


def load_baseline(path: str) -> dict[str, int]:
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return {os.path.normpath(k): v for k, v in json.load(f).items()}
    return {}


def check(files, max_lines: int, baseline: dict[str, int]):
    violations = []
    for p in files:
        n = code_lines(p)
        key = os.path.normpath(p)
        allowed = baseline.get(key)
        if allowed is not None:
            if n > allowed:
                violations.append((p, n, f"grandfathered at {allowed} code lines but grew to {n}"))
        elif n > max_lines:
            violations.append((p, n, f"{n} code lines > budget {max_lines}"))
    return violations


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--max", type=int, default=int(os.environ.get("REFACTOR_MAX_LINES", "500")))
    ap.add_argument("--baseline", default=os.environ.get("REFACTOR_BASELINE", DEFAULT_BASELINE))
    ap.add_argument("--hook", action="store_true")
    ap.add_argument("--write-baseline", metavar="FILE")
    args = ap.parse_args()

    if args.write_baseline:
        files = list(iter_py(args.paths or ["."]))
        over = {os.path.normpath(p): code_lines(p) for p in files if code_lines(p) > args.max}
        with open(args.write_baseline, "w", encoding="utf-8") as f:
            json.dump(dict(sorted(over.items())), f, indent=1)
        print(f"baseline written: {len(over)} files over {args.max} lines -> {args.write_baseline}")
        return 0

    baseline = load_baseline(args.baseline)

    if args.hook:
        try:
            payload = json.load(sys.stdin)
        except Exception:
            return 0
        fp = (payload.get("tool_input") or {}).get("file_path") or ""
        if not fp.endswith(".py") or not os.path.exists(fp):
            return 0
        # hook runs with cwd = project dir; normalise relative to it for baseline lookup
        rel = os.path.relpath(fp, os.getcwd()) if os.path.isabs(fp) else fp
        v = check([rel], args.max, baseline)
        if v:
            p, n, why = v[0]
            sys.stderr.write(
                f"FILE SIZE GUARD: {p}: {why}. Do not keep adding to this file. "
                f"Split it into a package first (see the split-module skill), then continue.\n"
            )
            return 2
        return 0

    files = list(iter_py(args.paths or ["."]))
    violations = check(files, args.max, baseline)
    for p, n, why in sorted(violations, key=lambda x: -x[1]):
        print(f"{p}: {why}")
    if violations:
        print(f"{len(violations)} file(s) violate the size budget (max {args.max}, baseline {args.baseline})")
        return 1
    print(f"ok: {len(files)} files within budget (max {args.max})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
