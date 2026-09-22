"""Wave close: add the 27 app/_engine_*.py modules to the FR-230 production subjects."""
import glob
import json
import os
import sys

path = sys.argv[1]
raw = open(path, encoding="utf-8").read()
m = json.loads(raw)
prod = m["subjects"]["production"]
new = sorted(glob.glob("scripts/forge/forge_cli/app/_engine_*.py"))
assert len(new) == 27, new
app = [p for p in prod if p.startswith("scripts/forge/forge_cli/app/")]
assert app == sorted(app), "app block is not sorted; inspect before editing"
merged = sorted(set(app) | set(new))
first = prod.index(app[0])
prod[first : first + len(app)] = merged
assert len(prod) == len(set(prod)), "duplicate subject"
assert all(os.path.exists(p) for p in merged)
text = json.dumps(m, ensure_ascii=False, indent=2) + "\n"
if len(sys.argv) > 2 and sys.argv[2] == "--write":
    open(path, "w", encoding="utf-8").write(text)
    print("written", path)
else:
    import difflib

    for line in difflib.unified_diff(raw.splitlines(), text.splitlines(), lineterm="", n=0):
        print(line)
