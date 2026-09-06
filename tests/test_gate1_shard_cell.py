"""Contract tests for the sharded gate-1 policy cell (bead forge-plugin-pwy).

The cell in forge-project.md's ``gate1-test-command`` region fans full discovery out over
shards inside one ``bash -c`` invocation. These tests extract that exact cell and run it, under
the FR-149 argv discipline (``bash -c <cell> forge <params...>``), against small synthetic test
trees, so the fail-closed semantics are proved without running the real suite.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests._cli_loader import package_module

ROOT = Path(__file__).resolve().parents[1]
POLICY_BYTES = (ROOT / "forge-project.md").read_bytes()
POLICY = POLICY_BYTES.decode("utf-8")


def gate1_cell() -> str:
    """The cell exactly as the commit, merge, and drift gates parse it (forge_cli.policy)."""

    return package_module("policy").parse_policy("worktree", POLICY_BYTES).gate1


PASSING = "import unittest\n\nclass T(unittest.TestCase):\n    def test_ok(self):\n        self.assertTrue(True)\n"
FAILING = "import unittest\n\nclass T(unittest.TestCase):\n    def test_bad(self):\n        self.fail('bad')\n"


class Gate1ShardCellTests(unittest.TestCase):
    def run_cell(self, tree: dict[str, str], *params: str) -> subprocess.CompletedProcess:
        root = Path(tempfile.mkdtemp(prefix="forge-gate1-cell-"))
        self.addCleanup(shutil.rmtree, root, True)
        (root / "tests").mkdir()
        for name, body in tree.items():
            (root / "tests" / name).write_text(body, encoding="utf-8")
        environment = dict(os.environ)
        environment["PATH"] = str(Path(sys.executable).parent) + os.pathsep + environment.get("PATH", "")
        return subprocess.run(
            ["bash", "-c", gate1_cell(), "forge", *params],
            cwd=root, env=environment, capture_output=True, text=True, timeout=120,
        )

    def test_cell_is_a_single_fenced_shell_cell_that_shards_discovery(self) -> None:
        cell = gate1_cell()
        self.assertTrue(cell.startswith("python3 - <<'PY'"))
        self.assertIn('glob.glob("tests/test_*.py")', cell)
        self.assertIn("min(4, os.cpu_count() or 1)", cell)
        self.assertIn("raise SystemExit(1 if failed else 0)", cell)
        # The tail is sliced in bytes before decoding, so the 8 KiB bound is a byte bound.
        self.assertIn('output[-8192:].decode("utf-8", "replace")', cell)
        # The region holds exactly one fenced cell (the policy parser's requirement).
        region = POLICY.split("<!-- FORGE:REGION gate1-test-command BEGIN -->", 1)[1].split(
            "<!-- FORGE:REGION gate1-test-command END -->", 1
        )[0]
        self.assertEqual(region.count("```bash"), 1)

    def test_all_shards_pass_and_every_module_is_collected(self) -> None:
        tree = {f"test_mod{i}.py": PASSING for i in range(6)}
        completed = self.run_cell(tree, "scripts/forge/cli.py", "tests/test_mod0.py")
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        summaries = re.findall(r"^gate-1 shard (\d+)/(\d+): exit 0 OK$", completed.stdout, flags=re.M)
        self.assertTrue(summaries, completed.stdout)
        total = sum(int(n) for n in re.findall(r"^Ran (\d+) tests? in", completed.stdout, flags=re.M))
        self.assertEqual(total, 6)
        self.assertEqual({int(t) for _, t in summaries}, {len(summaries)})
        # Extra argv parameters (the FR-149 changed-path list) never narrow discovery: a
        # parameter-free run collects exactly the same modules.
        bare = self.run_cell(tree)
        self.assertEqual(bare.returncode, 0, bare.stdout + bare.stderr)
        bare_total = sum(int(n) for n in re.findall(r"^Ran (\d+) tests? in", bare.stdout, flags=re.M))
        self.assertEqual(bare_total, total)

    def test_one_failing_shard_fails_the_cell_closed(self) -> None:
        tree = {f"test_mod{i}.py": PASSING for i in range(5)}
        tree["test_mod5.py"] = FAILING
        completed = self.run_cell(tree)
        self.assertEqual(completed.returncode, 1, completed.stdout)
        self.assertIn("FAILED", completed.stdout)
        self.assertIn("test_bad", completed.stdout)
        # Every other shard still reports; the cell does not stop at the first failure.
        self.assertGreaterEqual(len(re.findall(r"^gate-1 shard ", completed.stdout, flags=re.M)), 2)

    def test_empty_module_set_fails_closed(self) -> None:
        completed = self.run_cell({})
        self.assertEqual(completed.returncode, 1)
        self.assertIn("gate-1: no test modules under tests/", completed.stderr)

    def test_shard_without_a_unittest_summary_fails_closed(self) -> None:
        # A module that kills the interpreter before unittest prints its summary must
        # not pass merely because the exit code happened to be zero.
        tree = {"test_ok.py": PASSING, "test_exit.py": "import os\nos._exit(0)\n"}
        completed = self.run_cell(tree)
        self.assertEqual(completed.returncode, 1, completed.stdout)
        self.assertIn("FAILED", completed.stdout)

    def test_shard_output_is_capped_in_bytes(self) -> None:
        # Every shard floods stdout with four-byte and three-byte code points; the cell's
        # per-shard tail must be an 8 KiB byte bound, not a character bound, so the whole
        # cell stays inside the runner's 65,536-byte cap even for non-ASCII output.
        noisy = (
            "import sys, unittest\n\nclass T(unittest.TestCase):\n    def test_noise(self):\n"
            "        sys.stdout.write('\u20ac\U0001f600' * 100000)\n        self.assertTrue(True)\n"
        )
        tree = {f"test_noisy{i}.py": noisy for i in range(4)}
        completed = self.run_cell(tree)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("\u20ac", completed.stdout)
        shard_count = len(re.findall(r"^gate-1 shard ", completed.stdout, flags=re.M))
        self.assertGreaterEqual(shard_count, 1)
        self.assertLess(len(completed.stdout.encode("utf-8")), shard_count * (8192 + 256) + 1024)
        self.assertLess(len(completed.stdout.encode("utf-8")), 65536)

if __name__ == "__main__":
    unittest.main()
