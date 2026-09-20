# Decompose plan: `Engine` in `scripts/forge/forge_cli/engine/_engine.py` (function shape, tier 1)

Mode: **decompose** (class → verb modules), production class, **function shape**, **tier 1 only**.
Evidence root (dry runs, seeded inventory, seeds file):
`/dev/shm/forge-gate/claude-1000/-home-agents-foundry-of-zero-forge-plugin/edd6e87d-353b-4831-8e88-e17ed3b25f78/scratchpad/plan/` — referred to below as `$EVID`.
Tool roots: `$D=/home/agents/foundry-of-zero/refactor-python/skills/decompose/scripts`,
`$S=/home/agents/foundry-of-zero/refactor-python/skills/split-module/scripts`.

## 1. Summary

| item | value |
|---|---|
| baseline commit | `5480091` on `refactor/split-engine-class` (tree identical to `main` `7e40590`) |
| source | `scripts/forge/forge_cli/engine/_engine.py`: 3,710 total lines / **3,574 code lines** (`scripts/check_file_length.py` count; grandfathered at 3574 in `.refactor-baseline.json:19`) |
| class | `Engine`, 41 methods (20 `ok`, 21 `wrap`, 0 unsupported), no bases, no metaclass, no slots, no class statements |
| hubs (peeled, stay on the class) | `@state:ctx`, `select`, `_preflight`, `_wrong_state`, `next_step`, `_emit_decision` |
| shape | function: bodies move verbatim to `engine/_verbs_<x>.py`; the class keeps `name = _verbs_<x>.name` bindings (`staticmethod(...)` / `_serialize_worktree_command(...)` re-applied exactly as the smoke dry run showed) |
| tier | **1 only** (relocation, bodies verbatim, `--strict-bodies`). No tier-2 extraction in this plan (see §4 debt) |
| result | 9 clusters → 9 new modules of 275–458 code lines each; `_engine.py` shrinks to **324** code lines; 33 bindings + 8 real methods remain on `Engine` |
| prerequisites | none (inventory `prerequisites: []`; every helper the bodies read is an import, not a module-level definition in `_engine.py` — `grep -n "^def \|^[A-Za-z_]* = " _engine.py` returns nothing, so no "globals need an independent owner" refusal is possible) |
| dry runs | all nine exit 0 with `DRY RUN: verified; no files written` against the baseline tree: `$EVID/dryrun-<x>.txt` |
| seeded inventory | `python3 $D/class_inventory.py ... --seeds $EVID/seeds.json` → `$EVID/inventory-seeded.txt` (JSON): verdicts unchanged (20 ok / 21 wrap), every seed forms one connected cluster; the tool additionally pulls `_record_head_moved` into the status seed and `_chains_for_worktree` into the lifecycle seed — both are rejected here because each is also called from a hub that stays (§2) |

**Sequential-simulation evidence (not the project tree).** The nine clusters were applied in plan
order, one commit each, in a throwaway `git clone` of the baseline under the session scratchpad
(`/tmp/claude-1000/-home-agents-foundry-of-zero-forge-plugin/53cf828a-bf7b-4fb2-bdfc-aad5161b1996/scratchpad/sim`,
manifests + logs in its `.refactor/`). Nothing in the project tree was modified. Observed there:
`scripts/check_file_length.py scripts/forge/forge_cli/engine` → `ok: 38 files within budget`;
`lint-imports` → `Contracts: 5 kept, 0 broken` with no contract edit; `ruff check` on the new
modules reports only codes already grandfathered on `_engine.py` (no `F401`, no `I001` — the
`--format-imports` sort holds and no import is over-copied); `type_baseline.py check` reports the
same three `import-not-found` lines that the *untouched* project tree reports in this shell
(`codex_orchestrator` at `runtime.py:74`, `chain_core/_core.py:29`, `_repository.py:76` — an
environment difference, `MYPYPATH` unset), i.e. **zero move-induced type errors**; the census
probes in §5 all pass. Per-cluster numbers quoted below as "sequential" come from that
simulation; the extractor's own dry run at apply time is the authoritative manifest.

## 2. Stays in `_engine.py` (8 methods, 270 code lines + header + 33 bindings ≈ 324 code lines)

| method | lines | reason |
|---|---|---|
| `__init__` | 34–35 | constructor; owns `self.ctx` (the `@state:ctx` hub) |
| `_chains_for_worktree` | 255–271 | called by hub `select` (stays) and by `_live_chain` (c03) → shared across a hub and a cluster: stays on the class; `_live_chain` reaches it as `self._chains_for_worktree` |
| `select` | 273–316 | hub (fan-in 15) |
| `_record_head_moved` | 324–343 | called by hub `_preflight` (stays), `status` (c02) and `finalize` (c09) → shared across a hub and two clusters: stays |
| `_preflight` | 345–456 | hub (fan-in 17) |
| `next_step` | 583–615 | hub (fan-in 13) |
| `_wrong_state` | 1160–1173 | hub (fan-in 16); calls `self.next_step` |
| `_emit_decision` | 3280–3312 | hub (fan-in 5); census site `patch.object(CLI.Engine, '_emit_decision', autospec=True)` ×3 keeps patching a real method |

Every moved body that calls `self.select(...)`, `self._preflight(...)`, `self._wrong_state(...)`,
`self.next_step(...)`, `self._emit_decision(...)`, `self._record_head_moved(...)` or
`self._chains_for_worktree(...)` keeps working unchanged: these stay real methods on `Engine`.
Likewise a body in one cluster calling a method moved by another cluster (e.g. `status` →
`self._require_tombstone_control()` (c01), `self._recover_committing(...)` (c09); `gate_run` →
`self._run_fresh_reviewer_evals(...)` (c05), `self.scan_secrets(...)` (c04); `verify` →
`self.gate_run(...)` (c04); `review_collect`/`review_attach` → `self._parse_verdict`,
`self._apply_verdict` (both c08); `_review_package` → `self._profiles_for_path` (c07)) resolves
through the class-body binding whatever the commit order, because attribute lookup on `self`
finds the binding exactly where it found the `def`. **The critic must not flag cross-cluster
`self.` calls.**

Expected `_engine.py` header after the wave (sequential simulation; the extractor's manifests
decide the exact `remove_imports` per cluster):

```
from __future__ import annotations
import sys
from typing import Any, Mapping, MutableMapping
from forge_cli import candidate as candidate_module, chain_core, runtime
from forge_cli.engine._archive import _archive_recheck as _archive_recheck
from forge_cli.engine._candidate_ops import _adopt_out_of_band_candidate as _adopt_out_of_band_candidate
from forge_cli.engine._command_lock import _serialize_worktree_command as _serialize_worktree_command
from forge_cli.engine._core import _archive_metadata as _archive_metadata, _run_halt as _run_halt
from forge_cli.engine._state import TERMINAL_STATES as TERMINAL_STATES, TERMINAL_TOUCH_VERBS as TERMINAL_TOUCH_VERBS
from forge_cli.envelope import FrozenError, REVISION9_OUTPUT_SCHEMA, ReasonCode, Refusal
from . import _verbs_tombstone … from . import _verbs_finalize   (nine sibling imports)
```

## 3. Clusters in execution order (one commit each; sequential per source file)

Common to every cluster:

- Tier **1**. Shape `function`. Alias = destination stem. `--format-imports` on dry run and apply
  (ruff `I` rules are enforced; `format_imports: true` recorded in every manifest).
- Dry runs below were run against the **current baseline tree** as nine independent dry runs.
  In the applied sequence the extractor **re-dry-runs each cluster against the tree after the
  previous cluster's commit**, takes a fresh snapshot `.refactor/engine-cNN-before.json`
  (`python3 $S/snapshot_bodies.py snapshot scripts/forge/forge_cli --out .refactor/engine-cNN-before.json` — scope exactly `scripts/forge/forge_cli`, the gate's `--pkg`; including `tests` makes the oracle fail on unmanifested files: critic blocking finding 1),
  then applies. Bindings and destination imports are identical between baseline and sequential
  dry runs; only `remove_imports` grows (an import is removed when its *last* reader leaves
  `_engine.py`, which for shared names happens in a later cluster). Both values are listed.
- Gate environment (critic blocking finding 2; without `PYTHONPATH`/`MYPYPATH` the `types` step reports 3 new `import-untyped` errors and the gate FAILs): run from the repo root as
  `env -u FORGE_SESSION_PID -u REFACTOR_TYPE_CMD PYTHONPATH=scripts:scripts/forge MYPYPATH=scripts:scripts/forge TMPDIR=/dev/shm/forge-gate PATH="$HOME/.local/bin:$PATH" bash $S/verify.sh ...`
  (same variables the app split's `.refactor/split-app.workflow.js` GATE_ENV exported; `REFACTOR_TEST_CMD` and `REFACTOR_MINT_CMD` come from the launching shell). Verified on the untouched tree: `types ok: 251 error(s), all grandfathered`.
- Verify (after apply, before commit), with `REFACTOR_TEST_CMD` already exported
  (`tests.test_cli_chain tests.test_cli_chain_finalize tests.test_revision9_cli_surfaces tests.test_cli_loader`):
  `bash $S/verify.sh --pkg scripts/forge/forge_cli --snapshot .refactor/engine-cNN-before.json --manifest .refactor/engine-<x>.json --strict-bodies`
  `verify.sh` runs ruff, `check_file_length.py` (honours `.refactor-baseline.json` in cwd, so the
  shrinking grandfathered `_engine.py` passes at every step), the mypy ratchet
  (`type_baseline.py check`, baseline keyed by *(code, message)* so the five grandfathered
  `_engine.py` entries keep matching after they move files), `lint-imports`, and the focused tests.
- Expected refusals: **none** for any cluster (all nine dry runs verified; the refusal classes in
  `operations.md` — property setters, stacked/undeclared decorators, name mangling, `super`,
  `__class__`, globals still defined in the source, destination import-name clash — do not
  occur: inventory `reasons: []` for all 41 methods, `mangled: []`, and no method name collides
  with a destination import).
- Commit message form: `refactor(engine): move <cluster> verbs to _verbs_<x>.py (tier 1, function shape)`.
  Every cluster commit touches `*.py` → the project changelog gate needs one `## [Unreleased]`
  line staged with it.

### Prerequisite config commit P0 (before c01, config only, no code moved)

`verify.sh` runs `ruff check scripts/forge/forge_cli`; a new `_verbs_*.py` gets the full rule
set, so the grandfathered findings that today hide under the `_engine.py` per-file-ignores entry
fail the c01 gate unless a destination entry exists (`operations.md` §Manifest: "existing
source-path per-file ignores may need corresponding destination entries"; precedent: plan-engine.md
step E2 added `engine/*.py` at package conversion and narrowed per module at finalize). Add to
`[tool.ruff.lint.per-file-ignores]`, next to the `_engine.py` entry:

```
"scripts/forge/forge_cli/engine/_verbs_*.py" = ["B904", "C901", "E501", "PLR0911", "PLR0912", "PLR0913", "PLR0915", "PLR1702", "UP012", "UP035"]
```

That is the union of what the moved bodies trip (sequential simulation, `ruff --output-format json`),
a strict subset of the `_engine.py` list: `I001` and `PLR0904` are deliberately **not** carried
(sorted imports are proven by the manifest gate; there is no class in the verb modules). Finalize
narrows it per module (§4 table) and deletes the glob. This is the CLAUDE.md "never add to that
list" exception that both prior splits used for relocated code — **operator/critic call**; the
alternative is one per-module entry in each cluster commit (same codes, from §4), which keeps
cluster commits from being pure mover output. Commit: `chore(refactor): ruff per-file-ignores for engine/_verbs_*.py (relocated Engine bodies)` + changelog line.

### c01 — `tombstone` (first; operator watches this one through gate and merge)

- destination: `scripts/forge/forge_cli/engine/_verbs_tombstone.py` — tombstone/abort family: the
  three tombstone-creating verbs and their two shared helpers.
- methods (source order): `_require_tombstone_control` (38–45, `staticmethod`), `_tombstone_outcome` (47–62), `operator_tombstone` (65–112, `_serialize_worktree_command`), `abort` (878–972, `_serialize_worktree_command`), `abort_disposition` (975–1042, `_serialize_worktree_command`), `_tombstone_abort_disposition` (1044–1158)
- why this grouping: `_require_tombstone_control`/`_tombstone_outcome` are called by `operator_tombstone`, `abort` (both here) and `status` (c02) → helpers travel with the first cluster holding two of their three callers; `status` reaches them via `self.`. `_tombstone_abort_disposition` is called only by `abort_disposition`. Representative for the operator: one `staticmethod` binding, two plain bindings, three `_serialize_worktree_command` bindings; 346 code lines; no census site; `abort`'s `Mapping` annotation exercises `from typing import ...` copying.
- dry run: `python3 $D/move_methods.py --project . --source scripts/forge/forge_cli/engine/_engine.py --dest scripts/forge/forge_cli/engine/_verbs_tombstone.py --class Engine --methods _require_tombstone_control,_tombstone_outcome,operator_tombstone,abort,abort_disposition,_tombstone_abort_disposition --import-root scripts/forge --shape function --format-imports --manifest .refactor/engine-tombstone.json`
- apply: same argv + `--apply`
- expected class bindings (from the dry run):
  ```
  _require_tombstone_control = staticmethod(_verbs_tombstone._require_tombstone_control)
  _tombstone_outcome = _verbs_tombstone._tombstone_outcome
  operator_tombstone = _serialize_worktree_command(_verbs_tombstone.operator_tombstone)
  abort = _serialize_worktree_command(_verbs_tombstone.abort)
  abort_disposition = _serialize_worktree_command(_verbs_tombstone.abort_disposition)
  _tombstone_abort_disposition = _verbs_tombstone._tombstone_abort_disposition
  ```
- expected destination imports (manifest `imports[dest]`): `from __future__ import annotations`; `import copy`; `from typing import Any, Mapping`; `from forge_cli import chain_core, runtime`; `from forge_cli.engine._approval import _success as _success`; `from forge_cli.engine._command_lock import abort_disposition_refusal as abort_disposition_refusal`; `from forge_cli.engine._core import _transition_state as _transition_state, _run_halt as _run_halt`; `from forge_cli.engine._state import TERMINAL_STATES as TERMINAL_STATES`; `from forge_cli.envelope import FrozenError, Outcome, REVISION9_OUTPUT_SCHEMA, Refusal, V2ReasonCode`
- source imports: `from . import _verbs_tombstone`; `remove_imports` (baseline = sequential): `abort_disposition_refusal` (the `_command_lock` import line keeps `_new_state`, `_prove_run_task_binding`, `_serialize_worktree_command`)
- size: destination **346** code lines; `_engine.py` after: **3241**
- census: none of the 10 sites names these methods → no repoint
- refusals: none (`DRY RUN: verified; no files written`)
- evidence: `$EVID/dryrun-tombstone.txt`
- verify: `bash $S/verify.sh --pkg scripts/forge/forge_cli --snapshot .refactor/engine-c01-before.json --manifest .refactor/engine-tombstone.json --strict-bodies`

### c02 — `status`

- destination: `scripts/forge/forge_cli/engine/_verbs_status.py` — read-only/recovery surfaces: the journal verbs and `status`.
- methods (source order): `journal_batch_recover` (114–136), `journal_ingest_chain` (138–253), `status` (459–581, `_serialize_worktree_command`)
- why: the two journal verbs share `@state:ctx` and the `chain_core`/`runtime` coordination seam with nothing else; `status` is the only other verb without a state transition. `status` calls `self._require_tombstone_control`/`self._tombstone_outcome` (c01 bindings), `self._record_head_moved` (stays), `self._recover_committing`/`self._release_lock` (real methods until c09, bindings after) — second cluster on purpose so the first cross-cluster `self.` calls go through the gate early.
- dry run: `python3 $D/move_methods.py --project . --source scripts/forge/forge_cli/engine/_engine.py --dest scripts/forge/forge_cli/engine/_verbs_status.py --class Engine --methods journal_batch_recover,journal_ingest_chain,status --import-root scripts/forge --shape function --format-imports --manifest .refactor/engine-status.json` (+ `--apply`)
- bindings:
  ```
  journal_batch_recover = _verbs_status.journal_batch_recover
  journal_ingest_chain = _verbs_status.journal_ingest_chain
  status = _serialize_worktree_command(_verbs_status.status)
  ```
- destination imports: `from __future__ import annotations`; `from forge_cli import chain_core, runtime`; `from forge_cli.engine._approval import _success as _success`; `from forge_cli.engine._candidate_ops import _adopt_out_of_band_candidate as _adopt_out_of_band_candidate`; `from forge_cli.engine._core import _run_halt as _run_halt`; `from forge_cli.engine._finalize import FinalizeContext as FinalizeContext, FINALIZE_CHECKS as FINALIZE_CHECKS`; `from forge_cli.engine._journal import _read_ingest_sources as _read_ingest_sources, _install_ingest_sources as _install_ingest_sources`; `from forge_cli.engine._state import TERMINAL_STATES as TERMINAL_STATES`; `from forge_cli.envelope import FrozenError, Outcome, REVISION9_OUTPUT_SCHEMA, ReasonCode, Refusal, V2ReasonCode`
- source imports: `from . import _verbs_status`; `remove_imports` (baseline = sequential): `_install_ingest_sources`, `_read_ingest_sources` (whole `_journal` import line goes)
- size: destination **275**; `_engine.py` after: **2988**
- census: none → no repoint
- refusals: none. evidence: `$EVID/dryrun-status.txt`
- verify: `... --snapshot .refactor/engine-c02-before.json --manifest .refactor/engine-status.json --strict-bodies`

### c03 — `lifecycle`

- destination: `scripts/forge/forge_cli/engine/_verbs_lifecycle.py` — chain creation and candidate re-staging: `start`, `classify`, `restage`, `rebase`.
- methods (source order): `_live_chain` (318–322), `start` (618–751, `_serialize_worktree_command`), `classify` (754–785, `_serialize_worktree_command`), `restage` (788–875, `_serialize_worktree_command`), `rebase` (1176–1322, `_serialize_worktree_command`)
- why: `_live_chain` is called only by `start` → travels. `classify`/`restage`/`rebase` share the `_run_classification`/`_stage_paths`/`_archive_metadata` candidate-mutation seam with `start`. Not merged with `abort` (c01): 429 + 266 > 500.
- dry run: `python3 $D/move_methods.py --project . --source scripts/forge/forge_cli/engine/_engine.py --dest scripts/forge/forge_cli/engine/_verbs_lifecycle.py --class Engine --methods _live_chain,start,classify,restage,rebase --import-root scripts/forge --shape function --format-imports --manifest .refactor/engine-lifecycle.json` (+ `--apply`)
- bindings:
  ```
  _live_chain = _verbs_lifecycle._live_chain
  start = _serialize_worktree_command(_verbs_lifecycle.start)
  classify = _serialize_worktree_command(_verbs_lifecycle.classify)
  restage = _serialize_worktree_command(_verbs_lifecycle.restage)
  rebase = _serialize_worktree_command(_verbs_lifecycle.rebase)
  ```
- destination imports: `from __future__ import annotations`; `import copy`; `from typing import Any, Sequence`; `from forge_cli import chain_core`; `from forge_cli.engine._approval import _success as _success, _authorization_problem as _authorization_problem`; `from forge_cli.engine._archive import _prepare_archive_candidate as _prepare_archive_candidate, _archive_recheck as _archive_recheck`; `from forge_cli.engine._candidate_ops import _invalidate_candidate_evidence as _invalidate_candidate_evidence, _stage_paths as _stage_paths`; `from forge_cli.engine._classification import _run_classification as _run_classification`; `from forge_cli.engine._command_lock import _new_state as _new_state, _prove_run_task_binding as _prove_run_task_binding`; `from forge_cli.engine._core import chain_id_now as chain_id_now, _transition_state as _transition_state, _archive_contamination_refusal as _archive_contamination_refusal, _archive_metadata as _archive_metadata, _run_halt as _run_halt`; `from forge_cli.engine._state import TERMINAL_STATES as TERMINAL_STATES`; `from forge_cli.envelope import FrozenError, Outcome, REVISION9_OUTPUT_SCHEMA, ReasonCode, Refusal, V2ReasonCode`; `from forge_cli.policy import PolicyError, parse_policy, sha256_bytes`
- source imports: `from . import _verbs_lifecycle`; `remove_imports` (baseline = sequential): `PolicyError`, `Sequence`, `_archive_contamination_refusal`, `_new_state`, `_prepare_archive_candidate`, `_prove_run_task_binding`, `_stage_paths`, `chain_id_now`, `parse_policy`
- size: destination **429**; `_engine.py` after: **2591**
- census: none → no repoint. Note `_serialize_worktree_command` reads `method.__name__` (`_command_lock.py:313,319,332`: `create_run_lock = method.__name__ == "start"`); the moved function is still named `start` (simulation: `Engine.start.__wrapped__.__name__ == 'start'`).
- refusals: none. evidence: `$EVID/dryrun-lifecycle.txt`
- verify: `... --snapshot .refactor/engine-c03-before.json --manifest .refactor/engine-lifecycle.json --strict-bodies`

### c04 — `gate`

- destination: `scripts/forge/forge_cli/engine/_verbs_gate.py` — gate execution: `gate_run`, its two private helpers, and `scan_secrets` (which `gate_run` calls).
- methods (source order): `_pending_mutating_gate` (1324–1328), `_resolve_gate` (1330–1401), `gate_run` (1767–2045, `_serialize_worktree_command`), `scan_secrets` (2048–2127, `_serialize_worktree_command`)
- why: `_pending_mutating_gate`/`_resolve_gate` are called only by `gate_run`. `_run_fresh_reviewer_evals` (also called only by `gate_run`) is **deliberately not** here: 458 + 351 = 809 would put the module between target and ceiling (baseline entry + debt row) for no cohesion gain — it is the largest tier-2 candidate and gets its own module (c05); `gate_run` reaches it as `self._run_fresh_reviewer_evals(...)`. `verify` (calls `self.gate_run`) goes to c06 for the same size reason.
- dry run: `python3 $D/move_methods.py --project . --source scripts/forge/forge_cli/engine/_engine.py --dest scripts/forge/forge_cli/engine/_verbs_gate.py --class Engine --methods _pending_mutating_gate,_resolve_gate,gate_run,scan_secrets --import-root scripts/forge --shape function --format-imports --manifest .refactor/engine-gate.json` (+ `--apply`)
- bindings:
  ```
  _pending_mutating_gate = _verbs_gate._pending_mutating_gate
  _resolve_gate = _verbs_gate._resolve_gate
  gate_run = _serialize_worktree_command(_verbs_gate.gate_run)
  scan_secrets = _serialize_worktree_command(_verbs_gate.scan_secrets)
  ```
- destination imports: `from __future__ import annotations`; `import hashlib`; `import os`; `import secrets`; `import sys`; `import time`; `from typing import Any, Mapping, MutableMapping`; `from forge_cli import candidate as candidate_module, chain_core, fresh_evals as fresh_eval_module, runtime`; `from forge_cli.engine._approval import _success as _success`; `from forge_cli.engine._candidate_ops import _invalidate_candidate_evidence as _invalidate_candidate_evidence, _candidate_snapshot as _candidate_snapshot, _install_candidate_snapshot as _install_candidate_snapshot, _candidate_review_diff as _candidate_review_diff, _adopt_out_of_band_candidate as _adopt_out_of_band_candidate`; `from forge_cli.engine._classification import _run_classification as _run_classification`; `from forge_cli.engine._core import _transition_state as _transition_state, _archive_metadata as _archive_metadata, _evidence_record as _evidence_record, _record_process_step as _record_process_step`; `from forge_cli.engine._gate_checks import _current_test_paths as _current_test_paths, _void_mismatched_gate_one_pair as _void_mismatched_gate_one_pair, scan_added_secrets as scan_added_secrets`; `from forge_cli.envelope import FrozenError, Outcome, ReasonCode, Refusal, V2ReasonCode`; `from forge_cli.policy import sha256_bytes`
- source imports: `from . import _verbs_gate`; `remove_imports` baseline: `_candidate_snapshot`, `_current_test_paths`, `_evidence_record`, `_install_candidate_snapshot`, `_void_mismatched_gate_one_pair`, `hashlib`, `scan_added_secrets`; **sequential adds** `V2ReasonCode`, `_invalidate_candidate_evidence`, `_run_classification` (their other readers left in c01/c03)
- size: destination **458**; `_engine.py` after: **2169**
- census: `tests/test_revision9_cli_surfaces.py:5794` `inspect.getsource(CLI.Engine.gate_run)` — **no repoint**: `_serialize_worktree_command` uses `functools.wraps` (`_command_lock.py:310`), so the binding carries `__wrapped__`; `inspect.getsource` unwraps to the moved `_verbs_gate.gate_run` whose text still contains `environment.pop("FORGE_SESSION_PID", None)` (simulation probe: `True`). Today the test already reads through the same wrapper.
- refusals: none. evidence: `$EVID/dryrun-gate.txt`
- verify: `... --snapshot .refactor/engine-c04-before.json --manifest .refactor/engine-gate.json --strict-bodies`

### c05 — `gate_evals`

- destination: `scripts/forge/forge_cli/engine/_verbs_gate_evals.py` — the fresh-reviewer eval sub-step of `gate_run`.
- methods: `_run_fresh_reviewer_evals` (1403–1764)
- why: single-caller helper of `gate_run`, 362 lines, the largest tier-2 candidate; its own module keeps both gate modules under target and gives the later extraction a home. Disconnected from every other method except via `gate_run`.
- dry run: `python3 $D/move_methods.py --project . --source scripts/forge/forge_cli/engine/_engine.py --dest scripts/forge/forge_cli/engine/_verbs_gate_evals.py --class Engine --methods _run_fresh_reviewer_evals --import-root scripts/forge --shape function --format-imports --manifest .refactor/engine-gate_evals.json` (+ `--apply`)
- bindings: `_run_fresh_reviewer_evals = _verbs_gate_evals._run_fresh_reviewer_evals`
- destination imports: `from __future__ import annotations`; `import copy`; `import re`; `import secrets`; `import time`; `from typing import Any, Mapping, MutableMapping`; `from forge_cli import candidate as candidate_module, chain_core, fresh_evals as fresh_eval_module`; `from forge_cli.engine._approval import _success as _success`; `from forge_cli.engine._core import _fresh_eval_invalid_refusal as _fresh_eval_invalid_refusal`; `from forge_cli.engine._fresh_eval import _FreshEvalArtifactIO as _FreshEvalArtifactIO, _FreshEvalControlAbort as _FreshEvalControlAbort, _fresh_eval_evaluation as _fresh_eval_evaluation, _validated_fresh_reviewer_manifest as _validated_fresh_reviewer_manifest`; `from forge_cli.engine._fresh_eval_evidence import _record_fresh_eval_terminal as _record_fresh_eval_terminal`; `from forge_cli.engine._gate_checks import _next_incomplete as _next_incomplete`; `from forge_cli.engine._state import FRESH_REVIEWER_EVAL_REQUEST_SCHEMA as FRESH_REVIEWER_EVAL_REQUEST_SCHEMA`; `from forge_cli.envelope import FrozenError, Outcome, ReasonCode, Refusal`; `from forge_cli.policy import sha256_bytes`
- source imports: `from . import _verbs_gate_evals`; `remove_imports` baseline: `FRESH_REVIEWER_EVAL_REQUEST_SCHEMA`, `_FreshEvalArtifactIO`, `_FreshEvalControlAbort`, `_fresh_eval_evaluation`, `_record_fresh_eval_terminal`, `_validated_fresh_reviewer_manifest`; **sequential adds** `copy`, `time`
- size: destination **377**; `_engine.py` after: **1817**
- census: none → no repoint. refusals: none. evidence: `$EVID/dryrun-gate_evals.txt`
- verify: `... --snapshot .refactor/engine-c05-before.json --manifest .refactor/engine-gate_evals.json --strict-bodies`

### c06 — `decision`

- destination: `scripts/forge/forge_cli/engine/_verbs_decision.py` — verbs that advance the chain past a gate or review by issuing an authorization or recording a decision.
- methods (source order): `verify` (2130–2239), `review_disposition` (3064–3129), `approve` (3132–3179), `skip` (3182–3278) — all `_serialize_worktree_command`
- why: after hub peeling each is a singleton cluster (they share only `@state:ctx` and hub calls); the skill's rule against forcing disconnected methods together is satisfied by their shared state and shared hubs, and four 48–103-line singleton modules would defeat the module target. They share the authorization seam (`_issue_authorization`: `verify`, `approve`, `skip`; `_success`: all four) and are the post-gate/post-review transition verbs. `verify` calls `self.gate_run` (c04 binding).
- dry run: `python3 $D/move_methods.py --project . --source scripts/forge/forge_cli/engine/_engine.py --dest scripts/forge/forge_cli/engine/_verbs_decision.py --class Engine --methods verify,review_disposition,approve,skip --import-root scripts/forge --shape function --format-imports --manifest .refactor/engine-decision.json` (+ `--apply`)
- bindings:
  ```
  verify = _serialize_worktree_command(_verbs_decision.verify)
  review_disposition = _serialize_worktree_command(_verbs_decision.review_disposition)
  approve = _serialize_worktree_command(_verbs_decision.approve)
  skip = _serialize_worktree_command(_verbs_decision.skip)
  ```
- destination imports: `from __future__ import annotations`; `from forge_cli import chain_core, runtime`; `from forge_cli.engine._approval import _success as _success, _issue_authorization as _issue_authorization, _verify_operator_harness as _verify_operator_harness`; `from forge_cli.engine._classification import _classification_argv as _classification_argv, _classification_environment as _classification_environment`; `from forge_cli.engine._core import _transition_state as _transition_state, _record_process_step as _record_process_step`; `from forge_cli.engine._gate_checks import _fresh_reviewer_block_claimed as _fresh_reviewer_block_claimed, _mechanical_complete as _mechanical_complete, _next_incomplete as _next_incomplete`; `from forge_cli.envelope import FrozenError, Outcome, ReasonCode, Refusal`
- source imports: `from . import _verbs_decision`; `remove_imports` baseline: `_fresh_reviewer_block_claimed`, `_verify_operator_harness`; **sequential adds** `_next_incomplete`
- size: destination **327**; `_engine.py` after: **1508**
- census: none → no repoint. refusals: none. evidence: `$EVID/dryrun-decision.txt`
- verify: `... --snapshot .refactor/engine-c06-before.json --manifest .refactor/engine-decision.json --strict-bodies`

### c07 — `review_request`

- destination: `scripts/forge/forge_cli/engine/_verbs_review_request.py` — review package construction and reviewer launch.
- methods (source order): `_profiles_for_path` (2242–2274, `staticmethod`), `_review_package` (2276–2393), `review_request` (2396–2672, `_serialize_worktree_command`)
- why: `_review_package` is called only by `review_request`; `_profiles_for_path` only by `_review_package` (plus two external unbound calls, below).
- dry run: `python3 $D/move_methods.py --project . --source scripts/forge/forge_cli/engine/_engine.py --dest scripts/forge/forge_cli/engine/_verbs_review_request.py --class Engine --methods _profiles_for_path,_review_package,review_request --import-root scripts/forge --shape function --format-imports --manifest .refactor/engine-review_request.json` (+ `--apply`)
- bindings:
  ```
  _profiles_for_path = staticmethod(_verbs_review_request._profiles_for_path)
  _review_package = _verbs_review_request._review_package
  review_request = _serialize_worktree_command(_verbs_review_request.review_request)
  ```
- destination imports: `from __future__ import annotations`; `import os`; `import re`; `import secrets`; `import stat`; `import subprocess`; `import sys`; `from pathlib import Path`; `from typing import Any, Mapping`; `from forge_cli import chain_core, fresh_evals as fresh_eval_module`; `from forge_cli.engine._approval import _success as _success, _pid_is_running as _pid_is_running`; `from forge_cli.engine._candidate_ops import _candidate_review_diff as _candidate_review_diff`; `from forge_cli.engine._core import _write_artifact as _write_artifact, _fresh_eval_invalid_refusal as _fresh_eval_invalid_refusal`; `from forge_cli.engine._fresh_eval_evidence import _fresh_reviewer_evidence_package as _fresh_reviewer_evidence_package`; `from forge_cli.engine._gate_checks import _mechanical_complete as _mechanical_complete`; `from forge_cli.engine._review_transport import _review_package_is_oversized as _review_package_is_oversized, _review_master_window_count as _review_master_window_count, _review_master_transport as _review_master_transport, _review_master_pointer_prompt as _review_master_pointer_prompt`; `from forge_cli.engine._state import CODEX_EXECUTABLE as CODEX_EXECUTABLE, REVIEW_MASTER_WINDOW_BYTES as REVIEW_MASTER_WINDOW_BYTES, REVIEW_INSTRUCTION as REVIEW_INSTRUCTION, REVIEW_LAUNCHER_CODE as REVIEW_LAUNCHER_CODE`; `from forge_cli.envelope import Outcome, ReasonCode, Refusal`; `from forge_cli.policy import sha256_bytes`
- source imports: `from . import _verbs_review_request`; `remove_imports` baseline: `CODEX_EXECUTABLE`, `REVIEW_INSTRUCTION`, `REVIEW_LAUNCHER_CODE`, `REVIEW_MASTER_WINDOW_BYTES`, `_fresh_reviewer_evidence_package`, `_review_master_pointer_prompt`, `_review_master_transport`, `_review_master_window_count`, `_review_package_is_oversized`, `subprocess`; **sequential adds** `_candidate_review_diff`, `_fresh_eval_invalid_refusal`, `_mechanical_complete`, `fresh_eval_module`, `secrets`
- size: destination **458**; `_engine.py` after: **1083**
- census — **no repoint** at any site: `app/_merge_engine.py:3749` `engine.Engine._profiles_for_path(path)` and `tests/test_cli_chain.py:2736` `module.Engine._profiles_for_path('scripts/inspector.py')` are unbound calls on the class; `Engine.__dict__['_profiles_for_path']` is `staticmethod(<function>)`, whose class-level access yields the plain function exactly as the in-class `@staticmethod` did (simulation probe returns `['review-coding']`). `.codex-orchestrator/runs/.../head-guard/scripts/forge/forge_cli/app.py:4666` is frozen evidence (never edited; `ruff`/mypy exclude it).
- refusals: none. evidence: `$EVID/dryrun-review_request.txt`
- verify: `... --snapshot .refactor/engine-c07-before.json --manifest .refactor/engine-review_request.json --strict-bodies`

### c08 — `review_collect`

- destination: `scripts/forge/forge_cli/engine/_verbs_review_collect.py` — verdict intake: parse/apply helpers and the two collection verbs.
- methods (source order): `_parse_verdict` (2675–2709, `staticmethod`), `_apply_verdict` (2711–2791), `review_collect` (2794–2970, `_serialize_worktree_command`), `review_attach` (2973–3061, `_serialize_worktree_command`)
- why: both helpers are called by exactly these two verbs. Not merged with `review_disposition`/`approve` (c06): 398 + 114 > 500.
- dry run: `python3 $D/move_methods.py --project . --source scripts/forge/forge_cli/engine/_engine.py --dest scripts/forge/forge_cli/engine/_verbs_review_collect.py --class Engine --methods _parse_verdict,_apply_verdict,review_collect,review_attach --import-root scripts/forge --shape function --format-imports --manifest .refactor/engine-review_collect.json` (+ `--apply`)
- bindings:
  ```
  _parse_verdict = staticmethod(_verbs_review_collect._parse_verdict)
  _apply_verdict = _verbs_review_collect._apply_verdict
  review_collect = _serialize_worktree_command(_verbs_review_collect.review_collect)
  review_attach = _serialize_worktree_command(_verbs_review_collect.review_attach)
  ```
- destination imports: `from __future__ import annotations`; `import json`; `import os`; `import re`; `import stat`; `from pathlib import Path`; `from typing import Any, MutableMapping`; `from forge_cli import chain_core, runtime`; `from forge_cli.engine._approval import _success as _success, _issue_authorization as _issue_authorization, _pid_is_running as _pid_is_running`; `from forge_cli.engine._core import _transition_state as _transition_state, _write_artifact as _write_artifact, _read_bound_artifact as _read_bound_artifact`; `from forge_cli.envelope import Outcome, ReasonCode, Refusal`; `from forge_cli.policy import sha256_bytes`
- source imports: `from . import _verbs_review_collect`; `remove_imports` baseline: `_read_bound_artifact`, `json`; **sequential adds** `Path`, `_issue_authorization`, `_pid_is_running`, `_write_artifact`, `stat`
- size: destination **398**; `_engine.py` after: **700**
- census — **no repoint**: `app/_merge_engine.py:4052` `engine.Engine._parse_verdict(data, ...)` is an unbound call resolved through the `staticmethod` binding to the plain function (simulation: `inspect.isfunction(Engine._parse_verdict)` is `True`, module `forge_cli.engine._verbs_review_collect`); `.codex-orchestrator/.../app.py:4969` is frozen evidence.
- refusals: none. evidence: `$EVID/dryrun-review_collect.txt`
- verify: `... --snapshot .refactor/engine-c08-before.json --manifest .refactor/engine-review_collect.json --strict-bodies`

### c09 — `finalize`

- destination: `scripts/forge/forge_cli/engine/_verbs_finalize.py` — commit finalization and committing-state recovery.
- methods (source order): `finalize` (3315–3554, `_serialize_worktree_command`), `_release_lock` (3556–3571), `_recover_committing` (3573–3710)
- why: `_recover_committing` and `_release_lock` are called by `finalize` (here) and `status` (c02) → they travel with the cluster holding the primary verb; `status` reaches them via `self.`. Last on purpose: heaviest census exposure (`patch.object(CLI.Engine, 'finalize', ...)`) after eight gated precedents.
- dry run: `python3 $D/move_methods.py --project . --source scripts/forge/forge_cli/engine/_engine.py --dest scripts/forge/forge_cli/engine/_verbs_finalize.py --class Engine --methods finalize,_release_lock,_recover_committing --import-root scripts/forge --shape function --format-imports --manifest .refactor/engine-finalize.json` (+ `--apply`)
- bindings:
  ```
  finalize = _serialize_worktree_command(_verbs_finalize.finalize)
  _release_lock = _verbs_finalize._release_lock
  _recover_committing = _verbs_finalize._recover_committing
  ```
- destination imports: `from __future__ import annotations`; `import os`; `import re`; `from typing import Any, MutableMapping`; `from forge_cli import chain_core, runtime`; `from forge_cli.engine._approval import _success as _success, _authorization_problem as _authorization_problem`; `from forge_cli.engine._archive import _archive_recheck as _archive_recheck`; `from forge_cli.engine._classification import _classification_argv as _classification_argv, _classification_environment as _classification_environment`; `from forge_cli.engine._core import commit_message_bytes as commit_message_bytes, _transition_state as _transition_state, _record_process_step as _record_process_step`; `from forge_cli.engine._finalize import FinalizeContext as FinalizeContext, PRODUCED_COMMIT_CHECKS as PRODUCED_COMMIT_CHECKS, _record_produced_identity as _record_produced_identity, _produced_mismatch_outcome as _produced_mismatch_outcome, FINALIZE_CHECKS as FINALIZE_CHECKS`; `from forge_cli.envelope import FrozenError, Outcome, ReasonCode, Refusal`; `from forge_cli.policy import sha256_bytes`
- source imports: `from . import _verbs_finalize`; `remove_imports` baseline: `PRODUCED_COMMIT_CHECKS`, `_produced_mismatch_outcome`, `_record_produced_identity`, `commit_message_bytes`; **sequential adds** `FINALIZE_CHECKS`, `FinalizeContext`, `Outcome`, `_authorization_problem`, `_classification_argv`, `_classification_environment`, `_record_process_step`, `_success`, `_transition_state`, `os`, `re`, `sha256_bytes` (last readers of the whole engine helper surface leave here)
- size: destination **395**; `_engine.py` after: **324** (below the 500 target — finalize may delete the `.refactor-baseline.json:19` entry; not this plan's commit)
- census — **no repoint**: `tests/test_cli_chain_finalize.py:1667` `mock.patch.object(CLI.Engine, 'finalize', side_effect=refusal)` replaces the class attribute (now the `_serialize_worktree_command` wrapper bound in the class body) and restores it on exit; callers use `self.finalize(...)`/`engine.finalize(...)`, which resolve through the class attribute both ways (simulation probe: patched `is` mock, restored `__name__ == 'finalize'`). The three `_emit_decision` autospec patches target a method that stays.
- refusals: none. evidence: `$EVID/dryrun-finalize.txt`
- verify: `... --snapshot .refactor/engine-c09-before.json --manifest .refactor/engine-finalize.json --strict-bodies`

### Wave close (after c09; not a cluster)

- FR-230 byte pins: `engine/_engine.py` is an existing subject in
  `.forge/evals/tasks/fr230-phase3-4-v2.manifest.json` (line 112). Add the nine new subjects, then
  mint via `REFACTOR_MINT_CMD` (`verify.sh --mint`) before the digest tests — **do not run mint
  inside a cluster commit**:
  `scripts/forge/forge_cli/engine/_verbs_tombstone.py`, `_verbs_status.py`, `_verbs_lifecycle.py`,
  `_verbs_gate.py`, `_verbs_gate_evals.py`, `_verbs_decision.py`, `_verbs_review_request.py`,
  `_verbs_review_collect.py`, `_verbs_finalize.py` (all under `scripts/forge/forge_cli/engine/`).
- Import contract: `lint-imports` passes without edits (simulation: 5 kept / 0 broken — a layers
  contract ignores unlisted modules, and no `_verbs_*` module imports `_engine` or another
  `_verbs_*`). For documentation parity with the chain_core/app contracts, finalize should add one
  row to `forge_cli.engine layers` directly under `_engine`:
  `"_verbs_decision | _verbs_finalize | _verbs_gate | _verbs_gate_evals | _verbs_lifecycle | _verbs_review_collect | _verbs_review_request | _verbs_status | _verbs_tombstone"`
  (all nine import only rows below `_finalize | _merge_candidate_generation`; `_verbs_status` and
  `_verbs_finalize` import `_finalize`, so the row must sit above it — it does).
- `pyproject.toml` finalize: narrow the P0 glob into per-module entries (§4 table), delete the
  glob; drop `PLR0904` from the `_engine.py` entry (8 defs remain) and re-derive the rest from
  `ruff check`; delete `.refactor-baseline.json:19` (`_engine.py` = 324 < 500).
- Re-run the seeded inventory and `quality.py` on the final tree for the report.

## 4. Quality and debt report

Per resulting module (code lines as `check_file_length.py` counts them; simulation = baseline dry
run for every destination):

| module | code lines | vs target 500 / ceiling 1000 | functions over 150 (tier-2 candidates) | ruff codes the relocated bodies trip (finalize per-file-ignores entry) |
|---|---|---|---|---|
| `_engine.py` (after c09) | 324 | under target | — | re-derive; `PLR0904` no longer applies |
| `_verbs_tombstone.py` | 346 | under target | — | `C901`, `E501`, `UP035` |
| `_verbs_status.py` | 275 | under target | — | `C901`, `E501`, `PLR0911`, `PLR0912`, `PLR0913` |
| `_verbs_lifecycle.py` | 429 | under target | (`rebase` 147 — under target, watch) | `C901`, `E501`, `PLR0912`, `PLR0913`, `PLR0915`, `UP035` |
| `_verbs_gate.py` | 458 | under target | `gate_run` 279 | `C901`, `E501`, `PLR0912`, `PLR0915`, `UP035` |
| `_verbs_gate_evals.py` | 377 | under target | `_run_fresh_reviewer_evals` 362 | `B904`, `C901`, `PLR0912`, `PLR0915`, `UP035` |
| `_verbs_decision.py` | 327 | under target | — | `C901`, `E501`, `PLR0912` |
| `_verbs_review_request.py` | 458 | under target | `review_request` 277 | `C901`, `PLR0911`, `PLR0912`, `PLR0915`, `PLR1702`, `UP012`, `UP035` |
| `_verbs_review_collect.py` | 398 | under target | `review_collect` 177 | `C901`, `UP035` |
| `_verbs_finalize.py` | 395 | under target | `finalize` 240 | `C901`, `PLR0912`, `PLR0915`, `UP035` |

No module lands between target and ceiling → **no `.refactor-baseline.json` entry and no
`--debt` row is required for any new module**. `quality.py` on the simulated tree reports
`debt: false`, `over_ceiling: false` for all ten.

Tier-2 candidates (each: "tier 2 extract after tier 1, separate commit, bead forge-plugin-321p";
never in a cluster commit; `extract_ranges.py` against the *destination* module once c0N is merged):

1. `_verbs_gate_evals._run_fresh_reviewer_evals` — 362 lines (worst; also `B904`).
2. `_verbs_gate.gate_run` — 279 lines.
3. `_verbs_review_request.review_request` — 277 lines.
4. `_verbs_finalize.finalize` — 240 lines.
5. `_verbs_review_collect.review_collect` — 177 lines.
6. (`_verbs_lifecycle.rebase` — 147, under target; not a candidate, listed because it is 3 lines short.)

Class size: `Engine` has 41 defs today (over `class_target` 30 → reported as a class candidate
by `quality.py`). After the wave it has **8** `def`s and 33 bindings. `quality.py` counts
`sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) for n in node.body)` — only `def`
statements in the class body; `Assign` bindings are not counted — so the class drops to 8 and off
the candidate list (simulation `quality.py` output: `_engine.py` `candidates: []`). Parameter
counts are unchanged by relocation (`PLR0913` findings above are pre-existing, grandfathered).
Function lengths are unchanged by relocation (`quality.py` measures `end_lineno - lineno + 1` on
the same bodies).

## 5. Risks the critic must check

1. **P0 per-file-ignores glob vs CLAUDE.md "never add to that list".** Without it, c01's
   `verify.sh` ruff step fails on `C901`/`E501`/`UP035` in `_verbs_tombstone.py`. This is the
   relocated-code exception both prior splits used (plan-engine.md E2/finalize; chain_core
   narrowed per module). Check: the glob carries no code `_engine.py` does not already carry,
   omits `I001` and `PLR0904`, and finalize narrows it to the §4 table and deletes the glob.
2. **`remove_imports` is sequence-dependent.** The baseline dry runs (`$EVID/dryrun-*.txt`)
   under-report removals for c04–c09; the extractor's apply-time dry run is the manifest of record.
   Check each committed manifest's `remove_imports` against the "sequential adds" lists above; a
   *missing* removal would be an F401 in `_engine.py` — not ignored there — and fail ruff, so it is
   self-detecting; an *extra* removal would break a hub body and fail the focused tests.
3. **Reflection metadata changes** (`operations.md`: `__module__`/`__qualname__`/source location
   may change). `Engine.gate_run.__qualname__` becomes `gate_run`, `__wrapped__.__module__`
   becomes `forge_cli.engine._verbs_gate`. `grep -rn "__qualname__" scripts/forge` is empty;
   nothing pickles bound methods; `_serialize_worktree_command` keys on `method.__name__`
   (unchanged). Check no test asserts on `__module__`/`__qualname__` of `Engine` methods
   (`grep -rn "__qualname__\|__module__" tests/test_cli_chain*.py tests/test_revision9_cli_surfaces.py`).
4. **`patch_engine` coverage.** `tests/_cli_loader.py:_PackagePatch` patches the root and every
   submodule from `pkgutil.iter_modules(root.__path__)` that binds the name — new `_verbs_*`
   modules are enumerated automatically, and each imports its controls by value like `_engine.py`
   does today. Check `tests.test_cli_loader` (in the focused set) passes at every cluster.
5. **Type ratchet keyed by (code, message), not file.** Five grandfathered `_engine.py` entries
   (`_engine.py:1638,1643,1867,2536,3700`) move to `_verbs_gate`/`_verbs_gate_evals`/
   `_verbs_review_collect`/`_verbs_finalize` with the same messages. Simulation: no new keys. If
   the gate shows `import-untyped codex_orchestrator` ×3, the gate environment above was not applied — a FAIL step is a failed gate; rerun with the environment, not a
   move (identical on the untouched tree); do not "fix" it in a cluster commit.
6. **Census not complete by design.** `class_inventory` reports `census_complete: false` because
   dynamic lookups (`getattr`, string-built names) are not resolved. All 10 reported sites are
   dispositioned in §3 with no repoint; the two `.codex-orchestrator` copies are frozen evidence.
   Check the dispositions against the simulation probes, not against the plan's prose.
7. **Body-verbatim proof.** `--strict-bodies` + manifest oracle. Comments/blank lines are preserved
   by LibCST but not proven by the AST oracle; docstrings are. Check `git diff` of each cluster
   shows only: deleted `def`s in the class, inserted bindings at the same positions, one
   `from . import _verbs_<x>` line, import-line shrinkage in `_engine.py`, and the new file.
8. **`engine/__init__.py` `__all__` byte-identical**; nothing re-exports `_verbs_*` (simulation:
   `'Engine' in __all__`, no `_verbs` name in `__all__`). `_finalize.py:7` and
   `_command_lock.py:9` keep their `TYPE_CHECKING` import of `Engine` from `_engine`; no
   `_verbs_*` module imports `_engine` (that would be a real cycle — check with
   `grep -n "_engine" scripts/forge/forge_cli/engine/_verbs_*.py` → empty).
9. **Binding placement.** The mover leaves each binding where the `def` was, so the class body
   interleaves real methods and bindings (`_engine.py` lines 26–30, 94, 229, 264–301, 336–338 in
   the simulation). Harmless for attribute lookup; `_serialize_worktree_command` is imported at
   module top before the class executes. Do not "tidy" the order in a tier-1 commit.
10. **`check_file_length` in `verify.sh`** is the skill's copy but reads `.refactor-baseline.json`
    from cwd by default (`--baseline` / `REFACTOR_BASELINE`), so the grandfathered `_engine.py`
    passes while shrinking (3574 → 3241 → … → 324). Run `verify.sh` from the repo root.
11. **Changelog gate**: every cluster commit (and P0) touches `*.py`/`*.toml` and needs a staged
    `## [Unreleased]` line; write it at that commit's start (memory: changelog rides into the live chain).

## 6. Test expectations

- Production function shape: **no test-ID mapping, no test snapshot, no `--test-only`**; the
  test surface is untouched. `collect_tests.py` is not part of this wave.
- Focused per-cluster command (already exported as `REFACTOR_TEST_CMD`):
  `python3 -m unittest tests.test_cli_chain tests.test_cli_chain_finalize tests.test_revision9_cli_surfaces tests.test_cli_loader`
  — unchanged for all nine clusters; expected result identical to baseline (same count, OK).
  Sequential-simulation result of that exact command on the nine-cluster tree:
  `Ran 199 tests in 207.451s` / `OK` (exit 0) — identical count to the 199 the baseline tree collects (`unittest.defaultTestLoader.loadTestsFromNames(...)` on the untouched project). Log: `<sim>/.refactor/focused-tests.log`.
- Digest / byte-pin tests (FR-230 subjects, `test_repo_conformance` inventory) run **only at wave
  close** after `verify.sh --mint` adds and mints the nine new subjects; they are expected to fail
  between c01 and the mint and must stay out of the per-cluster command.
- Full unittest discovery (project Gate 1 cell) at wave close and at finalize, twice after the last fix.
