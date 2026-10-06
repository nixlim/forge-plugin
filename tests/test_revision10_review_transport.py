"""Focused tests for the revision-10 single-master review transport."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = ROOT / "scripts" / "forge" / "cli.py"


from tests._cli_loader import load_script, package_module, patch_engine


CLI = load_script("forge_cli_revision10_review_transport_tests", CLI_PATH)
ENGINE = package_module("engine")
RUNTIME = package_module("runtime")
FIXTURE_SUPPORT = load_script(
    "forge_cli_revision10_review_transport_fixture_support",
    ROOT / "tests" / "test_cli_chain.py",
)


REFUSAL = "forge: review refused — reviewer cannot inspect the complete authoritative package"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Revision10MasterReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="forge-review-master-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def write_master(self, name: str, data: bytes) -> Path:
        path = self.root / name
        path.write_bytes(data)
        return path

    def assert_complete_package_refusal(self, operation) -> CLI.Refusal:
        with self.assertRaises(CLI.Refusal) as caught:
            operation()
        self.assertEqual(caught.exception.reason_code, CLI.ReasonCode.EVIDENCE_INCOMPLETE)
        self.assertEqual(caught.exception.message, REFUSAL)
        return caught.exception

    def test_reader_yields_exact_raw_windows_in_ascending_order(self) -> None:
        data = b"abcdefghijklmn"
        master = self.write_master("master.bin", data)

        with patch_engine("REVIEW_MASTER_WINDOW_BYTES", 4):
            windows = list(
                ENGINE.iter_verified_master_package_windows(
                    master, len(data), sha256(data)
                )
            )

        self.assertEqual(windows, [b"abcd", b"efgh", b"ijkl", b"mn"])
        self.assertEqual(b"".join(windows), data)
        self.assertEqual(sha256(b"".join(windows)), sha256(data))

    def test_reader_refuses_a_symlinked_master_with_the_exact_literal(self) -> None:
        data = b"authoritative bytes"
        target = self.write_master("target.bin", data)
        link = self.root / "master-link.bin"
        link.symlink_to(target)

        self.assert_complete_package_refusal(
            lambda: list(
                ENGINE.iter_verified_master_package_windows(
                    link, len(data), sha256(data)
                )
            )
        )

    def test_reader_refuses_initial_length_or_digest_mismatch(self) -> None:
        data = b"0123456789abcdef"
        master = self.write_master("initial.bin", data)
        cases = (
            (len(data) - 1, sha256(data)),
            (len(data) + 1, sha256(data)),
            (len(data), sha256(data + b"different")),
        )

        for byte_length, digest in cases:
            with self.subTest(byte_length=byte_length, digest=digest):
                self.assert_complete_package_refusal(
                    lambda: list(
                        ENGINE.iter_verified_master_package_windows(
                            master, byte_length, digest
                        )
                    )
                )

    def test_reader_refuses_persistent_mutation_between_windows(self) -> None:
        data = b"abcdefghijkl"
        master = self.write_master("mutated.bin", data)

        with patch_engine("REVIEW_MASTER_WINDOW_BYTES", 4):
            windows = ENGINE.iter_verified_master_package_windows(
                master, len(data), sha256(data)
            )
            self.assertEqual(next(windows), b"abcd")
            with master.open("r+b") as handle:
                handle.seek(4)
                handle.write(b"WXYZ")
                handle.flush()
                os.fsync(handle.fileno())
            self.assert_complete_package_refusal(lambda: list(windows))

    def test_reader_refuses_truncated_or_grown_master_between_windows(self) -> None:
        data = b"abcdefghijkl"
        for mutation in ("truncate", "grow"):
            with self.subTest(mutation=mutation):
                master = self.write_master(f"{mutation}.bin", data)
                with patch_engine("REVIEW_MASTER_WINDOW_BYTES", 4):
                    windows = ENGINE.iter_verified_master_package_windows(
                        master, len(data), sha256(data)
                    )
                    self.assertEqual(next(windows), b"abcd")
                    if mutation == "truncate":
                        with master.open("r+b") as handle:
                            handle.truncate(5)
                    else:
                        with master.open("ab") as handle:
                            handle.write(b"grown")
                    self.assert_complete_package_refusal(lambda: list(windows))

    def test_reader_refuses_path_identity_replacement_between_windows(self) -> None:
        data = b"abcdefghijkl"
        master = self.write_master("identity.bin", data)
        replacement = self.write_master("replacement.bin", data)

        with patch_engine("REVIEW_MASTER_WINDOW_BYTES", 4):
            windows = ENGINE.iter_verified_master_package_windows(
                master, len(data), sha256(data)
            )
            self.assertEqual(next(windows), b"abcd")
            os.replace(replacement, master)
            self.assert_complete_package_refusal(lambda: list(windows))

    def test_reader_refuses_concat_mismatch_even_when_master_is_restored(self) -> None:
        data = b"abcdefghijkl"
        master = self.write_master("restored.bin", data)

        with patch_engine("REVIEW_MASTER_WINDOW_BYTES", 4):
            windows = ENGINE.iter_verified_master_package_windows(
                master, len(data), sha256(data)
            )
            self.assertEqual(next(windows), b"abcd")
            with master.open("r+b") as handle:
                handle.seek(4)
                handle.write(b"WXYZ")
            self.assertEqual(next(windows), b"WXYZ")
            with master.open("r+b") as handle:
                handle.seek(4)
                handle.write(data[4:8])
                handle.flush()
                os.fsync(handle.fileno())

            refusal = self.assert_complete_package_refusal(lambda: list(windows))

        self.assertIsInstance(refusal.__cause__, OSError)
        self.assertIn("window concatenation mismatch", str(refusal.__cause__))
        self.assertEqual(master.read_bytes(), data)


class Revision10CommitReviewTransportTests(FIXTURE_SUPPORT.ForgeCLIFixture):
    def setUp(self) -> None:
        super().setUp()
        environment_patch = mock.patch.dict(os.environ, self.environment(), clear=True)
        environment_patch.start()
        self.addCleanup(environment_patch.stop)
        script_patch = mock.patch.object(RUNTIME, "SCRIPT_DIR", self.helpers)
        script_patch.start()
        self.addCleanup(script_patch.stop)
        plugin_patch = mock.patch.object(RUNTIME, "PLUGIN_ROOT", ROOT)
        plugin_patch.start()
        self.addCleanup(plugin_patch.stop)
        for name, executable in (
            ("CODEX_EXECUTABLE", self.helpers / "fake-codex"),
            ("CLAUDE_EXECUTABLE", self.helpers / "fake-claude"),
        ):
            self.enterContext(patch_engine(name, str(executable)))

    @staticmethod
    def package_of_length(length: int, prefix: bytes = b"") -> bytes:
        if len(prefix) > length:
            raise ValueError("prefix is longer than requested package")
        return prefix + (b"x" * (length - len(prefix)))

    def ready_engine(self) -> tuple[object, str, dict[str, object]]:
        self.change("scripts/tool.py", "CONTROL = 2\n")
        started = self.start("scripts/tool.py")
        chain_id = str(started["chain_id"])

        self.cli("verify", "--chain-id", chain_id, expected=0)
        state = self.state(chain_id)
        repository = CLI.Repository(self.repo)
        context = CLI.CommandContext(
            repository,
            CLI.ChainStore(repository.common_root()),
            CLI.CLIOptions(chain_id=chain_id, repo=str(self.repo)),
        )
        return CLI.Engine(context), chain_id, state

    def request_package(
        self,
        package: bytes,
        *,
        reviewer: str = "review-final",
        candidate_diff: bytes = b"fixture candidate diff\n",
    ) -> tuple[object, dict[str, object], Path]:
        engine, chain_id, _state = self.ready_engine()
        package_parts = (
            package,
            reviewer,
            ["review-coding"],
            {"scripts/tool.py": ["review-coding"]},
            b"fixture transport header\n",
            b"fixture controlling policy\n",
            b"fixture fresh reviewer evidence\n",
            candidate_diff,
        )
        with mock.patch.object(engine, "_review_package", return_value=package_parts):
            outcome = engine.review_request()
        request = self.state(chain_id)["review"]["request"]
        master = self.repo / str(request["package"])
        self.request_engine = engine
        self.request_chain_id = chain_id
        return outcome, request, master

    def assert_oversized_receipt(
        self,
        receipt: str,
        *,
        master: Path,
        byte_length: int,
        master_digest: str,
    ) -> None:
        window_size = ENGINE.REVIEW_MASTER_WINDOW_BYTES
        window_count = (byte_length + window_size - 1) // window_size
        self.assertIn("authoritative-master", receipt)
        self.assertIn(
            f"path={json.dumps(str(master), ensure_ascii=True)}", receipt
        )
        self.assertIn(f"byte-length={byte_length}", receipt)
        self.assertIn(f"sha256={master_digest}", receipt)
        self.assertIn(
            "windows=[65536*n, min(65536*(n+1), byte_length))", receipt
        )
        self.assertIn(
            f"window-count=ceil({byte_length}/65536)={window_count}", receipt
        )
        self.assertIn(
            "reader=forge_cli.engine.iter_verified_master_package_windows", receipt
        )

    def test_exact_threshold_keeps_the_byte_identical_direct_package(self) -> None:
        self.assertEqual(ENGINE.REVIEW_DIRECT_PACKAGE_MAX_BYTES, 786_432)
        package = self.package_of_length(ENGINE.REVIEW_DIRECT_PACKAGE_MAX_BYTES)

        outcome, request, master = self.request_package(package)

        package_digest = sha256(package)
        self.assertEqual(master.read_bytes(), package)
        self.assertEqual(request["package_digest"], package_digest)
        self.assertEqual(request["lane"], "forge-review-lane/1")
        self.assertEqual(request["provider"], "claude")
        self.assertNotIn("invocation", request)
        self.assertIn("review-final launched detached", outcome.message)

    def test_threshold_plus_one_writes_one_full_master_and_pointer_receipt(self) -> None:
        marker = b"REVISION10_MASTER_BYTES_MUST_NOT_APPEAR_IN_RECEIPT"
        byte_length = ENGINE.REVIEW_DIRECT_PACKAGE_MAX_BYTES + 1
        package = self.package_of_length(byte_length, marker)

        outcome, request, master = self.request_package(package)

        package_digest = sha256(package)
        window_count = (
            byte_length + ENGINE.REVIEW_MASTER_WINDOW_BYTES - 1
        ) // ENGINE.REVIEW_MASTER_WINDOW_BYTES
        self.assertEqual(request["transport"], "single-master-package")
        self.assertEqual(request["byte_length"], byte_length)
        self.assertEqual(request["window_size"], 65_536)
        self.assertEqual(request["window_count"], window_count)
        self.assertEqual(request["package_digest"], package_digest)
        self.assertEqual(master.read_bytes(), package)
        self.assertEqual(sha256(master.read_bytes()), package_digest)
        self.assertIn(str(request["package"]), outcome.evidence_refs)
        self.assert_oversized_receipt(
            outcome.message,
            master=master,
            byte_length=byte_length,
            master_digest=package_digest,
        )
        self.assertNotIn("invocation", request)
        self.assertNotIn(marker.decode(), outcome.message)

    def assert_standard_oversized_package_is_pointer_only(self) -> None:
        marker = b"REVISION10_UNIQUE_CANDIDATE_MARKER_MUST_NOT_BE_EMBEDDED"
        byte_length = ENGINE.REVIEW_DIRECT_PACKAGE_MAX_BYTES + 1
        package = self.package_of_length(byte_length, marker)

        outcome, request, master = self.request_package(
            package,
            reviewer="review-cheap",
            candidate_diff=marker,
        )

        prompt = (self.repo / str(request["prompt_path"])).read_bytes()
        self.assertNotIn(marker, prompt)
        self.assertEqual(request["transport"], "single-master-package")
        self.assertEqual(master.read_bytes(), package)
        self.assertEqual(request["prompt_digest"], sha256(prompt))
        self.assert_oversized_receipt(
            outcome.message,
            master=master,
            byte_length=byte_length,
            master_digest=sha256(package),
        )

    def test_standard_oversized_prompt_is_pointer_only(self) -> None:
        self.assert_standard_oversized_package_is_pointer_only()

    def test_disabling_threshold_check_restores_embedded_prompt_and_kills_assertion(self) -> None:
        with patch_engine(
            "_review_package_is_oversized", return_value=False
        ), self.assertRaises(AssertionError):
            self.assert_standard_oversized_package_is_pointer_only()

    def test_oversized_review_final_collect_keeps_package_binding(self) -> None:
        byte_length = ENGINE.REVIEW_DIRECT_PACKAGE_MAX_BYTES + 1
        package = self.package_of_length(byte_length, b"binding master\n")
        _outcome, request, master = self.request_package(package)
        selected_chain_id = self.request_chain_id
        engine = self.request_engine
        self.wait_for_review_completion(request)
        original = master.read_bytes()
        master.write_bytes(b"substituted oversized package\n")

        with self.assertRaises(CLI.Refusal) as caught:
            engine.review_collect()
        self.assertEqual(
            caught.exception.reason_code, CLI.ReasonCode.REVIEW_VERDICT_INVALID
        )
        self.assertEqual(self.state(selected_chain_id)["state"], "reviewing")

        master.write_bytes(original)
        collected = engine.review_collect()

        self.assertEqual(collected.state, "awaiting_approval")
        persisted = self.state(selected_chain_id)
        self.assertEqual(
            persisted["review"]["verdict"]["package_digest"], request["package_digest"]
        )
        self.assertEqual(master.read_bytes(), package)


if __name__ == "__main__":
    unittest.main()
