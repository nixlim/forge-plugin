# Changelog

All notable changes to the Forge plugin are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Release dates are the UTC dates of the release commits.

## [Unreleased]

### Changed

- Specification Revision 15 defines the deferred per-clone routes file, eight provider/role profiles, headless review-final lane, route/task provenance, and mirrored routing trigger policy; every new FR/DM retains its chain-specific implementation-deferral marker.
- Refactor (tests): `tests/test_revision8_coordination.py` (4,905 code lines, one class `Revision8CoordinationTests` with 112 methods) is decomposed with the refactor-python `decompose` skill (0.1.3) in test shape (bead forge-plugin-25ms, plan `.refactor/plan-revision8.md`): the 31 helpers move verbatim into the support mixin `tests/_revision8_support.py` (539 code lines) and the 81 tests into seven scenario modules in class shape, `tests/test_revision8_{orphan_identity 809, append_schema 712, registry_races 618, precedence 609, rollback 583, interruptions 566, successors 533}.py`, each class inheriting the mixin, with both collectors' test IDs mapped 1:1 (`.refactor/idmap-revision8-*.json`); the source keeps a docstring-only shell that collects no test. One hand-written preparation commit precedes the moves (the preamble constants `ROOT`, `TOOLS`, `RECORDED_AT` relocated verbatim into `tests/_revision8_constants.py`, which also carries the `sys.path` bootstrap so every new module imports standalone without `PYTHONPATH`), and every mover call passes `--import-root "$PWD"` so the generated imports read `from tests._revision8_...` (the plugin's default writes a bare module name the Gate 1 cell cannot import). Two operator-ruled config changes ride with it: `pyproject.toml` gains `[tool.ruff.lint.isort] known-local-folder` for the `scripts/`-resident packages (`codex_orchestrator`, `codex_orch_tools`, `forge_cli`, `commitment_paths`), so a generated header imports the bootstrapping constants module before them (zero new isort findings repository-wide), and `tests/test_migration.py`'s legacy-runtime-name scan carves out `.refactor/` (the tracked test-tree snapshots carry that test's own name; evidence shipping is bead forge-plugin-xlt7). The temporary ruff globs are replaced by measured per-module entries and the eight new modules are pinned in `.refactor-baseline.json` at their measured sizes; no production file changed, no mint. At reintegration the isort ruling re-sorts one import block in `tests/test_vocab_readers.py` (added by 0.6.13 after the split was measured); that is the only file outside the split the branch edits. Follow-up: forge-plugin-7pzp (split the mixin by role; decide the empty shell).
- Refactor (tests): the `Revision9BuilderBatchTests` class in `tests/test_revision9_coordination.py` (13,222 code lines; 147 methods, 109 tests) is decomposed with the refactor-python `decompose` skill (0.1.3) in class shape (bead forge-plugin-6g67, plan `.refactor/plan-revision9-coord.md`): 18 helpers shared by two or more scenario families move verbatim to the mixin `Revision9BuilderBatchSupport` in `tests/_revision9_coord_support.py` (806 code lines) and 108 tests plus 20 family-private helpers move verbatim (LibCST mover, manifest-verified AST oracle, `--strict-bodies`, one commit per family, test IDs mapped 1:1 in both collectors) to twelve sibling modules `tests/test_revision9_coordination_<family>.py` — cli_diagnostics 230, batch_builder 576, scope_change 521, gap_repair 760, staging_crashes 536, chain_drain 424, terminal_builder 655, legacy_activation 896, receipted_chain 799, activation_scan 618, activation_outbox 790, ledger_recovery 810 — whose classes inherit the mixin; the source keeps the other three classes and the one `unittest.skipUnless` test the mover refuses (4,931 code lines; `Revision9BindingTests` and `Revision9MergeTransitionGrammarTests` are follow-up forge-plugin-z50i). Non-move commits: one hand-written preparation commit moves the module's preamble constants and `key()` verbatim to `tests/_revision9_coord_constants.py` (the plugin's rope mover cannot relocate `Path(__file__)`-derived constants); every mover call passes `--import-root "$PWD"` so destination imports read `from tests._revision9_coord_...` (the plugin's default writes a bare name the Gate 1 cell cannot import); `pyproject.toml` gains `[tool.ruff.lint.isort] known-local-folder` for the `scripts/` packages (operator ruling 2026-09-23) so a generated header imports the constants module, which puts `scripts/` on `sys.path`, before `codex_orchestrator`, and each new module imports standalone without `PYTHONPATH`; `tests/test_migration.py`'s legacy-runtime-name scan carves out `.refactor/` (operator ruling 2026-09-23; the tests-scoped evidence snapshots quote that test's own name); the temporary ruff globs for the new modules are replaced at finalize by measured per-module entries, the source entry shrinks to the six codes it still trips, and the size baseline pins the source and the eleven modules over 500 at their measured sizes. No body, docstring, decorator or assertion changed; no production file changed; no mint.

## [0.6.13] - 2026-09-23

### Changed

- Historical route readers now accept legacy and canonical role, provider, and event-source vocabulary through one shared normalizer.
- Refactor (app): the `MergeEngine` class in `scripts/forge/forge_cli/app/_merge_engine.py` (10,302 code lines, 93 methods) is decomposed with the refactor-python `decompose` skill (0.1.2) in function shape (bead forge-plugin-37fr): 86 method bodies move verbatim to 27 `app/_engine_*.py` seam modules and the class keeps same-named class-body bindings, so every `MergeEngine.<name>` attribute, patch target, verb, diagnostic and reason code is unchanged; the shell ends at 224 code lines. A second wave then extracts nine declared statement ranges (rope, oracle-checked) into three `app/_engine_*_steps.py` siblings and in-module helpers. Four config/type prep commits precede the moves (a temporary `app/_engine_*.py` ruff glob replaced at finalize by measured per-module entries; the `_recording_common_lock` return annotation corrected from `Iterable` to `Iterator`, type baseline 241 to 234; provisional size-baseline entries for the three single-method modules over 500, pinned at finalize to 830/584/578), and one mechanical non-move commit unquotes the mover's string receiver annotations. Consequences for reflection, none of which the repository reads: moved functions report `__module__` under their seam module and lose the `MergeEngine.` `__qualname__` prefix (plain moved functions still pickle by their new qualified name; the one new pickling failure is the `contextlib.contextmanager(...)` wrapper bound as `_recording_common_lock`, 2 of 93 attributes failing at the tip against 1, the `store` property, at baseline), and `typing.get_type_hints()` raises `NameError` on the 75 moved instance/class methods because their receiver annotation names `MergeEngine`, which the seam modules import only under `TYPE_CHECKING`. The 30 new modules are FR-230 production subjects (manifest, fixtures and byte pin re-minted); `app/__init__.py` and `__all__` are byte-identical; no test edits. Follow-ups: forge-plugin-c4l4 (remaining tier-2 ranges), forge-plugin-g8kf (closure state object).
- Refactor (engine): the `Engine` class in `scripts/forge/forge_cli/engine/_engine.py` (3,574 code lines, 41 methods) is decomposed with the refactor-python `decompose` skill in function shape (bead forge-plugin-321p, plan `.refactor/plan-engine-class.md`): 33 verb-method bodies move verbatim (LibCST, manifest-verified AST oracle, `--strict-bodies`, one tier-1 cluster per commit) into nine modules — `_verbs_tombstone.py` (346 code lines), `_verbs_status.py` (275), `_verbs_lifecycle.py` (429), `_verbs_gate.py` (458), `_verbs_gate_evals.py` (377), `_verbs_decision.py` (327), `_verbs_review_request.py` (458), `_verbs_review_collect.py` (398), `_verbs_finalize.py` (395) — and `_engine.py` keeps the class shell (324 code lines: `__init__`, the hubs `select`, `_preflight`, `_wrong_state`, `next_step`, `_emit_decision`, the two helpers they call, and one `name = _verbs_<x>.name` binding per moved method, re-wrapped with `staticmethod` or `_serialize_worktree_command` exactly as before), so `Engine.<verb>` lookups, unbound `Engine._profiles_for_path`/`_parse_verdict` calls, `patch.object(Engine, ...)` and `inspect.getsource(Engine.gate_run)` are unchanged; no body, verb, diagnostic or reason-code byte changes; the engine package root and its `__all__` are byte-identical. The nine modules are FR-230 production subjects (re-minted); `pyproject.toml` gains one measured ruff per-file-ignores entry per verb module (the temporary `_verbs_*.py` glob that carried `_engine.py`'s grandfathered codes during the moves is gone), the `_engine.py` entry shrinks to the five codes it still trips, a `forge_cli.engine layers` row places the verb modules under `_engine`, the `_engine.py` size-baseline entry (3574) is deleted, and the mypy ratchet drops 251 -> 241 (ten grandfathered checks inside moved bodies no longer fire because a moved function's `self` is untyped; tracked as debt with a follow-up bead).
- Refactor: `scripts/forge/forge_cli/app.py` (11,524 lines) becomes the `forge_cli.app` package — a root `__init__.py` with the verbatim `__all__` and re-exports plus five submodules moved by rope under the AST body oracle (bead forge-plugin-hcuo, plan `.refactor/plan-app.md`): `_mutation_journal.py`, `_admission.py`, `_candidate_observation.py`, `_merge_engine.py` (the `MergeEngine` class, the one new over-budget size-baseline entry at its measured count under the operator ruling on that bead; its class split is a follow-up) and `_dispatch.py`. One non-move edit rides with it: tests patch app-layer controls through one `patch_app` loader helper (E0; the loader sweep rejects raw module patches on app aliases). No body, verb, diagnostic, reason code or `--help` byte changes; the spec's package sentence, the FR-230 production subjects (re-minted), per-module ruff ignores and a `forge_cli.app layers` import-linter contract follow.
- Refactor: `scripts/forge/forge_cli/engine.py` (12,178 lines) becomes the `forge_cli.engine` package — a root `__init__.py` with the verbatim `__all__` and re-exports plus 29 submodules moved by rope under the AST body oracle (bead forge-plugin-2fc, plan `.refactor/plan-engine.md`). Two non-move edits ride with it: the merge bootstrap child resolves `scripts/forge/cli.py` from `runtime.py`'s location instead of its own file depth (E1, with a focused test), and tests patch engine controls through one `patch_engine` loader helper (E0; the hermetic chain fixture assigns the codex executable on every engine module that binds it). The reviewer-facing eval trigger table names `scripts/forge/forge_cli/engine/**` in place of `engine.py` in the spec, the policy constant, the rendered project files and the fixtures; the Revision-9 seam-marker loop moves from the `chain_core` package root to `_commit_chain.py` beside `register_coordination_seams` (bead forge-plugin-4j7, finding CON-02; its grandfathered size entry rises 1840 -> 1847 by operator direction of 2026-09-17); the FR-230 production subjects are the engine package files, re-minted; the size baseline is re-pinned at measured sizes (`engine/_engine.py`, the `Engine` class, is the one new over-budget entry), the ruff per-file ignores are narrowed per engine module, and an import-linter layers contract locks the package's wave order.
- Test isolation (beads forge-plugin-0eq, forge-plugin-ehn): `tests/test_audit_commitments.py` writes its disabled-control mutants of `audit-commitments.py` under a private temp directory (pinning the script's plugin root) instead of beside the real script, so a parallel Gate 1 shard copying the tracked `scripts/` tree no longer races on a vanishing sibling; `tests/test_mutation_runner.py` sets `FORGE_SESSION_PID` to the test process for the runner child instead of inheriting the caller's value, so an exported session identity no longer fails ten tests with a foreign-live-owner refusal.
- chain_core split follow-ups (bead forge-plugin-r0b; review-final findings at reintegration): `scripts/forge/forge_cli/chain_core/_state.py` declares its constants in the historical module order again (bodies unchanged; FR-230 manifest, result fixtures and the v2 byte pin re-minted for the changed production subject); the spec's package sentence names the submodules by the FR-230 manifest's production-subject list instead of the planning document; `pyproject.toml` per-file-ignores drop the dead `chain_core.py` entry and the blanket `chain_core/**` glob in favour of one entry per submodule listing only the codes it trips, and `scripts/check_file_length.py` is cleaned to the full rule set (its entry removed) and gains a focused unittest (`tests/test_check_file_length.py`: hook and plain-mode exit codes, the exact guard diagnostic, and an in-memory control-disable leg); `import-linter==2.15` is pinned beside ruff in the guardrails workflow and the pre-commit setup line. Disclosure: the 0.6.12 reintegration's `.claude/settings.json` also carries `worktree.baseRef: head` and `enabledPlugins: codex-orchestrator@codex-orchestrator` (operator-approved at Gate 4 on 2026-09-14; the plugin entry dangles on a clone without that marketplace). Deferred to the `_commit_chain` split (bead forge-plugin-4j7): moving the Revision-9 seam-marker loop out of the package root, because the grandfathered `_commit_chain.py` may not grow.
- Reviewer-facing eval fixture `review-passes-clean-change` is brought up to the conventions it claims to follow (first fresh-reviewer-evals run since the chain_core split's guardrails landed): its test imports are in the order the ruff I001 gate requires and its diff carries the `CHANGELOG.md` entry the changelog policy requires for added Python files; expected verdict unchanged (PASS). Landed as its own commit because a candidate may not rewrite an established fixture that judges it (bead forge-plugin-r0b).
- Refactor (chain_core): `scripts/forge/forge_cli/chain_core.py` (about 19,300 code lines) is now the package `scripts/forge/forge_cli/chain_core/`: 45 submodules hold the 315 moved symbols with every function and class body unchanged (strict AST oracle 881/881), and the root `__init__.py` keeps the verbatim `__all__` and re-exports every symbol the module defined, so `forge_cli.chain_core.<name>` and the CLI shim's forwarding are unchanged. Unused imports are no longer bound on the package root; test patches of moved controls go through `tests/_cli_loader.patch_chain_core`, which patches every submodule binding the name. The spec's package sentence, the size baseline (eight over-budget chain_core files recorded at measured size) and a `forge_cli.chain_core layers` import-linter contract follow (bead forge-plugin-deb; follow-ups in forge-plugin-r0b and forge-plugin-4j7).
- File categories: `*.js` now belongs to the `config` category (and the changelog gate's code-suffix list), so a tracked JavaScript file such as the chain_core split's Workflow script `.refactor/split-chain-core.workflow.js` matches a category and `tests.test_repo_conformance` file-category coverage passes (bead forge-plugin-g9i).
- Review evidence for the chain_core split is tracked under `.refactor/`: the Codex review transcripts (`codex-review.jsonl`, `codex-review-chain_core.jsonl`, thread `01a0a015-b9f3-7072-9abd-4d4a29f96082`) and their verdict summaries (`codex-review.md`, `codex-review-chain_core.md`), cited by the handback on bead forge-plugin-deb. Evidence only; no runtime surface changes.

### Deprecated

- Legacy route vocabulary on NEW journal `execution` records: 0.6.14 will refuse, with an exact diagnostic, `role` values other than `implementer | review-cheap | review-final | plan | monitoring` (legacy `implementation`, `implement`, `review`, `reviewer`), `provider` values other than `codex | claude` (legacy `codex-cli`; `openai` was never a mapped spelling and stays refused), `event_source` values other than `exec | claude` (legacy `codex`, `agent-tool`, and the literal `…/events.jsonl` path form), and `mode` values other than `headless | detached | subagent | teammate` (`orchestrator-inline` was never mapped and stays refused). Existing records are never rewritten and keep reading through the 0.6.13 map.

### Release notes

- 0.6.13 is the routing plan's vocabulary **readers** release (chain V1): `scripts/forge/route_vocab.py` gives every journal reader one legacy/canonical map for `role`, `provider` and `event_source`; writers are unchanged, so records written by 0.6.12 and by 0.6.13 read identically.
- Also ships (no behaviour change): the Engine and MergeEngine class decompositions, the app, chain_core and engine package splits, the chain_core split follow-ups and the reviewer-eval fixture repair — each itemised under Changed above.

## [0.6.12] - 2026-09-13

### Changed

- Run-bound commit chains no longer freeze at a multi-cell stack gate (GH#23). A stack-validations region with two or more fenced cells recorded one bound journal verification per cell while the replay validator required the whole batch, so `verify` returned `frozen-chain — carried binding fact is stale` after the first cell. The engine now emits one passed bound verification per completed batch, sourced from the final cell; a failed cell still records its failure immediately and stops the batch. Per-cell chain facts, the currentness predicate and non-run-bound chains are unchanged. FR-230 evidence re-minted.

## [0.6.11] - 2026-09-11

### Changed

- Stack-validations grammar legibility (bead forge-plugin-28y, GH#12(f), GH#19): a
  committed Stack Validations region that is present but holds no fenced shell cell
  (the prose shape `/forge:init` 0.6.x emitted) now refuses with its own literal naming
  the region and the required grammar instead of the sentinel's `not configured — run
  /forge:init`; the same literal surfaces on the fresh-reviewer-evals applicability
  reparse; `/forge:init` pins one fenced `bash`/`sh` cell per detected stack category
  and runs an isolated parser-only self-check with the same grammar so it cannot leave
  a prose region behind. Executable policy stays fenced; prose is not accepted. Spec:
  DM-003, FR-061, FR-080, refusal matrix. FR-230 evidence re-minted (policy and
  fresh-evals subjects).
- Legacy-run opening legibility (beads forge-plugin-khu, forge-plugin-2ev; GH#14/#18
  carve-out sharing GH#17's root): a `run-open --record-json` record that carries any
  caller-authored `writer_contract` now refuses before any repository access with one
  legible literal naming the typed `run-open` remedy (the shared activated-writer
  literal is unchanged at its other sites); a contract-less raw open still opens a
  legacy run and prints exactly one stderr notice that its first typed mutation will
  activate it in place; the spec's FR-019 and §8 `run-open` row name the typed form
  as canonical and the record-JSON form as legacy/migration-only, with the refusal in
  the matrix and the docs-contract inventory.
- Chain start on a lock-less legacy run (bead forge-plugin-ayk, review-final MINOR on
  the GH#17 chain): a run-bound `commit start` for a legacy run written by 0.6.10 (no
  `.journal-batch.lock`) refused with the frozen-chain divergence literal; the engine
  and chain store now validate the run, repository and owner with the existing
  predicates, create and acquire the stable batch lock, and revalidate under the
  batch → registry → journal order; nonexistent, foreign-owned or wrong-repository
  runs still refuse without creating a lock; read-only validators stay non-creating;
  run-bound `merge start` uses the same validated creation. The first chain-outbox
  drain then activates a never-typed legacy run in place through the Revision-14
  machinery (activation marker, receipt ledger at the journal origin), so verify,
  review, finalize and later typed mutations proceed; a refused drain leaves the
  chain, its events and the run journal byte-identical with no pending outbox; the
  activation-lineage scan keeps receipt and carried-binding authentication for
  commit-chain siblings. The legacy-open notice is emitted by the raw CLI surface
  only. FR-230 evidence re-minted (engine, chain-store and merge-adapter subjects).
- CI red at e7813cc (bead forge-plugin-eh2): the golden pre-fix wedge recovery test
  resolved the fixture's recorded host repository path through the terminal chain guard,
  so it errored on the GitHub runner where that path does not exist; the test now maps
  the archived chain authority to the restored temporary repository and fails loudly if
  the recorded host path is ever resolved. Fixture bytes and recovery assertions are
  unchanged.
- Mixed-mode journal wedge (bead forge-plugin-kk5, GH#17, GH#18; operator rulings:
  fix the bug with no new verb, and activate in place): a run opened in legacy mode
  and adopted by typed verbs is now ACTIVATED on its first typed use by an appended,
  authenticated `writer-contract-activated` decision written atomically with the
  adopting batch (allocated `decision-NN`, reserved resolution literal,
  `writer_contract`, `receipt_origin_size`/`receipt_origin_sha256`); both activation
  predicates recognise opening or decision activation; receipt-chain validation is
  anchored on the authenticated adoption origin; raw lifecycle writers (append,
  readmit, close, retire) share the first-use guard against a pending
  activation-bearing outbox; `journal batch-recover` repairs one interior
  N-record receipt gap with a single spanning repair receipt, reconciles a spent
  intent without re-applying it, activates a pre-fix legacy-adopted ledger, and
  accepts legacy-written gap records that carry no `run_id` — proven against a
  golden fixture written by the pre-fix code; retrospective ingest can be a legacy
  run's first typed use (shared decision-numbering projection); the scoped-mutation
  runner persists through the typed receipted writer with a deterministic
  idempotency key, never a raw fallback, with an advisory diagnostic on refusal,
  and the merge adapter passes owner identity to the runner while scrubbing it
  from the mutation child; the archive renderer and commitment audit classify
  adopted runs through the shared classifier and render the activation decision
  as lifecycle metadata; the workflow skill documents the typed `run-open` as
  canonical. The first-use reservation scan replays only chains bound to the
  current run, warns and skips unreplayable unrelated history, and byte-bounds
  every chain read (state 1 MiB, events 8 MiB, event-one 64 KiB); the raw
  lifecycle guard refuses only on a pending first-use intent or an
  activation-bearing outbox, so raw `run retire`/`run close` of an unactivated
  legacy run with a stale receipt ledger still work and retire → successor stays
  open; typed first use on such a run refuses with a new legible literal
  (`legacy receipt ledger does not reach journal EOF`) naming the remedy; global
  reconciliation no longer refuses unrelated `run-open` while an adopted run is
  mid-batch or torn. Spec: DM-001, DM-012, FR-011, FR-016, FR-019 (multi-record
  repair, stale-ledger refusal), FR-120, FR-142, §8, refusal matrix, SC-027
  (Revision 14). Disable-in-memory registries `WRITER_ACTIVATION_CONTROLS`,
  `BATCH_GAP_REPAIR_CONTROLS` (`legacy-record-membership`, `multi-record-gap`),
  `MUTATION_JOURNAL_CONTROLS`.
- Guard hook latency (bead forge-plugin-kc9, CI red at 18bbe01): the PreToolUse guard
  now resolves the committed guard-denied-commands rules before direct-invocation
  parsing and runs the Bash-accurate lexer only when denied rules exist, removing
  the per-segment lexing cost that pushed the 2,000-segment flood test past the
  10-second budget on slower CI runners. Hook outcomes, literals, precedence,
  the budget, and the configured-rule path are unchanged; new flood tests pin the
  filled-empty (zero lexer calls), configured (one call, match), and malformed
  (lexer-independent denial) policies.
- Fresh-reviewer events ceiling (first live fresh-evals run, this chain): the
  reviewer child's retained `events.jsonl` stream gets its own 8 MiB ceiling —
  live reviewers' search-command output routinely exceeded the old 64 KiB cap,
  killing judgments before the verdict was written — while `verdict.txt` and
  `completion.json` stay at 65,536 bytes and breach of any ceiling still
  terminates the process group fail-closed (spec FR-149 fresh-reviewer
  amendment + `fresh_evals.py`, with live-shaped regression tests).
- Guard denied-commands region (bead forge-plugin-x0h part 2, operator-requested):
  a new committed `guard-denied-commands` policy region lets the operator list
  additional command shapes the PreToolUse guard refuses outright — matched by
  prefix tokens against the parsed direct invocation under FR-149 committed
  sourcing, denying with `forge: operator-denied command — <reason>`; a
  malformed region fails closed, an absent region changes nothing, and the
  documented coverage is honestly the parser's direct-invocation scope
  (mistake prevention for cooperative agents, not tamper-proofing). The
  region-inventory sweep also fixed the drift checker and chain-test
  inventories and added the manifest entries missed earlier, including the
  reviewer-facing-eval-triggers line absent from `.forge-manifest`.
- Targeted fresh-execution evals (bead forge-plugin-7p4, external-review
  finding 5, operator option c): the recorded eval runner is honestly relabeled
  recorded-baseline integrity, and a new fresh-reviewer-evals chain gate runs
  real reviewer judgments on the nine review-role fixtures — in-session against
  a materialized copy of the exact candidate tree, compared by verdict, bound
  to the forge-commit-candidate/2 identity in a forge-fresh-reviewer-evals/1
  manifest under the chain directory — whenever the staged candidate matches
  the new committed reviewer-facing-eval-triggers policy region (a fixed
  plugin-owned table); trigger-region structural failures surface as the
  gate's INVALID exit-2 envelope, the TUI and orchestrator-oracle fixtures are
  explicitly dispositioned subject-specific-baseline-only, tests use a
  scripted-reviewer seam (no live model), and the bounded runner now kills and
  reaps the complete child process group on any post-launch exception.
- Immutable commit-candidate boundary (beads forge-plugin-w86 and forge-plugin-kmj,
  external-review findings 2 and 3): commit authorization now binds a
  `forge-commit-candidate/2` identity — a domain-separated SHA-256 over the
  repository object format and the `git write-tree` tree OID — with the intended
  parent and an exact message digest carried in commit intent; finalize verifies
  the produced commit's single parent, tree, and message BEFORE consuming
  authorization or recording a landing, freezing the chain fail-closed under the
  existing `frozen-chain` reason on mismatch, and crash recovery uses the same
  raw-object verifier. Staged-path enumeration, the review patch, and the secret
  scan render tree-to-tree from immutable objects under pinned, config-proof git
  invocation (gitlinks always visible), with bounded 16 MiB artifacts; the
  review-evidence diff keeps its own digest but is no longer authorization. The
  DM-006 marker gains a versioned five-line grammar (legacy markers are stale
  cleanup only, never authorization), all guard comparisons move to the
  authorization id with every public denial literal preserved, the journal
  accepts the `git-tree-candidate-v2` binding kind alongside readable historical
  bindings, and the replay grammar admits `commit_identity_checked`. Both
  external-review reproductions (pre-commit-hook index rewrite; ignoreSubmodules
  plus staged gitlink) are pinned as regression tests with disable-in-memory
  registries; spec amendment across DM-001/DM-006/DM-012/FR-210..223 including
  the deferred guard-breadth and reviewer-posture honesty wordings.
- Documentation honesty batch (external-review findings 1, 6, and 8; beads
  forge-plugin-x0h part 1, ryt, bfg, 9xb, x68): the README states the commit
  guard's real coverage (direct git invocations at the tool-use boundary,
  cooperative-agent assumption, wrappers intentionally out of scope); provider
  diversity is described as reducing correlated mistakes, not eliminating
  them; the binding Claude reviewer is described as instruction-bounded and
  execution-capable (deliberately keeping Bash for execution evidence) in
  contrast to the OS-sandboxed Codex first-pass reviewer; prose-contract tests
  and the release e2e are labeled as instruction-presence checks and scripted
  plumbing integration; platform claims are scoped to CI evidence; the
  standard MIT LICENSE is added per the operator's licensing decision and the
  README licence section fixed; stale README figures corrected; the AGENTS.md
  splice re-rendered byte-equal to committed policy; and the `docs` file
  category now classifies the root `LICENSE` file.
- Oversized review packages (bead forge-plugin-8lu, revision-10 FR-216/FR-170..174
  amendments): review packaging for commit, merge, and archive candidates now uses
  the single-master-package transport above a 786,432-byte threshold — the launch
  carries the authoritative package path, byte length, and lowercase SHA-256 with
  deterministic 65,536-byte window arithmetic instead of embedded bytes, the reader
  verifies identity and digest before the first and after the last window, and any
  mismatch refuses with the exact amendment literal; at or under the threshold the
  packaging is byte-identical to before, and the previous outright refusal for
  oversized merge packages upgrades to the same transport.
- CLI split phase 3 (bead forge-plugin-95e.4): the remaining 183 top-level
  names move verbatim into `scripts/forge/forge_cli/engine.py` (the commit-chain
  engine, parser construction, and helpers, including the journal-record-builder
  runtime binding) and `app.py` (`MergeEngine`, shared routing, argument parsing,
  dispatch, and main);
  `scripts/forge/cli.py` is now a 131-line forwarding shim, and the Revision-9
  seam-marker loop moves beside `register_coordination_seams` in
  `chain_core.py`. No verb, diagnostic, reason code, or `--help` byte changes.
- Gate 1 wall time (bead forge-plugin-pwy): the committed `gate1-test-command`
  cell now fans full unittest discovery out over `min(4, cpu)` shards inside the
  one `bash -c` cell, fail-closed on any failing shard, empty module set, or
  shard without a unittest summary, with per-shard output tails kept under the
  65,536-byte cap (tails sliced in bytes before decoding); the same 1,514 tests
  run in about 320 to 390 s instead of about 1,060 s on an eight-core host, and
  CI's gate-1 step runs the committed cell through the repository's FR-149
  runner (`forge_cli.runtime.run_bounded`: process group, output cap, 1,200 s
  bound), after its drift-check rerun had timed out at that bound on the
  slower runner. FR-149 gains a Revision-13 amendment authorising
  in-cell parallel workers under the cell's process group and output cap.
- CLI split phase 2b (bead forge-plugin-95e.3): the fenced process runner, the
  FR-235 common-lock arbiter and chain leases, chain and merge-chain storage,
  merge state and transition validation, and the ingest verifiers (288
  definitions) move verbatim into `scripts/forge/forge_cli/chain_core.py`; the
  shim reads them by attribute and forwards reads of those names, the
  journal-record builder stays in the shim and is bound onto a late-bound
  `forge_cli.runtime` seam that chain_core calls, the remaining test patch
  sites for `run_fenced_command` and the record builder target the canonical
  modules, and the FR-230 manifest subject set covers `chain_core.py`. The shim
  is now about 21k lines. No verb, diagnostic, reason code, or `--help` byte
  changes.
- CLI split phase 2a (bead forge-plugin-95e.3): `scripts/forge/forge_cli/runtime.py`
  is the one canonical module for the patchable controls (`utc_now`,
  `run_bounded`, `MERGE_LIFECYCLE_ACTIVE`, `REVISION9_STATE_CONTROLS`,
  `SCRIPT_DIR`/`PLUGIN_ROOT`, the coordination-module loader, and
  `_fast_mechanical_skips`); the shim reads them by attribute and forwards
  reads of those names, so a single `mock.patch.object(forge_cli.runtime, ...)`
  disables a control everywhere and the affected test patch sites now target
  that module. The FR-230 manifest subject set covers `runtime.py`. No verb,
  diagnostic, reason code, or `--help` byte changes.
- CLI split phase 1 (bead forge-plugin-95e.2): the response envelope (reason
  codes, `Refusal`, `FrozenError`, `Outcome`, output schemas) and the
  committed-policy parser move verbatim from `scripts/forge/cli.py` into the
  interpreter-loaded package `scripts/forge/forge_cli/` (`envelope.py`,
  `policy.py`); the shim re-imports every moved name by an explicit list so all
  module attributes, verbs, diagnostics, reason codes, and `--help` bytes are
  unchanged, and the policy-fence tests now patch the fence helpers on the
  canonical package module. The FR-230 phase-3 manifest's production subject
  set now covers the package modules beside `cli.py` and `commit-guard.sh`, so
  a change to a moved definition changes the subject candidate exactly as a
  shim edit does. The transition-table and ingest-verifier clusters stay in the
  shim for now: their closures reach patched controls and the coordination
  cache, so they move with the runtime module in later phases.
- CLI split phase 0 (bead forge-plugin-95e.1): every test module now loads
  `scripts/forge/cli.py` through one shared loader, `tests/_cli_loader.py`
  (`load_cli`, `load_script`, and the memoizing `load_cached`), with identical
  fresh-module semantics so per-module `mock.patch.object(CLI, ...)` isolation
  is unchanged; a loader contract test pins the shim path, the independent
  globals, and that no test module keeps a private loader. Spec §5 records
  `scripts/forge/forge_cli/` as the interpreter-loaded package the CLI is being
  split into, outside the executable-script inventory, with `cli.py` remaining
  the sole invoked entry point. No runtime behaviour changes.
- `/forge:worktree-merge` now takes its reintegration lock as FR-235's portable
  Git-common-dir arbiter through the Forge CLI wrapper `common-lock hold
  --owner-kind push --operation push`, waiting for the wrapper's readiness
  record before any rebase step and releasing with the exact `release` frame
  after the push; the skill-issued `flock --timeout 300` and `mkdir` mutex at
  `agent-rebase.lockdir` are retired because they diverged from, and collided
  with, the arbiter namespace every CLI merge and push entrant uses. The
  wrapper must not inherit the shell's release-pipe descriptor, the readiness
  wait ends as soon as the wrapper exits, every in-lock fenced command carries
  `8<&- 9>&-` so no child inherits the lock pipes, the post-push wrapper wait is
  bounded, the kernel `flock` layer is described by the wrapper's real predicate
  (Python's `fcntl.flock`, not the `flock` binary), a dead owner
  left by a killed holder is operator-cleared, and executable tests run the
  skill's exact fenced bytes against the wrapper (acquire/release, early exit,
  dead-owner refusal, and a descriptor disable proof). The init skill's lock
  report and the spec's macOS scenario now describe the arbiter instead of the
  retired `mkdir` fallback (spec revision 13 FR-062 amendment; bead
  forge-plugin-9qf.7, the slice-1 consumer cutover decision-02 of
  run-20260829-cli-phase3 deferred).

### Fixed

- FR-221 sentence shape restored (hotfix for the 41da640 amendment): the
  denial-literal sentence returns to the exact "with exactly `…(commit
  approve)` or `…(commit skip)` as the deny reason" phrasing that the phase-0
  contracts extractor pins against committed HEAD; the literals themselves
  never changed. The extractor reads HEAD by design, so the regression was
  invisible to every pre-commit gate and appeared only in post-landing CI.
- Bounded runner group termination (bead forge-plugin-8u4, external-review
  finding 4): `_kill_process_group` now proves process-group death — after
  SIGTERM and the full 0.25 s grace it probes the group and escalates SIGKILL
  to the group regardless of leader state, so a TERM-resistant descendant can
  no longer outlive a reported timeout; only ESRCH proves absence, existing
  fallbacks are preserved, and the regression is pinned by a real
  TERM-ignoring-descendant test with a disable-in-memory proof.
- Commitment audit, second matcher refinement (task-04 of the archive-unblockers
  run): a compound whose longest known-task-id prefix is a real task and whose
  tail is purely alphabetic ("task-09-bound" with task-09 known) resolves to the
  known id instead of failing the audit as an unresolved reference; unknown
  prefixes, digit-bearing tails, and partial-prefix forms stay flagged, with a
  disable-in-memory proof.
- Archive rendering of an operator-tombstoned chain (bead forge-plugin-cyg):
  when a journal-bound chain's artifacts are absent but a valid
  forge-chain-tombstone/1 record exists, the archive captures the tombstone's
  exact bytes as the chain's terminal artifact, renders bound records as
  explicitly not replay-authenticated with a `tombstoned_chain`
  non-authoritative discrepancy row, authenticates the tombstone-sourced
  chain-abort decision by carried-record equality, and keeps every fail-closed
  edge (missing or malformed tombstones refuse; real artifacts win; rerender
  determinism and the archive recheck cover the tombstone file) — with the
  Revision-13 spec amendment. Unblocks the run-20260829-cli-phase3 archive.
- Commitment audit (bead forge-plugin-a57, external-review follow-on): the
  unknown-task matcher treats a `task-<suffix>` compound in decision resolution
  prose as an unresolved reference only when the suffix begins with a digit, so
  ordinary English compounds ("task-binding", "task-level") no longer fail the
  audit closed and permanently block a run's archive; numeric references
  (`task-99`), known-id resolution, and the record task-field validation keep
  their fail-closed behavior, each pinned by new focused tests including a
  disable-in-memory proof.
- `commit abort-disposition --run-id <run> --chain-id <chain>` now dispositions
  an operator-tombstoned run-bound chain (a chain that froze and was sealed
  under Revision 11 without ever landing): it appends one `chain-abort`
  decision whose binding is sourced from the canonical tombstone digest and
  whose basis is the tombstone path, admitted on an already-terminal task and
  exempt from the terminal-task ordering, so the gate records the frozen chain
  drained are retired from FR-021 correlation and the run can close `passed`.
  The terminal guards authenticate that single decision against the tombstone
  and refuse a landing beside it, a second abort, or a candidate mismatch; every
  refusal appends nothing (spec revision 13 DM-001/FR-021/FR-210/FR-222 amendment;
  bead forge-plugin-11a).
- FR-021 journal-only correlation no longer refuses a `passed` close for a
  task whose chain drained gate sets for candidates it later restaged (any
  BLOCK-then-restage cycle): records bound to a superseded candidate are
  retired from the landing correlation and the precedence rule exactly as an
  abort retires a whole chain, the precedence rule scopes to the landed
  candidate's evidence, and a terminal execution result appended after its
  task's last landing for an execution recorded before that landing moves
  neither the run-level nor the per-task mutating boundary. Both rules are
  named controls (`superseded-candidate`, `post-landing-result`) with disable
  proofs; a landing followed by a different candidate on its own chain, an
  execution started after the landing, and records bound to a chain that
  neither landed, aborted with a decision, nor was superseded keep the
  refusals (spec revision 13 FR-021 amendment; bead forge-plugin-2mu).
- Retrospective chain abort disposition: `commit abort-disposition` on a
  run-bound chain that was aborted before revision 13 (its abort carried no
  decision) appends one `abort_disposition_recorded` self-event carrying the
  `chain-abort` decision through the ordinary outbox and receipt path, so the
  terminal guards, FR-021 correlation, and the archive see it exactly as a
  current abort; the verb refuses every other chain and any retry (spec
  revision 13, FR-210/FR-211/FR-222 amendments; bead forge-plugin-rtj).
- Journal validation: `validate` and the run-close validation now resolve a
  relative citation against the run directory first and the run's
  layout-derived repository root second, matching FR-017's append-time
  ordering, so gate evidence drained by run-bound chains (repository-relative
  `.forge/chains/…` paths) validates without a hand-made mirror, and the
  archive's pre-close recompute passes the real run's root into its temp
  mirror so a passed close stays archivable; absolute citations, symlink
  escapes, and citations absent from both roots keep the upstream diagnostic
  (spec revision 13, FR-011 amendment; bead forge-plugin-7t0).
- Commit guard: a leading shell assignment (`VAR=value python3
  scripts/forge/cli.py commit approve …`) no longer bypasses the operator-verb
  denial; the CLI invocation matcher skips assignment words before and after
  an `env` prefix like the git matcher does. The v1 corpus row that pinned
  the bypass is superseded, not edited, by the new `fr223-hook-argv/3`
  generation (twelve additive rows, one supersession member, eval fixture
  with a live-recorded baseline, v3 manifest), so v1 and v2 bytes stay
  immutable (spec revision 13, DM-016 and FR-221 amendments; bead
  forge-plugin-di8).
- Journal-visible chain abort: `commit abort` on a run-bound chain that
  holds a staged candidate and never landed now drains one `chain-abort`
  decision through the outbox, a fourth closed decision outcome. The terminal
  guard behind `journal task-finish` and `run-close` accepts an authenticated
  never-landed abort (new `abort-disposition` control with an in-memory
  disable) with at most one replay-exact abort decision, refuses a landing
  that cites an aborted chain, and `task-finish` inspects only the finishing
  task's chains, and `commit abort` refuses `closed` and `aborted` chains
  before any mutation so a landing is never rewritten and an abort is never
  retried. FR-021 journal-only correlation retires records bound to a
  chain with an abort decision and reports `terminal task '<task>' precedes
  a bound chain abort decision` when the task closes too early. Chains
  aborted before this release carry no decision and stay outside journal-only
  correlation until a retrospective path lands (spec revision 13; DM-001,
  FR-021, FR-210/FR-222 amendments; bead forge-plugin-437). The generation-1 `fr230-phase3-4-v2` manifest
  and its five result fixtures are re-bound to the changed `cli.py` subject.
- CI: the drift-check step wrote its summary into the checkout, so the
  worktree-clean check failed on every run; the summary now goes to the
  runner's temp directory and is uploaded from there (GH forge-plugin-76g).

### Added

- Phase-3 slice 7: the additive 41-member reason corpus, referenced 130-case
  hook matcher corpus, corpus-driven merge-approval and activation denials in
  `commit-guard.sh`, and the v2 byte-pin, hook, and manifest test modules.
- Commit guard fail-closed bounds: nested substitutions and case compounds
  reaching the 64-level bound, parsing plus per-action context resolution
  exceeding the 10-second budget, or any internal guard failure now deny on
  both channels with exit 2 instead of escaping as a traceback with a
  non-blocking exit; repository context, activation mode, and halt probes are
  memoized per distinct context; each bound has an in-memory disable test.
- Commit guard segmentation: a swallowed `case` compound can no longer hide
  the segments around it. Every command is also split raw with swallowing
  disabled and the union of actions and denials is enforced, so `case` words
  in quotes, comments, heredoc bodies, `${}`, `[[ ]]`, or `(( ))` never merge
  a raw push, commit, operator verb, or the halt check into an inert segment;
  case-arm bodies are visited once and case-word scans are linear, so
  alternating or wide case input stays fast.
- Phase-3 slice 7 evidence: the two planted-defect BLOCK eval baselines.
- Phase-3 slice 7 manifest: the generation-1 `fr230-phase3-4-v2` manifest and
  its five phase-3 PASS result fixtures under `tests/fixtures/fr230-results/`,
  bound to the reviewed `commit-guard.sh` subject candidate.
- Phase-3 slice 7 manifest rebind: the generation-1 manifest and its five
  result fixtures re-bound to the `commit-guard.sh` subject that carries the
  fail-closed parser bounds from review-final iteration 1.
- Phase-3 slice 7 manifest rebind (second): the manifest and fixtures
  re-bound to the guard subject that also carries the quoted-`case`
  segmentation fix and memoized resolution from review-final iteration 2.
- Phase-3 slice 7 manifest rebind (third): the manifest and fixtures
  re-bound to the guard subject that also carries the raw-split union and
  linear case-word scans from review-final iteration 3.
- Phase-3 slice 6 completes the merge inventory with real common-lock
  contention, fresh 300-second fence budgets, remote churn and destination-ref
  races, historical-attempt and safe-release recovery, serialized review
  edges, one shared hostile-path parser, and hermetic Revision-9 CI fixtures.
  The merge integration matrix is now split across
  `tests/test_cli_merge_integration.py` (shard 0) and two
  `tests/test_cli_merge_integration_shard<n>.py` siblings; full discovery
  runs all three, and a missing sibling refuses at load time.

## [0.6.10] - 2026-09-02

### Added

- Spec revision 12: one fenced composite performs fetch/name-status/full-patch
  when run-bound and fetch/full-patch when unbound, streaming patch bytes only
  into SHA-256 with no retained transcript; the sixteen-member scope-fetch
  sidecar /2 resolves DM-014/FR-236 for both modes. Also adds reservation-held
  surviving-fence clearing and loud explicit-recover-flag refusal outside owned
  conflict.
- Phase-3 slice 5: the dormant bounded-epoch merge finalize, recovery, cleanup,
  fenced gate execution, and Revision-12 composite bootstrap/run-scope proof
  engine, including one fenced fetch/name-status/full-patch process group,
  digest-streamed unbounded patch stdout, bound and unbound `/2` sidecars,
  reservation-held fence classification, loud conflict-recovery flags,
  observation-proven rebase recovery, contamination-safe conflict continuation,
  resumable scope sidecars, final-mode parking, push retry, and remote-tip carry.
- Spec revision 11: normative authority for the landed coordination fixes
  (replay history admission, operator tombstones, enumeration isolation, ingest
  evidence capture, typed readmission), the bounded receipts-ledger gap repair,
  the FR-236 per-operation publication budget, and the archive-mode changelog
  exemption.
- CI: a GitHub Actions workflow running the forge gates on pushes, pull
  requests, and a weekly schedule — full unittest discovery, routing/inventory
  conformance, STRICT evals, and the mechanical drift check in reduced-signal
  CI mode.
- Changelog gate configured in `forge-project.md`: code-class commits require a
  staged changelog entry; docs-class commits are exempt, and archive-only chains
  record a per-chain operator-directed skip until the auto-exemption ships.
- Phase-3 slice 4: the dormant merge verb lifecycle (start/refresh/verify/approve/
  abort/status) with atomic ownership publication and authenticated lineage.
- Phase-3 slice 3: merge candidate/admission, ordered gate, review, and run/task
  adapters (dormant; no `merge start` parser).
- Phase-3 slice 2: event-first chain-family routing and the DM-014 `MergeChainStore`
  with the nine-step transaction, replay repair, and frozen-chain isolation (dormant).
- Phase-3 slice 1: the FR-235 portable common-lock arbiter and `forge common-lock hold`
  long-lived wrapper with the FR-236 start-pipe fence (dormant).
- Spec revision 10: phase-3 authority adjudications — pending-phase-4 result bindings,
  epoch gate plans, post-fetch run-scope abort, normative v2/v4 layouts, the
  one-outstanding-disposition rule, and single-master-package oversized review.

### Fixed

- Engine policy reader (GH#12): `forge-project.md` fenced `bash`/`sh` cells may
  be uniformly indented (for example nested under a Markdown list item, as
  `/forge:init` has written them); the opening fence's exact indentation is
  stripped from every cell line so an indented cell is byte-identical to the
  same cell at column 0. A misaligned or mixed-indentation cell refuses with
  `forge: executable policy row malformed`; a CRLF closing fence now closes its
  cell. The cell reader is now a linear line scan with per-column closing-fence
  indexes instead of a lazy multi-line regex, so a policy full of unclosed
  openings parses in milliseconds rather than stalling for minutes.
  `forge --help` and `forge commit start --help` now list the global
  options (`--repo`, `--run-id`, `--chain-id`, `--json`, `--verbose`), state
  that `--run-id` requires `--task`, and note that `--task` is a verb option
  accepted only after `commit start`, `merge start`, or `journal ingest-chain`.
- Docs: `docs/updating-forge.md` documents plugin update mechanics and the
  pin-versus-track strategies for consumer repositories.
- Typed scope readmission now writes a contiguous batch receipt, and batch recovery can backfill one journal-proven historical receipt gap before clearing an exact landed intent.
- Commit-chain replay now preserves receipted history, isolates frozen chains, and supports explicit operator tombstones and frozen aborts.
- Commit-chain ingest now captures every cited evidence file into the run-relative content-addressed store.
- Activated runs now route scope readmission through the typed scope-change builder.
- Scope readmission preserves the current admitted set unless `--replace` is explicit, and containment refusals name escaped pathspecs.
- Run-bound changelog outputs declared by the pinned committed policy are treated as engine-injected gate paths in binding and ingest proofs.
- Revision-9 golden tests now skip with a stated reason on clean checkouts
  where the git-excluded origin-machine run journals cannot exist, instead of
  erroring (found by the CI candidate's binding review).

## [0.6.9] - 2026-08-29

### Added

- Archive/journal fidelity line: structured `forge-gate-binding/1` verdict bindings,
  chain-evidence embedding in run archives, typed journal builder verbs, batch
  intent/receipt crash recovery, run/task-bound chains with a receipted outbox, and
  the sixteen-proof retrospective `journal ingest-chain`.
- Spec revision 9 and the reason-codes/3 corpus (53 members) with its eval fixture.

### Fixed

- Operator-agent GitHub issues #5 (multi-session legacy journal tolerance, on the
  reporter's committed fixture) and #6.
- Gate-child environment scrub for `FORGE_SESSION_PID` across every stack cell.
- Archive renderer authority ordering and committed-archive preview.
- Legacy pre-revision-9 chain key-set tolerance.

## [0.6.8] - 2026-08-26

### Added

- Coordination hardening: successor-DAG retired-scope lifecycle, orphan
  classification, FR-019 append-time record schema, DM-010 stable live session
  identity, and the three-call commit Step 5.
- Spec revision 8 with nineteen new pinned literals.

### Fixed

- Operator-agent GitHub issues #1–#4, each with its reproduction committed as a
  regression test.

## [0.6.7] - 2026-08-26

### Added

- Spec revision 7: merge-chain authority (FR-230..FR-243, DM-014..DM-017), the
  forge-cli/2 41-member envelope enum, and bounded lock epochs.

### Fixed

- Reviewer verdict collection real-path handling (`/dev/fd` targets replaced by
  by-name re-opens).
- Assertion-sensor not-applicable short-circuit for docs-only chains.

## [0.6.6] - 2026-08-21

### Added

- CLI phase 1: the `scripts/forge/cli.py` commit-chain state machine
  (FR-210..FR-224, DM-012/DM-013) with staged-diff candidate identity, resumable
  `verify`, two-phase finalize, and the FR-221 dual-accept commit guard pinned by
  the 112-case invocation corpus.
