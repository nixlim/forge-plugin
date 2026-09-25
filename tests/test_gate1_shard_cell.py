"""Contract tests for the work-queue gate-1 policy cell (bead forge-plugin-pwy, revised).

The cell in forge-project.md's ``gate1-test-command`` region runs full discovery as a work
queue inside one ``bash -c`` invocation: every module is its own unittest process, pulled
longest-first by ``min(8, cpu)`` workers. These tests extract that exact cell and run it,
under the FR-149 argv discipline (``bash -c <cell> forge <params...>``), against small
synthetic test trees, so the fail-closed semantics are proved without running the real suite.

The cell's host guards (the ``/dev/shm/agents-sem/gate`` slot and the ``/proc/pressure/cpu``
wait) are re-entrant through ``FORGE_GATE1_NESTED=1``, which the cell exports to every module
process. These tests set it explicitly so a standalone run never takes the host slot the
enclosing gate may already hold, and pin the guard text statically instead.
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
EMPTY_SHELL = '"""Retained shell after a test split: collects no test."""\n'
MODULE_LINE = re.compile(r"^gate-1 (?P<name>test_\w+): exit (?P<exit>-?\d+) ran (?P<ran>-?\d+) in (?P<seconds>[0-9.?]+)s (?P<verdict>OK|FAILED)$", re.M)
SUMMARY_LINE = re.compile(r"^gate-1: (?P<modules>\d+) modules, (?P<tests>\d+) tests, (?P<workers>\d+) workers, (?P<slot>slot held|slot unavailable|nested), (?P<running>\d+)s running, (?P<waited>\d+)s waiting for host pressure, (?P<verdict>OK|FAILED)$", re.M)


class Gate1WorkQueueCellTests(unittest.TestCase):
    def run_cell(self, tree: dict[str, str], *params: str) -> subprocess.CompletedProcess:
        root = Path(tempfile.mkdtemp(prefix="forge-gate1-cell-"))
        self.addCleanup(shutil.rmtree, root, True)
        (root / "tests").mkdir()
        for name, body in tree.items():
            (root / "tests" / name).write_text(body, encoding="utf-8")
        environment = dict(os.environ)
        environment["PATH"] = str(Path(sys.executable).parent) + os.pathsep + environment.get("PATH", "")
        environment["FORGE_GATE1_NESTED"] = "1"
        return subprocess.run(
            ["bash", "-c", gate1_cell(), "forge", *params],
            cwd=root, env=environment, capture_output=True, text=True, timeout=120,
        )

    def test_cell_is_a_single_fenced_work_queue_cell_with_host_guards(self) -> None:
        cell = gate1_cell()
        self.assertTrue(cell.startswith("python3 - <<'PY'"))
        self.assertIn('glob.glob("tests/test_*.py")', cell)
        self.assertIn("min(8, os.cpu_count() or 1)", cell)
        self.assertIn("raise SystemExit(1 if failed else 0)", cell)
        # Longest-first work queue, one unittest process per module.
        self.assertIn("key=lambda name: (-weights[name], name)", cell)
        self.assertIn('[sys.executable, "-m", "unittest", f"tests.{name}"]', cell)
        # Host guards: the shared gate slot and the CPU-pressure wait, both re-entrant.
        self.assertIn('pathlib.Path("/dev/shm/agents-sem/gate")', cell)
        self.assertIn("fcntl.flock(gate_lock, fcntl.LOCK_EX)", cell)
        self.assertIn('pathlib.Path("/proc/pressure/cpu")', cell)
        self.assertIn("deadline = started + 300", cell)
        self.assertIn('nested = os.environ.get("FORGE_GATE1_NESTED") == "1"', cell)
        self.assertIn('slot = "nested" if nested else "slot unavailable"', cell)
        self.assertIn('slot = "slot held"', cell)
        self.assertIn('environment = dict(os.environ, FORGE_GATE1_NESTED="1")', cell)
        # The failing-module tail is sliced in bytes before decoding and budgeted.
        self.assertIn('output[-4096:]', cell)
        self.assertIn("tail_budget = 40 * 1024", cell)
        # The region holds exactly one fenced cell (the policy parser's requirement).
        region = POLICY.split("<!-- FORGE:REGION gate1-test-command BEGIN -->", 1)[1].split(
            "<!-- FORGE:REGION gate1-test-command END -->", 1
        )[0]
        self.assertEqual(region.count("```bash"), 1)

    def test_every_module_runs_once_and_the_summary_counts_them(self) -> None:
        tree = {f"test_mod{i}.py": PASSING for i in range(6)}
        completed = self.run_cell(tree, "scripts/forge/cli.py", "tests/test_mod0.py")
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        lines = [m.groupdict() for m in MODULE_LINE.finditer(completed.stdout)]
        self.assertEqual(sorted(line["name"] for line in lines), sorted(n[:-3] for n in tree))
        self.assertTrue(all(line["verdict"] == "OK" and line["ran"] == "1" for line in lines))
        summary = SUMMARY_LINE.search(completed.stdout)
        self.assertIsNotNone(summary, completed.stdout)
        self.assertEqual((summary["modules"], summary["tests"], summary["verdict"]), ("6", "6", "OK"))
        self.assertEqual((summary["waited"], summary["slot"]), ("0", "nested"))
        self.assertLessEqual(int(summary["workers"]), 8)
        # Extra argv parameters (the FR-149 changed-path list) never narrow discovery: a
        # parameter-free run collects exactly the same modules.
        bare = self.run_cell(tree)
        self.assertEqual(bare.returncode, 0, bare.stdout + bare.stderr)
        self.assertEqual(SUMMARY_LINE.search(bare.stdout)["tests"], "6")

    def test_one_failing_module_fails_the_cell_closed_and_prints_its_tail(self) -> None:
        tree = {f"test_mod{i}.py": PASSING for i in range(5)}
        tree["test_mod5.py"] = FAILING
        completed = self.run_cell(tree)
        self.assertEqual(completed.returncode, 1, completed.stdout)
        verdicts = {m["name"]: m["verdict"] for m in MODULE_LINE.finditer(completed.stdout)}
        self.assertEqual(verdicts["test_mod5"], "FAILED")
        self.assertEqual(sum(v == "OK" for v in verdicts.values()), 5)
        self.assertIn("test_bad", completed.stdout)
        self.assertEqual(SUMMARY_LINE.search(completed.stdout)["verdict"], "FAILED")

    def test_empty_module_set_fails_closed(self) -> None:
        completed = self.run_cell({})
        self.assertEqual(completed.returncode, 1)
        self.assertIn("gate-1: no test modules under tests/", completed.stderr)

    def test_module_without_a_unittest_summary_fails_closed(self) -> None:
        # A module that kills the interpreter before unittest prints its summary must
        # not pass merely because the exit code happened to be zero.
        tree = {"test_ok.py": PASSING, "test_exit.py": "import os\nos._exit(0)\n"}
        completed = self.run_cell(tree)
        self.assertEqual(completed.returncode, 1, completed.stdout)
        line = next(m for m in MODULE_LINE.finditer(completed.stdout) if m["name"] == "test_exit")
        self.assertEqual((line["exit"], line["ran"], line["verdict"]), ("0", "-1", "FAILED"))

    def test_retained_empty_shell_module_passes_with_ran_zero(self) -> None:
        # Python 3.12+ unittest exits 5 for a module that collects no test; the cell
        # admits exactly that pairing (exit 5 with a "Ran 0 tests" summary).
        tree = {"test_ok.py": PASSING, "test_shell.py": EMPTY_SHELL}
        completed = self.run_cell(tree)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        line = next(m for m in MODULE_LINE.finditer(completed.stdout) if m["name"] == "test_shell")
        self.assertEqual((line["ran"], line["verdict"]), ("0", "OK"))
        self.assertIn(line["exit"], {"0", "5"})

    def test_exit_five_without_a_ran_zero_summary_fails_closed(self) -> None:
        tree = {"test_ok.py": PASSING, "test_five.py": "import sys\nsys.exit(5)\n"}
        completed = self.run_cell(tree)
        self.assertEqual(completed.returncode, 1, completed.stdout)
        line = next(m for m in MODULE_LINE.finditer(completed.stdout) if m["name"] == "test_five")
        self.assertEqual((line["exit"], line["verdict"]), ("5", "FAILED"))

    def test_failing_output_is_capped_in_bytes(self) -> None:
        # Every failing module floods stdout with four-byte and three-byte code points;
        # the per-module tail is a 4 KiB byte bound under a 40 KiB budget, so the whole
        # cell stays inside the runner's 65,536-byte cap even for non-ASCII output.
        noisy = (
            "import sys, unittest\n\nclass T(unittest.TestCase):\n    def test_noise(self):\n"
            "        sys.stdout.write('€\U0001f600' * 100000)\n        self.fail('noisy')\n"
        )
        tree = {f"test_noisy{i}.py": noisy for i in range(14)}
        completed = self.run_cell(tree)
        self.assertEqual(completed.returncode, 1, completed.stderr)
        self.assertIn("€", completed.stdout)
        self.assertIn("tail budget exhausted", completed.stdout)
        self.assertLess(len(completed.stdout.encode("utf-8")), 65536)


if __name__ == "__main__":
    unittest.main()
