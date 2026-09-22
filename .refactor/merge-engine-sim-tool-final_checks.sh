#!/usr/bin/env bash
# End-of-sim checks on the final sim tree (throwaway clone only). Writes .refactor/merge-engine-sim-final.txt
set -u
D=/home/agents/foundry-of-zero/refactor-python/skills/decompose/scripts
S=/home/agents/foundry-of-zero/refactor-python/skills/split-module/scripts
T=$(cd "$(dirname "$0")" && pwd)
export PYTHONPATH=scripts:scripts/forge MYPYPATH=scripts:scripts/forge TMPDIR=/dev/shm/forge-gate PATH="$HOME/.local/bin:$PATH"
unset FORGE_SESSION_PID REFACTOR_TYPE_CMD
OUT=.refactor/merge-engine-sim-final.txt
{
echo "# final sim tree: $(git rev-parse --short HEAD) ($(git log --oneline | grep -c '\[sim c') cluster commits on P0,P1,P2,P0b over d885f97)"
echo; echo "## ruff check scripts/forge/forge_cli (glob WITH UP037 in place)"
ruff check scripts/forge/forge_cli; echo "[exit $?]"
echo; echo "## check_file_length over the app package (provisional entries in .refactor-baseline.json)"
python3 scripts/check_file_length.py scripts/forge/forge_cli/app; echo "[exit $?]"
echo; echo "## code lines per app module (check_file_length semantics)"
python3 - <<'PY'
import glob
for p in sorted(glob.glob("scripts/forge/forge_cli/app/*.py")):
    n = sum(1 for l in open(p, encoding="utf-8") if l.strip() and not l.strip().startswith("#"))
    flag = "  OVER 1000 (REJECT)" if n > 1000 else "  over 500 (baseline entry + debt row)" if n > 500 else ""
    print(f"{n:6d}  {p}{flag}")
PY
echo; echo "## lint-imports (contract unchanged)"
lint-imports 2>&1 | tail -15; echo "[exit ${PIPESTATUS[0]}]"
echo; echo "## type check vs the P1 baseline (234)"
python3 "$S/type_baseline.py" check --pkg scripts/forge/forge_cli; echo "[exit $?]"
python3 "$T/types_delta.py" "final tree"
echo; echo "## per-module ruff codes with the P0 glob DISABLED (finalize per-file-ignores table)"
cp pyproject.toml "$T/pyproject.keep"
python3 - <<'PY'
import re, pathlib
p = pathlib.Path("pyproject.toml"); t = p.read_text()
t2 = re.sub(r'^"scripts/forge/forge_cli/app/_engine_\*\.py" = \[.*\]\n', "", t, flags=re.M)
assert t2 != t
p.write_text(t2)
PY
ruff check scripts/forge/forge_cli/app --output-format json > "$T/ruff-noglob.json"; echo "[ruff exit $? with glob removed]"
cp "$T/pyproject.keep" pyproject.toml; git diff --quiet -- pyproject.toml && echo "[pyproject.toml restored, tree clean]"
python3 - "$T/ruff-noglob.json" <<'PY'
import json, sys, collections, os
d = json.load(open(sys.argv[1]))
per = collections.defaultdict(collections.Counter)
for x in d:
    per[os.path.basename(x["filename"])][x["code"]] += 1
for f in sorted(per):
    print(f'  {f}: {sorted(per[f])}   counts={dict(sorted(per[f].items()))}')
union = sorted({c for f in per if f.startswith("_engine_") for c in per[f]})
print("  UNION over _engine_*.py:", union)
PY
echo; echo "## quality.py over the app package"
python3 "$D/quality.py" scripts/forge/forge_cli/app/*.py > "$T/quality.json" 2>&1; echo "[exit $?]"
python3 - "$T/quality.json" <<'PY'
import json, sys
raw = open(sys.argv[1]).read()
try:
    q = json.loads(raw)
except Exception:
    print(raw[:3000]); raise SystemExit
print(json.dumps(q, indent=1)[:200] if not isinstance(q, (dict, list)) else "")
items = q.get("files", q) if isinstance(q, dict) else q
print(raw[:6000])
PY
echo; echo "## census + structure probes"
python3 "$T/probes.py"; echo "[exit $?]"
echo; echo "## through-module reader check for pruned imports"
python3 "$T/reader_check.py"; echo "[exit $?]"
} > "$OUT" 2>&1
echo "wrote $OUT"; wc -l "$OUT"
