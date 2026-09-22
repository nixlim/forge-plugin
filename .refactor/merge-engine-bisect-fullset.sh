#!/usr/bin/env bash
# Codex B3 remedy: the operator's bisect rule literally, the FULL parallel set at each of the five
# tier-2 commits before e05 (sequential worktrees; per-module rc and OK lines recorded).
set -u
root=$(pwd); export TMPDIR=/dev/shm/forge-gate; unset FORGE_SESSION_PID
out=$root/.refactor/bisect-merge-engine-t2-e05-fullset; mkdir -p "$out"
{ echo "e05 full-set bisect $(date -u +%FT%TZ): bash .refactor/merge-engine-full-set.sh at each commit, in a detached worktree"
  for sha in 6e60498 c81829d 034df09 913f275 05288f0; do
    w=$TMPDIR/wt-fs-$sha; rm -rf "$w"; git worktree add -q --detach "$w" "$sha"
    ( cd "$w" && PYTHONPATH=scripts:scripts/forge bash .refactor/merge-engine-full-set.sh "$out/$sha" > "$out/$sha.txt" 2>&1; echo "$sha $(git log -1 --format=%s "$sha" | cut -c1-60): rc=$? $(grep 'full set:' "$out/$sha.txt")" )
    git worktree remove --force "$w"
  done; } > "$out.txt" 2>&1
echo done > "$TMPDIR/bisect-fullset.done"
