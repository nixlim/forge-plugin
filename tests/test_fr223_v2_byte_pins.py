"""Byte pins for the seven additive DM-016 v2 artifacts."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_SHA256 = {
    ".forge/evals/tasks/fr223-hook-argv-matcher-v2.md": (
        "32b9d5d3559b310505d6c429bff7d867807df9fd2f2523acb25039d3038e318b"
    ),
    ".forge/evals/tasks/fr223-hook-argv-matcher-v2.result": (
        "09a6c264d3c4abdcb411b1659573ef239dad5df6f71760e7f44d8b36d73bf387"
    ),
    ".forge/evals/tasks/fr223-reason-code-enum-v2.md": (
        "286b220b59dfd8106503bf28e609ac3b77552e004d86b72761a40ea26d7aff31"
    ),
    ".forge/evals/tasks/fr223-reason-code-enum-v2.result": (
        "09a6c264d3c4abdcb411b1659573ef239dad5df6f71760e7f44d8b36d73bf387"
    ),
    ".forge/evals/tasks/fr230-phase3-4-v2.manifest.json": (
        "5d57f0db68e40580e5c76a05c09a7c1818a08e5a8d235b9be7ab4d9736488311"
    ),
    "system/fr223/hook-argv-cases-v2.json": (
        "310bfda5efdbfe3c99a1d189c8ff336782f90a79af741c4098ada4ae579bde27"
    ),
    "system/fr223/reason-codes-v2.json": (
        "6e33be25226111896dc6d6cf621935b414a8a5e1a509adb4ea4daa347c239a28"
    ),
}


class V2ArtifactBytePinTests(unittest.TestCase):
    def test_all_seven_artifacts_match_the_generation_contract(self) -> None:
        self.assertEqual(len(ARTIFACT_SHA256), 7)
        for relative_path, expected in ARTIFACT_SHA256.items():
            with self.subTest(path=relative_path):
                artifact = ROOT / relative_path
                self.assertTrue(artifact.is_file())
                self.assertFalse(artifact.is_symlink())
                raw = artifact.read_bytes()
                if relative_path.endswith("fr230-phase3-4-v2.manifest.json"):
                    payload = json.loads(raw.decode("utf-8"))
                    self.assertIn(payload.get("generation"), {1, 2})
                    if payload["generation"] == 2:
                        self.assertEqual(
                            payload.get("previous_manifest_sha256"), expected
                        )
                        continue
                self.assertEqual(hashlib.sha256(raw).hexdigest(), expected)


if __name__ == "__main__":
    unittest.main()
