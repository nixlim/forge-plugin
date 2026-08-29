from __future__ import annotations

import hashlib
import json
import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = Path("docs/specs/forge-plugin-spec.md")
V1_CORPUS = ROOT / "system/fr223/reason-codes-v1.json"
V3_CORPUS = ROOT / "system/fr223/reason-codes-v3.json"
V1_SHA256 = "3646227d8437789e0407117dc09e00d6116edccb63e89354c746d4b9059c264b"

REVISION9_ADDITIONS = [
    {
        "code": "archive-rerender-mismatch",
        "exit_class": 1,
        "precondition": "Archive candidate bytes do not equal deterministic rerender",
    },
    {
        "code": "archive-size-limit",
        "exit_class": 1,
        "precondition": "Rendered archive exceeds the 16 MiB UTF-8 limit",
    },
    {
        "code": "batch-idempotency-conflict",
        "exit_class": 1,
        "precondition": (
            "Existing receipt or intent uses the idempotency key for a different "
            "normalized request or batch bytes"
        ),
    },
    {
        "code": "batch-pending",
        "exit_class": 1,
        "precondition": (
            "Another outstanding journal batch intent prevents the requested operation"
        ),
    },
    {
        "code": "binding-invalid",
        "exit_class": 1,
        "precondition": (
            "Structured binding is missing, malformed, stale, or inconsistent with its "
            "chain event"
        ),
    },
    {
        "code": "ingest-proof-invalid",
        "exit_class": 1,
        "precondition": "At least one required external-chain ingest proof failed",
    },
    {
        "code": "journal-outbox-pending",
        "exit_class": 1,
        "precondition": (
            "A run-bound chain has an unreceipted event-carried journal batch"
        ),
    },
    {
        "code": "legacy-recovery-approval-required",
        "exit_class": 1,
        "precondition": (
            "Legacy archive mode lacks the matching per-instance operator decision and "
            "recovered HEAD"
        ),
    },
    {
        "code": "option-duplicate",
        "exit_class": 1,
        "precondition": (
            "A singleton option `--repo`, `--run-id`, or `--chain-id` occurs more than "
            "once"
        ),
    },
    {
        "code": "option-empty",
        "exit_class": 1,
        "precondition": "A required singleton option has an empty value",
    },
    {
        "code": "run-task-binding-invalid",
        "exit_class": 1,
        "precondition": (
            "Run/task binding fails repository, task, scope, policy, or immutability "
            "validation"
        ),
    },
    {
        "code": "run-task-binding-required",
        "exit_class": 1,
        "precondition": (
            "Exactly one of `--run-id` and `--task` was supplied at chain start"
        ),
    },
]


def committed_spec() -> str:
    result = subprocess.run(
        ["git", "show", f"HEAD:{SPEC_PATH.as_posix()}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return result.stdout


def reason_rows_between(spec: str, start: str, end: str) -> list[dict[str, object]]:
    try:
        section = spec[spec.index(start) + len(start) :]
        section = section[: section.index(end)]
    except ValueError as exc:
        raise AssertionError(f"committed reason-code authority is unavailable: {exc}") from exc

    rows = re.findall(
        r"(?m)^\| `([a-z][a-z0-9-]*)` \| ([012]) \| (.*?) \|$",
        section,
    )
    return [
        {"code": code, "exit_class": int(exit_class), "precondition": precondition}
        for code, exit_class, precondition in rows
    ]


def v2_spec_rows(spec: str) -> list[dict[str, object]]:
    return reason_rows_between(
        spec,
        "### `cli.py` — Forge CLI v2 output envelope and closed reason enum",
        "Hook audit labels",
    )


def revision9_spec_rows(spec: str) -> list[dict[str, object]]:
    return reason_rows_between(
        spec,
        "### Revision-9 `forge-cli/2` reason-union extension",
        "The two option messages",
    )


class Revision9ReasonCodeCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = committed_spec()
        cls.v3 = json.loads(V3_CORPUS.read_text(encoding="utf-8"))
        cls.v2_rows = v2_spec_rows(cls.spec)
        cls.revision9_rows = revision9_spec_rows(cls.spec)

    def test_exact_schema_sorted_unique_complete_count(self) -> None:
        self.assertEqual(set(self.v3), {"schema", "codes"})
        self.assertEqual(self.v3["schema"], "fr223-reason-codes/3")
        rows = self.v3["codes"]
        self.assertIsInstance(rows, list)
        self.assertTrue(
            all(
                isinstance(row, dict)
                and set(row) == {"code", "exit_class", "precondition"}
                for row in rows
            )
        )
        codes = [row["code"] for row in rows]
        self.assertEqual(len(rows), 53)
        self.assertEqual(codes, sorted(codes))
        self.assertEqual(len(codes), len(set(codes)))

    def test_complete_union_matches_committed_spec_authority(self) -> None:
        self.assertEqual(len(self.v2_rows), 41)
        self.assertEqual(len(self.revision9_rows), 12)
        expected = sorted(
            self.v2_rows + self.revision9_rows,
            key=lambda row: str(row["code"]),
        )
        self.assertEqual(self.v3["codes"], expected)

    def test_exact_twelve_revision9_additions(self) -> None:
        self.assertEqual(self.revision9_rows, REVISION9_ADDITIONS)
        v2_codes = {row["code"] for row in self.v2_rows}
        additions = [
            row for row in self.v3["codes"] if row["code"] not in v2_codes
        ]
        self.assertEqual(additions, REVISION9_ADDITIONS)
        self.assertTrue(all(row["exit_class"] == 1 for row in additions))

    def test_v1_artifact_unchanged_and_rows_retained(self) -> None:
        v1_bytes = V1_CORPUS.read_bytes()
        self.assertEqual(hashlib.sha256(v1_bytes).hexdigest(), V1_SHA256)
        v1 = json.loads(v1_bytes)
        self.assertEqual(set(v1), {"schema", "codes"})
        self.assertEqual(v1["schema"], "fr223-reason-codes/1")
        self.assertEqual(len(v1["codes"]), 25)

        v2_by_code = {row["code"]: row for row in self.v2_rows}
        v3_by_code = {row["code"]: row for row in self.v3["codes"]}
        for row in v1["codes"]:
            with self.subTest(code=row["code"]):
                self.assertEqual(v2_by_code[row["code"]], row)
                self.assertEqual(v3_by_code[row["code"]], row)


if __name__ == "__main__":
    unittest.main()
