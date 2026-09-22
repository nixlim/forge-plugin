#!/usr/bin/env bash
# Review-round evidence (Codex B2/B3, 2026-09-22): digest/conformance tests at the wave-close
# commit b0a2e72 in a temporary worktree, and the e05 bisect re-run with tracked output.
set -u
root=$(pwd); export TMPDIR=/dev/shm/forge-gate PYTHONPATH=scripts:scripts/forge; unset FORGE_SESSION_PID
out=.refactor/gate-merge-engine-wave-close-rerun-b0a2e72.txt
wt=$TMPDIR/wt-b0a2e72; rm -rf "$wt"; git worktree add -q --detach "$wt" b0a2e72
( cd "$wt" && { echo "commit=$(git rev-parse HEAD) $(date -u +%FT%TZ)"; python3 -m unittest tests.test_fr230_phase3_manifest tests.test_fr223_v2_byte_pins tests.test_repo_conformance 2>&1 | tail -4; echo "digest_rc=${PIPESTATUS[0]}"; } ) > "$out" 2>&1
git worktree remove --force "$wt"
bis=.refactor/bisect-merge-engine-t2-e05.txt
tests="tests.test_cli_merge_integration.MergeIntegrationEpochTests.test_inactive_older_only_landing_releases_tagged_terminal tests.test_cli_merge_integration.MergeIntegrationEpochTests.test_inactive_push_observed_requires_fresh_completed_progress"
{ echo "e05 bisect re-run $(date -u +%FT%TZ): the two tests that failed the e05 parallel checkpoint, at each tier-2 commit"
  for sha in 6e60498 c81829d 034df09 913f275 05288f0 3f421b0; do
    w=$TMPDIR/wt-bisect-$sha; rm -rf "$w"; git worktree add -q --detach "$w" "$sha"
    r=$(cd "$w" && python3 -m unittest $tests 2>&1 | tail -1); echo "$sha $(git log -1 --format=%s "$sha" | cut -c1-70): $r"
    git worktree remove --force "$w"
  done; } > "$bis" 2>&1
echo done > "$TMPDIR/review-evidence.done"
