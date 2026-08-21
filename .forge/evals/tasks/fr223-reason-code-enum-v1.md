---
id: fr223-reason-code-enum-v1
category: review
agent: review-cheap
expected_verdict: BLOCK
---

## Scenario

Review this proposed FR-220 refusal-envelope construction. The resulting spelling happens to
be a member of the closed reason-code enum, and the envelope otherwise follows the exact JSON
key contract.

<!-- BASELINE PLANTED DEFECT: the reason code is dynamically constructed. -->

## Input

```python
def awaiting_operator_approval(chain_id: str, candidate: str) -> dict[str, object]:
    reason_code = "-".join(("approval", "required"))
    return {
        "schema": "forge-cli/1",
        "ok": False,
        "chain_id": chain_id,
        "state": "awaiting_approval",
        "reason_code": reason_code,
        "message": "operator approval is required for the current candidate",
        "expected": candidate,
        "observed": None,
        "remediation": (
            'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/cli.py" '
            f"commit approve --candidate {candidate}"
        ),
        "next_required_step": (
            'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/cli.py" '
            f"commit approve --candidate {candidate}"
        ),
        "evidence_refs": [],
    }
```

## Expected

`review-cheap` MUST return **BLOCK** because FR-220 forbids dynamically constructed reason
codes even when the computed value is currently a registered member.
