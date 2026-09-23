# Consensus round: revision8 test-split reviews (2026-09-23)

Reviewed source tip: `97d4d60` (BASE main `69bc28d`), branch `refactor/split-test-revision8-coordination`.
Codex (gpt-5.6-sol, effort ultra, thread `01a0ce80-5296-7a53-af2c-ec33d7b35173`): REJECT with 4 BLOCKING + 3
ADVISORY (`codex-review-revision8.md`). Fable refactor-reviewer: APPROVE, no blocking; B2 CONFIRMED as fact and
downgraded, B1/B3/B4 REFUTED as blocking, A1..A3 CONFIRMED as advisory (`fable-review-revision8.md`). Follow-ups
on the Codex thread, one per disputed finding, plus a second round on B1 with new measurements:

| finding | Codex answer | record |
|---|---|---|
| B2 direct execution of `tests/test_revision8_coordination.py` fails before `unittest.main()` | AGREE: advisory. No consumer or documented contract executes an ordinary test module directly (the only direct-file consumer is the purpose-built CLI `tests/test_repo_conformance.py`); 30 test modules at BASE already pair a top-level `from tests...` import with a `__main__` guard; the import form is the brief's mandated `--import-root` deviation | `consensus-revision8-B2.md` |
| B3 relocated names (`TOOLS`, `RECORDED_AT`, `batch`, `journal`) not re-exported from the source module | RETRACT: no importer at BASE or HEAD (git grep and an AST scan of every tracked Python file), no declared contract; `tests` is not a declared package; the relocation is manifested | `consensus-revision8-B3.md` |
| B4 module-globals ownership split between the support and family modules | RETRACT: AST scans at both revisions find zero module-attribute rebinds and zero string-path patches; all 72 patches are `mock.patch.object` on the shared `journal` object plus 4 `patch.dict(os.environ)`; constants are immutable | `consensus-revision8-B4.md` |
| B1 `scripts` inserted on `sys.path` twice (constants module + the retained shell line), ahead of `scripts/forge` | Round 1 DISAGREE (ordinary imports resolve identically and no consumer imports `forge` or counts entries, but `forge.__path__` length and `pkgutil` importer count differ). Round 2 with new measurements (BASE under the documented `PYTHONPATH=scripts:scripts/forge` already has `forge.__path__` length 2 and `scripts` twice, tip 3/3; bare env BASE 1 / tip 2; four BASE test modules each insert `scripts`; nothing imports `forge` or enumerates its `__path__`; the shell's line is dead code removed with the shell under forge-plugin-7pzp): AGREE: advisory ("pre-existing in kind, disclosed, tracked for cleanup, and has no repository observer or resolution effect; it is not blocking"; Codex's own table: scripts count / forge.__path__ / importers = 1/1/1 BASE bare, 2/2/2 BASE documented env, 2/2/2 tip bare, 3/3/3 tip documented env; BASE Gate 1 already places two self-inserting modules in one shard) | `consensus-revision8-B1.md`, `consensus-revision8-B1-round2.md` |

Advisories, all accepted and recorded in the handover bead: A1 `.refactor/gate1-revision8.sh` exports `PYTHONPATH`
(the bare-`PYTHONPATH` proofs are the per-cluster standalone imports and the reviewer's shard simulation, 4/4) and
records `gate1_rc` without propagating it (evidence tooling; every log reads `gate1_rc=0`); A2 plan section 0.3 says
the empty shell exits 0 under unittest, it exits 5 (the debt report is correct); A3 the two finalize Gate 1 logs
were untracked at review time (tracked by the records commit that follows this file). Fable advisory: the shell's
`sys.path.insert` line is redundant after the constants import (kept because no hand edit is allowed; gone with
the shell, forge-plugin-7pzp).

Outcome: both reviewers agree there is no blocking finding on `97d4d60` (Codex: B1 AGREE advisory in round 2, B2 AGREE advisory, B3 RETRACT, B4 RETRACT; Fable: APPROVE). The review-records commit that follows this file tracks every artifact named above; the source tree is identical to `97d4d60`.
