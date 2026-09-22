#!/usr/bin/env bash
# Critique A12: prove the parallel full-set runner twice on the untouched branch before adopting it.
out=.refactor/fullset-merge-engine-baseline
{
  echo "head=$(git rev-parse HEAD)"
  for n in 1 2; do
    echo "== run $n $(date -u +%FT%TZ)"
    bash .refactor/merge-engine-full-set.sh "$out-run$n"
    echo "run $n rc=$?"
  done
} > "$out.txt" 2>&1
echo done > "$out.done"
