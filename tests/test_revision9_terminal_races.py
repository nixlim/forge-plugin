"""Process-level coverage for Revision-9 terminal/chain serialization."""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import multiprocessing
import os
import sys
import time
import traceback
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = ROOT / "scripts" / "forge" / "cli.py"
HARNESS_TIMEOUT_SECONDS = 45.0


from tests._cli_loader import load_cached as load_script  # cli split phase 0: one shared loader


CLI = load_script("forge_revision9_terminal_race_cli", CLI_PATH)
CLI_FIXTURE_SUPPORT = load_script(
    "forge_revision9_terminal_race_fixture_support",
    ROOT / "tests" / "test_cli_chain.py",
)


def key(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _write_result(path: str, value: dict[str, object]) -> None:
    Path(path).write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


@contextmanager
def _controlled_outer_lock(
    original: object,
    target_run_dir: Path,
    *,
    first: bool,
    first_acquired: object,
    contender_attempted: object,
    timing: dict[str, object],
):
    """Patch target used by a worker; the yielded value is a context manager."""

    announced = False

    @contextmanager
    def controlled(run_dir: Path, *, create: bool):
        nonlocal announced
        target = os.path.abspath(os.fspath(target_run_dir))
        matches = os.path.abspath(os.fspath(run_dir)) == target
        if matches and not announced and not first:
            if not first_acquired.wait(timeout=15):
                raise TimeoutError("designated first process did not acquire the outer lock")
            contender_attempted.set()
            announced = True
        with original(run_dir, create=create) as locked:  # type: ignore[misc,operator]
            if matches and not announced:
                announced = True
                timing["outer_lock_acquired_ns"] = time.monotonic_ns()
                first_acquired.set()
                if not contender_attempted.wait(timeout=15):
                    raise TimeoutError("contender did not attempt the outer lock")
            elif matches and "outer_lock_acquired_ns" not in timing:
                timing["outer_lock_acquired_ns"] = time.monotonic_ns()
            yield locked

    yield controlled


def _race_worker(
    config: dict[str, object],
    actor: str,
    first_actor: str,
    start_barrier: object,
    first_acquired: object,
    contender_attempted: object,
    result_path: str,
) -> None:
    """Run one chain or terminal operation in its own lock-owning process."""

    result: dict[str, object] = {
        "actor": actor,
        "first": actor == first_actor,
        "pid": os.getpid(),
    }
    timing: dict[str, object] = {}
    try:
        batch, builders, journal = CLI._coordination_modules()
        environment = dict(config["environment"])
        target_run_dir = Path(str(config["run_dir"]))
        original_batch_lock = batch.batch_lock
        start_barrier.wait(timeout=15)
        with _controlled_outer_lock(
            original_batch_lock,
            target_run_dir,
            first=actor == first_actor,
            first_acquired=first_acquired,
            contender_attempted=contender_attempted,
            timing=timing,
        ) as controlled_lock, mock.patch.dict(
            os.environ, environment, clear=True
        ), mock.patch.object(
            batch, "batch_lock", controlled_lock
        ), mock.patch.object(
            CLI, "SCRIPT_DIR", Path(str(config["helpers"]))
        ), mock.patch.object(
            CLI, "PLUGIN_ROOT", ROOT
        ), mock.patch.object(
            CLI,
            "CODEX_EXECUTABLE",
            str(Path(str(config["helpers"])) / "fake-codex"),
        ):
            if actor == "chain":
                stdout = io.StringIO()
                stderr = io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(
                    stderr
                ):
                    exit_code = CLI.main(list(config["chain_argv"]))
                lines = stdout.getvalue().splitlines()
                if len(lines) != 1:
                    raise AssertionError(
                        "chain CLI did not emit exactly one JSON envelope: "
                        f"stdout={stdout.getvalue()!r}; stderr={stderr.getvalue()!r}"
                    )
                envelope = json.loads(lines[0])
                result.update(
                    {
                        "exit_code": exit_code,
                        "ok": bool(envelope.get("ok")),
                        "reason_code": envelope.get("reason_code"),
                        "schema": envelope.get("schema"),
                        "state": envelope.get("state"),
                        "chain_id": envelope.get("chain_id"),
                        "stderr": stderr.getvalue(),
                    }
                )
            elif actor == "terminal":
                try:
                    if config["terminal"] == "task-finish":
                        outcome = builders.task_finish(
                            Path(str(config["repo"])),
                            str(config["run_id"]),
                            idempotency_key=str(config["terminal_key"]),
                            task="task-01",
                            status="complete",
                        )
                    else:
                        outcome = builders.run_close(
                            Path(str(config["repo"])),
                            str(config["run_id"]),
                            idempotency_key=str(config["terminal_key"]),
                            judgment="blocked",
                            summary="Serialize the terminal journal boundary",
                            risks=[],
                            follow_ups=[],
                        )
                except journal.CoordinationRefusal as exc:
                    result.update({"ok": False, "error": str(exc)})
                else:
                    result.update(
                        {
                            "ok": True,
                            "record_type": outcome.records[0].get("type"),
                            "repeated": outcome.repeated,
                        }
                    )
            else:
                raise AssertionError(f"unknown actor {actor}")
    except BaseException:
        result["traceback"] = traceback.format_exc()
        try:
            start_barrier.abort()
        except BaseException:
            pass
    finally:
        result.update(timing)
        _write_result(result_path, result)


class Revision9TerminalRaceTests(CLI_FIXTURE_SUPPORT.ForgeCLIFixture):
    """Exercise the real DM-012 journal-outer lock in separate processes."""

    def revision9_environment(self) -> dict[str, str]:
        return self.environment(FORGE_SESSION_PID=str(os.getpid()))

    @contextmanager
    def cli_context(self):
        with mock.patch.dict(
            os.environ, self.revision9_environment(), clear=True
        ), mock.patch.object(
            CLI, "SCRIPT_DIR", self.helpers
        ), mock.patch.object(
            CLI, "PLUGIN_ROOT", ROOT
        ), mock.patch.object(
            CLI, "CODEX_EXECUTABLE", str(self.helpers / "fake-codex")
        ):
            yield

    def invoke_cli(self, *argv: str) -> dict[str, object]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with self.cli_context(), contextlib.redirect_stdout(
            stdout
        ), contextlib.redirect_stderr(stderr):
            exit_code = CLI.main(
                ["--json", "--repo", str(self.repo), *argv]
            )
        self.assertEqual(exit_code, 0, stdout.getvalue() + stderr.getvalue())
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(stdout.getvalue().count("\n"), 1)
        envelope = json.loads(stdout.getvalue())
        self.assertTrue(envelope["ok"], envelope)
        self.assertEqual(envelope["schema"], "forge-cli/2")
        return envelope

    def open_run_and_task(self, run_id: str) -> None:
        _batch, builders, _journal = CLI._coordination_modules()
        with self.cli_context():
            builders.run_open(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-open"),
                goal="Exercise the terminal/chain serialization boundary",
                scope=["docs/**"],
                plugin_ref="forge-revision9-terminal-race-tests",
            )
            builders.task_start(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-task"),
                task="task-01",
                goal="Serialize one bound chain against terminal journal state",
                acceptance=["The journal-outer race has one valid order"],
                files=["docs/guide.md"],
            )

    def prepare_case(self, action: str, run_id: str) -> str | None:
        self.open_run_and_task(run_id)
        self.change("docs/guide.md", f"# Terminal race for {run_id}\n")
        if action == "start":
            return None
        started = self.invoke_cli(
            "--run-id",
            run_id,
            "commit",
            "start",
            "--paths",
            "docs/guide.md",
            "--task",
            "task-01",
        )
        chain_id = str(started["chain_id"])
        verified = self.invoke_cli("--chain-id", chain_id, "verify")
        self.assertEqual(verified["state"], "authorized")
        return chain_id

    def _terminate_processes(
        self, processes: tuple[multiprocessing.Process, ...]
    ) -> None:
        for process in processes:
            if process.is_alive():
                process.terminate()
        for process in processes:
            process.join(5)

    def run_race(
        self, action: str, terminal: str, order: str
    ) -> tuple[dict[str, object], dict[str, object], str]:
        label = f"{action}-{terminal}-{order}"
        run_id = f"run-20260828-terminal-race-{label}"
        chain_id = self.prepare_case(action, run_id)
        run_dir = (
            CLI.Repository(self.repo).common_root()
            / ".codex-orchestrator"
            / "runs"
            / run_id
        )
        if action == "start":
            chain_arguments = [
                "--json",
                "--repo",
                str(self.repo),
                "--run-id",
                run_id,
                "commit",
                "start",
                "--paths",
                "docs/guide.md",
                "--task",
                "task-01",
            ]
        else:
            self.assertIsNotNone(chain_id)
            chain_arguments = [
                "--json",
                "--repo",
                str(self.repo),
                "--chain-id",
                str(chain_id),
                "commit",
                "finalize",
                "--message",
                f"Finalize {label}",
            ]
        config: dict[str, object] = {
            "chain_argv": chain_arguments,
            "environment": self.revision9_environment(),
            "helpers": str(self.helpers),
            "repo": str(self.repo),
            "run_dir": str(run_dir),
            "run_id": run_id,
            "terminal": terminal,
            "terminal_key": key(f"{run_id}-{terminal}"),
        }
        context = multiprocessing.get_context("fork")
        start_barrier = context.Barrier(2)
        first_acquired = context.Event()
        contender_attempted = context.Event()
        first_actor = "chain" if order == "chain-first" else "terminal"
        result_paths = {
            actor: self.temp_root / f"{label}-{actor}.json"
            for actor in ("chain", "terminal")
        }
        processes = tuple(
            context.Process(
                target=_race_worker,
                args=(
                    config,
                    actor,
                    first_actor,
                    start_barrier,
                    first_acquired,
                    contender_attempted,
                    str(result_paths[actor]),
                ),
            )
            for actor in ("chain", "terminal")
        )
        for process in processes:
            process.start()
        self.addCleanup(self._terminate_processes, processes)
        deadline = time.monotonic() + HARNESS_TIMEOUT_SECONDS
        for process in processes:
            process.join(max(0.1, deadline - time.monotonic()))
        alive = [process for process in processes if process.is_alive()]
        self._terminate_processes(tuple(alive))
        self.assertEqual(alive, [], f"{label} deadlocked")
        self.assertTrue(
            all(process.exitcode == 0 for process in processes),
            f"{label} worker process failed before recording a result",
        )
        results = {
            actor: json.loads(result_paths[actor].read_text(encoding="utf-8"))
            for actor in ("chain", "terminal")
        }
        self.assertNotIn("traceback", results["chain"], results["chain"])
        self.assertNotIn("traceback", results["terminal"], results["terminal"])
        self.assertEqual(results[first_actor]["first"], True)
        contender = "terminal" if first_actor == "chain" else "chain"
        self.assertEqual(results[contender]["first"], False)
        self.assertLess(
            int(results[first_actor]["outer_lock_acquired_ns"]),
            int(results[contender]["outer_lock_acquired_ns"]),
            results,
        )
        return results["chain"], results["terminal"], run_id

    def terminal_records(
        self, records: list[dict[str, object]], terminal: str
    ) -> list[dict[str, object]]:
        if terminal == "task-finish":
            return [
                record
                for record in records
                if record.get("type") == "task"
                and record.get("id") == "task-01"
                and record.get("status") in {"complete", "blocked", "failed"}
            ]
        return [record for record in records if record.get("type") == "run_closed"]

    def assert_durable_serialization(
        self,
        *,
        action: str,
        terminal: str,
        order: str,
        chain_result: dict[str, object],
        terminal_result: dict[str, object],
        run_id: str,
    ) -> None:
        batch, builders, journal = CLI._coordination_modules()
        self.assertEqual(chain_result.get("stderr"), "")
        if action == "start":
            if order == "chain-first":
                self.assertTrue(chain_result["ok"], chain_result)
                self.assertFalse(terminal_result["ok"], terminal_result)
                self.assertEqual(
                    terminal_result.get("error"), builders.TERMINAL_CHAIN_INVALID
                )
            else:
                self.assertTrue(terminal_result["ok"], terminal_result)
                self.assertFalse(chain_result["ok"], chain_result)
                self.assertEqual(
                    chain_result.get("reason_code"), "run-task-binding-invalid"
                )
        else:
            self.assertTrue(chain_result["ok"], chain_result)
            if order == "chain-first":
                self.assertTrue(terminal_result["ok"], terminal_result)
            else:
                self.assertFalse(terminal_result["ok"], terminal_result)
                self.assertEqual(
                    terminal_result.get("error"), builders.TERMINAL_CHAIN_INVALID
                )

        common_root = CLI.Repository(self.repo).common_root()
        run_dir = common_root / ".codex-orchestrator" / "runs" / run_id
        records, issues = journal.read_journal(run_dir / "journal.jsonl")
        self.assertEqual(issues, [])
        terminals = self.terminal_records(records, terminal)
        terminal_expected = (
            order == "terminal-first"
            if action == "start"
            else order == "chain-first"
        )
        self.assertEqual(len(terminals), int(terminal_expected), records)
        landings = [
            record
            for record in records
            if record.get("type") == "decision"
            and record.get("outcome") == "chain-landing"
        ]
        self.assertEqual(len(landings), int(action == "mutation"), records)
        if terminals and landings:
            self.assertLess(records.index(landings[0]), records.index(terminals[0]))

        intent_path = run_dir / journal.BATCH_INTENT_NAME
        self.assertFalse(intent_path.exists(), f"pending batch intent: {intent_path}")
        receipt_lines = (
            run_dir / journal.BATCH_RECEIPTS_NAME
        ).read_bytes().splitlines(keepends=True)
        receipts = [json.loads(line) for line in receipt_lines]
        receipt_keys = [str(receipt["idempotency_key"]) for receipt in receipts]
        self.assertEqual(len(receipt_keys), len(set(receipt_keys)), receipts)

        normalized_records = [
            {name: value for name, value in record.items() if name != "_line"}
            for record in records
        ]
        chains_root = common_root / ".forge" / "chains"
        state_paths = (
            sorted(chains_root.glob("c-*.json"))
            if chains_root.exists()
            else []
        )
        if action == "start" and order == "terminal-first":
            self.assertEqual(state_paths, [])
        else:
            self.assertEqual(len(state_paths), 1)
        receipt_counts = {
            receipt_key: receipt_keys.count(receipt_key)
            for receipt_key in receipt_keys
        }
        for state_path in state_paths:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertIsNone(state.get("journal_outbox"), state)
            event_path = state_path.with_name(
                state_path.name.removesuffix(".json") + ".events.jsonl"
            )
            events = [
                json.loads(line)
                for line in event_path.read_text(encoding="utf-8").splitlines()
            ]
            for event in events:
                details = event.get("payload", {}).get("details", {})
                carried = (
                    details.get("journal_batch")
                    if isinstance(details, dict)
                    else None
                )
                if not isinstance(carried, dict):
                    continue
                source_key = str(carried["idempotency_key"])
                self.assertEqual(receipt_counts.get(source_key), 1, (event, receipts))
                for carried_record in carried["records"]:
                    self.assertEqual(
                        normalized_records.count(carried_record),
                        1,
                        (carried_record, normalized_records),
                    )
        if terminals:
            self.assertTrue(
                all(
                    json.loads(path.read_text(encoding="utf-8")).get(
                        "journal_outbox"
                    )
                    is None
                    for path in state_paths
                ),
                "terminal journal coexists with a non-null chain outbox",
            )
        self.assertTrue(
            all(set(receipt) == batch._receipt_keys() for receipt in receipts)
        )

    def chain_context(
        self, chain_id: str, *, original_argv: tuple[str, ...] = ()
    ) -> object:
        repository = CLI.Repository(self.repo)
        return CLI.CommandContext(
            repo=repository,
            store=CLI.ChainStore(repository.common_root()),
            options=CLI.CLIOptions(
                repo=str(self.repo),
                chain_id=chain_id,
                revision9_face=True,
                original_argv=original_argv,
            ),
        )

    def start_bound_chain_before_verification(self, run_id: str) -> str:
        self.open_run_and_task(run_id)
        self.change("docs/guide.md", f"# Pending outbox for {run_id}\n")
        started = self.invoke_cli(
            "--run-id",
            run_id,
            "commit",
            "start",
            "--paths",
            "docs/guide.md",
            "--task",
            "task-01",
        )
        return str(started["chain_id"])

    def load_chain_under_outer(
        self, context: object, run_id: str, chain_id: str
    ) -> dict[str, object]:
        batch, _builders, _journal = CLI._coordination_modules()
        run_dir = (
            CLI.Repository(self.repo).common_root()
            / ".codex-orchestrator"
            / "runs"
            / run_id
        )
        with self.cli_context(), batch.batch_lock(run_dir, create=False):
            return context.store.load(chain_id)

    def leave_pending_verification_outbox(self, run_id: str) -> str:
        chain_id = self.start_bound_chain_before_verification(run_id)
        batch, _builders, _journal = CLI._coordination_modules()
        context = self.chain_context(chain_id)
        with self.cli_context(), mock.patch.object(
            batch,
            "drain_chain_batch",
            side_effect=RuntimeError("injected crash after pending transition"),
        ), self.assertRaisesRegex(RuntimeError, "pending transition"):
            CLI.Engine(context).verify()
        state = self.load_chain_under_outer(context, run_id, chain_id)
        self.assertIsInstance(state.get("journal_outbox"), dict)
        return chain_id

    def leave_pending_finalize_outbox(self, run_id: str) -> str:
        chain_id = self.prepare_case("mutation", run_id)
        self.assertIsNotNone(chain_id)
        batch, _builders, _journal = CLI._coordination_modules()
        arguments = (
            "commit",
            "finalize",
            "--message",
            "Create the pending finalize outbox",
        )
        context = self.chain_context(str(chain_id), original_argv=arguments)
        with self.cli_context(), mock.patch.object(
            batch,
            "drain_chain_batch",
            side_effect=RuntimeError("injected crash after pending finalize"),
        ), self.assertRaisesRegex(RuntimeError, "pending finalize"):
            CLI.Engine(context).finalize("Create the pending finalize outbox")
        state = self.load_chain_under_outer(context, run_id, str(chain_id))
        self.assertEqual(state.get("state"), "committing")
        self.assertIsInstance(state.get("journal_outbox"), dict)
        return str(chain_id)

    def relevant_bytes(
        self, run_id: str, chain_id: str
    ) -> dict[str, bytes]:
        common_root = CLI.Repository(self.repo).common_root()
        run_dir = common_root / ".codex-orchestrator" / "runs" / run_id
        chains_root = common_root / ".forge" / "chains"
        snapshot: dict[str, bytes] = {
            "git-head": self.git_bytes("rev-parse", "HEAD"),
            "git-status": self.git_bytes(
                "status", "--porcelain=v1", "--untracked-files=all"
            ),
        }
        for label, root in (("run", run_dir), ("chains", chains_root)):
            if not root.exists():
                continue
            for path in sorted(root.rglob("*"), key=lambda item: os.fsencode(item)):
                if path.is_file() and (
                    label == "run"
                    or path.name.startswith(chain_id)
                    or path.name.startswith(f".{chain_id}.")
                ):
                    snapshot[f"{label}:{path.relative_to(root)}"] = path.read_bytes()
        registry = common_root / ".forge" / "tmp" / "run-registry.json"
        if registry.exists():
            snapshot["registry"] = registry.read_bytes()
        return snapshot

    def assert_pending_cli_refusal(self, raised: BaseException) -> None:
        self.assertIsInstance(raised, CLI.Refusal)
        refusal = raised
        self.assertEqual(
            refusal.reason_code.value, "journal-outbox-pending"  # type: ignore[attr-defined]
        )
        self.assertEqual(
            refusal.message,  # type: ignore[attr-defined]
            "forge: chain transition refused — journal outbox is pending",
        )

    def test_pending_outbox_refuses_later_chain_transition_without_mutation(
        self,
    ) -> None:
        run_id = "run-20260828-pending-transition-refusal"
        chain_id = self.leave_pending_verification_outbox(run_id)
        context = self.chain_context(chain_id)
        state = self.load_chain_under_outer(context, run_id, chain_id)
        before = self.relevant_bytes(run_id, chain_id)
        with self.cli_context(), self.assertRaises(CLI.Refusal) as raised:
            context.store.persist(
                state,
                "candidate_staged",
                {"candidate": state["candidate"]["sha256"]},
            )
        self.assert_pending_cli_refusal(raised.exception)
        self.assertEqual(self.relevant_bytes(run_id, chain_id), before)

    def test_pending_outbox_refuses_finalize_without_mutation(self) -> None:
        run_id = "run-20260828-pending-finalize-refusal"
        chain_id = self.leave_pending_finalize_outbox(run_id)
        before = self.relevant_bytes(run_id, chain_id)
        arguments = (
            "commit",
            "finalize",
            "--message",
            "Refuse the pending finalize outbox",
        )
        context = self.chain_context(chain_id, original_argv=arguments)
        with self.cli_context(), mock.patch.object(
            context.store,
            "recover_pending_outbox",
            side_effect=lambda state: state,
        ), self.assertRaises(CLI.Refusal) as raised:
            CLI.Engine(context).finalize("Refuse the pending finalize outbox")
        self.assert_pending_cli_refusal(raised.exception)
        self.assertEqual(self.relevant_bytes(run_id, chain_id), before)

    def test_pending_outbox_refuses_run_close_without_mutation(self) -> None:
        run_id = "run-20260828-pending-run-close-refusal"
        chain_id = self.leave_pending_verification_outbox(run_id)
        _batch, builders, journal = CLI._coordination_modules()
        before = self.relevant_bytes(run_id, chain_id)
        with self.cli_context(), self.assertRaises(
            journal.CoordinationRefusal
        ) as raised:
            builders.run_close(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-close"),
                judgment="blocked",
                summary="Refuse close until the chain outbox is receipted",
                risks=[],
                follow_ups=[],
            )
        self.assertEqual(str(raised.exception), builders.JOURNAL_OUTBOX_PENDING)
        self.assertEqual(self.relevant_bytes(run_id, chain_id), before)

    def exercise_case(self, action: str, terminal: str, order: str) -> None:
        chain_result, terminal_result, run_id = self.run_race(
            action, terminal, order
        )
        self.assert_durable_serialization(
            action=action,
            terminal=terminal,
            order=order,
            chain_result=chain_result,
            terminal_result=terminal_result,
            run_id=run_id,
        )

    def test_start_task_finish_chain_first(self) -> None:
        self.exercise_case("start", "task-finish", "chain-first")

    def test_start_task_finish_terminal_first(self) -> None:
        self.exercise_case("start", "task-finish", "terminal-first")

    def test_start_run_close_chain_first(self) -> None:
        self.exercise_case("start", "run-close", "chain-first")

    def test_start_run_close_terminal_first(self) -> None:
        self.exercise_case("start", "run-close", "terminal-first")

    def test_mutation_task_finish_chain_first(self) -> None:
        self.exercise_case("mutation", "task-finish", "chain-first")

    def test_mutation_task_finish_terminal_first(self) -> None:
        self.exercise_case("mutation", "task-finish", "terminal-first")

    def test_mutation_run_close_chain_first(self) -> None:
        self.exercise_case("mutation", "run-close", "chain-first")

    def test_mutation_run_close_terminal_first(self) -> None:
        self.exercise_case("mutation", "run-close", "terminal-first")


if __name__ == "__main__":
    unittest.main()
