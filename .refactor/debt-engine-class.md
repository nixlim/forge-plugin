# Debt report: Engine decompose (SESSION 1, bead forge-plugin-321p)

Measured at finalize on refactor/split-engine-class (tier-1 clusters c01..c09 plus wave-close mint),
against `.refactor-quality.json` (module_target 500, module_ceiling 1000, function_target 150,
class_target 30, max_parameters 6).

## Modules between target (500) and ceiling (1000)

None. Every verb module is under target (275..458 code lines); `_engine.py` is 324. No provisional
`.refactor-baseline.json` entry was added; the grandfathered `_engine.py` entry (3574) is deleted.

## Functions over 150 lines (tier-2 candidates; relocation does not change function length)

| function | module | lines | reason | follow-up |
|---|---|---|---|---|
| `_run_fresh_reviewer_evals` | `_verbs_gate_evals.py` | 362 | single-caller helper of `gate_run`; moved verbatim (tier 1 only this session) | forge-plugin-stfj |
| `gate_run` | `_verbs_gate.py` | 279 | verb body moved verbatim | forge-plugin-stfj |
| `review_request` | `_verbs_review_request.py` | 277 | verb body moved verbatim | forge-plugin-stfj |
| `finalize` | `_verbs_finalize.py` | 240 | verb body moved verbatim | forge-plugin-stfj |
| `review_collect` | `_verbs_review_collect.py` | 177 | verb body moved verbatim | forge-plugin-stfj |

`rebase` (`_verbs_lifecycle.py`) is 147 lines, under target; listed for watching only.

## Classes over 30 methods

None. `Engine` keeps 8 `def`s (`__init__`, `_chains_for_worktree`, `select`, `_record_head_moved`,
`_preflight`, `next_step`, `_wrong_state`, `_emit_decision`) plus 33 class-body bindings, which
`quality.py` does not count as methods.

## Type-coverage regression (not a gate failure)

The mypy ratchet went 251 -> 241 at finalize: ten grandfathered checks inside moved bodies no longer
fire because a function-shape body's `self` is unannotated (mypy: `Any`). Keys (cumulative, from
`.refactor/types-delta-engine-finalize.txt`): 8x `arg-type` "Argument 1 to persist of ChainStore has
incompatible type MutableMapping[str, Any]; expected dict[str, Any]"; 1x `var-annotated` `attempt_fd`;
1x `var-annotated` `verdict_name`. Zero new errors at every cluster. Operator direction 2026-09-20:
accepted as tracked debt. Follow-up: forge-plugin-psvo (`self: "Engine"` under TYPE_CHECKING, a
header-only change in its own reviewed commit).

## Reflection-metadata change (review advisory, both reviewers; Codex B1 downgraded in consensus)

The 18 class functions wrapped by `_serialize_worktree_command` (and the 3 `staticmethod` bindings) no
longer pickle as class-level function objects: `functools.wraps` points the wrapper's `__module__` /
`__qualname__` at the raw `_verbs_*` function, so pickle's by-name lookup finds a different object. They
pickled at 7e40590. `Engine` instances, bound methods and the class still pickle. No production code,
hook or test pickles these objects (multiprocessing tests use the fork context with module-level
targets). The decompose operation contract lists this as an expected function-shape change. No follow-up
bead: nothing to fix unless a pickling consumer appears (mixins are refused in this package).

## Non-move edits on the branch (for the handover)

- P0 78d9610 + 5025042: temporary ruff per-file-ignores glob for `engine/_verbs_*.py` (config-only;
  replaced at finalize by nine measured per-module entries; glob gone before the reviews).
- Wave close 311a9cf: FR-230 manifest gains the nine subjects; mint rewrote the five result fixtures
  and the byte pin.
- Finalize: per-module ruff entries, `_engine.py` entry shrunk to C901/E501/I001/PLR0911/UP035,
  `forge_cli.engine layers` row for the verb modules, `_engine.py` size-baseline entry deleted,
  `.refactor/type-baseline.json` ratcheted to 241, CHANGELOG entry reworded to the measured state.
- No test edits, no spec edits (spec line 117 defines the engine modules as the manifest's subjects,
  which now include the verb modules; whether to name them explicitly is an operator decision).
