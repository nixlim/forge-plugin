Evidence:

- [.refactor/plan-revision9-coord.md:645](/home/agents/foundry-of-zero/forge-plugin-refactor-wt/s4/.refactor/plan-revision9-coord.md:645) explicitly prescribes all 16 removals when their final source reader moves; lines 647–664 identify each owning cluster.
- [.refactor/plan-revision9-coord.md:690](/home/agents/foundry-of-zero/forge-plugin-refactor-wt/s4/.refactor/plan-revision9-coord.md:690) records that no re-exports are required.
- [tests/_revision9_coord_constants.py:18](/home/agents/foundry-of-zero/forge-plugin-refactor-wt/s4/tests/_revision9_coord_constants.py:18) is the planned owner of the six constants; [tests/test_revision9_coordination.py:16](/home/agents/foundry-of-zero/forge-plugin-refactor-wt/s4/tests/test_revision9_coordination.py:16) retains only names still used there.
- The per-family manifests’ `remove_imports` entries exactly match the plan.
- I ran:
  - `git grep -n -E 'from tests\.test_revision9_coordination|import (tests\.)?test_revision9_coordination|test_revision9_coordination\.(key|TOOLS|PREFIX_WEDGE|UNREPLAYABLE|hashlib)' f20b8e8 -- tests scripts system hooks agents rules`
  - Searches for patch targets involving `test_revision9_coordination`, `key`, or `hashlib`.
  - All returned no tracked code consumers.
- Importing all six constants from `tests._revision9_coord_constants` succeeds.

AGREE — downgrade BLOCKING 2 to ADVISORY. The old-path namespace loss is observable for hypothetical external importers, so I would not retract it entirely. But this is an internal unittest module, the removals were explicitly planned and manifested, the symbols have a designated new owner, and no tracked consumer or supported public API break exists.