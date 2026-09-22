#!/usr/bin/env bash
# Runs the project's Gate 1 cell (full unittest discovery, 4 shards) as extracted from
# forge-project.md into $CELL; usage: merge-engine-gate1.sh <run-label>
set -u
label=${1:?label}
export TMPDIR=/dev/shm/forge-gate PYTHONPATH=scripts:scripts/forge
unset FORGE_SESSION_PID
awk '/^## Gate 1 Test Command/{f=1;next} /^## /{f=0} f' forge-project.md | sed -n '/^```bash/,/^```/p' | sed '1d;$d' > "$TMPDIR/gate1-cell.sh"
{
  echo "head=$(git rev-parse HEAD) start=$(date -u +%FT%TZ) worktree=$(git status --porcelain --untracked-files=no | wc -l) tracked changes"
  bash -c "$(cat "$TMPDIR/gate1-cell.sh")"
  echo "gate1_rc=$?"
  echo "end=$(date -u +%FT%TZ)"
} > ".refactor/gate1-merge-engine-$label.txt" 2>&1
echo done > "$TMPDIR/gate1-$label.done"
