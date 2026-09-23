#!/usr/bin/env bash
# Pre-check after c00 (plan section 6 "Preferred"): dry-run every family at the current head with the driver's argv,
# measure the destination hunk's code lines against its provisional baseline entry, and check the header order.
# Writes nothing to tests/; evidence: .refactor/precheck-revision9-coord-<family>.txt and -summary.txt.
set -u
export TMPDIR=/dev/shm/refactor-s4 PYTHONPATH=scripts:scripts/forge
D=/home/agents/foundry-of-zero/refactor-python/skills/decompose/scripts
S=/home/agents/foundry-of-zero/refactor-python/skills/split-module/scripts
R=.refactor; SRC=tests/test_revision9_coordination.py; CLASS=Revision9BuilderBatchTests
ids=$R/tests-revision9-coord-precheck.json
python3 "$D/collect_tests.py" snapshot --start tests --out "$ids" || exit 1
summary=$R/precheck-revision9-coord-summary.txt
echo "precheck at head=$(git rev-parse --short HEAD) $(date -u +%FT%TZ)" > "$summary"
for label in $(python3 -c 'import json;print(" ".join(json.load(open(".refactor/families-revision9-coord.json"))["order"]))'); do
  fam=${label#*-}
  read -r dest cls methods < <(python3 -c "
import json; f=json.load(open('.refactor/families-revision9-coord.json'))['families']['$fam']; print(f['module'], f['class'], f['methods_csv'])")
  idmap=$R/precheck-idmap-revision9-coord-$fam.json
  python3 "$R/revision9-coord-idmap.py" "$ids" "$(basename "$dest" .py)" "$cls" "$idmap" "$methods" >/dev/null || { echo "$label: FAIL id map" | tee -a "$summary"; continue; }
  out=$R/precheck-revision9-coord-$fam.txt
  python3 "$D/move_methods.py" --project . --import-root "$PWD" --source "$SRC" --class "$CLASS" --methods "$methods" --dest "$dest" --shape class --target-class "$cls" --test-only --test-snapshot "$ids" --id-map "$idmap" --format-imports --manifest "$R/precheck-manifest-revision9-coord-$fam.json" > "$out" 2>&1
  rc=$?
  lines=$(awk -v d="+++ $dest" '$0==d{f=1;next} f && /^\+/{l=substr($0,2); if (l !~ /^[[:space:]]*$/ && l !~ /^[[:space:]]*#/) n++} END{print n+0}' "$out")
  prov=$(python3 -c "import json;print(json.load(open('.refactor-baseline.json')).get('$dest','none'))")
  order=$(grep -n "^+from tests._revision9_coord_constants\|^+from tests._revision9_coord_support\|^+from codex_orchestrator\|^+import codex_orch_tools\|^+from forge_cli\|^+from tests._cli_loader" "$out" | sed 's/:+/ /' | tr '\n' ';')
  echo "$label rc=$rc $(tail -1 "$out" | cut -c1-60) | dest code lines=$lines provisional=$prov | header: $order" | tee -a "$summary"
done
