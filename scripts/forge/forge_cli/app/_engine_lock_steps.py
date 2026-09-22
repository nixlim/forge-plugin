from __future__ import annotations

from forge_cli import chain_core


def _acquire_recording_common_lock(common_dir, chain_id, operation, unexpected_split_recovery_proof, classify_reserved_fence):
    lock = chain_core.acquire_common_lock(
        common_dir,
        owner_kind="merge",
        chain_id=chain_id,
        operation=operation,
        no_transaction_record=operation != "recover",
        recovery_recorder=(
            unexpected_split_recovery_proof
            if operation == "recover"
            else None
        ),
        recovery_classifier=(
            classify_reserved_fence if operation == "recover" else None
        ),
    )
    return lock
