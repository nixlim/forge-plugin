# Inventory: scripts/forge/forge_cli/app.py
- total lines: 11525
- top-level symbols: 18 (functions 10, classes 2, assignments 6)
- intra-module reference edges: 22

## Module-level mutable state (must get exactly ONE owning module)
- `_MUTATION_JOURNAL_REQUEST_KEYS` (line 51) used by: _validate_deferred_mutation_request
- `__all__` (line 11516) used by: nobody

## Hub symbols (highest fan-in; removed before clustering: 4)
Move these FIRST into a small `_core.py`/`_state.py`/`_base.py` so the rest of the graph falls apart. A hub that is a class used as a base class or a module-wide config/logger belongs in `_core.py`; a hub that is pure utility belongs in `_util.py`.
- `_DeferredMutationRequestError` (class, 2 LOC, fan-in 3, fan-out 0) (REMOVED)
- `main` (function, 117 LOC, fan-in 2, fan-out 1) (REMOVED)
- `MergeEngine` (class, 10574 LOC, fan-in 2, fan-out 3) (REMOVED)
- `_mutation_persistence_error` (function, 6 LOC, fan-in 1, fan-out 2) (REMOVED)
- `_bounded_mutation_output` (function, 12 LOC, fan-in 1, fan-out 1)
- `_validate_deferred_mutation_request` (function, 47 LOC, fan-in 1, fan-out 4)
- `_persist_deferred_mutation_result` (function, 77 LOC, fan-in 1, fan-out 5)
- `_route_shared_chain_engine` (function, 19 LOC, fan-in 1, fan-out 1)
- `_merge_command_engine` (function, 13 LOC, fan-in 1, fan-out 1)
- `dispatch` (function, 149 LOC, fan-in 1, fan-out 2)
- `prepare_merge_admission` (function, 198 LOC, fan-in 1, fan-out 1)
- `_observe_current_merge_candidate` (function, 195 LOC, fan-in 1, fan-out 1)
- after removing 4 hubs: 4 components, largest has 3 of 8 defs

## Suggested clusters (connected components after hub removal; showing >= 150 LOC)
### Cluster 1: 198 LOC, 1 symbols
- members: `prepare_merge_admission`
- referenced from outside cluster by: MergeEngine
- references outside cluster: main
### Cluster 2: 195 LOC, 1 symbols
- members: `_observe_current_merge_candidate`
- referenced from outside cluster by: MergeEngine
- references outside cluster: main
### Cluster 3: 181 LOC, 3 symbols
- members: `_route_shared_chain_engine`, `_merge_command_engine`, `dispatch`
- referenced from outside cluster by: main
- references outside cluster: MergeEngine

## Communities (label propagation on the hub-free graph; use when a component is still too big)
### Community 1: 198 LOC, 1 symbols; in-edges from 0 outside symbols, out-edges to 0
- members: `prepare_merge_admission`
### Community 2: 195 LOC, 1 symbols; in-edges from 0 outside symbols, out-edges to 0
- members: `_observe_current_merge_candidate`
### Community 3: 181 LOC, 3 symbols; in-edges from 0 outside symbols, out-edges to 0
- members: `_route_shared_chain_engine`, `_merge_command_engine`, `dispatch`

## Largest symbols
- `MergeEngine` (class, lines 940-11513, 10574 LOC, fan-in 2, fan-out 3)
- `prepare_merge_admission` (function, lines 543-740, 198 LOC, fan-in 1, fan-out 1)
- `_observe_current_merge_candidate` (function, lines 743-937, 195 LOC, fan-in 1, fan-out 1)
- `dispatch` (function, lines 273-421, 149 LOC, fan-in 1, fan-out 2)
- `main` (function, lines 424-540, 117 LOC, fan-in 2, fan-out 1)
- `_persist_deferred_mutation_result` (function, lines 158-234, 77 LOC, fan-in 1, fan-out 5)
- `_validate_deferred_mutation_request` (function, lines 109-155, 47 LOC, fan-in 1, fan-out 4)
- `_route_shared_chain_engine` (function, lines 237-255, 19 LOC, fan-in 1, fan-out 1)
- `_MUTATION_JOURNAL_REQUEST_KEYS` (assignment, lines 51-67, 17 LOC, fan-in 1, fan-out 0)
- `_MUTATION_JOURNAL_PREIMAGE_KEYS` (assignment, lines 68-80, 13 LOC, fan-in 1, fan-out 0)
- `_merge_command_engine` (function, lines 258-270, 13 LOC, fan-in 1, fan-out 1)
- `_bounded_mutation_output` (function, lines 95-106, 12 LOC, fan-in 1, fan-out 1)
- `__all__` (assignment, lines 11516-11524, 9 LOC, fan-in 0, fan-out 0)
- `_mutation_persistence_error` (function, lines 87-92, 6 LOC, fan-in 1, fan-out 2)
- `_MUTATION_PERSISTENCE_ADVISORY` (assignment, lines 48-50, 3 LOC, fan-in 2, fan-out 0)

## Leaves (fan-out 0 within module; safest to extract first)
`_DeferredMutationRequestError`
