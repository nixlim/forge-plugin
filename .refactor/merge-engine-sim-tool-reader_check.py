"""For every name the mover pruned from _merge_engine.py (union of all sim manifests' \
remove_imports), look for
readers/patchers that reach it THROUGH the module path forge_cli.app._merge_engine. Run \
from the sim root.

A through-module reader is one of:
  - attribute access on the module object:   _merge_engine.<name>
  - import of the name from the module:      from <...>._merge_engine import ... <name> ...
  - a dotted string path (mock.patch target): "forge_cli.app._merge_engine.<name>"
  - getattr/setattr/patch.object on an object obtained from the _merge_engine module path
patch_app/patch_engine/patch_chain_core sites never mention _merge_engine and patch by \
pkgutil enumeration, so
they cannot match any of these patterns; they are counted separately, only to show they \
exist and are excluded."""

import glob
import json
import re
import subprocess

names = set()
per_cluster = {}
for path in sorted(glob.glob(".refactor/merge-engine-*.json")):
    try:
        m = json.load(open(path))
    except Exception:
        continue
    if not isinstance(m, dict) or "operations" not in m:
        continue
    for op in m["operations"]:
        for _src, removed in (op.get("remove_imports") or {}).items():
            per_cluster[path] = removed
            names.update(removed)

files = subprocess.run(
    ["git", "ls-files", "*.py", "*.sh", "*.md", "*.json", "*.toml", "*.yml", "*.yaml"],
    capture_output=True,
    text=True,
).stdout.split()
skip = (".refactor/", ".forge/history/", "docs/analysis/", "CHANGELOG.md", ".codex-orchestrator/")
files = [
    f
    for f in files
    if not f.startswith(skip) and f != "scripts/forge/forge_cli/app/_merge_engine.py"
]

module_mentions = []
for f in files:
    try:
        text = open(f, encoding="utf-8", errors="replace").read()
    except OSError:
        continue
    for i, line in enumerate(text.split("\n"), 1):
        if "_merge_engine" in line:
            module_mentions.append((f, i, line.strip()[:160]))

print(f"pruned names (union over {len(per_cluster)} manifests with removals): {len(names)}")
print(sorted(names))
print(
    f"\nlines mentioning the module path `_merge_engine` outside the module itself: \
{len(module_mentions)}"
)
through = []
for f, i, line in module_mentions:
    hit = [
        n for n in names if re.search(rf"_merge_engine(\.|\s+import\s.*\b){re.escape(n)}\b", line)
    ]
    kind = "THROUGH-MODULE READER" if hit else "not a reader of a pruned name"
    if hit:
        through.append((f, i, hit))
    print(f"  {f}:{i}: {line}  -> {kind} {hit or ''}")

helper_sites = 0
for f in files:
    if f.startswith("tests/") and f.endswith(".py"):
        text = open(f, encoding="utf-8", errors="replace").read()
        for n in names:
            helper_sites += len(
                re.findall(rf"patch_(?:app|engine|chain_core)\(\s*['\"]{re.escape(n)}['\"]", text)
            )
print(
    f"\npatch_app/patch_engine/patch_chain_core sites naming a pruned name (EXCLUDED: \
package-root + pkgutil patching, "
    f"never through _merge_engine): {helper_sites}"
)
print(
    f"\nRESULT: through-module readers of pruned names = {len(through)} -> "
    f"{'no cluster needs --retain-module-api' if not through else 'RETAIN NEEDED: ' + str(through)}"
)
