Evidence:

- `.refactor/plan-merge-engine.md:1139-1140` requires the full set at each of at most five commits.
- `git show -s --format='%H %P %s'` confirms e05’s five first-parent predecessors are exactly `05288f0`, `913f275`, `6e60498`, `034df09`, and `c81829d`.
- `.refactor/merge-engine-bisect-fullset.sh:7-12` runs those five revisions serially in detached worktrees and invokes the full-set runner.
- `.refactor/merge-engine-full-set.sh:10-29` defines all seven modules, captures process return codes, requires each log to contain a test count and terminal `OK`, and succeeds only with `xargs rc=0` and 7/7 modules.
- `.refactor/bisect-merge-engine-t2-e05-fullset.txt:2-6` records all five revisions with `rc=0`, `7/7 modules OK`, and `xargs rc=0`.
- Each `.refactor/bisect-merge-engine-t2-e05-fullset/<sha>.txt:1-8` records seven module-level `rc=0` results and a 7/7 summary. Checking every underlying log found seven terminal `OK` lines per revision and 247 tests per revision.
- `.refactor/fullset-merge-engine-t2-e05-rerun.txt:1-8` supplies the corresponding 7/7 pass on e05 itself.

`git status --short` still shows the new summary, logs, and generator as untracked. Their promised inclusion in the review-records commit remains a delivery requirement.

AGREE — downgrade B3 to advisory. The exact plan-mandated full-set bisect has now been performed, so no reliance on the load-causation theory is necessary. I do not retract the original finding because it was accurate before this remedy; it is now resolved, subject only to tracking the evidence as promised.