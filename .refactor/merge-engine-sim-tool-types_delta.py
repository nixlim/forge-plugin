"""Sim helper: print NEW and GONE mypy keys vs .refactor/type-baseline.json using the \
plugin's own key logic."""

import json
import os
import sys
from collections import Counter

sys.path.insert(0, "/home/agents/foundry-of-zero/refactor-python/skills/split-module/scripts")
import type_baseline as tb

label = sys.argv[1]
base = json.load(open(".refactor/type-baseline.json"))
allowed = Counter(base["errors"])
now, _ = tb.run_checker("scripts/forge/forge_cli", os.getcwd())
cur = Counter(tb.key(e) for e in now)
new, gone = cur - allowed, allowed - cur
print(
    f"== {label}: total={len(now)} baseline={base['total']} NEW={sum(new.values())} \
GONE={sum(gone.values())}"
)
locs = {}
for e in now:
    locs.setdefault(tb.key(e), []).append(f"{e['file']}:{e['line']}")
for k, n in sorted(new.items()):
    print(f"  NEW  x{n} {k} at {', '.join(locs.get(k, [])[:5])}")
for k, n in sorted(gone.items()):
    print(f"  GONE x{n} {k} (baseline example {base.get('examples', {}).get(k)})")
