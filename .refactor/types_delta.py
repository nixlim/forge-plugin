"""Session helper: mypy delta of the working tree against the committed type baseline.

Errors are keyed the way the refactor-python type ratchet keys them (code + message).
"""
import json
import os
import sys
from collections import Counter

SCRIPTS = '~/foundry-of-zero/refactor-python/skills/split-module/scripts'
sys.path.insert(0, os.path.expanduser(SCRIPTS))
import type_baseline as tb  # noqa: E402

files = tuple(sys.argv[1:])
base = json.load(open('.refactor/type-baseline.json'))
allowed = Counter(base['errors'])
now, _raw = tb.run_checker('scripts/forge/forge_cli', os.getcwd())
current = Counter(tb.key(e) for e in now)
new = current - allowed
gone = allowed - current
print(
    f"baseline {base.get('ref', '')[:12]}: {sum(allowed.values())} | current: {len(now)}"
    f" | NEW: {sum(new.values())} | GONE: {sum(gone.values())}"
)
for k, n in sorted(new.items()):
    print("  NEW", n, k)
for k, n in sorted(gone.items()):
    print("  GONE", n, k)
if files:
    print("--- current errors in:", ", ".join(files))
    for e in now:
        if e['file'] in files:
            print(f"  {e['file']}:{e['line']} [{e['code']}] {e['msg'][:110]}")
