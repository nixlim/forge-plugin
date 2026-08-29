---
id: fr223-reason-code-enum-v3
category: review
agent: review-cheap
expected_verdict: BLOCK
---

## Scenario

Review this proposed FR-220 refusal-envelope construction for a Revision-9 merge/ingest
surface. The resulting spelling happens to be a member of the closed 53-member
`fr223-reason-codes/3` union for `forge-cli/2`, and the envelope otherwise follows the exact
JSON key contract.

<!-- BASELINE PLANTED DEFECT: the reason code is dynamically constructed. -->

## Input

```python
def outbox_still_pending(chain_id: str, batch_digest: str) -> dict[str, object]:
    reason_code = "-".join(("journal", "outbox", "pending"))
    return {
        "schema": "forge-cli/2",
        "ok": False,
        "chain_id": chain_id,
        "state": "authorized",
        "reason_code": reason_code,
        "message": "a run-bound chain has an unreceipted event-carried journal batch",
        "expected": batch_digest,
        "observed": None,
        "remediation": (
            'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/cli.py" '
            f"journal batch-recover --chain-id {chain_id}"
        ),
        "next_required_step": (
            'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/cli.py" '
            f"journal batch-recover --chain-id {chain_id}"
        ),
        "evidence_refs": [],
    }
```

## Expected

FR-220 (as extended by Revision 9's `forge-cli/2` union): reason codes are a closed, sorted,
literal enum; wildcards, dynamic construction, and unlisted codes are forbidden even when the
constructed spelling lands on a valid member such as `journal-outbox-pending`. A reviewer must
BLOCK the dynamic `"-".join(...)` construction exactly as the v1 baseline blocks it for
`forge-cli/1`.
