from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import unittest
from unittest import mock

from tests._revision8_constants import RECORDED_AT, TOOLS
from tests._revision8_support import Revision8Support

from codex_orchestrator import journal


class Revision8SuccessorsTests(Revision8Support, unittest.TestCase):

    def test_successor_transfer_control_is_load_bearing(self) -> None:
        self.assertEqual(self.open_run("run-transfer-A", "src/transfer/**").returncode, 0)
        self.assertEqual(self.retire("run-transfer-A").returncode, 0)
        before = self.coordination_snapshot()

        enabled = journal.SUCCESSOR_DAG_CONTROLS
        with self.api_environment(), mock.patch.object(
            journal, "SUCCESSOR_DAG_CONTROLS", enabled - {"transfer"}
        ):
            with self.assertRaises(journal.CoordinationRefusal) as caught:
                journal.open_run(
                    self.repo,
                    "run-transfer-B",
                    ["src/transfer/branch/**"],
                    self.opening_record("run-transfer-B"),
                    successor_of="run-transfer-A",
                )
        self.assertEqual(
            str(caught.exception),
            "forge: successor run refused — predecessor run-transfer-A is not a "
            "scope-reserving retired run",
        )
        self.assertEqual(self.coordination_snapshot(), before)
        self.assertFalse(self.run_dir("run-transfer-B").exists())

    def test_successor_chain_transfers_ancestry_releases_and_readmits(self) -> None:
        self.assertEqual(self.open_run("run-A", "src/ancestor/**").returncode, 0)
        self.assertEqual(self.retire("run-A").returncode, 0)

        opened_b = self.open_run(
            "run-B", "src/ancestor/b/**", successor_of="run-A"
        )
        self.assertEqual(opened_b.returncode, 0, opened_b.stderr)
        second_child = self.open_run(
            "run-A-second", "src/ancestor/second/**", successor_of="run-A"
        )
        self.assertEqual(second_child.returncode, 1)
        self.assertEqual(
            second_child.stderr,
            "forge: successor run refused — predecessor run-A is not a "
            "scope-reserving retired run\n",
        )
        self.assertFalse(self.run_dir("run-A-second").exists())
        self.assertEqual(self.retire("run-B").returncode, 0)

        self.assertEqual(self.open_run("run-U", "src/unrelated/**").returncode, 0)
        self.assertEqual(self.retire("run-U").returncode, 0)

        opened_c = self.open_run(
            "run-C", "src/ancestor/b/c/**", successor_of="run-B"
        )
        self.assertEqual(opened_c.returncode, 0, opened_c.stderr)
        carried = self.open_run("run-carried-probe", "src/ancestor/carried.py")
        self.assertEqual(carried.returncode, 1)
        self.assertEqual(
            carried.stderr,
            "forge: new run refused — scope overlap between run-carried-probe and "
            "open run run-C\n",
        )

        readmitted = self.readmit(
            "run-C", "src/ancestor/readmitted/**", replace=True
        )
        self.assertEqual(readmitted.returncode, 0, readmitted.stderr)
        unrelated = self.readmit(
            "run-C", "src/unrelated/file.py", replace=True
        )
        self.assertEqual(unrelated.returncode, 1)
        self.assertEqual(
            unrelated.stderr,
            "forge: new run refused — scope overlap between run-C and "
            "scope-reserving retired run run-U\n",
        )

        closed = self.command(
            "run-close",
            "--repo",
            str(self.repo),
            "--run-id",
            "run-C",
            "--idempotency-key",
            "2" * 64,
            "--judgment",
            "passed",
            "--summary",
            "Successor ancestry was transferred and released",
        )
        self.assertEqual(closed.returncode, 0, closed.stderr)
        readmitted_after_release = self.open_run(
            "run-after-release", "src/ancestor/new.py"
        )
        self.assertEqual(
            readmitted_after_release.returncode, 0, readmitted_after_release.stderr
        )
        unrelated_still_reserved = self.open_run(
            "run-unrelated-probe", "src/unrelated/new.py"
        )
        self.assertEqual(unrelated_still_reserved.returncode, 1)
        self.assertEqual(
            unrelated_still_reserved.stderr,
            "forge: new run refused — scope overlap between run-unrelated-probe and "
            "scope-reserving retired run run-U\n",
        )

    def test_successor_readmission_may_leave_ancestor_scope_but_keeps_it_reserved(self) -> None:
        self.assertEqual(
            self.open_run("run-readmit-A", "src/ancestor/**").returncode, 0
        )
        self.assertEqual(self.retire("run-readmit-A").returncode, 0)
        successor = self.open_run(
            "run-readmit-B",
            "src/ancestor/initial/**",
            successor_of="run-readmit-A",
        )
        self.assertEqual(successor.returncode, 0, successor.stderr)

        readmitted = self.readmit(
            "run-readmit-B", "src/disjoint/**", replace=True
        )

        self.assertEqual(readmitted.returncode, 0, readmitted.stderr)
        registry = json.loads(self.registry_path.read_text(encoding="utf-8"))
        self.assertEqual(
            registry["open_runs"],
            [{"run_id": "run-readmit-B", "scope": ["src/disjoint/**"]}],
        )
        ancestor_probe = self.open_run(
            "run-readmit-ancestor-probe", "src/ancestor/file.py"
        )
        self.assertEqual(ancestor_probe.returncode, 1)
        self.assertEqual(
            ancestor_probe.stderr,
            "forge: new run refused — scope overlap between "
            "run-readmit-ancestor-probe and open run run-readmit-B\n",
        )
        own_probe = self.open_run(
            "run-readmit-own-probe", "src/disjoint/file.py"
        )
        self.assertEqual(own_probe.returncode, 1)
        self.assertEqual(
            own_probe.stderr,
            "forge: new run refused — scope overlap between run-readmit-own-probe "
            "and open run run-readmit-B\n",
        )

    def test_successor_refusal_literals_for_retired_overlap_and_disjoint_scope(self) -> None:
        self.assertEqual(self.open_run("run-retired-base", "src/base/**").returncode, 0)
        self.assertEqual(self.retire("run-retired-base").returncode, 0)

        ordinary = self.open_run("run-ordinary", "src/base/file.py")
        self.assertEqual(ordinary.returncode, 1)
        self.assertEqual(
            ordinary.stderr,
            "forge: new run refused — scope overlap between run-ordinary and "
            "scope-reserving retired run run-retired-base\n",
        )
        disjoint = self.open_run(
            "run-disjoint", "other/**", successor_of="run-retired-base"
        )
        self.assertEqual(disjoint.returncode, 1)
        self.assertEqual(
            disjoint.stderr,
            "forge: successor run refused — scope of run-disjoint does not overlap "
            "scope-reserving retired run run-retired-base\n",
        )

    def test_persisted_dangling_successor_edge_is_generic_and_nonmutating(self) -> None:
        self.plant_run_state(
            "run-dangling",
            ("src/dangling/**",),
            successor_of="run-missing-predecessor",
        )
        self.write_registry({"run-dangling": ("src/dangling/**",)})
        self.prime_registry_lock()
        before = self.coordination_snapshot()

        refused = self.open_run("run-after-dangling", "other/**")

        self.assertEqual(refused.returncode, 1)
        self.assertEqual(refused.stdout, "")
        self.assertEqual(refused.stderr, journal.REGISTRY_UNAVAILABLE + "\n")
        self.assertEqual(self.coordination_snapshot(), before)
        self.assertFalse(self.run_dir("run-after-dangling").exists())

    def test_persisted_successor_cycle_is_generic_and_nonmutating(self) -> None:
        self.plant_run_state(
            "run-cycle-A",
            ("src/cycle/**",),
            successor_of="run-cycle-B",
            retired=True,
        )
        self.plant_run_state(
            "run-cycle-B",
            ("src/cycle/branch/**",),
            successor_of="run-cycle-A",
            retired=True,
        )
        self.write_registry({})
        self.prime_registry_lock()
        before = self.coordination_snapshot()

        refused = self.open_run("run-after-cycle", "other/**")

        self.assertEqual(refused.returncode, 1)
        self.assertEqual(refused.stdout, "")
        self.assertEqual(refused.stderr, journal.REGISTRY_UNAVAILABLE + "\n")
        self.assertEqual(self.coordination_snapshot(), before)
        self.assertFalse(self.run_dir("run-after-cycle").exists())

    def test_persisted_disjoint_successor_edge_is_generic_and_nonmutating(self) -> None:
        self.plant_run_state("run-edge-A", ("src/a/**",), retired=True)
        self.plant_run_state(
            "run-edge-B",
            ("src/b/**",),
            successor_of="run-edge-A",
        )
        self.write_registry({"run-edge-B": ("src/b/**",)})
        self.prime_registry_lock()
        before = self.coordination_snapshot()

        refused = self.open_run("run-after-disjoint-edge", "other/**")

        self.assertEqual(refused.returncode, 1)
        self.assertEqual(refused.stdout, "")
        self.assertEqual(refused.stderr, journal.REGISTRY_UNAVAILABLE + "\n")
        self.assertEqual(self.coordination_snapshot(), before)
        self.assertFalse(self.run_dir("run-after-disjoint-edge").exists())

    def test_legacy_successor_close_without_valid_judgment_cannot_release_scope(self) -> None:
        self.plant_run_state("run-legacy-release-A", ("src/legacy/**",), retired=True)
        successor_dir = self.run_dir("run-legacy-release-B")
        successor_dir.mkdir()
        opening = self.opening_record(
            "run-legacy-release-B",
            scope=["src/legacy/branch/**"],
            successor_of="run-legacy-release-A",
        )
        opening["id"] = opening.pop("run_id")
        owner = (
            f"pid: {os.getpid()}\n"
            f"host: {socket.gethostname()}\n"
            f"started_at: {RECORDED_AT}\n"
        )
        (successor_dir / "owner").write_text(owner, encoding="utf-8")
        self.write_registry({})
        self.prime_registry_lock()

        for judgment in (None, "unsafe-release"):
            closure: dict[str, object] = {
                "type": "run_closed",
                "recorded_at": RECORDED_AT,
                "summary": "historical closure must not release ancestry",
            }
            if judgment is not None:
                closure["judgment"] = judgment
            self.journal_path("run-legacy-release-B").write_text(
                "".join(
                    json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
                    for record in (opening, closure)
                ),
                encoding="utf-8",
            )
            before = self.coordination_snapshot()

            with self.subTest(judgment=judgment):
                refused = self.open_run(
                    "run-legacy-release-probe", "src/legacy/probe.py"
                )
                self.assertEqual(refused.returncode, 1)
                self.assertEqual(refused.stdout, "")
                self.assertEqual(
                    refused.stderr, journal.REGISTRY_UNAVAILABLE + "\n"
                )
                self.assertEqual(self.coordination_snapshot(), before)
                self.assertFalse(
                    self.run_dir("run-legacy-release-probe").exists()
                )

    def test_mixed_open_and_retired_conflicts_are_byte_sorted(self) -> None:
        self.assertEqual(
            self.open_run("run-z-open", "src/open/**").returncode, 0
        )
        self.assertEqual(
            self.open_run("run-a-retired", "src/retired/**").returncode, 0
        )
        self.assertEqual(self.retire("run-a-retired").returncode, 0)
        before = self.coordination_snapshot()

        refused = self.open_run("run-mixed", "src/**")

        self.assertEqual(refused.returncode, 1)
        self.assertEqual(
            refused.stderr,
            "forge: new run refused — scope overlap between run-mixed and "
            "scope-reserving retired run run-a-retired\n"
            "forge: new run refused — scope overlap between run-mixed and open run "
            "run-z-open\n",
        )
        self.assertEqual(self.coordination_snapshot(), before)
        self.assertFalse(self.run_dir("run-mixed").exists())

    def test_concurrent_successor_and_ordinary_admission_serialize_atomically(self) -> None:
        self.assertEqual(self.open_run("run-race-A", "src/race/**").returncode, 0)
        self.assertEqual(self.retire("run-race-A").returncode, 0)
        successor_record = self.write_record(
            self.opening_record("run-race-successor"), "race-successor"
        )
        ordinary_record = self.write_record(
            self.opening_record("run-race-ordinary"), "race-ordinary"
        )
        ready_successor = self.root / "successor.ready"
        ready_ordinary = self.root / "ordinary.ready"
        gate = self.root / "admission.gate"
        barrier_program = (
            "import os,sys,time\n"
            "from pathlib import Path\n"
            "ready=Path(sys.argv[1]); gate=Path(sys.argv[2])\n"
            "ready.touch()\n"
            "deadline=time.monotonic()+10\n"
            "while not gate.exists():\n"
            "    if time.monotonic()>deadline: raise SystemExit(97)\n"
            "    time.sleep(0.005)\n"
            "os.execv(sys.executable,[sys.executable,*sys.argv[3:]])\n"
        )
        common = ["--repo", str(self.repo)]
        successor_arguments = [
            "run-open",
            *common,
            "--run-id",
            "run-race-successor",
            "--scope",
            "src/race/successor/**",
            "--record-json",
            str(successor_record),
            "--successor-of",
            "run-race-A",
        ]
        ordinary_arguments = [
            "run-open",
            *common,
            "--run-id",
            "run-race-ordinary",
            "--scope",
            "src/race/ordinary/**",
            "--record-json",
            str(ordinary_record),
        ]
        processes = (
            subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    barrier_program,
                    str(ready_successor),
                    str(gate),
                    str(TOOLS),
                    *successor_arguments,
                ],
                cwd=self.repo,
                env=self.env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            ),
            subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    barrier_program,
                    str(ready_ordinary),
                    str(gate),
                    str(TOOLS),
                    *ordinary_arguments,
                ],
                cwd=self.repo,
                env=self.env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            ),
        )
        deadline = time.monotonic() + 10
        while not (ready_successor.exists() and ready_ordinary.exists()):
            if any(process.poll() is not None for process in processes):
                break
            if time.monotonic() >= deadline:
                break
            time.sleep(0.005)
        both_ready = ready_successor.exists() and ready_ordinary.exists()
        gate.touch()
        results: list[tuple[int, str, str]] = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=20)
            results.append((process.returncode, stdout, stderr))

        self.assertTrue(both_ready, results)
        successor_result, ordinary_result = results
        self.assertEqual(successor_result[0], 0, successor_result)
        self.assertEqual(ordinary_result[0], 1, ordinary_result)
        self.assertEqual(ordinary_result[1], "")
        self.assertIn(
            ordinary_result[2],
            {
                "forge: new run refused — scope overlap between run-race-ordinary "
                "and scope-reserving retired run run-race-A\n",
                "forge: new run refused — scope overlap between run-race-ordinary "
                "and open run run-race-successor\n",
            },
        )
        registry = json.loads(self.registry_path.read_text(encoding="utf-8"))
        self.assertEqual(
            registry["open_runs"],
            [
                {
                    "run_id": "run-race-successor",
                    "scope": ["src/race/successor/**"],
                }
            ],
        )
        self.assertFalse(self.run_dir("run-race-ordinary").exists())

    def test_only_a_retired_successor_may_close_and_release_ancestry(self) -> None:
        self.assertEqual(self.open_run("run-leaf", "src/leaf/**").returncode, 0)
        self.assertEqual(self.retire("run-leaf").returncode, 0)
        before = self.coordination_snapshot()

        refused_root = self.close("run-leaf", judgment="blocked")

        self.assertEqual(refused_root.returncode, 1)
        self.assertEqual(
            refused_root.stderr,
            "forge: run close refused — run run-leaf is retired\n",
        )
        self.assertEqual(self.coordination_snapshot(), before)

        successor = self.open_run(
            "run-leaf-successor",
            "src/leaf/successor/**",
            successor_of="run-leaf",
        )
        self.assertEqual(successor.returncode, 0, successor.stderr)
        self.assertEqual(self.retire("run-leaf-successor").returncode, 0)
        closed = self.close("run-leaf-successor", judgment="blocked")
        self.assertEqual(closed.returncode, 0, closed.stderr)
        reused = self.open_run("run-after-leaf", "src/leaf/reused.py")
        self.assertEqual(reused.returncode, 0, reused.stderr)

    def test_close_rollback_preserves_effective_ancestral_reservation(self) -> None:
        self.assertEqual(self.open_run("run-rollback-A", "src/rollback/**").returncode, 0)
        self.assertEqual(self.retire("run-rollback-A").returncode, 0)
        self.assertEqual(
            self.open_run(
                "run-rollback-B",
                "src/rollback/branch/**",
                successor_of="run-rollback-A",
            ).returncode,
            0,
        )
        self.prime_batch_lock("run-rollback-B")
        before = self.coordination_snapshot()

        with self.api_environment(), mock.patch.object(
            journal, "_write_registry", side_effect=OSError("injected update failure")
        ):
            with self.assertRaises(journal.CoordinationRefusal) as caught:
                journal.close_run(
                    self.repo, "run-rollback-B", self.closure_record("passed")
                )
        self.assertEqual(
            str(caught.exception),
            "forge: run coordination refused — run registry update failed",
        )
        self.assertEqual(self.coordination_snapshot(), before)

        probe = self.open_run("run-rollback-probe", "src/rollback/probe.py")
        self.assertEqual(probe.returncode, 1)
        self.assertEqual(
            probe.stderr,
            "forge: new run refused — scope overlap between run-rollback-probe and "
            "open run run-rollback-B\n",
        )

    def test_release_control_disabled_keeps_retired_ancestry_reserved(self) -> None:
        self.assertEqual(self.open_run("run-release-A", "src/release/**").returncode, 0)
        self.assertEqual(self.retire("run-release-A").returncode, 0)
        self.assertEqual(
            self.open_run(
                "run-release-B",
                "src/release/branch/**",
                successor_of="run-release-A",
            ).returncode,
            0,
        )

        enabled = journal.SUCCESSOR_DAG_CONTROLS
        with self.api_environment(), mock.patch.object(
            journal, "SUCCESSOR_DAG_CONTROLS", enabled - {"release"}
        ):
            journal.close_run(
                self.repo, "run-release-B", self.closure_record("passed")
            )
            with self.assertRaises(journal.CoordinationRefusal) as caught:
                journal.open_run(
                    self.repo,
                    "run-release-probe",
                    ["src/release/probe.py"],
                    self.opening_record("run-release-probe"),
                )
        self.assertEqual(
            str(caught.exception),
            "forge: new run refused — scope overlap between run-release-probe and "
            "scope-reserving retired run run-release-B",
        )
        self.assertFalse(self.run_dir("run-release-probe").exists())

    def test_historical_fork_releases_shared_ancestor_only_after_both_branches_close(self) -> None:
        self.assertEqual(self.open_run("run-fork-A", "src/shared/**").returncode, 0)
        self.assertEqual(self.retire("run-fork-A").returncode, 0)
        self.assertEqual(
            self.open_run(
                "run-fork-B", "src/shared/b/**", successor_of="run-fork-A"
            ).returncode,
            0,
        )

        fork_c = self.run_dir("run-fork-C")
        fork_c.mkdir()
        opening_c = self.opening_record("run-fork-C")
        opening_c["scope"] = ["src/shared/c/**"]
        opening_c["successor_of"] = "run-fork-A"
        (fork_c / "journal.jsonl").write_text(
            json.dumps(opening_c, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        (fork_c / "owner").write_text(
            f"pid: {os.getpid()}\nhost: {socket.gethostname()}\n"
            f"started_at: {RECORDED_AT}\n",
            encoding="utf-8",
        )
        self.write_registry(
            {
                "run-fork-B": ("src/shared/b/**",),
                "run-fork-C": ("src/shared/c/**",),
            }
        )

        closed_b = self.close("run-fork-B")
        self.assertEqual(closed_b.returncode, 0, closed_b.stderr)
        still_reserved = self.open_run("run-fork-probe", "src/shared/probe.py")
        self.assertEqual(still_reserved.returncode, 1)
        self.assertEqual(
            still_reserved.stderr,
            "forge: new run refused — scope overlap between run-fork-probe and "
            "open run run-fork-C\n",
        )

        closed_c = self.close("run-fork-C")
        self.assertEqual(closed_c.returncode, 0, closed_c.stderr)
        released = self.open_run("run-fork-probe", "src/shared/probe.py")
        self.assertEqual(released.returncode, 0, released.stderr)
