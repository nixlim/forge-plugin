# Consensus round: test_revision9_coordination split (lane A, session 4, bead forge-plugin-6g67)

Reviewed tip f20b8e8, range 69bc28d..f20b8e8. Codex (gpt-5.6-sol, effort ultra, thread
01a0ce81-0c72-7cd2-b38c-5ad8fa9753bd; `.refactor/codex-review-revision9-coord.md`) returned **REJECT** with two BLOCKING
and three ADVISORY items. The Fable refactor-reviewer (`.refactor/fable-review-revision9-coord.md`) returned **APPROVE**
independently and, in its adjudication round, marked both BLOCKING items REFUTED and listed them as DISPUTED. One
consensus round per item (`codex_review.sh --followup`, transcripts `.refactor/consensus-revision9-coord-B{1,2}.jsonl`,
responses `.refactor/consensus-revision9-coord-B{1,2}.md`):

| item | Codex finding | orchestrator evidence sent | Codex response | disposition |
|---|---|---|---|---|
| B1 | `tests/_revision9_coord_constants.py:27` duplicates the source's `sys.path.insert(0, ROOT/"scripts")`, changing lookup precedence; with the constants module cached and its entry removed the tip import fails | the copy is prescribed by the operator brief (section 4 item 2 / section 11 item 1) and the source line may not be removed; no repository code removes a `sys.path` entry; `scripts/` and `scripts/forge/` share no top-level name so the precedence change resolves nothing differently; `codex_orchestrator` resolves from the checkout at both refs; the source and all 13 new modules import first in a fresh process without PYTHONPATH | **AGREE** — downgrade to ADVISORY: "an explicitly authorized, disclosed state difference with no demonstrated repository behavior break" | advisory; disclosed in plan §4 state table and R2; no action |
| B2 | `tests/test_revision9_coordination.py:16` no longer binds `TOOLS`, `PREFIX_WEDGE_FIXTURE{,_SHA256}`, `UNREPLAYABLE_CHAIN_{ID,FIXTURE,FIXTURE_SHA256}` (16 bindings gone); direct imports raise `ImportError`; census incomplete | a discovered unittest module with no `__all__` is not an API; the bindings are the mover's planned `remove_imports` (plan §5, manifests); repository-wide grep finds no importer of the module or of those names and no `mock.patch` target naming `test_revision9_coordination.key`/`.hashlib`, which completes the `census_complete: false` census at zero sites; the names live in `tests._revision9_coord_constants` | **AGREE** — downgrade to ADVISORY: "internal unittest module, the removals were explicitly planned and manifested, the symbols have a designated new owner, and no tracked consumer or supported public API break exists" (kept as an advisory for hypothetical external importers) | advisory; recorded in the handover; no action |

Codex advisories A1 (`key.__module__` and patch target moved with the constants commit; no caller), A2 (no tracked c00
standalone source-module run; `.refactor/standalone-revision9-coord-source-tip.txt` records the run at the tip: 36 tests
OK) and A3 (Codex's own Gate 1 attempt was sandbox-limited; the committed Gate 1 logs are the record) stand as
advisories. Fable's advisories: the decompose-records pre-amend SHAs are rewritten to the amended branch commits in this
review-record commit (`pre_amend_commit` kept); the finalize Gate 1 logs are committed here; the per-cluster gate files
carry PASS/FAIL lines only (the 144 count is in every driver log's focused run and in the reviewer's own run); the
constants import's closing-paren layout is cosmetic (I001 grandfathered on the source).

Outcome: **no blocking finding survives the round** (brief section 8 item 5 not triggered). Reviewed tip unchanged at
f20b8e8; this commit adds review records only.
