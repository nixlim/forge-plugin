#!/usr/bin/env bash
# Gate 1 cell at an arbitrary commit in a temporary worktree (review-round evidence).
#   usage: merge-engine-gate1-at.sh <sha> <label>
set -u
sha=${1:?sha}; label=${2:?label}
export TMPDIR=/dev/shm/forge-gate PYTHONPATH=scripts:scripts/forge; unset FORGE_SESSION_PID
root=$(pwd); wt=$TMPDIR/wt-gate1-$label; rm -rf "$wt"; git worktree add -q --detach "$wt" "$sha"
awk '/^## Gate 1 Test Command/{f=1;next} /^## /{f=0} f' "$wt/forge-project.md" | sed -n '/^```bash/,/^```/p' | sed '1d;$d' > "$TMPDIR/gate1-cell-$label.sh"
( cd "$wt" && { echo "commit=$(git rev-parse HEAD) start=$(date -u +%FT%TZ)"; bash -c "$(cat "$TMPDIR/gate1-cell-$label.sh")"; echo "gate1_rc=$?"; echo "end=$(date -u +%FT%TZ)"; } ) > "$root/.refactor/gate1-merge-engine-$label.txt" 2>&1
git worktree remove --force "$wt"
echo done > "$TMPDIR/gate1-$label.done"
