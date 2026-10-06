"""Forge CLI application exports.

Application modules compose commit/merge admission, lifecycle transitions,
review and the fenced integration pipeline. State authority remains in chain_core.
"""

from __future__ import annotations

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
