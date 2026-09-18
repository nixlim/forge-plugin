"""Forge CLI application layer (cli split phase 3, bead forge-plugin-95e.4).

Moved verbatim from scripts/forge/cli.py: the MergeEngine class, the shared chain-verb
router, and the argument-parsing and dispatch entry points; parser construction and other
helpers are read as ``engine.<name>`` through the canonical ``forge_cli.engine`` module."""

from __future__ import annotations

from ._mutation_journal import (
    _MUTATION_JOURNAL_SCHEMA as _MUTATION_JOURNAL_SCHEMA,
    _MUTATION_JOURNAL_SIDEBAND_PREFIX as _MUTATION_JOURNAL_SIDEBAND_PREFIX,
    _MUTATION_PERSISTENCE_ADVISORY as _MUTATION_PERSISTENCE_ADVISORY,
    _MUTATION_JOURNAL_REQUEST_KEYS as _MUTATION_JOURNAL_REQUEST_KEYS,
    _MUTATION_JOURNAL_PREIMAGE_KEYS as _MUTATION_JOURNAL_PREIMAGE_KEYS,
    _DeferredMutationRequestError as _DeferredMutationRequestError,
    _mutation_persistence_error as _mutation_persistence_error,
    _bounded_mutation_output as _bounded_mutation_output,
    _validate_deferred_mutation_request as _validate_deferred_mutation_request,
    _persist_deferred_mutation_result as _persist_deferred_mutation_result,
)
from forge_cli.app._admission import (
    prepare_merge_admission as prepare_merge_admission,
)
from forge_cli.app._candidate_observation import (
    _observe_current_merge_candidate as _observe_current_merge_candidate,
)
from ._merge_engine import MergeEngine as MergeEngine
from ._dispatch import (
    _merge_command_engine as _merge_command_engine,
    _route_shared_chain_engine as _route_shared_chain_engine,
    dispatch as dispatch,
    main as main,
)


__all__ = [
    'MergeEngine',
    '_merge_command_engine',
    '_observe_current_merge_candidate',
    '_route_shared_chain_engine',
    'dispatch',
    'main',
    'prepare_merge_admission',
]
