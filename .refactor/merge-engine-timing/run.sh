#!/usr/bin/env bash
# Times each focused merge test module separately, all in parallel (session 2 start checklist).
out=.refactor/merge-engine-timing
for m in test_cli_merge_adapters test_cli_merge_store test_cli_merge_lifecycle \
  test_cli_merge_integration test_cli_merge_integration_shard1 \
  test_cli_merge_integration_shard2 test_cli_loader; do
  (
    s=$(date +%s)
    env -u FORGE_SESSION_PID python3 -m unittest "tests.$m" > "$out/$m.txt" 2>&1
    rc=$?
    e=$(date +%s)
    echo "$m rc=$rc wall=$((e - s))s $(grep -E '^Ran ' "$out/$m.txt")" >> "$out/summary.txt"
  ) &
done
wait
echo ALLDONE >> "$out/summary.txt"
