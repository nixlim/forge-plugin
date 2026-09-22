#!/usr/bin/env bash
# Full focused merge set, run as parallel unittest processes (operator decision 2026-09-22,
# bead forge-plugin-37fr). Fail-closed: every module must exit 0 AND print a final "OK" line.
#   usage: merge-engine-full-set.sh <log-dir>
set -u
dir=${1:?log dir}
mkdir -p "$dir"
unset FORGE_SESSION_PID
export TMPDIR=${TMPDIR:-/dev/shm/forge-gate}
mods="tests.test_cli_merge_integration tests.test_cli_merge_integration_shard1
tests.test_cli_merge_integration_shard2 tests.test_cli_merge_lifecycle
tests.test_cli_merge_adapters tests.test_cli_merge_store tests.test_cli_loader"
start=$(date +%s)
# shellcheck disable=SC2086
printf '%s\n' $mods | xargs -P 4 -I{} bash -c '
  python3 -m unittest "$1" > "$0/$1.txt" 2>&1; rc=$?
  echo "$1 rc=$rc $(grep -E "^Ran " "$0/$1.txt" | tail -1)"; exit $rc' "$dir" {}
xargs_rc=$?
ok=0
for m in $mods; do
  log="$dir/$m.txt"
  if [ -f "$log" ] && grep -qE '^Ran [0-9]+ tests?' "$log" && tail -1 "$log" | grep -qx 'OK'; then
    ok=$((ok + 1))
  else
    echo "FULL-SET FAIL: $m (see $log)"
  fi
done
echo "full set: $ok/7 modules OK, xargs rc=$xargs_rc, wall=$(( $(date +%s) - start ))s"
[ "$xargs_rc" -eq 0 ] && [ "$ok" -eq 7 ]
