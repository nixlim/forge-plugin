#!/usr/bin/env bash
# Gate for the type-only prep commit (bead forge-plugin-37fr): verify.sh with the mint hook,
# then the FR-230 digest tests. Evidence lands under .refactor/.
S="$HOME/foundry-of-zero/refactor-python/skills/split-module/scripts"
out=.refactor/gate-merge-engine-prep-iterator.txt
export PATH="$HOME/.local/bin:$PATH"
unset FORGE_SESSION_PID REFACTOR_TYPE_CMD
{
  echo "head=$(git rev-parse HEAD) start=$(date -u +%FT%TZ)"
  bash "$S/verify.sh" --pkg scripts/forge/forge_cli --mint
  echo "verify_rc=$?"
  python3 -m unittest tests.test_fr230_phase3_manifest tests.test_fr223_v2_byte_pins 2>&1 | tail -6
  echo "digest_rc=${PIPESTATUS[0]}"
  echo "end=$(date -u +%FT%TZ)"
} > "$out" 2>&1
echo done > "$TMPDIR/gate-merge-engine-prep-iterator.done"
