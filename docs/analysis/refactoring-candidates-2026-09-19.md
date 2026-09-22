# Refactoring candidates — 2026-09-19

Measured on main at 7e4059043a912fe9b52f70eed342d219674f7d01, right after the app.py split reintegrated (bead forge-plugin-90b0). Companion to `refactoring-review-2026-09-11.md`.

Rules applied:

- The Python budget is 500 *code* lines per file, counted the way `scripts/check_file_length.py` counts (blank and comment-only lines excluded, docstrings included). Every over-budget file is grandfathered in `.refactor-baseline.json` and may shrink but not grow.
- Vendored means the codex-orchestrator engine and tests named in `UPSTREAM`, vendored at commit cc0c13f (2026-08-10). Per the operator's 2026-09-19 direction, vendored files are not refactoring targets because feature work does not touch them. Files that live inside the vendored package but were authored here are listed separately for the operator's call.
- Shell scripts have no enforced budget; the nixlim/forge predecessor is this project's own lineage, not a foreign vendor.
- Bash and Python bodies are measured; JSON artifacts under `.refactor/` are generated data, not targets.

## 1. Over the 500-code-line budget

### 1a. Production Python, not vendored

| Code lines | File | Bead |
|---|---|---|
| 10302 | `scripts/forge/forge_cli/app/_merge_engine.py` | forge-plugin-37fr (class split; needs the class-split capability) |
| 4882 | `scripts/forge/archive-run.py` | forge-plugin-i5od (sweep-1) |
| 3574 | `scripts/forge/forge_cli/engine/_engine.py` | forge-plugin-321p (P4, class split) |
| 3000 | `scripts/forge/forge_cli/fresh_evals.py` | forge-plugin-i5od (sweep-1) |
| 2020 | `scripts/forge/forge_cli/chain_core/_merge_transition.py` | — |
| 1902 | `scripts/forge/forge_cli/chain_core/_merge_chain.py` | forge-plugin-4j7 (P4) |
| 1847 | `scripts/forge/forge_cli/chain_core/_commit_chain.py` | forge-plugin-4j7 (P4) |
| 1275 | `scripts/forge/fr223_eval.py` | — |
| 1195 | `scripts/forge/forge_cli/candidate.py` | — |
| 1096 | `scripts/forge/forge_cli/chain_core/_storage.py` | — |
| 963 | `scripts/forge/learn-proposals.py` | — |
| 924 | `scripts/forge/audit-commitments.py` | — |
| 887 | `scripts/forge/run-scoped-mutation.py` | — |
| 877 | `scripts/forge/forge_cli/chain_core/_ingest_merge.py` | — |
| 786 | `scripts/forge/check-test-quality.py` | — |
| 764 | `scripts/forge/forge_cli/chain_core/_common_lock.py` | — |
| 708 | `scripts/forge/risk_tier.py` | — |
| 671 | `scripts/forge/migrate-upstream.py` | — |
| 659 | `scripts/forge/forge_cli/chain_core/__init__.py` | — |
| 659 | `scripts/forge/commitment_paths.py` | — |
| 576 | `scripts/forge/forge_cli/chain_core/_activation.py` | — |

### 1b. Forge-authored files inside the vendored `scripts/codex_orchestrator/` package

Added 2026-08-29 (revision-9 archive and journal fidelity); not present at the vendoring commit.

| Code lines | File | Bead |
|---|---|---|
| 9431 | `scripts/codex_orchestrator/builders.py` | — |
| 4522 | `scripts/codex_orchestrator/batch.py` | forge-plugin-i5od (sweep-1; drop if the package counts as vendored) |

### 1c. Tests, not vendored

The split-module plugin's test-split capability is not built yet; these wait on it.

| Code lines | File |
|---|---|
| 13222 | `tests/test_revision9_coordination.py` |
| 7332 | `tests/test_cli_merge_integration.py` |
| 5456 | `tests/test_revision9_cli_surfaces.py` |
| 4946 | `tests/test_cli_merge_lifecycle.py` |
| 4905 | `tests/test_revision8_coordination.py` |
| 2635 | `tests/test_cli_chain.py` |
| 2275 | `tests/test_revision9_archive.py` |
| 2018 | `tests/test_cli_common_lock.py` |
| 2016 | `tests/test_fresh_reviewer_evals.py` |
| 1915 | `tests/test_audit_commitments.py` |
| 1770 | `tests/test_archive_run.py` |
| 1656 | `tests/test_fr223_v2_hook.py` |
| 1643 | `tests/test_drift_check.py` |
| 1618 | `tests/test_cli_merge_adapters.py` |
| 1587 | `tests/test_run_coordination.py` |
| 1537 | `tests/test_mutation_runner.py` |
| 1526 | `tests/test_fresh_reviewer_cli.py` |
| 1520 | `tests/test_cli_chain_finalize.py` |
| 1491 | `tests/test_learn_proposals.py` |
| 1401 | `tests/test_fr230_phase3_manifest.py` |
| 1340 | `tests/test_d13_concurrency.py` |
| 1270 | `tests/test_revision9_matrix.py` |
| 1088 | `tests/test_cli_merge_store.py` |
| 1059 | `tests/test_cli_phase0_contracts.py` |
| 1054 | `tests/test_revision9_ingest_negatives.py` |
| 991 | `tests/test_repo_conformance.py` |
| 889 | `tests/test_migration.py` |
| 728 | `tests/test_risk_tier.py` |
| 706 | `tests/test_cli_hook_integration.py` |
| 682 | `tests/test_revision9_terminal_races.py` |
| 653 | `tests/test_candidate_identity.py` |
| 633 | `tests/test_test_quality.py` |

### 1d. Shell scripts over 500 code lines (no enforced budget)

| Code lines | File |
|---|---|
| 4486 | `scripts/forge/commit-guard.sh` |
| 1097 | `scripts/forge/drift-check.sh` |
| 582 | `scripts/forge/install.sh` |
| 530 | `scripts/forge/aggregate-telemetry.sh` |

### 1e. Excluded as vendored codex-orchestrator content

Vendored by path; most have grown several-fold through forge work, so the exclusion is a policy choice, not a content one.

| Code lines at vendoring | Code lines now | File |
|---|---|---|
| 339 | 8261 | `scripts/codex_orchestrator/journal.py` |
| 458 | 2789 | `tests/test_commit_guard.py` |
| 340 | 1599 | `tests/test_validation.py` |
| 442 | 1562 | `tests/test_docs_contract.py` |
| 386 | 1446 | `tests/test_installer.py` |
| 355 | 1307 | `tests/test_governance_scripts.py` |
| 783 | 1030 | `tests/test_e2e_smoke.py` |
| 241 | 795 | `tests/test_evals.py` |
| 167 | 759 | `tests/test_commit_and_region_template.py` |

## 2. Every tracked file over 1,000 total lines

Total lines (`wc -l`). Status is relative to the vendoring commit cc0c13f: *new in forge* = not present then; *modified* = present and changed since. No file over 1,000 lines is unchanged since vendoring.

### Production code

| Lines | Lines at vendoring | Status | File |
|---|---|---|---|
| 10596 | — | new in forge | `scripts/forge/forge_cli/app/_merge_engine.py` |
| 9948 | — | new in forge | `scripts/codex_orchestrator/builders.py` |
| 9052 | 379 | modified | `scripts/codex_orchestrator/journal.py` |
| 5305 | — | new in forge | `scripts/forge/archive-run.py` |
| 4945 | 764 | modified | `scripts/forge/commit-guard.sh` |
| 4875 | — | new in forge | `scripts/codex_orchestrator/batch.py` |
| 3710 | — | new in forge | `scripts/forge/forge_cli/engine/_engine.py` |
| 3259 | — | new in forge | `scripts/forge/forge_cli/fresh_evals.py` |
| 2048 | — | new in forge | `scripts/forge/forge_cli/chain_core/_merge_transition.py` |
| 1981 | — | new in forge | `scripts/forge/forge_cli/chain_core/_merge_chain.py` |
| 1980 | — | new in forge | `scripts/forge/forge_cli/chain_core/_commit_chain.py` |
| 1385 | — | new in forge | `scripts/forge/fr223_eval.py` |
| 1326 | — | new in forge | `scripts/forge/forge_cli/candidate.py` |
| 1208 | — | new in forge | `scripts/forge/drift-check.sh` |
| 1142 | — | new in forge | `scripts/forge/forge_cli/chain_core/_storage.py` |
| 1080 | — | new in forge | `scripts/forge/audit-commitments.py` |
| 1073 | — | new in forge | `scripts/forge/learn-proposals.py` |
| 1002 | — | new in forge | `scripts/forge/run-scoped-mutation.py` |

### Tests

| Lines | Lines at vendoring | Status | File |
|---|---|---|---|
| 13881 | — | new in forge | `tests/test_revision9_coordination.py` |
| 7857 | — | new in forge | `tests/test_cli_merge_integration.py` |
| 5846 | — | new in forge | `tests/test_revision9_cli_surfaces.py` |
| 5334 | — | new in forge | `tests/test_cli_merge_lifecycle.py` |
| 5253 | — | new in forge | `tests/test_revision8_coordination.py` |
| 3039 | 517 | modified | `tests/test_commit_guard.py` |
| 2873 | — | new in forge | `tests/test_cli_chain.py` |
| 2432 | — | new in forge | `tests/test_revision9_archive.py` |
| 2185 | — | new in forge | `tests/test_fresh_reviewer_evals.py` |
| 2174 | — | new in forge | `tests/test_audit_commitments.py` |
| 2152 | — | new in forge | `tests/test_cli_common_lock.py` |
| 1949 | — | new in forge | `tests/test_archive_run.py` |
| 1779 | — | new in forge | `tests/test_run_coordination.py` |
| 1779 | — | new in forge | `tests/test_fr223_v2_hook.py` |
| 1765 | 393 | modified | `tests/test_validation.py` |
| 1747 | — | new in forge | `tests/test_drift_check.py` |
| 1712 | — | new in forge | `tests/test_mutation_runner.py` |
| 1710 | — | new in forge | `tests/test_cli_merge_adapters.py` |
| 1705 | 512 | modified | `tests/test_docs_contract.py` |
| 1689 | — | new in forge | `tests/test_cli_chain_finalize.py` |
| 1660 | — | new in forge | `tests/test_fresh_reviewer_cli.py` |
| 1615 | 439 | modified | `tests/test_installer.py` |
| 1587 | — | new in forge | `tests/test_learn_proposals.py` |
| 1522 | — | new in forge | `tests/test_fr230_phase3_manifest.py` |
| 1447 | — | new in forge | `tests/test_d13_concurrency.py` |
| 1442 | 412 | modified | `tests/test_governance_scripts.py` |
| 1314 | — | new in forge | `tests/test_revision9_matrix.py` |
| 1180 | — | new in forge | `tests/test_cli_phase0_contracts.py` |
| 1152 | — | new in forge | `tests/test_cli_merge_store.py` |
| 1130 | — | new in forge | `tests/test_revision9_ingest_negatives.py` |
| 1109 | — | new in forge | `tests/test_repo_conformance.py` |
| 1093 | 824 | modified | `tests/test_e2e_smoke.py` |
| 1018 | — | new in forge | `tests/test_migration.py` |

### Docs and control

| Lines | Lines at vendoring | Status | File |
|---|---|---|---|
| 3267 | 675 | modified | `docs/specs/forge-plugin-spec.md` |
| 1213 | 400 | modified | `skills/commit/SKILL.md` |
| 1115 | — | new in forge | `.forge/history/runs/run-20260826-coordination-hardening.md` |

### Generated refactor artifacts (data, not targets)

| Lines | File |
|---|---|
| 7930 | `.refactor/inventory-hubs60.json` |
| 7916 | `.refactor/inventory-hubs40.json` |
| 7908 | `.refactor/inventory-hubs20.json` |
| 7892 | `.refactor/inventory.json` |
| 5294 | `.refactor/before.json` |
| 5294 | `.refactor/before-engine.json` |
| 5294 | `.refactor/before-app.json` |
| 4418 | `.refactor/inventory-engine.json` |

## 3. Open refactor beads

- forge-plugin-37fr — split MergeEngine (`app/_merge_engine.py`) along its seams; blocked on the class-split capability.
- forge-plugin-i5od — sweep-1: `fresh_evals.py`, `archive-run.py`, `batch.py` on one branch with one reintegration.
- forge-plugin-321p — split Engine (`engine/_engine.py`) into verb mixins (P4).
- forge-plugin-4j7 — split `_commit_chain.py` and `_merge_chain.py` (P4).
- forge-plugin-ausy — loader fan-out tests share their module oracle with the control (MINOR from the app-split review).
- forge-plugin-deb — design discussion: file-size guardrail with agentic refactoring as part of the process.

Totals: 21 non-vendored production files, 2 forge-authored files in the vendored package, 32 non-vendored test files and 4 shell scripts over budget; 62 tracked files over 1,000 lines.
