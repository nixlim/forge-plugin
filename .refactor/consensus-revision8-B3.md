Evidence:

- Baseline bindings were at `tests/test_revision8_coordination.py:19` (`TOOLS`), line 22 (`batch`, `journal`), and line 25 (`RECORDED_AT`). Tip retains only `ROOT` and `Revision8Support` imports at lines 5–6.
- The names now live at `tests/_revision8_constants.py:5,9` and `tests/_revision8_support.py:15,17`; consumers import them there, e.g. `tests/test_revision8_successors.py:12-15`.
- I ran this at both revisions:

```sh
git grep -n -I -E \
'from tests\.test_revision8_coordination import|import tests\.test_revision8_coordination|test_revision8_coordination\.(TOOLS|RECORDED_AT|batch|journal)' \
<rev> -- . ':(exclude).refactor/**' \
' :(exclude)tests/test_revision8_coordination.py'
```

It found no importer. A separate AST scan of every tracked Python file likewise found zero imports from that module at both revisions.

- Broader `git grep test_revision8_coordination` found only config, changelog, analysis, and historical command references—no attribute consumer or patch target.
- `.refactor/plan-revision8.md:71,78` explicitly records the relocation, `prerequisites: []`, and zero code sites requiring repointing.
- `pyproject.toml:271-275` defines only `forge_cli` and `codex_orchestrator` as root packages; `tests` is not a declared API package.

**RETRACT** — the namespace shrink is real, but B3’s classification as a public-API break is unsupported. I found no importer or declared contract for these incidental test-module bindings, and the relocation was explicitly manifested.