---
id: fr223-reason-code-enum-v2
category: review
agent: review-cheap
expected_verdict: BLOCK
---

## Scenario

Review this proposed FR-220 refusal-envelope construction for a Revision-7 merge surface. The
resulting spelling happens to be a member of the closed 41-member `fr223-reason-codes/2` union
for `forge-cli/2`, and the envelope otherwise follows the exact JSON key contract.

<!-- BASELINE PLANTED DEFECT: the reason code is dynamically constructed. -->

## Input

```python
def cleanup_did_not_complete(chain_id: str, worktree: str) -> dict[str, object]:
    reason_code = "-".join(("cleanup", "failed"))
    return {
        "schema": "forge-cli/2",
        "ok": False,
        "chain_id": chain_id,
        "state": "cleanup_pending",
        "reason_code": reason_code,
        "message": "pushed candidate cleanup did not complete",
        "expected": "contained candidate and non-force cleanup",
        "observed": worktree,
        "remediation": (
            'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/cli.py" '
            f"merge cleanup --chain-id {chain_id}"
        ),
        "next_required_step": (
            'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/cli.py" '
            f"merge cleanup --chain-id {chain_id}"
        ),
        "evidence_refs": [],
    }
```

## Expected

FR-220's Revision-7 `forge-cli/2` reason codes are a closed, sorted, literal enum. Wildcards,
dynamic construction, and unlisted codes are forbidden even when the constructed spelling is a
valid member such as `cleanup-failed`. A reviewer MUST **BLOCK** the dynamic
`"-".join(...)` construction exactly as the immutable v1 baseline blocks it for `forge-cli/1`.
