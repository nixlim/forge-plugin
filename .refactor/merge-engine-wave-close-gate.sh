#!/usr/bin/env bash
# Wave close gate (bead forge-plugin-37fr): verify.sh --mint with the full parallel set, then the
# FR-230 digest tests and repo conformance.
S="$HOME/foundry-of-zero/refactor-python/skills/split-module/scripts"
out=.refactor/gate-merge-engine-wave-close.txt
export PATH="$HOME/.local/bin:$PATH" PYTHONPATH=scripts:scripts/forge MYPYPATH=scripts:scripts/forge
export TMPDIR=/dev/shm/forge-gate
export REFACTOR_TEST_CMD="bash .refactor/merge-engine-full-set.sh .refactor/fullset-merge-engine-wave-close"
unset FORGE_SESSION_PID REFACTOR_TYPE_CMD
{
  echo "head=$(git rev-parse HEAD) start=$(date -u +%FT%TZ)"
  bash "$S/verify.sh" --pkg scripts/forge/forge_cli --mint
  echo "verify_rc=$?"
  grep "full set:" .refactor/fullset-merge-engine-wave-close/*.txt 2>/dev/null; tail -2 .refactor-gate.log | head -1
  python3 -m unittest tests.test_fr230_phase3_manifest tests.test_fr223_v2_byte_pins tests.test_repo_conformance 2>&1 | tail -4
  echo "digest_rc=${PIPESTATUS[0]}"
  echo "end=$(date -u +%FT%TZ)"
} > "$out" 2>&1
echo done > "$TMPDIR/gate-merge-engine-wave-close.done"
