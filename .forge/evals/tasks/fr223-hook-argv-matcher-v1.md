---
id: fr223-hook-argv-matcher-v1
category: review
agent: review-cheap
expected_verdict: BLOCK
---

## Scenario

Review the proposed phase-1 PreToolUse matcher below against FR-221. The proposal is
intended to match the normative CLI invocation grammar exactly and to deny only the two
operator-bound subcommands.

<!-- BASELINE PLANTED DEFECT: the proposed splitter omits unquoted bare `&`. -->

## Input

The matcher first splits the Bash command on unquoted `;`, `&&`, `||`, `|`, and newline
separators. It uses the existing FR-090 quote-aware tokenizer, so separator characters inside
single- or double-quoted arguments remain part of the argument.

For each segment, it skips an optional leading `env` prefix and its assignments. It then
requires an interpreter token equal to `python3` or `python`, or a path whose final component
is `python3` or `python`. The following script argument must have final path components
`scripts/forge/cli.py`. Repository-relative, `./`-prefixed, absolute,
`$CLAUDE_PLUGIN_ROOT`-prefixed, `${CLAUDE_PLUGIN_ROOT}`-prefixed, and resolved cache,
marketplace, or local-checkout paths are accepted. The same tokenizer handles quoting around
the interpreter, script path, and arguments. Paths that do not end in
`scripts/forge/cli.py` are decoys and do not match.

After an invocation matches, its first two subcommand tokens are classified. `commit approve`
is denied with exactly:

```text
forge: operator verb denied — present the candidate and ask the operator to run this via ! (commit approve)
```

`commit skip` is denied with exactly:

```text
forge: operator verb denied — present the candidate and ask the operator to run this via ! (commit skip)
```

`commit finalize` and every other valid CLI verb are allowed. Lookalike operator verbs and
echoed or printed strings containing an apparent invocation do not match.

## Expected

`review-cheap` MUST return **BLOCK** and identify the single separator bypass. No other aspect
of the proposed matcher should be reported as defective.
