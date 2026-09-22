#!/usr/bin/env bash
# Runs the project's Gate 1 cell (full unittest discovery, 4 shards) as extracted from
# forge-project.md into $CELL, for lane B1 of the 2026-09-23 overnight brief (bead
# forge-plugin-25ms); usage: gate1-revision8.sh <run-label>. Run under the host-wide lock:
#   until [ "$(cut -d. -f1 /proc/loadavg)" -lt 24 ]; do sleep 120; done
#   flock /dev/shm/refactor-gate1.lock bash .refactor/gate1-revision8.sh <label>
set -u
label=${1:?label}
export TMPDIR=/dev/shm/refactor-s8 PYTHONPATH=scripts:scripts/forge
unset FORGE_SESSION_PID
mkdir -p "$TMPDIR"
awk '/^## Gate 1 Test Command/{f=1;next} /^## /{f=0} f' forge-project.md | sed -n '/^```bash/,/^```/p' | sed '1d;$d' > "$TMPDIR/gate1-cell.sh"
{
  echo "head=$(git rev-parse HEAD) start=$(date -u +%FT%TZ) load=$(cut -d' ' -f1-3 /proc/loadavg) worktree=$(git status --porcelain --untracked-files=no | wc -l) tracked changes"
  bash -c "$(cat "$TMPDIR/gate1-cell.sh")"
  echo "gate1_rc=$?"
  echo "end=$(date -u +%FT%TZ) load=$(cut -d' ' -f1-3 /proc/loadavg)"
} > ".refactor/gate1-revision8-$label.txt" 2>&1
echo done > "$TMPDIR/gate1-$label.done"
