# Consensus round: Engine decompose reviews (2026-09-20)

Reviewed tip: 813246a (base main 7e40590). Codex (gpt-5.6-sol, effort ultra, thread
01a0c00d-7844-7fa1-93f6-c89a33b6cadb): REJECT with 3 BLOCKING + 4 ADVISORY
(`codex-review-engine-class.md`). Fable refactor-reviewer: APPROVE, no blocking; every Codex item
CONFIRMED as fact, B1-B3 REFUTED as blocking (`fable-review-engine-class.md`). Follow-ups on the Codex
thread, one per disputed finding:

| finding | Codex answer | record |
|---|---|---|
| B1 wrapped class functions no longer pickle | AGREE: advisory for the handover (no consumer; operations.md permits it for function shape) | `consensus-engine-class-B1.md` |
| B2 temporary glob retained PLR0904 | AGREE: no applicable rule occurrence was masked (no class in any verb module); plan deviation is a handover advisory | `consensus-engine-class-B2.md` |
| B3 cluster commits without a CHANGELOG line | AGREE: cluster commits complied with the governing one-entry-per-branch protocol; conflict with the planner's text is a handover advisory | `consensus-engine-class-B3.md` |

Outcome: no blocking finding stands. Advisories carried to the handover: pickling / `__qualname__` /
`__module__` change of the 18 wrapped class functions (and 3 staticmethod bindings); ten lost mypy checks
(bead forge-plugin-psvo); `_engine` no longer binds 71 imported globals (private module, no reader);
the operator's 2026-09-19 direction that the temporary glob carry the `_engine.py` code list (then minus
I001, 5025042) is not worded as operator direction in the commit messages; the plan's per-commit CHANGELOG
wording was not amended to the protocol's one entry per branch; "tree identical" in the plan means
source-identical (5480091 adds only .refactor-quality.json); the nine verb modules lack a terminal newline
(operator decision pending at the time of this record).
