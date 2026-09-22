#!/usr/bin/env bash
# Wave close (bead forge-plugin-37fr): re-run the manifest oracle for every committed cluster at
# its own commit, in a temporary worktree, against the snapshot taken before that cluster.
set -u
S="$HOME/foundry-of-zero/refactor-python/skills/split-module/scripts"
root=$(pwd)
wt=/dev/shm/forge-gate/merge-engine-wave-verify
fail=0
python3 - <<'PY' > /dev/shm/forge-gate/merge-engine-wave-clusters.txt
import json
for c in json.load(open(".refactor/merge-engine-sim-clusters.json"))["clusters"]:
    print(c["id"], c["name"])
PY
while read -r cid name; do
  sha=$(git log --format=%H --grep="^refactor(app): move $name methods to " -n 1)
  [ -n "$sha" ] || { echo "$cid $name: no commit found"; fail=1; continue; }
  rm -rf "$wt"; git worktree add -q --detach "$wt" "$sha" || { echo "$cid: worktree failed"; fail=1; continue; }
  out=$(cd "$wt" && python3 "$S/snapshot_bodies.py" compare \
      "$root/.refactor/merge-engine-$cid-before.json" scripts/forge/forge_cli \
      --manifest "$root/.refactor/merge-engine-$name.json" --strict 2>&1 | tail -1)
  rc=$?
  echo "$cid $name @ ${sha:0:7}: $out"
  git worktree remove --force "$wt"
  echo "$out" | grep -q "PASS" || fail=1
done < /dev/shm/forge-gate/merge-engine-wave-clusters.txt
echo "wave verify: $([ $fail -eq 0 ] && echo ALL PASS || echo FAILED)"
exit $fail
