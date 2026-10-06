"""Chain artifacts retain the non-reserved evidence refusal reason."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tests._cli_loader import package_module

CORE = package_module("chain_core")


class ReservedArtifactReasonTests(unittest.TestCase):
    def test_artifact_root_checks_emit_evidence_incomplete(self):
        engine = package_module("engine._core")
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = CORE.ChainStore(root)
            ctx = CORE.CommandContext(CORE.Repository(root), store, CORE.CLIOptions())
            state = {"chain_id": "c-2026-10-06T120000Z-dead", "state": "reviewing"}
            for relative in ("../escape", "/outside"):
                with self.subTest(relative=relative):
                    with (
                        self.assertRaises(engine.Refusal) as caught,
                        store.artifact_parent_descriptor(state["chain_id"], relative, create=False),
                    ):
                        self.fail("outside artifact admitted")
                    self.assertEqual(caught.exception.reason_code.value, "evidence-incomplete")
                    with self.assertRaises(engine.Refusal) as caught:
                        engine._read_bound_artifact(ctx, state, relative, None, "review")
                    self.assertEqual(caught.exception.reason_code.value, "evidence-incomplete")
            self.assertEqual(list(root.iterdir()), [])
