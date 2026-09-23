Evidence:

- Baseline defined `TOOLS`, `batch`, `journal`, and `RECORDED_AT` at `tests/test_revision8_coordination.py:19-25`; helpers read them at lines 93 and 111.
- Tip has one constant definition each at `tests/_revision8_constants.py:5,9`. Support imports them at `tests/_revision8_support.py:15-17` and reads them at lines 84 and 102.
- I ran AST write/patch scans over every Revision 8 module at both revisions. Results:

```text
69bc28d: writes = constant definitions only
97d4d60: writes = constant definitions only
module-attribute rebinds = 0
string-path patches/setattr = 0
patch.object rooted at journal = 72 at each revision
patch.dict(os.environ, ...) = 4 at each revision
```

- A runtime probe confirmed both facts:

```text
helper sees family RECORDED_AT rebind: False
family journal is support journal: True
```

Thus `mock.patch.object(journal, ...)`, such as `tests/test_revision8_successors.py:25-29`, still mutates the shared module object seen by inherited helpers.
- `.refactor/plan-revision8.md:225-234` records immutable constants, no module-state writers, and no `global` statements.
- The focused gate passed all 81 tests at `.refactor/gate-revision8-mixin.txt:12,24-26`.

**RETRACT** — the theoretical Python lookup difference exists, but no test or helper rebinds any of these module bindings. All actual patches target the shared `journal` object or `os.environ`, so B4 does not demonstrate changed suite behavior.