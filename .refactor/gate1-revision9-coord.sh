#!/usr/bin/env bash
# Runs the project's Gate 1 cell (full unittest discovery, 4 shards) as extracted from
# forge-project.md into $CELL; usage: gate1-revision9-coord.sh <run-label>
set -u
label=${1:?label}
export TMPDIR=/dev/shm/refactor-s4
# No PYTHONPATH: CI (.github/workflows/forge-ci.yml) and the main-clone merge chain run the cell without it,
# so this script must prove the family modules bootstrap scripts/ on their own (critique B1, ruling 11:30).
unset FORGE_SESSION_PID PYTHONPATH MYPYPATH
awk '/^## Gate 1 Test Command/{f=1;next} /^## /{f=0} f' forge-project.md | sed -n '/^```bash/,/^```/p' | sed '1d;$d' > "$TMPDIR/gate1-cell.sh"
{
  echo "head=$(git rev-parse HEAD) start=$(date -u +%FT%TZ) worktree=$(git status --porcelain --untracked-files=no | wc -l) tracked changes"
  bash -c "$(cat "$TMPDIR/gate1-cell.sh")"
  echo "gate1_rc=$?"
  echo "end=$(date -u +%FT%TZ)"
} > ".refactor/gate1-revision9-coord-$label.txt" 2>&1
echo done > "$TMPDIR/gate1-$label.done"
