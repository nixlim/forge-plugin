# Consensus round: MergeEngine decompose reviews (2026-09-22)

Reviewed source tip: `eb1cc9e` (base main `d885f97`), branch `refactor/split-merge-engine`. Codex (gpt-5.6-sol,
effort ultra, thread `01a0c955-0292-78c0-b81e-52a2d34b4d5e`): REJECT with 3 BLOCKING + 4 ADVISORY
(`codex-review-merge-engine.md`). Fable refactor-reviewer: APPROVE, no blocking; every Codex item CONFIRMED as
fact, B1-B3 REFUTED as blocking (`fable-review-merge-engine.md`). Follow-ups on the Codex thread, one per disputed
finding, plus a second round on B3 after the remedy was performed:

| finding | Codex answer | record |
|---|---|---|
| B1 `typing.get_type_hints()` raises `NameError` on the 75 annotated receivers | AGREE: advisory. No consumer (`git grep` over scripts/tests/hooks/skills/system: none); `inspect.signature`/autospec intact; the `TYPE_CHECKING` class import is the documented `--annotate-self` contract and a runtime import would be the cycle it avoids; disclosed in CHANGELOG and the debt report | `consensus-merge-engine-B1.md` |
| B2 wave-close gate log records `digest_rc=1`; no Gate 1 artifact at wave close | AGREE: advisory once the rerun artifacts are tracked. The committed log is the run before the same commit renamed three `.refactor/*.log` files (only `test_dogfood_file_categories` failed); `gate-merge-engine-wave-close-rerun-b0a2e72.txt` (35 tests OK, `digest_rc=0`) and `gate1-merge-engine-wave-close-b0a2e72.txt` (4/4 shards, 1,908 tests, `gate1_rc=0`) supersede it. Not retracted: the wrapper `merge-engine-wave-close-gate.sh` records but does not propagate the digest rc (tooling defect, noted in the handover) | `consensus-merge-engine-B2.md` |
| B3 e05 checkpoint failure bisected with the two failing tests, not the full set | Round 1 DISAGREE (a request for ratification is not ratification; run the five full-set runs or obtain approval). Round 2 AGREE: advisory, resolved. `bisect-merge-engine-t2-e05-fullset.txt` records the full seven-module set at each of the five pre-e05 commits (6e60498, c81829d, 034df09, 913f275, 05288f0), each 7/7 OK, 247 tests, plus the e05 same-tree rerun 7/7; the original finding stands as accurate before the remedy | `consensus-merge-engine-B3.md`, `consensus-merge-engine-B3-round2.md` |

Advisories, all accepted and recorded in the handover bead: A1 nineteen imports pruned from the private
`_merge_engine.py` shell (no readers; critique A6); A2 the declared P1 annotation change and the one new
pickling failure (the `contextlib.contextmanager(...)` wrapper bound as `_recording_common_lock`; 2 of 93
attributes at the tip vs 1 at baseline); A3 CHANGELOG and debt-report wording (corrected in the records commit;
Fable's own correction of the session's over-claim, "86 objects", to "one wrapper", applied); A4
`merge-engine-debt.json` sizes and probe 10 (corrected: 578/584/830 measured; probes 12/12 with declared `_steps`
siblings allowed).

Outcome: both reviewers agree there is no blocking finding on `eb1cc9e`. The review-records commit that follows
this file tracks every artifact named above; the source tree is identical to `eb1cc9e`.
