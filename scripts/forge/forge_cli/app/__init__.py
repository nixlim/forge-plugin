"""Forge CLI application layer package (cli split phase 3, bead forge-plugin-95e.4; split
into a package by bead forge-plugin-hcuo).

This root holds the historical module's ``__all__`` verbatim and re-exports every symbol
``app.py`` defined from the submodule that now owns it: the deferred mutation-journal
sideband constants and helpers in ``_mutation_journal``, merge-start admission in
``_admission``, current-candidate observation in ``_candidate_observation``, the
``MergeEngine`` class in ``_merge_engine``, and the shared chain-verb router, ``dispatch``
and ``main`` in ``_dispatch``. Parser construction and other helpers are read as
``engine.<name>`` through the canonical ``forge_cli.engine`` module, and runtime controls
through ``forge_cli.runtime``.

Re-exports are snapshots of the owning module's binding: assigning a control on this root
does not reach the submodule that reads it (tests patch through ``patch_app``)."""

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
from ._admission import (
    prepare_merge_admission as prepare_merge_admission,
)
from ._candidate_observation import (
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
