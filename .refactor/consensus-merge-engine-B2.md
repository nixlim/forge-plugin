Evidence:

- `.refactor/gate-merge-engine-wave-close.txt:1,15-18` is a run at `f5ac5b3` with one failure and `digest_rc=1`.
- A category census using `git show f5ac5b3:forge-project.md` and `git ls-tree -r --name-only f5ac5b3` found exactly three unmatched `.refactor/*.log` files. `git diff --name-status f5ac5b3 b0a2e72 -- .refactor | rg '^R'` shows all three renamed `R100` to `.txt`.
- `.refactor/gate-merge-engine-wave-close-rerun-b0a2e72.txt:1-6` records exact commit `b0a2e72`, 35 tests passing, and `digest_rc=0`.
- `.refactor/gate1-merge-engine-wave-close-b0a2e72.txt:1-35` records four passing shards, 1,908 tests total, and `gate1_rc=0`.
- The two finalize Gate 1 logs also record consecutive 4/4-shard passes.
- `.refactor/merge-engine-wave-close-gate.sh:10-19` confirms the wrapper records return codes but does not propagate failure and always writes its completion marker.

One correction: `git status --short` currently marks both new wave-close artifacts `??`, and `git ls-files --stage -- <paths>` returns nothing. They are not yet tracked.

AGREE — downgrade to advisory for the handover once the rerun artifacts and supersession statement are tracked. The exact-SHA reruns close the substantive verification gap. I do not retract the historical observation: the original committed log failed, and the wrapper’s swallowed return code remains a tooling defect.