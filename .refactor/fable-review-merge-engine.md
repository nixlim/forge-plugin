# Fable adjudicating review: MergeEngine decompose (refactor-reviewer, 2026-09-22)

Reviewed: main d885f97 .. eb1cc9e (finalized tip, 55 linear commits) on refactor/split-merge-engine, plus the
uncommitted working-tree corrections (`git diff eb1cc9e`: CHANGELOG.md, .refactor/debt-merge-engine.md,
.refactor/merge-engine-debt.json, .refactor/merge-engine-sim-tool-probes.py; `git diff eb1cc9e -- scripts` is empty).
Read-only. Own check first (oracle replays in my own detached worktree, shell header and binding inspection against
the baseline AST, census probes, live-out analysis of the nine extractions, measured ruff/size/type evidence, the
CLAUDE.md trio, gate artifacts), then the Codex review `.refactor/codex-review-merge-engine.md` finding by finding.

VERDICT: APPROVE
CODEX_VERDICT: REJECT (3 BLOCKING, 4 ADVISORY; gpt-5.6-sol ultra, confidence high, thread 01a0c955-0292-78c0-b81e-52a2d34b4d5e)

BLOCKING:
- none. No hunk changes behavior or an API that anything in the repository uses.

ADVISORY:
- CHANGELOG.md:13 and .refactor/debt-merge-engine.md:76 (working tree) — the corrected wording over-claims the pickle
  consequence: "the 86 class-level function objects ... no longer pickle by qualified name" is wrong. Measured at HEAD
  with `pickle.dumps` over all 93 `MergeEngine.__dict__` attributes: 2 fail (`store`, a property, fails at d885f97 too;
  `_recording_common_lock`, the `contextlib.contextmanager(...)` wrapper, new). Plain moved functions pickle: their
  `__module__`/`__qualname__` (`forge_cli.app._engine_lifecycle.start`) resolve to the same object. Only the one
  contextmanager wrapper regresses (its `functools.wraps` metadata points at the raw generator). Reword to "one" before
  the commit that carries these files. The `get_type_hints` sentence (75 of 93) and the `__module__`/`__qualname__`
  sentence are accurate.
- .refactor/gate-merge-engine-wave-close.txt:17-18 vs b0a2e72's commit message — the committed log (head=f5ac5b3, run
  before the `.log -> .txt` renames) ends `FAILED (failures=1)` / `digest_rc=1` while the commit message says the three
  digest/conformance modules were OK. Reproduced: at f5ac5b3, `tests.test_repo_conformance` fails
  `test_dogfood_file_categories_preserve_generics_and_cover_repository` on exactly the three `.refactor/*.log` files that
  b0a2e72 renames; nothing else fails. The OK run was not captured then. Tracked now:
  `.refactor/gate-merge-engine-wave-close-rerun-b0a2e72.txt` (35 tests OK, digest_rc=0) and
  `.refactor/gate1-merge-engine-wave-close-b0a2e72.txt` (Gate 1 cell in a worktree at b0a2e72: 4 shards exit 0,
  496+582+363+467 = 1908 tests, gate1_rc=0, 14:02:08Z-14:10:31Z). Handover should name the stale log as superseded.
  Tooling: `.refactor/merge-engine-wave-close-gate.sh:16-19` records `digest_rc` but exits 0 and writes `.done` regardless;
  a future driver should propagate it.
- .refactor/plan-merge-engine.md:1139 (operator rule: "bisected over at most five commits by re-running the full set at
  each") vs what ran at e05 — the two failing tests were re-run in isolation at six commits
  (`.refactor/bisect-merge-engine-t2-e05.txt`, all OK) and the full set was re-run on the same tree (7/7), not the full
  set at each earlier commit. Literal deviation from the rule; the operator should ratify it in the handover or order the
  five full-set runs (~15 min). Not a behavior question (see B3 below).
- Reflection debt for every future `--annotate-self` move: `typing.get_type_hints()` on a moved instance/class method
  raises `NameError` because the receiver annotation names a `TYPE_CHECKING`-only import. Inherent to the contract
  (operations.md:74 "never evaluated at runtime"); a runtime import would be the cycle the contract avoids. Worth a plugin
  bead (e.g. document it next to the pickling sentence at operations.md:85, or offer a runtime-resolvable spelling).
- e06 not applied (rope dropped the live-out `next_state`) is correctly refused and recorded in the tier-2 plan; my own
  live-out analysis of the nine applied extractions (names assigned in each helper, read by the caller after the call,
  not returned) finds none, so that rope failure mode did not slip through elsewhere.

OWN CHECK (evidence):
- Oracle replays in a fresh detached worktree at each commit, own run: c01 653eb44, c16 61b3f8d, c17 3bf9201,
  c28 4d5cf46, c29 f5ac5b3 PASS (tier 1); e01 c81829d, e02 034df09, e03 913f275, e04 05288f0, e05 3f421b0, e07 b8ac959,
  e08 ce5d17d, e09 3b138b6, e10 22cb6a8 PASS (tier 2). Session's `.refactor/merge-engine-wave-verify.txt`: 29/29 PASS.
- Final sources vs reviewed outputs: `git diff 68c639a..eb1cc9e -- scripts` and `git diff eb1cc9e -- scripts` empty;
  3fffe48..68c639a (UP037) is exactly 74 `self: "MergeEngine"` -> `self: MergeEngine` and 1 `cls: "type[MergeEngine]"`
  -> `cls: type[MergeEngine]`, nothing else; d3946d7 (P1) is the two declared `Iterable` -> `Iterator` lines; the 13
  docs/config/evidence commits touch no file under scripts/.
- Shell `_merge_engine.py`: header equals plan §3 (contextlib, Path, Any/Mapping, chain_core/engine, five envelope
  names, 27 `from . import _engine_*`); class body 7 defs + 86 bindings in the baseline order; every binding form matches
  the baseline decorator (78 plain, 11 staticmethod, 1 classmethod, 1 contextlib.contextmanager); the 7 staying bodies
  are AST-identical to d885f97; 224 code lines.
- Tier-2 manifests: all nine match the plan's ranges, parameter and output counts; each `base_commit` is the previous tip.
- Census probes (`merge-engine-sim-tool-probes.py`, working tree): 12/12 PASS. `app/__init__.py` byte-identical to
  d885f97 (`__all__` verbatim); `_dispatch.py` still imports `MergeEngine` from `_merge_engine`.
- No module-level state in any `_engine_*` module; no package-root or parent imports; the only nested imports are the 27
  identical `if TYPE_CHECKING: from forge_cli.app._merge_engine import MergeEngine` blocks; the three `_steps` imports
  are top-level and declared; `pyproject.toml:263 exclude_type_checking_imports = true`; new layers rows present.
- CLAUDE.md trio on the working tree: ruff "All checks passed!"; check_file_length "231 files within budget";
  lint-imports "5 kept, 0 broken".
- Measured ruff codes with all 31 app entries removed from a ruff-only config: 120 diagnostics, entries match measured
  codes for 31/31 files (no UP037 anywhere; no I001 on any destination).
- Sizes (check_file_length.code_lines): `_engine_lock` 578, `_engine_recover` 584, `_engine_recover_conflict` 830 =
  `.refactor-baseline.json` and `merge-engine-debt.json` (working tree); the 10302 entry is gone.
- Types: 38 delta files NEW=0 GONE=0; prep-iterator NEW 0, 7 fixed (241 -> 234), as declared.
- Gates: 29 tier-1 gate logs and 9 tier-2 gate logs end `GATE: PASS [exit 0]`; UP037 gate PASS (NEW 0 GONE 0);
  finalize mint OK digest_rc=0; Gate 1 finalize run1 and run2 4/4 shards OK, 1908 tests each (same count as session 1's
  finalize on main). Full-set checkpoints 7/7 at baseline x2, c01, c05, c10, c15, c16, c17, c19, c20, c23, c25, c29,
  e05 rerun, e10, t2 wave close.
- Tests: `git diff d885f97..eb1cc9e -- tests` is the byte pin plus five FR-230 fixtures (mint); no test edit, no ID map.
- FR-230: the manifest's `scripts/forge/forge_cli/app/` production block is sorted, duplicate-free and equals the 36 app
  files exactly (spec line 117's "exactly" holds).
- Reflection at HEAD vs d885f97 (same probe in both trees): `get_type_hints` fails 76 vs 1 (`store` both) = 75
  regressions; `pickle.dumps` fails 2 vs 1 = 1 regression; `inspect.signature(MergeEngine.start)` works (string
  annotations). Readers of `get_type_hints`/`eval_str`/`__annotations__`/`get_annotations` in scripts, tests, hooks,
  skills, system: none. Pickle/multiprocessing users: tests/test_d13_concurrency.py and
  tests/test_revision9_terminal_races.py only (`get_context("fork")`, neither mentions `MergeEngine` or `forge_cli.app`).

CODEX_FINDINGS:
- B1 get_type_hints NameError on 75 moved methods — CONFIRMED as fact (my probe: 75 regressions, public verbs included),
  REFUTED as blocking: no reader of `get_type_hints`/`eval_str`/`__annotations__` in scripts/, tests/, hooks/, skills/,
  system/; `inspect.signature`, autospec patching and attribute access all work (probes 3, 5, 8); the behavior is the
  documented `--annotate-self` contract the operator selected (operations.md:58-75, "never evaluated at runtime"), and
  the fix Codex implies (a runtime import) is the import cycle the contract exists to avoid. Disclosed in the debt report
  and CHANGELOG (working tree). Advisory, same class as session 1's pickling finding.
- B2 wave-close digest_rc=1 / no Gate-1 artifact — CONFIRMED as fact (log lines 17-18; wrapper does not propagate rc;
  no wave-close Gate-1 log existed at review time), REFUTED as blocking: the failure is
  `test_dogfood_file_categories_preserve_generics_and_cover_repository` on three `.refactor/*.log` evidence files,
  reproduced by me at f5ac5b3 and fixed by the renames inside b0a2e72; the digest/conformance modules pass at b0a2e72
  (`gate-merge-engine-wave-close-rerun-b0a2e72.txt`), and the Gate 1 cell at b0a2e72 in a worktree is 4/4 OK, 1908
  tests, `gate1_rc=0`. No source file changed between the mint and b0a2e72. Plan §7:1119 is now met with artifacts.
- B3 e05 bisect not performed — CONFIRMED as fact (the full set was not re-run at each of the five earlier commits),
  REFUTED as blocking: the two failures are the `exists is None` -> `push-outcome-unknown` branch of
  `_run_remote_observation` (`_engine_observe_remote.py:416`) and an `attempted_heads` mismatch in
  `prepare_older_only_attempts`, both reached through the bounded process runner's real-time budget
  (runtime.py:281-416) under load 16 on 12 cores; both tests pass in isolation at all six tier-2 commits
  (`bisect-merge-engine-t2-e05.txt`), the full set passes 7/7 on the same tree (`fullset-merge-engine-t2-e05-rerun.txt`)
  and on every later tree containing e05 (e10, t2 wave close, Gate 1 x2 at finalize); the e05 oracle passes at 3f421b0
  and my live-out analysis finds no unreturned write in `_persist_remote_observation_delta`. Full-set runs at commits
  that precede e05 cannot implicate e05; the rule's literal form is an evidence-format deviation for the operator to
  ratify (advisory above).
- A1 19 pruned imports from `_merge_engine.py` — CONFIRMED (base64, copy, dataclasses, os, re, secrets, socket, stat,
  sys, Callable, Iterable, Sequence, runtime, prepare_merge_admission, _observe_current_merge_candidate,
  _persist_deferred_mutation_result, Outcome, Policy, sha256_bytes = 19). Only readers of the module path are
  `_dispatch.py` and `app/__init__.py`, both importing `MergeEngine`; declared per cluster in `remove_imports`
  (plan §4 "Common"); private path; disclosed in the debt report. Advisory.
- A2 P1 `Iterable` -> `Iterator` and the contextmanager wrapper unpicklable — CONFIRMED as fact: P1 is the operator-
  directed type-only prep (brief item 2, plan §4 P1, 7 mypy checks fixed, its own commit d3946d7); the wrapper is the
  single pickle regression (measured, above), same mechanism as session 1's `_serialize_worktree_command`. Advisory.
- A3 CHANGELOG/debt wording — CONFIRMED and still partly wrong after the correction: the reflection consequences are
  now present, but "86 class-level function objects ... no longer pickle" over-claims (1, not 86). See ADVISORY 1.
- A4 debt.json stale sizes; probe 10 at 11/12 — CONFIRMED at eb1cc9e, corrected in the working tree: debt.json now
  578/584/830 with post-tier-2 reasons and follow-ups (equal to measured); probe 10 admits the declared `_steps`
  sibling and the suite is 12/12.

FINDINGS CODEX MISSED: the pickle over-claim in the corrected wording (advisory, docs); nothing in source.

DISPUTED (to the consensus round): B1, B2, B3 as blocking.

ALLOWED_CHANGED: none
