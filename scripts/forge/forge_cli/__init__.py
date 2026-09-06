"""Forge CLI package: interpreter-loaded modules behind the scripts/forge/cli.py shim.

Nothing in this package is executable; `cli.py` remains the sole invoked entry point
(FR-221 matcher and FR-223 corpora pin that path). Phase 1 of bead forge-plugin-95e
holds the response envelope and the committed-policy parser; later phases move the
remaining clusters once a canonical runtime module hosts the patchable controls.
"""
