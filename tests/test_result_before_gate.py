"""Result-before-gate refusal and overlap tests (Revision 18, FR-249)."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shlex
import sys
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests._cli_loader import (
    load_cli,
    load_script,
    package_module,
    patch_engine,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from codex_orchestrator import journal, result_gate  # noqa: E402

CLI = load_cli("forge_result_before_gate_tests")
FIXTURE = load_script(
    "forge_result_gate_fixture_support", ROOT / "tests" / "test_cli_chain.py"
)
RUNTIME = package_module("runtime")
CORE = package_module("chain_core")
COMMAND_LOCK = package_module("engine._command_lock")
MERGE_GATE = package_module("app._engine_gate")
MERGE_REVIEW_LAUNCH = package_module("app._engine_review_launch")
SPEC = (ROOT / "docs/specs/forge-plugin-spec.md").read_text(encoding="utf-8")


def key(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def activated_records(*records: dict[str, object]) -> list[dict[str, object]]:
    opening: dict[str, object] = {
        "type": "run_started",
        "writer_contract": journal.WRITER_CONTRACT,
    }
    return [opening, *records]


def task_record(task: str, *files: str) -> dict[str, object]:
    return {"type": "task", "id": task, "status": "active", "files": list(files)}


def execution_record(
    number: int,
    task: str,
    *,
    role: str = "implementer",
    launched: bool = False,
) -> dict[str, object]:
    record: dict[str, object] = {
        "type": "execution",
        "execution": f"execution-{number:02d}",
        "agent": "codex-impl-01",
        "task": task,
        "role": role,
    }
    if launched:
        record["launch_marker"] = f"launch/{number}"
    return record


class ResultGateUnitTests(unittest.TestCase):
    def test_pending_partition_overlap_exemptions_and_roles(self) -> None:
        records = activated_records(
            task_record("task-01", "src/app.py"),
            task_record("task-02", "src/**"),
            task_record("task-03", "docs/**"),
            task_record("task-04", "CHANGELOG.md"),
            execution_record(1, "task-01"),
            execution_record(2, "task-02"),
            execution_record(3, "task-03"),
            execution_record(4, "task-04"),
            execution_record(5, "task-01", role="review-cheap"),
            execution_record(6, "task-01", role="plan"),
            {
                "type": "execution_result",
                "execution": "execution-03",
                "agent": "codex-impl-01",
                "task": "task-03",
                "status": "complete",
            },
        )

        blocking, advisory = result_gate.pending_mutations(
            records,
            chain_task="task-01",
            chain_paths=("src/app.py", "CHANGELOG.md"),
            exempt_paths=("CHANGELOG.md",),
        )

        self.assertEqual(
            [pending.execution for pending in blocking],
            ["execution-01", "execution-02"],
        )
        self.assertEqual(
            [pending.execution for pending in advisory], ["execution-04"]
        )

    def test_blocking_refusal_suppresses_advisory_warning(self) -> None:
        records = activated_records(
            task_record("task-01", "src/app.py"),
            task_record("task-02", "docs/guide.md"),
            execution_record(1, "task-01"),
            execution_record(2, "task-02"),
        )
        request = COMMAND_LOCK._ResultGateRequest(
            "run-result-order",
            "verify",
            "task-01",
            ("src/app.py",),
            frozenset(),
            None,
        )

        def assert_quiet_refusal() -> None:
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr), self.assertRaises(
                COMMAND_LOCK.Refusal
            ):
                COMMAND_LOCK._enforce_pending_result(records, request)
            self.assertEqual(stderr.getvalue(), "")

        assert_quiet_refusal()
        original = COMMAND_LOCK._enforce_pending_result

        def warn_before_block(current_records, current_request) -> None:
            _blocking, advisory = result_gate.pending_mutations(
                current_records,
                chain_task=current_request.task,
                chain_paths=current_request.paths,
                exempt_paths=current_request.exempt_paths,
            )
            for pending in advisory:
                print(result_gate.warning_message(pending), file=sys.stderr)
            original(current_records, current_request)

        with mock.patch.object(
            COMMAND_LOCK,
            "_enforce_pending_result",
            side_effect=warn_before_block,
        ), self.assertRaises(AssertionError):
            assert_quiet_refusal()

    def test_terminal_authority_and_legacy_tolerance_match_close_law(self) -> None:
        terminal = activated_records(
            task_record("task-01", "src/app.py"),
            execution_record(1, "task-01"),
            {
                "type": "execution_result",
                "execution": "execution-01",
                "agent": "codex-impl-01",
                "task": "task-01",
                "status": "complete",
            },
        )
        self.assertEqual(
            result_gate.pending_mutations(
                terminal,
                chain_task="task-01",
                chain_paths=("src/app.py",),
                exempt_paths=(),
            ),
            ([], []),
        )

        legacy = activated_records(
            task_record("task-01", "src/app.py"),
            execution_record(1, "task-01"),
            {
                "type": "decision",
                "id": journal.LEGACY_COMPATIBILITY_DECLARATION_ID,
                "resolution": journal.LEGACY_COMPATIBILITY_RESOLUTION_PREFIX
                + "fixture",
            },
        )
        self.assertEqual(
            result_gate.pending_mutations(
                legacy,
                chain_task="task-01",
                chain_paths=("src/app.py",),
                exempt_paths=(),
            ),
            ([], []),
        )

        inactive = [dict(record) for record in terminal]
        inactive[0].pop("writer_contract")
        inactive.pop()
        self.assertEqual(
            result_gate.pending_mutations(
                inactive,
                chain_task="task-01",
                chain_paths=("src/app.py",),
                exempt_paths=(),
            ),
            ([], []),
        )

    def test_launch_marker_selects_the_pinned_remediation(self) -> None:
        prose = result_gate.Pending(
            "execution-05", "task-01", "untrusted-agent", False
        )
        launched = result_gate.Pending(
            "execution-06", "task-01", "untrusted-agent", True
        )
        self.assertEqual(
            result_gate.remediation(prose, "run-example"),
            "python3 scripts/codex_orch_tools.py journal execution-result "
            "--repo <repo> --run-id run-example --idempotency-key <64-hex> "
            "--execution execution-05 --agent <agent> --task task-01 "
            "--status <complete|blocked|failed> --summary <text>",
        )
        self.assertEqual(
            result_gate.remediation(launched, "run-example"),
            "forge launch collect --repo <repo> --run-id run-example "
            "--execution execution-06",
        )
        self.assertNotIn("untrusted-agent", result_gate.remediation(prose, "run-example"))

    def test_hostile_task_identifier_is_one_quoted_shell_word(self) -> None:
        hostile = "t 1; echo pwned"
        pending = result_gate.Pending(
            "execution-05", hostile, "untrusted-agent", False
        )

        def assert_quoted() -> None:
            command = result_gate.remediation(pending, "run-example")
            argv = shlex.split(command)
            self.assertEqual(argv[argv.index("--task") + 1], hostile)
            self.assertIn("--task 't 1; echo pwned'", command)
            self.assertIn(
                "(task 't 1; echo pwned')",
                result_gate.refusal_message("verify", pending),
            )

        assert_quoted()
        with mock.patch.object(
            result_gate.shlex, "quote", side_effect=lambda value: value
        ), self.assertRaises(AssertionError):
            assert_quoted()

    def test_spec_pins_commit_family_scope_and_reason_row(self) -> None:
        self.assertIn("the commit-family run-bound chain verbs", SPEC)
        self.assertIn(
            "Merge-family chains are outside this control: "
            "`MergeEngine.review_request`, `merge verify`, and `merge gate run`",
            SPEC,
        )
        self.assertIn(
            "| `execution-result-pending` | 1 | A commit-family run-bound "
            "chain verb found a mutating execution",
            SPEC,
        )

    def test_route_j_prefixes_block_in_journal_order(self) -> None:
        records = activated_records(
            task_record("task-01", "src/**"),
            execution_record(5, "task-01"),
            execution_record(6, "task-01"),
            {
                "type": "execution_result",
                "execution": "execution-05",
                "agent": "codex-impl-01",
                "task": "task-01",
                "status": "complete",
            },
            {
                "type": "execution_result",
                "execution": "execution-06",
                "agent": "codex-impl-01",
                "task": "task-01",
                "status": "complete",
            },
        )
        cases = (
            (records[:3], ["execution-05"]),
            (records[:4], ["execution-05", "execution-06"]),
            (records[:5], ["execution-06"]),
            (records, []),
        )
        for prefix, expected in cases:
            with self.subTest(lines=len(prefix)):
                blocking, _advisory = result_gate.pending_mutations(
                    prefix,
                    chain_task="task-02",
                    chain_paths=("src/app.py",),
                    exempt_paths=(),
                )
                self.assertEqual([item.execution for item in blocking], expected)

    def test_control_disable_restores_empty_prior_result(self) -> None:
        records = activated_records(
            task_record("task-01", "src/app.py"), execution_record(1, "task-01")
        )

        def assert_blocked() -> None:
            blocking, _advisory = result_gate.pending_mutations(
                records,
                chain_task="task-01",
                chain_paths=("src/app.py",),
                exempt_paths=(),
            )
            self.assertEqual([item.execution for item in blocking], ["execution-01"])

        assert_blocked()
        with mock.patch.object(
            result_gate,
            "RESULT_GATE_CONTROLS",
            result_gate.RESULT_GATE_CONTROLS - {"result-before-gate"},
        ), self.assertRaises(AssertionError):
            assert_blocked()


class ResultBeforeGateIntegrationTests(FIXTURE.ForgeCLIFixture):
    @contextlib.contextmanager
    def cli_process_context(self):
        environment = self.environment(FORGE_SESSION_PID=str(os.getpid()))
        with (
            mock.patch.dict(os.environ, environment, clear=True),
            mock.patch.object(RUNTIME, "SCRIPT_DIR", self.helpers),
            mock.patch.object(RUNTIME, "PLUGIN_ROOT", ROOT),
            patch_engine("CODEX_EXECUTABLE", str(self.helpers / "fake-codex")),
            patch_engine("CLAUDE_EXECUTABLE", str(self.helpers / "fake-claude")),
        ):
            yield

    def invoke_cli(
        self, *argv: str
    ) -> tuple[int, dict[str, object], str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            self.cli_process_context(),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = CLI.main(["--json", "--repo", str(self.repo), *argv])
        self.assertEqual(stdout.getvalue().count("\n"), 1)
        envelope = json.loads(stdout.getvalue())
        self.assertEqual(set(envelope), FIXTURE.ENVELOPE_KEYS)
        return exit_code, envelope, stderr.getvalue()

    def open_run(
        self,
        run_id: str,
        *,
        scope: tuple[str, ...] = ("src/**",),
        tasks: tuple[tuple[str, tuple[str, ...]], ...] = (
            ("task-01", ("src/app.py",)),
        ),
    ) -> dict[str, object]:
        _batch, builders, _journal = CLI._coordination_modules()
        with self.cli_process_context():
            opened = builders.run_open(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-open"),
                goal="Exercise result-before-gate",
                scope=scope,
                plugin_ref="forge-result-gate-tests",
            )
            for task, files in tasks:
                builders.task_start(
                    self.repo,
                    run_id,
                    idempotency_key=key(f"{run_id}-{task}"),
                    task=task,
                    goal=f"Exercise {task}",
                    acceptance=["Pending work is legible"],
                    files=files,
                )
        run_dir = self.repo / ".codex-orchestrator" / "runs" / run_id
        for name in ("prompt.md", "events.jsonl", "handoff.md"):
            (run_dir / name).write_text("fixture evidence\n", encoding="utf-8")
        return dict(opened.records[0])

    def open_activated_legacy_run(self, run_id: str) -> Path:
        opening = {
            "type": "run_started",
            "recorded_at": "2026-09-30T12:00:00Z",
            "run_id": run_id,
            "goal": "Exercise legacy result tolerance",
            "repo": str(self.repo.resolve()),
            "repo_head": self.git("rev-parse", "HEAD"),
            "repo_status": [],
            "plugin_ref": "forge-result-gate-tests",
        }
        with self.cli_process_context(), contextlib.redirect_stderr(io.StringIO()):
            journal.open_run(self.repo, run_id, ["src/**"], opening)
        run_dir = self.repo / ".codex-orchestrator" / "runs" / run_id
        historical = (
            {
                "type": "task",
                "id": "task-01",
                "status": "active",
                "files": ["src/app.py"],
            },
            {
                "type": "execution",
                "execution": "execution-01",
                "agent": "codex-impl-01",
                "task": "task-01",
                "role": "implementer",
            },
            {
                "type": "decision",
                "id": journal.LEGACY_COMPATIBILITY_DECLARATION_ID,
                "resolution": (
                    journal.LEGACY_COMPATIBILITY_RESOLUTION_PREFIX
                    + "pre-activation execution"
                ),
            },
        )
        journal_path = run_dir / "journal.jsonl"
        journal_path.write_bytes(
            journal_path.read_bytes()
            + b"".join(journal._journal_line(record) for record in historical)
        )
        _batch, builders, _journal = CLI._coordination_modules()
        with self.cli_process_context():
            builders.task_start(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-activation"),
                task="task-02",
                goal="Activate the historical run",
                acceptance=["Activation is durable"],
                files=["src/app.py"],
            )
        return run_dir

    def append_execution(
        self,
        run_id: str,
        opening: dict[str, object],
        *,
        task: str = "task-01",
        launched: bool = False,
        role: str = "implementer",
    ) -> dict[str, object]:
        _batch, builders, _journal = CLI._coordination_modules()
        route = opening["route"]["implementer"]
        optional = {
            "sandbox": journal.route_evidence.route_config.profile_sandbox(
                str(route["provider"]), "implementer"
            ),
            "route_source": route["route_source"],
            "route_sha256": route["route_sha256"],
        }
        if launched:
            records, issues = journal.read_journal(
                self.repo
                / ".codex-orchestrator"
                / "runs"
                / run_id
                / "journal.jsonl"
            )
            self.assertEqual(issues, [])
            number = 1 + sum(
                record.get("type") == "execution" for record in records
            )
            optional["launch_marker"] = (
                f"codex-impl-01/execution-{number:02d}/launch.json"
            )
        with self.cli_process_context():
            outcome = builders.execution_start(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-{task}-{launched}-{role}"),
                agent="codex-impl-01",
                task=task,
                provider=str(route["provider"]),
                role=role,
                mode="detached" if launched else "headless",
                model=str(route["model"]),
                effort=str(route["effort"]),
                worktree=str(self.repo.resolve()),
                head=self.git("rev-parse", "HEAD"),
                prompt="prompt.md",
                handoff="handoff.md",
                event_source="exec",
                events="events.jsonl",
                **optional,
            )
        return dict(outcome.records[0])

    def append_result(self, run_id: str, execution: dict[str, object]) -> None:
        _batch, builders, _journal = CLI._coordination_modules()
        with self.cli_process_context():
            builders.execution_result(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-{execution['execution']}-result"),
                execution=str(execution["execution"]),
                agent=str(execution["agent"]),
                task=str(execution["task"]),
                status="complete",
                summary="Execution completed",
                files_changed=(),
                caveats=(),
                handoff="handoff.md",
            )

    def start_chain(self, run_id: str) -> str:
        self.change("src/app.py", "VALUE = 2\n")
        exit_code, envelope, _stderr = self.invoke_cli(
            "--run-id",
            run_id,
            "commit",
            "start",
            "--paths",
            "src/app.py",
            "--task",
            "task-01",
        )
        self.assertEqual(exit_code, 0, envelope)
        return str(envelope["chain_id"])

    def assert_pending_refusal(
        self,
        envelope: dict[str, object],
        *,
        verb: str,
        run_id: str,
        execution: str,
        remediation: str,
    ) -> None:
        self.assertEqual(envelope["reason_code"], "execution-result-pending")
        self.assertEqual(
            envelope["message"],
            f"forge: {verb} refused — execution {execution} (task task-01) "
            "has no terminal execution_result; journal it before gating this candidate",
        )
        self.assertEqual(
            envelope["expected"],
            f"every overlapping mutating execution of run {run_id} "
            "has a terminal execution_result",
        )
        self.assertEqual(envelope["remediation"], remediation)

    def test_commit_start_refuses_before_chain_creation_then_retry_succeeds(self) -> None:
        run_id = "run-20260930-result-start"
        opening = self.open_run(run_id)
        execution = self.append_execution(run_id, opening)
        journal_path = self.repo / ".codex-orchestrator" / "runs" / run_id / "journal.jsonl"
        journal_before = journal_path.read_bytes()
        self.change("src/app.py", "VALUE = 2\n")

        exit_code, envelope, stderr = self.invoke_cli(
            "--run-id", run_id, "commit", "start", "--paths", "src/app.py",
            "--task", "task-01",
        )

        self.assertEqual((exit_code, stderr), (1, ""))
        self.assert_pending_refusal(
            envelope,
            verb="commit start",
            run_id=run_id,
            execution=str(execution["execution"]),
            remediation=(
                "python3 scripts/codex_orch_tools.py journal execution-result "
                f"--repo <repo> --run-id {run_id} --idempotency-key <64-hex> "
                f"--execution {execution['execution']} --agent <agent> --task task-01 "
                "--status <complete|blocked|failed> --summary <text>"
            ),
        )
        self.assertEqual(journal_path.read_bytes(), journal_before)
        chains = self.repo / ".forge" / "chains"
        self.assertFalse(list(chains.glob("c-*.json")))
        self.assertFalse(list(chains.glob("c-*.events.jsonl")))

        self.append_result(run_id, execution)
        chain_id = self.start_chain(run_id)
        self.assertTrue(self.state_path(chain_id).is_file())

    def test_real_command_lock_honors_legacy_missing_result_tolerance(self) -> None:
        run_id = "run-20260930-result-legacy"
        run_dir = self.open_activated_legacy_run(run_id)
        records = journal._scan_run(run_dir).records
        self.assertTrue(journal._writer_contract_active(records))
        self.assertTrue(all("_line" not in record for record in records))
        self.change("src/app.py", "VALUE = 2\n")

        def assert_start_succeeds() -> str:
            exit_code, envelope, stderr = self.invoke_cli(
                "--run-id",
                run_id,
                "commit",
                "start",
                "--paths",
                "src/app.py",
                "--task",
                "task-01",
            )
            self.assertEqual((exit_code, stderr), (0, ""), envelope)
            return str(envelope["chain_id"])

        with mock.patch.object(
            journal, "_legacy_allows", return_value=False
        ), self.assertRaises(AssertionError):
            assert_start_succeeds()
        self.assertFalse(list((self.repo / ".forge/chains").glob("c-*.json")))

        with mock.patch.object(
            journal, "_legacy_allows", wraps=journal._legacy_allows
        ) as tolerance_spy:
            chain_id = assert_start_succeeds()
        self.assertTrue(
            any(
                call.args and call.args[0] == "missing-execution-result"
                for call in tolerance_spy.call_args_list
            )
        )
        exit_code, envelope, stderr = self.invoke_cli(
            "--chain-id", chain_id, "commit", "restage", "--paths", "src/app.py"
        )
        self.assertEqual((exit_code, stderr), (0, ""), envelope)
        with mock.patch.object(journal, "_legacy_allows", return_value=False):
            exit_code, envelope, stderr = self.invoke_cli(
                "--chain-id", chain_id, "verify"
            )
        self.assertEqual((exit_code, stderr), (1, ""))
        self.assertEqual(envelope["reason_code"], "execution-result-pending")

    def test_all_bound_gate_verbs_refuse_with_cli_spelling(self) -> None:
        run_id = "run-20260930-result-verbs"
        opening = self.open_run(run_id)
        chain_id = self.start_chain(run_id)
        execution = self.append_execution(run_id, opening)
        cases = (
            ("commit restage", ("commit", "restage", "--paths", "src/app.py")),
            ("commit rebase", ("commit", "rebase")),
            ("verify", ("verify",)),
            ("gate run", ("gate", "run", "gate-1")),
            ("review request", ("review", "request")),
        )
        remediation = (
            "python3 scripts/codex_orch_tools.py journal execution-result "
            f"--repo <repo> --run-id {run_id} --idempotency-key <64-hex> "
            f"--execution {execution['execution']} --agent <agent> --task task-01 "
            "--status <complete|blocked|failed> --summary <text>"
        )
        for verb, argv in cases:
            with self.subTest(verb=verb):
                exit_code, envelope, stderr = self.invoke_cli(
                    "--chain-id", chain_id, *argv
                )
                self.assertEqual((exit_code, stderr), (1, ""))
                self.assert_pending_refusal(
                    envelope,
                    verb=verb,
                    run_id=run_id,
                    execution=str(execution["execution"]),
                    remediation=remediation,
                )

        self.append_result(run_id, execution)
        exit_code, envelope, stderr = self.invoke_cli(
            "--chain-id", chain_id, "gate", "run", "gate-1"
        )
        self.assertEqual((exit_code, stderr), (0, ""), envelope)

    def test_launch_marker_selects_typed_remediation_in_envelope(self) -> None:
        run_id = "run-20260930-result-typed"
        opening = self.open_run(run_id)
        execution = self.append_execution(run_id, opening, launched=True)
        self.change("src/app.py", "VALUE = 2\n")

        exit_code, envelope, stderr = self.invoke_cli(
            "--run-id", run_id, "commit", "start", "--paths", "src/app.py",
            "--task", "task-01",
        )

        self.assertEqual((exit_code, stderr), (1, ""))
        self.assert_pending_refusal(
            envelope,
            verb="commit start",
            run_id=run_id,
            execution=str(execution["execution"]),
            remediation=(
                f"forge launch collect --repo <repo> --run-id {run_id} "
                f"--execution {execution['execution']}"
            ),
        )

    def test_nonoverlap_warns_once_and_mechanical_output_is_exempt(self) -> None:
        run_id = "run-20260930-result-warning"
        (self.repo / "forge-project.md").write_text(
            FIXTURE.policy_with_changelog(), encoding="utf-8"
        )
        (self.repo / "CHANGELOG.md").write_text("# Changes\n", encoding="utf-8")
        self.git("add", "--", "forge-project.md", "CHANGELOG.md")
        self.git("commit", "--quiet", "-m", "configure changelog output")
        opening = self.open_run(
            run_id,
            scope=("CHANGELOG.md", "docs/**", "src/**"),
            tasks=(
                ("task-01", ("src/app.py", "CHANGELOG.md")),
                ("task-02", ("CHANGELOG.md",)),
            ),
        )
        chain_id = self.start_chain(run_id)
        execution = self.append_execution(run_id, opening, task="task-02")
        (self.repo / "CHANGELOG.md").write_text(
            "# Changes\n- mechanical output\n", encoding="utf-8"
        )

        exit_code, envelope, stderr = self.invoke_cli(
            "--chain-id", chain_id, "commit", "restage", "--paths", "CHANGELOG.md"
        )

        self.assertEqual(exit_code, 0, envelope)
        self.assertEqual(
            stderr.splitlines(),
            [
                result_gate.warning_message(
                    result_gate.Pending(
                        str(execution["execution"]),
                        "task-02",
                        "codex-impl-01",
                        False,
                    )
                )
            ],
        )

    def test_commit_start_emits_each_advisory_once(self) -> None:
        run_id = "run-20260930-result-start-warning"
        opening = self.open_run(
            run_id,
            scope=("docs/**", "src/**"),
            tasks=(
                ("task-01", ("src/app.py",)),
                ("task-02", ("docs/guide.md",)),
            ),
        )
        execution = self.append_execution(run_id, opening, task="task-02")
        self.change("src/app.py", "VALUE = 2\n")

        exit_code, envelope, stderr = self.invoke_cli(
            "--run-id",
            run_id,
            "commit",
            "start",
            "--paths",
            "src/app.py",
            "--task",
            "task-01",
        )

        self.assertEqual(exit_code, 0, envelope)
        self.assertEqual(
            stderr.splitlines(),
            [
                result_gate.warning_message(
                    result_gate.Pending(
                        str(execution["execution"]),
                        "task-02",
                        "codex-impl-01",
                        False,
                    )
                )
            ],
        )

    def test_restage_requested_path_participates_in_overlap(self) -> None:
        run_id = "run-20260930-result-restage-path"
        opening = self.open_run(
            run_id,
            scope=("docs/**", "src/**"),
            tasks=(
                ("task-01", ("docs/guide.md", "src/app.py")),
                ("task-02", ("docs/guide.md",)),
            ),
        )
        chain_id = self.start_chain(run_id)
        execution = self.append_execution(run_id, opening, task="task-02")
        self.change("docs/guide.md", "# Pending overlap\n")

        def assert_refused(path: str) -> None:
            exit_code, envelope, stderr = self.invoke_cli(
                "--chain-id",
                chain_id,
                "commit",
                "restage",
                "--paths",
                path,
            )
            self.assertEqual((exit_code, stderr), (1, ""))
            self.assertEqual(
                envelope["reason_code"], "execution-result-pending"
            )
            self.assertIn(
                f"execution {execution['execution']} (task task-02)",
                envelope["message"],
            )

        for path in (
            "docs/guide.md",
            "./docs/guide.md",
            str(self.repo / "docs/guide.md"),
        ):
            with self.subTest(path=path):
                assert_refused(path)

        def raw_paths(
            _engine: object, method_name: str, args: tuple[object, ...]
        ) -> tuple[str, ...]:
            if method_name != "restage" or not args:
                return ()
            values = args[0]
            if not isinstance(values, (list, tuple)):
                return ()
            return tuple(value for value in values if isinstance(value, str))

        with mock.patch.object(
            COMMAND_LOCK, "_requested_restage_paths", side_effect=raw_paths
        ), self.assertRaises(AssertionError):
            assert_refused("./docs/guide.md")

    def test_pending_inspection_read_errors_have_the_bound_reason(self) -> None:
        run_id = "run-20260930-result-read-error"
        self.open_run(run_id)
        chain_id = self.start_chain(run_id)
        state_before = self.state_path(chain_id).read_bytes()
        events_before = self.events_path(chain_id).read_bytes()

        cases = (
            (
                "policy",
                lambda: mock.patch.object(
                    CORE.Repository,
                    "policy",
                    side_effect=OSError("injected policy read failure"),
                ),
            ),
            (
                "journal",
                lambda: mock.patch.object(
                    journal,
                    "_scan_run",
                    side_effect=OSError("injected journal read failure"),
                ),
            ),
        )
        for name, patcher in cases:
            with self.subTest(name=name), patcher():
                exit_code, envelope, stderr = self.invoke_cli(
                    "--chain-id", chain_id, "verify"
                )
            self.assertEqual((exit_code, stderr), (1, ""))
            self.assertEqual(
                envelope["reason_code"], "run-task-binding-invalid"
            )
            self.assertEqual(
                envelope["message"],
                "forge: verify refused — pending execution_result inspection "
                "is unavailable",
            )
            self.assertEqual(
                envelope["expected"], "readable committed policy and run journal"
            )
            self.assertEqual(
                envelope["remediation"],
                "inspect the run journal and committed policy, then retry",
            )
            self.assertEqual(self.state_path(chain_id).read_bytes(), state_before)
            self.assertEqual(self.events_path(chain_id).read_bytes(), events_before)

    def test_pending_execution_does_not_intercept_review_cancel(self) -> None:
        run_id = "run-20260930-result-review-cancel"
        opening = self.open_run(run_id)
        chain_id = self.start_chain(run_id)
        execution = self.append_execution(run_id, opening)

        exit_code, envelope, stderr = self.invoke_cli(
            "--chain-id", chain_id, "review", "cancel"
        )

        self.assertEqual((exit_code, stderr), (1, ""))
        self.assertNotEqual(envelope["reason_code"], "execution-result-pending")
        self.assertNotIn(str(execution["execution"]), envelope["message"])

    def test_disable_leg_restores_commit_start(self) -> None:
        run_id = "run-20260930-result-disable"
        opening = self.open_run(run_id)
        execution = self.append_execution(run_id, opening)
        self.change("src/app.py", "VALUE = 2\n")

        def assert_refused() -> None:
            exit_code, envelope, _stderr = self.invoke_cli(
                "--run-id", run_id, "commit", "start", "--paths", "src/app.py",
                "--task", "task-01",
            )
            self.assertEqual(exit_code, 1, envelope)
            self.assertEqual(envelope["reason_code"], "execution-result-pending")

        assert_refused()
        with mock.patch.object(
            result_gate,
            "RESULT_GATE_CONTROLS",
            result_gate.RESULT_GATE_CONTROLS - {"result-before-gate"},
        ), self.assertRaises(AssertionError):
            assert_refused()
        self.assertTrue(list((self.repo / ".forge" / "chains").glob("c-*.json")))
        self.assertEqual(str(execution["execution"]), "execution-01")


class SerializationPlacementTests(unittest.TestCase):
    @staticmethod
    def fake_engine() -> SimpleNamespace:
        store = SimpleNamespace(
            common_root=Path("/fixture/common"),
            admission_lock=lambda _root: nullcontext(),
        )
        return SimpleNamespace(
            ctx=SimpleNamespace(
                store=store,
                repo=SimpleNamespace(root=Path("/fixture/repo")),
                options=SimpleNamespace(chain_id=None, revision9_face=True),
            )
        )

    def test_unbound_and_review_cancel_returns_never_call_hook(self) -> None:
        sentinel = object()

        def verify(_engine):
            return sentinel

        def review_cancel(_engine):
            return sentinel

        engine = self.fake_engine()
        with mock.patch.object(
            COMMAND_LOCK, "_command_run_lock_id", return_value=None
        ), mock.patch.object(
            COMMAND_LOCK,
            "_refuse_pending_result",
            side_effect=AssertionError("hook reached"),
        ):
            self.assertIs(COMMAND_LOCK._serialize_worktree_command(verify)(engine), sentinel)

        with (
            mock.patch.object(
                COMMAND_LOCK, "_command_run_lock_id", return_value="run-bound"
            ),
            mock.patch.object(COMMAND_LOCK.chain_core, "register_coordination_seams"),
            mock.patch.object(
                COMMAND_LOCK.chain_core,
                "_chain_batch_lock",
                return_value=nullcontext(),
            ),
            mock.patch.object(
                COMMAND_LOCK,
                "_refuse_pending_result",
                side_effect=AssertionError("hook reached"),
            ),
        ):
            wrapped = COMMAND_LOCK._serialize_worktree_command(review_cancel)
            self.assertIs(wrapped(engine), sentinel)

    def test_merge_family_gate_verbs_are_direct_and_unhooked(self) -> None:
        self.assertIs(CLI.MergeEngine.gate_run, MERGE_GATE.gate_run)
        self.assertIs(CLI.MergeEngine.verify, MERGE_GATE.verify)
        self.assertIs(
            CLI.MergeEngine.review_request,
            MERGE_REVIEW_LAUNCH.review_request,
        )
        for method in (
            CLI.MergeEngine.gate_run,
            CLI.MergeEngine.verify,
            CLI.MergeEngine.review_request,
        ):
            self.assertFalse(hasattr(method, "__wrapped__"))

    def test_bound_gated_return_calls_hook(self) -> None:
        def verify(_engine):
            raise AssertionError("method reached")

        engine = self.fake_engine()
        with (
            mock.patch.object(
                COMMAND_LOCK, "_command_run_lock_id", return_value="run-bound"
            ),
            mock.patch.object(COMMAND_LOCK.chain_core, "register_coordination_seams"),
            mock.patch.object(
                COMMAND_LOCK.chain_core,
                "_chain_batch_lock",
                return_value=nullcontext(),
            ),
            mock.patch.object(
                COMMAND_LOCK,
                "_refuse_pending_result",
                side_effect=RuntimeError("hook reached"),
            ),
            self.assertRaisesRegex(RuntimeError, "hook reached"),
        ):
            COMMAND_LOCK._serialize_worktree_command(verify)(engine)

    def test_nested_gate_checks_warn_once_per_invocation(self) -> None:
        sentinel = object()
        records = activated_records(
            task_record("task-01", "src/app.py"),
            task_record("task-02", "docs/guide.md"),
            execution_record(1, "task-02"),
        )
        request = COMMAND_LOCK._ResultGateRequest(
            "run-nested-warning",
            "verify",
            "task-01",
            ("src/app.py",),
            frozenset(),
            None,
        )
        warning = result_gate.warning_message(
            result_gate.Pending(
                "execution-01", "task-02", "codex-impl-01", False
            )
        )

        def gate_run(_engine):
            return sentinel

        wrapped_gate_run = COMMAND_LOCK._serialize_worktree_command(gate_run)

        def verify(current_engine):
            return wrapped_gate_run(current_engine)

        def enforce(_engine, _method_name, _run_id, _args) -> None:
            COMMAND_LOCK._enforce_pending_result(records, request)

        engine = self.fake_engine()
        with (
            mock.patch.object(
                COMMAND_LOCK, "_command_run_lock_id", return_value="run-bound"
            ),
            mock.patch.object(COMMAND_LOCK.chain_core, "register_coordination_seams"),
            mock.patch.object(
                COMMAND_LOCK.chain_core,
                "_chain_batch_lock",
                side_effect=lambda *_args, **_kwargs: nullcontext(),
            ),
            mock.patch.object(
                COMMAND_LOCK, "_refuse_pending_result", side_effect=enforce
            ),
        ):
            wrapped_verify = COMMAND_LOCK._serialize_worktree_command(verify)
            for _invocation in range(2):
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    self.assertIs(wrapped_verify(engine), sentinel)
                self.assertEqual(stderr.getvalue().splitlines(), [warning])


if __name__ == "__main__":
    unittest.main()
