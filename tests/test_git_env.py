from __future__ import annotations

import ast
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Mapping
from pathlib import Path
from unittest import mock

from tests import _git_env, _worker_quiescence
from tests._git_env import (
    QUIET_GIT_SETTINGS,
    init_quiet_repository,
    quiet_repository,
    with_quiet_git,
)
from tests._revision9_coord_constants import key as batch_key
from tests._revision9_coord_support import Revision9BuilderBatchSupport
from tests.test_worktree_guard import (
    MERGE_SKILL,
    WORKFLOW_SKILL,
    _WorktreeGuardFixture,
    mutated_function,
)

import codex_orch_tools
from codex_orchestrator import builders, journal, worktree_guard

ROOT = Path(__file__).resolve().parents[1]
THIS_MODULE = "tests/test_git_env.py"
GIT_ENV_HELPER = "tests/_git_env.py"
PENDING_ADOPTION = frozenset(
    {
        "tests/test_archive_replay_vocabulary.py",
        "tests/test_archive_run.py",
        "tests/test_audit_commitments.py",
        "tests/test_candidate_identity.py",
        "tests/test_cli_chain_finalize.py",
        "tests/test_cli_common_lock.py",
        "tests/test_cli_hook_integration.py",
        "tests/test_cli_merge_integration.py",
        "tests/test_cli_phase0_contracts.py",
        "tests/test_d13_concurrency.py",
        "tests/test_d14_learn_concurrency.py",
        "tests/test_drift_check.py",
        "tests/test_e2e_smoke.py",
        "tests/test_evals.py",
        "tests/test_fr223_v2_hook.py",
        "tests/test_gate_one_once.py",
        "tests/test_governance_scripts.py",
        # Landed after this candidate's repository-creation adoption sweep.
        "tests/test_ingest_changed_paths_renames.py",
        "tests/test_installer.py",
        "tests/test_invariant_guard.py",
        "tests/test_journal_patterns.py",
        "tests/test_launch_init_step.py",
        "tests/test_learn_proposals.py",
        "tests/test_migration.py",
        "tests/test_mutation_runner.py",
        "tests/test_revision9_archive.py",
        "tests/test_revision9_coordination.py",
        "tests/test_revision9_matrix.py",
        "tests/test_risk_tier.py",
        "tests/test_route_config_ownership.py",
        "tests/test_run_coordination.py",
        "tests/test_tree_index_drift_flags.py",
        "tests/test_vocab_readers.py",
        "tests/test_vocab_writers.py",
    }
)
SHELL_CREATION = re.compile(r"(?<![\w-])git\s+(?:init|clone)\b")


def _literal_text(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            value.value
            for value in node.values
            if isinstance(value, ast.Constant) and isinstance(value.value, str)
        )
    return None


def _call_label(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_label(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _sequence_creates_repository(nodes: list[ast.AST]) -> bool:
    values = [_literal_text(node) for node in nodes]
    return any(
        value == "git"
        and any(action in {"init", "clone"} for action in values[index + 1 :])
        for index, value in enumerate(values)
    )


def _node_creates_repository(node: ast.AST) -> bool:
    if isinstance(node, ast.Call):
        if _sequence_creates_repository(node.args):
            return True
        if _call_label(node.func) in {"git", "self.git", "git_at", "self.git_at"}:
            return any(
                _literal_text(argument) in {"init", "clone"}
                for argument in node.args
            )
    if isinstance(node, (ast.List, ast.Tuple)):
        return _sequence_creates_repository(node.elts)
    text = _literal_text(node)
    return text is not None and SHELL_CREATION.search(text) is not None


def _dynamic_git_argv(node: ast.AST) -> bool:
    return (
        isinstance(node, (ast.List, ast.Tuple))
        and bool(node.elts)
        and _literal_text(node.elts[0]) == "git"
        and any(isinstance(element, ast.Starred) for element in node.elts)
    )


def _action_sequence(node: ast.AST) -> bool:
    return (
        isinstance(node, (ast.List, ast.Tuple))
        and bool(node.elts)
        and _literal_text(node.elts[0]) in {"init", "clone"}
    )


def _creates_git_repository(source: str) -> bool:
    nodes = tuple(ast.walk(ast.parse(source)))
    if any(_node_creates_repository(node) for node in nodes):
        return True
    return any(_dynamic_git_argv(node) for node in nodes) and any(
        _action_sequence(node) for node in nodes
    )


def _imports_git_env(source: str) -> bool:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            if any(alias.name == "tests._git_env" for alias in node.names):
                return True
        if isinstance(node, ast.ImportFrom) and node.module == "tests._git_env":
            return True
        if isinstance(node, ast.ImportFrom) and node.module == "tests":
            if any(alias.name == "_git_env" for alias in node.names):
                return True
    return False


def _adoption_issues(
    sources: Mapping[str, str], pending: frozenset[str] = PENDING_ADOPTION
) -> list[str]:
    issues = [
        f"{label}: listed file no longer creates repositories"
        for label in sorted(pending - sources.keys())
    ]
    for label, source in sorted(sources.items()):
        if label == THIS_MODULE:
            continue
        creates = _creates_git_repository(source)
        imports_helper = _imports_git_env(source)
        if label in pending and imports_helper:
            issues.append(f"{label}: listed file already imports tests._git_env")
        elif label in pending and not creates:
            issues.append(f"{label}: listed file no longer creates repositories")
        elif (
            label not in pending
            and creates
            and not imports_helper
            and label != GIT_ENV_HELPER
        ):
            issues.append(f"{label}: unlisted repository creator")
    return issues


def _test_sources() -> dict[str, str]:
    return {
        path.relative_to(ROOT).as_posix(): path.read_text(encoding="utf-8")
        for path in (ROOT / "tests").glob("*.py")
    }


def _drain_git_maintenance(root: Path) -> None:
    if not root.is_dir():
        raise AssertionError(f"git fixture root removed before maintenance drain: {root}")
    _worker_quiescence.wait_for_quiescence(root)
    residents = _worker_quiescence.resident_processes(root)
    if residents:
        raise AssertionError(
            f"processes remain inside git fixture root after maintenance drain: {residents}"
        )


class _GitMaintenanceFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="forge-git-env-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.addCleanup(_drain_git_maintenance, self.root)


class GitMaintenanceDrainTests(_GitMaintenanceFixture):
    def test_drain_runs_before_temporary_directory_cleanup(self) -> None:
        root = self.root
        original_wait = _worker_quiescence.wait_for_quiescence

        def assert_root_present(selected: Path) -> None:
            self.assertEqual(selected, root)
            self.assertTrue(selected.is_dir())
            original_wait(selected)

        with mock.patch.object(
            _worker_quiescence,
            "wait_for_quiescence",
            side_effect=assert_root_present,
        ) as wait:
            self.doCleanups()

        wait.assert_called_once_with(root)
        self.assertFalse(root.exists())

    def test_drain_disable_leg_detects_resident_process(self) -> None:
        sentinel_pid = 910001
        with (
            mock.patch.object(_worker_quiescence, "wait_for_quiescence"),
            mock.patch.object(
                _worker_quiescence,
                "resident_processes",
                return_value=[sentinel_pid],
            ),
            self.assertRaisesRegex(AssertionError, str(sentinel_pid)),
        ):
            _drain_git_maintenance(self.root)


class GitEnvironmentTests(_GitMaintenanceFixture):
    def trace_environment(self) -> dict[str, str]:
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("GIT_CONFIG_")
        }
        environment.update(
            {
                "GIT_TRACE": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_AUTHOR_NAME": "Forge Tests",
                "GIT_AUTHOR_EMAIL": "forge-tests@example.invalid",
                "GIT_COMMITTER_NAME": "Forge Tests",
                "GIT_COMMITTER_EMAIL": "forge-tests@example.invalid",
                "GIT_TERMINAL_PROMPT": "0",
                "LC_ALL": "C",
            }
        )
        return environment

    def git(
        self, repository: Path, *arguments: str, environment: Mapping[str, str]
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(repository), *arguments],
            env=environment,
            capture_output=True,
            text=True,
            check=True,
        )

    def repo_local_scenario(self, name: str) -> tuple[str, Path, Path]:
        scenario = self.root / name
        scenario.mkdir()
        local = scenario / "local"
        remote = scenario / "origin.git"
        environment = self.trace_environment()
        local_init = init_quiet_repository(local, "--quiet", environment=environment)
        remote_init = init_quiet_repository(
            remote, "--bare", "--quiet", environment=environment
        )
        self.assertEqual((local_init.returncode, remote_init.returncode), (0, 0))
        self.assertIsInstance(local_init.stdout, str)
        traces = []
        traces.append(
            self.git(
                local,
                "commit",
                "--allow-empty",
                "--quiet",
                "-m",
                "initial",
                environment=environment,
            ).stderr
        )
        self.git(local, "remote", "add", "origin", str(remote), environment=environment)
        traces.append(
            self.git(
                local,
                "push",
                "--quiet",
                "--set-upstream",
                "origin",
                "HEAD",
                environment=environment,
            ).stderr
        )
        traces.append(self.git(local, "fetch", "origin", environment=environment).stderr)
        return "\n".join(traces), local, remote

    def assert_settings_readable(self, repository: Path) -> None:
        environment = self.trace_environment()
        for key, value in QUIET_GIT_SETTINGS:
            with self.subTest(repository=repository.name, key=key):
                result = self.git(
                    repository, "config", "--get", key, environment=environment
                )
                self.assertEqual(result.stdout.strip(), value)

    def plain_fetch_trace(self, name: str, *, quiet_environment: bool) -> str:
        scenario = self.root / name
        scenario.mkdir()
        local = scenario / "local"
        remote = scenario / "origin.git"
        environment = self.trace_environment()
        subprocess.run(
            ["git", "init", "--quiet", str(local)],
            env=environment,
            check=True,
            capture_output=True,
        )
        init_quiet_repository(remote, "--bare", "--quiet", environment=environment)
        setup_environment = with_quiet_git(environment)
        self.git(
            local,
            "commit",
            "--allow-empty",
            "--quiet",
            "-m",
            "seed",
            environment=setup_environment,
        )
        self.git(local, "remote", "add", "origin", str(remote), environment=setup_environment)
        self.git(local, "push", "--quiet", "origin", "HEAD", environment=setup_environment)
        selected = with_quiet_git(environment) if quiet_environment else environment
        return self.git(local, "fetch", str(remote), environment=selected).stderr

    def linked_worktree_fixture(self, name: str) -> tuple[Path, Path]:
        main = self.root / f"{name}-main"
        linked = self.root / f"{name}-linked"
        environment = with_quiet_git(self.trace_environment())
        subprocess.run(
            ["git", "init", "--quiet", str(main)],
            env=environment,
            check=True,
            capture_output=True,
        )
        self.git(
            main,
            "commit",
            "--allow-empty",
            "--quiet",
            "-m",
            "linked worktree base",
            environment=environment,
        )
        self.git(
            main,
            "worktree",
            "add",
            "--quiet",
            "-b",
            f"{name}-branch",
            str(linked),
            environment=environment,
        )
        return main, linked

    def assert_preserving_merge(self) -> None:
        original = {
            "SENTINEL": "kept",
            "GIT_CONFIG_COUNT": "2",
            "GIT_CONFIG_KEY_0": "user.name",
            "GIT_CONFIG_VALUE_0": "Existing User",
            "GIT_CONFIG_KEY_1": "user.email",
            "GIT_CONFIG_VALUE_1": "existing@example.invalid",
        }
        untouched = dict(original)
        merged = _git_env.with_quiet_git(original)
        self.assertEqual(original, untouched)
        self.assertIsNot(merged, original)
        self.assertEqual(merged["SENTINEL"], "kept")
        self.assertEqual(merged["GIT_CONFIG_COUNT"], "7")
        for index in range(2):
            self.assertEqual(merged[f"GIT_CONFIG_KEY_{index}"], original[f"GIT_CONFIG_KEY_{index}"])
            self.assertEqual(
                merged[f"GIT_CONFIG_VALUE_{index}"],
                original[f"GIT_CONFIG_VALUE_{index}"],
            )
        for offset, (key, value) in enumerate(QUIET_GIT_SETTINGS, start=2):
            self.assertEqual(merged[f"GIT_CONFIG_KEY_{offset}"], key)
            self.assertEqual(merged[f"GIT_CONFIG_VALUE_{offset}"], value)

    def test_repo_local_settings_survive_environment_scrubbing(self) -> None:
        trace, local, remote = self.repo_local_scenario("quiet")
        self.assertNotIn("maintenance run", trace)
        self.assert_settings_readable(local)
        self.assert_settings_readable(remote)

        with mock.patch.object(_git_env, "QUIET_GIT_SETTINGS", ()):
            disabled_trace, _disabled_local, _disabled_remote = self.repo_local_scenario(
                "disabled"
            )
        maintenance = [
            line
            for line in disabled_trace.splitlines()
            if "maintenance run --auto" in line
        ]
        self.assertTrue(any(not line.startswith("remote:") for line in maintenance))
        self.assertTrue(any(line.startswith("remote:") for line in maintenance))

    def test_environment_layer_suppresses_fetch_maintenance(self) -> None:
        quiet_trace = self.plain_fetch_trace("environment-quiet", quiet_environment=True)
        disabled_trace = self.plain_fetch_trace(
            "environment-disabled", quiet_environment=False
        )
        self.assertNotIn("maintenance run", quiet_trace)
        self.assertIn("maintenance run --auto", disabled_trace)

    def test_environment_merge_preserves_entries_and_detects_overwrite(self) -> None:
        self.assert_preserving_merge()

        def overwrite(environment: Mapping[str, str]) -> dict[str, str]:
            merged = dict(environment)
            for index, (key, value) in enumerate(QUIET_GIT_SETTINGS):
                merged[f"GIT_CONFIG_KEY_{index}"] = key
                merged[f"GIT_CONFIG_VALUE_{index}"] = value
            merged["GIT_CONFIG_COUNT"] = str(len(QUIET_GIT_SETTINGS))
            return merged

        with mock.patch.object(_git_env, "with_quiet_git", side_effect=overwrite):
            with self.assertRaises(AssertionError):
                self.assert_preserving_merge()

    def test_environment_merge_rejects_malformed_counts(self) -> None:
        malformed = (
            {"GIT_CONFIG_COUNT": "x"},
            {"GIT_CONFIG_COUNT": "-1"},
            {
                "GIT_CONFIG_COUNT": "2",
                "GIT_CONFIG_KEY_0": "user.name",
                "GIT_CONFIG_VALUE_0": "Forge",
                "GIT_CONFIG_VALUE_1": "missing key",
            },
        )
        for environment in malformed:
            with self.subTest(environment=environment):
                with self.assertRaises(ValueError):
                    with_quiet_git(environment)

    def test_environment_merge_is_idempotent(self) -> None:
        original = {"SENTINEL": "unchanged"}
        once = with_quiet_git(original)
        twice = with_quiet_git(once)
        self.assertEqual(once, twice)
        self.assertIsNot(once, twice)
        self.assertEqual(original, {"SENTINEL": "unchanged"})

    def test_init_runs_once_and_missing_config_fails_closed(self) -> None:
        completed = subprocess.CompletedProcess(
            ["git", "init"], returncode=1, stdout="failed stdout", stderr="failed stderr"
        )
        target = self.root / "absent"
        with mock.patch.object(_git_env.subprocess, "run", return_value=completed) as run:
            with self.assertRaises(FileNotFoundError):
                init_quiet_repository(
                    target,
                    "--quiet",
                    cwd=self.root,
                    environment={"PATH": os.environ.get("PATH", os.defpath)},
                )
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], ["git", "init", "--quiet", str(target)])
        self.assertTrue(run.call_args.kwargs["text"])
        self.assertTrue(run.call_args.kwargs["capture_output"])

    def test_quiet_repository_detects_regular_and_bare_layouts(self) -> None:
        environment = self.trace_environment()
        regular = self.root / "regular"
        bare = self.root / "bare.git"
        subprocess.run(
            ["git", "init", "--quiet", str(regular)],
            env=environment,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "init", "--bare", "--quiet", str(bare)],
            env=environment,
            check=True,
            capture_output=True,
        )
        quiet_repository(regular)
        quiet_repository(bare)
        self.assert_settings_readable(regular)
        self.assert_settings_readable(bare)
        with self.assertRaises(FileNotFoundError):
            quiet_repository(self.root / "not-a-repository")
        false_bare = self.root / "false-bare"
        false_bare.mkdir()
        (false_bare / "config").write_text("[core]\n\tbare = true\n", encoding="utf-8")
        with self.assertRaises(FileNotFoundError):
            quiet_repository(false_bare)

    def test_quiet_repository_persists_linked_worktree_shared_config(self) -> None:
        main, linked = self.linked_worktree_fixture("shared")
        common_config = main / ".git" / "config"
        self.assertNotIn("maintenance", common_config.read_text(encoding="utf-8"))

        quiet_repository(linked)

        self.assertEqual(_git_env._repository_config(linked), common_config)
        self.assert_settings_readable(main)
        self.assert_settings_readable(linked)

        _disabled_main, disabled_linked = self.linked_worktree_fixture("disabled")
        with mock.patch.object(_git_env, "_linked_worktree_config", return_value=None):
            with self.assertRaises(FileNotFoundError):
                quiet_repository(disabled_linked)

    def test_repository_creation_adoption_is_an_exact_ratchet(self) -> None:
        self.assertEqual(len(PENDING_ADOPTION), 34)
        self.assertEqual(_adoption_issues(_test_sources()), [])

    def test_repo_conformance_imports_in_commitment_audit_script_mode(self) -> None:
        run_dir = self.root / "conformance-run"
        run_dir.mkdir()
        (run_dir / "journal.jsonl").write_text("", encoding="utf-8")
        environment = {
            key: value for key, value in os.environ.items() if key != "PYTHONPATH"
        }

        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tests/test_repo_conformance.py"),
                "--run-dir",
                str(run_dir),
            ],
            cwd=ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(
            result.stdout,
            "## Historical Routing Findings\n\nNone recorded\n",
        )

    def test_adoption_scanner_flags_an_unlisted_creator_when_disabled(self) -> None:
        synthetic = {
            "tests/test_unlisted_creator.py": (
                'subprocess.run(["git", "init", "--quiet", str(repo)])\n'
            )
        }
        self.assertEqual(
            _adoption_issues(synthetic, frozenset()),
            ["tests/test_unlisted_creator.py: unlisted repository creator"],
        )

    def test_adoption_scanner_excludes_known_init_false_positives(self) -> None:
        source = (
            'record = {"subtype": "init"}\n'
            'invoke("init", "--project", "fixture")\n'
        )
        self.assertFalse(_creates_git_repository(source))


class WorktreeGuardWriterCompatibilityTests(
    Revision9BuilderBatchSupport, unittest.TestCase
):
    def _guard_status(self, target: Path) -> int:
        with mock.patch.object(sys, "stderr", io.StringIO()):
            return worktree_guard.main(self.repo, target)

    def _target(self) -> Path:
        target = Path(self.temporary.name) / "cleanup-target"
        target.mkdir()
        return target

    def test_raw_writer_empty_citations_match_guard_shape_validation(self) -> None:
        run_id = "run-writer-empty-citations"
        execution = {
            "type": "execution", "recorded_at": "2026-10-04T00:00:01Z",
            "run_id": run_id, "execution": "execution-01", "agent": "claude-review-01",
            "task": "task-01", "provider": "claude", "role": "review-final",
            "mode": "subagent", "model": "fable", "effort": "high",
            "worktree": str(self.repo), "head": self.head, "prompt": "prompt.md",
            "handoff": "handoff.md", "event_source": "claude", "events": "",
        }
        result = {
            "type": "execution_result", "recorded_at": "2026-10-04T00:00:02Z",
            "run_id": run_id, "execution": "execution-01", "agent": "claude-review-01",
            "task": "task-01", "status": "blocked", "summary": "blocked",
            "files_changed": [], "caveats": [], "handoff": "",
        }
        with self.api_environment():
            self._open_legacy_run(self.repo, run_id)
            for invalid in (dict(execution, events=None), dict(result, handoff=None)):
                with self.assertRaises(journal.CoordinationRefusal):
                    journal.append_run_record(self.repo, run_id, invalid)
                with self.assertRaises(worktree_guard.WorktreeGuardError):
                    worktree_guard._normalize_record_shapes([invalid])
            journal.append_run_record(self.repo, run_id, execution)
            journal.append_run_record(self.repo, run_id, result)
        target = self._target()
        self.assertEqual(self._guard_status(target), 0)
        validator = worktree_guard._citation_field_is_valid

        def reject_empty(extraction: str, value: object, *, allow_empty: bool = False) -> bool:
            return validator(extraction, value)

        with mock.patch.object(worktree_guard, "_citation_field_is_valid", reject_empty):
            self.assertEqual(self._guard_status(target), 2)

    def test_typed_builder_null_optionals_are_omitted_and_guard_valid(self) -> None:
        run_id = "run-builder-optional-citations"
        with self.api_environment():
            opening = self.open_run(self.repo, run_id).records[0]
            self.start_task(self.repo, run_id)
            run_dir = self.run_dir(self.repo, run_id)
            for name in ("prompt.md", "handoff.md"):
                (run_dir / name).write_text("evidence\n", encoding="utf-8")
            route = opening["route"]["review-final"]
            execution = builders.execution_start(
                self.repo, run_id, idempotency_key=batch_key("optional-execution"),
                agent="claude-review-final-01", task="task-01", provider=route["provider"],
                role="review-final", mode="subagent", model=route["model"],
                effort=route["effort"], worktree=str(self.repo.resolve()), head=self.head,
                prompt="prompt.md", handoff="handoff.md", event_source="claude", events=None,
                sandbox=journal.route_evidence.route_config.profile_sandbox(
                    route["provider"], "review-final"), route_source=route["route_source"],
                route_sha256=route["route_sha256"],
            )
            builders.execution_result(
                self.repo, run_id, idempotency_key=batch_key("optional-result"),
                execution=execution.records[0]["execution"], agent="claude-review-final-01",
                task="task-01", status="blocked", summary="blocked", files_changed=[],
                caveats=[], handoff=None,
            )
        records, issues = journal.read_journal(run_dir / "journal.jsonl")
        self.assertEqual(issues, [])
        persisted = [record for record in records if record["type"].startswith("execution")]
        self.assertNotIn("events", persisted[0])
        self.assertNotIn("handoff", persisted[1])
        self.assertEqual(self._guard_status(self._target()), 0)


class WorktreeGuardAdditionalControlTests(_WorktreeGuardFixture, unittest.TestCase):
    def test_runs_root_ancestor_symlink_check_is_load_bearing(self) -> None:
        orchestration_root = self.repo / ".codex-orchestrator"
        symlink_target = self.base / "orchestration-state"
        (symlink_target / "runs").mkdir(parents=True)
        orchestration_root.symlink_to(symlink_target, target_is_directory=True)
        anchor = "        or runs_root.resolve(strict=True) != runs_root\n"
        mutant = mutated_function(worktree_guard._runs_root_entries, anchor, "")

        self.assertEqual(self._in_process(), self._expected_result(2))
        with mock.patch.object(worktree_guard, "_runs_root_entries", mutant):
            self.assertEqual(self._in_process(), self._expected_result(0))

    def test_worktree_argument_must_be_a_directory(self) -> None:
        target = self.base / "not-a-directory"
        target.write_text("not a worktree\n", encoding="utf-8")
        anchor = "        if not repository.is_dir() or not target.is_dir():\n"
        replacement = "        if not repository.is_dir():\n"
        mutant = mutated_function(worktree_guard.find_dependency, anchor, replacement)

        self.assertEqual(self._in_process(target), self._expected_result(2))
        with mock.patch.object(worktree_guard, "find_dependency", mutant):
            self.assertEqual(self._in_process(target), self._expected_result(0))

    def test_worktree_guard_import_failure_is_a_refusal(self) -> None:
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(
            codex_orch_tools.importlib, "import_module", side_effect=ImportError("broken guard")
        ), mock.patch.object(sys, "stdout", stdout), mock.patch.object(sys, "stderr", stderr):
            status = codex_orch_tools._coordination_main([
                "worktree-check", "--repo", str(self.repo), "--worktree", str(self.worktree)])
        self.assertEqual((status, stdout.getvalue()), (2, ""))
        self.assertEqual(stderr.getvalue(), worktree_guard.INPUT_DIAGNOSTIC + "\n")

    def test_worktree_check_help_is_refused_and_control_is_load_bearing(self) -> None:
        tools = ROOT / "scripts/codex_orch_tools.py"
        for option in ("-h", "--help"):
            result = subprocess.run(
                [sys.executable, str(tools), "worktree-check", option],
                check=False, capture_output=True, text=True,
            )
            with self.subTest(option=option):
                self.assertEqual((result.returncode, result.stdout), (2, ""))
                self.assertEqual(
                    result.stderr.splitlines()[0], worktree_guard.INPUT_DIAGNOSTIC
                )
                self.assertIn("usage:", result.stderr)

        mutant = mutated_function(
            codex_orch_tools._worktree_check_parser, "        add_help=False,\n", ""
        )
        with mock.patch.object(codex_orch_tools, "_worktree_check_parser", mutant), \
                mock.patch.object(sys, "stdout", io.StringIO()), \
                mock.patch.object(sys, "stderr", io.StringIO()), \
                self.assertRaises(SystemExit) as caught:
            codex_orch_tools._worktree_check_main(["--help"])
        self.assertEqual(caught.exception.code, 0)

    def test_eager_entry_import_failure_is_exit_two_and_control_is_load_bearing(
        self,
    ) -> None:
        source = (ROOT / "scripts/codex_orch_tools.py").read_text(encoding="utf-8")
        anchor = (
            '    if __name__ == "__main__" and sys.argv[1:2] == '
            '["worktree-check"]:\n'
        )
        self.assertEqual(source.count(anchor), 1)

        def execute(candidate: str) -> tuple[BaseException, str]:
            original_import = __import__

            def failing_import(
                name: str, globals_: object = None, locals_: object = None,
                fromlist: object = (), level: int = 0,
            ) -> object:
                if name == "codex_orchestrator.cli":
                    raise ImportError("disabled eager import")
                return original_import(name, globals_, locals_, fromlist, level)

            stderr = io.StringIO()
            namespace = {
                "__name__": "__main__",
                "__file__": str(ROOT / "scripts/codex_orch_tools.py"),
            }
            with mock.patch("builtins.__import__", side_effect=failing_import), \
                    mock.patch.object(sys, "argv", ["codex_orch_tools.py", "worktree-check"]), \
                    mock.patch.object(sys, "stderr", stderr):
                try:
                    exec(compile(candidate, "codex_orch_tools.py", "exec"), namespace)
                except (ImportError, SystemExit) as exc:
                    return exc, stderr.getvalue()
            raise AssertionError("entry script unexpectedly returned")

        intact, diagnostic = execute(source)
        self.assertIsInstance(intact, SystemExit)
        self.assertEqual(getattr(intact, "code", None), 2)
        self.assertEqual(diagnostic, worktree_guard.INPUT_DIAGNOSTIC + "\n")
        disabled, disabled_diagnostic = execute(source.replace(anchor, "    if False:\n", 1))
        self.assertIsInstance(disabled, ImportError)
        self.assertEqual(disabled_diagnostic, "")

    def test_operator_release_and_post_removal_controls_are_load_bearing(self) -> None:
        protocol = (
            "a passed run that remains unarchivable after the deferred workflow retry, a retired "
            "run, or a blocked run that is not gate-clean",
            "remains `cleanup deferred` with its worktree and branch intact",
            "only as an operator-reserved cleanup under explicit terminal direction recorded as "
            "an operator `decision` in an open run's journal",
            "The operator—not this skill or any agent—runs `git -C <main-worktree> worktree "
            "remove <absolute-worktree-path>` without a force option",
            "only after independently re-proving the branch tip and remote containment",
            "`git -C <main-worktree> update-ref -d <branch-ref> <verified-old-oid>`",
            "Agents never run either command themselves, never release that worktree, and never "
            "treat the operator decision as guard exit 0",
        )
        mechanics = (
            ("merge", 'cd "$MAIN_WORKTREE" || {'),
            ("merge", "branch tip changed during cleanup — cleanup incomplete"),
            ("merge", "branch tip is not contained in origin/${DEFAULT_BRANCH} "
             "— cleanup incomplete"),
            ("workflow", "branch tip changed during cleanup — cleanup incomplete"),
            ("workflow", "branch tip is not contained in "
             "origin/${DEFERRED_DEFAULT_BRANCH} — cleanup incomplete"),
        )

        def assert_contract(merge: str, workflow: str) -> None:
            sources = {"merge": merge, "workflow": workflow}
            for text in sources.values():
                normalized = " ".join(text.split())
                for fragment in protocol:
                    self.assertEqual(normalized.count(fragment), 1)
                self.assertEqual(
                    [normalized.index(fragment) for fragment in protocol],
                    sorted(normalized.index(fragment) for fragment in protocol),
                )
            for scope, fragment in mechanics:
                self.assertEqual(sources[scope].count(fragment), 1)
            cleanup = merge.split("## Cleanup after successful push", 1)[1].split(
                "## Record authority and report", 1
            )[0]
            self.assertLess(
                cleanup.index('cd "$MAIN_WORKTREE" || {'),
                cleanup.index('git -C "$MAIN_WORKTREE" worktree remove "$WORKTREE_DIR"'),
            )
            self.assertNotIn(
                "branch tip changed during cleanup — branch preserved",
                merge + workflow,
            )
            self.assertNotIn(
                "branch tip is not contained in origin/${DEFAULT_BRANCH} "
                "— branch preserved",
                merge,
            )
            self.assertNotIn(
                "branch tip is not contained in origin/${DEFERRED_DEFAULT_BRANCH} "
                "— branch preserved",
                workflow,
            )

        assert_contract(MERGE_SKILL, WORKFLOW_SKILL)
        for scope, fragment in mechanics:
            sources = {"merge": MERGE_SKILL, "workflow": WORKFLOW_SKILL}
            sources[scope] = sources[scope].replace(fragment, "DISABLED_CONTROL", 1)
            with self.subTest(disabled=fragment), self.assertRaises(AssertionError):
                assert_contract(sources["merge"], sources["workflow"])
        for scope, source in (("merge", MERGE_SKILL), ("workflow", WORKFLOW_SKILL)):
            for fragment in protocol:
                mutated = " ".join(source.split()).replace(
                    fragment, "DISABLED_CONTROL", 1
                )
                with self.subTest(scope=scope, disabled=fragment[:24]), \
                        self.assertRaises(AssertionError):
                    assert_contract(
                        mutated if scope == "merge" else MERGE_SKILL,
                        mutated if scope == "workflow" else WORKFLOW_SKILL,
                    )

    def test_permanently_unarchivable_runs_remain_deferred_after_decision(self) -> None:
        from tests import test_worktree_merge_skill as cleanup_test

        real_apply = cleanup_test.apply_cleanup_scenario

        def apply_permanent(fixture: object, scenario: str) -> str:
            if not scenario.startswith("permanent-"):
                return real_apply(fixture, scenario)
            main, worktree = fixture.main, fixture.worktree
            run_id = "run-a-" + scenario.removeprefix("permanent-")
            if scenario == "permanent-retired":
                opening = {"type": "run_started", "id": run_id,
                           "repo": str(worktree), "scope": ["src/**"]}
                tail = [{"type": "decision", "id": "forge-run-retired",
                         "resolution": journal.RETIREMENT_RESOLUTION}]
            else:
                opening = {"type": "run_started", "run_id": run_id,
                           "repo": str(worktree)}
                judgment = "passed" if scenario == "permanent-passed" else "blocked"
                tail = ([{"type": "verification", "id": "check-01", "result": "failed",
                          "evidence": []}] if judgment == "blocked" else [])
                tail.append({"type": "run_closed", "judgment": judgment})
            records_by_run = {
                run_id: [opening, *tail],
                "run-z-operator-direction": [
                    {"type": "run_started", "run_id": "run-z-operator-direction",
                     "repo": str(main)},
                    {"type": "decision", "id": "operator-release-direction",
                     "resolution": "terminal cleanup directed by operator"},
                ],
            }
            for selected_run, records in records_by_run.items():
                run_dir = main / ".codex-orchestrator" / "runs" / selected_run
                run_dir.mkdir(parents=True)
                (run_dir / "journal.jsonl").write_text(
                    "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
                )
                (run_dir / "owner").write_text(
                    "pid: 1\nhost: forge-tests\nstarted_at: 2026-10-04T00:00:00Z\n",
                    encoding="utf-8",
                )
            return cleanup_test.run_git(
                main, "rev-parse", "refs/heads/topic"
            ).stdout.strip()

        with mock.patch.object(
            cleanup_test, "apply_cleanup_scenario", side_effect=apply_permanent
        ):
            for scenario in ("permanent-passed", "permanent-retired", "permanent-blocked"):
                for kind in ("merge", "workflow"):
                    outcome = cleanup_test.run_cleanup_case(kind, scenario)
                    with self.subTest(run_class=scenario, block=kind):
                        self.assertEqual(outcome.process.returncode, 0 if kind == "merge" else 1)
                        self.assertIn(f"cleanup deferred — run run-a-{scenario[10:]}",
                                      outcome.process.stderr)
                        self.assertTrue(outcome.worktree_exists)
                        self.assertEqual(outcome.branch_tip, outcome.expected_tip)

    def test_successful_merge_cleanup_returns_to_main_worktree(self) -> None:
        from tests.test_worktree_merge_skill import SKILL, run_cleanup_case

        marker = "esac\n```\n\nRun the worktree-removal command exactly as shown"
        self.assertEqual(SKILL.count(marker), 1)
        probed = SKILL.replace(
            marker,
            "esac\npwd\n```\n\nRun the worktree-removal command exactly as shown",
            1,
        )
        outcome = run_cleanup_case("merge", "clean", skill=probed)
        self.assertEqual(outcome.process.returncode, 0, outcome.process.stderr)
        self.assertTrue(outcome.process.stdout.rstrip().endswith("/main"))


class WorkflowRetryStatusTests(unittest.TestCase):
    def test_repository_probe_and_fetch_failures_are_distinct_refusals(self) -> None:
        from tests.test_worktree_merge_skill import WORKFLOW, run_cleanup_case

        cases = (
            (WORKFLOW.replace('REPO="$(git rev-parse --show-toplevel 2>/dev/null)"',
                              'REPO="$(false 2>/dev/null)"', 1),
             "forge: repository root is unavailable — cleanup refused"),
            (WORKFLOW.replace("fetch origin", "fetch missing-origin", 1),
             "forge: default-branch fetch failed — cleanup refused"),
        )
        for workflow, diagnostic in cases:
            outcome = run_cleanup_case("workflow", "clean", workflow=workflow)
            with self.subTest(diagnostic=diagnostic):
                self.assertEqual(outcome.process.returncode, 2, outcome.process.stderr)
                self.assertIn(diagnostic, outcome.process.stderr)
                self.assertTrue(outcome.worktree_exists)
                self.assertEqual(outcome.branch_tip, outcome.expected_tip)


if __name__ == "__main__":
    unittest.main()
