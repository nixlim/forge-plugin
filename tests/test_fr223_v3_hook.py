"""Revision-13 DM-016 v3 hook-argv generation: supersession and assignment-prefix rows."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from unittest import mock

from tests.test_fr223_v2_hook import (
    DENIALS,
    HookHarnessMixin,
    LEGACY_OPERATOR_DENIALS,
    V1_HOOK,
    V1_HOOK_SHA256,
    V2_HOOK,
    denial,
    load_guard_module,
    read_json,
)


ROOT = Path(__file__).resolve().parents[1]
V3_HOOK = ROOT / "system/fr223/hook-argv-cases-v3.json"
V3_FIXTURE = ROOT / ".forge/evals/tasks/fr223-hook-argv-matcher-v3.md"
V3_RESULT = ROOT / ".forge/evals/tasks/fr223-hook-argv-matcher-v3.result"
V3_MANIFEST = ROOT / ".forge/evals/tasks/fr223-hook-argv-v3.manifest.json"
V2_HOOK_SHA256 = "310bfda5efdbfe3c99a1d189c8ff336782f90a79af741c4098ada4ae579bde27"
SUPERSEDED_ID = "no-match-bare-assignment-without-env"
EXPECTED_V3_IDS = tuple(
    f"deny-{verb}-bare-{prefix}"
    for verb in ("approve", "merge-approve", "skip")
    for prefix in (
        "assignment-then-env-assignment",
        "multiple-assignments",
        "quoted-assignment-space",
        "single-assignment",
    )
)
V3_EXPECTATION_ENUM = {
    "allow", "no-match", "deny-approve", "deny-skip",
    "deny-merge-approve", "deny-invalid-mode", "deny-raw-commit", "deny-raw-push",
}
ALL_DENIALS = {**DENIALS, **LEGACY_OPERATOR_DENIALS}


class V3CorpusContractTests(unittest.TestCase):
    def test_v3_layout_reference_and_supersession_are_exact(self) -> None:
        payload = read_json(V3_HOOK)
        self.assertEqual(tuple(payload), ("schema", "v2", "supersedes", "case_count", "cases"))
        self.assertEqual(payload["schema"], "fr223-hook-argv/3")
        self.assertEqual(
            payload["v2"],
            {
                "path": "system/fr223/hook-argv-cases-v2.json",
                "schema": "fr223-hook-argv/2",
                "sha256": V2_HOOK_SHA256,
                "case_count": 18,
            },
        )
        self.assertEqual(hashlib.sha256(V2_HOOK.read_bytes()).hexdigest(), V2_HOOK_SHA256)
        self.assertEqual(hashlib.sha256(V1_HOOK.read_bytes()).hexdigest(), V1_HOOK_SHA256)
        supersedes = payload["supersedes"]
        self.assertEqual(
            supersedes,
            [
                {
                    "id": SUPERSEDED_ID,
                    "generation": "fr223-hook-argv/1",
                    "expect": "deny-approve",
                    "reason": LEGACY_OPERATOR_DENIALS["deny-approve"],
                }
            ],
        )
        v1_by_id = {case["id"]: case for case in read_json(V1_HOOK)["cases"]}
        self.assertEqual(v1_by_id[SUPERSEDED_ID]["expect"], "no-match")
        self.assertEqual(
            v1_by_id[SUPERSEDED_ID]["command"],
            "FORGE_MODE=test python3 scripts/forge/cli.py commit approve --candidate abc123",
        )
        cases = payload["cases"]
        self.assertEqual(payload["case_count"], 12)
        self.assertEqual(len(cases), 12)
        self.assertEqual(112 + 18 + len(cases), 142)
        identifiers = tuple(case["id"] for case in cases)
        self.assertEqual(identifiers, tuple(sorted(identifiers, key=str.encode)))
        self.assertEqual(sorted(identifiers), sorted(EXPECTED_V3_IDS))
        referenced = set(v1_by_id) | {case["id"] for case in read_json(V2_HOOK)["cases"]}
        self.assertFalse(set(identifiers) & referenced)
        for case in cases:
            with self.subTest(case=case["id"]):
                self.assertEqual(
                    tuple(case), ("id", "command", "activation", "expect", "reason")
                )
                self.assertIn(case["expect"], V3_EXPECTATION_ENUM)
                self.assertEqual(case["reason"], ALL_DENIALS[case["expect"]])
                self.assertEqual(
                    tuple(case["activation"]), ("head_manifest", "worktree_manifest")
                )
                self.assertIsNone(case["activation"]["worktree_manifest"])
                first = case["command"].split()[0]
                self.assertRegex(first, r"^[A-Za-z_][A-Za-z0-9_]*=")

    def test_v3_manifest_pins_corpus_fixture_and_result(self) -> None:
        manifest = read_json(V3_MANIFEST)
        self.assertEqual(tuple(manifest), ("schema", "artifacts", "clauses"))
        self.assertEqual(manifest["schema"], "fr223-hook-argv-manifest/3")
        expected_paths = [
            ".forge/evals/tasks/fr223-hook-argv-matcher-v3.md",
            ".forge/evals/tasks/fr223-hook-argv-matcher-v3.result",
            "system/fr223/hook-argv-cases-v3.json",
        ]
        self.assertEqual([item["path"] for item in manifest["artifacts"]], expected_paths)
        for item in manifest["artifacts"]:
            with self.subTest(path=item["path"]):
                self.assertEqual(tuple(item), ("path", "sha256"))
                self.assertEqual(
                    hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest(),
                    item["sha256"],
                )
        self.assertEqual(V3_RESULT.read_bytes(), b"BLOCK\n")
        self.assertIn("expected_verdict: BLOCK", V3_FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["clauses"]), 1)
        clause = manifest["clauses"][0]
        self.assertEqual(tuple(clause), ("artifacts", "clause", "statement"))
        self.assertEqual(clause["clause"], "hook-argv-supersession-v3")
        self.assertEqual(clause["artifacts"], expected_paths)


class V3HookExecutionTests(HookHarnessMixin, unittest.TestCase):
    def test_all_12_additive_cases_execute_against_their_activation_context(self) -> None:
        for case in read_json(V3_HOOK)["cases"]:
            with self.subTest(case=case["id"]):
                activation = case["activation"]
                repo = self.repository(
                    activation["head_manifest"], activation["worktree_manifest"]
                )
                result = self.invoke(repo, case["command"])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, "")
                self.assertEqual(json.loads(result.stdout), denial(case["reason"]))
                self.wait_for_advisory_children(repo)

    def test_superseded_v1_row_is_denied_and_the_prefix_skip_is_load_bearing(self) -> None:
        module = load_guard_module(self, "forge_commit_guard_v3_supersession")
        v1_by_id = {case["id"]: case for case in read_json(V1_HOOK)["cases"]}
        command = v1_by_id[SUPERSEDED_ID]["command"]
        self.assertEqual(module.classify_forge_cli_invocation(command), "deny-approve")
        for context in ("non-forge", "legacy-v1", "forge-verbs-v1", "invalid"):
            with self.subTest(context=context):
                result = self.invoke(self.repository(context, None), command)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    json.loads(result.stdout), denial(LEGACY_OPERATOR_DENIALS["deny-approve"])
                )
        # Disable the prefix skip in memory: the v1 pin's bypass returns, and
        # only that row changes (env-prefixed rows still deny via the env branch).
        with mock.patch.object(module, "_skip_forge_cli_prefix", lambda _tokens: 0):
            self.assertEqual(module.classify_forge_cli_invocation(command), "no-match")
            self.assertEqual(
                module.classify_forge_cli_invocation(
                    v1_by_id["deny-approve-env-single-assignment"]["command"]
                ),
                "no-match",
            )
        self.assertEqual(
            module.classify_forge_cli_invocation(
                v1_by_id["deny-approve-env-single-assignment"]["command"]
            ),
            "deny-approve",
        )


if __name__ == "__main__":
    unittest.main()
