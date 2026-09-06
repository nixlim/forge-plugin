"""Forge CLI package: interpreter-loaded modules behind the scripts/forge/cli.py shim.

Nothing in this package is executable; `cli.py` remains the sole invoked entry point
(FR-221 matcher and FR-223 corpora pin that path). Modules: `envelope` (reason codes,
Refusal, FrozenError, Outcome), `policy` (the committed-policy parser), `runtime` (the one
canonical module for the patchable controls and the late-bound journal-record seam), and
`chain_core` (process runner, common-lock arbiter, chain storage, merge state, ingest
verifiers). The shim re-imports envelope and policy names by explicit lists and forwards
reads of runtime and chain_core names through a module __getattr__ (bead forge-plugin-95e).
"""
